(function () {
  const { createApp, ref, reactive, computed, onMounted, onBeforeUnmount } = Vue;

  function formatClock() {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`;
  }

  createApp({
    setup() {
      const currentTime = ref(formatClock());
      const activeTab = ref('dashboard');
      const tasks = ref([]);
      const filterStatus = ref('all');
      const searchQuery = ref('');
      const showTaskForm = ref(false);
      const editingTask = ref(null);
      const loading = ref(false);
      const dashboard = ref(null);
      const formData = reactive({
        taskName: '',
        containerId: '',
        origin: '',
        destination: '',
        yardSlot: '',
        status: 'pending',
      });
      let clockTimer = null;
      let refreshTimer = null;

      const origins = ['泊位1', '泊位2', '泊位3', '重箱堆场A', '空箱堆场B', '危险品堆场C'];
      const destinations = ['重箱堆场A', '空箱堆场B', '危险品堆场C', '泊位1', '泊位2', '泊位3'];

      function statusLabel(status) {
        return status === 'pending' ? '未开始' : status === 'in-progress' ? '进行中' : status === 'completed' ? '已完成' : status;
      }

      function nextActionLabel(status) {
        return status === 'pending' ? '开始' : status === 'in-progress' ? '完成' : '已完成';
      }

      function formatTime(value) {
        if (!value) return '-';
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return value;
        return `${String(date.getMonth() + 1).padStart(2, '0')}/${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
      }

      function normalizeTask(raw) {
        return {
          id: raw.id,
          taskNo: raw.taskNo || raw.task_no || '',
          taskName: raw.taskName || raw.task_type || '',
          containerId: raw.containerId || '',
          origin: raw.origin || raw.from_pos || '',
          destination: raw.destination || raw.to_pos || '',
          yardSlot: raw.yardSlot || '',
          status: raw.status || 'pending',
          updatedAt: raw.updatedAt || raw.updated_at || '',
          createdAt: raw.createdAt || raw.created_at || '',
        };
      }

      async function loadTasks(silent = false) {
        if (!silent) loading.value = true;
        try {
          const resp = await fetch('/tasks', { credentials: 'same-origin' });
          if (!resp.ok) throw new Error('作业单数据加载失败');
          const data = await resp.json();
          tasks.value = Array.isArray(data) ? data.map(normalizeTask) : [];
        } catch (err) {
          tasks.value = [];
        } finally {
          if (!silent) loading.value = false;
        }
      }

      async function loadDashboard() {
        try {
          const resp = await fetch('/api/dashboard/stats', { credentials: 'same-origin' });
          if (!resp.ok) throw new Error('统计数据加载失败');
          dashboard.value = await resp.json();
        } catch (err) {
          dashboard.value = null;
        }
      }

      const statusCounts = computed(() => {
        const counts = { pending: 0, inProgress: 0, completed: 0 };
        tasks.value.forEach((task) => {
          if (task.status === 'pending' || task.status === '未开始') counts.pending += 1;
          else if (task.status === 'in-progress' || task.status === '进行中') counts.inProgress += 1;
          else if (task.status === 'completed' || task.status === '已完成') counts.completed += 1;
        });
        return counts;
      });

      const completionRate = computed(() => {
        if (!tasks.value.length) return 0;
        return Math.round((statusCounts.value.completed / tasks.value.length) * 100);
      });

      const filteredTasks = computed(() => {
        let list = tasks.value.slice();
        if (filterStatus.value !== 'all') {
          list = list.filter((task) => task.status === filterStatus.value || task.status === statusLabel(filterStatus.value));
        }
        if (searchQuery.value.trim()) {
          const q = searchQuery.value.trim().toLowerCase();
          list = list.filter((task) => [task.taskName, task.containerId, task.origin, task.destination, task.yardSlot, task.taskNo].join(' ').toLowerCase().includes(q));
        }
        return list.sort((a, b) => String(b.updatedAt).localeCompare(String(a.updatedAt)));
      });

      const recentTasks = computed(() => tasks.value.slice().sort((a, b) => String(b.updatedAt).localeCompare(String(a.updatedAt))).slice(0, 6));

      const yardSummary = computed(() => {
        const rows = dashboard.value?.yardUsage || [];
        if (rows.length > 0) {
          return rows.map((item) => ({
            name: item.name,
            used: item.used,
            total: item.total,
            usage: item.usageRate,
          }));
        }
        return [
          { name: '重箱堆场A', used: 0, total: 0, usage: 0 },
          { name: '空箱堆场B', used: 0, total: 0, usage: 0 },
          { name: '危险品堆场C', used: 0, total: 0, usage: 0 },
        ];
      });

      function openTaskForm(task = null) {
        if (task) {
          editingTask.value = task;
          formData.taskName = task.taskName;
          formData.containerId = task.containerId;
          formData.origin = task.origin;
          formData.destination = task.destination;
          formData.yardSlot = task.yardSlot;
          formData.status = task.status;
        } else {
          editingTask.value = null;
          formData.taskName = '';
          formData.containerId = '';
          formData.origin = origins[0];
          formData.destination = destinations[0];
          formData.yardSlot = '';
          formData.status = 'pending';
        }
        showTaskForm.value = true;
      }

      function closeTaskForm() {
        showTaskForm.value = false;
        editingTask.value = null;
      }

      async function saveTask() {
        if (!formData.taskName.trim()) {
          alert('请输入任务名称');
          return;
        }
        const payload = {
          taskName: formData.taskName.trim(),
          containerId: formData.containerId.trim(),
          origin: formData.origin,
          destination: formData.destination,
          yardSlot: formData.yardSlot.trim(),
          status: formData.status,
        };
        const url = editingTask.value ? `/tasks/${editingTask.value.id}` : '/tasks';
        const method = editingTask.value ? 'PUT' : 'POST';
        const resp = await fetch(url, {
          method,
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify(payload),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
          alert(data.message || '保存作业单失败');
          return;
        }
        closeTaskForm();
        await loadTasks();
      }

      async function advanceStatus(task) {
        const nextStatus = task.status === 'pending' ? 'in-progress' : task.status === 'in-progress' ? 'completed' : task.status;
        if (nextStatus === task.status) return;
        const resp = await fetch(`/tasks/${task.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ ...task, status: nextStatus }),
        });
        if (!resp.ok) {
          const data = await resp.json().catch(() => ({}));
          alert(data.message || '更新状态失败');
          return;
        }
        await loadTasks();
      }

      async function deleteTask(id) {
        if (!confirm('确定删除该作业单吗？')) return;
        const resp = await fetch(`/tasks/${id}`, {
          method: 'DELETE',
          credentials: 'same-origin',
        });
        if (!resp.ok) {
          const data = await resp.json().catch(() => ({}));
          alert(data.message || '删除作业单失败');
          return;
        }
        await loadTasks();
      }

      function refreshClock() {
        currentTime.value = formatClock();
      }

      onMounted(() => {
        refreshClock();
        loadTasks();
        loadDashboard();
        clockTimer = setInterval(refreshClock, 1000);
        refreshTimer = setInterval(() => {
          loadTasks(true);
          if (activeTab.value === 'dashboard' || activeTab.value === 'status') {
            loadDashboard();
          }
        }, 5000);
      });

      onBeforeUnmount(() => {
        if (clockTimer) clearInterval(clockTimer);
        if (refreshTimer) clearInterval(refreshTimer);
      });

      return {
        currentTime,
        activeTab,
        tasks,
        filterStatus,
        searchQuery,
        showTaskForm,
        editingTask,
        loading,
        dashboard,
        formData,
        statusCounts,
        completionRate,
        filteredTasks,
        recentTasks,
        yardSummary,
        origins,
        destinations,
        statusLabel,
        nextActionLabel,
        formatTime,
        openTaskForm,
        closeTaskForm,
        saveTask,
        advanceStatus,
        deleteTask,
      };
    },
  }).mount('#app');
})();

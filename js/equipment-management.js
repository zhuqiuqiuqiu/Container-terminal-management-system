const { createApp, ref, reactive, computed, onMounted, onBeforeUnmount } = Vue;

createApp({
  setup() {
    const currentTime = ref('');
    const activeTab = ref('dashboard');
    const equipment = ref([]);
    const tasks = ref([]);
    const searchQuery = ref('');
    const filterStatus = ref('all');
    const selectedTaskId = ref('');
    const showDeviceDialog = ref(false);
    const editingEquipmentId = ref(null);
    const deviceForm = reactive({
      code: '',
      name: '',
      equipmentType: '岸桥',
      status: '空闲',
      location: '',
      efficiency: 30,
      remark: '',
    });
    let clockTimer = null;
    let refreshTimer = null;

    function tick() {
      currentTime.value = new Date().toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      });
    }

    async function apiRequest(path, options = {}) {
      const resp = await fetch(path, {
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        ...options,
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.message || `接口请求失败：${resp.status}`);
      return data;
    }

    function normalizeEquipment(item) {
      return {
        id: item.id,
        code: item.code || '',
        name: item.name || '',
        equipmentType: item.equipmentType || item.equipment_type || '',
        status: item.status || '空闲',
        location: item.location || '',
        efficiency: Number(item.efficiency || 0),
        currentTaskId: item.currentTaskId || null,
        currentTaskName: item.currentTaskName || '',
        currentContainer: item.currentContainer || '',
        lastMaintenanceAt: item.lastMaintenanceAt || '',
        remark: item.remark || '',
      };
    }

    function normalizeTask(item) {
      return {
        id: item.id,
        taskName: item.taskName || item.task_type || '',
        containerId: item.containerId || '',
        origin: item.origin || item.from_pos || '',
        destination: item.destination || item.to_pos || '',
        status: item.status || 'pending',
        equipmentId: item.equipmentId || null,
      };
    }

    async function loadEquipment() {
      const data = await apiRequest('/equipment');
      equipment.value = Array.isArray(data) ? data.map(normalizeEquipment) : [];
    }

    async function loadTasks() {
      const data = await apiRequest('/tasks');
      tasks.value = Array.isArray(data) ? data.map(normalizeTask) : [];
      if (!selectedTaskId.value && assignableTasks.value.length) {
        selectedTaskId.value = String(assignableTasks.value[0].id);
      }
    }

    async function refreshAll() {
      try {
        await Promise.all([loadEquipment(), loadTasks()]);
      } catch (err) {
        alert(err.message);
      }
    }

    const statusCounts = computed(() => ({
      idle: equipment.value.filter(item => item.status === '空闲').length,
      working: equipment.value.filter(item => item.status === '工作中').length,
      fault: equipment.value.filter(item => item.status === '故障').length,
    }));

    const filteredEquipment = computed(() => {
      let list = equipment.value.slice();
      if (filterStatus.value !== 'all') list = list.filter(item => item.status === filterStatus.value);
      if (searchQuery.value.trim()) {
        const q = searchQuery.value.trim().toLowerCase();
        list = list.filter(item => [item.code, item.name, item.equipmentType, item.location].join(' ').toLowerCase().includes(q));
      }
      return list;
    });

    const assignableTasks = computed(() => tasks.value.filter(task => task.status !== 'completed'));

    const selectedTask = computed(() => assignableTasks.value.find(task => String(task.id) === String(selectedTaskId.value)));

    function requiredEquipmentType(task) {
      if (!task) return '';
      const text = [task.taskName, task.origin, task.destination].join(' ');
      if (text.includes('AGV') || text.includes('转运') || text.includes('运送')) return 'AGV';
      if (text.includes('场桥') || text.includes('入堆') || text.includes('堆场')) return '场桥';
      if (text.includes('岸桥') || text.includes('卸船') || text.includes('泊位')) return '岸桥';
      return '';
    }

    const selectedTaskRequiredType = computed(() => requiredEquipmentType(selectedTask.value));

    const idleEquipment = computed(() => {
      const requiredType = selectedTaskRequiredType.value;
      return equipment.value.filter(item => item.status === '空闲' && (!requiredType || item.equipmentType === requiredType));
    });

    const selectedTaskSummary = computed(() => {
      const task = selectedTask.value;
      if (!task) return '请选择任务';
      const container = task.containerId ? ` ${task.containerId}` : '';
      return `${task.taskName}${container}`;
    });

    function statusKey(status) {
      return status === '空闲' ? 'idle' : status === '工作中' ? 'working' : status === '故障' ? 'fault' : 'idle';
    }

    function openDeviceDialog(item = null) {
      if (item) {
        editingEquipmentId.value = item.id;
        Object.assign(deviceForm, {
          code: item.code,
          name: item.name,
          equipmentType: item.equipmentType,
          status: item.status,
          location: item.location,
          efficiency: item.efficiency,
          remark: item.remark,
        });
      } else {
        editingEquipmentId.value = null;
        Object.assign(deviceForm, {
          code: '',
          name: '',
          equipmentType: '岸桥',
          status: '空闲',
          location: '',
          efficiency: 30,
          remark: '',
        });
      }
      showDeviceDialog.value = true;
    }

    function closeDeviceDialog() {
      showDeviceDialog.value = false;
      editingEquipmentId.value = null;
    }

    async function saveEquipment() {
      const payload = { ...deviceForm };
      const url = editingEquipmentId.value ? `/equipment/${editingEquipmentId.value}` : '/equipment';
      const method = editingEquipmentId.value ? 'PUT' : 'POST';
      try {
        await apiRequest(url, {
          method,
          body: JSON.stringify(payload),
        });
        closeDeviceDialog();
        await loadEquipment();
      } catch (err) {
        alert(err.message);
      }
    }

    async function deleteEquipment(item) {
      if (!confirm(`确定删除设备「${item.name}」吗？`)) return;
      try {
        await apiRequest(`/equipment/${item.id}`, { method: 'DELETE' });
        await loadEquipment();
      } catch (err) {
        alert(err.message);
      }
    }

    async function assignTask(item) {
      if (!selectedTaskId.value) {
        alert('请先选择一个任务');
        return;
      }
      try {
        await apiRequest(`/equipment/${item.id}/assign_task`, {
          method: 'POST',
          body: JSON.stringify({ taskId: Number(selectedTaskId.value) }),
        });
        await refreshAll();
      } catch (err) {
        alert(err.message);
      }
    }

    async function releaseEquipment(item) {
      try {
        await apiRequest(`/equipment/${item.id}/release`, { method: 'POST', body: JSON.stringify({}) });
        await refreshAll();
      } catch (err) {
        alert(err.message);
      }
    }

    async function markFault(item) {
      const remark = prompt('请输入故障说明', item.remark || '设备故障，等待维修');
      if (remark === null) return;
      try {
        await apiRequest(`/equipment/${item.id}/fault`, {
          method: 'POST',
          body: JSON.stringify({ remark }),
        });
        await refreshAll();
      } catch (err) {
        alert(err.message);
      }
    }

    async function repairEquipment(item) {
      try {
        await apiRequest(`/equipment/${item.id}/repair`, { method: 'POST', body: JSON.stringify({}) });
        await refreshAll();
      } catch (err) {
        alert(err.message);
      }
    }

    onMounted(() => {
      tick();
      refreshAll();
      clockTimer = setInterval(tick, 1000);
      refreshTimer = setInterval(refreshAll, 5000);
    });

    onBeforeUnmount(() => {
      if (clockTimer) clearInterval(clockTimer);
      if (refreshTimer) clearInterval(refreshTimer);
    });

    return {
      currentTime,
      activeTab,
      equipment,
      tasks,
      searchQuery,
      filterStatus,
      selectedTaskId,
      selectedTaskSummary,
      selectedTaskRequiredType,
      showDeviceDialog,
      editingEquipmentId,
      deviceForm,
      statusCounts,
      filteredEquipment,
      idleEquipment,
      assignableTasks,
      statusKey,
      openDeviceDialog,
      closeDeviceDialog,
      saveEquipment,
      deleteEquipment,
      assignTask,
      releaseEquipment,
      markFault,
      repairEquipment,
    };
  },
}).mount('#app');

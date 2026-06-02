const { createApp, ref, reactive, computed, onMounted, onBeforeUnmount } = Vue;

const STATUS_IDLE = '\u7a7a\u95f2';
const STATUS_WORKING = '\u5de5\u4f5c\u4e2d';
const STATUS_FAULT = '\u6545\u969c';
const TYPE_QUAY = '\u5cb8\u6865';
const TYPE_YARD = '\u573a\u6865';
const TYPE_AGV = 'AGV';

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
      equipmentType: TYPE_QUAY,
      status: STATUS_IDLE,
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
        status: item.status || STATUS_IDLE,
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
      idle: equipment.value.filter(item => item.status === STATUS_IDLE).length,
      working: equipment.value.filter(item => item.status === STATUS_WORKING).length,
      fault: equipment.value.filter(item => item.status === STATUS_FAULT).length,
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
      if (text.includes('AGV') || text.includes('\u8f6c\u8fd0') || text.includes('\u8fd0\u9001')) return TYPE_AGV;
      if (text.includes('\u573a\u6865') || text.includes('\u5165\u5806') || text.includes('\u5806\u573a')) return TYPE_YARD;
      if (text.includes('\u5cb8\u6865') || text.includes('\u5378\u8239') || text.includes('\u6cca\u4f4d')) return TYPE_QUAY;
      return '';
    }

    const selectedTaskRequiredType = computed(() => requiredEquipmentType(selectedTask.value));

    const idleEquipment = computed(() => {
      const requiredType = selectedTaskRequiredType.value;
      return equipment.value.filter(item => item.status === STATUS_IDLE && (!requiredType || item.equipmentType === requiredType));
    });

    const idleAgvList = computed(() => equipment.value.filter(item => item.equipmentType === TYPE_AGV && item.status === STATUS_IDLE));

    const waitingAgvTasks = computed(() => tasks.value
      .filter(task => task.status !== 'completed' && !task.equipmentId && requiredEquipmentType(task) === TYPE_AGV)
      .sort((a, b) => Number(a.id) - Number(b.id)));

    const agvDispatchPreview = computed(() => {
      const count = Math.min(idleAgvList.value.length, waitingAgvTasks.value.length);
      return Array.from({ length: count }, (_, index) => ({
        agv: idleAgvList.value[index],
        task: waitingAgvTasks.value[index],
      }));
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
          equipmentType: TYPE_QUAY,
          status: STATUS_IDLE,
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

    async function dispatchAgvTasks() {
      try {
        const result = await apiRequest('/equipment/agv_dispatch', {
          method: 'POST',
          body: JSON.stringify({}),
        });
        await refreshAll();
        alert(result.message || '\u8c03\u5ea6\u5b8c\u6210');
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
      idleAgvList,
      waitingAgvTasks,
      agvDispatchPreview,
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
      dispatchAgvTasks,
      releaseEquipment,
      markFault,
      repairEquipment,
    };
  },
}).mount('#app');

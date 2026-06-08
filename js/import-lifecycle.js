const { createApp, ref, computed, onMounted } = Vue;

createApp({
  setup() {
    const API_BASE = window.location.protocol.startsWith('http') ? window.location.origin : 'http://127.0.0.1:5000';

    const apiRequest = async (path, options = {}) => {
      const resp = await fetch(`${API_BASE}${path}`, {
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        ...options,
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.message || `请求失败：${resp.status}`);
      return data;
    };

    const currentTime = ref('');
    const currentView = ref('release');
    const message = ref('');
    const stats = ref({});
    const pickupReadyContainers = ref([]);
    const appointments = ref([]);
    const gateTransactions = ref([]);
    const exceptions = ref([]);
    const lastGateResult = ref(null);
    const currentUser = ref(null);

    const appointmentForm = ref({
      containerNo: '',
      truckPlate: '',
      driverName: '',
      driverPhone: '',
      customer: '',
      timeWindowStart: '',
      timeWindowEnd: '',
      remark: '',
    });
    const gateForm = ref({ appointmentNo: '', containerNo: '', truckPlate: '' });
    const exceptionForm = ref({
      objectType: 'container',
      objectId: '',
      exceptionType: '',
      description: '',
    });

    const activeAppointments = computed(() => appointments.value.filter(item =>
      ['待确认', '已确认', '已进闸', '已提箱'].includes(item.status)
    ));
    const hasPermission = (permission) => {
      const permissions = currentUser.value?.permissions || [];
      return permissions.includes('*') || permissions.includes(permission);
    };
    const canOperateImport = computed(() => hasPermission('import:operate'));
    const canWriteAppointment = computed(() => hasPermission('appointment:write'));
    const canWriteException = computed(() => hasPermission('exception:write'));

    function showMessage(text) {
      message.value = text;
      window.setTimeout(() => {
        if (message.value === text) message.value = '';
      }, 3500);
    }

    function formatForInput(date) {
      return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
    }

    function resetAppointmentForm() {
      const start = new Date(Date.now() - 10 * 60 * 1000);
      const end = new Date(Date.now() + 2 * 60 * 60 * 1000);
      appointmentForm.value = {
        containerNo: '',
        truckPlate: '',
        driverName: '',
        driverPhone: '',
        customer: '',
        timeWindowStart: formatForInput(start),
        timeWindowEnd: formatForInput(end),
        remark: '',
      };
    }

    function formatSlot(item) {
      const yard = item.yard || '-';
      const area = item.zone || item.area || '-';
      const row = item.row || item.column || '-';
      const tier = item.tier || item.layer || '-';
      return `${yard}/${area}/列${row}/层${tier}`;
    }

    function shortTime(text) {
      return text ? text.replace(/^\d{4}-/, '') : '-';
    }

    function appointmentTag(status) {
      return {
        '已确认': 'tag-blue',
        '已进闸': 'tag-cyan',
        '已提箱': 'tag-orange',
        '已出闸': 'tag-green',
        '已取消': 'tag-gray',
      }[status] || 'tag-gray';
    }

    async function loadOverview() {
      const data = await apiRequest('/api/import/overview');
      stats.value = data.stats || {};
      appointments.value = data.appointments || [];
      gateTransactions.value = data.gateTransactions || [];
      exceptions.value = data.exceptions || [];
    }

    async function loadPickupReady() {
      pickupReadyContainers.value = await apiRequest('/api/import/containers/pickup-ready');
    }

    async function refreshAll() {
      try {
        await loadOverview();
        await loadPickupReady();
      } catch (err) {
        showMessage(err.message);
      }
    }

    async function releaseContainer(item) {
      if (!canOperateImport.value) return;
      try {
        const data = await apiRequest('/api/import/customs/release', {
          method: 'POST',
          body: JSON.stringify({
            containerId: item.id,
            customsStatus: '已放行',
            inspectionStatus: '已通过',
          }),
        });
        showMessage(data.message);
        await refreshAll();
      } catch (err) {
        showMessage(err.message);
      }
    }

    function selectForAppointment(item) {
      appointmentForm.value.containerNo = item.containerNo;
      currentView.value = 'release';
      showMessage(`已选择 ${item.containerNo}，请填写车牌和司机信息`);
    }

    async function createAppointment() {
      if (!canWriteAppointment.value) {
        showMessage('当前角色无权创建预约');
        return;
      }
      try {
        const data = await apiRequest('/api/import/appointments', {
          method: 'POST',
          body: JSON.stringify(appointmentForm.value),
        });
        showMessage(data.message);
        gateForm.value.appointmentNo = data.data.appointmentNo;
        gateForm.value.containerNo = data.data.containerNo;
        gateForm.value.truckPlate = data.data.truckPlate;
        resetAppointmentForm();
        currentView.value = canOperateImport.value ? 'gate' : 'records';
        await refreshAll();
      } catch (err) {
        showMessage(err.message);
        await refreshAll();
      }
    }

    async function cancelAppointment(item) {
      if (!canWriteAppointment.value) return;
      if (!confirm(`确定取消预约 ${item.appointmentNo} 吗？`)) return;
      try {
        const data = await apiRequest(`/api/import/appointments/${item.id}/cancel`, { method: 'PUT' });
        showMessage(data.message);
        await refreshAll();
      } catch (err) {
        showMessage(err.message);
      }
    }

    async function gateIn(item) {
      if (!canOperateImport.value) return;
      try {
        const data = await apiRequest('/api/import/gate/in', {
          method: 'POST',
          body: JSON.stringify({
            appointmentNo: item.appointmentNo,
            containerNo: item.containerNo,
            truckPlate: item.truckPlate,
          }),
        });
        lastGateResult.value = data.data;
        showMessage(`${data.message}，小票 ${data.ticketNo}`);
        await refreshAll();
      } catch (err) {
        showMessage(err.message);
        await refreshAll();
      }
    }

    async function completePickup(item) {
      if (!canOperateImport.value) return;
      try {
        const data = await apiRequest(`/api/import/appointments/${item.id}/pickup`, { method: 'POST' });
        showMessage(data.message);
        await refreshAll();
      } catch (err) {
        showMessage(err.message);
      }
    }

    async function gateOut(item) {
      if (!canOperateImport.value) return;
      try {
        const data = await apiRequest('/api/import/gate/out', {
          method: 'POST',
          body: JSON.stringify({
            appointmentNo: item.appointmentNo,
            containerNo: item.containerNo,
            truckPlate: item.truckPlate,
          }),
        });
        lastGateResult.value = data.data;
        showMessage(data.message);
        await refreshAll();
      } catch (err) {
        showMessage(err.message);
        await refreshAll();
      }
    }

    async function manualGateIn() {
      if (!canOperateImport.value) return;
      try {
        const data = await apiRequest('/api/import/gate/in', {
          method: 'POST',
          body: JSON.stringify(gateForm.value),
        });
        lastGateResult.value = data.data;
        showMessage(data.message);
        await refreshAll();
      } catch (err) {
        lastGateResult.value = { gateType: '进闸', checkResult: '拦截', blockReason: err.message };
        showMessage(err.message);
        await refreshAll();
      }
    }

    async function manualGateOut() {
      if (!canOperateImport.value) return;
      try {
        const data = await apiRequest('/api/import/gate/out', {
          method: 'POST',
          body: JSON.stringify(gateForm.value),
        });
        lastGateResult.value = data.data;
        showMessage(data.message);
        await refreshAll();
      } catch (err) {
        lastGateResult.value = { gateType: '出闸', checkResult: '拦截', blockReason: err.message };
        showMessage(err.message);
        await refreshAll();
      }
    }

    async function createException() {
      if (!canWriteException.value) {
        showMessage('当前角色无权登记异常');
        return;
      }
      try {
        const data = await apiRequest('/api/import/exceptions', {
          method: 'POST',
          body: JSON.stringify(exceptionForm.value),
        });
        showMessage(data.message);
        exceptionForm.value = { objectType: 'container', objectId: '', exceptionType: '', description: '' };
        await refreshAll();
      } catch (err) {
        showMessage(err.message);
      }
    }

    async function resolveException(item) {
      if (!canOperateImport.value) return;
      try {
        const data = await apiRequest(`/api/import/exceptions/${item.id}/resolve`, {
          method: 'PUT',
          body: JSON.stringify({ handler: '调度员', resolution: '异常已核验并关闭' }),
        });
        showMessage(data.message);
        await refreshAll();
      } catch (err) {
        showMessage(err.message);
      }
    }

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

    onMounted(() => {
      resetAppointmentForm();
      tick();
      window.setInterval(tick, 1000);
      currentUser.value = window.__CURRENT_USER__ || null;
      window.addEventListener('auth:user', (event) => {
        currentUser.value = event.detail || null;
      });
      refreshAll();
    });

    return {
      currentTime,
      currentView,
      message,
      stats,
      pickupReadyContainers,
      appointments,
      gateTransactions,
      exceptions,
      activeAppointments,
      appointmentForm,
      gateForm,
      exceptionForm,
      lastGateResult,
      canOperateImport,
      canWriteAppointment,
      canWriteException,
      formatSlot,
      shortTime,
      appointmentTag,
      refreshAll,
      releaseContainer,
      selectForAppointment,
      createAppointment,
      resetAppointmentForm,
      cancelAppointment,
      gateIn,
      completePickup,
      gateOut,
      manualGateIn,
      manualGateOut,
      createException,
      resolveException,
    };
  },
}).mount('#app');

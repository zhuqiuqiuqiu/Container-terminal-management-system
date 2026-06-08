const { createApp, ref, onMounted } = Vue;

createApp({
  setup() {
    const API_BASE = window.location.protocol.startsWith('http') ? window.location.origin : 'http://127.0.0.1:5000';
    const currentTime = ref('');
    const message = ref('');
    const summary = ref({});
    const bills = ref([]);
    const containers = ref([]);
    const billForm = ref({ containerId: '', chargeType: '堆存费', amount: '', customer: '' });

    async function apiRequest(path, options = {}) {
      const resp = await fetch(`${API_BASE}${path}`, {
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        ...options,
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.message || `请求失败：${resp.status}`);
      return data;
    }

    function showMessage(text) {
      message.value = text;
      window.setTimeout(() => {
        if (message.value === text) message.value = '';
      }, 3000);
    }

    async function refreshAll() {
      try {
        summary.value = await apiRequest('/api/finance/summary');
        bills.value = await apiRequest('/api/finance/bills');
        containers.value = await apiRequest('/containers');
      } catch (err) {
        showMessage(err.message);
      }
    }

    async function createBill() {
      try {
        const payload = {
          containerId: billForm.value.containerId || null,
          chargeType: billForm.value.chargeType,
          customer: billForm.value.customer,
        };
        if (billForm.value.amount !== '' && billForm.value.amount !== null) payload.amount = Number(billForm.value.amount);
        const data = await apiRequest('/api/finance/bills', { method: 'POST', body: JSON.stringify(payload) });
        showMessage(data.message);
        billForm.value = { containerId: '', chargeType: '堆存费', amount: '', customer: '' };
        await refreshAll();
      } catch (err) {
        showMessage(err.message);
      }
    }

    async function settleBill(bill) {
      try {
        const data = await apiRequest(`/api/finance/bills/${bill.id}/settle`, { method: 'PUT' });
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
      tick();
      window.setInterval(tick, 1000);
      refreshAll();
    });

    return { currentTime, message, summary, bills, containers, billForm, refreshAll, createBill, settleBill };
  },
}).mount('#app');

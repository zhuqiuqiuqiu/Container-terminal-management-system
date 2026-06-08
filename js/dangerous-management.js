const { createApp, ref, computed, onMounted } = Vue;

createApp({
  setup() {
    const API_BASE = window.location.protocol.startsWith('http') ? window.location.origin : 'http://127.0.0.1:5000';
    const currentTime = ref('');
    const message = ref('');
    const stats = ref({});
    const containers = ref([]);
    const violations = ref([]);
    const dangerousYards = ref([]);

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
      }, 3200);
    }

    async function refreshAll() {
      try {
        const data = await apiRequest('/api/dangerous/overview');
        stats.value = data.stats || {};
        containers.value = data.containers || [];
        violations.value = data.violations || [];
        dangerousYards.value = data.dangerousYards || [];
      } catch (err) {
        showMessage(err.message);
      }
    }

    async function reassign() {
      try {
        const data = await apiRequest('/api/dangerous/reassign', { method: 'POST' });
        showMessage(data.message);
        await refreshAll();
      } catch (err) {
        showMessage(err.message);
      }
    }

    const violationIds = computed(() => new Set(violations.value.map((item) => item.id)));
    function isViolation(item) {
      return violationIds.value.has(item.id);
    }

    function formatSlot(item) {
      const yard = item.yard || '-';
      const area = item.zone || item.area || '-';
      const row = item.row || item.column || '-';
      const tier = item.tier || item.layer || '-';
      return `${yard}/${area}/列${row}/层${tier}`;
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

    return {
      currentTime,
      message,
      stats,
      containers,
      violations,
      dangerousYards,
      refreshAll,
      reassign,
      isViolation,
      formatSlot,
    };
  },
}).mount('#app');

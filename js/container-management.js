const { createApp, ref, computed, onMounted, nextTick } = Vue;

createApp({
  setup() {
    const API_BASE = window.location.protocol.startsWith('http') ? window.location.origin : 'http://127.0.0.1:5000';
    const apiRequest = async (path, options = {}) => {
      const resp = await fetch(`${API_BASE}${path}`, {
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        ...options,
      });
      const data = await resp.json().catch(() => null);
      if (!resp.ok) throw new Error((data && data.message) || `接口请求失败：${resp.status}`);
      return data;
    };

    const currentTime = ref('');
    const currentPageNum = ref(1);
    const pageSize = 10;
    const searchQuery = ref('');
    const filterStatus = ref('');
    const filterType = ref('');
    const filterLoad = ref('');
    const filterDangerous = ref(false);
    const filterReefer = ref(false);
    const showModal = ref(false);
    const modalTitle = ref('');
    const isEditing = ref(false);
    const editingId = ref(null);
    const allStatuses = ['在船上', '已卸船', '堆场存储', '等待提箱', '转运中', '在堆', '待装船', '离港'];
    const yardList = ref(['堆场A', '堆场B', '堆场C']);
    const zoneList = ref(['A区', 'B区', 'C区', 'D区', 'Zone-1', 'Zone-2', 'Zone-3', 'Zone-4']);
    const containers = ref([]);
    const formData = ref({
      containerNo: '',
      containerType: '20GP',
      loadStatus: '重箱',
      status: '堆场存储',
      yard: '堆场A',
      zone: 'Zone-1',
      row: 1,
      tier: 1,
      isDangerous: false,
      isReefer: false,
    });

    const yardUsage = { '堆场A': '进口箱', '堆场B': '出口箱', '堆场C': '冷藏箱' };

    const normalizeContainer = (item) => ({
      id: item.id,
      containerNo: item.containerNo || item.container_no,
      containerType: item.containerType || item.container_type,
      loadStatus: item.loadStatus || (item.is_full ? '重箱' : '空箱'),
      status: item.status || '在船上',
      yard: item.yard || '堆场A',
      zone: item.zone || item.area || 'Zone-1',
      row: Number(item.row ?? item.column ?? 1),
      tier: Number(item.tier ?? item.layer ?? 1),
      isDangerous: Boolean(item.isDangerous ?? item.is_dangerous),
      isReefer: Boolean(item.isReefer ?? item.is_refrigerated),
      createdAt: item.createdAt || item.created_at || '',
    });

    const toContainerPayload = (item) => ({
      containerNo: item.containerNo,
      containerType: item.containerType,
      loadStatus: item.loadStatus,
      status: item.status,
      yard: item.yard,
      zone: item.zone,
      row: Number(item.row),
      tier: Number(item.tier),
      isDangerous: Boolean(item.isDangerous),
      isReefer: Boolean(item.isReefer),
    });

    const loadContainers = async () => {
      const data = await apiRequest('/containers');
      containers.value = data.map(normalizeContainer);
      containers.value.forEach(c => {
        if (c.zone && !zoneList.value.includes(c.zone)) zoneList.value.push(c.zone);
      });
      currentPageNum.value = 1;
    };

    const loadYards = async () => {
      const data = await apiRequest('/yards');
      const names = data.map(y => y.yardName || y.yard_name);
      yardList.value.splice(0, yardList.value.length, ...names);
      data.forEach(y => {
        yardUsage[y.yardName || y.yard_name] = y.usageType || y.usage_type || '综合堆场';
        (y.zones || []).forEach(z => {
          if (!zoneList.value.includes(z)) zoneList.value.push(z);
        });
      });
    };

    const refreshAll = async () => {
      try {
        await loadYards();
        await loadContainers();
      } catch (err) {
        alert(`后端数据加载失败：${err.message}`);
      }
    };

    const filteredContainers = computed(() => {
      let res = containers.value;
      if (searchQuery.value) res = res.filter(c => c.containerNo.toLowerCase().includes(searchQuery.value.toLowerCase()));
      if (filterStatus.value) res = res.filter(c => c.status === filterStatus.value);
      if (filterType.value) res = res.filter(c => c.containerType === filterType.value);
      if (filterLoad.value) res = res.filter(c => c.loadStatus === filterLoad.value);
      if (filterDangerous.value) res = res.filter(c => c.isDangerous);
      if (filterReefer.value) res = res.filter(c => c.isReefer);
      return res;
    });

    const totalPages = computed(() => Math.max(1, Math.ceil(filteredContainers.value.length / pageSize)));
    const paginatedContainers = computed(() => filteredContainers.value.slice((currentPageNum.value - 1) * pageSize, currentPageNum.value * pageSize));
    const getStatusTagClass = (s) => ({ '在船上': 'tag tag-blue', '已卸船': 'tag tag-cyan', '堆场存储': 'tag tag-green', '等待提箱': 'tag tag-orange', '转运中': 'tag tag-cyan', '在堆': 'tag tag-green', '待装船': 'tag tag-orange', '离港': 'tag tag-gray' }[s] || 'tag tag-gray');
    const resetFilters = () => {
      searchQuery.value = '';
      filterStatus.value = '';
      filterType.value = '';
      filterLoad.value = '';
      filterDangerous.value = false;
      filterReefer.value = false;
      currentPageNum.value = 1;
    };

    const openAddModal = () => {
      modalTitle.value = '新增集装箱';
      isEditing.value = false;
      editingId.value = null;
      formData.value = {
        containerNo: `MSCU${String(Date.now()).slice(-7)}`,
        containerType: '20GP',
        loadStatus: '重箱',
        status: '堆场存储',
        yard: yardList.value[0] || '堆场A',
        zone: zoneList.value[0] || 'A区',
        row: 1,
        tier: 1,
        isDangerous: false,
        isReefer: false,
      };
      showModal.value = true;
    };

    const openDetailModal = (c) => {
      modalTitle.value = `集装箱详情 - ${c.containerNo}`;
      isEditing.value = true;
      editingId.value = c.id;
      formData.value = { ...c };
      showModal.value = true;
    };

    const saveContainer = async () => {
      if (!formData.value.containerNo.trim()) {
        alert('请输入箱号');
        return;
      }
      try {
        const payload = toContainerPayload(formData.value);
        if (isEditing.value && editingId.value) {
          await apiRequest(`/containers/${editingId.value}`, { method: 'PUT', body: JSON.stringify(payload) });
        } else {
          await apiRequest('/containers', { method: 'POST', body: JSON.stringify(payload) });
        }
        await loadContainers();
        showModal.value = false;
      } catch (err) {
        alert(err.message);
      }
    };

    const deleteContainer = async () => {
      if (!confirm('确定删除？')) return;
      try {
        await apiRequest(`/containers/${editingId.value}`, { method: 'DELETE' });
        await loadContainers();
        showModal.value = false;
      } catch (err) {
        alert(err.message);
      }
    };

    const advanceStatus = async (c) => {
      try {
        await apiRequest(`/containers/${c.id}/next_status`, { method: 'PUT' });
        await loadContainers();
      } catch (err) {
        alert(err.message);
      }
    };

    const tick = () => {
      currentTime.value = new Date().toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      });
    };

    onMounted(() => {
      tick();
      setInterval(tick, 1000);
      refreshAll();
    });

    return {
      currentTime,
      currentPageNum,
      searchQuery,
      filterStatus,
      filterType,
      filterLoad,
      filterDangerous,
      filterReefer,
      showModal,
      modalTitle,
      isEditing,
      formData,
      allStatuses,
      yardList,
      zoneList,
      yardUsage,
      filteredContainers,
      paginatedContainers,
      totalPages,
      getStatusTagClass,
      resetFilters,
      openAddModal,
      openDetailModal,
      saveContainer,
      deleteContainer,
      advanceStatus,
    };
  },
}).mount('#app');

const { createApp, ref, reactive, computed, onMounted, onUnmounted, nextTick, watch } = Vue;

createApp({
  setup() {
    const currentView = ref('ships');
    const currentTime = ref('');
    const ships = ref([]);
    const loading = ref(false);
    const message = ref('');
    const autoBerthMessage = ref('');
    const berths = ref([
      { id: 1, name: '泊位1', occupied: false, currentShip: '', depth: 16.5, length: 400 },
      { id: 2, name: '泊位2', occupied: false, currentShip: '', depth: 16.5, length: 380 },
      { id: 3, name: '泊位3', occupied: false, currentShip: '', depth: 18.0, length: 420 },
      { id: 4, name: '泊位4', occupied: false, currentShip: '', depth: 15.0, length: 350 },
      { id: 5, name: '泊位5', occupied: false, currentShip: '', depth: 17.0, length: 400 },
      { id: 6, name: '泊位6', occupied: false, currentShip: '', depth: 14.5, length: 320 },
    ]);

    const loadingPlans = ref([]);
    const showShipDialog = ref(false);
    const showBerthingDialog = ref(false);
    const editingShipId = ref(null);
    const shipForm = reactive({ name: '', voyage: '', eta: '', etd: '', berth: '', status: '计划中' });
    const berthingForm = reactive({ shipId: '', berthName: '', startTime: '', endTime: '' });

    const inPortCount = computed(() => ships.value.filter(s => s.status === '已靠泊').length);
    const scheduledCount = computed(() => ships.value.filter(s => s.status === '计划中').length);
    const totalLoadPlanned = computed(() => loadingPlans.value.reduce((sum, item) => sum + item.loadQty, 0));
    const totalDischargePlanned = computed(() => loadingPlans.value.reduce((sum, item) => sum + item.dischargeQty, 0));
    const totalCompleted = computed(() => loadingPlans.value.reduce((sum, item) => sum + item.completedQty, 0));
    const totalPending = computed(() => Math.max(totalLoadPlanned.value + totalDischargePlanned.value - totalCompleted.value, 0));

    const berthingPlans = computed(() => ships.value
      .filter(ship => ship.berth)
      .map(ship => {
        const start = ship.eta || '';
        const end = ship.etd || '';
        return {
          id: ship.id,
          shipName: ship.name,
          berthName: ship.berth,
          startTime: start,
          endTime: end,
          duration: calcDuration(start, end),
          status: ship.status === '已靠泊' ? '进行中' : ship.status === '已离港' ? '已离泊' : '待靠泊',
        };
      }));

    const statusClass = (status) => ({
      '已靠泊': 'tag-green',
      '计划中': 'tag-orange',
      '已离港': 'tag-gray',
    }[status] || 'tag-gray');

    function calcDuration(start, end) {
      const startDate = new Date(start);
      const endDate = new Date(end);
      if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) return '-';
      return Math.max(1, Math.round((endDate - startDate) / 3600000)) + 'h';
    }

    function normalizeShip(raw) {
      return {
        id: raw.id,
        name: raw.name || '',
        voyage: raw.voyage || '',
        eta: raw.eta || raw.ETA || '',
        etd: raw.etd || raw.ETD || '',
        berth: raw.berth || '',
        status: raw.status || '计划中',
      };
    }

    function buildLoadingPlans() {
      loadingPlans.value = ships.value.map((ship, index) => {
        const base = 500 + index * 180;
        const isDone = ship.status === '已离港';
        const isRunning = ship.status === '已靠泊';
        const plannedTotal = base + 320;
        return {
          id: ship.id,
          shipName: ship.name,
          loadQty: base,
          dischargeQty: 320 + index * 90,
          completedQty: isDone ? plannedTotal : isRunning ? Math.round(plannedTotal * 0.45) : 0,
          progressPercent: isDone ? 100 : isRunning ? 45 : 0,
          craneAssigned: isRunning ? 'QC01, QC02' : isDone ? '已完成' : '待分配',
        };
      });
    }

    function updateClock() {
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

    function updateBerthOccupancy() {
      berths.value.forEach(b => {
        b.occupied = false;
        b.currentShip = '';
      });
      ships.value.forEach(ship => {
        if (ship.status !== '已靠泊' || !ship.berth) return;
        let berth = berths.value.find(item => item.name === ship.berth);
        if (!berth) {
          berth = { id: berths.value.length + 1, name: ship.berth, occupied: false, currentShip: '', depth: 15, length: 350 };
          berths.value.push(berth);
        }
        berth.occupied = true;
        berth.currentShip = ship.name;
      });
    }

    function formatDateTime(date) {
      return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
    }

    function getFreeBerths() {
      const occupied = new Set(
        ships.value
          .filter(ship => ship.status === '已靠泊' && ship.berth)
          .map(ship => ship.berth)
      );
      return berths.value.filter(berth => !occupied.has(berth.name));
    }

    async function updateShipRecord(ship, patch) {
      const resp = await fetch(`/ships/${ship.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ ...ship, ...patch }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.message || `${ship.name} 靠泊计划保存失败`);
      return data.data;
    }

    async function loadShips() {
      loading.value = true;
      message.value = '';
      try {
        const resp = await fetch('/ships', { credentials: 'same-origin' });
        if (!resp.ok) throw new Error('船舶数据加载失败');
        const data = await resp.json();
        ships.value = Array.isArray(data) ? data.map(normalizeShip) : [];
        updateBerthOccupancy();
        buildLoadingPlans();
        renderCharts();
      } catch (err) {
        message.value = err.message || '船舶数据加载失败';
      } finally {
        loading.value = false;
      }
    }

    function openShipDialog(ship = null) {
      if (ship) {
        editingShipId.value = ship.id;
        Object.assign(shipForm, ship);
      } else {
        editingShipId.value = null;
        Object.assign(shipForm, { name: '', voyage: '', eta: '', etd: '', berth: '', status: '计划中' });
      }
      showShipDialog.value = true;
    }

    async function saveShip() {
      if (!shipForm.name || !shipForm.voyage) {
        alert('请填写船名和航次');
        return;
      }
      const payload = { ...shipForm };
      const url = editingShipId.value ? `/ships/${editingShipId.value}` : '/ships';
      const method = editingShipId.value ? 'PUT' : 'POST';
      const resp = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify(payload),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        alert(data.message || '保存船舶失败');
        return;
      }
      showShipDialog.value = false;
      await loadShips();
    }

    async function deleteShip(id) {
      if (!confirm('确定删除该船舶信息吗？')) return;
      const resp = await fetch(`/ships/${id}`, {
        method: 'DELETE',
        credentials: 'same-origin',
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        alert(data.message || '删除船舶失败');
        return;
      }
      await loadShips();
    }

    function openBerthingDialog() {
      Object.assign(berthingForm, { shipId: '', berthName: '', startTime: '', endTime: '' });
      showBerthingDialog.value = true;
    }

    async function saveBerthingPlan() {
      const ship = ships.value.find(item => String(item.id) === String(berthingForm.shipId));
      if (!ship || !berthingForm.berthName || !berthingForm.startTime || !berthingForm.endTime) {
        alert('请完整填写靠泊计划');
        return;
      }
      const resp = await fetch(`/ships/${ship.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({
          ...ship,
          eta: berthingForm.startTime,
          etd: berthingForm.endTime,
          berth: berthingForm.berthName,
          status: '已靠泊',
        }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        alert(data.message || '保存靠泊计划失败');
        return;
      }
      showBerthingDialog.value = false;
      await loadShips();
    }

    async function autoGenerateBerthingPlans() {
      autoBerthMessage.value = '';
      const freeBerths = getFreeBerths();
      const waitingShips = ships.value
        .filter(ship => ship.status === '计划中')
        .sort((a, b) => {
          const at = new Date(a.eta || 0).getTime() || 0;
          const bt = new Date(b.eta || 0).getTime() || 0;
          return at - bt || a.id - b.id;
        });

      if (freeBerths.length === 0) {
        autoBerthMessage.value = '当前没有空闲泊位，暂不能自动生成靠泊计划。';
        return;
      }
      if (waitingShips.length === 0) {
        autoBerthMessage.value = '当前没有状态为“计划中”的待靠泊船舶。';
        return;
      }

      const count = Math.min(freeBerths.length, waitingShips.length);
      const now = new Date();
      const assignments = [];

      try {
        for (let i = 0; i < count; i += 1) {
          const ship = waitingShips[i];
          const berth = freeBerths[i];
          const start = ship.eta || formatDateTime(new Date(now.getTime() + i * 60 * 60 * 1000));
          const end = ship.etd || formatDateTime(new Date(new Date(start).getTime() + 48 * 60 * 60 * 1000));
          await updateShipRecord(ship, {
            berth: berth.name,
            eta: start,
            etd: end,
            status: '已靠泊',
          });
          assignments.push(`${ship.name} → ${berth.name}`);
        }
        await loadShips();
        autoBerthMessage.value = `已自动生成 ${assignments.length} 条靠泊计划：${assignments.join('，')}`;
      } catch (err) {
        autoBerthMessage.value = err.message || '自动生成靠泊计划失败';
      }
    }

    async function deleteBerthingPlan(id) {
      if (!confirm('确定取消该靠泊计划吗？')) return;
      const ship = ships.value.find(item => item.id === id);
      if (!ship) return;
      const resp = await fetch(`/ships/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ ...ship, berth: '', status: '计划中' }),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        alert(data.message || '取消靠泊计划失败');
        return;
      }
      await loadShips();
    }

    let chartPie = null;
    let chartBar = null;
    let timer = null;
    function renderCharts() {
      nextTick(() => {
        const pieDom = document.getElementById('loadPieChart');
        const barDom = document.getElementById('loadBarChart');
        if (pieDom && window.echarts) {
          chartPie?.dispose();
          chartPie = echarts.init(pieDom);
          chartPie.setOption({
            title: { text: '装卸箱量分布', left: 'center', textStyle: { color: '#1a365d', fontSize: 14 } },
            tooltip: { trigger: 'item' },
            legend: { bottom: 8 },
            series: [{
              type: 'pie',
              radius: ['45%', '72%'],
              data: [
                { value: totalLoadPlanned.value, name: '装船', itemStyle: { color: '#3b82f6' } },
                { value: totalDischargePlanned.value, name: '卸船', itemStyle: { color: '#06b6d4' } },
              ],
            }],
          });
        }
        if (barDom && window.echarts) {
          chartBar?.dispose();
          chartBar = echarts.init(barDom);
          chartBar.setOption({
            title: { text: '各船装卸对比', left: 'center', textStyle: { color: '#1a365d', fontSize: 14 } },
            tooltip: { trigger: 'axis' },
            legend: { data: ['装船', '卸船'], bottom: 0 },
            grid: { top: 45, left: 50, right: 20, bottom: 45 },
            xAxis: { type: 'category', data: loadingPlans.value.map(item => item.shipName) },
            yAxis: { type: 'value' },
            series: [
              { name: '装船', type: 'bar', data: loadingPlans.value.map(item => item.loadQty), itemStyle: { color: '#3b82f6' } },
              { name: '卸船', type: 'bar', data: loadingPlans.value.map(item => item.dischargeQty), itemStyle: { color: '#06b6d4' } },
            ],
          });
        }
      });
    }

    function tick() {
      updateClock();
      if (currentView.value === 'loading') renderCharts();
    }

    onMounted(() => {
      tick();
      loadShips();
      timer = setInterval(tick, 1000);
      window.addEventListener('resize', renderCharts);
    });

    onUnmounted(() => {
      if (timer) clearInterval(timer);
      window.removeEventListener('resize', renderCharts);
      chartPie?.dispose();
      chartBar?.dispose();
    });

    watch(currentView, (view) => {
      if (view === 'loading') renderCharts();
    });

    return {
      currentView,
      currentTime,
      ships,
      berths,
      berthingPlans,
      loadingPlans,
      showShipDialog,
      showBerthingDialog,
      editingShipId,
      shipForm,
      berthingForm,
      inPortCount,
      scheduledCount,
      totalLoadPlanned,
      totalDischargePlanned,
      totalCompleted,
      totalPending,
      loading,
      message,
      autoBerthMessage,
      statusClass,
      openShipDialog,
      saveShip,
      deleteShip,
      openBerthingDialog,
      saveBerthingPlan,
      deleteBerthingPlan,
      autoGenerateBerthingPlans,
    };
  },
}).mount('#app');

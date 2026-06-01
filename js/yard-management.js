const { createApp, ref, onMounted, nextTick } = Vue;

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
    const yards = ref([]);
    const ships = ref([]);
    const selectedShipId = ref('');
    const shipAllocationResult = ref(null);
    const yardList = ref(['堆场A', '堆场B', '堆场C']);
    const zoneList = ref(['A区', 'B区', 'C区', 'D区', 'Zone-1', 'Zone-2', 'Zone-3', 'Zone-4']);
    const selectedYard = ref('堆场A');
    const selectedZone = ref('A区');
    const showAllocModal = ref(false);
    const showYardModal = ref(false);
    const editingYardId = ref(null);
    const selectedContainerOnMap = ref(null);
    const allocationResults = ref([]);
    const allocationSearched = ref(false);
    const allocForm = ref({
      containerType: '20GP',
      loadStatus: '重箱',
      targetType: 'auto',
      isDangerous: false,
      isReefer: false,
      preferZone: '',
    });
    const containers = ref([]);
    const yardForm = ref({
      yardName: '',
      usageType: '',
      totalCapacity: 240,
      code: '',
      address: '',
      manager: '',
      contactPhone: '',
      status: 'active',
    });

    const normalizeContainer = (item) => ({
      id: item.id,
      containerNo: item.containerNo || item.container_no,
      containerType: item.containerType || item.container_type,
      loadStatus: item.loadStatus || (item.is_full ? '重箱' : '空箱'),
      status: item.status || '在船上',
      yard: item.yard || '',
      zone: item.zone || item.area || 'Zone-1',
      row: Number(item.row ?? item.column ?? 1),
      tier: Number(item.tier ?? item.layer ?? 1),
      isDangerous: Boolean(item.isDangerous ?? item.is_dangerous),
      isReefer: Boolean(item.isReefer ?? item.is_refrigerated),
      createdAt: item.createdAt || item.created_at || '',
    });

    const loadContainers = async () => {
      const data = await apiRequest('/containers');
      containers.value = data.map(normalizeContainer);
      containers.value.forEach(c => {
        if (c.zone && !zoneList.value.includes(c.zone)) zoneList.value.push(c.zone);
      });
    };

    const loadYards = async () => {
      const data = await apiRequest('/yards');
      yards.value = data;
      const names = data.map(y => y.yardName || y.yard_name);
      yardList.value.splice(0, yardList.value.length, ...names);
      data.forEach(y => {
        (y.zones || []).forEach(z => {
          if (!zoneList.value.includes(z)) zoneList.value.push(z);
        });
      });
      if (!yardList.value.includes(selectedYard.value) && yardList.value.length) selectedYard.value = yardList.value[0];
    };

    const loadShips = async () => {
      const data = await apiRequest('/ships');
      ships.value = Array.isArray(data) ? data : [];
      if (!selectedShipId.value && ships.value.length) selectedShipId.value = String(ships.value[0].id);
    };

    const refreshAll = async () => {
      try {
        await loadYards();
        await loadShips();
        await loadContainers();
        redrawYardMap();
      } catch (err) {
        alert(`后端数据加载失败：${err.message}`);
      }
    };

    const openYardDialog = (yard = null) => {
      if (yard) {
        editingYardId.value = yard.id;
        yardForm.value = {
          yardName: yard.yardName || yard.yard_name,
          usageType: yard.usageType || yard.usage_type || '',
          totalCapacity: yard.totalCapacity || yard.total_capacity || 240,
          code: yard.code || '',
          address: yard.address || '',
          manager: yard.manager || '',
          contactPhone: yard.contactPhone || yard.contact_phone || '',
          status: yard.status || 'active',
        };
      } else {
        editingYardId.value = null;
        yardForm.value = {
          yardName: '',
          usageType: '',
          totalCapacity: 240,
          code: '',
          address: '',
          manager: '',
          contactPhone: '',
          status: 'active',
        };
      }
      showYardModal.value = true;
    };

    const saveYard = async () => {
      const payload = {
        yardName: yardForm.value.yardName,
        usageType: yardForm.value.usageType,
        totalCapacity: Number(yardForm.value.totalCapacity),
        capacity: Number(yardForm.value.totalCapacity),
        code: yardForm.value.code,
        address: yardForm.value.address,
        manager: yardForm.value.manager,
        contactPhone: yardForm.value.contactPhone,
        status: yardForm.value.status,
      };
      try {
        if (editingYardId.value) {
          await apiRequest(`/yards/${editingYardId.value}`, {
            method: 'PUT',
            body: JSON.stringify(payload),
          });
        } else {
          await apiRequest('/yards', {
            method: 'POST',
            body: JSON.stringify(payload),
          });
        }
        showYardModal.value = false;
        await refreshAll();
      } catch (err) {
        alert(err.message);
      }
    };

    const deleteYard = async (yard) => {
      if (!confirm(`确定删除堆场「${yard.yardName || yard.yard_name}」吗？`)) return;
      try {
        await apiRequest(`/yards/${yard.id}`, { method: 'DELETE' });
        await refreshAll();
      } catch (err) {
        alert(err.message);
      }
    };

    const selectedYardInfo = () => yards.value.find(y => (y.yardName || y.yard_name) === selectedYard.value) || {};
    const getYardContainers = () => containers.value.filter(c => c.yard === selectedYard.value && c.zone === selectedZone.value);
    const getCellColor = (c) => {
      if (!c) return '#3a3f4a';
      if (c.isDangerous && c.isReefer) return '#f5a623';
      if (c.isDangerous) return '#e85d75';
      if (c.isReefer) return '#3dd6c8';
      if (c.loadStatus === '空箱') return '#a0c4e8';
      return '#5b9bd5';
    };

    const redrawYardMap = () => {
      nextTick(() => {
        const canvas = document.getElementById('yardCanvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const dpr = window.devicePixelRatio || 1;
        const maxRows = 12;
        const maxTiers = 5;
        const cellW = 64;
        const cellH = 52;
        const marginLeft = 70;
        const marginTop = 40;
        const marginRight = 20;
        const marginBottom = 50;
        const gapX = 6;
        const gapY = 6;
        const totalW = marginLeft + maxRows * (cellW + gapX) - gapX + marginRight;
        const totalH = marginTop + maxTiers * (cellH + gapY) - gapY + marginBottom;

        canvas.width = totalW * dpr;
        canvas.height = totalH * dpr;
        canvas.style.width = `${totalW}px`;
        canvas.style.height = `${totalH}px`;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.fillStyle = '#0d2b45';
        ctx.fillRect(0, 0, totalW, totalH);
        ctx.strokeStyle = '#2a4a6e';
        ctx.lineWidth = 0.5;

        for (let r = 0; r <= maxRows; r++) {
          const x = marginLeft + r * (cellW + gapX) - gapX / 2;
          ctx.beginPath();
          ctx.moveTo(x, marginTop);
          ctx.lineTo(x, marginTop + maxTiers * (cellH + gapY) - gapY);
          ctx.stroke();
        }
        for (let t = 0; t <= maxTiers; t++) {
          const y = marginTop + t * (cellH + gapY) - gapY / 2;
          ctx.beginPath();
          ctx.moveTo(marginLeft, y);
          ctx.lineTo(marginLeft + maxRows * (cellW + gapX) - gapX, y);
          ctx.stroke();
        }

        ctx.fillStyle = '#8aaac0';
        ctx.font = '12px "PingFang SC"';
        ctx.textAlign = 'center';
        for (let r = 1; r <= maxRows; r++) {
          ctx.fillText(`列${r}`, marginLeft + (r - 1) * (cellW + gapX) + cellW / 2, marginTop - 10);
        }
        ctx.textAlign = 'right';
        for (let t = 1; t <= maxTiers; t++) {
          ctx.fillText(`层${t}`, marginLeft - 10, marginTop + (maxTiers - t) * (cellH + gapY) + cellH / 2 + 4);
        }

        const posMap = {};
        getYardContainers().forEach(c => { posMap[`${c.row}-${c.tier}`] = c; });
        canvas._cellData = [];
        for (let r = 1; r <= maxRows; r++) {
          for (let t = 1; t <= maxTiers; t++) {
            const key = `${r}-${t}`;
            const container = posMap[key] || null;
            const cx = marginLeft + (r - 1) * (cellW + gapX);
            const cy = marginTop + (maxTiers - t) * (cellH + gapY);
            ctx.fillStyle = getCellColor(container);
            const radius = 5;
            ctx.beginPath();
            ctx.moveTo(cx + radius, cy);
            ctx.lineTo(cx + cellW - radius, cy);
            ctx.quadraticCurveTo(cx + cellW, cy, cx + cellW, cy + radius);
            ctx.lineTo(cx + cellW, cy + cellH - radius);
            ctx.quadraticCurveTo(cx + cellW, cy + cellH, cx + cellW - radius, cy + cellH);
            ctx.lineTo(cx + radius, cy + cellH);
            ctx.quadraticCurveTo(cx, cy + cellH, cx, cy + cellH - radius);
            ctx.lineTo(cx, cy + radius);
            ctx.quadraticCurveTo(cx, cy, cx + radius, cy);
            ctx.closePath();
            ctx.fill();
            if (container) {
              ctx.strokeStyle = 'rgba(255,255,255,0.4)';
              ctx.lineWidth = 1.5;
              ctx.stroke();
              ctx.fillStyle = '#fff';
              ctx.font = 'bold 10px "PingFang SC"';
              ctx.textAlign = 'center';
              ctx.fillText(container.containerType, cx + cellW / 2, cy + cellH / 2 - 2);
            }
            canvas._cellData.push({ r, t, cx, cy, cellW, cellH, container, key });
          }
        }

        ctx.fillStyle = '#fff';
        ctx.font = 'bold 14px "PingFang SC"';
        ctx.textAlign = 'left';
        ctx.fillText(`${selectedYard.value} · ${selectedZone.value} 剖面图`, 16, 22);
      });
    };

    const handleCanvasClick = (e) => {
      const canvas = document.getElementById('yardCanvas');
      if (!canvas || !canvas._cellData) return;
      const rect = canvas.getBoundingClientRect();
      const scaleX = canvas.width / (parseFloat(canvas.style.width) || canvas.width);
      const scaleY = canvas.height / (parseFloat(canvas.style.height) || canvas.height);
      const mx = (e.clientX - rect.left) * scaleX;
      const my = (e.clientY - rect.top) * scaleY;
      for (const cell of canvas._cellData) {
        if (mx >= cell.cx && mx <= cell.cx + cell.cellW && my >= cell.cy && my <= cell.cy + cell.cellH) {
          selectedContainerOnMap.value = cell.container || null;
          if (!cell.container) alert(`空位：${selectedYard.value}/${selectedZone.value}/列${cell.r}/层${cell.t}`);
          return;
        }
      }
      selectedContainerOnMap.value = null;
    };

    const findEmptySlots = (yard, zone) => {
      const occupied = new Set(containers.value.filter(c => c.yard === yard && c.zone === zone).map(c => `${c.row}-${c.tier}`));
      const slots = [];
      for (let r = 1; r <= 12; r++) {
        for (let t = 1; t <= 5; t++) {
          if (!occupied.has(`${r}-${t}`)) slots.push({ yard, zone, row: r, tier: t });
        }
      }
      return slots;
    };

    const getAllEmptySlots = () => {
      const all = [];
      for (const yard of yardList.value) {
        for (const zone of zoneList.value) {
          all.push(...findEmptySlots(yard, zone));
        }
      }
      return all;
    };

    const openAllocationModal = () => {
      allocForm.value = {
        containerType: '20GP',
        loadStatus: '重箱',
        targetType: 'auto',
        isDangerous: false,
        isReefer: false,
        preferZone: '',
      };
      allocationResults.value = [];
      allocationSearched.value = false;
      showAllocModal.value = true;
    };

    const pickPreferredYard = (form) => {
      const byText = (patterns) => {
        const yard = yards.value.find(item => {
          const text = `${item.yardName || item.yard_name || ''}${item.usageType || item.usage_type || ''}`;
          return patterns.some(pattern => text.includes(pattern));
        });
        return yard ? (yard.yardName || yard.yard_name) : null;
      };
      if (form.isDangerous) return byText(['危险']);
      if (form.isReefer || form.targetType === '冷藏箱') return byText(['冷藏', '冷']);
      if (form.targetType === '进口箱' || form.loadStatus === '重箱') return byText(['重', '进口']);
      if (form.targetType === '出口箱' || form.loadStatus === '空箱') return byText(['空', '出口']);
      return yardList.value[0] || null;
    };

    const runSmartAllocation = () => {
      const { containerType, loadStatus, targetType, isDangerous, isReefer, preferZone } = allocForm.value;
      const candidates = getAllEmptySlots();
      const preferredYard = pickPreferredYard(allocForm.value);

      const scored = candidates
        .map(s => {
          let score = 0;
          if (s.yard === preferredYard) score += 30;
          score += containers.value.filter(c => c.yard === s.yard && c.zone === s.zone && c.containerType === containerType).length * 5;
          score += (5 - s.tier) * 4;
          if (preferZone && s.zone === preferZone) score += 10;
          if (isDangerous) {
            const colHasDanger = containers.value.some(c => c.yard === s.yard && c.zone === s.zone && c.row === s.row && c.isDangerous);
            score += colHasDanger ? -5 : 8;
          }
          if (isReefer && s.yard === '堆场C') score += 20;
          return { ...s, score };
        })
        .sort((a, b) => b.score - a.score);

      allocationResults.value = scored.slice(0, 5).map(s => {
        const reasons = [];
        if (s.yard === preferredYard) reasons.push('匹配目标用途');
        if (s.tier <= 2) reasons.push('低层减少翻箱');
        if (s.zone === preferZone) reasons.push('靠近偏好区域');
        if (isReefer && s.yard === '堆场C') reasons.push('冷藏专用堆场');
        return { ...s, reason: reasons.join('，') || '综合得分较高' };
      });
      allocationSearched.value = true;
    };

    const runShipSmartAllocation = async () => {
      if (!selectedShipId.value) {
        alert('请选择需要分配的船舶');
        return;
      }
      try {
        const data = await apiRequest('/yards/smart_assign_ship', {
          method: 'POST',
          body: JSON.stringify({ shipId: Number(selectedShipId.value) }),
        });
        shipAllocationResult.value = data;
        await refreshAll();
        alert(`${data.message}：成功分配 ${data.assignedCount} 个，跳过 ${data.skippedCount} 个`);
      } catch (err) {
        alert(err.message);
      }
    };

    const applyAllocation = async (rec) => {
      const newContainer = {
        containerNo: `SMART${String(Date.now()).slice(-7)}`,
        containerType: allocForm.value.containerType,
        loadStatus: allocForm.value.loadStatus,
        status: '堆场存储',
        yard: rec.yard,
        zone: rec.zone,
        row: rec.row,
        tier: rec.tier,
        isDangerous: allocForm.value.isDangerous,
        isReefer: allocForm.value.isReefer,
      };
      try {
        await apiRequest('/containers', {
          method: 'POST',
          body: JSON.stringify(newContainer),
        });
        await loadContainers();
        showAllocModal.value = false;
        alert(`集装箱 ${newContainer.containerNo} 已分配至 ${rec.yard}/${rec.zone}/列${rec.row}/层${rec.tier}`);
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
      yards,
      ships,
      selectedShipId,
      shipAllocationResult,
      yardList,
      zoneList,
      selectedYard,
      selectedZone,
      showAllocModal,
      showYardModal,
      editingYardId,
      yardForm,
      selectedContainerOnMap,
      allocationResults,
      allocationSearched,
      allocForm,
      openYardDialog,
      saveYard,
      deleteYard,
      redrawYardMap,
      handleCanvasClick,
      openAllocationModal,
      runSmartAllocation,
      runShipSmartAllocation,
      applyAllocation,
    };
  },
}).mount('#app');

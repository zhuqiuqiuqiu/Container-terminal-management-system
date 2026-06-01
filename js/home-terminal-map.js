(function () {
  const canvas = document.getElementById('homeTerminalMap');
  const tooltip = document.getElementById('homeTerminalMapTooltip');
  if (!canvas || !tooltip) return;

  const state = {
    yards: [],
    containers: [],
    ships: [],
    boxes: [],
    message: '正在加载数据库堆场数据...',
    error: '',
  };

  function roundRectPath(ctx, x, y, w, h, r) {
    const radius = Math.min(r, w / 2, h / 2);
    ctx.beginPath();
    ctx.moveTo(x + radius, y);
    ctx.lineTo(x + w - radius, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + radius);
    ctx.lineTo(x + w, y + h - radius);
    ctx.quadraticCurveTo(x + w, y + h, x + w - radius, y + h);
    ctx.lineTo(x + radius, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - radius);
    ctx.lineTo(x, y + radius);
    ctx.quadraticCurveTo(x, y, x + radius, y);
    ctx.closePath();
  }

  function normalizeYard(raw) {
    const name = raw.yardName || raw.yard_name || raw.name || raw.yard || '未命名堆场';
    const total = Number(raw.totalCapacity || raw.total_capacity || raw.capacity || 0);
    const used = Number(raw.usedCapacity || raw.used_capacity || raw.used || 0);
    return {
      id: raw.id || name,
      name,
      type: raw.usageType || raw.usage_type || raw.type || '综合堆场',
      totalCapacity: total > 0 ? total : 240,
      usedCapacity: used > 0 ? used : 0,
      status: raw.status || 'active',
    };
  }

  function normalizeContainer(raw) {
    return {
      id: raw.id,
      no: raw.containerNo || raw.container_no || raw.container_no || '',
      type: raw.containerType || raw.container_type || '',
      status: raw.status || '',
      yard: raw.yard || raw.yardName || raw.yard_name || '',
      area: raw.zone || raw.area || '',
      col: Number(raw.row || raw.column || raw.col || 0),
      layer: Number(raw.tier || raw.layer || 0),
      loadStatus: raw.loadStatus || raw.load_flag || '',
      dangerous: Boolean(raw.isDangerous || raw.is_dangerous || raw.dangerous_goods),
      refrigerated: Boolean(raw.isReefer || raw.is_refrigerated || raw.refrigerated),
    };
  }

  function normalizeShip(raw) {
    return {
      id: raw.id,
      name: raw.name || '未命名船舶',
      voyage: raw.voyage || '',
      berth: raw.berth || '',
      status: raw.status || '计划中',
    };
  }

  function mergeYards(yards, containers) {
    return yards;
  }

  function containersInYard(yardName) {
    return state.containers.filter((container) => {
      return container.yard === yardName && container.status !== '离港';
    });
  }

  function getUsageRate(yard, actualCount) {
    const used = Math.max(Number(yard.usedCapacity) || 0, actualCount);
    if (!yard.totalCapacity) return 0;
    return Math.min(100, Math.round((used / yard.totalCapacity) * 100));
  }

  function statusColor(container) {
    if (!container) return { fill: '#f8fafc', border: '#cbd5e1', text: '#64748b', dash: true };
    if (container.dangerous) return { fill: '#ffe4e6', border: '#e11d48', text: '#9f1239' };
    if (container.refrigerated) return { fill: '#cffafe', border: '#0891b2', text: '#155e75' };
    if (container.status === '离港') return { fill: '#e2e8f0', border: '#94a3b8', text: '#64748b' };
    if (container.status === '等待提箱') return { fill: '#fef3c7', border: '#d97706', text: '#92400e' };
    if (container.status === '堆场存储' || container.status === '在堆') return { fill: '#dbeafe', border: '#2563eb', text: '#1e40af' };
    return { fill: '#dcfce7', border: '#16a34a', text: '#166534' };
  }

  function getCanvasSize() {
    const parent = canvas.parentElement;
    if (!parent) return { width: 0, height: 0 };
    const width = Math.floor(parent.getBoundingClientRect().width);
    const rows = Math.max(1, Math.ceil(Math.max(state.yards.length, 1) / 2));
    const height = Math.max(360, 172 + rows * 156);
    return { width, height };
  }

  function drawMessage(ctx, width, height, message, isError) {
    ctx.fillStyle = '#f8fcff';
    ctx.fillRect(0, 0, width, height);
    ctx.textAlign = 'center';
    ctx.fillStyle = isError ? '#b91c1c' : '#4a6d8c';
    ctx.font = '600 15px Segoe UI, Microsoft YaHei, sans-serif';
    ctx.fillText(message, width / 2, height / 2);
  }

  function draw() {
    const { width, height } = getCanvasSize();
    if (width <= 0) {
      requestAnimationFrame(draw);
      return;
    }

    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = width + 'px';
    canvas.style.height = height + 'px';

    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    state.boxes = [];

    if (state.error) {
      drawMessage(ctx, width, height, state.error, true);
      return;
    }
    if (state.message && state.yards.length === 0) {
      drawMessage(ctx, width, height, state.message, false);
      return;
    }

    const bg = ctx.createLinearGradient(0, 0, 0, height);
    bg.addColorStop(0, '#e8f4ff');
    bg.addColorStop(0.45, '#f8fcff');
    bg.addColorStop(1, '#edf3f8');
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, width, height);

    const pad = width < 560 ? 12 : 18;
    const mapW = width - pad * 2;
    const seaH = width < 560 ? 78 : 92;
    const dockH = 34;
    const yardTop = pad + seaH + dockH + 18;

    const seaGrad = ctx.createLinearGradient(0, pad, 0, pad + seaH);
    seaGrad.addColorStop(0, '#8fd0ff');
    seaGrad.addColorStop(1, '#3b82f6');
    ctx.fillStyle = seaGrad;
    roundRectPath(ctx, pad, pad, mapW, seaH, 14);
    ctx.fill();

    ctx.fillStyle = 'rgba(255,255,255,0.78)';
    ctx.font = '600 13px Segoe UI, Microsoft YaHei, sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText('码头泊位与堆场数据库视图', pad + 16, pad + 25);

    const visibleShips = state.ships.filter((ship) => ship.berth && ship.status !== '已离港').slice(0, 3);
    const shipCount = Math.max(visibleShips.length, 1);
    const shipW = Math.min(168, Math.max(112, (mapW - 36 - (shipCount - 1) * 16) / shipCount));
    const ships = visibleShips.length ? visibleShips : [{ name: '暂无靠泊船舶', berth: '空闲泊位', status: '计划中' }];
    ships.forEach((ship, index) => {
      const shipX = pad + 18 + index * (shipW + 16);
      const shipY = pad + 44 + (index % 2) * 6;
      const color = ship.status === '已靠泊' ? '#1d4ed8' : '#0f766e';
      ctx.fillStyle = ship.color;
      ctx.fillStyle = color;
      roundRectPath(ctx, shipX, shipY, shipW, 28, 12);
      ctx.fill();
      ctx.fillStyle = '#fff';
      ctx.font = '700 12px Segoe UI, Microsoft YaHei, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(ship.name.length > 10 ? ship.name.slice(0, 10) + '...' : ship.name, shipX + shipW / 2, shipY + 18);
      ctx.fillStyle = 'rgba(255,255,255,0.9)';
      ctx.font = '11px Segoe UI, Microsoft YaHei, sans-serif';
      ctx.fillText(ship.berth || '-', shipX + shipW / 2, shipY + 43);
    });

    ctx.fillStyle = '#cbd5e1';
    roundRectPath(ctx, pad, pad + seaH + 6, mapW, dockH, 10);
    ctx.fill();
    ctx.fillStyle = '#64748b';
    ctx.font = '700 12px Segoe UI, Microsoft YaHei, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('码头作业带', width / 2, pad + seaH + 28);

    const columns = width < 760 ? 1 : 2;
    const gap = 12;
    const yardW = (mapW - gap * (columns - 1)) / columns;
    const yardH = 144;

    state.yards.forEach((yard, index) => {
      const col = index % columns;
      const row = Math.floor(index / columns);
      const x = pad + col * (yardW + gap);
      const y = yardTop + row * (yardH + gap);
      const yardContainers = containersInYard(yard.name);
      const usage = getUsageRate(yard, yardContainers.length);
      const border = usage >= 80 ? '#e11d48' : usage >= 60 ? '#d97706' : '#2563eb';

      ctx.fillStyle = '#ffffff';
      roundRectPath(ctx, x, y, yardW, yardH, 12);
      ctx.fill();
      ctx.strokeStyle = border;
      ctx.lineWidth = 2;
      ctx.stroke();

      ctx.textAlign = 'left';
      ctx.fillStyle = '#0f172a';
      ctx.font = '700 15px Segoe UI, Microsoft YaHei, sans-serif';
      ctx.fillText(yard.name, x + 14, y + 24);
      ctx.font = '12px Segoe UI, Microsoft YaHei, sans-serif';
      ctx.fillStyle = '#475569';
      ctx.fillText(yard.type + ' · 占用率 ' + usage + '%', x + 14, y + 44);

      const barW = Math.max(40, yardW - 28);
      ctx.fillStyle = '#e2e8f0';
      roundRectPath(ctx, x + 14, y + 54, barW, 8, 99);
      ctx.fill();
      ctx.fillStyle = border;
      roundRectPath(ctx, x + 14, y + 54, Math.max(8, barW * usage / 100), 8, 99);
      ctx.fill();

      const slots = 12;
      const slotCols = 6;
      const slotGap = 5;
      const slotW = (yardW - 28 - slotGap * (slotCols - 1)) / slotCols;
      const slotH = 25;
      const slotY = y + 76;
      for (let i = 0; i < slots; i += 1) {
        const slotX = x + 14 + (i % slotCols) * (slotW + slotGap);
        const rowY = slotY + Math.floor(i / slotCols) * (slotH + 7);
        const container = yardContainers[i] || null;
        const color = statusColor(container);

        ctx.fillStyle = color.fill;
        roundRectPath(ctx, slotX, rowY, slotW, slotH, 5);
        ctx.fill();
        ctx.strokeStyle = color.border;
        ctx.lineWidth = 1.4;
        if (color.dash) ctx.setLineDash([4, 3]);
        ctx.stroke();
        ctx.setLineDash([]);

        ctx.fillStyle = color.text;
        ctx.font = '700 10px Consolas, monospace';
        ctx.textAlign = 'center';
        ctx.fillText(container ? container.no.slice(0, 6) : '空位', slotX + slotW / 2, rowY + 16);

        state.boxes.push({
          x: slotX,
          y: rowY,
          w: slotW,
          h: slotH,
          title: container ? container.no : '空箱位',
          text: container
            ? `${yard.name} / ${container.area || '-'} / 列${container.col || '-'} / 层${container.layer || '-'}`
            : `${yard.name} 当前示意空位`,
          extra: container ? `${container.type || '-'} · ${container.status || '-'}` : '数据库中暂无集装箱占用',
        });
      }

      ctx.textAlign = 'right';
      ctx.fillStyle = '#64748b';
      ctx.font = '11px Segoe UI, Microsoft YaHei, sans-serif';
      ctx.fillText(`实际箱量 ${yardContainers.length} · 容量 ${yard.totalCapacity}`, x + yardW - 14, y + yardH - 10);
    });
  }

  async function loadDatabaseData() {
    state.message = '正在加载数据库堆场数据...';
    state.error = '';
    draw();
    try {
      const [yardResp, containerResp, shipResp] = await Promise.all([
        fetch('/yards', { credentials: 'same-origin' }),
        fetch('/containers', { credentials: 'same-origin' }),
        fetch('/ships', { credentials: 'same-origin' }),
      ]);
      if (!yardResp.ok || !containerResp.ok || !shipResp.ok) {
        throw new Error('接口请求失败，请确认已登录并通过 Flask 服务访问首页');
      }
      const yardData = await yardResp.json();
      const containerData = await containerResp.json();
      const shipData = await shipResp.json();
      const yards = Array.isArray(yardData) ? yardData.map(normalizeYard) : [];
      const containers = Array.isArray(containerData) ? containerData.map(normalizeContainer) : [];
      const ships = Array.isArray(shipData) ? shipData.map(normalizeShip) : [];
      state.containers = containers;
      state.ships = ships;
      state.yards = mergeYards(yards, containers);
      state.message = '';
      if (state.yards.length === 0) {
        state.message = '数据库中暂无堆场数据';
      }
      draw();
    } catch (err) {
      state.error = err.message || '数据库堆场数据加载失败';
      state.yards = [];
      state.containers = [];
      state.ships = [];
      draw();
    }
  }

  function showTip(item, x, y) {
    tooltip.hidden = false;
    tooltip.textContent = item.title + ' · ' + item.text + ' · ' + item.extra;
    const maxLeft = Math.max(8, canvas.clientWidth - tooltip.offsetWidth - 12);
    tooltip.style.left = Math.min(x + 14, maxLeft) + 'px';
    tooltip.style.top = Math.max(10, y - 38) + 'px';
  }

  function hideTip() {
    tooltip.hidden = true;
  }

  function getPos(evt) {
    const rect = canvas.getBoundingClientRect();
    return {
      x: evt.clientX - rect.left,
      y: evt.clientY - rect.top,
    };
  }

  function hitTest(x, y) {
    return state.boxes.find((box) => x >= box.x && x <= box.x + box.w && y >= box.y && y <= box.y + box.h);
  }

  canvas.addEventListener('mousemove', (evt) => {
    const pos = getPos(evt);
    const item = hitTest(pos.x, pos.y);
    if (item) {
      canvas.style.cursor = 'pointer';
      showTip(item, pos.x, pos.y);
    } else {
      canvas.style.cursor = 'default';
      hideTip();
    }
  });
  canvas.addEventListener('mouseleave', hideTip);

  if ('ResizeObserver' in window && canvas.parentElement) {
    const observer = new ResizeObserver(() => draw());
    observer.observe(canvas.parentElement);
  } else {
    window.addEventListener('resize', draw);
  }

  requestAnimationFrame(loadDatabaseData);
  setInterval(loadDatabaseData, 10000);
})();

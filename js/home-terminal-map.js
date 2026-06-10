(function () {
  const canvas = document.getElementById('homeTerminalMap');
  const tooltip = document.getElementById('homeTerminalMapTooltip');
  if (!canvas || !tooltip) return;

  const TYPE_QUAY = '\u5cb8\u6865';
  const TYPE_YARD = '\u573a\u6865';
  const TYPE_AGV = 'AGV';
  const STATUS_FAULT = '\u6545\u969c';
  const STATUS_WORKING = '\u5de5\u4f5c\u4e2d';
  const STATUS_DEPARTED = '\u5df2\u79bb\u6e2f';

  const state = {
    equipment: [],
    tasks: [],
    ships: [],
    yards: [],
    containers: [],
    hitBoxes: [],
    loading: true,
    error: '',
    lastUpdated: '',
  };

  function normalizeEquipment(item) {
    return {
      id: item.id,
      code: item.code || '',
      name: item.name || item.code || '未命名设备',
      type: item.equipmentType || item.equipment_type || '',
      status: item.status || '\u7a7a\u95f2',
      location: item.location || '',
      efficiency: Number(item.efficiency || 0),
      taskId: item.currentTaskId || item.current_task_id || null,
      taskName: item.currentTaskName || '',
      containerNo: item.status === STATUS_WORKING ? (item.currentContainer || '') : '',
    };
  }

  function normalizeTask(item) {
    return {
      id: item.id,
      no: item.taskNo || item.task_no || item.id || '',
      name: item.taskName || item.task_type || '',
      status: item.status || 'pending',
      equipmentId: item.equipmentId || item.equipment_id || null,
      equipmentName: item.equipmentName || '',
      containerNo: item.containerId || item.containerNo || '',
      origin: item.origin || item.from_pos || '',
      destination: item.destination || item.to_pos || '',
      yardSlot: item.yardSlot || '',
      updatedAt: item.updatedAt || '',
    };
  }

  function normalizeShip(item) {
    return {
      id: item.id,
      name: item.name || '未命名船舶',
      voyage: item.voyage || '',
      berth: item.berth || '',
      status: item.status || '计划中',
    };
  }

  function normalizeYard(item) {
    return {
      id: item.id,
      name: item.yardName || item.yard_name || item.name || '未命名堆场',
      type: item.usageType || item.usage_type || item.type || '综合堆场',
      total: Number(item.totalCapacity || item.total_capacity || item.capacity || 240),
      used: Number(item.usedCapacity || item.used_capacity || item.used || 0),
      rate: Number(item.usageRate || 0),
    };
  }

  function normalizeContainer(item) {
    return {
      id: item.id,
      no: item.containerNo || item.container_no || '',
      type: item.containerType || item.container_type || '',
      status: item.status || '',
      yard: item.yard || item.yardName || '',
      area: item.zone || item.area || '',
      column: item.column || item.row || '',
      layer: item.layer || item.tier || '',
      shipId: item.shipId || item.ship_id || null,
      dangerous: Boolean(item.isDangerous || item.is_dangerous),
      reefer: Boolean(item.isReefer || item.is_refrigerated),
    };
  }

  function byType(type) {
    return state.equipment.filter((item) => item.type === type);
  }

  function visibleYards() {
    return state.yards.length ? state.yards : [
      { name: 'Yard A', type: '综合堆场', total: 240, used: 0 },
      { name: 'Yard B', type: '综合堆场', total: 240, used: 0 },
      { name: 'Yard C', type: '综合堆场', total: 240, used: 0 },
    ];
  }

  function activeShip() {
    return state.ships.find((ship) => ship.berth && ship.status !== STATUS_DEPARTED)
      || state.ships.find((ship) => ship.status !== STATUS_DEPARTED)
      || null;
  }

  function taskForEquipment(equipment) {
    if (!equipment) return null;
    const activeTasks = state.tasks.filter((task) => task.status !== 'completed');
    return activeTasks.find((task) => String(task.id) === String(equipment.taskId))
      || activeTasks.find((task) => String(task.equipmentId) === String(equipment.id))
      || activeTasks.find((task) => task.equipmentName === equipment.name)
      || null;
  }

  function addHitBox(box) {
    state.hitBoxes.push(box);
  }

  function roundRect(ctx, x, y, w, h, r) {
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

  function fillRoundRect(ctx, x, y, w, h, r, color) {
    ctx.fillStyle = color;
    roundRect(ctx, x, y, w, h, r);
    ctx.fill();
  }

  function strokeRoundRect(ctx, x, y, w, h, r, color, width) {
    ctx.strokeStyle = color;
    ctx.lineWidth = width || 1;
    roundRect(ctx, x, y, w, h, r);
    ctx.stroke();
  }

  function drawText(ctx, text, x, y, options) {
    const opt = options || {};
    ctx.save();
    ctx.fillStyle = opt.color || '#e2e8f0';
    ctx.font = opt.font || '600 13px Microsoft YaHei, Segoe UI, sans-serif';
    ctx.textAlign = opt.align || 'left';
    ctx.textBaseline = opt.baseline || 'alphabetic';
    ctx.fillText(text, x, y);
    ctx.restore();
  }

  function shortText(text, max) {
    const value = String(text || '');
    return value.length > max ? value.slice(0, max) + '...' : value;
  }

  function statusColor(status) {
    if (status === STATUS_FAULT) return '#ef4444';
    if (status === STATUS_WORKING || status === 'in-progress') return '#f59e0b';
    if (status === 'completed' || status === '已完成') return '#22c55e';
    return '#38bdf8';
  }

  function getCanvasSize() {
    const parent = canvas.parentElement;
    const width = Math.max(360, Math.floor(parent ? parent.getBoundingClientRect().width : 1100));
    const yardCount = Math.max(visibleYards().length, 3);
    const height = width < 860
      ? Math.max(960, 520 + yardCount * 146)
      : Math.max(680, Math.min(1200, 390 + Math.ceil(yardCount / 3) * 238));
    return { width, height };
  }

  function drawGrid(ctx, width, height) {
    ctx.fillStyle = '#071421';
    ctx.fillRect(0, 0, width, height);
    ctx.strokeStyle = 'rgba(148, 163, 184, 0.12)';
    ctx.lineWidth = 1;
    for (let x = 24; x < width; x += 32) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }
    for (let y = 24; y < height; y += 32) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }
  }

  function drawHeader(ctx, width) {
    fillRoundRect(ctx, 18, 16, width - 36, 48, 8, 'rgba(15, 23, 42, 0.86)');
    strokeRoundRect(ctx, 18, 16, width - 36, 48, 8, 'rgba(56, 189, 248, 0.35)', 1);
    drawText(ctx, '码头设备实时作业流程', 36, 47, {
      color: '#f8fafc',
      font: '800 20px Microsoft YaHei, Segoe UI, sans-serif',
    });
    drawText(ctx, '船舶 -> 岸桥卸船 -> AGV转运 -> 堆场转运点 -> 场桥入位', width / 2, 47, {
      color: '#bae6fd',
      font: '700 13px Microsoft YaHei, Segoe UI, sans-serif',
      align: 'center',
    });
    drawText(ctx, state.lastUpdated ? '刷新 ' + state.lastUpdated : '实时刷新中', width - 36, 47, {
      color: '#94a3b8',
      font: '600 12px Microsoft YaHei, Segoe UI, sans-serif',
      align: 'right',
    });
  }

  function drawStatusPill(ctx, x, y, status) {
    const color = statusColor(status);
    fillRoundRect(ctx, x, y, 58, 22, 99, color + '33');
    strokeRoundRect(ctx, x, y, 58, 22, 99, color, 1);
    drawText(ctx, status || '空闲', x + 29, y + 15, {
      color,
      font: '700 11px Microsoft YaHei, Segoe UI, sans-serif',
      align: 'center',
    });
  }

  function drawShip(ctx, layout) {
    const ship = activeShip();
    const x = layout.ship.x;
    const y = layout.ship.y;
    const w = layout.ship.w;
    const h = layout.ship.h;
    const seaGradient = ctx.createLinearGradient(0, y - 42, 0, y + h + 38);
    seaGradient.addColorStop(0, '#0b3b62');
    seaGradient.addColorStop(1, '#075985');
    fillRoundRect(ctx, x - 28, y - 42, w + 56, h + 82, 12, seaGradient);

    ctx.fillStyle = 'rgba(125, 211, 252, 0.26)';
    for (let i = 0; i < 6; i += 1) {
      ctx.beginPath();
      ctx.ellipse(x + 20 + i * 58, y + h + 26, 34, 4, 0, 0, Math.PI * 2);
      ctx.fill();
    }

    fillRoundRect(ctx, x, y, w, h, 18, '#1d4ed8');
    fillRoundRect(ctx, x + w - 52, y + 16, 38, 34, 7, '#e2e8f0');
    fillRoundRect(ctx, x + 18, y + 16, w - 88, h - 32, 8, '#0f2f70');
    drawText(ctx, ship ? shortText(ship.name, 14) : '暂无靠泊船舶', x + w / 2, y + 33, {
      color: '#ffffff',
      font: '800 15px Microsoft YaHei, Segoe UI, sans-serif',
      align: 'center',
    });
    drawText(ctx, ship ? (ship.berth || ship.status) : '等待船舶计划', x + w / 2, y + 55, {
      color: '#bfdbfe',
      font: '700 12px Microsoft YaHei, Segoe UI, sans-serif',
      align: 'center',
    });

    const containers = state.containers.filter((item) => {
      return item.status === '在船上' || (ship && String(item.shipId) === String(ship.id));
    }).slice(0, 18);
    for (let i = 0; i < 18; i += 1) {
      const cx = x + 26 + (i % 6) * 31;
      const cy = y + 72 + Math.floor(i / 6) * 18;
      const item = containers[i];
      const color = item ? ['#2563eb', '#0891b2', '#16a34a'][i % 3] : 'rgba(148, 163, 184, 0.18)';
      fillRoundRect(ctx, cx, cy, 24, 12, 2, color);
      if (item) {
        addHitBox({
          x: cx,
          y: cy,
          w: 24,
          h: 12,
          title: item.no,
          text: '船上待卸集装箱',
          extra: item.type || '-',
        });
      }
    }
  }

  function drawDock(ctx, layout) {
    fillRoundRect(ctx, layout.dock.x, layout.dock.y, layout.dock.w, layout.dock.h, 8, '#283746');
    drawText(ctx, '码头前沿作业区', layout.dock.x + layout.dock.w / 2, layout.dock.y + 29, {
      color: '#cbd5e1',
      font: '800 13px Microsoft YaHei, Segoe UI, sans-serif',
      align: 'center',
    });
    ctx.strokeStyle = 'rgba(226, 232, 240, 0.45)';
    ctx.setLineDash([8, 8]);
    ctx.beginPath();
    ctx.moveTo(layout.dock.x + 18, layout.roadY);
    ctx.lineTo(layout.dock.x + layout.dock.w - 18, layout.roadY);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  function drawQuayCrane(ctx, crane, index, layout) {
    const x = layout.quayXs[index] || layout.quayXs[0];
    const y = layout.quayY;
    const color = statusColor(crane.status);
    const hasTask = Boolean(crane.taskName || crane.containerNo);
    const isActive = crane.status === STATUS_WORKING && hasTask;
    ctx.strokeStyle = crane.status === STATUS_FAULT ? '#ef4444' : '#14b8a6';
    ctx.lineWidth = 5;
    ctx.beginPath();
    ctx.moveTo(x - 22, y + 72);
    ctx.lineTo(x - 22, y);
    ctx.lineTo(x + 52, y);
    ctx.lineTo(x + 52, y + 34);
    ctx.stroke();
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(x + 16, y);
    ctx.lineTo(x + 16, y + 86);
    ctx.stroke();

    const phase = isActive ? performance.now() / 900 + index : index;
    const trolleyX = x + 12 + Math.sin(phase) * 36;
    const hookY = y + 34 + (isActive ? Math.abs(Math.sin(phase * 1.35)) * 32 : 10);
    fillRoundRect(ctx, trolleyX - 10, y - 8, 20, 14, 3, '#fbbf24');
    ctx.strokeStyle = '#fbbf24';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(trolleyX, y + 6);
    ctx.lineTo(trolleyX, hookY);
    ctx.stroke();
    fillRoundRect(ctx, trolleyX - 18, hookY, 36, 8, 2, '#fbbf24');

    drawText(ctx, crane.name, x + 15, y - 18, {
      color: '#e0f2fe',
      font: '800 12px Microsoft YaHei, Segoe UI, sans-serif',
      align: 'center',
    });
    drawStatusPill(ctx, x - 14, y - 11, crane.status);
    addHitBox({
      x: x - 34,
      y: y - 28,
      w: 108,
      h: 126,
      title: crane.name,
      text: `${crane.type} / ${crane.status}`,
      extra: crane.containerNo ? `当前箱 ${crane.containerNo}` : (crane.taskName || '暂无任务'),
    });
  }

  function drawYardCrane(ctx, crane, index, yardRect) {
    const x = yardRect.x + yardRect.w / 2;
    const y = yardRect.y + 28;
    ctx.strokeStyle = crane.status === STATUS_FAULT ? '#ef4444' : '#22c55e';
    ctx.lineWidth = 4;
    ctx.strokeRect(yardRect.x + 22, y, yardRect.w - 44, 54);
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x, y + 68);
    ctx.stroke();
    const hasTask = Boolean(crane.taskName || crane.containerNo);
    const isActive = crane.status === STATUS_WORKING && hasTask;
    const sway = (isActive ? Math.sin(performance.now() / 850 + index) : 0) * (yardRect.w * 0.25);
    fillRoundRect(ctx, x + sway - 17, y + 26, 34, 8, 2, '#fbbf24');
    drawText(ctx, crane.name, x, y - 8, {
      color: '#dcfce7',
      font: '800 12px Microsoft YaHei, Segoe UI, sans-serif',
      align: 'center',
    });
    drawStatusPill(ctx, yardRect.x + yardRect.w - 78, yardRect.y + 10, crane.status);
    addHitBox({
      x: yardRect.x + 18,
      y: yardRect.y + 4,
      w: yardRect.w - 36,
      h: 94,
      title: crane.name,
      text: `${crane.type} / ${crane.status}`,
      extra: crane.containerNo ? `当前箱 ${crane.containerNo}` : (crane.taskName || '暂无任务'),
    });
  }

  function drawYards(ctx, layout) {
    const yards = visibleYards();
    const yardCranes = byType(TYPE_YARD);
    yards.forEach((yard, index) => {
      const rect = layout.yards[index];
      if (!rect) return;
      const actual = state.containers.filter((item) => item.yard === yard.name && item.status !== '离港').length;
      const used = Math.max(yard.used, actual);
      const rate = yard.total ? Math.min(100, Math.round((used / yard.total) * 100)) : Math.round(yard.rate || 0);
      const border = rate >= 80 ? '#ef4444' : rate >= 60 ? '#f59e0b' : '#38bdf8';
      fillRoundRect(ctx, rect.x, rect.y, rect.w, rect.h, 10, '#132433');
      strokeRoundRect(ctx, rect.x, rect.y, rect.w, rect.h, 10, border, 2);
      drawText(ctx, yard.name, rect.x + 14, rect.y + 28, {
        color: '#f8fafc',
        font: '800 15px Microsoft YaHei, Segoe UI, sans-serif',
      });
      drawText(ctx, `${yard.type} / 占用 ${rate}%`, rect.x + 14, rect.y + 50, {
        color: '#94a3b8',
        font: '600 12px Microsoft YaHei, Segoe UI, sans-serif',
      });

      fillRoundRect(ctx, rect.x + 14, rect.y + 60, rect.w - 28, 7, 99, '#334155');
      fillRoundRect(ctx, rect.x + 14, rect.y + 60, Math.max(8, (rect.w - 28) * rate / 100), 7, 99, border);

      const transfer = layout.transferPoints[index];
      fillRoundRect(ctx, transfer.x - 42, transfer.y - 12, 84, 24, 5, '#fbbf24');
      drawText(ctx, '转运点', transfer.x, transfer.y + 4, {
        color: '#422006',
        font: '800 12px Microsoft YaHei, Segoe UI, sans-serif',
        align: 'center',
      });

      const crane = yardCranes[index] || {
        name: `场桥${index + 1}`,
        type: TYPE_YARD,
        status: '空闲',
      };
      drawYardCrane(ctx, crane, index, rect);

      const containers = state.containers.filter((item) => item.yard === yard.name && item.status !== '离港').slice(0, 18);
      const startX = rect.x + 22;
      const startY = rect.y + 106;
      for (let i = 0; i < 18; i += 1) {
        const cx = startX + (i % 6) * ((rect.w - 44) / 6);
        const cy = startY + Math.floor(i / 6) * 26;
        const item = containers[i];
        const fill = item ? ['#2563eb', '#0891b2', '#16a34a'][i % 3] : 'rgba(148, 163, 184, 0.14)';
        fillRoundRect(ctx, cx, cy, Math.max(24, (rect.w - 66) / 6), 18, 3, fill);
        if (item) {
          drawText(ctx, item.no.slice(-4), cx + Math.max(24, (rect.w - 66) / 12), cy + 13, {
            color: '#eff6ff',
            font: '700 10px Consolas, monospace',
            align: 'center',
          });
          addHitBox({
            x: cx,
            y: cy,
            w: Math.max(24, (rect.w - 66) / 6),
            h: 18,
            title: item.no,
            text: `${yard.name} / ${item.area || '-'}`,
            extra: `列 ${item.column || '-'} / 层 ${item.layer || '-'}`,
          });
        }
      }
    });
  }

  function routePoint(points, progress) {
    const segments = [];
    let total = 0;
    for (let i = 0; i < points.length - 1; i += 1) {
      const a = points[i];
      const b = points[i + 1];
      const len = Math.hypot(b.x - a.x, b.y - a.y);
      segments.push({ a, b, len });
      total += len;
    }
    let distance = (progress % 1) * total;
    for (const segment of segments) {
      if (distance <= segment.len) {
        const t = segment.len ? distance / segment.len : 0;
        return {
          x: segment.a.x + (segment.b.x - segment.a.x) * t,
          y: segment.a.y + (segment.b.y - segment.a.y) * t,
          angle: Math.atan2(segment.b.y - segment.a.y, segment.b.x - segment.a.x),
        };
      }
      distance -= segment.len;
    }
    const last = points[points.length - 1];
    return { x: last.x, y: last.y, angle: 0 };
  }

  function drawRoute(ctx, points, color) {
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.setLineDash([10, 9]);
    ctx.beginPath();
    points.forEach((point, index) => {
      if (index === 0) ctx.moveTo(point.x, point.y);
      else ctx.lineTo(point.x, point.y);
    });
    ctx.stroke();
    ctx.setLineDash([]);
  }

  function hashText(text) {
    return String(text || '').split('').reduce((sum, char) => sum + char.charCodeAt(0), 0);
  }

  function quayPointForAgv(agv, layout, index) {
    const task = agv.task || {};
    const origin = task.origin || '';
    const points = layout.quayPoints || layout.quayXs.map((x) => ({ x, y: layout.roadY }));
    if (!points.length) return { x: layout.quayXs[0], y: layout.roadY };

    if (layout.quayPointByName) {
      const matched = Object.keys(layout.quayPointByName).find((name) => name && origin.includes(name));
      if (matched) return layout.quayPointByName[matched];
    }

    const dynamicKey = task.containerNo || task.no || task.destination || agv.containerNo;
    if (dynamicKey) return points[hashText(dynamicKey) % points.length];
    return points[index % points.length];
  }

  function drawAgv(ctx, agv, index, layout) {
    const hasTask = Boolean(agv.task);
    const isWorking = agv.status === STATUS_WORKING && hasTask;
    const target = transferPointForAgv(agv, layout, index);
    const start = quayPointForAgv(agv, layout, index);
    const points = [
      start,
      { x: start.x, y: layout.roadY + 42 },
      { x: target.x, y: layout.roadY + 42 },
      target,
    ];
    const routeColor = agv.status === STATUS_FAULT ? 'rgba(239, 68, 68, 0.72)' : isWorking ? 'rgba(249, 115, 22, 0.68)' : 'rgba(148, 163, 184, 0.24)';
    if (isWorking || agv.status === STATUS_FAULT) drawRoute(ctx, points, routeColor);
    const speed = 14000;
    const idleProgress = Math.min(0.08 + index * 0.04, 0.24);
    const progress = agv.status === STATUS_FAULT ? 0.05 : isWorking ? ((performance.now() + index * 2300) % speed) / speed : idleProgress;
    const pos = routePoint(points, progress);
    ctx.save();
    ctx.translate(pos.x, pos.y);
    ctx.rotate(pos.angle);
    fillRoundRect(ctx, -23, -11, 46, 22, 6, agv.status === STATUS_FAULT ? '#7f1d1d' : isWorking ? '#f97316' : '#64748b');
    if (isWorking && agv.containerNo) {
      fillRoundRect(ctx, -10, -16, 28, 12, 3, '#2563eb');
    }
    fillRoundRect(ctx, -26, 9, 10, 5, 2, '#0f172a');
    fillRoundRect(ctx, 16, 9, 10, 5, 2, '#0f172a');
    ctx.restore();
    drawText(ctx, agv.name, pos.x, pos.y - 22, {
      color: agv.status === STATUS_FAULT ? '#fecaca' : '#fed7aa',
      font: '800 11px Microsoft YaHei, Segoe UI, sans-serif',
      align: 'center',
    });
    if (isWorking && agv.containerNo) {
      drawText(ctx, shortText(agv.containerNo, 10), pos.x, pos.y + 28, {
        color: '#bfdbfe',
        font: '800 10px Consolas, Microsoft YaHei, sans-serif',
        align: 'center',
      });
    }
    addHitBox({
      x: pos.x - 34,
      y: pos.y - 28,
      w: 68,
      h: 56,
      title: agv.name,
      text: `${agv.type} / ${agv.status}`,
      extra: agv.containerNo ? `运输箱 ${agv.containerNo}` : (agv.taskName || '按路线待命'),
    });
  }

  function yardNameFromTask(task) {
    if (!task) return '';
    const destination = task.destination || '';
    if (destination.includes('\u8f6c\u8fd0\u70b9')) {
      return destination.split('\u8f6c\u8fd0\u70b9')[0].trim();
    }
    if (destination.includes('/')) {
      return destination.split('/', 1)[0].trim();
    }
    const yardSlot = task.yardSlot || '';
    const finalSlotMatch = yardSlot.match(/\u6700\u7ec8\u7bb1\u4f4d\s*([^；;]+)/);
    if (finalSlotMatch && finalSlotMatch[1]) {
      return finalSlotMatch[1].split('/', 1)[0].trim();
    }
    return '';
  }

  function transferPointForAgv(agv, layout, index) {
    const yardName = yardNameFromTask(agv.task);
    if (yardName && layout.transferPointByYard && layout.transferPointByYard[yardName]) {
      return layout.transferPointByYard[yardName];
    }
    return layout.transferPoints[index % layout.transferPoints.length];
  }

  function drawEquipmentPanel(ctx, layout) {
    const x = layout.panel.x;
    const y = layout.panel.y;
    const w = layout.panel.w;
    const h = layout.panel.h;
    fillRoundRect(ctx, x, y, w, h, 10, 'rgba(15, 23, 42, 0.9)');
    strokeRoundRect(ctx, x, y, w, h, 10, 'rgba(56, 189, 248, 0.28)', 1);
    drawText(ctx, '设备状态', x + 16, y + 28, {
      color: '#f8fafc',
      font: '800 15px Microsoft YaHei, Segoe UI, sans-serif',
    });

    const groups = [
      { label: '岸桥', type: TYPE_QUAY, color: '#14b8a6' },
      { label: 'AGV', type: TYPE_AGV, color: '#f97316' },
      { label: '场桥', type: TYPE_YARD, color: '#22c55e' },
    ];
    groups.forEach((group, index) => {
      const list = byType(group.type);
      const working = list.filter((item) => item.status === STATUS_WORKING).length;
      const fault = list.filter((item) => item.status === STATUS_FAULT).length;
      const idle = Math.max(list.length - working - fault, 0);
      const rowY = y + 58 + index * 52;
      fillRoundRect(ctx, x + 16, rowY, w - 32, 38, 7, 'rgba(30, 41, 59, 0.92)');
      drawText(ctx, group.label, x + 30, rowY + 24, {
        color: group.color,
        font: '800 13px Microsoft YaHei, Segoe UI, sans-serif',
      });
      drawText(ctx, `总数 ${list.length || 0}`, x + 90, rowY + 24, { color: '#cbd5e1' });
      drawText(ctx, `空闲 ${idle}`, x + 150, rowY + 24, { color: '#38bdf8' });
      drawText(ctx, `工作 ${working}`, x + 214, rowY + 24, { color: '#f59e0b' });
      drawText(ctx, `故障 ${fault}`, x + 278, rowY + 24, { color: '#ef4444' });
    });

    if (h < 220) return;

    const activeTasks = state.tasks.filter((task) => task.status !== 'completed').slice(0, 4);
    drawText(ctx, '当前作业单', x + 16, y + 230, {
      color: '#f8fafc',
      font: '800 15px Microsoft YaHei, Segoe UI, sans-serif',
    });
    if (!activeTasks.length) {
      drawText(ctx, '暂无未完成作业，设备按默认流程巡航展示', x + 16, y + 258, {
        color: '#94a3b8',
        font: '600 12px Microsoft YaHei, Segoe UI, sans-serif',
      });
      return;
    }
    activeTasks.forEach((task, index) => {
      const rowY = y + 250 + index * 30;
      const color = statusColor(task.status);
      fillRoundRect(ctx, x + 16, rowY, 8, 18, 3, color);
      drawText(ctx, shortText(task.name || task.no, 16), x + 32, rowY + 14, {
        color: '#e2e8f0',
        font: '700 12px Microsoft YaHei, Segoe UI, sans-serif',
      });
      drawText(ctx, shortText(task.containerNo || task.destination || '-', 12), x + w - 18, rowY + 14, {
        color: '#94a3b8',
        font: '600 12px Microsoft YaHei, Segoe UI, sans-serif',
        align: 'right',
      });
    });
  }

  function drawMessage(ctx, width, height, text, error) {
    drawGrid(ctx, width, height);
    drawHeader(ctx, width);
    fillRoundRect(ctx, width / 2 - 190, height / 2 - 34, 380, 68, 10, 'rgba(15, 23, 42, 0.92)');
    strokeRoundRect(ctx, width / 2 - 190, height / 2 - 34, 380, 68, 10, error ? '#ef4444' : '#38bdf8', 1);
    drawText(ctx, text, width / 2, height / 2 + 5, {
      color: error ? '#fecaca' : '#e0f2fe',
      font: '800 15px Microsoft YaHei, Segoe UI, sans-serif',
      align: 'center',
    });
  }

  function buildLayout(width, height) {
    const pad = 28;
    const yardsForLayout = visibleYards();
    const yardCount = Math.max(yardsForLayout.length, 3);
    if (width < 860) {
      const workW = width - pad * 2;
      const yardTop = 520;
      const yardGap = 14;
      const yardH = 132;
      const quayCount = Math.max(1, Math.min(2, byType(TYPE_QUAY).length || 2));
      const quayXs = Array.from({ length: quayCount }, (_, i) => pad + 145 + i * 94);
      const roadY = 293;
      const quayPoints = quayXs.map((x) => ({ x, y: roadY }));
      const quayEquipment = byType(TYPE_QUAY).slice(0, quayCount);
      const quayPointByName = {};
      quayEquipment.forEach((item, index) => {
        const point = quayPoints[index];
        if (!point) return;
        if (item.name) quayPointByName[item.name] = point;
        if (item.code) quayPointByName[item.code] = point;
      });
      const yards = Array.from({ length: yardCount }, (_, i) => ({
        x: pad,
        y: yardTop + i * (yardH + yardGap),
        w: workW,
        h: yardH,
      }));
      const yardNames = yardsForLayout.map((yard) => yard.name);
      const transferPoints = yards.map((rect, index) => ({ x: rect.x + rect.w / 2, y: rect.y - 22, yardName: yardNames[index] }));
      const transferPointByYard = Object.fromEntries(transferPoints.map((point) => [point.yardName, point]));
      return {
        ship: { x: pad + 10, y: 108, w: Math.min(280, workW - 20), h: 116 },
        dock: { x: pad, y: 255, w: workW, h: 74 },
        roadY,
        quayY: 176,
        quayXs,
        quayPoints,
        quayPointByName,
        yards,
        transferPoints,
        transferPointByYard,
        panel: { x: pad, y: 350, w: workW, h: 150 },
      };
    }
    const panelW = Math.min(360, Math.max(300, width * 0.28));
    const workW = width - panelW - pad * 3;
    const shipW = Math.min(300, workW * 0.35);
    const dockY = 245;
    const yardTop = 390;
    const yardGap = 16;
    const yardCols = Math.min(3, yardCount);
    const yardRows = Math.ceil(yardCount / yardCols);
    const yardW = (workW - yardGap * (yardCols - 1)) / yardCols;
    const yardH = Math.max(214, Math.min(260, (height - yardTop - pad - yardGap * (yardRows - 1)) / yardRows));
    const quayCount = Math.max(1, Math.min(3, byType(TYPE_QUAY).length || 2));
    const quayXs = Array.from({ length: quayCount }, (_, i) => pad + shipW + 64 + i * 96);
    const roadY = dockY + 38;
    const quayPoints = quayXs.map((x) => ({ x, y: roadY }));
    const quayEquipment = byType(TYPE_QUAY).slice(0, quayCount);
    const quayPointByName = {};
    quayEquipment.forEach((item, index) => {
      const point = quayPoints[index];
      if (!point) return;
      if (item.name) quayPointByName[item.name] = point;
      if (item.code) quayPointByName[item.code] = point;
    });
    const yards = Array.from({ length: yardCount }, (_, i) => ({
      x: pad + (i % yardCols) * (yardW + yardGap),
      y: yardTop + Math.floor(i / yardCols) * (yardH + yardGap),
      w: yardW,
      h: yardH,
    }));
    const yardNames = yardsForLayout.map((yard) => yard.name);
    const transferPoints = yards.map((rect, index) => ({ x: rect.x + rect.w / 2, y: rect.y - 28, yardName: yardNames[index] }));
    const transferPointByYard = Object.fromEntries(transferPoints.map((point) => [point.yardName, point]));
    return {
      ship: { x: pad + 18, y: 108, w: shipW, h: 124 },
      dock: { x: pad, y: dockY, w: workW, h: 74 },
      roadY,
      quayY: 166,
      quayXs,
      quayPoints,
      quayPointByName,
      yards,
      transferPoints,
      transferPointByYard,
      panel: { x: width - panelW - pad, y: 82, w: panelW, h: height - 110 },
    };
  }

  function draw() {
    const { width, height } = getCanvasSize();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = width + 'px';
    canvas.style.height = height + 'px';
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    state.hitBoxes = [];

    if (state.error) {
      drawMessage(ctx, width, height, state.error, true);
      requestAnimationFrame(draw);
      return;
    }
    if (state.loading) {
      drawMessage(ctx, width, height, '正在加载码头设备与作业数据...', false);
      requestAnimationFrame(draw);
      return;
    }

    drawGrid(ctx, width, height);
    drawHeader(ctx, width);
    const layout = buildLayout(width, height);
    drawShip(ctx, layout);
    drawDock(ctx, layout);
    drawYards(ctx, layout);

    const quayCranes = byType(TYPE_QUAY);
    const fallbackQuay = quayCranes.length ? quayCranes : [
      { name: '岸桥1', type: TYPE_QUAY, status: '空闲' },
      { name: '岸桥2', type: TYPE_QUAY, status: '空闲' },
    ];
    fallbackQuay.slice(0, 3).forEach((crane, index) => {
      const task = taskForEquipment(crane);
      drawQuayCrane(ctx, Object.assign({}, crane, {
        taskName: task ? task.name : crane.taskName,
        containerNo: crane.containerNo || (task ? task.containerNo : ''),
      }), index, layout);
    });

    const agvs = byType(TYPE_AGV);
    const fallbackAgv = agvs.length ? agvs : [
      { name: 'AGV1', type: TYPE_AGV, status: '\u7a7a\u95f2' },
      { name: 'AGV2', type: TYPE_AGV, status: '\u7a7a\u95f2' },
    ];
    fallbackAgv.slice(0, 6).forEach((agv, index) => {
      const task = taskForEquipment(agv);
      const containerNo = agv.status === STATUS_WORKING ? (agv.containerNo || (task ? task.containerNo : '')) : '';
      drawAgv(ctx, Object.assign({}, agv, {
        taskName: task ? task.name : agv.taskName,
        containerNo,
        task,
      }), index, layout);
    });

    drawEquipmentPanel(ctx, layout);
    requestAnimationFrame(draw);
  }

  async function loadData() {
    try {
      const [equipmentResp, taskResp, shipResp, yardResp, containerResp] = await Promise.all([
        fetch('/equipment', { credentials: 'same-origin' }),
        fetch('/tasks', { credentials: 'same-origin' }),
        fetch('/ships', { credentials: 'same-origin' }),
        fetch('/yards', { credentials: 'same-origin' }),
        fetch('/containers', { credentials: 'same-origin' }),
      ]);
      if (!equipmentResp.ok || !taskResp.ok || !shipResp.ok || !yardResp.ok || !containerResp.ok) {
        throw new Error('接口加载失败，请确认已登录并通过 Flask 服务访问首页');
      }
      state.equipment = (await equipmentResp.json()).map(normalizeEquipment);
      state.tasks = (await taskResp.json()).map(normalizeTask);
      state.ships = (await shipResp.json()).map(normalizeShip);
      state.yards = (await yardResp.json()).map(normalizeYard);
      state.containers = (await containerResp.json()).map(normalizeContainer);
      state.loading = false;
      state.error = '';
      state.lastUpdated = new Date().toLocaleTimeString('zh-CN', { hour12: false });
    } catch (err) {
      state.loading = false;
      state.error = err.message || '实时作业数据加载失败';
    }
  }

  function showTip(item, x, y) {
    tooltip.hidden = false;
    tooltip.textContent = item.title + ' · ' + item.text + ' · ' + item.extra;
    const maxLeft = Math.max(8, canvas.clientWidth - tooltip.offsetWidth - 12);
    tooltip.style.left = Math.min(x + 14, maxLeft) + 'px';
    tooltip.style.top = Math.max(10, y - 40) + 'px';
  }

  function hideTip() {
    tooltip.hidden = true;
  }

  function hitTest(x, y) {
    return state.hitBoxes.find((box) => x >= box.x && x <= box.x + box.w && y >= box.y && y <= box.y + box.h);
  }

  canvas.addEventListener('mousemove', (evt) => {
    const rect = canvas.getBoundingClientRect();
    const item = hitTest(evt.clientX - rect.left, evt.clientY - rect.top);
    if (item) {
      canvas.style.cursor = 'pointer';
      showTip(item, evt.clientX - rect.left, evt.clientY - rect.top);
    } else {
      canvas.style.cursor = 'default';
      hideTip();
    }
  });
  canvas.addEventListener('mouseleave', hideTip);

  if ('ResizeObserver' in window && canvas.parentElement) {
    new ResizeObserver(draw).observe(canvas.parentElement);
  } else {
    window.addEventListener('resize', draw);
  }

  loadData();
  setInterval(loadData, 10000);
  requestAnimationFrame(draw);
})();

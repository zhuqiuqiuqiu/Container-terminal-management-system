(function () {
  const el = (id) => document.getElementById(id);

  function setText(id, value) {
    const node = el(id);
    if (node) node.textContent = value;
  }

  function drawDonut(canvas, items, colors) {
    if (!canvas) return;
    const parentWidth = canvas.parentElement ? canvas.parentElement.clientWidth : 260;
    const width = Math.max(220, parentWidth);
    const height = 210;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = width + 'px';
    canvas.style.height = height + 'px';
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const total = items.reduce((sum, item) => sum + item.value, 0);
    const cx = width / 2;
    const cy = 86;
    const radius = 58;
    let start = -Math.PI / 2;

    if (total === 0) {
      ctx.strokeStyle = '#dbe5f0';
      ctx.lineWidth = 22;
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.stroke();
    } else {
      items.forEach((item, index) => {
        const angle = (item.value / total) * Math.PI * 2;
        ctx.strokeStyle = colors[index % colors.length];
        ctx.lineWidth = 22;
        ctx.beginPath();
        ctx.arc(cx, cy, radius, start, start + angle);
        ctx.stroke();
        start += angle;
      });
    }

    ctx.fillStyle = '#17324d';
    ctx.font = '700 22px Segoe UI, Microsoft YaHei, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(String(total), cx, cy + 8);
    ctx.font = '12px Segoe UI, Microsoft YaHei, sans-serif';
    ctx.fillStyle = '#4a6d8c';
    ctx.fillText('总量', cx, cy + 28);

    const legendY = 166;
    const legendGap = Math.min(120, width / Math.max(items.length, 1));
    items.forEach((item, index) => {
      const x = width / 2 - ((items.length - 1) * legendGap) / 2 + index * legendGap;
      ctx.fillStyle = colors[index % colors.length];
      ctx.fillRect(x - 32, legendY, 10, 10);
      ctx.fillStyle = '#4a6d8c';
      ctx.font = '12px Segoe UI, Microsoft YaHei, sans-serif';
      ctx.textAlign = 'left';
      ctx.fillText(`${item.name} ${item.value}`, x - 18, legendY + 9);
    });
  }

  function renderRank(rows) {
    const wrap = el('yardUsageRank');
    if (!wrap) return;
    if (!rows || rows.length === 0) {
      wrap.innerHTML = '<div class="empty-note">暂无堆场统计数据</div>';
      return;
    }
    wrap.innerHTML = rows
      .slice()
      .sort((a, b) => b.usageRate - a.usageRate)
      .map((row) => {
        const rate = Math.min(100, Number(row.usageRate || 0));
        return `
          <div class="home-rank-row">
            <div class="home-rank-meta">
              <strong>${row.name}</strong>
              <span>${row.used}/${row.total} · ${rate}%</span>
            </div>
            <div class="home-rank-bar"><i style="width:${rate}%"></i></div>
          </div>
        `;
      })
      .join('');
  }

  async function loadStats() {
    try {
      const resp = await fetch('/api/dashboard/stats', { credentials: 'same-origin' });
      if (!resp.ok) throw new Error('stats failed');
      const data = await resp.json();
      const kpis = data.kpis || {};
      setText('statContainerTotal', kpis.containerTotal ?? '-');
      setText('statYardUsage', `${kpis.yardUsageRate ?? 0}%`);
      setText('statYardCapacity', `${kpis.yardUsedCapacity ?? 0} / ${kpis.yardTotalCapacity ?? 0}`);
      setText('statBerthedShips', kpis.berthedShips ?? '-');
      setText('statRunningTasks', kpis.runningTasks ?? '-');

      drawDonut(el('taskStatusChart'), [
        { name: '未开始', value: data.taskStatus?.pending || 0 },
        { name: '进行中', value: data.taskStatus?.inProgress || 0 },
        { name: '已完成', value: data.taskStatus?.completed || 0 },
      ], ['#94a3b8', '#f59e0b', '#22c55e']);

      drawDonut(el('shipStatusChart'), [
        { name: '靠泊', value: data.shipStatus?.berthed || 0 },
        { name: '计划', value: data.shipStatus?.scheduled || 0 },
        { name: '离港', value: data.shipStatus?.departed || 0 },
      ], ['#2563eb', '#06b6d4', '#64748b']);

      renderRank(data.yardUsage || []);
    } catch (err) {
      setText('statContainerTotal', '加载失败');
    }
  }

  window.addEventListener('resize', loadStats);
  loadStats();
  setInterval(loadStats, 10000);
})();

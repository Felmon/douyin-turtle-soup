"""v6 仪表盘 — 实时数据可视化（主播看数据用）

显示：在线人数、弹幕速率、礼物速率、收入趋势、段位分布、TOP 10 排行榜。
"""
import json

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>海龟汤 · 仪表盘</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0c0f1e;color:#e2e8f0;font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;padding:16px;min-height:100vh}

.app{max-width:1400px;margin:0 auto;display:grid;grid-template-columns:repeat(4,1fr);gap:12px}

.header{grid-column:1/-1;display:flex;justify-content:space-between;align-items:center;padding:16px 20px;background:rgba(18,22,48,0.6);border-radius:12px;border:1px solid rgba(255,255,255,0.06)}
.header h1{font-size:18px;background:linear-gradient(135deg,#e2e8f0,#94a3b8);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.header .status{display:flex;align-items:center;gap:6px;font-size:12px;color:#64748b}
.dot{width:8px;height:8px;border-radius:50%;background:#22c55e;box-shadow:0 0 8px #22c55e;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}

.card{background:rgba(18,22,48,0.6);border-radius:12px;border:1px solid rgba(255,255,255,0.06);padding:16px}
.card h3{font-size:12px;color:#64748b;margin-bottom:8px;text-transform:uppercase;letter-spacing:1px}
.metric{font-size:32px;font-weight:900;color:#00d4ff;font-feature-settings:'tnum'}
.metric .unit{font-size:14px;color:#64748b;margin-left:4px}
.sub-metric{font-size:11px;color:#64748b;margin-top:4px}
.metric.green{color:#22c55e}
.metric.gold{color:#fbbf24}
.metric.red{color:#ef4444}

.col-1{grid-column:span 1}
.col-2{grid-column:span 2}
.col-3{grid-column:span 3}
.col-4{grid-column:span 4}

.chart-container{height:140px;position:relative}
canvas{width:100%!important;height:100%!important}

.leaderboard{display:flex;flex-direction:column;gap:4px;max-height:240px;overflow-y:auto}
.lb-item{display:flex;align-items:center;gap:8px;padding:6px 8px;background:rgba(0,0,0,0.2);border-radius:6px;font-size:12px}
.lb-item .rank{width:20px;height:20px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:900;font-size:10px;flex-shrink:0}
.rank.r1{background:linear-gradient(135deg,#fbbf24,#f59e0b);color:#000}
.rank.r2{background:linear-gradient(135deg,#94a3b8,#64748b);color:#000}
.rank.r3{background:linear-gradient(135deg,#b45309,#92400e);color:#fff}
.rank.rn{background:rgba(100,116,139,0.3);color:#94a3b8}
.lb-item .name{flex:1;font-weight:600;color:#e2e8f0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lb-item .tier{font-size:10px;padding:1px 6px;border-radius:6px;background:rgba(0,212,255,0.15);color:#00d4ff}
.lb-item .score{font-size:11px;color:#fbbf24;font-weight:700;flex-shrink:0}

.gift-list{display:flex;flex-direction:column;gap:4px;max-height:240px;overflow-y:auto}
.gift-row{display:flex;align-items:center;gap:8px;padding:4px 8px;background:rgba(0,0,0,0.2);border-radius:6px;font-size:11px}
.gift-row .name{flex:1;color:#e2e8f0}
.gift-row .count{color:#94a3b8;font-feature-settings:'tnum'}
.gift-row .value{color:#fbbf24;font-weight:700;min-width:60px;text-align:right}

.tier-dist{display:grid;grid-template-columns:repeat(5,1fr);gap:4px}
.td-item{text-align:center;padding:6px;background:rgba(0,0,0,0.2);border-radius:6px;font-size:10px}
.td-item .num{font-size:18px;font-weight:900;display:block;color:#00d4ff}
.td-item .label{color:#64748b}

.session-controls{grid-column:1/-1;display:flex;gap:8px;padding:12px 16px;background:rgba(18,22,48,0.6);border-radius:12px;border:1px solid rgba(255,255,255,0.06);align-items:center}
.btn{padding:8px 16px;border:none;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;transition:all 0.2s}
.btn-primary{background:linear-gradient(135deg,#00d4ff,#7c3aed);color:#fff}
.btn-primary:hover{box-shadow:0 4px 16px rgba(0,212,255,0.35)}
.btn-ghost{background:rgba(255,255,255,0.05);color:#94a3b8}
.btn-ghost:hover{background:rgba(255,255,255,0.1)}

.refresh-info{font-size:11px;color:#64748b;margin-left:auto}
.chart-wrap{position:relative}
.chart-tooltip{position:absolute;display:none;background:rgba(0,0,0,0.85);color:#e2e8f0;padding:6px 10px;border-radius:6px;font-size:11px;pointer-events:none;white-space:nowrap;z-index:10;border:1px solid rgba(255,255,255,0.1);backdrop-filter:blur(4px)}
.time-range{display:flex;gap:4px;margin-bottom:6px}
.time-btn{padding:2px 10px;border:1px solid rgba(255,255,255,0.1);border-radius:4px;background:transparent;color:#64748b;font-size:11px;cursor:pointer;transition:all 0.2s}
.time-btn:hover{border-color:#00d4ff;color:#00d4ff}
.time-btn.active{background:#00d4ff22;border-color:#00d4ff;color:#00d4ff}
</style>
</head>
<body>

<div class="app">
  <div class="header">
    <h1>📊 海龟汤 · 实时数据</h1>
    <div class="status">
      <span class="dot"></span>
      <span id="statusText">运行中</span>
    </div>
  </div>

  <div class="card col-1">
    <h3>在线观众</h3>
    <div class="metric" id="viewers">0<span class="unit">人</span></div>
    <div class="sub-metric">↑ <span id="viewersDelta">0</span> / 5分钟</div>
  </div>

  <div class="card col-1">
    <h3>弹幕/分钟</h3>
    <div class="metric green" id="danmakuRate">0<span class="unit">条</span></div>
    <div class="sub-metric">总 <span id="danmakuTotal">0</span> 条</div>
  </div>

  <div class="card col-1">
    <h3>礼物/分钟</h3>
    <div class="metric gold" id="giftRate">0<span class="unit">个</span></div>
    <div class="sub-metric">总收入 <span id="giftRevenue">0</span> 抖币</div>
  </div>

  <div class="card col-1">
    <h3>付费率</h3>
    <div class="metric" id="payRate">0<span class="unit">%</span></div>
    <div class="sub-metric"><span id="paidUsers">0</span> 位付费用户</div>
  </div>

  <div class="card col-1">
    <h3>本场局数</h3>
    <div class="metric green" id="roundCount">0<span class="unit">局</span></div>
  </div>

  <div class="card col-1">
    <h3>本场时长</h3>
    <div class="metric" id="sessionDuration">00:00</div>
  </div>

  <div class="card col-1">
    <h3>答对率</h3>
    <div class="metric gold" id="accuracy">0<span class="unit">%</span></div>
  </div>

  <div class="card col-2">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
      <h3 style="margin-bottom:0">📈 弹幕趋势</h3>
      <div class="time-range" id="danmakuRange">
        <button class="time-btn active" data-range="30">30分钟</button>
        <button class="time-btn" data-range="60">1小时</button>
        <button class="time-btn" data-range="240">4小时</button>
      </div>
    </div>
    <div class="chart-wrap">
      <canvas id="danmakuChart"></canvas>
      <div class="chart-tooltip" id="danmakuTooltip"></div>
    </div>
  </div>

  <div class="card col-2">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
      <h3 style="margin-bottom:0">🎁 礼物收入趋势</h3>
      <div class="time-range" id="giftRange">
        <button class="time-btn active" data-range="30">30分钟</button>
        <button class="time-btn" data-range="60">1小时</button>
        <button class="time-btn" data-range="240">4小时</button>
      </div>
    </div>
    <div class="chart-wrap">
      <canvas id="giftChart"></canvas>
      <div class="chart-tooltip" id="giftTooltip"></div>
    </div>
  </div>

  <div class="card col-2">
    <h3>🏆 段位排行榜 TOP 10</h3>
    <div class="leaderboard" id="leaderboard"></div>
  </div>

  <div class="card col-2">
    <h3>💰 礼物收入 TOP 10</h3>
    <div class="gift-list" id="giftList"></div>
  </div>

  <div class="card col-4">
    <h3>📊 段位分布</h3>
    <div class="tier-dist" id="tierDist"></div>
  </div>

  <div class="session-controls">
    <button class="btn btn-ghost" onclick="exportData()">📥 导出数据</button>
    <button class="btn btn-ghost" onclick="resetSession()">🔄 重置会话</button>
    <span class="refresh-info">最近更新: <span id="lastUpdate">-</span></span>
  </div>
</div>

<script>
const wsUrl = (location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/ws';
let ws = null;
let reconnectTimer = null;
let chartState = { danmaku: { maxRange: 30 }, gift: { maxRange: 30 } };

function connect() {
  if (ws) ws.close();
  ws = new WebSocket(wsUrl);
  ws.onopen = () => { console.log('[WS] 已连接'); if(reconnectTimer){clearTimeout(reconnectTimer);reconnectTimer=null} document.getElementById('statusText').textContent='已连接'; };
  ws.onclose = () => { document.getElementById('statusText').textContent='已断开'; scheduleReconnect(); };
  ws.onmessage = (e) => { try { handleMessage(JSON.parse(e.data)); } catch(err){} };
}
function scheduleReconnect() {
  if (!reconnectTimer) reconnectTimer = setTimeout(() => { reconnectTimer=null; connect(); }, 3000);
}

function handleMessage(msg) {
  switch(msg.type) {
    case 'state_sync':
      if (msg.metrics) updateMetrics(msg.metrics);
      else if (msg.room?.stats) updateMetrics(msg.room.stats);
      break;
    case 'metrics_update': if (msg.metrics) updateMetrics(msg.metrics); break;
    case 'score_update': refreshMetrics(); refreshLeaderboard(); break;
    case 'tier_up': refreshMetrics(); refreshLeaderboard(); refreshTierDist(); break;
  }
  document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString();
}

async function refreshMetrics() {
  try {
    const m = await (await fetch('/api/admin/metrics')).json();
    updateMetrics(m);
  } catch(e) {}
}

function updateMetrics(m) {
  if (!m) return;
  document.getElementById('viewers').innerHTML = (m.viewers||0) + '<span class="unit">人</span>';
  document.getElementById('danmakuRate').innerHTML = (m.danmaku_rate||0) + '<span class="unit">条</span>';
  document.getElementById('giftRate').innerHTML = (m.gift_rate||0) + '<span class="unit">个</span>';
  document.getElementById('payRate').innerHTML = (m.pay_rate||0) + '<span class="unit">%</span>';
  document.getElementById('viewersDelta').textContent = m.viewers_delta||0;
  document.getElementById('danmakuTotal').textContent = m.danmaku_total||0;
  document.getElementById('giftRevenue').textContent = m.gift_revenue||0;
  document.getElementById('paidUsers').textContent = m.paid_users||0;
  document.getElementById('roundCount').innerHTML = (m.round_count||0) + '<span class="unit">局</span>';
  const dur = m.session_duration || 0;
  const mins = Math.floor(dur / 60);
  const secs = dur % 60;
  document.getElementById('sessionDuration').textContent = String(mins).padStart(2,'0') + ':' + String(secs).padStart(2,'0');
  document.getElementById('accuracy').innerHTML = (m.accuracy||0) + '<span class="unit">%</span>';

  if (m.leaderboard) updateLeaderboard(m.leaderboard);
  if (m.gift_list) updateGiftList(m.gift_list);
  if (m.tier_dist) updateTierDist(m.tier_dist);
  if (m.danmaku_series) drawChart('danmakuChart', m.danmaku_series, '#00d4ff', '条/分');
  if (m.gift_series) drawChart('giftChart', m.gift_series, '#fbbf24', '抖币/分');
}

function updateLeaderboard(list) {
  const container = document.getElementById('leaderboard');
  if (!list || list.length === 0) { container.innerHTML = '<div style="text-align:center;color:#64748b;padding:16px;font-size:12px">暂无数据</div>'; return; }
  container.innerHTML = list.slice(0,10).map((u,i) =>
    '<div class="lb-item"><div class="rank ' + (i<3?'r'+(i+1):'rn') + '">' + (i+1) + '</div><div class="name">' + escapeHtml(u.name||'') + '</div><div class="tier">' + escapeHtml(u.tier||'') + '</div><div class="score">' + (u.score||0) + '</div></div>'
  ).join('');
}

function updateGiftList(list) {
  const container = document.getElementById('giftList');
  if (!list || list.length === 0) { container.innerHTML = '<div style="text-align:center;color:#64748b;padding:16px;font-size:12px">暂无数据</div>'; return; }
  container.innerHTML = list.slice(0,10).map(g =>
    '<div class="gift-row"><div class="name">' + escapeHtml(g.name||'') + '</div><div class="count">×' + (g.count||0) + '</div><div class="value">' + (g.value||0) + '抖币</div></div>'
  ).join('');
}

function updateTierDist(dist) {
  const container = document.getElementById('tierDist');
  if (!dist || Object.keys(dist).length === 0) { container.innerHTML = '<div style="text-align:center;color:#64748b;padding:16px;font-size:12px">暂无数据</div>'; return; }
  container.innerHTML = Object.entries(dist).map(([tier, count]) =>
    '<div class="td-item"><span class="num">' + count + '</span><span class="label">' + tier + '</span></div>'
  ).join('');
}

function drawChart(id, data, color, label) {
  const canvas = document.getElementById(id);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.round(rect.width * dpr);
  canvas.height = Math.round(rect.height * dpr);
  ctx.scale(dpr, dpr);
  const w = rect.width, h = rect.height;
  ctx.clearRect(0, 0, w, h);

  const rangeKey = id === 'danmakuChart' ? 'danmaku' : 'gift';
  const maxRange = (chartState[rangeKey] || {}).maxRange || 30;
  const sliced = data ? data.slice(-maxRange) : [];
  if (!sliced || sliced.length < 2) {
    ctx.fillStyle = '#64748b'; ctx.font = '12px sans-serif';
    ctx.textAlign = 'center'; ctx.fillText('等待数据...', w/2, h/2);
    canvas._chartData = null;
    return;
  }

  const max = Math.max(...sliced, 1);
  const pad = { top: 8, right: 8, bottom: 16, left: 36 };
  const plotW = w - pad.left - pad.right;
  const plotH = h - pad.top - pad.bottom;
  const step = plotW / (sliced.length - 1);

  // Y轴网格线 + 标签
  ctx.textAlign = 'right';
  ctx.font = '10px sans-serif';
  ctx.strokeStyle = 'rgba(255,255,255,0.06)';
  ctx.lineWidth = 1;
  ctx.fillStyle = '#64748b';
  const ySteps = 4;
  for (let i = 0; i <= ySteps; i++) {
    const y = pad.top + (plotH / ySteps) * i;
    const val = Math.round(max - (max / ySteps) * i);
    ctx.beginPath();
    ctx.setLineDash([3, 3]);
    ctx.moveTo(pad.left, y);
    ctx.lineTo(w - pad.right, y);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillText(val, pad.left - 4, y + 3);
  }

  // 渐变填充
  const grad = ctx.createLinearGradient(0, pad.top, 0, h);
  grad.addColorStop(0, color + '66');
  grad.addColorStop(1, color + '00');
  ctx.beginPath();
  ctx.moveTo(pad.left, h - pad.bottom);
  sliced.forEach((v, i) => {
    ctx.lineTo(pad.left + i * step, pad.top + plotH - (v / max * plotH));
  });
  ctx.lineTo(pad.left + (sliced.length-1) * step, h - pad.bottom);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();

  // 折线
  ctx.beginPath();
  sliced.forEach((v, i) => {
    const x = pad.left + i * step;
    const y = pad.top + plotH - (v / max * plotH);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.stroke();

  // 数据点圆点
  sliced.forEach((v, i) => {
    const x = pad.left + i * step;
    const y = pad.top + plotH - (v / max * plotH);
    ctx.beginPath();
    ctx.arc(x, y, 2.5, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.strokeStyle = '#0c0f1e';
    ctx.lineWidth = 1;
    ctx.stroke();
  });

  // 存储数据供 tooltip 使用
  canvas._chartData = { sliced, max, step, pad, plotW, plotH, color, label: label || '' };
}

// 时间范围切换事件
document.querySelectorAll('.time-range').forEach(group => {
  group.addEventListener('click', function(e) {
    const btn = e.target.closest('.time-btn');
    if (!btn) return;
    this.querySelectorAll('.time-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const range = parseInt(btn.dataset.range);
    const key = this.id === 'danmakuRange' ? 'danmaku' : 'gift';
    chartState[key].maxRange = range;
    refreshMetrics();
  });
});

// 鼠标悬停 tooltip
document.addEventListener('mousemove', function(e) {
  ['danmakuChart','giftChart'].forEach(cid => {
    const canvas = document.getElementById(cid);
    const tid = cid === 'danmakuChart' ? 'danmakuTooltip' : 'giftTooltip';
    const tooltip = document.getElementById(tid);
    if (!canvas || !tooltip || !canvas._chartData) { if(tooltip) tooltip.style.display = 'none'; return; }
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const d = canvas._chartData;
    if (mx < 0 || mx > rect.width || my < 0 || my > rect.height) {
      tooltip.style.display = 'none'; return;
    }
    const idx = Math.round((mx - d.pad.left) / d.step);
    if (idx < 0 || idx >= d.sliced.length) { tooltip.style.display = 'none'; return; }
    const val = d.sliced[idx];
    tooltip.style.display = 'block';
    tooltip.style.left = (d.pad.left + idx * d.step + 8) + 'px';
    tooltip.style.top = Math.max(0, d.pad.top + d.plotH - (val / d.max * d.plotH) - 30) + 'px';
    tooltip.textContent = val + (d.label ? ' ' + d.label : '');
  });
});

function escapeHtml(s) { if(!s) return ''; const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }

function refreshLeaderboard() { fetch('/api/leaderboard?limit=10').then(r=>r.json()).then(d=>{ if(d.leaderboard) updateLeaderboard(d.leaderboard); }).catch(()=>{}); }
function refreshTierDist() { fetch('/api/admin/tier-dist').then(r=>r.json()).then(d=>{ if(d.dist) updateTierDist(d.dist); }).catch(()=>{}); }
function exportData() { window.open('/api/admin/export?format=json', '_blank'); }
function resetSession() { if(confirm('确认重置当前会话统计？')) fetch('/api/admin/reset-session', {method:'POST'}); }

// 启动
connect();
refreshMetrics();
setInterval(refreshMetrics, 5000);
setInterval(refreshLeaderboard, 10000);
setInterval(refreshTierDist, 30000);
</script>
</body>
</html>"""

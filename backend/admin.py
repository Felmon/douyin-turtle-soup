"""v6 控制面板 — 主播操作端

包含：游戏控制、礼物槽管理、难度切换、AI出题审核、实时数据。
"""
import json

ADMIN_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>海龟汤 · 控制台</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0c0f1e;color:#e2e8f0;font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;padding:16px;min-height:100vh}

.app{max-width:1400px;margin:0 auto;display:flex;flex-direction:column;gap:12px}

.header{display:flex;align-items:center;justify-content:space-between;padding:14px 20px;background:rgba(18,22,48,0.6);border-radius:12px;border:1px solid rgba(255,255,255,0.06)}
.header h1{font-size:18px;background:linear-gradient(135deg,#e2e8f0,#94a3b8);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.header-actions{display:flex;gap:8px}

.btn{padding:6px 14px;border:none;border-radius:8px;font-size:12px;font-weight:600;cursor:pointer;transition:all 0.2s;display:inline-flex;align-items:center;gap:5px}
.btn-primary{background:linear-gradient(135deg,#00d4ff,#7c3aed);color:#fff}
.btn-primary:hover{box-shadow:0 4px 16px rgba(0,212,255,0.35)}
.btn-ghost{background:rgba(255,255,255,0.05);color:#94a3b8}
.btn-ghost:hover{background:rgba(255,255,255,0.1);color:#e2e8f0}
.btn-success{background:#22c55e;color:#fff}
.btn-warning{background:#fbbf24;color:#000}
.btn-danger{background:#ef4444;color:#fff}
.btn-sm{padding:4px 10px;font-size:11px}

.tabs{display:flex;gap:4px;padding:4px;background:rgba(18,22,48,0.4);border-radius:10px;width:fit-content}
.tab{padding:8px 16px;border-radius:7px;font-size:13px;font-weight:600;cursor:pointer;color:#64748b;transition:all 0.2s}
.tab.active{background:rgba(0,212,255,0.15);color:#00d4ff}

.tab-content{display:none;background:rgba(18,22,48,0.6);border-radius:12px;border:1px solid rgba(255,255,255,0.06);padding:20px;min-height:500px}
.tab-content.active{display:block}

.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.grid-3{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}

.section{margin-bottom:20px}
.section h2{font-size:14px;color:#94a3b8;margin-bottom:10px;text-transform:uppercase;letter-spacing:1px;border-bottom:1px solid rgba(255,255,255,0.05);padding-bottom:6px}

.surface-preview{padding:16px;background:rgba(0,0,0,0.3);border-radius:8px;margin-bottom:12px;border-left:3px solid #00d4ff}
.surface-preview .label{font-size:10px;color:#64748b;letter-spacing:2px;margin-bottom:6px}
.surface-preview .text{font-size:14px;line-height:1.7;color:#e2e8f0}

.char-grid{display:flex;flex-wrap:wrap;gap:3px;padding:12px;background:rgba(0,0,0,0.3);border-radius:8px;max-height:300px;overflow-y:auto}
.char-cell{width:24px;height:30px;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:700;border-radius:3px;background:rgba(100,116,139,0.1)}
.char-cell.revealed{color:#00d4ff;text-shadow:0 0 8px rgba(0,212,255,0.3)}
.char-cell.hidden{color:transparent;background:rgba(100,116,139,0.25);position:relative}
.char-cell.hidden::after{content:'';position:absolute;width:60%;height:2px;background:rgba(100,116,139,0.4);border-radius:1px}
.char-cell.function{color:#64748b;font-size:11px}

.diff-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-bottom:12px}
.diff-btn{padding:12px;border:1px solid rgba(255,255,255,0.1);background:rgba(0,0,0,0.3);border-radius:8px;cursor:pointer;transition:all 0.2s;text-align:center}
.diff-btn:hover{border-color:#00d4ff;background:rgba(0,212,255,0.1)}
.diff-btn.active{border-color:#00d4ff;background:rgba(0,212,255,0.15);box-shadow:0 0 16px rgba(0,212,255,0.2)}
.diff-btn .name{font-size:14px;font-weight:700;color:#e2e8f0;margin-bottom:2px}
.diff-btn .range{font-size:10px;color:#64748b;margin-bottom:2px}
.diff-btn .multi{font-size:11px;color:#fbbf24;font-weight:600}

.slot-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}
.slot-card{padding:10px;background:rgba(0,0,0,0.3);border-radius:8px;border:1px solid rgba(255,255,255,0.05);position:relative;cursor:pointer;transition:all 0.2s}
.slot-card:hover{border-color:#00d4ff;background:rgba(0,212,255,0.05)}
.slot-card.disabled{opacity:0.4}
.slot-card .icon{width:40px;height:40px;border-radius:8px;background:rgba(100,116,139,0.2);margin:0 auto 6px;background-size:cover;background-position:center;display:flex;align-items:center;justify-content:center;font-size:20px}
.slot-card .name{font-size:11px;font-weight:600;color:#e2e8f0;text-align:center;margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.slot-card .desc{font-size:9px;color:#64748b;text-align:center;line-height:1.3}
.slot-card .group-tag{position:absolute;top:4px;right:4px;font-size:8px;padding:1px 5px;border-radius:4px;font-weight:600}
.group-tag.effect{background:rgba(251,191,36,0.2);color:#fbbf24}
.group-tag.difficulty{background:rgba(34,197,94,0.2);color:#22c55e}

.gift-picker{position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:200;display:flex;align-items:center;justify-content:center;padding:20px}
.gift-picker .modal{background:#0c0f1e;border:1px solid rgba(255,255,255,0.1);border-radius:12px;width:100%;max-width:600px;max-height:80vh;display:flex;flex-direction:column}
.gift-picker .header{padding:16px 20px;border-bottom:1px solid rgba(255,255,255,0.05)}
.gift-picker .search{padding:12px 20px;border-bottom:1px solid rgba(255,255,255,0.05)}
.gift-picker .search input{width:100%;padding:8px 12px;background:rgba(0,0,0,0.4);border:1px solid rgba(255,255,255,0.1);border-radius:6px;color:#e2e8f0;font-size:13px}
.gift-picker .body{flex:1;overflow-y:auto;padding:12px 20px;display:grid;grid-template-columns:repeat(5,1fr);gap:8px}
.gift-item{padding:8px;background:rgba(0,0,0,0.3);border-radius:6px;cursor:pointer;text-align:center;transition:all 0.15s}
.gift-item:hover{background:rgba(0,212,255,0.15);transform:translateY(-2px)}
.gift-item .icon{width:36px;height:36px;border-radius:6px;background-size:cover;background-position:center;margin:0 auto 4px;background-color:rgba(100,116,139,0.2)}
.gift-item .name{font-size:10px;color:#e2e8f0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gift-item .price{font-size:9px;color:#fbbf24}

.ai-soup-card{padding:12px;background:rgba(0,0,0,0.3);border-radius:8px;margin-bottom:8px;border-left:3px solid #7c3aed}
.ai-soup-card .meta{font-size:10px;color:#64748b;margin-bottom:4px}
.ai-soup-card .surface{font-size:13px;line-height:1.6;color:#e2e8f0;margin-bottom:4px}
.ai-soup-card .actions{display:flex;gap:6px;margin-top:8px}

.soup-list{max-height:400px;overflow-y:auto}
.soup-row{padding:10px 12px;background:rgba(0,0,0,0.2);border-radius:6px;margin-bottom:6px;display:flex;align-items:center;gap:12px;font-size:12px}
.soup-row .title{flex:1;color:#e2e8f0;font-weight:600}
.soup-row .meta{font-size:10px;color:#64748b}
.soup-row.selected{border-left:3px solid #00d4ff;background:rgba(0,212,255,0.1)}

input[type="text"], textarea, select{padding:8px 12px;background:rgba(0,0,0,0.4);border:1px solid rgba(255,255,255,0.1);border-radius:6px;color:#e2e8f0;font-size:13px;font-family:inherit}
input[type="text"]:focus, textarea:focus, select:focus{outline:none;border-color:#00d4ff}

textarea{width:100%;min-height:80px;resize:vertical}

.empty{text-align:center;padding:40px;color:#64748b;font-size:13px}

.metrics-row{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px}
.metric-card{padding:14px;background:rgba(0,0,0,0.3);border-radius:8px}
.metric-card .label{font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px}
.metric-card .val{font-size:24px;font-weight:900;color:#00d4ff}
.metric-card .val.gold{color:#fbbf24}
.metric-card .val.green{color:#22c55e}
.theme-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:8px}
.theme-card{background:rgba(0,0,0,0.3);border:2px solid rgba(255,255,255,0.06);border-radius:10px;padding:14px;cursor:pointer;transition:all 0.2s}
.theme-card:hover{border-color:rgba(0,212,255,0.4);transform:translateY(-2px)}
.theme-card.active{border-color:#00d4ff;box-shadow:0 0 20px rgba(0,212,255,0.3)}
.theme-card .preview{height:60px;border-radius:6px;margin-bottom:8px;border:1px solid rgba(255,255,255,0.05)}
.theme-card .name{font-size:14px;font-weight:700;color:#e2e8f0;margin-bottom:4px}
.theme-card .accent{display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:6px;vertical-align:middle}
.theme-card .btn{margin-top:8px;width:100%}
.chart-wrap{position:relative;height:140px}
.chart-tooltip{position:absolute;display:none;background:rgba(0,0,0,0.85);color:#e2e8f0;padding:6px 10px;border-radius:6px;font-size:11px;pointer-events:none;white-space:nowrap;z-index:10;border:1px solid rgba(255,255,255,0.1);backdrop-filter:blur(4px)}
canvas{max-width:100%}
</style>
</head>
<body>

<div class="app">
  <div class="header">
    <h1>🐢 海龟汤 · 主播控制台</h1>
    <div class="header-actions">
      <span class="btn btn-ghost" id="statusInfo">● 空闲中</span>
      <button class="btn btn-ghost" onclick="window.open('/overlay','_blank')">📺 投屏</button>
      <button class="btn btn-ghost" onclick="window.open('/dashboard','_blank')">📊 数据</button>
    </div>
  </div>

  <div class="tabs">
    <div class="tab active" data-tab="game">🎮 游戏控制</div>
    <div class="tab" data-tab="slots">🎁 礼物槽位</div>
    <div class="tab" data-tab="soup">📚 题库管理</div>
    <div class="tab" data-tab="ai">🤖 AI 出题</div>
    <div class="tab" data-tab="data">📈 数据</div>
    <div class="tab" data-tab="theme">🎨 主题</div>
  </div>

  <!-- 游戏控制 -->
  <div class="tab-content active" id="tab-game">
    <div class="grid-2">
      <div>
        <div class="section">
          <h2>游戏状态</h2>
          <div class="surface-preview">
            <div class="label">✦ 当前汤面</div>
            <div class="text" id="curSurface">等待开局</div>
          </div>
          <div style="display:flex;gap:8px;margin-bottom:12px">
            <button class="btn btn-primary" onclick="startGame()">▶ 开始新局</button>
            <button class="btn btn-warning" onclick="endGame()">⏭ 揭晓答案</button>
            <button class="btn btn-danger" onclick="resetGame()">⏹ 重置</button>
          </div>
        </div>

        <div class="section">
          <h2>难度选择（5档）</h2>
          <div class="diff-grid" id="diffGrid"></div>
          <div style="font-size:11px;color:#64748b;margin-top:6px">当前难度：<span id="curDiff" style="color:#00d4ff;font-weight:600">-</span></div>
          <div style="font-size:11px;color:#64748b;margin-top:4px">局数：<span id="adminRoundCount" style="color:#22c55e">0</span> &nbsp;|&nbsp; 时长：<span id="adminDuration" style="color:#22c55e">00:00</span></div>
        </div>
      </div>

      <div>
        <div class="section">
          <h2>谜底揭示</h2>
          <div class="char-grid" id="charGrid"></div>
          <div style="margin-top:8px;font-size:11px;color:#64748b">
            进度：<span id="progressText">0%</span>
            <div style="height:6px;background:rgba(100,116,139,0.2);border-radius:3px;margin-top:4px">
              <div id="progressBar" style="height:100%;background:linear-gradient(90deg,#00d4ff,#7c3aed);border-radius:3px;width:0%;transition:width 0.5s"></div>
            </div>
          </div>
        </div>

        <div class="section">
          <h2>操作日志 <button class="btn btn-ghost btn-sm" onclick="clearLog()" style="float:right">清空</button></h2>
          <div id="logList" style="max-height:200px;overflow-y:auto;background:rgba(0,0,0,0.3);border-radius:6px;padding:8px;font-size:11px;font-family:monospace;color:#94a3b8"></div>
        </div>
      </div>
    </div>
  </div>

  <!-- 礼物槽位 -->
  <div class="tab-content" id="tab-slots">
    <div class="section">
      <h2>10个固定槽位（5效果 + 5难度）</h2>
      <div style="font-size:11px;color:#64748b;margin-bottom:12px">点击槽位从368+抖音礼物中选择绑定。已选择的礼物在直播间送礼即触发对应效果。</div>
      <div class="slot-grid" id="slotGrid"></div>
    </div>
  </div>

  <!-- 题库管理 -->
  <div class="tab-content" id="tab-soup">
    <div class="section">
      <h2>题库浏览</h2>
      <div style="display:flex;gap:8px;margin-bottom:12px">
        <select id="filterDiff" onchange="loadSoupList()">
          <option value="">所有难度</option>
          <option value="easy">简单</option>
          <option value="medium">一般</option>
          <option value="hard">困难</option>
          <option value="hell">地狱</option>
          <option value="void">无人区</option>
        </select>
        <button class="btn btn-primary btn-sm" onclick="showAddSoup()">+ 新增题</button>
        <button class="btn btn-ghost btn-sm" onclick="importSoups()">📥 批量导入</button>
      </div>
      <div class="soup-list" id="soupList"></div>
    </div>
  </div>

  <!-- AI出题 -->
  <div class="tab-content" id="tab-ai">
    <div class="section">
      <h2>AI 出题（主）· 手动导入（辅）</h2>
      <div style="margin-bottom:12px">
        <button class="btn btn-primary" onclick="aiGenerate()">🤖 AI 生成 5 道新题</button>
        <span style="font-size:11px;color:#64748b;margin-left:8px">使用 DeepSeek 自动生成符合当前难度的题目，生成后人工审核入库</span>
      </div>
      <div id="aiPendingList"></div>
      <div id="aiBatchActions" style="display:none;margin-top:8px;display:flex;gap:8px">
        <button class="btn btn-success btn-sm" onclick="approveAllAi()">✓ 全部入库</button>
        <button class="btn btn-danger btn-sm" onclick="rejectAllAi()">✗ 全部废弃</button>
      </div>
    </div>
  </div>

  <!-- 数据 -->
  <div class="tab-content" id="tab-data">
    <div class="metrics-row">
      <div class="metric-card"><div class="label">本局积分总数</div><div class="val gold" id="mTotalScore">0</div></div>
      <div class="metric-card"><div class="label">本局弹幕数</div><div class="val green" id="mTotalDanmaku">0</div></div>
      <div class="metric-card"><div class="label">本局礼物数</div><div class="val" id="mTotalGifts">0</div></div>
      <div class="metric-card"><div class="label">付费用户数</div><div class="val gold" id="mPaidUsers">0</div></div>
      <div class="metric-card"><div class="label">本场局数</div><div class="val green" id="mRoundCount">0</div></div>
      <div class="metric-card"><div class="label">本场时长</div><div class="val" id="mSessionDuration">00:00</div></div>
      <div class="metric-card"><div class="label">答对率</div><div class="val gold" id="mAccuracy">0%</div></div>
    </div>
    <div class="grid-2" style="margin-bottom:16px">
      <div class="section">
        <h2>📈 弹幕趋势</h2>
        <div class="chart-wrap"><canvas id="adminDanmakuChart"></canvas><div class="chart-tooltip" id="adminDanmakuTooltip"></div></div>
      </div>
      <div class="section">
        <h2>🎁 礼物收入趋势</h2>
        <div class="chart-wrap"><canvas id="adminGiftChart"></canvas><div class="chart-tooltip" id="adminGiftTooltip"></div></div>
      </div>
    </div>
    <div class="section">
      <h2>最近 10 条礼物</h2>
      <div class="soup-list" id="recentGifts"></div>
    </div>
  </div>

  <!-- 主题 -->
  <div class="tab-content" id="tab-theme">
    <div class="section">
      <h2>当前主题</h2>
      <div id="themeGrid" class="theme-grid"></div>
    </div>
  </div>
</div>

<!-- 礼物选择器 -->
<div class="gift-picker" id="giftPicker" style="display:none">
  <div class="modal">
    <div class="header"><strong>选择礼物</strong> <span style="float:right;cursor:pointer;font-size:18px" onclick="closePicker()">×</span></div>
    <div class="search"><input type="text" id="giftSearchInput" placeholder="搜索礼物..." oninput="searchGifts(this.value)"></div>
    <div class="body" id="giftPickerBody"></div>
  </div>
</div>

<!-- 新增题弹窗 -->
<div class="gift-picker" id="addSoupModal" style="display:none">
  <div class="modal">
    <div class="header"><strong>新增题目</strong> <span style="float:right;cursor:pointer;font-size:18px" onclick="closeAddSoup()">×</span></div>
    <div style="padding:20px;display:flex;flex-direction:column;gap:10px">
      <input type="text" id="newSoupTitle" placeholder="题目标题（可留空）">
      <select id="newSoupDiff">
        <option value="easy">简单 (30-50字)</option>
        <option value="medium" selected>一般 (50-80字)</option>
        <option value="hard">困难 (80-100字)</option>
        <option value="hell">地狱 (100-120字)</option>
        <option value="void">无人区 (120-150字)</option>
      </select>
      <textarea id="newSoupSurface" placeholder="汤面（题目）"></textarea>
      <textarea id="newSoupBottom" placeholder="汤底（答案）"></textarea>
      <input type="text" id="newSoupKeywords" placeholder="关键词（逗号分隔）">
      <button class="btn btn-primary" onclick="submitNewSoup()">✓ 提交</button>
    </div>
  </div>
</div>

<script>
const wsUrl = (location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/ws';
let ws = null;
let currentSlots = [];
let currentSlotEditing = null;
let pendingAiSoups = [];
let selectedDiff = 'medium';

function connect() {
  if (ws) ws.close();
  ws = new WebSocket(wsUrl);
  ws.onopen = () => { console.log('[WS] 已连接'); };
  ws.onclose = () => setTimeout(connect, 3000);
  ws.onmessage = (e) => { try { handleMessage(JSON.parse(e.data)); } catch(err){} };
}

function handleMessage(msg) {
  switch(msg.type) {
    case 'state_sync': updateGameState(msg.room); break;
    case 'game_start': updateGameState({surface: msg.surface, charStates: msg.charStates, difficulty: msg.difficulty, phase: msg.phase || 'reading'}); break;
    case 'reveal_update': updateCharStates(msg.charStates); break;
    case 'game_end': document.getElementById('statusInfo').textContent='● 已结束'; break;
    case 'difficulty_scheduled': if(msg.nextDifficulty) updateGameState({difficulty: msg.nextDifficulty}); break;
    case 'classification': addLog(msg.user + ': ' + msg.text + ' -> ' + msg.answerType); break;
    case 'gift_effect': addLog('🎁 ' + msg.user + '送了' + msg.giftName); break;
    case 'tier_up': addLog('⬆ ' + msg.user + ' 升级到 ' + (msg.to_tier?.name||'')); break;
    case 'score_update': addLog('📊 ' + msg.user + ' 积分: ' + msg.score); break;
    case 'hint': addLog('💡 提示: ' + (msg.hint||'')); break;
    case 'slots_updated': loadSlots(); break;
    case 'metrics_update': updateMetrics(msg.metrics); break;
    case 'theme_change': loadThemes(); break;
  }
}

let metricsTimer = null;

function updateMetrics(m) {
  if (!m) return;
  document.getElementById('mTotalScore').textContent = m.totalScore ?? 0;
  document.getElementById('mTotalDanmaku').textContent = m.totalDanmaku ?? 0;
  document.getElementById('mTotalGifts').textContent = m.totalGifts ?? 0;
  document.getElementById('mPaidUsers').textContent = m.paid_users ?? 0;
  document.getElementById('mRoundCount').textContent = m.round_count ?? 0;
  const dur = m.session_duration || 0;
  document.getElementById('mSessionDuration').textContent = String(Math.floor(dur/60)).padStart(2,'0') + ':' + String(dur%60).padStart(2,'0');
  document.getElementById('mAccuracy').textContent = (m.accuracy||0) + '%';
  document.getElementById('adminRoundCount').textContent = m.round_count ?? 0;
  document.getElementById('adminDuration').textContent = String(Math.floor(dur/60)).padStart(2,'0') + ':' + String(dur%60).padStart(2,'0');

  if (m.danmaku_series) adminDrawChart('adminDanmakuChart', m.danmaku_series, '#00d4ff', '条/分');
  if (m.gift_series) adminDrawChart('adminGiftChart', m.gift_series, '#fbbf24', '抖币/分');

  // 最近礼物列表
  const list = document.getElementById('recentGifts');
  if (m.recentGifts && m.recentGifts.length > 0) {
    list.innerHTML = m.recentGifts.map(g =>
      '<div style="padding:6px 10px;background:rgba(0,0,0,0.2);border-radius:6px;margin-bottom:4px;font-size:12px;display:flex;justify-content:space-between">' +
      '<span>' + escapeHtml(g.user) + '</span>' +
      '<span>' + escapeHtml(g.gift_name) + '</span>' +
      '<span style="color:#fbbf24">' + (g.coins||0) + '抖币</span>' +
      '</div>'
    ).join('');
  } else {
    list.innerHTML = '<div class="empty">暂无礼物记录</div>';
  }
}

function adminDrawChart(id, data, color, label) {
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

  const sliced = data.slice(-60);
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
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + (plotH / 4) * i;
    const val = Math.round(max - (max / 4) * i);
    ctx.beginPath();
    ctx.setLineDash([3, 3]);
    ctx.moveTo(pad.left, y);
    ctx.lineTo(w - pad.right, y);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillText(val, pad.left - 4, y + 3);
  }

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

  ctx.beginPath();
  sliced.forEach((v, i) => {
    const x = pad.left + i * step;
    const y = pad.top + plotH - (v / max * plotH);
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.stroke();

  sliced.forEach((v, i) => {
    const x = pad.left + i * step;
    const y = pad.top + plotH - (v / max * plotH);
    ctx.beginPath(); ctx.arc(x, y, 2.5, 0, Math.PI * 2);
    ctx.fillStyle = color; ctx.fill();
    ctx.strokeStyle = '#0c0f1e'; ctx.lineWidth = 1; ctx.stroke();
  });

  canvas._chartData = { sliced, max, step, pad, plotH, color, label: label || '' };
}

async function refreshMetrics() {
  try {
    const data = await apiGet('/api/admin/metrics');
    updateMetrics(data);
  } catch(e) {}
}

function updateGameState(state) {
  if (state.surface) document.getElementById('curSurface').textContent = state.surface;
  if (state.charStates) updateCharStates(state.charStates);
  if (state.difficulty) {
    selectedDiff = state.difficulty;
    document.getElementById('curDiff').textContent = state.difficulty;
    refreshDiffGrid();
  }
  document.getElementById('statusInfo').textContent = '● ' + (state.phase || '空闲中');
}

function updateCharStates(states) {
  if (!states) return;
  const grid = document.getElementById('charGrid');
  grid.innerHTML = states.map(s => {
    let cls = 'char-cell';
    if (s.revealed) cls += ' revealed';
    else if (!s.isContent) cls += ' function';
    else cls += ' hidden';
    return '<div class="'+cls+'">'+escapeHtml(s.char)+'</div>';
  }).join('');
  const content = states.filter(s => s.isContent);
  const revealed = content.filter(s => s.revealed).length;
  const pct = content.length > 0 ? Math.round(revealed/content.length*100) : 0;
  document.getElementById('progressText').textContent = pct + '% (' + revealed + '/' + content.length + ')';
  document.getElementById('progressBar').style.width = pct + '%';
}

function refreshDiffGrid() {
  const diffs = [
    {id:'easy', name:'简单', range:'30-50字', multi:'×1.0'},
    {id:'medium', name:'一般', range:'50-80字', multi:'×1.5'},
    {id:'hard', name:'困难', range:'80-100字', multi:'×2.0'},
    {id:'hell', name:'地狱', range:'100-120字', multi:'×3.0'},
    {id:'void', name:'无人区', range:'120-150字', multi:'×5.0'},
  ];
  document.getElementById('diffGrid').innerHTML = diffs.map(d =>
    '<div class="diff-btn '+ (selectedDiff===d.id?'active':'') +'" onclick="setDiff(\''+d.id+'\')"><div class="name">'+d.name+'</div><div class="range">'+d.range+'</div><div class="multi">'+d.multi+'</div></div>'
  ).join('');
}

function setDiff(d) {
  selectedDiff = d;
  refreshDiffGrid();
  document.getElementById('curDiff').textContent = d;
  apiPost('/api/admin/difficulty', {difficulty: d});
}

function startGame() {
  apiPost('/api/game/start', {difficulty: selectedDiff});
}
function endGame() {
  if (!confirm('确认揭晓完整答案？')) return;
  apiPost('/api/admin/force-reveal', {});
}
function resetGame() {
  if (!confirm('确认重置游戏？当前进度将清空。')) return;
  apiPost('/api/admin/reset', {});
}

function addLog(msg) {
  const list = document.getElementById('logList');
  const time = new Date().toLocaleTimeString();
  list.innerHTML = '<div>[' + time + '] ' + escapeHtml(msg) + '</div>' + list.innerHTML;
  while (list.children.length > 100) list.removeChild(list.lastChild);
}
function clearLog() { document.getElementById('logList').innerHTML = ''; }

async function loadSlots() {
  const data = await apiGet('/api/admin/slots');
  currentSlots = data.slots || [];
  renderSlots();
}

function renderSlots() {
  document.getElementById('slotGrid').innerHTML = currentSlots.map(s =>
    '<div class="slot-card ' + (s.enabled?'':'disabled') + '" onclick="editSlot(\''+s.id+'\')">' +
    '<div class="group-tag ' + s.group + '">' + (s.group==='effect'?'效果':'难度') + '</div>' +
    '<div class="icon" style="background-image:url('+ (s.gift_icon||'') +')">' + (s.gift_icon?'':'🎁') + '</div>' +
    '<div class="name">' + escapeHtml(s.gift_name||'未绑定') + '</div>' +
    '<div class="desc">' + escapeHtml(s.name) + '<br>' + escapeHtml(s.desc) + '</div>' +
    '</div>'
  ).join('');
}

function editSlot(slotId) {
  currentSlotEditing = slotId;
  document.getElementById('giftPicker').style.display = 'flex';
  searchGifts('');
}
// 礼物选择器使用事件委托代替 onclick（防XSS）
document.getElementById('giftPickerBody').addEventListener('click', function(e) {
  const item = e.target.closest('.gift-item');
  if (item && item.dataset.giftName) pickGift(item.dataset.giftName);
});
function closePicker() { document.getElementById('giftPicker').style.display = 'none'; currentSlotEditing = null; }

async function searchGifts(query) {
  const data = await apiGet('/api/admin/gifts/search?q=' + encodeURIComponent(query));
  const body = document.getElementById('giftPickerBody');
  body.innerHTML = (data.gifts || []).map(g =>
    '<div class="gift-item" data-gift-name="' + escapeHtml(g.name) + '">' +
    '<div class="icon" style="background-image:url('+ (g.icon||'') +')"></div>' +
    '<div class="name">' + escapeHtml(g.name) + '</div>' +
    '<div class="price">' + g.coins + '抖币</div>' +
    '</div>'
  ).join('');
  if (!data.gifts || data.gifts.length === 0) body.innerHTML = '<div class="empty">未找到礼物</div>';
}

async function pickGift(name) {
  if (!currentSlotEditing) return;
  await apiPost('/api/admin/slots/assign', {slot_id: currentSlotEditing, gift_name: name});
  closePicker();
  loadSlots();
}

async function loadSoupList() {
  const diff = document.getElementById('filterDiff').value;
  const data = await apiGet('/api/admin/soups?difficulty=' + diff);
  document.getElementById('soupList').innerHTML = (data.soups||[]).map(s =>
    '<div class="soup-row">' +
    '<div class="title">'+escapeHtml(s.title||s.surface?.slice(0,20))+'</div>' +
    '<div class="meta">'+ (s.difficulty||'') +' | '+ (s.answer_length||0) +'字</div>' +
    '<button class="btn btn-ghost btn-sm" onclick="useSoup(\''+s.id+'\')">使用</button>' +
    '<button class="btn btn-danger btn-sm" onclick="deleteSoup(\''+s.id+'\')">删</button>' +
    '</div>'
  ).join('') || '<div class="empty">暂无题目</div>';
}

async function useSoup(id) { await apiPost('/api/game/start', {soup_id: id}); }
async function deleteSoup(id) { if (confirm('确认删除？')) { await apiPost('/api/admin/soups/delete', {id: id}); loadSoupList(); } }

function showAddSoup() { document.getElementById('addSoupModal').style.display = 'flex'; }
function closeAddSoup() { document.getElementById('addSoupModal').style.display = 'none'; }
async function submitNewSoup() {
  const soup = {
    title: document.getElementById('newSoupTitle').value,
    surface: document.getElementById('newSoupSurface').value,
    bottom: document.getElementById('newSoupBottom').value,
    keywords: document.getElementById('newSoupKeywords').value.split(/[,，]/).map(s=>s.trim()).filter(Boolean),
    difficulty: document.getElementById('newSoupDiff').value,
  };
  if (!soup.surface || !soup.bottom) { alert('汤面和汤底必填'); return; }
  await apiPost('/api/admin/soups/add', soup);
  closeAddSoup();
  loadSoupList();
}

async function importSoups() {
  const json = prompt('粘贴JSON数组: [{surface, bottom, keywords, difficulty}]');
  if (!json) return;
  try {
    const arr = JSON.parse(json);
    if (!Array.isArray(arr)) throw new Error('需为数组');
    await apiPost('/api/admin/soups/import', {soups: arr});
    loadSoupList();
    alert('已导入 ' + arr.length + ' 道题');
  } catch(e) { alert('格式错误: ' + e.message); }
}

async function aiGenerate() {
  document.getElementById('aiPendingList').innerHTML = '<div class="empty">AI生成中...</div>';
  const data = await apiPost('/api/admin/ai-generate', {difficulty: selectedDiff, count: 5});
  pendingAiSoups = data.soups || [];
  renderAiPending();
}

function renderAiPending() {
  document.getElementById('aiPendingList').innerHTML = pendingAiSoups.map((s, i) =>
    '<div class="ai-soup-card">' +
    '<div class="meta">[' + s.difficulty + '] 字数: ' + s.answer_length + '</div>' +
    '<div class="surface">汤面：' + escapeHtml(s.surface) + '</div>' +
    '<div class="surface" style="color:#94a3b8;font-size:11px">汤底：' + escapeHtml(s.bottom) + '</div>' +
    '<div class="actions">' +
    '<button class="btn btn-success btn-sm" onclick="approveAi('+i+')">✓ 入库</button>' +
    '<button class="btn btn-danger btn-sm" onclick="rejectAi('+i+')">✗ 废弃</button>' +
    '</div>' +
    '</div>'
  ).join('') || '<div class="empty">暂无待审核</div>';
}

async function approveAi(idx) {
  await apiPost('/api/admin/ai-approve', {soup: pendingAiSoups[idx]});
  pendingAiSoups.splice(idx, 1);
  renderAiPending();
}
async function rejectAi(idx) {
  pendingAiSoups.splice(idx, 1);
  renderAiPending();
}
async function approveAllAi() {
  if (!confirm('确认全部入库 ' + pendingAiSoups.length + ' 道题？')) return;
  const soups = [...pendingAiSoups];
  for (const s of soups) { await apiPost('/api/admin/ai-approve', {soup: s}); }
  pendingAiSoups = [];
  renderAiPending();
  addLog('批量入库 ' + soups.length + ' 道题');
}
async function rejectAllAi() {
  if (!confirm('确认全部废弃 ' + pendingAiSoups.length + ' 道题？')) return;
  const c = pendingAiSoups.length;
  pendingAiSoups = [];
  renderAiPending();
  addLog('批量废弃 ' + c + ' 道题');
}

async function apiGet(path) {
  try {
    const r = await fetch(path);
    if (!r.ok) return {};
    return await r.json();
  } catch(e) { return {}; }
}
async function apiPost(path, body) {
  try {
    const r = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
    if (!r.ok) return {};
    return await r.json();
  } catch(e) { return {}; }
}

function escapeHtml(s) { if(!s) return ''; const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }

// Tabs
document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => {
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(x=>x.classList.remove('active'));
  t.classList.add('active');
  document.getElementById('tab-'+t.dataset.tab).classList.add('active');
  if (t.dataset.tab==='slots') loadSlots();
  if (t.dataset.tab==='soup') loadSoupList();
  if (t.dataset.tab==='theme') loadThemes();
  // 数据 tab 启动轮询
  if (t.dataset.tab==='data') {
    refreshMetrics();
    metricsTimer = setInterval(refreshMetrics, 5000);
  } else if (metricsTimer) {
    clearInterval(metricsTimer);
    metricsTimer = null;
  }
}));

// 鼠标悬停 tooltip（admin 数据 tab 图表）
document.addEventListener('mousemove', function(e) {
  ['adminDanmakuChart','adminGiftChart'].forEach(cid => {
    const canvas = document.getElementById(cid);
    const tid = cid === 'adminDanmakuChart' ? 'adminDanmakuTooltip' : 'adminGiftTooltip';
    const tooltip = document.getElementById(tid);
    if (!canvas || !tooltip || !canvas._chartData) { if(tooltip) tooltip.style.display = 'none'; return; }
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const d = canvas._chartData;
    if (mx < 0 || mx > rect.width || my < 0 || my > rect.height) { tooltip.style.display = 'none'; return; }
    const idx = Math.round((mx - d.pad.left) / d.step);
    if (idx < 0 || idx >= d.sliced.length) { tooltip.style.display = 'none'; return; }
    const val = d.sliced[idx];
    tooltip.style.display = 'block';
    tooltip.style.left = (d.pad.left + idx * d.step + 8) + 'px';
    tooltip.style.top = Math.max(0, d.pad.top + d.plotH - (val / d.max * d.plotH) - 30) + 'px';
    tooltip.textContent = val + (d.label ? ' ' + d.label : '');
  });
});

// 每分钟刷新游戏面板统计（局数/时长）
setInterval(refreshMetrics, 60000);

// 启动
connect();
refreshDiffGrid();

async function loadThemes() {
  const data = await apiGet('/api/admin/themes');
  const grid = document.getElementById('themeGrid');
  if (!data.themes) return;
  const current = await apiGet('/api/theme');
  grid.innerHTML = data.themes.map(t => {
    const isActive = t.id === current.theme_id;
    return '<div class="theme-card' + (isActive ? ' active' : '') + '" data-theme-id="' + escapeHtml(t.id) + '">' +
      '<div class="preview" style="background:' + t.preview + '"></div>' +
      '<div class="name"><span class="accent" style="background:' + t.accent + '"></span>' + escapeHtml(t.name) + (isActive ? ' ✓' : '') + '</div>' +
      '<button class="btn btn-primary btn-sm">应用</button>' +
      '</div>';
  }).join('');
  grid.querySelectorAll('.theme-card').forEach(card => {
    card.addEventListener('click', () => applyTheme(card.dataset.themeId));
  });
}

async function applyTheme(id) {
  const res = await apiPost('/api/admin/theme', {theme_id: id});
  if (res.ok) {
    addLog('🎨 主题已切换: ' + id);
    loadThemes();
  } else {
    addLog('❌ 主题切换失败: ' + (res.error || ''));
  }
}
</script>
</body>
</html>"""

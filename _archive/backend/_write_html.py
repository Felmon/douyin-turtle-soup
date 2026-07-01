import sys, os
sys.stdout.reconfigure(encoding="utf-8")

html = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CCcat 海龟汤 🐢</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    background: #0a0a1a;
    color: #e0e0e0;
    min-height: 100vh;
    overflow-x: hidden;
  }
  body::before {
    content: "";
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: radial-gradient(ellipse at 20% 50%, rgba(0,100,255,0.08) 0%, transparent 50%),
                radial-gradient(ellipse at 80% 50%, rgba(100,0,255,0.05) 0%, transparent 50%);
    pointer-events: none;
    z-index: 0;
  }
  .app { position: relative; z-index: 1; min-height: 100vh; display: flex; flex-direction: column; }
  .header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 16px 24px;
    background: rgba(20,20,40,0.7);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border-bottom: 1px solid rgba(255,255,255,0.06);
  }
  .header-title {
    font-size: 22px; font-weight: 700;
    background: linear-gradient(135deg, #64b5f6, #7c4dff);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }
  .header-status { display: flex; align-items: center; gap: 8px; font-size: 13px; color: #888; }
  .status-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
  .status-dot.online { background: #4caf50; box-shadow: 0 0 6px #4caf5066; }
  .status-dot.offline { background: #f44336; box-shadow: 0 0 6px #f4433666; }
  .status-dot.connecting { background: #ff9800; box-shadow: 0 0 6px #ff980066; animation: pulse 1s infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
  .main {
    display: flex; flex: 1; padding: 20px; gap: 20px;
    max-width: 1400px; margin: 0 auto; width: 100%;
  }
  .game-panel { flex: 7; display: flex; flex-direction: column; gap: 16px; }
  .qa-panel { flex: 3; min-width: 280px; max-width: 360px; }
  .card {
    background: rgba(20,20,40,0.6); backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; padding: 20px;
    transition: border-color 0.3s;
  }
  .card:hover { border-color: rgba(255,255,255,0.12); }
  .card-title {
    font-size: 13px; color: #888; text-transform: uppercase;
    letter-spacing: 1.5px; margin-bottom: 12px; font-weight: 600;
  }
  .surface-text { font-size: 16px; line-height: 1.8; color: #c0c0e0; }
  .reveal-area {
    font-size: 20px; line-height: 1.9; letter-spacing: 2px;
    word-break: break-all; min-height: 60px;
  }
  .reveal-area .char-hidden {
    color: transparent;
    background: linear-gradient(135deg, #2a2a4a, #3a3a5a);
    border-radius: 3px; padding: 0 2px; position: relative;
    display: inline-block; min-width: 1.2em; text-align: center;
  }
  .reveal-area .char-hidden::after {
    content: "\\2593";
    color: #6666aa; position: absolute; left: 0; right: 0; text-align: center;
  }
  .reveal-area .char-revealed { color: #e0e0ff; }
  .reveal-area .char-function { color: #8888aa; }
  .progress-section { display: flex; align-items: center; gap: 12px; }
  .progress-bar {
    flex: 1; height: 6px; background: rgba(255,255,255,0.06);
    border-radius: 3px; overflow: hidden;
  }
  .progress-fill {
    height: 100%; background: linear-gradient(90deg, #64b5f6, #7c4dff);
    border-radius: 3px; transition: width 0.5s ease;
  }
  .progress-text { font-size: 13px; color: #888; min-width: 45px; text-align: right; }
  .controls { display: flex; gap: 10px; flex-wrap: wrap; }
  .btn {
    padding: 10px 20px; border: 1px solid rgba(255,255,255,0.1); border-radius: 10px;
    background: rgba(255,255,255,0.04); color: #c0c0e0; font-size: 14px;
    cursor: pointer; transition: all 0.2s; display: flex; align-items: center; gap: 6px;
    font-family: inherit;
  }
  .btn:hover {
    background: rgba(255,255,255,0.08); border-color: rgba(255,255,255,0.2);
    transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  }
  .btn:active { transform: translateY(0); }
  .btn-primary {
    background: linear-gradient(135deg, #1a237e, #283593);
    border-color: #3f51b5; color: #fff;
  }
  .btn-primary:hover { background: linear-gradient(135deg, #283593, #3949ab); }
  .btn-gift-pop { border-color: #ff6f00; color: #ffab00; }
  .btn-gift-pop:hover { background: rgba(255,111,0,0.1); border-color: #ffab00; }
  .btn-gift-beer { border-color: #00bcd4; color: #4dd0e1; }
  .btn-gift-beer:hover { background: rgba(0,188,212,0.1); border-color: #4dd0e1; }
  .btn-gift-sunglasses { border-color: #e040fb; color: #ea80fc; }
  .btn-gift-sunglasses:hover { background: rgba(224,64,251,0.1); border-color: #ea80fc; }
  .btn:disabled { opacity: 0.4; cursor: not-allowed; transform: none !important; }
  .qa-panel .card { height: 100%; display: flex; flex-direction: column; }
  .qa-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; min-height: 0; }
  .qa-list::-webkit-scrollbar { width: 4px; }
  .qa-list::-webkit-scrollbar-track { background: transparent; }
  .qa-list::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 2px; }
  .qa-bubble {
    padding: 10px 14px; border-radius: 12px; background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.05); animation: bubbleIn 0.3s ease;
  }
  @keyframes bubbleIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
  .qa-bubble .qa-user { font-size: 12px; color: #6666aa; margin-bottom: 4px; }
  .qa-bubble .qa-text { font-size: 14px; color: #c0c0e0; }
  .qa-bubble .qa-result { display: inline-block; margin-top: 6px; padding: 2px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; }
  .qa-result.yes, .qa-result.shi { background: rgba(76,175,80,0.15); color: #4caf50; border: 1px solid rgba(76,175,80,0.3); }
  .qa-result.no, .qa-result.bushi { background: rgba(244,67,54,0.15); color: #f44336; border: 1px solid rgba(244,67,54,0.3); }
  .qa-result.maybe, .qa-result.shiyebushi { background: rgba(255,152,0,0.15); color: #ff9800; border: 1px solid rgba(255,152,0,0.3); }
  .qa-result.irrelevant { background: rgba(158,158,158,0.15); color: #9e9e9e; border: 1px solid rgba(158,158,158,0.3); }
  .qa-empty { flex: 1; display: flex; align-items: center; justify-content: center; color: #555; font-size: 14px; }
  .overlay {
    display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.7); backdrop-filter: blur(8px); z-index: 100;
    justify-content: center; align-items: center;
  }
  .overlay.show { display: flex; }
  .overlay-content {
    background: rgba(20,20,40,0.9); border: 1px solid rgba(255,255,255,0.1);
    border-radius: 20px; padding: 40px 50px; text-align: center; max-width: 500px;
  }
  .overlay-content h2 {
    font-size: 28px;
    background: linear-gradient(135deg, #ffd54f, #ff6f00);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    margin-bottom: 12px;
  }
  .overlay-content p { color: #aaa; margin-bottom: 20px; }
  .toast {
    position: fixed; top: 80px; left: 50%; transform: translateX(-50%);
    background: rgba(20,20,40,0.9); backdrop-filter: blur(12px);
    border: 1px solid rgba(255,255,255,0.1); border-radius: 12px;
    padding: 12px 24px; color: #e0e0e0; font-size: 14px; z-index: 50;
    animation: toastIn 0.3s ease, toastOut 0.3s ease 2.5s forwards;
    pointer-events: none;
  }
  @keyframes toastIn { from { opacity: 0; transform: translateX(-50%) translateY(-10px); } to { opacity: 1; transform: translateX(-50%) translateY(0); } }
  @keyframes toastOut { from { opacity: 1; } to { opacity: 0; transform: translateX(-50%) translateY(-10px); } }
  .empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 40px; color: #555; text-align: center; }
  .empty-state .icon { font-size: 48px; margin-bottom: 16px; }
  @media (max-width: 800px) {
    .main { flex-direction: column; }
    .qa-panel { min-width: unset; max-width: unset; }
    .qa-list { max-height: 200px; }
  }
</style>
</head>
<body>
<div class="app">
  <header class="header">
    <div class="header-title">CCcat 海龟汤 \U0001f422</div>
    <div class="header-status">
      <span class="status-dot offline" id="statusDot"></span>
      <span id="statusText">未连接</span>
    </div>
  </header>
  <div class="main">
    <div class="game-panel">
      <div class="card" id="surfaceCard">
        <div class="card-title">\U0001f372 汤面</div>
        <div class="surface-text" id="surfaceText">
          <div class="empty-state">
            <div class="icon">\U0001f422</div>
            <p>点击「开始游戏」进入海龟汤推理之旅</p>
          </div>
        </div>
      </div>
      <div class="card" id="revealCard" style="display:none">
        <div class="card-title">\U0001f50d 逐字揭示</div>
        <div class="reveal-area" id="revealArea"></div>
      </div>
      <div class="card" id="progressCard" style="display:none">
        <div class="progress-section">
          <span style="font-size:13px;color:#888">揭示进度</span>
          <div class="progress-bar"><div class="progress-fill" id="progressFill" style="width:0%"></div></div>
          <span class="progress-text" id="progressText">0%</span>
        </div>
      </div>
      <div class="controls">
        <button class="btn btn-primary" id="btnStart" onclick="startGame()">\U0001f3ae 开始游戏</button>
        <button class="btn btn-gift-pop" id="btnPop" onclick="sendGift('\u4eba\u6c14\u7968')" disabled>\u2b50 \u4eba\u6c14\u7968</button>
        <button class="btn btn-gift-beer" id="btnBeer" onclick="sendGift('\u5564\u9152')" disabled>\U0001f37a \u5564\u9152</button>
        <button class="btn btn-gift-sunglasses" id="btnSunglasses" onclick="sendGift('\u58a8\u955c')" disabled>\U0001f576\ufe0f \u58a8\u955c</button>
      </div>
    </div>
    <div class="qa-panel">
      <div class="card" style="height:100%">
        <div class="card-title">\U0001f4ac 问答记录</div>
        <div class="qa-list" id="qaList">
          <div class="qa-empty">等待游戏开始...</div>
        </div>
      </div>
    </div>
  </div>
</div>
<div class="overlay" id="gameOverOverlay">
  <div class="overlay-content">
    <h2>\U0001f389 恭喜通关！</h2>
    <p id="gameOverText">所有谜底已经揭晓！</p>
    <button class="btn btn-primary" onclick="closeOverlay(); startGame();">再来一局</button>
  </div>
</div>

<script>
(function() {
  'use strict';
  var WS_URL = 'ws://localhost:3010/ws';
  var ws = null;
  var pingInterval = null;
  var gamePhase = 'idle';
  var charStates = [];
  var statusDot = document.getElementById('statusDot');
  var statusText = document.getElementById('statusText');
  var surfaceText = document.getElementById('surfaceText');
  var revealArea = document.getElementById('revealArea');
  var revealCard = document.getElementById('revealCard');
  var progressCard = document.getElementById('progressCard');
  var progressFill = document.getElementById('progressFill');
  var progressText = document.getElementById('progressText');
  var qaList = document.getElementById('qaList');
  var btnStart = document.getElementById('btnStart');
  var btnPop = document.getElementById('btnPop');
  var btnBeer = document.getElementById('btnBeer');
  var btnSunglasses = document.getElementById('btnSunglasses');
  var overlay = document.getElementById('gameOverOverlay');
  var gameOverText = document.getElementById('gameOverText');

  function setStatus(state) {
    statusDot.className = 'status-dot ' + state;
    var labels = { online: '\u5df2\u8fde\u63a5', offline: '\u672a\u8fde\u63a5', connecting: '\u8fde\u63a5\u4e2d...' };
    statusText.textContent = labels[state] || state;
  }

  function showToast(msg) {
    var el = document.createElement('div');
    el.className = 'toast';
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(function() { el.remove(); }, 3000);
  }

  function connectWS() {
    if (ws) { ws.close(); ws = null; }
    setStatus('connecting');
    try {
      ws = new WebSocket(WS_URL);
    } catch(e) {
      setStatus('offline');
      setTimeout(connectWS, 3000);
      return;
    }
    ws.onopen = function() {
      setStatus('online');
      stopPing();
      startPing();
    };
    ws.onmessage = function(event) {
      try {
        handleMessage(JSON.parse(event.data));
      } catch(e) {
        console.error('WS parse error:', e);
      }
    };
    ws.onclose = function() {
      setStatus('offline');
      stopPing();
      setTimeout(connectWS, 3000);
    };
    ws.onerror = function() { setStatus('offline'); };
  }

  function startPing() {
    stopPing();
    pingInterval = setInterval(function() {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }));
      }
    }, 5000);
  }

  function stopPing() {
    if (pingInterval) { clearInterval(pingInterval); pingInterval = null; }
  }

  function sendMsg(obj) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(obj));
      return true;
    }
    showToast('\u8fde\u63a5\u672a\u5efa\u7acb\uff0c\u8bf7\u7b49\u5f85...');
    return false;
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function renderReveal(states) {
    var html = '';
    for (var i = 0; i < states.length; i++) {
      var s = states[i];
      if (s.revealed) {
        if (s.isContent) {
          html += '<span class="char-revealed">' + escapeHtml(s.char) + '</span>';
        } else {
          html += '<span class="char-function">' + escapeHtml(s.char) + '</span>';
        }
      } else {
        html += '<span class="char-hidden"></span>';
      }
    }
    revealArea.innerHTML = html;
  }

  function updateProgress(states) {
    var total = 0, revealed = 0;
    for (var i = 0; i < states.length; i++) {
      if (states[i].isContent) { total++; if (states[i].revealed) revealed++; }
    }
    var pct = total === 0 ? 0 : Math.round(revealed / total * 100);
    progressFill.style.width = pct + '%';
    progressText.textContent = pct + '%';
  }

  function handleMessage(msg) {
    switch (msg.type) {
      case 'game_start':
        gamePhase = 'playing';
        charStates = msg.charStates || [];
        surfaceText.innerHTML = '<p>' + escapeHtml(msg.surface) + '</p>';
        revealCard.style.display = 'block';
        progressCard.style.display = 'block';
        renderReveal(charStates);
        updateProgress(charStates);
        qaList.innerHTML = '';
        btnPop.disabled = false;
        btnBeer.disabled = false;
        btnSunglasses.disabled = false;
        btnStart.textContent = '\U0001f504 \u91cd\u65b0\u5f00\u59cb';
        overlay.classList.remove('show');
        showToast('\u6e38\u620f\u5f00\u59cb\uff01\u731c\u731c\u771f\u76f8\u662f\u4ec0\u4e48\uff1f');
        btnStart.disabled = false;
        break;
      case 'reveal_update':
        if (msg.charStates) {
          charStates = msg.charStates;
          renderReveal(charStates);
          updateProgress(charStates);
        }
        break;
      case 'classification':
        var rc = '', rl = msg.answerType || '';
        switch (msg.answerType) {
          case '\u662f': rc = 'shi'; break;
          case '\u4e0d\u662f': rc = 'bushi'; break;
          case '\u662f\u4e5f\u4e0d\u662f': rc = 'shiyebushi'; break;
          case '\u4e0d\u76f8\u5173': rc = 'irrelevant'; break;
          default: rc = 'irrelevant';
        }
        var bub = document.createElement('div');
        bub.className = 'qa-bubble';
        bub.innerHTML = '<div class="qa-user">' + escapeHtml(msg.user || '\u89c2\u4f17') + '</div><div class="qa-text">' + escapeHtml(msg.text || '') + '</div><span class="qa-result ' + rc + '">' + escapeHtml(rl) + '</span>';
        qaList.insertBefore(bub, qaList.firstChild);
        var empty = qaList.querySelector('.qa-empty');
        if (empty) empty.remove();
        while (qaList.children.length > 50) { qaList.removeChild(qaList.lastChild); }
        break;
      case 'game_end':
        gamePhase = 'completed';
        if (msg.charStates) { charStates = msg.charStates; renderReveal(charStates); updateProgress(charStates); }
        btnPop.disabled = true;
        btnBeer.disabled = true;
        btnSunglasses.disabled = true;
        gameOverText.textContent = (msg.winner ? '\u611f\u8c22 ' + escapeHtml(msg.winner) + ' \u7684\u5e2e\u52a9\uff01' : '') + '\u6240\u6709\u8c1c\u5e95\u5df2\u7ecf\u63ed\u6653\uff01';
        overlay.classList.add('show');
        break;
      case 'gift_effect':
        if (msg.script) showToast(msg.script);
        break;
    }
  }

  window.startGame = function() {
    if (sendMsg({ type: 'start_round', nickname: '\u4e3b\u64ad' })) {
      btnStart.disabled = true;
      btnStart.textContent = '\u23f3 \u52a0\u8f7d\u4e2d...';
      setTimeout(function() { btnStart.disabled = false; }, 5000);
    }
  };

  window.sendGift = function(giftName) {
    if (gamePhase !== 'playing') { showToast('\u6e38\u620f\u8fdb\u884c\u4e2d\u624d\u80fd\u9001\u793c\u7269\u54e6'); return; }
    sendMsg({ type: 'gift', giftName: giftName, nickname: '\u89c2\u4f17' });
  };

  window.closeOverlay = function() { overlay.classList.remove('show'); };

  setStatus('offline');
  connectWS();
})();
</script>
</body>
</html>"""

out = "C:/Users/27871/OneDrive/Documents/抖音海龟汤/backend/embedded.html"
with open(out, "w", encoding="utf-8") as f:
    f.write(html)

print(f"HTML written: {len(html)} chars")

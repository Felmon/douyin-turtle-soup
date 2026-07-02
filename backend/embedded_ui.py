"""嵌入式游戏 UI — Meoo 风格"""
import json

EMBEDDED_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>CCcat 海龟汤</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0c0f1e;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;min-height:100vh;overflow:hidden;position:relative}
#particleCanvas{position:fixed;inset:0;pointer-events:none;z-index:0;opacity:0.5}
.app{position:relative;z-index:1;height:100vh;display:flex;flex-direction:column;padding:12px 16px;max-width:1280px;margin:0 auto;gap:10px}

/* ── Glass Card ── */
.glass{border-radius:12px;border:1px solid rgba(255,255,255,0.06);background:rgba(12,15,30,0.6);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);transition:all 0.3s}
.glass-primary{border-color:rgba(0,212,255,0.2);background:rgba(0,212,255,0.04);box-shadow:0 0 30px rgba(0,212,255,0.08)}
.glass .shine{position:absolute;inset:0;background:linear-gradient(135deg,rgba(255,255,255,0.04) 0%,transparent 50%);pointer-events:none;border-radius:inherit}

/* ── Header ── */
header{display:flex;align-items:center;justify-content:space-between;padding:12px 20px;flex-shrink:0;position:relative;overflow:hidden}
.header-left{display:flex;align-items:center;gap:12px}
.header-icon{width:40px;height:40px;border-radius:12px;background:linear-gradient(135deg,#00d4ff,#7c3aed);display:flex;align-items:center;justify-content:center;font-size:22px;box-shadow:0 4px 16px rgba(0,212,255,0.25)}
.header-title{font-size:18px;font-weight:700;background:linear-gradient(135deg,#e2e8f0,#94a3b8);-webkit-background-clip:text;-webkit-text-fill-color:transparent;line-height:1.2}
.header-sub{font-size:11px;color:#64748b;-webkit-text-fill-color:#64748b}
.header-status{display:flex;align-items:center;gap:6px;font-size:12px;color:#64748b}
.dot{width:7px;height:7px;border-radius:50%;display:inline-block}
.dot.on{background:#22c55e;box-shadow:0 0 8px #22c55e;animation:pulse-dot 2s infinite}
.dot.off{background:#ef4444}

/* ── Controls ── */
.controls{display:flex;align-items:center;justify-content:space-between;padding:8px 12px;flex-shrink:0;position:relative;overflow:hidden}
.controls-left{display:flex;align-items:center;gap:8px}
.phase-dot{width:8px;height:8px;border-radius:50%}
.phase-dot.idle{background:#64748b}
.phase-dot.playing{background:#22c55e;animation:pulse-dot 2s infinite}
.phase-dot.reading{background:#00d4ff;animation:pulse-dot 1.5s infinite}
.phase-dot.complete{background:#f59e0b}
.phase-label{font-size:13px;font-weight:500;color:#94a3b8}
.controls-right{display:flex;align-items:center;gap:6px}
.btn{display:inline-flex;align-items:center;gap:6px;padding:6px 14px;border:none;border-radius:8px;font-size:12px;font-weight:600;cursor:pointer;transition:all 0.2s;white-space:nowrap}
.btn:hover{transform:translateY(-1px)}
.btn:active{transform:translateY(0)}
.btn-primary{background:linear-gradient(135deg,#00d4ff,#7c3aed);color:#fff;box-shadow:0 2px 10px rgba(0,212,255,0.2)}
.btn-primary:hover{box-shadow:0 4px 16px rgba(0,212,255,0.35)}
.btn-ghost{background:transparent;color:#64748b;padding:6px 8px}
.btn-ghost:hover{background:rgba(255,255,255,0.05);color:#94a3b8}
.btn-outline{background:transparent;color:#ef4444;border:1px solid rgba(239,68,68,0.3);padding:6px 12px}
.btn-outline:hover{background:rgba(239,68,68,0.08)}

/* ── Main Layout ── */
.main-grid{flex:1;display:grid;grid-template-columns:1fr 2fr;gap:12px;min-height:0;overflow:hidden}
@media(max-width:900px){.main-grid{grid-template-columns:1fr}}
.side-panel{display:flex;flex-direction:column;gap:8px;min-height:0;overflow:hidden}
.main-panel{display:flex;flex-direction:column;gap:10px;min-height:0;overflow:hidden}

/* ── Gift Panel ── */
.gift-grid{display:flex;gap:3px;padding:8px}
.gift-btn{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;padding:6px 2px;border-radius:8px;border:1px solid rgba(255,255,255,0.05);background:rgba(255,255,255,0.02);cursor:pointer;transition:all 0.2s;color:#64748b;font-size:10px;min-width:0}
.gift-btn:hover{border-color:rgba(0,212,255,0.3);background:rgba(0,212,255,0.05);color:#e2e8f0}
.gift-btn .icon{font-size:18px;line-height:1}
.gift-btn .name{line-height:1}
.gift-btn .effect{color:#7c3aed;font-size:9px;line-height:1}

/* ── Progress Bars ── */
.progress-section{padding:8px 12px;display:flex;flex-direction:column;gap:6px}
.progress-item{display:flex;flex-direction:column;gap:2px}
.progress-header{display:flex;justify-content:space-between;font-size:11px}
.progress-header .label{color:#64748b}
.progress-header .count{color:#94a3b8}
.progress-track{height:5px;background:rgba(255,255,255,0.05);border-radius:3px;overflow:hidden}
.progress-fill{height:100%;border-radius:3px;transition:width 0.5s ease}
.progress-fill.cyan{background:linear-gradient(90deg,#00d4ff,#00d4ff80)}
.progress-fill.gold{background:linear-gradient(90deg,#f59e0b,#f59e0b80)}
.progress-remaining{font-size:10px;color:#475569}

/* ── QA Bubble ── */
.qa-card{flex:1;display:flex;flex-direction:column;min-height:0;overflow:hidden;position:relative}
.qa-card .qa-header{display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border-bottom:1px solid rgba(255,255,255,0.04);flex-shrink:0}
.qa-card .qa-header h3{font-size:12px;color:#64748b;display:flex;align-items:center;gap:6px}
.qa-card .qa-header span{font-size:11px;color:#475569}
.qa-list{flex:1;overflow-y:auto;padding:6px 8px;display:flex;flex-direction:column;gap:4px}
.qa-list::-webkit-scrollbar{width:3px}
.qa-list::-webkit-scrollbar-thumb{background:#334155;border-radius:2px}
.qa-item{padding:6px 8px;border-radius:8px;font-size:12px;display:flex;justify-content:space-between;align-items:flex-start;gap:6px;animation:fadeSlideIn 0.2s ease-out;flex-shrink:0}
.qa-item .left{flex:1;min-width:0}
.qa-item .user{font-size:10px;color:#64748b;margin-bottom:1px}
.qa-item .text{color:#cbd5e1;word-break:break-all;line-height:1.4}
.qa-badge{font-size:10px;padding:1px 6px;border-radius:8px;font-weight:600;white-space:nowrap;flex-shrink:0;margin-top:2px}
.qa-item.yes{background:rgba(34,197,94,0.06);border-left:2px solid #22c55e}
.qa-item.yes .qa-badge{background:rgba(34,197,94,0.15);color:#22c55e}
.qa-item.no{background:rgba(239,68,68,0.06);border-left:2px solid #ef4444}
.qa-item.no .qa-badge{background:rgba(239,68,68,0.15);color:#ef4444}
.qa-item.maybe{background:rgba(234,179,8,0.06);border-left:2px solid #eab308}
.qa-item.maybe .qa-badge{background:rgba(234,179,8,0.15);color:#eab308}
.qa-item.irrelevant{background:rgba(100,116,139,0.06);border-left:2px solid #64748b}
.qa-item.irrelevant .qa-badge{background:rgba(100,116,139,0.15);color:#64748b}

/* ── Surface Card ── */
.surface-card{flex-shrink:0;overflow:hidden}
.surface-header{padding:10px 14px;display:flex;justify-content:space-between;align-items:center;cursor:pointer;user-select:none}
.surface-header:hover{background:rgba(255,255,255,0.02)}
.surface-header .label{display:flex;align-items:center;gap:8px;font-size:13px;font-weight:600;color:#e2e8f0}
.surface-header .label .pulse{width:6px;height:6px;border-radius:50%;background:#00d4ff;animation:pulse-dot 2s infinite}
.surface-body{padding:0 14px 10px;font-size:14px;line-height:1.8;color:#94a3b8;animation:fadeSlideIn 0.3s ease-out}

/* ── Reveal Area ── */
.reveal-card{flex:1;position:relative;display:flex;flex-direction:column;min-height:0;overflow:hidden}
.reveal-progress{position:absolute;top:10px;right:14px;font-size:12px;color:#64748b;display:flex;align-items:center;gap:6px;z-index:2}
.reveal-progress span{color:#00d4ff;font-weight:700}
.timer-display{position:absolute;top:10px;left:14px;font-size:12px;color:#64748b;display:flex;align-items:center;gap:5px;z-index:2}
.timer-display .num{font-weight:700;font-variant-numeric:tabular-nums}
.timer-display.normal .num{color:#00d4ff}
.timer-display.warning .num{color:#fbbf24}
.timer-display.danger .num{color:#ef4444;animation:pulse-dot 1s infinite}
.auto-hint-toast{position:fixed;bottom:80px;left:50%;transform:translateX(-50%);z-index:98;padding:8px 18px;border-radius:10px;font-size:13px;text-align:center;pointer-events:none;opacity:0;transition:opacity 0.4s;max-width:80%;background:rgba(251,191,36,0.15);border:1px solid rgba(251,191,36,0.3);color:#fbbf24}
.auto-hint-toast.show{opacity:1}
.reveal-content{flex:1;display:flex;align-items:center;justify-content:center;padding:30px 20px 20px;overflow-y:auto}
.reveal-text{font-size:22px;line-height:2.2;letter-spacing:2px;text-align:center;word-break:break-all}
.reveal-text .ch{display:inline-block;transition:all 0.3s ease;margin:0 1px;animation:fadeIn 0.3s ease-out}
.reveal-text .ch.show{color:#e2e8f0}
.reveal-text .ch.hide{color:transparent;background:#1e293b;border-radius:4px;min-width:1.2em;text-align:center}
.reveal-text .ch.hide::after{content:"\2593";color:#334155}
.reveal-text .ch.func{color:#475569}
.reveal-bottom{padding:8px 14px 12px;display:flex;justify-content:space-between;align-items:center;flex-shrink:0}
.reveal-bottom .info{font-size:11px;color:#64748b}
.reveal-bottom .gift-actions{display:flex;gap:6px}
.btn-gift{display:inline-flex;align-items:center;gap:4px;padding:5px 10px;border-radius:8px;border:1px solid;font-size:11px;font-weight:500;cursor:pointer;transition:all 0.2s;background:transparent}
.btn-gift:hover{transform:translateY(-1px)}
.btn-gift.gold{color:#fbbf24;border-color:rgba(251,191,36,0.2)}
.btn-gift.gold:hover{background:rgba(251,191,36,0.08)}
.btn-gift.purple{color:#a855f7;border-color:rgba(168,85,247,0.2)}
.btn-gift.purple:hover{background:rgba(168,85,247,0.08)}
.contribution-card{padding:8px 12px;flex-shrink:0}
.contribution-card h3{font-size:12px;color:#64748b;margin-bottom:6px;display:flex;align-items:center;gap:4px}
.contribution-list{display:flex;flex-direction:column;gap:3px}
.contribution-row{display:flex;justify-content:space-between;padding:3px 6px;border-radius:4px;background:rgba(255,255,255,0.02);font-size:11px;color:#94a3b8}

/* ── Gift Toast ── */
.gift-toast{position:fixed;top:60px;left:50%;transform:translateX(-50%);z-index:99;padding:10px 24px;border-radius:12px;font-size:14px;font-weight:600;text-align:center;pointer-events:none;opacity:0;transition:all 0.3s ease;max-width:90%;box-shadow:0 4px 24px rgba(0,0,0,0.3)}
.gift-toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
.gift-toast.popularity{background:linear-gradient(135deg,rgba(0,212,255,0.2),rgba(0,212,255,0.05));border:1px solid rgba(0,212,255,0.3);color:#00d4ff}
.gift-toast.beer{background:linear-gradient(135deg,rgba(251,191,36,0.2),rgba(251,191,36,0.05));border:1px solid rgba(251,191,36,0.3);color:#fbbf24}
.gift-toast.lollipop{background:linear-gradient(135deg,rgba(236,72,153,0.2),rgba(236,72,153,0.05));border:1px solid rgba(236,72,153,0.3);color:#f472b6}
.gift-toast.sunglasses{background:linear-gradient(135deg,rgba(168,85,247,0.2),rgba(168,85,247,0.05));border:1px solid rgba(168,85,247,0.3);color:#a855f7}
.gift-toast.like{background:linear-gradient(135deg,rgba(244,63,94,0.2),rgba(244,63,94,0.05));border:1px solid rgba(244,63,94,0.3);color:#f43f5e}
.gift-toast.fan_light{background:linear-gradient(135deg,rgba(250,204,21,0.2),rgba(250,204,21,0.05));border:1px solid rgba(250,204,21,0.3);color:#facc15}

/* ── Settings Overlay ── */
.settings-overlay{position:fixed;inset:0;background:rgba(0,0,0,0.7);display:none;align-items:center;justify-content:center;z-index:200;backdrop-filter:blur(4px)}
.settings-overlay.show{display:flex}
.settings-card{background:#0c0f1e;border:1px solid rgba(255,255,255,0.08);border-radius:16px;padding:24px 28px;max-width:480px;width:90%;max-height:80vh;overflow-y:auto;box-shadow:0 0 40px rgba(0,212,255,0.08)}
.settings-card h2{font-size:16px;font-weight:700;color:#e2e8f0;margin-bottom:16px;display:flex;align-items:center;gap:8px}
.settings-card .section{margin-bottom:18px}
.settings-card .section-title{font-size:13px;font-weight:600;color:#94a3b8;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid rgba(255,255,255,0.05)}
.settings-card .field{display:flex;flex-direction:column;gap:4px;margin-bottom:10px}
.settings-card .field label{font-size:11px;color:#64748b}
.settings-card .field input,.settings-card .field select{padding:8px 10px;border-radius:8px;border:1px solid rgba(255,255,255,0.08);background:rgba(255,255,255,0.03);color:#e2e8f0;font-size:13px;outline:none;transition:border-color 0.2s}
.settings-card .field input:focus,.settings-card .field select:focus{border-color:rgba(0,212,255,0.3)}
.settings-card .field-row{display:flex;gap:10px;align-items:center}
.settings-card .field-row label{font-size:11px;color:#64748b}
.settings-card .field-row input[type=range]{flex:1}
.settings-card .field-row .val{font-size:12px;color:#00d4ff;min-width:32px;text-align:right}
.settings-card .actions{display:flex;gap:8px;justify-content:flex-end;margin-top:16px;padding-top:12px;border-top:1px solid rgba(255,255,255,0.05)}
.toggle-switch{position:relative;display:inline-block;width:36px;height:20px;flex-shrink:0}
.toggle-switch input{opacity:0;width:0;height:0}
.toggle-switch .slider{position:absolute;cursor:pointer;inset:0;background:#334155;border-radius:10px;transition:0.3s}
.toggle-switch .slider::before{content:'';position:absolute;height:16px;width:16px;left:2px;bottom:2px;background:#e2e8f0;border-radius:50%;transition:0.3s}
.toggle-switch input:checked+.slider{background:#00d4ff}
.toggle-switch input:checked+.slider::before{transform:translateX(16px)}

/* ── Win Overlay ── */
.win-overlay{position:fixed;inset:0;background:rgba(0,0,0,0.75);display:flex;align-items:center;justify-content:center;z-index:100;animation:fadeIn 0.4s ease;backdrop-filter:blur(4px)}
.win-card{padding:32px 48px;border-radius:16px;text-align:center;max-width:420px;border:1px solid rgba(0,212,255,0.2);background:rgba(12,15,30,0.95);backdrop-filter:blur(20px);box-shadow:0 0 40px rgba(0,212,255,0.1)}
.win-card h2{font-size:26px;font-weight:800;background:linear-gradient(135deg,#00d4ff,#f59e0b);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:8px}
.win-card p{color:#64748b;margin-bottom:20px;font-size:14px}
.empty-state{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:#334155;font-size:13px;gap:6px}
.empty-state .icon{font-size:36px;margin-bottom:4px;opacity:0.5}

@keyframes fadeSlideIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
@keyframes pulse-dot{0%,100%{opacity:1}50%{opacity:0.4}}

/* ── Contribution Board ── */
.contrib-card{padding:8px 12px;flex-shrink:0;position:relative;overflow:hidden}
.contrib-card h3{font-size:12px;color:#64748b;margin-bottom:6px;display:flex;align-items:center;gap:4px}
.contrib-list{display:flex;flex-direction:column;gap:3px}
.contrib-row{display:flex;justify-content:space-between;padding:3px 6px;border-radius:4px;background:rgba(255,255,255,0.02);font-size:11px;color:#94a3b8}

/* ── Header Badges (段位/金币/连击/签到) ── */
.header-badges{display:flex;align-items:center;gap:6px;margin-right:8px}
.tier-badge{display:flex;align-items:center;gap:4px;padding:3px 9px;border-radius:8px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.08);font-size:12px;font-weight:600;color:#6B7280;transition:all 0.3s}
.tier-badge .ti-icon{font-size:14px;line-height:1}
.tier-badge .ti-name{line-height:1}
.coin-badge{display:flex;align-items:center;gap:3px;padding:3px 9px;border-radius:8px;background:rgba(251,191,36,0.08);border:1px solid rgba(251,191,36,0.18);font-size:12px;font-weight:600;color:#fbbf24}
.combo-badge{display:flex;align-items:center;gap:3px;padding:3px 9px;border-radius:8px;background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.25);font-size:12px;font-weight:700;color:#fbbf24;animation:comboPulse 1s infinite}
@keyframes comboPulse{0%,100%{box-shadow:0 0 0 rgba(245,158,11,0)}50%{box-shadow:0 0 12px rgba(245,158,11,0.4)}}
.header-btn{padding:5px 10px;border-radius:8px;border:1px solid rgba(255,255,255,0.08);background:rgba(255,255,255,0.03);color:#94a3b8;font-size:12px;cursor:pointer;transition:all 0.2s;white-space:nowrap}
.header-btn:hover{background:rgba(0,212,255,0.08);color:#e2e8f0;border-color:rgba(0,212,255,0.2)}

/* ── Difficulty Selector ── */
.diff-row{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
.diff-btn{flex:1;padding:8px 10px;border-radius:8px;border:1px solid rgba(255,255,255,0.08);background:rgba(255,255,255,0.03);color:#94a3b8;font-size:12px;cursor:pointer;transition:all 0.2s;text-align:center;min-width:64px}
.diff-btn:hover{border-color:rgba(0,212,255,0.3);color:#e2e8f0}
.diff-btn.active{background:linear-gradient(135deg,#00d4ff,#7c3aed);color:#fff;border-color:transparent;box-shadow:0 2px 10px rgba(0,212,255,0.25)}
.diff-btn .mult{font-size:10px;color:#fbbf24;margin-top:2px}
.diff-btn.active .mult{color:#fff}

/* ── Gift Shop Overlay ── */
.shop-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin:14px 0}
.shop-item{padding:12px;border-radius:10px;border:1px solid rgba(255,255,255,0.06);background:rgba(255,255,255,0.03);display:flex;flex-direction:column;gap:5px;align-items:center;text-align:center;transition:all 0.2s}
.shop-item:hover{border-color:rgba(0,212,255,0.25);transform:translateY(-1px)}
.shop-item .shop-icon{font-size:28px}
.shop-item .shop-name{font-size:13px;font-weight:600;color:#e2e8f0}
.shop-item .shop-effect{font-size:11px;color:#7c3aed;line-height:1.3}
.shop-item .shop-price{font-size:13px;font-weight:700;color:#fbbf24;margin-top:2px}
.shop-item.disabled{opacity:0.45;filter:grayscale(0.6)}
.shop-item.disabled .shop-buy{cursor:not-allowed}

/* ── Signin Overlay ── */
.signin-info{display:flex;justify-content:space-between;margin:10px 0;font-size:13px;color:#94a3b8}
.signin-info b{color:#fbbf24}
.signin-row{display:grid;grid-template-columns:repeat(7,1fr);gap:5px;margin:10px 0 14px}
.signin-day{padding:8px 4px;border-radius:8px;border:1px solid rgba(255,255,255,0.06);background:rgba(255,255,255,0.02);text-align:center;font-size:11px;color:#64748b;transition:all 0.2s}
.signin-day .day-num{font-weight:700;color:#94a3b8;margin-bottom:3px}
.signin-day .day-reward{font-size:10px;color:#fbbf24}
.signin-day.done{background:rgba(34,197,94,0.1);border-color:rgba(34,197,94,0.3)}
.signin-day.done .day-num{color:#22c55e}
.signin-day.today{border-color:#00d4ff;background:rgba(0,212,255,0.08);box-shadow:0 0 12px rgba(0,212,255,0.2)}
.signin-day.today .day-num{color:#00d4ff}

/* ── Combo Panel ── */
.combo-panel{background:linear-gradient(135deg,rgba(251,191,36,0.15),rgba(245,158,11,0.05));border:1px solid rgba(251,191,36,0.3);border-radius:12px;padding:10px 16px;display:flex;align-items:center;gap:12px;margin-top:8px;position:relative;overflow:hidden}
.combo-panel::before{content:'';position:absolute;inset:0;background:linear-gradient(90deg,transparent,rgba(255,255,255,0.05),transparent);animation:comboShine 2s infinite}
@keyframes comboShine{0%{transform:translateX(-100%)}100%{transform:translateX(100%)}}
.combo-fire{font-size:20px;font-weight:800;color:#fbbf24;z-index:1}
.combo-msg{font-size:12px;color:#fde68a;flex:1;z-index:1}
.combo-bar{flex:1;height:4px;background:rgba(255,255,255,0.1);border-radius:2px;overflow:hidden;max-width:90px;z-index:1}
.combo-bar-fill{height:100%;background:linear-gradient(90deg,#fbbf24,#f59e0b);width:100%;transition:width 0.5s linear}
.combo-timer{font-size:11px;color:#fbbf24;z-index:1}
.combo-panel.urgent{animation:comboUrgent 0.5s infinite}
@keyframes comboUrgent{0%,100%{border-color:rgba(239,68,68,0.5)}50%{border-color:rgba(251,191,36,0.3)}}

/* ── Tier-Up Overlay ── */
.tier-up-overlay{position:fixed;inset:0;background:rgba(0,0,0,0.75);backdrop-filter:blur(4px);display:flex;align-items:center;justify-content:center;z-index:300;animation:fadeIn 0.3s}
.tier-up-content{text-align:center;padding:36px 56px;background:linear-gradient(135deg,rgba(0,212,255,0.1),rgba(124,58,237,0.1));border:2px solid #fbbf24;border-radius:16px;animation:scaleIn 0.5s}
.tier-up-from,.tier-up-to{font-size:30px;font-weight:800;margin:10px 0;display:flex;align-items:center;justify-content:center;gap:8px}
.tier-up-arrow{font-size:34px;color:#fbbf24;margin:4px 0}
.tier-up-msg{font-size:22px;color:#fbbf24;margin-top:14px;font-weight:700}
@keyframes scaleIn{from{transform:scale(0);opacity:0}to{transform:scale(1);opacity:1}}

/* ── Gift Fullscreen FX ── */
.gift-fx{position:fixed;z-index:250;pointer-events:none;font-size:120px;left:50%;transform:translateX(-50%);top:-120px;animation:giftFall 1.5s cubic-bezier(0.5,0,0.5,1) forwards}
@keyframes giftFall{0%{top:-120px;transform:translateX(-50%) scale(0.5) rotate(0)}50%{top:42%;transform:translateX(-50%) scale(1.6) rotate(15deg)}100%{top:110%;transform:translateX(-50%) scale(1) rotate(0);opacity:0}}
.gift-banner-row{position:fixed;top:54px;left:50%;transform:translateX(-50%);z-index:240;display:flex;flex-direction:column;align-items:center;gap:4px;width:max-content;max-width:90%}
.gift-banner{background:linear-gradient(90deg,rgba(251,191,36,0.2),rgba(245,158,11,0.05));border-left:3px solid #fbbf24;padding:6px 14px;border-radius:4px;font-size:13px;color:#fbbf24;animation:fadeSlideIn 0.3s}
.gift-flash{position:fixed;inset:0;z-index:245;pointer-events:none;animation:flashFade 0.6s ease-out forwards}
@keyframes flashFade{0%{background:rgba(168,85,247,0.5)}100%{background:rgba(168,85,247,0)}}
.shake{animation:shake 0.5s}
@keyframes shake{0%,100%{transform:translate(0,0)}25%{transform:translate(-6px,3px)}50%{transform:translate(5px,-3px)}75%{transform:translate(-4px,2px)}}
.particle-burst{position:fixed;z-index:248;pointer-events:none;width:8px;height:8px;border-radius:50%;animation:burst 1s ease-out forwards}
@keyframes burst{0%{transform:translate(0,0) scale(1);opacity:1}100%{transform:translate(var(--bx),var(--by)) scale(0);opacity:0}}

/* ── Milestone Hint ── */
.milestone-hint{background:linear-gradient(135deg,rgba(0,212,255,0.12),rgba(124,58,237,0.08));border:1px solid rgba(0,212,255,0.25);border-radius:12px;padding:10px 14px;font-size:13px;color:#e2e8f0;cursor:pointer;animation:fadeSlideIn 0.3s;box-shadow:0 4px 18px rgba(0,212,255,0.1);max-width:340px}
.milestone-hint:hover{transform:translateY(-1px);border-color:rgba(0,212,255,0.4)}
#hintFloat{position:fixed;right:16px;bottom:16px;z-index:230;display:flex;flex-direction:column;gap:8px;align-items:flex-end}
</style>
</head>
<body>
<canvas id="particleCanvas"></canvas>
<div class="app">

<!-- Header -->
<header class="glass">
<div class="header-left">
<div class="header-icon">🐢</div>
<div><div class="header-title">CCcat 海龟汤</div><div class="header-sub">弹幕互动推理游戏</div></div>
</div>
<div class="header-status">
<span class="dot off" id="statusDot"></span><span id="statusText">未连接</span>
</div>
<div class="header-badges">
<button class="header-btn" onclick="openSignin()">📅 签到</button>
<div id="comboIndicator" class="combo-badge" style="display:none">🔥x<span id="comboCount">0</span></div>
<div id="tierBadge" class="tier-badge"><span class="ti-icon" id="tierIcon">🛡️</span><span class="ti-name" id="tierName">黑铁</span></div>
<div id="coinBalance" class="coin-badge">🪙 <span id="coinNum">100</span></div>
</div>
</header>

<!-- Controls -->
<div class="controls glass">
<div class="controls-left">
<span class="phase-dot idle" id="phaseDot"></span>
<span class="phase-label" id="phaseLabel">等待开始</span>
</div>
<div class="controls-right">
<button class="btn btn-ghost" onclick="openGiftShop()" title="礼物商店">🎁 商店</button>
<button class="btn btn-primary" id="btnStart" onclick="startGame()">🎮 开始游戏</button>
<button class="btn btn-ghost" onclick="openSettings()" title="设置">⚙️</button>
</div>
</div>

<!-- Difficulty Selector (折叠在 controls 下方，开始下局时显示) -->
<div class="glass" id="diffPanel" style="flex-shrink:0;padding:8px 12px;display:none">
<div style="font-size:11px;color:#64748b;margin-bottom:2px">选择本局难度（影响积分倍率）</div>
<div class="diff-row" id="diffRow">
<div class="diff-btn active" data-diff="auto" onclick="pickDiff('auto')">自适应<span class="mult">⚡</span></div>
<div class="diff-btn" data-diff="easy" onclick="pickDiff('easy')">简单<span class="mult">×1.0</span></div>
<div class="diff-btn" data-diff="medium" onclick="pickDiff('medium')">一般<span class="mult">×1.5</span></div>
<div class="diff-btn" data-diff="hard" onclick="pickDiff('hard')">困难<span class="mult">×2.0</span></div>
<div class="diff-btn" data-diff="hell" onclick="pickDiff('hell')">地狱<span class="mult">×3.0</span></div>
<div class="diff-btn" data-diff="void" onclick="pickDiff('void')">无人区<span class="mult">×5.0</span></div>
</div>
</div>

<!-- Main Grid -->
<div class="main-grid">
<!-- Side Panel -->
<div class="side-panel">
<!-- Gift Panel -->
<div class="glass" style="flex-shrink:0">
<div class="gift-grid">
<div class="gift-btn" onclick="sendGift('人气票')"><span class="icon">⚡</span><span class="name">人气票</span><span class="effect">方向提示</span>
</div>
<div class="gift-btn" onclick="sendGift('啤酒')"><span class="icon">🍺</span><span class="name">啤酒</span><span class="effect">揭示一字</span></div>
<div class="gift-btn" onclick="sendGift('棒棒糖')"><span class="icon">🍭</span><span class="name">棒棒糖</span><span class="effect">揭示一句</span></div>
<div class="gift-btn" onclick="sendGift('墨镜')"><span class="icon">🕶️</span><span class="name">墨镜</span><span class="effect">直接通关</span></div>
<div class="gift-btn" onclick="sendGift('粉丝灯牌')"><span class="icon">⭐</span><span class="name">灯牌</span><span class="effect">随机一句</span></div>
<div class="gift-btn" onclick="sendGift('点赞')"><span class="icon">❤️</span><span class="name">点赞</span><span class="effect">500赞一字</span></div>
</div>
</div>

<!-- Progress -->
<div class="glass" style="flex-shrink:0">
<div class="progress-section">
<div class="progress-item">
<div class="progress-header"><span class="label">揭示进度</span><span class="count" id="revealCount">0/0</span></div>
<div class="progress-track"><div class="progress-fill cyan" id="revealFill" style="width:0%"></div></div>
<div class="progress-remaining" id="revealRemaining">剩余 0 字</div>
</div>
</div>
</div>

<!-- QA Card -->
<div class="qa-card glass">
<div class="qa-header"><h3>💬 问答记录</h3><span id="qaCount">0 条</span></div>
<div class="qa-list" id="qaList"><div class="empty-state"><div class="icon">💭</div>等待弹幕提问...</div></div>
</div>

<!-- Contribution -->
<div class="glass contrib-card">
<h3>🏆 揭示贡献榜</h3>
<div class="contrib-list" id="contribList"><div style="color:#334155;font-size:11px;text-align:center;padding:4px">暂无贡献</div></div>
</div>
</div>

<!-- Main Panel -->
<div class="main-panel">
<!-- Surface -->
<div class="surface-card glass" id="surfaceCard" style="display:none">
<div class="surface-header" onclick="toggleSurface()">
<div class="label"><span class="pulse"></span>汤面</div>
<span id="chevron" style="color:#475569;font-size:12px">▲</span>
</div>
<div class="surface-body" id="surfaceBody"><p id="surfaceText"></p></div>
</div>

<!-- Reveal Area -->
<div class="reveal-card glass glass-primary" id="revealArea">
<div class="timer-display normal" id="timerDisplay"><span id="timerIcon">⏱</span><span class="num" id="timerText">--:--</span></div>
<div class="reveal-progress">揭示进度 <span id="progressText">0%</span></div>
<div class="reveal-content">
<div class="reveal-text" id="revealText"><div class="empty-state"><div class="icon">🐢</div>点击「开始游戏」开始新一局</div></div>
</div>
<div class="reveal-bottom">
<div class="info" id="gameInfo">等待开始...</div>
<div class="gift-actions" id="giftActions" style="display:none">
<button class="btn-gift gold" onclick="sendGift('人气票')">⚡方向提示</button>
<button class="btn-gift gold" onclick="sendGift('啤酒')">🍺揭示一字</button>
<button class="btn-gift gold" onclick="buyHint()">🔮购买提示</button>
<button class="btn-gift purple" onclick="sendGift('墨镜')">🕶️通关</button>
</div>
</div>
</div>
</div>
</div>
</div>

<!-- Settings Overlay -->
<div class="settings-overlay" id="settingsOverlay" style="display:none">
<div class="settings-card">
<h2>⚙️ 设置</h2>

<div class="section">
<div class="section-title">🤖 LLM API 配置</div>
<div class="field">
<label>API 地址 (Base URL)</label>
<input type="text" id="cfgBaseUrl" placeholder="https://api.deepseek.com" onchange="saveApiSettings()">
</div>
<div class="field">
<label>API Key</label>
<input type="password" id="cfgApiKey" placeholder="sk-..." onchange="saveApiSettings()">
</div>
<div class="field">
<label>模型 (Model)</label>
<input type="text" id="cfgModel" placeholder="deepseek-v4-flash" onchange="saveApiSettings()">
</div>
</div>

<div class="section">
<div class="section-title">🔊 语音 (TTS) 设置</div>
<div class="field">
<div class="field-row">
<label>启用语音播报</label>
<label class="toggle-switch">
<input type="checkbox" id="cfgTtsEnabled" onchange="saveVoiceSettings()">
<span class="slider"></span>
</label>
</div>
</div>
<div class="field">
<div class="field-row">
<label>语速</label>>
<input type="range" id="cfgTtsRate" min="0.5" max="2.0" step="0.1" value="1.0" oninput="saveVoiceSettings()">
<span class="val" id="cfgTtsRateVal">1.0</span>
</div>
</div>
<div class="field">
<div class="field-row">
<label>音量</label>>
<input type="range" id="cfgTtsVolume" min="0" max="1.0" step="0.1" value="1.0" oninput="saveVoiceSettings()">
<span class="val" id="cfgTtsVolumeVal">1.0</span>
</div>
</div>
</div>

<div class="actions">
<button class="btn btn-ghost" onclick="closeSettings()">关闭</button>
</div>
</div>
</div>

<!-- Gift Toast -->
<div id="giftToast" class="gift-toast"></div>
<div id="autoHintToast" class="auto-hint-toast"></div>

<!-- Danmaku Input Bar -->
<div class="glass" style="flex-shrink:0;padding:8px 12px;display:flex;gap:8px;align-items:center;margin-top:0">
<input type="text" id="danmakuInput" placeholder="输入你的猜测或提问，按 Enter 发送..." 
    style="flex:1;padding:8px 12px;border-radius:8px;border:1px solid rgba(255,255,255,0.08);background:rgba(255,255,255,0.03);color:#e2e8f0;font-size:13px;outline:none;transition:border-color 0.2s"
    onkeydown="if(event.key==='Enter')sendDanmaku()"
    onfocus="this.style.borderColor='rgba(0,212,255,0.3)'"
    onblur="this.style.borderColor='rgba(255,255,255,0.08)'">
<button class="btn btn-primary" onclick="sendDanmaku()" style="padding:8px 18px;white-space:nowrap">发送</button>
</div>

<!-- Win Overlay -->
<div class="win-overlay" id="winOverlay" style="display:none" onclick="this.style.display='none'">
<div class="win-card">
<h2>🎉 谜题已揭开！</h2>
<p id="winText">恭喜通关！</p>
<button class="btn btn-primary" onclick="closeWin()">🔄 再来一局</button>
</div>
</div>

<!-- Gift Shop Overlay -->
<div class="settings-overlay" id="shopOverlay" style="display:none">
<div class="settings-card">
<h2>🎁 礼物商店</h2>
<div class="signin-info"><span>你的余额：</span><b>🪙 <span id="shopBalance">100</span></b></div>
<div class="shop-grid" id="shopGrid"></div>
<div class="actions" style="margin-top:8px">
<button class="btn btn-ghost" onclick="closeGiftShop()">关闭</button>
</div>
</div>
</div>

<!-- Signin Overlay -->
<div class="settings-overlay" id="signinOverlay" style="display:none">
<div class="settings-card">
<h2>📅 每日签到</h2>
<div class="signin-info">
<span>连续签到第 <b id="signinDay">0</b> 天</span>
<span>累计 <b id="signinTotal">0</b> 天</span>
</div>
<div style="font-size:13px;color:#94a3b8;margin:6px 0">今日奖励：<b style="color:#fbbf24">+<span id="signinReward">30</span> 🪙</b></div>
<div class="signin-row" id="signinDays"></div>
<div class="actions">
<button class="btn btn-primary" id="signinBtn" onclick="doSignin()">📥 立即签到</button>
<button class="btn btn-ghost" onclick="closeSignin()">关闭</button>
</div>
</div>
</div>

<!-- Tier-Up Overlay (动态创建) -->
<div id="tierUpHost"></div>
<!-- Gift FX banner row -->
<div class="gift-banner-row" id="giftBannerRow"></div>
<!-- Milestone hint float -->
<div id="hintFloat"></div>

<script>
let ws=null, surfaceVisible=true, gameState={phase:'lobby',charStates:[]}, lastDanmakuUser='我', contribs={};
function showGiftToast(msg){
    var toast=document.getElementById('giftToast');
    var name=msg.giftName||'';
    var user=msg.user||'观众';
    var typeMap={'点赞':'like','粉丝灯牌':'fan_light','人气票':'popularity','啤酒':'beer','棒棒糖':'lollipop','墨镜':'sunglasses'};
    var iconMap={'点赞':'❤️','粉丝灯牌':'⭐','人气票':'⚡','啤酒':'🍺','棒棒糖':'🍭','墨镜':'🕶️'};
    var gtype=typeMap[name]||'';
    var icon=iconMap[name]||'🎁';
    var effects={'popularity':'💡 方向引导提示','beer':'🔍 揭示一字','lollipop':'📖 揭示一句','sunglasses':'🏆 通关！','fan_light':'⭐ 揭示一句','like':'👍 点赞+1'};
    var effect=effects[gtype]||'';
    toast.textContent=icon+' '+user+' 送了 '+name+' '+effect;
    if(msg.taunt){toast.textContent+=' — '+msg.taunt}
    toast.className='gift-toast '+(gtype||'');
    setTimeout(function(){toast.classList.add('show')},10);
    clearTimeout(toast._hide);
    toast._hide=setTimeout(function(){toast.classList.remove('show')},3000);
}
// ?? ???? ??
function openSettings(){
    var el=document.getElementById('settingsOverlay');el.classList.add('show');el.style.display='';
    loadSettings();
}
function closeSettings(){
    var el=document.getElementById('settingsOverlay');el.classList.remove('show');el.style.display='none';
}
function loadSettings(){
    var s = JSON.parse(localStorage.getItem('cccat_settings') || '{}');
    document.getElementById('cfgBaseUrl').value = s.baseUrl || '';
    document.getElementById('cfgApiKey').value = s.apiKey || '';
    document.getElementById('cfgModel').value = s.model || '';
    document.getElementById('cfgTtsEnabled').checked = s.ttsEnabled !== false;
    document.getElementById('cfgTtsRate').value = s.ttsRate || 1.0;
    document.getElementById('cfgTtsRateVal').textContent = s.ttsRate || 1.0;
    document.getElementById('cfgTtsVolume').value = s.ttsVolume || 1.0;
    document.getElementById('cfgTtsVolumeVal').textContent = s.ttsVolume || 1.0;
}
function saveApiSettings(){
    var s = JSON.parse(localStorage.getItem('cccat_settings') || '{}');
    s.baseUrl = document.getElementById('cfgBaseUrl').value;
    s.apiKey = document.getElementById('cfgApiKey').value;
    s.model = document.getElementById('cfgModel').value;
    localStorage.setItem('cccat_settings', JSON.stringify(s));
    // Sync to server
    if(ws && ws.readyState === 1){
        fetch('/api/config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                api_key: s.apiKey,
                base_url: s.baseUrl,
                model: s.model
            })
        }).catch(function(){});
    }
}
function saveVoiceSettings(){
    var s = JSON.parse(localStorage.getItem('cccat_settings') || '{}');
    s.ttsEnabled = document.getElementById('cfgTtsEnabled').checked;
    s.ttsRate = parseFloat(document.getElementById('cfgTtsRate').value);
    s.ttsVolume = parseFloat(document.getElementById('cfgTtsVolume').value);
    document.getElementById('cfgTtsRateVal').textContent = s.ttsRate.toFixed(1);
    document.getElementById('cfgTtsVolumeVal').textContent = s.ttsVolume.toFixed(1);
    localStorage.setItem('cccat_settings', JSON.stringify(s));
}
// Auto-load settings on startup and sync API config
(function(){
    var s = JSON.parse(localStorage.getItem('cccat_settings') || '{}');
    if(s.baseUrl || s.apiKey || s.model){
        setTimeout(function(){
            fetch('/api/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    api_key: s.apiKey || undefined,
                    base_url: s.baseUrl || undefined,
                    model: s.model || undefined
                })
            }).catch(function(){});
        }, 1000);
    }
})();

function connectWS(){
    if(ws) try{ws.close()}catch(e){}
    ws=new WebSocket('ws://'+location.host+'/ws');
    ws.onopen=()=>{setStatus(true)}
    ws.onclose=()=>{setStatus(false);setTimeout(connectWS,3000)}
    ws.onmessage=e=>{try{handle(JSON.parse(e.data))}catch(ex){}}
    setInterval(()=>{if(ws&&ws.readyState===1)ws.send(JSON.stringify({type:'ping'}))},5000)
}
function setStatus(on){
    document.getElementById('statusDot').className='dot '+(on?'on':'off');
    document.getElementById('statusText').textContent=on?'已连接':'未连接';
}
function handle(msg){
    switch(msg.type){
        case 'game_start':
            contribs={}; gameState.charStates=msg.charStates||[]; gameState.surface=msg.surface||'';
            lastMilestoneBucket=-1;
            document.getElementById('surfaceCard').style.display='';
            document.getElementById('surfaceText').textContent=gameState.surface;
            document.getElementById('giftActions').style.display='';
            document.getElementById('btnStart').textContent='🔄 下一局';
            setPhase('reading');
            renderReveal();
            document.getElementById('gameInfo').innerHTML='📖 朗读汤面中...';
            document.getElementById('revealText').innerHTML='<div style="color:#475569;font-size:15px;line-height:1.8;text-align:center;padding:20px;animation:fadeIn 1s ease">'+esc(gameState.surface)+'</div>';
            // 朗读阶段持续3秒后自动进入游戏
            if(gameState.readingTimer)clearTimeout(gameState.readingTimer);
            gameState.playing=false;gameState.readingTimer=setTimeout(function(){
                setPhase('playing');
                document.getElementById('gameInfo').innerHTML='🎯 游戏进行中 - 输入弹幕猜测！';
                renderReveal();
            },3000);
            document.getElementById('qaList').innerHTML='<div class="empty-state"><div class="icon">💭</div>等待弹幕提问...</div>';
            document.getElementById('qaCount').textContent='0 条';
            document.getElementById('contribList').innerHTML='<div style="color:#334155;font-size:11px;text-align:center;padding:4px">暂无贡献</div>';
            docReady=true;
            break;
        case 'timer':
            updateTimer(msg.remaining);
            break;
        case 'auto_hint':
            showAutoHint(msg.text, msg.revealed);
            break;
        case 'progressive_hint':
            var _levelNames=['🔮 方向引导','🔮 关键词提示','🔮 半答案提示'];
            var _levelName=_levelNames[msg.level]||'💡 提示';
            showAutoHint(_levelName+': '+msg.hint, '');
            break;
        case 'reveal_update':
            if(msg.charStates){
                const old=gameState.charStates;
                const oldRevealed=old.filter(c=>c.revealed).length;
                gameState.charStates=msg.charStates;
                const newRevealed=gameState.charStates.filter(c=>c.revealed).length;
                const delta=newRevealed-oldRevealed;
                if(delta>0&&lastDanmakuUser){
                    addContrib(lastDanmakuUser,delta);
                }
                renderReveal();
                // 里程碑
                const cw=gameState.charStates.filter(c=>c.isContent);
                const tot=cw.length, rev=cw.filter(c=>c.revealed).length;
                if(tot>0)checkMilestone(Math.round(rev/tot*100));
            }
            break;
        case 'classification':
            addQA(msg.user||'观众',msg.text,msg.answerType);
            break;
        case 'game_end':
            if(msg.charStates){gameState.charStates=msg.charStates;renderReveal()}
            setPhase('complete');
            document.getElementById('gameInfo').innerHTML='🎉 谜题已揭晓！';
            // 显示完整汤底
            if(gameState.surface){
                var fullText='完整谜底：'+esc(gameState.surface)+'<br><br>';
                // Get the full answer from charStates
                var chars=gameState.charStates||[];
                var answer=chars.map(function(c){return c.char}).join('');
                fullText+=esc(answer);
                document.getElementById('winText').innerHTML=fullText;
            }
            document.getElementById('winOverlay').style.display='';
            // 5秒后自动下一局
            if(gameState.autoNextTimer)clearTimeout(gameState.autoNextTimer);
            gameState.autoNextTimer=setTimeout(function(){
                document.getElementById('winOverlay').style.display='none';
                startGame();
            },5000);
            break;
        case 'hint':
            if(msg.hint){
                addQA('💡 提示',msg.hint,'是');
                if(msg.script){
                    try{var _s=JSON.parse(localStorage.getItem('cccat_settings')||'{}');if(_s.ttsEnabled!==false){window.speechSynthesis.cancel();var u=new SpeechSynthesisUtterance(msg.script);u.lang='zh-CN';u.rate=_s.ttsRate||1.0;u.volume=_s.ttsVolume||1.0;speechSynthesis.speak(u)}}catch(e){}
                }
            }
            break;
        case 'gift_effect':
            if(msg.script){
                try{var _s=JSON.parse(localStorage.getItem('cccat_settings')||'{}');if(_s.ttsEnabled!==false){window.speechSynthesis.cancel();var u=new SpeechSynthesisUtterance(msg.script);u.lang='zh-CN';u.rate=_s.ttsRate||1.0;u.volume=_s.ttsVolume||1.0;speechSynthesis.speak(u)}}catch(e){}
            }
            showGiftToast(msg);
            // 全屏动画 + 连击 + 余额
            const gtype=msg.giftType||msg.giftName||'';
            showGiftEffect(gtype,msg.user||'观众');
            if(msg.balance!==undefined){setCoinBalance(msg.balance);coinBalanceState=msg.balance}
            if(msg.combo&&msg.combo>1){
                showCombo(msg.combo,msg.multiplier);
                if(msg.multiplier>=1.5)showComboPanel(gtype,msg.multiplier);
            }
            break;
        case 'score_update':
            if(msg.tier)updateTierBadge(msg.tier);
            if(msg.score!==undefined&&msg.user==='我'){
                // 当前仅展示段位；累计积分由 leaderboard 反映
            }
            break;
        case 'tier_up':
            if(msg.from_tier&&msg.to_tier)showTierUp(msg.from_tier,msg.to_tier);
            break;
    }
}
function setPhase(p){
    const dot=document.getElementById('phaseDot');
    dot.className='phase-dot '+(p||'idle');
    const labels={lobby:'等待开始',reading:'📖 朗读汤面',playing:'🎯 猜谜进行中',complete:'🎉 已揭晓'};
    document.getElementById('phaseLabel').textContent=labels[p]||p;
}
function renderReveal(){
    const chars=gameState.charStates||[];
    const contentWords=chars.filter(c=>c.isContent);
    const total=contentWords.length;
    const revealed=contentWords.filter(c=>c.revealed).length;
    const pct=total>0?Math.round(revealed/total*100):0;
    document.getElementById('progressText').textContent=pct+'%';
    document.getElementById('revealFill').style.width=pct+'%';
    document.getElementById('revealCount').textContent=revealed+'/'+total;
    document.getElementById('revealRemaining').textContent='剩余 '+(total-revealed)+' 实词';
    if(chars.length===0)return;
    // Only count 实词 for progress
    document.getElementById('gameInfo').innerHTML='已揭示 <b style="color:#00d4ff">'+revealed+'</b>/'+total+' 实词';
    document.getElementById('revealText').innerHTML=chars.map((c,i)=>{
        if(c.revealed) return '<span class="ch show">'+esc(c.char)+'</span>';
        if(c.isContent) return '<span class="ch hide"></span>';
        return '<span class="ch func">'+esc(c.char)+'</span>';
    }).join('');
}
let docReady=true;
function addQA(user,text,answerType){
    const list=document.getElementById('qaList'), empty=list.querySelector('.empty-state');
    if(empty)list.innerHTML='';
    const m={'是':'yes','不是':'no','是也不是':'maybe','不相关':'irrelevant'};
    const cls=m[answerType]||'irrelevant';
    const badge={'yes':'🟢 是','no':'🔴 不是','maybe':'🟡 是也不是','irrelevant':'⚪ 不相关'};
    const div=document.createElement('div');
    div.className='qa-item '+cls;
    div.innerHTML='<div class="left"><div class="user">'+esc(user)+'</div><div class="text">'+esc(text)+'</div></div><span class="qa-badge">'+(badge[cls]||answerType)+'</span>';
    div.style.animation='fadeSlideIn 0.2s ease-out';
    list.insertBefore(div,list.firstChild);
    const c=list.querySelectorAll('.qa-item').length;
    document.getElementById('qaCount').textContent=c+' 条';
}
function startGame(){
    if(ws&&ws.readyState===1){
        ws.send(JSON.stringify({type:'start_round',difficulty:currentDiff}));
        document.getElementById('winOverlay').style.display='none';
        document.getElementById('diffPanel').style.display='none';
    }
}
function sendGift(name){
    if(ws&&ws.readyState===1)ws.send(JSON.stringify({type:'gift',giftName:name,nickname:'default',diamondCount:0}));
    else alert('请先连接服务器');
}
function buyHint(){
    if(ws&&ws.readyState===1)ws.send(JSON.stringify({type:'buy_hint',user:'观众'}));
    else alert('请先连接服务器');
}
function addContrib(user,n){
    if(!contribs[user])contribs[user]=0;
    contribs[user]+=n;
    renderContrib();
}
function renderContrib(){
    const list=document.getElementById('contribList');
    const sorted=Object.entries(contribs).sort((a,b)=>b[1]-a[1]).slice(0,5);
    if(sorted.length===0){
        list.innerHTML='<div style="color:#334155;font-size:11px;text-align:center;padding:4px">暂无贡献</div>';
        return;
    }
    list.innerHTML=sorted.map(([u,c],i)=>{
        const medal=['🥇','🥈','🥉'][i]||(i+1)+'.';
        return '<div class="contrib-row"><span>'+medal+' '+esc(u)+'</span><span>揭示 '+c+' 字</span></div>';
    }).join('');
}
function closeWin(){
    document.getElementById('winOverlay').style.display='none';
    if(gameState.autoNextTimer)clearTimeout(gameState.autoNextTimer);
    startGame();
}
function toggleSurface(){
    surfaceVisible=!surfaceVisible;
    document.getElementById('surfaceBody').style.display=surfaceVisible?'':'none';
    document.getElementById('chevron').textContent=surfaceVisible?'▲':'▼';
}
function sendDanmaku(){
    const input=document.getElementById('danmakuInput');
    const text=input.value.trim();
    if(!text)return;
    lastDanmakuUser='我';
    if(ws&&ws.readyState===1){
        ws.send(JSON.stringify({type:'danmaku',text:text,nickname:'default'}));
        input.value='';
    }else alert('请先连接服务器');
}
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}

// ── 难度选择 ──
let currentDiff='auto';
function pickDiff(d){
  currentDiff=d;
  document.querySelectorAll('#diffRow .diff-btn').forEach(b=>b.classList.toggle('active',b.dataset.diff===d));
}
function toggleDiffPanel(show){document.getElementById('diffPanel').style.display=show?'':'none'}

// ── 余额/段位 UI ──
async function refreshUserState(){
  try{
    const bal=await fetch('/api/coin/balance?user=default').then(r=>r.json());
    setCoinBalance(bal.balance||0);
  }catch(e){}
  try{
    const lb=await fetch('/api/leaderboard?limit=1').then(r=>r.json());
    // 排行榜第一未必是自己；改用 score_update 时刻同步，这里仅作初始化占位
  }catch(e){}
}
function setCoinBalance(n){document.getElementById('coinNum').textContent=n}
function updateTierBadge(tier){
  if(!tier)return;
  document.getElementById('tierIcon').textContent=tier.icon||'🛡️';
  document.getElementById('tierName').textContent=tier.name||'黑铁';
  const el=document.getElementById('tierBadge');
  if(tier.color)el.style.color=tier.color;
  if(tier.color)el.style.borderColor=tier.color+'55';
}
function showTierUp(fromTier,toTier){
  const host=document.getElementById('tierUpHost');
  const ov=document.createElement('div');
  ov.className='tier-up-overlay';
  ov.innerHTML=`<div class="tier-up-content">
    <div class="tier-up-from" style="color:${fromTier.color}">${fromTier.icon} ${fromTier.name}</div>
    <div class="tier-up-arrow">⬇️</div>
    <div class="tier-up-to" style="color:${toTier.color}">${toTier.icon} ${toTier.name}</div>
    <div class="tier-up-msg">🎉 段位提升！</div></div>`;
  host.appendChild(ov);
  ov.onclick=()=>ov.remove();
  setTimeout(()=>ov.remove(),4000);
}

// ── 连击指示器 ──
let comboInterval=null, comboSeconds=0;
function showCombo(count,multiplier){
  const el=document.getElementById('comboIndicator');
  document.getElementById('comboCount').textContent=count;
  el.style.display='flex';
  clearInterval(comboInterval);comboSeconds=30;
  const msgMap={1:'连击中！',1.5:'×1.5 加成',2:'双倍揭示！',3:'三倍暴击！'};
  comboInterval=setInterval(()=>{
    comboSeconds--;
    if(comboSeconds<=0){clearInterval(comboInterval);el.style.display='none';return}
    el.classList.toggle('urgent',comboSeconds<=5);
  },1000);
  // 聚合连击面板文案由 gift_effect 触发
}
function showComboPanel(gtype,multiplier){
  const host=document.getElementById('hintFloat');
  // 不重复创建
  if(document.getElementById('comboPanel'))return;
  const div=document.createElement('div');
  div.id='comboPanel';div.className='combo-panel';
  div.innerHTML=`<div class="combo-fire">🔥 x${multiplier}</div>
    <div class="combo-msg">连击加成生效！</div>
    <div class="combo-bar"><div class="combo-bar-fill" id="comboBarFill"></div></div>
    <div class="combo-timer" id="comboTimer">剩余 30秒</div>`;
  host.appendChild(div);
  let s=30;
  const iv=setInterval(()=>{
    s--;
    if(s<=0){clearInterval(iv);div.remove();return}
    div.querySelector('#comboBarFill').style.width=(s/30*100)+'%';
    div.querySelector('#comboTimer').textContent='剩余 '+s+'秒';
    if(s<=5)div.classList.add('urgent');
  },1000);
}

// ── 礼物商店 ──
const SHOP_META={
  like:{icon:'❤️',name:'点赞',effect:'500赞揭示一字',price:0},
  fan_light:{icon:'⭐',name:'粉丝灯牌',effect:'揭示一句(限3次)',price:20},
  popularity:{icon:'⚡',name:'人气票',effect:'AI方向提示',price:30},
  beer:{icon:'🍺',name:'啤酒',effect:'揭示一字',price:50},
  lollipop:{icon:'🍭',name:'棒棒糖',effect:'揭示一整句',price:80},
  sunglasses:{icon:'🕶️',name:'墨镜',effect:'直接通关',price:200},
};
async function openGiftShop(){
  const grid=document.getElementById('shopGrid');
  grid.innerHTML=Object.entries(SHOP_META).map(([k,m])=>{
    const can=coinBalanceState>=m.price;
    return `<div class="shop-item ${can?'':'disabled'}">
      <div class="shop-icon">${m.icon}</div>
      <div class="shop-name">${m.name}</div>
      <div class="shop-effect">${m.effect}</div>
      <div class="shop-price">🪙 ${m.price}</div>
      <button class="btn btn-primary shop-buy" ${can?'':'disabled'} onclick="buyGift('${k}')">购买</button>
    </div>`;
  }).join('');
  try{
    const bal=await fetch('/api/coin/balance?user=default').then(r=>r.json());
    document.getElementById('shopBalance').textContent=bal.balance||0;
  }catch(e){}
  document.getElementById('shopOverlay').style.display='flex';
}
function closeGiftShop(){document.getElementById('shopOverlay').style.display='none'}
let coinBalanceState=100;
async function buyGift(giftType){
  const resp=await fetch('/api/gift/buy',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({gift_type:giftType,user:'default'})
  }).then(r=>r.json());
  if(resp.ok){
    setCoinBalance(resp.balance);coinBalanceState=resp.balance;
    showToast(`🎉 购买成功！`);
    closeGiftShop();
  }else{showToast(`❌ ${resp.msg||'购买失败'}`)}
}
function showToast(t){const el=document.getElementById('giftToast');el.textContent=t;el.className='gift-toast';setTimeout(()=>el.classList.add('show'),10);clearTimeout(el._hide);el._hide=setTimeout(()=>el.classList.remove('show'),2500)}

// ── 签到 ──
async function openSignin(){
  try{
    const resp=await fetch('/api/signin?user=default').then(r=>r.json());
    document.getElementById('signinDay').textContent=resp.streak||0;
    document.getElementById('signinTotal').textContent=resp.total_days||0;
    document.getElementById('signinReward').textContent=resp.reward||30;
    const rewardMap=resp.reward_map||{1:30,2:30,3:30,4:50,5:80,6:100,7:150};
    const done=resp.streak||0;
    const todayIdx=(resp.today_done)?done:(done+1);
    document.getElementById('signinDays').innerHTML=Array.from({length:7},(_,i)=>{
      const d=i+1, r=rewardMap[d]||50;
      const cls=(d<=done)?'done':(d===todayIdx?'today':'');
      return `<div class="signin-day ${cls}"><div class="day-num">D${d}</div><div class="day-reward">${r}🪙</div></div>`;
    }).join('');
    const btn=document.getElementById('signinBtn');
    btn.disabled=resp.today_done;
    btn.textContent=resp.today_done?'✅ 今日已签到':'📥 立即签到';
    document.getElementById('signinOverlay').style.display='flex';
  }catch(e){showToast('获取签到信息失败')}
}
function closeSignin(){document.getElementById('signinOverlay').style.display='none'}
async function doSignin(){
  const resp=await fetch('/api/signin?user=default',{method:'POST'}).then(r=>r.json());
  if(resp.status==='ok'){
    setCoinBalance(resp.balance);coinBalanceState=resp.balance;
    showToast(`🎉 签到成功！+${resp.reward} 金币 (连续 ${resp.streak} 天)`);
    openSignin();
  }else if(resp.status==='repeat'){showToast('今天已签到过了')}
  else{showToast(resp.msg||'签到失败')}
}

// ── 礼物全屏动画 ──
function showGiftEffect(gtype,user){
  if(gtype==='beer'||gtype==='啤酒'){dropFx('🍺')}
  else if(gtype==='lollipop'||gtype==='棒棒糖'){dropFx('🍭');particleBurst('#f472b6')}
  else if(gtype==='sunglasses'||gtype==='墨镜'){dropFx('🕶️');flashScreen();shakeScreen()}
  else if(gtype==='popularity'||gtype==='人气票'){dropFx('⚡')}
  else if(gtype==='fan_light'||gtype==='粉丝灯牌'){dropFx('⭐');particleBurst('#facc15')}
  else if(gtype==='like'||gtype==='点赞'){particleBurst('#f43f5e')}
  giftBanner(user,gtype);
}
function dropFx(emoji){
  const el=document.createElement('div');el.className='gift-fx';el.textContent=emoji;
  document.body.appendChild(el);setTimeout(()=>el.remove(),1500);
}
function flashScreen(){const el=document.createElement('div');el.className='gift-flash';document.body.appendChild(el);setTimeout(()=>el.remove(),600)}
function shakeScreen(){const app=document.querySelector('.app');app.classList.add('shake');setTimeout(()=>app.classList.remove('shake'),500)}
function particleBurst(color){
  const cx=innerWidth/2, cy=innerHeight/2;
  for(let i=0;i<14;i++){
    const p=document.createElement('div');p.className='particle-burst';
    p.style.left=cx+'px';p.style.top=cy+'px';p.style.background=color;
    const ang=(i/14)*Math.PI*2, dist=80+Math.random()*80;
    p.style.setProperty('--bx',Math.cos(ang)*dist+'px');
    p.style.setProperty('--by',Math.sin(ang)*dist+'px');
    document.body.appendChild(p);setTimeout(()=>p.remove(),1000);
  }
}
function giftBanner(user,gtype){
  const meta=SHOP_META[gtype]||{icon:'🎁'};
  const row=document.getElementById('giftBannerRow');
  const b=document.createElement('div');b.className='gift-banner';
  b.textContent=`${meta.icon} ${user} 送了${meta.name||gtype}！`;
  row.appendChild(b);setTimeout(()=>b.remove(),5000);
}

// ── 进度里程碑 ──
let lastMilestoneBucket=-1;
function checkMilestone(pct){
  const bucket=Math.floor(pct/25); // 0/1/2/3
  if(bucket>lastMilestoneBucket && pct>0){
    const milestones={1:'💡 进展不错！送⚡人气票获取提示？',2:'🎯 完成一半了！棒棒糖🍭限时8折！',3:'🚀 就差一点！送🕶️墨镜直接通关！'};
    if(milestones[bucket])showMilestone(milestones[bucket]);
    lastMilestoneBucket=bucket;
  }
}
function showMilestone(msg){
  const host=document.getElementById('hintFloat');
  const div=document.createElement('div');div.className='milestone-hint';
  div.textContent=msg;div.onclick=()=>{div.remove();openGiftShop()};
  host.appendChild(div);setTimeout(()=>div.remove(),8000);
}
toggleDiffPanel(true);
refreshUserState();
updateTierBadge({id:0,name:'黑铁',color:'#6B7280',icon:'🛡️'});
connectWS();

// ── Particle Background (Meoo style) ──
(function(){
    const c=document.getElementById('particleCanvas'),ctx=c.getContext('2d');
    let w,h,particles=[];
    const COLORS=['#00d4ff','#7c3aed','#f59e0b'],COUNT=30;
    function resize(){w=c.width=innerWidth;h=c.height=innerHeight}
    function init(){resize();particles=[];for(let i=0;i<COUNT;i++)particles.push({x:Math.random()*w,y:Math.random()*h,vx:(Math.random()-.5)*0.3,vy:(Math.random()-.5)*0.3,s:Math.random()*2+1.5,o:Math.random()*0.4+0.15,cl:COLORS[Math.floor(Math.random()*COLORS.length)]})}
    function draw(){
        ctx.clearRect(0,0,w,h);
        particles.forEach(p=>{
            p.x+=p.vx;p.y+=p.vy;
            if(p.x<0||p.x>w)p.vx*=-1;if(p.y<0||p.y>h)p.vy*=-1;
            ctx.beginPath();ctx.arc(p.x,p.y,p.s,0,Math.PI*2);
            ctx.fillStyle=p.cl;ctx.globalAlpha=p.o;ctx.fill();
            particles.forEach(p2=>{
                const dx=p.x-p2.x,dy=p.y-p2.y,d=Math.sqrt(dx*dx+dy*dy);
                if(d<120){ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(p2.x,p2.y);ctx.strokeStyle=p.cl;ctx.globalAlpha=(1-d/120)*0.12;ctx.lineWidth=0.5;ctx.stroke()}
            })
        });
        ctx.globalAlpha=1;
        requestAnimationFrame(draw)
    }
    window.addEventListener('resize',resize);
    init();draw();
})();

// ── 倒计时 ──
function updateTimer(remaining) {
  const el = document.getElementById("timerText");
  const display = document.getElementById("timerDisplay");
  if (remaining == null || remaining < 0) { el.textContent = "--:--"; return; }
  const m = Math.floor(remaining / 60);
  const s = remaining % 60;
  el.textContent = String(m).padStart(2,"0") + ":" + String(s).padStart(2,"0");
  display.className = "timer-display";
  if (remaining <= 30) display.classList.add("danger");
  else if (remaining <= 60) display.classList.add("warning");
  else display.classList.add("normal");
}

// ── 自动提示 ──
function showAutoHint(text, revealedChar) {
  const el = document.getElementById("autoHintToast");
  el.textContent = "💡 " + text;
  el.className = "auto-hint-toast";
  setTimeout(() => el.classList.add("show"), 10);
  clearTimeout(el._hide);
  el._hide = setTimeout(() => el.classList.remove("show"), 4000);
}

</script>
</body>
</html>"""





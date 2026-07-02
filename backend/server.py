"""
CCcat 海龟汤 — 合并版服务（单进程）
整合 LLM 分类 + WebSocket 游戏 + 弹幕中继 + 嵌入式前端
"""
import asyncio
import json
import os
import re
import sys
import time
import math
import random as rnd
import subprocess
import webbrowser
from pathlib import Path
from dotenv import load_dotenv
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel
from openai import OpenAI
import uvicorn
from admin import ADMIN_HTML
from overlay import OVERLAY_HTML
from theme_manager import theme_manager
from persistent import PersistentDB
from tiers import TIERS, get_tier, check_tier_up, SCORE_BY_DIFFICULTY, DIFFICULTY_MULTIPLIER
from gift_slots import slot_manager, GIFT_LIBRARY
from spam_filter import spam_filter

# ── 加载 .env ──
_env_path = (Path(sys.executable).resolve().parent / ".env") if getattr(sys, "frozen", False) else (Path(__file__).resolve().parent.parent / ".env")
if _env_path.exists():
    load_dotenv(str(_env_path), encoding="utf-8")
    print(f"[Config] 已加载 .env: {_env_path}")
else:
    _env_fallback = Path(__file__).resolve().parent.parent / ".env" if getattr(sys, "frozen", False) else None
    if _env_fallback and _env_fallback.exists():
        load_dotenv(str(_env_fallback), encoding="utf-8")
        print(f"[Config] 已加载 .env(后备): {_env_fallback}")
    else:
        print(f"[Config] .env 未发现 ({_env_path})，使用默认配置")

# ── 配置 ──
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-v4-flash")

SERVER_PORT = int(os.getenv("SERVER_PORT", "3010"))
FRONTEND_PORT = int(os.getenv("FRONTEND_PORT", "3015"))

# 兼容 exe (PyInstaller) 和开发模式
if getattr(sys, "frozen", False):
    # --onefile: sys._MEIPASS → temp extract dir (bundled assets)
    # --onedir:  sys.executable.parent → exe 所在目录
    if getattr(sys, '_MEIPASS', None):
        PROJECT_ROOT = Path(sys._MEIPASS)
    else:
        PROJECT_ROOT = Path(sys.executable).resolve().parent
    if not (PROJECT_ROOT / "meoo_frontend").exists() and (PROJECT_ROOT.parent / "meoo_frontend").exists():
        PROJECT_ROOT = PROJECT_ROOT.parent
    DATA_ROOT = Path(sys.executable).resolve().parent  # 持久化数据放在 exe 旁边
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    DATA_ROOT = PROJECT_ROOT
FRONTEND_DIR = PROJECT_ROOT / "meoo_frontend"
FRONTEND_DIST = FRONTEND_DIR / "dist"

ANTI_STALL_INTERVAL = 180
ANTI_STALL_DANMAKU = 50
ANTI_STALL_DECAY = 0.8
ANTI_STALL_ENABLED = True
AUTO_START_DELAY = 10
ROUND_TIMEOUT = 300  # 每局最长秒数

MOCK_LEADERBOARD = [
    {"name": "抖音用户_8848", "score": 450},
    {"name": "摸鱼小能手", "score": 320},
    {"name": "吃瓜群众01", "score": 210},
    {"name": "夜猫子剧场", "score": 150},
    {"name": "路过打酱油", "score": 80},
]

FUNCTION_WORDS = {
    "的","了","是","在","和","吗","呢","吧","着","过","得","地","个","一","不","没",
    "有","就","都","而","但","又","如果","因为","所以","然后","于是","向","对","从","到",
    "把","被","给","让","每","只","想","会","能","可以","很","太","非常","已经","正在",
    "曾经","将","要","这","那","你","我","他","她","它","们","上","下","里","外","前",
    "后","中","时","还","也","再","才","刚","做","说","看","来","去",
}


# ── 虚拟货币与礼物商店 ──
GIFT_PRICES = {
    "like": 0,
    "fan_light": 20,
    "popularity": 30,
    "beer": 50,
    "lollipop": 80,
    "sunglasses": 200,
}
GIFT_NAME_MAP = {"like":"like","fan_light":"粉丝灯牌","popularity":"人气票","beer":"啤酒","lollipop":"棒棒糖","sunglasses":"墨镜"}

class CoinSystem:
    def __init__(self):
        self.balances = {}
        self.daily_claimed = {}
        self.vip_status = {}
        self.gift_combo = {}
        self.total_spent = {}

    def get_balance(self, user: str) -> int:
        return self.balances.get(user, 100)

    def add_coins(self, user: str, amount: int):
        current = self.balances.get(user, 100)
        self.balances[user] = max(0, current + amount)

    def spend(self, user: str, amount: int) -> bool:
        if self.get_balance(user) >= amount:
            current = self.balances.get(user, 100)
            self.balances[user] = max(0, current - amount)
            self.total_spent[user] = self.total_spent.get(user, 0) + amount
            return True
        return False

    def claim_daily(self, user: str, today: str) -> bool:
        if self.daily_claimed.get(user) == today:
            return False
        self.daily_claimed[user] = today
        self.add_coins(user, 30)
        return True

    def update_combo(self, user: str) -> dict:
        import time as _t
        now = _t.time()
        c = self.gift_combo.get(user, {"count":0, "last_time":0, "multiplier":1.0})
        if now - c["last_time"] > 30:
            c = {"count":0, "last_time":0, "multiplier":1.0}
        c["count"] += 1
        c["last_time"] = now
        if c["count"] >= 10: c["multiplier"] = 3.0
        elif c["count"] >= 5: c["multiplier"] = 2.0
        elif c["count"] >= 3: c["multiplier"] = 1.5
        else: c["multiplier"] = 1.0
        self.gift_combo[user] = c
        return c

    def get_leaderboard(self, top_n: int = 5) -> list:
        sorted_users = sorted(self.total_spent.items(), key=lambda x: -x[1])
        return [{"user": u, "total_spent": s} for u, s in sorted_users[:top_n]]

    def check_vip(self, user: str) -> bool:
        return self.vip_status.get(user, 0) > __import__("time").time()

    def get_state(self, user: str = "default") -> dict:
        return {
            "balance": self.get_balance(user),
            "vip": self.check_vip(user),
            "combo": self.gift_combo.get(user, {"count":0, "multiplier":1.0}),
        }

    def has_gift(self, user: str, gift_type: str) -> bool:
        price = GIFT_PRICES.get(gift_type, 0)
        if price == 0:
            return True
        return self.get_balance(user) >= price

coins = CoinSystem()

# ── SQLite 持久化层（失败回退内存模式） ──
if getattr(sys, "frozen", False):
    DB_PATH = DATA_ROOT / "backend" / "data" / "persistent.db"
else:
    DB_PATH = Path(__file__).resolve().parent / "data" / "persistent.db"
try:
    db = PersistentDB(DB_PATH)
    print(f"[DB] 持久化就绪: {DB_PATH}")
except Exception as _e:
    print(f"[DB] 初始化失败，回退内存模式: {_e}")
    db = None

# 从持久化存储加载游戏时长配置
if db is not None:
    try:
        saved = db.get_setting("round_timeout")
        if saved is not None:
            ROUND_TIMEOUT = int(saved)
            print(f"[Config] 已加载游戏时长: {ROUND_TIMEOUT}秒")
    except Exception:
        pass
# 从持久化存储恢复礼物槽状态
if db is not None:
    try:
        slot_manager.load_from_db(db)
        print("[GiftSlots] 已恢复槽位状态")
    except Exception as e:
        print(f"[GiftSlots] 加载失败: {e}")
# OpenAI 客户端（懒加载）
_client_instance = None
def get_client():
    global _client_instance
    if _client_instance is None:
        _client_instance = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, timeout=20.0)
    return _client_instance
def recreate_client():
    global _client_instance
    _client_instance = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, timeout=20.0)

frontend_process = None

# ── 工具函数 ──
async def llm_classify(text: str, answer: str, keywords: list[str]) -> str:
    try:
        resp = get_client().chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "判断弹幕与答案的相关性。只回复：是、不是、是也不是"},
                {"role": "user", "content": f"汤底: {answer}\\n关键词: {'、'.join(keywords)}\\n弹幕: {text}"},
            ],
            max_tokens=10, temperature=0.1,
        )
        r = resp.choices[0].message.content.strip()
        if "是也不是" in r: return "是也不是"
        elif "是" in r: return "是"
        else: return "不是"
    except Exception as e:
        print(f"[LLM] classify error: {e}")
        return "不是"

DIFFICULTY_NAME_MAP = {"easy":"简单","medium":"一般","hard":"困难","hell":"地狱","void":"无人区","auto":"自适应"}
GIFT_TAUNTS = {
    "like": ["就这？再来点！", "不够不够，继续！", "节奏带起来！"],
    "fan_light": ["灯牌点亮，真爱粉！", "感谢你的灯牌！"],
    "popularity": ["人气票走一波！", "感谢人气票，排面拉满！"],
    "beer": ["啤酒一瓶，思路打开！", "干杯！喝完这瓶想答案！"],
    "lollipop": ["棒棒糖真甜！", "甜到心里了！"],
    "sunglasses": ["墨镜大佬来了！", "全场最靓的仔！"],
}
COMBO_TAUNTS = {3: "连击x3！稳！", 5: "连击x5！大神！", 10: "连击x10！！无敌！"}

SLOT_TAUNTS = {
    "effect_complete": ["直接通关！太强了！", "故事结束，恭喜通关！"],
    "effect_reveal1": ["揭示一字，真相更近了！", "关键字浮现！"],
    "effect_reveal_sentence": ["完整一句揭开！", "迷雾散开一些了！"],
    "effect_reveal_30p": ["大量内容揭示！", "真相即将大白！"],
}

async def llm_gift_solicit(gift_type: str, context: dict) -> str:
    fallbacks = {
        "人气票": "动动小手送个人气票！",
        "啤酒": "送瓶啤酒，揭示一个关键线索！",
        "棒棒糖": "来个棒棒糖，揭开一句话！",
        "墨镜": "送墨镜，直接通关！",
        "粉丝灯牌": "点亮粉丝灯牌！",
    }
    try:
        resp = get_client().chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "生成礼物索要话术，不超过20字"},
                {"role": "user", "content": f"礼物: {gift_type}, 进度: {context.get('revealProgress',0)*100:.0f}%"},
            ],
            max_tokens=30, temperature=0.8,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return fallbacks.get(gift_type, "感谢大家的支持！")

# ── Connection Manager ──
class ConnectionManager:
    def __init__(self):
        self.active: dict[str, WebSocket] = {}
    async def connect(self, ws: WebSocket, cid: str):
        await ws.accept()
        self.active[cid] = ws
    def disconnect(self, cid: str):
        self.active.pop(cid, None)
    async def broadcast(self, data: dict):
        dead = []
        for cid, ws in self.active.items():
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(cid)
        for cid in dead:
            self.active.pop(cid, None)

manager = ConnectionManager()

# ── 揭示引擎 ──
class RevealEngine:
    @staticmethod
    def is_content_word(char: str) -> bool:
        return bool(re.match(r"[\u4e00-\u9fa5]", char)) and char not in FUNCTION_WORDS
    @staticmethod
    def init_char_states(text: str) -> list[dict]:
        return [{"char": ch, "revealed": not RevealEngine.is_content_word(ch), "isContent": RevealEngine.is_content_word(ch)} for ch in text]
    @staticmethod
    def reveal_char(states: list[dict], target: str) -> list[dict]:
        """Reveal ALL occurrences of target char."""
        return [{**s, "revealed": True} if s["char"] == target else s for s in states]
    @staticmethod
    def get_unrevealed(states: list[dict]) -> list[dict]:
        return [s for s in states if s["isContent"] and not s["revealed"]]
    @staticmethod
    def get_unrevealed_clause(states: list[dict], answer: str) -> list[int]:
        """Find the first clause with unrevealed content words. Returns list of indices to reveal."""
        clauses = re.split(r"(?<=[，。！？、；：])", answer)
        idx = 0
        for clause in clauses:
            if not clause.strip():
                idx += len(clause)
                continue
            start = idx
            end = idx + len(clause)
            for i in range(start, end):
                if i < len(states) and states[i]["isContent"] and not states[i]["revealed"]:
                    return list(range(start, end))
            idx = end
        return []
    @staticmethod
    def get_progress(states: list[dict]) -> tuple:
        content = [s for s in states if s["isContent"]]
        revealed = sum(1 for s in content if s["revealed"])
        total = len(content)
        return revealed, total, (revealed/total*100) if total > 0 else 0

# ── 游戏房间 ──
class GameRoom:
    def __init__(self):
        self.reset()
    def reset(self):
        self.phase = "lobby"
        self.soup_text = ""
        self.soup_answer = ""
        self.soup_keywords = []
        self.char_states = []
        self.qa_history = []
        self.gift_log = []
        self.like_progress = {}  # {slot_id: current_count} 点赞槽位累积
        self.next_difficulty = ""
        self.guess_count = 0
        self.start_time = 0
        self.anti_last_reveal = 0
        self.anti_since_reveal = 0
        self.anti_triggers = 0
        self.fanlight_used = 0
        self.max_fanlight = 3
        self.current_difficulty = "medium"
        self.current_soup_id = ""
        self.round_timeout = ROUND_TIMEOUT
        self.remaining = 0
        # ── 自适应难度追踪 ──
        self.round_correct = 0
        self.round_total = 0
        self.round_correct_times = []  # 每次答对耗时
        self.adaptive_bias = 0  # 累积偏移
        self._auto_start_pending = False
    def to_dict(self):
        _, total, pct = RevealEngine.get_progress(self.char_states)
        return {
            "phase": self.phase, "guessCount": self.guess_count,
            "revealProgress": pct/100, "qaCount": len(self.qa_history),
            "startTime": self.start_time, "remaining": self.remaining,
            "roundTimeout": self.round_timeout,
            "difficulty": self.current_difficulty,
            "difficulty_name": {"easy":"简单","medium":"一般","hard":"困难","hell":"地狱","void":"无人区","auto":"自适应"}.get(self.current_difficulty, self.current_difficulty),
            "nextDifficulty": self.next_difficulty,
        }

room = GameRoom()

# ── 题库 ──
try:
    from data_soups import SOUPS
except ImportError:
    SOUPS = [{"id":"demo","title":"海龟汤","surface":"示例汤面","bottom":"示例汤底","keywords":["示例"],"difficulty":"easy"}]

_anti_stall_task = None
_timer_task = None

async def auto_reveal_and_hint(reason: str = "timeout"):
    """自动揭示一个高频字，并以 auto_hint 消息广播。"""
    cand = [s for s in room.char_states if s["isContent"] and not s["revealed"]]
    if not cand:
        return
    freq = {}
    for ch in room.soup_answer:
        if RevealEngine.is_content_word(ch):
            freq[ch] = freq.get(ch, 0) + 1
    cand.sort(key=lambda s: freq.get(s["char"], 0), reverse=True)
    target = cand[0]["char"]
    room.char_states = RevealEngine.reveal_char(room.char_states, target)
    room.anti_last_reveal = time.time()
    room.anti_since_reveal = 0
    room.anti_triggers += 1
    await manager.broadcast({"type": "reveal_update", "charStates": room.char_states, "auto": True})
    await manager.broadcast({
        "type": "auto_hint",
        "text": "自动揭示一关键词",
        "reason": reason,
        "revealed": target,
    })
    _, t, p = RevealEngine.get_progress(room.char_states)
    if p >= 100 and room.phase != "complete":
        room.phase = "complete"
        await manager.broadcast({"type": "game_end", "winner": "系统", "charStates": room.char_states})

async def timer_tick_loop():
    """每秒广播剩余时间，超时强制结束游戏。"""
    while True:
        await asyncio.sleep(1)
        try:
            # 自动开始检测：游戏结束后安排延迟开始
            if room.phase == "complete" and not room._auto_start_pending:
                room._auto_start_pending = True
                asyncio.create_task(auto_start_after_delay())
            if not room.soup_answer or room.phase in ("idle", "complete", "lobby"):
                continue
            elapsed = time.time() - room.start_time
            remaining = max(0, room.round_timeout - int(elapsed))
            room.remaining = remaining
            # 广播剩余时间
            await manager.broadcast({"type": "timer", "remaining": remaining, "elapsed": int(elapsed)})
            # 超时强制结束
            if remaining <= 0:
                await manager.broadcast({"type": "timer", "remaining": 0, "elapsed": int(elapsed)})
                # 揭示所有未揭示字
                for s in room.char_states:
                    if s["isContent"] and not s["revealed"]:
                        s["revealed"] = True
                room.phase = "complete"
                await manager.broadcast({"type": "reveal_update", "charStates": room.char_states, "auto": True})
                await manager.broadcast({"type": "game_end", "winner": "系统", "charStates": room.char_states})
        except Exception as e:
            print(f"[Timer] Error: {e}")

async def auto_start_after_delay():
    """游戏结束后等待 N 秒，自动开始下一局。"""
    await asyncio.sleep(AUTO_START_DELAY)
    try:
        if room.phase == "complete":
            print("[AutoStart] 自动开始下一局")
            await game_start("auto")
    except Exception as e:
        print(f"[AutoStart] Error: {e}")
    finally:
        room._auto_start_pending = False

async def anti_stall_loop():
    """后备防卡死：弹幕冷场时自动揭示。"""
    while True:
        await asyncio.sleep(30)
        try:
            if not room.soup_answer or room.phase in ("idle", "complete", "lobby"):
                continue
            if not ANTI_STALL_ENABLED:
                continue
            now = time.time()
            decay = ANTI_STALL_DECAY ** room.anti_triggers
            time_cond = (now - room.anti_last_reveal) >= (ANTI_STALL_INTERVAL * decay)
            danmaku_cond = room.anti_since_reveal >= (ANTI_STALL_DANMAKU * decay)
            if time_cond or danmaku_cond:
                await auto_reveal_and_hint("anti_stall")
        except Exception as e:
            print(f"[AntiStall] Error: {e}")
            await asyncio.sleep(30)

# ── 自适应难度 ──
DIFFICULTY_ORDER = ["easy", "medium", "hard", "hell", "void"]

def compute_adaptive_difficulty() -> str:
    """根据本局表现计算下一局难度。"""
    cur_idx = DIFFICULTY_ORDER.index(room.current_difficulty) if room.current_difficulty in DIFFICULTY_ORDER else 1
    if room.round_total < 5:
        return room.current_difficulty  # 数据太少不调
    correct_rate = room.round_correct / max(room.round_total, 1)
    avg_time = (sum(room.round_correct_times) / max(len(room.round_correct_times), 1)) if room.round_correct_times else 999
    bias = 0
    # 正确率高 + 答得快 → 太难了，升难度
    if correct_rate > 0.6 and avg_time < 60:
        bias = +1
    elif correct_rate > 0.5 and avg_time < 120:
        bias = +1
    # 正确率低 + 答得慢 → 太简单了，降难度
    elif correct_rate < 0.15 or avg_time > 300:
        bias = -1
    elif correct_rate < 0.3 and avg_time > 180:
        bias = -1
    # 累积偏移，限制单次最多变1级
    room.adaptive_bias += bias
    net = max(-1, min(1, room.adaptive_bias))
    new_idx = max(0, min(len(DIFFICULTY_ORDER) - 1, cur_idx + net))
    room.adaptive_bias -= net  # 消耗已用的偏移
    new_diff = DIFFICULTY_ORDER[new_idx]
    print(f"[Adaptive] {room.current_difficulty}→{new_diff} (rate={correct_rate:.0%} avg_t={avg_time:.0f}s bias={room.adaptive_bias})")
    return new_diff


# ── 配置热加载 ──
def reload_config():
    """从 .env 重新加载配置，不重启服务。"""
    global LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, ROUND_TIMEOUT
    env_path = DATA_ROOT / ".env"
    if not env_path.exists():
        return False, ".env 不存在"
    load_dotenv(str(env_path), encoding="utf-8", override=True)
    LLM_API_KEY = os.getenv("LLM_API_KEY", LLM_API_KEY)
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", LLM_BASE_URL)
    LLM_MODEL = os.getenv("LLM_MODEL", LLM_MODEL)
    try:
        ROUND_TIMEOUT = int(os.getenv("ROUND_TIMEOUT", str(ROUND_TIMEOUT)))
    except ValueError:
        pass
    recreate_client()
    return True, "配置已热加载"

@asynccontextmanager
async def lifespan(app: FastAPI):
    global frontend_process, _anti_stall_task, _timer_task
    if FRONTEND_DIST.exists() and (FRONTEND_DIST / "index.html").exists():
        print(f"[Server] 静态文件就绪: {FRONTEND_DIST}")
    elif FRONTEND_DIR.exists() and (FRONTEND_DIR / "package.json").exists():
        try:
            print(f"[Server] 尝试启动前端开发服务器...")
            if not (FRONTEND_DIR / "node_modules").exists():
                subprocess.run(["npm","install"], cwd=str(FRONTEND_DIR), shell=True, capture_output=True)
            frontend_process = subprocess.Popen(
                ["npm","run","dev"], cwd=str(FRONTEND_DIR), shell=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            print(f"[Server] 前端启动失败: {e}")
    print(f"[Server] 嵌入式前端可用: http://localhost:{SERVER_PORT}")
    try:
        webbrowser.open(f"http://localhost:{SERVER_PORT}")
    except Exception:
        pass
    _anti_stall_task = asyncio.create_task(anti_stall_loop())
    print("[Server] 防卡死机制已启动")
    _timer_task = asyncio.create_task(timer_tick_loop())
    print("[Server] 倒计时已启动")
    yield
    if _anti_stall_task and not _anti_stall_task.done():
        _anti_stall_task.cancel()
    if _timer_task and not _timer_task.done():
        _timer_task.cancel()
    if frontend_process:
        frontend_process.kill()

app = FastAPI(title="CCcat 海龟汤", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Request Models ──
class ClassifyReq(BaseModel):
    text: str; answer: str; keywords: list[str]
class HintReq(BaseModel):
    qaHistory: list[dict] = []; answer: str = ""; keywords: list[str] = []
class GiftSolicitReq(BaseModel):
    giftType: str = ""; context: dict = {}
class ConfigReq(BaseModel):
    api_key: str = ""
    base_url: str = ""
    model: str = ""
class PushDanmakuReq(BaseModel):
    user: str; content: str

# ── API Endpoints ──
@app.get("/health")
async def health():
    return {"status": "ok", "model": LLM_MODEL, "api_base": LLM_BASE_URL, "phase": room.phase, "connections": len(manager.active)}

@app.post("/classify")
async def classify(req: ClassifyReq):
    t0 = time.time()
    passed, reason = spam_filter.check_danmaku(req.text, "__api__")
    if not passed:
        return {"text": req.text, "answerType": "不是", "layer": reason, "latencyMs": (time.time()-t0)*1000}
    result = await llm_classify(req.text, req.answer, req.keywords)
    return {"text": req.text, "answerType": result, "layer": "llm", "latencyMs": (time.time()-t0)*1000}

@app.post("/hint")
async def hint(req: HintReq):
    # LLM 方向提示已移除，使用固定提示文本
    return {"hint": "想想故事里谁最可疑？", "note": "fixed_fallback"}

@app.post("/gift-solicit")
async def gift_solicit(req: GiftSolicitReq):
    return {"script": await llm_gift_solicit(req.giftType, req.context), "giftType": req.giftType}

@app.get("/api/config")
async def get_config():
    return {"api_key_configured": bool(LLM_API_KEY), "base_url": LLM_BASE_URL, "model": LLM_MODEL}

@app.post("/api/config")
async def update_config(req: ConfigReq):
    global LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, _client_instance
    changed = False
    if req.api_key:
        LLM_API_KEY = req.api_key; changed = True
    if req.base_url:
        LLM_BASE_URL = req.base_url; changed = True
    if req.model:
        LLM_MODEL = req.model; changed = True
    if changed:
        recreate_client()
    return {"ok": True, "model": LLM_MODEL, "base_url": LLM_BASE_URL}

@app.post("/api/barrage/push")
async def push_barrage(req: PushDanmakuReq):
    await manager.broadcast({"type": "danmu", "data": {"user": req.user, "content": req.content}})
    return {"ok": True}

@app.get("/api/game/state")
async def game_state():
    return room.to_dict()

@app.post("/api/game/start")
async def game_start(difficulty: str = "medium"):
    # 消耗预设难度（来自礼物或上局点赞）
    if room.next_difficulty:
        difficulty = room.next_difficulty
        room.next_difficulty = ""
    # 自适应难度
    if difficulty == "auto":
        difficulty = compute_adaptive_difficulty()
    diff = difficulty if difficulty in DIFFICULTY_MULTIPLIER else "medium"
    candidates = [s for s in SOUPS if s.get("difficulty") == diff]
    if not candidates:
        candidates = [s for s in SOUPS if s.get("difficulty") == "medium"] or SOUPS
    soup = rnd.choice(candidates)
    room.reset()
    room.soup_text = soup["surface"]
    room.soup_answer = soup["bottom"]
    room.soup_keywords = soup["keywords"]
    room.current_difficulty = diff
    room.current_soup_id = soup.get("id", "")
    room.char_states = RevealEngine.init_char_states(room.soup_answer)
    room.phase = "reading"
    room.start_time = time.time()
    room.anti_last_reveal = room.start_time
    room.remaining = room.round_timeout
    await manager.broadcast({
        "type": "game_start", "surface": room.soup_text,
        "keywords": room.soup_keywords, "charStates": room.char_states,
        "difficulty": diff, "difficulty_name": {"easy":"简单","medium":"一般","hard":"困难","hell":"地狱","void":"无人区","auto":"自适应"}.get(diff, diff), "remaining": room.remaining,
        "roundTimeout": room.round_timeout,
    })
    return {"ok": True, "surface": room.soup_text, "difficulty": diff}

# 难度选项（给前端用）
@app.get("/api/game/difficulties")
async def game_difficulties():
    return {"difficulties": [
        {"id": k, "name": k, "multiplier": v} for k, v in DIFFICULTY_MULTIPLIER.items()
    ]}



# ── 虚拟货币 API ──
@app.get("/api/coin/balance")
async def coin_balance(user: str = "default"):
    return {"balance": coins.get_balance(user), "vip": coins.check_vip(user)}

@app.post("/api/coin/daily")
async def coin_daily(user: str = "default"):
    today = __import__("time").strftime("%Y-%m-%d")
    ok = coins.claim_daily(user, today)
    return {"ok": ok, "balance": coins.get_balance(user), "reward": 30 if ok else 0}

@app.post("/api/coin/recharge")
async def coin_recharge(user: str = "default", amount: int = 100):
    coins.add_coins(user, amount)
    return {"ok": True, "balance": coins.get_balance(user), "added": amount}

@app.get("/api/coin/leaderboard")
async def coin_leaderboard():
    return {"leaderboard": coins.get_leaderboard(5)}

@app.get("/api/gift/shop")
async def gift_shop():
    return {"gifts": [{"type": k, "name": GIFT_NAME_MAP.get(k, k), "price": v} for k, v in GIFT_PRICES.items()]}

@app.get("/api/coin/state")
async def coin_state(user: str = "default"):
    return coins.get_state(user)

# ── 签到完整版 ──
SIGNIN_REWARD_MAP = {1: 30, 2: 30, 3: 30, 4: 50, 5: 80, 6: 100, 7: 150}
DEFAULT_SIGNIN_REWARD = 50

@app.get("/api/signin")
async def signin_status(user: str = "default"):
    if db is None:
        return {"status": "unavailable", "msg": "持久化未启用", "streak": 0, "reward": 0, "today_done": False}
    ck = db.get_checkin(user)
    today = time.strftime("%Y-%m-%d")
    streak = ck.get("streak", 0) if ck else 0
    last_day = ck.get("last_day", "") if ck else ""
    today_done = (last_day == today)
    # 今日若已签到，streak 已是当前；否则展示继续可获得的奖励档
    show_streak = streak + (0 if today_done else 1)
    reward = SIGNIN_REWARD_MAP.get(show_streak if show_streak <= 7 else 7, DEFAULT_SIGNIN_REWARD)
    return {
        "status": "ok" if not today_done else "repeat",
        "streak": streak,
        "total_days": (ck.get("total_days", 0) if ck else 0),
        "today_done": today_done,
        "reward": reward,
        "reward_map": SIGNIN_REWARD_MAP,
    }

@app.post("/api/signin")
async def do_signin(user: str = "default"):
    if db is None:
        return {"status": "unavailable", "msg": "持久化未启用"}
    today = time.strftime("%Y-%m-%d")
    yesterday = (time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400)))
    ck = db.get_checkin(user)
    if ck and ck.get("last_day") == today:
        return {"status": "repeat", "msg": "今天已签到", "streak": ck.get("streak", 0),
                "reward": 0, "balance": coins.get_balance(user)}
    if ck and ck.get("last_day") == yesterday:
        new_streak = (ck.get("streak", 0) or 0) + 1
    else:
        new_streak = 1
    reward = SIGNIN_REWARD_MAP.get(new_streak if new_streak <= 7 else 7, DEFAULT_SIGNIN_REWARD)
    db.upsert_checkin({
        "name": user, "last_day": today, "streak": new_streak,
        "total_days": ((ck.get("total_days", 0) if ck else 0) + 1),
    })
    coins.add_coins(user, reward)
    return {"status": "ok", "reward": reward, "streak": new_streak,
            "balance": coins.get_balance(user)}

# ── 排行榜（带段位） ──
@app.get("/api/leaderboard")
async def leaderboard(limit: int = 10):
    if db is None:
        return {"leaderboard": [], "source": "memory"}
    users = db.get_top_users(limit)
    # 始终将假数据与真人数据合并，真人按分数排在前面
    mock_list = [
        {"name": u["name"], "score": u["score"],
         "tier": get_tier(u["score"]),
         "combo": 0, "total_gifts": 0}
        for u in MOCK_LEADERBOARD
    ]
    real_list = [
        {"name": u["name"], "score": u.get("score", 0),
         "tier": get_tier(u.get("score", 0)),
         "combo": u.get("combo", 0),
         "total_gifts": u.get("total_gifts", 0)}
        for u in users
    ]
    merged = sorted(real_list + mock_list, key=lambda x: x["score"], reverse=True)[:limit]
    return {"leaderboard": merged, "source": "mixed" if real_list else "mock"}

# ── 礼物别名 API ──
@app.get("/api/gift/aliases")
async def get_aliases():
    if db is None:
        return {"aliases": []}
    return {"aliases": db.get_aliases()}

class AliasReq(BaseModel):
    alias: str
    gifts: str = ""
    effect: str = ""
    enabled: int = 1

@app.post("/api/gift/aliases")
async def add_alias(req: AliasReq):
    if db is None:
        return {"ok": False, "msg": "持久化未启用"}
    db.upsert_alias(req.alias, req.gifts, req.effect, 1 if req.enabled else 0)
    return {"ok": True, "alias": req.alias}

@app.put("/api/gift/aliases/{alias}")
async def update_alias(alias: str, req: AliasReq):
    if db is None:
        return {"ok": False, "msg": "持久化未启用"}
    db.upsert_alias(alias, req.gifts, req.effect, 1 if req.enabled else 0)
    return {"ok": True, "alias": alias}

@app.delete("/api/gift/aliases/{alias}")
async def delete_alias(alias: str):
    if db is None:
        return {"ok": False, "msg": "持久化未启用"}
    db.del_alias(alias)
    return {"ok": True}

# ── 触发器 API ──
@app.get("/api/triggers")
async def get_triggers():
    if db is None:
        return {"triggers": []}
    return {"triggers": db.get_triggers()}

class TriggerReq(BaseModel):
    type: str
    target: str = "*"
    effect: str = ""
    value: str = ""
    enabled: int = 1

@app.post("/api/triggers")
async def add_trigger(req: TriggerReq):
    if db is None:
        return {"ok": False, "msg": "持久化未启用"}
    tid = db.add_trigger(req.type, req.target, req.effect, req.value, 1 if req.enabled else 0)
    return {"ok": True, "id": tid}

@app.delete("/api/triggers/{tid}")
async def delete_trigger(tid: int):
    if db is None:
        return {"ok": False, "msg": "持久化未启用"}
    db.del_trigger(tid)
    return {"ok": True}

# ── 礼物购买（扣金币，触发效果） ──
class BuyGiftReq(BaseModel):
    gift_type: str
    user: str = "default"

@app.post("/api/gift/buy")
async def buy_gift(req: BuyGiftReq):
    price = GIFT_PRICES.get(req.gift_type, 0)
    if price == 0:
        return {"ok": False, "msg": "该礼物无需购买"}
    if not coins.spend(req.user, price):
        return {"ok": False, "msg": "金币不足", "balance": coins.get_balance(req.user)}
    # 余额已扣，触发等价于送礼效果
    await handle_gift({"nickname": req.user, "giftName": req.gift_type, "count": 1})
    return {"ok": True, "balance": coins.get_balance(req.user), "gift_type": req.gift_type}

# ── WebSocket ──
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    cid = f"client_{len(manager.active)}_{int(time.time())}"
    await manager.connect(ws, cid)
    await ws.send_json({"type": "state_sync", "room": room.to_dict()})
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            t = msg.get("type", "")
            if t == "danmaku":
                await handle_danmaku(msg)
            elif t == "gift":
                await handle_gift(msg)
            elif t == "start_round":
                await game_start(msg.get("difficulty", "medium"))
            elif t == "buy_gift":
                await buy_gift(BuyGiftReq(gift_type=msg.get("gift_type",""), user=msg.get("user","default")))
            elif t == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(cid)

async def add_score(user: str, delta: int, broadcast: bool = True):
    """加分并检查段位升级。delta 可为负。db 不可用时静默跳过持久化。"""
    if delta == 0:
        return
    if db is not None:
        u = db.get_user(user) or {"name": user, "score": 0, "combo": 0, "max_combo": 0,
                                  "total_coins": 0, "total_gifts": 0}
        old_score = u.get("score", 0) or 0
        new_score = max(0, old_score + delta)
        u.update({
            "name": user, "score": new_score,
            "last_seen": time.time(),
            "total_coins": (u.get("total_coins", 0) or 0) + max(0, delta),
        })
        db.upsert_user(u)
        tier_up = check_tier_up(old_score, new_score)
        if tier_up:
            db.record_tier_history(user, tier_up["from"]["name"], tier_up["to"]["name"], new_score)
            if broadcast:
                await manager.broadcast({
                    "type": "tier_up", "user": user,
                    "from_tier": tier_up["from"], "to_tier": tier_up["to"],
                    "delta": tier_up["delta"], "score": new_score,
                    "msg": f"🎉 恭喜 {user} 升级到 {tier_up['to']['name']}！",
                })
        if broadcast:
            await manager.broadcast({
                "type": "score_update", "user": user,
                "score": new_score, "tier": get_tier(new_score),
            })
    else:
        # 内存兜底（无持久化）— 仍广播以便前端展示
        if broadcast:
            await manager.broadcast({
                "type": "score_update", "user": user,
                "score": delta, "tier": get_tier(delta),
            })

async def handle_danmaku(msg: dict):
    text = msg.get("text","").strip()
    user = msg.get("nickname","观众")
    if not text or not room.soup_answer:
        return
    # 三层次弹幕过滤（静默丢弃）
    passed, reason = spam_filter.check_danmaku(text, user)
    if not passed:
        return
    # Track A: 逐字揭示 — 全文同字同时揭示
    any_revealed = False
    for ch in text:
        if ch in room.soup_answer and RevealEngine.is_content_word(ch):
            if any(s["char"]==ch and not s["revealed"] for s in room.char_states):
                room.char_states = RevealEngine.reveal_char(room.char_states, ch)
                any_revealed = True
    if any_revealed:
        room.anti_last_reveal = time.time()
        room.anti_since_reveal = 0
        room.anti_triggers = 0
        await manager.broadcast({"type":"reveal_update","charStates":room.char_states})
    else:
        room.anti_since_reveal += 1
    result = await llm_classify(text, room.soup_answer, room.soup_keywords)
    room.guess_count += 1
    room.qa_history.append({"user":user,"question":text,"result":result,"timestamp":time.time()})
    # 自适应难度追踪
    room.round_total += 1
    if result in ("是", "是也不是"):
        room.round_correct += 1
        room.round_correct_times.append(time.time() - room.start_time)
    await manager.broadcast({"type":"classification","text":text,"user":user,"answerType":result,"layer":"llm"})
    # 命中加分（按当前难度）
    if result in ("是", "是也不是"):
        base = SCORE_BY_DIFFICULTY.get(room.current_difficulty, 15)
        delta = base if result == "是" else base // 2  # 「是也不是」半分
        await add_score(user, delta)
    _, total, pct = RevealEngine.get_progress(room.char_states)
    if pct >= 100:
        room.phase = "complete"
        await manager.broadcast({"type":"game_end","winner":user,"charStates":room.char_states})

async def handle_gift(msg: dict):
    user = msg.get("nickname","观众")
    gift_name = msg.get("giftName","")
    gift_value = int(msg.get("diamondCount", 0) or 0)
    gift_count = msg.get("count", 1)

    # ── 通过礼物槽位系统解析 ──
    slot_id = slot_manager.resolve_gift(gift_name)
    if not slot_id:
        return

    # ── 点赞模式：槽位绑定的礼物可累积点赞数，达到阈值后揭示一字 ──
    slot_state = slot_manager.get_slot_state(slot_id)
    is_like_mode = slot_state and slot_state.get("like_mode", False)
    price = 0
    gift_info = GIFT_LIBRARY.get(gift_name, {})
    if is_like_mode:
        threshold = slot_state.get("like_threshold", 500)
        progress = room.like_progress.get(slot_id, 0) + gift_count
        room.like_progress[slot_id] = progress
        await manager.broadcast({"type":"like_update", "slotId": slot_id, "progress": progress, "threshold": threshold})
        if progress >= threshold:
            room.like_progress[slot_id] = 0
            room.anti_last_reveal = time.time()
            room.anti_since_reveal = 0
            room.anti_triggers = 0
            u = RevealEngine.get_unrevealed(room.char_states)
            if u:
                room.char_states = RevealEngine.reveal_char(room.char_states, rnd.choice(u)["char"])
                await manager.broadcast({"type":"reveal_update","charStates":room.char_states})
            r2, t2, p2 = RevealEngine.get_progress(room.char_states)
            if r2 == t2 and t2 > 0 and room.phase != "complete":
                room.phase = "complete"
                await manager.broadcast({"type":"game_end","winner":user,"charStates":room.char_states})
        # 点赞模式：跳过价格/连击/普通效果，但难度切换仍然执行
        # （不 return，让下面的难度派发逻辑继续运行）

    # ── 价格检查 + 连击（非点赞模式才执行） ──
    if not is_like_mode:
        price = gift_info.get("coins", 0)
        if price > 0:
            if not coins.spend(user, price):
                await manager.broadcast({"type":"gift_error","user":user,"msg":f"金币不足！{gift_name}需要{price}金币"})
                return

        # ── 连击 ──
        combo = coins.update_combo(user)
        room.gift_log.append({"user":user,"giftName":gift_name,"slotId":slot_id,"time":time.time()})
        if gift_value > 0:
            await add_score(user, gift_value)
    else:
        combo = {"count": 0, "multiplier": 1.0}
    if db is not None:
        try:
            db.log_gift(user, gift_name, gift_value or price)
            u = db.get_user(user) or {"name": user}
            db.upsert_user({**u, "name": user, "total_gifts": (u.get("total_gifts",0) or 0) + 1,
                            "last_seen": time.time()})
        except Exception as e:
            print(f"[DB] log_gift error: {e}")
    multiplier = combo["multiplier"]
    bonus_reveal = 0
    if multiplier >= 3.0:
        bonus_reveal = 2
    elif multiplier >= 2.0:
        bonus_reveal = 1

    # ── 难度槽派发 ──
    if slot_id.startswith("diff_"):
        diff_map = {"diff_easy":"easy","diff_medium":"medium","diff_hard":"hard","diff_hell":"hell","diff_void":"void"}
        nd = diff_map.get(slot_id)
        if nd:
            room.next_difficulty = nd
            nd_name = DIFFICULTY_NAME_MAP.get(nd, nd)
            await manager.broadcast({"type":"difficulty_scheduled", "nextDifficulty": nd, "nextDifficultyName": nd_name})
            print(f"[Difficulty] 礼物→槽位{slot_id} = {nd} ({nd_name})")

    # ── 效果槽派发（点赞模式不执行，已在上方处理完揭示） ──
    elif slot_id == "effect_complete" and not is_like_mode:
        for s in room.char_states:
            if s["isContent"] and not s["revealed"]:
                s["revealed"] = True
        room.phase = "complete"
        await manager.broadcast({"type":"reveal_update","charStates":room.char_states})
        await manager.broadcast({"type":"game_end","winner":user,"charStates":room.char_states})

    elif slot_id == "effect_reveal1":
        revealed_any = False
        for _ in range(1 + bonus_reveal):
            u = RevealEngine.get_unrevealed(room.char_states)
            if u:
                target = rnd.choice(u)["char"]
                room.char_states = RevealEngine.reveal_char(room.char_states, target)
                revealed_any = True
        if revealed_any:
            await manager.broadcast({"type":"reveal_update","charStates":room.char_states})

    elif slot_id == "effect_reveal_sentence":
        revealed_any = False
        for _ in range(1 + bonus_reveal):
            clause = RevealEngine.get_unrevealed_clause(room.char_states, room.soup_answer)
            if clause:
                for ch in set(room.char_states[i]["char"] for i in clause):
                    if RevealEngine.is_content_word(ch):
                        room.char_states = RevealEngine.reveal_char(room.char_states, ch)
                        revealed_any = True
        if revealed_any:
            await manager.broadcast({"type":"reveal_update","charStates":room.char_states})

    elif slot_id == "effect_reveal_30p":
        u = RevealEngine.get_unrevealed(room.char_states)
        if u:
            target_count = max(1, int(len(u) * 0.3))
            targets = rnd.sample(u, min(target_count, len(u)))
            for s in targets:
                room.char_states = RevealEngine.reveal_char(room.char_states, s["char"])
            await manager.broadcast({"type":"reveal_update","charStates":room.char_states})

    # ── 完成检查 ──
    r,t,p = RevealEngine.get_progress(room.char_states)
    if r == t and t > 0 and room.phase != "complete":
        room.phase = "complete"
        await manager.broadcast({"type":"game_end","winner":user,"charStates":room.char_states})

    # ── 广播礼物效果 ──
    balance = coins.get_balance(user)
    taunt_text = ""
    combo_count = combo["count"]
    if combo_count >= 10:
        taunt_text = COMBO_TAUNTS.get(10, "")
    elif combo_count >= 5:
        taunt_text = COMBO_TAUNTS.get(5, "")
    elif combo_count >= 3:
        taunt_text = COMBO_TAUNTS.get(3, "")
    if not taunt_text:
        taunt_list = SLOT_TAUNTS.get(slot_id, ["感谢赠送！"])
        taunt_text = rnd.choice(taunt_list)
    script = f"感谢{user}的{gift_name}！"
    if taunt_text:
        script += " " + taunt_text
    await manager.broadcast({
        "type":"gift_effect",
        "user":user,
        "giftName":gift_name,
        "slotId":slot_id,
        "coins": gift_value or price,
        "icon": gift_info.get("icon", ""),
        "script": script,
        "taunt": taunt_text,
        "combo": combo["count"],
        "multiplier": multiplier,
        "balance": balance,
        "spent": price,
    })


# ── Admin 路由 ──
@app.get("/admin")
async def admin_page():
    return HTMLResponse(content=ADMIN_HTML, headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"})

@app.get("/overlay")
async def overlay_page():
    active = theme_manager.get_active()
    html = theme_manager.apply_to_html(OVERLAY_HTML, active)
    return HTMLResponse(content=html)

class BannedWordReq(BaseModel):
    word: str

@app.get("/api/admin/banned-words")
async def get_banned_words():
    return {"words": spam_filter.banned.get_all()}

@app.post("/api/admin/banned-words")
async def add_banned_word(req: BannedWordReq):
    ok = spam_filter.banned.add(req.word)
    return {"ok": ok, "word": req.word}

@app.delete("/api/admin/banned-words")
async def delete_banned_word(req: BannedWordReq):
    ok = spam_filter.banned.remove(req.word)
    return {"ok": ok, "word": req.word}

@app.put("/api/admin/banned-words")
async def set_banned_words(req: list[str]):
    spam_filter.banned.set_all(req)
    return {"ok": True, "count": len(req)}

@app.post("/api/admin/config-reload")
async def admin_reload_config():
    ok, msg = reload_config()
    return {"ok": ok, "msg": msg}

# ── 防卡死配置 ──

@app.get("/api/admin/anti-stall-config")
async def get_anti_stall_config():
    return {
        "enabled": ANTI_STALL_ENABLED,
        "interval": ANTI_STALL_INTERVAL,
        "danmaku": ANTI_STALL_DANMAKU,
    }

@app.post("/api/admin/anti-stall-config")
async def set_anti_stall_config(req: dict):
    global ANTI_STALL_ENABLED, ANTI_STALL_INTERVAL, ANTI_STALL_DANMAKU
    if "enabled" in req:
        ANTI_STALL_ENABLED = bool(req["enabled"])
    if "interval" in req:
        ANTI_STALL_INTERVAL = max(30, int(req["interval"]))
    if "danmaku" in req:
        ANTI_STALL_DANMAKU = max(5, int(req["danmaku"]))
    return {"ok": True}


# ── 游戏时长配置 ──

@app.get("/api/admin/game-config")
async def get_game_config():
    return {"roundTimeout": ROUND_TIMEOUT}

@app.post("/api/admin/game-config")
async def set_game_config(req: dict):
    global ROUND_TIMEOUT
    if "roundTimeout" in req:
        val = int(req["roundTimeout"])
        ROUND_TIMEOUT = max(30, min(3600, val))
        if db is not None:
            db.set_setting("round_timeout", str(ROUND_TIMEOUT))
        print(f"[Config] 游戏时长已更新: {ROUND_TIMEOUT}秒")
    return {"ok": True}


# ── 礼物槽位管理（通过 gift_slots.py 的 slot_manager）──

@app.get("/api/admin/slots")
async def get_slots():
    return {"slots": slot_manager.get_all_slots()}

class AssignSlotReq(BaseModel):
    slot_id: str
    gift_name: str

@app.post("/api/admin/slots/assign")
async def assign_slot(req: AssignSlotReq):
    slot_manager.assign_gift(req.slot_id, req.gift_name)
    if db is not None:
        slot_manager.save_to_db(db)
    await manager.broadcast({"type": "slots_updated"})
    return {"ok": True}

class ToggleSlotReq(BaseModel):
    slot_id: str
    enabled: bool

@app.post("/api/admin/slots/toggle")
async def toggle_slot(req: ToggleSlotReq):
    slot_manager.set_enabled(req.slot_id, req.enabled)
    if db is not None:
        slot_manager.save_to_db(db)
    await manager.broadcast({"type": "slots_updated"})
    return {"ok": True}

class SlotLikeConfigReq(BaseModel):
    slot_id: str
    like_mode: bool
    like_threshold: int = 500

@app.post("/api/admin/slots/like-config")
async def set_slot_like_config(req: SlotLikeConfigReq):
    slot_manager.set_like_config(req.slot_id, req.like_mode, req.like_threshold)
    if db is not None:
        slot_manager.save_to_db(db)
    await manager.broadcast({"type": "slots_updated"})
    return {"ok": True}

@app.get("/api/admin/gifts/search")
async def search_gifts(q: str = ""):
    return {"gifts": slot_manager.search_gifts(q)}

@app.get("/api/adaptive/difficulty")
async def get_adaptive_difficulty():
    return {
        "current": room.current_difficulty,
        "suggested": compute_adaptive_difficulty(),
        "correct_rate": round(room.round_correct / max(room.round_total, 1), 3) if room.round_total >= 5 else None,
        "rounds_tracked": room.round_total,
    }

# ── 补充的管理员路由 ──

# 设置下局难度
@app.post("/api/admin/difficulty")
async def admin_set_difficulty(req: dict):
    diff = req.get("difficulty", "medium")
    room.next_difficulty = diff
    name = {"easy":"简单","medium":"一般","hard":"困难","hell":"地狱","void":"无人区","auto":"自适应"}.get(diff, diff)
    await manager.broadcast({"type":"difficulty_scheduled", "nextDifficulty": diff, "nextDifficultyName": name})
    return {"ok": True, "difficulty": diff}

# 强制揭示所有
@app.post("/api/admin/force-reveal")
async def admin_force_reveal():
    if room.char_states:
        for s in room.char_states:
            if s["isContent"] and not s["revealed"]:
                s["revealed"] = True
        room.phase = "complete"
        await manager.broadcast({"type": "reveal_update", "charStates": room.char_states})
    await manager.broadcast({"type": "game_end", "winner": "管理员"})
    return {"ok": True}

# 重置游戏
@app.post("/api/admin/reset")
async def admin_reset():
    room.reset()
    await manager.broadcast({"type": "game_end", "winner": "系统"})
    return {"ok": True}

# 题库管理
@app.get("/api/admin/soups")
async def admin_get_soups(difficulty: str = ""):
    if difficulty:
        candidates = [s for s in SOUPS if s.get("difficulty") == difficulty]
    else:
        candidates = SOUPS
    return {"soups": candidates}

@app.post("/api/admin/soups/delete")
async def admin_delete_soup(req: dict):
    sid = req.get("id", "")
    global SOUPS
    SOUPS = [s for s in SOUPS if s.get("id") != sid]
    return {"ok": True}

@app.post("/api/admin/soups/add")
async def admin_add_soup(req: dict):
    new_id = f"soup-{len(SOUPS)+1:03d}"
    soup = {
        "id": req.get("id", new_id),
        "title": req.get("title", ""),
        "surface": req.get("surface", ""),
        "bottom": req.get("bottom", ""),
        "keywords": req.get("keywords", []),
        "difficulty": req.get("difficulty", "medium"),
    }
    SOUPS.append(soup)
    return {"ok": True, "id": soup["id"]}

@app.post("/api/admin/soups/import")
async def admin_import_soups(req: dict):
    soups = req.get("soups", [])
    count = 0
    for s in soups:
        if not s.get("surface") or not s.get("bottom"):
            continue
        s["id"] = s.get("id", f"soup-{len(SOUPS)+1:03d}")
        s["keywords"] = s.get("keywords", [])
        s["difficulty"] = s.get("difficulty", "medium")
        SOUPS.append(s)
        count += 1
    return {"ok": True, "count": count}

# AI出题
@app.post("/api/admin/ai-generate")
async def admin_ai_generate(req: dict):
    diff = req.get("difficulty", "medium")
    count = req.get("count", 5)
    try:
        client = get_client()
        prompt = f"""生成{count}个海龟汤谜题，难度：{diff}。
每个谜题包含：title(标题), surface(汤面), bottom(汤底), keywords(关键词数组), difficulty(难度)。
汤面要有趣有悬念，汤底要合理完整。以JSON数组格式返回。
仅返回JSON，不要markdown包裹。"""
        resp = client.chat.completions.create(
            model=LLM_MODEL, messages=[{"role":"user","content":prompt}],
            temperature=0.8, max_tokens=4000,
        )
        text = resp.choices[0].message.content.strip()
        # 去掉可能的 markdown 包裹
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0]
        soups = json.loads(text)
        if isinstance(soups, dict) and "soups" in soups:
            soups = soups["soups"]
        for i, s in enumerate(soups):
            s["id"] = f"ai-{int(time.time())}-{i}"
            s["difficulty"] = s.get("difficulty", diff)
    except Exception as e:
        print(f"[AI Generate] Error: {e}")
        return {"soups": []}
    return {"soups": soups}

@app.post("/api/admin/llm-ping")
async def admin_llm_ping():
    """检测 LLM 模型连通性，发送一条简单请求验证模型是否可用"""
    status = ""
    try:
        client = get_client()
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role":"user","content":"仅回复一个词：OK"}],
            max_tokens=10, temperature=0.1,
        )
        text = resp.choices[0].message.content.strip()
        status = f"响应正常"
        return {"ok": True, "model": LLM_MODEL, "response": text, "msg": f"模型 {LLM_MODEL} 响应正常"}
    except Exception as e:
        return {"ok": False, "model": LLM_MODEL, "error": str(e), "msg": f"连接失败: {str(e)}"}

@app.get("/api/admin/llm-models")
async def admin_llm_models():
    """获取 API 端点可用的模型列表"""
    try:
        client = get_client()
        models = client.models.list()
        names = sorted([m.id for m in models])
        return {"ok": True, "models": names}
    except Exception as e:
        return {"ok": False, "models": [], "error": str(e)}

@app.post("/api/admin/ai-approve")
async def admin_ai_approve(req: dict):
    soup = req.get("soup", {})
    if not soup.get("surface") or not soup.get("bottom"):
        return {"ok": False, "msg": "数据不完整"}
    soup["id"] = soup.get("id", f"soup-{len(SOUPS)+1:03d}")
    SOUPS.append(soup)
    return {"ok": True}

# 主题管理
@app.get("/api/admin/themes")
async def admin_get_themes():
    return {"themes": theme_manager.list_themes()}

@app.post("/api/admin/theme")
async def admin_set_theme(req: dict):
    tid = req.get("theme_id", "")
    try:
        theme_manager.set_active(tid)
        await manager.broadcast({"type": "theme_change", "theme_id": tid})
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/api/theme")
async def admin_get_current_theme():
    return {"theme_id": theme_manager.get_active()}

# 数据面板
@app.get("/api/admin/metrics")
async def admin_metrics():
    dur = int(time.time() - room.start_time) if room.start_time else 0
    return {
        "totalScore": 0,
        "totalDanmaku": len(room.qa_history),
        "totalGifts": len(room.gift_log),
        "paid_users": len(set(g["user"] for g in room.gift_log[-200:])),
        "round_count": room.round_total,
        "session_duration": dur,
        "accuracy": round(room.round_correct / max(room.round_total, 1) * 100) if room.round_total else 0,
        "danmaku_series": [],
        "gift_series": [],
        "recentGifts": [{"user": g["user"], "gift_name": g["giftName"], "coins": GIFT_LIBRARY.get(g["giftName"], {}).get("coins", 0)} for g in room.gift_log[-10:]],
    }

# ── 前端路由 ──
_dist_index = FRONTEND_DIST / "index.html"
if _dist_index.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
    print(f"[Server] 静态文件服务: {FRONTEND_DIST}")
else:
    @app.get("/")
    async def serve_root():
        return RedirectResponse(url="/admin")
    print(f"[Server] 嵌入式前端就绪")

# ── 入口 ──
if __name__ == "__main__":
    print("=" * 50)
    print(f"  CCcat 海龟汤 - V7 (三端分离)")
    print(f"  LLM: {LLM_MODEL} @ {LLM_BASE_URL}")
    print(f"  [Admin] http://localhost:{SERVER_PORT}/admin")
    print(f"  [Overlay] http://localhost:{SERVER_PORT}/overlay")
    print(f"  [WS]  ws://localhost:{SERVER_PORT}/ws")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT)


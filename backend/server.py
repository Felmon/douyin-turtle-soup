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
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from pydantic import BaseModel
from openai import OpenAI
import uvicorn
from embedded_ui import EMBEDDED_HTML
from persistent import PersistentDB
from tiers import TIERS, get_tier, check_tier_up, SCORE_BY_DIFFICULTY, DIFFICULTY_MULTIPLIER
from gift_resolver import resolve_gift, match_triggers

# ── 加载 .env ──
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    load_dotenv(str(_env_path), encoding="utf-8")
    print(f"[Config] 已加载 .env: {_env_path}")
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
    PROJECT_ROOT = Path(sys.executable).resolve().parent
    if not (PROJECT_ROOT / "meoo_frontend").exists() and (PROJECT_ROOT.parent / "meoo_frontend").exists():
        PROJECT_ROOT = PROJECT_ROOT.parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "meoo_frontend"
FRONTEND_DIST = FRONTEND_DIR / "dist"

ANTI_STALL_INTERVAL = 180
ANTI_STALL_DANMAKU = 50
ANTI_STALL_DECAY = 0.8
ROUND_END_DELAY = 5

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
DB_PATH = Path(__file__).resolve().parent / "data" / "persistent.db"
try:
    db = PersistentDB(DB_PATH)
    print(f"[DB] 持久化就绪: {DB_PATH}")
except Exception as _e:
    print(f"[DB] 初始化失败，回退内存模式: {_e}")
    db = None
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
IRRELEVANT_PATTERNS = [
    re.compile(r"^[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]+$"),
    re.compile(r"^(6{2,}|666+|哈哈哈+|呵呵+|嘿嘿+|哈哈+)+$"),
    re.compile(r"^(主播|老师|大佬|好厉害|加油|来了|签到|打卡|第一)+"),
    re.compile(r"^.{0,2}$"),
]

def rule_filter(text: str) -> str | None:
    for p in IRRELEVANT_PATTERNS:
        if p.search(text):
            return None
    return text

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

async def llm_hint(qa_history: list[dict], answer: str, keywords: list[str]) -> str:
    try:
        history = "\\n".join([f"Q: {h.get('question','')} -> {h.get('result','')}" for h in qa_history[-5:]])
        resp = get_client().chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "生成方向引导提示。不超过20字。"},
                {"role": "user", "content": f"汤底: {answer}\\n历史:\\n{history}\\n提示:"},
            ],
            max_tokens=30, temperature=0.7,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[LLM] hint error: {e}")
        return "想想故事里谁最可疑？"

async def llm_gift_solicit(gift_type: str, context: dict) -> str:
    fallbacks = {
        "人气票": "动动小手送个人气票！",
        "啤酒": "送瓶啤酒，揭示一个关键线索！",
        "棒棒糖": "来个棒棒糖，揭开一句话！",
        "墨镜": "送墨镜，直接通关！",
        "粉丝灯牌": "点亮粉丝灯牌！",
        "点赞": "点点赞，500赞揭示一字！",
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
        self.like_progress = 0
        self.like_threshold = 500
        self.guess_count = 0
        self.start_time = 0
        self.anti_last_reveal = 0
        self.anti_since_reveal = 0
        self.anti_triggers = 0
        self.fanlight_used = 0
        self.max_fanlight = 3
        self.current_difficulty = "medium"
        self.current_soup_id = ""
    def to_dict(self):
        _, total, pct = RevealEngine.get_progress(self.char_states)
        return {
            "phase": self.phase, "guessCount": self.guess_count,
            "revealProgress": pct/100, "qaCount": len(self.qa_history),
            "likeProgress": self.like_progress, "likeThreshold": self.like_threshold,
            "startTime": self.start_time,
        }

room = GameRoom()

# ── 题库 ──
try:
    from data_soups import SOUPS
except ImportError:
    SOUPS = [{"id":"demo","title":"海龟汤","surface":"示例汤面","bottom":"示例汤底","keywords":["示例"],"difficulty":"easy"}]

# ── Lifecycle ──
# ── Anti-Stall Background Task ──
async def anti_stall_loop():
    while True:
        await asyncio.sleep(30)
        try:
            if not room.soup_answer or room.phase in ("idle", "complete"):
                continue
            now = time.time()
            decay = ANTI_STALL_DECAY ** room.anti_triggers
            time_cond = (now - room.anti_last_reveal) >= (ANTI_STALL_INTERVAL * decay)
            danmaku_cond = room.anti_since_reveal >= (ANTI_STALL_DANMAKU * decay)
            if time_cond or danmaku_cond:
                cand = [s for s in room.char_states if s["isContent"] and not s["revealed"]]
                if cand:
                    freq = {}
                    for ch in room.soup_answer:
                        if RevealEngine.is_content_word(ch):
                            freq[ch] = freq.get(ch, 0) + 1
                    cand.sort(key=lambda s: freq.get(s["char"], 0), reverse=True)
                    target = cand[0]["char"]
                    room.char_states = RevealEngine.reveal_char(room.char_states, target)
                    room.anti_last_reveal = now
                    room.anti_since_reveal = 0
                    room.anti_triggers += 1
                    await manager.broadcast({"type": "reveal_update", "charStates": room.char_states, "anti_stall": True})
                    await manager.broadcast({"type": "classification", "text": f"防卡死自动揭示：{target}", "user": "系统", "answerType": "是", "layer": "anti_stall"})
                    _, t, p = RevealEngine.get_progress(room.char_states)
                    if p >= 100 and room.phase != "complete":
                        room.phase = "complete"
                        await manager.broadcast({"type": "game_end", "winner": "系统", "charStates": room.char_states})
        except Exception as e:
            print(f"[AntiStall] Error: {e}")
            await asyncio.sleep(30)

_anti_stall_task = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global frontend_process, _anti_stall_task
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
    yield
    if _anti_stall_task and not _anti_stall_task.done():
        _anti_stall_task.cancel()
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
    filtered = rule_filter(req.text)
    if filtered is None:
        return {"text": req.text, "answerType": "不是", "layer": "rule", "latencyMs": (time.time()-t0)*1000}
    result = await llm_classify(req.text, req.answer, req.keywords)
    return {"text": req.text, "answerType": result, "layer": "llm", "latencyMs": (time.time()-t0)*1000}

@app.post("/hint")
async def hint(req: HintReq):
    return {"hint": await llm_hint(req.qaHistory, req.answer, req.keywords)}

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
    # 按难度过滤题库；无匹配则回退到 medium
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
    await manager.broadcast({
        "type": "game_start", "surface": room.soup_text,
        "keywords": room.soup_keywords, "charStates": room.char_states,
        "difficulty": diff,
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
    return {"leaderboard": [
        {"name": u["name"], "score": u.get("score", 0),
         "tier": get_tier(u.get("score", 0)),
         "combo": u.get("combo", 0),
         "total_gifts": u.get("total_gifts", 0)}
        for u in users
    ], "source": "db"}

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
    filtered = rule_filter(text)
    if filtered is None:
        await manager.broadcast({"type":"classification","text":text,"user":user,"answerType":"不相关","layer":"rule"})
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
    # 通过别名表解析真实效果（兜底默认映射）
    gift_type = resolve_gift(gift_name, db) if db else ""
    if not gift_type:
        type_map = {"点赞":"like","粉丝灯牌":"fan_light","人气票":"popularity","啤酒":"beer","棒棒糖":"lollipop","墨镜":"sunglasses"}
        gift_type = type_map.get(gift_name,"")
    if not gift_type:
        return
    # 检查金币余额（免费礼物跳过）
    price = GIFT_PRICES.get(gift_type, 0)
    if price > 0:
        if not coins.spend(user, price):
            await manager.broadcast({"type":"gift_error","user":user,"msg":f"金币不足！{gift_name}需要{price}金币"})
            return
    # 更新连击
    combo = coins.update_combo(user)
    room.gift_log.append({"user":user,"giftType":gift_type,"time":time.time()})
    # 按抖币真实价值加分（1 抖币 = 1 积分），免费礼物不加分
    gift_value = int(msg.get("diamondCount", 0) or 0)
    if gift_value > 0:
        await add_score(user, gift_value)
    # 持久化礼物日志
    if db is not None:
        try:
            db.log_gift(user, gift_name, gift_value or price)
            # 累计用户礼物数
            u = db.get_user(user) or {"name": user}
            db.upsert_user({**u, "name": user, "total_gifts": (u.get("total_gifts",0) or 0) + 1,
                            "last_seen": time.time()})
        except Exception as e:
            print(f"[DB] log_gift error: {e}")
    multiplier = combo["multiplier"]
    # 连击揭示增强
    bonus_reveal = 0
    if multiplier >= 3.0:
        bonus_reveal = 2
    elif multiplier >= 2.0:
        bonus_reveal = 1
    if gift_type == "like":
        room.like_progress += msg.get("count",1)
        if room.like_progress >= room.like_threshold:
            room.like_progress -= room.like_threshold
            u = RevealEngine.get_unrevealed(room.char_states)
            if u:
                room.char_states = RevealEngine.reveal_char(room.char_states, rnd.choice(u)["char"])
                await manager.broadcast({"type":"reveal_update","charStates":room.char_states})
    elif gift_type == "fan_light" and room.fanlight_used < room.max_fanlight:
        room.fanlight_used += 1
        clause = RevealEngine.get_unrevealed_clause(room.char_states, room.soup_answer)
        if clause:
            for ch in set(room.char_states[i]["char"] for i in clause):
                if RevealEngine.is_content_word(ch):
                    room.char_states = RevealEngine.reveal_char(room.char_states, ch)
            await manager.broadcast({"type":"reveal_update","charStates":room.char_states})
    elif gift_type == "beer":
        revealed_any = False
        for _ in range(1 + bonus_reveal):
            u = RevealEngine.get_unrevealed(room.char_states)
            if u:
                target = rnd.choice(u)["char"]
                room.char_states = RevealEngine.reveal_char(room.char_states, target)
                revealed_any = True
        if revealed_any:
            await manager.broadcast({"type":"reveal_update","charStates":room.char_states})
    elif gift_type == "lollipop":
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
    elif gift_type == "popularity":
        hint = await llm_hint(room.qa_history, room.soup_answer, room.soup_keywords)
        await manager.broadcast({"type":"hint","user":user,"hint":hint,"script":"💡 " + hint})
        if bonus_reveal > 0:
            u = RevealEngine.get_unrevealed(room.char_states)
            if u:
                target = rnd.choice(u)["char"]
                room.char_states = RevealEngine.reveal_char(room.char_states, target)
                await manager.broadcast({"type":"reveal_update","charStates":room.char_states})
    elif gift_type == "sunglasses":
        for s in room.char_states:
            s["revealed"] = True
        room.phase = "complete"
        await manager.broadcast({"type":"game_end","winner":user,"charStates":room.char_states})
    r,t,p = RevealEngine.get_progress(room.char_states)
    if r == t and t > 0 and room.phase != "complete":
        room.phase = "complete"
        await manager.broadcast({"type":"game_end","winner":user,"charStates":room.char_states})
    # 广播礼物效果（含连击信息）
    balance = coins.get_balance(user)
    await manager.broadcast({
        "type":"gift_effect",
        "user":user,
        "giftName":gift_name,
        "giftType":gift_type,
        "script":f"感谢{user}的{gift_name}！",
        "combo": combo["count"],
        "multiplier": multiplier,
        "balance": balance,
        "spent": price,
    })

# ── 前端路由 ──
_dist_index = FRONTEND_DIST / "index.html"
if _dist_index.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
    print(f"[Server] 静态文件服务: {FRONTEND_DIST}")
else:
    @app.get("/")
    async def serve_embedded():
        return HTMLResponse(content=EMBEDDED_HTML)
    print(f"[Server] 嵌入式前端就绪")

# ── 入口 ──
if __name__ == "__main__":
    print("=" * 50)
    print(f"  CCcat 海龟汤 — 合并服务")
    print(f"  LLM: {LLM_MODEL} @ {LLM_BASE_URL}")
    print(f"  服务: http://localhost:{SERVER_PORT}")
    print(f"  WS:  ws://localhost:{SERVER_PORT}/ws")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT)


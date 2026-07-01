"""
抖音海龟汤 — v6 主服务
单进程 FastAPI + WebSocket + SQLite WAL
三端分离：admin (控制台) / dashboard (数据) / overlay (投屏)

游戏流程:
  开局 → TTS朗读汤面 → 弹幕猜谜(双轨道)
  → Track A: 逐字揭示(本地,不广播新字给其他玩家)
  → Track B: 是非问答(全部走LLM,三分类)
  → 通关 → TTS朗读汤底 → 5秒后自动下一局

商业模型:
  - 售卖系统模式(授权): 试用/个人/团队/终身
  - 自营模式: 礼物经济
"""
import asyncio
import json
import os
import random
import re
import sqlite3
import sys
import time
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from openai import AsyncOpenAI

# v6 模块
from config_loader import config
from gift_slots import slot_manager, SLOT_DEFINITIONS, GIFT_LIBRARY
from admin import ADMIN_HTML
from dashboard import DASHBOARD_HTML
from overlay import OVERLAY_HTML
from data_soups_v6 import SOUPS, DIFFICULTY_CONFIG, DIFFICULTY_NAME, classify_by_length, _count_chars
from tiers import TIERS, get_tier, check_tier_up, SCORE_BY_DIFFICULTY


# ── 全局 LLM 客户端（懒加载） ──
_client = None
def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=config.get("LLM_API_KEY", ""),
            base_url=config.get("LLM_BASE_URL", "https://api.deepseek.com"),
            timeout=20.0,
        )
    return _client


# ── 虚词表 ──
FUNCTION_WORDS = set("的了是在和吗呢吧着过得地个一不没 有就都而但又如果因为所以然后于是向对从到把被给让每只想会能可以很太非常已经正在曾经将要这那你我他她它们上下里外前后中时还也再才刚做说看来去")


# ── SQLite 持久化（v6 简化：4张表） ──
DB_PATH = Path(__file__).resolve().parent / "data" / "v6.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_db_lock = threading.Lock()
_db = sqlite3.connect(str(DB_PATH), check_same_thread=False)
_db.row_factory = sqlite3.Row
_db.execute("PRAGMA journal_mode=WAL")
_db.execute("PRAGMA synchronous=NORMAL")
_db.executescript("""
CREATE TABLE IF NOT EXISTS users (
    name TEXT PRIMARY KEY,
    score INTEGER DEFAULT 0,
    tier TEXT DEFAULT '黑铁',
    total_coins INTEGER DEFAULT 0,
    total_gifts INTEGER DEFAULT 0,
    last_seen REAL
);
CREATE TABLE IF NOT EXISTS gift_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user TEXT, gift_name TEXT, slot_id TEXT,
    coins INTEGER, timestamp REAL
);
CREATE TABLE IF NOT EXISTS round_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    soup_id TEXT, difficulty TEXT, winner TEXT,
    duration REAL, reveal_pct REAL, timestamp REAL
);
CREATE TABLE IF NOT EXISTS custom_soups (
    id TEXT PRIMARY KEY,
    title TEXT, surface TEXT, bottom TEXT,
    keywords TEXT, difficulty TEXT,
    source TEXT DEFAULT 'manual',
    created_at REAL
);
""")
_db.commit()


def db_execute(sql: str, params: tuple = ()):
    with _db_lock:
        cur = _db.execute(sql, params)
        _db.commit()
        return cur


def db_query(sql: str, params: tuple = ()) -> list[dict]:
    with _db_lock:
        cur = _db.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


# ── 礼物别名（兜底映射） ──
GIFT_ALIASES = {
    "点赞": "like", "小心心": "like", "为你点赞": "like", "棒棒": "like",
    "粉丝灯牌": "fan_light", "粉丝团灯牌": "fan_light", "灯牌": "fan_light",
    "人气票": "popularity", "玫瑰": "popularity", "鲜花": "popularity",
    "啤酒": "beer", "大啤酒": "beer",
    "棒棒糖": "lollipop",
    "墨镜": "sunglasses",
}


def resolve_gift_to_slot(gift_name: str) -> str | None:
    """先查槽位绑定，再查兜底别名。"""
    slot_id = slot_manager.resolve_gift(gift_name)
    if slot_id:
        return slot_id
    # 兜底：别名映射（如 "点赞" → "like" → 槽位）
    alias_key = GIFT_ALIASES.get(gift_name)
    if alias_key:
        return slot_manager.resolve_gift(alias_key)
    return None


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

    def get_count(self) -> int:
        return len(self.active)


manager = ConnectionManager()


# ── 游戏状态 ──
class GameRoom:
    def __init__(self):
        self.reset()

    def reset(self):
        self.phase = "lobby"  # lobby | reading | playing | complete
        self.soup_text = ""
        self.soup_answer = ""
        self.soup_keywords: list[str] = []
        self.soup_id = ""
        self.char_states: list[dict] = []
        self.qa_history: list[dict] = []
        self.gift_log: list[dict] = []
        self.guess_count = 0
        self.start_time = 0
        self.anti_last_reveal = 0
        self.anti_since_reveal = 0
        self.anti_triggers = 0
        self.current_difficulty = "medium"
        self.next_difficulty = None  # 礼物切换的下一局难度
        self.revealed_chars: set[str] = set()  # Track A: 已揭示的字
        # 数据统计
        self.stats = {
            "viewers": 0,
            "danmaku_total": 0,
            "danmaku_series": [],  # 最近30分钟(每分钟一条)
            "gift_series": [],
            "gift_revenue": 0,
            "gift_list": [],  # 礼物TOP10
            "leaderboard": [],
            "tier_dist": {t["name"]: 0 for t in TIERS},
        }
        self._series_start = time.time()

    def to_dict(self):
        content = [s for s in self.char_states if s.get("isContent")]
        revealed = sum(1 for s in content if s.get("revealed"))
        total = len(content)
        pct = (revealed / total * 100) if total > 0 else 0
        return {
            "phase": self.phase,
            "soup_id": self.soup_id,
            "surface": self.soup_text,
            "charStates": self.char_states,
            "difficulty": self.current_difficulty,
            "difficulty_name": DIFFICULTY_NAME.get(self.current_difficulty, ""),
            "guessCount": self.guess_count,
            "revealProgress": pct / 100,
            "qaCount": len(self.qa_history),
            "startTime": self.start_time,
            "nextDifficulty": self.next_difficulty,
            "stats": self.stats,
            "connections": manager.get_count(),
        }

    def record_danmaku(self):
        self.stats["danmaku_total"] += 1
        self._record_series("danmaku")

    def record_gift(self, user: str, gift_name: str, slot_id: str, coins: int):
        self.stats["gift_revenue"] += coins
        # 更新礼物TOP10
        found = next((g for g in self.stats["gift_list"] if g["name"] == gift_name), None)
        if found:
            found["count"] += 1
            found["value"] += coins
        else:
            self.stats["gift_list"].append({"name": gift_name, "count": 1, "value": coins})
        self.stats["gift_list"].sort(key=lambda x: -x["value"])
        self.stats["gift_list"] = self.stats["gift_list"][:10]
        self._record_series("gift", value=coins)
        # 写数据库
        db_execute(
            "INSERT INTO gift_log(user, gift_name, slot_id, coins, timestamp) VALUES(?,?,?,?,?)",
            (user, gift_name, slot_id, coins, time.time()),
        )

    def _record_series(self, kind: str, value: int = 1):
        """记录时间序列（按分钟聚合）。"""
        now = time.time()
        elapsed = int((now - self._series_start) / 60)
        target_len = 30  # 30个点（30分钟）
        key = "danmaku_series" if kind == "danmaku" else "gift_series"
        series = self.stats[key]
        # 补齐缺失的分钟并滑动窗口
        while len(series) < min(elapsed, target_len):
            series.append(0)
        if elapsed < target_len:
            if len(series) <= elapsed:
                series.append(0)
            series[-1] = series[-1] + value
        else:
            # 滑动窗口：移除最老条目，添加新桶
            while len(series) >= target_len:
                series.pop(0)
            series.append(value)


room = GameRoom()


# ── 揭示引擎 ──
class RevealEngine:
    @staticmethod
    def is_content_word(ch: str) -> bool:
        return bool(re.match(r"[一-鿿]", ch)) and ch not in FUNCTION_WORDS

    @staticmethod
    def init_char_states(text: str) -> list[dict]:
        return [
            {
                "char": ch,
                "revealed": not RevealEngine.is_content_word(ch),
                "isContent": RevealEngine.is_content_word(ch),
            }
            for ch in text
        ]

    @staticmethod
    def reveal_char(states: list[dict], target: str) -> list[dict]:
        return [{**s, "revealed": True} if s["char"] == target else s for s in states]

    @staticmethod
    def reveal_sentence(states: list[dict], answer: str) -> list[dict]:
        """揭示一句中所有实词。"""
        clauses = re.split(r"(?<=[，。！？、；：])", answer)
        idx = 0
        for clause in clauses:
            if not clause.strip():
                idx += len(clause)
                continue
            start = idx
            end = idx + len(clause)
            has_unrevealed = any(
                i < len(states) and states[i]["isContent"] and not states[i]["revealed"]
                for i in range(start, end)
            )
            if has_unrevealed:
                for i in range(start, end):
                    if i < len(states) and states[i]["isContent"] and not states[i]["revealed"]:
                        states[i]["revealed"] = True
                return states
            idx = end
        return states

    @staticmethod
    def reveal_pct(states: list[dict], pct: float) -> list[dict]:
        """按百分比揭示未揭示的字。"""
        content_unrevealed = [s for s in states if s["isContent"] and not s["revealed"]]
        n = max(1, int(len(content_unrevealed) * pct))
        for s in content_unrevealed[:n]:
            s["revealed"] = True
        return states

    @staticmethod
    def get_progress(states: list[dict]) -> tuple[int, int, float]:
        content = [s for s in states if s["isContent"]]
        revealed = sum(1 for s in content if s["revealed"])
        total = len(content)
        return revealed, total, (revealed / total * 100) if total > 0 else 0


# ── LLM 双端点 ──
async def llm_classify(text: str, answer: str, keywords: list[str]) -> str:
    """Track B: 是/不是/是也不是 三分类。"""
    try:
        client = get_client()
        resp = await client.chat.completions.create(
            model=config.get("LLM_MODEL", "deepseek-v4-flash"),
            messages=[
                {"role": "system", "content": "判断弹幕与汤底的相关性。只回复：是、不是、是也不是"},
                {"role": "user", "content": f"汤底: {answer}\n关键词: {'、'.join(keywords)}\n弹幕: {text}"},
            ],
            max_tokens=10, temperature=0.1,
        )
        r = resp.choices[0].message.content.strip()
        if "是也不是" in r: return "是也不是"
        if "不是" in r: return "不是"
        if "是" in r: return "是"
        return "不是"
    except Exception as e:
        print(f"[LLM] classify error: {e}")
        return "不是"


async def llm_hint(qa_history: list[dict], answer: str, keywords: list[str]) -> str:
    """Track B: 方向提示。"""
    try:
        client = get_client()
        history = "\n".join([f"Q: {h.get('question','')} -> {h.get('result','')}" for h in qa_history[-5:]])
        resp = await client.chat.completions.create(
            model=config.get("LLM_MODEL", "deepseek-v4-flash"),
            messages=[
                {"role": "system", "content": "生成方向引导提示。不超过20字。"},
                {"role": "user", "content": f"汤底: {answer}\n历史:\n{history}\n提示:"},
            ],
            max_tokens=30, temperature=0.7,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[LLM] hint error: {e}")
        return "想想故事里谁最可疑？"


async def llm_generate_soups(difficulty: str, count: int = 5) -> list[dict]:
    """AI 自动出题。"""
    cfg = DIFFICULTY_CONFIG.get(difficulty, DIFFICULTY_CONFIG["medium"])
    min_len, max_len = cfg["min_len"], cfg["max_len"]
    prompt = f"""请生成 {count} 道海龟汤题。难度：{cfg['name']}（{min_len}-{max_len}字），要求：
1. 汤底中文字符数严格在 {min_len}-{max_len} 之间
2. 故事合理、有趣、有反转
3. 关键词3-5个
4. 返回 JSON 数组：[{{"surface":"汤面","bottom":"汤底","keywords":["词1","词2"],"difficulty":"{difficulty}"}}]
不要任何其他文字，只返回JSON。"""
    try:
        client = get_client()
        resp = await client.chat.completions.create(
            model=config.get("LLM_MODEL", "deepseek-v4-flash"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000, temperature=0.9,
        )
        content = resp.choices[0].message.content.strip()
        # 提取JSON（可能被```包裹）
        m = re.search(r"\[[\s\S]*\]", content)
        if not m:
            return []
        arr = json.loads(m.group(0))
        results = []
        for item in arr:
            bottom = item.get("bottom", "")
            actual_len = _count_chars(bottom)
            results.append({
                "id": f"ai-{int(time.time())}-{len(results)}",
                "title": item.get("surface", "")[:20],
                "surface": item.get("surface", ""),
                "bottom": bottom,
                "keywords": item.get("keywords", []),
                "difficulty": difficulty,
                "answer_length": actual_len,
            })
        return results
    except Exception as e:
        print(f"[LLM] generate error: {e}")
        return []


# ── 游戏控制 ──
async def start_game(difficulty: str = "medium", soup_id: str | None = None):
    diff = difficulty if difficulty in DIFFICULTY_CONFIG else "medium"
    # 优先使用指定题
    soup = None
    if soup_id:
        for s in SOUPS:
            if s["id"] == soup_id:
                soup = s
                break
    if not soup:
        # 按难度过滤
        candidates = [s for s in SOUPS if s.get("difficulty") == diff]
        if not candidates:
            candidates = SOUPS
        if not candidates:
            return None
        soup = random.choice(candidates)

    # 应用难度切换
    if room.next_difficulty:
        diff = room.next_difficulty
        room.next_difficulty = None

    room.reset()
    room.soup_text = soup["surface"]
    room.soup_answer = soup["bottom"]
    room.soup_keywords = soup.get("keywords", [])
    room.soup_id = soup.get("id", "")
    room.current_difficulty = diff
    room.char_states = RevealEngine.init_char_states(room.soup_answer)
    room.phase = "reading"
    room.start_time = time.time()
    room.anti_last_reveal = time.time()

    await manager.broadcast({
        "type": "game_start",
        "surface": room.soup_text,
        "difficulty": diff,
        "difficulty_name": DIFFICULTY_NAME.get(diff, ""),
        "charStates": room.char_states,
        "soup_id": room.soup_id,
    })
    return soup


async def end_game(reveal: bool = True):
    if reveal:
        for s in room.char_states:
            s["revealed"] = True
    room.phase = "complete"

    # 记录本局历史
    _, _, pct = RevealEngine.get_progress(room.char_states)
    duration = time.time() - room.start_time if room.start_time else 0
    db_execute(
        "INSERT INTO round_history(soup_id, difficulty, winner, duration, reveal_pct, timestamp) VALUES(?,?,?,?,?,?)",
        (room.soup_id, room.current_difficulty, "", duration, round(pct, 1), time.time()),
    )

    await manager.broadcast({
        "type": "game_end",
        "charStates": room.char_states,
        "winner": "系统",
        "soup_id": room.soup_id,
        "bottom": room.soup_answer,
    })


async def handle_danmaku(msg: dict):
    text = msg.get("text", "").strip()
    user = msg.get("nickname", msg.get("user", "观众"))
    if not text or not room.soup_answer:
        return
    if room.phase not in ("playing", "reading"):
        return

    room.record_danmaku()
    room.guess_count += 1

    # Track A: 逐字揭示（本地快速路径，不广播新字给其他玩家）
    new_chars = set()
    for ch in text:
        if ch in room.soup_answer and RevealEngine.is_content_word(ch):
            if any(s["char"] == ch and not s["revealed"] for s in room.char_states):
                room.char_states = RevealEngine.reveal_char(room.char_states, ch)
                new_chars.add(ch)
    if new_chars:
        room.anti_last_reveal = time.time()
        room.anti_since_reveal = 0
        room.anti_triggers = 0
        room.revealed_chars.update(new_chars)
        # 注意：不广播 reveal_update，只发 classification，让客户端知道"已揭示"但不暴露具体哪个字
        # 实际上仍然要广播，否则投屏端不会更新
        await manager.broadcast({
            "type": "reveal_update",
            "charStates": room.char_states,
            "newChars": list(new_chars),  # 客户端可以高亮
        })
    else:
        room.anti_since_reveal += 1

    # Track B: LLM 分类
    result = await llm_classify(text, room.soup_answer, room.soup_keywords)
    room.qa_history.append({
        "user": user, "question": text, "result": result, "timestamp": time.time()
    })
    await manager.broadcast({
        "type": "classification",
        "text": text, "user": user, "answerType": result,
    })

    # 命中加分（按难度倍率）
    if result in ("是", "是也不是"):
        base = SCORE_BY_DIFFICULTY.get(room.current_difficulty, 15)
        multiplier = DIFFICULTY_CONFIG.get(room.current_difficulty, {}).get("multiplier", 1.0)
        delta = int((base * multiplier) if result == "是" else (base * multiplier / 2))
        await add_score(user, delta)

    # 通关判定
    _, _, pct = RevealEngine.get_progress(room.char_states)
    if pct >= 100 and room.phase != "complete":
        await end_game(reveal=True)


async def handle_gift(msg: dict):
    user = msg.get("nickname", msg.get("user", "观众"))
    gift_name = msg.get("giftName", msg.get("gift_name", ""))
    if not gift_name:
        return

    # 查槽位绑定
    slot_id = resolve_gift_to_slot(gift_name)
    if not slot_id:
        return  # 未绑定到任何槽位

    # 查礼物信息
    gift_info = GIFT_LIBRARY.get(gift_name, {})
    coins = msg.get("diamond_count") or msg.get("coins") or gift_info.get("coins", 0)

    room.record_gift(user, gift_name, slot_id, coins)
    await manager.broadcast({
        "type": "gift_effect",
        "user": user,
        "giftName": gift_name,
        "slotId": slot_id,
        "coins": coins,
    })

    # 按槽位触发效果
    if slot_id == "effect_highlight":
        # 高亮一个未揭示的高频字
        unrevealed = [s for s in room.char_states if s["isContent"] and not s["revealed"]]
        if unrevealed:
            freq = {}
            for ch in room.soup_answer:
                if RevealEngine.is_content_word(ch):
                    freq[ch] = freq.get(ch, 0) + 1
            unrevealed.sort(key=lambda s: -freq.get(s["char"], 0))
            target = unrevealed[0]["char"]
            room.char_states = RevealEngine.reveal_char(room.char_states, target)
            room.anti_last_reveal = time.time()
            room.anti_since_reveal = 0
            await manager.broadcast({
                "type": "reveal_update", "charStates": room.char_states,
                "newChars": [target], "highlight": True,
            })
    elif slot_id == "effect_hint":
        hint = await llm_hint(room.qa_history, room.soup_answer, room.soup_keywords)
        await manager.broadcast({
            "type": "hint", "user": user, "hint": hint, "script": "💡 " + hint,
        })
    elif slot_id == "effect_reveal1":
        unrevealed = [s for s in room.char_states if s["isContent"] and not s["revealed"]]
        if unrevealed:
            target = random.choice(unrevealed)["char"]
            room.char_states = RevealEngine.reveal_char(room.char_states, target)
            room.anti_last_reveal = time.time()
            room.anti_since_reveal = 0
            await manager.broadcast({
                "type": "reveal_update", "charStates": room.char_states,
                "newChars": [target],
            })
    elif slot_id == "effect_reveal_sentence":
        room.char_states = RevealEngine.reveal_sentence(room.char_states, room.soup_answer)
        room.anti_last_reveal = time.time()
        room.anti_since_reveal = 0
        await manager.broadcast({
            "type": "reveal_update", "charStates": room.char_states,
        })
    elif slot_id == "effect_reveal_30p":
        # 立即揭示30%
        room.char_states = RevealEngine.reveal_pct(room.char_states, 0.3)
        room.anti_last_reveal = time.time()
        room.anti_since_reveal = 0
        await manager.broadcast({
            "type": "reveal_update", "charStates": room.char_states,
        })
    elif slot_id.startswith("diff_"):
        # 难度切换（下局生效）
        new_diff = slot_id.replace("diff_", "")
        if new_diff in DIFFICULTY_CONFIG:
            room.next_difficulty = new_diff
            await manager.broadcast({
                "type": "difficulty_scheduled",
                "nextDifficulty": new_diff,
                "nextDifficultyName": DIFFICULTY_NAME.get(new_diff, ""),
            })

    # 通关判定
    _, _, pct = RevealEngine.get_progress(room.char_states)
    if pct >= 100 and room.phase != "complete":
        await end_game(reveal=True)


async def add_score(user: str, delta: int):
    if delta == 0:
        return
    row = db_query("SELECT * FROM users WHERE name=?", (user,))
    if row:
        old_score = row[0].get("score", 0)
        new_score = max(0, old_score + delta)
    else:
        old_score = 0
        new_score = max(0, delta)  # 新用户初始分=实际得分
    new_tier = get_tier(new_score)
    db_execute(
        "INSERT INTO users(name, score, tier, last_seen) VALUES(?,?,?,?) "
        "ON CONFLICT(name) DO UPDATE SET score=excluded.score, tier=excluded.tier, last_seen=excluded.last_seen",
        (user, new_score, new_tier["name"], time.time()),
    )
    tier_up = check_tier_up(old_score, new_score)
    if tier_up:
        await manager.broadcast({
            "type": "tier_up", "user": user,
            "from_tier": tier_up["from"], "to_tier": tier_up["to"],
            "delta": tier_up["delta"], "score": new_score,
        })
    await manager.broadcast({
        "type": "score_update", "user": user, "score": new_score, "tier": new_tier,
    })


# ── 防卡死循环 ──
async def anti_stall_loop():
    while True:
        await asyncio.sleep(30)
        try:
            if room.phase not in ("playing", "reading") or not room.soup_answer:
                continue
            now = time.time()
            decay = config.get("ANTI_STALL_DECAY", 0.8) ** room.anti_triggers
            interval = max(config.get("ANTI_STALL_MIN", 30), config.get("ANTI_STALL_INTERVAL", 180) * decay)
            danmaku_thresh = max(config.get("ANTI_STALL_MIN", 30), config.get("ANTI_STALL_DANMAKU", 50) * decay)
            time_cond = (now - room.anti_last_reveal) >= interval
            danmaku_cond = room.anti_since_reveal >= danmaku_thresh
            if time_cond or danmaku_cond:
                unrevealed = [s for s in room.char_states if s["isContent"] and not s["revealed"]]
                if unrevealed:
                    freq = {}
                    for ch in room.soup_answer:
                        if RevealEngine.is_content_word(ch):
                            freq[ch] = freq.get(ch, 0) + 1
                    unrevealed.sort(key=lambda s: -freq.get(s["char"], 0))
                    target = unrevealed[0]["char"]
                    room.char_states = RevealEngine.reveal_char(room.char_states, target)
                    room.anti_last_reveal = now
                    room.anti_since_reveal = 0
                    room.anti_triggers += 1
                    await manager.broadcast({
                        "type": "reveal_update",
                        "charStates": room.char_states,
                        "newChars": [target],
                        "antiStall": True,
                    })
                    # 1分钟后自动消失（防卡死提示）
                    await manager.broadcast({
                        "type": "hint",
                        "user": "系统",
                        "hint": f"防卡死自动揭示：{target}",
                        "script": f"⏰ 自动揭示: {target}",
                        "autoHide": 60000,
                    })
        except Exception as e:
            print(f"[AntiStall] error: {e}")


# ── 抖音桥接（可选） ──
dy_bridge = None
async def start_dy_bridge():
    global dy_bridge
    if not config.get("BRIDGE_ENABLED", True):
        return
    try:
        from dy_bridge import DouyinBridge
        dy_bridge = DouyinBridge(
            live_ws_url=config.get("LIVE_WS_URL", "ws://localhost:1088"),
            server_push_url=f"http://127.0.0.1:{config.get('SERVER_PORT', 3010)}/api/barrage/push",
            server_gift_push_url=f"http://127.0.0.1:{config.get('SERVER_PORT', 3010)}/api/gift/push",
        )
        await dy_bridge.start()
    except Exception as e:
        print(f"[Bridge] 启动失败: {e}")


# ── FastAPI App ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = [
        asyncio.create_task(anti_stall_loop()),
        asyncio.create_task(start_dy_bridge()),
    ]
    print(f"[Server] v6 已启动: http://localhost:{config.get('SERVER_PORT', 3010)}")
    yield
    # 关机清理
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    if dy_bridge:
        await dy_bridge.stop()


app = FastAPI(title="海龟汤 v6", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── 三端路由 ──
@app.get("/")
async def root():
    return HTMLResponse(content=ADMIN_HTML)

@app.get("/admin")
async def admin_page():
    return HTMLResponse(content=ADMIN_HTML)

@app.get("/dashboard")
async def dashboard_page():
    return HTMLResponse(content=DASHBOARD_HTML)

@app.get("/overlay")
async def overlay_page():
    return HTMLResponse(content=OVERLAY_HTML)


# ── 健康检查 ──
@app.get("/health")
async def health():
    bridge_stats = {}
    if dy_bridge:
        try:
            bridge_stats = dy_bridge.get_stats()
        except Exception:
            pass
    return {
        "status": "ok", "version": "v6",
        "mode": config.get("V6_MODE", "self_hosted"),
        "phase": room.phase,
        "connections": manager.get_count(),
        "llm_model": config.get("LLM_MODEL", ""),
        "bridge": bridge_stats,
    }


# ── WebSocket ──
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    cid = f"c_{len(manager.active)}_{int(time.time()*1000)}"
    await manager.connect(ws, cid)
    await ws.send_json({"type": "state_sync", "room": room.to_dict()})
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            t = msg.get("type", "")
            if t == "danmaku":
                await handle_danmaku(msg)
            elif t == "gift":
                await handle_gift(msg)
            elif t == "start_round":
                difficulty = msg.get("difficulty", "medium")
                await start_game(difficulty=difficulty, soup_id=msg.get("soup_id"))
            elif t == "end_round":
                await end_game()
            elif t == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(cid)


# ── HTTP API: 弹幕/gift 推流 ──
class PushDanmakuReq(BaseModel):
    user: str
    content: str

class PushGiftReq(BaseModel):
    user: str
    gift_name: str
    diamond_count: int = 0
    count: int = 1

@app.post("/api/barrage/push")
async def push_danmaku(req: PushDanmakuReq):
    await handle_danmaku({"text": req.content, "nickname": req.user})
    return {"ok": True}

@app.post("/api/gift/push")
async def push_gift(req: PushGiftReq):
    await handle_gift({
        "nickname": req.user,
        "giftName": req.gift_name,
        "diamond_count": req.diamond_count,
        "count": req.count,
    })
    return {"ok": True}


# ── HTTP API: 游戏控制 ──
@app.get("/api/game/state")
async def game_state():
    return room.to_dict()

class StartGameReq(BaseModel):
    difficulty: str = "medium"
    soup_id: str | None = None

@app.post("/api/game/start")
async def game_start(req: StartGameReq):
    soup = await start_game(difficulty=req.difficulty, soup_id=req.soup_id)
    if not soup:
        return {"ok": False, "error": "题库为空，无法开局"}
    return {"ok": True, "soup_id": soup.get("id", "")}

class DifficultyReq(BaseModel):
    difficulty: str

@app.post("/api/admin/difficulty")
async def set_difficulty(req: DifficultyReq):
    if req.difficulty in DIFFICULTY_CONFIG:
        room.next_difficulty = req.difficulty
        return {"ok": True, "next": req.difficulty}
    return {"ok": False, "msg": "invalid difficulty"}

@app.post("/api/admin/force-reveal")
async def force_reveal():
    await end_game(reveal=True)
    return {"ok": True}

@app.post("/api/admin/reset")
async def reset_game():
    room.reset()
    await manager.broadcast({"type": "state_sync", "room": room.to_dict()})
    return {"ok": True}


# ── HTTP API: 礼物槽位 ──
@app.get("/api/admin/slots")
async def get_slots():
    return {"slots": slot_manager.get_all_slots()}

class AssignSlotReq(BaseModel):
    slot_id: str
    gift_name: str

@app.post("/api/admin/slots/assign")
async def assign_slot(req: AssignSlotReq):
    ok = slot_manager.assign_gift(req.slot_id, req.gift_name)
    if ok:
        # 通知所有客户端刷新槽位
        await manager.broadcast({
            "type": "slots_updated",
            "slots": slot_manager.get_all_slots(),
        })
    return {"ok": ok}

@app.get("/api/admin/gifts/search")
async def search_gifts(q: str = ""):
    return {"gifts": slot_manager.search_gifts(q)}

@app.post("/api/admin/reset-session")
async def reset_session():
    room.reset()
    await manager.broadcast({"type": "state_sync", "room": room.to_dict()})
    return {"ok": True}


# ── HTTP API: 题库 ──
@app.get("/api/admin/soups")
async def list_soups(difficulty: str | None = None):
    rows = db_query("SELECT * FROM custom_soups") + SOUPS
    if difficulty:
        rows = [s for s in rows if s.get("difficulty") == difficulty]
    return {"soups": [
        {
            "id": s.get("id", ""),
            "title": s.get("title", ""),
            "surface": s.get("surface", ""),
            "difficulty": s.get("difficulty", "medium"),
            "answer_length": _count_chars(s.get("bottom", "")),
            "source": s.get("source", "default"),
        } for s in rows
    ]}

class AddSoupReq(BaseModel):
    title: str = ""
    surface: str
    bottom: str
    keywords: list[str] = []
    difficulty: str = "medium"

@app.post("/api/admin/soups/add")
async def add_soup(req: AddSoupReq):
    sid = f"manual-{int(time.time()*1000)}"
    db_execute(
        "INSERT OR REPLACE INTO custom_soups(id,title,surface,bottom,keywords,difficulty,source,created_at) VALUES(?,?,?,?,?,?,?,?)",
        (sid, req.title, req.surface, req.bottom, ",".join(req.keywords), req.difficulty, "manual", time.time()),
    )
    return {"ok": True, "id": sid}

class DeleteSoupReq(BaseModel):
    id: str

@app.post("/api/admin/soups/delete")
async def delete_soup(req: DeleteSoupReq):
    db_execute("DELETE FROM custom_soups WHERE id=?", (req.id,))
    return {"ok": True}

class ImportSoupsReq(BaseModel):
    soups: list[dict]

@app.post("/api/admin/soups/import")
async def import_soups(req: ImportSoupsReq):
    n = 0
    for s in req.soups:
        if not s.get("surface") or not s.get("bottom"):
            continue
        sid = f"imp-{int(time.time()*1000)}-{n}"
        db_execute(
            "INSERT OR REPLACE INTO custom_soups(id,title,surface,bottom,keywords,difficulty,source,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (sid, s.get("title", ""), s["surface"], s["bottom"],
             ",".join(s.get("keywords", [])), s.get("difficulty", "medium"),
             "import", time.time()),
        )
        n += 1
    return {"ok": True, "imported": n}


# ── HTTP API: AI 出题 ──
class AIGenerateReq(BaseModel):
    difficulty: str = "medium"
    count: int = 5

@app.post("/api/admin/ai-generate")
async def ai_generate(req: AIGenerateReq):
    soups = await llm_generate_soups(req.difficulty, req.count)
    return {"soups": soups, "pending": True}

class AIApproveReq(BaseModel):
    soup: dict

@app.post("/api/admin/ai-approve")
async def ai_approve(req: AIApproveReq):
    s = req.soup
    sid = s.get("id") or f"ai-{int(time.time()*1000)}"
    db_execute(
        "INSERT OR REPLACE INTO custom_soups(id,title,surface,bottom,keywords,difficulty,source,created_at) VALUES(?,?,?,?,?,?,?,?)",
        (sid, s.get("title", ""), s.get("surface", ""), s.get("bottom", ""),
         ",".join(s.get("keywords", [])), s.get("difficulty", "medium"),
         "ai", time.time()),
    )
    return {"ok": True, "id": sid}


# ── HTTP API: 排行榜 + 数据 ──
@app.get("/api/leaderboard")
async def leaderboard(limit: int = 10):
    rows = db_query("SELECT * FROM users ORDER BY score DESC LIMIT ?", (limit,))
    return {"leaderboard": [
        {"name": r.get("name", ""), "score": r.get("score", 0), "tier": r.get("tier", "黑铁")}
        for r in rows
    ]}

@app.get("/api/admin/tier-dist")
async def tier_dist():
    rows = db_query("SELECT tier, COUNT(*) as cnt FROM users GROUP BY tier")
    dist = {t["name"]: 0 for t in TIERS}
    for r in rows:
        dist[r.get("tier", "黑铁")] = r.get("cnt", 0)
    return {"dist": dist}

@app.get("/api/admin/metrics")
async def admin_metrics():
    s = room.stats
    recent = db_query("SELECT * FROM gift_log ORDER BY timestamp DESC LIMIT 10")
    score_rows = db_query("SELECT score FROM users WHERE score > 0 LIMIT 1000")
    gift_count_rows = db_query("SELECT COUNT(*) as cnt FROM gift_log")
    paid_rows = db_query("SELECT DISTINCT user as cnt FROM gift_log")
    total_gifts = gift_count_rows[0]["cnt"] if gift_count_rows else 0
    paid_users = len(paid_rows) if paid_rows else 0
    lb_rows = db_query("SELECT * FROM users ORDER BY score DESC LIMIT 10")
    leaderboard = [
        {"name": r.get("name", ""), "score": r.get("score", 0), "tier": r.get("tier", "黑铁")}
        for r in lb_rows
    ]
    return {
        "viewers": s["viewers"],
        "viewers_delta": 0,
        "danmaku_rate": s["danmaku_total"] // max(1, int((time.time()-room._series_start)/60)),
        "danmaku_total": s["danmaku_total"],
        "gift_rate": sum(g["count"] for g in s["gift_list"]) // max(1, int((time.time()-room._series_start)/60)),
        "gift_revenue": s["gift_revenue"],
        "pay_rate": 0,
        "paid_users": paid_users,
        "danmaku_series": s["danmaku_series"],
        "gift_series": s["gift_series"],
        "leaderboard": leaderboard,
        "gift_list": s["gift_list"],
        "tier_dist": s["tier_dist"],
        # Admin data tab fields
        "totalScore": sum(r.get("score", 0) for r in score_rows),
        "totalDanmaku": s["danmaku_total"],
        "totalGifts": total_gifts,
        "recentGifts": [{"user": r.get("user", ""), "gift_name": r.get("gift_name", ""), "coins": r.get("coins", 0)} for r in recent],
    }

@app.get("/api/admin/export")
async def export_data(format: str = "json"):
    rows = db_query("SELECT * FROM gift_log ORDER BY timestamp DESC LIMIT 500")
    return JSONResponse(content={"gift_log": rows, "stats": room.stats})


# ── HTTP API: 难度配置 ──
@app.get("/api/game/difficulties")
async def get_difficulties():
    return {
        "difficulties": [
            {
                "id": k, "name": v["name"],
                "min_len": v["min_len"], "max_len": v["max_len"],
                "multiplier": v["multiplier"],
            } for k, v in DIFFICULTY_CONFIG.items()
        ]
    }


# ── 入口 ──
if __name__ == "__main__":
    import uvicorn
    port = config.get("SERVER_PORT", 3010)
    print("=" * 50)
    print(f"  抖音海龟汤 — v6")
    print(f"  LLM: {config.get('LLM_MODEL', '')} @ {config.get('LLM_BASE_URL', '')}")
    print(f"  模式: {config.get('V6_MODE', 'self_hosted')}")
    print(f"  服务: http://localhost:{port}")
    print(f"  控制台: /admin  数据: /dashboard  投屏: /overlay")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=port)

"""
CCcat 海龟汤 — WebSocket 游戏服务器 (完整版)

功能:
  房间管理 / 弹幕分类 / 逐字揭示 / 是非问答 / 礼物处理
  防卡死自动揭示 / 断线重连 / 游戏状态循环
"""
import asyncio
import json
import time
import random
import math
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import httpx
import uvicorn

# ── Config ──
QWEN_URL = "http://localhost:3009"
ANTI_STALL_INTERVAL = 180        # 3 分钟无揭示触发
ANTI_STALL_DANMAKU = 50          # 50 条弹幕无命中触发
ANTI_STALL_DECAY = 0.8           # 每次连续触发缩短 20%
ROUND_END_DELAY = 5              # 通关后等待秒数

# 虚词表
FUNCTION_WORDS = {
    "的", "了", "是", "在", "和", "吗", "呢", "吧",
    "着", "过", "得", "地", "个", "一", "不", "没",
    "有", "就", "都", "而", "但", "又", "如果", "因为",
    "所以", "然后", "于是", "向", "对", "从", "到",
    "把", "被", "给", "让", "每", "只", "想", "会",
    "能", "可以", "很", "太", "非常", "已经", "正在",
    "曾经", "将", "要", "这", "那", "你", "我", "他",
    "她", "它", "们", "上", "下", "里", "外", "前",
    "后", "中", "时", "还", "也", "再", "才", "刚",
    "做", "说", "看", "来", "去",
}

PUNCTUATION = set("，。、？！；：""''""（）【】《》——…·,.:;!?()[]{}")

app = FastAPI(title="Game WS Server")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ══════════════════════════════════════════
#  Connection Manager
# ══════════════════════════════════════════

class ConnectionManager:
    def __init__(self):
        self.active: dict[str, WebSocket] = {}  # client_id -> ws
        self.user_map: dict[str, str] = {}       # client_id -> nickname

    async def connect(self, ws: WebSocket, client_id: str) -> str:
        await ws.accept()
        self.active[client_id] = ws
        return client_id

    def disconnect(self, client_id: str):
        self.active.pop(client_id, None)
        nickname = self.user_map.pop(client_id, None)
        return nickname

    def set_nickname(self, client_id: str, nickname: str):
        self.user_map[client_id] = nickname

    def get_nickname(self, client_id: str) -> str:
        return self.user_map.get(client_id, "unknown")

    async def broadcast(self, data: dict, exclude: str | None = None):
        dead = []
        for cid, ws in self.active.items():
            if cid == exclude:
                continue
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(cid)
        for cid in dead:
            self.disconnect(cid)

    async def send_to(self, client_id: str, data: dict):
        ws = self.active.get(client_id)
        if ws:
            try:
                await ws.send_json(data)
            except Exception:
                self.disconnect(client_id)

    @property
    def player_list(self) -> list[dict]:
        return [{"clientId": cid, "nickname": nick} for cid, nick in self.user_map.items()]

    @property
    def connection_count(self) -> int:
        return len(self.active)


manager = ConnectionManager()


# ══════════════════════════════════════════
#  Soup / Reveal Engine
# ══════════════════════════════════════════

class RevealEngine:
    """管理逐字揭示状态"""

    def __init__(self, soup: dict):
        self.soup = soup
        self.truth = soup.get("answer", soup.get("truth", ""))
        self.title = soup.get("title", "")
        self.surface = soup.get("surface", "")
        self.keywords = soup.get("keywords", [])

        # 拆分字符
        self.chars = list(self.truth)
        self.total_chars = len(self.chars)
        self.revealed = [False] * self.total_chars

        # 实词 vs 虚词/标点
        self.content_word_indices = []
        self.function_word_indices = []
        for i, ch in enumerate(self.chars):
            if ch in FUNCTION_WORDS or ch in PUNCTUATION or ch.strip() == "":
                self.function_word_indices.append(i)
            else:
                self.content_word_indices.append(i)

        self.total_content = len(self.content_word_indices)
        # 开局直接揭示虚词和标点
        for i in self.function_word_indices:
            self.revealed[i] = True

        self.last_reveal_time = time.time()
        self.last_reveal_count = 0
        self.consecutive_stall_triggers = 0
        self.danmaku_since_last_reveal = 0

        # 句子拆分（按标点分段）
        self.sentences = self._split_sentences()

    def _split_sentences(self):
        """根据标点拆分句子"""
        sentences = []
        current = []
        for i, ch in enumerate(self.chars):
            current.append(i)
            if ch in "。！？.!?" and len(current) > 1:  # 至少包含一个字符+标点
                sentences.append(current)
                current = []
        if current:
            sentences.append(current)
        # 如果没分出句子，整段作为一个句子
        if not sentences:
            sentences = [list(range(self.total_chars))]
        return sentences

    def get_sentence_by_index(self, sent_idx: int) -> list[int]:
        if 0 <= sent_idx < len(self.sentences):
            return self.sentences[sent_idx]
        return []

    def reveal_char(self, ch: str) -> list[int]:
        """揭示所有匹配的字符位置，返回新揭示的位置列表"""
        newly_revealed = []
        for i in self.content_word_indices:
            if not self.revealed[i] and self.chars[i] == ch:
                self.revealed[i] = True
                newly_revealed.append(i)
        if newly_revealed:
            self.last_reveal_time = time.time()
            self.last_reveal_count += len(newly_revealed)
            self.danmaku_since_last_reveal = 0
            self.consecutive_stall_triggers = 0
        return newly_revealed

    def reveal_random_char(self) -> tuple[str, list[int]]:
        """揭示一个随机未揭示的实词"""
        unrevealed = [i for i in self.content_word_indices if not self.revealed[i]]
        if not unrevealed:
            return "", []
        idx = random.choice(unrevealed)
        ch = self.chars[idx]
        newly = self.reveal_char(ch)
        return ch, newly

    def reveal_random_sentence(self) -> list[int]:
        """揭示一个未完全揭示的句子"""
        # 按完整度排序，选完整度最低的未完全揭示句子
        incomplete = []
        for sidx, sent in enumerate(self.sentences):
            content_in_sent = [i for i in sent if i in self.content_word_indices]
            if not content_in_sent:
                continue
            revealed_in_sent = sum(1 for i in content_in_sent if self.revealed[i])
            if revealed_in_sent < len(content_in_sent):
                incomplete.append((sidx, revealed_in_sent / len(content_in_sent)))
        if not incomplete:
            return []
        # 选揭示比例最低的句子
        incomplete.sort(key=lambda x: x[1])
        sidx = incomplete[0][0]
        sent = self.sentences[sidx]
        newly = []
        for i in sent:
            if i in self.content_word_indices and not self.revealed[i]:
                self.revealed[i] = True
                newly.append(i)
        if newly:
            self.last_reveal_time = time.time()
            self.last_reveal_count += len(newly)
            self.danmaku_since_last_reveal = 0
        return newly

    def reveal_all(self) -> list[int]:
        """揭示所有内容"""
        newly = []
        for i in self.content_word_indices:
            if not self.revealed[i]:
                self.revealed[i] = True
                newly.append(i)
        if newly:
            self.last_reveal_count += len(newly)
        return newly

    def get_progress(self) -> float:
        if self.total_content == 0:
            return 1.0
        revealed_count = sum(1 for i in self.content_word_indices if self.revealed[i])
        return revealed_count / self.total_content

    def is_all_revealed(self) -> bool:
        return all(self.revealed[i] for i in self.content_word_indices)

    def get_revealed_text(self) -> str:
        """获取当前揭示状态的文本（已揭示显示字符，未揭示显示 _）"""
        result = []
        for i, ch in enumerate(self.chars):
            if self.revealed[i]:
                result.append(ch)
            else:
                result.append("_")
        return "".join(result)

    def get_unrevealed_content_chars(self) -> list[str]:
        return list({self.chars[i] for i in self.content_word_indices if not self.revealed[i]})

    def get_char_frequency(self) -> dict[str, int]:
        """统计未揭示字符的出现频率"""
        freq = {}
        for i in self.content_word_indices:
            if not self.revealed[i]:
                ch = self.chars[i]
                freq[ch] = freq.get(ch, 0) + 1
        return freq


# ══════════════════════════════════════════
#  Anti-Stall Engine
# ══════════════════════════════════════════

class AntiStallEngine:
    def __init__(self):
        self.task: asyncio.Task | None = None

    def get_thresholds(self, consecutive: int):
        decay = ANTI_STALL_DECAY ** consecutive
        return {
            "time": ANTI_STALL_INTERVAL * decay,
            "danmaku": int(ANTI_STALL_DANMAKU * decay),
        }

    async def run(self, reveal_engine: RevealEngine, broadcast_cb, game_active_ref):
        consecutive = 0
        while True:
            await asyncio.sleep(5)  # 每5秒检查一次
            if not game_active_ref():
                break

            thresholds = self.get_thresholds(consecutive)
            elapsed = time.time() - reveal_engine.last_reveal_time
            danmaku_count = reveal_engine.danmaku_since_last_reveal

            triggered = False
            reason = ""
            if elapsed >= thresholds["time"]:
                triggered = True
                reason = "timeout"
            elif danmaku_count >= thresholds["danmaku"]:
                triggered = True
                reason = "danmaku"

            if triggered and not reveal_engine.is_all_revealed():
                ch, positions = reveal_engine.reveal_random_char()
                if positions:
                    consecutive += 1
                    await broadcast_cb({
                        "type": "anti_stall",
                        "char": ch,
                        "positions": positions,
                        "progress": reveal_engine.get_progress(),
                        "revealedText": reveal_engine.get_revealed_text(),
                        "reason": reason,
                    })
                    # 检查是否通关
                    if reveal_engine.is_all_revealed():
                        await broadcast_cb({
                            "type": "game_end",
                            "winner": "system",
                            "reason": "all_revealed",
                            "soup": reveal_engine.soup,
                        })
                        break
            elif triggered:
                consecutive += 1


# ══════════════════════════════════════════
#  Game State
# ══════════════════════════════════════════

class GameRoom:
    def __init__(self):
        self.phase = "lobby"           # lobby | playing | complete
        self.track = "逐字揭示"         # 逐字揭示 | 问答推理
        self.current_soup = None
        self.reveal_engine: RevealEngine | None = None
        self.qa_history: list[dict] = []
        self.gift_log: list[dict] = []
        self.like_count = 0
        self.like_progress = 0
        self.like_threshold = 500
        self.question_count = 0
        self.start_time = 0
        self.winners: list[str] = []
        self.lamp_reveal_count = 0  # 粉丝灯牌每局最多3次
        self.anti_stall = AntiStallEngine()
        self._active = False
        self.gift_solicit_interval = 180  # 每3分钟生成一次索要
        self._last_gift_solicit_time = 0

    def is_active(self):
        return self._active

    def start_round(self, soup: dict, track: str = "逐字揭示"):
        self.phase = "playing"
        self.track = track
        self.current_soup = soup
        self.reveal_engine = RevealEngine(soup)
        self.qa_history = []
        self.gift_log = []
        self.like_count = 0
        self.like_progress = 0
        self.question_count = 0
        self.start_time = time.time()
        self.winners = []
        self.lamp_reveal_count = 0
        self._active = True
        self._last_gift_solicit_time = time.time()

    def end_round(self, winner: str = "system"):
        self.phase = "complete"
        self._active = False
        if winner not in self.winners:
            self.winners.append(winner)

    def next_round(self):
        self.phase = "lobby"
        self.current_soup = None
        self.reveal_engine = None
        self.qa_history = []
        self.gift_log = []
        self.question_count = 0
        self.winners = []

    def add_danmaku_to_history(self, text: str, answer_type: str):
        self.qa_history.append({
            "text": text,
            "answerType": answer_type,
            "time": time.time(),
        })

    def should_trigger_gift_solicit(self) -> bool:
        if self.phase != "playing":
            return False
        elapsed = time.time() - self._last_gift_solicit_time
        return elapsed >= self.gift_solicit_interval

    def reset_gift_solicit_timer(self):
        self._last_gift_solicit_time = time.time()

    def get_state_snapshot(self) -> dict:
        return {
            "phase": self.phase,
            "track": self.track,
            "soup": self.current_soup,
            "progress": self.reveal_engine.get_progress() if self.reveal_engine else 0,
            "revealedText": self.reveal_engine.get_revealed_text() if self.reveal_engine else "",
            "questionCount": self.question_count,
            "qaHistory": self.qa_history[-20:],
            "likeCount": self.like_count,
            "likeProgress": self.like_progress,
            "likeThreshold": self.like_threshold,
            "winners": self.winners,
            "players": manager.player_list,
        }


room = GameRoom()


# ══════════════════════════════════════════
#  Qwen API Helpers
# ══════════════════════════════════════════

async def call_qwen_classify(text: str, answer: str, keywords: list[str]) -> dict | None:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{QWEN_URL}/classify", json={
                "text": text,
                "answer": answer,
                "keywords": keywords,
            }, timeout=5.0)
            return resp.json()
    except Exception as e:
        print(f"[Qwen] classify error: {e}")
        return None


async def call_qwen_hint() -> str | None:
    if not room.current_soup or not room.qa_history:
        return None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{QWEN_URL}/hint", json={
                "qaHistory": room.qa_history,
                "answer": room.current_soup.get("answer", room.current_soup.get("truth", "")),
                "keywords": room.current_soup.get("keywords", []),
                "questionCount": room.question_count,
            }, timeout=5.0)
            data = resp.json()
            return data.get("hint")
    except Exception as e:
        print(f"[Qwen] hint error: {e}")
        return None


async def call_qwen_gift_solicit(gift_type: str) -> str | None:
    if not room.current_soup:
        return None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{QWEN_URL}/gift-solicit", json={
                "giftType": gift_type,
                "context": {
                    "revealProgress": room.reveal_engine.get_progress() if room.reveal_engine else 0,
                    "questionCount": room.question_count,
                    "phase": room.phase,
                },
            }, timeout=5.0)
            data = resp.json()
            return data.get("script")
    except Exception as e:
        print(f"[Qwen] gift_solicit error: {e}")
        return None


# ══════════════════════════════════════════
#  Gift Effect Handlers
# ══════════════════════════════════════════

async def handle_gift(gift_type: str, nickname: str) -> dict:
    """处理礼物效果，返回效果描述"""
    effect = {"type": "gift_effect", "giftType": gift_type, "nickname": nickname}

    if room.phase != "playing" or not room.reveal_engine:
        effect["message"] = "游戏未开始"
        return effect

    reveal = room.reveal_engine

    if gift_type == "人气票":
        # 方向引导提示
        hint = await call_qwen_hint()
        effect["effect"] = "hint"
        effect["hint"] = hint or "想想还有没有其他方向？"

    elif gift_type == "啤酒":
        # 揭示一个高频实词字
        ch, positions = reveal.reveal_random_char()
        if positions:
            progress = reveal.get_progress()
            effect["effect"] = "reveal_char"
            effect["char"] = ch
            effect["positions"] = positions
            effect["progress"] = progress
            effect["revealedText"] = reveal.get_revealed_text()

            if reveal.is_all_revealed():
                room.end_round(nickname)
                effect["game_end"] = True
                effect["winner"] = nickname
        else:
            effect["effect"] = "none"
            effect["message"] = "所有字已揭示"

    elif gift_type == "棒棒糖":
        # 揭示一句话
        positions = reveal.reveal_random_sentence()
        if positions:
            progress = reveal.get_progress()
            effect["effect"] = "reveal_sentence"
            effect["positions"] = positions
            effect["sentence"] = "".join(reveal.chars[i] for i in positions)
            effect["progress"] = progress
            effect["revealedText"] = reveal.get_revealed_text()

            if reveal.is_all_revealed():
                room.end_round(nickname)
                effect["game_end"] = True
                effect["winner"] = nickname
        else:
            effect["effect"] = "none"
            effect["message"] = "所有句子已揭示"

    elif gift_type == "墨镜":
        # 揭示全文通关
        positions = reveal.reveal_all()
        effect["effect"] = "reveal_all"
        effect["progress"] = 1.0
        effect["revealedText"] = reveal.get_revealed_text()
        room.end_round(nickname)
        effect["game_end"] = True
        effect["winner"] = nickname

    elif gift_type == "粉丝灯牌":
        # 揭示一句话，每局最多3次
        if room.lamp_reveal_count >= 3:
            effect["effect"] = "none"
            effect["message"] = "本局灯牌揭示已达上限（3次）"
            return effect
        room.lamp_reveal_count += 1
        positions = reveal.reveal_random_sentence()
        if positions:
            progress = reveal.get_progress()
            effect["effect"] = "reveal_sentence"
            effect["positions"] = positions
            effect["sentence"] = "".join(reveal.chars[i] for i in positions)
            effect["progress"] = progress
            effect["revealedText"] = reveal.get_revealed_text()

            if reveal.is_all_revealed():
                room.end_round(nickname)
                effect["game_end"] = True
                effect["winner"] = nickname
        else:
            effect["effect"] = "none"
            effect["message"] = "所有内容已揭示"

    elif gift_type == "点赞":
        # 点赞累积，每500赞揭示一字
        effect["effect"] = "like_progress"
        effect["likeCount"] = room.like_count
        effect["likeProgress"] = room.like_progress
        effect["likeThreshold"] = room.like_threshold
        if room.like_progress >= room.like_threshold:
            room.like_progress -= room.like_threshold
            ch, positions = reveal.reveal_random_char()
            if positions:
                effect["char"] = ch
                effect["positions"] = positions
                effect["progress"] = reveal.get_progress()
                effect["revealedText"] = reveal.get_revealed_text()
                effect["effect"] = "reveal_char"
                effect["message"] = f"达到{room.like_threshold}赞，揭示字'{ch}'！"
            else:
                effect["effect"] = "like_progress"
                effect["message"] = "所有字已揭示"

    room.gift_log.append({
        "giftType": gift_type,
        "nickname": nickname,
        "time": time.time(),
        "effect": effect.get("effect", ""),
    })

    return effect


# ══════════════════════════════════════════
#  WebSocket Endpoint
# ══════════════════════════════════════════

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, client_id: str = ""):
    if not client_id:
        client_id = f"client_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"

    await manager.connect(ws, client_id)
    print(f"[WS] 新连接: {client_id}")

    # 发送当前状态（断线重连用）
    await manager.send_to(client_id, {
        "type": "state_sync",
        "room": room.get_state_snapshot(),
        "clientId": client_id,
    })

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)

            # ── 处理消息 ──
            if msg.get("type") == "join":
                nickname = msg.get("nickname", client_id)
                manager.set_nickname(client_id, nickname)
                await manager.broadcast({
                    "type": "player_joined",
                    "nickname": nickname,
                    "players": manager.player_list,
                })

            elif msg.get("type") == "leave":
                nickname = manager.get_nickname(client_id)
                manager.disconnect(client_id)
                await manager.broadcast({
                    "type": "player_left",
                    "nickname": nickname,
                    "players": manager.player_list,
                })
                break

            elif msg.get("type") == "danmaku":
                await handle_danmaku(msg, client_id)

            elif msg.get("type") == "gift":
                await handle_gift_message(msg, client_id)

            elif msg.get("type") == "like":
                await handle_like(msg, client_id)

            elif msg.get("type") == "start_round":
                await handle_start_round(msg)

            elif msg.get("type") == "next_round":
                await handle_next_round()

    except WebSocketDisconnect:
        nickname = manager.disconnect(client_id)
        print(f"[WS] 断开: {client_id} ({nickname})")
        await manager.broadcast({
            "type": "player_left",
            "nickname": nickname or client_id,
            "players": manager.player_list,
        })
    except Exception as e:
        print(f"[WS] 错误 ({client_id}): {e}")
        nickname = manager.disconnect(client_id)
        await manager.broadcast({
            "type": "player_left",
            "nickname": nickname or client_id,
            "players": manager.player_list,
        })


# ══════════════════════════════════════════
#  Message Handlers
# ══════════════════════════════════════════

async def handle_danmaku(msg: dict, client_id: str):
    if room.phase != "playing" or not room.reveal_engine:
        return

    text = msg.get("text", "").strip()
    nickname = msg.get("nickname", manager.get_nickname(client_id))

    if not text:
        return

    reveal = room.reveal_engine
    answer_text = room.current_soup.get("answer", room.current_soup.get("truth", ""))
    keywords = room.current_soup.get("keywords", [])

    # ── Track A: 逐字揭示（每条弹幕必走）──
    newly_revealed = []
    for ch in text:
        positions = reveal.reveal_char(ch)
        if positions:
            newly_revealed.append({"char": ch, "positions": positions})

    if newly_revealed:
        progress = reveal.get_progress()
        await manager.broadcast({
            "type": "track_a_reveal",
            "reveals": newly_revealed,
            "progress": progress,
            "revealedText": reveal.get_revealed_text(),
        })

        # 检查通关
        if reveal.is_all_revealed():
            room.end_round(nickname)
            await manager.broadcast({
                "type": "game_end",
                "winner": nickname,
                "reason": "all_revealed",
                "soup": room.current_soup,
            })
            return
    else:
        reveal.danmaku_since_last_reveal += 1

    # ── Track B: Qwen 三分类（过滤后走）──
    result = await call_qwen_classify(text, answer_text, keywords)

    if result:
        answer_type = result.get("answerType", "不是")
        room.add_danmaku_to_history(text, answer_type)
        room.question_count += 1

        await manager.broadcast({
            "type": "classification",
            "text": text,
            "nickname": nickname,
            "answerType": answer_type,
            "layer": result.get("layer", "llm"),
            "latencyMs": result.get("latencyMs", 0),
        })

    # ── 检查礼物索要时机 ──
    if room.should_trigger_gift_solicit():
        script = await call_qwen_gift_solicit("人气票")
        if script:
            await manager.broadcast({
                "type": "gift_solicit",
                "script": script,
                "giftType": "人气票",
            })
        room.reset_gift_solicit_timer()


async def handle_gift_message(msg: dict, client_id: str):
    gift_type = msg.get("giftType", "")
    nickname = msg.get("nickname", manager.get_nickname(client_id))

    if gift_type not in ("人气票", "啤酒", "棒棒糖", "墨镜", "粉丝灯牌", "点赞"):
        await manager.broadcast({
            "type": "error",
            "message": f"未知礼物类型: {gift_type}",
        })
        return

    effect = await handle_gift(gift_type, nickname)

    # 广播礼物效果
    if gift_type == "点赞":
        await manager.broadcast({
            "type": "gift_effect",
            "giftType": gift_type,
            "nickname": nickname,
            "effect": effect.get("effect"),
            "likeCount": room.like_count,
            "likeProgress": room.like_progress,
            "likeThreshold": room.like_threshold,
            "char": effect.get("char"),
            "positions": effect.get("positions"),
            "progress": effect.get("progress"),
            "revealedText": effect.get("revealedText"),
            "message": effect.get("message", ""),
        })
    else:
        await manager.broadcast(effect)

    # 如果礼物导致通关
    if effect.get("game_end"):
        await manager.broadcast({
            "type": "game_end",
            "winner": effect.get("winner", nickname),
            "reason": f"gift_{gift_type}",
            "soup": room.current_soup,
        })


async def handle_like(msg: dict, client_id: str):
    if room.phase != "playing" or not room.reveal_engine:
        return

    count = msg.get("count", 1)
    nickname = msg.get("nickname", manager.get_nickname(client_id))

    room.like_count += count
    room.like_progress += count

    # 检查点赞是否达到阈值
    effect = await handle_gift("点赞", nickname)

    await manager.broadcast({
        "type": "like_update",
        "likeCount": room.like_count,
        "likeProgress": room.like_progress,
        "likeThreshold": room.like_threshold,
        "effect": effect.get("effect"),
        "char": effect.get("char"),
        "positions": effect.get("positions"),
        "progress": effect.get("progress"),
        "revealedText": effect.get("revealedText"),
        "message": effect.get("message", ""),
    })


async def handle_start_round(msg: dict):
    soup = msg.get("soup")
    track = msg.get("track", "逐字揭示")

    if not soup:
        await manager.broadcast({"type": "error", "message": "缺少汤底数据"})
        return

    room.start_round(soup, track)
    reveal = room.reveal_engine

    await manager.broadcast({
        "type": "game_start",
        "soup": soup,
        "track": track,
        "progress": 0,
        "revealedText": reveal.get_revealed_text(),
        "totalChars": reveal.total_chars,
        "totalContentChars": reveal.total_content,
    })

    # 启动防卡死
    if room.anti_stall.task and not room.anti_stall.task.done():
        room.anti_stall.task.cancel()
    room.anti_stall.task = asyncio.create_task(
        room.anti_stall.run(reveal, manager.broadcast, room.is_active)
    )


async def handle_next_round():
    room.next_round()
    await manager.broadcast({
        "type": "next_round",
        "message": "准备开始下一局",
        "room": room.get_state_snapshot(),
    })


# ══════════════════════════════════════════
#  REST Endpoints
# ══════════════════════════════════════════

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "connections": manager.connection_count,
        "gamePhase": room.phase,
        "progress": room.reveal_engine.get_progress() if room.reveal_engine else 0,
    }

@app.get("/state")
async def get_state():
    return room.get_state_snapshot()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3010)

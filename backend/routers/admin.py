"""
管理面板路由 — /api/admin/* + /api/theme + /api/triggers
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from admin import ADMIN_HTML
from state import (
    room, manager, db, slot_manager, spam_filter, theme_manager, SOUPS,
    LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, _client_instance,
    ANTI_STALL_ENABLED, ANTI_STALL_INTERVAL, ANTI_STALL_DANMAKU,
    ANTI_STALL_DECAY, ROUND_TIMEOUT, ANTI_STALL_DANMAKU as _ASD,
    GIFT_LIBRARY,
    DIFFICULTY_NAME_MAP, DIFFICULTY_MULTIPLIER, SCORE_BY_DIFFICULTY,
    get_client, recreate_client, reload_config, compute_adaptive_difficulty,
    auto_reveal_and_hint,
)
import json
import time

router = APIRouter(tags=["admin"])

class BannedWordReq(BaseModel):
    word: str

class AssignSlotReq(BaseModel):
    slot_id: str
    gift_name: str

class ToggleSlotReq(BaseModel):
    slot_id: str
    enabled: bool

class SlotLikeConfigReq(BaseModel):
    slot_id: str
    like_mode: bool
    like_threshold: int = 500

class TriggerReq(BaseModel):
    type: str
    target: str = "*"
    effect: str = ""
    value: str = ""
    enabled: int = 1

# ── 违禁词 ──
@router.get("/api/admin/banned-words")
async def get_banned_words():
    return {"words": spam_filter.banned.get_all()}

@router.post("/api/admin/banned-words")
async def add_banned_word(req: BannedWordReq):
    ok = spam_filter.banned.add(req.word)
    return {"ok": ok, "word": req.word}

@router.delete("/api/admin/banned-words")
async def delete_banned_word(req: BannedWordReq):
    ok = spam_filter.banned.remove(req.word)
    return {"ok": ok, "word": req.word}

@router.put("/api/admin/banned-words")
async def set_banned_words(req: list[str]):
    spam_filter.banned.set_all(req)
    return {"ok": True, "count": len(req)}

# ── 配置 ──
@router.post("/api/admin/config-reload")
async def admin_reload_config():
    ok, msg = reload_config()
    return {"ok": ok, "msg": msg}

# ── 防卡死配置 ──
@router.get("/api/admin/anti-stall-config")
async def get_anti_stall_config():
    global ANTI_STALL_ENABLED, ANTI_STALL_INTERVAL, ANTI_STALL_DANMAKU
    return {"enabled": ANTI_STALL_ENABLED, "interval": ANTI_STALL_INTERVAL, "danmaku": ANTI_STALL_DANMAKU}

@router.post("/api/admin/anti-stall-config")
async def set_anti_stall_config(req: dict):
    global ANTI_STALL_ENABLED, ANTI_STALL_INTERVAL, ANTI_STALL_DANMAKU
    if "enabled" in req:
        ANTI_STALL_ENABLED = bool(req["enabled"])
    if "interval" in req:
        ANTI_STALL_INTERVAL = max(30, int(req["interval"]))
    if "danmaku" in req:
        ANTI_STALL_DANMAKU = max(5, int(req["danmaku"]))
    return {"ok": True}

# ── 游戏时长 ──
@router.get("/api/admin/game-config")
async def get_game_config():
    return {"roundTimeout": ROUND_TIMEOUT}

@router.post("/api/admin/game-config")
async def set_game_config(req: dict):
    global ROUND_TIMEOUT
    if "roundTimeout" in req:
        val = int(req["roundTimeout"])
        ROUND_TIMEOUT = max(30, min(3600, val))
        if db is not None:
            db.set_setting("round_timeout", str(ROUND_TIMEOUT))
        print(f"[Config] 游戏时长已更新: {ROUND_TIMEOUT}秒")
    return {"ok": True}

# ── 礼物槽位管理 ──
@router.get("/api/admin/slots")
async def get_slots():
    return {"slots": slot_manager.get_all_slots()}

@router.post("/api/admin/slots/assign")
async def assign_slot(req: AssignSlotReq):
    slot_manager.assign_gift(req.slot_id, req.gift_name)
    if db is not None:
        slot_manager.save_to_db(db)
    await manager.broadcast({"type": "slots_updated"})
    return {"ok": True}

@router.post("/api/admin/slots/toggle")
async def toggle_slot(req: ToggleSlotReq):
    slot_manager.set_enabled(req.slot_id, req.enabled)
    if db is not None:
        slot_manager.save_to_db(db)
    await manager.broadcast({"type": "slots_updated"})
    return {"ok": True}

@router.post("/api/admin/slots/like-config")
async def set_slot_like_config(req: SlotLikeConfigReq):
    slot_manager.set_like_config(req.slot_id, req.like_mode, req.like_threshold)
    if db is not None:
        slot_manager.save_to_db(db)
    await manager.broadcast({"type": "slots_updated"})
    return {"ok": True}

@router.get("/api/admin/gifts/search")
async def search_gifts(q: str = ""):
    return {"gifts": slot_manager.search_gifts(q)}

# ── 难度控制 ──
@router.post("/api/admin/difficulty")
async def admin_set_difficulty(req: dict):
    diff = req.get("difficulty", "medium")
    room.next_difficulty = diff
    name = {"easy":"简单","medium":"一般","hard":"困难","hell":"地狱","void":"无人区","auto":"自适应"}.get(diff, diff)
    await manager.broadcast({"type":"difficulty_scheduled", "nextDifficulty": diff, "nextDifficultyName": name})
    return {"ok": True, "difficulty": diff}

# ── 强制揭示 ──
@router.post("/api/admin/force-reveal")
async def admin_force_reveal():
    if room.char_states:
        for s in room.char_states:
            if s["isContent"] and not s["revealed"]:
                s["revealed"] = True
        room.phase = "complete"
        await manager.broadcast({"type": "reveal_update", "charStates": room.char_states})
    await manager.broadcast({"type": "game_end", "winner": "管理员"})
    return {"ok": True}

# ── 重置游戏 ──
@router.post("/api/admin/reset")
async def admin_reset():
    room.reset()
    await manager.broadcast({"type": "game_end", "winner": "系统"})
    return {"ok": True}

# ── 题库管理 ──
@router.get("/api/admin/soups")
async def admin_get_soups(difficulty: str = ""):
    if difficulty:
        candidates = [s for s in SOUPS if s.get("difficulty") == difficulty]
    else:
        candidates = SOUPS
    return {"soups": candidates}

@router.post("/api/admin/soups/delete")
async def admin_delete_soup(req: dict):
    sid = req.get("id", "")
    global SOUPS  # noqa: F811, F824
    import state
    state.SOUPS = [s for s in SOUPS if s.get("id") != sid]
    return {"ok": True}

@router.post("/api/admin/soups/add")
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

@router.post("/api/admin/soups/import")
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

# ── AI 出题 ──
@router.post("/api/admin/ai-generate")
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

@router.post("/api/admin/llm-ping")
async def admin_llm_ping():
    status = ""
    try:
        client = get_client()
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role":"user","content":"仅回复一个词：OK"}],
            max_tokens=10, temperature=0.1,
        )
        text = resp.choices[0].message.content.strip()
        return {"ok": True, "model": LLM_MODEL, "response": text, "msg": f"模型 {LLM_MODEL} 响应正常"}
    except Exception as e:
        return {"ok": False, "model": LLM_MODEL, "error": str(e), "msg": f"连接失败: {str(e)}"}

@router.get("/api/admin/llm-models")
async def admin_llm_models():
    try:
        client = get_client()
        models = client.models.list()
        names = sorted([m.id for m in models])
        return {"ok": True, "models": names}
    except Exception as e:
        return {"ok": False, "models": [], "error": str(e)}

@router.post("/api/admin/ai-approve")
async def admin_ai_approve(req: dict):
    soup = req.get("soup", {})
    if not soup.get("surface") or not soup.get("bottom"):
        return {"ok": False, "msg": "数据不完整"}
    soup["id"] = soup.get("id", f"soup-{len(SOUPS)+1:03d}")
    SOUPS.append(soup)
    return {"ok": True}

# ── 主题管理 ──
@router.get("/api/admin/themes")
async def admin_get_themes():
    return {"themes": theme_manager.list_themes()}

@router.post("/api/admin/theme")
async def admin_set_theme(req: dict):
    tid = req.get("theme_id", "")
    try:
        theme_manager.set_active(tid)
        await manager.broadcast({"type": "theme_change", "theme_id": tid})
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@router.get("/api/theme")
async def admin_get_current_theme():
    return {"theme_id": theme_manager.get_active()}

# ── 数据面板 ──
@router.get("/api/admin/metrics")
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

# ── 触发器 API ──
@router.get("/api/triggers")
async def get_triggers():
    if db is None:
        return {"triggers": []}
    return {"triggers": db.get_triggers()}

@router.post("/api/triggers")
async def add_trigger(req: TriggerReq):
    if db is None:
        return {"ok": False, "msg": "持久化未启用"}
    tid = db.add_trigger(req.type, req.target, req.effect, req.value, 1 if req.enabled else 0)
    return {"ok": True, "id": tid}

@router.delete("/api/triggers/{tid}")
async def delete_trigger(tid: int):
    if db is None:
        return {"ok": False, "msg": "持久化未启用"}
    db.del_trigger(tid)
    return {"ok": True}

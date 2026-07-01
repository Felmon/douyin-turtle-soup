"""礼物别名解析 — 真实礼物名 → 触发效果。"""

# 默认兜底映射（别名表中查不到时使用）
DEFAULT_MAP = {
    "点赞": "like",
    "粉丝灯牌": "fan_light",
    "人气票": "popularity",
    "啤酒": "beer",
    "棒棒糖": "lollipop",
    "墨镜": "sunglasses",
}


def resolve_gift(gift_name: str, db=None) -> str:
    """接收真实礼物名，返回对应效果（like/fan_light/...）。

    优先级：别名表精确匹配 > 别名内任一礼物名 > 默认兜底。
    """
    if db is not None:
        try:
            for alias in db.get_enabled_aliases():
                gift_list = [g.strip() for g in (alias.get("gifts") or "").split(",") if g.strip()]
                if gift_name in gift_list or alias.get("alias") == gift_name:
                    return alias.get("effect") or ""
        except Exception as e:
            print(f"[gift_resolver] query aliases error: {e}")
    return DEFAULT_MAP.get(gift_name, "")


def match_triggers(event_type: str, target: str, db=None) -> list[dict]:
    """返回匹配的所有触发器。target 为礼物名或 '*'（任意）。"""
    if db is None:
        return []
    out = []
    try:
        for t in db.get_enabled_triggers():
            if t.get("type") != event_type:
                continue
            tgt = t.get("target") or ""
            if tgt == "*" or tgt == target:
                out.append(t)
    except Exception as e:
        print(f"[gift_resolver] query triggers error: {e}")
    return out
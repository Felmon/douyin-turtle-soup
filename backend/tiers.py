"""段位系统 — 10 级段位定义与晋级判定。"""

TIERS = [
    {"id": 0, "name": "黑铁",   "color": "#6B7280", "min_score": 0,       "icon": "🛡️"},
    {"id": 1, "name": "青铜",   "color": "#B45309", "min_score": 100,     "icon": "🥉"},
    {"id": 2, "name": "黄金",   "color": "#F59E0B", "min_score": 500,     "icon": "🥇"},
    {"id": 3, "name": "铂金",   "color": "#06B6D4", "min_score": 2000,    "icon": "💎"},
    {"id": 4, "name": "钻石",   "color": "#3B82F6", "min_score": 5000,    "icon": "💠"},
    {"id": 5, "name": "白银",   "color": "#E5E7EB", "min_score": 10000,   "icon": "⚪"},
    {"id": 6, "name": "王者",   "color": "#A855F7", "min_score": 25000,   "icon": "👑"},
    {"id": 7, "name": "宗师",   "color": "#DC2626", "min_score": 50000,   "icon": "🔥"},
    {"id": 8, "name": "大师",   "color": "#FBBF24", "min_score": 100000,  "icon": "🌟"},
    {"id": 9, "name": "超级王者", "color": "#FF1493", "min_score": 200000, "icon": "⚡"},
]

# 难度 → 命中加分
SCORE_BY_DIFFICULTY = {
    "easy": 10,
    "medium": 15,
    "hard": 20,
    "hell": 30,
    "void": 50,
}

# 难度倍率（与原版一致 ×1/×1.5/×2/×3/×5）
DIFFICULTY_MULTIPLIER = {
    "easy": 1.0,
    "medium": 1.5,
    "hard": 2.0,
    "hell": 3.0,
    "void": 5.0,
}


def get_tier(score: int) -> dict:
    """根据积分返回段位。低于最低分返回黑铁。"""
    for tier in reversed(TIERS):
        if score >= tier["min_score"]:
            return tier
    return TIERS[0]


def check_tier_up(old_score: int, new_score: int) -> dict | None:
    """积分变化时检查是否升级，返回 {from, to, delta} 或 None。"""
    old_tier = get_tier(old_score)
    new_tier = get_tier(new_score)
    if new_tier["id"] > old_tier["id"]:
        return {"from": old_tier, "to": new_tier, "delta": new_tier["id"] - old_tier["id"]}
    return None
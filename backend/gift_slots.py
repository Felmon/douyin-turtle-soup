"""v6 礼物槽系统 — 10个固定槽位：5效果 + 5难度切换

主播从全部368+个抖音礼物中自由分配给10个槽位。
每个槽位独立启用/禁用、可随时更换绑定的礼物。
"""
import json
import threading
from pathlib import Path

# ── 10个固定槽位定义 ──
SLOT_DEFINITIONS = [
    # 效果槽（5个）
    {"id": "effect_highlight", "group": "effect", "name": "高亮线索", "desc": "高亮一个未揭示的关键字", "default_gift": "小心心"},
    {"id": "effect_hint",      "group": "effect", "name": "方向提示", "desc": "揭示解谜方向提示（固定文本）", "default_gift": "人气票"},
    {"id": "effect_reveal1",   "group": "effect", "name": "揭示一字",  "desc": "随机揭示一个高频实词字", "default_gift": "啤酒"},
    {"id": "effect_reveal_sentence", "group": "effect", "name": "揭示一句", "desc": "揭示完整一句话", "default_gift": "棒棒糖"},
    {"id": "effect_reveal_30p","group": "effect", "name": "揭示30%",  "desc": "立即揭示30%的未揭示内容", "default_gift": "墨镜"},
    # 难度槽（5个）
    {"id": "diff_easy",  "group": "difficulty", "name": "难度-简单", "desc": "下局切换为简单（点赞≥300触发）", "default_gift": "鲜花"},
    {"id": "diff_medium","group": "difficulty", "name": "难度-一般", "desc": "下局切换为一般（点赞≥500触发）", "default_gift": "玫瑰"},
    {"id": "diff_hard",  "group": "difficulty", "name": "难度-困难", "desc": "下局切换为困难（点赞≥800触发）", "default_gift": "跑车"},
    {"id": "diff_hell",  "group": "difficulty", "name": "难度-地狱", "desc": "下局切换为地狱（礼物：火箭/跑车）", "default_gift": "嘉年华"},
    {"id": "diff_void",  "group": "difficulty", "name": "难度-无人区", "desc": "下局切换为无人区（礼物：城堡/钻石）", "default_gift": "梦幻城堡"},
]

# ── 礼物库（从 gift_icons.json 加载） ──
GIFT_LIBRARY_PATH = Path(__file__).resolve().parent.parent / "gift_icons.json"
# 也尝试从桌面项目加载
ALT_GIFT_LIBRARY_PATH = Path("C:/Users/27871/OneDrive/Desktop/CCcat猜词大挑战/overlay/gift_icons.json")

GIFT_LIBRARY = {}  # {gift_name: {coins, icon}}

def _load_gift_library():
    global GIFT_LIBRARY
    for p in [GIFT_LIBRARY_PATH, ALT_GIFT_LIBRARY_PATH]:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                GIFT_LIBRARY = {k: v for k, v in data.items()}
                print(f"[GiftSlots] 已加载 {len(GIFT_LIBRARY)} 个礼物: {p}")
                return
            except Exception as e:
                print(f"[GiftSlots] 加载礼物库失败 {p}: {e}")
    print("[GiftSlots] 警告: 未找到礼物库文件，使用空库")

_load_gift_library()


class GiftSlotManager:
    """管理10个礼物槽位的状态。线程安全。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._slots = {}  # {slot_id: {gift_name, enabled}}
        self._init_defaults()

    def _init_defaults(self):
        for sd in SLOT_DEFINITIONS:
            self._slots[sd["id"]] = {
                "gift_name": sd["default_gift"],
                "enabled": True,
            }

    def get_all_slots(self) -> list[dict]:
        """返回所有槽位信息（含定义+当前绑定）。"""
        with self._lock:
            result = []
            for sd in SLOT_DEFINITIONS:
                state = self._slots.get(sd["id"], {})
                gift_name = state.get("gift_name", sd["default_gift"])
                gift_info = GIFT_LIBRARY.get(gift_name, {})
                result.append({
                    "id": sd["id"],
                    "group": sd["group"],
                    "name": sd["name"],
                    "desc": sd["desc"],
                    "gift_name": gift_name,
                    "gift_coins": gift_info.get("coins", 0),
                    "gift_icon": gift_info.get("icon", ""),
                    "enabled": state.get("enabled", True),
                })
            return result

    def get_slot(self, slot_id: str) -> dict | None:
        for s in self.get_all_slots():
            if s["id"] == slot_id:
                return s
        return None

    def assign_gift(self, slot_id: str, gift_name: str) -> bool:
        """将某个礼物绑定到槽位。"""
        valid_ids = {sd["id"] for sd in SLOT_DEFINITIONS}
        if slot_id not in valid_ids:
            return False
        with self._lock:
            self._slots[slot_id] = {
                "gift_name": gift_name,
                "enabled": self._slots.get(slot_id, {}).get("enabled", True),
            }
        return True

    def set_enabled(self, slot_id: str, enabled: bool) -> bool:
        valid_ids = {sd["id"] for sd in SLOT_DEFINITIONS}
        if slot_id not in valid_ids:
            return False
        with self._lock:
            if slot_id in self._slots:
                self._slots[slot_id]["enabled"] = enabled
            else:
                self._slots[slot_id] = {"gift_name": "", "enabled": enabled}
        return True

    def resolve_gift(self, gift_name: str) -> str | None:
        """根据收到的礼物名，返回匹配的槽位ID（效果或难度）。"""
        with self._lock:
            for sd in SLOT_DEFINITIONS:
                state = self._slots.get(sd["id"], {})
                if not state.get("enabled", True):
                    continue
                if state.get("gift_name") == gift_name:
                    return sd["id"]
        return None

    def search_gifts(self, query: str) -> list[dict]:
        """搜索礼物库（主播分配时用），按价值升序排列。"""
        q = query.lower().strip()
        if not q:
            items = sorted(GIFT_LIBRARY.items(), key=lambda x: x[1].get("coins", 0))
            items = items[:50]
        else:
            items = [(k, v) for k, v in GIFT_LIBRARY.items() if q in k.lower()]
            items = sorted(items, key=lambda x: x[1].get("coins", 0))[:50]
        return [{"name": k, "coins": v.get("coins", 0), "icon": v.get("icon", "")} for k, v in items]


# 全局单例
slot_manager = GiftSlotManager()

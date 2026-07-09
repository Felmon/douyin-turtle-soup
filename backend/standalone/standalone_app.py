"""
独立集成版 — 控制面板 + 投屏端
完全自包含，无需启动 server.py（端口 3010）。

用法:
    python standalone_app.py              # 默认端口 3090
    python standalone_app.py --port 8080  # 指定端口
    python standalone_app.py --backend http://myserver:3010  # 连接外部后端

特性:
    - 内置 HTTP 服务器提供 admin/overlay 页面
    - 内置 WebSocket 处理游戏状态
    - 默认模拟 API 响应（无真实游戏后端也可用）
    - 可指定外部后端（生产模式）
    - PyWebView 原生窗口
"""
import asyncio
import json
import os
import socket
import sys
import threading
import time
import traceback
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, unquote

# ── 授权模块 ──
import license as lic

# ── 配置 ──
PORT = 3090
WS_PORT = PORT + 1  # WebSocket 用下一个端口
HOST = "127.0.0.1"

# ── 路径处理（兼容 PyInstaller EXE 和直接运行） ──
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    _BASE = sys._MEIPASS
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_BASE)  # backend/（仅开发模式）

def _resolve_src(filename: str) -> str:
    """尝试 _BASE（EXE）→ _PARENT（开发）解析数据文件路径"""
    p = os.path.join(_BASE, filename)
    if os.path.isfile(p):
        return p
    return os.path.join(_PARENT, filename)

ADMIN_SRC = _resolve_src("admin.py")
OVERLAY_SRC = _resolve_src("overlay.py")


def _exec_py_var(filepath, varname):
    with open(filepath, encoding="utf-8") as f:
        src = f.read()
    g = {}
    exec(src, g)
    return g[varname]

ADMIN_HTML_RAW = _exec_py_var(ADMIN_SRC, "ADMIN_HTML")
OVERLAY_HTML_RAW = _exec_py_var(OVERLAY_SRC, "OVERLAY_HTML")

# ── 可选加载题库 ──
SOUPS_DATA = []
SOUPS_CACHE = os.path.join(os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else _BASE, "soups_cache.json")
try:
    SOUPS_SRC = os.path.join(_BASE, "data_soups.py")
    if os.path.isfile(SOUPS_SRC):
        SOUPS_DATA = _exec_py_var(SOUPS_SRC, "SOUPS")
        print(f"  已加载 {len(SOUPS_DATA)} 道题库")
except Exception:
    pass
# 合并持久化的用户修改（增删题目在重启后保留）
try:
    if os.path.isfile(SOUPS_CACHE):
        with open(SOUPS_CACHE, encoding="utf-8") as f:
            cached = json.load(f)
        if isinstance(cached, list) and len(cached) >= len(SOUPS_DATA):
            SOUPS_DATA = cached
            print(f"  从缓存恢复 {len(SOUPS_DATA)} 道（含用户自建）")
except Exception:
    pass

def _save_soups():
    try:
        with open(SOUPS_CACHE, "w", encoding="utf-8") as f:
            json.dump(SOUPS_DATA, f, ensure_ascii=False)
    except Exception:
        pass

# ── LLM 配置（持久化到本地 JSON）──
_LLM_CONFIG_FILE = os.path.join(os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else _BASE, "llm_config.json")
_llm_config = {"api_key": "", "base_url": "", "model": "deepseek-v4-flash", "reasoning": True}
try:
    if os.path.isfile(_LLM_CONFIG_FILE):
        with open(_LLM_CONFIG_FILE, encoding="utf-8") as f:
            _llm_config.update(json.load(f))
except Exception:
    pass

def _save_llm_config():
    try:
        with open(_LLM_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(_llm_config, f, ensure_ascii=False)
    except Exception:
        pass

def _llm_chat(messages, model=None, temperature=0.7, max_tokens=1024, timeout=30, response_format=None, reasoning=True):
    """使用 urllib 调用 OpenAI 兼容 API（零额外依赖）
    reasoning=False 时传入 reasoning_effort="none" 请求模型关闭推理。
    """
    api_key = _llm_config.get("api_key", "")
    base_url = _llm_config.get("base_url", "").rstrip("/")
    model_name = model or _llm_config.get("model", "")
    if not api_key or not base_url or not model_name:
        return None
    url = f"{base_url}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if not reasoning:
        payload["reasoning_effort"] = "none"
    if response_format:
        payload["response_format"] = response_format
    body = json.dumps(payload).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_text = resp.read().decode("utf-8")
        try:
            data = json.loads(resp_text)
        except json.JSONDecodeError:
            print(f"[LLM] API 返回非 JSON 内容: {resp_text[:300]}")
            raise Exception(f"API 返回格式异常（非 JSON），请检查 base_url 是否正确。响应开头: {resp_text[:80]}")
        return data
    except urllib.error.HTTPError as e:
        err_text = e.read().decode("utf-8", errors="replace")
        # 如果 response_format 被 API 拒绝，回退重试（不带此参数）
        if e.code == 400 and response_format:
            print(f"[LLM] response_format 被拒绝，回退重试: {err_text[:200]}")
            return _llm_chat(messages, model=model, temperature=temperature, max_tokens=max_tokens, timeout=timeout, response_format=None, reasoning=reasoning)
        raise Exception(f"HTTP {e.code}: {err_text[:200]}")
    except urllib.error.URLError as e:
        raise Exception(f"连接失败: {e.reason}")

# AI 出题方向 prompt 映射（与 routers/admin.py 同步）
_DIRECTION_PROMPTS = {
    "random":        "",
    "mystery":       "方向为悬疑推理：包含谋杀、失踪、盗窃等需要逻辑推理的情节，线索要埋得巧妙，反转要合理。",
    "horror":        "方向为恐怖惊悚：包含灵异事件、鬼怪传说或心理恐怖元素，氛围要阴森压抑，结局要令人不寒而栗。",
    "daily":         "方向为日常推理：场景设定在日常生活（家庭、学校、办公室等），看似普通的事件背后有惊人的真相。",
    "sci-fi":        "方向为科幻想象：涉及人工智能、时空旅行、虚拟现实、未来世界等科幻元素，逻辑自洽。",
    "ethics":        "方向为情感伦理：围绕爱情、亲情、友情、道德困境等人性主题，情感冲击力强，引人深思。",
    "fairy-tale":    "方向为黑暗童话：基于经典童话、寓言或知名故事进行暗黑、反转改编，既熟悉又意外。",
    "urban":         "方向为都市传说：设定在现代都市中，带有怪谈、都市传说色彩，亦真亦假，细思极恐。",
    "history":       "方向为历史秘闻：基于真实历史事件或人物进行创意改编，历史背景准确，核心谜题有新意。",
    "dark-humor":    "方向为黑色幽默：情节荒诞讽刺，结局出人意料又合情合理，让人哭笑不得。",
    "psychological": "方向为心理迷宫：涉及人格分裂、记忆错乱、梦境与现实交织、感官欺骗等心理悬疑元素。",
}
_DIFFICULTY_CONSTRAINTS = {
    "easy":   "简单难度：单步推理即可解开，剧情直白零误导，线索明显摆在汤面中，适合新手快速上手。",
    "medium": "一般难度：两步推理或一次关键反转，线索半隐半现，需要跳出初始视角重新审视。",
    "hard":   "困难难度：三步以上逻辑链，多层反转或巧妙误导，线索分散在不同细节中，需要串联推敲。",
    "hell":   "地狱难度：复杂嵌套谜局，多重反转环环相扣，大部分线索隐晦，需要极强的逆向思维才能突破。",
    "void":   "无人区难度：极度抽象荒诞，违背常理和直觉，线索若有若无，需要彻底打破思维定势才能触及真相。",
    "auto":   "自适应难度：AI 根据题目本身自动判断归属的难度等级，覆盖各层次。",
}

# ── 加载礼物库 ──
GIFT_LIBRARY = {}  # {gift_name: {coins, icon}}
GIFT_JSON_SRC = os.path.join(_BASE, "gift_icons.json")
if os.path.isfile(GIFT_JSON_SRC):
    try:
        with open(GIFT_JSON_SRC, "r", encoding="utf-8") as f:
            GIFT_LIBRARY = json.load(f)
        print(f"  已加载 {len(GIFT_LIBRARY)} 个礼物")
    except Exception:
        pass

# ── 加载主题库 ──
BUILTIN_THEMES = {}
THEMES_SRC = _resolve_src("theme_manager.py")
if os.path.isfile(THEMES_SRC):
    try:
        BUILTIN_THEMES = _exec_py_var(THEMES_SRC, "BUILTIN_THEMES")
        print(f"  已加载 {len(BUILTIN_THEMES)} 个主题")
    except Exception as e:
        print(f"  [WARN] 主题加载失败: {e}")

# 9个固定槽位定义（与 gift_slots.py 一致）
SLOT_DEFINITIONS = [
    {"id": "effect_complete", "group": "effect", "name": "直接通关", "desc": "立即通关当前故事", "default_gift": "梦幻城堡"},
    {"id": "effect_reveal1",   "group": "effect", "name": "揭示一字",  "desc": "随机揭示一个高频实词字", "default_gift": "啤酒"},
    {"id": "effect_reveal_sentence", "group": "effect", "name": "揭示一句", "desc": "揭示完整一句话", "default_gift": "棒棒糖"},
    {"id": "effect_reveal_30p","group": "effect", "name": "揭示30%",  "desc": "立即揭示30%的未揭示内容", "default_gift": "墨镜"},
    {"id": "diff_easy",  "group": "difficulty", "name": "难度-简单", "desc": "下局切换为简单", "default_gift": "鲜花"},
    {"id": "diff_medium","group": "difficulty", "name": "难度-一般", "desc": "下局切换为一般", "default_gift": "玫瑰"},
    {"id": "diff_hard",  "group": "difficulty", "name": "难度-困难", "desc": "下局切换为困难", "default_gift": "跑车"},
    {"id": "diff_hell",  "group": "difficulty", "name": "难度-地狱", "desc": "下局切换为地狱", "default_gift": "嘉年华"},
    {"id": "diff_void",  "group": "difficulty", "name": "难度-无人区", "desc": "下局切换为无人区", "default_gift": "梦幻城堡"},
]


def _build_slots():
    """构建模拟槽位数据（含礼物信息）"""
    result = []
    for sd in SLOT_DEFINITIONS:
        gift_name = sd["default_gift"]
        gift_info = GIFT_LIBRARY.get(gift_name, {})
        result.append({
            "id": sd["id"],
            "group": sd["group"],
            "name": sd["name"],
            "desc": sd["desc"],
            "gift_name": gift_name,
            "gift_coins": gift_info.get("coins", 0),
            "gift_icon": gift_info.get("icon", ""),
            "enabled": True,
            "like_mode": False,
            "like_threshold": 500,
        })
    return result


def _search_gifts(query: str) -> list:
    """搜索礼物库"""
    q = query.lower().strip()
    if not q:
        return []
    results = []
    for name, info in GIFT_LIBRARY.items():
        if q in name.lower():
            results.append({
                "name": name,
                "coins": info.get("coins", 0),
                "icon": info.get("icon", ""),
            })
    results.sort(key=lambda x: x["coins"])
    return results


def inject_html(html: str, server_url: str, ws_url: str) -> str:
    """注入前端配置 — 劫持 API 调用指向本地服务器"""
    script = (
        "<script>"
        f"window.SERVER_URL={json.dumps(server_url)};"
        f"window.WS_URL={json.dumps(ws_url)};"
        "window.__STANDALONE__=true;"
        "(function(){"
        "var _f=window.fetch;"
        "window.fetch=function(u,o){"
        "if(typeof u==='string'&&u.startsWith('/'))u=window.SERVER_URL+u;"
        "return _f.call(window,u,o);"
        "};"
        "})();"
        "</script>"
    )
    h = html.replace("</head>", script + "</head>")
    # 替换 WebSocket URL 构造
    for pattern in [
        "(location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/ws'",
        "((location.protocol==='https:')?'wss:':'ws:')+'//'+location.host+'/ws'",
    ]:
        h = h.replace(pattern, "window.WS_URL")
    return h


def _apply_theme(html: str, theme_id: str) -> str:
    """为 HTML 注入主题 CSS 变量。"""
    import re
    theme = BUILTIN_THEMES.get(theme_id)
    if not theme:
        return html
    vars_dict = theme["vars"]
    css_lines = [f"  {k}: {v};" for k, v in vars_dict.items()]
    css_block = ":root {\n" + "\n".join(css_lines) + "\n}"
    new_html, n = re.subn(r":root\s*\{[^}]*\}", css_block, html, count=1)
    if n == 0:
        new_html = html.replace("</style>", f"{css_block}\n</style>", 1)
    return new_html


EDGE_CN_VOICES = {
    "zh-CN-XiaoxiaoNeural": "晓晓 (女声·推荐)",
    "zh-CN-XiaoyiNeural": "晓伊 (女声·情感)",
    "zh-CN-YunxiNeural": "云希 (男声)",
    "zh-CN-YunjianNeural": "云健 (男声)",
    "zh-CN-XiaohanNeural": "晓涵 (女声·温柔)",
    "zh-CN-XiaomengNeural": "晓梦 (女声·活泼)",
    "zh-CN-XiaochenNeural": "晓辰 (女声·知性)",
    "zh-CN-XiaomoNeural": "晓墨 (女声·文学)",
    "zh-CN-XiaoruiNeural": "晓睿 (女声·成熟)",
    "zh-CN-XiaoshuangNeural": "晓双 (女声·元气)",
    "zh-CN-XiaoxuanNeural": "晓萱 (女声·亲和)",
    "zh-CN-XiaoyanNeural": "晓颜 (女声·自然)",
    "zh-CN-XiaozhenNeural": "晓珍 (女声·温柔)",
    "zh-CN-YunyangNeural": "云扬 (男声·阳光)",
    "zh-CN-YunyeNeural": "云野 (男声·随性)",
    "zh-CN-YunfanNeural": "云帆 (男声·深沉)",
    "zh-CN-YunhaoNeural": "云皓 (男声·活力)",
}

# ── 模拟 API 响应 ──
class MockState:
    """模拟游戏状态"""
    def __init__(self):
        self.phase = "idle"
        self.start_time = 0
        self.round_total = 0
        self.round_correct = 0
        self.qa_history = []
        self.gift_log = []
        self.char_states = []
        self.active_theme = "dark"

    def to_dict(self):
        dur = int(time.time() - self.start_time) if self.start_time else 0
        return {
            "totalScore": 0,
            "totalDanmaku": len(self.qa_history),
            "totalGifts": len(self.gift_log),
            "paid_users": 0,
            "round_count": self.round_total,
            "session_duration": dur,
            "accuracy": round(self.round_correct / max(self.round_total, 1) * 100) if self.round_total else 0,
            "danmaku_series": [],
            "gift_series": [],
            "recentGifts": [{
                "user": g["user"], "gift_name": g["giftName"],
                "coins": 0,
            } for g in self.gift_log[-10:]],
        }


_mock_state = MockState()

# ── TTS 配置（可写，POST 持久化） ──
_tts_config = {
    "engine": "edge", "voice": "zh-CN-XiaoxiaoNeural", "rate": 1.0,
    "voices": EDGE_CN_VOICES,
    "engines": {"edge": {"available": True}},
    "cosyvoice_spk": "default",
    "cosyvoice_speakers": {},
}

def _build_tts_config():
    base = dict(_tts_config)
    base["engines"] = {"edge": {"available": True}, "cosyvoice": _get_cosyvoice_engine()}
    return base

# ── CosyVoice 模拟部署状态 ──
_cv_deploy = {
    "deploying": False, "progress": None, "error": None,
    "_step": 0, "_max_step": 5,
}
_CV_STEPS = [
    {"pct": 10, "step": "install_deps", "text": "安装 Python 依赖..."},
    {"pct": 30, "step": "submodule",    "text": "初始化 Git 子模块..."},
    {"pct": 60, "step": "download_model", "text": "下载模型文件中..."},
    {"pct": 90, "step": "verify",       "text": "验证安装..."},
    {"pct": 100,"step": "done",         "text": "✅ 部署完成！（独立模式模拟）"},
]


def _get_cosyvoice_engine():
    """返回 cosyvoice engine 状态 — 根据部署进度变化。"""
    if _cv_deploy["_step"] >= _cv_deploy["_max_step"]:
        return {"status": "ready", "detail": "CosyVoice3 已就绪（独立模式模拟）"}
    return {"status": "not_found", "detail": "模拟独立模式 — 可点击一键安装体验完整流程"}


def _get_cv_deploy_status():
    """返回 CosyVoice 部署状态（每查一次自动推进进度）。"""
    if not _cv_deploy["deploying"]:
        return {"deploying": False, "progress": None, "error": None}
    step_idx = _cv_deploy["_step"]
    if step_idx >= _cv_deploy["_max_step"]:
        _cv_deploy["deploying"] = False
        _cv_deploy["progress"] = None
        return {"deploying": False, "progress": None, "error": None}
    step = _CV_STEPS[step_idx]
    _cv_deploy["_step"] += 1
    result = {"deploying": True, "progress": step, "error": None}
    if step["step"] == "done":
        _cv_deploy["deploying"] = False
    return result


# ── 题库筛选 ──
def _filter_soups(query_string: str) -> dict:
    """按难度筛选，补充 answer_length"""
    from urllib.parse import parse_qs
    params = parse_qs(query_string)
    diff = params.get("difficulty", [None])[0]
    raw = SOUPS_DATA
    if diff:
        raw = [s for s in raw if s.get("difficulty") == diff]
    result = []
    for s in raw:
        item = dict(s)
        item["answer_length"] = len(item.get("bottom", ""))
        result.append(item)
    return {"soups": result}


# ── 授权 API ──
def _get_auth_status():
    """返回授权状态（前端友好格式）"""
    status = lic.check()
    if status.get("ok"):
        return {
            "ok": True,
            "source": status["source"],
            "is_permanent": status.get("is_permanent", False),
            "remaining_days": status.get("remaining_days", 0),
            "remaining_seconds": status.get("remaining_seconds", 0),
            "machine_id": lic.get_machine_id(),
        }
    # 未授权或过期
    result = {
        "ok": False,
        "reason": status.get("reason", "unknown"),
        "machine_id": lic.get_machine_id(),
        "trial_available": status.get("trial_available", False),
    }
    if "remaining_seconds" in status:
        result["remaining_seconds"] = status["remaining_seconds"]
    return result


def _activate_auth(key: str) -> dict:
    """激活授权码"""
    return lic.activate(key)


# ── LLM 工具函数 ──
def _fetch_llm_models():
    """尝试从 API 获取模型列表（通过 urllib）"""
    api_key = _llm_config.get("api_key", "")
    base_url = _llm_config.get("base_url", "").rstrip("/")
    if not api_key or not base_url:
        return {"ok": False, "models": [], "error": "请先配置 API 地址和 Key"}
    try:
        req = urllib.request.Request(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {api_key}", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        names = sorted([m["id"] for m in data.get("data", []) if "id" in m])
        return {"ok": True, "models": names}
    except Exception as e:
        return {"ok": False, "models": [], "error": str(e)}

def _llm_ping():
    """测试 LLM 连接"""
    try:
        data = _llm_chat(
            messages=[{"role": "user", "content": "仅回复一个词：OK"}],
            temperature=0.1, max_tokens=100,
        )
        if data is None:
            return {"ok": False, "model": _llm_config.get("model", ""), "error": "LLM 未配置", "msg": "请先在下方填写 API 地址和 Key"}
        choice = data["choices"][0]
        text = (choice["message"].get("content") or choice["message"].get("reasoning_content") or "").strip()
        return {"ok": True, "model": _llm_config.get("model", ""), "response": text, "msg": f"✅ 模型 {_llm_config.get('model', '')} 响应正常"}
    except Exception as e:
        err = str(e)
        if "401" in err or "403" in err or "1010" in err:
            msg = "API Key 无效，请检查并重新填写"
        elif "404" in err:
            msg = f"模型 '{_llm_config.get('model', '')}' 不存在或 API 地址有误"
        elif "timeout" in err.lower():
            msg = "连接超时，请检查网络"
        elif "connection" in err.lower() or "refused" in err.lower():
            msg = f"无法连接到 {_llm_config.get('base_url', '')}"
        else:
            msg = f"连接失败: {err[:100]}"
        return {"ok": False, "model": _llm_config.get("model", ""), "error": err, "msg": msg}

def _parse_ai_soups_text(text):
    """从 AI 返回的文本中解析出海龟汤数组。返回 (soups_list_or_None, error_str_or_None)。"""
    text = (text or "").strip()
    if not text:
        return None, "AI 返回了空内容，请检查模型是否支持文本生成或更换模型"
    # 去除可能的 markdown 代码块包裹
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0]
    try:
        soups = json.loads(text)
    except json.JSONDecodeError:
        print(f"[AI] JSON 解析失败, 前200字符: {text[:200]}")
        import re as _re
        # 使用贪婪匹配：从第一个 [ 到最后一个 ]，避免字符串内含 ] 被截断
        block = _re.search(r'\[[\s\S]*\]', text, _re.DOTALL)
        if block:
            try:
                soups = json.loads(block.group(0))
            except (json.JSONDecodeError, ValueError):
                preview = text[:120]
                return None, f"AI 返回了不完整的 JSON 数据（预览: {preview}），请尝试减少单次生成数量或更换模型"
        else:
            return None, f"AI 返回格式异常，无法解析为 JSON: {text[:120]}"
    if isinstance(soups, dict):
        # 尝试从包装键中提取
        wrapped = soups.get("soups") or soups.get("data")
        if isinstance(wrapped, list):
            soups = wrapped
        elif soups.get("title") or soups.get("surface") or soups.get("content"):
            # 单条谜题直接返回的对象，包装成数组
            soups = [soups]
        else:
            soups = []
    if not isinstance(soups, list):
        return None, "AI 返回格式异常，期待数组但得到 " + type(soups).__name__
    if not soups:
        return None, "AI 返回了空数组，请尝试重新生成"
    return soups, None


def _normalize_ai_soup(s, difficulty, direction, idx):
    """标准化单条 AI 谜题：补全 id/difficulty/direction，并将 keywords 字符串转为数组。"""
    import time as _time
    s["id"] = s.get("id") or f"ai-{int(_time.time())}-{idx}"
    s["difficulty"] = s.get("difficulty", difficulty)
    s["direction"] = s.get("direction", direction)
    # 模型有时把 keywords 输出成逗号字符串而非数组，这里统一转为数组
    kw = s.get("keywords")
    if isinstance(kw, str):
        s["keywords"] = [k.strip() for k in kw.replace("，", ",").split(",") if k.strip()]
    elif not isinstance(kw, list):
        s["keywords"] = []
    return s


def _ai_generate(difficulty, count, direction):
    """使用 LLM 生成海龟汤谜题（通过 urllib）。
    根据 reasoning 模式选择参数：
    - 思考模式 ON（推理模型）: 分批每批 3 题，max_tokens=16384，timeout=300
    - 思考模式 OFF（普通模型）: 分批每批 5 题，max_tokens=4096，timeout=60
    """
    try:
        reasoning = _llm_config.get("reasoning", True)
        if reasoning:
            BATCH = 3
            MAX_TOKENS = 16384
            TIMEOUT = 300
        else:
            BATCH = 5
            MAX_TOKENS = 4096
            TIMEOUT = 60
        print(f"[AI] 思考模式={'ON' if reasoning else 'OFF'}, 模型={_llm_config.get('model', '')}")
        all_soups = []
        remaining = count
        last_finish_reason = None
        while remaining > 0:
            batch_count = min(BATCH, remaining)
            data = _llm_chat(
                messages=[{"role": "user", "content": _build_ai_prompt(difficulty, batch_count, direction)}],
                temperature=0.8, max_tokens=MAX_TOKENS, timeout=TIMEOUT,
                response_format={"type": "json_object"}, reasoning=reasoning,
            )
            if data is None:
                if not all_soups:
                    return {"soups": [], "error": "LLM 未配置，请在 AI 出题页设置 API 地址和 Key"}
                break  # 已生成部分，直接返回已得结果
            choice = data["choices"][0] if data.get("choices") else None
            if choice is None:
                if not all_soups:
                    return {"soups": [], "error": "AI 返回了空响应（无 choices），请尝试重新生成"}
                break
            last_finish_reason = choice.get("finish_reason")
            raw_content = choice["message"].get("content") or ""
            raw_reasoning = choice["message"].get("reasoning_content") or ""
            # 推理模型若被 max_tokens 截断，content 常为空而 reasoning 有值
            if not raw_content.strip() and last_finish_reason == "length":
                print(f"[AI] content 为空且 finish_reason=length（reasoning {len(raw_reasoning)} 字符），token 配额不足")
                if not all_soups:
                    return {"soups": [], "error": "AI 推理 token 配额不足导致未输出结果，请减少单次生成数量或更换非推理模型"}
                break
            soups, err = _parse_ai_soups_text(raw_content or raw_reasoning)
            if err:
                print(f"[AI] 批次解析失败: {err}")
                if not all_soups:
                    return {"soups": [], "error": err}
                break  # 已有部分结果，跳过本批错误
            all_soups.extend(soups)
            remaining -= batch_count
        if not all_soups:
            return {"soups": [], "error": "AI 未生成任何谜题，请重试或更换模型"}
        all_soups = [_normalize_ai_soup(s, difficulty, direction, i) for i, s in enumerate(all_soups)]
        return {"soups": all_soups}
    except Exception as e:
        err_msg = str(e)
        print(f"[AI] 生成异常: {traceback.format_exc()}")
        if "401" in err_msg or "403" in err_msg or "Authentication" in err_msg or "Incorrect API key" in err_msg or "1010" in err_msg:
            hint = "API Key 无效或未填写，请在 AI 出题页下方配置正确的 API Key"
        elif "404" in err_msg or "Not Found" in err_msg:
            hint = f"模型 '{_llm_config.get('model', '')}' 不存在或 API 地址有误，请检查 LLM API 配置"
        elif "timeout" in err_msg.lower() or "timed out" in err_msg.lower():
            hint = "请求超时，AI 推理耗时过长，请减少生成数量或更换响应更快的模型"
        elif "connection" in err_msg.lower() or "refused" in err_msg.lower():
            hint = f"无法连接 API 服务器 ({_llm_config.get('base_url', '')})，请检查地址和网络"
        else:
            hint = f"AI 生成失败 [{type(e).__name__}]: {err_msg[:60]}"
        return {"soups": [], "error": hint}

def _build_ai_prompt(difficulty, count, direction):
    """构建 AI 出题 prompt"""
    dir_name = {"random":"🎲 综合随机","mystery":"🔍 悬疑推理","horror":"👻 恐怖惊悚","daily":"☕ 日常推理","sci-fi":"🚀 科幻想象","ethics":"💔 情感伦理","fairy-tale":"🧙 黑暗童话","urban":"🌃 都市传说","history":"📜 历史秘闻","dark-humor":"😈 黑色幽默","psychological":"🌀 心理迷宫"}.get(direction, direction)
    dir_prompt = _DIRECTION_PROMPTS.get(direction, "")
    diff_constraint = _DIFFICULTY_CONSTRAINTS.get(difficulty, _DIFFICULTY_CONSTRAINTS["medium"])
    return f"""你是一个海龟汤谜题生成器。请生成{count}个海龟汤谜题。

难度：{difficulty}（要求：{diff_constraint}）
方向：{dir_name}。{dir_prompt}

每个谜题是一个JSON对象，包含以下字段：
- title: 标题（简短有力）
- surface: 汤面（有趣有悬念的谜面）
- bottom: 汤底（合理完整的谜底）
- keywords: 关键词数组（3-5个）
- difficulty: 难度，值为"{difficulty}"
- direction: 方向，值为"{direction}"

以JSON数组格式返回。示例如下：
[
  {{
    "title": "雨中的空椅子",
    "surface": "一个雨夜，小明看到公园的长椅上放着一把湿透的伞。第二天他听说昨晚有人在那张长椅上坐着等了一夜。小明看了看那把伞，吓得跑掉了。为什么？",
    "bottom": "那把伞是小明自己遗忘的。昨晚他在梦游状态下冒雨去了公园，把伞放在椅子上，然后空手回家。但他完全不记得这件事，所以看到自己的伞出现在别人描述中的地点时，以为遇到了灵异事件。",
    "keywords": ["梦游", "雨伞", "遗忘", "长椅"],
    "difficulty": "{difficulty}",
    "direction": "{direction}"
  }}
]

仅返回JSON数组，不要markdown包裹，不要额外文字。"""


# ── HTTP Handler ──
class Handler(BaseHTTPRequestHandler):
    """轻量 HTTP 服务器 — 提供页面 + API 模拟"""

    def _parse_path(self):
        parsed = urlparse(self.path)
        return parsed.path.rstrip("/") or "/"

    def _read_body(self):
        content_len = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(content_len) if content_len else b"{}"

    # ── GET ──
    def do_GET(self):
        path = self._parse_path()

        # 页面路由
        if path == "/":
            return self._html(ADMIN_HTML_RAW)
        if path == "/overlay":
            overlay_html = _apply_theme(OVERLAY_HTML_RAW, _mock_state.active_theme)
            return self._html(overlay_html)

        # API 路由
        routes = {
            "/api/health": lambda: {"status": "ok", "phase": _mock_state.phase, "connections": 0},
            "/api/config": lambda: {"api_key_configured": bool(_llm_config.get("api_key")), "base_url": _llm_config.get("base_url", ""), "model": _llm_config.get("model", ""), "chat_model": _llm_config.get("chat_model", ""), "reasoning": _llm_config.get("reasoning", True)},
            "/api/admin/anti-stall-config": lambda: {"enabled": True, "interval": 180, "danmaku": 50},
            "/api/admin/game-config": lambda: {"roundTimeout": 600},
            "/api/admin/slots": lambda: {"slots": _build_slots()},
            "/api/admin/themes": lambda: {"themes": [
                {"id": t["id"], "name": t["name"], "accent": t["accent"],
                 "preview": t["vars"]["--bg-grad"]}
                for t in BUILTIN_THEMES.values()
            ]},
            "/api/theme": lambda: {"theme_id": _mock_state.active_theme},
            "/api/admin/banned-words": lambda: {"words": []},
            "/api/triggers": lambda: {"triggers": []},
            "/api/admin/llm-models": lambda: _fetch_llm_models(),
            "/api/admin/metrics": lambda: _mock_state.to_dict(),
            "/api/leaderboard": lambda: {"leaderboard": []},
            "/api/tts/config": lambda: _build_tts_config(),
            "/api/admin/soups": lambda: _filter_soups(urlparse(self.path).query),
            "/api/admin/gifts/search": lambda: {"gifts": _search_gifts(unquote(urlparse(self.path).query.split("=")[-1] if "q=" in self.path else ""))},
            "/api/tts/cosyvoice-deploy": lambda: _get_cv_deploy_status(),
            "/api/admin/ai-directions": lambda: {"directions": [
                {"id":"random","name":"🎲 综合随机","desc":"AI自由发挥，不限定方向"},
                {"id":"mystery","name":"🔍 悬疑推理","desc":"谋杀、失踪、盗窃等推理解谜"},
                {"id":"horror","name":"👻 恐怖惊悚","desc":"灵异、鬼怪、心理恐怖"},
                {"id":"daily","name":"☕ 日常推理","desc":"日常生活隐藏的反转真相"},
                {"id":"sci-fi","name":"🚀 科幻想象","desc":"AI、时空旅行、未来科技"},
                {"id":"ethics","name":"💔 情感伦理","desc":"爱情、亲情、友情、人性抉择"},
                {"id":"fairy-tale","name":"🧙 黑暗童话","desc":"经典童话/故事的暗黑反转"},
                {"id":"urban","name":"🌃 都市传说","desc":"现代都市诡异怪谈"},
                {"id":"history","name":"📜 历史秘闻","desc":"历史事件/人物的另类解读"},
                {"id":"dark-humor","name":"😈 黑色幽默","desc":"讽刺荒诞、出人意料"},
                {"id":"psychological","name":"🌀 心理迷宫","desc":"人格分裂、记忆陷阱、梦境"}
            ]},
        }

        # ── 授权 API ──
        if path == "/api/auth/status":
            return self._json(_get_auth_status())
        if path == "/api/auth/start-trial":
            lic.start_trial()
            return self._json({"ok": True, "status": _get_auth_status()})

        handler = routes.get(path)
        if handler:
            return self._json(handler())
        self._json({"error": "not found"}, status=404)

    # ── POST ──
    def do_POST(self):
        path = self._parse_path()
        raw = self._read_body()
        try:
            body = raw.decode("utf-8")
        except UnicodeDecodeError:
            body = raw.decode("gbk", errors="replace")

        # ── 题库操作（需要实际修改 SOUPS_DATA）──
        if path == "/api/admin/soups/delete":
            try:
                sid = json.loads(body).get("id", "")
                global SOUPS_DATA
                SOUPS_DATA = [s for s in SOUPS_DATA if s.get("id") != sid]
                _save_soups()
            except Exception:
                pass
            return self._json({"ok": True})
        if path == "/api/admin/soups/add":
            try:
                data = json.loads(body)
                new_id = f"soup-{len(SOUPS_DATA)+1:03d}"
                SOUPS_DATA.append({
                    "id": data.get("id", new_id),
                    "title": data.get("title", ""),
                    "surface": data.get("surface", ""),
                    "bottom": data.get("bottom", ""),
                    "keywords": data.get("keywords", []),
                    "difficulty": data.get("difficulty", "medium"),
                })
                _save_soups()
            except Exception:
                pass
            return self._json({"ok": True})
        if path == "/api/admin/soups/import":
            try:
                data = json.loads(body)
                for s in data.get("soups", []):
                    if s.get("surface") and s.get("bottom"):
                        s["id"] = s.get("id", f"soup-{len(SOUPS_DATA)+1:03d}")
                        s["keywords"] = s.get("keywords", [])
                        s["difficulty"] = s.get("difficulty", "medium")
                        SOUPS_DATA.append(s)
                _save_soups()
            except Exception:
                pass
            return self._json({"ok": True, "count": 1})
        if path == "/api/admin/ai-approve":
            try:
                data = json.loads(body)
                soup = data.get("soup", {})
                if soup.get("surface") and soup.get("bottom"):
                    soup["id"] = soup.get("id", f"soup-{len(SOUPS_DATA)+1:03d}")
                    SOUPS_DATA.append(soup)
                    _save_soups()
            except Exception:
                pass
            return self._json({"ok": True})

        # ── 授权激活 ──
        if path == "/api/auth/activate":
            try:
                data = json.loads(body)
                key = data.get("key", "").strip()
                if not key:
                    return self._json({"ok": False, "error": "请输入授权码"})
                result = _activate_auth(key)
                return self._json({**result, "status": _get_auth_status() if result.get("ok") else None})
            except Exception:
                return self._json({"ok": False, "error": "激活请求解析失败"})

        # ── LLM 配置保存 ──
        if path == "/api/config":
            try:
                data = json.loads(body)
                changed = False
                if data.get("api_key"):
                    _llm_config["api_key"] = data["api_key"]; changed = True
                if data.get("base_url"):
                    _llm_config["base_url"] = data["base_url"]; changed = True
                if data.get("model"):
                    _llm_config["model"] = data["model"]; changed = True
                if "reasoning" in data:
                    _llm_config["reasoning"] = bool(data["reasoning"]); changed = True
                if changed:
                    _save_llm_config()
            except Exception:
                pass
            return self._json({"ok": True, "model": _llm_config.get("model", ""), "base_url": _llm_config.get("base_url", "")})

        # ── LLM ping（测试连接）──
        if path == "/api/admin/llm-ping":
            return self._json(_llm_ping())

        # ── AI 出题 ──
        if path == "/api/admin/ai-generate":
            try:
                data = json.loads(body)
                diff = data.get("difficulty", "medium")
                count = data.get("count", 5)
                direction = data.get("direction", "random")
                return self._json(_ai_generate(diff, count, direction))
            except Exception:
                return self._json({"soups": [], "error": "AI 生成请求解析失败"})

        ok_responses = {
            "/api/admin/config-reload", "/api/admin/anti-stall-config",
            "/api/admin/game-config", "/api/admin/slots/assign",
            "/api/admin/slots/toggle", "/api/admin/slots/like-config",
            "/api/admin/difficulty", "/api/admin/force-reveal",
            "/api/admin/reset", "/api/admin/banned-words",
            "/api/game/start",
        }
        if path in ok_responses:
            return self._json({"ok": True})

        # ── TTS 配置持久化 ──
        if path == "/api/tts/config":
            try:
                data = json.loads(body)
                for key in ("engine", "voice", "rate", "cosyvoice_spk"):
                    if key in data:
                        _tts_config[key] = data[key]
            except Exception:
                pass
            return self._json({"ok": True})

        # 主题切换（需要存储状态）
        if path == "/api/admin/theme":
            try:
                data = json.loads(body)
                tid = data.get("theme_id", "")
                if tid in BUILTIN_THEMES:
                    _mock_state.active_theme = tid
            except Exception:
                pass
            return self._json({"ok": True})

        special = {
            "/api/admin/ai-directions": {"directions": [
                {"id":"random","name":"🎲 综合随机","desc":"AI自由发挥，不限定方向"},
                {"id":"mystery","name":"🔍 悬疑推理","desc":"谋杀、失踪、盗窃等推理解谜"},
                {"id":"horror","name":"👻 恐怖惊悚","desc":"灵异、鬼怪、心理恐怖"},
                {"id":"daily","name":"☕ 日常推理","desc":"日常生活隐藏的反转真相"},
                {"id":"sci-fi","name":"🚀 科幻想象","desc":"AI、时空旅行、未来科技"},
                {"id":"ethics","name":"💔 情感伦理","desc":"爱情、亲情、友情、人性抉择"},
                {"id":"fairy-tale","name":"🧙 黑暗童话","desc":"经典童话/故事的暗黑反转"},
                {"id":"urban","name":"🌃 都市传说","desc":"现代都市诡异怪谈"},
                {"id":"history","name":"📜 历史秘闻","desc":"历史事件/人物的另类解读"},
                {"id":"dark-humor","name":"😈 黑色幽默","desc":"讽刺荒诞、出人意料"},
                {"id":"psychological","name":"🌀 心理迷宫","desc":"人格分裂、记忆陷阱、梦境"}
            ]},
            "/api/admin/ai-approve-all": {"ok": True},
            "/api/admin/tts/cosyvoice": {"ok": False, "error": "独立模式无 TTS"},
            "/api/tts/cosyvoice-uninstall": {"ok": True},
            "/api/tts/synthesize": {"ok": True, "url": ""},
        }
        handler = special.get(path)
        if handler is not None:
            return self._json(handler)
        # CosyVoice 部署（独立处理 — 需要动态状态）
        if path == "/api/tts/cosyvoice-deploy":
            _cv_deploy["deploying"] = True
            _cv_deploy["_step"] = 0
            _cv_deploy["progress"] = _CV_STEPS[0]
            _cv_deploy["error"] = None
            return self._json({"ok": True})
        if path == "/api/tts/cosyvoice-speaker":
            return self._json({"ok": True, "speakers": {}})
        self._json({"error": "not found"}, status=404)

    # ── PUT（违禁词批量设置）──
    def do_PUT(self):
        self._json({"ok": True})

    # ── DELETE ──
    def do_DELETE(self):
        self._json({"ok": True})

    # ── Response helpers ──
    def _html(self, content: str):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def _json(self, data: dict, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def log_message(self, fmt, *args):
        if args and args[1] != "/api/health":
            print(f"  [HTTP] {args[0]} {args[1]} {args[2]}")


# ── WebSocket Handler ──
async def _ws_serve(host, port):
    """启动 WebSocket 服务器 —— 处理心跳和基本状态推送"""
    try:
        import websockets
    except ImportError:
        print("[WS] websockets 未安装，WebSocket 不可用")
        return

    async def handler(websocket):
        try:
            await websocket.send(json.dumps({"type": "connected", "standalone": True, "phase": _mock_state.phase}))
            async for message in websocket:
                try:
                    data = json.loads(message)
                    msg_type = data.get("type", "")
                    if msg_type == "ping":
                        await websocket.send(json.dumps({"type": "pong"}))
                    elif msg_type == "start_round":
                        _mock_state.phase = "playing"
                        _mock_state.start_time = time.time()
                        await websocket.send(json.dumps({
                            "type": "game_start", "phase": "reading",
                            "soupText": "（独立模式 — 无游戏后端）",
                            "soupAnswer": "", "charStates": [],
                            "maxLike": 500, "roundTimeout": 600,
                        }))
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass

    async def serve():
        async with websockets.serve(handler, host, port, ping_interval=30):
            await asyncio.Future()

    try:
        await serve()
    except OSError as e:
        print(f"[WS] 端口 {port} 被占用: {e}")


# ── Overlay JS API（PyWebView） ──
class OverlayApi:
    """PyWebView JS API — 从 admin 页面控制 overlay 窗口"""
    def __init__(self, overlay_url: str):
        self._overlay_url = overlay_url
        self._window = None
        self._lock = threading.Lock()

    def open_overlay(self) -> dict:
        with self._lock:
            if self._window is not None:
                try:
                    self._window.show()
                    return {"ok": True, "already_open": True}
                except Exception:
                    self._window = None
            import webview
            self._window = webview.create_window(
                "海龟汤 · 投屏端",
                url=self._overlay_url,
                width=480, height=854, resizable=True,
            )
            self._window.events.closed += self._on_closed
        return {"ok": True}

    def close_overlay(self) -> dict:
        with self._lock:
            if self._window is None:
                return {"ok": True, "already_closed": True}
            try:
                self._window.destroy()
            except Exception:
                pass
            self._window = None
        return {"ok": True}

    def _on_closed(self):
        self._window = None


# ── 入口 ──
def main():
    import argparse
    parser = argparse.ArgumentParser(description="海龟汤 · 独立集成版")
    parser.add_argument("--port", type=int, default=PORT, help=f"HTTP 端口（默认 {PORT}）")
    parser.add_argument("--backend", type=str, default=None,
                        help="外部后端地址（如 http://myserver:3010），省略则使用模拟模式")
    parser.add_argument("--no-gui", action="store_true", help="无 GUI 模式（仅启动服务器）")
    args = parser.parse_args()

    # ── 授权状态（静默检查，不再弹窗阻塞） ──
    auth = lic.check()

    port = args.port
    ws_port = port + 1
    server_url = f"http://{HOST}:{port}"
    ws_url = f"ws://{HOST}:{ws_port}/ws"

    # 注入 HTML
    global ADMIN_HTML_RAW, OVERLAY_HTML_RAW
    if args.backend:
        backend = args.backend.rstrip("/")
        b_ws_url = backend.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
        ADMIN_HTML_RAW = inject_html(ADMIN_HTML_RAW, backend, b_ws_url)
        OVERLAY_HTML_RAW = inject_html(OVERLAY_HTML_RAW, backend, b_ws_url)
        mode = f"后端: {backend}"
    else:
        ADMIN_HTML_RAW = inject_html(ADMIN_HTML_RAW, server_url, ws_url)
        OVERLAY_HTML_RAW = inject_html(OVERLAY_HTML_RAW, server_url, ws_url)
        mode = "独立模式（模拟 API，无后端依赖）"

    print("=" * 50)
    print("  海龟汤 · 独立集成版")
    print(f"  {mode}")
    print("=" * 50)
    print(f"  控制面板: {server_url}/")
    print(f"  投屏端:   {server_url}/overlay")
    print(f"  WebSocket: {ws_url}")
    if auth.get("source") == "trial":
        remain = lic.format_remaining(auth.get("remaining_seconds", 0))
        print(f"  授权: 试用模式（剩余 {remain}）")
    elif auth.get("source") == "license":
        if auth.get("is_permanent"):
            print(f"  授权: 永久授权")
        else:
            print(f"  授权: 授权码（剩余 {auth.get('remaining_days', 0)} 天）")
    print("=" * 50)

    # ── 启动 HTTP 服务器 ──
    httpd = HTTPServer((HOST, port), Handler)
    http_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    http_thread.start()

    # ── 启动 WebSocket 服务器 ──
    ws_thread = threading.Thread(
        target=lambda: asyncio.run(_ws_serve(HOST, ws_port)),
        daemon=True,
    )
    ws_thread.start()

    if args.no_gui:
        print("\n[无 GUI 模式] 按 Ctrl+C 停止...")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            print("\n正在关闭...")
        finally:
            httpd.shutdown()
        return

    # ── GUI 模式 —— PyWebView ──
    if args.backend:
        overlay_url = f"{args.backend.rstrip('/')}/overlay"
    else:
        overlay_url = f"{server_url}/overlay"

    try:
        import webview
        webview.create_window(
            "海龟汤 · 控制台"
            if not args.backend else "海龟汤 · 控制台（远程模式）",
            url=server_url,
            width=1280, height=800, resizable=True,
            js_api=OverlayApi(overlay_url),
        )
        webview.start(private_mode=True, debug=False)
    except ImportError:
        import webbrowser
        webbrowser.open(server_url)
        httpd.serve_forever()
    except Exception as e:
        print(f"[错误] GUI 启动失败: {e}")
        traceback.print_exc()
        import webbrowser
        webbrowser.open(server_url)
        httpd.serve_forever()
    finally:
        httpd.shutdown()
    print("[独立版] 已退出")


if __name__ == "__main__":
    main()

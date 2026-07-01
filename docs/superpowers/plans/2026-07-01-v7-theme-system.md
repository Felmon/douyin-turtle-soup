# V7.1 主题系统 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** overlay 端支持 3 个内置主题（暗色/星空紫/春节红），admin 控制台切换，配置跨重启保留。

**Architecture:** 服务端在 `GET /overlay` 时读 SQLite `settings.active_theme` → 用 `theme_manager.apply_to_html()` 把 CSS 变量注入到 HTML `<head>`；admin 通过 `POST /api/admin/theme` 切换 → 服务端写 SQLite + 广播 `theme_change` WS → overlay 收到后 `location.reload()`。

**Tech Stack:** Python 3.10+、FastAPI、SQLite WAL、纯 HTML+CSS（无新依赖）。

## Global Constraints

- 主题 CSS 变量注入到 overlay HTML 已有的 `<style>:root{}` 块中（覆盖原值）
- 主题配置跨重启保留（SQLite `settings` 表）
- 主题 ID 白名单校验（只能是 `dark` / `starry` / `festival`）
- 静态资源目录 `backend/themes/{id}/bg.jpg` 允许缺失（CSS 中 `url()` 失败不阻断渲染）
- WS 广播 `theme_change` 时 payload 必含 `theme_id`
- 不修改 overlay.js 中除 `theme_change` 处理以外的任何业务逻辑

---

## File Structure

**新建：**
- `backend/theme_manager.py` — 主题定义、SQLite 持久化、HTML 注入（独立模块，单一职责）
- `backend/themes/dark/bg.jpg` — 占位（可选，缺失时 CSS url 失败降级为纯渐变）
- `backend/themes/starry/bg.jpg` — 占位
- `backend/themes/festival/bg.jpg` — 占位
- `tests/test_theme_manager.py` — 单元测试

**修改：**
- `backend/server_v6.py` — 新增 `settings` 表 + 3 个端点 + 静态文件挂载 + overlay 注入
- `backend/overlay.py` — 删除原 `<style>:root{}` 块内容（保留结构），新增 `theme_change` WS 处理
- `backend/admin.py` — 新增"主题"Tab + 3 卡片 UI + `loadThemes()` + `theme_change` WS 处理

---

### Task 1: 创建 theme_manager.py 模块骨架

**Files:**
- Create: `backend/theme_manager.py`
- Create: `tests/test_theme_manager.py`

**Interfaces:**
- Produces:
  - `BUILTIN_THEMES: dict[str, dict]` — 3 个主题配置
  - `class ThemeManager` — 见下方签名
  - `theme_manager: ThemeManager` — 模块级单例

**Step 1.1: 写失败测试**

创建 `tests/test_theme_manager.py`：

```python
"""主题管理器单元测试"""
import os
import tempfile
import pytest


@pytest.fixture
def tm():
    """每个测试用独立临时 DB"""
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "test.db")
        from theme_manager import ThemeManager
        return ThemeManager(db_path=db)


def test_default_active_is_dark(tm):
    """空 DB 时活动主题回退到 dark"""
    assert tm.get_active() == "dark"


def test_set_and_get_active(tm):
    """set_active 后 get_active 返回新值"""
    tm.set_active("starry")
    assert tm.get_active() == "starry"


def test_persistence_across_instances(tmp_path):
    """新实例从同 DB 读到上次写入的值"""
    from theme_manager import ThemeManager
    db = str(tmp_path / "test.db")
    a = ThemeManager(db_path=db)
    a.set_active("festival")
    b = ThemeManager(db_path=db)
    assert b.get_active() == "festival"


def test_unknown_id_falls_back_to_dark(tm):
    """越权值回退到 dark（白名单校验）"""
    tm.set_active("hack")
    assert tm.get_active() == "dark"


def test_list_themes_returns_three(tm):
    """list_themes 返回 3 个内置主题"""
    themes = tm.list_themes()
    assert len(themes) == 3
    ids = {t["id"] for t in themes}
    assert ids == {"dark", "starry", "festival"}


def test_apply_to_html_injects_vars(tm):
    """apply_to_html 返回的 HTML 含主题 CSS 变量"""
    html = "<html><head><style>:root{}</style></head></html>"
    out = tm.apply_to_html(html, "starry")
    assert "--primary: #a855f7" in out
    assert "url('/static/themes/starry/bg.jpg')" in out


def test_apply_to_html_invalid_id_returns_unchanged(tm):
    """无效主题 id 不修改 HTML"""
    html = "<html><head><style>:root{}</style></head></html>"
    out = tm.apply_to_html(html, "hack")
    assert out == html
```

**Step 1.2: 跑测试确认失败**

```bash
cd "C:\Users\27871\OneDrive\Documents\抖音海龟汤"
python -m pytest tests/test_theme_manager.py -v
```

Expected: 全部失败，`ModuleNotFoundError: No module named 'theme_manager'`

**Step 1.3: 实现 theme_manager.py**

创建 `backend/theme_manager.py`：

```python
"""主题管理器 — 3 个内置主题 + SQLite 持久化 + HTML 注入

设计:
  - BUILTIN_THEMES: 硬编码 3 个主题的完整 CSS 变量映射
  - ThemeManager: 实例方法操作 SQLite settings 表
  - apply_to_html: 在 <style>:root{} 块中插入 CSS 变量
"""
import json
import sqlite3
import time
from pathlib import Path
from threading import Lock


# 3 个内置主题的完整 CSS 变量映射
BUILTIN_THEMES = {
    "dark": {
        "id": "dark",
        "name": "经典暗夜",
        "accent": "#00d4ff",
        "vars": {
            "--bg": "#050714",
            "--bg-grad": "linear-gradient(180deg,#0a0e26 0%,#1a0e3a 50%,#260e26 100%)",
            "--card": "rgba(12,16,38,0.88)",
            "--card-border": "rgba(255,255,255,0.08)",
            "--primary": "#00d4ff",
            "--gold": "#fbbf24",
            "--green": "#22c55e",
            "--red": "#ef4444",
            "--yellow": "#eab308",
            "--pink": "#f472b6",
            "--purple": "#a855f7",
            "--text": "#f1f5f9",
            "--text-dim": "#94a3b8",
            "--text-dimmer": "#475569",
            "--bg-image": "url('/static/themes/dark/bg.jpg')",
        },
    },
    "starry": {
        "id": "starry",
        "name": "星空紫",
        "accent": "#a855f7",
        "vars": {
            "--bg": "#0a0418",
            "--bg-grad": "linear-gradient(180deg,#1a0a2e 0%,#2d0a4a 50%,#1a0a2e 100%)",
            "--card": "rgba(30,15,55,0.88)",
            "--card-border": "rgba(168,85,247,0.15)",
            "--primary": "#a855f7",
            "--gold": "#fbbf24",
            "--green": "#22c55e",
            "--red": "#ef4444",
            "--yellow": "#eab308",
            "--pink": "#f472b6",
            "--purple": "#7c3aed",
            "--text": "#f1f5f9",
            "--text-dim": "#c4b5fd",
            "--text-dimmer": "#6d28d9",
            "--bg-image": "url('/static/themes/starry/bg.jpg')",
        },
    },
    "festival": {
        "id": "festival",
        "name": "春节红",
        "accent": "#ef4444",
        "vars": {
            "--bg": "#1a0505",
            "--bg-grad": "linear-gradient(180deg,#3d0a0a 0%,#5a0a0a 50%,#3d0a0a 100%)",
            "--card": "rgba(50,10,10,0.88)",
            "--card-border": "rgba(251,191,36,0.2)",
            "--primary": "#ef4444",
            "--gold": "#fbbf24",
            "--green": "#22c55e",
            "--red": "#dc2626",
            "--yellow": "#fbbf24",
            "--pink": "#f472b6",
            "--purple": "#a855f7",
            "--text": "#fef3c7",
            "--text-dim": "#fbbf24",
            "--text-dimmer": "#92400e",
            "--bg-image": "url('/static/themes/festival/bg.jpg')",
        },
    },
}

VALID_IDS = set(BUILTIN_THEMES.keys())


class ThemeManager:
    """主题管理器单例。

    Args:
        db_path: SQLite 数据库路径。None 时使用默认 backend/data/v6.db。
    """

    def __init__(self, db_path: str | None = None):
        if db_path is None:
            db_path = str(Path(__file__).resolve().parent / "data" / "v6.db")
        self.db_path = db_path
        self._lock = Lock()
        # 确保 data 目录存在
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with self._lock:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.execute("""CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at REAL
            )""")
            conn.commit()
            conn.close()

    def get_active(self) -> str:
        """返回当前活动主题 id，越权值回退到 dark。"""
        with self._lock:
            try:
                conn = sqlite3.connect(self.db_path, check_same_thread=False)
                row = conn.execute(
                    "SELECT value FROM settings WHERE key='active_theme'"
                ).fetchone()
                conn.close()
            except Exception:
                return "dark"
        if not row or row[0] not in VALID_IDS:
            return "dark"
        return row[0]

    def set_active(self, theme_id: str) -> None:
        """写入活动主题。无效 id 抛 ValueError。"""
        if theme_id not in VALID_IDS:
            raise ValueError(f"Unknown theme_id: {theme_id}")
        with self._lock:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.execute(
                "INSERT OR REPLACE INTO settings(key, value, updated_at) VALUES(?,?,?)",
                ("active_theme", theme_id, time.time()),
            )
            conn.commit()
            conn.close()

    def get_theme_dict(self, theme_id: str) -> dict:
        """返回某主题的完整 CSS 变量字典。"""
        return BUILTIN_THEMES[theme_id]["vars"]

    def list_themes(self) -> list[dict]:
        """返回 [{\"id\", \"name\", \"accent\", \"preview\"}, ...]"""
        return [
            {"id": t["id"], "name": t["name"], "accent": t["accent"],
             "preview": t["vars"]["--bg-grad"]}
            for t in BUILTIN_THEMES.values()
        ]

    def apply_to_html(self, html: str, theme_id: str) -> str:
        """在 HTML <style>:root{} 块中注入 CSS 变量。

        策略: 找到第一个 `<style>` 标签后的 `:root{...}` 块，替换为新的。
        若未找到或 theme_id 无效，返回原 HTML。
        """
        if theme_id not in VALID_IDS:
            return html
        vars_dict = BUILTIN_THEMES[theme_id]["vars"]
        # 生成 :root CSS
        css_lines = [f"  {k}: {v};" for k, v in vars_dict.items()]
        css_block = ":root {\n" + "\n".join(css_lines) + "\n}"
        # 替换第一个 :root{...} 块（支持多行）
        import re
        pattern = r":root\s*\{[^}]*\}"
        new_html, n = re.subn(pattern, css_block, html, count=1)
        if n == 0:
            # 没找到 :root 块，在第一个 </style> 前插入
            new_html = html.replace("</style>", f"{css_block}\n</style>", 1)
        return new_html


# 模块级单例
theme_manager = ThemeManager()
```

**Step 1.4: 跑测试确认全部通过**

```bash
cd "C:\Users\27871\OneDrive\Documents\抖音海龟汤"
python -m pytest tests/test_theme_manager.py -v
```

Expected: 7 passed

**Step 1.5: 提交**

```bash
cd "C:\Users\27871\OneDrive\Documents\抖音海龟汤"
git add backend/theme_manager.py tests/test_theme_manager.py
git commit -m "feat(v7.1): add theme_manager with 3 builtin themes + persistence"
```

---

### Task 2: 创建主题资源目录 + 占位 bg.jpg

**Files:**
- Create: `backend/themes/dark/bg.jpg`
- Create: `backend/themes/starry/bg.jpg`
- Create: `backend/themes/festival/bg.jpg`

**Step 2.1: 创建目录和 1x1 占位图**

```bash
cd "C:\Users\27871\OneDrive\Documents\抖音海龟汤"
mkdir -p backend/themes/dark backend/themes/starry backend/themes/festival
```

为每个主题生成 1x1 像素的占位 JPEG（用 Python 内置库，无 PIL 依赖）：

```bash
cd "C:\Users\27871\OneDrive\Documents\抖音海龟汤"
python3 -c "
import struct
# 最小有效 JPEG 1x1 白色像素
# 来源: 手工构造
jpeg_bytes = bytes.fromhex(
    'ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707070909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c30313434341f27393d38323c2e333432ffc0000b080001000101011100ffc4001f0000010501010101010100000000000000000102030405060708090a0bffc400351000020103030204030505040400000102770001020311040521310612415107617113423281081442291a1b1c109233352f0156272d10a162434e125f11718191a262728292a3536373839a434445464748494a535455565758595a636465666768696a737475767778797a838485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2f3f4f5f6f7f8f9faffda0008010100003f00fb95ffd9'
)
for name in ['dark', 'starry', 'festival']:
    open(f'backend/themes/{name}/bg.jpg', 'wb').write(jpeg_bytes)
print('OK: 3 placeholder bg.jpg created')
"
```

**Step 2.2: 验证文件存在**

```bash
ls -la backend/themes/*/bg.jpg
```

Expected: 3 个文件各 ~134 字节

**Step 2.3: 提交**

```bash
cd "C:\Users\27871\OneDrive\Documents\抖音海龟汤"
git add backend/themes/
git commit -m "feat(v7.1): add 3 theme directories with placeholder bg.jpg"
```

---

### Task 3: server_v6.py — 新增 settings 表 + 3 个端点

**Files:**
- Modify: `backend/server_v6.py:71-97`（_db.executescript 区域）

**Interfaces:**
- Consumes: `theme_manager` from `theme_manager.py`（Task 1）

**Step 3.1: 在 imports 后添加 theme_manager 导入**

在 `backend/server_v6.py` 第 42 行（`from tiers import ...`）后新增：

```python
from theme_manager import theme_manager, ThemeManager
```

**Step 3.2: 在 _db.executescript 中新增 settings 表**

在 `backend/server_v6.py` 的 `_db.executescript("""...""")` 块末尾（`custom_soups` 表后）追加：

```sql
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at REAL
);
```

完整新块：

```python
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
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at REAL
);
""")
```

**Step 3.3: 修改 overlay_page() 注入主题**

找到 `backend/server_v6.py` 的 `async def overlay_page():` 函数（搜索 `overlay_page`），替换为：

```python
@app.get("/overlay")
async def overlay_page():
    active = theme_manager.get_active()
    html = theme_manager.apply_to_html(OVERLAY_HTML, active)
    return HTMLResponse(html)
```

**Step 3.4: 挂载静态主题资源**

在 `app.add_middleware(...)` 之后（搜索 `CORSMiddleware`）新增：

```python
from fastapi.staticfiles import StaticFiles
THEMES_DIR = Path(__file__).resolve().parent / "themes"
THEMES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static/themes", StaticFiles(directory=str(THEMES_DIR)), name="themes")
```

**Step 3.5: 新增 3 个端点**

在 `server_v6.py` 中找一个合适位置（如 `async def admin_metrics` 之后）追加：

```python
# ── HTTP API: 主题系统 ──
@app.get("/api/theme")
async def get_theme():
    """返回当前活动主题 CSS 变量。overlay 启动时调用。"""
    active = theme_manager.get_active()
    return {"theme_id": active, "vars": theme_manager.get_theme_dict(active)}


@app.get("/api/admin/themes")
async def list_themes():
    """返回所有内置主题列表（admin Tab 用）。"""
    return {"themes": theme_manager.list_themes()}


class ThemeReq(BaseModel):
    theme_id: str


@app.post("/api/admin/theme")
async def set_theme(req: ThemeReq):
    """切换活动主题 + 广播 WS 消息。"""
    try:
        theme_manager.set_active(req.theme_id)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    await manager.broadcast({"type": "theme_change", "theme_id": req.theme_id})
    return {"ok": True, "theme_id": req.theme_id}
```

**Step 3.6: 语法检查**

```bash
cd "C:\Users\27871\OneDrive\Documents\抖音海龟汤"
python -m py_compile backend/server_v6.py && echo OK
```

**Step 3.7: 启动服务并 curl 验证端点**

```bash
cd "C:\Users\27871\OneDrive\Documents\抖音海龟汤"
python backend/server_v6.py &
SERVER_PID=$!
sleep 2
echo "--- GET /api/admin/themes ---"
curl -s http://localhost:3010/api/admin/themes
echo ""
echo "--- POST /api/admin/theme starry ---"
curl -s -X POST http://localhost:3010/api/admin/theme -H "Content-Type: application/json" -d '{"theme_id":"starry"}'
echo ""
echo "--- GET /api/theme ---"
curl -s http://localhost:3010/api/theme
echo ""
echo "--- POST invalid id (should error) ---"
curl -s -X POST http://localhost:3010/api/admin/theme -H "Content-Type: application/json" -d '{"theme_id":"hack"}'
echo ""
echo "--- GET /overlay (first 200 chars) ---"
curl -s http://localhost:3010/overlay | head -c 200
echo ""
kill $SERVER_PID
```

Expected:
- `/api/admin/themes` 返回 `{"themes": [...]}` 含 3 个
- `/api/admin/theme` POST 后 `{"ok": true, "theme_id": "starry"}`
- `/api/theme` 返回 `{"theme_id": "starry", "vars": {...}}`
- 越权值 `{"ok": false, "error": "Unknown theme_id: hack"}`
- `/overlay` HTML 含 `--primary: #a855f7`（因为已切到 starry）

**Step 3.8: 提交**

```bash
cd "C:\Users\27871\OneDrive\Documents\抖音海龟汤"
git add backend/server_v6.py
git commit -m "feat(v7.1): add /api/theme + theme admin endpoints with SQLite persistence"
```

---

### Task 4: overlay.py — 清理 :root 块 + 添加 theme_change WS 处理

**Files:**
- Modify: `backend/overlay.py:27-45`（CSS `:root{}` 块）
- Modify: `backend/overlay.py:680-744`（handleMessage switch）

**Step 4.1: 清理 :root{} 块内容**

找到 `backend/overlay.py` 第 27-45 行的 `:root { ... }` 块（搜索 `:root {`），**删除**其中的所有 `--*` 变量赋值，**保留** `:root {` 和 `}` 行及注释。结构如下：

```css
:root {
  /* CSS 变量由服务端 theme_manager.apply_to_html() 注入 */
}
```

最终内容（替换 27-45 行）：

```css
:root {
  /* CSS 变量由服务端 theme_manager.apply_to_html() 注入 */
}
```

**Step 4.2: 新增 theme_change WS 处理**

在 `handleMessage` switch 块中（搜索 `case 'metrics_update':`），`metrics_update` case 之后新增：

```js
    case 'theme_change':
      location.reload();
      break;
```

**Step 4.3: 语法检查**

```bash
cd "C:\Users\27871\OneDrive\Documents\抖音海龟汤"
python -m py_compile backend/overlay.py && echo OK
```

**Step 4.4: 验证 HTML 注入**

启动服务：

```bash
cd "C:\Users\27871\OneDrive\Documents\抖音海龟汤"
python backend/server_v6.py &
sleep 2
curl -s http://localhost:3010/overlay | grep -A 2 ":root"
kill %1
```

Expected: `:root {` 块内含 `--primary: #00d4ff`（默认 dark 主题）

**Step 4.5: 提交**

```bash
cd "C:\Users\27871\OneDrive\Documents\抖音海龟汤"
git add backend/overlay.py
git commit -m "feat(v7.1): strip hardcoded :root vars (server injects), handle theme_change WS"
```

---

### Task 5: admin.py — 新增"主题"Tab + 3 卡片 UI

**Files:**
- Modify: `backend/admin.py:127-130`（tabs 区域）
- Modify: `backend/admin.py:280-294`（handleMessage switch）
- Modify: `backend/admin.py:501-511`（script 末尾）

**Step 5.1: 新增"主题"Tab 按钮**

在 `backend/admin.py` 的 tabs 区域（搜索 `<div class="tab active" data-tab="game">`），在最后一个 `<div class="tab " data-tab="...">` 之后新增：

```html
    <div class="tab" data-tab="theme">🎨 主题</div>
```

**Step 5.2: 新增主题 Tab content 容器**

在 `backend/admin.py` 最后一个 `<div class="tab-content" data-tab="...">` 之后新增：

```html
  <div class="tab-content" data-tab="theme" id="themeTab">
    <div class="section">
      <h2>当前主题</h2>
      <div id="themeGrid" class="theme-grid"></div>
    </div>
  </div>
```

**Step 5.3: 添加主题卡片 CSS**

在 `backend/admin.py` 的 CSS 区域末尾（搜索 `</style>` 之前）追加：

```css
.theme-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:8px}
.theme-card{background:rgba(0,0,0,0.3);border:2px solid rgba(255,255,255,0.06);border-radius:10px;padding:14px;cursor:pointer;transition:all 0.2s}
.theme-card:hover{border-color:rgba(0,212,255,0.4);transform:translateY(-2px)}
.theme-card.active{border-color:#00d4ff;box-shadow:0 0 20px rgba(0,212,255,0.3)}
.theme-card .preview{height:60px;border-radius:6px;margin-bottom:8px;border:1px solid rgba(255,255,255,0.05)}
.theme-card .name{font-size:14px;font-weight:700;color:#e2e8f0;margin-bottom:4px}
.theme-card .accent{display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:6px;vertical-align:middle}
.theme-card .btn{margin-top:8px;width:100%}
```

**Step 5.4: 添加 loadThemes + applyTheme 函数**

在 admin.py `<script>` 末尾（`</script>` 之前）追加：

```js
async function loadThemes() {
  const data = await apiGet('/api/admin/themes');
  const grid = document.getElementById('themeGrid');
  if (!data.themes) return;
  const current = await apiGet('/api/theme');
  grid.innerHTML = data.themes.map(t => {
    const isActive = t.id === current.theme_id;
    return '<div class="theme-card' + (isActive ? ' active' : '') + '" data-theme-id="' + escapeHtml(t.id) + '">' +
      '<div class="preview" style="background:' + t.preview + '"></div>' +
      '<div class="name"><span class="accent" style="background:' + t.accent + '"></span>' + escapeHtml(t.name) + (isActive ? ' ✓' : '') + '</div>' +
      '<button class="btn btn-primary btn-sm">应用</button>' +
      '</div>';
  }).join('');
  grid.querySelectorAll('.theme-card').forEach(card => {
    card.addEventListener('click', () => applyTheme(card.dataset.themeId));
  });
}

async function applyTheme(id) {
  const res = await apiPost('/api/admin/theme', {theme_id: id});
  if (res.ok) {
    addLog('🎨 主题已切换: ' + id);
    loadThemes();
  } else {
    addLog('❌ 主题切换失败: ' + (res.error || ''));
  }
}
```

**Step 5.5: 注册主题 Tab 加载**

找到 admin.py 的 `loadInitialData()` 或类似函数（搜索 `loadSlots\|loadMetrics\|loadSoup`），在末尾追加 `loadThemes();`：

```js
  loadThemes();
```

**Step 5.6: handleMessage 新增 theme_change**

在 `handleMessage` switch 块中（搜索 `case 'metrics_update':`），在 metrics_update case 后新增：

```js
    case 'theme_change': loadThemes(); break;
```

**Step 5.7: 语法检查**

```bash
cd "C:\Users\27871\OneDrive\Documents\抖音海龟汤"
python -m py_compile backend/admin.py && echo OK
```

**Step 5.8: 手动验证**

启动服务：

```bash
cd "C:\Users\27871\OneDrive\Documents\抖音海龟汤"
python backend/server_v6.py &
sleep 2
echo "打开 Chrome: http://localhost:3010/admin"
echo "点击 🎨 主题 Tab → 应该看到 3 个卡片"
echo "点击 星空紫 的应用 → 卡片高亮应切到 starry"
echo "OBS overlay 抓的画面应变成紫色调"
kill %1
```

**Step 5.9: 提交**

```bash
cd "C:\Users\27871\OneDrive\Documents\抖音海龟汤"
git add backend/admin.py
git commit -m "feat(v7.1): add theme tab in admin with 3 theme cards + apply handler"
```

---

### Task 6: 端到端集成测试

**Files:**
- Modify: `tests/test_theme_manager.py`（追加集成场景）

**Step 6.1: 追加集成测试**

在 `tests/test_theme_manager.py` 末尾追加：

```python
def test_apply_persists_across_simulated_restart(tmp_path):
    """模拟重启: set → 新实例 → get 验证持久化"""
    from theme_manager import ThemeManager
    db = str(tmp_path / "test.db")
    a = ThemeManager(db_path=db)
    for tid in ["dark", "starry", "festival", "dark"]:
        a.set_active(tid)
        b = ThemeManager(db_path=db)
        assert b.get_active() == tid


def test_apply_to_html_preserves_rest_of_document(tm):
    """注入只改 :root，不破坏其他 HTML"""
    html = "<html><head><style>:root{--old: red;}</style></head><body>其他</body></html>"
    out = tm.apply_to_html(html, "festival")
    assert "其他" in out
    assert "--primary: #ef4444" in out
    assert "--old" not in out  # 旧变量被覆盖


def test_all_themes_have_consistent_var_keys():
    """3 个主题必须有相同的 15 个 CSS 变量键（防缺漏）"""
    from theme_manager import BUILTIN_THEMES
    keys_per_theme = {tid: set(t["vars"].keys()) for tid, t in BUILTIN_THEMES.items()}
    reference = keys_per_theme["dark"]
    for tid, keys in keys_per_theme.items():
        assert keys == reference, f"Theme {tid} missing vars: {reference - keys}"
```

**Step 6.2: 跑全部测试**

```bash
cd "C:\Users\27871\OneDrive\Documents\抖音海龟汤"
python -m pytest tests/test_theme_manager.py -v
```

Expected: 10 passed

**Step 6.3: 提交**

```bash
cd "C:\Users\27871\OneDrive\Documents\抖音海龟汤"
git add tests/test_theme_manager.py
git commit -m "test(v7.1): add integration tests for theme persistence and var consistency"
```

---

### Task 7: 更新 V7_实施纲要.md + 收尾

**Files:**
- Modify: `V7_实施纲要.md`（新增 §15 主题系统章节）

**Step 7.1: 追加 §15 主题系统章节**

在 `V7_实施纲要.md` 文件末尾追加：

```markdown

---

## 15. 主题系统（V7.1 新增）

### 15.1 主题列表

| ID | 中文名 | accent | 风格 |
|----|--------|--------|------|
| `dark` | 经典暗夜 | `#00d4ff` 青蓝 | 当前默认 |
| `starry` | 星空紫 | `#a855f7` 紫色 | 背景更暗、紫色主导 |
| `festival` | 春节红 | `#ef4444` 红金 | 红色 + 金色主导 |

### 15.2 主题存储

- SQLite `settings` 表（`active_theme` key）
- 跨重启保留
- 越权值回退到 `dark`（白名单校验）

### 15.3 API

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/theme` | overlay 启动拉取当前主题 CSS 变量 |
| GET | `/api/admin/themes` | admin 列出 3 个内置主题 |
| POST | `/api/admin/theme` | admin 切换主题 + 广播 `theme_change` |

### 15.4 数据流

```
admin POST /api/admin/theme
  → 写 SQLite
  → broadcast theme_change
    → overlay 收到 → location.reload()
      → GET /overlay → 服务端注入新主题 CSS 变量到 :root
    → admin 收到 → loadThemes() 刷新高亮
```

### 15.5 资源目录

```
backend/themes/
  dark/      bg.jpg
  starry/    bg.jpg
  festival/  bg.jpg
```

通过 `app.mount("/static/themes", ...)` 挂载。
```

**Step 7.2: 提交**

```bash
cd "C:\Users\27871\OneDrive\Documents\抖音海龟汤"
git add V7_实施纲要.md
git commit -m "docs(v7.1): document theme system in V7 spec §15"
```

---

## Self-Review Checklist

✅ **Spec coverage：**
- 3 个内置主题 → Task 1
- SQLite 持久化 → Task 1, 3
- 注入 HTML → Task 1, 4
- 静态资源 → Task 2, 3
- 3 个 API 端点 → Task 3
- admin UI → Task 5
- WS `theme_change` → Task 4, 5
- 单元测试 → Task 1, 6
- 文档 → Task 7

✅ **No placeholders:** 每个 step 都有完整代码或命令

✅ **Type consistency:** `ThemeManager` 签名在 Task 1 定义，Task 3 复用一致；`theme_manager` 单例在 Task 1 创建，Task 3 导入

✅ **YAGNI:** 不做主题编辑器、不做用户上传、不做预览图

✅ **Frequent commits:** 7 个 task 各自独立 commit

# V7.1 主题系统 设计

> 父项目：抖音海龟汤 V7（三端分离重构）
> 子项目 V7.1：素材目录 + 主题系统
> 日期：2026-07-01

## 目标

overlay 端支持 3 个内置主题（暗色 / 星空 / 春节红），admin 控制台可下拉切换，OBS 刷新即生效，配置跨重启保留。

非目标（YAGNI）：
- 不做在线主题编辑器
- 不做用户上传主题
- 不做主题预览图
- 不做主题动画差异

## 架构

```
backend/
  themes/
    dark/        bg.jpg + accent vars
    starry/      bg.jpg + accent vars
    festival/    bg.jpg + accent vars
  theme_manager.py   # 主题加载 + SQLite 持久化 + HTML 注入
  server_v6.py       # 新增 theme 路由 + overlay 注入

SQLite 新增表:
  settings (key TEXT PRIMARY KEY, value TEXT, updated_at REAL)
  -- 存 'active_theme' = 'dark' | 'starry' | 'festival'
```

## 组件

### `theme_manager.py`（新文件，约 80 行）

**导出：**
- `BUILTIN_THEMES: dict[str, ThemeDict]` — 3 个主题的完整 CSS 变量映射
- `class ThemeManager`:
  - `get_active() -> str` — 读 SQLite `settings.active_theme`，回退到 `"dark"`
  - `set_active(theme_id: str) -> None` — 写 SQLite，更新时间戳
  - `get_theme_dict(theme_id: str) -> ThemeDict` — 返回某主题的 CSS 变量字典
  - `list_themes() -> list[dict]` — 返回 `[{"id", "name", "accent", "preview"}]`
  - `apply_to_html(html: str, theme_id: str) -> str` — 在 HTML 的 `<head>` 注入 `<style>:root{...}</style>`

**`ThemeDict` 结构：**
```python
{
  "id": "dark",
  "name": "经典暗夜",
  "accent": "#00d4ff",
  "vars": {
    "--bg": "#050714",
    "--bg-grad": "linear-gradient(180deg,#0a0e26 0%,#1a0e3a 50%,#260e26 100%)",
    "--card": "rgba(12,16,38,0.88)",
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
  }
}
```

**3 个主题对比：**
| ID | 中文名 | accent | 风格差异 |
|----|--------|--------|----------|
| `dark` | 经典暗夜 | `#00d4ff` 青蓝 | 当前默认 |
| `starry` | 星空紫 | `#a855f7` 紫色 | 背景色更暗、紫色主导 |
| `festival` | 春节红 | `#ef4444` 红金 | 红色 + 金色主导 |

### `server_v6.py` 改动

**新增表（启动时 `_db.executescript`）：**
```sql
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at REAL
);
```

**新增 3 个端点：**

| 方法 | 路径 | body | 返回 |
|------|------|------|------|
| GET | `/api/theme` | - | `{"theme_id": "dark", "vars": {...}}` |
| GET | `/api/admin/themes` | - | `{"themes": [{id, name, accent, preview}]}` |
| POST | `/api/admin/theme` | `{"theme_id": "starry"}` | `{"ok": true, "theme_id": "..."}` |

**`/api/admin/theme` 副作用：**
- 写 SQLite
- `manager.broadcast({"type": "theme_change", "theme_id": "..."})`

**`overlay_page()` 改动：**
```python
@app.get("/overlay")
async def overlay_page():
    active = theme_manager.get_active()
    html = theme_manager.apply_to_html(OVERLAY_HTML, active)
    return HTMLResponse(html)
```

**静态文件挂载：**
```python
app.mount("/static/themes", StaticFiles(directory="backend/themes"), name="themes")
```

### `overlay.py` 改动

**HTML 中已有 `<style>:root{...}</style>` 块（行 27-45），删除该块的内容（保留注释标记），由服务端注入填充。**

**JS 新增 WS 处理：**
```js
case 'theme_change':
  // 重新加载页面以应用新主题
  location.reload();
  break;
```

### `admin.py` 改动

**新增"主题"Tab（第 6 个 Tab）：**

UI 结构（紧凑 3 卡片）：
```
┌─ 🎨 主题 ─────────────────────────┐
│ ┌────┐  ┌────┐  ┌────┐            │
│ │ 暗 │  │ 星 │  │ 春 │            │
│ │色  │  │ 空 │  │ 节 │            │
│ │[●] │  │[ ] │  │[ ] │            │
│ │应用│  │应用│  │应用│            │
│ └────┘  └────┘  └────┘            │
└────────────────────────────────────┘
```

- 启动时调 `GET /api/admin/themes` 渲染 3 卡片
- 当前激活主题用边框高亮
- 点击"应用" → `POST /api/admin/theme` → 收到 200 后重新渲染高亮
- WS 收到 `theme_change` → 重新拉 `/api/admin/themes`

**`handleMessage()` 新增：**
```js
case 'theme_change': loadThemes(); break;
```

## 数据流

```
admin POST /api/admin/theme {theme_id: "starry"}
  → server_v6 写 SQLite settings.active_theme = "starry"
  → manager.broadcast({type: "theme_change", theme_id: "starry"})
    → overlay 收到 → location.reload()
      → GET /overlay → theme_manager.apply_to_html(OVERLAY_HTML, "starry")
        → 返回的 HTML :root{} 含星空紫 CSS 变量
        → OBS 浏览器源下次刷帧呈现新主题
    → admin 收到 → loadThemes() 更新高亮
```

## 测试

**单元测试 `test_theme_manager.py`：**
1. `set_active("starry")` 后 `get_active()` 返回 `"starry"`
2. 重启进程后 `get_active()` 仍返回 `"starry"`
3. `list_themes()` 长度 == 3
4. `apply_to_html(html, "festival")` 后 HTML 含 `festival` 的 `--primary: #ef4444`
5. `get_active()` 在空表时回退到 `"dark"`

**集成测试：**
- 启动 server，admin 切到 festival，overlay reload 验证主色变红
- SQLite 直接改 `settings.active_theme` 越权值（如 `"hack"`），启动后 `get_active()` 应回退到 `dark`（白名单校验）

**手动验证：**
- OBS 抓 overlay 页面
- admin 切换 3 个主题，每次 overlay 应在 1s 内变化
- 重启 server，admin 显示的主题状态保持

## 风险

- **OBS 不自动 reload**：用户没切换主题时 OBS 不会自动刷新。V7.1 用 `location.reload()` 触发 OBS 自动刷帧（因为新 HTML 内容不同）
- **静态资源 404**：首次切换主题时 OBS 才开始下载 `bg.jpg`，有 1 次性网络延迟
- **CSS 变量注入位置**：必须注入在 overlay 已有的 `:root` 之后才能覆盖原值

## 不在 V7.1 范围

- V7.2 Dashboard 图表增强
- V7.3 Admin 功能补全（屏蔽词/参数热更）
- V7.4 代码清理 + 规范化

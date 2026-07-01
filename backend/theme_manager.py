"""主题管理器 — 3 个内置主题 + SQLite 持久化 + HTML 注入

设计:
  - BUILTIN_THEMES: 硬编码 3 个主题的完整 CSS 变量映射
  - ThemeManager: 实例方法操作 SQLite settings 表
  - apply_to_html: 在 <style>:root{} 块中插入 CSS 变量
"""
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
        # 确保 data 目录存在 + 表已建
        self._ensure_db()

    def _ensure_db(self):
        """确保父目录存在 + settings 表已建（幂等，每次操作前调用）"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
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
                self._ensure_db()
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
        """写入活动主题。无效 id 静默忽略（白名单在 get_active 处生效）。"""
        if theme_id not in VALID_IDS:
            return
        with self._lock:
            self._ensure_db()
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

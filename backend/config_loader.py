"""配置加载器 — 集中管理所有运行时配置

支持 .env 文件 + 环境变量覆盖 + 运行时动态修改。
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# ── 加载 .env ──
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    load_dotenv(str(_env_path), encoding="utf-8")
    print(f"[Config] 已加载 .env: {_env_path}")


class ConfigLoader:
    """配置管理（可热更新）。"""

    def __init__(self):
        self._data = {}

    def load(self):
        """从环境变量加载全部配置。"""
        self._data = {
            # LLM
            "LLM_API_KEY": os.getenv("LLM_API_KEY", ""),
            "LLM_BASE_URL": os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
            "LLM_MODEL": os.getenv("LLM_MODEL", "deepseek-v4-flash"),

            # 服务器
            "SERVER_PORT": int(os.getenv("SERVER_PORT", "3010")),

            # 抖音弹幕桥接
            "LIVE_WS_URL": os.getenv("LIVE_WS_URL", "ws://localhost:1088"),
            "BRIDGE_ENABLED": os.getenv("BRIDGE_ENABLED", "true").lower() == "true",

            # 运行模式
            "V6_MODE": os.getenv("V6_MODE", "self_hosted"),  # self_hosted | licensed

            # 游戏参数
            "ANTI_STALL_INTERVAL": int(os.getenv("ANTI_STALL_INTERVAL", "180")),
            "ANTI_STALL_MIN": int(os.getenv("ANTI_STALL_MIN", "30")),
            "ANTI_STALL_DANMAKU": int(os.getenv("ANTI_STALL_DANMAKU", "50")),
            "ANTI_STALL_DECAY": float(os.getenv("ANTI_STALL_DECAY", "0.8")),

            # 授权（预留）
            "LICENSE_KEY": os.getenv("LICENSE_KEY", ""),
            "LICENSE_MODE": os.getenv("LICENSE_MODE", "trial"),  # trial | personal | team | lifetime
        }

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value

    def all(self) -> dict:
        return dict(self._data)


# 全局单例
config = ConfigLoader()
config.load()

"""Pytest configuration — add backend/ to sys.path so tests can import theme_manager."""
import sys
from pathlib import Path

# 把 backend/ 目录加入 sys.path，使 from theme_manager import ... 生效
_BACKEND = Path(__file__).resolve().parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

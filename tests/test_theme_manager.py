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

"""设置持久化测试：界面设置（data/settings.json）与隐藏配置（resources/config/app_config.json）。

覆盖：读写、缺失/损坏回退、应用装配按设置初始化并写回、配置拆分边界。
"""

from __future__ import annotations

import json

from deltaforcebox.app import build_app
from deltaforcebox.core.settings import (
    DEFAULT_APP_CONFIG,
    DEFAULT_SETTINGS,
    load_app_config,
    load_settings,
    safe_int,
    save_settings,
)


def test_load_missing_file_returns_defaults(tmp_path):
    assert load_settings(tmp_path / "nope.json") == DEFAULT_SETTINGS


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    save_settings({"theme": "light", "language": "zh"}, path)
    loaded = load_settings(path)
    assert loaded["theme"] == "light"
    assert loaded["language"] == "zh"
    assert loaded["password_source_order"] == ["tmini", "shushu_fan"]  # 未写入的字段补默认值


def test_load_corrupt_file_returns_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not valid json", encoding="utf-8")
    assert load_settings(path) == DEFAULT_SETTINGS


def test_load_partial_merges_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"theme": "light"}), encoding="utf-8")
    loaded = load_settings(path)
    assert loaded["theme"] == "light"
    assert loaded["language"] == "zh"


def test_build_app_restores_persisted_theme(qapp, tmp_path):
    path = tmp_path / "settings.json"
    save_settings({"theme": "light", "language": "zh"}, path)
    _app, window = build_app(settings_path=path)
    assert window._theme.theme() == "light"
    assert window.pages["settings"].theme_combo.currentData() == "light"


def test_build_app_falls_back_to_default(qapp, tmp_path):
    _app, window = build_app(settings_path=tmp_path / "missing.json")
    assert window._theme.theme() == "dark"


def test_theme_change_persists_to_file(qapp, tmp_path):
    path = tmp_path / "settings.json"
    save_settings({"theme": "light", "language": "zh"}, path)
    _app, window = build_app(settings_path=path)
    window._theme.set_theme("dark")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["theme"] == "dark"
    assert data["language"] == "zh"


# ── 配置拆分：界面设置不含隐藏字段 ────────────────────

def test_settings_contains_only_ui_visible_keys(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"theme": "light", "puzzle_pieces": 200}), encoding="utf-8")
    values = load_settings(path)
    assert values["theme"] == "light"
    assert "puzzle_pieces" not in values
    assert "gun_sync_interval_days" not in values
    assert "image_cache_limit_mb" not in values


def test_save_settings_writes_only_ui_keys(tmp_path):
    path = tmp_path / "settings.json"
    save_settings({"theme": "light", "language": "zh", "puzzle_pieces": 999}, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["theme"] == "light"
    assert "puzzle_pieces" not in data
    assert "gun_render_page_size" not in data


# ── 隐藏配置（resources/config/app_config.json） ──────

def test_load_app_config_defaults(tmp_path):
    """隐藏配置缺失时回退默认值并自动创建默认文件（便于手改）。"""
    cfg = tmp_path / "config" / "app_config.json"
    values = load_app_config(cfg)
    assert values == DEFAULT_APP_CONFIG
    assert cfg.exists()
    assert json.loads(cfg.read_text(encoding="utf-8")) == DEFAULT_APP_CONFIG


def test_safe_int_guards():
    """#2 回归：隐藏配置整型归一化（非法/越界回退，不中断启动）。"""
    from deltaforcebox.core.settings import safe_int

    assert safe_int("abc", 8) == 8
    assert safe_int(None, 8) == 8
    assert safe_int(0, 8, 1, 120) == 1
    assert safe_int(999, 8, 1, 120) == 120
    assert safe_int("16", 8) == 16
    assert safe_int(48, 48, 4, 200) == 48


def test_load_app_config_corrupt_falls_back(tmp_path):
    """隐藏配置损坏（JSON 解析失败）时回退默认值，不中断。"""
    cfg = tmp_path / "app_config.json"
    cfg.write_text("{broken", encoding="utf-8")
    assert load_app_config(cfg) == DEFAULT_APP_CONFIG


def test_load_app_config_manual_edit_wins(tmp_path):
    """用户手改隐藏配置后程序读取生效，未改字段保持默认。"""
    cfg = tmp_path / "app_config.json"
    cfg.write_text(json.dumps({"puzzle_pieces": 200, "gun_render_page_size": 60}), encoding="utf-8")
    values = load_app_config(cfg)
    assert values["puzzle_pieces"] == 200
    assert values["gun_render_page_size"] == 60
    assert values["gun_sync_interval_days"] == DEFAULT_APP_CONFIG["gun_sync_interval_days"]


def test_load_app_config_ignores_unknown_keys(tmp_path):
    """未知字段忽略，不影响其余默认值。"""
    cfg = tmp_path / "app_config.json"
    cfg.write_text(json.dumps({"unknown_thing": 1}), encoding="utf-8")
    assert load_app_config(cfg) == DEFAULT_APP_CONFIG


def test_puzzle_pieces_roundtrip(tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"puzzle_pieces": 60}), encoding="utf-8")
    assert load_app_config(cfg)["puzzle_pieces"] == 60


def test_theme_change_preserves_app_config(qapp, tmp_path):
    """主题变更写回 data/settings.json 不影响隐藏配置文件的手改项。"""
    settings_path = tmp_path / "settings.json"
    config_path = tmp_path / "config" / "app_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({"puzzle_pieces": 60}), encoding="utf-8")
    save_settings({"theme": "light", "language": "zh"}, settings_path)
    _app, window = build_app(settings_path=settings_path, config_path=config_path)
    window._theme.set_theme("dark")
    assert json.loads(config_path.read_text(encoding="utf-8"))["puzzle_pieces"] == 60
    assert load_app_config(config_path)["puzzle_pieces"] == 60


def test_build_app_passes_puzzle_pieces(qapp, tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"puzzle_pieces": 60}), encoding="utf-8")
    _app, window = build_app(settings_path=tmp_path / "settings.json", config_path=config_path)
    assert window.pages["puzzle"]._target_pieces == 60


# ── 每日密码来源优先级 ────────────────────────────────

def test_password_source_order_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    save_settings(
        {"theme": "dark", "language": "zh", "password_source_order": ["shushu_fan", "tmini"]},
        path,
    )
    loaded = load_settings(path)
    assert loaded["password_source_order"] == ["shushu_fan", "tmini"]


def test_theme_change_preserves_password_source_order(qapp, tmp_path):
    path = tmp_path / "settings.json"
    save_settings(
        {"theme": "light", "language": "zh", "password_source_order": ["shushu_fan", "tmini"]},
        path,
    )
    _app, window = build_app(settings_path=path)
    window._theme.set_theme("dark")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["theme"] == "dark"
    assert data["password_source_order"] == ["shushu_fan", "tmini"]


def test_build_app_passes_password_sources(qapp, tmp_path):
    path = tmp_path / "settings.json"
    save_settings(
        {"theme": "dark", "language": "zh", "password_source_order": ["shushu_fan", "tmini"]},
        path,
    )
    _app, window = build_app(settings_path=path)
    assert window.pages["daily_password"]._order == ("shushu_fan", "tmini")


def test_settings_page_source_combo_repersists(qapp, tmp_path):
    path = tmp_path / "settings.json"
    save_settings({"theme": "dark", "language": "zh"}, path)
    _app, window = build_app(settings_path=path)
    page = window.pages["settings"]
    page.source_combo.setCurrentIndex(page.source_combo.findData("shushu_fan"))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["password_source_order"] == ["shushu_fan", "tmini"]


# ── 改枪码图片内存缓存上限（仅隐藏配置） ──────────────

def test_image_cache_limit_default_in_app_config():
    assert DEFAULT_APP_CONFIG["image_cache_limit_mb"] == 64


def test_build_app_sets_pixmap_cache_limit(qapp, tmp_path):
    from PySide6.QtGui import QPixmapCache

    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"image_cache_limit_mb": 128}), encoding="utf-8")
    _app, _window = build_app(settings_path=tmp_path / "settings.json", config_path=config_path)
    assert QPixmapCache.cacheLimit() == 128 * 1024  # MB -> KB


def test_build_app_pixmap_cache_zero_disables(qapp, tmp_path):
    from PySide6.QtGui import QPixmapCache

    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"image_cache_limit_mb": 0}), encoding="utf-8")
    _app, _window = build_app(settings_path=tmp_path / "settings.json", config_path=config_path)
    assert QPixmapCache.cacheLimit() == 0


# ── 改枪码每页卡片数（仅隐藏配置） ──────────────────

def test_build_app_passes_render_page_size(qapp, tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"gun_render_page_size": 25}), encoding="utf-8")
    _app, window = build_app(settings_path=tmp_path / "settings.json", config_path=config_path)
    assert window.pages["anchor"]._page_size == 25

def test_safe_int_rejects_bool():
    """bool 是 int 子类：True/False 不应被 int() 转成 1/0，直接回退默认。"""
    assert safe_int(True, 48, 4, 200) == 48
    assert safe_int(False, 48, 4, 200) == 48
    assert safe_int(0, 48, 4, 200) == 4  # 普通 0 仍走 clamp

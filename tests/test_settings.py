"""设置持久化测试：读写、缺失/损坏回退、应用装配按设置初始化并写回。"""

from __future__ import annotations

import json

from deltaforcebox.app import build_app
from deltaforcebox.core.settings import DEFAULT_SETTINGS, load_settings, save_settings


def test_load_missing_file_returns_defaults(tmp_path):
    assert load_settings(tmp_path / "nope.json") == DEFAULT_SETTINGS


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    save_settings({"theme": "light", "language": "zh"}, path)
    loaded = load_settings(path)
    assert loaded["theme"] == "light"
    assert loaded["language"] == "zh"
    assert loaded["puzzle_pieces"] == 48  # 未写入的字段补默认值


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


def test_puzzle_pieces_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    save_settings({"theme": "dark", "language": "zh", "puzzle_pieces": 60}, path)
    loaded = load_settings(path)
    assert loaded["puzzle_pieces"] == 60


def test_theme_change_preserves_puzzle_pieces(qapp, tmp_path):
    """主题变更写回时不覆盖用户手改的拼图碎片数配置。"""
    path = tmp_path / "settings.json"
    save_settings({"theme": "light", "language": "zh", "puzzle_pieces": 60}, path)
    _app, window = build_app(settings_path=path)
    window._theme.set_theme("dark")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["theme"] == "dark"
    assert data["puzzle_pieces"] == 60


def test_build_app_passes_puzzle_pieces(qapp, tmp_path):
    path = tmp_path / "settings.json"
    save_settings({"theme": "dark", "language": "zh", "puzzle_pieces": 60}, path)
    _app, window = build_app(settings_path=path)
    assert window.pages["puzzle"]._target_pieces == 60

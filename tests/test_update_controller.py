"""更新控制器测试：关闭时拉起安装器、pending 清理、模式判断。"""

from __future__ import annotations

from pathlib import Path

import pytest

from deltaforcebox.core import updater
from deltaforcebox.widgets import update_controller as uc_module
from deltaforcebox.widgets.update_controller import UpdateController


@pytest.fixture()
def _isolated(tmp_path: Path, monkeypatch) -> Path:
    """隔离 pending 与设置路径（monkeypatch 模块级路径）。"""
    pending = tmp_path / "pending_update.json"
    monkeypatch.setattr(updater, "PENDING_PATH", pending)
    monkeypatch.setattr(updater, "DATA_DIR", tmp_path)
    monkeypatch.setattr(
        uc_module,
        "load_settings",
        lambda path=None: {"update_mode": "auto"},
    )
    return pending


def test_close_auto_launches_installer(_isolated: Path) -> None:
    """auto 模式且有待安装更新：关闭时拉起安装器并清空 pending。"""
    installer = _isolated.parent / "pkg.exe"
    installer.write_bytes(b"x")
    updater.write_pending("Beta-4.3", installer)
    launched: list[str] = []

    controller = UpdateController(run_installer=lambda path: launched.append(path) or True)
    controller.on_app_close()

    assert launched == [str(installer)]
    assert updater.read_pending() is None


def test_close_auto_missing_pending(_isolated: Path) -> None:
    """无待安装更新：关闭时不拉起安装器。"""
    launched: list[str] = []
    controller = UpdateController(run_installer=lambda path: launched.append(path) or True)
    controller.on_app_close()
    assert launched == []


def test_close_auto_launch_failure_keeps_pending(_isolated: Path) -> None:
    """拉起失败：保留 pending（下次启动自愈重试）。"""
    installer = _isolated.parent / "pkg.exe"
    installer.write_bytes(b"x")
    updater.write_pending("Beta-4.3", installer)

    controller = UpdateController(run_installer=lambda path: False)
    controller.on_app_close()

    assert updater.read_pending() is not None


def test_close_auto_missing_installer_clears_pending(_isolated: Path) -> None:
    """安装包文件已不存在：清空 pending，不拉起。"""
    updater.write_pending("Beta-4.3", _isolated.parent / "gone.exe")
    launched: list[str] = []

    controller = UpdateController(run_installer=lambda path: launched.append(path) or True)
    controller.on_app_close()

    assert launched == []
    assert updater.read_pending() is None


def test_close_ignores_non_auto_mode(_isolated: Path, monkeypatch) -> None:
    """非 auto 模式（download_only）：关闭时不拉起安装器。"""
    monkeypatch.setattr(
        uc_module,
        "load_settings",
        lambda path=None: {"update_mode": "download_only"},
    )
    installer = _isolated.parent / "pkg.exe"
    installer.write_bytes(b"x")
    updater.write_pending("Beta-4.3", installer)
    launched: list[str] = []

    controller = UpdateController(run_installer=lambda path: launched.append(path) or True)
    controller.on_app_close()

    assert launched == []


def test_stale_pending_cleared_when_local_is_current(tmp_path: Path, monkeypatch) -> None:
    """本地已是最新时清理残留 pending（防止退出时重复重装）。"""
    pending = tmp_path / "pending_update.json"
    monkeypatch.setattr(updater, "PENDING_PATH", pending)
    monkeypatch.setattr(updater, "DATA_DIR", tmp_path)
    # pending 指向与本地相同版本（Beta-4.2 = 当前 __version__）
    installer = tmp_path / "pkg.exe"
    installer.write_bytes(b"x")
    updater.write_pending("Beta-4.2", installer)

    controller = UpdateController()
    # 直接调用内部清理逻辑（模拟 worker 发现无新版本）
    controller._clear_stale_pending()
    assert updater.read_pending() is None

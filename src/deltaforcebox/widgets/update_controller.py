"""自动更新控制器：启动时检查、下载、通知首页提示条、退出时拉起安装器。

- 设置模式四选一：auto（自动更新）/ download_only（下载但不自动安装）/
  notify（新版本提示）/ off（关闭）；
- 检查与下载在后台线程执行，通过 Qt 信号驱动 UI（首页右上角提示条），非弹窗；
- 下载完成写 pending_update.json；auto 模式下主程序退出时拉起安装器静默安装；
- 网络失败静默降级（直连→镜像轮询），最终失败仅提示条告知，不打断使用。

UI 约定：notice 信号的 action 取值为动作键（download / run / retry），
由主窗口映射为提示条按钮回调，避免依赖界面文案做判断。
"""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from ..core import updater
from ..core.settings import load_settings

# 动作键：提示条按钮对应的语义（主窗口按 key 挂回调）
ACTION_DOWNLOAD = "download"  # notify 模式：点击开始下载
ACTION_RUN = "run"  # download_only 模式：点击打开安装包位置
ACTION_RETRY = "retry"  # 下载失败：点击重试


class UpdateController(QObject):
    """更新流程控制器（由主窗口持有）。"""

    # notice(text, action_key|None)；text 为空表示静默（无更新/网络不可用）
    notice = Signal(str, object)
    progress = Signal(str, int, int)

    def __init__(
        self,
        parent: QObject | None = None,
        download_dir: Path | None = None,
        run_installer: Callable[[str], bool] | None = None,
    ) -> None:
        super().__init__(parent)
        self._download_dir = download_dir or updater.DATA_DIR / "updates"
        # run_installer：实际拉起安装器（注入便于测试）；默认用 updater 的静默命令
        self._run_installer = run_installer or self._default_run_installer
        self._busy = False
        self._thread: threading.Thread | None = None
        self._candidate = None  # 最近一次检查发现的新版（notify 模式点击下载用）

    # ---------- 对外入口 ----------

    def check_on_start(self) -> None:
        """启动时按设置模式执行检查/下载（后台线程，不阻塞启动）。"""
        if self._busy or (self._thread is not None and self._thread.is_alive()):
            return
        if self._mode() == "off":
            return
        # 延迟片刻再检查，避免与启动渲染抢资源
        QTimer.singleShot(1500, self._start_check)

    def download_candidate(self) -> None:
        """notify 模式点击「下载」：对候选版本开始下载。"""
        if self._busy or self._candidate is None:
            return
        self._start_download(self._candidate)

    def retry(self) -> None:
        """下载失败点击「重试」：重新检查并下载。"""
        if self._busy:
            return
        self._start_check()

    def open_installer_location(self) -> None:
        """download_only 模式点击「打开位置」：在资源管理器中定位安装包。"""
        pending = updater.read_pending()
        if not pending:
            return
        path = Path(pending["installer_path"])
        if not path.exists():
            updater.clear_pending()
            return
        try:
            import os

            os.startfile(str(path.parent))  # type: ignore[attr-defined]  # noqa: S606
        except OSError:
            pass

    # ---------- 内部 ----------

    @staticmethod
    def _mode() -> str:
        settings = load_settings()
        return str(settings.get("update_mode") or "auto")

    def _start_check(self) -> None:
        if self._busy:
            return
        self._busy = True
        self._thread = threading.Thread(
            target=self._worker, daemon=True, name="update-check"
        )
        self._thread.start()

    def _worker(self) -> None:
        """后台线程：检查 →（按模式）下载 → 通知 UI。"""
        try:
            release = updater.fetch_latest_release()
            if release is None:
                self.notice.emit("", None)  # 网络不可用/无 Release：静默
                return
            if not updater.is_newer(release.version):
                self._clear_stale_pending()
                self.notice.emit("", None)
                return
            self._candidate = release
            if release.asset is None:
                self.notice.emit(f"发现新版本 {release.tag}，但暂无可下载安装包", None)
                return

            mode = self._mode()
            if mode == "notify":
                self.notice.emit(f"发现新版本 {release.tag}", ACTION_DOWNLOAD)
                return
            if mode == "off":
                return
            # auto / download_only：直接下载
            self._start_download(release)
        except Exception:
            self.notice.emit("", None)
        finally:
            self._busy = False

    def _clear_stale_pending(self) -> None:
        """本地已是新版本：清理残留的待安装状态（防止退出时重复重装）。"""
        pending = updater.read_pending()
        if pending is None:
            return
        remote = updater.parse_version(pending.get("version") or "")
        if remote is None or not updater.is_newer(remote):
            updater.clear_pending()

    def _start_download(self, release) -> None:
        if self._busy:
            return
        self._busy = True
        self._thread = threading.Thread(
            target=self._download_worker, args=(release,), daemon=True,
            name="update-download",
        )
        self._thread.start()

    def _download_worker(self, release) -> None:
        """后台线程：下载 → 写 pending → 通知 UI。"""
        try:
            target = self._download_path(release.asset.name)

            def on_progress(done: int, total: int) -> None:
                self.progress.emit(f"正在下载更新：{release.tag}", done, total)

            if not self._download(release, target, on_progress):
                self.notice.emit(
                    f"更新下载失败：{release.tag}，点击重试", ACTION_RETRY
                )
                return
            updater.write_pending(release.tag, target)
            if self._mode() == "auto":
                self.notice.emit(
                    f"更新已就绪：{release.tag}，退出程序后将自动安装", None
                )
            else:
                self.notice.emit(
                    f"更新已就绪：{release.tag}，请退出程序后手动安装",
                    ACTION_RUN,
                )
        except Exception:
            self.notice.emit("", None)
        finally:
            self._busy = False

    def _download(self, release, target: Path, on_progress) -> bool:
        """下载资产到目标路径；已存在且大小一致则跳过。"""
        if target.exists() and target.stat().st_size == release.asset.size:
            return True
        downloaded = updater.download_asset(
            release.asset, self._download_dir, on_progress
        )
        if downloaded is None:
            return False
        return downloaded.stat().st_size == release.asset.size

    @staticmethod
    def _download_path(name: str) -> Path:
        return updater.DATA_DIR / "updates" / name

    @staticmethod
    def _default_run_installer(installer_path: str) -> bool:
        """静默拉起安装器（Inno Setup：/VERYSILENT 无人值守）。"""
        try:
            result = subprocess.Popen(
                [installer_path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                close_fds=True,
            )
            return result.pid > 0
        except OSError:
            return False

    # ---------- 关闭流程 ----------

    def on_app_close(self) -> None:
        """主程序退出前调用：auto 模式下若有待安装更新则拉起安装器。"""
        if self._mode() != "auto":
            return
        pending = updater.read_pending()
        if not pending:
            return
        installer_path = pending["installer_path"]
        if not Path(installer_path).exists():
            updater.clear_pending()
            return
        if self._run_installer(installer_path):
            # 拉起成功即清 pending：若安装失败，下次启动检查会重新发现新版本并自愈
            updater.clear_pending()
        else:
            # 拉起失败：保留 pending，下次启动仍会提示/重试
            self.notice.emit("更新未能启动，请稍后手动运行安装包", None)

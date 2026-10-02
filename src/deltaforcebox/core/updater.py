"""自动更新核心逻辑：版本解析、Release 检查、安装包下载与待安装状态。

- 版本比较：Beta-X.Y（阶段 0，预发布）< v-X.Y / vX.Y.Z（阶段 1，正式版），
  统一解析为整数元组比较，正式版前缀切换无需迁移；
- 检查：拉取 GitHub Releases 列表，按版本元组取最大者（不依赖发布时间 / latest 语义），
  并匹配 DeltaForceBox-Setup-*.exe 资产；
- 网络：默认直连 github.com，失败静默降级为内置镜像列表（整 URL 代理形态）轮询；
- 下载：HTTP Range 断点续传（206 续写 / 200 从头），完成后按 Content-Length 校验；
- 待安装：下载完成写 data/pending_update.json，主程序退出时据此拉起安装器。

本模块为纯逻辑（无 Qt 依赖），可独立测试。
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .. import __version__
from .paths import DATA_DIR
from .settings import load_app_config

# GitHub 仓库（公开后无需认证）
REPO = "PastSheep/DeltaForceBox"
API_RELEASES_URL = f"https://api.github.com/repos/{REPO}/releases"
# 资产名约定（英文命名，与安装器产物一致）
ASSET_PREFIX = "DeltaForceBox-Setup-"
ASSET_SUFFIX = ".exe"

PENDING_PATH = DATA_DIR / "pending_update.json"

# 默认镜像列表：整 URL 代理形态（https://<mirror>/https://<原始完整URL>）
DEFAULT_MIRRORS: list[str] = [
    "https://ghproxy.net/",
    "https://mirror.ghproxy.com/",
]


@dataclass
class ReleaseAsset:
    """Release 资产（安装包）。"""

    name: str
    url: str  # browser_download_url
    size: int


@dataclass
class ReleaseInfo:
    """版本检查结果。"""

    tag: str
    version: tuple[int, ...]
    asset: ReleaseAsset | None


def parse_version(value: str) -> tuple[int, ...] | None:
    """解析版本字符串为可比较元组。

    - Beta-4.2 / Beta-4.2.1 → (0, 4, 2[, 1])（阶段 0 = 预发布）
    - v-1.0 / v1.0 / v1.0.1 / 1.0 → (1, 1, 0[, 1])（阶段 1 = 正式版）
    - 无法识别（含非版本 tag）→ None，由调用方跳过
    """
    text = value.strip()
    match = re.fullmatch(r"Beta-(\d+)\.(\d+)(?:\.(\d+))?", text)
    if match:
        return (0, *(int(part) for part in match.groups() if part is not None))
    match = re.fullmatch(r"v-?(\d+)\.(\d+)(?:\.(\d+))?", text)
    if match:
        return (1, *(int(part) for part in match.groups() if part is not None))
    match = re.fullmatch(r"(\d+)\.(\d+)(?:\.(\d+))?", text)
    if match:
        return (1, *(int(part) for part in match.groups() if part is not None))
    return None


def is_newer(remote: tuple[int, ...]) -> bool:
    """远端版本是否比本地版本新（本地 __version__ 解析失败时视为无更新）。"""
    local = parse_version(__version__)
    if local is None:
        return False
    return remote > local


def _mirror_urls(original: str) -> list[str]:
    """构造候选下载/请求 URL 列表：直连优先，镜像整 URL 代理在后。"""
    config = load_app_config()
    mirrors = [m for m in (config.get("update_mirrors") or []) if m]
    urls = [original]
    for mirror in mirrors:
        prefix = mirror.rstrip("/") + "/"
        urls.append(prefix + original)
    return urls


def _request_json(urls: list[str], timeout: int) -> object | None:
    """按序尝试多个 URL 拉取 JSON；全部失败返回 None。"""
    for url in urls:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (OSError, ValueError, urllib.error.URLError):
            continue
    return None


def fetch_latest_release() -> ReleaseInfo | None:
    """拉取 Release 列表，返回版本元组最大的一条（含安装包资产）。

    - 不依赖 GitHub 的 latest 语义（按发布时间），而是语义版本比较取最大；
    - 无可用 Release / 网络全失败 / 均不可解析 → None。
    """
    config = load_app_config()
    timeout = int(config.get("update_timeout_s") or 8)
    data = _request_json(_mirror_urls(API_RELEASES_URL), timeout)
    if not isinstance(data, list):
        return None

    best: ReleaseInfo | None = None
    for item in data:
        if not isinstance(item, dict):
            continue
        version = parse_version(str(item.get("tag_name") or ""))
        if version is None:
            continue
        asset: ReleaseAsset | None = None
        for a in item.get("assets") or []:
            if not isinstance(a, dict):
                continue
            name = str(a.get("name") or "")
            if name.startswith(ASSET_PREFIX) and name.endswith(ASSET_SUFFIX):
                asset = ReleaseAsset(
                    name=name,
                    url=str(a.get("browser_download_url") or ""),
                    size=int(a.get("size") or 0),
                )
                break
        candidate = ReleaseInfo(
            tag=str(item.get("tag_name") or ""),
            version=version,
            asset=asset,
        )
        if best is None or version > best.version:
            best = candidate
    return best


def _open_download(url: str, timeout: int, offset: int) -> urllib.response.addinfourl:
    """发起下载请求（带 Range 断点）；非 2xx 抛 OSError。"""
    request = urllib.request.Request(url)
    if offset:
        request.add_header("Range", f"bytes={offset}-")
    request.add_header("User-Agent", f"DeltaForceBox/{__version__}")
    resp = urllib.request.urlopen(request, timeout=timeout)
    return resp


def download_asset(
    asset: ReleaseAsset,
    dest_dir: Path,
    progress: object | None = None,
) -> Path | None:
    """下载安装包到 dest_dir（断点续传 + 镜像轮询）。

    - 断点：已存在 .part 临时文件则按其大小带 Range 续传；响应 206 续写，
      响应 200 视为镜像不支持 Range，从头重下；
    - 完成后按 Content-Length 校验，通过则更名为正式文件名并返回路径；
    - 全程失败返回 None（不抛异常，由调用方决定提示策略）。
    progress：可选回调 progress(downloaded, total)，总大小未知时 total=0。
    """
    config = load_app_config()
    timeout = int(config.get("update_timeout_s") or 8)
    dest_dir.mkdir(parents=True, exist_ok=True)
    part_path = dest_dir / (asset.name + ".part")
    final_path = dest_dir / asset.name

    offset = part_path.stat().st_size if part_path.exists() else 0
    urls = _mirror_urls(asset.url) if asset.url else []

    for url in urls:
        if offset:
            try:
                resp = _open_download(url, timeout, offset)
            except OSError:
                continue
        else:
            try:
                request = urllib.request.Request(
                    url, headers={"User-Agent": f"DeltaForceBox/{__version__}"}
                )
                resp = urllib.request.urlopen(request, timeout=timeout)
            except OSError:
                continue
        if resp.status == 200:
            # 镜像不支持 Range：从头下载
            if offset:
                offset = 0
                try:
                    part_path.unlink(missing_ok=True)
                except OSError:
                    pass
        elif resp.status != 206:
            resp.close()
            continue
        total = int(resp.headers.get("Content-Length") or 0) + offset
        try:
            with part_path.open("ab" if offset else "wb") as fh:
                while True:
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
                    offset += len(chunk)
                    if progress is not None:
                        progress(offset, total)
        except OSError:
            # 下载中途失败：保留 .part，下次从断点继续
            resp.close()
            return None
        finally:
            resp.close()
        break
    else:
        return None

    if offset != asset.size or asset.size <= 0:
        return None
    try:
        part_path.replace(final_path)
    except OSError:
        return None
    return final_path


def write_pending(version: str, installer_path: Path) -> None:
    """记录待安装状态（主程序退出时据此拉起安装器）。"""
    PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PENDING_PATH.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {"version": version, "installer_path": str(installer_path)},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    tmp.replace(PENDING_PATH)


def read_pending() -> dict[str, str] | None:
    """读取待安装状态；缺失/损坏返回 None。"""
    try:
        with PENDING_PATH.open(encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and data.get("installer_path"):
            return {"version": str(data.get("version") or ""),
                    "installer_path": str(data["installer_path"])}
    except (OSError, ValueError):
        pass
    return None


def clear_pending() -> None:
    """清除待安装状态（安装完成/放弃时调用）。"""
    try:
        PENDING_PATH.unlink()
    except OSError:
        pass

"""自动更新核心逻辑测试：版本解析、Release 检查、断点续传、pending 状态。"""

from __future__ import annotationsimport threadingfrom http.server import BaseHTTPRequestHandler, ThreadingHTTPServerfrom pathlib import Pathimport pytestfrom deltaforcebox.core import updater# ── 版本解析与比较 ─────────────────────────────────────────

@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Beta-4.2", (0, 4, 2)),
        ("Beta-4.2.1", (0, 4, 2, 1)),
        ("v-1.0", (1, 1, 0)),
        ("v1.0", (1, 1, 0)),
        ("v1.0.1", (1, 1, 0, 1)),
        ("1.0", (1, 1, 0)),
        ("", None),
        ("v1", None),
        ("1.0-beta", None),
        ("Beta-1", None),
    ],
)
def test_parse_version(text: str, expected: object) -> None:
    assert updater.parse_version(text) == expected


def test_is_newer_than_local() -> None:
    """与本地 __version__（Beta-5.2）比较：更高/同版本/正式版判定。"""
    from deltaforcebox import __version__ as local_version

    assert local_version == "Beta-5.2"
    assert updater.is_newer((0, 5, 3))
    assert not updater.is_newer((0, 5, 2))
    assert not updater.is_newer((0, 4, 9))
    assert updater.is_newer((1, 1, 0))  # 正式版高于所有 Beta


def test_beta_less_than_formal() -> None:
    """Beta-4.2 < v-1.0（正式版阶段高于所有预发布）。"""
    assert updater.parse_version("Beta-4.2") < updater.parse_version("v-1.0")
    assert updater.parse_version("v-1.0") < updater.parse_version("v-1.0.1")


# ── Release 检查（mock 网络） ─────────────────────────────

def _fake_releases(*tags: str) -> list[dict]:
    return [
        {
            "tag_name": tag,
            "assets": [
                {
                    "name": f"DeltaForceBox-Setup-{tag}.exe",
                    "browser_download_url": f"https://example.com/{tag}.exe",
                    "size": 100,
                }
            ],
        }
        for tag in tags
    ]
def _asset(tag: str) -> dict:
    return {"name": f"DeltaForceBox-Setup-{tag}.exe",
            "browser_download_url": f"https://example.com/{tag}.exe",
            "size": 1}


def test_fetch_latest_takes_highest_version(monkeypatch) -> None:
    """按版本元组取最大（Beta 与正式混排、乱序 tag）。"""
    monkeypatch.setattr(
        updater,
        "_request_json",
        lambda urls, timeout: _fake_releases("Beta-4.3", "v-1.0", "Beta-4.2"),
    )
    release = updater.fetch_latest_release()
    assert release is not None
    assert release.tag == "v-1.0"
    assert release.version == (1, 1, 0)
    assert release.asset is not None
    assert release.asset.name == "DeltaForceBox-Setup-v-1.0.exe"


def test_fetch_latest_skips_unparseable_and_no_asset(monkeypatch) -> None:
    data = [
        {"tag_name": "not-a-version", "assets": []},
        {"tag_name": "Beta-4.4", "assets": []},  # 无安装包资产
    ]
    monkeypatch.setattr(updater, "_request_json", lambda urls, timeout: data)
    release = updater.fetch_latest_release()
    assert release is not None
    assert release.asset is None


def test_fetch_latest_all_network_fail(monkeypatch) -> None:
    monkeypatch.setattr(updater, "_request_json", lambda urls, timeout: None)
    assert updater.fetch_latest_release() is None


def test_fetch_latest_skips_draft_and_prerelease(monkeypatch) -> None:
    """#13 回归：草稿/预发布 release 不被选中（tag 可能高于正式发布）。"""
    data = [
        {"tag_name": "Beta-9.9", "draft": True, "prerelease": False,
         "assets": [_asset("Beta-9.9")]},
        {"tag_name": "Beta-5.2", "prerelease": True, "assets": [_asset("Beta-5.2")]},
        {"tag_name": "Beta-5.1", "assets": [_asset("Beta-5.1")]},
    ]
    monkeypatch.setattr(updater, "_request_json", lambda urls, timeout: data)
    release = updater.fetch_latest_release()
    assert release is not None
    assert release.tag == "Beta-5.1"


def test_fetch_latest_tolerates_bad_asset_size(monkeypatch) -> None:
    """#2/#13 回归：资产 size 非数字不崩，回退 0。"""
    data = [
        {
            "tag_name": "Beta-5.3",
            "assets": [{"name": "DeltaForceBox-Setup-Beta-5.3.exe",
                        "browser_download_url": "https://example.com/x.exe",
                        "size": "oops"}],
        }
    ]
    monkeypatch.setattr(updater, "_request_json", lambda urls, timeout: data)
    release = updater.fetch_latest_release()
    assert release is not None
    assert release.asset is not None
    assert release.asset.size == 0


# ── 断点续传下载（本地 Range 服务器） ──────────────────────

class _RangeHandler(BaseHTTPRequestHandler):
    """最小 HTTP 服务器：支持 Range（206），供断点续传测试。"""

    def do_GET(self) -> None:  # noqa: N802 - HTTP 动词
        body = b"x" * 100
        start = 0
        if self.headers.get("Range"):
            start = int(self.headers["Range"].split("=")[1].split("-")[0])
        if start:
            self.send_response(206)
            self.send_header("Content-Length", str(len(body) - start))
            self.send_header("Content-Range", f"bytes {start}-99/100")
        else:
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body[start:])


@pytest.fixture()
def range_server() -> object:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RangeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_download_resume_from_part(range_server: str, tmp_path: Path) -> None:
    """已存在 .part 时带 Range 续传（206），完成后替换为正式名。"""
    asset = updater.ReleaseAsset(
        name="pkg.exe", url=f"{range_server}/pkg.exe", size=100
    )
    part = tmp_path / "pkg.exe.part"
    part.write_bytes(b"x" * 30)  # 已下载 30 字节
    result = updater.download_asset(asset, tmp_path)
    assert result == tmp_path / "pkg.exe"
    assert result.exists()
    assert result.stat().st_size == 100
    assert not part.exists()


def test_download_from_scratch(range_server: str, tmp_path: Path) -> None:
    asset = updater.ReleaseAsset(
        name="pkg.exe", url=f"{range_server}/pkg.exe", size=100
    )
    result = updater.download_asset(asset, tmp_path)
    assert result is not None
    assert result.stat().st_size == 100


def test_download_size_mismatch_fails(range_server: str, tmp_path: Path) -> None:
    """大小不符（服务器返回 100 但声明 200）视为失败，不产生正式文件。"""
    asset = updater.ReleaseAsset(
        name="pkg.exe", url=f"{range_server}/pkg.exe", size=200
    )
    assert updater.download_asset(asset, tmp_path) is None
    assert not (tmp_path / "pkg.exe").exists()


# ── pending 状态 ──────────────────────────────────────────

def test_pending_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(updater, "PENDING_PATH", tmp_path / "pending_update.json")
    assert updater.read_pending() is None
    updater.write_pending("Beta-4.3", tmp_path / "pkg.exe")
    pending = updater.read_pending()
    assert pending == {
        "version": "Beta-4.3",
        "installer_path": str(tmp_path / "pkg.exe"),
    }
    updater.clear_pending()
    assert updater.read_pending() is None


def test_pending_corrupt_returns_none(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "pending_update.json"
    path.write_text("{bad json", encoding="utf-8")
    monkeypatch.setattr(updater, "PENDING_PATH", path)
    assert updater.read_pending() is None

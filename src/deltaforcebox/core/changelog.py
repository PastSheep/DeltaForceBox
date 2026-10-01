"""版本日志解析：读取 docs/版本日志.md 的最新版本节，供首页展示。

约定：文档按时间倒序排列，顶部第一个 `## ` 即最新版本；
该节内 `### ` 为功能分组标题，`- ` 为功能条目。
"""

from __future__ import annotations

from pathlib import Path

from .paths import PROJECT_ROOT

CHANGELOG_PATH = PROJECT_ROOT / "docs" / "版本日志.md"


def load_latest_update(doc_path: Path | None = None) -> dict | None:
    """返回最新版本节的结构化内容；文件缺失/格式不符时返回 None。

    返回结构：{"version": "Beta-1.1", "intro": "…", "sections": [{"title": "…", "items": [...]}]}
    """
    path = doc_path or CHANGELOG_PATH
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    lines = text.splitlines()
    start = next(
        (i for i, ln in enumerate(lines) if ln.startswith("## ")), None
    )
    if start is None:
        return None

    # 版本号取标题括号前的部分（"Beta-1.1（2026-10-01）" → "Beta-1.1"）
    version = lines[start][3:].split("（", 1)[0].strip()

    intro = ""
    sections: list[dict] = []
    current: dict | None = None
    for ln in lines[start + 1 :]:
        stripped = ln.strip()
        if not stripped:
            continue
        if stripped.startswith("## ") or stripped.startswith("---"):
            break
        if stripped.startswith("### "):
            current = {"title": stripped[4:].strip(), "items": []}
            sections.append(current)
        elif stripped.startswith("- "):
            if current is not None:
                current["items"].append(stripped[2:].strip())
        elif stripped.startswith("**") and current is None and not intro:
            # 版本简介行，如 "**当前版本**：首次发行版，…"
            intro = stripped.replace("**", "").strip()

    if not sections and not intro:
        return None
    return {"version": version, "intro": intro, "sections": sections}

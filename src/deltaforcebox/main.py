"""三角洲行动工具箱（Delta Force Box）程序入口。

用法：
    python -m deltaforcebox.main
"""

from __future__ import annotations

import sys

from .app import build_app


def main() -> int:
    app, window = build_app(sys.argv)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

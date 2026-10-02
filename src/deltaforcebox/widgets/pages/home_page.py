"""首页：欢迎信息、版本号、最近更新与作者信息。"""

from __future__ import annotations

import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ... import __version__
from ...core.changelog import load_latest_update
from ...core.i18n import I18nManager
from ..notice_bar import NoticeBar

# 作者署名与联系邮箱（邮箱可点击写信）
AUTHOR_NAME = "PastSheep"
AUTHOR_EMAIL = "wzylscszyzh@163.com"
# 链接色：取明暗主题都可读的中性蓝
LINK_COLOR = "#4d8ff7"


class HomePage(QWidget):
    def __init__(self, i18n: I18nManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("pageRoot")
        self._i18n = i18n

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)

        # 顶部行：欢迎标题（左）+ 右上角提示条（右）
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)
        self.notice_bar = NoticeBar()
        self.notice_bar.hide()

        self.welcome_label = QLabel()
        self.welcome_label.setAlignment(Qt.AlignLeft)
        font = self.welcome_label.font()
        font.setPointSize(20)
        font.setBold(True)
        self.welcome_label.setFont(font)

        self.desc_label = QLabel()
        self.desc_label.setWordWrap(True)
        self.desc_label.setObjectName("hint")

        self.version_label = QLabel()
        self.version_label.setObjectName("hint")

        self.author_label = QLabel()
        self.author_label.setObjectName("hint")

        self.email_label = QLabel()
        self.email_label.setObjectName("hint")
        self.email_label.setOpenExternalLinks(True)
        self.email_label.setTextFormat(Qt.TextFormat.RichText)
        self.email_label.setTextInteractionFlags(Qt.TextBrowserInteraction)

        self.update_title_label = QLabel()
        self.update_title_label.setObjectName("pageTitle")

        self.update_body_label = QLabel()
        self.update_body_label.setObjectName("hint")
        self.update_body_label.setWordWrap(True)
        self.update_body_label.setTextFormat(Qt.TextFormat.RichText)

        top_row.addWidget(self.welcome_label, 1)
        top_row.addWidget(self.notice_bar, 0, Qt.AlignTop)
        layout.addLayout(top_row)
        layout.addSpacing(8)
        layout.addWidget(self.desc_label)
        layout.addWidget(self.version_label)
        layout.addSpacing(4)
        layout.addWidget(self.author_label)
        layout.addWidget(self.email_label)
        layout.addSpacing(12)
        layout.addWidget(self.update_title_label)
        layout.addWidget(self.update_body_label)
        layout.addStretch(1)

    def retranslate(self) -> None:
        self.welcome_label.setText(self._i18n.t("home.welcome"))
        self.desc_label.setText(self._i18n.t("home.description"))
        self.version_label.setText(f"{self._i18n.t('home.version')}：{__version__}")
        self.author_label.setText(f"{self._i18n.t('home.author')}：{AUTHOR_NAME}")
        self.email_label.setText(
            f'{self._i18n.t("home.email")}：'
            f'<a href="mailto:{AUTHOR_EMAIL}" '
            f'style="color:{LINK_COLOR};text-decoration:none;">{AUTHOR_EMAIL}</a>'
        )
        self._refresh_update_section()

    def _refresh_update_section(self) -> None:
        """从版本日志读取最新版本节并渲染；缺失时隐藏该区域。"""
        update = load_latest_update()
        if update is None:
            self.update_title_label.hide()
            self.update_body_label.hide()
            return
        self.update_title_label.setText(
            f"{self._i18n.t('home.latest_update')}（{update['version']}）"
        )
        parts: list[str] = []
        if update.get("intro"):
            parts.append(html.escape(update["intro"]))
        for section in update.get("sections", []):
            title = html.escape(section["title"])
            parts.append(f"<b>{title}</b>")
            for item in section.get("items", []):
                parts.append(f"· {html.escape(item)}")
        self.update_body_label.setText("<br>".join(parts))
        self.update_title_label.show()
        self.update_body_label.show()

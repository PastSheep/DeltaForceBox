"""首页：欢迎信息、版本号与作者信息。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ... import __version__
from ...core.i18n import I18nManager

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
        self.email_label.setTextFormat(Qt.RichText)
        self.email_label.setTextInteractionFlags(Qt.TextBrowserInteraction)

        layout.addWidget(self.welcome_label)
        layout.addSpacing(8)
        layout.addWidget(self.desc_label)
        layout.addWidget(self.version_label)
        layout.addSpacing(4)
        layout.addWidget(self.author_label)
        layout.addWidget(self.email_label)
        layout.addStretch(1)

    def retranslate(self) -> None:
        self.welcome_label.setText(self._i18n.t("home.welcome"))
        self.desc_label.setText(self._i18n.t("home.description"))
        self.version_label.setText(f"{self._i18n.t('home.version')} {__version__}")
        self.author_label.setText(f"{self._i18n.t('home.author')}：{AUTHOR_NAME}")
        self.email_label.setText(
            f'{self._i18n.t("home.email")}：'
            f'<a href="mailto:{AUTHOR_EMAIL}" '
            f'style="color:{LINK_COLOR};text-decoration:none;">{AUTHOR_EMAIL}</a>'
        )

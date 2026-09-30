"""首页：欢迎信息与版本号。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ... import __version__
from ...core.i18n import I18nManager


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

        layout.addWidget(self.welcome_label)
        layout.addSpacing(8)
        layout.addWidget(self.desc_label)
        layout.addWidget(self.version_label)
        layout.addStretch(1)

    def retranslate(self) -> None:
        self.welcome_label.setText(self._i18n.t("home.welcome"))
        self.desc_label.setText(self._i18n.t("home.description"))
        self.version_label.setText(f"{self._i18n.t('home.version')} {__version__}")

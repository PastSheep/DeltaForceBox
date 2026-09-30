"""设置页：语言切换（当前仅中文）与主题切换。"""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QWidget

from ...core.i18n import I18nManager
from ...core.theme import ThemeManager

# 语言下拉选项；英文支持后续加入时在此追加 ("en", "English")
LANGUAGE_ITEMS = (("zh", "中文"),)


class SettingsPage(QWidget):
    def __init__(
        self,
        i18n: I18nManager,
        theme: ThemeManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("pageRoot")
        self._i18n = i18n
        self._theme = theme

        layout = QFormLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        self.title_label = QLabel()
        font = self.title_label.font()
        font.setPointSize(15)
        font.setBold(True)
        self.title_label.setFont(font)
        layout.addRow(self.title_label)

        self.lang_label = QLabel()
        self.lang_combo = QComboBox()
        for code, name in LANGUAGE_ITEMS:
            self.lang_combo.addItem(name, code)
        self.lang_combo.setCurrentIndex(max(0, self.lang_combo.findData(i18n.language())))

        self.theme_label = QLabel()
        self.theme_combo = QComboBox()

        layout.addRow(self.lang_label, self.lang_combo)
        layout.addRow(self.theme_label, self.theme_combo)
        layout.addRow(QLabel())

        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        self._refresh_theme_combo()

    def _on_language_changed(self, index: int) -> None:
        code = self.lang_combo.itemData(index)
        if code:
            self._i18n.set_language(code)

    def _on_theme_changed(self, index: int) -> None:
        name = self.theme_combo.itemData(index)
        if name:
            self._theme.set_theme(name)

    def _refresh_theme_combo(self) -> None:
        self.theme_combo.blockSignals(True)
        self.theme_combo.clear()
        for name in ("light", "dark"):
            self.theme_combo.addItem(self._i18n.t(f"settings.theme.{name}"), name)
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(self._theme.theme())))
        self.theme_combo.blockSignals(False)

    def retranslate(self) -> None:
        self.title_label.setText(self._i18n.t("settings.title"))
        self.lang_label.setText(self._i18n.t("settings.language"))
        self.theme_label.setText(self._i18n.t("settings.theme"))
        self._refresh_theme_combo()

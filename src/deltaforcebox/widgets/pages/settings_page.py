"""设置页：语言切换（当前仅中文）、主题切换与每日密码来源优先级。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QWidget

from ...core.daily_password import normalize_source_order
from ...core.i18n import I18nManager
from ...core.settings import load_settings, save_settings
from ...core.theme import ThemeManager

# 语言下拉选项；英文支持后续加入时在此追加 ("en", "English")
LANGUAGE_ITEMS = (("zh", "中文"),)

# 每日密码数据源选项（顺序即 fallback 优先级，靠前者优先）
PASSWORD_SOURCE_ITEMS = ("tmini", "shushu_fan")

# 自动更新模式选项（启动时检查；auto=自动更新，download_only=下载但不自动安装，
# notify=新版本提示，off=关闭）
UPDATE_MODE_ITEMS = ("auto", "download_only", "notify", "off")


class SettingsPage(QWidget):
    # 首选来源变更后发出（携带重排后的完整顺序），供主窗口实时更新每日密码页
    password_source_changed = Signal(object)

    def __init__(
        self,
        i18n: I18nManager,
        theme: ThemeManager,
        settings_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("pageRoot")
        self._i18n = i18n
        self._theme = theme
        self._settings_path = settings_path

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

        # 每日密码来源：优先尝试首选源，失败自动回退其余源
        self.source_label = QLabel()
        self.source_combo = QComboBox()
        for name in PASSWORD_SOURCE_ITEMS:
            self.source_combo.addItem(i18n.t(f"settings.password_source.{name}"), name)
        order = normalize_source_order(load_settings(settings_path).get("password_source_order"))
        self.source_combo.setCurrentIndex(max(0, self.source_combo.findData(order[0])))

        # 自动更新模式
        self.update_label = QLabel()
        self.update_combo = QComboBox()
        for name in UPDATE_MODE_ITEMS:
            self.update_combo.addItem(
                self._i18n.t(f"settings.update_mode.{name}"), name
            )
        mode = str(load_settings(settings_path).get("update_mode") or "auto")
        self.update_combo.setCurrentIndex(max(0, self.update_combo.findData(mode)))

        layout.addRow(self.lang_label, self.lang_combo)
        layout.addRow(self.theme_label, self.theme_combo)
        layout.addRow(self.source_label, self.source_combo)
        layout.addRow(self.update_label, self.update_combo)
        layout.addRow(QLabel())

        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        self.update_combo.currentIndexChanged.connect(self._on_update_mode_changed)
        self._refresh_theme_combo()

    def _on_language_changed(self, index: int) -> None:
        code = self.lang_combo.itemData(index)
        if code:
            self._i18n.set_language(code)

    def _on_theme_changed(self, index: int) -> None:
        name = self.theme_combo.itemData(index)
        if name:
            self._theme.set_theme(name)

    def _on_update_mode_changed(self, index: int) -> None:
        """自动更新模式变更：立即持久化（下次启动生效）。"""
        name = self.update_combo.itemData(index)
        if not name:
            return
        settings = load_settings(self._settings_path)
        settings["update_mode"] = name
        save_settings(settings, self._settings_path)

    def _on_source_changed(self, index: int) -> None:
        """首选来源变更：重排优先级顺序（首选置顶，其余保序）并持久化。"""
        name = self.source_combo.itemData(index)
        if not name:
            return
        settings = load_settings(self._settings_path)
        order = list(normalize_source_order(settings.get("password_source_order")))
        order = [name] + [s for s in order if s != name]
        settings["password_source_order"] = order
        save_settings(settings, self._settings_path)
        # 通知主窗口实时更新每日密码页来源顺序（无需重启）
        self.password_source_changed.emit(tuple(order))

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
        self.source_label.setText(self._i18n.t("settings.password_source"))
        self.update_label.setText(self._i18n.t("settings.update_mode"))
        for i in range(self.update_combo.count()):
            name = self.update_combo.itemData(i)
            self.update_combo.setItemText(i, self._i18n.t(f"settings.update_mode.{name}"))
        for i in range(self.source_combo.count()):
            name = self.source_combo.itemData(i)
            self.source_combo.setItemText(i, self._i18n.t(f"settings.password_source.{name}"))
        self._refresh_theme_combo()

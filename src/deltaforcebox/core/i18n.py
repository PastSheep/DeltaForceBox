"""轻量国际化：JSON 翻译字典 + 切换信号（当前仅支持中文）。

翻译文件位于 resources/i18n/{lang}.json，结构为 {key: text}。
切换语言时发出 changed 信号，各界面据此刷新文本。

当前版本只支持中文（SUPPORTED_LANGUAGES 仅 "zh"），设置页语言行
仅提供“中文”选项；后续恢复英文支持时：新增 resources/i18n/en.json、
在 SUPPORTED_LANGUAGES 中追加 "en"、并在设置页语言下拉中增加英文项。
"""

from __future__ import annotations

import json

from PySide6.QtCore import QObject, Signal

from .paths import I18N_DIR

# 仅支持中文；英文支持待后续扩展
SUPPORTED_LANGUAGES = ("zh",)
DEFAULT_LANGUAGE = "zh"


class I18nManager(QObject):
    """翻译管理与语言切换。"""

    changed = Signal(str)

    def __init__(self, language: str = DEFAULT_LANGUAGE, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._language = language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
        self._strings: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        path = I18N_DIR / f"{self._language}.json"
        with path.open(encoding="utf-8") as fh:
            self._strings = json.load(fh)

    def language(self) -> str:
        return self._language

    def t(self, key: str, *args) -> str:
        """取翻译文本；支持 %1、%2… 占位符替换。"""
        text = self._strings.get(key, key)
        if args:
            for i, arg in enumerate(args, start=1):
                text = text.replace(f"%{i}", str(arg))
        return text

    def set_language(self, language: str) -> None:
        if language == self._language or language not in SUPPORTED_LANGUAGES:
            return
        self._language = language
        self._load()
        self.changed.emit(language)

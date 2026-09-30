"""Windows 标题栏与主题联动。

原生标题栏颜色默认跟随 Windows 系统深浅色设置；通过
DwmSetWindowAttribute(DWMWA_USE_IMMERSIVE_DARK_MODE) 可让标题栏
跟随应用内主题（暗色主题→深色标题栏，浅色主题→浅色标题栏）。
"""

from __future__ import annotations

import ctypes
import sys

from PySide6.QtWidgets import QWidget

# DWMWA_USE_IMMERSIVE_DARK_MODE：Win10 20H1(19041)+ 使用 20，
# 更早版本使用 19（BEFORE_20H1）。
_DARK_MODE_ATTRS = (20, 19)


def set_title_bar_dark(hwnd: int, dark: bool) -> bool:
    """为指定原生窗口设置/取消沉浸式暗色标题栏，失败返回 False。"""
    if sys.platform != "win32":
        return False
    try:
        value = ctypes.c_int(1 if dark else 0)
        for attr in _DARK_MODE_ATTRS:
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd),
                attr,
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
            if result == 0:
                return True
    except (OSError, AttributeError):
        pass
    return False


def apply_title_bar_theme(widget: QWidget) -> bool:
    """按当前应用主题设置窗口标题栏深浅色（窗口须已创建原生句柄）。"""
    if widget.winId() == 0:
        return False
    from .theme import current_theme

    return set_title_bar_dark(int(widget.winId()), current_theme() == "dark")

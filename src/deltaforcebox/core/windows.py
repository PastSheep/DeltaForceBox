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

# SetWindowPos 标志：不移动/不缩放/不改 Z 序/不激活 + 强制重绘窗口框架
_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOZORDER = 0x0004
_SWP_NOACTIVATE = 0x0010
_SWP_FRAMECHANGED = 0x0020

_WM_NCACTIVATE = 0x0086


def _refresh_title_bar(hwnd: int) -> None:
    """强制 DWM 以最新属性立即重绘标题栏（不改变真实激活状态）。

    仅设置 DWMWA_USE_IMMERSIVE_DARK_MODE 不会触发标题栏重绘，
    表现为切主题后标题栏不变色，直到窗口失焦/缩放才刷新。
    通过 WM_NCACTIVATE 先反向后按真实激活状态重绘一次标题栏即可立即生效：
    激活窗口走 0→1，非激活窗口走 1→0，最终视觉状态与实际焦点一致。
    """
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    foreground = user32.GetForegroundWindow()
    is_active = foreground is not None and int(foreground) == hwnd
    if is_active:
        user32.SendMessageW(ctypes.c_void_p(hwnd), _WM_NCACTIVATE, 0, 0)
        user32.SendMessageW(ctypes.c_void_p(hwnd), _WM_NCACTIVATE, 1, 0)
    else:
        user32.SendMessageW(ctypes.c_void_p(hwnd), _WM_NCACTIVATE, 1, 0)
        user32.SendMessageW(ctypes.c_void_p(hwnd), _WM_NCACTIVATE, 0, 0)


def set_title_bar_dark(hwnd: int, dark: bool) -> bool:
    """为指定原生窗口设置/取消沉浸式暗色标题栏，失败返回 False。

    设置 DWM 属性后同时强制刷新窗口框架（SWP_FRAMECHANGED）与
    WM_NCACTIVATE 重绘，确保标题栏立即跟随主题切换。
    """
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
                ctypes.windll.user32.SetWindowPos(
                    ctypes.c_void_p(hwnd),
                    None,
                    0,
                    0,
                    0,
                    0,
                    _SWP_NOMOVE
                    | _SWP_NOSIZE
                    | _SWP_NOZORDER
                    | _SWP_NOACTIVATE
                    | _SWP_FRAMECHANGED,
                )
                _refresh_title_bar(hwnd)
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

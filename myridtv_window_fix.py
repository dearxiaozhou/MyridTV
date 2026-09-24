# -*- coding: utf-8 -*-
"""Windows 窗口样式补丁（后端拆分第32刀自 rh_official_proxy.py 逐字外移）：
后台线程等待 MyridTV/WcsTV 主窗口出现，用 user32 API 把 POPUP/无框样式
修复为常规 WS_OVERLAPPEDWINDOW。完全自包含：零主文件全局依赖。"""
import ctypes
import threading
import time
import ctypes.wintypes


def _fix_window_style_worker():
    """后台线程：等待主窗口出现并自动修复样式"""
    # Windows API 常量
    GWL_STYLE = -16
    WS_CAPTION = 0x00C00000
    WS_THICKFRAME = 0x00040000
    WS_SYSMENU = 0x00080000
    WS_MINIMIZEBOX = 0x00020000
    WS_MAXIMIZEBOX = 0x00010000
    WS_POPUP = 0x80000000
    WS_OVERLAPPEDWINDOW = 0x00CF0000
    
    SWP_NOMOVE = 0x0002
    SWP_NOSIZE = 0x0001
    SWP_FRAMECHANGED = 0x0020
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    
    def find_window():
        found = []
        def enum_callback(hwnd, lparam):
            if ctypes.windll.user32.IsWindowVisible(hwnd):
                buf = ctypes.create_unicode_buffer(256)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
                title = buf.value.lower()
                if 'myridtv' in title or 'wcstv' in title:
                    found.append((hwnd, buf.value))
            return True
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        ctypes.windll.user32.EnumWindows(WNDENUMPROC(enum_callback), 0)
        return found
    
    def fix_window(hwnd):
        old_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
        # 检查是否已经是正常样式
        if (old_style & WS_CAPTION) and (old_style & WS_THICKFRAME) and (old_style & WS_SYSMENU):
            return False
        # 修复样式
        if old_style & WS_POPUP:
            new_style = (old_style & ~WS_POPUP) | WS_OVERLAPPEDWINDOW
        else:
            new_style = old_style | WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, new_style)
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED | SWP_NOACTIVATE)
        return True
    
    # 最多等待 30 秒
    for _ in range(60):
        time.sleep(0.5)
        windows = find_window()
        if windows:
            # 再等一下，确保窗口完全初始化
            time.sleep(0.5)
            for hwnd, title in windows:
                try:
                    fix_window(hwnd)
                except:
                    pass
            break


def _start_window_fix():
    """启动窗口自动修复的后台线程"""
    try:
        t = threading.Thread(target=_fix_window_style_worker, daemon=True)
        t.start()
    except:
        pass

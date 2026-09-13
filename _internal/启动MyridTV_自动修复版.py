"""
MyridTV 自动修复启动器
功能：启动应用并自动修复窗口样式问题
"""

import ctypes
import ctypes.wintypes
import time
import subprocess
import sys
import os

# ============================================
# 配置
# ============================================
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_EXE = os.path.join(APP_DIR, 'MyridTV-Desktop.exe')
PYTHON_EXE = sys.executable

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

# ============================================
# 窗口操作函数
# ============================================

def find_window():
    """查找 MyridTV/WcsTV 窗口"""
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
    """修复窗口样式"""
    old_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
    
    # 检查是否已经正常
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


# ============================================
# 主函数
# ============================================

def main():
    # 检查应用是否已运行
    windows = find_window()
    
    if windows:
        # 已运行，直接修复
        for hwnd, title in windows:
            fix_window(hwnd)
        return 0
    
    # 启动应用
    if not os.path.exists(APP_EXE):
        print(f"错误：找不到应用程序 {APP_EXE}")
        return 1
    
    subprocess.Popen([APP_EXE], cwd=APP_DIR)
    
    # 等待窗口出现（最多 15 秒）
    for i in range(30):
        time.sleep(0.5)
        windows = find_window()
        if windows:
            break
    
    # 修复窗口
    if windows:
        time.sleep(0.5)  # 等窗口完全初始化
        for hwnd, title in windows:
            fix_window(hwnd)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

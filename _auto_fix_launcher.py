"""
MyridTV 自动修复启动器
通过 IFEO 注册表注入，exe 启动时自动运行
启动真正的程序，等待窗口出现后修复样式，然后退出
"""
import ctypes
import ctypes.wintypes
import subprocess
import sys
import threading
import time
import os

def fix_window_style():
    """等待窗口出现并修复样式"""
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
        if (old_style & WS_CAPTION) and (old_style & WS_THICKFRAME) and (old_style & WS_SYSMENU):
            return False
        if old_style & WS_POPUP:
            new_style = (old_style & ~WS_POPUP) | WS_OVERLAPPEDWINDOW
        else:
            new_style = old_style | WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, new_style)
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED | SWP_NOACTIVATE)
        return True
    
    # 等待窗口出现并修复
    for _ in range(100):
        time.sleep(0.1)
        windows = find_window()
        if windows:
            time.sleep(0.3)
            for hwnd, title in windows:
                try:
                    fix_window(hwnd)
                except:
                    pass
            # 再修复几次防止被覆盖
            for _ in range(10):
                time.sleep(0.2)
                for hwnd, title in windows:
                    try:
                        fix_window(hwnd)
                    except:
                        pass
            return

def main():
    # 获取真正的 exe 路径（IFEO 会把原程序路径作为第一个参数）
    if len(sys.argv) > 1:
        real_exe = sys.argv[1]
        args = sys.argv[2:]
    else:
        # 如果没有参数，默认路径
        script_dir = os.path.dirname(os.path.abspath(__file__))
        real_exe = os.path.join(script_dir, "MyridTV-Desktop-core.exe")
        args = []
    
    # 启动真正的程序（不等待，立即返回）
    try:
        subprocess.Popen([real_exe] + args)
    except:
        # 如果启动失败，直接返回
        return
    
    # 在后台线程中修复窗口
    t = threading.Thread(target=fix_window_style, daemon=True)
    t.start()
    # 等待修复完成后退出（最多等 15 秒）
    t.join(timeout=15)

if __name__ == "__main__":
    main()

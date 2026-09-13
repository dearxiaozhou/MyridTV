import ctypes
import ctypes.wintypes
import time
import sys

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

def find_window_by_title(title_substring):
    found = []
    def enum_callback(hwnd, lparam):
        if ctypes.windll.user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
            if title_substring.lower() in buf.value.lower():
                found.append((hwnd, buf.value))
        return True
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    ctypes.windll.user32.EnumWindows(WNDENUMPROC(enum_callback), 0)
    return found

def fix_window(hwnd):
    old_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
    if old_style & WS_POPUP:
        new_style = (old_style & ~WS_POPUP) | WS_OVERLAPPEDWINDOW
    else:
        new_style = old_style
        if not (old_style & WS_CAPTION):
            new_style |= WS_CAPTION
        if not (old_style & WS_THICKFRAME):
            new_style |= WS_THICKFRAME
        if not (old_style & WS_SYSMENU):
            new_style |= WS_SYSMENU
        if not (old_style & WS_MINIMIZEBOX):
            new_style |= WS_MINIMIZEBOX
        if not (old_style & WS_MAXIMIZEBOX):
            new_style |= WS_MAXIMIZEBOX
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, new_style)
    ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED | SWP_NOACTIVATE)
    return True

if __name__ == '__main__':
    windows = find_window_by_title('MyridTV')
    if not windows:
        windows = find_window_by_title('WcsTV')
    
    if windows:
        for hwnd, title in windows:
            print(f'修复窗口: {title}')
            fix_window(hwnd)
        print('修复完成')
    else:
        print('未找到运行中的窗口')
        sys.exit(1)

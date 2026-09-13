import sys
if sys.platform == 'win32':
    import ctypes
    import ctypes.wintypes
    import threading
    import time
    
    # Windows API 常量
    GWL_STYLE = -16
    GWLP_WNDPROC = -4
    WS_THICKFRAME = 0x00040000
    WS_SYSMENU = 0x00080000
    WS_MINIMIZEBOX = 0x00020000
    WS_MAXIMIZEBOX = 0x00010000
    
    WM_NCHITTEST = 0x0084
    HTLEFT = 10
    HTRIGHT = 11
    HTTOP = 12
    HTTOPLEFT = 13
    HTTOPRIGHT = 14
    HTBOTTOM = 15
    HTBOTTOMLEFT = 16
    HTBOTTOMRIGHT = 17
    
    SWP_NOMOVE = 0x0002
    SWP_NOSIZE = 0x0001
    SWP_NOZORDER = 0x0004
    SWP_FRAMECHANGED = 0x0020
    SWP_NOACTIVATE = 0x0010
    
    BORDER_WIDTH = 6
    
    _old_wnd_proc = None
    _hwnd = None
    
    # 窗口过程
    def wnd_proc(hwnd, msg, wParam, lParam):
        if msg == WM_NCHITTEST:
            rect = ctypes.wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
            x = ctypes.c_short(lParam & 0xFFFF).value
            y = ctypes.c_short((lParam >> 16) & 0xFFFF).value
            
            left = x - rect.left < BORDER_WIDTH
            right = rect.right - x < BORDER_WIDTH
            top = y - rect.top < BORDER_WIDTH
            bottom = rect.bottom - y < BORDER_WIDTH
            
            if left and top:
                return HTTOPLEFT
            if right and top:
                return HTTOPRIGHT
            if left and bottom:
                return HTBOTTOMLEFT
            if right and bottom:
                return HTBOTTOMRIGHT
            if left:
                return HTLEFT
            if right:
                return HTRIGHT
            if top:
                return HTTOP
            if bottom:
                return HTBOTTOM
        return ctypes.windll.user32.CallWindowProcW(_old_wnd_proc, hwnd, msg, wParam, lParam)
    
    WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.wintypes.HWND, ctypes.c_uint, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)
    _wnd_proc = WNDPROC(wnd_proc)
    
    def fix_thread():
        global _hwnd, _old_wnd_proc
        while True:
            # 查找窗口
            _hwnd = ctypes.windll.user32.FindWindowW(None, "MyridTV")
            if not _hwnd:
                _hwnd = ctypes.windll.user32.FindWindowW(None, "WcsTV")
            
            if _hwnd and ctypes.windll.user32.IsWindow(_hwnd):
                # 设置样式
                style = ctypes.windll.user32.GetWindowLongW(_hwnd, GWL_STYLE)
                new_style = style | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX
                if style != new_style:
                    ctypes.windll.user32.SetWindowLongW(_hwnd, GWL_STYLE, new_style)
                    ctypes.windll.user32.SetWindowPos(_hwnd, 0, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED | SWP_NOACTIVATE)
                
                # 子类化窗口（只做一次）
                if not _old_wnd_proc:
                    _old_wnd_proc = ctypes.windll.user32.SetWindowLongPtrW(_hwnd, GWLP_WNDPROC, _wnd_proc)
            
            time.sleep(0.2)
    
    t = threading.Thread(target=fix_thread, daemon=True)
    t.start()

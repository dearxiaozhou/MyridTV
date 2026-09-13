import sys
if sys.platform == 'win32':
    import ctypes
    import ctypes.wintypes
    try:
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

        _SetWindowLongW = ctypes.windll.user32.SetWindowLongW
        _SetWindowLongPtrW = ctypes.windll.user32.SetWindowLongPtrW
        _CreateWindowExW = ctypes.windll.user32.CreateWindowExW

        def _is_target_window(hwnd):
            buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
            title = buf.value.lower()
            if 'myrid' in title or 'wcs' in title:
                return True
            buf2 = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetClassNameW(hwnd, buf2, 256)
            cls = buf2.value.lower()
            if 'webview' in cls or 'windows.forms' in cls:
                return True
            return False

        def _hooked_SetWindowLongW(hwnd, nIndex, dwNewLong):
            if nIndex == GWL_STYLE and _is_target_window(hwnd):
                dwNewLong = (dwNewLong & ~WS_POPUP) | WS_OVERLAPPEDWINDOW
            return _SetWindowLongW(hwnd, nIndex, dwNewLong)
        SWLW_proto = ctypes.WINFUNCTYPE(ctypes.wintypes.LONG, ctypes.wintypes.HWND, ctypes.c_int, ctypes.wintypes.LONG)
        ctypes.windll.user32.SetWindowLongW = SWLW_proto(_hooked_SetWindowLongW)

        def _hooked_SetWindowLongPtrW(hwnd, nIndex, dwNewLong):
            if nIndex == GWL_STYLE and _is_target_window(hwnd):
                dwNewLong = (dwNewLong & ~WS_POPUP) | WS_OVERLAPPEDWINDOW
            return _SetWindowLongPtrW(hwnd, nIndex, dwNewLong)
        SWLPW_proto = ctypes.WINFUNCTYPE(ctypes.wintypes.LONG_PTR, ctypes.wintypes.HWND, ctypes.c_int, ctypes.wintypes.LONG_PTR)
        ctypes.windll.user32.SetWindowLongPtrW = SWLPW_proto(_hooked_SetWindowLongPtrW)

        CEW_proto = ctypes.WINFUNCTYPE(
            ctypes.wintypes.HWND,
            ctypes.wintypes.DWORD, ctypes.wintypes.LPCWSTR, ctypes.wintypes.LPCWSTR,
            ctypes.wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.wintypes.HWND, ctypes.wintypes.HMENU, ctypes.wintypes.HINSTANCE, ctypes.wintypes.LPVOID,
            use_last_error=True
        )
        def _hooked_CreateWindowExW(dwExStyle, lpClassName, lpWindowName, dwStyle, X, Y, nWidth, nHeight, hWndParent, hMenu, hInstance, lpParam):
            name = (lpWindowName or '').lower()
            cls = (lpClassName or '').lower()
            if ('myrid' in name or 'wcs' in name) and (dwStyle & WS_POPUP):
                dwStyle = (dwStyle & ~WS_POPUP) | WS_OVERLAPPEDWINDOW
            return _CreateWindowExW(dwExStyle, lpClassName, lpWindowName, dwStyle, X, Y, nWidth, nHeight, hWndParent, hMenu, hInstance, lpParam)
        ctypes.windll.user32.CreateWindowExW = CEW_proto(_hooked_CreateWindowExW)

        import threading
        import time
        def _guard_thread():
            for _ in range(100):
                time.sleep(0.1)
                def cb(hwnd, _):
                    if _is_target_window(hwnd):
                        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
                        if not (style & WS_CAPTION) or not (style & WS_THICKFRAME) or not (style & WS_SYSMENU):
                            new_style = (style & ~WS_POPUP) | WS_OVERLAPPEDWINDOW
                            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, new_style)
                            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                                SWP_NOMOVE|SWP_NOSIZE|SWP_NOZORDER|SWP_FRAMECHANGED|SWP_NOACTIVATE)
                    return True
                WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
                ctypes.windll.user32.EnumWindows(WNDENUMPROC(cb), 0)
        t = threading.Thread(target=_guard_thread, daemon=True)
        t.start()
    except Exception:
        pass

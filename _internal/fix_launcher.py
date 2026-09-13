import ctypes, subprocess, sys, threading, time
def fix():
    GWL_STYLE=-16;WS_OW=0x00CF0000;WS_POPUP=0x80000000
    SWP=0x0002|0x0001|0x0004|0x0020|0x0010
    def find():
        r=[]
        def cb(h,_):
            if ctypes.windll.user32.IsWindowVisible(h):
                b=ctypes.create_unicode_buffer(256)
                ctypes.windll.user32.GetWindowTextW(h,b,256)
                if 'myridtv' in b.value.lower() or 'wcstv' in b.value.lower():r.append(h)
            return True
        CMP=ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL,ctypes.wintypes.HWND,ctypes.wintypes.LPARAM)
        ctypes.windll.user32.EnumWindows(CMP(cb),0)
        return r
    for _ in range(100):
        time.sleep(0.1)
        ws=find()
        if ws:
            time.sleep(0.3)
            for h in ws:
                o=ctypes.windll.user32.GetWindowLongW(h,GWL_STYLE)
                ctypes.windll.user32.SetWindowLongW(h,GWL_STYLE,(o&~WS_POPUP)|WS_OW)
                ctypes.windll.user32.SetWindowPos(h,0,0,0,0,0,SWP)
            for _ in range(20):
                time.sleep(0.2)
                for h in ws:
                    o=ctypes.windll.user32.GetWindowLongW(h,GWL_STYLE)
                    ctypes.windll.user32.SetWindowLongW(h,GWL_STYLE,(o&~WS_POPUP)|WS_OW)
                    ctypes.windll.user32.SetWindowPos(h,0,0,0,0,0,SWP)
            return
if __name__=='__main__':
    if len(sys.argv)>1:
        subprocess.Popen([sys.argv[1]]+sys.argv[2:])
        t=threading.Thread(target=fix,daemon=True)
        t.start()
        t.join(15)

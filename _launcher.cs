using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading;

class Program
{
    [DllImport("user32.dll")]
    static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
    
    [DllImport("user32.dll")]
    static extern int GetWindowLong(IntPtr hWnd, int nIndex);
    
    [DllImport("user32.dll")]
    static extern int SetWindowLong(IntPtr hWnd, int nIndex, int dwNewLong);
    
    [DllImport("user32.dll")]
    static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);
    
    [DllImport("user32.dll")]
    static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
    
    [DllImport("user32.dll")]
    static extern IntPtr SetWindowLongPtr(IntPtr hWnd, int nIndex, IntPtr dwNewLong);
    
    [DllImport("user32.dll")]
    static extern IntPtr CallWindowProc(IntPtr lpfnWndProc, IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);
    
    [DllImport("user32.dll")]
    static extern bool IsWindow(IntPtr hWnd);
    
    [StructLayout(LayoutKind.Sequential)]
    struct RECT { public int Left, Top, Right, Bottom; }
    
    const int GWL_STYLE = -16;
    const int GWLP_WNDPROC = -4;
    const int WS_THICKFRAME = 0x00040000;
    const int WS_SYSMENU = 0x00080000;
    const int WS_MINIMIZEBOX = 0x00020000;
    const int WS_MAXIMIZEBOX = 0x00010000;
    
    const uint WM_NCHITTEST = 0x0084;
    const int HTLEFT = 10;
    const int HTRIGHT = 11;
    const int HTTOP = 12;
    const int HTTOPLEFT = 13;
    const int HTTOPRIGHT = 14;
    const int HTBOTTOM = 15;
    const int HTBOTTOMLEFT = 16;
    const int HTBOTTOMRIGHT = 17;
    
    const uint SWP_NOMOVE = 0x0002;
    const uint SWP_NOSIZE = 0x0001;
    const uint SWP_NOZORDER = 0x0004;
    const uint SWP_FRAMECHANGED = 0x0020;
    const uint SWP_NOACTIVATE = 0x0010;
    
    static IntPtr _hwnd = IntPtr.Zero;
    static IntPtr _oldWndProc = IntPtr.Zero;
    static WndProcDelegate _delegate;
    static Process _proc;
    const int _borderWidth = 6;
    
    delegate IntPtr WndProcDelegate(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);
    
    static IntPtr WndProc(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam)
    {
        if (msg == WM_NCHITTEST)
        {
            RECT rect;
            if (GetWindowRect(hWnd, out rect))
            {
                int x = (short)(lParam.ToInt32() & 0xFFFF);
                int y = (short)((lParam.ToInt32() >> 16) & 0xFFFF);
                
                bool left = x - rect.Left < _borderWidth;
                bool right = rect.Right - x < _borderWidth;
                bool top = y - rect.Top < _borderWidth;
                bool bottom = rect.Bottom - y < _borderWidth;
                
                if (left && top) return (IntPtr)HTTOPLEFT;
                if (right && top) return (IntPtr)HTTOPRIGHT;
                if (left && bottom) return (IntPtr)HTBOTTOMLEFT;
                if (right && bottom) return (IntPtr)HTBOTTOMRIGHT;
                if (left) return (IntPtr)HTLEFT;
                if (right) return (IntPtr)HTRIGHT;
                if (top) return (IntPtr)HTTOP;
                if (bottom) return (IntPtr)HTBOTTOM;
            }
        }
        return CallWindowProc(_oldWndProc, hWnd, msg, wParam, lParam);
    }

    static void Main()
    {
        string dir = AppDomain.CurrentDomain.BaseDirectory;
        _proc = Process.Start(dir + "MyridTV-Desktop-core.exe");
        
        uint flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED | SWP_NOACTIVATE;
        _delegate = WndProc;
        
        // 循环等待窗口出现
        while (_hwnd == IntPtr.Zero)
        {
            Thread.Sleep(100);
            _hwnd = FindWindow(null, "MyridTV");
            if (_hwnd == IntPtr.Zero) _hwnd = FindWindow(null, "WcsTV");
        }
        
        Thread.Sleep(500);
        
        // 子类化窗口
        _oldWndProc = SetWindowLongPtr(_hwnd, GWLP_WNDPROC, Marshal.GetFunctionPointerForDelegate(_delegate));
        
        // 持续运行，保持修复，直到目标进程退出
        while (IsWindow(_hwnd) && !_proc.HasExited)
        {
            // 持续修复样式，防止被改回去
            int style = GetWindowLong(_hwnd, GWL_STYLE);
            int targetStyle = style | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX;
            if (style != targetStyle)
            {
                SetWindowLong(_hwnd, GWL_STYLE, targetStyle);
                SetWindowPos(_hwnd, IntPtr.Zero, 0, 0, 0, 0, flags);
            }
            Thread.Sleep(200);
        }
    }
}

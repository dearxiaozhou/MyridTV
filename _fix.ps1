Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {
    [DllImport("user32.dll")]
    public static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
    [DllImport("user32.dll")]
    public static extern int GetWindowLong(IntPtr hWnd, int nIndex);
    [DllImport("user32.dll")]
    public static extern int SetWindowLong(IntPtr hWnd, int nIndex, int dwNewLong);
    [DllImport("user32.dll")]
    public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);
}
"@

$GWL_STYLE = -16
$WS_OVERLAPPEDWINDOW = 0x00CF0000
$WS_POPUP = 0x80000000
$SWP_NOMOVE = 0x0002
$SWP_NOSIZE = 0x0001
$SWP_NOZORDER = 0x0004
$SWP_FRAMECHANGED = 0x0020
$SWP_NOACTIVATE = 0x0010
$flags = $SWP_NOMOVE -bor $SWP_NOSIZE -bor $SWP_NOZORDER -bor $SWP_FRAMECHANGED -bor $SWP_NOACTIVATE

Start-Sleep -Milliseconds 500

for ($i=0; $i -lt 100; $i++) {
    Start-Sleep -Milliseconds 100
    $hwnd = [Win32]::FindWindow($null, "MyridTV")
    if ($hwnd -eq [IntPtr]::Zero) { $hwnd = [Win32]::FindWindow($null, "WcsTV") }
    if ($hwnd -ne [IntPtr]::Zero) {
        Start-Sleep -Milliseconds 300
        for ($j=0; $j -lt 40; $j++) {
            Start-Sleep -Milliseconds 200
            $style = [Win32]::GetWindowLong($hwnd, $GWL_STYLE)
            $newStyle = ($style -band (-bnot $WS_POPUP)) -bor $WS_OVERLAPPEDWINDOW
            [Win32]::SetWindowLong($hwnd, $GWL_STYLE, $newStyle) | Out-Null
            [Win32]::SetWindowPos($hwnd, [IntPtr]::Zero, 0, 0, 0, 0, $flags) | Out-Null
        }
        break
    }
}

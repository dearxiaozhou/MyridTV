using System.Drawing;
using System.Net.Http;
using System.Text.Json;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Diagnostics;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace MyridTV.Desktop;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        ApplicationConfiguration.Initialize();
        Application.Run(new MainWindow());
    }
}

internal sealed class MainWindow : Form
{
    // 端口不写死：从本安装目录的 _internal\data\app_config.json 读 proxy.port
    // （多份安装各用各的端口；start_myridtv.ps1 在端口被别的安装占用时会把新端口写回同一份配置）
    private static readonly string ProxyBaseUrl = ResolveProxyBaseUrl();
    private static readonly string HealthUrl = ProxyBaseUrl + "/health";
    private static readonly string StartUrl = ProxyBaseUrl + "/static/index.html";

    private static string ResolveProxyBaseUrl()
    {
        var appDir = Path.GetDirectoryName(Application.ExecutablePath) ?? ".";
        var port = 0;
        try
        {
            var configPath = Path.Combine(appDir, "_internal", "data", "app_config.json");
            if (File.Exists(configPath))
            {
                using var doc = JsonDocument.Parse(File.ReadAllText(configPath));
                if (doc.RootElement.TryGetProperty("proxy", out var proxy))
                {
                    if (proxy.TryGetProperty("port", out var portElement) && portElement.TryGetInt32(out var configuredPort) && configuredPort > 0 && configuredPort < 65536)
                    {
                        port = configuredPort;
                    }
                    else if (proxy.TryGetProperty("base_url", out var baseUrlElement) && baseUrlElement.ValueKind == JsonValueKind.String &&
                             Uri.TryCreate(baseUrlElement.GetString(), UriKind.Absolute, out var baseUri))
                    {
                        port = baseUri.Port;
                    }
                }
            }
        }
        catch (Exception ex)
        {
            LogDesktop("resolve proxy port failed: " + ex.Message);
        }
        if (port <= 0)
        {
            var envPort = Environment.GetEnvironmentVariable("MYRIDTV_PROXY_PORT");
            if (int.TryParse(envPort, out var parsedEnvPort) && parsedEnvPort > 0 && parsedEnvPort < 65536)
            {
                port = parsedEnvPort;
            }
        }
        if (port <= 0) port = 3107;
        LogDesktop($"proxy port resolved: {port} (config={Path.Combine(appDir, "_internal", "data", "app_config.json")})");
        return $"http://127.0.0.1:{port}";
    }

    private static void LogDesktop(string message)
    {
        try
        {
            var appDir = Path.GetDirectoryName(Application.ExecutablePath) ?? ".";
            var logDir = Path.Combine(appDir, "_internal", "data", "logs");
            Directory.CreateDirectory(logDir);
            File.AppendAllText(Path.Combine(logDir, "desktop.log"), $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] {message}{Environment.NewLine}");
        }
        catch { }
    }

    // WebView2 用户数据目录按安装隔离。曾写死 %APPDATA%\MyridTV\webview2，多份安装共用同一个 profile：
    // 后开的那份 CreateCoreWebView2ControllerAsync 报 0x8007139F 弹「无法启动 MyridTV」；表单历史/自动填充也跨安装串。
    private static string ResolveWebViewProfileFolder()
    {
        var appDir = Path.GetDirectoryName(Application.ExecutablePath) ?? ".";
        var portableRoot = Path.Combine(appDir, "user_data");
        if (Directory.Exists(portableRoot) || File.Exists(Path.Combine(appDir, ".portable")))
        {
            return Path.Combine(portableRoot, "webview2");
        }
        return Path.Combine(appDir, "_internal", "data", "webview2");
    }

    private const int DWMWA_USE_IMMERSIVE_DARK_MODE = 20;
    private const int DWMWA_TEXT_COLOR = 36;

    private static readonly Color DarkBg = Color.FromArgb(0x15, 0x19, 0x1C);
    private static readonly Color DarkFg = Color.FromArgb(0xED, 0xF2, 0xF2);
    private static readonly Color LightBg = Color.FromArgb(0xEE, 0xF3, 0xF0);
    private static readonly Color LightFg = Color.FromArgb(0x23, 0x39, 0x2D);
    // 自绘 HTML 标题栏（#tb-bar）的条带底色：客户区吃进标题栏行后 DWM 仍绘制 Caption 按钮与标题文字，
    // 文字用 DWMWA_TEXT_COLOR 染成同色藏掉（HideDwmCaptionText），右侧按钮区留给原生按钮。
    private static readonly Color TitleStripDark = Color.FromArgb(0x1B, 0x21, 0x25);
    private static readonly Color TitleStripLight = Color.FromArgb(0xF3, 0xF7, 0xF5);

    private readonly Label statusLabel;
    private readonly WebView2 webView;

    private bool isDarkTheme;
    private int captionFrameY;
    private int captionFrameX;
    private int captionButtonsWidth;
    private bool captionMetricsReady;
    private bool? lastWindowMaximized;

    [DllImport("dwmapi.dll")]
    private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);

    [DllImport("user32.dll")]
    private static extern short GetKeyState(int virtualKey);

    // —— 标题栏一体化：把客户区吃进原生标题栏，保留原生边框/缩放/贴靠/Caption 按钮 ——
    private const int WM_NCCALCSIZE = 0x0083;
    private const int HTCAPTION = 2;
    private const int SM_CYFRAME = 33;
    private const int SM_CXFRAME = 32;
    private const int SM_CXPADDEDBORDER = 92;
    private const int SM_CYCAPTION = 4;
    private const int WM_NCLBUTTONDOWN = 0x00A1;
    private const int WM_SYSCOMMAND = 0x0112;
    private const int WM_SIZE = 0x0005;
    private const int SIZE_RESTORED = 0;
    private const int SIZE_MAXIMIZED = 2;
    private const int SC_RESTORE = 0xF120;
    private const int SC_MAXIMIZE = 0xF030;
    private const int SC_MINIMIZE = 0xF020;
    private const int SC_MOVE = 0xF010;
    private const int SC_SIZE = 0xF000;
    private const int SC_CLOSE = 0xF060;
    private const int WM_NULL = 0x0000;

    // —— 2026-10-17 老王：右键标题栏弹 Windows 系统菜单（还原/移动/大小/最小化/最大化/关闭）——
    // 客户区已吃进标题栏行，原生 WM_NCRBUTTONUP(HTCAPTION) 不会再触发，改由网页 contextmenu
    // 回传 win|sysmenu，壳层取当前光标位置弹原生菜单（TrackPopupMenuEx + TPM_RETURNCMD）。
    private const uint TPM_LEFTALIGN = 0x0000;
    private const uint TPM_TOPALIGN = 0x0000;
    private const uint TPM_RETURNCMD = 0x0100;
    private const uint TPM_RIGHTBUTTON = 0x0002;
    private const uint MF_BYCOMMAND = 0x00000000;
    private const uint MF_ENABLED = 0x00000000;
    private const uint MF_GRAYED = 0x00000001;
    // 缩放热区（WM_NCLBUTTONDOWN 的 wParam）：网页条带最上沿模拟原生上边框
    private const int HTLEFT = 10;
    private const int HTTOP = 12;
    private const int HTTOPLEFT = 13;
    private const int HTTOPRIGHT = 14;

    [StructLayout(LayoutKind.Sequential)]
    private struct POINT
    {
        public int X;
        public int Y;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct RECT
    {
        public int left, top, right, bottom;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct NCCALCSIZE_PARAMS
    {
        public RECT rgrc0;
        public RECT rgrc1;
        public RECT rgrc2;
        public IntPtr lppos;
    }

    [DllImport("user32.dll")]
    private static extern int GetSystemMetricsForDpi(int nIndex, int dpi);

    [DllImport("user32.dll")]
    private static extern bool IsZoomed(IntPtr hWnd);

    [DllImport("user32.dll")]
    private static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int x, int y, int cx, int cy, uint uFlags);

    [DllImport("user32.dll")]
    private static extern bool ReleaseCapture();

    [DllImport("user32.dll")]
    private static extern IntPtr SendMessage(IntPtr hWnd, int msg, IntPtr wParam, IntPtr lParam);

    [DllImport("user32.dll")]
    private static extern bool PostMessage(IntPtr hWnd, int msg, IntPtr wParam, IntPtr lParam);

    [DllImport("user32.dll")]
    private static extern IntPtr GetSystemMenu(IntPtr hWnd, bool bRevert);

    // 返回值是 BOOL，但 TPM_RETURNCMD 下它承载的是被选中的菜单项命令 id（不是 true/false）
    [DllImport("user32.dll")]
    private static extern int TrackPopupMenuEx(IntPtr hMenu, uint uFlags, int x, int y, IntPtr hwnd, IntPtr lptpm);

    [DllImport("user32.dll")]
    private static extern bool EnableMenuItem(IntPtr hMenu, uint uIDEnableItem, uint uEnable);

    [DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    private static extern bool GetCursorPos(out POINT lpPoint);

    private static void DispatchCanvasGroupShortcut(CoreWebView2 core)
    {
        _ = core.ExecuteScriptAsync("""
            (function(){
                const frame = [...document.querySelectorAll('iframe')]
                    .find(item => item.src.includes('/static/smart-canvas.html'));
                const canvasWindow = frame && frame.contentWindow;
                if (!canvasWindow) return false;
                if (typeof canvasWindow.groupSelectedNodes === 'function') {
                    canvasWindow.groupSelectedNodes();
                    return true;
                }
                canvasWindow.dispatchEvent(new KeyboardEvent('keydown', {
                    key: 'g', code: 'KeyG', ctrlKey: true, bubbles: true, cancelable: true
                }));
                return true;
            })();
            """);
    }

    public MainWindow()
    {
        Text = "MyridTV";
        StartPosition = FormStartPosition.CenterScreen;
        MinimumSize = new Size(960, 640);
        Size = new Size(1440, 960);
        FormBorderStyle = FormBorderStyle.Sizable;

        try
        {
            var dir = Path.GetDirectoryName(Application.ExecutablePath) ?? ".";
            var iconPath = Path.Combine(dir, "_internal", "static", "images", "myrid-icon.ico");
            if (File.Exists(iconPath))
            {
                Icon = new Icon(iconPath);
            }
        }
        catch
        {
            // The window can still run without a custom icon.
        }

        statusLabel = new Label
        {
            Dock = DockStyle.Fill,
            Text = "正在启动 MyridTV...",
            TextAlign = ContentAlignment.MiddleCenter,
            Font = new Font("Microsoft YaHei UI", 11, FontStyle.Bold)
        };

        webView = new WebView2
        {
            Dock = DockStyle.Fill,
            Visible = false
        };

        var content = new Panel
        {
            Dock = DockStyle.Fill,
            Margin = Padding.Empty,
            Padding = Padding.Empty
        };

        content.Controls.Add(webView);
        content.Controls.Add(statusLabel);
        Controls.Add(content);

        ApplyThemeColors(false);

        Shown += async (_, _) => await InitAsync();
    }

    protected override void OnHandleCreated(EventArgs e)
    {
        base.OnHandleCreated(e);
        ApplyDwmTitleBarTheme(isDarkTheme);
        InitCaptionMetrics();
        HideDwmCaptionText(isDarkTheme ? TitleStripDark : TitleStripLight);
    }

    private void ApplyThemeColors(bool dark)
    {
        isDarkTheme = dark;

        var bg = dark ? DarkBg : LightBg;
        var fg = dark ? DarkFg : LightFg;
        var contentBg = dark ? DarkBg : LightBg;

        BackColor = bg;
        statusLabel.BackColor = contentBg;
        statusLabel.ForeColor = fg;
        webView.DefaultBackgroundColor = contentBg;

        ApplyDwmTitleBarTheme(dark);
        HideDwmCaptionText(dark ? TitleStripDark : TitleStripLight);
    }

    private void ApplyDwmTitleBarTheme(bool dark)
    {
        if (!IsHandleCreated)
        {
            return;
        }

        try
        {
            var darkValue = dark ? 1 : 0;
            DwmSetWindowAttribute(
                Handle,
                DWMWA_USE_IMMERSIVE_DARK_MODE,
                ref darkValue,
                Marshal.SizeOf<int>());
        }
        catch
        {
            // Older Windows versions can ignore this attribute.
        }
    }

    private void SetupThemeSync()
    {
        var core = webView.CoreWebView2;

        _ = core.AddScriptToExecuteOnDocumentCreatedAsync("""
            (function(){
            if (window.__myridtvTitleThemeBridge) return;
            window.__myridtvTitleThemeBridge = true;

                function normalize(theme) {
                    return theme === 'dark' ? 'dark' : 'light';
                }

                function readTheme() {
                    try {
                        if (window.StudioTheme && typeof window.StudioTheme.get === 'function') {
                            return normalize(window.StudioTheme.get());
                        }
                        return normalize(localStorage.getItem('studio_theme') || localStorage.getItem('canvas_theme') || 'light');
                    } catch(e) {
                        return 'light';
                    }
                }

                function notify(theme) {
                    try {
                        window.chrome.webview.postMessage('theme|' + normalize(theme));
                    } catch(e) {}
                }

                function sync() {
                    notify(readTheme());
                }

                try {
                    var originalSetItem = Storage.prototype.setItem;
                    Storage.prototype.setItem = function(key, value) {
                        var result = originalSetItem.apply(this, arguments);
                        if (this === localStorage && (key === 'studio_theme' || key === 'canvas_theme')) {
                            notify(value);
                        }
                        return result;
                    };
                } catch(e) {}

                window.addEventListener('studio-theme-change', function(event) {
                    notify(event && event.detail ? event.detail.theme : readTheme());
                });
                window.addEventListener('storage', function(event) {
                    if (event.key === 'studio_theme' || event.key === 'canvas_theme') {
                        notify(event.newValue);
                    }
                });
                document.addEventListener('DOMContentLoaded', sync);
                window.addEventListener('load', sync);

                setTimeout(sync, 0);
                setTimeout(sync, 200);
                setTimeout(sync, 1000);
            })();
            """);

        core.WebMessageReceived += (_, args) =>
        {
            var msg = args.TryGetWebMessageAsString();
            if (string.IsNullOrEmpty(msg)) return;
            if (msg.StartsWith("theme|", StringComparison.Ordinal))
            {
                ApplyThemeFromString(msg[6..]);
                return;
            }
            // 自绘 HTML 标题栏（#tb-bar）回传的跨壳动作
            if (msg.StartsWith("menu|", StringComparison.Ordinal) || msg.StartsWith("win|", StringComparison.Ordinal))
            {
                HandleTitleBarMessage(msg);
                return;
            }
            // 资产目录页「浏览…」：iframe 没有 chrome.webview，由 index.html 父文档转发
            if (msg.StartsWith("assets|", StringComparison.Ordinal))
            {
                _ = PickAssetsDirAsync();
            }
        };

        core.NavigationCompleted += async (_, _) => await SyncThemeFromPageAsync();
    }

    private async Task SyncThemeFromPageAsync()
    {
        try
        {
            var result = await webView.CoreWebView2.ExecuteScriptAsync("""
                (function(){
                    try {
                        if (window.StudioTheme && typeof window.StudioTheme.get === 'function') {
                            return window.StudioTheme.get();
                        }
                        return localStorage.getItem('studio_theme') || localStorage.getItem('canvas_theme') || 'light';
                    } catch(e) {
                        return 'light';
                    }
                })();
                """);

            ApplyThemeFromString(result.Trim().Trim('"'));
        }
        catch
        {
            // Navigation can finish during shutdown; ignore late sync failures.
        }
    }

    private void ApplyThemeFromString(string theme)
    {
        var dark = string.Equals(theme, "dark", StringComparison.OrdinalIgnoreCase);
        if (InvokeRequired)
        {
            BeginInvoke(() => ApplyThemeColors(dark));
            return;
        }

        ApplyThemeColors(dark);
    }

    // —— 自绘 HTML 标题栏（2026-10-16，取代原底部 dock 与 WinForms MenuStrip）——
    // 设计约束：
    // 1) 标题栏整行（图标槽 / 菜单 / 拖动区）由 _internal/static/index.html 的 #tb-bar 自绘，
    //    与 ChatGPT / WorkBuddy 同构；壳层只保留原生 Caption 按钮命中区、吃标题栏行与消息分发；
    // 2) 网页内可完成的动作（切页 / 外观 / 语言 / 控制台）由页面脚本直接调全局函数，
    //    跨壳动作经 postMessage 回传：menu|new-canvas / menu|import-canvas / menu|export-canvas /
    //    menu|backend-url / menu|logs / menu|about / menu|update / menu|exit；
    // 3) 窗口拖动 / 最大化切换：win|drag → ReleaseCapture + WM_NCLBUTTONDOWN(HTCAPTION)，
    //    win|maximize-toggle → SC_MAXIMIZE / SC_RESTORE；
    // 4) 画布动作仍跨 iframe 调用 canvas.html 内的全局函数（与 DispatchCanvasGroupShortcut 同一模式）；
    // 5) 配色与既有 web→shell theme 桥联动，收口在 ApplyThemeColors → HideDwmCaptionText。

    private const string ScriptNewCanvas = "(function(){var w=document.getElementById('frame-canvas');var cw=w&&w.contentWindow;if(cw&&typeof cw.createSmartCanvas==='function'){cw.createSmartCanvas();return 'ok'}return 'no'})()";
    private const string ScriptImportCanvas = "(function(){var w=document.getElementById('frame-canvas');var d=w&&w.contentWindow&&w.contentWindow.document;var b=d&&d.getElementById('gateImportBtn');if(b){b.click();return 'ok'}return 'no'})()";

    private void InitCaptionMetrics()
    {
        try
        {
            var dpi = DeviceDpi;
            captionFrameY = GetSystemMetricsForDpi(SM_CYFRAME, dpi) + GetSystemMetricsForDpi(SM_CXPADDEDBORDER, dpi);
            captionFrameX = GetSystemMetricsForDpi(SM_CXFRAME, dpi) + GetSystemMetricsForDpi(SM_CXPADDEDBORDER, dpi);
            // 标题栏行总高（缩放边框+caption）实测 31px@96dpi：客户区整行吃进，#tb-bar 按同高自绘
            var stripHeight = PointToScreen(Point.Empty).Y - Top;
            if (stripHeight <= 8) stripHeight = captionFrameY + GetSystemMetricsForDpi(SM_CYCAPTION, dpi);
            // 窗口按钮区总宽（Windows 三键 46px/键 @96dpi），推给网页 --tb-btn-w
            captionButtonsWidth = (int)Math.Round(46.0 * dpi / 96.0) * 3;
            captionMetricsReady = true;
            // 强制 Windows 重发 WM_NCCALCSIZE，让客户区立即吃进标题栏
            SetWindowPos(Handle, IntPtr.Zero, 0, 0, 0, 0, 0x0020 | 0x0002 | 0x0001 | 0x0004);
        }
        catch
        {
            captionMetricsReady = false;
        }
    }

    /// <summary>
    /// 把窗口按钮区总宽推给网页标题栏（CSS 变量 --tb-btn-w，对齐 Windows 三键宽度），
    /// 让 #tb-bar 右侧自绘按钮区在任何 DPI 下保持原生比例；失败时网页用 138px 兜底。
    /// </summary>
    private void PushCaptionButtonWidth()
    {
        try
        {
            var width = captionMetricsReady ? captionButtonsWidth : 138;
            _ = webView.CoreWebView2.ExecuteScriptAsync(
                "document.documentElement.style.setProperty('--tb-btn-w','" + width + "px')");
        }
        catch
        {
            // CoreWebView2 尚未就绪：保持 CSS 兜底值。
        }
    }

    protected override void WndProc(ref Message m)
    {
        if (m.Msg == WM_NCCALCSIZE && m.WParam != IntPtr.Zero && captionMetricsReady)
        {
            // 传入的 rgrc0 是完整窗口矩形：左右下裁出缩放边框。
            // 还原态：rgrc0.top 不动 = 整个标题栏行（帧+caption，实测 31px）吃进客户区，
            //         由 #tb-bar 自绘菜单与窗口按钮（DWM 原生按钮会被 WebView2 的不透明内容盖住，故自绘）；
            // 最大化态：窗口矩形比工作区大出上下左右各一个帧宽（实测 inflate=8），
            //         顶部只裁帧宽、不裁 caption → 客户区恰好等于工作区，HTML 标题栏完整可见。
            var p = Marshal.PtrToStructure<NCCALCSIZE_PARAMS>(m.LParam);
            p.rgrc0.left += captionFrameX;
            p.rgrc0.right -= captionFrameX;
            p.rgrc0.bottom -= captionFrameY;
            if (IsZoomed(Handle))
            {
                p.rgrc0.top += captionFrameY;
            }
            Marshal.StructureToPtr(p, m.LParam, false);
            m.Result = IntPtr.Zero;
            return;
        }
        if (m.Msg == WM_SIZE && captionMetricsReady)
        {
            base.WndProc(ref m);
            // 标题栏行已整体放行给 WebView2（不再劫持 WM_NCHITTEST）：最大化/还原时把状态同步给网页，
            // 让 #tb-bar 的最大化按钮切换字形（只在状态真正变化时通知，避免交互缩放时刷屏）
            var code = m.WParam.ToInt32();
            if (code == SIZE_MAXIMIZED || code == SIZE_RESTORED)
            {
                if (lastWindowMaximized != (code == SIZE_MAXIMIZED))
                {
                    lastWindowMaximized = code == SIZE_MAXIMIZED;
                    try
                    {
                        _ = webView.CoreWebView2?.ExecuteScriptAsync(
                            "window.__tbSyncWinState&&window.__tbSyncWinState(" +
                            (code == SIZE_MAXIMIZED ? "true" : "false") + ")");
                    }
                    catch
                    {
                        // CoreWebView2 尚未就绪：网页加载后会再同步一次。
                    }
                }
            }
            return;
        }
        base.WndProc(ref m);
    }

    /// <summary>
    /// 分发自绘 HTML 标题栏回传的跨壳动作（menu|… / win|…）。
    /// </summary>
    private void HandleTitleBarMessage(string msg)
    {
        if (InvokeRequired)
        {
            BeginInvoke(() => HandleTitleBarMessage(msg));
            return;
        }
        switch (msg)
        {
            case "menu|new-canvas": _ = SwitchAndRunAsync("canvas", ScriptNewCanvas); break;
            case "menu|import-canvas": _ = SwitchAndRunAsync("canvas", ScriptImportCanvas); break;
            case "menu|export-canvas": _ = ExportCurrentCanvasAsync(); break;
            case "menu|backend-url": _ = CopyBackendUrlAsync(); break;
            case "menu|logs": _ = OpenLogFolderAsync(); break;
            case "menu|about": ShowAbout(); break;
            case "menu|update": _ = CheckUpdateAsync(); break;
            case "menu|exit": ExitApp(); break;
            case "win|drag": BeginWindowDrag(); break;
            case "win|maximize-toggle": ToggleMaximize(); break;
            case "win|minimize": MinimizeWindow(); break;
            case "win|close": Close(); break;
            case "win|sysmenu": ShowSystemMenu(); break;
            default:
                // win|resize|<HT 热区值>：拖窗口边缘缩放（网页条带上沿模拟原生上边框）
                if (msg.StartsWith("win|resize|", StringComparison.Ordinal))
                {
                    if (int.TryParse(msg["win|resize|".Length..], out var hit)) BeginWindowResize(hit);
                }
                break;
        }
    }

    /// <summary>
    /// 右键自绘标题栏 → Windows 原生系统菜单（还原 / 移动 / 大小 / 最小化 / 最大化 / 关闭）。
    /// 位置直接用当前光标（右键那一刻光标就在条带上，省掉跨 DPI/iframe 的坐标换算）；
    /// 菜单各项按窗口状态置灰（最大化时「移动/大小/最大化」不可用），选中后发 WM_SYSCOMMAND。
    /// </summary>
    private void ShowSystemMenu()
    {
        try
        {
            var menu = GetSystemMenu(Handle, false);
            if (menu == IntPtr.Zero) return;
            var maximized = IsZoomed(Handle);
            EnableMenuItem(menu, SC_RESTORE, MF_BYCOMMAND | (maximized ? MF_ENABLED : MF_GRAYED));
            EnableMenuItem(menu, SC_MOVE, MF_BYCOMMAND | (maximized ? MF_GRAYED : MF_ENABLED));
            EnableMenuItem(menu, SC_SIZE, MF_BYCOMMAND | (maximized ? MF_GRAYED : MF_ENABLED));
            EnableMenuItem(menu, SC_MINIMIZE, MF_BYCOMMAND | MF_ENABLED);
            EnableMenuItem(menu, SC_MAXIMIZE, MF_BYCOMMAND | (maximized ? MF_GRAYED : MF_ENABLED));
            EnableMenuItem(menu, SC_CLOSE, MF_BYCOMMAND | MF_ENABLED);

            if (!GetCursorPos(out var point)) return;
            // 弹菜单前必须置前，否则点空白处菜单不消失
            SetForegroundWindow(Handle);
            var command = TrackPopupMenuEx(
                menu,
                TPM_LEFTALIGN | TPM_TOPALIGN | TPM_RETURNCMD | TPM_RIGHTBUTTON,
                point.X, point.Y, Handle, IntPtr.Zero);
            // 菜单关闭后补一条空消息，逼 Windows 立刻重算窗口状态（防御菜单残留的高亮/焦点）
            PostMessage(Handle, WM_NULL, IntPtr.Zero, IntPtr.Zero);
            if (command > 0) SendMessage(Handle, WM_SYSCOMMAND, (IntPtr)command, IntPtr.Zero);
        }
        catch
        {
            // 系统菜单失败不影响窗口其他功能。
        }
    }

    /// <summary>
    /// 以原生边框缩放的方式进入缩放循环：网页条带最上沿（原生标题栏已被客户区吃掉，
    /// 顶部没有可缩放的 NC 区）用它补上「拖上边缘改窗口高度」。左右下三边仍是原生边框，不动。
    /// </summary>
    private void BeginWindowResize(int hitTest)
    {
        if (hitTest < HTLEFT || hitTest > HTTOPRIGHT) return; // 只接受 10..14（左/上/左上/右上）
        if (IsZoomed(Handle)) return;
        try
        {
            ReleaseCapture();
            SendMessage(Handle, WM_NCLBUTTONDOWN, (IntPtr)hitTest, IntPtr.Zero);
        }
        catch
        {
            // 合成输入失败时静默：窗口仍可用原生左/右/下边框缩放。
        }
    }

    /// <summary>
    /// 以原生 Caption 拖动的方式进入移动循环（保留 Win11 贴靠），松手自动结束。
    /// 注意：移动循环会吞掉 mouseup，网页侧收不到抬键——所以网页只在位移超阈值后才发 win|drag，
    /// 纯点击（含双击判定）不走这条路，点击流保持完整。
    /// </summary>
    private void BeginWindowDrag()
    {
        try
        {
            ReleaseCapture();
            SendMessage(Handle, WM_NCLBUTTONDOWN, (IntPtr)HTCAPTION, IntPtr.Zero);
        }
        catch
        {
            // 合成输入失败时静默：窗口仍可用原生边框拖动。
        }
    }

    private void ToggleMaximize()
    {
        try
        {
            SendMessage(Handle, WM_SYSCOMMAND, (IntPtr)(IsZoomed(Handle) ? SC_RESTORE : SC_MAXIMIZE), IntPtr.Zero);
        }
        catch
        {
            // 忽略：极端情况下用户仍可点原生最大化按钮。
        }
    }

    private void MinimizeWindow()
    {
        try
        {
            SendMessage(Handle, WM_SYSCOMMAND, (IntPtr)SC_MINIMIZE, IntPtr.Zero);
        }
        catch
        {
            // 忽略：极端情况下用户仍可用任务栏最小化。
        }
    }

    /// <summary>
    /// 客户区已吃进标题栏：把 DWM 绘制的窗口标题文字染成与 #tb-bar 条带同色（视觉隐藏，任务栏标签保留）。
    /// </summary>
    private void HideDwmCaptionText(Color background)
    {
        if (!IsHandleCreated) return;
        try
        {
            // COLORREF = 0x00BBGGRR
            var colorref = (background.R) | (background.G << 8) | (background.B << 16);
            DwmSetWindowAttribute(Handle, DWMWA_TEXT_COLOR, ref colorref, Marshal.SizeOf<int>());
        }
        catch
        {
            // 低于 Win11 22000 时忽略；老系统标题文字由 DWMWA 本身不绘制。
        }
    }

    private async Task RunTopLevelAsync(string script)
    {
        try { await webView.CoreWebView2.ExecuteScriptAsync(script); }
        catch { }
    }

    private async Task SwitchAndRunAsync(string pageId, string probeScript)
    {
        try
        {
            await webView.CoreWebView2.ExecuteScriptAsync("switchUI(null,'" + pageId + "')");
            for (var i = 0; i < 10; i++)
            {
                await Task.Delay(400);
                var result = await webView.CoreWebView2.ExecuteScriptAsync(probeScript);
                if (result != null && result.Contains("ok")) return;
            }
        }
        catch { }
    }

    private async Task<string> QueryWebValueAsync(string script)
    {
        try
        {
            var result = await webView.CoreWebView2.ExecuteScriptAsync(script);
            if (string.IsNullOrEmpty(result)) return string.Empty;
            return JsonSerializer.Deserialize<string>(result) ?? string.Empty;
        }
        catch { return string.Empty; }
    }

    private async Task ExportCurrentCanvasAsync()
    {
        var id = await QueryWebValueAsync("localStorage.getItem('studio_last_canvas_id')||''");
        if (string.IsNullOrWhiteSpace(id))
        {
            MessageBox.Show(this, "当前没有打开的画布。\n先打开一个画布，再导出。", "导出画布", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }
        var script = "(function(){var id=" + JsonSerializer.Serialize(id) + ";"
            + "var w=document.getElementById('frame-canvas');var cw=w&&w.contentWindow;"
            + "if(cw&&typeof cw.exportCanvasToFile==='function'){cw.exportCanvasToFile(id);return 'ok'}"
            + "var base=location.origin;"
            + "fetch(base+'/api/canvases/'+encodeURIComponent(id)+'/export',{cache:'no-store'})"
            + ".then(function(r){if(!r.ok)throw new Error('HTTP '+r.status);return r.json()})"
            + ".then(function(payload){"
            + "var blob=new Blob([JSON.stringify(payload,null,2)],{type:'application/json'});"
            + "var a=document.createElement('a');var href=URL.createObjectURL(blob);a.href=href;"
            + "var title=String((payload&&payload.canvas&&payload.canvas.title)||id).replace(/[\\\\/:*?\"<>|]/g,'_').slice(0,48);"
            + "a.download=title+'.myridtv-canvas.json';document.body.appendChild(a);a.click();a.remove();"
            + "setTimeout(function(){URL.revokeObjectURL(href)},2000);})"
            + ".catch(function(e){alert('导出失败：'+e.message)});return 'ok'})()";
        await RunTopLevelAsync(script);
    }

    private Task CopyBackendUrlAsync()
    {
        try { Clipboard.SetText(ProxyBaseUrl); }
        catch { }
        MessageBox.Show(this, "后端地址已复制到剪贴板：\n" + ProxyBaseUrl, "后端地址", MessageBoxButtons.OK, MessageBoxIcon.Information);
        return Task.CompletedTask;
    }

    /// <summary>
    /// 资产目录页「浏览…」按钮：原生文件夹选择框（老王 2026-10-16：自定义路径不许只能手打/复制地址）。
    /// iframe 内没有 window.chrome.webview，所以由 index.html 父文档把 'assets|pick-dir' 转发上来；
    /// 选完后在此用 ExecuteScriptAsync 回调父文档的 window.__onShellPickedDir(path)，父文档再转给弹窗 iframe。
    /// </summary>
    private async Task PickAssetsDirAsync()
    {
        string picked;
        try
        {
            using var dialog = new FolderBrowserDialog
            {
                Description = "选择资产主目录（不存在会自动创建）",
                ShowNewFolderButton = true,
                UseDescriptionForTitle = true
            };
            if (dialog.ShowDialog(this) != DialogResult.OK) return;
            picked = dialog.SelectedPath;
        }
        catch (Exception ex)
        {
            MessageBox.Show(this, "打开文件夹选择框失败：" + ex.Message, "资产目录", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }
        if (string.IsNullOrWhiteSpace(picked)) return;
        var js = "window.__onShellPickedDir && window.__onShellPickedDir(" + JsonSerializer.Serialize(picked) + ")";
        try { await webView.CoreWebView2.ExecuteScriptAsync(js); } catch { }
    }

    private async Task OpenLogFolderAsync()
    {
        var dirs = new System.Collections.Generic.List<string>();
        try
        {
            using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(3) };
            var response = await client.GetAsync(ProxyBaseUrl + "/health");
            if (response.IsSuccessStatusCode)
            {
                using var doc = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
                if (doc.RootElement.TryGetProperty("user_data_dir", out var userData))
                {
                    var root = userData.GetString();
                    if (!string.IsNullOrWhiteSpace(root)) dirs.Add(Path.Combine(root, "data", "logs"));
                }
            }
        }
        catch { }
        var roaming = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
        if (!string.IsNullOrWhiteSpace(roaming)) dirs.Add(Path.Combine(roaming, "MyridTV", "data", "logs"));
        foreach (var dir in dirs)
        {
            if (!Directory.Exists(dir)) continue;
            try
            {
                Process.Start(new ProcessStartInfo("explorer.exe", dir) { UseShellExecute = false });
                return;
            }
            catch { }
        }
        MessageBox.Show(this, "没找到日志目录。", "日志", MessageBoxButtons.OK, MessageBoxIcon.Information);
    }

    private async Task CheckUpdateAsync()
    {
        try
        {
            using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(20) };
            var content = new StringContent("{}", System.Text.Encoding.UTF8, "application/json");
            var response = await client.PostAsync(ProxyBaseUrl + "/api/update-check", content);
            var body = await response.Content.ReadAsStringAsync();
            var current = "V" + (Application.ProductVersion ?? string.Empty).Split('+')[0];
            var found = string.Empty;
            try
            {
                using var doc = JsonDocument.Parse(body);
                if (doc.RootElement.TryGetProperty("static_version", out var versionElement)) found = versionElement.GetString() ?? string.Empty;
            }
            catch { }
            if (!string.IsNullOrWhiteSpace(found) && !string.Equals(found, current, StringComparison.OrdinalIgnoreCase))
            {
                MessageBox.Show(this, "发现新版本 " + found + "，已下载到本地。\n保存好当前内容，重启 MyridTV 后生效。", "检查更新", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
            else
            {
                MessageBox.Show(this, "当前已是最新版本（" + current + "）。", "检查更新", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
        }
        catch (Exception ex)
        {
            MessageBox.Show(this, "检查更新失败：" + ex.Message, "检查更新", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private void ShowAbout()
    {
        var version = "V" + (Application.ProductVersion ?? string.Empty).Split('+')[0];
        MessageBox.Show(this, "MyridTV " + version + "\n后端 " + ProxyBaseUrl + "\n\n画布创作 · 本地优先", "关于 MyridTV", MessageBoxButtons.OK, MessageBoxIcon.Information);
    }

    private void ExitApp()
    {
        var answer = MessageBox.Show(this, "退出 MyridTV？\n正在运行的任务会在后台继续完成。", "退出", MessageBoxButtons.YesNo, MessageBoxIcon.Question);
        if (answer == DialogResult.Yes) Close();
    }

    private async Task InitAsync()
    {
        try
        {
            var folder = ResolveWebViewProfileFolder();
            LogDesktop($"webview profile: {folder}");
            ClearCache(folder);

            var env = await CoreWebView2Environment.CreateAsync(userDataFolder: folder);
            await webView.EnsureCoreWebView2Async(env);

            var core = webView.CoreWebView2;
            var controllerField = typeof(WebView2).GetField("_coreWebView2Controller", BindingFlags.Instance | BindingFlags.NonPublic);
            if (controllerField?.GetValue(webView) is CoreWebView2Controller controller)
            {
                controller.AcceleratorKeyPressed += (_, args) =>
                {
                    var keyDown = args.KeyEventKind is CoreWebView2KeyEventKind.KeyDown or CoreWebView2KeyEventKind.SystemKeyDown;
                    var ctrlDown = (GetKeyState((int)Keys.ControlKey) & 0x8000) != 0;
                    var shiftDown = (GetKeyState((int)Keys.ShiftKey) & 0x8000) != 0;
                    if (keyDown && args.VirtualKey == (uint)Keys.G && ctrlDown && !shiftDown)
                    {
                        args.Handled = true;
                        DispatchCanvasGroupShortcut(core);
                    }
                };
            }
            core.Settings.AreDefaultContextMenusEnabled = false;
            core.Settings.AreDevToolsEnabled = false;
            core.Settings.AreBrowserAcceleratorKeysEnabled = true;
            core.Settings.IsStatusBarEnabled = false;
            core.Settings.IsZoomControlEnabled = false;
            // 关掉 WebView2 通用自动填充：平台名称/请求地址这类输入框不再记录、不再弹历史值。
            // 注意：这是浏览器 profile 级设置，不换目录（%APPDATA%\MyridTV\webview2 仍与其它安装共用），
            // 只保证今后不再往那份 profile 里写表单值；localStorage 里的画布偏好不受影响。
            try
            {
                core.Settings.IsGeneralAutofillEnabled = false;
                LogDesktop($"general autofill enabled={core.Settings.IsGeneralAutofillEnabled}");
            }
            catch (Exception ex)
            {
                LogDesktop("disable general autofill failed: " + ex.Message);
            }

            SetupThemeSync();
            PushCaptionButtonWidth();

            if (!await WaitReadyAsync())
            {
                statusLabel.Text = "MyridTV 启动超时，正在尝试直接打开...";
            }

            webView.Source = new Uri(StartUrl);
            webView.Visible = true;
            statusLabel.Visible = false;
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                $"无法启动 MyridTV。\n\n{ex.Message}",
                "MyridTV 启动失败",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            Close();
        }
    }

    private static async Task<bool> WaitReadyAsync()
    {
        using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(2) };

        for (var i = 0; i < 40; i++)
        {
            try
            {
                using var response = await client.GetAsync(HealthUrl);
                if (response.IsSuccessStatusCode)
                {
                    return true;
                }
            }
            catch
            {
                // The local backend may still be starting.
            }

            await Task.Delay(250);
        }

        return false;
    }

    private static void ClearCache(string folder)
    {
        foreach (var name in new[] { "Cache", "Code Cache", "GPUCache", "Service Worker", "blob_storage" })
        {
            var path = Path.Combine(folder, name);
            try
            {
                if (Directory.Exists(path))
                {
                    Directory.Delete(path, true);
                }
            }
            catch
            {
                // Cache cleanup is best-effort only.
            }
        }
    }
}

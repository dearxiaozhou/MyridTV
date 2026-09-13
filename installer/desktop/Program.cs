using System.Drawing;
using System.Net.Http;
using System.Text.Json;
using System.Reflection;
using System.Runtime.InteropServices;
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

    private const int DWMWA_USE_IMMERSIVE_DARK_MODE = 20;

    private static readonly Color DarkBg = Color.FromArgb(4, 10, 22);
    private static readonly Color DarkFg = Color.White;
    private static readonly Color LightBg = Color.FromArgb(248, 250, 252);
    private static readonly Color LightFg = Color.FromArgb(15, 23, 42);

    private readonly Label statusLabel;
    private readonly WebView2 webView;

    private bool isDarkTheme;

    [DllImport("dwmapi.dll")]
    private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);

    [DllImport("user32.dll")]
    private static extern short GetKeyState(int virtualKey);

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
    }

    private void ApplyThemeColors(bool dark)
    {
        isDarkTheme = dark;

        var bg = dark ? DarkBg : LightBg;
        var fg = dark ? DarkFg : LightFg;
        var contentBg = dark ? Color.FromArgb(15, 20, 32) : Color.FromArgb(248, 250, 252);

        BackColor = bg;
        statusLabel.BackColor = contentBg;
        statusLabel.ForeColor = fg;
        webView.DefaultBackgroundColor = contentBg;

        ApplyDwmTitleBarTheme(dark);
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
            if (msg == null || !msg.StartsWith("theme|", StringComparison.Ordinal))
            {
                return;
            }

            ApplyThemeFromString(msg[6..]);
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

    private async Task InitAsync()
    {
        try
        {
            var folder = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                "MyridTV",
                "webview2");
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

            SetupThemeSync();

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

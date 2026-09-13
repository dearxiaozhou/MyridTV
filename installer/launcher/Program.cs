using System.Diagnostics;
using System.Text;
using System.Windows.Forms;

namespace MyridTV.Launcher;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        var appDir = AppContext.BaseDirectory;
        var startScript = Path.Combine(appDir, "start_myridtv.ps1");
        if (!File.Exists(startScript))
        {
            MessageBox.Show(
                $"未找到启动脚本：\n{startScript}",
                "MyridTV 启动失败",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
            return 1;
        }

        var argumentList = new List<string>
        {
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            startScript
        };

        foreach (var arg in args)
        {
            if (string.Equals(arg, "--no-desktop", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(arg, "-NoDesktop", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(arg, "/NoDesktop", StringComparison.OrdinalIgnoreCase))
            {
                argumentList.Add("-NoDesktop");
            }
        }

        try
        {
            var process = Process.Start(new ProcessStartInfo
            {
                FileName = "powershell.exe",
                Arguments = JoinArguments(argumentList),
                WorkingDirectory = appDir,
                UseShellExecute = false,
                CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden
            });

            if (process is null)
            {
                throw new InvalidOperationException("启动器未能创建 PowerShell 进程。");
            }

            return 0;
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                $"无法启动 MyridTV。\n\n{ex.Message}",
                "MyridTV 启动失败",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
            return 1;
        }
    }

    private static string JoinArguments(IEnumerable<string> args)
    {
        var builder = new StringBuilder();
        foreach (var arg in args)
        {
            if (builder.Length > 0)
            {
                builder.Append(' ');
            }

            builder.Append(EscapeArgument(arg));
        }

        return builder.ToString();
    }

    private static string EscapeArgument(string value)
    {
        if (string.IsNullOrEmpty(value))
        {
            return "\"\"";
        }

        if (!value.Any(ch => char.IsWhiteSpace(ch) || ch is '"' or '\\'))
        {
            return value;
        }

        var builder = new StringBuilder();
        builder.Append('"');
        var backslashCount = 0;

        foreach (var ch in value)
        {
            if (ch == '\\')
            {
                backslashCount++;
                continue;
            }

            if (ch == '"')
            {
                builder.Append('\\', backslashCount * 2 + 1);
                builder.Append('"');
                backslashCount = 0;
                continue;
            }

            if (backslashCount > 0)
            {
                builder.Append('\\', backslashCount);
                backslashCount = 0;
            }

            builder.Append(ch);
        }

        if (backslashCount > 0)
        {
            builder.Append('\\', backslashCount * 2);
        }

        builder.Append('"');
        return builder.ToString();
    }
}

param(
    [switch]$NoDesktop
)

$ErrorActionPreference = 'Continue'
# Local health checks must never depend on a system proxy process.
$env:NO_PROXY = '127.0.0.1,localhost'
$env:no_proxy = '127.0.0.1,localhost'
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$InternalDir = Join-Path $AppDir '_internal'
$UserDataEnv = 'MYRIDTV_USER_DATA_DIR'
$MigrationBackupRoot = Join-Path $InternalDir 'migration_backups'
$ConfigFile = Join-Path $InternalDir 'data\app_config.json'
$ConfigTemplateFile = Join-Path $InternalDir 'data\app_config.template.json'
$StaticConfigFile = Join-Path $InternalDir 'static\app_config.json'
$ProxyScript = Join-Path $AppDir 'rh_official_proxy.py'
$UpgradeHelperScript = Join-Path $AppDir 'startup_upgrade.ps1'
$AppExe = Join-Path $AppDir 'MyridTV-Desktop.exe'

function Resolve-UserDataRoot() {
    $envValue = [Environment]::GetEnvironmentVariable($UserDataEnv)
    if (![string]::IsNullOrWhiteSpace($envValue)) {
        return [System.IO.Path]::GetFullPath($envValue)
    }
    # 便携模式（多份安装各自独立，仿 ComfyUI 的 user 目录）：
    # 安装目录下存在 user_data\ 或 .portable 标记 → 这份安装用自己的数据目录。
    $portableDir = Join-Path $AppDir 'user_data'
    if ((Test-Path -LiteralPath (Join-Path $AppDir '.portable')) -or (Test-Path -LiteralPath $portableDir -PathType Container)) {
        return $portableDir
    }
    $appData = [Environment]::GetFolderPath('ApplicationData')
    if (![string]::IsNullOrWhiteSpace($appData)) {
        return Join-Path $appData 'MyridTV'
    }
    return Join-Path $AppDir 'user_data'
}

$UserDataRoot = Resolve-UserDataRoot
$script:StartupLog = Join-Path $UserDataRoot 'data\logs\startup.log'

function Read-JsonFile($Path) {
    if (!(Test-Path -LiteralPath $Path)) { return $null }
    try { return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json } catch { return $null }
}

function Resolve-InternalPath($Value, $Fallback) {
    $text = [string]($(if ($Value) { $Value } else { $Fallback }))
    if ([string]::IsNullOrWhiteSpace($text)) { return $null }
    if ([System.IO.Path]::IsPathRooted($text)) { return $text }
    return Join-Path $InternalDir $text
}

function Write-StartupLog($Message) {
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    try {
        $dir = Split-Path -Parent $script:StartupLog
        if ($dir) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
        Add-Content -LiteralPath $script:StartupLog -Encoding UTF8 -Value "[$stamp] $Message"
    } catch {}
}

function Test-ReparsePoint($Path) {
    if (!(Test-Path -LiteralPath $Path)) { return $false }
    try {
        return [bool]((Get-Item -LiteralPath $Path -Force).Attributes -band [System.IO.FileAttributes]::ReparsePoint)
    } catch {
        return $false
    }
}

function Copy-MissingTree($Source, $Target) {
    if (!(Test-Path -LiteralPath $Source)) { return }
    New-Item -ItemType Directory -Force -Path $Target | Out-Null
    Get-ChildItem -LiteralPath $Source -Force -Recurse | ForEach-Object {
        $relative = $_.FullName.Substring($Source.Length).TrimStart('\', '/')
        if ([string]::IsNullOrWhiteSpace($relative)) { return }
        $dest = Join-Path $Target $relative
        if ($_.PSIsContainer) {
            New-Item -ItemType Directory -Force -Path $dest | Out-Null
        } elseif (!(Test-Path -LiteralPath $dest)) {
            $destDir = Split-Path -Parent $dest
            if ($destDir) { New-Item -ItemType Directory -Force -Path $destDir | Out-Null }
            Copy-Item -LiteralPath $_.FullName -Destination $dest -Force
        }
    }
}

function Move-ToMigrationBackup($Path, $Label) {
    if (!(Test-Path -LiteralPath $Path)) { return $null }
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $safeLabel = ($Label -replace '[^A-Za-z0-9_.-]', '_')
    $target = Join-Path $MigrationBackupRoot "$safeLabel`_$stamp"
    New-Item -ItemType Directory -Force -Path $MigrationBackupRoot | Out-Null
    Move-Item -LiteralPath $Path -Destination $target -Force
    return $target
}

function Ensure-DirectoryRedirect($InstallRelative, $UserRelative) {
    $installPath = Join-Path $InternalDir $InstallRelative
    $userPath = Join-Path $UserDataRoot $UserRelative
    New-Item -ItemType Directory -Force -Path $userPath | Out-Null
    if (Test-ReparsePoint $installPath) {
        $existingTarget = [string](Get-Item -LiteralPath $installPath -Force).Target
        try {
            if ([System.IO.Path]::GetFullPath($existingTarget).TrimEnd('\') -ieq [System.IO.Path]::GetFullPath($userPath).TrimEnd('\')) { return }
        } catch {}
        try {
            [System.IO.Directory]::Delete($installPath, $false)
            New-Item -ItemType Junction -Path $installPath -Target $userPath | Out-Null
            Write-StartupLog "directory redirect corrected install=$installPath old_target=$existingTarget user=$userPath"
        } catch {
            Write-StartupLog "directory redirect correction failed install=$installPath old_target=$existingTarget user=$userPath error=$($_.Exception.Message)"
        }
        return
    }

    $backupPath = $null
    if (Test-Path -LiteralPath $installPath) {
        Copy-MissingTree $installPath $userPath
        $backupPath = Move-ToMigrationBackup $installPath $InstallRelative
    }

    try {
        $parent = Split-Path -Parent $installPath
        if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
        New-Item -ItemType Junction -Path $installPath -Target $userPath | Out-Null
    } catch {
        if ($backupPath -and !(Test-Path -LiteralPath $installPath)) {
            Move-Item -LiteralPath $backupPath -Destination $installPath -Force
        }
        Write-StartupLog "directory redirect failed install=$installPath user=$userPath error=$($_.Exception.Message)"
    }
}

function Ensure-FileRedirect($InstallRelative, $UserRelative) {
    $installPath = Join-Path $InternalDir $InstallRelative
    $userPath = Join-Path $UserDataRoot $UserRelative
    if (Test-ReparsePoint $installPath) { return }

    $userParent = Split-Path -Parent $userPath
    if ($userParent) { New-Item -ItemType Directory -Force -Path $userParent | Out-Null }
    if ((Test-Path -LiteralPath $installPath) -and !(Test-Path -LiteralPath $userPath)) {
        Copy-Item -LiteralPath $installPath -Destination $userPath -Force
    }
    if (!(Test-Path -LiteralPath $userPath)) { return }

    $backupPath = $null
    if (Test-Path -LiteralPath $installPath) {
        $backupPath = Move-ToMigrationBackup $installPath $InstallRelative
    }

    try {
        $parent = Split-Path -Parent $installPath
        if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
        New-Item -ItemType SymbolicLink -Path $installPath -Target $userPath | Out-Null
    } catch {
        if (!(Test-Path -LiteralPath $installPath)) {
            Copy-Item -LiteralPath $userPath -Destination $installPath -Force
        }
        Write-StartupLog "file redirect fallback copy install=$installPath user=$userPath error=$($_.Exception.Message)"
    }
}

function Initialize-UserDataLayout() {
    try {
        $defaultHealth = Get-ProxyHealth 'http://127.0.0.1:3107/health'
        $desktopRunning = @(Get-Process | Where-Object { $_.ProcessName -eq 'MyridTV-Desktop' }).Count -gt 0
        if (($defaultHealth -and $defaultHealth.ok) -or (Get-ProxyProcesses).Count -gt 0 -or $desktopRunning) {
            Write-StartupLog "user data migration skipped because MyridTV is already running"
            return
        }
    } catch {}
    New-Item -ItemType Directory -Force -Path $UserDataRoot | Out-Null
    Ensure-DirectoryRedirect 'data' 'data'
    Ensure-DirectoryRedirect 'assets' 'assets'
    Ensure-DirectoryRedirect 'API' 'API'
    Ensure-DirectoryRedirect 'output' 'output'
    Ensure-FileRedirect 'history.json' 'history.json'
}

function Initialize-AppConfig() {
    if (Test-Path -LiteralPath $ConfigFile) { return }
    if (!(Test-Path -LiteralPath $ConfigTemplateFile)) { return }
    try {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ConfigFile) | Out-Null
        Copy-Item -LiteralPath $ConfigTemplateFile -Destination $ConfigFile -Force
        if (Test-Path -LiteralPath (Split-Path -Parent $StaticConfigFile)) {
            Copy-Item -LiteralPath $ConfigTemplateFile -Destination $StaticConfigFile -Force
        }
    } catch {}
}

function Get-ProxyHealth($Url) {
    try { return Invoke-RestMethod -Uri $Url -TimeoutSec 2 } catch { return $null }
}

function Get-ProxyProcesses() {
    return @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -match '^pythonw?\.exe$' -and
        $_.CommandLine -and
        $_.CommandLine -like '*rh_official_proxy.py*' -and
        $_.CommandLine -like "*$ProxyScript*"
    })
}

function Find-PythonExe($Config) {
    $envName = 'WCSTV_PYTHON_EXE'
    if ($Config -and $Config.runtime -and $Config.runtime.python_env) { $envName = [string]$Config.runtime.python_env }
    $envValue = [Environment]::GetEnvironmentVariable($envName)
    if ($envValue -and (Test-Path -LiteralPath $envValue)) { return $envValue }
    if ($Config -and $Config.runtime -and $Config.runtime.python_exe) {
        $cfgPython = [string]$Config.runtime.python_exe
        if ($cfgPython -and (Test-Path -LiteralPath $cfgPython)) { return $cfgPython }
    }
    $localCandidates = @(
        (Join-Path $AppDir 'python\python.exe'),
        (Join-Path $InternalDir 'python\python.exe')
    )
    if ($env:LOCALAPPDATA) {
        $localCandidates += @(
            (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python310\python.exe')
        )
    }
    foreach ($candidate in $localCandidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) { return $candidate }
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) { return $cmd.Source }
    return ''
}

Initialize-UserDataLayout
Initialize-AppConfig
if (Test-Path -LiteralPath $UpgradeHelperScript) {
    try {
        . $UpgradeHelperScript
        $upgradeArtifacts = @(
            $ProxyScript,
            $AppExe,
            (Join-Path $AppDir 'MyridTV.exe'),
            (Join-Path $AppDir 'start_wcstv.ps1'),
            (Join-Path $InternalDir 'static\index.html'),
            (Join-Path $InternalDir 'static\canvas.html'),
            (Join-Path $InternalDir 'static\asset-manager.html'),
            (Join-Path $InternalDir 'static\api-settings.html'),
            (Join-Path $InternalDir 'static\js\canvas.js'),
            (Join-Path $InternalDir 'static\js\smart-canvas.js'),
            (Join-Path $InternalDir 'static\js\asset-manager.js'),
            (Join-Path $InternalDir 'static\js\api-settings.js'),
            (Join-Path $InternalDir 'static\js\canvas-node-registry.js'),
            (Join-Path $InternalDir 'static\js\canvas-draft-store.js'),
            (Join-Path $AppDir 'task_store.py'),
            (Join-Path $AppDir 'myridtv_core.py'),
            (Join-Path $AppDir 'myridtv_http.py'),
            (Join-Path $AppDir 'myridtv_env.py'),
            (Join-Path $AppDir 'myridtv_provider.py'),
            (Join-Path $AppDir 'myridtv_agent.py'),
            (Join-Path $AppDir 'myridtv_canvas_store.py'),
            (Join-Path $AppDir 'myridtv_task_state.py'),
            (Join-Path $AppDir 'myridtv_media_localize.py'),
            (Join-Path $AppDir 'myridtv_libraries.py'),
            (Join-Path $AppDir 'myridtv_codex.py'),
            (Join-Path $AppDir 'myridtv_agent_tools.py'),
            (Join-Path $AppDir 'myridtv_agent_state.py'),
            (Join-Path $AppDir 'myridtv_agent_guard.py'),
            (Join-Path $AppDir 'myridtv_agent_artifact.py'),
            (Join-Path $AppDir 'myridtv_agent_batch.py'),
            (Join-Path $AppDir 'myridtv_agent_short_drama.py'),
            (Join-Path $AppDir 'myridtv_agent_stop.py'),
            (Join-Path $AppDir 'myridtv_agent_generation.py'),
            (Join-Path $AppDir 'myridtv_runninghub_build.py'),
            (Join-Path $AppDir 'myridtv_task_console.py'),
            (Join-Path $AppDir 'myridtv_mcp.py'),
            (Join-Path $AppDir 'myridtv_mcp_contract.py'),
            (Join-Path $AppDir 'myridtv_mcp_client.py'),
            (Join-Path $AppDir 'myridtv_chat.py'),
            (Join-Path $AppDir 'myridtv_asset_resolver.py'),
            (Join-Path $AppDir 'myridtv_rh_taskflow.py'),
            (Join-Path $AppDir 'myridtv_workflow_assets.py'),
            (Join-Path $AppDir 'myridtv_window_fix.py'),
            (Join-Path $AppDir 'myridtv_agent_receipt.py'),
            (Join-Path $AppDir 'myridtv_rh_api.py'),
(Join-Path $AppDir 'myridtv_static_delivery.py'),
            (Join-Path $AppDir 'myridtv_agent_guidance.py'),
            (Join-Path $AppDir 'myridtv_agent_tasks.py'),
            (Join-Path $AppDir 'myridtv_agent_submit.py'),
            (Join-Path $AppDir 'myridtv_blender_previz.py'),
            (Join-Path $AppDir 'myridtv_comfy.py'),
            (Join-Path $AppDir 'myridtv_runninghub.py'),
            (Join-Path $AppDir 'myridtv_rh_catalog.py'),
            (Join-Path $AppDir 'myridtv_volcengine.py'),
            (Join-Path $AppDir 'startup_upgrade.ps1')
        )
        $upgradeResult = Invoke-WcsTvUpgradeSafety -AppDir $AppDir -UserDataRoot $UserDataRoot -ArtifactPaths $upgradeArtifacts
        foreach ($entry in @($upgradeResult.Events)) {
            if ($entry) { Write-StartupLog $entry }
        }
    } catch {
        Write-StartupLog "upgrade safety failed: $($_.Exception.Message)"
    }
} else {
    Write-StartupLog "upgrade helper missing: $UpgradeHelperScript"
}
function Test-PortInUse([string]$HostName, [int]$Port) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $iar = $client.BeginConnect($HostName, $Port, $null, $null)
        $connected = $iar.AsyncWaitHandle.WaitOne(400)
        $ok = ($connected -and $client.Connected)
        $client.Close()
        return $ok
    } catch { return $false }
}

function Test-PortBindable([string]$HostName, [int]$Port) {
    $portProbe = $null
    try {
        $address = [System.Net.Dns]::GetHostAddresses($HostName) | Where-Object { $_.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork } | Select-Object -First 1
        if (!$address) { return $false }
        $portProbe = [System.Net.Sockets.TcpListener]::new($address, $Port)
        $portProbe.ExclusiveAddressUse = $true
        $portProbe.Start()
        return $true
    } catch { return $false }
    finally { if ($portProbe) { $portProbe.Stop() } }
}

function Normalize-PathText($Value) {
    if (!$Value) { return '' }
    return ([string]$Value).TrimEnd([char]92, [char]47).ToLowerInvariant()
}

function Set-ProxyPortInConfig([int]$Port) {
    # 本安装自己换端口时，把端口写回本安装的配置 —— 桌面壳从同一份配置读端口，两边自动一致
    try {
        $json = Read-JsonFile $ConfigFile
        if (!$json -or !$json.proxy) { return }
        $json.proxy.port = $Port
        $json.proxy.base_url = "http://{0}:{1}" -f [string]$json.proxy.host, $Port
        [System.IO.File]::WriteAllText($ConfigFile, ($json | ConvertTo-Json -Depth 12), (New-Object System.Text.UTF8Encoding($false)))
    } catch {
        Write-StartupLog "proxy port write-back failed: $($_.Exception.Message)"
    }
}

$Config = Read-JsonFile $ConfigFile
$ProxyHost = '127.0.0.1'
$ProxyPort = 3107
if ($Config -and $Config.proxy) {
    if ($Config.proxy.host) { $ProxyHost = [string]$Config.proxy.host }
    if ($Config.proxy.port) { $ProxyPort = [int]$Config.proxy.port }
    elseif ($Config.proxy.base_url) {
        try {
            $parsed = [uri]([string]$Config.proxy.base_url)
            $ProxyHost = $parsed.Host
            $ProxyPort = $parsed.Port
        } catch {}
    }
}

# —— 多份安装共存：目标端口上那个后端如果属于「别的安装」，换到本安装自己的空闲端口 ——
$portHealth = Get-ProxyHealth ("http://{0}:{1}/health" -f $ProxyHost, $ProxyPort)
if ($portHealth -and $portHealth.ok) {
    $ownerPath = Normalize-PathText $portHealth.user_data_dir
    $myPath = Normalize-PathText $UserDataRoot
    if ($ownerPath -and $myPath -and $ownerPath -ne $myPath) {
        $shifted = $false
        for ($candidatePort = $ProxyPort + 1; $candidatePort -le $ProxyPort + 20; $candidatePort++) {
            if (Test-PortBindable $ProxyHost $candidatePort) { $ProxyPort = $candidatePort; $shifted = $true; break }
        }
        if ($shifted) {
            Write-StartupLog ("proxy port conflict: port used by another MyridTV install (user_data={0}); this install switches to port {1}" -f $portHealth.user_data_dir, $ProxyPort)
            Set-ProxyPortInConfig $ProxyPort
        } else {
            Write-StartupLog ("proxy port conflict: port used by another MyridTV install (user_data={0}) and no free port in +20; keeping port {0}" -f $portHealth.user_data_dir, $ProxyPort)
        }
    } else {
        Write-StartupLog "proxy on port $ProxyPort belongs to this install (user_data=$($portHealth.user_data_dir))"
    }
}
if (!($portHealth -and $portHealth.ok) -and !(Test-PortBindable $ProxyHost $ProxyPort)) {
    $unavailablePort = $ProxyPort
    for ($candidatePort = $unavailablePort + 1; $candidatePort -le [Math]::Min(65535, $unavailablePort + 100); $candidatePort++) {
        if (Test-PortBindable $ProxyHost $candidatePort) {
            $ProxyPort = $candidatePort
            Set-ProxyPortInConfig $ProxyPort
            Write-StartupLog "proxy port $unavailablePort cannot bind; switched to $ProxyPort"
            break
        }
    }
}
$ProxyBase = "http://{0}:{1}" -f $ProxyHost, $ProxyPort
$ProxyHealthUrl = "$ProxyBase/health"
$script:StartupLog = Resolve-InternalPath $Config.paths.startup_log 'data/logs/startup.log'
$ProxyLog = Resolve-InternalPath $Config.paths.proxy_log 'data/logs/rh_official_proxy.log'
$ProxyStdoutLog = Resolve-InternalPath $Config.paths.proxy_stdout_log 'data/logs/rh_official_proxy.stdout.log'
$ProxyStderrLog = Resolve-InternalPath $Config.paths.proxy_stderr_log 'data/logs/rh_official_proxy.stderr.log'

Write-StartupLog "startup begin app_dir=$AppDir user_data=$UserDataRoot proxy=$ProxyBase"

$DesktopStarted = $false
if (!$NoDesktop) {
    if (Test-Path -LiteralPath $AppExe) {
        Write-StartupLog "desktop launch delayed until proxy check exe=$AppExe"
    } else {
        Write-StartupLog "desktop exe missing: $AppExe"
    }
}

$PythonExe = Find-PythonExe $Config
$health = $null
for ($i = 0; $i -lt 3 -and -not ($health -and $health.ok); $i++) {
    $health = Get-ProxyHealth $ProxyHealthUrl
    if (!($health -and $health.ok)) { Start-Sleep -Milliseconds 300 }
}
if ($health -and $health.ok) {
    Write-StartupLog "proxy already running pid=$($health.pid) version=$($health.version)"
} elseif ($PythonExe) {
    $existingProxyProcesses = Get-ProxyProcesses
    if ($existingProxyProcesses.Count -gt 0) {
        Write-StartupLog "proxy process exists but health failed; stopping stale pids=$($existingProxyProcesses.ProcessId -join ',')"
        foreach ($proc in $existingProxyProcesses) {
            try { Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop } catch { Write-StartupLog "failed to stop stale proxy pid=$($proc.ProcessId): $($_.Exception.Message)" }
        }
        Start-Sleep -Milliseconds 400
    }
    if (!(Test-Path -LiteralPath $ProxyScript)) {
        Write-StartupLog "proxy script missing: $ProxyScript"
    } else {
        $proxyLogDir = Split-Path -Parent $ProxyLog
        if ($proxyLogDir) { New-Item -ItemType Directory -Force -Path $proxyLogDir | Out-Null }
            Write-StartupLog "starting proxy python=$PythonExe script=$ProxyScript"
            try {
                Start-Process -FilePath $PythonExe -ArgumentList @('-B', $ProxyScript) -WorkingDirectory $AppDir -WindowStyle Hidden -RedirectStandardOutput $ProxyStdoutLog -RedirectStandardError $ProxyStderrLog | Out-Null
            $health = $null
            for ($i = 0; $i -lt 10 -and -not ($health -and $health.ok); $i++) {
                Start-Sleep -Milliseconds 500
                $health = Get-ProxyHealth $ProxyHealthUrl
            }
            if ($health -and $health.ok) {
                Write-StartupLog "proxy started pid=$($health.pid) version=$($health.version)"
            } else {
                Write-StartupLog "proxy start attempted but health check failed url=$ProxyHealthUrl"
            }
        } catch {
            Write-StartupLog "proxy start failed: $($_.Exception.Message)"
        }
    }
} else {
    Write-StartupLog "python not found; set WCSTV_PYTHON_EXE or app_config.runtime.python_exe"
}

if (!$NoDesktop -and -not $DesktopStarted) {
    if (Test-Path -LiteralPath $AppExe) {
        Write-StartupLog "starting desktop exe=$AppExe"
        Start-Process -FilePath $AppExe -WorkingDirectory $AppDir | Out-Null
    } else {
        Write-StartupLog "desktop exe missing: $AppExe"
    }
}

# The release updater runs separately from the proxy. A file lock prevents
# duplicate watchers when the launcher is opened more than once. Source checkouts
# are never updated automatically, so local development edits stay intact.
# 2026-10-06：发布版的默认更新通道。原先要求用户自己设 MYRIDTV_UPDATE_FEED_URL
# 才启动，导致条件永假、更新器永不运行；现在给出默认值，需要时仍可用环境变量覆盖
# （置空字符串可显式关闭自动更新）。
$DefaultUpdateFeed = 'https://github.com/dearxiaozhou/MyridTV-updates/releases/latest/download/update-manifest.json'
$UpdaterScript = Join-Path $AppDir 'myridtv_updater.py'
$UpdateKey = Join-Path $AppDir 'update-public-key.pub'
if (!$env:MYRIDTV_UPDATE_FEED_URL) { $env:MYRIDTV_UPDATE_FEED_URL = $DefaultUpdateFeed }
if (!$NoDesktop -and $env:MYRIDTV_UPDATE_FEED_URL -and $PythonExe -and (Test-Path -LiteralPath $UpdaterScript) -and (Test-Path -LiteralPath $UpdateKey) -and -not (Test-Path -LiteralPath (Join-Path $AppDir '.git'))) {
    try {
        $updateLogDir = Join-Path $UserDataRoot 'data\logs'
        New-Item -ItemType Directory -Force -Path $updateLogDir | Out-Null
        Start-Process -FilePath $PythonExe -ArgumentList @('-B', $UpdaterScript, '--watch') -WorkingDirectory $AppDir -WindowStyle Hidden -RedirectStandardOutput (Join-Path $updateLogDir 'updater.out.log') -RedirectStandardError (Join-Path $updateLogDir 'updater.err.log') | Out-Null
        Write-StartupLog 'update watcher launched'
    } catch {
        Write-StartupLog "update watcher failed: $($_.Exception.Message)"
    }
}

Write-StartupLog "startup end"

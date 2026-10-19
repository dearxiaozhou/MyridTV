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
    # 本安装自己换端口时，把端口写回本安装的配置 —— 桌面壳从同一份配置读端口，两边自动一致。
    # 发版有两道隐私门控：prepare-release.ps1 既跳过打包 _internal\data\app_config.json，又把它列进
    # forbiddenFileNames 巡检（初衷是防止本机 API key/绝对路径随包外泄，合理）。副作用是**全新安装
    # 必然没有这份配置**，原逻辑会被下面的判空静默拦掉 —— 端口写不回去、也不记日志，多份安装共存时
    # 就会一起抢 3107，proxy 健康检查永远失败，桌面壳连到别人家的后端上，于是「打开 A 却读到 B 的资产」。
    # 这里改用随包的 app_config.template.json 兜底生成（模板只有结构性内容、无密钥），让写回始终生效。
    try {
        $json = Read-JsonFile $ConfigFile
        # 用字符串记录兜底来源。不要用布尔：$true -eq 'minimal' 会把右侧字符串转成 Boolean 而成立，日志会张冠李戴。
        $bootstrapMode = 'none'
        if (!$json) {
            $json = Read-JsonFile $ConfigTemplateFile
            if ($json) { $bootstrapMode = 'template' }
        }
        if (!$json -or !$json.proxy) {
            # 模板也不在（老版本安装普遍没有它）时，退化为「只含 proxy 段」的极简配置。
            # 这是安全的：后端 load_app_config() 走 deep_merge(DEFAULT_CONFIG, 文件)，
            # 其余段落（paths/runtime/user_data/setup/agent…）会由默认值自动补齐。
            $json = [ordered]@{ proxy = [ordered]@{ host = '127.0.0.1'; port = 3107; base_url = 'http://127.0.0.1:3107' } }
            $bootstrapMode = 'minimal'
        }
        $cfgHost = if ($json.proxy.host) { [string]$json.proxy.host } else { '127.0.0.1' }
        $json.proxy.host = $cfgHost
        $json.proxy.port = $Port
        $json.proxy.base_url = "http://{0}:{1}" -f $cfgHost, $Port
        $configDir = Split-Path -Parent $ConfigFile
        if ($configDir -and !(Test-Path -LiteralPath $configDir)) {
            New-Item -ItemType Directory -Path $configDir -Force | Out-Null
        }
        [System.IO.File]::WriteAllText($ConfigFile, ($json | ConvertTo-Json -Depth 12), (New-Object System.Text.UTF8Encoding($false)))
        if ($bootstrapMode -eq 'minimal') {
            Write-StartupLog ("proxy port write-back bootstrapped app_config.json (proxy-only, template absent); port={0}" -f $Port)
        } elseif ($bootstrapMode -eq 'template') {
            Write-StartupLog ("proxy port write-back bootstrapped app_config.json from template; port={0}" -f $Port)
        }
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

# —— 多份安装共存：目标端口上那个后端只有确认属于「本安装」才直连 ——
# 认不出归属（外来服务 / 老版本没有 user_data_dir 字段）时也必须换端口：
# 直连别人的后端 = 读到别人的画布/资产/模型，正是「打开 A 却看到 B 的数据」。
$portHealth = Get-ProxyHealth ("http://{0}:{1}/health" -f $ProxyHost, $ProxyPort)
if ($portHealth -and $portHealth.ok) {
    $ownerPath = Normalize-PathText $portHealth.user_data_dir
    $myPath = Normalize-PathText $UserDataRoot
    if ($ownerPath -and $myPath -and $ownerPath -eq $myPath) {
        Write-StartupLog "proxy on port $ProxyPort belongs to this install (user_data=$($portHealth.user_data_dir))"
    } else {
        $who = if ($portHealth.user_data_dir) { "user_data=$($portHealth.user_data_dir)" } else { "unidentified service" }
        $shifted = $false
        for ($candidatePort = $ProxyPort + 1; $candidatePort -le $ProxyPort + 20; $candidatePort++) {
            if (Test-PortBindable $ProxyHost $candidatePort) { $ProxyPort = $candidatePort; $shifted = $true; break }
        }
        if ($shifted) {
            Write-StartupLog ("proxy port occupied by another MyridTV install ({0}); this install switches to port {1}" -f $who, $ProxyPort)
            Set-ProxyPortInConfig $ProxyPort
        } else {
            Write-StartupLog ("proxy port occupied by another MyridTV install ({0}) and no free port in +20; keeping port {1}" -f $who, $ProxyPort)
        }
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
# —— 复用已有 proxy 前，先核对它实际生效的资产目录 ——
# ASSETS_DIR 是 proxy 进程 import 期定值（改配置热切不可靠）。若用户在设置页改过
# 资产目录后只重启了前端，旧 proxy 还活着 → 新目录永远不生效，设置页的
# 「已保存为 X，重启后生效」提示会一直挂着（实测重启两次依旧）。
# 认出不匹配就重启 proxy，让新配置真正生效。
$ProxyNeedsStart = $false
if ($health -and $health.ok) {
    $expectedAssets = [string]$env:MYRIDTV_ASSETS_DIR
    if (!$expectedAssets -and $Config -and $Config.paths -and $Config.paths.assets_dir) { $expectedAssets = [string]$Config.paths.assets_dir }
    if (!$expectedAssets) { $expectedAssets = Join-Path $AppDir 'assets' }
    $runningAssets = ''
    try {
        $assetsState = Invoke-RestMethod -Uri ("$ProxyBase/api/assets-root") -TimeoutSec 5 -ErrorAction Stop
        $runningAssets = [string]$assetsState.assets_dir
    } catch {
        # 老版本 proxy 没有这个端点 → 探不到就当匹配，保持原行为（复用）
        Write-StartupLog "proxy assets probe failed: $($_.Exception.Message)"
    }
    if ($runningAssets -and (Normalize-PathText $runningAssets) -ne (Normalize-PathText $expectedAssets)) {
        Write-StartupLog "proxy assets dir mismatch (running=$runningAssets expected=$expectedAssets); restarting proxy so the new assets dir takes effect"
        try { Stop-Process -Id $health.pid -Force -ErrorAction Stop } catch { Write-StartupLog "failed to stop proxy pid=$($health.pid): $($_.Exception.Message)" }
        Start-Sleep -Milliseconds 400
        $ProxyNeedsStart = $true
    } else {
        Write-StartupLog "proxy already running pid=$($health.pid) version=$($health.version)"
    }
} else {
    $ProxyNeedsStart = $true
}
if ($ProxyNeedsStart -and $PythonExe) {
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

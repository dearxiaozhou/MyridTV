param(
    [string]$SourceDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [string]$StageDir = (Join-Path $PSScriptRoot 'build\MyridTV'),
    [string]$PythonDir = '',
    [switch]$Sign,
    [string]$SignToolPath = '',
    [string]$SignCertPath = '',
    [string]$SignCertPassword = '',
    [string]$SignCertPasswordEnv = 'MYRIDTV_SIGN_CERT_PASSWORD',
    [string]$SignCertThumbprint = '',
    [ValidateSet('CurrentUser', 'LocalMachine')]
    [string]$SignCertStoreLocation = 'CurrentUser',
    [string]$SignTimestampUrl = 'http://timestamp.digicert.com'
)

$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'signing.ps1')

function Resolve-ActualPythonDir {
    param([string]$RequestedDir, [string]$AppSourceDir)

    if ($RequestedDir) {
        $candidate = [System.IO.Path]::GetFullPath($RequestedDir)
        if (Test-Path -LiteralPath (Join-Path $candidate 'python.exe')) {
            return $candidate
        }
        throw "Invalid Python directory: $candidate"
    }

    $candidates = @()
    $candidates += Join-Path $AppSourceDir 'python'
    if ($env:LOCALAPPDATA) {
        $candidates += Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313'
        $candidates += Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312'
        $candidates += Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311'
        $candidates += Join-Path $env:LOCALAPPDATA 'Programs\Python\Python310'
    }

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath (Join-Path $candidate 'python.exe'))) {
            return [System.IO.Path]::GetFullPath($candidate)
        }
    }

    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd -and $pythonCmd.Source) {
        $pythonExe = & $pythonCmd.Source -c "import pathlib,sys; print(pathlib.Path(sys.executable).resolve())" 2>$null
        if ($LASTEXITCODE -eq 0 -and $pythonExe) {
            $candidate = Split-Path -Parent $pythonExe.Trim()
            if (Test-Path -LiteralPath (Join-Path $candidate 'python.exe')) {
                return [System.IO.Path]::GetFullPath($candidate)
            }
        }
    }

    throw 'No Python runtime found. Use -PythonDir to point to a directory containing python.exe.'
}

function Remove-IfExists {
    param([string]$Path)
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

function Get-RelativePathCompat {
    param([string]$BasePath, [string]$ChildPath)

    $base = [System.IO.Path]::GetFullPath($BasePath).TrimEnd('\', '/')
    $child = [System.IO.Path]::GetFullPath($ChildPath)
    if ($child.StartsWith($base, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $child.Substring($base.Length).TrimStart('\', '/')
    }
    return $child
}

function Should-SkipRelativePath {
    param([string]$RelativePath, [switch]$AppRoot)

    $sep = [string][char]92
    $normalized = ($RelativePath -replace '/', $sep).TrimStart([char]92)
    if ([string]::IsNullOrWhiteSpace($normalized)) { return $false }

    $prefixes = @(
        'assets',
        '_internal\API',
        '_internal\assets',
        '_internal\data',
        '_internal\output',
        '_internal\backup-ui-compact-20260904',
        '_internal\_internal',
        '_internal\API',
        'installer',
        'installer\build',
        'internal',
        'test-results',
        '__pycache__',
        'tests',
        '_test_userdata',
        'MyridTV',
        '.git',
        '.githooks',
        '.gitignore',
        '.gitattributes'
    )

    foreach ($prefix in $prefixes) {
        if ($normalized.Equals($prefix, [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
        if ($normalized.StartsWith($prefix + $sep, [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    }

    # AGENTS.md 规则2：发布包禁带备份/日志（全树 .bak* / *.log 一律跳过）
    $fileName = [System.IO.Path]::GetFileName($normalized)
    if ($fileName -match '(?i)\.bak') { return $true }
    if ($fileName -match '(?i)\.log$') { return $true }

    # 根级开发/临时遗留不进包：下划线开头（_internal 除外）、gate_restart*、canvas_*.json、根级 png
    # 只在应用树根（-AppRoot）判定——bundled Python 的 DLLs 目录拷贝时相对路径是纯文件名，不能当根级判
    if ($AppRoot -and ($normalized -notmatch [regex]::Escape($sep))) {
        if (-not $fileName.Equals('_internal', [System.StringComparison]::OrdinalIgnoreCase) -and $fileName.StartsWith('_')) { return $true }
        if ($fileName -match '(?i)^gate_restart') { return $true }
        if ($fileName -match '(?i)^canvas_.*\.json$') { return $true }
        if ($fileName -match '(?i)\.png$') { return $true }
    }

    if ($normalized.Equals('_internal\history.json', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    if ($normalized.Equals('_internal\fix_window_style.py', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
if ($normalized.Equals('_internal\fix_launcher.py', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
if ($normalized.StartsWith('_internal\启动', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
if ($normalized.StartsWith('_internal\static\images\wcstv-', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
if ($normalized.Equals('_internal\data\app_config.json', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
if ($normalized.Equals('_internal\static\app_config.json', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
if ($normalized.StartsWith('_internal' + $sep, [System.StringComparison]::OrdinalIgnoreCase)) {
    $internalFileName = [System.IO.Path]::GetFileName($normalized)
    $internalExtension = [System.IO.Path]::GetExtension($normalized)
    if ($internalExtension -in @('.dll', '.pyd', '.cat')) { return $true }
    if ($internalFileName.Equals('base_library.zip', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
}
    if ($normalized.IndexOf($sep) -lt 0 -and $normalized.EndsWith('.txt', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    if ($normalized.Equals('MyridTV-Desktop-core.exe', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    if ($normalized.Equals('MyridTV-Desktop.wsf', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    if ($normalized.Equals('_auto_fix_launcher.py', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    if ($normalized.Equals('_fix.ps1', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    if ($normalized.Equals('_launcher.cs', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    if ($normalized.Equals('MyridTV-Desktop.exe', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    if ($normalized.Equals('api-settings-runninghub-autotest.png', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    if ($normalized.StartsWith('verification-', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    if ($normalized.Equals('MyridTV-Desktop.pdb', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    if ($normalized.StartsWith('run_style_', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    if ($normalized.StartsWith('run_yj_', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    if ($normalized.StartsWith('style_', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    if ($normalized -like 'Microsoft.Web.WebView2*.xml') { return $true }
    if ($normalized.EndsWith('.cmd', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    if ($normalized.EndsWith('.bat', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    if ($normalized.EndsWith('.vbs', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    if ($normalized.EndsWith('.wsf', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    if ($normalized.EndsWith('.ps1', [System.StringComparison]::OrdinalIgnoreCase) -and
        -not $normalized.Equals('start_myridtv.ps1', [System.StringComparison]::OrdinalIgnoreCase) -and
        -not $normalized.Equals('startup_upgrade.ps1', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    # *.new 是本地改前对照副本，不是应用文件，绝不能进发布包
    if ($normalized.EndsWith('.new', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    if ($normalized.EndsWith('.pyc', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    if ($normalized.EndsWith('.pyo', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    if ($normalized.EndsWith('.log', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    if ($normalized.EndsWith('.tmp', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    if ($normalized.EndsWith('.bak', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    if ($normalized.IndexOf('.bak_', [System.StringComparison]::OrdinalIgnoreCase) -ge 0) { return $true }
    if ($normalized.IndexOf('_bak_', [System.StringComparison]::OrdinalIgnoreCase) -ge 0) { return $true }
    if ($normalized.IndexOf('.disabled-', [System.StringComparison]::OrdinalIgnoreCase) -ge 0) { return $true }
    if ($normalized.EndsWith('.env', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    return $false
}

function Copy-FilteredTree {
    param(
        [string]$RootDir,
        [string]$CurrentSource,
        [string]$CurrentDest,
        [switch]$AppRoot
    )

    New-Item -ItemType Directory -Force -Path $CurrentDest | Out-Null

    foreach ($item in Get-ChildItem -LiteralPath $CurrentSource -Force) {
        $relative = Get-RelativePathCompat -BasePath $RootDir -ChildPath $item.FullName
        if (Should-SkipRelativePath $relative -AppRoot:$AppRoot) { continue }
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { continue }

        $targetPath = Join-Path $CurrentDest $item.Name
        if ($item.PSIsContainer) {
            Copy-FilteredTree -RootDir $RootDir -CurrentSource $item.FullName -CurrentDest $targetPath -AppRoot:$AppRoot
        } else {
            $parent = Split-Path -Parent $targetPath
            if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
            Copy-Item -LiteralPath $item.FullName -Destination $targetPath -Force
        }
    }
}

function Should-SkipPythonLibRelativePath {
    param([string]$RelativePath)

    $sep = [string][char]92
    $normalized = ($RelativePath -replace '/', $sep).TrimStart([char]92)
    if ([string]::IsNullOrWhiteSpace($normalized)) { return $false }

    $prefixes = @(
        '__pycache__',
        '__phello__',
        '_pyrepl',
        'ensurepip',
        'idlelib',
        'site-packages',
        'test',
        'tkinter',
        'turtledemo',
        'venv'
    )

    foreach ($prefix in $prefixes) {
        if ($normalized.Equals($prefix, [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
        if ($normalized.StartsWith($prefix + $sep, [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    }

    if ($normalized.EndsWith('.pyc', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    if ($normalized.EndsWith('.pyo', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    if ($normalized.EndsWith('.bat', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    return $false
}

function Copy-PythonLibMinimal {
    param(
        [string]$LibSource,
        [string]$LibDest,
        [string]$CurrentSource = $LibSource
    )

    New-Item -ItemType Directory -Force -Path $LibDest | Out-Null

    foreach ($item in Get-ChildItem -LiteralPath $CurrentSource -Force) {
        $relative = Get-RelativePathCompat -BasePath $LibSource -ChildPath $item.FullName
        if (Should-SkipPythonLibRelativePath $relative) { continue }
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { continue }

        $target = Join-Path $LibDest $item.Name
        if ($item.PSIsContainer) {
            Copy-PythonLibMinimal -LibSource $LibSource -LibDest $target -CurrentSource $item.FullName
        } else {
            $parent = Split-Path -Parent $target
            if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
            Copy-Item -LiteralPath $item.FullName -Destination $target -Force
        }
    }
}

function Copy-PythonRuntime {
    param([string]$RuntimeSource, [string]$RuntimeDest)

    Write-Host "Bundling Python runtime from: $RuntimeSource"
    Remove-IfExists $RuntimeDest
    New-Item -ItemType Directory -Force -Path $RuntimeDest | Out-Null

    foreach ($name in @('python.exe', 'pythonw.exe', 'python3.dll', 'python313.dll', 'vcruntime140.dll', 'vcruntime140_1.dll', 'LICENSE.txt')) {
        $sourcePath = Join-Path $RuntimeSource $name
        if (Test-Path -LiteralPath $sourcePath) {
            Copy-Item -LiteralPath $sourcePath -Destination (Join-Path $RuntimeDest $name) -Force
        }
    }

    $dllSource = Join-Path $RuntimeSource 'DLLs'
    if (Test-Path -LiteralPath $dllSource) {
        Copy-FilteredTree -RootDir $dllSource -CurrentSource $dllSource -CurrentDest (Join-Path $RuntimeDest 'DLLs')
    }

    $libSource = Join-Path $RuntimeSource 'Lib'
    if (Test-Path -LiteralPath $libSource) {
        Copy-PythonLibMinimal -LibSource $libSource -LibDest (Join-Path $RuntimeDest 'Lib')
    }
}

function Install-PythonRuntimePackage {
    param(
        [string]$RuntimeSource,
        [string]$RuntimeDest,
        [string[]]$Packages
    )

    $sourcePython = Join-Path $RuntimeSource 'python.exe'
    if (!(Test-Path -LiteralPath $sourcePython)) {
        throw "Source python.exe not found: $sourcePython"
    }

    $sitePackages = Join-Path $RuntimeDest 'Lib\site-packages'
    New-Item -ItemType Directory -Force -Path $sitePackages | Out-Null

    foreach ($package in $Packages) {
        Write-Host "Installing bundled Python package: $package"
        & $sourcePython -m pip install --upgrade --no-cache-dir --no-compile --target $sitePackages $package
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install bundled Python package: $package"
        }
    }
}

function Remove-StageSensitiveFiles {
    param([string]$TargetStageDir)

    foreach ($relativePath in @(
        '_internal\API',
        '_internal\data',
        '_internal\output',
        '_internal\history.json',
        '_internal\static\app_config.json',
        'installer-build.json'
    )) {
        Remove-IfExists (Join-Path $TargetStageDir $relativePath)
    }

    Get-ChildItem -LiteralPath $TargetStageDir -Force -File -Filter '*.txt' -ErrorAction SilentlyContinue |
        Remove-Item -Force
}

function Initialize-StageRuntimeState {
    param([string]$TargetStageDir)

    foreach ($relativePath in @(
        '_internal\API',
        '_internal\assets',
        '_internal\data',
        '_internal\output',
        '_internal\data\logs'
    )) {
        New-Item -ItemType Directory -Force -Path (Join-Path $TargetStageDir $relativePath) | Out-Null
    }

    Set-Content -LiteralPath (Join-Path $TargetStageDir '_internal\history.json') -Value '' -Encoding UTF8
}

function Remove-StageAuthorTraces {
    param([string]$TargetStageDir)

    # 发布包不许带构建机信息：pip 装包与 import 生成的字节码缓存(.pyc)、console script(.exe)
    # 会把构建机路径（C:\Users\<用户名>\AppData\Local\Temp\pip-target-...）写进二进制。
    $pythonDir = Join-Path $TargetStageDir 'python'
    if (Test-Path -LiteralPath $pythonDir) {
        Get-ChildItem -LiteralPath $pythonDir -Recurse -Force -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -eq '__pycache__' } |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        foreach ($pattern in @('*.pyc', '*.pyo')) {
            Get-ChildItem -LiteralPath $pythonDir -Recurse -Force -File -Filter $pattern -ErrorAction SilentlyContinue |
                Remove-Item -Force -ErrorAction SilentlyContinue
        }
    }
    foreach ($relative in @('python\Lib\site-packages\bin', 'python\Scripts')) {
        $traceDir = Join-Path $TargetStageDir $relative
        if (Test-Path -LiteralPath $traceDir) { Remove-IfExists $traceDir }
    }
}

function Test-FileContainsAnyNeedle {
    param([string]$Path, [string[]]$Needles)

    # 一律用「子串匹配」，不要用 Select-String 正则：
    # 源码/JSON 里的反斜杠是转义后的双反斜杠（D:\\APP\\...），
    # 正则 'D:\\APP\\...' 只匹配单反斜杠文本，会导致硬编码路径全部漏网。
    try {
        $text = [System.IO.File]::ReadAllText($Path)
    } catch {
        return $null
    }

    foreach ($needle in $Needles) {
        if ($text.IndexOf($needle, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) { return $needle }
        $escaped = $needle.Replace('\', '\\')
        if ($text.IndexOf($escaped, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) { return $escaped }
    }
    return $null
}

function Assert-ReleasePrivacy {
    param([string]$TargetStageDir)

    $forbiddenRelativePaths = @(
        '_internal\API\.env',
        '_internal\data\app_config.json',
        '_internal\data\app_config.json.bak',
        '_internal\data\api_providers.json',
        '_internal\data\asset_library.json',
        '_internal\data\canvas_tasks.json',
        '_internal\data\codex_bridge_sessions.json',
        '_internal\data\user_model_prefs.json'
    )

    foreach ($relativePath in $forbiddenRelativePaths) {
        $path = Join-Path $TargetStageDir $relativePath
        if (Test-Path -LiteralPath $path) {
            throw "Release privacy check failed: forbidden file present: $relativePath"
        }
    }

    $forbiddenDirs = @(
        '_internal\data\agent_batches',
        '_internal\data\canvas_agent_history',
        '_internal\data\canvas_agent_skills',
        '_internal\data\canvas_backups',
        '_internal\data\canvases',
        '_internal\data\cleanup_backups',
        '_internal\data\codex_bridge',
        '_internal\data\conversations',
        '_internal\data\desktop_backups',
        '_internal\data\manual_backups',
        '_internal\data\modlens_cache',
        '_internal\data\recovery_backups',
        '_internal\data\rollback_before_restore_20260627-021446',
        '_internal\data\upgrade_backups',
        '_internal\data\vision_cache'
    )

    foreach ($relativeDir in $forbiddenDirs) {
        $path = Join-Path $TargetStageDir $relativeDir
        if (Test-Path -LiteralPath $path) {
            throw "Release privacy check failed: forbidden runtime directory present: $relativeDir"
        }
    }

    $forbiddenFileNames = @('.env', 'app_config.json', 'app_config.json.bak')
    $badFile = Get-ChildItem -LiteralPath $TargetStageDir -Recurse -Force -File |
        Where-Object {
            $relative = Get-RelativePathCompat -BasePath $TargetStageDir -ChildPath $_.FullName
            $relative = ($relative -replace '/', '\')
            if ($relative.StartsWith('python\', [System.StringComparison]::OrdinalIgnoreCase)) { return $false }
            if ($relative.StartsWith('_internal\static\vendor\', [System.StringComparison]::OrdinalIgnoreCase)) { return $false }
            return $_.Name -in $forbiddenFileNames
        } |
        Select-Object -First 1
    if ($badFile) {
        throw "Release privacy check failed: sensitive file name present: $(Get-RelativePathCompat -BasePath $TargetStageDir -ChildPath $badFile.FullName)"
    }

    $contentNeedles = @(
        'C:\Users\<user>',
        'D:\APP\MyridTV'
    )

    $scanFiles = Get-ChildItem -LiteralPath $TargetStageDir -Recurse -Force -File |
        Where-Object {
            $relative = Get-RelativePathCompat -BasePath $TargetStageDir -ChildPath $_.FullName
            $relative = ($relative -replace '/', '\')
            if ($relative.StartsWith('python\', [System.StringComparison]::OrdinalIgnoreCase)) { return $false }
            if ($relative.StartsWith('_internal\static\vendor\', [System.StringComparison]::OrdinalIgnoreCase)) { return $false }
            return $_.Extension -in @('.json', '.txt', '.md', '.html', '.js', '.css', '.ps1', '.py', '.xml', '.config')
        }

    # 硬门禁：任何文件（含二进制、含 bundled Python）都不许出现构建机用户目录 C:\Users\<name>
    $authorNeedles = @('C:\Users\')
    foreach ($file in (Get-ChildItem -LiteralPath $TargetStageDir -Recurse -Force -File -ErrorAction SilentlyContinue |
                       Where-Object { $_.Length -lt 50MB })) {
        $hit = Test-FileContainsAnyNeedle -Path $file.FullName -Needles $authorNeedles
        if ($hit) {
            throw "Release privacy check failed: build-machine user path '$hit' found in $(Get-RelativePathCompat -BasePath $TargetStageDir -ChildPath $file.FullName)"
        }
    }

    foreach ($file in $scanFiles) {
        $hit = Test-FileContainsAnyNeedle -Path $file.FullName -Needles $contentNeedles
        if ($hit) {
            throw "Release privacy check failed: sensitive content '$hit' matched in $(Get-RelativePathCompat -BasePath $TargetStageDir -ChildPath $file.FullName)"
        }
    }
}

function Remove-StageLegacySensitiveFiles {
    param([string]$TargetStageDir)

    Remove-IfExists (Join-Path $TargetStageDir '_internal\static\app_config.json')
    Remove-IfExists (Join-Path $TargetStageDir 'installer-build.json')
    Get-ChildItem -LiteralPath $TargetStageDir -Force -File -Filter '*.txt' -ErrorAction SilentlyContinue |
        Remove-Item -Force
}

function Sanitize-RunningHubCatalog {
param([string]$TargetStageDir)

$catalogPath = Join-Path $TargetStageDir '_internal\static\runninghub\api_providers.json'
$json = @"
[
  {
    "id": "modelscope",
    "name": "ModelScope",
    "base_url": "https://api-inference.modelscope.cn/v1",
    "protocol": "openai",
    "image_generation_endpoint": "",
    "image_edit_endpoint": "",
    "enabled": true,
    "primary": false,
    "image_models": [],
    "chat_models": [],
    "video_models": [],
    "model_display_names": {},
    "model_protocols": {},
    "ms_loras": [],
    "ms_defaults_version": 3
  },
{
"id": "runninghub",
"name": "RunningHub",
    "base_url": "https://www.runninghub.ai",
    "protocol": "runninghub",
    "image_generation_endpoint": "",
    "image_edit_endpoint": "",
    "enabled": true,
    "primary": false,
    "image_models": [
      "seedream-v5-lite/text-to-image",
      "seedream-v5-lite/image-to-image",
      "rhart-image-g-2-official/text-to-image",
      "rhart-image-g-2-official/image-to-image",
      "rhart-image-n-pro-official/edit"
    ],
    "chat_models": [],
    "video_models": [],
    "ms_loras": [],
    "ms_defaults_version": 0,
"rh_apps": [],
"rh_workflows": []
  },
  {
    "id": "volcengine",
    "name": "火山引擎",
    "base_url": "https://ark.cn-beijing.volces.com/api/v3",
    "protocol": "volcengine",
    "image_generation_endpoint": "",
    "image_edit_endpoint": "",
    "enabled": true,
    "primary": false,
    "image_models": [
      "doubao-seedream-3-0-t2i-250415",
      "doubao-seedream-4-0-250828",
      "doubao-seedream-4-5-251128",
      "doubao-seedream-5-0-260128"
    ],
    "chat_models": [],
    "video_models": [
      "doubao-seedance-1-0-lite-i2v-250428",
      "doubao-seedance-1-0-lite-t2v-250428",
      "doubao-seedance-1-0-pro-250528",
      "doubao-seedance-1-0-pro-fast-251015",
      "doubao-seedance-1-5-pro-251215",
      "doubao-seedance-2-0-260128",
      "doubao-seedance-2-0-fast-260128",
      "doubao-seedance-2-0-mini-260615"
    ],
    "model_display_names": {},
    "model_protocols": {},
    "ms_loras": [],
    "ms_defaults_version": 0,
    "volcengine_region": "",
    "volcengine_project_name": ""
}
]
"@
    Set-Content -LiteralPath $catalogPath -Value $json -Encoding UTF8
}

function Test-StagedPythonRuntime {
    param([string]$TargetStageDir)

    $pythonExe = Join-Path $TargetStageDir 'python\python.exe'
    if (!(Test-Path -LiteralPath $pythonExe)) {
        throw "Staged python.exe not found: $pythonExe"
    }

    # 冒烟测试会 import websockets → 默认会写 __pycache__，字节码里会内嵌构建机路径，故禁写
    $previousNoBytecode = $env:PYTHONDONTWRITEBYTECODE
    $env:PYTHONDONTWRITEBYTECODE = '1'
    try {
        & $pythonExe -B -c "import base64,json,mimetypes,os,re,threading,time,uuid,urllib.request,urllib.parse,urllib.error,http.server,pathlib,websockets; print('ok')"
        if ($LASTEXITCODE -ne 0) {
            throw 'Staged Python runtime smoke test failed.'
        }
    } finally {
        if ($null -eq $previousNoBytecode) { Remove-Item Env:PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue }
        else { $env:PYTHONDONTWRITEBYTECODE = $previousNoBytecode }
    }
}

function Build-Launcher {
    param(
        [string]$ProjectFile,
        [string]$StageDest
    )

    if (!(Test-Path -LiteralPath $ProjectFile)) {
        throw "Launcher project not found: $ProjectFile"
    }

    $dotnet = (Get-Command dotnet -ErrorAction SilentlyContinue).Source
    if (-not $dotnet) {
        throw 'dotnet CLI not found. Install .NET SDK 9 first, then run packaging again.'
    }

    $publishDir = Join-Path $PSScriptRoot 'build\launcher-publish'
    Remove-IfExists $publishDir
    New-Item -ItemType Directory -Force -Path $publishDir | Out-Null

    & $dotnet publish $ProjectFile `
        -c Release `
        -r win-x64 `
        --self-contained true `
        -o $publishDir `
        /p:PublishSingleFile=true `
        /p:EnableCompressionInSingleFile=true `
        /p:PublishTrimmed=false `
        /p:IncludeNativeLibrariesForSelfExtract=true `
        /nologo

    if ($LASTEXITCODE -ne 0) {
        throw "dotnet publish failed for launcher project: $ProjectFile"
    }

    $launcherExe = Join-Path $publishDir 'MyridTV.exe'
    if (!(Test-Path -LiteralPath $launcherExe)) {
        throw "Launcher build did not produce MyridTV.exe: $launcherExe"
    }

    Copy-Item -LiteralPath $launcherExe -Destination $StageDest -Force
}

function Build-DesktopHost {
    param(
        [string]$ProjectFile,
        [string]$StageDest
    )

    if (!(Test-Path -LiteralPath $ProjectFile)) {
        throw "Desktop project not found: $ProjectFile"
    }

    $dotnet = (Get-Command dotnet -ErrorAction SilentlyContinue).Source
    if (-not $dotnet) {
        throw 'dotnet CLI not found. Install .NET SDK 9 first, then run packaging again.'
    }

    $publishDir = Join-Path $PSScriptRoot 'build\desktop-publish'
    Remove-IfExists $publishDir
    New-Item -ItemType Directory -Force -Path $publishDir | Out-Null

    & $dotnet publish $ProjectFile `
        -c Release `
        -r win-x64 `
        --self-contained true `
        -o $publishDir `
        /p:PublishSingleFile=true `
        /p:EnableCompressionInSingleFile=true `
        /p:PublishTrimmed=false `
        /p:IncludeNativeLibrariesForSelfExtract=true `
        /nologo

    if ($LASTEXITCODE -ne 0) {
        throw "dotnet publish failed for desktop project: $ProjectFile"
    }

    $desktopExe = Join-Path $publishDir 'MyridTV-Desktop.exe'
    if (!(Test-Path -LiteralPath $desktopExe)) {
        throw "Desktop build did not produce MyridTV-Desktop.exe: $desktopExe"
    }

    Copy-Item -LiteralPath $desktopExe -Destination $StageDest -Force
}

# ── 源 / 快照 说明（消除 _internal/installer 副本混淆，见 installer/COPIES.md）──
# $SourceDir = 项目根（开发者手改的源，含 _internal/ 运行时文件）
# $StageDir  = installer/build/MyridTV/（本脚本生成的打包快照，会被整目录清空+重建，切勿手改）
# 开发者只改 _internal/ 等源文件；本步骤后 installer/build/ 会被完全覆盖刷新。
$SourceDir = [System.IO.Path]::GetFullPath($SourceDir)
$StageDir = [System.IO.Path]::GetFullPath($StageDir)
$PythonDir = Resolve-ActualPythonDir -RequestedDir $PythonDir -AppSourceDir $SourceDir

Write-Host "SourceDir : $SourceDir"
Write-Host "StageDir  : $StageDir"
Write-Host "PythonDir : $PythonDir"

Remove-IfExists $StageDir
New-Item -ItemType Directory -Force -Path $StageDir | Out-Null

Copy-FilteredTree -RootDir $SourceDir -CurrentSource $SourceDir -CurrentDest $StageDir -AppRoot
Remove-StageSensitiveFiles -TargetStageDir $StageDir
Get-ChildItem -LiteralPath $StageDir -File -Force | Where-Object { $_.Extension -in @('.vbs', '.bat') } | Remove-Item -Force

$launcherProject = Join-Path $PSScriptRoot 'launcher\MyridTV.Launcher.csproj'
Build-Launcher -ProjectFile $launcherProject -StageDest (Join-Path $StageDir 'MyridTV.exe')

$desktopProject = Join-Path $PSScriptRoot 'desktop\MyridTV.Desktop.csproj'
Build-DesktopHost -ProjectFile $desktopProject -StageDest (Join-Path $StageDir 'MyridTV-Desktop.exe')

Invoke-MyridCodeSign `
    -Files @((Join-Path $StageDir 'MyridTV.exe'), (Join-Path $StageDir 'MyridTV-Desktop.exe')) `
    -Sign $Sign.IsPresent `
    -SignToolPath $SignToolPath `
    -CertificatePath $SignCertPath `
    -CertificatePassword $SignCertPassword `
    -CertificatePasswordEnv $SignCertPasswordEnv `
    -CertificateThumbprint $SignCertThumbprint `
    -CertificateStoreLocation $SignCertStoreLocation `
    -TimestampUrl $SignTimestampUrl

Initialize-StageRuntimeState -TargetStageDir $StageDir

$templateSource = Join-Path $SourceDir '_internal\data\app_config.template.json'
$templateTarget = Join-Path $StageDir '_internal\data\app_config.template.json'
if (Test-Path -LiteralPath $templateSource) {
    Copy-Item -LiteralPath $templateSource -Destination $templateTarget -Force
}

$envExamplePath = Join-Path $StageDir '_internal\API\.env.example'
$envExample = @(
    '# Fill API keys after installation.',
    'MYRIDTV_AGENT_API_KEY=',
    'API_PROVIDER_CUSTOM_API_KEY=',
    'API_PROVIDER_CUSTOM_API_3_KEY=',
    'RUNNINGHUB_API_KEY=',
    '',
    '# Legacy fallback, kept for existing users only.',
    'WCSTV_AGENT_API_KEY='
)
Set-Content -LiteralPath $envExamplePath -Value $envExample -Encoding UTF8

$stagedPythonDir = Join-Path $StageDir 'python'
Copy-PythonRuntime -RuntimeSource $PythonDir -RuntimeDest $stagedPythonDir
Install-PythonRuntimePackage -RuntimeSource $PythonDir -RuntimeDest $stagedPythonDir -Packages @('websockets>=13,<17')
Remove-StageLegacySensitiveFiles -TargetStageDir $StageDir
Sanitize-RunningHubCatalog -TargetStageDir $StageDir
Test-StagedPythonRuntime -TargetStageDir $StageDir
Remove-StageAuthorTraces -TargetStageDir $StageDir
Assert-ReleasePrivacy -TargetStageDir $StageDir

$manifestPath = Join-Path $StageDir 'installer-build.json'
$manifest = [ordered]@{
    built_at   = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    app_name   = 'MyridTV'
    release    = 'staged'
}
$manifest | ConvertTo-Json | Set-Content -LiteralPath $manifestPath -Encoding UTF8

Write-Host ''
Write-Host 'Release staging complete.'
Write-Host "Staged app: $StageDir"

param(
    [string]$PythonDir = '',
    [string]$SourceDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [string]$BuildRoot = (Join-Path $PSScriptRoot 'build'),
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

$stageScript = Join-Path $PSScriptRoot 'prepare-release.ps1'
$issFile = Join-Path $PSScriptRoot 'MyridTV.iss'
$buildRoot = [System.IO.Path]::GetFullPath($BuildRoot)
$stageDir = Join-Path $buildRoot 'MyridTV'
$outputDir = Join-Path $buildRoot 'installer'

# Check the compiler before clearing any previous build output.
$isccPreflight = Get-Command iscc -ErrorAction SilentlyContinue
if (-not $isccPreflight) {
    $isccPreflightPaths = @()
    foreach ($candidateRoot in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:LOCALAPPDATA)) {
        if (-not $candidateRoot) { continue }
        $isccPreflightPaths += (Join-Path $candidateRoot 'Inno Setup 6\ISCC.exe')
        $isccPreflightPaths += (Join-Path $candidateRoot 'Inno Setup 7\ISCC.exe')
        $isccPreflightPaths += (Join-Path $candidateRoot 'Programs\Inno Setup 6\ISCC.exe')
        $isccPreflightPaths += (Join-Path $candidateRoot 'Programs\Inno Setup 7\ISCC.exe')
    }
    $isccPreflight = $isccPreflightPaths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $isccPreflight) {
    foreach ($registryKey in @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*'
    )) {
        $innoInstall = Get-ItemProperty -Path $registryKey -ErrorAction SilentlyContinue |
            Where-Object { $_.DisplayName -like 'Inno Setup*' -and $_.InstallLocation } |
            Select-Object -First 1
        if ($innoInstall -and (Test-Path -LiteralPath (Join-Path $innoInstall.InstallLocation 'ISCC.exe'))) {
            $isccPreflight = $true
            break
        }
    }
}
if (-not $isccPreflight) {
    throw "ISCC.exe not found. Install Inno Setup (https://jrsoftware.org/isinfo.php) or add ISCC.exe to PATH. Existing build files were left untouched."
}

# Keep one reproducible build tree instead of accumulating old publish copies.
foreach ($oldBuildDir in @(
    $stageDir,
    $outputDir,
    (Join-Path $buildRoot 'desktop-publish'),
    (Join-Path $buildRoot 'launcher-publish'),
    (Join-Path $buildRoot 'release-unsigned')
)) {
    if (Test-Path -LiteralPath $oldBuildDir) {
        Remove-Item -LiteralPath $oldBuildDir -Recurse -Force
    }
}

& $stageScript `
    -SourceDir $SourceDir `
    -BuildRoot $buildRoot `
    -StageDir $stageDir `
    -PythonDir $PythonDir `
    -Sign:$Sign `
    -SignToolPath $SignToolPath `
    -SignCertPath $SignCertPath `
    -SignCertPassword $SignCertPassword `
    -SignCertPasswordEnv $SignCertPasswordEnv `
    -SignCertThumbprint $SignCertThumbprint `
    -SignCertStoreLocation $SignCertStoreLocation `
    -SignTimestampUrl $SignTimestampUrl

function Resolve-Iscc {
    # 1) PATH 里有直接用
    $cmd = Get-Command iscc -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -and (Test-Path -LiteralPath $cmd.Source)) { return $cmd.Source }

    # 2) 常见安装位置。用环境变量拼接，不把构建机用户名写死进脚本
    $candidates = @()
    foreach ($root in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:LOCALAPPDATA)) {
        if (-not $root) { continue }
        $candidates += (Join-Path $root 'Inno Setup 6\ISCC.exe')
        $candidates += (Join-Path $root 'Inno Setup 7\ISCC.exe')
        $candidates += (Join-Path $root 'Programs\Inno Setup 6\ISCC.exe')
        $candidates += (Join-Path $root 'Programs\Inno Setup 7\ISCC.exe')
    }
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) { return $candidate }
    }

    # 3) 注册表卸载信息里的安装目录，覆盖非默认路径安装
    $uninstallKeys = @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*'
    )
    foreach ($key in $uninstallKeys) {
        $entries = Get-ItemProperty -Path $key -ErrorAction SilentlyContinue |
            Where-Object { $_.DisplayName -like 'Inno Setup*' }
        foreach ($entry in $entries) {
            if (-not $entry.InstallLocation) { continue }
            $probe = Join-Path $entry.InstallLocation 'ISCC.exe'
            if (Test-Path -LiteralPath $probe) { return $probe }
        }
    }

    return $null
}

$iscc = Resolve-Iscc
if (-not $iscc) {
    throw "ISCC.exe not found. Install Inno Setup (https://jrsoftware.org/isinfo.php) or add ISCC.exe to PATH, then run this script again."
}
Write-Host "Inno Setup compiler: $iscc"

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

# 安装包版本号取自 VERSION（唯一事实源）；不再依赖 MyridTV.iss 里的硬编码值
$versionFile = Join-Path $SourceDir 'VERSION'
if (-not (Test-Path -LiteralPath $versionFile)) { $versionFile = Join-Path $stageDir 'VERSION' }
$displayVersion = ''
if (Test-Path -LiteralPath $versionFile) {
    $displayVersion = (Get-Content -LiteralPath $versionFile -Raw).Trim()
}
$numericVersion = $displayVersion.TrimStart('V', 'v')
if (-not $numericVersion) { $numericVersion = '0.0.0' }
if (-not $displayVersion) { $displayVersion = "V$numericVersion" }
Write-Host "Installer version: $displayVersion (numeric $numericVersion) from $versionFile"

& $iscc "/DMyAppSource=$stageDir" "/DMyOutputDir=$outputDir" "/DMyAppVersion=$numericVersion" "/DMyAppDisplayVersion=$displayVersion" $issFile

$setupExe = Join-Path $outputDir 'MyridTV-Setup.exe'
Invoke-MyridCodeSign `
    -Files @($setupExe) `
    -Sign $Sign.IsPresent `
    -SignToolPath $SignToolPath `
    -CertificatePath $SignCertPath `
    -CertificatePassword $SignCertPassword `
    -CertificatePasswordEnv $SignCertPasswordEnv `
    -CertificateThumbprint $SignCertThumbprint `
    -CertificateStoreLocation $SignCertStoreLocation `
    -TimestampUrl $SignTimestampUrl

Write-Host ''
Write-Host "Installer build complete: $outputDir"

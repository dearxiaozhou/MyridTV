param(
    [string]$PythonDir = '',
    [string]$SourceDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
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
$buildRoot = Join-Path $PSScriptRoot 'build'
$stageDir = Join-Path $buildRoot 'MyridTV'
$outputDir = Join-Path $buildRoot 'installer'

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

$iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
if (-not $iscc) {
    $candidate = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
    if (Test-Path -LiteralPath $candidate) { $iscc = $candidate }
}
if (-not $iscc) {
    $candidate = 'C:\Users\<user>\AppData\Local\Programs\Inno Setup 7\ISCC.exe'
    if (Test-Path -LiteralPath $candidate) { $iscc = $candidate }
}
if (-not $iscc) {
    $candidate = 'C:\Program Files (x86)\Inno Setup 7\ISCC.exe'
    if (Test-Path -LiteralPath $candidate) { $iscc = $candidate }
}

if (-not $iscc) {
    throw "ISCC.exe not found. Install Inno Setup first, then run this script again."
}

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

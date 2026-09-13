param(
    [string]$InstallerPath = (Join-Path $PSScriptRoot 'build\installer\MyridTV-Setup.exe'),
    [string]$ReleaseRoot = (Join-Path $PSScriptRoot 'build\release-unsigned')
)

$ErrorActionPreference = 'Stop'

function Get-InnoDefineValue {
    param(
        [string]$FilePath,
        [string]$Name
    )

    $pattern = '^\s*#define\s+' + [regex]::Escape($Name) + '\s+"([^"]+)"'
    foreach ($line in Get-Content -LiteralPath $FilePath) {
        $match = [regex]::Match($line, $pattern)
        if ($match.Success) {
            return $match.Groups[1].Value
        }
    }

    return ''
}

$installerFullPath = [System.IO.Path]::GetFullPath($InstallerPath)
if (!(Test-Path -LiteralPath $installerFullPath)) {
    throw "Installer not found: $installerFullPath"
}

$issFile = Join-Path $PSScriptRoot 'MyridTV.iss'
$appName = Get-InnoDefineValue -FilePath $issFile -Name 'MyAppName'
$version = Get-InnoDefineValue -FilePath $issFile -Name 'MyAppVersion'
$displayVersion = Get-InnoDefineValue -FilePath $issFile -Name 'MyAppDisplayVersion'
if ([string]::IsNullOrWhiteSpace($appName)) {
    $appName = 'MyridTV'
}
if ([string]::IsNullOrWhiteSpace($version)) {
    $version = (Get-Date).ToString('yyyy.MM.dd')
}
if ([string]::IsNullOrWhiteSpace($displayVersion)) {
    $displayVersion = $version
}

$releaseVersion = $displayVersion -replace '[^\w\.\-]+', '-'
$releaseDir = Join-Path $ReleaseRoot "$appName-$releaseVersion-unsigned"
New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null
$releaseZip = Join-Path $ReleaseRoot "$appName-$releaseVersion-unsigned.zip"

$installerFileName = "$appName-Setup-$releaseVersion-unsigned.exe"
$releaseInstaller = Join-Path $releaseDir $installerFileName
Copy-Item -LiteralPath $installerFullPath -Destination $releaseInstaller -Force

$hash = Get-FileHash -LiteralPath $releaseInstaller -Algorithm SHA256
$sizeBytes = (Get-Item -LiteralPath $releaseInstaller).Length
$sizeMb = [Math]::Round($sizeBytes / 1MB, 2)
$buildTime = (Get-Item -LiteralPath $releaseInstaller).LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')
$generatedAt = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
$signature = Get-AuthenticodeSignature -LiteralPath $releaseInstaller

$shaLine = "$($hash.Hash.ToLowerInvariant())  $installerFileName"
Set-Content -LiteralPath (Join-Path $releaseDir 'SHA256SUMS.txt') -Value $shaLine -Encoding UTF8
Set-Content -LiteralPath (Join-Path $releaseDir "$installerFileName.sha256") -Value $shaLine -Encoding UTF8

$notes = @"
$appName $displayVersion unsigned test release

File:
  $installerFileName

Size:
  $sizeMb MB ($sizeBytes bytes)

SHA256:
  $($hash.Hash.ToLowerInvariant())

Signature status:
  $($signature.Status)

Generated at:
  $generatedAt

Build time:
  $buildTime

What this build is for:
  This is an unsigned test build for small-scope testing.
  It has passed local install, launch, and uninstall smoke tests.

Important:
  Windows may show Unknown Publisher or SmartScreen warnings because this build is not code-signed.
  Only install this package if you trust the source where you got it.
  SHA256 can help verify that the downloaded file matches this release, but it is not a replacement for code signing.

Basic install:
  1. Run $installerFileName.
  2. If Windows SmartScreen appears, choose More info, then Run anyway.
  3. After installation, launch MyridTV from the desktop or Start menu shortcut.

Verify SHA256 in PowerShell:
  Get-FileHash .\$installerFileName -Algorithm SHA256

Expected SHA256:
  $($hash.Hash.ToLowerInvariant())
"@

Set-Content -LiteralPath (Join-Path $releaseDir 'RELEASE_NOTES.txt') -Value $notes -Encoding UTF8

$installGuide = @"
MyridTV unsigned installer instructions

This release is not code-signed.
Windows may display Unknown Publisher or SmartScreen warnings.

Recommended checks before installing:

1. Confirm the file name:
   $installerFileName

2. Confirm SHA256:
   $($hash.Hash.ToLowerInvariant())

3. PowerShell command:
   Get-FileHash .\$installerFileName -Algorithm SHA256

If the SHA256 value is different, do not install the file.

Install:
  Run $installerFileName and follow the installer.

Uninstall:
  Windows Settings > Apps > Installed apps > MyridTV > Uninstall
"@

Set-Content -LiteralPath (Join-Path $releaseDir 'INSTALL_UNSIGNED.txt') -Value $installGuide -Encoding UTF8

if (Test-Path -LiteralPath $releaseZip) {
    Remove-Item -LiteralPath $releaseZip -Force
}
Compress-Archive -Path (Join-Path $releaseDir '*') -DestinationPath $releaseZip -CompressionLevel Optimal
$zipHash = Get-FileHash -LiteralPath $releaseZip -Algorithm SHA256
$zipHashLine = "$($zipHash.Hash.ToLowerInvariant())  $(Split-Path -Leaf $releaseZip)"
Set-Content -LiteralPath "$releaseZip.sha256" -Value $zipHashLine -Encoding UTF8

[pscustomobject]@{
    ReleaseDir = $releaseDir
    ReleaseZip = $releaseZip
    Installer = $releaseInstaller
    SizeMB = $sizeMb
    SHA256 = $hash.Hash.ToLowerInvariant()
    ZipSHA256 = $zipHash.Hash.ToLowerInvariant()
    SignatureStatus = $signature.Status
} | Format-List

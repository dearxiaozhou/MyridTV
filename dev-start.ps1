param(
    [switch]$StopExisting,
    [switch]$NoDesktop,
    [switch]$NoSyncDesktopHost
)

$ErrorActionPreference = 'Stop'

$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$StartScript = Join-Path $AppDir 'start_myridtv.ps1'
$SourceDesktopHost = Join-Path $AppDir 'MyridTV-Desktop.exe'
$BuiltDesktopHost = Join-Path $AppDir 'installer\build\MyridTV\MyridTV-Desktop.exe'

function Stop-MyridProcesses {
    $processes = Get-CimInstance Win32_Process | Where-Object {
        $_.Name -in @('MyridTV.exe', 'MyridTV-Desktop.exe') -or
        (($_.Name -like 'python*' -or $_.Name -like 'py.exe') -and $_.CommandLine -match 'rh_official_proxy\.py') -or
        (($_.Name -like 'powershell*' -or $_.Name -like 'pwsh*') -and $_.CommandLine -match 'start_myridtv\.ps1')
    }

    foreach ($process in $processes) {
        try {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
            Write-Host "Stopped $($process.Name) pid=$($process.ProcessId)"
        }
        catch {
            Write-Warning "Could not stop $($process.Name) pid=$($process.ProcessId): $($_.Exception.Message)"
        }
    }
}

if ($StopExisting) {
    Stop-MyridProcesses
    Start-Sleep -Milliseconds 500
}

if (!(Test-Path -LiteralPath $StartScript)) {
    throw "Missing startup script: $StartScript"
}

if (!$NoSyncDesktopHost -and (Test-Path -LiteralPath $BuiltDesktopHost)) {
    $sourceInfo = if (Test-Path -LiteralPath $SourceDesktopHost) { Get-Item -LiteralPath $SourceDesktopHost } else { $null }
    $builtInfo = Get-Item -LiteralPath $BuiltDesktopHost

    if (!$sourceInfo -or $sourceInfo.Length -ne $builtInfo.Length -or $sourceInfo.LastWriteTime -lt $builtInfo.LastWriteTime) {
        Copy-Item -LiteralPath $BuiltDesktopHost -Destination $SourceDesktopHost -Force
        Write-Host "Synced desktop host: $SourceDesktopHost"
    }
}

$arguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $StartScript)
if ($NoDesktop) {
    $arguments += '-NoDesktop'
}

& powershell @arguments

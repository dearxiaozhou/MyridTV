param()

$ErrorActionPreference = 'Continue'

$processes = Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -in @('MyridTV.exe', 'MyridTV-Desktop.exe') -or
        (($_.Name -like 'python*' -or $_.Name -like 'py.exe') -and $_.CommandLine -match 'rh_official_proxy\.py') -or
        (($_.Name -like 'powershell*' -or $_.Name -like 'pwsh*') -and $_.CommandLine -match 'start_myridtv\.ps1')
    }

if (!$processes) {
    Write-Host 'No MyridTV processes found.'
    exit 0
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

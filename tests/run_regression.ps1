param(
  [switch]$DryRun,
  [switch]$IncludeLiveIntegration,
  [switch]$IncludePerformanceBenchmarks,
  [string]$Only = "",
  [int]$TestPort = 0
)
# Deterministic browser regression. Real ComfyUI generation needs explicit opt-in.
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File tests\run_regression.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File tests\run_regression.ps1 -DryRun
#   powershell -NoProfile -ExecutionPolicy Bypass -File tests\run_regression.ps1 -Only composer
#   powershell -NoProfile -ExecutionPolicy Bypass -File tests\run_regression.ps1 -IncludeLiveIntegration
#   powershell -NoProfile -ExecutionPolicy Bypass -File tests\run_regression.ps1 -Only scale_benchmark -IncludePerformanceBenchmarks
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$testDir = Join-Path $root 'tests'
if ($TestPort -gt 0) {
  $port = $TestPort
  if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
    Write-Host "[FAIL] isolated test port $port is already in use; refusing to connect to an unrelated server" -ForegroundColor Red
    exit 2
  }
} else {
  $portProbe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
  $portProbe.Start()
  $port = ([System.Net.IPEndPoint]$portProbe.LocalEndpoint).Port
  $portProbe.Stop()
}
$base = "http://127.0.0.1:$port"
$liveIntegrationNames = @('e2e_http_jobs.py')
$performanceBenchmarkNames = @('e2e_canvas_scale_benchmark.py')

$python = $null
foreach ($envName in @('WCSTV_PYTHON_EXE', 'MYRIDTV_PYTHON_EXE')) {
  $v = [Environment]::GetEnvironmentVariable($envName)
  if ($v -and (Test-Path -LiteralPath $v)) { $python = $v; break }
}
if (-not $python) {
  foreach ($c in @(
    (Join-Path $root 'python\python.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe')
  )) { if (Test-Path -LiteralPath $c) { $python = $c; break } }
}
if (-not $python) { $python = 'python' }

$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONPATH = $root

$allE2eFiles = @(Get-ChildItem -LiteralPath $testDir -Filter 'e2e_*.py' -File)
if ($IncludeLiveIntegration) {
  $e2eFiles = $allE2eFiles
} else {
  $e2eFiles = @($allE2eFiles | Where-Object { $_.Name -notin $liveIntegrationNames })
}
if (-not $IncludePerformanceBenchmarks) {
  $e2eFiles = @($e2eFiles | Where-Object { $_.Name -notin $performanceBenchmarkNames })
}
if ($Only) { $e2eFiles = @($e2eFiles | Where-Object { $_.Name -like "*$Only*" }) }
$liveNames = @($allE2eFiles | Where-Object { $_.Name -in $liveIntegrationNames } | ForEach-Object { $_.Name })

Write-Host "MyridTV regression | root=$root"
Write-Host "  python: $python"
Write-Host "  deterministic e2e files: $($e2eFiles.Count)"
if ($liveNames.Count -gt 0) {
  if ($IncludeLiveIntegration) {
    Write-Host "  live integration: included by explicit request ($($liveNames -join ', '))" -ForegroundColor Yellow
  } else {
    Write-Host "  live integration: skipped by default ($($liveNames -join ', ')); requires -IncludeLiveIntegration" -ForegroundColor Yellow
  }
}
if ($IncludePerformanceBenchmarks) {
  Write-Host "  performance benchmarks: included by explicit opt-in"
} elseif (@($allE2eFiles | Where-Object { $_.Name -in $performanceBenchmarkNames }).Count -gt 0) {
  Write-Host "  performance benchmarks: skipped by default (use -IncludePerformanceBenchmarks)" -ForegroundColor Yellow
}

if ($DryRun) {
  Write-Host "  [DRY] check_frontend_architecture.py"
  foreach ($t in $e2eFiles) { Write-Host "  [DRY] $($t.Name)" }
  Write-Host "DRYRUN done (no instance started, no tests run)"
  exit 0
}

$architectureCheck = Join-Path $testDir 'check_frontend_architecture.py'
Write-Host "running frontend architecture gate..."
& $python $architectureCheck
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if ($e2eFiles.Count -eq 0) { Write-Host "no e2e_*.py selected, exit" -ForegroundColor Yellow; exit 0 }

$runId = [Guid]::NewGuid().ToString('N')
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) 'MyridTV-RegressionRuns'
$runRoot = Join-Path $tempRoot $runId
$testDataPath = Join-Path $runRoot 'userdata'
New-Item -ItemType Directory -Path $testDataPath -Force | Out-Null
$previousTestDataPath = [Environment]::GetEnvironmentVariable('MYRIDTV_TEST_DATA_DIR', 'Process')
$previousTestPort = [Environment]::GetEnvironmentVariable('MYRIDTV_TEST_PORT', 'Process')
$previousTestBase = [Environment]::GetEnvironmentVariable('MYRIDTV_TEST_BASE', 'Process')
$previousLiveFlag = [Environment]::GetEnvironmentVariable('MYRIDTV_RUN_LIVE_INTEGRATION', 'Process')
[Environment]::SetEnvironmentVariable('MYRIDTV_TEST_DATA_DIR', $testDataPath, 'Process')
[Environment]::SetEnvironmentVariable('MYRIDTV_TEST_PORT', [string]$port, 'Process')
[Environment]::SetEnvironmentVariable('MYRIDTV_TEST_BASE', $base, 'Process')
if ($IncludeLiveIntegration) {
  [Environment]::SetEnvironmentVariable('MYRIDTV_RUN_LIVE_INTEGRATION', '1', 'Process')
} else {
  [Environment]::SetEnvironmentVariable('MYRIDTV_RUN_LIVE_INTEGRATION', $null, 'Process')
}

$instProc = $null
$keepRunData = $false
try {
  $outLog = Join-Path $runRoot 'server.out'
  $errLog = Join-Path $runRoot 'server.err'
  $instProc = Start-Process -FilePath $python -ArgumentList @((Join-Path $testDir 'launch_test_instance.py')) -PassThru -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden
  Write-Host "isolated instance started pid=$($instProc.Id), waiting for ready..."

  $ready = $false
  for ($i = 0; $i -lt 60; $i++) {
    if ($instProc.HasExited) {
      $keepRunData = $true
      Write-Host "[FAIL] isolated test server process exited before readiness (port $port)" -ForegroundColor Red
      if (Test-Path -LiteralPath $errLog) { Get-Content $errLog | ForEach-Object { Write-Host "    $_" } }
      Write-Host "diagnostics retained at $runRoot" -ForegroundColor Yellow
      exit 2
    }
    try {
      $r = Invoke-WebRequest -Uri "$base/smart-canvas.html" -TimeoutSec 1 -UseBasicParsing
      if ($r.StatusCode -eq 200 -and -not $instProc.HasExited) { $ready = $true; break }
    } catch {}
    Start-Sleep -Seconds 1
  }
  if (-not $ready) {
    $keepRunData = $true
    Write-Host "[FAIL] isolated instance 3217 not ready (port occupied or backend failed)" -ForegroundColor Red
    if (Test-Path -LiteralPath $errLog) { Get-Content $errLog | ForEach-Object { Write-Host "    $_" } }
    Write-Host "diagnostics retained at $runRoot" -ForegroundColor Yellow
    exit 2
  }
  Write-Host "instance ready, running e2e" -ForegroundColor Green

  $failed = @()
  foreach ($t in $e2eFiles) {
    $out = & $python $t.FullName 2>&1
    $rc = $LASTEXITCODE
    $failLines = ($out | Where-Object { $_ -match '\bFAIL\b' }).Count
    $resultLine = ($out | Where-Object { $_ -match 'RESULT:' } | Select-Object -Last 1)
    $ok = ($rc -eq 0) -and ($failLines -eq 0)
    if ($ok) {
      Write-Host "  [OK]   $($t.Name)  $resultLine" -ForegroundColor Green
      if ($t.Name -in $performanceBenchmarkNames) {
        $baselineLine = $out | Where-Object { $_ -match '^PERFORMANCE_BASELINE:' } | Select-Object -Last 1
        if ($baselineLine) { Write-Host "         $baselineLine" }
      }
    } else {
      $failed += "$($t.Name) | rc=$rc failLines=$failLines | $resultLine"
      Write-Host "  [FAIL] $($t.Name)  rc=$rc failLines=$failLines  $resultLine" -ForegroundColor Red
      foreach ($line in $out) { Write-Host "      $line" }
    }
  }

  Write-Host ''
  if ($failed.Count -gt 0) {
    $keepRunData = $true
    Write-Host "REGRESSION FAILED: $($failed.Count)/$($e2eFiles.Count)" -ForegroundColor Red
    foreach ($f in $failed) { Write-Host "    - $f" }
    Write-Host "isolated test data and server logs retained at $runRoot" -ForegroundColor Yellow
    exit 1
  }
  Write-Host "REGRESSION PASSED: $($e2eFiles.Count)/$($e2eFiles.Count)" -ForegroundColor Green
}
finally {
  if ($instProc) {
    try { Stop-Process -Id $instProc.Id -Force -ErrorAction SilentlyContinue } catch {}
  }
  [Environment]::SetEnvironmentVariable('MYRIDTV_TEST_DATA_DIR', $previousTestDataPath, 'Process')
  [Environment]::SetEnvironmentVariable('MYRIDTV_TEST_PORT', $previousTestPort, 'Process')
  [Environment]::SetEnvironmentVariable('MYRIDTV_TEST_BASE', $previousTestBase, 'Process')
  [Environment]::SetEnvironmentVariable('MYRIDTV_RUN_LIVE_INTEGRATION', $previousLiveFlag, 'Process')
  if (-not $keepRunData -and (Test-Path -LiteralPath $runRoot)) {
    $resolvedTempRoot = [IO.Path]::GetFullPath($tempRoot).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    $resolvedRunRoot = [IO.Path]::GetFullPath($runRoot)
    if ($resolvedRunRoot.StartsWith($resolvedTempRoot, [StringComparison]::OrdinalIgnoreCase)) {
      Remove-Item -LiteralPath $resolvedRunRoot -Recurse -Force
    } else {
      Write-Host "[WARN] refusing to remove unexpected temp path: $resolvedRunRoot" -ForegroundColor Yellow
    }
  }
}

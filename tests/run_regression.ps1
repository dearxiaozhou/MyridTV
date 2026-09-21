param(
  [switch]$DryRun,
  [string]$Only = ""
)
# run_regression.ps1 - MyridTV one-click browser e2e regression
# auto: start isolated instance(3217) -> wait ready -> run tests/e2e_*.py -> summarize -> stop instance
# usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File tests\run_regression.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File tests\run_regression.ps1 -DryRun
#   powershell -NoProfile -ExecutionPolicy Bypass -File tests\run_regression.ps1 -Only composer
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$testDir = Join-Path $root 'tests'
$port = 3217
$base = "http://127.0.0.1:$port"

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

$e2eFiles = @(Get-ChildItem -LiteralPath $testDir -Filter 'e2e_*.py' -File)
if ($Only) { $e2eFiles = $e2eFiles | Where-Object { $_.Name -like "*$Only*" } }

Write-Host "MyridTV regression | root=$root"
Write-Host "  python: $python"
Write-Host "  e2e files: $($e2eFiles.Count)"

if ($DryRun) {
  foreach ($t in $e2eFiles) { Write-Host "  [DRY] $($t.Name)" }
  Write-Host "DRYRUN done (no instance started, no tests run)"
  exit 0
}

if ($e2eFiles.Count -eq 0) { Write-Host "no e2e_*.py found, exit" -ForegroundColor Yellow; exit 0 }

$instProc = $null
try {
  $outLog = Join-Path $testDir '_inst.out'
  $errLog = Join-Path $testDir '_inst.err'
  $instProc = Start-Process -FilePath $python -ArgumentList @((Join-Path $testDir 'launch_test_instance.py')) -PassThru -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden
  Write-Host "isolated instance started pid=$($instProc.Id), waiting for ready..."

  $ready = $false
  for ($i = 0; $i -lt 60; $i++) {
    try {
      $r = Invoke-WebRequest -Uri "$base/smart-canvas.html" -TimeoutSec 1 -UseBasicParsing
      if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
    Start-Sleep -Seconds 1
  }
  if (-not $ready) {
    Write-Host "[FAIL] isolated instance 3217 not ready (port occupied or backend failed)" -ForegroundColor Red
    if (Test-Path -LiteralPath $errLog) { Get-Content $errLog | ForEach-Object { Write-Host "    $_" } }
    exit 2
  }
  Write-Host "instance ready, running e2e" -ForegroundColor Green

  $failed = @()
  $passed = @()
  foreach ($t in $e2eFiles) {
    $out = & $python $t.FullName 2>&1
    $rc = $LASTEXITCODE
    $failLines = ($out | Where-Object { $_ -match '\bFAIL\b' }).Count
    $resultLine = ($out | Where-Object { $_ -match 'RESULT:' } | Select-Object -Last 1)
    $ok = ($rc -eq 0) -and ($failLines -eq 0)
    if ($ok) {
      $passed += $t.Name
      Write-Host "  [OK]   $($t.Name)  $resultLine" -ForegroundColor Green
    } else {
      $failed += "$($t.Name) | rc=$rc failLines=$failLines | $resultLine"
      Write-Host "  [FAIL] $($t.Name)  rc=$rc failLines=$failLines  $resultLine" -ForegroundColor Red
    }
  }

  Write-Host ''
  if ($failed.Count -gt 0) {
    Write-Host "REGRESSION FAILED: $($failed.Count)/$($e2eFiles.Count)" -ForegroundColor Red
    foreach ($f in $failed) { Write-Host "    - $f" }
    exit 1
  }
  Write-Host "REGRESSION PASSED: $($e2eFiles.Count)/$($e2eFiles.Count)" -ForegroundColor Green
  exit 0
}
finally {
  if ($instProc) {
    try { Stop-Process -Id $instProc.Id -Force -ErrorAction SilentlyContinue } catch {}
  }
}

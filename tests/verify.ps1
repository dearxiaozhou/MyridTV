# MyridTV 自检基线（②A）
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File tests\verify.ps1
# 改完代码先跑这个；红了就别交付。全绿 = 语法/前端/i18n/单测四道都过。

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$fail = New-Object System.Collections.Generic.List[string]
$pass = New-Object System.Collections.Generic.List[string]

# --- 找一个 python（优先配置的运行时，其次系统 3.1x） ---
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

Write-Host "MyridTV verify  |  root=$root"
Write-Host "   python: $python"
Write-Host "   node  : $((Get-Command node -ErrorAction SilentlyContinue).Source)"

# --- 1) Python 语法编译 ---
$pyFiles = @(Get-ChildItem -LiteralPath $root -Filter *.py -File) +
           @(Get-ChildItem -LiteralPath (Join-Path $root 'tests') -Filter *.py -File -ErrorAction SilentlyContinue)
$pyBad = 0
foreach ($f in $pyFiles) {
    $out = & $python -m py_compile $f.FullName 2>&1
    if ($LASTEXITCODE -ne 0) { $pyBad++; $fail.Add("py_compile 失败: $($f.Name)`n    $out") }
}
if ($pyBad -eq 0) { $pass.Add("Python 语法: $($pyFiles.Count) 个文件全部通过") }

# --- 2) 前端 JS 语法（跳过 vendor/） ---
$jsDir = Join-Path $root '_internal\static\js'
$jsFiles = @()
if (Test-Path -LiteralPath $jsDir) {
    $jsFiles = @(Get-ChildItem -LiteralPath $jsDir -Recurse -Filter *.js -File |
                 Where-Object { $_.FullName -notmatch '\\vendor\\' })
}
$jsBad = 0
foreach ($f in $jsFiles) {
    $out = & node --check $f.FullName 2>&1
    if ($LASTEXITCODE -ne 0) { $jsBad++; $fail.Add("node --check 失败: $($f.Name)`n    $out") }
}
if ($jsBad -eq 0) { $pass.Add("前端 JS 语法: $($jsFiles.Count) 个文件全部通过（跳过 vendor）") }

# --- 3) i18n 键校验 ---
$i18n = Join-Path $root '_internal\static\js\i18n\validate-i18n.js'
if (Test-Path -LiteralPath $i18n) {
    $out = & node $i18n 2>&1
    if ($LASTEXITCODE -ne 0) { $fail.Add("i18n 校验失败:`n    $out") }
    else { $pass.Add("i18n: $out") }
} else { $fail.Add('找不到 _internal\static\js\i18n\validate-i18n.js') }

# --- 4) 悬空名字检查（拆模块/搬函数后"用了没绑定"的名字，运行时才炸的那种） ---
$dangling = Join-Path $root 'tests\check_dangling_names.py'
if (Test-Path -LiteralPath $dangling) {
    $out = & $python -B $dangling 2>&1
    if ($LASTEXITCODE -ne 0) { $fail.Add("悬空名字检查失败:`n    $out") }
    else { $pass.Add("悬空名字: $out") }
} else { $fail.Add('找不到 tests\check_dangling_names.py') }

# --- 5) 单测（tests/test_*.py，含子目录） ---
# 必须递归：tests/agent-e2e/ 下的 4 个测试以前因为不递归而从未被跑到，
# 变成"看着有测试、其实没人跑"的死测试。
$testFiles = @(Get-ChildItem -LiteralPath (Join-Path $root 'tests') -Filter 'test_*.py' -File -Recurse -ErrorAction SilentlyContinue)
foreach ($t in $testFiles) {
    $out = & $python $t.FullName -v 2>&1
    if ($LASTEXITCODE -ne 0) { $fail.Add("单测失败: $($t.Name)`n    $($out | Select-Object -Last 8 | Out-String)") }
    else { $pass.Add("单测通过: $($t.Name)") }
}

# --- 汇总 ---
Write-Host ''
foreach ($line in $pass) { Write-Host "  [OK]   $line" -ForegroundColor Green }
foreach ($line in $fail) { Write-Host "  [FAIL] $line" -ForegroundColor Red }
Write-Host ''
if ($fail.Count -gt 0) {
    Write-Host "verify FAILED: $($fail.Count) 项" -ForegroundColor Red
    exit 1
}
Write-Host "verify PASSED" -ForegroundColor Green
exit 0

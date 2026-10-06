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

# --- 固定 Python 运行环境（本地与 CI 行为一致）---
# 1) 非中文代码页的机器上，Python 默认 stdout 是 cp1252，脚本里 print 中文会直接抛
#    UnicodeEncodeError。强制 UTF-8 后，换机器/CI 都不会因为输出中文而崩。
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
# 2) tests\agent-e2e\ 下的测试要 import 仓库根模块（rh_official_proxy 等），
#    而脚本模式只会把脚本所在目录加进 sys.path，这里显式补上仓库根。
$env:PYTHONPATH = $root

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

# --- 6) 前端模块接线静态门禁 ---
$wiring = Join-Path $root 'tests\check_frontend_wiring.py'
if (Test-Path -LiteralPath $wiring) {
    $out = & $python -B $wiring 2>&1
    if ($LASTEXITCODE -ne 0) { $fail.Add("前端接线检查失败:`n    $out") }
    else { $pass.Add("前端接线检查: $out") }
} else { $fail.Add('找不到 tests\check_frontend_wiring.py（前端接线门禁缺失）') }

# --- 7) 画布交互 e2e（隔离测试实例 3217，Playwright） ---
# 守护无限画布交互链路（引擎切换/节点生命周期/连线/提示词构建）：
# 这些测试跑在独立端口 3217 + _test_userdata，不碰用户正式实例 3107。
# 流程：启动 launch_test_instance.py → 跑 tests/e2e_canvas_*.py → 杀实例。
# 注意：e2e 用 Python313（装 playwright）；verify 选中的 python 必须是同一个。
$e2eDir = Join-Path $root 'tests'
# P95 performance sampling includes browser automation and is host-dependent; keep it
# opt-in through run_regression.ps1 -IncludePerformanceBenchmarks instead of a release gate.
$e2eFiles = @(Get-ChildItem -LiteralPath $e2eDir -Filter 'e2e_canvas_*.py' -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -ne 'e2e_canvas_scale_benchmark.py' })
if (Test-Path -LiteralPath (Join-Path $e2eDir 'e2e_canvas_scale_benchmark.py')) {
    Write-Host '[INFO] canvas performance benchmark is opt-in: run_regression.ps1 -Only scale_benchmark -IncludePerformanceBenchmarks'
}
if ($e2eFiles.Count -gt 0) {
    # 确认 playwright 可用（Python313 装了；其它解释器可能没有）
    $hasPw = & $python -c "import playwright" 2>&1
    if ($LASTEXITCODE -eq 0) {
        # 启动隔离测试实例（后台）
        $instOut = Join-Path $env:TEMP 'myridtv_e2e_instance.out.log'
        $instErr = Join-Path $env:TEMP 'myridtv_e2e_instance.err.log'
        $inst = Start-Process -FilePath $python -ArgumentList @((Join-Path $e2eDir 'launch_test_instance.py')) -PassThru -WindowStyle Hidden -RedirectStandardOutput $instOut -RedirectStandardError $instErr
        # 等实例健康（最多 30s）
        $healthy = $false
        for ($i = 0; $i -lt 30; $i++) {
            Start-Sleep -Seconds 1
            try {
                $r = Invoke-WebRequest -Uri 'http://127.0.0.1:3217/health' -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
                if ($r.StatusCode -eq 200) { $healthy = $true; break }
            } catch {}
        }
        if (-not $healthy) {
            $fail.Add("画布 e2e: 测试实例 3217 启动失败`n    $(Get-Content $instOut -ErrorAction SilentlyContinue | Select-Object -Last 5 | Out-String)`n    $(Get-Content $instErr -ErrorAction SilentlyContinue | Select-Object -Last 5 | Out-String)")
        } else {
            $pass.Add("画布 e2e: 测试实例 3217 就绪")
            $e2eBad = 0
            foreach ($e in $e2eFiles) {
                $out = & $python $e.FullName 2>&1
                # e2e 脚本自己输出 PASS/FAIL 并返回 exit 1（failures>0 时）
                if ($LASTEXITCODE -ne 0) { $e2eBad++; $fail.Add("画布 e2e 失败: $($e.Name)`n    $($out | Select-Object -Last 12 | Out-String)") }
                else { $pass.Add("画布 e2e 通过: $($e.Name)") }
            }
            if ($e2eBad -eq 0) { $pass.Add("画布 e2e: $($e2eFiles.Count) 个全部通过") }
        }
        # 杀测试实例（含可能残留的 python 子进程：launch_test_instance 里 ThreadingHTTPServer 同进程）
        if (-not $inst.HasExited) { Stop-Process -Id $inst.Id -Force -ErrorAction SilentlyContinue }
        # 兜底：端口 3217 若还被占，杀占用 pid（测试实例是独立进程，只杀 3217 的）
        $listener = Get-NetTCPConnection -LocalPort 3217 -State Listen -ErrorAction SilentlyContinue
        if ($listener) {
            $listener | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
        }
        Start-Sleep -Seconds 1
    } else {
        $fail.Add("画布 e2e: 当前 python 无 playwright 模块（需要 Python313），跳过")
    }
} else {
    $fail.Add('找不到 tests/e2e_canvas_*.py（画布交互 e2e 缺失）')
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

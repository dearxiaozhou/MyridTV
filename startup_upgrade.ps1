# startup_upgrade.ps1 — MyridTV 升级安全钩子
#
# 被 start_myridtv.ps1 点源加载（dot-source），启动时调用：
#     $r = Invoke-WcsTvUpgradeSafety -AppDir <应用目录> -UserDataRoot <用户数据根> -ArtifactPaths <被升级覆盖的文件列表>
#     $r.Events   → 逐条写进 data/logs/startup.log
#
# 作用（只做保护，不动业务数据语义）：
#   1) 记录"程序文件指纹 + 版本号"基线：发现程序被升级/替换（指纹或版本变了）
#   2) 升级前把用户数据（画布/配置/平台/素材库/任务库/技能）备份到
#      <用户数据>\data\upgrade_backups\<版本>_<时间戳>\（只保留最新 1 份）
#   3) 升级后做完整性体检：关键 JSON 解析不了 → 从上面这份备份里取回该文件
#   4) 用户数据"缩水"体检：画布/技能数量比升级前少 → 明确告警并给出备份路径
#
# 约定：本文件任何情况都不得抛异常中断启动；全部失败都变成 Events 里的一行说明。
# 注意：只做加法（备份/取回），不做任何删除用户数据的动作。

$ErrorActionPreference = 'Continue'
Set-StrictMode -Off

$script:WcsTvUpgradeStateDir = 'state'
$script:WcsTvUpgradeStateFile = 'upgrade_state.json'
$script:WcsTvUpgradeBackupDir = 'upgrade_backups'
$script:WcsTvUpgradeKeepBackups = 1
$script:WcsTvUpgradeBackupFiles = @(
    'app_config.json',
    'api_providers.json',
    'asset_library.json',
    'canvas_tasks.db',
    'canvas_tasks.db-wal',
    'canvas_tasks.db-shm',
    'canvas_agent_rules.md'
)
$script:WcsTvUpgradeBackupDirs = @(
    'canvases',
    'canvas_agent_skills',
    'canvas_agent_history',
    'conversations'
)
# 体检 JSON：解析不了就从备份取回
$script:WcsTvUpgradeJsonFiles = @(
    'app_config.json',
    'api_providers.json',
    'asset_library.json'
)

function WcsTvUpgrade-WriteJson($Path, $Object) {
    try {
        $dir = Split-Path -Parent $Path
        if ($dir -and !(Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
        $json = $Object | ConvertTo-Json -Depth 10
        [System.IO.File]::WriteAllText($Path, $json, (New-Object System.Text.UTF8Encoding($false)))
        return $true
    } catch { return $false }
}

function WcsTvUpgrade-ReadJson($Path) {
    if (!(Test-Path -LiteralPath $Path)) { return $null }
    try { return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json) } catch { return $null }
}

function WcsTvUpgrade-AppVersion($AppDir) {
    foreach ($name in @('VERSION', 'VERSION.txt')) {
        $p = Join-Path $AppDir $name
        if (Test-Path -LiteralPath $p) {
            try { return ([string](Get-Content -LiteralPath $p -Raw -Encoding UTF8)).Trim() } catch { }
        }
    }
    return ''
}

function WcsTvUpgrade-Signature($AppDir, $Paths) {
    $items = New-Object System.Collections.Generic.List[string]
    foreach ($p in @($Paths)) {
        if ([string]::IsNullOrWhiteSpace($p)) { continue }
        if (!(Test-Path -LiteralPath $p)) { $items.Add("$p|missing"); continue }
        try {
            $f = Get-Item -LiteralPath $p -Force
            $rel = $f.FullName
            if ($AppDir -and $f.FullName.StartsWith($AppDir, [System.StringComparison]::OrdinalIgnoreCase)) {
                $rel = $f.FullName.Substring($AppDir.Length).TrimStart('\', '/')
            }
            $items.Add(("{0}|{1}|{2}" -f $rel, $f.Length, $f.LastWriteTimeUtc.Ticks))
        } catch { $items.Add("$p|error") }
    }
    $joined = ($items | Sort-Object) -join "`n"
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hash = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($joined))
        $sig = ([System.BitConverter]::ToString($hash) -replace '-', '').Substring(0, 16).ToLowerInvariant()
    } finally { $sha.Dispose() }
    return [pscustomobject]@{ Signature = $sig; Count = $items.Count }
}

function WcsTvUpgrade-CopyItem($Source, $DestDir) {
    # 返回 @{ files=; bytes= } 或 $null
    try {
        if (!(Test-Path -LiteralPath $Source)) { return $null }
        $name = Split-Path -Leaf $Source
        $target = Join-Path $DestDir $name
        $src = Get-Item -LiteralPath $Source -Force
        if ($src.PSIsContainer) {
            if (!(Test-Path -LiteralPath $target)) { New-Item -ItemType Directory -Force -Path $target | Out-Null }
            $files = 0; $bytes = 0
            foreach ($f in Get-ChildItem -LiteralPath $Source -Recurse -File -Force -ErrorAction SilentlyContinue) {
                $rel = $f.FullName.Substring($src.FullName.Length).TrimStart('\', '/')
                $dst = Join-Path $target $rel
                $dstParent = Split-Path -Parent $dst
                if ($dstParent -and !(Test-Path -LiteralPath $dstParent)) { New-Item -ItemType Directory -Force -Path $dstParent | Out-Null }
                Copy-Item -LiteralPath $f.FullName -Destination $dst -Force -ErrorAction SilentlyContinue
                $files++; $bytes += $f.Length
            }
            return [pscustomobject]@{ files = $files; bytes = $bytes }
        }
        $dstParent = Split-Path -Parent $target
        if ($dstParent -and !(Test-Path -LiteralPath $dstParent)) { New-Item -ItemType Directory -Force -Path $dstParent | Out-Null }
        Copy-Item -LiteralPath $Source -Destination $target -Force -ErrorAction SilentlyContinue
        return [pscustomobject]@{ files = 1; bytes = $src.Length }
    } catch { return $null }
}

function WcsTvUpgrade-BackupUserData($DataRoot, $Label, $Events) {
    try {
        $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
        $root = Join-Path $DataRoot $script:WcsTvUpgradeBackupDir
        if (!(Test-Path -LiteralPath $root)) { New-Item -ItemType Directory -Force -Path $root | Out-Null }
        $dest = Join-Path $root ("{0}_{1}" -f $Label, $stamp)
        if (!(Test-Path -LiteralPath $dest)) { New-Item -ItemType Directory -Force -Path $dest | Out-Null }
        $files = 0; $bytes = 0
        foreach ($name in $script:WcsTvUpgradeBackupFiles) {
            $r = WcsTvUpgrade-CopyItem (Join-Path $DataRoot $name) $dest
            if ($r) { $files += $r.files; $bytes += $r.bytes }
        }
        foreach ($name in $script:WcsTvUpgradeBackupDirs) {
            $r = WcsTvUpgrade-CopyItem (Join-Path $DataRoot $name) $dest
            if ($r) { $files += $r.files; $bytes += $r.bytes }
        }
        $counts = [pscustomobject]@{
            canvases = @(Get-ChildItem -LiteralPath (Join-Path $DataRoot 'canvases') -Filter *.json -File -ErrorAction SilentlyContinue).Count
            skills   = @(Get-ChildItem -LiteralPath (Join-Path $DataRoot 'canvas_agent_skills') -File -ErrorAction SilentlyContinue).Count
        }
        $manifest = [pscustomobject]@{
            created_at = (Get-Date).ToString('o')
            label      = $Label
            app_dir    = $DataRoot
            files      = $files
            bytes      = $bytes
            counts     = $counts
        }
        WcsTvUpgrade-WriteJson (Join-Path $dest 'manifest.json') $manifest | Out-Null
        if ($Events) { $Events.Add(("upgrade backup created: {0} (files={1} bytes={2} canvases={3} skills={4})" -f $dest, $files, $bytes, $counts.canvases, $counts.skills)) }
        return [pscustomobject]@{ path = $dest; files = $files; bytes = $bytes; counts = $counts }
    } catch {
        if ($Events) { $Events.Add("upgrade backup failed: $($_.Exception.Message)") }
        return $null
    }
}

function WcsTvUpgrade-IsOwnBackup($Dir) {
    # 只认自己写的 manifest（必须同时有 label / files / counts 三个键）。
    # 用户数据里可能有别的机制留下的目录（例如旧版 WcsTV 的升级刷新记录，只有
    # refresh_reason/backed_up/purged_caches）——那些一律不碰、不删。
    try {
        $m = Join-Path $Dir.FullName 'manifest.json'
        if (!(Test-Path -LiteralPath $m)) { return $false }
        $d = WcsTvUpgrade-ReadJson $m
        if (!$d) { return $false }
        $names = @($d.PSObject.Properties.Name)
        foreach ($need in @('label', 'files', 'counts')) {
            if ($names -notcontains $need) { return $false }
        }
        return $true
    } catch { return $false }
}

function WcsTvUpgrade-PruneBackups($DataRoot, $Events) {
    try {
        $root = Join-Path $DataRoot $script:WcsTvUpgradeBackupDir
        if (!(Test-Path -LiteralPath $root)) { return }
        $all = @(Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue)
        $mine = @($all | Where-Object { WcsTvUpgrade-IsOwnBackup $_ } | Sort-Object LastWriteTime -Descending)
        $foreign = $all.Count - $mine.Count
        if ($foreign -gt 0 -and $Events) { $Events.Add("upgrade backup prune: skipped $foreign foreign director(ies) (not created by this helper)") }
        if ($mine.Count -le $script:WcsTvUpgradeKeepBackups) { return }
        foreach ($old in $mine[$script:WcsTvUpgradeKeepBackups..($mine.Count - 1)]) {
            try { Remove-Item -LiteralPath $old.FullName -Recurse -Force -ErrorAction SilentlyContinue } catch { }
            if ($Events) { $Events.Add("upgrade backup pruned (own): $($old.FullName)") }
        }
    } catch { }
}

function WcsTvUpgrade-CountUserData($DataRoot) {
    return [pscustomobject]@{
        canvases = @(Get-ChildItem -LiteralPath (Join-Path $DataRoot 'canvases') -Filter *.json -File -ErrorAction SilentlyContinue).Count
        skills   = @(Get-ChildItem -LiteralPath (Join-Path $DataRoot 'canvas_agent_skills') -File -ErrorAction SilentlyContinue).Count
    }
}

function WcsTvUpgrade-TestJsonFile($Path) {
    if (!(Test-Path -LiteralPath $Path)) { return 'missing' }
    try {
        $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
        if ([string]::IsNullOrWhiteSpace($raw)) { return 'empty' }
        $null = $raw | ConvertFrom-Json
        return 'ok'
    } catch { return 'corrupt' }
}

function WcsTvUpgrade-RestoreFromBackup($DataRoot, $RelPath, $Events) {
    try {
        $root = Join-Path $DataRoot $script:WcsTvUpgradeBackupDir
        if (!(Test-Path -LiteralPath $root)) { return $false }
        $dirs = @(Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)
        foreach ($d in $dirs) {
            $cand = Join-Path $d.FullName $RelPath
            if (!(Test-Path -LiteralPath $cand)) { continue }
            # 关键：候选副本自己也得能解析，否则（比如刚做的那份备份里装的就是坏文件）
            # 继续往前找；找不到任何可解析副本时明确告警。
            if ($RelPath.ToLowerInvariant().EndsWith('.json')) {
                if ((WcsTvUpgrade-TestJsonFile $cand) -ne 'ok') {
                    if ($Events) { $Events.Add("backup copy unusable (not parseable): $RelPath in $($d.Name), trying older backup") }
                    continue
                }
            }
            $target = Join-Path $DataRoot $RelPath
            $parent = Split-Path -Parent $target
            if ($parent -and !(Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
            Copy-Item -LiteralPath $cand -Destination $target -Force -ErrorAction SilentlyContinue
            if ($Events) { $Events.Add("user data restored: $RelPath <- $($d.FullName)") }
            return $true
        }
        return $false
    } catch { return $false }
}

function Invoke-WcsTvUpgradeSafety {
    param(
        [Parameter(Mandatory = $false)][string]$AppDir = '',
        [Parameter(Mandatory = $false)][string]$UserDataRoot = '',
        [Parameter(Mandatory = $false)][string[]]$ArtifactPaths = @()
    )
    $Events = New-Object System.Collections.Generic.List[string]
    $result = [pscustomobject]@{
        Events          = @()
        Upgraded        = $false
        BaselineCreated = $false
        Version         = ''
        PreviousVersion = ''
        BackupPath      = ''
    }
    $mutex = $null
    $held = $false
    try {
        if ([string]::IsNullOrWhiteSpace($UserDataRoot)) { $result.Events = @('upgrade safety skipped: no user data root'); return $result }
        $DataRoot = Join-Path $UserDataRoot 'data'
        try {
            $mutex = New-Object System.Threading.Mutex($false, 'MyridTV_UpgradeSafety')
            $held = $mutex.WaitOne(2000)
        } catch { $held = $true }
        if (!$held) {
            $result.Events = @('upgrade safety skipped: another instance is checking')
            return $result
        }
        if (!(Test-Path -LiteralPath $DataRoot)) { New-Item -ItemType Directory -Force -Path $DataRoot | Out-Null }

        $version = WcsTvUpgrade-AppVersion $AppDir
        $sig = WcsTvUpgrade-Signature $AppDir $ArtifactPaths
        $statePath = Join-Path (Join-Path $DataRoot $script:WcsTvUpgradeStateDir) $script:WcsTvUpgradeStateFile
        $state = WcsTvUpgrade-ReadJson $statePath
        $result.Version = $version

        $currentCounts = WcsTvUpgrade-CountUserData $DataRoot
        if (!$state -or ![string]$state.signature) {
            $now = [pscustomobject]@{
                signature     = $sig.Signature
                artifacts     = $sig.Count
                version       = $version
                created_at    = (Get-Date).ToString('o')
                checked_at    = (Get-Date).ToString('o')
                last_upgrade  = ''
                upgrade_count = 0
                counts        = $currentCounts
                history       = @()
            }
            WcsTvUpgrade-WriteJson $statePath $now | Out-Null
            $result.BaselineCreated = $true
            $Events.Add(("upgrade baseline created version={0} artifacts={1}" -f $version, $sig.Count))
            $result.Events = $Events.ToArray()
            return $result
        }

        $prevVersion = [string]$state.version
        $result.PreviousVersion = $prevVersion
        $sameVersion = ($prevVersion -eq $version)
        $sameSig = ([string]$state.signature -eq $sig.Signature)
        if ($sameVersion -and $sameSig) {
            $Events.Add(("upgrade check ok version={0} artifacts={1} (no change)" -f $version, $sig.Count))
            # 顺手把 checked_at 更新掉（失败也无所谓）
            try {
                $state.checked_at = (Get-Date).ToString('o')
                $state.artifacts = $sig.Count
                $state.counts = $currentCounts
                WcsTvUpgrade-WriteJson $statePath $state | Out-Null
            } catch { }
            $result.Events = $Events.ToArray()
            return $result
        }

        # ---- 检测到升级/文件被替换 ----
        $result.Upgraded = $true
        $Events.Add(("upgrade detected: version {0} -> {1}, artifacts changed={2}" -f $prevVersion, $version, (!$sameSig)))
        $label = if ($version) { $version -replace '[^0-9A-Za-z\.\-_]', '' } else { 'unknown' }
        $backup = WcsTvUpgrade-BackupUserData $DataRoot $label $Events
        if ($backup) { $result.BackupPath = $backup.path }

        # 完整性体检：坏掉的 JSON 从备份取回（没有备份可取就明确告警）
        foreach ($rel in $script:WcsTvUpgradeJsonFiles) {
            $status = WcsTvUpgrade-TestJsonFile (Join-Path $DataRoot $rel)
            if ($status -eq 'corrupt' -or $status -eq 'empty') {
                $Events.Add(("user data $status after upgrade: $rel"))
                if (!(WcsTvUpgrade-RestoreFromBackup $DataRoot $rel $Events)) {
                    $Events.Add("restore unavailable for $rel (no backup copy)")
                }
            }
        }
        $canvasDir = Join-Path $DataRoot 'canvases'
        if (Test-Path -LiteralPath $canvasDir) {
            foreach ($f in Get-ChildItem -LiteralPath $canvasDir -Filter *.json -File -ErrorAction SilentlyContinue) {
                $status = WcsTvUpgrade-TestJsonFile $f.FullName
                if ($status -eq 'corrupt' -or $status -eq 'empty') {
                    $Events.Add(("canvas file $status after upgrade: $($f.Name)"))
                    if (!(WcsTvUpgrade-RestoreFromBackup $DataRoot ("canvases\{0}" -f $f.Name) $Events)) {
                        $Events.Add("restore unavailable for canvases\$($f.Name)")
                    }
                }
            }
        }

        # 缩水体检：与"上一次运行记录的数量"比（那才是升级前的状态）→ 只说事实并给路径，绝不自动删改
        $prevCounts = $state.counts
        if ($prevCounts) {
            $backupPathText = if ($backup) { $backup.path } else { '(no backup)' }
            if ($null -ne $prevCounts.canvases -and $currentCounts.canvases -lt [int]$prevCounts.canvases) {
                $Events.Add(("WARNING user data shrank: canvases {0} -> {1}; restore from {2}" -f $prevCounts.canvases, $currentCounts.canvases, $backupPathText))
            }
            if ($null -ne $prevCounts.skills -and $currentCounts.skills -lt [int]$prevCounts.skills) {
                $Events.Add(("WARNING user data shrank: skills {0} -> {1}; restore from {2}" -f $prevCounts.skills, $currentCounts.skills, $backupPathText))
            }
        }

        # 写回状态
        $history = @()
        if ($state.history) { $history = @($state.history) }
        $entry = ("{0} -> {1} @ {2}" -f $prevVersion, $version, (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
        $history = @($entry) + $history
        if ($history.Count -gt 5) { $history = $history[0..4] }
        $count = 0
        if ($state.upgrade_count) { $count = [int]$state.upgrade_count }
        $newState = [pscustomobject]@{
            signature     = $sig.Signature
            artifacts     = $sig.Count
            version       = $version
            created_at    = if ($state.created_at) { [string]$state.created_at } else { (Get-Date).ToString('o') }
            checked_at    = (Get-Date).ToString('o')
            last_upgrade  = (Get-Date).ToString('o')
            upgrade_count = ($count + 1)
            counts        = $currentCounts
            history       = $history
        }
        WcsTvUpgrade-WriteJson $statePath $newState | Out-Null
        WcsTvUpgrade-PruneBackups $DataRoot $Events
        $Events.Add("upgrade safety done: user data verified, backup kept at $($result.BackupPath)")
        $result.Events = $Events.ToArray()
        return $result
    } catch {
        try { $Events.Add("upgrade safety error: $($_.Exception.Message)") } catch { }
        $result.Events = $Events.ToArray()
        return $result
    } finally {
        if ($mutex) {
            try { if ($held) { $mutex.ReleaseMutex() } } catch { }
            try { $mutex.Dispose() } catch { }
        }
    }
}

# publish-all.ps1
# Publish signed static update to GitHub AND mirror to Gitee in one command.
# Scope: runbook step 6 (GitHub) + Gitee file-tree mirror.
# Prereqs (runbook steps 1-5): bump VERSION, tests/verify.ps1 PASSED, git commit,
#   .\installer\build-installer.ps1, and installer\build\update-release\ must exist
#   (produced by installer\make-update-release.py with --previous).
# Usage (from repo root D:\APP\MyridTV):
#   .\installer\publish-all.ps1                      # auto-detect version, mirror Gitee
#   .\installer\publish-all.ps1 -SkipGitee          # GitHub only (no GITEE_TOKEN)
#   .\installer\publish-all.ps1 -Version V0.10.10    # force version
# Requires: gh CLI logged in, GITEE_TOKEN env (unless -SkipGitee).

param(
    [string]$Version = "",
    [string]$Repo = "dearxiaozhou/MyridTV-updates",
    [string]$Out = "installer\build\update-release",
    [string]$GiteeOwner = "myridtv",
    [string]$GiteeRepo = "myrid-tv-updates",
    [string]$CacheDir = "",
    [switch]$SkipGitee
)

$repoRoot = Split-Path $PSScriptRoot -Parent
$Out = Join-Path $repoRoot $Out

if (-not (Test-Path $Out)) {
    throw "update-release dir not found: $Out`nRun installer\make-update-release.py first (runbook step 5)."
}

# --- resolve version ---
if (-not $Version) {
    $manifestFile = Join-Path $Out "update-manifest.json"
    if (Test-Path $manifestFile) {
        $Version = (Get-Content $manifestFile -Raw | ConvertFrom-Json).version
    } else {
        $vf = Join-Path $repoRoot "installer\build\MyridTV\VERSION"
        if (Test-Path $vf) { $Version = (Get-Content $vf -Raw).Trim() }
    }
}
if (-not $Version) { throw "cannot determine version; pass -Version Vx.y.z" }
Write-Host "==> Publishing $Version to GitHub ($Repo) + Gitee ($GiteeOwner/$GiteeRepo)"

# --- step 6a: tag on the updates repo master ---
$sha = gh api "repos/$Repo/commits/master" --jq '.sha'
if ($sha) {
    gh api "repos/$Repo/git/refs" -X POST -f "ref=refs/tags/$Version" -f "sha=$sha" 2>$null
    Write-Host "    tag $Version -> $sha (ignored if exists)"
}

# --- step 6b: draft release ---
gh release create $Version --repo $Repo `
    --title "MyridTV static update $Version" `
    --notes "Front-end static resources only (html/css/js); no Python source. Unchanged files reuse this Release's URL in later versions. Do not delete." `
    --draft 2>$null
Write-Host "    draft release created (ignored if exists)"

# --- step 6c: upload blobs with retry for network jitter ---
$ok = 0; $fail = 0
Get-ChildItem $Out -Filter "blob-*" | ForEach-Object {
    if (gh release upload $Version $_.FullName --repo $Repo --clobber 2>$null) { $ok++ } else { $fail++ }
}
Write-Host "    initial upload: ok=$ok fail=$fail"

for ($round = 1; $round -le 5; $round++) {
    $remote = (gh release view $Version -R $Repo --json assets --jq '.assets[].name')
    $local  = (Get-ChildItem $Out -Filter "blob-*").Name
    $missing = Compare-Object $local $remote | Where-Object SideIndicator -eq '<=' | ForEach-Object InputObject
    if (-not $missing) { Write-Host "    all blobs present"; break }
    Write-Host "    round ${round}: backfill $($missing.Count) missing"
    $missing | ForEach-Object { gh release upload $Version "$Out\$_" -R $Repo --clobber 2>$null }
    Start-Sleep 3
}

# --- step 6d: manifest + publish ---
gh release upload $Version (Join-Path $Out "update-manifest.json") --repo $Repo --clobber
gh release edit $Version --repo $Repo --draft=false `
    --title "MyridTV static update $Version" `
    --notes "Front-end static resources only (html/css/js); no Python source. Unchanged files reuse this Release's URL in later versions. Do not delete."
Write-Host "    GitHub release $Version is LIVE"

# --- Gitee mirror (file tree + raw) ---
if ($SkipGitee) {
    Write-Host "==> -SkipGitee set, skipped Gitee mirror."
    return
}
if (-not $env:GITEE_TOKEN) {
    Write-Warning "GITEE_TOKEN not set; skipping Gitee mirror. Set it and re-run to sync backup repo."
    return
}

$mirrorPy = Join-Path $repoRoot "installer\mirror_to_gitee.py"
$mirrorArgs = @($mirrorPy, "--tag", $Version)
if ($CacheDir) { $mirrorArgs += @("--cache-dir", $CacheDir) }

$done = $false
for ($i = 1; $i -le 3 -and -not $done; $i++) {
    try {
        Write-Host "==> Gitee mirror attempt $i ..."
        & python @mirrorArgs
        if ($LASTEXITCODE -eq 0) { $done = $true }
        else { Write-Warning "mirror exited $LASTEXITCODE" }
    } catch {
        Write-Warning "mirror attempt $i failed: $_"
    }
    if (-not $done) { Start-Sleep 5 }
}
if ($done) {
    Write-Host "==> DONE. Both platforms synced for $Version."
} else {
    Write-Warning "Gitee mirror did not complete after retries. GitHub release is live; re-run publish-all.ps1 to sync backup."
}

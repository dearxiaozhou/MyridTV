# MyridTV 发版清单（安装包 + 增量更新）

写给老王照着做。两条线要一起走：**安装包**给新用户装，**增量更新**给已装的老用户升级。
只走其中一条会造成"新装的能用自动更新，但老用户拿不到新功能"。

---

## 当前状态（2026-10-06 13:35 核实）

| 项 | 值 |
|---|---|
| 仓库 `VERSION` | **V0.10.0** |
| 磁盘上的 Setup | **10-05 20:08 的 V0.9.14**（470MB，**不含今天任何改动**） |
| 公网增量通道 | V0.9.20 已发布，156 资产（155 blob + 1 manifest） |
| 更新仓库 | `dearxiaozhou/MyridTV-updates`（公开，tag `V0.9.20` 已建） |

---

## 铁律（先看这 7 条，踩了就白干）

1. **一定要重打安装包。** 今天改了 `myridtv_updater.py`、`rh_official_proxy.py`、`start_myridtv.ps1`、`index.html` —— 这些**只在安装包里**。磁盘那颗 20:08 的包是 V0.9.14，**装它等于没做**。
2. **VERSION 要先改再打包。** `build-installer.ps1` 读 `VERSION` 注入版本号，两个 csproj 也要同步（下面步骤里有）。
3. **绝不能删历史 Release。** 未变化的文件在清单里沿用**旧版本**的下载地址。跳过多版更新的客户端会去老 Release 拉，删了它那些用户直接更新失败。
4. **`--previous` 必须传。** 不传会生成全量基线，客户端第一次更新就下载全部 155 个文件。
5. **私钥不进包、不进 Git。** `installer/build/update-signing.key` 已被 `.gitignore` 的 `installer/build/` 挡住，**别动这个规则**。
6. **公网只发前端静态资源。** 不含 Python 源码。后端 `.py` 改了只能靠重装安装包。
7. **发版前跑一次自检。** `tests/verify.ps1` 六道门禁（17 分钟）。挂了就别发。

### ⚠️ 最容易中招的一条：新增前端文件必须先 commit

`make-update-release.py` 靠 `git ls-files` 决定打包哪些文件。**新加的、还没 `git add` 的 `.js`/`.css` 会被静默跳过**——不报错、不警告，只是用户更新后少了这些功能。

```powershell
# 发版前自查：有没有未跟踪的前端文件
git status --porcelain | Select-String '^\?\?.*_internal/static'
# 有输出 → 先 commit，别急着打包
```

（今天实际踩过：codex 新增了 13 个前端模块，211 项改动没提交，打包前必须先提交否则这些功能全丢。）

---

## 第 1 步：改版本号

**唯一事实源是仓库根目录的 `VERSION`**（`build-installer.ps1` 读它注入版本号）。

两个 csproj（Launcher / Desktop）里的 `0.10.0` 需与 `VERSION` 一致。**先查现状再改**：

```powershell
cd D:\APP\MyridTV
cat VERSION
Select-String -Path installer\launcher\MyridTV.Launcher.csproj,installer\desktop\MyridTV.Desktop.csproj -Pattern '<Version>'
```

若需要改（把 `0.9.x` 批量替换为目标版本号）：

```powershell
$num = "0.10.0"   # 不带 V
foreach ($f in @("installer\launcher\MyridTV.Launcher.csproj", "installer\desktop\MyridTV.Desktop.csproj")) {
    (Get-Content $f -Raw) -replace '<\d+\.\d+\.\d+>', "<$num>" | Set-Content $f -NoNewline
}
```

> 💡 2026-10-06 实测：codex 已经把 `VERSION` 和两个 csproj 都同步到 `0.10.0` 了，**这一步多半不用动**，查一下确认即可。

---

## 第 2 步：跑自检

```powershell
$env:MYRIDTV_PYTHON_EXE = "C:\Users\77972\AppData\Local\Programs\Python\Python313\python.exe"
powershell -NoProfile -ExecutionPolicy Bypass -File tests\verify.ps1
```

**必须看到 `verify PASSED`**（含 63 个画布 e2e 全绿）。失败就别往下走。

> 💡 pre-commit 钩子会调这个脚本，17 分钟超时会挂。所以**提交时用 `git commit --no-verify`**，但前提是你刚手动跑过并看到 PASSED。

---

## 第 3 步：提交

```powershell
git add -A
git status --short# 确认没有敏感文件
git commit --no-verify -m "release: V0.10.0"
```

**提交前必查**：

```powershell
# 有没有把密钥/日志/临时产物加进去
git diff --cached --name-only | Select-String -Pattern '\.key|\.pem|\.pfx|_verification|\.log$'
# 有输出就是有问题，先git reset 再处理
```

> `_verification/` 已在 `.gitignore`（我加的），`installer/build/` 也已忽略。正常应该没输出。

---

## 第 4 步：打安装包

### 4.0 先跑隐私预检（能省 20 分钟）

打包炸过两次，都是隐私门控。**先跑这个预检，1 分钟出结果**：

```powershell
python "C:\Users\77972\WorkBuddy\无限画布\outputs\_preflight_privacy.py"
```

它逐字节读（含 UTF-16）模拟 `Assert-ReleasePrivacy`，扫所有会被打进包的文件：

- `[PASS] 无机器路径泄漏` → 直接往下打
- `[FAIL] 发现 N 处泄漏` → 会列出具体文件 + 命中的路径串，按 4.1 的说明处理

> ⚠️ **为什么必须用 Python 扫**：workflow 的 `.config.json` 是 **UTF-16** 编码，系统 `grep` 当二进制跳过 → **假阴性**（漏检）。而且 JSON 转义是**双反斜杠** `C:\\Users\\`，单反斜杠 grep 匹配不到。10-05 两次门控失败都是这么漏掉的。

### 4.1 正式打包

```powershell
.\installer\build-installer.ps1
```

**17-20 分钟。**

**如果报 `Release privacy check failed`**：说明有文件含你机器的绝对路径。按名字找到它，两种处理：

- 是 dev 产物（截图/调试 JSON）→ 加进 `installer\prepare-release.ps1` 的排除清单
- 是要发布的正经文件 → 改成相对路径

已排除的（别重复加）：`style-preview-*.json`、`style-preview-records/`、`_internal\workflows\custom\`、根级下划线开头文件（`_patch_*.json` 等）、全树 `.cmd/.bat/.vbs/.wsf`、根级 `.txt`。

> 📌 **排除规则的三个坑**（10-05~10-06 实测）：
> - **`.bat`/`.cmd` 是不限层级排除**（`prepare-release.ps1:163-166` 只判扩展名），但 `.txt` **只排根级**（`:149`）。写预检脚本时容易搞混。
> - **根级下划线规则只在 `-AppRoot` 判定时生效**（`:126`），且 `_internal` 目录本身要豁免。
> - **`style-` 与 `style_` 是两条规则**：`:161` 排 `style_`（下划线），根目录那批 `style-preview-*.json` 是连字符，靠 `:132` 单独一条。别以为一条就够。


**产物**：`installer\build\installer\MyridTV-Setup.exe`
**确认**：

```powershell
ls -la installer\build\installer\MyridTV-Setup.exe
cat installer\build\MyridTV\VERSION      # 应等于你设的版本号
```

---

## 第 5 步：生成增量更新包

安装包打好后，`installer\build\MyridTV\` 就是最新快照。**要先下载上一版清单做基线**：

```powershell
# 5a) 拿上一版签名清单（客户端靠它复用未变文件的地址）
Invoke-WebRequest `
  'https://github.com/dearxiaozhou/MyridTV-updates/releases/latest/download/update-manifest.json' `
  -OutFile installer\build\previous-update-manifest.json

# 5b) 签名密钥。key 文件里是 44 字符 base64 串，脚本要的就是它原样
$env:MYRIDTV_UPDATE_SIGNING_KEY = (Get-Content installer\build\update-signing.key -Raw).Trim()

# 5c) 生成
python installer\make-update-release.py `
  --stage installer\build\MyridTV `
  --out   installer\build\update-release `
  --repo  dearxiaozhou/MyridTV-updates `
  --previous installer\build\previous-update-manifest.json
```

**期望输出**：`{"version": "V0.10.0", "files": 155, "new_blobs": N, "new_bytes": ...}`

| 字段 | 含义 |
|---|---|
| `files: 155` | 可更新文件总数（固定，前端资源就这么多） |
| `new_blobs: N` | 本次**新增/变化**的 blob 数。**这才是真实增量** |
| `new_bytes` | 本次要下载的字节数 |

> 💡 **怎么判断增量是否正常**：
> - 传了 `--previous` 且只改了几个文件 → `new_blobs` 应是**个位数到几十**，远小于 155。
> - `new_blobs` 接近 155 → 说明几乎全变了（改了很多前端，或上次基线太老）。
> - `new_blobs` 正好 155 → 只在**首个基线版本**（无 `--previous`）时正常；有`--previous` 时出现说明复用逻辑没生效，要查`git ls-files` 是否漏了文件。
>
> 关键前提：`make-update-release.py` **只打包 `git ls-files` 输出里、且存在于 stage 的文件**。所以**新加的前端文件必须先 `git add` 提交**，否则会被静默跳过，用户更新后缺功能。

> ⚠️ **密钥坑**：`update-signing.key` 里存的是 44 字符 base64 串（解码得 32 字节私钥）。`MYRIDTV_UPDATE_SIGNING_KEY` 要的是**这 44 个字符本身**，不要额外base64 一次。多编码会报 `ValueError: An Ed25519 private key is 32 bytes long`。

**依赖**：`python -c "import cryptography"` 必须成功。没装：`python -m pip install cryptography`。

---

## 第 6 步：推上公网

**6a) 先建 tag**（草稿 release 缺 tag 会报 `tag_name is not a valid tag`）：

```powershell
$V = "V0.10.0"   # 改成你的版本号
$SHA = gh api repos/dearxiaozhou/MyridTV-updates/commits/master --jq '.sha'
gh api repos/dearxiaozhou/MyridTV-updates/git/refs -X POST `
   -f ref="refs/tags/$V" -f sha=$SHA
```

**6b) 建草稿 release**：

```powershell
gh release create $V --repo dearxiaozhou/MyridTV-updates `
  --title "MyridTV 静态更新 $V" `
  --notes "仅前端静态资源，不含 Python 源码。请勿删除本 Release。" `
  --draft
```

**6c) 逐个上传**（**别一次传 156 个**，会撞名报 `HTTP 422 already exists`）：

```powershell
$OUT = "installer\build\update-release"
$ok = 0; $fail = 0
Get-ChildItem $OUT -Filter "blob-*" | ForEach-Object {
    if (gh release upload $V $_.FullName --repo dearxiaozhou/MyridTV-updates --clobber 2>$null) { $ok++ } else { $fail++ }
}
"成功 $ok / 失败 $fail"
```

**网络抖动的处理**：失败的**重试就就好**，不是文件问题：

```powershell
# 循环几轮，只补缺失的
for ($round = 1; $round -le 5; $round++) {
    $remote = (gh release view $V -R dearxiaozhou/MyridTV-updates --json assets --jq '.assets[].name')
    $local  = (Get-ChildItem $OUT -Filter "blob-*").Name
    $missing = Compare-Object $local $remote | Where-Object SideIndicator -eq '<=' | ForEach-Object InputObject
    if (-not $missing) { "全部就位"; break }
    "第 $round 轮补 $($missing.Count) 个"
    $missing | ForEach-Object { gh release upload $V "$OUT\$_" -R dearxiaozhou/MyridTV-updates --clobber 2>$null }
    Start-Sleep 3
}
```

**6d) 传清单 + 转正式**：

```powershell
gh release upload $V "$OUT\update-manifest.json" --repo dearxiaozhou/MyridTV-updates --clobber

gh release edit $V --repo dearxiaozhou/MyridTV-updates --draft=false `
  --title "MyridTV 静态更新 $V" `
  --notes "仅前端静态资源（html/css/js），不含 Python 源码。未变文件在后续版本沿用本 Release 地址，请勿删除。"
```

---

## 第 7 步：验证

**7a) 确认远端完整**：

```powershell
gh release view $V -R dearxiaozhou/MyridTV-updates --json isDraft,assets --jq '"draft=\(.isDraft) 资产=\(.assets|length)"'
# 期望：draft=False 资产=<blob数+1>
```

**7b) 端到端验签**（现成脚本，会拉公网清单、验签、试篡改、比对blob 字节）：

```powershell
cd D:\APP\MyridTV
python "C:\Users\77972\WorkBuddy\无限画布\outputs\_verify_update_e2e.py"
```

**期望输出**：
```
1) 拉取公网清单 ...  版本=V0.10.0  文件数=155
2) 用内置公钥验签 ...  签名有效 (Ed25519)
3) 篡改检测 ...  篡改被正确拒绝
4) 下载并比对 3 个 blob 字节 ...  OK ...
E2E_PASS
```

**7c) 真机验更新**（只能在你装好的机器上做）：

装第 4 步打出的包 → 启动 → **点底部版本号** → 应弹出提示。

- 有新版本：右下角提示"界面已更新到 Vx，可在保存后刷新"
- 已是最新：提示"当前已是最新版本"
- 检查中：版本号变`…` 且不可连点

**启动器自动检查**（发布版才有，源码目录不会自动更新因为有 `.git`）：
看 `%APPDATA%\MyridTV\data\logs\updater.err.log` 有没有报错。

---

## 一页速查

```
1. 改 VERSION + 两个 csproj
2. verify.ps1→ 必须 PASSED
3. git commit --no-verify（提交前查敏感文件）
4. .\installer\build-installer.ps1→ 17-20 分钟
5. 下载 previous 清单 → make-update-release.py（带 --previous）
6. 建 tag → 建草稿 release → 逐个上传 → 转正式
7. _verify_update_e2e.py 验签 → 装包点版本号验真机
```

---

## 常见故障速查

| 报错 | 原因 | 解决 |
|---|---|---|
| `Release privacy check failed` | 有文件含 `C:\Users\` 绝对路径 | 加进 `prepare-release.ps1` 排除清单 |
| `tag_name is not a valid tag` | 草稿 release 没有 git tag | 先 `gh api .../git/refs` 建 tag |
| `HTTP 422 already exists` | 一次传了太多文件 | 先建草稿，逐个 `upload --clobber` |
| `An Ed25519 private key is 32 bytes long` | 密钥多 base64 编码了一层 | 用 key 文件的 44 字符原样 |
| `must increase` | 新版本号 ≤ 上一版 | 升 VERSION |
| `remote error: tls: bad record MAC` | 网络抖动/代理不稳 | 重试；本机批量操作时常见 |
| `release version must increase` | 同上 | 检查 VERSION 排序 |
| 客户端提示"检查更新失败" | `updater.err.log` 有详情 | 启动器没起：确认安装目录无 `.git` |

---

## 边界（必须知道，否则会误解）

- **自动更新只更新前端 HTML/CSS/JS。** 后端 `.py` 变了必须重装安装包。
- **源码目录不自动更新**（含 `.git`），这是保护你的开发改动不被覆盖。
- **前端代码在浏览器里永远可查看**，这是网页应用的固有属性，无法回避。
- **公网不含 Python 源码**，但安装包解压后 `.py` 是可读的（未编译）——所以**别把安装包公开撒出去**。

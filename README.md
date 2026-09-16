# MyridTV

Windows 本地运行的 AI 无限画布应用。节点式编排 + 本地后端 + 可选接本机 ComfyUI 出图。

## 跑起来

**开发态**（改代码日常用这个）：

```
启动研发版.cmd
```

内部调 `dev-start.ps1`，拉起后端并打开画布。停服用 `停止MyridTV.cmd` 或 `stop-myridtv.ps1`。

**用户态**：装 `MyridTV-Setup.exe`，从开始菜单启动。

## 结构

| 位置 | 是什么 |
|---|---|
| `_internal/static/` | 前端。**手写多页 HTML/CSS/JS，源码即产物，没有构建步骤** |
| `rh_official_proxy.py` | 后端主进程，默认 `http://127.0.0.1:3107` |
| `installer/desktop/` | 桌面壳，.NET 9 + WebView2 |
| `installer/launcher/` | 启动器 |
| `installer/` | 打包脚本（prepare-release / build-installer / signing） |
| `tests/verify.ps1` | 自检基线，改完代码跑这个 |

出图依赖**本机 ComfyUI**，默认地址 `http://127.0.0.1:8188`。发布包内嵌便携 Python 3.13。

## 开发约定

### 1. 改完先自检

```
powershell -NoProfile -ExecutionPolicy Bypass -File tests\verify.ps1
```

五道检查：Python 语法 → 前端 JS 语法 → i18n 键 → 悬空名字 → 单测（含 `tests/agent-e2e/` 子目录）。

`core.hooksPath` 指向 `.githooks`，**提交时会自动跑，红了就提交不了**。

### 2. 改代码必须推版本号，且四处同步

按 `AGENTS.md` 的 Version Rule，patch 小于 20 时 +1，等于 20 时进到 `Vx.(y+1).0`。四个地方必须一起改：

- `VERSION`
- `_internal/static/index.html` 里的 `版本：Vx.y.z` 徽章
- `installer/desktop/MyridTV.Desktop.csproj`
- `installer/launcher/MyridTV.Launcher.csproj`

> 后两个 `.csproj` 最容易漏（各 4 个字段：`Version` / `FileVersion` / `AssemblyVersion` / `InformationalVersion`）。漏改不会报错，但安装包里的程序集版本会跟界面显示对不上。

### 3. i18n 键要注册

前端新增 `tr('xxx')` 后，必须在 `_internal/static/js/i18n/` 下注册 zh / en 两个版本，否则 i18n 校验会红。

### 4. 发布包不许带本机信息

`installer/prepare-release.ps1` 里有硬门禁：扫描暂存目录，任何文件里出现「Windows 用户主目录的绝对路径」或「本项目开发目录的绝对路径」，直接中断打包。检测的是**路径形状**而不是某个固定用户名，所以换机器、换人打包照样拦得住。这不是可选项。

> 坑：写文档时**不要原样抄这两个探测串**。README 本身也在扫描范围内，抄了就会把自己拦下（CI 上真发生过：自检全绿、打包却死在 README.md）。用中文描述即可。

## 打包

```
installer\build-installer.ps1 -PythonDir "<Python 3.13 安装目录>"
```

需要 .NET 9 SDK 和 Inno Setup 6/7（脚本会自动找 `ISCC.exe`，找不到会提示）。

## 改动怎么提交

日常改东西先开分支，别直接往 main 上推 —— main 要始终保持能发版。

```
git switch -c fix/某个短描述
git commit -am "..."
git push -u origin fix/某个短描述
gh pr create --base main
```

PR 页面上会直接显示 CI 自检结果，红了就别合并。

## 发版

```
git tag V0.3.14
git push origin V0.3.14
```

`.github/workflows/desktop-package.yml` 有 verify / build 两个 job，触发关系是：

| 触发方式 | verify（自检） | build（出包） |
|---|---|---|
| 开 PR / 更新 PR | 跑 | 跳过 |
| push 到 main | 跑 | 跳过 |
| 打 tag | 跑 | 跑，并建 Release 挂附件 |
| 手动 Run workflow | 跑 | 跑，只出 Artifact（保留 30 天），不发 Release |

PR 上不出包是有意的：出一次安装包要 3 分钟，没必要每个 PR 都付这个成本。build 依赖 verify（`needs: verify`），自检红了就不会往下走。

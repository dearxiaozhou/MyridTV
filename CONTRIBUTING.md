# 参与贡献

感谢你愿意改进 MyridTV。这份文档说明本项目的开发约定，提交 PR 前请先过一遍。

## 环境

- Windows 10/11 x64
- 仓库已内置便携 Python 运行时与前端源码，前端没有构建步骤（手写 HTML/CSS/JS，源码即产物）
- 打包相关才需要 .NET 9 SDK 与 Inno Setup 6/7

## 改完先自检

```
powershell -NoProfile -ExecutionPolicy Bypass -File tests\verify.ps1
```

五道检查：Python 语法 → 前端 JS 语法 → i18n 键 → 悬空名字 → 单测（含 `tests/agent-e2e/`）。

`core.hooksPath` 指向 `.githooks`，提交时会自动跑，红了就提交不了。

> 本机没有 Playwright 浏览器时，可设 `MYRIDTV_SKIP_E2E=1` 跳过浏览器 e2e 段（CI 用的是同一个开关）。语法、i18n、单测仍会跑。

## 版本号规则

按 `AGENTS.md` 的 Version Rule，patch 小于 20 时 +1，等于 20 时进到 `Vx.(y+1).0`。**四个地方必须一起改**：

- `VERSION`
- `_internal/static/index.html` 里的 `版本：Vx.y.z` 徽章
- `installer/desktop/MyridTV.Desktop.csproj`
- `installer/launcher/MyridTV.Launcher.csproj`

> 后两个 `.csproj` 最容易漏（各 4 个字段：`Version` / `FileVersion` / `AssemblyVersion` / `InformationalVersion`）。漏改不会报错，但安装包里的程序集版本会跟界面显示对不上。

## i18n

前端新增 `tr('xxx')` 后，必须在 `_internal/static/js/i18n/` 下注册 zh / en 两个版本，否则 i18n 校验会红。

## 分支与 PR

日常改动先开分支，别直接往 main 上推 —— main 要始终保持能发版。

```
git switch -c fix/某个短描述
git commit -am "..."
git push -u origin fix/某个短描述
gh pr create --base main
```

PR 页面会直接显示 CI 自检结果，红了先修再合并。

提交信息建议用 conventional commits 前缀：`feat:` / `fix:` / `chore:` / `docs:` / `refactor:` / `test:`。

## 不要提交这些

- 本机绝对路径（用户主目录、开发目录）——发布门禁会直接拦下
- API Key、`.env`、证书私钥
- 运行时数据：`_internal/data/` 下的画布、会话、日志
- 构建产物：`installer/build/`、`installer/*/obj|bin`、`*.exe`

这些已在 `.gitignore` 中排除，新增规则时注意不要破坏现有排除项。

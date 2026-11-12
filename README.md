# MyridTV

Windows 本地运行的 AI 无限画布应用。节点式编排 + 本地后端 + 可选接本机 ComfyUI 出图。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 特性

- **无限画布编排**：拖拽节点、连线、分组，一套编排反复复用
- **多类节点**：提示词 / 批量生成 / 语音生成 / 视频生成 / 3D 解算 / 刚性体 / ComfyUI 生成
- **本地优先**：后端只监听本机 `127.0.0.1:3107`，任务与素材留在本地
- **可接 ComfyUI**：填一次本机 ComfyUI 目录，注册工作流后即可在画布内出图
- **多模型服务**：OpenAI 兼容协议（可接 Ollama / LM Studio 等本地模型）、RunningHub、火山引擎
- **画布内 AI 助手**：对话式改图、@ 引用素材、技能、批量任务

## 快速开始

### 方式一：安装包

运行 `MyridTV-Setup.exe` 安装，从开始菜单启动。安装包内已含便携 Python 运行时，无需另装环境。

### 方式二：从源码运行

要求 Windows 10/11 x64。仓库 `_internal/` 内已内置便携 Python 运行时与依赖，克隆即可跑。

```
启动研发版.cmd
```

内部调 `dev-start.ps1`，拉起后端并打开画布。停服用 `停止MyridTV.cmd` 或 `stop-myridtv.ps1`。

## 首次配置

### 1. 配置模型服务

打开应用内「设置 → API 配置」，新增服务商并填入 Key。Key 建议写入 `_internal/API/.env`（字段示例见 `_internal/API/.env.example`），不要硬编码进代码。

- **本地模型**：新增一个「OpenAI 兼容」服务商，请求地址填 Ollama 的 `http://127.0.0.1:11434/v1` 或 LM Studio 的 `http://127.0.0.1:1234/v1`，Key 留空，保存后点「拉取模型」。
- **云端服务**：按服务商要求填 Base URL 与 Key，再拉取模型列表。

### 2. 接本机 ComfyUI（可选）

设置 → ComfyUI → 填本机 ComfyUI 目录（例如 `D:\ComfyUI`），默认连接 `http://127.0.0.1:8188`。保存后可在画布添加「ComfyUI 生成」节点并上传自己的工作流 JSON。未启动 ComfyUI 时，顶栏状态灯为红色，点击可让后端尝试拉起。

## 项目结构

| 位置 | 是什么 |
|---|---|
| `_internal/static/` | 前端。**手写多页 HTML/CSS/JS，源码即产物，没有构建步骤** |
| `rh_official_proxy.py` | 后端主进程，默认 `http://127.0.0.1:3107` |
| `installer/desktop/` | 桌面壳，.NET 9 + WebView2 |
| `installer/launcher/` | 启动器 |
| `installer/` | 打包脚本（prepare-release / build-installer / signing） |
| `tests/verify.ps1` | 自检基线，改完代码跑这个 |

出图依赖**本机 ComfyUI**，默认地址 `http://127.0.0.1:8188`。发布包内嵌便携 Python 运行时。

## 开发

改完代码先自检：

```
powershell -NoProfile -ExecutionPolicy Bypass -File tests\verify.ps1
```

五道检查：Python 语法 → 前端 JS 语法 → i18n 键 → 悬空名字 → 单测（含 `tests/agent-e2e/` 子目录）。

`core.hooksPath` 指向 `.githooks`，**提交时会自动跑，红了就提交不了**。

提交前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)，其中有版本号规则、i18n 注册要求、分支与 PR 流程。

## 打包

```
installer\build-installer.ps1 -PythonDir "<Python 安装目录>"
```

需要 .NET 9 SDK 和 Inno Setup 6/7（脚本会自动找 `ISCC.exe`，找不到会提示）。

> 发布包不许带本机信息：`installer/prepare-release.ps1` 有硬门禁，暂存目录里任何文件出现用户主目录或本项目开发目录的绝对路径，直接中断打包。所以写文档时不要原样抄绝对路径，用中文描述即可。

## 发版

```
git tag V0.3.14
git push origin V0.3.14
```

`.github/workflows/desktop-package.yml` 有 verify / build 两个 job：

| 触发方式 | verify（自检） | build（出包） |
|---|---|---|
| 开 PR / 更新 PR | 跑 | 跳过 |
| push 到 main | 跑 | 跳过 |
| 打 tag | 跑 | 跑，并建 Release 挂附件 |
| 手动 Run workflow | 跑 | 跑，只出 Artifact（保留 30 天），不发 Release |

PR 上不出包是有意的：出一次安装包要 3 分钟，没必要每个 PR 都付这个成本。build 依赖 verify（`needs: verify`），自检红了就不会往下走。

## 安全

发现安全问题请不要公开提 issue，按 [SECURITY.md](SECURITY.md) 的方式私密报送。

## 许可

本项目源代码采用 [MIT License](LICENSE)。仓库内置的 Python 运行时与第三方库遵循各自许可，详见 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。

ComfyUI 不随本仓库分发，需自行安装。

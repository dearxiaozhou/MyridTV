# 第三方组件声明（THIRD-PARTY NOTICES）

本仓库为「克隆即可运行」内置了便携 Python 运行时与若干第三方库（vendored 于 `_internal/`）。
这些组件版权归各自作者所有，遵循各自许可证。根目录 `LICENSE`（MIT）仅覆盖 MyridTV 自有源代码，
不改变下列组件的授权条件。

| 组件 | 版本 | 上游许可证 |
|---|---|---|
| Python 运行时 | 3.10 (Windows x64) | PSF-2.0 |
| Pillow (PIL) | 12.2.0 | MIT-CMU (HPND) |
| pydantic | 2.13.4 | MIT |
| pydantic-core | 2.46.4 | MIT |
| websockets | 16.0 | BSD-3-Clause |
| click | 8.3.3 | BSD-3-Clause |
| certifi | 随包 | MPL-2.0 |
| charset-normalizer | 随包 | MIT |
| httptools | 随包 | MIT |
| pywebview | 随包 | BSD-3-Clause |
| pythonnet | 随包 | MIT |
| PyYAML | 随包 | MIT |
| ecdsa | 构建/签名期 | MIT |
| cryptography | 构建/签名期 | Apache-2.0 OR BSD-3-Clause |
| OpenSSL (`libcrypto-1_1.dll`) | 1.1.x | OpenSSL License + SSLeay License |
| three.js | 0.160.0 | MIT |
| Model Context Protocol Python SDK (`mcp`) | 随包 | MIT |
| Inno Setup | 构建期工具 | Inno Setup License |
| .NET | 9（桌面壳构建/运行） | MIT |

说明：

- 上表版本取自仓库内 `*.dist-info` 与 vendored 文件，可能随更新变化；再分发前请以各项目官方仓库的 LICENSE 原文为准。
- 仓库内 `_internal/*.dist-info/licenses/` 已保留部分组件（click / pydantic / websockets 等）的原始许可文本。
- 若你基于本仓库二次分发安装包，需自行保留并附上上述许可声明。
- ComfyUI 不随本仓库分发，MyridTV 仅通过本地 HTTP（默认 `127.0.0.1:8188`）调用用户自行安装的实例。

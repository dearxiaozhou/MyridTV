# MyridTV 源 / 副本 关系说明（消除副本混淆）

> 适用场景：重构 spec Phase 7「清理 `_internal` / `installer` 副本混淆」。
> 目的：让开发者一眼分清「运行时源」和「打包快照」，避免改了不生效的文件。

## 1. 谁是源，谁是副本

- **`_internal/` = 运行时源（唯一应手改的目录）**
  - 开发模式 `启动研发版.cmd` 直接加载 `_internal/static/` 下的前端静态文件与 `rh_official_proxy.py`。
  - 所有 Agent / Canvas / 节点 / 事件驱动重构都落在 `_internal/static/js/smart-canvas.js` 与 `rh_official_proxy.py`。

- **`installer/build/MyridTV/` = 打包快照（不要手改）**
  - 由 `installer/prepare-release.ps1` 在打包时生成：先 `Remove-IfExists $StageDir`（整目录清空），
    再 `Copy-FilteredTree $SourceDir → $StageDir`（整目录拷贝），最后构建 launcher / desktop 二进制。
  - 因此 `installer/build/` 下所有文件都是**打包那一刻项目根的镜像**，下次打包会被完全覆盖 + 重建。

## 2. ⚠️ 开发铁律

- **只改 `_internal/`（及项目根其他源文件）**，`installer/build/` 一律不要手改。
- 典型踩坑：编辑了 `installer/build/MyridTV/_internal/static/js/smart-canvas.js`（旧快照，可能比源落后几天），
  但 dev/生产实际加载的是 `_internal/static/js/smart-canvas.js`（当前），改动无效且下次打包丢失。
- 若发现 `installer/build/` 里的文件与 `_internal/` 不一致，**以 `_internal/` 为准**，重新跑 `prepare-release.ps1` 刷新快照即可。

## 3. 快照跳过列表（`prepare-release.ps1` `Should-SkipRelativePath`）

以下目录**不进安装包**（不会出现在 `installer/build/` 快照里）：
`assets`、`_internal\API`、`_internal\assets`、`_internal\data`、`_internal\output`、`_internal\_internal`、
`installer`、`installer\build`、`internal`、`test-results`、`__pycache__`。

注意：**`_internal\static` 不在跳过列表** → 前端静态文件（html/css/js）会进包，且来自 `_internal/static` 的当前内容。

## 4. 前端画布入口（双入口，迁移期并存）

| 入口 | 主文件 | 体量 | 状态 |
|---|---|---|---|
| `smart-canvas.html` | `_internal/static/js/smart-canvas.js` | 965KB | **新主画布**：事件驱动 Agent 架构重构落地点，dev/生产都加载 |
| `canvas.html` | `_internal/static/js/canvas.js` | 637KB | **旧画布**：仍被 `rh_official_proxy.py` STATIC_PATCHES 与 `index.html` 导航服务（兼容保留） |

- 两者均被 proxy 路由服务、均进 `index.html` 导航，不是「未引用死文件」。
- 旧入口（`canvas.html` + `canvas.js`）淘汰需单独评估（破坏性，影响仍在使用该页的用户），见重构 spec Phase 7 决策。

## 5. i18n 文件

- `i18n/canvas.js`（旧入口用）与 `i18n/smart-canvas.js`（新入口用）是两个**独立**文件，各自绑定对应入口，不要混用或合并。

## 6. 相关文件

- 打包逻辑：`installer/prepare-release.ps1`（L588-599 源→快照）
- 静态版本注入：`rh_official_proxy.py` `STATIC_PATCHES`（L368-385）服务两个画布入口
- 备份快照：本次重构在 `_internal/static/js/` 留下 `smart-canvas.js.bak_phase4_*` / `smart-canvas.js.bak_phase6_visual`，验证无误后可清理。

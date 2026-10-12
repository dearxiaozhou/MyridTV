# 外部 Agent MCP 接口（V0.10.18）

后端统一入口为 `POST /mcp`；本地默认地址 `http://127.0.0.1:3107/mcp`。
Codex 使用 `codex-canvas-mcp.py`，Hermes 使用 `hermes-canvas-mcp.py`。
两个 stdio 入口共用 `myridtv_mcp_client.py`，每次 `tools/list` 向后端获取当前 schema。
可用 `MYRIDTV_MCP_BASE` 指定其他本地实例；未连接后端时明确报错，不伪装成旧接口仍可用。

## 调用流程

1. `canvas_list_canvases` 选择画布，或 `canvas_create` 创建并取得 `canvas_id`。
2. `canvas_get_state` 读取画布概况与 `updated_at`；`canvas_get_node` 读取完整节点。
3. 修改时明确传入 `canvas_id`。建议传 `expected_updated_at`，发现冲突后重新读取并重新决定修改。
4. 每次逻辑写操作使用独立 `idempotency_key`；网络超时重试同一操作时，原样复用全部参数和同一个键。
5. 生图返回 `task_id` 表示提交，不表示完成。使用 `canvas_check_generation` 按需查询状态与结果。

本版本涉及画布的工具都要求明确的 `canvas_id`；不再继承其他调用留下的“当前画布”。
全局工具（画布列表、新建画布、技能列表、保存技能）不需要此参数。
`canvas_get_selection` 当前返回 `available=false`，表示尚无实时界面选择桥接，不能解释成用户没有选中节点。

## 新增工具

| 工具 | 用途 |
| --- | --- |
| `canvas_get_node` | 完整正文、图片、参数和待处理任务 |
| `canvas_check_generation` | 指定画布任务的状态和媒体结果 |
| `canvas_batch_operations` | 1–50 项操作，一次保存；错误时整批不保存 |
| `canvas_undo_batch` | 撤销批次，恢复被删除节点和连线；后续有新修改时拒绝撤销 |
| `canvas_list_snapshots` | 列出持久快照 |
| `canvas_get_snapshot` | 查看快照完整记录 |
| `canvas_restore_snapshot` | 按当前版本恢复节点、连线、设置、产物、视口和输入模式 |
| `canvas_upsert_flow` | 按稳定 ID 批量创建/更新依赖图，自动布局并原子保存 |
| `canvas_layout_flow` | 仅重新布局指定工作流，保留锁定与无关节点 |

`canvas_snapshot` 已升级为持久快照，返回 `snapshot_id`，不会只写时间戳。
恢复快照必须传入当前 `expected_updated_at`；保留现有画布身份、名称和日志。
批量操作复用内置 Agent 的操作校验、节点构建和 Artifact Gate。
同批新增节点的 ID 由软件分配；需要引用新节点时先取得返回 ID，再提交连线批次。

## MCP 工作流自动布局

外部 Agent 创建完整流程时优先使用 `canvas_upsert_flow`，不再逐个计算 x/y。
接口沿用项目的 snake_case 命名：`canvas_id`、`workflow_id`；节点的
`parent_id` / `branch_order` 也兼容 `parentId` / `branchOrder`。
每批最多 100 个节点和 300 条边，同一工作流最多 500 个节点。

```json
{
  "canvas_id": "从 canvas_create 或 canvas_list_canvases 取得的 ID",
  "workflow_id": "director-scene-01",
  "layout": "tree_lr",
  "nodes": [
    {"id":"scene-01","type":"generation","title":"场景资产","prompt":"清晨居民家客厅，窗边木桌，冷暖光交织"},
    {"id":"shot-01","type":"generation","title":"镜头一","prompt":"客厅全景，人物站在窗边","parent_id":"scene-01","branch_order":1},
    {"id":"shot-02","type":"generation","title":"镜头二","prompt":"人物肩部近景，窗外光照在侧脸","parent_id":"scene-01","branch_order":2},
    {"id":"shot-03","type":"generation","title":"镜头三","prompt":"桌面物品特写，背景人物虚化","parent_id":"scene-01","branch_order":3},
    {"id":"video-01","type":"video","title":"视频一","prompt":"从客厅全景缓慢推进，人物保持一致","depends_on":["shot-01"]},
    {"id":"video-02","type":"video","title":"视频二","prompt":"人物缓缓回头，保持侧面光线","depends_on":["shot-02"]},
    {"id":"video-03","type":"video","title":"视频三","prompt":"缓慢掠过桌面，保持物品细节","depends_on":["shot-03"]}
  ],
  "edges": [
    {"from":"已存在的角色资产节点ID","to":"shot-01","kind":"input"},
    {"from":"已存在的角色资产节点ID","to":"shot-02","kind":"input"}
  ]
}
```

示例中的共享角色必须已经存在；没有该资产时删除相应 edges，或在同一批 nodes 中创建一次。
真实依赖统一写入原生 `connections`；`kind=input` 同步目标节点的 `inputNodeIds`。
原生连线已经从源节点右侧连接至目标节点左侧，无需修改画布连线系统。

- `nodes` 中每项必须有稳定 `id`。新文本节点用 `type=text` 和 `text`；新生成节点用
  `generation/image/video` 和真实 `prompt`，沿用 Artifact Gate。生成参数 `provider_id/model/aspect_ratio/...`
  与原 MCP 保持一致，不提交生成任务，也不产生生成费用。
- `edges`、`parent_id`、`depends_on` 可组合使用，接受多输入 DAG；不会复制共享角色来伪造单父树。
  重复连线去重。循环、悬空依赖、重复批内 ID、非法参数导致整批不保存。
- 增量调用传同一 `workflow_id`，只提供新增或需更新的 nodes/edges。省略的节点、结果、提示词和连线保留。
  同一 ID 更新而不是复制；跨工作流共享资产只在 edges 引用，不放入 nodes 覆盖它。
- `branch_order` 控制同级从上到下的顺序。`width/height` 可选，只描述尺寸，不需要坐标。
  文本、生成卡片和实际浏览器测量尺寸用于避让；生成后尺寸变化保存时自动重排受影响工作流。
  MCP 图片分组作为整体占地移动，保留组内布局。
- 既有节点传 `{"id":"...","locked":true}` 可锁定布局位置；`locked:false` 解锁。
  也尊重节点已有的 `locked/positionLocked/layoutLocked/pinned` 标记。
  不移动其他工作流或普通手工节点。若锁定坐标使依赖不能从左至右，返回 `constraints`，不会偷偷解锁。
- `canvas_layout_flow` 只需 `canvas_id/workflow_id`，可显式重新布局；同样支持版本检查与幂等回执。

实现复用现有 Python 节点构建、Artifact Gate、版本冲突保护和原子保存；本项目没有可复用的
ELK/Dagre 图布局引擎，现有 layout coordinator 仅用于面板避让。本次使用独立、确定性的分层 DAG
布局模块，避免给便携桌面版新增 Node.js 服务或安装依赖。对树分支保持顺序和父子居中；
共享依赖保留真实图关系，不能保证任意非平面依赖图完全没有交叉。

## 结果与错误

工具结果通过 `result.content[].text` 返回 JSON。工具执行失败标记 `result.isError=true`，
JSON 内包含 `error` 与 `error_code`。两个 stdio 入口原样保留错误标记。
“查询成功，但任务状态为 failed”属于正常查询结果，查看其中的 `status` 和 `error`。

常见错误码：`invalid_arguments`、`node_not_found`、`task_not_found`、`conflict`、
`task_canvas_mismatch`、`idempotency_conflict`、`outcome_unknown`。
有 `outcome_unknown` 时先检查画布/任务，不要换键盲目重复提交。
幂等回执在用户数据目录持久保存；同键复用不同参数会被拒绝。

节点列表支持 `limit`（1–200）和 `offset`；完整节点正文使用 `canvas_get_node`。
`/health` 保留原 `version`（静态资源版本），新增 `software_version` 与 `mcp_api_version`。
MCP initialize 的 `serverInfo.version` 使用软件版本。

## 验证

`tests/test_mcp_contract.py` 和 `tests/test_canvas_save_revision.py` 覆盖并发、回滚、撤销、墓碑与幂等。
运行 `tests/serve_mcp_verification.py` 可启动独立用户数据的真实后端（默认端口3227）；
再运行 `tests/e2e_mcp_contract.py` 验证 HTTP、两个 stdio 入口及真实前端。
任务状态使用验证实例的固定数据，不调用付费生成服务。

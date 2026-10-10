# 外部 Agent MCP 接口（V0.10.12）

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

`canvas_snapshot` 已升级为持久快照，返回 `snapshot_id`，不会只写时间戳。
恢复快照必须传入当前 `expected_updated_at`；保留现有画布身份、名称和日志。
批量操作复用内置 Agent 的操作校验、节点构建和 Artifact Gate。
同批新增节点的 ID 由软件分配；需要引用新节点时先取得返回 ID，再提交连线批次。

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

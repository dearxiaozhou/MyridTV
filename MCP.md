# MCP 自动排版已关闭

外部调用仍使用 canvas_execute。创建、连线、结果尺寸变化不触发工作流重排；已有节点保持位置。支持坐标的动作可以传 x/y，新节点未传坐标时使用原生空位放置。upsert_flow 保留批量创建和依赖连接功能，返回 layout_disabled=true。下方旧排版说明仅作为历史记录，不再生效。

# 外部 Agent 画布统一入口（V0.12.8）

对外 MCP **只发布一个工具：`canvas_execute`**。创建、更新、连接、生成、查询、快照和批量操作全部通过它。
旧的独立 canvas_* 工具不再发布或执行；旧会话调用会收到 entrypoint_changed 及刷新工具列表的提示。

后端仍为 POST /mcp。Hermes、Codex、Claude 三个 stdio 适配器均读取同一后端 schema，不各自维护工具集。
实际端口跟随当前 app_config，可用 MYRIDTV_MCP_BASE 指定；不能假定一直是3107。

## 调用结构

```json
{
  "action": "upsert_flow",
  "canvas_id": "明确选择的画布ID",
  "workflow_id": "scene-production-01",
  "idempotency_key": "scene-production-01-step-1",
  "params": {
    "nodes": [
      {"id":"scene","type":"generation","title":"场景资产","prompt":"清晨居民家客厅，窗边木桌"},
      {"id":"shot1","type":"generation","title":"镜头一","prompt":"客厅全景，角色站在窗边","parent_id":"scene","branch_order":1},
      {"id":"shot2","type":"generation","title":"镜头二","prompt":"角色近景，窗光落在侧脸","parent_id":"scene","branch_order":2},
      {"id":"shot3","type":"generation","title":"镜头三","prompt":"桌面物品特写，背景人物虚化","parent_id":"scene","branch_order":3},
      {"id":"video1","type":"video","title":"视频一","prompt":"全景缓慢推进，保持角色一致","depends_on":["shot1"]}
    ],
    "edges": []
  }
}
```

action 表示操作意图，具体参数放 params。
canvas_id、workflow_id、idempotency_key、expected_updated_at 放顶层，不能通过 params 覆盖目标。
涉及画布的操作必须明确给 canvas_id，不默认选择“最近画布”。不要提供 x/y，入口会拒绝坐标参数。

## 查看操作参数

仍然调用同一个工具，不必猜参数：

```json
{"action":"describe","params":{"action":"create_video_node"}}
```

返回该操作的 params_schema、用途和画布目标要求。`{"action":"describe"}` 列出全部 action。

| action | 用途 |
| --- | --- |
| list_canvases / create | 选择画布 / 新建画布 |
| get_state / get_node / search | 状态、完整节点和正文搜索 |
| upsert_flow | 推荐：用稳定ID、nodes、edges 批量或增量建立依赖图 |
| create_node / create_text_node / create_generation_node / create_video_node | 逐个创建，同样自动进入树状布局 |
| update_node / delete_node | 更新或删除节点 |
| connect_nodes / disconnect_nodes | 原生连接与输入引用，自动重排受影响工作流 |
| generate_images / check_generation / analyze_image | 生成、任务查询、看图；用 describe 查具体参数 |
| batch_operations / undo_batch | 原有批量事务与可恢复撤销 |
| snapshot / list_snapshots / get_snapshot / restore_snapshot | 持久快照和版本保护恢复 |
| layout_flow | 显式重排；常规创建、连线与尺寸变化不需要额外调用 |
| list_skills / save_skill | 原有技能库操作，统一入口分发 |

## 自动布局是软件规则

外部新增节点在现有 Artifact Gate 中、第一次保存前自动取得 flowLayout.layout=tree_lr 和工作流归属。
即使 Agent 逐个创建再连线，也不需要主动选布局工具。

- workflow_id 建议每个生产任务使用稳定值；省略时复用目标节点已有工作流，否则为 external:<canvas_id>。
  更新既有节点时不能悄悄改变工作流归属。
- 完整流程使用 upsert_flow。nodes 中的稳定ID负责去重，parent_id/depends_on/edges 表达真实多输入DAG。
  branch_order 控制同级分支顺序，width/height 只描述尺寸。
- 共享角色通过 edges 引用已有节点，不为树形外观重复创建。
- 根据真实尺寸从左向右分层，尽量父子居中，保持间距；创建、连线、断连、删除和尺寸改变复用同一保存/布局逻辑。
- 继续修改或连接旧 Agent 节点时，只接管本次触及的旧Agent连通区域。普通手工节点、无关旧任务、其他已有工作流不改归属。
- 尊重 locked/positionLocked/layoutLocked/pinned。若锁定位置阻碍依赖方向，返回 constraints，不偷偷解锁。
- 不新增自动分组，遵守“仅手工打组”规则；已有组按整体占地移动。不重构画布系统，不修改 DirectorOS Skill。

upsert_flow 每批最多100节点、300边，同一工作流最多500节点；batch_operations 保留50操作上限。
循环、悬空依赖或非法批量操作不会部分落库。真实复杂DAG不保证完全无交叉。

## 错误、重试和任务

每次逻辑写操作使用稳定 idempotency_key；超时后原样重试。同键复用不同动作、参数或工作流返回幂等冲突。
生成返回 task_id 只表示已提交，用 check_generation 按需查询结果，不盲目重复提交。

get_state 返回 updated_at，写操作可传 expected_updated_at；恢复快照必须使用当前版本。
版本冲突先重新读取。错误仍通过 result.isError 与 content 中的JSON返回。
新增错误：entrypoint_changed、coordinates_managed、workflow_conflict。
get_selection.available=false 表示没有活动选择桥，不能推断用户未选择节点。

## 生效与验证

后端升级后，Hermes 等客户端需刷新 MCP 连接/工具列表。验收标准是 tools/list 仅返回 canvas_execute，
而不是同时看到新旧工具。入口约束由后端执行，不能仅靠提示词或 Skill 要求 Agent 自觉选择新工具。

tests/e2e_canvas_gateway.py 验证唯一入口、逐个创建自动布局、旧入口拦截、旧Agent继续操作、
重试去重、并发隔离、手工/锁定保护和真实桌面保存刷新。
tests/e2e_mcp_contract.py 验证查询、批量、快照、任务查询及三个真实 stdio 入口。
测试使用隔离实例，不调用付费生成接口。

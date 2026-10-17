"""The only public MCP tool. Native operations remain private implementation details."""
import copy
import myridtv_flow_layout as flow_layout
from contextvars import ContextVar

TOOL = 'canvas_execute'
_request = ContextVar('canvas_gateway_request', default=None)
CONTROL = {'canvas_id','workflow_id','idempotency_key','expected_updated_at'}
GLOBAL = {'canvas_list_canvases','canvas_create','canvas_list_skills','canvas_save_skill'}
READ = {'canvas_get_state','canvas_get_node','canvas_get_selection','canvas_search',
        'canvas_check_generation','canvas_list_snapshots','canvas_get_snapshot','canvas_analyze_image'}


def _target_ids(value):
    ids=set()
    if isinstance(value,dict):
        for key,child in value.items():
            if key in ('node_id','from_id','to_id','target_id') and isinstance(child,str):ids.add(child)
            ids.update(_target_ids(child))
    elif isinstance(value,list):
        for child in value:ids.update(_target_ids(child))
    return ids


def enroll_existing(cid, canvas, extra_ids=()):
    """Migrate only the touched legacy Agent component, in the pending transaction.

    Never enroll ordinary hand-created cards or reassign another managed workflow.
    Old Agent IDs/provenance distinguish their cards from manual nodes updated by MCP.
    """
    if not flow_layout.AUTOMATIC_LAYOUT_ENABLED:return
    request=_request.get()
    if not request or str(cid or canvas.get('id') or '')!=request['canvas_id']:return
    nodes={n.get('id'):n for n in canvas.get('nodes',[])}
    pending=list(request['target_ids']|set(extra_ids));visited=set()
    while pending:
        nid=pending.pop()
        if nid in visited:continue
        visited.add(nid);node=nodes.get(nid)
        if not node:continue
        flow=node.get('flowLayout') or {}
        if flow.get('workflowId'):
            if flow['workflowId']!=request['workflow_id']:continue
        else:
            provenance=node.get('provenance') or {}
            is_agent=(str(nid).startswith('agent_') and str(node.get('__origin') or '').startswith(('mcp','agent_'))) or node.get('created_by')=='agent' or bool(provenance.get('tool_call_id'))
            if not is_agent:continue
            node['flowLayout']={'workflowId':request['workflow_id'],'layout':'tree_lr'}
        for edge in canvas.get('connections',[]):
            if edge.get('from')==nid:pending.append(edge.get('to'))
            if edge.get('to')==nid:pending.append(edge.get('from'))


def enroll_new_node(cid, canvas, node):
    """Run inside the existing Artifact Gate, before the first native save."""
    if not flow_layout.AUTOMATIC_LAYOUT_ENABLED:return
    request = _request.get()
    if not request or not isinstance(node,dict):return
    target = str(cid or canvas.get('id') or '')
    if target != request['canvas_id']:return
    enroll_existing(cid,canvas,node.get('inputNodeIds',[]))
    if any(n.get('id')==node.get('id') for n in canvas.get('nodes',[])):return
    flow = node.setdefault('flowLayout',{})
    flow.update(workflowId=request['workflow_id'],layout='tree_lr')


def _coordinate_path(value, path='params'):
    if isinstance(value,dict):
        for key,child in value.items():
            if key in ('x','y'):return path+'.'+key
            found=_coordinate_path(child,path+'.'+key)
            if found:return found
    elif isinstance(value,list):
        for index,child in enumerate(value):
            found=_coordinate_path(child,f'{path}[{index}]')
            if found:return found


def install(public_registry, private_registry, private_handle):
    actions={name.removeprefix('canvas_'):name for name in private_registry}
    def failure(message, code='invalid_arguments', **extra):
        return {'ok':False,'error':message,'error_code':code,**extra}
    def describe(action=None):
        if action is None:return {'ok':True,'entrypoint':TOOL,'actions':['describe',*sorted(actions)],
                                 'layout_policy':'Automatic MCP layout is disabled. Existing positions are preserved; x/y may be supplied to supported actions, otherwise native empty-space placement is used.'}
        if not isinstance(action,str) or action not in actions:return failure('未知 action: '+str(action))
        schema=copy.deepcopy(private_registry[actions[action]]['inputSchema'])
        hidden=CONTROL | ({'x','y'} if flow_layout.AUTOMATIC_LAYOUT_ENABLED else set())
        schema['properties']={k:v for k,v in schema['properties'].items() if k not in hidden}
        schema['required']=[k for k in schema.get('required',[]) if k not in hidden]
        example={'action':action,'params':{}}
        if actions[action] not in GLOBAL:example['canvas_id']='target-canvas-id'
        return {'ok':True,'entrypoint':TOOL,'action':action,'description':private_registry[actions[action]]['description'],
                'params_schema':schema,'canvas_id_required':actions[action] not in GLOBAL,
                'workflow_id':'optional; defaults to external:<canvas_id>, or follows an existing target node',
                'example':example}
    public_registry.clear()
    public_registry[TOOL] = {
        'description': 'MyridTV 唯一画布入口。action 选择操作，参数放 params；canvas_id/workflow_id/幂等键/版本号放顶层。MCP自动排版已关闭，创建、连接、结果尺寸变化不会触发工作流重排。已有节点位置保持不变；支持坐标的动作可传 x/y，新节点未传坐标时使用原生空位放置。批量创建可使用 upsert_flow。action=describe 查询参数。',
        'inputSchema':{'type':'object','additionalProperties':False,'required':['action'],
                       'properties':{'action':{'type':'string','enum':['describe',*sorted(actions)]},
                                     'canvas_id':{'type':'string'},'workflow_id':{'type':'string'},
                                     'idempotency_key':{'type':'string'},'expected_updated_at':{'type':'integer','minimum':1},
                                     'params':{'type':'object','description':'action 的参数；用 describe 查询。自动排版已关闭，坐标按具体动作支持情况填写。'}}}}

    def handle(name, arguments):
        if name != TOOL:return failure('旧工具已撤下；请刷新 MCP 工具列表，统一调用 canvas_execute',
                                      'entrypoint_changed',entrypoint=TOOL,action=name.removeprefix('canvas_'))
        if not isinstance(arguments,dict):return failure('arguments 必须是对象')
        if set(arguments)-{'action','params',*CONTROL}:return failure('未知顶层参数；操作参数应放在 params')
        action=arguments.get('action');params=arguments.get('params',{})
        if not isinstance(action,str):return failure('action 必须是字符串')
        if not isinstance(params,dict):return failure('params 必须是对象')
        if action=='describe':
            if set(params)-{'action'}:return failure('describe 的 params 只接受 action')
            return describe(params.get('action'))
        if action not in actions:return failure('未知 action；使用 describe 查看支持的操作')
        if set(params)&CONTROL:return failure('canvas_id/workflow_id/幂等键/版本号必须放顶层，不允许覆盖目标')
        coordinate=_coordinate_path(params)
        if coordinate and flow_layout.AUTOMATIC_LAYOUT_ENABLED:return failure('坐标由软件统一计算，不接受 '+coordinate, 'coordinates_managed')
        name=actions[action]
        cid=arguments.get('canvas_id')
        if name not in GLOBAL and (not isinstance(cid,str) or not cid.strip()):return failure('canvas_id 必填')
        if isinstance(cid,str):cid=cid.strip()
        for key in ('workflow_id','idempotency_key'):
            if key in arguments and (not isinstance(arguments[key],str) or not arguments[key].strip()):return failure(key+' 必须是非空字符串')
        if len(arguments.get('workflow_id',''))>200:return failure('workflow_id 最多200字符')
        wid=arguments.get('workflow_id','').strip() or None
        if name not in GLOBAL:
            import myridtv_canvas_store as store
            try:
                canvas=store.read_canvas_record(cid,include_deleted=False)
            except Exception as exc:return failure(str(exc),'canvas_not_found')
            target_ids=[params.get('node_id'),params.get('to_id'),params.get('from_id')]
            node=next((n for nid in target_ids for n in canvas['nodes'] if n.get('id')==nid and (n.get('flowLayout') or {}).get('workflowId')),None)
            existing_wid=(node.get('flowLayout') or {}).get('workflowId') if node else None
            if wid and existing_wid and wid!=existing_wid:return failure('目标节点属于其他工作流，不会隐式移动或改归属','workflow_conflict')
            wid=wid or existing_wid or 'external:'+cid
        payload=copy.deepcopy(params)
        payload.update({key:arguments[key] for key in CONTROL if key in arguments})
        if name not in GLOBAL:payload.update(canvas_id=cid,workflow_id=wid)
        token=_request.set({'canvas_id':cid,'workflow_id':wid,'target_ids':_target_ids(params)}) if name not in GLOBAL and name not in READ else None
        try:
            result=private_handle(name,payload)
            # Keep the native result shape and its error semantics; expose routing evidence.
            if isinstance(result,dict):
                data=result.get('result',result)
                if isinstance(data,dict):data.setdefault('gateway',{'entrypoint':TOOL,'action':action,'workflow_id':wid})
            return result
        finally:
            if token is not None:_request.reset(token)
    # Private handles are retained for internal contract tests, never MCP discovery.
    handle._private_registry = private_registry
    handle._private_handle = private_handle
    return handle

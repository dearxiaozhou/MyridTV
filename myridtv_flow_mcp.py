"""Atomic workflow upsert using the existing builders, Artifact Gate and store."""
import copy
import math

import myridtv_agent_artifact as artifacts
import myridtv_agent_batch as batch
import myridtv_agent_state as state
import myridtv_canvas_store as store
import myridtv_flow_layout as layout


NODE_KEYS = {'id','type','title','text','content','prompt','images','width','height','parent_id','parentId',
             'depends_on','branch_order','branchOrder','locked','provider_id','model','size','aspect_ratio',
             'resolution','quality','count','reference_image_urls'}


def upsert(args):
    cid,wid=args['canvas_id'],args['workflow_id'].strip()
    specs=args.get('nodes',[]);edges=args.get('edges',[])
    if not wid or len(wid)>200:raise ValueError('workflow_id 需要 1–200 个字符')
    if len(specs)>100 or len(edges)>300:raise ValueError('每批最多 100 个节点、300 条边')
    with store._canvas_save_lock:
        canvas=store.read_canvas_record(cid,include_deleted=False)
        if args.get('expected_updated_at') is not None and args['expected_updated_at']!=canvas['updated_at']:
            from myridtv_core import CanvasConflictError
            raise CanvasConflictError(canvas)
        canvas=copy.deepcopy(canvas)
        by_id={n['id']:n for n in canvas['nodes']}
        deleted={t['id'] for t in canvas.get('deleted',[]) if isinstance(t,dict) and t.get('id')}
        seen=set();created=[];updated=[];dependency_edges=[]
        for spec in specs:
            if not isinstance(spec,dict) or set(spec)-NODE_KEYS:raise ValueError('节点含未知字段；坐标由 tree_lr 统一计算，不接受 x/y')
            nid=spec.get('id')
            if not isinstance(nid,str) or not nid.strip() or len(nid)>200:raise ValueError('每个节点需要稳定的非空 id（最多200字符）')
            if nid in seen:raise ValueError('同一批次存在重复节点 ID: '+nid)
            if nid in deleted:raise ValueError('节点已被用户删除，不会自动复活: '+nid)
            seen.add(nid)
            existing=by_id.get(nid)
            if existing and (existing.get('flowLayout') or {}).get('workflowId')!=wid:
                raise ValueError('节点 ID 已属于画布其他区域；共享资产请仅在 edges 中引用: '+nid)
            kind=spec.get('type') or ('text' if existing and existing.get('type')=='smart-prompt' else 'generation')
            if kind not in ('text','generation','image','video'):raise ValueError('节点 type 仅支持 text/generation/image/video')
            for key in ('width','height','branch_order','branchOrder'):
                if key in spec and (isinstance(spec[key],bool) or not isinstance(spec[key],(int,float)) or not math.isfinite(spec[key])):raise ValueError(key+' 必须是有限数字')
            if 'locked' in spec and not isinstance(spec['locked'],bool):raise ValueError('locked 必须是布尔值')
            if existing:
                if (kind=='text')!=(existing.get('type')=='smart-prompt'):raise ValueError('不能通过 upsert 改变既有节点类型: '+nid)
                node=existing
                if 'title' in spec:node['title']=str(spec['title'])
                body=next((spec[k] for k in ('prompt','text','content') if k in spec),None)
                if body is not None:
                    body=str(body).strip()
                    if not body:raise ValueError('节点正文不能为空: '+nid)
                    node.update(promptDraftText=body,promptDraftTouched=True)
                    node['promptDraftHtml']=state._agent_html_escape(body)
                    if kind=='text':node.update(text=body,content=body)
                    else:node['runPrompt']=body
                if 'images' in spec:
                    if not isinstance(spec['images'],list):raise ValueError('images 必须为数组')
                    node['images']=copy.deepcopy(spec['images'])
                # Preserve generated results and all omitted settings on incremental calls.
                for key in ('provider_id','model','size','aspect_ratio','resolution','quality','count'):
                    if key in spec:
                        rs=node.setdefault('runSettings',{})
                        rs['ratio' if key=='aspect_ratio' else key]=spec[key]
                if kind=='video':node.setdefault('runSettings',{})['apiKind']='video'
                updated.append(nid)
            else:
                params={k:copy.deepcopy(v) for k,v in spec.items() if k in NODE_KEYS}
                if kind=='text':node=batch._agent_batch_build_text_node(canvas,params)
                else:
                    if kind=='video':params['apiKind']='video'
                    node,reference_ids=batch._agent_batch_build_generation_node(canvas,params,None)
                    dependency_edges.extend({'from':reference_id,'to':nid,'kind':'input'} for reference_id in reference_ids)
                    if kind=='video':node['runSettings']['apiKind']='video'
                    if 'images' in spec:
                        if not isinstance(spec['images'],list):raise ValueError('images 必须为数组')
                        node['images']=copy.deepcopy(spec['images'])
                node.update(id=nid,artifactId='flow:'+wid+':'+nid)
                ok,error,deduped=artifacts._agent_prepare_node_for_canvas(cid,canvas,node,'mcp_flow',{})
                if not ok or deduped:raise ValueError(str(error))
                canvas['nodes'].append(node);by_id[nid]=node;created.append(nid)
            flow=node.setdefault('flowLayout',{})
            flow.update(workflowId=wid,layout='tree_lr')
            if 'branch_order' in spec or 'branchOrder' in spec:flow['branchOrder']=spec.get('branch_order',spec.get('branchOrder'))
            if 'locked' in spec:flow['locked']=spec['locked']
            for key,field in (('width','w'),('height','h')):
                if key in spec:
                    if not 28<=spec[key]<=20000:raise ValueError(key+' 需在28至20000之间')
                    node[field]=round(spec[key]);flow.pop('measuredSize',None)
                    if node.get('cardSize'):node['cardSize']['width' if field=='w' else 'height']=node[field]
            dependencies=spec.get('depends_on',[])
            parent=spec.get('parent_id',spec.get('parentId'))
            if parent is not None:dependencies=[parent]+dependencies if isinstance(dependencies,list) else dependencies
            if not isinstance(dependencies,list) or any(not isinstance(p,str) or not p for p in dependencies):raise ValueError('depends_on 必须是节点 ID 数组')
            dependency_edges.extend({'from':p,'to':nid,'kind':'input'} for p in dependencies)
        for edge in [*edges,*dependency_edges]:
            if not isinstance(edge,dict) or set(edge)-{'from','to','kind','label'}:raise ValueError('edges 项仅接受 from/to/kind/label')
            a,b=edge.get('from'),edge.get('to');kind=edge.get('kind','input')
            if a not in by_id or b not in by_id or a==b:raise ValueError('连线必须引用两个已存在的不同节点')
            if kind not in ('input','flow'):raise ValueError('连线 kind 仅支持 input/flow')
            if (by_id[b].get('flowLayout') or {}).get('workflowId')!=wid:raise ValueError('连线目标必须属于当前工作流；不会修改其他工作流')
            connections=canvas.setdefault('connections',[])
            existing_edge=next((e for e in connections if e.get('from')==a and e.get('to')==b and e.get('kind','input')==kind),None)
            if existing_edge is None:
                connections.append({**copy.deepcopy(edge),'kind':kind})
            elif 'label' in edge:existing_edge['label']=str(edge['label'])
            if kind=='input':
                target=by_id[b];target['inputNodeIds']=list(dict.fromkeys([*target.get('inputNodeIds',[]),a]))
        outcome=layout.layout_workflow(canvas,wid)
        saved=store.save_canvas_record(cid,canvas)
        return {'ok':True,'canvas_id':cid,'workflow_id':wid,'layout':'tree_lr','created':created,'updated':updated,
                'moved':outcome['moved'],'constraints':outcome['constraints'],'save_ok':True,'updated_at':saved['updated_at'],
                'nodes':[{k:n.get(k) for k in ('id','x','y','w','h','flowLayout')} for n in saved['nodes']
                         if (n.get('flowLayout') or {}).get('workflowId')==wid]}

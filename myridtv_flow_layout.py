"""Scoped left-to-right DAG layout, shared by MCP commits and size-change saves.

No browser/runtime dependency: existing Python desktop distributions can lay out
flows even while the canvas is closed. Nodes retain native types and connections.
"""
import copy
import math
import re

GAP_X, GAP_Y = 160, 96


def number(value, default=0):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (ValueError, TypeError):
        return default


def node_size(node):
    """Match native card geometry; browser measurements cover expanded controls."""
    measured = (node.get('flowLayout') or {}).get('measuredSize') or {}
    card = node.get('cardSize') or {}
    w, h = number(card.get('width') or node.get('w')), number(card.get('height') or node.get('h'))
    if node.get('type') == 'smart-prompt':
        w = 632 if not w or w == 360 else w
        h = max(h, 688 if node.get('llmSystemEnabled') else 584 if node.get('llmEnabled') else 388)
    elif node.get('type') == 'smart-speech':
        w, h = max(900, w or 1000), max(520, h or 540)
    elif node.get('type') == 'smart-image':
        if not w or not h:
            rs=node.get('runSettings') or {}
            ratio=str(rs.get('videoAspect') if rs.get('apiKind')=='video' else rs.get('ratio') or '')
            match=re.fullmatch(r'(\d+(?:\.\d+)?)\s*[:x×]\s*(\d+(?:\.\d+)?)',ratio)
            if match:
                rw,rh=map(float,match.groups())
                if rw>0 and rh>0:
                    fit=min(512/rw,440/rh);w,h=round(rw*fit),round(rh*fit)
            images=node.get('images') or []
            if len(images)==1 and not (card.get('width') or node.get('w')):
                image=images[0];nw,nh=number(image.get('natural_w')),number(image.get('natural_h'))
                if nw>0 and nh>0 and not (image.get('generatedResult') and match):
                    scale=number(node.get('scale'),2);fit=min(260*scale/nw,220*scale/nh);w,h=round(nw*fit),round(nh*fit)
        w, h = w or 512, h or 288
    else:
        w, h = w or 340, h or 240
    return (max(28, number(measured.get('width'), w)), max(28, number(measured.get('height'), h)))


def locked(node):
    return bool(node.get('locked') or node.get('positionLocked') or node.get('layoutLocked') or node.get('pinned')
                or (node.get('flowLayout') or {}).get('locked'))


def graph(canvas, workflow_id):
    selected = {n['id']:n for n in canvas.get('nodes', [])
                if (n.get('flowLayout') or {}).get('workflowId') == workflow_id}
    parents = {nid:[] for nid in selected}
    children = {nid:[] for nid in selected}
    for edge in canvas.get('connections', []):
        a, b = edge.get('from'), edge.get('to')
        if a in selected and b in selected and b not in children[a]:
            children[a].append(b); parents[b].append(a)
    return selected, parents, children


def topological(selected, parents, children):
    def order(nid):
        return (number((selected[nid].get('flowLayout') or {}).get('branchOrder')), nid)
    degrees = {nid:len(parents[nid]) for nid in selected}
    ready = sorted((nid for nid in selected if not degrees[nid]), key=order)
    result = []
    while ready:
        nid = ready.pop(0);result.append(nid)
        for child in sorted(children[nid], key=order):
            degrees[child] -= 1
            if not degrees[child]:ready.append(child);ready.sort(key=order)
    if len(result) != len(selected):
        raise ValueError('tree_lr 需要无环依赖图；检测到循环，整批未保存')
    return result, order


def footprint(node, by_id):
    group = by_id.get(node.get('mcpGroupId'))
    if group and group.get('type') == 'smart-group':
        return (number(group.get('x')), number(group.get('y')), *node_size(group)), group
    return (number(node.get('x')), number(node.get('y')), *node_size(node)), None


def overlap(a, b, gap=0):
    return a[0] < b[0]+b[2]+gap and a[0]+a[2]+gap > b[0] and a[1] < b[1]+b[3]+gap and a[1]+a[3]+gap > b[1]


def layout_workflow(canvas, workflow_id):
    selected, parents, children = graph(canvas, workflow_id)
    if not selected:return {'moved':[], 'constraints':[]}
    if len(selected)>500:raise ValueError('单个工作流最多支持 500 个节点')
    # Validate the real dependency graph including shared external ancestors.
    by_id = {n['id']:n for n in canvas.get('nodes', [])}
    ancestors=set(selected)
    while True:
        extra={e.get('from') for e in canvas.get('connections',[]) if e.get('to') in ancestors and e.get('from') in by_id}
        if extra<=ancestors:break
        ancestors.update(extra)
    all_parents={nid:[] for nid in ancestors};all_children={nid:[] for nid in ancestors}
    for edge in canvas.get('connections',[]):
        a,b=edge.get('from'),edge.get('to')
        if a in ancestors and b in ancestors and b not in all_children[a]:
            all_children[a].append(b);all_parents[b].append(a)
    topological({nid:by_id[nid] for nid in ancestors},all_parents,all_children)
    topo, order = topological(selected, parents, children)
    by_id = {n['id']:n for n in canvas.get('nodes', [])}
    footprints = {nid:footprint(n, by_id) for nid,n in selected.items()}
    fixed = {nid for nid,n in selected.items() if locked(n) or
             (footprints[nid][1] and any(locked(by_id[mid]) for mid in footprints[nid][1].get('memberIds',[]) if mid in by_id))}
    # Native generated-image groups are one workflow footprint; move members together.
    owned = set(selected)
    for rect, group in footprints.values():
        if group:owned.update([group['id'], *group.get('memberIds', [])])
    obstacles = [(n['id'], (*[number(n.get(k)) for k in ('x','y')], *node_size(n)))
                 for n in canvas.get('nodes', []) if n['id'] not in owned and n.get('type') != 'smart-group']
    origin = next((n['flowLayout'].get('origin') for n in selected.values() if n['flowLayout'].get('origin')), None)
    if not origin:
        origin = {'x':120, 'y':max([0]+[r[1]+r[3] for _,r in obstacles])+160}
    ox, oy = number(origin.get('x'),120), number(origin.get('y'),160)
    ranks = {}
    for nid in topo:ranks[nid] = max([ranks[p]+1 for p in parents[nid]] or [0])
    primary = {nid:min(parents[nid],key=order) if parents[nid] else None for nid in topo}
    tree = {nid:sorted((c for c in children[nid] if primary[c]==nid),key=order) for nid in topo}
    spans = {}
    for nid in reversed(topo):
        spans[nid] = max(footprints[nid][0][3], sum(spans[c] for c in tree[nid])+GAP_Y*max(0,len(tree[nid])-1))
    centers = {}
    def place(nid, y):
        centers[nid] = y+spans[nid]/2
        child_y = y+(spans[nid]-sum(spans[c] for c in tree[nid])-GAP_Y*max(0,len(tree[nid])-1))/2
        for child in tree[nid]:place(child,child_y);child_y+=spans[child]+GAP_Y
    y = oy
    for root in sorted((nid for nid in topo if primary[nid] is None),key=order):
        place(root,y);y+=spans[root]+GAP_Y
    # A shared asset is a real second parent, not duplicated for tree aesthetics.
    for nid in reversed(topo):
        if tree[nid]:
            centers[nid]=(min(centers[c]-footprints[c][0][3]/2 for c in tree[nid])+
                          max(centers[c]+footprints[c][0][3]/2 for c in tree[nid]))/2
        elif children[nid]:centers[nid]=sum(centers[c] for c in children[nid])/len(children[nid])
    widths = {rank:max(footprints[nid][0][2] for nid in topo if ranks[nid]==rank) for rank in set(ranks.values())}
    columns = {0:ox}
    for rank in range(1,max(ranks.values())+1):columns[rank]=columns[rank-1]+widths[rank-1]+GAP_X
    placed = obstacles+[(nid,footprints[nid][0]) for nid in topo if nid in fixed]
    moved, constraints = [], []
    for rank in sorted(widths):
        layer = sorted((nid for nid in topo if ranks[nid]==rank),key=lambda nid:(centers[nid],order(nid)))
        for nid in layer:
            node=selected[nid];rect,group=footprints[nid]
            node['flowLayout']['origin']=copy.deepcopy(origin)
            if nid in fixed:continue
            x=columns[rank]
            for p in parents[nid]:
                pr=next((r for key,r in placed if key==p),footprints[p][0])
                x=max(x,pr[0]+pr[2]+GAP_X)
            for edge in canvas.get('connections',[]):
                if edge.get('to')==nid and edge.get('from') not in selected and edge.get('from') in by_id:
                    external,_=footprint(by_id[edge['from']],by_id)
                    x=max(x,external[0]+external[2]+GAP_X)
            candidate=(round(x),round(centers[nid]-rect[3]/2),rect[2],rect[3])
            # Fixed nodes/other workflows are obstacles, never moved to make room.
            while True:
                hits=[r for _,r in placed if overlap(candidate,r,GAP_Y/2)]
                if not hits:break
                candidate=(candidate[0],round(max(r[1]+r[3] for r in hits)+GAP_Y),candidate[2],candidate[3])
            dx,dy=candidate[0]-rect[0],candidate[1]-rect[1]
            if dx or dy:
                ids=[nid] if not group else list(dict.fromkeys([group['id'],*group.get('memberIds',[])]))
                for member_id in ids:
                    member=by_id.get(member_id)
                    if member:member['x']=round(number(member.get('x'))+dx);member['y']=round(number(member.get('y'))+dy)
                moved.append(nid)
            placed.append((nid,candidate))
    for nid in topo:
        for child in children[nid]:
            a,_=footprint(selected[nid],by_id);b,_=footprint(selected[child],by_id)
            if a[0]+a[2]>b[0]:constraints.append({'from':nid,'to':child,'reason':'locked_position_prevents_left_to_right'})
    return {'moved':moved,'constraints':constraints}


def signature(canvas, workflow_id):
    selected,_,_=graph(canvas,workflow_id)
    by_id={n['id']:n for n in canvas.get('nodes',[])}
    return (tuple(sorted((nid,*footprint(n,by_id)[0][2:],locked(n),
                          number(n['flowLayout'].get('branchOrder'))) for nid,n in selected.items())),
            tuple(sorted((e.get('from',''),e.get('to','')) for e in canvas.get('connections',[])
                         if e.get('to') in selected)),
            tuple(sorted((nid,*footprint(by_id[nid],by_id)[0]) for nid in
                         {e.get('from') for e in canvas.get('connections',[]) if e.get('to') in selected and e.get('from') not in selected}
                         if nid in by_id)))


def relayout_changed(current, saved):
    workflow_ids={n['flowLayout']['workflowId'] for n in saved.get('nodes',[]) if
                  isinstance(n.get('flowLayout'),dict) and n['flowLayout'].get('layout')=='tree_lr' and n['flowLayout'].get('workflowId')}
    owners={n['id']:(n.get('flowLayout') or {}).get('workflowId') for n in saved.get('nodes',[])}
    dependencies={wid:set() for wid in workflow_ids}
    for edge in saved.get('connections',[]):
        source,target=owners.get(edge.get('from')),owners.get(edge.get('to'))
        if source in workflow_ids and target in workflow_ids and source!=target:dependencies[target].add(source)
    pending=set(workflow_ids);ordered=[]
    while pending:
        ready=sorted(wid for wid in pending if not dependencies[wid]&pending)
        if not ready:ready=sorted(pending)  # workflow regions may reference each other in an otherwise valid DAG
        ordered.extend(ready);pending.difference_update(ready)
    for wid in ordered:
        if signature(current,wid)!=signature(saved,wid):layout_workflow(saved,wid)

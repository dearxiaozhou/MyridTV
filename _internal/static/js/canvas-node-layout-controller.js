/* Node grouping, alignment, sizing and spacing actions. */
(function(global){
    'use strict';

    const deps = {getContext:null};
    function configure(options){Object.assign(deps, options || {});}
    function context(){return deps.getContext ? deps.getContext() : {};}

    function selectedLayoutNodes(){
        const ctx = context();
        return ctx.selectedNodeIds().map(id => ctx.getNodes().find(node => node.id === id)).filter(Boolean);
    }

    function sortedSelectedLayoutNodes(){
        const ctx = context();
        return selectedLayoutNodes().sort((a, b) => {
            const ar = ctx.nodeRect(a), br = ctx.nodeRect(b);
            return ar.y - br.y || ar.x - br.x || String(a.id).localeCompare(String(b.id));
        });
    }

    /* 2026-10-07（老王："把打组改成：两个空节点也可以打组"）
       原来这里拿 `(node.images || []).length` 当准入条件，等于要求"节点已经有图片/产物"
       才能进组 —— 两个空节点会被过滤成 0 个，打组按钮直接 disabled，执行时还会弹
       smart.toastNeedGroup。现在放宽为：节点存在即可入组（空节点、空 Prompt 节点都行）。

       仍然排除组框本身（node.type === 'smart-group'），避免组套组 ——
       它以前是被 images.length 顺带挡掉的，去掉那个条件后必须显式挡。 */
    function groupableNode(node){
        return Boolean(node && node.id) && node.type !== 'smart-group';
    }

    function canGroupSelectedNodes(){
        const ctx = context();
        return ctx.selectedNodeIds().map(id => ctx.getNodes().find(node => node.id === id))
            .filter(groupableNode).length >= 2;
    }

    function refreshToolButtons(){
        const ctx = context();
        const hasMulti = selectedLayoutNodes().length >= 2;
        const canGroup = canGroupSelectedNodes();
        const selectedIds = new Set(ctx.selectedNodeIds());
        ctx.getWorld()?.querySelectorAll?.('.smart-node-toolbar').forEach(toolbar => {
            const nodeEl = toolbar.closest('.image-node');
            const nodeId = nodeEl ? nodeEl.dataset.id : '';
            toolbar.classList.toggle('show', hasMulti && selectedIds.has(nodeId));
        });
        ctx.getWorld()?.querySelectorAll?.('.smart-layout-tools').forEach(group => {
            group.classList.toggle('is-inactive', !hasMulti);
        });
        ctx.getWorld()?.querySelectorAll?.('[data-smart-node-action]').forEach(button => {
            const enabled = button.dataset.smartNodeAction === 'group' ? canGroup : hasMulti;
            button.disabled = !enabled;
            button.classList.toggle('disabled', !enabled);
        });
    }

    function createCanvasGroupForNodes(memberNodes, options={}){
        const ctx = context();
        const members = [...(memberNodes || [])].filter(node => node?.id);
        if(!members.length) return null;
        const rects = members.map(node => ctx.nodeRect(node));
        const x = Math.min(...rects.map(rect => rect.x));
        const y = Math.min(...rects.map(rect => rect.y));
        const padX = 18, padTop = 42, padBottom = 18;
        const right = Math.max(...rects.map(rect => rect.x + rect.width));
        const bottom = Math.max(...rects.map(rect => rect.y + rect.height));
        const group = {
            id:String(options.id || ctx.uid('smart')),
            type:'smart-group',
            x:Math.round(x - padX),
            y:Math.round(y - padTop),
            w:Math.round(right - x + padX * 2),
            h:Math.round(bottom - y + padTop + padBottom),
            title:String(options.title || 'Group'),
            memberIds:members.map(node => node.id),
            created_at:Number(options.created_at) || Date.now(),
            __origin:options.origin || 'user_manual'
        };
        if(options.addToStore !== false) ctx.addNodeToStore(group, options.origin || 'user_manual');
        return group;
    }

    function groupSelectedNodes(){
        const ctx = context();
        const domIds = [...ctx.getWorld().querySelectorAll('.image-node.selected')].map(el => el.dataset.id || '').filter(Boolean);
        const currentIds = ctx.getSelectedIds();
        const currentId = ctx.getSelectedId();
        const ids = domIds.length >= 2 ? domIds : (currentIds.length ? currentIds.slice() : (domIds.length ? domIds : (currentId ? [currentId] : [])));
        if(ids.length){
            ctx.setSelectedIds(ids.length > 1 ? ids.slice() : []);
            ctx.setSelectedId(ids.length === 1 ? ids[0] : '');
        }
        const selected = ids.map(id => ctx.getNodes().find(node => node.id === id)).filter(groupableNode);
        if(selected.length < 2){ctx.toast(ctx.tr('smart.toastNeedGroup'));return;}
        ctx.pushUndo();
        const group = createCanvasGroupForNodes(selected);
        ctx.setSelectedIds([]);
        ctx.setSelectedId(group.id);
        ctx.setSelectedImage({nodeId:'', index:-1});
        ctx.render();
        ctx.scheduleSave();
    }

    function alignSelectedNodesLeft(){
        const ctx = context(), selected = selectedLayoutNodes();
        if(selected.length < 2){ctx.toast('请选择 2 个以上节点');return false;}
        ctx.pushUndo();
        const left = Math.min(...selected.map(node => ctx.nodeRect(node).x));
        selected.forEach(node => {node.x = Math.round(left);});
        ctx.render();ctx.scheduleSave();ctx.toast('已左对齐');
        return true;
    }

    function alignSelectedNodesTop(){
        const ctx = context(), selected = selectedLayoutNodes();
        if(selected.length < 2){ctx.toast('请选择 2 个以上节点');return false;}
        ctx.pushUndo();
        const top = Math.min(...selected.map(node => ctx.nodeRect(node).y));
        selected.forEach(node => {node.y = Math.round(top);});
        ctx.render();ctx.scheduleSave();ctx.toast('已顶对齐');
        return true;
    }

    function matchSelectedNodeSizes(){
        const ctx = context(), selected = sortedSelectedLayoutNodes();
        if(selected.length < 2){ctx.toast('请选择 2 个以上节点');return false;}
        const reference = ctx.nodeRect(selected[0]);
        ctx.pushUndo();
        selected.forEach(node => {
            node.w = Math.max(28, Math.round(reference.width));
            node.h = Math.max(28, Math.round(reference.height));
            node.scale = 1;
        });
        ctx.render();ctx.scheduleSave();ctx.toast('已统一尺寸');
        return true;
    }

    function distributeSelectedNodesHorizontally(){
        const ctx = context();
        const selected = sortedSelectedLayoutNodes().slice().sort((a, b) => ctx.nodeRect(a).x - ctx.nodeRect(b).x);
        if(selected.length < 2){ctx.toast('请选择 2 个以上节点');return false;}
        const firstRect = ctx.nodeRect(selected[0]), secondRect = ctx.nodeRect(selected[1]);
        const gap = Math.max(0, Math.round(secondRect.x - (firstRect.x + firstRect.width)));
        ctx.pushUndo();
        let x = Math.round(firstRect.x);
        selected.forEach((node, index) => {
            if(index === 0){node.x = x;return;}
            x += Math.round(ctx.nodeRect(selected[index - 1]).width) + gap;
            node.x = x;
        });
        ctx.render();ctx.scheduleSave();ctx.toast('已左右等距');
        return true;
    }

    function distributeSelectedNodesVertically(){
        const ctx = context(), selected = sortedSelectedLayoutNodes();
        if(selected.length < 2){ctx.toast('请选择 2 个以上节点');return false;}
        const firstRect = ctx.nodeRect(selected[0]), secondRect = ctx.nodeRect(selected[1]);
        const gap = Math.max(0, Math.round(secondRect.y - (firstRect.y + firstRect.height)));
        ctx.pushUndo();
        let y = Math.round(firstRect.y);
        selected.forEach((node, index) => {
            if(index === 0){node.y = y;return;}
            y += Math.round(ctx.nodeRect(selected[index - 1]).height) + gap;
            node.y = y;
        });
        ctx.render();ctx.scheduleSave();ctx.toast('已上下等距');
        return true;
    }

    function handleToolAction(action, event=null){
        event?.preventDefault?.();event?.stopPropagation?.();event?.stopImmediatePropagation?.();
        if(action === 'group') return groupSelectedNodes();
        if(action === 'align-left') return alignSelectedNodesLeft();
        if(action === 'align-top') return alignSelectedNodesTop();
        if(action === 'same-size') return matchSelectedNodeSizes();
        if(action === 'distribute-horizontal') return distributeSelectedNodesHorizontally();
        if(action === 'distribute-vertical') return distributeSelectedNodesVertically();
    }

    function ungroupNode(groupId){
        const ctx = context();
        const nodes = ctx.getNodes();
        const group = nodes.find(node => node.id === groupId);
        if(!group || !Array.isArray(group.images) || group.images.length < 2) return false;
        ctx.pushUndo();
        const preservePositions = group.groupLayout?.mode === 'preserve';
        const layout = ctx.imageLayout(group.images || [], ctx.nodeScale(group), group);
        const pad = 16, gap = 8;
        const cell = Math.max(28, Math.round(layout.thumb || 96));
        const created = (group.images || []).map((img, index) => {
            const col = index % Math.max(1, layout.cols || 1);
            const row = Math.floor(index / Math.max(1, layout.cols || 1));
            const saved = img.groupPosition || {};
            const size = preservePositions
                ? {width:Math.max(28, Number(saved.w) || cell), height:Math.max(28, Number(saved.h) || cell)}
                : ctx.thumbDisplaySize(img, cell);
            const x = preservePositions
                ? Math.round(Number(group.x || 0) + Math.max(0, Number(saved.x) || 0))
                : Math.round(Number(group.x || 0) + pad + col * (cell + gap) + Math.max(0, (cell - size.width) / 2));
            const y = preservePositions
                ? Math.round(Number(group.y || 0) + Math.max(0, Number(saved.y) || 0))
                : Math.round(Number(group.y || 0) + pad + row * (cell + gap) + Math.max(0, (cell - size.height) / 2));
            const node = {
                id:ctx.uid('smart'),type:'smart-image',x,y,w:size.width,h:size.height,title:'Image',
                images:[ctx.stripImageGenerationMeta({...img, groupPosition:undefined})],
                scale:ctx.mediaNodeDefaultScale(),created_at:Date.now()
            };
            ctx.inheritNodeMetaFromImage(node);
            return node;
        });
        ctx.removeNodeFromStore(groupId);
        ctx.addNodesToStore(created, 'user_manual');
        const canvas = ctx.getCanvas();
        if(canvas) canvas.connections = (canvas.connections || []).filter(connection => connection.from !== groupId && connection.to !== groupId);
        nodes.forEach(node => {
            if(Array.isArray(node.inputNodeIds)) node.inputNodeIds = node.inputNodeIds.filter(inputId => inputId !== groupId);
        });
        ctx.setSelectedIds(created.map(node => node.id));
        ctx.setSelectedId(created.length === 1 ? created[0].id : '');
        ctx.setSelectedImage({nodeId:'', index:-1});
        ctx.render();ctx.scheduleSave();
        return true;
    }

    global.CanvasNodeLayoutController = {
        configure,
        selectedLayoutNodes,
        sortedSelectedLayoutNodes,
        canGroupSelectedNodes,
        refreshToolButtons,
        groupSelectedNodes,
        alignSelectedNodesLeft,
        alignSelectedNodesTop,
        matchSelectedNodeSizes,
        distributeSelectedNodesHorizontally,
        distributeSelectedNodesVertically,
        handleToolAction,
        createCanvasGroupForNodes,
        ungroupNode
    };
})(typeof window !== 'undefined' ? window : globalThis);

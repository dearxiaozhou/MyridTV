/* Node cloning, clipboard paste and duplicate gesture state. */
(function(global){
    'use strict';

    const deps = {getContext:null};
    let clipboard = null;
    function configure(options){Object.assign(deps, options || {});}
    function context(){return deps.getContext ? deps.getContext() : {};}
    function hasClipboardNodes(){return Boolean(clipboard?.nodes?.length);}

    function cloneNode(node, dx=0, dy=0){
        const ctx = context();
        const copy = JSON.parse(JSON.stringify(node));
        copy.id = ctx.uid(node.type === 'smart-prompt' ? 'prompt' : node.type === 'smart-loop' ? 'loop' : 'smart');
        delete copy.artifactId;
        copy.x = (Number(node.x) || 0) + dx;
        copy.y = (Number(node.y) || 0) + dy;
        copy.running = false;
        copy.pending = 0;
        delete copy.runStartedAt;
        delete copy.runFinishedAt;
        delete copy.runElapsedMs;
        delete copy.runTimerHidden;
        return copy;
    }

    function duplicateConnections(sourceId, copyId){
        const ctx = context();
        const canvas = ctx.getCanvas();
        const planned = ctx.planDuplicateConnections(canvas?.connections || [], sourceId, copyId) || [];
        planned.forEach(conn => {
            if((conn.kind || 'flow') === 'input') ctx.connectInputNode(conn.from, conn.to);
            else ctx.addConnection(conn.from, conn.to, conn.kind || 'flow');
        });
    }

    function duplicateNodeWithConnections(nodeOrId, dx=48, dy=36){
        const ctx = context();
        const source = typeof nodeOrId === 'string' ? (ctx.getNodes() || []).find(node => node.id === nodeOrId) : nodeOrId;
        if(!source) return null;
        ctx.pushUndo();
        const copy = cloneNode(source, dx, dy);
        ctx.nodeStore.addNode(copy, 'user_manual');
        duplicateConnections(source.id, copy.id);
        ctx.setSelectedId(copy.id);
        ctx.setSelectedIds([]);
        ctx.setSelectedImage({nodeId:'', index:-1});
        ctx.bringNodesToFront(copy.id);
        ctx.render();
        ctx.scheduleSave();
        ctx.toast('已复制节点');
        return copy;
    }

    function copySelectedNodes(){
        const ctx = context();
        if(!ctx.getCanvas() || ctx.isEditableTarget(ctx.getActiveElement())) return false;
        const ids = ctx.selectedNodeIds();
        const copiedNodes = ids.map(id => (ctx.getNodes() || []).find(node => node.id === id)).filter(Boolean);
        if(!copiedNodes.length) return false;
        const idSet = new Set(copiedNodes.map(node => node.id));
        const copiedConnections = (ctx.getCanvas().connections || []).filter(conn => idSet.has(conn.from) && idSet.has(conn.to));
        clipboard = {
            nodes:JSON.parse(JSON.stringify(copiedNodes)),
            connections:JSON.parse(JSON.stringify(copiedConnections))
        };
        ctx.toast(`已复制 ${copiedNodes.length} 个节点`);
        return true;
    }

    function pasteNodes(){
        const ctx = context();
        const canvas = ctx.getCanvas();
        if(!canvas || !hasClipboardNodes() || ctx.isEditableTarget(ctx.getActiveElement())) return false;
        ctx.setLastNodePasteAt(Date.now());
        ctx.pushUndo();
        const sourceNodes = clipboard.nodes;
        const xs = sourceNodes.map(node => Number(node.x) || 0);
        const ys = sourceNodes.map(node => Number(node.y) || 0);
        const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
        const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
        const point = ctx.getLastMouseWorld() || ctx.viewportCenter();
        const dx = point.x - cx;
        const dy = point.y - cy;
        const idMap = new Map();
        const copies = sourceNodes.map(node => {
            const copy = cloneNode(node, dx, dy);
            idMap.set(node.id, copy.id);
            return copy;
        });
        copies.forEach(copy => {
            if(Array.isArray(copy.inputNodeIds)) copy.inputNodeIds = copy.inputNodeIds.map(id => idMap.get(id)).filter(Boolean);
            if(copy.sourceNodeId) copy.sourceNodeId = idMap.get(copy.sourceNodeId) || '';
        });
        const newConnections = (clipboard.connections || []).map(conn => ({
            ...conn,
            from:idMap.get(conn.from),
            to:idMap.get(conn.to)
        })).filter(conn => conn.from && conn.to && conn.from !== conn.to);
        canvas.connections = [...(canvas.connections || []), ...newConnections];
        ctx.nodeStore.addNodes(copies, 'user_manual');
        ctx.setSelectedId(copies.length === 1 ? copies[0].id : '');
        ctx.setSelectedIds(copies.length > 1 ? copies.map(node => node.id) : []);
        ctx.setSelectedImage({nodeId:'', index:-1});
        ctx.render();
        ctx.scheduleSave();
        return copies;
    }

    function duplicateForAltDrag(node){
        const ctx = context();
        const ids = ctx.isNodeSelected(node.id) ? ctx.selectedNodeIds() : [node.id];
        const sourceNodes = ids.map(id => (ctx.getNodes() || []).find(item => item.id === id)).filter(Boolean);
        if(!sourceNodes.length) return node;
        ctx.pushUndo();
        const idMap = new Map();
        const copies = sourceNodes.map(source => {
            const copy = cloneNode(source, 0, 0);
            idMap.set(source.id, copy.id);
            return copy;
        });
        copies.forEach(copy => {
            if(Array.isArray(copy.inputNodeIds)) copy.inputNodeIds = copy.inputNodeIds.map(id => idMap.get(id)).filter(Boolean);
            if(copy.sourceNodeId) copy.sourceNodeId = idMap.get(copy.sourceNodeId) || '';
        });
        const idSet = new Set(sourceNodes.map(source => source.id));
        const copiedConnections = (ctx.getCanvas()?.connections || []).filter(conn => idSet.has(conn.from) && idSet.has(conn.to));
        const newConnections = copiedConnections.map(conn => ({...conn, from:idMap.get(conn.from), to:idMap.get(conn.to)}))
            .filter(conn => conn.from && conn.to && conn.from !== conn.to);
        const canvas = ctx.getCanvas();
        if(canvas) canvas.connections = [...(canvas.connections || []), ...newConnections];
        ctx.nodeStore.addNodes(copies, 'user_manual');
        ctx.setSelectedId('');
        ctx.setSelectedIds([]);
        ctx.setSelectedImage({nodeId:'', index:-1});
        const dragCopy = copies.find(copy => copy.id === idMap.get(node.id)) || copies[0];
        ctx.render();
        ctx.scheduleSave();
        return dragCopy;
    }

    global.CanvasNodeClipboardController = {
        configure,
        hasClipboardNodes,
        cloneNode,
        duplicateConnections,
        duplicateNodeWithConnections,
        copySelectedNodes,
        pasteNodes,
        duplicateForAltDrag
    };
})(typeof window !== 'undefined' ? window : globalThis);

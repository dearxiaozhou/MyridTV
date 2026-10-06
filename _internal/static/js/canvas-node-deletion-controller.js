/* Atomic node deletion and keyboard deletion behavior. */
(function(global){
    'use strict';

    const deps = {getContext:null};
    function configure(options){Object.assign(deps, options || {});}
    function context(){return deps.getContext ? deps.getContext() : {};}

    function candidateNodeIds(){
        const ctx = context();
        const nodes = ctx.getNodes() || [];
        const existing = new Set(nodes.map(node => node.id));
        const ids = [];
        const add = id => {
            if(id && existing.has(id) && !ids.includes(id)) ids.push(id);
        };
        (ctx.selectedNodeIds() || []).forEach(add);
        ctx.getWorld()?.querySelectorAll?.('.image-node.selected').forEach(el => add(el.dataset.id || ''));
        add(ctx.getSelectedImage()?.nodeId);
        return ids;
    }

    function deleteNodes(ids){
        const ctx = context();
        const nodes = ctx.getNodes() || [];
        const requested = new Set((ids || []).filter(Boolean));
        const baseIds = nodes.filter(node => requested.has(node.id)).map(node => node.id);
        if(!baseIds.length) return false;

        ctx.pushUndo();
        const deleteIds = new Set(baseIds);
        baseIds.forEach(id => {
            const node = nodes.find(item => item.id === id);
            if(node) delete node.retainOutputNames;
        });
        nodes.forEach(node => {
            if(ctx.isHistoryGroupNode(node) && baseIds.includes(node.historyFor)) deleteIds.add(node.id);
        });

        // The controller owns the single render/save at the end of the deletion transaction.
        ctx.nodeStore.removeNodes([...deleteIds], {render:false, save:false});
        ctx.pruneCanvasObjectReferences();
        const canvas = ctx.getCanvas();
        if(canvas) canvas.connections = (canvas.connections || []).filter(conn => !deleteIds.has(conn.from) && !deleteIds.has(conn.to));
        ctx.getNodes().forEach(node => {
            if(Array.isArray(node.inputNodeIds)) node.inputNodeIds = node.inputNodeIds.filter(id => !deleteIds.has(id));
        });
        if(deleteIds.has(ctx.getSelectedId())) ctx.setSelectedId('');
        ctx.setSelectedIds((ctx.getSelectedIds() || []).filter(id => !deleteIds.has(id)));
        if(deleteIds.has(ctx.getSelectedImage()?.nodeId)) ctx.setSelectedImage({nodeId:'', index:-1});
        ctx.render();
        ctx.scheduleSave();
        return true;
    }

    function clearNodeMediaBeforeDelete(id){
        const ctx = context();
        const node = (ctx.getNodes() || []).find(item => item.id === id);
        if(!node || (node.type && node.type !== 'smart-image')) return false;
        if(!(node.images || []).length && !node.pending) return false;

        ctx.pushUndo();
        node.images = [];
        node.pending = 0;
        node.running = false;
        node.title = ctx.emptyNodeTitle();
        delete node.w;
        delete node.h;
        delete node.cardSize;
        delete node.cardSizing;
        const history = ctx.historyGroupForNode(node);
        if(history){
            ctx.nodeStore.removeNode(history.id, {render:false, save:false});
            const canvas = ctx.getCanvas();
            if(canvas) canvas.connections = (canvas.connections || []).filter(conn => conn.from !== history.id && conn.to !== history.id);
        }
        if(ctx.getSelectedImage()?.nodeId === id) ctx.setSelectedImage({nodeId:'', index:-1});
        ctx.setSelectedId(id);
        ctx.setSelectedIds([]);
        ctx.render();
        ctx.scheduleSave();
        return true;
    }

    function deleteNodeFromButton(id){
        if(clearNodeMediaBeforeDelete(id)) return true;
        return deleteNodes([id]);
    }

    function deleteSelectedNodesFromKeyboard(event=null){
        const ctx = context();
        if(event && ctx.isEditableTarget(event.target)) return false;
        if(ctx.isImageEditModalOpen()) return false;
        const ids = candidateNodeIds();
        if(!ids.length){
            if(event && !ctx.isEditableTarget(event.target) && !ctx.hasFocusedPromptInput()){
                ctx.toast('未找到选中的节点，请先点击选中画布节点再按 Del');
            }
            return false;
        }
        event?.preventDefault?.();
        event?.stopPropagation?.();
        event?.stopImmediatePropagation?.();
        ctx.setDeleteShortcutHandledAt(Date.now());
        return deleteNodes(ids);
    }

    function isDeleteShortcut(event){
        return event?.key === 'Delete' || event?.key === 'Del' || event?.code === 'Delete';
    }

    global.CanvasNodeDeletionController = {
        configure,
        candidateNodeIds,
        deleteNodes,
        deleteNodeFromButton,
        deleteSelectedNodesFromKeyboard,
        isDeleteShortcut
    };
})(typeof window !== 'undefined' ? window : globalThis);

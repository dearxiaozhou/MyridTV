/* Canvas undo history: snapshots, pending gesture commits and restoration. */
(function(global){
    'use strict';

    const HISTORY_LIMIT = 40;
    const deps = {getContext:null};
    const undoStack = [];
    let pendingSnapshot = null;

    function configure(options){Object.assign(deps, options || {});}
    function context(){return deps.getContext ? deps.getContext() : {};}

    function snapshot(){
        const ctx = context();
        return {
            nodes: JSON.parse(JSON.stringify(ctx.getNodes() || [])),
            connections: JSON.parse(JSON.stringify(ctx.getCanvas()?.connections || [])),
            selectedId: ctx.getSelectedId(),
            selectedIds: (ctx.getSelectedIds() || []).slice(),
            selectedImage: {...(ctx.getSelectedImage() || {nodeId:'', index:-1})}
        };
    }

    function appendSnapshot(value){
        if(!value) return;
        undoStack.push(value);
        if(undoStack.length > HISTORY_LIMIT) undoStack.shift();
    }

    function capturePending(){pendingSnapshot = snapshot();}
    function commitPending(){
        if(!pendingSnapshot) return;
        appendSnapshot(pendingSnapshot);
        pendingSnapshot = null;
    }
    function discardPending(){pendingSnapshot = null;}
    function push(){
        const ctx = context();
        if(ctx.isSuppressed() || !ctx.getCanvas()) return;
        appendSnapshot(snapshot());
    }

    function restore(value){
        const ctx = context();
        const wasSuppressed = ctx.isSuppressed();
        ctx.setSuppressed(true);
        try{
            ctx.setNodes(value.nodes);
            // Restoring deleted nodes must also clear tombstones, or the next save
            // would filter the restored nodes out again.
            ctx.nodeStore.untombstone(value.nodes.map(node => node.id));
            const canvas = ctx.getCanvas();
            if(canvas) canvas.connections = value.connections;
            ctx.setSelectedId(value.selectedId);
            ctx.setSelectedIds(value.selectedIds);
            ctx.setSelectedImage(value.selectedImage);
            ctx.clearComposerSelection();
            ctx.render();
            ctx.scheduleSave();
        } finally {
            ctx.setSuppressed(wasSuppressed);
        }
    }

    function undo(){
        const ctx = context();
        if(!undoStack.length){ctx.toast(ctx.tr('smart.toastNoUndo'));return false;}
        restore(undoStack.pop());
        ctx.toast(ctx.tr('smart.toastUndone'));
        return true;
    }

    global.CanvasUndoController = {
        configure,
        snapshot,
        capturePending: capturePending,
        commitPending,
        discardPending,
        push,
        undo,
        getUndoDepth: () => undoStack.length
    };
})(typeof window !== 'undefined' ? window : globalThis);

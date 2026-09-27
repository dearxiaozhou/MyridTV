/* Node selection state, focus handoff and selection UI synchronization. */
(function(global){
    'use strict';

    const deps = {getContext:null};
    function configure(options){Object.assign(deps, options || {});}
    function context(){return deps.getContext ? deps.getContext() : {};}

    function selectedNode(){
        const ctx = context();
        return (ctx.getNodes() || []).find(node => node.id === ctx.getSelectedId()) || null;
    }

    function clearSelection(){
        const ctx = context();
        ctx.savePromptDraftForCurrent();
        ctx.setSelectedId('');
        ctx.setSelectedIds([]);
        ctx.setSelectedImage({nodeId:'', index:-1});
        ctx.setFrontNodeIds([]);
    }

    function isNodeSelected(id){
        const ctx = context();
        return ctx.getSelectedId() === id || (ctx.getSelectedIds() || []).includes(id);
    }

    function selectedNodeIds(){
        const ctx = context();
        const ids = ctx.getSelectedIds() || [];
        return ids.length ? ids.slice() : (ctx.getSelectedId() ? [ctx.getSelectedId()] : []);
    }

    function syncSelectionUi(){
        const ctx = context();
        const selectedImage = ctx.getSelectedImage() || {nodeId:'', index:-1};
        ctx.getWorld().querySelectorAll('.image-node').forEach(el => {
            const id = el.dataset.id || '';
            el.classList.toggle('selected', isNodeSelected(id));
            el.style.zIndex = String(ctx.nodeLayerZ(id));
            el.querySelectorAll('.thumb-item,.image-wrap').forEach(item => {
                const index = Number(item.dataset.imageIndex || 0);
                item.classList.toggle('image-selected', selectedImage.nodeId === id && selectedImage.index === index);
            });
        });
        ctx.scheduleConnectionLayerRefresh();
        ctx.refreshSmartNodeToolButtons();
    }

    function focusCanvasWorld(){
        const world = context().getWorld();
        try{
            if(world){
                if(!world.hasAttribute('tabindex')) world.setAttribute('tabindex', '-1');
                if(document.activeElement !== world) world.focus({preventScroll:true});
            }
        }catch(_){}
    }

    function selectNodeFromPointer(nodeId, event=null, options={}){
        if(!nodeId) return [];
        const ctx = context();
        try{
            const active = document.activeElement;
            if(active && active !== document.body && active.closest?.('input, textarea, [contenteditable="true"], .prompt-input')) active.blur();
        }catch(_){}
        focusCanvasWorld();

        const imageIndex = Number(options.imageIndex);
        const hasImageIndex = Number.isFinite(imageIndex);
        if(event?.shiftKey){
            const current = selectedNodeIds();
            const exists = current.includes(nodeId);
            const next = exists ? current.filter(id => id !== nodeId) : [...current, nodeId];
            ctx.setSelectedIds(next);
            ctx.setSelectedId(next.length === 1 ? next[0] : '');
            if(hasImageIndex && !exists){
                ctx.setSelectedImage({nodeId, index:imageIndex});
            } else if(!next.includes(ctx.getSelectedImage()?.nodeId)){
                ctx.setSelectedImage({nodeId:'', index:-1});
            }
            ctx.bringNodesToFront(next);
            return next;
        }

        ctx.setSelectedId(nodeId);
        ctx.setSelectedIds([]);
        ctx.setSelectedImage(hasImageIndex ? {nodeId, index:imageIndex} : {nodeId:'', index:-1});
        ctx.bringNodesToFront(nodeId);
        return [nodeId];
    }

    global.CanvasNodeSelectionController = {
        configure,
        selectedNode,
        clearSelection,
        syncSelectionUi,
        isNodeSelected,
        selectedNodeIds,
        focusCanvasWorld,
        selectNodeFromPointer
    };
})(typeof window !== 'undefined' ? window : globalThis);

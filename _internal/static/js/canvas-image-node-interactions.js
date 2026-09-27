/* Image-node thumbnail gestures: selection, preview, context menu and detach drag. */
(function(global){
    'use strict';

    const deps = {getContext:null};
    function configure(options){Object.assign(deps, options || {});}
    function context(){return deps.getContext ? deps.getContext() : {};}

    function bindItems(el, nodeId){
        const ctx = context();
        if(!el || !nodeId) return;
        el.querySelectorAll('.thumb-item,.image-wrap').forEach(item => {
            item.setAttribute('draggable', 'false');
            item.addEventListener('dragstart', event => event.preventDefault());
            item.addEventListener('mousedown', event => {
                if(global.CanvasImageCrop?.startSelection(event, nodeId, item)) return;
                if(event.button !== 0 || event.target.closest('.image-delete, .smart-crop-action, .smart-node-action, .smart-image-name-label, .smart-image-name-input')) return;
                ctx.bringNodesToFront(nodeId);
                if(event.detail < 2){
                    const imageIndex = Number(item.dataset.imageIndex || 0);
                    const node = ctx.getNodes().find(candidate => candidate.id === nodeId);
                    ctx.hideRunTimerForNode(node);
                    const selectedIds = ctx.getSelectedIds();
                    const keepMultiSelection = !event.shiftKey && selectedIds.length > 1 && selectedIds.includes(nodeId);
                    if(!keepMultiSelection) ctx.selectNodeFromPointer(nodeId, {shiftKey:event.shiftKey}, {imageIndex});
                    if(ctx.smartCascadeAnyRunning()) ctx.setSmartCascadeSilentSelection(false);
                    ctx.syncSelectionUi();
                    ctx.updateComposer();
                    return;
                }
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
                ctx.clearImageClickTimer();
                ctx.setSuppressImageClickUntil(Date.now() + 260);
                ctx.setSelectedId(nodeId);
                ctx.setSelectedIds([]);
                ctx.setSelectedImage({nodeId, index:Number(item.dataset.imageIndex || 0)});
                ctx.bringNodesToFront(nodeId);
                ctx.openImagePreview(nodeId, Number(item.dataset.imageIndex || 0));
            }, true);
            item.addEventListener('click', event => {
                if(event.target.closest('.image-delete, .smart-crop-action, .smart-node-action, .smart-image-name-label, .smart-image-name-input')) return;
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
                if(Date.now() < ctx.getSuppressImageClickUntil()) return;
                const imageIndex = Number(item.dataset.imageIndex || 0);
                if(event.detail >= 2){
                    ctx.clearImageClickTimer();
                    ctx.setSuppressImageClickUntil(Date.now() + 260);
                    ctx.setSelectedId(nodeId);
                    ctx.setSelectedIds([]);
                    ctx.setSelectedImage({nodeId, index:imageIndex});
                    ctx.bringNodesToFront(nodeId);
                    ctx.openImagePreview(nodeId, imageIndex);
                }
            });
            item.addEventListener('dblclick', event => {
                if(event.target.closest('.image-delete, .smart-crop-action, .smart-node-action, .smart-image-name-label, .smart-image-name-input')) return;
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
                ctx.clearImageClickTimer();
                ctx.setSuppressImageClickUntil(Date.now() + 260);
                ctx.setSelectedId(nodeId);
                ctx.setSelectedIds([]);
                ctx.setSelectedImage({nodeId, index:Number(item.dataset.imageIndex || 0)});
                ctx.bringNodesToFront(nodeId);
                ctx.openImagePreview(nodeId, Number(item.dataset.imageIndex || 0));
            }, true);
            item.addEventListener('contextmenu', event => {
                if(event.altKey || event.target.closest('.image-delete, .smart-crop-action, .smart-node-action, .smart-image-name-label, .smart-image-name-input')) return;
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation?.();
                ctx.clearImageClickTimer();
                ctx.setSuppressImageClickUntil(Date.now() + 220);
                ctx.openSmartImageContextMenu(nodeId, Number(item.dataset.imageIndex || 0), event);
            }, true);
        });

        el.querySelectorAll('.thumb-item').forEach(item => {
            item.addEventListener('mousedown', event => {
                if(global.CanvasImageCrop?.isActive()) return;
                if(event.button !== 0 || event.target.closest('.mini-x, .smart-crop-action, .smart-node-action')) return;
                if(event.detail >= 2) return;
                const node = ctx.getNodes().find(candidate => candidate.id === nodeId);
                if(!node || (node.images || []).length <= 1) return;
                event.preventDefault();
                event.stopPropagation();
                ctx.setThumbDragState({nodeId, imgIndex:Number(item.dataset.imageIndex || 0), startX:event.clientX, startY:event.clientY, detached:false});
                global.CanvasInteractionMachine?.begin('thumb-drag');
                ctx.capturePendingUndo();
            });
        });
    }

    global.CanvasImageNodeInteractions = {configure, bindItems};
})(typeof window !== 'undefined' ? window : globalThis);

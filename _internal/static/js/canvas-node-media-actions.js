/* Image-node action buttons: crop tools, layout actions and media renaming. */
(function(global){
    'use strict';

    const deps = {getContext:null};
    function configure(options){Object.assign(deps, options || {});}
    function context(){return deps.getContext ? deps.getContext() : {};}

    function bind(el, nodeId){
        const ctx = context();
        if(!el || !nodeId) return;
        el.querySelectorAll('.image-delete').forEach(btn => {
            btn.addEventListener('click', event => {
                event.preventDefault();
                event.stopPropagation();
                ctx.deleteImage(nodeId, Number(btn.dataset.imageIndex));
            });
        });
        el.querySelectorAll('.smart-crop-action').forEach(btn => {
            btn.addEventListener('mousedown', event => {
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation?.();
            }, true);
            btn.addEventListener('click', event => ctx.openSmartImageTool(
                nodeId,
                Number(btn.dataset.cropIndex || 0),
                btn.dataset.toolMode || 'free-crop',
                event
            ));
        });
        el.querySelectorAll('[data-smart-node-action]').forEach(btn => {
            btn.addEventListener('mousedown', event => {
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation?.();
            }, true);
            btn.addEventListener('click', event => ctx.handleSmartNodeToolAction(btn.dataset.smartNodeAction || '', event));
        });
        el.querySelectorAll('.smart-image-name-label').forEach(label => {
            label.addEventListener('mousedown', event => {
                event.preventDefault();
                event.stopPropagation();
            }, true);
            label.addEventListener('click', event => {
                event.preventDefault();
                event.stopPropagation();
            });
            label.addEventListener('dblclick', event => {
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation?.();
                ctx.clearImageClickTimer();
                ctx.setSuppressImageClickUntil(Date.now() + 260);
                ctx.beginSmartImageRename(nodeId, Number(label.dataset.imageNameIndex || 0), label);
            }, true);
        });
    }

    global.CanvasNodeMediaActions = {configure, bind};
})(typeof window !== 'undefined' ? window : globalThis);

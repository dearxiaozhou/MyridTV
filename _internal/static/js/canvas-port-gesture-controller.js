/* Port gesture entry: begin an edge drag and maintain its temporary visual. */
(function(global){
    'use strict';

    const deps = {getContext:null};
    function configure(options){Object.assign(deps, options || {});}
    function context(){return deps.getContext ? deps.getContext() : {};}

    function bind(el, nodeId){
        const ctx = context();
        if(!el || !nodeId) return;
        el.querySelectorAll('.node-port').forEach(port => {
            port.addEventListener('mousedown', event => {
                if(event.button !== 0) return;
                event.preventDefault();
                event.stopPropagation();
                ctx.setPortDragState({
                    fromId:nodeId,
                    fromPort:port.dataset.port,
                    currentWorld:ctx.screenToWorld(event),
                    hoverTargetId:'',
                    hoverPort:'',
                    moved:false
                });
                global.CanvasInteractionMachine?.begin('connecting');
                ctx.getShell().classList.add('port-dragging');
                ctx.capturePendingUndo();
                ctx.ensurePortDragPathElement();
                ctx.updatePortDragVisual();
            });
            port.addEventListener('click', event => event.stopPropagation());
            port.addEventListener('dblclick', event => event.stopPropagation());
        });
    }

    global.CanvasPortGestureController = {configure, bind};
})(typeof window !== 'undefined' ? window : globalThis);

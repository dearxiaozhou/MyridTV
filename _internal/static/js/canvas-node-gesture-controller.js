/* Node body gestures: begin direct dragging and resize interactions. */
(function(global){
    'use strict';

    const deps = {getContext:null};
    let dropHighlightEl = null;
    function configure(options){Object.assign(deps, options || {});}
    function context(){return deps.getContext ? deps.getContext() : {};}

    function canvasGroupDropTargetFor(node){
        const ctx = context();
        if(!node || ctx.isCanvasGroupNode(node)) return null;
        const rect = ctx.nodeRect(node);
        const cx = rect.x + rect.width / 2;
        const cy = rect.y + rect.height / 2;
        return ctx.getNodes().filter(group => ctx.isCanvasGroupNode(group) && !((group.memberIds || []).includes(node.id)))
            .filter(group => {
                const groupRect = ctx.nodeRect(group);
                return cx >= groupRect.x && cx <= groupRect.x + groupRect.width && cy >= groupRect.y && cy <= groupRect.y + groupRect.height;
            })
            .sort((a, b) => ctx.nodeLayerZ(b) - ctx.nodeLayerZ(a))[0] || null;
    }

    function addNodeToCanvasGroup(node, group){
        const ctx = context();
        if(!node || !group || !ctx.isCanvasGroupNode(group)) return false;
        const memberIds = Array.isArray(group.memberIds) ? group.memberIds : [];
        if(memberIds.includes(node.id)) return false;
        group.memberIds = [...memberIds, node.id];
        return true;
    }

    function removeNodeOutsideCanvasGroups(node){
        const ctx = context();
        if(!node || ctx.isCanvasGroupNode(node)) return false;
        const rect = ctx.nodeRect(node);
        let changed = false;
        ctx.getNodes().filter(group => ctx.isCanvasGroupNode(group) && (group.memberIds || []).includes(node.id)).forEach(group => {
            const groupRect = ctx.nodeRect(group);
            const outside = rect.x + rect.width <= groupRect.x || rect.x >= groupRect.x + groupRect.width
                || rect.y + rect.height <= groupRect.y || rect.y >= groupRect.y + groupRect.height;
            if(!outside) return;
            group.memberIds = group.memberIds.filter(memberId => memberId !== node.id);
            changed = true;
        });
        return changed;
    }

    function clearDropHighlight(){
        if(dropHighlightEl){
            dropHighlightEl.classList.remove('drop-target');
            dropHighlightEl = null;
        }
    }

    function setDropHighlight(targetId){
        if(dropHighlightEl?.dataset?.id === targetId) return;
        clearDropHighlight();
        if(!targetId) return;
        const el = context().getWorld()?.querySelector(`.image-node[data-id="${targetId}"]`);
        if(el){
            el.classList.add('drop-target');
            dropHighlightEl = el;
        }
    }

    function moveNodeElementsDuringDrag(){
        const ctx = context();
        const drag = ctx.getDragState();
        if(!drag) return;
        const groupItems = drag.group || [{id:drag.id}];
        groupItems.map(item => item.id).forEach(id => {
            const node = ctx.getNodes().find(item => item.id === id);
            const el = ctx.getWorld()?.querySelector(`.image-node[data-id="${global.CSS.escape(id)}"]`);
            if(node && el){
                const origin = groupItems.find(item => item.id === id);
                const dx = (Number(node.x) || 0) - (Number(origin?.ox) || 0);
                const dy = (Number(node.y) || 0) - (Number(origin?.oy) || 0);
                el.style.transform = `translate3d(${dx}px, ${dy}px, 0)`;
            }
        });
        const active = ctx.selectedNode();
        if(active && groupItems.some(item => item.id === active.id)) ctx.positionComposerForNode(active);
    }

    function commitDraggedNodeElementPositions(){
        const ctx = context();
        const drag = ctx.getDragState();
        if(!drag) return;
        const groupItems = drag.group || [{id:drag.id}];
        groupItems.forEach(item => {
            const node = ctx.getNodes().find(candidate => candidate.id === item.id);
            const el = ctx.getWorld()?.querySelector(`.image-node[data-id="${global.CSS.escape(item.id)}"]`);
            if(!node || !el) return;
            el.style.left = `${node.x || 0}px`;
            el.style.top = `${node.y || 0}px`;
            el.style.transform = '';
        });
    }

    function updateDragFrame(event){
        const ctx = context();
        const drag = ctx.getDragState();
        if(!drag) return;
        const nodes = ctx.getNodes();
        const node = nodes.find(item => item.id === drag.id);
        if(!node) return;
        const moveDx = (event.clientX - drag.startX) / ctx.getViewportScale();
        const moveDy = (event.clientY - drag.startY) / ctx.getViewportScale();
        (drag.group || [{id:drag.id, ox:drag.ox, oy:drag.oy}]).forEach(item => {
            const moved = nodes.find(candidate => candidate.id === item.id);
            if(!moved) return;
            moved.x = item.ox + moveDx;
            moved.y = item.oy + moveDy;
        });
        if(ctx.isAssetLibraryOpen()){
            const hit = global.document.elementFromPoint(event.clientX, event.clientY);
            if(hit && ctx.getAssetPanel()?.contains(hit)){
                ctx.setAssetDragOver(true);
                clearDropHighlight();
                return;
            }
            ctx.setAssetDragOver(false);
        }
        moveNodeElementsDuringDrag();
        setDropHighlight(canvasGroupDropTargetFor(node)?.id || '');
    }

    function queueDragFrame(event){
        const drag = context().getDragState();
        if(!drag) return;
        drag.pendingClientX = event.clientX;
        drag.pendingClientY = event.clientY;
        if(drag.frame) return;
        drag.frame = global.requestAnimationFrame(() => {
            const current = context().getDragState();
            if(!current) return;
            current.frame = 0;
            updateDragFrame({clientX:current.pendingClientX, clientY:current.pendingClientY});
        });
    }

    function flushDragFrame(event){
        const drag = context().getDragState();
        if(!drag?.frame) return;
        global.cancelAnimationFrame(drag.frame);
        drag.frame = 0;
        drag.pendingClientX = event.clientX;
        drag.pendingClientY = event.clientY;
        updateDragFrame({clientX:event.clientX, clientY:event.clientY});
    }

    function finishDrag(event){
        const ctx = context();
        const drag = ctx.getDragState();
        if(!drag) return false;
        const nodes = ctx.getNodes();
        const draggedNode = nodes.find(node => node.id === drag.id);
        let stateChanged = false;
        const hit = global.document.elementFromPoint(event.clientX, event.clientY);
        const droppedOnAssetPanel = ctx.isAssetLibraryOpen() && hit && ctx.getAssetPanel()?.contains(hit);
        if(droppedOnAssetPanel && draggedNode && (draggedNode.images || []).length){
            (draggedNode.images || []).filter(img => img?.url).forEach(img => {
                ctx.addUrlToAssetLibrary(img.url, img.name || draggedNode.title || 'image');
            });
            (drag.group || [{id:drag.id, ox:drag.ox, oy:drag.oy}]).forEach(item => {
                const node = nodes.find(candidate => candidate.id === item.id);
                if(node){node.x = item.ox;node.y = item.oy;}
            });
            ctx.setAssetDragOver(false);
            ctx.discardPendingUndo();
            clearDropHighlight();
            ctx.setDragState(null);
            global.CanvasInteractionMachine?.end('dragging-node');
            global.document.body.classList.remove('smart-node-drag');
            ctx.render();
            ctx.scheduleSave();
            return true;
        }
        const movedNodes = (drag.group || [{id:drag.id}]).map(item => nodes.find(node => node.id === item.id)).filter(node => node && !ctx.isCanvasGroupNode(node));
        movedNodes.forEach(node => {
            const dropGroup = canvasGroupDropTargetFor(node);
            if(dropGroup && addNodeToCanvasGroup(node, dropGroup)) stateChanged = true;
            if(removeNodeOutsideCanvasGroups(node)) stateChanged = true;
        });
        if((drag.group || []).some(item => {
            const node = nodes.find(candidate => candidate.id === item.id);
            return node && (Math.abs((Number(node.x) || 0) - item.ox) > 1 || Math.abs((Number(node.y) || 0) - item.oy) > 1);
        }) || (draggedNode && (Math.abs((draggedNode.x || 0) - drag.ox) > 1 || Math.abs((draggedNode.y || 0) - drag.oy) > 1))){
            stateChanged = true;
        }
        if(drag.thumbDetached) stateChanged = true;
        if(stateChanged) ctx.commitPendingUndo();
        else ctx.discardPendingUndo();
        if(stateChanged || drag.thumbDetached) ctx.suppressNodeClick(180);
        clearDropHighlight();
        ctx.setLoopInsertPreview(null);
        commitDraggedNodeElementPositions();
        ctx.scheduleMinimapRender();
        ctx.setDragState(null);
        global.CanvasInteractionMachine?.end('dragging-node');
        ctx.scheduleSave();
        ctx.refreshConnectionLayer();
        return true;
    }

    function bind(el, nodeId){
        const ctx = context();
        if(!el || !nodeId) return;

        el.querySelector('.node-resize-handle')?.addEventListener('mousedown', event => {
            if(event.button !== 0) return;
            event.preventDefault();
            event.stopPropagation();
            const node = ctx.getNodes().find(item => item.id === nodeId);
            if(!node) return;
            const rect = ctx.nodeRect(node);
            ctx.setResizeState({
                id:nodeId,
                startX:event.clientX,
                startY:event.clientY,
                startW:rect.width,
                startH:rect.height,
                aspect:rect.width / Math.max(1, rect.height)
            });
            global.CanvasInteractionMachine?.begin('resizing');
            global.document.body.classList.add('smart-node-resize');
            ctx.capturePendingUndo();
        });

        el.onmousedown = event => {
            if(event.button !== 0 || event.target.closest('.mini-x, .node-resize-handle, .thumb-item, .node-port, select, input, button')) return;
            if(event.target.closest('.prompt-node-pill, .prompt-node-llm, textarea:not(.prompt-node-text)')) return;
            if(event.shiftKey) return;
            event.preventDefault();
            event.stopPropagation();
            global.window.getSelection?.()?.removeAllRanges?.();
            if(global.document.activeElement?.blur) global.document.activeElement.blur();

            const nodes = ctx.getNodes();
            let node = nodes.find(item => item.id === nodeId);
            if(!node) return;
            if(event.altKey) node = ctx.duplicateForAltDrag(node);

            const groupMembers = ctx.isCanvasGroupNode(node)
                ? (node.memberIds || []).filter(memberId => nodes.some(candidate => candidate.id === memberId))
                : [];
            const activeSelectedIds = ctx.selectedNodeIds().filter(selectedNodeId => nodes.some(candidate => candidate.id === selectedNodeId));
            const dragIds = groupMembers.length
                ? [node.id, ...groupMembers]
                : (activeSelectedIds.length > 1 && activeSelectedIds.includes(node.id)
                    ? activeSelectedIds
                    : [node.id]);

            ctx.bringNodesToFront(dragIds);
            const group = dragIds.map(dragId => {
                const item = nodes.find(candidate => candidate.id === dragId);
                return item ? {id:item.id, ox:Number(item.x) || 0, oy:Number(item.y) || 0} : null;
            }).filter(Boolean);
            ctx.setDragState({
                id:node.id,
                startX:event.clientX,
                startY:event.clientY,
                ox:node.x || 0,
                oy:node.y || 0,
                group,
                groupIds:group.map(item => item.id),
                ctrlGroup:Boolean(event.ctrlKey),
                layoutRects:new Map(nodes.map(candidate => [candidate.id, ctx.nodeRect(candidate)]))
            });
            global.CanvasInteractionMachine?.begin('dragging-node');
            global.document.body.classList.add('smart-node-drag');
            ctx.capturePendingUndo();
        };

        el.ondragover = event => ctx.setSmartDropCopyEffect(event);
        el.ondrop = async event => {
            event.preventDefault();
            event.stopPropagation();
            const payload = await ctx.resolveSmartImageDropPayload(event.dataTransfer);
            if(payload.type === 'none') return;
            await ctx.handleSmartImageDropPayload(payload, nodeId);
        };
    }

    global.CanvasNodeGestureController = {
        configure,
        bind,
        queueDragFrame,
        flushDragFrame,
        finishDrag,
        canvasGroupDropTargetFor,
        addNodeToCanvasGroup,
        removeNodeOutsideCanvasGroups,
        clearDropHighlight,
        setDropHighlight
    };
})(typeof window !== 'undefined' ? window : globalThis);

/* Generic node actions: selection, upload, rename and node-level commands. */
(function(global){
    'use strict';

    const deps = {getContext:null};
    function configure(options){Object.assign(deps, options || {});}
    function context(){return deps.getContext ? deps.getContext() : {};}

    function bind(el, nodeId){
        const ctx = context();
        if(!el || !nodeId) return;
        const beginCanvasGroupRename = label => {
            const node = ctx.getNodes().find(item => item.id === nodeId);
            if(!node || !label || label.dataset.renaming === '1') return;
            label.dataset.renaming = '1';
            ctx.capturePendingUndo();
            const input = global.document.createElement('input');
            input.className = 'canvas-group-title-input';
            input.type = 'text';
            input.value = node.title || '未命名组';
            input.setAttribute('aria-label', '组名称');
            input.spellcheck = false;
            const finish = () => {
                node.title = input.value.trim().slice(0, 80) || '未命名组';
                ctx.commitPendingUndo();
                ctx.scheduleSave();
                ctx.render();
            };
            input.addEventListener('mousedown', event => event.stopPropagation());
            input.addEventListener('click', event => event.stopPropagation());
            input.addEventListener('dblclick', event => event.stopPropagation());
            input.addEventListener('keydown', event => {
                if(event.key === 'Enter'){event.preventDefault();input.blur();}
                if(event.key === 'Escape'){input.value = node.title || '未命名组';input.blur();}
            });
            input.addEventListener('blur', finish, {once:true});
            label.replaceWith(input);
            input.focus();
            input.select();
        };

        el.onclick = event => {
            event.stopPropagation();
            if(ctx.isNodeClickSuppressed()) return;
            const node = ctx.getNodes().find(item => item.id === nodeId);
            ctx.hideRunTimerForNode(node);
            ctx.selectNodeFromPointer(nodeId, event);
            if(ctx.smartCascadeAnyRunning()) ctx.setSmartCascadeSilentSelection(false);
            ctx.syncSelectionUi();
            ctx.updateComposer();
        };
        el.ondblclick = event => event.stopPropagation();

        const uploadBtn = el.querySelector('.upload-node-btn');
        uploadBtn?.addEventListener('mousedown', event => {
            if(event.button !== 0) return;
            event.preventDefault();
            event.stopPropagation();
        }, true);
        uploadBtn?.addEventListener('click', event => {
            event.preventDefault();
            event.stopPropagation();
            ctx.hideRunTimerForNode(ctx.getNodes().find(item => item.id === nodeId));
            ctx.setSelectedId(nodeId);
            ctx.setSelectedIds([]);
            ctx.setSelectedImage({nodeId:'', index:-1});
            ctx.bringNodesToFront(nodeId);
            ctx.setPendingGroupUploadPoint(null);
            ctx.setUploadTargetId(nodeId);
            ctx.syncSelectionUi();
            ctx.updateComposer();
            ctx.pickMediaForSmartNode(nodeId);
        });

        el.querySelectorAll('.node-delete').forEach(btn => {
            btn.addEventListener('click', event => {
                event.preventDefault();
                event.stopPropagation();
                ctx.deleteNodeFromButton(nodeId);
            });
        });
        el.querySelectorAll('.node-set-toggle').forEach(btn => {
            btn.addEventListener('mousedown', event => {event.preventDefault();event.stopPropagation();}, true);
            btn.addEventListener('click', event => {
                event.preventDefault();
                event.stopPropagation();
                ctx.toggleCanvasNodeSet(nodeId);
            });
        });

        const title = el.querySelector('.canvas-group-title-display');
        title?.addEventListener('mousedown', event => {
            if(event.button === 0 && event.detail >= 2){
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation?.();
                beginCanvasGroupRename(event.currentTarget);
            }
        }, true);
        title?.addEventListener('dblclick', event => {
            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation?.();
            beginCanvasGroupRename(event.currentTarget);
        });
        el.querySelectorAll('[data-jimeng-query]').forEach(btn => {
            btn.addEventListener('mousedown', event => {event.preventDefault();event.stopPropagation();}, true);
            btn.addEventListener('click', event => {
                event.preventDefault();
                event.stopPropagation();
                ctx.queryJimengNow(btn.dataset.jimengQuery);
            });
        });
    }

    global.CanvasNodeActionController = {configure, bind};
})(typeof window !== 'undefined' ? window : globalThis);

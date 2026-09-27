/* Canvas keyboard commands, focus guards and modifier gesture cleanup. */
(function(global){
    'use strict';

    const deps = {};
    let captureBound = false;
    let canvasBound = false;
    let escapeBound = false;

    function configure(options){Object.assign(deps, options || {});}

    function bindNodeCaptureHandlers(){
        if(captureBound) return;
        captureBound = true;
        global.addEventListener('keydown', event => {
            if((deps.isDeleteShortcut(event) || event.key === 'Backspace') && deps.deleteSelectedNodesFromKeyboard(event)) return;
            const key = String(event.key || '').toLowerCase();
            if(!(event.ctrlKey || event.metaKey) || event.shiftKey || key !== 'g') return;
            if(event.target?.closest?.('.canvas-group-title-input')) return;
            const domIds = [...(deps.getWorld()?.querySelectorAll('.image-node.selected') || [])]
                .map(el => el.dataset.id || '').filter(Boolean);
            const ids = domIds.length ? domIds : deps.selectedNodeIds();
            if(ids.length < 2) return;
            event.preventDefault();
            event.stopImmediatePropagation();
            deps.groupSelectedNodes();
        }, true);
        global.addEventListener('keyup', event => {
            if(!(deps.isDeleteShortcut(event) || event.key === 'Backspace')) return;
            if(Date.now() - deps.getDeleteShortcutHandledAt() < 500) return;
            deps.deleteSelectedNodesFromKeyboard(event);
        }, true);
    }

    function bindCanvasHandlers(){
        if(canvasBound) return;
        canvasBound = true;
        global.addEventListener('keydown', event => {
            const key = String(event.key || '').toLowerCase();
            if(deps.isImageCropActive()){
                if(event.key === 'Enter'){
                    event.preventDefault();
                    event.stopPropagation();
                    deps.confirmImageCrop();
                    return;
                }
                if(event.key === 'Escape'){
                    event.preventDefault();
                    event.stopPropagation();
                    deps.stopImageCrop();
                    return;
                }
            }
            if(key === 'r' && !deps.isEditableTarget(event.target)) deps.setIsRKeyDown(true);
            if(deps.isImageEditOpen() && !deps.isEditableTarget(event.target)){
                if(event.key === 'ArrowLeft' || event.key === 'ArrowRight'){
                    event.preventDefault();
                    if(!deps.seekPreviewVideoFrames(event.key === 'ArrowLeft' ? -1 : 1)){
                        deps.navigatePreviewImage(event.key === 'ArrowLeft' ? -1 : 1);
                    }
                    return;
                }
            }
            if(!event.ctrlKey && !event.metaKey && !event.altKey && !deps.isEditableTarget(event.target)){
                if(key === 'z'){
                    if(event.repeat) return;
                    event.preventDefault();
                    deps.toggleZoomPreview();
                    return;
                }
                if(key === 'a'){
                    if(event.repeat) return;
                    event.preventDefault();
                    deps.toggleAssetLibrary();
                    return;
                }
            }
            if((event.ctrlKey || event.metaKey) && key === 'c' && !deps.isEditableTarget(event.target)){
                const selectionText = global.getSelection?.().toString() || '';
                if(selectionText) return;
                event.preventDefault();
                deps.copySelectedNodes();
                return;
            }
            if((event.ctrlKey || event.metaKey) && key === 'v' && !deps.isEditableTarget(event.target) && deps.hasClipboardNodes()){
                const requestedAt = Date.now();
                global.setTimeout(() => {
                    if(deps.getLastImagePasteAt() >= requestedAt) return;
                    if(deps.getLastNodePasteAt() >= requestedAt) return;
                    deps.pasteNodes();
                }, 90);
            }
            if(event.key === 'Escape' && deps.isImageEditOpen()){
                deps.closeImageEditor();
                return;
            }
            if((event.ctrlKey || event.metaKey) && key === 'z' && !deps.isEditableTarget(event.target)){
                event.preventDefault();
                deps.performUndo();
                return;
            }
            if((deps.isDeleteShortcut(event) || event.key === 'Backspace') && deps.deleteSelectedNodesFromKeyboard(event)) return;
            if((event.ctrlKey || event.metaKey) && event.shiftKey && key === 'g' && !deps.isEditableTarget(event.target)){
                event.preventDefault();
                const ids = deps.getSelectedIds().length ? deps.getSelectedIds().slice()
                    : (deps.getSelectedId() ? [deps.getSelectedId()] : []);
                const ok = ids.map(id => deps.ungroupNode(id)).some(Boolean);
                if(ok) return;
            }
            if((event.ctrlKey || event.metaKey) && key === 'g' && !event.shiftKey && !deps.isEditableTarget(event.target)){
                const selectedCount = deps.selectedNodeIds().length
                    || deps.getWorld().querySelectorAll('.image-node.selected').length;
                if(selectedCount >= 2){
                    event.preventDefault();
                    deps.groupSelectedNodes();
                }
            }
        });
        global.addEventListener('keyup', event => {
            if(String(event.key || '').toLowerCase() === 'r') deps.setIsRKeyDown(false);
            if(event.key === 'Alt' && deps.isConnectionCutActive()) deps.finishConnectionCutGesture();
        });
        global.addEventListener('blur', () => {
            deps.setIsRKeyDown(false);
            if(deps.isConnectionCutActive()) deps.finishConnectionCutGesture();
        });
    }

    function bindGlobalEscapeHandler(){
        if(escapeBound) return;
        escapeBound = true;
        global.document.addEventListener('keydown', event => {
            if(event.key === 'Escape') deps.closeGlobalOverlays();
        });
    }

    global.CanvasKeyboardShortcutController = {
        configure,
        bindNodeCaptureHandlers,
        bindCanvasHandlers,
        bindGlobalEscapeHandler
    };
})(typeof window !== 'undefined' ? window : globalThis);

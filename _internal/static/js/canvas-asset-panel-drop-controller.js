/* Owns asset-panel drag-over feedback and imported-media drop routing.
   Local-path drops are no longer supported (backend never implemented the import endpoint). */
(function(global){
    'use strict';

    const deps = {};
    const bound = new WeakSet();
    function configure(options){Object.assign(deps, options || {});}

    function isCanvasImageDrag(event){
        return (deps.dataTypes(event?.dataTransfer) || []).includes('application/x-smart-canvas-image');
    }

    function accepts(event){
        return isCanvasImageDrag(event) || deps.hasImageData(event?.dataTransfer);
    }

    function setDragOver(active){
        const dropZone = deps.getDropZone?.();
        const panel = deps.getPanel?.();
        if(!dropZone || !panel) return;
        dropZone.classList.toggle('drag-over', !!active);
        panel.classList.toggle('drag-over', !!active);
    }

    function handleDragOver(event){
        if(!accepts(event)) return;
        event.preventDefault();
        event.stopPropagation();
        if(event.dataTransfer) event.dataTransfer.dropEffect = 'copy';
        setDragOver(true);
    }

    function handleDropZoneDragOver(event){
        if(!accepts(event)) return;
        event.preventDefault();
        event.stopPropagation();
        deps.getDropZone?.()?.classList.add('drag-over');
    }

    async function handleDrop(event){
        if(!accepts(event)) return;
        event.preventDefault();
        event.stopPropagation();
        setDragOver(false);
        let raw = '';
        try { raw = event.dataTransfer?.getData?.('application/x-smart-canvas-image') || ''; } catch(_) {}
        if(raw){
            try {
                const payload = JSON.parse(raw);
                if(payload?.url) await deps.addUrlToAssetLibrary(payload.url, payload.name || '');
                return;
            } catch(_) {
                deps.toast(deps.assetAddFailMessage());
                return;
            }
        }
        try {
            const payload = await deps.resolvePayload(event.dataTransfer);
            if(payload.type === 'files'){
                const uploaded = await deps.uploadFiles(payload.files);
                for(const file of uploaded) if(file?.url) await deps.addUrlToAssetLibrary(file.url, file.name || '');
            } else if(payload.type === 'url'){
                await deps.addUrlToAssetLibrary(payload.url, deps.imageNameFromUrl(payload.url));
            }
        } catch(error) {
            deps.toast(error.message || deps.assetAddFailMessage());
        }
    }

    function bind(){
        const dropZone = deps.getDropZone?.();
        const panel = deps.getPanel?.();
        if(dropZone && !bound.has(dropZone)){
            bound.add(dropZone);
            dropZone.addEventListener('dragover', handleDropZoneDragOver);
            dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
            dropZone.addEventListener('drop', handleDrop);
        }
        if(panel && !bound.has(panel)){
            bound.add(panel);
            panel.addEventListener('dragover', handleDragOver);
            panel.addEventListener('dragleave', event => {
                if(!panel.contains(event.relatedTarget)) setDragOver(false);
            });
            panel.addEventListener('drop', handleDrop);
        }
    }

    global.CanvasAssetPanelDropController = {configure, bind, setDragOver, handleDragOver, handleDropZoneDragOver, handleDrop};
})(typeof window !== 'undefined' ? window : globalThis);

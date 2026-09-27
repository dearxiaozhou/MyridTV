/* Routes preview wheel input to video stepping, panorama zoom, or image transform. */
(function(global){
    'use strict';

    const state={listenersBound:false};
    const deps={
        isModalOpen:() => false,
        getMode:() => '',
        getElementById:id => global.document.getElementById(id),
        getPreviewStage:() => global.document.getElementById('previewStage'),
        getImageStage:() => global.document.getElementById('imageEditStage'),
        getFrame:() => global.document.getElementById('previewFrame'),
        isPanoramaEnabled:() => false,
        getPanoramaState:() => ({fov:75}),
        seekVideoFrames:() => false,
        lockRootScroll:() => {},
        updateZoomLabel:() => {},
        zoomAt:() => {}
    };

    function configure(options){Object.assign(deps,options || {});}
    function getState(){return state;}

    function handleWheel(event){
        if(event.__imagePreviewWheelHandled) return true;
        if(!deps.isModalOpen() || deps.getMode()!=='preview') return false;
        if(event.target?.closest?.('button, input, textarea, select, .preview-tools-overlay, .preview-download-overlay, .preview-nav-btn')) return false;
        const previewStage=deps.getPreviewStage();
        const imageStage=deps.getImageStage();
        const path=typeof event.composedPath==='function' ? event.composedPath() : [];
        const insidePreview=event.target?.closest?.('#previewStage, #previewFrame, #previewCurrentImage, #previewCurrentVideo, #panoramaStage, #panoramaCanvas');
        if(!insidePreview && !path.includes(previewStage) && event.currentTarget!==imageStage) return false;

        event.__imagePreviewWheelHandled=true;
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation?.();
        deps.lockRootScroll();
        if(deps.seekVideoFrames(event.deltaY>0 ? 1 : -1)) return true;
        if(deps.isPanoramaEnabled()){
            const panorama=deps.getPanoramaState();
            const factor=event.deltaY<0 ? 0.92 : 1/0.92;
            panorama.fov=Math.max(35,Math.min(100,panorama.fov*factor));
            deps.updateZoomLabel();
            return true;
        }
        const factor=event.deltaY<0 ? 1.12 : 1/1.12;
        const frame=deps.getFrame();
        const rect=frame?.getBoundingClientRect() || previewStage?.getBoundingClientRect();
        deps.zoomAt(event.clientX,event.clientY,rect,factor);
        return true;
    }

    function bindWheelListeners(ids){
        if(state.listenersBound) return false;
        for(const id of ids || []) deps.getElementById(id)?.addEventListener('wheel',handleWheel,{passive:false,capture:true});
        state.listenersBound=true;
        return true;
    }

    global.CanvasImagePreviewInteractionController={configure,getState,handleWheel,bindWheelListeners};
})(typeof window!=='undefined' ? window : globalThis);

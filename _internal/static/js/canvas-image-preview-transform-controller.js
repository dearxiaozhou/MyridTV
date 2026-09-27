/* Owns preview zoom and pan state plus the image-frame transform. */
(function(global){
    'use strict';

    const state={zoom:1,pan:{x:0,y:0}};
    const deps={
        getFrame:() => global.document.getElementById('previewFrame'),
        isPanoramaEnabled:() => false,
        updateZoomLabel:() => {}
    };

    function configure(options){Object.assign(deps,options || {});}
    function getState(){return state;}
    function apply(){
        const frame=deps.getFrame();
        if(frame) frame.style.transform=deps.isPanoramaEnabled() ? '' : `translate(${state.pan.x}px, ${state.pan.y}px) scale(${state.zoom})`;
        deps.updateZoomLabel();
        return {zoom:state.zoom,pan:{...state.pan}};
    }
    function setPan(value){
        const x=Number(value?.x), y=Number(value?.y);
        state.pan={x:Number.isFinite(x)?x:0,y:Number.isFinite(y)?y:0};
        return apply();
    }
    function reset(){state.zoom=1; state.pan={x:0,y:0}; return apply();}
    function zoomAt(clientX,clientY,rect,factor){
        const oldZoom=state.zoom;
        const multiplier=Number(factor);
        if(!Number.isFinite(multiplier) || multiplier<=0) return apply();
        state.zoom=Math.max(0.05,Math.min(12,state.zoom*multiplier));
        if(rect && oldZoom>0){
            const originX=clientX-rect.left-rect.width/2;
            const originY=clientY-rect.top-rect.height/2;
            const ratio=state.zoom/oldZoom;
            state.pan.x-=originX*(ratio-1);
            state.pan.y-=originY*(ratio-1);
        }
        return apply();
    }

    global.CanvasImagePreviewTransformController={configure,getState,apply,setPan,reset,zoomAt};
})(typeof window !== 'undefined' ? window : globalThis);

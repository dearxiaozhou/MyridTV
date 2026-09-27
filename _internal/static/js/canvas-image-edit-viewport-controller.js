/* Owns crop/workspace zoom, overflow layout, and crop/outpaint overlays. */
(function(global){
    'use strict';

    const state={zoom:1,baseW:0,baseH:0};
    const deps={
        getImage:() => global.document.getElementById('cropImage'),
        getDrawCanvas:() => global.document.getElementById('editDrawCanvas'),
        getTextCanvas:() => global.document.getElementById('editTextCanvas'),
        getStage:() => global.document.getElementById('imageEditStage'),
        getCropCanvas:() => global.document.getElementById('cropCanvas'),
        getCropBox:() => global.document.getElementById('cropBox'),
        getOutpaintFrame:() => global.document.getElementById('outpaintFrame'),
        getOutpaintResolution:() => global.document.getElementById('outpaintResolution'),
        getZoomLabel:() => global.document.getElementById('imageEditZoomLabel'),
        getMode:() => 'crop',
        getCropState:() => null,
        getWindowSize:() => ({width:global.innerWidth,height:global.innerHeight}),
        getPreviewZoom:() => 1,
        getPanorama:() => ({enabled:false,fov:75}),
        resizeDrawCanvas:() => {},
        clampCrop:() => {},
        refreshGridSplitPreview:() => {},
        exceedsFourKStandard:(width,height) => width>4096 || height>4096,
        resetPanoramaView:() => {},
        resetPreviewTransform:() => {}
    };

    function configure(options){Object.assign(deps,options || {});}
    function getState(){return state;}
    function getZoom(){return state.zoom;}
    function setZoom(value){state.zoom=Number(value) || 1; return state.zoom;}
    function setBaseSize(width,height){state.baseW=Number(width) || 0; state.baseH=Number(height) || 0;}
    function reset(){state.zoom=1; state.baseW=0; state.baseH=0;}

    function ensureBaseSize(force=false){
        if(state.baseW && state.baseH && !force) return;
        const image=deps.getImage();
        const naturalW=image?.naturalWidth || image?.clientWidth || 0;
        const naturalH=image?.naturalHeight || image?.clientHeight || 0;
        if(!naturalW || !naturalH) return;
        const viewport=deps.getWindowSize();
        const maxW=Math.max(1,Math.min(1300,viewport.width-100));
        const maxH=Math.max(1,Math.min(840,viewport.height-200));
        const fit=Math.min(1,maxW/naturalW,maxH/naturalH);
        state.baseW=Math.max(1,Math.round(naturalW*fit));
        state.baseH=Math.max(1,Math.round(naturalH*fit));
    }

    function displaySize(){
        const image=deps.getImage();
        const clientW=Number(image?.clientWidth || 0), clientH=Number(image?.clientHeight || 0);
        if(clientW>2 && clientH>2) return {w:clientW,h:clientH};
        ensureBaseSize();
        return {w:Math.max(1,Math.round((state.baseW || Number(image?.naturalWidth || 0) || 1)*state.zoom)),
            h:Math.max(1,Math.round((state.baseH || Number(image?.naturalHeight || 0) || 1)*state.zoom))};
    }

    function syncOverflow(){
        const stage=deps.getStage(), crop=deps.getCropCanvas();
        if(!stage || !crop) return;
        const rect=crop.getBoundingClientRect(), pad=36;
        stage.classList.toggle('overflow-x',rect.width+pad>stage.clientWidth);
        stage.classList.toggle('overflow-y',rect.height+pad>stage.clientHeight);
    }

    function outpaintNaturalSize(){
        const image=deps.getImage(), crop=deps.getCropState();
        if(!image || !crop) return {w:1,h:1};
        const display=displaySize();
        const scaleX=Math.max(1,Number(image.naturalWidth || 1))/Math.max(1,Number(display.w || image.clientWidth || 1));
        const scaleY=Math.max(1,Number(image.naturalHeight || 1))/Math.max(1,Number(display.h || image.clientHeight || 1));
        return {w:Math.max(1,Math.round((crop.w || 1)*scaleX)),h:Math.max(1,Math.round((crop.h || 1)*scaleY))};
    }

    function updateOutpaintResolutionLabel(){
        const label=deps.getOutpaintResolution(), crop=deps.getCropState();
        if(!label || !crop) return;
        const size=outpaintNaturalSize();
        deps.getCropCanvas()?.classList.toggle('outpaint-warning',deps.exceedsFourKStandard(size.w,size.h));
        label.textContent=`${Math.round(size.w)} x ${Math.round(size.h)}`;
    }

    function renderCropBox(){
        const crop=deps.getCropState();
        if(!crop) return;
        const cropCanvas=deps.getCropCanvas(), image=deps.getImage();
        const draw=deps.getDrawCanvas(), textCanvas=deps.getTextCanvas();
        let boxX=crop.x, boxY=crop.y;
        if(deps.getMode()==='outpaint' && cropCanvas && image){
            cropCanvas.style.width=`${Math.round(crop.w)}px`;
            cropCanvas.style.height=`${Math.round(crop.h)}px`;
            image.style.position='absolute'; image.style.left=`${Math.round(crop.x)}px`; image.style.top=`${Math.round(crop.y)}px`;
            boxX=0; boxY=0;
            if(draw){draw.style.left=image.style.left;draw.style.top=image.style.top;}
            if(textCanvas){textCanvas.style.left=image.style.left;textCanvas.style.top=image.style.top;}
            updateOutpaintResolutionLabel();
        } else if(cropCanvas && image){
            cropCanvas.style.width=''; cropCanvas.style.height=''; image.style.position=''; image.style.left=''; image.style.top='';
            if(draw){draw.style.left='';draw.style.top='';}
            if(textCanvas){textCanvas.style.left='';textCanvas.style.top='';}
        }
        const box=deps.getCropBox();
        if(box){box.style.left=`${boxX}px`;box.style.top=`${boxY}px`;box.style.width=`${crop.w}px`;box.style.height=`${crop.h}px`;}
        const frame=deps.getOutpaintFrame();
        if(frame){
            frame.style.left=deps.getMode()==='outpaint'?'0px':`${boxX}px`;
            frame.style.top=deps.getMode()==='outpaint'?'0px':`${boxY}px`;
            frame.style.width=`${crop.w}px`;frame.style.height=`${crop.h}px`;
        }
    }

    function applyZoom(scaleOverride=null){
        ensureBaseSize();
        if(!state.baseW) return;
        const image=deps.getImage(), oldW=displaySize().w;
        image.style.maxWidth='none'; image.style.maxHeight='none';
        image.style.width=`${Math.round(state.baseW*state.zoom)}px`;
        image.style.height=`${Math.round(state.baseH*state.zoom)}px`;
        deps.resizeDrawCanvas();
        const crop=deps.getCropState();
        if(crop){
            const scale=Number(scaleOverride) || (oldW>0 ? displaySize().w/oldW : 1);
            crop.x=Math.round(crop.x*scale);crop.y=Math.round(crop.y*scale);
            crop.w=Math.round(crop.w*scale);crop.h=Math.round(crop.h*scale);
            deps.clampCrop();renderCropBox();
        }
        if(deps.getMode()==='grid') deps.refreshGridSplitPreview();
        syncOverflow(); updateZoomLabel();
    }

    function resetZoom(){
        const mode=deps.getMode(), panorama=deps.getPanorama();
        if(mode==='preview'){
            if(panorama.enabled){deps.resetPanoramaView();return;}
            deps.resetPreviewTransform();return;
        }
        const stage=deps.getStage(); state.zoom=1; applyZoom();
        if(stage){stage.scrollLeft=0;stage.scrollTop=0;}
    }

    function updateZoomLabel(){
        const label=deps.getZoomLabel();
        if(!label) return;
        const mode=deps.getMode(), panorama=deps.getPanorama();
        if(mode==='preview' && panorama.enabled){label.textContent=`${Math.round((75/Math.max(1,panorama.fov))*100)}%`;return;}
        label.textContent=`${Math.round((mode==='preview'?deps.getPreviewZoom():state.zoom)*100)}%`;
    }

    global.CanvasImageEditViewportController={configure,getState,getZoom,setZoom,setBaseSize,reset,ensureBaseSize,
        displaySize,bounds:displaySize,syncOverflow,outpaintNaturalSize,updateOutpaintResolutionLabel,renderCropBox,applyZoom,resetZoom,updateZoomLabel};
})(typeof window!=='undefined'?window:globalThis);

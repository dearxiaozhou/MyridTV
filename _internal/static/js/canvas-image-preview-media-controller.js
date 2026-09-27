/* Owns preview metadata and video-frame navigation mechanics. */
(function(global){
    'use strict';

    const state={extraHint:''};
    const deps={
        getEditing:() => ({image:null,node:null}),
        isModalOpen:() => false,
        getCurrentImage:() => global.document.getElementById('previewCurrentImage'),
        getCurrentVideo:() => global.document.getElementById('previewCurrentVideo'),
        getCropImage:() => global.document.getElementById('cropImage'),
        getMetaHint:() => global.document.getElementById('previewMetaHint'),
        getPanoramaToggle:() => global.document.getElementById('panoramaToggleBtn'),
        isPanoramaEnabled:() => false,
        getLoadToken:() => 0,
        getCompareController:() => global.CanvasImagePreviewCompareController,
        displayMediaUrl:item => item?.url || item || '',
        proxiedMediaUrl:item => item?.url || item || '',
        syncFrameSize:() => {},
        requestAnimationFrame:callback => global.requestAnimationFrame(callback),
        mediaKindForItem:item => item?.kind || 'image',
        translate:key => key,
        scheduleSave:() => {},
        setTimeout:(callback,delay) => global.setTimeout(callback,delay),
        clearTimeout:id => global.clearTimeout(id)
    };

    function configure(options){Object.assign(deps,options || {});}
    function getState(){return state;}

    function resolutionText(){
        const editing=deps.getEditing() || {};
        const image=editing.image || {};
        const currentImage=deps.getCurrentImage();
        const currentVideo=deps.getCurrentVideo();
        const cropImage=deps.getCropImage();
        const width=Number(image.natural_w || image.width || image.w || 0)
            || Number(currentVideo?.videoWidth || 0)
            || Number(currentImage?.naturalWidth || 0)
            || Number(cropImage?.naturalWidth || 0);
        const height=Number(image.natural_h || image.height || image.h || 0)
            || Number(currentVideo?.videoHeight || 0)
            || Number(currentImage?.naturalHeight || 0)
            || Number(cropImage?.naturalHeight || 0);
        if(!width || !height) return '';
        return `${deps.translate('smart.resolution')}: ${Math.round(width)} x ${Math.round(height)}`;
    }

    function updateMetaHint(extraHint){
        if(arguments.length===0) extraHint=state.extraHint;
        state.extraHint=extraHint || '';
        const hint=deps.getMetaHint();
        if(!hint) return;
        hint.textContent=[resolutionText(),state.extraHint].filter(Boolean).join(' · ');
    }

    function rememberResolution(){
        const image=deps.getEditing()?.image;
        if(!image) return false;
        const currentImage=deps.getCurrentImage();
        const currentVideo=deps.getCurrentVideo();
        const cropImage=deps.getCropImage();
        const width=Number(currentVideo?.videoWidth || 0)
            || Number(currentImage?.naturalWidth || 0)
            || Number(cropImage?.naturalWidth || 0);
        const height=Number(currentVideo?.videoHeight || 0)
            || Number(currentImage?.naturalHeight || 0)
            || Number(cropImage?.naturalHeight || 0);
        if(width>0 && height>0 && (!image.natural_w || !image.natural_h)){
            image.natural_w=width;
            image.natural_h=height;
            deps.scheduleSave();
            return true;
        }
        return false;
    }

    function refreshCurrentMedia(){
        const currentImage=deps.getCurrentImage();
        const currentVideo=deps.getCurrentVideo();
        const panoramaToggle=deps.getPanoramaToggle();
        const editing=deps.getEditing() || {};
        const image=editing.image || {};
        const loadToken=deps.getLoadToken();
        const currentUrl=image.url || '';
        const isVideo=deps.mediaKindForItem(image)==='video';
        const compare=deps.getCompareController();

        if(panoramaToggle){
            panoramaToggle.style.display=isVideo ? 'none' : 'inline-flex';
            panoramaToggle.classList.toggle('active',Boolean(deps.isPanoramaEnabled()));
        }
        if(deps.isPanoramaEnabled() && !isVideo){
            currentImage.onload=null;
            currentImage.onerror=null;
            currentImage.style.display='none';
            compare?.refresh('panorama');
            return;
        }

        const onCurrentLoaded=()=>{
            if(loadToken!==deps.getLoadToken()) return;
            rememberResolution();
            deps.syncFrameSize();
            updateMetaHint();
        };
        if(isVideo){
            currentImage.onload=null;
            currentImage.onerror=null;
            currentImage.removeAttribute('src');
            currentImage.style.display='none';
            if(currentVideo){
                const previewSrc=deps.displayMediaUrl(image || currentUrl);
                currentVideo.style.display='block';
                currentVideo.onloadedmetadata=onCurrentLoaded;
                currentVideo.onloadeddata=onCurrentLoaded;
                if(currentVideo.getAttribute('src')!==previewSrc){
                    currentVideo.src=previewSrc;
                    currentVideo.load?.();
                }
                if(currentVideo.readyState>=1) deps.requestAnimationFrame(onCurrentLoaded);
            }
            compare?.refresh('video');
            if(panoramaToggle) panoramaToggle.style.display='none';
            return;
        }

        if(currentVideo){
            currentVideo.pause?.();
            currentVideo.onloadedmetadata=null;
            currentVideo.onloadeddata=null;
            currentVideo.removeAttribute('src');
            currentVideo.load?.();
            currentVideo.style.display='none';
        }
        currentImage.style.display='block';
        currentImage.onload=onCurrentLoaded;
        currentImage.onerror=()=>{
            if(loadToken!==deps.getLoadToken() || currentImage.dataset.proxyFallbackTried==='1') return;
            const fallback=deps.proxiedMediaUrl(image || currentUrl);
            if(!fallback || fallback===currentImage.getAttribute('src')) return;
            currentImage.dataset.proxyFallbackTried='1';
            currentImage.src=fallback;
        };
        const previewSrc=deps.displayMediaUrl(image || currentUrl);
        if(currentImage.getAttribute('src')!==previewSrc){
            currentImage.dataset.proxyFallbackTried='';
            currentImage.src=previewSrc;
        }
        if(currentImage.complete && currentImage.naturalWidth) deps.requestAnimationFrame(onCurrentLoaded);
        compare?.refresh('image');
    }

    function currentVideo(){
        if(!deps.isModalOpen()) return null;
        if(deps.mediaKindForItem(deps.getEditing()?.image || {})!=='video') return null;
        return deps.getCurrentVideo();
    }

    function frameStep(){
        const image=deps.getEditing()?.image || {};
        const fps=Number(image.fps || image.frameRate || image.frame_rate || image.framespersecond || image.frames_per_second || 0);
        return 1/Math.max(1,Math.min(120,Number.isFinite(fps) && fps>0 ? fps : 30));
    }

    function seekFrames(direction){
        const video=currentVideo();
        if(!video || video.readyState<1) return false;
        video.pause?.();
        const step=frameStep();
        const duration=Number.isFinite(video.duration) && video.duration>0 ? video.duration : 0;
        const maxTime=duration ? Math.max(0,duration-step/2) : Number.MAX_SAFE_INTEGER;
        video.currentTime=Math.max(0,Math.min(maxTime,Number(video.currentTime || 0)+direction*step));
        return true;
    }

    function waitForEvent(video,eventName,timeout=1500){
        return new Promise(resolve=>{
            let done=false;
            const finish=()=>{
                if(done) return;
                done=true;
                deps.clearTimeout(timer);
                video.removeEventListener(eventName,finish);
                resolve();
            };
            const timer=deps.setTimeout(finish,timeout);
            video.addEventListener(eventName,finish,{once:true});
        });
    }

    async function seekForFrame(video,time){
        if(Math.abs(Number(video.currentTime || 0)-time)<=0.002) return false;
        video.currentTime=time;
        await waitForEvent(video,'seeked',2200);
        return true;
    }

    global.CanvasImagePreviewMediaController={configure,getState,resolutionText,updateMetaHint,rememberResolution,refreshCurrentMedia,currentVideo,frameStep,seekFrames,waitForEvent,seekForFrame};
})(typeof window !== 'undefined' ? window : globalThis);

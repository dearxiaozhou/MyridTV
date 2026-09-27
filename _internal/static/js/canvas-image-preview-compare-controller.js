/* Owns the image preview comparison panel and its source selection state. */
(function(global){
    'use strict';

    const state = {active:false,index:-1};
    const deps = {
        getEditing:() => ({node:null,image:null}),
        getNodes:() => [],
        getInputImages:() => [],
        mediaKindForItem:item => item?.kind || 'image',
        getStage:() => global.document.getElementById('previewStage'),
        getCompareImage:() => global.document.getElementById('previewCompareImage'),
        getCompareLayer:() => global.document.getElementById('previewCompareLayer'),
        getCompareHandle:() => global.document.getElementById('previewCompareHandle'),
        getThumbs:() => global.document.getElementById('compareThumbs'),
        getToggle:() => global.document.getElementById('compareToggleBtn'),
        syncFrameSize:() => {},
        updateMetaHint:() => {},
        translate:key => key,
        escapeHtml:value => String(value),
        toast:() => {}
    };

    function configure(options){Object.assign(deps,options || {});}
    function getState(){return state;}
    function setActive(value){state.active=Boolean(value);}
    function setIndex(value){state.index=Number.isFinite(Number(value)) ? Number(value) : -1;}
    function reset(){state.active=false; state.index=-1;}

    function sources(){
        const editing = deps.getEditing() || {};
        const node = editing.node;
        if(!node) return [];
        const savedRefs = Array.isArray(node.runInputRefs) ? node.runInputRefs.filter(ref => ref?.url) : [];
        const upstream = savedRefs.length ? savedRefs : deps.getInputImages(node);
        const dedup = [];
        const seen = new Set();
        for(const image of upstream || []){
            if(!image?.url || seen.has(image.url) || deps.mediaKindForItem(image) !== 'image') continue;
            seen.add(image.url);
            dedup.push(image);
        }
        if(dedup.length) return dedup;
        if(node.sourceNodeId){
            const source = deps.getNodes().find(item => item.id === node.sourceNodeId);
            for(const image of source?.images || []){
                if(!image?.url || seen.has(image.url) || deps.mediaKindForItem(image) !== 'image') continue;
                seen.add(image.url);
                dedup.push(image);
            }
        }
        return dedup;
    }

    function hidePanel(){
        deps.getStage()?.classList.remove('compare-on');
        const layer=deps.getCompareLayer();
        const handle=deps.getCompareHandle();
        const thumbs=deps.getThumbs();
        if(layer) layer.style.display='none';
        if(handle) handle.style.display='none';
        if(thumbs){thumbs.style.display='none'; thumbs.innerHTML='';}
    }

    function refresh(mode='image'){
        const editing=deps.getEditing() || {};
        const stage=deps.getStage();
        const compareImage=deps.getCompareImage();
        const compareLayer=deps.getCompareLayer();
        const compareHandle=deps.getCompareHandle();
        const thumbs=deps.getThumbs();
        const toggle=deps.getToggle();
        const prompt=editing.node?.runPrompt ? `${deps.translate('smart.runPromptPrefix')}${editing.node.runPrompt.slice(0,60)}` : '';

        if(mode === 'panorama'){
            state.active=false;
            hidePanel();
            toggle?.classList.remove('active');
            deps.updateMetaHint(deps.translate('smart.panoramaHint'));
            return false;
        }
        if(mode === 'video'){
            reset();
            hidePanel();
            if(toggle){toggle.disabled=true; toggle.style.opacity='.45'; toggle.classList.remove('active'); toggle.title=deps.translate('smart.compareEmpty');}
            deps.updateMetaHint(prompt);
            return false;
        }

        const items=sources();
        if(!items.length){
            reset();
            hidePanel();
            if(toggle){toggle.disabled=true; toggle.style.opacity='.45'; toggle.title=deps.translate('smart.compareEmpty'); toggle.classList.remove('active');}
            deps.updateMetaHint(prompt);
            return false;
        }
        if(toggle){
            toggle.disabled=false;
            toggle.style.opacity='1';
            toggle.title=deps.translate('smart.compareHover');
            toggle.classList.toggle('active',state.active);
        }

        const sliderActive=state.active && state.index >= 0 && state.index < items.length;
        if(sliderActive){
            const source=items[state.index];
            compareImage.src=source?.url || '';
            compareImage.onload=deps.syncFrameSize;
            deps.syncFrameSize();
            stage.classList.add('compare-on');
            if(compareLayer) compareLayer.style.display='';
            if(compareHandle) compareHandle.style.display='';
        } else {
            stage.classList.remove('compare-on');
            if(compareLayer) compareLayer.style.display='none';
            if(compareHandle) compareHandle.style.display='none';
        }

        if(state.active){
            thumbs.style.display='inline-flex';
            thumbs.innerHTML=items.map((item,index)=>`<button type="button" class="compare-thumb ${index===state.index?'active':''}" data-compare-idx="${index}" title="${deps.escapeHtml(deps.translate(index===state.index?'smart.compareCancelTip':'smart.compareUseTip'))}"><img src="${deps.escapeHtml(item.url)}"></button>`).join('');
            thumbs.querySelectorAll('[data-compare-idx]').forEach(button=>{
                button.onclick=event=>{
                    event.preventDefault(); event.stopPropagation();
                    const index=Number(button.dataset.compareIdx);
                    state.index=state.index===index ? -1 : index;
                    refresh('image');
                };
            });
        } else {
            thumbs.style.display='none';
            thumbs.innerHTML='';
        }
        let hint=prompt;
        if(state.active && !sliderActive) hint=(hint ? `${hint} · ` : '')+deps.translate('smart.compareHintPick');
        deps.updateMetaHint(hint);
        return true;
    }

    function toggle(){
        const items=sources();
        if(!items.length){deps.toast(deps.translate('smart.compareNoSource')); return false;}
        state.active=!state.active;
        if(state.active && (state.index<0 || state.index>=items.length)) state.index=0;
        if(!state.active) state.index=-1;
        refresh('image');
        return true;
    }

    global.CanvasImagePreviewCompareController={configure,getState,setActive,setIndex,reset,sources,refresh,toggle};
})(typeof window !== 'undefined' ? window : globalThis);

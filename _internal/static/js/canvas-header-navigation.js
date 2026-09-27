/* Canvas header navigation: canvas list, rename, switch and create flows. */
(function(global){
    'use strict';

    var deps={getContext:null};
    var allCanvases=[];
    var dropdownOpen=false;
    var bound=false;
    function configure(opts){Object.assign(deps,opts||{});}
    function context(){return deps.getContext?deps.getContext():{};}
    function backToCanvasList(){
        const ctx=context();
        ctx.savePromptDraft();
        if(global.parent&&global.parent!==global){global.parent.postMessage({type:'open-page',page:'canvas',resetFrame:true},'*');return;}
        global.location.href='/static/canvas.html?v=2026.07.10.navfix1';
    }
    async function loadAllCanvases(){
        try{
            const response=await fetch('/api/canvases');
            if(!response.ok) return [];
            const data=await response.json();
            allCanvases=data.canvases||[];
            return allCanvases;
        }catch(error){console.error(error);return [];}
    }
    function toggleDropdown(event){
        event?.stopPropagation();
        if(dropdownOpen){closeDropdown();return;}
        openDropdown();
    }
    async function openDropdown(){
        const ctx=context();
        if(!ctx.canvasListDropdown) return;
        dropdownOpen=true;
        ctx.canvasTitleDropdown?.classList.add('open');
        ctx.canvasListDropdown.style.display='flex';
        if(ctx.canvasDropdownSearch) ctx.canvasDropdownSearch.value='';
        await loadAllCanvases();
        renderDropdownItems();
    }
    function closeDropdown(){
        const ctx=context();
        dropdownOpen=false;
        ctx.canvasTitleDropdown?.classList.remove('open');
        if(ctx.canvasListDropdown) ctx.canvasListDropdown.style.display='none';
    }
    function renderDropdownItems(){
        const ctx=context();
        if(!ctx.canvasListDropdownItems) return;
        const query=(ctx.canvasDropdownSearch?.value||'').trim().toLowerCase();
        let items=allCanvases.slice().sort((a,b)=>Number(b.updated_at||0)-Number(a.updated_at||0));
        if(query) items=items.filter(item=>(item.title||'').toLowerCase().includes(query));
        if(!items.length){ctx.canvasListDropdownItems.innerHTML=`<div class="canvas-dropdown-empty">${ctx.escapeHtml(ctx.tr('canvas.noCanvasCreateFirst'))}</div>`;return;}
        ctx.canvasListDropdownItems.innerHTML=items.map(item=>{
            const title=item.title||ctx.tr('canvas.untitled');
            const active=item.id===ctx.canvasId;
            const time=formatCanvasTimeShort(item.updated_at||item.created_at);
            const icon=renderDropdownCanvasIcon(item.icon,16);
            return `<button class="canvas-dropdown-item ${active?'active':''}" type="button" data-canvas-id="${ctx.escapeHtml(item.id)}" onclick="switchToCanvas('${ctx.escapeHtml(item.id)}')"><span class="canvas-dropdown-item-icon">${icon}</span><span class="canvas-dropdown-item-text">${ctx.escapeHtml(title)}</span><span class="canvas-dropdown-item-meta">${ctx.escapeHtml(time)}</span></button>`;
        }).join('');
        if(typeof ctx.refreshIcons==='function') ctx.refreshIcons();
        else if(global.lucide?.createIcons) global.lucide.createIcons({root:ctx.canvasListDropdownItems});
    }
    function renderDropdownCanvasIcon(icon,size=14){
        const escape=context().escapeHtml;
        if(!icon||icon==='🧩') return `<i data-lucide="layers" style="width:${size}px;height:${size}px"></i>`;
        if(/[^\x00-\x7F]/.test(icon)) return escape(icon);
        return `<i data-lucide="${escape(icon)}" style="width:${size}px;height:${size}px"></i>`;
    }
    function formatCanvasTimeShort(timestamp){
        if(!timestamp) return '';
        const date=new Date(Number(timestamp));
        const diffMinutes=Math.floor((new Date()-date)/60000);
        if(diffMinutes<1) return context().tr('smart.justNow')||'刚刚';
        if(diffMinutes<60) return diffMinutes+'m';
        const diffHours=Math.floor(diffMinutes/60);
        if(diffHours<24) return diffHours+'h';
        const diffDays=Math.floor(diffHours/24);
        if(diffDays<7) return diffDays+'d';
        return (date.getMonth()+1)+'/'+date.getDate();
    }
    function switchToCanvas(id){
        const ctx=context();
        if(!id||id===ctx.canvasId){closeDropdown();return;}
        const url=`/static/smart-canvas.html?id=${encodeURIComponent(id)}`;
        if(global.parent&&global.parent!==global){global.parent.postMessage({type:'open-page',page:'smart-canvas',url},'*');return;}
        global.location.href=url;
    }
    function startRename(event){
        event?.stopPropagation();
        const ctx=context();
        const canvas=ctx.getCanvas();
        if(!ctx.canvasTitleText||!ctx.canvasTitleInput||!canvas) return;
        closeDropdown();
        ctx.canvasTitleInput.value=canvas.title||'';
        ctx.canvasTitleInput.style.display='block';
        ctx.canvasTitleInput.focus();
        ctx.canvasTitleInput.select();
    }
    function finishRename(commit){
        const ctx=context();
        const canvas=ctx.getCanvas();
        if(!ctx.canvasTitleInput||!canvas) return;
        const title=ctx.canvasTitleInput.value.trim();
        ctx.canvasTitleInput.style.display='none';
        if(commit&&title&&title!==(canvas.title||'')) setCanvasTitle(ctx.canvasId,title);
    }
    async function setCanvasTitle(id,title){
        if(!id) return;
        const ctx=context();
        try{
            const response=await fetch(`/api/canvases/${encodeURIComponent(id)}`,{
                method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({title})
            });
            if(!response.ok) throw new Error('rename failed');
            const data=await response.json().catch(()=>({}));
            const canvas=ctx.getCanvas();
            if(canvas&&canvas.id===id) canvas.title=title;
            if(data.renamed) applyFolderRename(data.renamed.old_folder,data.renamed.new_folder);
            updateTitleDisplay();
            if(global.parent&&global.parent!==global) global.parent.postMessage({type:'canvas-current-id',id:ctx.canvasId,page:'smart-canvas'},'*');
            global.document.title=title||ctx.tr('canvas.smartCanvas');
            if(data.renamed) ctx.scheduleSave();
        }catch(error){ctx.toast(ctx.tr('canvas.renameFailed')||'重命名失败');console.error(error);}
    }
    function applyFolderRename(oldFolder,newFolder){
        if(!oldFolder||!newFolder||oldFolder===newFolder) return;
        const ctx=context();
        const escapeRegex=value=>value.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
        const oldQuery=encodeURIComponent(oldFolder);
        const newQuery=encodeURIComponent(newFolder);
        const pattern=new RegExp('/assets/output/'+escapeRegex(oldQuery)+'(?=/)','g');
        const fix=value=>typeof value==='string'?value.replace(pattern,'/assets/output/'+newQuery):value;
        const walk=value=>{
            if(typeof value==='string') return fix(value);
            if(Array.isArray(value)) return value.map(walk);
            if(value&&typeof value==='object'){for(const key in value) value[key]=walk(value[key]);return value;}
            return value;
        };
        const nodes=ctx.getNodes();
        const canvas=ctx.getCanvas();
        if(Array.isArray(nodes)) walk(nodes);
        if(canvas?.artifacts) walk(canvas.artifacts);
        if(canvas?.cover) canvas.cover=fix(canvas.cover);
    }
    function handleCanvasRenamedMessage(data){
        if(!data||data.id!==context().canvasId) return;
        if(data.renamed) applyFolderRename(data.renamed.old_folder,data.renamed.new_folder);
        context().scheduleSave();
    }
    function updateTitleDisplay(){
        const ctx=context();
        const title=ctx.getCanvas()?.title||ctx.tr('canvas.smartCanvas');
        if(ctx.canvasTitleText) ctx.canvasTitleText.textContent=title;
        const oldTitle=global.document.getElementById('smartTitle');
        if(oldTitle) oldTitle.textContent=title;
    }
    async function createNewCanvas(){
        const ctx=context();
        try{
            const response=await fetch('/api/canvases',{
                method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:ctx.tr('canvas.untitled')||'未命名画布'})
            });
            if(!response.ok) throw new Error('create failed');
            const data=await response.json();
            if(data.canvas?.id) switchToCanvas(data.canvas.id);
        }catch(error){ctx.toast(ctx.tr('smart.createFailed')||'创建失败');console.error(error);}
    }
    function bindEvents(){
        if(bound) return;
        const ctx=context();
        global.document.addEventListener('click',event=>{
            const back=event.target.closest('.canvas-back-btn');
            if(back){event.preventDefault();backToCanvasList();}
        },true);
        const bar=global.document.querySelector('.canvas-header-bar');
        if(bar){
            const stopPan=event=>event.stopPropagation();
            bar.addEventListener('mousedown',stopPan);
            bar.addEventListener('touchstart',stopPan,{passive:true});
            bar.addEventListener('wheel',stopPan,{passive:true});
        }
        global.document.addEventListener('click',event=>{
            if(!dropdownOpen) return;
            const wrap=global.document.querySelector('.canvas-title-wrap');
            if(wrap&&!wrap.contains(event.target)) closeDropdown();
        });
        ctx.canvasDropdownSearch?.addEventListener('input',renderDropdownItems);
        if(ctx.canvasTitleInput){
            ctx.canvasTitleInput.addEventListener('click',event=>event.stopPropagation());
            ctx.canvasTitleInput.addEventListener('keydown',event=>{
                event.stopPropagation();
                if(event.key==='Enter'){event.preventDefault();finishRename(true);}
                if(event.key==='Escape'){event.preventDefault();finishRename(false);}
            });
            ctx.canvasTitleInput.addEventListener('blur',()=>finishRename(true));
        }
        if(ctx.canvasTitleDropdown) ctx.canvasTitleDropdown.addEventListener('click',function(event){
            event.stopPropagation();
            const text=this.querySelector('.canvas-title-text');
            const caret=this.querySelector('.canvas-title-caret');
            if(text&&text.contains(event.target)) startRename(event);
            else if((caret&&caret.contains(event.target))||event.target===this) toggleDropdown(event);
            else toggleDropdown(event);
        });
        if(ctx.canvasTitleText){ctx.canvasTitleText.title=ctx.tr('smart.clickToRename')||'点击重命名';ctx.canvasTitleText.style.cursor='text';}
        bound=true;
    }

    global.CanvasHeaderNavigation={
        configure,bindEvents,backToCanvasList,loadAllCanvases,toggleDropdown,openDropdown,closeDropdown,
        renderDropdownItems,renderDropdownCanvasIcon,formatCanvasTimeShort,switchToCanvas,startRename,
        finishRename,setCanvasTitle,applyFolderRename,handleCanvasRenamedMessage,updateTitleDisplay,createNewCanvas
    };
})(typeof window!=='undefined'?window:globalThis);

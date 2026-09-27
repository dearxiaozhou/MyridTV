/* Legacy prompt-preset panel controller, backed by the shared template model. */
(function(global){
    'use strict';

    var deps={getContext:null};
    var deleteArmed=false;
    var bound=false;
    function configure(opts){Object.assign(deps,opts||{});}
    function context(){return deps.getContext?deps.getContext():{};}
    function panelNode(){
        const ctx=context();
        return ctx.nodes().find(node=>node.id===ctx.promptPresetPanel?.dataset.nodeId)||null;
    }
    function setStatus(text='',tone=''){
        const status=context().promptPresetStatus;
        if(!status) return;
        status.textContent=text;
        status.classList.toggle('warn',tone==='warn');
        status.classList.toggle('ok',tone==='ok');
    }
    function resetDeleteState(){
        deleteArmed=false;
        const ctx=context();
        if(ctx.promptPresetDelete){
            ctx.promptPresetDelete.textContent=ctx.tr('common.delete');
            ctx.promptPresetDelete.classList.remove('confirm-danger');
        }
    }
    function renderPanel(selectedId='',message=''){
        const ctx=context();
        const select=ctx.promptPresetSelect;
        if(!select) return;
        resetDeleteState();
        const presets=ctx.promptPresets();
        select.innerHTML=presets.length
            ?presets.map(preset=>`<option value="${ctx.escapeHtml(preset.id)}" ${preset.id===selectedId?'selected':''}>${ctx.escapeHtml(preset.name||ctx.tr('smart.promptPresetUnnamed'))}</option>`).join('')
            :`<option value="">${ctx.escapeHtml(ctx.tr('smart.promptPresetNone'))}</option>`;
        const preset=ctx.currentPromptPreset(selectedId)||presets[0]||null;
        if(preset&&select.value!==preset.id) select.value=preset.id;
        ctx.promptPresetName.value=preset?.name||'';
        ctx.promptPresetText.value=preset?.text||'';
        const hasPreset=Boolean(preset);
        const nodeHasText=Boolean(String(panelNode()?.text||'').trim());
        ctx.promptPresetApply.disabled=!hasPreset;
        ctx.promptPresetDelete.disabled=!hasPreset;
        ctx.promptPresetSave.disabled=!hasPreset;
        if(ctx.promptPresetNew) ctx.promptPresetNew.disabled=!nodeHasText;
        setStatus(message||(hasPreset?ctx.tr('smart.promptPresetPanelHint'):ctx.tr('smart.promptPresetPanelEmpty')));
    }
    function openPanel(nodeId='',presetId='',options={}){
        const ctx=context();
        const panel=ctx.promptPresetPanel;
        if(!panel) return;
        panel.dataset.nodeId=nodeId||'';
        const node=ctx.nodes().find(item=>item.id===nodeId);
        const preferred=presetId||node?.promptPresetId||ctx.promptPresets()[0]?.id||'';
        renderPanel(preferred,options.status||'');
        if(options.tone) setStatus(options.status||'',options.tone);
        const nodeElement=nodeId?ctx.world.querySelector(`.image-node[data-id="${global.CSS.escape(nodeId)}"]`):null;
        const rect=nodeElement?.getBoundingClientRect();
        const shellRect=ctx.shell.getBoundingClientRect();
        const maxLeft=Math.max(18,shellRect.width-410);
        const maxTop=Math.max(18,shellRect.height-330);
        const left=rect?Math.min(maxLeft,Math.max(18,rect.right-shellRect.left+12)):80;
        const top=rect?Math.min(maxTop,Math.max(18,rect.top-shellRect.top)):80;
        panel.style.left=`${left}px`;
        panel.style.top=`${top}px`;
        panel.classList.add('open');
        ctx.refreshIcons();
    }
    function closePanel(){
        context().promptPresetPanel?.classList.remove('open');
        resetDeleteState();
    }
    function bindEvents(){
        if(bound) return;
        const ctx=context();
        const panel=ctx.promptPresetPanel;
        panel?.addEventListener('pointerdown',event=>event.stopPropagation());
        panel?.addEventListener('mousedown',event=>event.stopPropagation());
        panel?.addEventListener('click',event=>event.stopPropagation());
        if(ctx.promptPresetClose) ctx.promptPresetClose.onclick=closePanel;
        if(ctx.promptPresetSelect) ctx.promptPresetSelect.onchange=()=>renderPanel(ctx.promptPresetSelect.value);
        [ctx.promptPresetName,ctx.promptPresetText].forEach(input=>input?.addEventListener('input',()=>{
            resetDeleteState();
            setStatus(ctx.tr('smart.promptPresetEditing'));
        }));
        if(ctx.promptPresetApply) ctx.promptPresetApply.onclick=()=>{
            const preset=ctx.currentPromptPreset(ctx.promptPresetSelect.value);
            const node=panelNode();
            if(!preset||!node) return;
            node.promptPresetId=preset.id;
            node.text=preset.text||'';
            closePanel();
            ctx.render();
            ctx.scheduleSave();
        };
        if(ctx.promptPresetSave) ctx.promptPresetSave.onclick=()=>{
            const preset=ctx.currentPromptPreset(ctx.promptPresetSelect.value);
            if(!preset) return;
            const name=ctx.promptPresetName.value.trim();
            const text=ctx.promptPresetText.value.trim();
            if(!name||!text){setStatus(ctx.tr('smart.promptPresetRequired'),'warn');return;}
            ctx.updatePreset(preset.id,{name,text,updatedAt:Date.now()});
            const node=panelNode();
            if(node?.promptPresetId===preset.id) node.text=text;
            renderPanel(preset.id,ctx.tr('smart.promptPresetSaved'));
            setStatus(ctx.tr('smart.promptPresetSaved'),'ok');
            ctx.render();
            ctx.scheduleSave();
        };
        if(ctx.promptPresetNew) ctx.promptPresetNew.onclick=()=>{
            const preset=ctx.createPresetFromNode(panelNode(),{openPanel:false});
            if(!preset) return;
            renderPanel(preset.id,ctx.tr('smart.promptPresetSavedNew'));
            setStatus(ctx.tr('smart.promptPresetSavedNew'),'ok');
            ctx.promptPresetName?.focus();
            ctx.promptPresetName?.select();
        };
        if(ctx.promptPresetDelete) ctx.promptPresetDelete.onclick=()=>{
            const preset=ctx.currentPromptPreset(ctx.promptPresetSelect.value);
            if(!preset) return;
            if(!deleteArmed){
                deleteArmed=true;
                ctx.promptPresetDelete.textContent=ctx.tr('smart.promptPresetDeleteAgain');
                ctx.promptPresetDelete.classList.add('confirm-danger');
                setStatus(ctx.tr('smart.promptPresetDeleteConfirm').replace('{name}',preset.name||ctx.tr('smart.promptPresetUnnamed')),'warn');
                return;
            }
            ctx.removePreset(preset.id);
            ctx.nodes().forEach(node=>{if(node.promptPresetId===preset.id) node.promptPresetId='';});
            renderPanel(ctx.promptPresets()[0]?.id||'',ctx.tr('smart.promptPresetDeleted'));
            setStatus(ctx.tr('smart.promptPresetDeleted'),'ok');
            ctx.render();
            ctx.scheduleSave();
        };
        bound=true;
    }

    global.CanvasPromptPresetPanel={configure,bindEvents,panelNode,setStatus,resetDeleteState,renderPanel,openPanel,closePanel};
})(typeof window!=='undefined'?window:globalThis);

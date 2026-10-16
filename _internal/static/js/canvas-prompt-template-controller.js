/* Prompt-template panel controller: panel lifecycle, selection state and commands. */
(function(global){
    'use strict';

    var deps={getContext:null};
    var bound=false;
    function configure(opts){Object.assign(deps,opts||{});}
    function context(){return deps.getContext?deps.getContext():{};}

    function activeNodeId(){
        const ctx=context();
        const panel=ctx.promptTemplatePanel;
        return panel?.classList?.contains('open') && panel.dataset.target!=='composer' ? (panel.dataset.nodeId||'') : '';
    }
    function syncComposerButton(){
        const ctx=context();
        const button=ctx.composerTemplateBtn;
        const panel=ctx.promptTemplatePanel;
        if(!button||!panel) return;
        // 停靠在资产库面板（.docked）时不算 composer 激活态
        const active=panel.classList.contains('open') && panel.dataset.target==='composer' && !panel.classList.contains('docked');
        button.classList.toggle('active',active);
        button.setAttribute('aria-pressed',active?'true':'false');
    }
    function positionNearAnchor(anchor){
        const panel=context().promptTemplatePanel;
        if(!panel||!anchor?.getBoundingClientRect) return;
        const rect=anchor.getBoundingClientRect();
        const pad=12;
        const width=Math.min(620,Math.max(320,global.innerWidth-pad*2));
        const height=Math.min(760,Math.max(320,global.innerHeight-pad*2));
        const left=Math.min(Math.max(pad,rect.left),Math.max(pad,global.innerWidth-width-pad));
        let top=rect.bottom+10;
        if(top+height>global.innerHeight-pad) top=rect.top-height-10;
        top=Math.min(Math.max(pad,top),Math.max(pad,global.innerHeight-height-pad));
        panel.style.left=`${Math.round(left)}px`;
        panel.style.top=`${Math.round(top)}px`;
        panel.style.right='auto';
        panel.style.bottom='auto';
        panel.style.width=`${Math.round(width)}px`;
        panel.style.height=`${Math.round(height)}px`;
    }
    function openPanel(nodeId='',templateId='',options={}){
        const ctx=context();
        const state=ctx.state;
        const panel=ctx.promptTemplatePanel;
        if(!panel) return;
        const target=options.target==='composer'?'composer':'node';
        panel.dataset.target=target;
        panel.dataset.nodeId=nodeId||'';
        if(panel.classList.contains('docked')){
            // 2026-10-16：面板停靠在资产库里时被外部入口打开 → 摘掉停靠态（openPanel 会搬回 shell），
            // 并广播给 smart-canvas.js 同步资产库 tab
            panel.classList.remove('docked');
            panel.dispatchEvent(new CustomEvent('prompttemplate-undocked'));
        }
        if(panel.parentElement!==ctx.shell) ctx.shell.appendChild(panel);
        if(templateId) state.selectedId=templateId;
        if(!state.selectedId) state.selectedId=ctx.promptTemplateItems()[0]?.id||'';
        ctx.renderPromptTemplatePanel();
        panel.classList.add('open');
        if(target==='node'&&nodeId) ctx.setTemplateNodeSelection(nodeId);
        ctx.render();
        syncComposerButton();
        if(options.anchor) positionNearAnchor(options.anchor);
        else {
            panel.style.left=''; panel.style.top=''; panel.style.right=''; panel.style.bottom='';
            panel.style.width=''; panel.style.height='';
        }
        ctx.promptTemplateSearch?.focus();
    }
    function closePanel(){
        const ctx=context();
        // 2026-10-16：停靠在资产库面板（.docked）时不关——由 tab 切换/资产面板关闭接管；
        // 应用模板后也留在库内继续浏览
        if(ctx.promptTemplatePanel?.classList.contains('docked')){ syncComposerButton(); return; }
        ctx.promptTemplatePanel?.classList.remove('open');
        syncComposerButton();
        ctx.render();
    }
    function applyTemplate(mode='positive'){
        const ctx=context();
        const state=ctx.state;
        const panel=ctx.promptTemplatePanel;
        const template=ctx.promptTemplateItems().find(item=>item.id===state.selectedId);
        if(!template) return;
        if(panel?.dataset.target==='composer'){
            ctx.setPromptText(ctx.promptTemplateText(template,mode));
            delete ctx.promptInput.dataset.preserveDraftOnce;
            ctx.savePromptDraftForCurrent();
            ctx.renderInputThumbsRow(ctx.selectedNode());
            closePanel();
            ctx.scheduleSave();
            return;
        }
        const node=ctx.getNodes().find(item=>item.id===panel?.dataset.nodeId);
        if(!node) return;
        node.text=ctx.promptTemplateText(template,mode);
        node.promptPresetId=template.builtin?'':(template.sourceId||'');
        closePanel();
        ctx.render();
        ctx.scheduleSave();
    }
    function bindEvents(){
        if(bound) return;
        const ctx=context();
        const panel=ctx.promptTemplatePanel;
        panel?.addEventListener('pointerdown',event=>event.stopPropagation());
        panel?.addEventListener('mousedown',event=>event.stopPropagation());
        panel?.addEventListener('wheel',event=>event.stopPropagation(),{passive:false});
        panel?.addEventListener('click',event=>{
            event.stopPropagation();
            const apply=event.target.closest('[data-template-apply]');
            if(apply){applyTemplate(apply.dataset.templateApply||'positive');return;}
            if(event.target.closest('[data-template-save-current]')){context().saveCurrentPromptAsTemplate();return;}
            if(event.target.closest('[data-template-new]')){context().createBlankPromptTemplate();return;}
            if(event.target.closest('[data-template-edit]')){context().state.editing=true;context().renderPromptTemplatePanel();return;}
            if(event.target.closest('[data-template-edit-cancel]')){context().state.editing=false;context().renderPromptTemplatePanel();return;}
            if(event.target.closest('[data-template-edit-save]')){context().savePromptTemplateEdit();return;}
            if(event.target.closest('[data-template-delete]')){context().deletePromptTemplate();return;}
            const category=event.target.closest('[data-template-cat]');
            if(category){
                const state=context().state;
                state.category=category.dataset.templateCat||'all';
                state.selectedId='';
                state.editing=false;
                context().renderPromptTemplatePanel({preserveScroll:false});
                return;
            }
            const rename=event.target.closest('[data-template-cat-edit]');
            if(rename){context().renamePromptTemplateGroup(rename.dataset.templateCatEdit||'');return;}
            const remove=event.target.closest('[data-template-cat-delete]');
            if(remove){context().deletePromptTemplateGroup(remove.dataset.templateCatDelete||'');return;}
            if(event.target.closest('[data-template-group-edit]')){
                const state=context().state;
                state.groupEditMode=!state.groupEditMode;
                context().renderPromptTemplatePanel({preserveScroll:false});
                return;
            }
            if(event.target.closest('[data-template-cat-new]')){context().createPromptTemplateGroup();return;}
            const card=event.target.closest('[data-template-id]');
            if(card){
                const state=context().state;
                state.selectedId=card.dataset.templateId||'';
                state.editing=false;
                context().renderPromptTemplatePanel();
            }
        });
        if(ctx.promptTemplateClose) ctx.promptTemplateClose.onclick=closePanel;
        if(ctx.promptTemplateSearch) ctx.promptTemplateSearch.oninput=()=>context().renderPromptTemplatePanel({preserveScroll:false});
        if(ctx.promptTemplateLibrarySelect) ctx.promptTemplateLibrarySelect.onchange=()=>{
            const state=context().state;
            state.activeLibraryId=ctx.promptTemplateLibrarySelect.value||'system';
            state.selectedId='';
            state.editing=false;
            context().renderPromptTemplatePanel({preserveScroll:false});
        };
        if(ctx.composerTemplateBtn) ctx.composerTemplateBtn.onclick=event=>{
            event.preventDefault();event.stopPropagation();
            const panel=context().promptTemplatePanel;
            if(panel?.classList?.contains('open')&&panel.dataset.target==='composer'&&!panel.classList.contains('docked')){closePanel();return;}
            const active=context();
            openPanel(active.activeComposerNode()?.id||active.selectedNode()?.id||'',active.state.selectedId,{target:'composer',anchor:event.currentTarget});
        };
        bound=true;
    }

    global.CanvasPromptTemplateController={
        configure:configure,
        bindEvents:bindEvents,
        activeNodeId:activeNodeId,
        syncComposerButton:syncComposerButton,
        positionNearAnchor:positionNearAnchor,
        openPanel:openPanel,
        closePanel:closePanel,
        applyTemplate:applyTemplate
    };
})(typeof window!=='undefined'?window:globalThis);

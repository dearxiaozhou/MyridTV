/* Prompt-node controls: bind text editing and LLM settings. */
(function(global){
    'use strict';

    const deps = {getContext:null};
    function configure(options){Object.assign(deps, options || {});}
    function context(){return deps.getContext ? deps.getContext() : {};}

    function bind(el, node){
        const ctx = context();
        if(!el || !node) return;
        el.querySelectorAll('.prompt-node-control, .prompt-node-pill').forEach(control => {
            control.addEventListener('mousedown', event => event.stopPropagation());
            control.addEventListener('click', event => event.stopPropagation());
            control.addEventListener('dblclick', event => event.stopPropagation());
        });
        // ~ 提示词库 / / 技能：三个输入区都挂快捷插入面板（LLM 打开后主文本是只读输出，不影响）
        const picker = global.CanvasNodePromptPicker;
        const attachPicker = target => { if(target && picker) picker.attach(target); };
        const textEl = el.querySelector('.prompt-node-text');
        if(textEl){
            ctx.bindScrollableText(textEl);
            textEl.oninput = event => { node.text = event.target.value; ctx.scheduleSave(); };
            attachPicker(textEl);
        }
        const presetEdit = el.querySelector('.prompt-preset-edit');
        if(presetEdit) presetEdit.onclick = event => {
            event.preventDefault();
            event.stopPropagation();
            ctx.editPromptPresetForNode(node);
        };
        const toggle = el.querySelector('.prompt-llm-toggle');
        if(toggle) toggle.onclick = event => {
            event.preventDefault();
            event.stopPropagation();
            node.llmEnabled = !node.llmEnabled;
            if(node.llmEnabled){
                node.llmProvider = ctx.resolveChatProviderId(node.llmProvider || '');
                node.llmModel = ctx.resolveChatModel(node.llmModel || '', node.llmProvider);
                node.h = Math.max(Number(node.h) || 0, ctx.promptNodeExpandedHeight(node));
                node.w = Math.max(Number(node.w) || 0, 316);
            } else {
                node.h = 194;
                node.w = Math.max(Number(node.w) || 0, 316);
            }
            ctx.render();
            ctx.scheduleSave();
        };
        const providerEl = el.querySelector('.prompt-llm-provider');
        if(providerEl) providerEl.onchange = event => {
            event.stopPropagation();
            node.llmProvider = ctx.resolveChatProviderId(event.target.value);
            node.llmModel = ctx.resolveChatModel('', node.llmProvider);
            ctx.render();
            ctx.scheduleSave();
        };
        const modelEl = el.querySelector('.prompt-llm-model');
        if(modelEl) modelEl.onchange = event => { event.stopPropagation(); node.llmModel = event.target.value; ctx.scheduleSave(); };
        const systemToggle = el.querySelector('.prompt-system-toggle');
        if(systemToggle) systemToggle.onclick = event => {
            event.preventDefault();
            event.stopPropagation();
            const previousHeight = Number(node.h) || 0;
            node.llmSystemEnabled = !node.llmSystemEnabled;
            if(node.llmSystemEnabled) node.h = Math.max(previousHeight, ctx.promptNodeExpandedHeight(node));
            else if(previousHeight <= 364) node.h = ctx.promptNodeExpandedHeight(node);
            ctx.render();
            ctx.scheduleSave();
        };
        const systemEl = el.querySelector('.prompt-llm-system');
        if(systemEl){
            ctx.bindScrollableText(systemEl);
            systemEl.oninput = event => { node.llmSystemPrompt = event.target.value; ctx.scheduleSave(); };
            attachPicker(systemEl);
        }
        const instructionEl = el.querySelector('.prompt-llm-instruction');
        if(instructionEl){
            ctx.bindScrollableText(instructionEl);
            instructionEl.oninput = event => { node.llmInstruction = event.target.value; ctx.scheduleSave(); };
            attachPicker(instructionEl);
        }
        const runEl = el.querySelector('.prompt-node-run');
        if(runEl) runEl.onclick = event => {
            event.preventDefault();
            event.stopPropagation();
            ctx.runPromptLLMNode(node.id);
        };
    }

    global.CanvasPromptNodeController = {configure, bind};
})(typeof window !== 'undefined' ? window : globalThis);

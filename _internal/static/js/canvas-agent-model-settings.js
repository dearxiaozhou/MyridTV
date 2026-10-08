//** Agent model catalogs (gen/chat/llm providers), custom dropdown enhancement, settings panel render/collect/toggle, generation preset build. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    function D(name){return typeof deps[name] === 'function' ? deps[name]() : deps[name];}

function canvasAgentGenProviders(){
    const list = deps.imageProviders().map(p => ({id:p.id, name:p.name || p.id}));
    const rh0 = (D("apiProviders") || []).find(p => p.id === 'runninghub' && p.enabled !== false);
    if(rh0 && !list.some(p => p.id === 'runninghub')) list.unshift({id:'runninghub', name:rh0.name || 'RunningHub'});
    const volc = (D("apiProviders") || []).find(p => p.id === 'volcengine' && p.enabled !== false && (p.image_models || []).length);
    if(volc && !list.some(p => p.id === 'volcengine')) list.push({id:'volcengine', name:volc.name || '火山引擎'});
    list.push({id:'comfy', name:'本地 ComfyUI'});
    return list;
}
function canvasAgentComfyWorkflowNames(){
    const names = (D("comfyWorkflows") || [])
        .map(w => String(w?.name || w?.workflow || '').trim())
        .filter(Boolean);
    return [...new Set(names)];
}
function canvasAgentGenModelsFor(providerId){
    if(providerId === 'comfy'){
        return canvasAgentComfyWorkflowNames();
    }
    if(providerId === 'volcengine'){
        const provider = (D("apiProviders") || []).find(p => p.id === 'volcengine');
        // 生图模型列表只取 image_models；video_models（如 SD-2.0/seedance）不是生图模型，禁止混入
        const models = (provider && Array.isArray(provider.image_models)) ? provider.image_models : [];
        return [...new Set(models)].filter(Boolean);
    }
    const provider = (D("apiProviders") || []).find(p => p.id === providerId);
    let models = (provider && Array.isArray(provider.image_models)) ? provider.image_models : [];
    // RH 云端工作流不进 Agent 生图模型池（工作流生图走画布节点：选 RH 平台+工作流+连图配参）
    return [...new Set(models)].filter(Boolean);
}
function canvasAgentResolveGenModel(providerId, requested, kind='t2i'){
    const models = canvasAgentGenModelsFor(providerId);
    const cleanRequested = String(requested || '').trim();
    if(cleanRequested && models.includes(cleanRequested)) return cleanRequested;
    const wantsI2I = kind === 'i2i';
    const preferred = models.find(m => wantsI2I
        ? /(image-to-image|\/edit|img2img|图生图)/i.test(String(m))
        : /(text-to-image|txt2img|文生图)/i.test(String(m)));
    return preferred || models[0] || '';
}
function canvasAgentGenModelLabel(model, providerId){
    const m = String(model || '');
    // 名称本身已带"文生图/图生图"字样时不再追加后缀（避免"Krea2文生图（文生图）"冗余）
    let kindHint = /(image-to-image|\/edit|img2img|图生图)/i.test(m) ? '（图生图）'
        : /(text-to-image|txt2img|文生图)/i.test(m) ? '（文生图）' : '';
    if(m.includes('图生图') || m.includes('文生图')) kindHint = '';
    // 优先用 API 设置里的自定义显示名（与 composer 模型下拉同一来源）
    const pid = providerId || presetAgentGenProviderId() || 'runninghub';
    const disp = (typeof providerModelDisplayName === 'function') ? deps.providerModelDisplayName(pid, m) : '';
    if(disp && disp !== m) return disp + (kindHint && !disp.includes('图生图') && !disp.includes('文生图') ? kindHint : '');
    return m + kindHint;
}
function presetAgentGenProviderId(){
    const sel = document.getElementById('canvasAgentGenProvider');
    return (sel && sel.value) || (D("canvasAgentModelPreset") && D("canvasAgentModelPreset").genProviderId) || '';
}
function canvasAgentChatModelsFor(providerId){
    const provider = canvasAgentLlmProviders().find(p => p.id === providerId)
        || deps.canvasAgentChatProviders().find(p => p.id === providerId);
    return [...new Set(provider?.chat_models || [])].filter(Boolean);
}
// 画布「智能体设置」里的 LLM 平台下拉：已配置好的自定义对话平台（OpenAI 兼容、有请求地址）。
/* 2026-10-08（老王："智能体设置的 LLM 平台，自动过滤掉没有 LLM 模型的平台"）
   原来只按 enabled / 非 runninghub / 有 base_url 过滤，于是纯生图平台、或者压根没拉过
   模型的平台也混进「LLM平台」下拉，选了才发现模型是空的。

   判据用 available_chat_models（平台**提供**的全部 chat 模型，拉取模型时写入），
   并回退 chat_models（用户已勾选的）：
     · 只看 chat_models 会误杀「平台有模型、但用户还没勾选」的平台
     · 只看 available_chat_models 会漏掉「模型是手填的」老配置
   两者任一非空即视为该平台可用。 */
function canvasAgentLlmProviders(){
    const modelList = (...buckets) => [...new Set(buckets.flat().map(v => String(v || '').trim()).filter(Boolean))];
    const list = (D("apiProviders") || []).filter(p => p && p.enabled !== false
        && p.id !== 'runninghub' && String(p.protocol || '').toLowerCase() !== 'runninghub'
        && String(p.base_url || '').trim())
        .map(p => ({
            id:String(p.id || ''),
            name:p.name || String(p.id || ''),
            chat_models:modelList(p.chat_models),
            available_chat_models:modelList(p.available_chat_models)
        }))
        .filter(p => p.id)
        // 没有 LLM 模型的平台一律不进下拉
        .filter(p => p.available_chat_models.length || p.chat_models.length);
    const entry = deps.canvasAgentActiveEntry() || {};
    const savedPid = String(entry.provider_id || deps.configuredAgentProviderId() || '').trim();
    if(savedPid && !list.some(p => p.id === savedPid)){
        // 兜底项（配置里存着、但平台列表里没有）同样要求有模型，否则别塞回下拉
        const fbModels = modelList(entry.chat_models, entry.available_chat_models);
        if(fbModels.length) list.unshift({
            id:savedPid,
            name:entry.name || savedPid,
            chat_models:fbModels,
            available_chat_models:[]
        });
    }
    return list;
}
/* ================= Agent 设置面板 select 统一化 =================
   原生 <select> 展开的是系统菜单（浅色/圆角，与深色方正风格脱节）。
   做法：保留隐藏原生 select 作数据载体（collect/render 仍读写 .value），
   外面盖一个方正按钮 + 自研列表气泡（挂在 body 用 fixed 定位，避免面板 overflow:auto 裁剪）。 */
function closeAgentDropdown(){
    document.querySelectorAll('.agent-select-btn[aria-expanded="true"]').forEach(btn => btn.setAttribute('aria-expanded', 'false'));
    document.querySelectorAll('.agent-select-pop').forEach(e => e.remove());
}
function openAgentDropdown(sel, anchor){
    closeAgentDropdown();
    // 定位锚点必须是【可见】元素：隐藏的原生 select rect 全 0，会把菜单甩到左上角
    const anchorEl = anchor && anchor.offsetParent !== null ? anchor : (sel.closest('.agent-select-wrap')?.querySelector(':scope > .agent-select-btn') || sel);
    const rect = anchorEl.getBoundingClientRect();
    const opts = [...sel.options];
    if(!opts.length) return;
    anchorEl.setAttribute('aria-expanded', 'true');
    const pop = document.createElement('div');
    pop.className = 'agent-select-pop';
    const rowH = 26, maxVisible = 8;
    const below = window.innerHeight - rect.bottom;
    const popH = Math.min(opts.length, maxVisible) * rowH + 8;
    const putBelow = below >= popH + 8 || below >= rect.top;
    pop.style.left = Math.max(6, Math.min(rect.left, window.innerWidth - Math.max(rect.width, 130) - 6)) + 'px';
    pop.style.width = Math.max(rect.width, 130) + 'px';
    pop.style.maxHeight = popH + 'px';
    if(putBelow) pop.style.top = (rect.bottom + 4) + 'px';
    else pop.style.bottom = (window.innerHeight - rect.top + 4) + 'px';
    pop.innerHTML = opts.map((o, i) => `<button type="button" class="agent-select-opt${o.value === sel.value ? ' active' : ''}" data-agent-select-index="${i}"><span>${deps.escapeHtml(o.textContent)}</span></button>`).join('');
    document.body.appendChild(pop);
    const closeAll = () => {
        closeAgentDropdown();
        document.removeEventListener('mousedown', onDocDown, true);
        window.removeEventListener('scroll', closeAll, true);
        window.removeEventListener('resize', closeAll);
    };
    const onDocDown = e => { if(!pop.contains(e.target) && !pop.contains(anchorEl)) closeAll(); };
    pop.querySelectorAll('[data-agent-select-index]').forEach(btn => {
        btn.onclick = ev => {
            ev.preventDefault(); ev.stopPropagation();
            const o = opts[Number(btn.dataset.agentSelectIndex)];
            if(o && sel.value !== o.value){
                sel.value = o.value;
                sel.dispatchEvent(new Event('change', {bubbles:true}));
            }
            closeAll();
        };
    });
    document.addEventListener('mousedown', onDocDown, true);
    window.addEventListener('scroll', closeAll, true);
    window.addEventListener('resize', closeAll);
}
function enhanceAgentSelects(){
    const roots = [];
    const panel = document.getElementById('canvasAgentSettingsPanel');
    if(panel) roots.push(...panel.querySelectorAll('select'));
    if(D("engineSelect")) roots.push(D("engineSelect"));
    roots.forEach(sel => {
        sel.classList.add('agent-select-native');
        if(!sel.__ddEnhanced){
            sel.__ddEnhanced = true;
            const syncLabel = () => {
                const btn = sel.parentElement?.querySelector(':scope > .agent-select-btn span');
                if(btn) btn.textContent = sel.options[sel.selectedIndex]?.textContent || '';
            };
            sel.addEventListener('change', syncLabel);
            sel.__syncDdLabel = syncLabel;
        }
        let wrap = sel.closest('.agent-select-wrap');
        if(!wrap){
            wrap = document.createElement('span');
            wrap.className = 'agent-select-wrap';
            sel.parentNode.insertBefore(wrap, sel);
            wrap.appendChild(sel);
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'agent-select-btn';
            btn.setAttribute('aria-expanded', 'false');
            btn.innerHTML = `<span>${deps.escapeHtml(sel.options[sel.selectedIndex]?.textContent || '')}</span><span class="agent-select-caret">▾</span>`;
            btn.onclick = e => { e.preventDefault(); e.stopPropagation(); openAgentDropdown(sel, btn); };
            wrap.insertBefore(btn, sel);
        } else {
            const btn = wrap.querySelector(':scope > .agent-select-btn span');
            if(btn) btn.textContent = sel.options[sel.selectedIndex]?.textContent || '';
        }
        // 原生 select 被业务逻辑隐藏（如 3D预演隐藏引擎下拉）时，包装层与按钮一并隐藏
        const wrapEl = sel.closest('.agent-select-wrap');
        if(wrapEl){
            const hidden = sel.style.display === 'none' || sel.offsetParent === null && sel.style.display !== '';
            wrapEl.style.display = sel.style.display === 'none' ? 'none' : '';
        }
    });
}
function renderCanvasAgentSettingsPanel(){
    const preset = D("canvasAgentModelPreset") || deps.canvasAgentLoadPreset();
    if(preset && preset.agentId && deps.canvasAgentRegistry()[preset.agentId]) deps.setCanvasAgentActiveId(preset.agentId);
    const activeEntry = deps.canvasAgentEntry(D("canvasAgentActiveId")) || {};
    deps.canvasAgentRefreshHeadTitle();
    const el = id => document.getElementById(id);
    const chatModelSel = el('canvasAgentChatModel');
    const genProviderSel = el('canvasAgentGenProvider');
    const genModelSel = el('canvasAgentGenModel');
    const genRatioSel = el('canvasAgentGenRatio');
    const genResSel = el('canvasAgentGenResolution');
    const genQualitySel = el('canvasAgentGenQuality');
    if(!chatModelSel) return;
    const agentSel = el('canvasAgentSelect');
    const llmProviders = canvasAgentLlmProviders();
    if(agentSel){
        agentSel.innerHTML = llmProviders.map(p => `<option value="${deps.escapeHtml(p.id)}">${deps.escapeHtml(p.name)}</option>`).join('')
            || '<option value="">暂无可用对话平台，请先在 API 设置添加</option>';
        const savedPid = String(activeEntry.provider_id || deps.configuredAgentProviderId() || '').trim();
        agentSel.value = (savedPid && llmProviders.some(p => p.id === savedPid)) ? savedPid : (llmProviders[0]?.id || '');
    }
    if(chatModelSel) chatModelSel.disabled = false;
    const selectedPid = String(agentSel?.value || activeEntry.provider_id || '').trim();
    const chatProvider = llmProviders.find(p => p.id === selectedPid) || llmProviders[0] || null;
    const configuredChatModel = deps.canvasAgentConfiguredChatModel(activeEntry, chatProvider);
    const chatModels = chatProvider ? [...new Set([configuredChatModel, ...(chatProvider.chat_models || []), ...(chatProvider.available_chat_models || [])].filter(Boolean))] : [configuredChatModel].filter(Boolean);
    const activeChatModel = chatModels.includes(configuredChatModel) ? configuredChatModel : (chatModels[0] || '');
    chatModelSel.innerHTML = [...new Set([activeChatModel, ...chatModels].filter(Boolean))].map(m => `<option value="${deps.escapeHtml(m)}" ${m === activeChatModel ? 'selected' : ''}>${deps.escapeHtml(m)}</option>`).join('');
    // 生图控件无论哪种模式都渲染
    const genProviders = canvasAgentGenProviders();
    const activeGenProvider = genProviders.some(p => p.id === preset.genProviderId) ? preset.genProviderId : (genProviders[0]?.id || 'runninghub');
    genProviderSel.innerHTML = genProviders.map(p => `<option value="${deps.escapeHtml(p.id)}" ${p.id === activeGenProvider ? 'selected' : ''}>${deps.escapeHtml(p.name || p.id)}</option>`).join('');
    const genModels = canvasAgentGenModelsFor(activeGenProvider);
    const activeGenModel = canvasAgentResolveGenModel(activeGenProvider, preset.genModel, 't2i');
    genModelSel.innerHTML = genModels.map(m => `<option value="${deps.escapeHtml(m)}" ${m === activeGenModel ? 'selected' : ''}>${deps.escapeHtml(canvasAgentGenModelLabel(m, activeGenProvider))}</option>`).join('');
    genRatioSel.innerHTML = D("CANVAS_AGENT_RATIO_OPTIONS").map(([k, label]) => `<option value="${k}" ${k === preset.ratio ? 'selected' : ''}>${label}</option>`).join('');
    genResSel.innerHTML = ['1k','2k','4k'].map(r => `<option value="${r}" ${r === preset.resolution ? 'selected' : ''}>${r}</option>`).join('');
    genQualitySel.innerHTML = ['auto','low','medium','high'].map(q => `<option value="${q}" ${q === preset.quality ? 'selected' : ''}>${q === 'auto' ? '自动' : q}</option>`).join('');
    // 图生图预设（第二组）
    const gen2ProviderSel = el('canvasAgentGen2Provider');
    const gen2ModelSel = el('canvasAgentGen2Model');
    const gen2RatioSel = el('canvasAgentGen2Ratio');
    const gen2ResSel = el('canvasAgentGen2Resolution');
    const gen2QualitySel = el('canvasAgentGen2Quality');
    if(gen2ProviderSel){
        const gen2Providers = canvasAgentGenProviders();
        const activeGen2Provider = gen2Providers.some(p => p.id === preset.gen2ProviderId) ? preset.gen2ProviderId : (gen2Providers[0]?.id || 'runninghub');
        gen2ProviderSel.innerHTML = gen2Providers.map(p => `<option value="${deps.escapeHtml(p.id)}" ${p.id === activeGen2Provider ? 'selected' : ''}>${deps.escapeHtml(p.name || p.id)}</option>`).join('');
        const gen2Models = canvasAgentGenModelsFor(activeGen2Provider);
        let activeGen2Model = canvasAgentResolveGenModel(activeGen2Provider, preset.gen2Model, 'i2i');
        gen2ModelSel.innerHTML = gen2Models.map(m => `<option value="${deps.escapeHtml(m)}" ${m === activeGen2Model ? 'selected' : ''}>${deps.escapeHtml(canvasAgentGenModelLabel(m, activeGen2Provider))}</option>`).join('');
        gen2RatioSel.innerHTML = D("CANVAS_AGENT_RATIO_OPTIONS").map(([k, label]) => `<option value="${k}" ${k === (preset.gen2Ratio || 'landscape43') ? 'selected' : ''}>${label}</option>`).join('');
        gen2ResSel.innerHTML = ['1k','2k','4k'].map(r => `<option value="${r}" ${r === (preset.gen2Resolution || '2k') ? 'selected' : ''}>${r}</option>`).join('');
        gen2QualitySel.innerHTML = ['auto','low','medium','high'].map(q => `<option value="${q}" ${q === (preset.gen2Quality || 'medium') ? 'selected' : ''}>${q === 'auto' ? '自动' : q}</option>`).join('');
    }
    enhanceAgentSelects();
}
function collectCanvasAgentSettings(){
    const el = id => document.getElementById(id);
    const chatModelSel = el('canvasAgentChatModel');
    if(!chatModelSel) return null;
    return {
        chatProviderId: (el('canvasAgentSelect')?.value || ''),
        chatModel: (chatModelSel.value || deps.canvasAgentConfiguredChatModel()),
        genProviderId: (el('canvasAgentGenProvider')?.value || 'runninghub'),
        genModel: (el('canvasAgentGenModel')?.value || ''),
        ratio: (el('canvasAgentGenRatio')?.value || 'landscape43'),
        resolution: (el('canvasAgentGenResolution')?.value || '2k'),
        quality: (el('canvasAgentGenQuality')?.value || 'medium'),
        gen2ProviderId: (el('canvasAgentGen2Provider')?.value || 'runninghub'),
        gen2Model: (el('canvasAgentGen2Model')?.value || ''),
        gen2Ratio: (el('canvasAgentGen2Ratio')?.value || 'landscape43'),
        gen2Resolution: (el('canvasAgentGen2Resolution')?.value || '2k'),
        gen2Quality: (el('canvasAgentGen2Quality')?.value || 'medium')
    };
}
function toggleCanvasAgentSettings(force, mode){
    const panel = document.getElementById('canvasAgentSettingsPanel');
    if(!panel) return;
    if(force === true || (force !== false && panel.hidden)){
        if(mode){
            const titleEl = document.getElementById('canvasAgentSettingsTitleText');
            const agentSection = document.getElementById('canvasAgentAgentSection');
            const genSection = document.getElementById('canvasAgentGenSection');
            if(titleEl) titleEl.textContent = mode === 'gen' ? '生图模型设置' : '智能体设置';
            if(agentSection) agentSection.hidden = mode === 'gen';
            if(genSection) genSection.hidden = mode !== 'gen';
            const testBtn = document.getElementById('canvasAgentTestChat');
            if(testBtn) testBtn.style.display = mode === 'gen' ? 'none' : '';
        }
        renderCanvasAgentSettingsPanel();
        panel.hidden = false;
    }else{
        panel.hidden = true;
    }
}
function buildCanvasAgentGenerationPreset(preset, kind='t2i'){
    preset = preset || {};
    const isI2I = kind === 'i2i';
    const ratioKey = (isI2I ? preset.gen2Ratio : preset.ratio) && D("SIZE_MAP")[isI2I ? preset.gen2Ratio : preset.ratio] ? (isI2I ? preset.gen2Ratio : preset.ratio) : 'wide';
    const resolution = (isI2I ? preset.gen2Resolution : preset.resolution) || '4k';
    const size = D("SIZE_MAP")[ratioKey]?.[resolution] || D("SIZE_MAP")[ratioKey]?.['4k'] || '3840x2160';
    return {
        provider_id: (isI2I ? preset.gen2ProviderId : preset.genProviderId) || 'runninghub',
        model: canvasAgentResolveGenModel(
            (isI2I ? preset.gen2ProviderId : preset.genProviderId) || 'runninghub',
            isI2I ? preset.gen2Model : preset.genModel,
            isI2I ? 'i2i' : 't2i'
        ),
        size,
        aspectRatio: D("CANVAS_AGENT_RATIO_TEXT")[ratioKey] || '4:3',
        resolution,
        quality: (isI2I ? preset.gen2Quality : preset.quality) || 'high'
    };
}

    global.CanvasAgentModelSettings = {
        configure,
        canvasAgentGenProviders,
        canvasAgentComfyWorkflowNames,
        canvasAgentGenModelsFor,
        canvasAgentResolveGenModel,
        canvasAgentGenModelLabel,
        presetAgentGenProviderId,
        canvasAgentChatModelsFor,
        canvasAgentLlmProviders,
        closeAgentDropdown,
        openAgentDropdown,
        enhanceAgentSelects,
        renderCanvasAgentSettingsPanel,
        collectCanvasAgentSettings,
        toggleCanvasAgentSettings,
        buildCanvasAgentGenerationPreset,
    };
})(typeof window !== 'undefined' ? window : this);

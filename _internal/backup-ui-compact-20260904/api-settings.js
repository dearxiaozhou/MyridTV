const REMOVED_NATIVE_PROVIDER_IDS = new Set(['modelscope']);
let providers = [];
let selectedId = '';
let selectedAgentId = 'codex';
const AGENT_PANEL_ID = '__agent_panel__';
const AGENT_CODEX_ID = '__agent_codex__';
const providerList = document.getElementById('providerList');
const agentList = document.getElementById('agentList');
const editorTitle = document.getElementById('editorTitle');
const apiPlatformCount = document.getElementById('apiPlatformCount');
const apiAgentCount = document.getElementById('apiAgentCount');
const apiCurrentSelected = document.getElementById('apiCurrentSelected');
const apiCurrentSelectedSub = document.getElementById('apiCurrentSelectedSub');
const statusEl = document.getElementById('status');
const nameInput = document.getElementById('nameInput');
const idInput = document.getElementById('idInput');
const baseInput = document.getElementById('baseInput');
const protocolInput = document.getElementById('protocolInput');
const keyInput = document.getElementById('keyInput');
const keyHint = document.getElementById('keyHint');
const rhFreeKeyInput = document.getElementById('rhFreeKeyInput');
const rhWalletKeyInput = document.getElementById('rhWalletKeyInput');
const rhFreeKeyHint = document.getElementById('rhFreeKeyHint');
const rhWalletKeyHint = document.getElementById('rhWalletKeyHint');
const volcArkKeyHint = document.getElementById('volcArkKeyHint');
const volcAkInput = document.getElementById('volcAkInput');
const volcSkInput = document.getElementById('volcSkInput');
const volcAssetKeyHint = document.getElementById('volcAssetKeyHint');
const volcProjectInput = document.getElementById('volcProjectInput');
const volcRegionInput = document.getElementById('volcRegionInput');
const jimengCliPanel = document.getElementById('jimengCliPanel');
const jimengCliStatus = document.getElementById('jimengCliStatus');
const jimengCredit = document.getElementById('jimengCredit');
const jimengLoginBox = document.getElementById('jimengLoginBox');
const jimengHelpOverlay = document.getElementById('jimengHelpOverlay');
const jimengHelpCommand = document.getElementById('jimengHelpCommand');
const jimengHelpOutput = document.getElementById('jimengHelpOutput');
const runninghubConfigBlock = document.getElementById('runninghubConfigBlock');
const rhPasteInput = document.getElementById('rhPasteInput');
const rhSaveBtn = document.getElementById('rhSaveBtn');
const rhAppsList = document.getElementById('rhAppsList');
const rhWorkflowsList = document.getElementById('rhWorkflowsList');
const rhAppsCount = document.getElementById('rhAppsCount');
const rhWorkflowsCount = document.getElementById('rhWorkflowsCount');
const settingsContent = document.getElementById('settingsContent');
const agentProviderSelect = document.getElementById('agentProviderSelect');
const agentModelSelect = document.getElementById('agentModelSelect');
const agentProxyBaseInput = document.getElementById('agentProxyBaseInput');
const agentUpstreamBaseInput = document.getElementById('agentUpstreamBaseInput');
const agentKeyInput = document.getElementById('agentKeyInput');
const agentKeyHint = document.getElementById('agentKeyHint');
const agentStorageHint = document.getElementById('agentStorageHint');
const agentConfigHint = document.getElementById('agentConfigHint');
const agentModelSourceHint = document.getElementById('agentModelSourceHint');
const agentSaveBtn = document.getElementById('agentSaveBtn');
const agentTestBtn = document.getElementById('agentTestBtn');
const agentFetchModelsBtn = document.getElementById('agentFetchModelsBtn');
const setupWizardOverlay = document.getElementById('setupWizardOverlay');
const setupWizardSteps = document.getElementById('setupWizardSteps');
const setupWizardStatus = document.getElementById('setupWizardStatus');
document.getElementById('visionModelSelect')?.addEventListener('input', () => { try{ syncVisionDisplayName(); }catch(_){} });
document.getElementById('visionEnabledCheck')?.addEventListener('change', () => { try{ syncVisionDisplayName(); }catch(_){} });async function fetchLocalJson(url, options={}, timeout=1800){
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
        const res = await fetch(url, {...options, signal:controller.signal});
        return await res.json();
    } finally {
        clearTimeout(timer);
    }
}
const recommendContent = document.getElementById('recommendContent');
const recommendPanel = document.getElementById('recommendPanel');
const providerOnboardingCard = document.getElementById('providerOnboardingCard');
const rhWorkflowEditorOverlay = document.getElementById('rhWorkflowEditorOverlay');
const rhWorkflowEditorTitle = document.getElementById('rhWorkflowEditorTitle');
const rhWorkflowEditorSub = document.getElementById('rhWorkflowEditorSub');
const rhWorkflowSaveBtn = document.getElementById('rhWorkflowSaveBtn');
const rhWorkflowEditName = document.getElementById('rhWorkflowEditName');
const rhWorkflowEditNote = document.getElementById('rhWorkflowEditNote');
const rhWorkflowEditorSummary = document.getElementById('rhWorkflowEditorSummary');
const rhWorkflowEditorNodeList = document.getElementById('rhWorkflowEditorNodeList');
const rhWorkflowEditorGraphWrap = document.getElementById('rhWorkflowEditorGraphWrap');
let rhWorkflowEditorGraphSvg = document.getElementById('rhWorkflowEditorGraphSvg');
let rhWorkflowEditorZoom = document.getElementById('rhWorkflowEditorZoom');
const imageModelList = document.getElementById('imageModelList');
const chatModelList = document.getElementById('chatModelList');
const videoModelList = document.getElementById('videoModelList');
const msLoraBlock = document.getElementById('msLoraBlock');
const msLoraList = document.getElementById('msLoraList');
const recommendApiOverlay = document.getElementById('recommendApiOverlay');
const recommendApiList = document.getElementById('recommendApiList');
const VOLCENGINE_DEFAULT_BASE_URL = 'https://ark.cn-beijing.volces.com/api/v3';
const VOLCENGINE_DEFAULT_PROJECT_NAME = 'default';
const VOLCENGINE_DEFAULT_REGION = 'cn-beijing';
const CODEX_APP_ICON = '/static/images/codex-native.png';
const VOLCENGINE_DEFAULT_VIDEO_MODELS = [
    'doubao-seedance-2-0-260128',
    'doubao-seedance-2-0-fast-260128',
    'doubao-seedance-1-5-pro-251215',
    'doubao-seedance-1-0-pro-250528',
    'doubao-seedance-1-0-lite-t2v-250428',
    'doubao-seedance-1-0-lite-i2v-250428'
];
const MS_BUILTIN_IMAGE_MODELS = [
    'Tongyi-MAI/Z-Image-Turbo',
    'Qwen/Qwen-Image-2512',
    'Qwen/Qwen-Image-Edit-2511',
    'black-forest-labs/FLUX.2-klein-9B'
];
const MS_DEFAULT_BASE_URL = 'https://api-inference.modelscope.cn/v1';
const RH_DEFAULT_BASE_URL = 'https://www.runninghub.ai';
const EXAMPLE_BASE_URL = 'https://api.example.com/v1';
const CODEX_LOCAL_UPSTREAM = 'codex://local';
const CODEX_LOCAL_DEFAULT_MODEL = 'codex-default';
const RH_DEFAULT_IMAGE_MODELS = [
  'seedream-v5-lite/text-to-image',
  'seedream-v5-lite/image-to-image',
  'rhart-image-g-2/text-to-image',
    'rhart-image-g-2/image-to-image',
    'rhart-image-g-2-official/text-to-image',
    'rhart-image-g-2-official/image-to-image',
    'rhart-image-n-pro-official/edit',
    'rhart-image/f-2-klein-9b/text-to-image',
  'rhart-image/f-2-klein-9b/edit',
  'rhart-image-v1-official/text-to-image'
];
const RH_MODEL_ALIASES = window.WcsRhModelAliases || null;
const RH_DEFAULT_MODEL_DISPLAY_NAMES = RH_MODEL_ALIASES?.RH_DEFAULT_MODEL_DISPLAY_NAMES || {};
const JIMENG_DEFAULT_IMAGE_MODELS = ['5.0', '4.6', '4.5', '4.1', '4.0', '3.1', '3.0'];
const JIMENG_DEFAULT_VIDEO_MODELS = ['seedance2.0fast_vip', 'seedance2.0_vip'];
const JIMENG_LEGACY_IMAGE_MODELS = new Set(['jimeng-image-2k', 'jimeng-image-4k']);
const JIMENG_LEGACY_VIDEO_MODELS = new Set(['jimeng-video-720p', 'jimeng-video-1080p']);
const APP_CONFIG_DEFAULTS = {
    server:{host:'127.0.0.1', port:3000, base_url:'http://127.0.0.1:3000'},
    proxy:{host:'127.0.0.1', port:3107, base_url:'http://127.0.0.1:3107'},
    agent:{
        active_id:'codex',
        agents:{
            codex:{
                name:'Myrid-Agent',
                provider_id:'',
                model:'',
                preferred_model_pattern:'',
                upstream_base_url:'',
                api_key_env:'MYRIDTV_AGENT_API_KEY',
                fallback_api_key_env:'API_PROVIDER_CUSTOM_API_KEY'
            }
        }
    },
    runninghub:{api_key_envs:['API_PROVIDER_CUSTOM_API_3_KEY', 'RUNNINGHUB_API_KEY']},
    paths:{env_file:'API/.env'},
    runtime:{python_exe:''},
    setup:{completed:false, completed_at:'', dismissed_at:''}
};
function escapeRegexLiteral(value){
    return String(value || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
let appConfig = APP_CONFIG_DEFAULTS;
let appConfigLoaded = false;
let agentFetchedModels = [];
let agentModelsFetched = false;
let setupWizardOpened = false;
const ONBOARDING_GUIDES = {
    modelscope:{
        titleKey:'api.msOnboardingTitle',
        descKey:'api.msOnboardingDesc',
        primaryLabelKey:'api.msGetTokenCn',
        secondaryLabelKey:'api.msGetTokenGlobal',
        primaryUrl:'https://www.modelscope.cn/my/access/token',
        secondaryUrl:'https://www.modelscope.ai/my/access/token'
    },
    runninghub:{
        titleKey:'api.rhOnboardingTitle',
        descKey:'api.rhOnboardingDesc',
        primaryLabelKey:'api.rhGetKeyCn',
        secondaryLabelKey:'api.rhGetKeyGlobal',
        primaryUrl:'https://www.runninghub.ai/enterprise-api/consumerApi?inviteCode=rh-v1331',
        secondaryUrl:'https://www.runninghub.ai/enterprise-api/consumerApi?inviteCode=rh-v1331',
        walletPrimaryLabelKey:'api.rhGetWalletKeyCn',
        walletSecondaryLabelKey:'api.rhGetWalletKeyGlobal',
        walletPrimaryUrl:'https://www.runninghub.ai/enterprise-api/sharedApi?inviteCode=rh-v1331',
        walletSecondaryUrl:'https://www.runninghub.ai/enterprise-api/sharedApi?inviteCode=rh-v1331'
    }
};
let rhWorkflowEditorState = { open:false, index:-1, entry:null, config:null, expanded:{}, activeNodeId:'', graph:{ k:1, x:0, y:0, w:0, h:0 }, pan:null, bound:false, previewParams:{}, previewRunning:false, previewStatus:'', previewOutputs:[] };
let rhEditorMode = 'workflow';
let rhProviderRefreshInFlight = false;
let rhProviderLastRefreshAt = 0;
let recommendInlineOpen = false;
let providerDragId = '';
const RECOMMENDED_APIS = [];

function refreshIcons(){ if(window.lucide) lucide.createIcons(); }
function tr(key){ return window.StudioI18n ? window.StudioI18n.t(key) : key; }
function trf(key, vars={}){
    let text = tr(key);
    Object.entries(vars).forEach(([name, value]) => {
        text = text.replaceAll(`{${name}}`, String(value ?? ''));
    });
    return text;
}
function setStatus(text){ statusEl.textContent = text || ''; }
function broadcastStudioApiChange(type='providers-changed'){
    const message = { type, updated_at:Date.now() };
    try { new BroadcastChannel('studio-api').postMessage(message); } catch(e) {}
    try { window.parent?.postMessage(message, '*'); } catch(e) {}
    try { window.top?.postMessage(message, '*'); } catch(e) {}
}
function mergeAppConfig(base, override){
    const merged = {...(base || {})};
    Object.entries(override || {}).forEach(([key, value]) => {
        merged[key] = value && typeof value === 'object' && !Array.isArray(value)
            ? mergeAppConfig(merged[key] || {}, value)
            : value;
    });
    return merged;
}
/* —— 多 Agent 支持：Agent 注册表、选中与激活 —— */
const AGENT_DEFS = [
    { id:'codex', name:'Myrid-Agent', defaultKeyEnv:'MYRIDTV_AGENT_API_KEY', defaultUpstream:'' }
];
function agentPanelId(id){ return `__agent_${String(id || '')}__`; }
function isAgentPanelSelection(){ return String(selectedId || '').startsWith('__agent_'); }
function selectedAgentFromPanel(){
    const text = String(selectedId || '');
    if(!text.startsWith('__agent_')) return selectedAgentId || 'codex';
    const inner = text.slice('__agent_'.length);
    return inner.endsWith('__') ? inner.slice(0, -2) : (inner || 'codex');
}
function agentRegistry(){
    return (appConfig?.agent?.agents && typeof appConfig.agent.agents === 'object') ? appConfig.agent.agents : {};
}
function agentEntry(id){
    return agentRegistry()[String(id || '')];
}
function currentAgent(){
    return agentEntry(selectedAgentFromPanel()) || agentEntry(selectedAgentId) || {};
}
function activeAgent(){
    const id = String(appConfig?.agent?.active_id || 'codex');
    return agentEntry(id) || agentEntry('codex') || {};
}
function ensureAgentRegistry(){
    if(!appConfig) appConfig = APP_CONFIG_DEFAULTS;
    const agent = appConfig?.agent || {};
    let agents = (agent.agents && typeof agent.agents === 'object') ? agent.agents : null;
    if(!agents || !Object.keys(agents).length){
        const legacy = {};
        ['provider_id', 'model', 'preferred_model_pattern', 'upstream_base_url', 'api_key_env', 'fallback_api_key_env'].forEach(key => {
            if(agent[key] !== undefined && agent[key] !== '') legacy[key] = agent[key];
        });
        legacy.name = 'Myrid-Agent';
        agents = { codex: legacy };
        appConfig = mergeAppConfig(appConfig, { agent:{ active_id:'codex', agents } });
    }
    const mergedAgents = {...agents};
    AGENT_DEFS.forEach(def => {
        const existing = mergedAgents[def.id];
        if(!existing){
            mergedAgents[def.id] = {
                name:def.name, provider_id:'', model:'', preferred_model_pattern:'',
                upstream_base_url:def.defaultUpstream, api_key_env:def.defaultKeyEnv,
                fallback_api_key_env:'API_PROVIDER_CUSTOM_API_KEY'
            };
        } else if(!existing.name || existing.name === 'DP-H'){
            mergedAgents[def.id] = {...existing, name:def.name};
        }
    });
    if(JSON.stringify(agents) !== JSON.stringify(mergedAgents)){
        appConfig = mergeAppConfig(appConfig, { agent:{ agents: mergedAgents } });
    }
    if(!String(appConfig?.agent?.active_id || '')){
        appConfig = mergeAppConfig(appConfig, { agent:{ active_id:'codex' } });
    }
}
function cleanBaseUrl(value, fallback=''){
    return String(value || fallback || '').trim().replace(/\/+$/, '');
}
function setAgentConfigHint(text, state=''){
    if(!agentConfigHint) return;
    agentConfigHint.textContent = text || '';
    agentConfigHint.classList.toggle('is-ok', state === 'ok');
    agentConfigHint.classList.toggle('is-error', state === 'error');
}
function setSetupWizardStatus(text='', state=''){
    if(!setupWizardStatus) return;
    setupWizardStatus.textContent = text || '';
    setupWizardStatus.classList.toggle('is-ok', state === 'ok');
    setupWizardStatus.classList.toggle('is-error', state === 'error');
}
function agentKeySavedHint(){
    const envName = currentAgent()?.api_key_env || 'API/.env';
    const preview = currentAgent()?.key_preview ? ` ${currentAgent().key_preview}` : '';
    return `Agent Key 已保存：${envName}${preview}`;
}
function setupProviderHasKey(){
    return Boolean(activeAgent()?.has_key);
}
function setupAgentConfigured(){
    const item = activeAgent();
    return Boolean(item?.model && item?.provider_id && appConfig?.proxy?.base_url);
}
function setupSteps(){
    const agent = activeAgent();
    const providerName = agent?.name || appConfig?.agent?.active_id || 'Agent';
    const modelName = agent?.model || agentModelSelect?.value || '';
    return [
        {
            ok:setupAgentConfigured(),
            title:'选择 Agent 对话模型',
            desc:`当前：${providerName}${modelName ? ` / ${modelName}` : ''}`,
            action:'定位设置',
            run:'focusAgentConfig'
        },
        {
            ok:setupProviderHasKey(),
            title:'填写 API Key',
            desc:'在左侧选择平台后保存 Key。也可以从推荐 API 快速创建平台。',
            action:'推荐 API',
            run:'openRecommend'
        },
        {
            ok:appConfig?.setup?.agent_tested === true,
            title:'测试 Agent',
            desc:'确认画布 Agent 可以发起一次真实对话请求。',
            action:'测试',
            run:'testAgent'
        }
    ];
}
function renderSetupWizard(){
    if(!setupWizardSteps) return;
    setupWizardSteps.innerHTML = setupSteps().map((step, index) => `
        <div class="setup-step-card ${step.ok ? 'is-ok' : ''}">
            <div class="setup-step-top">
                <div class="setup-step-index">${index + 1}</div>
                <div class="setup-step-state">${step.ok ? '已完成' : '待处理'}</div>
            </div>
            <div class="setup-step-title">${escapeHtml(step.title)}</div>
            <div class="setup-step-desc">${escapeHtml(step.desc)}</div>
            <button class="action-btn" type="button" onclick="runSetupStep('${step.run}')">${escapeHtml(step.action)}</button>
        </div>
    `).join('');
    refreshIcons();
}
function openSetupWizard(auto=false){
    if(!setupWizardOverlay) return;
    setupWizardOpened = true;
    setupWizardOverlay.classList.add('open');
    renderSetupWizard();
    setSetupWizardStatus(auto ? '按顺序完成这三步，完成后以后不会自动弹出。' : '可以随时重新打开这个向导检查配置。');
}
function closeSetupWizard(){
    setupWizardOverlay?.classList.remove('open');
}
async function saveSetupState(fields){
    const next = mergeAppConfig(appConfig, {setup:{...(appConfig.setup || {}), ...fields}});
    const proxyBase = cleanBaseUrl(next?.proxy?.base_url, APP_CONFIG_DEFAULTS.proxy.base_url);
    const res = await fetch(`${proxyBase}/app-config`, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify(next)
    });
    const data = await res.json().catch(() => ({}));
    if(!res.ok || data.ok === false) throw new Error(data.detail || '保存首次配置状态失败');
    appConfig = mergeAppConfig(APP_CONFIG_DEFAULTS, data.config || next);
    broadcastStudioApiChange('app-config-changed');
    renderSetupWizard();
    return appConfig;
}
async function dismissSetupWizard(){
    try {
        await saveSetupState({dismissed_at:new Date().toISOString()});
    } catch(_) {}
    closeSetupWizard();
}
async function completeSetupWizard(){
    try {
        await saveAgentConfig();
        await saveSetupState({completed:true, completed_at:new Date().toISOString()});
        setSetupWizardStatus('首次配置已完成。', 'ok');
        setTimeout(closeSetupWizard, 450);
    } catch(err) {
        setSetupWizardStatus(err.message || '保存首次配置状态失败。', 'error');
    }
}
function focusAgentConfig(){
    closeSetupWizard();
    document.querySelector('.agent-config-block')?.scrollIntoView({behavior:'smooth', block:'start'});
}
function openRecommendApiFromWizard(){
    closeSetupWizard();
    openRecommendApi();
}
async function runSetupAgentTest(){
    setSetupWizardStatus('正在测试 Agent...');
    await testAgentConfig();
    const ok = agentConfigHint?.classList.contains('is-ok');
    if(ok){
        try { await saveSetupState({agent_tested:true}); } catch(_) {}
        setSetupWizardStatus('Agent 测试通过。', 'ok');
    } else {
        setSetupWizardStatus(agentConfigHint?.textContent || 'Agent 测试失败。', 'error');
    }
}
function runSetupStep(action){
    if(action === 'focusAgentConfig') focusAgentConfig();
    if(action === 'openRecommend') openRecommendApiFromWizard();
    if(action === 'testAgent') runSetupAgentTest();
}
function maybeOpenSetupWizard(){
    const url = new URL(location.href);
    if(url.searchParams.get('setup') === '1'){
        openSetupWizard(false);
        return;
    }
    if(appConfig?.setup?.completed === true) return;
    const dismissedAt = appConfig?.setup?.dismissed_at ? Date.parse(appConfig.setup.dismissed_at) : 0;
    const dismissedRecently = dismissedAt && Date.now() - dismissedAt < 24 * 60 * 60 * 1000;
    if(!dismissedRecently && !setupWizardOpened) setTimeout(() => openSetupWizard(true), 250);
}
async function loadAppConfig(){
    if(appConfigLoaded) return appConfig;
    appConfigLoaded = true;
    try {
        const staticConfig = await fetchLocalJson(`/static/app_config.json?v=${Date.now()}`, {cache:'no-store'}, 1800);
        appConfig = mergeAppConfig(APP_CONFIG_DEFAULTS, staticConfig || {});
    } catch(_) {
        appConfig = APP_CONFIG_DEFAULTS;
    }
    try {
        const proxyBase = cleanBaseUrl(appConfig?.proxy?.base_url, APP_CONFIG_DEFAULTS.proxy.base_url);
        const proxyConfig = await fetchLocalJson(`${proxyBase}/app-config?v=${Date.now()}`, {cache:'no-store'}, 1800);
        appConfig = mergeAppConfig(appConfig, proxyConfig || {});
    } catch(_) {}
    ensureAgentRegistry();
    return appConfig;
}
function chatProvidersForAgent(){
    return (providers || []).filter(item =>
        item && item.enabled !== false && !isRunningHubProvider(item)
        && item.id !== 'jimeng' && cleanBaseUrl(item.base_url));
}
function selectedAgentProviderId(){
    const items = chatProvidersForAgent();
    const saved = String(currentAgent()?.provider_id || '').trim();
    if(saved && items.some(item => String(item.id) === saved)) return saved;
    const selected = String(agentProviderSelect?.value || '').trim();
    if(selected && items.some(item => String(item.id) === selected)) return selected;
    return saved || selected || '';
}
function selectedAgentProvider(){
    const pid = selectedAgentProviderId();
    return chatProvidersForAgent().find(item => String(item.id) === pid) || null;
}
function agentProvider(){
    return selectedAgentProvider();
}
function agentProviderKeyEnv(item){
    return item?.key_env || currentAgent()?.api_key_env || 'MYRIDTV_AGENT_API_KEY';
}
function renderAgentProviderOptions(){
    if(!agentProviderSelect) return;
    const allProviders = providers || [];
    const items = chatProvidersForAgent();
    const hintEl = document.getElementById('agentProviderHint');
    const excluded = allProviders.filter(p => p && p.enabled !== false && !items.some(i => String(i.id) === String(p.id)));
    if(hintEl){
        hintEl.textContent = excluded.length
            ? `已自动排除 ${excluded.map(p => p.name || p.id).filter(Boolean).join('、')}：这些是图像/视频工作流平台，不含对话模型；Agent 只能选 OpenAI 兼容的对话平台（可点左侧“+”添加）。`
            : '';
    }
    if(!items.length){
        agentProviderSelect.innerHTML = '<option value="">请先在左侧添加 OpenAI 兼容的对话平台</option>';
        agentProviderSelect.value = '';
        agentProviderSelect.disabled = true;
        return;
    }
    agentProviderSelect.disabled = false;
    agentProviderSelect.innerHTML = items
        .map(item => `<option value="${escapeAttr(item.id)}">${escapeHtml(item.name || item.id)}</option>`)
        .join('');
    const current = selectedAgentProviderId();
    agentProviderSelect.value = items.some(item => String(item.id) === current) ? current : String(items[0].id);
}
function savedAgentModel(){
    return String(currentAgent()?.model || '').trim();
}
function isCodexLocalUpstream(value=''){
    return String(value || '').trim().toLowerCase().replace(/\/+$/, '') === CODEX_LOCAL_UPSTREAM;
}
function agentModelChoices(){
    const configured = savedAgentModel();
    const provider = selectedAgentProvider();
    const providerModels = Array.isArray(provider?.chat_models) ? provider.chat_models : [];
    const savedModels = Array.isArray(currentAgent()?.chat_models) ? currentAgent().chat_models : [];
    return unique([configured, ...providerModels, ...savedModels, ...(agentFetchedModels || [])]).filter(Boolean);
}
function renderAgentModelOptions(){
    if(!agentModelSelect) return;
    const provider = selectedAgentProvider();
    const configured = savedAgentModel();
    const datalist = document.getElementById('agentModelList');
    if(!provider){
        agentModelSelect.disabled = true;
        agentModelSelect.value = '';
        agentModelSelect.placeholder = '请先选择 LLM平台';
        if(datalist) datalist.innerHTML = '';
        return;
    }
    agentModelSelect.disabled = false;
    const models = agentModelChoices();
    if(datalist){
        datalist.innerHTML = models.length
            ? models.map(model => `<option value="${escapeAttr(model)}">${escapeHtml(model)}</option>`).join('')
            : '';
    }
    const current = String(agentModelSelect.value || '').trim();
    if(current) {
        // 保留用户正在输入的值
    } else if(configured) {
        agentModelSelect.value = configured;
    } else if(models.length) {
        agentModelSelect.value = models[0];
    }
    agentModelSelect.placeholder = models.length
        ? '可从下拉选择或直接输入模型名'
        : '该平台未提供模型列表，请直接输入模型名，如 deepseek-v4-flash';
}
function visionModelName(){
    const fromInput = String(document.getElementById('visionModelSelect')?.value || '').trim();
    if(fromInput) return fromInput;
    return String(appConfig?.vision?.model || '').trim() || 'glm-4v-flash';
}
function visionEnabledState(){
    const check = document.getElementById('visionEnabledCheck');
    if(check) return Boolean(check.checked);
    return appConfig?.vision?.enabled !== false;
}
function syncVisionDisplayName(){
    try{
        if(typeof renderAgentList === 'function') renderAgentList();
        if(typeof isAgentPanelSelection === 'function' && isAgentPanelSelection()){
            const displayName = visionModelName();
            if(editorTitle) editorTitle.textContent = displayName;
            const blockTitle = document.getElementById('agentBlockTitle');
            if(blockTitle) blockTitle.textContent = displayName;
        }
    }catch(_){}
}
async function loadVisionConfig(){
    try{
        const proxyBase = cleanBaseUrl(appConfig?.proxy?.base_url, APP_CONFIG_DEFAULTS.proxy.base_url);
        const res = await fetch(`${proxyBase}/api/canvas-agent-config?v=${Date.now()}`, {cache:'no-store'});
        if(!res.ok) return;
        const data = await res.json();
        const v = data?.vision || {};
        const enabledCheck = document.getElementById('visionEnabledCheck');
        const modelSel = document.getElementById('visionModelSelect');
        const baseInput = document.getElementById('visionBaseInput');
        const keyInput = document.getElementById('visionKeyInput');
        if(enabledCheck) enabledCheck.checked = v.enabled !== false;
        if(modelSel && v.model) modelSel.value = v.model;
        if(baseInput && v.base_url) baseInput.value = v.base_url;
        if(keyInput){
            keyInput.value = '';
            keyInput.placeholder = v.has_key ? '已保存 Key，输入新值可替换' : '留空则用环境变量 GLM_API_KEY';
        }
        appConfig = mergeAppConfig(appConfig, {vision:{enabled: v.enabled !== false, model: v.model || 'glm-4v-flash', base_url: v.base_url || ''}});
        syncVisionDisplayName();
    }catch(_){}
}
async function saveVisionConfig(){
    const hint = document.getElementById('visionSaveHint');
    try{
        const proxyBase = cleanBaseUrl(appConfig?.proxy?.base_url, APP_CONFIG_DEFAULTS.proxy.base_url);
        const enabled = document.getElementById('visionEnabledCheck')?.checked !== false;
        const model = document.getElementById('visionModelSelect')?.value || 'glm-4v-flash';
        const baseUrl = document.getElementById('visionBaseInput')?.value?.trim() || 'https://open.bigmodel.cn/api/paas/v4';
        const apiKey = document.getElementById('visionKeyInput')?.value?.trim() || '';
        const body = {vision:{enabled, model, base_url:baseUrl}};
        if(apiKey) body.vision.api_key = apiKey;
        const res = await fetch(`${proxyBase}/api/canvas-agent-config`, {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify(body)
        });
        if(!res.ok) throw new Error('HTTP ' + res.status);
        appConfig = mergeAppConfig(appConfig, {vision:{enabled, model, base_url:baseUrl}});
        syncVisionDisplayName();
        if(hint) hint.textContent = '已保存：视觉识别 ' + (enabled ? `开启（${model}）` : '关闭') + (apiKey ? '，已更新 Key' : '');
    }catch(e){
        if(hint) hint.textContent = '保存失败：' + (e?.message || e);
    }
}
function renderAgentConfig(){
    loadVisionConfig();
    ensureAgentRegistry();
    if(!agentModelSelect) return;
    renderAgentProviderOptions();
    renderAgentModelOptions();
    if(agentProxyBaseInput) agentProxyBaseInput.value = cleanBaseUrl(appConfig?.proxy?.base_url, APP_CONFIG_DEFAULTS.proxy.base_url);
    const itemModel = currentAgent();
    const provider = selectedAgentProvider();
    const agentName = itemModel?.name || selectedAgentFromPanel() || 'Agent';
    const model = agentModelSelect.value || itemModel?.model || '';
    const providerLabel = provider ? (provider.name || provider.id) : '';
    setAgentConfigHint(provider && model
        ? `当前 Agent：${agentName} / ${providerLabel} / ${model}`
        : provider
            ? `当前 Agent：${agentName} / ${providerLabel}（未选择模型）`
            : `当前 Agent：${agentName}（未选择 LLM 平台）`);
    if(agentModelSourceHint){
        agentModelSourceHint.textContent = !provider
            ? ''
            : (agentModelsFetched
                ? `模型来源：已从平台「${providerLabel}」实时拉取 ${(agentFetchedModels || []).length} 个模型；请求地址和 API Key 复用该平台配置。`
                : `模型来源：平台「${providerLabel}」已保存的模型列表；请求地址和 API Key 复用该平台配置，可点右上角“拉取模型”刷新。`);
    }
}
function handleAgentProviderChange(){
    const aid = selectedAgentFromPanel();
    const pid = String(agentProviderSelect?.value || '').trim();
    appConfig = mergeAppConfig(appConfig, {agent:{agents:{[aid]:{provider_id:pid, model:'', chat_models:[]}}}});
    agentFetchedModels = [];
    agentModelsFetched = false;
    renderAgentConfig();
}
function collectAgentConfigFromForm(){
    ensureAgentRegistry();
    const aid = selectedAgentFromPanel();
    const item = currentAgent() || {};
    const proxyBase = cleanBaseUrl(agentProxyBaseInput?.value, APP_CONFIG_DEFAULTS.proxy.base_url);
    const providerId = String(agentProviderSelect?.value || item.provider_id || '').trim();
    const model = String(agentModelSelect?.value || item.model || '').trim();
    const nextAgents = {...agentRegistry()};
    nextAgents[aid] = {
        ...(nextAgents[aid] || {}),
        name: item.name || aid,
        provider_id:providerId,
        model,
        preferred_model_pattern:'',
        upstream_base_url:'',
        api_key_env:item.api_key_env || agentProviderKeyEnv(item),
        fallback_api_key_env:item.fallback_api_key_env || 'API_PROVIDER_CUSTOM_API_KEY',
        chat_models: agentFetchedModels.length
            ? agentFetchedModels
            : (Array.isArray(item.chat_models) ? item.chat_models : (Array.isArray(nextAgents[aid]?.chat_models) ? nextAgents[aid].chat_models : []))
    };
    return mergeAppConfig(appConfig, {
        proxy:{base_url:proxyBase, port:Number((proxyBase.match(/:(\d+)(?:\/)?$/) || [])[1]) || appConfig?.proxy?.port || 3107},
        agent:{ active_id:aid, agents:nextAgents }
    });
}
async function saveAgentConfig(){
    if(!agentSaveBtn) return false;
    const nextConfig = collectAgentConfigFromForm();
    nextConfig.vision = {
        enabled: document.getElementById('visionEnabledCheck')?.checked !== false,
        model: document.getElementById('visionModelSelect')?.value || 'glm-4v-flash',
        base_url: document.getElementById('visionBaseInput')?.value?.trim() || 'https://open.bigmodel.cn/api/paas/v4'
    };
    const visionKey = document.getElementById('visionKeyInput')?.value?.trim();
    if(visionKey) nextConfig.vision.api_key = visionKey;
    const aid = selectedAgentFromPanel();
    const nextEntry = nextConfig?.agent?.agents?.[aid] || {};
    if(!String(nextEntry.provider_id || '').trim()){
        setAgentConfigHint('请先选择 LLM平台。', 'error');
        return false;
    }
    if(!String(nextEntry.model || '').trim()){
        setAgentConfigHint('请先点击右上角“拉取模型”，再选择模型。', 'error');
        return false;
    }
    const proxyBase = cleanBaseUrl(nextConfig?.proxy?.base_url, APP_CONFIG_DEFAULTS.proxy.base_url);
    agentSaveBtn.disabled = true;
    setAgentConfigHint('正在保存 Agent 配置...');
    try {
        const res = await fetch(`${proxyBase}/app-config`, {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify(nextConfig)
        });
        const data = await res.json().catch(() => ({}));
        if(!res.ok || data.ok === false) throw new Error(data.detail || '保存 Agent 配置失败');
        appConfig = mergeAppConfig(APP_CONFIG_DEFAULTS, data.config || nextConfig);
        renderAgentConfig();
        renderSetupWizard();
        setAgentConfigHint('Agent 配置已保存，画布会复用所选 LLM 平台的请求地址和 API Key。', 'ok');
        broadcastStudioApiChange('app-config-changed');
        return true;
    } catch(err) {
        setAgentConfigHint(err.message || '保存 Agent 配置失败，请确认 3107 代理已启动。', 'error');
        return false;
    } finally {
        agentSaveBtn.disabled = false;
    }
}
async function saveAgentKeyOnly(){
    if(!agentKeyInput) return false;
    const apiKey = String(agentKeyInput.value || '').trim();
    if(!apiKey){
        setAgentConfigHint('请输入 Agent API Key', 'error');
        return false;
    }
    const proxyBase = cleanBaseUrl(appConfig?.proxy?.base_url, APP_CONFIG_DEFAULTS.proxy.base_url);
    const keyEnv = String(currentAgent()?.api_key_env || APP_CONFIG_DEFAULTS.agent.agents?.codex?.api_key_env || 'MYRIDTV_AGENT_API_KEY').trim();
    try {
        const res = await fetch(`${proxyBase}/api/agent-key`, {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({ api_key:apiKey, key_env:keyEnv })
        });
        const data = await res.json().catch(() => ({}));
        if(!res.ok || data.ok === false) throw new Error(data.detail || '保存 Agent Key 失败');
        appConfig = mergeAppConfig(appConfig, { agent:data.agent || {} });
        renderAgentConfig();
        setAgentConfigHint('Agent Key 已保存。', 'ok');
        return true;
    } catch(err){
        setAgentConfigHint(err.message || '保存 Agent Key 失败', 'error');
        return false;
    }
}
async function clearAgentKeyOnly(){
    const proxyBase = cleanBaseUrl(appConfig?.proxy?.base_url, APP_CONFIG_DEFAULTS.proxy.base_url);
    const keyEnv = String(currentAgent()?.api_key_env || APP_CONFIG_DEFAULTS.agent.agents?.codex?.api_key_env || 'MYRIDTV_AGENT_API_KEY').trim();
    try {
        const res = await fetch(`${proxyBase}/api/agent-key`, {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({ clear:true, key_env:keyEnv })
        });
        const data = await res.json().catch(() => ({}));
        if(!res.ok || data.ok === false) throw new Error(data.detail || '清除 Agent Key 失败');
        appConfig = mergeAppConfig(appConfig, { agent:data.agent || {} });
        renderAgentConfig();
        setAgentConfigHint('Agent Key 已清除。', 'ok');
        return true;
    } catch(err){
        if(agentKeyHint) agentKeyHint.textContent = err.message || '清除 Agent Key 失败';
        setAgentConfigHint(err.message || '清除 Agent Key 失败', 'error');
        return false;
    }
}
async function testAgentConfig(){
    const saved = await saveAgentConfig();
    if(!saved) return;
    const proxyBase = cleanBaseUrl(appConfig?.proxy?.base_url, APP_CONFIG_DEFAULTS.proxy.base_url);
    if(agentTestBtn) agentTestBtn.disabled = true;
    setAgentConfigHint('正在测试 Agent 对话...');
    const payload = {
        agent_id:selectedAgentFromPanel(),
        provider:currentAgent()?.provider_id,
        model:currentAgent()?.model,
        message:'请只回复 ok，用于测试 MyridTV Agent 连接。'
    };
    const requestAgent = async endpoint => {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 45000);
        try {
            const res = await fetch(endpoint, {
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify(payload),
                signal:controller.signal
            });
            const data = await res.json().catch(() => ({}));
            if(!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
            return data;
        } catch(error) {
            throw error?.name === 'AbortError' ? new Error('Agent 测试超时，上游模型暂时没有响应。') : error;
        } finally {
            clearTimeout(timer);
        }
    };
    try {
        let data;
        try {
            data = await requestAgent(`${proxyBase}/api/canvas-llm`);
        } catch(primaryError) {
            try {
                data = await requestAgent('/api/canvas-llm');
            } catch(fallbackError) {
                throw primaryError;
            }
        }
        const text = String(data.text || '').trim();
        setAgentConfigHint(`Agent 测试通过：${text || '已收到回复'}`, 'ok');
    } catch(err) {
        setAgentConfigHint(err.message || 'Agent 测试失败，请检查平台 Key、模型和上游地址。', 'error');
    } finally {
        if(agentTestBtn) agentTestBtn.disabled = false;
    }
}
function rhEditorSideScrollEl(){
    return rhWorkflowEditorNodeList?.closest?.('.rh-workflow-editor-side') || rhWorkflowEditorNodeList;
}
function captureRhEditorScrollState(){
    const pop = document.getElementById('rhNodePopover');
    const popBody = pop?.querySelector?.('.rh-popover-body');
    const side = rhEditorSideScrollEl();
    return {
        sideTop:side?.scrollTop || 0,
        nodeListTop:rhWorkflowEditorNodeList?.scrollTop || 0,
        graphTop:rhWorkflowEditorGraphWrap?.scrollTop || 0,
        popNodeId:pop?.dataset?.nodeId || '',
        popFieldKey:pop?.dataset?.fieldKey || '',
        popBodyTop:popBody?.scrollTop || 0
    };
}
function restoreRhEditorScrollState(state){
    if(!state) return;
    const restore = () => {
        const side = rhEditorSideScrollEl();
        if(side) side.scrollTop = state.sideTop || 0;
        if(rhWorkflowEditorNodeList) rhWorkflowEditorNodeList.scrollTop = state.nodeListTop || 0;
        if(rhWorkflowEditorGraphWrap) rhWorkflowEditorGraphWrap.scrollTop = state.graphTop || 0;
        const pop = document.getElementById('rhNodePopover');
        const samePopover = pop && (
            (state.popNodeId && pop.dataset.nodeId === state.popNodeId) ||
            (state.popFieldKey && pop.dataset.fieldKey === state.popFieldKey)
        );
        if(samePopover){
            const popBody = pop.querySelector('.rh-popover-body');
            if(popBody) popBody.scrollTop = state.popBodyTop || 0;
        }
    };
    requestAnimationFrame(() => {
        restore();
        requestAnimationFrame(restore);
    });
}
function withRhEditorScrollPreserved(callback){
    const scrollState = captureRhEditorScrollState();
    const result = callback();
    restoreRhEditorScrollState(scrollState);
    return result;
}
function findRhAppFieldCard(key){
    return Array.from(document.querySelectorAll('.rh-app-field-card')).find(el => el.dataset.fieldKey === String(key || ''));
}
function normalizeId(value){
    return String(value || '').trim().toLowerCase().replace(/[^a-z0-9_-]/g, '-').replace(/^-+|-+$/g, '').replace(/-+/g, '-').slice(0, 40);
}
// 平台 Key 按 ID 写入 API/.env；ID 一旦创建就保持稳定，避免改名或中文名称导致 Key 看起来丢失。
function deriveIdFromName(name, existingId){
    if(existingId) return existingId;
    let id = normalizeId(name);
    if(!id){
        id = 'api-' + Math.random().toString(36).slice(2, 8);
    }
    let candidate = id, i = 2;
    while(providers.some(p => p.id === candidate)){
        candidate = `${id}-${i++}`;
    }
    return candidate;
}
function updateIdPreview(){
    const item = provider();
    if(!item) return;
    const isBuiltin = item.id === 'comfly' || item.id === 'modelscope' || item.id === 'runninghub' || item.id === 'volcengine' || item.id === 'jimeng';
    const idPreview = document.getElementById('idPreview');
    if(!idPreview) return;
    if(isBuiltin){
        idPreview.textContent = item.id;
        return;
    }
    idPreview.textContent = deriveIdFromName(nameInput.value, item.id);
}
function provider(){
if(isAgentPanelSelection()) return visibleProviders()[0] || providers[0];
return visibleProviders().find(item => item.id === selectedId) || visibleProviders()[0] || providers[0];
}
async function refreshRunningHubProviderFromApi(renderAfter=true){
if(selectedId !== 'runninghub') return false;
if(rhConfigDirty) return false;
if(rhProviderRefreshInFlight) return false;
rhProviderRefreshInFlight = true;
rhProviderLastRefreshAt = Date.now();
try {
const data = await fetchLocalJson(`/api/providers?v=${Date.now()}`, {cache:'no-store'}, 3000);
const fresh = (data.providers || []).find(item => item?.id === 'runninghub');
const current = providers.find(item => item?.id === 'runninghub');
if(!fresh || !current) return false;
 // rh_apps/rh_workflows 是用户手动粘贴路径创建/删除的，绝不在为空时自动回填内置示例（否则删除会“复活”）。
 current.rh_apps = normalizeRhEntries(current.rh_apps || [], 'app');
 current.rh_workflows = normalizeRhEntries(current.rh_workflows || [], 'workflow');
current.image_models = unique(fresh.image_models || current.image_models || []);
current.chat_models = unique(fresh.chat_models || current.chat_models || []);
current.video_models = unique(fresh.video_models || current.video_models || []);
current.model_display_names = (fresh.model_display_names && typeof fresh.model_display_names === 'object') ? {...fresh.model_display_names} : (current.model_display_names || {});
current.model_protocols = (fresh.model_protocols && typeof fresh.model_protocols === 'object') ? {...fresh.model_protocols} : (current.model_protocols || {});
ensureRunningHubLists(current);
if(renderAfter) renderRunningHubCards();
return true;
} catch(_) {
return false;
} finally {
rhProviderRefreshInFlight = false;
}
}
function isProviderTemporarilyHidden(item){
return false;
}
function visibleProviders(){
    return (providers || []).filter(item => !isProviderTemporarilyHidden(item));
}
function isFixedProvider(itemOrId){
    const id = typeof itemOrId === 'string' ? itemOrId : itemOrId?.id;
    // 即梦 CLI 不再是固定平台：可删除、可排序，未添加则不存在。
    return id === 'modelscope' || id === 'runninghub' || id === 'volcengine';
}
function isRunningHubProvider(item){
  return Boolean(item) && (item.id === 'runninghub' || String(item.protocol || '').toLowerCase() === 'runninghub');
}
function isBuiltinRunningHubProvider(item){
  return Boolean(item) && String(item.id || '').trim() === 'runninghub';
}
function unique(values){
  const seen = new Set();
  return values.map(v => String(v || '').trim()).filter(v => v && !seen.has(v) && seen.add(v));
}
function modelDisplayNameMap(item){
  return (item?.model_display_names && typeof item.model_display_names === 'object') ? item.model_display_names : {};
}
function providerAvailableModelKey(kind){
  return kind === 'image' ? 'available_image_models' : kind === 'video' ? 'available_video_models' : 'available_chat_models';
}
function providerModelValueOptions(item, kind, currentValue){
  const key = kind === 'image' ? 'image_models' : kind === 'video' ? 'video_models' : 'chat_models';
  if(isRunningHubProvider(item) && RH_MODEL_ALIASES?.getRhModelValueOptions){
    return RH_MODEL_ALIASES.getRhModelValueOptions(item?.[providerAvailableModelKey(kind)] || item?.[key] || [], currentValue);
  }
  return unique([String(currentValue || '').trim(), ...((item?.[key]) || [])]).filter(Boolean);
}
function renderModelValueControl(item, kind, index, model){
  if(isRunningHubProvider(item)){
    const options = providerModelValueOptions(item, kind, model);
    const currentValue = String(model || '').trim();
    const emptyOption = currentValue ? '' : '<option value="">请选择模型</option>';
    return `<select class="model-value-input model-value-select" onchange="updateModel('${kind}', ${index}, this.value)">${emptyOption}${options.map(option => `<option value="${escapeAttr(option)}" ${option === currentValue ? 'selected' : ''}>${escapeHtml(option)}</option>`).join('')}</select>`;
  }
  return `<input class="model-value-input" value="${escapeAttr(model)}" oninput="updateModel('${kind}', ${index}, this.value)">`;
}
function repairProviderRhModelAliases(item){
  if(RH_MODEL_ALIASES?.repairProviderRhModelAliases) RH_MODEL_ALIASES.repairProviderRhModelAliases(item);
  return item;
}
function applyDefaultRhModelDisplayNames(item){
  if(!item) return;
  repairProviderRhModelAliases(item);
  const knownModels = new Set([...(item.image_models || []), ...(item.chat_models || []), ...(item.video_models || [])].map(v => String(v || '').trim()).filter(Boolean));
  const next = {...modelDisplayNameMap(item)};
  Object.entries(RH_DEFAULT_MODEL_DISPLAY_NAMES).forEach(([model, label]) => {
    if(knownModels.has(model) && !String(next[model] || '').trim()) next[model] = label;
  });
  item.model_display_names = next;
}
function sanitizeModelDisplayNames(item){
  if(!item) return {};
  repairProviderRhModelAliases(item);
  const allowed = new Set([...(item.image_models || []), ...(item.chat_models || []), ...(item.video_models || [])].map(v => String(v || '').trim()).filter(Boolean));
  const result = {};
  Object.entries(modelDisplayNameMap(item)).forEach(([model, label]) => {
    const modelKey = String(model || '').trim();
    const text = String(label || '').trim();
    if(modelKey && text && allowed.has(modelKey)) result[modelKey] = text;
  });
  item.model_display_names = result;
  applyDefaultRhModelDisplayNames(item);
  return item.model_display_names;
}
function normalizeRhEntries(values, kind){
    const seen = new Set();
    return (Array.isArray(values) ? values : []).map(raw => {
        const parsed = parseRunningHubRunRef(raw?.appId || raw?.workflowId || raw?.id || '');
        const id = String(parsed?.id || raw?.id || raw?.appId || raw?.workflowId || '').trim();
        if(!id || seen.has(id)) return null;
        seen.add(id);
        const fallback = kind === 'app' ? `AI 应用 ${id.slice(-6)}` : `工作流 ${id.slice(-6)}`;
        const entry = {
            id,
            title:String(raw?.title || raw?.name || fallback).trim(),
            note:String(raw?.note || raw?.description || '').trim(),
            thumbnail:String(raw?.thumbnail || '').trim(),
            enabled:raw?.enabled !== false
        };
        if(raw?.hidden === true) entry.hidden = true;
        if(Array.isArray(raw?.fields)) entry.fields = raw.fields.map(normalizeRhWorkflowField);
        if(raw?.workflowJson && typeof raw.workflowJson === 'object') entry.workflowJson = raw.workflowJson;
        if(raw?.raw && typeof raw.raw === 'object') entry.raw = raw.raw;
        const updatedAt = Number(raw?.updatedAt || 0);
        if(updatedAt > 0) entry.updatedAt = updatedAt;
        if(kind === 'app') entry.appId = id;
        else {
            entry.workflowId = id;
            entry.optionalImageMode = String(raw?.optionalImageMode || 'prune-workflow');
        }
        return entry;
    }).filter(Boolean);
}
function parseRunningHubRunRef(value){
    const text = String(value || '').trim();
    const match = text.match(/\/run\/(ai-app|workflow)\/([0-9A-Za-z_-]+)/i);
    if(match) return { type:match[1].toLowerCase() === 'ai-app' ? 'app' : 'workflow', id:match[2] };
    const numeric = text.match(/^[0-9]{8,}$/);
    if(numeric) return { type:'workflow', id:text };
    return null;
}
function workflowNodeTitle(node){
    return (node?._meta?.title || node?.class_type || node?._class || node?.type || 'Node').toString();
}
function workflowNodeClass(node){
    return (node?.class_type || node?._class || node?.type || '').toString();
}
function workflowNodeCategory(node){
    const text = `${workflowNodeTitle(node)} ${workflowNodeClass(node)}`.toLowerCase();
    if(/text|prompt|clip/.test(text)) return 'prompt';
    if(/lora/.test(text)) return 'lora';
    if(/ksampler|k sampler|sampler|scheduler|guid|cfg/.test(text)) return 'sampler';
    if(/video|movie|mp4|webm|frame/.test(text)) return 'video';
    if(/audio|sound|voice|music|wav|mp3/.test(text)) return 'audio';
    if(/image|mask|resize|scale|crop|photo|picture|preview|save/.test(text)) return 'image';
    return 'misc';
}
function rhWorkflowFieldKey(field){
    return `${field?.nodeId || ''}::${field?.fieldName || ''}`;
}
function rhWorkflowFieldKind(field){
    const type = String(field?.fieldType || '').toUpperCase();
    if(['IMAGE','VIDEO','AUDIO','BOOLEAN','NUMBER','FLOAT','INT','INTEGER','TEXT','SLIDER'].includes(type)){
        if(type === 'FLOAT' || type === 'INT' || type === 'INTEGER') return 'NUMBER';
        return type;
    }
    const key = `${field?.fieldName || ''} ${field?.fieldValue || ''}`.toLowerCase();
    if(/image|img|mask|png|jpg|jpeg|webp/.test(key)) return 'IMAGE';
    if(/video|mp4|webm|mov/.test(key)) return 'VIDEO';
    if(/audio|wav|mp3|voice|sound/.test(key)) return 'AUDIO';
    if(/true|false/.test(key)) return 'BOOLEAN';
    if(/^-?\d+(\.\d+)?$/.test(String(field?.fieldValue || '').trim())) return 'NUMBER';
    return 'TEXT';
}
function rhWorkflowFieldTypeLabel(type){
    return ({
        TEXT:'文本',
        NUMBER:'数字',
        SLIDER:'滑块',
        BOOLEAN:'开关',
        SELECT:'下拉',
        IMAGE:'图片',
        VIDEO:'视频',
        AUDIO:'音频'
    })[String(type || '').toUpperCase()] || type;
}
const RH_EDITOR_KNOWN_FIELD_OPTIONS = {
    sampler_name:['euler','euler_ancestral','heun','dpm_2','dpm_2_ancestral','lms','dpmpp_2m','dpmpp_sde','ddim','uni_pc'],
    sampler:['euler','euler_ancestral','heun','dpm_2','dpm_2_ancestral','lms','dpmpp_2m','dpmpp_sde','ddim','uni_pc'],
    scheduler:['normal','karras','exponential','sgm_uniform','simple','ddim_uniform','beta'],
    ratio:['1:1','16:9','9:16','21:9','9:21','4:3','3:4','4:5','5:4','3:2','2:3'],
    aspectRatio:['1:1','16:9','9:16','4:3','3:4','4:5','5:4','3:2','2:3'],
    resolution:['512','768','1024','1280','1536','2048','1k','2k','4k'],
    size:['512','768','1024','1280','1536','2048'],
    ckpt_name:[],
    unet_name:[],
    lora_name:[]
};
function rhKnownOptionsForField(field){
    const name = String(field?.fieldName || '').trim();
    if(!name) return [];
    if(RH_EDITOR_KNOWN_FIELD_OPTIONS[name]) return RH_EDITOR_KNOWN_FIELD_OPTIONS[name].map(String);
    const hit = Object.keys(RH_EDITOR_KNOWN_FIELD_OPTIONS).find(key => key.toLowerCase() === name.toLowerCase());
    return hit ? RH_EDITOR_KNOWN_FIELD_OPTIONS[hit].map(String) : [];
}
function normalizeRhWorkflowField(field){
    const options = Array.isArray(field?.options)
        ? field.options.map(option => String(option ?? '').trim()).filter(Boolean)
        : String(field?.options || '').split(/\r?\n|,/).map(option => option.trim()).filter(Boolean);
    const knownOptions = options.length ? options : rhKnownOptionsForField(field);
    const fieldType = String(field?.fieldType || rhWorkflowFieldKind(field));
    const normalizedType = fieldType.toUpperCase();
    const savedSource = field?.sourceFromUpstream;
    return {
        id:String(field?.id || rhWorkflowFieldKey(field)),
        nodeId:String(field?.nodeId || ''),
        fieldName:String(field?.fieldName || ''),
        fieldValue:field?.fieldValue == null ? '' : String(field.fieldValue),
        fieldType:knownOptions.length && !['IMAGE','VIDEO','AUDIO','SLIDER'].includes(normalizedType) ? 'SELECT' : fieldType,
        label:String(field?.label || field?.fieldName || ''),
        enabled:field?.enabled === true,
        sourceFromUpstream:savedSource === undefined ? false : savedSource !== false,
        group:String(field?.group || ''),
        note:String(field?.note || ''),
        options:knownOptions,
        random_enabled:field?.random_enabled === true,
        min:field?.min ?? '',
        max:field?.max ?? '',
        step:field?.step ?? '',
        imageOrder:Number(field?.imageOrder || field?.image_order || 0) || 0,
        required:field?.required === true
    };
}
function normalizeFetchedRhWorkflowField(field){
    return {...normalizeRhWorkflowField(field), enabled:false};
}
function rhWorkflowGroupKey(field){
    return `${field?.nodeId || ''}::${field?.group || ''}`;
}
function rhEditorSortedFields(fields){
    return [...(fields || [])].sort((a, b) => {
        const ak = rhWorkflowFieldKind(a);
        const bk = rhWorkflowFieldKind(b);
        if(ak === 'IMAGE' && bk === 'IMAGE'){
            const ao = Number(a.imageOrder) || 9999;
            const bo = Number(b.imageOrder) || 9999;
            if(ao !== bo) return ao - bo;
        }
        if(ak === 'IMAGE' && bk !== 'IMAGE') return -1;
        if(ak !== 'IMAGE' && bk === 'IMAGE') return 1;
        return String(a.nodeId || '').localeCompare(String(b.nodeId || ''), undefined, {numeric:true}) || String(a.fieldName || '').localeCompare(String(b.fieldName || ''));
    });
}
function rhFreeKeyHintText(item){
    return item?.has_key ? `${tr('api.rhCoinKeySaved')}${item.key_env || 'API/.env'} ${item.key_preview || ''}` : tr('api.rhNoCoinKey');
}
function rhWalletKeyHintText(item){
    return item?.has_wallet_key ? `${tr('api.rhWalletKeySaved')}${item.wallet_key_env || 'API/.env'} ${item.wallet_key_preview || ''}` : tr('api.rhNoWalletKey');
}
function volcengineArkKeyHintText(item){
    return item?.has_key ? `方舟 API Key 已保存：${item.key_env || 'API/.env'} ${item.key_preview || ''}` : '还没有保存方舟 API Key。';
}
function volcengineAssetKeyHintText(item){
    const ak = item?.has_volcengine_access_key ? `AK 已保存：${item.volcengine_access_key_env || 'API/.env'} ${item.volcengine_access_key_preview || ''}` : 'AK 未保存';
    const sk = item?.has_volcengine_secret_key ? `SK 已保存：${item.volcengine_secret_key_env || 'API/.env'} ${item.volcengine_secret_key_preview || ''}` : 'SK 未保存';
    return `${ak} · ${sk}`;
}
function isNewUserProvider(item){
    if(!item) return false;
    if(item.id === 'modelscope') return !item.has_key;
    if(isRunningHubProvider(item)) return !item.has_key && !item.has_wallet_key;
    return false;
}
function renderProviderOnboarding(item){
    if(!providerOnboardingCard) return;
    const guide = ONBOARDING_GUIDES[item?.id];
    const visible = Boolean(!recommendInlineOpen && guide && isNewUserProvider(item));
    providerOnboardingCard.hidden = !visible;
    document.body.classList.toggle('show-provider-onboarding', visible);
    if(!visible){
        providerOnboardingCard.innerHTML = '';
        return;
    }
    if(item.id === 'modelscope'){
        providerOnboardingCard.innerHTML = `
            <div class="onboarding-head">
                <div>
                    <div class="onboarding-title">${escapeHtml(tr(guide.titleKey))}</div>
                    <div class="onboarding-desc">${escapeHtml(tr(guide.descKey))}</div>
                </div>
                <span class="onboarding-badge">${escapeHtml(tr('api.onboardingNew'))}</span>
            </div>
            <div class="onboarding-step-panel onboarding-rh-linear-panel onboarding-ms-linear-panel">
                <div class="onboarding-rh-panel-head">
                    <div>
                        <div class="onboarding-step-title">${escapeHtml(tr('api.msOnboardingStep'))}</div>
                    </div>
                    <i data-lucide="key-round" class="onboarding-rh-icon w-4 h-4"></i>
                </div>
                <div class="onboarding-rh-linear-rows">
                    <div class="onboarding-rh-linear-row onboarding-ms-linear-row">
                        <div class="onboarding-rh-source-group">
                            <div class="onboarding-rh-source-label">${escapeHtml(tr('api.msTokenLabel'))}</div>
                            <div class="onboarding-key-actions onboarding-rh-key-actions">
                                <a class="onboarding-key-btn" href="${escapeAttr(guide.primaryUrl)}" target="_blank" rel="noopener noreferrer"><i data-lucide="key-round" class="w-3.5 h-3.5"></i><span>${escapeHtml(tr(guide.primaryLabelKey))}</span></a>
                                <a class="onboarding-key-btn" href="${escapeAttr(guide.secondaryUrl)}" target="_blank" rel="noopener noreferrer"><i data-lucide="globe-2" class="w-3.5 h-3.5"></i><span>${escapeHtml(tr(guide.secondaryLabelKey))}</span></a>
                            </div>
                        </div>
                        <div class="recommend-flow-arrow onboarding-flow-arrow onboarding-rh-row-arrow" aria-hidden="true"><span></span><b></b></div>
                        <label class="onboarding-key-field onboarding-rh-row-field">
                            <span>API Key</span>
                            <input type="password" value="${escapeAttr(keyInput?.value || '')}" placeholder="${escapeAttr(tr('api.msTokenPlaceholder'))}" oninput="syncOnboardingKeyInput('standard', this.value)">
                        </label>
                    </div>
                </div>
                <div class="onboarding-rh-save-line">
                    <button class="onboarding-save-btn onboarding-rh-save-all" type="button" onclick="saveKeyOnly()"><i data-lucide="check" class="w-3.5 h-3.5"></i><span>${escapeHtml(tr('api.save'))}</span></button>
                </div>
            </div>
        `;
        refreshIcons();
        return;
    }
    if(item.id === 'runninghub'){
        providerOnboardingCard.innerHTML = `
            <div class="onboarding-head">
                <div>
                    <div class="onboarding-title">${escapeHtml(tr(guide.titleKey))}</div>
                    <div class="onboarding-desc">${escapeHtml(tr(guide.descKey))}</div>
                </div>
                <span class="onboarding-badge">${escapeHtml(tr('api.onboardingNew'))}</span>
            </div>
            <div class="onboarding-step-panel onboarding-rh-linear-panel">
                <div class="onboarding-rh-panel-head">
                    <div>
                        <div class="onboarding-step-title">${escapeHtml(tr('api.rhOnboardingStep'))}</div>
                    </div>
                    <i data-lucide="key-round" class="onboarding-rh-icon w-4 h-4"></i>
                </div>
                <div class="onboarding-rh-linear-rows">
                    <div class="onboarding-rh-linear-row">
                        <div class="onboarding-rh-source-group">
                            <div class="onboarding-rh-source-label">${escapeHtml(tr('api.rhCoinKey'))}</div>
                            <div class="onboarding-key-actions onboarding-rh-key-actions">
                                <a class="onboarding-key-btn" href="${escapeAttr(guide.primaryUrl)}" target="_blank" rel="noopener noreferrer"><i data-lucide="coins" class="w-3.5 h-3.5"></i><span>${escapeHtml(tr(guide.primaryLabelKey))}</span></a>
                                <a class="onboarding-key-btn" href="${escapeAttr(guide.secondaryUrl)}" target="_blank" rel="noopener noreferrer"><i data-lucide="globe-2" class="w-3.5 h-3.5"></i><span>${escapeHtml(tr(guide.secondaryLabelKey))}</span></a>
                            </div>
                        </div>
                        <div class="recommend-flow-arrow onboarding-flow-arrow onboarding-rh-row-arrow" aria-hidden="true"><span></span><b></b></div>
                        <label class="onboarding-key-field onboarding-rh-row-field">
                            <span>${escapeHtml(tr('api.rhCoinApiKeyRequired'))}</span>
                            <input type="password" value="${escapeAttr(rhFreeKeyInput?.value || '')}" placeholder="${escapeAttr(tr('api.rhCoinPlaceholder'))}" oninput="syncOnboardingKeyInput('free', this.value)">
                        </label>
                    </div>
                    <div class="onboarding-rh-linear-row">
                        <div class="onboarding-rh-source-group">
                            <div class="onboarding-rh-source-label">${escapeHtml(tr('api.rhWalletKey'))}</div>
                            <div class="onboarding-key-actions onboarding-rh-key-actions">
                                <a class="onboarding-key-btn" href="${escapeAttr(guide.walletPrimaryUrl)}" target="_blank" rel="noopener noreferrer"><i data-lucide="wallet" class="w-3.5 h-3.5"></i><span>${escapeHtml(tr(guide.walletPrimaryLabelKey))}</span></a>
                                <a class="onboarding-key-btn" href="${escapeAttr(guide.walletSecondaryUrl)}" target="_blank" rel="noopener noreferrer"><i data-lucide="globe-2" class="w-3.5 h-3.5"></i><span>${escapeHtml(tr(guide.walletSecondaryLabelKey))}</span></a>
                            </div>
                        </div>
                        <div class="recommend-flow-arrow onboarding-flow-arrow onboarding-rh-row-arrow" aria-hidden="true"><span></span><b></b></div>
                        <label class="onboarding-key-field onboarding-rh-row-field">
                            <span>${escapeHtml(tr('api.rhWalletApiKeyOptional'))}</span>
                            <input type="password" value="${escapeAttr(rhWalletKeyInput?.value || '')}" placeholder="${escapeAttr(tr('api.rhWalletPlaceholder'))}" oninput="syncOnboardingKeyInput('wallet', this.value)">
                        </label>
                    </div>
                </div>
                <div class="onboarding-rh-save-line">
                    <button class="onboarding-save-btn onboarding-rh-save-all" type="button" onclick="saveOnboardingRunningHubKey()"><i data-lucide="check" class="w-3.5 h-3.5"></i><span>${escapeHtml(tr('api.save'))}</span></button>
                </div>
            </div>
        `;
        refreshIcons();
    }
}
function syncOnboardingKeyInput(kind, value){
    if(kind === 'free' && rhFreeKeyInput) rhFreeKeyInput.value = value || '';
    else if(kind === 'wallet' && rhWalletKeyInput) rhWalletKeyInput.value = value || '';
    else if(keyInput) keyInput.value = value || '';
}
async function saveOnboardingRunningHubKey(){
    const freeKey = rhFreeKeyInput?.value.trim() || '';
    if(!freeKey){ alert(tr('api.rhEnterCoinAlert')); return; }
    const item = provider();
    if(!isRunningHubProvider(item)) return;
    syncEditor();
    const ok = await saveProviders();
    if(ok){
        if(rhFreeKeyInput) rhFreeKeyInput.value = '';
        if(rhWalletKeyInput) rhWalletKeyInput.value = '';
    }
}
function applyProviderOnboardingDefaults(id){
    const item = providers.find(provider => provider.id === id);
    if(!item) return;
    if(id === 'modelscope'){
        item.base_url = MS_DEFAULT_BASE_URL;
        item.protocol = 'openai';
        item.image_models = unique([...MS_BUILTIN_IMAGE_MODELS, ...(item.image_models || [])]);
        item.chat_models = unique([...(item.chat_models || [])]);
        item.ms_defaults_version = Math.max(3, Number(item.ms_defaults_version || 0));
    } else if(id === 'runninghub'){
        item.base_url = RH_DEFAULT_BASE_URL;
        item.protocol = 'runninghub';
        item.image_models = unique([...(item.image_models || []), ...RH_DEFAULT_IMAGE_MODELS]);
        ensureRunningHubLists(item);
    } else if(id === 'volcengine'){
        item.base_url = VOLCENGINE_DEFAULT_BASE_URL;
        item.protocol = 'volcengine';
        item.video_models = unique([...(item.video_models || []), ...VOLCENGINE_DEFAULT_VIDEO_MODELS]);
        item.volcengine_project_name = item.volcengine_project_name || VOLCENGINE_DEFAULT_PROJECT_NAME;
        item.volcengine_region = item.volcengine_region || VOLCENGINE_DEFAULT_REGION;
    } else if(id === 'jimeng'){
        item.base_url = '';
        item.protocol = 'jimeng';
        item.image_models = unique([...(item.image_models || []).filter(model => !JIMENG_LEGACY_IMAGE_MODELS.has(String(model || '').trim())), ...JIMENG_DEFAULT_IMAGE_MODELS]);
        item.video_models = unique([...(item.video_models || []).filter(model => !JIMENG_LEGACY_VIDEO_MODELS.has(String(model || '').trim())), ...JIMENG_DEFAULT_VIDEO_MODELS]);
    }
    selectedId = item.id;
    renderEditor();
    setStatus('已显示默认配置，填写 Key 后点击保存生效');
}
function refreshProviderOnboarding(){
    renderProviderOnboarding(provider());
    refreshIcons();
}
function syncEditor(){
    if(isAgentPanelSelection()) return;
    const item = provider();
    if(!item) return;
    const oldId = item.id;
    const isBuiltin = item.id === 'comfly' || item.id === 'modelscope' || item.id === 'runninghub' || item.id === 'volcengine' || item.id === 'jimeng';
    // 内置和自定义平台的 ID 都保持稳定；新建时若没有 ID 才生成一次。
    const nextId = isBuiltin ? item.id : deriveIdFromName(nameInput.value, item.id);
    item.id = nextId;
if(oldId !== item.id) selectedId = item.id;
const selectedProtocol = item.id === 'modelscope' ? 'openai' : isRunningHubProvider(item) ? 'runninghub' : item.id === 'volcengine' ? 'volcengine' : item.id === 'jimeng' ? 'jimeng' : (protocolInput?.value || 'openai');
if(isFixedProvider(item)){
const fixedCustomName = nameInput.value.trim();
if(item.id === 'modelscope'){
item.name = fixedCustomName || 'ModelScope';
item.base_url = MS_DEFAULT_BASE_URL;
} else if(item.id === 'runninghub'){
item.name = fixedCustomName || 'RunningHub';
item.base_url = RH_DEFAULT_BASE_URL;
} else if(item.id === 'volcengine'){
item.name = fixedCustomName || '火山引擎';
item.base_url = VOLCENGINE_DEFAULT_BASE_URL;
}
} else {
item.name = nameInput.value.trim() || item.id;
item.base_url = selectedProtocol === 'jimeng' ? '' : baseInput.value.trim();
}
// 固定平台不从协议下拉读取
item.protocol = selectedProtocol;
    item.image_generation_endpoint = '';
    item.image_edit_endpoint = '';
    if(isBuiltinRunningHubProvider(item)){
        item.rh_apps = normalizeRhEntries(item.rh_apps || [], 'app');
        item.rh_workflows = normalizeRhEntries(item.rh_workflows || [], 'workflow');
    } else {
        item.rh_apps = [];
        item.rh_workflows = [];
    }
    const key = keyInput.value.trim();
    if(key) item.api_key = key;
    if(isRunningHubProvider(item)){
        const freeKey = rhFreeKeyInput?.value.trim() || '';
        const walletKey = rhWalletKeyInput?.value.trim() || '';
        if(freeKey) item.api_key = freeKey;
        if(walletKey) item.wallet_api_key = walletKey;
    }
    if(item.id === 'volcengine'){
        const ak = volcAkInput?.value.trim() || '';
        const sk = volcSkInput?.value.trim() || '';
        if(ak) item.volcengine_access_key_id = ak;
        if(sk) item.volcengine_secret_access_key = sk;
        item.volcengine_project_name = (volcProjectInput?.value.trim() || VOLCENGINE_DEFAULT_PROJECT_NAME);
        item.volcengine_region = (volcRegionInput?.value.trim() || VOLCENGINE_DEFAULT_REGION);
    }
}
function ensureRunningHubLists(item){
  if(!item) return;
  if(!isBuiltinRunningHubProvider(item)){
    item.rh_apps = [];
    item.rh_workflows = [];
    return;
  }
  item.rh_apps = normalizeRhEntries(item.rh_apps || [], 'app');
  item.rh_workflows = normalizeRhEntries(item.rh_workflows || [], 'workflow');
  applyDefaultRhModelDisplayNames(item);
}
async function fetchAgentModels(){
    if(!agentFetchModelsBtn) return;
    const proxyBase = cleanBaseUrl(agentProxyBaseInput?.value, APP_CONFIG_DEFAULTS.proxy.base_url);
    const provider = selectedAgentProvider();
    if(!provider){
        setAgentConfigHint('请先选择 LLM平台。', 'error');
        return;
    }
    agentFetchModelsBtn.disabled = true;
    const label = agentFetchModelsBtn.querySelector('span');
    if(label) label.textContent = '拉取中...';
    setAgentConfigHint(`正在从平台「${provider.name || provider.id}」拉取模型...`);
    try {
        const res = await fetch(`${proxyBase}/api/agent-models`, {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({
                provider:String(provider.id || '')
            })
        });
        const data = await res.json().catch(() => ({}));
        if(!res.ok || data.ok === false) throw new Error(data.detail || data.message || '模型拉取失败');
        const fetched = unique(data.chat_models || data.all || []).filter(Boolean);
        agentFetchedModels = fetched.length ? fetched : (agentFetchedModels || []);
        agentModelsFetched = true;
        const aid = selectedAgentFromPanel();
        appConfig = mergeAppConfig(appConfig, {agent:{agents:{[aid]:{chat_models: agentFetchedModels}}}});
        renderAgentModelOptions();
        if(agentModelSourceHint) agentModelSourceHint.textContent =
            data.message
                ? `模型来源：平台「${provider.name || provider.id}」${data.message}`
                : `模型来源：${data.source || provider.base_url || provider.id} · 已拉取 ${agentFetchedModels.length} 个模型`;
        setAgentConfigHint(data.message
            ? `平台「${provider.name || provider.id}」：${data.message}`
            : `已从平台「${provider.name || provider.id}」拉取 ${agentFetchedModels.length} 个模型，请选择或输入模型后保存 Agent。`, 'ok');
    } catch(err){
        agentFetchedModels = [];
        agentModelsFetched = false;
        renderAgentModelOptions();
        setAgentConfigHint(err.message || '模型拉取失败，请检查该平台的请求地址和 API Key。', 'error');
    } finally {
        agentFetchModelsBtn.disabled = false;
        if(label) label.textContent = '拉取模型';
    }
}
function updateProtocolFromInput(){
    const item = provider();
    if(!item || !protocolInput || item.id === 'modelscope' || item.id === 'volcengine' || item.id === 'jimeng') return;
    const value = String(protocolInput.value || 'openai').toLowerCase();
    item.protocol = ['openai', 'apimart', 'gemini', 'runninghub', 'volcengine', 'jimeng'].includes(value) ? value : 'openai';
    if(item.protocol === 'runninghub'){
        item.base_url = baseInput?.value.trim() || item.base_url || RH_DEFAULT_BASE_URL;
        if(item.id === 'runninghub' && !(item.image_models || []).length) item.image_models = [...RH_DEFAULT_IMAGE_MODELS];
        ensureRunningHubLists(item);
    }
    if(item.protocol === 'jimeng') item.base_url = '';
    clearVerifyResult();
    // 协议会改变整个表单（如即梦 CLI 账户面板、默认模型、Key 占位）。renderEditor 是唯一切换这些的入口，
    // 这里复跑一次让面板立即出现；保存并恢复 Key 输入框，避免推荐流程里先填的 Key 被 renderEditor 清空。
    const savedKey = keyInput ? keyInput.value : '';
    renderEditor();
    if(keyInput) keyInput.value = savedKey;
}
function isVolcengineProvider(item){
    return String(item?.protocol || '').toLowerCase() === 'volcengine';
}
function handleRhPasteInput(value){
const parsed = parseRunningHubRunRef(value);
if(parsed) setStatus('已识别 RunningHub 路径，点击右侧创建卡片');
}
let rhConfigDirty = false;
function markRhConfigDirty(message='RunningHub 配置未保存'){
    rhConfigDirty = true;
    if(rhSaveBtn){
        rhSaveBtn.classList.add('dirty');
        const label = rhSaveBtn.querySelector('span');
        if(label) label.textContent = '保存工作流配置 *';
    }
    setStatus(message);
}
function markRhConfigSaved(){
    rhConfigDirty = false;
    if(rhSaveBtn){
        rhSaveBtn.classList.remove('dirty');
        const label = rhSaveBtn.querySelector('span');
        if(label) label.textContent = '保存工作流配置';
    }
}
async function saveRunningHubConfig(){
    const item = provider();
    if(!isBuiltinRunningHubProvider(item)) return false;
    ensureRunningHubLists(item);
    const ok = await saveProviders();
    if(ok) markRhConfigSaved();
    return ok;
}
function createRhEntryFromPaste(){
const item = provider();
    if(!isBuiltinRunningHubProvider(item)) return;
    const parsed = parseRunningHubRunRef(rhPasteInput?.value || '');
    if(!parsed){ setStatus('请粘贴 /run/ai-app/... 或 /run/workflow/...'); return; }
    ensureRunningHubLists(item);
    const listKey = parsed.type === 'app' ? 'rh_apps' : 'rh_workflows';
    const exists = item[listKey].some(entry => entry.id === parsed.id);
    if(!exists){
        item[listKey].unshift({
            id:parsed.id,
            appId:parsed.type === 'app' ? parsed.id : undefined,
            workflowId:parsed.type === 'workflow' ? parsed.id : undefined,
            title:parsed.type === 'app' ? `AI 应用 ${parsed.id.slice(-6)}` : `工作流 ${parsed.id.slice(-6)}`,
            note:'',
            thumbnail:'',
            enabled:true
        });
    }
if(rhPasteInput) rhPasteInput.value = '';
    renderRunningHubCards();
    if(exists) setStatus('这个 RunningHub 项目已经存在');
    else markRhConfigDirty('已创建 RunningHub 卡片，点击“保存工作流配置”生效');
}
function updateRhEntry(kind, index, prop, value){
    const item = provider();
    if(!isBuiltinRunningHubProvider(item)) return;
    const listKey = kind === 'app' ? 'rh_apps' : 'rh_workflows';
    ensureRunningHubLists(item);
    if(!item[listKey][index]) return;
    item[listKey][index][prop] = value;
    if(prop === 'title') markRhConfigDirty('名称已修改，点击“保存工作流配置”生效');
    if(prop === 'note') markRhConfigDirty('备注已修改，点击“保存工作流配置”生效');
}
function removeRhEntry(kind, index){
    const item = provider();
    if(!isBuiltinRunningHubProvider(item)) return;
    const listKey = kind === 'app' ? 'rh_apps' : 'rh_workflows';
    ensureRunningHubLists(item);
    item[listKey].splice(index, 1);
    renderRunningHubCards();
    markRhConfigDirty('已删除 RunningHub 卡片，点击“保存工作流配置”生效');
}
function readFileAsDataUrl(file){
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ''));
        reader.onerror = () => reject(reader.error || new Error('读取图片失败'));
        reader.readAsDataURL(file);
    });
}
function loadImageForThumbnail(src){
    return new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = () => reject(new Error('图片解析失败'));
        img.src = src;
    });
}
async function createRhThumbnailDataUrl(file){
    const original = await readFileAsDataUrl(file);
    try {
        const img = await loadImageForThumbnail(original);
        const maxSide = 360;
        const scale = Math.min(1, maxSide / Math.max(img.naturalWidth || img.width || 1, img.naturalHeight || img.height || 1));
        const width = Math.max(1, Math.round((img.naturalWidth || img.width || 1) * scale));
        const height = Math.max(1, Math.round((img.naturalHeight || img.height || 1) * scale));
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, width, height);
        ctx.drawImage(img, 0, 0, width, height);
        return canvas.toDataURL('image/jpeg', 0.78);
    } catch(e) {
        return original;
    }
}
function pickRhThumbnail(kind, index){
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = async () => {
        const file = input.files?.[0];
        if(!file) return;
        try {
            const thumbnail = await createRhThumbnailDataUrl(file);
            updateRhEntry(kind, index, 'thumbnail', thumbnail);
            renderRunningHubCards();
            setStatus('缩略图已更新，点保存生效');
        } catch(e) {
            alert(e.message || '上传缩略图失败');
        }
    };
    input.click();
}
async function openRhWorkflowEditor(index){
    const item = provider();
    if(!isBuiltinRunningHubProvider(item)) return;
    ensureRunningHubLists(item);
    const entry = item.rh_workflows[index];
    if(!entry) return;
    rhEditorMode = 'workflow';
    rhWorkflowEditorState = { open:true, index, entry, config:null, expanded:{}, activeNodeId:'', graph:{ k:1, x:0, y:0, w:0, h:0 }, pan:null, bound:false, previewParams:{}, previewRunning:false, previewStatus:'', previewOutputs:[] };
    if(rhWorkflowEditorOverlay) rhWorkflowEditorOverlay.classList.add('open');
    renderRhWorkflowEditorLoading('正在加载工作流...');
    refreshIcons();
    try {
        await loadRhWorkflowEditorConfig(entry);
    } catch(e) {
        renderRhWorkflowEditorLoading(e.message || '工作流加载失败');
    }
}
async function openRhAppEditor(index){
    const item = provider();
    if(!isBuiltinRunningHubProvider(item)) return;
    ensureRunningHubLists(item);
    const entry = item.rh_apps[index];
    if(!entry) return;
    rhEditorMode = 'app';
    rhWorkflowEditorState = { open:true, index, entry, config:null, expanded:{}, activeNodeId:'app', graph:{ k:1, x:0, y:0, w:0, h:0 }, pan:null, bound:false, previewParams:{}, previewRunning:false, previewStatus:'', previewOutputs:[] };
    if(rhWorkflowEditorOverlay) rhWorkflowEditorOverlay.classList.add('open');
    renderRhWorkflowEditorLoading('正在加载应用参数...');
    refreshIcons();
    try {
        await loadRhAppEditorConfig(entry);
    } catch(e) {
        renderRhWorkflowEditorLoading(e.message || '应用参数加载失败');
    }
}
function closeRhWorkflowEditor(){
    if(rhWorkflowEditorOverlay) rhWorkflowEditorOverlay.classList.remove('open');
    rhWorkflowEditorState.open = false;
}
function renderRhWorkflowEditorLoading(text){
    if(rhWorkflowEditorTitle) rhWorkflowEditorTitle.textContent = rhWorkflowEditorState.entry?.title || (rhEditorMode === 'app' ? 'RunningHub AI 应用' : 'RunningHub 工作流');
    if(rhWorkflowEditorSub) rhWorkflowEditorSub.textContent = rhEditorMode === 'app'
        ? `/run/ai-app/${rhWorkflowEditorState.entry?.appId || rhWorkflowEditorState.entry?.id || ''}`
        : `/run/workflow/${rhWorkflowEditorState.entry?.workflowId || rhWorkflowEditorState.entry?.id || ''}`;
    if(rhWorkflowEditorSummary) rhWorkflowEditorSummary.innerHTML = `<div class="rh-editor-empty">${escapeHtml(text)}</div>`;
    if(rhWorkflowEditorNodeList) rhWorkflowEditorNodeList.innerHTML = '';
    if(rhEditorMode === 'workflow') {
        restoreRhGraphWrap();
        if(rhWorkflowEditorGraphSvg) rhWorkflowEditorGraphSvg.innerHTML = '';
    } else if(rhWorkflowEditorGraphWrap) {
        rhWorkflowEditorGraphWrap.classList.add('rh-app-field-wrap');
        rhWorkflowEditorGraphWrap.innerHTML = `<div class="rh-editor-empty">${escapeHtml(text)}</div>`;
    }
}
async function loadRhWorkflowEditorConfig(entry){
    let config = null;
    const workflowId = String(entry.workflowId || entry.id || '').trim();
    if(!workflowId) throw new Error('workflowId 为空');
    const existing = await fetch(`/api/runninghub/workflows/${encodeURIComponent(workflowId)}`).then(async r => {
        if(r.status === 404) return null;
        const data = await r.json();
        if(!r.ok) throw new Error(data.detail || '读取工作流配置失败');
        return data.workflow || null;
    });
    if(existing) {
        config = existing;
    } else {
        config = await fetchRhWorkflowEditor(false);
        return config;
    }
    rhWorkflowEditorState.config = normalizeRhWorkflowConfig(config, entry);
    renderRhWorkflowEditor();
    setTimeout(() => rhEditorGraphFit(), 50);
    return rhWorkflowEditorState.config;
}
function normalizeRhWorkflowConfig(config, entry){
    const workflowId = String(config?.workflowId || entry?.workflowId || entry?.id || '').trim();
    const normalized = {
        workflowId,
        title:String(config?.title || entry?.title || workflowId),
        description:String(config?.description || entry?.note || ''),
        fields:(Array.isArray(config?.fields) ? config.fields : []).map(normalizeRhWorkflowField),
        workflowJson:config?.workflowJson || {},
        optionalImageMode:String(config?.optionalImageMode || entry?.optionalImageMode || 'prune-workflow'),
        raw:config?.raw || {}
    };
    return applyRhImageSlotDefaults(normalized);
}
function normalizeRhAppConfig(entry){
    const appId = String(entry?.appId || entry?.id || '').trim();
    return {
        appId,
        title:String(entry?.title || `AI 应用 ${appId.slice(-6)}` || appId),
        description:String(entry?.note || ''),
        fields:(Array.isArray(entry?.fields) ? entry.fields : []).map(normalizeRhWorkflowField),
        raw:entry?.raw || {}
    };
}
function applyRhImageSlotDefaults(config){
    const imageFields = (config.fields || []).filter(field => rhWorkflowFieldKind(field) === 'IMAGE');
    imageFields.forEach((field, index) => {
        if(!Number(field.imageOrder)) field.imageOrder = index + 1;
        if(field.required !== true && field.required !== false) field.required = index === 0;
        if(index === 0 && field.required !== false) field.required = true;
    });
    config.optionalImageMode = config.optionalImageMode || 'prune-workflow';
    return config;
}
function setRhWorkflowOptionalImageMode(value){
    const config = rhWorkflowEditorState.config;
    if(!config || rhEditorMode !== 'workflow') return;
    config.optionalImageMode = value || 'prune-workflow';
    withRhEditorScrollPreserved(() => renderRhMappedPreview());
}
function rhAppFieldSourceList(raw){
    const data = raw?.data && typeof raw.data === 'object' ? raw.data : raw;
    const candidates = [
        data?.nodeInfoList,
        data?.fields,
        data?.inputs,
        data?.inputList,
        data?.formItems,
        data?.forms,
        data?.params,
        data?.parameters,
        data?.apiParams,
        data?.config?.fields,
        data?.webapp?.fields,
        data?.webapp?.inputs
    ];
    for(const candidate of candidates){
        if(Array.isArray(candidate) && candidate.length) return candidate;
        if(candidate && typeof candidate === 'object' && Object.keys(candidate).length){
            return Object.entries(candidate).map(([key, value]) => ({fieldName:key, fieldValue:value}));
        }
    }
    return [];
}
function normalizeFetchedRhAppField(field, index=0){
    const name = field?.fieldName || field?.inputName || field?.name || field?.key || field?.paramName || field?.id || `field_${index + 1}`;
    const nodeId = field?.nodeId || field?.node_id || field?.groupId || 'app';
    let value = field?.fieldValue;
    if(value === undefined) value = field?.defaultValue;
    if(value === undefined) value = field?.value;
    if(value === undefined) value = field?.default;
    if(value === undefined || value === null) value = '';
    if(typeof value === 'object') value = JSON.stringify(value);
    const options = extractRhEditorFieldOptions(field);
    return normalizeRhWorkflowField({
        id:field?.id || `${nodeId}::${name}`,
        nodeId,
        fieldName:name,
        fieldValue:value,
        fieldType:field?.fieldType || field?.type || field?.valueType || (options.length ? 'SELECT' : ''),
        label:field?.label || field?.title || field?.name || name,
        enabled:true,
        group:field?.group || field?.category || field?.title || 'AI 应用参数',
        note:field?.note || field?.description || '',
        options,
        min:field?.min ?? '',
        max:field?.max ?? '',
        step:field?.step ?? ''
    });
}
function extractRhEditorFieldOptions(field){
    const candidates = [field?.options, field?.optionList, field?.values, field?.enum, field?.choices, field?.items, field?.list, field?.selectOptions, field?.fieldData];
    for(const candidate of candidates){
        if(!Array.isArray(candidate) || !candidate.length) continue;
        return candidate.map(item => {
            if(item && typeof item === 'object') return item.value ?? item.label ?? item.name ?? item.title;
            return item;
        }).filter(item => item !== undefined && item !== null).map(String);
    }
    const known = rhKnownOptionsForField(field);
    if(known.length) return known;
    return [];
}
async function loadRhAppEditorConfig(entry){
    const config = normalizeRhAppConfig(entry);
    rhWorkflowEditorState.config = config;
    if(!config.fields.length) await fetchRhAppEditor(false);
    else {
        renderRhWorkflowEditor();
        setTimeout(() => rhEditorGraphFit(), 50);
    }
    return rhWorkflowEditorState.config;
}
async function fetchRhAppEditor(force=false){
    const state = rhWorkflowEditorState;
    const entry = state.entry;
    const appId = String(entry?.appId || entry?.id || '').trim();
    if(!appId) throw new Error('appId 为空');
    if(force) renderRhWorkflowEditorLoading('正在重新拉取...');
    const res = await fetch(`/api/runninghub/app-info?webappId=${encodeURIComponent(appId)}`);
    const data = await res.json();
    if(!res.ok || data.success === false) throw new Error(data.detail || '拉取应用参数失败');
    const fields = rhAppFieldSourceList(data).map(normalizeFetchedRhAppField);
    state.config = {
        appId,
        title:rhWorkflowEditName?.value.trim() || entry.title || `AI 应用 ${appId.slice(-6)}`,
        description:rhWorkflowEditNote?.value.trim() || entry.note || '',
        fields,
        raw:data.data || data
    };
    state.graph = { k:1, x:0, y:0, w:0, h:0 };
    renderRhWorkflowEditor();
    setTimeout(() => rhEditorGraphFit(), 50);
    return state.config;
}
async function fetchRhWorkflowEditor(force=false){
    const state = rhWorkflowEditorState;
    const entry = state.entry;
    if(rhEditorMode === 'app') return fetchRhAppEditor(force);
    if(!entry) return null;
    const workflowId = String(entry.workflowId || entry.id || '').trim();
    if(!workflowId) throw new Error('workflowId 为空');
    if(force) renderRhWorkflowEditorLoading('正在重新拉取...');
    const res = await fetch('/api/runninghub/workflows/fetch', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
            workflowId,
            title:rhWorkflowEditName?.value.trim() || entry.title || workflowId,
            description:rhWorkflowEditNote?.value.trim() || entry.note || ''
        })
    });
    const data = await res.json();
    if(!res.ok || data.success === false) throw new Error(data.detail || '拉取工作流失败');
    state.config = normalizeRhWorkflowConfig({
        workflowId:data.data.workflowId,
        title:data.data.title,
        description:data.data.description,
        fields:(data.data.fields || []).map(normalizeFetchedRhWorkflowField),
        workflowJson:data.data.workflowJson || {},
        optionalImageMode:entry.optionalImageMode || 'prune-workflow',
        raw:data.data.raw || {}
    }, entry);
    state.graph = { k:1, x:0, y:0, w:0, h:0 };
    renderRhWorkflowEditor();
    setTimeout(() => rhEditorGraphFit(), 50);
    return state.config;
}
function updateRhWorkflowEditorMeta(prop, value){
    const config = rhWorkflowEditorState.config;
    if(!config) return;
    if(prop === 'title') config.title = value;
    if(prop === 'description') config.description = value;
    withRhEditorScrollPreserved(() => renderRhMappedPreview());
}
function toggleRhWorkflowEditorGroup(groupId){
    const expanded = rhWorkflowEditorState.expanded;
    expanded[groupId] = expanded[groupId] === false;
    withRhEditorScrollPreserved(() => renderRhWorkflowEditor());
}
function focusRhWorkflowEditorNode(nodeId){
    const state = rhWorkflowEditorState;
    const config = state.config;
    if(!config) return;
    state.activeNodeId = String(nodeId || '');
    (config.fields || []).forEach(field => {
        if(String(field.nodeId) === state.activeNodeId){
            const groupId = rhWorkflowGroupKey(field).replace(/[^a-zA-Z0-9_-]/g, '_');
            state.expanded[groupId] = true;
        }
    });
    withRhEditorScrollPreserved(() => renderRhWorkflowEditor());
}
function openRhWorkflowNodePopover(nodeId, anchorEl){
    const state = rhWorkflowEditorState;
    state.activeNodeId = String(nodeId || '');
    renderRhWorkflowEditorGraph();
    const freshAnchor = Array.from(document.querySelectorAll('.rh-editor-gnode')).find(el => el.dataset.nodeId === state.activeNodeId) || anchorEl;
    renderRhNodePopover(state.activeNodeId, freshAnchor);
}
function closeRhNodePopover(){
    document.getElementById('rhNodePopover')?.remove();
}
function renderRhNodePopover(nodeId, anchorEl){
    closeRhNodePopover();
    const config = rhWorkflowEditorState.config;
    if(!config) return;
    const fields = (config.fields || []).filter(field => String(field.nodeId) === String(nodeId));
    if(!fields.length) return;
    const pop = document.createElement('div');
    pop.id = 'rhNodePopover';
    pop.className = 'rh-node-popover';
    pop.dataset.nodeId = String(nodeId || '');
    const workflowNode = config.workflowJson?.[nodeId] || {};
    const title = (workflowNode?._meta?.title || workflowNode?.class_type || fields[0]?.group || `Node #${nodeId}`).toString();
    pop.innerHTML = `
        <div class="rh-popover-head">
            <div>
                <strong>${escapeHtml(title)}</strong>
                <span>#${escapeHtml(nodeId)} · ${fields.length}</span>
            </div>
            <button type="button" onclick="closeRhNodePopover()"><i data-lucide="x" class="w-3.5 h-3.5"></i></button>
        </div>
        <div class="rh-popover-body">${fields.map(field => renderRhWorkflowEditorField(field)).join('')}</div>
    `;
    document.body.appendChild(pop);
    const rect = anchorEl?.getBoundingClientRect?.();
    const modalRect = rhWorkflowEditorOverlay?.getBoundingClientRect?.() || {left:0, top:0, right:window.innerWidth, bottom:window.innerHeight};
    let left = rect ? rect.right + 12 : window.innerWidth / 2 - 190;
    let top = rect ? rect.top : window.innerHeight / 2 - 180;
    const width = 390;
    if(left + width > modalRect.right - 16) left = Math.max(modalRect.left + 16, (rect?.left || left) - width - 12);
    top = Math.max(modalRect.top + 74, Math.min(top, modalRect.bottom - 420));
    pop.style.left = `${left}px`;
    pop.style.top = `${top}px`;
    refreshIcons();
}
function toggleRhWorkflowEditorField(key){
    const config = rhWorkflowEditorState.config;
    if(!config) return;
    withRhEditorScrollPreserved(() => {
        config.fields = (config.fields || []).map(field => {
            if(rhWorkflowFieldKey(field) !== key) return field;
            return {...field, enabled: field.enabled !== true};
        });
        renderRhWorkflowEditor();
        if(rhEditorMode === 'workflow' && rhWorkflowEditorState.activeNodeId) {
            const active = document.querySelector(`.rh-editor-gnode[data-node-id="${rhWorkflowEditorState.activeNodeId}"]`);
            if(active) renderRhNodePopover(rhWorkflowEditorState.activeNodeId, active);
        } else if(rhEditorMode === 'app') {
            const active = findRhAppFieldCard(key);
            if(active) openRhAppFieldPopover(key, active);
        }
    });
}
function updateRhWorkflowEditorField(key, prop, value){
    const config = rhWorkflowEditorState.config;
    if(!config) return;
    config.fields = (config.fields || []).map(field => {
        if(rhWorkflowFieldKey(field) !== key) return field;
        const nextValue = prop === 'imageOrder' ? Math.max(1, Number(value) || 1) : prop === 'required' ? Boolean(value) : value;
        return {...field, [prop]: nextValue};
    });
    if(prop === 'random_enabled' || prop === 'fieldType' || prop === 'required' || prop === 'sourceFromUpstream'){
        withRhEditorScrollPreserved(() => {
            renderRhWorkflowEditor();
            if(rhEditorMode === 'workflow' && rhWorkflowEditorState.activeNodeId) {
                const active = document.querySelector(`.rh-editor-gnode[data-node-id="${rhWorkflowEditorState.activeNodeId}"]`);
                if(active) renderRhNodePopover(rhWorkflowEditorState.activeNodeId, active);
            } else if(rhEditorMode === 'app') {
                const active = findRhAppFieldCard(key);
                if(active) openRhAppFieldPopover(key, active);
            }
        });
    }
}
function setRhWorkflowSaveButtonState(state, text){
    if(!rhWorkflowSaveBtn) return;
    const label = rhWorkflowSaveBtn.querySelector('span');
    rhWorkflowSaveBtn.classList.toggle('is-saved', state === 'saved');
    rhWorkflowSaveBtn.disabled = state === 'saving';
    if(label) label.textContent = text || (state === 'saved' ? '已保存' : state === 'saving' ? '保存中...' : '保存');
    const icon = rhWorkflowSaveBtn.querySelector('i');
    if(icon) icon.setAttribute('data-lucide', state === 'saved' ? 'check' : 'save');
    refreshIcons();
}
async function saveRhWorkflowEditor(){
    const state = rhWorkflowEditorState;
    const config = state.config;
    if(!config){ alert(rhEditorMode === 'app' ? '请先加载应用参数' : '请先加载工作流'); return; }
    setRhWorkflowSaveButtonState('saving', '保存中...');
    config.title = rhWorkflowEditName?.value.trim() || config.title || config.workflowId;
    config.description = rhWorkflowEditNote?.value.trim() || config.description || '';
    try {
        if(rhEditorMode === 'app'){
            const item = provider();
            if(isBuiltinRunningHubProvider(item) && item.rh_apps?.[state.index]){
                const entry = item.rh_apps[state.index];
                entry.title = config.title || entry.title;
                entry.note = config.description || '';
                entry.fields = (config.fields || []).map(normalizeRhWorkflowField);
                entry.raw = config.raw || {};
                renderRunningHubCards();
                await saveProviders();
            }
            setStatus('应用参数配置已保存');
            setRhWorkflowSaveButtonState('saved', '已保存');
            setTimeout(() => setRhWorkflowSaveButtonState('idle', '保存'), 1600);
            broadcastStudioApiChange('providers-changed');
            renderRhWorkflowEditor();
            return;
        }
        const res = await fetch(`/api/runninghub/workflows/${encodeURIComponent(config.workflowId)}`, {
            method:'PUT',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({
                workflowId:config.workflowId,
                title:config.title,
                description:config.description,
                fields:(config.fields || []).map(normalizeRhWorkflowField),
                workflowJson:config.workflowJson || {},
                optionalImageMode:config.optionalImageMode || 'prune-workflow',
                raw:config.raw || {}
            })
        });
        const data = await res.json();
        if(!res.ok || data.success === false) throw new Error(data.detail || '保存失败');
        state.config = normalizeRhWorkflowConfig(data.workflow || config, state.entry);
        const item = provider();
        if(isBuiltinRunningHubProvider(item) && item.rh_workflows?.[state.index]){
            const entry = item.rh_workflows[state.index];
            entry.title = state.config.title;
            entry.note = state.config.description;
            entry.fields = (state.config.fields || []).map(normalizeRhWorkflowField);
            entry.workflowJson = state.config.workflowJson || {};
            entry.optionalImageMode = state.config.optionalImageMode || 'prune-workflow';
            entry.raw = state.config.raw || {};
            entry.updatedAt = Number(data.workflow?.updatedAt || Date.now());
            renderRunningHubCards();
            await saveProviders();
        }
        setStatus('工作流配置已保存');
        setRhWorkflowSaveButtonState('saved', '已保存');
        setTimeout(() => setRhWorkflowSaveButtonState('idle', '保存'), 1600);
        broadcastStudioApiChange('workflows-changed');
        renderRhWorkflowEditor();
    } catch(err) {
        setRhWorkflowSaveButtonState('idle', '保存');
        alert(err.message || '保存失败');
    }
}
function renderRhWorkflowEditor(){
    const config = rhWorkflowEditorState.config;
    if(!config){ renderRhWorkflowEditorLoading(rhEditorMode === 'app' ? '应用参数未加载' : '工作流未加载'); return; }
    if(rhWorkflowEditorTitle) rhWorkflowEditorTitle.textContent = config.title || (rhEditorMode === 'app' ? 'RunningHub AI 应用' : 'RunningHub 工作流');
    if(rhWorkflowEditorSub) rhWorkflowEditorSub.textContent = rhEditorMode === 'app' ? `/run/ai-app/${config.appId}` : `/run/workflow/${config.workflowId}`;
    if(rhWorkflowEditName) rhWorkflowEditName.value = config.title || '';
    if(rhWorkflowEditNote) rhWorkflowEditNote.value = config.description || '';
    applyRhImageSlotDefaults(config);
    renderRhMappedPreview();
    renderRhEditorSourcePane();
    refreshIcons();
}
function renderRhMappedPreview(){
    const config = rhWorkflowEditorState.config;
    if(!config || !rhWorkflowEditorSummary || !rhWorkflowEditorNodeList) return;
    renderRhWorkflowEditorSummary();
    rhWorkflowEditorNodeList.innerHTML = renderRhMappedPreviewHtml(config);
    refreshIcons();
}
function renderRhMappedPreviewHtml(config){
    const enabledFields = rhEditorSortedFields((config.fields || []).filter(field => field.enabled === true));
    const title = config.title || (rhEditorMode === 'app' ? 'RunningHub AI 应用' : 'RunningHub 工作流');
    const mediaCounts = enabledFields.reduce((acc, field) => {
        const kind = rhWorkflowFieldKind(field);
        if(kind === 'IMAGE') acc.image += 1;
        else if(kind === 'VIDEO') acc.video += 1;
        else if(kind === 'AUDIO') acc.audio += 1;
        else acc.setting += 1;
        return acc;
    }, {image:0, video:0, audio:0, setting:0});
    const fieldsHtml = enabledFields.length
        ? enabledFields.map(field => renderRhPreviewControl(field)).join('')
        : `<div class="rh-preview-empty">勾选右侧参数后，这里会显示画布节点上的效果</div>`;
    const statusHtml = rhWorkflowEditorState.previewStatus
        ? `<div class="rh-preview-status">${escapeHtml(rhWorkflowEditorState.previewStatus)}</div>`
        : '';
    const outputsHtml = (rhWorkflowEditorState.previewOutputs || []).length
        ? `<div class="rh-preview-output-list">${rhWorkflowEditorState.previewOutputs.map(url => renderRhPreviewOutput(url)).join('')}</div>`
        : '';
    const workflowOptionsHtml = rhEditorMode === 'workflow' ? `
        <div class="rh-workflow-run-mode">
            <label>
                <span>空可选图</span>
                <select onchange="setRhWorkflowOptionalImageMode(this.value)">
                    <option value="prune-workflow" ${String(config.optionalImageMode || 'prune-workflow') === 'prune-workflow' ? 'selected' : ''}>裁剪 workflow JSON</option>
                    <option value="skip" ${String(config.optionalImageMode || '') === 'skip' ? 'selected' : ''}>不提交字段</option>
                </select>
            </label>
            <small>仅工作流生效。可选图片为空时，裁剪模式会移除该图片输入及相关连接。</small>
        </div>
    ` : '';
    return `
        <div class="rh-mapped-card">
            <div class="rh-mapped-head">
                <div class="rh-mapped-icon"><i data-lucide="${rhEditorMode === 'app' ? 'sparkles' : 'workflow'}" class="w-4 h-4"></i></div>
                <div>
                    <div class="rh-mapped-title">${escapeHtml(title)}</div>
                    <div class="rh-mapped-sub">${rhEditorMode === 'app' ? `/run/ai-app/${escapeHtml(config.appId || '')}` : `/run/workflow/${escapeHtml(config.workflowId || '')}`}</div>
                </div>
            </div>
            <div class="rh-mapped-stats">
                <span>图片 ${mediaCounts.image}</span>
                <span>视频 ${mediaCounts.video}</span>
                <span>音频 ${mediaCounts.audio}</span>
                <span>参数 ${mediaCounts.setting}</span>
            </div>
            <div class="rh-preview-fields">${fieldsHtml}</div>
            ${workflowOptionsHtml}
            <button class="rh-preview-run ${rhWorkflowEditorState.previewRunning ? 'running' : ''}" type="button" onclick="testRhMappedPreview()" ${rhWorkflowEditorState.previewRunning ? 'disabled' : ''}><i data-lucide="${rhWorkflowEditorState.previewRunning ? 'loader-2' : 'play'}" class="w-3.5 h-3.5 ${rhWorkflowEditorState.previewRunning ? 'spin-icon' : ''}"></i><span>${rhWorkflowEditorState.previewRunning ? '测试中...' : '测试'}</span></button>
            ${statusHtml}
            ${outputsHtml}
        </div>
    `;
}
function renderRhPreviewOutput(url){
    const safe = escapeAttr(url || '');
    if(/\.(mp4|webm|mov|m4v)(\?|$)/i.test(safe)) return `<video src="${safe}" controls muted playsinline preload="metadata"></video>`;
    if(/\.(mp3|wav|ogg|m4a|flac|aac)(\?|$)/i.test(safe)) return `<audio src="${safe}" controls preload="metadata"></audio>`;
    return `<img src="${safe}" alt="">`;
}
function renderRhPreviewControl(field){
    const key = rhWorkflowFieldKey(field);
    const label = escapeHtml(field.label || field.fieldName);
    const kind = rhWorkflowFieldKind(field);
    const previewState = rhWorkflowEditorState.previewParams[key] || {};
    if(field.sourceFromUpstream === false && !['IMAGE','VIDEO','AUDIO'].includes(kind)){
        return `<div class="rh-preview-field keep-original"><div class="rh-preview-label">${label}</div><div class="rh-preview-keep"><i data-lucide="lock" class="w-3.5 h-3.5"></i><span>保留工作流原设置</span></div></div>`;
    }
    const randomActive = field.random_enabled === true && previewState.randomActive !== false;
    const value = previewState.value ?? field.fieldValue ?? '';
    const options = Array.isArray(field.options) ? field.options : [];
    if(['IMAGE','VIDEO','AUDIO'].includes(kind)){
        const slot = rhEditorMode === 'workflow' && kind === 'IMAGE'
            ? `<span class="rh-preview-slot">图 ${Number(field.imageOrder) || 1} · ${field.required === true ? '必选' : '可选'}</span>`
            : '';
        const icon = kind === 'VIDEO' ? 'file-video' : kind === 'AUDIO' ? 'file-audio' : 'image';
        const media = previewState.url
            ? renderRhPreviewMedia(previewState.url, kind, previewState.name || value)
            : `<i data-lucide="${icon}" class="w-5 h-5"></i><span>点击上传</span>`;
        return `<div class="rh-preview-field"><div class="rh-preview-label">${label}${slot}</div><button class="rh-preview-media ${previewState.url ? 'has-media' : ''}" type="button" onclick="pickRhPreviewMedia('${escapeAttr(key)}','${kind}')">${media}</button></div>`;
    }
    if(kind === 'BOOLEAN'){
        const on = String(value).toLowerCase() === 'true';
        return `<div class="rh-preview-field"><div class="rh-preview-label">${label}</div><div class="rh-preview-switch ${on ? 'on' : ''}"><span></span></div></div>`;
    }
    if(kind === 'SLIDER'){
        const min = Number.isFinite(Number(field.min)) ? Number(field.min) : 0;
        const max = Number.isFinite(Number(field.max)) && Number(field.max) > min ? Number(field.max) : 1;
        const step = Number.isFinite(Number(field.step)) && Number(field.step) > 0 ? Number(field.step) : 0.01;
        const numericValue = Number.isFinite(Number(value)) ? Number(value) : min;
        return `<div class="rh-preview-field"><div class="rh-preview-label"><span>${label}</span><span class="rh-preview-slider-val">${escapeHtml(numericValue)}</span></div><input class="rh-preview-slider" type="range" min="${escapeAttr(min)}" max="${escapeAttr(max)}" step="${escapeAttr(step)}" value="${escapeAttr(numericValue)}" oninput="updateRhPreviewValue('${escapeAttr(key)}', this.value); const val=this.closest('.rh-preview-field')?.querySelector('.rh-preview-slider-val'); if(val) val.textContent=this.value;"></div>`;
    }
    if(options.length || kind === 'SELECT'){
        return `<div class="rh-preview-field"><div class="rh-preview-label">${label}</div><select disabled>${(options.length ? options : [value || '选项']).map(option => `<option>${escapeHtml(option)}</option>`).join('')}</select></div>`;
    }
    const randomButton = kind === 'NUMBER' && field.random_enabled
        ? `<button class="random-btn rh-preview-random-btn ${randomActive ? 'active' : ''}" type="button" onclick="toggleRhPreviewRandom('${escapeAttr(key)}')" title="${randomActive ? '使用随机数' : '使用固定数'}"><i data-lucide="dice-5" class="w-4 h-4"></i></button>`
        : '';
    const readonly = randomActive ? 'disabled' : '';
    return `<div class="rh-preview-field"><div class="rh-preview-label">${label}</div><div class="rh-preview-random-row" style="${randomButton ? '' : 'grid-template-columns:1fr'}"><input ${readonly} type="${kind === 'NUMBER' ? 'number' : 'text'}" value="${escapeAttr(value)}" placeholder="${kind === 'NUMBER' && randomActive ? '随机数' : ''}" oninput="updateRhPreviewValue('${escapeAttr(key)}', this.value)">${randomButton}</div></div>`;
}
function renderRhPreviewMedia(url, kind, name=''){
    const safe = escapeAttr(url || '');
    if(kind === 'VIDEO') return `<video src="${safe}" muted preload="metadata" playsinline controls></video>`;
    if(kind === 'AUDIO') return `<span class="rh-preview-audio"><i data-lucide="file-audio" class="w-5 h-5"></i>${escapeHtml(name || '音频')}</span><audio src="${safe}" controls preload="metadata"></audio>`;
    return `<img src="${safe}" alt="">`;
}
function mediaAcceptForRhKind(kind){
    if(kind === 'VIDEO') return 'video/*';
    if(kind === 'AUDIO') return 'audio/*';
    return 'image/*';
}
async function pickRhPreviewMedia(key, kind){
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = mediaAcceptForRhKind(kind);
    input.onchange = async () => {
        const file = input.files?.[0];
        if(!file) return;
        const localUrl = URL.createObjectURL(file);
        rhWorkflowEditorState.previewParams[key] = {...(rhWorkflowEditorState.previewParams[key] || {}), url:localUrl, name:file.name, uploading:true};
        renderRhMappedPreview();
        const form = new FormData();
        form.append('files', file);
        try {
            const data = await fetch('/api/ai/upload', {method:'POST', body:form}).then(async r => {
                const json = await r.json();
                if(!r.ok) throw new Error(json.detail || '上传失败');
                return json;
            });
            const uploaded = data.files?.[0];
            rhWorkflowEditorState.previewParams[key] = {
                ...(rhWorkflowEditorState.previewParams[key] || {}),
                url:uploaded?.url || localUrl,
                name:uploaded?.name || file.name,
                kind:uploaded?.kind || kind.toLowerCase(),
                uploading:false
            };
            withRhEditorScrollPreserved(() => renderRhMappedPreview());
        } catch(err) {
            rhWorkflowEditorState.previewParams[key] = {...(rhWorkflowEditorState.previewParams[key] || {}), uploading:false};
            withRhEditorScrollPreserved(() => renderRhMappedPreview());
            alert(err.message || '上传失败');
        }
    };
    input.click();
}
function toggleRhPreviewRandom(key){
    const state = rhWorkflowEditorState.previewParams[key] || {};
    const field = (rhWorkflowEditorState.config?.fields || []).find(item => rhWorkflowFieldKey(item) === key);
    rhWorkflowEditorState.previewParams[key] = {
        ...state,
        value:state.value ?? field?.fieldValue ?? '',
        randomActive:state.randomActive === false
    };
    withRhEditorScrollPreserved(() => renderRhMappedPreview());
}
function updateRhPreviewValue(key, value){
    const state = rhWorkflowEditorState.previewParams[key] || {};
    rhWorkflowEditorState.previewParams[key] = {...state, value, randomActive:false};
}
function rhPreviewRandomValue(field){
    const isFloat = Number(field.step) > 0 && Number(field.step) < 1;
    let min = Number.isFinite(Number(field.min)) ? Number(field.min) : null;
    let max = Number.isFinite(Number(field.max)) ? Number(field.max) : null;
    const name = `${field.fieldName || ''} ${field.label || ''}`.toLowerCase();
    const looksSeed = name.includes('seed') || name.includes('noise') || name.includes('随机') || name.includes('种子');
    if(min === null) min = looksSeed ? 1 : 0;
    if(max === null || max <= min) max = looksSeed ? 1000000000000000 : 999999;
    const value = min + Math.random() * (max - min);
    if(isFloat){
        const precision = Math.min(8, Math.max(1, String(field.step).split('.')[1]?.length || 2));
        return Number(value.toFixed(precision));
    }
    return Math.floor(value);
}
async function rhPreviewUploadValueIfNeeded(value){
    const text = String(value || '').trim();
    if(!text) return '';
    if(!/^https?:\/\//i.test(text) && !text.startsWith('/output/') && !text.startsWith('/assets/')) return text;
    const res = await fetch('/api/runninghub/upload-asset', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({url:text})
    });
    const data = await res.json();
    if(!res.ok || data.success === false) throw new Error(data.detail || data.error || 'RunningHub 素材上传失败');
    return data.data?.fileName || text;
}
async function buildRhPreviewNodeInfoList(){
    const config = rhWorkflowEditorState.config;
    const fields = rhEditorSortedFields((config?.fields || []).filter(field => field.enabled === true));
    const result = [];
    for(const field of fields){
        const key = rhWorkflowFieldKey(field);
        const kind = rhWorkflowFieldKind(field);
        if(field.sourceFromUpstream === false && !['IMAGE','VIDEO','AUDIO'].includes(kind)) continue;
        const preview = rhWorkflowEditorState.previewParams[key] || {};
        let value = preview.value ?? field.fieldValue ?? '';
        if(['IMAGE','VIDEO','AUDIO'].includes(kind)){
            if(rhEditorMode === 'workflow' && kind === 'IMAGE' && field.required !== true && !preview.url) continue;
            if(rhEditorMode === 'workflow' && kind === 'IMAGE' && field.required === true && !preview.url && !value) throw new Error(`缺少必选图片：${field.label || field.fieldName}`);
            value = await rhPreviewUploadValueIfNeeded(preview.url || value);
        } else if(kind === 'NUMBER' && field.random_enabled === true && preview.randomActive !== false) {
            value = rhPreviewRandomValue(field);
        } else if(['NUMBER','SLIDER'].includes(kind) && String(value ?? '').trim() !== '' && !Number.isNaN(Number(value))) {
            value = Number(value);
        }
        if(typeof value === 'string' && /[\r\n]/.test(value)) value = value.split(/\r?\n/).map(s => s.trim()).filter(Boolean)[0] || '';
        result.push({nodeId:field.nodeId, fieldName:field.fieldName, fieldValue:value});
    }
    return result;
}
function rhPreviewPruneWorkflow(nodeInfoList){
    const config = rhWorkflowEditorState.config;
    if(rhEditorMode !== 'workflow' || (config?.optionalImageMode || 'prune-workflow') !== 'prune-workflow') return null;
    const submitted = new Set((nodeInfoList || []).map(item => rhWorkflowFieldKey(item)));
    const missing = rhEditorSortedFields(config.fields || []).filter(field => field.enabled === true && rhWorkflowFieldKind(field) === 'IMAGE' && field.required !== true && !submitted.has(rhWorkflowFieldKey(field)));
    if(!missing.length || !config.workflowJson) return null;
    const workflow = JSON.parse(JSON.stringify(config.workflowJson));
    const removeIds = new Set();
    missing.forEach(field => {
        const node = workflow[String(field.nodeId)];
        if(node?.inputs && Object.prototype.hasOwnProperty.call(node.inputs, field.fieldName)) delete node.inputs[field.fieldName];
        if(node?.inputs && !Object.keys(node.inputs).length) removeIds.add(String(field.nodeId));
    });
    removeIds.forEach(id => delete workflow[id]);
    Object.values(workflow).forEach(node => {
        Object.entries(node?.inputs || {}).forEach(([name, value]) => {
            if(Array.isArray(value) && removeIds.has(String(value[0]))) delete node.inputs[name];
        });
    });
    return workflow;
}
async function testRhMappedPreview(){
    const config = rhWorkflowEditorState.config;
    if(!config || rhWorkflowEditorState.previewRunning) return;
    rhWorkflowEditorState.previewRunning = true;
    rhWorkflowEditorState.previewStatus = '正在提交 RunningHub 任务...';
    rhWorkflowEditorState.previewOutputs = [];
    renderRhMappedPreview();
    try {
        const nodeInfoList = await buildRhPreviewNodeInfoList();
        const endpoint = rhEditorMode === 'workflow' ? '/api/runninghub/workflow-submit' : '/api/runninghub/submit';
        const workflow = rhPreviewPruneWorkflow(nodeInfoList);
        const body = rhEditorMode === 'workflow'
            ? {workflowId:String(config.workflowId || '').trim(), nodeInfoList, ...(workflow ? {workflow} : {})}
            : {webappId:String(config.appId || '').trim(), nodeInfoList};
        if(rhEditorMode === 'workflow' && !body.workflowId) throw new Error('workflowId 为空');
        if(rhEditorMode === 'app' && !body.webappId) throw new Error('webappId 为空');
        const submit = await fetch(endpoint, {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify(body)
        }).then(async r => {
            const data = await r.json();
            if(!r.ok || data.success === false) throw new Error(data.detail || data.error || 'RunningHub 提交失败');
            return data.data || data;
        });
        const taskId = submit.taskId;
        if(!taskId) throw new Error('RunningHub 没有返回 taskId');
        rhWorkflowEditorState.previewStatus = `任务已提交：${taskId}`;
        renderRhMappedPreview();
        let result = null;
        for(let i = 0; i < 720; i++){
            await new Promise(resolve => setTimeout(resolve, 2500));
            const data = await fetch(`/api/runninghub/query?taskId=${encodeURIComponent(taskId)}`).then(async r => {
                const json = await r.json();
                if(!r.ok || json.success === false) throw new Error(json.detail || json.error || 'RunningHub 查询失败');
                return json.data || json;
            });
            if(data.status === 'SUCCESS'){
                result = data;
                break;
            }
            if(data.status === 'FAILED') throw new Error(data.failReason || 'RunningHub 任务失败');
            rhWorkflowEditorState.previewStatus = data.status === 'QUEUED' ? '排队中...' : '运行中...';
            renderRhMappedPreview();
        }
        if(!result) throw new Error('RunningHub 任务超时');
        const outputs = result.urls || [];
        if(!outputs.length) throw new Error('RunningHub 没有返回产物');
        rhWorkflowEditorState.previewOutputs = outputs;
        rhWorkflowEditorState.previewStatus = '测试完成';
        setStatus('RunningHub 测试完成');
    } catch(err) {
        rhWorkflowEditorState.previewStatus = err.message || String(err);
        setStatus(rhWorkflowEditorState.previewStatus);
        alert(rhWorkflowEditorState.previewStatus);
    } finally {
        rhWorkflowEditorState.previewRunning = false;
        renderRhMappedPreview();
    }
}
function renderRhEditorSourcePane(){
    if(rhEditorMode === 'app') renderRhAppFieldCards();
    else renderRhWorkflowEditorGraph();
}
function renderRhWorkflowEditorSummary(){
    const config = rhWorkflowEditorState.config;
    if(!config || !rhWorkflowEditorSummary) return;
    const fields = config.fields || [];
    const enabled = fields.filter(field => field.enabled === true).length;
    const nodes = rhEditorMode === 'app' ? 1 : Object.keys(config.workflowJson || {}).length;
    const imageFields = fields.filter(field => field.enabled === true && rhWorkflowFieldKind(field) === 'IMAGE');
    const optionalImages = imageFields.filter(field => field.required !== true).length;
    rhWorkflowEditorSummary.innerHTML = `
        <div><span>${rhEditorMode === 'app' ? '应用' : '节点'}</span><strong>${nodes}</strong></div>
        <div><span>字段</span><strong>${enabled} / ${fields.length}</strong></div>
        ${rhEditorMode === 'workflow' ? `<div><span>可选图</span><strong>${optionalImages} / ${imageFields.length}</strong></div>` : ''}
    `;
}
function renderRhWorkflowEditorNodeList(){
    const config = rhWorkflowEditorState.config;
    if(!config || !rhWorkflowEditorNodeList) return;
    const groups = {};
    (config.fields || []).forEach(field => {
        const key = rhWorkflowGroupKey(field);
        (groups[key] = groups[key] || { field, items:[] }).items.push(field);
    });
    const values = Object.entries(groups);
    if(!values.length){
        rhWorkflowEditorNodeList.innerHTML = `<div class="rh-editor-empty">没有可配置字段</div>`;
        return;
    }
    rhWorkflowEditorNodeList.innerHTML = values.map(([groupKey, group]) => {
        const safeGroup = groupKey.replace(/[^a-zA-Z0-9_-]/g, '_');
        const expanded = rhWorkflowEditorState.expanded[safeGroup] !== false;
        const enabledCount = group.items.filter(field => field.enabled === true).length;
        return `
            <div class="rh-editor-node ${expanded ? 'expanded' : ''} ${String(group.field.nodeId) === rhWorkflowEditorState.activeNodeId ? 'is-focused' : ''}" data-node-id="${escapeAttr(group.field.nodeId)}">
                <button class="rh-editor-node-head" type="button" onclick="toggleRhWorkflowEditorGroup('${escapeAttr(safeGroup)}')">
                    <span>
                        <strong>${escapeHtml(group.field.group || `Node #${group.field.nodeId}`)}</strong>
                        <small>#${escapeHtml(group.field.nodeId)} · ${enabledCount}/${group.items.length}</small>
                    </span>
                    <i data-lucide="chevron-down" class="w-4 h-4"></i>
                </button>
                <div class="rh-editor-node-body">
                    ${group.items.map(field => renderRhWorkflowEditorField(field)).join('')}
                </div>
            </div>
        `;
    }).join('');
}
function renderRhWorkflowEditorField(field){
    const key = rhWorkflowFieldKey(field);
    const checked = field.enabled === true;
    const type = rhWorkflowFieldKind(field);
    const optionsText = Array.isArray(field.options) ? field.options.join('\n') : '';
    const randomOn = field.random_enabled === true;
    const keepOriginal = field.sourceFromUpstream === false;
    const imageSlotControls = rhEditorMode === 'workflow' && type === 'IMAGE' ? `
        <div class="rh-image-slot-row">
            <label><span>排序</span><input type="number" min="1" step="1" value="${escapeAttr(field.imageOrder || '')}" oninput="updateRhWorkflowEditorField('${escapeAttr(key)}','imageOrder',this.value)"></label>
            <button class="rh-editor-required ${field.required === true ? 'active' : ''}" type="button" onclick="updateRhWorkflowEditorField('${escapeAttr(key)}','required',${field.required === true ? 'false' : 'true'})">
                <span class="check-dot"></span>${field.required === true ? '必选' : '可选'}
            </button>
        </div>
    ` : '';
    return `
        <div class="rh-editor-field-row ${checked ? 'active' : ''}">
            <button class="rh-editor-check ${checked ? 'checked' : ''}" type="button" onclick="toggleRhWorkflowEditorField('${escapeAttr(key)}')">${checked ? '<i data-lucide="check" class="w-3 h-3"></i>' : ''}</button>
            <div class="rh-editor-field-main">
                <div class="rh-editor-field-name">${escapeHtml(field.label || field.fieldName)}</div>
                <div class="rh-editor-field-meta">${escapeHtml(field.fieldName)} · ${escapeHtml(type)}</div>
                <button class="rh-editor-keep ${keepOriginal ? 'active' : ''}" type="button" onclick="updateRhWorkflowEditorField('${escapeAttr(key)}','sourceFromUpstream',${keepOriginal ? 'true' : 'false'})">
                    <span class="check-dot"></span>${keepOriginal ? '保留工作流原设置' : '暴露并覆盖参数'}
                </button>
                <div class="rh-editor-field-controls">
                    <input type="text" value="${escapeAttr(field.label || '')}" placeholder="显示名称" oninput="updateRhWorkflowEditorField('${escapeAttr(key)}','label',this.value)">
                    <select onchange="updateRhWorkflowEditorField('${escapeAttr(key)}','fieldType',this.value)">
                        ${['TEXT','NUMBER','SLIDER','BOOLEAN','SELECT','IMAGE','VIDEO','AUDIO'].map(option => `<option value="${option}" ${String(field.fieldType || type).toUpperCase() === option ? 'selected' : ''}>${rhWorkflowFieldTypeLabel(option)}</option>`).join('')}
                    </select>
                </div>
                ${imageSlotControls}
                <div class="rh-editor-field-controls rh-editor-wide-controls">
                    <textarea placeholder="下拉选项：每行一个，例如 1024x1024" oninput="updateRhWorkflowEditorField('${escapeAttr(key)}','options',this.value)">${escapeHtml(optionsText)}</textarea>
                </div>
                <div class="rh-editor-random-row">
                    <button class="rh-editor-random ${randomOn ? 'active' : ''}" type="button" onclick="updateRhWorkflowEditorField('${escapeAttr(key)}','random_enabled',${randomOn ? 'false' : 'true'})"><i data-lucide="dice-5" class="w-3.5 h-3.5"></i><span>随机数</span></button>
                    <input type="number" value="${escapeAttr(field.min ?? '')}" placeholder="最小" oninput="updateRhWorkflowEditorField('${escapeAttr(key)}','min',this.value)">
                    <input type="number" value="${escapeAttr(field.max ?? '')}" placeholder="最大" oninput="updateRhWorkflowEditorField('${escapeAttr(key)}','max',this.value)">
                    <input type="number" value="${escapeAttr(field.step ?? '')}" placeholder="步长" oninput="updateRhWorkflowEditorField('${escapeAttr(key)}','step',this.value)">
                </div>
            </div>
        </div>
    `;
}
function renderRhAppFieldCards(){
    const config = rhWorkflowEditorState.config;
    if(!rhWorkflowEditorGraphWrap || !config) return;
    closeRhNodePopover();
    rhWorkflowEditorGraphWrap.classList.add('rh-app-field-wrap');
    rhWorkflowEditorGraphWrap.innerHTML = `
        <div class="rh-app-field-list">
            ${(config.fields || []).length
                ? (config.fields || []).map(field => renderRhAppFieldCard(field)).join('')
                : `<div class="rh-editor-empty">没有拉取到应用参数</div>`}
        </div>
    `;
    refreshIcons();
}
function restoreRhGraphWrap(){
    if(!rhWorkflowEditorGraphWrap || rhWorkflowEditorGraphSvg?.parentElement === rhWorkflowEditorGraphWrap) return;
    rhWorkflowEditorGraphWrap.classList.remove('rh-app-field-wrap');
    rhWorkflowEditorGraphWrap.innerHTML = `
        <svg id="rhWorkflowEditorGraphSvg" class="rh-editor-graph-svg"></svg>
        <div class="rh-editor-graph-controls">
            <button type="button" onclick="rhEditorGraphZoom(-1)" title="缩小"><i data-lucide="zoom-out" class="w-4 h-4"></i></button>
            <span id="rhWorkflowEditorZoom">100%</span>
            <button type="button" onclick="rhEditorGraphZoom(1)" title="放大"><i data-lucide="zoom-in" class="w-4 h-4"></i></button>
            <button type="button" onclick="rhEditorGraphFit()" title="适应窗口"><i data-lucide="maximize" class="w-4 h-4"></i></button>
        </div>
    `;
    rhWorkflowEditorGraphSvg = document.getElementById('rhWorkflowEditorGraphSvg');
    rhWorkflowEditorZoom = document.getElementById('rhWorkflowEditorZoom');
}
function renderRhAppFieldCard(field){
    const key = rhWorkflowFieldKey(field);
    const checked = field.enabled === true;
    return `
        <div class="rh-app-field-card ${checked ? 'active' : ''}" data-field-key="${escapeAttr(key)}" onclick="openRhAppFieldPopover('${escapeAttr(key)}', this)">
            <button class="rh-editor-check ${checked ? 'checked' : ''}" type="button" onclick="event.stopPropagation();toggleRhWorkflowEditorField('${escapeAttr(key)}')">${checked ? '<i data-lucide="check" class="w-3 h-3"></i>' : ''}</button>
            <div>
                <strong>${escapeHtml(field.label || field.fieldName)}</strong>
                <span>${escapeHtml(field.fieldName)} · ${escapeHtml(rhWorkflowFieldKind(field))}</span>
            </div>
            <i data-lucide="settings-2" class="w-4 h-4"></i>
        </div>
    `;
}
function openRhAppFieldPopover(key, anchorEl){
    const config = rhWorkflowEditorState.config;
    const field = (config?.fields || []).find(item => rhWorkflowFieldKey(item) === key);
    if(!field) return;
    closeRhNodePopover();
    const pop = document.createElement('div');
    pop.id = 'rhNodePopover';
    pop.className = 'rh-node-popover rh-app-popover';
    pop.dataset.fieldKey = String(key || '');
    pop.innerHTML = `
        <div class="rh-popover-head">
            <div>
                <strong>${escapeHtml(field.label || field.fieldName)}</strong>
                <span>${escapeHtml(field.fieldName)}</span>
            </div>
            <button type="button" onclick="closeRhNodePopover()"><i data-lucide="x" class="w-3.5 h-3.5"></i></button>
        </div>
        <div class="rh-popover-body">${renderRhWorkflowEditorField(field)}</div>
    `;
    document.body.appendChild(pop);
    const rect = anchorEl?.getBoundingClientRect?.();
    const modalRect = rhWorkflowEditorOverlay?.getBoundingClientRect?.() || {left:0, top:0, right:window.innerWidth, bottom:window.innerHeight};
    const width = 390;
    let left = rect ? rect.left : window.innerWidth / 2 - 190;
    let top = rect ? rect.bottom + 10 : window.innerHeight / 2 - 180;
    if(left + width > modalRect.right - 16) left = modalRect.right - width - 16;
    if(top + 420 > modalRect.bottom - 16) top = Math.max(modalRect.top + 74, (rect?.top || top) - 420);
    pop.style.left = `${Math.max(modalRect.left + 16, left)}px`;
    pop.style.top = `${top}px`;
    refreshIcons();
}
function computeRhWorkflowEditorLayers(workflow){
    const ids = Object.keys(workflow || {});
    const incoming = {}, outgoing = {};
    ids.forEach(id => { incoming[id] = new Set(); outgoing[id] = new Set(); });
    ids.forEach(id => {
        Object.values(workflow[id]?.inputs || {}).forEach(value => {
            if(Array.isArray(value) && value.length === 2 && typeof value[0] === 'string' && workflow[value[0]]){
                incoming[id].add(value[0]);
                outgoing[value[0]].add(id);
            }
        });
    });
    const layer = {};
    const visiting = new Set();
    function dfs(id, lv){
        if(visiting.has(id)) return;
        layer[id] = Math.max(layer[id] || 0, lv);
        visiting.add(id);
        outgoing[id].forEach(child => dfs(child, lv + 1));
        visiting.delete(id);
    }
    ids.forEach(id => { if(incoming[id].size === 0) dfs(id, 0); });
    ids.forEach(id => { if(!(id in layer)) layer[id] = 0; });
    const buckets = {};
    ids.forEach(id => { (buckets[layer[id]] = buckets[layer[id]] || []).push(id); });
    return { buckets };
}
function renderRhWorkflowEditorGraph(){
    const config = rhWorkflowEditorState.config;
    restoreRhGraphWrap();
    closeRhNodePopover();
    const workflow = config?.workflowJson || {};
    const svg = rhWorkflowEditorGraphSvg;
    const wrap = rhWorkflowEditorGraphWrap;
    if(!svg || !wrap) return;
    if(!workflow || !Object.keys(workflow).length){
        svg.innerHTML = `<text x="24" y="42" fill="currentColor">暂无工作流预览</text>`;
        return;
    }
    const { buckets } = computeRhWorkflowEditorLayers(workflow);
    const NODE_W = 136, NODE_H = 52, X_GAP = 42, Y_GAP = 16;
    const positions = {};
    const levels = Object.keys(buckets).map(Number).sort((a,b)=>a-b);
    let maxRows = 0;
    levels.forEach(lv => {
        const ids = buckets[lv].sort((a,b)=>parseInt(a,10)-parseInt(b,10));
        ids.forEach((id, idx) => positions[id] = { x:lv * (NODE_W + X_GAP) + 18, y:idx * (NODE_H + Y_GAP) + 18 });
        maxRows = Math.max(maxRows, ids.length);
    });
    const edges = [];
    Object.keys(workflow).forEach(toId => {
        const seen = new Set();
        Object.values(workflow[toId]?.inputs || {}).forEach(value => {
            if(Array.isArray(value) && value.length === 2 && typeof value[0] === 'string' && positions[value[0]] && positions[toId]){
                if(seen.has(value[0])) return;
                seen.add(value[0]);
                const from = positions[value[0]], to = positions[toId];
                const x1 = from.x + NODE_W, y1 = from.y + NODE_H / 2;
                const x2 = to.x, y2 = to.y + NODE_H / 2;
                const cx = (x1 + x2) / 2;
                edges.push(`<path class="rh-editor-edge" d="M ${x1} ${y1} C ${cx} ${y1}, ${cx} ${y2}, ${x2} ${y2}"></path>`);
            }
        });
    });
    const activeNodes = new Set((config.fields || []).filter(field => field.enabled === true).map(field => String(field.nodeId)));
    const nodes = Object.entries(workflow).map(([id, node]) => {
        const pos = positions[id];
        const title = workflowNodeTitle(node);
        const klass = workflowNodeClass(node);
        const cat = workflowNodeCategory(node);
        const count = (config.fields || []).filter(field => field.enabled === true && String(field.nodeId) === String(id)).length;
        return `
            <g class="rh-editor-gnode cat-${cat} ${activeNodes.has(String(id)) ? 'has-exposed' : ''} ${String(id) === rhWorkflowEditorState.activeNodeId ? 'is-active' : ''}" data-node-id="${escapeAttr(id)}" transform="translate(${pos.x},${pos.y})" onclick="openRhWorkflowNodePopover('${escapeAttr(id)}', this)">
                <rect width="${NODE_W}" height="${NODE_H}" rx="8"></rect>
                <text class="rh-editor-gtitle" x="10" y="20">${escapeHtml(title.length > 15 ? title.slice(0, 15) + '...' : title)}</text>
                <text class="rh-editor-gsub" x="10" y="36">${escapeHtml(klass.length > 18 ? klass.slice(0, 18) + '...' : klass)}</text>
                <text class="rh-editor-gsub" x="${NODE_W - 8}" y="20" text-anchor="end">#${escapeHtml(id)}</text>
                ${count ? `<text class="rh-editor-gbadge" x="${NODE_W - 8}" y="43" text-anchor="end">${count}</text>` : ''}
            </g>
        `;
    }).join('');
    rhWorkflowEditorState.graph.w = levels.length * (NODE_W + X_GAP) + 18;
    rhWorkflowEditorState.graph.h = maxRows * (NODE_H + Y_GAP) + 18;
    svg.setAttribute('viewBox', `0 0 ${wrap.clientWidth || 800} ${wrap.clientHeight || 520}`);
    svg.innerHTML = `<g id="rhWorkflowEditorViewport" transform="translate(${rhWorkflowEditorState.graph.x},${rhWorkflowEditorState.graph.y}) scale(${rhWorkflowEditorState.graph.k})">${edges.join('')}${nodes}</g>`;
    bindRhWorkflowEditorPanZoom();
    updateRhEditorZoom();
}
function updateRhEditorZoom(){
    if(rhWorkflowEditorZoom) rhWorkflowEditorZoom.textContent = Math.round((rhWorkflowEditorState.graph.k || 1) * 100) + '%';
}
function applyRhEditorGraphTransform(){
    const vp = document.getElementById('rhWorkflowEditorViewport');
    const g = rhWorkflowEditorState.graph;
    if(vp) vp.setAttribute('transform', `translate(${g.x},${g.y}) scale(${g.k})`);
    updateRhEditorZoom();
}
function rhEditorGraphZoom(dir){
    const wrap = rhWorkflowEditorGraphWrap;
    if(!wrap) return;
    const g = rhWorkflowEditorState.graph;
    const factor = dir > 0 ? 1.2 : 1 / 1.2;
    const newK = Math.max(0.2, Math.min(3, g.k * factor));
    const cx = wrap.clientWidth / 2;
    const cy = wrap.clientHeight / 2;
    g.x = cx - (cx - g.x) * (newK / g.k);
    g.y = cy - (cy - g.y) * (newK / g.k);
    g.k = newK;
    applyRhEditorGraphTransform();
}
function rhEditorGraphFit(){
    const wrap = rhWorkflowEditorGraphWrap;
    const g = rhWorkflowEditorState.graph;
    if(!wrap || !g.w || !g.h) return;
    const pad = 24;
    const k = Math.max(0.2, Math.min(2, Math.min((wrap.clientWidth - pad * 2) / g.w, (wrap.clientHeight - pad * 2) / g.h)));
    g.k = k;
    g.x = (wrap.clientWidth - g.w * k) / 2;
    g.y = (wrap.clientHeight - g.h * k) / 2;
    applyRhEditorGraphTransform();
}
function bindRhWorkflowEditorPanZoom(){
    const svg = rhWorkflowEditorGraphSvg;
    const wrap = rhWorkflowEditorGraphWrap;
    if(!svg || !wrap || svg.dataset.editorPanZoomBound) return;
    svg.dataset.editorPanZoomBound = '1';
    rhWorkflowEditorState.bound = true;
    wrap.addEventListener('wheel', event => {
        if(!rhWorkflowEditorState.open) return;
        event.preventDefault();
        const g = rhWorkflowEditorState.graph;
        const factor = event.deltaY < 0 ? 1.15 : 1 / 1.15;
        const newK = Math.max(0.2, Math.min(3, g.k * factor));
        const rect = wrap.getBoundingClientRect();
        const mx = event.clientX - rect.left;
        const my = event.clientY - rect.top;
        g.x = mx - (mx - g.x) * (newK / g.k);
        g.y = my - (my - g.y) * (newK / g.k);
        g.k = newK;
        applyRhEditorGraphTransform();
    }, { passive:false });
    svg.addEventListener('mousedown', event => {
        if(!rhWorkflowEditorState.open) return;
        event.preventDefault();
        rhWorkflowEditorState.pan = { sx:event.clientX, sy:event.clientY, ox:rhWorkflowEditorState.graph.x, oy:rhWorkflowEditorState.graph.y };
        wrap.classList.add('is-panning');
    });
    window.addEventListener('mousemove', event => {
        const pan = rhWorkflowEditorState.pan;
        if(!pan) return;
        rhWorkflowEditorState.graph.x = pan.ox + event.clientX - pan.sx;
        rhWorkflowEditorState.graph.y = pan.oy + event.clientY - pan.sy;
        applyRhEditorGraphTransform();
    });
    window.addEventListener('mouseup', () => {
        if(rhWorkflowEditorState.pan){
            rhWorkflowEditorState.pan = null;
            wrap.classList.remove('is-panning');
        }
    });
}
function renderRunningHubCards(){
    const item = provider();
    if(!isBuiltinRunningHubProvider(item)){
        if(rhAppsList) rhAppsList.innerHTML = '';
        if(rhWorkflowsList) rhWorkflowsList.innerHTML = '';
        return;
    }
ensureRunningHubLists(item);
const apps = item.rh_apps.map((entry, index) => ({...entry, _rhIndex:index})).filter(entry => entry?.hidden !== true);
const workflows = item.rh_workflows.map((entry, index) => ({...entry, _rhIndex:index})).filter(entry => entry?.hidden !== true);
if(!apps.length && !workflows.length && Date.now() - rhProviderLastRefreshAt > 3000){
refreshRunningHubProviderFromApi(true);
}
if(rhAppsCount) rhAppsCount.textContent = apps.length;
    if(rhWorkflowsCount) rhWorkflowsCount.textContent = workflows.length;
    renderRhEntryList(rhAppsList, apps, 'app');
    renderRhEntryList(rhWorkflowsList, workflows, 'workflow');
    refreshIcons();
}
function rhEntryThumbnailCandidates(kind, entry){
    const id = String((kind === 'workflow' ? (entry?.workflowId || entry?.id) : (entry?.appId || entry?.id)) || '').trim().replace(/[^0-9A-Za-z_-]/g, '');
    if(!id) return [];
    const prefix = kind === 'workflow' ? 'workflow' : 'app';
    const exts = ['jpg'];
    const names = [`${prefix}-${id}`, id];
    const roots = ['/static/runninghub/thumbnails', '/static/runninghub'];
    const urls = [];
    names.forEach(name => {
        exts.forEach(ext => {
            roots.forEach(root => urls.push(`${root}/${name}.${ext}`));
        });
    });
    return urls;
}
function renderRhEntryThumbnail(kind, entry){
    const icon = kind === 'app' ? 'sparkles' : 'workflow';
    const candidates = rhEntryThumbnailCandidates(kind, entry);
    const thumbnail = String(entry?.thumbnail || '').trim();
    const src = thumbnail || candidates[0] || '';
    if(!src) return `<i data-lucide="${icon}" class="w-5 h-5"></i>`;
    const fallbacks = thumbnail ? candidates : candidates.slice(1);
    return `<img src="${escapeAttr(src)}" alt="" data-rh-thumb-fallbacks="${escapeAttr(fallbacks.join('|'))}" onerror="fallbackRhEntryThumbnail(this,'${icon}')">`;
}
function fallbackRhEntryThumbnail(img, icon){
    const fallbacks = String(img?.dataset?.rhThumbFallbacks || '').split('|').filter(Boolean);
    const next = fallbacks.shift();
    if(next){
        img.dataset.rhThumbFallbacks = fallbacks.join('|');
        img.src = next;
        return;
    }
    const parent = img?.parentElement;
    if(parent){
        parent.innerHTML = `<i data-lucide="${icon === 'sparkles' ? 'sparkles' : 'workflow'}" class="w-5 h-5"></i>`;
        refreshIcons();
    }
}
function renderRhEntryList(target, list, kind){
    if(!target) return;
    if(!list.length){
        target.innerHTML = `<div class="rh-empty">${kind === 'app' ? '粘贴 /run/ai-app/... 后点击创建 AI 应用卡片' : '粘贴 /run/workflow/... 后点击创建工作流卡片'}</div>`;
        return;
    }
    target.innerHTML = list.map((entry, index) => `
        <div class="rh-config-card">
            <button class="rh-thumb" type="button" onclick="pickRhThumbnail('${kind}', ${entry._rhIndex ?? index})" title="上传缩略图">
                ${renderRhEntryThumbnail(kind, entry)}
            </button>
            <div class="rh-card-main">
                <label class="rh-card-title-field">
                    <span>名称</span>
                    <input type="text" value="${escapeAttr(entry.title || '')}" oninput="updateRhEntry('${kind}', ${entry._rhIndex ?? index}, 'title', this.value)" placeholder="${kind === 'app' ? 'AI 应用名称' : '工作流名称'}">
                </label>
                <div class="rh-id-line"><i data-lucide="hash" class="w-3 h-3"></i><span>${escapeHtml(kind === 'app' ? `/run/ai-app/${entry.id}` : `/run/workflow/${entry.id}`)}</span></div>
                <textarea oninput="updateRhEntry('${kind}', ${entry._rhIndex ?? index}, 'note', this.value)" placeholder="备注、用途、参数说明">${escapeHtml(entry.note || '')}</textarea>
            </div>
            <div class="rh-card-actions">
                ${kind === 'workflow'
                    ? `<button class="rh-card-action" type="button" onclick="openRhWorkflowEditor(${entry._rhIndex ?? index})" title="编辑工作流"><i data-lucide="settings-2" class="w-3.5 h-3.5"></i></button>`
                    : `<button class="rh-card-action" type="button" onclick="openRhAppEditor(${entry._rhIndex ?? index})" title="编辑应用参数"><i data-lucide="settings-2" class="w-3.5 h-3.5"></i></button>`}
                <button class="rh-card-action danger" type="button" onclick="removeRhEntry('${kind}', ${entry._rhIndex ?? index})" title="删除"><i data-lucide="trash-2" class="w-3.5 h-3.5"></i></button>
            </div>
        </div>
    `).join('');
}
function openRecommendApi(){
    recommendInlineOpen = true;
    syncRecommendView();
    renderRecommendApi();
    renderProviderOnboarding(provider());
}
function closeRecommendApi(){
    if(recommendApiOverlay) recommendApiOverlay.style.display = 'none';
    recommendInlineOpen = false;
    syncRecommendView();
    renderRecommendApi();
    renderEditor();
}
function syncRecommendView(){
    if(settingsContent) settingsContent.hidden = recommendInlineOpen;
    if(recommendContent) recommendContent.hidden = !recommendInlineOpen;
    const recommendTitle = recommendContent?.querySelector('.editor-title');
    const recommendSub = recommendContent?.querySelector('.editor-sub');
    if(recommendTitle) recommendTitle.textContent = tr('api.recommendPanelTitle');
    if(recommendSub) recommendSub.textContent = tr('api.recommendPanelSub');
    document.body.classList.toggle('show-recommend-mode', recommendInlineOpen);
}
function renderRecommendApi(){
    if(!recommendPanel) return;
    if(!recommendInlineOpen){
        recommendPanel.innerHTML = '';
        return;
    }
    const html = RECOMMENDED_APIS.map((api, index) => `
        <section class="recommend-card recommend-platform-card" style="--recommend-index:${index}">
            <div class="recommend-platform-info">
                <div class="recommend-platform-head">
                    <div>
                        <div class="recommend-name"><span>${escapeHtml(api.name)}</span></div>
                    </div>
                    <span class="recommend-badge">${escapeHtml(api.protocol === 'apimart' ? 'APIMart' : 'OpenAI')}</span>
                </div>
                <p class="recommend-platform-summary">${escapeHtml(tr(api.summaryKey))}</p>
                <div class="recommend-tags">
                    ${api.perkKey ? `<span class="recommend-tag recommend-perk-tag"><i data-lucide="gift" class="w-3 h-3"></i><span>${escapeHtml(tr(api.perkKey))}</span></span>` : ''}
                    ${(api.tagKeys || []).map(tag => `<span class="recommend-tag">${escapeHtml(tag.startsWith('api.') ? tr(tag) : tag)}</span>`).join('')}
                </div>
            </div>
            <div class="recommend-platform-setup">
                <div class="recommend-setup-title">${escapeHtml(tr('api.recommendQuickSetup'))}</div>
                <div class="recommend-quick-stack recommend-setup-flow">
                    <div class="recommend-guide-source onboarding-rh-source-group">
                        <div class="onboarding-rh-source-label">${escapeHtml(tr('api.getKey'))}</div>
                        <div class="onboarding-key-actions onboarding-rh-key-actions recommend-single-action">
                            <a class="onboarding-key-btn recommend-guide-key-btn" href="${escapeAttr(api.register_url)}" target="_blank" rel="noopener noreferrer"><i data-lucide="key-round" class="w-3.5 h-3.5"></i><span>${escapeHtml(tr('api.getKey'))}</span></a>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    `).join('');
    recommendPanel.innerHTML = `
        <div class="onboarding-head">
            <div>
                <div class="onboarding-title">${escapeHtml(tr('api.recommendPanelTitle'))}</div>
                <div class="onboarding-desc">${escapeHtml(tr('api.recommendPanelDesc'))}</div>
            </div>
        </div>
        <div class="recommend-api-body recommend-inline-body">${html}</div>
        <div class="recommend-note">${escapeHtml(tr('api.recommendApiNote'))}</div>
    `;
    refreshIcons();
}
function recommendedProviderForApi(api){
    let item = providers.find(provider => String(provider.name || '').toLowerCase() === api.name.toLowerCase());
    if(item) return item;
    const baseId = normalizeId(api.name) || 'custom-api';
    let id = baseId;
    let suffix = 2;
    while(providers.some(provider => provider.id === id)) id = `${baseId}-${suffix++}`;
  item = {
    id,
    name:api.name,
        base_url:api.base_url,
        protocol:api.protocol,
        image_generation_endpoint:'',
        image_edit_endpoint:'',
    enabled:true,
    primary:false,
    image_models:Array.isArray(api.image_models) ? [...api.image_models] : [],
    chat_models:Array.isArray(api.chat_models) ? [...api.chat_models] : [],
    video_models:Array.isArray(api.video_models) ? [...api.video_models] : [],
    model_display_names:(api.model_display_names && typeof api.model_display_names === 'object') ? {...api.model_display_names} : {},
    model_protocols:(api.model_protocols && typeof api.model_protocols === 'object') ? {...api.model_protocols} : {},
    has_key:false,
    key_preview:''
  };
  applyDefaultRhModelDisplayNames(item);
  providers.push(item);
  return item;
}
async function saveRecommendedApi(index){
    const api = RECOMMENDED_APIS[index];
    if(!api) return;
    const input = recommendPanel?.querySelector(`[data-recommend-key="${index}"]`);
    const key = input?.value.trim() || '';
    if(!key){ alert(tr('api.enterApiKey')); return; }
    const item = recommendedProviderForApi(api);
    selectedId = item.id;
    recommendInlineOpen = false;
    syncRecommendView();
    renderProviderList();
    renderEditor();
    keyInput.value = key;
    if(protocolInput){
        protocolInput.value = api.protocol;
        protocolInput.dispatchEvent(new Event('change'));
    }
    syncEditor();
    const ok = await saveProviders();
    if(ok) setStatus(trf('api.recommendSaved', {name:api.name}));
}
function sortedProviders(){
    const order = ['modelscope', 'runninghub', 'volcengine'];
    return visibleProviders().sort((a, b) => {
        const ai = order.indexOf(a.id);
        const bi = order.indexOf(b.id);
        if(ai === -1 && bi === -1) return 0;
        if(ai === -1) return 1;
        if(bi === -1) return -1;
        return ai - bi;
    });
}
function providerDragAttrs(item){
if(isFixedProvider(item)) return '';
const id = escapeAttr(item.id);
return ` draggable="true" data-provider-id="${id}" ondragstart="handleProviderDragStart(event,'${id}')" ondragover="handleProviderDragOver(event,'${id}')" ondrop="handleProviderDrop(event,'${id}')" ondragend="handleProviderDragEnd()"`;
}
function renderProviderNavCard(item){
const active = item.id === selectedId ? 'active' : '';
const stateClass = item.enabled === false ? 'is-disabled' : (item.has_key || item.has_wallet_key ? 'has-key' : 'missing-key');
const protocolLabel = isRunningHubProvider(item) ? 'RH' : String(item.protocol || 'openai').toUpperCase();
return `
<button class="provider-card provider-card-compact ${active} ${stateClass}" type="button" onclick="selectProvider('${escapeHtml(item.id)}')"${providerDragAttrs(item)}>
<span class="provider-info">
<span class="provider-name">${escapeHtml(item.name || item.id)}</span>
</span>
<span class="provider-side-meta">
<span class="provider-status-dot"></span>
<span class="provider-protocol-pill">${escapeHtml(protocolLabel)}</span>
</span>
</button>
`;
}
function selectedSummaryInfo(){
if(isAgentPanelSelection()){
    const item = currentAgent() || {};
    const model = String(item.model || '').trim();
    const name = item.name || selectedAgentFromPanel() || 'Agent';
    return {
        name,
        sub: model ? `${name} / ${model}` : name
    };
}
const item = visibleProviders().find(provider => provider.id === selectedId) || provider();
return {
    name:item?.name || item?.id || '未选择',
    sub:item?.base_url || item?.id || '请选择平台'
};
}
function renderApiSummary(){
if(apiPlatformCount) apiPlatformCount.textContent = String(visibleProviders().length);
if(apiAgentCount) apiAgentCount.textContent = String(Object.keys(agentRegistry()).length || 1);
const selected = selectedSummaryInfo();
if(apiCurrentSelected) apiCurrentSelected.textContent = selected.name;
if(apiCurrentSelectedSub) apiCurrentSelectedSub.textContent = selected.sub;
}
function renderCodexProviderMark(){
return `
<span class="provider-mark provider-image-mark provider-codex-mark">
<img src="${CODEX_APP_ICON}" alt="Myrid-Agent" class="provider-mark-image" onerror="this.style.display='none';this.nextElementSibling.style.display='inline-flex'">
<i data-lucide="bot" class="w-4 h-4 provider-mark-fallback-icon"></i>
        </span>
`;
}
function renderProviderList(){
providerList.innerHTML = sortedProviders().map(renderProviderNavCard).join('') + '<button class="provider-add-inline" type="button" onclick="addProvider()"><i data-lucide="plus" class="w-4 h-4"></i></button>';
renderAgentList();
renderApiSummary();
lucide.createIcons();
return;
providerList.innerHTML = sortedProviders().map(item => {
const active = item.id === selectedId ? 'active' : '';
const stateClass = item.enabled === false ? 'is-disabled' : (item.has_key || item.has_wallet_key ? 'has-key' : 'missing-key');
const protocolLabel = isRunningHubProvider(item) ? 'RH' : String(item.protocol || 'openai').toUpperCase();
        if(item.id === 'modelscope'){
            return `
                <button class="provider-card provider-card-banner ${active} ${stateClass}" type="button" onclick="selectProvider('${escapeHtml(item.id)}')">
                    <span class="provider-banner-inner">
                        <span class="provider-logo-wrap">
                            <img src="/static/images/modelscope.gif" alt="ModelScope" class="ms-icon-light">
                            <img src="/static/images/modelscope-1.gif" alt="ModelScope" class="ms-icon-dark">
                            <span class="provider-logo-fallback">ModelScope</span>
                        </span>
                        <span class="provider-protocol-pill">OpenAI</span>
                    </span>
                </button>
            `;
        }
        if(item.id === 'runninghub'){
            return `
                <button class="provider-card provider-card-banner ${active} ${stateClass}" type="button" onclick="selectProvider('${escapeHtml(item.id)}')">
                    <span class="provider-banner-inner">
                        <span class="provider-logo-wrap">
                            <img src="/static/images/RunningHub-B.png" alt="RunningHub" class="runninghub-icon ms-icon-light">
                            <img src="/static/images/RunningHub-W.png" alt="RunningHub" class="runninghub-icon ms-icon-dark">
                            <span class="provider-logo-fallback">RunningHub</span>
                        </span>
                        <span class="provider-protocol-pill">RH</span>
                    </span>
                </button>
            `;
        }
        if(item.id === 'volcengine'){
            return `
                <button class="provider-card provider-card-banner ${active} ${stateClass}" type="button" onclick="selectProvider('${escapeHtml(item.id)}')">
                    <span class="provider-banner-inner">
                        <span class="provider-logo-wrap">
                            <img src="/static/images/volcengine-theme-light.svg" alt="火山引擎" class="volcengine-icon ms-icon-light">
                            <img src="/static/images/volcengine-theme-dark.svg" alt="火山引擎" class="volcengine-icon ms-icon-dark">
                            <span class="provider-logo-fallback">火山引擎</span>
                        </span>
                        <span class="provider-protocol-pill">Ark</span>
                    </span>
                </button>
            `;
        }
        return `
            <button class="provider-card provider-card-sortable ${active} ${stateClass}" type="button" onclick="selectProvider('${escapeHtml(item.id)}')"${providerDragAttrs(item)}>
                <span class="provider-drag-handle" aria-hidden="true"><i data-lucide="grip-vertical" class="w-3.5 h-3.5"></i></span>
                <span class="provider-mark"><i data-lucide="${item.has_key ? 'key-round' : 'key'}" class="w-4 h-4"></i></span>
                <span class="provider-info">
                    <div class="provider-name">${escapeHtml(item.name || item.id)}</div>
                    <div class="provider-meta">${escapeHtml(item.base_url || '未配置地址')}</div>
                </span>
                <span class="provider-side-meta">
                    <span class="provider-status-dot"></span>
                    <span class="provider-protocol-pill">${escapeHtml(protocolLabel)}</span>
                </span>
            </button>
        `;
    }).join('');
    renderAgentList();
    refreshIcons();
}
function renderAgentList(){
if(!agentList) return;
ensureAgentRegistry();
const agents = agentRegistry();
agentList.innerHTML = Object.entries(agents).map(([id, item]) => {
    const entry = item || {};
    const active = selectedId === agentPanelId(id) ? 'active' : '';
    const hasKey = Boolean(entry.has_key);
    const stateClass = hasKey ? 'has-key' : 'missing-key';
    const visionName = visionModelName();
    const visionOn = visionEnabledState();
    return `
<button class="provider-card provider-card-compact agent-provider-card ${active} ${stateClass}" type="button" onclick="selectAgent('${escapeHtml(id)}')">
<span class="provider-info">
<span class="provider-name">${escapeHtml(visionName)}</span>
<span class="provider-meta">${visionOn ? '视觉识别已开启' : '视觉识别已关闭'}</span>
</span>
<span class="provider-side-meta">
<span class="provider-status-dot"></span>
<span class="provider-protocol-pill">视觉</span>
</span>
</button>
`;
}).join('');
renderApiSummary();
lucide.createIcons();
}
function handleProviderDragStart(event, id){
    const item = providers.find(provider => provider.id === id);
    if(!item || isFixedProvider(item)){
        event.preventDefault();
        return;
    }
    providerDragId = id;
    event.currentTarget.classList.add('is-dragging');
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', id);
}
function handleProviderDragOver(event, id){
    if(!providerDragId || providerDragId === id || isFixedProvider(id)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    providerList?.querySelectorAll('.provider-card-drop-target').forEach(el => el.classList.remove('provider-card-drop-target'));
    event.currentTarget.classList.add('provider-card-drop-target');
}
function handleProviderDrop(event, targetId){
    event.preventDefault();
    providerList?.querySelectorAll('.provider-card-drop-target').forEach(el => el.classList.remove('provider-card-drop-target'));
    const sourceId = providerDragId || event.dataTransfer.getData('text/plain');
    providerDragId = '';
    if(!sourceId || sourceId === targetId || isFixedProvider(sourceId) || isFixedProvider(targetId)) return;
    const sourceIndex = providers.findIndex(item => item.id === sourceId);
    const targetIndex = providers.findIndex(item => item.id === targetId);
    if(sourceIndex < 0 || targetIndex < 0) return;
    const [moved] = providers.splice(sourceIndex, 1);
    const adjustedTargetIndex = providers.findIndex(item => item.id === targetId);
    providers.splice(adjustedTargetIndex, 0, moved);
    renderProviderList();
    saveProviders();
}
function handleProviderDragEnd(){
    providerDragId = '';
    providerList?.querySelectorAll('.is-dragging,.provider-card-drop-target').forEach(el => {
        el.classList.remove('is-dragging', 'provider-card-drop-target');
    });
}
function renderEditor(){
renderApiSummary();
loadVisionConfig();
if(isAgentPanelSelection()){
    document.body.classList.remove('show-provider-onboarding');
    document.body.classList.remove('show-ms', 'show-runninghub', 'show-volcengine', 'show-volcengine-standalone', 'show-jimeng');
    document.body.classList.add('show-agent-mode');
    ensureAgentRegistry();
    const visionDisplayName = visionModelName();
    editorTitle.textContent = visionDisplayName;
    const agentTitle = document.getElementById('agentBlockTitle');
    if(agentTitle) agentTitle.textContent = visionDisplayName;
    if(runninghubConfigBlock){
        runninghubConfigBlock.hidden = true;
        runninghubConfigBlock.style.display = 'none';
    }
    if(rhPasteInput) rhPasteInput.value = '';
    if(rhAppsList) rhAppsList.innerHTML = '';
    if(rhWorkflowsList) rhWorkflowsList.innerHTML = '';
    if(rhAppsCount) rhAppsCount.textContent = '0';
    if(rhWorkflowsCount) rhWorkflowsCount.textContent = '0';
    if(msLoraBlock) msLoraBlock.style.display = 'none';
    if(jimengCliPanel){
        jimengCliPanel.hidden = true;
        jimengCliPanel.style.display = 'none';
    }
    clearVerifyResult();
    renderAgentConfig();
        renderProviderList();
        refreshIcons();
        return;
    }
    document.body.classList.remove('show-agent-mode');
    const item = provider();
    if(!item) return;
    editorTitle.textContent = item.name || item.id;
    nameInput.value = item.name || '';
    idInput.value = item.id || '';
    updateIdPreview();
    clearVerifyResult();
    baseInput.placeholder = EXAMPLE_BASE_URL;
    baseInput.value = item.base_url || '';
    if(protocolInput) protocolInput.value = isRunningHubProvider(item) ? 'runninghub' : item.id === 'volcengine' ? 'volcengine' : item.id === 'jimeng' ? 'jimeng' : (item.protocol || 'openai');
    keyInput.value = '';
    keyInput.placeholder = item.has_key ? `${tr('api.keepCurrentKey')} ${item.key_preview || ''}` : tr('api.enterKey');
    keyHint.textContent = item.has_key ? `${tr('api.keySaved')}${item.key_env || 'API/.env'}` : tr('api.noKey');
    const isModelScope = item.id === 'modelscope';
    const isRunningHub = isRunningHubProvider(item);
    const isBuiltinRunningHub = isBuiltinRunningHubProvider(item);
    const isVolcengine = item.id === 'volcengine' || String(protocolInput?.value || item.protocol || '').toLowerCase() === 'volcengine';
    const isStandaloneVolcengine = item.id === 'volcengine';
    const isJimeng = item.id === 'jimeng' || String(protocolInput?.value || item.protocol || '').toLowerCase() === 'jimeng';
    if(isRunningHub){
        ensureRunningHubLists(item);
        if(rhFreeKeyInput){
            rhFreeKeyInput.value = '';
            rhFreeKeyInput.placeholder = item.has_key ? `${tr('api.rhKeepCoinKey')} ${item.key_preview || ''}` : tr('api.rhEnterCoinKey');
        }
        if(rhWalletKeyInput){
            rhWalletKeyInput.value = '';
            rhWalletKeyInput.placeholder = item.has_wallet_key ? `${tr('api.rhKeepWalletKey')} ${item.wallet_key_preview || ''}` : tr('api.rhEnterWalletKey');
        }
        if(rhFreeKeyHint) rhFreeKeyHint.textContent = rhFreeKeyHintText(item);
        if(rhWalletKeyHint) rhWalletKeyHint.textContent = rhWalletKeyHintText(item);
        renderRunningHubCards();
    }
    if(isVolcengine){
        item.base_url = item.base_url || VOLCENGINE_DEFAULT_BASE_URL;
        item.protocol = 'volcengine';
        item.volcengine_project_name = item.volcengine_project_name || VOLCENGINE_DEFAULT_PROJECT_NAME;
        item.volcengine_region = item.volcengine_region || VOLCENGINE_DEFAULT_REGION;
        keyInput.placeholder = item.has_key ? `保持当前方舟 API Key ${item.key_preview || ''}` : '输入方舟 API Key';
        keyHint.textContent = volcengineArkKeyHintText(item);
        if(volcArkKeyHint) volcArkKeyHint.textContent = volcengineArkKeyHintText(item);
        if(volcAkInput){
            volcAkInput.value = '';
            volcAkInput.placeholder = item.has_volcengine_access_key ? `保持当前 AK ${item.volcengine_access_key_preview || ''}` : 'Access Key ID';
        }
        if(volcSkInput){
            volcSkInput.value = '';
            volcSkInput.placeholder = item.has_volcengine_secret_key ? `保持当前 SK ${item.volcengine_secret_key_preview || ''}` : 'Secret Access Key';
        }
        if(volcAssetKeyHint) volcAssetKeyHint.textContent = volcengineAssetKeyHintText(item);
        if(volcProjectInput) volcProjectInput.value = item.volcengine_project_name || VOLCENGINE_DEFAULT_PROJECT_NAME;
        if(volcRegionInput) volcRegionInput.value = item.volcengine_region || VOLCENGINE_DEFAULT_REGION;
    }
    if(isJimeng){
        item.base_url = '';
        item.protocol = 'jimeng';
        item.image_models = unique([...(item.image_models || []).filter(model => !JIMENG_LEGACY_IMAGE_MODELS.has(String(model || '').trim())), ...JIMENG_DEFAULT_IMAGE_MODELS]);
        item.video_models = unique([...(item.video_models || []).filter(model => !JIMENG_LEGACY_VIDEO_MODELS.has(String(model || '').trim())), ...JIMENG_DEFAULT_VIDEO_MODELS]);
        keyInput.placeholder = '即梦 CLI 使用本机 dreamina login，无需 API Key';
        keyHint.textContent = '请先在终端安装 dreamina CLI，并执行 dreamina login';
    }
    document.body.classList.toggle('show-ms', isModelScope);
    document.body.classList.toggle('show-runninghub', isBuiltinRunningHub);
    document.body.classList.toggle('show-volcengine', isVolcengine);
    document.body.classList.toggle('show-volcengine-standalone', isStandaloneVolcengine);
    document.body.classList.toggle('show-jimeng', isJimeng);
    renderProviderOnboarding(item);
    renderRecommendApi();
    if(runninghubConfigBlock){
        runninghubConfigBlock.hidden = !isBuiltinRunningHub;
        runninghubConfigBlock.style.display = isBuiltinRunningHub ? 'flex' : 'none';
    }
    if(!isBuiltinRunningHub){
        if(rhPasteInput) rhPasteInput.value = '';
        if(rhAppsList) rhAppsList.innerHTML = '';
        if(rhWorkflowsList) rhWorkflowsList.innerHTML = '';
        if(rhAppsCount) rhAppsCount.textContent = '0';
        if(rhWorkflowsCount) rhWorkflowsCount.textContent = '0';
    }
    if(msLoraBlock) msLoraBlock.style.display = isModelScope ? 'flex' : 'none';
    if(jimengCliPanel){
        jimengCliPanel.hidden = !isJimeng;
        jimengCliPanel.style.display = isJimeng ? 'flex' : 'none';
        if(isJimeng) refreshJimengStatus(false);
    }
    const deleteBtn = document.getElementById('deleteBtn');
    if(deleteBtn) deleteBtn.style.display = isFixedProvider(item) ? 'none' : 'inline-flex';
    renderModels('image');
    renderModels('chat');
    renderModels('video');
    if(isModelScope) renderMsLoras();
    else if(msLoraList) msLoraList.innerHTML = '';
    renderProviderList();
    renderAgentConfig();
    renderAgentList();
}
function showVerifyResult(html){ const el = document.getElementById('verifyResult'); if(el){ el.style.display = 'block'; el.innerHTML = html; } }
function clearVerifyResult(){ const el = document.getElementById('verifyResult'); if(el){ el.style.display = 'none'; el.innerHTML = ''; } }
function prettyJson(value){
    try { return JSON.stringify(value, null, 2); } catch(_) { return String(value || ''); }
}
function jimengCreditText(raw){
    if(!raw) return '';
    const parts = [];
    const seen = new Set();
    const visit = value => {
        if(!value || typeof value !== 'object') return;
        Object.entries(value).forEach(([key, item]) => {
            const low = key.toLowerCase();
            if(/credit|balance|quota|point|coin|积分|余额/.test(low) && item !== null && typeof item !== 'object'){
                const label = `${key}: ${item}`;
                if(!seen.has(label)){ seen.add(label); parts.push(label); }
            }
            if(item && typeof item === 'object') visit(item);
        });
    };
    visit(raw);
    return parts.join(' · ') || prettyJson(raw);
}
function setJimengStatus(text, ok=null){
    if(!jimengCliStatus) return;
    jimengCliStatus.textContent = text || '未检测';
    jimengCliStatus.classList.toggle('ok', ok === true);
    jimengCliStatus.classList.toggle('bad', ok === false);
}
function renderJimengLoginBox(data){
    if(!jimengLoginBox) return;
    const text = data?.text || '';
    const qrUrl = data?.qr_url || '';
    const qrHtml = qrUrl && qrUrl.startsWith('http')
        ? `<img class="jimeng-qr-img" src="${escapeHtml(qrUrl)}" alt="即梦登录二维码">`
        : '';
    jimengLoginBox.hidden = false;
    jimengLoginBox.innerHTML = `${qrHtml}<pre>${escapeHtml(text || '等待 CLI 输出登录二维码...')}</pre>`;
}
let jimengLoginTimer = null;
async function refreshJimengStatus(showCredit=true){
    if(!jimengCliPanel || jimengCliPanel.hidden) return;
    setJimengStatus('检测中...');
    try {
        const data = await fetchLocalJson('/api/jimeng/status', {}, 1800);
        setJimengStatus(data.logged_in ? '已登录' : (data.installed ? '未登录' : '未安装'), data.logged_in === true);
        if(data.installed && data.version_ok === false && jimengCredit){
            jimengCredit.textContent = `⚠ 检测到 dreamina CLI 版本 ${data.cli_version || '未知'}，低于推荐的 ${data.min_version || '1.4.2'}。旧版本任务状态可能无法更新，请升级 CLI。`;
        } else if(showCredit && data.raw && jimengCredit){
            jimengCredit.textContent = jimengCreditText(data.raw);
        }
    } catch(e){
        setJimengStatus('检测失败', false);
        if(jimengCredit) jimengCredit.textContent = e.message || String(e);
    }
}
async function startJimengLogin(){
    setJimengStatus('等待扫码...');
    if(jimengCredit) jimengCredit.textContent = '';
    try {
        const data = await fetch('/api/jimeng/login/start', {method:'POST'}).then(async r => {
            const json = await r.json();
            if(!r.ok) throw new Error(json.detail || '启动登录失败');
            return json;
        });
        renderJimengLoginBox(data);
        clearInterval(jimengLoginTimer);
        jimengLoginTimer = setInterval(pollJimengLogin, 2500);
        refreshIcons();
    } catch(e){
        setJimengStatus('登录失败', false);
        if(jimengLoginBox){
            jimengLoginBox.hidden = false;
            jimengLoginBox.innerHTML = `<pre>${escapeHtml(e.message || String(e))}</pre>`;
        }
    }
}
async function pollJimengLogin(){
    try {
        const data = await fetch('/api/jimeng/login/status').then(r => r.json());
        renderJimengLoginBox(data);
        if(data.logged_in){
            clearInterval(jimengLoginTimer);
            setJimengStatus('已登录', true);
            if(jimengCredit) jimengCredit.textContent = jimengCreditText(data.raw);
        } else if(data.running){
            setJimengStatus('等待扫码...');
        } else {
            setJimengStatus('未登录', false);
        }
    } catch(e){
        clearInterval(jimengLoginTimer);
        setJimengStatus('登录检测失败', false);
    }
}
async function refreshJimengCredit(){
    setJimengStatus('查询余额...');
    try {
        const data = await fetch('/api/jimeng/credit').then(async r => {
            const json = await r.json();
            if(!r.ok) throw new Error(json.detail || '查询余额失败');
            return json;
        });
        setJimengStatus('已登录', true);
        if(jimengCredit) jimengCredit.textContent = jimengCreditText(data.raw);
    } catch(e){
        setJimengStatus('未登录', false);
        if(jimengCredit) jimengCredit.textContent = e.message || String(e);
    }
}
async function logoutJimeng(){
    if(!confirm('确认退出即梦 CLI 登录？')) return;
    try {
        const data = await fetch('/api/jimeng/logout', {method:'POST'}).then(async r => {
            const json = await r.json();
            if(!r.ok) throw new Error(json.detail || '退出登录失败');
            return json;
        });
        setJimengStatus('已退出', false);
        if(jimengCredit) jimengCredit.textContent = prettyJson(data.raw);
        if(jimengLoginBox) jimengLoginBox.hidden = true;
    } catch(e){
        setJimengStatus('退出失败', false);
        if(jimengCredit) jimengCredit.textContent = e.message || String(e);
    }
}
function openJimengHelp(){
    if(!jimengHelpOverlay) return;
    jimengHelpOverlay.style.display = 'flex';
    loadJimengHelp();
}
function closeJimengHelp(){
    if(jimengHelpOverlay) jimengHelpOverlay.style.display = 'none';
}
async function loadJimengHelp(){
    if(!jimengHelpOutput) return;
    jimengHelpOutput.textContent = '加载中...';
    try {
        const command = jimengHelpCommand?.value || '';
        const data = await fetch('/api/jimeng/help', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({command})
        }).then(async r => {
            const json = await r.json();
            if(!r.ok) throw new Error(json.detail || '加载帮助失败');
            return json;
        });
        jimengHelpOutput.textContent = data.text || prettyJson(data.raw);
    } catch(e){
        jimengHelpOutput.textContent = e.message || String(e);
    }
}
function currentProviderApiKey(item){
    if(isRunningHubProvider(item)){
        return rhWalletKeyInput?.value.trim() || rhFreeKeyInput?.value.trim() || '';
    }
    return keyInput.value.trim();
}
function applyDetectedProtocol(protocol){
    const item = provider();
    const detected = String(protocol || '').toLowerCase();
    if(!item || !protocolInput || !['openai', 'apimart', 'gemini', 'runninghub', 'volcengine', 'jimeng'].includes(detected)) return false;
    if(String(protocolInput.value || '').toLowerCase() === detected && String(item.protocol || '').toLowerCase() === detected) return false;
    protocolInput.value = detected;
    item.protocol = detected;
    item.base_url = detected === 'jimeng' ? '' : (baseInput?.value.trim() || item.base_url || '');
    if(detected === 'runninghub'){
        item.base_url = item.base_url || RH_DEFAULT_BASE_URL;
        if(!(item.image_models || []).length) item.image_models = [...RH_DEFAULT_IMAGE_MODELS];
        ensureRunningHubLists(item);
    }
    if(detected === 'volcengine'){
        item.video_models = unique([...(item.video_models || []), ...VOLCENGINE_DEFAULT_VIDEO_MODELS]);
        item.volcengine_project_name = item.volcengine_project_name || VOLCENGINE_DEFAULT_PROJECT_NAME;
        item.volcengine_region = item.volcengine_region || VOLCENGINE_DEFAULT_REGION;
    }
    protocolInput.dispatchEvent(new Event('change'));
    return true;
}

async function probeAsync(){
    const item = provider();
    if(!item) return;
    const btn = document.getElementById('probeAsyncBtn');
    const baseUrl = baseInput.value.trim();
    if(!baseUrl){ alert('请先填写请求地址'); return; }
    if(btn){ btn.disabled = true; btn.querySelector('span').textContent = '检测中...'; }
    showVerifyResult(`<span style="color:var(--muted);font-size:11px;font-weight:700">正在检测协议类型...</span>`);
    try {
        const apiKey = currentProviderApiKey(item);
        const currentProtocol = String(protocolInput?.value || item.protocol || 'openai').toLowerCase();
        const data = await fetch('/api/providers/probe-async', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ base_url: baseUrl, api_key: apiKey, provider_id: item.id, protocol: currentProtocol })
        }).then(async r => {
            if(!r.ok) throw new Error((await r.json()).detail || '请求失败');
            return r.json();
        });
        const detectedProtocol = String(data.protocol || '').toLowerCase();
        const isAsync = data.ok === true && detectedProtocol === 'apimart';
        const isOpenAiCompat = data.ok === true && detectedProtocol === 'openai';
        const keepManualProtocol = ['gemini', 'runninghub', 'volcengine', 'jimeng'].includes(currentProtocol);
        if(protocolInput && !keepManualProtocol){
            applyDetectedProtocol(detectedProtocol || (isAsync ? 'apimart' : 'openai'));
        }
        const rawJson = JSON.stringify(data.raw, null, 2);
        const probeMessage = String(data.message || '');
        const hideTasksEndpointTip = probeMessage.includes('/v1/tasks/');
        const color = (isAsync || isOpenAiCompat || data.ok === true) ? '#15803d' : data.ok === null ? '#b45309' : '#64748b';
        const icon = (isAsync || isOpenAiCompat || data.ok === true) ? '✓' : '⚠';
        const proto = detectedProtocol === 'runninghub'
            ? 'RunningHub'
            : detectedProtocol === 'volcengine'
            ? '方舟/Ark 任务协议'
            : isAsync
                ? 'APIMart 异步'
                : detectedProtocol === 'openai'
                    ? 'OpenAI 兼容'
                    : keepManualProtocol
                    ? (currentProtocol === 'gemini' ? 'Gemini' : currentProtocol.toUpperCase())
                    : 'OpenAI 兼容';
        showVerifyResult(`
            ${hideTasksEndpointTip ? '' : `<div style="font-size:11px;font-weight:800;color:${color}">${icon} ${escapeHtml(probeMessage)}</div>`}
            <div style="font-size:11px;color:var(--muted);font-weight:700;margin-top:2px">${keepManualProtocol ? '协议已验证为' : '协议已自动设置为'}：<strong style="color:var(--text)">${proto}</strong></div>
            <details style="margin-top:6px">
                <summary style="font-size:10.5px;color:var(--muted);cursor:pointer;font-weight:700;user-select:none">▸ 查看原始响应 (HTTP ${data.status_code})</summary>
                <pre style="margin-top:6px;padding:10px 12px;border-radius:10px;background:var(--soft);border:1px solid var(--line-2);font-size:10.5px;font-family:ui-monospace,Menlo,monospace;white-space:pre-wrap;word-break:break-all;color:var(--text);max-height:200px;overflow:auto">${escapeHtml(rawJson)}</pre>
            </details>`);
    } catch(e){
        const keepManualProtocol = ['gemini', 'runninghub', 'volcengine', 'jimeng'].includes(String(protocolInput?.value || item.protocol || '').toLowerCase());
        if(protocolInput && !keepManualProtocol){ protocolInput.value = 'openai'; protocolInput.dispatchEvent(new Event('change')); }
        const suffix = keepManualProtocol ? '，已保留当前手动选择的协议' : '，协议已设为 OpenAI 兼容';
        showVerifyResult(`<div style="font-size:11px;font-weight:800;color:#b45309">⚠ ${escapeHtml(e.message || String(e))}${suffix}</div>`);
    } finally {
        if(btn){ btn.disabled = false; btn.querySelector('span').textContent = '验证协议'; refreshIcons(); }
    }
}

async function testConnection(){
    const item = provider();
    if(!item) return;
    const btn = document.getElementById('testUrlBtn');
    const baseUrl = baseInput.value.trim();
    const isJimeng = item.id === 'jimeng' || (protocolInput?.value || '') === 'jimeng';
    if(!baseUrl && !isJimeng){ alert('请先填写请求地址'); return; }
    if(btn){ btn.disabled = true; btn.querySelector('span').textContent = tr('api.testingUrl') || '验证中...'; }
    showVerifyResult(`<span style="color:var(--muted);font-size:11px;font-weight:700">验证中...</span>`);
    try {
        const apiKey = currentProviderApiKey(item);
        const data = await fetch('/api/providers/test-connection', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ base_url: baseUrl, api_key: apiKey, provider_id: item.id, protocol: protocolInput?.value || 'openai' })
        }).then(async r => {
            if(!r.ok) throw new Error((await r.json()).detail || (tr('api.urlInvalid') || '验证失败'));
            return r.json();
        });
        if(data.ok){
            const detectedProtocol = String(data.protocol || '').toLowerCase();
            if(detectedProtocol && detectedProtocol !== String(protocolInput?.value || '').toLowerCase()){
                applyDetectedProtocol(detectedProtocol);
            }
            // 存入 picker 状态并启用「选择模型」按钮，但不自动弹出
            lastFetchedAll = data.all || [];
            lastFetchedSuggestion = {
                image: new Set(data.image_models || []),
                chat: new Set(data.chat_models || []),
                video: new Set(data.video_models || []),
            };
            const openBtn = document.getElementById('openPickerBtn');
            if(openBtn){ openBtn.disabled = false; openBtn.style.opacity = '1'; }
            const isVolcengineNow = detectedProtocol === 'volcengine' || isVolcengineProvider(item);
            const isRunninghubNow = detectedProtocol === 'runninghub' || isRunningHubProvider(item);
            const volcengineNote = isVolcengineNow
                ? `<div style="margin-top:6px;color:#92400e;font-size:11px;font-weight:700">${detectedProtocol === 'volcengine' ? '已自动识别为方舟/Ark 任务协议。' : ''}火山协议提示：模型列表只代表可见模型，聊天模型建议填写你在方舟控制台创建的 <code>ep-...</code> 推理接入点。</div>`
                : '';
            const runninghubNote = isRunninghubNow
                ? `<div style="margin-top:6px;color:#92400e;font-size:11px;font-weight:700">RunningHub 不提供稳定的统一模型列表接口。这里返回的是内置/手动维护的标准模型端点；AI App / Workflow 请使用 <code>app:ID</code> 或 <code>workflow:ID</code>。</div>`
                : '';
            const jimengNote = isJimeng ? `<div style="margin-top:6px;color:#15803d;font-size:11px;font-weight:700">即梦 CLI 已可用，可在画布里选择“即梦 CLI”生成。</div>` : '';
            const verifyMsg = data.message
                ? `<div style="margin-top:6px;color:#15803d;font-size:11px;font-weight:700">${escapeHtml(String(data.message).slice(0,200))}</div>`
                : '';
            showVerifyResult(`<span style="color:#15803d;font-size:11px;font-weight:800">✓ 地址验证通过${data.model_count ? ` · 找到 ${data.model_count} 个模型` : ''}</span>${verifyMsg}${volcengineNote}${runninghubNote}${jimengNote}`);
        } else {
            showVerifyResult(`
                <div style="font-size:11px;font-weight:800;color:#b45309">⚠ 地址验证未通过 (HTTP ${data.status})</div>
                <div style="font-size:11px;color:var(--muted);font-weight:600;margin-top:3px">${escapeHtml((data.message || '').slice(0,200))}</div>`);
        }
    } catch(e){
        showVerifyResult(`<div style="font-size:11px;font-weight:800;color:#b45309">⚠ ${escapeHtml(e.message || String(e))}</div>`);
    } finally {
        if(btn){ btn.disabled = false; btn.querySelector('span').textContent = tr('api.testUrl') || '验证地址'; }
    }
}
let lastFetchedAll = [];          // 全部模型 id 列表
let lastFetchedSuggestion = null; // 后端自动分类建议
const apiSettingsPickerHelper = window.WcsApiSettingsPicker || null;
const apiSettingsProviderRepair = window.WcsApiSettingsProviderRepair || null;


async function fetchModels(){
 const item = provider();
 if(!item) return;
 syncEditor();
 const btn = document.getElementById('fetchModelsBtn');
 const baseUrl = baseInput.value.trim();
 const apiKey = currentProviderApiKey(item);
 const isJimeng = item.id === 'jimeng' || (protocolInput?.value || '') === 'jimeng';
 if(!baseUrl && !isJimeng){
 alert('请先填写请求地址');
 return;
 }
 if(btn){
     btn.disabled = true;
     btn.querySelector('span').textContent = tr('api.fetchingModels') || '拉取中...';
 }
 lastFetchedAll = [];
 lastFetchedSuggestion = null;
 const openBtn = document.getElementById('openPickerBtn');
 if(openBtn){
     openBtn.disabled = true;
     openBtn.style.opacity = '0.5';
 }
 setStatus(tr('api.fetchingModels') || '正在从上游拉取模型列表...');
 try {
 const data = await fetch('/api/providers/fetch-models', {
 method:'POST',
 headers:{'Content-Type':'application/json'},
 body:JSON.stringify({
 base_url:baseUrl,
 api_key:apiKey,
 provider_id:item.id,
 protocol:protocolInput?.value || 'openai'
 })
 }).then(async r => {
 if(!r.ok) throw new Error((await r.json()).detail || (tr('api.urlInvalid') || '拉取失败'));
 return r.json();
 });
 lastFetchedAll = data.all || [];
 lastFetchedSuggestion = {
 image: new Set(data.image_models || []),
 chat: new Set(data.chat_models || []),
 video: new Set(data.video_models || []),
 };
 item.available_image_models = unique(data.image_models || []);
 item.available_chat_models = unique(data.chat_models || []);
 item.available_video_models = unique(data.video_models || []);
 const detectedProtocol = String(data.protocol || '').toLowerCase();
 if(detectedProtocol && detectedProtocol !== String(protocolInput?.value || '').toLowerCase()){
 applyDetectedProtocol(detectedProtocol);
 }
    if(openBtn){
        openBtn.disabled = false;
        openBtn.style.opacity = '1';
    }
    const extra = (detectedProtocol === 'volcengine' || isVolcengineProvider(item))
        ? ' · 已识别方舟协议，火山聊天建议改填 ep-... 接入点'
        : ((detectedProtocol === 'runninghub' || isRunningHubProvider(item))
            ? ' · RunningHub 已按官方文档实时同步模型'
            : '');
    setStatus(`已拉取 ${data.total} 个模型 · 点「选择模型」勾选要导入的${extra}`);
    openModelPicker();
 } catch(e){
    lastFetchedAll = [];
    lastFetchedSuggestion = null;
    alert('拉取失败：' + (e.message || e));
    setStatus('拉取失败');
 } finally {
 if(btn){
 btn.disabled = false;
 btn.querySelector('span').textContent = tr('api.fetchModels') || '拉取模型';
 }
 }
}

// —— 模型选择器浮层 ——
// 每个模型只归一类（根据用户已配置 或 关键字猜测）；勾选 = 纳入该分类
let pickerState = { category: {}, selected: {} };
let pickerVisibleIds = [];
function openModelPicker(){
    const item = provider();
    if(!item || !lastFetchedAll.length){ alert('没有拉取到模型'); return; }
    const existing = { image: new Set(item.image_models||[]), chat: new Set(item.chat_models||[]), video: new Set(item.video_models||[]) };
    const allIds = new Set([...lastFetchedAll, ...(item.image_models||[]), ...(item.chat_models||[]), ...(item.video_models||[])]);
    pickerState = { category: {}, selected: {} };
    allIds.forEach(id => {
        // 类别归属：用户已配置 > 关键字建议 > 默认 chat
        let cat;
        if(existing.image.has(id)) cat = 'image';
        else if(existing.video.has(id)) cat = 'video';
        else if(existing.chat.has(id)) cat = 'chat';
        else if(lastFetchedSuggestion?.image?.has(id)) cat = 'image';
        else if(lastFetchedSuggestion?.video?.has(id)) cat = 'video';
        else cat = 'chat';
        pickerState.category[id] = cat;
        // 默认勾选状态：已在用户配置里的 = 勾选；新拉的 = 不勾选（让用户主动选）
        pickerState.selected[id] = existing.image.has(id) || existing.chat.has(id) || existing.video.has(id);
    });
    // 默认 tab 切回「全部」
    document.querySelectorAll('.picker-cat-tab').forEach(t => t.classList.toggle('active', t.dataset.cat === 'all'));
    document.getElementById('modelPickerOverlay').style.display = 'flex';
    renderModelPicker();
}
function openModelPicker(){
 const item = provider();
 if(!item || !lastFetchedAll.length){ alert('没有拉取到模型'); return; }
 const existing = { image: new Set(item.image_models||[]), chat: new Set(item.chat_models||[]), video: new Set(item.video_models||[]) };
 const built = typeof apiSettingsPickerHelper?.buildModelPickerState === 'function'
   ? apiSettingsPickerHelper.buildModelPickerState(
       lastFetchedAll,
       {
         image:[...existing.image],
         chat:[...existing.chat],
         video:[...existing.video],
       },
       lastFetchedSuggestion || {},
     )
   : { ids:[...new Set(lastFetchedAll)].sort(), category:{}, selected:{} };
 pickerState = { category: built.category || {}, selected: built.selected || {} };
 document.querySelectorAll('.picker-cat-tab').forEach(t => t.classList.toggle('active', t.dataset.cat === 'all'));
 document.getElementById('modelPickerOverlay').style.display = 'flex';
 renderModelPicker();
}
function closeModelPicker(){ document.getElementById('modelPickerOverlay').style.display = 'none'; }
function renderModelPicker(){
    const filter = (document.getElementById('pickerFilter')?.value || '').toLowerCase();
    const currentTab = document.querySelector('.picker-cat-tab.active')?.dataset.cat || 'all';
    const ids = Object.keys(pickerState.category).sort();
    // 各分类总数 / 已选数
    const totals = { all: ids.length, image:0, chat:0, video:0 };
    const selecteds = { all:0, image:0, chat:0, video:0 };
    ids.forEach(id => {
        const cat = pickerState.category[id];
        totals[cat]++;
        if(pickerState.selected[id]){ selecteds[cat]++; selecteds.all++; }
    });
    // 过滤显示
    const list = ids.filter(id => {
        if(filter && !id.toLowerCase().includes(filter)) return false;
        if(currentTab === 'all') return true;
        return pickerState.category[id] === currentTab;
    });
    pickerVisibleIds = list;
    document.getElementById('pickerCount').textContent = `共 ${totals.all} 个模型 · 当前显示 ${list.length} 个`;
    document.querySelectorAll('.picker-cat-tab').forEach(tab => {
        const cat = tab.dataset.cat;
        tab.querySelector('.cat-count').textContent = `${selecteds[cat]}/${totals[cat]}`;
    });
    // 列表
    const html = list.map((id, index) => {
        const checked = pickerState.selected[id];
        return `
            <div class="picker-row ${checked?'has-sel':''}" onclick="togglePickerRowByIndex(${index})">
                <div class="picker-checkbox ${checked?'checked':''}">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
                </div>
                <div class="picker-model-name" title="${escapeAttr(id)}">${escapeHtml(id)}</div>
            </div>
        `;
    }).join('');
    document.getElementById('pickerList').innerHTML = html || `<div style="padding:32px;text-align:center;color:var(--faint);font-size:12px">无匹配</div>`;
    // 底部汇总
    const sumImage = document.getElementById('sumImage');
    const sumChat = document.getElementById('sumChat');
    const sumVideo = document.getElementById('sumVideo');
    const sumUnsel = document.getElementById('sumUnsel');
    if(sumImage){ sumImage.textContent = `生图 ${selecteds.image}`; sumImage.classList.toggle('picker-sum-chip-empty', selecteds.image === 0); }
    if(sumChat){ sumChat.textContent = `LLM ${selecteds.chat}`; sumChat.classList.toggle('picker-sum-chip-empty', selecteds.chat === 0); }
    if(sumVideo){ sumVideo.textContent = `视频 ${selecteds.video}`; sumVideo.classList.toggle('picker-sum-chip-empty', selecteds.video === 0); }
    if(sumUnsel){ sumUnsel.textContent = `未选 ${totals.all - selecteds.all}`; }
}
function togglePickerRow(id){
    pickerState.selected[id] = !pickerState.selected[id];
    renderModelPicker();
}
function togglePickerRowByIndex(index){
    const id = pickerVisibleIds[index];
    if(typeof id !== 'string') return;
    togglePickerRow(id);
}
function selectPickerCat(cat){
    document.querySelectorAll('.picker-cat-tab').forEach(t => t.classList.toggle('active', t.dataset.cat === cat));
    renderModelPicker();
}
function applyModelPicker(){
    const item = provider(); if(!item) return;
    const image = [], chat = [], video = [];
    Object.entries(pickerState.selected).forEach(([id, sel]) => {
        if(!sel) return;
        const cat = pickerState.category[id];
        if(cat === 'image') image.push(id);
        else if(cat === 'video') video.push(id);
        else chat.push(id);
    });
    item.image_models = image;
    item.chat_models = chat;
    item.video_models = video;
    renderModels('image'); renderModels('chat'); renderModels('video');
    renderMsLoras();
    setStatus(`已应用 · 生图 ${image.length} / LLM ${chat.length} / 视频 ${video.length}，点保存生效`);
    closeModelPicker();
}
async function saveKeyOnly(){
    const item = provider();
    if(!item) return;
    const key = keyInput.value.trim();
    if(!key){ alert(tr('api.enterKeyAlert') || '请输入 Key'); return; }
    item.api_key = key;
    const ok = await saveProviders();
    if(ok) keyInput.value = '';
}
async function clearKeyOnly(){
    const item = provider();
    if(!item) return;
    if(!item.has_key && !keyInput.value){ return; }
    if(!confirm(tr('api.confirmClearKey') || '确认清除当前 Key？')) return;
    item._clearKey = true;
    const ok = await saveProviders();
    if(ok) keyInput.value = '';
}
const FIXED_PROTOCOL_PROVIDER_IDS = new Set(['modelscope', 'volcengine', 'jimeng', 'runninghub']);
function providerSupportsModelProtocol(item){
    return Boolean(item) && !FIXED_PROTOCOL_PROVIDER_IDS.has(item.id) && !isRunningHubProvider(item);
}
function modelProtocolSelectHtml(kind, index, model, item){
    if(kind === 'video' || !providerSupportsModelProtocol(item)) return '';
    const map = (item.model_protocols && typeof item.model_protocols === 'object') ? item.model_protocols : {};
    const current = String(map[String(model || '').trim()] || '').toLowerCase();
    const opt = (val, label) => `<option value="${val}" ${current === val ? 'selected' : ''}>${label}</option>`;
    return `<select class="model-protocol-select" title="该模型使用的协议，默认跟随平台全局协议" onchange="updateModelProtocol('${kind}', ${index}, this.value)">
        <option value="" ${current === '' ? 'selected' : ''}>默认</option>
        ${opt('openai', 'OpenAI')}
        ${opt('gemini', 'Gemini')}
    </select>`;
}
function renderModels(kind){
 const item = provider();
 const key = kind === 'image' ? 'image_models' : kind === 'video' ? 'video_models' : 'chat_models';
 const list = kind === 'image' ? imageModelList : kind === 'video' ? videoModelList : chatModelList;
 const models = item?.[key] || [];
 if(!models.length){
 list.innerHTML = `<div class="empty">${tr('api.noModels')}</div>`;
 return;
 }
 const showProtocol = kind !== 'video' && providerSupportsModelProtocol(item);
 const displayNames = modelDisplayNameMap(item);
 list.innerHTML = models.map((model, index) => `
 <div class="model-row${showProtocol ? ' has-protocol' : ''}">
 <div class="model-row-main">
 <label class="model-subfield">
 <span class="model-subfield-label">模型值</span>
 ${renderModelValueControl(item, kind, index, model)}
 </label>
 <label class="model-subfield">
 <span class="model-subfield-label">显示名</span>
 <input class="model-alias-input" data-model-kind="${kind}" data-model-index="${index}" value="${escapeAttr(displayNames[String(model || '').trim()] || '')}" placeholder="显示名称（选填）" oninput="updateModelDisplayName('${kind}', ${index}, this.value)">
 </label>
 </div>
 ${modelProtocolSelectHtml(kind, index, model, item)}
 <button class="icon-btn" type="button" onclick="removeModel('${kind}', ${index})" title="删除"><i data-lucide="trash-2" class="w-4 h-4"></i></button>
 </div>
 `).join('');
 refreshIcons();
 if(kind === 'chat') renderAgentModelOptions();
}

function msLoraTargetOptions(selected){
 const item = provider();
 const models = unique([selected, ...MS_BUILTIN_IMAGE_MODELS, ...((item?.image_models) || [])]);
 return models.filter(Boolean).map(model => `<option value="${escapeAttr(model)}" ${model === selected ? 'selected' : ''}>${escapeHtml(model)}</option>`).join('');
}
function normalizeLoraStrength(value){
    const n = Number(value);
    if(!Number.isFinite(n)) return 0.8;
    return Math.max(0, Math.min(2, n));
}
function renderMsLoras(){
    const item = provider();
    if(!msLoraList || !item || item.id !== 'modelscope') return;
    item.ms_loras = Array.isArray(item.ms_loras) ? item.ms_loras : [];
    if(!item.ms_loras.length){
        msLoraList.innerHTML = `<div class="lora-empty">${tr('api.loraEmpty')}</div>`;
        return;
    }
    msLoraList.innerHTML = item.ms_loras.map((lora, index) => {
        const target = lora.target_model || lora.model || MS_BUILTIN_IMAGE_MODELS[0];
        const strength = normalizeLoraStrength(lora.strength ?? lora.default_strength ?? 0.8);
        return `
            <div class="lora-row">
                <label class="lora-field">
                    <span>${tr('api.loraId')}</span>
                    <input value="${escapeAttr(lora.id || '')}" placeholder="${escapeAttr(tr('api.loraIdPlaceholder'))}" oninput="updateMsLora(${index}, 'id', this.value)">
                </label>
                <label class="lora-field">
                    <span>${tr('api.loraTargetModel')}</span>
                    <select onchange="updateMsLora(${index}, 'target_model', this.value)">${msLoraTargetOptions(target)}</select>
                </label>
                <label class="lora-field">
                    <span>${tr('api.loraDefaultStrength')}</span>
                    <input type="number" min="0" max="2" step="0.05" value="${strength}" oninput="updateMsLora(${index}, 'strength', this.value)">
                </label>
                <button class="icon-btn" type="button" onclick="removeMsLora(${index})" title="${escapeAttr(tr('common.delete'))}"><i data-lucide="trash-2" class="w-4 h-4"></i></button>
            </div>
        `;
    }).join('');
    refreshIcons();
}
function addMsLora(){
    const item = provider();
    if(!item || item.id !== 'modelscope') return;
    item.ms_loras = Array.isArray(item.ms_loras) ? item.ms_loras : [];
    item.ms_loras.push({
        id:'',
        name:'',
        target_model: (item.image_models || [])[0] || MS_BUILTIN_IMAGE_MODELS[0],
        strength:0.8,
        enabled:true,
        note:''
    });
    renderMsLoras();
}
function updateMsLora(index, field, value){
    const item = provider();
    if(!item || item.id !== 'modelscope') return;
    item.ms_loras = Array.isArray(item.ms_loras) ? item.ms_loras : [];
    const lora = item.ms_loras[index];
    if(!lora) return;
    if(field === 'strength') lora.strength = normalizeLoraStrength(value);
    else lora[field] = value;
}
function removeMsLora(index){
    const item = provider();
    if(!item || item.id !== 'modelscope') return;
    item.ms_loras = Array.isArray(item.ms_loras) ? item.ms_loras : [];
    item.ms_loras.splice(index, 1);
    renderMsLoras();
}
async function selectProvider(id){
if(isProviderTemporarilyHidden(providers.find(item => item.id === id))) return;
recommendInlineOpen = false;
syncRecommendView();
renderRecommendApi();
if(selectedId !== AGENT_PANEL_ID) syncEditor();
selectedId = id;
renderEditor();
if(id === 'runninghub'){
await refreshRunningHubProviderFromApi();
renderEditor();
}
}
function selectAgent(id){
    selectedAgentId = String(id || 'codex');
    recommendInlineOpen = false;
    syncRecommendView();
    renderRecommendApi();
    if(!String(selectedId || '').startsWith('__agent_')) syncEditor();
    selectedId = agentPanelId(selectedAgentId);
    renderEditor();
}
function selectCodexAgent(){ selectAgent('codex'); }
function addProvider(){
    recommendInlineOpen = false;
    syncRecommendView();
    renderRecommendApi();
    syncEditor();
    let id = 'custom-api';
    let index = 2;
    while(providers.some(item => item.id === id)) id = `custom-api-${index++}`;
    providers.push({id, name:'API', base_url:'', protocol:'openai', image_generation_endpoint:'', image_edit_endpoint:'', enabled:true, primary:false, image_models:[], chat_models:[], video_models:[], has_key:false, key_preview:''});
    selectedId = id;
    renderEditor();
}
function deleteProvider(){
    const item = provider();
    if(!item) return;
    if(isFixedProvider(item)){ alert(tr('api.defaultNoDelete') || '默认平台不能删除'); return; }
    if(providers.length <= 1){ alert(tr('api.keepOne')); return; }
    providers = providers.filter(p => p.id !== item.id);
    selectedId = providers[0]?.id || '';
    renderEditor();
    saveProviders();
}
async function saveRhKeyOnly(kind){
    const item = provider();
    if(!isRunningHubProvider(item)) return;
    const input = kind === 'wallet' ? rhWalletKeyInput : rhFreeKeyInput;
    const key = input?.value.trim() || '';
    if(!key){ alert('请输入 Key'); return; }
    syncEditor();
    const ok = await saveProviders();
    if(ok && input) input.value = '';
}
async function clearRhKeyOnly(kind){
    const item = provider();
    if(!isRunningHubProvider(item)) return;
    if(!confirm(tr('api.confirmClearKey') || '确认清除当前 Key？')) return;
    if(kind === 'wallet') item._clearWalletKey = true;
    else item._clearKey = true;
    const ok = await saveProviders();
    if(ok){
        if(kind === 'wallet' && rhWalletKeyInput) rhWalletKeyInput.value = '';
        if(kind !== 'wallet' && rhFreeKeyInput) rhFreeKeyInput.value = '';
    }
}
async function saveVolcengineAssetKeys(){
    const item = provider();
    if(!item || item.id !== 'volcengine') return;
    const ak = volcAkInput?.value.trim() || '';
    const sk = volcSkInput?.value.trim() || '';
    if(!ak && !sk){ alert('请输入火山素材库 AK 或 SK'); return; }
    syncEditor();
    const ok = await saveProviders();
    if(ok){
        if(volcAkInput) volcAkInput.value = '';
        if(volcSkInput) volcSkInput.value = '';
    }
}
async function clearVolcengineAssetKeys(){
    const item = provider();
    if(!item || item.id !== 'volcengine') return;
    if(!confirm('确认清除火山素材库 AK/SK？')) return;
    item._clearVolcengineAccessKey = true;
    item._clearVolcengineSecretKey = true;
    const ok = await saveProviders();
    if(ok){
        if(volcAkInput) volcAkInput.value = '';
        if(volcSkInput) volcSkInput.value = '';
    }
}
function addModel(kind){
  const item = provider();
  const key = kind === 'image' ? 'image_models' : kind === 'video' ? 'video_models' : 'chat_models';
  item[key] = [...(item[key] || []), ''];
  if(!item.model_display_names || typeof item.model_display_names !== 'object') item.model_display_names = {};
  renderModels(kind);
  if(kind === 'chat') renderAgentConfig();
  if(kind === 'image') renderMsLoras();
}
function modelProtocolStillUsed(item, name){
    if(!item || !name) return false;
    const lists = ['image_models', 'chat_models', 'video_models'];
    return lists.some(k => Array.isArray(item[k]) && item[k].includes(name));
}
function updateModel(kind, index, value){
  const item = provider();
  const key = kind === 'image' ? 'image_models' : kind === 'video' ? 'video_models' : 'chat_models';
  const oldName = String(item[key][index] || '').trim();
  const newName = String(value || '').trim();
  item[key][index] = value;
  if(!item.model_display_names || typeof item.model_display_names !== 'object') item.model_display_names = {};
  if(oldName && oldName !== newName && Object.prototype.hasOwnProperty.call(item.model_display_names, oldName)){
    const alias = String(item.model_display_names[oldName] || '').trim();
    delete item.model_display_names[oldName];
    if(newName && alias) item.model_display_names[newName] = alias;
  }
  // 重命名时迁移该模型的协议覆盖
  if(item.model_protocols && typeof item.model_protocols === 'object' && oldName && oldName !== newName){
    if(Object.prototype.hasOwnProperty.call(item.model_protocols, oldName)){
            const proto = item.model_protocols[oldName];
            // 旧名称在其他列表里不再使用时才删除旧键
            const stillUsedElsewhere = (() => {
                const lists = ['image_models', 'chat_models', 'video_models'];
                return lists.some(k => Array.isArray(item[k]) && item[k].some((m, i) => !(k === key && i === index) && String(m || '').trim() === oldName));
            })();
            if(!stillUsedElsewhere) delete item.model_protocols[oldName];
            if(newName) item.model_protocols[newName] = proto;
        }
    }
  if(kind === 'chat') renderAgentModelOptions();
  if(kind === 'image') renderMsLoras();
}
function updateModelDisplayName(kind, index, value){
  const item = provider();
  const key = kind === 'image' ? 'image_models' : kind === 'video' ? 'video_models' : 'chat_models';
  const name = String(item[key]?.[index] || '').trim();
  if(!name) return;
  if(!item.model_display_names || typeof item.model_display_names !== 'object') item.model_display_names = {};
  const label = String(value || '').trim();
  if(label) item.model_display_names[name] = label;
  else delete item.model_display_names[name];
}
function syncModelDisplayNameInputs(){
  const item = provider();
  if(!item) return;
  if(!item.model_display_names || typeof item.model_display_names !== 'object') item.model_display_names = {};
  document.querySelectorAll('.model-alias-input[data-model-kind][data-model-index]').forEach(input => {
    const kind = input.dataset.modelKind;
    const index = Number(input.dataset.modelIndex);
    if(!Number.isInteger(index)) return;
    const key = kind === 'image' ? 'image_models' : kind === 'video' ? 'video_models' : 'chat_models';
    const name = String(item[key]?.[index] || '').trim();
    if(!name) return;
    const label = String(input.value || '').trim();
    if(label) item.model_display_names[name] = label;
    else delete item.model_display_names[name];
  });
}
function updateModelProtocol(kind, index, value){
  const item = provider();
  const key = kind === 'image' ? 'image_models' : kind === 'video' ? 'video_models' : 'chat_models';
  const name = String(item[key]?.[index] || '').trim();
    if(!name) return;
    if(!item.model_protocols || typeof item.model_protocols !== 'object') item.model_protocols = {};
    const proto = String(value || '').trim().toLowerCase();
    if(proto === 'openai' || proto === 'gemini'){
        item.model_protocols[name] = proto;
    } else {
        delete item.model_protocols[name];
    }
}
function removeModel(kind, index){
  const item = provider();
  const key = kind === 'image' ? 'image_models' : kind === 'video' ? 'video_models' : 'chat_models';
  const removed = String(item[key][index] || '').trim();
  item[key].splice(index, 1);
  if(removed && item.model_display_names && typeof item.model_display_names === 'object' && !modelProtocolStillUsed(item, removed)){
    delete item.model_display_names[removed];
  }
  // 清理不再使用的协议覆盖
  if(removed && item.model_protocols && typeof item.model_protocols === 'object' && !modelProtocolStillUsed(item, removed)){
    delete item.model_protocols[removed];
  }
    renderModels(kind);
    if(kind === 'chat') renderAgentConfig();
    if(kind === 'image') renderMsLoras();
}
async function loadProviders(){
  setStatus(tr('api.loading'));
  try {
    const [data] = await Promise.all([
      fetchLocalJson('/api/providers'),
      loadAppConfig()
    ]);
    providers = (data.providers || []).map(item => {
      const next = {
        ...item,
        model_display_names:(item?.model_display_names && typeof item.model_display_names === 'object') ? {...item.model_display_names} : {}
      };
      if(typeof apiSettingsProviderRepair?.repairProviderModelListsFromDisplayNames === 'function'){
        apiSettingsProviderRepair.repairProviderModelListsFromDisplayNames(next);
      }
      repairProviderRhModelAliases(next);
      applyDefaultRhModelDisplayNames(next);
      return next;
    });
selectedId = sortedProviders()[0]?.id || '';
renderEditor();
if(selectedId === 'runninghub'){
await refreshRunningHubProviderFromApi();
renderEditor();
}
maybeOpenSetupWizard();
setStatus('');
    } catch(err) {
        setStatus(tr('api.loadFailed'));
    }
}
async function saveProviders(){
    // The input handler updates the live object, but read the rendered fields once more
    // so a save cannot lose an alias after a rerender or a stale WebView event.
    syncModelDisplayNameInputs();
    syncEditor();
    const incompleteCustom = providers.find(item =>
        /^custom-api(-\d+)?$/.test(String(item.id || '')) &&
        !String(item.base_url || '').trim()
    );
    if(incompleteCustom){
        alert('自定义平台「' + (incompleteCustom.name || incompleteCustom.id) + '」还没有填写请求地址。\n\n请在左侧选中该平台，在“基本信息”的“请求地址”填入上游地址（例如 https://ark.cn-beijing.volces.com/api/v3），再点“验证地址”拉取模型后保存。\n\n没有请求地址的自定义平台不会出现在画布的“LLM平台”下拉里——这就是画布“读不到”它的原因。若不需要该平台，请在左侧选中后删除。');
        return false;
    }
    providers.forEach(item => {
        item.id = normalizeId(item.id);
        item.protocol = isRunningHubProvider(item)
            ? 'runninghub'
            : item.id === 'runninghub'
            ? 'runninghub'
            : item.id === 'volcengine'
            ? 'volcengine'
            : item.id === 'jimeng'
            ? 'jimeng'
            : ['openai', 'apimart', 'gemini', 'runninghub', 'volcengine', 'jimeng'].includes(String(item.protocol || '').toLowerCase()) ? String(item.protocol).toLowerCase() : 'openai';
        if(item.id === 'jimeng') item.base_url = '';
        if(item.id === 'jimeng') item.video_models = unique([...(item.video_models || []).filter(model => !JIMENG_LEGACY_VIDEO_MODELS.has(String(model || '').trim())), ...JIMENG_DEFAULT_VIDEO_MODELS]);
    item.image_generation_endpoint = '';
    item.image_edit_endpoint = '';
    item.image_models = unique(item.image_models || []);
    item.chat_models = unique(item.chat_models || []);
    item.video_models = unique(item.video_models || []);
    repairProviderRhModelAliases(item);
    sanitizeModelDisplayNames(item);
    if(isBuiltinRunningHubProvider(item)){
        item.rh_apps = normalizeRhEntries(item.rh_apps || [], 'app');
        item.rh_workflows = normalizeRhEntries(item.rh_workflows || [], 'workflow');
    } else {
        item.rh_apps = [];
        item.rh_workflows = [];
    }
    item.ms_loras = (Array.isArray(item.ms_loras) ? item.ms_loras : []).map(lora => ({
            id:String(lora.id || '').trim(),
            name:String(lora.name || lora.id || '').trim(),
            target_model:String(lora.target_model || '').trim(),
            strength:normalizeLoraStrength(lora.strength ?? 0.8),
            enabled:lora.enabled !== false,
            note:String(lora.note || '').trim()
        })).filter(lora => lora.id && lora.target_model);
    });
    if(new Set(providers.map(item => item.id)).size !== providers.length){
        alert(tr('api.duplicateId'));
        return false;
    }
    setStatus(tr('api.saving'));
    try {
        const res = await fetch('/api/providers', {
            method:'PUT',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify(providers.map(item => ({
                id:item.id,
                name:item.name,
                base_url:item.base_url,
                protocol:(item.id === 'modelscope') ? 'openai' : isRunningHubProvider(item) ? 'runninghub' : item.id === 'volcengine' ? 'volcengine' : item.id === 'jimeng' ? 'jimeng' : (item.protocol || 'openai'),
                image_generation_endpoint:item.image_generation_endpoint || '',
                image_edit_endpoint:item.image_edit_endpoint || '',
        enabled:item.enabled !== false,
        primary:false,
        image_models:item.image_models || [],
        chat_models:item.chat_models || [],
        video_models:item.video_models || [],
        model_display_names:(item.model_display_names && typeof item.model_display_names === 'object') ? item.model_display_names : {},
        model_protocols:(item.model_protocols && typeof item.model_protocols === 'object') ? item.model_protocols : {},
        ms_loras:item.id === 'modelscope' ? (item.ms_loras || []) : [],
                ms_defaults_version:item.id === 'modelscope' ? (item.ms_defaults_version || 1) : 0,
                rh_apps:isBuiltinRunningHubProvider(item) ? (item.rh_apps || []) : [],
                rh_workflows:isBuiltinRunningHubProvider(item) ? (item.rh_workflows || []) : [],
                volcengine_project_name:item.id === 'volcengine' ? (item.volcengine_project_name || VOLCENGINE_DEFAULT_PROJECT_NAME) : '',
                volcengine_region:item.id === 'volcengine' ? (item.volcengine_region || VOLCENGINE_DEFAULT_REGION) : '',
                volcengine_access_key_id:item.volcengine_access_key_id || undefined,
                volcengine_secret_access_key:item.volcengine_secret_access_key || undefined,
                api_key:item.api_key || undefined,
                wallet_api_key:item.wallet_api_key || undefined,
                clear_key:item._clearKey === true,
                clear_wallet_key:item._clearWalletKey === true,
                clear_volcengine_access_key_id:item._clearVolcengineAccessKey === true,
                clear_volcengine_secret_access_key:item._clearVolcengineSecretKey === true
            })))
        });
        if(!res.ok) throw new Error((await res.json()).detail || tr('api.saveFailed'));
        const data = await res.json();
        providers = (data.providers || providers).filter(item => !REMOVED_NATIVE_PROVIDER_IDS.has(item?.id));
        providers.forEach(item => {
            delete item.api_key;
            delete item.wallet_api_key;
            delete item.volcengine_access_key_id;
            delete item.volcengine_secret_access_key;
            delete item._clearKey;
            delete item._clearWalletKey;
            delete item._clearVolcengineAccessKey;
            delete item._clearVolcengineSecretKey;
        });
selectedId = provider()?.id || providers[0]?.id || '';
renderEditor();
if(selectedId === 'runninghub') markRhConfigSaved();
setStatus(tr('api.saved'));
        // 广播变更，画布等其他 iframe 立即重新拉取最新平台/模型列表
        broadcastStudioApiChange('providers-changed');
        return true;
    } catch(err) {
        setStatus(err.message || tr('api.saveFailed'));
        return false;
    }
}
function escapeHtml(str){
    return String(str || '').replace(/[&<>"']/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]));
}
function escapeAttr(str){ return escapeHtml(str).replace(/`/g, '&#96;'); }
window.addEventListener('message', event => {
    if(event.data?.type === 'studio-theme' && window.StudioTheme) window.StudioTheme.set(event.data.theme);
    if(event.data?.type === 'studio-lang' && window.StudioI18n) {
        window.StudioI18n.set(event.data.lang);
        if(recommendInlineOpen) renderRecommendApi();
        else renderEditor();
    }
});
rhWorkflowEditorOverlay?.addEventListener('mousedown', event => {
    if(event.target === rhWorkflowEditorOverlay) closeRhWorkflowEditor();
});
document.addEventListener('keydown', event => {
    if(event.key === 'Escape' && rhWorkflowEditorState.open) closeRhWorkflowEditor();
    if(event.key === 'Escape' && setupWizardOverlay?.classList.contains('open')) dismissSetupWizard();
});
document.addEventListener('mousedown', event => {
    if(!rhWorkflowEditorState.open) return;
    const pop = document.getElementById('rhNodePopover');
    if(!pop) return;
    if(pop.contains(event.target)) return;
    if(event.target.closest('.rh-editor-gnode,.rh-app-field-card')) return;
    closeRhNodePopover();
});
recommendApiOverlay?.addEventListener('mousedown', event => {
    if(event.target === recommendApiOverlay) closeRecommendApi();
});
setupWizardOverlay?.addEventListener('mousedown', event => {
    if(event.target === setupWizardOverlay) dismissSetupWizard();
});
window.addEventListener('studio-lang-change', () => {
    syncRecommendView();
    if(recommendInlineOpen) renderRecommendApi();
    else renderEditor();
});

/* 统一保存入口：根据当前视图调用正确的保存函数 */
async function handlePageSave(){
    const item = provider();
    if(!item) { saveProviders(); return; }
    if(item.id === 'modelscope' && !providerOnboardingCard.hidden){
        await saveKeyOnly();
        return;
    }
    if(item.id === 'runninghub' && !providerOnboardingCard.hidden){
        await saveOnboardingRunningHubKey();
        return;
    }
    await saveProviders();
}

window.onload = () => {
    if(window.StudioTheme) window.StudioTheme.apply();
    if(window.StudioI18n) window.StudioI18n.apply();
    syncRecommendView();
    loadProviders();
    // 平台名输入时实时预览生成的 ID
    if(nameInput) nameInput.addEventListener('input', updateIdPreview);
    if(protocolInput) protocolInput.addEventListener('change', updateProtocolFromInput);
    [keyInput, rhFreeKeyInput, rhWalletKeyInput].forEach(input => {
        if(input) input.addEventListener('input', refreshProviderOnboarding);
    });
};

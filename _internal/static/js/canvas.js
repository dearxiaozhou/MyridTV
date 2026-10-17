function refreshIcons(){ if(window.lucide) lucide.createIcons(); }
refreshIcons();
function tr(key){ return window.StudioI18n ? StudioI18n.t(key) : key; }
function trf(key, values={}){
    return Object.entries(values).reduce((text, [name, value]) => text.replaceAll(`{${name}}`, String(value)), tr(key));
}
function langIsEn(){ return window.StudioI18n?.lang?.() === 'en'; }
function applyLanguage(lang){
    if(lang && window.StudioI18n) StudioI18n.set(lang);
    document.title = tr('canvas.title');
    refreshGateViewControls();
    if(canvas) {
        currentCanvasTitle.textContent = canvas?.title || tr('canvas.untitled');
    }
    renderCanvasList();
    render();
}
async function refreshCanvasConfigFromSettings(){
    await loadConfig();
    pruneMissingComfyWorkflows();
    (nodes || []).forEach(node => {
        sanitizeImageNodeProviderModel(node);
        sanitizeVideoNodeProviderModel(node);
    });
    if(typeof render === 'function') render();
}
window.addEventListener('message', event => {
    if(event.origin && event.origin !== location.origin) return;
    if(event.data?.type === 'studio-lang') applyLanguage(event.data.lang);
    if(event.data?.type === 'providers-changed' || event.data?.type === 'workflows-changed' || event.data?.type === 'comfy-instances-changed'){
        refreshCanvasConfigFromSettings();
    }
});
window.addEventListener('studio-lang-change', () => {
    document.title = tr('canvas.title');
    refreshGateViewControls();
    if(canvas) currentCanvasTitle.textContent = canvas?.title || tr('canvas.untitled');
    renderCanvasList();
    render();
});
const shell = document.getElementById('shell');
const canvasGate = document.getElementById('canvasGate');
const gateStatus = document.getElementById('gateStatus');
const gateCreateBtn = document.getElementById('gateCreateBtn');
const gateCreateSmartBtn = document.getElementById('gateCreateSmartBtn');
const gateRefreshBtn = document.getElementById('gateRefreshBtn');
const gateBackBtn = document.getElementById('gateBackBtn');
const gateTrashBtn = document.getElementById('gateTrashBtn');
const gatePurgeAllBtn = document.getElementById('gatePurgeAllBtn');
const gateAssetManagerBtn = document.getElementById('gateAssetManagerBtn');
const gateTrashCount = document.getElementById('gateTrashCount');
const gateTitleText = document.getElementById('gateTitleText');
const gateSubtitle = document.getElementById('gateSubtitle');
const gateCanvasList = document.getElementById('gateCanvasList');
const gateTitleInput = document.getElementById('gateTitleInput');
const gateConfirmBtn = document.getElementById('gateConfirmBtn');
const gateCancelBtn = document.getElementById('gateCancelBtn');
const backToManagerBtn = document.getElementById('backToManagerBtn');
const currentCanvasTitle = document.getElementById('currentCanvasTitle');
const currentCanvasTime = document.getElementById('currentCanvasTime');
const assetManagerModal = document.getElementById('assetManagerModal');
const assetManagerBody = document.getElementById('assetManagerBody');
function revealCanvasAssetControls(){
    [assetManagerModal].forEach(el => {
        if(!el) return;
        el.hidden = false;
        if(el.style?.display === 'none') el.style.display = '';
    });
}
revealCanvasAssetControls();
const logModal = document.getElementById('logModal');
const logList = document.getElementById('logList');
const errorModal = document.getElementById('errorModal');
const errorTitle = document.getElementById('errorTitle');
const errorMessage = document.getElementById('errorMessage');
let canvases = [];
let deletedCanvases = [];
let canvas = null;
let nodes = [];
let connections = [];
let viewport = {x: -1800, y: -1000, scale: 1};
let dragNode = null;
let dragBoard = null;
let minimapDrag = false;
let minimapState = null;
let minimapRenderQueued = false;
let resizeNode = null;
let llmPaneDrag = null;
let tempLink = null;
let knifeActive = false;
let knifePoint = null;
let knifeTrail = [];
let knifeChanged = false;
let knifeNeedsRender = false;
let selectDrag = null;
let isRKeyDown = false;
let menuPoint = null;
let linkCreateState = null;
let internalDrag = false;
let selected = new Set();
let saveTimer = null;
let creatingCanvas = false;
let createCanvasKind = 'smart';
let trashMode = false;
let pendingDeleteCanvasId = null;
let pendingPurgeCanvasId = null;
let emojiPickerCanvasId = null;
let canvasSortMode = (() => { try { return localStorage.getItem('canvasSortMode') || 'recent'; } catch(e){ return 'recent'; } })();
const CANVAS_COLOR_OPTIONS = ['red','orange','amber','green','teal','blue','violet','pink','slate'];
let localCanvasDirty = false;
let acknowledgedCanvas = null;
let savingCanvasNow = false;
let saveCanvasAgain = false;
let applyingRemoteCanvas = false;
let remoteSyncTimer = null;
let remoteSyncInterval = null;
let remoteSyncBusy = false;
let lastCanvasUpdatedAt = 0;
let models = {gpt:'gpt-image-2', nano:'nano-banana-pro'};
let imageModels = ['gpt-image-2', 'nano-banana-pro'];
let chatModels = ['gpt-4o-mini'];
let videoModels = [];
let apiProviders = [];
const PROVIDER_MODEL_DISPLAY = window.WcsProviderModelDisplay || null;
let comfyBackendCount = 1;
let comfyWorkflows = [];
let comfyWorkflowCache = {};
const COMFY_WORKFLOW_REGISTRY_KEY = 'studio_comfy_workflows_v1';
const REMOVED_COMFY_WORKFLOWS = new Set(['2511.json', 'Flux2-Klein.json']);
const COMFY_WORKFLOW_NAME_ALIASES = Object.freeze({
    'Z image 文生图强化版.json': 'Z-image-enhanced.json',
    'Qwen3.5提示词扩写+图片反推+视频反推.json': 'Qwen35-prompt-vision-video.json'
});
const DEFAULT_COMFY_WORKFLOWS = [
    {name:'SeedVR2图片放大流.json', title:'SeedVR2图片放大流', field_count:0, builtin:true},
    {name:'Z-image-enhanced.json', title:'Z image 文生图强化版', field_count:0, builtin:false},
];
let runningHubWorkflowCache = {};
const smartTextContentCache = new Map();
let managedProviderId = 'comfly';
let localImageModels = [];
let localChatModels = [];
let hasManagedImageModels = false;
let hasManagedChatModels = false;
let outputCompareDrag = false;
let outputPreviewZoom = 1;
let outputPreviewPan = {x: 0, y: 0};
let outputPreviewPanDrag = null;
let currentOutputCompareUrl = '';
let currentOutputMeta = null;
let currentOutputLightboxOutId = '';
let currentOutputLightboxUrl = '';
const missingAssetUrls = new Set();
let outputTimer = null;
let loopContext = null;
let clipboard = null;
let lastImagePasteAt = 0;
let promptTemplateNodeId = '';
let promptTemplateCategory = 'all';
let promptTemplateSelectedId = '';
let promptTemplateQuery = '';
let promptTemplateEditing = false;
let canvasPromptTemplates = [];
let canvasPromptTemplatesLoaded = false;
let canvasPromptLibraries = [];
let activePromptLibraryId = 'system';
const CANVAS_PROMPT_TEMPLATE_GROUPS_KEY = 'canvas_prompt_template_groups_v1';
const CANVAS_PROMPT_TEMPLATE_OVERRIDES_KEY = 'canvas_prompt_template_overrides';
let promptTemplateGroups = [];
let promptTemplateGroupEditMode = false;
let canvasPromptTemplateOverrides = {hiddenBuiltinIds:[], editedBuiltins:{}};
let canvasAssetLibrary = {categories:[]};
let canvasAssetLibraryOpen = false;
let activeCanvasAssetLibraryId = '';
let activeCanvasAssetCategoryId = '';
let assetManagerTab = 'assets';
let managerSelectedAssetIds = new Set();
let managerSelectedPromptIds = new Set();
const activeCanvasTaskPolls = new Set();
let hoveredConnectionId = '';
let lastMouseBoard = {x: 0, y: 0};
let undoStack = [];
const UNDO_MAX = 30;
const cascadeRunningIds = new Set();
const cascadeStopIds = new Set();
const cascadeSerialIds = new Set(); // 记录以串行循环模式启动的运行，用于停止按钮
const cascadeContexts = new Map();
let cropState = null;
let canvasCropState = null;
function normalizeComfyWorkflowEntries(list){
    const seen = new Set();
    const out = [];
    (Array.isArray(list) ? list : []).forEach(item => {
        const name = resolveComfyWorkflowName(item?.name);
        if(!name || REMOVED_COMFY_WORKFLOWS.has(name) || !/\.json$/i.test(name) || /\.config\.json$/i.test(name) || seen.has(name)) return;
        seen.add(name);
        out.push({
            name,
            title: String(item?.title || name.replace(/\.json$/i, '')).trim() || name.replace(/\.json$/i, ''),
            field_count: Math.max(0, Number(item?.field_count) || 0),
            builtin: item?.builtin === true
        });
    });
    return out;
}
function resolveComfyWorkflowName(name){
    const normalized = String(name || '').trim();
    return COMFY_WORKFLOW_NAME_ALIASES[normalized] || normalized;
}
function loadLocalComfyWorkflowRegistry(){
    try {
        return normalizeComfyWorkflowEntries(JSON.parse(localStorage.getItem(COMFY_WORKFLOW_REGISTRY_KEY) || '[]'));
    } catch(_) {
        return [];
    }
}
function saveLocalComfyWorkflowRegistry(list){
    try {
        localStorage.setItem(COMFY_WORKFLOW_REGISTRY_KEY, JSON.stringify(normalizeComfyWorkflowEntries(list)));
    } catch(_) {}
}
function mergeKnownComfyWorkflows(primary=[], fallback=[]){
    return normalizeComfyWorkflowEntries([
        ...(Array.isArray(primary) ? primary : []),
        ...(Array.isArray(fallback) ? fallback : []),
        ...DEFAULT_COMFY_WORKFLOWS
    ]);
}
function updateKnownComfyWorkflows(primary=[]){
    const merged = mergeKnownComfyWorkflows(primary, pruneRegistryAgainstBackend(loadLocalComfyWorkflowRegistry(), primary));
    saveLocalComfyWorkflowRegistry(merged);
    return merged;
}
// 后端列表非空时以它为准：本地缓存里后端已不存在（被删除/被改名）的自定义条目不再
// 合并回注册表，避免已删除的工作流在列表里阴魂不散（旧实现无脑 merge 还会写回缓存）。
function pruneRegistryAgainstBackend(local=[], primary=[]){
    const list = Array.isArray(primary) ? primary : [];
    const backendNames = new Set(list.map(w => String(w?.name || '')).filter(Boolean));
    if(!backendNames.size) return Array.isArray(local) ? local : [];
    return (Array.isArray(local) ? local : []).filter(
        w => w?.builtin === true || backendNames.has(String(w?.name || '')));
}
async function filterAccessibleComfyWorkflows(list=[]){
    const normalized = normalizeComfyWorkflowEntries(list);
    const accessible = [];
    for(const item of normalized){
        const data = await ensureComfyWorkflow(item.name);
        if(!data?.workflow) continue;
        const resolvedName = resolveComfyWorkflowName(data.name || item.name);
        accessible.push({
            ...item,
            name: resolvedName,
            title: String(data?.config?.title || item.title || resolvedName.replace(/\.json$/i, '')).trim() || resolvedName.replace(/\.json$/i, ''),
            field_count: Array.isArray(data?.config?.fields) ? data.config.fields.length : item.field_count,
            builtin: item.builtin === true || data?.builtin === true
        });
    }
    return normalizeComfyWorkflowEntries(accessible);
}
let cropDrag = null;
let imageEditMode = 'crop';
let imageEditModeTouched = false;
let editDrawState = null;
let editTextItems = [];
let editTextSelectedId = '';
let editTextDrag = null;
let editTextDirty = false;
let editTextInlineEditor = null;
let editDrawUndoStack = [];
let editDrawRedoStack = [];
const EDIT_DRAW_HISTORY_MAX = 40;
let brushTool = 'free';
let brushLabelCounter = 1;
let gridCustomMode = false;
let gridCustomLines = []; // [{type:'h'|'v', pos:0-1}] 相对图片尺寸的分数位置
let gridCustomOrientation = 'h'; // 当前点击放置方向
let gridCustomHistory = []; // 撤销栈：每次放线前快照
let gridCustomDrag = null; // {index, pointerId}
let imageEditZoom = 1.0;
let imageEditBaseW = 0; // zoom=1 时图片显示宽度
let imageEditBaseH = 0;
let textSelectionGuard = null;
const PROMPT_TEXT_MAX_LENGTH = 20000;
const CLIENT_ID = 'canvas_' + Math.random().toString(36).slice(2);
const LTX_DIRECTOR_WORKFLOW = 'LTXDirectorv2-API.json';
const LTX_DIRECTOR_WF_NODE = '46';
const LTX_DIRECTOR_SEED_NODE = '94:28';
const LTX_SEGMENT_COLORS = ['#e07b3a', '#3b82f6', '#10b981', '#8b5cf6', '#ec4899', '#f59e0b'];
const CANVAS_EMOJIS = ['layers','sparkles','image','palette','wand-2','star','heart','rocket','flame','moon','cloud','leaf','gem','compass','pin','flag','bookmark','crown'];
function renderCanvasIcon(icon, size = 14) {
    // 旧的默认 emoji 或空值都映射为 layers
    if(!icon || icon === '🧩') return `<i data-lucide="layers" style="width:${size}px;height:${size}px"></i>`;
    // 含非 ASCII 字符（用户旧选过的 emoji）继续按文本渲染
    if(/[^\x00-\x7F]/.test(icon)) return escapeHtml(icon);
    return `<i data-lucide="${escapeHtml(icon)}" style="width:${size}px;height:${size}px"></i>`;
}

const SIZE_MAP = {
    square: { '1k':'1024x1024', '2k':'2048x2048', '4k':'4096x4096' },
    portrait: { '1k':'1024x1536', '2k':'1360x2048', '4k':'2352x3520' },
    portrait43: { '1k':'1008x1344', '2k':'1536x2048', '4k':'2448x3264' },
    landscape43: { '1k':'1344x1008', '2k':'2048x1536', '4k':'3264x2448' },
    landscape: { '1k':'1536x1024', '2k':'2048x1360', '4k':'3520x2352' },
    story: { '1k':'720x1280', '2k':'1152x2048', '4k':'2160x3840' },
    wide: { '1k':'1280x720', '2k':'2048x1152', '4k':'3840x2160' },
    ultrawide: { '1k':'1280x544', '2k':'2048x880', '4k':'3840x1648' },
    ultratall: { '1k':'544x1280', '2k':'880x2048', '4k':'1648x3840' }
};
const RES_LONG_SIDE = { '1k':1536, '2k':2048, '4k':3840 };
const RES_PIXEL_LIMIT = { '1k':1572864, '2k':4194304, '4k':8294400 };
const CUSTOM_IMAGE_MODELS_KEY = 'canvas_custom_image_models';
const MANAGED_IMAGE_MODELS_KEY = 'canvas_image_models_ordered';
const MANAGED_CHAT_MODELS_KEY = 'canvas_chat_models_ordered';
const CANVAS_THEME_KEY = 'canvas_theme';
const QUICK_TOOLBAR_COLLAPSED_KEY = 'canvas_quick_toolbar_collapsed';
const CANVAS_SESSION_VIEWPORTS_KEY = 'canvas_session_viewports_v1';
let canvasSessionViewportFallback = {};
const DEFAULT_VIDEO_MODELS = [
    // Veo
    'veo2', 'veo2-fast', 'veo2-pro',
    'veo3', 'veo3-fast', 'veo3-pro',
    'veo3.1', 'veo3.1-fast', 'veo3.1-quality', 'veo3.1-lite',
    // Sora
    'sora-2', 'sora-2-pro',
    // 通义万相
    'wan2.6-t2v', 'wan2.6-i2v',
    'wan2.5-t2v-preview', 'wan2.5-i2v-preview',
    'wan2.2-t2v-plus', 'wan2.2-i2v-plus', 'wan2.2-i2v-flash',
    // Seedance
    'doubao-seedance-2-0-260128',
    'doubao-seedance-2-0-fast-260128',
    'doubao-seedance-1-5-pro-251215',
    'doubao-seedance-1-0-pro-250528',
    'doubao-seedance-1-0-lite-t2v-250428',
    'doubao-seedance-1-0-lite-i2v-250428'
];

function loadLocalViewportMap(){
    try {
        const data = JSON.parse(sessionStorage.getItem(CANVAS_SESSION_VIEWPORTS_KEY) || '{}');
        return data && typeof data === 'object' ? data : {};
    } catch(e) {
        return canvasSessionViewportFallback;
    }
}
function localViewportForCanvas(canvasId, fallback={x:0, y:0, scale:1}){
    const item = loadLocalViewportMap()[canvasId || ''];
    if(!item || typeof item !== 'object') return {...fallback};
    return {
        x:Number.isFinite(Number(item.x)) ? Number(item.x) : Number(fallback.x || 0),
        y:Number.isFinite(Number(item.y)) ? Number(item.y) : Number(fallback.y || 0),
        scale:Number.isFinite(Number(item.scale)) ? Math.max(.12, Math.min(8, Number(item.scale))) : Number(fallback.scale || 1)
    };
}
function applyTheme(theme){
    const dark = window.StudioTheme?.isDark?.(theme) ?? (theme === 'dark');
    document.documentElement.classList.toggle('studio-theme-dark', dark);
    document.documentElement.classList.toggle('theme-dark', dark);
    document.body.classList.toggle('studio-theme-dark', dark);
    document.body.classList.toggle('theme-dark', dark);
    shell.classList.toggle('theme-dark', dark);
}
function loadLocalModelLists(){
    try {
        const managedRaw = localStorage.getItem(MANAGED_IMAGE_MODELS_KEY);
        const raw = JSON.parse(managedRaw || localStorage.getItem(CUSTOM_IMAGE_MODELS_KEY) || '[]');
        localImageModels = Array.isArray(raw) ? raw.filter(Boolean) : [];
        hasManagedImageModels = Boolean(managedRaw);
    } catch(e) {
        localImageModels = [];
        hasManagedImageModels = false;
    }
    try {
        const managedRaw = localStorage.getItem(MANAGED_CHAT_MODELS_KEY);
        const raw = JSON.parse(managedRaw || '[]');
        localChatModels = Array.isArray(raw) ? raw.filter(Boolean) : [];
        hasManagedChatModels = Boolean(managedRaw);
    } catch(e) {
        localChatModels = [];
        hasManagedChatModels = false;
    }
}
function uniqueModels(list){
    const seen = new Set();
    return list.map(item => String(item || '').trim()).filter(item => {
        if(!item || seen.has(item)) return false;
        seen.add(item);
        return true;
    });
}
function defaultApiProviders(){
    return [{id:'comfly', name:'Comfly', base_url:'', enabled:true, image_models:imageModels, chat_models:chatModels, video_models:videoModels.length ? videoModels : DEFAULT_VIDEO_MODELS, has_key:false, key_preview:''}];
}
function isRunningHubProvider(provider){
    const id = String(provider?.id || '').trim().toLowerCase();
    const protocol = String(provider?.protocol || '').trim().toLowerCase();
    const name = String(provider?.name || '').trim().toLowerCase();
    return id === 'runninghub' || protocol === 'runninghub' || name === 'runninghub' || id === 'rh';
}
function imageApiProviders(){
    const providers = (apiProviders.length ? apiProviders : defaultApiProviders())
        .filter(p => p.enabled !== false && (p.image_models || []).length);
    return providers;
}
function resolveImageProviderId(id){
    const providers = imageApiProviders();
    return providers.find(p => p.id === id)?.id || providers[0]?.id || '';
}
function providerImageModels(providerId){
  // 不走 providerById（会 fallback 到第一个 provider，造成串台），直接查精确匹配
  const provider = apiProviders.find(p => p.id === providerId);
  return uniqueModels(provider?.image_models || []);
}
function sanitizeImageNodeProviderModel(node){
  if(!node || node.type !== 'generator') return;
  node.apiProvider = resolveImageProviderId(node.apiProvider || '');
    const models = providerImageModels(node.apiProvider);
    if(!models.length) node.model = '';
    else if(!models.includes(resolveImageModel(node.model))) node.model = models[0] || '';
}
function videoApiProviders(){
    const providers = (apiProviders.length ? apiProviders : defaultApiProviders())
        .filter(p => !isRunningHubProvider(p) && p.enabled !== false && (p.video_models || []).length);
    return providers.length ? providers : defaultApiProviders();
}
function resolveVideoProviderId(id){
    const providers = videoApiProviders();
    return providers.find(p => p.id === id)?.id || providers[0]?.id || 'comfly';
}
function providerVideoModels(providerId){
    // 不走 providerById（会 fallback 到第一个 provider，造成串台），直接查精确匹配
    const provider = apiProviders.find(p => p.id === providerId);
    return uniqueModels(provider?.video_models || []);
}
function sanitizeVideoNodeProviderModel(node){
    if(!node || node.type !== 'video') return;
    node.apiProvider = resolveVideoProviderId(node.apiProvider || 'comfly');
    const models = providerVideoModels(node.apiProvider);
    if(!models.length) node.model = '';
    else if(!models.includes(node.model)) node.model = models[0] || '';
}
function allImageModels(providerId){
    const providerModels = providerImageModels(providerId || managedProviderId);
    return uniqueModels(providerModels);
}
function resolveImageModel(value){
    if(value === 'gpt') return models.gpt;
    if(value === 'nano') return models.nano;
    return normalizeRhModelId(value || allImageModels(managedProviderId)[0] || models.gpt);
}
function normalizeRhModelId(value){
    return String(value || '').trim().replace(/rhart-image-g-2-offcial/g, 'rhart-image-g-2-official');
}
const APP_RUNTIME_CONFIG_DEFAULTS = {
    proxy:{base_url:(typeof location!=='undefined'&&location.origin?location.origin:'http://127.0.0.1:3107')},
    agent:{provider_id:'', model:'', preferred_model_pattern:''}
};
let appRuntimeConfig = APP_RUNTIME_CONFIG_DEFAULTS;
let appRuntimeConfigLoaded = false;
let RH_OFFICIAL_PROXY_BASE = APP_RUNTIME_CONFIG_DEFAULTS.proxy.base_url;
function mergeAppRuntimeConfig(base, override){
    const merged = {...(base || {})};
    Object.entries(override || {}).forEach(([key, value]) => {
        merged[key] = value && typeof value === 'object' && !Array.isArray(value)
            ? mergeAppRuntimeConfig(merged[key] || {}, value)
            : value;
    });
    return merged;
}
async function loadAppRuntimeConfig(){
    if(appRuntimeConfigLoaded) return appRuntimeConfig;
    appRuntimeConfigLoaded = true;
    try {
        const response = await fetch(`/static/app_config.json?v=${Date.now()}`, {cache:'no-store'});
        if(response.ok) appRuntimeConfig = mergeAppRuntimeConfig(APP_RUNTIME_CONFIG_DEFAULTS, await response.json());
    } catch(_) {
        appRuntimeConfig = APP_RUNTIME_CONFIG_DEFAULTS;
    }
    RH_OFFICIAL_PROXY_BASE = String(appRuntimeConfig?.proxy?.base_url || APP_RUNTIME_CONFIG_DEFAULTS.proxy.base_url).replace(/\/$/, '');
    return appRuntimeConfig;
}
function closeErrorModal(){
    if(errorModal) errorModal.classList.remove('open');
}
async function copyErrorMessage(){
    const text = errorMessage?.textContent || '';
    if(!text) return;
    try {
        await navigator.clipboard.writeText(text);
    } catch(e) {
        const range = document.createRange();
        range.selectNodeContents(errorMessage);
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
    }
}
async function copyTextToClipboard(text){
    const value = String(text || '');
    if(!value) return false;
    try {
        if(navigator.clipboard?.writeText){
            await navigator.clipboard.writeText(value);
            return true;
        }
    } catch(_) {}
    try {
        const ta = document.createElement('textarea');
        ta.value = value;
        ta.setAttribute('readonly', '');
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        ta.style.top = '0';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        const ok = document.execCommand('copy');
        ta.remove();
        return ok;
    } catch(_) {
        return false;
    }
}
function formatCanvasTime(value){
    if(!value) return '--';
    const raw = Number(value);
    const time = raw < 10000000000 ? raw * 1000 : raw;
    const date = new Date(time);
    if(Number.isNaN(date.getTime())) return '--';
    return date.toLocaleString(window.StudioI18n?.lang() === 'en' ? 'en-US' : 'zh-CN', { month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit' });
}
function canvasIdPreview(id){
    const raw = String(id || '').trim();
    if(!raw) return '';
    return raw.length <= 8 ? raw : raw.slice(0, 8);
}
function canvasIdStatusText(){
    return langIsEn() ? 'Canvas ID copied' : '已复制 Canvas ID';
}
function setStatus(text){
    document.getElementById('saveState').textContent = text;
    if(gateStatus) gateStatus.textContent = text;
}
function refreshGateViewControls(){
    canvasGate.classList.toggle('trash-mode', trashMode);
    if(gateTitleText) gateTitleText.textContent = trashMode ? tr('canvas.trash') : tr('canvas.selectCanvas');
    if(gateSubtitle) gateSubtitle.textContent = trashMode ? tr('canvas.trashSubtitle') : tr('canvas.subtitle');
    const trashCount = deletedCanvases.length;
    if(gateTrashCount){
        gateTrashCount.textContent = String(trashCount);
        gateTrashCount.classList.toggle('visible', trashCount > 0);
    }
    const canPurgeAll = trashMode && trashCount > 0;
    if(gatePurgeAllBtn){
        gatePurgeAllBtn.classList.toggle('hidden', !canPurgeAll);
        if(canPurgeAll) gatePurgeAllBtn.removeAttribute('hidden'); else gatePurgeAllBtn.setAttribute('hidden','');
        if(gatePurgeAllBtn.dataset) gatePurgeAllBtn.dataset.count = String(trashCount);
    }
    const countPill = document.getElementById('gateCountPill');
    if(countPill){
        const items = trashMode ? deletedCanvases : canvases;
        const suffix = tr('canvas.countSuffix');
        countPill.textContent = suffix ? `${items.length} ${suffix}` : String(items.length);
    }
    const sortSwitch = document.getElementById('gateSortSwitch');
    if(sortSwitch){
        sortSwitch.classList.toggle('hidden', trashMode);
        sortSwitch.querySelectorAll('[data-sort]').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.sort === canvasSortMode);
        });
    }
}
function normalizeGateActions(){
 const actions = document.querySelector('.gate-head-actions');
 if(!actions || !gateCreateSmartBtn || !gateRefreshBtn || !gateTrashBtn) return;
 actions.insertBefore(gateCreateSmartBtn, actions.firstChild);
 actions.insertBefore(gateRefreshBtn, gateCreateSmartBtn.nextSibling);
 actions.insertBefore(gateTrashBtn, gateRefreshBtn.nextSibling);
}
function setCanvasMode(open){
    shell.classList.toggle('no-canvas', !open);
    if(!open){
        canvas = null;
    } else if(currentCanvasTitle) {
        currentCanvasTitle.textContent = canvas?.title || tr('canvas.untitled');
        currentCanvasTime.textContent = formatCanvasTime(canvas?.updated_at || canvas?.created_at);
    }
    refreshIcons();
}
function setCreateMode(active, kind='smart'){
    creatingCanvas = active;
    createCanvasKind = 'smart';
    if(active) trashMode = false;
    canvasGate.classList.toggle('creating', active);
    refreshGateViewControls();
    setStatus(active ? tr('canvas.enterCanvasName') : (canvases.length ? tr('canvas.chooseFirst') : tr('canvas.noCanvasCreateFirst')));
    if(active) {
        gateTitleInput.placeholder = tr('canvas.newSmartCanvasPlaceholder') || tr('canvas.newCanvasPlaceholder');
        gateTitleInput.focus();
        gateTitleInput.select();
    } else {
        gateTitleInput.value = '';
        gateTitleInput.placeholder = tr('canvas.newSmartCanvasPlaceholder') || tr('canvas.newCanvasPlaceholder');
    }
    refreshIcons();
}

// ===== 任务控制台定位（tc-locate，旧画布）=====

function scheduleSave(){
    if(!canvas || applyingRemoteCanvas) return;
    localCanvasDirty = true;
    setStatus('Saving...');
    clearTimeout(saveTimer);
    if(savingCanvasNow){
        saveCanvasAgain = true;
        return;
    }
    saveTimer = setTimeout(saveCanvas, 500);
}
function serializableCanvasNode(node){
    const copy = {...(node || {})};
    delete copy._ltxEditor;
    delete copy.running;
    delete copy.runStatus;
    delete copy.runError;
    delete copy._cascadeIdx;
    delete copy._cascadeFailed;
    delete copy._activeLoopCtx;
    return copy;
}
function serializableCanvasNodes(list=nodes){
    return (list || []).map(serializableCanvasNode);
}
async function saveCanvas(){
    if(!canvas || applyingRemoteCanvas) return;
    if(savingCanvasNow){
        saveCanvasAgain = true;
        return;
    }
    sanitizeConnections();
    savingCanvasNow = true;
    saveCanvasAgain = false;
    try {
        const res = await fetch(`/api/canvases/${canvas.id}`, {
            method:'PUT',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({
                title:canvas.title,
                icon:canvas.icon || '🧩',
                nodes:serializableCanvasNodes(),
                connections,
                viewport,
                logs:canvas.logs || [],
                client_id:CLIENT_ID,
                base_updated_at:Number(lastCanvasUpdatedAt || canvas.updated_at || 0)
            })
        });
        if(res.status === 409){
            const data = await res.json().catch(() => ({}));
            const remote = data.detail?.canvas || data.canvas;
            if(localCanvasDirty || saveCanvasAgain){
                if(!remote) throw new Error('Missing conflicting canvas');
                const base = acknowledgedCanvas?.id === canvas.id ? acknowledgedCanvas : canvas;
                nodes = CanvasMergeSync.mergeSmartNodeLists(nodes, remote.nodes || [],
                    new Set((remote.deleted || []).map(t => t.id)), base.nodes || []);
                const key = c => `${c.from}->${c.to}:${c.kind || 'flow'}`;
                const baseKeys = new Set((base.connections || []).map(key));
                const localKeys = new Set(connections.map(key));
                const remoteKeys = new Set((remote.connections || []).map(key));
                const keep = c => !baseKeys.has(key(c)) || (localKeys.has(key(c)) && remoteKeys.has(key(c)));
                connections = CanvasMergeSync.mergeSmartConnections(connections.filter(keep), (remote.connections || []).filter(keep), new Set(nodes.map(n => n.id)));
                canvas = {...canvas, ...remote, nodes, connections};
                acknowledgedCanvas = JSON.parse(JSON.stringify(remote));
                lastCanvasUpdatedAt = Number(remote.updated_at || 0);
                render();
                saveCanvasAgain = true;
                setStatus('Saving...');
                return;
            }
            if(remote) applyRemoteCanvasData(remote);
            setStatus('Synced');
            return;
        }
        if(!res.ok) throw new Error('save failed');
        const data = await res.json().catch(() => ({}));
        const localViewport = {...viewport};
        if(data.canvas) canvas = {...canvas, ...data.canvas, viewport:localViewport};
        if(data.canvas) acknowledgedCanvas = JSON.parse(JSON.stringify(data.canvas));
        viewport = localViewport;
        canvas.updated_at = Number(canvas.updated_at || Date.now());
        lastCanvasUpdatedAt = canvas.updated_at;
        localCanvasDirty = Boolean(saveCanvasAgain);
        if(currentCanvasTime) currentCanvasTime.textContent = formatCanvasTime(canvas.updated_at);
        setStatus('Saved');
        loadCanvasList(false);
    } catch(e) {
        setStatus('Save failed');
        console.error(e);
    } finally {
        savingCanvasNow = false;
        if(saveCanvasAgain && canvas && !applyingRemoteCanvas){
            saveCanvasAgain = false;
            localCanvasDirty = true;
            setTimeout(saveCanvas, 0);
        }
    }
}

async function fetchCanvasLocalJson(url, options={}, timeout=1800){
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
        const res = await fetch(url, {...options, signal:controller.signal});
        if(!res.ok) throw new Error('local-api-unavailable');
        return await res.json();
    } finally {
        clearTimeout(timer);
    }
}
async function loadConfig(){
    await loadAppRuntimeConfig();
    loadLocalModelLists();
    try {
        const cfg = await fetchCanvasLocalJson('/api/config');
        imageModels = cfg.image_models?.length ? cfg.image_models : imageModels;
        chatModels = cfg.chat_models?.length ? cfg.chat_models : chatModels;
        videoModels = cfg.video_models?.length ? cfg.video_models : DEFAULT_VIDEO_MODELS;
        comfyBackendCount = Math.max(1, (cfg.comfy_instances || []).length || 1);
        apiProviders = Array.isArray(cfg.api_providers) && cfg.api_providers.length ? cfg.api_providers : defaultApiProviders();
        models.nano = imageModels.find(m => m.toLowerCase().includes('nano')) || 'nano-banana-pro';
        models.gpt = imageModels.find(m => !m.toLowerCase().includes('nano')) || cfg.image_model || 'gpt-image-2';
        try {
            const wf = await fetchCanvasLocalJson('/api/workflows');
            comfyWorkflows = updateKnownComfyWorkflows(wf.workflows || []);
        } catch(_) {
            comfyWorkflows = await filterAccessibleComfyWorkflows(mergeKnownComfyWorkflows(loadLocalComfyWorkflowRegistry()));
            saveLocalComfyWorkflowRegistry(comfyWorkflows);
        }
        runningHubWorkflowCache = {};
    } catch(e) {
        apiProviders = defaultApiProviders();
    }
}

// 监听 API 设置页面的变更广播，实时刷新画布的模型/平台下拉
try {
    const apiChannel = new BroadcastChannel('studio-api');
    apiChannel.onmessage = async (e) => {
        if(e.data?.type === 'providers-changed' || e.data?.type === 'workflows-changed' || e.data?.type === 'comfy-instances-changed'){
            await refreshCanvasConfigFromSettings();
        }
    };
} catch(e) { /* 不支持 BroadcastChannel 的旧浏览器忽略 */ }
async function loadCanvasList(openFirst=true){
    try {
        const res = await fetch('/api/canvases');
        if(!res.ok) throw new Error(tr('canvas.canvasListFailed'));
        const data = await res.json();
        canvases = data.canvases || [];
        sortCanvasListByUpdated();
        refreshGateViewControls();
        renderCanvasList();
        refreshTrashCount();
        if(openFirst && canvases[0]) await openCanvas(canvases[0].id);
        else if(!canvas) {
            setCanvasMode(false);
            setStatus(trashMode ? (deletedCanvases.length ? tr('canvas.trash') : tr('canvas.trashEmpty')) : (canvases.length ? tr('canvas.chooseFirst') : tr('canvas.noCanvasCreateFirst')));
        }
    } catch(e) {
        setStatus(tr('canvas.canvasListFailed'));
        console.error(e);
    }
}
async function loadTrashList(){
    try {
        const res = await fetch('/api/canvases/trash');
        if(!res.ok) throw new Error(tr('canvas.trashLoadFailed'));
        const data = await res.json();
        deletedCanvases = data.canvases || [];
        refreshGateViewControls();
        renderCanvasList();
        setStatus(deletedCanvases.length ? tr('canvas.trash') : tr('canvas.trashEmpty'));
    } catch(e) {
        setStatus(tr('canvas.trashLoadFailed'));
        console.error(e);
    }
}
async function refreshTrashCount(){
    if(trashMode) return;
    try {
        const res = await fetch('/api/canvases/trash');
        if(!res.ok) return;
        const data = await res.json();
        deletedCanvases = data.canvases || [];
        refreshGateViewControls();
    } catch(e) {}
}
async function setTrashMode(active){
    trashMode = active;
    creatingCanvas = false;
    pendingDeleteCanvasId = null;
    pendingPurgeCanvasId = null;
    emojiPickerCanvasId = null;
    canvasGate.classList.toggle('creating', false);
    refreshGateViewControls();
    if(trashMode) await loadTrashList();
    else await loadCanvasList(false);
    refreshIcons();
}
function renderCanvasList(){
    renderCanvasListInto(gateCanvasList);
}
function compareCanvasRecords(a, b){
    // 置顶始终排在最前；其余按当前排序模式（最近编辑 / 名称）。
    const ap = a.pinned ? 1 : 0, bp = b.pinned ? 1 : 0;
    if(ap !== bp) return bp - ap;
    if(canvasSortMode === 'name'){
        const cmp = String(a.title || '').localeCompare(String(b.title || ''), 'zh-Hans-CN', {numeric:true, sensitivity:'base'});
        if(cmp !== 0) return cmp;
    }
    return Number(b.updated_at || b.created_at || 0) - Number(a.updated_at || a.created_at || 0);
}
function sortCanvasListByUpdated(){
    canvases.sort(compareCanvasRecords);
}
function setCanvasSortMode(mode){
    const next = mode === 'name' ? 'name' : 'recent';
    if(next === canvasSortMode) { refreshGateViewControls(); return; }
    canvasSortMode = next;
    try { localStorage.setItem('canvasSortMode', canvasSortMode); } catch(e){}
    sortCanvasListByUpdated();
    renderCanvasList();
    refreshGateViewControls();
}
function commitCanvasCover(id, cover){
    patchCanvasMeta(id, { cover: String(cover || '').trim() });
}
function pickCanvasCoverUpload(id){
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = async () => {
        const file = input.files && input.files[0];
        if(!file) return;
        const form = new FormData();
        form.append('files', file);
        try {
            // 画布封面属于该画布：落进画布输出目录，随改名搬移、随彻底删除清理
            const res = await fetch(`/api/ai/upload?scope=canvas&canvas_id=${encodeURIComponent(id)}`, { method:'POST', body:form });
            if(!res.ok) throw new Error('upload failed');
            const data = await res.json();
            const url = data.files && data.files[0] && data.files[0].url;
            if(!url) throw new Error('no url');
            commitCanvasCover(id, url);
        } catch(err) { console.error('[CoverUpload]', err); alert('背景图上传失败，请重试'); }
    };
    input.click();
}
async function patchCanvasMeta(id, patch){
    const item = canvases.find(c => c.id === id);
    if(item) Object.assign(item, patch);
    if(canvas?.id === id) Object.assign(canvas, patch);
    sortCanvasListByUpdated();
    renderCanvasList();
    try {
        const res = await fetch(`/api/canvases/${encodeURIComponent(id)}/meta`, {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify(patch)
        });
        if(!res.ok) throw new Error('meta save failed');
        const data = await res.json();
        if(data.canvas) updateCanvasListRecord(data.canvas);
    } catch(e){
        setStatus(tr('canvas.metaSaveFailed') || '保存失败');
        console.error(e);
        await loadCanvasList(false);
    }
}
function togglePinCanvas(id, event){
    event?.preventDefault();
    event?.stopPropagation();
    const item = canvases.find(c => c.id === id);
    emojiPickerCanvasId = null;
    patchCanvasMeta(id, {pinned: !(item && item.pinned)});
}
function setCanvasColorValue(id, color, event){
    event?.preventDefault();
    event?.stopPropagation();
    patchCanvasMeta(id, {color: color || ''});
}
function commitCanvasOwner(id, value){
    const owner = String(value || '').trim().slice(0, 40);
    const item = canvases.find(c => c.id === id);
    if((item?.owner || '') === owner) return;
    patchCanvasMeta(id, {owner});
}
function updateCanvasListRecord(record){
    if(!record?.id) return;
    const index = canvases.findIndex(item => item.id === record.id);
    if(index >= 0) canvases[index] = {...canvases[index], ...record};
    else canvases.unshift(record);
    sortCanvasListByUpdated();
    renderCanvasList();
}
async function touchCanvasOpened(id){
    if(!id) return null;
    try {
        const res = await fetch(`/api/canvases/${encodeURIComponent(id)}/touch`, {method:'POST'});
        if(!res.ok) return null;
        const data = await res.json();
        if(data.canvas) updateCanvasListRecord(data.canvas);
        return data.canvas || data;
    } catch(e) {
        console.warn('touch canvas failed', e);
        return null;
    }
}
function renderCanvasListInto(list){
    if(!list) return;
    document.querySelectorAll('body > .canvas-meta-pop').forEach(el => el.remove());
    refreshGateViewControls();
    const items = trashMode ? deletedCanvases : canvases;
    list.innerHTML = '';
    if(!items.length){
        const empty = document.createElement('div');
        empty.className = 'gate-list-empty';
        empty.innerHTML = trashMode
            ? `<div class="gate-list-empty-icon"><i data-lucide="trash-2" class="w-6 h-6"></i></div>${tr('canvas.trashEmpty')}`
            : `<div class="gate-list-empty-icon"><i data-lucide="layout-grid" class="w-6 h-6"></i></div>${tr('canvas.noCanvas')}<br>${tr('canvas.startWithNewCanvas')}`;
        list.appendChild(empty);
        refreshIcons();
        return;
    }
    items.forEach(item => {
        const row = document.createElement('div');
        const isSmartCanvas = (item.kind || 'smart') === 'smart';
        const color = String(item.color || '').trim();
        const owner = String(item.owner || '').trim();
        const shortId = canvasIdPreview(item.id);
        const pinned = !!item.pinned && !trashMode;
        row.className = `canvas-item ${isSmartCanvas ? 'smart-canvas' : ''} ${canvas?.id === item.id ? 'active' : ''} ${pinned ? 'pinned' : ''} ${color ? 'has-color' : ''}`;
        const ownerChip = owner
            ? `<span class="canvas-owner-chip" role="button" tabindex="0" title="${escapeAttr(owner)}"><i data-lucide="user-round" class="w-3 h-3"></i><span class="canvas-owner-text">${escapeHtml(owner)}</span></span>`
            : '';
        const cover = String(item.cover || '').trim();
        row.innerHTML = `
            ${color ? `<span class="canvas-color-bar cc-${escapeAttr(color)}"></span>` : ''}
            ${cover && !trashMode ? `<div class="canvas-card-bg" style="background-image:url('${escapeAttr(cover)}')"></div><div class="canvas-card-bg-shade"></div>` : ''}
            <div class="canvas-open${cover && !trashMode ? ' has-cover' : ''}" role="button" tabindex="${trashMode ? '-1' : '0'}">
                <div class="canvas-card-icon-row">
                    <span class="canvas-preview-mark" role="button" tabindex="0" title="${trashMode ? tr('canvas.deletedCanvas') : (tr('canvas.editMeta') || '编辑图标 / 颜色 / 负责人')}">${renderCanvasIcon(isSmartCanvas && /[^\x00-\x7F]/.test(item.icon || '') ? 'sparkles' : item.icon, 16)}</span>
                </div>
                <div class="canvas-card-title">${escapeHtml(item.title)}</div>
                ${ownerChip}
                ${shortId ? `
                <div class="canvas-card-id-row">
                    <span class="canvas-card-id" title="${escapeAttr(item.id)}">ID ${escapeHtml(shortId)}</span>
                    <button class="canvas-card-copy-id" type="button" title="复制完整 ID" aria-label="复制完整 ID">
                        <i data-lucide="copy" class="w-3 h-3"></i>
                    </button>
                </div>` : ''}
                <div class="canvas-card-meta">
                    <span class="canvas-card-meta-dot"></span>
                    <div class="canvas-card-time">${trashMode ? `${tr('canvas.deletedAt')} ${formatCanvasTime(item.deleted_at)}` : formatCanvasTime(item.updated_at || item.created_at)}</div>
                    ${!trashMode && Number(item.asset_node_count || 0) > 0 ? `<span class="canvas-card-asset-count" title="${tr('canvas.assetNodeCount') || '素材节点数（空节点不计）'}">${Number(item.asset_node_count)} 素材</span>` : ''}
                </div>
            </div>
            ${trashMode ? (pendingPurgeCanvasId === item.id ? `
                <div class="canvas-delete-confirm">
                    <div class="canvas-delete-box">
                        <div class="canvas-delete-title">${tr('canvas.purgeConfirm')}</div>
                        <div class="canvas-delete-sub">${tr('canvas.purgeLocalFilesNote')}</div>
                        <div class="canvas-delete-actions">
                            <button class="canvas-confirm-btn" type="button">${tr('common.confirm')}</button>
                            <button class="canvas-cancel-btn" type="button">${tr('common.cancel')}</button>
                        </div>
                    </div>
                </div>
            ` : `
                <button class="canvas-delete canvas-restore" type="button" title="${tr('canvas.restoreCanvas')}" aria-label="${tr('canvas.restoreCanvas')} ${escapeHtml(item.title)}" style="right:42px">
                    <i data-lucide="rotate-ccw" class="w-3.5 h-3.5"></i>
                </button>
                <button class="canvas-delete canvas-purge" type="button" title="${tr('canvas.purgeCanvas')}" aria-label="${tr('canvas.purgeCanvas')} ${escapeHtml(item.title)}">
                    <i data-lucide="x" class="w-3.5 h-3.5"></i>
                </button>
            `) : (pendingDeleteCanvasId === item.id ? `
                <div class="canvas-delete-confirm">
                    <div class="canvas-delete-box">
                        <div class="canvas-delete-title">${tr('canvas.moveToTrashConfirm')}</div>
                        <div class="canvas-delete-actions">
                            <button class="canvas-confirm-btn" type="button">${tr('common.confirm')}</button>
                            <button class="canvas-cancel-btn" type="button">${tr('common.cancel')}</button>
                        </div>
                    </div>
                </div>
            ` : `
                <button class="canvas-pin-btn ${pinned ? 'active' : ''}" type="button" title="${pinned ? (tr('canvas.unpin') || '取消置顶') : (tr('canvas.pin') || '置顶')}" aria-label="${pinned ? (tr('canvas.unpin') || '取消置顶') : (tr('canvas.pin') || '置顶')}">
                    <i data-lucide="pin" class="w-3.5 h-3.5"></i>
                </button>
                <button class="canvas-card-edit" type="button" title="${tr('canvas.rename')}" aria-label="${tr('canvas.rename')} ${escapeHtml(item.title)}">
                    <i data-lucide="pencil" class="w-3.5 h-3.5"></i>
                </button>
                <button class="canvas-card-export" type="button" title="导出画布（.json）" aria-label="导出画布">
                    <i data-lucide="download" class="w-3.5 h-3.5"></i>
                </button>
                <button class="canvas-delete" type="button" title="${tr('canvas.moveToTrash')}" aria-label="${tr('canvas.moveToTrash')} ${escapeHtml(item.title)}">
                    <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
                </button>
            `)}
            ${!trashMode && emojiPickerCanvasId === item.id ? `
                <div class="canvas-meta-pop">
                    <div class="canvas-meta-section">
                        <div class="canvas-meta-label">${tr('canvas.ownerLabel') || '负责人 / 项目'}</div>
                        <input class="canvas-owner-input" type="text" maxlength="40" value="${escapeAttr(owner)}" placeholder="${escapeAttr(tr('canvas.ownerPlaceholder') || '如：张三 / 双十一项目')}">
                    </div>
                    <div class="canvas-meta-section">
                        <div class="canvas-meta-label">${tr('canvas.colorLabel') || '颜色标记'}</div>
                        <div class="canvas-color-row">
                            <button class="canvas-color-swatch cc-none ${!color ? 'active' : ''}" type="button" data-color="" title="${tr('canvas.colorNone') || '无'}"><i data-lucide="ban" class="w-3 h-3"></i></button>
                            ${CANVAS_COLOR_OPTIONS.map(c => `<button class="canvas-color-swatch cc-${c} ${color === c ? 'active' : ''}" type="button" data-color="${c}" aria-label="${c}"></button>`).join('')}
                        </div>
                    </div>
                    <div class="canvas-meta-section">
                        <div class="canvas-meta-label">${tr('canvas.changeIcon')}</div>
                        <div class="emoji-picker-grid">
                            ${CANVAS_EMOJIS.map(icon => `<button class="emoji-option" type="button" data-icon="${escapeHtml(icon)}">${renderCanvasIcon(icon, 14)}</button>`).join('')}
                        </div>
                    </div>
                    <div class="canvas-meta-section">
                        <div class="canvas-meta-label">背景图</div>
                        <div class="canvas-cover-row">
                            <button class="canvas-cover-btn" type="button" data-cover-action="upload">上传图片</button>
                            <button class="canvas-cover-btn canvas-cover-clear ${cover ? '' : 'disabled'}" type="button" data-cover-action="clear" ${cover ? '' : 'disabled'}>清除</button>
                        </div>
                    </div>
                </div>
            ` : ''}
        `;
        if(!trashMode) row.querySelector('.canvas-open').onclick = () => openCanvas(item.id);
        const titleEl = row.querySelector('.canvas-card-title');
        const editBtn = row.querySelector('.canvas-card-edit');
        if(editBtn && titleEl && !trashMode) {
            editBtn.onmousedown = e => e.stopPropagation();
            editBtn.onclick = e => { e.stopPropagation(); startTitleEdit(item.id, titleEl); };
        }
        const iconBtn = row.querySelector('.canvas-preview-mark');
        if(iconBtn && !trashMode) {
            iconBtn.onclick = e => toggleEmojiPicker(item.id, e);
            iconBtn.onkeydown = e => {
                if(e.key === 'Enter' || e.key === ' ') toggleEmojiPicker(item.id, e);
            };
        }
        row.querySelectorAll('.emoji-option').forEach(btn => {
            btn.onclick = e => setCanvasIcon(item.id, btn.dataset.icon, e);
        });
        const pinBtn = row.querySelector('.canvas-pin-btn');
        if(pinBtn){
            pinBtn.onmousedown = e => e.stopPropagation();
            pinBtn.onclick = e => togglePinCanvas(item.id, e);
        }
        const ownerChipEl = row.querySelector('.canvas-owner-chip');
        if(ownerChipEl && !trashMode){
            ownerChipEl.onmousedown = e => e.stopPropagation();
            ownerChipEl.onclick = e => { e.stopPropagation(); toggleEmojiPicker(item.id, e); };
        }
        const copyIdBtn = row.querySelector('.canvas-card-copy-id');
        if(copyIdBtn){
            copyIdBtn.onmousedown = e => e.stopPropagation();
            copyIdBtn.onclick = async e => {
                e.stopPropagation();
                if(await copyTextToClipboard(item.id)){
                    copyIdBtn.classList.add('copied');
                    setStatus(canvasIdStatusText());
                    setTimeout(() => copyIdBtn.classList.remove('copied'), 1400);
                }
            };
        }
        row.querySelectorAll('.canvas-color-swatch').forEach(btn => {
            btn.onmousedown = e => e.stopPropagation();
            btn.onclick = e => setCanvasColorValue(item.id, btn.dataset.color || '', e);
        });
        const exportBtn = row.querySelector('.canvas-card-export');
        if(exportBtn){
            exportBtn.onmousedown = e => e.stopPropagation();
            exportBtn.onclick = e => { e.stopPropagation(); exportCanvasToFile(item.id); };
        }
        const ownerInput = row.querySelector('.canvas-owner-input');
        if(ownerInput){
            ownerInput.onmousedown = e => e.stopPropagation();
            ownerInput.onclick = e => e.stopPropagation();
            ownerInput.onkeydown = e => {
                e.stopPropagation();
                if(e.key === 'Enter'){ e.preventDefault(); ownerInput.blur(); }
                if(e.key === 'Escape'){ e.preventDefault(); emojiPickerCanvasId = null; renderCanvasList(); }
            };
            ownerInput.onblur = () => commitCanvasOwner(item.id, ownerInput.value);
        }
        row.querySelectorAll('.canvas-cover-btn').forEach(btn => {
            btn.onmousedown = e => e.stopPropagation();
            btn.onclick = e => {
                e.stopPropagation();
                const action = btn.dataset.coverAction;
                if(action === 'upload') pickCanvasCoverUpload(item.id);
                else if(action === 'clear') commitCanvasCover(item.id, '');
            };
        });
        const deleteBtn = row.querySelector('.canvas-delete');
        if(deleteBtn) deleteBtn.onclick = e => requestDeleteCanvas(item.id, e);
        const confirmBtn = row.querySelector('.canvas-confirm-btn');
        if(confirmBtn) confirmBtn.onclick = e => trashMode ? purgeCanvas(item.id, e) : deleteCanvas(item.id, e);
        const cancelBtn = row.querySelector('.canvas-cancel-btn');
        if(cancelBtn) cancelBtn.onclick = e => cancelDeleteCanvas(e);
        const restoreBtn = row.querySelector('.canvas-restore');
        if(restoreBtn) restoreBtn.onclick = e => restoreCanvas(item.id, e);
        const purgeBtn = row.querySelector('.canvas-purge');
        if(purgeBtn) purgeBtn.onclick = e => requestPurgeCanvas(item.id, e);
        list.appendChild(row);
    });
    refreshIcons();
    const pop = list.querySelector('.canvas-meta-pop');
    if(pop){
        const card = pop.closest('.canvas-item');
        const mark = card && card.querySelector('.canvas-preview-mark');
        if(card && mark){
            document.body.appendChild(pop);
            const cr = card.getBoundingClientRect();
            const mr = mark.getBoundingClientRect();
            const popH = pop.offsetHeight || 400;
            let top = cr.top + 46;
            if(top + popH > window.innerHeight - 12) top = Math.max(12, window.innerHeight - popH - 12);
            pop.style.position = 'fixed';
            pop.style.left = Math.max(8, mr.left - 4) + 'px';
            pop.style.top = top + 'px';
            pop.style.zIndex = '60';
            pop.style.width = '212px';
        }
    }
}
async function createCanvas(){
    const customTitle = gateTitleInput?.value.trim();
    const titleBase = tr('canvas.newSmartCanvas');
    const title = customTitle || `${titleBase} ${new Date().toLocaleTimeString(window.StudioI18n?.lang() === 'en' ? 'en-US' : 'zh-CN', {hour:'2-digit', minute:'2-digit'})}`;
    trashMode = false;
    refreshGateViewControls();
    setStatus('Creating...');
    try {
        const res = await fetch('/api/canvases', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({title, icon:'sparkles', kind:'smart'})
        });
        if(!res.ok) throw new Error(tr('canvas.createFailed'));
        const data = await res.json();
        setCreateMode(false);
        await loadCanvasList(false);
        openSmartCanvasPage(data.canvas?.id);
    } catch(e) {
        setStatus(tr('canvas.createFailed'));
        console.error(e);
    }
}
async function createSmartCanvas(){
    setCreateMode(true);
}
function openSmartCanvasPage(id){
    if(!id) return;
    const url = `/static/smart-canvas.html?id=${encodeURIComponent(id)}`;
    if(window.parent && window.parent !== window){
        window.parent.postMessage({type:'open-page', page:'smart-canvas', url}, '*');
        return;
    }
    window.location.href = url;
}
function toggleEmojiPicker(id, event){
    event?.preventDefault();
    event?.stopPropagation();
    pendingDeleteCanvasId = null;
    emojiPickerCanvasId = emojiPickerCanvasId === id ? null : id;
    renderCanvasList();
}
async function setCanvasIcon(id, icon, event){
    event?.preventDefault();
    event?.stopPropagation();
    const item = canvases.find(c => c.id === id);
    if(item) item.icon = icon || 'layers';
    emojiPickerCanvasId = null;
    renderCanvasList();
    try {
        let target = canvas?.id === id ? canvas : null;
        if(!target) {
            const data = await fetch(`/api/canvases/${id}`).then(r => r.json());
            target = data.canvas;
        }
        target.icon = icon || 'layers';
        const res = await fetch(`/api/canvases/${id}`, {
            method:'PUT',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({
                title:target.title,
                icon:target.icon,
                nodes:target.nodes || [],
                connections:target.connections || [],
                viewport:target.viewport || {x:0, y:0, scale:1}
            })
        });
        if(!res.ok) throw new Error('图标保存失败');
        if(canvas?.id === id) canvas.icon = target.icon;
        await loadCanvasList(false);
    } catch(e) {
        setStatus('图标保存失败');
        console.error(e);
    }
}
function startTitleEdit(id, titleEl){
    if(!titleEl || titleEl.querySelector('input')) return;
    const item = canvases.find(c => c.id === id);
    const current = item?.title || titleEl.textContent || '';
    const input = document.createElement('input');
    input.type = 'text';
    input.maxLength = 80;
    input.value = current;
    input.className = 'canvas-card-title-input';
    titleEl.innerHTML = '';
    titleEl.appendChild(input);
    input.onmousedown = e => e.stopPropagation();
    input.onclick = e => e.stopPropagation();
    input.focus();
    input.select();
    let done = false;
    const finish = async (commit) => {
        if(done) return;
        done = true;
        const newTitle = input.value.trim();
        if(commit && newTitle && newTitle !== current){
            await setCanvasTitle(id, newTitle);
        } else {
            renderCanvasList();
        }
    };
    input.onblur = () => finish(true);
    input.onkeydown = e => {
        e.stopPropagation();
        if(e.key === 'Enter'){ e.preventDefault(); finish(true); }
        if(e.key === 'Escape'){ e.preventDefault(); finish(false); }
    };
}
async function setCanvasTitle(id, title){
    const item = canvases.find(c => c.id === id);
    if(item) item.title = title;
    if(canvas?.id === id) canvas.title = title;
    renderCanvasList();
    try {
        let target = canvas?.id === id ? canvas : null;
        if(!target){
            const data = await fetch(`/api/canvases/${id}`).then(r => r.json());
            target = data.canvas;
        }
        target.title = title;
        const res = await fetch(`/api/canvases/${id}`, {
            method:'PUT',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({
                title:target.title,
                icon:target.icon,
                nodes:target.nodes || [],
                connections:target.connections || [],
                viewport:target.viewport || {x:0, y:0, scale:1}
            })
        });
        if(!res.ok) throw new Error('重命名失败');
        const saved = await res.json().catch(() => ({}));
        // 重命名联动：通知可能开着同一画布的编辑页同步内存 url，避免其自动保存冲掉后端已移动目录
        if(saved.renamed){
            try { apiChannel.postMessage({type:'canvas-renamed', id, renamed: saved.renamed}); } catch(_) {}
        }
        if(currentCanvasTitle && canvas?.id === id) currentCanvasTitle.textContent = title;
        await loadCanvasList(false);
    } catch(e){
        setStatus('重命名失败');
        console.error(e);
    }
}
async function openCanvas(id){
    openSmartCanvasPage(id);
}
function applyRemoteCanvasData(remote){
    if(!remote || !canvas || remote.id !== canvas.id) return;
    if(localCanvasDirty || saveTimer || savingCanvasNow || saveCanvasAgain){
        clearTimeout(remoteSyncTimer);
        remoteSyncTimer = setTimeout(syncRemoteCanvasNow, 1000);
        return;
    }
    applyingRemoteCanvas = true;
    try {
        resetCascadeRuntimeState();
        const localViewport = localViewportForCanvas(canvas.id, viewport || remote.viewport || {x:0, y:0, scale:1});
        const localSelectedIds = new Set(selected);
        canvas = remote;
        acknowledgedCanvas = JSON.parse(JSON.stringify(remote));
        canvas.logs = canvas.logs || [];
        nodes = canvas.nodes || [];
        connections = canvas.connections || [];
        viewport = localViewport;
        canvas.viewport = {...viewport};
        lastCanvasUpdatedAt = Number(canvas.updated_at || Date.now());
        localCanvasDirty = false;
        resetTransientRunState(nodes);
        sanitizeConnections();
        pruneMissingComfyWorkflows();
        refreshMissingCanvasAssets().then(() => render());
        selected = new Set([...localSelectedIds].filter(id => nodes.some(node => node.id === id)));
        renderCanvasList();
        render();
        if(currentCanvasTitle) currentCanvasTitle.textContent = canvas.title || tr('canvas.untitled');
        if(currentCanvasTime) currentCanvasTime.textContent = formatCanvasTime(canvas.updated_at || canvas.created_at);
        setStatus('Synced');
    } finally {
        applyingRemoteCanvas = false;
    }
}
function resetTransientRunState(list=nodes){
    (list || []).forEach(node => {
        if(!node) return;
        if(node.running) node.running = false;
        if(node.runStatus) node.runStatus = '';
        if(node.runError) node.runError = '';
        if(node._cascadeIdx) node._cascadeIdx = '';
        if(node._cascadeFailed) node._cascadeFailed = false;
    });
}
function canvasLocalAssetUrls(){
    const urls = new Set();
    const add = value => {
        const url = outputUrlValue(value);
        if(url && (url.startsWith('/output/') || url.startsWith('/assets/'))) urls.add(url);
    };
    nodes.forEach(node => {
        if(node.url) add(node.url);
        (node.images || []).forEach(add);
        (node.generatedOutputs || []).forEach(add);
        Object.entries(node.imageComparisons || {}).forEach(([key, value]) => {
            add(key);
            add(value);
        });
    });
    (canvas?.logs || []).forEach(log => {
        (log.outputs || []).forEach(add);
        (log.refs || []).forEach(add);
        (log.run?.refs || []).forEach(add);
    });
    return [...urls];
}
async function refreshMissingCanvasAssets(){
    missingAssetUrls.clear();
    const urls = canvasLocalAssetUrls();
    if(!urls.length) return;
    try {
        const data = await fetch('/api/canvas-assets/check', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({urls})
        }).then(r => r.json());
        const exists = data.exists || {};
        Object.entries(exists).forEach(([url, ok]) => { if(!ok) missingAssetUrls.add(url); });
    } catch(e) {
        console.warn('canvas asset check failed', e);
    }
}
async function syncRemoteCanvasNow(){
    if(!canvas) return;
    try {
        const res = await fetch(`/api/canvases/${canvas.id}`);
        if(!res.ok) throw new Error(tr('canvas.openFailed'));
        const data = await res.json();
        const remote = data.canvas;
        if(Number(remote?.updated_at || 0) >= Number(lastCanvasUpdatedAt || 0)){
            applyRemoteCanvasData(remote);
        }
    } catch(e) {
        console.error(e);
        setStatus('Sync failed');
    }
}
function stopCanvasRemotePolling(){
    if(remoteSyncInterval){
        clearInterval(remoteSyncInterval);
        remoteSyncInterval = null;
    }
}
function handleCanvasUpdatedMessage(data){
    if(!canvas || !data || data.type !== 'canvas_updated') return;
    if(data.client_id && data.client_id === CLIENT_ID) return;
    if(data.canvas_id !== canvas.id) return;
    const remoteUpdatedAt = Number(data.updated_at || 0);
    if(remoteUpdatedAt && remoteUpdatedAt <= Number(lastCanvasUpdatedAt || 0)) return;
    clearTimeout(remoteSyncTimer);
    remoteSyncTimer = setTimeout(syncRemoteCanvasNow, savingCanvasNow ? 700 : 120);
    setStatus('Syncing...');
}
async function returnToCanvasManager(){
    clearTimeout(saveTimer);
    if(canvas && localCanvasDirty) await saveCanvas();
    stopCanvasRemotePolling();
    canvas = null;
    nodes = [];
    connections = [];
    selected.clear();
    viewport = {x: -1800, y: -1000, scale: 1};
    setCanvasMode(false);
    trashMode = false;
    pendingPurgeCanvasId = null;
    refreshGateViewControls();
    await loadCanvasList(false);
    setCreateMode(false);
}
function requestDeleteCanvas(id, event){
    event?.preventDefault();
    event?.stopPropagation();
    emojiPickerCanvasId = null;
    pendingPurgeCanvasId = null;
    pendingDeleteCanvasId = id;
    renderCanvasList();
}
function requestPurgeCanvas(id, event){
    event?.preventDefault();
    event?.stopPropagation();
    emojiPickerCanvasId = null;
    pendingDeleteCanvasId = null;
    pendingPurgeCanvasId = id;
    renderCanvasList();
}
function cancelDeleteCanvas(event){
    event?.preventDefault();
    event?.stopPropagation();
    pendingDeleteCanvasId = null;
    pendingPurgeCanvasId = null;
    renderCanvasList();
}
async function deleteCanvas(id, event){
    event?.preventDefault();
    event?.stopPropagation();
    setStatus('Moving to trash...');
    try {
        const res = await fetch(`/api/canvases/${id}`, {method:'DELETE'});
        if(!res.ok) throw new Error(tr('canvas.moveToTrashFailed'));
        const deletingCurrent = canvas?.id === id;
        pendingDeleteCanvasId = null;
        canvases = canvases.filter(item => item.id !== id);
        if(deletingCurrent){
            canvas = null;
            nodes = [];
            connections = [];
            selected.clear();
            viewport = {x: -1800, y: -1000, scale: 1};
            setCanvasMode(false);
        }
        renderCanvasList();
        setStatus(canvases.length ? tr('canvas.movedToTrash') : tr('canvas.noCanvasCreateFirst'));
        await loadCanvasList(false);
    } catch(e) {
        setStatus(tr('canvas.moveToTrashFailed'));
        console.error(e);
    }
}
async function restoreCanvas(id, event){
    event?.preventDefault();
    event?.stopPropagation();
    setStatus('Restoring...');
    try {
        const res = await fetch(`/api/canvases/${id}/restore`, {method:'POST'});
        if(!res.ok) throw new Error(tr('canvas.restoreFailed'));
        pendingPurgeCanvasId = null;
        deletedCanvases = deletedCanvases.filter(item => item.id !== id);
        await loadCanvasList(false);
        await loadTrashList();
        setStatus(tr('canvas.restored'));
    } catch(e) {
        setStatus(tr('canvas.restoreFailed'));
        console.error(e);
    }
}
async function purgeCanvas(id, event){
    event?.preventDefault();
    event?.stopPropagation();
    setStatus('Deleting...');
    try {
        const res = await fetch(`/api/canvases/${id}/purge`, {method:'DELETE'});
        if(!res.ok) throw new Error(tr('canvas.purgeFailed'));
        pendingPurgeCanvasId = null;
        deletedCanvases = deletedCanvases.filter(item => item.id !== id);
        renderCanvasList();
        setStatus(deletedCanvases.length ? tr('canvas.purged') : tr('canvas.trashEmpty'));
        await loadTrashList();
    } catch(e) {
        setStatus(tr('canvas.purgeFailed'));
        console.error(e);
    }
}
async function purgeAllTrash(){
    if(!trashMode) return;
    const n = deletedCanvases.length;
    if(!n) return;
    const confirmMsg = tr('canvas.purgeAllConfirm').replace('{n}', String(n));
    if(!window.confirm(confirmMsg)) return;
    setStatus(tr('canvas.purgingTrash'));
    try {
        const res = await fetch('/api/canvases/trash/purge-all', {method:'DELETE'});
        if(!res.ok) throw new Error(tr('canvas.purgeFailed') || 'purge failed');
        const data = await res.json();
        const purged = Number(data?.purged ?? 0);
        deletedCanvases = [];
        pendingPurgeCanvasId = null;
        refreshGateViewControls();
        renderCanvasList();
        setStatus(purged
            ? tr('canvas.purgedCount').replace('{n}', String(purged))
            : tr('canvas.trashEmpty'));
        await loadTrashList();
    } catch(e) {
        setStatus(tr('canvas.purgeFailed') || 'purge failed');
        console.error(e);
    }
}
window.purgeAllTrash = purgeAllTrash;
window.createCanvas = createCanvas;
window.createSmartCanvas = createSmartCanvas;
window.loadCanvasList = loadCanvasList;
window.openCanvas = openCanvas;
window.deleteCanvas = deleteCanvas;
window.returnToCanvasManager = returnToCanvasManager;
normalizeGateActions();
gateCreateBtn?.addEventListener('click', () => setCreateMode(true));
gateCreateSmartBtn?.addEventListener('click', createSmartCanvas);
gateBackBtn.addEventListener('click', () => setTrashMode(false));
gateTrashBtn.addEventListener('click', () => setTrashMode(true));
gateRefreshBtn.addEventListener('click', () => trashMode ? loadTrashList() : loadCanvasList(false));
gatePurgeAllBtn?.addEventListener('click', (e) => { e.preventDefault(); e.stopPropagation(); purgeAllTrash(); });
document.getElementById('gateSortSwitch')?.addEventListener('click', e => {
    const btn = e.target.closest('[data-sort]');
    if(btn) setCanvasSortMode(btn.dataset.sort);
});
gateConfirmBtn.addEventListener('click', createCanvas);
gateCancelBtn.addEventListener('click', () => setCreateMode(false));
gateTitleInput.addEventListener('keydown', e => {
    if(e.key === 'Enter') createCanvas();
    if(e.key === 'Escape') setCreateMode(false);
});
document.addEventListener('mousedown', e => {
    if(emojiPickerCanvasId === null) return;
    if(e.target.closest('.canvas-meta-pop') || e.target.closest('.canvas-preview-mark') || e.target.closest('.canvas-owner-chip')) return;
    emojiPickerCanvasId = null;
    renderCanvasList();
});
window.addEventListener('studio-theme-change', event => applyTheme(event.detail?.theme || 'dark'));
// 图片编辑区滚轮缩放

const IMAGE_DROP_EXT_RE = /\.(png|jpe?g|webp|gif)$/i;
const IMAGE_DROP_TEXT_TYPES = [
    'text/uri-list',
    'text/plain',
    'text/html',
    'DownloadURL',
    'text/x-moz-url',
    'text/x-file-url',
    'public.file-url',
    'public.url',
    'UniformResourceLocator',
    'FileName',
    'FileNameW'
];
const IMAGE_DROP_TYPE_HINT_RE = /^(?:files?|image\/.+|text\/(?:uri-list|html|plain|x-moz-url|x-file-url)|downloadurl|public\.(?:file-url|url)|uniformresourcelocator|filenamew?)$|application\/x-qt-(?:windows-mime|image)|application\/x-moz-file|com\.eagle/i;
const MASK_BRUSH_ALPHA = 115;
const MASK_BRUSH_COLOR = `rgba(255,255,255,${MASK_BRUSH_ALPHA / 255})`;
// ——— 自定义宫格辅助函数 ———
// ——— 图片缩放 ———


const loopPromptVisiting = new Set();
function canvasAssetLibraries(){
    return Array.isArray(canvasAssetLibrary.libraries) && canvasAssetLibrary.libraries.length ? canvasAssetLibrary.libraries : [{id:'default', name:'默认资产库', categories:canvasAssetLibrary.categories || []}];
}
function activeCanvasAssetLibrary(){
    const libs = canvasAssetLibraries();
    return libs.find(lib => lib.id === activeCanvasAssetLibraryId) || libs[0] || null;
}
function canvasAssetCategories(){
    return (activeCanvasAssetLibrary()?.categories || canvasAssetLibrary.categories || []).filter(cat => {
        const type = String(cat.type || 'image').toLowerCase();
        return type === 'image' || type === 'media';
    });
}
function activeCanvasAssetCategory(){
    const cats = canvasAssetCategories();
    return cats.find(cat => cat.id === activeCanvasAssetCategoryId) || cats[0] || null;
}
async function loadCanvasAssetLibrary({renderPanel=true}={}){
    try {
        const data = await fetch('/api/asset-library').then(r => r.json());
        canvasAssetLibrary = data.library || canvasAssetLibrary;
        const libs = canvasAssetLibraries();
        if(!activeCanvasAssetLibraryId) activeCanvasAssetLibraryId = canvasAssetLibrary.active_library_id || libs[0]?.id || '';
        if(!libs.some(lib => lib.id === activeCanvasAssetLibraryId)) activeCanvasAssetLibraryId = libs[0]?.id || '';
        const cats = canvasAssetCategories();
        if(!cats.some(cat => cat.id === activeCanvasAssetCategoryId)) activeCanvasAssetCategoryId = cats[0]?.id || '';
        return data;
    } catch(e) {
        setStatus('资产库加载失败');
        return null;
    }
}
async function uploadFilesToLibrary(files, libraryId, categoryId){
    const form = new FormData();
    [...files].forEach(file => form.append('files', file));
    // 素材库是跨画布资源：落 assets/library/，不随任何画布删除
    const uploaded = await fetch('/api/ai/upload?scope=library', {method:'POST', body:form}).then(r => r.json());
    const items = (uploaded.files || []).filter(file => file?.url).map(file => ({library_id:libraryId, category_id:categoryId, url:file.url, name:file.name || 'asset'}));
    if(!items.length) return null;
    return fetch('/api/asset-library/items/batch', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({library_id:libraryId, category_id:categoryId, items})
    }).then(r => r.json());
}
function openAssetManager(){
    assetManagerModal?.classList.add('open');
    managerSelectedAssetIds.clear();
    managerSelectedPromptIds.clear();
    canvasPromptTemplatesLoaded = false;
    Promise.all([loadCanvasAssetLibrary({renderPanel:false}), loadCanvasPromptTemplates()]).then(renderAssetManager);
}
function closeAssetManager(){
    assetManagerModal?.classList.remove('open');
}
window.closeAssetManager = closeAssetManager;
function renderAssetManager(){
    if(!assetManagerBody) return;
    document.querySelectorAll('[data-manager-tab]').forEach(btn => btn.classList.toggle('active', btn.dataset.managerTab === assetManagerTab));
    if(assetManagerTab === 'prompts') renderPromptAssetManager();
    else renderImageAssetManager();
    refreshIcons();
}
function renderImageAssetManager(){
    const libs = canvasAssetLibraries();
    const library = activeCanvasAssetLibrary();
    const cats = canvasAssetCategories();
    const cat = activeCanvasAssetCategory();
    const items = cat?.items || [];
    const canEditLibrary = !!library;
    const canEditCategory = !!cat;
    assetManagerBody.innerHTML = `
        <div class="asset-manager-side">
            <div class="asset-manager-tools">
                <button type="button" class="primary" data-manager-asset-lib-new><i data-lucide="plus" class="w-4 h-4"></i><span>新资产库</span></button>
                <button type="button" ${!canEditLibrary ? 'disabled' : ''} data-manager-asset-lib-rename><i data-lucide="pencil" class="w-4 h-4"></i><span>重命名</span></button>
                <button type="button" class="danger" ${libs.length <= 1 ? 'disabled' : ''} data-manager-asset-lib-delete><i data-lucide="trash-2" class="w-4 h-4"></i><span>删除库</span></button>
            </div>
            <div class="asset-manager-list">
                ${libs.map(lib => `<button type="button" class="${lib.id === activeCanvasAssetLibraryId ? 'active' : ''}" data-manager-asset-lib="${escapeAttr(lib.id)}"><span>${escapeHtml(lib.name || '资产库')}</span><small>${(lib.categories || []).reduce((n,c)=>n+(c.items || []).length,0)}</small></button>`).join('')}
            </div>
            <div class="asset-manager-tools">
                <button type="button" class="primary" data-manager-asset-cat-new><i data-lucide="folder-plus" class="w-4 h-4"></i><span>新分组</span></button>
                <button type="button" ${!canEditCategory ? 'disabled' : ''} data-manager-asset-cat-rename><i data-lucide="pencil" class="w-4 h-4"></i><span>重命名</span></button>
                <button type="button" class="danger" ${!canEditCategory ? 'disabled' : ''} data-manager-asset-cat-delete><i data-lucide="trash-2" class="w-4 h-4"></i><span>删除组</span></button>
            </div>
            <div class="asset-manager-list">
                ${cats.map(item => `<button type="button" class="${item.id === activeCanvasAssetCategoryId ? 'active' : ''}" data-manager-asset-cat="${escapeAttr(item.id)}"><span>${escapeHtml(item.name || '分组')}</span><small>${(item.items || []).length}</small></button>`).join('')}
            </div>
        </div>
        <div class="asset-manager-main">
            <div class="asset-manager-tools">
                <label class="${!cat ? 'disabled' : ''}"><i data-lucide="upload" class="w-4 h-4"></i><span>批量上传</span><input id="managerAssetUpload" type="file" multiple accept="image/*" ${!cat ? 'disabled' : ''}></label>
                <button type="button" class="danger" ${managerSelectedAssetIds.size ? '' : 'disabled'} data-manager-asset-delete><i data-lucide="trash-2" class="w-4 h-4"></i><span>删除所选 ${managerSelectedAssetIds.size ? managerSelectedAssetIds.size : ''}</span></button>
            </div>
            <div class="asset-manager-grid">
                ${items.length ? items.map(item => `<div class="asset-manager-card">
                    <input type="checkbox" data-manager-asset-check="${escapeAttr(item.id)}" ${managerSelectedAssetIds.has(item.id) ? 'checked' : ''}>
                    <img src="${escapeAttr(item.thumbnail || item.url || '')}" alt="">
                    <span class="asset-manager-card-name" title="${escapeAttr(item.name || '')}">${escapeHtml(item.name || 'asset')}</span>
                    <div class="asset-manager-card-actions">
                        <button type="button" data-manager-asset-rename="${escapeAttr(item.id)}"><i data-lucide="pencil" class="w-3.5 h-3.5"></i><span>重命名</span></button>
                        <button type="button" class="danger" data-manager-asset-remove="${escapeAttr(item.id)}"><i data-lucide="trash-2" class="w-3.5 h-3.5"></i><span>删除</span></button>
                    </div>
                </div>`).join('') : `<div class="canvas-asset-empty">当前分组为空</div>`}
            </div>
        </div>
    `;
    const upload = document.getElementById('managerAssetUpload');
    upload?.addEventListener('change', async () => {
        if(!upload.files?.length || !cat) return;
        const data = await uploadFilesToLibrary(upload.files, library.id, cat.id);
        if(data?.library) canvasAssetLibrary = data.library;
        managerSelectedAssetIds.clear();
        renderAssetManager();
        renderCanvasAssetLibrary();
    });
}
function renderPromptAssetManager(){
    const libs = canvasPromptLibraries.filter(lib => lib.id !== 'system');
    if(!canvasPromptLibraries.some(lib => lib.id === activePromptLibraryId)) activePromptLibraryId = libs[0]?.id || canvasPromptLibraries[0]?.id || 'system';
    const lib = canvasPromptLibraries.find(item => item.id === activePromptLibraryId) || libs[0] || null;
    const items = lib?.items || [];
    const canEditLibrary = !!lib && !lib.readonly;
    assetManagerBody.innerHTML = `
        <div class="asset-manager-side">
            <div class="asset-manager-tools">
                <button type="button" class="primary" data-manager-prompt-lib-new><i data-lucide="plus" class="w-4 h-4"></i><span>新提示词库</span></button>
                <button type="button" ${!canEditLibrary ? 'disabled' : ''} data-manager-prompt-lib-rename><i data-lucide="pencil" class="w-4 h-4"></i><span>重命名</span></button>
                <button type="button" class="danger" ${!canEditLibrary || canvasPromptLibraries.length <= 1 ? 'disabled' : ''} data-manager-prompt-lib-delete><i data-lucide="trash-2" class="w-4 h-4"></i><span>删除库</span></button>
            </div>
            <div class="asset-manager-list">
                ${canvasPromptLibraries.map(library => `<button type="button" class="${library.id === activePromptLibraryId ? 'active' : ''}" data-manager-prompt-lib="${escapeAttr(library.id)}"><span>${escapeHtml(library.name || '提示词库')}</span><small>${(library.items || []).length}</small></button>`).join('')}
            </div>
        </div>
        <div class="asset-manager-main">
            <div class="asset-manager-tools">
                <button type="button" class="primary" ${!lib || lib.readonly ? 'disabled' : ''} data-manager-prompt-new><i data-lucide="file-plus-2" class="w-4 h-4"></i><span>新增提示词</span></button>
                <button type="button" class="danger" ${!lib || lib.readonly || !managerSelectedPromptIds.size ? 'disabled' : ''} data-manager-prompt-delete><i data-lucide="trash-2" class="w-4 h-4"></i><span>删除所选 ${managerSelectedPromptIds.size ? managerSelectedPromptIds.size : ''}</span></button>
            </div>
            <div class="asset-manager-grid">
                ${items.length ? items.map(item => `<div class="asset-manager-card">
                    <input type="checkbox" data-manager-prompt-check="${escapeAttr(item.id)}" ${managerSelectedPromptIds.has(item.id) ? 'checked' : ''} ${lib?.readonly ? 'disabled' : ''}>
                    <div class="asset-manager-card-text">${escapeHtml(item.positive || '')}</div>
                    <span class="asset-manager-card-name" title="${escapeAttr(item.name || '')}">${escapeHtml(item.name || '提示词')}</span>
                    <div class="asset-manager-card-actions">
                        <button type="button" ${lib?.readonly ? 'disabled' : ''} data-manager-prompt-edit="${escapeAttr(item.id)}"><i data-lucide="pencil" class="w-3.5 h-3.5"></i><span>编辑</span></button>
                        <button type="button" class="danger" ${lib?.readonly ? 'disabled' : ''} data-manager-prompt-remove="${escapeAttr(item.id)}"><i data-lucide="trash-2" class="w-3.5 h-3.5"></i><span>删除</span></button>
                    </div>
                </div>`).join('') : `<div class="canvas-asset-empty">当前提示词库为空</div>`}
            </div>
        </div>
    `;
}
async function loadCanvasPromptTemplates(){
    if(canvasPromptTemplatesLoaded) return canvasPromptTemplates;
    try {
        loadCanvasPromptTemplateGroups();
        loadCanvasPromptTemplateOverrides();
        const data = await fetch('/api/prompt-libraries').then(r => r.ok ? r.json() : {library:{libraries:[]}});
        canvasPromptLibraries = Array.isArray(data.library?.libraries) ? data.library.libraries : [];
        if(!canvasPromptLibraries.some(lib => lib.id === activePromptLibraryId)) {
            activePromptLibraryId = canvasPromptLibraries.some(lib => lib.id === 'system') ? 'system' : (canvasPromptLibraries[0]?.id || 'system');
        }
        canvasPromptTemplates = activeCanvasPromptLibraryItems();
    } catch(e) {
        canvasPromptTemplates = [];
        canvasPromptLibraries = [];
    }
    canvasPromptTemplatesLoaded = true;
    return canvasPromptTemplates;
}
function activeCanvasPromptLibrary(){
    return canvasPromptLibraries.find(lib => lib.id === activePromptLibraryId) || canvasPromptLibraries[0] || {id:'system', name:'系统提示词库', readonly:true, items:[]};
}
function defaultCanvasPromptTemplateGroups(){
    return [
        {id:'view', name:tr('smart.tplCatView')},
        {id:'storyboard', name:tr('smart.tplCatStoryboard')},
        {id:'character', name:tr('smart.tplCatCharacter')},
        {id:'product', name:tr('smart.tplCatProduct')},
        {id:'lighting', name:tr('smart.tplCatLighting')},
        {id:'mine', name:tr('smart.tplCatMine')}
    ];
}
function loadCanvasPromptTemplateGroups(){
    try {
        const list = JSON.parse(localStorage.getItem(CANVAS_PROMPT_TEMPLATE_GROUPS_KEY) || '[]');
        const valid = Array.isArray(list) ? list.filter(g => g?.id && g?.name) : [];
        const defaults = defaultCanvasPromptTemplateGroups();
        promptTemplateGroups = defaults.map(group => valid.find(g => g.id === group.id) || group);
        valid.filter(g => !promptTemplateGroups.some(x => x.id === g.id)).forEach(g => promptTemplateGroups.push(g));
    } catch(e) {
        promptTemplateGroups = defaultCanvasPromptTemplateGroups();
    }
}
function loadCanvasPromptTemplateOverrides(){
    try {
        const data = JSON.parse(localStorage.getItem(CANVAS_PROMPT_TEMPLATE_OVERRIDES_KEY) || '{}');
        canvasPromptTemplateOverrides = {
            hiddenBuiltinIds:Array.isArray(data.hiddenBuiltinIds) ? data.hiddenBuiltinIds : [],
            editedBuiltins:data.editedBuiltins && typeof data.editedBuiltins === 'object' ? data.editedBuiltins : {}
        };
    } catch(e) {
        canvasPromptTemplateOverrides = {hiddenBuiltinIds:[], editedBuiltins:{}};
    }
}
function activeCanvasPromptLibraryItems(){
    const lib = activeCanvasPromptLibrary();
    const hidden = new Set(canvasPromptTemplateOverrides.hiddenBuiltinIds || []);
    if(lib.id !== 'system'){
        return (lib.items || []).filter(t => t?.id && t?.positive).map(t => ({
            ...t,
            sourceId:t.id,
            remote:true,
            libraryId:lib.id,
            libraryName:lib.name || '提示词库',
            builtin:false,
        }));
    }
    const system = canvasPromptLibraries.find(item => item.id === 'system') || lib;
    const builtins = (system.items || [])
        .filter(t => t?.id && t?.positive && !hidden.has(t.id))
        .map(t => ({
            ...t,
            ...(canvasPromptTemplateOverrides.editedBuiltins?.[t.id] || {}),
            sourceId:t.id,
            builtin:true,
            remote:false,
            libraryId:'system',
            libraryName:'系统提示词库',
        }));
    const remotes = canvasPromptLibraries
        .filter(item => item.id !== 'system')
        .flatMap(item => (item.items || [])
            .filter(t => t?.id && t?.positive)
            .map(t => ({
                ...t,
                sourceId:t.id,
                remote:true,
                builtin:false,
                libraryId:item.id,
                libraryName:item.name || '提示词库',
            })));
    return [...builtins, ...remotes];
}
function refreshCanvasPromptTemplatesFromLibraries(){
    canvasPromptTemplatesLoaded = true;
    canvasPromptTemplates = activeCanvasPromptLibraryItems();
}
function hasComfyWorkflow(name){
    const resolved = resolveComfyWorkflowName(name);
    return !!resolved && comfyWorkflows.some(w => w.name === resolved);
}
function pruneMissingComfyWorkflows(){
    let changed = false;
    nodes.filter(n => n.type === 'comfy').forEach(node => {
        const resolved = resolveComfyWorkflowName(node.comfyWorkflow);
        if(node.comfyWorkflow && resolved && node.comfyWorkflow !== resolved){
            node.comfyWorkflow = resolved;
            changed = true;
        }
        if(node.comfyWorkflow && !hasComfyWorkflow(node.comfyWorkflow)){
            delete comfyWorkflowCache[node.comfyWorkflow];
            node.comfyWorkflow = '';
            changed = true;
        }
    });
    if(changed) scheduleSave();
}
async function ensureComfyWorkflow(name){
    const resolved = resolveComfyWorkflowName(name);
    if(!hasComfyWorkflow(resolved)) return null;
    if(comfyWorkflowCache[resolved]) return comfyWorkflowCache[resolved];
    const res = await fetch(`/api/workflows/${encodeURIComponent(resolved)}`);
    if(!res.ok){
        delete comfyWorkflowCache[resolved];
        return null;
    }
    const data = await res.json();
    comfyWorkflowCache[resolved] = data;
    if(name && name !== resolved) comfyWorkflowCache[name] = data;
    return data;
}
const RH_KNOWN_FIELD_OPTIONS = {
    aspectRatio:['1:1','16:9','9:16','4:3','3:4','4:5','5:4','3:2','2:3','21:9','9:21'],
    aspect_ratio:['1:1','16:9','9:16','4:3','3:4','4:5','5:4','3:2','2:3','21:9','9:21'],
    ratio:['1:1','16:9','9:16','21:9','9:21','4:3','3:4','4:5','5:4','3:2','2:3'],
    resolution:['1k','2k','4k','8k'],
    size:['512','768','1024','1280','1536','2048'],
    mode:['text2img','img2img'],
    quality:['low','medium','high','best'],
    instanceType:['default','plus','pro'],
    instance_type:['default','plus','pro'],
    precision:['fp16','fp32','bf16'],
    scheduler:['normal','karras','exponential','sgm_uniform','simple','ddim_uniform'],
    sampler:['euler','euler_ancestral','heun','dpm_2','dpm_2_ancestral','lms','dpmpp_2m','dpmpp_sde','ddim','uni_pc']
};

const CANVAS_GENERATOR_TYPES = ['generator','comfy','ltxDirector','video','rh'];
const CANVAS_IMAGE_OUTPUT_TYPES = ['generator','comfy','ltxDirector','rh'];
const CANVAS_MEDIA_OUTPUT_TYPES = ['generator','comfy','ltxDirector','video','rh'];
function resetCascadeRuntimeState(){
    cascadeRunningIds.clear();
    cascadeStopIds.clear();
    cascadeSerialIds.clear();
    cascadeContexts.forEach(ctx => clearCascadeCleanupTimer(ctx));
    cascadeContexts.clear();
    loopContext = null;
}
function clearCascadeCleanupTimer(ctx){
    if(!ctx?.cleanupTimer) return;
    clearTimeout(ctx.cleanupTimer);
    ctx.cleanupTimer = null;
}
// 判断是不是「链尾」节点：没有下游生成节点（直接相连或经 Output 中转都算）
// —— 一键运行：从目标节点反向追溯到所有上游生成节点，按拓扑顺序串行执行 ——
// 失败重试：从该节点继续往下游跑


// 生成结果导出目录：应由后端按当前用户数据目录下发，前端不能写死开发者本机路径
// （写死绝对路径会污染发布包，也会让装在其他机器上的实例导出到错误位置）
const GENERATED_OUTPUT_EXPORT_FOLDER = '';
const generatedOutputNameReservations = new Set();
function outputUrlValue(item){
    return typeof item === 'string' ? item : item?.url || '';
}
gateAssetManagerBtn?.addEventListener('click', openAssetManager);
document.querySelectorAll('[data-manager-tab]').forEach(btn => {
    btn.addEventListener('click', () => {
        assetManagerTab = btn.dataset.managerTab || 'assets';
        renderAssetManager();
    });
});
assetManagerModal?.addEventListener('change', event => {
    let shouldRender = false;
    const assetCheck = event.target.closest?.('[data-manager-asset-check]');
    if(assetCheck){
        if(assetCheck.checked) managerSelectedAssetIds.add(assetCheck.dataset.managerAssetCheck);
        else managerSelectedAssetIds.delete(assetCheck.dataset.managerAssetCheck);
        shouldRender = true;
    }
    const promptCheck = event.target.closest?.('[data-manager-prompt-check]');
    if(promptCheck){
        if(promptCheck.checked) managerSelectedPromptIds.add(promptCheck.dataset.managerPromptCheck);
        else managerSelectedPromptIds.delete(promptCheck.dataset.managerPromptCheck);
        shouldRender = true;
    }
    if(shouldRender) renderAssetManager();
});
assetManagerModal?.addEventListener('click', async event => {
    const assetLib = event.target.closest?.('[data-manager-asset-lib]');
    if(assetLib){ activeCanvasAssetLibraryId = assetLib.dataset.managerAssetLib || ''; activeCanvasAssetCategoryId = ''; managerSelectedAssetIds.clear(); renderAssetManager(); return; }
    const assetCat = event.target.closest?.('[data-manager-asset-cat]');
    if(assetCat){ activeCanvasAssetCategoryId = assetCat.dataset.managerAssetCat || ''; managerSelectedAssetIds.clear(); renderAssetManager(); return; }
    const promptLib = event.target.closest?.('[data-manager-prompt-lib]');
    if(promptLib){ activePromptLibraryId = promptLib.dataset.managerPromptLib || 'system'; managerSelectedPromptIds.clear(); renderAssetManager(); return; }
    const assetRename = event.target.closest?.('[data-manager-asset-rename]');
    if(assetRename){
        const itemId = assetRename.dataset.managerAssetRename || '';
        const item = (activeCanvasAssetCategory()?.items || []).find(entry => entry.id === itemId);
        const name = window.prompt('资产名称', item?.name || '');
        if(!item || !String(name || '').trim()) return;
        const data = await fetch(`/api/asset-library/items/${encodeURIComponent(item.id)}`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name})}).then(r => r.json());
        canvasAssetLibrary = data.library || canvasAssetLibrary;
        renderAssetManager(); renderCanvasAssetLibrary(); return;
    }
    const assetRemove = event.target.closest?.('[data-manager-asset-remove]');
    if(assetRemove){
        const itemId = assetRemove.dataset.managerAssetRemove || '';
        const item = (activeCanvasAssetCategory()?.items || []).find(entry => entry.id === itemId);
        if(!item || !window.confirm(`删除资产「${item.name || 'asset'}」？`)) return;
        const data = await fetch(`/api/asset-library/items/${encodeURIComponent(item.id)}`, {method:'DELETE'}).then(r => r.json());
        canvasAssetLibrary = data.library || canvasAssetLibrary;
        managerSelectedAssetIds.delete(item.id);
        renderAssetManager(); renderCanvasAssetLibrary(); return;
    }
    const promptEdit = event.target.closest?.('[data-manager-prompt-edit]');
    if(promptEdit){
        const lib = activeCanvasPromptLibrary();
        if(!lib || lib.readonly) return;
        const itemId = promptEdit.dataset.managerPromptEdit || '';
        const item = (lib.items || []).find(entry => entry.id === itemId);
        if(!item) return;
        const name = window.prompt('提示词名称', item.name || '提示词');
        if(!String(name || '').trim()) return;
        const positive = window.prompt('提示词内容', item.positive || '');
        if(!String(positive || '').trim()) return;
        const data = await fetch(`/api/prompt-libraries/items/${encodeURIComponent(item.id)}`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({library_id:lib.id, name, positive, negative:item.negative || '', category:item.category || 'mine', scene:item.scene || ''})}).then(r => r.json());
        canvasPromptLibraries = data.library?.libraries || canvasPromptLibraries;
        refreshCanvasPromptTemplatesFromLibraries();
        renderAssetManager(); return;
    }
    const promptRemove = event.target.closest?.('[data-manager-prompt-remove]');
    if(promptRemove){
        const lib = activeCanvasPromptLibrary();
        if(!lib || lib.readonly) return;
        const itemId = promptRemove.dataset.managerPromptRemove || '';
        const item = (lib.items || []).find(entry => entry.id === itemId);
        if(!item || !window.confirm(`删除提示词「${item.name || '提示词'}」？`)) return;
        const data = await fetch(`/api/prompt-libraries/items/${encodeURIComponent(item.id)}`, {method:'DELETE'}).then(r => r.json());
        canvasPromptLibraries = data.library?.libraries || canvasPromptLibraries;
        managerSelectedPromptIds.delete(item.id);
        refreshCanvasPromptTemplatesFromLibraries();
        renderAssetManager(); return;
    }
    if(event.target.closest?.('[data-manager-asset-lib-new]')){
        const name = window.prompt('资产库名称', '新资产库');
        if(!String(name || '').trim()) return;
        const data = await fetch('/api/asset-library/libraries', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name})}).then(r => r.json());
        canvasAssetLibrary = data.library || canvasAssetLibrary;
        activeCanvasAssetLibraryId = data.asset_library?.id || activeCanvasAssetLibraryId;
        activeCanvasAssetCategoryId = '';
        renderAssetManager(); renderCanvasAssetLibrary(); return;
    }
    if(event.target.closest?.('[data-manager-asset-lib-rename]')){
        const lib = activeCanvasAssetLibrary();
        const name = window.prompt('资产库名称', lib?.name || '');
        if(!lib || !String(name || '').trim()) return;
        const data = await fetch(`/api/asset-library/libraries/${encodeURIComponent(lib.id)}`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name})}).then(r => r.json());
        canvasAssetLibrary = data.library || canvasAssetLibrary;
        renderAssetManager(); renderCanvasAssetLibrary(); return;
    }
    if(event.target.closest?.('[data-manager-asset-lib-delete]')){
        const lib = activeCanvasAssetLibrary();
        if(!lib || !window.confirm(`删除资产库「${lib.name || '资产库'}」？`)) return;
        const data = await fetch(`/api/asset-library/libraries/${encodeURIComponent(lib.id)}`, {method:'DELETE'}).then(r => r.json());
        canvasAssetLibrary = data.library || canvasAssetLibrary;
        activeCanvasAssetLibraryId = canvasAssetLibrary.active_library_id || canvasAssetLibraries()[0]?.id || '';
        activeCanvasAssetCategoryId = '';
        renderAssetManager(); renderCanvasAssetLibrary(); return;
    }
    if(event.target.closest?.('[data-manager-asset-cat-new]')){
        const name = window.prompt('分组名称', '新分组');
        if(!String(name || '').trim()) return;
        const data = await fetch('/api/asset-library/categories', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({library_id:activeCanvasAssetLibraryId, name, type:'image'})}).then(r => r.json());
        canvasAssetLibrary = data.library || canvasAssetLibrary;
        activeCanvasAssetCategoryId = data.category?.id || activeCanvasAssetCategoryId;
        renderAssetManager(); renderCanvasAssetLibrary(); return;
    }
    if(event.target.closest?.('[data-manager-asset-cat-rename]')){
        const cat = activeCanvasAssetCategory();
        const name = window.prompt('分组名称', cat?.name || '');
        if(!cat || !String(name || '').trim()) return;
        const data = await fetch(`/api/asset-library/categories/${encodeURIComponent(cat.id)}`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name})}).then(r => r.json());
        canvasAssetLibrary = data.library || canvasAssetLibrary;
        renderAssetManager(); renderCanvasAssetLibrary(); return;
    }
    if(event.target.closest?.('[data-manager-asset-cat-delete]')){
        const cat = activeCanvasAssetCategory();
        if(!cat || !window.confirm(`删除分组「${cat.name || '分组'}」？`)) return;
        const data = await fetch(`/api/asset-library/categories/${encodeURIComponent(cat.id)}`, {method:'DELETE'}).then(r => r.json());
        canvasAssetLibrary = data.library || canvasAssetLibrary;
        activeCanvasAssetCategoryId = canvasAssetCategories()[0]?.id || '';
        renderAssetManager(); renderCanvasAssetLibrary(); return;
    }
    if(event.target.closest?.('[data-manager-asset-delete]')){
        if(!managerSelectedAssetIds.size) return;
        const data = await fetch('/api/asset-library/items/delete', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({library_id:activeCanvasAssetLibraryId, ids:[...managerSelectedAssetIds]})}).then(r => r.json());
        canvasAssetLibrary = data.library || canvasAssetLibrary;
        managerSelectedAssetIds.clear();
        renderAssetManager(); renderCanvasAssetLibrary(); return;
    }
    if(event.target.closest?.('[data-manager-prompt-lib-new]')){
        const name = window.prompt('提示词库名称', '新提示词库');
        if(!String(name || '').trim()) return;
        const data = await fetch('/api/prompt-libraries', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name})}).then(r => r.json());
        canvasPromptLibraries = data.library?.libraries || canvasPromptLibraries;
        activePromptLibraryId = data.prompt_library?.id || activePromptLibraryId;
        refreshCanvasPromptTemplatesFromLibraries();
        renderAssetManager(); return;
    }
    if(event.target.closest?.('[data-manager-prompt-lib-rename]')){
        const lib = activeCanvasPromptLibrary();
        if(!lib || lib.readonly) return;
        const name = window.prompt('提示词库名称', lib.name || '');
        if(!String(name || '').trim()) return;
        const data = await fetch(`/api/prompt-libraries/${encodeURIComponent(lib.id)}`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name})}).then(r => r.json());
        canvasPromptLibraries = data.library?.libraries || canvasPromptLibraries;
        refreshCanvasPromptTemplatesFromLibraries();
        renderAssetManager(); return;
    }
    if(event.target.closest?.('[data-manager-prompt-lib-delete]')){
        const lib = activeCanvasPromptLibrary();
        if(!lib || lib.readonly || !window.confirm(`删除提示词库「${lib.name || '提示词库'}」？`)) return;
        const data = await fetch(`/api/prompt-libraries/${encodeURIComponent(lib.id)}`, {method:'DELETE'}).then(r => r.json());
        canvasPromptLibraries = data.library?.libraries || canvasPromptLibraries;
        activePromptLibraryId = data.library?.active_library_id || canvasPromptLibraries.find(item => item.id !== 'system')?.id || 'system';
        refreshCanvasPromptTemplatesFromLibraries();
        renderAssetManager(); return;
    }
    if(event.target.closest?.('[data-manager-prompt-new]')){
        const lib = activeCanvasPromptLibrary();
        if(!lib || lib.readonly) return;
        const name = window.prompt('提示词名称', '新提示词');
        if(!String(name || '').trim()) return;
        const positive = window.prompt('提示词内容', '');
        if(!String(positive || '').trim()) return;
        const data = await fetch('/api/prompt-libraries/items', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({library_id:lib.id, name, positive, category:'mine'})}).then(r => r.json());
        canvasPromptLibraries = data.library?.libraries || canvasPromptLibraries;
        refreshCanvasPromptTemplatesFromLibraries();
        renderAssetManager(); return;
    }
    if(event.target.closest?.('[data-manager-prompt-delete]')){
        if(!managerSelectedPromptIds.size) return;
        const data = await fetch('/api/prompt-libraries/items/delete', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ids:[...managerSelectedPromptIds]})}).then(r => r.json());
        canvasPromptLibraries = data.library?.libraries || canvasPromptLibraries;
        managerSelectedPromptIds.clear();
        refreshCanvasPromptTemplatesFromLibraries();
        renderAssetManager(); return;
    }
}, true);


function wouldCreateGeneratorCycle(fromId, toId){
    const seen = new Set();
    const walk = id => {
        if(id === fromId) return true;
        if(seen.has(id)) return false;
        seen.add(id);
        for(const c of connections.filter(x => x.from === id)){
            if(walk(c.to)) return true;
            const next = nodes.find(n => n.id === c.to);
            if(next?.type === 'output'){
                for(const cc of connections.filter(x => x.from === next.id)){
                    if(walk(cc.to)) return true;
                }
            }
        }
        return false;
    };
    return walk(toId);
}
function canConnect(fromId, toId){
    if(!fromId || !toId || fromId === toId) return false;
    const from = nodes.find(n => n.id === fromId);
    const to = nodes.find(n => n.id === toId);
    if(!from || !to) return false;
    if(CANVAS_GENERATOR_TYPES.includes(from.type)){
        if(to.type === 'output') return true;
        if(to.type === 'image' && CANVAS_IMAGE_OUTPUT_TYPES.includes(from.type)) return true;
        if(CANVAS_MEDIA_OUTPUT_TYPES.includes(from.type) && CANVAS_GENERATOR_TYPES.includes(to.type)){
            return !wouldCreateGeneratorCycle(fromId, toId);
        }
        return false;
    }
    if(to.type === 'loop'){
        const allowImage = Boolean(to.imageInput) && ['image','group','output'].includes(from.type);
        const allowPrompt = Boolean(to.showPrompt) && ['prompt','promptGroup','loop','llm'].includes(from.type);
        return allowImage || allowPrompt;
    }
    if(to.type === 'llm') return ['prompt','loop','promptGroup','llm','image','group','output'].includes(from.type);
    if(from.type === 'llm') return CANVAS_GENERATOR_TYPES.includes(to.type);
    return CANVAS_GENERATOR_TYPES.includes(to.type) && ['image','prompt','loop','group','promptGroup','output','llm'].includes(from.type);
}
function sanitizeConnections(){
    connections = (connections || []).filter(c => canConnect(c.from, c.to));
}


function escapeHtml(str){ return String(str == null ? '' : str).replace(/[&<>"']/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s])); }
function escapeAttr(str){ return escapeHtml(str); }

// ===== 画布导出 / 导入（带格式版本信封；后端 /api/canvases/{id}/export 与 /api/canvases/import）=====
// 导出文件结构：{app:"myridtv", version, exportedAt, source, media, canvas}
// 导入永远新建一张画布（不覆盖已有），并回报"有多少媒体在本机找不到"。
async function exportCanvasToFile(canvasId){
    if(!canvasId){ alert(tr('canvas.exportFailed')); return; }
    try{
        const res = await fetch(`/api/canvases/${encodeURIComponent(canvasId)}/export`, { cache:'no-store' });
        if(!res.ok) throw new Error(`HTTP ${res.status}`);
        const payload = await res.json();
        const blob = new Blob([JSON.stringify(payload, null, 2)], {type:'application/json'});
        const link = document.createElement('a');
        const href = URL.createObjectURL(blob);
        link.href = href;
        const title = String((payload && payload.canvas && payload.canvas.title) || canvasId).replace(/[\\/:*?"<>|]/g, '_').slice(0, 48);
        link.download = `${title}.myridtv-canvas.json`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(href), 2000);
        const mediaCount = Number((payload && payload.media && payload.media.count) || 0);
        setStatus(trf('canvas.exportDone', {n: mediaCount}));
    }catch(e){
        console.error(e);
        alert(tr('canvas.exportFailed'));
    }
}

async function importCanvasPayload(payload){
    const res = await fetch('/api/canvases/import', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify(payload || {})
    });
    const data = await res.json().catch(() => ({}));
    if(!res.ok || data.ok === false) throw new Error(data.detail || tr('canvas.importFailed'));
    return data;
}

async function importCanvasFromFile(file){
    if(!file) return;
    try{
        const text = await file.text();
        let payload;
        try{ payload = JSON.parse(text); }
        catch(_){ throw new Error(tr('canvas.importInvalid')); }
        const data = await importCanvasPayload(payload);
        const media = (data && data.media) || {};
        const total = Number(media.count || 0);
        const missing = Number(media.missingCount || 0);
        await loadCanvasList(false);
        if(missing > 0){
            setStatus(trf('canvas.importDoneMissing', {total, missing}));
            alert(trf('canvas.importMissingAlert', {missing}));
        } else {
            setStatus(trf('canvas.importDone', {total}));
        }
        return data;
    }catch(e){
        console.error(e);
        alert(e.message || tr('canvas.importFailed'));
    }
}

function initCanvasImportEntry(){
    const btn = document.getElementById('gateImportBtn');
    const input = document.getElementById('gateImportFile');
    if(!btn || !input) return;
    btn.onclick = e => { e.stopPropagation(); input.value = ''; input.click(); };
    input.onchange = () => { const picked = input.files && input.files[0]; importCanvasFromFile(picked); };
}


window.onload = async () => {
    applyTheme(window.StudioTheme?.get?.() || 'dark');
    if(window.StudioI18n) StudioI18n.apply();
    document.title = tr('canvas.title');
    await loadConfig();
    pruneMissingComfyWorkflows();
    await loadCanvasList(false);
    initCanvasImportEntry();
    setCanvasMode(false);
};



/* ===== 2026-09-16：旧画布（board）已移除 =====
   以下函数原本负责旧画布节点图与画布内嵌面板的渲染，
   已随 board 一并删除；保留空实现以兼容仍可能被调用的残留代码路径。 */
function render(){}
function renderNode(){}
function applyViewport(){}
function renderCanvasAssetLibrary(){}
function renderCanvasPromptLibrarySelect(){}

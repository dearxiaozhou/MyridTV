// ===== 前端错误上报(诊断用):任何 JS 异常/未处理 rejection 都会 POST 到后端日志 =====
(function(){
    function report(payload){
        try{
            fetch('/api/frontend-log', {
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({t:Date.now(), kind:payload.kind, msg:String(payload.msg||'').slice(0,500), stack:String(payload.stack||'').slice(0,1200), url:location.href.slice(0,300)})
            }).catch(function(){});
        }catch(_){}
    }
    window.addEventListener('error', function(ev){
        report({kind:'error', msg:ev.message, stack:ev.error && ev.error.stack});
    }, true);
    window.addEventListener('unhandledrejection', function(ev){
        var r = ev.reason;
        report({kind:'rejection', msg:(r && r.message) || String(r), stack:(r && r.stack) || ''});
    }, true);
})();
const params = new URLSearchParams(location.search);
const canvasId = params.get('id') || '';
const initialAgentSessionId = params.get('agent_session') || '';
const shell = document.getElementById('shell');
const world = document.getElementById('world');
const composer = document.getElementById('composer');
const createMenu = document.getElementById('createMenu');
const promptInput = document.getElementById('promptInput');
const mentionPicker = document.getElementById('mentionPicker');
const mentionPreview = document.getElementById('mentionPreview');
const engineSelect = document.getElementById('engineSelect');
const dynamicParams = document.getElementById('dynamicParams');
const composerReferenceModeSlot = document.getElementById('composerReferenceModeSlot');
const composerStyleModeSlot = document.getElementById('composerStyleModeSlot');
// 2026-09-25：槽会被搬进 #dynamicParams，而下轮渲染 innerHTML= 会把它连节点冲掉——
// 记下原归属容器，renderDynamicParams 开头先归位避毁，末尾再统一搬回参数排。
const composerSlotHomes = new Map();
[composerReferenceModeSlot, composerStyleModeSlot].forEach(s => { if(s?.parentElement) composerSlotHomes.set(s, s.parentElement); });
const runBtn = document.getElementById('runBtn');
const cascadeRunBtn = null; // ComfyUI 生成节点不显示“一键运行”
const fileInput = document.getElementById('fileInput');
const apiKindToggle = document.getElementById('apiKindToggle');
const inputThumbsRow = document.getElementById('inputThumbsRow');
const inputPromptPreview = document.getElementById('inputPromptPreview');
const minimap = document.getElementById('minimap');
const minimapContent = document.getElementById('minimapContent');
const minimapToggle = document.getElementById('minimapToggle');
const imageEditModal = document.getElementById('imageEditModal');
const smartLogModal = document.getElementById('smartLogModal');
const smartLogList = document.getElementById('smartLogList');
const smartShortcutModal = document.getElementById('smartShortcutModal');
const selectionBox = document.getElementById('selectionBox');
const canvasAddToggle = document.getElementById('canvasAddToggle');
const assetToggle = document.getElementById('assetToggle');
const styleToggle = document.getElementById('styleToggle');

// Canvas header bar (back button + title dropdown)
const canvasTitleDropdown = document.getElementById('canvasTitleDropdown');
const canvasTitleText = document.getElementById('canvasTitleText');
const canvasTitleInput = document.getElementById('canvasTitleInput');
const canvasListDropdown = document.getElementById('canvasListDropdown');
const canvasListDropdownItems = document.getElementById('canvasListDropdownItems');
const canvasDropdownSearch = document.getElementById('canvasDropdownSearch');
const assetPanel = document.getElementById('assetPanel');
const assetCloseBtn = document.getElementById('assetCloseBtn');
const stylePanel = document.getElementById('stylePanel');
const styleCloseBtn = document.getElementById('styleCloseBtn');
const assetLibrarySelect = document.getElementById('assetLibrarySelect');
const assetCategorySelect = document.getElementById('assetCategorySelect');
const assetGrid = document.getElementById('assetGrid');
const assetDropZone = document.getElementById('assetDropZone');
const SMART_CANVAS_ACTIONS = window.WcsSmartCanvasActions || null;
const assetImageControls = document.getElementById('assetImageControls');
const assetDialogBackdrop = document.getElementById('assetDialogBackdrop');
const assetDialogTitle = document.getElementById('assetDialogTitle');
const assetDialogInput = document.getElementById('assetDialogInput');
const assetDialogCancel = document.getElementById('assetDialogCancel');
const assetDialogOk = document.getElementById('assetDialogOk');
const assetHoverPreview = document.getElementById('assetHoverPreview');
const canvasAgentToggle = document.getElementById('canvasAgentToggle');
const canvasAgentPanel = document.getElementById('canvasAgentPanel');
const canvasAgentClose = document.getElementById('canvasAgentClose');
const canvasAgentNewChat = document.getElementById('canvasAgentNewChat');
const canvasAgentHistoryToggle = document.getElementById('canvasAgentHistoryToggle');
const canvasAgentHistoryPanel = document.getElementById('canvasAgentHistoryPanel');
const canvasAgentMessages = document.getElementById('canvasAgentMessages');
const canvasAgentWelcomeTemplate = canvasAgentMessages?.querySelector('.canvas-agent-welcome')?.outerHTML || '';
const canvasAgentRefs = document.getElementById('canvasAgentRefs');
const canvasAgentAttach = document.getElementById('canvasAgentAttach');
const canvasAgentUpload = document.getElementById('canvasAgentUpload');
const canvasAgentFileInput = document.getElementById('canvasAgentFileInput');
const canvasAgentInput = document.getElementById('canvasAgentInput');
let canvasAgentEditingId = '';
const canvasAgentSend = document.getElementById('canvasAgentSend');
const canvasAgentBrainstormBtn = document.getElementById('canvasAgentBrainstorm');
const promptPresetPanel = document.getElementById('promptPresetPanel');
const promptPresetClose = document.getElementById('promptPresetClose');
const promptPresetStatus = document.getElementById('promptPresetStatus');
const promptPresetSelect = document.getElementById('promptPresetSelect');
const promptPresetName = document.getElementById('promptPresetName');
const promptPresetText = document.getElementById('promptPresetText');
const promptPresetApply = document.getElementById('promptPresetApply');
const promptPresetDelete = document.getElementById('promptPresetDelete');
const promptPresetNew = document.getElementById('promptPresetNew');
const promptPresetSave = document.getElementById('promptPresetSave');
const promptTemplatePanel = document.getElementById('promptTemplatePanel');
const promptTemplateClose = document.getElementById('promptTemplateClose');
const promptTemplateSearch = document.getElementById('promptTemplateSearch');
const promptTemplateLibrarySelect = document.getElementById('promptTemplateLibrarySelect');
const promptTemplateCats = document.getElementById('promptTemplateCats');
const promptTemplateBody = document.getElementById('promptTemplateBody');
const composerTemplateBtn = document.getElementById('composerTemplateBtn');
function installAudioThumbCleanup(){
    const styleId = 'smart-audio-thumb-cleanup-style';
    if(!document.getElementById(styleId)){
        const style = document.createElement('style');
        style.id = styleId;
        style.textContent = `
audio,
.audio-thumb-base,
.audio-thumb-base *,
.audio-thumb-base-pill,
.audio-thumb-base-cut {
    display:none !important;
    width:0 !important;
    height:0 !important;
    min-width:0 !important;
    min-height:0 !important;
    opacity:0 !important;
    pointer-events:none !important;
}
`;
        document.head.appendChild(style);
    }
    const cleanup = root => {
        // Keep custom audio players alive; only remove the obsolete native-thumb fragments.
        (root || document).querySelectorAll?.('.audio-thumb-base,.audio-thumb-base-pill,.audio-thumb-base-cut').forEach(el => el.remove());
    };
    cleanup(document);
    if(!window.__smartAudioThumbCleanupObserver){
        window.__smartAudioThumbCleanupObserver = new MutationObserver(records => {
            for(const record of records){
                record.addedNodes?.forEach(node => {
                    if(node?.nodeType === 1) cleanup(node);
                });
            }
        });
        window.__smartAudioThumbCleanupObserver.observe(document.documentElement, {childList:true, subtree:true});
    }
}
installAudioThumbCleanup();
let canvas = null;
let nodes = [];
// ============ 节点单一写入口（nodeStore）============
// 所有"新增节点"必须经由 addNode/addNodes；所有"删除节点"必须经由 removeNode/removeNodes。
// 这是前端对后端 Artifact Gate 的呼应：集中补 provenance 标记(__origin/role/status)、做 artifactId 去重、统一操作 nodes 数组。
// 严禁在 nodeStore 之外直接 nodes.push(新建节点) 或 nodes = nodes.filter(删除节点)。
// 节点生命周期状态机（status 字段，Phase 2 落地、Phase 6 渲染层消费）：
//   draft   : 草稿/尚未授权（预留，目前不主动产生）
//   pending : 已授权、待生成。Agent 建的生成节点 images=[] 即此态；用户手动生成节点未跑也可是此态
//   ready   : 已落定。生成节点回填图 / 文本节点写好 / 导入节点加载完毕
//   failed  : 生成或回填异常（后端 attach_result 异常时置；渲染层红色告警）
// 转换：新建 generation 节点 -> pending；attach_result 成功回填图 -> ready；异常 -> failed。
//   text/import 类节点默认 ready。status 一旦 ready/failed 不回退 pending，除非用户显式重跑该节点。
// role 字段：user(用户手动) / generation(生成) / text(文本/提示词/脚本) / container(组) / output(产物)；仅作视觉/审计标识。
// 自检：grep -nE 'nodes\.(push|splice)\(|nodes = nodes\.filter\(' _internal/static/js/smart-canvas.js
//   合法命中仅应出现在下方 nodeStore IIFE 定义块内。
const nodeStore = (function(){
    function inferRole(node){
        if(node.role) return node.role;
        if(node.type === 'smart-group' || node.isHistoryGroup) return 'container';
        if(node.type === 'smart-image') return (node.runPrompt || (node.images && node.images.length === 0 && node.pending)) ? 'generation' : 'media';
        if(node.type === 'smart-prompt' || node.type === 'smart-loop') return 'text';
        return 'media';
    }
    function inferStatus(node){
        if(node.status) return node.status;
        if(node.images && node.images.length) return 'ready';
        if(node.pending) return 'pending';
        return 'ready';
    }
    function addNode(node, origin){
        if(!node || typeof node !== 'object') return null;
        if(node.__preview){ nodes.push(node); return node; }
        if(origin) node.__origin = origin;
        if(!node.role) node.role = inferRole(node);
        if(!node.status) node.status = inferStatus(node);
        if(!node.artifactId) node.artifactId = node.id; // Phase 5：兜底 artifactId，激活 nodeStore 去重守卫（id 唯一，稳定幂等）
        if(node.artifactId && nodes.some(function(n){ return n.id !== node.id && n.artifactId === node.artifactId; })){
            console.warn('[NodeDupSkipped] artifactId=' + node.artifactId);
            return nodes.find(function(n){ return n.artifactId === node.artifactId; });
        }
        nodes.push(node);
        return node;
    }
    function addNodes(list, origin){ (list || []).forEach(function(n){ addNode(n, origin); }); return list; }
    // ---- Phase 4 删除墓碑 ----
    // 没有墓碑，mergeSmartNodeLists 的 "仅本地存在就保留" 会把对方已删的节点复活。
    // 墓碑写在 canvas.deleted:[{id,at,by}]，随保存回写后端，多端合并时双向剔除。
    const TOMBSTONE_LIMIT = 500;
    function tombstoneList(){
        if(!canvas) return [];
        if(!Array.isArray(canvas.deleted)) canvas.deleted = [];
        return canvas.deleted;
    }
    function tombstone(ids){
        if(!canvas) return;
        const list = tombstoneList();
        const known = new Set(list.map(function(t){ return t && t.id; }));
        const at = Date.now();
        let by = 'local';
        try { by = smartClientId || 'local'; } catch(e) { by = 'local'; }
        (ids || []).forEach(function(id){
            if(!id || known.has(id)) return;
            known.add(id);
            list.push({id: id, at: at, by: by});
        });
        // 上限保护：只留最近 TOMBSTONE_LIMIT 条，避免画布文件无限膨胀。
        if(list.length > TOMBSTONE_LIMIT) canvas.deleted = list.slice(list.length - TOMBSTONE_LIMIT);
    }
    // 撤销恢复节点时必须消掉墓碑，否则保存会被墓碑过滤再杀一次。
    function untombstone(ids){
        if(!canvas || !Array.isArray(canvas.deleted) || !canvas.deleted.length) return;
        const revive = new Set((ids || []).filter(Boolean));
        if(!revive.size) return;
        canvas.deleted = canvas.deleted.filter(function(t){ return !(t && revive.has(t.id)); });
    }
    function deletedIds(canvasLike){
        const src = (canvasLike && Array.isArray(canvasLike.deleted)) ? canvasLike.deleted : [];
        return new Set(src.map(function(t){ return t && t.id; }).filter(Boolean));
    }
    function removeNode(id, options={}){
        if(!id) return false;
        if(!nodes.some(function(n){ return n.id === id; })) return false;
        nodes = nodes.filter(function(n){ return n.id !== id; });
        tombstone([id]);
        if(options.render !== false) render();
        if(options.save !== false) scheduleSave();
        return true;
    }
    function removeNodes(ids, options={}){
        const set = new Set(ids || []);
        if(!set.size) return false;
        const hit = nodes.filter(function(n){ return set.has(n.id); }).map(function(n){ return n.id; });
        nodes = nodes.filter(function(n){ return !set.has(n.id); });
        tombstone(hit);
        if(options.render !== false) render();
        if(options.save !== false) scheduleSave();
        return true;
    }
    return { addNode: addNode, addNodes: addNodes, removeNode: removeNode, removeNodes: removeNodes,
             tombstone: tombstone, untombstone: untombstone, deletedIds: deletedIds };
})();

const canvasUiState = CanvasUiState.create();
canvasUiState.installLegacyAliases(globalThis);
let frontNodeIds = [];
let dragState = null;
let loopInsertPreview = null;
/* 拖拽吸附开关（左下角「吸附」按钮，2026-10-05）。默认开：对齐是画布高频操作，
   默认关等于没做。状态存 localStorage，与 minimapToggle 同一族 key 命名。 */
const SMART_CANVAS_SNAP_KEY = 'smart_canvas_snap_enabled';
let snapEnabled = true;
try { snapEnabled = localStorage.getItem(SMART_CANVAS_SNAP_KEY) !== '0'; } catch(_) {}
/* 当前正在显示的对齐辅助线（[{axis:'x'|'y', at, from, to}]，坐标是世界坐标）。 */
let snapGuides = [];
let selectionState = null;
let isRKeyDown = false;
let selectionJustFinished = false;
let resizeState = null;
let thumbDragState = null;
let inputThumbDragState = null;
let uploadTargetId = '';
let pendingGroupUploadPoint = null;
let mentionRange = null;
let panState = null;
// didPan 已收编进 CanvasInteractionMachine 粘滞表 'gesture:pan'（第7步）
let portDragState = null;
let connectionCutState = null;
// 划断手势用的连线几何缓存：connIndex -> {c:[p0x,p0y,c1x,c1y,c2x,c2y,p1x,p1y], pts, box}
// renderConnections 每次重渲时清空并重新填充（只存 8 个数，折线采样按需懒算）。
const connCutGeom = new Map();
const CONN_CUT_TRAIL_MAX_POINTS = 900;
let saveTimer = null;
const canvasSaveRecovery = window.CanvasSaveRecoveryController.create();
const canvasMediaPresentation = window.CanvasMediaPresentationController.create({
    mediaKindForItem: image => mediaKindForItem(image)
});
const fileNameFromUrl = url => canvasMediaPresentation.fileNameFromUrl(url);
let apiProviders = [];
const PROVIDER_MODEL_DISPLAY = window.WcsProviderModelDisplay || null;
let comfyWorkflows = [];
let comfyInstanceCount = 1;
let assetLibrary = {categories:[]};
let assetLibraryOpen = false;
let assetTab = 'image';
let activeAssetCategoryId = '';
let activeAssetLibraryId = '';
let mentionSource = 'input';
let mentionAssetCategoryId = '';
let assetLibraryUpdatedAt = 0;
let assetLibraryRefreshTimer = null;
let canvasAgentOpen = false;
let canvasAgentSending = false;
let canvasAgentAbortController = null;
let canvasAgentActiveRequestId = null;
let canvasAgentToggleDragState = null;
let canvasAgentToggleSuppressClickUntil = 0;
let canvasAgentRefsState = [];
let canvasAgentMessagesState = [];
let canvasAgentLastReply = '';
let canvasAgentLastReplyRefs = [];
let canvasAgentMentionIndex = -1;
let canvasAgentSessionId = uid('agent_session');
let canvasAgentHistoryOpen = false;
let canvasAgentSettingsOpen = false;
let canvasAgentModelPreset = null;
let canvasAgentBrainstormState = null;
let canvasAgentPendingChosenId = '';
let canvasAgentChosenMap = {};
/* —— 多 Agent（Myrid-Agent 等）支持 —— */
let canvasAgentActiveId = 'codex';
let canvasAgentConfigAgents = null;
const CANVAS_AGENT_FALLBACK_AGENTS = {
    codex: {name:'Myrid-Agent', provider_id:'', model:'', upstream_base_url:'', api_key_env:'MYRIDTV_AGENT_API_KEY', chat_models:['deepseek-chat', 'deepseek-reasoner', 'deepseek-v4-flash']}
};
function canvasAgentRegistry(){
    const agents = canvasAgentConfigAgents?.agents;
    return agents && typeof agents === 'object' ? agents : CANVAS_AGENT_FALLBACK_AGENTS;
}
function canvasAgentEntry(id){
    return canvasAgentRegistry()[String(id || '')] || {};
}
function canvasAgentActiveEntry(){
    const id = canvasAgentActiveId || canvasAgentConfigAgents?.active_id || 'codex';
    return canvasAgentEntry(id);
}
function canvasAgentDisplayName(entryOrName, fallback='Myrid-Agent'){
    if(typeof entryOrName === 'string') return entryOrName || fallback;
    return entryOrName?.name || fallback;
}
function canvasAgentRoleName(entryOrName, fallback='Myrid-Agent'){
    const name = canvasAgentDisplayName(entryOrName, fallback);
    return /\bagent\b/i.test(name) ? name : `${name} Agent`;
}
function canvasAgentConfiguredChatModel(entry=canvasAgentActiveEntry(), provider=null){
    const configured = String(entry?.model || '').trim();
    const models = [...new Set((provider?.chat_models || entry?.chat_models || []).filter(Boolean))];
    return configured || models[0] || configuredAgentFallbackModel();
}
async function refreshCanvasAgentConfig(){
    try {
        const res = await fetch(`${RH_OFFICIAL_PROXY_BASE}/api/canvas-agent-config?v=${Date.now()}`, {cache:'no-store'});
        if(!res.ok) return;
        const data = await res.json();
        if(data && data.agents && typeof data.agents === 'object' && data.agents.agents){
            canvasAgentConfigAgents = data.agents;
            if(data.agents.active_id && canvasAgentRegistry()[data.agents.active_id]) canvasAgentActiveId = data.agents.active_id;
            const titleEl = document.querySelector('.canvas-agent-title');
            const entry = canvasAgentEntry(canvasAgentActiveId) || {};
            if(titleEl) canvasAgentRefreshHeadTitle();
            if(canvasAgentSettingsOpen) renderCanvasAgentSettingsPanel();
        }
    } catch(_) {}
}
const CANVAS_AGENT_PRESET_KEY = 'smart_canvas_agent_model_preset_v1';
const CANVAS_AGENT_PRESET_DEFAULTS = {
    chatProviderId: '',
    chatModel: '',
    genProviderId: 'runninghub',
    genModel: '',
    // 资产规范死规矩：默认 16:9(wide)+4k => SIZE_MAP.wide.4k = 3840x2160；旧值 landscape43/2k 会出 4:3/2048 系列，必错
    ratio: 'wide',
    resolution: '4k',
    quality: 'medium',
    gen2ProviderId: 'runninghub',
    gen2Model: '',
    gen2Ratio: 'wide',
    gen2Resolution: '4k',
    gen2Quality: 'medium'
};
function canvasAgentLoadPreset(){
    try{
        const raw = localStorage.getItem(CANVAS_AGENT_PRESET_KEY);
        const parsed = raw ? JSON.parse(raw) : {};
        return Object.assign({}, CANVAS_AGENT_PRESET_DEFAULTS, parsed || {});
    }catch(_){ return Object.assign({}, CANVAS_AGENT_PRESET_DEFAULTS); }
}
function canvasAgentSavePreset(){
    try{ localStorage.setItem(CANVAS_AGENT_PRESET_KEY, JSON.stringify(canvasAgentModelPreset || {})); }catch(_){}
}
const CANVAS_AGENT_HISTORY_KEY = `smart_canvas_agent_history_${canvasId || 'default'}_v1`;
const CANVAS_AGENT_HISTORY_KEY_PREFIX = 'smart_canvas_agent_history_';
const CANVAS_AGENT_HISTORY_KEY_SUFFIX = '_v1';
const CANVAS_AGENT_TOGGLE_POS_KEY = 'smart_canvas_agent_toggle_pos_v1';
let canvasAgentQuoteState = null;
let promptPresets = [];
let builtinPromptTemplates = [];
let promptLibraries = [];
let activePromptLibraryId = 'system';
let promptTemplateGroups = [];
let promptTemplateOverrides = {hiddenBuiltinIds:[], editedBuiltins:{}};
let promptTemplateCategory = 'all';
let promptTemplateSelectedId = '';
let promptTemplateEditing = false;
let promptTemplateGroupEditMode = false;
let promptTemplateRefreshTimer = null;
let createMenuPoint = {x:0, y:0};
// 拖线落空后挂起的"连线意图"：等用户在 createMenu 里选节点类型，再建节点 + 连线。
// null 表示当前没有挂起的意图（菜单走的是普通"新建节点"路径）。
let pendingPortDrop = null;
let imageClickTimer = null;
let suppressImageClickUntil = 0;
let lastMouseWorld = null;
let lastConfigRefreshAt = 0;
let connectionRenderFrame = 0;
let imageMeasureRenderFrame = 0;
let smartCascadeRunning = false;
let smartCascadeActiveLoopId = '';
let smartCascadeStopRequested = false;
let smartCascadeSilentSelection = false;
let smartCascadeRunPath = null;
function normalizeComfyWorkflowEntries(list){
    return CanvasComfyJobEngine.normalizeComfyWorkflowEntries(list);
}
function resolveComfyWorkflowName(name){
    return CanvasComfyJobEngine.resolveComfyWorkflowName(name);
}
function loadLocalComfyWorkflowRegistry(){
    return CanvasComfyJobEngine.loadLocalComfyWorkflowRegistry();
}
function saveLocalComfyWorkflowRegistry(list){
    CanvasComfyJobEngine.saveLocalComfyWorkflowRegistry(list);
}
function mergeKnownComfyWorkflows(primary=[], fallback=[]){
    return CanvasComfyJobEngine.mergeKnownComfyWorkflows(primary, fallback);
}
function updateKnownComfyWorkflows(primary=[]){
    return CanvasComfyJobEngine.updateKnownComfyWorkflows(primary);
}
function replaceKnownComfyWorkflows(primary=[]){
    return CanvasComfyJobEngine.replaceKnownComfyWorkflows(primary);
}
async function filterAccessibleComfyWorkflows(list=[]){
    return CanvasComfyJobEngine.filterAccessibleComfyWorkflows(list);
}
const smartCascadeRuns = new Map();
let smartLoopContext = null;
let transientSmartCloudLinks = [];
let runBtnCooldownToken = 0;
let smartRunStateToken = 0;
const activeSmartTaskPolls = new Map();
const smartNodeRunTokens = new Map();
let smartRhRandomValues = {};
let lastImagePasteAt = 0;
let lastNodePasteAt = 0;
// suppressNodeClickUntil 已收编进 CanvasInteractionMachine 粘滞表 'gesture:node-click'（第7步）
let textSelectionGuard = null;
let undoSuppressed = false;
let deleteShortcutHandledAt = 0;
let runningHubWorkflowCache = {};
const smartTextContentCache = new Map();
function activeSmartCascadeCount(){ return smartCascadeRuns.size; }
function smartCascadeRunForLoop(loopId){ return loopId ? smartCascadeRuns.get(loopId) || null : null; }
function smartCascadeIsLoopRunning(loopId){ return Boolean(smartCascadeRunForLoop(loopId)); }
function syncSmartCascadeLegacyState(preferredLoopId=''){
    const activeIds = [...smartCascadeRuns.keys()];
    smartCascadeRunning = activeIds.length > 0;
    smartCascadeActiveLoopId = preferredLoopId && smartCascadeRuns.has(preferredLoopId)
        ? preferredLoopId
        : (activeIds[0] || '');
    const activeRun = smartCascadeActiveLoopId ? smartCascadeRuns.get(smartCascadeActiveLoopId) : null;
    smartCascadeStopRequested = Boolean(activeRun?.stopRequested);
    smartCascadeRunPath = activeRun?.runPath || null;
}
function smartCascadeAnyRunning(){ return smartCascadeRunning || activeSmartCascadeCount() > 0; }
function smartCascadeEdgeState(edgeKey){
    for(const run of smartCascadeRuns.values()){
        const state = run?.runPath?.states?.[edgeKey];
        if(state) return state;
    }
    return smartCascadeRunPath?.states?.[edgeKey] || '';
}
function smartCascadePathForCtx(ctx=null){
    return ctx?.runState?.runPath || ctx?.runPath || smartCascadeRunPath;
}
function capturePendingUndo(){ return CanvasUndoController.capturePending(); }
function commitPendingUndo(){ return CanvasUndoController.commitPending(); }
function discardPendingUndo(){ return CanvasUndoController.discardPending(); }
function snapshotForUndo(){ return CanvasUndoController.snapshot(); }
function pushUndo(){ return CanvasUndoController.push(); }
function performUndo(){ return CanvasUndoController.undo(); }
const comfyWorkflowCache = CanvasComfyJobEngine.cache;  // 权威缓存在任务引擎模块
let cropState = null;
let cropDrag = null;
let imageEditMode = 'crop';
let imageEditModeTouched = false;
let previewPanDrag = null;
let previewCompareDrag = false;
let previewComparePos = 50;
let imageEditPanDrag = null;
let previewNavState = {nodeId:'', index:0, count:0};
const PANORAMA_RATIO_PRESETS = {
    square:{w:1, h:1},
    portrait:{w:2, h:3},
    landscape:{w:3, h:2},
    portrait43:{w:3, h:4},
    landscape43:{w:4, h:3},
    story:{w:9, h:16},
    wide:{w:16, h:9},
    ultrawide:{w:21, h:9},
    ultratall:{w:9, h:21}
};
let panoramaState = {
    enabled:false,
    ratio:'wide',
    customW:16,
    customH:9,
    fov:75,
    yaw:0,
    pitch:0,
    drag:null
};
let settings = {
    engine:'api',
    apiKind:'image',
    provider_id:'',
    model:'',
    ratio:'square',
    resolution:'1k',
    customRatio:'',
    customRatioWidth:'',
    customRatioHeight:'',
    customSize:'',
    customWidth:'',
    customHeight:'',
    quality:'auto',
    count:1,
    videoProvider:'',
    videoModel:'',
    videoDuration:5,
    videoAspect:'16:9',
    videoResolution:'',
    videoEnhancePrompt:false,
    videoEnableUpsample:false,
    videoWatermark:false,
    videoCameraFixed:false,
    videoGenerateAudio:false,
    videoMultimodal:false,
    videoUseFrameRoles:false,
    videoReferenceMode:'mixed',
    videoExtendMode:'after',
    videoTrustedAsset:false,
    videoTrustedSource:'library',
    videoTempShLinks:[],
 comfyMode:'custom',
    comfyWorkflow:'',
    comfyParams:{},
    comfyModes:{},
    rhConfigKey:'',
    rhPayment:'free',
    rhInstanceType:'',
    rhParams:{},
    rhRandomActive:{},
    rhNodeOff:{},
    width:1024,
    height:1024,
    enhanceStrength:0.5,
    enhanceUpscale:false,
    enhanceUpscaleRes:2048,
    editUpscale:false,
    editUpscaleRes:2048,
    promptH:93
};
const APP_RUNTIME_CONFIG_DEFAULTS = {
    proxy:{base_url:(typeof location!=='undefined'&&location.origin?location.origin:'http://127.0.0.1:3107')},
    agent:{provider_id:'', model:'', preferred_model_pattern:''}
};
let appRuntimeConfig = APP_RUNTIME_CONFIG_DEFAULTS;
let appRuntimeConfigLoaded = false;
let RH_OFFICIAL_PROXY_BASE = APP_RUNTIME_CONFIG_DEFAULTS.proxy.base_url;
// Read-only registry: transient UI snapshots come from their dedicated owner;
// canvas content, providers and task domains retain their existing getters.
if(globalThis.CanvasStateHub){CanvasStateHub.configure({
        nodes: () => nodes,
        settings: () => settings,
        canvas: () => canvas,
        canvasId: () => canvasId,
        ui: () => canvasUiState.snapshot(),
        selectedId: () => canvasUiState.selection.primaryId,
        selectedIds: () => canvasUiState.selection.ids,
        selectedImage: () => canvasUiState.selection.image,
        apiProviders: () => apiProviders,
        runningHubWorkflowCache: () => runningHubWorkflowCache,
        comfyWorkflows: () => comfyWorkflows,
        smartRhRandomValues: () => smartRhRandomValues,
        world: () => world
});}
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
function canvasAgentConfig(){
    return appRuntimeConfig?.agent || APP_RUNTIME_CONFIG_DEFAULTS.agent;
}
function configuredAgentProviderId(){
    const entry = (typeof canvasAgentActiveEntry === 'function') ? canvasAgentActiveEntry() : null;
    return String(entry?.provider_id || canvasAgentConfig().provider_id || APP_RUNTIME_CONFIG_DEFAULTS.agent.provider_id).trim();
}
function configuredAgentFallbackModel(){
    const entry = (typeof canvasAgentActiveEntry === 'function') ? canvasAgentActiveEntry() : null;
    return String(entry?.model || canvasAgentConfig().model || APP_RUNTIME_CONFIG_DEFAULTS.agent.model).trim();
}
function configuredAgentModelPattern(){
    const pattern = String(canvasAgentConfig().preferred_model_pattern || APP_RUNTIME_CONFIG_DEFAULTS.agent.preferred_model_pattern || '').trim();
    if(!pattern) return null;
    try {
        return new RegExp(pattern, 'i');
    } catch(_) {
        return null;
    }
}
const SIZE_MAP = {
    square: {'1k':'1024x1024','2k':'2048x2048','4k':'4096x4096'},
    landscape: {'1k':'1536x1024','2k':'2048x1360','4k':'3520x2336'},
    portrait: {'1k':'1024x1536','2k':'1360x2048','4k':'2336x3520'},
    landscape43: {'1k':'1024x768','2k':'2048x1536','4k':'3312x2480'},
    portrait43: {'1k':'768x1024','2k':'1536x2048','4k':'2480x3312'},
    wide: {'1k':'1536x864','2k':'2048x1152','4k':'3840x2160'},
    story: {'1k':'864x1536','2k':'1152x2048','4k':'2160x3840'},
    ultrawide: {'1k':'1536x656','2k':'2048x880','4k':'3840x1648'},
    ultratall: {'1k':'656x1536','2k':'880x2048','4k':'1648x3840'}
};
const RES_LONG_SIDE = { '1k':1024, '2k':2048, '4k':3840 };
const RES_PIXEL_LIMIT = { '1k':2359296, '2k':4194304, '4k':8294400 };
function tr(key){ return window.StudioI18n?.t ? window.StudioI18n.t(key) : key; }
function trf(key, values={}){
    return Object.entries(values).reduce((text, [name, value]) => text.replaceAll(`{${name}}`, String(value)), tr(key));
}
function refreshIcons(){ if(window.lucide) lucide.createIcons(); }
function uid(prefix){ return `${prefix}_${Math.random().toString(36).slice(2, 10)}${Date.now().toString(36).slice(-4)}`; }
function escapeHtml(str){ return String(str == null ? '' : str).replace(/[&<>"']/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s])); }
const escapeAttr = escapeHtml;
function cloneSmartSettings(source=settings){
    try {
        return JSON.parse(JSON.stringify(source || {}));
    } catch(e) {
        return {...(source || {})};
    }
}
function settingsForStorage(source=settings){
 const clean = cloneSmartSettings(source);
 if(clean.engine === 'comfy') normalizeComfyWorkflowSelection(clean);
 clean.videoReferenceMode = videoReferenceModeValue(clean);
 if(clean.videoTrustedAsset !== undefined) clean.videoTrustedAsset = clean.videoTrustedAsset === true;
 if(!['library','cloud','manual'].includes(clean.videoTrustedSource)) clean.videoTrustedSource = 'library';
 clean.videoTempShLinks = (clean.videoTempShLinks || []).filter(item => item?.manual === true);
 return clean;
}
function isApiLikeEngine(engine){
    return ['api', 'volcengine'].includes(String(engine || '').toLowerCase());
}
// ===== 工作流类引擎（2026-10-05 老王定调）=====
// 「工作流类」= 本地 ComfyUI + 云端 RunningHub(RH)。两者都是提交一整个工作流去跑，
// 节点侧走 comfyStatus/comfyProgress 进度环（RH 无精确百分比，用 comfyIndeterminate 走整圈流光），
// 按钮侧统一红态（is-running/is-stop）。
// 其余一切（api / volcengine / blender 3D预演）都不是工作流类 → 蓝色波纹 is-ap-running。
// ⚠️ 口径必须与 canvas-generation-runner.js 的 apiConcurrentRun 对齐：
//    那边 = isApiLikeEngine(engine) || engine==='runninghub'，即 RH 算「会置 apiRunning 的那类」。
//    之前按钮侧用布局 class(closest .api-single-row/.api-video-row) 判 API 身份，
//    而 RH 挂的是互斥的 .rh-single-row → 命中不了，两处口径打架（RH 按钮毫无动效）。
function isWorkflowEngine(engine){
    const key = String(engine || '').toLowerCase();
    return key === 'comfy' || key === 'runninghub';
}
// ===== 产出类型（图片/视频）识别与切换（2026-09-24 方案B）=====
// API/火山：手动切（apiKind）。RH/Comfy：切工作流时按工作流产出自动设默认值，
// 用户仍可手动改（App 封装应用无图可扫，只能默认+手改）；实际输出落图/落视频
// 仍按产出 URL 后缀兜底，不会错数据。
const RH_VIDEO_TITLE_RE = /视频|video|即梦|seedance|可灵|kling|veo|海螺|hailuo|wan\b|万象|sora|p-?video|动效|mv/i;
function scanComfyGraphIsVideo(graph){
    // graph: ComfyUI API 格式 {nodeId:{class_type,...}}；扫输出节点类型
    let sawImageOut = false;
    const vals = Object.values(graph || {});
    for(const node of vals){
        const ct = String(node?.class_type || node?.type || '');
        const title = String(node?._meta?.title || '');
        const hay = (ct + ' ' + title).toLowerCase();
        if(/video\s*_?\s*combine|savevideo|createvideo|vhs_\s*video|video\b.*\b(save|out|combine)|video_?(rotate|extract|split)|save\s*webm|save\s*mp4/.test(hay)) return true;
        if(/saveimage|save\s*image|saveanimatedimage/.test(hay)) sawImageOut = true;
    }
    return false;
}
function workflowOutputKindForRhEntry(entry){
    if(!entry) return 'image';
    const wj = entry.workflowJson;
    let graph = wj;
    if(typeof graph === 'string'){ try { graph = JSON.parse(graph); } catch(_) { graph = null; } }
    if(graph && typeof graph === 'object' && Object.keys(graph).length){
        try { return scanComfyGraphIsVideo(graph) ? 'video' : 'image'; } catch(_) {}
    }
    // 无 JSON 可扫（AI App/拉取失败）→ 弱提示：标题含视频词即猜视频
    return RH_VIDEO_TITLE_RE.test(String(entry.title || entry.name || '')) ? 'video' : 'image';
}
function workflowOutputKindForComfy(name){
    const wf = comfyWorkflowCache[name];
    const graph = wf?.workflow || wf?.prompt || null;
    if(graph && typeof graph === 'object' && Object.keys(graph).length){
        try { return scanComfyGraphIsVideo(graph) ? 'video' : 'image'; } catch(_) {}
    }
    return RH_VIDEO_TITLE_RE.test(String(name || '')) ? 'video' : 'image';
}
function runKindForSettings(s){
    // 统一按 apiKind 记日志类型（RH/Comfy 已由 applyWorkflowOutputKind 同步为工作流识别值；
    // blender 的 apiKind 恒为 image，行为与旧逻辑一致）
    return String(s?.apiKind) === 'video' ? 'video' : 'image';
}
function applyWorkflowOutputKind(key){
    // 换工作流/选 RH 条目时自动设 图片/视频；App/无信息时按标题猜测并提示
    if(settings.engine === 'runninghub'){
        const parsed = parseRunningHubEntryKey(settings.rhConfigKey || key || '');
        if(parsed?.kind !== 'workflow') return;
        const entry = (runningHubEntries('workflow') || []).find(e => runningHubEntryId(e, 'workflow') === parsed.id);
        const kind = workflowOutputKindForRhEntry(entry);
        const wj = entry?.workflowJson;
        const hasGraph = wj && (typeof wj !== 'string' || wj.trim().length > 4);
        if(settings.apiKind !== kind) settings.apiKind = kind;
        if(!hasGraph) toast(kind === 'video' ? '该应用按名称识别为视频工作流，请确认' : '该应用无流程图可识别，默认按图片工作流，可手动切换');
    } else if(settings.engine === 'comfy'){
        const kind = workflowOutputKindForComfy(settings.comfyWorkflow || key || '');
        if(settings.apiKind !== kind) settings.apiKind = kind;
    }
    syncApiKindToggleVisibility();
}
function mediaItemForStorage(item){
    if(!item || typeof item !== 'object') return item;
    const clean = {...item};
    delete clean.cloudUrl;
    delete clean.uploadedUrl;
    delete clean.originalRemoteUrl;
    delete clean.tempCloudUrl;
    return clean;
}
function canvasForStorage(){
    const clean = JSON.parse(JSON.stringify(canvas || {}));
    clean.settings = settingsForStorage(canvasDefaultSmartSettings || initialSmartSettings);
    (clean.nodes || []).forEach(node => {
        if(Array.isArray(node.images)) node.images = node.images.map(mediaItemForStorage);
        if(node.runSettings) node.runSettings = settingsForStorage(node.runSettings);
    });
    return clean;
}
const RECENT_SMART_SETTINGS_KEY = 'smart_canvas_recent_run_settings_v1';
const initialSmartSettings = cloneSmartSettings(settings);
let canvasDefaultSmartSettings = cloneSmartSettings(settings);
// 默认设置引擎绝不为 blender（3D预演 是节点专用）
if(initialSmartSettings.engine === 'blender') initialSmartSettings.engine = 'api';
if(canvasDefaultSmartSettings.engine === 'blender') canvasDefaultSmartSettings.engine = 'api';
let recentSmartSettingsByMode = {};
function smartSettingsModeKey(source=settings){
 const engine = ['api','volcengine','comfy','runninghub'].includes(source?.engine) ? source.engine : 'api';
 if(engine === 'api') return `api:${source?.apiKind === 'video' ? 'video' : 'image'}`;
 if(engine === 'volcengine') return `volcengine:${source?.apiKind === 'video' ? 'video' : 'image'}`;
 if(engine === 'comfy') return 'comfy:workflow';
 if(engine === 'runninghub') return 'runninghub';
}
function loadRecentSmartSettings(){
    try {
        const data = JSON.parse(localStorage.getItem(RECENT_SMART_SETTINGS_KEY) || '{}');
        recentSmartSettingsByMode = data && typeof data === 'object' ? data : {};
        // 清理历史遗留的 blender 污染（3D预演 是节点专用，不得进入全局 recent）
        Object.values(recentSmartSettingsByMode).forEach(s => {
            if(s && typeof s === 'object' && s.engine === 'blender'){
                delete s.engine; delete s.provider_id; delete s.model;
            }
        });
    } catch(e) {
        recentSmartSettingsByMode = {};
    }
}
function saveRecentSmartSettings(){
    localStorage.setItem(RECENT_SMART_SETTINGS_KEY, JSON.stringify(recentSmartSettingsByMode));
}
function recentSmartSettingsForMode(modeKey=''){
    const key = modeKey || recentSmartSettingsByMode.__lastKey || smartSettingsModeKey(settings);
    const saved = recentSmartSettingsByMode[key];
    const clean = saved && typeof saved === 'object' ? cloneSmartSettings(saved) : {};
    // 防历史污染：blender 是节点专用引擎，不进全局 recent
    if(clean.engine === 'blender'){ delete clean.engine; delete clean.provider_id; delete clean.model; }
    return clean;
}
function rememberRecentSmartSettings(source=settings, node=null){
    const clean = stripOutpaintDisplaySettings(settingsForStorage(source), node);
    sanitizeSmartApiSelection(clean);
    if(clean.outpaintResolutionLocked === true && clean.resolution === 'custom'){
        clean.resolution = '1k';
        clean.ratio = clean.ratio || 'square';
        clean.customWidth = '';
        clean.customHeight = '';
        clean.customSize = '';
    }
    delete clean.outpaintResolutionLocked;
    // 3D预演 是节点专用引擎，不进全局 recent（否则污染其他节点的默认设置）
    if(clean.engine === 'blender') return;
    const key = smartSettingsModeKey(clean);
    recentSmartSettingsByMode[key] = settingsForStorage(clean);
    recentSmartSettingsByMode.__lastKey = key;
    saveRecentSmartSettings();
}
function applyRecentSmartSettingsForCurrentMode(){
    const availableEngines = smartAvailableEngines();
    const requestedEngine = availableEngines.includes(settings.engine) ? settings.engine : (availableEngines[0] || 'api');
    const requestedApiKind = settings.apiKind === 'video' ? 'video' : 'image';
    const key = smartSettingsModeKey(settings);
    const saved = recentSmartSettingsForMode(key);
    if(!Object.keys(saved).length){
        settings.engine = requestedEngine;
        if(isApiLikeEngine(requestedEngine)) settings.apiKind = requestedApiKind;
        clearVolcengineSelectionOutsideVolcengine(settings);
        sanitizeSmartApiSelection(settings);
        return;
    }
    // 防旧污染：recent 里若有 blender（历史版本遗留），清除
    if(saved.engine === 'blender'){ delete saved.engine; delete saved.provider_id; }
    settings = {...settings, ...saved, engine:requestedEngine};
    if(isApiLikeEngine(requestedEngine)) settings.apiKind = requestedApiKind;
    clearVolcengineSelectionOutsideVolcengine(settings);
    sanitizeSmartApiSelection(settings);
}
function clearVolcengineSelectionOutsideVolcengine(target=settings){
    if(!target || typeof target !== 'object' || target.engine === 'volcengine') return target;
    if(target.provider_id === 'volcengine') target.provider_id = '';
    if(target.videoProvider === 'volcengine') target.videoProvider = '';
    return target;
}
function canvasNodeRegistry(){
    return (typeof window !== 'undefined' && window.CanvasNodeRegistry) ? window.CanvasNodeRegistry : null;
}

// ===== 画布输入模式：连线模式 / 无线模式（无线 Set / Get）=====
// 无线模式：隐藏端口圆点与连线（只隐藏渲染，绝不删 canvas.connections 数据）；
// 结果节点可“设为 Set”发布当前结果；其它节点通过“引用结果”无线引用（不连线、不复制媒体）；
// 运行时才解析，读的是来源节点当前成功结果（跟最新），来源重跑不自动触发下游任务。
function canvasInputMode(){
    return (canvas && canvas.inputMode === 'objects') ? 'objects' : 'connections';
}
function canvasObjectsMode(){
    return canvasInputMode() === 'objects';
}
function canvasNodeHasSetResult(node){
    if(!node || isHistoryGroupNode(node) || isCanvasGroupNode(node)) return false;
    if((node.images || []).some(img => img?.url)) return true;
    if(node.type === 'smart-prompt') return Boolean(String(node.text || '').trim());
    return false;
}
function canvasNodeResultKind(node){
    if(!node) return '';
    const img = (node.images || []).find(item => item?.url);
    if(img){
        const kind = mediaKindForItem(img);
        return ['image','video','audio'].includes(kind) ? kind : 'file';
    }
    if(String(textForNode(node) || '').trim()) return 'text';
    return '';
}
function canvasSetSourceNodes(){
    return nodes.filter(n => n.canvasSetEnabled === true && canvasNodeHasSetResult(n));
}
function canvasObjectReferencesFor(node){
    return (node && Array.isArray(node.objectReferences)) ? node.objectReferences.filter(ref => ref && ref.sourceNodeId) : [];
}
// 运行时解析：引用只指向来源节点，不复制媒体；来源没 Set / 已删 / 暂无结果 → 不产生输入
// 无线引用仅在无线模式解析；切到有线时同步为输入连线，由连线继续提供输入。
function canvasObjectReferenceImages(node, ctx=smartLoopContext){
    if(!canvasObjectsMode()) return [];
    return canvasObjectReferencesFor(node).flatMap(ref => {
        const source = nodes.find(n => n.id === ref.sourceNodeId);
        if(!source || source.canvasSetEnabled !== true) return [];
        return outputImagesForNode(source, false, ctx).map(img => ({...img, objectReferenceId:ref.id, refSource:'object'}));
    });
}
function canvasObjectReferenceTextNodes(node){
    if(!canvasObjectsMode()) return [];
    return canvasObjectReferencesFor(node).map(ref => {
        const source = nodes.find(n => n.id === ref.sourceNodeId);
        if(!source || source.canvasSetEnabled !== true) return '';
        return textForNode(source);
    }).filter(Boolean);
}
// 来源节点被删除 / 引用失效时清掉悬挂引用（PRD：删除来源不得留下失效引用）
function pruneCanvasObjectReferences(){
    if(!canvas) return 0;
    const existing = new Set(nodes.map(n => n.id));
    let removed = 0;
    nodes.forEach(node => {
        const refs = canvasObjectReferencesFor(node);
        const declared = Array.isArray(node.objectReferences) ? node.objectReferences.length : 0;
        const keep = refs.filter(ref => existing.has(ref.sourceNodeId) && ref.sourceNodeId !== node.id);
        if(keep.length !== declared) removed += declared - keep.length;
        if(keep.length) node.objectReferences = keep;
        else delete node.objectReferences;
    });
    return removed;
}
function canvasNodeSetToggleHtml(node){
    if(!canvasObjectsMode() || !canvasNodeHasSetResult(node)) return '';
    const isSet = node.canvasSetEnabled === true;
    return `<button class="mini-x node-set-toggle ${isSet ? 'is-set' : ''}" type="button" title="${escapeAttr(tr(isSet ? 'smart.unsetNode' : 'smart.setNode'))}"><i data-lucide="${isSet ? 'radio' : 'circle-dot'}"></i></button>`;
}
// 无线取消引用也要移除同一输入的隐藏连线，避免缩略图继续显示或切回有线后复活。
function disconnectCanvasObjectReference(consumerId, sourceNodeId){
    if(!canvasObjectsMode()) return;
    canvas.connections = (canvas.connections || []).filter(conn =>
        !(conn.from === sourceNodeId && conn.to === consumerId && ['input', 'flow'].includes(conn.kind || 'flow')));
    const consumer = nodes.find(n => n.id === consumerId);
    if(Array.isArray(consumer?.inputNodeIds)){
        consumer.inputNodeIds = consumer.inputNodeIds.filter(id => id !== sourceNodeId);
    }
}
function toggleCanvasNodeSet(nodeId){
    const node = nodes.find(n => n.id === nodeId);
    if(!node) return;
    if(!canvasNodeHasSetResult(node)){ toast(tr('smart.setNeedResult')); return; }
    pushUndo();
    if(node.canvasSetEnabled === true){
        delete node.canvasSetEnabled;
        let removed = 0;
        nodes.forEach(other => {
            disconnectCanvasObjectReference(other.id, nodeId);
            const refs = canvasObjectReferencesFor(other);
            const keep = refs.filter(ref => ref.sourceNodeId !== nodeId);
            if(keep.length !== refs.length) removed += refs.length - keep.length;
            if(keep.length) other.objectReferences = keep;
            else delete other.objectReferences;
        });
        toast(removed ? tr('smart.unsetNodeDoneWithRefs').replace('{n}', String(removed)) : tr('smart.unsetNodeDone'));
    } else {
        node.canvasSetEnabled = true;
        toast(tr('smart.setNodeDone'));
    }
    render();
    scheduleSave();
}
function setCanvasInputMode(mode, opts={}){
    const next = mode === 'objects' ? 'objects' : 'connections';
    if(!canvas || canvasInputMode() === next) return;
    pushUndo();
    canvas.inputMode = next;
    // 切到无线模式：连线里的所有“被引用源节点”（connections[].from）自动设为 Set 并选中，
    // 使它们成为可被其它节点无线引用（引用结果）的发布源，并高亮方便二次操作。
    if(next === 'objects'){
        // 有线输入是当前引用关系的依据。保留已有引用 ID，清掉有线期间已断开的旧引用。
        nodes.forEach(consumer => {
            const previous = canvasObjectReferencesFor(consumer);
            const sourceIds = Array.from(new Set((canvas.connections || [])
                .filter(conn => conn.to === consumer.id && conn.from !== consumer.id && ['input', 'flow'].includes(conn.kind || 'flow'))
                .map(conn => conn.from).filter(id => nodes.some(n => n.id === id))));
            const refs = sourceIds.map(sourceNodeId => previous.find(ref => ref.sourceNodeId === sourceNodeId)
                || {id:uid('canvasobjref'), sourceNodeId, versionMode:'latest', createdAt:Date.now()});
            if(refs.length) consumer.objectReferences = refs;
            else delete consumer.objectReferences;
        });
        const referencedIds = Array.from(new Set((canvas.connections || []).map(c => c.from).filter(Boolean)));
        const targets = referencedIds.map(id => nodes.find(n => n.id === id)).filter(Boolean);
        if(targets.length){
            targets.forEach(n => { n.canvasSetEnabled = true; });
            const merged = Array.from(new Set([...selectedNodeIds(), ...targets.map(n => n.id)]));
            canvasUiState.patchSelection({ids: merged}, 'selectedIds');
            syncSelectionUi();
        }
    } else {
        // 无线新增的引用补为真实输入连线；已有 input/flow 连线沿用，反复切换不重复添加。
        nodes.forEach(consumer => canvasObjectReferencesFor(consumer).forEach(ref => {
            const source = nodes.find(n => n.id === ref.sourceNodeId);
            if(!source || source.id === consumer.id || source.canvasSetEnabled !== true) return;
            const connected = (canvas.connections || []).some(conn => conn.from === source.id && conn.to === consumer.id
                && ['input', 'flow'].includes(conn.kind || 'flow'));
            if(!connected) connectInputNode(source.id, consumer.id);
        }));
    }
    closeCanvasObjectRefPicker();
    syncCanvasInputModeUi();
    render();
    scheduleSave();
    if(!opts.silent) toast(next === 'objects' ? tr('smart.modeWirelessOn') : tr('smart.modeConnectionsOn'));
}
function toggleCanvasInputMode(){
    setCanvasInputMode(canvasObjectsMode() ? 'connections' : 'objects');
}
function syncCanvasInputModeUi(){
    const objects = canvasObjectsMode();
    document.body.classList.toggle('canvas-mode-objects', objects);
    const btn = document.getElementById('canvasInputModeToggle');
    if(!btn) return;
    const key = objects ? 'objects' : 'connections';
    if(btn.dataset.mode === key) return;
    btn.dataset.mode = key;
    btn.classList.toggle('is-objects', objects);
    btn.title = objects ? tr('smart.modeWirelessTip') : tr('smart.modeConnectionsTip');
    const icon = btn.querySelector('i');
    if(icon) icon.setAttribute('data-lucide', objects ? 'wifi' : 'link-2');
    const label = document.getElementById('canvasInputModeLabel');
    if(label) label.textContent = objects ? tr('smart.modeWireless') : tr('smart.modeConnections');
    if(window.lucide) lucide.createIcons();
}
function isSmartImageNode(node){
    // ① 走节点注册表（类型 → 能力）；注册表未加载/未知类型时回退到老判定，行为完全等价
    if(!node) return false;
    const reg = canvasNodeRegistry();
    if(reg) return node.type ? reg.nodeTypeHasImages(node.type) : true;
    return Boolean(node.type === 'smart-image' || !node.type);
}
function canvasNodePorts(node){
    const reg = canvasNodeRegistry();
    return reg ? reg.nodeTypePorts(node?.type, node) : {inputs:[], outputs:[]};
}
// ① 端口元信息统一走注册表：DOM 上的 data-port-type / 提示都从这里来
function canvasPortMeta(type, direction){
    const reg = canvasNodeRegistry();
    if(!reg) return {type:'any', label: direction === 'input' ? '输入' : '输出', tip: ''};
    const primary = reg.nodePrimaryPort(type, direction);
    return {
        type: primary?.dataType || 'any',
        label: primary?.label || (direction === 'input' ? '输入' : '输出'),
        tip: reg.labelForNodePort(type, direction) || (direction === 'input' ? '输入' : '输出')
    };
}
function canvasPortDotsHtml(node, direction){
    // 无线模式：隐藏端口圆点（只隐藏，画布数据不动）
    if(canvasObjectsMode()) return '';
    const meta = canvasPortMeta(node?.type, direction);
    const cls = direction === 'input' ? 'port-in' : 'port-out';
    const dataPort = direction === 'input' ? 'in' : 'out';
    return `<div class="node-port ${cls}" data-port="${dataPort}" data-port-type="${escapeAttr(meta.type)}" data-port-label="${escapeAttr(meta.label)}" title="${escapeAttr(meta.tip)}"></div>`;
}
function canvasNodeDescribe(node){
    const reg = canvasNodeRegistry();
    return reg ? reg.describeNode(node) : null;
}
function isHistoryGroupNode(node){
    return Boolean(isSmartImageNode(node) && (node.isHistoryGroup || node.historyFor));
}
function isCanvasGroupNode(node){
    const reg = canvasNodeRegistry();
    if(reg) return Boolean(node?.type && reg.nodeTypeIsContainer(node.type));
    return Boolean(node?.type === 'smart-group');
}
function nodeHasCompletedGeneration(node){
    // 时间戳之外再认"带生成结果图"：后端 Agent/ComfyUI 直写回填的旧节点没有 runAt/runFinishedAt，
    // 只看时间戳会让用户点运行时被误判为首跑、旧图不进历史分组
    return Boolean(node && (node.runAt || node.runFinishedAt || (node.images || []).some(img => img?.generatedResult)));
}
function normalizeSmartImageMode(mode){
    return 'self';
}
function smartImageMode(node){
    return 'self';
}
function setSmartImageMode(node, mode){
    if(!isSmartImageNode(node)) return;
    delete node.imageMode;
}
function smartImageUsesWorkflowInput(node, ctx=smartLoopContext){
    return Boolean(isSmartImageNode(node) && ctx?.forceWorkflow);
}
function normalizeLegacySmartNode(node){
    if(!node || typeof node !== 'object') return node;
    if(node.type === 'smart-container'){
        const fallbackImage = node.inputImage?.url ? stripImageGenerationMeta({
            url:node.inputImage.url,
            name:node.inputImage.name || 'image',
            kind:node.inputImage.kind || mediaKindForItem(node.inputImage),
            natural_w:Number(node.inputImage.natural_w || 0),
            natural_h:Number(node.inputImage.natural_h || 0)
        }) : null;
        const images = Array.isArray(node.images) && node.images.length
            ? node.images
            : (fallbackImage ? [fallbackImage] : []);
        const normalized = {
            ...node,
            type:'smart-image',
            title:images.length > 1 ? 'Group' : (images.length ? 'Image' : tr('smart.createImportNode')),
            images
        };
        delete normalized.imageMode;
        delete normalized.inputImage;
        delete normalized.steps;
        delete normalized.resultGrouping;
        return normalized;
    }
    if(!node.type) node.type = 'smart-image';
    if(node.type === 'director'){
        const screenshot = node.images?.find?.(img => img?.url) || null;
        node.type = 'smart-image';
        node.title = screenshot?.name || node.title || 'Image';
        node.images = screenshot ? [screenshot] : [];
        delete node.directorData;
    }
    if(node.type === 'note'){
        // 旧 Agent 文本节点（canvas_create_text_node 早期产物）迁移为原生 smart-prompt
        node.type = 'smart-prompt';
        node.kind = 'text';
        node.text = String(node.text || node.content || '').trim();
        node.llmEnabled = false;
        node.llmSystemEnabled = false;
        if(!node.w) node.w = 316;
        if(!node.h) node.h = 194;
    }
    if(node.type === 'smart-image'){
        if(node.cardSize && !node.cardSizing){
            delete node.cardSize;
            delete node.w;
            delete node.h;
            if(!(node.images || []).length){
                const box = nodeRatioBox(node);
                node.cardSize = {width:box.w, height:box.h};
                node.cardSizing = 'default';
            }
        }
        delete node.imageMode;
        const previous = node.images || [];
        node.images = CanvasGenerationResultModel.uniqueMediaItems(previous);
        if(previous.length > node.images.length && node.images.length === 1){
            if(['Group','Images','Videos','Audios','Texts'].includes(node.title)) node.title = node.outputKind === 'video' ? 'Video' : node.outputKind === 'audio' ? 'Audio' : node.outputKind === 'text' ? 'Text' : 'Image';
            delete node.w;
            delete node.h;
        }
    }
    if(node.type === 'smart-image' && node.historyFor) node.isHistoryGroup = true;
    const savedEngine = String(node.runSettings?.engine || '').toLowerCase();
    if(node.running && !Number(node.pending) && !node.jimengPending && ['api', 'volcengine', 'runninghub', 'comfy'].includes(savedEngine)){
        node.running = false;
    }
    return node;
}
function validOutpaintSize(node){
    const w = Math.round(Number(node?.outpaintSize?.width || 0));
    const h = Math.round(Number(node?.outpaintSize?.height || 0));
    return w > 0 && h > 0 ? {width:w, height:h} : null;
}
function parseSizePair(value){
    const match = String(value || '').match(/(\d+)\s*x\s*(\d+)/i);
    return match ? {width:Number(match[1]), height:Number(match[2])} : null;
}
function nearestFourKSizeFor(width, height){
    const w = Math.max(1, Number(width) || 1);
    const h = Math.max(1, Number(height) || 1);
    const ratio = w / h;
    let best = null;
    Object.entries(SIZE_MAP).forEach(([key, values]) => {
        const size = parseSizePair(values?.['4k']);
        if(!size) return;
        const score = Math.abs(Math.log(ratio / (size.width / size.height)));
        if(!best || score < best.score) best = {...size, key, score};
    });
    return best;
}
function exceedsFourKStandard(width, height){
    const standard = nearestFourKSizeFor(width, height);
    if(!standard) return false;
    return Number(width) > standard.width || Number(height) > standard.height;
}
function withOutpaintDisplaySettings(node, baseSettings){
    const size = validOutpaintSize(node);
    if(!size) return baseSettings;
    const engine = ['api','volcengine','comfy','runninghub'].includes(baseSettings?.engine) ? baseSettings.engine : 'api';
    const next = {
        ...baseSettings,
        resolution:'custom',
        ratio:'',
        customWidth:size.width,
        customHeight:size.height,
        customSize:`${size.width}x${size.height}`,
        outpaintResolutionLocked:true
    };
    if(isApiLikeEngine(engine)) next.apiKind = 'image';
    if(engine === 'comfy'){
        next.width = size.width;
        next.height = size.height;
    }
    return next;
}
function stripOutpaintDisplaySettings(settingsObj, node=null){
    const clean = cloneSmartSettings(settingsObj);
    const size = validOutpaintSize(node);
    const matchesOutpaintSize = size && clean.resolution === 'custom' && String(clean.customSize || '') === `${size.width}x${size.height}`;
    if(matchesOutpaintSize){
        clean.resolution = '1k';
        clean.ratio = clean.ratio || 'square';
        clean.customWidth = '';
        clean.customHeight = '';
        clean.customSize = '';
    }
    if(size && Number(clean.width) === size.width && Number(clean.height) === size.height){
        clean.width = 1024;
        clean.height = 1024;
    }
    delete clean.outpaintResolutionLocked;
    return clean;
}
function smartSettingsForNode(node){
    const nodeSettings = stripOutpaintDisplaySettings(node?.runSettings || {}, node);
    const recentSettings = Object.keys(nodeSettings).length ? {} : recentSmartSettingsForMode();
    const base = {
        ...cloneSmartSettings(canvasDefaultSmartSettings || initialSmartSettings),
        ...recentSettings,
        ...nodeSettings
    };
    if(nodeSettings.videoReferenceMode === undefined && nodeSettings.videoUseFrameRoles === true) base.videoReferenceMode = 'first_last';
    if(nodeSettings.videoReferenceMode === undefined && nodeSettings.videoTrustedAsset === true) base.videoReferenceMode = 'mixed';
    if(recentSettings.videoReferenceMode === undefined && recentSettings.videoUseFrameRoles === true && nodeSettings.videoReferenceMode === undefined) base.videoReferenceMode = 'first_last';
    return withOutpaintDisplaySettings(node, base);
}
function activeSettingsSubject(){
    const active = canvasUiState.editor.subject?.id
        ? (nodes.find(n => n.id === canvasUiState.editor.subject.id) || canvasUiState.editor.subject)
        : selectedNode();
    return isSmartImageNode(active) ? active : null;
}
function activeComposerNode(){
    if(!canvasUiState.editor.key) return null;
    const id = String(canvasUiState.editor.key).split(':')[0] || '';
    const node = nodes.find(n => n.id === id);
    return isSmartImageNode(node) ? node : null;
}
function persistActiveSmartSettings(){
    if(!composer?.classList?.contains('open')) return;
    const subject = activeComposerNode();
    if(!subject) return;
    // 3D预演 节点保护：节点是 blender 时，全局 settings 不得覆盖节点引擎
    if(subject.runSettings?.engine === 'blender' || settings.engine === 'blender'){
        settings.engine = 'blender';
        settings.provider_id = 'blender';
        settings.model = 'blender-previz';
    }
    const previousSpec = nodeCardSpecKey(subject.runSettings || {});
    subject.runSettings = settingsForStorage(settings);
    if(previousSpec !== nodeCardSpecKey(subject.runSettings) && syncNodeCardToSpec(subject)) render();
    rememberRecentSmartSettings(settings, subject);
}
function backToCanvasList(){ return CanvasHeaderNavigation.backToCanvasList(); }
function loadAllCanvasesForDropdown(){ return CanvasHeaderNavigation.loadAllCanvases(); }
function toggleCanvasListDropdown(event){ return CanvasHeaderNavigation.toggleDropdown(event); }
function openCanvasListDropdown(){ return CanvasHeaderNavigation.openDropdown(); }
function closeCanvasListDropdown(){ return CanvasHeaderNavigation.closeDropdown(); }
function renderCanvasDropdownItems(){ return CanvasHeaderNavigation.renderDropdownItems(); }
function renderDropdownCanvasIcon(icon,size=14){ return CanvasHeaderNavigation.renderDropdownCanvasIcon(icon,size); }
function formatCanvasTimeShort(ts){ return CanvasHeaderNavigation.formatCanvasTimeShort(ts); }
function switchToCanvas(id){ return CanvasHeaderNavigation.switchToCanvas(id); }
function startRenameCanvasFromHeader(event){ return CanvasHeaderNavigation.startRename(event); }
function finishRenameCanvasFromHeader(commit){ return CanvasHeaderNavigation.finishRename(commit); }
function setCanvasTitle(id,title){ return CanvasHeaderNavigation.setCanvasTitle(id,title); }
function applyCanvasFolderRename(oldFolder,newFolder){ return CanvasHeaderNavigation.applyFolderRename(oldFolder,newFolder); }
function handleCanvasRenamedMessage(data){ return CanvasHeaderNavigation.handleCanvasRenamedMessage(data); }
function updateCanvasTitleDisplay(){ return CanvasHeaderNavigation.updateTitleDisplay(); }
function createNewCanvasFromDropdown(){ return CanvasHeaderNavigation.createNewCanvas(); }

function promptPlainText(){
    return promptInput.innerText.replace(/\u00a0/g, ' ').trim();
}
function setPromptInputLocked(locked){
    promptInput.dataset.promptLocked = locked ? '1' : '0';
    promptInput.setAttribute('contenteditable', locked ? 'false' : 'true');
    promptInput.classList.toggle('prompt-input-locked', Boolean(locked));
    if(locked) closeMentionPicker();
}
function setPromptText(text){
    promptInput.textContent = text || '';
}
function clearPromptInput(options={}){
    if(options.preserveDraft){
        promptInput.dataset.preserveDraftOnce = '1';
        closeMentionPicker();
        return;
    }
    promptInput.textContent = '';
    closeMentionPicker();
    if(canvasUiState.editor.subject){
        canvasUiState.editor.subject.promptDraftHtml = '';
        canvasUiState.editor.subject.promptDraftText = '';
    }
}
function applyTheme(theme){
    const dark = window.StudioTheme?.isDark?.(theme) ?? (theme === 'dark');
    document.documentElement.classList.toggle('theme-dark', dark);
    document.documentElement.classList.toggle('studio-theme-dark', dark);
    document.body?.classList.toggle('theme-dark', dark);
    document.body?.classList.toggle('studio-theme-dark', dark);
}
function toast(text){
    const el = document.getElementById('toast');
    el.textContent = text;
    el.classList.add('show');
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => el.classList.remove('show'), 1800);
}
function selectedNode(){ return CanvasNodeSelectionController.selectedNode(); }
function clearSelection(){ return CanvasNodeSelectionController.clearSelection(); }
function clearImageClickTimer(){
    if(imageClickTimer){
        clearTimeout(imageClickTimer);
        imageClickTimer = null;
    }
}
function clearInputThumbDragClasses(){
    inputThumbsRow?.querySelectorAll('.input-thumb:not(.input-thumb-text)').forEach(el => {
        el.classList.remove('dragging', 'drop-before', 'drop-after');
    });
}
function inputThumbInsertIndexAtClientX(clientX){
    const thumbs = [...(inputThumbsRow?.querySelectorAll('.input-thumb:not(.input-thumb-text)') || [])];
    if(!thumbs.length) return 0;
    let insertIndex = 0;
    for(let index = 0; index < thumbs.length; index++){
        const rect = thumbs[index].getBoundingClientRect();
        if(clientX > rect.left + rect.width / 2) insertIndex = index + 1;
        else break;
    }
    return Math.max(0, Math.min(thumbs.length, insertIndex));
}
function updateInputThumbDragVisual(clientX){
    if(!inputThumbDragState) return;
    const thumbs = [...(inputThumbsRow?.querySelectorAll('.input-thumb:not(.input-thumb-text)') || [])];
    clearInputThumbDragClasses();
    const sourceEl = thumbs[inputThumbDragState.from];
    sourceEl?.classList.add('dragging');
    const insertIndex = inputThumbInsertIndexAtClientX(clientX);
    inputThumbDragState.insertIndex = insertIndex;
    if(!thumbs.length) return;
    if(insertIndex <= 0){
        thumbs[0]?.classList.add('drop-before');
        return;
    }
    if(insertIndex >= thumbs.length){
        thumbs[thumbs.length - 1]?.classList.add('drop-after');
        return;
    }
    thumbs[insertIndex]?.classList.add('drop-before');
}
function syncSelectionUi(){ return CanvasNodeSelectionController.syncSelectionUi(); }
function isNodeSelected(id){ return CanvasNodeSelectionController.isNodeSelected(id); }
function selectedNodeIds(){ return CanvasNodeSelectionController.selectedNodeIds(); }
function focusCanvasWorld(){ return CanvasNodeSelectionController.focusCanvasWorld(); }
function selectNodeFromPointer(nodeId, event=null, options={}){
    return CanvasNodeSelectionController.selectNodeFromPointer(nodeId, event, options);
}
function selectedPortDragSourceIds(drag){
    if(!drag || drag.fromPort !== 'out') return [drag?.fromId].filter(Boolean);
    const ids = selectedNodeIds();
    return ids.includes(drag.fromId) ? ids : [drag.fromId];
}
function connectSelectedNodesToTarget(sourceIds, targetId){
    const uniqueIds = Array.from(new Set((sourceIds || []).filter(Boolean)));
    if(!uniqueIds.length || !targetId) return 0;
    let count = 0;
    uniqueIds.forEach(fromId => {
        if(fromId === targetId) return;
        if(connectInputNode(fromId, targetId)) count += 1;
    });
    return count;
}
function nodeLayerZ(nodeOrId){
    const id = typeof nodeOrId === 'string' ? nodeOrId : (nodeOrId?.id || '');
    // 分组框(smart-group)永远压在成员之下：旧实现只在 render 模板里特判组=1，
    // 但 syncSelectionUi/refreshNodeLayerStyles 用本函数直写 style.zIndex 时会把组
    // 抬成 2，与未选中成员同层——谁在上面变成 DOM 追加顺序说了算，
    // 组框整面积木随重渲染时前时后 → 「组内节点有时死活点不到、有时一点就中」。
    const node = typeof nodeOrId === 'string' ? (nodes || []).find(n => n.id === nodeOrId) : nodeOrId;
    // 组（smart-group）必须压在【连线层之下】：连线层 connection-layer 是 z-index:1，
    // 普通节点 2/4。组返回 0（<1）才能稳稳躺在连线之下，不会再盖住节点之间的连线。
    // 不能用 1——同层时谁在上由 DOM 追加顺序决定（节点在连线层之后渲染），
    // 组内节点重渲染会前时后，连线时而被盖时而不被盖（即"打组后连线被盖住"的元凶）。
    if(node && node.type === 'smart-group') return 0;
    return (id && (frontNodeIds.includes(id) || isNodeSelected(id))) ? 4 : 2;
}
function refreshNodeLayerStyles(){
    world?.querySelectorAll?.('.image-node').forEach(el => {
        el.style.zIndex = String(nodeLayerZ(el.dataset.id || ''));
    });
}
function bringNodesToFront(ids=[]){
    const list = [...new Set((Array.isArray(ids) ? ids : [ids]).filter(Boolean))];
    if(!list.length) return false;
    frontNodeIds = list.filter(id => nodes.some(node => node.id === id));
    refreshNodeLayerStyles();
    return Boolean(frontNodeIds.length);
}
function bringNodeSelectionToFront(nodeId=''){
    const ids = canvasUiState.selection.ids.includes(nodeId) ? canvasUiState.selection.ids.slice() : [nodeId];
    return bringNodesToFront(ids);
}
function selectedLayoutNodes(){
    return CanvasNodeLayoutController.selectedLayoutNodes();
}
function sortedSelectedLayoutNodes(){
    return CanvasNodeLayoutController.sortedSelectedLayoutNodes();
}
function canGroupSelectedNodes(){
    return CanvasNodeLayoutController.canGroupSelectedNodes();
}
function refreshSmartNodeToolButtons(){
    return CanvasNodeLayoutController.refreshToolButtons();
}
function syncCanvasAgentDockLayout(){
 window.CanvasLayoutCoordinator?.sync();
}
window.CanvasLayoutCoordinator?.configure({
 panel: canvasAgentPanel,
 isOpen: () => canvasAgentOpen,
 getLeftTools: () => document.querySelector('.canvas-bottom-cluster')
});
window.CanvasLayoutCoordinator?.start();

function setCanvasAgentOpen(open){
 canvasAgentOpen = Boolean(open);
 canvasAgentPanel?.classList.toggle('open', canvasAgentOpen);
 syncCanvasAgentDockLayout();
 canvasAgentToggle?.classList.toggle('visible', !canvasAgentOpen);
 canvasAgentToggle?.classList.toggle('active', canvasAgentOpen);
 try { localStorage.setItem('smart_canvas_agent_open', canvasAgentOpen ? '1' : '0'); } catch(_) {}
 if(canvasAgentOpen){
  // 从保存的预设恢复 Agent 选择并同步对话框标题
  const preset = canvasAgentModelPreset || canvasAgentLoadPreset();
  if(preset && preset.agentId && canvasAgentRegistry()[preset.agentId] && canvasAgentActiveId !== preset.agentId){
   canvasAgentActiveId = preset.agentId;
  }
  const entry = canvasAgentEntry(canvasAgentActiveId) || {};
  canvasAgentRefreshHeadTitle();
  // 不自动 focus 输入框：否则进画布时焦点被抢到 Agent 输入框，首次选中节点按 Del 会被输入框吃掉删不掉（点一下其它 UI 才恢复）。用户手动点开面板时才 focus（见 setCanvasAgentOpen 调用方）。
 }
 if(window.lucide) lucide.createIcons();
}
// Agent 开关拖拽定位域外移 canvas-agent-toggle-drag.js（第十一刀/B2）。dragState/suppressClickUntil 双通道，主文件仍为真变量。
if(globalThis.CanvasAgentToggleDrag){CanvasAgentToggleDrag.configure({
        canvasAgentToggle: () => canvasAgentToggle,
        CANVAS_AGENT_TOGGLE_POS_KEY: () => CANVAS_AGENT_TOGGLE_POS_KEY,
        canvasAgentToggleDragState: () => canvasAgentToggleDragState,
        canvasAgentToggleSuppressClickUntil: () => canvasAgentToggleSuppressClickUntil,
        setCanvasAgentToggleDragState: v => { canvasAgentToggleDragState = v; },
        setCanvasAgentToggleSuppressClickUntil: v => { canvasAgentToggleSuppressClickUntil = v; }
});}
function clampCanvasAgentTogglePosition(){return CanvasAgentToggleDrag.clampCanvasAgentTogglePosition.apply(null, arguments);}
function canvasAgentTogglePositionFromStored(){return CanvasAgentToggleDrag.canvasAgentTogglePositionFromStored.apply(null, arguments);}
function storedCanvasAgentTogglePosition(){return CanvasAgentToggleDrag.storedCanvasAgentTogglePosition.apply(null, arguments);}
function applyCanvasAgentTogglePosition(){return CanvasAgentToggleDrag.applyCanvasAgentTogglePosition.apply(null, arguments);}
function loadCanvasAgentTogglePosition(){return CanvasAgentToggleDrag.loadCanvasAgentTogglePosition.apply(null, arguments);}
function currentCanvasAgentTogglePosition(){return CanvasAgentToggleDrag.currentCanvasAgentTogglePosition.apply(null, arguments);}
function installCanvasAgentToggleDrag(){return CanvasAgentToggleDrag.installCanvasAgentToggleDrag.apply(null, arguments);}
function canvasAgentMediaLabel(item, index=0) {
    return CanvasAgentMessageRender.canvasAgentMediaLabel.apply(null, arguments);
}
function canvasAgentRefFromImage(img, node=null, index=0) {
    return CanvasAgentMessageRender.canvasAgentRefFromImage.apply(null, arguments);
}
// Agent 引用收集/上传域外移 canvas-agent-reference-intake.js（第十刀）。canvasAgentRefsState 块内只 push 不重赋，getter 足够。
if(globalThis.CanvasAgentReferenceIntake){CanvasAgentReferenceIntake.configure({
        canvasAgentMediaLabel: (...a) => canvasAgentMediaLabel(...a),
        canvasAgentRefFromImage: (...a) => canvasAgentRefFromImage(...a),
        canvasScopedUploadUrl: (...a) => canvasScopedUploadUrl(...a),
        mediaKindForFile: (...a) => mediaKindForFile(...a),
        mediaKindForItem: (...a) => mediaKindForItem(...a),
        renderCanvasAgentRefs: (...a) => renderCanvasAgentRefs(...a),
        selectedNode: (...a) => selectedNode(...a),
        selectedNodeIds: (...a) => selectedNodeIds(...a),
        setCanvasAgentOpen: (...a) => setCanvasAgentOpen(...a),
        smartResponseErrorMessage: (...a) => smartResponseErrorMessage(...a),
        textContentValue: (...a) => textContentValue(...a),
        textPreviewSnippet: (...a) => textPreviewSnippet(...a),
        toast: (...a) => toast(...a),
        RH_OFFICIAL_PROXY_BASE: () => RH_OFFICIAL_PROXY_BASE,
        canvasAgentFileInput: () => canvasAgentFileInput,
        canvasAgentPanel: () => canvasAgentPanel,
        canvasAgentRefsState: () => canvasAgentRefsState,
        nodes: () => nodes,
        selectedImage: () => canvasUiState.selection.image,
        visibleReferenceImagesFor: () => visibleReferenceImagesFor
});}
function collectCanvasAgentSelectedResources(){return CanvasAgentReferenceIntake.collectCanvasAgentSelectedResources.apply(null, arguments);}
function addCanvasAgentRefs(){return CanvasAgentReferenceIntake.addCanvasAgentRefs.apply(null, arguments);}
function isAgentTextFile(){return CanvasAgentReferenceIntake.isAgentTextFile.apply(null, arguments);}
function uploadCanvasAgentFiles(){return CanvasAgentReferenceIntake.uploadCanvasAgentFiles.apply(null, arguments);}
function canvasAgentFileTranscript(){return CanvasAgentReferenceIntake.canvasAgentFileTranscript.apply(null, arguments);}
function ensureSmartImageContextMenu(){
    return CanvasImageContextMenuController.ensure();
}
function closeSmartImageContextMenu(){
    return CanvasImageContextMenuController.close();
}
function openSmartImageContextMenu(nodeId, imageIndex, event){
    return CanvasImageContextMenuController.open(nodeId, imageIndex, event);
}
function smartImageAssetRef(nodeId, imageIndex){
    const node = nodes.find(n => n.id === nodeId);
    const img = (node?.images || [])[Number(imageIndex)] || null;
    return {node, img};
}
async function setSmartImageAssetVersionMode(nodeId, imageIndex, mode){
    const {img} = smartImageAssetRef(nodeId, imageIndex);
    if(!img || !String(img.assetId || '').trim()){ toast(tr('smart.assetNoRef')); return; }
    img.assetVersionMode = (mode === 'pinned') ? 'pinned' : 'latest';
    await saveCanvas();
    await loadCanvas();   // 让后端按新策略解析引用地址
    toast(img.assetVersionMode === 'pinned' ? tr('smart.assetPinned') : tr('smart.assetFollowed'));
}
async function saveSmartImageAsAssetVersion(nodeId, imageIndex){
    const {node, img} = smartImageAssetRef(nodeId, imageIndex);
    if(!img || !img.url){ toast(tr('smart.toastUploadFail')); return; }
    // 这张图自己没带 assetId 时，继承同节点里其它引用的素材（典型场景：节点引用着角色素材，重跑出图 → 新图登记为它的新版本）
    let assetId = String(img.assetId || '').trim();
    if(!assetId){
        const sibling = (node?.images || []).find(x => String(x.assetId || '').trim());
        assetId = String(sibling?.assetId || '').trim();
    }
    if(!assetId){ toast(tr('smart.assetNoRef')); return; }
    try{
        const res = await fetch('/api/asset-library/items/versions', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({item_id: assetId, url: img.url, name: img.name || ''})
        });
        const data = await res.json().catch(() => ({}));
        if(!res.ok || data.ok === false) throw new Error(data.detail || tr('smart.assetAddFail'));
        img.assetId = assetId;
        img.assetVersionMode = 'latest';
        await saveCanvas();
        await loadAssetLibrary();
        toast(trf('smart.assetVersionSaved', {n: Number(data.versionCount || 0)}));
    }catch(e){
        toast((e.message || tr('smart.assetAddFail')).slice(0, 120));
    }
}
function addImageNodeRefToCanvasAgent(nodeId, imageIndex){
const selectedForContext = selectedNodeIds();
const useSelectedGroup = selectedForContext.length > 1 && selectedForContext.includes(nodeId);
let refs = [];
if(useSelectedGroup){
refs = collectCanvasAgentSelectedResources();
} else {
const node = nodes.find(n => n.id === nodeId);
const ref = canvasAgentRefFromImage(node?.images?.[Number(imageIndex)], node, Number(imageIndex));
if(ref) refs = [ref];
}
if(!refs.length) return;
addCanvasAgentRefs(refs);
setCanvasAgentOpen(true);
canvasAgentInput?.focus();
toast(useSelectedGroup ? `已加入 ${refs.length} 个资源到 Agent` : '已加入 Agent');
}
function uniqueCanvasAgentRefs(refs=[]){
    const seen = new Set();
    return (refs || []).filter(ref => {
        if(!ref?.url || seen.has(ref.url)) return false;
        seen.add(ref.url);
        return true;
    });
}
function canvasAgentMentionCandidates(){
    return CanvasAgentMentionController.candidates();
}
function canvasAgentMentionQuery(){
    return CanvasAgentMentionController.query();
}
function ensureCanvasAgentMentionPicker(){
    return CanvasAgentMentionController.ensurePicker();
}
function closeCanvasAgentMention(){
    return CanvasAgentMentionController.close();
}
function canvasAgentRefFileName(ref) {
    return CanvasAgentMessageRender.canvasAgentRefFileName.apply(null, arguments);
}
// 编号铁律（用户 2026-09-11 定稿）：对话框不参与排序，@弹层略缩图网格顺序即编号——
// 网格第 N 张=图片N（同类分开计数），第几次@它号都不变；点选后引用条按网格序就位。
let canvasAgentMentionPoolSnapshot = [];
function canvasAgentRefKindLabel(ref) {
    return CanvasAgentMessageRender.canvasAgentRefKindLabel.apply(null, arguments);
}
function canvasAgentMentionBadge(ref) {
    return CanvasAgentMessageRender.canvasAgentMentionBadge.apply(null, arguments);
}
function canvasAgentRefStripLabel(ref, index) {
    return CanvasAgentMessageRender.canvasAgentRefStripLabel.apply(null, arguments);
}
function sortCanvasAgentRefsByMentionPool(){
    return CanvasAgentMentionController.sortRefsByMentionPool();
}
function renderCanvasAgentMention(){
    return CanvasAgentMentionController.render();
}
function insertCanvasAgentMention(ref){
    return CanvasAgentMentionController.insert(ref);
}
function removeCanvasAgentRef(url){
    canvasAgentRefsState = canvasAgentRefsState.filter(ref => ref.url !== url);
    renderCanvasAgentRefs();
}
function canvasAgentRefThumbHtml(ref, index=0) {
    return CanvasAgentMessageRender.canvasAgentRefThumbHtml.apply(null, arguments);
}
function renderCanvasAgentRefs(){
    if(!canvasAgentRefs) return;
    canvasAgentRefs.classList.toggle('has-refs', canvasAgentRefsState.length > 0);
    const uploadHtml = `<button id="canvasAgentUpload" class="canvas-agent-add" type="button" title="上传文件（文档/技能/图片）" aria-label="上传文件"><i data-lucide="paperclip"></i></button>`;
    const attachHtml = `<button id="canvasAgentAttach" class="canvas-agent-add" type="button" title="加入选中的画布资源" aria-label="加入选中的画布资源"><i data-lucide="plus"></i></button>`;
    canvasAgentRefs.innerHTML = canvasAgentRefsState.map(canvasAgentRefThumbHtml).join('') + uploadHtml + attachHtml;
    canvasAgentRefs.querySelectorAll('[data-agent-ref-remove]').forEach(btn => {
        btn.onclick = e => {
            e.preventDefault();
            e.stopPropagation();
            removeCanvasAgentRef(btn.dataset.agentRefRemove || '');
        };
    });
    canvasAgentRefs.querySelector('#canvasAgentAttach')?.addEventListener('click', e => {
        e.preventDefault();
        e.stopPropagation();
        attachSelectedResourcesToCanvasAgent();
    });
    canvasAgentRefs.querySelector('#canvasAgentUpload')?.addEventListener('click', e => {
        e.preventDefault();
        e.stopPropagation();
        canvasAgentFileInput?.click();
    });
    if(window.lucide) lucide.createIcons();
}
function canvasAgentSuggestionsFromText(text='') {
    return CanvasAgentMessageRender.canvasAgentSuggestionsFromText.apply(null, arguments);
}
function canvasAgentFormatLatency(ms) {
    return CanvasAgentMessageRender.canvasAgentFormatLatency.apply(null, arguments);
}
function canvasAgentToolLabel(name='') {
    return CanvasAgentMessageRender.canvasAgentToolLabel.apply(null, arguments);
}
function canvasAgentTraceFromToolLog(toolLog=[]) {
    return CanvasAgentMessageRender.canvasAgentTraceFromToolLog.apply(null, arguments);
}
function normalizeCanvasAgentResult(result={}, reply='') {
    return CanvasAgentMessageRender.normalizeCanvasAgentResult.apply(null, arguments);
}
function isCanvasAgentStoppedEmptyReply(result={}, text='') {
    return CanvasAgentMessageRender.isCanvasAgentStoppedEmptyReply.apply(null, arguments);
}
function canvasAgentQuickActionsForMessage(message) {
    return CanvasAgentMessageRender.canvasAgentQuickActionsForMessage.apply(null, arguments);
}
function canvasAgentInteractionHtml(ic, chosenId) {
    return CanvasAgentMessageRender.canvasAgentInteractionHtml.apply(null, arguments);
}
function canvasAgentMessageHtml(message) {
    return CanvasAgentMessageRender.canvasAgentMessageHtml.apply(null, arguments);
}
function renderCanvasAgentMessages(){
    return CanvasAgentMessageViewController.render();
}
function canvasAgentHistoryList() {
    return CanvasAgentHistoryStore.canvasAgentHistoryList();
}
function saveCanvasAgentHistoryList(list) {
    return CanvasAgentHistoryStore.saveCanvasAgentHistoryList(list);
}
function canvasAgentHistoryKeyFor(id='') {
    return CanvasAgentHistoryStore.canvasAgentHistoryKeyFor(id);
}
function canvasAgentLegacyHistoryList() {
    return CanvasAgentHistoryStore.canvasAgentLegacyHistoryList();
}
function canvasAgentLegacyHistoryListFor(canvasHistoryId='') {
    return CanvasAgentHistoryStore.canvasAgentLegacyHistoryListFor(canvasHistoryId);
}
async function migrateLegacyCanvasAgentHistories() {
    return CanvasAgentHistoryStore.migrateLegacyCanvasAgentHistories();
}
async function loadCanvasAgentHistoryList(force=false) {
    return CanvasAgentHistoryStore.loadCanvasAgentHistoryList(force);
}
async function persistCanvasAgentHistoryStore() {
    return CanvasAgentHistoryStore.persistCanvasAgentHistoryStore();
}
async function loadCanvasAgentHistoryIndex() {
    return CanvasAgentHistoryStore.loadCanvasAgentHistoryIndex();
}
function canvasAgentSessionTitle(messages=canvasAgentMessagesState) {
    return CanvasAgentHistoryStore.canvasAgentSessionTitle(messages);
}
function canvasAgentRefreshHeadTitle(){
    const titleEl = document.querySelector('.canvas-agent-title');
    if(titleEl) titleEl.textContent = canvasAgentSessionTitle();
}
function canvasAgentCloneRefs(refs=[]) {
    return CanvasAgentHistoryStore.canvasAgentCloneRefs(refs);
}
function canvasAgentCloneActionPlan(plan) {
    return CanvasAgentHistoryStore.canvasAgentCloneActionPlan(plan);
}
function canvasAgentCloneMessage(message) {
    return CanvasAgentHistoryStore.canvasAgentCloneMessage(message);
}
function restoreCanvasAgentActionPlans(messages=[]) {
    return CanvasAgentHistoryStore.restoreCanvasAgentActionPlans(messages);
}
function isCanvasAgentFailureMessage(message) {
    return CanvasAgentHistoryStore.isCanvasAgentFailureMessage(message);
}
function canvasAgentCleanPromptCandidate(value='') {
    return CanvasAgentHistoryStore.canvasAgentCleanPromptCandidate(value);
}
function canvasAgentFallbackPromptCandidate(value='') {
    return CanvasAgentHistoryStore.canvasAgentFallbackPromptCandidate(value);
}
function extractCanvasAgentPrompt(text='') {
    return CanvasAgentHistoryStore.extractCanvasAgentPrompt(text);
}
function canvasAgentSerializableMessages(messages=canvasAgentMessagesState) {
    return CanvasAgentHistoryStore.canvasAgentSerializableMessages(messages);
}
async function persistCanvasAgentSession() {
    return CanvasAgentHistoryStore.persistCanvasAgentSession();
}
// Agent 会话面板域外移 canvas-agent-session-panel.js（第六刀）。会话状态读走 getter、写走 setter 回主文件。
if(globalThis.CanvasAgentSessionPanel){CanvasAgentSessionPanel.configure({
        canvasAgentHistoryList: (...a) => canvasAgentHistoryList(...a),
        canvasAgentSerializableMessages: (...a) => canvasAgentSerializableMessages(...a),
        escapeHtml: (...a) => escapeHtml(...a),
        loadCanvasAgentHistoryIndex: (...a) => loadCanvasAgentHistoryIndex(...a),
        loadCanvasAgentHistoryList: (...a) => loadCanvasAgentHistoryList(...a),
        persistCanvasAgentHistoryStore: (...a) => persistCanvasAgentHistoryStore(...a),
        persistCanvasAgentSession: (...a) => persistCanvasAgentSession(...a),
        renderCanvasAgentMessages: (...a) => renderCanvasAgentMessages(...a),
        renderCanvasAgentRefs: (...a) => renderCanvasAgentRefs(...a),
        restoreCanvasAgentActionPlans: (...a) => restoreCanvasAgentActionPlans(...a),
        saveCanvasAgentHistoryList: (...a) => saveCanvasAgentHistoryList(...a),
        uid: (...a) => uid(...a),
        canvas: () => canvas,
        canvasId: () => canvasId,
        canvasAgentHistoryPanel: () => canvasAgentHistoryPanel,
        canvasAgentInput: () => canvasAgentInput,
        canvasAgentHistoryOpen: () => canvasAgentHistoryOpen,
        canvasAgentSessionId: () => canvasAgentSessionId,
        canvasAgentMessagesState: () => canvasAgentMessagesState,
        canvasAgentRefsState: () => canvasAgentRefsState,
        canvasAgentLastReply: () => canvasAgentLastReply,
        canvasAgentLastReplyRefs: () => canvasAgentLastReplyRefs,
        canvasAgentMentionPoolSnapshot: () => canvasAgentMentionPoolSnapshot,
        setCanvasAgentHistoryOpen: v => { canvasAgentHistoryOpen = v; },
        setCanvasAgentSessionId: v => { canvasAgentSessionId = v; },
        setCanvasAgentMessagesState: v => { canvasAgentMessagesState = v; },
        setCanvasAgentRefsState: v => { canvasAgentRefsState = v; },
        setCanvasAgentLastReply: v => { canvasAgentLastReply = v; },
        setCanvasAgentLastReplyRefs: v => { canvasAgentLastReplyRefs = v; },
        setCanvasAgentMentionPoolSnapshot: v => { canvasAgentMentionPoolSnapshot = v; }
});}
function closeCanvasAgentHistory(){return CanvasAgentSessionPanel.closeCanvasAgentHistory.apply(null, arguments);}
function renderCanvasAgentHistory(){return CanvasAgentSessionPanel.renderCanvasAgentHistory.apply(null, arguments);}
function toggleCanvasAgentHistory(){return CanvasAgentSessionPanel.toggleCanvasAgentHistory.apply(null, arguments);}
function loadCanvasAgentSession(){return CanvasAgentSessionPanel.loadCanvasAgentSession.apply(null, arguments);}
function deleteCanvasAgentSession(){return CanvasAgentSessionPanel.deleteCanvasAgentSession.apply(null, arguments);}
function newCanvasAgentSession(){return CanvasAgentSessionPanel.newCanvasAgentSession.apply(null, arguments);}
function resizeCanvasAgentInput(){return CanvasAgentSessionPanel.resizeCanvasAgentInput.apply(null, arguments);}
function canvasAgentHistoryForRequest(){
    return canvasAgentSerializableMessages(canvasAgentMessagesState.slice(0, -1))
        .filter(msg => msg.role === 'user' || msg.role === 'assistant')
        .slice(-10)
        .map(msg => ({role:msg.role, content:canvasAgentTrimText(msg.text, 900)}));
}
function canvasAgentTrimText(value='', max=900){
    const text = String(value || '').replace(/\s+/g, ' ').trim();
    return text.length > max ? `${text.slice(0, max)}...` : text;
}
function canvasAgentRequestMessage(messageText, attachSummary='', history=[], fileTranscript=''){
    const historyLines = (history || [])
        .filter(msg => msg.content)
        .map(msg => `${msg.role === 'user' ? '用户' : 'Agent'}：${msg.content}`)
        .join('\n');
    const parts = [];
    if(historyLines) parts.push(`以下是本轮对话历史，请延续上下文回答：\n${historyLines}`);
    parts.push(`用户当前请求：${messageText}`);
    if(attachSummary) parts.push(`当前引用的画布资源：\n${attachSummary}`);
    if(fileTranscript) parts.push(`以下是引用文件的内容，请先学习再回答：\n${fileTranscript}`);
    return parts.join('\n\n');
}
function canvasAgentRequestMessageForLocalCodex(messageText, attachSummary='', fileTranscript=''){
    const parts = [String(messageText || '').trim()];
    if(attachSummary) parts.push(`当前引用的画布资源：\n${attachSummary}`);
    if(fileTranscript) parts.push(`以下是引用文件的内容，请先学习再回答：\n${fileTranscript}`);
    return parts.filter(Boolean).join('\n\n');
}
function canvasAgentAttachmentSummary(refs){
    if(!refs.length) return '';
    return refs.map((ref, index) => `引用${index + 1}: ${canvasAgentMediaLabel(ref, index)} (${mediaKindForItem(ref)})`).join('\n');
}
function canvasAgentCodexProvider(){
    const entry = canvasAgentActiveEntry() || {};
    const providerId = entry.provider_id || configuredAgentProviderId();
    const fallbackModel = entry.model || configuredAgentFallbackModel();
    const provider = (apiProviders || []).find(p => p.id === providerId && p.enabled !== false);
    if(provider) return provider;
    const chatModels = Array.isArray(entry.chat_models) && entry.chat_models.length
        ? entry.chat_models
        : [fallbackModel, 'deepseek-v4-flash', 'deepseek-v4-pro', 'deepseek-chat', 'deepseek-reasoner'].filter(Boolean);
    return {
        id:providerId || '',
        name:entry.name || 'Myrid-Agent',
        protocol:'openai',
        enabled:true,
        has_key:Boolean(entry.has_key),
        chat_models:chatModels
    };
}
function canvasAgentUsesLocalCodex(){
    const entry = canvasAgentActiveEntry() || {};
    return String(entry.upstream_base_url || '').trim().toLowerCase().replace(/\/+$/, '') === 'codex://local';
}
function canvasAgentChatProviders(){
    const provider = canvasAgentCodexProvider();
    return provider ? [provider] : [];
}
function resolveCanvasAgentChatProvider(){
    return canvasAgentCodexProvider();
}
function resolveCanvasAgentChatModel(provider){
    const models = [...new Set(provider?.chat_models || [])];
    const configured = canvasAgentConfiguredChatModel(canvasAgentActiveEntry(), provider);
    if(configured && (!models.length || models.includes(configured))) return configured;
    const preferredPattern = configuredAgentModelPattern();
    const match = models.find(model => preferredPattern ? preferredPattern.test(model) : false);
    return match || models[0] || configured || configuredAgentFallbackModel();
}
function setCanvasAgentBusy(busy){
    canvasAgentSending = Boolean(busy);
    if(canvasAgentSend){
        canvasAgentSend.disabled = false;
        canvasAgentSend.title = canvasAgentSending ? '停止生成' : '发送';
        canvasAgentSend.setAttribute('aria-label', canvasAgentSending ? '停止生成' : '发送');
    }
    if(!canvasAgentSending){
        canvasAgentAbortController = null;
        canvasAgentActiveRequestId = null;
    }
    canvasAgentPanel?.classList.toggle('is-sending', canvasAgentSending);
}
function stopCanvasAgentGeneration(){
    if(!canvasAgentSending) return;
    if(canvasAgentActiveRequestId){
        try {
            fetch(`${RH_OFFICIAL_PROXY_BASE}/api/canvas-llm-stop`, {
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({request_id:canvasAgentActiveRequestId})
            }).catch(() => {});
        } catch(_) {}
    }
    if(canvasAgentAbortController) canvasAgentAbortController.abort();
}
async function waitForCanvasAgentProxy(timeoutMs=6500){
    if(!shouldUseCanvasLLMProxy({provider:configuredAgentProviderId(), model:configuredAgentFallbackModel()})) return true;
    const started = Date.now();
    let lastError = null;
    while(Date.now() - started < timeoutMs){
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 1800);
        try {
            const response = await fetch(`${RH_OFFICIAL_PROXY_BASE}/health?v=${Date.now()}`, {
                cache:'no-store',
                signal:controller.signal
            });
            if(response.ok){
                const data = await response.json().catch(() => ({}));
                if(data?.ok) return true;
            }
            lastError = new Error(`代理健康检查失败：HTTP ${response.status}`);
        } catch(error) {
            lastError = error;
        } finally {
            clearTimeout(timer);
        }
        await sleep(500);
    }
    const detail = String(lastError?.message || lastError || '').slice(0, 120);
    throw new Error(`Agent 本地代理未启动或无响应${detail ? `：${detail}` : ''}`);
}
async function fetchCanvasAgentLLM(payload, timeoutMs=480000, externalSignal){
    const endpoints = canvasLLMEndpointsForPayload(payload);
    let lastError = null;
    for(const endpoint of endpoints){
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeoutMs);
        let userStopped = false;
        const onExternalAbort = () => { userStopped = true; controller.abort(); };
        if(externalSignal){
            if(externalSignal.aborted) onExternalAbort();
            else externalSignal.addEventListener('abort', onExternalAbort);
        }
        try {
            const response = await fetch(endpoint, {
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify(payload),
                signal:controller.signal
            });
            if(!response.ok) throw new Error(await smartResponseErrorMessage(response, 'Agent 请求失败'));
            return response.json();
        } catch(error) {
            if(userStopped) lastError = Object.assign(new Error('已停止生成'), {userStopped:true});
            else lastError = error?.name === 'AbortError' ? new Error(`上游模型请求超时(${Math.round(timeoutMs / 1000)}s)`) : error;
        } finally {
            clearTimeout(timer);
            if(externalSignal) externalSignal.removeEventListener('abort', onExternalAbort);
        }
    }
    throw lastError || new Error('Agent 请求失败');
}
function shouldUseCanvasLLMProxy(payload={}){
    const provider = String(payload.provider || payload.provider_id || '').trim();
    const model = String(payload.model || '').trim();
    return provider === configuredAgentProviderId() || (configuredAgentModelPattern() && configuredAgentModelPattern().test(model));
}
function canvasLLMEndpointForPayload(payload={}){
return shouldUseCanvasLLMProxy(payload) ? `${RH_OFFICIAL_PROXY_BASE}/api/canvas-llm` : '/api/canvas-llm';
}
function canvasLLMEndpointsForPayload(payload={}){
const primary = canvasLLMEndpointForPayload(payload);
return [primary];
}
function comfyProxyUrl(path=''){
const suffix = String(path || '');
return `${RH_OFFICIAL_PROXY_BASE}${suffix.startsWith('/') ? suffix : `/${suffix}`}`;
}
function canvasAgentFriendlyError(error){
    const raw = String(error?.message || error || 'Agent 请求失败');
    if(/本地代理未启动|ERR_CONNECTION_REFUSED|Failed to fetch|NetworkError|Could not connect|拒绝连接|无响应/i.test(raw)){
        return 'Agent 本地代理没有启动或无响应。请从桌面重新启动 MyridTV，本次对话已保留。';
    }
    if(/504|gateway time-?out|timed?\s*out|超时/i.test(raw)){
        return '上游模型超时，请稍后重试或切换 API。历史对话已保留。';
    }
    return raw.slice(0, 220);
}
function canvasAgentRefNodeIds(refs=[]){
    const ids = [];
    const seen = new Set();
    (refs || []).forEach(ref => {
        let id = ref?.nodeId || '';
        if(!id && ref?.url){
            id = nodes.find(node => (node.images || []).some(img => img.url === ref.url))?.id || '';
        }
        if(id && nodes.some(node => node.id === id) && !seen.has(id)){
            seen.add(id);
            ids.push(id);
        }
    });
    return ids;
}
function connectCanvasAgentRefsToNode(refs=[], targetNode=null){
if(!targetNode) return 0;
let count = 0;
canvasAgentRefNodeIds(refs).forEach(id => {
if(connectInputNode(id, targetNode.id)) count += 1;
});
return count;
}
function canvasAgentSelectedNodes(){
const ids = selectedNodeIds();
return ids.map(id => nodes.find(node => node.id === id)).filter(Boolean);
}
function canvasAgentLowerText(value=''){
return String(value || '').toLowerCase();
}
function canvasAgentAssetText(asset={}){
const node = asset.nodeId ? nodes.find(item => item.id === asset.nodeId) : null;
const ref = asset.ref || {};
const image = node?.images?.[Number(ref.imageIndex)] || null;
return [
asset.name,
asset.title,
ref.name,
ref.title,
image?.name,
image?.title,
node?.title,
node?.promptDraftText,
node?.runPrompt
].map(value => String(value || '').trim()).filter(Boolean).join(' ');
}
function canvasAgentAssetAspect(asset={}){
const ref = asset.ref || {};
const node = asset.nodeId ? nodes.find(item => item.id === asset.nodeId) : null;
const image = node?.images?.[Number(ref.imageIndex)] || null;
const width = Number(ref.width || ref.natural_w || ref.naturalWidth || image?.width || image?.natural_w || image?.naturalWidth || node?.w || 0);
const height = Number(ref.height || ref.natural_h || ref.naturalHeight || image?.height || image?.natural_h || image?.naturalHeight || node?.h || 0);
if(width > 0 && height > 0) return width / height;
if(node){
const rect = nodeRect(node);
if(rect.width > 0 && rect.height > 0) return rect.width / rect.height;
}
return 1;
}
function canvasAgentAssetTags(asset={}, index=0, total=0){
const text = canvasAgentLowerText(canvasAgentAssetText(asset));
const tags = new Set();
if(/人物|角色|人像|肖像|面部|脸|女孩|女人|男人|男主|女主|portrait|character|person|face|girl|woman|man/.test(text)) tags.add('person');
if(/场景|环境|室内|室外|远景|全景|宫殿|房间|街道|森林|城市|背景参考|scene|environment|background|location|wide|establishing/.test(text)) tags.add('scene');
if(/道具|物件|物品|产品|皇冠|王冠|饰品|武器|服装|prop|object|product|crown|costume/.test(text)) tags.add('prop');
if(!tags.size){
const aspect = canvasAgentAssetAspect(asset);
if(total >= 3 && index === 0) tags.add('person');
else if(total >= 3 && index === total - 1) tags.add('scene');
else if(total >= 3) tags.add('prop');
else if(aspect < 0.85) tags.add('person');
else if(aspect > 1.45) tags.add('scene');
else tags.add('prop');
}
return [...tags];
}
function canvasAgentSourceAssets(refs=[], sourceNodes=[]){
const byId = new Map();
(refs || []).forEach((ref, index) => {
const nodeId = String(ref?.nodeId || '').trim();
if(!nodeId || byId.has(nodeId) || !nodes.some(node => node.id === nodeId)) return;
const node = nodes.find(item => item.id === nodeId);
byId.set(nodeId, {nodeId, ref:{...ref}, name:ref.name || node?.title || `素材 ${index + 1}`, index});
});
(sourceNodes || []).forEach((node, index) => {
if(!node?.id || byId.has(node.id)) return;
const image = (node.images || [])[0] || {};
byId.set(node.id, {nodeId:node.id, ref:{...image, nodeId:node.id, imageIndex:0}, name:node.title || image.name || `素材 ${index + 1}`, index});
});
const list = [...byId.values()];
return list.map((asset, index) => ({...asset, tags:canvasAgentAssetTags(asset, index, list.length), text:canvasAgentAssetText(asset)}));
}
function canvasAgentShotRequiredTags(text=''){
const value = canvasAgentLowerText(text);
const tags = new Set();
if(/人物|角色|人像|肖像|面部|脸|眼神|表情|特写|半身|全身|站位|动作|女主|男主|portrait|character|person|face|close[-\s]?up|medium shot|full body/.test(value)) tags.add('person');
if(/场景|环境|大远景|远景|全景|建立镜头|空间|宫殿|房间|街道|森林|城市|室内|室外|scene|environment|location|wide shot|long shot|establishing/.test(value)) tags.add('scene');
if(/道具|物件|物品|产品|皇冠|王冠|饰品|武器|服装|手持|prop|object|product|crown|costume|weapon/.test(value)) tags.add('prop');
return tags;
}
function canvasAgentSourceIdsForShot(text='', sourceAssets=[]){
const assets = Array.isArray(sourceAssets) ? sourceAssets.filter(asset => asset?.nodeId) : [];
if(!assets.length) return [];
const required = canvasAgentShotRequiredTags(text);
let matched = assets.filter(asset => (asset.tags || []).some(tag => required.has(tag))).map(asset => asset.nodeId);
if(!matched.length){
const value = canvasAgentLowerText(text);
matched = assets.filter(asset => {
const label = canvasAgentLowerText([asset.name, asset.text].filter(Boolean).join(' '));
return label && label.length >= 2 && value.includes(label.slice(0, Math.min(label.length, 12)));
}).map(asset => asset.nodeId);
}
if(!matched.length && assets.length === 1) matched = [assets[0].nodeId];
if(!matched.length && required.size) matched = [assets[0].nodeId];
return [...new Set(matched)];
}
function buildCanvasAgentStoryboardPlan(userText='', refs=[]){
if(!/(分镜|剧本|链路|镜头|剧情短片|storyboard|shot|sequence)/i.test(String(userText || ''))) return null;
const selected = canvasAgentSelectedNodes();
const refNodeIds = canvasAgentRefNodeIds(refs);
const sourceNodes = selected.length ? selected : refNodeIds.map(id => nodes.find(node => node.id === id)).filter(Boolean);
if(!sourceNodes.length) return null;
const sourceAssets = canvasAgentSourceAssets(refs, sourceNodes);
const maxX = Math.max(...sourceNodes.map(node => (Number(node.x) || 0) + (Number(node.w) || 260)));
const minY = Math.min(...sourceNodes.map(node => Number(node.y) || 0));
const intent = String(userText || '').trim();
const steps = sourceNodes.map((node, index) => {
const title = `镜头 ${index + 1}`;
const text = [
`# ${title}`,
`来源：${node.title || node.type || node.id}`,
intent ? `任务：${intent}` : '任务：根据来源素材整理为可生成的剧本/分镜描述。',
'画面：保留主体、风格和关键视觉信息，补充镜头、动作、光线、构图和情绪。',
'生成提示：请根据该镜头继续细化可执行的图像或视频生成提示词。'
].join('\n');
return {type:'create_image_node', sourceIds:[node.id], title, text, x:maxX + 80, y:minY + index * 236};
});
return {id:uid('agent_plan'), type:'storyboard_chain', title:'整理成分镜/剧本链路', sourceIds:sourceNodes.map(node => node.id), sourceAssets, baseX:maxX + 80, baseY:minY, steps, connectSequential:false, createdAt:Date.now()};
}
function splitCanvasAgentStoryboardSections(reply=''){
const text = String(reply || '').replace(/\r/g, '').trim();
if(!text) return [];
let matches = [...text.matchAll(/(?:^|\n)\s*(?:#{1,6}\s*)?(?:镜头|分镜|Shot)\s*([0-9一二三四五六七八九十]+)[^\n]*/gi)];
if(!matches.length && /镜头|分镜|shot/i.test(text)){
matches = [...text.matchAll(/(?:^|\n)\s*(?:#{1,6}\s*)?(?:第?\s*)?([0-9]{1,2})[.、）)]\s+[^\n]+/g)];
}
if(!matches.length) return [];
return matches.map((match, index) => {
const start = match.index + (match[0].startsWith('\n') ? 1 : 0);
const end = index + 1 < matches.length ? matches[index + 1].index : text.length;
const block = text.slice(start, end).trim();
const lines = block.split('\n');
const rawTitle = (lines[0] || `镜头 ${index + 1}`).replace(/^\s*#{1,6}\s*/, '').trim();
return {title:rawTitle || `镜头 ${index + 1}`, text:block};
}).filter(item => item.text).slice(0, 24);
}
function buildCanvasAgentStoryboardPlanFromReply(reply='', basePlan=null){
if(!basePlan) return null;
const sections = splitCanvasAgentStoryboardSections(reply);
if(!sections.length) return null;
const sourceIds = Array.isArray(basePlan.sourceIds) ? basePlan.sourceIds.filter(Boolean) : [];
const sourceAssets = Array.isArray(basePlan.sourceAssets) && basePlan.sourceAssets.length
? basePlan.sourceAssets
: sourceIds.map((nodeId, index) => ({nodeId, ref:{nodeId, imageIndex:0}, name:`素材 ${index + 1}`, index}));
const baseX = Number(basePlan.baseX) || Number(basePlan.steps?.[0]?.x) || 0;
const baseY = Number(basePlan.baseY) || Number(basePlan.steps?.[0]?.y) || 0;
const steps = sections.map((section, index) => ({
type:'create_image_node',
sourceIds:canvasAgentSourceIdsForShot(section.text, sourceAssets),
title:section.title || `镜头 ${index + 1}`,
text:section.text,
x:baseX,
y:baseY + index * 236
}));
return {...basePlan, id:uid('agent_plan'), title:`执行回复中的 ${steps.length} 个镜头`, steps, connectSequential:false, createdAt:Date.now()};
}
function canvasAgentActionPlanSummary(plan){
    if(!plan || !Array.isArray(plan.steps) || !plan.steps.length) return '没有可执行计划。';
    return [
        `将创建 ${plan.steps.length} 个图片生成节点。`,
        '将按每个镜头需要的人物、场景、道具资产连接来源图片。',
        '执行前会写入撤销记录。'
    ].filter(Boolean).join('\n');
}
const CANVAS_AGENT_RATIO_OPTIONS = [
    ['square','1:1'], ['portrait','2:3'], ['landscape','3:2'],
    ['portrait43','3:4'], ['landscape43','4:3'],
    ['story','9:16'], ['wide','16:9'], ['ultrawide','21:9'], ['ultratall','9:21']
];
const CANVAS_AGENT_RATIO_TEXT = {square:'1:1', portrait:'2:3', landscape:'3:2', portrait43:'3:4', landscape43:'4:3', story:'9:16', wide:'16:9', ultrawide:'21:9', ultratall:'9:21'};
// Agent 模型目录+设置面板域外移 canvas-agent-model-settings.js（第十二刀）。canvasAgentActiveId 块内整写走 setter，其余跨域态 getter。
if(globalThis.CanvasAgentModelSettings){CanvasAgentModelSettings.configure({
        canvasAgentActiveEntry: (...a) => canvasAgentActiveEntry(...a),
        canvasAgentChatProviders: (...a) => canvasAgentChatProviders(...a),
        canvasAgentConfiguredChatModel: (...a) => canvasAgentConfiguredChatModel(...a),
        canvasAgentEntry: (...a) => canvasAgentEntry(...a),
        canvasAgentLoadPreset: (...a) => canvasAgentLoadPreset(...a),
        canvasAgentRefreshHeadTitle: (...a) => canvasAgentRefreshHeadTitle(...a),
        canvasAgentRegistry: (...a) => canvasAgentRegistry(...a),
        configuredAgentProviderId: (...a) => configuredAgentProviderId(...a),
        escapeHtml: (...a) => escapeHtml(...a),
        imageProviders: (...a) => imageProviders(...a),
        providerModelDisplayName: (...a) => providerModelDisplayName(...a),
        render: (...a) => render(...a),
        CANVAS_AGENT_RATIO_OPTIONS: () => CANVAS_AGENT_RATIO_OPTIONS,
        CANVAS_AGENT_RATIO_TEXT: () => CANVAS_AGENT_RATIO_TEXT,
        SIZE_MAP: () => SIZE_MAP,
        apiProviders: () => apiProviders,
        canvasAgentModelPreset: () => canvasAgentModelPreset,
        comfyWorkflows: () => comfyWorkflows,
        engineSelect: () => engineSelect,
        canvasAgentActiveId: () => canvasAgentActiveId,
        setCanvasAgentActiveId: v => { canvasAgentActiveId = v; }
});}
function canvasAgentGenModelsFor(){return CanvasAgentModelSettings.canvasAgentGenModelsFor.apply(null, arguments);}
function canvasAgentGenModelLabel(){return CanvasAgentModelSettings.canvasAgentGenModelLabel.apply(null, arguments);}
function canvasAgentChatModelsFor(){return CanvasAgentModelSettings.canvasAgentChatModelsFor.apply(null, arguments);}
function canvasAgentLlmProviders(){return CanvasAgentModelSettings.canvasAgentLlmProviders.apply(null, arguments);}
function enhanceAgentSelects(){return CanvasAgentModelSettings.enhanceAgentSelects.apply(null, arguments);}
function renderCanvasAgentSettingsPanel(){return CanvasAgentModelSettings.renderCanvasAgentSettingsPanel.apply(null, arguments);}
function collectCanvasAgentSettings(){return CanvasAgentModelSettings.collectCanvasAgentSettings.apply(null, arguments);}
function toggleCanvasAgentSettings(){return CanvasAgentModelSettings.toggleCanvasAgentSettings.apply(null, arguments);}
function buildCanvasAgentGenerationPreset(){return CanvasAgentModelSettings.buildCanvasAgentGenerationPreset.apply(null, arguments);}
const CANVAS_AGENT_BS_STAGES = ['方向探索','深化','确认','落地'];
function canvasAgentParseBrainstormReply(text){
    let raw = String(text || '').trim();
    if(!raw) return null;
    const fence = raw.match(/```(?:json)?\s*([\s\S]*?)```/);
    if(fence) raw = fence[1].trim();
    const tryParse = s => {
        try{
            const o = JSON.parse(s);
            if(o && typeof o === 'object' && (Array.isArray(o.candidates) || o.stage)) return o;
        }catch(_){}
        return null;
    };
    let obj = tryParse(raw);
    if(obj) return obj;
    const start = raw.indexOf('{');
    const end = raw.lastIndexOf('}');
    if(start >= 0 && end > start){
        obj = tryParse(raw.slice(start, end + 1));
        if(obj) return obj;
    }
    // 模型无关兜底：从 A./B./C.（或 1./2./3.）并列的文本方案里提取候选。
    // 这样无论走 DeepSeek/Codex/本地模型，只要按 reply_rules 的 A. B. C. 编号输出，前端都能转成候选卡片。
    const lines = String(text || '').split(/\r?\n/).map(l => l.trim()).filter(Boolean)
    const itemRe = /^(?:[A-Da-d]\s*[\.、:：)]|第[一二三四五1-4]个|方案\s*[A-Da-d]|\[?[A-Da-d]\]\s*)[\s]*([\s\S]*)$/;
    let items = [];
    let cur = null;
    for(const line of lines){
        const m = line.match(itemRe);
        if(m){
            if(cur) items.push(cur);
            cur = { raw: m[1], desc: m[1] };
        } else if(cur){
            cur.raw += ' ' + line;
            cur.desc += ' ' + line;
        }
    }
    if(cur) items.push(cur);
    // 至少 2 个并列项才算候选
    if(items.length >= 2){
        const candidates = items.map((it, i) => {
            const letters = ['A','B','C','D'];
            const title = it.raw.split(/[——:：]/)[0].trim().slice(0, 24) || ('方案' + letters[i]);
            return { id: letters[i], title: title, desc: it.desc.slice(0, 80), prompt: it.raw.slice(0, 120), tags: [] };
        });
        return { stage: '方向探索', step: '', question: '请选择其中一个方向', candidates: candidates, decisions: [], done: false };
    }
    return null;
}
function canvasAgentBrainstormCardHtml(card, message) {
    return CanvasAgentMessageRender.canvasAgentBrainstormCardHtml.apply(null, arguments);
}
function renderCanvasAgentBrainstormBar(){
    const bar = document.getElementById('canvasAgentBrainstormBar');
    if(!bar || !canvasAgentBrainstormState) return;
    const stage = canvasAgentBrainstormState.stage || '方向探索';
    const cur = CANVAS_AGENT_BS_STAGES.indexOf(stage);
    bar.querySelectorAll('.canvas-agent-bs-stage').forEach(el => {
        const idx = CANVAS_AGENT_BS_STAGES.indexOf(el.dataset.bsStage);
        el.classList.toggle('done', cur >= 0 && idx < cur);
        el.classList.toggle('current', idx === cur);
    });
    const decisionsEl = document.getElementById('canvasAgentBsDecisions');
    if(decisionsEl){
        decisionsEl.innerHTML = (canvasAgentBrainstormState.decisions || []).map(d =>
            `<span class="canvas-agent-bs-decision">${escapeHtml(String(d.key || ''))}：${escapeHtml(String(d.value || ''))}</span>`
        ).join('');
    }
}
function toggleCanvasAgentBrainstorm(){
    if(canvasAgentBrainstormState){
        canvasAgentBrainstormState = null;
        const bar = document.getElementById('canvasAgentBrainstormBar');
        if(bar) bar.hidden = true;
        if(canvasAgentBrainstormBtn) canvasAgentBrainstormBtn.classList.remove('active');
        toast('已退出头脑风暴');
    }else{
        canvasAgentBrainstormState = {stage:'方向探索', decisions:[], done:false};
        renderCanvasAgentBrainstormBar();
        const bar = document.getElementById('canvasAgentBrainstormBar');
        if(bar) bar.hidden = false;
        if(canvasAgentBrainstormBtn) canvasAgentBrainstormBtn.classList.add('active');
        toast('头脑风暴已开启：描述你的起点（一句想法、Brief 或 @引用画布素材）');
    }
}
function sendCanvasAgentBrainstormChoice(kind='pick', id='', title=''){
    if(kind === 'pick' && id){
        const lastCard = [...canvasAgentMessagesState].reverse().find(m => m.brainstormCard && !m.brainstormLocked);
        if(!lastCard){
            toast('该组候选已处理，无需重复选择');
            return;
        }
        // 头脑风暴模式：直接建生成节点；非头脑风暴（默认候选交互）：把选择发回大模型推进流程，不本地建节点
        const isBrainstormMode = !!canvasAgentBrainstormState;
        if(!isBrainstormMode){
            // 默认候选交互：只锁定卡片标记已选，选择作为新消息发给大模型继续主链流程
            lastCard.brainstormLocked = true;
            lastCard.brainstormChosenId = String(id);
            canvasAgentChosenMap[lastCard.id] = String(id);
            renderCanvasAgentMessages();
            persistCanvasAgentSession();
            if(canvasAgentInput) canvasAgentInput.value = `选${String(id)}`;
            sendCanvasAgentMessage();
            return;
        }
        const candidates = Array.isArray(lastCard.brainstormCard.candidates) ? lastCard.brainstormCard.candidates : [];
        const chosenCandidate = candidates.find(c => String(c.id || c.title || '') === String(id)) || candidates[0] || null;
        // 头脑风暴模式：本地直接建生成节点
        const created = canvasAgentCreateBrainstormNodes(chosenCandidate ? [chosenCandidate] : [], title);
        lastCard.brainstormLocked = true;
        lastCard.brainstormChosenId = String(id);
        lastCard.brainstormNodeIds = created.map(n => n.id);
        canvasAgentChosenMap[lastCard.id] = String(id);
        renderCanvasAgentMessages();
        scheduleSave();
        persistCanvasAgentSession();
        toast(`已选择${id}，已在画布创建 ${created.length} 个生成节点`);
        return;
    }
    // 换一批：仍需问大模型
    const text = '都不太行，请换一批完全不同的候选方向。';
    if(canvasAgentInput) canvasAgentInput.value = text;
    sendCanvasAgentMessage();
}
function canvasAgentCreateBrainstormNodes(candidates=[], chosenTitle=''){
    const created = [];
    if(!Array.isArray(candidates) || !candidates.length) return created;
    const agentPreset = canvasAgentModelPreset || canvasAgentLoadPreset();
    const gen = buildCanvasAgentGenerationPreset(agentPreset, 't2i');
    const genProvider = String(gen.provider_id || '');
    const genEngine = genProvider === 'comfy' ? 'comfyui'
        : genProvider === 'runninghub' ? 'runninghub'
        : genProvider === 'volcengine' ? 'volcengine'
        : 'api';
    const ratioKey = (agentPreset && agentPreset.ratio) || 'landscape43';
    const center = viewportCenter();
    const w = 316, h = 194, gap = 40;
    const totalW = (w + gap) * candidates.length - gap;
    let startX = Math.round(center.x - totalW / 2);
    let baseY = Math.round(center.y - h / 2) - 120;
    pushUndo();
    candidates.forEach((c, i) => {
        const cid = String(c.id || c.title || ('选项' + (i + 1)));
        const prompt = String(c.prompt || c.desc || c.title || '').trim();
        const spot = agentFindEmptySpot(startX + i * (w + gap), baseY, w, h);
        const node = createSmartGeneratorNode({x:spot.x + w / 2, y:spot.y + h / 2}, {skipUndo:true, select:false, engine:genEngine, apiKind:'image', title:cid + (c.title ? ' ' + c.title : '')});
        node.runPrompt = prompt;
        try{ setPromptDraftForNode(node, prompt); }catch(_){}
        node.runSettings = settingsForStorage({
            ...cloneSmartSettings(node.runSettings || {}),
            engine: genEngine,
            apiKind: 'image',
            provider_id: genProvider,
            model: gen.model || (node.runSettings && node.runSettings.model) || '',
            ratio: ratioKey,
            resolution: gen.resolution || (node.runSettings && node.runSettings.resolution) || '2k',
            quality: gen.quality || (node.runSettings && node.runSettings.quality) || 'medium'
        });
        node.__origin = 'agent_brainstorm';
        node.role = 'generation';
        node.status = 'pending';
        created.push(node);
    });
    if(created.length){
        canvasUiState.patchSelection({ids: created.map(n => n.id)}, 'selectedIds');
        canvasUiState.patchSelection({primaryId: created.length === 1 ? created[0].id : ''}, 'selectedId');
        render();
    }
    return created;
}
async function canvasAgentRunBrainstormNodes(messageId=''){
    const msg = messageId ? canvasAgentMessagesState.find(m => m.id === messageId) : null;
    const nodeIds = Array.isArray(msg?.brainstormNodeIds) ? msg.brainstormNodeIds : [];
    const targets = nodeIds.map(id => (nodes || []).find(n => n.id === id)).filter(canvasAgentPendingGenNode);
    if(!targets.length){
        toast('未找到待执行的生成节点');
        return;
    }
    msg.brainstormExecuted = true;
    renderCanvasAgentMessages();
    // 候选节点全部并行生成（各用自身 runPrompt），不再借道 composer 逐个 runGeneration
    await canvasAgentBatchRunNodes(targets);
    if(msg) renderCanvasAgentMessages();
}
function canvasAgentCopyMessageText(messageId){
    const msg = canvasAgentMessagesState.find(m => m.id === messageId);
    const text = String(msg?.text || '').trim();
    if(!text){ toast('没有可复制的内容'); return; }
    const done = () => toast('已复制回复内容');
    if(navigator.clipboard && navigator.clipboard.writeText){
        navigator.clipboard.writeText(text).then(done).catch(() => { canvasAgentFallbackCopy(text); done(); });
    } else {
        canvasAgentFallbackCopy(text);
        done();
    }
}
function canvasAgentEditMessage(messageId){
    const msg = canvasAgentMessagesState.find(m => m.id === messageId);
    if(!msg || msg.role !== 'user') return;
    const text = String(msg.text || '').trim();
    if(!text){ toast('没有可编辑的内容'); return; }
    if(canvasAgentSending){ toast('正在生成中，请先停止'); return; }
    // 原地编辑：不删消息、不动输入框，气泡内展开编辑框，修改后原地重发
    canvasAgentEditingId = messageId;
    renderCanvasAgentMessages();
    const textarea = canvasAgentMessages?.querySelector(`[data-agent-editing-textarea="${messageId}"]`);
    if(textarea){
        textarea.value = text;
        textarea.focus();
        textarea.selectionStart = textarea.selectionEnd = text.length;
    }
}
function canvasAgentCancelEditMessage(){
    canvasAgentEditingId = '';
    renderCanvasAgentMessages();
}
function canvasAgentResendEditedMessage(messageId, newText){
    const msg = canvasAgentMessagesState.find(m => m.id === messageId);
    if(!msg || msg.role !== 'user') return;
    const text = String(newText || '').trim();
    if(!text){ toast('编辑内容不能为空'); return; }
    if(canvasAgentSending){ toast('正在生成中，请先停止'); return; }
    // Hermes 式重发：更新该条消息文本，删除其后所有对话轮次（到下一个 user 消息前的 assistant 回复），
    // 然后用该文本直接发起新请求——不新建 user 消息、不经过输入框
    const idx = canvasAgentMessagesState.findIndex(m => m.id === messageId);
    if(idx < 0) return;
    const keep = canvasAgentMessagesState.slice(0, idx + 1);
    canvasAgentMessagesState.length = 0;
    canvasAgentMessagesState.push(...keep);
    msg.text = text;
    msg.createdAt = Date.now();
    canvasAgentEditingId = '';
    canvasAgentRefsState = [];
    canvasAgentMentionPoolSnapshot = []; // 编号表随引用条一起清空
    renderCanvasAgentMessages();
    persistCanvasAgentSession();
    canvasAgentResendFromMessage(msg);
}
function canvasAgentResendFromMessage(msg){
    if(!msg) return;
    sendCanvasAgentMessage(msg);
}
function canvasAgentUserEditHtml(message) {
    return CanvasAgentMessageRender.canvasAgentUserEditHtml.apply(null, arguments);
}
function canvasAgentFallbackCopy(text){
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try{ document.execCommand('copy'); }catch(_){}
    document.body.removeChild(ta);
}
function canvasAgentQuoteMessageText(messageId){
    const msg = canvasAgentMessagesState.find(m => m.id === messageId);
    const text = String(msg?.text || '').trim();
    if(!text || !canvasAgentInput){ toast('没有可引用的内容'); return; }
    canvasAgentQuoteState = {messageId, text};
    renderCanvasAgentQuoteCard();
}
function renderCanvasAgentQuoteCard(){
    const card = document.getElementById('canvasAgentQuoteCard');
    if(!card) return;
    if(!canvasAgentQuoteState){
        card.hidden = true;
        card.innerHTML = '';
        return;
    }
    const text = canvasAgentQuoteState.text;
    const short = text.length > 90 ? text.slice(0, 90) + '…' : text;
    card.hidden = false;
    card.innerHTML = `<span class="canvas-agent-quote-card-label">引用</span><span class="canvas-agent-quote-card-text">${escapeHtml(short)}</span><button class="canvas-agent-quote-card-close" type="button" title="取消引用" data-agent-quote-clear="1"><i data-lucide="x"></i></button>`;
    card.querySelector('[data-agent-quote-clear]')?.addEventListener('click', e => {
        e.preventDefault();
        e.stopPropagation();
        canvasAgentQuoteState = null;
        renderCanvasAgentQuoteCard();
    });
    if(window.lucide) lucide.createIcons();
}
function canvasAgentLocateMessageNode(messageId){
    const msg = canvasAgentMessagesState.find(m => m.id === messageId);
    let target = null;
    if(Array.isArray(msg?.nodeIds) && msg.nodeIds.length){
        target = msg.nodeIds.map(id => (nodes || []).find(n => n.id === id)).find(Boolean) || null;
    }
    if(msg?.actionPlan && Array.isArray(msg.actionPlan.steps)){
        const stepNode = msg.actionPlan.steps.find(s => s.nodeId && (nodes || []).some(n => n.id === s.nodeId));
        if(stepNode) target = (nodes || []).find(n => n.id === stepNode.nodeId);
    }
    if(!target){
        const agentNodes = (nodes || []).filter(n => String(n.id || '').startsWith('agent_'));
        target = agentNodes[agentNodes.length - 1] || null;
    }
    if(!target){
        toast('暂未找到该回复关联的画布节点');
        return;
    }
    const r = nodeRect(target);
    if(r){
        centerViewportOnWorldPoint({x: r.x + r.width / 2, y: r.y + r.height / 2});
        canvasUiState.patchSelection({primaryId: target.id}, 'selectedId');
        canvasUiState.patchSelection({ids: [target.id]}, 'selectedIds');
        render();
        toast(`已定位到节点：${target.title || target.id}`);
    }
}
function canvasAgentLocateSpecificNode(nodeId='', messageId=''){
    const targetId = String(nodeId || '').trim();
    let target = targetId ? (nodes || []).find(n => n.id === targetId) : null;
    if(!target && messageId){
        canvasAgentLocateMessageNode(messageId);
        return;
    }
    if(!target){
        toast('暂未找到该选项对应的画布节点');
        return;
    }
    const r = nodeRect(target);
    if(r){
        centerViewportOnWorldPoint({x: r.x + r.width / 2, y: r.y + r.height / 2});
        canvasUiState.patchSelection({primaryId: target.id}, 'selectedId');
        canvasUiState.patchSelection({ids: [target.id]}, 'selectedIds');
        render();
        toast(`已定位到节点：${target.title || target.id}`);
    }
}
function bindCanvasAgentBrainstormButtons(){
    if(!canvasAgentMessages) return;
    canvasAgentMessages.querySelectorAll('[data-bs-pick]').forEach(btn => {
        btn.onclick = e => {
            e.preventDefault();
            e.stopPropagation();
            sendCanvasAgentBrainstormChoice('pick', btn.dataset.bsPick, btn.dataset.bsTitle);
        };
    });
    canvasAgentMessages.querySelectorAll('[data-bs-refresh]').forEach(btn => {
        btn.onclick = e => {
            e.preventDefault();
            e.stopPropagation();
            sendCanvasAgentBrainstormChoice('refresh');
        };
    });
}
function canvasAgentPendingGenNode(n){
    // 「待生成」判据：节点没有「生成结果图」（generatedResult）。
    // 旧判据 !img?.url 会把 Agent 建节点时挂上的输入参考图当成已有输出，
    // 导致消息明明建了 3 个节点、执行时却挑不出目标或行为漂移。
    return Boolean(n && n.type === 'smart-image' && !(n.images || []).some(img => img?.generatedResult));
}
async function canvasAgentBatchRunNodes(targets){
    // 批量生成：各节点用「自己的 runPrompt」并行提交，绝不借道 composer 的 runGeneration。
    // 旧实现逐个 selectedId=节点 → runGeneration()：会改写 composer 草稿/选中态，
    // 且首个节点跑完出图后，后续若再回到该节点会被判成「覆盖重跑」，
    // 把刚生成的图压进历史、新图叠在同一节点上（用户 2026-09-23 报告的根因）。
    const apiItems = [];
    const otherNodes = [];
    for(const node of targets){
        const rs = smartSettingsForNode(node);
        const prompt = String(node.runPrompt || node.promptDraftText || '').trim();
        let refs = Array.isArray(node.runPromptRefs) ? node.runPromptRefs.filter(r => r && r.url) : [];
        if(!refs.length){
            // Agent 建的链式节点可能没存 runPromptRefs：回退用上游连线输入（与 composer 首跑同源）
            try{
                refs = defaultInputImagesFor(node, false)
                    .filter(img => img && img.url)
                    .map(img => ({url:img.url, name:img.name || '图片', nodeId:img.nodeId || '', imageIndex:img.imageIndex ?? '', kind:'image'}));
            }catch(_){ refs = []; }
        }
        const parallelOk = prompt && isApiLikeEngine(rs.engine) && rs.apiKind !== 'video';
        if(parallelOk) apiItems.push({node, rs:cloneSmartSettings(rs), prompt, refs});
        else otherNodes.push(node);
    }
    let okCount = 0, failCount = 0;
    const jobs = apiItems.map(async ({node, rs, prompt, refs}) => {
        const label = node.title || node.id;
        try{
            const result = await runApiGeneration(prompt, refs, rs, node);
            const taskIds = Array.isArray(result?.taskIds) ? result.taskIds.filter(Boolean) : [];
            if(!taskIds.length) throw new Error('提交生成任务失败');
            node.pendingTasks = taskIds.map(taskId => ({taskId, kind:'image'}));
            rememberSmartTaskIds(node, taskIds);
            node.pending = taskIds.length;
            node.apiRunning = true;
            node.runStartedAt = nowMs();
            delete node.runFinishedAt;
            delete node.runError;
            // 与 composer 首跑语义一致：回填前清掉挂在节点上的输入参考图，只留生成结果
            if(!(node.images || []).some(img => img?.generatedResult)) node.images = [];
            render();
            scheduleSave();
            // 与单节点「运行」共用同一条轮询/回填路径（含即梦排队、失败清理、apiRunning 复位）
            await resumeSmartPendingNode(node);
            if((node.images || []).some(img => img?.generatedResult)) okCount += 1;
            else failCount += 1;
            render();
            scheduleSave();
        }catch(e){
            node.apiRunning = false;
            node.runError = (e?.message || '生成失败').slice(0, 160);
            restoreNodeBoxAfterFailure(node); // 失败不改尺寸：拨回按比例的默认盒，别停在占位框
            failCount += 1;
            toast(`${label}：${node.runError}`);
            render();
        }
    });
    await Promise.all(jobs);
    // comfy / runninghub / 无自身提示词的节点：回退到逐个 runGeneration（这些引擎的提交流程依赖 composer 状态）
    for(const node of otherNodes){
        try{
            canvasUiState.patchSelection({primaryId: node.id}, 'selectedId');
            canvasUiState.patchSelection({ids: [node.id]}, 'selectedIds');
            render();
            await runGeneration();
            if((node.images || []).some(img => img?.generatedResult)) okCount += 1;
            else failCount += 1;
        }catch(e){
            failCount += 1;
            toast((e?.message || '生成失败').slice(0, 160));
        }
    }
    if(targets.length > 1 || apiItems.length){
        toast(`批量生成完成：成功 ${okCount} 个，失败 ${failCount} 个`);
    }
    scheduleSave();
    return {ok: okCount, failed: failCount};
}
async function canvasAgentExecuteRecentNodes(messageId=''){
    const msg = messageId ? canvasAgentMessagesState.find(m => m.id === messageId) : null;
    // 收集本轮对话应执行的全部待生成节点（该消息 nodeIds 里的 smart-image 且无生成结果）
    let targets = [];
    if(Array.isArray(msg?.nodeIds) && msg.nodeIds.length){
        targets = msg.nodeIds
            .map(id => (nodes || []).find(n => n.id === id))
            .filter(canvasAgentPendingGenNode);
    }
    // Phase 1 (P7): 移除"agent_ 前缀 + 无图"兜底自动执行。
    // 旧逻辑会把历史分组、pending、甚至垃圾节点也当成本轮节点批量执行，既烧配额又放大污染。
    // 现在只信任消息明确携带的 nodeIds。
    if(!targets.length){
        toast('未找到待执行的生成节点，请在画布中选择节点后点击运行');
        return;
    }
    await canvasAgentBatchRunNodes(targets);
    renderCanvasAgentMessages();
}
async function previewCanvasAgentActionPlan(plan, messageId){
    if(!plan || !Array.isArray(plan.steps) || !plan.steps.length){
        toast('当前回复没有可执行计划');
        return;
    }
    const btn = messageId ? document.querySelector(`[data-agent-preview-plan="${CSS.escape(String(messageId))}"]`) : null;
    const runBtn = messageId ? document.querySelector(`[data-agent-run="${CSS.escape(String(messageId))}"]`) : null;
    const setBtnText = (el, text, disabled) => {
        if(!el) return;
        el.disabled = disabled;
        const span = el.querySelector('span');
        if(span) span.textContent = text;
        const icon = el.querySelector('i');
        if(icon) icon.setAttribute('data-lucide', disabled ? 'check' : 'play');
    };
    setBtnText(btn, '执行中…', true);
    setBtnText(runBtn, '执行中…', true);
    try{
        await executeCanvasAgentActionPlan(plan);
        const msg = messageId ? canvasAgentMessagesState.find(item => item.id === messageId) : null;
        if(msg) msg.executed = true;
        renderCanvasAgentMessages();
    }catch(e){
        toast((e.message || '执行失败').slice(0, 160));
        setBtnText(btn, '执行', false);
        setBtnText(runBtn, '执行', false);
    }
}
function agentFindEmptySpot(x, y, w, h, step=36){
    const overlaps = (px, py) => (nodes || []).some(n => {
        const r = nodeRect(n);
        if(!r || !(r.width > 0) || !(r.height > 0)) return false;
        return px < r.x + r.width && px + w > r.x && py < r.y + r.height && py + h > r.y;
    });
    let px = Number(x) || 0;
    let py = Number(y) || 0;
    for(let i = 0; i < 240; i++){
        if(!overlaps(px, py)) return {x:px, y:py};
        py += step;
        if(i % 36 === 35){
            px += w + 32;
            py = Number(y) || 0;
        }
    }
    return {x:Number(x) || 0, y:Number(y) || 0};
}
async function executeCanvasAgentActionPlan(plan){
    if(!plan || !Array.isArray(plan.steps) || !plan.steps.length) return;
    // CanvasMutationManager 前端守卫：Agent 计划创建节点前必须先经过用户确认，避免 story-outline 等规划技能批量倾倒"垃圾节点"。
    const stepsToCreate = (plan.steps || []).filter(s => s.type === 'create_image_node');
    if(stepsToCreate.length > 3){
        const ok = confirm(`Agent 准备在此画布创建 ${stepsToCreate.length} 个节点。\n\n为避免生成提示词尚未就绪就提前落盘，请确认这些节点确实需要现在创建。\n\n点「取消」则本次不创建任何节点。`);
        if(!ok){
            toast('已取消创建节点');
            return;
        }
    }
    pushUndo();
    const created = [];
    // 纵向对齐、不重叠排布：同一列(相同 x)，按顺序递增 y，间距=节点高+固定空隙
    let cursorY = null;
    let baseX = 0;
    const ROW_GAP = 24;      // 相邻节点纵向空隙
    const DEFAULT_W = 316;
    const DEFAULT_H = 194;
    plan.steps.forEach(step => {
        if(step.type !== 'create_image_node') return;
        const prompt = extractCanvasAgentPrompt(step.text || '') || String(step.text || '').trim();
        // 额外守卫：尚未生成有效文生图提示词的图片节点禁止落盘
        if(step.type === 'create_image_node'){
            const hasRealPrompt = prompt && prompt.length >= 10 && /[a-zA-Z\u4e00-\u9fa5]/.test(prompt);
            if(!hasRealPrompt){
                console.warn('[CanvasMutationGuard] skipped image node with empty/invalid prompt:', step.title || '(untitled)');
                return;
            }
        }
        // 起点：第一步用 plan 给的首坐标，后续继承同一列
        if(cursorY === null){
            baseX = Number(step.x) || 0;
            cursorY = Number(step.y) || 0;
        }
        // 找不重叠的位置（在给定 x 列内纵向探空位，优先向下）
        const spot = agentFindEmptySpot(baseX, cursorY, DEFAULT_W, DEFAULT_H);
        cursorY = spot.y + DEFAULT_H + ROW_GAP;
        // Phase 8c：文档类产物交给 Artifact Router 决策（需求第三十一/三十二条）。
        // 默认 sidebar；用户明确说"放到画布"则 both（Sidebar 保留 + 建节点，共享 artifactId）。
        let sidebarArtifact = null;

        const node = createSmartGeneratorNode({x:spot.x + 158, y:spot.y + 97}, {skipUndo:true, select:false, engine:'api', apiKind:'image', title:step.title || '镜头生成'});
        if(step.type === 'create_image_node'){
            node.runPrompt = prompt;
            setPromptDraftForNode(node, prompt);
            // 模型自动判断：有输入引用→图生图预设，无→文生图预设（用户要求 2026-08-16）
            const agentPreset = canvasAgentModelPreset || canvasAgentLoadPreset();
            const hasRefs = (Array.isArray(step.sourceIds) && step.sourceIds.length > 0) || Boolean(step.sourceId);
            const isI2I = Boolean(hasRefs);
            const gen = buildCanvasAgentGenerationPreset(agentPreset, isI2I ? 'i2i' : 't2i');
            const genProvider = String(gen.provider_id || '');
            const genEngine = genProvider === 'comfy' ? 'comfyui'
                : genProvider === 'runninghub' ? 'runninghub'
                : genProvider === 'volcengine' ? 'volcengine'
                : 'api';
            const ratioKey = (isI2I ? agentPreset.gen2Ratio : agentPreset.ratio) || 'landscape43';
            node.runSettings = settingsForStorage({
                ...cloneSmartSettings(node.runSettings || {}),
                engine: genEngine,
                apiKind: 'image',
                provider_id: genProvider,
                model: gen.model || node.runSettings?.model || '',
                ratio: ratioKey,
                resolution: gen.resolution || node.runSettings?.resolution || '2k',
                quality: gen.quality || node.runSettings?.quality || 'medium'
            });
        }
        node.__origin = 'agent_action_plan';
        if(sidebarArtifact && sidebarArtifact.id){
            // Artifact 是 Source of Truth，Node 只是它的 Canvas Representation（需求第十四条）
            node.artifactId = sidebarArtifact.id;
            sidebarArtifact.canvasNodeId = node.id;
        }
        node.role = 'generation'; node.status = 'pending';
        created.push({node, step});
        const sourceIds = Array.isArray(step.sourceIds) ? step.sourceIds : [step.sourceId].filter(Boolean);
        sourceIds.filter(Boolean).forEach(sourceId => connectInputNode(sourceId, node.id));
    });
    if(plan.connectSequential){
        for(let i = 1; i < created.length; i += 1) connectInputNode(created[i - 1].node.id, created[i].node.id);
    }
    canvasUiState.patchSelection({ids: created.map(item => item.node.id)}, 'selectedIds');
    canvasUiState.patchSelection({primaryId: canvasUiState.selection.ids.length === 1 ? canvasUiState.selection.ids[0] : ''}, 'selectedId');
    render();
    scheduleSave();
    const imageNodes = created.filter(item => item.step.type === 'create_image_node');
    if(!imageNodes.length){
        toast(`已执行：创建 ${created.length} 个节点`);
        return;
    }
    toast(`已创建 ${created.length} 个节点，开始生成 ${imageNodes.length} 张图片…`);
    // 并行生成（各节点用自身 runPrompt），不再逐个借道 composer 的 runGeneration
    await canvasAgentBatchRunNodes(imageNodes.map(item => item.node));
}
async function canvasAgentSubmitInteractionReceipt({card_id='', intent='', selection=null, fields={}, confirmed=false}){
    if(!card_id) return;
    try{
        const resp = await fetch('/api/canvas-agent-interaction-receipt', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({
                session_id: canvasAgentSessionId || '',
                card_id,
                intent,
                selection,
                fields,
                confirmed,
            })
        });
        const data = await resp.json();
        if(data?.ok === false){ toast('回执失败：' + (data?.error || '')); return; }
        canvasAgentMessagesState.forEach(msg => {
            if(msg?.interaction && String(msg.interaction.card_id || '') === String(card_id || '')){
                msg.interaction.resolved = true;
            }
        });
        renderCanvasAgentMessages();
        // 构建要传给主链的消息文本：choose/confirm 用"我选择X"，collect 用字段汇总
        let nextText = '';
        if(intent === 'collect' && fields && Object.keys(fields).length){
            nextText = '参数已确认：' + Object.entries(fields).map(([k,v]) => `${k}=${v}`).join('，');
        } else {
            nextText = (data?.receipt_text && data.receipt_text !== '已收到。') ? data.receipt_text : ((selection ? `我选择 ${selection}` : '已确认'));
        }
        const pickValue = data?.receipt?.selection_label || data?.receipt?.selection || '';
        const pickLabel = pickValue ? `已选择：${pickValue}` : '已确认';
        toast(pickLabel);
        if(canvasAgentInput) canvasAgentInput.value = nextText;
        // "需要修改"（确认卡且未确认）：不自动往下生成，先让用户把具体修改意见告诉 Agent，主链停下收集
        if(intent === 'confirm' && !confirmed){
            // 追加一条用户消息"需要修改"，并把输入框聚焦让用户补充具体意见，不自动重发
            canvasAgentMessagesState.push({id:uid('agent_msg'), role:'user', text:'需要修改，请先别继续往下走。', sourceRefs:[], refs:[]});
            renderCanvasAgentMessages();
            if(canvasAgentInput){ canvasAgentInput.value = ''; canvasAgentInput.focus(); }
            toast('请告诉我想改哪里（节奏/人物/台词/结局等），我会修改后再给你确认');
            return;
        }
        // collect/confirm 由用户点提交/确认后触发推进；choose 由点选后触发
        if(intent === 'choose' || intent === 'confirm' || intent === 'collect'){
            setTimeout(() => { sendCanvasAgentMessage(); }, 120);
        }
    } catch(e){
        toast('提交回执失败：' + (e.message || e));
    }
}
// Agent 主发送链外移 canvas-agent-send-chain.js（第十三刀）。9 个会话态写入走 setter 回主文件真变量。
if(globalThis.CanvasAgentSendChain){CanvasAgentSendChain.configure({
        buildCanvasAgentGenerationPreset: (...a) => buildCanvasAgentGenerationPreset(...a),
        buildCanvasAgentStoryboardPlan: (...a) => buildCanvasAgentStoryboardPlan(...a),
        buildCanvasAgentStoryboardPlanFromReply: (...a) => buildCanvasAgentStoryboardPlanFromReply(...a),
        canvasAgentActiveEntry: (...a) => canvasAgentActiveEntry(...a),
        canvasAgentArtifactTranscript: (...a) => canvasAgentArtifactTranscript(...a),
        canvasAgentAttachmentSummary: (...a) => canvasAgentAttachmentSummary(...a),
        canvasAgentChatProviders: (...a) => canvasAgentChatProviders(...a),
        canvasAgentFileTranscript: (...a) => canvasAgentFileTranscript(...a),
        canvasAgentFormatLatency: (...a) => canvasAgentFormatLatency(...a),
        canvasAgentFriendlyError: (...a) => canvasAgentFriendlyError(...a),
        canvasAgentHistoryForRequest: (...a) => canvasAgentHistoryForRequest(...a),
        canvasAgentLoadPreset: (...a) => canvasAgentLoadPreset(...a),
        canvasAgentParseBrainstormReply: (...a) => canvasAgentParseBrainstormReply(...a),
        canvasAgentRequestMessage: (...a) => canvasAgentRequestMessage(...a),
        canvasAgentRequestMessageForLocalCodex: (...a) => canvasAgentRequestMessageForLocalCodex(...a),
        canvasAgentRoleName: (...a) => canvasAgentRoleName(...a),
        canvasAgentUsesLocalCodex: (...a) => canvasAgentUsesLocalCodex(...a),
        closeCanvasAgentMention: (...a) => closeCanvasAgentMention(...a),
        fetchCanvasAgentLLM: (...a) => fetchCanvasAgentLLM(...a),
        imageRefsOnly: (...a) => imageRefsOnly(...a),
        isCanvasAgentStoppedEmptyReply: (...a) => isCanvasAgentStoppedEmptyReply(...a),
        mediaKindForItem: (...a) => mediaKindForItem(...a),
        normalizeCanvasAgentResult: (...a) => normalizeCanvasAgentResult(...a),
        persistCanvasAgentSession: (...a) => persistCanvasAgentSession(...a),
        renderCanvasAgentBrainstormBar: (...a) => renderCanvasAgentBrainstormBar(...a),
        renderCanvasAgentMessages: (...a) => renderCanvasAgentMessages(...a),
        renderCanvasAgentQuoteCard: (...a) => renderCanvasAgentQuoteCard(...a),
        renderCanvasAgentRefs: (...a) => renderCanvasAgentRefs(...a),
        resizeCanvasAgentInput: (...a) => resizeCanvasAgentInput(...a),
        resolveCanvasAgentChatModel: (...a) => resolveCanvasAgentChatModel(...a),
        setCanvasAgentBusy: (...a) => setCanvasAgentBusy(...a),
        textContentValue: (...a) => textContentValue(...a),
        toast: (...a) => toast(...a),
        uid: (...a) => uid(...a),
        videoRefsOnly: (...a) => videoRefsOnly(...a),
        waitForCanvasAgentProxy: (...a) => waitForCanvasAgentProxy(...a),
        canvasAgentAbortController: () => canvasAgentAbortController,
        canvasAgentActiveRequestId: () => canvasAgentActiveRequestId,
        canvasAgentLastReply: () => canvasAgentLastReply,
        canvasAgentLastReplyRefs: () => canvasAgentLastReplyRefs,
        canvasAgentMentionPoolSnapshot: () => canvasAgentMentionPoolSnapshot,
        canvasAgentPendingChosenId: () => canvasAgentPendingChosenId,
        canvasAgentQuoteState: () => canvasAgentQuoteState,
        canvasAgentRefsState: () => canvasAgentRefsState,
        canvasAgentSending: () => canvasAgentSending,
        canvasAgentActiveId: () => canvasAgentActiveId,
        canvasAgentInput: () => canvasAgentInput,
        canvasAgentMessagesState: () => canvasAgentMessagesState,
        canvasAgentModelPreset: () => canvasAgentModelPreset,
        canvasAgentSessionId: () => canvasAgentSessionId,
        canvasId: () => canvasId,
        setCanvasAgentAbortController: v => { canvasAgentAbortController = v; },
        setCanvasAgentActiveRequestId: v => { canvasAgentActiveRequestId = v; },
        setCanvasAgentLastReply: v => { canvasAgentLastReply = v; },
        setCanvasAgentLastReplyRefs: v => { canvasAgentLastReplyRefs = v; },
        setCanvasAgentMentionPoolSnapshot: v => { canvasAgentMentionPoolSnapshot = v; },
        setCanvasAgentPendingChosenId: v => { canvasAgentPendingChosenId = v; },
        setCanvasAgentQuoteState: v => { canvasAgentQuoteState = v; },
        setCanvasAgentRefsState: v => { canvasAgentRefsState = v; },
        setCanvasAgentSending: v => { canvasAgentSending = v; }
});}
function sendCanvasAgentMessage(){return CanvasAgentSendChain.sendCanvasAgentMessage.apply(null, arguments);}
function useCanvasAgentReply(text=canvasAgentLastReply, refs=canvasAgentLastReplyRefs){
    const value = String(text || '').trim();
    if(!value){
        toast('还没有可用的 Agent 回复');
        return;
    }
    const node = createImageNodeAt(viewportCenter(), [], {select:true});
    canvasUiState.patchSelection({primaryId: node.id}, 'selectedId');
    canvasUiState.patchSelection({ids: []}, 'selectedIds');
    canvasUiState.patchSelection({image: {nodeId:'', index:-1}}, 'selectedImage');
    node.runPrompt = value;
    setPromptDraftForNode(node, value);
    node.__origin = 'agent_reply';
    node.role = 'generation';
    node.status = 'pending';
    const connectedCount = connectCanvasAgentRefsToNode(refs, node);
    render();
    scheduleSave();
    toast(connectedCount ? `已新建图片节点并连接 ${connectedCount} 个引用` : '已新建图片节点并送到生成框');
}
function saveCanvasAgentReplyAsTextNode(text=''){
    const value = String(text || '').trim();
    if(!value){
        toast('没有可保存的文本');
        return;
    }
    const p = viewportCenter();
    const node = createPromptNode(p.x - 316, p.y - 194, {
        title:'Agent 文本',
        kind:'note',
        text:value,
        llmEnabled:false,
    });
    node.__origin = 'agent_reply_text';
    node.role = 'text';
    node.status = 'ready';
    canvasUiState.patchSelection({primaryId: node.id}, 'selectedId');
    canvasUiState.patchSelection({ids: [node.id]}, 'selectedIds');
    canvasUiState.patchSelection({image: {nodeId:'', index:-1}}, 'selectedImage');
    render();
    scheduleSave();
    toast('已保存为文本节点');
}
function attachSelectedResourcesToCanvasAgent(){
    const refs = collectCanvasAgentSelectedResources();
    if(!refs.length){
        toast('请先选中画布里的图片、视频或素材节点');
        return;
    }
    addCanvasAgentRefs(refs);
    setCanvasAgentOpen(true);
}
function isEditableTarget(target){
    const candidates = [target, document.activeElement].filter(Boolean);
    return candidates.some(el => el.closest?.('input, textarea, select, option, [contenteditable="true"], .prompt-input'));
}
// ===== 渲染调度与小地图（canvas-render-scheduler.js）：主文件侧注入 =====
CanvasRenderScheduler.configure({
    shell, world,
    viewport: CanvasViewport.viewport,
    getNodes: () => nodes,
    nodeRect: (n) => nodeRect(n),
    canvasObjectsMode: () => canvasObjectsMode(),
    canvasThumbnailUrl: (u, e2) => canvasThumbnailUrl(u, e2),
    forceNodeIds: () => {
        const force = [];
        if(canvasUiState.selection.primaryId) force.push(canvasUiState.selection.primaryId);
        (canvasUiState.selection.ids || []).forEach(id => force.push(id));
        if(dragState?.id) force.push(dragState.id);
        (dragState?.groupIds || []).forEach(id => force.push(id));
        if(resizeState?.id) force.push(resizeState.id);
        if(uploadTargetId) force.push(uploadTargetId);
        return force;
    },
    isInteracting: () => !!(dragState || resizeState || portDragState || thumbDragState),
    render: () => render(),
    minimapEl: document.getElementById('minimap'),
    minimapContentEl: document.getElementById('minimapContent'),
    minimapToggleEl: document.getElementById('minimapToggle')
});

// ===== ComfyUI 任务引擎（canvas-comfy-job-engine.js）：主文件侧注入 =====
CanvasComfyJobEngine.configure({
    proxyUrl: (p) => comfyProxyUrl(p),
    getNodes: () => nodes,
    render: () => render(),
    scheduleSave: () => scheduleSave(),
    clearNodeRunningState: (n) => clearNodeRunningState(n),
    syncRunButtonAvailability: (n) => syncRunButtonAvailability(n),
    updateComfyNodeLiveState: (n) => updateComfyNodeLiveState(n),
    finalizePendingNode: async (n, urls, meta, kind) => finalizePendingNode(n, urls, meta, kind),
    nowMs: () => nowMs()
});

// ===== 画布撤销记录（canvas-undo-controller.js）：主文件侧注入 =====
CanvasUndoController.configure({
    getContext: () => ({
        setSelection: (patch, reason) => canvasUiState.patchSelection(patch, reason),
        getNodes: () => nodes,
        setNodes: value => { nodes = value; },
        getCanvas: () => canvas,
        getSelectedId: () => canvasUiState.selection.primaryId,
        getSelectedIds: () => canvasUiState.selection.ids,
        getSelectedImage: () => canvasUiState.selection.image,
        isSuppressed: () => undoSuppressed,
        setSuppressed: value => { undoSuppressed = Boolean(value); },
        nodeStore,
        clearComposerSelection: () => { closeAllSmartPopovers(); canvasUiState.clearEditor(); },
        render: () => render(),
        scheduleSave: () => scheduleSave(),
        toast: (...args) => toast(...args),
        tr: (...args) => tr(...args)
    })
});

// ===== 节点删除事务（canvas-node-deletion-controller.js）：一次性删改、单次渲染与保存 =====
CanvasNodeDeletionController.configure({
    getContext: () => ({
        setSelection: (patch, reason) => canvasUiState.patchSelection(patch, reason),
        getNodes: () => nodes,
        selectedNodeIds: () => selectedNodeIds(),
        getWorld: () => world,
        getSelectedId: () => canvasUiState.selection.primaryId,
        getSelectedIds: () => canvasUiState.selection.ids,
        getSelectedImage: () => canvasUiState.selection.image,
        getCanvas: () => canvas,
        nodeStore,
        pushUndo: () => pushUndo(),
        isHistoryGroupNode: node => isHistoryGroupNode(node),
        pruneCanvasObjectReferences: () => pruneCanvasObjectReferences(),
        historyGroupForNode: node => historyGroupForNode(node),
        emptyNodeTitle: () => tr('smart.createImportNode'),
        isEditableTarget: target => isEditableTarget(target),
        isImageEditModalOpen: () => imageEditModal?.classList.contains('open'),
        hasFocusedPromptInput: () => Boolean(document.activeElement?.closest?.('.prompt-input')),
        setDeleteShortcutHandledAt: value => { deleteShortcutHandledAt = value; },
        toast: (...args) => toast(...args),
        render: () => render(),
        scheduleSave: () => scheduleSave()
    })
});

// ===== 节点选择状态（canvas-node-selection-controller.js）：主文件侧注入 =====
CanvasNodeSelectionController.configure({
    getContext: () => ({
        setSelection: (patch, reason) => canvasUiState.patchSelection(patch, reason),
        getNodes: () => nodes,
        getSelectedId: () => canvasUiState.selection.primaryId,
        getSelectedIds: () => canvasUiState.selection.ids,
        getSelectedImage: () => canvasUiState.selection.image,
        setFrontNodeIds: value => { frontNodeIds = value; },
        getWorld: () => world,
        savePromptDraftForCurrent: () => savePromptDraftForCurrent(),
        nodeLayerZ: id => nodeLayerZ(id),
        scheduleConnectionLayerRefresh: () => scheduleConnectionLayerRefresh(),
        refreshSmartNodeToolButtons: () => refreshSmartNodeToolButtons(),
        bringNodesToFront: (...args) => bringNodesToFront(...args)
    })
});

// ===== 节点复制与剪贴板（canvas-node-clipboard-controller.js）：主文件侧注入 =====
CanvasNodeClipboardController.configure({
    getContext: () => ({
        setSelection: (patch, reason) => canvasUiState.patchSelection(patch, reason),
        getNodes: () => nodes,
        getCanvas: () => canvas,
        selectedNodeIds: () => selectedNodeIds(),
        isNodeSelected: id => isNodeSelected(id),
        isEditableTarget: target => isEditableTarget(target),
        getActiveElement: () => document.activeElement,
        uid: prefix => uid(prefix),
        nodeStore,
        planDuplicateConnections: (connections, sourceId, copyId) => SMART_CANVAS_ACTIONS?.duplicateNodeConnections?.(connections, sourceId, copyId) || [],
        connectInputNode: (fromId, toId) => connectInputNode(fromId, toId),
        addConnection: (...args) => addConnection(...args),
        pushUndo: () => pushUndo(),
        bringNodesToFront: (...args) => bringNodesToFront(...args),
        setLastNodePasteAt: value => { lastNodePasteAt = value; },
        getLastMouseWorld: () => lastMouseWorld,
        viewportCenter: () => viewportCenter(),
        render: () => render(),
        scheduleSave: () => scheduleSave(),
        toast: (...args) => toast(...args)
    })
});

// ===== 循环节点控件（canvas-loop-node-controller.js）：主文件侧注入 =====
CanvasLoopNodeController.configure({
    getContext: () => ({
        smartLoopCount: (...args) => smartLoopCount(...args),
        scheduleSave: () => scheduleSave(),
        render: () => render(),
        smartLoopActivePromptFieldValues: (...args) => smartLoopActivePromptFieldValues(...args),
        setSmartLoopPromptFieldValues: (...args) => setSmartLoopPromptFieldValues(...args),
        tr: (...args) => tr(...args),
        fitSmartLoopNode: (...args) => fitSmartLoopNode(...args),
        smartLoopEditorText: (...args) => smartLoopEditorText(...args),
        bindScrollableText: (...args) => bindScrollableText(...args),
        smartLoopPromptFieldValues: (...args) => smartLoopPromptFieldValues(...args),
        insertSmartLoopToken: (...args) => insertSmartLoopToken(...args),
        smartCascadeIsLoopRunning: (...args) => smartCascadeIsLoopRunning(...args),
        requestSmartCascadeStop: (...args) => requestSmartCascadeStop(...args),
        runSmartCascadeFromLoop: (...args) => runSmartCascadeFromLoop(...args)
    })
});

// ===== 节点输入框 ~ 提示词库 / / 技能（canvas-node-prompt-picker.js）：主文件侧注入 =====
if (typeof CanvasNodePromptPicker !== 'undefined') {
    CanvasNodePromptPicker.configure({
        escapeHtml: (...a) => escapeHtml(...a),
        toast: message => toast(message),
        tr: (...a) => tr(...a)
    });
}

// ===== 提示词节点控件（canvas-prompt-node-controller.js）：主文件侧注入 =====
CanvasPromptNodeController.configure({
    getContext: () => ({
        bindScrollableText: (...args) => bindScrollableText(...args),
        scheduleSave: () => scheduleSave(),
        editPromptPresetForNode: (...args) => editPromptPresetForNode(...args),
        resolveChatProviderId: (...args) => resolveChatProviderId(...args),
        resolveChatModel: (...args) => resolveChatModel(...args),
        promptNodeExpandedHeight: (...args) => promptNodeExpandedHeight(...args),
        render: () => render(),
        runPromptLLMNode: (...args) => runPromptLLMNode(...args)
    })
});

// ===== 图片节点操作（canvas-node-media-actions.js）：主文件侧注入 =====
CanvasNodeMediaActions.configure({
    getContext: () => ({
        deleteImage: (...args) => deleteImage(...args),
        openSmartImageTool: (...args) => openSmartImageTool(...args),
        handleSmartNodeToolAction: (...args) => handleSmartNodeToolAction(...args),
        clearImageClickTimer: () => clearImageClickTimer(),
        setSuppressImageClickUntil: value => { suppressImageClickUntil = value; },
        beginSmartImageRename: (...args) => beginSmartImageRename(...args)
    })
});

// ===== 通用节点操作（canvas-node-action-controller.js）：主文件侧注入 =====
CanvasNodeActionController.configure({
    getContext: () => ({
        getNodes: () => nodes,
        isNodeClickSuppressed: () => smNodeClickSuppressed(),
        hideRunTimerForNode: (...args) => hideRunTimerForNode(...args),
        selectNodeFromPointer: (...args) => selectNodeFromPointer(...args),
        smartCascadeAnyRunning: () => smartCascadeAnyRunning(),
        setSmartCascadeSilentSelection: value => { smartCascadeSilentSelection = value; },
        syncSelectionUi: () => syncSelectionUi(),
        updateComposer: () => updateComposer(),
        setSelectedId: value => { canvasUiState.patchSelection({primaryId: value}, 'selectedId'); },
        setSelectedIds: value => { canvasUiState.patchSelection({ids: value}, 'selectedIds'); },
        setSelectedImage: value => { canvasUiState.patchSelection({image: value}, 'selectedImage'); },
        bringNodesToFront: (...args) => bringNodesToFront(...args),
        setPendingGroupUploadPoint: value => { pendingGroupUploadPoint = value; },
        setUploadTargetId: value => { uploadTargetId = value; },
        pickMediaForSmartNode: (...args) => pickMediaForSmartNode(...args),
        deleteNodeFromButton: (...args) => deleteNodeFromButton(...args),
        toggleCanvasNodeSet: (...args) => toggleCanvasNodeSet(...args),
        capturePendingUndo: () => capturePendingUndo(),
        commitPendingUndo: () => commitPendingUndo(),
        scheduleSave: () => scheduleSave(),
        render: () => render(),
        queryJimengNow: (...args) => queryJimengNow(...args)
    })
});

// ===== 端口连线手势（canvas-port-gesture-controller.js）：主文件侧注入 =====
CanvasPortGestureController.configure({
    getContext: () => ({
        setPortDragState: value => { portDragState = value; },
        screenToWorld: (...args) => screenToWorld(...args),
        getShell: () => shell,
        capturePendingUndo: () => capturePendingUndo(),
        ensurePortDragPathElement: () => ensurePortDragPathElement(),
        updatePortDragVisual: () => updatePortDragVisual()
    })
});

// ===== 图片上下文菜单（canvas-image-context-menu-controller.js）：主文件侧注入 =====
CanvasNodeContextMenuController.configure({
    getNodes:() => nodes,
    getSelectedNodeIds:() => selectedNodeIds(),
    duplicateNodeWithConnections:nodeId => duplicateSmartNodeWithConnections(nodeId),
    copyNodesToClipboard:nodeId => {
        // 菜单项「复制」= 放进内部剪贴板（之后 Ctrl+V 可粘），与「复制节点」= 立刻克隆一份不同
        const selected = selectedNodeIds();
        if(!selected.includes(nodeId)){
            canvasUiState.patchSelection({primaryId: nodeId}, 'selectedId');
            canvasUiState.patchSelection({ids: []}, 'selectedIds');
            syncSelectionUi();
        }
        return copySelectedNodes();
    },
    deleteNodes:ids => CanvasNodeDeletionController.deleteNodes(ids),
    bringNodesToFront:(...args) => bringNodesToFront(...args)
});

// 提示词框 / 输入框右键的复制/粘贴/全选菜单（WebView2 下系统原生菜单被关，必须自建）
CanvasEditableContextMenuController.configure({
    toast:message => toast(message)
});

CanvasImageContextMenuController.configure({
    getActionIds:() => SMART_CANVAS_ACTIONS?.smartImageContextActionIds?.(),
    translate:key => tr(key),
    escapeAttr:value => escapeAttr(value),
    escapeHtml:value => escapeHtml(value),
    getNodes:() => nodes,
    getCanvasId:() => canvasId,
    toast:message => toast(message),
    fetcher:(...args) => fetch(...args),
    setAssetVersionMode:(...args) => setSmartImageAssetVersionMode(...args),
    saveAssetVersion:(...args) => saveSmartImageAsAssetVersion(...args),
    addImageNodeRefToAgent:(...args) => addImageNodeRefToCanvasAgent(...args),
    duplicateNodeWithConnections:nodeId => duplicateSmartNodeWithConnections(nodeId),
    nodeRect:node => nodeRect(node),
    getSettings:() => settings,
    createGeneratorNode:(...args) => createSmartGeneratorNode(...args),
    settingsForStorage:value => settingsForStorage(value),
    cloneSettings:value => cloneSmartSettings(value),
    connectInputNode:(...args) => connectInputNode(...args),
    setSelectedId:value => {canvasUiState.patchSelection({primaryId: value}, 'selectedId');},
    setSelectedIds:value => {canvasUiState.patchSelection({ids: value}, 'selectedIds');},
    setSelectedImage:value => {canvasUiState.patchSelection({image: value}, 'selectedImage');},
    isApiLikeEngine:engine => isApiLikeEngine(engine),
    setApiKind:value => {settings.apiKind = value;},
    syncSelectionUi:() => syncSelectionUi(),
    updateComposer:() => updateComposer(),
    insertImageReferenceIntoPrompt:value => insertImageReferenceIntoPrompt(value),
    mediaKindForItem:item => mediaKindForItem(item),
    persistActiveSettings:() => persistActiveSmartSettings(),
    renderDynamicParams:() => renderDynamicParams(),
    render:() => render(),
    scheduleSave:() => scheduleSave(),
    getAssetLibrary:() => assetLibrary,
    loadAssetLibrary:() => loadAssetLibrary(),
    addUrlToAssetLibrary:(...args) => addUrlToAssetLibrary(...args),
    getSelectedNodeIds:() => selectedNodeIds(),
    bringNodesToFront:(...args) => bringNodesToFront(...args),
    enterRedirectPickMode:nodeId => enterRedirectPickMode(nodeId)
});

// ===== 图片缩略图交互（canvas-image-node-interactions.js）：主文件侧注入 =====
CanvasImageNodeInteractions.configure({
    getContext: () => ({
        getNodes: () => nodes,
        bringNodesToFront: (...args) => bringNodesToFront(...args),
        hideRunTimerForNode: (...args) => hideRunTimerForNode(...args),
        getSelectedIds: () => canvasUiState.selection.ids,
        selectNodeFromPointer: (...args) => selectNodeFromPointer(...args),
        smartCascadeAnyRunning: () => smartCascadeAnyRunning(),
        setSmartCascadeSilentSelection: value => { smartCascadeSilentSelection = value; },
        syncSelectionUi: () => syncSelectionUi(),
        updateComposer: () => updateComposer(),
        clearImageClickTimer: () => clearImageClickTimer(),
        getSuppressImageClickUntil: () => suppressImageClickUntil,
        setSuppressImageClickUntil: value => { suppressImageClickUntil = value; },
        setSelectedId: value => { canvasUiState.patchSelection({primaryId: value}, 'selectedId'); },
        setSelectedIds: value => { canvasUiState.patchSelection({ids: value}, 'selectedIds'); },
        setSelectedImage: value => { canvasUiState.patchSelection({image: value}, 'selectedImage'); },
        openImagePreview: (...args) => openImagePreview(...args),
        openSmartImageContextMenu: (...args) => openSmartImageContextMenu(...args),
        setThumbDragState: value => { thumbDragState = value; },
        capturePendingUndo: () => capturePendingUndo()
    })
});

// ===== 节点拖动与缩放手势（canvas-node-gesture-controller.js）：主文件侧注入 =====
CanvasNodeGestureController.configure({
    getContext: () => ({
        getNodes: () => nodes,
        nodeRect: (...args) => nodeRect(...args),
        setResizeState: value => { resizeState = value; },
        duplicateForAltDrag: (...args) => duplicateForAltDrag(...args),
        isCanvasGroupNode: (...args) => isCanvasGroupNode(...args),
        connectNewGroupMemberConnections: (...args) => connectNewGroupMemberConnections(...args),
        selectedNodeIds: () => selectedNodeIds(),
        bringNodesToFront: (...args) => bringNodesToFront(...args),
        getDragState: () => dragState,
        setDragState: value => { dragState = value; },
        getViewportScale: () => viewport.scale,
        getWorld: () => world,
        selectedNode: () => selectedNode(),
        positionComposerForNode: (...args) => positionComposerForNode(...args),
        isAssetLibraryOpen: () => assetLibraryOpen,
        getAssetPanel: () => assetPanel,
        setAssetDragOver: (...args) => CanvasAssetPanelDropController.setDragOver(...args),
        nodeLayerZ: (...args) => nodeLayerZ(...args),
        addUrlToAssetLibrary: (...args) => addUrlToAssetLibrary(...args),
        commitPendingUndo: () => commitPendingUndo(),
        discardPendingUndo: () => discardPendingUndo(),
        suppressNodeClick: (...args) => smSuppressNodeClick(...args),
        setLoopInsertPreview: value => { loopInsertPreview = value; },
        isSnapEnabled: () => snapEnabled,
        renderSnapGuides: guides => renderSnapGuides(guides),
        scheduleMinimapRender: () => scheduleMinimapRender(),
        refreshConnectionLayer: () => refreshConnectionLayer(),
        render: () => render(),
        scheduleSave: () => scheduleSave(),
        setSmartDropCopyEffect: (...args) => setSmartDropCopyEffect(...args),
        resolveSmartImageDropPayload: (...args) => CanvasImageDropPayload.resolve(...args),
        handleSmartImageDropPayload: (...args) => handleSmartImageDropPayload(...args),
        capturePendingUndo: () => capturePendingUndo()
    })
});

// ===== 节点分组与布局操作（canvas-node-layout-controller.js）：主文件侧注入 =====
CanvasNodeLayoutController.configure({
    getContext: () => ({
        getNodes: () => nodes,
        getWorld: () => world,
        selectedNodeIds: () => selectedNodeIds(),
        getSelectedIds: () => canvasUiState.selection.ids,
        getSelectedId: () => canvasUiState.selection.primaryId,
        setSelectedIds: value => { canvasUiState.patchSelection({ids: value}, 'selectedIds'); },
        setSelectedId: value => { canvasUiState.patchSelection({primaryId: value}, 'selectedId'); },
        setSelectedImage: value => { canvasUiState.patchSelection({image: value}, 'selectedImage'); },
        nodeRect: (...args) => nodeRect(...args),
        nodeScale: (...args) => nodeScale(...args),
        imageLayout: (...args) => imageLayout(...args),
        thumbDisplaySize: (...args) => thumbDisplaySize(...args),
        stripImageGenerationMeta: (...args) => stripImageGenerationMeta(...args),
        inheritNodeMetaFromImage: (...args) => inheritNodeMetaFromImage(...args),
        uid: (...args) => uid(...args),
        addNodeToStore: (...args) => nodeStore.addNode(...args),
        removeNodeFromStore: (...args) => nodeStore.removeNode(...args),
        addNodesToStore: (...args) => nodeStore.addNodes(...args),
        getCanvas: () => canvas,
        mediaNodeDefaultScale: () => MEDIA_NODE_DEFAULT_SCALE,
        pushUndo: () => pushUndo(),
        render: () => render(),
        scheduleSave: () => scheduleSave(),
        toast: (...args) => toast(...args),
        tr: (...args) => tr(...args)
    })
});

// ===== Agent 会话存储层（canvas-agent-history-store.js）：主文件侧注入 =====
CanvasAgentHistoryStore.configure({
    proxyBase: () => RH_OFFICIAL_PROXY_BASE,
    loadAppRuntimeConfig: () => loadAppRuntimeConfig(),
    uid: (p) => uid(p),
    canvasId: () => canvasId,
    historyKey: () => CANVAS_AGENT_HISTORY_KEY,
    historyKeyPrefix: () => CANVAS_AGENT_HISTORY_KEY_PREFIX,
    historyKeySuffix: () => CANVAS_AGENT_HISTORY_KEY_SUFFIX,
    buildStoryboardPlan: (t, r) => buildCanvasAgentStoryboardPlan(t, r),
    buildStoryboardPlanFromReply: (r, b) => buildCanvasAgentStoryboardPlanFromReply(r, b),
    getSession: () => ({
        messages: canvasAgentMessagesState,
        sessionId: canvasAgentSessionId,
        lastReply: canvasAgentLastReply,
        lastReplyRefs: canvasAgentLastReplyRefs
    }),
    getCanvasTitle: () => canvas?.title || document.getElementById('smartTitle')?.textContent || ''
});

// ===== 产物数据模型（canvas-artifact-model.js）：主文件侧注入 =====
CanvasArtifactModel.configure({
    canvasId: () => canvasId,
    getArtifacts: () => canvasAgentArtifactsState,
    setArtifacts: (list) => { canvasAgentArtifactsState = list; },
    navSectionId: () => canvasAgentActiveSectionId,
    navItemId: () => canvasAgentActiveItemId,
    renderSidebar: () => renderArtifactSidebar(),
    scheduleSave: () => scheduleSave(),
    artifactTypeLabel: (t) => artifactTypeLabel(t)
});

// ===== 产物视图层（canvas-artifact-view.js）：主文件侧注入 =====
CanvasArtifactView.configure({
    getArtifacts: () => canvasAgentArtifactsState,
    setArtifacts: (v) => { canvasAgentArtifactsState = v; },
    getActiveArtifactId: () => canvasAgentActiveArtifactId,
    setActiveArtifactId: (v) => { canvasAgentActiveArtifactId = v; },
    getActiveSectionId: () => canvasAgentActiveSectionId,
    setActiveSectionId: (v) => { canvasAgentActiveSectionId = v; },
    getActiveItemId: () => canvasAgentActiveItemId,
    setActiveItemId: (v) => { canvasAgentActiveItemId = v; },
    getSelectedId: () => canvasUiState.selection.primaryId,
    setSelectedId: (v) => { canvasUiState.patchSelection({primaryId: v}, 'selectedId'); },
    getNodes: () => nodes,
    getRefs: () => canvasAgentRefsState,
    getMessages: () => canvasAgentMessagesState,
    render: () => render(),
    scheduleSave: () => scheduleSave(),
    escapeHtml: (s) => escapeHtml(s),
    artifactTypeLabel: (t) => artifactTypeLabel(t),
    artifactTypeMeta: (t) => artifactTypeMeta(t),
    createTextNode: (x, y, o) => createTextNode(x, y, o),
    newCanvasAgentSession: (s) => newCanvasAgentSession(s),
    renderCanvasAgentRefs: () => renderCanvasAgentRefs()
});

// ===== Agent 消息渲染层（canvas-agent-message-render.js）：主文件侧注入 =====
CanvasAgentMessageRender.configure({
    mediaKindForItem: (i) => mediaKindForItem(i),
    canvasAgentMentionCandidates: () => canvasAgentMentionCandidates(),
    canvasAgentParseBrainstormReply: (t) => canvasAgentParseBrainstormReply(t),
    escapeHtml: (s) => escapeHtml(s),
    getMentionPool: () => canvasAgentMentionPoolSnapshot,
    getRefs: () => canvasAgentRefsState,
    getNodes: () => nodes,
    getChosenMap: () => canvasAgentChosenMap
});
CanvasAgentMessageViewController.configure({
    getContainer:() => canvasAgentMessages,
    getWelcomeTemplate:() => canvasAgentWelcomeTemplate,
    getMessages:() => canvasAgentMessagesState,
    setChosenMap:map => {canvasAgentChosenMap = map;},
    renderMessage:message => canvasAgentMessageHtml(message),
    refreshHeadTitle:() => canvasAgentRefreshHeadTitle(),
    previewActionPlan:(...args) => previewCanvasAgentActionPlan(...args),
    executeRecentNodes:messageId => canvasAgentExecuteRecentNodes(messageId),
    sendBrainstormChoice:(...args) => sendCanvasAgentBrainstormChoice(...args),
    runBrainstormNodes:messageId => canvasAgentRunBrainstormNodes(messageId),
    copyMessageText:text => canvasAgentCopyMessageText(text),
    editMessage:messageId => canvasAgentEditMessage(messageId),
    cancelEditMessage:() => canvasAgentCancelEditMessage(),
    resendEditedMessage:(...args) => canvasAgentResendEditedMessage(...args),
    quoteMessageText:value => canvasAgentQuoteMessageText(value),
    locateMessageNode:value => canvasAgentLocateMessageNode(value),
    locateSpecificNode:(...args) => canvasAgentLocateSpecificNode(...args),
    submitInteractionReceipt:payload => canvasAgentSubmitInteractionReceipt(payload),
    getInput:() => canvasAgentInput,
    resizeInput:() => resizeCanvasAgentInput(),
    sendMessage:() => sendCanvasAgentMessage(),
    toast:message => toast(message),
    fetcher:(...args) => fetch(...args),
    renderAgain:() => CanvasAgentMessageViewController.render(),
    refreshAfterUndo:async() => {
        if(typeof refreshFromBackend === 'function') await refreshFromBackend();
        else if(typeof loadCanvases === 'function') await loadCanvases();
    },
    createBrainstormNodes:(...args) => canvasAgentCreateBrainstormNodes(...args),
    saveReplyAsTextNode:value => saveCanvasAgentReplyAsTextNode(value),
    refreshIcons:() => {if(window.lucide) lucide.createIcons();}
});
CanvasAgentMentionController.configure({
    getInput:() => canvasAgentInput,
    getPanel:() => canvasAgentPanel,
    getRefs:() => canvasAgentRefsState,
    setRefs:refs => {canvasAgentRefsState = refs;},
    collectSelectedResources:() => collectCanvasAgentSelectedResources(),
    uniqueRefs:refs => uniqueCanvasAgentRefs(refs),
    mediaKindForItem:item => mediaKindForItem(item),
    mediaLabel:(ref, index) => canvasAgentMediaLabel(ref, index),
    refFileName:ref => canvasAgentRefFileName(ref),
    refKindLabel:ref => canvasAgentRefKindLabel(ref),
    mentionBadge:ref => canvasAgentMentionBadge(ref),
    escapeHtml:value => escapeHtml(value),
    getIndex:() => canvasAgentMentionIndex,
    setIndex:index => {canvasAgentMentionIndex = index;},
    getMentionPool:() => canvasAgentMentionPoolSnapshot,
    setMentionPool:pool => {canvasAgentMentionPoolSnapshot = pool;},
    addRefs:refs => addCanvasAgentRefs(refs),
    renderRefs:() => renderCanvasAgentRefs(),
    resizeInput:() => resizeCanvasAgentInput(),
    sendMessage:() => sendCanvasAgentMessage()
});
CanvasGenerationDispatchController.configure({
    getSettings:() => settings,
    generateComfyUrlsWithSettings:(...args) => generateComfyUrlsWithSettings(...args),
    isApiLikeEngine:engine => isApiLikeEngine(engine),
    runApiVideoGeneration:(...args) => runApiVideoGeneration(...args),
    taskIdsFromResult:result => taskIdsFromResult(result),
    resultMediaUrls:result => resultMediaUrls(result),
    pollSmartCanvasTask:taskId => pollSmartCanvasTask(taskId),
    mediaKindForUrls:(urls, fallback) => mediaKindForUrls(urls, fallback),
    runApiGeneration:(...args) => runApiGeneration(...args),
    runRunningHubGeneration:(...args) => runRunningHubGeneration(...args)
});
CanvasGenerationResultModel.configure({
    isVideoMediaItem:item => isVideoMediaItem(item),
    isAudioMediaItem:item => isAudioMediaItem(item),
    isTextMediaItem:item => isTextMediaItem(item)
});
CanvasGenerationTaskPoller.configure({
    activePolls:activeSmartTaskPolls,
    proxyBase:() => RH_OFFICIAL_PROXY_BASE,
    translate:key => tr(key),
    newJimengPendingSignal:options => new CanvasSmartTaskSupervisor.JimengPendingSignal(options),
    wait:ms => sleep(ms),
    fetcher:url => fetch(url)
});
CanvasCascadeRoundScheduler.configure({
    shouldStop:runState => Boolean(runState?.stopRequested || (!runState && smartCascadeStopRequested)),
    isStoppedError:error => Boolean(error?.smartCascadeStopped)
});

// ===== Agent 技能管理（canvas-agent-skill-manager.js）：主文件侧注入 =====
CanvasAgentSkillManager.configure({
    proxyBase: () => RH_OFFICIAL_PROXY_BASE,
    escapeHtml: (value) => escapeHtml(value),
    toast: (message) => toast(message),
    refreshIcons: () => refreshIcons(),
    confirm: (message) => window.confirm(message)
});

// ===== 图片自由裁剪（canvas-image-crop.js）：主文件侧注入 =====
CanvasImageCrop.configure({
    getNodes: () => nodes,
    getWorld: () => world,
    getViewport: () => CanvasViewport.viewport,
    mediaKindForItem: (item) => mediaKindForItem(item),
    setSelection: (nodeId, imageIndex) => {
        canvasUiState.patchSelection({primaryId: nodeId}, 'selectedId');
        canvasUiState.patchSelection({ids: []}, 'selectedIds');
        canvasUiState.patchSelection({image: {nodeId, index:imageIndex}}, 'selectedImage');
    },
    syncSelectionUi: () => syncSelectionUi(),
    fileNameFromUrl: (url) => fileNameFromUrl(url),
    uploadCroppedBlob: (blob, name) => uploadCroppedBlob(blob, name),
    imageLayout: (images, scale, node) => imageLayout(images, scale, node),
    nodeScale: (node) => nodeScale(node),
    createNode: (x, y, images) => createNode(x, y, images),
    toast: (message) => toast(message)
});

// ===== RunningHub 控件渲染层（canvas-rh-controls.js）：主文件侧注入 =====
CanvasRhControls.configure({
    escapeHtml: (s) => escapeHtml(s),
    tr: (k, fb) => tr(k, fb),
    runningHubEntries: (kind) => runningHubEntries(kind),
    selectedRunningHubRef: (src) => selectedRunningHubRef(src),
    rhNodeOffBucket: (src) => rhNodeOffBucket(src),
    renderRhInputsRow: () => renderRhInputsRow(),
    rhFieldRole: (f) => rhFieldRole(f),
    renderRhSettingField: (f) => renderRhSettingField(f),
    getRunningHubWorkflowCache: () => runningHubWorkflowCache,
    rhIsWorkflowLinkValue: (value) => rhIsWorkflowLinkValue(value),
    getSettings: () => settings,
    getEngineSelect: () => engineSelect
});

// ===== ComfyUI 控件渲染层（canvas-comfy-controls.js）：主文件侧注入 =====
CanvasComfyControls.configure({
    escapeHtml: (s) => escapeHtml(s),
    tr: (k, fb) => tr(k, fb),
    renderComfyInputsRow: () => renderComfyInputsRow(),
    renderComfySettingField: (f) => renderComfySettingField(f),
    comfyFieldKind: (f, wf) => comfyFieldKind(f, wf),
    visibleComfyFields: (fields, wf) => visibleComfyFields(fields, wf),
    comfyParamValue: (f) => comfyParamValue(f),
    smartComfyRandomActive: (id) => smartComfyRandomActive(id),
    comfyModesForWorkflow: (wf) => comfyModesForWorkflow(wf),
    resolveComfyWorkflowName: (wf) => resolveComfyWorkflowName(wf),
    getSettings: () => settings,
    getEngineSelect: () => engineSelect,
    getWorkflows: () => comfyWorkflows
});

// ===== 交互观察者（canvas-interaction-observer.js，状态机改造第0步）：只读采样，零行为影响 =====
if (typeof CanvasInteractionObserver !== 'undefined') {
    CanvasInteractionObserver.configure({
        probes: [
            {name: 'panState',            get: () => panState},
            {name: 'dragState',           get: () => dragState},
            {name: 'selectionState',      get: () => selectionState},
            {name: 'resizeState',         get: () => resizeState},
            {name: 'portDragState',       get: () => portDragState},
            {name: 'connectionCutState',  get: () => connectionCutState},
            {name: 'thumbDragState',      get: () => thumbDragState},
            {name: 'inputThumbDragState', get: () => inputThumbDragState},
            {name: 'cropDrag',            get: () => cropDrag},
            {name: 'previewPanDrag',      get: () => previewPanDrag},
            {name: 'previewCompareDrag',  get: () => previewCompareDrag},
            {name: 'imageEditPanDrag',    get: () => imageEditPanDrag},
            {name: 'panoramaDrag',        get: () => panoramaState && panoramaState.drag},
            {name: 'promptResizeState',   get: () => promptResizeState},
            {name: 'minimapDrag',         get: () => (typeof CanvasRenderScheduler !== 'undefined' && CanvasRenderScheduler.inMinimapDrag && CanvasRenderScheduler.inMinimapDrag())}
        ]
    });
}

// ===== 参数控件渲染层（canvas-param-controls.js）：主文件侧注入 =====
CanvasParamControls.configure({
    escapeHtml: (...a) => escapeHtml(...a),
    tr: (...a) => tr(...a),
    videoProviderById: (...a) => videoProviderById(...a),
    providerModelDisplayName: (...a) => providerModelDisplayName(...a),
    videoAspectIconClass: (...a) => videoAspectIconClass(...a),
    videoAspectLabel: (...a) => videoAspectLabel(...a),
    videoAspectOptions: (...a) => videoAspectOptions(...a),
    videoDurationValue: (...a) => videoDurationValue(...a),
    videoResolutionLabel: (...a) => videoResolutionLabel(...a),
    imageQualityLabel: (...a) => imageQualityLabel(...a),
    imageSpecOptions: (...a) => imageSpecOptions(...a),
    ratioIconClass: (...a) => ratioIconClass(...a),
    ratioLabel: (...a) => ratioLabel(...a),
    resolutionLabel: (...a) => resolutionLabel(...a),
    videoReferenceModeValue: (...a) => videoReferenceModeValue(...a),
    apiProviderById: (...a) => apiProviderById(...a),
    smartAvailableEngines: (...a) => smartAvailableEngines(...a),
    smartEngineLabel: (...a) => smartEngineLabel(...a),
    videoApiProviders: (...a) => videoApiProviders(...a),
    volcengineProvider: (...a) => volcengineProvider(...a),
    getSettings: () => settings
});

// ===== 参数控件事件（canvas-param-events.js）：主文件侧注入 =====
CanvasParamEvents.configure({
    getContainer: () => dynamicParams,
    getEngineSelect: () => engineSelect,
    getSettings: () => settings,
    closeAllSmartPopovers: () => closeAllSmartPopovers(),
    renderDynamicParams: () => renderDynamicParams(),
    setVideoSpecSetting: (...a) => setVideoSpecSetting(...a),
    setImageSpecSetting: (...a) => setImageSpecSetting(...a),
    setDynamicSetting: (...a) => setDynamicSetting(...a),
    syncImageSpecControl: () => syncImageSpecControl(),
    persistActiveSmartSettings: () => persistActiveSmartSettings(),
    scheduleSave: () => scheduleSave(),
    uploadCurrentSmartVideosToCloud: () => uploadCurrentSmartVideosToCloud(),
    setCurrentSmartManualVideoUrl: () => setCurrentSmartManualVideoUrl(),
    currentComfyFields: () => currentComfyFields(),
    updateComfySliderValueLabel: (...a) => updateComfySliderValueLabel(...a),
    toggleSmartComfyRandom: (...a) => toggleSmartComfyRandom(...a),
    toggleSmartRhRandom: (...a) => toggleSmartRhRandom(...a),
    resolveComfyWorkflowName: (...a) => resolveComfyWorkflowName(...a),
    tr: (...a) => tr(...a),
    syncComfyModesChrome: (...a) => syncComfyModesChrome(...a),
    syncComfyDetailsAndParams: (...a) => syncComfyDetailsAndParams(...a),
    getComfyWorkflowCache: () => comfyWorkflowCache,
    selectedRunningHubRef: (...a) => selectedRunningHubRef(...a),
    runningHubEntryKey: (...a) => runningHubEntryKey(...a),
    syncRhNodesChrome: (...a) => syncRhNodesChrome(...a),
    syncRhDetailsAndParams: (...a) => syncRhDetailsAndParams(...a),
    rhActiveFields: () => rhActiveFields(),
    rhParamKey: (...a) => rhParamKey(...a),
    rhParamValue: (...a) => rhParamValue(...a),
    toast: (...a) => toast(...a),
    refreshIcons: () => refreshIcons()
});

// ===== 3D 预演参数视图（canvas-previz-controls.js）：主文件侧注入 =====
CanvasPrevizControls.configure({
    getContext: () => ({
        settings,
        getNode: () => selectedNode(),
        applyOfflinePatch: patch => {
            const node = selectedNode();
            if(!node) return;
            Object.assign(settings, patch);
            node.runSettings = Object.assign(node.runSettings || {}, patch);
            scheduleSave();
        },
        notify: message => toast(message),
        generateOffline: () => document.getElementById('runBtn')?.click(),
        layoutOffline: () => {const node=selectedNode();if(node&&composer.classList.contains('open'))positionComposerForNode(node);},
        dynamicParams,
        composerStyleModeSlot,
        promptInput,
        escapeAttr: (...a) => escapeAttr(...a),
        escapeHtml: (...a) => escapeHtml(...a),
        renderPrevizLlmControl: () => renderPrevizLlmControl(),
        closeAllSmartPopovers: () => closeAllSmartPopovers(),
        scheduleSave: () => scheduleSave(),
        bindPrevizLlmControl: () => bindPrevizLlmControl(),
        syncEngineSelectOptions: () => syncEngineSelectOptions()
    })
});

// ===== ~ 快捷提示词库面板（canvas-prompt-library-picker.js）：主文件侧注入 =====
if (typeof CanvasPromptLibPicker !== 'undefined') {
    CanvasPromptLibPicker.configure({
        promptInput: promptInput,
        escapeHtml: (...a) => escapeHtml(...a),
        tr: (...a) => tr(...a)
    });
}

// ===== 提示词模板视图（canvas-prompt-template-view.js）：主文件侧注入 =====
CanvasPromptTemplateModel.configure({
    getContext: () => ({
        state: {
            get promptPresets(){ return promptPresets; },
            set promptPresets(value){ promptPresets = value; },
            get builtinPromptTemplates(){ return builtinPromptTemplates; },
            set builtinPromptTemplates(value){ builtinPromptTemplates = value; },
            get promptLibraries(){ return promptLibraries; },
            set promptLibraries(value){ promptLibraries = value; },
            get activePromptLibraryId(){ return activePromptLibraryId; },
            set activePromptLibraryId(value){ activePromptLibraryId = value; },
            get promptTemplateGroups(){ return promptTemplateGroups; },
            set promptTemplateGroups(value){ promptTemplateGroups = value; },
            get promptTemplateOverrides(){ return promptTemplateOverrides; },
            set promptTemplateOverrides(value){ promptTemplateOverrides = value; },
            get promptTemplateSelectedId(){ return promptTemplateSelectedId; }
        },
        tr: (...a) => tr(...a)
    })
});
CanvasPromptPresetPanel.configure({
    getContext: () => ({
        promptPresetPanel, promptPresetClose, promptPresetStatus, promptPresetSelect,
        promptPresetName, promptPresetText, promptPresetApply, promptPresetDelete,
        promptPresetNew, promptPresetSave, shell, world,
        promptPresets: () => promptPresets,
        nodes: () => nodes,
        currentPromptPreset: id => currentPromptPreset(id),
        updatePreset: (id, changes) => CanvasPromptTemplateModel.updatePreset(id, changes),
        removePreset: id => CanvasPromptTemplateModel.removePreset(id),
        createPresetFromNode: (...a) => createPromptPresetFromNode(...a),
        escapeHtml: (...a) => escapeHtml(...a),
        tr: (...a) => tr(...a),
        render: () => render(),
        scheduleSave: () => scheduleSave(),
        refreshIcons: () => refreshIcons()
    })
});
CanvasPromptPresetPanel.bindEvents();
CanvasHeaderNavigation.configure({
    getContext: () => ({
        canvasId, canvasTitleDropdown, canvasTitleText, canvasTitleInput,
        canvasListDropdown, canvasListDropdownItems, canvasDropdownSearch,
        getCanvas: () => canvas,
        getNodes: () => nodes,
        savePromptDraft: () => savePromptDraftForCurrent(),
        escapeHtml: (...a) => escapeHtml(...a),
        tr: (...a) => tr(...a),
        toast: (...a) => toast(...a),
        scheduleSave: () => scheduleSave(),
        refreshIcons: () => refreshIcons()
    })
});
CanvasHeaderNavigation.bindEvents();
CanvasPromptTemplateView.configure({
    getContext: () => ({
        promptTemplatePanel, promptTemplateBody, promptTemplateCats, promptTemplateSearch,
        promptTemplateCategory, promptTemplateGroupEditMode, promptTemplateEditing, promptTemplateSelectedId,
        setPromptTemplateSelectedId: value => { promptTemplateSelectedId = value; },
        renderPromptLibrarySelect: () => renderPromptLibrarySelect(),
        promptTemplateItems: () => promptTemplateItems(),
        activePromptTemplateGroups: () => activePromptTemplateGroups(),
        promptTemplateCategoryLabel: (...a) => promptTemplateCategoryLabel(...a),
        promptTemplateSearchText: (...a) => promptTemplateSearchText(...a),
        currentPromptPreset: (...a) => currentPromptPreset(...a),
        promptTemplateName: (...a) => promptTemplateName(...a),
        promptTemplateScene: (...a) => promptTemplateScene(...a),
        activePromptLibrary: () => activePromptLibrary(),
        tr: (...a) => tr(...a),
        escapeHtml: (...a) => escapeHtml(...a),
        escapeAttr: (...a) => escapeAttr(...a),
        getNodes: () => nodes,
        refreshIcons: () => refreshIcons()
    })
});

// ===== 提示词模板交互控制器（canvas-prompt-template-controller.js） =====
CanvasPromptTemplateController.configure({
    getContext: () => ({
        state: {
            get category(){ return promptTemplateCategory; },
            set category(value){ promptTemplateCategory = value; },
            get selectedId(){ return promptTemplateSelectedId; },
            set selectedId(value){ promptTemplateSelectedId = value; },
            get editing(){ return promptTemplateEditing; },
            set editing(value){ promptTemplateEditing = value; },
            get groupEditMode(){ return promptTemplateGroupEditMode; },
            set groupEditMode(value){ promptTemplateGroupEditMode = value; },
            get activeLibraryId(){ return activePromptLibraryId; },
            set activeLibraryId(value){ activePromptLibraryId = value; }
        },
        promptTemplatePanel, composerTemplateBtn, promptTemplateSearch, promptTemplateClose,
        promptTemplateLibrarySelect, promptInput, shell,
        promptTemplateItems: () => promptTemplateItems(),
        renderPromptTemplatePanel: (...a) => renderPromptTemplatePanel(...a),
        setTemplateNodeSelection: id => { canvasUiState.patchSelection({primaryId: id}, 'selectedId'); canvasUiState.patchSelection({ids: []}, 'selectedIds'); canvasUiState.patchSelection({image: {nodeId:'', index:-1}}, 'selectedImage'); },
        render: () => render(),
        selectedNode: () => selectedNode(),
        activeComposerNode: () => activeComposerNode(),
        setPromptText: (...a) => setPromptText(...a),
        promptTemplateText: (...a) => promptTemplateText(...a),
        savePromptDraftForCurrent: () => savePromptDraftForCurrent(),
        renderInputThumbsRow: node => renderInputThumbsRow(node),
        getNodes: () => nodes,
        scheduleSave: () => scheduleSave(),
        saveCurrentPromptAsTemplate: () => saveCurrentPromptAsTemplate(),
        createBlankPromptTemplate: () => createBlankPromptTemplate(),
        savePromptTemplateEdit: () => savePromptTemplateEdit(),
        deletePromptTemplate: () => deletePromptTemplate(),
        renamePromptTemplateGroup: id => renamePromptTemplateGroup(id),
        deletePromptTemplateGroup: id => deletePromptTemplateGroup(id),
        createPromptTemplateGroup: () => createPromptTemplateGroup()
    })
});
CanvasPromptTemplateController.bindEvents();

// ===== 规格控件渲染层（canvas-spec-controls.js）：主文件侧注入 =====
CanvasSpecControls.configure({
    escapeHtml: (...a) => escapeHtml(...a),
    tr: (...a) => tr(...a),
    sourceImageRatioLabel: (...a) => sourceImageRatioLabel(...a),
    getSettings: () => settings
});
CanvasArtifactView.bindEvents();

// ===== 视口内核（canvas-viewport-engine.js）：viewport 权威状态在该模块，这里是主文件侧注入与薄别名 =====
const viewport = CanvasViewport.viewport;
CanvasViewport.configure({
    shell, world,
    positionComposer: () => {
        const node = selectedNode();
        if(node && composer.classList.contains('open')) positionComposerForNode(node);
    },
    scheduleSave: () => scheduleSave(),
    scheduleCullCheck: () => scheduleCullCheck(),
    scheduleMinimapRender: () => scheduleMinimapRender(),
    scheduleImageUpgrade: () => scheduleImageUpgrade(),
    closeCreateMenu: () => closeCreateMenu(),
    getNodes: () => nodes,
    nodeRect: (n) => nodeRect(n)
});

// 兼容别名：safeScale 实现已入视口内核
const safeScale = CanvasViewport.safeScale;
function nodeScale(node){
    const v = Number(node?.scale);
    if((node?.images || []).length > 1 && v === MEDIA_GROUP_PREVIOUS_DEFAULT_SCALE) return MEDIA_GROUP_DEFAULT_SCALE;
    return Number.isFinite(v) && v > 0 ? v : 1;
}
const MEDIA_NODE_DEFAULT_SCALE = 2;
const MEDIA_GROUP_PREVIOUS_DEFAULT_SCALE = 1.6;
const MEDIA_GROUP_DEFAULT_SCALE = 0.8;
const MEDIA_GROUP_THUMB_BASE = 224;
const EMPTY_UPLOAD_NODE_WIDTH = 512;
const EMPTY_UPLOAD_NODE_HEIGHT = 288;
// 2026-10-10 统一节点默认尺寸口径（老王："统一尺寸，有选了比例的就按比例"）。
// 此前一张画布上并存三套默认：空节点 512×288（EMPTY_UPLOAD）、生成占位 520×293（pendingBoxSize）、
// MCP 文本节点 316×194 —— 同一个 16:9 的节点，手动建 / Agent 建 / 跑过一次，尺寸各不相同。
// 现在只留一套：有选定比例 → 按比例算盒（夹在 MEDIA_BOX_MAX_W×MEDIA_BOX_MAX_H 内）；
// 没选比例 → 空卡默认 512×288。新建 / 生成中 / 失败三态共用这一个盒，尺寸不再跳变。
const MEDIA_BOX_MAX_W = EMPTY_UPLOAD_NODE_WIDTH;
const MEDIA_BOX_MAX_H = 440;
function mediaBoxForRatio(ratio){
    if(!(Number(ratio?.w) > 0 && Number(ratio?.h) > 0)) return {w:EMPTY_UPLOAD_NODE_WIDTH, h:EMPTY_UPLOAD_NODE_HEIGHT};
    const fit = Math.min(MEDIA_BOX_MAX_W / ratio.w, MEDIA_BOX_MAX_H / ratio.h);
    return {w:Math.max(72, Math.round(ratio.w * fit)), h:Math.max(72, Math.round(ratio.h * fit))};
}
// 取「用户选定的输出比例」。没选（comfy 工作流、缺 ratio 字段）返回 null —— 不准拿默认值冒充用户选择。
function nodeOutputRatio(s){
    const st = s || {};
    if(st.apiKind === 'video'){
        const m = String(st.videoAspect || '').match(/^(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)$/);
        return m ? {w:Number(m[1]) || 16, h:Number(m[2]) || 9} : null;
    }
    if(st.engine === 'comfy'){
        if(st.comfyMode === 'text') return {w:Number(st.width) || 1024, h:Number(st.height) || 1024};
        return null; // comfy 工作流的真实尺寸由流程内部的分辨率节点决定，面板没有比例控件
    }
    if(!st.ratio) return null;
    const parsed = parseSizeValue(sizeForRun(st));
    return (Number(parsed?.width) > 0 && Number(parsed?.height) > 0) ? {w:Number(parsed.width), h:Number(parsed.height)} : null;
}
function nodeRatioBox(node, s){
    return mediaBoxForRatio(nodeOutputRatio(s || node?.runSettings));
}
// 生成失败/超时：把尺寸拨回「按比例的默认盒」。跑之前是它、生成中也是它，失败了就该还是它，
// 不能停在 pending 占位框上（老王："跑图都是先选了比例的，那失败了也不应该改变尺寸"）。
function restoreNodeBoxAfterFailure(node){
    if(!isSmartImageNode(node) || (node.images || []).length) return false;
    return CanvasGenerationLifecycle.restoreFrame(node, nodeRatioBox(node));
}
function mediaNodeDefaultScale(node){
    if((node?.images || []).length > 1 && !Number.isFinite(Number(node?.scale))) return MEDIA_GROUP_DEFAULT_SCALE;
    return Number.isFinite(Number(node?.scale)) && Number(node.scale) > 0 ? Number(node.scale) : MEDIA_NODE_DEFAULT_SCALE;
}
function createImageNodeAt(point, images=[], options={}){
    const layout = imageLayout(images || [], mediaNodeDefaultScale({type:'smart-image', images:images || []}), {type:'smart-image', images:images || []});
    return createNode((point?.x || 0) - Math.round(layout.width / 2), (point?.y || 0) - Math.round(layout.height / 2), images, options);
}
// 2026-10-19（老王：一个节点只装一张图）——本次多出来的图各自落成独立节点，
// 摆在基准节点右侧的空位（agentFindEmptySpot 负责避让），返回新建节点数组。
function spawnImageNodesForExtras(baseNode, extraImages=[], options={}){
    const extras = [...(extraImages || [])].filter(image => image && image.url);
    if(!extras.length) return [];
    const baseRect = baseNode ? nodeRect(baseNode) : null;
    let cursor = baseRect
        ? {x: Math.round(baseRect.x + baseRect.width + 24), y: Math.round(baseRect.y)}
        : {x: Number(options.x) || 0, y: Number(options.y) || 0};
    const created = [];
    for(const image of extras){
        const layout = imageLayout([image], MEDIA_NODE_DEFAULT_SCALE, {type:'smart-image', images:[image]});
        const w = Math.max(64, Math.round(Number(layout && layout.width) || 240));
        const h = Math.max(64, Math.round(Number(layout && layout.height) || 200));
        const spot = agentFindEmptySpot(cursor.x, cursor.y, w, h);
        const node = createImageNodeAt({x: spot.x + Math.round(w / 2), y: spot.y + Math.round(h / 2)}, [image], {select:false, skipUndo:true});
        if(!node) continue;
        delete node.w;
        delete node.h;
        const stem = String(image.name || '').replace(/\.[^.]+$/, '').replace(/[\/:*?"<>|]+/g, ' ').trim().slice(0, 30);
        if(stem && !['Image','Images','Video','Videos','Audio','Audios','Group','Media'].includes(stem)) node.title = stem;
        if(!node.outputKind) node.outputKind = 'image';
        created.push(node);
        cursor = {x: spot.x, y: spot.y + h + 24};
    }
    return created;
}
const AUTO_IMPORT_GROUP_CELL = 180;
const AUTO_IMPORT_GROUP_GAP = 10;
function imageSizeWithinBox(image, width, height){
    const natural = knownImageNaturalSize(image, true);
    const naturalW = Number(natural?.w || 0);
    const naturalH = Number(natural?.h || 0);
    if(!(naturalW > 0 && naturalH > 0)) return {width:Math.round(width), height:Math.round(height), known:false};
    const fit = Math.min(width / naturalW, height / naturalH);
    return {
        width:Math.max(1, Math.round(naturalW * fit)),
        height:Math.max(1, Math.round(naturalH * fit)),
        known:true
    };
}
function importedMediaNodeTitle(image){
    const kind = mediaKindForItem(image);
    return kind === 'video' ? 'Video' : kind === 'audio' ? 'Audio' : kind === 'text' ? 'Text' : kind === 'file' ? 'File' : 'Image';
}
function fitAutoGroupMemberToSlot(node, image){
    const slot = node?.autoGroupSlot;
    if(!slot || !image) return false;
    const size = imageSizeWithinBox(image, Number(slot.w) || AUTO_IMPORT_GROUP_CELL, Number(slot.h) || AUTO_IMPORT_GROUP_CELL);
    if(!size.known) return false;
    node.w = size.width;
    node.h = size.height;
    node.x = Math.round((Number(slot.x) || 0) + ((Number(slot.w) || AUTO_IMPORT_GROUP_CELL) - size.width) / 2);
    node.y = Math.round((Number(slot.y) || 0) + ((Number(slot.h) || AUTO_IMPORT_GROUP_CELL) - size.height) / 2);
    delete node.autoGroupSlot;
    return true;
}
// Existing groups retain their size reconciliation; creating groups is manual only.
function reconcileExistingAgentGroups(sourceNodes){
    const result = [...(sourceNodes || [])];
    let changed = false;
    // Existing saved groups need the same reconciliation as newly split results.
    // Metadata may arrive after grouping or a server merge may contain old cardSize.
    for(const group of result.filter(node => node.type === 'smart-group' && node.mcpGroupSourceId)){
        const members = (group.memberIds || []).map(id => result.find(node => node.id === id)).filter(Boolean);
        let resized = false;
        for(const member of members){
            const image = member.images?.length === 1 ? member.images[0] : null;
            const natural = knownImageNaturalSize(image, false);
            if(natural && reconcileSingleImageAspect(member, image, natural.w, natural.h, true)) resized = true;
        }
        if(resized || group.intrinsicLayoutVersion !== 1){
            // Old provisional cells can overlap after their real dimensions arrive.
            // Only move automatic cards that actually intersect an earlier member.
            const placed = [];
            for(const member of [...members].sort((a,b) => a.y-b.y || a.x-b.x)){
                if(member.cardSizing !== 'manual'){
                    for(const previous of placed){
                        const a = nodeRect(member), b = nodeRect(previous);
                        if(a.y < b.y+b.height && a.y+a.height > b.y && a.x < b.x+b.width && a.x+a.width > b.x){
                            member.x = Math.round(b.x+b.width+12);
                            changed = true;
                        }
                    }
                }
                placed.push(member);
            }
            if(group.intrinsicLayoutVersion !== 1){group.intrinsicLayoutVersion = 1;changed = true;}
        }
        if(members.length){
            const bounds = CanvasNodeLayoutController.createCanvasGroupForNodes(members, {addToStore:false});
            if(resized || ['x','y','w','h'].some(key => group[key] !== bounds[key])){
                group.x = bounds.x;group.y = bounds.y;group.w = bounds.w;group.h = bounds.h;
                changed = true;
            }
        }
    }
    result.mcpGroupChanged = changed;
    return result;
}
function singleImageLayout(image, node, scale){
    const explicitW = Number(node?.w);
    const explicitH = Number(node?.h);
    if(Number.isFinite(explicitW) && explicitW > 24 && Number.isFinite(explicitH) && explicitH > 24){
        return {cols:1, rows:1, width:Math.round(explicitW), height:Math.round(explicitH), thumb:Math.round(96 * scale), single:true};
    }
    const naturalW = Number(image?.natural_w || image?.width || 0);
    const naturalH = Number(image?.natural_h || image?.height || 0);
    if(naturalW > 0 && naturalH > 0){
        const maxW = 260 * scale;
        const maxH = 220 * scale;
        const fit = Math.min(maxW / naturalW, maxH / naturalH);
        return {
            cols:1,
            rows:1,
            width:Math.max(72, Math.round(naturalW * fit)),
            height:Math.max(72, Math.round(naturalH * fit)),
            thumb:Math.round(96 * scale),
            single:true
        };
    }
    return {cols:1, rows:1, width:Math.round(260*scale), height:Math.round(180*scale), thumb:Math.round(96*scale), single:true};
}
function groupImageGridLayout(count, explicitW, explicitH, maxThumb, pad=32, gap=8){
    let best = null;
    for(let cols = 1; cols <= count; cols++){
        const rows = Math.ceil(count / cols);
        const availableW = explicitW - pad - (cols - 1) * gap;
        const availableH = explicitH - pad - (rows - 1) * gap;
        if(availableW <= 0 || availableH <= 0) continue;
        const rawThumb = Math.floor(Math.min(availableW / cols, availableH / rows));
        const fittedThumb = Math.max(28, Math.min(maxThumb, rawThumb));
        const fits = rawThumb >= 28;
        const usedW = cols * fittedThumb + (cols - 1) * gap + pad;
        const usedH = rows * fittedThumb + (rows - 1) * gap + pad;
        const spareW = Math.max(0, explicitW - usedW);
        const spareH = Math.max(0, explicitH - usedH);
        const atMax = fittedThumb >= maxThumb;
        const score = [
            fits ? 1 : 0,
            fittedThumb,
            atMax ? cols : 0,
            -(spareW + spareH * 0.35),
            -rows
        ];
        let better = !best;
        if(best){
            for(let i = 0; i < score.length; i++){
                if(score[i] === best.score[i]) continue;
                better = score[i] > best.score[i];
                break;
            }
        }
        if(better){
            best = {cols, rows, thumb:fittedThumb, score};
        }
    }
    return best || {cols:Math.min(count, 2), rows:Math.ceil(count / Math.min(count, 2)), thumb:28};
}
function aspectGroupImageSize(image, maxSide){
    const limit = Math.max(1, Math.round(Number(maxSide) || 96));
    const naturalW = Number(image?.natural_w || image?.naturalWidth || image?.width || image?.w || 0);
    const naturalH = Number(image?.natural_h || image?.naturalHeight || image?.height || image?.h || 0);
    if(!(naturalW > 0 && naturalH > 0)) return {width:limit, height:limit};
    const fit = Math.min(limit / naturalW, limit / naturalH);
    return {width:Math.max(1, Math.round(naturalW * fit)), height:Math.max(1, Math.round(naturalH * fit))};
}
function aspectGroupGridBounds(images, maxSide, cols, gap=8){
    const safeCols = Math.max(1, Number(cols) || 1);
    const rowWidths = [], rowHeights = [];
    (images || []).forEach((image, index) => {
        const row = Math.floor(index / safeCols);
        const size = aspectGroupImageSize(image, maxSide);
        rowWidths[row] = (rowWidths[row] || 0) + size.width + (index % safeCols ? gap : 0);
        rowHeights[row] = Math.max(rowHeights[row] || 0, size.height);
    });
    return {
        width:Math.max(0, ...rowWidths),
        height:rowHeights.reduce((sum, height) => sum + height, 0) + Math.max(0, rowHeights.length - 1) * gap
    };
}
function smartNodeInputThumbRows(count){
    return count ? Math.ceil(Math.min(10, count) / 5) : 0;
}
function smartNodeInputThumbsHeight(images){
    const rows = smartNodeInputThumbRows((images || []).length);
    return rows ? rows * 44 + (rows - 1) * 6 + 8 : 0;
}
function promptNodeInputImages(node){
    if(!node?.llmEnabled) return [];
    return promptNodeInputMediaForLLM(node).filter(img => img?.url);
}
function promptNodeInputMediaForLLM(node){
    const refs = smartImageUsesWorkflowInput(node) ? workflowInputImagesFor(node) : inputImagesFor(node);
    return (refs || []).filter(ref => ref?.url);
}
function smartNodeInputThumbsHtml(images, opts={}){
    const refs = (images || []).filter(img => img?.url);
    if(!refs.length) return '';
    const limit = Math.min(10, refs.length);
    let audioCount = 0;
    const items = refs.slice(0, limit).map((img) => {
        const title = escapeHtml(img.name || '');
        const media = isAudioMediaItem(img)
            ? audioThumbHtml(audioThumbLabel(img, ++audioCount), title ? ` title="${title}"` : '')
            : isVideoMediaItem(img)
            ? `<video src="${escapeHtml(img.url)}" muted preload="metadata" playsinline disablepictureinpicture controlslist="nodownload noplaybackrate noremoteplayback"></video>`
            : `<img src="${escapeHtml(img.url)}" alt="">`;
        return `<div class="smart-node-input-thumb"${title ? ` title="${title}"` : ''}>${media}</div>`;
    }).join('');
    const more = refs.length > limit ? `<div class="smart-node-input-thumb smart-node-input-more">+${refs.length - limit}</div>` : '';
    return `<div class="smart-node-input-thumbs">${items}${more}</div>`;
}
function promptNodeExpandedHeight(node){
    return (node?.llmSystemEnabled ? 688 : 584) + smartNodeInputThumbsHeight(promptNodeInputImages(node));
}
function promptNodeLayoutSize(node){
    const oldCollapsedH = 460;
    const oldExpandedH = node?.llmSystemEnabled ? 800 : 680;
    const explicitW = Number(node?.w);
    const explicitH = Number(node?.h);
    const width = !Number.isFinite(explicitW) || explicitW === 360 ? 632 : explicitW;
    const fallbackH = node?.llmEnabled ? promptNodeExpandedHeight(node) : 388;
    const legacyExpandedH = node?.llmSystemEnabled ? 688 : 584;
    const height = !Number.isFinite(explicitH) || explicitH === oldCollapsedH || explicitH === oldExpandedH || explicitH === legacyExpandedH
        ? fallbackH
        : Math.max(explicitH, fallbackH);
    return {width:Math.round(width), height:Math.round(height)};
}
function nodeCardSpecKey(s){
    return JSON.stringify([s.engine,s.apiKind,s.ratio,s.videoAspect,s.resolution,s.customRatio,s.customSize]);
}
function preserveNodeCardForRun(node, s=node?.runSettings || {}){
    if(!isSmartImageNode(node) || isCanvasGroupNode(node) || node.type === 'smart-speech') return;
    // Capture the displayed box before outputs/pending state change, for every engine.
    const layout = imageLayout(node.images || [], nodeScale(node), node);
    CanvasGenerationLifecycle.lockFrame(node, layout);
}
function syncNodeCardToSpec(node){
    const s = node?.runSettings || {};
    if(!isSmartImageNode(node) || node.running || node.apiRunning || node.pending || node.jimengPending || ['running','queued'].includes(node.comfyStatus) || s.engine === 'comfy' || s.engine === 'blender') return false;
    let size;
    if(s.apiKind === 'video'){
        const match = String(s.videoAspect || '16:9').match(/^(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)$/);
        if(match) size = {width:Number(match[1]),height:Number(match[2])};
        else {
            const source = reducedRatioForImage(sourceRatioImageForNode(node));
            if(source) size = {width:source.w,height:source.h};
        }
    } else size = parseSizeValue(sizeForRun(s));
    if(!(size?.width > 0 && size?.height > 0)) return false;
    const ratio = size.width / size.height;
    const longSide = Math.max(Number(node.cardSize?.width) || EMPTY_UPLOAD_NODE_WIDTH, Number(node.cardSize?.height) || EMPTY_UPLOAD_NODE_HEIGHT);
    node.cardSize = {width:Math.round(ratio >= 1 ? longSide : longSide * ratio),height:Math.round(ratio >= 1 ? longSide / ratio : longSide)};
    node.cardSizing = 'spec';
    node.w = node.cardSize.width;
    node.h = node.cardSize.height;
    return true;
}
function imageLayout(images, scale=1, node=null){
    // 2026-10-10：Agent/MCP 建的生成节点没有 cardSize，成功后按图片自然尺寸落 520×293，
    // 跟手动节点（有 cardSize）的 512×288 差一截，产物落地瞬间还会"跳一下"。
    // 生成产物必然等于面板选的比例，所以：没 cardSize + 没被手动改过尺寸 + 单张生成产物
    // → 直接套按比例默认盒，跟生成中 / 失败态对齐。上传图、手动改过的节点一律不碰。
    const nodeImages = node?.images || images || [];
    const size = node?.cardSize
        || (nodeImages.length === 1 && nodeImages[0]?.generatedResult
            && !(Number(node?.w) > 24 && Number(node?.h) > 24)
            && nodeOutputRatio(node?.runSettings)
            ? (b => ({width:b.w, height:b.h}))(nodeRatioBox(node))
            : null);
    if(node?.type === 'smart-image' && Number(size?.width) > 24 && Number(size?.height) > 24){
        return intrinsicImageLayout(images, scale, {...node, w:size.width, h:size.height});
    }
    return intrinsicImageLayout(images, scale, node);
}
function intrinsicImageLayout(images, scale=1, node=null){
    if(node?.type === 'smart-speech'){
        if((node.speechLayout || 0) < 3){node.w=Math.max(1000,Number(node.w)||0); node.h=540; node.speechLayout=3;}
        return {cols:1, rows:1, width:Math.max(900, Number(node.w) || 1000), height:Math.max(520, Number(node.h) || 540), thumb:96, single:true};
    }
    if(node?.type === 'smart-prompt') return {cols:1, rows:1, ...promptNodeLayoutSize(node), thumb:96, single:true};
    if(node?.type === 'smart-loop') return {cols:1, rows:1, width:Math.round(Number(node.w) || smartLoopWidth(node)), height:Math.round(Math.max(Number(node.h) || 0, smartLoopHeight(node))), thumb:96, single:true};
    if(isCanvasGroupNode(node)) return {cols:1, rows:1, width:Math.max(80, Math.round(Number(node.w) || 80)), height:Math.max(80, Math.round(Number(node.h) || 80)), thumb:96, single:false};
    if(node?.groupLayout?.mode === 'preserve'){
        const pad = 12;
        const bounds = (images || []).reduce((max, img) => {
            const box = img?.groupPosition || {};
            const x = Math.max(0, Number(box.x) || 0);
            const y = Math.max(0, Number(box.y) || 0);
            const w = Math.max(28, Number(box.w) || 96);
            const h = Math.max(28, Number(box.h) || 96);
            return {width:Math.max(max.width, x + w + pad), height:Math.max(max.height, y + h + pad)};
        }, {width:0, height:0});
        return {cols:1, rows:1, width:Math.round(Math.max(Number(node.w) || 0, bounds.width || 96)), height:Math.round(Math.max(Number(node.h) || 0, bounds.height || 96)), thumb:96, single:false};
    }
    const count = (images || []).length;
    const s = node?.type === 'smart-image' || !node?.type ? mediaNodeDefaultScale(node) : (Number.isFinite(scale) && scale > 0 ? scale : 1);
    if(count === 0){
        const explicitW = Number(node?.w);
        const explicitH = Number(node?.h);
        // 2026-10-10 统一：pending 档原本是 260*s×180*s（16:9 输出下 = 520×360），跟空卡的
        // 512×288 又不是一回事，节点一跑就"忽大忽小"。现在空态 / 生成中共用同一个默认盒：
        // 有选比例就按比例（pendingBoxSize 也是这个盒，两者天然相等），没选就 512×288。
        const box = nodeRatioBox(node);
        const fallbackW = box.w;
        const fallbackH = box.h;
        return {
            cols:1,
            rows:1,
            width:Math.round(Number.isFinite(explicitW) && explicitW > 24 ? explicitW : fallbackW),
            height:Math.round(Number.isFinite(explicitH) && explicitH > 24 ? explicitH : fallbackH),
            thumb:Math.round(96*s),
            single:true
        };
    }
    if(count === 1) return singleImageLayout(images[0], node, s);
    const thumb = Math.round(MEDIA_GROUP_THUMB_BASE * s);
    const PAD = 40; // include the group padding and border when sizing the image area
    const GAP = 8;
    const grid = images.find(img => img?.grid?.type === 'grid-split')?.grid;
    const explicitW = Number(node?.w);
    const explicitH = Number(node?.h);
    if(grid){
        const cols = Math.max(1, Number(grid.cols || 1));
        const rows = Math.max(1, Number(grid.rows || 1));
        if(Number.isFinite(explicitW) && explicitW > 40 && Number.isFinite(explicitH) && explicitH > 40){
            const fittedThumb = Math.max(28, Math.floor(Math.min((explicitW - PAD - (cols - 1) * GAP) / cols, (explicitH - PAD - (rows - 1) * GAP) / rows)));
            return {cols, rows, width:Math.round(explicitW), height:Math.round(explicitH), thumb:fittedThumb};
        }
        const bounds = aspectGroupGridBounds(images, thumb, cols, GAP);
        return {cols, rows, width:Math.max(Math.round(226*s), bounds.width + PAD), height:bounds.height + PAD, thumb};
    }
    const cols = Math.min(4, Math.max(2, Math.ceil(Math.sqrt(count))));
    const rows = Math.ceil(count / cols);
    if(Number.isFinite(explicitW) && explicitW > 40 && Number.isFinite(explicitH) && explicitH > 40){
        const fitted = groupImageGridLayout(count, explicitW, explicitH, thumb, PAD, 8);
        return {cols:fitted.cols, rows:fitted.rows, width:Math.round(explicitW), height:Math.round(explicitH), thumb:fitted.thumb};
    }
    const bounds = aspectGroupGridBounds(images, thumb, cols, GAP);
    const width = Math.max(Math.round(226*s), bounds.width + PAD);
    const height = bounds.height + PAD;
    return {cols, rows, width, height, thumb};
}
function smartLoopCount(node){
    return Math.max(1, Math.min(100, Number(node?.count || 1) || 1));
}
function smartLoopWidth(node){
    return 340;
}
function smartLoopHeight(node){
    let h = 168;
    if(node?.imageInput) h += 72;
    if(node?.showPrompt) {
        const promptCount = Math.max(1, smartLoopPromptFieldValues(node).length);
        h += 94 + promptCount * 58 + smartLoopUpstreamPromptPreviewHeight(node);
    }
    h += smartNodeInputThumbsHeight(smartLoopPreviewImages(node));
    return h;
}
function fitSmartLoopNode(node){
    if(!node || node.type !== 'smart-loop') return;
    node.w = smartLoopWidth(node);
    node.h = smartLoopHeight(node);
}
function nodeRect(node){
    const layout = imageLayout(node.images || [], nodeScale(node), node);
    return {x:node.x || 0, y:node.y || 0, width:layout.width, height:layout.height};
}
// （视口裁剪实现已拆入 canvas-render-scheduler.js）
let nodeRenderStamp = 0;
function visibleNodeList(){
    return CanvasRenderScheduler.visibleNodeList();
}
function nodeRenderKey(html){
    let h = 2166136261;
    for(let i = 0; i < html.length; i++){
        h ^= html.charCodeAt(i);
        h = Math.imul(h, 16777619);
    }
    return (h >>> 0).toString(36);
}
function scheduleCullCheck(){
    CanvasRenderScheduler.scheduleCullCheck();
}
function scheduleImageUpgrade(){
    CanvasRenderScheduler.scheduleImageUpgrade();
}
function applyViewport(){
    CanvasViewport.applyViewport();
}
function scheduleViewportApply(){
    CanvasViewport.scheduleViewportApply();
}
function screenToWorld(event){
    return CanvasViewport.screenToWorld(event);
}
/* ===== 拖拽对齐辅助线（2026-10-05）=====
 * 独立 SVG 层，不塞进 svg.connection-layer：连接层 z-index:1，而节点是 1/2/4，
 * 辅助线会被节点盖住（吸附线必须压着节点才看得见对齐位置）。所以新开一层
 * .snap-guide-layer，z-index 抬到节点之上、pointer-events:none 保证不挡交互。
 * 坐标系与 #world 一致（绝对定位 left/top 0，viewBox 6000x4000），所以直接用世界坐标。
 */
function snapGuidesLayer(){
    let svg = world?.querySelector('svg.snap-guide-layer');
    if(!svg && world){
        svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('class', 'snap-guide-layer');
        svg.setAttribute('width', '6000');
        svg.setAttribute('height', '4000');
        svg.setAttribute('viewBox', '0 0 6000 4000');
        svg.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
        world.appendChild(svg);
    }
    return svg;
}
function renderSnapGuides(guides){
    const next = Array.isArray(guides) ? guides : [];
    snapGuides = next;
    const layer = snapGuidesLayer();
    if(!layer) return;
    if(!next.length){
        if(layer.childNodes.length) layer.replaceChildren();
        return;
    }
    // 线只画到有意义的范围：以命中轴为界，覆盖参与比对的节点，两端各留 40px 余量。
    const pad = 40;
    layer.replaceChildren();
    next.forEach(guide => {
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('class', 'snap-guide');
        if(guide.axis === 'x'){
            line.setAttribute('x1', String(Math.round(guide.at)));
            line.setAttribute('x2', String(Math.round(guide.at)));
            line.setAttribute('y1', String(Math.round((guide.from ?? 0) - pad)));
            line.setAttribute('y2', String(Math.round((guide.to ?? 0) + pad)));
        } else {
            line.setAttribute('y1', String(Math.round(guide.at)));
            line.setAttribute('y2', String(Math.round(guide.at)));
            line.setAttribute('x1', String(Math.round((guide.from ?? 0) - pad)));
            line.setAttribute('x2', String(Math.round((guide.to ?? 0) + pad)));
        }
        layer.appendChild(line);
    });
}
function syncComposerAdaptiveUi(){
    const active=CanvasViewport.isComposerAdaptive(),button=document.getElementById('canvasComposerAutoFitToggle');
    if(button){button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));button.title=active?'输入框位置自适应：开（自动避让窗口边缘）':'输入框位置自适应：关（始终固定在节点下方）';}
}
function toggleCanvasComposerAutoFit(){CanvasViewport.setComposerAdaptive(!CanvasViewport.isComposerAdaptive());syncComposerAdaptiveUi();}
function isSnapEnabled(){ return snapEnabled; }
function setSnapEnabled(value, opts = {}){
    snapEnabled = !!value;
    try { localStorage.setItem(SMART_CANVAS_SNAP_KEY, snapEnabled ? '1' : '0'); } catch(_) {}
    const btn = document.getElementById('canvasSnapToggle');
    if(btn){
        btn.classList.toggle('active', snapEnabled);
        btn.setAttribute('aria-pressed', snapEnabled ? 'true' : 'false');
        btn.title = snapEnabled ? tr('smart.snapOnTip') : tr('smart.snapOffTip');
    }
    if(!snapEnabled) renderSnapGuides([]);
    if(!opts.silent) toast(snapEnabled ? tr('smart.snapOn') : tr('smart.snapOff'));
}
function toggleSnap(){
    setSnapEnabled(!snapEnabled);
}
function viewportCenter(){
    return CanvasViewport.viewportCenter();
}
function scheduleMinimapRender(){
    CanvasRenderScheduler.scheduleMinimapRender();
}
function renderMinimap(){
    CanvasRenderScheduler.renderMinimap();
}
function minimapEventToWorld(event){
    return CanvasRenderScheduler.minimapEventToWorld(event);
}
function scheduleConnectionLayerRefresh(){
    if(connectionRenderFrame) return;
    connectionRenderFrame = requestAnimationFrame(() => {
        connectionRenderFrame = 0;
        refreshConnectionLayer();
    });
}
function scheduleImageMeasureRender(){
    if(imageMeasureRenderFrame) return;
    imageMeasureRenderFrame = requestAnimationFrame(() => {
        imageMeasureRenderFrame = 0;
        render();
    });
}
// ===== 任务控制台定位（tc-locate）=====
function tcLocateNode(nodeId){
    if(!nodeId) return false;
    const node = nodes.find(n => n.id === nodeId);
    if(!node) return false;
    canvasUiState.patchSelection({ids: []}, 'selectedIds');
    canvasUiState.patchSelection({primaryId: nodeId}, 'selectedId');
    const rect = nodeRect(node);
    centerViewportOnWorldPoint({x:rect.x + rect.width/2, y:rect.y + rect.height/2});
    syncSelectionUi();
    render();
    // 高亮闪烁：给节点 DOM 加瞬时类
    requestAnimationFrame(() => {
        const el = world.querySelector(`.image-node[data-id="${CSS.escape(nodeId)}"]`);
        if(el){
            el.classList.add('tc-flash');
            setTimeout(() => el.classList.remove('tc-flash'), 2200);
        }
    });
    return true;
}
window.__tcLocateNode = tcLocateNode;
window.addEventListener('message', function(event){
    const data = event.data || {};
    if(data.type === 'tc-locate-node'){
        const ok = tcLocateNode(String(data.node_id || ''));
        if(!ok && data.canvas_id && String(data.canvas_id) !== String(canvasId)){
            // 画布不匹配：跳转到目标画布并定位
            try { location.href = '/static/smart-canvas.html?id=' + encodeURIComponent(data.canvas_id) + '&focus_node=' + encodeURIComponent(data.node_id) + '&v=' + (window.SCRIPT_VER || ''); } catch(e){}
        }
    }
});

function centerViewportOnWorldPoint(point){
    CanvasViewport.centerViewportOnWorldPoint(point);
}
function fitAllNodesViewport(){
    CanvasViewport.fitAllNodesViewport();
}
function enterZoomPreview(){
    CanvasViewport.enterZoomPreview();
}
function exitZoomPreview(point=null){
    return CanvasViewport.exitZoomPreview(point);
}
function exitZoomPreviewToNode(nodeId){
    return CanvasViewport.exitZoomPreviewToNode(nodeId);
}
function toggleZoomPreview(){
    CanvasViewport.toggleZoomPreview();
}
function isCanvasWheelExcludedTarget(target){
    return CanvasViewport.isCanvasWheelExcludedTarget(target);
}
function isCanvasWheelScrollableOverlay(target){
    return CanvasViewport.isCanvasWheelScrollableOverlay(target);
}
function resetSmartCanvasRootScroll(){
    CanvasViewport.resetSmartCanvasRootScroll();
}
function lockSmartCanvasRootScroll(){
    CanvasViewport.lockSmartCanvasRootScroll();
}
function beginSmartCanvasScrollLock(){
    CanvasViewport.beginSmartCanvasScrollLock();
}
function openImagePreviewFromCanvasDblClick(event){
    if(event.target.closest('.image-delete, .smart-crop-action, .smart-node-action, .smart-image-name-label, .smart-image-name-input, .canvas-group-header, .node-port, button, input, textarea, select')) return false;
    const item = event.target.closest?.('.thumb-item,.image-wrap');
    const nodeEl = item?.closest?.('.image-node');
    if(!item || !nodeEl?.dataset?.id) return false;
    const nodeId = nodeEl.dataset.id;
    const imageIndex = Number(item.dataset.imageIndex || 0);
    if(!Number.isFinite(imageIndex)) return false;
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation?.();
    clearImageClickTimer();
    suppressImageClickUntil = Date.now() + 260;
    canvasUiState.patchSelection({primaryId: nodeId}, 'selectedId');
    canvasUiState.patchSelection({ids: []}, 'selectedIds');
    canvasUiState.patchSelection({image: {nodeId, index:imageIndex}}, 'selectedImage');
    bringNodesToFront(nodeId);
    openImagePreview(nodeId, imageIndex);
    return true;
}
function rememberCanvasPointerClient(event){
    CanvasViewport.rememberCanvasPointerClient(event);
}
function forgetCanvasPointerClient(){
    CanvasViewport.forgetCanvasPointerClient();
}
function canvasWheelAnchorPoint(event){
    return CanvasViewport.canvasWheelAnchorPoint(event);
}
function zoomViewportAtClientPoint(event){
    return CanvasViewport.zoomViewportAtClientPoint(event);
}
function imageProviders(){
    // RunningHub 内置平台带标准生图模型（rhart/seedream 等），需作为生图平台出现在节点；
    // 火山引擎走独立引擎、Comfy/模型广场另有入口，故这里仅排除它们。
    return (apiProviders || []).filter(p => p.enabled !== false && p.id !== 'volcengine' && p.id !== 'blender' && (p.image_models || []).length);
}
function volcengineProvider(){
    return (apiProviders || []).find(p => p.id === 'volcengine' && p.enabled !== false) || {
        id:'volcengine',
        name:'火山引擎',
        image_models:[],
        video_models:[],
        enabled:true
    };
}
function runningHubProvider(){
    return (apiProviders || []).find(p => p.id === 'runninghub' && p.enabled !== false) || null;
}
function runningHubEntries(kind){
    const provider = runningHubProvider();
    const key = kind === 'workflow' ? 'rh_workflows' : 'rh_apps';
    return Array.isArray(provider?.[key]) ? provider[key].filter(item => item?.enabled !== false && item?.hidden !== true) : [];
}
function runningHubEntryId(entry, kind) {
    return CanvasRhControls.runningHubEntryId.apply(null, arguments);
}
function runningHubEntryLabel(entry, kind) {
    return CanvasRhControls.runningHubEntryLabel.apply(null, arguments);
}
function runningHubEntryKey(kind, id) {
    return CanvasRhControls.runningHubEntryKey.apply(null, arguments);
}
function parseRunningHubEntryKey(value) {
    return CanvasRhControls.parseRunningHubEntryKey.apply(null, arguments);
}
function runningHubAllEntries(){
    return [
        ...runningHubEntries('app').map(entry => ({kind:'app', id:runningHubEntryId(entry, 'app'), entry})).filter(x => x.id),
        ...runningHubEntries('workflow').map(entry => ({kind:'workflow', id:runningHubEntryId(entry, 'workflow'), entry})).filter(x => x.id)
    ];
}
function selectedRunningHubRef(sourceSettings=settings){
    const all = runningHubAllEntries();
    sourceSettings = sourceSettings || settings;
    const parsed = parseRunningHubEntryKey(sourceSettings.rhConfigKey || '');
    let ref = parsed ? all.find(item => item.kind === parsed.kind && item.id === parsed.id) : null;
    if(!ref && all.length) ref = all[0];
    if(ref && sourceSettings === settings) settings.rhConfigKey = runningHubEntryKey(ref.kind, ref.id);
    return ref || null;
}
function rhEntryFields(entry) {
    return CanvasRhControls.rhEntryFields.apply(null, arguments);
}
function rhWorkflowJsonFromSources(...sources) {
    return CanvasRhControls.rhWorkflowJsonFromSources.apply(null, arguments);
}
function rhCurrentKind(sourceSettings=settings){
    return selectedRunningHubRef(sourceSettings)?.kind || 'app';
}
// RunningHub 云端工作流的「节点开关」（对齐本地 ComfyUI 的 comfyModes 语义）：
// settings.rhNodeOff[<kind>:<id>][<nodeId>] === true 表示该节点被关闭。
// 关闭 = 不渲染它的参数 + 提交时把该节点从 workflow JSON 中裁剪掉（下游引用一并断开）。
function rhNodeOffBucket(sourceSettings=settings){
    const source = sourceSettings || settings;
    const store = (source.rhNodeOff && typeof source.rhNodeOff === 'object') ? source.rhNodeOff : {};
    source.rhNodeOff = store;
    const ref = selectedRunningHubRef(source);
    if(!ref) return {};
    const bucket = store[runningHubEntryKey(ref.kind, ref.id)];
    return (bucket && typeof bucket === 'object') ? bucket : {};
}
function rhNodeOffIds(sourceSettings=settings) {
    return CanvasRhControls.rhNodeOffIds.apply(null, arguments);
}
function rhNodeIsOff(nodeId, sourceSettings=settings) {
    return CanvasRhControls.rhNodeIsOff.apply(null, arguments);
}
// Provider 目录域外移 canvas-provider-catalog.js（第四刀，双段：rhNodeOff 开关 + chat/video provider 解析/引擎下拉）。
if(globalThis.CanvasProviderCatalog){CanvasProviderCatalog.configure({
        activeComposerNode: (...a) => activeComposerNode(...a),
        clearVolcengineSelectionOutsideVolcengine: (...a) => clearVolcengineSelectionOutsideVolcengine(...a),
        enhanceAgentSelects: (...a) => enhanceAgentSelects(...a),
        escapeHtml: (...a) => escapeHtml(...a),
        imageProviders: (...a) => imageProviders(...a),
        imageRefsOnly: (...a) => imageRefsOnly(...a),
        manualSmartVideoLink: (...a) => manualSmartVideoLink(...a),
        normalizeComfyWorkflowSelection: (...a) => normalizeComfyWorkflowSelection(...a),
        persistActiveSmartSettings: (...a) => persistActiveSmartSettings(...a),
        renderDynamicParams: (...a) => renderDynamicParams(...a),
        rhEntryFields: (...a) => rhEntryFields(...a),
        rhFieldKind: (...a) => rhFieldKind(...a),
        rhNodeIsOff: (...a) => rhNodeIsOff(...a),
        runningHubEntries: (...a) => runningHubEntries(...a),
        runningHubEntryKey: (...a) => runningHubEntryKey(...a),
        runningHubProvider: (...a) => runningHubProvider(...a),
        scheduleSave: (...a) => scheduleSave(...a),
        selectedNode: (...a) => selectedNode(...a),
        selectedRunningHubRef: (...a) => selectedRunningHubRef(...a),
        videoRefsOnly: (...a) => videoRefsOnly(...a),
        visibleReferenceImagesFor: (...a) => visibleReferenceImagesFor(...a),
        volcengineProvider: (...a) => volcengineProvider(...a),
        PROVIDER_MODEL_DISPLAY: () => PROVIDER_MODEL_DISPLAY,
        apiProviders: () => apiProviders,
        comfyInstanceCount: () => comfyInstanceCount,
        comfyWorkflows: () => comfyWorkflows,
        engineSelect: () => engineSelect,
        runningHubWorkflowCache: () => runningHubWorkflowCache,
        settings: () => settings
});}
function rhToggleNodeOff(){return CanvasProviderCatalog.rhToggleNodeOff.apply(null, arguments);}
function rhActiveFields(){return CanvasProviderCatalog.rhActiveFields.apply(null, arguments);}
function sortRunningHubFields(){return CanvasProviderCatalog.sortRunningHubFields.apply(null, arguments);}
function chatApiProviders(){return CanvasProviderCatalog.chatApiProviders.apply(null, arguments);}
function resolveChatProviderId(){return CanvasProviderCatalog.resolveChatProviderId.apply(null, arguments);}
function providerChatModels(){return CanvasProviderCatalog.providerChatModels.apply(null, arguments);}
function resolveChatModel(){return CanvasProviderCatalog.resolveChatModel.apply(null, arguments);}
function chatProviderOptions(){return CanvasProviderCatalog.chatProviderOptions.apply(null, arguments);}
function chatModelOptions(){return CanvasProviderCatalog.chatModelOptions.apply(null, arguments);}
function apiProviderById(){return CanvasProviderCatalog.apiProviderById.apply(null, arguments);}
function videoProviderPlatform(){return CanvasProviderCatalog.videoProviderPlatform.apply(null, arguments);}
function providerImageModels(){return CanvasProviderCatalog.providerImageModels.apply(null, arguments);}
function providerModelDisplayName(){return CanvasProviderCatalog.providerModelDisplayName.apply(null, arguments);}
function jimengImageEditMode(){return CanvasProviderCatalog.jimengImageEditMode.apply(null, arguments);}
function filterJimengImageModels(){return CanvasProviderCatalog.filterJimengImageModels.apply(null, arguments);}
function syncJimengModelPillForRefs(){return CanvasProviderCatalog.syncJimengModelPillForRefs.apply(null, arguments);}
function jimengVideoCommand(){return CanvasProviderCatalog.jimengVideoCommand.apply(null, arguments);}
function filterJimengVideoModels(){return CanvasProviderCatalog.filterJimengVideoModels.apply(null, arguments);}
function syncJimengVideoModelPillForRefs(){return CanvasProviderCatalog.syncJimengVideoModelPillForRefs.apply(null, arguments);}
function sanitizeSmartApiSelection(){return CanvasProviderCatalog.sanitizeSmartApiSelection.apply(null, arguments);}
function videoApiProviders(){return CanvasProviderCatalog.videoApiProviders.apply(null, arguments);}
function videoProviderById(){return CanvasProviderCatalog.videoProviderById.apply(null, arguments);}
function providerVideoModels(){return CanvasProviderCatalog.providerVideoModels.apply(null, arguments);}
function volcengineVideoModels(){return CanvasProviderCatalog.volcengineVideoModels.apply(null, arguments);}
function smartAvailableEngines(){return CanvasProviderCatalog.smartAvailableEngines.apply(null, arguments);}
function smartEngineLabel(){return CanvasProviderCatalog.smartEngineLabel.apply(null, arguments);}
function syncEngineSelectOptions(){return CanvasProviderCatalog.syncEngineSelectOptions.apply(null, arguments);}
let previzLlmPanelOpen = false;
function closePrevizLlmPanel(){
    if(!previzLlmPanelOpen) return;
    previzLlmPanelOpen = false;
    renderDynamicParams();
}
function normalizePrevizLlmSettings(target=settings){
    if(!target || typeof target !== 'object') return target;
    target.previzLlmEnabled = target.previzLlmEnabled === true;
    target.previzLlmProvider = resolveChatProviderId(target.previzLlmProvider || '');
    target.previzLlmModel = resolveChatModel(target.previzLlmModel || '', target.previzLlmProvider);
    return target;
}
function renderPrevizLlmControl(){
    normalizePrevizLlmSettings(settings);
    const enabled = settings.previzLlmEnabled === true;
    const panelOpen = enabled && previzLlmPanelOpen;
    return `<div class="previz-llm-row">
        <button type="button" class="prompt-node-pill previz-llm-toggle ${enabled ? 'active' : ''}" title="先用 LLM 整理镜头，再生成 Blender 预演">
            <i data-lucide="sparkles"></i><span>LLM</span>
        </button>
        ${panelOpen ? `
            <div class="previz-llm-panel">
                <div class="smart-control previz-llm-select previz-llm-provider-ctl" data-ctl="provider">
                    <button type="button" class="smart-pill previz-llm-select-pill"><span class="previz-llm-select-label"></span><i data-lucide="chevron-down" class="pill-caret"></i></button>
                    <div class="smart-popover previz-llm-select-popover">
                        <div class="previz-llm-select-list"></div>
                    </div>
                </div>
                <div class="smart-control previz-llm-select previz-llm-model-ctl" data-ctl="model">
                    <button type="button" class="smart-pill previz-llm-select-pill"><span class="previz-llm-select-label"></span><i data-lucide="chevron-down" class="pill-caret"></i></button>
                    <div class="smart-popover previz-llm-select-popover">
                        <div class="previz-llm-select-list"></div>
                    </div>
                </div>
                <button type="button" class="previz-llm-disable" title="关闭 LLM"><i data-lucide="power"></i><span>关闭 LLM</span></button>
            </div>
        ` : ''}
    </div>`;
}
function bindPrevizLlmControl(){
    normalizePrevizLlmSettings(settings);
    const toggle = document.querySelector('.previz-llm-toggle');
    if(toggle){
        toggle.onclick = e => {
            e.preventDefault();
            e.stopPropagation();
            if(!settings.previzLlmEnabled){
                settings.previzLlmEnabled = true;
                normalizePrevizLlmSettings(settings);
                previzLlmPanelOpen = true;
            } else {
                previzLlmPanelOpen = !previzLlmPanelOpen;
            }
            renderDynamicParams();
            persistActiveSmartSettings();
        };
    }
    const disableEl = document.querySelector('.previz-llm-disable');
    if(disableEl){
        disableEl.onclick = e => {
            e.preventDefault();
            e.stopPropagation();
            settings.previzLlmEnabled = false;
            previzLlmPanelOpen = false;
            renderDynamicParams();
            persistActiveSmartSettings();
        };
    }
    const providerCtl = document.querySelector('.previz-llm-provider-ctl');
    if(providerCtl){
        const label = providerCtl.querySelector('.previz-llm-select-label');
        const list = providerCtl.querySelector('.previz-llm-select-list');
        const pill = providerCtl.querySelector('.previz-llm-select-pill');
        const providers = chatApiProviders();
        const curP = resolveChatProviderId(settings.previzLlmProvider);
        if(label) label.textContent = (providers.find(p => p.id === curP) || {}).name || curP;
        if(list){
            list.innerHTML = providers.map(p => `<button type="button" class="previz-llm-opt ${p.id === curP ? 'active' : ''}" data-val="${escapeAttr(p.id)}" title="${escapeHtml(p.name || p.id)}"><span>${escapeHtml(p.name || p.id)}</span>${p.id === curP ? '<span class="previz-llm-opt-check">✓</span>' : ''}</button>`).join('');
        }
        if(pill) pill.onclick = event => {
            event.preventDefault();
            event.stopPropagation();
            const wasPinned = providerCtl.classList.contains('pinned');
            closeAllSmartPopovers();
            if(wasPinned && providerCtl.contains(document.activeElement)) document.activeElement.blur();
            if(!wasPinned) providerCtl.classList.add('pinned');
        };
        providerCtl.querySelectorAll('.previz-llm-opt').forEach(opt => {
            opt.addEventListener('click', e => {
                e.preventDefault(); e.stopPropagation();
                const val = opt.dataset.val || '';
                if(!val) return;
                settings.previzLlmProvider = resolveChatProviderId(val);
                settings.previzLlmModel = resolveChatModel('', settings.previzLlmProvider);
                previzLlmPanelOpen = true;
                renderDynamicParams();
                persistActiveSmartSettings();
            });
        });
    }
    const modelCtl = document.querySelector('.previz-llm-model-ctl');
    if(modelCtl){
        const label = modelCtl.querySelector('.previz-llm-select-label');
        const list = modelCtl.querySelector('.previz-llm-select-list');
        const pill = modelCtl.querySelector('.previz-llm-select-pill');
        const models = providerChatModels(resolveChatProviderId(settings.previzLlmProvider));
        const curM = resolveChatModel(settings.previzLlmModel, settings.previzLlmProvider);
        if(label) label.textContent = curM;
        if(list){
            list.innerHTML = [...new Set([curM, ...models].filter(Boolean))].map(m => `<button type="button" class="previz-llm-opt ${m === curM ? 'active' : ''}" data-val="${escapeAttr(m)}" title="${escapeHtml(m)}"><span>${escapeHtml(m)}</span>${m === curM ? '<span class="previz-llm-opt-check">✓</span>' : ''}</button>`).join('');
        }
        if(pill) pill.onclick = event => {
            event.preventDefault();
            event.stopPropagation();
            const wasPinned = modelCtl.classList.contains('pinned');
            closeAllSmartPopovers();
            if(wasPinned && modelCtl.contains(document.activeElement)) document.activeElement.blur();
            if(!wasPinned) modelCtl.classList.add('pinned');
        };
        modelCtl.querySelectorAll('.previz-llm-opt').forEach(opt => {
            opt.addEventListener('click', e => {
                e.preventDefault(); e.stopPropagation();
                const val = opt.dataset.val || '';
                if(!val) return;
                settings.previzLlmModel = val;
                persistActiveSmartSettings();
            });
        });
    }
}
document.addEventListener('click', event => {
    if(!previzLlmPanelOpen) return;
    if(event.target.closest('.previz-llm-row')) return;
    closePrevizLlmPanel();
});
document.addEventListener('keydown', event => {
    if(event.key === 'Escape') closePrevizLlmPanel();
});
function renderVideoProviderControl(providers) {
    return CanvasParamControls.renderVideoProviderControl.apply(null, arguments);
}
function renderVideoModelControl(models) {
    return CanvasParamControls.renderVideoModelControl.apply(null, arguments);
}
function renderVideoDurationControl() {
    return CanvasParamControls.renderVideoDurationControl.apply(null, arguments);
}
function renderVideoAspectControl() {
    return CanvasParamControls.renderVideoAspectControl.apply(null, arguments);
}
function renderVideoResolutionControl() {
    return CanvasParamControls.renderVideoResolutionControl.apply(null, arguments);
}
function videoAspectOptions() {
    return CanvasSpecControls.videoAspectOptions.apply(null, arguments);
}
function videoResolutionOptions(){
    return [['', tr('smart.videoResAuto')], ['480p','480P'], ['720p','720P'], ['1080p','1080P'], ['4k','4K']];
}
function videoDurationValue(source=settings){
    return Math.max(1, Math.min(60, Number(source?.videoDuration) || 5));
}
function videoResolutionLabel(source=settings){
    const options = videoResolutionOptions();
    const value = source?.videoResolution || '';
    const labelMap = Object.fromEntries(options);
    return labelMap[value] || value || tr('smart.videoResAuto');
}
function videoAspectLabel(source=settings) {
    return CanvasSpecControls.videoAspectLabel.apply(null, arguments);
}
function renderVideoSpecControl() {
    return CanvasParamControls.renderVideoSpecControl.apply(null, arguments);
}
function imageSpecOptions() {
    return CanvasSpecControls.imageSpecOptions.apply(null, arguments);
}
function imageQualityLabel(source=settings) {
    return CanvasSpecControls.imageQualityLabel.apply(null, arguments);
}
function renderImageSpecControl() {
    return CanvasParamControls.renderImageSpecControl.apply(null, arguments);
}
function syncImageSpecControl(){
    const control = dynamicParams?.querySelector('.image-spec-control');
    if(!control) return;
    const ratio = settings.ratio || 'square';
    const resolution = settings.resolution || '1k';
    const quality = settings.quality || 'auto';
    const count = Number(settings.count || 1);
    const pillText = control.querySelector('.smart-pill span');
    if(pillText){
        // 合并 pill（.combo-spec-count）文本含数量；普通规格 pill 不带
        if(control.classList.contains('combo-spec-count')){
            pillText.textContent = `${ratioLabel('')} · ${resolutionLabel('')} · ${imageQualityLabel()} · ${count}张`;
        } else {
            pillText.textContent = `${ratioLabel('')} · ${resolutionLabel('')} · ${imageQualityLabel()}`;
        }
    }
    control.querySelectorAll('[data-smart-param="ratio"]').forEach(btn => btn.classList.toggle('active', btn.dataset.smartValue === ratio));
    control.querySelectorAll('[data-smart-param="resolution"]').forEach(btn => btn.classList.toggle('active', btn.dataset.smartValue === resolution));
    control.querySelectorAll('[data-smart-param="quality"]').forEach(btn => btn.classList.toggle('active', btn.dataset.smartValue === quality));
    control.querySelectorAll('[data-smart-param="count"]').forEach(btn => btn.classList.toggle('active', Number(btn.dataset.smartValue) === count));
}
function setImageSpecSetting(key, value){
    const prevRatio = settings.ratio;
    const prevResolution = settings.resolution;
    setDynamicSetting(key, value, {keepLayout:true});
    // 自定义输入行只在 ratio/resolution 切到/切离 custom 时才需要重建布局
    const needRerender = (key === 'ratio' && (value === 'custom' || prevRatio === 'custom'))
        || (key === 'resolution' && (value === 'custom' || prevResolution === 'custom'));
    if(needRerender){
        renderDynamicParams();
        // 重建后弹层会被一并关掉；重新钉住，让用户直接看到刚出现的自定义输入行
        const ctrl = dynamicParams?.querySelector('.image-spec-control');
        if(ctrl) ctrl.classList.add('pinned');
    }
    else syncImageSpecControl();
}
function renderVideoToggleControl(key, label) {
    return CanvasParamControls.renderVideoToggleControl.apply(null, arguments);
}
function renderTempShUploadControl(){
    return `<button type="button" class="smart-pill cloud-upload-pill" data-temp-sh-upload-video title="上传当前输入图片或视频到云端直链"><i data-lucide="upload-cloud"></i><span>上传云端</span></button>`;
}
function renderManualVideoUrlControl(){
    return `<button type="button" class="smart-pill manual-video-url-pill" data-manual-video-url title="手动输入媒体 URL"><i data-lucide="link"></i><span>输入网址</span></button>`;
}
function videoReferenceModeValue(source=settings){
    const value = String(source?.videoReferenceMode || '').trim();
    // 官方收敛后的合法枚举
    if(['mixed','first_last','video_edit','video_extend'].includes(value)) return value;
    // 旧数据兼容：仅视频参考→全能参考；抽帧参考→全能参考（抽帧改为后端自动兜底）
    if(value === 'video_only' || value === 'frame_extract') return 'mixed';
    if(source?.videoUseFrameRoles) return 'first_last';
    return 'mixed';
}
function renderVideoReferenceModeControl() {
    return CanvasParamControls.renderVideoReferenceModeControl.apply(null, arguments);
}
function shouldShowVideoReferenceModeControl(){
    if(!isApiLikeEngine(settings.engine) || settings.apiKind !== 'video') return false;
    return true;
}
function renderComposerReferenceModeSlot(){
    if(!composerReferenceModeSlot) return;
    let html = shouldShowVideoReferenceModeControl() ? renderVideoReferenceModeControl() : '';
    // 视频延长模式：追加「向前/向后」方向下拉
    if(html && videoReferenceModeValue(settings) === 'video_extend') html += renderVideoExtendDirectionControl();
    composerReferenceModeSlot.innerHTML = html;
    bindComposerReferenceModeControl();
}
// 可信素材模式：打开后可选择素材来源——素材库认证链接 / 自行上传云端 / 自行输入网址。
// 视频/RH参数+Comfy工作流带外移 canvas-video-comfy-params.js（第十七刀）。块内零整写，值型走 getter。
if(globalThis.CanvasVideoComfyParams){CanvasVideoComfyParams.configure({
        bindDynamicParams: (...a) => bindDynamicParams(...a),
        clearVolcengineSelectionOutsideVolcengine: (...a) => clearVolcengineSelectionOutsideVolcengine(...a),
        comfyFieldKind: (...a) => comfyFieldKind(...a),
        filterJimengImageModels: (...a) => filterJimengImageModels(...a),
        imageProviders: (...a) => imageProviders(...a),
        imageRefsOnly: (...a) => imageRefsOnly(...a),
        isApiLikeEngine: (...a) => isApiLikeEngine(...a),
        persistActiveSmartSettings: (...a) => persistActiveSmartSettings(...a),
        providerImageModels: (...a) => providerImageModels(...a),
        relocateComposerSlotsToParamRow: (...a) => relocateComposerSlotsToParamRow(...a),
        renderApiVideoParams: (...a) => renderApiVideoParams(...a),
        renderComboSpecCount: (...a) => renderComboSpecCount(...a),
        renderComfyParams: (...a) => renderComfyParams(...a),
        renderComposerReferenceModeSlot: (...a) => renderComposerReferenceModeSlot(...a),
        renderComposerStyleControl: (...a) => renderComposerStyleControl(...a),
        renderQualityControl: (...a) => renderQualityControl(...a),
        renderResolutionControl: (...a) => renderResolutionControl(...a),
        renderRunningHubParams: (...a) => renderRunningHubParams(...a),
        renderUnifiedPickerControl: (...a) => renderUnifiedPickerControl(...a),
        renderVolcengineParams: (...a) => renderVolcengineParams(...a),
        renderVolcengineVideoParams: (...a) => renderVolcengineVideoParams(...a),
        resolveComfyWorkflowName: (...a) => resolveComfyWorkflowName(...a),
        smartAvailableEngines: (...a) => smartAvailableEngines(...a),
        syncApiKindToggleVisibility: (...a) => syncApiKindToggleVisibility(...a),
        syncEngineSelectOptions: (...a) => syncEngineSelectOptions(...a),
        updatePromptPlaceholder: (...a) => updatePromptPlaceholder(...a),
        videoReferenceModeValue: (...a) => videoReferenceModeValue(...a),
        RES_LONG_SIDE: () => RES_LONG_SIDE,
        RES_PIXEL_LIMIT: () => RES_PIXEL_LIMIT,
        SIZE_MAP: () => SIZE_MAP,
        comfyWorkflowCache: () => comfyWorkflowCache,
        comfyWorkflows: () => comfyWorkflows,
        composer: () => composer,
        composerSlotHomes: () => composerSlotHomes,
        dynamicParams: () => dynamicParams,
        settings: () => settings
});}
function renderVideoExtendDirectionControl(){return CanvasVideoComfyParams.renderVideoExtendDirectionControl.apply(null, arguments);}
function parseSizeValue(){return CanvasVideoComfyParams.parseSizeValue.apply(null, arguments);}
function apiImageSize(){return CanvasVideoComfyParams.apiImageSize.apply(null, arguments);}
function rhOfficialModelForRun(){return CanvasVideoComfyParams.rhOfficialModelForRun.apply(null, arguments);}
function shouldUseRhOfficialProxy(){return CanvasVideoComfyParams.shouldUseRhOfficialProxy.apply(null, arguments);}
function rhOfficialResolutionForRun(){return CanvasVideoComfyParams.rhOfficialResolutionForRun.apply(null, arguments);}
function rhOfficialAspectRatioForRun(){return CanvasVideoComfyParams.rhOfficialAspectRatioForRun.apply(null, arguments);}
function normalizeApiSizeSettings(){return CanvasVideoComfyParams.normalizeApiSizeSettings.apply(null, arguments);}
function ensureComfyWorkflow(){return CanvasVideoComfyParams.ensureComfyWorkflow.apply(null, arguments);}
function currentComfyWorkflowData(){return CanvasVideoComfyParams.currentComfyWorkflowData.apply(null, arguments);}
function currentComfyFields(){return CanvasVideoComfyParams.currentComfyFields.apply(null, arguments);}
function comfyFieldMeta(){return CanvasVideoComfyParams.comfyFieldMeta.apply(null, arguments);}
function normalizeComfyWorkflowSelection(){return CanvasVideoComfyParams.normalizeComfyWorkflowSelection.apply(null, arguments);}
function ensureCustomComfyWorkflowReady(){return CanvasVideoComfyParams.ensureCustomComfyWorkflowReady.apply(null, arguments);}
function allowsPromptlessCustomComfy(){return CanvasVideoComfyParams.allowsPromptlessCustomComfy.apply(null, arguments);}
function comfyParamValue(){return CanvasVideoComfyParams.comfyParamValue.apply(null, arguments);}
function formatComfySliderValue(){return CanvasVideoComfyParams.formatComfySliderValue.apply(null, arguments);}
function updateComfySliderValueLabel(){return CanvasVideoComfyParams.updateComfySliderValueLabel.apply(null, arguments);}
function updateProviderModels(){return CanvasVideoComfyParams.updateProviderModels.apply(null, arguments);}
function renderDynamicParams(){return CanvasVideoComfyParams.renderDynamicParams.apply(null, arguments);}
function normalizeHiddenVideoToggles(){return CanvasVideoComfyParams.normalizeHiddenVideoToggles.apply(null, arguments);}
// API 视频单排：平台+模型合并下拉（与图片版 renderEngineModelCombo 同款）
function renderVideoEngineModelCombo(models) {
    return CanvasParamControls.renderVideoEngineModelCombo.apply(null, arguments);
}
function renderApiVideoParams(){
    normalizeHiddenVideoToggles();
    const providers = videoApiProviders();
    if(!settings.videoProvider || !providers.some(p => p.id === settings.videoProvider)){
        // 无配置视频平台时兜底到豆包（volcengine 有视频模型即视为可用）
        const volc = volcengineProvider();
        if(!providers.length && volc && (volc.video_models || []).length){
            settings.videoProvider = 'volcengine';
        } else {
            settings.videoProvider = providers[0]?.id || '';
        }
    }
    const models = filterJimengVideoModels(providerVideoModels(settings.videoProvider));
    if(!settings.videoModel || !models.includes(settings.videoModel)) settings.videoModel = models[0] || '';
    dynamicParams.innerHTML = `
        ${renderUnifiedPickerControl()}
        ${renderVideoSpecControl()}
    `;
}
function renderVolcengineParams(){
    const provider = volcengineProvider();
    const providers = [provider];
    const models = providerImageModels('volcengine');
    settings.provider_id = 'volcengine';
    if(!settings.model || !models.includes(settings.model)) settings.model = models[0] || '';
    normalizeApiSizeSettings('');
    const outpaintLocked = settings.outpaintResolutionLocked === true;
    // 2026-09-16：同上（API 图片参数），自定义比例/尺寸输入框移入规格弹层内部。
    dynamicParams.innerHTML = `
        ${renderUnifiedPickerControl()}
        ${outpaintLocked ? `${renderResolutionControl('')}${renderQualityControl()}` : renderComboSpecCount()}
    `;
}
function renderVolcengineVideoParams(){
    normalizeHiddenVideoToggles();
    const provider = volcengineProvider();
    const providers = [provider];
    const models = volcengineVideoModels();
    settings.videoProvider = 'volcengine';
    if(!settings.videoModel || !models.includes(settings.videoModel)) settings.videoModel = models[0] || '';
    dynamicParams.innerHTML = `
        ${renderUnifiedPickerControl()}
        ${renderVideoSpecControl()}
    `;
}
function renderRunningHubParams(){
    if(!runningHubAllEntries().some(item => runningHubEntryKey(item.kind, item.id) === settings.rhConfigKey)){
        settings.rhConfigKey = '';
    }
    const ref = selectedRunningHubRef();
    const fields = rhActiveFields();
    settings.rhPayment = settings.rhPayment === 'wallet' ? 'wallet' : 'free';
    settings.rhParams = settings.rhParams || {};
    settings.rhRandomActive = settings.rhRandomActive || {};
    settings.rhNodeOff = (settings.rhNodeOff && typeof settings.rhNodeOff === 'object') ? settings.rhNodeOff : {};
    // 节点开关要列节点清单，需要 workflow JSON。缓存里没有就先异步取一次，到手后重绘
    // （与本地 ComfyUI 的 ensureComfyWorkflow().then(renderDynamicParams) 同一套路）。
    if(ref?.kind === 'workflow' && !Object.keys(rhWorkflowJsonForRef(ref)).length){
        ensureRunningHubWorkflow(ref.id)
            .then(() => { if(settings.engine === 'runninghub') renderDynamicParams(); })
            .catch(() => {});
    }
    // 2026-09-15 用户要求：删掉底部提示文字说明（原「请先在 API 设置里…」）。
    if(!ref){
        dynamicParams.innerHTML = `<div class="cfn-controls">${renderUnifiedPickerControl()}${renderRhResourceControl()}</div>`;
        return;
    }
    // 2026-09-15 用户要求：底部按钮两两合并为两个入口（不是合成一个）。
    // 入口① = 引擎下拉「RH-API·工作流」+ 工作流选择器；入口② = 「RunningHub币」+「24G 显存」。
    // 选项仍沿用 data-smart-param/data-smart-value，取值与生成逻辑完全不变。
    // 2026-09-16：与本地 ComfyUI 规格对齐 —— 新增「节点开关」+ 素材输入行 + 「工作流参数」标题；
    // 被关掉的节点其参数由 rhActiveFields 过滤掉，不再渲染。
    // 2026-09-16：三个控件包进 .cfn-controls —— 与 ComfyUI 模式同构。
    // .param-row / .dynamic-params 在 rh-single-row 下 display:contents 透明化，于是
    // .cfn-controls 落在 "head params run" 那一行的 params 列（与运行键同排），
    // .cfn-details 落在新增的 "details details details" 整行 —— 参数块不再把运行键顶下去。
    // 2026-09-16 老王：与本地 ComfyUI 对齐 —— 工作流参数也收进「工作流参数」二级菜单，
    // 详情区只留素材输入行（原来参数常驻在 .rh-details 里，占掉整块宽度）。
    dynamicParams.innerHTML = `
        <div class="cfn-controls">
            ${renderUnifiedPickerControl()}
            ${renderRhNodesControl(ref)}
            ${renderRhParamsControl(fields)}
            ${renderRhResourceControl()}
        </div>
        ${renderRhDetailsHtml()}
    `;
}
/* 入口一：工作流（原「引擎下拉 RH-API·工作流」+「工作流选择器」两个同功能按钮合并）
   弹层内 = 工作流列表 + 生成引擎切换（引擎下拉已隐藏，切走其他引擎的入口在此） */
function renderRhWorkflowControl(ref) {
    return CanvasRhControls.renderRhWorkflowControl.apply(null, arguments);
}

function rhWorkflowJsonForRef(ref){
    return CanvasRhControls.rhWorkflowJsonForRef.apply(null, arguments);
}
function rhWorkflowNodeList(ref){
    return CanvasRhControls.rhWorkflowNodeList.apply(null, arguments);
}
function rhIsImageLoaderClass(cls){
    return CanvasRhControls.rhIsImageLoaderClass.apply(null, arguments);
}
function rhWorkflowImageFieldName(node){
    return CanvasRhControls.rhWorkflowImageFieldName.apply(null, arguments);
}
function rhWorkflowImageSlots(ref){
    return CanvasRhControls.rhWorkflowImageSlots.apply(null, arguments);
}
function rhImageSlotOrderMap(sourceSettings=settings){
    return CanvasRhControls.rhImageSlotOrderMap(sourceSettings);
}
function rhNodesPillText(nodes) {
    return CanvasRhControls.rhNodesPillText.apply(null, arguments);
}
function renderRhNodesControl(ref) {
    return CanvasRhControls.renderRhNodesControl.apply(null, arguments);
}

// 参数区（素材行 + 工作流参数菜单）单独成块，关节点时只局部重建这一块，保住节点弹层的展开状态。
// 2026-09-16 老王：参数已收进「工作流参数」二级菜单（见 renderRhParamsControl），这里只留素材输入行。
function renderRhDetailsHtml() {
    return CanvasRhControls.renderRhDetailsHtml.apply(null, arguments);
}
// 参与「工作流参数」菜单的字段：排除媒体（图片/视频/音频，值来自画布上游连线）与提示词（走画布顶部原生输入框）。
function rhParamFields(fields) {
    return CanvasRhControls.rhParamFields.apply(null, arguments);
}
// 工作流参数二级菜单（与本地 ComfyUI 的 comfy-params-control 同规格）：
// 弹层内还是同一套参数控件（renderRhSettingField），只是从常驻详情区收进一颗 pill。
function renderRhParamsControl(fields) {
    return CanvasRhControls.renderRhParamsControl.apply(null, arguments);
}
// 关节点后原地重建素材行 + 参数菜单（不整体重绘，保住刚打开的节点弹层）。
function syncRhDetailsAndParams(ref){
    const details = dynamicParams?.querySelector('.rh-details');
    if(details){
        const tpl = document.createElement('template');
        tpl.innerHTML = renderRhDetailsHtml().trim();
        const next = tpl.content.firstElementChild;
        if(next) details.replaceWith(next);
    }
    const controls = dynamicParams?.querySelector('.cfn-controls');
    const currentParams = dynamicParams?.querySelector('.rh-params-control');
    const tpl2 = document.createElement('template');
    tpl2.innerHTML = renderRhParamsControl(rhActiveFields()).trim();
    const nextParams = tpl2.content.firstElementChild;
    if(currentParams && nextParams) currentParams.replaceWith(nextParams);
    else if(currentParams && !nextParams) currentParams.remove();
    else if(!currentParams && nextParams && controls){
        const resource = controls.querySelector('.rh-resource-control');
        if(resource) controls.insertBefore(nextParams, resource);
        else controls.appendChild(nextParams);
    }
}
function syncRhNodesChrome(ref){
    const control = dynamicParams?.querySelector('.rh-nodes-control');
    if(!control) return;
    const nodes = rhWorkflowNodeList(ref);
    const pillText = rhNodesPillText(nodes);
    const sub = control.querySelector('.smart-pill .sub');
    if(sub) sub.textContent = pillText;
    const pill = control.querySelector('.smart-pill');
    if(pill) pill.title = pillText;
    const count = control.querySelector('.smart-popover-title .count');
    if(count) count.textContent = String(nodes.length);
}
// 关节点：只切该行外观 + 局部重建参数区，不整体重绘（整体重绘会把刚打开的弹层关掉）。
function handleRhNodeModeToggle(btn, event){
    return CanvasParamEvents.handleRhNodeModeToggle(btn, event);
}

/* 素材输入行：与本地 ComfyUI（renderComfyInputsRow）同规格 ——
   统计画布上游连进来的图片/音频/视频数量 + 是否有提示词。 */
function renderRhInputsRow(){
    const node = activeComposerNode() || selectedNode();
    const ups = upstreamNodesForKinds(node, ['input']);
    let img = 0, vid = 0, aud = 0;
    ups.forEach(up => {
        (up?.images || []).forEach(m => {
            if(!m?.url) return;
            const kind = mediaKindForItem(m);
            if(kind === 'image') img++;
            else if(kind === 'video') vid++;
            else if(kind === 'audio') aud++;
        });
    });
    const promptText = (promptInput?.innerText || '').replace(/\u00a0/g, ' ').trim();
    const upstreamPrompt = node ? inputPromptTextFor(node).trim() : '';
    const promptCount = (promptText || upstreamPrompt) ? 1 : 0;
    const cell = (label, n) => `<span class="cfn-mit ${n > 0 ? 'has' : ''}"><span class="cfn-dot"></span>${escapeHtml(label)}：<span class="cfn-mit-n">${n}</span></span>`;
    // 外层 .cfn-inputs-wrap 负责「独占整行」占位，内层 .cfn-inputs-row 收紧到内容宽度
    // 并与上方首颗按钮左缘对齐（见 smart-canvas.css 的 CFA-INPUTSROW-ALIGN-20260916）。
    return `<div class="cfn-inputs-wrap"><div class="cfn-inputs-row">
        <span class="cfn-mit-label">素材：</span>
        ${cell('接收图片', img)}<span class="cfn-sep">·</span>
        ${cell('接收音频', aud)}<span class="cfn-sep">·</span>
        ${cell('接收视频', vid)}<span class="cfn-sep">·</span>
        ${cell('接收提示词', promptCount)}
    </div></div>`;
}

/* 入口二：资源（原「RunningHub币」+「24G 显存」两个按钮合并）
   弹层内 = 付费方式 + 显存规格 */
function renderRhResourceControl() {
    return CanvasRhControls.renderRhResourceControl.apply(null, arguments);
}
function renderRhConfigControl(ref) {
    return CanvasRhControls.renderRhConfigControl.apply(null, arguments);
}
function renderRhPaymentControl() {
    return CanvasRhControls.renderRhPaymentControl.apply(null, arguments);
}
function renderRhMachineControl() {
    return CanvasRhControls.renderRhMachineControl.apply(null, arguments);
}
function renderComfyParams(){
 normalizeComfyWorkflowSelection(settings);
 if(settings.comfyWorkflow && !comfyWorkflowCache[settings.comfyWorkflow]) ensureComfyWorkflow(settings.comfyWorkflow).then(renderDynamicParams);
 const wf = comfyWorkflowCache[settings.comfyWorkflow];
 const fields = wf?.config?.fields || [];
 dynamicParams.innerHTML = `
 <div class="cfn-controls">${renderUnifiedPickerControl()}${renderComfyNodeModesControl(wf)}${renderComfyParamsControl(wf, fields)}</div>
 ${renderComfyDetailsHtml(wf, fields)}
 `;
}
function comfyFieldNodeIsOff(field, workflowName=settings.comfyWorkflow) {
    return CanvasComfyControls.comfyFieldNodeIsOff.apply(null, arguments);
}
function visibleComfyFields(fields, workflowName=settings.comfyWorkflow){
    return (fields || []).filter(field => !comfyFieldNodeIsOff(field, workflowName));
}
// 详情区（2026-09-16）：参数已收进「工作流参数」二级菜单，这里只保留素材输入行。
function renderComfyDetailsHtml(wf, fields) {
    return CanvasComfyControls.renderComfyDetailsHtml.apply(null, arguments);
}
// 工作流参数二级菜单：原来常驻在详情区的参数收进一颗 pill，弹层内还是同一套参数控件。
function renderComfyParamsControl(wf, fields) {
    return CanvasComfyControls.renderComfyParamsControl.apply(null, arguments);
}
// 关节点后原地重建详情区 + 参数弹层（不整体重绘，保住刚打开的节点弹层）。
function syncComfyDetailsAndParams(wf){
    const fields = wf?.config?.fields || [];
    const details = dynamicParams?.querySelector('.cfn-details');
    if(details){
        const tpl = document.createElement('template');
        tpl.innerHTML = renderComfyDetailsHtml(wf, fields).trim();
        const next = tpl.content.firstElementChild;
        if(next) details.replaceWith(next);
    }
    const controls = dynamicParams?.querySelector('.cfn-controls');
    const currentParams = dynamicParams?.querySelector('.comfy-params-control');
    const tpl2 = document.createElement('template');
    tpl2.innerHTML = renderComfyParamsControl(wf, fields).trim();
    const nextParams = tpl2.content.firstElementChild;
    if(currentParams && nextParams) currentParams.replaceWith(nextParams);
    else if(currentParams && !nextParams) currentParams.remove();
    else if(!currentParams && nextParams && controls) controls.appendChild(nextParams);
}
// 素材输入行：标题与计数同一行；只统计画布上游连接（图片/音频/视频 各自计数）；末尾"提示词："标记（原生 #promptInput 非空时亮）。
function renderComfyInputsRow(){
    const node = activeComposerNode() || selectedNode();
    const ups = upstreamNodesForKinds(node, ['input']);
    let img = 0, vid = 0, aud = 0;
    ups.forEach(up => {
        (up?.images || []).forEach(m => {
            if(!m?.url) return;
            const k = mediaKindForItem(m);
            if(k === 'image') img++;
            else if(k === 'video') vid++;
            else if(k === 'audio') aud++;
        });
    });
    // 无线引用（objectReferences）也计入素材行计数：按引用源节点当前的媒体归类累加
    canvasObjectReferenceImages(node).forEach(m => {
        if(!m?.url) return;
        const k = mediaKindForItem(m);
        if(k === 'image') img++;
        else if(k === 'video') vid++;
        else if(k === 'audio') aud++;
    });
    const promptText = (promptInput?.innerText || '').replace(/\u00a0/g, ' ').trim();
    const upstreamPrompt = node ? inputPromptTextFor(node).trim() : '';
    const promptField = (comfyWorkflowCache[settings.comfyWorkflow]?.config?.fields || []).find(f => comfyFieldKind(f, comfyWorkflowCache[settings.comfyWorkflow]) === 'prompt');
    const promptCount = promptField && (promptText || upstreamPrompt) ? 1 : 0;
    const cell = (label, n) => `<span class="cfn-mit ${n > 0 ? 'has' : ''}"><span class="cfn-dot"></span>${escapeHtml(label)}：<span class="cfn-mit-n">${n}</span></span>`;
    // 外层 .cfn-inputs-wrap 负责「独占整行」占位，内层 .cfn-inputs-row 收紧到内容宽度
    // 并与上方首颗按钮左缘对齐（见 smart-canvas.css 的 CFA-INPUTSROW-ALIGN-20260916）。
    return `<div class="cfn-inputs-wrap"><div class="cfn-inputs-row">
        <span class="cfn-mit-label">素材：</span>
        ${cell('接收图片', img)}<span class="cfn-sep">·</span>
        ${cell('接收音频', aud)}<span class="cfn-sep">·</span>
        ${cell('接收视频', vid)}<span class="cfn-sep">·</span>
        ${cell('接收提示词', promptCount)}
    </div></div>`;
}
function syncComfyInputsRow(){
    if(settings.engine !== 'comfy') return;
    const row = dynamicParams?.querySelector('.cfn-inputs-row');
    if(!row) return;
    const tpl = document.createElement('template');
    tpl.innerHTML = renderComfyInputsRow().trim();
    const next = tpl.content.firstElementChild;
    if(!next) return;
    // 原位替换要连外层占位壳一起换，否则会在 .cfn-inputs-wrap 里再套一层
    const host = row.parentElement?.classList?.contains('cfn-inputs-wrap') ? row.parentElement : row;
    host.replaceWith(next);
}
// 字段分组渲染：媒体字段跳过（值来自画布上游连线）；连续 number 横排一行；其余按 .pfield。
function renderComfyFields(fields) {
    return CanvasComfyControls.renderComfyFields.apply(null, arguments);
}
function renderComfyNumberCell(field) {
    return CanvasComfyControls.renderComfyNumberCell.apply(null, arguments);
}
// 可编辑参数已经统一由 renderComfyFields() 渲染；不再额外渲染节点名称网格。
function renderComfyOtherNodesGrid(){ return ''; }
function renderUpscalePill(paramKey, current) {
    return CanvasComfyControls.renderUpscalePill.apply(null, arguments);
}
function comfyModesForWorkflow(workflowName, source=settings){
    const bucket = (source?.comfyModes || {})[workflowName];
    return (bucket && typeof bucket === 'object') ? bucket : {};
}
function comfyModesSummary(bucket){
    const entries = Object.entries(bucket || {}).filter(([,mode]) => mode === 'bypass' || mode === 'mute');
    if(!entries.length) return tr('smart.comfyNodesAllOn') || '节点 · 全开';
    return `节点 · 关${entries.length}`;
}
// 自动裁剪（2026-09-16）：画布传来的媒体少于工作流槽位时，多出来的槽位对应的节点自动旁路。
// 语义等同用户手动点「关」（= 本地 ComfyUI 的 Ctrl+B），所以「传几张就是几张」，不用手动关节点。
// 只在本轮提交时生效，**不写回用户保存的 comfyModes**（避免污染用户自己的开关设置）。
function comfyAutoBypassForMissingMedia(plans){
    const out = {};
    (plans || []).forEach(plan => {
        const fields = Array.isArray(plan?.fields) ? plan.fields : [];
        const refs = Array.isArray(plan?.refs) ? plan.refs : [];
        // 传满时无需裁剪。
        // 一张都没传时**同样要裁**：空槽位会把工作流自带的无效默认值原样提交上去，
        // ComfyUI 校验会直接失败并返回 400（典型报错 "Invalid audio file: None"，
        // 因为本地工作流里 LoadAudio 的默认值就是字符串 'None'）。
        // 图片一张都没传时，调用方在更早的位置已有友好报错，走不到这里。
        if(refs.length >= fields.length) return;
        fields.slice(refs.length).forEach(field => {
            const nodeId = String(field?.node || '').trim();
            if(nodeId) out[nodeId] = 'bypass';
        });
    });
    return out;
}
// 节点开关（两态）：只列 config.fields 暴露的节点；开 = 使用，关 = 跳过（等同 ComfyUI Ctrl+B 旁路）。
function renderComfyNodeModesControl(wf) {
    return CanvasComfyControls.renderComfyNodeModesControl.apply(null, arguments);
}
// 节点开关切换后原位同步 pill 摘要 + 其它暴露节点网格（不重渲整个面板，避免 popover 被关）。
function syncComfyModesChrome(workflowName){
    const wf = comfyWorkflowCache[workflowName];
    const exposedNodes = [...new Set((wf?.config?.fields || []).map(f => String(f?.node || '')).filter(Boolean))];
    const modes = comfyModesForWorkflow(workflowName);
    const offCount = exposedNodes.filter(id => modes[id] === 'bypass' || modes[id] === 'mute').length;
    dynamicParams.querySelectorAll('.comfy-nodes-control .smart-pill .sub').forEach(sub => {
        sub.textContent = `${tr('smart.nodesPill') || '节点开关'}`;
    });
    dynamicParams.querySelectorAll('[data-cfn-node-id]').forEach(el => {
        const id = el.dataset.cfnNodeId;
        el.classList.toggle('off', modes[id] === 'bypass' || modes[id] === 'mute');
    });
}
function renderSizeControls(prefix='', includeSource=false) {
    return CanvasSpecControls.renderSizeControls.apply(null, arguments);
}
function ratioLabel(prefix='') {
    return CanvasSpecControls.ratioLabel.apply(null, arguments);
}
function gcdInt(a, b) {
    return CanvasSpecControls.gcdInt.apply(null, arguments);
}
function imageSizeForRatio(img) {
    return CanvasSpecControls.imageSizeForRatio.apply(null, arguments);
}
function sourceRatioImageForNode(node){
    const images = (node?.images || []).filter(img => img?.url && !isAudioMediaItem(img));
    if(!images.length) return null;
    if(canvasUiState.selection.image.nodeId === node?.id && canvasUiState.selection.image.index >= 0 && imagesForNode(node)[canvasUiState.selection.image.index]){
        const selected = imagesForNode(node)[canvasUiState.selection.image.index];
        if(imageSizeForRatio(selected)) return selected;
    }
    return images.find(img => imageSizeForRatio(img)) || images[0];
}
function reducedRatioForImage(img) {
    return CanvasSpecControls.reducedRatioForImage.apply(null, arguments);
}
function sourceImageRatioLabel(prefix=''){
    const node = activeComposerNode() || selectedNode();
    const ratio = reducedRatioForImage(sourceRatioImageForNode(node));
    if(!ratio) return '';
    return `${ratio.w}:${ratio.h}`;
}
function applySourceRatioToSettings(prefix=''){
    const ratioKey = prefix ? `${prefix}Ratio` : 'ratio';
    if(settings[ratioKey] !== 'source') return;
    const ratio = reducedRatioForImage(sourceRatioImageForNode(activeComposerNode() || selectedNode()));
    if(!ratio) return;
    const customKey = prefix ? `${prefix}CustomRatio` : 'customRatio';
    const wKey = prefix ? `${prefix}CustomRatioWidth` : 'customRatioWidth';
    const hKey = prefix ? `${prefix}CustomRatioHeight` : 'customRatioHeight';
    settings[wKey] = ratio.w;
    settings[hKey] = ratio.h;
    settings[customKey] = `${ratio.w}:${ratio.h}`;
}
function resolutionLabel(prefix='') {
    return CanvasSpecControls.resolutionLabel.apply(null, arguments);
}
function ratioIconClass(value) {
    return CanvasSpecControls.ratioIconClass.apply(null, arguments);
}
function videoAspectIconClass(value) {
    return CanvasSpecControls.videoAspectIconClass.apply(null, arguments);
}
function renderProviderControl(providers) {
    return CanvasParamControls.renderProviderControl.apply(null, arguments);
}
function renderModelControl(models) {
    return CanvasParamControls.renderModelControl.apply(null, arguments);
}
// API 单排 v2：引擎+模型合并下拉（无边框 pill）
function renderEngineModelCombo(models) {
    return CanvasParamControls.renderEngineModelCombo.apply(null, arguments);
}
// ===== 统一「平台·工作流/模型」面板（canvas-unified-picker.js）宿主接线 =====
function renderUnifiedPickerControl() {
    return CanvasUnifiedPicker.renderPill();
}
function unifiedPersist(){
    persistActiveSmartSettings();
    rememberRecentSmartSettings(settings, activeSettingsSubject());
}
CanvasUnifiedPicker.configure({
    getSettings: () => settings,
    comfyWorkflows: () => comfyWorkflows,
    runningHubEntries: (kind) => runningHubEntries(kind),
    runningHubEntryId: (e, k) => runningHubEntryId(e, k),
    workflowOutputKindForComfy: (n) => workflowOutputKindForComfy(n),
    workflowOutputKindForRhEntry: (e) => workflowOutputKindForRhEntry(e),
    imageProviders: () => imageProviders(),
    videoApiProviders: () => videoApiProviders(),
    volcengineProvider: () => volcengineProvider(),
    providerImageModels: (id) => providerImageModels(id),
    providerVideoModels: (id) => providerVideoModels(id),
    providerModelDisplayName: (id, m) => providerModelDisplayName(id, m),
    filterJimengImageModels: (m) => filterJimengImageModels(m),
    filterJimengVideoModels: (m) => filterJimengVideoModels(m),
    setDynamicProperty: (k, v) => setDynamicSetting(k, v, { keepLayout: true }),
    applyToSubject: (patch) => {
        const subject = activeComposerNode();
        Object.entries(patch).forEach(([k, v]) => {
            settings[k] = v;
            if(subject?.runSettings) subject.runSettings[k] = v;
        });
        if(subject){
            subject.promptDraftHtml = promptInput?.innerHTML || subject.promptDraftHtml || '';
            subject.promptDraftText = promptPlainText();
        }
    },
    tr: (k) => tr(k),
    escapeHtml: (s) => escapeHtml(s),
    escapeAttr: (s) => escapeAttr(s),
    refreshIcons: () => refreshIcons(),
    toast: (m) => toast(m),
    renderDynamicParams: () => renderDynamicParams(),
    persist: () => unifiedPersist(),
    scheduleSave: () => scheduleSave()
});
CanvasUnifiedPicker.bindEvents();
// 类别切换（图片/视频）后当前项失配 → 自动跳该类别最近用过的
function applyKindAutoPick() {
    const pick = CanvasUnifiedPicker.autoPickForKind(settings.apiKind === 'video' ? 'video' : 'image');
    if (pick) CanvasUnifiedPicker.select(pick);
}
// API 单排 v2：规格+数量合并 pill（无边框）
function renderComboSpecCount() {
    return CanvasSpecControls.renderComboSpecCount.apply(null, arguments);
}
// 抽取规格弹层（供合并 pill 复用）
function renderImageSpecPopover() {
    return CanvasSpecControls.renderImageSpecPopover.apply(null, arguments);
}
function renderRatioControl(prefix='', includeSource=false) {
    return CanvasSpecControls.renderRatioControl.apply(null, arguments);
}
function renderResolutionControl(prefix='') {
    return CanvasSpecControls.renderResolutionControl.apply(null, arguments);
}
function renderInlineCustomRatioFields(prefix='', extraClass='') {
    return CanvasSpecControls.renderInlineCustomRatioFields.apply(null, arguments);
}
function renderInlineCustomSizeFields(prefix='', extraClass='') {
    return CanvasSpecControls.renderInlineCustomSizeFields.apply(null, arguments);
}
function renderQualityControl() {
    return CanvasSpecControls.renderQualityControl.apply(null, arguments);
}
function renderCountVisualControl() {
    return CanvasSpecControls.renderCountVisualControl.apply(null, arguments);
}
function renderCountControl() {
    return CanvasSpecControls.renderCountControl.apply(null, arguments);
}
function renderCustomRatioControls(prefix='') {
    return CanvasSpecControls.renderCustomRatioControls.apply(null, arguments);
}
function renderCustomSizeControls(prefix='') {
    return CanvasSpecControls.renderCustomSizeControls.apply(null, arguments);
}
// 完全照搬 comfyui-settings.js renderPreviewField —— 把 config.json 里 user
// 手工配的"暴露字段"按 type 渲染成完整面板（textarea/number/slider/dropdown/boolean）。
// 字段顺序即 user 配置顺序；值绑 settings.comfyParams[field.id]；事件由 bindDynamicParams
// 通过 data-comfy-param / data-comfy-bool / data-comfy-pick / data-comfy-random 委托。
// 媒体字段（image/video/audio）不在此渲染 —— 值来自画布上游连线（素材输入行只读计数）。
// Comfy/RH 动态参数域外移 canvas-dynamic-param-engine.js（第五刀）。transientSmartCloudLinks 写入走 setter，读走 getter。
if(globalThis.CanvasDynamicParamEngine){CanvasDynamicParamEngine.configure({
        activeSettingsSubject: (...a) => activeSettingsSubject(...a),
        audioRefsOnly: (...a) => audioRefsOnly(...a),
        buildPromptRequest: (...a) => buildPromptRequest(...a),
        collectMentionedImagesFromPrompt: (...a) => collectMentionedImagesFromPrompt(...a),
        comfyParamValue: (...a) => comfyParamValue(...a),
        escapeHtml: (...a) => escapeHtml(...a),
        formatComfySliderValue: (...a) => formatComfySliderValue(...a),
        imageRefsOnly: (...a) => imageRefsOnly(...a),
        isRemoteVideoReferenceUrl: (...a) => isRemoteVideoReferenceUrl(...a),
        localDisplayUrlForMediaItem: (...a) => localDisplayUrlForMediaItem(...a),
        mediaKindForItem: (...a) => mediaKindForItem(...a),
        openAssetNameDialog: (...a) => openAssetNameDialog(...a),
        persistActiveSmartSettings: (...a) => persistActiveSmartSettings(...a),
        render: (...a) => render(...a),
        renderDynamicParams: (...a) => renderDynamicParams(...a),
        rhActiveFields: (...a) => rhActiveFields(...a),
        rhCurrentKind: (...a) => rhCurrentKind(...a),
        rhEntryFields: (...a) => rhEntryFields(...a),
        rhImageSlotOrderMap: (...a) => rhImageSlotOrderMap(...a),
        rhNodeIsOff: (...a) => rhNodeIsOff(...a),
        rhNodeOffIds: (...a) => rhNodeOffIds(...a),
        rhWorkflowImageSlots: (...a) => rhWorkflowImageSlots(...a),
        rhWorkflowJsonFromSources: (...a) => rhWorkflowJsonFromSources(...a),
        savePromptDraftForCurrent: (...a) => savePromptDraftForCurrent(...a),
        scheduleSave: (...a) => scheduleSave(...a),
        selectedNode: (...a) => selectedNode(...a),
        selectedRunningHubRef: (...a) => selectedRunningHubRef(...a),
        smartComfyRandomActive: (...a) => smartComfyRandomActive(...a),
        smartComfyRandomValue: (...a) => smartComfyRandomValue(...a),
        smartResponseErrorMessage: (...a) => smartResponseErrorMessage(...a),
        sortRunningHubFields: (...a) => sortRunningHubFields(...a),
        toast: (...a) => toast(...a),
        uniqueReferenceImages: (...a) => uniqueReferenceImages(...a),
        videoProviderPlatform: (...a) => videoProviderPlatform(...a),
        videoRefsOnly: (...a) => videoRefsOnly(...a),
        RH_OFFICIAL_PROXY_BASE: () => RH_OFFICIAL_PROXY_BASE,
        dynamicParams: () => dynamicParams,
        inputThumbsRow: () => inputThumbsRow,
        promptInput: () => promptInput,
        runningHubWorkflowCache: () => runningHubWorkflowCache,
        settings: () => settings,
        smartLoopContext: () => smartLoopContext,
        smartRhRandomValues: () => smartRhRandomValues,
        transientSmartCloudLinks: () => transientSmartCloudLinks,
        setTransientSmartCloudLinks: v => { transientSmartCloudLinks = v; }
});}
function renderComfySettingField(){return CanvasDynamicParamEngine.renderComfySettingField.apply(null, arguments);}
function rhParamKey(){return CanvasDynamicParamEngine.rhParamKey.apply(null, arguments);}
function rhFieldKind(){return CanvasDynamicParamEngine.rhFieldKind.apply(null, arguments);}
function rhFieldRole(){return CanvasDynamicParamEngine.rhFieldRole.apply(null, arguments);}
function rhExtractFieldOptions(){return CanvasDynamicParamEngine.rhExtractFieldOptions.apply(null, arguments);}
function rhDefaultValue(){return CanvasDynamicParamEngine.rhDefaultValue.apply(null, arguments);}
function rhIsWorkflowLinkValue(){return CanvasDynamicParamEngine.rhIsWorkflowLinkValue.apply(null, arguments);}
function rhRandomEnabled(){return CanvasDynamicParamEngine.rhRandomEnabled.apply(null, arguments);}
function smartRhRandomActive(){return CanvasDynamicParamEngine.smartRhRandomActive.apply(null, arguments);}
function toggleSmartRhRandom(){return CanvasDynamicParamEngine.toggleSmartRhRandom.apply(null, arguments);}
function rhParamValue(){return CanvasDynamicParamEngine.rhParamValue.apply(null, arguments);}
function rhDefaultPromptSuggestion(){return CanvasDynamicParamEngine.rhDefaultPromptSuggestion.apply(null, arguments);}
function refreshPromptPlaceholderVisible(){return CanvasDynamicParamEngine.refreshPromptPlaceholderVisible.apply(null, arguments);}
function updatePromptPlaceholder(){return CanvasDynamicParamEngine.updatePromptPlaceholder.apply(null, arguments);}
function rhFieldIndexes(){return CanvasDynamicParamEngine.rhFieldIndexes.apply(null, arguments);}
function ensureRunningHubWorkflow(){return CanvasDynamicParamEngine.ensureRunningHubWorkflow.apply(null, arguments);}
function currentRunningHubWorkflowConfig(){return CanvasDynamicParamEngine.currentRunningHubWorkflowConfig.apply(null, arguments);}
function rhMediaForRun(){return CanvasDynamicParamEngine.rhMediaForRun.apply(null, arguments);}
function applyUploadedUrlsToSmartRefs(){return CanvasDynamicParamEngine.applyUploadedUrlsToSmartRefs.apply(null, arguments);}
function manualSmartVideoLink(){return CanvasDynamicParamEngine.manualSmartVideoLink.apply(null, arguments);}
function manualSmartMediaLinks(){return CanvasDynamicParamEngine.manualSmartMediaLinks.apply(null, arguments);}
function renderedInputMediaRefs(){return CanvasDynamicParamEngine.renderedInputMediaRefs.apply(null, arguments);}
function comfyWorkflowImageRefsForNode(){return CanvasDynamicParamEngine.comfyWorkflowImageRefsForNode.apply(null, arguments);}
function setCurrentSmartManualVideoUrl(){return CanvasDynamicParamEngine.setCurrentSmartManualVideoUrl.apply(null, arguments);}
function uploadCurrentSmartVideosToCloud(){return CanvasDynamicParamEngine.uploadCurrentSmartVideosToCloud.apply(null, arguments);}

// Rh 工作流构建域外移 canvas-rh-workflow-builder.js（第一刀），此处留注入与薄代理。
if(globalThis.CanvasRhWorkflowBuilder){CanvasRhWorkflowBuilder.configure({
        currentRunningHubWorkflowConfig: (...a) => currentRunningHubWorkflowConfig(...a),
        escapeHtml: (...a) => escapeHtml(...a),
        rhActiveFields: (...a) => rhActiveFields(...a),
        rhCurrentKind: (...a) => rhCurrentKind(...a),
        rhDefaultValue: (...a) => rhDefaultValue(...a),
        rhExtractFieldOptions: (...a) => rhExtractFieldOptions(...a),
        rhFieldIndexes: (...a) => rhFieldIndexes(...a),
        rhFieldKind: (...a) => rhFieldKind(...a),
        rhFieldRole: (...a) => rhFieldRole(...a),
        rhIsWorkflowLinkValue: (...a) => rhIsWorkflowLinkValue(...a),
        rhNodeIsOff: (...a) => rhNodeIsOff(...a),
        rhNodeOffIds: (...a) => rhNodeOffIds(...a),
        rhParamKey: (...a) => rhParamKey(...a),
        rhParamValue: (...a) => rhParamValue(...a),
        rhRandomEnabled: (...a) => rhRandomEnabled(...a),
        rhWorkflowImageSlots: (...a) => rhWorkflowImageSlots(...a),
        selectedRunningHubRef: (...a) => selectedRunningHubRef(...a),
        settings: () => settings,
        smartRhRandomActive: (...a) => smartRhRandomActive(...a),
        smartRhRandomValues: () => smartRhRandomValues
});}
function rhBuildWorkflowRequestExtras(){return CanvasRhWorkflowBuilder.rhBuildWorkflowRequestExtras.apply(null, arguments);}
function rhBuildNodeInfoList(){return CanvasRhWorkflowBuilder.rhBuildNodeInfoList.apply(null, arguments);}
function renderRhSettingField(){return CanvasRhWorkflowBuilder.renderRhSettingField.apply(null, arguments);}
function comfyRandomEnabledField(field){ return field?.type === 'number' && field.random_enabled === true; }
function smartComfyRandomActive(fieldId){
    return smartComfyRandomActiveFor(settings, fieldId);
}
function smartComfyRandomActiveFor(source, fieldId){
    const active = source?.comfyRandomActive || {};
    return active[fieldId] !== false;
}
function toggleSmartComfyRandom(fieldId){
    settings.comfyRandomActive = settings.comfyRandomActive || {};
    settings.comfyRandomActive[fieldId] = !smartComfyRandomActive(fieldId);
    persistActiveSmartSettings();
    renderDynamicParams();
    scheduleSave();
}
function smartComfyRandomValue(field){
    const isFloat = Number(field.step) > 0 && Number(field.step) < 1;
    let min = Number.isFinite(Number(field.min)) ? Number(field.min) : null;
    let max = Number.isFinite(Number(field.max)) ? Number(field.max) : null;
    const name = `${field.input || ''} ${field.name || ''}`.toLowerCase();
    const looksSeed = name.includes('seed') || name.includes('noise') || name.includes('随机') || name.includes('噪');
    if(min === null) min = looksSeed ? 1 : 0;
    if(max === null || max <= min) max = looksSeed ? 1000000000000000 : 999999;
    const value = min + Math.random() * (max - min);
    if(isFloat){
        const precision = Math.min(8, Math.max(1, String(field.step).split('.')[1]?.length || 2));
        return Number(value.toFixed(precision));
    }
    return Math.floor(value);
}
function setDynamicSetting(key, value, opts={}){
    const numericKeys = new Set(['count','width','height','videoDuration','enhanceStrength','enhanceUpscaleRes','editUpscaleRes','customRatioWidth','customRatioHeight','customWidth','customHeight']);
    const layoutKeys = new Set(['provider_id','model','resolution','ratio','videoProvider','videoModel','videoAspect','videoResolution','videoReferenceMode','videoExtendMode','comfyMode','comfyWorkflow','quality','count','enhanceUpscaleRes','editUpscaleRes','rhConfigKey','rhPayment','rhInstanceType']);
    settings[key] = numericKeys.has(key) && value !== '' ? Number(value) : value;
    if(key === 'provider_id') settings.model = '';
    if(key === 'videoProvider') settings.videoModel = '';
    if(key === 'videoReferenceMode') {
        settings.videoUseFrameRoles = videoReferenceModeValue(settings) === 'first_last';
        if(settings.videoUseFrameRoles) settings.videoMultimodal = false;
    }
    if(key === 'videoExtendMode') settings.videoExtendMode = ['before','after'].includes(value) ? value : 'after';
    if(key === 'videoMultimodal' && settings.videoMultimodal) settings.videoUseFrameRoles = false;
    if(key === 'videoUseFrameRoles' && settings.videoUseFrameRoles) settings.videoMultimodal = false;
    if(key === 'comfyMode') applyRecentSmartSettingsForCurrentMode();
    if(key === 'resolution'){
        if(settings.resolution === 'custom') settings.ratio = '';
        else if(!settings.ratio) settings.ratio = 'square';
    }
    if(key === 'ratio') applySourceRatioToSettings('');
    if(key === 'customRatioWidth' || key === 'customRatioHeight') settings.customRatio = settings.customRatioWidth && settings.customRatioHeight ? `${settings.customRatioWidth}:${settings.customRatioHeight}` : '';
    if(key === 'customWidth' || key === 'customHeight') settings.customSize = settings.customWidth && settings.customHeight ? `${settings.customWidth}x${settings.customHeight}` : '';
    const sizeKeys = new Set(['resolution','ratio','customRatio','customRatioWidth','customRatioHeight','customWidth','customHeight','customSize']);
    const unlockOutpaintSize = settings.outpaintResolutionLocked && sizeKeys.has(key);
    if(unlockOutpaintSize){
        delete settings.outpaintResolutionLocked;
        const subject = activeSettingsSubject();
        if(subject) delete subject.outpaintSize;
    }
    if(key === 'comfyWorkflow') {
        settings.comfyWorkflow = resolveComfyWorkflowName(settings.comfyWorkflow);
        settings.comfyParams = {};
        applyWorkflowOutputKind();
        ensureComfyWorkflow(settings.comfyWorkflow).then(() => { applyWorkflowOutputKind(); renderDynamicParams(); });
    }
    if(key === 'rhConfigKey'){
        settings.rhParams = {};
        settings.rhRandomActive = {};
        applyWorkflowOutputKind();
    }
    persistActiveSmartSettings();
    rememberRecentSmartSettings(settings, activeSettingsSubject());
    if(layoutKeys.has(key) && !opts.keepLayout) renderDynamicParams();
    scheduleSave();
}
function setVideoSpecSetting(key, value){
    if(key === 'videoDuration') {
        settings.videoDuration = Math.max(1, Math.min(60, Number(value) || 5));
    } else if(key === 'videoAspect') {
        settings.videoAspect = value || '16:9';
    } else if(key === 'videoResolution') {
        settings.videoResolution = value || '';
    } else if(key === 'videoGenerateAudio') {
        settings.videoGenerateAudio = !settings.videoGenerateAudio;
    } else {
        return;
    }
    persistActiveSmartSettings();
    rememberRecentSmartSettings(settings, activeSettingsSubject());
    syncVideoSpecControl();
    scheduleSave();
}
function syncVideoSpecControl(){
    const control = dynamicParams?.querySelector('.video-spec-control');
    if(!control) return;
    const aspect = settings.videoAspect || '16:9';
    const resolution = settings.videoResolution || '';
    const duration = videoDurationValue(settings);
    const pillText = control.querySelector('.smart-pill span');
    if(pillText) pillText.textContent = `${videoAspectLabel(settings)} · ${videoResolutionLabel(settings)} · ${duration}s`;
    control.querySelectorAll('[data-smart-param="videoAspect"]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.smartValue === aspect);
    });
    control.querySelectorAll('[data-smart-param="videoResolution"]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.smartValue === resolution);
    });
    control.querySelectorAll('[data-smart-param="videoDuration"]').forEach(btn => {
        btn.classList.toggle('active', Number(btn.dataset.smartValue) === duration);
    });
    control.querySelectorAll('[data-param="videoDuration"]').forEach(input => {
        if(document.activeElement !== input) input.value = duration;
    });
    control.querySelectorAll('[data-toggle-param="videoGenerateAudio"]').forEach(btn => {
        btn.classList.toggle('active', !!settings.videoGenerateAudio);
    });
}
function closeAllSmartPopovers(){
    document.querySelectorAll('.smart-control.pinned').forEach(c => {
        CanvasParamEvents.setPopoverOpen(c, false);
    });
    document.querySelectorAll('.loop-number-control.pinned').forEach(c => c.classList.remove('pinned'));
}
function bindComposerReferenceModeControl(){
    if(!composerReferenceModeSlot) return;
    composerReferenceModeSlot.querySelectorAll('.smart-control > .smart-pill').forEach(pill => {
        CanvasParamEvents.bindPopoverTrigger(pill);
    });
    composerReferenceModeSlot.querySelectorAll('[data-smart-param]').forEach(btn => {
        btn.onclick = event => {
            event.preventDefault();
            event.stopPropagation();
            setDynamicSetting(btn.dataset.smartParam, btn.dataset.smartValue);
        };
    });
}
function handleComfyNodeModeToggle(btn, event){
    return CanvasParamEvents.handleComfyNodeModeToggle(btn, event);
}
function bindDynamicParams(){
    return CanvasParamEvents.bindDynamicParams();
}
function smartNoCacheUrl(url){
    const value = String(url || '');
    if(!value) return value;
    try {
        const parsed = new URL(value, window.location.origin);
        if(parsed.pathname.startsWith('/api/')){
            parsed.searchParams.set('_smart_ts', `${Date.now()}-${Math.random().toString(36).slice(2)}`);
        }
        if(parsed.origin === window.location.origin) return `${parsed.pathname}${parsed.search}${parsed.hash}`;
        return parsed.toString();
    } catch(_) {
        return value;
    }
}
async function fetchSmartLocalJson(url, options={}, timeout=3500){
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
        const headers = {'Accept':'application/json', ...(options.headers || {})};
        const res = await fetch(smartNoCacheUrl(url), {...options, headers, cache:'no-store', signal:controller.signal});
        if(!res.ok) throw new Error('local-api-unavailable');
        return await res.json();
    } finally {
        clearTimeout(timer);
    }
}
async function loadConfig(){
    await loadAppRuntimeConfig();
    try {
        const cfg = await fetchSmartLocalJson('/api/config');
        let nextProviders = Array.isArray(cfg.api_providers) ? cfg.api_providers : [];
        try {
            const providerPayload = await fetchSmartLocalJson('/api/providers');
            if(Array.isArray(providerPayload.providers)) nextProviders = providerPayload.providers;
        } catch(_) {}
        apiProviders = nextProviders;
        comfyInstanceCount = Math.max(1, (Array.isArray(cfg.comfy_instances) ? cfg.comfy_instances : []).filter(Boolean).length || 1);
        // 提供商配置已就绪即先渲染参数面板，避免等工作流/RunningHub 预取完成后参数才「突然刷新出来」。
        sanitizeSmartApiSelection(settings);
        updateProviderModels();
        try {
            const wf = await fetchSmartLocalJson('/api/workflows');
            comfyWorkflows = replaceKnownComfyWorkflows(Array.isArray(wf.workflows) ? wf.workflows : []);
        } catch(_) {
            comfyWorkflows = await filterAccessibleComfyWorkflows(mergeKnownComfyWorkflows(loadLocalComfyWorkflowRegistry()));
            saveLocalComfyWorkflowRegistry(comfyWorkflows);
        }
        // 统一面板按产出类型分组依赖工作流 JSON 扫节点——后台预热缓存，到手增量重绘
        Promise.all((comfyWorkflows || []).map(w => ensureComfyWorkflow(w.name).catch(() => null)))
            .then(() => { if(typeof renderDynamicParams === 'function') renderDynamicParams(); });
        runningHubWorkflowCache = {};
        lastConfigRefreshAt = Date.now();
        sanitizeSmartApiSelection(settings);
        updateProviderModels();
    } catch(e) {
        toast(tr('smart.toastApiSettingsFail'));
    }
}
async function refreshSmartConfigFromSettings(){
    await loadConfig();
    renderDynamicParams();
    const node = selectedNode();
    if(node?.type === 'smart-prompt') {
        // applySettingsToNode 已在历史重构中遗失，直接调用会抛 ReferenceError 并中断后续 render
        if(typeof applySettingsToNode === 'function') applySettingsToNode(node);
        render();
    }
}
function loadPromptPresets(){
    return CanvasPromptTemplateModel.loadPresets();
}
function savePromptPresets(){
    return CanvasPromptTemplateModel.savePresets();
}
function defaultPromptTemplateGroups(){
    return CanvasPromptTemplateModel.defaultGroups();
}
function loadPromptTemplateGroups(){
    return CanvasPromptTemplateModel.loadGroups();
}
function savePromptTemplateGroups(){
    return CanvasPromptTemplateModel.saveGroups();
}
function loadPromptTemplateOverrides(){
    return CanvasPromptTemplateModel.loadOverrides();
}
function savePromptTemplateOverrides(){
    return CanvasPromptTemplateModel.saveOverrides();
}
async function loadPromptTemplates(){
    try {
        const result = await CanvasPromptTemplateRepository.loadLibraries();
        promptLibraries = result.libraries;
        builtinPromptTemplates = result.builtinPromptTemplates;
        if(!promptLibraries.some(lib => lib.id === activePromptLibraryId)) activePromptLibraryId = promptLibraries[0]?.id || 'system';
        renderPromptLibrarySelect();
    } catch(e) {
        builtinPromptTemplates = [];
        promptLibraries = [];
    }
}
function activePromptLibrary(){
    return CanvasPromptTemplateModel.activeLibrary();
}
function renderPromptLibrarySelect(){
    if(!promptTemplateLibrarySelect) return;
    promptTemplateLibrarySelect.innerHTML = promptLibraries.map(lib => `<option value="${escapeAttr(lib.id)}" ${lib.id === activePromptLibraryId ? 'selected' : ''}>${escapeHtml(lib.name || '提示词库')}</option>`).join('');
}
function promptTemplateItems(){
    return CanvasPromptTemplateModel.items();
}
function promptTemplateText(template, mode='positive'){
    return CanvasPromptTemplateModel.text(template, mode);
}
function promptTemplateName(template){
    return CanvasPromptTemplateModel.name(template);
}
function promptTemplateScene(template){
    return CanvasPromptTemplateModel.scene(template);
}
function promptTemplateSearchText(template){
    return CanvasPromptTemplateModel.searchText(template);
}
function activePromptTemplateGroups(){
    return CanvasPromptTemplateModel.activeGroups();
}
function promptTemplateCategoryLabel(category){
    return CanvasPromptTemplateModel.categoryLabel(category);
}
function promptTemplateSelectedItem(){
    return CanvasPromptTemplateModel.selectedItem();
}
function currentPromptPreset(id){
    return CanvasPromptTemplateModel.currentPreset(id);
}
function defaultPromptPresetName(text){
    return CanvasPromptTemplateModel.defaultPresetName(text);
}
function promptPresetPanelNode(){
    return CanvasPromptPresetPanel.panelNode();
}
function setPromptPresetStatus(text='', tone=''){
    return CanvasPromptPresetPanel.setStatus(text, tone);
}
function resetPromptPresetDeleteState(){
    return CanvasPromptPresetPanel.resetDeleteState();
}
function createPromptPresetFromNode(node, {openPanel=true, openTemplatePanel=false}={}){
    const text = String(node?.text || '').trim();
    if(!text){ toast(tr('smart.promptPresetEmpty')); return null; }
    const preset = {id:uid('preset'), name:defaultPromptPresetName(text), text, createdAt:Date.now(), updatedAt:Date.now()};
    CanvasPromptTemplateModel.addPreset(preset);
    if(node) node.promptPresetId = preset.id;
    render();
    scheduleSave();
    if(openPanel) openPromptPresetPanel(node?.id || '', preset.id, {status:tr('smart.promptPresetSavedNew'), tone:'ok'});
    if(openTemplatePanel) {
        promptTemplateCategory = 'mine';
        promptTemplateSelectedId = `mine:${preset.id}`;
        promptTemplateEditing = true;
        openPromptTemplatePanel(node?.id || '', promptTemplateSelectedId);
    }
    return preset;
}
function createPromptPresetFromComposer(){
    const text = promptPlainText();
    if(!text){ toast(tr('smart.promptPresetEmpty')); return null; }
    const preset = {id:uid('preset'), name:defaultPromptPresetName(text), text, category:'mine', createdAt:Date.now(), updatedAt:Date.now()};
    CanvasPromptTemplateModel.addPreset(preset);
    savePromptDraftForCurrent();
    scheduleSave();
    return preset;
}
function savePromptNodeAsPreset(node){
    createPromptPresetFromNode(node);
}
function renderPromptPresetPanel(selectedId='', message=''){
    return CanvasPromptPresetPanel.renderPanel(selectedId, message);
}
function openPromptPresetPanel(nodeId='', presetId='', options={}){
    return CanvasPromptPresetPanel.openPanel(nodeId, presetId, options);
}
function closePromptPresetPanel(){
    return CanvasPromptPresetPanel.closePanel();
}
function promptTemplateScrollSnapshot(){
    return CanvasPromptTemplateView.scrollSnapshot();
}
function restorePromptTemplateScroll(snapshot){
    return CanvasPromptTemplateView.restoreScroll(snapshot);
}
function renderPromptTemplatePanel(options={}){
    return CanvasPromptTemplateView.render(options);
}
function activePromptTemplateNodeId(){
    return CanvasPromptTemplateController.activeNodeId();
}
function syncComposerTemplateButton(){
    return CanvasPromptTemplateController.syncComposerButton();
}
function positionPromptTemplateNearAnchor(anchor){
    return CanvasPromptTemplateController.positionNearAnchor(anchor);
}
function openPromptTemplatePanel(nodeId='', templateId='', options={}){
    undockPromptTemplatePanel(); // 若停靠在资产库面板，先移回原位再按原逻辑开浮层
    return CanvasPromptTemplateController.openPanel(nodeId, templateId, options);
}
function closePromptTemplatePanel(){
    return CanvasPromptTemplateController.closePanel();
}
function applyPromptTemplateToNode(mode='positive'){
    return CanvasPromptTemplateController.applyTemplate(mode);
}
async function saveCurrentPromptAsTemplate(){
    const library = activePromptLibrary();
    if(library.id === 'system' || library.readonly){ toast('请选择可编辑的提示词库'); return; }
    const text = promptTemplatePanel?.dataset.target === 'composer'
        ? promptPlainText()
        : String(nodes.find(n => n.id === promptTemplatePanel?.dataset.nodeId)?.text || '').trim();
    if(!text){ toast(tr('smart.promptPresetEmpty')); return; }
    try {
        const data = await CanvasPromptTemplateRepository.createItem({library_id:library.id, name:defaultPromptPresetName(text), category:promptTemplateCategory === 'all' ? 'mine' : promptTemplateCategory, positive:text, scene:'我的提示词预设'});
        promptLibraries = data.library?.libraries || promptLibraries;
        activePromptLibraryId = library.id;
        promptTemplateCategory = data.item?.category || 'mine';
        promptTemplateSelectedId = data.item?.id || '';
        promptTemplateEditing = true;
        renderPromptTemplatePanel({preserveScroll:false});
    } catch(err) {
        toast(err.message || '保存失败');
    }
}
async function createBlankPromptTemplate(){
    const library = activePromptLibrary();
    if(library.id === 'system' || library.readonly){ toast('请选择可编辑的提示词库'); return; }
    const category = promptTemplateCategory && promptTemplateCategory !== 'all' ? promptTemplateCategory : 'mine';
    try {
        const data = await CanvasPromptTemplateRepository.createItem({library_id:library.id, name:tr('smart.tplNewTemplateName'), category, positive:'新提示词', scene:'我的提示词预设'});
        promptLibraries = data.library?.libraries || promptLibraries;
        activePromptLibraryId = library.id;
        promptTemplateCategory = category;
        promptTemplateSelectedId = data.item?.id || '';
        promptTemplateEditing = true;
        renderPromptTemplatePanel({preserveScroll:false});
    } catch(err) {
        toast(err.message || '创建失败');
    }
}
async function savePromptTemplateEdit(){
    const item = promptTemplateSelectedItem();
    if(!item) return;
    const name = promptTemplatePanel.querySelector('[data-template-edit-name]')?.value?.trim() || '';
    const text = promptTemplatePanel.querySelector('[data-template-edit-text]')?.value?.trim() || '';
    const category = promptTemplatePanel.querySelector('[data-template-edit-category]')?.value || 'mine';
    if(!name || !text){ toast(tr('smart.tplRequired')); return; }
    if(item.remote){
        try {
            const data = await CanvasPromptTemplateRepository.updateItem(item.id,{library_id:item.libraryId || activePromptLibrary().id, name, category, positive:text, scene:item.scene || '', negative:item.negative || ''});
            promptLibraries = data.library?.libraries || promptLibraries;
            promptTemplateSelectedId = data.item?.id || item.id;
        } catch(err) {
            toast(err.message || '保存失败');
            return;
        }
    } else if(item.builtin){
        promptTemplateOverrides.editedBuiltins = promptTemplateOverrides.editedBuiltins || {};
        promptTemplateOverrides.editedBuiltins[item.id] = {
            ...(promptTemplateOverrides.editedBuiltins[item.id] || {}),
            name,
            positive:text,
            category
        };
        savePromptTemplateOverrides();
    } else {
        const preset = currentPromptPreset(item.sourceId);
        if(!preset) return;
        CanvasPromptTemplateModel.updatePreset(preset.id,{name,text,category,updatedAt:Date.now()});
        nodes.forEach(node => { if(node.promptPresetId === preset.id) node.text = text; });
    }
    promptTemplateEditing = false;
    renderPromptTemplatePanel();
    render();
    scheduleSave();
}
async function deletePromptTemplate(){
    const item = promptTemplateSelectedItem();
    if(!item) return;
    if(item.remote){
        try {
            const data = await CanvasPromptTemplateRepository.deleteItem(item.id);
            promptLibraries = data.library?.libraries || promptLibraries;
        } catch(err) {
            toast(err.message || '删除失败');
            return;
        }
    } else if(item.builtin){
        promptTemplateOverrides.hiddenBuiltinIds = [...new Set([...(promptTemplateOverrides.hiddenBuiltinIds || []), item.id])];
        savePromptTemplateOverrides();
    } else {
        CanvasPromptTemplateModel.removePreset(item.sourceId);
        nodes.forEach(node => { if(node.promptPresetId === item.sourceId) node.promptPresetId = ''; });
    }
    promptTemplateSelectedId = '';
    promptTemplateEditing = false;
    renderPromptTemplatePanel({preserveScroll:false});
    render();
    scheduleSave();
}
async function createPromptTemplateGroup(){
    const name = window.prompt(tr('smart.tplNewGroupPrompt'), tr('smart.tplNewGroupDefault'));
    if(!String(name || '').trim()) return;
    const lib = activePromptLibrary();
    if(lib && lib.id !== 'system'){
        try {
            const data = await CanvasPromptTemplateRepository.createCategory({name:String(name).trim().slice(0, 24), library_id:lib.id});
            promptLibraries = data.library?.libraries || promptLibraries;
            promptTemplateCategory = data.category?.id || promptTemplateCategory;
            renderPromptTemplatePanel({preserveScroll:false});
        } catch(err){ if(typeof setStatus === 'function') setStatus(err.message || '新增分组失败'); }
        return;
    }
    const group = {id:uid('tpl_group'), name:String(name).trim().slice(0, 24)};
    promptTemplateGroups.push(group);
    savePromptTemplateGroups();
    promptTemplateCategory = group.id;
    renderPromptTemplatePanel({preserveScroll:false});
}
async function renamePromptTemplateGroup(groupId){
    const lib = activePromptLibrary();
    const group = activePromptTemplateGroups().find(g => g.id === groupId);
    if(!group) return;
    const name = window.prompt(tr('smart.tplGroupNamePrompt'), group.name || '');
    if(!String(name || '').trim()) return;
    if(lib && lib.id !== 'system'){
        try {
            const data = await CanvasPromptTemplateRepository.updateCategory(groupId,{name:String(name).trim().slice(0, 24), library_id:lib.id});
            promptLibraries = data.library?.libraries || promptLibraries;
            renderPromptTemplatePanel();
        } catch(err){ if(typeof setStatus === 'function') setStatus(err.message || '重命名失败'); }
        return;
    }
    const cleanName = String(name).trim().slice(0, 24);
    let storedGroup = promptTemplateGroups.find(item => item.id === groupId);
    if(!storedGroup){
        storedGroup = {id:groupId, name:cleanName};
        promptTemplateGroups.push(storedGroup);
    }
    storedGroup.name = cleanName;
    if(defaultPromptTemplateGroups().some(item => item.id === groupId)) storedGroup.customized = true;
    savePromptTemplateGroups();
    renderPromptTemplatePanel();
}
async function deletePromptTemplateGroup(groupId){
    const lib = activePromptLibrary();
    if(lib && lib.id !== 'system'){
        if(!window.confirm(tr('smart.tplDeleteGroupConfirm'))) return;
        try {
            const data = await CanvasPromptTemplateRepository.deleteCategory(groupId);
            promptLibraries = data.library?.libraries || promptLibraries;
            if(promptTemplateCategory === groupId) promptTemplateCategory = 'all';
            renderPromptTemplatePanel({preserveScroll:false});
        } catch(err){ if(typeof setStatus === 'function') setStatus(err.message || '删除失败'); }
        return;
    }
    if(['view','storyboard','character','product','lighting','mine'].includes(groupId)){
        renamePromptTemplateGroup(groupId);
        return;
    }
    if(!window.confirm(tr('smart.tplDeleteGroupConfirm'))) return;
    promptTemplateGroups = promptTemplateGroups.filter(g => g.id !== groupId);
    CanvasPromptTemplateModel.movePresetCategory(groupId,'mine');
    Object.entries(promptTemplateOverrides.editedBuiltins || {}).forEach(([id, item]) => {
        if(item?.category === groupId) promptTemplateOverrides.editedBuiltins[id] = {...item, category:'mine'};
    });
    if(promptTemplateCategory === groupId) promptTemplateCategory = 'all';
    savePromptTemplateGroups();
    savePromptTemplateOverrides();
    renderPromptTemplatePanel({preserveScroll:false});
}
function editPromptPresetForNode(node){
    openPromptTemplatePanel(node?.id || '', node?.promptPresetId ? `mine:${node.promptPresetId}` : '');
}
function assetCategories(type='image'){
    const library = activeAssetLibrary();
    return (library?.categories || assetLibrary.categories || []).filter(cat => (cat.type || 'image') === type);
}
function assetLibraries(){
    return Array.isArray(assetLibrary.libraries) && assetLibrary.libraries.length ? assetLibrary.libraries : [{id:'default', name:'默认资产库', categories:assetLibrary.categories || []}];
}
function activeAssetLibrary(){
    const libs = assetLibraries();
    return libs.find(lib => lib.id === activeAssetLibraryId) || libs[0] || null;
}
function activeAssetCategory(){
    const cats = assetCategories('image');
    if(!cats.length) return null;
    return cats.find(cat => cat.id === activeAssetCategoryId) || cats[0];
}
async function loadAssetLibrary(){
    try {
        const data = await fetch('/api/asset-library').then(r => r.json());
        setAssetLibraryFromResponse(data, {render:false});
        renderAssetLibrary();
    } catch(e) {
        toast(tr('smart.assetLoadFail'));
    }
}
function refreshAssetLibrarySoon(delay=120){
    clearTimeout(assetLibraryRefreshTimer);
    assetLibraryRefreshTimer = setTimeout(async () => {
        await loadAssetLibrary();
        if(mentionPicker?.classList?.contains('open') && mentionSource === 'asset') renderMentionPicker('asset');
    }, delay);
}
function handleAssetLibraryUpdatedMessage(data={}){
    const remoteUpdatedAt = Number(data.updated_at || 0);
    if(remoteUpdatedAt && remoteUpdatedAt <= Number(assetLibraryUpdatedAt || 0)) return;
    refreshAssetLibrarySoon();
}
function refreshPromptTemplatesSoon(delay=120){
    clearTimeout(promptTemplateRefreshTimer);
    promptTemplateRefreshTimer = setTimeout(async () => {
        await loadPromptTemplates();
        const groups = activePromptTemplateGroups();
        if(promptTemplateCategory !== 'all' && !groups.some(group => group.id === promptTemplateCategory)) promptTemplateCategory = 'all';
        if(promptTemplatePanel?.classList?.contains('open')) renderPromptTemplatePanel({preserveScroll:false});
    }, delay);
}
function handlePromptLibraryUpdatedMessage(){
    refreshPromptTemplatesSoon();
}
// 多人协作同步：一个稳定的客户端 id，既用于 WS 连接，也随 saveCanvas 上报，
// 服务器广播 canvas_updated 时带回 client_id，自己发的就忽略，避免自我刷新。
const smartClientId = `canvas_smart_${Math.random().toString(36).slice(2, 10)}${Date.now().toString(36).slice(-4)}`;
let canvasSyncInFlight = false;
let canvasSyncTimer = null;
let canvasMetaPollTimer = null;
// 画布多端合并/资产库同步带外移 canvas-merge-sync.js（第二十一刀）。8 写入态走 setter，节点数组写源仍在主文件。
if(globalThis.CanvasMergeSync){CanvasMergeSync.configure({
        beforeMerge: () => savePromptDraftForCurrent(),
        afterMerge: () => {
            closeAllSmartPopovers(); canvasUiState.clearEditor();
            const subject = selectedNode();
            if(isSmartImageNode(subject)) loadPromptDraft(subject);
        },
        activeAssetCategory: (...a) => activeAssetCategory(...a),
        assetCategories: (...a) => assetCategories(...a),
        assetLibraries: (...a) => assetLibraries(...a),
        handleAssetLibraryUpdatedMessage: (...a) => handleAssetLibraryUpdatedMessage(...a),
        handlePromptLibraryUpdatedMessage: (...a) => handlePromptLibraryUpdatedMessage(...a),
        recoverStuckComfyNodes: (...a) => recoverStuckComfyNodes(...a),
        pruneStaleComfyErrorsOnLoad: (...a) => (globalThis.CanvasComfyJobEngine && CanvasComfyJobEngine.pruneStaleComfyErrorsOnLoad ? CanvasComfyJobEngine.pruneStaleComfyErrorsOnLoad(...a) : undefined),
        refreshConnectionLayer: (...a) => refreshConnectionLayer(...a),
        refreshSmartLogPanel: (...a) => refreshSmartLogPanel(...a),
        render: (...a) => render(...a),
        renderAssetLibrary: (...a) => renderAssetLibrary(...a),
        renderMentionPicker: (...a) => renderMentionPicker(...a),
        resumeJimengPendingNodes: (...a) => resumeJimengPendingNodes(...a),
        resumeSmartPendingTasks: (...a) => resumeSmartPendingTasks(...a),
        smartPendingTasks: (...a) => smartPendingTasks(...a),
        updateCanvasTitleDisplay: (...a) => updateCanvasTitleDisplay(...a),
        activeAssetCategoryId: () => activeAssetCategoryId,
        activeAssetLibraryId: () => activeAssetLibraryId,
        assetLibrary: () => assetLibrary,
        assetLibraryUpdatedAt: () => assetLibraryUpdatedAt,
        canvasMetaPollTimer: () => canvasMetaPollTimer,
        canvasSyncTimer: () => canvasSyncTimer,
        mentionAssetCategoryId: () => mentionAssetCategoryId,
        nodes: () => nodes,
        canvas: () => canvas,
        canvasId: () => canvasId,
        canvasSyncInFlight: () => canvasSyncInFlight,
        dragState: () => dragState,
        mentionPicker: () => mentionPicker,
        mentionSource: () => mentionSource,
        nodeStore: () => nodeStore,
        normalizeLegacySmartNode: () => normalizeLegacySmartNode,
        selectionState: () => selectionState,
        smartClientId: () => smartClientId,
        setActiveAssetCategoryId: v => { activeAssetCategoryId = v; },
        setActiveAssetLibraryId: v => { activeAssetLibraryId = v; },
        setAssetLibrary: v => { assetLibrary = v; },
        setAssetLibraryUpdatedAt: v => { assetLibraryUpdatedAt = v; },
        setCanvasMetaPollTimer: v => { canvasMetaPollTimer = v; },
        setCanvasSyncTimer: v => { canvasSyncTimer = v; },
        setMentionAssetCategoryId: v => { mentionAssetCategoryId = v; },
        setNodes: v => { nodes = v; }
});}
function mergeSmartNodeLists(){return CanvasMergeSync.mergeSmartNodeLists.apply(null, arguments);}
function pruneLegacyDirectorNodes(){return CanvasMergeSync.pruneLegacyDirectorNodes.apply(null, arguments);}
function applyMergedServerCanvas(){return CanvasMergeSync.applyMergedServerCanvas.apply(null, arguments);}
function handleCanvasUpdatedMessage(){return CanvasMergeSync.handleCanvasUpdatedMessage.apply(null, arguments);}
function startCanvasMetaPoll(){return CanvasMergeSync.startCanvasMetaPoll.apply(null, arguments);}
function connectAssetLibrarySyncSocket(){return CanvasMergeSync.connectAssetLibrarySyncSocket.apply(null, arguments);}
function setAssetLibraryFromResponse(){return CanvasMergeSync.setAssetLibraryFromResponse.apply(null, arguments);}
/* ================= 风格库（composer 标签版） =================
   风格 = 提示词框内的可删除标签（仿截图），选中的风格文本在生成时追加到提示词尾部。
   内置风格只读；用户自建风格存 localStorage，可编辑/删除。 */
const USER_STYLE_PRESETS_KEY = 'smart_canvas_style_presets_v1';
const BUILTIN_STYLE_PRESETS = CanvasStylePresets.presets;
let styleLibraryCategory = 'all';
let styleLibraryQuery = '';
let filterLibraryQuery = '';
// Both popovers own wheel scrolling and must never pan/zoom the canvas underneath.
CanvasOverlayRegistry.register('.style-popover,.filter-popover');
let userStylePresets = [];
try {
    const raw = JSON.parse(localStorage.getItem(USER_STYLE_PRESETS_KEY) || '[]');
    userStylePresets = Array.isArray(raw) ? raw.filter(s => s && s.id && s.name) : [];
} catch(_) { userStylePresets = []; }
function persistUserStylePresets(){
    try { localStorage.setItem(USER_STYLE_PRESETS_KEY, JSON.stringify(userStylePresets)); } catch(_) {}
}
function allStylePresets(){
    return [...BUILTIN_STYLE_PRESETS, ...userStylePresets];
}
function stylePresetById(id){
    return allStylePresets().find(s => s.id === id) || CanvasStylePresets.archived.find(s => s.id === id) || null;
}
function isBuiltinStyleId(id){
    return BUILTIN_STYLE_PRESETS.some(s => s.id === id) || CanvasStylePresets.archived.some(s => s.id === id);
}
function saveStylePreset(preset){
    if(!preset || isBuiltinStyleId(preset.id)) return false;
    const idx = userStylePresets.findIndex(s => s.id === preset.id);
    if(idx >= 0) userStylePresets[idx] = preset;
    else userStylePresets.unshift(preset);
    persistUserStylePresets();
    return true;
}
function deleteStylePreset(id){
    userStylePresets = userStylePresets.filter(s => s.id !== id);
    persistUserStylePresets();
}
function styleTokenHtml(preset){
    const filter = preset.kind === 'filter';
    const shot = preset.kind === 'preset';
    return `<span class="mention-style-token${filter ? ' mention-filter-token' : ''}" contenteditable="false" data-preset-kind="${filter ? 'filter' : shot ? 'preset' : 'style'}" data-style-id="${escapeAttr(preset.id)}" data-style-name="${escapeAttr(preset.name)}" data-style-text="${escapeAttr(preset.text || '')}"><i data-lucide="${filter ? 'aperture' : 'palette'}" class="style-token-icon"></i><span>@${filter ? '滤镜·' : shot ? '预设·' : ''}${escapeHtml(preset.name)}</span><button class="style-token-x" type="button" tabindex="-1" title="移除${filter ? '滤镜' : shot ? '预设' : '风格'}"><i data-lucide="x"></i></button></span>`;
}
function insertedStyleIds(){
    if(!promptInput) return [];
    return [...promptInput.querySelectorAll('.mention-style-token:not(.mention-filter-token):not([data-preset-kind="preset"])')].map(t => t.dataset.styleId).filter(Boolean);
}
function selectedFilterPresetId(){
    return promptInput?.querySelector('.mention-filter-token')?.dataset.styleId || 'ft-none';
}
function applyFilterPreset(preset){
    if(!preset || !promptInput) return;
    const current = [...promptInput.querySelectorAll('.mention-filter-token')];
    if(preset.id === 'ft-none'){
        current.forEach(token => token.remove());
    } else if(current.length){
        current[0].outerHTML = styleTokenHtml(preset);
        current.slice(1).forEach(token => token.remove());
    } else {insertStyleToken(preset); return;}
    closeAllSmartPopovers();
    promptInput.dispatchEvent(new Event('input',{bubbles:true}));
    renderComposerStyleControl();
    refreshIcons();
}
function insertStyleToken(preset){
    if(!preset || !promptInput) return;
    if(promptInput.querySelector(`[data-style-id="${CSS.escape(preset.id)}"]`)){ toast('该预设已添加'); return; }
    promptInput.focus();
    const sel = window.getSelection();
    const range = sel && sel.rangeCount && promptInput.contains(sel.anchorNode) ? sel.getRangeAt(0) : null;
    const frag = document.createElement('template');
    frag.innerHTML = styleTokenHtml(preset) + ' ';
    const el = frag.content.firstChild;
    if(range){
        range.deleteContents();
        range.insertNode(el);
        el.after(frag.content.childNodes[0] || document.createTextNode(' '));
    } else {
        promptInput.insertAdjacentHTML('beforeend', styleTokenHtml(preset) + ' ');
    }
    bindStyleTokenRemoval();
    closeAllSmartPopovers();
    promptInput.dispatchEvent(new Event('input', {bubbles:true}));
    renderComposerStyleControl();
    refreshIcons();
}
function bindStyleTokenRemoval(){
    if(!promptInput || promptInput.__styleTokenBound) return;
    promptInput.__styleTokenBound = true;
    promptInput.addEventListener('mousedown', e => {
        if(e.target.closest?.('.style-token-x')) e.preventDefault();
    });
    promptInput.addEventListener('click', e => {
        const x = e.target.closest?.('.style-token-x');
        if(!x) return;
        e.preventDefault();
        e.stopPropagation();
        removeStyleToken(x.closest('.mention-style-token'));
    });
}
function removeStyleToken(token){
    const name = token?.dataset?.styleName || '';
    const kind = token?.dataset.presetKind === 'preset' ? '预设' : token?.classList.contains('mention-filter-token') ? '滤镜' : '风格';
    token?.remove?.();
    if(promptInput){
        promptInput.dispatchEvent(new Event('input', {bubbles:true}));
        renderComposerStyleControl();
        toast(`已移除${kind}「${name}」`);
    }
}
function promptStyleSuffix(parts){
    const texts = (parts || []).filter(part => part.type === 'style').map(part => String(part.text || '').trim()).filter(Boolean);
    const seen = new Set();
    return texts.filter(t => { if(seen.has(t)) return false; seen.add(t); return true; }).join('，');
}
function promptHtmlHasMentionToken(html){
    const s = String(html || '');
    return s.includes('mention-image-token') || s.includes('mention-style-token');
}
function promptHtmlHasImageMentionToken(html){
    return String(html || '').includes('mention-image-token');
}
function styleAssetVersionTag(){
    try { return new URLSearchParams(location.search).get('v') || ''; } catch(_) { return ''; }
}
function stylePresetImageUrl(preset){
    if(preset.image) return preset.image;
    if(isBuiltinStyleId(preset.id)){
        const v = styleAssetVersionTag();
        return `/static/images/styles/${encodeURIComponent(preset.id)}.webp` + (v ? `?v=${encodeURIComponent(v)}` : '');
    }
    return '';
}
function styleTileFallbackBg(preset){
    const src = String(preset.id || '') + String(preset.text || '');
    let h = 0;
    for(let i = 0; i < src.length; i++) h = (h * 31 + src.charCodeAt(i)) >>> 0;
    const hue = h % 360;
    return `linear-gradient(135deg,hsl(${hue} 55% 42%),hsl(${(hue + 48) % 360} 60% 28%))`;
}
function renderComposerStyleControl(){
    if(!composerStyleModeSlot) return;
    composerStyleModeSlot.__hideStyleTip?.();
    bindStyleTokenRemoval();
    const activeIds = insertedStyleIds();
    const label = activeIds.length ? `风格 · ${activeIds.length}` : '风格';
    const tileHtml = preset => {
        const on = activeIds.includes(preset.id);
        const builtin = isBuiltinStyleId(preset.id);
        const url = stylePresetImageUrl(preset);
        // Standalone previews always keep their intrinsic aspect ratio.
        const media = url
            ? `<img class="style-tile-img" src="${escapeAttr(url)}" alt="" loading="lazy" decoding="async" draggable="false"${preset.previewFilter ? ` style="filter:${escapeAttr(preset.previewFilter)}"` : ''}>`
            : `<div class="style-tile-ph"><i data-lucide="palette"></i></div>`;
        return `<div class="style-tile${on ? ' active' : ''}" data-style-option="${escapeAttr(preset.id)}" role="button" tabindex="0" aria-label="${escapeAttr(preset.name)}" aria-pressed="${on}" style="--style-fallback:${styleTileFallbackBg(preset)}" title="${escapeAttr(preset.text || '')}">
            ${media}
            ${preset.image && !preset.generatedPreview ? '<span class="style-tile-preview-label">示意</span>' : ''}
            ${on ? '<span class="style-tile-check"><i data-lucide="check"></i></span>' : ''}
            ${builtin ? '' : '<button type="button" class="style-tile-del" title="删除"><i data-lucide="trash-2"></i></button>'}
            <div class="style-tile-name">${escapeHtml(preset.name)}</div>
        </div>`;
    };
    composerStyleModeSlot.innerHTML = `<div class="smart-control style-mode-control">
        <button class="smart-pill${activeIds.length ? ' has-value' : ''}" type="button" aria-label="${escapeAttr(label)}" aria-expanded="false"><i data-lucide="palette"></i><span>${escapeHtml(label)}</span><i data-lucide="chevron-down" class="pill-caret"></i></button>
        <div class="smart-popover style-popover">
            <div class="style-popover-head">
                <div class="smart-popover-title">风格库 <span class="style-library-count" data-style-count></span></div>
            <label class="style-library-search"><i data-lucide="search"></i><input type="search" data-style-search aria-label="搜索风格" placeholder="搜索风格、媒介或关键词" value="${escapeAttr(styleLibraryQuery)}"></label>
                <button type="button" class="filter-preset-close" data-style-close aria-label="关闭风格库"><i data-lucide="x"></i></button>
            </div>
            <!-- 2026-10-16 老王：「新建」从标题行移到「我的风格」后面 -->
            <div class="style-library-categories" aria-label="风格分类">
                ${[{id:'all',name:'全部'},...CanvasStylePresets.categories,{id:'mine',name:'我的风格'}].map(category => `<button type="button" data-style-category="${category.id}" aria-pressed="${category.id === styleLibraryCategory}">${category.name}</button>`).join('')}
                <button type="button" class="style-new-btn" data-style-new title="新建自定义风格"><i data-lucide="plus"></i><span>新建</span></button>
            </div>
            <div class="style-library-results">
                ${CanvasStylePresets.categories.map(category => `<section data-style-group="${category.id}"><div class="style-option-group-label">${category.name}</div><div class="style-tile-grid">${BUILTIN_STYLE_PRESETS.filter(preset => preset.category === category.id).map(tileHtml).join('')}</div></section>`).join('')}
                <section data-style-group="mine"><div class="style-option-group-label">我的风格</div><div class="style-tile-grid">${userStylePresets.map(tileHtml).join('')}</div></section>
                <div class="style-library-empty" data-style-empty hidden></div>
            </div>
        </div>
    </div>${filterPresetControlHtml()}${shotPresetControlHtml()}`;
    bindComposerStyleControl();
    filterComposerStyleLibrary();
    bindFilterPresetControl();
    bindShotPresetControl();
    refreshIcons();
}
function bindPresetPopoverScroll(pop){
    if(!pop) return;
    pop.addEventListener('wheel',event => {
        const results = pop.querySelector('[data-preset-scroll],.style-library-results');
        if(!results) return;
        if(!results.contains(event.target)){
            event.preventDefault();
            const factor = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? results.clientHeight : 1;
            results.scrollTop += event.deltaY * factor;
        }
        event.stopPropagation();
        event.__smartCanvasWheelHandled = true;
    },{passive:false});
}
function positionPresetPopover(ctrl,pop){
    if(!pop) return;
    const rect = ctrl.getBoundingClientRect();
    const below = window.innerHeight - rect.bottom - 20;
    const above = rect.top - 80;
    const useAbove = below < 420 && above > below;
    const scale = rect.width / ctrl.offsetWidth || 1;
    // Keep wide libraries clear of the fixed left canvas toolbar as well as the viewport edge.
    const leftInset = document.querySelector('.canvas-tool-dock') ? 72 : 12;
    const rightInset = document.querySelector('#canvasAgentToggle') ? 64 : 12;
    const availableWidth = Math.max(200,(window.innerWidth - leftInset - rightInset)/scale);
    pop.style.maxWidth = `${availableWidth}px`;
    pop.style.minWidth = `${Math.min(360,availableWidth)}px`;
    ctrl.classList.toggle('style-pop-above',useAbove);
    pop.style.maxHeight = `${Math.max(180,Math.min(580,(useAbove ? above : below)/scale))}px`;
    pop.style.marginLeft = '0px';
    const bounds = pop.getBoundingClientRect();
    const shift = bounds.right > window.innerWidth - rightInset ? window.innerWidth - rightInset - bounds.right : bounds.left < leftInset ? leftInset - bounds.left : 0;
    if(shift) pop.style.marginLeft = `${shift/scale}px`;
}
function filterPresetControlHtml(){
    const active = selectedFilterPresetId();
    const selected = CanvasFilterPresets.presets.find(preset => preset.id === active);
    const label = active === 'ft-none' ? '滤镜' : `滤镜·${selected?.name || ''}`;
    return `<div class="smart-control filter-mode-control">
        <button class="smart-pill${active !== 'ft-none' ? ' has-value' : ''}" type="button" title="${escapeAttr(label)}" aria-label="${escapeAttr(label)}" aria-expanded="false"><i data-lucide="aperture"></i><span>${escapeHtml(label)}</span><i data-lucide="chevron-down" class="pill-caret"></i></button>
        <div class="smart-popover style-popover filter-popover">
            <div class="style-popover-head"><div class="smart-popover-title">滤镜预设</div><label class="style-library-search"><i data-lucide="search"></i><input type="search" data-filter-search aria-label="搜索滤镜" placeholder="搜索滤镜预设" value="${escapeAttr(filterLibraryQuery)}"></label><button type="button" class="filter-preset-close" data-filter-close aria-label="关闭滤镜预设"><i data-lucide="x"></i></button></div>
            <div class="style-library-results" data-preset-scroll><div class="style-tile-grid filter-preset-grid">
                ${CanvasFilterPresets.presets.map(preset => `<div class="style-tile filter-preset-tile${preset.id === active ? ' active' : ''}" data-filter-option="${preset.id}" role="button" tabindex="0" aria-label="${preset.name}" aria-pressed="${preset.id === active}" title="${escapeAttr(preset.text || '移除当前滤镜')}"><div class="style-tile-img" style="background-image:url('${preset.image}');filter:${preset.previewFilter}"></div>${preset.id === active ? '<span class="style-tile-check"><i data-lucide="check"></i></span>' : ''}<div class="style-tile-name">${preset.name}</div></div>`).join('')}
            </div><div class="style-library-empty" data-filter-empty hidden>没有匹配的滤镜</div></div>
        </div>
    </div>`;
}
function bindFilterPresetControl(){
    const ctrl = composerStyleModeSlot?.querySelector('.filter-mode-control');
    if(!ctrl) return;
    const pop = ctrl.querySelector('.filter-popover');
    const pill = ctrl.querySelector(':scope > .smart-pill');
    const close = () => {ctrl.classList.remove('pinned'); pill?.setAttribute('aria-expanded','false'); if(ctrl.contains(document.activeElement)) document.activeElement.blur();};
    pill.onclick = event => {
        event.preventDefault(); event.stopPropagation();
        const wasPinned = ctrl.classList.contains('pinned');
        closeAllSmartPopovers();
        if(wasPinned){close(); return;}
        ctrl.classList.add('pinned'); pill.setAttribute('aria-expanded','true'); positionPresetPopover(ctrl,pop);
    };
    const search = ctrl.querySelector('[data-filter-search]');
    const filter = () => {
        const query = filterLibraryQuery.trim().toLocaleLowerCase();
        let count = 0;
        ctrl.querySelectorAll('[data-filter-option]').forEach(tile => {
            const preset = CanvasFilterPresets.presets.find(item => item.id === tile.dataset.filterOption);
            tile.hidden = !!query && !`${preset.name} ${preset.text}`.toLocaleLowerCase().includes(query);
            if(!tile.hidden) count++;
        });
        ctrl.querySelector('[data-filter-empty]').hidden = count > 0;
        ctrl.querySelector('[data-preset-scroll]').scrollTop = 0;
    };
    search.addEventListener('input',event => {filterLibraryQuery = event.target.value; filter();});
    ctrl.querySelector('[data-filter-close]').onclick = event => {event.preventDefault(); event.stopPropagation(); close();};
    ctrl.addEventListener('keydown',event => {
        if(event.key === 'Escape'){event.preventDefault(); event.stopPropagation(); close();}
    });
    ctrl.querySelectorAll('[data-filter-option]').forEach(tile => {
        tile.onclick = event => {event.preventDefault(); event.stopPropagation(); applyFilterPreset(CanvasFilterPresets.presets.find(preset => preset.id === tile.dataset.filterOption));};
        tile.onkeydown = event => {if(event.target === tile && ['Enter',' '].includes(event.key)){event.preventDefault(); event.stopPropagation(); tile.click();}};
    });
    filter(); bindPresetPopoverScroll(pop);
}
function filterComposerStyleLibrary(){
    const ctrl = composerStyleModeSlot?.querySelector('.style-mode-control');
    if(!ctrl) return;
    const query = styleLibraryQuery.trim().toLocaleLowerCase();
    let count = 0;
    ctrl.querySelectorAll('[data-style-option]').forEach(tile => {
        const preset = stylePresetById(tile.dataset.styleOption);
        const category = preset?.category || 'mine';
        const categoryName = CanvasStylePresets.categories.find(item => item.id === category)?.name || '我的风格';
        const matches = (styleLibraryCategory === 'all' || styleLibraryCategory === category)
            && (!query || `${preset?.name || ''} ${preset?.text || ''} ${categoryName}`.toLocaleLowerCase().includes(query));
        tile.hidden = !matches;
        if(matches) count++;
    });
    ctrl.querySelectorAll('[data-style-group]').forEach(group => {
        group.hidden = !group.querySelector('[data-style-option]:not([hidden])');
    });
    ctrl.querySelectorAll('[data-style-category]').forEach(button => {
        const active = button.dataset.styleCategory === styleLibraryCategory;
        button.classList.toggle('active',active);
        button.setAttribute('aria-pressed',String(active));
    });
    ctrl.querySelector('[data-style-count]').textContent = `${count} / ${allStylePresets().length}`;
    const empty = ctrl.querySelector('[data-style-empty]');
    empty.hidden = count > 0;
    empty.textContent = styleLibraryCategory === 'mine' && !userStylePresets.length ? '还没有自建风格，点击“新建”添加' : '没有匹配的风格，试试其它关键词或分类';
    ctrl.querySelector('.style-library-results').scrollTop = 0;
}
function bindComposerStyleControl(){
    if(!composerStyleModeSlot) return;
    const ctrl = composerStyleModeSlot.querySelector('.style-mode-control');
    const pill = ctrl?.querySelector(':scope > .smart-pill');
    if(pill){
        pill.onclick = event => {
        event.preventDefault();
        event.stopPropagation();
        const wasPinned = ctrl.classList.contains('pinned');
        closeAllSmartPopovers();
        if(wasPinned && ctrl.contains(document.activeElement)) document.activeElement.blur();
        if(!wasPinned){
            ctrl.classList.add('pinned');
            pill.setAttribute('aria-expanded','true');
            positionPresetPopover(ctrl,ctrl.querySelector('.style-popover'));
        }
    };
    // 跟随鼠标的悬浮提示（tooltip 渲染在 body 层，不在按钮内）
    let styleTip = null;
    const hideStyleTip = () => {
        if(styleTip){ styleTip.remove(); styleTip = null; }
        pill.removeEventListener('mousemove', moveStyleTip);
    };
    composerStyleModeSlot.__hideStyleTip = hideStyleTip;
    const moveStyleTip = e => {
        if(!styleTip) return;
        const pad = 14;
        const x = Math.min(e.clientX + pad, window.innerWidth - styleTip.offsetWidth - 8);
        const y = Math.min(e.clientY + pad, window.innerHeight - styleTip.offsetHeight - 8);
        styleTip.style.left = x + 'px';
        styleTip.style.top = y + 'px';
    };
    pill.addEventListener('mouseenter', e => {
        hideStyleTip();
        styleTip = document.createElement('div');
        styleTip.className = 'smart-mouse-tip';
        styleTip.textContent = '风格';
        document.body.appendChild(styleTip);
        moveStyleTip(e);
        pill.addEventListener('mousemove', moveStyleTip);
    });
    pill.addEventListener('mouseleave', hideStyleTip);
    }
    ctrl?.querySelector('[data-style-close]')?.addEventListener('click',event=>{event.preventDefault();event.stopPropagation();ctrl.classList.remove('pinned');pill?.setAttribute('aria-expanded','false');if(ctrl.contains(document.activeElement))document.activeElement.blur();});
    bindPresetPopoverScroll(ctrl?.querySelector('.style-popover'));
    ctrl?.querySelector('[data-style-search]')?.addEventListener('input',event => {
        styleLibraryQuery = event.target.value;
        filterComposerStyleLibrary();
    });
    ctrl?.addEventListener('keydown',event => {
        if(event.key !== 'Escape') return;
        event.preventDefault(); event.stopPropagation();
        ctrl.classList.remove('pinned');
        pill?.setAttribute('aria-expanded','false');
        if(ctrl.contains(document.activeElement)) document.activeElement.blur();
    });
    ctrl?.querySelectorAll('[data-style-category]').forEach(button => button.addEventListener('click',event => {
        event.preventDefault(); event.stopPropagation();
        styleLibraryCategory = button.dataset.styleCategory;
        filterComposerStyleLibrary();
    }));
    ctrl?.querySelectorAll('[data-style-option]').forEach(row => {
        const id = row.dataset.styleOption;
        row.addEventListener('click', e => {
            if(e.target.closest('.style-tile-del')) return;
            e.preventDefault(); e.stopPropagation();
            const preset = stylePresetById(id);
            if(preset) insertStyleToken(preset);
            renderComposerStyleControl();
        });
        row.addEventListener('keydown',event => {
            if(event.target !== row || !['Enter',' '].includes(event.key)) return;
            event.preventDefault(); event.stopPropagation(); row.click();
        });
        row.querySelector('.style-tile-del')?.addEventListener('click', e => {
            e.preventDefault(); e.stopPropagation();
            const btn = row.querySelector('.style-tile-del');
            if(btn?.dataset.armed === '1'){
                deleteStylePreset(id);
                promptInput?.querySelectorAll(`.mention-style-token[data-style-id="${CSS.escape(id)}"]`).forEach(t => t.remove());
                promptInput?.dispatchEvent(new Event('input', {bubbles:true}));
                renderComposerStyleControl();
                toast('已删除风格');
                return;
            }
            if(!btn) return;
            btn.dataset.armed = '1';
            btn.classList.add('armed');
            setTimeout(() => {
                if(!btn.isConnected) return;
                btn.dataset.armed = '';
                btn.classList.remove('armed');
                refreshIcons();
            }, 4000);
        });
    });
    ctrl?.querySelector('[data-style-new]')?.addEventListener('click', async e => {
        e.preventDefault(); e.stopPropagation();
        const name = await openAssetNameDialog({title:'新建风格', value:'', placeholder:'风格名称', cancelValue:null});
        if(!name) return;
        const text = await openAssetNameDialog({title:`「${name}」的风格提示词`, value:'', placeholder:'如：水墨画风格，留白构图，墨色浓淡渐变', cancelValue:null, multiline:true});
        if(text === null) return;
        saveStylePreset({id:`us-${Date.now().toString(36)}`, name, text: text || ''});
        renderComposerStyleControl();
        toast('已创建风格');
    });
}

/* ===== 提示词库停靠（2026-10-16 老王：资产库面板的「提示词库」tab）=====
 * 不复制第二套模板库 UI——把 #promptTemplatePanel 整个搬进 #assetPanel（.docked 模式），
 * 库选择/搜索/分组/编辑/应用全部复用。停靠时 target 固定 'composer'（应用=写进下方提示词框），
 * controller 对 .docked 有专门守卫：closePanel 不关（由 tab 切换/面板关闭接管）。
 */
let promptTemplatePanelHome = null;
function undockPromptTemplatePanel(){
    if(!promptTemplatePanel || !promptTemplatePanel.classList.contains('docked')) return;
    promptTemplatePanel.classList.remove('docked', 'open');
    promptTemplatePanel.dataset.target = '';
    promptTemplatePanel.dataset.nodeId = '';
    promptTemplatePanel.style.cssText = '';
    (promptTemplatePanelHome || shell || document.body).appendChild(promptTemplatePanel);
    const closeBtn = document.getElementById('promptTemplateClose');
    if(closeBtn) closeBtn.onclick = () => CanvasPromptTemplateController.closePanel();
    restorePromptTemplateSearch();
    promptTemplatePanelHome = null;
}
// 2026-10-17 老王：停靠进资产库时，搜索框挪到面板头部右上角（照风格面板
// .style-panel-top 的排布：tab 左、搜索居中撑开、× 右）。视图只重建 cats/body 的
// innerHTML，整个搜索容器搬家不影响绑定（controller 按 id 取 input）。
function movePromptTemplateSearchToPanelTop(){
    const search = promptTemplatePanel?.querySelector('.prompt-template-search');
    const topRow = assetPanel?.querySelector('.style-panel-top');
    const closeBtn = document.getElementById('assetCloseBtn');
    if(!search || !topRow) return;
    if(closeBtn) topRow.insertBefore(search, closeBtn);
    else topRow.appendChild(search);
}
function restorePromptTemplateSearch(){
    const search = assetPanel?.querySelector('.style-panel-top .prompt-template-search')
        || document.querySelector('.style-panel-top .prompt-template-search');
    if(!search) return;
    const before = promptTemplatePanel?.querySelector('#promptTemplateCats');
    if(before) before.parentElement.insertBefore(search, before);
    else promptTemplatePanel?.appendChild(search);
}
function dockPromptTemplateInAssetPanel(dock){
    if(!assetPanel || !promptTemplatePanel) return;
    if(!dock){
        undockPromptTemplatePanel();
        return;
    }
    if(promptTemplatePanel.classList.contains('docked')) return;
    promptTemplatePanelHome = promptTemplatePanel.parentElement || shell || document.body;
    promptTemplatePanel.classList.add('docked', 'open');
    promptTemplatePanel.style.cssText = '';
    promptTemplatePanel.dataset.target = 'composer';
    promptTemplatePanel.dataset.nodeId = '';
    assetPanel.appendChild(promptTemplatePanel);
    const closeBtn = document.getElementById('promptTemplateClose');
    // 停靠态下 × = 退出提示词库 tab，回到图片资产
    if(closeBtn) closeBtn.onclick = () => { assetTab = 'image'; renderAssetLibrary(); };
    movePromptTemplateSearchToPanelTop();
    renderPromptTemplatePanel({preserveScroll:false});
}
// composer/节点入口打开模板库时（controller.openPanel 会搬回 shell 并 dispatch 此事件），同步 tab 态
promptTemplatePanel?.addEventListener('prompttemplate-undocked', () => {
    if(assetTab === 'prompts'){ assetTab = 'image'; renderAssetLibrary(); }
});

function toggleAssetLibrary(open=!assetLibraryOpen){
    if(!assetPanel || !assetToggle) return;
    assetLibraryOpen = !!open;
    assetPanel.classList.toggle('open', assetLibraryOpen);
    assetToggle?.classList.toggle('active', assetLibraryOpen);
    if(assetLibraryOpen) loadAssetLibrary();
    else undockPromptTemplatePanel();
    render();
}

/* ===== 左侧风格面板（2026-10-05）=====
 * 老王需求：左侧工具栏资产库下面加「风格」入口，滤镜整合进去，通过按钮切换。
 * 数据源与 composer 里的风格库/滤镜完全同一套（BUILTIN_STYLE_PRESETS / userStylePresets /
 * CanvasFilterPresets），所以这里只做「另一种摆放」——点选后仍然插到 promptInput 里，
 * 与 composer 的两个 pill 共享同一份选中态。
 */
let stylePanelOpen = false;
let stylePanelTab = 'style';
/* 风格面板是独立于画布的浮层：不注册的话点它会冒泡到 shell.onclick，
   被当成"点了空白"→ 触发 clearSelection/render，把刚插进 composer 的 token 一起清掉。
   与 .asset-panel 一样注册进 overlay/pan-exclude/click-empty。 */
CanvasOverlayRegistry.register('#stylePanel,.style-panel', ['overlay', 'pan-exclude', 'click-empty', 'wheel-exclude']);
function stylePanelVisible(){
    return Boolean(stylePanel?.classList.contains('open'));
}
function toggleStylePanel(open=!stylePanelOpen){
    if(!stylePanel || !styleToggle) return;
    stylePanelOpen = !!open;
    stylePanel.classList.toggle('open', stylePanelOpen);
    styleToggle.classList.toggle('active', stylePanelOpen);
    // 资产库与风格面板同位（left:88px），同时开会叠在一起，开一个就收另一个。
    if(stylePanelOpen && assetLibraryOpen) toggleAssetLibrary(false);
    if(stylePanelOpen) renderStylePanel();
}
function setStylePanelTab(tab){
    stylePanelTab = tab === 'filter' ? 'filter' : 'style';
    document.querySelectorAll('#stylePanel [data-style-tab]').forEach(btn => {
        const on = btn.dataset.styleTab === stylePanelTab;
        btn.classList.toggle('active', on);
        btn.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    const stylePane = document.getElementById('stylePanelStylePane');
    const filterPane = document.getElementById('stylePanelFilterPane');
    if(stylePane) stylePane.style.display = stylePanelTab === 'style' ? 'flex' : 'none';
    if(filterPane) filterPane.style.display = stylePanelTab === 'filter' ? 'flex' : 'none';
    stylePanel.querySelectorAll('[data-panel-search-kind]').forEach(label=>{label.hidden=label.dataset.panelSearchKind!==stylePanelTab;});
}
function stylePanelTileHtml(preset, activeIds){
    const on = activeIds.includes(preset.id);
    const builtin = isBuiltinStyleId(preset.id);
    const url = stylePresetImageUrl(preset);
    const media = url
        ? `<img class="style-tile-img" src="${escapeAttr(url)}" alt="" loading="lazy" decoding="async" draggable="false"${preset.previewFilter ? ` style="filter:${escapeAttr(preset.previewFilter)}"` : ''}>`
        : `<div class="style-tile-ph"><i data-lucide="palette"></i></div>`;
    return `<div class="style-tile${on ? ' active' : ''}" data-panel-style-option="${escapeAttr(preset.id)}" role="button" tabindex="0" aria-label="${escapeAttr(preset.name)}" aria-pressed="${on}" style="--style-fallback:${styleTileFallbackBg(preset)}" title="${escapeAttr(preset.text || '')}">
        ${media}
        ${on ? '<span class="style-tile-check"><i data-lucide="check"></i></span>' : ''}
        ${builtin ? '' : '<button type="button" class="style-tile-del" title="删除"><i data-lucide="trash-2"></i></button>'}
        <div class="style-tile-name">${escapeHtml(preset.name)}</div>
    </div>`;
}
function stylePanelFilterTileHtml(preset, active){
    return `<div class="style-tile filter-preset-tile${preset.id === active ? ' active' : ''}" data-panel-filter-option="${preset.id}" role="button" tabindex="0" aria-label="${preset.name}" aria-pressed="${preset.id === active}" title="${escapeAttr(preset.text || '移除当前滤镜')}"><div class="style-tile-img" style="background-image:url('${preset.image}');filter:${preset.previewFilter}"></div>${preset.id === active ? '<span class="style-tile-check"><i data-lucide="check"></i></span>' : ''}<div class="style-tile-name">${preset.name}</div></div>`;
}
function renderStylePanel(){
    if(!stylePanel) return;
    setStylePanelTab(stylePanelTab);
    const activeIds = insertedStyleIds();
    const categories = stylePanel.querySelector('[data-panel-style-categories]');
    if(categories){
        // 2026-10-16 老王：「新建」从 head-row 移到分类行「我的风格」后面
        categories.innerHTML = [{id:'all',name:'全部'},...CanvasStylePresets.categories,{id:'mine',name:'我的风格'}]
            .map(c => `<button type="button" data-panel-style-category="${c.id}" aria-pressed="${c.id === styleLibraryCategory}" class="${c.id === styleLibraryCategory ? 'active' : ''}">${c.name}</button>`).join('')
            + `<button type="button" class="style-new-btn" data-panel-style-new title="新建自定义风格"><i data-lucide="plus"></i><span>新建</span></button>`;
    }
    const results = stylePanel.querySelector('[data-panel-style-results]');
    if(results){
        results.innerHTML = `
            ${CanvasStylePresets.categories.map(category => `<section data-panel-style-group="${category.id}"><div class="style-option-group-label">${category.name}</div><div class="style-tile-grid">${BUILTIN_STYLE_PRESETS.filter(p => p.category === category.id).map(p => stylePanelTileHtml(p, activeIds)).join('')}</div></section>`).join('')}
            <section data-panel-style-group="mine"><div class="style-option-group-label">我的风格</div><div class="style-tile-grid">${userStylePresets.map(p => stylePanelTileHtml(p, activeIds)).join('')}</div></section>
            <div class="style-library-empty" data-panel-style-empty hidden></div>`;
    }
    const filterResults = stylePanel.querySelector('[data-panel-filter-results]');
    if(filterResults){
        const activeFilter = selectedFilterPresetId();
        filterResults.innerHTML = `<div class="style-tile-grid filter-preset-grid">${CanvasFilterPresets.presets.map(p => stylePanelFilterTileHtml(p, activeFilter)).join('')}</div><div class="style-library-empty" data-panel-filter-empty hidden>没有匹配的滤镜</div>`;
    }
    filterStylePanelLibrary();
    refreshIcons();
}
function filterStylePanelLibrary(){
    if(!stylePanel) return;
    const query = styleLibraryQuery.trim().toLocaleLowerCase();
    let count = 0;
    stylePanel.querySelectorAll('[data-panel-style-option]').forEach(tile => {
        const preset = stylePresetById(tile.dataset.panelStyleOption);
        const category = preset?.category || 'mine';
        const categoryName = CanvasStylePresets.categories.find(item => item.id === category)?.name || '我的风格';
        const matches = (styleLibraryCategory === 'all' || styleLibraryCategory === category)
            && (!query || `${preset?.name || ''} ${preset?.text || ''} ${categoryName}`.toLocaleLowerCase().includes(query));
        tile.hidden = !matches;
        if(matches) count++;
    });
    stylePanel.querySelectorAll('[data-panel-style-group]').forEach(group => {
        group.hidden = !group.querySelector('[data-panel-style-option]:not([hidden])');
    });
    stylePanel.querySelectorAll('[data-panel-style-category]').forEach(button => {
        const active = button.dataset.panelStyleCategory === styleLibraryCategory;
        button.classList.toggle('active', active);
        button.setAttribute('aria-pressed', String(active));
    });
    const empty = stylePanel.querySelector('[data-panel-style-empty]');
    if(empty){
        empty.hidden = count > 0;
        empty.textContent = styleLibraryCategory === 'mine' && !userStylePresets.length ? '还没有自建风格，点击“新建”添加' : '没有匹配的风格，试试其它关键词或分类';
    }
    const fquery = filterLibraryQuery.trim().toLocaleLowerCase();
    let fcount = 0;
    stylePanel.querySelectorAll('[data-panel-filter-option]').forEach(tile => {
        const preset = CanvasFilterPresets.presets.find(item => item.id === tile.dataset.panelFilterOption);
        tile.hidden = !!fquery && !`${preset?.name || ''} ${preset?.text || ''}`.toLocaleLowerCase().includes(fquery);
        if(!tile.hidden) fcount++;
    });
    const fempty = stylePanel.querySelector('[data-panel-filter-empty]');
    if(fempty) fempty.hidden = fcount > 0;
    const results = stylePanel.querySelector('[data-panel-style-results]');
    if(results) results.scrollTop = 0;
}
function bindStylePanel(){
    if(!stylePanel) return;
    stylePanel.querySelectorAll('[data-style-tab]').forEach(btn => {
        btn.addEventListener('click', event => {event.preventDefault(); setStylePanelTab(btn.dataset.styleTab);});
    });
    stylePanel.querySelector('[data-panel-style-search]')?.addEventListener('input', event => {
        styleLibraryQuery = event.target.value;
        filterStylePanelLibrary();
    });
    stylePanel.querySelector('[data-panel-filter-search]')?.addEventListener('input', event => {
        filterLibraryQuery = event.target.value;
        filterStylePanelLibrary();
    });
    stylePanel.addEventListener('click', event => {
        // 面板内部一律不让事件冒泡到 shell：shell.onclick 的"点空白清选中"会把
        // 刚插进 composer 的风格/滤镜 token 一起 render 掉。
        event.stopPropagation();
        const categoryBtn = event.target.closest('[data-panel-style-category]');
        if(categoryBtn){
            event.preventDefault();
            styleLibraryCategory = categoryBtn.dataset.panelStyleCategory;
            filterStylePanelLibrary();
            return;
        }
        const filterTile = event.target.closest('[data-panel-filter-option]');
        if(filterTile){
            event.preventDefault();
            applyFilterPreset(CanvasFilterPresets.presets.find(p => p.id === filterTile.dataset.panelFilterOption));
            // 延到微任务再重建面板：本帧内若重建，事件继续冒泡时 e.target 已脱离 DOM，
            // 上层浮层判定会失效（曾是"选完滤镜 token 立刻被清空"的真凶）。
            queueMicrotask(() => renderStylePanel());
            return;
        }
        const tile = event.target.closest('[data-panel-style-option]');
        if(tile){
            if(event.target.closest('.style-tile-del')) return;
            event.preventDefault();
            const preset = stylePresetById(tile.dataset.panelStyleOption);
            if(preset) insertStyleToken(preset);
            queueMicrotask(() => renderStylePanel());
            return;
        }
        const newBtn = event.target.closest('[data-panel-style-new]');
        if(newBtn){
            event.preventDefault();
            openStylePanelNewPresetDialog();
        }
    });
    stylePanel.addEventListener('click', event => {
        const del = event.target.closest('.style-tile-del');
        if(!del) return;
        event.preventDefault();
        event.stopPropagation();
        const tile = del.closest('[data-panel-style-option]');
        const id = tile?.dataset.panelStyleOption;
        if(!id) return;
        if(del.dataset.armed === '1'){
            deleteStylePreset(id);
            promptInput?.querySelectorAll(`.mention-style-token[data-style-id="${CSS.escape(id)}"]`).forEach(t => t.remove());
            promptInput?.dispatchEvent(new Event('input', {bubbles:true}));
            renderComposerStyleControl();
            renderStylePanel();
            toast('已删除风格');
            return;
        }
        del.dataset.armed = '1';
        del.classList.add('armed');
        setTimeout(() => {
            if(!del.isConnected) return;
            del.dataset.armed = '';
            del.classList.remove('armed');
            refreshIcons();
        }, 4000);
    }, true);
}
async function openStylePanelNewPresetDialog(){
    const name = await openAssetNameDialog({title:'新建风格', value:'', placeholder:'风格名称', cancelValue:null});
    if(!name) return;
    const text = await openAssetNameDialog({title:`「${name}」的风格提示词`, value:'', placeholder:'如：水墨画风格，留白构图，墨色浓淡渐变', cancelValue:null, multiline:true});
    if(text === null) return;
    saveStylePreset({id:`us-${Date.now().toString(36)}`, name, text: text || ''});
    renderComposerStyleControl();
    renderStylePanel();
    toast('已创建风格');
}

function assetCategoryForMention(){
    const cats = assetCategories('image');
    if(!cats.length) return null;
    return cats.find(cat => cat.id === mentionAssetCategoryId)
        || cats.find(cat => cat.id === activeAssetCategoryId)
        || cats.find(cat => (cat.items || []).length)
        || cats[0];
}
function assetMediaKind(item){
    if(!item) return 'image';
    if(item.kind === 'video' || item.type === 'video') return 'video';
    if(item.kind === 'audio' || item.type === 'audio') return 'audio';
    const url = String(item.url || item.thumbnail || '').toLowerCase().split('?')[0];
    const name = String(item.name || '').toLowerCase();
    if(/\.(mp4|webm|mov|m4v|avi|mkv)$/.test(url) || /\.(mp4|webm|mov|m4v|avi|mkv)$/.test(name)) return 'video';
    if(/\.(mp3|wav|m4a|aac|ogg|flac)$/.test(url) || /\.(mp3|wav|m4a|aac|ogg|flac)$/.test(name)) return 'audio';
    return 'image';
}
function assetThumbHtml(item){
    const url = escapeAttr(item.url || '');
    const thumb = escapeAttr(item.thumbnail || item.thumb || item.preview || item.url || '');
    const kind = assetMediaKind(item);
    if(kind === 'video'){
        return `<div class="asset-thumb-wrap"><video class="asset-thumb" src="${url}" data-url="${url}" muted preload="metadata" playsinline disablepictureinpicture controlslist="nodownload noplaybackrate noremoteplayback"></video><span class="asset-video-badge"><i data-lucide="film"></i>VIDEO</span></div>`;
    }
    if(kind === 'audio'){
        return `<div class="asset-thumb-wrap">${audioThumbHtml(item.name || '音频', '', 'asset-thumb')}</div>`;
    }
    return `<img class="asset-thumb" src="${thumb}" alt="">`;
}
function renderAssetLibrary(){
    if(!assetPanel || !assetGrid || !assetCategorySelect) return;
    // 2026-10-17 老王：切到「提示词库」后「图片资产」仍显示选中——class 切了，但
    // canvas-interaction-style.css 也给 [role="tab"][aria-selected="true"] 上选中色，
    // aria-selected 必须同步，否则视觉上两个 tab 都是绿的（照 setStylePanelTab 的做法）。
    document.querySelectorAll('[data-asset-tab]').forEach(btn => {
        const on = btn.dataset.assetTab === assetTab;
        btn.classList.toggle('active', on);
        btn.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    const libs = assetLibraries();
    if(!activeAssetLibraryId || !libs.some(lib => lib.id === activeAssetLibraryId)) activeAssetLibraryId = libs[0]?.id || '';
    if(assetLibrarySelect){
        assetLibrarySelect.innerHTML = libs.map(lib => `<option value="${escapeHtml(lib.id)}" ${lib.id === activeAssetLibraryId ? 'selected' : ''}>${escapeHtml(lib.name || '资产库')}</option>`).join('');
    }
    const imageMode = assetTab === 'image';
    assetImageControls.style.display = imageMode ? 'block' : 'none';
    assetDropZone.style.display = imageMode ? 'flex' : 'none';
    assetGrid.style.display = imageMode ? 'grid' : 'none';
    // 2026-10-16 老王：删掉「工作流」占位 tab，换成「提示词库」——把模板库面板停靠进资产库面板
    dockPromptTemplateInAssetPanel(!imageMode);
    if(!imageMode){ refreshIcons(); return; }
    const cats = assetCategories('image');
    if(!cats.some(cat => cat.id === activeAssetCategoryId)) activeAssetCategoryId = cats[0]?.id || '';
    assetCategorySelect.innerHTML = cats.map(cat => `<option value="${escapeHtml(cat.id)}" ${cat.id === activeAssetCategoryId ? 'selected' : ''}>${escapeHtml(cat.name || tr('smart.assetFolder'))}</option>`).join('');
    const cat = activeAssetCategory();
    const items = cat?.items || [];
    assetGrid.innerHTML = items.length ? items.map(item => `
        <div class="asset-item" draggable="true" data-asset-id="${escapeHtml(item.id)}" data-url="${escapeHtml(item.url)}" data-name="${escapeHtml(item.name || 'asset')}" data-kind="${escapeHtml(assetMediaKind(item))}" data-version-count="${Array.isArray(item.versions) ? item.versions.length : 0}">
            ${assetThumbHtml(item)}
            ${Array.isArray(item.versions) && item.versions.length > 1 ? `<span class="asset-version-badge" title="${escapeAttr(tr('smart.assetVersionBadgeTip'))}">v${item.versions.length}</span>` : ''}
            <div class="asset-meta">
                <span class="asset-name" title="${escapeHtml(item.name || '')}">${escapeHtml(item.name || 'asset')}</span>
                <button class="asset-mini-btn" type="button" data-rename-asset="${escapeHtml(item.id)}" title="${escapeHtml(tr('smart.assetRename'))}"><i data-lucide="pencil"></i></button>
                <button class="asset-mini-btn" type="button" data-delete-asset="${escapeHtml(item.id)}" title="${escapeHtml(tr('common.delete'))}"><i data-lucide="trash-2"></i></button>
            </div>
        </div>
    `).join('') : `<div class="asset-empty">${escapeHtml(tr('smart.assetEmpty'))}</div>`;
    bindAssetItemEvents();
    refreshIcons();
}
function openAssetNameDialog({title='', value='', placeholder='', cancelValue='', multiline=false }={}){
    if(!assetDialogBackdrop || !assetDialogInput || !assetDialogOk || !assetDialogCancel) return Promise.resolve(cancelValue);
    return new Promise(resolve => {
        assetDialogTitle.textContent = title || tr('smart.assetRename');
        assetDialogInput.value = value || '';
        assetDialogInput.placeholder = placeholder || '';
        assetDialogInput.classList.toggle('is-multiline', Boolean(multiline));
        assetDialogInput.rows = multiline ? 5 : 1;
        assetDialogBackdrop.hidden = false;
        assetDialogBackdrop.classList.add('open');
        assetDialogInput.focus();
        assetDialogInput.select();
        const cleanup = result => {
            assetDialogBackdrop.classList.remove('open');
            assetDialogBackdrop.hidden = true;
            assetDialogOk.onclick = null;
            assetDialogCancel.onclick = null;
            assetDialogInput.onkeydown = null;
            assetDialogBackdrop.onmousedown = null;
            assetDialogInput.classList.remove('is-multiline');
            assetDialogInput.rows = 1;
            resolve(result);
        };
        assetDialogOk.onclick = () => cleanup(assetDialogInput.value.trim());
        assetDialogCancel.onclick = () => cleanup(cancelValue);
        assetDialogInput.onkeydown = event => {
            if(event.key === 'Enter' && !multiline) cleanup(assetDialogInput.value.trim());
            if(event.key === 'Enter' && multiline && (event.ctrlKey || event.metaKey)) cleanup(assetDialogInput.value.trim());
            if(event.key === 'Escape') cleanup(cancelValue);
        };
        assetDialogBackdrop.onmousedown = event => {
            if(event.target === assetDialogBackdrop) cleanup(cancelValue);
        };
    });
}
function positionAssetHoverPreview(event){
    if(!assetHoverPreview || assetHoverPreview.hidden || assetHoverPreview.style.display === 'none') return;
    const pad = 14;
    const w = assetHoverPreview.offsetWidth || 260;
    const h = assetHoverPreview.offsetHeight || 300;
    let left = event.clientX - w - 16;
    if(left < pad) left = event.clientX + 16;
    left = Math.max(pad, Math.min(window.innerWidth - w - pad, left));
    const top = Math.max(pad, Math.min(window.innerHeight - h - pad, event.clientY + 12));
    assetHoverPreview.style.left = `${left}px`;
    assetHoverPreview.style.top = `${top}px`;
}
function showAssetHoverPreview(event, item){
    if(!assetHoverPreview || !item?.url) return;
    let media = assetHoverPreview.querySelector('img,video');
    const name = assetHoverPreview.querySelector('.asset-hover-name');
    const kind = assetMediaKind(item);
    if(kind === 'video' && media?.tagName?.toLowerCase() !== 'video'){
        media?.replaceWith(document.createElement('video'));
        media = assetHoverPreview.querySelector('video');
    } else if(kind !== 'video' && media?.tagName?.toLowerCase() !== 'img'){
        media?.replaceWith(document.createElement('img'));
        media = assetHoverPreview.querySelector('img');
    }
    if(kind === 'video'){
        media.muted = true;
        media.loop = true;
        media.playsInline = true;
        media.preload = 'metadata';
        media.controls = false;
        media.disablePictureInPicture = true;
        media.setAttribute('disablepictureinpicture', '');
        media.setAttribute('controlslist', 'nodownload noplaybackrate noremoteplayback');
        media.src = item.url;
        media.play?.().catch(() => {});
    } else {
        media.src = item.url;
        media.alt = 'asset preview';
    }
    name.textContent = item.name || 'asset';
    assetHoverPreview.hidden = false;
    assetHoverPreview.style.display = 'block';
    positionAssetHoverPreview(event);
}
function hideAssetHoverPreview(){
    if(!assetHoverPreview) return;
    assetHoverPreview.style.display = 'none';
    assetHoverPreview.hidden = true;
    const media = assetHoverPreview.querySelector('img,video');
    media?.pause?.();
    media?.removeAttribute('src');
    media?.load?.();
}
function beginAssetInlineRename(assetId){
    const item = (activeAssetCategory()?.items || []).find(x => x.id === assetId);
    const card = [...assetGrid.querySelectorAll('.asset-item')].find(el => el.dataset.assetId === assetId);
    const nameEl = card?.querySelector('.asset-name');
    if(!item || !card || !nameEl || card.querySelector('.asset-rename-input')) return;
    hideAssetHoverPreview();
    const previousName = item.name || 'asset';
    const input = document.createElement('input');
    input.className = 'asset-rename-input';
    input.type = 'text';
    input.value = previousName;
    input.setAttribute('aria-label', tr('smart.assetRename'));
    card.draggable = false;
    nameEl.replaceWith(input);
    input.focus();
    input.select();
    let done = false;
    const restore = () => {
        if(input.isConnected) input.replaceWith(nameEl);
        card.draggable = true;
    };
    const finish = async save => {
        if(done) return;
        done = true;
        const name = input.value.trim();
        if(!save || !name || name === previousName){
            restore();
            return;
        }
        input.disabled = true;
        try {
            const data = await fetch(`/api/asset-library/items/${encodeURIComponent(assetId)}`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name})}).then(r => r.json());
            setAssetLibraryFromResponse(data);
        } catch(err){
            restore();
            toast(err.message || tr('smart.assetAddFail'));
        }
    };
    input.addEventListener('keydown', event => {
        event.stopPropagation();
        if(event.key === 'Enter'){
            event.preventDefault();
            finish(true);
        } else if(event.key === 'Escape'){
            event.preventDefault();
            finish(false);
        }
    });
    input.addEventListener('pointerdown', event => event.stopPropagation());
    input.addEventListener('mousedown', event => event.stopPropagation());
    input.addEventListener('click', event => event.stopPropagation());
    input.addEventListener('blur', () => finish(true));
}
function bindAssetItemEvents(){
    assetGrid.querySelectorAll('.asset-item').forEach(el => {
        const thumb = el.querySelector('.asset-thumb');
        thumb?.addEventListener('mouseenter', e => showAssetHoverPreview(e, {url:el.dataset.url, name:el.dataset.name, kind:el.dataset.kind}));
        thumb?.addEventListener('mousemove', e => positionAssetHoverPreview(e));
        thumb?.addEventListener('mouseleave', hideAssetHoverPreview);
        el.addEventListener('dragstart', e => {
            hideAssetHoverPreview();
            e.dataTransfer.effectAllowed = 'copy';
            e.dataTransfer.setData('application/x-smart-asset', JSON.stringify({url:el.dataset.url, name:el.dataset.name, kind:el.dataset.kind, assetId:el.dataset.assetId || ''}));
            e.dataTransfer.setData('text/plain', el.dataset.url || '');
        });
    });
    assetGrid.querySelectorAll('[data-rename-asset]').forEach(btn => {
        btn.onclick = async e => {
            e.preventDefault(); e.stopPropagation();
            beginAssetInlineRename(btn.dataset.renameAsset);
        };
    });
    assetGrid.querySelectorAll('[data-delete-asset]').forEach(btn => {
        btn.onclick = async e => {
            e.preventDefault(); e.stopPropagation();
            btn.disabled = true;
            try {
                const data = await fetch(`/api/asset-library/items/${encodeURIComponent(btn.dataset.deleteAsset)}`, {method:'DELETE'}).then(r => r.json());
                setAssetLibraryFromResponse(data);
            } catch(err){
                btn.disabled = false;
                toast(err.message || tr('smart.assetAddFail'));
            }
        };
    });
}
async function addUrlToAssetLibrary(url, name=''){
    const cat = activeAssetCategory();
    if(!cat){ toast(tr('smart.assetNoFolder')); return; }
    const data = await fetch('/api/asset-library/items', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({library_id:activeAssetLibraryId, category_id:cat.id, url, name})}).then(async r => {
        if(!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || tr('smart.assetAddFail'));
        return r.json();
    });
    setAssetLibraryFromResponse(data);
    toast(tr('smart.assetSaved'));
}
function canvasImageDragPayload(node, index=0){
    const img = node?.images?.[index];
    if(!img?.url) return null;
    return {url:img.url, name:img.name || node.title || 'image'};
}
async function loadCanvas(){
    if(!canvasId) return;
    try {
        const res = await fetch(`/api/canvases/${encodeURIComponent(canvasId)}`);
        if(!res.ok) return;
        const data = await res.json();
        canvas = data.canvas;
        CanvasMergeSync.rememberServerCanvas({...canvas, nodes:(canvas.nodes || []).map(normalizeLegacySmartNode).filter(Boolean)});
        // ③ 先看看本地有没有比服务端更新的草稿（崩溃/断网时的未同步改动）
        try { await restoreCanvasDraftIfNewer(data.canvas); } catch(e) {}
        // Phase 8：按 canvasId 载入持久产物（Sidebar 不是全局文件列表）
        canvasAgentArtifactsState = Array.isArray(canvas.artifacts) ? canvas.artifacts.slice() : [];
        canvasAgentActiveArtifactId = '';
        canvasAgentActiveSectionId = '';   // Phase 9：切换 Canvas 重置内部导航层级
        canvasAgentActiveItemId = '';
        if(CanvasArtifactModel.ARTIFACT_AUTO_MIGRATE) migrateLegacyArtifactsToConversations();
        renderArtifactSidebar();
        document.title = canvas.title || tr('canvas.smartCanvas');
        updateCanvasTitleDisplay();
        const cleanedCanvas = pruneLegacyDirectorNodes(
            (Array.isArray(canvas.nodes) ? canvas.nodes : []).map(normalizeLegacySmartNode).filter(Boolean),
            canvas.connections
        );
        // Phase 4：载入即剔除墓碑节点（防御后端历史数据 / 多端竞态残留）
        const loadDead = nodeStore.deletedIds(canvas);
        const liveNodes = loadDead.size ? cleanedCanvas.nodes.filter(n => !loadDead.has(n.id)) : cleanedCanvas.nodes;
        nodes = reconcileExistingAgentGroups(liveNodes);
        const migratedLegacyGroups = nodes.length !== liveNodes.length || nodes.mcpGroupChanged;
        nodes.forEach(n => {
            const pendingTasks = smartPendingTasks(n);
            if(pendingTasks.length){
                n.pending = Math.max(pendingTasks.length, Number(n.pending || 0) || pendingTasks.length);
                n.running = false;
            } else if(n.pending){
                n.pending = 0;
            }
        });
        canvas.connections = cleanedCanvas.connections;
        // 2026-10-19 老王：载入即把历史“组线”展开成组内每张图各自的线
        const migratedGroupLines = migrateGroupConnectionsToMemberLines();
        pruneCanvasObjectReferences();
        Object.assign(viewport, canvas.viewport || {});
        viewport.scale = safeScale(viewport.scale);
        if(canvas.settings) settings = {...settings, ...canvas.settings};
        canvasDefaultSmartSettings = cloneSmartSettings(settings);
        loadRecentSmartSettings();
        if(settings.comfy_workflow && !settings.comfyWorkflow) settings.comfyWorkflow = settings.comfy_workflow;
        settings.comfyWorkflow = resolveComfyWorkflowName(settings.comfyWorkflow);
        if(settings.comfy_params && !settings.comfyParams) settings.comfyParams = settings.comfy_params;
        updateProviderModels();
        applyViewport();
        render();
        if(migratedLegacyGroups || migratedGroupLines) scheduleSave();
        try {
            const focusNodeId = params.get('focus_node') || '';
            if(focusNodeId){
                params.delete('focus_node');
                const cleanUrl = location.pathname + (params.toString() ? '?' + params.toString() : '');
                history.replaceState(null, '', cleanUrl);
                setTimeout(() => tcLocateNode(focusNodeId), 350);
            }
        } catch(e){}
        resumeSmartPendingTasks();
        recoverCompletedEmptySmartNodes();
        resumeJimengPendingNodes();
        recoverStuckComfyNodes();
        if(globalThis.CanvasComfyJobEngine && typeof CanvasComfyJobEngine.pruneStaleComfyErrorsOnLoad === 'function') CanvasComfyJobEngine.pruneStaleComfyErrorsOnLoad();
        startComfyJobSupervisor();
        startCanvasMetaPoll();
    } catch(e) { toast(tr('smart.toastCanvasFail')); }
}
// ===== ③ 本地草稿层：改动先落本地（防抖），同步成功后清掉 =====
let canvasDraftSuppressed = false;   // 从草稿恢复时先别把它又写一遍
const canvasDraftWriter = window.CanvasDraftStore.createWriter({
    getCanvasId:() => canvasId,
    getPayload:() => buildCanvasStoragePayload(),
    isSuppressed:() => canvasDraftSuppressed
});
function canvasDraftStore(){
    return (typeof window !== 'undefined' && window.CanvasDraftStore) ? window.CanvasDraftStore : null;
}
function clearCanvasDraft(){
    const store = canvasDraftStore();
    if(!store || !canvasId) return;
    try { store.clear(canvasId); } catch(e) {}
}
async function restoreCanvasDraftIfNewer(serverCanvas){
    const store = canvasDraftStore();
    if(!store || !canvasId || !serverCanvas) return false;
    let draft = null;
    try { draft = await store.read(canvasId); } catch(e) { return false; }
    if(!draft || !Array.isArray(draft.nodes)) return false;
    const serverUpdatedAt = Number(serverCanvas.updated_at || 0);
    const base = Number(draft.baseUpdatedAt || 0);
    const savedAt = Number(draft.savedAt || 0);
    // 只在"草稿基于当前服务端版本、且比服务端那次写入更晚"时恢复，避免把老草稿当成新改动
    const newer = savedAt > serverUpdatedAt && base >= serverUpdatedAt;
    if(!newer) return false;
    // 内容与服务端一致就不用恢复（避免"同步完成后又被自己恢复一次"的噪音）
    const signature = (ns, cs) => (ns || []).map(n => String(n?.id || '')).join('|') + '#' + ((cs || []).length);
    if(signature(draft.nodes, draft.connections) === signature(serverCanvas.nodes, serverCanvas.connections)) return false;
    canvasDraftSuppressed = true;
    try {
        nodes = (draft.nodes || []).map(normalizeLegacySmartNode).filter(Boolean);
        canvas.nodes = nodes;
        canvas.connections = Array.isArray(draft.connections) ? draft.connections : (canvas.connections || []);
        if(Array.isArray(draft.artifacts)) canvasAgentArtifactsState = draft.artifacts.slice();
        if(draft.inputMode === 'objects' || draft.inputMode === 'connections') canvas.inputMode = draft.inputMode;
        if(draft.viewport) Object.assign(viewport, draft.viewport);
        render();
        applyViewport();
        toast(tr('smart.draftRestored'));
    } finally {
        canvasDraftSuppressed = false;
    }
    scheduleSave();   // 立刻同步回后端，让服务端跟上
    return true;
}
function scheduleSave(){
    clearTimeout(saveTimer);
    canvasSaveRecovery.reset();
    saveTimer = setTimeout(saveCanvas, 450);
    canvasDraftWriter.schedule();
}
// ③ 把"要发出去的画布内容"收成一个函数：保存和本地草稿共用同一份 payload，
// 保证草稿内容永远不会比同步出去的内容旧（否则恢复草稿会丢节点）。
function buildCanvasStoragePayload(){
    savePromptDraftForCurrent();
    nodes.forEach(node => {
        node.images = (node.images || []).map(img => mediaItemForStorage(stripImageGenerationMeta(img)));
        if(node.runSettings) node.runSettings = settingsForStorage(node.runSettings);
        if(node.flowLayout?.layout === 'tree_lr'){
            const rect = nodeRect(node);
            node.flowLayout.measuredSize = {width:rect.width, height:rect.height};
        }
    });
    canvas.nodes = nodes.filter(n => !n.__preview);
    canvas.settings = settingsForStorage(canvasDefaultSmartSettings || initialSmartSettings);
    canvas.viewport = {...viewport};
    const storageCanvas = canvasForStorage();
    return {
        title: storageCanvas.title || tr('smart.title'),
        icon: storageCanvas.icon || 'sparkles',
        nodes: storageCanvas.nodes || [],
        connections: storageCanvas.connections || [],
        viewport: storageCanvas.viewport || {x:0,y:0,scale:1},
        logs: storageCanvas.logs || [],
        settings: storageCanvas.settings,
        deleted: Array.isArray(storageCanvas.deleted) ? storageCanvas.deleted : [],
        artifacts: Array.isArray(canvasAgentArtifactsState) ? canvasAgentArtifactsState : [],
        inputMode: canvasInputMode(),
        base_updated_at: storageCanvas.updated_at || canvas.updated_at || 0,
        client_id: smartClientId
    };
}
async function saveCanvas(){
    if(!canvasId || !canvas) return false;
    if(canvasSyncInFlight){
        clearTimeout(saveTimer);
        saveTimer = setTimeout(saveCanvas, 250);
        return false;
    }
    const payload = buildCanvasStoragePayload();
    // 先同步写入本地兜底草稿，再请求服务器；请求失败或页面随后关闭时仍可恢复。
    try { canvasDraftStore()?.save(canvasId, CanvasDraftStore.toDraft(payload)); } catch(e) {}
    canvasSyncInFlight = true;
    let saved = false;
    try {
        const res = await fetch(`/api/canvases/${encodeURIComponent(canvasId)}`, {
            method:'PUT',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify(payload)
        });
        if(res.ok){
            const data = await res.json();
            if(data?.ok === false) throw new Error(data.detail || '服务器没有接受画布保存');
            if(data.canvas && data.canvas.updated_at) canvas.updated_at = data.canvas.updated_at;
            // The server may reflow opt-in workflows after actual card measurements.
            // Only acknowledge positions whose local coordinates are still unchanged.
            if(data.canvas?.nodes?.some(node => node.flowLayout?.layout === 'tree_lr') && !dragState && !resizeState){
                const sent = new Map(payload.nodes.map(node => [node.id,node]));
                const acknowledged = new Map(data.canvas.nodes.map(node => [node.id,node]));
                let moved = false;
                nodes.forEach(node => {
                    const old = sent.get(node.id), next = acknowledged.get(node.id);
                    if(old && next && node.x === old.x && node.y === old.y && (node.x !== next.x || node.y !== next.y)){
                        node.x = next.x;node.y = next.y;moved = true;
                    }
                });
                if(moved) render();
            }
            // Remember exactly what was acknowledged, not edits made while PUT was in flight.
            CanvasMergeSync.rememberServerCanvas({...data.canvas, nodes:(data.canvas?.nodes || payload.nodes).map(normalizeLegacySmartNode).filter(Boolean)});
            // 同步成功：草稿已经变成服务端内容，清掉（并取消排队中的写入，避免又被写回一份）
            canvasDraftWriter.cancel();
            clearCanvasDraft();
            canvasSaveRecovery.reset();
            saved = true;
        } else if(res.status === 409) {
            // Rebase only local changes against the acknowledged server baseline.
            const data = await res.json().catch(() => ({}));
            const serverCanvas = data.canvas || data.detail?.canvas;
            if(serverCanvas){
                applyMergedServerCanvas(serverCanvas);
                nodes.forEach(node => {
                    node.images = (node.images || []).map(img => mediaItemForStorage(stripImageGenerationMeta(img)));
                    if(node.runSettings) node.runSettings = settingsForStorage(node.runSettings);
                });
                canvas.nodes = nodes;
            } else if(data.detail?.updated_at) {
                canvas.updated_at = data.detail.updated_at;
            } else {
                throw new Error(tr('smart.canvasSaveConflictUnknown'));
            }
            clearTimeout(saveTimer);
            saveTimer = setTimeout(saveCanvas, 300);
        } else {
            const data = await res.json().catch(() => ({}));
            throw new Error(data.detail || data.error || `${res.status} ${res.statusText}`);
        }
    } catch(e) {
        const reason = String(e?.message || e || '').replace(/\\s+/g, ' ').trim().slice(0, 120);
        canvasSaveRecovery.fail({
            retry:saveCanvas,
            onFirstFailure:() => toast(trf('smart.canvasSaveFailed', {reason:reason || 'Unknown error'})),
            onExhausted:() => toast(tr('smart.canvasSaveRetryExhausted'))
        });
        saved = false;
    } finally {
        canvasSyncInFlight = false;
    }
    return saved;
}
window.addEventListener('online', () => {
    if(!canvasId || !canvas || !canvasSaveRecovery.prepareOnlineRetry()) return;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveCanvas, 250);
});
function imageMetaFromNode(node){
    return {};
}
function applyNodeMetaToImage(image, node){
    return stripImageGenerationMeta(image);
}
function inheritNodeMetaFromImage(node){
    if(!node) return;
    node.images = (node.images || []).map(img => stripImageGenerationMeta(img));
}
CanvasSpeech.configure({
    getNodes:() => nodes, getConnections:() => canvas?.connections || [], getProviders:() => apiProviders,
    getCanvasId:() => canvasId, getCanvasTitle:() => canvas?.title || '',
    escapeHtml, audioPlayerHtml, render, scheduleSave, toast, addSmartGenerationLog, createSpeechOutputNode,

});
function createSpeechOutputNode(source, items, taskId){
    const media = items.map(item => ({...item,kind:'audio',generatedResult:true}));
    const layout = imageLayout(media, MEDIA_NODE_DEFAULT_SCALE, {type:'smart-image',images:media});
    const rect = nodeRect(source);
    const point = agentFindEmptySpot(rect.x + rect.width + 60, rect.y, layout.width, layout.height);
    const output = createNode(point.x,point.y,media,{select:false});
    output.title = '音频';
    output.speechSourceId = source.id;
    output.speechTaskId = taskId;
    addConnection(source.id,output.id,'input');
    render();
    scheduleSave();
    return output;
}
function createSpeechNode(point){
    pushUndo();
    const node = {id:uid('speech'), type:'smart-speech', x:point.x-500, y:point.y-270, w:1000, h:540, speechLayout:3,
        title:'语音生成', images:[], speechProvider:CanvasSpeech.providers()[0]?.id || '', speechModel:'mimo-v2.5-tts-voicedesign',
        speechStyle:'', speechText:'', speechVoice:'mimo_default', created_at:Date.now(), status:'ready', role:'media', __origin:'user_manual'};
    nodeStore.addNode(node, 'user_manual');
    canvasUiState.patchSelection({primaryId: node.id}, 'selectedId');
    render();
    scheduleSave();
    return node;
}
function createNode(x, y, images=[], options={}){
    if(!options.skipUndo) pushUndo();
    const nodeImages = (images || []).map(img => ({...img}));
    const firstKind = nodeImages[0] ? mediaKindForItem(nodeImages[0]) : 'image';
    const singleTitle = firstKind === 'video' ? 'Video' : firstKind === 'audio' ? 'Audio' : firstKind === 'text' ? 'Text' : firstKind === 'file' ? 'File' : 'Image';
    // 单素材节点默认用素材文件名当标题（2026-10-09），拖一张"主角设定.png"进来标题就叫"主角设定"
    const nameTitle = nodeImages.length === 1 ? CanvasGeneratedOutputNaming.mediaNameStem(nodeImages[0]?.name) : '';
    const node = {id:uid('smart'), type:'smart-image', x, y, title:nodeImages.length > 1 ? 'Group' : (nameTitle || (nodeImages.length ? singleTitle : tr('smart.createImportNode'))), images:nodeImages, created_at:Date.now(), __origin:'user_manual', status:'ready', role:'media'};
    node.scale = nodeImages.length > 1 ? MEDIA_GROUP_DEFAULT_SCALE : mediaNodeDefaultScale(node);
    inheritNodeMetaFromImage(node);
    node.runSettings = settingsForStorage({...smartSettingsForNode(node), promptH:93});
    if(!nodeImages.length){ node.runSettings.ratio = 'wide'; node.runSettings.videoAspect = '16:9'; }
    // 空节点也走统一的按比例默认盒（宽幅 16:9 → 512×288），与 Agent/MCP 建的生成节点同尺寸。
    if(!nodeImages.length){
        const box = nodeRatioBox(node);
        node.cardSize = {width:box.w, height:box.h};
        node.cardSizing = 'default';
    }
    nodeStore.addNode(node, 'user_manual');
    if(options.select !== false) canvasUiState.patchSelection({primaryId: node.id}, 'selectedId');
    render();
    scheduleSave();
    return node;
}

function createPromptNode(x, y, options={}){
if(!options.skipUndo) pushUndo();
const providerId = resolveChatProviderId();
const node = {
id:uid('prompt'),
type:'smart-prompt',
x,
y,
w:632,
h:388,
title:options.title || 'Prompt',
kind:options.kind || 'prompt',
text:String(options.text || ''),
llmEnabled:Boolean(options.llmEnabled),
        llmProvider:providerId,
        llmModel:resolveChatModel('', providerId),
        llmSystemEnabled:false,
        llmSystemPrompt:'You are a helpful prompt assistant.',
        llmInstruction:'',
        created_at:Date.now(),
        status:'ready',
        role:'text',
        __origin:'user_manual'
    };
    nodeStore.addNode(node, 'user_manual');
    if(options.select !== false) canvasUiState.patchSelection({primaryId: node.id}, 'selectedId');
    render();
    scheduleSave();
return node;
}
function createTextNode(x, y, options={}){
return createPromptNode(x, y, {...options});
}
function createLoopNode(x, y, options={}){
    if(!options.skipUndo) pushUndo();
    const node = {id:uid('loop'), type:'smart-loop', x, y, w:340, h:168, title:'Loop', count:1, mode:'serial', showPrompt:false, imageInput:false, loopStart:1, imageBatchSize:1, variablePrompt:'', created_at:Date.now(), status:'ready', role:'text', __origin:'user_manual'};
    nodeStore.addNode(node, 'user_manual');
    if(options.select !== false) canvasUiState.patchSelection({primaryId: node.id}, 'selectedId');
    render();
    scheduleSave();
    return node;
}
function createSmartGeneratorNode(point, config={}){
    const node = createImageNodeAt(point, [], {select:config.select !== false, skipUndo:Boolean(config.skipUndo)});
    node.title = config.title || '生成节点';
    node.runSettings = settingsForStorage({
        ...cloneSmartSettings(settings),
        promptH:93,
        engine:config.engine || 'api',
        apiKind:config.apiKind || 'image',
        ratio:'wide',
        videoAspect:'16:9',
 comfyMode:config.comfyMode || settings.comfyMode || 'custom'
    });
    // 3D预演 节点：强制 blender 平台（独立节点，不经引擎下拉）
    if(config.engine === 'blender'){
        node.runSettings.engine = 'blender';
        node.runSettings.provider_id = 'blender';
        node.runSettings.model = 'blender-previz';
        node.runSettings.previzOutput = 'motion';
        node.runSettings.count = 1;
    }
    if(config.engine === 'runninghub'){
        node.runSettings.rhPayment = node.runSettings.rhPayment || 'free';
    }
    render();
    scheduleSave();
    return node;
}
function cloneSmartNode(node, dx=0, dy=0){ return CanvasNodeClipboardController.cloneNode(node, dx, dy); }
function duplicateSmartNodeConnections(sourceId, copyId){ return CanvasNodeClipboardController.duplicateConnections(sourceId, copyId); }
function duplicateSmartNodeWithConnections(nodeOrId, dx=48, dy=36){
    return CanvasNodeClipboardController.duplicateNodeWithConnections(nodeOrId, dx, dy);
}
function copySelectedNodes(){ return CanvasNodeClipboardController.copySelectedNodes(); }
function pasteNodes(){ return CanvasNodeClipboardController.pasteNodes(); }
function duplicateForAltDrag(node){ return CanvasNodeClipboardController.duplicateForAltDrag(node); }
function shellPoint(event){
    const rect = shell.getBoundingClientRect();
    return {x:event.clientX - rect.left, y:event.clientY - rect.top};
}
function renderConnections(){
    connCutGeom.clear();
    // 无线模式：不渲染任何连线（保留 svg 容器，切回连线模式即恢复）
    if(canvasObjectsMode()) return '<svg class="connection-layer" width="6000" height="4000" viewBox="0 0 6000 4000" xmlns="http://www.w3.org/2000/svg"></svg>';
    const nodeMap = new Map(nodes.map(node => [node.id, node]));
    const conns = (canvas?.connections || []).map((conn, index) => ({...conn, index})).filter(c => nodeMap.has(c.from) && nodeMap.has(c.to));
    const cascadeKeys = cascadeConnectionKeys();
    const selectedLinkIds = new Set(selectedNodeIds());
    const paths = conns.map(conn => {
        const isLinkedToSelection = selectedLinkIds.has(conn.from) || selectedLinkIds.has(conn.to);
        const fromNode = nodeMap.get(conn.from);
        const toNode = nodeMap.get(conn.to);
        const fr = nodeRect(fromNode), tr = nodeRect(toNode);
        const kind = conn.kind || 'flow';
        const isHistory = kind === 'history';
        const isInsertPreview = loopInsertPreview?.index === conn.index;
        const edgeKey = `${conn.from}->${conn.to}`;
        const cascadeState = smartCascadeEdgeState(edgeKey);
        const isCascade = !isHistory && (cascadeKeys.has(edgeKey) || Boolean(cascadeState) || isInsertPreview);
        const isPendingLine = Boolean(toNode.pending && !isCascade);
        const fx = isHistory ? fr.x + fr.width / 2 : fr.x + fr.width;
        const fy = isHistory ? fr.y + fr.height : fr.y + fr.height / 2;
        const tx = isHistory ? tr.x + tr.width / 2 : tr.x;
        const ty = isHistory ? tr.y : tr.y + tr.height / 2;
        const dx = Math.max(50, Math.abs(tx - fx) * 0.45);
        const dy = Math.max(36, Math.abs(ty - fy) * 0.45);
        const curve = isHistory
            ? `M${fx} ${fy} C ${fx} ${fy+dy}, ${tx} ${ty-dy}, ${tx} ${ty}`
            : `M${fx} ${fy} C ${fx+dx} ${fy}, ${tx-dx} ${ty}, ${tx} ${ty}`;
        const cls = [
            isPendingLine ? 'conn-pending conn-comet-track' : '',
            isCascade ? 'conn-cascade' : '',
            isCascade && cascadeState === 'done' ? 'conn-cascade-done' : '',
            isCascade && Boolean(cascadeState) && cascadeState !== 'done' ? 'conn-cascade-wait' : '',
            isCascade && cascadeState === 'active' ? 'conn-cascade-active' : '',
            isHistory ? 'conn-history' : '',
            isLinkedToSelection ? 'conn-linked' : ''
        ].filter(Boolean).join(' ');
        const color = isLinkedToSelection ? '#C9A227' : isCascade ? '#16a34a' : isHistory ? 'rgba(138,138,138,0.46)' : kind === 'input' ? 'rgba(138,138,138,0.62)' : 'rgba(200,200,200,0.62)';
        const opacity = isPendingLine ? '.82' : '1';
        const width = isLinkedToSelection ? '2.4' : kind === 'input' ? '1.9' : '1.6';
        // 运行中连线：底线常亮 + 两颗彗星光点沿管道滑行（A 方案），不再用滚动虚线
        const cometLayer = isPendingLine ? `<path class="conn-comet" d="${curve}" pathLength="180" stroke="#dbeafe" stroke-dasharray="22 158" fill="none"></path><path class="conn-comet conn-comet-2" d="${curve}" pathLength="180" stroke="#93c5fd" stroke-width="2" stroke-dasharray="10 170" fill="none"></path>` : '';
        // 划断手势要用：存三次贝塞尔的四个控制点（p0,c1,c2,p1）。只存 8 个数，
        // 折线采样留给真正划的时候懒算——render 每帧都跑，别在这里做采样。
        connCutGeom.set(conn.index, {c: isHistory
            ? [fx, fy, fx, fy + dy, tx, ty - dy, tx, ty]
            : [fx, fy, fx + dx, fy, tx - dx, ty, tx, ty], pts: null, box: null});
        // data-conn-line：划断手势拿到命中后要把这根线即时标成金色（Blender 刀切线同理）
        return `<path class="${cls}" data-conn-line="${conn.index}" d="${curve}" stroke="${color}" stroke-width="${width}" fill="none" opacity="${opacity}"></path>${cometLayer}<path class="conn-hit" data-conn-index="${conn.index}" d="${curve}" stroke="transparent" stroke-width="14" fill="none"></path>`;
    }).join('');
    return `<svg class="connection-layer" width="6000" height="4000" viewBox="0 0 6000 4000" xmlns="http://www.w3.org/2000/svg"><defs><filter id="conn-comet-glow" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="2.4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>${paths}<g class="conn-scissor conn-knife-host" data-conn-index="-1" transform="translate(-100 -100)"><circle r="20" fill="transparent" pointer-events="all"></circle><circle r="13" fill="var(--card,#1f1f1f)" stroke="#C9A227" stroke-width="1.4"></circle><!-- 2026-10-17 老王：剪刀换刀（参考 Blender 节点 Ctrl+右键切线）。45° 裁刀：刀尖左下、刀柄右上，与剪刀同一套金描边+卡片填充观感 --><g class="conn-knife" transform="translate(-9.6 -9.6) scale(0.78)" fill="var(--card,#1f1f1f)" stroke="#C9A227" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20 12.3 14.3 9.7 11.7z"></path><path d="M11 13 17.4 6.6" fill="none" stroke-width="3.4"></path></g></g></svg>`;
}
function refreshConnectionLayer(){
    const oldSvg = world.querySelector('svg.connection-layer');
    if(!oldSvg) return;
    const tpl = document.createElement('template');
    tpl.innerHTML = renderConnections().trim();
    const nextSvg = tpl.content.firstElementChild;
    if(nextSvg) oldSvg.replaceWith(nextSvg);
    bindConnectionEvents();
    updateComfyInputsRow();
}
// 连线变化后原位刷新"素材输入"计数行（不重渲整个 composer，避免丢输入焦点/关弹层）。
// 媒体kind/helper带外移 canvas-media-helpers.js（第十六刀）。块内零整写，值型走 getter。
if(globalThis.CanvasMediaHelpers){CanvasMediaHelpers.configure({
        canvasThumbnailUrl: (...a) => canvasThumbnailUrl(...a),
        displayMediaUrl: (...a) => displayMediaUrl(...a),
        escapeHtml: (...a) => escapeHtml(...a),
        imageLayout: (...a) => imageLayout(...a),
        nodeScale: (...a) => nodeScale(...a),
        positionComposerForNode: (...a) => positionComposerForNode(...a),
        render: (...a) => render(...a),
        renderComfyInputsRow: (...a) => renderComfyInputsRow(...a),
        scheduleConnectionLayerRefresh: (...a) => scheduleConnectionLayerRefresh(...a),
        scheduleMinimapRender: (...a) => scheduleMinimapRender(...a),
        scheduleSave: (...a) => scheduleSave(...a),
        selectedNode: (...a) => selectedNode(...a),
        dynamicParams: () => dynamicParams,
        escapeAttr: () => escapeAttr,
        smartTextContentCache: () => smartTextContentCache,
        world: () => world
});}
function updateComfyInputsRow(){return CanvasMediaHelpers.updateComfyInputsRow.apply(null, arguments);}
function updateNodeElementDuringResize(){return CanvasMediaHelpers.updateNodeElementDuringResize.apply(null, arguments);}
function isVideoMediaItem(){return CanvasMediaHelpers.isVideoMediaItem.apply(null, arguments);}
function isAudioMediaItem(){return CanvasMediaHelpers.isAudioMediaItem.apply(null, arguments);}
function isTextMediaItem(){return CanvasMediaHelpers.isTextMediaItem.apply(null, arguments);}
function isFileMediaItem(){return CanvasMediaHelpers.isFileMediaItem.apply(null, arguments);}
function mediaKindForFile(){return CanvasMediaHelpers.mediaKindForFile.apply(null, arguments);}
function mediaKindForItem(){return CanvasMediaHelpers.mediaKindForItem.apply(null, arguments);}
function textContentValue(){return CanvasMediaHelpers.textContentValue.apply(null, arguments);}
function textPreviewSnippet(){return CanvasMediaHelpers.textPreviewSnippet.apply(null, arguments);}
function ensureNodeTextMedia(){return CanvasMediaHelpers.ensureNodeTextMedia.apply(null, arguments);}
function nodeTextOutput(){return CanvasMediaHelpers.nodeTextOutput.apply(null, arguments);}
function localDisplayUrlForMediaItem(){return CanvasMediaHelpers.localDisplayUrlForMediaItem.apply(null, arguments);}
function imageForDisplay(){return CanvasMediaHelpers.imageForDisplay.apply(null, arguments);}
function resultMediaUrls(){return CanvasMediaHelpers.resultMediaUrls.apply(null, arguments);}
function taskIdsFromResult(){return CanvasMediaHelpers.taskIdsFromResult.apply(null, arguments);}
function mediaKindForUrls(){return CanvasMediaHelpers.mediaKindForUrls.apply(null, arguments);}
function imageRefsOnly(){return CanvasMediaHelpers.imageRefsOnly.apply(null, arguments);}
function videoRefsOnly(){return CanvasMediaHelpers.videoRefsOnly.apply(null, arguments);}
function isRemoteVideoReferenceUrl(){return CanvasMediaHelpers.isRemoteVideoReferenceUrl.apply(null, arguments);}
function audioRefsOnly(){return CanvasMediaHelpers.audioRefsOnly.apply(null, arguments);}
function audioThumbLabel(){return CanvasMediaHelpers.audioThumbLabel.apply(null, arguments);}
function audioThumbHtml(){return CanvasMediaHelpers.audioThumbHtml.apply(null, arguments);}
function audioPlayerHtml(){return CanvasMediaHelpers.audioPlayerHtml.apply(null, arguments);}
function bindSmartAudioPlayers(){return CanvasMediaHelpers.bindSmartAudioPlayers.apply(null, arguments);}
function thumbMediaHtml(){return CanvasMediaHelpers.thumbMediaHtml.apply(null, arguments);}
const imageResolutionMetaCache = new Map();
let imageResolutionRerenderQueued = false;
function positiveImageDimension(value){
    const n = Number(value || 0);
    return Number.isFinite(n) && n > 0 ? n : 0;
}
function imageDimensionPairFrom(obj, pairs){
    if(!obj || typeof obj !== 'object') return null;
    for(const [wk, hk] of pairs){
        const w = positiveImageDimension(obj[wk]);
        const h = positiveImageDimension(obj[hk]);
        if(w > 0 && h > 0) return {w, h};
    }
    return null;
}
function localAssetUrlForImageInfo(img){
    const candidates = [
        img?.url,
        img?.originalLocalUrl,
        img?.localUrl,
        img?.sourceUrl,
        img?.local_url,
        img?.source_url
    ];
    for(const value of candidates){
        const url = String(value || '').trim();
        if(!url) continue;
        if(url.startsWith('/assets/')) return url;
        try {
            const parsed = new URL(url, location.origin);
            if(parsed.origin === location.origin && parsed.pathname.startsWith('/assets/')) return `${parsed.pathname}${parsed.search || ''}`;
        } catch(_) {}
    }
    return '';
}
function knownImageNaturalSize(img, allowDisplayFallback=false){
    const intrinsicPairs = [
        ['natural_w','natural_h'],
        ['naturalWidth','naturalHeight'],
        ['original_w','original_h'],
        ['originalWidth','originalHeight'],
        ['original_width','original_height'],
        ['source_w','source_h'],
        ['sourceWidth','sourceHeight'],
        ['source_width','source_height'],
        ['intrinsic_w','intrinsic_h'],
        ['intrinsicWidth','intrinsicHeight'],
        ['meta_width','meta_height']
    ];
    const direct = imageDimensionPairFrom(img, intrinsicPairs);
    if(direct) return direct;
    for(const key of ['metadata','meta','info','imageInfo']){
        const nested = imageDimensionPairFrom(img?.[key], [...intrinsicPairs, ['width','height'], ['w','h']]);
        if(nested) return nested;
    }
    return allowDisplayFallback ? imageDimensionPairFrom(img, [['width','height'], ['w','h']]) : null;
}
function mediaItemUrlMatches(item, url){
    if(!item || !url) return false;
    return localAssetUrlForImageInfo(item) === url;
}
function imageResolutionCacheKey(img){
    return JSON.stringify([localAssetUrlForImageInfo(img), img?.generationTaskId || '', img?.source_url || img?.sourceUrl || '']);
}
function reconcileSingleImageAspect(owner, item, width, height, intrinsicGroupMember=false){
    if(!owner || (owner.images || []).length !== 1 || owner.images[0] !== item || owner.groupLayout?.mode === 'preserve') return false;
    if(owner.cardSizing === 'manual' || owner.generationFrameLocked) return false;
    const displayW = Number(owner.w), displayH = Number(owner.h);
    if(!(displayW > 24 && displayH > 24)) return false;
    const ratio = width / height;
    const autoGroup = intrinsicGroupMember || Boolean(owner.mcpGroupId || owner.mcpGroupSourceId);
    if(!autoGroup && Math.abs(displayW / displayH - ratio) / ratio < 0.01) return false;
    const longSide = Math.max(displayW, displayH, autoGroup ? Number(owner.cardSize?.width) || 0 : 0, autoGroup ? Number(owner.cardSize?.height) || 0 : 0);
    const w = Math.round(ratio >= 1 ? longSide : longSide * ratio);
    const h = Math.round(ratio >= 1 ? longSide / ratio : longSide);
    if(autoGroup && owner.w === w && owner.h === h && owner.cardSize?.width === w && owner.cardSize?.height === h && owner.cardSizing === 'intrinsic') return false;
    owner.w = w;owner.h = h;
    if(autoGroup){
        owner.cardSize = {width:w, height:h};
        owner.cardSizing = 'intrinsic';
    }
    return true;
}
function queueImageResolutionRerender(){
    if(imageResolutionRerenderQueued) return;
    imageResolutionRerenderQueued = true;
    requestAnimationFrame(() => {
        imageResolutionRerenderQueued = false;
        render();
        scheduleSave();
    });
}
function applyImageResolutionMetadata(url, width, height, target=null, cacheKey=''){
    const w = Math.round(positiveImageDimension(width));
    const h = Math.round(positiveImageDimension(height));
    if(!(w > 0 && h > 0)) return;
    let changed = false;
    const apply = (item, owner=null) => {
        if(!item || typeof item !== 'object') return;
        if(cacheKey && imageResolutionCacheKey(item) !== cacheKey) return;
        const current = knownImageNaturalSize(item, false);
        if(current?.w !== w || current?.h !== h){
            item.natural_w = w;
            item.natural_h = h;
            changed = true;
        }
        if(owner && fitAutoGroupMemberToSlot(owner, item)) changed = true;
        if(reconcileSingleImageAspect(owner, item, w, h)) changed = true;
    };
    const targetOwner = target ? nodes.find(node => (node.images || []).includes(target)) : null;
    apply(target, targetOwner);
    nodes.forEach(node => (node.images || []).forEach(item => {
        if(mediaItemUrlMatches(item, url)) apply(item, node);
    }));
    if(changed) queueImageResolutionRerender();
}
function ensureImageResolutionMetadata(img, force=false){
    if(!img || mediaKindForItem(img) !== 'image') return;
    if(!force && knownImageNaturalSize(img, false)) return;
    const url = localAssetUrlForImageInfo(img);
    if(!url) return;
    const cacheKey = imageResolutionCacheKey(img);
    const cached = imageResolutionMetaCache.get(cacheKey);
    if(cached === 'pending' || cached === 'failed') return;
    if(cached){
        applyImageResolutionMetadata(url, cached.w, cached.h, img, cacheKey);
        return;
    }
    imageResolutionMetaCache.set(cacheKey, 'pending');
    fetch(`/api/canvas-image-info?url=${encodeURIComponent(url)}`)
        .then(response => response.ok ? response.json() : Promise.reject(new Error('image info failed')))
        .then(data => {
            const w = positiveImageDimension(data?.width);
            const h = positiveImageDimension(data?.height);
            if(!(w > 0 && h > 0)) throw new Error('missing image size');
            const size = {w:Math.round(w), h:Math.round(h)};
            imageResolutionMetaCache.set(cacheKey, size);
            applyImageResolutionMetadata(url, size.w, size.h, img, cacheKey);
        })
        .catch(() => imageResolutionMetaCache.set(cacheKey, 'failed'));
}
function imageResolutionLabel(img){
    const localAssetUrl = localAssetUrlForImageInfo(img);
    const size = knownImageNaturalSize(img, !localAssetUrl);
    if(localAssetUrl) ensureImageResolutionMetadata(img, true);
    return size?.w > 0 && size?.h > 0 ? `${Math.round(size.w)} x ${Math.round(size.h)}` : '';
}
function imageResolutionBadgeHtml(img){
    const label = imageResolutionLabel(img);
    return label ? `<span class="image-resolution-badge">${escapeHtml(label)}</span>` : '';
}
function smartImageDisplayName(img){
    const raw = String(img?.name || fileNameFromUrl(img?.url || '') || 'image').trim();
    return raw || 'image';
}
function smartImageTargetFileName(value, image){
    const fallback = smartImageDisplayName(image);
    let name = safeExportFileName(String(value || '').trim() || fallback, fallback || 'image.png');
    const source = smartImageDisplayName(image);
    const sourceExt = (source.match(/(\.[a-z0-9]{2,8})$/i) || fileNameFromUrl(image?.url || '').match(/(\.[a-z0-9]{2,8})$/i) || [,'.png'])[1];
    if(sourceExt && !/\.[a-z0-9]{2,8}$/i.test(name)) name += sourceExt;
    return name;
}
function smartImageNameLabelHtml(img, index){
    if(mediaKindForItem(img) !== 'image') return '';
    const name = smartImageDisplayName(img);
    return `<span class="smart-image-name-label" data-image-name-index="${index}" title="双击重命名">${escapeHtml(name)}</span>`;
}
async function uploadRenamedSmartImageCopy(image, targetName){
    if(!image?.url) return null;
    const url = /^https?:\/\//i.test(String(image.url || '')) ? proxiedMediaUrl(image, image.name || targetName) : image.url;
    const res = await fetch(url);
    if(!res.ok) throw new Error('读取原图片失败');
    const blob = await res.blob();
    if(!blob) throw new Error('读取原图片失败');
    const file = await uploadCroppedBlob(blob, targetName);
    if(!file?.url) throw new Error('未返回重命名图片地址');
    return {...image, ...file, name:file.name || targetName, kind:file.kind || mediaKindForItem(image) || 'image'};
}
async function renameSmartImageFile(image, targetName){
    const payload = {url:image?.url || '', name:targetName};
    try {
        const res = await fetch('/api/canvas-assets/rename', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify(payload)
        });
        if(res.ok){
            const data = await res.json().catch(() => ({}));
            if(data?.url || data?.name) return {...image, ...data, url:data.url || image.url, name:data.name || targetName, kind:data.kind || mediaKindForItem(image) || 'image'};
        }
    } catch(_) {}
    try {
        return await uploadRenamedSmartImageCopy(image, targetName);
    } catch(err) {
        toast(err.message ? `文件名同步失败：${err.message}` : '文件名同步失败，已仅更新画布名称');
        return {...image, name:targetName};
    }
}
async function beginSmartImageRename(nodeId, imageIndex, labelEl){
    const node = nodes.find(n => n.id === nodeId);
    const image = node?.images?.[imageIndex];
    if(!node || !image || labelEl?.classList?.contains('editing')) return;
    const previous = smartImageDisplayName(image);
    const input = document.createElement('input');
    input.className = 'smart-image-name-input';
    input.value = previous;
    input.setAttribute('aria-label', '重命名图片');
    labelEl.replaceWith(input);
    input.focus();
    input.select();
    let done = false;
    const restore = () => { if(input.isConnected) input.replaceWith(labelEl); };
    const commit = async save => {
        if(done) return;
        done = true;
        const raw = input.value.trim();
        if(!save || !raw || raw === previous){ restore(); return; }
        const targetName = smartImageTargetFileName(raw, image);
        pushUndo();
        const oldUrl = image.url || '';
        const updated = await renameSmartImageFile(image, targetName);
        nodes.forEach(n => (n.images || []).forEach(img => {
            if(img && img.url === oldUrl) Object.assign(img, updated, {name:updated.name || targetName});
        }));
        canvasUiState.patchSelection({primaryId: nodeId}, 'selectedId');
        canvasUiState.patchSelection({image: {nodeId, index:imageIndex}}, 'selectedImage');
        render();
        scheduleSave();
    };
    input.addEventListener('keydown', event => {
        if(event.key === 'Enter'){ event.preventDefault(); commit(true); }
        if(event.key === 'Escape'){ event.preventDefault(); commit(false); }
    });
    input.addEventListener('mousedown', event => event.stopPropagation());
    input.addEventListener('click', event => event.stopPropagation());
    input.addEventListener('dblclick', event => event.stopPropagation());
    input.addEventListener('blur', () => commit(true));
}
function thumbDisplaySize(img, maxSize){
    const limit = Math.max(28, Math.round(Number(maxSize) || 96));
    const w = Number(img?.natural_w || img?.width || img?.w || 0);
    const h = Number(img?.natural_h || img?.height || img?.h || 0);
    if(!(w > 0 && h > 0)) return {width:limit, height:limit};
    const fit = Math.min(limit / w, limit / h);
    return {
        width:Math.max(28, Math.round(w * fit)),
        height:Math.max(28, Math.round(h * fit))
    };
}
function thumbItemStyle(img, maxSize){
    const size = thumbDisplaySize(img, maxSize);
    return `--thumb-w:${size.width}px;--thumb-h:${size.height}px`;
}
function applyThumbDisplaySizeToElement(itemEl, img, maxSize=0){
    if(!itemEl?.classList?.contains('thumb-item')) return;
    const limit = Math.max(
        28,
        Math.round(
            Number(maxSize || 0)
            || Number(itemEl.style.getPropertyValue('--thumb-size').replace('px', ''))
            || Math.max(itemEl.clientWidth || 0, itemEl.clientHeight || 0)
            || 96
        )
    );
    const size = thumbDisplaySize(img, limit);
    itemEl.style.setProperty('--thumb-w', `${size.width}px`);
    itemEl.style.setProperty('--thumb-h', `${size.height}px`);
}
function singleMediaHtml(img, w, h){
    if(isFileMediaItem(img) || isTextMediaItem(img)){
        const preview = isTextMediaItem(img) ? textPreviewSnippet(img.textPreview || textContentValue(img), 220) : '';
        return `<div class="node-img media-card media-file-card" style="width:${w}px;height:${h}px"><div class="media-card-icon"><i data-lucide="${isTextMediaItem(img) ? 'file-text' : 'file'}"></i></div><div class="media-card-title">${escapeHtml(img.name || (isTextMediaItem(img) ? 'Text' : 'File'))}</div><div class="media-card-sub">${isTextMediaItem(img) ? 'TEXT' : 'FILE'}</div>${preview ? `<div class="media-card-text">${escapeHtml(preview)}</div>` : ''}</div>`;
    }
    if(isAudioMediaItem(img)) return audioPlayerHtml(img, w, h);
    if(isVideoMediaItem(img)) return `<div class="node-img media-card media-video-card" style="width:${w}px;height:${h}px"><video src="${escapeHtml(img.url)}" data-url="${escapeHtml(img.url)}" controls muted preload="metadata" playsinline disablepictureinpicture controlslist="nodownload noplaybackrate noremoteplayback"></video></div>`;
    const thumbEdge = Math.max(384, Math.min(1024, Math.ceil(Math.max(w, h) * 1.25)));
    return `<img class="node-img" src="${escapeHtml(canvasThumbnailUrl(img, thumbEdge))}" data-original-src="${escapeAttr(img.url || '')}" data-base-edge="${thumbEdge}" draggable="false" loading="eager" decoding="async" style="width:${w}px;height:${h}px">`;
}
function smartNodeHasLiveMedia(node){
    return Boolean(!node?.pending && (node?.images || []).some(img => isVideoMediaItem(img) || isAudioMediaItem(img)));
}
function mediaSignaturePartFromElement(itemEl){
    if(itemEl?.dataset?.mediaSignature) return itemEl.dataset.mediaSignature;
    const media = itemEl?.querySelector?.('video,audio,img');
    if(media){
        const tag = media.tagName.toLowerCase();
        const kind = tag === 'video' ? 'video' : tag === 'audio' ? 'audio' : 'image';
        const url = media.dataset?.url || media.dataset?.originalSrc || media.getAttribute('src') || '';
        return `${kind}:${url}`;
    }
    const audioThumb = itemEl?.querySelector?.('.audio-thumb[data-media-url]');
    if(audioThumb) return `audio:${audioThumb.dataset.mediaUrl || ''}`;
    return '';
}
function captureMediaPlaybackState(media){
    if(!media) return null;
    return {
        currentTime:Number.isFinite(media.currentTime) ? media.currentTime : 0,
        paused:Boolean(media.paused),
        playbackRate:Number.isFinite(media.playbackRate) ? media.playbackRate : 1,
        muted:Boolean(media.muted),
        volume:Number.isFinite(media.volume) ? media.volume : 1
    };
}
function restoreMediaPlaybackState(media, state){
    if(!media || !state) return;
    try { media.playbackRate = state.playbackRate || 1; } catch(e) {}
    try { media.muted = state.muted; } catch(e) {}
    try { media.volume = state.volume; } catch(e) {}
    const applyTime = () => {
        if(Number.isFinite(state.currentTime) && state.currentTime > 0 && Math.abs((media.currentTime || 0) - state.currentTime) > 0.2){
            try { media.currentTime = state.currentTime; } catch(e) {}
        }
        if(!state.paused && typeof media.play === 'function'){
            const playPromise = media.play();
            if(playPromise?.catch) playPromise.catch(() => {});
        }
    };
    if(media.readyState >= 1) applyTime();
    else media.addEventListener('loadedmetadata', applyTime, {once:true});
}
function transplantSmartMediaElements(oldNodeEl, newNodeEl){
    const oldItems = [...(oldNodeEl?.querySelectorAll?.('.thumb-item,.image-wrap') || [])];
    const newItems = [...(newNodeEl?.querySelectorAll?.('.thumb-item,.image-wrap') || [])];
    oldItems.forEach((oldItem, index) => {
        const oldMedia = oldItem.querySelector('video,audio');
        if(!oldMedia) return;
        const selector = oldMedia.tagName.toLowerCase();
        const oldUrl = oldMedia.dataset?.url || oldMedia.getAttribute('src') || '';
        const oldSignature = oldItem.dataset?.mediaSignature || `${selector}:${oldUrl}`;
        const newItem = newItems.find(item => item.dataset?.mediaSignature === oldSignature)
            || newItems.find(item => item.querySelector?.(selector)?.dataset?.url === oldUrl)
            || newItems[index];
        const newMedia = newItem?.querySelector?.(selector);
        const newUrl = newMedia?.dataset?.url || newMedia?.getAttribute?.('src') || '';
        if(!newMedia || oldUrl !== newUrl) return;
        const state = captureMediaPlaybackState(oldMedia);
        newMedia.replaceWith(oldMedia);
        restoreMediaPlaybackState(oldMedia, state);
        requestAnimationFrame(() => restoreMediaPlaybackState(oldMedia, state));
    });
}
function captureMediaPlaybackStates(){
    const states = new Map();
    world.querySelectorAll('video[data-url], audio[data-url]').forEach(media => {
        const tag = media.tagName.toLowerCase();
        const url = media.dataset.url || media.getAttribute('src') || '';
        if(url) states.set(`${tag}:${url}`, captureMediaPlaybackState(media));
    });
    return states;
}
function restoreMediaPlaybackStates(states){
    if(!states?.size) return;
    world.querySelectorAll('video[data-url], audio[data-url]').forEach(media => {
        const tag = media.tagName.toLowerCase();
        const url = media.dataset.url || media.getAttribute('src') || '';
        restoreMediaPlaybackState(media, states.get(`${tag}:${url}`));
    });
}
function smartRunTaskLabel(run){
    const s = run?.settings || {};
    // 2026-10-13：comfy 引擎必须优先于 kind 判定。此前 kind==='video' 排在前面，
    // 导致 ComfyUI 工作流跑视频时模型标签取节点设置里的 videoModel（doubao-seedance-2-0），
    // 日志里 ComfyUI 任务全被贴成火山视频模型。工作流任务的"模型"就是工作流本身。
    if(s.engine === 'comfy'){
        return s.comfyWorkflow || 'ComfyUI';
    }
    // 云端工作流类同理：任务/模型列写工作流名（2026-10-21，否则被写成 videoModel）
    if(s.engine === 'runninghub'){
        const wfLabel = smartRunWorkflowLabel(s);
        return wfLabel || 'RunningHub 工作流';
    }
    if(run?.kind === 'audio') return s.model || 'MiMo 语音';
    if(run?.kind === 'video') return s.videoModel || 'Video';
    return providerModelDisplayName(s.provider_id || s.providerId || s.provider || '', s.model || '') || 'API Image';
}
function outputUrlLooksVideo(url){
    return /\.(mp4|webm|mov|m4v)(\?|$)/.test(String(url || '').toLowerCase());
}
function proxiedMediaUrl(itemOrUrl, name=''){ return canvasMediaPresentation.proxiedMediaUrl(itemOrUrl, name); }
function prefersDirectRemoteMedia(itemOrUrl){ return canvasMediaPresentation.prefersDirectRemoteMedia(itemOrUrl); }
function displayMediaUrl(itemOrUrl, name=''){ return canvasMediaPresentation.displayMediaUrl(itemOrUrl, name); }
function canvasThumbnailUrl(itemOrUrl, maxEdge=640){ return canvasMediaPresentation.thumbnailUrl(itemOrUrl, maxEdge); }
function bindImageProxyFallback(imgEl, itemOrUrl){ return canvasMediaPresentation.bindImageFallback(imgEl, itemOrUrl); }
function safeExportFileName(name, fallback='download.zip'){ return canvasMediaPresentation.safeExportFileName(name, fallback); }
function extensionForMediaItem(item, fallback='.png'){ return canvasMediaPresentation.extensionForMediaItem(item, fallback); }
function downloadNameForMediaItem(item, fallbackPrefix='canvas-output'){ return canvasMediaPresentation.downloadNameForMediaItem(item, fallbackPrefix); }
function downloadPreviewImage(){
    return CanvasImagePreviewDownloadController.downloadCurrent();
}
function downloadPreviewFile(item){
    return CanvasImagePreviewDownloadController.downloadFile(item);
}
function previewDownloadGroupItems(){
    return CanvasImagePreviewDownloadController.groupItems();
}
async function downloadPreviewGroup(){
    return CanvasImagePreviewDownloadController.downloadGroup();
}
// 2026-10-21（老王：日志里的平台全被写成 doubao 之类的模型名）：
// 云端工作流（RH app/workflow）的「平台」= RunningHub，「模型/任务」= 工作流名；
// 名称按 rhConfigKey 现查配置，新增任何工作流都自动成立，不需要改代码。
function smartRunWorkflowLabel(s){
    const key = String(s?.rhConfigKey || '').trim();
    if(!key) return '';
    try {
        const ref = typeof selectedRunningHubRef === 'function' ? selectedRunningHubRef(s) : null;
        if(ref && typeof runningHubEntryLabel === 'function'){
            const label = runningHubEntryLabel(ref.entry, ref.kind);
            if(label) return String(label).trim();
        }
    } catch(_){}
    try {
        if(typeof parseRunningHubEntryKey === 'function'){
            const parsed = parseRunningHubEntryKey(key);
            if(parsed && parsed.id) return '工作流 ' + String(parsed.id);
        }
    } catch(_){}
    return key.replace(/^[a-zA-Z_]+:/, '') || '';
}
function smartRunPlatformLabel(run){
    const s = run?.settings || {};
    if(s.engine === 'comfy') return 'ComfyUI';
    // 云端工作流类：平台就是 RunningHub（工作流名进「模型/任务」列），
    // 绝不能落成 videoProvider/videoModel 兜底（否则日志平台列会出现 doubao）。
    if(s.engine === 'runninghub') return 'RunningHub';
    if(run?.kind === 'video') return videoProviderById(s.videoProvider || '')?.name || s.videoProvider || 'Video';
    return apiProviderById(s.provider_id || '')?.name || s.provider_id || 'API';
}
// 2026-10-21（老王：新增云端工作流在日志里认不出来）：把 rhConfigKey 解析成
// workflow_id + 可读名称一并写进日志 request —— 新增工作流只要在 api_providers 登记就自动带出。
function smartRunWorkflowMeta(s){
    const key = String(s?.rhConfigKey || '').trim();
    if(!key) return {};
    let id = key.replace(/^[a-zA-Z_]+:/, '');
    try {
        if(typeof parseRunningHubEntryKey === 'function'){
            const parsed = parseRunningHubEntryKey(key);
            if(parsed && parsed.id) id = String(parsed.id);
        }
    } catch(_){}
    let title = '';
    try {
        const ref = typeof selectedRunningHubRef === 'function' ? selectedRunningHubRef(s) : null;
        if(ref && typeof runningHubEntryLabel === 'function') title = runningHubEntryLabel(ref.entry, ref.kind) || '';
    } catch(_){}
    return {rh_config_key:key, workflow_id:id || '', workflow_title:title || ''};
}
function smartRunRequestMeta(run){
    const s = run?.settings || {};
    const wfMeta = smartRunWorkflowMeta(s);
    if(run?.kind === 'audio') return {...(run.request || {}), provider_id:s.provider_id || '',model:s.model || '', ...wfMeta};
    if(s.engine === 'comfy') return {workflow_json:s.comfyWorkflow || '', mode:s.comfyMode || 'custom', ...wfMeta};
    if(run?.kind === 'video') return {provider_id:s.videoProvider || '', model:s.videoModel || '', duration:s.videoDuration || '', aspect_ratio:s.videoAspect || '', resolution:s.videoResolution || '', ...wfMeta};
    return {provider_id:s.provider_id || '', model:s.model || '', size:run?.size || '', quality:s.quality || '', n:s.count || 1, ...wfMeta};
}
function smartRunSnapshot(node, prompt, refs=[], kind='image'){
    const settingsSnapshot = cloneSmartSettings(settings);
    return {
        nodeId:node?.id || '',
        nodeType:node?.type || 'smart-image',
        kind,
        settings:settingsSnapshot,
        prompt:prompt || '',
        refs:(refs || []).map(ref => ({url:ref.url || '', name:ref.name || 'image', kind:ref.kind || ''})).filter(ref => ref.url),
        size: kind === 'image' && isApiLikeEngine(settingsSnapshot.engine) ? sizeForRun(settingsSnapshot) : ''
    };
}
function addSmartGenerationLog({run, outputs=[], runMs=0, error='', taskId='', status='', update=false}) {
    if(!canvas) return;
    canvas.logs = canvas.logs || [];
    const previous = taskId ? canvas.logs.find(log => log.taskId === taskId) : null;
    if(previous && !update) return;
    const entry = {
        id:previous?.id || uid('log'),
        ...(taskId ? {taskId} : {}),
        createdAt:Date.now(),
        status:status || (error ? 'failed' : 'success'),
        kind:run?.kind || 'image',
        platform:smartRunPlatformLabel(run),
        nodeType:run?.nodeType || 'smart-image',
        model:smartRunTaskLabel(run),
        request:{...smartRunRequestMeta(run), ...(taskId ? {task_id:taskId} : {})},
        prompt:run?.prompt || '',
        outputs:(outputs || []).filter(Boolean),
        refs:run?.refs || [],
        runMs:Number(runMs || 0),
        error:error ? String(error) : ''
    };
    canvas.logs = [entry, ...canvas.logs.filter(log => log.id !== entry.id)].slice(0, 500);
    scheduleSave();
    refreshSmartLogPanel();
}
function smartLogPreviewNode(url, kind='image'){
    if(kind === 'video' || outputUrlLooksVideo(url)){
        window.open(url, '_blank');
        return;
    }
    const node = {id:'__smart_log_preview__', type:'smart-image', images:[{url, name:'log-preview', kind}], title:kind === 'video' ? 'Video' : 'Image', __preview:true};
    const prevSelectedId = canvasUiState.selection.primaryId;
    const prevSelectedImage = {...canvasUiState.selection.image};
    nodeStore.addNode(node);
    try { openImageEditor(node.id, 0); }
    finally {
        nodeStore.removeNode(node.id);
        canvasUiState.patchSelection({primaryId: prevSelectedId}, 'selectedId');
        canvasUiState.patchSelection({image: prevSelectedImage}, 'selectedImage');
    }
}
// 2026-09-23：日志面板原本只在点开那一刻渲染一次，之后新生成的日志永远不出现。
// 这里加指纹比对 —— 只有 logs 真的变了才重建 DOM，避免每 2s 全量重排 + 重新请求缩略图。
function smartLogFingerprint(){
    const logs = canvas?.logs || [];
    return `${logs.length}:${logs[0]?.id || ''}:${logs[0]?.createdAt || 0}`;
}
let smartLogPollTimer = null;
let smartLogLastFingerprint = '';
function refreshSmartLogPanel(force=false){
    if(!smartLogModal || !smartLogModal.classList.contains('open')) return;
    const fp = smartLogFingerprint();
    if(!force && fp === smartLogLastFingerprint) return;
    smartLogLastFingerprint = fp;
    renderSmartCanvasLog();
}
function renderSmartCanvasLog(){
    const keepScroll = smartLogList ? Number(smartLogList.scrollTop || 0) : 0;
    const logs = canvas?.logs || [];
    smartLogList.innerHTML = logs.length ? logs.map(log => {
        const thumbs = (log.outputs || []).slice(0, 8).map(url => {
            const safe = escapeAttr(url);
            const kind = log.kind === 'audio' || /\.(mp3|wav|ogg|m4a)(?:[?#]|$)/i.test(url) ? 'audio' : outputUrlLooksVideo(url) ? 'video' : 'image';
            if(kind === 'audio') return audioPlayerHtml({url,kind:'audio',name:'语音生成结果'},220,84);
            return kind === 'video' ? `<video src="${safe}" data-url="${safe}" data-kind="video" muted playsinline disablepictureinpicture controlslist="nodownload noplaybackrate noremoteplayback"></video>` : `<img src="${safe}" data-url="${safe}" data-kind="image" alt="output">`;
        }).join('');
        const date = new Date(log.createdAt || Date.now()).toLocaleString(window.StudioI18n?.lang() === 'en' ? 'en-US' : 'zh-CN');
        const req = log.request || {};
        const taskId = req.task_id || req.taskId || req.prompt_id || req.promptId || '';
        const backend = req.workflow_json || req.workflow || req.provider_id || req.providerId || req.backend || '';
        const subParts = [
            date,
            `${window.StudioI18n?.lang() === 'en' ? 'outputs' : '输出'} ${(log.outputs || []).length}`,
            taskId ? `ID ${taskId}` : '',
            backend
        ].filter(Boolean);
        return `<div class="log-item ${log.status === 'failed' ? 'failed' : ''}">
            <div class="log-main">
                <div class="log-meta">
                    <span class="log-chip ${log.status === 'failed' ? 'status-failed' : 'status-ok'}">${escapeHtml(log.status === 'running' ? '运行中' : log.status === 'failed' ? tr('canvas.failed') : tr('canvas.success'))}</span>
                    <span class="log-chip">${escapeHtml(log.platform || '-')}</span>
                    ${log.model ? `<span class="log-chip">${escapeHtml(log.model)}</span>` : ''}
                    <span class="log-chip">${escapeHtml(formatRunDuration(log.runMs || 0))}</span>
                </div>
                <div class="log-subline">${subParts.map(part => `<span title="${escapeAttr(part)}">${escapeHtml(part)}</span>`).join('')}</div>
                ${log.error ? `<div class="log-error" title="${escapeAttr(log.error)}">${escapeHtml(log.error)}</div>` : ''}
                <div class="log-prompt" title="${escapeAttr(log.prompt || tr('canvas.noPromptMeta'))}" data-prompt="${escapeAttr(log.prompt || '')}">${escapeHtml(log.prompt || tr('canvas.noPromptMeta'))}</div>
            </div>
            <div class="log-thumbs">${thumbs}</div>
        </div>`;
    }).join('') : `<div class="log-empty">${escapeHtml(tr('canvas.noLogs'))}</div>`;
    smartLogList.querySelectorAll('img[data-url], video[data-url]').forEach(el => {
        el.onclick = e => {
            e.stopPropagation();
            smartLogPreviewNode(el.dataset.url, el.dataset.kind || 'image');
        };
    });
    smartLogList.querySelectorAll('[data-prompt]').forEach(el => {
        el.onclick = e => {
            e.stopPropagation();
            const text = el.dataset.prompt || '';
            if(text) navigator.clipboard?.writeText(text).catch(() => {});
            const oldText = el.textContent;
            el.textContent = tr('canvas.copied');
            el.classList.add('copied');
            setTimeout(() => {
                el.textContent = oldText;
                el.classList.remove('copied');
            }, 900);
        };
    });
    bindSmartAudioPlayers(smartLogList);
    refreshIcons();
    // 重建后把滚动位置还回去，正在翻旧日志时不会被弹回顶部
    if(smartLogList && keepScroll > 0) smartLogList.scrollTop = keepScroll;
}
function openSmartCanvasLog(){
    if(!canvas) return;
    renderSmartCanvasLog();
    smartLogModal.classList.add('open');
    smartLogLastFingerprint = smartLogFingerprint();
    // 兜底轮询：日志也可能由其它窗口/实例写入画布，开着面板时也要跟得上
    if(!smartLogPollTimer) smartLogPollTimer = setInterval(() => refreshSmartLogPanel(), 2000);
}
function closeSmartCanvasLog(){
    smartLogModal.classList.remove('open');
    if(smartLogPollTimer){ clearInterval(smartLogPollTimer); smartLogPollTimer = null; }
}
function openSmartCanvasShortcuts(){
    smartShortcutModal?.classList.add('open');
    refreshIcons();
}
function closeSmartCanvasShortcuts(){
    smartShortcutModal?.classList.remove('open');
}
function promptNodeBodyHtml(node){

node.llmProvider = resolveChatProviderId(node.llmProvider || '');
    node.llmModel = resolveChatModel(node.llmModel || '', node.llmProvider);
    node.llmSystemEnabled = node.llmSystemEnabled === true;
    const readonly = node.llmEnabled ? 'readonly' : '';
    const systemPrompt = (node.llmSystemPrompt || '').trim();
    const inputThumbs = smartNodeInputThumbsHtml(promptNodeInputImages(node));
    const templateActive = activePromptTemplateNodeId() === node.id;
    const llmParams = node.llmEnabled ? `
        <div class="prompt-node-llm">
            <select class="prompt-node-control prompt-llm-provider">${chatProviderOptions(node.llmProvider)}</select>
            <select class="prompt-node-control prompt-llm-model">${chatModelOptions(node.llmModel, node.llmProvider)}</select>
            <button class="prompt-node-run prompt-node-control" type="button" ${node.running ? 'disabled' : ''}><i data-lucide="${node.running ? 'loader-2' : 'play'}"></i><span>${node.running ? escapeHtml(tr('common.running')) : escapeHtml(tr('common.run'))}</span></button>
            <textarea class="prompt-node-control prompt-llm-instruction" placeholder="${escapeHtml(tr('smart.promptLlmInstructionPlaceholder'))}">${escapeHtml(node.llmInstruction || '')}</textarea>
            <div class="prompt-node-llm-actions">
                <button class="prompt-node-pill prompt-node-control prompt-system-toggle ${node.llmSystemEnabled ? 'active' : ''}" type="button"><i data-lucide="${node.llmSystemEnabled ? 'toggle-right' : 'toggle-left'}"></i><span>${escapeHtml(node.llmSystemEnabled ? tr('smart.promptLlmDisableSystem') : tr('smart.promptLlmEnableSystem'))}</span></button>
            </div>
            ${node.llmSystemEnabled ? `<textarea class="prompt-node-control prompt-llm-system" placeholder="${escapeHtml(tr('smart.promptLlmSystemPlaceholder'))}">${escapeHtml(systemPrompt || 'You are a helpful prompt assistant.')}</textarea>` : ''}
        </div>` : '';
return `<div class="prompt-node-card">
<textarea class="prompt-node-text prompt-node-control" ${readonly} placeholder="${escapeHtml(tr('smart.promptPlaceholderNode'))}">${escapeHtml(node.text || '')}</textarea>
${`<div class="prompt-node-tools">
<button class="prompt-node-pill prompt-llm-toggle ${node.llmEnabled ? 'active' : ''}" type="button"><i data-lucide="sparkles"></i><span>LLM</span></button>
</div>`}
${node.llmEnabled ? inputThumbs : ''}
${llmParams}
</div>`;
}
// 智能循环token+节点body HTML带外移 canvas-node-body-html.js（第十八刀）。selected 三件套写入走 setter 回主文件真变量。
// 镜像方向菜单：只注入执行回调，浮层本身由控制器自建自注册
if(globalThis.CanvasImageMirrorMenuController){
    CanvasImageMirrorMenuController.configure({
        runMirror: (...a) => applyImageMirror(...a),
        toast: message => toast(message)
    });
}
if(globalThis.CanvasNodeBodyHtml){CanvasNodeBodyHtml.configure({
        canGroupSelectedNodes: (...a) => canGroupSelectedNodes(...a),
        comfyNodeProgressBarHtml: (...a) => comfyNodeProgressBarHtml(...a),
        escapeHtml: (...a) => escapeHtml(...a),
        imageResolutionBadgeHtml: (...a) => imageResolutionBadgeHtml(...a),
        isAudioMediaItem: (...a) => isAudioMediaItem(...a),
        isCanvasGroupNode: (...a) => isCanvasGroupNode(...a),
        jimengQueueText: (...a) => jimengQueueText(...a),
        mediaKindForItem: (...a) => mediaKindForItem(...a),
        openImageEditor: (...a) => openImageEditor(...a),
        openImageMirrorMenu: (nodeId, imageIndex, anchor) => globalThis.CanvasImageMirrorMenuController?.open(nodeId, imageIndex, anchor),
        promptNodeBodyHtml: (...a) => promptNodeBodyHtml(...a),
        selectedLayoutNodes: (...a) => selectedLayoutNodes(...a),
        setImageEditMode: (...a) => setImageEditMode(...a),
        singleMediaHtml: (...a) => singleMediaHtml(...a),
        aspectGroupImageSize: (...a) => aspectGroupImageSize(...a),
        smartCascadeRunForLoop: (...a) => smartCascadeRunForLoop(...a),
        smartCascadeStopText: (...a) => smartCascadeStopText(...a),
        smartImageNameLabelHtml: (...a) => smartImageNameLabelHtml(...a),
        smartLoopCount: (...a) => smartLoopCount(...a),
        smartLoopInputImages: (...a) => smartLoopInputImages(...a),
        smartLoopInputPromptItems: (...a) => smartLoopInputPromptItems(...a),
        smartLoopPreviewImages: (...a) => smartLoopPreviewImages(...a),
        smartLoopPromptFieldValues: (...a) => smartLoopPromptFieldValues(...a),
        smartLoopSelectedInputPrompt: (...a) => smartLoopSelectedInputPrompt(...a),
        smartNodeInputThumbsHtml: (...a) => smartNodeInputThumbsHtml(...a),
        thumbMediaHtml: (...a) => thumbMediaHtml(...a),
        trf: (...a) => trf(...a),
        selectedId: () => canvasUiState.selection.primaryId,
        selectedIds: () => canvasUiState.selection.ids,
        selectedImage: () => canvasUiState.selection.image,
        block: () => block,
        canvas: () => canvas,
        deleteImage: () => deleteImage,
        escapeAttr: () => escapeAttr,
        imageForDisplay: () => imageForDisplay,
        setSelectedId: v => { canvasUiState.patchSelection({primaryId: v}, 'selectedId'); },
        setSelectedIds: v => { canvasUiState.patchSelection({ids: v}, 'selectedIds'); },
        setSelectedImage: v => { canvasUiState.patchSelection({image: v}, 'selectedImage'); }
});}
function smartLoopEditorText(){return CanvasNodeBodyHtml.smartLoopEditorText.apply(null, arguments);}
function insertSmartLoopToken(){return CanvasNodeBodyHtml.insertSmartLoopToken.apply(null, arguments);}
function smartNodeToolbarHtml(){return CanvasNodeBodyHtml.smartNodeToolbarHtml.apply(null, arguments);}
function openSmartImageTool(){return CanvasNodeBodyHtml.openSmartImageTool.apply(null, arguments);}
function nodeBodyHtml(){return CanvasNodeBodyHtml.nodeBodyHtml.apply(null, arguments);}
function nowMs(){return CanvasNodeBodyHtml.nowMs.apply(null, arguments);}
const generatedOutputNameReservations = new Set();
const remoteGeneratedMediaLocalizationInFlight = new Set();
function generatedDatePrefix(date=new Date()){
    return `${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}
function generatedDateSequenceName(index=0, ext='png', date=new Date()){
    const cleanExt = String(ext || 'png').replace(/^\./, '') || 'png';
    return `${generatedDatePrefix(date)}-${String(Number(index || 0) + 1).padStart(2, '0')}.${cleanExt}`;
}
function smartGeneratedOutputName(index=0, kind='image', date=new Date()){
    const ext = kind === 'video' ? 'mp4' : kind === 'audio' ? 'mp3' : kind === 'text' ? 'txt' : 'png';
    return generatedDateSequenceName(index, ext, date);
}
function generatedOutputExt(kind='image'){
    return kind === 'video' ? 'mp4' : kind === 'audio' ? 'mp3' : kind === 'text' ? 'txt' : 'png';
}
function generatedOutputKindForName(name='', fallback='image'){
    const ext = String(name || '').split('?')[0].split('#')[0].split('.').pop().toLowerCase();
    if(['mp4','mov','avi','webm','mkv'].includes(ext)) return 'video';
    if(['png','jpg','jpeg','webp','gif','bmp'].includes(ext)) return 'image';
    return fallback || 'image';
}
function generatedOutputUrlForName(name, kind='image'){
    const folder = generatedOutputKindForName(name, kind) === 'video' ? 'videos' : 'images';
    return `/assets/output/${folder}/${encodeURIComponent(name).replace(/%2F/gi, '/')}`;
}
async function generatedOutputNameExists(name, kind='image'){
    if(!name) return true;
    try {
        const res = await fetch(`${generatedOutputUrlForName(name, kind)}?v=${Date.now()}`, {method:'HEAD', cache:'no-store'});
        return res.ok;
    } catch(err) {
        return false;
    }
}
async function reserveGeneratedDateNames(count=1, ext='png', date=new Date(), kind='image'){
    const names = [];
    const cleanExt = String(ext || 'png').replace(/^\./, '') || 'png';
    const prefix = generatedDatePrefix(date);
    let index = 1;
    while(names.length < count && index < 10000){
        const name = `${prefix}-${String(index).padStart(2, '0')}.${cleanExt}`;
        const key = name.toLowerCase();
        if(!generatedOutputNameReservations.has(key) && !(await generatedOutputNameExists(name, kind))){
            generatedOutputNameReservations.add(key);
            names.push(name);
        }
        index += 1;
    }
    while(names.length < count){
        const name = `${prefix}-${Date.now()}-${names.length + 1}.${cleanExt}`;
        generatedOutputNameReservations.add(name.toLowerCase());
        names.push(name);
    }
    return names;
}
async function localizeGeneratedOutputItems(items, kind='image'){
    const sources = (items || []).map(item => {
        const source = item && typeof item === 'object' ? item : {};
        const url = typeof item === 'string' ? item : item?.url || '';
        if(!url) return null;
        return {
            source,
            url,
            kind:source.kind || source.mediaKind || kind || 'image'
        };
    }).filter(Boolean);
    if(!sources.length) return [];
    const needsLocalization = sources.some(entry => /^https?:\/\//i.test(String(entry.url || '')));
    if(!needsLocalization) return sources.map(entry => ({...entry.source, url:entry.url, kind:entry.kind}));
    try {
        const res = await fetch('/api/localize-generated-media', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({
                kind,
                canvas_id:canvasId || '',
                canvas_title:String(canvas?.title || document.getElementById('smartTitle')?.textContent || '').trim(),
                items:sources.map(entry => ({
                    ...entry.source,
                    url:entry.url,
                    kind:entry.kind
                }))
            })
        });
        if(!res.ok) throw new Error(await res.text());
        const data = await res.json().catch(() => ({}));
        const localizedItems = Array.isArray(data.items) ? data.items : [];
        return sources.map((entry, index) => {
            const localized = localizedItems[index];
            if(!localized || !localized.url) return {
                ...entry.source,
                url:entry.url,
                kind:entry.kind,
                source_url:entry.source?.source_url || entry.source?.sourceUrl || entry.url,
                remoteFallback:true,
                remote_fallback:true
            };
            return {
                ...entry.source,
                ...localized,
                url:localized.url,
                kind:localized.kind || entry.kind,
                remoteFallback:Boolean(localized.remoteFallback || localized.remote_fallback),
                remote_fallback:Boolean(localized.remote_fallback || localized.remoteFallback)
            };
        });
    } catch(err) {
        console.warn('Localize generated output failed', err);
        return sources.map(entry => ({
            ...entry.source,
            url:entry.url,
            kind:entry.kind,
            source_url:entry.source?.source_url || entry.source?.sourceUrl || entry.url,
            remoteFallback:true,
            remote_fallback:true,
            localizeError:String(err?.message || err || '')
        }));
    }
}
function generatedImageNeedsLocalization(item){
    if(!item || mediaKindForItem(item) !== 'image') return false;
    const url = String(item.url || '').trim();
    if(!/^https?:\/\//i.test(url)) return false;
    const retryAt = Number(item.localizeRetryAt || 0);
    if(retryAt && nowMs() < retryAt) return false;
    return Boolean(item.generatedResult || item.display_name || item.source_url || item.sourceUrl || /\/output\//i.test(url));
}
async function localizeRemoteGeneratedNodeImages(node){
    if(!node?.id || !(node.images || []).some(generatedImageNeedsLocalization)) return;
    const entries = (node.images || []).map((img, index) => ({img, index})).filter(entry => generatedImageNeedsLocalization(entry.img));
    if(!entries.length) return;
    const key = `${node.id}|${entries.map(entry => entry.img.url).join('|')}`;
    if(remoteGeneratedMediaLocalizationInFlight.has(key)) return;
    remoteGeneratedMediaLocalizationInFlight.add(key);
    try {
        const items = entries.map(({img, index}) => ({
            ...img,
            name:img.name || img.display_name || fileNameFromUrl(img.url) || `output-${index + 1}.png`,
            display_name:img.display_name || img.name || fileNameFromUrl(img.url) || ''
        }));
        const localized = await localizeGeneratedOutputItems(items, 'image');
        let changed = false;
        entries.forEach(({img, index}, i) => {
            const next = localized[i];
            const current = node.images?.[index];
            if(!current || current.url !== img.url || !next?.url) return;
            if(/^https?:\/\//i.test(String(next.url))){
                node.images[index] = stripImageGenerationMeta({
                    ...current,
                    ...next,
                    url:current.url,
                    source_url:next.source_url || current.source_url || current.sourceUrl || img.url,
                    kind:next.kind || current.kind || 'image',
                    generatedResult:true,
                    remoteFallback:true,
                    remote_fallback:true,
                    localizeRetryAt:nowMs() + 5 * 60 * 1000
                });
                changed = true;
                return;
            }
            node.images[index] = stripImageGenerationMeta({
                ...current,
                ...next,
                source_url:next.source_url || current.source_url || current.sourceUrl || img.url,
                kind:next.kind || current.kind || 'image',
                generatedResult:true
            });
            changed = true;
        });
        if(changed){
            render();
            scheduleSave();
        }
    } catch(err) {
        console.warn('Localize visible generated media failed', err);
    } finally {
        remoteGeneratedMediaLocalizationInFlight.delete(key);
    }
}
// 生成产物命名+运行计时域外移 canvas-generated-output-naming.js（第三刀），runTimerInterval 已随域迁入模块自持。
if(globalThis.CanvasGeneratedOutputNaming){CanvasGeneratedOutputNaming.configure({
        escapeHtml: (...a) => escapeHtml(...a),
        generatedDateSequenceName: (...a) => generatedDateSequenceName(...a),
        generatedOutputExt: (...a) => generatedOutputExt(...a),
        generatedOutputNameExists: (...a) => generatedOutputNameExists(...a),
        localizeGeneratedOutputItems: (...a) => localizeGeneratedOutputItems(...a),
        localizeRemoteGeneratedNodeImages: (...a) => localizeRemoteGeneratedNodeImages(...a),
        nodeRect: (...a) => nodeRect(...a),
        nowMs: (...a) => nowMs(...a),
        render: (...a) => render(...a),
        reserveGeneratedDateNames: (...a) => reserveGeneratedDateNames(...a),
        scheduleSave: (...a) => scheduleSave(...a),
        stripImageGenerationMeta: (...a) => stripImageGenerationMeta(...a),
        syncRunButtonAvailability: (...a) => syncRunButtonAvailability(...a),
        uid: (...a) => uid(...a),
        generatedImageNeedsLocalization: () => generatedImageNeedsLocalization,
        generatedOutputNameReservations: () => generatedOutputNameReservations,
        nodes: () => nodes,
        visibleNodeList: (...a) => visibleNodeList(...a),
        world: () => world
});}

function queueRemoteGeneratedMediaLocalization(){return CanvasGeneratedOutputNaming.queueRemoteGeneratedMediaLocalization.apply(null, arguments);}

function cleanGeneratedOutputBaseName(){return CanvasGeneratedOutputNaming.cleanGeneratedOutputBaseName.apply(null, arguments);}

function reserveGeneratedBaseNames(){return CanvasGeneratedOutputNaming.reserveGeneratedBaseNames.apply(null, arguments);}

function uniqueGeneratedMediaItems(){return CanvasGeneratedOutputNaming.uniqueGeneratedMediaItems.apply(null, arguments);}

function smartGeneratedOutputItems(){return CanvasGeneratedOutputNaming.smartGeneratedOutputItems.apply(null, arguments);}

function formatRunDuration(){return CanvasGeneratedOutputNaming.formatRunDuration.apply(null, arguments);}

function nodeRunElapsedMs(){return CanvasGeneratedOutputNaming.nodeRunElapsedMs.apply(null, arguments);}

function runTimePillHtml(){return CanvasGeneratedOutputNaming.runTimePillHtml.apply(null, arguments);}

function updateComfyNodeLiveState(){return CanvasGeneratedOutputNaming.updateComfyNodeLiveState.apply(null, arguments);}

function nodeProgressRingPath(){return CanvasGeneratedOutputNaming.nodeProgressRingPath.apply(null, arguments);}

function syncNodeProgressRing(){return CanvasGeneratedOutputNaming.syncNodeProgressRing.apply(null, arguments);}

function comfyNodeProgressBarHtml(){return CanvasGeneratedOutputNaming.comfyNodeProgressBarHtml.apply(null, arguments);}

function syncAllNodeProgressRings(){return CanvasGeneratedOutputNaming.syncAllNodeProgressRings.apply(null, arguments);}

function hideRunTimerForNode(){return CanvasGeneratedOutputNaming.hideRunTimerForNode.apply(null, arguments);}

function refreshRunTimerPills(){return CanvasGeneratedOutputNaming.refreshRunTimerPills.apply(null, arguments);}
function render(){
    const materializedNodes = reconcileExistingAgentGroups(nodes);
    if(materializedNodes.mcpGroupChanged){
        nodes = materializedNodes;
        scheduleSave();
    }
    syncCanvasInputModeUi();
    if(canvasObjectRefPickerOpen) renderCanvasObjectRefPicker();
    const composerEl = composer;
    const mediaStates = captureMediaPlaybackStates();
    const reusableNodes = new Map();
    const nodeMap = new Map(nodes.map(node => [node.id, node]));
    const existingEls = new Map();
    world.querySelectorAll('.image-node').forEach(el => {
        const node = nodeMap.get(el.dataset.id);
        if(!node) return;
        existingEls.set(node.id, el);
        if(smartNodeHasLiveMedia(node)) reusableNodes.set(node.id, el);
    });
    const renderStamp = String(++nodeRenderStamp);
    const renderNodes = visibleNodeList();
    const nodeHtmlEntries = renderNodes.map(node => {
        ensureNodeTextMedia(node, true);
        const imgs = node.images || [];
const isTable = node.type === 'smart-table';
const title = isTable ? '镜头表' : node.type === 'smart-prompt' ? 'Prompt' : node.type === 'smart-loop' ? 'Loop' : (node.title || (imgs.length > 1 ? 'Group' : imgs.length ? 'Image' : escapeHtml(tr('smart.createImportNode'))));
        const scale = nodeScale(node);
        const layout = imageLayout(imgs, scale, node);
        const isPrompt = node.type === 'smart-prompt';
        const isLoop = node.type === 'smart-loop';
        const isImageNode = node.type === 'smart-image' || !node.type;
        const isJimengPending = Boolean(node.jimengPending && node.jimengPending.submitId && imgs.length === 0);
        // comfyBusy：comfyStatus queued/running 的节点（级联槽位等无 pending 标志）按忙碌渲染，
        // 不算空节点（否则会渲染成上传占位大黑窗）、尺寸走 pending 档而不是 empty 档。
        const comfyBusy = !isJimengPending && (node.comfyStatus === 'queued' || node.comfyStatus === 'running') && imgs.length === 0;
        const isQueued = Boolean((node.queued || node.comfyStatus === 'queued') && imgs.length === 0 && !node.pending && !isJimengPending);
        const isEmpty = isImageNode && imgs.length === 0 && !node.pending && !isQueued && !isJimengPending && !comfyBusy;
        const isHistory = isHistoryGroupNode(node);
        const isGroup = isImageNode && imgs.length > 1;
        // Multi-image cards and canvas group frames have distinct surfaces.
        // nodeLayerZ owns stacking; component CSS must not override it.
        const isPending = ((node.pending || node.status === 'pending' || isQueued || isJimengPending || comfyBusy) && imgs.length === 0);
        const isBlenderPreview = node.runSettings?.engine === 'blender' || node.runSettings?.provider_id === 'blender' || node.title === '3D预演';
        const body = nodeBodyHtml(node, layout);
        const hasOut = (canvas?.connections || []).some(c => c.from === node.id);
        const deleteBtn = `<button class="mini-x node-delete" type="button" title="${escapeHtml(tr('smart.deleteNode'))}"><i data-lucide="trash-2"></i></button>`;
        const hint = isPending ? escapeHtml(tr('smart.hintPending')) : (imgs.length > 1 ? escapeHtml(tr('smart.hintMulti')) : imgs.length ? escapeHtml(tr('smart.hintSingle')) : escapeHtml(tr('smart.hintEmpty')));
        const comfyNodeNote = node.comfyError
            ? `<div class="comfy-node-note error">${escapeHtml(`失败：${node.comfyError}`)}</div>`
            : node.comfyNotice ? `<div class="comfy-node-note">${escapeHtml(node.comfyNotice)}</div>` : '';
const html = `<div class="image-node ${node.cardSize ? 'fixed-media-card' : ''} ${isEmpty ? 'empty-node' : ''} ${node.type === 'smart-speech' ? 'speech-smart-node' : ''} ${isGroup ? 'multi-image-node' : ''} ${node.groupLayout?.mode === 'preserve' ? 'preserved-group-node' : ''} ${isCanvasGroupNode(node) ? 'canvas-group-node' : ''} ${isHistory ? 'history-group-node' : ''} ${isPrompt ? 'prompt-smart-node' : ''} ${isTable ? 'table-smart-node' : ''} ${isLoop ? 'loop-smart-node' : ''} ${isBlenderPreview ? 'blender-preview-node' : ''} ${isNodeSelected(node.id) ? 'selected' : ''} ${(dragState?.groupIds?.includes(node.id) || dragState?.id === node.id) ? 'dragging' : ''} ${node.running ? 'node-running' : ''} ${isPending ? 'node-pending' : ''} ${node.comfyStatus === 'running' ? 'comfy-running' : ''} ${node.comfyStatus === 'queued' ? 'comfy-queued' : ''} node-status-${escapeHtml(node.status || 'ready')} node-role-${escapeHtml(node.role || 'media')}" data-id="${escapeHtml(node.id)}" data-status="${escapeHtml(node.status || 'ready')}" data-role="${escapeHtml(node.role || 'media')}" data-comfy-status="${escapeHtml(node.comfyStatus || '')}" ${(node.comfyStatus === 'queued' && Number(node.comfyQueuePosition ?? -1) > 0) ? `data-comfy-queue="${Number(node.comfyQueuePosition)}"` : ''} style="left:${node.x || 0}px;top:${node.y || 0}px;width:${layout.width}px;height:${layout.height}px;z-index:${nodeLayerZ(node)}">
            <div class="node-head"><div class="node-title">${node.canvasSetEnabled === true ? `<span class="node-set-badge" title="${escapeAttr(tr('smart.setBadgeTip'))}">SET</span>` : ''}${title}</div><div class="node-actions">${deleteBtn}</div></div>
            ${isCanvasGroupNode(node) ? `<div class="canvas-group-header"><span class="canvas-group-title-display" title="双击重命名">${escapeHtml(node.title || '未命名组')}</span><button class="canvas-group-delete node-delete" type="button" title="删除组"><i data-lucide="trash-2"></i></button></div>` : ''}
            ${!isCanvasGroupNode(node) ? (!isEmpty ? `<div class="floating-node-set">${canvasNodeSetToggleHtml(node)}</div>${((node.type === 'smart-image' || node.type === 'smart-video' || node.type === 'smart-audio' || !node.type) && hasOut) ? '<button class="node-move-lines" type="button" title="把线移到新素材（点此节点，再点目标素材，旧素材所有连线整体平移，图片与节点均不动）"><i data-lucide="link"></i></button>' : ''}${(node.type === 'smart-image' || node.type === 'smart-video' || node.type === 'smart-audio' || !node.type) ? '<button class="upload-node-btn" type="button" data-upload-action="files"><i data-lucide="upload"></i><span>上传</span></button>' : ''}<div class="floating-node-actions"><button class="mini-x node-delete" type="button" title="${escapeHtml(tr('smart.deleteNode'))}"><i data-lucide="trash-2"></i></button></div>` : `<div class="floating-node-actions"><button class="mini-x node-delete" type="button" title="${escapeHtml(tr('smart.deleteNode'))}"><i data-lucide="trash-2"></i></button></div>`) : ''}
            ${runTimePillHtml(node)}
            ${comfyNodeNote}
            <div class="node-body">${body}</div>
            ${!isImageNode ? smartNodeToolbarHtml() : ''}
            <div class="node-hint">${hint}</div>
            ${isSmartImageNode(node) || isCanvasGroupNode(node) || imgs.length || node.pending || isQueued || isJimengPending || isPrompt || isLoop || isTable || node.type === 'smart-speech' ? '<div class="node-resize-handle" data-resize="1"></div>' : ''}
            ${canvasPortDotsHtml(node, 'input')}
            ${canvasPortDotsHtml(node, 'output')}
        </div>`;
        return {node, html, key:nodeRenderKey(html)};
    });
    // ── 增量复用：HTML 没变的节点保留原 DOM（不重建、不重新绑事件、图片不重载）──
    const plan = nodeHtmlEntries.map(entry => {
        const existing = existingEls.get(entry.node.id);
        const reusable = reusableNodes.get(entry.node.id);
        const canReuse = Boolean(existing) && !reusable && existing.dataset.renderKey === entry.key;
        return {node:entry.node, html:entry.html, key:entry.key, existing, reusable, canReuse};
    });
    const tpl = document.createElement('template');
    const renderedNodeEls = new Map();
    const freshPlan = plan.filter(entry => !entry.canReuse);
    if(freshPlan.length){
        tpl.innerHTML = freshPlan.map(entry => entry.html).join('');
        freshPlan.forEach(entry => {
            const fresh = tpl.content.querySelector(`.image-node[data-id="${CSS.escape(entry.node.id)}"]`);
            if(fresh) renderedNodeEls.set(entry.node.id, fresh);
        });
    }
    const keepEls = new Set();
    reusableNodes.forEach(el => keepEls.add(el));
    plan.forEach(entry => { if(entry.canReuse && entry.existing) keepEls.add(entry.existing); });
    const connSvg = world.querySelector('svg.connection-layer');
    if(connSvg) keepEls.add(connSvg);
    if(composerEl) keepEls.add(composerEl);
    [...world.childNodes].forEach(child => {
        if(!keepEls.has(child)) child.remove();
    });
    if(composerEl && composerEl.parentNode !== world) world.appendChild(composerEl);
    // 连线层用数据模型算坐标，不依赖节点 DOM，所以裁剪掉节点也不会断线
    if(connSvg) refreshConnectionLayer();
    else world.insertAdjacentHTML('beforeend', renderConnections());
    plan.forEach(entry => {
        if(entry.canReuse) return;
        const fresh = renderedNodeEls.get(entry.node.id);
        if(!fresh) return;
        fresh.dataset.renderKey = entry.key;
        fresh.dataset.renderStamp = renderStamp;
        world.appendChild(fresh);
        const reusable = entry.reusable;
        if(reusable){
            transplantSmartMediaElements(reusable, fresh);
            if(reusable !== fresh) reusable.remove();
        }
    });
    restoreMediaPlaybackStates(mediaStates);
    bindNodeEvents();
    bindConnectionEvents();
    updateComposer();
    scheduleMinimapRender();
    refreshSmartNodeToolButtons();
    if(window.lucide) lucide.createIcons();
    bindSmartAudioPlayers();
    measureSmartNodeImages();
    queueRemoteGeneratedMediaLocalization();
    refreshRunTimerPills();
    installAudioThumbCleanup();
    CanvasRenderScheduler.markCullRendered();
    scheduleImageUpgrade();
    return;
    world.innerHTML = '';
    if(composerEl) world.appendChild(composerEl);
    world.insertAdjacentHTML('beforeend', renderConnections());
    const nodesHtml = nodes.map(node => {
        const imgs = node.images || [];
        const title = node.type === 'smart-prompt' ? 'Prompt' : node.type === 'smart-loop' ? 'Loop' : (imgs.length > 1 ? 'Group' : 'Image');
        const scale = nodeScale(node);
        const layout = imageLayout(imgs, scale, node);
        const isPrompt = node.type === 'smart-prompt';
        const isLoop = node.type === 'smart-loop';
        const isImageNode = node.type === 'smart-image' || !node.type;
        const isQueued = Boolean(node.queued && imgs.length === 0 && !node.pending);
        const isEmpty = isImageNode && imgs.length === 0 && !node.pending && !isQueued;
        const isGroup = isImageNode && imgs.length > 1;
        const isPending = (node.pending || isQueued) && imgs.length === 0;
        const body = nodeBodyHtml(node, layout);
        const deleteBtn = `<button class="mini-x node-delete" type="button" title="${escapeHtml(tr('smart.deleteNode'))}"><i data-lucide="trash-2"></i></button>`;
        return `<div class="image-node ${node.cardSize ? 'fixed-media-card' : ''} ${isEmpty ? 'empty-node' : ''} ${isGroup ? 'multi-image-node' : ''} ${isPrompt ? 'prompt-smart-node' : ''} ${isLoop ? 'loop-smart-node' : ''} ${isNodeSelected(node.id) ? 'selected' : ''} ${(dragState?.groupIds?.includes(node.id) || dragState?.id === node.id) ? 'dragging' : ''} ${node.running ? 'node-running' : ''} ${isPending ? 'node-pending' : ''}" data-id="${escapeHtml(node.id)}" style="left:${node.x || 0}px;top:${node.y || 0}px;width:${layout.width}px;height:${layout.height}px;z-index:${nodeLayerZ(node)}">
            <div class="node-head"><div class="node-title">${title}</div><div class="node-actions">${deleteBtn}</div></div>
            ${!isEmpty ? `<div class="floating-node-actions"><button class="mini-x node-delete" type="button" title="${escapeHtml(tr('smart.deleteNode'))}"><i data-lucide="trash-2"></i></button></div>` : ''}
            ${runTimePillHtml(node)}
            <div class="node-body">${body}</div>
            <div class="node-hint">${isPending ? escapeHtml(tr('smart.hintPending')) : (imgs.length > 1 ? escapeHtml(tr('smart.hintMulti')) : imgs.length ? escapeHtml(tr('smart.hintSingle')) : escapeHtml(tr('smart.hintEmpty')))}</div>
            ${node.type === 'smart-image' || imgs.length || node.pending || isQueued || isPrompt || isLoop ? '<div class="node-resize-handle" data-resize="1"></div>' : ''}
            ${canvasPortDotsHtml(node, 'input')}
            ${canvasPortDotsHtml(node, 'output')}
        </div>`;
    }).join('');
    world.insertAdjacentHTML('beforeend', nodesHtml);
    bindNodeEvents();
    bindConnectionEvents();
    updateComposer();
    renderMinimap();
    if(window.lucide) lucide.createIcons();
    measureSmartNodeImages();
    refreshRunTimerPills();
    syncAllNodeProgressRings();
}
function measureSmartNodeImages(){
    world.querySelectorAll('.image-node img,.image-node video').forEach(imgEl => {
        const nodeEl = imgEl.closest('.image-node');
        const itemEl = imgEl.closest('[data-image-index]');
        const node = nodes.find(n => n.id === nodeEl?.dataset.id);
        const index = Number(itemEl?.dataset.imageIndex ?? 0);
        const image = node?.images?.[index];
        if(imgEl.tagName?.toLowerCase() === 'img' && image?.url) bindImageProxyFallback(imgEl, image);
        const isImageElement = imgEl.tagName?.toLowerCase() === 'img';
        const localAssetUrl = localAssetUrlForImageInfo(image);
        if(isImageElement && localAssetUrl){
            ensureImageResolutionMetadata(image, true);
            return;
        }
        if(!node || !image || image.natural_w || image.natural_h) return;
        const apply = () => {
            const w = imgEl.naturalWidth || imgEl.videoWidth || 0;
            const h = imgEl.naturalHeight || imgEl.videoHeight || 0;
            if(w <= 0 || h <= 0 || image.natural_w || image.natural_h) return;
            image.natural_w = w;
            image.natural_h = h;
            applyThumbDisplaySizeToElement(itemEl, image, Math.max(itemEl?.clientWidth || 0, itemEl?.clientHeight || 0));
            if(!fitAutoGroupMemberToSlot(node, image) && (node.images || []).length === 1 && !node.w && !node.h){
                const layout = singleImageLayout(image, node, mediaNodeDefaultScale(node));
                node.w = layout.width;
                node.h = layout.height;
            }
            reconcileSingleImageAspect(node, image, w, h);
            scheduleImageMeasureRender();
            scheduleSave();
        };
        const isVideo = imgEl.tagName?.toLowerCase() === 'video';
        if(!isVideo && imgEl.complete) apply();
        else imgEl.addEventListener('load', apply, {once:true});
        imgEl.addEventListener('loadedmetadata', apply, {once:true});
    });
}
let connScissorHideTimer = 0;
let connScissorShowTimer = 0;
let connScissorLineIndex = -1;
const CONN_SCISSOR_SHOW_DELAY = 480; // 光标需在同一条线上停留满 480ms 才弹剪刀
function hideConnScissor(){
    const g = world && world.querySelector('g.conn-scissor');
    connScissorLineIndex = -1;
    clearTimeout(connScissorShowTimer);
    if(g){
        g.classList.remove('show');
        g.dataset.connIndex = '-1';
        g.setAttribute('transform', 'translate(-100 -100)');
    }
}
function requestHideConnScissor(){
    clearTimeout(connScissorShowTimer);
    clearTimeout(connScissorHideTimer);
    connScissorHideTimer = setTimeout(hideConnScissor, 160);
}
// 光标投影到连线曲线上的最近点（粗采样+三分细化）
function connScissorNearestPoint(path, x, y){
    const L = path.getTotalLength();
    if(!Number.isFinite(L) || L <= 0) return null;
    const steps = Math.max(8, Math.min(64, Math.floor(L / 14)));
    let bestAt = 0, bestD = Infinity;
    for(let i = 0; i <= steps; i++){
        const at = L * i / steps;
        const p = path.getPointAtLength(at);
        const d = (p.x - x) * (p.x - x) + (p.y - y) * (p.y - y);
        if(d < bestD){ bestD = d; bestAt = at; }
    }
    let span = L / steps;
    for(let i = 0; i < 10 && span > 0.6; i++){
        const lo = Math.max(0, bestAt - span), hi = Math.min(L, bestAt + span);
        const a = path.getPointAtLength(lo + (hi - lo) / 3), b = path.getPointAtLength(hi - (hi - lo) / 3);
        const da = (a.x - x) * (a.x - x) + (a.y - y) * (a.y - y), db = (b.x - x) * (b.x - x) + (b.y - y) * (b.y - y);
        bestAt = da < db ? lo + (hi - lo) / 3 : hi - (hi - lo) / 3;
        span = (hi - lo) / 3;
    }
    const p = path.getPointAtLength(bestAt);
    return {x:p.x, y:p.y};
}
function updateConnScissorFromEvent(event){
    if(!world || connectionCutState) return;
    // 交互进行中（平移/框选/拖节点/拖端口/缩节点/拖输入缩略图）直接跳过全量最近线求解。
    // 求解成本 = 连线数 × 每条 28~84 次 path.getPointAtLength()（同步几何计算），
    // 百来条连线时每次 pointermove 上万次；平移每帧都触发，是"连线一显示拖动就卡"的头号元凶。
    // 跳过不影响功能：剪刀只在光标停留时弹出，交互结束后光标停下即恢复跟随。
    if(panState || selectionState || portDragState || promptResizeState
        || (inputThumbDragState && inputThumbDragState.active)
        || document.body.classList.contains('smart-node-drag')
        || document.body.classList.contains('smart-node-resize')) return;
    const g = world.querySelector('g.conn-scissor');
    if(!g) return;
    // 2026-10-17 老王：节点左右 + 号（.node-port，伸出节点外）区域内不许弹剪刀——
    // 线一多，光标落在这片区域上，剪刀把线挡住，一点就把线剪断了。
    // 判断口径：命中节点自身/其任意子元素（含端口）即跳过；剪刀层盖在端口之上时
    // target 会变成剪刀本身，所以再用 elementsFromPoint 看底下有没有节点元素。
    const overNodeOrPort = (() => {
        if(event.target?.closest?.('.image-node')) return true;
        const stack = document.elementsFromPoint?.(event.clientX, event.clientY) || [];
        return stack.some(el => el.closest?.('.image-node'));
    })();
    if(overNodeOrPort || event.target?.closest?.('.composer')){ requestHideConnScissor(); return; }
    const scaleNow = safeScale(viewport.scale);
    const wp = screenToWorld(event);
    const paths = [...world.querySelectorAll('svg.connection-layer path.conn-hit')];
    let best = null;
    for(const path of paths){
        const index = Number(path.dataset.connIndex);
        if(!Number.isFinite(index) || index < 0) continue;
        const p = connScissorNearestPoint(path, wp.x, wp.y);
        if(!p) continue;
        const d = Math.hypot(p.x - wp.x, p.y - wp.y);
        // 命中容差按屏幕距离恒定（剪刀本身也是恒定屏幕尺寸）→ 世界距离要除以缩放
        if(d < 16 / scaleNow && (!best || d < best.d)) best = {d, index, x:p.x, y:p.y};
    }
    if(best){
        clearTimeout(connScissorHideTimer);
        // 位置始终贴着光标所在线上移动；剪刀弹出需在同一条线停留满 480ms。
        // 2026-10-17 老王：剪刀图标不随画布缩放 → 整体乘 1/scale 抵消世界层缩放。
        g.dataset.connIndex = String(best.index);
        g.setAttribute('transform', `translate(${best.x} ${best.y}) scale(${1 / scaleNow})`);
        if(connScissorLineIndex !== best.index){
            connScissorLineIndex = best.index;
            if(g.classList.contains('show')){
                g.classList.remove('show'); // 换到另一条线：重新计时
            }
            clearTimeout(connScissorShowTimer);
            connScissorShowTimer = setTimeout(() => {
                if(connScissorLineIndex === best.index) g.classList.add('show');
            }, CONN_SCISSOR_SHOW_DELAY);
        }
    } else {
        connScissorLineIndex = -1;
        requestHideConnScissor();
    }
}
function bindConnectionEvents(){
    // Keep the cut button above external port hit areas, while wires stay behind cards.
    const scissor = world.querySelector('svg.connection-layer:not(.connection-tools-layer) g.conn-scissor');
    if(scissor){
        world.querySelector('svg.connection-tools-layer')?.remove();
        const tools = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        tools.setAttribute('class', 'connection-layer connection-tools-layer');
        tools.setAttribute('width', '6000');
        tools.setAttribute('height', '4000');
        tools.setAttribute('viewBox', '0 0 6000 4000');
        tools.appendChild(scissor);
        world.appendChild(tools);
    }
    if(!world.__connScissorMoveBound){
        world.__connScissorMoveBound = true;
        world.addEventListener('pointermove', updateConnScissorFromEvent);
        world.addEventListener('pointerleave', requestHideConnScissor);
    }
    world.querySelectorAll('[data-conn-index]').forEach(el => {
        // render() 与 refreshConnectionLayer() 可能连续处理同一组 SVG 节点。
        if(el.__connectionEventsBound) return;
        el.__connectionEventsBound = true;
        if(el.classList.contains('conn-scissor')){
            el.addEventListener('pointerenter', () => clearTimeout(connScissorHideTimer));
            el.addEventListener('pointerleave', requestHideConnScissor);
            el.addEventListener('pointerdown', e => {
                e.preventDefault();
                e.stopPropagation();
            });
            el.addEventListener('click', e => {
                e.preventDefault();
                e.stopPropagation();
                if(!el.classList.contains('show')) return;
                const index = Number(el.dataset.connIndex);
                if(Number.isFinite(index) && index >= 0) disconnectConnection(index);
                hideConnScissor();
            });
            return;
        }
        ['mousedown', 'mouseup', 'pointerdown', 'pointerup'].forEach(type => {
            el.addEventListener(type, e => {
                e.stopPropagation();
            });
        });
        el.addEventListener('contextmenu', e => {
            if(!e.altKey) return;
            e.preventDefault();
            e.stopPropagation();
            const index = Number(el.dataset.connIndex);
            if(Number.isFinite(index)) startConnectionCutGesture(e, index);
        });
        // 连线只作为命中区域和切断手势起点；点击删除仅由已显示的剪刀按钮触发。
        if(el.classList.contains('conn-hit')) return;
    });
}
function isConnectionInteractionTarget(target){
    return Boolean(target?.closest?.('[data-conn-index], .connection-layer'));
}
function isCanvasZoomPreviewExcluded(target){
  // 第8步：缩放预览吞事件浮层判定（原两处内联链收编）
  if (typeof CanvasOverlayRegistry !== 'undefined') return CanvasOverlayRegistry.isOverlay(target, 'zoom-preview');
  return Boolean(target?.closest?.('.composer,.smart-back,.asset-panel,.asset-toggle,.style-panel,.style-toggle,.canvas-tool-dock,.canvas-bottom-tools,.canvas-agent-panel,.canvas-agent-toggle,.smart-log-toggle,.smart-shortcut-toggle,.log-modal,.shortcut-modal,.image-edit-modal,.create-menu,.smart-minimap'));
}
function isCanvasClickEmptyExcluded(target){
  // 第8步：空白点击清选中排除（含 .image-node=点节点不清选，原语义）
  if (typeof CanvasOverlayRegistry !== 'undefined') return CanvasOverlayRegistry.isOverlay(target, 'click-empty');
  return Boolean(target?.closest?.('.image-node,.composer,.smart-back,.canvas-tool-dock,.canvas-bottom-tools,.canvas-agent-panel,.canvas-agent-toggle,.smart-log-toggle,.smart-shortcut-toggle,.log-modal,.shortcut-modal,.image-edit-modal,.create-menu'));
}
function isCanvasOverlayTarget(target){
  // 第8步：统一浮层注册表判定（CanvasOverlayRegistry.register 一处声明全局生效）
  if (typeof CanvasOverlayRegistry !== 'undefined') return CanvasOverlayRegistry.isOverlay(target, 'overlay');
  return Boolean(target?.closest?.('.composer,.smart-back,.asset-panel,.asset-toggle,.style-panel,.style-toggle,.canvas-tool-dock,.canvas-bottom-tools,.canvas-agent-panel,.canvas-agent-toggle,.smart-log-toggle,.smart-shortcut-toggle,.log-modal,.shortcut-modal,.image-edit-modal,.create-menu,.smart-minimap,.smart-image-context-menu,#smartImageContextMenu'));
}
function isCanvasMiddlePanExcludedTarget(target){
  if (typeof CanvasOverlayRegistry !== 'undefined') return CanvasOverlayRegistry.isOverlay(target, 'pan-exclude');
  return Boolean(target?.closest?.('.smart-back,.asset-panel,.asset-toggle,.style-panel,.style-toggle,.canvas-tool-dock,.canvas-bottom-tools,.canvas-agent-panel,.canvas-agent-toggle,.smart-log-toggle,.smart-shortcut-toggle,.log-modal,.shortcut-modal,.image-edit-modal,.create-menu,.smart-minimap,.smart-image-context-menu,#smartImageContextMenu'));
}
function connectionIndexFromTarget(target){
    const index = Number(target?.closest?.('[data-conn-index]')?.dataset?.connIndex);
    return Number.isFinite(index) ? index : -1;
}
function connectionHitElementsAtClientPoint(clientX, clientY){
    if(typeof document.elementsFromPoint !== 'function') return [];
    return document.elementsFromPoint(clientX, clientY).filter(el => el?.closest?.('[data-conn-index]'));
}
// 2026-10-19 老王：连线剪断后，提示词里已经被 @ 引用的那一段降级为普通文本（@图片1），
// 不再是一条还能被引用/上传的引用（token 消失 = 上游拿不到这张图，就不能再引用）。
function degradeMentionTokenToText(token){
    if(!token) return '';
    const name = String(token.dataset.name || '').trim() || '图片';
    token.replaceWith(document.createTextNode(`@${name}`));
    return name;
}
function removeMentionTokensFromContainer(container, sourceIds, sourceUrls){
    if(!container || (!sourceIds?.size && !sourceUrls?.size)) return 0;
    let degraded = 0;
    container.querySelectorAll?.('.mention-image-token')?.forEach(token => {
        const nodeId = String(token.dataset.nodeId || '').trim();
        const url = String(token.dataset.url || '').trim();
        if((nodeId && sourceIds?.has(nodeId)) || (url && sourceUrls?.has(url))){
            degradeMentionTokenToText(token);
            degraded += 1;
        }
    });
    return degraded;
}
// 节点当前还能从活着的上游（连线 + 无线引用）拿到的图片地址集合
function liveInputUrlsForNode(node){
    const urls = new Set();
    if(!node) return urls;
    const collect = img => ['url','originalLocalUrl','sourceUrl','localUrl'].forEach(key => {
        const value = String(img?.[key] || '').trim();
        if(value) urls.add(value);
    });
    candidateInputImagesFor(node, false, smartLoopContext).forEach(collect);
    canvasObjectReferenceImages(node, smartLoopContext).forEach(collect);
    return urls;
}
// 兜底：有来源节点 id 的引用 token，若其图片已不在存活上游里（跨节点转发被剪断等），一律降级
function degradeStaleMentionTokensInContainer(container, node){
    if(!container || !node) return 0;
    const live = liveInputUrlsForNode(node);
    let degraded = 0;
    container.querySelectorAll?.('.mention-image-token')?.forEach(token => {
        const nodeId = String(token.dataset.nodeId || '').trim();
        const url = String(token.dataset.url || '').trim();
        if(nodeId && url && !live.has(url)){
            degradeMentionTokenToText(token);
            degraded += 1;
        }
    });
    return degraded;
}
function degradeStaleMentionTokensForNode(node){
    if(!node) return 0;
    let changed = 0;
    if(node.promptDraftHtml && promptHtmlHasMentionToken(node.promptDraftHtml)){
        const box = document.createElement('div');
        box.innerHTML = node.promptDraftHtml;
        if(degradeStaleMentionTokensInContainer(box, node)){
            node.promptDraftHtml = box.innerHTML;
            node.promptDraftText = box.innerText || box.textContent || '';
            changed += 1;
        }
    }
    if(promptInput && activeComposerNode()?.id === node.id){
        if(degradeStaleMentionTokensInContainer(promptInput, node)) changed += 1;
    }
    return changed;
}
function sourceUrlsForDisconnectedIds(sourceIds){
    const urls = new Set();
    sourceIds.forEach(id => {
        const source = nodes.find(n => n.id === id);
        imagesForNode(source).forEach(img => {
            const url = String(img?.url || '').trim();
            if(url) urls.add(url);
            const original = String(img?.originalLocalUrl || img?.sourceUrl || img?.localUrl || '').trim();
            if(original) urls.add(original);
        });
    });
    return urls;
}
function downstreamTargetsForDisconnectedTarget(targetId){
    const out = new Set();
    const walk = id => {
        if(!id || out.has(id)) return;
        out.add(id);
        (canvas?.connections || []).forEach(conn => {
            if(conn.from === id && ['input', 'flow'].includes(conn.kind || 'flow')) walk(conn.to);
        });
    };
    walk(targetId);
    return out;
}
function cleanPromptRefArraysForDisconnectedSource(node, sourceIds, sourceUrls){
    if(!node) return;
    const keep = ref => {
        const nodeId = String(ref?.nodeId || '').trim();
        const url = String(ref?.url || '').trim();
        if(nodeId && sourceIds.has(nodeId)) return false;
        if(url && sourceUrls.has(url)) return false;
        return true;
    };
    if(Array.isArray(node.runPromptRefs)) node.runPromptRefs = node.runPromptRefs.filter(keep);
    if(Array.isArray(node.runInputRefs)) node.runInputRefs = node.runInputRefs.filter(keep);
}
function cleanupPromptRefsForDisconnectedConnections(pairs=[]){
    if(!pairs.length) return;
    const sourcesByTarget = new Map();
    pairs.forEach(pair => {
        const from = String(pair?.from || '').trim();
        const to = String(pair?.to || '').trim();
        if(!from || !to) return;
        if(!sourcesByTarget.has(to)) sourcesByTarget.set(to, new Set());
        sourcesByTarget.get(to).add(from);
    });
    sourcesByTarget.forEach((sourceIds, targetId) => {
        const sourceUrls = sourceUrlsForDisconnectedIds(sourceIds);
        downstreamTargetsForDisconnectedTarget(targetId).forEach(affectedId => {
        const node = nodes.find(n => n.id === affectedId);
        cleanPromptRefArraysForDisconnectedSource(node, sourceIds, sourceUrls);
        if(node?.promptDraftHtml && promptHtmlHasMentionToken(node.promptDraftHtml)){
            const box = document.createElement('div');
            box.innerHTML = node.promptDraftHtml;
            if(removeMentionTokensFromContainer(box, sourceIds, sourceUrls)){
                node.promptDraftHtml = box.innerHTML;
                node.promptDraftText = box.innerText || box.textContent || '';
            }
        }
        if(activeComposerNode()?.id === affectedId && promptInput){
            if(removeMentionTokensFromContainer(promptInput, sourceIds, sourceUrls)) savePromptDraftForCurrent();
        }
        // 2026-10-19 老王：存活复验——剪断后依旧拿不到来源的引用一律降级为普通文本
        if(degradeStaleMentionTokensForNode(node) && activeComposerNode()?.id === affectedId) savePromptDraftForCurrent();
        });
    });
}
function refreshComposerAfterConnectionCut(pairs=[]){
    cleanupPromptRefsForDisconnectedConnections(pairs);
    const node = activeComposerNode() || selectedNode();
    if(!node) return;
    const affected = pairs.some(pair => pair?.to === node.id || pair?.from === node.id || downstreamTargetsForDisconnectedTarget(pair?.to).has(node.id));
    if(!affected) return;
    renderInputThumbsRow(node);
    renderInputPromptPreview(node);
}
function cutConnectionIndexes(indexes=[], {renderNow=true, saveNow=true, pushUndoSnapshot=true}={}){
    if(!canvas || !Array.isArray(canvas.connections) || !indexes.length) return 0;
    const unique = [...new Set(indexes.map(value => Number(value)).filter(Number.isFinite))].sort((a, b) => b - a);
    const valid = unique.filter(index => index >= 0 && index < canvas.connections.length);
    if(!valid.length) return 0;
    if(pushUndoSnapshot) pushUndo();
    const historyPairs = [];
    const disconnectedPairs = [];
    valid.forEach(index => {
        const conn = canvas.connections[index];
        if(!conn) return;
        const toNode = nodes.find(n => n.id === conn.to);
        if(toNode && Array.isArray(toNode.inputNodeIds)){
            toNode.inputNodeIds = toNode.inputNodeIds.filter(id => id !== conn.from);
        }
        if(['input', 'flow'].includes(conn.kind || 'flow')){
            disconnectedPairs.push({from:conn.from, to:conn.to, kind:conn.kind || 'flow'});
        }
        if((conn.kind || 'flow') === 'history'){
            historyPairs.push({from:conn.from, to:conn.to});
        }
        canvas.connections.splice(index, 1);
    });
    historyPairs.forEach(pair => {
        const group = nodes.find(n => n.id === pair.to && isHistoryGroupNode(n) && n.historyFor === pair.from);
        demoteHistoryGroupNode(group);
    });
    if(renderNow) render();
    refreshComposerAfterConnectionCut(disconnectedPairs);
    if(saveNow) scheduleSave();
    return valid.length;
}
/* ===== 划断连线手势（2026-10-17 老王：照 Blender 节点 Ctrl+右键切线重做）=====
 * 旧实现只对每个 pointermove 的“当前点”做一次 DOM 命中，鼠标事件间隔几十上百
 * 像素时，中间跨过的连线根本没被采样到 → “慢慢划才有效，快速一刀只断一根”。
 * 新实现把相邻两个鼠标位置连成一段，与连线的折线做线段×线段求交：刀口扫过
 * 的线一根不漏，划多快都算数。 */
function connCutBox(entry){
    if(entry.box) return entry.box;
    const c = entry.c;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for(let i = 0; i < 8; i += 2){
        if(c[i] < minX) minX = c[i];
        if(c[i] > maxX) maxX = c[i];
        if(c[i + 1] < minY) minY = c[i + 1];
        if(c[i + 1] > maxY) maxY = c[i + 1];
    }
    // 三次贝塞尔必在控制点凸包内 → 凸包 bbox 是安全上界，用它先粗筛
    entry.box = [minX, minY, maxX, maxY];
    return entry.box;
}
// 懒采样：把连线按 ~14px 世界距离折线化（长线多采几段，短线少采）
function connCutPolyline(entry){
    if(entry.pts) return entry.pts;
    const c = entry.c;
    const chord = Math.hypot(c[6] - c[0], c[7] - c[1]);
    const n = Math.max(4, Math.min(56, Math.ceil(chord / 14)));
    const pts = new Float64Array((n + 1) * 2);
    for(let i = 0; i <= n; i++){
        const t = i / n, mt = 1 - t;
        const a = mt * mt * mt, b = 3 * mt * mt * t, cc = 3 * mt * t * t, d = t * t * t;
        pts[i * 2] = a * c[0] + b * c[2] + cc * c[4] + d * c[6];
        pts[i * 2 + 1] = a * c[1] + b * c[3] + cc * c[5] + d * c[7];
    }
    entry.pts = pts;
    return pts;
}
function connCutSegsCross(ax, ay, bx, by, cx, cy, dx, dy){
    const r1 = bx - ax, r2 = by - ay, s1 = dx - cx, s2 = dy - cy;
    const den = r1 * s2 - r2 * s1;
    if(!den) return false;
    const ox = cx - ax, oy = cy - ay;
    const t = (ox * s2 - oy * s1) / den;
    if(t < 0 || t > 1) return false;
    const u = (ox * r2 - oy * r1) / den;
    return u >= 0 && u <= 1;
}
function connCutIntersectSegment(indexes, ax, ay, bx, by){
    const segMinX = Math.min(ax, bx), segMaxX = Math.max(ax, bx);
    const segMinY = Math.min(ay, by), segMaxY = Math.max(ay, by);
    connCutGeom.forEach((entry, index) => {
        if(indexes.has(index)) return;
        const box = connCutBox(entry);
        if(segMaxX < box[0] || segMinX > box[2] || segMaxY < box[1] || segMinY > box[3]) return;
        const pts = connCutPolyline(entry);
        const segs = pts.length / 2 - 1;
        let ax0 = pts[0], ay0 = pts[1];
        for(let i = 0; i < segs; i++){
            const bx0 = pts[i * 2 + 2], by0 = pts[i * 2 + 3];
            if(connCutSegsCross(ax, ay, bx, by, ax0, ay0, bx0, by0)){ indexes.add(index); return; }
            ax0 = bx0; ay0 = by0;
        }
    });
}
// 刀痕独立 SVG 层：连线层每次重渲会清空，刀痕必须活在不会被重建的层里
function cutTrailLayer(){
    let svg = world && world.querySelector('svg.cut-trail-layer');
    if(!svg && world){
        svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('class', 'cut-trail-layer');
        svg.setAttribute('width', '6000');
        svg.setAttribute('height', '4000');
        svg.setAttribute('viewBox', '0 0 6000 4000');
        svg.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
        world.appendChild(svg);
    }
    return svg;
}
function renderCutTrail(points){
    const layer = cutTrailLayer();
    if(!layer) return;
    if(!points || points.length < 2){
        if(layer.childNodes.length) layer.replaceChildren();
        return;
    }
    let path = layer.querySelector('path.conn-cut-trail');
    if(!path){
        path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('class', 'conn-cut-trail');
        layer.appendChild(path);
    }
    let d = `M${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)}`;
    for(let i = 1; i < points.length; i++) d += ` L${points[i].x.toFixed(1)} ${points[i].y.toFixed(1)}`;
    path.setAttribute('d', d);
}
// 刀口扫到的线即时标成金色（松手才真断，避免误切）——照 Blender 刀切线的红标
function markCutConnections(state){
    const svg = world && world.querySelector('svg.connection-layer:not(.connection-tools-layer)');
    if(!svg || !state) return;
    state.indexes.forEach(index => {
        svg.querySelector(`path[data-conn-line="${index}"]`)?.classList.add('cut-marked');
    });
}
function clearCutMarks(){
    world && world.querySelectorAll('svg.connection-layer path.cut-marked').forEach(el => el.classList.remove('cut-marked'));
}
function clearCutTrail(){
    const layer = world && world.querySelector('svg.cut-trail-layer');
    if(!layer) return;
    const path = layer.querySelector('path.conn-cut-trail');
    if(!path){ if(layer.childNodes.length) layer.replaceChildren(); return; }
    // 松手后刀痕短暂淡出，别硬切
    path.classList.add('fade');
    setTimeout(() => { if(path.isConnected) layer.replaceChildren(); }, 220);
}
// 刀跟着光标：划断时不再“停留 480ms 才出现”，而是立即跟手
function moveConnKnifeToClient(clientX, clientY){
    const g = world && world.querySelector('g.conn-scissor');
    if(!g) return;
    clearTimeout(connScissorHideTimer);
    clearTimeout(connScissorShowTimer);
    const scaleNow = safeScale(viewport.scale);
    const wp = screenToWorld({clientX, clientY});
    g.dataset.connIndex = '-1';
    g.setAttribute('transform', `translate(${wp.x.toFixed(1)} ${wp.y.toFixed(1)}) scale(${(1 / scaleNow).toFixed(4)})`);
    g.classList.add('show');
}
// 兜底收尾：capture 阶段先拿 mouseup，避免中途有 handler stopPropagation 把
// 事件拦在 window 之前（那样手势会卡住不结束）。finish 幂等，重复调用无副作用。
document.addEventListener('mouseup', e => {
    if(connectionCutState && e.button === 2) finishConnectionCutGesture();
}, true);
// 鼠标在窗口外松开时 mouseup 收不到 → 失焦即取消（不切任何线），别留着一直划
window.addEventListener('blur', () => {
    if(connectionCutState && typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.cancelActive();
});
function startConnectionCutGesture(event, initialIndex=-1){
    if(event){
        event.preventDefault();
        event.stopPropagation();
    }
 closeCreateMenu();
    const indexes = new Set();
    if(Number.isFinite(initialIndex) && initialIndex >= 0) indexes.add(initialIndex);
    const startW = event ? screenToWorld(event) : null;
    connectionCutState = {
        indexes,
        lastClientX:Number(event?.clientX || 0),
        lastClientY:Number(event?.clientY || 0),
        trail: startW ? [{x:startW.x, y:startW.y}] : []
    };
    if (typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.begin('cutting');
    shell.classList.add('cutting-connections');
    if(event) updateConnectionCutGesture(event);
}
function updateConnectionCutGesture(event){
    if(!connectionCutState) return;
    const state = connectionCutState;
    // 浏览器会把高频移动合并成一个事件，getCoalescedEvents() 能取回被合并掉的
    // 中间点——快速划刀时靠它把轨迹补完整（拿不到就退回单段，一样能求交）。
    const raw = [];
    if(typeof event?.getCoalescedEvents === 'function'){
        try{
            const co = event.getCoalescedEvents();
            if(co && co.length){
                for(const ce of co){
                    const x = Number(ce.clientX), y = Number(ce.clientY);
                    if(Number.isFinite(x) && Number.isFinite(y)) raw.push([x, y]);
                }
            }
        }catch(err){ /* 部分合成事件不支持，忽略即可 */ }
    }
    if(!raw.length){
        const x = Number(event?.clientX), y = Number(event?.clientY);
        if(Number.isFinite(x) && Number.isFinite(y)) raw.push([x, y]);
    }
    let prevX = state.lastClientX, prevY = state.lastClientY;
    let prevW = screenToWorld({clientX:prevX, clientY:prevY});
    for(const [cx, cy] of raw){
        const w = screenToWorld({clientX:cx, clientY:cy});
        // 关键：按“上一点→本点”整条线段求交，而不是只测当前点
        connCutIntersectSegment(state.indexes, prevW.x, prevW.y, w.x, w.y);
        const last = state.trail[state.trail.length - 1];
        if(!last || Math.hypot(w.x - last.x, w.y - last.y) > 1.5){
            state.trail.push({x:w.x, y:w.y});
            if(state.trail.length > CONN_CUT_TRAIL_MAX_POINTS) state.trail.shift();
        }
        prevX = cx; prevY = cy; prevW = w;
    }
    state.lastClientX = prevX;
    state.lastClientY = prevY;
    // 鼠标几乎没动、正压在某条线上时，补一次点命中（保留原来的手感）
    connectionHitElementsAtClientPoint(prevX, prevY).forEach(el => {
        const index = connectionIndexFromTarget(el);
        if(index >= 0) state.indexes.add(index);
    });
    moveConnKnifeToClient(prevX, prevY);
    renderCutTrail(state.trail);
    markCutConnections(state);
}
function finishConnectionCutGesture(){
    if(!connectionCutState) return false;
    shell.classList.remove('cutting-connections');
    shell.classList.remove('panning');
    const indexes = [...connectionCutState.indexes];
    connectionCutState = null;
    hideConnScissor();
    clearCutTrail();
    if (typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.end('cutting');
    // 有真切断时 renderNow 会重渲、标记自然消失；没切断（空划）则手动清
    setTimeout(clearCutMarks, 0);
    if(!indexes.length) return true;
    cutConnectionIndexes(indexes, {renderNow:true, saveNow:true, pushUndoSnapshot:true});
    return true;
}
function ensurePortDragPathElement(){
    const svg = world.querySelector('svg.connection-layer');
    if(!svg) return null;
    let path = svg.querySelector('path.port-drag-temp');
    if(!path){
        path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('class', 'port-drag-temp conn-pending');
        path.setAttribute('stroke', 'rgba(138,138,138,0.92)');
        path.setAttribute('stroke-width', '1.9');
        path.setAttribute('fill', 'none');
        path.setAttribute('stroke-linecap', 'round');
        svg.appendChild(path);
    }
    return path;
}
function clearPortDragVisual(){
    world.querySelector('path.port-drag-temp')?.remove();
    world.querySelectorAll('.node-port.is-active').forEach(el => el.classList.remove('is-active'));
    world.querySelectorAll('.image-node.port-hover').forEach(el => el.classList.remove('port-hover'));
    clearNodeBodyHover();
}
function bindPromptNodeControls(el,node){ return CanvasPromptNodeController.bind(el,node); }
function bindLoopNodeControls(el,node){ return CanvasLoopNodeController.bind(el,node); }
function bindScrollableText(el){
    if(!el || el.dataset.scrollBound === '1') return;
    el.dataset.scrollBound = '1';
    const stop = e => e.stopPropagation();
    const beginSelection = e => {
        e.stopPropagation();
        textSelectionGuard = {
            el,
            scrollTop:el.scrollTop || 0,
            scrollLeft:el.scrollLeft || 0,
            clientY:e.clientY,
            wheelUntil:0,
            active:true
        };
    };
    el.addEventListener('mousedown', beginSelection);
    el.addEventListener('mousemove', e => {
        e.stopPropagation();
        if(textSelectionGuard?.el === el) textSelectionGuard.clientY = e.clientY;
    });
    el.addEventListener('mouseup', e => {
        e.stopPropagation();
        if(textSelectionGuard?.el === el) textSelectionGuard.active = false;
    });
    el.addEventListener('mouseleave', e => {
        e.stopPropagation();
        if(textSelectionGuard?.el === el) {
            el.scrollTop = textSelectionGuard.scrollTop;
            el.scrollLeft = textSelectionGuard.scrollLeft;
        }
    });
    el.addEventListener('scroll', () => {
        const guard = textSelectionGuard;
        if(!guard || guard.el !== el || !guard.active || Date.now() < guard.wheelUntil) {
            if(guard?.el === el) {
                guard.scrollTop = el.scrollTop || 0;
                guard.scrollLeft = el.scrollLeft || 0;
            }
            return;
        }
        const nextTop = el.scrollTop || 0;
        const prevTop = guard.scrollTop || 0;
        const rect = el.getBoundingClientRect();
        const pointerBelow = Number.isFinite(guard.clientY) && guard.clientY > rect.bottom - 10;
        const pointerAbove = Number.isFinite(guard.clientY) && guard.clientY < rect.top + 10;
        const jumpedToTop = prevTop > Math.max(80, el.clientHeight * 0.45) && nextTop < 4 && !pointerAbove;
        const wrongDirectionJump = pointerBelow && nextTop < prevTop - Math.max(40, el.clientHeight * 0.25);
        if(jumpedToTop || wrongDirectionJump) {
            requestAnimationFrame(() => {
                if(textSelectionGuard?.el === el && textSelectionGuard.active) {
                    el.scrollTop = prevTop;
                    el.scrollLeft = guard.scrollLeft || 0;
                }
            });
            return;
        }
        guard.scrollTop = nextTop;
        guard.scrollLeft = el.scrollLeft || 0;
    }, {passive:true});
    el.addEventListener('click', stop);
    el.addEventListener('dblclick', stop);
    el.addEventListener('wheel', e => {
        e.stopPropagation();
        if(textSelectionGuard?.el === el) textSelectionGuard.wheelUntil = Date.now() + 180;
    }, {passive:true});
}
function updatePortDragVisual(){
    if(!portDragState) return;
    const fromNode = nodes.find(n => n.id === portDragState.fromId);
    if(!fromNode) return;
    const fr = nodeRect(fromNode);
    const isOut = portDragState.fromPort === 'out';
    const fx = isOut ? fr.x + fr.width : fr.x;
    const fy = fr.y + fr.height / 2;
    const tx = portDragState.currentWorld.x;
    const ty = portDragState.currentWorld.y;
    const dx = Math.max(50, Math.abs(tx - fx) * 0.45);
    const sign = isOut ? 1 : -1;
    const path = ensurePortDragPathElement();
    if(path) path.setAttribute('d', `M${fx} ${fy} C ${fx + dx * sign} ${fy}, ${tx - dx * sign} ${ty}, ${tx} ${ty}`);
    world.querySelectorAll('.node-port.is-active').forEach(el => el.classList.remove('is-active'));
    world.querySelectorAll('.image-node.port-hover').forEach(el => {
        if(el.dataset.id !== portDragState.hoverTargetId) el.classList.remove('port-hover');
    });
    if(portDragState.hoverTargetId){
        const targetNodeEl = world.querySelector(`.image-node[data-id="${portDragState.hoverTargetId}"]`);
        targetNodeEl?.classList.add('port-hover');
        targetNodeEl?.querySelector(`.node-port[data-port="${portDragState.hoverPort}"]`)?.classList.add('is-active');
    }
}
// ===== 2026-10-19 老王：+ 号命中裁决 =====
// 现象：端口命中区（84px 方块）整块伸出节点外，旁边的节点会盖在上面 → 鼠标在“+号区域”里命中的
// 是旁边节点（elementFromPoint 返回邻节点），于是亮的是邻节点的 +，你要那个节点的 + 根本不出现，
// 节点挨在一起时点不到、点错。修法：按“离哪个 + 号环最近”几何裁决，把该节点临时提到最前
// （.port-hover → z-index:7），这样显示与点击都落在你真正想要的 + 上。
// 2026-10-21 起此裁决仅用于拖线悬停（portDragState.hoverTargetId）；非拖线状态不再点亮
// 命中区——+ 只在节点身体内 / 选中 / 压在圆环上时可见（见 smart-canvas.css 显隐规则）。
function nodePortRingCenter(portEl){
    const r = portEl.getBoundingClientRect();
    return {x: r.left + r.width / 2, y: r.top + r.height / 2};
}
function clearNodePortHover(exceptNode=null){
    if(!world) return;
    world.querySelectorAll('.image-node.port-hover').forEach(el => {
        if(el !== exceptNode) el.classList.remove('port-hover');
    });
}
// 2026-10-21 老王：+ 号只在「鼠标在节点身体里」时显示（.body-hover）——端口命中区（84px）
// 整块伸出节点外、且默认 pointer-events:none，不算“在节点里”、也不会点亮任何 +。
// 用 elementFromPoint 取视觉最顶层元素，命中落在 .node-port（圆环）上时由 CSS :hover 兜底亮。
function nodeBodyAtClientPoint(clientX, clientY){
    const hit = document.elementFromPoint(clientX, clientY);
    if(!hit || typeof hit.closest !== 'function') return null;
    return hit.closest('.image-node');
}
function clearNodeBodyHover(exceptNode=null){
    if(!world) return;
    world.querySelectorAll('.image-node.body-hover').forEach(el => {
        if(el !== exceptNode) el.classList.remove('body-hover');
    });
}
function syncNodePortHoverFromPointer(clientX, clientY){
    if(portDragState) return;   // 拖线中由原逻辑管（目标是落点节点）
    if(!world) return;
    if(document.body.classList.contains('smart-node-drag')){
        // 拖节点中不点亮任何 +（与“拖动时清场”的旧意图一致）
        clearNodePortHover();
        clearNodeBodyHover();
        return;
    }
    // 鼠标真在哪个节点身体里 → 只亮它；命中落在端口圆环上时 CSS .node-port:hover 单独亮那一个
    const bodyNode = nodeBodyAtClientPoint(clientX, clientY);
    clearNodeBodyHover(bodyNode || null);
    if(bodyNode) bodyNode.classList.add('body-hover');
}
// The hit area stays still; only the visible plus follows the pointer inside it.
world.addEventListener('mousemove', event => {
    const port = event.target.closest?.('.node-port');
    if(!port) return;
    const rect = port.getBoundingClientRect();
    if(!rect.width || !rect.height) return;
    const x = Math.max(15, Math.min(69, (event.clientX - rect.left) / rect.width * 84));
    const y = Math.max(15, Math.min(69, (event.clientY - rect.top) / rect.height * 84));
    port.style.setProperty('--port-x', `${x}px`);
    port.style.setProperty('--port-y', `${y}px`);
}, true);
world.addEventListener('mouseout', event => {
    const port = event.target.closest?.('.node-port');
    if(!port || port.contains(event.relatedTarget)) return;
    port.style.removeProperty('--port-x');
    port.style.removeProperty('--port-y');
}, true);
// 鼠标在节点身体里的移动 → 维护 .body-hover；端口圆环自身可 hover（CSS pointer-events:auto），
// 压在圆环上时由 .node-port:hover 单独亮那一个，不需要 JS 参与。离开世界即全清。
world.addEventListener('mousemove', event => syncNodePortHoverFromPointer(event.clientX, event.clientY), true);
world.addEventListener('mouseleave', () => { clearNodePortHover(); clearNodeBodyHover(); });
// ===== 拖线落空 → 选节点类型（createMenu 复用） =====
// 菜单里 8 张卡对应的节点类型。判定"能不能接"要按连线方向分开看：
//  - 往下游接（fromPort==='out'，新节点是终点）：新节点得有能吃这个输入的口子
//  - 往上游接（fromPort==='in'，新节点是起点）：新节点得出得了东西给下游
const PORT_DROP_CREATE_TYPES = {
    image:     {nodeType:'smart-image',  labelKey:null},
    speech:    {nodeType:'smart-speech', labelKey:null},
    prompt:    {nodeType:'smart-prompt', labelKey:null},
    loop:      {nodeType:'smart-loop',   labelKey:null},
    generator: {nodeType:'smart-image',  labelKey:null},
    video:     {nodeType:'smart-image',  labelKey:null},
    rh:        {nodeType:'smart-image',  labelKey:null},
    comfy:     {nodeType:'smart-image',  labelKey:null}
};
// 拖的是输入口（反向拖）时，提示词节点才是合理的上游；拖输出口时它自己没输入口，接不了
function portDropTypeDisabledReason(type, drag){
    const meta = PORT_DROP_CREATE_TYPES[type];
    if(!meta) return '';
    if(!drag) return '';
    const ports = canvasNodePorts({type:meta.nodeType});
    if(drag.fromPort === 'out'){
        // 新节点要当终点：没有输入口就接不了
        if(!(ports.inputs || []).length) return tr('smart.portDropNoInput');
        // 循环节点只吃图片/提示词，源节点不是这两类就白建
        if(meta.nodeType === 'smart-loop'){
            const source = nodes.find(n => n.id === drag.fromId);
            const looksImage = source ? (isSmartImageNode(source) || isCanvasGroupNode(source) || (source.type === 'smart-loop' && source.imageInput)) : false;
            const looksPrompt = source ? (source.type === 'smart-prompt' || (source.type === 'smart-loop' && source.showPrompt)) : false;
            if(!looksImage && !looksPrompt) return tr('smart.portDropLoopNeedsImage');
        }
        return '';
    }
    // 新节点要当起点：没有输出口就供不了下游
    if(!(ports.outputs || []).length) return tr('smart.portDropNoOutput');
    return '';
}
function refreshCreateMenuAvailability(){
    if(!createMenu) return;
    createMenu.querySelectorAll('[data-create-type]').forEach(card => {
        const reason = pendingPortDrop ? portDropTypeDisabledReason(card.dataset.createType || '', pendingPortDrop.drag) : '';
        card.classList.toggle('is-disabled', Boolean(reason));
        card.disabled = Boolean(reason);
        if(reason){
            card.dataset.disabledReason = reason;
            card.title = reason;
        } else {
            delete card.dataset.disabledReason;
            card.removeAttribute('title');
        }
    });
}
function cancelPendingPortDrop(){
    if(!pendingPortDrop) return false;
    pendingPortDrop = null;
    discardPendingUndo();
    return true;
}
// 菜单定位在落点旁；菜单 520px 宽，优先放右侧，放不下翻到左侧，再夹进视口
function placeCreateMenuNear(clientX, clientY){
    if(!createMenu) return;
    const w = 520;
    const h = 460;
    const gap = 16;
    let left = clientX + gap;
    if(left + w > window.innerWidth - gap) left = clientX - w - gap;
    left = Math.max(gap, Math.min(left, window.innerWidth - w - gap));
    const top = Math.max(gap, Math.min(clientY - 24, window.innerHeight - h - gap));
    createMenu.style.left = `${left}px`;
    createMenu.style.top = `${top}px`;
}
function openPortDropTypeMenu(drag, worldPoint, dropGroupId, e){
    createMenuPoint = {x:worldPoint.x, y:worldPoint.y};
    // mousedown 时 capture 的"拖线前"快照在这里作废：用户可能停留很久才选，
    // 期间任何自动保存/其它编辑都会让它过期。撤销改由各 create*Node 自己 pushUndo 负责
    // （它们都是"先 push 快照再加节点"，撤销正好回到拖线前的状态）。
    discardPendingUndo();
    pendingPortDrop = {
        drag,
        point:{x:worldPoint.x, y:worldPoint.y},
        dropGroupId: dropGroupId || ''
    };
    placeCreateMenuNear(e?.clientX ?? window.innerWidth / 2, e?.clientY ?? window.innerHeight / 2);
    createMenu.classList.add('open');
    refreshCreateMenuAvailability();
    refreshIcons();
}
// 用户在菜单里选完类型后：真正建节点 + 接上刚才那条线
function finishPendingPortDrop(pending, node){
    if(!pending || !node) return false;
    if(pendingPortDrop === pending) pendingPortDrop = null;
    const dropGroup = nodes.find(n => n.id === pending.dropGroupId) || CanvasNodeGestureController.canvasGroupDropTargetFor(node);
    if(dropGroup) CanvasNodeGestureController.addNodeToCanvasGroup(node, dropGroup);
    const drag = pending.drag;
    const toId = drag.fromPort === 'out' ? node.id : drag.fromId;
    const sourceIds = drag.fromPort === 'out' ? selectedPortDragSourceIds(drag) : [node.id];
    const connected = connectSelectedNodesToTarget(sourceIds, toId) > 0;
    if(!connected) toast(tr('smart.portDropConnectFailed'));
    render();
    scheduleSave();
    return true;
}
// 拖线落空开菜单后，浏览器仍会为同一次手势派发 click / mousedown（mouseup 之后）。
// 若不拦，shell.onclick → closeCreateMenu 会把刚开的菜单立刻关掉、pendingPortDrop 被清，
// 表现为"菜单闪一下就没了"。这里开一个一次性闸门吞掉紧随其后的那一次 mousedown + click。
let portDropClickGuardUntil = 0;
function armPortDropClickGuard(){
    portDropClickGuardUntil = Date.now() + 400;
}
function portDropClickGuardActive(){
    return Date.now() < portDropClickGuardUntil;
}
function handlePortDrop(drag, e){
    const {targetId, targetPort, hit, dropGroupId} = (() => {
        const hitEl = document.elementFromPoint(e.clientX, e.clientY);
        const portEl = hitEl?.closest?.('.node-port');
        const nodeEl = portEl?.closest?.('.image-node') || hitEl?.closest?.('.image-node');
        let id = '', port = '';
        let groupId = '';
        if(nodeEl && nodeEl.dataset.id && nodeEl.dataset.id !== drag.fromId){
            const hitNode = nodes.find(n => n.id === nodeEl.dataset.id);
            if(isCanvasGroupNode(hitNode) && !portEl){
                groupId = hitNode.id;
            } else {
                id = nodeEl.dataset.id;
            }
            if(portEl){
                port = portEl.dataset.port;
            } else if(id) {
                const rect = nodeEl.getBoundingClientRect();
                port = (e.clientX - rect.left) < rect.width / 2 ? 'in' : 'out';
            }
        }

        return {targetId:id, targetPort:port, hit:hitEl, dropGroupId:groupId};
    })();
    if(targetId){
        const compatible = (drag.fromPort === 'out' && targetPort === 'in') || (drag.fromPort === 'in' && targetPort === 'out');
        if(!compatible){ discardPendingUndo(); render(); return; }
        const toId = drag.fromPort === 'out' ? targetId : drag.fromId;
        const sourceIds = drag.fromPort === 'out' ? selectedPortDragSourceIds(drag) : [targetId];
        if(connectSelectedNodesToTarget(sourceIds, toId) > 0){
            commitPendingUndo();
            render();
            scheduleSave();
        } else {
            discardPendingUndo();
            render();
        }
        return;
    }
    if(!drag.moved){ discardPendingUndo(); render(); return; }
    if(hit?.closest?.('.composer,.smart-back,.asset-panel,.asset-toggle,.style-panel,.style-toggle,.canvas-tool-dock,.canvas-bottom-tools,.canvas-agent-panel,.canvas-agent-toggle,.smart-log-toggle,.smart-shortcut-toggle,.log-modal,.shortcut-modal,.image-edit-modal,.smart-minimap')){
        discardPendingUndo(); render(); return;
    }
    const p = screenToWorld(e);
    // 拖线落空不再写死建万能节点：挂起这次连线意图，弹节点类型菜单让用户选。
    // 选中后由 createNodeFromMenu → finishPendingPortDrop 真正建节点 + 连线。
    openPortDropTypeMenu(drag, p, dropGroupId, e);
    armPortDropClickGuard();
    render();
}
function pickMediaForSmartNode(nodeId){
    const _pickNode = nodes.find(n => n.id === nodeId);
    if(_pickNode) delete _pickNode.retainOutputNames;
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*,video/*,audio/*';
    input.multiple = true;
        input.onchange = () => {
            if(input.files?.length) handleFiles(input.files, nodeId, {replaceIfExists:true});
            input.remove();
        };
    input.style.position = 'fixed';
    input.style.left = '-9999px';
    input.style.top = '-9999px';
    input.style.opacity = '0';
    document.body.appendChild(input);
    input.click();
}
// 已移除：右键「替换素材」画廊(openInCanvasReplaceGallery)、replaceMediaForSmartNode、revertMediaVersion
// 原因：用户反馈画布内替换画廊太卡，2026-09-27 删除。本地上传仍由 upload-node-btn → pickMediaForSmartNode 提供。

// redirect-lines 域外移 canvas-redirect-lines.js（第九刀），redirectPickMode 随域自持。
if(globalThis.CanvasRedirectLines){CanvasRedirectLines.configure({
        pushUndo: (...a) => pushUndo(...a),
        render: (...a) => render(...a),
        scheduleSave: (...a) => scheduleSave(...a),
        toast: (...a) => toast(...a),
        canvas: () => canvas,
        nodes: () => nodes,
        world: () => world
});}
function enterRedirectPickMode(){return CanvasRedirectLines.enterRedirectPickMode.apply(null, arguments);}
function exitRedirectPickMode(){return CanvasRedirectLines.exitRedirectPickMode.apply(null, arguments);}
function applyMoveLinesToNewSource(){return CanvasRedirectLines.applyMoveLinesToNewSource.apply(null, arguments);}

function bindNodeEvents(){
    // 只有本轮刚创建的节点需要绑定；HTML 未变化的节点沿用已有监听器
    const stamp = String(nodeRenderStamp);
    // 建一次索引，避免每个节点都做一次 nodes.find（O(n²) → O(n)）
    const nodeIndex = new Map(nodes.map(n => [n.id, n]));
    world.querySelectorAll('.image-node').forEach(el => {
        if(el.dataset.renderStamp !== stamp) return;
        const id = el.dataset.id;
        const nodeForControls = nodeIndex.get(id);
        if(nodeForControls?.type === 'smart-prompt') bindPromptNodeControls(el, nodeForControls);
        if(nodeForControls?.type === 'smart-loop') bindLoopNodeControls(el, nodeForControls);
        if(nodeForControls?.type === 'smart-speech') CanvasSpeech.bind(el, nodeForControls);
        CanvasNodeActionController.bind(el,id);
        CanvasNodeMediaActions.bind(el,id);
        CanvasImageNodeInteractions.bindItems(el,id);
        CanvasNodeGestureController.bind(el,id);
        CanvasPortGestureController.bind(el,id);
    });
}
function deleteNode(id){ return CanvasNodeDeletionController.deleteNodes([id]); }
function keyboardDeleteCandidateNodeIds(){
    return CanvasNodeDeletionController.candidateNodeIds();
}
function deleteSelectedNodesFromKeyboard(event=null){
    return CanvasNodeDeletionController.deleteSelectedNodesFromKeyboard(event);
}
function isDeleteShortcut(event){
    return CanvasNodeDeletionController.isDeleteShortcut(event);
}
function deleteNodeFromButton(id){
    return CanvasNodeDeletionController.deleteNodeFromButton(id);
}
function disconnectConnection(index){
    cutConnectionIndexes([index], {renderNow:true, saveNow:true, pushUndoSnapshot:true});
}
function connectionMidpoint(conn){
    const fromNode = nodes.find(n => n.id === conn?.from);
    const toNode = nodes.find(n => n.id === conn?.to);
    if(!fromNode || !toNode) return null;
    const fr = nodeRect(fromNode), tr = nodeRect(toNode);
    if((conn.kind || 'flow') === 'history'){
        return {x:(fr.x + fr.width / 2 + tr.x + tr.width / 2) / 2, y:(fr.y + fr.height + tr.y) / 2};
    }
    return {x:(fr.x + fr.width + tr.x) / 2, y:(fr.y + fr.height / 2 + tr.y + tr.height / 2) / 2};
}
function insertionConnectionForNode(node){
    if(!node || node.type !== 'smart-loop' || !canvas?.connections?.length) return null;
    const r = nodeRect(node);
    const cx = (Number(r.x) || 0) + (Number(r.width) || 0) / 2;
    const cy = (Number(r.y) || 0) + (Number(r.height) || 0) / 2;
    let best = null;
    (canvas.connections || []).forEach((conn, index) => {
        const kind = conn.kind || 'flow';
        if(!['input','flow'].includes(kind)) return;
        if(conn.from === node.id || conn.to === node.id) return;
        const fromNode = nodes.find(n => n.id === conn.from);
        const toNode = nodes.find(n => n.id === conn.to);
        if(!fromNode || !toNode || isHistoryGroupNode(fromNode) || isHistoryGroupNode(toNode)) return;
        const mid = connectionMidpoint(conn);
        if(!mid) return;
        const score = Math.hypot(cx - mid.x, cy - mid.y);
        if(score > 96) return;
        if(!best || score < best.score) best = {conn, index, score};
    });
    return best;
}
function insertLoopNodeIntoConnection(loopNode, hit){
    if(!loopNode || loopNode.type !== 'smart-loop' || !hit?.conn) return false;
    const conn = hit.conn;
    const kind = conn.kind || 'flow';
    canvas.connections = (canvas.connections || []).filter((c, index) => index !== hit.index);
    nodes.forEach(n => {
        if(Array.isArray(n.inputNodeIds)) n.inputNodeIds = n.inputNodeIds.filter(id => !(n.id === conn.to && id === conn.from));
    });
    addConnection(conn.from, loopNode.id, kind === 'flow' ? 'flow' : 'input');
    connectInputNode(loopNode.id, conn.to);
    return true;
}
function updateLoopInsertPreview(){
    const node = dragState ? nodes.find(n => n.id === dragState.id) : null;
    const next = node?.type === 'smart-loop' && dragState.ctrlGroup && (dragState.group || []).length <= 1
        ? insertionConnectionForNode(node)
        : null;
    const nextPreview = next ? {index:next.index} : null;
    const changed = (loopInsertPreview?.index ?? -1) !== (nextPreview?.index ?? -1);
    loopInsertPreview = nextPreview;
    if(changed) scheduleConnectionLayerRefresh();
    return next;
}
function deleteImage(id, imageIndex){
    const _imgNode = nodes.find(n => n.id === id);
    if(_imgNode) delete _imgNode.retainOutputNames;
    const node = nodes.find(n => n.id === id);
    if(!node || imageIndex < 0) return;
    pushUndo();
    node.images = (node.images || []).filter((_, index) => index !== imageIndex);
    if(node.images.length <= 1) node.title = 'Image';
    if(canvasUiState.selection.image.nodeId === id) canvasUiState.patchSelection({image: {nodeId:id, index:Math.min(canvasUiState.selection.image.index, node.images.length - 1)}}, 'selectedImage');
    if(canvasUiState.selection.image.index < 0) canvasUiState.patchSelection({image: {nodeId:'', index:-1}}, 'selectedImage');
    render();
    scheduleSave();
}
function currentEditImage(){
    const node = nodes.find(n => n.id === cropState?.nodeId);
    const index = Number(cropState?.imageIndex || 0);
    return {node, index, image:imageForDisplay(node?.images?.[index])};
}
function cropImageDisplaySize(){
    return CanvasImageEditViewportController.displaySize();
}
function cropBounds(){
    return CanvasImageEditViewportController.bounds();
}
function editDrawCanvas(){ return document.getElementById('editDrawCanvas'); }
function editTextCanvas(){ return document.getElementById('editTextCanvas'); }
function editTextContext(){ return editTextCanvas()?.getContext('2d') || null; }
function selectedEditTextItem(){ return CanvasImageEditTextController.selectedItem(); }
function defaultEditTextText(){ return CanvasImageEditTextController.defaultText(); }
function editTextSizeFromBrush(){ return CanvasImageEditTextController.sizeFromBrush(); }
function createEditTextItem(text, point, preset={}){ return CanvasImageEditTextController.createItem(text, point, preset); }
function textItemFont(item){ return CanvasImageEditTextController.itemFont(item); }
function measureEditTextItem(item, ctx=editTextContext()){ return CanvasImageEditTextController.measure(item, ctx); }
function hitEditTextItem(point){ return CanvasImageEditTextController.hit(point); }
function renderEditTextCanvas(){ return CanvasImageEditTextController.render(); }
function syncTextToolState(){ return CanvasImageEditTextController.syncToolState(); }
function syncSelectedEditTextStyleFromBrush(){ return CanvasImageEditTextController.syncSelectedStyleFromBrush(); }
function beginTextEditChange(){ return CanvasImageEditTextController.beginChange(); }
function setSelectedEditTextItem(id){ return CanvasImageEditTextController.setSelected(id); }
function confirmSelectedEditTextItem(){ return CanvasImageEditTextController.confirmSelected(); }
function editTextCanvasScale(){ return CanvasImageEditTextController.canvasScale(); }
function positionEditTextInlineEditor(){ return CanvasImageEditTextController.positionInlineEditor(); }
function removeEditTextInlineEditor(commit=true){ return CanvasImageEditTextController.removeInlineEditor(commit); }
function beginEditTextInline(item){ return CanvasImageEditTextController.beginInline(item); }
function editTextPoint(event){ return editDrawPoint(event); }
function beginEditText(event){ return CanvasImageEditTextController.begin(event); }
function updateEditTextCursor(event){ return CanvasImageEditTextController.updateCursor(event); }
function moveEditText(event){ return CanvasImageEditTextController.move(event); }
function endEditText(event){ return CanvasImageEditTextController.end(event); }
function editTextHasContent(){ return CanvasImageEditTextController.hasContent(); }
function resizeEditTextCanvas(){
    const img = document.getElementById('cropImage');
    const canvasEl = editTextCanvas();
    if(!img || !canvasEl) return;
    const display = cropImageDisplaySize();
    const w = Math.max(1, img.naturalWidth || img.clientWidth || 1);
    const h = Math.max(1, img.naturalHeight || img.clientHeight || 1);
    if(canvasEl.width !== w) canvasEl.width = w;
    if(canvasEl.height !== h) canvasEl.height = h;
    canvasEl.style.width = `${display.w}px`;
    canvasEl.style.height = `${display.h}px`;
    renderEditTextCanvas();
}
function resizeEditDrawCanvas(){
    const img = document.getElementById('cropImage');
    const canvasEl = editDrawCanvas();
    const display = cropImageDisplaySize();
    const w = Math.max(1, img.naturalWidth || img.clientWidth || 1);
    const h = Math.max(1, img.naturalHeight || img.clientHeight || 1);
    if(canvasEl.width !== w || canvasEl.height !== h){ canvasEl.width = w; canvasEl.height = h; }
    canvasEl.style.width = `${display.w}px`;
    canvasEl.style.height = `${display.h}px`;
    resizeEditTextCanvas();
    if(imageEditMode === 'grid') refreshGridSplitPreview();
}
CanvasImageGridSplitController.configure({
    getDrawCanvas: () => editDrawCanvas(),
    getCropCanvas: () => document.getElementById('cropCanvas'),
    getEditorMode: () => imageEditMode,
    getGridSettings: () => gridSplitSettings(),
    getRawGap: () => document.getElementById('gridGapSize')?.value,
    translate: key => tr(key)
});
CanvasImagePanoramaRenderer.configure({
    getCanvas: () => document.getElementById('panoramaCanvas'),
    getStage: () => document.getElementById('panoramaStage'),
    getViewState: () => panoramaState,
    getFallbackSource: () => panoramaFallbackSource(),
    onReady: () => { resizePanoramaViewer(); startPanoramaLoop(); },
    toast: message => toast(message),
    translate: key => tr(key)
});
CanvasImagePreviewCompareController.configure({
    getEditing: () => currentEditImage(),
    getNodes: () => nodes,
    getInputImages: node => inputImagesFor(node),
    mediaKindForItem: image => mediaKindForItem(image),
    syncFrameSize: () => syncPreviewFrameSize(),
    updateMetaHint: text => updatePreviewMetaHint(text),
    translate: key => tr(key),
    escapeHtml: value => escapeHtml(value),
    toast: message => toast(message)
});
CanvasImagePreviewTransformController.configure({
    getFrame: () => document.getElementById('previewFrame'),
    isPanoramaEnabled: () => panoramaState.enabled,
    updateZoomLabel: () => updateZoomLabel()
});
CanvasImagePreviewDownloadController.configure({
    getNavigation: () => previewNavState,
    getNodes: () => nodes,
    safeExportFileName: (...args) => safeExportFileName(...args),
    downloadNameForMediaItem: (...args) => downloadNameForMediaItem(...args),
    toast: message => toast(message)
});
CanvasImagePreviewMediaController.configure({
    getEditing: () => currentEditImage(),
    isModalOpen: () => imageEditModal.classList.contains('open'),
    getCurrentImage: () => document.getElementById('previewCurrentImage'),
    getCurrentVideo: () => document.getElementById('previewCurrentVideo'),
    getCropImage: () => document.getElementById('cropImage'),
    getMetaHint: () => document.getElementById('previewMetaHint'),
    getPanoramaToggle: () => document.getElementById('panoramaToggleBtn'),
    isPanoramaEnabled: () => panoramaState.enabled,
    getLoadToken: () => previewLoadToken,
    displayMediaUrl: item => displayMediaUrl(item),
    proxiedMediaUrl: item => proxiedMediaUrl(item),
    syncFrameSize: () => syncPreviewFrameSize(),
    requestAnimationFrame: callback => requestAnimationFrame(callback),
    mediaKindForItem: image => mediaKindForItem(image),
    translate: key => tr(key),
    scheduleSave: () => scheduleSave()
});
CanvasImagePreviewInteractionController.configure({
    isModalOpen: () => imageEditModal.classList.contains('open'),
    getMode: () => imageEditMode,
    isPanoramaEnabled: () => panoramaState.enabled,
    getPanoramaState: () => panoramaState,
    seekVideoFrames: direction => seekPreviewVideoFrames(direction),
    lockRootScroll: () => lockSmartCanvasRootScroll(),
    updateZoomLabel: () => updateZoomLabel(),
    zoomAt: (...args) => CanvasImagePreviewTransformController.zoomAt(...args)
});
const previewTransformState = CanvasImagePreviewTransformController.getState();
['three','renderer','scene','camera','sphere','texture','threeLoadPromise','image','animationId','loadedSrc','loadToken'].forEach(key => {
    Object.defineProperty(panoramaState, key, {enumerable:true, get:() => CanvasImagePanoramaRenderer.getState()[key]});
});
window.__smartCanvasPanoramaState = panoramaState;
CanvasImageEditViewportController.configure({
    getImage: () => document.getElementById('cropImage'),
    getDrawCanvas: () => editDrawCanvas(),
    getTextCanvas: () => editTextCanvas(),
    getStage: () => document.getElementById('imageEditStage'),
    getCropCanvas: () => document.getElementById('cropCanvas'),
    getCropBox: () => document.getElementById('cropBox'),
    getOutpaintFrame: () => document.getElementById('outpaintFrame'),
    getOutpaintResolution: () => document.getElementById('outpaintResolution'),
    getZoomLabel: () => document.getElementById('imageEditZoomLabel'),
    getMode: () => imageEditMode,
    getCropState: () => cropState,
    getWindowSize: () => ({width:window.innerWidth,height:window.innerHeight}),
    getPreviewZoom: () => previewTransformState.zoom,
    getPanorama: () => panoramaState,
    resizeDrawCanvas: () => resizeEditDrawCanvas(),
    clampCrop: () => clampCrop(),
    refreshGridSplitPreview: () => refreshGridSplitPreview(),
    exceedsFourKStandard: (width,height) => exceedsFourKStandard(width,height),
    resetPanoramaView: () => resetPanoramaView(),
    resetPreviewTransform: () => resetPreviewTransform()
});
CanvasImageEditDrawingController.configure({
    getCanvas: () => editDrawCanvas(),
    getMode: () => imageEditMode,
    getGridController: () => CanvasImageGridSplitController,
    getElementById: id => document.getElementById(id),
    removeInlineEditor: (...args) => removeEditTextInlineEditor(...args),
    syncTextToolState: (...args) => syncTextToolState(...args),
    pushHistory: () => pushEditDrawHistory(),
    snapshot: () => editDrawSnapshot(),
    restoreSnapshot: value => restoreEditDrawSnapshot(value),
    syncGridUndoButton: () => syncGridCustomUndoBtn(),
    refreshGridPreview: () => refreshGridSplitPreview(),
    syncHistoryButtons: () => syncEditDrawingHistoryButtons()
});
CanvasImageEditTextController.configure({
    getCanvas: () => editTextCanvas(),
    getCropCanvas: () => document.getElementById('cropCanvas'),
    getMode: () => imageEditMode,
    getBrushTool: () => CanvasImageEditDrawingController.getTool(),
    getBrushSize: () => CanvasImageEditDrawingController.brushSize(),
    getBrushColor: () => CanvasImageEditDrawingController.brushColor(),
    getDefaultText: () => window.StudioI18n?.lang?.() === 'en' ? 'Double-click to edit' : '双击编辑',
    getPoint: event => editDrawPoint(event),
    createId: () => uid('txt'),
    pushHistory: () => pushEditDrawHistory()
});
CanvasImageEditDrawingHistoryController.configure({
    getDrawCanvas: () => editDrawCanvas(),
    getTextCanvas: () => editTextCanvas(),
    getTextItems: () => CanvasImageEditTextController.getItems(),
    setTextItems: value => CanvasImageEditTextController.setItems(value),
    getSelectedTextId: () => CanvasImageEditTextController.getSelectedId(),
    setSelectedTextId: value => CanvasImageEditTextController.setSelectedId(value),
    getLabelCounter: () => CanvasImageEditDrawingController.getLabelCounter(),
    setLabelCounter: value => CanvasImageEditDrawingController.setLabelCounter(value),
    removeInlineEditor: value => CanvasImageEditTextController.removeInlineEditor(value),
    renderTextCanvas: () => CanvasImageEditTextController.render(),
    syncTextToolState: () => CanvasImageEditTextController.syncToolState(),
    resetTextInteraction: () => CanvasImageEditTextController.resetInteraction(),
    hasContent: () => editCanvasHasPixels()
});
CanvasImageEditorModeController.configure({
    getEditKind: () => mediaKindForItem(currentEditImage().image || {}),
    getMode: () => imageEditMode,
    setMode: value => { imageEditMode = value; },
    markModeTouched: () => { imageEditModeTouched = true; },
    isPanoramaEnabled: () => panoramaState.enabled,
    previewDownloadGroupCount: () => previewDownloadGroupItems().length,
    removeEditTextInlineEditor: (...args) => removeEditTextInlineEditor(...args),
    bindPreviewWheelListeners: () => bindPreviewWheelListeners(),
    disposePanoramaPreview: () => disposePanoramaPreview(),
    translate: key => tr(key),
    syncGridCustomCursor: () => syncGridCustomCursor(),
    syncGridGapValue: () => syncGridGapValue(),
    refreshComparePanel: () => refreshComparePanel(),
    ensureImageEditBaseSize: (...args) => ensureImageEditBaseSize(...args),
    applyImageEditZoom: () => applyImageEditZoom(),
    resetCropBox: () => resetCropBox(),
    resetOutpaintBox: () => resetOutpaintBox(),
    syncImageEditOverflow: () => syncImageEditOverflow(),
    resizeEditDrawCanvas: () => resizeEditDrawCanvas(),
    refreshGridSplitPreview: () => refreshGridSplitPreview(),
    clearEditDrawing: (...args) => clearEditDrawing(...args),
    syncEditDrawingHistoryButtons: () => syncEditDrawingHistoryButtons(),
    syncBrushToolButtons: () => syncBrushToolButtons(),
    syncTextToolState: (...args) => syncTextToolState(...args),
    refreshIcons: () => refreshIcons()
});
function setImageEditMode(mode, userTouched=false){
    return CanvasImageEditorModeController.setMode(mode, userTouched);
}
let previewLoadToken = 0;
const previewCompareState = {};
Object.defineProperties(previewCompareState, {
    active:{get:() => CanvasImagePreviewCompareController.getState().active, set:value => CanvasImagePreviewCompareController.setActive(value)},
    index:{get:() => CanvasImagePreviewCompareController.getState().index, set:value => CanvasImagePreviewCompareController.setIndex(value)}
});
function applyPreviewTransform(){
    return CanvasImagePreviewTransformController.apply();
}
function resetPreviewTransform(){
    CanvasImagePreviewTransformController.reset();
    previewComparePos = 50;
    document.getElementById('previewStage')?.style.setProperty('--compare-pos', `${previewComparePos}%`);
}
function panoramaRatioValue(){
    const preset = PANORAMA_RATIO_PRESETS[panoramaState.ratio];
    if(preset) return preset;
    return {
        w:Math.max(1, Number(panoramaState.customW) || 16),
        h:Math.max(1, Number(panoramaState.customH) || 9)
    };
}
function panoramaResolutionValue(){
    const longSide = 1536;
    const ratio = panoramaRatioValue();
    const aspect = ratio.w / Math.max(1, ratio.h);
    if(aspect >= 1){
        return {w:longSide, h:Math.max(1, Math.round(longSide / aspect))};
    }
    return {w:Math.max(1, Math.round(longSide * aspect)), h:longSide};
}
function panoramaSource(){
    const editing = currentEditImage();
    const image = editing.image || {};
    if(mediaKindForItem(image) !== 'image') return '';
    return displayMediaUrl(image.url ? image : (image.url || ''));
}
function panoramaFallbackSource(){
    const image = currentEditImage().image || {};
    return image?.url ? proxiedMediaUrl(image) : '';
}
function isLikelyPanoramaImage(node, image, naturalW=0, naturalH=0){
    if(mediaKindForItem(image || {}) !== 'image') return false;
    const text = [
        image?.name,
        image?.title,
        node?.title,
        node?.runPrompt,
        node?.runModelPrompt,
        node?.promptDraftText,
        node?.runSettings?.ratio,
        node?.runSettings?.size,
        node?.runSettings?.customSize
    ].filter(Boolean).join(' ');
    if(/(?:360|全景|环景|panorama|equirect|spherical|vr\b)/i.test(text)) return true;
    const w = Number(naturalW || image?.natural_w || image?.width || image?.w || 0);
    const h = Number(naturalH || image?.natural_h || image?.height || image?.h || 0);
    if(!(w > 0 && h > 0)) return false;
    const aspect = w / h;
    return aspect >= 1.9 && aspect <= 2.1;
}
async function ensurePanoramaRenderer(){ return CanvasImagePanoramaRenderer.ensure(); }
function applyPanoramaTexture(img){ return CanvasImagePanoramaRenderer.applyTexture(img); }
function drawPanoramaFrame(){ return CanvasImagePanoramaRenderer.drawFrame(); }
function renderPanoramaFrame(){ return CanvasImagePanoramaRenderer.renderFrame(); }
function startPanoramaLoop(){ return CanvasImagePanoramaRenderer.start(); }
function stopPanoramaLoop(){ return CanvasImagePanoramaRenderer.stop(); }function resizePanoramaViewer(){
    const stage = document.getElementById('panoramaStage');
    const frame = document.getElementById('previewFrame');
    const canvas = document.getElementById('panoramaCanvas');
    if(!stage) return;
    const ratio = panoramaRatioValue();
    const aspect = Math.max(0.08, Math.min(12, ratio.w / ratio.h));
    const maxW = Math.max(260, Math.min(1180, window.innerWidth - 116));
    const maxH = Math.max(220, Math.min(780, window.innerHeight - 220));
    let w = maxW;
    let h = w / aspect;
    if(h > maxH){
        h = maxH;
        w = h * aspect;
    }
    w = Math.max(160, Math.round(w));
    h = Math.max(160, Math.round(h));
    stage.style.width = `${w}px`;
    stage.style.height = `${h}px`;
    stage.style.aspectRatio = `${ratio.w} / ${ratio.h}`;
    if(frame){
        frame.style.width = `${w}px`;
        frame.style.height = `${h}px`;
    }
    if(canvas){
        const render = panoramaResolutionValue();
        const nextW = Math.max(1, Math.round(render.w));
        const nextH = Math.max(1, Math.round(render.h));
        if(canvas.width !== nextW) canvas.width = nextW;
        if(canvas.height !== nextH) canvas.height = nextH;
    }
}
function disposePanoramaTexture(){ return CanvasImagePanoramaRenderer.disposeTexture(); }
function loadPanoramaTexture(src, allowFallback=true){ return CanvasImagePanoramaRenderer.load(src, allowFallback); }function refreshPanoramaControls(){
    const controls = document.getElementById('panoramaControls');
    const custom = document.getElementById('panoramaCustomRatio');
    if(controls) controls.style.display = panoramaState.enabled ? 'inline-flex' : 'none';
    if(custom) custom.style.display = panoramaState.enabled && panoramaState.ratio === 'custom' ? 'inline-flex' : 'none';
    document.querySelectorAll('[data-panorama-ratio]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.panoramaRatio === panoramaState.ratio);
    });
    const w = document.getElementById('panoramaRatioW');
    const h = document.getElementById('panoramaRatioH');
    if(w && document.activeElement !== w) w.value = panoramaState.customW;
    if(h && document.activeElement !== h) h.value = panoramaState.customH;
}
function setPanoramaEnabled(enabled){
    const next = Boolean(enabled);
    if(panoramaState.enabled === next) return;
    panoramaState.enabled = next;
    const stage = document.getElementById('previewStage');
    const pano = document.getElementById('panoramaStage');
    const currentImg = document.getElementById('previewCurrentImage');
    const compareLayer = document.getElementById('previewCompareLayer');
    const compareHandle = document.getElementById('previewCompareHandle');
    const toggle = document.getElementById('panoramaToggleBtn');
    const exportBtn = document.getElementById('panoramaExportBtn');
    const compareToggle = document.getElementById('compareToggleBtn');
    const compareThumbs = document.getElementById('compareThumbs');
    const previewTools = document.getElementById('imagePreviewTools');
    stage?.classList.toggle('panorama-on', next);
    previewTools?.classList.toggle('panorama-tools-on', next);
    if(pano) pano.style.display = next ? 'block' : 'none';
    if(currentImg) currentImg.style.display = next ? 'none' : 'block';
    if(compareLayer && next) compareLayer.style.display = 'none';
    if(compareHandle && next) compareHandle.style.display = 'none';
    if(toggle) toggle.classList.toggle('active', next);
    if(exportBtn) exportBtn.style.display = next ? 'inline-flex' : 'none';
    if(compareToggle) compareToggle.style.display = next ? 'none' : 'inline-flex';
    if(compareThumbs && next){ compareThumbs.style.display = 'none'; compareThumbs.innerHTML = ''; }
    if(next) CanvasImagePreviewCompareController.setActive(false);
    if(next){
        CanvasImagePreviewTransformController.reset();
        resizePanoramaViewer();
        loadPanoramaTexture(panoramaSource());
        updatePreviewMetaHint(tr('smart.panoramaHint'));
    } else {
        stopPanoramaLoop();
        const frame = document.getElementById('previewFrame');
        if(frame){ frame.style.width = ''; frame.style.height = ''; }
        refreshComparePanel();
    }
    refreshPanoramaControls();
    updateZoomLabel();
}
function togglePanoramaPreview(){
    const image = currentEditImage().image || {};
    if(mediaKindForItem(image) !== 'image') return;
    setPanoramaEnabled(!panoramaState.enabled);
}
async function exportPanoramaFrame(){
    if(!panoramaState.enabled) return;
    const canvasEl = document.getElementById('panoramaCanvas');
    if(!canvasEl){ toast(tr('smart.panoramaExportFailed')); return; }
    try {
        if(!drawPanoramaFrame()) throw new Error(tr('smart.panoramaExportFailed'));
        const blob = await new Promise(resolve => canvasEl.toBlob(resolve, 'image/png'));
        if(!blob) throw new Error(tr('smart.panoramaExportFailed'));
        const editing = currentEditImage();
        const rawName = editing.image?.name || fileNameFromUrl(editing.image?.url || '') || 'panorama';
        const base = String(rawName).replace(/\.[a-z0-9]{2,8}$/i, '') || 'panorama';
        const filename = safeExportFileName(`${base}-panorama.png`, 'panorama.png');
        const uploaded = await uploadFiles([new File([blob], filename, {type:'image/png'})]);
        const frame = uploaded[0];
        if(!frame?.url) throw new Error(tr('smart.panoramaExportFailed'));
        frame.kind = 'image';
        frame.natural_w = canvasEl.width;
        frame.natural_h = canvasEl.height;
        const rect = editing.node ? nodeRect(editing.node) : null;
        const point = rect
            ? {x:rect.x + rect.width + 240, y:rect.y + rect.height / 2}
            : viewportCenter();
        pushUndo();
        const newNode = createImageNodeAt(point, [frame], {select:true, skipUndo:true});
        canvasUiState.patchSelection({ids: []}, 'selectedIds');
        canvasUiState.patchSelection({image: {nodeId:newNode.id, index:0}}, 'selectedImage');
        render();
        scheduleSave();
        toast(tr('smart.panoramaExportDone'));
    } catch(e) {
        toast((e.message || tr('smart.panoramaExportFailed')).slice(0, 120));
    }
}
function resetPanoramaView(){
    panoramaState.fov = 75;
    panoramaState.yaw = 0;
    panoramaState.pitch = 0;
    resizePanoramaViewer();
    updateZoomLabel();
}
function disposePanoramaPreview(){
    CanvasImagePanoramaRenderer.dispose();
    panoramaState.enabled = false;
    panoramaState.drag = null;
    const stage = document.getElementById('panoramaStage');
    stage?.classList.remove('ready');
    if(stage) stage.style.display = 'none';
    document.getElementById('previewStage')?.classList.remove('panorama-on', 'panning');
    document.getElementById('imagePreviewTools')?.classList.remove('panorama-tools-on');
    document.getElementById('panoramaControls')?.style.setProperty('display', 'none');
    document.getElementById('panoramaToggleBtn')?.classList.remove('active');
    document.getElementById('panoramaExportBtn')?.style.setProperty('display', 'none');
}
function applyPanoramaRatio(value){
    panoramaState.ratio = PANORAMA_RATIO_PRESETS[value] ? value : 'custom';
    refreshPanoramaControls();
    resizePanoramaViewer();
}
function setPreviewComparePos(clientX){
    const frame = document.getElementById('previewFrame');
    const stage = document.getElementById('previewStage');
    if(!frame || !stage) return;
    const rect = frame.getBoundingClientRect();
    const pct = Math.max(0, Math.min(100, ((clientX - rect.left) / Math.max(1, rect.width)) * 100));
    previewComparePos = pct;
    stage.style.setProperty('--compare-pos', `${pct}%`);
}
function syncPreviewFrameSize(){
    const frame = document.getElementById('previewFrame');
    if(panoramaState.enabled){
        resizePanoramaViewer();
        return;
    }
    const currentImg = document.getElementById('previewCurrentImage');
    const currentVideo = document.getElementById('previewCurrentVideo');
    const compareImg = document.getElementById('previewCompareImage');
    const currentMedia = currentVideo && currentVideo.style.display !== 'none' ? currentVideo : currentImg;
    if(!frame || !currentMedia) return;
    const w = currentMedia.clientWidth || currentMedia.videoWidth || currentMedia.naturalWidth || 1;
    const h = currentMedia.clientHeight || currentMedia.videoHeight || currentMedia.naturalHeight || 1;
    frame.style.width = `${w}px`;
    frame.style.height = `${h}px`;
    if(compareImg){
        compareImg.style.width = `${w}px`;
        compareImg.style.height = `${h}px`;
    }
}
function updatePreviewMetaHint(...args){
    return CanvasImagePreviewMediaController.updateMetaHint(...args);
}
function rememberPreviewImageResolution(){
    return CanvasImagePreviewMediaController.rememberResolution();
}
function previewCompareSources(){
    return CanvasImagePreviewCompareController.sources();
}
function refreshComparePanel(){
    return CanvasImagePreviewMediaController.refreshCurrentMedia();
}
function togglePreviewCompare(){
    return CanvasImagePreviewCompareController.toggle();
}
function currentPreviewVideo(){
    return CanvasImagePreviewMediaController.currentVideo();
}
function videoFrameStep(){
    return CanvasImagePreviewMediaController.frameStep();
}
function seekPreviewVideoFrames(direction){
    return CanvasImagePreviewMediaController.seekFrames(direction);
}
function handleImagePreviewWheel(event){
    return CanvasImagePreviewInteractionController.handleWheel(event);
}
function bindPreviewWheelListeners(){
    return CanvasImagePreviewInteractionController.bindWheelListeners(
        ['imageEditStage','previewStage','previewFrame','previewCurrentImage','previewCurrentVideo','panoramaStage','panoramaCanvas']
    );
}
function waitForVideoEvent(video, eventName, timeout=1500){
    return CanvasImagePreviewMediaController.waitForEvent(video,eventName,timeout);
}
async function seekVideoForFrame(video, time){
    return CanvasImagePreviewMediaController.seekForFrame(video,time);
}
async function exportVideoFrame(which='current'){
    const video = currentPreviewVideo();
    if(!video){ toast('没有可导出的视频帧'); return; }
    if(video.readyState < 2) await waitForVideoEvent(video, 'loadeddata', 2200);
    if(!video.videoWidth || !video.videoHeight){ toast('视频还没有加载完成'); return; }
    const originalTime = Number(video.currentTime || 0);
    const duration = Number.isFinite(video.duration) && video.duration > 0 ? video.duration : 0;
    const step = videoFrameStep();
    const target = which === 'first'
        ? 0
        : which === 'last'
            ? Math.max(0, duration - step / 2)
            : originalTime;
    const suffix = which === 'first' ? 'first-frame' : which === 'last' ? 'last-frame' : 'current-frame';
    try {
        video.pause?.();
        await seekVideoForFrame(video, target);
        const canvasEl = document.createElement('canvas');
        canvasEl.width = video.videoWidth;
        canvasEl.height = video.videoHeight;
        const ctx = canvasEl.getContext('2d');
        ctx.drawImage(video, 0, 0, canvasEl.width, canvasEl.height);
        const blob = await new Promise(resolve => canvasEl.toBlob(resolve, 'image/png'));
        if(!blob) throw new Error('导出帧失败');
        const editing = currentEditImage();
        const rawName = editing.image?.name || fileNameFromUrl(editing.image?.url || '') || 'video';
        const base = String(rawName).replace(/\.[a-z0-9]{2,8}$/i, '') || 'video';
        const filename = safeExportFileName(`${base}-${suffix}.png`, `${suffix}.png`);
        const uploaded = await uploadFiles([new File([blob], filename, {type:'image/png'})]);
        const frame = uploaded[0];
        if(!frame?.url) throw new Error('导出到画布失败');
        frame.kind = 'image';
        frame.natural_w = video.videoWidth;
        frame.natural_h = video.videoHeight;
        const rect = editing.node ? nodeRect(editing.node) : null;
        const point = rect
            ? {x:rect.x + rect.width + 240, y:rect.y + rect.height / 2}
            : viewportCenter();
        pushUndo();
        const newNode = createImageNodeAt(point, [frame], {select:true, skipUndo:true});
        canvasUiState.patchSelection({ids: []}, 'selectedIds');
        canvasUiState.patchSelection({image: {nodeId:newNode.id, index:0}}, 'selectedImage');
        render();
        scheduleSave();
        toast('已导出到画布');
        if(which !== 'current') await seekVideoForFrame(video, originalTime);
    } catch(e) {
        toast((e.message || '导出帧失败').slice(0, 120));
    }
}
function editDrawSnapshot(){
    return CanvasImageEditDrawingHistoryController.snapshot();
}
function restoreEditDrawSnapshot(snapshot){
    return CanvasImageEditDrawingHistoryController.restore(snapshot);
}
function pushEditDrawHistory(){
    return CanvasImageEditDrawingHistoryController.push();
}
function syncEditDrawingHistoryButtons(){
    return CanvasImageEditDrawingHistoryController.syncButtons();
}
function undoEditDrawing(){
    return CanvasImageEditDrawingHistoryController.undo();
}
function redoEditDrawing(){
    return CanvasImageEditDrawingHistoryController.redo();
}
function editCanvasHasPixels(){
    if(editTextHasContent()) return true;
    const canvasEl = editDrawCanvas();
    const data = canvasEl.getContext('2d').getImageData(0, 0, canvasEl.width, canvasEl.height).data;
    for(let i = 3; i < data.length; i += 4) if(data[i] > 0) return true;
    return false;
}
function clearEditDrawing(silent=false){
    return CanvasImageEditDrawingHistoryController.clear(silent);
}
function resetEditDrawingHistory(){
    return CanvasImageEditDrawingHistoryController.reset();
}
function setBrushTool(tool){
    return CanvasImageEditDrawingController.setTool(tool);
}
function syncBrushToolButtons(){
    return CanvasImageEditDrawingController.syncToolButtons();
}
function editDrawPoint(event){
    return CanvasImageEditDrawingController.point(event);
}
function beginEditDraw(event){ return CanvasImageEditDrawingController.begin(event); }
function moveEditDraw(event){ return CanvasImageEditDrawingController.move(event); }
function endEditDraw(event){ return CanvasImageEditDrawingController.end(event); }
function syncGridGapValue(){
    const input = document.getElementById('gridGapSize');
    const value = Math.max(0, Math.min(240, Number(input?.value || 0)));
    if(input) input.value = value;
    const label = document.getElementById('gridGapValue');
    if(label) label.textContent = String(value);
    return value;
}
function gridSplitSettings(){
    const hLines = Math.max(0, Math.min(20, Number(document.getElementById('gridHorizontalLines')?.value || 0)));
    const vLines = Math.max(0, Math.min(20, Number(document.getElementById('gridVerticalLines')?.value || 0)));
    return {rows:hLines + 1, cols:vLines + 1, gap:syncGridGapValue()};
}
function gridSplitRects(width, height){
    return CanvasImageGridSplitController.rects(width, height, gridSplitSettings());
}
function gridLayoutFromRects(rects){
    return CanvasImageGridSplitController.layoutFromRects(rects, uid('grid'));
}
function applyGridPreset(rows, cols){
    CanvasImageGridSplitController.applyPreset();
    const h = document.getElementById('gridHorizontalLines'), v = document.getElementById('gridVerticalLines');
    if(h){ h.disabled = false; h.value = String(Math.max(0, Number(rows || 1) - 1)); }
    if(v){ v.disabled = false; v.value = String(Math.max(0, Number(cols || 1) - 1)); }
    document.getElementById('gridCustomToggle')?.classList.remove('primary');
    document.getElementById('gridCustomToggle')?.classList.add('secondary');
    syncGridCustomControls();
    syncGridCustomCursor(); syncGridCustomUndoBtn(); refreshGridSplitPreview();
}
function syncGridCustomControls(){
    const custom = document.getElementById('gridCustomControls');
    const isCustom = CanvasImageGridSplitController.isCustomMode();
    if(custom) custom.style.display = isCustom ? 'flex' : 'none';
    document.querySelectorAll('.grid-preset-row').forEach(row => {
        row.style.display = isCustom ? 'none' : 'flex';
    });
}
function toggleGridCustomMode(){
    const custom = CanvasImageGridSplitController.toggleCustomMode();
    const toggle = document.getElementById('gridCustomToggle');
    toggle.classList.toggle('primary', custom); toggle.classList.toggle('secondary', !custom);
    ['gridHorizontalLines','gridVerticalLines'].forEach(id => { const el = document.getElementById(id); if(el) el.disabled = custom; });
    syncGridCustomControls();
    syncGridCustomCursor(); syncGridCustomUndoBtn(); refreshGridSplitPreview();
}
function setGridCustomOrientation(orient){
    CanvasImageGridSplitController.setOrientation(orient);
    document.getElementById('gridOrientH').classList.toggle('primary', orient === 'h');
    document.getElementById('gridOrientH').classList.toggle('secondary', orient !== 'h');
    document.getElementById('gridOrientV').classList.toggle('primary', orient === 'v');
    document.getElementById('gridOrientV').classList.toggle('secondary', orient !== 'v');
    syncGridCustomCursor();
}
function clearGridCustomLines(){ CanvasImageGridSplitController.clearLines(); syncGridCustomUndoBtn(); refreshGridSplitPreview(); }
function undoGridCustomLine(){ if(!CanvasImageGridSplitController.undoLine()) return; syncGridCustomUndoBtn(); refreshGridSplitPreview(); }
function syncGridCustomUndoBtn(){
    const btn = document.getElementById('gridUndoBtn');
    if(!btn) return;
    const canUndo = CanvasImageGridSplitController.canUndo();
    btn.disabled = !canUndo;
    btn.style.opacity = canUndo ? '1' : '0.4';
}
function applyImageEditZoom(scaleOverride=null){
    return CanvasImageEditViewportController.applyZoom(scaleOverride);
}
function ensureImageEditBaseSize(force=false){
    return CanvasImageEditViewportController.ensureBaseSize(force);
}
function syncImageEditOverflow(){
    return CanvasImageEditViewportController.syncOverflow();
}
function resetImageEditZoom(){
    return CanvasImageEditViewportController.resetZoom();
}
function updateZoomLabel(){
    return CanvasImageEditViewportController.updateZoomLabel();
}
function syncGridCustomCursor(){
    return CanvasImageGridSplitController.syncCursor();
}
function refreshGridSplitPreview(){
    return CanvasImageGridSplitController.refreshPreview();
}
function renderCropBox(){
    return CanvasImageEditViewportController.renderCropBox();
}
function outpaintNaturalSize(){
    return CanvasImageEditViewportController.outpaintNaturalSize();
}
function updateOutpaintResolutionLabel(){
    return CanvasImageEditViewportController.updateOutpaintResolutionLabel();
}
function clampOutpaint(){
    if(!cropState) return;
    const {w, h} = cropBounds();
    Object.assign(cropState, CanvasImageEditCropGeometryModel.clampOutpaint(cropState, {w, h}));
}
function resetOutpaintBox(){
    if(!cropState) return;
    ensureImageEditBaseSize(true);
    applyImageEditZoom();
    const {w, h} = cropBounds();
    Object.assign(cropState, CanvasImageEditCropGeometryModel.resetRect({w, h}, 'outpaint'));
    clampOutpaint();
    renderCropBox();
}
function resetCropBox(){
    if(!cropState) return;
    if(imageEditMode === 'outpaint') return resetOutpaintBox();
    const {w, h} = cropBounds();
    Object.assign(cropState, CanvasImageEditCropGeometryModel.resetRect({w, h}, 'crop'));
    renderCropBox();
}
CanvasImageEditorLifecycleController.configure({
    getNodes: () => nodes,
    imageForDisplay: image => imageForDisplay(image),
    mediaKindForItem: image => mediaKindForItem(image),
    downloadPreviewFile: image => downloadPreviewFile(image),
    getPreviewNavigation: () => previewNavState,
    setPreviewNavigation: value => { previewNavState = value; },
    isModalOpen: () => imageEditModal.classList.contains('open'),
    getModal: () => imageEditModal,
    nextLoadToken: () => ++previewLoadToken,
    getLoadToken: () => previewLoadToken,
    setSelectedId: value => { canvasUiState.patchSelection({primaryId: value}, 'selectedId'); },
    setSelectedImage: value => { canvasUiState.patchSelection({image: value}, 'selectedImage'); },
    setCropState: value => { cropState = value; },
    resetGridState: () => CanvasImageGridSplitController.reset(),
    resetImageViewState: () => { CanvasImageEditViewportController.reset(); imageEditModeTouched = false; },
    resetTextEditState: () => CanvasImageEditTextController.resetState(),
    resetCompareState: () => CanvasImagePreviewCompareController.reset(),
    resetPreviewInteractionState: () => { previewPanDrag = null; previewCompareDrag = false; imageEditPanDrag = null; },
    setCropDrag: value => { cropDrag = value; },
    setEditDrawState: value => CanvasImageEditDrawingController.setDrawState(value),
    setGridCustomDrag: () => CanvasImageGridSplitController.endLineEdit(),
    setImageBaseSize: (width, height) => CanvasImageEditViewportController.setBaseSize(width,height),
    isImageEditModeTouched: () => imageEditModeTouched,
    isPanoramaEnabled: () => panoramaState.enabled,
    setImageEditMode: (...args) => setImageEditMode(...args),
    syncGridCustomControls: () => syncGridCustomControls(),
    syncGridCustomUndoButton: () => syncGridCustomUndoBtn(),
    lockRootScroll: () => lockSmartCanvasRootScroll(),
    disposePanoramaPreview: () => disposePanoramaPreview(),
    resetPreviewTransform: () => resetPreviewTransform(),
    updatePreviewMetaHint: (...args) => updatePreviewMetaHint(...args),
    updateZoomLabel: () => updateZoomLabel(),
    scheduleSave: () => scheduleSave(),
    resizeEditDrawCanvas: () => resizeEditDrawCanvas(),
    resetEditDrawingHistory: () => resetEditDrawingHistory(),
    clearEditDrawing: (...args) => clearEditDrawing(...args),
    resetCropBox: () => resetCropBox(),
    refreshComparePanel: () => refreshComparePanel(),
    syncImageEditOverflow: () => syncImageEditOverflow(),
    proxiedMediaUrl: (...args) => proxiedMediaUrl(...args),
    displayMediaUrl: (...args) => displayMediaUrl(...args),
    refreshIcons: () => refreshIcons()
});
function updatePreviewNavButtons(){
    return CanvasImageEditorLifecycleController.updateNavigation();
}
function navigatePreviewImage(delta){
    return CanvasImageEditorLifecycleController.navigate(delta);
}
function openImagePreview(nodeId, imageIndex=0){
    openImageEditor(nodeId, imageIndex);
    setImageEditMode('preview');
}
function openImageEditor(nodeId, imageIndex=0){
    return CanvasImageEditorLifecycleController.open(nodeId, imageIndex);
}
function closeImageEditor(){
    return CanvasImageEditorLifecycleController.close();
}
function clampCrop(){
    if(!cropState) return;
    if(imageEditMode === 'outpaint') return clampOutpaint();
    const {w, h} = cropBounds();
    Object.assign(cropState, CanvasImageEditCropGeometryModel.clampCrop(cropState, {w, h}));
}
function beginCropDrag(event, mode){
    if(!cropState) return;
    event.preventDefault(); event.stopPropagation();
    if(imageEditMode === 'outpaint' && mode === 'move') return;
    cropDrag = {mode, sx:event.clientX, sy:event.clientY, start:{...cropState}};
    if (typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.begin('crop-drag');
}
function resizeOutpaintFromDrag(dx, dy){
    const start = cropDrag?.start;
    if(!start || !cropState) return;
    const {w, h} = cropBounds();
    Object.assign(cropState, CanvasImageEditCropGeometryModel.resizeOutpaint(start, cropDrag.mode, dx, dy, {w, h}));
}
function canvasScopedUploadUrl(){
    // 画布类上传（导入/粘贴/裁剪外扩/Agent 附件）一律归到当前画布输出目录下：
    // 随画布改名一起搬移、随画布彻底删除一起清理，不再堆在 assets/input。
    try {
        const id = String(canvasId || canvas?.id || '').trim();
        if(id) return `/api/ai/upload?scope=canvas&canvas_id=${encodeURIComponent(id)}`;
    } catch(e) {}
    return '/api/ai/upload';
}
async function uploadCroppedBlob(blob, name){
    const form = new FormData();
    form.append('files', blob, name);
    const data = await fetch(canvasScopedUploadUrl(), {method:'POST', body:form}).then(r => r.json());
    return data.files?.[0];
}
async function uploadImageBlobs(blobs){
    const form = new FormData();
    blobs.forEach(item => form.append('files', item.blob, item.name));
    const data = await fetch(canvasScopedUploadUrl(), {method:'POST', body:form}).then(r => r.json());
    return data.files || [];
}
function replaceEditedImage(file){
    const {node, index} = currentEditImage();
    if(!node || !file) return false;
    node.images[index] = {...(node.images[index] || {}), url:file.url, name:file.name, kind:file.kind || mediaKindForItem(file), natural_w:0, natural_h:0};
    if((node.images || []).length === 1){ delete node.w; delete node.h; }
    canvasUiState.patchSelection({primaryId: node.id}, 'selectedId'); canvasUiState.patchSelection({image: {nodeId:node.id, index}}, 'selectedImage');
    return true;
}
function applyOutpaintSizeToSmartParams(width, height){
    const w = Math.max(1, Math.round(Number(width) || 0));
    const h = Math.max(1, Math.round(Number(height) || 0));
    if(!w || !h) return;
    const subject = currentEditImage().node;
    if(!subject || !isSmartImageNode(subject)) return;
    subject.outpaintSize = {width:w, height:h};
    subject.runSettings = withOutpaintDisplaySettings(subject, cloneSmartSettings(subject.runSettings || settings));
    if(activeSettingsSubject()?.id === subject.id){
        settings = smartSettingsForNode(subject);
        renderDynamicParams();
    }
}
async function applyImageCrop(){
    if(!cropState) return;
    const {node, image} = currentEditImage();
    const img = document.getElementById('cropImage');
    if(!node || !image || !img.naturalWidth || !img.naturalHeight) return;
    const scaleX = img.naturalWidth / (img.clientWidth || 1), scaleY = img.naturalHeight / (img.clientHeight || 1);
    const sx = Math.max(0, Math.round(cropState.x * scaleX)), sy = Math.max(0, Math.round(cropState.y * scaleY));
    const sw = Math.max(1, Math.round(cropState.w * scaleX)), sh = Math.max(1, Math.round(cropState.h * scaleY));
    const canvasEl = document.createElement('canvas');
    canvasEl.width = sw; canvasEl.height = sh;
    canvasEl.getContext('2d').drawImage(img, sx, sy, sw, sh, 0, 0, sw, sh);
    const blob = await new Promise(resolve => canvasEl.toBlob(resolve, 'image/png'));
    const base = (image.name || 'image').replace(/\.[^.]+$/, '');
    const file = blob ? await uploadCroppedBlob(blob, `${base}_crop.png`) : null;
    if(file?.url){
        const cropped = {...file, kind:'image', natural_w:sw, natural_h:sh};
        const layout = imageLayout(node.images || [], nodeScale(node), node);
        closeImageEditor();
        const newNode = createNode(Number(node.x || 0) + Number(layout.width || 260) + 36, Number(node.y || 0), [cropped]);
        canvasUiState.patchSelection({ids: []}, 'selectedIds');
        canvasUiState.patchSelection({image: {nodeId:newNode.id, index:0}}, 'selectedImage');
        render();
        scheduleSave();
    }
}
// 2026-10-05（老王：画布里加图片镜像）：像素级镜像，复用裁剪/扩图那条
// 「前端 canvas → toBlob → uploadCroppedBlob → createNode」链路，只在 drawImage
// 前加方向 transform，其余（导出/上传/命名清洗/落盘）全部沿用既有实现。
//
// 为什么不用 CSS 显示层镜像(scaleX(-1))：那样只翻界面，送进 ComfyUI 生成/图生图时
// 用的仍是原图，会出现「我镜像了怎么生成出来没镜像」的困惑。像素级才是真镜像。
// 产物是【新节点】放在原节点右边，原素材不动 —— 与裁剪/扩图完全一致，删掉新节点即回退。
const IMAGE_MIRROR_DIRS = {
    flipX:    {flipX:true,  flipY:false, suffix:'_mirror_h.png'},
    flipY:    {flipX:false, flipY:true,  suffix:'_mirror_v.png'},
    flipBoth: {flipX:true,  flipY:true,  suffix:'_mirror_180.png'}
};
function loadImageForMirror(url){
    return new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = () => reject(new Error('图片加载失败'));
        img.src = url;
    });
}
async function applyImageMirror(nodeId, imageIndex, dir){
    const conf = IMAGE_MIRROR_DIRS[dir] || IMAGE_MIRROR_DIRS.flipX;
    const node = nodes.find(item => item.id === nodeId);
    const image = node?.images?.[imageIndex];
    if(!node || !image) return false;
    // 只做图片（老王拍板）：视频/音频素材走 ffmpeg 翻转是另一套，先不碰
    if(mediaKindForItem(image) !== 'image'){ toast('镜像仅支持图片素材'); return false; }
    if(!image.url){ toast('该图片没有可用地址'); return false; }
    try{
        // 同源可直接读像素（裁剪链路已在用 drawImage，说明这些图没被 CORS 污染）
        const img = await loadImageForMirror(image.url);
        const w = img.naturalWidth, h = img.naturalHeight;
        if(!w || !h) throw new Error('图片尺寸读取失败');
        const canvasEl = document.createElement('canvas');
        canvasEl.width = w; canvasEl.height = h;
        const ctx = canvasEl.getContext('2d');
        // 水平镜像 = 沿 x 轴翻：先平移到右边界，再把 x 方向缩放取反
        if(conf.flipX) ctx.translate(w, 0);
        if(conf.flipY) ctx.translate(0, h);
        if(conf.flipX) ctx.scale(-1, 1);
        if(conf.flipY) ctx.scale(1, -1);
        ctx.drawImage(img, 0, 0, w, h);
        const blob = await new Promise(resolve => canvasEl.toBlob(resolve, 'image/png'));
        if(!blob) throw new Error('导出失败');
        const base = (image.name || 'image').replace(/\.[^.]+$/, '');
        const file = await uploadCroppedBlob(blob, `${base}${conf.suffix}`);
        if(!file?.url) throw new Error('上传失败');
        const mirrored = {...file, kind:'image', natural_w:w, natural_h:h};
        const layout = imageLayout([mirrored], nodeScale(node), node);
        const newNode = createNode(Number(node.x || 0) + Number(layout.width || 260) + 36, Number(node.y || 0), [mirrored]);
        canvasUiState.patchSelection({ids: []}, 'selectedIds');
        canvasUiState.patchSelection({image: {nodeId:newNode.id, index:0}}, 'selectedImage');
        render();
        scheduleSave();
        toast('已生成镜像图');
        return true;
    }catch(err){
        toast(`镜像失败：${err?.message || err}`);
        return false;
    }
}
async function applyImageOutpaint(){
    if(!cropState) return;
    const {node, image} = currentEditImage();
    const img = document.getElementById('cropImage');
    if(!node || !image || !img.naturalWidth || !img.naturalHeight) return;
    clampOutpaint();
    const scaleX = img.naturalWidth / (img.clientWidth || 1), scaleY = img.naturalHeight / (img.clientHeight || 1);
    const outW = Math.max(img.naturalWidth, Math.round(cropState.w * scaleX));
    const outH = Math.max(img.naturalHeight, Math.round(cropState.h * scaleY));
    const dx = Math.round(cropState.x * scaleX);
    const dy = Math.round(cropState.y * scaleY);
    const canvasEl = document.createElement('canvas');
    canvasEl.width = outW; canvasEl.height = outH;
    const ctx = canvasEl.getContext('2d');
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, outW, outH);
    ctx.drawImage(img, dx, dy, img.naturalWidth, img.naturalHeight);
    const blob = await new Promise(resolve => canvasEl.toBlob(resolve, 'image/png'));
    const base = (image.name || 'image').replace(/\.[^.]+$/, '');
    const file = blob ? await uploadCroppedBlob(blob, `${base}_outpaint.png`) : null;
    if(file && replaceEditedImage(file)){
        applyOutpaintSizeToSmartParams(outW, outH);
        setPromptDraftForNode(node, 'Remove white area and fill the scene');
        promptInput.dataset.preserveDraftOnce = '1';
        closeImageEditor();
        render();
        scheduleSave();
    }
}
async function applyImageMask(){
    if(!cropState || !editCanvasHasPixels()) return;
    const {node, image} = currentEditImage();
    if(!node || !image) return;
    const mask = maskCanvasFromDrawCanvas(editDrawCanvas());
    const blob = await new Promise(resolve => mask.toBlob(resolve, 'image/png'));
    const base = (image.name || 'image').replace(/\.[^.]+$/, '');
    const file = blob ? await uploadCroppedBlob(blob, `${base}_mask.png`) : null;
    if(file){
        node.images.push({url:file.url, name:file.name, role:'mask'});
        canvasUiState.patchSelection({primaryId: node.id}, 'selectedId'); canvasUiState.patchSelection({image: {nodeId:node.id, index:node.images.length - 1}}, 'selectedImage');
        closeImageEditor(); render(); scheduleSave();
    }
}
function maskCanvasFromDrawCanvas(src){
    const mask = document.createElement('canvas');
    mask.width = src.width;
    mask.height = src.height;
    const srcCtx = src.getContext('2d');
    const srcData = srcCtx.getImageData(0, 0, src.width, src.height);
    const ctx = mask.getContext('2d');
    const out = ctx.createImageData(mask.width, mask.height);
    for(let i = 0; i < srcData.data.length; i += 4){
        const painted = srcData.data[i + 3] > 8;
        const v = painted ? 255 : 0;
        out.data[i] = v;
        out.data[i + 1] = v;
        out.data[i + 2] = v;
        out.data[i + 3] = 255;
    }
    ctx.putImageData(out, 0, 0);
    return mask;
}
async function applyImageBrush(){
    if(!cropState) return;
    removeEditTextInlineEditor(true);
    if(!editCanvasHasPixels()) return;
    const {node, image} = currentEditImage();
    const img = document.getElementById('cropImage');
    if(!node || !image || !img.naturalWidth || !img.naturalHeight) return;
    const canvasEl = document.createElement('canvas');
    canvasEl.width = img.naturalWidth; canvasEl.height = img.naturalHeight;
    const ctx = canvasEl.getContext('2d');
    ctx.drawImage(img, 0, 0, canvasEl.width, canvasEl.height); ctx.drawImage(editDrawCanvas(), 0, 0); ctx.drawImage(editTextCanvas(), 0, 0);
    const blob = await new Promise(resolve => canvasEl.toBlob(resolve, 'image/png'));
    const base = (image.name || 'image').replace(/\.[^.]+$/, '');
    const file = blob ? await uploadCroppedBlob(blob, `${base}_paint.png`) : null;
    if(file && replaceEditedImage(file)){ closeImageEditor(); render(); scheduleSave(); }
}
async function applyImageGridSplit(){
    if(!cropState) return;
    const {node, image} = currentEditImage();
    const img = document.getElementById('cropImage');
    if(!node || !image || !img.naturalWidth || !img.naturalHeight) return;
    const rects = gridSplitRects(img.naturalWidth, img.naturalHeight).sort((a, b) => (Number(a.row || 0) - Number(b.row || 0)) || (Number(a.col || 0) - Number(b.col || 0)));
    if(!rects.length) return;
    const base = safeExportFileName((downloadNameForMediaItem(image, 'image') || 'image').replace(/\.[^.]+$/, ''), 'image');
    const digits = String(rects.length).length;
    const blobs = [];
    for(let i = 0; i < rects.length; i++){
        const rect = rects[i];
        const canvasEl = document.createElement('canvas');
        canvasEl.width = rect.w; canvasEl.height = rect.h;
        canvasEl.getContext('2d').drawImage(img, rect.x, rect.y, rect.w, rect.h, 0, 0, rect.w, rect.h);
        const blob = await new Promise(resolve => canvasEl.toBlob(resolve, 'image/png'));
        const order = String(i + 1).padStart(digits, '0');
        if(blob) blobs.push({blob, name:`${base}_${order}_r${rect.row + 1}_c${rect.col + 1}.png`});
    }
    const files = await uploadImageBlobs(blobs);
    if(files.length){
        const layout = gridLayoutFromRects(rects);
        // 2026-10-19（老王：一个节点只装一张图）：九宫格切图不再合成一个 Grid 节点，
        // 每格各自一个独立节点，按原来的行列位置摆开。
        const startX = (node.x || 0) + imageLayout(node.images || [], nodeScale(node), node).width + 40;
        const startY = node.y || 0;
        const cellW = 260, cellH = 220, cellGap = 24;
        files.forEach((file, i) => {
            const rect = rects[i] || {};
            const row = Number(rect.row || 0), col = Number(rect.col || 0);
            const point = {
                x: startX + col * (cellW + cellGap) + Math.round(cellW / 2),
                y: startY + row * (cellH + cellGap) + Math.round(cellH / 2)
            };
            const outNode = createImageNodeAt(point, [{
                url:file.url,
                name:file.name,
                grid:{...layout, row, col, w:rect.w || 1, h:rect.h || 1}
            }], {select:false, skipUndo:true});
            if(!outNode) return;
            const stem = String(file.name || '').replace(/\.[^.]+$/, '').slice(0, 30);
            if(stem) outNode.title = stem;
            delete outNode.w;
            delete outNode.h;
        });
        closeImageEditor(); render(); scheduleSave();
    }
}
function applyImageEdit(){
    if(imageEditMode === 'preview') return;
    if(imageEditMode === 'outpaint') return applyImageOutpaint();
    if(imageEditMode === 'mask') return applyImageMask();
    if(imageEditMode === 'brush') return applyImageBrush();
    if(imageEditMode === 'grid') return applyImageGridSplit();
    return applyImageCrop();
}
function currentComposerSubject(){
    return selectedNode();
}
function savePromptDraftForCurrent(){
    if(promptInput?.dataset?.promptLocked === '1') return;
    const subject = activeComposerNode();
    if(!subject) return;
    if(promptInput?.dataset?.preserveDraftOnce === '1' && subject.promptDraftHtml){
        delete promptInput.dataset.preserveDraftOnce;
        return;
    }
    const hasImageMentionToken = promptHtmlHasImageMentionToken(promptInput?.innerHTML || '');
    if(promptInput?.dataset?.promptDraftHadImageMention === '1' && !hasImageMentionToken){
        subject.promptDraftRefsEdited = true;
    }
    if(promptInput) promptInput.dataset.promptDraftHadImageMention = hasImageMentionToken ? '1' : '0';
    subject.promptDraftHtml = promptInput.innerHTML;
    subject.promptDraftText = promptPlainText();
    if(subject.runSettings?.engine === 'blender' || settings.engine === 'blender'){
        settings.engine = 'blender';
        settings.provider_id = 'blender';
        settings.model = 'blender-previz';
    }
    subject.runSettings = cloneSmartSettings(settings);
}
function setPromptDraftForNode(node, text){
    if(!isSmartImageNode(node)) return;
    const value = String(text || '');
    node.promptDraftHtml = escapeHtml(value);
    node.promptDraftText = value;
    node.promptDraftTouched = true;
    if(activeSettingsSubject()?.id === node.id && promptInput){
        promptInput.textContent = value;
        delete promptInput.dataset.preserveDraftOnce;
    }
}
function loadPromptDraft(subject){
    if(subject?.promptDraftRefsEdited){
        promptInput.innerHTML = subject.promptDraftHtml || escapeHtml(subject.promptDraftText || '');
    } else if(subject?.promptDraftHtml){
        const hasToken = promptHtmlHasMentionToken(subject.promptDraftHtml);
        promptInput.innerHTML = hasToken
            ? subject.promptDraftHtml
            : (promptHtmlWithMentionTokens(subject.runPrompt || subject.promptDraftText || '', subject.runPromptRefs || []) || subject.promptDraftHtml);
    } else if(typeof subject?.runPrompt === 'string'){
        const rebuilt = promptHtmlWithMentionTokens(subject.runPrompt, subject.runPromptRefs || []);
        if(rebuilt) promptInput.innerHTML = rebuilt;
        else setPromptText(subject.runPrompt);
    } else {
        setPromptText('');
    }
    if(CanvasPlainTextPaste.cleanFormatting(promptInput) && subject){
        subject.promptDraftHtml = promptInput.innerHTML;
        scheduleSave();
    }
    promptInput.dataset.promptDraftHadImageMention = promptHtmlHasImageMentionToken(promptInput.innerHTML) ? '1' : '0';
    refreshPromptPlaceholderVisible();
    renderComposerStyleControl();
}
function positionComposerForNode(node){
    if(!node) return;
    const rect = nodeRect(node);
    const scale = safeScale(viewport.scale);
    const widthScale = Number.parseFloat(getComputedStyle(composer).getPropertyValue('--canvas-composer-width-scale')) || 1;
    const adaptive=CanvasViewport.isComposerAdaptive();
    const cardW=Math.max(280,Math.min(825,shell.clientWidth*.615)*widthScale);
    const screenWidth=cardW;
    composer.style.width = `${cardW}px`;
    const nodeCenterX = viewport.x + (rect.x + rect.width / 2) * scale;
    const nodeBottomScreen = viewport.y + (rect.y + rect.height) * scale;
    // With position adaptation off, keep the same node-bottom anchor even when
    // the panel grows or crosses the viewport/minimap boundary.
    if(!adaptive){
        composer.style.left=`${(nodeCenterX-cardW/2-viewport.x)/scale}px`;
        composer.style.top=`${(nodeBottomScreen+14-viewport.y)/scale}px`;
        return;
    }

    // The editor has fixed screen size even when the node is zoomed. Clamp
    // before converting back to world coordinates, leaving room for the dock.
    const leftInset = document.querySelector('.canvas-tool-dock') ? 72 : 12;
    const maxLeft = Math.max(12, shell.clientWidth - screenWidth - 12);
    const left = Math.max(Math.min(leftInset, maxLeft), Math.min(nodeCenterX - screenWidth / 2, maxLeft));
    let maxTop = shell.clientHeight - composer.offsetHeight - 64;
    if(minimap?.offsetHeight){
        const shellBox = shell.getBoundingClientRect(), mapBox = minimap.getBoundingClientRect();
        const uiScale = shellBox.width / Math.max(shell.clientWidth, 1);
        const mapLeft = (mapBox.left - shellBox.left) / uiScale;
        const mapRight = (mapBox.right - shellBox.left) / uiScale;
        if(left < mapRight && left + screenWidth > mapLeft){
            maxTop = Math.min(maxTop, (mapBox.top - shellBox.top) / uiScale - composer.offsetHeight - 12);
        }
    }
    maxTop = Math.max(12, maxTop);
    const top = Math.max(12, Math.min(nodeBottomScreen + 14, maxTop));
    composer.style.left = `${(left - viewport.x) / scale}px`;
    composer.style.top = `${(top - viewport.y) / scale}px`;
}
function isAudioOnlyNode(node){
    const imgs = node?.images || [];
    return Boolean(isSmartImageNode(node) && imgs.length && imgs.every(isAudioMediaItem));
}
function updateComposer(){
    const node = selectedNode();
    if(smartCascadeSilentSelection && !canvasUiState.editor.subject){
        composer.classList.remove('open');
        if(cascadeRunBtn) cascadeRunBtn.style.display = 'none';
        closeAllSmartPopovers(); canvasUiState.clearEditor();
        return;
    }
    if(node?.type === 'smart-speech' || isAudioOnlyNode(node)){
        savePromptDraftForCurrent();
        composer.classList.remove('open');
        closeAllSmartPopovers(); canvasUiState.clearEditor();
        if(cascadeRunBtn) cascadeRunBtn.style.display = 'none';
        setPromptInputLocked(false);
        return;
    }
    composer.classList.toggle('open', !!node);
    if(!isSmartImageNode(node)){
        if(cascadeRunBtn) cascadeRunBtn.style.display = 'none';
        savePromptDraftForCurrent();
        composer.classList.remove('open');
        closeAllSmartPopovers(); canvasUiState.clearEditor();
        setPromptInputLocked(false);
        if(!node) setPromptText('');
        return;
    }
    // composer 只绑定节点本身：图片只是素材/结果，不携带提示词或参数状态。
    const subject = node;
    const composerKey = `${node.id}:node`;
    const switchedNode = canvasUiState.editor.key !== composerKey;
    if(switchedNode){ savePromptDraftForCurrent(); closeAllSmartPopovers(); }
    canvasUiState.bindEditor(subject, composerKey);
    const hasPromptInput = promptInputNodesFor(node).length > 0;
    // 每次选中都从节点刷新设置（确保 3D预演 节点引擎生效）
    settings = smartSettingsForNode(subject);
    if(switchedNode){
        loadPromptDraft(subject);
    }
    setPromptInputLocked(false);
    syncCascadeRunButton(node);
    const ph = Math.max(60, Math.min(380, Number(settings.promptH) || 93));
    promptInput.style.setProperty('--prompt-h', `${ph}px`);
    renderInputThumbsRow(node);
    renderInputPromptPreview(node);
    syncCascadeRunButton(node);
    syncRunButtonAvailability(node);
    updateProviderModels();
    positionComposerForNode(node);
}
// 2026-10-19 老王：上游提示词节点只出缩略图行里的“文本1/文本2”缩略图，不再在本节点多出一个提示词框。
function renderInputPromptPreview(node){
    if(!inputPromptPreview) return;
    void node;
    inputPromptPreview.classList.remove('has-text');
    if(inputPromptPreview.innerHTML) inputPromptPreview.innerHTML = '';
}
// ===== 2026-10-19 老王：上游提示词节点不再在本节点多出一个“提示词框”，
// 改为缩略图行里的文本缩略图（文本1、文本2…），样式对齐音频缩略图。 =====
function inputTextThumbItems(node, ctx=smartLoopContext){
    if(!node) return [];
    const texts = [
        ...canvasObjectReferenceTextNodes(node),
        ...promptInputNodesFor(node).map(input => textForNode(input, ctx)),
        ...(Array.isArray(ctx?.relayPromptNodeIds)
            ? ctx.relayPromptNodeIds.map(id => nodes.find(n => n.id === id)).map(input => textForNode(input, ctx))
            : [])
    ];
    const seen = new Set();
    const items = [];
    texts.forEach(text => {
        const value = String(text || '').trim();
        if(!value || seen.has(value)) return;
        seen.add(value);
        items.push({text:value, name:`文本${items.length + 1}`});
    });
    return items;
}
// 2026-10-19 老王：视频缩略图跟音频一样带文字标签（视频1、视频2…）
function videoInputThumbHtml(img, label, attrs=''){
    const name = String(label || '视频');
    return `<div class="media-thumb video-thumb input-video-thumb"${attrs}><video src="${escapeHtml(img.url)}" muted preload="metadata" playsinline disablepictureinpicture controlslist="nodownload noplaybackrate noremoteplayback"></video><span class="input-video-thumb-label">${escapeHtml(name)}</span></div>`;
}
function inputTextThumbHtml(item, index){
    const name = item?.name || `文本${index + 1}`;
    const title = `${name} · ${tr('smart.inputUpstream')}`;
    return `<div class="input-thumb input-thumb-text" draggable="false" data-text-index="${index}" data-name="${escapeHtml(name)}" title="${escapeHtml(title)}"><div class="media-thumb text-thumb"><div class="text-thumb-art" aria-hidden="true"><i data-lucide="type"></i></div><span class="text-thumb-footer">${escapeHtml(name)}</span></div></div>`;
}
// ❌ 语义（老王 2026-10-19 定）：上游节点只有这一张 → 剪断连线；上游是多图 → 只屏蔽这一张。
function inputThumbMediaCount(sourceNode){
    if(!sourceNode) return 0;
    return imagesForNode(sourceNode).filter(img => img?.url && ['image','video','audio','file'].includes(mediaKindForItem(img))).length;
}
function inputThumbCutTitle(img){
    const source = nodes.find(n => n.id === img?.nodeId);
    return inputThumbMediaCount(source) > 1 ? tr('smart.inputClickBlock') : tr('smart.cutInputWire');
}
function cutOrBlockInputThumb(node, img){
    if(!node || !img?.url) return;
    if(isInputRefBlocked(node, img)){
        toggleInputRefBlocked(node, img);
        renderInputThumbsRow(node);
        return;
    }
    const source = nodes.find(n => n.id === img.nodeId);
    if(inputThumbMediaCount(source) > 1){
        toggleInputRefBlocked(node, img);
        renderInputThumbsRow(node);
        return;
    }
    const index = (canvas?.connections || []).findIndex(conn => conn.from === img.nodeId && conn.to === node.id && ['input','flow'].includes(conn.kind || 'flow'));
    if(index >= 0){
        disconnectConnection(index);
        renderInputThumbsRow(node);
        return;
    }
    toggleInputRefBlocked(node, img);
    renderInputThumbsRow(node);
}
function ensurePromptCaretInEditor(){
    if(!promptInput) return;
    promptInput.focus();
    const sel = window.getSelection();
    if(sel?.rangeCount){
        const range = sel.getRangeAt(0);
        const container = range.startContainer;
        if(container && (container === promptInput || promptInput.contains(container))) return;
    }
    const range = document.createRange();
    range.selectNodeContents(promptInput);
    range.collapse(false);
    if(sel){
        sel.removeAllRanges();
        sel.addRange(range);
    }
    mentionRange = range.cloneRange();
}
function referenceInputThumbToPrompt(node, img){
    if(!node || !img?.url) return;
    ensurePromptCaretInEditor();
    insertMentionToken(img);
}
function bindInputThumbHoverActions(node, items){
    if(!inputThumbsRow || !node) return;
    inputThumbsRow.querySelectorAll('.input-thumb').forEach(el => {
        const url = el.dataset.sourceUrl || el.dataset.url || '';
        const kind = el.dataset.kind || '';
        if(!url || !['image','video'].includes(kind)) return;
        el.addEventListener('mouseenter', () => showInputThumbHoverPreview(el, url, kind));
        el.addEventListener('mouseleave', hideInputThumbHoverPreview);
    });
    inputThumbsRow.querySelectorAll('[data-thumb-cut]').forEach(btn => {
        btn.onclick = event => {
            event.preventDefault();
            event.stopPropagation();
            cutOrBlockInputThumb(node, (items || [])[Number(btn.dataset.thumbCut)]);
        };
    });
    inputThumbsRow.querySelectorAll('[data-thumb-at]').forEach(btn => {
        btn.onclick = event => {
            event.preventDefault();
            event.stopPropagation();
            referenceInputThumbToPrompt(node, (items || [])[Number(btn.dataset.thumbAt)]);
        };
    });
}
// 悬停缩略图：显示大图（与提示词框里 @ 引用 token 悬停同一个预览框）
function showInputThumbHoverPreview(el, url, kind){
    if(!mentionPreview || !url) return;
    let media = mentionPreview.querySelector('img,video');
    const isVideo = kind === 'video';
    if(isVideo && media?.tagName?.toLowerCase() !== 'video'){
        media?.replaceWith(document.createElement('video'));
        media = mentionPreview.querySelector('video');
    } else if(!isVideo && media?.tagName?.toLowerCase() !== 'img'){
        media?.replaceWith(document.createElement('img'));
        media = mentionPreview.querySelector('img');
    }
    if(!media) return;
    if(isVideo){
        media.muted = true;
        media.loop = true;
        media.playsInline = true;
        media.preload = 'metadata';
        media.disablePictureInPicture = true;
        media.setAttribute('disablepictureinpicture', '');
        media.setAttribute('controlslist', 'nodownload noplaybackrate noremoteplayback');
        media.src = url;
        media.play?.().catch(() => {});
    } else {
        media.src = url;
        media.alt = 'preview';
    }
    const rect = el.getBoundingClientRect();
    mentionPreview.style.left = `${Math.max(4, Math.min(window.innerWidth - 236, rect.left))}px`;
    mentionPreview.style.top = `${Math.max(4, Math.min(window.innerHeight - 236, rect.bottom + 8))}px`;
    mentionPreview.style.display = 'block';
}
function hideInputThumbHoverPreview(){
    if(!mentionPreview) return;
    mentionPreview.style.display = 'none';
    const media = mentionPreview.querySelector('img,video');
    media?.pause?.();
    media?.removeAttribute('src');
    media?.load?.();
}
// 2026-10-19 老王：屏蔽的输入不再占缩略图行的位（不渲染灰卡），改在行右端出一个「已屏蔽 X」胶囊，点它恢复该张。
function inputThumbBlockedChipsHtml(blockedItems){
    if(!blockedItems?.length) return '';
    const chips = blockedItems.map((img, i) => {
        const name = img.name || tr('smart.inputNum').replace('{n}', String(i + 1));
        const label = `${tr('smart.inputBlocked')} ${name}`;
        const title = `${label} · ${tr('smart.unblockInput')}`;
        return `<button class="smart-pill input-thumb-unblock" type="button" data-thumb-unblock="${i}" title="${escapeAttr(title)}" aria-label="${escapeAttr(title)}"><i data-lucide="eye-off"></i><span>${escapeHtml(label)}</span></button>`;
    }).join('');
    return `<div class="input-thumb-unblock-actions">${chips}</div>`;
}
function bindInputThumbBlockedChips(node, blockedItems){
    if(!inputThumbsRow || !node) return;
    inputThumbsRow.querySelectorAll('[data-thumb-unblock]').forEach(btn => {
        btn.onclick = event => {
            event.preventDefault();
            event.stopPropagation();
            const img = (blockedItems || [])[Number(btn.dataset.thumbUnblock)];
            if(!img) return;
            toggleInputRefBlocked(node, img);
            renderInputThumbsRow(node);
        };
    });
}
function renderInputThumbsRow(node){
    if(!inputThumbsRow) return;
    syncJimengModelPillForRefs();
    syncJimengVideoModelPillForRefs();
    const dedup = node ? visibleReferenceImagesFor(node) : [];
    const textItems = inputTextThumbItems(node);
    // 屏蔽的输入：不占位、不计数，只留右端恢复胶囊
    const blockedItems = node ? dedup.filter(img => isInputRefBlocked(node, img)) : [];
    const displayItems = node ? dedup.filter(img => !isInputRefBlocked(node, img)) : dedup;
    const unblockActions = inputThumbBlockedChipsHtml(blockedItems);
    // 无线模式：即使还没有任何输入，也保留“引用结果”入口
    // 2026-09-16 老王：只留图标（文字改由 hover 的 title 说明），并浮到卡片右上角
    const objectRefActions = (node && canvasObjectsMode())
        ? `<div class="input-thumb-actions"><button class="smart-pill input-object-ref-btn" type="button" data-object-ref-open="1" title="${escapeAttr(tr('smart.objectRefTip'))}" aria-label="${escapeAttr(tr('smart.objectRef'))}"><i data-lucide="waypoints"></i></button></div>`
        : '';
    inputThumbsRow.classList.toggle('has-items', displayItems.length > 0 || textItems.length > 0 || Boolean(unblockActions) || Boolean(objectRefActions));
    const videoQuickActions = '';
    if(!displayItems.length && !textItems.length){
        inputThumbsRow.innerHTML = `${videoQuickActions}${unblockActions}${objectRefActions}`;
        inputThumbsRow.classList.toggle('has-items', Boolean(videoQuickActions || unblockActions || objectRefActions));
        bindInputThumbVideoActions();
        bindCanvasObjectRefActions(node);
        bindInputThumbBlockedChips(node, blockedItems);
        if(window.lucide) lucide.createIcons();
        return;
    }
    let audioCount = 0;
    let videoCount = 0;
    const thumbsHtml = displayItems.map((img, i) => {
        const kind = mediaKindForItem(img);
        const isVid = kind === 'video';
        const isAudio = kind === 'audio';
        const audioIndex = isAudio ? ++audioCount : 0;
        const isSelf = node ? isSelfReferenceForNode(node, img) : false;
        const title = isSelf
            ? tr('smart.inputSelf')
            : (smartImageMode(node) === 'workflow' ? tr('smart.inputUpstreamWorkflow') : tr('smart.inputUpstream'));
        const sourceUrl = img.originalLocalUrl || img.url || '';
        const displayName = img.name || tr('smart.inputNum').replace('{n}', String(i + 1));
        const videoLabel = isVid ? `视频${++videoCount}` : '';
        const inner = isAudio
            ? audioThumbHtml(audioThumbLabel(img, audioIndex), ` title="${escapeAttr(displayName)}"`)
            : (isVid ? videoInputThumbHtml(img, videoLabel, ` title="${escapeAttr(displayName)}"`) : thumbMediaHtml(img));
        const objectRefId = img.objectReferenceId || '';
        const removeBtn = objectRefId
            ? `<button class="input-thumb-unset" type="button" title="${escapeAttr(tr('smart.removeObjectRef'))}" data-object-ref-remove="${escapeAttr(objectRefId)}"><i data-lucide="x"></i></button>`
            : '';
        // 2026-10-19 老王：上游素材缩略图悬停 → 右上角 ❌（剪断/屏蔽该输入）、中下 @（引用到提示词光标处）
        const wired = !isSelf && !objectRefId && Boolean(img.nodeId);
        const cutTitle = inputThumbCutTitle(img);
        const cutBtn = wired
            ? `<button class="input-thumb-cut" type="button" title="${escapeAttr(cutTitle)}" aria-label="${escapeAttr(cutTitle)}" data-thumb-cut="${i}"><i data-lucide="x"></i></button>`
            : '';
        const atBtn = wired && ['image','video','audio'].includes(kind)
            ? `<button class="input-thumb-at" type="button" title="${escapeAttr(tr('smart.refToPrompt'))}" aria-label="${escapeAttr(tr('smart.refToPrompt'))}" data-thumb-at="${i}">@</button>`
            : '';
        return `<div class="input-thumb ${isSelf ? 'input-self' : ''} ${objectRefId ? 'input-thumb-object-ref' : ''}" draggable="false" data-thumb-index="${i}" data-node-id="${escapeHtml(img.nodeId || '')}" data-image-index="${img.imageIndex ?? ''}" data-url="${escapeHtml(img.url || '')}" data-source-url="${escapeHtml(sourceUrl)}" data-kind="${escapeHtml(kind)}" data-object-ref="${escapeAttr(objectRefId)}" data-name="${escapeHtml(displayName)}" title="${escapeHtml(`${displayName} · ${title}`)}">${inner}${removeBtn}${cutBtn}${atBtn}</div>`;
    }).join('');
    // ComfyUI 缩略图只显示上游素材本身，不额外添加说明文字。
    const textThumbsHtml = textItems.map((item, index) => inputTextThumbHtml(item, index)).join('');
    inputThumbsRow.innerHTML = `<div class="input-thumb-list">${thumbsHtml}${textThumbsHtml}</div>${unblockActions}${videoQuickActions}${objectRefActions}`;
    bindInputThumbsDrag(node, displayItems);
    bindInputThumbVideoActions();
    bindCanvasObjectRefActions(node);
    bindInputThumbHoverActions(node, displayItems);
    bindInputThumbBlockedChips(node, blockedItems);
    if(window.lucide) lucide.createIcons();
}
// ===== 无线引用（引用结果）：选择器 =====
var canvasObjectRefPickerOpen = false;  // 2026-10-15: must hoist - render() runs at line 237, before this let would initialize (TDZ ReferenceError killed every ui_baseline case).
let canvasObjectRefConsumerId = '';
let canvasObjectRefQuery = '';
let canvasObjectRefKind = 'all';
function canvasObjectRefPickerEl(){ return document.getElementById('canvasObjectRefPicker'); }
function canvasObjectRefDocumentClose(event){
    if(!canvasObjectRefPickerOpen) return;
    const el = canvasObjectRefPickerEl();
    if(!el || el.contains(event.target)) return;
    if(event.target?.closest?.('[data-object-ref-open]')) return;
    closeCanvasObjectRefPicker();
}
document.addEventListener('pointerdown', canvasObjectRefDocumentClose, true);
// 对象引用选择器+缩略图拖拽带外移 canvas-object-ref-picker.js（第二十刀）。picker 四态+拖拽态写入走 setter。
if(globalThis.CanvasObjectRefPicker){CanvasObjectRefPicker.configure({
        canvasNodeResultKind: (...a) => canvasNodeResultKind(...a),
        canvasObjectRefPickerEl: (...a) => canvasObjectRefPickerEl(...a),
        canvasObjectReferencesFor: (...a) => canvasObjectReferencesFor(...a),
        disconnectCanvasObjectReference: (...a) => disconnectCanvasObjectReference(...a),
        canvasSetSourceNodes: (...a) => canvasSetSourceNodes(...a),
        canvasThumbnailUrl: (...a) => canvasThumbnailUrl(...a),
        escapeHtml: (...a) => escapeHtml(...a),
        imagesForNode: (...a) => imagesForNode(...a),
        pushUndo: (...a) => pushUndo(...a),
        renderInputThumbsRow: (...a) => renderInputThumbsRow(...a),
        scheduleSave: (...a) => scheduleSave(...a),
        setCurrentSmartManualVideoUrl: (...a) => setCurrentSmartManualVideoUrl(...a),
        toast: (...a) => toast(...a),
        uid: (...a) => uid(...a),
        uploadCurrentSmartVideosToCloud: (...a) => uploadCurrentSmartVideosToCloud(...a),
        canvasObjectRefConsumerId: () => canvasObjectRefConsumerId,
        canvasObjectRefKind: () => canvasObjectRefKind,
        canvasObjectRefPickerOpen: () => canvasObjectRefPickerOpen,
        canvasObjectRefQuery: () => canvasObjectRefQuery,
        inputThumbDragState: () => inputThumbDragState,
        escapeAttr: () => escapeAttr,
        inputThumbsRow: () => inputThumbsRow,
        nodes: () => nodes,
        setCanvasObjectRefConsumerId: v => { canvasObjectRefConsumerId = v; },
        setCanvasObjectRefKind: v => { canvasObjectRefKind = v; },
        setCanvasObjectRefPickerOpen: v => { canvasObjectRefPickerOpen = v; },
        setCanvasObjectRefQuery: v => { canvasObjectRefQuery = v; },
        setInputThumbDragState: v => { inputThumbDragState = v; }
});}
function closeCanvasObjectRefPicker(){return CanvasObjectRefPicker.closeCanvasObjectRefPicker.apply(null, arguments);}
function renderCanvasObjectRefPicker(){return CanvasObjectRefPicker.renderCanvasObjectRefPicker.apply(null, arguments);}
function bindCanvasObjectRefActions(){return CanvasObjectRefPicker.bindCanvasObjectRefActions.apply(null, arguments);}
function bindInputThumbsDrag(){return CanvasObjectRefPicker.bindInputThumbsDrag.apply(null, arguments);}
function bindInputThumbVideoActions(){return CanvasObjectRefPicker.bindInputThumbVideoActions.apply(null, arguments);}
function reorderInputThumb(){return CanvasObjectRefPicker.reorderInputThumb.apply(null, arguments);}
function isSupportedUploadFile(){return CanvasObjectRefPicker.isSupportedUploadFile.apply(null, arguments);}
CanvasImageDropPayload.configure({isSupportedUploadFile});
CanvasImageNodeMediaController.configure({
    getNodes: () => nodes,
    selectedNode: () => selectedNode(),
    isImageNode: node => isSmartImageNode(node),
    viewportCenter: () => viewportCenter(),
    createEmptyNodeAt: point => {
        undoSuppressed = true;
        try { return createImageNodeAt(point, []); }
        finally { undoSuppressed = false; }
    },
    nodeRect: node => nodeRect(node),
    findFreeSpot: (x, y, w, h) => agentFindEmptySpot(x, y, w, h),
    createNodeWithImage: (point, image) => {
        undoSuppressed = true;
        try { return createImageNodeAt(point, [image]); }
        finally { undoSuppressed = false; }
    },
    isFile: value => typeof File !== 'undefined' && value instanceof File,
    mediaKindForFile: file => mediaKindForFile(file),
    mediaKindForItem: item => mediaKindForItem(item),
    defaultImageNodeScale: MEDIA_NODE_DEFAULT_SCALE,
    defaultGroupNodeScale: MEDIA_GROUP_DEFAULT_SCALE,
    previousGroupNodeScale: MEDIA_GROUP_PREVIOUS_DEFAULT_SCALE,
    setSelectedId: value => { canvasUiState.patchSelection({primaryId: value}, 'selectedId'); },
    render: () => render(),
    scheduleSave: () => scheduleSave()
});
function uploadTitleForItems(items, fallback='Upload'){
    return CanvasImageNodeMediaController.uploadTitleForItems(items, fallback);
}
async function smartResponseErrorMessage(response, fallback='请求失败'){
    try {
        const data = await response.clone().json();
        const detail = data.detail ?? data.error ?? data.message;
        if(typeof detail === 'string') return detail || fallback;
        if(Array.isArray(detail)) return detail.map(item => item?.msg || item?.message || String(item)).join('\n') || fallback;
    } catch(_) {}
    try {
        const text = await response.text();
        if(text) return text;
    } catch(_) {}
    return fallback;
}
function setSmartDropCopyEffect(e, includeAsset=false){
    e.preventDefault();
    if(CanvasImageDropPayload.hasInputThumb(e.dataTransfer)) return;
    if(CanvasImageDropPayload.hasImageData(e.dataTransfer) || (includeAsset && CanvasImageDropPayload.hasAsset(e.dataTransfer))){
        e.dataTransfer.dropEffect = 'copy';
    }
}
CanvasImageImportController.configure({
    fetcher: (...args) => fetch(...args),
    isSupportedUploadFile: file => isSupportedUploadFile(file),
    mediaKindForFile: file => mediaKindForFile(file),
    responseErrorMessage: (...args) => smartResponseErrorMessage(...args),
    uploadFailMessage: () => tr('smart.toastUploadFail'),
    pushUndo: () => pushUndo(),
    uploadUrl: () => canvasScopedUploadUrl(),
    appendImagesToNode: (...args) => appendImagesToSmartNode(...args),
    imageNameFromUrl: url => CanvasImageDropPayload.imageNameFromUrl(url),
    toast: message => toast(message)
});
async function uploadFiles(files){
    return CanvasImageImportController.uploadFiles(files);
}
function appendImagesToSmartNode(uploaded, targetId='', opts={}){
    return CanvasImageNodeMediaController.appendImages(uploaded, targetId, opts);
}
async function handleFiles(files, targetId='', opts={}){
    return CanvasImageImportController.handleFiles(files, targetId, opts);
}
async function handleSmartImageDropPayload(payload, targetId='', opts={}){
    return CanvasImageImportController.handleDropPayload(payload, targetId, opts);
}
function sizeForRun(sourceSettings=settings){
    return apiImageSize(sourceSettings.ratio || 'square', sourceSettings.resolution || '1k', sourceSettings.customRatio || '', sourceSettings.customSize || '') || '1024x1024';
}
function expectedOutputSize(){
    if(settings.engine === 'comfy'){
        if(settings.comfyMode === 'text'){
            const w = Number(settings.width) || 1024;
            const h = Number(settings.height) || 1024;
            return {w, h};
        }
        // comfy 图像工作流的真实尺寸由工作流内的分辨率节点决定，composer 的 comfy-layout 里
        // 也根本没有比例控件（settings.ratio 对它无意义），所以维持 1024×1024 中性方图。
        return {w:1024, h:1024};
    }
    // 2026-10-06（老王："工作流类的任务怎么一运行，节点就先变成正方形窗口？而不是按设定的比例显示窗口"）：
    // runninghub 原来在这里直接 return {w:1024,h:1024}。RH 的比例是随请求发给后端的（sizeForRun），
    // 输出真的就是面板选的那个比例，硬编码方图等于骗人 —— 一运行，占位框走
    // displayBoxFromNaturalSize(1024×1024) 被 singleImageLayout 的 520×440 上限一夹，
    // 就成了 440×440 的正方形，面板选 16:9 完全不起作用（API 类走 isApiLikeEngine 分支，一直是对的）。
    // 现在删掉这行 → 落到下面的 sizeForRun()，与 API 类口径一致。
    // ⚠️ expectedOutputSize 全局只有 pendingBaseBoxSize 一个调用方，且只在
    //    explicitRequestOutputSizeForPending / pendingSourceBoxSize 都没结论时才轮到，
    //    改它只影响「运行中占位框的形状」，不碰任何真实请求尺寸。
    const sizeStr = sizeForRun();
    const parsed = parseSizeValue(sizeStr);
    if(parsed){
        return {w: Number(parsed.width) || 1024, h: Number(parsed.height) || 1024};
    }
    return {w:1024, h:1024};
}
function explicitRequestOutputSizeForPending(){
    if(isApiLikeEngine(settings.engine) && settings.apiKind !== 'video'){
        const parsed = parseSizeValue(sizeForRun());
        if(parsed) return {w:Number(parsed.width) || 1024, h:Number(parsed.height) || 1024};
    }
    if(settings.engine === 'comfy' && settings.comfyMode === 'text'){
        const w = Number(settings.width) || 1024;
        const h = Number(settings.height) || 1024;
        return {w, h};
    }
    // comfy 自定义工作流 + 视频：占位框按面板选的视频比例算，不能跟输入参考图走。
    // 否则竖版参考图（如 1152x2048）会把 16:9 的视频占位框拉成 9:16，用户以为设置没生效。
    // 输出真实尺寸由工作流内部分辨率节点决定，这里只负责把"用户选的比例"显示出来。
    if(settings.engine === 'comfy' && settings.comfyMode === 'custom' && settings.apiKind === 'video'){
        const am = String(settings.videoAspect || '').match(/^(\d+)\s*:\s*(\d+)$/);
        if(am){
            const aw = Number(am[1]) || 16;
            const ah = Number(am[2]) || 9;
            const base = 480;   // 短边取 480：占位框只需要比例正确，displayBoxFromNaturalSize 会再做布局缩放
            return aw >= ah ? {w: Math.round(base * aw / ah), h: base} : {w: base, h: Math.round(base * ah / aw)};
        }
    }
    return null;
}
function pendingSizeFromImageRef(img){
    const w = Number(img?.natural_w || img?.width || 0);
    const h = Number(img?.natural_h || img?.height || 0);
    return w > 0 && h > 0 ? {w, h} : null;
}
function pendingSourceBoxSize(options={}){
    const sourceNode = options.sourceNode || null;
    if(sourceNode && (sourceNode.images || []).length){
        const rect = nodeRect(sourceNode);
        if(rect.width > 24 && rect.height > 24) return {w:Math.round(rect.width), h:Math.round(rect.height), display:true};
    }
    const ref = (options.refs || []).find(img => img?.url);
    const refSize = pendingSizeFromImageRef(ref);
    if(refSize) return refSize;
    const refNode = ref?.nodeId ? nodes.find(n => n.id === ref.nodeId) : null;
    if(refNode){
        const rect = nodeRect(refNode);
        if(rect.width > 24 && rect.height > 24) return {w:Math.round(rect.width), h:Math.round(rect.height), display:true};
    }
    return null;
}
function displayBoxFromNaturalSize(size){
    const layout = singleImageLayout(
        {natural_w:size?.w || size?.width || 1024, natural_h:size?.h || size?.height || 1024},
        {type:'smart-image', images:[{}]},
        MEDIA_NODE_DEFAULT_SCALE
    );
    return {w:layout.width, h:layout.height};
}
function pendingBaseBoxSize(options={}){
    const savedCard = options.sourceNode?.cardSize;
    if(Number(savedCard?.width) > 24 && Number(savedCard?.height) > 24){
        return {w:Math.round(savedCard.width), h:Math.round(savedCard.height)};
    }
    // 2026-10-10：占位框走统一的按比例默认盒（此前 displayBoxFromNaturalSize 把 16:9 夹成
    // 520×293，与空卡的 512×288 差一点点，看着就像"两套尺寸"）。
    const requestSize = explicitRequestOutputSizeForPending();
    if(requestSize) return mediaBoxForRatio(requestSize);
    const sourceSize = pendingSourceBoxSize(options);
    if(sourceSize?.display) return {w:sourceSize.w, h:sourceSize.h};
    if(sourceSize) return mediaBoxForRatio(sourceSize);
    return mediaBoxForRatio(expectedOutputSize());
}
function pendingBoxSize(count, options={}){
    const base = pendingBaseBoxSize(options);
    const aspect = base.w / Math.max(1, base.h);
    const c = Math.max(1, Number(count) || 1);
    if(c <= 1){
        return {w:Math.round(base.w), h:Math.round(base.h)};
    }
    const cols = Math.min(4, Math.max(2, Math.ceil(Math.sqrt(c))));
    const rows = Math.ceil(c / cols);
    const cellMax = Math.max(96, Math.min(220, Math.max(base.w, base.h) * 0.42));
    let cellW, cellH;
    if(base.w >= base.h){
        cellW = cellMax;
        cellH = Math.max(40 * MEDIA_NODE_DEFAULT_SCALE, Math.round(cellMax / aspect));
    } else {
        cellH = cellMax;
        cellW = Math.max(40 * MEDIA_NODE_DEFAULT_SCALE, Math.round(cellMax * aspect));
    }
    const w = cols * (cellW + 8) + 16;
    const h = rows * (cellH + 8) + 16;
    return {w, h};
}
function mentionTokenHtml(img){
 if(!img?.url) return '';
 const name = img.alias || img.name || '图片';
 const kind = mediaKindForItem(img);
    const media = kind === 'video'
        ? `<video src="${escapeHtml(img.url)}" muted preload="metadata" playsinline disablepictureinpicture controlslist="nodownload noplaybackrate noremoteplayback"></video>`
        : (kind === 'audio'
            ? `<span class="mention-audio-token-art" aria-hidden="true"><i data-lucide="music"></i></span>`
            : `<img src="${escapeHtml(img.url)}" alt="">`);
 return `<span class="mention-image-token" contenteditable="false" data-url="${escapeHtml(img.url)}" data-kind="${escapeHtml(kind)}" data-name="${escapeHtml(name)}" data-node-id="${escapeHtml(img.nodeId || '')}" data-image-index="${escapeHtml(img.imageIndex ?? '')}">${media}<span>${escapeHtml(name)}</span>${promptImageMentionRemoveButtonHtml()}</span>`;
}
function promptImageMentionRemoveButtonHtml(){
 const label = escapeHtml(tr('common.delete'));
 return `<button class="mention-image-token-remove" type="button" title="${label}" aria-label="${label}"></button>`;
}
function mentionImageTokenAdjacentToCaret(direction){
 const selection = window.getSelection();
 if(!selection?.rangeCount || !selection.isCollapsed) return null;
 const node = selection.anchorNode;
 const offset = selection.anchorOffset;
 if(!node || (node !== promptInput && !promptInput.contains(node))) return null;
 let candidate = null;
 if(node.nodeType === Node.TEXT_NODE){
  const text = node.textContent || '';
  if(direction === 'backward'){
   if(offset !== 0) return null;
   candidate = node.previousSibling;
  } else {
   if(offset !== text.length) return null;
   candidate = node.nextSibling;
  }
 } else if(node.nodeType === Node.ELEMENT_NODE){
  candidate = node.childNodes[direction === 'backward' ? offset - 1 : offset] || null;
 }
 while(candidate?.nodeType === Node.TEXT_NODE && !candidate.textContent){
  candidate = direction === 'backward' ? candidate.previousSibling : candidate.nextSibling;
 }
 return candidate?.classList?.contains('mention-image-token') ? candidate : null;
}
function removePromptImageMention(token){
 if(!promptInput || !token || !promptInput.contains(token)) return false;
 const parent = token.parentNode;
 const tokenIndex = Array.prototype.indexOf.call(parent.childNodes, token);
 const previous = token.previousSibling;
 const next = token.nextSibling;
 if(next?.nodeType === Node.TEXT_NODE && /^[ \u00a0]/.test(next.textContent || '')){
  next.textContent = next.textContent.slice(1);
 }
 token.remove();
 if(mentionPreview){
  mentionPreview.style.display = 'none';
  const previewMedia = mentionPreview.querySelector('img,video');
  previewMedia?.pause?.();
  previewMedia?.removeAttribute('src');
  previewMedia?.load?.();
 }
 const subject = activeComposerNode();
 if(subject) subject.promptDraftRefsEdited = true;
 promptInput.focus();
 const range = document.createRange();
 if(previous?.nodeType === Node.TEXT_NODE && promptInput.contains(previous)){
  range.setStart(previous, previous.textContent.length);
 } else if(next?.nodeType === Node.TEXT_NODE && promptInput.contains(next)){
  range.setStart(next, 0);
 } else {
  range.setStart(parent, Math.min(tokenIndex, parent.childNodes.length));
 }
 range.collapse(true);
 const selection = window.getSelection();
 if(selection){
  selection.removeAllRanges();
  selection.addRange(range);
 }
 promptInput.dispatchEvent(new Event('input', {bubbles:true}));
 return true;
}
function insertImageReferenceIntoPrompt(ref){
 if(!promptInput || !ref?.url) return false;
 const exists = [...promptInput.querySelectorAll('.mention-image-token')].some(token => token.dataset.url === ref.url);
 if(!exists){
 const thumbList = mentionThumbnailCandidates(selectedNode());
 const count = [...promptInput.querySelectorAll('.mention-image-token')].length;
     const posAlias = mentionThumbAlias(ref, thumbList) || `${mentionKindLabel(mediaKindForItem(ref))}${count + 1}`;
 const tokenRef = {...ref, alias:posAlias};
 const tokenHtml = mentionTokenHtml(tokenRef);
 if(!tokenHtml) return false;
 const prefix = promptInput.textContent.trim() || promptInput.querySelector('.mention-image-token') ? ' ' : '';
 promptInput.insertAdjacentHTML('beforeend', `${prefix}${tokenHtml} `);
 }
 promptInput.focus();
 renderInputThumbsRow(selectedNode());
 return true;
}
function promptHtmlWithMentionTokens(text, refs=[]){
    const value = String(text || '');
    const items = (refs || []).filter(ref => ref?.url && ref?.name).sort((a, b) => String(b.name || '').length - String(a.name || '').length);
    if(!value || !items.length || !value.includes('@')) return '';
    let html = '';
    let index = 0;
    while(index < value.length){
        if(value[index] === '@'){
            const hit = items.find(ref => value.slice(index + 1, index + 1 + String(ref.name || '').length) === String(ref.name || ''));
            if(hit){
                html += mentionTokenHtml(hit);
                index += 1 + String(hit.name || '').length;
                continue;
            }
        }
        html += escapeHtml(value[index]);
        index += 1;
    }
    return html;
}
function snapshotRunMeta(prompt, sourceId, displayPrompt='', refs=[]){
    return {
        prompt,
        displayPrompt:displayPrompt || promptPlainText() || prompt,
        promptHtml: promptInput ? promptInput.innerHTML : '',
        promptText: promptPlainText(),
        promptRefs:(refs || []).map(ref => ({url:ref.url || '', name:ref.name || '', nodeId:ref.nodeId || '', imageIndex:ref.imageIndex ?? ''})).filter(ref => ref.url),
        inputRefs:(refs || []).map(ref => ({url:ref.url || '', name:ref.name || '', nodeId:ref.nodeId || '', imageIndex:ref.imageIndex ?? '', kind:ref.kind || ''})).filter(ref => ref.url),
        sourceNodeId:sourceId,
        settings:JSON.parse(JSON.stringify(settings)),
        createdAt:Date.now()
    };
}
function attachRunMeta(targetNode, meta){
    if(!targetNode || !meta) return;
    targetNode.runPrompt = meta.displayPrompt || meta.promptText || meta.prompt;
    targetNode.runModelPrompt = meta.prompt;
    targetNode.runPromptRefs = meta.promptRefs || [];
    targetNode.runInputRefs = (meta.inputRefs || meta.promptRefs || []).map(ref => ({
        url:ref.url || '',
        name:ref.name || '',
        nodeId:ref.nodeId || '',
        imageIndex:ref.imageIndex ?? '',
        kind:ref.kind || ''
    })).filter(ref => ref.url);
    targetNode.runSettings = meta.settings;
    if(meta.sourceNodeId) targetNode.sourceNodeId = meta.sourceNodeId;
    else delete targetNode.sourceNodeId;
    targetNode.runAt = meta.createdAt;
    // 保存可编辑的 @-提及表单到草稿字段，方便点输出节点时还原原始可编辑形式
    if(meta.promptHtml != null){
        const htmlHasToken = promptHtmlHasMentionToken(meta.promptHtml);
        const rebuiltHtml = htmlHasToken ? '' : promptHtmlWithMentionTokens(meta.displayPrompt || meta.promptText || '', meta.promptRefs || []);
        targetNode.promptDraftHtml = htmlHasToken ? meta.promptHtml : (rebuiltHtml || meta.promptHtml);
        targetNode.promptDraftText = meta.promptText || '';
    }
    targetNode.images = (targetNode.images || []).map(img => stripImageGenerationMeta(img));
}
function stripRunInputMeta(meta){
    if(!meta) return meta;
    const cleanPrompt = meta.promptText || meta.displayPrompt || meta.prompt || '';
    return {
        ...meta,
        promptHtml:escapeHtml(cleanPrompt),
        promptText:cleanPrompt,
        promptRefs:[],
        inputRefs:meta.inputRefs || meta.promptRefs || [],
        sourceNodeId:''
    };
}
function stripImageGenerationMeta(img){
    if(!img) return img;
    delete img.runPrompt;
    delete img.runModelPrompt;
    delete img.runSettings;
    delete img.sourceNodeId;
    delete img.runAt;
    delete img.promptDraftHtml;
    delete img.promptDraftText;
    if(mediaKindForItem(img) === 'text'){
        img.textContent = textContentValue(img);
        img.textPreview = textPreviewSnippet(img.textPreview || img.textContent);
    }
    return img;
}
function addConnection(fromId, toId, kind='flow'){
    if(!fromId || !toId || fromId === toId) return;
    canvas.connections = canvas.connections || [];
    if(canvas.connections.some(c => c.from === fromId && c.to === toId && (c.kind || 'flow') === kind)) return;
    canvas.connections.push({from:fromId, to:toId, kind});
}
// ===== 2026-10-19 老王：连“组”= 把组内每张图各自连上（不再只连一根组线）。
// 这样缩略图行里每张图都有自己的线，❌ 直接剪它自己那根（剪断后提示词里的引用随之降级）。=====
function groupSourceNodeIds(node, visited=new Set()){
    if(!node || !node.id) return [];
    if(!isCanvasGroupNode(node)) return [node.id];
    if(visited.has(node.id)) return [];
    visited.add(node.id);
    return (Array.isArray(node.memberIds) ? node.memberIds : [])
        .flatMap(id => groupSourceNodeIds(nodes.find(n => n.id === id), visited));
}
// 把已有的“组线”就地展开成成员线（幂等：展开后不再有组线）
function expandGroupConnections(groupId){
    if(!canvas || !Array.isArray(canvas.connections) || !groupId) return 0;
    const group = nodes.find(n => n.id === groupId);
    if(!group || !isCanvasGroupNode(group)) return 0;
    const memberIds = groupSourceNodeIds(group).filter(id => id !== groupId);
    if(!memberIds.length) return 0;
    let expanded = 0;
    const next = [];
    canvas.connections.forEach(conn => {
        const kind = conn.kind || 'flow';
        if(conn.from !== groupId || !['input', 'flow'].includes(kind)){
            next.push(conn);
            return;
        }
        memberIds.forEach(id => {
            if(id === conn.to) return;
            if(next.some(c => c.from === id && c.to === conn.to && (c.kind || 'flow') === kind)) return;
            next.push({...conn, from:id});
        });
        const toNode = nodes.find(n => n.id === conn.to);
        if(toNode && Array.isArray(toNode.inputNodeIds)){
            toNode.inputNodeIds = Array.from(new Set([...(toNode.inputNodeIds || []).filter(x => x !== groupId), ...memberIds.filter(id => id !== conn.to)]));
        }
        expanded += 1;
    });
    if(expanded) canvas.connections = next;
    return expanded;
}
function migrateGroupConnectionsToMemberLines(){
    if(!canvas || !Array.isArray(canvas.connections)) return 0;
    let changed = 0;
    nodes.filter(n => isCanvasGroupNode(n)).forEach(group => { changed += expandGroupConnections(group.id); });
    return changed;
}
// 新加入组的成员：自动连到“组内其它成员已经在喂的目标”
function connectNewGroupMemberConnections(group, memberId){
    if(!canvas || !Array.isArray(canvas.connections) || !group || !memberId) return 0;
    if(!isCanvasGroupNode(group)) return 0;
    const others = groupSourceNodeIds(group).filter(id => id !== group.id && id !== memberId);
    if(!others.length) return 0;
    const targets = new Set();
    canvas.connections.forEach(conn => {
        const kind = conn.kind || 'flow';
        if(!['input', 'flow'].includes(kind)) return;
        if(conn.from === group.id || others.includes(conn.from)) targets.add(conn.to);
    });
    let added = 0;
    targets.forEach(toId => { if(toId !== memberId && connectInputNode(memberId, toId)) added += 1; });
    if(added) render();
    return added;
}
function connectInputNode(fromId, toId){
    const from = nodes.find(n => n.id === fromId);
    const to = nodes.find(n => n.id === toId);
    if(!from || !to || from.id === to.id) return false;
    // 连“组”= 组内每张图各自连一条线（老王 2026-10-19）
    if(isCanvasGroupNode(from)){
        const memberIds = groupSourceNodeIds(from).filter(id => id !== to.id);
        if(memberIds.length){
            let connected = 0;
            memberIds.forEach(id => { if(connectInputNode(id, to.id)) connected += 1; });
            return connected > 0;
        }
    }
    if(to.type === 'smart-loop'){
        const looksImage = isSmartImageNode(from) || (isCanvasGroupNode(from) && imagesForNode(from).some(img => img?.url)) || (from.type === 'smart-loop' && from.imageInput);
        const looksPrompt = from.type === 'smart-prompt' || (from.type === 'smart-loop' && from.showPrompt);
        if(looksImage && !to.imageInput) to.imageInput = true;
        if(looksPrompt && !to.showPrompt) to.showPrompt = true;
        if(looksImage || looksPrompt) fitSmartLoopNode(to);
        const canImage = Boolean(to.imageInput) && looksImage;
        const canPrompt = Boolean(to.showPrompt) && looksPrompt;
        if(!canImage && !canPrompt) return false;
    }
    to.inputNodeIds = Array.from(new Set([...(to.inputNodeIds || []), from.id]));
    addConnection(from.id, to.id, 'input');
    return true;
}
function upstreamNodesForKinds(node, kinds=['input']){
    if(!node) return [];
    const allowed = new Set(kinds);
    // Connections are authoritative. Older canvases may retain inputNodeIds after an edge is cut.
    const ids = new Set();
    (canvas?.connections || []).forEach(conn => {
        if(conn.to === node.id && allowed.has(conn.kind || 'flow')) ids.add(conn.from);
    });
    return [...ids].map(id => nodes.find(n => n.id === id)).filter(Boolean);
}
function inputNodesFor(node){
    return upstreamNodesForKinds(node, ['input']);
}
function workflowInputNodesFor(node){
    return upstreamNodesForKinds(node, ['input', 'flow']);
}
function imagesForNode(node, visitedGroups=new Set()){
    if(!node) return [];
    if(isCanvasGroupNode(node)){
        if(visitedGroups.has(node.id)) return [];
        const nextVisited = new Set(visitedGroups);
        nextVisited.add(node.id);
        return (node.memberIds || [])
            .map(id => nodes.find(candidate => candidate.id === id))
            .filter(Boolean)
            .flatMap(member => imagesForNode(member, nextVisited));
    }
    ensureNodeTextMedia(node);
    return (node?.images || []).map((img, index) => ({...imageForDisplay(img), nodeId:node.id, imageIndex:index}));
}
function nodeHasReferenceContent(node){
    return imagesForNode(node).some(img => img?.url);
}
function isSelfReferenceForNode(node, img){
    return Boolean(node?.id && img?.nodeId === node.id);
}
function candidateInputImagesFor(node, consume=false, ctx=smartLoopContext){
    const inputs = (smartImageUsesWorkflowInput(node, ctx) ? workflowInputImagesFor(node, consume, ctx) : inputImagesFor(node, consume, ctx))
        .filter(img => img?.url);
    if(!inputs.length) return [];
    if(smartImageUsesWorkflowInput(node, ctx)) return inputs;
    // 节点自身有无输出图都不影响上游输入引用（用户要求 2026-08-16：有输入节点就显示输入图缩略图）
    return inputs;
}
// 2026-10-19 老王：缩略图行顺序 = 节点自存的扁平输入图顺序（inputImageOrder，按 url 记），
// 这样每一张都能拖到任意位置（旧模型按“节点顺序 + 节点内图片顺序”成段排列，跨段的图拖不动）。
function applyInputImageOrder(node, images){
    const order = Array.isArray(node?.inputImageOrder) ? node.inputImageOrder : [];
    if(!order.length || !Array.isArray(images) || images.length < 2) return images;
    const rank = new Map();
    order.forEach((url, index) => {
        const key = String(url || '').trim();
        if(key && !rank.has(key)) rank.set(key, index);
    });
    return images.map((img, index) => ({img, index}))
        .sort((a, b) => {
            const ra = rank.has(String(a.img?.url || '')) ? rank.get(String(a.img.url)) : Number.MAX_SAFE_INTEGER;
            const rb = rank.has(String(b.img?.url || '')) ? rank.get(String(b.img.url)) : Number.MAX_SAFE_INTEGER;
            if(ra !== rb) return ra - rb;
            return a.index - b.index;   // 未登记的（新接进来的）保持在后
        })
        .map(item => item.img);
}
function defaultInputImagesFor(node, consume=false, ctx=smartLoopContext){
    // 无线引用与连线输入在这一层合流（@编号 = 缩略图行从左到右第 N 张）。
    // 顺序：有线图片在前、无线引用追加到末尾 —— 这样在无线模式下再新增引用图片会“往后排”，
    // 不会插到第一张把既有有线图片的 @编号 往后挤（老王 2026-09-29 反馈引用错乱）。
    const objectRefs = canvasObjectReferenceImages(node, ctx);
    const connected = candidateInputImagesFor(node, consume, ctx);
    if(!objectRefs.length) return applyInputImageOrder(node, connected);
    return applyInputImageOrder(node, uniqueReferenceImages([...connected, ...objectRefs]));
}
function splitSmartPromptItems(text){
    const trimmed = String(text || '').trim();
    if(!trimmed) return [];
    const numbered = trimmed.split(/\s*(?:^|\s)\d+\s*[.、)）．]\s+/).map(s => s.trim()).filter(Boolean);
    if(numbered.length >= 2) return numbered;
    const lines = trimmed.split(/\r?\n+/).map(s => s.trim()).filter(Boolean);
    return lines.length >= 2 ? lines : [trimmed];
}
function smartLoopPromptFieldValues(node){
    const fields = Array.isArray(node?.variablePrompts)
        ? node.variablePrompts.map(text => String(text || '').trim())
        : [];
    if(fields.length) return fields;
    return splitSmartPromptItems(node?.variablePrompt || '');
}
function smartLoopActivePromptFieldValues(node){
    return smartLoopPromptFieldValues(node).filter(Boolean);
}
function setSmartLoopPromptFieldValues(node, values){
    if(!node || node.type !== 'smart-loop') return;
    const fields = (values || []).map(text => String(text || '').trim());
    node.variablePrompts = fields.length ? fields : [''];
    node.variablePrompt = fields.filter(Boolean).join('\n');
}
function smartLoopPromptFieldText(node, fieldIndex){
    const values = smartLoopPromptFieldValues(node);
    return values[fieldIndex] || '';
}
function smartLoopSelectedLocalPrompt(node, ctx=smartLoopContext){
    const values = smartLoopActivePromptFieldValues(node);
    if(!values.length) return '';
    const startBase = Math.max(1, Number(node?.loopStart) || 1);
    const index = Math.max(1, Number(ctx?.index || startBase) || startBase);
    return values[(index - 1) % values.length] || '';
}
function smartLoopUpstreamPromptPreviewHeight(node){
    return smartLoopInputPromptItems(node).length ? 78 : 0;
}
const smartLoopPromptVisiting = new Set();
// smartLoop 输入图/引用数据带外移 canvas-smartloop-data.js（第二十二刀）。零整写带：4 只读 getter + 13 函数 deps。
if(globalThis.CanvasSmartLoopData){CanvasSmartLoopData.configure({
        collectPromptParts: (...a) => collectPromptParts(...a),
        defaultInputImagesFor: (...a) => defaultInputImagesFor(...a),
        imagesForNode: (...a) => imagesForNode(...a),
        inputNodesFor: (...a) => inputNodesFor(...a),
        nodeTextOutput: (...a) => nodeTextOutput(...a),
        pushUndo: (...a) => pushUndo(...a),
        renderInputThumbsRow: (...a) => renderInputThumbsRow(...a),
        scheduleSave: (...a) => scheduleSave(...a),
        smartImageUsesWorkflowInput: (...a) => smartImageUsesWorkflowInput(...a),
        smartLoopCount: (...a) => smartLoopCount(...a),
        smartLoopSelectedLocalPrompt: (...a) => smartLoopSelectedLocalPrompt(...a),
        trf: (...a) => trf(...a),
        workflowInputNodesFor: (...a) => workflowInputNodesFor(...a),
        canvas: () => canvas,
        canvasObjectReferenceTextNodes: () => canvasObjectReferenceTextNodes,
        nodes: () => nodes,
        smartLoopContext: () => smartLoopContext,
        smartLoopPromptVisiting: () => smartLoopPromptVisiting
});}
function smartLoopInputPromptItems(){return CanvasSmartLoopData.smartLoopInputPromptItems.apply(null, arguments);}
function smartLoopSelectedInputPrompt(){return CanvasSmartLoopData.smartLoopSelectedInputPrompt.apply(null, arguments);}
function smartLoopInputImages(){return CanvasSmartLoopData.smartLoopInputImages.apply(null, arguments);}
function smartLoopPreviewImages(){return CanvasSmartLoopData.smartLoopPreviewImages.apply(null, arguments);}
function outputImagesForNode(){return CanvasSmartLoopData.outputImagesForNode.apply(null, arguments);}
function selfReferenceImagesForNode(){return CanvasSmartLoopData.selfReferenceImagesForNode.apply(null, arguments);}
function textForNode(){return CanvasSmartLoopData.textForNode.apply(null, arguments);}
function promptInputNodesFor(){return CanvasSmartLoopData.promptInputNodesFor.apply(null, arguments);}
function inputPromptTextFor(){return CanvasSmartLoopData.inputPromptTextFor.apply(null, arguments);}
function upstreamLoopPromptNodesFor(){return CanvasSmartLoopData.upstreamLoopPromptNodesFor.apply(null, arguments);}
function inputImagesFor(){return CanvasSmartLoopData.inputImagesFor.apply(null, arguments);}
function workflowInputImagesFor(){return CanvasSmartLoopData.workflowInputImagesFor.apply(null, arguments);}
function inputRefKey(){return CanvasSmartLoopData.inputRefKey.apply(null, arguments);}
function blockedInputRefKeys(){return CanvasSmartLoopData.blockedInputRefKeys.apply(null, arguments);}
function isInputRefBlocked(){return CanvasSmartLoopData.isInputRefBlocked.apply(null, arguments);}
function toggleInputRefBlocked(){return CanvasSmartLoopData.toggleInputRefBlocked.apply(null, arguments);}
function defaultReferenceImagesFor(){return CanvasSmartLoopData.defaultReferenceImagesFor.apply(null, arguments);}
function lineImagesFor(){return CanvasSmartLoopData.lineImagesFor.apply(null, arguments);}
function collectMentionedImagesFromPrompt(){return CanvasSmartLoopData.collectMentionedImagesFromPrompt.apply(null, arguments);}
function uniqueReferenceImages(){return CanvasSmartLoopData.uniqueReferenceImages.apply(null, arguments);}
function visibleReferenceImagesFor(){return CanvasSmartLoopData.visibleReferenceImagesFor.apply(null, arguments);}
// @编号铁律（用户 2026-09-11 定稿）：编号=缩略图行从左到右第 N 张（图片/视频分计），
// 与点击先后无关，第 N 次 @ 它仍是图片N；拖缩略图换序后编号随新序。
function mentionThumbnailCandidates(node){
    if(!node) return [];
    const seen = new Set();
    return visibleReferenceImagesFor(node).filter(img => {
        if(!img?.url || !['image','video','audio'].includes(mediaKindForItem(img))) return false;
        if(isInputRefBlocked(node, img)) return false;   // 已屏蔽 = 不参与 @ 候选与编号
        if(seen.has(img.url)) return false;
        seen.add(img.url);
        return true;
    });
}
// 2026-10-19 老王：类型按节点里的素材定 —— 图片/视频/音频/文本，不再一律当图片
function mentionKindLabel(kind){
    return kind === 'video' ? '视频' : (kind === 'audio' ? '音频' : (kind === 'text' ? '文本' : '图片'));
}
function mentionThumbAlias(img, list){
    const label = mentionKindLabel(mediaKindForItem(img));
    const same = (list || []).filter(x => mentionKindLabel(mediaKindForItem(x)) === label);
    const pos = same.findIndex(x => x.url === img?.url);
    return pos >= 0 ? `${label}${pos + 1}` : '';
}
function inputMentionCandidateImages(node){
    const current = node ? lineImagesFor(node).filter(img => !isInputRefBlocked(node, img)) : [];
    const thumbs = mentionThumbnailCandidates(node);
    const thumbOrder = new Map(thumbs.map((img, index) => [img.url, index]));
    const seen = new Set();
    // 先列缩略图行顺序（编号基准），再补未进缩略图行的连线图
    const ordered = [
        ...thumbs,
        ...current.filter(img => img?.url && !thumbOrder.has(img.url))
    ];
    const kindCounters = {};
    return ordered.filter(img => {
        if(!img?.url || seen.has(img.url)) return false;
        seen.add(img.url);
        return true;
    }).map((img, index) => {
        const label = mentionKindLabel(mediaKindForItem(img));
        kindCounters[label] = (kindCounters[label] || 0) + 1;
        return {
            ...img,
            mentionId:`mention_${index}_${Math.random().toString(36).slice(2, 7)}`,
            alias:`${label}${kindCounters[label]}`
        };
    });
}
// 一个素材可注册到多个平台：收集所有「已通过」的 asset:// 地址，按平台映射。
function assetRegisteredUris(item){
    const regs = (item && item.registrations && typeof item.registrations === 'object') ? item.registrations : {};
    const out = {};
    Object.keys(regs).forEach(platform => {
        const reg = regs[platform];
        if(reg && reg.status === 'Active' && reg.asset_uri) out[platform] = reg.asset_uri;
    });
    return out;
}
function assetMentionCandidateImages(categoryId=''){
    const cats = assetCategories('image');
    const cat = cats.find(c => c.id === categoryId) || assetCategoryForMention();
    if(!cat) return [];
    mentionAssetCategoryId = cat.id;
    const items = (cat.items || []).map(item => ({...item, categoryName:cat.name || '', categoryId:cat.id}));
    const seen = new Set();
    return items.filter(item => {
        if(!item?.url || seen.has(item.url)) return false;
        seen.add(item.url);
        return true;
    }).map((item, index) => ({
        url:item.url,
        kind:assetMediaKind(item),
        name:item.name || `资产${index + 1}`,
        alias:item.name || `资产${index + 1}`,
        role:'asset',
        categoryName:item.categoryName || '',
        asset_uris:assetRegisteredUris(item),
        mentionId:`asset_${index}_${Math.random().toString(36).slice(2, 7)}`
    }));
}
function mentionCandidateImages(node, source=mentionSource){
    return source === 'asset' ? assetMentionCandidateImages(mentionAssetCategoryId) : inputMentionCandidateImages(node);
}
function referenceImagesFor(node){
    return defaultReferenceImagesFor(node);
}
function closeMentionPicker(){
    mentionPicker.classList.remove('open');
    mentionPicker.innerHTML = '';
}
function saveMentionRange(){
    const sel = window.getSelection();
    if(sel && sel.rangeCount && promptInput.contains(sel.anchorNode)){
        mentionRange = sel.getRangeAt(0).cloneRange();
    }
}
function textBeforeCaret(){
    const sel = window.getSelection();
    if(!sel || !sel.rangeCount || !promptInput.contains(sel.anchorNode)) return '';
    const range = sel.getRangeAt(0).cloneRange();
    range.selectNodeContents(promptInput);
    range.setEnd(sel.anchorNode, sel.anchorOffset);
    return range.toString();
}
function renderMentionPicker(source){
    const node = selectedNode();
    const inputItems = inputMentionCandidateImages(node);
    const assetLibs = assetLibraries();
    if(!activeAssetLibraryId || !assetLibs.some(lib => lib.id === activeAssetLibraryId)) activeAssetLibraryId = assetLibrary.active_library_id || assetLibs[0]?.id || '';
    const libraryWithMentionAssets = assetLibs.find(lib => (lib.categories || []).some(cat => (cat.type || 'image') === 'image' && (cat.items || []).some(item => item?.url)));
    const assetCats = assetCategories('image');
    const hasInput = inputItems.length > 0;
    const hasAssets = Boolean(libraryWithMentionAssets);
    mentionSource = source || (hasInput ? 'input' : 'asset');
    if(mentionSource === 'asset' && hasAssets && !assetCats.some(cat => (cat.items || []).some(item => item?.url)) && libraryWithMentionAssets){
        activeAssetLibraryId = libraryWithMentionAssets.id;
        activeAssetCategoryId = '';
        mentionAssetCategoryId = '';
    }
    if(mentionSource === 'input' && !hasInput && hasAssets) mentionSource = 'asset';
    if(mentionSource === 'asset' && !hasAssets && hasInput) mentionSource = 'input';
    if(!hasInput && !hasAssets){ closeMentionPicker(); return; }
    const nextAssetCats = assetCategories('image');
    const currentAssetCat = assetCategoryForMention();
    const assetItems = assetMentionCandidateImages(currentAssetCat?.id || '');
    const candidates = (mentionSource === 'asset' ? assetItems : inputItems).slice(0, 36);
    const body = candidates.length ? `<div class="mention-option-grid">${candidates.map((img, i) => `
            <button class="mention-option" type="button" data-mention-index="${i}" title="${escapeHtml(img.name || canvasAgentRefFileName(img) || '')}">
                ${mediaKindForItem(img) === 'video'
                    ? `<video src="${escapeHtml(img.url)}" muted preload="metadata" playsinline disablepictureinpicture controlslist="nodownload noplaybackrate noremoteplayback"></video>`
                    : (mediaKindForItem(img) === 'audio'
                        ? `<span class="media-audio-art" aria-hidden="true"><span></span><span></span><span></span><span></span><span></span></span>`
                        : `<img src="${escapeHtml(img.url)}" alt="">`)}
                <span>${escapeHtml(img.alias)}</span>
            </button>
        `).join('')}</div>` : `<div class="mention-empty">${escapeHtml(tr('smart.mentionEmpty'))}</div>`;
    const librarySelect = (mentionSource === 'asset' && assetLibs.length)
        ? `<label class="mention-library-row"><span>${escapeHtml(tr('smart.assetLibrary'))}</span><select class="mention-library-select" data-mention-library>${assetLibs.map(lib => `<option value="${escapeHtml(lib.id)}" ${lib.id === activeAssetLibraryId ? 'selected' : ''}>${escapeHtml(lib.name || '资产库')}</option>`).join('')}</select></label>`
        : '';
    const folderChips = (mentionSource === 'asset' && nextAssetCats.length)
        ? nextAssetCats.map(cat => {
            const label = cat.name || tr('smart.assetFolder');
            return `<button class="mention-folder-chip ${cat.id === mentionAssetCategoryId ? 'active' : ''}" type="button" data-mention-folder="${escapeHtml(cat.id)}" title="${escapeHtml(label)}">${escapeHtml(label)}</button>`;
          }).join('')
        : '';
    mentionPicker.innerHTML = `
        <div class="mention-picker-shell">
            <div class="mention-source-tabs">
                <button class="mention-source-tab ${mentionSource === 'input' ? 'active' : ''}" type="button" data-mention-source="input" title="${escapeHtml(tr('smart.mentionInput'))}" ${hasInput ? '' : 'disabled'}>
                    <i data-lucide="image"></i><span>${escapeHtml(tr('smart.mentionInput'))}</span>
                </button>
                <button class="mention-source-tab ${mentionSource === 'asset' ? 'active' : ''}" type="button" data-mention-source="asset" title="${escapeHtml(tr('smart.mentionAssets'))}" ${hasAssets ? '' : 'disabled'}>
                    <i data-lucide="library"></i><span>${escapeHtml(tr('smart.mentionAssets'))}</span>
                </button>
            </div>
            ${librarySelect}
            <div class="mention-folder-chips ${folderChips ? '' : 'hidden'}">
                ${folderChips}
            </div>
            <div class="mention-content">
                ${body}
            </div>
        </div>
    `;
    mentionPicker._items = candidates;
    positionMentionPickerAtCaret();
    mentionPicker.classList.add('open');
    mentionPicker.querySelectorAll('[data-mention-source]').forEach(btn => {
        btn.addEventListener('mousedown', e => {
            e.preventDefault(); e.stopPropagation();
            if(btn.disabled) return;
            renderMentionPicker(btn.dataset.mentionSource);
        });
    });
    mentionPicker.querySelectorAll('[data-mention-library]').forEach(select => {
        select.addEventListener('mousedown', e => e.stopPropagation());
        select.addEventListener('change', e => {
            activeAssetLibraryId = e.target.value || '';
            activeAssetCategoryId = '';
            mentionAssetCategoryId = '';
            renderAssetLibrary();
            renderMentionPicker('asset');
        });
    });
    mentionPicker.querySelectorAll('[data-mention-folder]').forEach(btn => {
        btn.addEventListener('mousedown', e => {
            e.preventDefault(); e.stopPropagation();
            mentionAssetCategoryId = btn.dataset.mentionFolder || '';
            renderMentionPicker('asset');
        });
    });
    mentionPicker.querySelectorAll('[data-mention-index]').forEach(btn => {
        btn.addEventListener('mousedown', e => {
            e.preventDefault(); e.stopPropagation();
            insertMentionToken(mentionPicker._items[Number(btn.dataset.mentionIndex)]);
        });
    });
    refreshIcons();
}
function showMentionPicker(){
    const node = selectedNode();
    const hasInput = inputMentionCandidateImages(node).length > 0;
    mentionSource = hasInput ? 'input' : 'asset';
    renderMentionPicker(mentionSource);
}
function positionMentionPickerAtCaret(){
    const row = promptInput.closest('.prompt-row');
    const rowRect = row.getBoundingClientRect();
    let caretRect = null;
    const sel = window.getSelection();
    if(sel && sel.rangeCount){
        const range = sel.getRangeAt(0).cloneRange();
        caretRect = range.getClientRects()[0] || range.getBoundingClientRect();
    }
    const inputRect = promptInput.getBoundingClientRect();
    // composer 本体反向抵消画布缩放后，内部坐标与屏幕像素保持 1:1。
    const rowLogicalWidth = rowRect.width;
    const pickerWidth = mentionPicker.offsetWidth || 340;
    const maxLeft = Math.max(4, rowLogicalWidth - pickerWidth - 4);
    const rawLeft = (caretRect?.left || inputRect.left) - rowRect.left - 6;
    const rawTop = (caretRect?.bottom || inputRect.top + 24) - rowRect.top + 2;
    const left = Math.max(4, Math.min(rawLeft, maxLeft));
    const top = Math.max(2, rawTop);
    mentionPicker.style.left = `${left}px`;
    mentionPicker.style.top = `${top}px`;
}
function maybeOpenMentionPicker(){
    saveMentionRange();
    const before = textBeforeCaret();
    if(/@$/.test(before)) showMentionPicker();
    else closeMentionPicker();
}
function insertMentionToken(img){
    if(!img?.url) return;
    promptInput.focus();
    const sel = window.getSelection();
    if(mentionRange){
        const saved = mentionRange;
        sel.removeAllRanges();
        sel.addRange(saved);
    }
    // @ 编号=缩略图行位置（第N张=图片N），不是点击顺序（用户 2026-09-11 定稿）
    const thumbList = mentionThumbnailCandidates(selectedNode());
    const posAlias = mentionThumbAlias(img, thumbList) || inputMentionCandidateImages(selectedNode()).find(c => c.url === img.url)?.alias;
    const count = [...promptInput.querySelectorAll('.mention-image-token')].length;
    img = {...img, alias:posAlias || `${mentionKindLabel(mediaKindForItem(img))}${count + 1}`};
    const range = sel.rangeCount ? sel.getRangeAt(0) : document.createRange();
    let removedAt = false;
    if(range.startContainer?.nodeType === Node.TEXT_NODE && range.startOffset > 0){
        const text = range.startContainer.textContent || '';
        if(text[range.startOffset - 1] === '@'){
            range.setStart(range.startContainer, range.startOffset - 1);
            range.deleteContents();
            removedAt = true;
        }
    }
    if(!removedAt) {
        const walker = document.createTreeWalker(promptInput, NodeFilter.SHOW_TEXT);
        let lastText = null;
        while(walker.nextNode()) lastText = walker.currentNode;
        if(lastText && /@$/.test(lastText.textContent || '')) {
            lastText.textContent = lastText.textContent.slice(0, -1);
            range.selectNodeContents(promptInput);
            range.collapse(false);
        }
    }
    const token = document.createElement('span');
    token.className = 'mention-image-token';
    token.contentEditable = 'false';
    token.dataset.url = img.url;
    token.dataset.name = img.alias || img.name || '图片';
    token.dataset.kind = mediaKindForItem(img);
    token.dataset.nodeId = img.nodeId || '';
    token.dataset.imageIndex = String(img.imageIndex ?? '');
    token.dataset.assetUris = JSON.stringify(img.asset_uris || {});
    token.innerHTML = token.dataset.kind === 'video'
        ? `<video src="${escapeHtml(img.url)}" muted preload="metadata" playsinline disablepictureinpicture controlslist="nodownload noplaybackrate noremoteplayback"></video><span>${escapeHtml(token.dataset.name)}</span>`
        : (token.dataset.kind === 'audio'
            ? `<span class="mention-audio-token-art" aria-hidden="true"><i data-lucide="music"></i></span><span>${escapeHtml(token.dataset.name)}</span>`
            : `<img src="${escapeHtml(img.url)}" alt=""><span>${escapeHtml(token.dataset.name)}</span>`);
    token.insertAdjacentHTML('beforeend', promptImageMentionRemoveButtonHtml());
    range.insertNode(token);
    const spacer = document.createTextNode(' ');
    token.after(spacer);
    range.setStartAfter(spacer);
    range.collapse(true);
    sel.removeAllRanges();
    sel.addRange(range);
    closeMentionPicker();
    promptInput.focus();
    renderInputThumbsRow(selectedNode());
}
function collectPromptParts(){
    const parts = [];
    const walk = node => {
        if(node.nodeType === Node.TEXT_NODE){
            if(node.textContent) parts.push({type:'text', text:node.textContent});
            return;
        }
        if(node.nodeType !== Node.ELEMENT_NODE) return;
        if(node.classList?.contains('mention-image-token')){
            let assetUris = {};
            try { assetUris = JSON.parse(node.dataset.assetUris || '{}') || {}; } catch(e) { assetUris = {}; }
            parts.push({type:'image', url:node.dataset.url || '', name:node.dataset.name || '图片', nodeId:node.dataset.nodeId || '', imageIndex:Number(node.dataset.imageIndex || 0), asset_uris:assetUris});
            return;
        }
        if(node.classList?.contains('mention-style-token')){
            parts.push({type:'style', text:node.dataset.styleText || '', name:node.dataset.styleName || '风格', styleId:node.dataset.styleId || ''});
            return;
        }
        if(node.tagName === 'BR') parts.push({type:'text', text:'\n'});
        node.childNodes.forEach(walk);
        if(node !== promptInput && ['DIV','P'].includes(node.tagName)) parts.push({type:'text', text:'\n'});
    };
    promptInput.childNodes.forEach(walk);
    return parts;
}
function originalPromptTextFromParts(parts){
    let text = '';
    (parts || []).forEach(part => {
        if(part.type === 'text'){
            text += part.text || '';
            return;
        }
        if(part.type === 'image') text += `@${part.name || '图片'}`;
        if(part.type === 'style') text += `@${part.name || '风格'}`;
    });
    return text.replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
}
function buildPromptRequest(node, overrideDefaultImages=null, consumeDefault=false, ctx=smartLoopContext){
    const parts = collectPromptParts();
    const originalPrompt = originalPromptTextFromParts(parts);
    const blockedRefs = blockedInputRefKeys(node);
    const hasOverrideImages = Array.isArray(overrideDefaultImages);
    const preferredRenderedRefs = !hasOverrideImages && selectedNode()?.id === node?.id ? renderedInputMediaRefs() : [];
    const defaultCandidates = hasOverrideImages
        ? overrideDefaultImages
        : (preferredRenderedRefs.length ? preferredRenderedRefs : defaultReferenceImagesFor(node, consumeDefault, ctx));
    const filteredDefaultImages = defaultCandidates
        .filter(img => !blockedRefs.has(inputRefKey(img)));
    const defaultRefs = uniqueReferenceImages(filteredDefaultImages);
    const refs = defaultRefs.map((img, index) => ({...img, kind:mediaKindForItem(img), role:`image_${index + 1}`}));
    let hasMentionToken = false;
    const refMap = new Map();
    refs.forEach((img, index) => refMap.set(img.url, index + 1));
    let body = '';
    parts.forEach(part => {
        if(part.type === 'text'){
            body += part.text;
            return;
        }
        if(!part.url) return;
        hasMentionToken = true;
        const mentionedKey = inputRefKey(part);
        if(blockedRefs.has(mentionedKey)){
            body += `@${part.name || '图片'}`;
            return;
        }
        if(!refMap.has(part.url)){
            refMap.set(part.url, refs.length + 1);
            refs.push({url:part.url, name:part.name || `图${refs.length + 1}`, nodeId:part.nodeId, imageIndex:part.imageIndex, role:`image_${refs.length + 1}`});
        }
        body += `图${refMap.get(part.url)}`;
    });
    body = body.replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
    const inputPrompt = inputPromptTextFor(node, ctx).trim();
    if(inputPrompt) body = [inputPrompt, body].filter(Boolean).join('\n\n');
    // 风格标签后缀：提示词框内已选风格标签的文本去重后追加到正文之后（风格段不进 displayPrompt）
    const styleText = promptStyleSuffix(parts);
    if(styleText) body = [body, styleText].filter(Boolean).join('\n\n');

    if(!body && settings.engine === 'runninghub'){
        body = rhDefaultPromptSuggestion();
    }
    const displayPrompt = originalPrompt || body;
    if(hasMentionToken && refs.length){
        const mapText = refs.map((img, i) => `图${i + 1}：${img.name || `图片${i + 1}`}`).join('\n');
        return {
            prompt:`${tr('smart.refMapHeader')}\n${mapText}\n\n${tr('smart.refUserNeed')}\n${body}`,
            displayPrompt,
            refs:refs.map((img, index) => ({url:img.url, name:img.name || `图${index + 1}`, kind:img.kind || mediaKindForItem(img), nodeId:img.nodeId || '', imageIndex:img.imageIndex ?? '', role:`image_${index + 1}`})),
            mentioned:true
        };
    }
    return {
        prompt:body,
        displayPrompt,
        refs:refs.map((img, index) => ({url:img.url, name:img.name || `图${index + 1}`, kind:img.kind || mediaKindForItem(img), nodeId:img.nodeId || '', imageIndex:img.imageIndex ?? '', role:`image_${index + 1}`})),
        mentioned:false
    };
}
function outgoingConnectionsFor(node, kinds=['input']){
    if(!node) return [];
    const allowed = new Set(kinds);
    return (canvas?.connections || []).filter(conn => conn.from === node.id && allowed.has(conn.kind || 'flow'));
}
function outgoingInputConnectionsFor(node){
    return outgoingConnectionsFor(node, ['input']);
}
function nextOutputPositionForSource(sourceNode, pendingBox, options={}){
    const sourceRect = nodeRect(sourceNode);
    const x = (sourceRect.x || 0) + sourceRect.width + 80;
    const gap = 28;
    const outputs = outgoingConnectionsFor(sourceNode, ['input','flow'])
        .map(conn => nodes.find(n => n.id === conn.to))
        .filter(n => isSmartImageNode(n))
        .map(n => nodeRect(n))
        .filter(rect => Math.abs((rect.x || 0) - x) < Math.max(320, (pendingBox?.w || 260) + 120))
        .sort((a, b) => (a.y || 0) - (b.y || 0));
    if(!outputs.length) return {x, y:sourceRect.y || 0};
    let y = sourceRect.y || 0;
    for(const rect of outputs){
        const bottom = (rect.y || 0) + (rect.height || 0) + gap;
        if(y < bottom) y = bottom;
    }
    return {x, y};
}
function createPendingOutputFromSource(sourceNode, expectedCount, meta, options={}){
    const pendingBox = pendingBoxSize(expectedCount, {sourceNode, refs:options.refs || meta?.promptRefs || []});
    const pos = nextOutputPositionForSource(sourceNode, pendingBox);
    const output = {
        id:uid('smart'),
        type:'smart-image',
        x:pos.x,
        y:pos.y,
        title:'Image',
        images:[],
        pending:Math.max(1, Number(expectedCount) || 1),
        runStartedAt:nowMs(),
        runTimerHidden:false,
        w:pendingBox.w,
        h:pendingBox.h,
        scale:MEDIA_NODE_DEFAULT_SCALE,
        created_at:Date.now()
    };
    if((settings.engine || '') === 'comfy'){
        output.comfyRecovery = {
            startedAt:output.runStartedAt,
            workflow:settings.comfyWorkflow || '',
            mode:settings.comfyMode || 'custom'
        };
    }
    output._selectAfterRunId = options.selectOutput ? output.id : sourceNode.id;
    nodeStore.addNode(output, 'generation');
    if(options.connectSource === false) addConnection(sourceNode.id, output.id, 'flow');
    else connectInputNode(sourceNode.id, output.id);
    attachRunMeta(output, options.stripInputMeta ? stripRunInputMeta(meta) : meta);
    canvasUiState.patchSelection({primaryId: sourceNode.id}, 'selectedId');
    canvasUiState.patchSelection({image: {nodeId:'', index:-1}}, 'selectedImage');
    return output;
}
function createParallelLoopOutputNode(templateNode, sourceNode, roundIndex, roundOffset=0){
    const rect = nodeRect(templateNode);
    const output = cloneSmartNode(templateNode, 0, 0);
    output.id = uid('smart');
    output.type = 'smart-image';
    output.x = (Number(templateNode.x) || 0) + (Number(rect.width) || 260) + 80;
    output.y = (Number(templateNode.y) || 0) + roundOffset * ((Number(rect.height) || 180) + 28);
    output.title = `Image ${roundIndex}`;
    output.images = [];
    output.pending = 0;
    output.running = false;
    output.created_at = Date.now();
    delete output.w;
    delete output.h;
    delete output.historyFor;
    delete output.isHistoryGroup;
    delete output.sourceNodeId;
    delete output.runAt;
    delete output.runPrompt;
    delete output.runModelPrompt;
    delete output.runPromptRefs;
    delete output.runInputRefs;
    nodeStore.addNode(output, 'generation');
    connectInputNode(sourceNode.id, output.id);
    return output;
}
function loopOutputSlotsForRoot(rootNode){
    if(!rootNode?.id) return [];
    return downstreamNodesForId(rootNode.id)
        .filter(n => isSmartImageNode(n) && !isHistoryGroupNode(n))
        .sort((a, b) => {
            const ax = Number(a.x) || 0, bx = Number(b.x) || 0;
            if(ax !== bx) return ax - bx;
            return (Number(a.y) || 0) - (Number(b.y) || 0);
        });
}
function loopOutputSlotForRound(rootNode, loopNode, roundIndex, slotIndex){
    if(!rootNode?.id) return null;
    const candidates = loopOutputSlotsForRoot(rootNode)
        .filter(node => node.sourceNodeId === rootNode.id)
        .filter(node => !loopNode?.id || !node.loopSourceId || node.loopSourceId === loopNode.id);
    const untagged = candidates.filter(node => !Number.isFinite(Number(node.loopRoundIndex)) && !Number.isFinite(Number(node.loopSlotIndex)));
    return candidates.find(node => Number(node.loopRoundIndex) === Number(roundIndex))
        || candidates.find(node => Number(node.loopSlotIndex) === Number(slotIndex))
        || untagged[Math.max(0, Number(slotIndex) || 0)]
        || null;
}
function tagLoopOutputSlot(output, rootNode, loopNode, roundIndex, slotIndex){
    if(!output) return output;
    output.sourceNodeId = rootNode?.id || output.sourceNodeId || '';
    output.loopSourceId = loopNode?.id || output.loopSourceId || '';
    output.loopRootId = rootNode?.id || output.loopRootId || '';
    output.loopRoundIndex = Number(roundIndex) || 0;
    output.loopSlotIndex = Math.max(0, Number(slotIndex) || 0);
    return output;
}
function createLoopOutputSlot(rootNode, roundIndex, roundOffset=0, options={}){
    const rootRect = nodeRect(rootNode);
    const output = cloneSmartNode(rootNode, 0, 0);
    output.id = uid('smart');
    output.type = 'smart-image';
    output.x = (Number(rootNode.x) || 0) + (Number(rootRect.width) || 260) + 80;
    output.title = `Image ${roundIndex}`;
    output.images = [];
    output.pending = options.pending ? Math.max(1, Number(options.pending) || 1) : 0;
    output.running = Boolean(options.pending);
    output.queued = Boolean(options.queued);
    if(options.pending){
        output.runStartedAt = nowMs();
        output.runTimerHidden = false;
    }
    output.created_at = Date.now();
    delete output.w;
    delete output.h;
    delete output.historyFor;
    delete output.isHistoryGroup;
    delete output.sourceNodeId;
    delete output.runAt;
    delete output.runPrompt;
    delete output.runModelPrompt;
    delete output.runPromptRefs;
    delete output.runInputRefs;
    delete output.runFinishedAt;
    delete output.runElapsedMs;
    tagLoopOutputSlot(output, rootNode, options.loopNode || null, roundIndex, options.slotIndex ?? roundOffset);
    const slots = loopOutputSlotsForRoot(rootNode).map(nodeRect);
    let y = (Number(rootNode.y) || 0) + roundOffset * ((Number(rootRect.height) || 180) + 28);
    slots.forEach(rect => {
        if((Number(rect.x) || 0) >= (Number(output.x) || 0) - 24){
            y = Math.max(y, (Number(rect.y) || 0) + (Number(rect.height) || 0) + 28);
        }
    });
    output.y = y;
    nodeStore.addNode(output, 'generation');
    addConnection(rootNode.id, output.id, 'flow');
        const runPath = smartCascadePathForCtx(options.ctx || options.runState);
        if(runPath?.states) runPath.states[`${rootNode.id}->${output.id}`] = 'wait';
    return output;
}
function extractCurrentImagesToSource(node, meta=null){
    const imgs = (node.images || []).slice();
    if(!imgs.length) return null;
    const r = nodeRect(node);
    const newX = (node.x || 0) - Math.max(280, r.width + 60);
    const source = {
        id: uid('smart'),
        type: 'smart-image',
        x: newX,
        y: node.y || 0,
        title: imgs.length > 1 ? 'Group' : 'Image',
        // 抽出到上游源节点的图片只保留"原始素材"语义：清空 runPrompt / runSettings /
        // sourceNodeId / runAt / promptDraftHtml / promptDraftText 等"生成"相关字段，
        // 避免上游图片继承下游输出的提示词信息
        images: imgs.map(img => stripImageGenerationMeta({...img})),
        created_at: Date.now()
    };
    if(Number.isFinite(Number(node.w))) source.w = node.w;
    if(Number.isFinite(Number(node.h))) source.h = node.h;
    if(Number.isFinite(Number(node.scale))) source.scale = node.scale;
    nodeStore.addNode(source, 'user_manual');
    connectInputNode(source.id, node.id);
    node.images = [];
    delete node.w;
    delete node.h;
    return source;
}
async function finalizePendingNode(pendingNode, urls, meta, kind='image'){
    if(!pendingNode) return;
    const attempt = meta?.generationAttemptId || pendingNode.generationAttemptId;
    if(attempt && !CanvasGenerationLifecycle.isCurrent(pendingNode, attempt)) return false;
    preserveNodeCardForRun(pendingNode);
    urls = CanvasGenerationResultModel.uniqueMediaItems(urls);
    const ext = kind === 'video' ? 'mp4' : kind === 'audio' ? 'mp3' : kind === 'text' ? 'txt' : 'png';
    const date = new Date();
    const outputTitle = pendingNode.title || meta?.displayPrompt || meta?.promptText || '';
    let imgs = kind === 'image'
        ? await smartGeneratedOutputItems(urls, kind, {displayName:outputTitle, nodeId:pendingNode.id})
        : urls.map((item, i) => {
            const url = typeof item === 'string' ? item : item?.url || '';
            const itemKind = (typeof item === 'object' && item.kind) || kind;
            const name = (typeof item === 'object' && item.name) || `output-${i + 1}.${ext}`;
            return {url, name, kind:itemKind, generatedResult:true};
        }).filter(img => img.url);
    if(attempt && !CanvasGenerationLifecycle.isCurrent(pendingNode, attempt)) return false;
    // 2026-10-19（老王：一个节点只装一张图）：节点只留最新一张，其余各自独立节点。
    if(kind === 'image' && imgs.length > 1){
        const extras = imgs.slice(0, -1);
        imgs = [imgs[imgs.length - 1]];
        spawnImageNodesForExtras(pendingNode, extras, {});
    }
    pendingNode.images = imgs;
    pendingNode.pending = 0;
    pendingNode.runFinishedAt = nowMs();
    if(!pendingNode.runStartedAt) pendingNode.runStartedAt = meta?.createdAt || pendingNode.runFinishedAt;
    pendingNode.runElapsedMs = Math.max(0, pendingNode.runFinishedAt - Number(pendingNode.runStartedAt || pendingNode.runFinishedAt));
    pendingNode.runTimerHidden = false;
    pendingNode.outputKind = kind;
    if(imgs.length > 1) pendingNode.title = kind === 'video' ? 'Videos' : kind === 'audio' ? 'Audios' : kind === 'text' ? 'Texts' : 'Group';
    else pendingNode.title = kind === 'video' ? 'Video' : kind === 'audio' ? 'Audio' : kind === 'text' ? 'Text' : kind === 'file' ? 'File' : 'Image';
    // 自动命名（2026-10-09）：提示词前缀 + 产物序号；titleManual（用户手动改名）不覆盖
    pendingNode.title = CanvasGeneratedOutputNaming.autoNodeTitleFromNode(pendingNode, pendingNode.title);
    const metaTarget = pendingNode._runMetaTargetId ? nodes.find(n => n.id === pendingNode._runMetaTargetId) : pendingNode;
    if(metaTarget) attachRunMeta(metaTarget, meta);
    pendingNode.images = (pendingNode.images || []).map(img => stripImageGenerationMeta(img));
    // 2026-10-09 老王拍板：去掉覆盖重跑保留名机制 —— 画布内素材名必须与磁盘文件名一致，
    // 重跑产物按新落盘名（MM-DD-NN）命名，历史版本进 history/ 分组。不再沿用第一次生图名。
    delete pendingNode.retainOutputNames;
    delete pendingNode._retainOutputNames;
    // Completing A must not take the editor away from B. Explicit extraction
    // destinations still apply while A itself remains selected.
    const ownsSelection = canvasUiState.selection.primaryId === pendingNode.id;
    if(ownsSelection) canvasUiState.patchSelection({primaryId: pendingNode._selectAfterRunId || pendingNode.id}, 'generation-result');
    delete pendingNode._runMetaTargetId;
    delete pendingNode._selectAfterRunId;
    if(canvasUiState.editor.subject?.id && canvasUiState.selection.primaryId === canvasUiState.editor.subject.id) canvasUiState.patchEditor({key: `${canvasUiState.selection.primaryId}:node`}, 'lastComposerNodeId');
    if(ownsSelection) canvasUiState.patchSelection({image: {nodeId:'', index:-1}}, 'generation-result');
}
function restoreFromExtraction(node, extracted){
    if(!node || !extracted) return;
    node.images = extracted.images.slice();
    if(Number.isFinite(Number(extracted.w))) node.w = extracted.w;
    if(Number.isFinite(Number(extracted.h))) node.h = extracted.h;
    nodeStore.removeNode(extracted.id);
    canvas.connections = (canvas.connections || []).filter(c => !(c.from === extracted.id && c.to === node.id));
    if(Array.isArray(node.inputNodeIds)){
        node.inputNodeIds = node.inputNodeIds.filter(id => id !== extracted.id);
    }
}
function restoreSourceVisualState(node, state){
    if(!node || !state) return;
    node.images = (state.images || []).map(img => ({...img}));
    node.title = state.title || (node.images.length > 1 ? 'Group' : 'Image');
    ['w','h','scale','outputKind'].forEach(key => {
        if(state[key] === undefined) delete node[key];
        else node[key] = state[key];
    });
}
function finishLoopTargetPreviewState(node){
    if(!node) return;
    preserveNodeCardForRun(node);
    node.pending = 0;
    node.running = false;
    node.queued = false;
    delete node.pendingTasks;
    node.runFinishedAt = nowMs();
    if(!node.runStartedAt) node.runStartedAt = node.runFinishedAt;
    node.runElapsedMs = Math.max(0, node.runFinishedAt - Number(node.runStartedAt || node.runFinishedAt));
    node.runTimerHidden = false;
    if((node.images || []).some(img => img?.url)){
        node.title = node.images.length > 1 ? 'Group' : 'Image';
        node.outputKind = mediaKindForUrls(node.images || [], (node.images || []).some(isVideoMediaItem) ? 'video' : 'image');
    }
}
function refsForDirectLoopRound(loopNode, loopIndex, total){
    if(!loopNode?.imageInput) return [];
    return outputImagesForNode(loopNode, true, {index:loopIndex, total, nodeId:loopNode.id})
        .filter(ref => ref?.url)
        .map((ref, index) => ({
            ...ref,
            role:ref.role || `image_${index + 1}`,
            name:ref.name || trf('canvas.loopImageLabel', {n:loopIndex + index})
        }));
}
function showDirectLoopRoundPreview(loopNode, target, refs, loopIndex, total){
    if(!loopNode?.imageInput || !isSmartImageNode(target)) return false;
    preserveNodeCardForRun(target);
    const cleanRefs = (refs || []).filter(ref => ref?.url);
    if(!cleanRefs.length) return false;
    const preview = cleanRefs.map((ref, index) => stripImageGenerationMeta({
        url:ref.url || '',
        name:ref.name || trf('canvas.loopImageLabel', {n:loopIndex + index}),
        kind:ref.kind || (isVideoMediaItem(ref) ? 'video' : 'image'),
        nodeId:ref.nodeId || '',
        imageIndex:ref.imageIndex ?? '',
        loopInputPreview:true
    })).filter(ref => ref.url);
    if(!preview.length) return false;
    target.images = preview;
    target.pending = 0;
    target.running = true;
    target.runStartedAt = nowMs();
    delete target.runFinishedAt;
    delete target.runElapsedMs;
    target.runTimerHidden = false;
    target.runInputRefs = cleanRefs.map(ref => ({
        url:ref.url || '',
        name:ref.name || '',
        nodeId:ref.nodeId || '',
        imageIndex:ref.imageIndex ?? '',
        kind:ref.kind || ''
    })).filter(ref => ref.url);
    target.outputKind = mediaKindForUrls(preview, preview.some(isVideoMediaItem) ? 'video' : 'image');
    target.title = total > 1 ? `Image ${loopIndex}/${total}` : (target.title || 'Image');
    render();
    return true;
}
function directImageInputsFor(node){
    const upstream = smartImageUsesWorkflowInput(node) ? workflowInputNodesFor(node) : inputNodesFor(node);
    return upstream
        .filter(n => isSmartImageNode(n) && !isHistoryGroupNode(n) && (n.images || []).some(img => img?.url))
        .sort((a, b) => {
            const ax = Number(a.x) || 0, bx = Number(b.x) || 0;
            if(ax !== bx) return bx - ax;
            return (Number(a.y) || 0) - (Number(b.y) || 0);
        });
}
function directImageInputsForKinds(node, kinds=['input']){
    const upstream = upstreamNodesForKinds(node, kinds);
    return upstream
        .filter(n => isSmartImageNode(n) && !isHistoryGroupNode(n) && (n.images || []).some(img => img?.url))
        .sort((a, b) => {
            const ax = Number(a.x) || 0, bx = Number(b.x) || 0;
            if(ax !== bx) return bx - ax;
            return (Number(a.y) || 0) - (Number(b.y) || 0);
        });
}
function primaryImageInputFor(node, options={}){
    const direct = options.includeFlow
        ? directImageInputsForKinds(node, ['input', 'flow'])[0]
        : directImageInputsFor(node)[0];
    if(direct) return direct;
    const inputs = options.includeFlow ? upstreamNodesForKinds(node, ['input', 'flow']) : (smartImageUsesWorkflowInput(node) ? workflowInputNodesFor(node) : inputNodesFor(node));
    const loop = inputs.find(n => n?.type === 'smart-loop');
    if(loop?.imageInput){
        const upstream = upstreamNodesForKinds(loop, options.includeFlow ? ['input', 'flow'] : ['input']).find(n => isSmartImageNode(n) && (n.images || []).some(img => img?.url));
        if(upstream) return upstream;
    }
    return null;
}
function hasDownstreamImageNode(node){
    return downstreamNodesForId(node?.id).some(n => isSmartImageNode(n) && !isHistoryGroupNode(n));
}
function isGeneratedOutputForNode(sourceNode, targetNode){
    return Boolean(sourceNode?.id && targetNode?.sourceNodeId === sourceNode.id);
}
function downstreamWorkflowImageTargetsFor(node){
    return downstreamImageTargetsFor(node).filter(target => !isGeneratedOutputForNode(node, target));
}
function hasDownstreamWorkflowImageNode(node){
    return downstreamWorkflowImageTargetsFor(node).length > 0;
}
function smartImageChainTo(nodeId, options={}){
    const tail = nodes.find(n => n.id === nodeId);
    if(!isSmartImageNode(tail) || isHistoryGroupNode(tail)) return [];
    const chain = [];
    const seen = new Set();
    let cur = tail;
    while(cur && !seen.has(cur.id)){
        seen.add(cur.id);
        chain.unshift(cur);
        cur = primaryImageInputFor(cur, options);
    }
    return chain;
}
function upstreamNodesForId(nodeId, kinds=['input']){
    const result = [];
    const seen = new Set([nodeId]);
    const walk = id => {
        upstreamNodesForKinds(nodes.find(n => n.id === id), kinds).forEach(input => {
            if(seen.has(input.id)) return;
            seen.add(input.id);
            walk(input.id);
            result.push(input);
        });
    };
    walk(nodeId);
    return result;
}
function resolveSmartCascadeLoop(nodeId){
    const loops = upstreamNodesForId(nodeId, ['input', 'flow']).filter(n => n.type === 'smart-loop');
    if(!loops.length) return null;
    const loop = loops[loops.length - 1];
    return {node:loop, count:smartLoopCount(loop), mode:loop.mode === 'parallel' ? 'parallel' : 'serial'};
}
function relayLoopPromptNodesForEdge(sourceNode, targetNode){
    if(!sourceNode?.id || !targetNode?.id) return [];
    const directLoopIds = new Set(promptInputNodesFor(targetNode).filter(n => n?.type === 'smart-loop' && n.showPrompt).map(n => n.id));
    return inputNodesFor(sourceNode)
        .filter(n => n?.type === 'smart-loop' && n.showPrompt && !directLoopIds.has(n.id));
}
function relayLoopPromptNodesForTarget(node){
    if(!node?.id) return [];
    return inputNodesFor(node).filter(n => n?.type === 'smart-loop' && n.showPrompt);
}
function downstreamNodesForId(nodeId){
    const result = [];
    const seen = new Set([nodeId]);
    const walk = id => {
        (canvas?.connections || [])
            .filter(conn => conn.from === id && ['input','flow'].includes(conn.kind || 'flow'))
            .map(conn => nodes.find(n => n.id === conn.to))
            .filter(Boolean)
            .forEach(next => {
                if(seen.has(next.id)) return;
                seen.add(next.id);
                result.push(next);
                walk(next.id);
            });
    };
    walk(nodeId);
    return result;
}
function downstreamImageTargetsFor(node){
    if(!node?.id) return [];
    return (canvas?.connections || [])
        .filter(conn => conn.from === node.id && ['input','flow'].includes(conn.kind || 'flow'))
        .map(conn => nodes.find(n => n.id === conn.to))
        .filter(n => isSmartImageNode(n) && !isHistoryGroupNode(n))
        .sort((a, b) => {
            const ax = Number(a.x) || 0, bx = Number(b.x) || 0;
            if(ax !== bx) return ax - bx;
            return (Number(a.y) || 0) - (Number(b.y) || 0);
        });
}
function downstreamCascadeTargetsFor(node){
    if(!node?.id) return [];
    return (canvas?.connections || [])
        .filter(conn => conn.from === node.id && ['input','flow'].includes(conn.kind || 'flow'))
        .map(conn => nodes.find(n => n.id === conn.to))
        .filter(n => n && !isHistoryGroupNode(n) && (isSmartImageNode(n) || n.type === 'smart-loop'))
        .sort((a, b) => {
            const ax = Number(a.x) || 0, bx = Number(b.x) || 0;
            if(ax !== bx) return ax - bx;
            return (Number(a.y) || 0) - (Number(b.y) || 0);
        });
}
function directLoopRunTargets(loop){
    if(!loop?.id) return [];
    return downstreamImageTargetsFor(loop)
        .filter(node => !hasDownstreamWorkflowImageNode(node));
}
function smartCascadeGraphForTail(tail){
    const path = smartImageChainTo(tail?.id, {includeFlow:true}).filter(n => isSmartImageNode(n) && !isHistoryGroupNode(n));
    if(!path.length) return {root:null, path:[], edges:[], children:new Map()};
    const loop = resolveSmartCascadeLoop(tail?.id);
    const loopRoots = loop?.node?.id ? downstreamImageTargetsFor(loop.node) : [];
    const loopRoot = loopRoots.find(n => path.some(p => p.id === n.id));
    const root = loopRoot || path[0];
    const edges = [];
    const children = new Map();
    const seenEdges = new Set();
    const visiting = new Set();
    const walk = node => {
        if(!node?.id || visiting.has(node.id)) return;
        visiting.add(node.id);
        const targets = downstreamCascadeTargetsFor(node);
        children.set(node.id, targets);
        targets.forEach(target => {
            const key = `${node.id}->${target.id}`;
            if(!seenEdges.has(key)){
                seenEdges.add(key);
                edges.push({source:node, target, key});
            }
            walk(target);
        });
        visiting.delete(node.id);
    };
    walk(root);
    return {root, path, edges, children};
}
function cascadeTailForLoop(loopId){
    const loop = nodes.find(n => n.id === loopId && n.type === 'smart-loop');
    const directTargets = directLoopRunTargets(loop);
    if(directTargets.length) return directTargets[directTargets.length - 1];
    const directImages = downstreamImageTargetsFor({id:loopId});
    const directIds = new Set(directImages.map(n => n.id));
    const candidates = downstreamNodesForId(loopId)
        .filter(n => isSmartImageNode(n))
        .filter(n => !isHistoryGroupNode(n))
        .filter(n => canRunSmartCascade(n));
    if(!candidates.length) return null;
    return candidates.sort((a, b) => {
        const ad = directIds.has(a.id) ? 1 : 0;
        const bd = directIds.has(b.id) ? 1 : 0;
        if(ad !== bd) return ad - bd;
        const ax = Number(a.x) || 0, bx = Number(b.x) || 0;
        if(ax !== bx) return bx - ax;
        return (Number(b.y) || 0) - (Number(a.y) || 0);
    })[0];
}
function canRunSmartCascade(node){
    if(!isSmartImageNode(node) || isHistoryGroupNode(node)) return false;
    const graph = smartCascadeGraphForTail(node);
    const loop = resolveSmartCascadeLoop(node.id);
    if(loop && isDirectLoopTargetRun(loop, node, graph)) return true;
    if(hasDownstreamImageNode(node)) return false;
    if(graph.edges.length) return true;
    return Boolean(loop);
}
function isDirectLoopTargetRun(loop, tail, graph){
    if(!loop?.node?.id || !tail?.id) return false;
    if(graph?.root?.id !== tail.id) return false;
    if(hasDownstreamWorkflowImageNode(tail)) return false;
    return downstreamImageTargetsFor(loop.node).some(node => node.id === tail.id);
}
function cascadeConnectionKeys(){
    const keys = new Set();
    const addKey = (from, to) => {
        if(from && to) keys.add(`${from}->${to}`);
    };
    const activeLoopIds = new Set(smartCascadeRuns.keys());
    const loops = activeLoopIds.size
        ? nodes.filter(n => n?.type === 'smart-loop' && activeLoopIds.has(n.id))
        : nodes.filter(n => n?.type === 'smart-loop');
    loops.forEach(loop => {
        const tail = cascadeTailForLoop(loop.id);
        if(!tail) return;
        const graph = smartCascadeGraphForTail(tail);
        if(!graph.root) return;
        const chainIds = new Set(graph.path.map(n => n.id));
        graph.edges.forEach(edge => addKey(edge.source.id, edge.target.id));
        (canvas?.connections || []).forEach(conn => {
            if((conn.kind || 'flow') === 'history') return;
            const toNode = nodes.find(n => n.id === conn.to);
            if(conn.from === loop.id && (chainIds.has(conn.to) || downstreamNodesForId(conn.to).some(n => chainIds.has(n.id)))) addKey(conn.from, conn.to);
            if(toNode && chainIds.has(toNode.id)){
                inputNodesFor(toNode).filter(n => n?.type === 'smart-loop' && n.showPrompt).forEach(inputLoop => addKey(inputLoop.id, toNode.id));
            }
        });
    });
    return keys;
}
function coolRunButton(ms=2000){
    if(!runBtn) return 0;
    const token = ++runBtnCooldownToken;
    runBtn.disabled = true;
    setTimeout(() => {
        if(token === runBtnCooldownToken) syncRunButtonAvailability();
    }, ms);
    return token;
}
function syncRunButtonAvailability(node=selectedNode()){
    if(!runBtn) return;
    // 共享按钮只跟随"当前选中节点"。ComfyUI 运行中的节点每 900ms 轮询一次并调用本函数，
    // 若不判断选中态，会把用户刚选中的其他节点（如 API 生图节点）的按钮持续刷成红色停止态，
    // 导致 ComfyUI 跑任务期间其他节点无法点运行。
    if(node && node !== selectedNode()) return;
    // 2026-09-17：queued 也算 ComfyUI 运行态。
    // 后端 job 建好时 status 是 'queued'（comfy_flow_service.py:280），要等 ComfyUI 真正开工才转
    // 'running'（同文件 460/467/499）。而 submitComfyWorkflowJob 的 900ms 轮询第一轮就会把
    // comfyStatus 覆写成后端即时值（20112 行）—— 只认 running 的话，点下运行后按钮要么压根不亮、
    // 要么只亮一瞬就灭，看起来就是"动效不到 1 秒就变回来，但后台还在跑"。
    const isComfyRunning = Boolean(node && node.comfyJobId && ['running', 'queued'].includes(node.comfyStatus));
    // 2026-10-05 老王定调：运行按钮分两种动效，按「工作流类 / 非工作流类」分，不按布局 class 分。
    //   工作流类（comfy 本地 + runninghub 云端）→ 红态 is-running/is-stop，节点侧配进度环 + 流光。
    //   其余（api / volcengine / blender 3D预演）→ 蓝色波纹 is-ap-running。
    // 判定改用 isWorkflowEngine(settings.engine)（见 isWorkflowEngine 定义处），
    // 不再用 apScope=closest('.api-single-row,.api-video-row') 判 API 身份 ——
    // 那两个 class 与 RH 的 .rh-single-row 互斥，RH 永远命中不了，导致 RH 按钮毫无动效。
    const engineIsWorkflow = isWorkflowEngine(settings.engine);
    // 工作流类运行中：ComfyUI 认 comfyJobId（queued 也算，见上）；
    // RH 没有 comfyJobId，认 runner 置的 comfyStatus='running' + comfyIndeterminate（canvas-generation-runner.js:148-153）。
    const isWorkflowRunning = Boolean(node
        && (node.comfyJobId ? ['running', 'queued'].includes(node.comfyStatus)
            : (node.comfyStatus === 'running' && !node.comfyJobId)));
    // 2026-09-16 运行按钮分类动效：非工作流类（api/volcengine/blender）运行时单独挂 is-ap-running，
    // 与工作流类运行的 is-running/is-stop 区分，使两类运行态颜色/动效不同。
    // 2026-09-17：API 类运行态改用 node.apiRunning（与 node.running 解耦）。
    // 之前 isApRunning 依赖 node.running，而 API 并发任务里 node.running 被刻意保持 false
    // （避免锁住共享运行按钮），结果点运行后 is-ap-running 永远不触发、毫无动效。
    // node.apiRunning 由运行流程显式置位/清除，只管「动效」，不参与「禁用」判定。
    const isApRunning = Boolean(node && (node.running || node.apiRunning)
        && !isWorkflowRunning && !engineIsWorkflow);
    // 选中节点正在 ComfyUI 本地运行时，按钮变"停止"，可点击；否则按原逻辑
    // 2026-09-23：smartCascadeAnyRunning() 是「级联批量运行」的标志位，它一旦卡在 true，
    // 会把普通单节点的运行按钮一起禁用 —— 表现就是「跑了一个之后别的节点全点不动」。
    // 任务现已改走后端 FIFO 队列，多节点提交只会排队、不会互相冲突，
    // 所以这里只保留「当前节点自己在跑」的禁用判定。
    // ⚠️ 只有本地 ComfyUI 可停：cancelComfyJob 依赖 comfyJobId 打后端 cancel/interrupt，
    // RH 没有 jobId，走那条路只会误清状态（canvas-comfy-job-engine.js:217-251）。
    // 所以工作流类里再分「可停（ComfyUI）」与「仅显示（RH）」，后者 disabled。
    const canStop = isComfyRunning;
    // 工作流类里「不可停」的那一支（云端 RH）单独一个 class，走红底+进度条+流光（见 CSS is-wf-cloud）
    const isWfCloud = isWorkflowRunning && !canStop;
    runBtn.disabled = canStop ? false : Boolean(node?.running) || (engineIsWorkflow && isWorkflowRunning);
    runBtn.classList.toggle('is-running', isWorkflowRunning);
    runBtn.classList.toggle('is-stop', canStop);
    runBtn.classList.toggle('is-wf-cloud', isWfCloud);
    runBtn.classList.toggle('is-ap-running', isApRunning);
    // 数据态给 CSS/调试用：wf-running（工作流类，含不可停的 RH）/ ap-running / idle
    runBtn.setAttribute('data-comfy-state', isWorkflowRunning ? 'running' : (isApRunning ? 'ap-running' : 'idle'));
    // 只有可停的工作流任务才显示「停止」文案；RH 显示「生成中」但按钮 disabled
    const label = runBtn.querySelector('[data-i18n], span');
    if(label){
        const runningText = canStop ? tr('smart.stop') : (isWorkflowRunning || isApRunning ? '生成中' : tr('smart.run'));
        label.dataset.i18n = canStop ? 'smart.stop' : ((isWorkflowRunning || isApRunning) ? 'common.running' : 'smart.run');
        label.textContent = runningText;
        runBtn.setAttribute('aria-label', runningText);
    }
    // 2026-09-16：图标（arrow-up / square / loader）一律由 CSS 按 [data-lucide] 切显隐，此处不再改
    // data-lucide。原因：renderDynamicParams() 里写死了「把 #runBtn 的第一个图标设回 arrow-up」，
    // 两边同时改图标会互相覆盖 —— 真机实测方块永远出现不了，lucide 重建后 class 还被叠成
    // "lucide lucide-arrow-up lucide-square"。CSS 方案对那处写死逻辑免疫（第一个图标本来就是 arrow-up）。
}
// 停止当前 ComfyUI 任务：先尝试后端 cancel 路由；不存在就只清前端状态
async function cancelComfyJob(node){
    return CanvasComfyJobEngine.cancelComfyJob(node);
}
// 类似 clearComfyProgress 但保留 comfyStatus 字段（cancelled 用于 UI 显示）
function clearComfyProgressExceptStatus(node){
    CanvasComfyJobEngine.clearComfyProgressExceptStatus(node);
}
function coolNodeRunningState(node, ms=2000){
    if(!node) return 0;
    const token = ++smartRunStateToken;
    smartNodeRunTokens.set(node.id, token);
    node.running = true;
    setTimeout(() => {
        if(smartNodeRunTokens.get(node.id) !== token) return;
        smartNodeRunTokens.delete(node.id);
        const current = nodes.find(n => n.id === node.id);
        if(current){
            current.running = false;
            render();
        }
    }, ms);
    return token;
}
function clearNodeRunningState(node){
    if(!node) return;
    smartNodeRunTokens.delete(node.id);
    node.running = false;
}
function pushRightSideNodes(sourceNode, delta){
    const shift = Math.ceil(Number(delta) || 0);
    if(!sourceNode || shift <= 0) return;
    const sourceRight = (Number(sourceNode.x) || 0) + nodeRect(sourceNode).width - shift;
    const downstreamIds = new Set(downstreamNodesForId(sourceNode.id).map(n => n.id));
    nodes.forEach(n => {
        if(!n || n.id === sourceNode.id) return;
        const r = nodeRect(n);
        const shouldShift = downstreamIds.has(n.id) || (Number(r.x) > sourceRight && Math.abs((Number(r.y) || 0) - (Number(sourceNode.y) || 0)) < 520);
        if(shouldShift) n.x = (Number(n.x) || 0) + shift;
    });
}
function cascadeOutputTitle(kind='image', count=1){
    if(Number(count) > 1) return kind === 'video' ? 'Videos' : kind === 'audio' ? 'Audios' : kind === 'text' ? 'Texts' : 'Group';
    return kind === 'video' ? 'Video' : kind === 'audio' ? 'Audio' : kind === 'text' ? 'Text' : kind === 'file' ? 'File' : 'Image';
}
// 归档组域外移 canvas-history-archive-group.js（第七刀）。historyGroupNodeIds 读写分双通道。
if(globalThis.CanvasHistoryArchiveGroup){CanvasHistoryArchiveGroup.configure({
        addConnection: (...a) => addConnection(...a),
        generatedOutputKindForName: (...a) => generatedOutputKindForName(...a),
        isHistoryGroupNode: (...a) => isHistoryGroupNode(...a),
        nodeRect: (...a) => nodeRect(...a),
        stripImageGenerationMeta: (...a) => stripImageGenerationMeta(...a),
        uid: (...a) => uid(...a),
        MEDIA_GROUP_DEFAULT_SCALE: () => MEDIA_GROUP_DEFAULT_SCALE,
        assets: () => assets,
        canvas: () => canvas,
        nodeStore: () => nodeStore,
        nodes: () => nodes,
        promptInput: () => promptInput
});}
function cleanHistoryImages(){return CanvasHistoryArchiveGroup.cleanHistoryImages.apply(null, arguments);}
function moveOutputImagesToHistoryForRun(){return CanvasHistoryArchiveGroup.moveOutputImagesToHistoryForRun.apply(null, arguments);}
function remapRefsForMovedAssets(){return CanvasHistoryArchiveGroup.remapRefsForMovedAssets.apply(null, arguments);}
function updatePromptMentionUrlsForMovedAssets(){return CanvasHistoryArchiveGroup.updatePromptMentionUrlsForMovedAssets.apply(null, arguments);}
function demoteHistoryGroupNode(){return CanvasHistoryArchiveGroup.demoteHistoryGroupNode.apply(null, arguments);}
function historyGroupForNode(){return CanvasHistoryArchiveGroup.historyGroupForNode.apply(null, arguments);}
function ensureHistoryGroupForNode(){return CanvasHistoryArchiveGroup.ensureHistoryGroupForNode.apply(null, arguments);}
async function replaceOutputsToNodeWithHistory(node, additions, kind='image', meta=null, options={}){
    if(!node || !additions?.length) return [];
    const attempt = node.generationAttemptId;
    if(meta?.generationAttemptId && !CanvasGenerationLifecycle.isCurrent(node,meta.generationAttemptId)) return [];
    preserveNodeCardForRun(node);
    const beforeRight = (Number(node.x) || 0) + nodeRect(node).width;
    const existing = cleanHistoryImages(node.images || []);
    const next = cleanHistoryImages(additions);
    if(!next.length) return [];
    const nextUrls = new Set(next.map(image => image.url));
    await moveOutputImagesToHistoryForRun(existing.filter(image => !nextUrls.has(image.url)), {strict:true});
    if(node.generationAttemptId !== attempt || (meta?.generationAttemptId && !CanvasGenerationLifecycle.isCurrent(node,meta.generationAttemptId))) return [];
    node.outputPlacement = 'replace';
    node.images = next;
    delete node.runError;
    node.pending = 0;
    node.running = false;
    delete node.pendingTasks;
    node.runFinishedAt = nowMs();
    if(!node.runStartedAt) node.runStartedAt = meta?.createdAt || node.runFinishedAt;
    node.runElapsedMs = Math.max(0, node.runFinishedAt - Number(node.runStartedAt || node.runFinishedAt));
    node.runTimerHidden = false;
    node.outputKind = kind;
    node.title = cascadeOutputTitle(kind, node.images.length);
    // 自动命名（2026-10-09 补全第三条收口）：RH/API 引擎级联回填此前只给通用名，
    // 重跑后节点标题停留在旧名。comfy（finalizePendingNode）与 supervisor
    // （finalizeSmartPendingTask）两条路已接，这里把 cascade 路径补齐；
    // titleManual（用户手动改名）由 helper 内部保护。autoTitlePrompt 由调用方传真实提示词。
    node.title = CanvasGeneratedOutputNaming.autoNodeTitleFromNode(node, node.title, options.autoTitlePrompt);
    if(meta) attachRunMeta(node, meta);
    const afterRight = (Number(node.x) || 0) + nodeRect(node).width;
    const skipShift = options.skipShift || Boolean(smartLoopContext?.nodeId);
    if(!skipShift) pushRightSideNodes(node, afterRight - beforeRight + 36);
    canvasUiState.patchSelection({image: {nodeId:'', index:-1}}, 'selectedImage');
    return next;
}
function appendOutputsToNode(node, additions, kind='image', options={}){
    if(!node || !additions?.length) return [];
    preserveNodeCardForRun(node);
    const beforeRight = (Number(node.x) || 0) + nodeRect(node).width;
    const existing = (node.images || []).filter(img => img?.url).map(img => stripImageGenerationMeta(img));
    let next = additions.map(img => stripImageGenerationMeta({...img}));
    // 2026-10-19（老王：一个节点只装一张图，旧的进历史）
    if(kind === 'image'){
        if(next.length > 1){
            const extras = next.slice(0, -1);
            next = [next[next.length - 1]];
            spawnImageNodesForExtras(node, extras, options);
        }
        if(existing.length){
            try { Promise.resolve(moveOutputImagesToHistoryForRun(existing, {})).catch(() => {}); } catch(_){}
        }
        node.images = CanvasGenerationResultModel.uniqueMediaItems(next);
    } else {
        node.images = CanvasGenerationResultModel.uniqueMediaItems([...existing, ...next]);
    }
    node.pending = 0;
    node.running = false;
    node.runFinishedAt = nowMs();
    if(!node.runStartedAt) node.runStartedAt = node.runFinishedAt;
    node.runElapsedMs = Math.max(0, node.runFinishedAt - Number(node.runStartedAt || node.runFinishedAt));
    node.runTimerHidden = false;
    node.outputKind = kind;
    node.title = node.images.length > 1 ? (kind === 'video' ? 'Videos' : kind === 'audio' ? 'Audios' : kind === 'text' ? 'Texts' : 'Group') : (kind === 'video' ? 'Video' : kind === 'audio' ? 'Audio' : kind === 'text' ? 'Text' : kind === 'file' ? 'File' : 'Image');
    const afterRight = (Number(node.x) || 0) + nodeRect(node).width;
    const skipShift = options.skipShift || Boolean(smartLoopContext?.nodeId);
    if(!skipShift) pushRightSideNodes(node, afterRight - beforeRight + 36);
    return next;
}
function syncCascadeRunButton(node=selectedNode()){
    if(!cascadeRunBtn) return;
    // ComfyUI 生成节点只保留普通“运行”；一键运行会与工作流/暴露节点控件争抢同一行空间。
    if(settings.engine === 'comfy' || node?.engine === 'comfy'){
        cascadeRunBtn.style.display = 'none';
        cascadeRunBtn.disabled = true;
        return;
    }
    const visible = canRunSmartCascade(node);
    cascadeRunBtn.style.display = visible ? 'inline-flex' : 'none';
    const nodeLoopId = resolveSmartCascadeLoop(node?.id)?.node?.id || '';
    const loopRunState = smartCascadeRunForLoop(nodeLoopId);
    const runningForNode = Boolean(loopRunState);
    cascadeRunBtn.disabled = !visible || (!runningForNode && Boolean(node?.running)) || Boolean(loopRunState?.stopRequested);
    cascadeRunBtn.classList.toggle('is-stop', runningForNode);
    cascadeRunBtn.innerHTML = runningForNode
        ? `<i data-lucide="square"></i><span>${escapeHtml(smartCascadeStopText(Boolean(loopRunState?.stopRequested)))}</span>`
        : `<i data-lucide="workflow"></i><span>${escapeHtml(tr('smart.loopRunAll'))}</span>`;
    refreshIcons();
}
function loadNodePromptDraftToInput(node){
    if(node?.promptDraftRefsEdited) {
        promptInput.innerHTML = node.promptDraftHtml || escapeHtml(node.promptDraftText || '');
    } else if(node?.promptDraftHtml) {
        const hasToken = promptHtmlHasMentionToken(node.promptDraftHtml);
        promptInput.innerHTML = hasToken
            ? node.promptDraftHtml
            : (promptHtmlWithMentionTokens(node.runPrompt || node.promptDraftText || '', node.runPromptRefs || []) || node.promptDraftHtml);
    } else {
        const rebuilt = promptHtmlWithMentionTokens(node?.runPrompt || '', node?.runPromptRefs || []);
        if(rebuilt) promptInput.innerHTML = rebuilt;
        else setPromptText(node?.runPrompt || '');
    }
    if(CanvasPlainTextPaste.cleanFormatting(promptInput) && node){
        node.promptDraftHtml = promptInput.innerHTML;
        scheduleSave();
    }
}
function buildPromptRequestForNode(node, defaultImages, ctx=smartLoopContext){
    const oldHtml = promptInput.innerHTML;
    loadNodePromptDraftToInput(node);
    try {
        return buildPromptRequest(node, defaultImages, false, ctx);
    } finally {
        promptInput.innerHTML = oldHtml;
    }
}
async function generateUrlsForCurrentSettings(node, prompt, refs, runSettings=settings){
    return CanvasGenerationDispatchController.generate(node, prompt, refs, runSettings);
}
async function generateComfyUrlsWithSettings(runSettings, prompt, refs, node=null){
    normalizeComfyWorkflowSelection(runSettings);
    const allRefs = refs || [];
    const imageRefs = comfyWorkflowImageRefsForNode(node, allRefs);
    const mode = runSettings.comfyMode || 'custom';
    if(mode === 'text'){
        const data = await fetch(comfyProxyUrl('/api/generate'), {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({prompt, width:Number(runSettings.width || 1024), height:Number(runSettings.height || 1024), workflow_json:'Z-Image.json', type:'zimage'})
        }).then(async r => { if(!r.ok) throw new Error(await r.text()); return r.json(); });
        const urls = resultMediaUrls(data);
        return {urls, kind:mediaKindForUrls(urls, 'image')};
    }
    if(mode === 'enhance'){
        if(!imageRefs.length) throw new Error(tr('smart.errEnhanceNeedRefs'));
        const inputName = await comfyNameForRef(imageRefs[0]);
        const data = await fetch(comfyProxyUrl('/api/generate'), {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({workflow_json:'Z-Image-Enhance.json', type:'enhance', params:{"15":{image:inputName},"204":{value:Number(runSettings.enhanceStrength ?? 0.5)}}})
        }).then(async r => { if(!r.ok) throw new Error(await r.text()); return r.json(); });
        const urls = resultMediaUrls(data);
        return {urls, kind:mediaKindForUrls(urls, 'image')};
    }
    if(mode === 'edit'){
        if(!imageRefs.length) throw new Error(tr('smart.errEditNeedRefs'));
        const names = [];
        for(const ref of imageRefs.slice(0, 3)) names.push(await comfyNameForRef(ref));
        const data = await fetch(comfyProxyUrl('/api/generate'), {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({prompt, workflow_json:'Flux2-Klein.json', type:'klein', params:{"168":{text:prompt},"158":{noise_seed:Math.floor(Math.random()*1000000)},"278":{image:names[0] || ""},"270":{image:names[1] || ""},"292":{image:names[2] || ""},"313":{value:Boolean(names[1])},"314":{value:Boolean(names[2])}}})
        }).then(async r => { if(!r.ok) throw new Error(await r.text()); return r.json(); });
        const urls = resultMediaUrls(data);
        return {urls, kind:mediaKindForUrls(urls, 'image')};
    }
    const workflowName = runSettings.comfyWorkflow || comfyWorkflows[0]?.name || '';
    if(!workflowName) throw new Error(tr('smart.errNeedWorkflow'));
    const wf = await fetch(comfyProxyUrl(`/api/workflows/${encodeURIComponent(workflowName)}`)).then(async r => {
        if(!r.ok) throw new Error(await r.text());
        return r.json();
    });
    const fields = wf.config?.fields || [];
    const values = {};
    const promptFields = fields.filter(f => comfyFieldKind(f, wf) === 'prompt');
    // 预检/填充只统计未旁路的媒体输入：已暴露节点里被"关"掉的输入不应要求连接(与运行时 modes 旁路一致)
    const imageFields = fields.filter(f => comfyFieldKind(f, wf) === 'image' && !comfyFieldNodeIsOff(f, workflowName));
    const videoFields = fields.filter(f => comfyFieldKind(f, wf) === 'video' && !comfyFieldNodeIsOff(f, workflowName));
    const audioFields = fields.filter(f => comfyFieldKind(f, wf) === 'audio' && !comfyFieldNodeIsOff(f, workflowName));
    if(imageFields.length && !imageRefs.length){
        throw new Error(`ComfyUI 工作流需要 ${imageFields.length} 张输入图，当前 0 张。请把图片节点连到该节点后再运行。`);
    }
    // 2026-09-16：媒体数量不足不再中止 —— 多出来的槽位自动旁路（传几张就用几张），
    // 与用户手动关节点合并提交，自动裁剪不会覆盖用户已保存的开关设置。
    const videoRefs = videoRefsOnly(allRefs);
    const audioRefs = audioRefsOnly(allRefs);
    const autoModes = comfyAutoBypassForMissingMedia([
        {fields:imageFields, refs:imageRefs},
        {fields:videoFields, refs:videoRefs},
        {fields:audioFields, refs:audioRefs},
    ]);
    promptFields.forEach((field, index) => {
        // 2026-10-07 BUGFIX：提示词一律以「大框」（composer 提示词输入框）为准。
        // 原先参数区 textarea 字段（comfyParams[field.id]）优先、大框只做兜底，
        // 导致旧残留把用户在大框里写的提示词整段压住；现在反转优先级。
        // 大框为空（级联/循环等无 UI 输入场景）才回退参数区字段，再回退 default。
        const userVal = runSettings.comfyParams?.[field.id];
        const boxText = index === 0 ? (prompt ?? '') : '';
        if(String(boxText).trim() !== ''){
            values[field.id] = boxText;
        } else if(userVal !== undefined && userVal !== null && String(userVal).trim() !== ''){
            values[field.id] = userVal;
        } else {
            values[field.id] = index === 0 ? boxText : (field.default ?? '');
        }
    });
    const assignMediaFields = async (mediaFields, mediaRefs) => {
        for(let i = 0; i < mediaFields.length && i < mediaRefs.length; i++){
            values[mediaFields[i].id] = await comfyNameForRef(mediaRefs[i]);
        }
    };
    await assignMediaFields(imageFields, imageRefs);
    await assignMediaFields(videoFields, videoRefs);
    await assignMediaFields(audioFields, audioRefs);
    fields.filter(f => comfyFieldKind(f, wf) === 'setting').forEach(field => {
        if(comfyRandomEnabledField(field) && smartComfyRandomActiveFor(runSettings, field.id)){
            values[field.id] = smartComfyRandomValue(field);
        } else {
            values[field.id] = runSettings.comfyParams?.[field.id] ?? field.default;
        }
    });
    return runComfyWorkflowJob(node, runSettings, prompt, allRefs, node, null);
}
async function runCascadeStepIntoNode(sourceNode, targetNode, inputRefs, ctx=smartLoopContext){
    const outputNode = targetNode || sourceNode;
    if(!sourceNode || !targetNode || !outputNode) return [];
    const requestNode = sourceNode?.type === 'smart-loop' ? targetNode : sourceNode;
    const previousSettings = cloneSmartSettings(settings);
    const runSettings = {...cloneSmartSettings(settings), ...cloneSmartSettings(smartSettingsForNode(requestNode) || {})};
    settings = runSettings;
    const outpaintSize = validOutpaintSize(requestNode);
    const selfRefs = sourceNode?.type === 'smart-loop' ? [] : selfReferenceImagesForNode(sourceNode, false, ctx).filter(img => img?.url);
    const sourceRefs = (selfRefs.length ? selfRefs : defaultReferenceImagesFor(requestNode, false, ctx)).filter(img => img?.url);
    const refsForRequest = sourceRefs.length
        ? sourceRefs
        : (inputRefs && inputRefs.length ? inputRefs : null);
    await ensureCustomComfyWorkflowReady(runSettings);
    const request = buildPromptRequestForNode(
        requestNode,
        refsForRequest,
        ctx
    );
    const prompt = (request.prompt || '').trim();
    const displayPrompt = (request.displayPrompt || '').trim();
    const promptOptional = allowsPromptlessCustomComfy(runSettings);
    if((!prompt && !promptOptional) || (!displayPrompt && !promptOptional && !(runSettings.engine === 'comfy' && runSettings.comfyMode === 'enhance'))){
        settings = previousSettings;
        throw new Error('链路节点缺少提示词');
    }
    const meta = {
        prompt,
        displayPrompt:request.displayPrompt || '',
        promptRefs:(request.refs || []).map(ref => ({url:ref.url || '', name:ref.name || '', nodeId:ref.nodeId || '', imageIndex:ref.imageIndex ?? ''})).filter(ref => ref.url),
        inputRefs:(request.refs || []).map(ref => ({url:ref.url || '', name:ref.name || '', nodeId:ref.nodeId || '', imageIndex:ref.imageIndex ?? '', kind:ref.kind || ''})).filter(ref => ref.url),
        sourceNodeId:sourceNode.id,
        settings:JSON.parse(JSON.stringify(runSettings)),
        createdAt:Date.now()
    };
    if(requestNode.promptDraftHtml != null){
        meta.promptHtml = requestNode.promptDraftHtml;
        meta.promptText = requestNode.promptDraftText || request.displayPrompt || '';
    }
    const logKind = runKindForSettings(runSettings);
    const runLog = smartRunSnapshot(requestNode, prompt, request.refs || [], logKind);
    const runLogStart = nowMs();
    const targetPromptState = {
        promptDraftHtml:targetNode.promptDraftHtml,
        promptDraftText:targetNode.promptDraftText,
        runPrompt:targetNode.runPrompt,
        runModelPrompt:targetNode.runModelPrompt,
        runPromptRefs:targetNode.runPromptRefs ? targetNode.runPromptRefs.map(ref => ({...ref})) : undefined,
        runInputRefs:targetNode.runInputRefs ? targetNode.runInputRefs.map(ref => ({...ref})) : undefined,
        runSettings:targetNode.runSettings ? cloneSmartSettings(targetNode.runSettings) : undefined,
        sourceNodeId:targetNode.sourceNodeId,
        runAt:targetNode.runAt
    };
    preserveNodeCardForRun(outputNode, runSettings);
    outputNode.running = true;
    outputNode.runStartedAt = nowMs();
    delete outputNode.runFinishedAt;
    delete outputNode.runElapsedMs;
    outputNode.runTimerHidden = false;
    rememberRecentSmartSettings(runSettings, requestNode);
    render();
    settings = previousSettings;
    try {
        const result = await generateUrlsForCurrentSettings(outputNode, prompt, request.refs || [], runSettings);
        if(!result.urls?.length) throw new Error(result.kind === 'video' ? tr('smart.errNoOutVideos') : tr('smart.errNoOutImages'));
        if(outpaintSize) delete requestNode.outpaintSize;
        const ext = result.kind === 'video' ? 'mp4' : result.kind === 'audio' ? 'mp3' : result.kind === 'text' ? 'txt' : 'png';
        const additions = isApiLikeEngine(runSettings.engine) && runSettings.apiKind !== 'video'
            ? await smartGeneratedOutputItems(result.urls, result.kind || 'image', {displayName:outputNode.title || requestNode.title || '', nodeId:outputNode.id})
            : result.urls.map((item, i) => {
                const url = typeof item === 'string' ? item : item?.url || '';
                const name = (typeof item === 'object' && item.name) || `output-${i + 1}.${ext}`;
                return stripImageGenerationMeta({url, name, kind:(typeof item === 'object' && item.kind) || result.kind, generatedResult:true});
            }).filter(item => item.url);
        addSmartGenerationLog({run:{...runLog, kind:result.kind || logKind}, outputs:additions, runMs:nowMs() - runLogStart});
        await replaceOutputsToNodeWithHistory(outputNode, additions, result.kind, null, {skipShift:Boolean(ctx?.nodeId), autoTitlePrompt:prompt});
        outputNode.runPrompt = targetPromptState.runPrompt;
        outputNode.runModelPrompt = targetPromptState.runModelPrompt;
        outputNode.runPromptRefs = targetPromptState.runPromptRefs || [];
        outputNode.runInputRefs = targetPromptState.runInputRefs || [];
        outputNode.runSettings = targetPromptState.runSettings;
        outputNode.sourceNodeId = targetPromptState.sourceNodeId;
        outputNode.runAt = targetPromptState.runAt;
        if(targetPromptState.promptDraftHtml === undefined) delete outputNode.promptDraftHtml;
        else outputNode.promptDraftHtml = targetPromptState.promptDraftHtml;
        if(targetPromptState.promptDraftText === undefined) delete outputNode.promptDraftText;
        else outputNode.promptDraftText = targetPromptState.promptDraftText;
        ['runPrompt','runModelPrompt','runSettings','sourceNodeId','runAt'].forEach(key => {
            if(targetPromptState[key] === undefined) delete outputNode[key];
        });
        settings = previousSettings;
        render();
        return additions;
    } catch(e) {
        settings = previousSettings;
        if(handleJimengPendingSignal(outputNode, e)){
            render();
            return [];
        }
        outputNode.running = false;
        addSmartGenerationLog({run:runLog, outputs:[], runMs:nowMs() - runLogStart, error:e.message || String(e)});
        render();
        throw e;
    }
}
async function runLoopRoundIntoSlot(loopNode, rootNode, outputSlot, loopIndex, ctx){
    if(!loopNode || !rootNode || !outputSlot) return [];
    const previousSettings = cloneSmartSettings(settings);
    const edgeKey = `${rootNode.id}->${outputSlot.id}`;
    const runSettings = {...cloneSmartSettings(settings), ...cloneSmartSettings(smartSettingsForNode(rootNode) || {})};
    settings = runSettings;
    try {
        const refsForRequest = outputImagesForNode(loopNode, true, ctx).filter(img => img?.url);
        await ensureCustomComfyWorkflowReady(runSettings);
        const request = buildPromptRequestForNode(rootNode, refsForRequest.length ? refsForRequest : null, ctx);
        const prompt = (request.prompt || '').trim();
        const displayPrompt = (request.displayPrompt || '').trim();
        const promptOptional = allowsPromptlessCustomComfy(runSettings);
        if((!prompt && !promptOptional) || (!displayPrompt && !promptOptional && !(runSettings.engine === 'comfy' && runSettings.comfyMode === 'enhance'))) throw new Error('链路节点缺少提示词');
        const meta = {
            prompt,
            displayPrompt:request.displayPrompt || '',
            promptRefs:(request.refs || []).map(ref => ({url:ref.url || '', name:ref.name || '', nodeId:ref.nodeId || '', imageIndex:ref.imageIndex ?? ''})).filter(ref => ref.url),
            inputRefs:(request.refs || []).map(ref => ({url:ref.url || '', name:ref.name || '', nodeId:ref.nodeId || '', imageIndex:ref.imageIndex ?? '', kind:ref.kind || ''})).filter(ref => ref.url),
            sourceNodeId:rootNode.id,
            settings:JSON.parse(JSON.stringify(runSettings)),
            createdAt:Date.now()
        };
        const logKind = runKindForSettings(runSettings);
        const runLog = smartRunSnapshot(rootNode, prompt, request.refs || [], logKind);
        const runLogStart = nowMs();
        const expectedCount = isApiLikeEngine(runSettings.engine) && runSettings.apiKind !== 'video'
            ? Math.max(1, Math.min(8, Number(runSettings.count || 1)))
            : 1;
        outputSlot.queued = false;
        outputSlot.running = true;
        outputSlot.pending = expectedCount;
        outputSlot.runStartedAt = nowMs();
        delete outputSlot.runFinishedAt;
        delete outputSlot.runElapsedMs;
        outputSlot.runTimerHidden = false;
        const runPath = smartCascadePathForCtx(ctx);
        if(runPath?.states) {
            runPath.states[edgeKey] = 'active';
            refreshConnectionLayer();
        }
        render();
        settings = previousSettings;
        let result;
        if(isApiLikeEngine(runSettings.engine) && runSettings.apiKind !== 'video'){
            const taskResult = await runApiGeneration(prompt, request.refs || [], runSettings, rootNode);
            const taskIds = Array.isArray(taskResult?.taskIds) ? taskResult.taskIds : [];
            if(!taskIds.length) throw new Error(tr('smart.errRunFailed'));
            const existing = cleanHistoryImages(outputSlot.images || []);
            if(existing.length && nodeHasCompletedGeneration(outputSlot)){
                const history = ensureHistoryGroupForNode(outputSlot);
                history.images = cleanHistoryImages([...existing, ...(history.images || [])]);
                history.title = '历史分组';
                history.outputKind = 'image';
                history.scale = MEDIA_GROUP_DEFAULT_SCALE;
                delete history.w;
                delete history.h;
                outputSlot.images = [];
            }
            outputSlot.pendingTasks = taskIds.map(taskId => ({taskId, kind:'image'}));
            rememberSmartTaskIds(outputSlot, taskIds);
            outputSlot.pending = Math.max(taskIds.length, Number(outputSlot.pending || 0) || taskIds.length);
            outputSlot.running = false;
            render();
            scheduleSave();
            await saveCanvas();
            await resumeSmartPendingNode(outputSlot);
            if(outputSlot.jimengPending){
                outputSlot.queued = false;
                return [];
            }
            result = {urls:(outputSlot.images || []).map(img => img?.url ? img : null).filter(Boolean), kind:'image'};
        } else {
            result = await generateUrlsForCurrentSettings(outputSlot, prompt, request.refs || [], runSettings);
        }
        if(!result.urls?.length) throw new Error(result.kind === 'video' ? tr('smart.errNoOutVideos') : tr('smart.errNoOutImages'));
        let additions;
        if(isApiLikeEngine(runSettings.engine) && runSettings.apiKind !== 'video'){
            additions = (outputSlot.images || []).map(img => stripImageGenerationMeta({...img})).filter(img => img?.url);
            if(meta) attachRunMeta(outputSlot, meta);
        } else {
            const ext = result.kind === 'video' ? 'mp4' : result.kind === 'audio' ? 'mp3' : result.kind === 'text' ? 'txt' : 'png';
            additions = result.urls.map((item, i) => {
                const url = typeof item === 'string' ? item : item?.url || '';
                return stripImageGenerationMeta({url, name:(typeof item === 'object' && item.name) || `output-${i + 1}.${ext}`, kind:(typeof item === 'object' && item.kind) || result.kind, generatedResult:true});
            }).filter(item => item.url);
            await replaceOutputsToNodeWithHistory(outputSlot, additions, result.kind, meta, {skipShift:Boolean(ctx?.nodeId), autoTitlePrompt:prompt});
        }
        if(runPath?.states) {
            runPath.states[edgeKey] = 'done';
            refreshConnectionLayer();
        }
        addSmartGenerationLog({run:{...runLog, kind:result.kind || logKind}, outputs:additions, runMs:nowMs() - runLogStart});
        return additions;
    } catch(e) {
        if(handleJimengPendingSignal(outputSlot, e)){
            outputSlot.queued = false;
            return [];
        }
        outputSlot.queued = false;
        outputSlot.pending = 0;
        outputSlot.running = false;
        throw e;
    } finally {
        settings = previousSettings;
    }
}
async function appendCascadeRefsToReceiver(node, refs, ctx=smartLoopContext){
    if(!node || !refs?.length) return [];
    const additions = refs
        .filter(ref => ref?.url)
        .map((ref, i) => stripImageGenerationMeta({
            url:ref.url,
            name:ref.name || `output-${i + 1}.png`,
            kind:ref.kind || (isVideoMediaItem(ref) ? 'video' : 'image')
        }));
    if(!additions.length) return [];
    await replaceOutputsToNodeWithHistory(node, additions, mediaKindForUrls(additions, additions.some(isVideoMediaItem) ? 'video' : 'image'), null, {skipShift:Boolean(ctx?.nodeId)});
    render();
    return additions;
}
function cascadeRefsFromOutputs(outputs, targetNode){
    return (outputs || []).filter(img => img?.url).map((img, index) => ({
        url:img.url,
        name:img.name || `图${index + 1}`,
        kind:img.kind || 'image',
        role:`image_${index + 1}`,
        nodeId:targetNode?.id || '',
        imageIndex:targetNode ? (targetNode.images || []).length - outputs.length + index : index
    }));
}
function smartCascadeStopText(stopping=false){
    return stopping ? '停止中...' : '停止运行';
}
function smartCascadeAbortError(){
    const err = new Error('已停止一键运行');
    err.smartCascadeStopped = true;
    return err;
}
function throwIfSmartCascadeStopRequested(runState=null){
    if(runState?.stopRequested || (!runState && smartCascadeStopRequested)) throw smartCascadeAbortError();
}
function requestSmartCascadeStop(loopId=''){
    const runState = loopId ? smartCascadeRunForLoop(loopId) : (smartCascadeRuns.get(smartCascadeActiveLoopId) || [...smartCascadeRuns.values()][0] || null);
    if(runState){
        if(runState.stopRequested) return;
        runState.stopRequested = true;
        syncSmartCascadeLegacyState(runState.runKey || runState.loopId || loopId);
    } else {
        if(!smartCascadeRunning || smartCascadeStopRequested) return;
        smartCascadeStopRequested = true;
    }
    toast('已请求停止，当前任务完成后停止');
    render();
}
function smartCascadeParallelLimit(chain=[]){
    const hasComfy = (chain || []).some(node => smartSettingsForNode(node)?.engine === 'comfy');
    return hasComfy ? Math.max(1, Math.min(6, Number(comfyInstanceCount) || 1)) : 6;
}
async function runSmartCascadeRoundsWithLimit(roundIndexes, limit, runner, runState=null){
    return CanvasCascadeRoundScheduler.runWithLimit(roundIndexes, limit, runner, runState);
}
// 智能级联执行域外移 canvas-smart-cascade-runner.js（第十四刀）。9 个选择/设置/路径态写入走 setter 回主文件真变量。
if(globalThis.CanvasSmartCascadeRunner){CanvasSmartCascadeRunner.configure({
        appendCascadeRefsToReceiver: (...a) => appendCascadeRefsToReceiver(...a),
        canRunSmartCascade: (...a) => canRunSmartCascade(...a),
        cascadeRefsFromOutputs: (...a) => cascadeRefsFromOutputs(...a),
        cloneSmartSettings: (...a) => cloneSmartSettings(...a),
        createLoopOutputSlot: (...a) => createLoopOutputSlot(...a),
        defaultReferenceImagesFor: (...a) => defaultReferenceImagesFor(...a),
        finishLoopTargetPreviewState: (...a) => finishLoopTargetPreviewState(...a),
        isDirectLoopTargetRun: (...a) => isDirectLoopTargetRun(...a),
        isSmartImageNode: (...a) => isSmartImageNode(...a),
        loopOutputSlotForRound: (...a) => loopOutputSlotForRound(...a),
        outputImagesForNode: (...a) => outputImagesForNode(...a),
        pushUndo: (...a) => pushUndo(...a),
        refreshConnectionLayer: (...a) => refreshConnectionLayer(...a),
        refsForDirectLoopRound: (...a) => refsForDirectLoopRound(...a),
        relayLoopPromptNodesForEdge: (...a) => relayLoopPromptNodesForEdge(...a),
        relayLoopPromptNodesForTarget: (...a) => relayLoopPromptNodesForTarget(...a),
        render: (...a) => render(...a),
        requestSmartCascadeStop: (...a) => requestSmartCascadeStop(...a),
        resolveSmartCascadeLoop: (...a) => resolveSmartCascadeLoop(...a),
        runCascadeStepIntoNode: (...a) => runCascadeStepIntoNode(...a),
        runLoopRoundIntoSlot: (...a) => runLoopRoundIntoSlot(...a),
        runSmartCascadeRoundsWithLimit: (...a) => runSmartCascadeRoundsWithLimit(...a),
        savePromptDraftForCurrent: (...a) => savePromptDraftForCurrent(...a),
        scheduleSave: (...a) => scheduleSave(...a),
        selectedNode: (...a) => selectedNode(...a),
        showDirectLoopRoundPreview: (...a) => showDirectLoopRoundPreview(...a),
        smartCascadeAnyRunning: (...a) => smartCascadeAnyRunning(...a),
        smartCascadeGraphForTail: (...a) => smartCascadeGraphForTail(...a),
        smartCascadeIsLoopRunning: (...a) => smartCascadeIsLoopRunning(...a),
        smartCascadeParallelLimit: (...a) => smartCascadeParallelLimit(...a),
        syncSmartCascadeLegacyState: (...a) => syncSmartCascadeLegacyState(...a),
        tagLoopOutputSlot: (...a) => tagLoopOutputSlot(...a),
        throwIfSmartCascadeStopRequested: (...a) => throwIfSmartCascadeStopRequested(...a),
        toast: (...a) => toast(...a),
        trf: (...a) => trf(...a),
        updateComposer: (...a) => updateComposer(...a),
        upstreamLoopPromptNodesFor: (...a) => upstreamLoopPromptNodesFor(...a),
        activeComposerSubject: () => canvasUiState.editor.subject,
        lastComposerNodeId: () => canvasUiState.editor.key,
        selectedId: () => canvasUiState.selection.primaryId,
        selectedIds: () => canvasUiState.selection.ids,
        selectedImage: () => canvasUiState.selection.image,
        settings: () => settings,
        smartCascadeRunPath: () => smartCascadeRunPath,
        smartCascadeSilentSelection: () => smartCascadeSilentSelection,
        smartLoopContext: () => smartLoopContext,
        cascadeRunBtn: () => cascadeRunBtn,
        composer: () => composer,
        promptInput: () => promptInput,
        runBtn: () => runBtn,
        smartCascadeRuns: () => smartCascadeRuns,
        setActiveComposerSubject: v => { canvasUiState.patchEditor({subject: v}, 'activeComposerSubject'); },
        setLastComposerNodeId: v => { canvasUiState.patchEditor({key: v}, 'lastComposerNodeId'); },
        setSelectedId: v => { canvasUiState.patchSelection({primaryId: v}, 'selectedId'); },
        setSelectedIds: v => { canvasUiState.patchSelection({ids: v}, 'selectedIds'); },
        setSelectedImage: v => { canvasUiState.patchSelection({image: v}, 'selectedImage'); },
        setSettings: v => { settings = v; },
        setSmartCascadeRunPath: v => { smartCascadeRunPath = v; },
        setSmartCascadeSilentSelection: v => { smartCascadeSilentSelection = v; },
        setSmartLoopContext: v => { smartLoopContext = v; }
});}
function runSmartCascade(){return CanvasSmartCascadeRunner.runSmartCascade.apply(null, arguments);}
function runSmartCascadeFromLoop(loopId){
    const loop = nodes.find(n => n.id === loopId && n.type === 'smart-loop');
    if(!loop){ toast('没有找到循环节点'); return; }
    const tail = cascadeTailForLoop(loop.id);
    if(!tail){ toast('请把循环节点连接到下游图片链路'); return; }
    canvasUiState.patchSelection({primaryId: tail.id}, 'selectedId');
    canvasUiState.patchSelection({ids: []}, 'selectedIds');
    canvasUiState.patchSelection({image: {nodeId:'', index:-1}}, 'selectedImage');
    runSmartCascade(tail);
}
// 生图执行域外移 canvas-generation-runner.js（第十五刀）。settings/selected 写入走 setter 回主文件真变量。
if(globalThis.CanvasGenerationRunner){CanvasGenerationRunner.configure({
        nodes: () => nodes,
        preserveNodeCardForRun: (...a) => preserveNodeCardForRun(...a),
        addSmartGenerationLog: (...a) => addSmartGenerationLog(...a),
        allowsPromptlessCustomComfy: (...a) => allowsPromptlessCustomComfy(...a),
        attachRunMeta: (...a) => attachRunMeta(...a),
        buildPromptRequest: (...a) => buildPromptRequest(...a),
        clearComfyRunStateKeepPromptId: (...a) => clearComfyRunStateKeepPromptId(...a),
        clearNodeRunningState: (...a) => clearNodeRunningState(...a),
        clearPromptInput: (...a) => clearPromptInput(...a),
        cloneSmartSettings: (...a) => cloneSmartSettings(...a),
        ensureCustomComfyWorkflowReady: (...a) => ensureCustomComfyWorkflowReady(...a),
        finalizePendingNode: (...a) => finalizePendingNode(...a),
        localizeGeneratedOutputItems: (...a) => localizeGeneratedOutputItems(...a),
        mediaKindForUrls: (...a) => mediaKindForUrls(...a),
        handleJimengPendingSignal: (...a) => handleJimengPendingSignal(...a),
        isApiLikeEngine: (...a) => isApiLikeEngine(...a),
        nowMs: (...a) => nowMs(...a),
        pendingBoxSize: (...a) => pendingBoxSize(...a),
        rememberSmartTaskIds: (...a) => rememberSmartTaskIds(...a),
        render: (...a) => render(...a),
        restoreFromExtraction: (...a) => restoreFromExtraction(...a),
        restoreSourceVisualState: (...a) => restoreSourceVisualState(...a),
        resultMediaUrls: (...a) => resultMediaUrls(...a),
        resumeSmartPendingNode: (...a) => resumeSmartPendingNode(...a),
        isPrevizPushWaiting: (...a) => isPrevizPushWaiting(...a),
        runApiGeneration: (...a) => runApiGeneration(...a),
        runApiVideoGeneration: (...a) => runApiVideoGeneration(...a),
        runComfyGeneration: (...a) => runComfyGeneration(...a),
        runRunningHubGeneration: (...a) => runRunningHubGeneration(...a),
        saveCanvas: (...a) => saveCanvas(...a),
        scheduleSave: (...a) => scheduleSave(...a),
        selectedNode: (...a) => selectedNode(...a),
        smartImageUsesWorkflowInput: (...a) => smartImageUsesWorkflowInput(...a),
        smartSettingsForNode: (...a) => smartSettingsForNode(...a),
        syncRunButtonAvailability: (...a) => syncRunButtonAvailability(...a),
        taskIdsFromResult: (...a) => taskIdsFromResult(...a),
        toast: (...a) => toast(...a),
        uid: (...a) => uid(...a),
        updateComfyNodeLiveState: (...a) => updateComfyNodeLiveState(...a),
        selectedId: () => canvasUiState.selection.primaryId,
        selectedImage: () => canvasUiState.selection.image,
        settings: () => settings,
        undoSuppressed: () => undoSuppressed,
        canvas: () => canvas,
        nodeStore: () => nodeStore,
        smartLoopContext: () => smartLoopContext,
        setSelectedId: v => { canvasUiState.patchSelection({primaryId: v}, 'selectedId'); },
        setSelectedImage: v => { canvasUiState.patchSelection({image: v}, 'selectedImage'); },
        setSettings: v => { settings = v; },
        setUndoSuppressed: v => { undoSuppressed = v; }
});}
function runGeneration(){return CanvasGenerationRunner.runGeneration.apply(null, arguments);}
// 生成引擎分发带外移 canvas-engine-dispatch.js（第十九刀）。JimengPendingSignal 类与 transientSmartCloudLinks 走 deps 通道。
if(globalThis.CanvasEngineDispatch){CanvasEngineDispatch.configure({
        applyUploadedUrlsToSmartRefs: (...a) => applyUploadedUrlsToSmartRefs(...a),
        audioRefsOnly: (...a) => audioRefsOnly(...a),
        canvasLLMEndpointForPayload: (...a) => canvasLLMEndpointForPayload(...a),
        comfyFieldMeta: (...a) => comfyFieldMeta(...a),
        currentComfyWorkflowData: (...a) => currentComfyWorkflowData(...a),
        expandSkillMentions: (...a) => (typeof CanvasNodePromptPicker !== 'undefined'
            ? CanvasNodePromptPicker.expandSkillMentions(...a)
            : Promise.resolve(String(a[0] || ''))),
        imageRefsOnly: (...a) => imageRefsOnly(...a),
        manualSmartMediaLinks: (...a) => manualSmartMediaLinks(...a),
        manualSmartVideoLink: (...a) => manualSmartVideoLink(...a),
        normalizePrevizLlmSettings: (...a) => normalizePrevizLlmSettings(...a),
        promptNodeInputMediaForLLM: (...a) => promptNodeInputMediaForLLM(...a),
        render: (...a) => render(...a),
        resolveChatModel: (...a) => resolveChatModel(...a),
        resolveChatProviderId: (...a) => resolveChatProviderId(...a),
        resultMediaUrls: (...a) => resultMediaUrls(...a),
        rhActiveFields: (...a) => rhActiveFields(...a),
        rhBuildNodeInfoList: (...a) => rhBuildNodeInfoList(...a),
        rhBuildWorkflowRequestExtras: (...a) => rhBuildWorkflowRequestExtras(...a),
        rhMediaForRun: (...a) => rhMediaForRun(...a),
        rhOfficialAspectRatioForRun: (...a) => rhOfficialAspectRatioForRun(...a),
        rhOfficialModelForRun: (...a) => rhOfficialModelForRun(...a),
        rhOfficialResolutionForRun: (...a) => rhOfficialResolutionForRun(...a),
        scheduleSave: (...a) => scheduleSave(...a),
        selectedRunningHubRef: (...a) => selectedRunningHubRef(...a),
        shouldUseRhOfficialProxy: (...a) => shouldUseRhOfficialProxy(...a),
        sizeForRun: (...a) => sizeForRun(...a),
        smartResponseErrorMessage: (...a) => smartResponseErrorMessage(...a),
        taskIdsFromResult: (...a) => taskIdsFromResult(...a),
        toast: (...a) => toast(...a),
        uploadCurrentSmartVideosToCloud: (...a) => uploadCurrentSmartVideosToCloud(...a),
        videoProviderPlatform: (...a) => videoProviderPlatform(...a),
        videoReferenceModeValue: (...a) => videoReferenceModeValue(...a),
        videoRefsOnly: (...a) => videoRefsOnly(...a),
        JimengPendingSignal: CanvasSmartTaskSupervisor.JimengPendingSignal,
        transientSmartCloudLinks: () => transientSmartCloudLinks,
        RH_OFFICIAL_PROXY_BASE: () => RH_OFFICIAL_PROXY_BASE,
        canvas: () => canvas,
        canvasId: () => canvasId,
        nodes: () => nodes,
        settings: () => settings,
        setTransientSmartCloudLinks: v => { transientSmartCloudLinks = v; }
});}
function runPromptLLMNode(){return CanvasEngineDispatch.runPromptLLMNode.apply(null, arguments);}
function comfyFieldKind(){return CanvasEngineDispatch.comfyFieldKind.apply(null, arguments);}
function runApiGeneration(){return CanvasEngineDispatch.runApiGeneration.apply(null, arguments);}
function runRunningHubGeneration(){return CanvasEngineDispatch.runRunningHubGeneration.apply(null, arguments);}
function runApiVideoGeneration(){return CanvasEngineDispatch.runApiVideoGeneration.apply(null, arguments);}
function sleep(){return CanvasEngineDispatch.sleep.apply(null, arguments);}
// 清掉「运行中」外观，但保留 comfyPromptId —— 后端重启/任务记录丢失时，
// prompt_id 是之后把 ComfyUI 已经跑完的结果认领回节点的唯一钥匙，不能删。
function clearComfyRunStateKeepPromptId(node){
    CanvasComfyJobEngine.clearComfyRunStateKeepPromptId(node);
}
function clearComfyProgress(node){
    CanvasComfyJobEngine.clearComfyProgress(node);
}
// 2026-09-17：ComfyUI 状态后台监督器
// 运行按钮回弹原本完全依赖 submitComfyWorkflowJob 内部那条「随 runGeneration promise
// 生命周期」的 900ms 轮询。一旦这条 promise 链被打断（切画布 / 智能体重渲染 /
// 标签页休眠 / 异常提前 return），comfyStatus 就永远停在 'running'，按钮卡在红底「停止」态，
// 必须手动点一下才清 —— 即老王说的「状态调取断了」。
// 这里加一层与单次运行 promise 解耦的独立监督：定期回拉后端 job 状态，
// 任务真正结束就把视觉/按钮态清掉（必要时按输出回填产出），实现「状态主动调取」。
async function syncComfyJobStatusOnce(node){
    return CanvasComfyJobEngine.syncComfyJobStatusOnce(node);
}
function startComfyJobSupervisor(){
    CanvasComfyJobEngine.startComfyJobSupervisor();
}
function stopComfyJobSupervisor(){
    CanvasComfyJobEngine.stopComfyJobSupervisor();
}
async function buildComfyWorkflowJobPayload(node, runSettings, prompt, refs){
    normalizeComfyWorkflowSelection(runSettings);
    const allRefs = refs || [];
    const imageRefs = comfyWorkflowImageRefsForNode(node, allRefs);
    const workflowName = runSettings.comfyWorkflow || comfyWorkflows[0]?.name || '';
    if(!workflowName) throw new Error(tr('smart.errNeedWorkflow'));
    const wf = await fetch(comfyProxyUrl(`/api/workflows/${encodeURIComponent(workflowName)}`)).then(async r => {
        if(!r.ok) throw new Error(await r.text());
        return r.json();
    });
    const fields = wf.config?.fields || [];
    const values = {};
    const promptFields = fields.filter(f => comfyFieldKind(f, wf) === 'prompt');
    // 预检/填充只统计未旁路的媒体输入：已暴露节点里被"关"掉的输入不应要求连接(与运行时 modes 旁路一致)
    const imageFields = fields.filter(f => comfyFieldKind(f, wf) === 'image' && !comfyFieldNodeIsOff(f, workflowName));
    const videoFields = fields.filter(f => comfyFieldKind(f, wf) === 'video' && !comfyFieldNodeIsOff(f, workflowName));
    const audioFields = fields.filter(f => comfyFieldKind(f, wf) === 'audio' && !comfyFieldNodeIsOff(f, workflowName));
    if(imageFields.length && !imageRefs.length){
        throw new Error(`ComfyUI 工作流需要 ${imageFields.length} 张输入图，当前 0 张。请把图片节点连到该节点后再运行。`);
    }
    // 2026-09-16：媒体数量不足不再中止 —— 多出来的槽位自动旁路（传几张就用几张），
    // 与用户手动关节点合并提交，自动裁剪不会覆盖用户已保存的开关设置。
    const videoRefs = videoRefsOnly(allRefs);
    const audioRefs = audioRefsOnly(allRefs);
    const autoModes = comfyAutoBypassForMissingMedia([
        {fields:imageFields, refs:imageRefs},
        {fields:videoFields, refs:videoRefs},
        {fields:audioFields, refs:audioRefs},
    ]);
    promptFields.forEach((field, index) => {
        // 2026-10-07 BUGFIX：提示词一律以「大框」（composer 提示词输入框）为准。
        // 原先参数区 textarea 字段（comfyParams[field.id]）优先、大框只做兜底，
        // 导致旧残留把用户在大框里写的提示词整段压住；现在反转优先级。
        // 大框为空（级联/循环等无 UI 输入场景）才回退参数区字段，再回退 default。
        const userVal = runSettings.comfyParams?.[field.id];
        const boxText = index === 0 ? (prompt ?? '') : '';
        if(String(boxText).trim() !== ''){
            values[field.id] = boxText;
        } else if(userVal !== undefined && userVal !== null && String(userVal).trim() !== ''){
            values[field.id] = userVal;
        } else {
            values[field.id] = index === 0 ? boxText : (field.default ?? '');
        }
    });
    const assignMediaFields = async (mediaFields, mediaRefs) => {
        for(let i = 0; i < mediaFields.length && i < mediaRefs.length; i++){
            values[mediaFields[i].id] = await comfyNameForRef(mediaRefs[i]);
        }
    };
    await assignMediaFields(imageFields, imageRefs);
    await assignMediaFields(videoFields, videoRefs);
    await assignMediaFields(audioFields, audioRefs);
    fields.filter(f => comfyFieldKind(f, wf) === 'setting').forEach(field => {
 if(comfyRandomEnabledField(field) && smartComfyRandomActiveFor(runSettings, field.id)){
 values[field.id] = smartComfyRandomValue(field);
 } else {
 values[field.id] = runSettings.comfyParams?.[field.id] ?? field.default;
 }
    });
    const overrides = {};
    fields.forEach(field => {
        const id = field?.id;
        const nodeId = String(field?.node || '').trim();
        const input = String(field?.input || '').trim();
        if(!id || !nodeId || !input || values[id] === undefined) return;
        overrides[nodeId] = overrides[nodeId] || {};
        overrides[nodeId][input] = values[id];
    });
    return {
        workflowName,
        body:{
            workflow:workflowName,
            overrides,
            modes:{...autoModes, ...comfyModesForWorkflow(workflowName, runSettings)},
            prefs:wf.config?.node_prefs || wf.config?.prefs || {}
        }
    };
}
// Comfy 任务提交/轮询域外移 canvas-comfy-job-submitter.js（第八刀）。
if(globalThis.CanvasComfyJobSubmitter){CanvasComfyJobSubmitter.configure({
        comfyProxyUrl: (...a) => comfyProxyUrl(...a),
        render: (...a) => render(...a),
        syncRunButtonAvailability: (...a) => syncRunButtonAvailability(...a),
        scheduleSave: (...a) => scheduleSave(...a),
        startComfyJobSupervisor: (...a) => startComfyJobSupervisor(...a),
        sleep: (...a) => sleep(...a),
        clearComfyRunStateKeepPromptId: (...a) => clearComfyRunStateKeepPromptId(...a),
        updateComfyNodeLiveState: (...a) => updateComfyNodeLiveState(...a),
        canvasId: () => canvasId,
        canvas: () => canvas
});}
function submitComfyWorkflowJob(){return CanvasComfyJobSubmitter.submitComfyWorkflowJob.apply(null, arguments);}
// Comfy/即梦任务监督域外移 canvas-smart-task-supervisor.js（第二刀），此处留注入与薄代理。
if(globalThis.CanvasSmartTaskSupervisor){CanvasSmartTaskSupervisor.configure({
        isComposerOwner: node => canvasUiState.editor.subject?.id === node?.id && selectedNode()?.id === node?.id,
        preserveNodeCardForRun: (...a) => preserveNodeCardForRun(...a),
        addConnection: (...a) => addConnection(...a),
        addSmartGenerationLog: (...a) => addSmartGenerationLog(...a),
        attachRunMeta: (...a) => attachRunMeta(...a),
        autoNodeTitle: (...a) => CanvasGeneratedOutputNaming.autoNodeTitleFromNode(...a),
        buildComfyWorkflowJobPayload: (...a) => buildComfyWorkflowJobPayload(...a),
        clearComfyProgress: (...a) => clearComfyProgress(...a),
        clearNodeRunningState: (...a) => clearNodeRunningState(...a),
        clearPromptInput: (...a) => clearPromptInput(...a),
        comfyProxyUrl: (...a) => comfyProxyUrl(...a),
        comfyWorkflowImageRefsForNode: (...a) => comfyWorkflowImageRefsForNode(...a),
        createNode: (...a) => createNode(...a),
        fileNameFromUrl: (...a) => fileNameFromUrl(...a),
        finalizePendingNode: (...a) => finalizePendingNode(...a),
        generatedDateSequenceName: (...a) => generatedDateSequenceName(...a),
        isSmartImageNode: (...a) => isSmartImageNode(...a),
        mediaKindForUrls: (...a) => mediaKindForUrls(...a),
        mediaNodeDefaultScale: (...a) => mediaNodeDefaultScale(...a),
        nodeRect: (...a) => nodeRect(...a),
        normalizeComfyWorkflowSelection: (...a) => normalizeComfyWorkflowSelection(...a),
        nowMs: (...a) => nowMs(...a),
        render: (...a) => render(...a),
        replaceOutputsToNodeWithHistory: (...a) => replaceOutputsToNodeWithHistory(...a),
        spawnImageNodesForExtras: (...a) => spawnImageNodesForExtras(...a),
        moveOutputImagesToHistoryForRun: (...a) => moveOutputImagesToHistoryForRun(...a),
        restoreNodeBoxAfterFailure: (...a) => restoreNodeBoxAfterFailure(...a),
        resultMediaUrls: (...a) => resultMediaUrls(...a),
        scheduleSave: (...a) => scheduleSave(...a),
        smartGeneratedOutputItems: (...a) => smartGeneratedOutputItems(...a),
        stripImageGenerationMeta: (...a) => stripImageGenerationMeta(...a),
        submitComfyWorkflowJob: (...a) => submitComfyWorkflowJob(...a),
        syncRunButtonAvailability: (...a) => syncRunButtonAvailability(...a),
        toast: (...a) => toast(...a),
        nodes: () => nodes,
        settings: () => settings
});}

function runComfyWorkflowJob(){return CanvasSmartTaskSupervisor.runComfyWorkflowJob.apply(null, arguments);}

function runComfyGeneration(){return CanvasSmartTaskSupervisor.runComfyGeneration.apply(null, arguments);}

function comfyNameForRef(){return CanvasSmartTaskSupervisor.comfyNameForRef.apply(null, arguments);}

function smartPendingTasks(){return CanvasSmartTaskSupervisor.smartPendingTasks.apply(null, arguments);}

function rememberSmartTaskIds(){return CanvasSmartTaskSupervisor.rememberSmartTaskIds.apply(null, arguments);}

function jimengQueueText(){return CanvasSmartTaskSupervisor.jimengQueueText.apply(null, arguments);}

function handleJimengPendingSignal(){return CanvasSmartTaskSupervisor.handleJimengPendingSignal.apply(null, arguments);}

function queryJimengNow(){return CanvasSmartTaskSupervisor.queryJimengNow.apply(null, arguments);}

function resumeJimengPendingNodes(){return CanvasSmartTaskSupervisor.resumeJimengPendingNodes.apply(null, arguments);}

function pollSmartCanvasTask(){return CanvasSmartTaskSupervisor.pollSmartCanvasTask.apply(null, arguments);}

function resumeSmartPendingNode(){return CanvasSmartTaskSupervisor.resumeSmartPendingNode.apply(null, arguments);}
function isPrevizPushWaiting(){return CanvasSmartTaskSupervisor.isPrevizPushWaiting.apply(null, arguments);}

function recoverStuckComfyNodes(){return CanvasSmartTaskSupervisor.recoverStuckComfyNodes.apply(null, arguments);}

function resumeSmartPendingTasks(){return CanvasSmartTaskSupervisor.resumeSmartPendingTasks.apply(null, arguments);}

function recoverCompletedEmptySmartNodes(){return CanvasSmartTaskSupervisor.recoverCompletedEmptySmartNodes.apply(null, arguments);}
function runComfyText(){return CanvasSmartTaskSupervisor.runComfyText.apply(null, arguments);}
function runComfyEnhance(){return CanvasSmartTaskSupervisor.runComfyEnhance.apply(null, arguments);}
function runComfyEdit(){return CanvasSmartTaskSupervisor.runComfyEdit.apply(null, arguments);}
function fallbackGeneratedOutputItems(){return CanvasSmartTaskSupervisor.fallbackGeneratedOutputItems.apply(null, arguments);}
function setNodeJimengPending(){return CanvasSmartTaskSupervisor.setNodeJimengPending.apply(null, arguments);}
function finalizeJimengPending(){return CanvasSmartTaskSupervisor.finalizeJimengPending.apply(null, arguments);}
function applyJimengQueryResult(){return CanvasSmartTaskSupervisor.applyJimengQueryResult.apply(null, arguments);}
function fetchJimengQuery(){return CanvasSmartTaskSupervisor.fetchJimengQuery.apply(null, arguments);}
function startJimengPoll(){return CanvasSmartTaskSupervisor.startJimengPoll.apply(null, arguments);}
function finalizeSmartPendingTask(){return CanvasSmartTaskSupervisor.finalizeSmartPendingTask.apply(null, arguments);}
function recoverCompletedEmptySmartNode(){return CanvasSmartTaskSupervisor.recoverCompletedEmptySmartNode.apply(null, arguments);}
function isRecoverableComfyNode(){return CanvasSmartTaskSupervisor.isRecoverableComfyNode.apply(null, arguments);}
function updateSelectionBox(event){
    if(!selectionState) return;
    const sx = selectionState.startScreen.x, sy = selectionState.startScreen.y;
    const x = Math.min(sx, event.clientX), y = Math.min(sy, event.clientY);
    selectionBox.style.display = 'block';
    selectionBox.style.left = `${x}px`;
    selectionBox.style.top = `${y}px`;
    selectionBox.style.width = `${Math.abs(event.clientX - sx)}px`;
    selectionBox.style.height = `${Math.abs(event.clientY - sy)}px`;
}
function finishSelection(event){
    if(!selectionState) return;
    const a = selectionState.startWorld;
    const b = screenToWorld(event);
    const minX = Math.min(a.x, b.x), minY = Math.min(a.y, b.y);
    const maxX = Math.max(a.x, b.x), maxY = Math.max(a.y, b.y);
    canvasUiState.patchSelection({ids: nodes.filter(node => {
        const r = nodeRect(node);
        return r.x < maxX && r.x + r.width > minX && r.y < maxY && r.y + r.height > minY;
    }).map(n => n.id)}, 'selectedIds');
    canvasUiState.patchSelection({primaryId: canvasUiState.selection.ids.length === 1 ? canvasUiState.selection.ids[0] : ''}, 'selectedId');
    canvasUiState.patchSelection({image: {nodeId:'', index:-1}}, 'selectedImage');
    selectionState = null;
    if (typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.end('box-selecting');
    selectionJustFinished = true;
    selectionBox.style.display = 'none';
    focusCanvasWorld();
    render();
    setTimeout(() => { selectionJustFinished = false; }, 0);
}
function groupSelectedNodes(){
    return CanvasNodeLayoutController.groupSelectedNodes();
}
CanvasKeyboardShortcutController.configure({
    getWorld:() => world,
    getDeleteShortcutHandledAt:() => deleteShortcutHandledAt,
    getSelectedIds:() => canvasUiState.selection.ids,
    getSelectedId:() => canvasUiState.selection.primaryId,
    selectedNodeIds:() => selectedNodeIds(),
    isDeleteShortcut:event => isDeleteShortcut(event),
    deleteSelectedNodesFromKeyboard:event => deleteSelectedNodesFromKeyboard(event),
    groupSelectedNodes:() => groupSelectedNodes(),
    isEditableTarget:target => isEditableTarget(target),
    isImageCropActive:() => CanvasImageCrop.isActive(),
    confirmImageCrop:() => CanvasImageCrop.confirm(),
    stopImageCrop:() => CanvasImageCrop.stop(),
    setIsRKeyDown:value => {isRKeyDown = value;},
    isImageEditOpen:() => imageEditModal.classList.contains('open'),
    seekPreviewVideoFrames:direction => seekPreviewVideoFrames(direction),
    navigatePreviewImage:direction => navigatePreviewImage(direction),
    toggleZoomPreview:() => toggleZoomPreview(),
    toggleAssetLibrary:() => toggleAssetLibrary(),
    copySelectedNodes:() => copySelectedNodes(),
    hasClipboardNodes:() => CanvasNodeClipboardController.hasClipboardNodes(),
    getLastImagePasteAt:() => lastImagePasteAt,
    getLastNodePasteAt:() => lastNodePasteAt,
    pasteNodes:() => pasteNodes(),
    closeImageEditor:() => closeImageEditor(),
    performUndo:() => performUndo(),
    ungroupNode:id => ungroupNode(id),
    isConnectionCutActive:() => Boolean(connectionCutState),
    finishConnectionCutGesture:() => finishConnectionCutGesture(),
    closeGlobalOverlays:() => {
        closeAllSmartPopovers();
        closeCreateMenu();
        closeSmartCanvasLog();
        closeSmartCanvasShortcuts();
        closePromptPresetPanel();
        closePromptTemplatePanel();
    }
});
CanvasKeyboardShortcutController.bindNodeCaptureHandlers();
function alignSelectedNodesLeft(){
return CanvasNodeLayoutController.alignSelectedNodesLeft();
}
function alignSelectedNodesTop(){
return CanvasNodeLayoutController.alignSelectedNodesTop();
}
function matchSelectedNodeSizes(){
return CanvasNodeLayoutController.matchSelectedNodeSizes();
}
function distributeSelectedNodesHorizontally(){
return CanvasNodeLayoutController.distributeSelectedNodesHorizontally();
}
function distributeSelectedNodesVertically(){
return CanvasNodeLayoutController.distributeSelectedNodesVertically();
}
function handleSmartNodeToolAction(action, event=null){
    return CanvasNodeLayoutController.handleToolAction(action, event);
}
function ungroupNode(groupId){
    return CanvasNodeLayoutController.ungroupNode(groupId);
}
function closeCreateMenu(){
    createMenu?.classList.remove('open');
    // 菜单关掉 = 用户没选（或按 Esc），挂起的连线意图作废，灰化状态也要还原
    if(cancelPendingPortDrop()) refreshCreateMenuAvailability();
}
function openCreateMenuFromDock(){
    if(!createMenu || !canvasAddToggle) return;
    if(cancelPendingPortDrop()) refreshCreateMenuAvailability();
    createMenuPoint = viewportCenter();
    const rect = canvasAddToggle.getBoundingClientRect();
    const w = 520;
    const h = 460;
    const left = Math.max(14, Math.min(window.innerWidth - w - 14, rect.right + 12));
    const top = Math.max(14, Math.min(window.innerHeight - h - 14, rect.top - 8));
    createMenu.style.left = `${left}px`;
    createMenu.style.top = `${top}px`;
    createMenu.classList.add('open');
    refreshIcons();
}
function openCreateMenu(event){
    if(!createMenu) return;
    if(cancelPendingPortDrop()) refreshCreateMenuAvailability();
    createMenuPoint = screenToWorld(event);
    const w = 520;
    const h = 460;
    const left = Math.max(14, Math.min(window.innerWidth - w - 14, event.clientX + 8));
    const top = Math.max(14, Math.min(window.innerHeight - h - 14, event.clientY + 8));
    createMenu.style.left = `${left}px`;
    createMenu.style.top = `${top}px`;
    createMenu.classList.add('open');
    refreshIcons();
}
function setMinimapOpen(open){
    CanvasRenderScheduler.setMinimapOpen(open);
}
function createNodeFromMenu(type){
    const p = createMenuPoint || viewportCenter();
    // 拖线落空来的：先摘下 pending（closeCreateMenu 会清状态），建完节点再补连线
    const pending = pendingPortDrop;
    closeCreateMenu();
    const finish = node => (pending ? finishPendingPortDrop(pending, node) : node);
if(type === 'speech') return finish(createSpeechNode(p));
if(type === 'prompt') return finish(createPromptNode(p.x - 158, p.y - 97));
if(type === 'script' || type === 'llm') return finish(createPromptNode(p.x - 158, p.y - 97));
if(type === 'loop') return finish(createLoopNode(p.x - 135, p.y - 95));
    if(type === 'generator') return finish(createSmartGeneratorNode(p, {engine:'blender', apiKind:'image', title:'3D预演'}));
    if(type === 'video') return finish(createSmartGeneratorNode(p, {engine:'api', apiKind:'video', title:'视频生成'}));
    if(type === 'rh') return finish(createSmartGeneratorNode(p, {engine:'runninghub', apiKind:'image', title:'RH生成'}));
 if(type === 'comfy') return finish(createSmartGeneratorNode(p, {engine:'comfy', comfyMode:'custom', comfyWorkflow:comfyWorkflows[0]?.name || '', apiKind:'image', title:'ComfyUI 生成'}));
    return finish(createImageNodeAt(p));
}
shell.addEventListener('mousedown', e => {
    if(!CanvasViewport.inZoomPreview()) return;
    if(e.button !== 0) return;
    if(isCanvasZoomPreviewExcluded(e.target)) return;
    e.preventDefault();
    e.stopPropagation();
}, true);
shell.addEventListener('click', e => {
    if(!CanvasViewport.inZoomPreview()) return;
    if(e.button !== 0) return;
    if(isCanvasZoomPreviewExcluded(e.target)) return;
    e.preventDefault();
    e.stopPropagation();
    const nodeEl = e.target.closest('.image-node');
    if(nodeEl?.dataset?.id) exitZoomPreviewToNode(nodeEl.dataset.id);
    else exitZoomPreview(screenToWorld(e));
}, true);
function startCanvasMiddlePan(e, opts){
    if(!e || e.button !== 1) return false;
    // 幂等：pointerdown 已启动平移时，随后的 mousedown 不再重置起点（两种事件可能都到达）
    if(panState){ if(e.cancelable) e.preventDefault(); return true; }
    if(isCanvasMiddlePanExcludedTarget(e.target)) return false;
    if(!shell.contains(e.target)) return false;
    // keepCompat：来自 pointerdown 入口时不能 preventDefault —— 那会抑制整条兼容性鼠标事件链
    // （mousedown/mousemove/mouseup），平移反而彻底失效。此处仍要拦 Chrome 中键自动滚动，
    // 故由紧随其后的 mousedown（若派发）补 preventDefault。
    if(!(opts && opts.keepCompat) && e.cancelable) e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation?.();
    closeSmartImageContextMenu();
    smMarkPanSticky(false);
    if(document.activeElement?.blur) document.activeElement.blur();
    panState = {button:e.button, startX:e.clientX, startY:e.clientY, ox:viewport.x, oy:viewport.y};
    if (typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.begin('panning');
    shell.classList.add('panning');
    return true;
}
shell.addEventListener('mousedown', e => {
    startCanvasMiddlePan(e);
}, true);
shell.addEventListener('auxclick', e => {
    if(e.button !== 1 || isCanvasMiddlePanExcludedTarget(e.target)) return;
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation?.();
}, true);
// 防御：即使 mouseup 被某些元素拦截/丢失，也强制结束中键平移（检测到中键已松开）
document.addEventListener('mouseup', () => {
    if(panState){
        panState = null;
        shell.classList.remove('panning');
        if (typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.end('panning');
    }
}, true);
document.addEventListener('mousemove', e => {
    if(panState && (e.buttons & 4) === 0){
        panState = null;
        shell.classList.remove('panning');
        if (typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.end('panning');
    }
}, true);
// 状态机白名单：框选中叠中键=box-selecting/panning 短暂并存（设计内瞬态：
// 平移不抢路由、框选继续，见 smChainModeProbe 优先级）。2ca9b2a 后 mouseup
// 主链只认对应按钮收尾，"打残框选"行为债已修，此豁免仅为并存窗口保留。
if (typeof CanvasInteractionMachine !== 'undefined') {
    CanvasInteractionMachine.addOverlapWhitelist(function (from, to) {
        return (from === 'box-selecting' && to === 'panning') || (from === 'panning' && to === 'box-selecting');
    });
}

// —— 第6步：Escape 一键取消（cancel 钩子=清状态+清视觉+还原必要副作用；不做未完成的提交）
if (typeof CanvasInteractionMachine !== 'undefined') {
    const SM = CanvasInteractionMachine;
    SM.registerCancel('panning', () => {
        if(panState){
            viewport.x = panState.ox; viewport.y = panState.oy;
            scheduleViewportApply();
            SM.setSticky('gesture:pan', Infinity);
            panState = null;
        }
        shell.classList.remove('panning');
    });
    SM.registerCancel('box-selecting', () => {
        selectionState = null;
        const sb = document.getElementById('selectionBox');
        if(sb) sb.style.display = 'none';
    });
    SM.registerCancel('dragging-node', () => {
        if(dragState){
            (dragState.group || [{id:dragState.id, ox:dragState.ox, oy:dragState.oy}]).forEach(item => {
                const n = nodes.find(x => x.id === item.id);
                if(n){ n.x = item.ox; n.y = item.oy; }
            });
            discardPendingUndo();
            SM.setSticky('gesture:node-click', 180);
            dragState = null;
            render();
            scheduleSave();
        }
    });
    SM.registerCancel('connecting', () => {
        if(portDragState){
            portDragState = null;
            shell.classList.remove('port-dragging');
            clearPortDragVisual();
        }
    });
    SM.registerCancel('cutting', () => {
        // 取消=不剪任何连线：直接清手势（不走 finish 的 cut 提交）
        connectionCutState = null;
        shell.classList.remove('cutting-connections');
        shell.classList.remove('panning');
        hideConnScissor();
        clearCutTrail();
        clearCutMarks();
    });
    SM.registerCancel('resizing', () => {
        if(resizeState){
            const node = nodes.find(n => n.id === resizeState.id);
            if(node){
                node.w = resizeState.startW; node.h = resizeState.startH; node.scale = 1;
                if(resizeState.startCardSizing === undefined) delete node.cardSizing;
                else node.cardSizing = resizeState.startCardSizing;
                if(node.cardSize) node.cardSize = {width:node.w, height:node.h};
                discardPendingUndo();
                render();
            }
            resizeState = null;
            scheduleSave();
        }
    });
    SM.registerCancel('minimap-panning', () => {
        if (typeof CanvasRenderScheduler !== 'undefined') CanvasRenderScheduler.endMinimapDrag();
    });
    SM.registerCancel('prompt-resize', () => {
        if(promptResizeState){ promptResizeState = null; scheduleSave(); }
    });
    SM.registerCancel('thumb-drag', () => {
        if(thumbDragState){
            if(!thumbDragState.detached) discardPendingUndo();
            thumbDragState = null;
        }
    });
    SM.registerCancel('input-thumb-drag', () => {
        inputThumbDragState = null;
        clearInputThumbDragClasses();
    });
    SM.registerCancel('preview-compare', () => { previewCompareDrag = false; });
    SM.registerCancel('panorama-drag', () => {
        panoramaState.drag = null;
        document.getElementById('previewStage')?.classList.remove('panning');
    });
    SM.registerCancel('preview-pan', () => {
        previewPanDrag = null;
        document.getElementById('previewStage')?.classList.remove('panning');
    });
    SM.registerCancel('image-edit-pan', () => { imageEditPanDrag = null; });
    SM.registerCancel('crop-drag', () => {
        cropDrag = null;
        document.getElementById('cropCanvas')?.classList.remove('dragging-image');
    });
    window.addEventListener('keydown', e => {
        if(e.key !== 'Escape' || e.repeat) return;
        if(SM.current() === 'idle') return;              // 无交互进行中：交还给既有 Escape 语义
        const canceled = SM.cancelActive();
        if(canceled){ e.preventDefault(); e.stopPropagation(); }
    }, true);
}
shell.onmousedown = e => {
    if (typeof CanvasInteractionObserver !== 'undefined') CanvasInteractionObserver.tick();
    if(CanvasViewport.inZoomPreview() && e.button === 0 && !isCanvasOverlayTarget(e.target)) return;
    // 左键点击画布（节点/空白）时主动 blur 输入框，避免焦点残留导致 Del 删除偶发失效（用户要求 2026-08-16）
    if(e.button === 0 && !isEditableTarget(e.target)){
        if(document.activeElement?.blur) document.activeElement.blur();
    }
    if(e.button === 2 && e.altKey && !isCanvasOverlayTarget(e.target)){
        startConnectionCutGesture(e, connectionIndexFromTarget(e.target));
        return;
    }
    if(isConnectionInteractionTarget(e.target)) return;
    closeSmartImageContextMenu();
    if(startCanvasMiddlePan(e)) return;
    if(e.target.closest('.image-node') || isCanvasOverlayTarget(e.target)) return;
    // 同上：吞掉拖线落空那次手势的 mousedown，否则会顺手开始框选并关掉菜单
    if(portDropClickGuardActive()){ portDropClickGuardUntil = 0; return; }
    closeCreateMenu();
    if(e.button === 0){
        e.preventDefault();
        smMarkPanSticky(false);
        selectionState = {startScreen:{x:e.clientX, y:e.clientY}, startWorld:screenToWorld(e)};
        if (typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.begin('box-selecting');
        updateSelectionBox(e);
        return;
    }
};
shell.oncontextmenu = e => {
    if((e.ctrlKey || e.metaKey) || isRKeyDown){
        e.preventDefault();
        e.stopPropagation();
        return;
    }
    if(e.altKey && !isCanvasOverlayTarget(e.target)){
        // 划断手势的唯一入口是 mousedown。contextmenu 是 mouseup 之后才到的，
        // 那时手势已经 finish 了；若在这里重启，就会留下一个没有 mouseup 收尾的
        // 手势——表现就是“松掉鼠标还在一直划”。所以这里只负责吞掉右键菜单。
        e.preventDefault();
        e.stopPropagation();
        return;
    }
    closeSmartImageContextMenu();
    if(isConnectionInteractionTarget(e.target)) return;
    // 可编辑控件（textarea / input / contenteditable / 提示词框）：弹出画布自带的
    // 复制/粘贴/全选菜单。真机跑在 WebView2 里，系统原生右键菜单被宿主关掉了，
    // 所以不能再"放行原生菜单"——必须自己画一个，否则右键提示词框啥都没有（只能靠快捷键）。
    const editField = CanvasEditableContextMenuController.isEditableTarget(e.target);
    if(editField){
        e.preventDefault();
        e.stopPropagation();
        CanvasEditableContextMenuController.open(editField, e);
        return;
    }
    const nodeEl = e.target.closest('.image-node');
    if(nodeEl){
        const nodeId = nodeEl.dataset?.id;
        if(!nodeId) return;
        // 缩略图仍走图片菜单（它有更完整的操作）；其余区域走节点菜单。
        if(e.target.closest('.thumb-item')) return;
        e.preventDefault();
        e.stopPropagation();
        selectNodeFromPointer(nodeId);
        syncSelectionUi();
        CanvasNodeContextMenuController.open(nodeId, e);
        return;
    }
    if(isCanvasOverlayTarget(e.target)) return;
    if(document.getElementById('imageEditModal')?.classList.contains('open')) return;
    e.preventDefault();
    e.stopPropagation();
    openCreateMenu(e);
};
shell.ondblclick = e => {
    if(isConnectionInteractionTarget(e.target)) return;
    if(smPanSticky() || isCanvasClickEmptyExcluded(e.target)) return;
    if(document.getElementById('imageEditModal')?.classList.contains('open')) return;
    e.preventDefault();
    openCreateMenu(e);
};
shell.onclick = e => {
    // 拖线落空刚弹的菜单：吞掉同一次手势带出来的 click，否则菜单会被立刻关掉
    if(portDropClickGuardActive() && !e.target.closest?.('.create-menu')){ portDropClickGuardUntil = 0; return; }
    if(selectionJustFinished) return;
    closeSmartImageContextMenu();
    if(isConnectionInteractionTarget(e.target)) return;
    if(smPanSticky() || isCanvasClickEmptyExcluded(e.target)) return;
    if(document.getElementById('imageEditModal')?.classList.contains('open')) return;
    closeCreateMenu();
    clearSelection();
    render();
};
shell.addEventListener('dblclick', e => {
    openImagePreviewFromCanvasDblClick(e);
}, {capture:true});
shell.addEventListener('pointermove', rememberCanvasPointerClient, {passive:true, capture:true});
shell.addEventListener('mousemove', rememberCanvasPointerClient, {passive:true, capture:true});
shell.addEventListener('mouseenter', rememberCanvasPointerClient, {passive:true, capture:true});
shell.addEventListener('pointerdown', rememberCanvasPointerClient, {passive:true, capture:true});
shell.addEventListener('mousedown', rememberCanvasPointerClient, {passive:true, capture:true});
// 指针离开 shell 就把记忆作废：滚轮缩放的锚点必须来自本次事件坐标，
// 陈旧记忆会让画面「固定从几秒前去过的某个点放大」（2026-10-07）。
shell.addEventListener('mouseleave', forgetCanvasPointerClient, {passive:true, capture:true});
shell.addEventListener('pointerleave', forgetCanvasPointerClient, {passive:true, capture:true});
// 中键平移补一条 pointerdown 入口：SVG 元素（连线 path / 剪刀 circle）上中键只派发 pointerdown、
// 不派发 mousedown，落在连线或已弹出的剪刀按钮上时旧入口收不到事件，导致「线多了没地方拖」。
// 这里只 stopPropagation（阻止剪刀按钮自己在 pointerdown 里 preventDefault 吞掉事件链），
// 不动 preventDefault，保证 mousedown/mousemove/mouseup 照常派发，平移驱动不受影响。
// 放在 rememberCanvasPointerClient 之后，保证先记录指针坐标再启动平移（行为零变更）。
shell.addEventListener('pointerdown', e => {
    if(e.button !== 1) return;
    if(isCanvasMiddlePanExcludedTarget(e.target)) return;
    if(!shell.contains(e.target)) return;
    e.stopPropagation();
    e.stopImmediatePropagation?.();
    startCanvasMiddlePan(e, {keepCompat:true});
}, true);
document.addEventListener('mousedown', e => {
    if(!e.target.closest?.('#smartImageContextMenu')) closeSmartImageContextMenu();
    // 节点右键菜单：点它自己（按钮）不关，点了外面才关
    if(!e.target.closest?.('#smartNodeContextMenu')) CanvasNodeContextMenuController.close();
    // 编辑右键菜单（复制/粘贴/全选）：同理
    if(!e.target.closest?.('#smartEditableContextMenu')) CanvasEditableContextMenuController.close();
}, true);
window.addEventListener('resize', closeSmartImageContextMenu);
window.addEventListener('resize', () => CanvasNodeContextMenuController.close());
window.addEventListener('resize', () => CanvasEditableContextMenuController.close());
document.addEventListener('keydown', e => {
    if(e.key === 'Escape' && CanvasNodeContextMenuController.isOpen()) CanvasNodeContextMenuController.close();
    if(e.key === 'Escape' && CanvasEditableContextMenuController.isOpen()) CanvasEditableContextMenuController.close();
}, true);
window.addEventListener('dragstart', e => { if(resizeState || dragState){ e.preventDefault(); e.stopPropagation(); } }, true);
minimap?.addEventListener('mousedown', e => {
    if(e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();
    CanvasRenderScheduler.beginMinimapDrag();
    if (typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.begin('minimap-panning');
    centerViewportOnWorldPoint(minimapEventToWorld(e));
});
// —— 第7步：粘滞标志统一入口（表在 CanvasInteractionMachine，语义与原布尔/时间戳一致）
function smPanSticky(){ return (typeof CanvasInteractionMachine !== 'undefined') && CanvasInteractionMachine.stickyActive('gesture:pan'); }
function smMarkPanSticky(v){
    if (typeof CanvasInteractionMachine === 'undefined') return;
    if (v) CanvasInteractionMachine.setSticky('gesture:pan', Infinity);
    else CanvasInteractionMachine.clearSticky('gesture:pan');
}
function smNodeClickSuppressed(){ return (typeof CanvasInteractionMachine !== 'undefined') && CanvasInteractionMachine.stickyActive('gesture:node-click'); }
function smSuppressNodeClick(ms){ if (typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.setSticky('gesture:node-click', ms || 180); }

function smChainModeProbe(){
    // 第三刀：15 态全覆盖的唯一路由源——按旧链真实优先级返回首个命中态 mode 名。
    // 注意两条历史语义：cropDrag 非空但 cropState 空 → 原链跳过继续往下；
    // thumb 未拆分 → 原链分支内 else return（链内重算兜住拆分升级后的 fall-through）。
    if(connectionCutState) return 'cutting';
    if(CanvasRenderScheduler.inMinimapDrag()) return 'minimap-panning';
    if(portDragState) return 'connecting';
    if(promptResizeState) return 'prompt-resize';
    if(selectionState) return 'box-selecting';
    if(previewCompareDrag) return 'preview-compare';
    if(panoramaState && panoramaState.drag) return 'panorama-drag';
    if(previewPanDrag) return 'preview-pan';
    if(imageEditPanDrag) return 'image-edit-pan';
    if(cropDrag && cropState) return 'crop-drag';
    if(resizeState) return 'resizing';
    if(thumbDragState) return 'thumb-drag';
    if(inputThumbDragState) return 'input-thumb-drag';
    if(panState) return 'panning';
    if(dragState) return 'dragging-node';
    return 'idle';
}

if (typeof CanvasInteractionMachine !== 'undefined') {
    CanvasInteractionMachine.configure({ route: () => smChainModeProbe() });
}

window.onmousemove = e => {
    if (typeof CanvasInteractionObserver !== 'undefined') CanvasInteractionObserver.tick();
    let smRoute = smChainModeProbe();
    if (typeof CanvasInteractionMachine !== 'undefined' && smRoute) {
        CanvasInteractionMachine.dispatchShadow(smRoute);
    }
lastMouseWorld = screenToWorld(e);
    if(smRoute === 'cutting'){
        e.preventDefault();
        updateConnectionCutGesture(e);
        return;
    }
    if(smRoute === 'minimap-panning'){
        e.preventDefault();
        centerViewportOnWorldPoint(minimapEventToWorld(e));
        return;
    }
    if(smRoute === 'connecting'){
        e.preventDefault();
        const p = screenToWorld(e);
        portDragState.currentWorld = p;
        portDragState.moved = true;
        const hitEl = document.elementFromPoint(e.clientX, e.clientY);
        const portEl = hitEl?.closest?.('.node-port');
        const nodeEl = portEl?.closest?.('.image-node') || hitEl?.closest?.('.image-node');
        let targetId = '', targetPort = '';
        if(nodeEl && nodeEl.dataset.id && nodeEl.dataset.id !== portDragState.fromId){
            targetId = nodeEl.dataset.id;
            if(portEl){
                targetPort = portEl.dataset.port;
            } else {
                const rect = nodeEl.getBoundingClientRect();
                targetPort = (e.clientX - rect.left) < rect.width / 2 ? 'in' : 'out';
            }

            const compatible = (portDragState.fromPort === 'out' && targetPort === 'in') || (portDragState.fromPort === 'in' && targetPort === 'out');
            if(!compatible){ targetId = ''; targetPort = ''; }
        }
        portDragState.hoverTargetId = targetId;
        portDragState.hoverPort = targetPort;
        updatePortDragVisual();
        return;
    }
    if(smRoute === 'prompt-resize'){
        e.preventDefault();
        const dy = e.clientY - promptResizeState.startY;
        settings.promptH = Math.max(60, Math.min(380, promptResizeState.startH + dy));
        promptInput.style.setProperty('--prompt-h', `${settings.promptH}px`);
        persistActiveSmartSettings();
        return;
    }
    if(smRoute === 'box-selecting'){
        e.preventDefault();
        updateSelectionBox(e);
        return;
    }
    if(smRoute === 'preview-compare'){
        e.preventDefault();
        setPreviewComparePos(e.clientX);
        return;
    }
    if(smRoute === 'panorama-drag'){
        e.preventDefault();
        const dx = e.clientX - panoramaState.drag.clientX;
        const dy = e.clientY - panoramaState.drag.clientY;
        panoramaState.yaw = panoramaState.drag.yaw - dx * 0.18;
        panoramaState.pitch = Math.max(-85, Math.min(85, panoramaState.drag.pitch + dy * 0.18));
        document.getElementById('previewStage')?.classList.add('panning');
        return;
    }
    if(smRoute === 'preview-pan'){
        const stage = document.getElementById('previewStage');
        CanvasImagePreviewTransformController.setPan({
            x:previewPanDrag.startX + (e.clientX - previewPanDrag.clientX),
            y:previewPanDrag.startY + (e.clientY - previewPanDrag.clientY)
        });
        stage?.classList.add('panning');
        return;
    }
    if(smRoute === 'image-edit-pan'){
        const stage = document.getElementById('imageEditStage');
        if(stage){
            stage.scrollLeft = imageEditPanDrag.scrollLeft - (e.clientX - imageEditPanDrag.clientX);
            stage.scrollTop = imageEditPanDrag.scrollTop - (e.clientY - imageEditPanDrag.clientY);
        }
        return;
    }
    if(smRoute === 'crop-drag'){
        const dx = e.clientX - cropDrag.sx;
        const dy = e.clientY - cropDrag.sy;
        if(cropDrag.mode === 'move'){
            cropState.x = cropDrag.start.x + dx;
            cropState.y = cropDrag.start.y + dy;
        } else if(cropDrag.mode === 'image'){
            cropState.x = cropDrag.start.x + dx;
            cropState.y = cropDrag.start.y + dy;
        } else if(String(cropDrag.mode || '').startsWith('outpaint-')){
            resizeOutpaintFromDrag(dx, dy);
        } else {
            cropState.w = cropDrag.start.w + dx;
            cropState.h = cropDrag.start.h + dy;
        }
        clampCrop();
        renderCropBox();
        return;
    }
    if(smRoute === 'resizing'){
        const node = nodes.find(n => n.id === resizeState.id);
        if(!node) return;
        const dx = (e.clientX - resizeState.startX) / viewport.scale;
        const dy = (e.clientY - resizeState.startY) / viewport.scale;
        const minW = node.type === 'smart-prompt' ? 260 : node.type === 'smart-loop' ? 252 : 48;
        const minH = node.type === 'smart-prompt' ? 170 : node.type === 'smart-loop' ? 132 : 48;
        const lockAspect = node.type === 'smart-image' || !node.type;
        if(lockAspect){
            const scaleX = (resizeState.startW + dx) / Math.max(1, resizeState.startW);
            const scaleY = (resizeState.startH + dy) / Math.max(1, resizeState.startH);
            const rawScale = Math.max(scaleX, scaleY);
            const minScale = Math.max(minW / Math.max(1, resizeState.startW), minH / Math.max(1, resizeState.startH));
            const scale = Math.max(minScale, rawScale);
            node.w = Math.max(minW, Math.round(resizeState.startW * scale));
            node.h = Math.max(minH, Math.round(node.w / Math.max(0.01, resizeState.aspect || (resizeState.startW / Math.max(1, resizeState.startH)))));
        } else {
            node.w = Math.max(minW, Math.round(resizeState.startW + dx));
            node.h = Math.max(minH, Math.round(resizeState.startH + dy));
        }
        node.scale = 1;
        if(node.type === 'smart-image'){
            node.cardSize = {width:node.w, height:node.h};
            node.cardSizing = 'manual';
        }
        updateNodeElementDuringResize(node);
        return;
    }
    if(smRoute === 'thumb-drag'){
        const dx = e.clientX - thumbDragState.startX;
        const dy = e.clientY - thumbDragState.startY;
        const source = nodes.find(n => n.id === thumbDragState.nodeId);
        // A click on a thumbnail always arms this gesture. Use a deliberate drag
        // distance so small hand jitter does not split an image out of its group.
        if(!thumbDragState.detached && Math.hypot(dx, dy) > 12){
            if(source && (source.images || []).length > 1){
                const img = source.images[thumbDragState.imgIndex];
                if(img){
                    commitPendingUndo();
                    undoSuppressed = true;
                    applyNodeMetaToImage(img, source);
                    source.images.splice(thumbDragState.imgIndex, 1);
                    if(source.images.length <= 1){
                        source.title = 'Image';
                        delete source.w; delete source.h;
                        inheritNodeMetaFromImage(source);
                    }
                    const point = screenToWorld(e);
                    canvasUiState.patchSelection({primaryId: ''}, 'selectedId');
                    canvasUiState.patchSelection({image: {nodeId:'', index:-1}}, 'selectedImage');
                    const newNode = createImageNodeAt(point, [img], {select:false, skipUndo:true});
                    undoSuppressed = false;
                    dragState = {id:newNode.id, startX:e.clientX, startY:e.clientY, ox:newNode.x, oy:newNode.y, thumbDetached:true};
                    if (typeof CanvasInteractionMachine !== 'undefined') { CanvasInteractionMachine.end('thumb-drag'); CanvasInteractionMachine.begin('dragging-node'); }
                    thumbDragState.detached = true;
                    render();
                }
            }
        }
        if(thumbDragState.detached){ thumbDragState = null; smRoute = smChainModeProbe(); }
        else return;
    }
    if(smRoute === 'input-thumb-drag'){
        const dx = e.clientX - inputThumbDragState.startX;
        const dy = e.clientY - inputThumbDragState.startY;
        if(!inputThumbDragState.active && Math.abs(dx) + Math.abs(dy) > 6){
            inputThumbDragState.active = true;
        }
        if(inputThumbDragState.active){
            e.preventDefault();
            updateInputThumbDragVisual(e.clientX);
        }
        return;
    }
    if(smRoute === 'panning'){
        const dx = e.clientX - panState.startX;
        const dy = e.clientY - panState.startY;
        if(Math.abs(dx) + Math.abs(dy) > 3) smMarkPanSticky(true);
        viewport.x = panState.ox + dx;
        viewport.y = panState.oy + dy;
        scheduleViewportApply();
        return;
    }
    if(smRoute !== 'dragging-node') return;
    CanvasNodeGestureController.queueDragFrame(e);
};
window.onmouseup = e => {
    // 划断收尾放在最前：前面任何一步抛错都不会把手势卡在“一直划”的状态
    if(connectionCutState && e.button === 2){
        finishConnectionCutGesture();
        return;
    }
    CanvasNodeGestureController.flushDragFrame(e);
    document.body.classList.remove('smart-node-drag');
    document.body.classList.remove('smart-node-resize');
    if(portDragState){
        const drag = portDragState;
        portDragState = null;
        if (typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.end('connecting');
        shell.classList.remove('port-dragging');
        clearPortDragVisual();
        handlePortDrop(drag, e);
        return;
    }
    if(promptResizeState){ promptResizeState = null; scheduleSave(); if (typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.end('prompt-resize'); }
    if(selectionState && e.button === 0) finishSelection(e); // 只认左键松手（中键叠加不打残框选）
    if(previewCompareDrag){ previewCompareDrag = false; if (typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.end('preview-compare'); }
    if(panoramaState.drag){
        panoramaState.drag = null; if (typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.end('panorama-drag');
        document.getElementById('previewStage')?.classList.remove('panning');
    }
    if(previewPanDrag){
        previewPanDrag = null; if (typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.end('preview-pan');
        document.getElementById('previewStage')?.classList.remove('panning');
    }
    if(imageEditPanDrag){ imageEditPanDrag = null; if (typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.end('image-edit-pan'); }
    if(cropDrag){
        document.getElementById('cropCanvas')?.classList.remove('dragging-image');
        cropDrag = null; if (typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.end('crop-drag');
    }
    if(resizeState){
        const node = nodes.find(n => n.id === resizeState.id);
        const rect = node ? nodeRect(node) : null;
        const changed = rect && (Math.abs(rect.width - resizeState.startW) > 1 || Math.abs(rect.height - resizeState.startH) > 1);
        if(changed){
            commitPendingUndo();
        } else { discardPendingUndo(); }
        resizeState = null;
        if (typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.end('resizing');
        if(changed) render();
        scheduleSave();
    }
    if(thumbDragState){
        if(!thumbDragState.detached) discardPendingUndo();
        if(thumbDragState && !thumbDragState.detached && typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.end('thumb-drag');
        thumbDragState = null;
    }
    if(inputThumbDragState){
        const drag = inputThumbDragState;
        inputThumbDragState = null; if (typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.end('input-thumb-drag');
        clearInputThumbDragClasses();
        if(drag.active){
            const rawInsert = Number.isFinite(Number(drag.insertIndex)) ? Number(drag.insertIndex) : drag.from;
            let to = rawInsert;
            if(to > drag.from) to -= 1;
            if(drag.from !== to){
                const current = nodes.find(n => n.id === drag.nodeId);
                reorderInputThumb(current, drag.items || [], drag.from, Math.max(0, Math.min((drag.items || []).length - 1, to)));
                return;
            }
        }
    }
    if(panState && e.button === 1) { // 只认中键松手；防御链/watchdog 兜底丢事件
        panState = null;
        shell.classList.remove('panning');
        if (typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.end('panning');
        scheduleSave();
        setTimeout(() => { smMarkPanSticky(false); }, 0);
    }
    if(CanvasRenderScheduler.inMinimapDrag()){
        CanvasRenderScheduler.endMinimapDrag();
        if (typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.end('minimap-panning');
    }
    CanvasNodeGestureController.finishDrag(e);
};
shell.addEventListener('wheel', e => {
    if(e.__smartCanvasWheelHandled) return;
    if(isCanvasWheelExcludedTarget(e.target)){
        if(!isCanvasWheelScrollableOverlay(e.target)){
            e.preventDefault();
            e.stopPropagation();
            e.__smartCanvasWheelHandled = true;
            beginSmartCanvasScrollLock();
        }
        return;
    }
    // 2026-10-10 20:28（老王反馈：LLM 节点里滚轮翻不动提示词）：节点内的文本滚动区
    // （.prompt-node-text/.loop-smart-text/.smart-table-wrap/textarea/[contenteditable]）
    // 不在 wheel-exclude 里，会掉进下面的缩放分支——preventDefault 吃掉原生滚动，画布反而缩放。
    // 这里放行 wheel-scrollable 白名单，节点正文自己消化滚轮；滚到头也不链回画布缩放。
    if(isCanvasWheelScrollableOverlay(e.target)) return;
    e.preventDefault();
    e.stopPropagation();
    e.__smartCanvasWheelHandled = true;
    zoomViewportAtClientPoint(e);
    beginSmartCanvasScrollLock();
}, {passive:false, capture:true});
document.addEventListener('wheel', e => {
    if(handleImagePreviewWheel(e)) return;
    if(e.__smartCanvasWheelHandled) return;
    if(imageEditModal?.classList.contains('open')){
        if(e.target.closest?.('#imageEditStage')) return;
        e.preventDefault();
        e.stopPropagation();
        e.__smartCanvasWheelHandled = true;
        beginSmartCanvasScrollLock();
        return;
    }
    if(isCanvasWheelScrollableOverlay(e.target)) return;
    if(shell.contains(e.target)){
        e.preventDefault();
        e.stopPropagation();
        e.__smartCanvasWheelHandled = true;
        if(!isCanvasWheelExcludedTarget(e.target)) zoomViewportAtClientPoint(e);
    }
    beginSmartCanvasScrollLock();
}, {passive:false, capture:true});
window.addEventListener('scroll', lockSmartCanvasRootScroll, {passive:true, capture:true});
shell.ondragover = e => setSmartDropCopyEffect(e, true);
shell.ondrop = async e => {
    e.preventDefault();
    if(e.target.closest('.image-node')) return;
    const p = screenToWorld(e);
    const assetRaw = e.dataTransfer.getData('application/x-smart-asset');
    if(assetRaw){
        try {
            const asset = JSON.parse(assetRaw);
            if(asset?.url) {
                pushUndo();
                const imageRef = {url:asset.url, name:asset.name || 'asset', kind:asset.kind || assetMediaKind(asset)};
                if(asset.assetId){
                    imageRef.assetId = asset.assetId;
                    imageRef.assetVersionMode = asset.assetVersionMode === 'pinned' ? 'pinned' : 'latest';
                    if(asset.assetVersionId) imageRef.assetVersionId = asset.assetVersionId;
                }
                createImageNodeAt(p, [imageRef], {skipUndo:true});
            }
            return;
        } catch {}
    }
    const payload = await CanvasImageDropPayload.resolve(e.dataTransfer);
    if(payload.type === 'none') return;
    await handleSmartImageDropPayload(payload, '', {point:p, forceNew:true});
};
window.addEventListener('paste', e => {
    const files = [...(e.clipboardData?.files || [])].filter(isSupportedUploadFile);
    if(files.length){
        lastImagePasteAt = Date.now();
        handleFiles(files, canvasUiState.selection.primaryId);
        return;
    }
    if(CanvasNodeClipboardController.hasClipboardNodes() && !isEditableTarget(e.target)){
        e.preventDefault();
        pasteNodes();
    }
});
CanvasKeyboardShortcutController.bindCanvasHandlers();
function bindComposerSelectHoverGuard(){
  const composer = document.getElementById('composer');
  if(!composer || composer.__composerSelectGuard) return;
  composer.__composerSelectGuard = true;
  const setOpen = (on) => document.body.classList.toggle('composer-select-open', !!on);
  composer.addEventListener('focusin', e => { if(e.target && e.target.tagName === 'SELECT') setOpen(true); });
  composer.addEventListener('focusout', e => { if(e.target && e.target.tagName === 'SELECT') setOpen(false); });
  composer.addEventListener('click', e => { if(e.target && e.target.tagName === 'SELECT') setOpen(true); });
}
bindComposerSelectHoverGuard();
engineSelect.onchange = () => {
    settings.engine = engineSelect.value;
    applyRecentSmartSettingsForCurrentMode();
    syncApiKindToggleVisibility();
    renderDynamicParams();
    persistActiveSmartSettings();
    scheduleSave();
};
function syncApiKindToggleVisibility(){
    if(!apiKindToggle) return;
    // 2026-09-24：图片/视频切换推广到所有生成节点（3D预演在 blender 分支单独隐藏；
    // 文本/剧本节点不渲染 composer，天然无按钮）。RH/Comfy 切换工作流时自动跟随产出类型。
    // Comfy 的 composer-head、RH 的 composer-head-left 被布局 CSS 整列隐藏——
    // 这两引擎下把按钮搬进参数控制列（dynamicParams 首行），其余引擎留在原位。
    if(settings.engine === 'blender'){
        apiKindToggle.style.display = 'none';   // 3D预演无图片/视频切换
        return;
    }
    const relocate = settings.engine === 'comfy' || settings.engine === 'runninghub';
    if(relocate){
        const holder = document.getElementById('dynamicParams');
        const host = holder?.querySelector('.cfn-controls') || holder?.querySelector('.param-controls-row') || holder;
        if(host && apiKindToggle.parentElement !== host) host.insertBefore(apiKindToggle, host.firstChild);
    } else {
        const headLeft = document.querySelector('.composer-head-left');
        if(headLeft && !headLeft.contains(apiKindToggle)) headLeft.appendChild(apiKindToggle);
    }
    apiKindToggle.style.display = 'inline-flex';
    apiKindToggle.querySelectorAll('[data-kind]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.kind === (settings.apiKind || 'image'));
        const kindLabel = tr(btn.dataset.kind === 'video' ? 'smart.kindVideo' : 'smart.kindImage');
        const workflowDetected = ['runninghub', 'comfy'].includes(String(settings.engine || '').toLowerCase());
        const modeHint = tr(workflowDetected ? 'smart.kindAutoHint' : 'smart.kindManualHint');
        btn.title = [kindLabel, modeHint].filter(Boolean).join(' · ');
    });
}
// 2026-09-25 老王：风格/参考模式槽不再留在运行键旁，统一搬进参数排末位
// （切换钮→模型→参数→参考模式→风格，运行键单独钉右）。
function relocateComposerSlotsToParamRow(){
    const holder = document.getElementById('dynamicParams');
    if(!holder) return;
    const host = holder.querySelector('.cfn-controls') || holder.querySelector('.param-controls-row') || holder;
    if(!host) return;
    ['.composer-reference-mode-slot', '.composer-style-mode-slot'].forEach(sel => {
        // id 优先（静态 HTML），class 兜底（运行时重建的 composer 可能只带 class）
        const slot = document.getElementById(sel.slice(1)) || document.querySelector('#composer ' + sel + ':not(#dynamicParams ' + sel + ')');
        if(slot && slot.parentElement !== host) host.appendChild(slot);
    });
}
if(apiKindToggle){
    apiKindToggle.querySelectorAll('[data-kind]').forEach(btn => {
        btn.onclick = e => {
            e.preventDefault();
            e.stopPropagation();
            const kind = btn.dataset.kind;
            if(kind === settings.apiKind) return;
            settings.apiKind = kind;
            applyRecentSmartSettingsForCurrentMode();
            // recent 快照可能带旧 apiKind，回灌后必须重写（RH/Comfy 模式尤其）
            settings.apiKind = kind;
            syncApiKindToggleVisibility();
            applyKindAutoPick();
            renderDynamicParams();
            renderInputThumbsRow(selectedNode());
            persistActiveSmartSettings();
            scheduleSave();
        };
    });
}
let promptResizeState = null;
const promptResize = document.getElementById('promptResize');
if(promptResize){
    promptResize.addEventListener('mousedown', e => {
        if(e.button !== 0) return;
        e.preventDefault(); e.stopPropagation();
        promptResizeState = {
            startY: e.clientY,
            startH: Number(settings.promptH) || promptInput.offsetHeight || 93
        };
        if (typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.begin('prompt-resize');
    });
}
runBtn.onclick = async function(ev){
    const sel = selectedNode();
    // 选中节点正在 ComfyUI 运行 → 按钮变身"停止"，调用 cancel
    if(sel && sel.comfyStatus === 'running' && sel.comfyJobId){
        if(ev && typeof ev.preventDefault === 'function') ev.preventDefault();
        if(ev && typeof ev.stopImmediatePropagation === 'function') ev.stopImmediatePropagation();
        await cancelComfyJob(sel);
        return;
    }
    return runGeneration();
};
if(cascadeRunBtn){
    cascadeRunBtn.onclick = () => {
        const node = selectedNode();
        const loopId = resolveSmartCascadeLoop(node?.id)?.node?.id || '';
        if(loopId && smartCascadeIsLoopRunning(loopId)) {
            requestSmartCascadeStop(loopId);
            return;
        }
        runSmartCascade();
    };
}
fileInput.onchange = () => {
    const groupPoint = pendingGroupUploadPoint;
    if(!fileInput.files?.length){
        pendingGroupUploadPoint = null;
        uploadTargetId = '';
        return;
    }
    const targetId = groupPoint ? '' : (uploadTargetId || canvasUiState.selection.primaryId);
    handleFiles(fileInput.files, targetId, groupPoint ? {point:groupPoint} : {});
    pendingGroupUploadPoint = null;
    uploadTargetId = '';
    fileInput.value = '';
};
setMinimapOpen(CanvasRenderScheduler.isMinimapOpen());
if(canvasAddToggle) canvasAddToggle.onclick = e => {
    e.preventDefault();
    e.stopPropagation();
    if(createMenu?.classList?.contains('open')) closeCreateMenu();
    else openCreateMenuFromDock();
};
if(minimapToggle) minimapToggle.onclick = e => {
    e.preventDefault();
    e.stopPropagation();
    setMinimapOpen(!CanvasRenderScheduler.isMinimapOpen());
};
if(assetToggle) assetToggle.onclick = () => toggleAssetLibrary();
if(assetCloseBtn) assetCloseBtn.onclick = () => toggleAssetLibrary(false);
if(styleToggle) styleToggle.onclick = () => toggleStylePanel();
if(styleCloseBtn) styleCloseBtn.onclick = () => toggleStylePanel(false);
bindStylePanel();
setSnapEnabled(snapEnabled, {silent:true});
syncComposerAdaptiveUi();
setCanvasAgentOpen(false);
installCanvasAgentToggleDrag();
renderCanvasAgentRefs();
renderCanvasAgentMessages();
refreshCanvasAgentConfig().catch(() => {});
loadCanvasAgentHistoryList().then(() => renderCanvasAgentHistory()).catch(() => {});
 if(initialAgentSessionId){
 loadCanvasAgentHistoryList().then(() => loadCanvasAgentSession(initialAgentSessionId)).catch(() => {});
 }
canvasAgentToggle?.addEventListener('click', e => {
 e.preventDefault();
 e.stopPropagation();
 if(Date.now() < canvasAgentToggleSuppressClickUntil) return;
 setCanvasAgentOpen(true);
});
document.getElementById('canvasAgentTitleBtn')?.addEventListener('click', e => {
    e.preventDefault();
    e.stopPropagation();
    toggleCanvasAgentHistory();
});
document.getElementById('canvasAgentSkillToggle')?.addEventListener('click', e => {
    e.preventDefault();
    e.stopPropagation();
    if(CanvasAgentSkillManager.isOpen()) CanvasAgentSkillManager.close();
    else CanvasAgentSkillManager.open();
});
document.getElementById('canvasAgentSkillClose')?.addEventListener('click', e => {
    e.preventDefault();
    e.stopPropagation();
    CanvasAgentSkillManager.close();
});
document.getElementById('canvasAgentSkillNew')?.addEventListener('click', e => {
    e.preventDefault();
    e.stopPropagation();
    CanvasAgentSkillManager.openEditor('');
});
document.getElementById('canvasAgentSkillCancel')?.addEventListener('click', e => {
    e.preventDefault();
    e.stopPropagation();
    CanvasAgentSkillManager.cancelEditor();
});
document.getElementById('canvasAgentSkillSave')?.addEventListener('click', e => {
    e.preventDefault();
    e.stopPropagation();
    CanvasAgentSkillManager.saveFromEditor().catch(err => toast(err.message || '保存技能失败'));
});
document.getElementById('canvasAgentSkillDelete')?.addEventListener('click', e => {
    e.preventDefault();
    e.stopPropagation();
    CanvasAgentSkillManager.deleteFromEditor().catch(err => toast(err.message || '删除技能失败'));
});
canvasAgentClose?.addEventListener('click', e => {
    e.preventDefault();
    e.stopPropagation();
    closeCanvasAgentHistory();
    setCanvasAgentOpen(false);
});
canvasAgentAttach?.addEventListener('click', e => {
    e.preventDefault();
    e.stopPropagation();
    attachSelectedResourcesToCanvasAgent();
});
canvasAgentUpload?.addEventListener('click', e => {
    e.preventDefault();
    e.stopPropagation();
    canvasAgentFileInput?.click();
});
canvasAgentFileInput?.addEventListener('change', e => {
    e.preventDefault();
    uploadCanvasAgentFiles(e.target?.files);
});
canvasAgentSend?.addEventListener('click', e => {
    e.preventDefault();
    e.stopPropagation();
    if(canvasAgentSending) stopCanvasAgentGeneration();
    else sendCanvasAgentMessage();
});
canvasAgentSettings?.addEventListener('click', e => {
    e.preventDefault();
    e.stopPropagation();
    toggleCanvasAgentSettings(undefined, 'agent');
});
document.getElementById('canvasAgentGenSettings')?.addEventListener('click', e => {
    e.preventDefault();
    e.stopPropagation();
    toggleCanvasAgentSettings(undefined, 'gen');
});
document.getElementById('canvasAgentSettingsClose')?.addEventListener('click', e => {
    e.preventDefault();
    e.stopPropagation();
    toggleCanvasAgentSettings(false);
});
document.getElementById('canvasAgentSettingsSave')?.addEventListener('click', e => {
    e.preventDefault();
    e.stopPropagation();
    const collected = collectCanvasAgentSettings();
    if(collected){
        canvasAgentModelPreset = {...collected, agentId:canvasAgentActiveId};
        canvasAgentSavePreset();
        // 把选择的 LLM 平台和模型写入 Agent 配置（app_config），画布对话直接生效。
        const pid = String(collected.chatProviderId || '').trim();
        const chatModel = String(collected.chatModel || '').trim();
        if(pid){
            const aid = canvasAgentActiveId || 'codex';
            fetch(`${RH_OFFICIAL_PROXY_BASE}/app-config`, {
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({agent:{active_id:aid, agents:{[aid]:{provider_id:pid, model:chatModel}}}})
            }).then(() => refreshCanvasAgentConfig()).catch(() => {});
        }
    }
    toggleCanvasAgentSettings(false);
    toast('模型设置已保存');
});
document.getElementById('canvasAgentTestChat')?.addEventListener('click', async e => {
    e.preventDefault();
    e.stopPropagation();
    const btn = e.currentTarget;
    const pid = String(document.getElementById('canvasAgentSelect')?.value || '').trim();
    const model = String(document.getElementById('canvasAgentChatModel')?.value || '').trim();
    if(!pid){ toast('请先选择 LLM平台'); return; }
    if(!model){ toast('请先选择模型'); return; }
    const oldText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '测试中…';
    btn.classList.remove('is-ok', 'is-err');
    try {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 45000);
        const res = await fetch(`${RH_OFFICIAL_PROXY_BASE}/api/canvas-llm`, {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            signal:controller.signal,
            body:JSON.stringify({agent_id:canvasAgentActiveId || 'codex', provider:pid, model, message:'请只回复 ok，用于测试对话连接。'})
        });
        clearTimeout(timer);
        const data = await res.json().catch(() => ({}));
        if(!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
        const text = String(data.text || '').trim() || '已收到回复';
        btn.classList.add('is-ok');
        btn.textContent = '测试通过';
        toast(`对话测试通过：${text.slice(0, 40)}`);
    } catch(err){
        const msg = err?.name === 'AbortError' ? '上游模型请求超时(45s)' : (err?.message || err);
        btn.classList.add('is-err');
        btn.textContent = '测试失败';
        toast(`对话测试失败：${msg}`);
    } finally {
        btn.disabled = false;
        setTimeout(() => { btn.textContent = oldText; btn.classList.remove('is-ok', 'is-err'); }, 4000);
    }
});
document.getElementById('canvasAgentSelect')?.addEventListener('change', e => {
    e.stopPropagation();
    const pid = String(e.target.value || '').trim();
    const provider = canvasAgentLlmProviders().find(p => p.id === pid);
    const modelSel = document.getElementById('canvasAgentChatModel');
    if(modelSel && provider){
        const entry = canvasAgentActiveEntry() || {};
        const keep = String(entry.model || '').trim();
        const models = [...new Set(provider.chat_models || [])].filter(Boolean);
        const picked = (keep && models.includes(keep)) ? keep : (models[0] || keep || '');
        modelSel.innerHTML = models.length
            ? models.map(m => `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`).join('')
            : `<option value="${escapeHtml(picked)}">${escapeHtml(picked || '该平台暂无模型')}</option>`;
        if(picked) modelSel.value = picked;
    }
});
document.getElementById('canvasAgentChatProvider')?.addEventListener('change', e => {
    e.stopPropagation();
    const modelSel = document.getElementById('canvasAgentChatModel');
    if(modelSel){
        const models = canvasAgentChatModelsFor(e.target.value);
        modelSel.innerHTML = models.map(m => `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`).join('');
    }
});
document.getElementById('canvasAgentGenProvider')?.addEventListener('change', e => {
    e.stopPropagation();
    const modelSel = document.getElementById('canvasAgentGenModel');
    if(modelSel){
        const models = canvasAgentGenModelsFor(e.target.value);
        modelSel.innerHTML = models.map(m => `<option value="${escapeHtml(m)}">${escapeHtml(canvasAgentGenModelLabel(m, e.target.value))}</option>`).join('');
    }
});
/* 2026-10-08（老王："生图预设-图生图，选择平台后，后面的模型没有跟着变，要把窗口关闭再打开才换过来"）
   上面 canvasAgentGenProvider（文生图）绑了「平台 → 模型」联动，图生图这一组
   （canvasAgentGen2Provider / canvasAgentGen2Model）却漏绑了：换平台后模型下拉不动，
   必须把设置窗口关掉重开（走 renderCanvasAgentSettingsPanel 重新渲染）才刷新。
   这里补一份与文生图完全对称的绑定。
   能生效的原因：自定义下拉 enhanceAgentSelects 点选项时会执行
   `sel.dispatchEvent(new Event('change',{bubbles:true}))`，原生监听收得到。 */
document.getElementById('canvasAgentGen2Provider')?.addEventListener('change', e => {
    e.stopPropagation();
    const modelSel = document.getElementById('canvasAgentGen2Model');
    if(modelSel){
        const models = canvasAgentGenModelsFor(e.target.value);
        modelSel.innerHTML = models.map(m => `<option value="${escapeHtml(m)}">${escapeHtml(canvasAgentGenModelLabel(m, e.target.value))}</option>`).join('');
    }
});
CanvasAgentMentionController.bindInputEvents();
canvasAgentPanel?.addEventListener('pointerdown', e => e.stopPropagation());
canvasAgentPanel?.addEventListener('mousedown', e => e.stopPropagation());
canvasAgentPanel?.addEventListener('dragstart', e => {
 if(e.target.closest?.('.canvas-agent-avatar,.canvas-agent-avatar-img')){
  e.preventDefault();
  e.stopPropagation();
 }
});
canvasAgentPanel?.addEventListener('click', e => {
 e.stopPropagation();
 if(!e.target.closest('#canvasAgentHistoryPanel,#canvasAgentTitleBtn')) closeCanvasAgentHistory();
});
canvasAgentPanel?.addEventListener('wheel', e => {
    const scroller = e.target.closest?.('.canvas-agent-messages') || canvasAgentMessages;
    if(scroller && scroller.scrollHeight > scroller.clientHeight) e.stopPropagation();
}, {passive:true});
canvasAgentPanel?.addEventListener('dragover', e => {
    e.preventDefault();
    e.stopPropagation();
    canvasAgentPanel.classList.add('drag-over');
});
canvasAgentPanel?.addEventListener('dragleave', e => {
    if(!canvasAgentPanel.contains(e.relatedTarget)) canvasAgentPanel.classList.remove('drag-over');
});
canvasAgentPanel?.addEventListener('drop', e => {
    e.preventDefault();
    e.stopPropagation();
    canvasAgentPanel.classList.remove('drag-over');
    const raw = e.dataTransfer?.getData('application/x-smart-canvas-image') || e.dataTransfer?.getData('application/x-smart-asset') || '';
    if(raw){
        try {
            const item = JSON.parse(raw);
            const ref = canvasAgentRefFromImage(item, nodes.find(n => n.id === item.nodeId), Number(item.imageIndex || 0));
            if(ref) addCanvasAgentRefs([ref]);
        } catch(_) {}
    }
});
assetPanel?.addEventListener('pointerdown', e => e.stopPropagation());
assetPanel?.addEventListener('mousedown', e => e.stopPropagation());
assetPanel?.addEventListener('click', e => e.stopPropagation());
assetPanel?.addEventListener('wheel', e => {
    e.stopPropagation();
    const scroller = e.target.closest?.('.asset-grid') || assetGrid;
    if(!scroller || getComputedStyle(scroller).display === 'none') return;
    const canScroll = scroller.scrollHeight > scroller.clientHeight || scroller.scrollWidth > scroller.clientWidth;
    if(!canScroll) return;
    e.preventDefault();
    scroller.scrollTop += e.deltaY;
    scroller.scrollLeft += e.deltaX;
}, {passive:false, capture:true});
assetDialogBackdrop?.addEventListener('pointerdown', e => e.stopPropagation());
assetDialogBackdrop?.addEventListener('mousedown', e => e.stopPropagation());
assetDialogBackdrop?.addEventListener('click', e => e.stopPropagation());
document.querySelectorAll('[data-asset-tab]').forEach(btn => {
    btn.onclick = () => { assetTab = btn.dataset.assetTab; renderAssetLibrary(); };
});
if(assetLibrarySelect) assetLibrarySelect.onchange = () => {
    activeAssetLibraryId = assetLibrarySelect.value || '';
    activeAssetCategoryId = '';
    mentionAssetCategoryId = '';
    renderAssetLibrary();
};
if(assetCategorySelect) assetCategorySelect.onchange = () => { activeAssetCategoryId = assetCategorySelect.value; renderAssetLibrary(); };
const assetAddCategoryBtn = document.getElementById('assetAddCategoryBtn');
if(assetAddCategoryBtn) assetAddCategoryBtn.onclick = async () => {
    const name = await openAssetNameDialog({title:tr('smart.assetNewFolder'), value:tr('smart.assetFolder'), placeholder:tr('smart.assetFolder')});
    if(!name) return;
    const data = await fetch('/api/asset-library/categories', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({library_id:activeAssetLibraryId, name, type:'image'})}).then(r => r.json());
    activeAssetCategoryId = data.category?.id || activeAssetCategoryId;
    setAssetLibraryFromResponse(data);
};
const assetRenameCategoryBtn = document.getElementById('assetRenameCategoryBtn');
if(assetRenameCategoryBtn) assetRenameCategoryBtn.onclick = async () => {
    const cat = activeAssetCategory();
    if(!cat) return;
    const name = await openAssetNameDialog({title:tr('smart.assetRenameFolder'), value:cat.name || '', placeholder:tr('smart.assetFolder')});
    if(!name) return;
    const data = await fetch(`/api/asset-library/categories/${encodeURIComponent(cat.id)}`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name})}).then(r => r.json());
    setAssetLibraryFromResponse(data);
};
CanvasAssetPanelDropController.configure({
    getDropZone: () => assetDropZone,
    getPanel: () => assetPanel,
    dataTypes: dataTransfer => CanvasImageDropPayload.dataTypes(dataTransfer),
    hasImageData: dataTransfer => CanvasImageDropPayload.hasImageData(dataTransfer),
    resolvePayload: dataTransfer => CanvasImageDropPayload.resolve(dataTransfer),
    imageNameFromUrl: url => CanvasImageDropPayload.imageNameFromUrl(url),
    uploadFiles: files => CanvasImageImportController.uploadFiles(files),
    addUrlToAssetLibrary: (...args) => addUrlToAssetLibrary(...args),
    toast: message => toast(message),
    assetAddFailMessage: () => tr('smart.assetAddFail')
});
CanvasAssetPanelDropController.bind();
createMenu?.addEventListener('mousedown', event => event.stopPropagation());
createMenu?.addEventListener('click', event => {
    event.stopPropagation();
    const card = event.target.closest('[data-create-type]');
    if(!card) return;
    // 灰化的卡（当前连线方向接不上）点了不建节点，只提示原因
    if(card.classList.contains('is-disabled')){
        toast(card.dataset.disabledReason || tr('smart.portDropConnectFailed'));
        return;
    }
    createNodeFromMenu(card.dataset.createType || 'image');
});

composer.addEventListener('pointerdown', event => event.stopPropagation());
composer.addEventListener('mousedown', event => event.stopPropagation());
composer.addEventListener('click', event => {
    if(!event.target.closest('.smart-control')) closeAllSmartPopovers();
    event.stopPropagation();
});
promptInput.addEventListener('input', maybeOpenMentionPicker);
promptInput.addEventListener('input', () => { if(typeof CanvasPromptLibPicker !== 'undefined') CanvasPromptLibPicker.handleInput(); });
promptInput.addEventListener('input', () => {
    refreshPromptPlaceholderVisible();
    delete promptInput.dataset.preserveDraftOnce;
    savePromptDraftForCurrent();
    renderInputThumbsRow(selectedNode());
    syncComfyInputsRow();
    scheduleSave();
});
promptInput.addEventListener('keyup', maybeOpenMentionPicker);
promptInput.addEventListener('mouseup', saveMentionRange);
promptInput.addEventListener('focus', saveMentionRange);
promptInput.addEventListener('keydown', event => {
    // ~ 快捷调出提示词库（本帧不交给 mention/生成链，先由面板消费导航键）
    if(typeof CanvasPromptLibPicker !== 'undefined'){
        if(CanvasPromptLibPicker.isOpen()){
            if(CanvasPromptLibPicker.handleKeydown(event)){ event.preventDefault(); event.stopPropagation(); return; }
        } else if(event.key === '~' && !event.ctrlKey && !event.metaKey && !event.altKey){
            event.preventDefault();
            document.execCommand('insertText', false, '~');
            CanvasPromptLibPicker.open();
            return;
        }
    }
    if((event.key === 'Backspace' || event.key === 'Delete') && !event.shiftKey && !event.ctrlKey && !event.metaKey && !event.altKey){
        const direction = event.key === 'Backspace' ? 'backward' : 'forward';
        const token = mentionImageTokenAdjacentToCaret(direction);
        if(token){
            event.preventDefault();
            event.stopPropagation();
            removePromptImageMention(token);
            return;
        }
    }
    if(event.key === 'Escape') closeMentionPicker();
});
promptInput.addEventListener('click', event => {
    const removeButton = event.target.closest?.('.mention-image-token-remove');
    if(!removeButton) return;
    event.preventDefault();
    event.stopPropagation();
    removePromptImageMention(removeButton.closest('.mention-image-token'));
});
promptInput.addEventListener('mouseover', event => {
    const token = event.target.closest?.('.mention-image-token');
    if(!token) return;
    let media = mentionPreview.querySelector('img,video');
    const isVideo = token.dataset.kind === 'video' || isVideoMediaItem({url:token.dataset.url, kind:token.dataset.kind});
    if(isVideo && media?.tagName?.toLowerCase() !== 'video'){
        media?.replaceWith(document.createElement('video'));
        media = mentionPreview.querySelector('video');
    } else if(!isVideo && media?.tagName?.toLowerCase() !== 'img'){
        media?.replaceWith(document.createElement('img'));
        media = mentionPreview.querySelector('img');
    }
    if(isVideo){
        media.muted = true;
        media.loop = true;
        media.playsInline = true;
        media.preload = 'metadata';
        media.disablePictureInPicture = true;
        media.setAttribute('disablepictureinpicture', '');
        media.setAttribute('controlslist', 'nodownload noplaybackrate noremoteplayback');
        media.src = token.dataset.url || '';
        media.play?.().catch(() => {});
    } else {
        media.src = token.dataset.url || '';
        media.alt = 'preview';
    }
    const rect = token.getBoundingClientRect();
    mentionPreview.style.left = `${Math.min(window.innerWidth - 236, rect.left)}px`;
    mentionPreview.style.top = `${Math.min(window.innerHeight - 236, rect.bottom + 8)}px`;
    mentionPreview.style.display = 'block';
});
promptInput.addEventListener('mouseout', event => {
    if(event.target.closest?.('.mention-image-token')){
        mentionPreview.style.display = 'none';
        const media = mentionPreview.querySelector('img,video');
        media?.pause?.();
        media?.removeAttribute('src');
        media?.load?.();
    }
});
mentionPicker.addEventListener('mousedown', event => event.stopPropagation());
document.addEventListener('click', event => {
    if(!event.target.closest('.smart-control')) closeAllSmartPopovers();
    if(!event.target.closest('.loop-number-control')) document.querySelectorAll('.loop-number-control.pinned').forEach(c => c.classList.remove('pinned'));
    if(!event.target.closest('.mention-picker') && !event.target.closest('#promptInput')) closeMentionPicker();
    if(typeof CanvasPromptLibPicker !== 'undefined' && CanvasPromptLibPicker.isOpen() && !event.target.closest('.prompt-lib-picker') && !event.target.closest('#promptInput')) CanvasPromptLibPicker.close();
    if(!event.target.closest('.prompt-preset-panel') && !event.target.closest('.prompt-preset-edit') && !event.target.closest('.prompt-preset-save')) closePromptPresetPanel();
    if(!event.target.closest('.prompt-template-panel') && !event.target.closest('.prompt-preset-edit') && !event.target.closest('#composerTemplateBtn')) closePromptTemplatePanel();
});
CanvasKeyboardShortcutController.bindGlobalEscapeHandler();
document.getElementById('cropBox').addEventListener('mousedown', event => beginCropDrag(event, 'move'));
document.getElementById('cropHandle').addEventListener('mousedown', event => beginCropDrag(event, 'resize'));
document.getElementById('outpaintFrame').addEventListener('mousedown', event => {
    if(event.target.closest('[data-outpaint-handle]')) return;
    beginCropDrag(event, 'image');
});
document.querySelectorAll('[data-outpaint-handle]').forEach(handle => {
    handle.addEventListener('mousedown', event => beginCropDrag(event, `outpaint-${handle.dataset.outpaintHandle || 'corner'}`));
});
document.getElementById('cropImage').addEventListener('mousedown', event => {
    if(imageEditMode !== 'outpaint' || !cropState) return;
    document.getElementById('cropCanvas')?.classList.add('dragging-image');
    beginCropDrag(event, 'image');
});
document.querySelectorAll('[data-image-edit-mode]').forEach(btn => {
    btn.addEventListener('click', event => {
        event.stopPropagation();
        setImageEditMode(btn.dataset.imageEditMode || 'crop', true);
    });
});
imageEditModal.addEventListener('pointerdown', event => {
    event.stopPropagation();
});
imageEditModal.addEventListener('mousedown', event => {
    event.stopPropagation();
});
imageEditModal.addEventListener('mousemove', event => {
    if(previewPanDrag || previewCompareDrag || panoramaState.drag || imageEditPanDrag || cropDrag) return;
    event.stopPropagation();
});
imageEditModal.addEventListener('click', event => {
    event.stopPropagation();
    if(event.target === imageEditModal) closeImageEditor();
});
imageEditModal.addEventListener('wheel', event => {
    if(handleImagePreviewWheel(event)) return;
    if(event.target.closest?.('#imageEditStage')) return;
    event.preventDefault();
    event.stopPropagation();
    lockSmartCanvasRootScroll();
}, {passive:false});
document.getElementById('previewStage').addEventListener('mousedown', event => {
    if(imageEditMode !== 'preview' || event.button !== 0) return;
    if(event.target.closest('.preview-tools-overlay, .preview-download-overlay')) return;
    if(event.target.closest('.preview-compare-handle')) return;
    if(event.target.closest('video')) return;
    event.preventDefault();
    event.stopPropagation();
    if(panoramaState.enabled){
        panoramaState.drag = {
            clientX:event.clientX,
            clientY:event.clientY,
            yaw:panoramaState.yaw,
            pitch:panoramaState.pitch
        };
        if (typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.begin('panorama-drag');
        document.getElementById('previewStage')?.classList.add('panning');
        return;
    }
    previewPanDrag = {clientX:event.clientX, clientY:event.clientY, startX:previewTransformState.pan.x, startY:previewTransformState.pan.y};
    if (typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.begin('preview-pan');
});
document.getElementById('imageEditStage').addEventListener('mousedown', event => {
    if(imageEditMode === 'preview' || event.button !== 0) return;
    if(event.target.closest('.image-edit-actions, .preview-tools-overlay, .preview-download-overlay, .crop-box, .crop-handle')) return;
    if(event.target.closest('#editDrawCanvas, #editTextCanvas, .edit-text-inline') && imageEditMode !== 'crop') return;
    const stage = event.currentTarget;
    if(stage.scrollWidth <= stage.clientWidth && stage.scrollHeight <= stage.clientHeight) return;
    event.preventDefault();
    event.stopPropagation();
    imageEditPanDrag = {
        clientX:event.clientX,
        clientY:event.clientY,
        scrollLeft:stage.scrollLeft,
        scrollTop:stage.scrollTop
    };
    if (typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.begin('image-edit-pan');
});
document.getElementById('previewCompareHandle').addEventListener('mousedown', event => {
    if(imageEditMode !== 'preview' || !previewCompareState.active || previewCompareState.index < 0) return;
    event.preventDefault();
    event.stopPropagation();
    previewPanDrag = null;
    previewCompareDrag = true;
    if (typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.begin('preview-compare');
    setPreviewComparePos(event.clientX);
});
document.getElementById('previewCompareHandle').addEventListener('pointerdown', event => {
    if(imageEditMode !== 'preview' || !previewCompareState.active || previewCompareState.index < 0) return;
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    previewPanDrag = null;
    previewCompareDrag = true;
    if (typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.begin('preview-compare');
    setPreviewComparePos(event.clientX);
});
document.getElementById('previewCompareHandle').addEventListener('pointermove', event => {
    if(!previewCompareDrag) return;
    event.preventDefault();
    event.stopPropagation();
    setPreviewComparePos(event.clientX);
});
document.getElementById('previewCompareHandle').addEventListener('pointerup', event => {
    if(previewCompareDrag){
        event.preventDefault();
        event.stopPropagation();
    }
    previewCompareDrag = false;
    if (typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.end('preview-compare');
    event.currentTarget.releasePointerCapture?.(event.pointerId);
});
document.getElementById('previewCompareHandle').addEventListener('pointercancel', event => {
    previewCompareDrag = false;
    if (typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.end('preview-compare');
    event.currentTarget.releasePointerCapture?.(event.pointerId);
});
bindPreviewWheelListeners();
document.getElementById('editDrawCanvas').addEventListener('pointerdown', beginEditDraw);
document.getElementById('editDrawCanvas').addEventListener('pointermove', moveEditDraw);
document.getElementById('editDrawCanvas').addEventListener('pointerup', endEditDraw);
document.getElementById('editDrawCanvas').addEventListener('pointercancel', endEditDraw);
document.getElementById('editDrawCanvas').addEventListener('pointerleave', endEditDraw);
document.getElementById('editTextCanvas')?.addEventListener('pointerdown', beginEditText);
document.getElementById('editTextCanvas')?.addEventListener('pointermove', moveEditText);
document.getElementById('editTextCanvas')?.addEventListener('pointerup', endEditText);
document.getElementById('editTextCanvas')?.addEventListener('pointercancel', endEditText);
document.getElementById('editTextCanvas')?.addEventListener('pointerleave', endEditText);
document.getElementById('editTextCanvas')?.addEventListener('dblclick', event => {
    if(imageEditMode !== 'brush' || CanvasImageEditDrawingController.getTool() !== 'text') return;
    event.preventDefault(); event.stopPropagation();
    const hit = hitEditTextItem(editTextPoint(event));
    if(hit){
        setSelectedEditTextItem(hit.id);
        beginEditTextInline(hit);
    }
});
['paintBrushSize','paintBrushColor'].forEach(id => {
    const control = document.getElementById(id);
    if(!control) return;
    control.addEventListener('input', syncSelectedEditTextStyleFromBrush);
    control.addEventListener('change', () => CanvasImageEditTextController.markClean());
});
['gridHorizontalLines','gridVerticalLines','gridGapSize'].forEach(id => {
    document.getElementById(id).addEventListener('input', () => {
        syncGridGapValue();
        refreshGridSplitPreview();
    });
});
document.querySelectorAll('[data-panorama-ratio]').forEach(btn => {
    btn.addEventListener('click', event => {
        event.preventDefault();
        event.stopPropagation();
        applyPanoramaRatio(btn.dataset.panoramaRatio || 'wide');
    });
});
['panoramaRatioW','panoramaRatioH'].forEach(id => {
    document.getElementById(id)?.addEventListener('input', () => {
        panoramaState.ratio = 'custom';
        panoramaState.customW = Math.max(1, Math.min(999, Number(document.getElementById('panoramaRatioW')?.value || 16)));
        panoramaState.customH = Math.max(1, Math.min(999, Number(document.getElementById('panoramaRatioH')?.value || 9)));
        refreshPanoramaControls();
        resizePanoramaViewer();
    });
});
document.getElementById('imageEditStage').addEventListener('wheel', event => {
    if(handleImagePreviewWheel(event)) return;
    if(imageEditMode === 'preview') return;
    if(!cropState) return;
    event.preventDefault();
    event.stopPropagation();
    const stage = event.currentTarget;
    const oldZoom = CanvasImageEditViewportController.getZoom();
    const factor = event.deltaY < 0 ? 1.12 : 1 / 1.12;
    const nextZoom = CanvasImageEditViewportController.setZoom(Math.max(0.15, Math.min(6.0, oldZoom * factor)));
    const stageRect = stage.getBoundingClientRect();
    const mx = event.clientX - stageRect.left;
    const my = event.clientY - stageRect.top;
    const contentX = stage.scrollLeft + mx;
    const scale = nextZoom / oldZoom;
    const contentY = stage.scrollTop + my;
    applyImageEditZoom(scale);
    stage.scrollLeft = contentX * scale - mx;
    stage.scrollTop = contentY * scale - my;
}, {passive:false, capture:true});
window.addEventListener('resize', () => {
    const node = selectedNode();
    if(node && composer.classList.contains('open')) positionComposerForNode(node);
    if(cropState) syncImageEditOverflow();
    if(panoramaState.enabled) resizePanoramaViewer();
});
window.addEventListener('studio-theme-change', event => applyTheme(event.detail?.theme || 'dark'));
try {
    const apiChannel = new BroadcastChannel('studio-api');
    apiChannel.onmessage = async event => {
        if(event.data?.type === 'providers-changed' || event.data?.type === 'workflows-changed' || event.data?.type === 'comfy-instances-changed'){
            await refreshSmartConfigFromSettings();
        }
        if(event.data?.type === 'app-config-changed') refreshCanvasAgentConfig().catch(() => {});
        if(event.data?.type === 'asset_library_updated') handleAssetLibraryUpdatedMessage(event.data);
        if(event.data?.type === 'prompt_library_updated') handlePromptLibraryUpdatedMessage(event.data);
        if(event.data?.type === 'canvas_updated') handleCanvasUpdatedMessage(event.data);
        if(event.data?.type === 'canvas-renamed') handleCanvasRenamedMessage(event.data);
    };
} catch(e) {}
window.addEventListener('focus', () => {
    if(Date.now() - lastConfigRefreshAt > 1200) refreshSmartConfigFromSettings();
    recoverStuckComfyNodes();
});
window.addEventListener('message', event => {
    if(event.origin && event.origin !== location.origin) return;
    if(event.data?.type === 'studio-theme') applyTheme(event.data.theme || 'dark');
    if(event.data?.type === 'providers-changed' || event.data?.type === 'workflows-changed' || event.data?.type === 'comfy-instances-changed') refreshSmartConfigFromSettings();
    if(event.data?.type === 'app-config-changed') refreshCanvasAgentConfig().catch(() => {});
    if(event.data?.type === 'asset_library_updated') handleAssetLibraryUpdatedMessage(event.data);
    if(event.data?.type === 'prompt_library_updated') handlePromptLibraryUpdatedMessage(event.data);
    if(event.data?.type === 'canvas_updated') handleCanvasUpdatedMessage(event.data);
    if(event.data?.type === 'studio-lang' && window.StudioI18n) {
        window.StudioI18n.set(event.data.lang || 'zh');
    }
});
window.addEventListener('studio-lang-change', () => {
    renderDynamicParams();
    renderInputThumbsRow(selectedNode());
    renderAssetLibrary();
    if(document.getElementById('imageEditModal')?.classList.contains('open')){
        setImageEditMode(imageEditMode);
    }
    if(promptTemplatePanel?.classList?.contains('open')) renderPromptTemplatePanel();
    render();
});
window.onload = async () => {
    applyTheme(window.StudioTheme?.get?.() || 'dark');
    loadPromptPresets();
    loadPromptTemplateGroups();
    loadPromptTemplateOverrides();
    await loadPromptTemplates();
    if(window.StudioI18n) window.StudioI18n.apply();
    if(window.lucide) lucide.createIcons();
    connectAssetLibrarySyncSocket();
    await loadConfig();
    await loadAssetLibrary();
    await loadCanvas();
    refreshCanvasAgentConfig().catch(() => {});
    syncApiKindToggleVisibility();
    render();
    // Boot signal: window.onload only *starts* this async chain, so state injected
    // right after the load event races loadConfig/loadCanvas and gets overwritten.
    // Tests and automation wait for this flag instead.
    window.__smartCanvasBooted = true;
};


/* =====================================================================
   Phase 8 · Agent Artifact Sidebar
   ---------------------------------------------------------------------
   三层模型（不要混淆）：
     Execution State      -> Timeline Card
     Persistent Document  -> Sidebar Artifact
     Visual / Media       -> Canvas Node

   核心原则：
     Everything the Agent says != Artifact
     Every Artifact       != Canvas Node
   ===================================================================== */

let canvasAgentArtifactsState = [];
let canvasAgentActiveArtifactId = '';
let canvasAgentActiveSectionId = '';   // Phase 9：Conversation 内部选中的 Section
let canvasAgentActiveItemId = '';      // Phase 9：Section 内部选中的 Item

// 安全总开关：文档类默认进 Sidebar 而不是直接建 Canvas Node。
// 若线上出现误伤，改 false 即回退旧行为（文本仍建节点）。
const ARTIFACT_TEXT_DEFAULT_SIDEBAR = true;

const ARTIFACT_TYPE_META = {
    brainstorm:        {icon:'sparkles',        label:'Brainstorm'},
    markdown:          {icon:'file-text',       label:'Markdown'},
    document:          {icon:'file-text',       label:'Document'},
    script:            {icon:'film',            label:'Script'},
    brief:             {icon:'clipboard-list',  label:'Brief'},
    creative_brief:    {clipboard:1, icon:'clipboard-list', label:'Brief'},
    story_outline:     {icon:'list-tree',       label:'大纲'},
    story_bible:       {icon:'book-open',       label:'故事圣经'},
    character_bible:   {icon:'users',           label:'角色设定'},
    character_profile: {icon:'user',            label:'角色小传'},
    world_bible:       {icon:'globe',           label:'世界观'},
    world_setting:     {icon:'globe',           label:'世界观'},
    visual_direction:  {icon:'palette',         label:'视觉风格'},
    table:             {icon:'table',           label:'Table'},
    csv:               {icon:'table',           label:'CSV'},
    html:              {icon:'code',            label:'HTML'},
    interactive:       {icon:'monitor-play',    label:'Interactive'},
    deck:              {icon:'presentation',    label:'Deck'},
    presentation:      {icon:'presentation',    label:'Deck'},
    text:              {icon:'file-text',       label:'Text'},
    note:              {icon:'sticky-note',     label:'Note'},
    analysis:          {icon:'search',          label:'分析'},
    report:            {icon:'file-bar-chart',  label:'报告'}
};

// 默认路由策略（需求第四条/第五条/第四十九条）
const ARTIFACT_SIDEBAR_TYPES = new Set([
    'markdown','document','brief','creative_brief','script','story_outline','story_bible',
    'character_bible','character_profile','world_bible','world_setting','visual_direction',
    'brainstorm','table','csv','html','interactive','deck','presentation','text','note',
    'outline','analysis','report'
]);
const ARTIFACT_CANVAS_TYPES = new Set([
    'image','video','audio','generated_image','generated_video','generated_audio','media'
]);
// 显式用户意图（需求第三十二条：显式操作优先级最高）
const ARTIFACT_CANVAS_HINTS = ['放到画布','放到画布上','加入画布','加入canvas','创建成节点','建成节点','生成节点','加到画布','放到canvas'];
const ARTIFACT_SIDEBAR_HINTS = ['保存成文档','存成文档','保存为文件','存到文件','保存成文件','只要文档','不用建节点','不要建节点'];

function artifactTypeMeta(type){
    const key = String(type || 'text').trim().toLowerCase();
    return ARTIFACT_TYPE_META[key] || {icon:'file', label: key || 'text'};
}
function artifactIcon(type){ return artifactTypeMeta(type).icon; }
function artifactTypeLabel(type){ return artifactTypeMeta(type).label; }

/* ---------------------------------------------------------------
   Artifact Router（前端侧，与后端 route_artifact 同构）
   返回 'canvas' | 'sidebar' | 'both'
   绝不基于 LLM 的一句自然语言直接决定 createNode。
   --------------------------------------------------------------- */
function canvasAgentLatestUserText(){
    // Router 判断"显式用户意图"需要用户原话。不新增状态，直接从消息栈倒查最近一条 user。
    try{
        const list = canvasAgentMessagesState || [];
        for(let i = list.length - 1; i >= 0; i--){
            const m = list[i];
            if(m && m.role === 'user') return String(m.text || '');
        }
    }catch(e){}
    return '';
}
function routeArtifact(opts){
    const o = opts || {};
    const atype = String(o.artifactType || o.type || '').trim().toLowerCase();
    const arole = String(o.role || '').trim().toLowerCase();
    const tool  = String(o.toolName || '').trim().toLowerCase();
    const text  = String(o.userText || '');

    for(const hint of ARTIFACT_CANVAS_HINTS){
        if(text.indexOf(hint) >= 0) return 'both';
    }
    for(const hint of ARTIFACT_SIDEBAR_HINTS){
        if(text.indexOf(hint) >= 0) return 'sidebar';
    }
    if(tool === 'canvas_create_text_node'){
        return ARTIFACT_TEXT_DEFAULT_SIDEBAR ? 'sidebar' : 'canvas';
    }
    if(tool === 'canvas_create_generation_node' || tool === 'canvas_generate_images') return 'canvas';
    if(ARTIFACT_CANVAS_TYPES.has(atype) || arole === 'media' || arole === 'generation' || arole === 'output') return 'canvas';
    if(ARTIFACT_SIDEBAR_TYPES.has(atype) || arole === 'text' || arole === 'container') return 'sidebar';
    return 'canvas';
}

/* ---------------------------------------------------------------
   Store：upsert 去重（需求第二十二/二十三条）
   同一 artifactId -> update，不 append duplicate。
   --------------------------------------------------------------- */
function findArtifact(id){
    return CanvasArtifactModel.findArtifact(id);
}
function artifactUpsert(next){
    return CanvasArtifactModel.artifactUpsert(next);
}

/* 保存一个 Valid Artifact 到 Sidebar（需求第三十条：只接受 Valid Artifact，
   Thinking/Plan/Tool/Progress/Error/普通消息 永不进入） */
function saveArtifactToSidebar(opts){
    return CanvasArtifactModel.saveArtifactToSidebar(opts);
}
function simpleHash(str){
    return CanvasArtifactModel.simpleHash(str);
}

/* --------------------------------------------------------------- Sidebar UI */
function renderArtifactSidebar() {
    return CanvasArtifactView.renderArtifactSidebar.apply(null, arguments);
}

function toggleArtifactSidebar(force) {
    return CanvasArtifactView.toggleArtifactSidebar.apply(null, arguments);
}

/* --------------------------------------------------------------- Viewer */
function openArtifact(id, opts) {
    return CanvasArtifactView.openArtifact.apply(null, arguments);
}
function closeArtifactViewer() {
    return CanvasArtifactView.closeArtifactViewer.apply(null, arguments);
}

/* 安全渲染：HTML 一律转义后再做最小 Markdown 处理，不执行任何脚本（需求第四十条） */
function renderArtifactContent(a) {
    return CanvasArtifactView.renderArtifactContent.apply(null, arguments);
}
function renderArtifactBodyByType(type, raw) {
    return CanvasArtifactView.renderArtifactBodyByType.apply(null, arguments);
}
function renderMarkdownSafe(raw) {
    return CanvasArtifactView.renderMarkdownSafe.apply(null, arguments);
}
function inlineMd(s) {
    return CanvasArtifactView.inlineMd.apply(null, arguments);
}
/* Agent Runtime 读取 Artifact：只发 title / content / artifactType / artifactId，
   绝不发送 UI state、sidebar 选中态、节点坐标等（需求第十七条） */
function canvasAgentArtifactTranscript(refs) {
    return CanvasArtifactView.canvasAgentArtifactTranscript.apply(null, arguments);
}

function renderArtifactTable(raw, isCsv) {
    return CanvasArtifactView.renderArtifactTable.apply(null, arguments);
}

/* --------------------------------------------------------------- 操作 */
/* 新节点落点：优先落在现有节点包围盒右侧；无节点时用视口原点附近。
   不硬编码 (0,0)，避免"加入画布"后节点跑到视口外看不见。 */
function artifactNodeDropSpot() {
    return CanvasArtifactView.artifactNodeDropSpot.apply(null, arguments);
}

/* 加入画布：必须走现有 Canvas Adapter（nodeStore），不直接 push nodes
   Phase 9：支持 scope = conversation | section | item（需求第十七/三十条）。
   section 只把该 Section 转成 Canvas Representation，不把整轮 Brainstorm 全塞进一个 Node。 */
function addArtifactToCanvas(id, opts) {
    return CanvasArtifactView.addArtifactToCanvas.apply(null, arguments);
}
function artifactScopeKey(scope, sec, it) {
    return CanvasArtifactView.artifactScopeKey.apply(null, arguments);
}
function artifactScopeLabel(a, scope, sec, it) {
    return CanvasArtifactView.artifactScopeLabel.apply(null, arguments);
}
function artifactScopeText(a, scope, sec, it) {
    return CanvasArtifactView.artifactScopeText.apply(null, arguments);
}
/* 继续修改：把 Artifact 作为 Reference 加入 Agent Context（需求第十五/十六条） */
function referenceArtifactInAgent(id, opts) {
    return CanvasArtifactView.referenceArtifactInAgent.apply(null, arguments);
}
function renameArtifact(id, title) {
    return CanvasArtifactView.renameArtifact.apply(null, arguments);
}
function deleteArtifact(id) {
    return CanvasArtifactView.deleteArtifact.apply(null, arguments);
}
function clearCanvasAgentArtifacts() {
    return CanvasArtifactView.clearCanvasAgentArtifacts.apply(null, arguments);
}

/* --------------------------------------------------------------- 事件绑定 */


/* =====================================================================
   Phase 9 · Conversation Artifact（分层结构化产物）
   ---------------------------------------------------------------------
   Canvas
    └ ConversationArtifact     一轮完整 Agent 讨论 = 一个 Sidebar 一级条目
       └ ArtifactSection       内部分类（核心人物 / 故事设定 / 关键场面 ...）
          └ ArtifactSectionItem  分类内条目（林澜 / 司徒岳 ...）

   三条铁律：
     1. Section 不是 Artifact，不占 Sidebar 一级条目
     2. Section / Item 的 ID 只在同一 Conversation 内部有意义
     3. 同一 canvas + 同一 conversationId + 同一类型 -> 同一个 artifactId
   ===================================================================== */

// 容器型产物：内部按 Section 组织，是 Sidebar 一级 Conversation 条目。
// 收窄原则：只有"一轮讨论会自然产出多个板块"的创意/结构型类型才算容器；
// script / markdown / report 这类成品文档保持独立文件，不并进会话
// （与后端 CONVERSATION_CONTAINER_TYPES 必须逐项一致）。

// 独立文档型：保持 Sidebar 一级独立条目（如 project.md），即使产生于会话内
// 也不吸进 Conversation 容器（与后端 INDEPENDENT_DOC_TYPES 必须逐项一致）。

// 已有数据是否自动归并成 Conversation。默认 false：老扁平产物（project.md 等）
// 保持原样可读，不会被猜错关系。需要归并时控制台执行 migrateLegacyArtifactsToConversations(true)。


/* 与后端 _artifact_hash 完全一致的 FNV-1a 32-bit。前后端算出同一个 ID 是
   "连改 5 次仍是 1 个 Section" 以及重试不裂成多份的前提。

   注意：必须用 Math.imul。写成 (h ^ c) * 16777619 会因为超过 2^53 丢浮点精度，
   和后端 Python 的精确整数运算算出不同的 ID（踩过，test_phase9_parity.py 有守）。 */
function artifactHash(){
    return CanvasArtifactModel.artifactHash.apply(null, arguments);
}
function conversationArtifactId(canvasIdVal, conversationId, artifactType){
    return CanvasArtifactModel.conversationArtifactId(canvasIdVal, conversationId, artifactType);
}
function artifactSectionId(conversationId, sectionType, sectionTitle){
    return CanvasArtifactModel.artifactSectionId(conversationId, sectionType, sectionTitle);
}
function artifactItemId(sectionId, itemTitle){
    return CanvasArtifactModel.artifactItemId(sectionId, itemTitle);
}
function inferSectionType(title, explicit){
    return CanvasArtifactModel.inferSectionType(title, explicit);
}
function sectionTypeMeta(type){
    return CanvasArtifactModel.sectionTypeMeta(type);
}

/* --------------------------------------------------------------- 读写 */
function artifactSections(a){
    return CanvasArtifactModel.artifactSections(a);
}
function findSectionOf(a, sid){
    return CanvasArtifactModel.findSectionOf(a, sid);
}
function defaultSectionId(a){
    return CanvasArtifactModel.defaultSectionId(a);
}
function activeSectionOf(a){
    return CanvasArtifactModel.activeSectionOf(a);
}
function defaultItemId(a, sid){
    return CanvasArtifactModel.defaultItemId(a, sid);
}
function activeItemOf(sec){
    return CanvasArtifactModel.activeItemOf(sec);
}
function sectionItems(sec){
    return CanvasArtifactModel.sectionItems(sec);
}

function flattenSectionContent(sec){
    return CanvasArtifactModel.flattenSectionContent(sec);
}
function flattenConversationContent(a){
    return CanvasArtifactModel.flattenConversationContent(a);
}

/* --------------------------------------------------------------- 写入 */
/* 一轮会话内部写 Section / Item。
   同一 conversationId + 同一 Section -> update，不 append duplicate（需求第十二/三十二条）。
   Agent 连改 5 次「核心人物」，结果仍然是 1 个 Conversation + 1 个 核心人物 Section。 */
function upsertConversationSection(opts){
    return CanvasArtifactModel.upsertConversationSection(opts);
}

/* 新建一轮独立 Brainstorm：本质是开一个新的 Agent Session，
   conversationId 随之变化，后续产出自然进入新 Conversation（需求第三/九/十条）。 */
function newBrainstormConversation() {
    return CanvasArtifactView.newBrainstormConversation.apply(null, arguments);
}

/* 会话标题种子：优先用本轮第一条用户消息，避免所有 Brainstorm 都叫 "Brainstorm"（需求第二十二条） */
function canvasAgentConversationSeedTitle() {
    return CanvasArtifactView.canvasAgentConversationSeedTitle.apply(null, arguments);
}

/* 老数据迁移：把同一 canvas 下、同一 Agent 会话（sourceRunId 相同）产出的多个
   扁平产物，归并成一个 Conversation 的多个 Section。
   默认不自动跑（ARTIFACT_AUTO_MIGRATE=false），确认无误后再手动执行。 */
function migrateLegacyArtifactsToConversations(apply){
    return CanvasArtifactModel.migrateLegacyArtifactsToConversations(apply);
}

/* --------------------------------------------------------------- 旧数据兼容读取 */
/* Agent / 其它模块读 artifact 内容时统一走这里：有分层就返回当前作用域文本，
   没有就返回老字段 content。老数据零改动即可继续工作。 */
function artifactPlainText(a){
    return CanvasArtifactModel.artifactPlainText(a);
}

/* --------------------------------------------------------------- Viewer 导航 */
function currentArtifactScope(){
    return CanvasArtifactModel.currentArtifactScope();
}
function setArtifactScope(scope) {
    return CanvasArtifactView.setArtifactScope.apply(null, arguments);
}

/* Section Selector + Item Tabs：只切换 Viewer 内容，
   不改变 Sidebar 一级选中项，也不新建 Panel（需求第五/十四条）。 */
function renderConversationChrome(a) {
    return CanvasArtifactView.renderConversationChrome.apply(null, arguments);
}

function selectArtifactSection(sid) {
    return CanvasArtifactView.selectArtifactSection.apply(null, arguments);
}
function openArtifactBodyOnly(a) {
    return CanvasArtifactView.openArtifactBodyOnly.apply(null, arguments);
}
function closeArtifactSectionMenu() {
    return CanvasArtifactView.closeArtifactSectionMenu.apply(null, arguments);
}
function closeArtifactScopeMenu() {
    return CanvasArtifactView.closeArtifactScopeMenu.apply(null, arguments);
}

/* 直接更新某个 Item 的内容（Agent 侧 "只改林澜" 的落点） */
function updateArtifactItemContent(artifactId, sectionId, itemId, content) {
    return CanvasArtifactView.updateArtifactItemContent.apply(null, arguments);
}

/* --------------------------------------------------------------- 事件绑定 */

function tr(key){ return window.StudioI18n ? window.StudioI18n.t(key) : key; }
function tf(key, vars={}){
    return Object.entries(vars).reduce((text, [k,v]) => text.replaceAll(`{${k}}`, v), tr(key));
}
function refreshLanguageView(){
    document.title = tr('comfy.title');
    renderList();
    renderEditor();
    renderPreview();
    renderWorkspaceView();
    refreshIcons();
}
function applyLanguage(){
    if(window.StudioI18n) window.StudioI18n.apply();
    refreshLanguageView();
}
function refreshIcons(){ if(window.lucide) lucide.createIcons(); }

const TYPES = [
    { v:'text', zh:'文本', en:'Text' },
    { v:'textarea', zh:'多行文本', en:'Textarea' },
    { v:'number', zh:'数字', en:'Number' },
    { v:'slider', zh:'滑块', en:'Slider' },
    { v:'dropdown', zh:'下拉框', en:'Dropdown' },
    { v:'image', zh:'图片', en:'Image' },
    { v:'video', zh:'视频', en:'Video' },
    { v:'audio', zh:'音频', en:'Audio' },
    { v:'boolean', zh:'开关', en:'Switch' },
];
function currentLang(){ return window.StudioI18n?.lang?.() === 'en' ? 'en' : 'zh'; }
function typeLabel(type){
    const item = TYPES.find(t => t.v === type);
    return item ? item[currentLang()] : type;
}

// ComfyUI 节点类型 → 中文 + 图标 + 颜色分类
const NODE_INFO = {
    'KSampler':              { label:'采样器',        icon:'⚙', cat:'sampler' },
    'KSamplerAdvanced':      { label:'采样器（高级）',icon:'⚙', cat:'sampler' },
    'SamplerCustom':         { label:'自定义采样',    icon:'⚙', cat:'sampler' },
    'CheckpointLoaderSimple':{ label:'主模型加载',    icon:'📦', cat:'loader' },
    'UNETLoader':            { label:'UNet 加载',     icon:'📦', cat:'loader' },
    'VAELoader':             { label:'VAE 加载',      icon:'📦', cat:'loader' },
    'CLIPLoader':            { label:'CLIP 加载',     icon:'📦', cat:'loader' },
    'DualCLIPLoader':        { label:'双 CLIP 加载',  icon:'📦', cat:'loader' },
    'LoraLoader':            { label:'LoRA 加载',     icon:'⚡', cat:'lora' },
    'LoraLoaderModelOnly':   { label:'LoRA 加载（仅模型）', icon:'⚡', cat:'lora' },
    'CLIPTextEncode':        { label:'提示词编码',    icon:'✎', cat:'prompt' },
    'CLIPTextEncodeFlux':    { label:'Flux 提示词',   icon:'✎', cat:'prompt' },
    'ConditioningCombine':   { label:'条件合并',      icon:'⊕', cat:'prompt' },
    'ConditioningConcat':    { label:'条件拼接',      icon:'⊕', cat:'prompt' },
    'VAEDecode':             { label:'VAE 解码',      icon:'◐', cat:'vae' },
    'VAEEncode':             { label:'VAE 编码',      icon:'◑', cat:'vae' },
    'LoadImage':             { label:'图片加载',      icon:'🖼', cat:'image' },
    'SaveImage':             { label:'图片保存',      icon:'💾', cat:'output' },
    'PreviewImage':          { label:'图片预览',      icon:'👁', cat:'output' },
    'ImageScale':            { label:'图片缩放',      icon:'⇆', cat:'image' },
    'EmptyLatentImage':      { label:'空白潜空间',    icon:'▦', cat:'latent' },
    'LatentUpscaleBy':       { label:'潜空间放大',    icon:'↗', cat:'latent' },
    'ControlNetApply':       { label:'ControlNet',    icon:'⇨', cat:'controlnet' },
    'ControlNetLoader':      { label:'ControlNet 加载',icon:'📦', cat:'loader' },
    'PrimitiveNode':         { label:'常量',          icon:'•', cat:'misc' },
    'Note':                  { label:'备注',          icon:'≡', cat:'misc' },
};

// 常见输入字段 → 中文友好名
const INPUT_LABELS = {
    'text': '提示词文本',
    'prompt': '提示词',
    'positive': '正向条件',
    'negative': '负向条件',
    'seed': '随机种子',
    'noise_seed': '噪声种子',
    'steps': '采样步数',
    'cfg': 'CFG 引导系数',
    'sampler_name': '采样方法',
    'scheduler': '调度器',
    'denoise': '重绘强度',
    'width': '宽度',
    'height': '高度',
    'batch_size': '批量大小',
    'megapixels': '百万像素',
    'strength_model': '模型强度',
    'strength_clip': 'CLIP 强度',
    'lora_name': 'LoRA 模型',
    'ckpt_name': '主模型',
    'vae_name': 'VAE 模型',
    'clip_name': 'CLIP 模型',
    'clip_name1': 'CLIP 模型 1',
    'clip_name2': 'CLIP 模型 2',
    'unet_name': 'UNet 模型',
    'control_net_name': 'ControlNet 模型',
    'image': '图片',
    'images': '图片',
    'mask': '蒙版',
    'latent': '潜空间',
    'value': '数值',
    'string': '字符串',
    'strength': '强度',
    'guidance': '引导系数',
    'resolution': '分辨率',
    'filename_prefix': '文件名前缀',
    'upscale_method': '放大方式',
    'crop': '裁剪方式',
};

function nodeLabel(node){
    if(node._meta?.title) return node._meta.title;
    return NODE_INFO[node.class_type]?.label || node.class_type || '未命名';
}
function nodeSub(node){
    const info = NODE_INFO[node.class_type];
    if(info && node._meta?.title) return info.label + ' · ' + node.class_type;
    return node.class_type || '';
}
function nodeIcon(node){
    return NODE_INFO[node.class_type]?.icon || '◆';
}
function inputLabel(name){
    return INPUT_LABELS[name] || name;
}

let workflows = [];
let selectedName = '';
let currentWorkflow = null;     // 原始 JSON
let currentConfig = null;       // { title, fields:[...] }
let isBuiltin = false;
let previewValues = {};         // field_id -> 发给后端的值（图片：comfy 文件名）
let previewRandomActive = {};   // field_id -> 筛子运行时是否激活；未设置时默认激活
let previewImageUrls = {};      // field_id -> 浏览器可显示的本地 URL（仅图片字段）
let runResult = null;           // url 或 null
let workspaceMode = 'graph';
let miniView = { k: 1, x: 0, y: 0 };
let miniCards = {};
let miniTestNodes = [];
let miniDrag = null;
const COMFY_WORKFLOW_REGISTRY_KEY = 'studio_comfy_workflows_v1';
const REMOVED_COMFY_WORKFLOWS = new Set(['2511.json', 'Flux2-Klein.json']);
const COMFY_WORKFLOW_NAME_ALIASES = Object.freeze({
    'Z image 文生图强化版.json': 'Z-image-enhanced.json',
    'Qwen3.5提示词扩写+图片反推+视频反推.json': 'Qwen35-prompt-vision-video.json'
});
const COMFY_WORKFLOW_FETCH_CACHE = new Map();
const DEFAULT_COMFY_WORKFLOWS = [
    {name:'SeedVR2图片放大流.json', title:'SeedVR2图片放大流', field_count:0, builtin:true},
];

const statusEl = document.getElementById('status');
const listEl = document.getElementById('workflowList');
const workflowTitleInput = document.getElementById('workflowTitleInput');
const subEl = document.getElementById('editorSub');
const deleteBtn = document.getElementById('deleteBtn');
const saveBtn = document.getElementById('saveBtn');
const reloadBtn = document.getElementById('reloadBtn');
const nodeListEl = document.getElementById('nodeList');
const previewCard = document.getElementById('previewContent');
const miniCanvasHost = document.getElementById('miniCanvasHost');

function normalizeComfyWorkflowEntries(list){
    const seen = new Set();
    const out = [];
    (Array.isArray(list) ? list : []).forEach(item => {
        const name = resolveComfyWorkflowName(item?.name);
        if(!name || REMOVED_COMFY_WORKFLOWS.has(name) || !/\.json$/i.test(name) || /\.config\.json$/i.test(name) || seen.has(name)) return;
        seen.add(name);
        const entry = {
            name,
            title: String(item?.title || name.replace(/\.json$/i, '')).trim() || name.replace(/\.json$/i, ''),
            field_count: Math.max(0, Number(item?.field_count) || 0),
            builtin: item?.builtin === true
        };
        if(item?.group?.id) entry.group = {id: String(item.group.id), title: String(item.group.title || item.group.id)};
        out.push(entry);
    });
    return out.sort(compareComfyWorkflowEntries);
}
const COMFY_WORKFLOW_NAME_COLLATOR = new Intl.Collator(['zh-Hans-CN', 'en'], {
    numeric: true,
    sensitivity: 'base'
});
function compareComfyWorkflowEntries(a, b){
    const titleA = String(a?.title || a?.name || '').trim();
    const titleB = String(b?.title || b?.name || '').trim();
    const byTitle = COMFY_WORKFLOW_NAME_COLLATOR.compare(titleA, titleB);
    if(byTitle) return byTitle;
    return COMFY_WORKFLOW_NAME_COLLATOR.compare(String(a?.name || ''), String(b?.name || ''));
}
function resolveComfyWorkflowName(name){
    const normalized = String(name || '').trim();
    return COMFY_WORKFLOW_NAME_ALIASES[normalized] || normalized;
}
function buildSafeComfyWorkflowFileName(name){
    const base = String(name || '')
        .trim()
        .replace(/\.json$/i, '')
        .replace(/[\s]+/g, '-')
        .replace(/[^A-Za-z0-9._-]+/g, '-')
        .replace(/-+/g, '-')
        .replace(/^[-_.]+|[-_.]+$/g, '');
    const safeBase = base || `custom-workflow-${Date.now()}`;
    return `${safeBase}.json`;
}
function clearComfyWorkflowFetchCache(name){
    const resolved = resolveComfyWorkflowName(name);
    if(resolved) COMFY_WORKFLOW_FETCH_CACHE.delete(resolved);
}
async function fetchComfyWorkflowByName(name){
    const resolved = resolveComfyWorkflowName(name);
    if(!resolved) return null;
    if(COMFY_WORKFLOW_FETCH_CACHE.has(resolved)) return COMFY_WORKFLOW_FETCH_CACHE.get(resolved);
    const pending = fetch(`/api/workflows/${encodeURIComponent(resolved)}`)
        .then(async res => res.ok ? res.json() : null)
        .catch(() => null)
        .then(data => {
            if(!data?.workflow) COMFY_WORKFLOW_FETCH_CACHE.delete(resolved);
            return data?.workflow ? data : null;
        });
    COMFY_WORKFLOW_FETCH_CACHE.set(resolved, pending);
    return pending;
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
function replaceKnownComfyWorkflows(primary=[]){
    const normalized = normalizeComfyWorkflowEntries(primary);
    saveLocalComfyWorkflowRegistry(normalized);
    return normalized;
}
async function filterAccessibleComfyWorkflows(list=[]){
    const normalized = normalizeComfyWorkflowEntries(list);
    const accessible = [];
    for(const item of normalized){
        const data = await fetchComfyWorkflowByName(item.name);
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
function removeKnownComfyWorkflow(name){
    const resolved = resolveComfyWorkflowName(name);
    workflows = workflows.filter(item => resolveComfyWorkflowName(item.name) !== resolved);
    saveLocalComfyWorkflowRegistry(loadLocalComfyWorkflowRegistry().filter(item => resolveComfyWorkflowName(item.name) !== resolved));
    clearComfyWorkflowFetchCache(resolved);
}
function rememberComfyWorkflow(name, title='', extra={}){
    workflows = updateKnownComfyWorkflows([{name, title, ...extra}, ...workflows]);
}

function setStatus(text){ statusEl.textContent = text || ''; }
function escapeHtml(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function escapeAttr(s){ return escapeHtml(s); }
const MINI_TEST_NODES_KEY = '__test_nodes';
function comfyFieldMeta(f){
    const node = currentWorkflow?.[f?.node] || null;
    const classType = String(node?.class_type || '').toLowerCase();
    const nodeTitle = String(node?._meta?.title || '').toLowerCase();
    const inputKey = String(f?.input || '').toLowerCase();
    const fieldName = String(f?.name || '').toLowerCase();
    return {
        node,
        classType,
        nodeTitle,
        inputKey,
        fieldName,
        fullText:`${classType} ${nodeTitle} ${inputKey} ${fieldName}`.trim()
    };
}
function fieldKind(f){
    if(['image','video','audio'].includes(f?.type)) return f.type;
    // 2026-10-26：与 canvas-engine-dispatch.js comfyFieldKind 同口径 —— 后端 _is_prompt_slot
    // 判过的提示词槽（id 带 auto_prompt_ 前缀）直接采信，别再按 class_type 猜第二遍。
    if(String(f?.id || '').startsWith('auto_prompt_')) return 'prompt';
    const meta = comfyFieldMeta(f);
    const excludedPromptNode = /previewany|preview|save\s*text|savetext|save_text/.test(meta.classType)
        || /预览|保存文本|保存文件|输出/.test(meta.nodeTitle)
        || /preview|markdown|output|save|file|path|name/.test(meta.inputKey);
    if(excludedPromptNode) return 'setting';
    const promptNode = /cliptextencode|primitivestringmultiline|prompt|\btext\b/.test(meta.classType)
        || /提示词|正向|负向|prompt/.test(meta.nodeTitle);
    const promptField = /(^|[\s_-])(prompt|positive|negative)([\s_-]|$)|提示词|正向|负向/.test(meta.fullText);
    if(promptNode && (meta.inputKey === 'text' || meta.inputKey === 'value' || f?.type === 'textarea' || promptField)) return 'prompt';
    if(promptField) return 'prompt';
    return 'setting';
}
function isMediaField(f){ return ['image','video','audio'].includes(fieldKind(f)); }
function mediaFieldLabel(kind, count){
    const labels = currentLang() === 'en'
        ? {image:'Images', video:'Videos', audio:'Audio'}
        : {image:'图片', video:'视频', audio:'音频'};
    return `${labels[kind] || kind} ${count}`;
}
function mediaAccept(kind){
    if(kind === 'video') return 'video/*';
    if(kind === 'audio') return 'audio/*';
    return 'image/*';
}
function mediaUploadText(kind){
    if(kind === 'video') return tr('comfy.clickUploadVideo');
    if(kind === 'audio') return tr('comfy.clickUploadAudio');
    return tr('comfy.clickUploadImage');
}
function mediaUploadFailedText(kind){
    if(kind === 'video') return tr('comfy.videoUploadFailed');
    if(kind === 'audio') return tr('comfy.audioUploadFailed');
    return tr('comfy.imageUploadFailed');
}
function mediaPreviewHtml(kind, url, name='', compact=false){
    const safeUrl = escapeAttr(url || '');
    const safeName = escapeHtml(name || typeLabel(kind));
    if(!url) return mediaUploadText(kind);
    if(kind === 'video') return `<video src="${safeUrl}" muted preload="metadata" playsinline controls></video>`;
    if(kind === 'audio') return `<div class="media-file-chip"><i data-lucide="file-audio" class="${compact ? 'w-5 h-5' : 'w-6 h-6'}"></i><span class="media-file-name">${safeName}</span><audio src="${safeUrl}" controls preload="metadata"></audio></div>`;
    return `<img src="${safeUrl}">`;
}
function defaultMiniCards(){
    return {
        prompt:{ x:24, y:30 },
        image:{ x:24, y:210 },
        custom:{ x:280, y:78 },
        output:{ x:540, y:120 }
    };
}
function miniNodeFieldCounts(){
    const counts = {prompt:0, image:0, video:0, audio:0};
    if(!currentConfig?.fields?.length) return counts;
    currentConfig.fields.forEach(field => {
        const kind = fieldKind(field);
        if(kind === 'prompt') counts.prompt = 1;
        else if(Object.prototype.hasOwnProperty.call(counts, kind)) counts[kind] += 1;
    });
    return counts;
}
function createMiniNode(type, index=0){
    const baseY = type === 'prompt' ? 96 : type === 'image' ? 286 : type === 'video' ? 456 : 626;
    return {
        id:`${type}_${Date.now()}_${index}_${Math.random().toString(36).slice(2,5)}`,
        type,
        x:type === 'prompt' ? 36 : 42 + index * 26,
        y:baseY + index * 52,
        text:'',
        url:'',
        value:'',
        name:''
    };
}
function sanitizeMiniNode(node){
    if(!node || typeof node !== 'object' || !node.type) return null;
    if(node.type === 'comfy') return { id:String(node.id || 'comfy_1'), type:'comfy', x:Number(node.x) || 330, y:Number(node.y) || 150 };
    if(node.type === 'output') return { id:String(node.id || 'output_1'), type:'output', x:Number(node.x) || 670, y:Number(node.y) || 190 };
    if(!['prompt','image','video','audio'].includes(node.type)) return null;
    return {
        id:String(node.id || `${node.type}_${Math.random().toString(36).slice(2,8)}`),
        type:node.type,
        x:Number(node.x) || (node.type === 'prompt' ? 36 : 42),
        y:Number(node.y) || (node.type === 'prompt' ? 96 : 286),
        text:String(node.text || ''),
        url:String(node.url || ''),
        value:String(node.value || ''),
        name:String(node.name || '')
    };
}
function persistMiniTestNodes(){
    if(!currentConfig) return;
    currentConfig.mini_cards = currentConfig.mini_cards || {};
    currentConfig.mini_cards[MINI_TEST_NODES_KEY] = miniTestNodes.map(sanitizeMiniNode).filter(Boolean);
}
function defaultMiniTestNodes(savedNodes=null){
    const counts = miniNodeFieldCounts();
    const supported = new Set(['comfy','output']);
    Object.entries(counts).forEach(([type, count]) => {
        if(count > 0) supported.add(type);
    });
    const existing = Array.isArray(savedNodes) ? savedNodes.map(sanitizeMiniNode).filter(node => node && supported.has(node.type)) : null;
    const normalized = existing ? existing.filter(node => supported.has(node.type)) : [];
    if(existing){
        if(!normalized.some(node => node.type === 'comfy')) normalized.push({ id:'comfy_1', type:'comfy', x:330, y:150 });
        if(!normalized.some(node => node.type === 'output')) normalized.push({ id:'output_1', type:'output', x:670, y:190 });
        return normalized;
    }
    const ensureCount = (type, count) => {
        while(normalized.filter(node => node.type === type).length < count){
            normalized.push(createMiniNode(type, normalized.filter(node => node.type === type).length));
        }
    };
    ensureCount('prompt', counts.prompt);
    ensureCount('image', counts.image);
    ensureCount('video', counts.video);
    ensureCount('audio', counts.audio);
    if(!normalized.some(node => node.type === 'comfy')) normalized.push({ id:'comfy_1', type:'comfy', x:330, y:150 });
    if(!normalized.some(node => node.type === 'output')) normalized.push({ id:'output_1', type:'output', x:670, y:190 });
    return normalized;
}
function syncMiniTestNodes(){
    miniTestNodes = defaultMiniTestNodes(miniTestNodes);
    persistMiniTestNodes();
}

// —— ComfyUI 本地路径（简化：只填一个路径，url/启动命令后端自动处理）——
let comfyInstances = [];
function _normalizeComfyInstance(item){
    if(typeof item === 'string') return { path: item };
    return { path: item?.path || '' };
}
async function loadComfyInstances(){
    try {
        const data = await fetch('/api/comfyui/instances').then(r => r.json());
        comfyInstances = (Array.isArray(data.instances) ? data.instances : []).map(_normalizeComfyInstance);
        renderComfyInstances();
    } catch(e){ console.error(e); }
}
function renderComfyInstances(){
    const el = document.getElementById('comfyInstancesList');
    if(!el) return;
    const it = comfyInstances[0] || { path:'' };
    el.innerHTML = `
        <div class="comfy-instance-row">
            <div class="ci-field ci-path">
                <span class="ci-label">路径</span>
                <input class="small-input comfy-path-input" type="text" value="${escapeAttr(it.path)}" placeholder="ComfyUI 安装目录，如 D:/ComfyUI" oninput="updateComfyInstance(0, 'path', this.value)">
            </div>
        </div>`;
    refreshIcons();
}
function updateComfyInstance(index, field, value){
    if(!comfyInstances[index]) comfyInstances[index] = { path:'' };
    comfyInstances[index][field] = value;
}
async function saveComfyInstances(){
    const path = String(comfyInstances[0]?.path || '').trim();
    const cleaned = path ? [{ path }] : [];
    setStatus('保存中...');
    try {
        const res = await fetch('/api/comfyui/instances', {
            method:'PUT',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({ instances: cleaned })
        });
        if(!res.ok) throw new Error((await res.json()).detail || '保存失败');
        const data = await res.json();
        comfyInstances = (data.instances || cleaned).map(_normalizeComfyInstance);
        renderComfyInstances();
        try { new BroadcastChannel('studio-api').postMessage({ type: 'comfy-instances-changed' }); } catch(e) {}
        try { window.parent?.postMessage({ type: 'comfy-instances-changed' }, '*'); } catch(e) {}
        setStatus(cleaned.length ? 'ComfyUI 本地路径已保存' : '已清除本地路径（运行前需手动启动 ComfyUI）');
    } catch(e){
        alert(e.message || '保存失败');
        setStatus('保存失败');
    }
}

async function loadList(){
    try {
        const res = await fetch('/api/workflows');
        if(!res.ok) throw new Error('workflow-list-unavailable');
        const data = await res.json();
        workflows = replaceKnownComfyWorkflows(data.workflows || []);
        renderList();
        // 自动加载：当前没选中 或 之前选中的已不存在 → 选第一个
        const stillExists = selectedName && workflows.some(w => w.name === selectedName);
        if(!stillExists && workflows.length){
            await selectWorkflow(workflows[0].name);
        }
    } catch(e){
        workflows = await filterAccessibleComfyWorkflows(mergeKnownComfyWorkflows(loadLocalComfyWorkflowRegistry()));
        saveLocalComfyWorkflowRegistry(workflows);
        renderList();
        const stillExists = selectedName && workflows.some(w => w.name === selectedName);
        if(!stillExists && workflows.length){
            await selectWorkflow(workflows[0].name);
        }
        setStatus(tr('comfy.loadFailed'));
        console.error(e);
    }
}
// iframe 在 index.html 里通过 switchUI 显示，首次显示时可能 DOMContentLoaded 已经过去；
// 添加一个 pageshow 监听确保进入页面时一定刷新
window.addEventListener('pageshow', () => {
    if(!currentWorkflow && workflows.length === 0) loadList();
});

// 2026-10-26 老王：重载不是「重读 app 自己那份副本」——那玩意儿是导入时拷进来的副本，
// 改 ComfyUI 侧导出的源文件后它永远不变。真重载 = 去源文件拉新版本 → 覆盖副本。
//   ① 后端记住过源路径 → 直接拉；
//   ② 没记过 / 源文件被删或改名 → 弹窗让老王手动指定，指定一次写进 config，以后一键拉；
//   ③ 两边缓存清掉后重新读盘，并广播给画布页（画布上已配参数按稳定键保留）。
async function onReload(){
    const target = resolveComfyWorkflowName(selectedName || '');
    if(!target) return;
    setStatus(tr('comfy.reloading') || '正在从源文件重载…');
    const result = await reloadFromSource(target, {});
    if(result && result.need_source){
        openSourcePicker(target, result.last_source || '', result.reason || 'unset',
            result.candidates || [], result.source_dirs || []);
        return;
    }
    await finishReload(target, result);
}
async function reloadFromSource(name, body){
    const res = await fetch(`/api/workflows/${encodeURIComponent(name)}/reload-source`, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify(body || {})
    }).catch(() => null);
    if(!res) return {ok:false, error:(tr('comfy.reloadFailed') || '重载失败')};
    const data = await res.json().catch(() => ({}));
    if(!res.ok && !data.need_source){
        return {ok:false, error:data.detail || data.error || (tr('comfy.reloadFailed') || '重载失败')};
    }
    return data;
}
async function finishReload(target, data){
    if(!data || !data.ok){
        const msg = (data && data.error) || (tr('comfy.reloadFailed') || '重载失败');
        alert(msg);
        setStatus(msg);
        return;
    }
    const finalName = resolveComfyWorkflowName((data.record && data.record.name) || data.name || target);
    COMFY_WORKFLOW_FETCH_CACHE.delete(finalName);
    COMFY_WORKFLOW_FETCH_CACHE.delete(target);
    await selectWorkflow(finalName);
    renderSourceInfo(data.source_path || '');
    setStatus((tr('comfy.reloadedFromSource') || '已从源文件重载') + ' · ' + String(finalName).replace(/\.json$/i, ''));
    broadcastComfyWorkflowReloaded(finalName);
}
function renderSourceInfo(path){
    const row = document.getElementById('sourceInfoRow');
    const text = document.getElementById('sourcePathText');
    if(!row || !text) return;
    const src = String(path || (currentConfig && currentConfig.source_path) || '').trim();
    if(!src){ row.style.display = 'none'; return; }
    row.style.display = '';
    text.textContent = src;
    text.title = src;
}
// ---- 源文件指定弹窗（源没了 / 从没记过） ----
let sourcePickerTarget = '';
let sourcePickerLast = '';
let sourcePickerDirs = [];
function openSourcePicker(name, lastSource, reason, candidates, sourceDirs){
    sourcePickerTarget = resolveComfyWorkflowName(name || '');
    sourcePickerLast = String(lastSource || '').trim();
    sourcePickerDirs = Array.isArray(sourceDirs) ? sourceDirs.filter(Boolean) : [];
    const backdrop = document.getElementById('sourcePickerBackdrop');
    const hint = document.getElementById('sourcePickerHint');
    const input = document.getElementById('sourcePathInput');
    if(!backdrop || !input) return;
    renderSourceCandidates(candidates || []);
    if(hint){
        hint.textContent = reason === 'missing'
            ? ((tr('comfy.sourceMissing') || '原来记的源文件已经不在了：') + sourcePickerLast + '。' + (tr('comfy.sourceMissingTip') || '指定新位置（同目录下可以直接选文件），指定一次以后就自动了。'))
            : reason === 'dir-empty'
                ? (tr('comfy.sourceDirEmpty') || '这个目录里没找到能对上名字的工作流 json，换一个目录或填完整文件路径。')
                : (tr('comfy.sourceUnset') || '这个工作流还没记过源文件。填完整文件路径，或**只填它所在的目录**（我来认名字），也可以用「浏览…」直接选文件；指定一次以后点重载就自动拉新版。');
    }
    input.value = reason === 'missing' ? '' : sourcePickerLast;
    backdrop.style.display = 'flex';
    setTimeout(() => { try { input.focus(); input.select(); } catch(e){} }, 30);
    refreshIcons();
}
// 后端扫本机常见 ComfyUI 工作流目录找到的同名候选：点一下就是它，省得手敲路径。
function renderSourceCandidates(list){
    const box = document.getElementById('sourceCandidateList');
    if(!box) return;
    box.innerHTML = '';
    const items = (list || []).filter(Boolean);
    if(!items.length){ box.style.display = 'none'; return; }
    box.style.display = 'flex';
    const head = document.createElement('div');
    head.style.cssText = 'font-size:11px;color:var(--wf-v2-muted)';
    head.textContent = tr('comfy.sourceCandidates') || '在本机 ComfyUI 目录里找到这些同名文件，点一下就用它：';
    box.appendChild(head);
    items.forEach(path => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'source-candidate';
        btn.textContent = path;
        btn.addEventListener('click', () => submitSourcePathValue(path));
        box.appendChild(btn);
    });
}
async function submitSourcePathValue(path){
    if(!sourcePickerTarget || !path) return;
    const hint = document.getElementById('sourcePickerHint');
    const result = await reloadFromSource(sourcePickerTarget, {source_path:path});
    if(result && result.ok){
        closeSourcePicker();
        await finishReload(sourcePickerTarget, result);
        return;
    }
    if(hint) hint.textContent = (result && result.error) || (tr('comfy.reloadFailed') || '重载失败');
}
function closeSourcePicker(){
    const backdrop = document.getElementById('sourcePickerBackdrop');
    if(backdrop) backdrop.style.display = 'none';
    const box = document.getElementById('sourceCandidateList');
    if(box){ box.innerHTML = ''; box.style.display = 'none'; }
    sourcePickerTarget = '';
}
function pickSourceFile(){
    const input = document.getElementById('sourceFileInput');
    if(input) input.click();
}
async function onSourceFilePicked(event){
    const file = event.target.files && event.target.files[0];
    event.target.value = '';
    if(!file || !sourcePickerTarget) return;
    let parsed = null;
    try { parsed = JSON.parse(await file.text()); }
    catch(e){ alert(tr('comfy.invalidJson') || '不是合法的 JSON 文件'); return; }
    // 浏览器不给真实绝对路径。用「记过的源目录 + 选中的文件名」拼一个可复用路径，
    // 后端会校验它确实存在；拼不出来就退回只传内容（能覆盖，但记不住源）。
    let guess = '';
    const dirs = [];
    if(sourcePickerLast){
        const cut = Math.max(sourcePickerLast.lastIndexOf('\\'), sourcePickerLast.lastIndexOf('/'));
        if(cut >= 0) dirs.push(sourcePickerLast.slice(0, cut + 1));
    }
    sourcePickerDirs.forEach(d => dirs.push(d));
    for(const dir of dirs){
        const sep = dir.includes('\\') ? '\\' : '/';
        guess = dir.endsWith(sep) ? (dir + file.name) : (dir + sep + file.name);
        break;
    }
    const hint = document.getElementById('sourcePickerHint');
    const body = guess ? {source_path:guess} : {workflow:parsed};
    const result = await reloadFromSource(sourcePickerTarget, body);
    if(result && result.need_source && guess){
        // 拼出来的路径不存在 → 退回「只传内容」，这次能覆盖，但记不住路径
        const fallback = await reloadFromSource(sourcePickerTarget, {workflow:parsed});
        if(fallback && fallback.ok){
            if(hint) hint.textContent = (tr('comfy.sourcePickedNoPath') || '已用选中的文件覆盖（浏览器不给真实路径，记不住源；想以后自动拉新版就手动填一次绝对路径）');
            await finishReload(sourcePickerTarget, fallback);
            setTimeout(closeSourcePicker, 1200);
            return;
        }
        if(hint) hint.textContent = (fallback && fallback.error) || (tr('comfy.reloadFailed') || '重载失败');
        return;
    }
    if(result && result.ok){
        closeSourcePicker();
        await finishReload(sourcePickerTarget, result);
        return;
    }
    if(hint) hint.textContent = (result && result.error) || (tr('comfy.reloadFailed') || '重载失败');
}
async function submitSourcePath(){
    if(!sourcePickerTarget) return;
    const input = document.getElementById('sourcePathInput');
    const hint = document.getElementById('sourcePickerHint');
    const path = String((input && input.value) || '').trim().replace(/^["']|["']$/g, '');
    if(!path){
        if(hint) hint.textContent = (tr('comfy.sourcePathEmpty') || '先填源文件路径，或用「浏览…」选一个文件');
        return;
    }
    const result = await reloadFromSource(sourcePickerTarget, {source_path:path});
    if(result && result.need_source){
        if(hint) hint.textContent = (tr('comfy.sourceNotFound') || '这个路径下没有文件，检查一下：') + path;
        return;
    }
    if(result && result.ok){
        closeSourcePicker();
        await finishReload(sourcePickerTarget, result);
        return;
    }
    if(hint) hint.textContent = (result && result.error) || (tr('comfy.reloadFailed') || '重载失败');
}
function broadcastComfyWorkflowReloaded(name){
    const msg = { type:'comfy-workflow-reloaded', name:name };
    try { new BroadcastChannel('studio-api').postMessage(msg); } catch(e) {}
    try { if(window.parent && window.parent !== window) window.parent.postMessage(msg, '*'); } catch(e) {}
    try { if(window.top && window.top !== window) window.top.postMessage(msg, '*'); } catch(e) {}
}

function renderList(){
    if(!workflows.length){
        listEl.innerHTML = `<div class="preview-empty" style="padding:20px 12px">${escapeHtml(tr('smart.noWorkflow') || '暂无 ComfyUI 工作流')}</div>`;
        refreshIcons();
        return;
    }
    listEl.innerHTML = workflows.map(w => `
        <button class="workflow-card ${w.name===selectedName?'active':''}" type="button" onclick="selectWorkflow('${escapeHtml(w.name)}')">
            <span class="workflow-icon"><i data-lucide="${w.builtin?'package':(w.group?'layers':'file-json-2')}" class="w-3.5 h-3.5"></i></span>
            <span class="min-w-0" style="flex:1">
                <div class="workflow-name">${escapeHtml(w.title)}</div>
                <div class="workflow-meta">${tf('comfy.fieldCount', {count:w.field_count})}</div>
            </span>
            ${w.builtin?`<span class="builtin-badge">${tr('comfy.builtin')}</span>`:''}
        </button>
    `).join('');
    refreshIcons();
}

async function selectWorkflow(name){
    selectedName = resolveComfyWorkflowName(name);
    renderList();
    try {
        setStatus(tr('comfy.loading'));
        const data = await fetchComfyWorkflowByName(selectedName);
        if(!data?.workflow) throw new Error('workflow-open-unavailable');
        selectedName = resolveComfyWorkflowName(data.name || selectedName);
        currentWorkflow = data.workflow;
        const knownWorkflow = workflows.find(item => item.name === selectedName);
        currentConfig = data.config || { title:(knownWorkflow?.title || selectedName.replace('.json','')), fields:[] };
        if(!currentConfig.fields) currentConfig.fields = [];
        if(!currentConfig.mini_cards) currentConfig.mini_cards = {};
        isBuiltin = !!data.builtin;
        miniCards = {...defaultMiniCards(), ...currentConfig.mini_cards};
        currentConfig.mini_cards = miniCards;
        // 释放上一次的图片 blob URL
        Object.values(previewImageUrls).forEach(u => { try { URL.revokeObjectURL(u); } catch(e){} });
        previewImageUrls = {};
        previewValues = {};
        currentConfig.fields.forEach(f => {
            if(f.default !== undefined && f.default !== null) previewValues[f.id] = f.default;
        });
        previewRandomActive = {};
        runResult = null;
        graphView = { k: 1, x: 0, y: 0 };
        miniView = { k: 1, x: 0, y: 0 };
        miniTestNodes = defaultMiniTestNodes(currentConfig.mini_cards?.[MINI_TEST_NODES_KEY]);
        persistMiniTestNodes();
        rememberComfyWorkflow(selectedName, currentConfig.title || selectedName.replace('.json',''), {field_count:(currentConfig.fields || []).length, builtin:isBuiltin});
        renderList();
        renderEditor();
        renderPreview();
        renderSourceInfo(currentConfig && currentConfig.source_path);
        // 新工作流加载后自动适配窗口
        setTimeout(() => graphFit(), 50);
        setStatus('');
    } catch(e){
        removeKnownComfyWorkflow(name);
        if(selectedName === resolveComfyWorkflowName(name)) selectedName = '';
        currentWorkflow = null;
        currentConfig = null;
        renderList();
        renderEditor();
        renderPreview();
        setStatus(tr('comfy.openFailed'));
        console.error(e);
    }
}

function fieldFor(node, input){
    return currentConfig.fields.find(f => f.node === node && f.input === input);
}
function makeFieldId(node, input){
    const nodeId = String(node == null ? '' : node).trim();
    const key = String(input == null ? '' : input).trim();
    if(!nodeId || !key) return 'f_' + Math.random().toString(36).slice(2,9);
    // 2026-10-24 老王：改成由 node+input 派生的**稳定 id**。原来是随机串，
    // 重新暴露同一个参数就换 id，之前配好的值就失联（"改一点点要重配"）。
    const seed = nodeId + '::' + key;
    let h1 = 2166136261, h2 = 5381;
    for(let i = 0; i < seed.length; i++){
        const c = seed.charCodeAt(i);
        h1 = ((h1 ^ c) * 16777619) >>> 0;
        h2 = ((h2 * 33) ^ c) >>> 0;
    }
    const body = (h1.toString(36) + h2.toString(36)).replace(/[^a-z0-9]/g, '');
    return 'f_' + body.slice(0, 8).padEnd(8, '0');
}

function toggleField(node, input){
    const existing = fieldFor(node, input);
    if(existing){
        currentConfig.fields = currentConfig.fields.filter(f => f !== existing);
        delete previewValues[existing.id];
        delete previewRandomActive[existing.id];
    } else {
        const nodeData = currentWorkflow[node];
        const rawValue = nodeData?.inputs?.[input];
        const type = guessType(rawValue, input);
        const f = {
            id: makeFieldId(node, input),
            node, input,
            name: inputLabel(input),
            type,
            default: typeof rawValue === 'object' ? null : rawValue,
            options: [],
        };
        if(type === 'slider' || type === 'number') {
            if(typeof rawValue === 'number'){
                f.min = 0;
                f.max = Math.max(rawValue * 2, 10);
                f.step = rawValue > 0 && rawValue < 5 ? 0.1 : 1;
            }
            if(type === 'number') f.random_enabled = false;
        }
        currentConfig.fields.push(f);
        if(f.default !== undefined && f.default !== null) previewValues[f.id] = f.default;
    }
    syncMiniTestNodes();
    renderEditor();
    renderPreview();
    // 浮窗打开时同步刷新浮窗内容
    if(popupNodeId === node) refreshPopupBody();
}

function refreshPopupBody(){
    if(!popupNodeId) return;
    const node = currentWorkflow[popupNodeId];
    if(!node) return;
    const popup = document.getElementById('nodePopup');
    const body = popup.querySelector('.popup-body');
    if(!body) return;
    const inputs = Object.entries(node.inputs || {}).filter(([k,v]) => {
        return !(Array.isArray(v) && v.length === 2 && typeof v[0] === 'string' && typeof v[1] === 'number');
    });
    body.innerHTML = inputs.length === 0
        ? `<div class="popup-empty">${tr('comfy.noConfigFields')}</div>`
        : inputs.map(([key, value]) => renderInputRow(popupNodeId, key, value)).join('');
    refreshIcons();
}

function guessType(value, inputName){
    const lc = (inputName||'').toLowerCase();
    if(typeof value === 'boolean') return 'boolean';
    if(typeof value === 'number'){
        if(/strength|cfg|denoise/.test(lc)) return 'slider';
        return 'number';
    }
    if(typeof value === 'string'){
        if(/prompt|text|description/.test(lc) || (value && value.length > 60)) return 'textarea';
        if(/video|movie|mp4|webm|mov|m4v|vhs/.test(lc) || /\.(mp4|webm|mov|m4v|avi|mkv)(\?|$)/i.test(value)) return 'video';
        if(/audio|sound|music|voice|wav|mp3/.test(lc) || /\.(mp3|wav|m4a|aac|ogg|flac)(\?|$)/i.test(value)) return 'audio';
        if(/image|img|mask|filename|file/.test(lc) || /\.(png|jpe?g|webp|gif|bmp|tiff?)(\?|$)/i.test(value)) return 'image';
        return 'text';
    }
    return 'text';
}

function updateField(fieldId, key, value, sourceEl){
    const f = currentConfig.fields.find(x => x.id === fieldId);
    if(!f) return;
    f[key] = value;
    const sourceInPopup = !!(sourceEl && sourceEl.closest && sourceEl.closest('#nodePopup'));
    if(key === 'type'){
        previewValues[fieldId] = (value === 'boolean') ? false : (value === 'number' || value === 'slider' ? 0 : '');
        f.random_enabled = value === 'number' ? !!f.random_enabled : false;
        delete previewRandomActive[fieldId];
    }
    if(key === 'random_enabled'){
        delete previewRandomActive[fieldId];
    }
    // 改名字 / 类型时不需要整页重渲染，浮窗自身刷新即可
    if(key === 'name' || key === 'min' || key === 'max' || key === 'step' || key === 'default' || key === 'options' || key === 'random_enabled'){
        syncMiniTestNodes();
        renderPreview();
        if(workspaceMode === 'canvas') renderMiniCanvasPreview(miniCanvasHost, true);
        // 浮窗内编辑时不要重建当前输入框，否则每输入一个字符都会失焦。
        if(popupNodeId === f.node && !sourceInPopup) refreshPopupBody();
        return;
    }
    syncMiniTestNodes();
    renderEditor();
    renderPreview();
    if(popupNodeId === f.node) refreshPopupBody();
}

function updateWorkflowTitle(value){
    if(!currentConfig) return;
    currentConfig.title = value;
    const item = workflows.find(w => w.name === selectedName);
    if(item) item.title = value || selectedName.replace('.json','');
    renderList();
}

async function onRenameFile(){
    // 把后端文件名也改成显示名，让「前端显示名」和「后端文件名」统一；
    // 画布里所有引用旧文件名的工作流节点由后端自动改写，无需手动重连。
    if(!selectedName || !currentConfig) return;
    const target = String(workflowTitleInput?.value || '').trim();
    if(!target){ alert('请先填写工作流名称'); return; }
    const base = target.replace(/\.json$/i, '').trim();
    const oldBase = selectedName.replace(/\.json$/i, '');
    if(!base) return;
    if(base === oldBase){ setStatus('文件名已经一致了'); return; }
    const confirmText = (typeof tf === 'function' && typeof tr === 'function')
        ? `把工作流文件也改名为《${base}》？`
        : `把工作流文件也改名为《${base}》？`;
    if(!confirm(confirmText + '\n\n画布里引用它的节点会自动同步，不需要手动重连。')) return;
    setStatus('正在改名…');
    try {
        const res = await fetch(`/api/workflows/${encodeURIComponent(selectedName)}/rename`, {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({name: base})
        });
        const data = await res.json().catch(() => ({}));
        if(!res.ok) throw new Error(data.detail || '改名失败');
        clearComfyWorkflowFetchCache(selectedName);
        selectedName = data.name || (base + '.json');
        setStatus('已改名为 ' + selectedName);
        await loadList();
        selectWorkflow(selectedName);
        new BroadcastChannel('studio-api').postMessage({ type: 'workflows-changed' });
    } catch(e){
        const msg = String(e?.message || '改名失败');
        // 后端没加载 rename 路由（Python 改动必须重启软件）时给明确指引，别甩黑话
        alert(/not found|404/i.test(msg)
            ? '改名失败：后端还没加载这个功能（改了后端 Python 必须重启软件）。\n请完全退出并重新启动 MyridTV，再点「同步文件名」。'
            : ('改名失败：' + msg));
        setStatus('改名失败');
    }
}

function setWorkspaceMode(mode){
    workspaceMode = mode === 'canvas' ? 'canvas' : 'graph';
    document.getElementById('workspaceGraphTab')?.classList.toggle('active', workspaceMode === 'graph');
    document.getElementById('workspaceCanvasTab')?.classList.toggle('active', workspaceMode === 'canvas');
    renderWorkspaceView();
}

function renderEditor(){
    if(!currentWorkflow){
        deleteBtn.style.display = 'none';
        saveBtn.style.display = 'none';
        if(reloadBtn) reloadBtn.style.display = 'none';
        nodeListEl.innerHTML = '';
        document.getElementById('graphCard').style.display = 'none';
        document.getElementById('nodesToggle').style.display = 'none';
        if(miniCanvasHost) miniCanvasHost.style.display = 'none';
        return;
    }
    document.getElementById('nodesToggle').style.display = workspaceMode === 'graph' ? 'flex' : 'none';
    workflowTitleInput.value = currentConfig.title || selectedName.replace('.json','');
    subEl.textContent = tf('comfy.nodeStats', {nodes:Object.keys(currentWorkflow).length, fields:currentConfig.fields.length}) + (isBuiltin ? ` · ${tr('comfy.builtin')}` : '');
    deleteBtn.style.display = isBuiltin ? 'none' : 'inline-flex';
    saveBtn.style.display = 'inline-flex';
    if(reloadBtn) reloadBtn.style.display = 'inline-flex';

    renderGraph();
    renderWorkspaceView();

    const nodes = Object.entries(currentWorkflow).sort((a,b)=>{
        const aNum = parseInt(a[0],10), bNum = parseInt(b[0],10);
        if(!isNaN(aNum) && !isNaN(bNum)) return aNum - bNum;
        return a[0].localeCompare(b[0]);
    });

    nodeListEl.innerHTML = nodes.map(([nodeId, node])=>{
        const inputs = Object.entries(node.inputs || {}).filter(([k,v])=>{
            return !(Array.isArray(v) && v.length === 2 && typeof v[0] === 'string' && typeof v[1] === 'number');
        });
        const exposedCount = inputs.filter(([k])=>fieldFor(nodeId,k)).length;
        const expanded = exposedCount > 0;
        const icon = nodeIcon(node);
        return `
            <div class="node-card ${expanded?'expanded':''}" id="node-card-${escapeAttr(nodeId)}" data-node-id="${escapeAttr(nodeId)}">
                <div class="node-card-head" onclick="this.parentElement.classList.toggle('expanded')">
                    <div style="display:flex;align-items:center;gap:12px;min-width:0;flex:1">
                        <span style="font-size:20px;line-height:1;flex:0 0 auto">${icon}</span>
                        <div style="min-width:0">
                            <div class="node-class">${escapeHtml(nodeLabel(node))}</div>
                            <div class="node-id">${escapeHtml(nodeSub(node))} · #${escapeHtml(nodeId)} · ${tf('comfy.configurableCount', {count:inputs.length})}</div>
                        </div>
                    </div>
                    <div style="display:flex;align-items:center;gap:10px;flex:0 0 auto">
                        <div class="node-stats">${exposedCount > 0 ? tf('comfy.exposedCount', {count:exposedCount}) : ''}</div>
                        <i data-lucide="chevron-down" class="w-4 h-4 node-chev"></i>
                    </div>
                </div>
                <div class="node-inputs">
                    ${inputs.map(([key, value])=>renderInputRow(nodeId, key, value)).join('') || `<div style="color:var(--faint);font-size:11px;text-align:center;padding:14px">${tr('comfy.noConfigInputs')}</div>`}
                </div>
            </div>
        `;
    }).join('');
    refreshIcons();
}

// 计算节点拓扑层级（按从入度 0 的源节点向下游传播）
function computeLayers(){
    const ids = Object.keys(currentWorkflow);
    const incoming = {};   // nodeId -> Set of upstream nodeIds
    const outgoing = {};
    ids.forEach(id => { incoming[id] = new Set(); outgoing[id] = new Set(); });
    ids.forEach(id => {
        const inputs = currentWorkflow[id].inputs || {};
        Object.values(inputs).forEach(v => {
            if(Array.isArray(v) && v.length === 2 && typeof v[0] === 'string'){
                if(currentWorkflow[v[0]]){
                    incoming[id].add(v[0]);
                    outgoing[v[0]].add(id);
                }
            }
        });
    });
    const layer = {};
    const visited = new Set();
    function dfs(id, lv){
        if(visited.has(id)) return;
        if((layer[id] || 0) < lv) layer[id] = lv;
        else layer[id] = layer[id] || lv;
        visited.add(id);
        outgoing[id].forEach(child => dfs(child, lv + 1));
    }
    // 从无上游的节点开始
    ids.forEach(id => { if(incoming[id].size === 0) dfs(id, 0); });
    // 处理可能漏掉的环 / 孤立节点
    ids.forEach(id => { if(!(id in layer)) layer[id] = 0; });
    // 按层级分桶
    const buckets = {};
    ids.forEach(id => {
        const lv = layer[id];
        (buckets[lv] = buckets[lv] || []).push(id);
    });
    return { layer, buckets, incoming };
}

function renderGraph(){
    const svg = document.getElementById('graphSvg');
    if(!currentWorkflow || !Object.keys(currentWorkflow).length){
        document.getElementById('graphCard').style.display = 'none';
        return;
    }
    document.getElementById('graphCard').style.display = 'block';
    const { layer, buckets, incoming } = computeLayers();
    const NODE_W = 130, NODE_H = 50, X_GAP = 36, Y_GAP = 14;
    const positions = {};
    const sortedLevels = Object.keys(buckets).map(Number).sort((a,b)=>a-b);
    let maxRows = 0;
    sortedLevels.forEach(lv => {
        const ids = buckets[lv].sort((a,b)=>parseInt(a,10)-parseInt(b,10));
        ids.forEach((id, idx) => {
            positions[id] = { x: lv * (NODE_W + X_GAP) + 16, y: idx * (NODE_H + Y_GAP) + 16 };
        });
        maxRows = Math.max(maxRows, ids.length);
    });
    const totalW = (sortedLevels.length) * (NODE_W + X_GAP) + 16;
    const totalH = maxRows * (NODE_H + Y_GAP) + 16;

    // 连线
    const edgesHtml = [];
    Object.keys(currentWorkflow).forEach(toId => {
        const inputs = currentWorkflow[toId].inputs || {};
        const seen = new Set();
        Object.values(inputs).forEach(v => {
            if(Array.isArray(v) && v.length === 2 && typeof v[0] === 'string' && positions[v[0]]){
                if(seen.has(v[0])) return;
                seen.add(v[0]);
                const from = positions[v[0]];
                const to = positions[toId];
                const x1 = from.x + NODE_W, y1 = from.y + NODE_H/2;
                const x2 = to.x, y2 = to.y + NODE_H/2;
                const cx = (x1 + x2) / 2;
                edgesHtml.push(`<path class="gedge" d="M ${x1} ${y1} C ${cx} ${y1}, ${cx} ${y2}, ${x2} ${y2}"></path>`);
            }
        });
    });

    // 节点
    const nodesHtml = Object.entries(currentWorkflow).map(([id, node]) => {
        const pos = positions[id];
        const label = nodeLabel(node);
        const sub = node.class_type || '';
        const exposedCount = currentConfig.fields.filter(f => f.node === id).length;
        const exposedClass = exposedCount > 0 ? 'has-exposed' : '';
        const cat = NODE_INFO[node.class_type]?.cat || 'misc';
        const icon = nodeIcon(node);
        const truncLabel = label.length > 12 ? label.slice(0,12) + '…' : label;
        const truncSub = sub.length > 16 ? sub.slice(0,16) + '…' : sub;
        return `
            <g class="gnode cat-${cat} ${exposedClass}" data-node-id="${escapeAttr(id)}" transform="translate(${pos.x},${pos.y})" onclick="openNodePopup('${escapeAttr(id)}', this)">
                <rect width="${NODE_W}" height="${NODE_H}" rx="8"></rect>
                <text class="gn-icon" x="10" y="20" font-size="14">${icon}</text>
                <text class="gn-title" x="28" y="20">${escapeHtml(truncLabel)}</text>
                <text class="gn-sub" x="28" y="35">${escapeHtml(truncSub)}</text>
                <text class="gn-sub" x="${NODE_W - 8}" y="20" text-anchor="end">#${escapeHtml(id)}</text>
                ${exposedCount > 0 ? `<text class="gbadge" x="${NODE_W - 8}" y="42" text-anchor="end">${tf('comfy.usedCount', {count:exposedCount})}</text>` : ''}
            </g>
        `;
    }).join('');

    graphContentSize = { w: totalW, h: totalH };
    svg.innerHTML = `<g id="graphViewport" transform="translate(${graphView.x},${graphView.y}) scale(${graphView.k})">${edgesHtml.join('')}${nodesHtml}</g>`;
    // 设置 SVG 自身尺寸（占满容器）
    const wrap = svg.parentElement;
    svg.setAttribute('viewBox', `0 0 ${wrap.clientWidth} ${wrap.clientHeight}`);
    attachPanZoom(svg, wrap);
    updateZoomPill();
}

// 缩放/平移状态
let graphView = { k: 1, x: 0, y: 0 };
let graphContentSize = { w: 0, h: 0 };
let panState = null;

function updateZoomPill(){
    const pill = document.getElementById('zoomPill');
    if(pill) pill.textContent = Math.round(graphView.k * 100) + '%';
}
function applyGraphTransform(){
    const vp = document.getElementById('graphViewport');
    if(vp) vp.setAttribute('transform', `translate(${graphView.x},${graphView.y}) scale(${graphView.k})`);
    updateZoomPill();
}
function graphZoom(dir){
    const factor = dir > 0 ? 1.2 : 1/1.2;
    const newK = Math.max(0.2, Math.min(3, graphView.k * factor));
    // 围绕容器中心缩放
    const wrap = document.querySelector('.graph-svg-wrap');
    const cx = wrap.clientWidth / 2;
    const cy = wrap.clientHeight / 2;
    graphView.x = cx - (cx - graphView.x) * (newK / graphView.k);
    graphView.y = cy - (cy - graphView.y) * (newK / graphView.k);
    graphView.k = newK;
    applyGraphTransform();
}
function graphFit(){
    const wrap = document.querySelector('.graph-svg-wrap');
    if(!graphContentSize.w || !wrap) return;
    const pad = 20;
    const kx = (wrap.clientWidth - pad*2) / graphContentSize.w;
    const ky = (wrap.clientHeight - pad*2) / graphContentSize.h;
    const k = Math.max(0.2, Math.min(2, Math.min(kx, ky)));
    graphView.k = k;
    graphView.x = (wrap.clientWidth - graphContentSize.w * k) / 2;
    graphView.y = (wrap.clientHeight - graphContentSize.h * k) / 2;
    applyGraphTransform();
}
function attachPanZoom(svg, wrap){
    if(svg.dataset.panZoomBound) return;
    svg.dataset.panZoomBound = '1';
    // 滚轮缩放（围绕鼠标位置）
    wrap.addEventListener('wheel', e => {
        if(e.target.closest('.popup-panel')) return;
        e.preventDefault();
        const factor = e.deltaY < 0 ? 1.15 : 1/1.15;
        const newK = Math.max(0.2, Math.min(3, graphView.k * factor));
        const rect = wrap.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        graphView.x = mx - (mx - graphView.x) * (newK / graphView.k);
        graphView.y = my - (my - graphView.y) * (newK / graphView.k);
        graphView.k = newK;
        applyGraphTransform();
    }, { passive: false });
    // 鼠标拖动（空白区域）
    svg.addEventListener('mousedown', e => {
        // 只在点击空白处（不是节点 g）才平移
        if(e.target.closest('.gnode')) return;
        e.preventDefault();
        panState = { sx: e.clientX, sy: e.clientY, ox: graphView.x, oy: graphView.y };
        wrap.classList.add('is-panning');
    });
    window.addEventListener('mousemove', e => {
        if(!panState) return;
        graphView.x = panState.ox + (e.clientX - panState.sx);
        graphView.y = panState.oy + (e.clientY - panState.sy);
        applyGraphTransform();
    });
    window.addEventListener('mouseup', () => {
        if(panState){ panState = null; wrap.classList.remove('is-panning'); }
    });
}
let popupNodeId = null;

function openNodePopup(nodeId, gEl){
    popupNodeId = nodeId;
    document.querySelectorAll('.gnode').forEach(g => g.classList.toggle('is-active', g.dataset.nodeId === nodeId));
    const node = currentWorkflow[nodeId];
    if(!node) return;
    const popup = document.getElementById('nodePopup');
    const backdrop = document.getElementById('popupBackdrop');
    const inputs = Object.entries(node.inputs || {}).filter(([k,v]) => {
        return !(Array.isArray(v) && v.length === 2 && typeof v[0] === 'string' && typeof v[1] === 'number');
    });
    const icon = nodeIcon(node);
    const label = nodeLabel(node);
    const sub = nodeSub(node);
    popup.innerHTML = `
        <div class="popup-head">
            <span class="popup-icon">${icon}</span>
            <div style="min-width:0;flex:1">
                <div class="popup-title">${escapeHtml(label)}</div>
                <div class="popup-sub">${escapeHtml(sub)} · #${escapeHtml(nodeId)}</div>
            </div>
            <div class="popup-close" onclick="closeNodePopup()"><i data-lucide="x" class="w-4 h-4"></i></div>
        </div>
        <div class="popup-body">
            ${inputs.length === 0
                ? `<div class="popup-empty">${tr('comfy.noConfigFields')}</div>`
                : inputs.map(([key, value]) => renderInputRow(nodeId, key, value)).join('')}
        </div>
    `;
    // 定位：尽量贴在节点右侧；若超出则放左侧；若上下放不下则居中
    const wrap = document.querySelector('.graph-svg-wrap');
    const wrapRect = wrap.getBoundingClientRect();
    const gRect = gEl.getBoundingClientRect();
    const POP_W = 380;
    const POP_H_MAX = Math.min(wrap.clientHeight - 40, window.innerHeight * 0.7);
    backdrop.style.display = 'block';
    popup.style.display = 'flex';
    popup.style.maxHeight = POP_H_MAX + 'px';
    // 相对 wrap 的坐标（含滚动）
    let left = gRect.right - wrapRect.left + wrap.scrollLeft + 12;
    // 不够位置就放左侧
    if(left + POP_W > wrap.scrollLeft + wrap.clientWidth - 8){
        left = gRect.left - wrapRect.left + wrap.scrollLeft - POP_W - 12;
    }
    if(left < wrap.scrollLeft + 8) left = wrap.scrollLeft + 8;
    let top = gRect.top - wrapRect.top + wrap.scrollTop;
    // 防止溢出底部
    const maxTop = wrap.scrollTop + wrap.clientHeight - POP_H_MAX - 8;
    if(top > maxTop) top = Math.max(wrap.scrollTop + 8, maxTop);
    popup.style.left = left + 'px';
    popup.style.top = top + 'px';
    popup.onwheel = e => e.stopPropagation();
    popup.querySelector('.popup-body')?.addEventListener('wheel', e => e.stopPropagation(), { passive:true });
    refreshIcons();
}

function closeNodePopup(){
    popupNodeId = null;
    document.querySelectorAll('.gnode').forEach(g => g.classList.remove('is-active'));
    document.getElementById('nodePopup').style.display = 'none';
    document.getElementById('popupBackdrop').style.display = 'none';
}

function toggleNodeList(){
    const list = document.getElementById('nodeList');
    const txt = document.getElementById('nodesToggleText');
    const hidden = list.classList.toggle('hidden');
    txt.textContent = hidden ? tr('comfy.showNodeList') : tr('comfy.hideNodeList');
}

// Esc 关闭浮窗
document.addEventListener('keydown', e => {
    if(e.key === 'Escape' && popupNodeId) closeNodePopup();
    if(e.key === 'Escape') closeImagePreview();
});

function renderInputRow(nodeId, inputKey, rawValue){
    const f = fieldFor(nodeId, inputKey);
    const active = !!f;
    const showExtras = active && (f.type === 'slider' || f.type === 'number' || f.type === 'dropdown');
    // 原始值类型徽章
    let valueBadge = '';
    const typeOf = typeof rawValue;
    if(typeOf === 'string'){
        const preview = rawValue.length > 50 ? rawValue.slice(0,50) + '…' : rawValue;
        valueBadge = `<span style="color:var(--muted);font-size:10.5px;font-weight:700">"</span><span style="color:var(--text);font-size:11px;font-weight:700">${escapeHtml(preview)}</span><span style="color:var(--muted);font-size:10.5px;font-weight:700">"</span>`;
    } else if(typeOf === 'number'){
        valueBadge = `<span style="color:#0369a1;font-size:11px;font-weight:800;font-variant-numeric:tabular-nums">${rawValue}</span>`;
    } else if(typeOf === 'boolean'){
        valueBadge = `<span style="color:${rawValue?'#15803d':'#b45309'};font-size:11px;font-weight:800">${rawValue?'✓ true':'✗ false'}</span>`;
    } else {
        valueBadge = `<span style="color:var(--faint);font-size:11px">${escapeHtml(String(rawValue))}</span>`;
    }
    const friendlyName = inputLabel(inputKey);
    const showOriginal = friendlyName !== inputKey;
    return `
        <div class="input-row ${active?'is-active':''} ${showExtras?'has-extras':''}">
            <div class="check-toggle ${active?'checked':''}" onclick="toggleField('${escapeAttr(nodeId)}','${escapeAttr(inputKey)}')">
                ${active ? '<i data-lucide="check" class="w-3 h-3"></i>' : ''}
            </div>
            <div class="input-info">
                <div class="input-key">${escapeHtml(friendlyName)}${showOriginal ? ` <span style="font-size:10px;font-weight:600;color:var(--faint);margin-left:4px">${escapeHtml(inputKey)}</span>` : ''}</div>
                <div class="input-orig">${tr('comfy.defaultValue')}${valueBadge}</div>
            </div>
            <input class="small-input" type="text" placeholder="${tr('comfy.displayName')}" value="${active?escapeAttr(f.name):escapeAttr(friendlyName)}" ${active?'':'disabled'} oninput="updateField('${active?f.id:''}','name',this.value,this)">
            <select class="small-select" ${active?'':'disabled'} onchange="updateField('${active?f.id:''}','type',this.value)">
                ${TYPES.map(t=>`<option value="${t.v}" ${active && f.type===t.v?'selected':''}>${typeLabel(t.v)}</option>`).join('')}
            </select>
            ${active ? renderExtras(f) : ''}
        </div>
    `;
}

function renderExtras(f){
    if(f.type === 'slider' || f.type === 'number'){
        const randomToggle = f.type === 'number'
            ? `<label class="random-toggle" onclick="event.stopPropagation()"><input type="checkbox" ${f.random_enabled === true ? 'checked' : ''} onchange="updateField('${f.id}','random_enabled',this.checked)">随机数</label>`
            : '';
        return `<div class="extras-row">
            <div class="extra-pair">min<input class="small-input" type="number" value="${f.min ?? ''}" oninput="updateField('${f.id}','min',this.value===''?null:parseFloat(this.value),this)"></div>
            <div class="extra-pair">max<input class="small-input" type="number" value="${f.max ?? ''}" oninput="updateField('${f.id}','max',this.value===''?null:parseFloat(this.value),this)"></div>
            <div class="extra-pair">step<input class="small-input" type="number" value="${f.step ?? ''}" oninput="updateField('${f.id}','step',this.value===''?null:parseFloat(this.value),this)"></div>
            <div class="extra-pair">${tr('comfy.defaultValue')}<input class="small-input" type="number" value="${f.default ?? ''}" oninput="updateField('${f.id}','default',this.value===''?null:parseFloat(this.value),this)"></div>
            ${randomToggle}
        </div>`;
    }
    if(f.type === 'dropdown'){
        const opts = f.options || [];
        const fid = escapeAttr(f.id);
        const rows = opts.map((o, i) => {
            const looksNumber = String(o).trim() !== '' && !isNaN(Number(o));
            const tag = looksNumber
                ? '<span class="opt-type-tag is-num">数字</span>'
                : '<span class="opt-type-tag">文本</span>';
            return `
                <div class="dropdown-opt-row">
                    <span class="opt-index">${i + 1}</span>
                    <input class="small-input" type="text" placeholder="选项 ${i + 1}" value="${escapeAttr(o)}"
                        onmousedown="event.stopPropagation()" onclick="event.stopPropagation()"
                        oninput="updateDropdownOption('${fid}', ${i}, this.value, this)">
                    ${tag}
                    <button class="opt-del" type="button" onclick="event.stopPropagation();removeDropdownOption('${fid}', ${i})" title="删除"><i data-lucide="x" class="w-3 h-3"></i></button>
                </div>
            `;
        }).join('');
        return `<div class="extras-row" style="flex-direction:column;align-items:stretch;gap:6px">
            <div style="font-size:11px;color:var(--muted);font-weight:700">
                下拉选项 <span style="color:var(--faint)">· 数字形式自动作为数值传给 ComfyUI</span>
            </div>
            ${rows}
            <button class="ghost-btn" type="button" onclick="event.stopPropagation();addDropdownOption('${fid}')" style="height:34px;padding:0 16px;font-size:12px;font-weight:800;align-self:flex-start;gap:6px"><i data-lucide="plus" class="w-3.5 h-3.5"></i><span>添加选项</span></button>
        </div>`;
    }
    return '';
}
function updateDropdownOption(fieldId, index, value, inputEl){
    const f = currentConfig.fields.find(x => x.id === fieldId); if(!f) return;
    f.options = f.options || [];
    f.options[index] = value;
    // 不重渲浮窗，只更新当前行右侧「数字/文本」标签
    if(inputEl){
        const tag = inputEl.parentElement?.querySelector('.opt-type-tag');
        if(tag){
            const looksNumber = String(value).trim() !== '' && !isNaN(Number(value));
            tag.classList.toggle('is-num', looksNumber);
            tag.textContent = looksNumber ? '数字' : '文本';
        }
    }
    renderPreview();  // 右侧预览的下拉选项实时同步
}
function addDropdownOption(fieldId){
    const f = currentConfig.fields.find(x => x.id === fieldId); if(!f) return;
    f.options = [...(f.options || []), ''];
    renderPreview();
    if(popupNodeId === f.node) refreshPopupBody();
}
function removeDropdownOption(fieldId, index){
    const f = currentConfig.fields.find(x => x.id === fieldId); if(!f) return;
    f.options = (f.options || []).filter((_, i) => i !== index);
    renderPreview();
    if(popupNodeId === f.node) refreshPopupBody();
}

// --- 右侧实时预览 ---
function setPreviewValue(fieldId, value){
    previewValues[fieldId] = value;
    // 更新滑块旁边的数值显示
    const valSpan = document.querySelector(`[data-slider-val="${fieldId}"]`);
    if(valSpan) valSpan.textContent = value;
}
function togglePreviewBoolean(fieldId, track){
    const next = !track.classList.contains('on');
    setPreviewValue(fieldId, next);
    track.classList.toggle('on', next);
    track.setAttribute('aria-checked', String(next));
}
function randomValueForField(f){
    const isFloat = Number(f.step) > 0 && Number(f.step) < 1;
    let min = Number.isFinite(Number(f.min)) ? Number(f.min) : null;
    let max = Number.isFinite(Number(f.max)) ? Number(f.max) : null;
    const name = `${f.input || ''} ${f.name || ''}`.toLowerCase();
    const looksSeed = name.includes('seed') || name.includes('noise') || name.includes('随机') || name.includes('噪');
    if(min === null) min = looksSeed ? 1 : 0;
    if(max === null || max <= min) max = looksSeed ? 1000000000000000 : 999999;
    let value = min + Math.random() * (max - min);
    if(isFloat){
        const precision = Math.min(8, Math.max(1, String(f.step).split('.')[1]?.length || 2));
        value = Number(value.toFixed(precision));
    } else {
        value = Math.floor(value);
    }
    return value;
}

function fieldSupportsRandom(f){
    return !!f && f.type === 'number' && f.random_enabled === true;
}

function isPreviewRandomActive(fieldId){
    return previewRandomActive[fieldId] !== false;
}

function randomButtonHtml(f){
    if(!fieldSupportsRandom(f)) return '';
    const active = isPreviewRandomActive(f.id);
    const title = active ? '随机已开启，点击关闭' : '随机已关闭，点击开启';
    return `<button class="random-btn ${active ? 'active' : ''}" type="button" onclick="togglePreviewRandom('${f.id}')" title="${title}"><i data-lucide="dice-5" class="w-4 h-4"></i></button>`;
}

function togglePreviewRandom(fieldId){
    const f = currentConfig?.fields?.find(x => x.id === fieldId);
    if(!fieldSupportsRandom(f)) return;
    previewRandomActive[fieldId] = !isPreviewRandomActive(fieldId);
    renderPreview();
    if(workspaceMode === 'canvas') renderMiniCanvasPreview(miniCanvasHost, true);
}

function applyActiveRandomValues(fields){
    const out = {...fields};
    currentConfig?.fields?.forEach(f => {
        if(fieldSupportsRandom(f) && isPreviewRandomActive(f.id)){
            const value = randomValueForField(f);
            out[f.id] = value;
            previewValues[f.id] = value;
        }
    });
    return out;
}

function openImagePreview(url){
    const box = document.getElementById('imageLightbox');
    const img = document.getElementById('imageLightboxImg');
    if(!box || !img || !url) return;
    img.src = url;
    box.classList.add('open');
}

function closeImagePreview(){
    const box = document.getElementById('imageLightbox');
    const img = document.getElementById('imageLightboxImg');
    if(box) box.classList.remove('open');
    if(img) img.src = '';
}

function renderPreview(){
    const fields = currentConfig?.fields || [];
    if(!fields.length){
        previewCard.innerHTML = `<div class="preview-empty">${tr('comfy.previewEmpty')}</div>`;
        return;
    }
    const fieldsHtml = fields.map(f => renderPreviewField(f)).join('');
    const resultHtml = runResult
        ? `<div class="run-result"><img src="${escapeAttr(runResult)}" onclick="openImagePreview('${escapeAttr(runResult)}')"><div class="run-status">${tr('comfy.runSuccess')}</div></div>`
        : '';
    const runButton = `<button id="runBtn" class="run-btn" type="button" onclick="onRun()">
            <i data-lucide="play" class="w-4 h-4"></i><span>${tr('comfy.runTest')}</span>
        </button>`;
    previewCard.innerHTML = `
        ${fieldsHtml}
        ${runButton}
        ${resultHtml}
    `;
    refreshIcons();
}

function renderPreviewField(f){
    const fieldLabel = String(f.name || f.input || '参数');
    const label = `<div class="pfield-label">${escapeHtml(fieldLabel)}</div>`;
    const accessibleLabel = `aria-label="${escapeAttr(fieldLabel)}"`;
    const v = previewValues[f.id] ?? f.default ?? (f.type==='boolean'?false:(f.type==='number'||f.type==='slider'?0:''));
    if(f.type === 'textarea'){
        return `<div class="pfield">${label}<textarea class="pfield-textarea" ${accessibleLabel} oninput="setPreviewValue('${f.id}',this.value)">${escapeHtml(v)}</textarea></div>`;
    }
    if(f.type === 'number'){
        const randomBtn = randomButtonHtml(f);
        return `<div class="pfield">${label}<div class="pfield-random-row" style="${randomBtn ? '' : 'grid-template-columns:1fr'}"><input class="pfield-input" type="number" ${accessibleLabel} value="${escapeAttr(v)}" oninput="setPreviewValue('${f.id}',parseFloat(this.value)||0)">${randomBtn}</div></div>`;
    }
    if(f.type === 'slider'){
        const min = f.min ?? 0, max = f.max ?? 10, step = f.step ?? 1;
        return `<div class="pfield">${label}<div class="pfield-random-row" style="grid-template-columns:1fr"><div class="pfield-slider">
            <input type="range" ${accessibleLabel} min="${min}" max="${max}" step="${step}" value="${escapeAttr(v)}" oninput="setPreviewValue('${f.id}',parseFloat(this.value))">
            <span class="pfield-slider-val" data-slider-val="${f.id}">${v}</span>
        </div></div></div>`;
    }
    if(f.type === 'dropdown'){
        const opts = (f.options || []).map(o => `<option value="${escapeAttr(o)}" ${String(v)===String(o)?'selected':''}>${escapeHtml(o)}</option>`).join('');
        return `<div class="pfield">${label}<select class="pfield-select" ${accessibleLabel} onchange="setPreviewValue('${f.id}',this.value)">${opts || `<option value="">${tr('comfy.noOptions')}</option>`}</select></div>`;
    }
    if(isMediaField(f)){
        // 浏览器显示用本地 blob URL；如果没有就尝试用 /output/ 之类的可访问 URL；都没有显示占位文字
        const displayUrl = previewImageUrls[f.id] || (typeof v === 'string' && /^(\/|https?:|blob:|data:)/.test(v) ? v : '');
        return `<div class="pfield">${label}<div class="pfield-image-drop ${displayUrl?'has-image':''}" role="button" tabindex="0" ${accessibleLabel} onclick="pickImage('${f.id}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();this.click()}">
            ${mediaPreviewHtml(fieldKind(f), displayUrl, v)}
        </div></div>`;
    }
    if(f.type === 'boolean'){
        return `<div class="pfield">${label}<div class="pfield-bool">
            <div class="pfield-bool-track ${v?'on':''}" role="switch" tabindex="0" aria-checked="${Boolean(v)}" ${accessibleLabel} onclick="togglePreviewBoolean('${f.id}',this)" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();this.click()}">
                <div class="pfield-bool-thumb"></div>
            </div>
        </div></div>`;
    }
    return `<div class="pfield">${label}<input class="pfield-input" type="text" ${accessibleLabel} value="${escapeAttr(v)}" oninput="setPreviewValue('${f.id}',this.value)"></div>`;
}

function miniCardStyle(key){
    const p = miniCards[key] || defaultMiniCards()[key] || {x:0,y:0};
    return `left:${p.x}px;top:${p.y}px`;
}

function miniLine(aKey, bKey){
    const a = miniCards[aKey] || defaultMiniCards()[aKey];
    const b = miniCards[bKey] || defaultMiniCards()[bKey];
    const x1 = a.x + 210, y1 = a.y + 70, x2 = b.x, y2 = b.y + 70;
    const dx = x2 - x1, dy = y2 - y1;
    const len = Math.sqrt(dx*dx + dy*dy);
    const deg = Math.atan2(dy, dx) * 180 / Math.PI;
    return `<div class="mini-line" style="left:${x1}px;top:${y1}px;width:${len}px;transform:rotate(${deg}deg)"></div>`;
}

function renderWorkspaceView(){
    const graphWrap = document.querySelector('.graph-svg-wrap');
    const nodesToggle = document.getElementById('nodesToggle');
    document.getElementById('workspaceGraphTab')?.classList.toggle('active', workspaceMode === 'graph');
    document.getElementById('workspaceCanvasTab')?.classList.toggle('active', workspaceMode === 'canvas');
    if(!currentWorkflow){
        if(graphWrap) graphWrap.style.display = 'none';
        if(miniCanvasHost) miniCanvasHost.style.display = 'none';
        return;
    }
    if(workspaceMode === 'canvas'){
        if(graphWrap) graphWrap.style.display = 'none';
        if(nodesToggle) nodesToggle.style.display = 'none';
        renderMiniCanvasPreview(miniCanvasHost, true);
    } else {
        if(graphWrap) graphWrap.style.display = 'block';
        if(miniCanvasHost) miniCanvasHost.style.display = 'none';
        if(nodesToggle) nodesToggle.style.display = 'flex';
    }
}

function renderMiniCanvasPreview(target = previewCard, large = false){
    if(!target) return;
    const promptFields = currentConfig.fields.filter(f => fieldKind(f) === 'prompt');
    const imageFields = currentConfig.fields.filter(f => fieldKind(f) === 'image');
    const videoFields = currentConfig.fields.filter(f => fieldKind(f) === 'video');
    const audioFields = currentConfig.fields.filter(f => fieldKind(f) === 'audio');
    const settingFields = currentConfig.fields.filter(f => fieldKind(f) === 'setting');
    const prompts = miniTestNodes.filter(n => n.type === 'prompt');
    const mediaNodes = miniTestNodes.filter(n => ['image','video','audio'].includes(n.type));
    const comfy = miniTestNodes.find(n => n.type === 'comfy') || defaultMiniTestNodes().find(n => n.type === 'comfy');
    const output = miniTestNodes.find(n => n.type === 'output') || defaultMiniTestNodes().find(n => n.type === 'output');
    const resultHtml = runResult
        ? `<div class="mini-result"><img src="${escapeAttr(runResult)}" onclick="openImagePreview('${escapeAttr(runResult)}')"><div class="run-status">${tr('comfy.runSuccess')}</div></div>`
        : `<div class="preview-empty" style="padding:18px 10px">${tr('comfy.resultHere')}</div>`;
    target.style.display = 'block';
    target.innerHTML = `
        <div id="miniCanvas" class="mini-canvas ${large ? 'large' : ''}">
            <div class="mini-toolbar">
                <button class="mini-tool" type="button" onclick="addMiniNode('prompt')"><i data-lucide="text-cursor-input" class="w-3.5 h-3.5"></i>${tr('comfy.addPrompt')}</button>
                <button class="mini-tool" type="button" onclick="addMiniNode('image')"><i data-lucide="image-plus" class="w-3.5 h-3.5"></i>${tr('comfy.addImage')}</button>
                <button class="mini-tool" type="button" onclick="addMiniNode('video')"><i data-lucide="file-video" class="w-3.5 h-3.5"></i>${typeLabel('video')}</button>
                <button class="mini-tool" type="button" onclick="addMiniNode('audio')"><i data-lucide="file-audio" class="w-3.5 h-3.5"></i>${typeLabel('audio')}</button>
            </div>
            <div id="miniWorld" class="mini-world" style="transform:translate(${miniView.x}px,${miniView.y}px) scale(${miniView.k})">
                ${[...prompts, ...mediaNodes].map(n => miniLineBetween(n, comfy)).join('')}
                ${miniLineBetween(comfy, output)}
                ${prompts.map((n,i) => `
                    <div class="mini-card" data-node="${n.id}" style="left:${n.x}px;top:${n.y}px">
                        <span class="mini-port out"></span>
                        <div class="mini-card-head"><i data-lucide="text-cursor-input" class="w-3.5 h-3.5"></i><span class="mini-node-title">${tr('comfy.promptNode')} ${i+1}</span>${miniDeleteButton(n)}</div>
                        <div class="mini-card-body"><textarea class="mini-textarea" oninput="updateMiniNode('${n.id}','text',this.value)" placeholder="${escapeAttr(tr('comfy.promptPlaceholder'))}">${escapeHtml(n.text || '')}</textarea></div>
                    </div>`).join('')}
                ${mediaNodes.map((n,i) => `
                    <div class="mini-card" data-node="${n.id}" style="left:${n.x}px;top:${n.y}px">
                        <span class="mini-port out"></span>
                        <div class="mini-card-head"><i data-lucide="${n.type === 'video' ? 'file-video' : n.type === 'audio' ? 'file-audio' : 'image'}" class="w-3.5 h-3.5"></i><span class="mini-node-title">${typeLabel(n.type)} ${i+1}</span>${miniDeleteButton(n)}</div>
                        <div class="mini-card-body"><div class="mini-image-drop" onclick="pickMiniImage('${n.id}')">${mediaPreviewHtml(n.type, n.url, n.name || n.value, true)}</div></div>
                    </div>`).join('')}
                <div class="mini-card comfy-card" data-node="${comfy.id}" style="left:${comfy.x}px;top:${comfy.y}px">
                    <span class="mini-port in"></span><span class="mini-port out"></span>
                    <div class="mini-card-head"><i data-lucide="workflow" class="w-3.5 h-3.5"></i><span class="mini-node-title">${escapeHtml(currentConfig.title || selectedName.replace('.json',''))} · ${tr('canvas.comfyCustom')}</span></div>
                    <div class="mini-card-body">
                        <div class="text-[10px] font-black uppercase" style="color:var(--faint)">${tr('comfy.inputs')}</div>
                        <div class="preview-empty" style="padding:10px;font-size:11px;text-align:left">
                            ${mediaFieldLabel('image', imageFields.length)} · ${mediaFieldLabel('video', videoFields.length)} · ${mediaFieldLabel('audio', audioFields.length)} · ${promptFields.length ? tr('comfy.acceptsPrompt') : tr('comfy.noPromptField')}
                        </div>
                        <div class="mini-settings-list">
                            ${settingFields.length ? settingFields.map(f => renderMiniField(f)).join('') : `<div class="preview-empty" style="padding:16px 10px">${tr('comfy.otherParamsHere')}</div>`}
                        </div>
                        <button id="runBtn" class="run-btn mini-run" type="button" onclick="onRun()">
                            <i data-lucide="play" class="w-4 h-4"></i><span>${tr('comfy.runTest')}</span>
                        </button>
                    </div>
                </div>
                <div class="mini-card" data-node="${output.id}" style="left:${output.x}px;top:${output.y}px">
                    <span class="mini-port in"></span>
                    <div class="mini-card-head"><i data-lucide="circle-dot" class="w-3.5 h-3.5"></i><span>${tr('comfy.output')}</span></div>
                    <div class="mini-card-body">${resultHtml}</div>
                </div>
            </div>
        </div>
    `;
    bindMiniCanvas();
    refreshIcons();
}

function renderMiniField(f){
    const label = `<div class="pfield-label">${escapeHtml(f.name || f.input)}</div>`;
    const v = previewValues[f.id] ?? f.default ?? (f.type==='boolean'?false:(f.type==='number'||f.type==='slider'?0:''));
    if(isMediaField(f)){
        const displayUrl = previewImageUrls[f.id] || (typeof v === 'string' && /^(\/|https?:|blob:|data:)/.test(v) ? v : '');
        return `<div class="pfield">${label}<div class="mini-image-drop" onclick="pickImage('${f.id}')">${mediaPreviewHtml(fieldKind(f), displayUrl, v, true)}</div></div>`;
    }
    if(f.type === 'textarea'){
        return `<div class="pfield">${label}<textarea class="mini-textarea" oninput="setPreviewValue('${f.id}',this.value)">${escapeHtml(v)}</textarea></div>`;
    }
    if(f.type === 'number'){
        const randomBtn = randomButtonHtml(f);
        return `<div class="pfield">${label}<div class="pfield-random-row" style="${randomBtn ? '' : 'grid-template-columns:1fr'}"><input class="mini-input" type="number" value="${escapeAttr(v)}" oninput="setPreviewValue('${f.id}',parseFloat(this.value)||0)">${randomBtn}</div></div>`;
    }
    if(f.type === 'slider'){
        const min = f.min ?? 0, max = f.max ?? 10, step = f.step ?? 1;
        return `<div class="pfield">${label}<div class="pfield-random-row" style="grid-template-columns:1fr"><div class="pfield-slider">
            <input type="range" min="${min}" max="${max}" step="${step}" value="${escapeAttr(v)}" oninput="setPreviewValue('${f.id}',parseFloat(this.value))">
            <span class="pfield-slider-val" data-slider-val="${f.id}">${v}</span>
        </div></div></div>`;
    }
    if(f.type === 'dropdown'){
        const opts = (f.options || []).map(o => `<option value="${escapeAttr(o)}" ${String(v)===String(o)?'selected':''}>${escapeHtml(o)}</option>`).join('');
        return `<div class="pfield">${label}<select class="pfield-select" onchange="setPreviewValue('${f.id}',this.value)">${opts || `<option value="">${tr('comfy.noOptions')}</option>`}</select></div>`;
    }
    if(f.type === 'boolean'){
        return `<div class="pfield">${label}<div class="pfield-bool"><div class="pfield-bool-track ${v?'on':''}" onclick="setPreviewValue('${f.id}',!${!!v});this.classList.toggle('on')"><div class="pfield-bool-thumb"></div></div></div></div>`;
    }
    return `<div class="pfield">${label}<input class="mini-input" type="text" value="${escapeAttr(v)}" oninput="setPreviewValue('${f.id}',this.value)"></div>`;
}

function miniDeleteButton(node){
    return ['prompt','image'].includes(node.type) ? `<button class="mini-delete" type="button" onclick="removeMiniNode('${node.id}')" title="${escapeAttr(tr('common.delete'))}"><i data-lucide="x" class="w-3 h-3"></i></button>` : '';
}

function miniLineBetween(a, b){
    if(!a || !b) return '';
    const x1 = a.x + 230, y1 = a.y + 72, x2 = b.x, y2 = b.y + 72;
    const dx = x2 - x1, dy = y2 - y1;
    const len = Math.sqrt(dx*dx + dy*dy);
    const deg = Math.atan2(dy, dx) * 180 / Math.PI;
    return `<div class="mini-line" style="left:${x1}px;top:${y1}px;width:${len}px;transform:rotate(${deg}deg)"></div>`;
}

function addMiniNode(type){
    const count = miniTestNodes.filter(n => n.type === type).length;
    miniTestNodes.push(createMiniNode(type, count));
    persistMiniTestNodes();
    renderWorkspaceView();
}

function removeMiniNode(id){
    miniTestNodes = miniTestNodes.filter(n => n.id !== id);
    persistMiniTestNodes();
    renderWorkspaceView();
}

function updateMiniNode(id, key, value){
    const node = miniTestNodes.find(n => n.id === id);
    if(node) node[key] = value;
    persistMiniTestNodes();
}

async function pickMiniImage(nodeId){
    const input = document.createElement('input');
    input.type = 'file';
    const node = miniTestNodes.find(n => n.id === nodeId);
    input.accept = mediaAccept(node?.type || 'image');
    input.onchange = async () => {
        const file = input.files[0];
        if(!file) return;
        if(!node) return;
        if(node.url && node.url.startsWith('blob:')) URL.revokeObjectURL(node.url);
        node.url = URL.createObjectURL(file);
        node.name = file.name;
        persistMiniTestNodes();
        renderWorkspaceView();
        const form = new FormData();
        form.append('files', file);
        try {
            const data = await fetch('/api/upload', { method:'POST', body:form }).then(r=>r.json());
            node.value = data.files?.[0]?.comfy_name || data.files?.[0]?.filename || file.name;
            persistMiniTestNodes();
        } catch(e){ alert(mediaUploadFailedText(node.type)); }
    };
    input.click();
}

function bindMiniCanvas(){
    const canvas = document.getElementById('miniCanvas');
    const world = document.getElementById('miniWorld');
    if(!canvas || !world) return;
    const sync = () => { world.style.transform = `translate(${miniView.x}px,${miniView.y}px) scale(${miniView.k})`; };
    canvas.onwheel = e => {
        e.preventDefault();
        const old = miniView.k;
        const next = Math.max(0.45, Math.min(1.8, old * (e.deltaY > 0 ? 0.9 : 1.1)));
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left, my = e.clientY - rect.top;
        miniView.x = mx - (mx - miniView.x) * (next / old);
        miniView.y = my - (my - miniView.y) * (next / old);
        miniView.k = next;
        sync();
    };
    canvas.onmousedown = e => {
        if(e.target.closest('textarea,input,select,button,.mini-image-drop')) return;
        const card = e.target.closest('.mini-card');
        if(card && e.target.closest('.mini-card-head')){
            const id = card.dataset.node || card.dataset.card;
            const node = miniTestNodes.find(n => n.id === id);
            const pos = node || miniCards[id] || defaultMiniCards()[id];
            miniDrag = { type:'card', id, sx:e.clientX, sy:e.clientY, ox:pos.x, oy:pos.y };
        } else {
            miniDrag = { type:'pan', sx:e.clientX, sy:e.clientY, ox:miniView.x, oy:miniView.y };
            canvas.classList.add('is-panning');
        }
    };
    window.onmousemove = e => {
        if(!miniDrag) return;
        if(miniDrag.type === 'pan'){
            miniView.x = miniDrag.ox + e.clientX - miniDrag.sx;
            miniView.y = miniDrag.oy + e.clientY - miniDrag.sy;
            sync();
        } else {
            const dx = (e.clientX - miniDrag.sx) / miniView.k;
            const dy = (e.clientY - miniDrag.sy) / miniView.k;
            const node = miniTestNodes.find(n => n.id === miniDrag.id);
            if(node){
                node.x = miniDrag.ox + dx;
                node.y = miniDrag.oy + dy;
                persistMiniTestNodes();
            } else {
                miniCards[miniDrag.id] = { x: miniDrag.ox + dx, y: miniDrag.oy + dy };
                currentConfig.mini_cards = miniCards;
            }
            const card = world.querySelector(`[data-node="${miniDrag.id}"],[data-card="${miniDrag.id}"]`);
            if(card){
                const p = node || miniCards[miniDrag.id];
                card.style.left = `${p.x}px`;
                card.style.top = `${p.y}px`;
            }
        }
    };
    window.onmouseup = () => {
        if(miniDrag?.type === 'pan') canvas.classList.remove('is-panning');
        const shouldRefresh = miniDrag?.type === 'card';
        miniDrag = null;
        if(shouldRefresh) renderWorkspaceView();
    };
}

async function pickImage(fieldId){
    const input = document.createElement('input');
    input.type = 'file';
    const field = currentConfig.fields.find(f => f.id === fieldId);
    const kind = fieldKind(field || {type:'image'});
    input.accept = mediaAccept(kind);
    input.onchange = async () => {
        const file = input.files[0];
        if(!file) return;
        // 先用本地 blob URL 立即显示缩略图
        if(previewImageUrls[fieldId]) URL.revokeObjectURL(previewImageUrls[fieldId]);
        previewImageUrls[fieldId] = URL.createObjectURL(file);
        renderPreview();
        // 再上传到 ComfyUI 拿到 comfy_name 作为运行时的实际值
        const form = new FormData();
        form.append('files', file);
        try {
            const data = await fetch('/api/upload', { method:'POST', body:form }).then(r=>r.json());
            const filename = data.files?.[0]?.comfy_name || data.files?.[0]?.filename || file.name;
            previewValues[fieldId] = filename;
        } catch(e){ alert(mediaUploadFailedText(kind)); }
    };
    input.click();
}

async function onRun(){
    if(!selectedName || !currentConfig) return;
    const btn = document.getElementById('runBtn');
    if(btn){ btn.disabled = true; btn.querySelector('span').textContent = tr('comfy.runningTest'); }
    setStatus(tr('comfy.runningTest'));
    try {
        const baseFields = workspaceMode === 'canvas' ? fieldsFromMiniCanvas() : {...previewValues};
        const runFields = applyActiveRandomValues(baseFields);
        const res = await fetch(`/api/workflows/${encodeURIComponent(selectedName)}/run`, {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            // async: 后端只入队就返回 job_id，HTTP 不再挂到工作流跑完（以前会卡到 3600 秒）
            body:JSON.stringify({ fields:runFields, config:currentConfig, client_id:'workflow-test', async:true })
        });
        if(!res.ok) throw new Error((await res.json()).detail || tr('comfy.runFailed'));
        const accepted = await res.json();
        const job = accepted?.async === false ? accepted : await waitForComfyTestJob(accepted?.job_id);
        if(job?.status === 'cancelled') throw new Error(tr('comfy.runFailed'));
        if(job?.status === 'error') throw new Error(job.error || tr('comfy.runFailed'));
        runResult = job?.images?.[0] || null;
        renderPreview();
        renderWorkspaceView();
        setStatus(tr('comfy.runSuccess'));
    } catch(e){
        alert(e.message || tr('comfy.runFailed'));
        setStatus(tr('comfy.runFailed'));
    } finally {
        if(btn){ btn.disabled = false; btn.querySelector('span').textContent = tr('comfy.runTest'); }
    }
}

// 轮询等待入队后的任务。任务在后端统一队列里排着，这里只问状态，
// 不再像以前那样让「运行测试」这一个 HTTP 请求挂到工作流跑完。
async function waitForComfyTestJob(jobId){
    if(!jobId) throw new Error(tr('comfy.runFailed'));
    const deadline = Date.now() + 3600 * 1000;
    let lastLabel = '';
    while(Date.now() < deadline){
        const res = await fetch(`/api/comfyui/jobs/${encodeURIComponent(jobId)}`, { cache:'no-store' }).catch(() => null);
        if(res && res.status === 404) throw new Error(tr('comfy.runFailed'));  // 任务记录已丢（后端重启过）
        if(!res || !res.ok) throw new Error(tr('comfy.runFailed'));
        const job = await res.json();
        if(job.status === 'done' || job.status === 'error' || job.status === 'cancelled') return job;
        const pos = Number(job.queue_position || 0);
        const label = pos > 0
            ? tr('comfy.queuedAt').replace('N', String(pos))
            : (Number(job.progress || 0) > 0 ? tr('comfy.runningPercent').replace('N', String(job.progress)) : tr('comfy.runningTest'));
        if(label !== lastLabel){ setStatus(label); lastLabel = label; }
        await new Promise(r => setTimeout(r, 1000));
    }
    throw new Error(tr('comfy.runFailed'));
}

function fieldsFromMiniCanvas(){
    syncMiniTestNodes();
    const fields = {...previewValues};
    const mediaKinds = ['image','video','audio'];
    const promptFields = currentConfig.fields.filter(f => fieldKind(f) === 'prompt');
    const prompt = miniTestNodes.filter(n => n.type === 'prompt').map(n => n.text || '').filter(Boolean).join('\n\n');
    mediaKinds.forEach(kind => {
        const mediaFields = currentConfig.fields.filter(f => fieldKind(f) === kind);
        const mediaNodes = miniTestNodes.filter(n => n.type === kind && n.value);
        mediaFields.forEach((f, i) => {
            fields[f.id] = mediaNodes[i]?.value || fields[f.id] || '';
        });
    });
    promptFields.forEach(f => {
        fields[f.id] = prompt || fields[f.id] || '';
    });
    return fields;
}

async function onUpload(event){
    const file = event.target.files[0];
    if(!file) return;
    event.target.value = '';
    try {
        const text = await file.text();
        let workflow;
        try { workflow = JSON.parse(text); }
        catch { alert(tr('comfy.invalidJson')); return; }
        const baseName = file.name.replace(/\.json$/i, '');
        const inputName = prompt(tr('comfy.namePrompt'), baseName);
        if(!inputName) return;
        const safeName = buildSafeComfyWorkflowFileName(inputName);
        const data = await fetch('/api/workflows', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({ name:safeName, workflow })
        });
        const result = await data.json();
        if(!data.ok) throw new Error(result.detail || tr('comfy.uploadFailed'));
        clearComfyWorkflowFetchCache(result.name);
        rememberComfyWorkflow(resolveComfyWorkflowName(result.name), inputName, {builtin:false});
        await loadList();
        selectWorkflow(resolveComfyWorkflowName(result.name));
        setStatus(tr('comfy.uploaded') + result.name);
        new BroadcastChannel('studio-api').postMessage({ type: 'workflows-changed' });
    } catch(e){ alert(e.message || tr('comfy.uploadFailed')); }
}

async function onSave(){
    if(!selectedName || !currentConfig) return;
    // 校验
    for(const f of currentConfig.fields){
        if(!f.name || !f.name.trim()){
            alert(tf('comfy.saveMissingName', {field:f.input})); return;
        }
    }
    setStatus(tr('comfy.saving'));
    try {
        const res = await fetch(`/api/workflows/${encodeURIComponent(selectedName)}/config`, {
            method:'PUT',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify(currentConfig)
        });
        if(!res.ok) throw new Error((await res.json()).detail || tr('comfy.saveFailed'));
        clearComfyWorkflowFetchCache(selectedName);
        const savedName = await saveComfyWorkflowConfigAndFile(currentConfig, selectedName);
        rememberComfyWorkflow(savedName, currentConfig.title || savedName.replace('.json',''), {field_count:(currentConfig.fields || []).length, builtin:isBuiltin});
        setStatus(savedName !== selectedName ? (tr('comfy.saved') + ' · ' + savedName) : tr('comfy.saved'));
        await loadList();
        new BroadcastChannel('studio-api').postMessage({ type: 'workflows-changed' });
    } catch(e){ alert(e.message || tr('comfy.saveFailed')); setStatus(tr('comfy.saveFailed')); }
}

// 保存配置时顺手把后端文件名也同步成显示名，省掉单独的「同步文件名」按钮。
// 返回最终生效的文件名；改名失败只提示不阻断（配置本身已经存下去了）。
async function saveComfyWorkflowConfigAndFile(config, name){
    const renamed = await renameComfyWorkflowFileIfNeeded(config, name);
    if(renamed){
        selectedName = renamed;
        // 只刷新列表和标题，不走 selectWorkflow（那会重置预览/节点选中态）
        renderList();
        if(workflowTitleInput) workflowTitleInput.value = config.title || renamed.replace('.json','');
    }
    return renamed || name;
}

async function renameComfyWorkflowFileIfNeeded(config, name){
    if(isBuiltin) return '';
    const base = String(config?.title || '').replace(/\.json$/i, '').trim();
    const oldBase = String(name || '').replace(/\.json$/i, '').trim();
    if(!base || base === oldBase) return '';
    try {
        const res = await fetch(`/api/workflows/${encodeURIComponent(name)}/rename`, {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({name: base})
        });
        const data = await res.json().catch(() => ({}));
        if(!res.ok) throw new Error(data.detail || '改名失败');
        clearComfyWorkflowFetchCache(name);
        const nextName = data.name || (base + '.json');
        if(nextName !== name) new BroadcastChannel('studio-api').postMessage({ type: 'workflows-changed' });
        return nextName;
    } catch(e){
        const msg = String(e?.message || '改名失败');
        alert(/not found|404/i.test(msg)
            ? '配置已保存，但文件名没同步：后端还没加载这个功能（改了后端 Python 必须重启软件）。'
            : ('配置已保存，但文件名同步失败：' + msg));
        return '';
    }
}

async function onDelete(){
    if(!selectedName || isBuiltin) return;
    if(!confirm(tf('comfy.deleteConfirm', {name: currentConfig.title || selectedName}))) return;
    try {
        const res = await fetch(`/api/workflows/${encodeURIComponent(selectedName)}`, { method:'DELETE' });
        if(!res.ok) throw new Error((await res.json()).detail || tr('comfy.deleteFailed'));
        removeKnownComfyWorkflow(selectedName);
        selectedName = '';
        currentWorkflow = null;
        currentConfig = null;
        renderEditor();
        renderPreview();
        renderWorkspaceView();
        await loadList();
        new BroadcastChannel('studio-api').postMessage({ type: 'workflows-changed' });
    } catch(e){ alert(e.message || tr('comfy.deleteFailed')); }
}

window.addEventListener('message', event => {
    if(event.data?.type === 'studio-theme' && window.StudioTheme) window.StudioTheme.set(event.data.theme);
    if(event.data?.type === 'studio-lang' && window.StudioI18n) window.StudioI18n.set(event.data.lang);
});
window.addEventListener('studio-lang-change', refreshLanguageView);

document.addEventListener('DOMContentLoaded', () => {
    refreshIcons();
    if(window.StudioI18n) StudioI18n.apply();
    loadList();
    loadComfyInstances();
});

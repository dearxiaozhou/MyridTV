//** Video/RH-official parameter controls and Comfy workflow resolution helpers. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    function D(name){return typeof deps[name] === 'function' ? deps[name]() : deps[name];}

function renderVideoTrustedAssetControl() {
    return CanvasParamControls.renderVideoTrustedAssetControl.apply(null, arguments);
}
function renderVideoExtendDirectionControl() {
    return CanvasParamControls.renderVideoExtendDirectionControl.apply(null, arguments);
}
function optionHtml(value, label, selected) {
    return CanvasSpecControls.optionHtml.apply(null, arguments);
}
function parseSizeValue(value){
    const match = String(value || '').trim().match(/^(\d+)\s*[xX*]\s*(\d+)$/);
    return match ? {width:match[1], height:match[2]} : null;
}
function parseRatioValue(value){
    const raw = String(value || '').trim();
    const parts = raw.includes(':') ? raw.split(':') : raw.split(/[xX*]/);
    if(parts.length !== 2) return 0;
    const w = Number(parts[0]);
    const h = Number(parts[1]);
    return w > 0 && h > 0 ? w / h : 0;
}
function apiImageSize(ratioValue, resolutionValue, customRatioValue='', customSizeValue=''){
    if(resolutionValue === 'custom') return String(customSizeValue || '').trim();
    const resolutionKey = resolutionValue || '1k';
    if(ratioValue === 'custom' || ratioValue === 'source'){
        const parsed = parseRatioValue(customRatioValue);
        const longSide = D("RES_LONG_SIDE")[resolutionKey] || 1024;
        if(parsed){
            const pixelLimit = D("RES_PIXEL_LIMIT")[resolutionKey] || (longSide * longSide);
            const rawWidth = parsed >= 1 ? longSide : Math.min(longSide * parsed, Math.sqrt(pixelLimit * parsed));
            const rawHeight = parsed >= 1 ? Math.min(longSide / parsed, Math.sqrt(pixelLimit / parsed)) : longSide;
            const width = Math.floor(rawWidth / 16) * 16;
            const height = Math.floor(rawHeight / 16) * 16;
            return `${Math.max(64, width)}x${Math.max(64, height)}`;
        }
    }
    const ratioKey = ratioValue && D("SIZE_MAP")[ratioValue] ? ratioValue : 'square';
    return D("SIZE_MAP")[ratioKey]?.[resolutionKey] || D("SIZE_MAP").square[resolutionKey] || D("SIZE_MAP").square['1k'];
}
function rhOfficialNormalizeModel(model){
    return String(model || '').trim().replace('rhart-image-g-2-offcial', 'rhart-image-g-2-official');
}
function rhOfficialModelForRun(model, refs){
    const clean = rhOfficialNormalizeModel(model);
    if(deps.imageRefsOnly(refs || []).length && clean === 'rhart-image-g-2-official/text-to-image') return 'rhart-image-g-2-official/image-to-image';
    return clean;
}
function shouldUseRhOfficialProxy(payload){
    const model = rhOfficialNormalizeModel(payload?.model);
    if(model === 'blender-previz' || payload?.provider_id === 'blender') return true;
    return model.startsWith('rhart-image-g-2/') || model.startsWith('rhart-image-g-2/official/')
        || model.startsWith('rhart-image-g-2.5/') || model.startsWith('rhart-image-g-2.5/official/');
}
function rhOfficialResolutionForRun(sourceSettings=D("settings")){
    const value = String(sourceSettings?.resolution || '1k').trim().toLowerCase();
    return ['1k','2k','4k','8k'].includes(value) ? value : '1k';
}
function rhOfficialAspectRatioForRun(sourceSettings=D("settings")){
    const ratioKey = String(sourceSettings?.ratio || 'square').trim();
    const mapped = {
        square:'1:1',
        landscape:'3:2',
        portrait:'2:3',
        landscape43:'4:3',
        portrait43:'3:4',
        wide:'16:9',
        story:'9:16',
        ultrawide:'21:9',
        ultratall:'9:21'
    };
    if(mapped[ratioKey]) return mapped[ratioKey];
    const custom = String(sourceSettings?.customRatio || '').trim();
    if(/^\d+\s*:\s*\d+$/.test(custom)) return custom.replace(/\s+/g, '');
    const size = parseSizeValue(sourceSettings?.customSize || '');
    if(size){
        const w = Number(size.width);
        const h = Number(size.height);
        if(w > 0 && h > 0){
            const gcd = (a, b) => b ? gcd(b, a % b) : a;
            const g = gcd(w, h);
            return `${Math.round(w / g)}:${Math.round(h / g)}`;
        }
    }
    return '1:1';
}
function normalizeApiSizeSettings(prefix=''){
    const ratioKey = prefix ? `${prefix}Ratio` : 'ratio';
    const resKey = prefix ? `${prefix}Resolution` : 'resolution';
}
async function ensureComfyWorkflow(name){
    return CanvasComfyJobEngine.ensureComfyWorkflow(name);
}
function currentComfyWorkflowData(){
    const name = deps.resolveComfyWorkflowName(D("settings").comfyWorkflow || D("comfyWorkflows")[0]?.name || '');
    return name ? (D("comfyWorkflowCache")[name] || null) : null;
}
function currentComfyFields(){
    return currentComfyWorkflowData()?.config?.fields || [];
}
function comfyFieldMeta(field, workflowData=currentComfyWorkflowData()){
    const node = workflowData?.workflow?.[field?.node] || null;
    const classType = String(node?.class_type || '').toLowerCase();
    const nodeTitle = String(node?._meta?.title || '').toLowerCase();
    const inputKey = String(field?.input || '').toLowerCase();
    const fieldName = String(field?.name || '').toLowerCase();
    return {
        node,
        classType,
        nodeTitle,
        inputKey,
        fieldName,
        fullText:`${classType} ${nodeTitle} ${inputKey} ${fieldName}`.trim()
    };
}
function customComfyPromptFields(runSettings=D("settings")){
 if((runSettings?.engine || D("settings").engine) !== 'comfy') return [];
 normalizeComfyWorkflowSelection(runSettings);
 const workflowName = deps.resolveComfyWorkflowName(runSettings?.comfyWorkflow || D("settings").comfyWorkflow || D("comfyWorkflows")[0]?.name || '');
 const data = workflowName ? (D("comfyWorkflowCache")[workflowName] || null) : null;
 const fields = data?.config?.fields || [];
 return fields.filter(field => deps.comfyFieldKind(field, data) === 'prompt');
}
function normalizeComfyWorkflowSelection(target=D("settings")){
 if(!target || typeof target !== 'object') return target;
 target.comfyMode = 'custom';
 target.comfyWorkflow = deps.resolveComfyWorkflowName(target.comfyWorkflow || '');
 if(!target.comfyWorkflow || !D("comfyWorkflows").some(w => w.name === target.comfyWorkflow)){
 target.comfyWorkflow = D("comfyWorkflows")[0]?.name || '';
 }
 if(!target.comfyParams || typeof target.comfyParams !== 'object') target.comfyParams = {};
 if(!target.comfyModes || typeof target.comfyModes !== 'object') target.comfyModes = {};
 return target;
}
async function ensureCustomComfyWorkflowReady(runSettings=D("settings")){
 if((runSettings?.engine || D("settings").engine) !== 'comfy') return null;
 normalizeComfyWorkflowSelection(runSettings);
 const workflowName = deps.resolveComfyWorkflowName(runSettings?.comfyWorkflow || D("settings").comfyWorkflow || D("comfyWorkflows")[0]?.name || '');
 if(!workflowName) return null;
 return ensureComfyWorkflow(workflowName);
}
// 2026-10-21（老王：SeedVR2 高清放大这类云端工作流凭什么要提示词）：
// 判据改成看工作流定义本身 —— 定义里没有任何提示词节点（Text/CLIPTextEncode/…
// 且带 text/prompt 输入）就允许空提示词。新增工作流自动适用，不用逐个登记。
function rhWorkflowNeedsPrompt(entry){
 try{
  let wf = entry?.workflowJson;
  if(typeof wf === 'string') wf = JSON.parse(wf);
  if(!wf || typeof wf !== 'object') return true;   // 拿不到定义 -> 保守要求提示词
  for(const node of Object.values(wf)){
   if(!node || typeof node !== 'object') continue;
   const ct = String(node.class_type || '').toLowerCase();
   const inputs = node.inputs || {};
   const isPromptNode = /(text|prompt|clip|string|llm)/.test(ct) &&
    ('text' in inputs || 'prompt' in inputs || 'string' in inputs || 'text_positive' in inputs || 'value' in inputs);
   if(isPromptNode && !String(ct).includes('clipsetlastlayer')) return true;
  }
  return false;
 }catch(_){ return true; }
}
function allowsPromptlessRunningHub(runSettings=D("settings")){
 if((runSettings?.engine || D("settings").engine) !== 'runninghub') return false;
 try{
  const ref = (typeof selectedRunningHubRef === 'function') ? selectedRunningHubRef(runSettings) : null;
  if(!ref) return false;
  return !rhWorkflowNeedsPrompt(ref.entry);
 }catch(_){ return false; }
}
function allowsPromptlessCustomComfy(runSettings=D("settings")){
 if((runSettings?.engine || D("settings").engine) !== 'comfy') return allowsPromptlessRunningHub(runSettings);
 normalizeComfyWorkflowSelection(runSettings);
 return customComfyPromptFields(runSettings).length === 0;
}
function comfyParamValue(field){
    D("settings").comfyParams = D("settings").comfyParams || {};
    if(D("settings").comfyParams[field.id] !== undefined) return D("settings").comfyParams[field.id];
    return field.default ?? (field.type === 'boolean' ? false : (field.type === 'number' || field.type === 'slider' ? 0 : ''));
}
function formatComfySliderValue(value, step=1){
    const num = Number(value);
    if(!Number.isFinite(num)) return value ?? '';
    const stepText = String(step ?? 1);
    const decimals = stepText.includes('.') ? Math.min(6, stepText.split('.')[1].length) : 0;
    return num.toFixed(decimals).replace(/\.?0+$/, '');
}
function updateComfySliderValueLabel(input, value){
    const fieldId = input?.dataset?.comfyParam || '';
    const field = currentComfyFields().find(f => f.id === fieldId);
    const label = D("dynamicParams")?.querySelector?.(`[data-slider-val="${CSS.escape(fieldId)}"]`);
    if(label) label.textContent = formatComfySliderValue(value, input?.step || field?.step || 1);
}
function updateProviderModels(){ renderDynamicParams(); }
function renderDynamicParams(){
    if(!D("dynamicParams")) return;
    // 槽若被上轮搬进参数排，先归位到原容器，避免下面 innerHTML= 连节点冲掉
    D("composerSlotHomes").forEach((home, slot) => {
        if (slot.parentElement !== home && home.isConnected) home.appendChild(slot);
    });
    const availableEngines = deps.smartAvailableEngines();
    D("settings").engine = availableEngines.includes(D("settings").engine) ? D("settings").engine : (availableEngines[0] || 'api');
    D("composer").classList.toggle('comfy-layout', D("settings").engine === 'comfy');
    D("composer").classList.toggle('blender-layout', D("settings").engine === 'blender');
    // API 类引擎（api/volcengine/runninghub）图片模式：参数选择按钮合并为单排
    D("composer").classList.toggle('api-single-row', deps.isApiLikeEngine(D("settings").engine) && D("settings").apiKind !== 'video');
    // API 类引擎视频模式：同样的紧凑单排布局
    D("composer").classList.toggle('api-video-row', deps.isApiLikeEngine(D("settings").engine) && D("settings").apiKind === 'video');
    // RH-API 工作流模式（runninghub）：与图片模式同款紧凑单排 chip 布局（2026-09-15 统一）
    D("composer").classList.toggle('rh-single-row', D("settings").engine === 'runninghub');
    // —— 3D预演：只保留视频比例（控制 Blender 渲染分辨率），上移到引擎一排 ——
    if(CanvasPrevizControls.renderBlenderControls()) return;
    // 非 3D预演：恢复 图片/视频 切换 + 按钮原样
    const toggle2 = document.getElementById('apiKindToggle');
    if(toggle2) toggle2.style.display = '';
    const headEl2 = document.querySelector('.composer-head');
    if(headEl2) headEl2.style.flexWrap = '';
    document.querySelectorAll('.blender-ratio-item, .blender-asset-item, .blender-lens-item, .blender-engine-label, .previz-llm-row').forEach(el => el.remove());
    const rb2 = document.getElementById('runBtn');
    if(rb2){
        rb2.querySelector('span').textContent = '运行';
        rb2.style.minWidth = '';
        rb2.style.width = '';
        rb2.style.height = '';
        rb2.style.fontSize = '';
        rb2.style.justifyContent = '';
        rb2.style.gap = '';
        rb2.style.borderRadius = '';
        rb2.style.marginLeft = '';
        // 把按钮放回右侧 run 区（非 3D预演 时保持原样）
        const actionsRow2 = document.querySelector('.composer-actions');
        if(actionsRow2){
            actionsRow2.style.display = '';
            actionsRow2.style.gridColumn = '';
            if(rb2.parentElement !== actionsRow2) actionsRow2.appendChild(rb2);
        }
    }
    D("settings").apiKind = D("settings").apiKind === 'video' ? 'video' : 'image';
    deps.clearVolcengineSelectionOutsideVolcengine(D("settings"));
    deps.syncEngineSelectOptions();
    deps.syncApiKindToggleVisibility();
    if(D("settings").engine === 'api'){
        if(D("settings").apiKind === 'video') deps.renderApiVideoParams();
        else renderApiParams();
    }
    else if(D("settings").engine === 'volcengine'){
        if(D("settings").apiKind === 'video') deps.renderVolcengineVideoParams();
        else deps.renderVolcengineParams();
    }
    else if(D("settings").engine === 'runninghub') deps.renderRunningHubParams();
    else deps.renderComfyParams();
    deps.renderComposerReferenceModeSlot();
    deps.renderComposerStyleControl();
    deps.relocateComposerSlotsToParamRow();
    deps.bindDynamicParams();
    deps.updatePromptPlaceholder();
    deps.syncApiKindToggleVisibility();
    deps.persistActiveSmartSettings();
    // 运行按钮图标：2026-09-16 老王「统一成那个箭头+圆圈」——
    // 所有引擎/布局一律 arrow-up（原来只有 API/RH 单排用 arrow-up，其余用 sparkles，
    // 同一个按钮在不同引擎下两种图标）。圆形的形状由各布局的 CSS 决定（comfy 30px / API·RH 26px）。
    const runIcon = document.querySelector('#runBtn [data-lucide]');
    if(runIcon && runIcon.getAttribute('data-lucide') !== 'arrow-up'){
        runIcon.setAttribute('data-lucide', 'arrow-up');
        if(window.lucide) lucide.createIcons();
    }
    if(window.lucide) lucide.createIcons();
}
function renderApiParams(){
    const providers = deps.imageProviders();
    if(!D("settings").provider_id || !providers.some(p => p.id === D("settings").provider_id)) D("settings").provider_id = providers[0]?.id || '';
    const models = deps.filterJimengImageModels(deps.providerImageModels(D("settings").provider_id));
    if(!D("settings").model || !models.includes(D("settings").model)) D("settings").model = models[0] || '';
    normalizeApiSizeSettings('');
    const outpaintLocked = D("settings").outpaintResolutionLocked === true;
    // 2026-09-16：「自定义比例 / 自定义尺寸」的输入框已并入规格弹层（.image-spec-popover）内部，
    // 不再作为独立一格塞进参数排——单排布局（api-single-row，flex-wrap:nowrap）下它会撑开
    // 参数列并把运行按钮挤出可视区。设置项本身没变，只是换了落点。
    D("dynamicParams").innerHTML = `
        ${deps.renderUnifiedPickerControl()}
        ${outpaintLocked ? `${deps.renderResolutionControl('')}${deps.renderQualityControl()}` : deps.renderComboSpecCount()}
    `;
}
function normalizeHiddenVideoToggles(){
    D("settings").videoEnableUpsample = false;
    D("settings").videoCameraFixed = false;
    D("settings").videoWatermark = false;
    D("settings").videoMultimodal = false;
    D("settings").videoUseFrameRoles = deps.videoReferenceModeValue(D("settings")) === 'first_last';
    // 可信素材=独立开关（与参考模式解耦）；非视频链路一律关（该 toggle 本就被隐藏）
    D("settings").videoTrustedAsset = D("settings").videoTrustedAsset === true;
}

    global.CanvasVideoComfyParams = {
        configure,
        renderVideoTrustedAssetControl,
        renderVideoExtendDirectionControl,
        optionHtml,
        parseSizeValue,
        parseRatioValue,
        apiImageSize,
        rhOfficialNormalizeModel,
        rhOfficialModelForRun,
        shouldUseRhOfficialProxy,
        rhOfficialResolutionForRun,
        rhOfficialAspectRatioForRun,
        normalizeApiSizeSettings,
        ensureComfyWorkflow,
        currentComfyWorkflowData,
        currentComfyFields,
        comfyFieldMeta,
        customComfyPromptFields,
        normalizeComfyWorkflowSelection,
        ensureCustomComfyWorkflowReady,
        allowsPromptlessCustomComfy,
        comfyParamValue,
        formatComfySliderValue,
        updateComfySliderValueLabel,
        updateProviderModels,
        renderDynamicParams,
        renderApiParams,
        normalizeHiddenVideoToggles,
    };
})(typeof window !== 'undefined' ? window : this);

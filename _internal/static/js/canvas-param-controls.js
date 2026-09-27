/* MyridTV 画布参数控件渲染层（拆模块 ⑦：API/火山/即梦 图片与视频 pill）
 *
 * 14 个「settings+provider 数据 → HTML 字符串」纯渲染函数：平台/模型选择、引擎合并 pill、
 * 规格(比例·分辨率·质量·张数)、视频时长/画幅/参考模式/可信素材、开关 cell。
 * 无 DOM 写入（renderApiParams 等 6 个 render*Params 的 dynamicParams.innerHTML 编排
 * 与事件绑定仍在主文件）；settings 所有权在主文件经 getter 注入（本层零写点）。
 */
(function (global) {
    'use strict';

    var deps = {
        escapeHtml: null,
        tr: null,
        videoProviderById: null,
        providerModelDisplayName: null,
        videoAspectIconClass: null,
        videoAspectLabel: null,
        videoAspectOptions: null,
        videoDurationValue: null,
        videoResolutionLabel: null,
        imageQualityLabel: null,
        imageSpecOptions: null,
        ratioIconClass: null,
        ratioLabel: null,
        resolutionLabel: null,
        videoReferenceModeValue: null,
        apiProviderById: null,
        smartAvailableEngines: null,
        smartEngineLabel: null,
        videoApiProviders: null,
        volcengineProvider: null,
        getSettings: null
    };
    function configure(opts) {
        Object.assign(deps, opts || {});
    }

function renderVideoProviderControl(providers){
    const current = (providers || []).find(p => p.id === deps.getSettings().videoProvider) || deps.videoProviderById(deps.getSettings().videoProvider);
    return `<div class="smart-control provider-control">
        <button class="smart-pill" type="button"><i data-lucide="plug-zap"></i><span class="sub">${deps.escapeHtml(current?.name || deps.getSettings().videoProvider || deps.tr('smart.platform'))}</span></button>
        <div class="smart-popover compact-popover">
            <div class="smart-popover-title">${deps.escapeHtml(deps.tr('smart.videoPlatform'))}</div>
            <div class="model-list">
                ${providers.map(p => `<button type="button" class="direct-option ${p.id === deps.getSettings().videoProvider ? 'active' : ''}" data-smart-param="videoProvider" data-smart-value="${deps.escapeHtml(p.id)}"><span>${deps.escapeHtml(p.name || p.id)}</span></button>`).join('') || `<div class="muted-note">${deps.escapeHtml(deps.tr('smart.noVideoPlatform'))}</div>`}
            </div>
        </div>
    </div>`;
}
function renderVideoModelControl(models){
    const videoLabel = deps.getSettings().videoModel ? deps.providerModelDisplayName(deps.getSettings().videoProvider, deps.getSettings().videoModel) : deps.tr('smart.model');
    return `<div class="smart-control model-control">
        <button class="smart-pill" type="button"><i data-lucide="film"></i><span class="sub">${deps.escapeHtml(videoLabel)}</span></button>
        <div class="smart-popover compact-popover">
            <div class="smart-popover-title">${deps.escapeHtml(deps.tr('smart.videoModel'))}</div>
            <div class="model-list">
                ${models.map(m => `<button type="button" class="direct-option ${m === deps.getSettings().videoModel ? 'active' : ''}" data-smart-param="videoModel" data-smart-value="${deps.escapeHtml(m)}"><span>${deps.escapeHtml(deps.providerModelDisplayName(deps.getSettings().videoProvider, m))}</span></button>`).join('') || `<div class="muted-note">${deps.escapeHtml(deps.tr('smart.noVideoModel'))}</div>`}
            </div>
        </div>
    </div>`;
}
function renderVideoDurationControl(){
    const v = Math.max(1, Math.min(60, Number(deps.getSettings().videoDuration) || 5));
    // Seedance 2.5 支持 30s 直出：当前模型是 2.5 时快捷档放宽到 20/30
    const model = String(deps.getSettings().videoModel || '');
    const isSd25 = /seedance[-_. ]*2[-_. ]?5/i.test(model);
    const quick = isSd25 ? [4, 5, 6, 8, 10, 12, 15, 20, 30] : [3, 4, 5, 6, 8, 10, 12, 15];
    return `<div class="smart-control duration-control" title="${deps.escapeHtml(deps.tr('smart.videoDurationTip'))}">
        <button class="smart-pill" type="button"><i data-lucide="timer"></i><span>${v}s</span></button>
        <div class="smart-popover compact-popover">
            <div class="smart-popover-title">${deps.escapeHtml(deps.tr('smart.videoDuration'))}</div>
            <div class="duration-grid">
                ${quick.map(n => `<button type="button" class="duration-option ${n === v ? 'active' : ''}" data-smart-param="videoDuration" data-smart-value="${n}">${n}s</button>`).join('')}
            </div>
            <label class="duration-custom">
                <span>${deps.escapeHtml(deps.tr('smart.custom'))}</span>
                <input type="number" min="1" max="60" step="1" data-param="videoDuration" value="${v}">
            </label>
        </div>
    </div>`;
}
function renderVideoAspectControl(){
    const options = [
        ['16:9','16:9'], ['9:16','9:16'], ['1:1','1:1'], ['4:3','4:3'], ['3:4','3:4'],
        ['21:9','21:9'], ['9:21','9:21'], ['keep_ratio', deps.tr('smart.videoAspectKeep')], ['adaptive', deps.tr('smart.videoAspectAdaptive')]
    ];
    const value = deps.getSettings().videoAspect || '16:9';
    const labelMap = Object.fromEntries(options);
    return `<div class="smart-control aspect-control">
        <button class="smart-pill" type="button"><i data-lucide="scan"></i><span>${deps.escapeHtml(labelMap[value] || value)}</span></button>
        <div class="smart-popover">
            <div class="smart-popover-title">${deps.escapeHtml(deps.tr('smart.videoAspect'))}</div>
            <div class="ratio-grid">
                ${options.map(([v,l]) => `<button type="button" class="ratio-option ${v === value ? 'active' : ''}" data-smart-param="videoAspect" data-smart-value="${deps.escapeHtml(v)}"><span class="ratio-icon ${deps.videoAspectIconClass(v)}"></span><span>${deps.escapeHtml(l)}</span></button>`).join('')}
            </div>
        </div>
    </div>`;
}
function renderVideoResolutionControl(){
    const options = [['', deps.tr('smart.videoResAuto')], ['480p','480P'], ['720p','720P'], ['1080p','1080P'], ['4k','4K']];
    const value = deps.getSettings().videoResolution || '';
    const labelMap = Object.fromEntries(options);
    return `<div class="smart-control resolution-control">
        <button class="smart-pill" type="button"><i data-lucide="monitor"></i><span>${deps.escapeHtml(labelMap[value] || value || deps.tr('smart.videoResAuto'))}</span></button>
        <div class="smart-popover compact-popover">
            <div class="smart-popover-title">${deps.escapeHtml(deps.tr('smart.videoResolution'))}</div>
            <div class="model-list">
                ${options.map(([v,l]) => `<button type="button" class="direct-option ${v === value ? 'active' : ''}" data-smart-param="videoResolution" data-smart-value="${deps.escapeHtml(v)}"><span>${deps.escapeHtml(l)}</span></button>`).join('')}
            </div>
        </div>
    </div>`;
}
function renderVideoSpecControl(){
    const aspect = deps.getSettings().videoAspect || '16:9';
    const resolution = deps.getSettings().videoResolution || '';
    const duration = deps.videoDurationValue(deps.getSettings());
    const aspectLabel = deps.videoAspectLabel(deps.getSettings());
    const resolutionLabelText = deps.videoResolutionLabel(deps.getSettings());
    const aspectOptions = deps.videoAspectOptions();
    const resolutionOptions = videoResolutionOptions();
    return `<div class="smart-control video-spec-control" title="视频规格">
        <button class="smart-pill" type="button"><span>${deps.escapeHtml(aspectLabel)} · ${deps.escapeHtml(resolutionLabelText)} · ${duration}s</span><i data-lucide="chevron-down" class="pill-caret"></i></button>
        <div class="smart-popover video-spec-popover">
            <div class="video-spec-section">
                <div class="video-spec-title">视频比例</div>
                <div class="video-spec-aspect-grid">
                    ${aspectOptions.map(([v,l]) => `<button type="button" class="video-spec-aspect ${v === aspect ? 'active' : ''}" data-smart-param="videoAspect" data-smart-value="${deps.escapeHtml(v)}"><span class="ratio-icon ${deps.videoAspectIconClass(v)}"></span><span>${deps.escapeHtml(l)}</span></button>`).join('')}
                </div>
            </div>
            <div class="video-spec-section">
                <div class="video-spec-title">分辨率</div>
                <div class="video-spec-seg">
                    ${resolutionOptions.map(([v,l]) => `<button type="button" class="${v === resolution ? 'active' : ''}" data-smart-param="videoResolution" data-smart-value="${deps.escapeHtml(v)}">${deps.escapeHtml(l)}</button>`).join('')}
                </div>
            </div>
            <div class="video-spec-section">
                <div class="video-spec-title">视频时长</div>
                <label class="duration-custom video-spec-custom-duration">
                    <span>自定义</span>
                    <input type="number" min="1" max="60" step="1" data-param="videoDuration" value="${duration}">
                    <span>秒</span>
                </label>
            </div>
            <div class="video-spec-section">
                <div class="video-spec-title">音频</div>
                ${renderVideoToggleControl('videoGenerateAudio', deps.tr('smart.videoGenerateAudio'))}
            </div>
        </div>
    </div>`;
}
function renderImageSpecControl(){
    const {ratios, resolutions, qualityLabels} = deps.imageSpecOptions();
    const ratio = deps.getSettings().ratio || 'square';
    const resolution = deps.getSettings().resolution || '1k';
    const quality = deps.getSettings().quality || 'auto';
    return `<div class="smart-control image-spec-control" title="图片规格">
        <button class="smart-pill" type="button"><i data-lucide="sliders-horizontal"></i><span>${deps.escapeHtml(deps.ratioLabel(''))} · ${deps.escapeHtml(deps.resolutionLabel(''))} · ${deps.escapeHtml(deps.imageQualityLabel())}</span><i data-lucide="chevron-down" class="pill-caret"></i></button>
        <div class="smart-popover video-spec-popover image-spec-popover">
            <div class="video-spec-section">
                <div class="video-spec-title">图片比例</div>
                <div class="image-spec-ratio-grid">
                    ${ratios.map(([v,l]) => `<button type="button" class="video-spec-aspect ${v === ratio ? 'active' : ''}" data-smart-param="ratio" data-smart-value="${deps.escapeHtml(v)}"><span class="ratio-icon ${deps.ratioIconClass(v)}"></span><span>${deps.escapeHtml(l)}</span></button>`).join('')}
                </div>
            </div>
            <div class="video-spec-section">
                <div class="video-spec-title">分辨率</div>
                <div class="video-spec-seg">
                    ${resolutions.map(([v,l]) => `<button type="button" class="${v === resolution ? 'active' : ''}" data-smart-param="resolution" data-smart-value="${deps.escapeHtml(v)}">${deps.escapeHtml(l)}</button>`).join('')}
                </div>
            </div>
            <div class="video-spec-section">
                <div class="video-spec-title">画质</div>
                <div class="video-spec-seg">
                    ${Object.entries(qualityLabels).map(([v,l]) => `<button type="button" class="${v === quality ? 'active' : ''}" data-smart-param="quality" data-smart-value="${deps.escapeHtml(v)}">${deps.escapeHtml(l)}</button>`).join('')}
                </div>
            </div>
        </div>
    </div>`;
}
function renderVideoToggleControl(key, label){
    const on = !!deps.getSettings()[key];
    return `<button type="button" class="setting-check ${on ? 'active' : ''}" data-toggle-param="${deps.escapeHtml(key)}"><span class="check-box"></span><span>${deps.escapeHtml(label)}</span></button>`;
}
function renderVideoReferenceModeControl(){
    const value = deps.videoReferenceModeValue(deps.getSettings());
    const labels = {
        mixed:'全能参考',
        first_last:'首尾帧',
        video_edit:'视频编辑',
        video_extend:'视频延长'
    };
    // 火山 Seedance 官方三种参考场景（文案照官方，不加解释）：全能参考 / 首尾帧 / 视频编辑 / 视频延长。
    // 旧的 video_only、frame_extract 已合并：素材直链与自动抽帧降级由后端在提交时兜底，不再让用户选。
    const opts = [
        ['mixed','全能参考'],
        ['first_last','首尾帧'],
        ['video_edit','视频编辑'],
        ['video_extend','视频延长']
    ];
    return `<div class="smart-control video-reference-mode-control">
        <button class="smart-pill" type="button"><span>${deps.escapeHtml(labels[value] || labels.mixed)}</span><i data-lucide="chevron-down" class="pill-caret"></i></button>
        <div class="smart-popover compact-popover">
            <div class="smart-popover-title">参考模式</div>
            <div class="model-list">
                ${opts.map(([v,label]) => `<button type="button" class="direct-option ${value === v ? 'active' : ''}" data-smart-param="videoReferenceMode" data-smart-value="${v}"><span>${label}</span></button>`).join('')}
            </div>
        </div>
    </div>`;
}
function renderVideoExtendDirectionControl(){
    // 仅「视频延长」模式显示：向后延长=生成视频1之后的内容 / 向前延长=生成视频1之前的内容
    const value = String(deps.getSettings().videoExtendMode || 'after');
    return `<div class="smart-control video-extend-dir-control">
        <button class="smart-pill" type="button"><span>${value === 'before' ? '向前延长' : '向后延长'}</span><i data-lucide="chevron-down" class="pill-caret"></i></button>
        <div class="smart-popover compact-popover">
            <div class="smart-popover-title">延长方向</div>
            <div class="model-list">
                <button type="button" class="direct-option ${value === 'after' ? 'active' : ''}" data-smart-param="videoExtendMode" data-smart-value="after"><span>向后延长</span></button>
                <button type="button" class="direct-option ${value === 'before' ? 'active' : ''}" data-smart-param="videoExtendMode" data-smart-value="before"><span>向前延长</span></button>
            </div>
        </div>
    </div>`;
}
function renderVideoTrustedAssetControl(){
    const on = !!deps.getSettings().videoTrustedAsset;
    let html = renderVideoToggleControl('videoTrustedAsset', deps.tr('smart.videoTrustedAsset'));
    if(!on) return html;
    const src = ['library','cloud','manual'].includes(deps.getSettings().videoTrustedSource) ? deps.getSettings().videoTrustedSource : 'library';
    html += `<div class="trusted-source-row">
        <button type="button" class="smart-pill trusted-src-pill ${src === 'library' ? 'active' : ''}" data-trusted-source="library" title="使用素材库中已注册的认证素材链接（asset://）"><i data-lucide="library"></i><span>素材库链接</span></button>
        <button type="button" class="smart-pill trusted-src-pill ${src === 'cloud' ? 'active' : ''}" data-trusted-source="cloud" title="把当前输入图片/视频上传到云端直链"><i data-lucide="upload-cloud"></i><span>上传云端</span></button>
        <button type="button" class="smart-pill trusted-src-pill ${src === 'manual' ? 'active' : ''}" data-trusted-source="manual" title="手动输入媒体 URL 或 asset:// 地址"><i data-lucide="link"></i><span>输入网址</span></button>
    </div>`;
    return html;
}
function renderProviderControl(providers){
    const current = (providers || []).find(p => p.id === deps.getSettings().provider_id) || deps.apiProviderById(deps.getSettings().provider_id);
    return `<div class="smart-control provider-control">
        <button class="smart-pill" type="button"><i data-lucide="plug-zap"></i><span class="sub">${deps.escapeHtml(current?.name || deps.getSettings().provider_id || deps.tr('smart.platform'))}</span></button>
        <div class="smart-popover compact-popover">
            <div class="smart-popover-title">${deps.escapeHtml(deps.tr('smart.apiPlatform'))}</div>
            <div class="model-list">
                ${providers.map(p => `<button type="button" class="direct-option ${p.id === deps.getSettings().provider_id ? 'active' : ''}" data-smart-param="provider_id" data-smart-value="${deps.escapeHtml(p.id)}"><span>${deps.escapeHtml(p.name || p.id)}</span></button>`).join('') || `<div class="muted-note">${deps.escapeHtml(deps.tr('smart.noApiPlatform'))}</div>`}
            </div>
        </div>
    </div>`;
}
function renderModelControl(models){
  const selectedLabel = deps.providerModelDisplayName(deps.getSettings().provider_id, deps.getSettings().model || '') || deps.tr('smart.model');
  return `<div class="smart-control model-control">
    <button class="smart-pill" type="button"><i data-lucide="sparkles"></i><span class="sub">${deps.escapeHtml(selectedLabel)}</span></button>
    <div class="smart-popover compact-popover">
      <div class="smart-popover-title">${deps.escapeHtml(deps.tr('smart.imageModel'))}</div>
      <div class="model-list">
        ${models.map(m => `<button type="button" class="direct-option ${m === deps.getSettings().model ? 'active' : ''}" data-smart-param="model" data-smart-value="${deps.escapeHtml(m)}"><span>${deps.escapeHtml(deps.providerModelDisplayName(deps.getSettings().provider_id, m))}</span></button>`).join('') || `<div class="muted-note">${deps.escapeHtml(deps.tr('smart.noImageModel'))}</div>`}
      </div>
    </div>
  </div>`;
}
function renderEngineModelCombo(models){
  const engineLabel = deps.smartEngineLabel(deps.getSettings().engine);
  const modelLabel = deps.providerModelDisplayName(deps.getSettings().provider_id, deps.getSettings().model || '');
  const engines = deps.smartAvailableEngines().filter(e => e !== 'blender');
  const currentEngine = deps.getSettings().engine || engines[0] || 'api';
  return `<div class="smart-control engine-model-combo" title="平台与模型">
    <button class="smart-pill" type="button"><span class="sub">${deps.escapeHtml(engineLabel)}${modelLabel ? ` · ${deps.escapeHtml(modelLabel)}` : ''}</span><i data-lucide="chevron-down" class="pill-caret"></i></button>
    <div class="smart-popover engine-model-popover">
      <div class="smart-popover-title">平台</div>
      <div class="model-list">
        ${engines.map(e => `<button type="button" class="direct-option ${e === currentEngine ? 'active' : ''}" data-combo-engine="${deps.escapeHtml(e)}"><span>${deps.escapeHtml(deps.smartEngineLabel(e))}</span></button>`).join('')}
      </div>
      <div class="smart-popover-title" style="margin-top:8px">模型</div>
      <div class="model-list">
        ${models.map(m => `<button type="button" class="direct-option ${m === deps.getSettings().model ? 'active' : ''}" data-smart-param="model" data-smart-value="${deps.escapeHtml(m)}"><span>${deps.escapeHtml(deps.providerModelDisplayName(deps.getSettings().provider_id, m))}</span></button>`).join('') || `<div class="muted-note">${deps.escapeHtml(deps.tr('smart.noImageModel'))}</div>`}
      </div>
    </div>
  </div>`;
}
function renderVideoEngineModelCombo(models){
  // 平台组 = 有视频模型的配置平台（含 volcengine 豆包，点它切到火山引擎）+ 无配置平台时的兜底
  const volc = deps.volcengineProvider();
  const volcHasVid = volc && (volc.video_models || []).length > 0;
  const providers = deps.videoApiProviders();
  const platforms = providers.map(p => ({ id: p.id, name: p.name || p.id, engine: 'api' }));
  if(volcHasVid) platforms.push({ id: 'volcengine', name: volc.name || '火山引擎', engine: 'volcengine' });
  const currentEngine = deps.getSettings().engine || 'api';
  let currentPlatformId = currentEngine === 'volcengine' ? 'volcengine' : (deps.getSettings().videoProvider || '');
  // 无配置视频平台时默认落到豆包（volcengine），保证 pill 与模型列表有真实内容
  if(!currentPlatformId && !providers.length && volcHasVid) currentPlatformId = 'volcengine';
  const currentPlatform = platforms.find(p => p.id === currentPlatformId);
  const providerLabel = currentPlatform?.name || deps.tr('smart.platform');
  const modelLabel = deps.getSettings().videoModel ? deps.providerModelDisplayName(deps.getSettings().videoProvider, deps.getSettings().videoModel) : '';
  return `<div class="smart-control engine-model-combo" title="平台与模型">
    <button class="smart-pill" type="button"><span class="sub">${deps.escapeHtml(providerLabel)}${modelLabel ? ` · ${deps.escapeHtml(modelLabel)}` : ''}</span><i data-lucide="chevron-down" class="pill-caret"></i></button>
    <div class="smart-popover engine-model-popover">
      <div class="smart-popover-title">平台</div>
      <div class="model-list">
        ${platforms.map(p => `<button type="button" class="direct-option ${p.id === currentPlatformId ? 'active' : ''}" ${p.engine === 'volcengine' ? `data-combo-engine="volcengine"` : `data-smart-param="videoProvider" data-smart-value="${deps.escapeHtml(p.id)}"`}><span>${deps.escapeHtml(p.name)}</span></button>`).join('') || `<div class="muted-note">${deps.escapeHtml(deps.tr('smart.noVideoPlatform'))}</div>`}
      </div>
      <div class="smart-popover-title" style="margin-top:8px">模型</div>
      <div class="model-list">
        ${models.map(m => `<button type="button" class="direct-option ${m === deps.getSettings().videoModel ? 'active' : ''}" data-smart-param="videoModel" data-smart-value="${deps.escapeHtml(m)}"><span>${deps.escapeHtml(deps.providerModelDisplayName(deps.getSettings().videoProvider, m))}</span></button>`).join('') || `<div class="muted-note">${deps.escapeHtml(deps.tr('smart.noVideoModel'))}</div>`}
      </div>
    </div>
  </div>`;
}

    global.CanvasParamControls = {
        configure: configure,
        renderVideoProviderControl: renderVideoProviderControl,
        renderVideoModelControl: renderVideoModelControl,
        renderVideoDurationControl: renderVideoDurationControl,
        renderVideoAspectControl: renderVideoAspectControl,
        renderVideoResolutionControl: renderVideoResolutionControl,
        renderVideoSpecControl: renderVideoSpecControl,
        renderImageSpecControl: renderImageSpecControl,
        renderVideoToggleControl: renderVideoToggleControl,
        renderVideoReferenceModeControl: renderVideoReferenceModeControl,
        renderVideoExtendDirectionControl: renderVideoExtendDirectionControl,
        renderVideoTrustedAssetControl: renderVideoTrustedAssetControl,
        renderProviderControl: renderProviderControl,
        renderModelControl: renderModelControl,
        renderEngineModelCombo: renderEngineModelCombo,
        renderVideoEngineModelCombo: renderVideoEngineModelCombo
    };
})(typeof window !== 'undefined' ? window : globalThis);

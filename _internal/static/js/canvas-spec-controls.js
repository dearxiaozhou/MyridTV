/* MyridTV 画布规格控件渲染层（拆模块 ⑧：比例·分辨率·画质·张数）
 *
 * 27 个「settings → HTML 字符串 / 数据解析」纯函数：规格弹层、合并规格 pill、
 * 比例/分辨率/画质/数量控件、自定义比例与尺寸内联字段、比例化简(gcd)、原 Modelscope 函数选择。
 * 无 DOM 写入与事件绑定；settings 所有权在主文件经 getter 注入（本层零写点）；
 * sourceImageRatioLabel（节点图深链）经注入。
 */
(function (global) {
    'use strict';

    var deps = {
        escapeHtml: null,
        tr: null,
        sourceImageRatioLabel: null,
        getSettings: null
    };
    function configure(opts) {
        Object.assign(deps, opts || {});
    }

function optionHtml(value, label, selected){
    return `<option value="${deps.escapeHtml(value)}" ${String(value) === String(selected) ? 'selected' : ''}>${deps.escapeHtml(label ?? value)}</option>`;
}
function gcdInt(a, b){
    a = Math.abs(Math.round(Number(a) || 0));
    b = Math.abs(Math.round(Number(b) || 0));
    while(b){ const t = b; b = a % b; a = t; }
    return a || 1;
}
function imageSizeForRatio(img){
    const w = Math.round(Number(img?.natural_w || img?.width || img?.w || 0));
    const h = Math.round(Number(img?.natural_h || img?.height || img?.h || 0));
    return w > 0 && h > 0 ? {w, h} : null;
}
function reducedRatioForImage(img){
    const size = imageSizeForRatio(img);
    if(!size) return null;
    const d = gcdInt(size.w, size.h);
    return {w:Math.max(1, Math.round(size.w / d)), h:Math.max(1, Math.round(size.h / d))};
}
function ratioLabel(prefix=''){
    const ratioKey = prefix ? `${prefix}Ratio` : 'ratio';
    const customKey = prefix ? `${prefix}CustomRatio` : 'customRatio';
    const sourceLabel = deps.sourceImageRatioLabel(prefix) || deps.tr('smart.imageRatio');
    const map = {square:'1:1', portrait:'2:3', landscape:'3:2', portrait43:'3:4', landscape43:'4:3', story:'9:16', wide:'16:9', ultrawide:'21:9', ultratall:'9:21', source:sourceLabel, custom:deps.getSettings()[customKey] || deps.tr('smart.custom')};
    return map[deps.getSettings()[ratioKey] || 'square'] || '1:1';
}
function resolutionLabel(prefix=''){
    const resKey = prefix ? `${prefix}Resolution` : 'resolution';
    const sizeKey = prefix ? `${prefix}CustomSize` : 'customSize';
    const value = deps.getSettings()[resKey] || '1k';
    return value === 'custom' ? (deps.getSettings()[sizeKey] || deps.tr('smart.custom')) : value.toUpperCase();
}
function imageQualityLabel(source=deps.getSettings()){
    const labels = {auto:deps.tr('smart.qualityAuto'), low:deps.tr('smart.qualityLow'), medium:deps.tr('smart.qualityMid'), high:deps.tr('smart.qualityHigh')};
    const v = source?.quality || 'auto';
    return labels[v] || v;
}
function imageSpecOptions(){
    const ratios = [
        ['square','1:1'], ['portrait','2:3'], ['landscape','3:2'], ['portrait43','3:4'], ['landscape43','4:3'],
        ['story','9:16'], ['wide','16:9'], ['ultrawide','21:9'], ['ultratall','9:21'],
        ['source', deps.sourceImageRatioLabel('') || deps.tr('smart.imageRatio')],
        ['custom', deps.tr('smart.custom')]
    ];
    const resolutions = [['1k','1K'], ['2k','2K'], ['4k','4K'], ['custom', deps.tr('smart.custom')]];
    const qualityLabels = {auto:deps.tr('smart.qualityAuto'), low:deps.tr('smart.qualityLow'), medium:deps.tr('smart.qualityMid'), high:deps.tr('smart.qualityHigh')};
    return {ratios, resolutions, qualityLabels};
}
function ratioIconClass(value){
    if(value === 'portrait') return 'r-portrait';
    if(value === 'portrait43') return 'r-portrait43';
    if(value === 'landscape') return 'r-landscape';
    if(value === 'landscape43') return 'r-landscape43';
    if(value === 'wide' || value === 'ultrawide') return 'r-wide';
    if(value === 'story' || value === 'ultratall') return 'r-story';
    if(value === 'source') return 'r-source';
    if(value === 'custom') return 'r-custom';
    return '';
}
function videoAspectIconClass(value){
    if(value === '16:9' || value === '21:9') return 'r-wide';
    if(value === '9:16' || value === '9:21') return 'r-story';
    if(value === '4:3') return 'r-landscape43';
    if(value === '3:4') return 'r-portrait43';
    if(value === 'keep_ratio' || value === 'adaptive') return 'r-source';
    return '';
}
function videoAspectLabel(source=deps.getSettings()){
    const options = videoAspectOptions();
    const value = source?.videoAspect || '16:9';
    const labelMap = Object.fromEntries(options);
    return labelMap[value] || value;
}
function videoAspectOptions(){
    return [
        ['21:9','21:9'], ['16:9','16:9'], ['4:3','4:3'], ['1:1','1:1'], ['3:4','3:4'],
        ['9:16','9:16'], ['keep_ratio', deps.tr('smart.videoAspectKeep')], ['adaptive', deps.tr('smart.videoAspectAdaptive')]
    ];
}
function renderSizeControls(prefix='', includeSource=false){
    const ratioKey = prefix ? `${prefix}Ratio` : 'ratio';
    const resKey = prefix ? `${prefix}Resolution` : 'resolution';
    const ratios = [
        ['square','1:1'], ['portrait','2:3'], ['landscape','3:2'], ['portrait43','3:4'], ['landscape43','4:3'], ['story','9:16'], ['wide','16:9'], ['ultrawide','21:9'], ['ultratall','9:21'],
        ...(includeSource ? [['source', deps.tr('canvas.adaptiveRatio') || '适配比例']] : []),
        ['custom', deps.tr('canvas.custom') || '自定义']
    ];
    return `<select data-param="${resKey}">
            ${['1k','2k','4k','custom'].map(v => optionHtml(v, v === 'custom' ? (deps.tr('canvas.custom') || '自定义') : v.toUpperCase(), deps.getSettings()[resKey] || '1k')).join('')}
        </select>
        <select data-param="${ratioKey}" ${deps.getSettings()[resKey] === 'custom' ? 'disabled' : ''}>
            ${ratios.map(([v,l]) => `<option value="${deps.escapeHtml(v)}" ${v === (deps.getSettings()[ratioKey] || 'square') ? 'selected' : ''}>${deps.escapeHtml(l)}</option>`).join('')}
        </select>`;
}
function renderRatioControl(prefix='', includeSource=false){
    const ratioKey = prefix ? `${prefix}Ratio` : 'ratio';
    const resKey = prefix ? `${prefix}Resolution` : 'resolution';
    const ratios = [
        ['square','1:1'], ['portrait','2:3'], ['landscape','3:2'], ['portrait43','3:4'], ['landscape43','4:3'],
        ['story','9:16'], ['wide','16:9'], ['ultrawide','21:9'], ['ultratall','9:21'],
        ...(includeSource ? [['source', deps.tr('smart.imageRatio')]] : []),
        ['custom', deps.tr('smart.custom')]
    ];
    return `<div class="smart-control ratio-control">
        <button class="smart-pill" type="button"><i data-lucide="scan"></i><span>${deps.escapeHtml(ratioLabel(prefix))}</span></button>
        <div class="smart-popover">
            <div class="smart-popover-title">${deps.escapeHtml(deps.tr('smart.ratio'))}</div>
            <div class="ratio-grid">
                ${ratios.map(([value, label]) => `<button type="button" class="ratio-option ${value === (deps.getSettings()[ratioKey] || 'square') ? 'active' : ''}" data-smart-param="${ratioKey}" data-smart-value="${deps.escapeHtml(value)}"><span class="ratio-icon ${ratioIconClass(value)}"></span><span>${deps.escapeHtml(label)}</span></button>`).join('')}
            </div>
        </div>
    </div>`;
}
function renderResolutionControl(prefix=''){
    const resKey = prefix ? `${prefix}Resolution` : 'resolution';
    return `<div class="smart-control resolution-control">
        <button class="smart-pill" type="button"><i data-lucide="monitor"></i><span>${deps.escapeHtml(resolutionLabel(prefix))}</span></button>
        <div class="smart-popover compact-popover">
            <div class="smart-popover-title">${deps.escapeHtml(deps.tr('smart.resolution'))}</div>
            <div class="seg-row">
                ${['1k','2k','4k','custom'].map(value => `<button type="button" class="${value === (deps.getSettings()[resKey] || '1k') ? 'active' : ''}" data-smart-param="${resKey}" data-smart-value="${value}">${value === 'custom' ? deps.escapeHtml(deps.tr('smart.custom')) : value.toUpperCase()}</button>`).join('')}
            </div>
        </div>
    </div>`;
}
function renderQualityControl(){
    const value = deps.getSettings().quality || 'auto';
    const labels = {auto:deps.tr('smart.qualityAuto'), low:deps.tr('smart.qualityLow'), medium:deps.tr('smart.qualityMid'), high:deps.tr('smart.qualityHigh')};
    return `<div class="smart-control quality-control">
        <button class="smart-pill" type="button"><i data-lucide="sliders-horizontal"></i><span>${deps.escapeHtml(labels[value] || value)}</span></button>
        <div class="smart-popover compact-popover">
            <div class="smart-popover-title">${deps.escapeHtml(deps.tr('smart.quality'))}</div>
            <div class="seg-row">
                ${Object.entries(labels).map(([k, l]) => `<button type="button" class="${k === value ? 'active' : ''}" data-smart-param="quality" data-smart-value="${deps.escapeHtml(k)}">${deps.escapeHtml(l)}</button>`).join('')}
            </div>
        </div>
    </div>`;
}
function renderCountVisualControl(){
    const value = Number(deps.getSettings().count || 1);
    return `<div class="smart-control count-control">
        <button class="smart-pill" type="button"><i data-lucide="copy"></i><span>${value}${deps.tr('smart.countUnit') ? ' ' + deps.escapeHtml(deps.tr('smart.countUnit')) : ''}</span></button>
        <div class="smart-popover compact-popover" style="min-width:170px">
            <div class="smart-popover-title">${deps.escapeHtml(deps.tr('smart.count'))}</div>
            <div class="count-grid">
                ${[1,2,3,4,5,6,7,8].map(n => `<button type="button" class="count-cell ${n === value ? 'active' : ''}" data-smart-param="count" data-smart-value="${n}">${n}</button>`).join('')}
            </div>
        </div>
    </div>`;
}
function renderCountControl(){
    return `<select data-param="count">${[1,2,3,4,5,6,7,8].map(n => optionHtml(n, `${n} 张`, Number(deps.getSettings().count || 1))).join('')}</select>`;
}
function renderCustomRatioControls(prefix=''){
    const ratioKey = prefix ? `${prefix}Ratio` : 'ratio';
    if(deps.getSettings()[ratioKey] !== 'custom' && deps.getSettings()[ratioKey] !== 'source') return '';
    const wKey = prefix ? `${prefix}CustomRatioWidth` : 'customRatioWidth';
    const hKey = prefix ? `${prefix}CustomRatioHeight` : 'customRatioHeight';
    const disabled = deps.getSettings()[ratioKey] === 'source' ? 'disabled' : '';
    return `<input type="number" data-param="${wKey}" value="${deps.escapeHtml(deps.getSettings()[wKey] || '')}" placeholder="比例宽" ${disabled}>
            <input type="number" data-param="${hKey}" value="${deps.escapeHtml(deps.getSettings()[hKey] || '')}" placeholder="比例高" ${disabled}>`;
}
function renderCustomSizeControls(prefix=''){
    const resKey = prefix ? `${prefix}Resolution` : 'resolution';
    if(deps.getSettings()[resKey] !== 'custom') return '';
    const wKey = prefix ? `${prefix}CustomWidth` : 'customWidth';
    const hKey = prefix ? `${prefix}CustomHeight` : 'customHeight';
    return `<input type="number" data-param="${wKey}" value="${deps.escapeHtml(deps.getSettings()[wKey] || '')}" placeholder="宽度">
            <input type="number" data-param="${hKey}" value="${deps.escapeHtml(deps.getSettings()[hKey] || '')}" placeholder="高度">`;
}
function renderComboSpecCount(){
  const ratio = deps.getSettings().ratio || 'square';
  const resolution = deps.getSettings().resolution || '1k';
  const quality = deps.getSettings().quality || 'auto';
  const count = Number(deps.getSettings().count || 1);
  const label = `${ratioLabel('')} · ${resolutionLabel('')} · ${imageQualityLabel()} · ${count}张`;
  return `<div class="smart-control image-spec-control combo-spec-count" title="图片参数">
    <button class="smart-pill" type="button"><span class="sub">${deps.escapeHtml(label)}</span><i data-lucide="chevron-down" class="pill-caret"></i></button>
    ${renderImageSpecPopover()}
  </div>`;
}
function renderImageSpecPopover(){
  const {ratios, resolutions, qualityLabels} = imageSpecOptions();
  const ratio = deps.getSettings().ratio || 'square';
  const resolution = deps.getSettings().resolution || '1k';
  const quality = deps.getSettings().quality || 'auto';
  const count = Number(deps.getSettings().count || 1);
  return `<div class="smart-popover video-spec-popover image-spec-popover">
    <div class="video-spec-section">
      <div class="video-spec-title">图片比例</div>
      <div class="image-spec-ratio-grid">
        ${ratios.map(([v,l]) => `<button type="button" class="video-spec-aspect ${v === ratio ? 'active' : ''}" data-smart-param="ratio" data-smart-value="${deps.escapeHtml(v)}"><span class="ratio-icon ${ratioIconClass(v)}"></span><span>${deps.escapeHtml(l)}</span></button>`).join('')}
      </div>
      ${renderInlineCustomRatioFields('', 'inline-fields-in-popover')}
    </div>
    <div class="video-spec-section">
      <div class="video-spec-title">分辨率</div>
      <div class="video-spec-seg">
        ${resolutions.map(([v,l]) => `<button type="button" class="${v === resolution ? 'active' : ''}" data-smart-param="resolution" data-smart-value="${deps.escapeHtml(v)}">${deps.escapeHtml(l)}</button>`).join('')}
      </div>
      ${renderInlineCustomSizeFields('', 'inline-fields-in-popover')}
    </div>
    <div class="video-spec-section">
      <div class="video-spec-title">画质</div>
      <div class="video-spec-seg">
        ${Object.entries(qualityLabels).map(([v,l]) => `<button type="button" class="${v === quality ? 'active' : ''}" data-smart-param="quality" data-smart-value="${deps.escapeHtml(v)}">${deps.escapeHtml(l)}</button>`).join('')}
      </div>
    </div>
    <div class="video-spec-section">
      <div class="video-spec-title">数量</div>
      <div class="count-grid">
        ${[1,2,3,4,5,6,7,8].map(n => `<button type="button" class="count-cell ${n === count ? 'active' : ''}" data-smart-param="count" data-smart-value="${n}">${n}</button>`).join('')}
      </div>
    </div>
  </div>`;
}
function renderInlineCustomRatioFields(prefix='', extraClass=''){
    const ratioKey = prefix ? `${prefix}Ratio` : 'ratio';
    if(deps.getSettings()[ratioKey] === 'source') return '';
    if(deps.getSettings()[ratioKey] !== 'custom') return '';
    const wKey = prefix ? `${prefix}CustomRatioWidth` : 'customRatioWidth';
    const hKey = prefix ? `${prefix}CustomRatioHeight` : 'customRatioHeight';
    return `<div class="inline-fields${extraClass ? ' ' + extraClass : ''}">
        <span class="inline-label">${deps.escapeHtml(deps.tr('smart.ratio'))}</span>
        <input type="number" data-param="${wKey}" value="${deps.escapeHtml(deps.getSettings()[wKey] || '')}" placeholder="W">
        <span class="inline-divider">:</span>
        <input type="number" data-param="${hKey}" value="${deps.escapeHtml(deps.getSettings()[hKey] || '')}" placeholder="H">
    </div>`;
}
function renderInlineCustomSizeFields(prefix='', extraClass=''){
    const resKey = prefix ? `${prefix}Resolution` : 'resolution';
    if(deps.getSettings()[resKey] !== 'custom') return '';
    const wKey = prefix ? `${prefix}CustomWidth` : 'customWidth';
    const hKey = prefix ? `${prefix}CustomHeight` : 'customHeight';
    return `<div class="inline-fields${extraClass ? ' ' + extraClass : ''}">
        <span class="inline-label">${deps.escapeHtml(deps.tr('smart.size'))}</span>
        <input type="number" data-param="${wKey}" value="${deps.escapeHtml(deps.getSettings()[wKey] || '')}" placeholder="${deps.escapeHtml(deps.tr('smart.width'))}">
        <span class="inline-divider">×</span>
        <input type="number" data-param="${hKey}" value="${deps.escapeHtml(deps.getSettings()[hKey] || '')}" placeholder="${deps.escapeHtml(deps.tr('smart.height'))}">
    </div>`;
}
global.CanvasSpecControls = {
        configure: configure,
        optionHtml: optionHtml,
        gcdInt: gcdInt,
        imageSizeForRatio: imageSizeForRatio,
        reducedRatioForImage: reducedRatioForImage,
        ratioLabel: ratioLabel,
        resolutionLabel: resolutionLabel,
        imageQualityLabel: imageQualityLabel,
        imageSpecOptions: imageSpecOptions,
        ratioIconClass: ratioIconClass,
        videoAspectIconClass: videoAspectIconClass,
        videoAspectLabel: videoAspectLabel,
        videoAspectOptions: videoAspectOptions,
        renderSizeControls: renderSizeControls,
        renderRatioControl: renderRatioControl,
        renderResolutionControl: renderResolutionControl,
        renderQualityControl: renderQualityControl,
        renderCountVisualControl: renderCountVisualControl,
        renderCountControl: renderCountControl,
        renderCustomRatioControls: renderCustomRatioControls,
        renderCustomSizeControls: renderCustomSizeControls,
        renderComboSpecCount: renderComboSpecCount,
        renderImageSpecPopover: renderImageSpecPopover,
        renderInlineCustomRatioFields: renderInlineCustomRatioFields,
        renderInlineCustomSizeFields: renderInlineCustomSizeFields
    };
})(typeof window !== 'undefined' ? window : globalThis);

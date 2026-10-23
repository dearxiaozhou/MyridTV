//** Node body HTML renderers: smart-loop token chips, toolbars, table/image/group/jimeng bodies. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    function D(name){return typeof deps[name] === 'function' ? deps[name]() : deps[name];}

function loopNumberControlHtml({label, value, key, min=1, max=100, quick=[1,2,3,4,5,6,8,10]}){
    const v = Math.max(min, Math.min(max, Number(value) || min));
    return `<div class="loop-number-control">
        <button class="loop-smart-control loop-number-trigger" type="button"><span>${deps.escapeHtml(label)}</span><strong>${v}</strong></button>
        <div class="loop-number-popover">
            <div class="loop-number-grid">
                ${quick.map(n => `<button type="button" class="loop-smart-control loop-number-cell ${n === v ? 'active' : ''}" data-loop-number="${escapeHtml(key)}" data-loop-value="${n}">${n}</button>`).join('')}
            </div>
            <label class="loop-number-custom">
                <span>${deps.escapeHtml(tr('common.custom'))}</span>
                <input class="loop-smart-control loop-number-input" type="number" min="${min}" max="${max}" step="1" data-loop-number-input="${deps.escapeHtml(key)}" value="${v}">
            </label>
        </div>
    </div>`;
}
function smartLoopTokenLabel(token){
    if(token === '《计数》' || token === '[计数]') return tr('canvas.counterToken');
    return token;
}
function smartLoopTokenChipHtml(token){
    return `<span class="loop-smart-token-chip" contenteditable="false" data-token="${deps.escapeHtml(token)}"><span>${deps.escapeHtml(smartLoopTokenLabel(token))}</span><button class="loop-smart-token-remove" type="button" aria-label="${deps.escapeHtml(tr('common.delete'))}" title="${deps.escapeHtml(tr('common.delete'))}">×</button></span>`;
}
function smartLoopVariableHtml(text){
    return String(text || '').split(/(《计数》|\[计数\])/g).map(part => {
        if(part === '《计数》' || part === '[计数]') return smartLoopTokenChipHtml('《计数》');
        return deps.escapeHtml(part);
    }).join('');
}
function smartLoopEditorText(editor){
    const walk = node => {
        if(node.nodeType === Node.TEXT_NODE) return node.nodeValue || '';
        if(node.nodeType !== Node.ELEMENT_NODE) return '';
        if(node.classList?.contains('loop-smart-token-chip')) return node.dataset.token || '';
        if(node.tagName === 'BR') return '\n';
        return [...node.childNodes].map(walk).join('');
    };
    return [...(editor?.childNodes || [])].map(walk).join('').replace(/\u00a0/g, ' ');
}
function insertSmartLoopToken(editor, token){
    if(!editor) return;
    editor.focus();
    const chipWrap = document.createElement('span');
    chipWrap.innerHTML = smartLoopTokenChipHtml(token);
    const chip = chipWrap.firstElementChild;
    const spacer = document.createTextNode(' ');
    const sel = window.getSelection();
    if(sel && sel.rangeCount && editor.contains(sel.anchorNode)){
        const range = sel.getRangeAt(0);
        range.deleteContents();
        range.insertNode(spacer);
        range.insertNode(chip);
        range.setStartAfter(spacer);
        range.collapse(true);
        sel.removeAllRanges();
        sel.addRange(range);
    } else {
        editor.appendChild(chip);
        editor.appendChild(spacer);
    }
}
function smartLoopBodyHtml(node){
    node.count = deps.smartLoopCount(node);
    node.mode = node.mode === 'parallel' ? 'parallel' : 'serial';
    node.loopStart = Math.max(1, Number(node.loopStart) || 1);
    node.imageBatchSize = Math.max(1, Math.min(100, Number(node.imageBatchSize) || 1));
    node.showPrompt = Boolean(node.showPrompt);
    node.imageInput = Boolean(node.imageInput);
    const imageCount = deps.smartLoopInputImages(node, {index:node.loopStart}).length;
    const loopThumbs = deps.smartNodeInputThumbsHtml(deps.smartLoopPreviewImages(node));
    const promptItems = deps.smartLoopInputPromptItems(node);
    const promptFields = deps.smartLoopPromptFieldValues(node);
    const visiblePromptFields = promptFields.length ? promptFields : [''];
    const promptHint = promptItems.length
        ? deps.trf('smart.loopPromptHintFound', {n:promptItems.length})
        : tr('smart.loopPromptHintVariable');
    const currentUpstreamPrompt = deps.smartLoopSelectedInputPrompt(node, {index:node.loopStart});
    const defaultPrompt = tr('smart.loopDefaultPrompt') || '现在生成第《计数》张卖点图片';
    const loopRunState = deps.smartCascadeRunForLoop(node.id);
    const loopRunning = Boolean(loopRunState);
    const loopStopping = Boolean(loopRunState?.stopRequested);
    return `<div class="loop-smart-card ${node.imageInput ? 'has-image' : ''} ${node.showPrompt ? 'has-prompt' : ''}">
        <div class="loop-smart-row loop-smart-top">
            <div class="loop-smart-seg">
                <button type="button" class="loop-smart-control ${node.mode !== 'parallel' ? 'active' : ''}" data-loop-mode="serial">${deps.escapeHtml(tr('canvas.loopSerial'))}</button>
                <button type="button" class="loop-smart-control ${node.mode === 'parallel' ? 'active' : ''}" data-loop-mode="parallel" title="${deps.escapeHtml(tr('smart.loopParallelTip'))}">${deps.escapeHtml(tr('canvas.loopParallel'))}</button>
            </div>
        </div>
        <div class="loop-smart-row">
            <button class="loop-smart-control loop-smart-toggle ${node.imageInput ? 'active' : ''}" type="button" data-loop-toggle="image"><i data-lucide="image"></i><span>${deps.escapeHtml(tr('canvas.loopImageToggle'))}</span></button>
            <button class="loop-smart-control loop-smart-toggle ${node.showPrompt ? 'active' : ''}" type="button" data-loop-toggle="prompt"><i data-lucide="text-cursor-input"></i><span>${deps.escapeHtml(tr('canvas.loopPromptToggle'))}</span></button>
        </div>
        ${node.imageInput ? `<div class="loop-smart-panel">
            ${loopThumbs}
            <div class="loop-smart-mini">
                ${loopNumberControlHtml({label:tr('canvas.loopBatchSize'), value:node.imageBatchSize, key:'imageBatchSize', max:100, quick:[1,2,3,4,5,6,8,10]})}
            </div>
            <div class="loop-smart-note">${imageCount ? deps.escapeHtml(deps.trf('canvas.loopImageWillOutput', {n:imageCount})) : deps.escapeHtml(tr('canvas.loopImageEmpty'))}</div>
        </div>` : ''}
        ${node.showPrompt ? `<div class="loop-smart-panel prompt-panel">
            ${currentUpstreamPrompt ? `<div class="loop-smart-upstream">
                <div class="loop-smart-upstream-label">${deps.escapeHtml(promptHint)}</div>
                <div class="loop-smart-upstream-text">${deps.escapeHtml(currentUpstreamPrompt)}</div>
            </div>` : ''}
            <div class="loop-smart-prompt-list">
                ${visiblePromptFields.map((value, index) => `<div class="loop-smart-prompt-item">
                    <div class="loop-smart-prompt-index">${index + 1}</div>
                    <div class="loop-smart-control loop-smart-text" contenteditable="true" data-loop-prompt-index="${index}" data-placeholder="${escapeHtml(tr('canvas.loopVariablePlaceholder'))}">${smartLoopVariableHtml(value || (index === 0 && !promptFields.length ? defaultPrompt : ''))}</div>
                    <button class="loop-smart-control loop-smart-icon-btn" type="button" data-loop-prompt-delete="${index}" ${visiblePromptFields.length <= 1 ? 'disabled' : ''} title="${escapeHtml(tr('common.delete'))}" aria-label="${escapeHtml(tr('common.delete'))}">×</button>
                </div>`).join('')}
            </div>
            <div class="loop-smart-row loop-smart-prompt-actions">
                <button class="loop-smart-control loop-smart-token loop-smart-counter-token" type="button" data-loop-token="《计数》">${deps.escapeHtml(tr('canvas.counterToken'))}</button>
                <span class="loop-smart-note">${deps.escapeHtml(promptHint)}</span>
                <button class="loop-smart-control loop-smart-add-prompt" type="button" data-loop-prompt-add="1" title="新增" aria-label="新增"><i data-lucide="plus"></i></button>
            </div>
        </div>` : ''}
        <div class="loop-smart-footer">
            ${loopNumberControlHtml({label:tr('canvas.loopImageStart'), value:node.loopStart, key:'loopStart', max:9999, quick:[1,2,3,4,5,6,8,10]})}
            ${loopNumberControlHtml({label:tr('canvas.loopCount'), value:node.count, key:'count', max:100, quick:[1,2,3,4,5,6,8,10]})}
            <button class="loop-smart-control loop-smart-run ${loopRunning ? 'is-stop' : ''}" type="button" data-loop-run="${deps.escapeHtml(node.id)}" ${loopStopping ? 'disabled' : ''}><i data-lucide="${loopRunning ? 'square' : 'workflow'}"></i><span>${deps.escapeHtml(loopRunning ? deps.smartCascadeStopText(loopStopping) : tr('smart.loopRunAll'))}</span></button>
        </div>
    </div>`;
}
function smartCropButtonHtml(img, index, nodeType){
    // 2026-10-05（老王：视频素材类节点多选时要能看到对齐工具）：
    // 这里原本对「非图片媒体」整段 return ''，于是含视频的媒体节点
    // （type 仍是 smart-image、只是 images[].kind==='video'）连对齐工具一起没了。
    // 现在：视频只跳过图片专属的裁剪/遮罩/画笔/宫格，对齐工具照常渲染，
    // 与图片节点多选时的行为完全一致。
    if(deps.mediaKindForItem(img) !== 'image'){
        // smart-video 这类非图像节点已在节点级 .smart-node-toolbar 里有对齐按钮（见
        // smart-canvas.js 的 `${!isImageNode ? smartNodeToolbarHtml() : ''}`），
        // 这里再渲染一份会重复，故只对「图像节点里的视频」补渲染。
        if(nodeType && nodeType !== 'smart-image') return '';
        const vMultiDisabled = deps.selectedLayoutNodes().length >= 2 ? '' : ' disabled';
        const vGroupDisabled = deps.canGroupSelectedNodes() ? '' : ' disabled';
        const vLayoutButtons = [
            ['group', 'group', '打组', vGroupDisabled],
            ['align-left', 'align-left', '左对齐', vMultiDisabled],
            ['align-top', 'align-start-horizontal', '顶对齐', vMultiDisabled],
            ['same-size', 'maximize-2', '统一尺寸', vMultiDisabled],
            ['distribute-horizontal', 'columns-3', '左右等距', vMultiDisabled],
            ['distribute-vertical', 'rows-3', '上下等距', vMultiDisabled]
        ];
        return `<div class="smart-image-tools">
            <span class="smart-layout-tools${vMultiDisabled ? ' is-inactive' : ''}">
                ${vLayoutButtons.map(([action, icon, title, disabled]) => `<button class="smart-node-action${disabled ? ' disabled' : ''}" type="button" data-smart-node-action="${action}" title="${title}" aria-label="${title}"${disabled}><i data-lucide="${icon}"></i></button>`).join('')}
            </span>
        </div>`;
    }
    const buttons = [
    ['crop', 'crop', '编辑裁剪'],
        ['mask', 'brush', '遮罩'],
        ['brush', 'paintbrush', '画笔'],
        ['grid', 'grid-3x3', '宫格切分'],
        // 镜像：一次性动作，不进编辑器（由 openSmartImageTool 拦截后弹方向菜单）
        ['mirror', 'flip-horizontal', '镜像']
    ];
    const multiDisabled = deps.selectedLayoutNodes().length >= 2 ? '' : ' disabled';
    const groupDisabled = deps.canGroupSelectedNodes() ? '' : ' disabled';
 const layoutButtons = [
 ['group', 'group', '打组', groupDisabled],
 ['align-left', 'align-left', '左对齐', multiDisabled],
 ['align-top', 'align-start-horizontal', '顶对齐', multiDisabled],
 ['same-size', 'maximize-2', '统一尺寸', multiDisabled],
 ['distribute-horizontal', 'columns-3', '左右等距', multiDisabled],
 ['distribute-vertical', 'rows-3', '上下等距', multiDisabled]
 ];
    return `<div class="smart-image-tools">
        ${buttons.map(([mode, icon, title]) => `<button class="smart-crop-action" type="button" data-crop-index="${index}" data-tool-mode="${mode}" title="${title}" aria-label="${title}"><i data-lucide="${icon}"></i></button>`).join('')}
        <span class="smart-layout-tools${multiDisabled ? ' is-inactive' : ''}">
            <span class="smart-tools-separator"></span>
            ${layoutButtons.map(([action, icon, title, disabled]) => `<button class="smart-node-action${disabled ? ' disabled' : ''}" type="button" data-smart-node-action="${action}" title="${title}" aria-label="${title}"${disabled}><i data-lucide="${icon}"></i></button>`).join('')}
        </span>
    </div>`;
}
function smartNodeToolbarHtml(){
    // 节点级工具栏（非图片节点：Prompt / Loop / 镜头表 / 3D预演 等通用布局功能）
    const multiDisabled = deps.selectedLayoutNodes().length >= 2 ? '' : ' disabled';
    const groupDisabled = deps.canGroupSelectedNodes() ? '' : ' disabled';
    const layoutButtons = [
        ['group', 'group', '打组', groupDisabled],
        ['align-left', 'align-left', '左对齐', multiDisabled],
        ['align-top', 'align-start-horizontal', '顶对齐', multiDisabled],
        ['same-size', 'maximize-2', '统一尺寸', multiDisabled],
        ['distribute-horizontal', 'columns-3', '左右等距', multiDisabled],
        ['distribute-vertical', 'rows-3', '上下等距', multiDisabled]
    ];
    return `<div class="smart-node-toolbar">
        ${layoutButtons.map(([action, icon, title, disabled]) => `<button class="smart-node-action${disabled ? ' disabled' : ''}" type="button" data-smart-node-action="${action}" title="${title}" aria-label="${title}"${disabled}><i data-lucide="${icon}"></i></button>`).join('')}
    </div>`;
}
function openSmartImageTool(nodeId, imageIndex, mode, event){
    if(mode === 'free-crop') return CanvasImageCrop.begin(nodeId, imageIndex, event);
    // 2026-10-05 镜像：一次性动作，不进图片编辑器（裁剪/遮罩/画笔才进），
    // 直接弹方向小菜单（水平/垂直/180°），选完立刻执行像素级镜像。
    if(mode === 'mirror'){
        event?.preventDefault?.();
        event?.stopPropagation?.();
        event?.stopImmediatePropagation?.();
        return deps.openImageMirrorMenu?.(nodeId, imageIndex, event?.currentTarget || null);
    }
    event?.preventDefault?.();
    event?.stopPropagation?.();
    event?.stopImmediatePropagation?.();
    CanvasImageCrop.stop();
    deps.setSelectedId(nodeId);
    deps.setSelectedIds([]);
    deps.setSelectedImage({nodeId, index:imageIndex});
    deps.openImageEditor(nodeId, imageIndex);
    deps.setImageEditMode(mode, true);
}
function tableNodeBodyHtml(node){
    const data = node.tableData || {cols:[], rows:[]};
    const thead = data.cols.length ? `<thead><tr>${data.cols.map(c => `<th>${deps.escapeHtml(c)}</th>`).join('')}</tr></thead>` : '';
    const tbody = data.rows.length ? `<tbody>${data.rows.map(r => `<tr>${r.map(c => `<td>${deps.escapeHtml(c)}</td>`).join('')}</tr>`).join('')}</tbody>` : '';
    const resizeCss = data.cols.length ? ` style="min-width:${Math.max(data.cols.length * 120, 300)}px"` : '';
    return `<div class="smart-table-wrap"${resizeCss}><table class="smart-table">${thead}${tbody}</table></div>`;
}
function smartImageMetaBodyHtml(node){
    const prompt = String(node.prompt || '').trim();
    const content = String(node.content || '').trim();
    return `<div class="smart-image-meta-card">
        ${content ? `<div class="smart-image-meta-block"><div class="smart-image-meta-label">说明</div><textarea class="smart-image-meta-text smart-image-content-text" data-meta-field="content" placeholder="说明">${deps.escapeHtml(content)}</textarea></div>` : ''}
        <div class="smart-image-meta-block"><div class="smart-image-meta-label">提示词</div><textarea class="smart-image-meta-text smart-image-prompt-text" data-meta-field="prompt" placeholder="提示词">${deps.escapeHtml(prompt)}</textarea></div>
    </div>`;
}
function nodeBodyHtml(node, layout){
    if(node.type === 'smart-speech') return global.CanvasSpeech.body(node);
    if(node.type === 'smart-table') return tableNodeBodyHtml(node);
    if(deps.isCanvasGroupNode(node)) return '';
    // A generation clears its output list before the result arrives. Keep that state
    // in the loading branch instead of rendering the saved prompt as an empty node.
    const isGeneratingImage = Boolean(node.pending || node.queued || node.jimengPending?.submitId);
    // 2026-10-12：跑过但被中断/失败、输出已清空的生成节点不许落进「说明/提示词」meta 卡
    // —— 视频节点的草稿在 promptDraftText、meta 卡绑 node.prompt，落进去必然是空提示词框的伪装说明卡。
    // 按拍板（10-10 01:00「图片节点失败了就是失败的图片节点」/ 01:21「不加提示 UI」）回落到普通空图片节点形态。
    // 2026-10-13 补：role=generation 的生成节点（含从没跑过的 Agent 节点）同样不走 meta 卡 ——
    // 只要空输出，就按空图片节点渲染；只有非生成的记事类节点才用「说明/提示词」卡。
    const hasRunEvidence = Boolean(node.runStartedAt || node.runAt || node.comfyPromptId || node.comfyRunToken || (Array.isArray(node.lastTaskIds) && node.lastTaskIds.length));
    const isGenerationNode = node.role === 'generation' || hasRunEvidence;
    if((node.type === 'smart-image' || !node.type) && !(node.images || []).length && !isGeneratingImage && (node.prompt || node.content) && !isGenerationNode) return smartImageMetaBodyHtml(node);
    if(node.type === 'smart-prompt') return deps.promptNodeBodyHtml(node);
    if(node.type === 'smart-loop') return smartLoopBodyHtml(node);
    const imgs = (node.images || []).map(D("imageForDisplay"));
    if(node.groupLayout?.mode === 'preserve') return preservedGroupBodyHtml(node, imgs);
    if(node.jimengPending && node.jimengPending.submitId && imgs.length === 0){
        return jimengPendingBodyHtml(node, layout);
    }
    // 2026-09-23：comfyStatus queued/running 的节点（级联槽位等没有 pending 标志）也走加载占位，
    // 不能掉进下面的「空节点上传占位」—— 否则会出现一个大黑窗 + 三个幽灵图标 + 排队徽标的怪状态，
    // 且尺寸沿用节点上次的 w/h，看起来就是「点开排队节点窗口变大」。
    const comfyBusy = node.comfyStatus === 'queued' || node.comfyStatus === 'running';
    if((node.queued || comfyBusy) && imgs.length === 0 && !node.pending){
        return `<div class="loading-cell single queued" style="width:${layout.width}px;height:${layout.height}px">${deps.comfyNodeProgressBarHtml(node)}</div>`;
    }
    if(node.pending && imgs.length === 0){
        const count = Math.max(1, Number(node.pending) || 1);
        if(count <= 1) return `<div class="loading-cell single" style="width:${layout.width}px;height:${layout.height}px">${deps.comfyNodeProgressBarHtml(node)}</div>`;
        const cols = Math.min(4, Math.max(2, Math.ceil(Math.sqrt(count))));
        const rows = Math.ceil(count / cols);
        return `<div class="loading-skeleton" style="grid-template-columns:repeat(${cols}, 1fr);grid-template-rows:repeat(${rows}, 1fr);width:${layout.width}px;height:${layout.height}px;padding:8px;box-sizing:border-box">${Array.from({length:count}).map(() => `<div class="loading-cell"></div>`).join('')}</div>`;
    }
    if(imgs.length > 1){
        let audioCount = 0;
        const items = imgs.map((img, i) => {
            const audioIndex = deps.isAudioMediaItem(img) ? ++audioCount : 0;
            const size = deps.aspectGroupImageSize(img, layout.thumb);
            return `<div class="thumb-item ${D("selectedImage").nodeId === node.id && D("selectedImage").index === i ? 'image-selected' : ''}" data-image-index="${i}" data-media-signature="${D("escapeAttr")(`${deps.mediaKindForItem(img)}:${img?.url || ''}`)}" style="--thumb-w:${size.width}px;--thumb-h:${size.height}px">${deps.thumbMediaHtml(img, audioIndex)}${deps.smartImageNameLabelHtml(img, i)}${deps.imageResolutionBadgeHtml(img)}${smartCropButtonHtml(img, i, node.type)}<button class="mini-x image-delete" type="button" data-image-index="${i}" title="${deps.escapeHtml(tr('smart.deleteImage'))}"><i data-lucide="trash-2"></i></button></div>`;
        }).join('');
        return `<div class="ratio-thumb-grid" style="--thumb-cols:${layout.cols};--thumb-size:${layout.thumb}px">${items}</div>`;
    }
    if(imgs[0]) return `<div class="image-wrap ${D("selectedImage").nodeId === node.id && D("selectedImage").index === 0 ? 'image-selected' : ''}" data-image-index="0" data-media-signature="${D("escapeAttr")(`${deps.mediaKindForItem(imgs[0])}:${imgs[0]?.url || ''}`)}" style="--node-img-w:${layout.width}px;--node-img-h:${layout.height}px">${deps.singleMediaHtml(imgs[0], layout.width, layout.height)}${deps.smartImageNameLabelHtml(imgs[0], 0)}${deps.imageResolutionBadgeHtml(imgs[0])}${smartCropButtonHtml(imgs[0], 0, node.type)}${deps.comfyNodeProgressBarHtml(node)}<button class="mini-x image-delete" type="button" data-image-index="0" title="${deps.escapeHtml(tr('smart.deleteImage'))}"><i data-lucide="trash-2"></i></button></div>`;
    return `<div class="node-drop" data-upload-action="files">
        <span class="node-media-hint"><i data-lucide="image"></i><i data-lucide="square-play"></i><i data-lucide="music"></i></span>
        <div class="node-drop-hint">${deps.escapeHtml(tr('smart.createImportNodeSub'))}</div>
        <button class="upload-node-btn" type="button" data-upload-action="files"><i data-lucide="upload"></i><span>上传</span></button>
    </div>`;
}
function preservedGroupBodyHtml(node, imgs){
    return `<div class="preserved-group-canvas">${imgs.map((img, index) => {
        const box = img.groupPosition || {};
        const w = Math.max(28, Math.round(Number(box.w) || 96));
        const h = Math.max(28, Math.round(Number(box.h) || 96));
        const x = Math.max(0, Math.round(Number(box.x) || 0));
        const y = Math.max(0, Math.round(Number(box.y) || 0));
        return `<div class="preserved-group-item image-wrap ${selectedImage.nodeId === node.id && selectedImage.index === index ? 'image-selected' : ''}" data-image-index="${index}" data-media-signature="${escapeAttr(`${mediaKindForItem(img)}:${img?.url || ''}`)}" style="left:${x}px;top:${y}px;width:${w}px;height:${h}px;--node-img-w:${w}px;--node-img-h:${h}px">${deps.singleMediaHtml(img, w, h)}${deps.smartImageNameLabelHtml(img, index)}${deps.imageResolutionBadgeHtml(img)}${smartCropButtonHtml(img, index, node.type)}<button class="mini-x image-delete" type="button" data-image-index="${index}" title="${escapeHtml(tr('smart.deleteImage'))}"><i data-lucide="trash-2"></i></button></div>`;
    }).join('')}</div>`;
}
function jimengPendingBodyHtml(node, layout){
    const jp = node.jimengPending || {};
    const querying = Boolean(jp.querying);
    const queueText = deps.jimengQueueText(jp.queueInfo);
    return `<div class="jimeng-pending-cell loading-cell single" style="width:${layout.width}px;height:${layout.height}px">
        <div class="jimeng-pending-overlay">
            <div class="jimeng-pending-spinner"><i data-lucide="loader-2"></i></div>
            <div class="jimeng-pending-text">${deps.escapeHtml(queueText)}</div>
            <div class="jimeng-pending-sub">任务未丢失，可继续等待或手动查询</div>
            <button class="jimeng-pending-query" type="button" data-jimeng-query="${D("escapeAttr")(node.id)}" ${querying ? 'disabled' : ''}><i data-lucide="${querying ? 'loader-2' : 'refresh-cw'}"></i><span>${querying ? '查询中…' : '查询结果'}</span></button>
        </div>
    </div>`;
}
function nowMs(){ return Date.now(); }

    global.CanvasNodeBodyHtml = {
        configure,
        loopNumberControlHtml,
        smartLoopTokenLabel,
        smartLoopTokenChipHtml,
        smartLoopVariableHtml,
        smartLoopEditorText,
        insertSmartLoopToken,
        smartLoopBodyHtml,
        smartCropButtonHtml,
        smartNodeToolbarHtml,
        openSmartImageTool,
        tableNodeBodyHtml,
        smartImageMetaBodyHtml,
        nodeBodyHtml,
        preservedGroupBodyHtml,
        jimengPendingBodyHtml,
        nowMs,
    };
})(typeof window !== 'undefined' ? window : this);

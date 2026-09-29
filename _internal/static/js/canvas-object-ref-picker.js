//** Canvas object-reference picker + input-thumb drag reorder interactions. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    function D(name){return typeof deps[name] === 'function' ? deps[name]() : deps[name];}

function openCanvasObjectRefPicker(consumerId){
    const consumer = D("nodes").find(n => n.id === (consumerId || D("canvasObjectRefConsumerId")));
    if(!consumer) return;
    deps.setCanvasObjectRefConsumerId(consumer.id);
    deps.setCanvasObjectRefQuery('');
    deps.setCanvasObjectRefKind('all');
    deps.setCanvasObjectRefPickerOpen(true);
    renderCanvasObjectRefPicker();
    deps.canvasObjectRefPickerEl()?.classList.add('open');
}
function closeCanvasObjectRefPicker(){
    deps.setCanvasObjectRefPickerOpen(false);
    deps.canvasObjectRefPickerEl()?.classList.remove('open');
}
function toggleCanvasObjectRefPicker(consumerId){
    const el = deps.canvasObjectRefPickerEl();
    if(D("canvasObjectRefPickerOpen") && el?.classList.contains('open')) closeCanvasObjectRefPicker();
    else openCanvasObjectRefPicker(consumerId);
}
function canvasSetCandidatesFor(consumerId){
    return deps.canvasSetSourceNodes()
        .filter(n => n.id !== consumerId)
        .map(node => ({node, kind:deps.canvasNodeResultKind(node), thumb:deps.imagesForNode(node)[0] || null}))
        .filter(item => item.kind);
}
function canvasObjectRefCandidateHtml(item, selected){
    const kindKey = item.kind === 'image' ? 'smart.kindImage'
        : item.kind === 'video' ? 'smart.kindVideo'
        : item.kind === 'audio' ? 'smart.kindAudio'
        : item.kind === 'text' ? 'smart.kindText' : 'smart.kindFile';
    const thumb = item.thumb
        ? `<img src="${deps.escapeHtml(deps.canvasThumbnailUrl(item.thumb, 96))}" data-original-src="${D("escapeAttr")(item.thumb.url || '')}" alt="" draggable="false" loading="lazy">`
        : `<span class="object-ref-icon"><i data-lucide="${item.kind === 'text' ? 'file-text' : 'file'}"></i></span>`;
    return `<button class="object-ref-item ${selected ? 'is-selected' : ''}" type="button" data-object-ref-pick="${D("escapeAttr")(item.node.id)}"><span class="object-ref-thumb">${thumb}</span><span class="object-ref-meta"><span class="object-ref-title">${deps.escapeHtml(item.node.title || tr('smart.title'))}</span><span class="object-ref-kind">${deps.escapeHtml(tr(kindKey))}</span></span><span class="object-ref-check">${selected ? '<i data-lucide="check"></i>' : ''}</span></button>`;
}
function renderCanvasObjectRefPicker(){
    const el = deps.canvasObjectRefPickerEl();
    if(!el) return;
    const consumer = D("nodes").find(n => n.id === D("canvasObjectRefConsumerId"));
    if(!consumer){ closeCanvasObjectRefPicker(); return; }
    const refs = deps.canvasObjectReferencesFor(consumer);
    const kindKeys = ['all','image','video','audio','text'];
    const allCandidates = canvasSetCandidatesFor(consumer.id);
    const items = allCandidates
        .filter(item => D("canvasObjectRefKind") === 'all' || item.kind === D("canvasObjectRefKind"))
        .filter(item => !D("canvasObjectRefQuery") || String(item.node.title || '').toLowerCase().includes(D("canvasObjectRefQuery")));
    const listHtml = items.length
        ? items.map(item => canvasObjectRefCandidateHtml(item, refs.some(ref => ref.sourceNodeId === item.node.id))).join('')
        : `<div class="object-ref-empty">${deps.escapeHtml(allCandidates.length ? tr('smart.objectRefNoMatch') : tr('smart.objectRefEmpty'))}</div>`;
    const kindLabel = key => tr(key === 'all' ? 'smart.tplAll' : key === 'image' ? 'smart.kindImage' : key === 'video' ? 'smart.kindVideo' : key === 'audio' ? 'smart.kindAudio' : 'smart.kindText');
    el.innerHTML = `
        <div class="object-ref-head"><span>${deps.escapeHtml(tr('smart.objectRef'))}</span><button class="object-ref-close" type="button" title="${D("escapeAttr")(tr('smart.close'))}"><i data-lucide="x"></i></button></div>
        <div class="object-ref-search"><i data-lucide="search"></i><input type="search" placeholder="${D("escapeAttr")(tr('smart.objectRefSearch'))}" value="${D("escapeAttr")(D("canvasObjectRefQuery"))}"></div>
        <div class="object-ref-kinds">${kindKeys.map(key => `<button class="object-ref-kind-chip ${canvasObjectRefKind === key ? 'active' : ''}" type="button" data-object-ref-kind="${key}">${deps.escapeHtml(kindLabel(key))}</button>`).join('')}</div>
        <div class="object-ref-list">${listHtml}</div>`;
    el.querySelector('.object-ref-close')?.addEventListener('click', e => { e.preventDefault(); closeCanvasObjectRefPicker(); });
    const search = el.querySelector('.object-ref-search input');
    if(search){
        search.addEventListener('input', () => {
            deps.setCanvasObjectRefQuery(String(search.value || '').trim().toLowerCase());
            renderCanvasObjectRefPicker();
            const next = deps.canvasObjectRefPickerEl()?.querySelector('.object-ref-search input');
            if(next){ next.focus(); next.setSelectionRange(next.value.length, next.value.length); }
        });
    }
    el.querySelectorAll('[data-object-ref-kind]').forEach(btn => btn.addEventListener('click', e => {
        e.preventDefault();
        deps.setCanvasObjectRefKind(btn.dataset.objectRefKind || 'all');
        renderCanvasObjectRefPicker();
    }));
    el.querySelectorAll('[data-object-ref-pick]').forEach(btn => btn.addEventListener('click', e => {
        e.preventDefault();
        toggleCanvasObjectReference(D("canvasObjectRefConsumerId"), btn.dataset.objectRefPick);
    }));
    if(window.lucide) lucide.createIcons();
}
function toggleCanvasObjectReference(consumerId, sourceNodeId){
    const consumer = D("nodes").find(n => n.id === consumerId);
    const source = D("nodes").find(n => n.id === sourceNodeId);
    if(!consumer || !source || consumer.id === source.id) return;
    if(source.canvasSetEnabled !== true){ deps.toast(tr('smart.objectRefNeedSet')); return; }
    deps.pushUndo();
    const refs = deps.canvasObjectReferencesFor(consumer).slice();
    const index = refs.findIndex(ref => ref.sourceNodeId === sourceNodeId);
    if(index >= 0) refs.splice(index, 1);
    else refs.push({id:deps.uid('canvasobjref'), sourceNodeId, versionMode:'latest', createdAt:Date.now()});
    if(refs.length) consumer.objectReferences = refs;
    else delete consumer.objectReferences;
    deps.renderInputThumbsRow(consumer);
    renderCanvasObjectRefPicker();
    deps.scheduleSave();
}
function removeCanvasObjectReference(consumerId, referenceId){
    const consumer = D("nodes").find(n => n.id === consumerId);
    if(!consumer || !referenceId) return;
    deps.pushUndo();
    const refs = deps.canvasObjectReferencesFor(consumer).filter(ref => ref.id !== referenceId);
    if(refs.length) consumer.objectReferences = refs;
    else delete consumer.objectReferences;
    deps.renderInputThumbsRow(consumer);
    if(D("canvasObjectRefPickerOpen")) renderCanvasObjectRefPicker();
    deps.scheduleSave();
}
function bindCanvasObjectRefActions(node){
    if(node) deps.setCanvasObjectRefConsumerId(node.id);
    D("inputThumbsRow")?.querySelectorAll('[data-object-ref-open]').forEach(btn => {
        btn.onclick = event => {
            event.preventDefault();
            event.stopPropagation();
            toggleCanvasObjectRefPicker(node?.id);
        };
    });
    D("inputThumbsRow")?.querySelectorAll('[data-object-ref-remove]').forEach(btn => {
        btn.onclick = event => {
            event.preventDefault();
            event.stopPropagation();
            removeCanvasObjectReference(node?.id, btn.dataset.objectRefRemove);
        };
    });
}
function bindInputThumbsDrag(node, items){
    if(!D("inputThumbsRow")) return;
    D("inputThumbsRow").querySelectorAll('.input-thumb').forEach(el => {
        const index = Number(el.dataset.thumbIndex || 0);
        el.setAttribute('draggable', 'false');
        el.addEventListener('mousedown', e => {
            if(e.button !== 0 || !node || !items?.length) return;
            if(el.classList.contains('input-self')) return;
            e.preventDefault();
            e.stopPropagation();
            deps.setInputThumbDragState({
                nodeId:node.id,
                from:index,
                target:index,
                before:true,
                startX:e.clientX,
                startY:e.clientY,
                active:false,
                items
            });
            if (typeof CanvasInteractionMachine !== 'undefined') CanvasInteractionMachine.begin('input-thumb-drag');
        });
        el.addEventListener('click', e => {
            e.preventDefault();
            e.stopPropagation();
        });
    });
}
function bindInputThumbVideoActions(){
    D("inputThumbsRow")?.querySelectorAll('[data-manual-video-url]').forEach(btn => {
        btn.onclick = async event => {
            event.preventDefault();
            event.stopPropagation();
            try {
                await deps.setCurrentSmartManualVideoUrl();
            } catch(e) {
                deps.toast((e.message || '设置视频网址失败').slice(0, 180));
            }
        };
    });
    D("inputThumbsRow")?.querySelectorAll('[data-temp-sh-upload-video]').forEach(btn => {
        btn.onclick = async event => {
            event.preventDefault();
            event.stopPropagation();
            try {
                await deps.uploadCurrentSmartVideosToCloud();
            } catch(e) {
                deps.toast((e.message || '云端上传失败').slice(0, 180));
            }
        };
    });
}
function applyInputOrderFromImageList(currentNode, items){
    // 按缩略图视觉顺序推导节点顺序（每个节点取其首张图的位置），回写 inputNodeIds 并返回该顺序
    const order = [];
    (items || []).forEach(img => {
        const id = img?.nodeId;
        if(id && !order.includes(id)) order.push(id);
    });
    if(!order.length || !currentNode) return null;
    currentNode.inputNodeIds = order;
    return order;
}
function reorderInputThumb(currentNode, items, from, to){
    // items are already sourced from inputImagesFor → multiple source D("nodes") possible.
    // Same source node: reorder images inside that node.
    // Different source nodes: reorder current node's upstream input order.
    if(from < 0 || to < 0 || from >= items.length || to >= items.length) return;
    const fromImg = items[from];
    const toImg = items[to];
    if(!fromImg || !toImg) return;
    // 与函数内 splice+insert 的移动语义一致：把第 from 张移到第 to 位（拖动落点传的就是插入位）
    const applied = items.slice();
    const [movedImg] = applied.splice(from, 1);
    applied.splice(to, 0, movedImg);
    if(fromImg.nodeId === toImg.nodeId){
        const src = nodes.find(n => n.id === fromImg.nodeId);
        if(!src) return;
        pushUndo();
        const fi = Number(fromImg.imageIndex);
        const ti = Number(toImg.imageIndex);
        if(Number.isFinite(fi) && Number.isFinite(ti) && (src.images || [])[fi]){
            const arr = src.images;
            const item = arr.splice(fi, 1)[0];
            arr.splice(ti, 0, item);
        }
        // 同节点内换序也要让连线顺序跟上缩略图视觉顺序（用户要求 2026-09-11）
        applyInputOrderFromImageList(currentNode, applied);
        render();
        scheduleSave();
        return;
    }
    if(!currentNode?.id || !fromImg.nodeId || !toImg.nodeId) return;
    pushUndo();
    // 以交换后的缩略图视觉顺序为准推导节点顺序（旧实现把图片下标当节点下标用，跨节点拖动必错位）
    const order = applyInputOrderFromImageList(currentNode, applied);
    if(!order){
        discardPendingUndo?.();
        return;
    }
    if(canvas?.connections){
        const ranked = new Map(order.map((id, index) => [id, index]));
        const indexed = canvas.connections.map((conn, index) => ({conn, index}));
        indexed.sort((a, b) => {
            const ar = a.conn?.to === currentNode.id ? (ranked.get(a.conn.from) ?? Number.MAX_SAFE_INTEGER) : Number.MAX_SAFE_INTEGER;
            const br = b.conn?.to === currentNode.id ? (ranked.get(b.conn.from) ?? Number.MAX_SAFE_INTEGER) : Number.MAX_SAFE_INTEGER;
            if(ar !== br) return ar - br;
            return a.index - b.index;
        });
        canvas.connections = indexed.map(item => item.conn);
    }
    render();
    scheduleSave();
}
function isSupportedUploadFile(file){
    const type = String(file?.type || '').toLowerCase();
    const name = String(file?.name || '').toLowerCase();
    return type.startsWith('image/') || type.startsWith('video/') || type.startsWith('audio/')
        || /\.(png|jpe?g|webp|gif|mp4|webm|mov|m4v|mp3|wav|m4a|aac|ogg|flac)(\?|$)/.test(name);
}

    global.CanvasObjectRefPicker = {
        configure,
        openCanvasObjectRefPicker,
        closeCanvasObjectRefPicker,
        toggleCanvasObjectRefPicker,
        canvasSetCandidatesFor,
        canvasObjectRefCandidateHtml,
        renderCanvasObjectRefPicker,
        toggleCanvasObjectReference,
        removeCanvasObjectReference,
        bindCanvasObjectRefActions,
        bindInputThumbsDrag,
        bindInputThumbVideoActions,
        applyInputOrderFromImageList,
        reorderInputThumb,
        isSupportedUploadFile,
    };
})(typeof window !== 'undefined' ? window : this);

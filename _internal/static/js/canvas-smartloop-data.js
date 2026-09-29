//** Smart-loop input data layer: image/prompt resolution across lines, loops, workflow inputs and mentions. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    function D(name){return typeof deps[name] === 'function' ? deps[name]() : deps[name];}

function smartLoopInputPromptItems(node){
    if(!node?.showPrompt || D("smartLoopPromptVisiting").has(node.id)) return [];
    D("smartLoopPromptVisiting").add(node.id);
    try {
        return deps.inputNodesFor(node).flatMap(input => {
            const text = textForNode(input);
            return text ? [text] : [];
        }).filter(Boolean);
    } finally {
        D("smartLoopPromptVisiting").delete(node.id);
    }
}
function smartLoopSelectedInputPrompt(node, ctx=D("smartLoopContext")){
    const items = smartLoopInputPromptItems(node);
    if(!items.length) return '';
    const startBase = Math.max(1, Number(node?.loopStart) || 1);
    const index = Math.max(1, Number(ctx?.index || startBase) || startBase);
    return items[(index - 1) % items.length] || '';
}
function smartLoopPrompt(node, ctx=D("smartLoopContext")){
    if(!node?.showPrompt) return '';
    const count = deps.smartLoopCount(node);
    const startBase = Math.max(1, Number(node.loopStart) || 1);
    const index = Math.max(1, Number(ctx?.index || startBase) || startBase);
    const total = Math.max(1, Number(ctx?.total || count) || count);
    const selected = smartLoopSelectedInputPrompt(node, ctx);
    const localPrompt = deps.smartLoopSelectedLocalPrompt(node, ctx);
    const combined = [selected, localPrompt].map(text => String(text || '').trim()).filter(Boolean).join('\n\n');
    return String(combined || '')
        .replaceAll('《计数》', String(index))
        .replaceAll('[计数]', String(index))
        .replaceAll(`[${tr('canvas.counterToken')}]`, String(index))
        .replaceAll('《总数》', String(total))
        .replaceAll('[总数]', String(total))
        .replaceAll('《进度》', `${index}/${total}`)
        .replaceAll('[进度]', `${index}/${total}`)
        .trim();
}
function smartLoopInputImages(node, ctx=D("smartLoopContext")){
    if(!node?.imageInput) return [];
    const refs = deps.inputNodesFor(node).flatMap(input => {
        if(input?.type === 'smart-loop') return smartLoopInputImages(input, ctx);
        return deps.imagesForNode(input);
    }).filter(img => img?.url);
    if(!refs.length) return [];
    const startBase = Math.max(1, Number(node.loopStart) || 1);
    const batchSize = Math.max(1, Math.min(100, Number(node.imageBatchSize) || 1));
    const currentIndex = Math.max(1, Number(ctx?.index || startBase) || startBase);
    return refs.slice(Math.max(0, currentIndex - 1), Math.max(0, currentIndex - 1) + batchSize)
        .map((img, i) => ({...img, name:img.name || deps.trf('canvas.loopImageLabel', {n:currentIndex + i})}));
}
function smartLoopPreviewImages(node){
    if(!node?.imageInput) return [];
    return deps.inputNodesFor(node).flatMap(input => {
        if(input?.type === 'smart-loop') return smartLoopInputImages(input, {index:Number(node.loopStart) || 1});
        return deps.imagesForNode(input);
    }).filter(img => img?.url);
}
function outputImagesForNode(node, consume=false, ctx=D("smartLoopContext")){
    if(node?.type === 'smart-loop') return smartLoopInputImages(node, ctx);
    return deps.imagesForNode(node).filter(img => img?.url);
}
function selfReferenceImagesForNode(node, consume=false, ctx=D("smartLoopContext")){
    return outputImagesForNode(node, consume, ctx).filter(img => img?.url);
}
function textForNode(node, ctx=D("smartLoopContext")){
    if(!node) return '';
    if(node.type === 'smart-prompt') return node.text || '';
    if(node.type === 'smart-loop') return smartLoopPrompt(node, ctx);
    if(node.type === 'smart-image' || !node.type) return deps.nodeTextOutput(node);
    return '';
}
function promptInputNodesFor(node){
    return deps.inputNodesFor(node).filter(input => Boolean(textForNode(input)));
}
function inputPromptTextFor(node, ctx=D("smartLoopContext")){
    // 无线引用里的文本节点与连线文本节点一样并入提示词正文
    const directText = [...canvasObjectReferenceTextNodes(node), ...promptInputNodesFor(node).map(input => textForNode(input, ctx))].filter(Boolean);
    const relayText = Array.isArray(ctx?.relayPromptNodeIds)
        ? ctx.relayPromptNodeIds.map(id => D("nodes").find(n => n.id === id)).map(input => textForNode(input, ctx)).filter(Boolean)
        : [];
    const seen = new Set();
    return [...directText, ...relayText].filter(text => {
        const key = String(text || '').trim();
        if(!key || seen.has(key)) return false;
        seen.add(key);
        return true;
    }).join('\n\n');
}
function upstreamLoopPromptNodesFor(node){
    return promptInputNodesFor(node).filter(input => input?.type === 'smart-loop' && input.showPrompt);
}
function inputImagesFor(node, consume=false, ctx=D("smartLoopContext")){
    return deps.inputNodesFor(node).flatMap(input => outputImagesForNode(input, consume, ctx));
}
function workflowInputImagesFor(node, consume=false, ctx=D("smartLoopContext")){
    return deps.workflowInputNodesFor(node).flatMap(input => outputImagesForNode(input, consume, ctx));
}
function inputRefKey(img){
    if(!img?.url) return '';
    const nodeId = img.nodeId || '';
    const imageIndex = Number.isFinite(Number(img.imageIndex)) ? String(Number(img.imageIndex)) : '';
    if(nodeId && imageIndex !== '') return `${nodeId}|${imageIndex}`;
    return `url|${img.url}`;
}
function blockedInputRefKeys(node){
    return new Set(Array.isArray(node?.blockedInputRefs) ? node.blockedInputRefs.filter(Boolean) : []);
}
function isInputRefBlocked(node, img){
    if(!node || !img?.url) return false;
    return blockedInputRefKeys(node).has(inputRefKey(img));
}
function activeInputImagesFor(node, consume=false, ctx=D("smartLoopContext")){
    return inputImagesFor(node, consume, ctx).filter(img => img?.url && !isInputRefBlocked(node, img));
}
function toggleInputRefBlocked(node, img){
    if(!node || !img?.url) return;
    const key = inputRefKey(img);
    if(!key) return;
    deps.pushUndo();
    const blocked = blockedInputRefKeys(node);
    if(blocked.has(key)) blocked.delete(key);
    else blocked.add(key);
    node.blockedInputRefs = [...blocked];
    if(!node.blockedInputRefs.length) delete node.blockedInputRefs;
    deps.renderInputThumbsRow(node);
    deps.scheduleSave();
}
function defaultReferenceImagesFor(node, consume=false, ctx=D("smartLoopContext")){
    if(!node) return [];
    // 节点自身输出图不参与输入引用（用户要求 2026-08-16）
    const upstream = deps.defaultInputImagesFor(node, consume, ctx);
    if(deps.smartImageUsesWorkflowInput(node, ctx)) return uniqueReferenceImages(upstream);
    return uniqueReferenceImages(upstream);
}
function lineConnectionsFor(node){
    if(!node) return [];
    return (D("canvas")?.connections || []).filter(conn => {
        if(!conn?.from || !conn?.to || conn.from === conn.to) return false;
        return ['input', 'flow'].includes(conn.kind || 'flow');
    });
}
function connectedLineNodeIds(node){
    if(!node) return [];
    const conns = lineConnectionsFor(node);
    const upstream = [];
    const downstream = [];
    const seenUp = new Set([node.id]);
    const seenDown = new Set([node.id]);
    const walkUp = id => {
        conns.filter(conn => conn.to === id).forEach(conn => {
            if(seenUp.has(conn.from)) return;
            seenUp.add(conn.from);
            walkUp(conn.from);
            upstream.push(conn.from);
        });
    };
    const walkDown = id => {
        conns.filter(conn => conn.from === id).forEach(conn => {
            if(seenDown.has(conn.to)) return;
            seenDown.add(conn.to);
            downstream.push(conn.to);
            walkDown(conn.to);
        });
    };
    walkUp(node.id);
    walkDown(node.id);
    return [...upstream, node.id, ...downstream];
}
function upstreamLineNodeIds(node){
    if(!node) return [];
    // 只取直接上游（上一组输入），不递归整条链，也不含当前节点自身（用户要求 2026-08-16）
    const conns = lineConnectionsFor(node);
    const direct = [];
    conns.filter(conn => conn.to === node.id).forEach(conn => {
        if(conn.from && conn.from !== node.id && !direct.includes(conn.from)) direct.push(conn.from);
    });
    return direct;
}
function lineImagesFor(node){
    const ids = upstreamLineNodeIds(node);
    return ids.flatMap(id => {
        const source = D("nodes").find(n => n.id === id);
        return deps.imagesForNode(source);
    }).filter(img => img?.url);
}
function collectMentionedImagesFromPrompt(){
    const images = [];
    deps.collectPromptParts().forEach(part => {
        if(part.type === 'image' && part.url) images.push(part);
    });
    return images;
}
function uniqueReferenceImages(images){
    const refs = [];
    const seen = new Set();
    (images || []).forEach((img, index) => {
        if(!img?.url || seen.has(img.url)) return;
        seen.add(img.url);
        refs.push({
            ...img,
            name:img.name || `图${refs.length + 1}`,
            role:img.role || `image_${refs.length + 1}`,
            imageIndex:Number.isFinite(Number(img.imageIndex)) ? Number(img.imageIndex) : index
        });
    });
    return refs;
}
function visibleReferenceImagesFor(node){
    const base = defaultReferenceImagesFor(node);
    return uniqueReferenceImages([...base, ...collectMentionedImagesFromPrompt()]);
}

    global.CanvasSmartLoopData = {
        configure,
        smartLoopInputPromptItems,
        smartLoopSelectedInputPrompt,
        smartLoopPrompt,
        smartLoopInputImages,
        smartLoopPreviewImages,
        outputImagesForNode,
        selfReferenceImagesForNode,
        textForNode,
        promptInputNodesFor,
        inputPromptTextFor,
        upstreamLoopPromptNodesFor,
        inputImagesFor,
        workflowInputImagesFor,
        inputRefKey,
        blockedInputRefKeys,
        isInputRefBlocked,
        activeInputImagesFor,
        toggleInputRefBlocked,
        defaultReferenceImagesFor,
        lineConnectionsFor,
        connectedLineNodeIds,
        upstreamLineNodeIds,
        lineImagesFor,
        collectMentionedImagesFromPrompt,
        uniqueReferenceImages,
        visibleReferenceImagesFor,
    };
})(typeof window !== 'undefined' ? window : this);

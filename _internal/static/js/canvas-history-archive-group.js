//** Groups generated outputs into history container nodes (ensure/position/demote/forget). */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    function D(name){return typeof deps[name] === 'function' ? deps[name]() : deps[name];}

function cleanHistoryImages(images=[]){
 const seen = new Set();
 return (images || [])
 .filter(img => img?.url)
        .map(img => deps.stripImageGenerationMeta({...img}))
        .filter(img => {
            const key = `${img.kind || ''}|${img.url || ''}`;
            if(seen.has(key)) return false;
            seen.add(key);
 return true;
 });
}
function shouldMoveOutputAssetToHistory(url){
 const value = String(url || '').trim();
 if(!value.startsWith('/assets/output/')) return false;
 if(value.includes('/history/')) return false; // 任意层级 history 目录都算已归档（含画布同名子目录），与后端 skip 对齐
 if(value.startsWith('/assets/output/videos/')) return false;
 return deps.generatedOutputKindForName(value, 'image') === 'image';
}
async function moveOutputImagesToHistoryForRun(images=[]){
 const moved = new Map();
 for(const img of images || []){
 const oldUrl = String(img?.url || '').trim();
 if(!shouldMoveOutputAssetToHistory(oldUrl)) continue;
 try {
 const res = await fetch('/api/move-to-history', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url:oldUrl})});
 const data = await res.json().catch(() => ({}));
 const nextUrl = data?.moved || data?.url || '';
 if(res.ok && nextUrl){
 moved.set(oldUrl, nextUrl);
 img.url = nextUrl;
 ['sourceUrl','localUrl','originalLocalUrl','source_url','local_url'].forEach(key => {
 if(img[key] === oldUrl) img[key] = nextUrl;
 });
 }
 } catch(_) {}
 }
 return moved;
}
function remapRefsForMovedAssets(refs=[], moved=new Map()){
 if(!moved?.size) return refs || [];
 return (refs || []).map(ref => {
 const oldUrl = String(ref?.url || '');
 const nextUrl = moved.get(oldUrl);
 if(!nextUrl) return ref;
 const copy = {...ref, url:nextUrl};
 ['sourceUrl','localUrl','originalLocalUrl','source_url','local_url'].forEach(key => {
 if(copy[key] === oldUrl) copy[key] = nextUrl;
 });
 return copy;
 });
}
function updatePromptMentionUrlsForMovedAssets(moved=new Map()){
 if(!D("promptInput") || !moved?.size) return;
 D("promptInput").querySelectorAll('.mention-image-token').forEach(token => {
 const oldUrl = token.dataset.url || '';
 const nextUrl = moved.get(oldUrl);
 if(!nextUrl) return;
 token.dataset.url = nextUrl;
 const media = token.querySelector('img,video');
 if(media) media.setAttribute('src', nextUrl);
 });
}
function hasHistoryConnection(nodeId, groupId){
    return Boolean(nodeId && groupId && (D("canvas")?.connections || []).some(conn => conn.from === nodeId && conn.to === groupId && (conn.kind || 'flow') === 'history'));
}
function demoteHistoryGroupNode(group){
    if(!group) return;
    delete group.historyFor;
    delete group.isHistoryGroup;
    if(group.title === '历史分组'){
        const count = (group.images || []).length;
        group.title = count > 1 ? 'Group' : count === 1 ? 'Image' : tr('smart.createImportNode');
    }
}
function historyGroupForNode(node){
    if(!node?.id) return null;
    let matched = null;
    D("nodes").forEach(n => {
        if(!deps.isHistoryGroupNode(n) || n.historyFor !== node.id) return;
        if(hasHistoryConnection(node.id, n.id)){
            if(!matched) matched = n;
        } else {
            demoteHistoryGroupNode(n);
        }
    });
    return matched;
}
function positionHistoryGroupForNode(node, group){
    if(!node || !group) return;
    const r = deps.nodeRect(node);
    const gr = deps.nodeRect(group);
    if(!Number.isFinite(Number(group.x))) group.x = Math.round((Number(node.x) || 0) + Math.max(0, (r.width - gr.width) / 2));
    if(!Number.isFinite(Number(group.y))) group.y = Math.round((Number(node.y) || 0) + r.height + 56);
}
function ensureHistoryGroupForNode(node){
    if(!node?.id) return null;
    let group = historyGroupForNode(node);
    if(!group){
        const r = deps.nodeRect(node);
        group = {
            id:deps.uid('smart'),
            type:'smart-image',
            x:Math.round(Number(node.x || 0)),
            y:Math.round(Number(node.y || 0) + r.height + 56),
            title:'历史分组',
            images:[],
            historyFor:node.id,
            isHistoryGroup:true,
            scale:D("MEDIA_GROUP_DEFAULT_SCALE"),
            created_at:Date.now()
        };
        D("nodeStore").addNode(group, 'user_manual');
    }
    group.type = 'smart-image';
    group.title = '历史分组';
    group.isHistoryGroup = true;
    group.historyFor = node.id;
    if(!Number.isFinite(Number(group.scale))) group.scale = D("MEDIA_GROUP_DEFAULT_SCALE");
    deps.addConnection(node.id, group.id, 'history');
    positionHistoryGroupForNode(node, group);
    return group;
}

    global.CanvasHistoryArchiveGroup = {
        configure,
        cleanHistoryImages,
        shouldMoveOutputAssetToHistory,
        moveOutputImagesToHistoryForRun,
        remapRefsForMovedAssets,
        updatePromptMentionUrlsForMovedAssets,
        hasHistoryConnection,
        demoteHistoryGroupNode,
        historyGroupForNode,
        positionHistoryGroupForNode,
        ensureHistoryGroupForNode,
    };
})(typeof window !== 'undefined' ? window : this);

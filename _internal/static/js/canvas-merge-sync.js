//** Multi-device canvas merge + asset-library sync (WebSocket/meta poll, merged state application). */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    function D(name){return typeof deps[name] === 'function' ? deps[name]() : deps[name];}

// Keep an immutable server baseline; live nodes are mutated by editors and jobs.
let serverBaseline = null;
function rememberServerCanvas(value){
    serverBaseline = value ? JSON.parse(JSON.stringify(value)) : null;
}
function sameValue(a, b){return JSON.stringify(a) === JSON.stringify(b);}
function mergeChangedMedia(local=[], remote=[], base=[]){
    const keys = items => new Set(items.flatMap(global.CanvasGenerationResultModel.mediaIdentityKeys));
    const baseKeys = keys(base), localKeys = keys(local), remoteKeys = keys(remote);
    const alive = item => global.CanvasGenerationResultModel.mediaIdentityKeys(item).every(key =>
        !baseKeys.has(key) || (localKeys.has(key) && remoteKeys.has(key)));
    return mergeSmartImageLists(remote.filter(alive), local.filter(alive));
}
function mergeChangedNode(local, remote, base){
    if(!base) return mergeSmartNode(local, remote);
    const merged = {...remote};
    // Remote wins a same-field conflict. Unrelated unsaved local edits survive.
    for(const key of new Set([...Object.keys(base), ...Object.keys(local)])){
        if(sameValue(remote[key], base[key]) && !sameValue(local[key], base[key])){
            if(key in local) merged[key] = local[key]; else delete merged[key];
        }
    }
    if(!sameValue(local.images, base.images) && !sameValue(remote.images, base.images)){
        const localRun = Number(local.runAt || local.runStartedAt || 0);
        const remoteRun = Number(remote.runAt || remote.runStartedAt || 0);
        merged.images = localRun && remoteRun && localRun !== remoteRun
            ? (localRun > remoteRun ? local.images : remote.images)
            : mergeChangedMedia(local.images || [], remote.images || [], base.images || []);
    }
    return merged;
}

function mergeSmartImageLists(localImgs, remoteImgs){
    return global.CanvasGenerationResultModel.uniqueMediaItems([...(localImgs || []), ...(remoteImgs || [])]);
}
function mergeSmartLogLists(localLogs, remoteLogs){
    const byId = new Map();
    [...(localLogs || []), ...(remoteLogs || [])].forEach(log => {
        if(!log || typeof log !== 'object') return;
        const key = String(log.taskId || log.id || '').trim();
        if(key) byId.set(key, log);
    });
    return [...byId.values()].sort((a, b) => Number(b.createdAt || 0) - Number(a.createdAt || 0)).slice(0, 500);
}
function smartNodeInFlight(node){
    return Boolean(node && (global.CanvasSpeech?.isActive(node.id) || node.running || node.pending || node.queued || node.jimengPending || deps.smartPendingTasks(node).length));
}
function mergeSmartNode(local, remote){
    // 统一文本兜底：本地 text 非空而对方为空，说明对方还没见过本地这次（可能未落盘的）写入。
    // 典型：LLM 刚把结果写回 node.text、防抖保存还在途，服务端已被 Agent 工具/别的端先写，
    // 合并按 {...remote} 会把刚生成的文本瞬间冲掉。此场景保留本地文本（含草稿字段）。
    const localText = String(local?.text || '');
    const remoteText = String(remote?.text || '');
    const keepLocalText = Boolean(localText.trim() && !remoteText.trim());
    const keepLocalDraft = keepLocalText
        && String(local?.promptDraftText || '').trim() && !String(remote?.promptDraftText || '').trim();
    // A rerun replaces its previous output. A stale client must not restore the
    // old generation through the image union when it saves or receives sync.
    const localRun = Number(local?.runAt || local?.runStartedAt || 0);
    const remoteRun = Number(remote?.runAt || remote?.runStartedAt || 0);
    let merged;
    if(localRun > 0 && remoteRun > 0 && localRun !== remoteRun){
        const newer = localRun > remoteRun ? local : remote;
        merged = {...remote, ...newer, images:mergeSmartImageLists(newer.images, [])};
    // 本地正在生成/排队的节点完全以本地为准，只把对方可能多出来的图并进来，绝不被对方旧状态冲掉
    } else if(smartNodeInFlight(local)){
        if((remote?.images || []).length && !smartNodeInFlight(remote)){
            merged = {...remote, images:mergeSmartImageLists(local.images, remote.images)};
        } else {
            merged = {...local, images:mergeSmartImageLists(local.images, remote.images)};
        }
    } else {
        // 否则以对方（最新保存方）的布局/标题/设置为基底，但图片取并集——双方生成结果都不丢
        merged = {...remote, images:mergeSmartImageLists(local.images, remote.images)};
    }
    if(keepLocalText) merged.text = localText;
    if(keepLocalDraft){
        merged.promptDraftText = local.promptDraftText;
        merged.promptDraftHtml = local.promptDraftHtml;
        merged.promptDraftTouched = local.promptDraftTouched;
    }
    return merged;
}
function mergeSmartNodeLists(localNodes, remoteNodes, tombstoned, baseNodes){
    const dead = (tombstoned instanceof Set) ? tombstoned : new Set(tombstoned || []);
    const localById = new Map((localNodes || []).map(n => [n.id, n]));
    const remoteById = new Map((remoteNodes || []).map(n => [n.id, n]));
    const baseById = new Map((baseNodes || []).map(n => [n.id, n]));
    const order = [];
    const seen = new Set();
    (localNodes || []).forEach(n => { if(!seen.has(n.id)){ seen.add(n.id); order.push(n.id); } });
    (remoteNodes || []).forEach(n => { if(!seen.has(n.id)){ seen.add(n.id); order.push(n.id); } });
    const mergedNodes = order.map(id => {
        if(dead.has(id)) return null;           // Phase 4：有墓碑 = 任一端已显式删除，双向剔除（修 never delete 复活 bug）
        const local = localById.get(id);
        const remote = remoteById.get(id);
        const base = baseById.get(id);
        if(base && (!local || !remote)) return null;
        if(local && !remote) return local;     // 仅本地存在且无墓碑：保留（我新建的节点，不丢结果）
        if(remote && !local) return remote;     // 仅对方存在且无墓碑：加入对方新建的节点
        return mergeChangedNode(local, remote, base);
    }).filter(Boolean);
    // A generated image moved into a real smart-group member must not reappear in
    // the source node when a stale canvas tab unions local and remote image lists.
    const movedBySource = new Map();
    mergedNodes.forEach(node => {
        if(node.__origin !== 'mcp_output' || !node.mcpGroupSourceId) return;
        const moved = movedBySource.get(node.mcpGroupSourceId) || new Set();
        (node.images || []).forEach(image => { if(image?.url) moved.add(image.url); });
        movedBySource.set(node.mcpGroupSourceId, moved);
    });
    mergedNodes.forEach(node => {
        if(!node.mcpGroupId || !movedBySource.has(node.id)) return;
        const moved = movedBySource.get(node.id);
        node.images = (node.images || []).filter(image => !moved.has(image?.url));
    });
    return mergedNodes;
}
function mergeSmartConnections(localConns, remoteConns, nodeIds){
    const out = [];
    const seen = new Set();
    [...(localConns || []), ...(remoteConns || [])].forEach(c => {
        if(!c || !nodeIds.has(c.from) || !nodeIds.has(c.to)) return;
        const key = `${c.from}->${c.to}:${c.kind || 'flow'}`;
        if(seen.has(key)) return;
        seen.add(key);
        out.push(c);
    });
    return out;
}
function pruneLegacyDirectorNodes(nodeList, connectionList){
    const filteredNodes = (Array.isArray(nodeList) ? nodeList : []).filter(node => node?.type !== 'director');
    const validIds = new Set(filteredNodes.map(node => node.id));
    const filteredConnections = (Array.isArray(connectionList) ? connectionList : []).filter(conn => conn && validIds.has(conn.from) && validIds.has(conn.to));
    return { nodes: filteredNodes, connections: filteredConnections };
}
function applyMergedServerCanvas(serverCanvas){
    if(!serverCanvas || !D("canvas")) return false;
    if(serverCanvas.id && serverCanvas.id !== D("canvas").id) return false;
    if(Number(serverCanvas.updated_at || 0) < Number(D("canvas").updated_at || 0)) return false;
    deps.beforeMerge?.();
    const cleanedRemote = pruneLegacyDirectorNodes(
        (Array.isArray(serverCanvas.nodes) ? serverCanvas.nodes : []).map(D("normalizeLegacySmartNode")).filter(Boolean),
        serverCanvas.connections
    );
    const remoteNodes = cleanedRemote.nodes;
    // Phase 4：墓碑并集——本地删的 + 对方删的都不复活；并把对方墓碑并入本地，随下次保存回写。
    const localDead = D("nodeStore").deletedIds(D("canvas"));
    const remoteTombs = Array.isArray(serverCanvas.deleted) ? serverCanvas.deleted : [];
    if(remoteTombs.length){
        if(!Array.isArray(D("canvas").deleted)) D("canvas").deleted = [];
        remoteTombs.forEach(t => { if(t && t.id && !localDead.has(t.id)) D("canvas").deleted.push(t); });
    }
    const baseline = serverBaseline?.id === D("canvas").id ? serverBaseline : null;
    const mergedNodes = mergeSmartNodeLists(D("nodes"), remoteNodes, D("nodeStore").deletedIds(D("canvas")), baseline?.nodes);
    const nodeIds = new Set(mergedNodes.map(n => n.id));
    deps.setNodes(mergedNodes);
    const connectionKey = c => `${c.from}->${c.to}:${c.kind || 'flow'}`;
    const baseConnections = new Set((baseline?.connections || []).map(connectionKey));
    const localConnections = D("canvas").connections || [];
    const localKeys = new Set(localConnections.map(connectionKey));
    const remoteKeys = new Set(cleanedRemote.connections.map(connectionKey));
    const keepConnection = c => !baseConnections.has(connectionKey(c)) || (localKeys.has(connectionKey(c)) && remoteKeys.has(connectionKey(c)));
    D("canvas").connections = mergeSmartConnections(localConnections.filter(keepConnection), cleanedRemote.connections.filter(keepConnection), nodeIds);
    D("canvas").logs = mergeSmartLogLists(D("canvas").logs, serverCanvas.logs);
    D("canvas").updated_at = Number(serverCanvas.updated_at || D("canvas").updated_at || 0);
    rememberServerCanvas({...serverCanvas, nodes:remoteNodes, connections:cleanedRemote.connections});
    if(D("canvas").title !== serverCanvas.title && serverCanvas.title){
        D("canvas").title = serverCanvas.title;
        const titleEl = document.getElementById('smartTitle');
        if(titleEl) titleEl.textContent = D("canvas").title;
        if(typeof deps.updateCanvasTitleDisplay === 'function') deps.updateCanvasTitleDisplay();
    }
    deps.afterMerge?.();
    deps.render();
    deps.refreshSmartLogPanel();
    if(typeof deps.refreshConnectionLayer === 'function') deps.refreshConnectionLayer();
    deps.resumeSmartPendingTasks();
    deps.resumeJimengPendingNodes();
    deps.recoverStuckComfyNodes();
    if(deps.pruneStaleComfyErrorsOnLoad) deps.pruneStaleComfyErrorsOnLoad();
    return true;
}
async function mergeReloadCanvasNow(){
    if(!D("canvasId")) return;
    if(D("dragState") || D("selectionState")){
        // 用户正在拖拽/框选，稍后再合并，别打断操作
        scheduleCanvasMergeReload(600);
        return;
    }
    try {
        const res = await fetch(`/api/canvases/${encodeURIComponent(D("canvasId"))}`);
        if(!res.ok) return;
        const data = await res.json();
        if(data && data.canvas) applyMergedServerCanvas(data.canvas);
    } catch(e) {}
}
function scheduleCanvasMergeReload(delay=200){
    clearTimeout(D("canvasSyncTimer"));
    deps.setCanvasSyncTimer(setTimeout(() => { mergeReloadCanvasNow(); }, delay));
}
function handleCanvasUpdatedMessage(data={}){
    if(!data || data.type !== 'canvas_updated') return;
    if(!D("canvasId") || data.canvas_id !== D("canvasId")) return;
    if(data.client_id && data.client_id === D("smartClientId")) return; // 自己发的，忽略
    if(D("canvasSyncInFlight")) return; // 我正在保存，保存完成/409 合并会处理
    const remoteUpdatedAt = Number(data.updated_at || 0);
    if(remoteUpdatedAt && remoteUpdatedAt <= Number(D("canvas")?.updated_at || 0)) return;
    scheduleCanvasMergeReload(200);
}
function startCanvasMetaPoll(){
    // WS / iframe 转发不可靠时的兜底：定期看服务器 updated_at 是否变新，变新就合并拉取
    if(D("canvasMetaPollTimer")) return;
    deps.setCanvasMetaPollTimer(setInterval(async () => {
        if(!D("canvasId") || !D("canvas")) return;
        if(D("canvasSyncInFlight") || D("dragState") || D("selectionState")) return;
        try {
            const res = await fetch(`/api/canvases/${encodeURIComponent(D("canvasId"))}/meta`);
            if(!res.ok) return;
            const meta = await res.json();
            if(Number(meta.updated_at || 0) > Number(D("canvas").updated_at || 0)) mergeReloadCanvasNow();
        } catch(e) {}
    }, 8000));
}
function connectAssetLibrarySyncSocket(){
    if(window.parent && window.parent !== window) return;
    const host = window.location.host;
    if(!host) return;
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
    const clientId = D("smartClientId");
    let socket;
    let retryTimer = null;
    const connect = () => {
        try {
            socket = new WebSocket(`${protocol}://${host}/ws/stats?client_id=${clientId}`);
        } catch(e) {
            retryTimer = setTimeout(connect, 3000);
            return;
        }
        socket.onmessage = event => {
            try {
                const data = JSON.parse(event.data);
                if(data?.type === 'asset_library_updated') deps.handleAssetLibraryUpdatedMessage(data);
                if(data?.type === 'prompt_library_updated') deps.handlePromptLibraryUpdatedMessage(data);
                if(data?.type === 'canvas_updated') handleCanvasUpdatedMessage(data);
            } catch(e) {}
        };
        socket.onclose = () => {
            retryTimer = setTimeout(connect, 3000);
        };
        socket.onerror = () => {
            try { socket.close(); } catch(e) {}
        };
    };
    window.addEventListener('beforeunload', () => {
        clearTimeout(retryTimer);
        try { socket?.close(); } catch(e) {}
    });
    connect();
}
function setAssetLibraryFromResponse(data, options={}){
    deps.setAssetLibrary(data.library || D("assetLibrary"));
    deps.setAssetLibraryUpdatedAt(Number(D("assetLibrary").updated_at || D("assetLibraryUpdatedAt") || 0));
    const libs = deps.assetLibraries();
    if(!D("activeAssetLibraryId")) deps.setActiveAssetLibraryId(D("assetLibrary").active_library_id || libs[0]?.id || '');
    if(D("activeAssetLibraryId") && !libs.some(lib => lib.id === D("activeAssetLibraryId"))) deps.setActiveAssetLibraryId(libs[0]?.id || '');
    const cats = deps.assetCategories('image');
    if(D("activeAssetCategoryId") && !cats.some(cat => cat.id === D("activeAssetCategoryId"))) deps.setActiveAssetCategoryId('');
    if(!D("activeAssetCategoryId")) deps.setActiveAssetCategoryId(deps.activeAssetCategory()?.id || '');
    if(D("mentionAssetCategoryId") && !cats.some(cat => cat.id === D("mentionAssetCategoryId"))) deps.setMentionAssetCategoryId('');
    if(!D("mentionAssetCategoryId")) deps.setMentionAssetCategoryId(D("activeAssetCategoryId"));
    if(options.render !== false) {
        deps.renderAssetLibrary();
        if(D("mentionPicker")?.classList?.contains('open') && D("mentionSource") === 'asset') deps.renderMentionPicker('asset');
    }
}

    global.CanvasMergeSync = {
        configure,
        rememberServerCanvas,
        mergeChangedNode,
        mergeSmartImageLists,
        mergeSmartLogLists,
        smartNodeInFlight,
        mergeSmartNode,
        mergeSmartNodeLists,
        mergeSmartConnections,
        pruneLegacyDirectorNodes,
        applyMergedServerCanvas,
        mergeReloadCanvasNow,
        scheduleCanvasMergeReload,
        handleCanvasUpdatedMessage,
        startCanvasMetaPoll,
        connectAssetLibrarySyncSocket,
        setAssetLibraryFromResponse,
    };
})(typeof window !== 'undefined' ? window : this);

//** Supervises Comfy/即梦 canvas generation tasks: submit, poll, pending state and recovery. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    function D(name){return typeof deps[name] === 'function' ? deps[name]() : deps[name];}

async function runComfyWorkflowJob(node, runSettings, prompt, refs, progressNode=null, meta=null){
    const payload = await deps.buildComfyWorkflowJobPayload(node, runSettings, prompt, refs);
    const result = await deps.submitComfyWorkflowJob(progressNode, payload, meta);
    if(result.comfyAlreadyFinalized) return {urls:[], kind:'image', raw:result, alreadyFinalized:true};
    const urls = deps.resultMediaUrls(result);
    const fallbackKind = result.videos?.length ? 'video' : result.audios?.length ? 'audio' : result.texts?.length ? 'text' : 'image';
    if(progressNode) deps.clearComfyProgress(progressNode);
    return {urls, kind:deps.mediaKindForUrls(urls, fallbackKind), raw:result};
}
async function runComfyGeneration(node, prompt, refs, pendingNode, meta){
 const runSettings = deps.normalizeComfyWorkflowSelection(D("settings"));
 const allRefs = refs || [];
 refs = deps.comfyWorkflowImageRefsForNode(node, allRefs);
 const mode = runSettings.comfyMode || 'custom';
 if(mode === 'text') return runComfyText(node, prompt, pendingNode, meta);
 if(mode === 'enhance') return runComfyEnhance(node, refs, pendingNode, meta);
    if(mode === 'edit') return runComfyEdit(node, prompt, refs, pendingNode, meta);
    const result = await runComfyWorkflowJob(node, runSettings, prompt, allRefs, pendingNode || node, meta);
    if(result.alreadyFinalized) return;
    if(!result.urls.length) throw new Error(tr('smart.errComfyNoImages'));
    const kind = result.kind;
    const ext = kind === 'video' ? 'mp4' : kind === 'audio' ? 'mp3' : 'png';
    const out = result.urls.map((url, i) => ({url, name:`comfy-${i + 1}.${ext}`, kind})).filter(x => x.url);
    if(!out.length) throw new Error(tr('smart.errComfyEmpty'));
    const outputUrls = out.map(o => o.url);
    if(pendingNode){
        await deps.finalizePendingNode(pendingNode, outputUrls, meta, kind);
        deps.clearComfyProgress(pendingNode);
        // ComfyUI has returned and the output is now on the canvas. Release
        // this Comfy-only run lock immediately; outer cleanup remains a
        // second safety net for persistence and logging.
        deps.clearNodeRunningState(pendingNode);
        deps.syncRunButtonAvailability();
        deps.render();
    } else {
        const created = deps.createNode((node.x || 0) + deps.nodeRect(node).width + 40, node.y || 0, out);
        deps.attachRunMeta(created, meta);
        deps.addConnection(node.id, created.id);
    }
    deps.clearPromptInput({preserveDraft:true});
    deps.scheduleSave();
}
async function runComfyText(node, prompt, pendingNode, meta){
    const data = await fetch(deps.comfyProxyUrl('/api/generate'), {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({prompt, width:Number(D("settings").width || 1024), height:Number(D("settings").height || 1024), workflow_json:'Z-Image.json', type:'zimage'})
    }).then(async r => { if(!r.ok) throw new Error(await r.text()); return r.json(); });
    const out = data.outputs || data.images || [];
    if(!out.length) throw new Error(tr('smart.errComfyNoImages'));
    if(pendingNode){
        await deps.finalizePendingNode(pendingNode, out, meta);
    } else {
        const created = deps.createNode((node.x || 0) + deps.nodeRect(node).width + 40, node.y || 0, out.map((url, i) => ({url, name:`comfy-${i + 1}.png`})));
        deps.attachRunMeta(created, meta);
        deps.addConnection(node.id, created.id);
    }
    deps.clearPromptInput({preserveDraft:true});
    deps.scheduleSave();
}
async function runComfyEnhance(node, refs, pendingNode, meta){
    if(!refs.length) throw new Error(tr('smart.errEnhanceNeedRefs'));
    const inputName = await comfyNameForRef(refs[0]);
    const data = await fetch(deps.comfyProxyUrl('/api/generate'), {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({workflow_json:'Z-Image-Enhance.json', type:'enhance', params:{"15":{image:inputName},"204":{value:Number(D("settings").enhanceStrength ?? 0.5)}}})
    }).then(async r => { if(!r.ok) throw new Error(await r.text()); return r.json(); });
    const out = data.outputs || data.images || [];
    if(!out.length) throw new Error(tr('smart.errComfyNoImages'));
    if(pendingNode){
        await deps.finalizePendingNode(pendingNode, out, meta);
    } else {
        const created = deps.createNode((node.x || 0) + deps.nodeRect(node).width + 40, node.y || 0, out.map((url, i) => ({url, name:`enhance-${i + 1}.png`})));
        deps.attachRunMeta(created, meta);
        deps.addConnection(node.id, created.id);
    }
    deps.scheduleSave();
}
async function runComfyEdit(node, prompt, refs, pendingNode, meta){
    if(!refs.length) throw new Error(tr('smart.errEditNeedRefs'));
    const names = [];
    for(const ref of refs.slice(0, 3)) names.push(await comfyNameForRef(ref));
    const data = await fetch(deps.comfyProxyUrl('/api/generate'), {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({prompt, workflow_json:'Flux2-Klein.json', type:'klein', params:{"168":{text:prompt},"158":{noise_seed:Math.floor(Math.random()*1000000)},"278":{image:names[0] || ""},"270":{image:names[1] || ""},"292":{image:names[2] || ""},"313":{value:Boolean(names[1])},"314":{value:Boolean(names[2])}}})
    }).then(async r => { if(!r.ok) throw new Error(await r.text()); return r.json(); });
    const out = data.outputs || data.images || [];
    if(!out.length) throw new Error(tr('smart.errComfyNoImages'));
    if(pendingNode){
        await deps.finalizePendingNode(pendingNode, out, meta);
    } else {
        const created = deps.createNode((node.x || 0) + deps.nodeRect(node).width + 40, node.y || 0, out.map((url, i) => ({url, name:`edit-${i + 1}.png`})));
        deps.attachRunMeta(created, meta);
        deps.addConnection(node.id, created.id);
    }
    deps.clearPromptInput({preserveDraft:true});
    deps.scheduleSave();
}
async function comfyNameForRef(ref){
    if(ref.comfy_name) return ref.comfy_name;
    const response = await fetch(ref.url);
    if(!response.ok) return ref.name || ref.url;
    const blob = await response.blob();
    const form = new FormData();
    form.append('files', blob, ref.name || 'smart-ref.png');
    const data = await fetch('/api/upload', {method:'POST', body:form}).then(async r => {
        if(!r.ok) throw new Error(await r.text());
        return r.json();
    });
    const name = data.files?.[0]?.comfy_name || ref.name || ref.url;
    const sourceNode = ref.nodeId ? D("nodes").find(n => n.id === ref.nodeId) : null;
    const sourceIndex = Number(ref.imageIndex);
    const sourceImage = sourceNode && Number.isFinite(sourceIndex)
        ? sourceNode.images?.[sourceIndex]
        : null;
    const image = sourceImage || sourceNode?.images?.find(img => img.url === ref.url) || D("nodes").flatMap(n => n.images || []).find(img => img.url === ref.url);
    if(image) image.comfy_name = name;
    ref.comfy_name = name;
    return name;
}
function smartPendingTasks(node){
    if(!node || !Array.isArray(node.pendingTasks)) return [];
    return node.pendingTasks.filter(task => task && task.taskId);
}
function rememberSmartTaskIds(node, taskIds=[]){
    if(!node) return;
    const seen = new Set();
    const ids = [...(Array.isArray(node.lastTaskIds) ? node.lastTaskIds : []), ...(taskIds || [])]
        .map(id => String(id || '').trim())
        .filter(id => id && !seen.has(id) && seen.add(id))
        .slice(-12);
    if(ids.length) node.lastTaskIds = ids;
}
function fallbackGeneratedOutputItems(items, kind='image'){
    const ext = kind === 'video' ? 'mp4' : kind === 'audio' ? 'mp3' : kind === 'text' ? 'txt' : 'png';
    const date = new Date();
    return (items || []).map((item, index) => {
        const source = item && typeof item === 'object' ? item : {url:item};
        const url = source.url || source.path || source.src || source.uri || '';
        if(!url) return null;
        const name = source.name || source.display_name || deps.fileNameFromUrl(url) || deps.generatedDateSequenceName(index, ext, date);
        const isRemote = /^https?:\/\//i.test(String(url));
        return deps.stripImageGenerationMeta({
            ...source,
            url,
            name,
            display_name:source.display_name || name,
            kind:source.kind || source.mediaKind || kind,
            source_url:source.source_url || source.sourceUrl || url,
            generatedResult:true,
            remoteFallback:isRemote,
            remote_fallback:isRemote,
            localizePending:isRemote
        });
    }).filter(item => item?.url);
}
class JimengPendingSignal extends Error {
    constructor(info){
        const data = info || {};
        super(data.message || '即梦任务排队中，可继续等待或手动查询');
        this.jimengPending = true;
        this.submitId = data.submitId || data.submit_id || '';
        this.kind = data.kind || 'image';
        this.queueInfo = data.queueInfo || data.queue_info || {};
    }
}
const activeJimengPolls = new Set();
const JIMENG_POLL_INTERVAL = 60000;
const JIMENG_POLL_MAX = 1440;
function jimengQueueText(queueInfo){
    const qi = queueInfo || {};
    const idx = qi.queue_idx;
    const len = qi.queue_length;
    if(idx != null && len != null) return `即梦云端排队中（第 ${idx}/${len} 位）`;
    return '即梦云端生成中';
}
function setNodeJimengPending(node, signal){
    if(!node || !signal || !signal.submitId) return;
    const prev = node.jimengPending && node.jimengPending.submitId === signal.submitId ? node.jimengPending : null;
    node.jimengPending = {
        submitId:signal.submitId,
        kind:signal.kind || (prev && prev.kind) || 'image',
        queueInfo:signal.queueInfo || (prev && prev.queueInfo) || {},
        message:signal.message || (prev && prev.message) || '',
        startedAt:(prev && prev.startedAt) || deps.nowMs(),
        updatedAt:deps.nowMs(),
        querying:prev ? prev.querying : false
    };
    node.running = false;
    node.pending = 0;
    delete node.pendingTasks;
    if(!node.runStartedAt) node.runStartedAt = node.jimengPending.startedAt;
    delete node.runFinishedAt;
    delete node.runElapsedMs;
    node.runTimerHidden = false;
    deps.render();
    deps.scheduleSave();
    startJimengPoll(node);
}
function handleJimengPendingSignal(node, e){
    if(!(e && e.jimengPending && e.submitId)) return false;
    setNodeJimengPending(node, e);
    deps.toast((e.message || jimengQueueText(e.queueInfo)).slice(0, 160));
    return true;
}
async function finalizeJimengPending(node, urls, kind='image'){
    if(!node) return false;
    const ext = kind === 'video' ? 'mp4' : kind === 'audio' ? 'mp3' : kind === 'text' ? 'txt' : 'png';
    const date = new Date();
    const additions = kind === 'image'
        ? await deps.smartGeneratedOutputItems(urls, kind, {displayName:node.title || '', nodeId:node.id})
        : (urls || []).map((item, i) => {
            const url = typeof item === 'string' ? item : item?.url || '';
            const itemKind = (typeof item === 'object' && item.kind) || kind;
            return deps.stripImageGenerationMeta({url, name:deps.generatedDateSequenceName(i, ext, date), kind:itemKind, generatedResult:true});
        }).filter(item => item.url);
    if(!additions.length) return false;
    delete node.jimengPending;
    deps.replaceOutputsToNodeWithHistory(node, additions, kind, null, {skipShift:true});
    node.running = false;
    node.pending = 0;
    node.runFinishedAt = deps.nowMs();
    if(!node.runStartedAt) node.runStartedAt = node.runFinishedAt;
    node.runElapsedMs = Math.max(0, node.runFinishedAt - Number(node.runStartedAt || node.runFinishedAt));
    node.runTimerHidden = false;
    deps.render();
    deps.scheduleSave();
    return true;
}
async function applyJimengQueryResult(node, data){
    if(!node || !data) return false;
    if(data.status === 'succeeded'){
        const kind = data.kind || node.jimengPending?.kind || 'image';
        return await finalizeJimengPending(node, data.urls || [], kind);
    }
    if(data.status === 'failed'){
        delete node.jimengPending;
        node.running = false;
        node.pending = 0;
        deps.toast((data.error || '即梦任务失败').slice(0, 160));
        deps.render();
        deps.scheduleSave();
        return true;
    }
    if(node.jimengPending){
        node.jimengPending.queueInfo = data.queue_info || node.jimengPending.queueInfo || {};
        node.jimengPending.message = data.message || node.jimengPending.message || '';
        node.jimengPending.updatedAt = deps.nowMs();
    }
    deps.render();
    deps.scheduleSave();
    return false;
}
async function fetchJimengQuery(submitId, kind){
    return fetch('/api/jimeng/query-media', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({submit_id:submitId, kind:kind || 'image'})
    }).then(async r => { if(!r.ok) throw new Error(await r.text()); return r.json(); });
}
async function queryJimengNow(nodeId){
    const node = D("nodes").find(n => n.id === nodeId);
    if(!node || !node.jimengPending || !node.jimengPending.submitId) return;
    if(node.jimengPending.querying) return;
    const submitId = node.jimengPending.submitId;
    const kind = node.jimengPending.kind || 'image';
    node.jimengPending.querying = true;
    deps.render();
    try {
        const data = await fetchJimengQuery(submitId, kind);
        await applyJimengQueryResult(node, data);
    } catch(e){
        deps.toast((e.message || '查询失败').slice(0, 160));
    } finally {
        if(node.jimengPending) node.jimengPending.querying = false;
        deps.render();
    }
}
function startJimengPoll(node){
    if(!node || !node.jimengPending || !node.jimengPending.submitId) return;
    const submitId = node.jimengPending.submitId;
    if(activeJimengPolls.has(submitId)) return;
    activeJimengPolls.add(submitId);
    const nodeId = node.id;
    (async () => {
        try {
            for(let i = 0; i < JIMENG_POLL_MAX; i++){
                await new Promise(resolve => setTimeout(resolve, JIMENG_POLL_INTERVAL));
                const cur = D("nodes").find(n => n.id === nodeId);
                if(!cur || !cur.jimengPending || cur.jimengPending.submitId !== submitId) return;
                if(cur.jimengPending.querying) continue;
                let data;
                try {
                    data = await fetchJimengQuery(submitId, cur.jimengPending.kind || 'image');
                } catch(err){ continue; }
                const done = await applyJimengQueryResult(cur, data);
                if(done) return;
                const after = D("nodes").find(n => n.id === nodeId);
                if(!after || !after.jimengPending || after.jimengPending.submitId !== submitId) return;
            }
        } finally {
            activeJimengPolls.delete(submitId);
        }
    })();
}
function resumeJimengPendingNodes(){
    D("nodes").filter(n => n && n.jimengPending && n.jimengPending.submitId).forEach(n => {
        n.jimengPending.querying = false;
        startJimengPoll(n);
    });
}
async function pollSmartCanvasTask(taskId){
    return CanvasGenerationTaskPoller.poll(taskId);
}
async function finalizeSmartPendingTask(node, taskId, images, kind='image'){
    if(!node || !taskId) return;
    rememberSmartTaskIds(node, [taskId]);
    node.pendingTasks = smartPendingTasks(node).filter(task => task.taskId !== taskId);
    node.pending = Math.max(0, Number(node.pending || 0) - 1);
    const ext = kind === 'video' ? 'mp4' : kind === 'audio' ? 'mp3' : kind === 'text' ? 'txt' : 'png';
    const date = new Date();
    const rawItems = Array.isArray(images) ? images : [];
    let additions = kind === 'image'
        ? await deps.smartGeneratedOutputItems(rawItems, kind, {displayName:node.title || '', nodeId:node.id})
        : rawItems.map((item, i) => {
            const url = typeof item === 'string' ? item : item?.url || '';
            const itemKind = (typeof item === 'object' && item.kind) || kind;
            return deps.stripImageGenerationMeta({url, name:deps.generatedDateSequenceName(i, ext, date), kind:itemKind, generatedResult:true});
        }).filter(item => item.url);
    if(!additions.length && rawItems.length){
        additions = fallbackGeneratedOutputItems(rawItems, kind);
    }
    const existing = (node.images || []).map(img => deps.stripImageGenerationMeta(img));
    const seenUrls = new Set(existing.map(img => String(img?.url || '').trim()).filter(Boolean));
    const seenTaskIds = new Set(existing.map(img => String(img?.generationTaskId || '').trim()).filter(Boolean));
    additions = seenTaskIds.has(String(taskId)) ? [] : additions.filter(img => {
        const url = String(img?.url || '').trim();
        if(!url || seenUrls.has(url)) return false;
        seenUrls.add(url);
        return true;
    }).map(img => ({...img, generationTaskId:taskId}));
    node.images = [...existing, ...additions];
    if(node.__origin === 'agent_tool_generation'){
        deps.addSmartGenerationLog({
            taskId,
            run:{nodeType:node.type, kind, settings:node.runSettings || {}, prompt:node.runPrompt || node.promptDraftText || '', refs:node.runPromptRefs || []},
            outputs:(rawItems || []).map(item => typeof item === 'string' ? item : item?.url).filter(Boolean),
            runMs:node.runStartedAt ? deps.nowMs() - Number(node.runStartedAt) : 0
        });
    }
    if(additions.length) node.outputKind = kind;
    if(!node.pending && smartPendingTasks(node).length === 0){
        delete node.pendingTasks;
        node.runFinishedAt = deps.nowMs();
        if(!node.runStartedAt) node.runStartedAt = node.runFinishedAt;
        node.runElapsedMs = Math.max(0, node.runFinishedAt - Number(node.runStartedAt || node.runFinishedAt));
        node.runTimerHidden = false;
        node.running = false;
        if((node.images || []).length){
            node.title = node.images.length > 1 ? (kind === 'video' ? 'Videos' : kind === 'audio' ? 'Audios' : kind === 'text' ? 'Texts' : 'Group') : (kind === 'video' ? 'Video' : kind === 'audio' ? 'Audio' : kind === 'text' ? 'Text' : 'Image');
            node.scale = deps.mediaNodeDefaultScale(node);
            delete node.w;
            delete node.h;
            delete node.runError;
        } else {
            node.runError = '任务完成但没有写入图片，已保留任务 ID，可重新恢复。';
        }
    }
}
async function recoverCompletedEmptySmartNode(node){
    if(!node || (node.images || []).length || smartPendingTasks(node).length) return false;
    const ids = Array.isArray(node.lastTaskIds) ? node.lastTaskIds.filter(Boolean).slice(-6).reverse() : [];
    if(!ids.length || node._recoveringCompletedTask) return false;
    node._recoveringCompletedTask = true;
    try {
        for(const taskId of ids){
            const result = await pollSmartCanvasTask(taskId).catch(() => null);
            const media = result?.images || result?.videos || deps.resultMediaUrls(result);
            if(Array.isArray(media) && media.length){
                await finalizeSmartPendingTask(node, taskId, media, result?.videos ? 'video' : 'image');
                return (node.images || []).length > 0;
            }
        }
        return false;
    } finally {
        delete node._recoveringCompletedTask;
    }
}
async function resumeSmartPendingNode(node){
    const tasks = smartPendingTasks(node);
    if(!node || !tasks.length) return;
    node.pending = Math.max(tasks.length, Number(node.pending || 0) || tasks.length);
    node.running = false;
    node.apiRunning = true;   // 2026-09-17：被恢复的 API 任务也显示「生成中」动效
    deps.syncRunButtonAvailability(node);
    deps.render();
    const failures = [];
    await Promise.all(tasks.map(async task => {
        try {
            const result = await pollSmartCanvasTask(task.taskId);
            await finalizeSmartPendingTask(node, task.taskId, result?.images || result?.videos || deps.resultMediaUrls(result), task.kind || 'image');
            deps.render();
            deps.scheduleSave();
        } catch(e) {
            if(e && e.jimengPending && e.submitId){
                node.pendingTasks = smartPendingTasks(node).filter(item => item.taskId !== task.taskId);
                setNodeJimengPending(node, e);
                deps.render();
                deps.scheduleSave();
                return;
            }
            node.pendingTasks = smartPendingTasks(node).filter(item => item.taskId !== task.taskId);
            node.pending = Math.max(0, Number(node.pending || 0) - 1);
            if(!node.pending && smartPendingTasks(node).length === 0){
                delete node.pendingTasks;
                node.running = false;
                if(!(node.images || []).length){
                    rememberSmartTaskIds(node, [task.taskId]);
                    node.runError = e.message || tr('smart.errRunFailed');
                }
            }
            failures.push(e);
            if(node.__origin === 'agent_tool_generation'){
                deps.addSmartGenerationLog({
                    taskId:task.taskId,
                    run:{nodeType:node.type, kind:task.kind || 'image', settings:node.runSettings || {}, prompt:node.runPrompt || node.promptDraftText || '', refs:node.runPromptRefs || []},
                    runMs:node.runStartedAt ? deps.nowMs() - Number(node.runStartedAt) : 0,
                    error:e.message || String(e)
                });
            }
            deps.toast((e.message || tr('smart.errRunFailed')).slice(0, 160));
            deps.render();
            deps.scheduleSave();
        }
    }));
    // 2026-09-17：无论成功/失败都清掉 API 运行动效标记
    node.apiRunning = false;
    deps.syncRunButtonAvailability(node);
    if(failures.length && !(node.images || []).length){
        throw failures[0];
    }
}
function isRecoverableComfyNode(node){
    return CanvasComfyJobEngine.isRecoverableComfyNode(node);
}
async function recoverStuckComfyNodes(){
    return CanvasComfyJobEngine.recoverStuckComfyNodes();
}
function resumeSmartPendingTasks(){
    D("nodes").filter(node => smartPendingTasks(node).length).forEach(node => {
        resumeSmartPendingNode(node);
    });
}
async function recoverCompletedEmptySmartNodes(){
    const emptyNodes = D("nodes").filter(node => deps.isSmartImageNode(node) && !(node.images || []).length && !smartPendingTasks(node).length && Array.isArray(node.lastTaskIds) && node.lastTaskIds.length);
    if(!emptyNodes.length) return;
    let changed = false;
    for(const node of emptyNodes){
        if(await recoverCompletedEmptySmartNode(node)) changed = true;
    }
    if(changed){
        deps.render();
        deps.scheduleSave();
    }
}

    global.CanvasSmartTaskSupervisor = {
        configure,
        runComfyWorkflowJob,
        runComfyGeneration,
        runComfyText,
        runComfyEnhance,
        runComfyEdit,
        comfyNameForRef,
        smartPendingTasks,
        rememberSmartTaskIds,
        fallbackGeneratedOutputItems,
        jimengQueueText,
        setNodeJimengPending,
        handleJimengPendingSignal,
        finalizeJimengPending,
        applyJimengQueryResult,
        fetchJimengQuery,
        queryJimengNow,
        startJimengPoll,
        resumeJimengPendingNodes,
        pollSmartCanvasTask,
        finalizeSmartPendingTask,
        recoverCompletedEmptySmartNode,
        resumeSmartPendingNode,
        isRecoverableComfyNode,
        recoverStuckComfyNodes,
        resumeSmartPendingTasks,
        recoverCompletedEmptySmartNodes,
    };
})(typeof window !== 'undefined' ? window : this);

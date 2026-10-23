//** Supervises Comfy/即梦 canvas generation tasks: submit, poll, pending state and recovery. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    function D(name){return typeof deps[name] === 'function' ? deps[name]() : deps[name];}

function isCurrentComfyResult(node,meta){ return !meta?.generationAttemptId || global.CanvasGenerationLifecycle.isCurrent(node,meta.generationAttemptId); }
async function runComfyWorkflowJob(node, runSettings, prompt, refs, progressNode=null, meta=null){
    const payload = await deps.buildComfyWorkflowJobPayload(node, runSettings, prompt, refs);
    if(!isCurrentComfyResult(progressNode || node,meta)) return {urls:[],alreadyFinalized:true};
    const result = await deps.submitComfyWorkflowJob(progressNode, payload, meta);
    if(!isCurrentComfyResult(progressNode || node,meta)) return {urls:[],alreadyFinalized:true};
    if(result.comfyAlreadyFinalized) return {urls:[], kind:'image', raw:result, alreadyFinalized:true};
    // 视频优先（2026-09-30 打组 bug 兜底）：job 结果同时含 videos+images（预览图）时，
    // resultMediaUrls 会把两者合并成一个列表并被统一盖上 kind=video，PNG 变"假视频"黑卡。
    // 与 supervisor 兜底路径 / 后端 _collect_outputs 口径一致：有视频只取视频。
    const urls = (Array.isArray(result.videos) && result.videos.length) ? result.videos.slice() : deps.resultMediaUrls(result);
    const fallbackKind = result.videos?.length ? 'video' : result.audios?.length ? 'audio' : result.texts?.length ? 'text' : 'image';
    if(progressNode) deps.clearComfyProgress(progressNode);
    return {urls, kind:deps.mediaKindForUrls(urls, fallbackKind), raw:result};
}
async function runComfyGeneration(node, prompt, refs, pendingNode, meta, capturedSettings=null){
 const runSettings = deps.normalizeComfyWorkflowSelection(capturedSettings || D("settings"));
 const allRefs = refs || [];
 refs = deps.comfyWorkflowImageRefsForNode(node, allRefs);
 const mode = runSettings.comfyMode || 'custom';
 if(mode === 'text') return runComfyText(node, prompt, pendingNode, meta, runSettings);
 if(mode === 'enhance') return runComfyEnhance(node, refs, pendingNode, meta, runSettings);
    if(mode === 'edit') return runComfyEdit(node, prompt, refs, pendingNode, meta, runSettings);
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
        if(!isCurrentComfyResult(pendingNode,meta)) return;
        deps.clearComfyProgress(pendingNode);
        // ComfyUI has returned and the output is now on the canvas. Release
        // this Comfy-only run lock immediately; outer cleanup remains a
        // second safety net for persistence and logging.
        deps.clearNodeRunningState(pendingNode);
        deps.syncRunButtonAvailability();
        deps.render();
    } else {
        const created = deps.createNode((node.x || 0) + deps.nodeRect(node).width + 40, node.y || 0, out.slice(0, 1));
        deps.spawnImageNodesForExtras(created, out.slice(1), {});
        deps.attachRunMeta(created, meta);
        deps.addConnection(node.id, created.id);
    }
    if(deps.isComposerOwner(node)) deps.clearPromptInput({preserveDraft:true});
    deps.scheduleSave();
}
async function runComfyText(node, prompt, pendingNode, meta, runSettings=D("settings")){
    const data = await fetch(deps.comfyProxyUrl('/api/generate'), {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({prompt, width:Number(runSettings.width || 1024), height:Number(runSettings.height || 1024), workflow_json:'Z-Image.json', type:'zimage'})
    }).then(async r => { if(!r.ok) throw new Error(await r.text()); return r.json(); });
    if(!isCurrentComfyResult(pendingNode || node,meta)) return;
    const out = data.outputs || data.images || [];
    if(!out.length) throw new Error(tr('smart.errComfyNoImages'));
    if(pendingNode){
        await deps.finalizePendingNode(pendingNode, out, meta);
        if(!isCurrentComfyResult(pendingNode,meta)) return;
    } else {
        const comfyItems = out.map((url, i) => ({url, name:`comfy-${i + 1}.png`}));
        const created = deps.createNode((node.x || 0) + deps.nodeRect(node).width + 40, node.y || 0, comfyItems.slice(0, 1));
        deps.spawnImageNodesForExtras(created, comfyItems.slice(1), {});
        deps.attachRunMeta(created, meta);
        deps.addConnection(node.id, created.id);
    }
    if(deps.isComposerOwner(node)) deps.clearPromptInput({preserveDraft:true});
    deps.scheduleSave();
}
async function runComfyEnhance(node, refs, pendingNode, meta, runSettings=D("settings")){
    if(!refs.length) throw new Error(tr('smart.errEnhanceNeedRefs'));
    const inputName = await comfyNameForRef(refs[0]);
    if(!isCurrentComfyResult(pendingNode || node,meta)) return;
    const data = await fetch(deps.comfyProxyUrl('/api/generate'), {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({workflow_json:'Z-Image-Enhance.json', type:'enhance', params:{"15":{image:inputName},"204":{value:Number(runSettings.enhanceStrength ?? 0.5)}}})
    }).then(async r => { if(!r.ok) throw new Error(await r.text()); return r.json(); });
    if(!isCurrentComfyResult(pendingNode || node,meta)) return;
    const out = data.outputs || data.images || [];
    if(!out.length) throw new Error(tr('smart.errComfyNoImages'));
    if(pendingNode){
        await deps.finalizePendingNode(pendingNode, out, meta);
        if(!isCurrentComfyResult(pendingNode,meta)) return;
    } else {
        const enhanceItems = out.map((url, i) => ({url, name:`enhance-${i + 1}.png`}));
        const created = deps.createNode((node.x || 0) + deps.nodeRect(node).width + 40, node.y || 0, enhanceItems.slice(0, 1));
        deps.spawnImageNodesForExtras(created, enhanceItems.slice(1), {});
        deps.attachRunMeta(created, meta);
        deps.addConnection(node.id, created.id);
    }
    deps.scheduleSave();
}
async function runComfyEdit(node, prompt, refs, pendingNode, meta, runSettings=D("settings")){
    if(!refs.length) throw new Error(tr('smart.errEditNeedRefs'));
    const names = [];
    for(const ref of refs.slice(0, 3)) names.push(await comfyNameForRef(ref));
    if(!isCurrentComfyResult(pendingNode || node,meta)) return;
    const data = await fetch(deps.comfyProxyUrl('/api/generate'), {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({prompt, workflow_json:'Flux2-Klein.json', type:'klein', params:{"168":{text:prompt},"158":{noise_seed:Math.floor(Math.random()*1000000)},"278":{image:names[0] || ""},"270":{image:names[1] || ""},"292":{image:names[2] || ""},"313":{value:Boolean(names[1])},"314":{value:Boolean(names[2])}}})
    }).then(async r => { if(!r.ok) throw new Error(await r.text()); return r.json(); });
    if(!isCurrentComfyResult(pendingNode || node,meta)) return;
    const out = data.outputs || data.images || [];
    if(!out.length) throw new Error(tr('smart.errComfyNoImages'));
    if(pendingNode){
        await deps.finalizePendingNode(pendingNode, out, meta);
        if(!isCurrentComfyResult(pendingNode,meta)) return;
    } else {
        const editItems = out.map((url, i) => ({url, name:`edit-${i + 1}.png`}));
        const created = deps.createNode((node.x || 0) + deps.nodeRect(node).width + 40, node.y || 0, editItems.slice(0, 1));
        deps.spawnImageNodesForExtras(created, editItems.slice(1), {});
        deps.attachRunMeta(created, meta);
        deps.addConnection(node.id, created.id);
    }
    if(deps.isComposerOwner(node)) deps.clearPromptInput({preserveDraft:true});
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
// blender 预演「完全依赖插件」：后端渲染完在等插件动画推送，节点保持等待态——
// 无图、blender 引擎、pendingTasks 未清。轮询窗口超时≠失败（resumeSmartPendingNode 会重武装）。
function isPrevizPushWaiting(node){
    return !!node && !(node.images || []).length
        && String(node.runSettings?.engine || '') === 'blender'
        && smartPendingTasks(node).length > 0;
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
    await deps.replaceOutputsToNodeWithHistory(node, additions, kind, null, {skipShift:true});
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
async function finalizeSmartPendingTask(node, taskId, images, kind='image', expectedAttempt=node?.generationAttemptId){
    if(!node || !taskId) return;
    const isCurrent = () => !expectedAttempt || global.CanvasGenerationLifecycle.isCurrent(node,expectedAttempt);
    if(!isCurrent()) return false;
    deps.preserveNodeCardForRun(node);
    rememberSmartTaskIds(node, [taskId]);
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
    if(!isCurrent()) return false;
    node.pendingTasks = smartPendingTasks(node).filter(task => task.taskId !== taskId);
    node.pending = smartPendingTasks(node).length;
    const existing = (node.images || []).map(img => deps.stripImageGenerationMeta(img));
    const seenUrls = new Set(existing.flatMap(img => global.CanvasGenerationResultModel.mediaIdentityKeys(img)));
    const seenTaskIds = new Set(existing.map(img => String(img?.generationTaskId || '').trim()).filter(Boolean));
    additions = seenTaskIds.has(String(taskId)) ? [] : additions.filter(img => {
        const keys = global.CanvasGenerationResultModel.mediaIdentityKeys(img);
        if(!keys.length || keys.some(key => seenUrls.has(key))) return false;
        keys.forEach(key => seenUrls.add(key));
        return true;
    }).map(img => ({...img, generationTaskId:taskId}));
    if(kind === 'image'){
        // 2026-10-19（老王：一个节点只装一张图，旧的进历史）
        if(additions.length > 1){
            const extras = additions.slice(0, -1);
            additions = [additions[additions.length - 1]];
            if(deps.spawnImageNodesForExtras) deps.spawnImageNodesForExtras(node, extras, {});
        }
        // 2026-10-23 老王：重复/并发回执（同一 taskId、或同一张图已在节点上）时 additions 为空，
        // 此时**绝不能**动节点上的图和历史 —— 否则 1 张会被清成 0 张
        // （回归实测：并发两次 finalizeSmartPendingTask 后 images 变 0）。
        if(additions.length){
            if(existing.length && deps.moveOutputImagesToHistoryForRun){
                try { Promise.resolve(deps.moveOutputImagesToHistoryForRun(existing, {})).catch(() => {}); } catch(_){}
            }
            node.images = additions;
        }
    } else {
        node.images = [...existing, ...additions];
    }
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
            // 自动命名（2026-10-09）：提示词前缀 + 产物序号；用户手动改过名（titleManual）不覆盖
            const fallbackTitle = node.images.length > 1 ? (kind === 'video' ? 'Videos' : kind === 'audio' ? 'Audios' : kind === 'text' ? 'Texts' : 'Group') : (kind === 'video' ? 'Video' : kind === 'audio' ? 'Audio' : kind === 'text' ? 'Text' : 'Image');
            node.title = deps.autoNodeTitle ? deps.autoNodeTitle(node, fallbackTitle) : fallbackTitle;
            delete node.runError;
        } else {
            node.runError = '任务完成但没有写入图片，已保留任务 ID，可重新恢复。';
            // 2026-10-10：失败不改尺寸 —— 拨回按比例的默认盒，别让节点停在生成中的占位框上
            if(deps.restoreNodeBoxAfterFailure) deps.restoreNodeBoxAfterFailure(node);
        }
    }
}
async function recoverCompletedEmptySmartNode(node){
    if(!node || (node.images || []).length || smartPendingTasks(node).length || node.pending || node.running || node.apiRunning || ['preparing','queued','running'].includes(node.generationState)) return false;
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
    const attempt = node?.generationAttemptId;
    const isCurrent = () => !attempt || global.CanvasGenerationLifecycle.isCurrent(node,attempt);
    const tasks = smartPendingTasks(node);
    if(!node || !tasks.length) return;
    node.pending = tasks.length;
    node.running = false;
    node.apiRunning = true;   // 2026-09-17：被恢复的 API 任务也显示「生成中」动效
    deps.syncRunButtonAvailability(node);
    deps.render();
    const failures = [];
    await Promise.all(tasks.map(async task => {
        try {
            const result = await pollSmartCanvasTask(task.taskId);
            if(!isCurrent()) return;
            if(['blender-offline-endpoints','blender-motion-presets'].includes(result?.backend)){
                node.offlinePrevisArtifacts = {blend_url:result.previs_blend_url, spec_url:result.previs_data_url, validation_url:result.validation_url,video_url:result.video_url||'',validation:result.validation||null,preset_id:result.motion_preset||''};
                task.kind = result.output_kind || 'image';
            }
            await finalizeSmartPendingTask(node, task.taskId, result?.images || result?.videos || deps.resultMediaUrls(result), task.kind || 'image', attempt);
            if(!isCurrent()) return;
            deps.render();
            deps.scheduleSave();
        } catch(e) {
            if(!isCurrent()) return;
            if(e && e.jimengPending && e.submitId){
                node.pendingTasks = smartPendingTasks(node).filter(item => item.taskId !== task.taskId);
                setNodeJimengPending(node, e);
                deps.render();
                deps.scheduleSave();
                return;
            }
            // blender 预演「完全依赖插件」：后端渲染完在等插件动画推送，轮询窗口超时≠失败——
            // 不碰 pendingTasks，5 秒后重新武装继续等（推送落地/任务失败/用户停止都会正常退出循环）。
            if(e && (e.message === tr('smart.errRunTimeout') || e.message === 'smart.errRunTimeout') && isPrevizPushWaiting(node)){
                node.previzPushRearms = (node.previzPushRearms || 0) + 1;
                setTimeout(() => {
                    if(!(node.images || []).length && smartPendingTasks(node).length) resumeSmartPendingNode(node);
                }, 5000);
                return;
            }
            node.pendingTasks = smartPendingTasks(node).filter(item => item.taskId !== task.taskId);
            node.pending = smartPendingTasks(node).length;
            if(!node.pending && smartPendingTasks(node).length === 0){
                delete node.pendingTasks;
                node.running = false;
                if(!(node.images || []).length){
                    rememberSmartTaskIds(node, [task.taskId]);
                    node.runError = e.message || tr('smart.errRunFailed');
                    // 2026-10-10：同上，失败/超时不改尺寸
                    if(deps.restoreNodeBoxAfterFailure) deps.restoreNodeBoxAfterFailure(node);
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
    if(!isCurrent()) return;
    node.apiRunning = false;
    if(attempt && !node.pending && !node.jimengPending){
        global.CanvasGenerationLifecycle.finish(node,attempt,(node.images || []).length ? 'succeeded' : 'failed', failures[0]?.message || node.runError, deps.nowMs());
    }
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

    // 2026-10-23 老王（真因）：页面刷新/切画布会掐断前端那条轮询连接，节点可能停在
// apiRunning / pending 却没有 pendingTasks（提交还没落盘就被刷新）。这时
// resumeSmartPendingTasks 与 recoverCompletedEmptySmartNodes 都找不到它 —— 节点
// 永远「生成中」、拿不到结果、也没法重跑，还不报错。
// 载入时按 node_id 去后端任务表收尾：云端在跑就接回轮询，终端态就回填，查不到就解除占用。
function clearInflightFlags(node){
    if(!node) return;
    node.apiRunning = false;
    node.running = false;
    node.pending = 0;
    if(['running','queued','preparing'].includes(node.generationState)) delete node.generationState;
    if(node.comfyStatus === 'running'){
        delete node.comfyStatus;
        node.comfyIndeterminate = false;
        node.comfyProgress = 0;
    }
    if(deps.clearNodeRunningState) deps.clearNodeRunningState(node);
}
function releaseInflightNode(node){
    if(!node) return;
    clearInflightFlags(node);
    delete node.pendingTasks;
}
async function reconcileInflightNodesWithTaskStore(){
    const canvasId = String(D("canvasId") || '');
    if(!canvasId) return;
    const list = (D("nodes") || []).filter(node => node && !node._reconcilingInflight
        && !smartPendingTasks(node).length
        && (node.apiRunning || node.running || Number(node.pending) > 0
            || ['running','queued','preparing'].includes(node.generationState)
            || node.comfyStatus === 'running'));
    if(!list.length) return;
    let tasks = [];
    try{
        const res = await fetch(`${D("proxyBase")}/api/task-console?v=${Date.now()}`, {cache:'no-store'});
        if(!res.ok) return;
        const data = await res.json();
        tasks = (Array.isArray(data.tasks) ? data.tasks : []).filter(t => String(t.canvas_id || '') === canvasId);
    }catch(_){ return; }
    if(!tasks.length) return;
    const latestByNode = new Map();
    tasks.forEach(t => {
        const nid = String(t.node_id || '').trim();
        if(!nid) return;
        const prev = latestByNode.get(nid);
        if(!prev || (Number(t.created_at) || 0) >= (Number(prev.created_at) || 0)) latestByNode.set(nid, t);
    });
    const kindForTask = (task, firstUrl) => {
        if(String(task?.workflow_media || '').toLowerCase() === 'video' || /video/i.test(String(task?.kind || ''))) return 'video';
        const u = String(firstUrl || '');
        if(/\.(mp4|webm|mov)(\?|$)/i.test(u)) return 'video';
        if(/\.(mp3|wav|m4a|aac)(\?|$)/i.test(u)) return 'audio';
        return 'image';
    };
    let changed = false;
    for(const node of list){
        const task = latestByNode.get(String(node.id));
        node._reconcilingInflight = true;
        try{
            const status = String(task?.status || '');
            if(task && ['running','pending','recovering','submitted','queued'].includes(status)){
                // 云端还在跑（后端常驻对账也在收）—— 接回正常轮询，别让它悬着
                node.pendingTasks = [{taskId: task.task_id, kind: kindForTask(task)}];
                node.pending = 1;
                node.apiRunning = true;
                deps.syncRunButtonAvailability(node);
                resumeSmartPendingNode(node).catch(() => {});
                continue;
            }
            if(task && status === 'succeeded'){
                const result = await pollSmartCanvasTask(task.task_id).catch(() => null);
                const media = result?.images || result?.videos || deps.resultMediaUrls(result);
                if(Array.isArray(media) && media.length){
                    const kind = result?.videos ? 'video' : kindForTask(task, (media[0] && media[0].url) || media[0]);
                    await finalizeSmartPendingTask(node, task.task_id, media, kind);
                    // 回填后必须把残留的「生成中」清掉，否则节点一直显示在跑、也不能重跑
                    clearInflightFlags(node);
                    deps.syncRunButtonAvailability(node);
                    changed = true;
                    continue;
                }
            }
            if(task && ['failed','cancelled'].includes(status)){
                releaseInflightNode(node);
                node.runError = String(task.error || '任务失败').slice(0, 160);
                changed = true;
                continue;
            }
            // 任务表里没有对应任务（或已完成但没产物）：解除占用，让节点能重跑
            releaseInflightNode(node);
            changed = true;
        }catch(_){
        }finally{
            delete node._reconcilingInflight;
        }
    }
    if(changed){
        deps.render();
        deps.scheduleSave();
    }
}

    global.CanvasSmartTaskSupervisor = {
        configure,
        JimengPendingSignal,
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
        isPrevizPushWaiting,
        isRecoverableComfyNode,
        recoverStuckComfyNodes,
        resumeSmartPendingTasks,
        recoverCompletedEmptySmartNodes,
        reconcileInflightNodesWithTaskStore,
    };
})(typeof window !== 'undefined' ? window : this);

//** The single-node generation runner: build request, dispatch by engine, finalize or suspend node. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    function D(name){return typeof deps[name] === 'function' ? deps[name]() : deps[name];}

async function runGeneration(){
    const node = deps.selectedNode();
    if(!node) return;
    if(node.type === 'smart-speech') return global.CanvasSpeech.run(node);
    const previousSettings = deps.cloneSmartSettings(D("settings"));
    const runSettings = deps.smartSettingsForNode(node);
    await deps.ensureCustomComfyWorkflowReady(runSettings);
    deps.setSettings({...settings, ...cloneSmartSettings(runSettings || {})});
    const request = deps.buildPromptRequest(node, null, true, D("smartLoopContext"));
    const prompt = request.prompt.trim();
    if(!prompt && !deps.allowsPromptlessCustomComfy(D("settings"))){ deps.toast(tr('smart.toastNeedPrompt')); deps.setSettings(previousSettings); return; }
    let refs = request.refs;
    const outpaintSize = node?.outpaintSize && Number(node.outpaintSize.width) > 0 && Number(node.outpaintSize.height) > 0
        ? {width:Math.round(Number(node.outpaintSize.width)), height:Math.round(Number(node.outpaintSize.height))}
        : null;
 if(outpaintSize && deps.isApiLikeEngine(D("settings").engine) && D("settings").apiKind !== 'video'){
 deps.setSettings({
 ...settings,
 resolution:'custom',
            ratio:'',
            customWidth:outpaintSize.width,
            customHeight:outpaintSize.height,
 customSize:`${outpaintSize.width}x${outpaintSize.height}`
 });
 }
    const nodeHasImages = (node.images || []).some(img => img?.url);
    const workflowModeRun = deps.smartImageUsesWorkflowInput(node, D("smartLoopContext"));
    // History is scoped to the node itself. Input links and neighboring nodes never
    // affect whether this is the node's first generation.
    const overwriteExistingOutput = nodeHasImages && nodeHasCompletedGeneration(node) && !workflowModeRun;
    // 覆盖重跑：新图沿用第一次生图的名称（显示名 + 磁盘文件名），不再按日期重新命名
    const retainedOutputNames = overwriteExistingOutput
        ? (node.images || []).map(img => String(img?.name || '').trim()).filter(Boolean)
        : [];
    const movedOutputAssetUrls = overwriteExistingOutput ? await moveOutputImagesToHistoryForRun(node.images || []) : new Map();
    if(movedOutputAssetUrls.size){
        refs = remapRefsForMovedAssets(refs, movedOutputAssetUrls);
        updatePromptMentionUrlsForMovedAssets(movedOutputAssetUrls);
    }
    const meta = snapshotRunMeta(prompt, node.id, request.displayPrompt, refs);
    const logKind = runKindForSettings(settings);
    const runLog = smartRunSnapshot(node, prompt, refs, logKind);
    rememberRecentSmartSettings(settings, node);
    const runLogStart = nowMs();
    const expectedCount = settings.engine === 'runninghub'
        ? 1
        : settings.engine === 'comfy'
            ? (settings.comfyMode === 'text' || settings.comfyMode === 'enhance' || settings.comfyMode === 'edit' || settings.comfyMode === 'custom' ? 1 : 1)
            : Math.max(1, Math.min(8, Number(settings.count || 1)));
    const apiConcurrentRun = isApiLikeEngine(settings.engine) || settings.engine === 'runninghub';
    const sourceVisualState = null;
    pushUndo();
    deps.preserveNodeCardForRun(node, D("settings"));
    let extracted = null;
    let branchNode = null;
    const pendingMeta = overwriteExistingOutput ? stripRunInputMeta(meta) : meta;
    undoSuppressed = true;
    // Only this node's completed output is replaced on a subsequent run.
    if(overwriteExistingOutput){
        node.images = [];
        deps.setSelectedImage({nodeId:'', index:-1});
    }
    deps.setUndoSuppressed(false);
    const pendingNode = branchNode || node;
    const comfyRunToken = D("settings").engine === 'comfy' ? deps.uid('comfy_run') : '';
    if(comfyRunToken) pendingNode.comfyRunToken = comfyRunToken;
    // 保留名持久化到节点：覆盖重跑=沿用第一次生图名；非覆盖（首跑/追加）=清掉
    if(retainedOutputNames.length) pendingNode.retainOutputNames = retainedOutputNames;
    else delete pendingNode.retainOutputNames;
    if(extracted) pendingNode._runMetaTargetId = extracted.id;
    if(!branchNode){
        pendingNode.pending = Math.max(1, Number(expectedCount) || 1);
        pendingNode.runStartedAt = deps.nowMs();
        delete pendingNode.runFinishedAt;
        delete pendingNode.runElapsedMs;
        pendingNode.runTimerHidden = false;
        const pendingBox = deps.pendingBoxSize(pendingNode.pending, {sourceNode:node, refs});
        pendingNode.w = pendingBox.w;
        pendingNode.h = pendingBox.h;
        deps.attachRunMeta(pendingNode, pendingMeta);
    }
    if(apiConcurrentRun){
        // API tasks expose their own pending state and may run alongside other nodes.
        // Do not lock the shared composer button while the request is in flight.
        pendingNode.running = false;
        // 2026-09-17：API 并发任务不锁按钮，但要让按钮进入「生成中」动效，
        // 用独立标记 node.apiRunning 驱动 is-ap-running（不依赖 node.running）。
        pendingNode.apiRunning = true;
        deps.syncRunButtonAvailability(pendingNode);
    } else {
        pendingNode.running = true;
        deps.syncRunButtonAvailability(pendingNode);
    }
    deps.render();
    try {
        if(D("settings").engine === 'comfy'){
            await deps.runComfyGeneration(pendingNode, prompt, refs, pendingNode, pendingMeta);
            if(sourceVisualState) deps.restoreSourceVisualState(node, sourceVisualState);
            deps.addSmartGenerationLog({run:runLog, outputs:(pendingNode.images || []).map(img => img.url).filter(Boolean), runMs:deps.nowMs() - runLogStart});
            deps.setSettings(previousSettings);
            return;
        }
        if((deps.isApiLikeEngine(D("settings").engine) && D("settings").apiKind === 'video') || D("settings").engine === 'blender'){
            const videoResult = D("settings").engine === 'blender'
                ? await deps.runApiGeneration(prompt, refs, D("settings"), node)
                : await deps.runApiVideoGeneration(prompt, refs);
            const taskIds = deps.taskIdsFromResult(videoResult);
            const outVideos = videoResult?.urls || deps.resultMediaUrls(videoResult);
            if(taskIds.length && !outVideos.length){
                pendingNode.pendingTasks = taskIds.map(taskId => ({taskId, kind:'video'}));
                deps.rememberSmartTaskIds(pendingNode, taskIds);
                pendingNode.pending = Math.max(taskIds.length, Number(pendingNode.pending || 0) || taskIds.length);
                pendingNode.runStartedAt = deps.nowMs();
                pendingNode.runTimerHidden = false;
                pendingNode.running = false;
                deps.render();
                deps.scheduleSave();
                await deps.saveCanvas();
                await deps.resumeSmartPendingNode(pendingNode);
                if(!(pendingNode.images || []).length) throw new Error(tr('smart.errNoOutVideos'));
                if(sourceVisualState) deps.restoreSourceVisualState(node, sourceVisualState);
                deps.addSmartGenerationLog({run:runLog, outputs:(pendingNode.images || []).map(img => img.url).filter(Boolean), runMs:deps.nowMs() - runLogStart});
                deps.clearPromptInput({preserveDraft:true});
                deps.setSettings(previousSettings);
                deps.scheduleSave();
                return;
            }
            if(!outVideos.length) throw new Error(tr('smart.errNoOutVideos'));
            await deps.finalizePendingNode(pendingNode, outVideos, pendingMeta, 'video');
            if(sourceVisualState) deps.restoreSourceVisualState(node, sourceVisualState);
            deps.addSmartGenerationLog({run:runLog, outputs:outVideos, runMs:deps.nowMs() - runLogStart});
            deps.clearPromptInput({preserveDraft:true});
            deps.setSettings(previousSettings);
            deps.scheduleSave();
            return;
        }
        // 2026-09-18：云端 RH-api 工作流没有实时进度百分比，但要让节点保持「运行中」视觉
        // （边框进度环 + comfy-running 蓝色边框），否则点一下运行态就消失。
        // 用 comfyStatus='running' 触发现有进度环，comfyIndeterminate 标记走「整圈流光」渲染。
        if(D("settings").engine === 'runninghub'){
            pendingNode.comfyStatus = 'running';
            pendingNode.comfyIndeterminate = true;
            deps.syncRunButtonAvailability(pendingNode);
            deps.updateComfyNodeLiveState(pendingNode);
        }
        const outImages = D("settings").engine === 'runninghub'
            ? await deps.runRunningHubGeneration(prompt, refs): await deps.runApiGeneration(prompt, refs, D("settings"), node);
        if(deps.isApiLikeEngine(D("settings").engine)){
            const taskIds = Array.isArray(outImages?.taskIds) ? outImages.taskIds : [];
            if(!taskIds.length) throw new Error(tr('smart.errRunFailed'));
            pendingNode.pendingTasks = taskIds.map(taskId => ({taskId, kind:'image'}));
            deps.rememberSmartTaskIds(pendingNode, taskIds);
            pendingNode.pending = Math.max(taskIds.length, Number(pendingNode.pending || 0) || taskIds.length);
            pendingNode.runStartedAt = deps.nowMs();
            pendingNode.runTimerHidden = false;
            pendingNode.running = false;
            deps.render();
            deps.scheduleSave();
            await deps.saveCanvas();
            await deps.resumeSmartPendingNode(pendingNode);
            if(pendingNode.jimengPending){
                if(sourceVisualState) deps.restoreSourceVisualState(node, sourceVisualState);
                deps.clearPromptInput({preserveDraft:true});
                deps.setSettings(previousSettings);
                deps.scheduleSave();
                return;
            }
            if(!(pendingNode.images || []).length) throw new Error(tr('smart.errNoOutImages'));
            if(outpaintSize) delete node.outpaintSize;
            if(sourceVisualState) deps.restoreSourceVisualState(node, sourceVisualState);
            deps.addSmartGenerationLog({run:runLog, outputs:(pendingNode.images || []).map(img => img.url).filter(Boolean), runMs:deps.nowMs() - runLogStart});
            deps.clearPromptInput({preserveDraft:true});
            deps.setSettings(previousSettings);
            deps.scheduleSave();
            return;
        }
        if(!outImages.length) throw new Error(tr('smart.errNoOutImages'));
        if(outpaintSize) delete node.outpaintSize;
        await deps.finalizePendingNode(pendingNode, outImages, pendingMeta);
        if(sourceVisualState) deps.restoreSourceVisualState(node, sourceVisualState);
        deps.addSmartGenerationLog({run:runLog, outputs:outImages, runMs:deps.nowMs() - runLogStart});
        deps.clearPromptInput({preserveDraft:true});
        deps.setSettings(previousSettings);
        deps.scheduleSave();
    } catch(e) {
        if(comfyRunToken && pendingNode.comfyRunToken !== comfyRunToken) return;
        deps.setSettings(previousSettings);
        if(deps.handleJimengPendingSignal(pendingNode, e)){
            if(sourceVisualState) deps.restoreSourceVisualState(node, sourceVisualState);
            delete pendingNode._runMetaTargetId;
            deps.clearPromptInput({preserveDraft:true});
            return;
        }
        pendingNode.pending = 0;
        // ComfyUI 失败/记录丢失/超时：连 comfy 运行态一起清，别留节点卡在「正在生成…」
        if(pendingNode.comfyJobId || pendingNode.comfyStatus) deps.clearComfyRunStateKeepPromptId(pendingNode);
        if(branchNode){
            D("nodeStore").removeNode(branchNode.id);
            D("canvas").connections = (D("canvas").connections || []).filter(c => c.from !== branchNode.id && c.to !== branchNode.id);
            deps.setSelectedId(node.id);
        } else {
            pendingNode.pending = 0;
            pendingNode.running = false;
            if(!(pendingNode.images || []).length){
                delete pendingNode.w;
                delete pendingNode.h;
            }
        }
        if(extracted) deps.restoreFromExtraction(node, extracted);
        delete pendingNode._runMetaTargetId;
        deps.addSmartGenerationLog({run:runLog, outputs:[], runMs:deps.nowMs() - runLogStart, error:e.message || String(e)});
        deps.toast((e.message || tr('smart.errRunFailed')).slice(0, 160));
    } finally {
        if(comfyRunToken && pendingNode.comfyRunToken !== comfyRunToken) return;
        if(!apiConcurrentRun){
            deps.clearNodeRunningState(pendingNode);
            deps.syncRunButtonAvailability();
        } else {
            // 2026-09-17：清掉 API 运行动效标记，让按钮回到待机态
            delete pendingNode.apiRunning;
            deps.syncRunButtonAvailability();
        }
        // 2026-09-18：清掉云端 RH-api 运行时挂的 indeterminate 进度环标记。
        // 非 ComfyUI 模式（无 comfyJobId）设的 comfyStatus 也一并清，避免节点卡在 running 视觉。
        delete pendingNode.comfyIndeterminate;
        if(!pendingNode.comfyJobId) delete pendingNode.comfyStatus;
        if(comfyRunToken) delete pendingNode.comfyRunToken;
        deps.render();
    }
}

    global.CanvasGenerationRunner = {
        configure,
        runGeneration,
    };
})(typeof window !== 'undefined' ? window : this);

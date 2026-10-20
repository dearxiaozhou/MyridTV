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
    const executionSettings = deps.cloneSmartSettings(deps.smartSettingsForNode(node));
    const lifecycle = global.CanvasGenerationLifecycle;
    const attempt = lifecycle.begin(node, {id:deps.uid('generation_run')});
    const isCurrent = () => lifecycle.isCurrent(node, attempt) && (D('nodes') || []).includes(node);
    const ownsEditor = () => deps.selectedNode()?.id === node.id;
    // Legacy synchronous request/meta helpers read the shared settings getter.
    // Borrow it only for the synchronous call, never across an await.
    const withRunSettings = action => {
        const current = D("settings");
        deps.setSettings(executionSettings);
        try { return action(); } finally { deps.setSettings(current); }
    };
    try { await deps.ensureCustomComfyWorkflowReady(executionSettings); }
    catch(error){ if(isCurrent()) lifecycle.finish(node,attempt,'failed',error.message); throw error; }
    if(!isCurrent()) return;
    const request = withRunSettings(() => deps.buildPromptRequest(node, null, true, D("smartLoopContext")));
    const prompt = request.prompt.trim() || (executionSettings.engine === 'blender' && ['endpoints','motion'].includes(executionSettings.previzOutput) ? '运镜预设预览' : '');
    if(!prompt && !deps.allowsPromptlessCustomComfy(executionSettings)){ deps.toast(tr('smart.toastNeedPrompt')); lifecycle.finish(node,attempt,'cancelled'); return; }
    let refs = request.refs;
    const outpaintSize = node?.outpaintSize && Number(node.outpaintSize.width) > 0 && Number(node.outpaintSize.height) > 0
        ? {width:Math.round(Number(node.outpaintSize.width)), height:Math.round(Number(node.outpaintSize.height))}
        : null;
 if(outpaintSize && deps.isApiLikeEngine(executionSettings.engine) && executionSettings.apiKind !== 'video'){
 Object.assign(executionSettings, {
 resolution:'custom',
            ratio:'',
            customWidth:outpaintSize.width,
            customHeight:outpaintSize.height,
 customSize:`${outpaintSize.width}x${outpaintSize.height}`
 });
 }
    const nodeHasImages = (node.images || []).some(img => img?.url);
    // Uploaded inputs and earlier generated results both belong to this node.
    // Re-generation keeps the node identity and archives the previous image on disk.
    const overwriteExistingOutput = nodeHasImages;
    node.outputPlacement = 'replace';
    // 2026-10-09 老王拍板：保留名机制已移除 —— 画布素材名与磁盘文件名保持一致，
    // 覆盖重跑产物按新落盘名命名，旧产物只进本地 history，不创建画布历史分组。
    let movedOutputAssetUrls;
    try {
        movedOutputAssetUrls = overwriteExistingOutput ? await moveOutputImagesToHistoryForRun(node.images || [], {strict:true}) : new Map();
    } catch(error) {
        if(!isCurrent()) return;
        lifecycle.finish(node,attempt,'failed','旧图归档失败，已保留当前素材：' + (error.message || String(error)));
        deps.toast(node.runError);
        deps.render(); deps.scheduleSave();
        return;
    }
    if(!isCurrent()) return;
    if(movedOutputAssetUrls.size){
        refs = remapRefsForMovedAssets(refs, movedOutputAssetUrls);
        updatePromptMentionUrlsForMovedAssets(movedOutputAssetUrls);
    }
    const archivedPreviousImages = overwriteExistingOutput ? (node.images || []).map(image => ({...image})) : [];
    const meta = {...withRunSettings(() => snapshotRunMeta(prompt, node.id, request.displayPrompt, refs)), generationAttemptId:attempt};
    if(!ownsEditor()){
        meta.promptHtml = node.promptDraftHtml;
        meta.promptText = node.promptDraftText || request.displayPrompt || prompt;
    }
    const logKind = runKindForSettings(executionSettings);
    const runLog = withRunSettings(() => smartRunSnapshot(node, prompt, refs, logKind));
    rememberRecentSmartSettings(executionSettings, node);
    const runLogStart = nowMs();
    const expectedCount = executionSettings.engine === 'runninghub'
        ? 1
        : executionSettings.engine === 'comfy'
            ? (executionSettings.comfyMode === 'text' || executionSettings.comfyMode === 'enhance' || executionSettings.comfyMode === 'edit' || executionSettings.comfyMode === 'custom' ? 1 : 1)
            : Math.max(1, Math.min(8, Number(executionSettings.count || 1)));
    const apiConcurrentRun = isApiLikeEngine(executionSettings.engine) || executionSettings.engine === 'runninghub';
    const sourceVisualState = null;
    pushUndo();
    deps.preserveNodeCardForRun(node, executionSettings);
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
    const comfyRunToken = executionSettings.engine === 'comfy' ? deps.uid('comfy_run') : '';
    if(comfyRunToken) pendingNode.comfyRunToken = comfyRunToken;
    // 保留名机制已移除（2026-10-09）：清理存量节点上遗留的 retainOutputNames 字段
    delete pendingNode.retainOutputNames;
    if(extracted) pendingNode._runMetaTargetId = extracted.id;
    if(!branchNode){
        pendingNode.pending = Math.max(1, Number(expectedCount) || 1);
        pendingNode.runStartedAt = deps.nowMs();
        delete pendingNode.runFinishedAt;
        delete pendingNode.runElapsedMs;
        pendingNode.runTimerHidden = false;
        const pendingBox = pendingNode.cardSize
            ? {w:pendingNode.cardSize.width, h:pendingNode.cardSize.height}
            : deps.pendingBoxSize(pendingNode.pending, {sourceNode:node, refs});
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
    lifecycle.transition(pendingNode,attempt,'running');
    deps.render();
    try {
        if(executionSettings.engine === 'comfy'){
            await withRunSettings(() => deps.runComfyGeneration(pendingNode, prompt, refs, pendingNode, pendingMeta, executionSettings));
            if(!isCurrent()) return;
            if(sourceVisualState) deps.restoreSourceVisualState(node, sourceVisualState);
            deps.addSmartGenerationLog({run:runLog, outputs:(pendingNode.images || []).map(img => img.url).filter(Boolean), runMs:deps.nowMs() - runLogStart});

            return;
        }
        if((deps.isApiLikeEngine(executionSettings.engine) && executionSettings.apiKind === 'video') || executionSettings.engine === 'blender'){
            const generationKind = executionSettings.engine === 'blender' && executionSettings.previzOutput === 'endpoints' ? 'image' : 'video';
            const videoResult = executionSettings.engine === 'blender'
                ? await deps.runApiGeneration(prompt, refs, executionSettings, node)
                : await deps.runApiVideoGeneration(prompt, refs, executionSettings);
            if(!isCurrent()) return;
            const taskIds = deps.taskIdsFromResult(videoResult);
            const outVideos = videoResult?.urls || deps.resultMediaUrls(videoResult);
            if(taskIds.length && !outVideos.length){
                pendingNode.pendingTasks = taskIds.map(taskId => ({taskId, kind:generationKind}));
                deps.rememberSmartTaskIds(pendingNode, taskIds);
                pendingNode.pending = taskIds.length;
                pendingNode.runStartedAt = deps.nowMs();
                pendingNode.runTimerHidden = false;
                pendingNode.running = false;
                deps.render();
                deps.scheduleSave();
                await deps.saveCanvas();
                await deps.resumeSmartPendingNode(pendingNode);
                if(!isCurrent()) return;
                // blender 预演：渲染完在等插件回传（完全依赖插件），节点保持等待态，不算失败
                if(!(pendingNode.images || []).length && deps.isPrevizPushWaiting && deps.isPrevizPushWaiting(pendingNode)) return;
                if(!(pendingNode.images || []).length) throw new Error(tr('smart.errNoOutVideos'));
                if(sourceVisualState) deps.restoreSourceVisualState(node, sourceVisualState);
                deps.addSmartGenerationLog({run:runLog, outputs:(pendingNode.images || []).map(img => img.url).filter(Boolean), runMs:deps.nowMs() - runLogStart});
                if(ownsEditor()) deps.clearPromptInput({preserveDraft:true});

                deps.scheduleSave();
                return;
            }
            if(!outVideos.length) throw new Error(tr('smart.errNoOutVideos'));
            await deps.finalizePendingNode(pendingNode, outVideos, pendingMeta, generationKind);
            if(!isCurrent()) return;
            if(sourceVisualState) deps.restoreSourceVisualState(node, sourceVisualState);
            deps.addSmartGenerationLog({run:runLog, outputs:outVideos, runMs:deps.nowMs() - runLogStart});
            if(ownsEditor()) deps.clearPromptInput({preserveDraft:true});

            deps.scheduleSave();
            return;
        }
        // 2026-09-18：云端 RH-api 工作流没有实时进度百分比，但要让节点保持「运行中」视觉
        // （边框进度环 + comfy-running 蓝色边框），否则点一下运行态就消失。
        // 用 comfyStatus='running' 触发现有进度环，comfyIndeterminate 标记走「整圈流光」渲染。
        if(executionSettings.engine === 'runninghub'){
            pendingNode.comfyStatus = 'running';
            pendingNode.comfyIndeterminate = true;
            deps.syncRunButtonAvailability(pendingNode);
            deps.updateComfyNodeLiveState(pendingNode);
        }
        const outImages = executionSettings.engine === 'runninghub'
            ? await deps.runRunningHubGeneration(prompt, refs, executionSettings): await deps.runApiGeneration(prompt, refs, executionSettings, node);
        if(!isCurrent()) return;
        if(deps.isApiLikeEngine(executionSettings.engine)){
            const taskIds = Array.isArray(outImages?.taskIds) ? outImages.taskIds : [];
            if(!taskIds.length) throw new Error(tr('smart.errRunFailed'));
            pendingNode.pendingTasks = taskIds.map(taskId => ({taskId, kind:'image'}));
            deps.rememberSmartTaskIds(pendingNode, taskIds);
            pendingNode.pending = taskIds.length;
            pendingNode.runStartedAt = deps.nowMs();
            pendingNode.runTimerHidden = false;
            pendingNode.running = false;
            deps.render();
            deps.scheduleSave();
            await deps.saveCanvas();
            await deps.resumeSmartPendingNode(pendingNode);
                if(!isCurrent()) return;
            if(pendingNode.jimengPending){
                if(sourceVisualState) deps.restoreSourceVisualState(node, sourceVisualState);
                if(ownsEditor()) deps.clearPromptInput({preserveDraft:true});

                deps.scheduleSave();
                return;
            }
            if(!(pendingNode.images || []).length) throw new Error(tr('smart.errNoOutImages'));
            if(outpaintSize) delete node.outpaintSize;
            if(sourceVisualState) deps.restoreSourceVisualState(node, sourceVisualState);
            deps.addSmartGenerationLog({run:runLog, outputs:(pendingNode.images || []).map(img => img.url).filter(Boolean), runMs:deps.nowMs() - runLogStart});
            if(ownsEditor()) deps.clearPromptInput({preserveDraft:true});

            deps.scheduleSave();
            return;
        }
        if(!outImages.length) throw new Error(tr('smart.errNoOutImages'));
        if(outpaintSize) delete node.outpaintSize;
        await deps.finalizePendingNode(pendingNode, outImages, pendingMeta);
            if(!isCurrent()) return;
        if(sourceVisualState) deps.restoreSourceVisualState(node, sourceVisualState);
        deps.addSmartGenerationLog({run:runLog, outputs:outImages, runMs:deps.nowMs() - runLogStart});
        if(ownsEditor()) deps.clearPromptInput({preserveDraft:true});

        deps.scheduleSave();
    } catch(e) {
        if(!isCurrent()) return;
        if(comfyRunToken && pendingNode.comfyRunToken !== comfyRunToken) return;
        if(!branchNode && !(pendingNode.images || []).length && archivedPreviousImages.length){
            pendingNode.images = archivedPreviousImages;
        }

        if(deps.handleJimengPendingSignal(pendingNode, e)){
            if(sourceVisualState) deps.restoreSourceVisualState(node, sourceVisualState);
            delete pendingNode._runMetaTargetId;
            if(ownsEditor()) deps.clearPromptInput({preserveDraft:true});
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
                deps.preserveNodeCardForRun(pendingNode);
            }
        }
        if(extracted) deps.restoreFromExtraction(node, extracted);
        delete pendingNode._runMetaTargetId;
        lifecycle.finish(pendingNode,attempt,'failed',e.message || String(e),deps.nowMs());
        deps.addSmartGenerationLog({run:runLog, outputs:[], runMs:deps.nowMs() - runLogStart, error:e.message || String(e)});
        deps.toast((e.message || tr('smart.errRunFailed')).slice(0, 160));
    } finally {
        if(!isCurrent()) return;
        if(comfyRunToken && pendingNode.comfyRunToken !== comfyRunToken) return;
        if(!apiConcurrentRun){
            deps.clearNodeRunningState(pendingNode);
            deps.syncRunButtonAvailability();
        } else {
            // 2026-09-17：清掉 API 运行动效标记，让按钮回到待机态
            delete pendingNode.apiRunning;
            deps.syncRunButtonAvailability();
        }
        if(!pendingNode.pending && !pendingNode.jimengPending && !pendingNode.runError) lifecycle.finish(pendingNode,attempt,'succeeded','',deps.nowMs());
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

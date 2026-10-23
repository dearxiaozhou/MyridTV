//** The smart-cascade runner: execute a graph of cascade steps/loop rounds into output slots. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    function D(name){return typeof deps[name] === 'function' ? deps[name]() : deps[name];}

async function runSmartCascade(targetNode=null){
    const tail = targetNode || deps.selectedNode();
    if(!deps.canRunSmartCascade(tail)){ deps.toast('请选择链路结尾图片节点'); return; }
    deps.savePromptDraftForCurrent();
    const graph = deps.smartCascadeGraphForTail(tail);
    const chain = graph.path;
    const loop = deps.resolveSmartCascadeLoop(tail.id);
    const loopId = loop?.node?.id || '';
    if(loopId && deps.smartCascadeIsLoopRunning(loopId)){ deps.requestSmartCascadeStop(loopId); return; }
    if(!loopId && deps.smartCascadeAnyRunning()){ deps.requestSmartCascadeStop(); return; }
    const directLoopTargetRun = Boolean(loop && deps.isDirectLoopTargetRun(loop, tail, graph));
    const singleNodeLoopRun = Boolean(loop && (chain.length === 1 || directLoopTargetRun));
    if(!graph.edges.length && !singleNodeLoopRun){ deps.toast(tr('smart.loopNoChain')); return; }
    const originalSelected = D("selectedId");
    const originalSettings = deps.cloneSmartSettings(D("settings"));
    const originalPromptHtml = D("promptInput").innerHTML;
    const runKey = loopId || `cascade-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const runState = {runKey, loopId, stopRequested:false, runPath:null};
    D("smartCascadeRuns").set(runKey, runState);
    deps.syncSmartCascadeLegacyState(runKey);
    deps.setSmartCascadeSilentSelection(true);
    D("runBtn").disabled = true;
    if(D("cascadeRunBtn")) D("cascadeRunBtn").disabled = false;
    deps.pushUndo();
    const totalRounds = loop?.count || 1;
    const startIndex = Math.max(1, Number(loop?.node?.loopStart) || 1);
    const batchSize = loop?.node?.imageInput ? Math.max(1, Math.min(100, Number(loop.node.imageBatchSize) || 1)) : 1;
    const endIndex = startIndex + (totalRounds - 1) * batchSize;
    const loopMode = loop?.mode === 'parallel' ? 'parallel' : 'serial';
    const parallelLimit = loopMode === 'parallel' && totalRounds > 1 ? deps.smartCascadeParallelLimit(chain) : 1;
    const precreateSingleSlots = singleNodeLoopRun && loopMode === 'parallel' && totalRounds > 1 && parallelLimit > 1;
    let singleLoopSlots = [];
    if(singleNodeLoopRun){
        runState.runPath = {states:{}};
        deps.setSmartCascadeRunPath(runState.runPath);
    }
    if(singleNodeLoopRun){
        singleLoopSlots = Array.from({length:totalRounds}, (_, round) => {
            const loopIndex = startIndex + round * batchSize;
            const slot = deps.loopOutputSlotForRound(tail, loop.node, loopIndex, round);
            return slot ? deps.tagLoopOutputSlot(slot, tail, loop.node, loopIndex, round) : null;
        });
        singleLoopSlots.filter(Boolean).forEach(slot => { runState.runPath.states[`${tail.id}->${slot.id}`] = 'wait'; });
        if(precreateSingleSlots){
            for(let slotOffset = 0; slotOffset < totalRounds; slotOffset++){
                if(singleLoopSlots[slotOffset]) continue;
                const loopIndex = startIndex + slotOffset * batchSize;
                singleLoopSlots[slotOffset] = deps.createLoopOutputSlot(tail, loopIndex, slotOffset, {queued:true, loopNode:loop.node, slotIndex:slotOffset, runState});
            }
        }
        deps.render();
    }
    if(!singleNodeLoopRun){
        const runStates = {};
        if(loop?.node?.id && graph.root?.id) runStates[`${loop.node.id}->${graph.root.id}`] = 'wait';
        graph.edges.forEach(edge => { runStates[edge.key] = 'wait'; });
        runState.runPath = {states:runStates};
        deps.setSmartCascadeRunPath(runState.runPath);
        deps.refreshConnectionLayer();
        deps.updateComposer();
    }
    try {
        const runRound = async (loopIndex=startIndex, options={}) => {
            deps.throwIfSmartCascadeStopRequested(runState);
            const ctx = loop ? {index:loopIndex, total:endIndex, nodeId:loop.node.id, forceWorkflow:chain.length > 1 && !singleNodeLoopRun, runState} : {runState};
            if(parallelLimit === 1) deps.setSmartLoopContext(ctx);
            if(singleNodeLoopRun){
                const refs = deps.refsForDirectLoopRound(loop.node, loopIndex, endIndex);
                if(directLoopTargetRun && parallelLimit === 1) deps.showDirectLoopRoundPreview(loop.node, tail, refs, loopIndex, endIndex);
                const slotIndex = Math.max(0, Math.floor((loopIndex - startIndex) / batchSize));
                const outputTarget = deps.tagLoopOutputSlot(
                    options.outputTarget || singleLoopSlots[slotIndex] || deps.loopOutputSlotForRound(tail, loop.node, loopIndex, slotIndex) || deps.createLoopOutputSlot(tail, loopIndex, slotIndex, {loopNode:loop.node, slotIndex, runState}),
                    tail,
                    loop.node,
                    loopIndex,
                    slotIndex
                );
                singleLoopSlots[slotIndex] = outputTarget;
                await deps.runLoopRoundIntoSlot(loop.node, tail, outputTarget, loopIndex, ctx);
                return;
            }
            const producedRefs = new Map();
            const runBranch = async (source, incomingRefs=[]) => {
                deps.throwIfSmartCascadeStopRequested(runState);
                let targets = graph.children.get(source.id) || [];
                const loopPrompts = deps.isSmartImageNode(source) ? deps.upstreamLoopPromptNodesFor(source) : [];
                const sourceLoopPrompts = deps.isSmartImageNode(source) ? deps.relayLoopPromptNodesForTarget(source) : [];
                if(runState.runPath && sourceLoopPrompts.length && source?.id){
                    sourceLoopPrompts.forEach(loopNode => {
                        runState.runPath.states[`${loopNode.id}->${source.id}`] = 'done';
                    });
                    deps.refreshConnectionLayer();
                }
                if(loopPrompts.length && targets.length > 1){
                    const firstLoop = loopPrompts[0];
                    const startBase = Math.max(1, Number(firstLoop.loopStart) || 1);
                    const currentIndex = Math.max(1, Number(ctx?.index || startBase) || startBase);
                    const selectedTarget = targets[(currentIndex - 1) % targets.length];
                    if(runState.runPath && firstLoop?.id && source?.id){
                        runState.runPath.states[`${firstLoop.id}->${source.id}`] = 'done';
                        deps.refreshConnectionLayer();
                    }
                    targets = [selectedTarget].filter(Boolean);
                }
                let sharedRefs = incomingRefs;
                for(let index = 0; index < targets.length; index++){
                    deps.throwIfSmartCascadeStopRequested(runState);
                    const target = targets[index];
                    const edgeKey = `${source.id}->${target.id}`;
                    let outputs = [];
                    const relayLoops = deps.isSmartImageNode(source) && deps.isSmartImageNode(target)
                        ? deps.relayLoopPromptNodesForEdge(source, target)
                        : [];
                    const stepCtx = relayLoops.length && deps.isSmartImageNode(target)
                        ? {...(ctx || {}), relayPromptNodeIds:[...new Set([...(ctx?.relayPromptNodeIds || []), ...relayLoops.map(n => n.id)])]}
                        : ctx;
                    try {
                        if(runState.runPath && relayLoops.length && source?.id && deps.isSmartImageNode(target)){
                            relayLoops.forEach(loopNode => {
                                runState.runPath.states[`${loopNode.id}->${source.id}`] = 'done';
                            });
                            deps.refreshConnectionLayer();
                        }
                        if(runState.runPath){
                            runState.runPath.states[edgeKey] = 'active';
                            deps.refreshConnectionLayer();
                        }
                        if(target.type === 'smart-loop'){
                            outputs = deps.outputImagesForNode(source, true, ctx).filter(img => img?.url);
                            sharedRefs = deps.cascadeRefsFromOutputs(outputs, source);
                        } else if(index === 0){
                            outputs = await deps.runCascadeStepIntoNode(source, target, incomingRefs, stepCtx);
                            sharedRefs = deps.cascadeRefsFromOutputs(outputs, target);
                        } else {
                            outputs = await deps.appendCascadeRefsToReceiver(target, sharedRefs, stepCtx);
                        }
                    } catch(err) {
                        if(/缺少提示词|需要输入文本|need prompt/i.test(err.message || '') && incomingRefs.length){
                            outputs = await deps.appendCascadeRefsToReceiver(target, incomingRefs, stepCtx);
                            if(index === 0){
                                sharedRefs = deps.cascadeRefsFromOutputs(outputs, target);
                            }
                        } else {
                            throw err;
                        }
                    }
                    if(runState.runPath){
                        runState.runPath.states[edgeKey] = 'done';
                        deps.refreshConnectionLayer();
                    }
                    const refs = target.type === 'smart-loop' ? sharedRefs : (index === 0 ? sharedRefs : deps.cascadeRefsFromOutputs(outputs, target));
                    producedRefs.set(target.id, refs);
                    deps.throwIfSmartCascadeStopRequested(runState);
                    await runBranch(target, refs);
                }
            };
            const rootRefs = deps.defaultReferenceImagesFor(graph.root, true, ctx).filter(img => img?.url);
            producedRefs.set(graph.root.id, rootRefs);
            await runBranch(graph.root, rootRefs);
        };
        const roundIndexes = Array.from({length:totalRounds}, (_, round) => startIndex + round * batchSize);
        if(loopMode === 'parallel' && totalRounds > 1){
            const parallelTargets = singleNodeLoopRun
                ? singleLoopSlots
                : [];
            if(parallelTargets.length) deps.render();
            await deps.runSmartCascadeRoundsWithLimit(roundIndexes, parallelLimit, (loopIndex, roundOffset) => {
                const outputTarget = parallelTargets[roundOffset] || null;
                return runRound(loopIndex, {outputTarget});
            }, runState);
        } else {
            for(const loopIndex of roundIndexes){
                deps.throwIfSmartCascadeStopRequested(runState);
                await runRound(loopIndex);
            }
        }
        deps.throwIfSmartCascadeStopRequested(runState);
        if(parallelLimit === 1) deps.setSmartLoopContext(null);
        deps.setSelectedId('');
        deps.setSelectedIds([]);
        deps.setSelectedImage({nodeId:'', index:-1});
        deps.setActiveComposerSubject(null);
        deps.setLastComposerNodeId('');
        D("composer").classList.remove('open');
        deps.setSettings(originalSettings);
        D("promptInput").innerHTML = originalPromptHtml;
        deps.scheduleSave();
        deps.toast(totalRounds > 1
            ? deps.trf(loopMode === 'parallel' ? 'smart.loopParallelRoundsDone' : 'smart.loopRunRoundsDone', {n:totalRounds})
            : tr('smart.loopRunDone'));
    } catch(e) {
        if(parallelLimit === 1) deps.setSmartLoopContext(null);
        deps.setSelectedId(originalSelected);
        deps.setSettings(originalSettings);
        D("promptInput").innerHTML = originalPromptHtml;
        deps.toast(e?.smartCascadeStopped ? '已停止一键运行' : (e.message || tr('smart.errRunFailed')).slice(0, 160));
    } finally {
        D("smartCascadeRuns").delete(runKey);
        deps.syncSmartCascadeLegacyState();
        deps.setSmartCascadeSilentSelection(false);
        D("runBtn").disabled = deps.smartCascadeAnyRunning();
        if(D("cascadeRunBtn")) D("cascadeRunBtn").disabled = false;
        if(directLoopTargetRun) deps.finishLoopTargetPreviewState(tail);
        deps.scheduleSave();
        deps.render();
    }
}

    global.CanvasSmartCascadeRunner = {
        configure,
        runSmartCascade,
    };
})(typeof window !== 'undefined' ? window : this);

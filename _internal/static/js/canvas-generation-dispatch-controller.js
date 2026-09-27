/* Routes one canvas generation request to the selected engine and normalizes outputs. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    async function generate(node, prompt, refs, runSettings){
        const activeSettings = runSettings || deps.getSettings();
        if(activeSettings.engine === 'comfy'){
            return deps.generateComfyUrlsWithSettings(activeSettings, prompt, refs, node);
        }
        if(deps.isApiLikeEngine(activeSettings.engine) && activeSettings.apiKind === 'video'){
            const videoResult = await deps.runApiVideoGeneration(prompt, refs, activeSettings);
            const taskIds = deps.taskIdsFromResult(videoResult);
            const directUrls = videoResult?.urls || deps.resultMediaUrls(videoResult);
            if(taskIds.length && !directUrls.length){
                const settled = await Promise.all(taskIds.map(taskId => deps.pollSmartCanvasTask(taskId)));
                const urls = settled.flatMap(result => deps.resultMediaUrls(result?.videos || result?.images || result)).filter(Boolean);
                return {urls, kind:'video'};
            }
            return {urls:directUrls, kind:'video'};
        }
        if(deps.isApiLikeEngine(activeSettings.engine)){
            const taskResult = await deps.runApiGeneration(prompt, refs, activeSettings, node);
            const taskIds = Array.isArray(taskResult?.taskIds) ? taskResult.taskIds : [];
            if(taskIds.length){
                const settled = await Promise.all(taskIds.map(taskId => deps.pollSmartCanvasTask(taskId)));
                const urls = settled.flatMap(result => deps.resultMediaUrls(result?.images || result)).filter(Boolean);
                return {urls, kind:deps.mediaKindForUrls(urls, 'image')};
            }
            const urls = deps.resultMediaUrls(taskResult);
            return {urls, kind:deps.mediaKindForUrls(urls, 'image')};
        }
        const urls = activeSettings.engine === 'runninghub'
            ? await deps.runRunningHubGeneration(prompt, refs, activeSettings): [];
        return {urls, kind:deps.mediaKindForUrls(urls, 'image')};
    }

    global.CanvasGenerationDispatchController = {configure, generate};
})(typeof window !== 'undefined' ? window : globalThis);

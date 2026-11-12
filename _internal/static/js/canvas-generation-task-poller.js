/* Polls canvas generation jobs, coalescing concurrent requests by task id. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    async function poll(taskId){
        if(!taskId) throw new Error(deps.translate('smart.errRunFailed'));
        if(deps.activePolls.has(taskId)) return deps.activePolls.get(taskId);
        const maxAttempts = Number(deps.maxAttempts) || 900;
        const intervalMs = Number(deps.intervalMs) || 2000;
        const promise = (async () => {
            for(let i = 0; i < maxAttempts; i++){
                await deps.wait(intervalMs);
                const taskBase = String(taskId || '').startsWith('rhproxy_') ? deps.proxyBase() : '';
                const response = await deps.fetcher(`${taskBase}/api/canvas-image-tasks/${encodeURIComponent(taskId)}`);
                if(!response.ok) throw new Error(await response.text());
                const task = await response.json();
                if(task.status === 'succeeded') return task.result || {};
                if(task.status === 'jimeng_pending'){
                    throw deps.newJimengPendingSignal({
                        submitId:task.submit_id,
                        kind:task.kind,
                        queueInfo:task.queue_info,
                        message:task.message
                    });
                }
                if(task.status === 'failed' || task.status === 'cancelled') throw new Error(task.error_hint ? `${task.error_hint}（原文：${task.error || ''}）` : (task.error || deps.translate('smart.errRunFailed')));
            }
            throw new Error(deps.translate('smart.errRunTimeout'));
        })();
        deps.activePolls.set(taskId, promise);
        try {
            return await promise;
        } finally {
            deps.activePolls.delete(taskId);
        }
    }

    global.CanvasGenerationTaskPoller = {configure, poll};
})(typeof window !== 'undefined' ? window : globalThis);

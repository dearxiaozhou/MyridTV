//** Submits a ComfyUI workflow job and polls it to completion with token-race guards. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    function D(name){return typeof deps[name] === 'function' ? deps[name]() : deps[name];}

async function submitComfyWorkflowJob(node, payload, meta=null){
    const target = node || null;
    const runToken = target?.comfyRunToken;
    // 重跑前清掉上一轮的失败提示，否则旧错误会一直挂在节点上
    if(target){ delete target.comfyError; delete target.comfyNotice; }
    // 任务控制台定位：提交时带上画布/节点信息（与 RH 提交链的 canvas_id/node_id 同构）
    const consoleMeta = {
        canvas_id:D("canvasId") || '',
        canvas_title:String(D("canvas")?.title || document.getElementById('smartTitle')?.textContent || '').trim(),
        node_id:String(target?.id || ''),
        node_title:String(target?.title || ''),
        origin:'画布节点执行'
    };
    const submitted = await fetch(deps.comfyProxyUrl('/api/comfyui/jobs'), {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({...payload.body, ...consoleMeta})
    }).then(async r => {
        const data = await r.json().catch(async () => ({error:await r.text()}));
        if(!r.ok || data.ok === false) throw new Error(data.error || tr('smart.errRunFailed'));
        return data;
    });
    const jobId = submitted.job_id;
    if(!jobId) throw new Error('ComfyUI 未返回 job_id');
    if(target && target.comfyRunToken !== runToken){
        // Stop/retry may race with the submit response. Cancel this now-orphaned
        // job and prevent its stale promise from claiming the node again.
        for(const action of ['cancel', 'interrupt']){
            try {
                await fetch(deps.comfyProxyUrl(`/api/comfyui/jobs/${encodeURIComponent(jobId)}/${action}`), {
                    method:'POST', headers:{'Content-Type':'application/json'}
                });
            } catch(_) {}
        }
        const superseded = new Error('ComfyUI 任务已被替换');
        superseded.comfyRunSuperseded = true;
        throw superseded;
    }
    if(target){
        target.comfyJobId = jobId;
        target.comfyStatus = submitted.status || 'queued';
        target.comfyProgress = Number(submitted.progress || 0);
        target.comfyCurrentNode = submitted.current_node || '';
        target.comfyCurrentNodeTitle = submitted.current_node_title || '';
        target.comfyPromptId = submitted.prompt_id || '';
        target.comfyQueuePosition = Number(submitted.queue_position ?? -1);
        deps.render();
        deps.syncRunButtonAvailability(target);
        deps.scheduleSave();
        // 2026-09-17：启动独立状态监督，避免单次 runGeneration promise 链被打断后按钮卡死
        deps.startComfyJobSupervisor();
    }
    for(let i = 0; i < 7200; i++){
        await deps.sleep(900);
        const job = await fetch(deps.comfyProxyUrl(`/api/comfyui/jobs/${encodeURIComponent(jobId)}`), {cache:'no-store'}).then(async r => {
            const data = await r.json().catch(async () => ({error:await r.text()}));
            if(!r.ok || data.ok === false){
                if(target && target.comfyRunToken !== runToken){
                    const superseded = new Error('ComfyUI 任务已被替换');
                    superseded.comfyRunSuperseded = true;
                    throw superseded;
                }
                // 任务记录丢失（后端重启过）或接口报错：必须连节点上的 comfy 运行态一起清，
                // 否则节点会永远停在「正在生成…」、运行按钮永远是停止。
                if(target) deps.clearComfyRunStateKeepPromptId(target);
                deps.syncRunButtonAvailability(target);
                deps.render();
                throw new Error(data.error || tr('smart.errRunFailed'));
            }
            return data;
        });
        // 后端兜底：状态被迟到的 WS 消息翻回 running，但 error + finished_at 已经落地 → 按失败收尾
        if(job.status === 'running' && Number(job.finished_at || 0) > 0 && job.error){
            job.status = 'error';
        }
        if(target){
            if(target.comfyRunToken !== runToken){
                const superseded = new Error('ComfyUI 任务已被替换');
                superseded.comfyRunSuperseded = true;
                throw superseded;
            }
            if(target.comfyJobId !== jobId && job.status === 'done' && (target.images || []).length){
                // The supervisor already received and applied this task's output.
                // Let the foreground run finish without appending the same media twice.
                return {...job, comfyAlreadyFinalized:true};
            }
            target.comfyStatus = job.status || target.comfyStatus || '';
            target.comfyProgress = Number(job.progress || 0);
            target.comfyCurrentNode = job.current_node || '';
            target.comfyCurrentNodeTitle = job.current_node_title || '';
            target.comfyPromptId = job.prompt_id || target.comfyPromptId || '';
            target.comfyError = job.error || '';
            target.comfyNotice = job.notice || '';
            updateComfyNodeLiveState(target, job);
            if(i % 3 === 0) scheduleSave();
        }
        if(job.status === 'done'){
            if(target) target.comfyProgress = 100;
            render();
            syncRunButtonAvailability(target);
            return job;
        }
        if(['error','cancelled','gone'].includes(job.status)){
            if(target && job.status !== 'cancelled') clearComfyRunStateKeepPromptId(target);
            syncRunButtonAvailability(target);
            render();
            throw new Error(job.error || (job.status === 'cancelled' ? 'ComfyUI 任务已取消' : 'ComfyUI 任务失败'));
        }
    }
    if(target) clearComfyRunStateKeepPromptId(target);
    syncRunButtonAvailability(target);
    render();
    throw new Error('ComfyUI 任务超时');
}

    global.CanvasComfyJobSubmitter = {
        configure,
        submitComfyWorkflowJob,
    };
})(typeof window !== 'undefined' ? window : this);

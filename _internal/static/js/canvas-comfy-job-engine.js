/* MyridTV ComfyUI 任务引擎（拆模块 ③：工作流注册表 + 任务生命周期 + supervisor + 卡死恢复）
 *
 * 背景：ComfyUI 任务的「状态机」代码（job 轮询兜底、取消、后端重启后按 prompt_id 认领产出、
 * 工作流注册表持久化）散在 smart-canvas.js 各处，而它跟 composer UI 几乎没有耦合 ——
 * 是最适合先收拢的一块。本模块只管任务生命周期，不碰渲染。
 *
 * 模块自持状态：
 *  - comfyWorkflowCache（工作流定义缓存；主文件以 const 别名共享读，零调用点改动）
 *  - comfyJobSupervisorTimer / comfyRecoveryInFlight
 *  - 常量：REGISTRY_KEY / REMOVED / ALIASES / DEFAULT（只被本模块函数使用）
 *
 * 主文件保留：comfyWorkflows 数组与 comfyProxyUrl、currentComfyWorkflowData（composer UI 高频读）。
 */
(function (global) {
    'use strict';

    // ===== 注入点（configure 填充）=====
    var deps = {
        proxyUrl: null,              // (path) => string  RH 代理绝对地址
        getNodes: null,              // () => nodes
        render: null,                // () => void
        scheduleSave: null,          // () => void
        clearNodeRunningState: null, // (node) => void
        syncRunButtonAvailability: null, // (node) => void
        updateComfyNodeLiveState: null,  // (node) => void
        finalizePendingNode: null,   // async (node, urls, meta, kind) => void
        nowMs: null                  // () => number
    };
    function configure(opts) {
        Object.assign(deps, opts || {});
    }

    // ===== 工作流常量与注册表（只被本模块函数使用，自主文件迁入）=====
    const COMFY_WORKFLOW_REGISTRY_KEY = 'studio_comfy_workflows_v1';
    const REMOVED_COMFY_WORKFLOWS = new Set(['2511.json', 'Flux2-Klein.json']);
    const COMFY_WORKFLOW_NAME_ALIASES = Object.freeze({
        'Z image 文生图强化版.json': 'Z-image-enhanced.json',
        'Qwen3.5提示词扩写+图片反推+视频反推.json': 'Qwen35-prompt-vision-video.json'
    });
    const DEFAULT_COMFY_WORKFLOWS = [
        {name:'SeedVR2图片放大流.json', title:'SeedVR2图片放大流', field_count:0, builtin:true},
    ];

    const comfyWorkflowCache = {};

    function resolveComfyWorkflowName(name){
        const normalized = String(name || '').trim();
        return COMFY_WORKFLOW_NAME_ALIASES[normalized] || normalized;
    }
    function normalizeComfyWorkflowEntries(list){
        const seen = new Set();
        const out = [];
        (Array.isArray(list) ? list : []).forEach(item => {
            const name = resolveComfyWorkflowName(item?.name);
            if(!name || REMOVED_COMFY_WORKFLOWS.has(name) || !/\.json$/i.test(name) || /\.config\.json$/i.test(name) || seen.has(name)) return;
            seen.add(name);
            const entry = {
                name,
                title: String(item?.title || name.replace(/\.json$/i, '')).trim() || name.replace(/\.json$/i, ''),
                field_count: Math.max(0, Number(item?.field_count) || 0),
                builtin: item?.builtin === true
            };
            if(item?.group?.id) entry.group = {id: String(item.group.id), title: String(item.group.title || item.group.id)};
            out.push(entry);
        });
        return out;
    }
    function loadLocalComfyWorkflowRegistry(){
        try {
            return normalizeComfyWorkflowEntries(JSON.parse(localStorage.getItem(COMFY_WORKFLOW_REGISTRY_KEY) || '[]'));
        } catch(_) {
            return [];
        }
    }
    function saveLocalComfyWorkflowRegistry(list){
        try {
            localStorage.setItem(COMFY_WORKFLOW_REGISTRY_KEY, JSON.stringify(normalizeComfyWorkflowEntries(list)));
        } catch(_) {}
    }
    function mergeKnownComfyWorkflows(primary=[], fallback=[]){
        return normalizeComfyWorkflowEntries([
            ...(Array.isArray(primary) ? primary : []),
            ...(Array.isArray(fallback) ? fallback : []),
            ...DEFAULT_COMFY_WORKFLOWS
        ]);
    }
    function updateKnownComfyWorkflows(primary=[]){
        const merged = mergeKnownComfyWorkflows(primary, loadLocalComfyWorkflowRegistry());
        saveLocalComfyWorkflowRegistry(merged);
        return merged;
    }
    function replaceKnownComfyWorkflows(primary=[]){
        const normalized = normalizeComfyWorkflowEntries(primary);
        saveLocalComfyWorkflowRegistry(normalized);
        return normalized;
    }
    async function ensureComfyWorkflow(name){
        const resolved = resolveComfyWorkflowName(name);
        if(!resolved) return null;
        if(comfyWorkflowCache[resolved]) return comfyWorkflowCache[resolved];
        const data = await fetch(`/api/workflows/${encodeURIComponent(resolved)}`).then(r => r.ok ? r.json() : null).catch(() => null);
        if(data){
            comfyWorkflowCache[resolved] = data;
            if(name && name !== resolved) comfyWorkflowCache[name] = data;
        }
        return data;
    }
    async function filterAccessibleComfyWorkflows(list=[]){
        const normalized = normalizeComfyWorkflowEntries(list);
        const accessible = [];
        for(const item of normalized){
            const data = await ensureComfyWorkflow(item.name);
            if(!data?.workflow) continue;
            const resolvedName = resolveComfyWorkflowName(data.name || item.name);
            accessible.push({
                ...item,
                name: resolvedName,
                title: String(data?.config?.title || item.title || resolvedName.replace(/\.json$/i, '')).trim() || resolvedName.replace(/\.json$/i, ''),
                field_count: Array.isArray(data?.config?.fields) ? data.config.fields.length : item.field_count,
                builtin: item.builtin === true || data?.builtin === true
            });
        }
        return normalizeComfyWorkflowEntries(accessible);
    }

    // ===== 任务运行态清理 =====
    function clearComfyRunStateKeepPromptId(node){
        if(!node) return;
        delete node.comfyJobId;
        delete node.comfyStatus;
        delete node.comfyProgress;
        delete node.comfyCurrentNode;
        delete node.comfyCurrentNodeTitle;
        delete node.comfyStartedAt; // 计时起点，跨任务不能复用
        delete node.comfyNotice;    // 运行期提示，结束了就该消失
        // 注意：这里故意保留 comfyError —— 失败原因要继续挂在节点上给用户看
    }
    function clearComfyProgress(node){
        if(!node) return;
        delete node.comfyJobId;
        delete node.comfyPromptId;
        delete node.comfyQueuePosition;
        delete node.comfyProgress;
        delete node.comfyCurrentNode;
        delete node.comfyCurrentNodeTitle;
        delete node.comfyStatus;
        delete node.comfyStartedAt;
        delete node.comfyError;   // 成功了就别留着上一轮的失败提示
        delete node.comfyNotice;
    }
    function clearComfyProgressExceptStatus(node){
        if(!node) return;
        delete node.comfyJobId;
        delete node.comfyPromptId;
        delete node.comfyProgress;
        delete node.comfyCurrentNode;
        delete node.comfyCurrentNodeTitle;
        delete node.comfyStartedAt;
        // 保留 comfyStatus = 'cancelled'
    }

    // ===== 取消 =====
    async function cancelComfyJob(node){
        if(!node || !node.comfyJobId) return false;
        const jobId = node.comfyJobId;
        node.comfyStatus = 'cancelled';  // 保留 cancelled 状态供前端显示
        try {
            await fetch(deps.proxyUrl(`/api/comfyui/jobs/${encodeURIComponent(jobId)}/cancel`), {
                method:'POST',
                headers:{'Content-Type':'application/json'}
            }).catch(()=>null);
            await fetch(deps.proxyUrl(`/api/comfyui/jobs/${encodeURIComponent(jobId)}/interrupt`), {
                method:'POST',
                headers:{'Content-Type':'application/json'}
            }).catch(()=>null);
        } catch(e){ /* 后端暂无 cancel 接口也能清前端态 */ }
        clearComfyProgressExceptStatus(node);
        deps.syncRunButtonAvailability(node);
        deps.render();
        // 停止要落盘：不保存的话刷新/切画布又会从磁盘读回「运行中」
        deps.scheduleSave();
        return true;
    }

    // ===== supervisor：promise 链断掉时的轮询兜底 =====
    let comfyJobSupervisorTimer = null;
    async function syncComfyJobStatusOnce(node){
        // queued 也要管：否则任务停在排队阶段、promise 链又断了时，没人把它推进到 running/收尾
        if(!node || !node.comfyJobId || !['running', 'queued'].includes(node.comfyStatus)) return false;
        let job;
        try {
            job = await fetch(deps.proxyUrl(`/api/comfyui/jobs/${encodeURIComponent(node.comfyJobId)}`), {cache:'no-store'}).then(async r => {
                if(!r.ok) throw new Error('http ' + r.status);
                return r.json();
            });
        } catch(e) {
            // 拉取失败先计数，不立刻清 —— 后端瞬时抖动 / 重启间隙不该把「还在跑」的任务误清成已结束，
            // 否则按钮会假回弹、产出也永远补不回来。连续失败 3 次（约 6s）才认定任务记录真丢了。
            node.comfySupervisorMiss = (Number(node.comfySupervisorMiss || 0)) + 1;
            if(node.comfySupervisorMiss < 3) return false;
            // 任务记录已丢失（后端重启 / job 被清）：连运行态一起清，别卡按钮
            delete node.comfySupervisorMiss;
            clearComfyRunStateKeepPromptId(node);
            deps.clearNodeRunningState(node);
            deps.syncRunButtonAvailability(node);
            deps.render(); deps.scheduleSave();
            return true;
        }
        delete node.comfySupervisorMiss;
        const st = job.status || node.comfyStatus;
        // 状态必须写回：promise 链断了只剩 supervisor 在轮询时，不写回的话节点会永远停在
        // 提交那一刻的 queued，「排队中 · 第 N 位」一直挂着，哪怕它其实已经在跑了。
        if(['running', 'queued'].includes(st)) node.comfyStatus = st;
        node.comfyProgress = Number(job.progress || node.comfyProgress || 0);
        // 后端 FIFO 队列位次：-1=已出队/完成/历史恢复，>0=前方还有几个（从 1 起）
        node.comfyQueuePosition = Number(job.queue_position ?? -1);
        // 失败原因 + 运行期提示（等待显存 / 显存不足重试中），要显示到节点上，
        // 否则用户只能看到「转圈然后没了」，不知道是显存炸了还是工作流填错。
        node.comfyError = job.error || '';
        node.comfyNotice = job.notice || '';
        deps.updateComfyNodeLiveState(node, job);
        if(st === 'done'){
            const urls = (job.videos && job.videos.length) ? job.videos : (job.images || []);
            const kind = (job.videos && job.videos.length) ? 'video' : 'image';
            // 仅当节点还没产出时回填（避免和正常轮询的 finalize 重复）
            if(urls.length && !(node.images || []).length){
                try { await deps.finalizePendingNode(node, urls, {prompt:node.promptDraftText || node.runPrompt || '', displayPrompt:node.promptDraftText || node.runPrompt || ''}, kind); }
                catch(_) { /* 产出回填失败也不阻塞清态 */ }
            }
            clearComfyProgress(node);
            deps.clearNodeRunningState(node);
            deps.syncRunButtonAvailability(node);
            deps.render(); deps.scheduleSave();
            return true;
        }
        if(['error','cancelled','gone'].includes(st)){
            if(st !== 'cancelled') clearComfyRunStateKeepPromptId(node);
            else clearComfyProgressExceptStatus(node);
            deps.clearNodeRunningState(node);
            deps.syncRunButtonAvailability(node);
            deps.render(); deps.scheduleSave();
            return true;
        }
        return false;
    }
    function startComfyJobSupervisor(){
        if(comfyJobSupervisorTimer) return;
        comfyJobSupervisorTimer = setInterval(async () => {
            const active = (deps.getNodes() || []).filter(n => n.comfyJobId && ['running', 'queued'].includes(n.comfyStatus));
            if(!active.length){ stopComfyJobSupervisor(); return; }
            for(const n of active){
                try { await syncComfyJobStatusOnce(n); } catch(_) {}
            }
        }, 2000);
    }
    function stopComfyJobSupervisor(){
        if(comfyJobSupervisorTimer){ clearInterval(comfyJobSupervisorTimer); comfyJobSupervisorTimer = null; }
    }

    // ===== 卡死恢复：后端重启/记录丢失后按 prompt_id 认领产出 =====
    let comfyRecoveryInFlight = false;
    function isRecoverableComfyNode(node){
        if(!node || (node.images || []).length) return false;
        const runSettings = node.runSettings || node.settings || {};
        const isComfy = (runSettings.engine || '') === 'comfy' || node.comfyRecovery || node.comfyPromptId || node.comfyJobId;
        if(!isComfy) return false;
        // 还在跑的节点：跑够 20 秒还没产出，才认为可能卡住了。
        if(node.running) {
            const startedAt = Number(node.runStartedAt || node.comfyRecovery?.startedAt || 0);
            return !startedAt || deps.nowMs() - startedAt > 20000;
        }
        // 后端重启过 / 记录丢失被清掉运行态，但留了 prompt_id：按 prompt_id 认领结果。
        return Boolean(node.comfyPromptId);
    }
    async function recoverStuckComfyNodes(){
        if(comfyRecoveryInFlight) return false;
        const stuck = (deps.getNodes() || []).filter(isRecoverableComfyNode);
        if(!stuck.length) return false;
        comfyRecoveryInFlight = true;
        try {
            const data = await fetch(deps.proxyUrl('/api/comfyui/recent-outputs?limit=6'), {cache:'no-store'}).then(async r => {
                if(!r.ok) throw new Error(await r.text());
                return r.json();
            });
            const outputs = Array.isArray(data.outputs) ? data.outputs : [];
            let changed = false;
            for(const node of stuck){
                if((node.images || []).length) continue;
                // 有 prompt_id 就精确认领对应那一条（避免把「最近一条输出」错挂到别的节点上）
                const row = node.comfyPromptId
                    ? outputs.find(item => String(item.prompt_id || '') === String(node.comfyPromptId))
                    : outputs.find(item => (item.images || []).length || (item.videos || []).length);
                if(!row) continue;
                const urls = (row.images || []).length ? row.images : (row.videos || []);
                const kind = (row.images || []).length ? 'image' : 'video';
                await deps.finalizePendingNode(node, urls, {prompt:node.runPrompt || '', displayPrompt:node.runPrompt || ''}, kind);
                node.comfyPromptId = row.prompt_id || '';
                delete node.comfyRecovery;
                changed = true;
            }
            if(changed){
                deps.render();
                deps.scheduleSave();
            }
            return changed;
        } catch(e) {
            console.warn('comfy recovery failed', e);
            return false;
        } finally {
            comfyRecoveryInFlight = false;
        }
    }

    global.CanvasComfyJobEngine = {
        configure: configure,
        cache: comfyWorkflowCache,
        // 注册表
        resolveComfyWorkflowName: resolveComfyWorkflowName,
        normalizeComfyWorkflowEntries: normalizeComfyWorkflowEntries,
        loadLocalComfyWorkflowRegistry: loadLocalComfyWorkflowRegistry,
        saveLocalComfyWorkflowRegistry: saveLocalComfyWorkflowRegistry,
        mergeKnownComfyWorkflows: mergeKnownComfyWorkflows,
        updateKnownComfyWorkflows: updateKnownComfyWorkflows,
        replaceKnownComfyWorkflows: replaceKnownComfyWorkflows,
        ensureComfyWorkflow: ensureComfyWorkflow,
        filterAccessibleComfyWorkflows: filterAccessibleComfyWorkflows,
        // 任务生命周期
        clearComfyRunStateKeepPromptId: clearComfyRunStateKeepPromptId,
        clearComfyProgress: clearComfyProgress,
        clearComfyProgressExceptStatus: clearComfyProgressExceptStatus,
        cancelComfyJob: cancelComfyJob,
        syncComfyJobStatusOnce: syncComfyJobStatusOnce,
        startComfyJobSupervisor: startComfyJobSupervisor,
        stopComfyJobSupervisor: stopComfyJobSupervisor,
        isRecoverableComfyNode: isRecoverableComfyNode,
        recoverStuckComfyNodes: recoverStuckComfyNodes
    };
})(typeof window !== 'undefined' ? window : globalThis);

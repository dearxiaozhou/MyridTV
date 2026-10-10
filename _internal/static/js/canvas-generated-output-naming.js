//** Names, reserves, localizes generated outputs and drives run-timer/progress-ring state. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    function D(name){return typeof deps[name] === 'function' ? deps[name]() : deps[name];}

    let runTimerInterval = null;

function queueRemoteGeneratedMediaLocalization(){
    (D("nodes") || []).forEach(node => {
        if((node?.images || []).some(D("generatedImageNeedsLocalization"))){
            deps.localizeRemoteGeneratedNodeImages(node);
        }
    });
}
function cleanGeneratedOutputBaseName(name){
    const raw = String(name || '').trim();
    if(!raw) return '';
    const generic = new Set(['Image','Images','Group','Output','Video','Videos','Audio','Audios','Text','Texts','File','Files', tr('smart.createImportNode')]);
    if(generic.has(raw)) return '';
    return raw.replace(/[\\/:*?"<>|]/g, '_').replace(/\s+/g, '_').slice(0, 60).replace(/^_+|_+$/g, '');
}
async function reserveGeneratedBaseNames(baseName, count=1, ext='png', kind='image'){
    const names = [];
    const cleanExt = String(ext || 'png').replace(/^\./, '') || 'png';
    const cleanBase = cleanGeneratedOutputBaseName(baseName);
    if(!cleanBase) return names;
    let index = 1;
    while(names.length < count && index < 10000){
        const suffix = count === 1 ? '' : `_${index}`;
        const name = `${cleanBase}${suffix}.${cleanExt}`;
        const key = name.toLowerCase();
        if(!D("generatedOutputNameReservations").has(key) && !(await deps.generatedOutputNameExists(name, kind))){
            D("generatedOutputNameReservations").add(key);
            names.push(name);
        }
        index += 1;
    }
    while(names.length < count){
        const name = `${cleanBase}_${Date.now()}_${names.length + 1}.${cleanExt}`;
        D("generatedOutputNameReservations").add(name.toLowerCase());
        names.push(name);
    }
    return names;
}
function uniqueGeneratedMediaItems(items){
    return global.CanvasGenerationResultModel.uniqueMediaItems(items);
}
async function smartGeneratedOutputItems(items, kind='image', options={}){
    const ext = deps.generatedOutputExt(kind);
    const date = new Date();
    const rawItems = uniqueGeneratedMediaItems(items);
    const names = await deps.reserveGeneratedDateNames(rawItems.length, ext, date, kind);
    const preparedItems = rawItems.map((item, index) => {
        const source = item && typeof item === 'object' ? {...item} : {url:item};
        const fallbackName = names[index] || deps.generatedDateSequenceName(index, ext, date);
        // 2026-10-09 老王拍板：画布素材名必须与磁盘文件名一致 —— url 已是本地落盘文件的，
        // 其名字（含日期流水名）就是磁盘真名，原样保留，不再用前端预约名覆盖；
        // 仅远程 url（尚未落盘）才走"非日期名保留/日期名重新预约"的老逻辑。
        const existingName = String(source.name || source.display_name || '').trim()
            || decodeURIComponent(String(typeof item === 'string' ? item : (item?.url || '')).split(/[?#]/)[0].split('/').pop() || '').trim();
        const isDateSeq = /^\d{2,4}-\d{2}-\d{2}([-_]\d+)?\.\w+$|^\d{8}-\d{6}[-_]\d{2}\.\w+$/i.test(existingName);
        const isLocalUrl = !/^https?:\/\//i.test(String(typeof item === 'string' ? item : (source.url || '')).split(/[?#]/)[0]);
        const name = (isLocalUrl && existingName) ? existingName
            : (existingName && !isDateSeq ? existingName : fallbackName);
        source.name = name;
        source.display_name = name;
        return source;
    });
    const hasRemoteSource = preparedItems.some(item => /^https?:\/\//i.test(String(item?.url || '')));
    const deferLocalization = options.deferLocalization !== false && hasRemoteSource;
    const sources = deferLocalization
        ? preparedItems.map(item => ({
            ...item,
            kind:item.kind || item.mediaKind || kind,
            source_url:item.source_url || item.sourceUrl || item.url,
            remoteFallback:true,
            remote_fallback:true,
            localizePending:true
        }))
        : await deps.localizeGeneratedOutputItems(preparedItems, kind);
    const named = sources.map((entry, index) => {
        // 2026-10-09 老王拍板：后端 localize 返回的 name 就是磁盘文件真名，一律直接采用
        // （含日期流水名）；前端预约名只在后端没给出名字时兜底（远程兜底未落盘的场景）。
        const entryName = String(entry.name || entry.display_name || '').trim();
        const name = entryName || names[index] || deps.generatedDateSequenceName(index, ext, date);
        return {
            ...entry,
            url:entry.url,
            name,
            kind:entry.kind || entry.mediaKind || kind,
            generatedResult:true
        };
    });
    return named.map(item => deps.stripImageGenerationMeta(item));
}
// 2026-10-10 老王定标题口径：只取提示词**前 6 个字以内**；这 6 字窗口里一旦遇到断句标点，
// 就断在该标点之前（标点越靠前标题越短）。此前硬切 16 字会切出读不通的半句话，
// 标题里还缝过日期尾巴，两头不靠。
function PROMPT_BREAK_CHAR(ch){
    return /[：:，,。;；、！!？?~～｜|·—…]/.test(ch);
}
// 2026-10-10 补充（老王拍板）：真实语料里提示词开头常是套话前缀，直接取前 6 字会拿到
// 一堆「角色描述」「[BASE」这种同名废话。先剥这类前缀，再走下面的 6 字取词。
const PROMPT_LEAD_NOISE = [
    /^\s*[\[(（][^\])）]{0,24}[\])）]\s*/,                                   // [BASE] / (风格)
    /^\s*[^\s：:\n]{1,8}(描述|设定|说明|内容|需求|要求|标签|参考|规格|提示词)[：:]\s*/,  // 角色描述：/ 场景设定：
    /^\s*(超写实次世代3D渲染|超写实|超高清8K杰作|高清8K|电影级写实CG|电影级写实|超高品质|最佳画质|高质量|杰作|masterpiece|ultra detailed|best quality|8k|4k)[,，、：:\s]+/i
];
function stripPromptLeadNoise(line){
    for(let round = 0; round < 3; round++){
        let hit = false;
        for(const re of PROMPT_LEAD_NOISE){
            const next = line.replace(re, '');
            if(next === line) continue;
            // 剥成独字宁可不剥；但允许剥空（上层会顺延到下一行，如 [BASE]\n<正文>）
            if(next.trim().length === 1) continue;
            line = next; hit = true;
        }
        if(!hit) break;
    }
    return line.trim();
}
function promptTitleStem(prompt, maxLen=6){
    // 逐行剥离前缀后取第一个还有内容的行（[BASE]\n<正文> 这种首行会被剥空，要落到第二行）
    let cleaned = '';
    const lines = String(prompt || '').split(/\r?\n/).map(s => s.trim()).filter(Boolean);
    for(const raw of lines){
        const candidate = stripPromptLeadNoise(raw.replace(/[\\/:*?"<>|]+/g, ' ')).trim();
        if(candidate.length >= 2){ cleaned = candidate; break; }
        if(!cleaned) cleaned = candidate;
    }
    if(!cleaned) return '';
    // 断句优先：在 maxLen 窗口内命中第一个标点就取其之前的内容（读得通），
    // 标点更靠前时天然更短；一个标点都没有才取满 maxLen 字。
    let out = null;
    for(let i = 0; i < Math.min(maxLen, cleaned.length); i++){
        if(PROMPT_BREAK_CHAR(cleaned[i])){ out = cleaned.slice(0, i); break; }
    }
    if(out === null) out = cleaned.slice(0, maxLen);
    out = out.replace(/[\s，。；：、！？""''（）()\[\]【】,;:!?~\-]+$/g, '').trim();
    return out ? out.slice(0, maxLen).trim() : '';
}
function mediaNameStem(name, maxLen=30){
    const stem = String(name || '').replace(/\.[^.]+$/, '').replace(/[\\/:*?"<>|]+/g, ' ').trim();
    return stem ? stem.slice(0, maxLen).trim() : '';
}
// 生成成功后的节点自动命名：提示词前 6 字（归档档案号 MM-DD-NN 只活在 img.name/磁盘文件名里，
// 不再拼进标题——2026-10-10 老王：标题要短、要给人看）。
// 两类节点永不覆盖：①用户手动改过名（titleManual）；②Agent 创建/管理的节点
// （id 前缀 agent_ 或 __origin 以 agent_ 开头）——Agent 卡的标题带验收状态等语义，
// 重跑后被提示词截短名顶掉会破坏 Agent 的管理流（2026-10-09 老王要求跳过）。
// 提示词为空时退回调用方给的 fallback。
function isAgentManagedNode(node){
    return String(node && node.id || '').startsWith('agent_') || String(node && node.__origin || '').startsWith('agent_');
}
// promptOverride：调用方在回填时点手里就有真实提示词（node.runPrompt 要到回填之后才写入），
// 优先用它，避免读到上一轮的旧提示词。
function autoNodeTitleFromNode(node, fallback, promptOverride){
    if(!node) return fallback;
    if(node.titleManual) return node.title || fallback;
    if(isAgentManagedNode(node)) return node.title || fallback;
    const stem = promptTitleStem(promptOverride || node.runPrompt || node.promptDraftText || (node.runSettings && node.runSettings.prompt) || '');
    if(!stem) return fallback;
    // 不拼日期尾巴：同提示词重跑时标题稳定不变，档案号去 img.name 查即可
    return stem;
}
function formatRunDuration(ms){
    const total = Math.max(0, Math.floor(Number(ms || 0) / 1000));
    const min = Math.floor(total / 60);
    const sec = total % 60;
    return min ? `${min}:${String(sec).padStart(2, '0')}` : `${sec}s`;
}
function nodeRunElapsedMs(node){
    if(!node) return 0;
    if(node.runFinishedAt && node.runStartedAt) return Number(node.runElapsedMs) || (Number(node.runFinishedAt) - Number(node.runStartedAt));
    if(node.runStartedAt) return deps.nowMs() - Number(node.runStartedAt);
    return 0;
}
function runTimePillHtml(node){
    if(!node || node.runTimerHidden || node.type === 'smart-prompt') return '';
    // 2026-09-23：comfyStatus==='running' 也要算运行中 —— 级联槽位等路径创建的节点没有
    // pending/running 标志，只带 comfyStatus，漏掉它会导致「正在跑的节点计时 pill 消失」。
    const running = Boolean(node.pending || node.running || node.jimengPending || node.comfyStatus === 'running');
    // queued（哪怕没有 pending 标志，如级联槽位）也要显示「排队中」pill，不能直接不渲染
    if(!running && !node.runFinishedAt && node.comfyStatus !== 'queued') return '';
    // 2026-09-23：ComfyUI 排队中不走计时 —— 那段时间 ComfyUI 还没开工，跑秒没有意义，
    // 也会让人误以为「等了这么久还没出图是生成慢」。排队位次由节点底部徽标显示。
    if(node.comfyStatus === 'queued'){
        return `<span class="run-time-pill queued" data-run-timer="${deps.escapeHtml(node.id)}">排队中</span>`;
    }
    const cls = running ? '' : ' done';
    return `<span class="run-time-pill${cls}" data-run-timer="${deps.escapeHtml(node.id)}">${formatRunDuration(nodeRunElapsedMs(node))}</span>`;
}
// comfy 轮询期间的轻量 DOM 更新：只动进度条/状态类/计时pill/运行按钮，避免全量 deps.render() 重建节点
// 导致选中/hover 每 900ms 丢失（「选中一下又没了」bug）。
function updateComfyNodeLiveState(node, job){
    if(!node) return;
    // 2026-09-23：计时起点以后端「真正开工」为准（job.started_at），排队等待不计入耗时。
    // 以前 runStartedAt 在提交那一刻就定了，排了 2 分钟队再跑，秒表一上来就是 2:00。
    if(job){
        const startedAt = Math.round(Number(job.started_at || 0) * 1000);
        if(startedAt > 0 && Number(node.comfyStartedAt || 0) !== startedAt){
            node.comfyStartedAt = startedAt;
            node.runStartedAt = startedAt;   // 通用计时（含完成后的 finished-started）一并校正
        }
    }
    // 刚从排队转入运行、但后端 started_at 还没随本次轮询返回的空窗（最多一次轮询间隔）：
    // 先按本地时间起算，别拿提交时刻当起点闪一下大数字，等后端值到了再校正。
    if(node.comfyStatus === 'running' && !node.comfyStartedAt){
        node.comfyStartedAt = deps.nowMs();
        node.runStartedAt = node.comfyStartedAt;
    }
    const el = D("world").querySelector(`.image-node[data-id="${CSS.escape(node.id)}"]`);
    // 节点不在 DOM 时分两种情况，千万别一律 deps.render() —— 2026-10-06 多任务卡顿真因：
    // 画布有视口裁剪（visibleNodeList），画面外的节点压根不在 DOM 里；提交一批任务后只要
    // 有 N 个任务跑到了视野之外，这条兜底就会让「每个任务每轮轮询」各触发一次整画布 render()
    // （旧实测单次 35ms、我们的画布节点更多时更贵）， polling 越密越卡，直接雪崩。
    // ① 被裁掉（不在可见名单里）→ 不用更新它的 DOM，回到视野时 cull 会按最新模型重绘；
    // ② 不该被裁却不在 DOM（刚提交出来的新节点）→ 才真的需要全量渲染。
    if(!el){
        const visible = typeof deps.visibleNodeList === 'function' ? deps.visibleNodeList() : null;
        const culled = Array.isArray(visible) && visible.length
            ? !visible.some(n => n && n.id === node.id)
            : false;   // 拿不到可见名单时保守起见照旧渲染
        if(!culled) deps.render();
        return;
    }
    // 排队 ≠ 运行：queued 只给「排队中 · 第 N 位」徽标 + 静态描边，不显示进度、不跑流光。
    // （以前把 queued 也算进 running，排在队尾的节点会亮蓝框 + 进度环空转，看着像在生成。）
    const isQueued = node.comfyStatus === 'queued';
    const running = node.comfyStatus === 'running';
    el.classList.toggle('comfy-running', running);
    el.classList.toggle('comfy-queued', isQueued);
    el.setAttribute('data-comfy-status', node.comfyStatus || '');
    // 排队位次：只在「还在队列里等待」时挂属性，由 CSS ::after 渲染成「排队中 · 第 N 位」。
    // 位次从 1 起（1 = 下一个就跑）；正在执行的任务已被 worker 出队，位次为 -1，不显示。
    const queuePos = Number(node.comfyQueuePosition ?? -1);
    if(isQueued && queuePos > 0){
        el.setAttribute('data-comfy-queue', String(queuePos));
    } else {
        el.removeAttribute('data-comfy-queue');
    }
    // 进度环：running 时确保存在并按当前进度沿边框绘制；否则移除
    let bar = el.querySelector(':scope > .comfy-node-progress');
    if(running){
        if(!bar){
            el.insertAdjacentHTML('beforeend', comfyNodeProgressBarHtml(node, {width: el.clientWidth, height: el.clientHeight}));
            bar = el.querySelector(':scope > .comfy-node-progress');
        }
        syncNodeProgressRing(bar, el, node);
        // 兼容旧版底部直条（若 DOM 里还有）：宽度一并同步，避免两种形态不同步
        const fill = bar && bar.querySelector('.comfy-node-progress-fill');
        if(fill) fill.style.width = Math.max(0, Math.min(100, Number(node.comfyProgress || 0))) + '%';
    } else if(bar){
        bar.remove();
    }
    // 运行期提示 / 失败原因：挂一条顶部横幅（底部已被「排队中 · 第 N 位」徽标占了）。
    // 以前失败只体现在「转圈停了」，用户不知道是显存炸了还是工作流填错。
    const noteText = node.comfyError ? ('失败：' + node.comfyError) : (node.comfyNotice || '');
    el.classList.toggle('comfy-failed', Boolean(node.comfyError));
    let note = el.querySelector(':scope > .comfy-node-note');
    if(noteText){
        if(!note){
            el.insertAdjacentHTML('beforeend', '<div class="comfy-node-note"></div>');
            note = el.querySelector(':scope > .comfy-node-note');
        }
        note.textContent = noteText;
        note.classList.toggle('error', Boolean(node.comfyError));
        // 这条横幅在轮询期间是轻量插入的（不经过全量 render），action-controller 里的
        // 点击清除绑定覆盖不到 → 在这里补绑，否则失败横幅点了没反应、消不掉。
        if(!note.dataset.errClearBound){
            note.dataset.errClearBound = '1';
            note.addEventListener('click', ev => {
                ev.preventDefault();
                ev.stopPropagation();
                delete node.comfyError;
                note.remove();
                el.classList.remove('comfy-failed');
                deps.render();
                deps.scheduleSave();
            });
        }
    } else if(note){
        note.remove();
    }
    refreshRunTimerPills();
    deps.syncRunButtonAvailability(node);
}
// 2026-09-17：节点进度改为「沿节点边框一圈」的进度环，整圈 = 100%。
// 起点 = 下边中点，方向 = 逆时针（底中 → 右下 → 右 → 上 → 左 → 回到底中）。
function nodeProgressRingPath(w, h, radius=10){
    const inset = 2; // 3px 描边整体内缩，保证整条线都落在节点内、不被 overflow 裁掉
    const x0 = inset, y0 = inset;
    const x1 = Math.max(x0 + 1, (Number(w) || 260) - inset);
    const y1 = Math.max(y0 + 1, (Number(h) || 178) - inset);
    const r = Math.max(0, Math.min(Number(radius) || 10, Math.min(x1 - x0, y1 - y0) / 2));
    const cx = (x0 + x1) / 2;
    return `M ${cx} ${y1} L ${x1 - r} ${y1} Q ${x1} ${y1} ${x1} ${y1 - r} L ${x1} ${y0 + r} Q ${x1} ${y0} ${x1 - r} ${y0} L ${x0 + r} ${y0} Q ${x0} ${y0} ${x0} ${y0 + r} L ${x0} ${y1 - r} Q ${x0} ${y1} ${x0 + r} ${y1} L ${cx} ${y1} Z`;
}
// 把进度刷到环上：pathLength=100，dashoffset = 100 - 百分比。
// 传 node 时可识别 indeterminate（云端 RH-api 等无精确进度）：整圈流光一直跑，不锁定百分比。
function syncNodeProgressRing(bar, host, node){
    if(!bar) return;
    const data = node && typeof node === 'object' ? node : null;
    const indeterminate = Boolean(data && data.comfyIndeterminate);
    const progress = data ? (data.comfyProgress) : (typeof node === 'number' ? node : 0);
    const box = host || bar.parentElement;
    const w = box ? (box.clientWidth || Number.parseFloat(box.style.width) || 0) : 0;
    const h = box ? (box.clientHeight || Number.parseFloat(box.style.height) || 0) : 0;
    const d = nodeProgressRingPath(w || 260, h || 178, 10);
    // 多任务性能护栏（2026-10-06）：这个函数每轮轮询对每个运行中节点都跑一次，而 setAttribute('d')
    // 会让整段路径几何失效、getTotalLength()/getPointAtLength() 又会强制同步布局 —— 轮询越密、
    // 任务越多，这些"没变化也照写一遍"的开销越叠加。这里先比对上次写进去的值，没变就整段跳过。
    if(bar.dataset.ringD !== d){
        bar.dataset.ringD = d;
        bar.querySelectorAll('path').forEach(p => p.setAttribute('d', d));
        bar.dataset.ringLen = '';   // 形状变了，缓存的长度作废
    }
    const pct = Math.max(0, Math.min(100, Number(progress) || 0));
    const arc = bar.querySelector('.comfy-node-progress-path');
    if(arc) arc.setAttribute('stroke-dashoffset', String(indeterminate ? 0 : (100 - pct)));
    // 点状流光：determinate 时由 mask 裁到 [0, pct]（只有已跑过的那段有光点）；
    // indeterminate 时 mask 整圈放开，光点沿整圈逆时针流动表示「运行中」。
    const maskPath = bar.querySelector('.comfy-node-progress-mask');
    if(maskPath){
        maskPath.setAttribute('d', d);
        maskPath.setAttribute('stroke-dashoffset', String(indeterminate ? 0 : (100 - Math.max(pct, 2.5))));
    }
    // 头部亮点：determinate 时跟着当前进度停在进度弧末端（0% / 100% 时不显示）；indeterminate 不显示
    const dot = bar.querySelector('.comfy-node-progress-dot');
    if(dot && arc){
        const show = !indeterminate && pct > 0.5 && pct < 99.5;
        dot.classList.toggle('is-on', show);
        dot.style.opacity = show ? '' : '0';
        // 亮点位置只在进度真的动了才重算（getPointAtLength 强制布局）：同值直接复用旧坐标
        const posKey = bar.dataset.ringLen ? `${bar.dataset.ringLen}|${pct.toFixed(1)}` : '';
        if(show && bar.dataset.ringPos !== posKey && typeof arc.getTotalLength === 'function'){
            let len = Number(bar.dataset.ringLen || 0);
            if(!len){ len = arc.getTotalLength(); bar.dataset.ringLen = String(len); }
            if(len){
                const pt = arc.getPointAtLength(len * pct / 100);
                dot.setAttribute('cx', pt.x.toFixed(2));
                dot.setAttribute('cy', pt.y.toFixed(2));
                bar.dataset.ringPos = `${len}|${pct.toFixed(1)}`;
            }
        }
    }
}
// 节点进度环：comfyStatus 为 running/queued 时显示当前节点进度。
// indeterminate（云端 RH-api 等无精确进度的运行）：整圈流光一直跑，不锁定百分比。
function comfyNodeProgressBarHtml(node, size){
    if(!node || !['running', 'queued'].includes(node.comfyStatus)) return '';
    const indeterminate = Boolean(node.comfyIndeterminate);
    const progress = Math.max(0, Math.min(100, Number(node.comfyProgress || 0)));
    const box = size || deps.nodeRect(node) || {};
    const d = nodeProgressRingPath(box.width, box.height, 10);
    const maskId = 'cnring-' + deps.uid('ring'); // 随机 id：多个节点的 mask 不打架
    const arcOffset = indeterminate ? 0 : (100 - progress);
    const maskOffset = indeterminate ? 0 : (100 - Math.max(progress, 2.5));
    return `<div class="comfy-node-progress" data-progress="${progress}">
        <svg class="comfy-node-progress-ring" xmlns="http://www.w3.org/2000/svg" focusable="false" aria-hidden="true">
            <defs><mask id="${maskId}" maskUnits="userSpaceOnUse">
                <path class="comfy-node-progress-mask" d="${d}" pathLength="100" stroke-dasharray="100 100" stroke-dashoffset="${maskOffset}" />
            </mask></defs>
            <path class="comfy-node-progress-track-path" d="${d}" pathLength="100" />
            <path class="comfy-node-progress-path" d="${d}" pathLength="100" stroke-dasharray="100 100" stroke-dashoffset="${arcOffset}" />
            <path class="comfy-node-progress-flow" d="${d}" pathLength="100" mask="url(#${maskId})" />
            <circle class="comfy-node-progress-dot" r="3.4" cx="0" cy="0" />
        </svg>
    </div>`;
}
// 全量 render 后统一校准一次尺寸（节点缩放/布局变化时环跟着重画）
function syncAllNodeProgressRings(){
    D("world")?.querySelectorAll?.('.comfy-node-progress').forEach(bar => {
        const host = bar.parentElement;
        const hostNode = host ? host.closest('.image-node') : null;
        const data = hostNode ? D("nodes").find(n => n.id === hostNode.dataset.id) : null;
        syncNodeProgressRing(bar, host, data);
    });
}
function hideRunTimerForNode(node){
    if(!node || node.runTimerHidden || node.pending || node.running || node.jimengPending || !node.runFinishedAt) return false;
    node.runTimerHidden = true;
    deps.scheduleSave();
    return true;
}
function refreshRunTimerPills(){
    // active 判定与 runTimePillHtml 同口径：comfyStatus queued/running 的节点（无 pending 标志的级联槽位）也要让秒表继续走
    const active = D("nodes").some(n => n.type !== 'smart-prompt' && !n.runTimerHidden && (n.pending || n.running || n.jimengPending || n.runFinishedAt || n.comfyStatus === 'queued' || n.comfyStatus === 'running'));
    document.querySelectorAll('[data-run-timer]').forEach(el => {
        const node = D("nodes").find(n => n.id === el.dataset.runTimer);
        if(!node || node.runTimerHidden || node.type === 'smart-prompt') {
            el.remove();
            return;
        }
        // 排队中不计时：显示「排队中」占位，等后端真正开工（job.started_at）后自动切回秒数
        if(node.comfyStatus === 'queued'){
            el.textContent = '排队中';
            el.classList.add('queued');
            el.classList.remove('done');
            return;
        }
        el.classList.remove('queued');
        el.textContent = formatRunDuration(nodeRunElapsedMs(node));
        el.classList.toggle('done', Boolean(!node.pending && !node.running && !node.jimengPending && node.runFinishedAt));
    });
    if(active && !runTimerInterval) runTimerInterval = setInterval(refreshRunTimerPills, 1000);
    if(!active && runTimerInterval){ clearInterval(runTimerInterval); runTimerInterval = null; }
}

    global.CanvasGeneratedOutputNaming = {
        configure,
        queueRemoteGeneratedMediaLocalization,
        cleanGeneratedOutputBaseName,
        reserveGeneratedBaseNames,
        uniqueGeneratedMediaItems,
        smartGeneratedOutputItems,
        promptTitleStem,
        mediaNameStem,
        autoNodeTitleFromNode,
        formatRunDuration,
        nodeRunElapsedMs,
        runTimePillHtml,
        updateComfyNodeLiveState,
        nodeProgressRingPath,
        syncNodeProgressRing,
        comfyNodeProgressBarHtml,
        syncAllNodeProgressRings,
        hideRunTimerForNode,
        refreshRunTimerPills,
    };
})(typeof window !== 'undefined' ? window : this);

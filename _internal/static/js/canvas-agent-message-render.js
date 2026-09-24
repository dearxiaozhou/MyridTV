/* MyridTV 画布 Agent 消息渲染层（拆模块 ④-4：气泡 / 引用条 / 交互卡 / 头脑风暴卡 / 工具轨迹）
 *
 * 18 个「输入 → HTML 字符串」纯生成函数 + 快速动作/结果规范化判定：无 DOM 写入、
 * 无事件绑定（renderCanvasAgentMessages 的 innerHTML 与 onclick 编排仍在主文件），
 * 消息克隆/序列化在 canvas-agent-history-store（Store 直连），
 * 会话/引用/节点等状态所有权在主文件，经 deps getter 只读。
 */
(function (global) {
    'use strict';

    var Store = global.CanvasAgentHistoryStore;

    var deps = {
        mediaKindForItem: null,
        canvasAgentMentionCandidates: null,
        canvasAgentParseBrainstormReply: null,
        escapeHtml: null,
        getMentionPool: null,
        getRefs: null,
        getNodes: null,
        getChosenMap: null
    };
    function configure(opts) {
        Object.assign(deps, opts || {});
    }

function canvasAgentMediaLabel(item, index=0){
    const kind = deps.mediaKindForItem(item);
    const fallback = kind === 'video' ? '视频' : kind === 'audio' ? '音频' : kind === 'text' ? '文本' : kind === 'file' ? '文件' : '图片';
    return item?.name || `${fallback}${index + 1}`;
}
function canvasAgentRefFromImage(img, node=null, index=0){
    if(!img?.url) return null;
    return {
        ...img,
        id:`${node?.id || img.nodeId || 'ref'}:${Number.isFinite(Number(img.imageIndex)) ? Number(img.imageIndex) : index}:${img.url}`,
        nodeId:node?.id || img.nodeId || '',
        imageIndex:Number.isFinite(Number(img.imageIndex)) ? Number(img.imageIndex) : index,
        name:canvasAgentMediaLabel(img, index),
        kind:deps.mediaKindForItem(img)
    };
}
function canvasAgentSuggestionsFromText(text=''){
    const all = [];
    const re = /(?:^|\n)\s*([A-H])[.、．]\s*([^\n]{2,90})/g;
    let m;
    while((m = re.exec(String(text || '')))) all.push({key:m[1].toUpperCase(), text:m[2].trim()});
    if(!all.length || all[0].key !== 'A') return [];
    const seq = [all[0]];
    for(let i = 1; i < all.length; i++){
        const prev = seq[seq.length - 1].key;
        if(all[i].key === String.fromCharCode(prev.charCodeAt(0) + 1)) seq.push(all[i]);
        else break;
    }
    return seq.length >= 2 ? seq.slice(0, 8) : [];
}
function canvasAgentFormatLatency(ms){
    ms = Number(ms) || 0;
    if(ms < 1000) return `${Math.round(ms)}ms`;
    const s = ms / 1000;
    return s >= 60 ? `${(s / 60).toFixed(1)}min` : `${s.toFixed(1)}s`;
}
function canvasAgentToolLabel(name=''){
    const labels = {
        canvas_get_state:'读取画布',
        canvas_search_nodes:'搜索节点',
        canvas_create_text_node:'创建文本节点',
        canvas_create_generation_node:'创建生成节点',
        canvas_generate_images:'提交生成',
        canvas_check_generation:'查询生成状态',
        canvas_update_node:'更新节点',
        canvas_batch_operations:'批量画布操作',
        canvas_undo_batch:'撤销批量操作',
        canvas_add_link:'创建连线',
        canvas_delete_node:'删除节点',
        canvas_list_skills:'读取技能库',
        canvas_save_skill:'保存技能'
    };
    return labels[name] || name || '执行动作';
}
function canvasAgentTraceFromToolLog(toolLog=[]){
    const items = [];
    const nodeIds = [];
    const createdTitles = [];
    (Array.isArray(toolLog) ? toolLog : []).forEach((entry, index) => {
        const name = String(entry?.name || '').trim();
        const args = entry?.args || {};
        const result = entry?.result || {};
        const ok = result?.ok !== false;
        const nodeId = String(result?.node_id || result?.nodeId || args?.node_id || '').trim();
        // 批量操作 canvas_batch_operations：节点 ID 嵌在 results[].node_id，顶层没有 node_id
        if(!nodeId && Array.isArray(result?.results)){
            for(const sub of result.results){
                if(!sub || typeof sub !== 'object') continue;
                const subId = String(sub?.node_id || sub?.nodeId || '').trim();
                if(subId && !nodeIds.includes(subId)) nodeIds.push(subId);
                const subTitle = String(sub?.title || '').trim();
                if(subTitle && !createdTitles.includes(subTitle)) createdTitles.push(subTitle);
            }
        }
        const title = String(args?.title || '').trim();
        const detailParts = [];
        if(title) detailParts.push(title);
        if(result?.task_id) detailParts.push(`任务 ${String(result.task_id).slice(0, 10)}`);
        if(result?.status === 'running') detailParts.push('进行中');
        if(result?.status === 'succeeded') detailParts.push('已完成');
        if(result?.error) detailParts.push(String(result.error).slice(0, 80));
        if(result?.message && !result?.error) detailParts.push(String(result.message).slice(0, 80));
        items.push({
            id:`trace_${index}_${name}`,
            name,
            label:canvasAgentToolLabel(name),
            ok,
            nodeId,
            batchId:String(result?.batch_id || '').trim(),
            detail:detailParts.filter(Boolean).join(' · ')
        });
        if(nodeId && !nodeIds.includes(nodeId)) nodeIds.push(nodeId);
        if(title && !createdTitles.includes(title)) createdTitles.push(title);
    });
    return {
        items,
        nodeIds,
        createdTitles
    };
}
function normalizeCanvasAgentResult(result={}, reply=''){
    const agentResult = result?.agent_result && typeof result.agent_result === 'object' ? result.agent_result : {};
    const resolvedText = String(agentResult.text || result.text || result.message || result.content || reply || '').trim();
    const toolLog = Array.isArray(agentResult.tool_log) ? agentResult.tool_log : (Array.isArray(result.tool_log) ? result.tool_log : []);
    const toolTrace = canvasAgentTraceFromToolLog(toolLog);
    const createdNodes = Array.isArray(agentResult.created_nodes) ? agentResult.created_nodes : (Array.isArray(result.created_nodes) ? result.created_nodes : []);
    const nodeIds = createdNodes.map(item => String(item?.node_id || '')).filter(Boolean);
    const quickActions = Array.isArray(agentResult.quick_actions) ? agentResult.quick_actions : (Array.isArray(result.quick_actions) ? result.quick_actions : []);
    const rawSuggestions = Array.isArray(agentResult.suggestions) ? agentResult.suggestions : (Array.isArray(result.suggestions) ? result.suggestions : []);
    const suggestions = rawSuggestions.map(item => ({
        key:String(item?.key || '').trim().toUpperCase(),
        text:String(item?.label || item?.text || '').trim(),
        action:String(item?.action || '').trim(),
        nodeId:String(item?.node_id || item?.nodeId || '').trim(),
    })).filter(item => item.key && item.text);
    const interaction = (agentResult.interaction && typeof agentResult.interaction === 'object')
        ? agentResult.interaction
        : ((result.interaction && typeof result.interaction === 'object') ? result.interaction : null);
    return {
        text: resolvedText,
        toolLog,
        toolTrace,
        nodeIds: nodeIds.length ? nodeIds : (toolTrace.nodeIds || []),
        suggestions,
        quickActions,
        outputMode: String(agentResult.output_mode || result.output_mode || '').trim(),
        interaction,
        loadedSkills: Array.isArray(agentResult.loaded_skills) ? agentResult.loaded_skills.filter(n => String(n || '').trim()) : (Array.isArray(result.loaded_skills) ? result.loaded_skills.filter(n => String(n || '').trim()) : (Array.isArray(agentResult.loadedSkills) ? agentResult.loadedSkills.filter(n => String(n || '').trim()) : [])),
        task: (agentResult.task && typeof agentResult.task === 'object') ? agentResult.task : ((result.task && typeof result.task === 'object') ? result.task : null),
        step: (agentResult.step && typeof agentResult.step === 'object') ? agentResult.step : ((result.step && typeof result.step === 'object') ? result.step : null),
        progress: (agentResult.progress && typeof agentResult.progress === 'object') ? agentResult.progress : ((result.progress && typeof result.progress === 'object') ? result.progress : null),
    };
}
function isCanvasAgentStoppedEmptyReply(result={}, text=''){
    if(!result?.stopped) return false;
    const value = String(text || '').trim();
    return !value || /^已停止生成(?:（可继续输入新消息）)?$/.test(value);
}
function canvasAgentQuickActionsForMessage(message){
    if(Array.isArray(message?.quickActions) && message.quickActions.length){
        return message.quickActions;
    }
    const actions = [];
    // 撤销本次批量操作：消息工具轨迹里有成功的 batch 且带 batch_id
    const batchEntry = (Array.isArray(message?.toolTrace?.items) ? message.toolTrace.items : [])
        .map(e => e || {})
        .filter(r => r?.ok !== false && r?.batchId)
        .pop();
    if(batchEntry?.batchId && !message?.undone){
        actions.push({id:'undo', label:'撤销本次操作', icon:'undo-2', batchId:batchEntry.batchId});
    }
    if(Array.isArray(message?.nodeIds) && message.nodeIds.length){
        actions.push({id:'locate', label:'定位节点', icon:'locate-fixed'});
        const pending = message.nodeIds.some(id => {
            const node = (deps.getNodes() || []).find(n => n.id === id);
            // 判据=没有「生成结果图」；Agent 建的节点带输入参考图也算待生成
            return node && node.type === 'smart-image' && !(node.images || []).some(img => img?.generatedResult);
        });
        if(pending) actions.push({id:'run', label:'执行节点', icon:'play'});
    }
    if(!actions.length && message?.text && !Store.isCanvasAgentFailureMessage(message)){
        actions.push({id:'save_text', label:'保存为文本节点', icon:'file-text'});
    }
    return actions;
}
function canvasAgentInteractionHtml(ic, chosenId){
    if(!ic || typeof ic !== 'object') return '';
    const intent = String(ic.intent || 'choose');
    const title = String(ic.title || '');
    const opts = Array.isArray(ic.options) ? ic.options : [];
    const fields = Array.isArray(ic.fields) ? ic.fields : [];
    const defaultId = String(ic.default_id || '');
    const resolved = !!ic.resolved;
    const disabledAttr = resolved ? ' disabled' : '';
    // 用户已选(clicked)优先于默认项：点C后重渲染仍高亮C，不跳回默认A
    const activeId = (chosenId && String(chosenId).trim()) ? String(chosenId).trim() : defaultId;
    const cardData = JSON.stringify({card_id: ic.card_id, intent, default_id: activeId}).replace(/</g, '\\u003c');
    let body = '';
    // 选择卡 / 确认卡
    if(intent === 'choose' || intent === 'confirm'){
        const rows = opts.map(o => {
            const oid = String(o.id || '');
            const isActive = oid === activeId;
            const desc = o.desc ? String(o.desc).trim() : '';
            return `<button class="canvas-agent-ic-opt${isActive ? ' selected' : ''}" type="button" data-ic-card="${deps.escapeHtml(ic.card_id || '')}" data-ic-select="${deps.escapeHtml(oid)}" data-ic-action="${deps.escapeHtml(o.action || '')}"${disabledAttr}>
                <span class="canvas-agent-ic-opt-head">
                    <span class="canvas-agent-ic-opt-label">${deps.escapeHtml(o.label || oid)}</span>
                    <span class="canvas-agent-ic-opt-check">${isActive ? '<i data-lucide="check-circle-2"></i>' : '<i data-lucide="circle"></i>'}</span>
                </span>
                ${desc ? `<span class="canvas-agent-ic-opt-desc">${deps.escapeHtml(desc)}</span>` : ''}
            </button>`;
        }).join('');
        // confirm 卡：主按钮固定"确认并继续"，简洁；标题显示在卡片上方（不塞按钮）
        const mainBtn = intent === 'confirm'
            ? `<button class="canvas-agent-ic-main" type="button" data-ic-card="${deps.escapeHtml(ic.card_id || '')}" data-ic-select="${deps.escapeHtml(defaultId)}" data-ic-action="${deps.escapeHtml((opts.find(o=>String(o.id)===defaultId)||{}).action || '')}"${disabledAttr}>确认并继续</button>`
            : '';
        body = `<div class="canvas-agent-ic-options">${rows}</div>${mainBtn}`;
    }
    // 表单卡
    else if(intent === 'collect'){
        const rows = fields.map(f => {
            const fkey = String(f.key || '');
            const ftype = String(f.type || 'text');
            if(ftype === 'select' && Array.isArray(f.options)){
                const selOpts = f.options.map(o => `<option value="${deps.escapeHtml(String(o.value ?? o.id ?? ''))}" ${String(o.value ?? o.id ?? '') === String(f.default ?? '') ? 'selected' : ''}>${deps.escapeHtml(String(o.label ?? o.value ?? ''))}</option>`).join('');
                return `<label class="canvas-agent-ic-field"><span>${deps.escapeHtml(String(f.label || fkey))}</span><select data-ic-field="${deps.escapeHtml(fkey)}"${disabledAttr}>${selOpts}</select></label>`;
            }
            return `<label class="canvas-agent-ic-field"><span>${deps.escapeHtml(String(f.label || fkey))}</span><input type="text" data-ic-field="${deps.escapeHtml(fkey)}" value="${deps.escapeHtml(String(f.default ?? ''))}" placeholder="${deps.escapeHtml(String(f.placeholder || ''))}"${disabledAttr}></label>`;
        }).join('');
        body = `<div class="canvas-agent-ic-fields">${rows}</div><button class="canvas-agent-ic-main" type="button" data-ic-card="${deps.escapeHtml(ic.card_id || '')}" data-ic-submit="1"${disabledAttr}>提交</button>`;
    }
    // 进度卡
    else if(intent === 'progress'){
        body = `<div class="canvas-agent-ic-progress"><span class="canvas-agent-ic-dot"></span>${deps.escapeHtml(title || '生成中…')}</div>`;
    }
    // 产物卡
    else if(intent === 'artifact'){
        body = `<div class="canvas-agent-ic-artifact">${deps.escapeHtml(title || '产物')}<span class="canvas-agent-ic-artifact-id">${deps.escapeHtml(String(ic.asset_id || ''))}</span></div>`;
    }
    else {
        body = `<div class="canvas-agent-ic-text">${deps.escapeHtml(title)}</div>`;
    }
    return `<div class="canvas-agent-ic${resolved ? ' resolved' : ''}" data-ic-intent="${deps.escapeHtml(intent)}" data-ic-resolved="${resolved ? '1' : '0'}" data-ic-data="${cardData}">${title ? `<div class="canvas-agent-ic-title">${deps.escapeHtml(title)}</div>` : ''}${body}</div>`;
}
function canvasAgentMessageHtml(message){
    const role = message.role === 'user' ? 'user' : 'assistant';
    const refs = Array.isArray(message.refs) && message.refs.length
        ? `<div class="canvas-agent-message-refs">${message.refs.map(canvasAgentRefThumbHtml).join('')}</div>`
        : '';
const isThinking = role === 'assistant' && message.status === 'thinking';
// 用户消息不显示软件小图标（仅 assistant 保留头像）
const avatar = role === 'assistant'
? '<div class="canvas-agent-message-avatar" aria-hidden="true"><img src="/static/images/myrid-icon.png" alt=""></div>'
: '';
const timestampHtml = message.createdAt
    ? `<span class="canvas-agent-msg-time" title="${new Date(message.createdAt).toLocaleString()}">${new Date(message.createdAt).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}</span>`
    : '';
// 历史遗留兜底：text 是候选 JSON 但 brainstormCard 未解析时，渲染时补解析成卡片
let bsCardData = message.brainstormCard;
if(role === 'assistant' && !bsCardData){
    const candidateJson = deps.canvasAgentParseBrainstormReply(message.text || '');
    if(candidateJson && (Array.isArray(candidateJson.candidates) || candidateJson.stage)){
        bsCardData = candidateJson;
    }
}
const bsIsLocked = role === 'assistant' && Boolean(message.brainstormLocked);
const bsCardHtml = bsCardData ? canvasAgentBrainstormCardHtml(bsCardData, message) : '';
const isRawCandidateJson = Boolean(bsCardData && message.text && /^[\s\S]*?\{[\s\S]*?"candidates"[\s\S]*?\}[\s\S]*?$/.test(String(message.text).trim()));
// 带候选卡片的消息：卡片区已渲染问题文本+候选，消息本级不再重复渲染 question 文本，避免"两个版本"
const textForRender = bsCardData ? '' : (message.text || '');
const textHtml = isThinking
? '<div class="canvas-agent-thinking"><span>思考中</span><i></i><i></i><i></i></div>'
: `<div class="canvas-agent-text">${deps.escapeHtml(textForRender).replace(/\n/g, '<br>')}</div>`;
const bsChosenId = String(message.brainstormChosenId || deps.getChosenMap()[message.id] || '');
const bsRunHtml = (bsIsLocked && bsChosenId) ? `<div class="canvas-agent-bs-done">
    <span class="canvas-agent-bs-done-text"><i data-lucide="check-circle-2"></i>已选择${deps.escapeHtml(bsChosenId)}，已创建 ${Array.isArray(message.brainstormNodeIds) ? message.brainstormNodeIds.length : ''} 个节点</span>
    <button class="canvas-agent-message-action primary" type="button" data-bs-run="${deps.escapeHtml(message.id || '')}" ${message.brainstormExecuted ? 'disabled' : ''}><i data-lucide="${message.brainstormExecuted ? 'check' : 'play'}"></i><span>${message.brainstormExecuted ? '已完成' : '执行'}</span></button>
</div>` : '';
const hasExecutablePlan = message.actionPlan && Array.isArray(message.actionPlan.steps) && message.actionPlan.steps.length;
const hasExecutableNodes = Array.isArray(message.nodeIds) && message.nodeIds.some(id => {
    const node = (deps.getNodes() || []).find(n => n.id === id);
    return node && node.type === 'smart-image' && !(node.images || []).some(img => img?.generatedResult);
}) || (deps.getNodes() || []).some(n => String(n.id || '').startsWith('agent_') && n.type === 'smart-image' && !(n.images || []).some(img => img?.generatedResult));
const showRunBtn = !message.brainstormCard && (hasExecutablePlan || hasExecutableNodes);
const showLocateBtn = !message.brainstormCard && (Array.isArray(message.nodeIds) && message.nodeIds.length || (deps.getNodes() || []).some(n => String(n.id || '').startsWith('agent_')));
const traceItems = Array.isArray(message.toolTrace?.items) ? message.toolTrace.items : [];
const traceHtml = traceItems.length ? `<div class="canvas-agent-trace">
${traceItems.map(item => `<div class="canvas-agent-trace-item ${item.ok ? 'ok' : 'error'}">
    <span class="canvas-agent-trace-dot"></span>
    <span class="canvas-agent-trace-label">${deps.escapeHtml(item.label || item.name || '执行动作')}</span>
    ${item.detail ? `<span class="canvas-agent-trace-detail">${deps.escapeHtml(item.detail)}</span>` : ''}
</div>`).join('')}
</div>` : '';
const action = role === 'assistant' && message.text && !isThinking && !Store.isCanvasAgentFailureMessage(message)
? `<div class="canvas-agent-message-actions">
<button class="canvas-agent-message-icon" type="button" data-agent-copy="${deps.escapeHtml(message.id || '')}" title="复制回复内容" aria-label="复制回复内容"><i data-lucide="copy"></i></button>
<button class="canvas-agent-message-icon" type="button" data-agent-quote="${deps.escapeHtml(message.id || '')}" title="引用到对话框" aria-label="引用到对话框"><i data-lucide="quote"></i></button>
${showLocateBtn ? `<button class="canvas-agent-message-icon" type="button" data-agent-locate="${deps.escapeHtml(message.id || '')}" title="定位画布节点" aria-label="定位画布节点"><i data-lucide="locate-fixed"></i></button>` : ''}
${message.latencyText ? `<span class="canvas-agent-msg-latency" title="大模型返回答案所用时间">${deps.escapeHtml(message.latencyText)}</span>` : ''}
${showRunBtn ? `<button class="canvas-agent-message-action primary" type="button" data-agent-run="${deps.escapeHtml(message.id || '')}" title="${message.executed ? '已完成' : '执行'}" ${message.executed ? 'disabled' : ''}><i data-lucide="${message.executed ? 'check' : 'play'}"></i><span>${message.executed ? '已完成' : '执行'}</span></button>` : ''}
</div>`
: '';
// 用户消息专用操作：时间(常显,在复制按钮左边) + 复制 + 编辑并重发
const userAction = role === 'user' && message.text
? `<div class="canvas-agent-message-actions user">
${timestampHtml}
<button class="canvas-agent-message-icon" type="button" data-agent-copy="${deps.escapeHtml(message.id || '')}" title="复制内容" aria-label="复制内容"><i data-lucide="copy"></i></button>
<button class="canvas-agent-message-icon" type="button" data-agent-edit="${deps.escapeHtml(message.id || '')}" title="编辑并重发" aria-label="编辑并重发"><i data-lucide="edit-2"></i></button>
</div>`
: '';
const suggestions = role === 'assistant' && message.text && !isThinking && !Store.isCanvasAgentFailureMessage(message)
    ? ((Array.isArray(message.suggestions) && message.suggestions.length) ? message.suggestions : canvasAgentSuggestionsFromText(message.text))
    : [];
const quickActions = role === 'assistant' && !isThinking ? canvasAgentQuickActionsForMessage(message) : [];
const suggestionsHtml = suggestions.length
    ? `<div class="canvas-agent-suggestions">${suggestions.map(s => `
        <button class="canvas-agent-suggestion" type="button" data-agent-suggest="${deps.escapeHtml(s.key)}" data-agent-message="${deps.escapeHtml(message.id || '')}" data-agent-node="${deps.escapeHtml(s.nodeId || '')}" data-agent-action="${deps.escapeHtml(s.action || '')}" title="选择建议 ${s.key}">
            <span class="canvas-agent-suggestion-key">${deps.escapeHtml(s.key)}</span>
            <span class="canvas-agent-suggestion-text">${deps.escapeHtml(s.text)}</span>
        </button>`).join('')}</div>`
    : '';
const quickActionsHtml = quickActions.length
    ? `<div class="canvas-agent-suggestions">${quickActions.map(action => `
        <button class="canvas-agent-suggestion" type="button" data-agent-quick="${deps.escapeHtml(action.id)}" data-agent-message="${deps.escapeHtml(message.id || '')}" data-agent-batch="${deps.escapeHtml(action.batchId || '')}">
            <i data-lucide="${deps.escapeHtml(action.icon || 'sparkles')}"></i>
            <span class="canvas-agent-suggestion-text">${deps.escapeHtml(action.label)}</span>
        </button>`).join('')}</div>`
    : '';
const interactionHtml = message.interaction ? canvasAgentInteractionHtml(message.interaction, message.chosenId) : '';
const skillsHtml = (Array.isArray(message.loadedSkills) && message.loadedSkills.length)
    ? `<div class="canvas-agent-skills"><span class="canvas-agent-skills-label">本次加载技能</span>${message.loadedSkills.map(s => `<span class="canvas-agent-skill-chip" title="本轮按该技能执行">${deps.escapeHtml(s)}</span>`).join('')}</div>`
    : '';
const taskHtml = (role === 'assistant' && message.task && message.step)
    ? `<div class="canvas-agent-skills canvas-agent-task-state"><span class="canvas-agent-skills-label">${deps.escapeHtml(message.task.title || 'Agent Task')}</span><span class="canvas-agent-skill-chip">${deps.escapeHtml(message.step.label || message.step.step_id || '')}</span>${message.progress ? `<span class="canvas-agent-skill-chip">${deps.escapeHtml(String(message.progress.current || 0))}/${deps.escapeHtml(String(message.progress.total || 0))}</span>` : ''}<span class="canvas-agent-skill-chip">${deps.escapeHtml(message.task.status || '')}</span></div>`
    : '';
// 原地编辑：该消息处于编辑态时，文本区替换为编辑框
const userEditHtml = (role === 'user' && canvasAgentEditingId === message.id) ? canvasAgentUserEditHtml(message) : '';
return `<div class="canvas-agent-message ${role}" data-agent-message-id="${deps.escapeHtml(message.id || '')}">
${avatar}<div class="canvas-agent-bubble">${refs}${userEditHtml || textHtml}${taskHtml}${skillsHtml}${interactionHtml}${bsCardHtml}${bsRunHtml}${traceHtml}${action}${userAction}${suggestionsHtml}${quickActionsHtml}</div>
</div>`;
}
function canvasAgentBrainstormCardHtml(card, message){
    if(!card) return '';
    const msg = message || {};
    const candidates = Array.isArray(card.candidates) ? card.candidates : [];
    const chosenId = String(msg.brainstormChosenId || deps.getChosenMap()[msg.id] || '');
    const locked = Boolean(msg.brainstormLocked);
    const question = card.question ? `<div class="canvas-agent-bs-question">${deps.escapeHtml(card.question)}</div>` : '';
    const cards = candidates.map(c => {
        const cid = String(c.id || c.title || '');
        const isChosen = locked && chosenId && cid === chosenId;
        const isOtherLocked = locked && !isChosen;
        let cls = 'canvas-agent-bs-card';
        let btnHtml;
        // 锁定态由 done 条(bsRunHtml)唯一表达选择状态，卡片区只保留候选展示，避免"已选择/已锁定"与 done 条重复
        if(locked){
            cls += isChosen ? ' selected' : ' locked';
            btnHtml = '';
        }else{
            const label = c.id ? `选择${deps.escapeHtml(String(c.id))}` : '选择这个';
            btnHtml = `<button class="canvas-agent-bs-pick" type="button" data-bs-pick="${deps.escapeHtml(cid)}" data-bs-title="${deps.escapeHtml(c.title || '')}">${label}</button>`;
        }
        return `
        <div class="${cls}">
            <div class="canvas-agent-bs-card-title">${deps.escapeHtml(c.title || cid || '')}</div>
            <div class="canvas-agent-bs-card-desc">${deps.escapeHtml(c.desc || '')}</div>
            ${Array.isArray(c.tags) && c.tags.length ? `<div class="canvas-agent-bs-card-tags">${c.tags.map(t => `<span>${deps.escapeHtml(t)}</span>`).join('')}</div>` : ''}
            ${btnHtml}
        </div>`;
    }).join('');
    const refresh = locked ? '' : `<button class="canvas-agent-bs-refresh" type="button" data-bs-refresh="1">都不太行，换一批</button>`;
    return `<div class="canvas-agent-bs${locked ? ' bs-locked' : ''}" data-bs-card="${deps.escapeHtml(msg.id || '')}">${question}<div class="canvas-agent-bs-cards">${cards}</div>${refresh}</div>`;
}
function canvasAgentUserEditHtml(message){
    const messageId = String(message.id || '');
    const safeText = deps.escapeHtml(message.text || '');
    return `<div class="canvas-agent-edit-box">
<textarea class="canvas-agent-edit-textarea" data-agent-editing-textarea="${messageId}" rows="3">${safeText}</textarea>
<div class="canvas-agent-edit-actions">
<button class="canvas-agent-message-icon canvas-agent-edit-cancel" type="button" data-agent-edit-cancel="${messageId}" title="取消编辑" aria-label="取消编辑"><i data-lucide="x"></i></button>
<button class="canvas-agent-message-icon canvas-agent-edit-send" type="button" data-agent-edit-send="${messageId}" title="发送编辑后的消息" aria-label="发送编辑后的消息"><i data-lucide="arrow-up"></i></button>
</div>
</div>`;
}
function canvasAgentRefThumbHtml(ref, index=0){
    const kind = ref?.artifactId ? 'artifact' : deps.mediaKindForItem(ref);
    const fileName = canvasAgentRefFileName(ref);
    const inDraft = deps.getRefs().some(r => r.url === ref?.url);
    const name = `${inDraft ? canvasAgentRefStripLabel(ref, index) : canvasAgentRefKindLabel(ref) + (index + 1)}${fileName ? ' · ' + fileName : ''}`;
    const media = kind === 'image'
        ? `<img src="${deps.escapeHtml(ref.url)}" alt="">`
        : kind === 'video'
        ? `<video src="${deps.escapeHtml(ref.url)}" muted preload="metadata" playsinline></video>`
        : `<span class="canvas-agent-ref-file"><i data-lucide="${kind === 'audio' ? 'file-audio' : kind === 'text' ? 'file-text' : 'file'}"></i></span>`;
    return `<div class="canvas-agent-ref canvas-agent-ref-${deps.escapeHtml(kind)}" title="${deps.escapeHtml(name)}" aria-label="${deps.escapeHtml(name)}">
        ${media}
        <span class="canvas-agent-ref-name">${deps.escapeHtml(name)}</span>
        <button type="button" data-agent-ref-remove="${deps.escapeHtml(ref.url)}" title="移除"><i data-lucide="x"></i></button>
    </div>`;
}
function canvasAgentRefFileName(ref){
    const fromUrl = decodeURIComponent(String(ref?.url || '').split('/').pop().split('?')[0] || '');
    return fromUrl || ref?.name || '';
}
function canvasAgentRefKindLabel(ref){
    const kind = deps.mediaKindForItem(ref);
    return kind === 'video' ? '视频' : kind === 'audio' ? '音频' : kind === 'text' ? '文本' : kind === 'file' ? '文件' : '图片';
}
function canvasAgentRefStripLabel(ref, index){
    // 引用条角标与 @弹层网格同号（网格顺序即编号，对话框不重排）
    const inPool = deps.getMentionPool().some(r => r.url === ref?.url);
    if(inPool) return canvasAgentMentionBadge(ref);
    const label = canvasAgentRefKindLabel(ref);
    const pos = deps.getRefs().filter(r => canvasAgentRefKindLabel(r) === label).findIndex(r => r.url === ref.url);
    return `${label}${pos >= 0 ? pos + 1 : index + 1}`;
}
function canvasAgentMentionBadge(ref){
    const label = canvasAgentRefKindLabel(ref);
    const pool = (deps.getMentionPool().length ? deps.getMentionPool() : deps.canvasAgentMentionCandidates())
        .filter(r => canvasAgentRefKindLabel(r) === label);
    const pos = pool.findIndex(r => r.url === ref.url);
    return pos >= 0 ? `${label}${pos + 1}` : label;
}

    global.CanvasAgentMessageRender = {
        configure: configure,
        canvasAgentMediaLabel: canvasAgentMediaLabel,
        canvasAgentRefFromImage: canvasAgentRefFromImage,
        canvasAgentSuggestionsFromText: canvasAgentSuggestionsFromText,
        canvasAgentFormatLatency: canvasAgentFormatLatency,
        canvasAgentToolLabel: canvasAgentToolLabel,
        canvasAgentTraceFromToolLog: canvasAgentTraceFromToolLog,
        normalizeCanvasAgentResult: normalizeCanvasAgentResult,
        isCanvasAgentStoppedEmptyReply: isCanvasAgentStoppedEmptyReply,
        canvasAgentQuickActionsForMessage: canvasAgentQuickActionsForMessage,
        canvasAgentInteractionHtml: canvasAgentInteractionHtml,
        canvasAgentMessageHtml: canvasAgentMessageHtml,
        canvasAgentBrainstormCardHtml: canvasAgentBrainstormCardHtml,
        canvasAgentUserEditHtml: canvasAgentUserEditHtml,
        canvasAgentRefThumbHtml: canvasAgentRefThumbHtml,
        canvasAgentRefFileName: canvasAgentRefFileName,
        canvasAgentRefKindLabel: canvasAgentRefKindLabel,
        canvasAgentRefStripLabel: canvasAgentRefStripLabel,
        canvasAgentMentionBadge: canvasAgentMentionBadge
    };
})(typeof window !== 'undefined' ? window : globalThis);

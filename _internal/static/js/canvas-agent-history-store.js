/* MyridTV 画布 Agent 会话存储层（拆模块 ④-1：历史列表 / 后端同步 / legacy 迁移 / 克隆与提示词抽取）
 *
 * 背景：canvasAgent* 面板约 168 个函数散在 smart-canvas.js。这一刀切「存储与纯函数层」：
 * 对 DOM/渲染零依赖，是面板里可独立测试的切片。函数体为自主文件逐字迁入（脚本提取，非手抄），
 * 依赖（uid/后端地址/会话状态/storyboard 构建）全部 configure() 注入。
 *
 * 所有权：模块自持 history 缓存/loaded/loading/索引缓存/迁移 promise；
 * 会话内容（messages/sessionId/lastReply）仍归主文件，经 deps.getSession() 读取。
 * 兼容：主文件薄别名转调，旧调用点签名不变。
 */
(function (global) {
    'use strict';

    var deps = {
        proxyBase: null, loadAppRuntimeConfig: null, uid: null,
        canvasId: null, historyKey: null, historyKeyPrefix: null, historyKeySuffix: null,
        buildStoryboardPlan: null, buildStoryboardPlanFromReply: null,
        getSession: null,   // () => {messages, sessionId, lastReply, lastReplyRefs}
        getCanvasTitle: null
    };
    function configure(opts) {
        Object.assign(deps, opts || {});
    }

    // ===== 模块自持状态（自主文件迁入，只被以下函数读写）=====
    let canvasAgentHistoryCache = [];
    let canvasAgentHistoryLoaded = false;
    let canvasAgentHistoryLoading = null;
    let canvasAgentHistoryIndexCache = [];
    let canvasAgentLegacyMigrationPromise = null;

function canvasAgentHistoryList(){
    return Array.isArray(canvasAgentHistoryCache) ? canvasAgentHistoryCache.map(item => ({
        ...item,
        messages:canvasAgentSerializableMessages(item.messages),
        lastReply:String(item.lastReply || ''),
        lastReplyRefs:canvasAgentCloneRefs(item.lastReplyRefs)
    })) : [];
}
function saveCanvasAgentHistoryList(list){
    canvasAgentHistoryCache = Array.isArray(list) ? list.slice(0, 24) : [];
}
function canvasAgentHistoryKeyFor(id=''){
    return `${deps.historyKeyPrefix()}${id || 'default'}${deps.historyKeySuffix()}`;
}
function canvasAgentLegacyHistoryList(){
    try {
        const list = JSON.parse(localStorage.getItem(deps.historyKey()) || '[]');
        return Array.isArray(list) ? list.filter(item => item?.id && Array.isArray(item.messages)).map(item => ({
            ...item,
            messages:canvasAgentSerializableMessages(item.messages),
            lastReply:String(item.lastReply || ''),
            lastReplyRefs:canvasAgentCloneRefs(item.lastReplyRefs)
        })) : [];
    } catch(_) {
        return [];
    }
}
function canvasAgentLegacyHistoryListFor(canvasHistoryId=''){
    try {
        const key = canvasAgentHistoryKeyFor(canvasHistoryId);
        const list = JSON.parse(localStorage.getItem(key) || '[]');
        return Array.isArray(list) ? list.filter(item => item?.id && Array.isArray(item.messages)).map(item => ({
            ...item,
            messages:canvasAgentSerializableMessages(item.messages),
            lastReply:String(item.lastReply || ''),
            lastReplyRefs:canvasAgentCloneRefs(item.lastReplyRefs)
        })) : [];
    } catch(_) {
        return [];
    }
}
async function migrateLegacyCanvasAgentHistories(){
    if(canvasAgentLegacyMigrationPromise) return canvasAgentLegacyMigrationPromise;
    canvasAgentLegacyMigrationPromise = (async () => {
        await deps.loadAppRuntimeConfig();
        let keys = [];
        try {
            keys = Object.keys(localStorage).filter(key => key.startsWith(deps.historyKeyPrefix()) && key.endsWith(deps.historyKeySuffix()));
        } catch(_) {
            keys = [];
        }
        for(const key of keys){
            const canvasHistoryId = key.slice(deps.historyKeyPrefix().length, key.length - deps.historyKeySuffix().length);
            const normalizedCanvasId = canvasHistoryId === 'default' ? '' : canvasHistoryId;
            const legacy = canvasAgentLegacyHistoryListFor(normalizedCanvasId);
            if(!legacy.length) continue;
            try {
                await fetch(`${deps.proxyBase()}/api/canvas-agent-history`, {
                    method:'POST',
                    headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({
                        canvas_id: normalizedCanvasId,
                        canvas_title: '',
                        history: legacy
                    })
                });
                localStorage.removeItem(key);
                if(normalizedCanvasId === String(deps.canvasId() || '')){
                    saveCanvasAgentHistoryList(legacy);
                    canvasAgentHistoryLoaded = true;
                }
            } catch(_) {}
        }
    })();
    return canvasAgentLegacyMigrationPromise;
}
async function loadCanvasAgentHistoryList(force=false){
    if(canvasAgentHistoryLoaded && !force) return canvasAgentHistoryList();
    if(canvasAgentHistoryLoading && !force) return canvasAgentHistoryLoading;
    canvasAgentHistoryLoading = (async () => {
        await migrateLegacyCanvasAgentHistories();
        try {
            const res = await fetch(`${deps.proxyBase()}/api/canvas-agent-history?canvas_id=${encodeURIComponent(deps.canvasId() || '')}`, {cache:'no-store'});
            if(!res.ok) throw new Error('history-fetch-failed');
            const data = await res.json();
            const history = Array.isArray(data.history) ? data.history : [];
            if(history.length){
                saveCanvasAgentHistoryList(history);
            } else {
                const legacy = canvasAgentLegacyHistoryList();
                if(legacy.length){
                    saveCanvasAgentHistoryList(legacy);
                    await persistCanvasAgentHistoryStore();
                    try { localStorage.removeItem(deps.historyKey()); } catch(_) {}
                } else {
                    saveCanvasAgentHistoryList([]);
                }
            }
            canvasAgentHistoryLoaded = true;
            return canvasAgentHistoryList();
        } catch(_) {
            const legacy = canvasAgentLegacyHistoryList();
            saveCanvasAgentHistoryList(legacy);
            canvasAgentHistoryLoaded = true;
            return canvasAgentHistoryList();
        } finally {
            canvasAgentHistoryLoading = null;
        }
    })();
    return canvasAgentHistoryLoading;
}
async function persistCanvasAgentHistoryStore(){
    await deps.loadAppRuntimeConfig();
    const payload = {
        canvas_id: deps.canvasId() || '',
        canvas_title: deps.getCanvasTitle() || '',
        history: canvasAgentHistoryList()
    };
    const res = await fetch(`${deps.proxyBase()}/api/canvas-agent-history`, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify(payload)
    });
    if(!res.ok) throw new Error('history-save-failed');
    const data = await res.json().catch(() => ({}));
    saveCanvasAgentHistoryList(Array.isArray(data.history) ? data.history : payload.history);
    canvasAgentHistoryLoaded = true;
    return canvasAgentHistoryList();
}
async function loadCanvasAgentHistoryIndex(){
    await deps.loadAppRuntimeConfig();
    try {
        const res = await fetch(`${deps.proxyBase()}/api/canvas-agent-history-index`, {cache:'no-store'});
        if(!res.ok) throw new Error('history-index-fetch-failed');
        const data = await res.json();
        canvasAgentHistoryIndexCache = Array.isArray(data.entries) ? data.entries : [];
    } catch(_) {
        canvasAgentHistoryIndexCache = [];
    }
    return canvasAgentHistoryIndexCache;
}
function canvasAgentSessionTitle(messages=null){
    if(!messages) messages = deps.getSession().messages;
    const firstUser = (messages || []).find(msg => msg.role === 'user' && String(msg.text || '').trim());
    return String(firstUser?.text || '新对话').trim().replace(/\s+/g, ' ').slice(0, 28) || '新对话';
}
function canvasAgentCloneRefs(refs=[]){
return (Array.isArray(refs) ? refs : []).map(ref => {
const clone = {...ref};
const content = String(clone.textContent || '');
if(content.length > 4000) clone.textContent = `${content.slice(0, 4000)}\n...(内容过长已截断)`;
return clone;
}).filter(ref => ref.url || ref.nodeId || ref.name || ref.title);
}
function canvasAgentCloneActionPlan(plan){
if(!plan || typeof plan !== 'object') return null;
try {
const clone = JSON.parse(JSON.stringify(plan));
return Array.isArray(clone.steps) && clone.steps.length ? clone : null;
} catch(_) {
return null;
}
}
function canvasAgentCloneMessage(message){
if(!message) return null;
if(message.status === 'thinking') return null;
const text = String(message.text ?? message.content ?? '').trim();
const refs = canvasAgentCloneRefs(message.refs);
const sourceRefs = canvasAgentCloneRefs(message.sourceRefs);
const actionPlan = canvasAgentCloneActionPlan(message.actionPlan);
if(!text && !refs.length && !sourceRefs.length) return null;
const cloned = {
id:message.id || deps.uid('agent_msg'),
role:message.role === 'user' ? 'user' : 'assistant',
text,
refs,
sourceRefs
};
if(actionPlan && cloned.role === 'assistant') cloned.actionPlan = actionPlan;
if(message.brainstormCard && cloned.role === 'assistant') cloned.brainstormCard = message.brainstormCard;
if(message.toolTrace && Array.isArray(message.toolTrace.items) && message.toolTrace.items.length) cloned.toolTrace = message.toolTrace;
if(Array.isArray(message.nodeIds) && message.nodeIds.length) cloned.nodeIds = message.nodeIds.slice();
if(message.latencyText) cloned.latencyText = message.latencyText;
if(message.executed) cloned.executed = true;
if(message.chosenId) cloned.chosenId = message.chosenId;
if(cloned.role === 'assistant'){
    if(message.brainstormLocked) cloned.brainstormLocked = true;
    if(message.brainstormChosenId) cloned.brainstormChosenId = message.brainstormChosenId;
    if(Array.isArray(message.brainstormNodeIds) && message.brainstormNodeIds.length) cloned.brainstormNodeIds = message.brainstormNodeIds.slice();
    if(message.brainstormExecuted) cloned.brainstormExecuted = true;
}
// 保留交互卡片（选择/表单/确认/进度/产物），重启后历史才能重建选项卡
if(cloned.role === 'assistant' && message.interaction && typeof message.interaction === 'object'){
    cloned.interaction = message.interaction;
}
// 保留本轮加载的技能名，历史重开仍可见
if(cloned.role === 'assistant' && Array.isArray(message.loadedSkills) && message.loadedSkills.length){
    cloned.loadedSkills = message.loadedSkills.slice();
}
if(cloned.role === 'assistant' && message.task && typeof message.task === 'object') cloned.task = JSON.parse(JSON.stringify(message.task));
if(cloned.role === 'assistant' && message.step && typeof message.step === 'object') cloned.step = JSON.parse(JSON.stringify(message.step));
if(cloned.role === 'assistant' && message.progress && typeof message.progress === 'object') cloned.progress = JSON.parse(JSON.stringify(message.progress));
return cloned;
}
function restoreCanvasAgentActionPlans(messages=[]){
let previousUser = null;
return (Array.isArray(messages) ? messages : []).map(message => {
if(message?.role === 'user'){
previousUser = message;
return message;
}
if(message?.role === 'assistant' && !message.actionPlan && previousUser){
const basePlan = deps.buildStoryboardPlan(previousUser.text || '', previousUser.refs || previousUser.sourceRefs || []);
const restoredPlan = deps.buildStoryboardPlanFromReply(message.text || '', basePlan);
if(restoredPlan && Array.isArray(restoredPlan.steps) && restoredPlan.steps.length){
return {...message, actionPlan:restoredPlan};
}
}
return message;
});
}
function isCanvasAgentFailureMessage(message){
return message?.role === 'assistant' && /^请求失败：/.test(String(message.text || '').trim());
}
function canvasAgentCleanPromptCandidate(value=''){
    return String(value || '')
        .replace(/^```[\w-]*\s*/i, '')
        .replace(/```$/i, '')
        .replace(/^\s*[-*]\s+/gm, '')
        .replace(/^\s*(提示词|正向提示词|生成提示词|Prompt|Final Prompt)\s*[:：]\s*/gim, '')
        .trim();
}
function canvasAgentFallbackPromptCandidate(value=''){
    const source = String(value || '').trim();
    const lines = source
        .replace(/```[\s\S]*?```/g, '')
        .split(/\r?\n/)
        .map(line => line.trim())
        .filter(Boolean)
        .map(line => line.replace(/^\s*(?:[-*•]|[0-9]+[.)、])\s*/, '').trim())
        .filter(Boolean)
        .filter(line => !/^(?:✅|✔|任务已完成|已完成|请查收|画布节点|节点|执行结果|操作结果|说明|解析|建议|步骤|备注|参考|为什么|注意|参数|尺寸|比例)(?:$|[\s:：，,。!！])/i.test(line))
        .filter(line => !/^#{1,6}\s*/.test(line));
    const promptLike = lines.filter(line =>
        line.length >= 6 &&
        /(生成|改成|换成|换个|换一套|变成|添加|去除|保留|人物|背景|风格|画面|镜头|光影|颜色|发色|服装|姿势|场景|构图|特写|提示词|prompt)/i.test(line)
    );
    const picked = (promptLike.length ? promptLike : lines).slice(0, 4).join('\n');
    const cleaned = canvasAgentCleanPromptCandidate(picked);
    return cleaned && cleaned.length < source.length ? cleaned : '';
}
function extractCanvasAgentPrompt(text=''){
    const source = String(text || '').trim();
    if(!source) return '';
    const codeBlocks = [...source.matchAll(/```(?:prompt|text|txt|markdown|md)?\s*([\s\S]*?)```/gi)]
        .map(match => canvasAgentCleanPromptCandidate(match[1]))
        .filter(Boolean);
    const promptHeading = /(?:^|\n)\s*(?:#{1,6}\s*)?(?:【\s*)?(?:正向)?(?:生成)?提示词|Prompt|Final Prompt(?:\s*】)?\s*[:：]?\s*/i;
    const headingMatch = source.match(promptHeading);
    if(headingMatch){
        const start = (headingMatch.index || 0) + headingMatch[0].length;
        const rest = source.slice(start);
        const nextSection = rest.search(/\n\s*(?:#{1,6}\s*)?(?:【\s*)?(?:负面提示词|Negative Prompt|参数|尺寸|比例|说明|解析|建议|参考|步骤|备注|为什么|优化点)(?:\s*】)?\s*[:：]?/i);
        const section = nextSection >= 0 ? rest.slice(0, nextSection) : rest;
        const cleaned = canvasAgentCleanPromptCandidate(section);
        if(cleaned) return cleaned;
    }
    const inline = source.match(/(?:提示词|Prompt)\s*[:：]\s*([^\n]+(?:\n(?!\s*(?:负面提示词|参数|说明|建议|解析|参考|步骤)\s*[:：]).+)*)/i);
    if(inline?.[1]){
        const cleaned = canvasAgentCleanPromptCandidate(inline[1]);
        if(cleaned) return cleaned;
    }
    if(codeBlocks.length) return codeBlocks[0];
    const fallback = canvasAgentFallbackPromptCandidate(source);
    if(fallback) return fallback;
    return source;
}
function canvasAgentSerializableMessages(messages=null){
    if(!messages) messages = deps.getSession().messages;
    return (Array.isArray(messages) ? messages : []).map(canvasAgentCloneMessage).filter(Boolean).filter(msg => !isCanvasAgentFailureMessage(msg));
}
async function persistCanvasAgentSession(){
    if(!deps.getSession().messages.length) return;
    const messages = canvasAgentSerializableMessages();
    if(!messages.length) return;
    await loadCanvasAgentHistoryList();
    const list = canvasAgentHistoryList().filter(item => item.id !== deps.getSession().sessionId);
    list.unshift({
        id:deps.getSession().sessionId,
        title:canvasAgentSessionTitle(messages),
        updatedAt:Date.now(),
        messages,
        lastReply:deps.getSession().lastReply,
        lastReplyRefs:canvasAgentCloneRefs(deps.getSession().lastReplyRefs)
    });
    saveCanvasAgentHistoryList(list);
    await persistCanvasAgentHistoryStore();
}

    function getCanvasAgentHistoryIndexCache(){
        return canvasAgentHistoryIndexCache;
    }

    global.CanvasAgentHistoryStore = {
        configure: configure,
        getCanvasAgentHistoryIndexCache: getCanvasAgentHistoryIndexCache,
        canvasAgentHistoryList: canvasAgentHistoryList,
        saveCanvasAgentHistoryList: saveCanvasAgentHistoryList,
        canvasAgentHistoryKeyFor: canvasAgentHistoryKeyFor,
        canvasAgentLegacyHistoryList: canvasAgentLegacyHistoryList,
        canvasAgentLegacyHistoryListFor: canvasAgentLegacyHistoryListFor,
        migrateLegacyCanvasAgentHistories: migrateLegacyCanvasAgentHistories,
        loadCanvasAgentHistoryList: loadCanvasAgentHistoryList,
        persistCanvasAgentHistoryStore: persistCanvasAgentHistoryStore,
        loadCanvasAgentHistoryIndex: loadCanvasAgentHistoryIndex,
        canvasAgentSessionTitle: canvasAgentSessionTitle,
        canvasAgentCloneRefs: canvasAgentCloneRefs,
        canvasAgentCloneActionPlan: canvasAgentCloneActionPlan,
        canvasAgentCloneMessage: canvasAgentCloneMessage,
        restoreCanvasAgentActionPlans: restoreCanvasAgentActionPlans,
        isCanvasAgentFailureMessage: isCanvasAgentFailureMessage,
        canvasAgentCleanPromptCandidate: canvasAgentCleanPromptCandidate,
        canvasAgentFallbackPromptCandidate: canvasAgentFallbackPromptCandidate,
        extractCanvasAgentPrompt: extractCanvasAgentPrompt,
        canvasAgentSerializableMessages: canvasAgentSerializableMessages,
        persistCanvasAgentSession: persistCanvasAgentSession
    };
})(typeof window !== 'undefined' ? window : globalThis);

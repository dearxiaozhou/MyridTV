//** The Agent main send pipeline: assemble request, stream/await LLM reply, attach artifacts, finalize messages. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    function D(name){return typeof deps[name] === 'function' ? deps[name]() : deps[name];}

async function sendCanvasAgentMessage(resendUserMessage = null){
    if(D("canvasAgentSending")) return;
    deps.closeCanvasAgentMention();
    let refs;
    let messageText;
    let userMessage;
    let thinkingMessage;
    if(resendUserMessage){
        // 编辑重发路径：不读输入框、不新建 user 消息，直接复用被编辑的那条
        userMessage = resendUserMessage;
        messageText = String(userMessage.text || '').trim();
        refs = Array.isArray(userMessage.refs) ? userMessage.refs.slice() : [];
        if(!messageText && !refs.length){ deps.toast('编辑内容不能为空'); return; }
        if(!messageText){
            const onlyFileRefs2 = refs.length && !deps.imageRefsOnly(refs).length && !deps.videoRefsOnly(refs).length;
            messageText = onlyFileRefs2 ? '读取附件文本内容，自行识别内容类型后给出创作建议，如果是图片就解析图片内容。' : '请分析这些画布资源，并给出可执行的创作建议。';
            userMessage.text = messageText;
        }
    } else {
        const text = String(D("canvasAgentInput")?.value || '').trim();
        if(!text && !D("canvasAgentRefsState").length){
            deps.toast('先输入想法，或加入画布资源');
            return;
        }
        refs = D("canvasAgentRefsState").slice();
        const onlyFileRefs = refs.length && !deps.imageRefsOnly(refs).length && !deps.videoRefsOnly(refs).length;
        messageText = text || (onlyFileRefs ? '读取附件文本内容，自行识别内容类型后给出创作建议，如果是图片就解析图片内容。' : '请分析这些画布资源，并给出可执行的创作建议。');
        if(D("canvasAgentQuoteState")?.text){
            messageText = `【引用】\n${D("canvasAgentQuoteState").text}\n\n${messageText}`;
            deps.setCanvasAgentQuoteState(null);
            deps.renderCanvasAgentQuoteCard();
        }
        userMessage = {id:deps.uid('agent_msg'), role:'user', text:messageText, refs, chosenId:D("canvasAgentPendingChosenId") || '', createdAt:Date.now()};
        deps.setCanvasAgentPendingChosenId('');
    }
    thinkingMessage = {id:deps.uid('agent_msg'), role:'assistant', text:'思考中', status:'thinking', createdAt:Date.now()};
    const localActionPlan = deps.buildCanvasAgentStoryboardPlan(messageText, refs);
    if(!resendUserMessage) D("canvasAgentMessagesState").push(userMessage);
    D("canvasAgentMessagesState").push(thinkingMessage);
    deps.setCanvasAgentRefsState([]);
    deps.setCanvasAgentMentionPoolSnapshot([]); // 编号表随引用条一起清空
    if(!resendUserMessage){
        if(D("canvasAgentInput")) D("canvasAgentInput").value = '';
        deps.resizeCanvasAgentInput();
    }
    deps.renderCanvasAgentRefs();
    deps.renderCanvasAgentMessages();
    await deps.persistCanvasAgentSession();
    deps.setCanvasAgentBusy(true);
    deps.setCanvasAgentAbortController(new AbortController());
    deps.setCanvasAgentActiveRequestId(deps.uid('agent_req'));
    try {
        await deps.waitForCanvasAgentProxy();
        const chatProviders = deps.canvasAgentChatProviders();
        if(!chatProviders.length) throw new Error('未配置可用的聊天 API Key，请在 API 设置里启用一个带聊天模型的 OpenAI 兼容提供商。');
        const preset = D("canvasAgentModelPreset") || deps.canvasAgentLoadPreset();
        const generationPreset = deps.buildCanvasAgentGenerationPreset(preset, deps.imageRefsOnly(refs.filter(ref => ref?.url)).length ? 'i2i' : 't2i');
        const mediaRefs = refs.filter(ref => ref?.url);
        const images = deps.imageRefsOnly(mediaRefs).map(ref => ({
            url:ref.url,
            source_url:ref.source_url || ref.sourceUrl || '',
            name:ref.name || '',
            nodeId:ref.nodeId || '',
            imageIndex:ref.imageIndex ?? ''
        }));
        const videos = deps.videoRefsOnly(mediaRefs).map(ref => ref.url);
        const fileRefs = refs.filter(ref => ['text', 'file'].includes(deps.mediaKindForItem(ref)));
        const files = fileRefs.map(ref => ({
            url:ref.url,
            name:ref.name || '',
            kind:deps.mediaKindForItem(ref),
            content_type:ref.content_type || '',
            content_chars:deps.textContentValue(ref).length
        }));
        const fileTranscript = deps.canvasAgentFileTranscript(refs) + deps.canvasAgentArtifactTranscript(refs);
        const attachSummary = deps.canvasAgentAttachmentSummary(mediaRefs);
        const requestHistory = deps.canvasAgentHistoryForRequest();
        const requestMessage = deps.canvasAgentUsesLocalCodex()
            ? deps.canvasAgentRequestMessageForLocalCodex(messageText, attachSummary, fileTranscript)
            : deps.canvasAgentRequestMessage(messageText, attachSummary, requestHistory, fileTranscript);
        let result = null;
        let lastError = null;
        for(const chatProvider of chatProviders){
            const provider = chatProvider.id;
            const model = deps.resolveCanvasAgentChatModel(chatProvider);
            try {
                const activeAgentName = deps.canvasAgentRoleName(deps.canvasAgentActiveEntry(), 'Myrid-Agent');
                const requestPayload = {
                    message:requestMessage,
                    messages:requestHistory,
                    images,
                    videos,
                    files,
                    canvas_id:D("canvasId") || '',
                    agent_session_id:D("canvasAgentSessionId") || '',
                    request_id:D("canvasAgentActiveRequestId"),
                    model,
                    provider,
                    agent_id:D("canvasAgentActiveId"),
                    generation_preset:generationPreset,
                    system_prompt:`你是 MyridTV 无限画布里的 ${activeAgentName}。你擅长理解画布素材、生成创意方案、镜头/海报/电商/品牌提示词，并给出可以直接放进生成框的中文提示词。回答要具体、可执行。`
                };
                if(canvasAgentBrainstormState){
                    requestPayload.brainstorm = {
                        stage:canvasAgentBrainstormState.stage || '方向探索',
                        decisions:canvasAgentBrainstormState.decisions || []
                    };
                }
                result = await deps.fetchCanvasAgentLLM(requestPayload, undefined, D("canvasAgentAbortController")?.signal);
                break;
            } catch(providerError) {
                if(providerError?.userStopped) throw providerError;
                lastError = providerError;
            }
        }
        if(!result) throw lastError || new Error('Agent 请求失败');
        const normalizedResult = deps.normalizeCanvasAgentResult(result);
        const thinkingIndex = D("canvasAgentMessagesState").findIndex(msg => msg.id === thinkingMessage.id);
        if(deps.isCanvasAgentStoppedEmptyReply(result, normalizedResult.text)){
            if(thinkingIndex >= 0) D("canvasAgentMessagesState").splice(thinkingIndex, 1);
            deps.renderCanvasAgentMessages();
            await deps.persistCanvasAgentSession();
            deps.toast('已停止生成');
            return;
        }
        const reply = normalizedResult.text || '没有收到有效回复。';
        deps.setCanvasAgentLastReply(reply);
        deps.setCanvasAgentLastReplyRefs(mediaRefs);
const replyActionPlan = deps.buildCanvasAgentStoryboardPlanFromReply(reply, localActionPlan);
let brainstormCard = null;
let displayReply = reply;
// 解析不依赖头脑风暴开关：只要回复本身是候选 JSON，就总是建卡片（重开后状态丢失也能正确显示）
const parsed = deps.canvasAgentParseBrainstormReply(reply);
if(parsed && (Array.isArray(parsed.candidates) || parsed.stage)){
    brainstormCard = parsed;
    displayReply = parsed.question || reply;
    if(canvasAgentBrainstormState){
        canvasAgentBrainstormState.stage = parsed.stage || canvasAgentBrainstormState.stage;
        if(Array.isArray(parsed.decisions) && parsed.decisions.length) canvasAgentBrainstormState.decisions = parsed.decisions;
        if(parsed.done) canvasAgentBrainstormState.done = true;
        deps.renderCanvasAgentBrainstormBar();
    }
}
const assistantMessage = {
    id:deps.uid('agent_msg'),
    role:'assistant',
    text:displayReply,
    sourceRefs:mediaRefs,
    actionPlan:replyActionPlan,
    brainstormCard,
        toolTrace: normalizedResult.toolTrace,
        nodeIds: normalizedResult.nodeIds || [],
        suggestions: normalizedResult.suggestions || [],
        quickActions: normalizedResult.quickActions || [],
        interaction: normalizedResult.interaction || null,
        loadedSkills: normalizedResult.loadedSkills || [],
        task: normalizedResult.task || null,
        step: normalizedResult.step || null,
        progress: normalizedResult.progress || null,
        latencyText: deps.canvasAgentFormatLatency(thinkingMessage?.createdAt ? Date.now() - thinkingMessage.createdAt : 0)
};
        if(thinkingIndex >= 0) D("canvasAgentMessagesState").splice(thinkingIndex, 1, assistantMessage);
        else D("canvasAgentMessagesState").push(assistantMessage);
        deps.renderCanvasAgentMessages();
        await deps.persistCanvasAgentSession();
    } catch(e) {
        const stopped = !!e?.userStopped;
        const msg = stopped ? '已停止生成' : deps.canvasAgentFriendlyError(e);
        const thinkingIndex = D("canvasAgentMessagesState").findIndex(item => item.id === thinkingMessage.id);
        if(stopped){
            if(thinkingIndex >= 0) D("canvasAgentMessagesState").splice(thinkingIndex, 1);
            deps.renderCanvasAgentMessages();
            await deps.persistCanvasAgentSession();
            deps.toast(msg);
            return;
        }
        const errorMessage = {id:deps.uid('agent_msg'), role:'assistant', text:`请求失败：${msg}`};
        if(thinkingIndex >= 0) D("canvasAgentMessagesState").splice(thinkingIndex, 1, errorMessage);
        else D("canvasAgentMessagesState").push(errorMessage);
        deps.renderCanvasAgentMessages();
        deps.toast(msg);
    } finally {
        deps.setCanvasAgentBusy(false);
    }
}

    global.CanvasAgentSendChain = {
        configure,
        sendCanvasAgentMessage,
    };
})(typeof window !== 'undefined' ? window : this);

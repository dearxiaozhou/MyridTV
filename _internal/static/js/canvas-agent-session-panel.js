//** Agent session history panel: render list, open/close/toggle, switch/new/delete sessions. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    function D(name){return typeof deps[name] === 'function' ? deps[name]() : deps[name];}

function closeCanvasAgentHistory(){
    deps.setCanvasAgentHistoryOpen(false);
    D("canvasAgentHistoryPanel")?.classList.remove('open');
}
async function renderCanvasAgentHistory(){
    if(!D("canvasAgentHistoryPanel")) return;
    await deps.loadCanvasAgentHistoryList();
    await deps.loadCanvasAgentHistoryIndex();
    const list = deps.canvasAgentHistoryList();
    const currentSessionIds = new Set(list.map(item => item.id));
    const otherEntries = (CanvasAgentHistoryStore.getCanvasAgentHistoryIndexCache() || []).filter(entry => {
        if(!entry?.session_id) return false;
        if(String(entry.canvas_id || '') === String(D("canvasId") || '')) return !currentSessionIds.has(String(entry.session_id || ''));
        return true;
    }).slice(0, 12);
    const newChatHtml = '<button class="canvas-agent-history-item canvas-agent-history-newchat" type="button" data-agent-new-chat="1">'
        + '<span class="canvas-agent-history-main"><span class="canvas-agent-history-title"><i data-lucide="plus" class="w-3.5 h-3.5"></i> 新建对话</span></span>'
        + '</button>';
    if(!list.length && !otherEntries.length){
        D("canvasAgentHistoryPanel").innerHTML = newChatHtml + '<div class="canvas-agent-history-empty">暂无历史对话</div>';
        D("canvasAgentHistoryPanel").querySelector('[data-agent-new-chat]')?.addEventListener('click', e => {
            e.preventDefault(); e.stopPropagation();
            newCanvasAgentSession(true);
            closeCanvasAgentHistory();
        });
        if(window.lucide) lucide.createIcons();
        return;
    }
    const currentHtml = list.map(item => {
        const count = (item.messages || []).length;
        const active = item.id === D("canvasAgentSessionId") ? ' active' : '';
        const time = item.updatedAt ? new Date(item.updatedAt).toLocaleString('zh-CN', {month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit'}) : '';
        return `<button class="canvas-agent-history-item${active}" type="button" data-agent-session="${deps.escapeHtml(item.id)}">
            <span class="canvas-agent-history-main">
                <span class="canvas-agent-history-title">${deps.escapeHtml(item.title || '未命名对话')}</span>
                <span class="canvas-agent-history-meta">${deps.escapeHtml(time)} · ${count} 条</span>
            </span>
            <span class="canvas-agent-history-delete" data-agent-session-delete="${deps.escapeHtml(item.id)}" title="删除"><i data-lucide="trash-2"></i></span>
        </button>`;
    }).join('');
    const otherHtml = otherEntries.map(entry => {
        const time = entry.updatedAt ? new Date(entry.updatedAt).toLocaleString('zh-CN', {month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit'}) : '';
        const count = Number(entry.message_count || 0);
        const canvasLabel = String(entry.canvas_title || entry.canvas_id || '其他画布');
        return `<button class="canvas-agent-history-item" type="button" data-agent-history-entry="${deps.escapeHtml(entry.entry_id || '')}">
            <span class="canvas-agent-history-main">
                <span class="canvas-agent-history-title">${deps.escapeHtml(entry.title || '未命名对话')}</span>
                <span class="canvas-agent-history-meta">${deps.escapeHtml(canvasLabel)} · ${deps.escapeHtml(time)} · ${count} 条</span>
            </span>
        </button>`;
    }).join('');
    D("canvasAgentHistoryPanel").innerHTML = `${newChatHtml}${currentHtml}${otherHtml ? `<div class="D("canvas")-agent-history-empty" style="padding-top:6px;padding-bottom:4px">其他画布最近对话</div>${otherHtml}` : ''}`;
    D("canvasAgentHistoryPanel").querySelector('[data-agent-new-chat]')?.addEventListener('click', e => {
        e.preventDefault(); e.stopPropagation();
        newCanvasAgentSession(true);
        closeCanvasAgentHistory();
    });
    D("canvasAgentHistoryPanel").querySelectorAll('[data-agent-session]').forEach(btn => {
        btn.onclick = e => {
            e.preventDefault();
            e.stopPropagation();
            if(e.target.closest('[data-agent-session-delete]')) return;
            loadCanvasAgentSession(btn.dataset.agentSession || '');
        };
    });
    D("canvasAgentHistoryPanel").querySelectorAll('[data-agent-history-entry]').forEach(btn => {
        btn.onclick = async e => {
            e.preventDefault();
            e.stopPropagation();
            const raw = String(btn.dataset.agentHistoryEntry || '');
            const splitAt = raw.indexOf('::');
            if(splitAt <= 0) return;
            const targetCanvasId = raw.slice(0, splitAt);
            const targetSessionId = raw.slice(splitAt + 2);
            if(targetCanvasId && targetCanvasId !== String(D("canvasId") || '')){
                location.href = `/static/smart-canvas.html?id=${encodeURIComponent(targetCanvasId)}&agent_session=${encodeURIComponent(targetSessionId)}`;
                return;
            }
            loadCanvasAgentSession(targetSessionId);
        };
    });
    D("canvasAgentHistoryPanel").querySelectorAll('[data-agent-session-delete]').forEach(btn => {
        btn.onclick = e => {
            e.preventDefault();
            e.stopPropagation();
            deleteCanvasAgentSession(btn.dataset.agentSessionDelete || '');
        };
    });
    if(window.lucide) lucide.createIcons();
}
async function toggleCanvasAgentHistory(open=!D("canvasAgentHistoryOpen")){
    deps.setCanvasAgentHistoryOpen(Boolean(open));
    await renderCanvasAgentHistory();
    D("canvasAgentHistoryPanel")?.classList.toggle('open', D("canvasAgentHistoryOpen"));
}
async function loadCanvasAgentSession(id){
    await deps.loadCanvasAgentHistoryList();
    const item = deps.canvasAgentHistoryList().find(session => session.id === id);
    if(!item) return;
    await deps.persistCanvasAgentSession();
    deps.setCanvasAgentSessionId(item.id);
    deps.setCanvasAgentMessagesState(deps.restoreCanvasAgentActionPlans(deps.canvasAgentSerializableMessages(item.messages)));
    deps.setCanvasAgentLastReply(item.lastReply || [...canvasAgentMessagesState].reverse().find(msg => msg.role === 'assistant')?.text || '');
    deps.setCanvasAgentLastReplyRefs(item.lastReplyRefs || [...canvasAgentMessagesState].reverse().find(msg => msg.role === 'assistant')?.sourceRefs || []);
    deps.setCanvasAgentRefsState([]);
    deps.setCanvasAgentMentionPoolSnapshot([]); // 编号表随引用条一起清空
    deps.renderCanvasAgentRefs();
    deps.renderCanvasAgentMessages();
    closeCanvasAgentHistory();
}
async function deleteCanvasAgentSession(id){
    await deps.loadCanvasAgentHistoryList();
    deps.saveCanvasAgentHistoryList(deps.canvasAgentHistoryList().filter(item => item.id !== id));
    await deps.persistCanvasAgentHistoryStore();
    if(id === D("canvasAgentSessionId")) newCanvasAgentSession(false);
    await renderCanvasAgentHistory();
}
async function newCanvasAgentSession(saveCurrent=true){
    if(saveCurrent) await deps.persistCanvasAgentSession();
    deps.setCanvasAgentSessionId(deps.uid('agent_session'));
    deps.setCanvasAgentMessagesState([]);
    deps.setCanvasAgentRefsState([]);
    deps.setCanvasAgentMentionPoolSnapshot([]); // 编号表随引用条一起清空
    deps.setCanvasAgentLastReply('');
    deps.setCanvasAgentLastReplyRefs([]);
    if(D("canvasAgentInput")) D("canvasAgentInput").value = '';
    resizeCanvasAgentInput();
    deps.renderCanvasAgentRefs();
    deps.renderCanvasAgentMessages();
    closeCanvasAgentHistory();
}
function resizeCanvasAgentInput(){
    if(!D("canvasAgentInput")) return;
    D("canvasAgentInput").style.height = 'auto';
    D("canvasAgentInput").style.height = `${Math.min(130, Math.max(38, D("canvasAgentInput").scrollHeight))}px`;
}

    global.CanvasAgentSessionPanel = {
        configure,
        closeCanvasAgentHistory,
        renderCanvasAgentHistory,
        toggleCanvasAgentHistory,
        loadCanvasAgentSession,
        deleteCanvasAgentSession,
        newCanvasAgentSession,
        resizeCanvasAgentInput,
    };
})(typeof window !== 'undefined' ? window : this);

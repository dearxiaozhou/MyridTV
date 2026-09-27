/* Mounts Agent messages and binds their message, interaction, and quick-action controls. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    function messageFor(id){
        return deps.getMessages().find(message => message.id === id);
    }

    function stopEvent(event){
        event.preventDefault();
        event.stopPropagation();
    }

    function bindClick(root, selector, handler){
        root.querySelectorAll(selector).forEach(button => {
            button.onclick = event => {
                stopEvent(event);
                return handler(button, event);
            };
        });
    }

    function render(){
        const messagesEl = deps.getContainer();
        if(!messagesEl) return;
        const messages = deps.getMessages();
        const welcome = messagesEl.querySelector('.canvas-agent-welcome')?.outerHTML || deps.getWelcomeTemplate();
        const chosenMap = {};
        messages.forEach((message, index) => {
            if(message.role !== 'user' || !message.chosenId) return;
            for(let previousIndex = index - 1; previousIndex >= 0; previousIndex--){
                const previous = messages[previousIndex];
                if(previous.role === 'assistant' && previous.brainstormCard){
                    chosenMap[previous.id] = message.chosenId;
                    break;
                }
                if(previous.role === 'user') break;
            }
        });
        deps.setChosenMap(chosenMap);
        messagesEl.innerHTML = `${messages.length ? '' : welcome}${messages.map(deps.renderMessage).join('')}`;
        deps.refreshHeadTitle();

        bindClick(messagesEl, '[data-agent-preview-plan]', button => {
            const message = messageFor(button.dataset.agentPreviewPlan);
            deps.previewActionPlan(message?.actionPlan, message?.id);
        });
        bindClick(messagesEl, '[data-agent-run]', async button => {
            const message = messageFor(button.dataset.agentRun);
            if(message?.actionPlan && Array.isArray(message.actionPlan.steps) && message.actionPlan.steps.length){
                deps.previewActionPlan(message.actionPlan, message.id);
                return;
            }
            await deps.executeRecentNodes(button.dataset.agentRun);
        });
        bindClick(messagesEl, '[data-bs-pick]', button => deps.sendBrainstormChoice('pick', button.dataset.bsPick, button.dataset.bsTitle));
        bindClick(messagesEl, '[data-bs-refresh]', () => deps.sendBrainstormChoice('refresh'));
        bindClick(messagesEl, '[data-bs-run]', async button => deps.runBrainstormNodes(button.dataset.bsRun));
        bindClick(messagesEl, '[data-agent-copy]', button => deps.copyMessageText(button.dataset.agentCopy || ''));
        bindClick(messagesEl, '[data-agent-edit]', button => deps.editMessage(button.dataset.agentEdit || ''));
        bindClick(messagesEl, '[data-agent-edit-cancel]', () => deps.cancelEditMessage());
        bindClick(messagesEl, '[data-agent-edit-send]', button => {
            const box = button.closest('.canvas-agent-edit-box');
            const textarea = box?.querySelector('textarea[data-agent-editing-textarea]');
            deps.resendEditedMessage(button.dataset.agentEditSend || '', textarea?.value ?? '');
        });

        messagesEl.querySelectorAll('textarea[data-agent-editing-textarea]').forEach(textarea => {
            textarea.addEventListener('keydown', event => {
                if(event.key === 'Enter' && (event.ctrlKey || event.metaKey)){
                    event.preventDefault();
                    deps.resendEditedMessage(textarea.dataset.agentEditingTextarea || '', textarea.value);
                } else if(event.key === 'Escape'){
                    event.preventDefault();
                    deps.cancelEditMessage();
                }
                event.stopPropagation();
            });
        });

        bindClick(messagesEl, '[data-agent-quote]', button => deps.quoteMessageText(button.dataset.agentQuote || ''));
        bindClick(messagesEl, '[data-agent-locate]', button => deps.locateMessageNode(button.dataset.agentLocate || ''));
        bindClick(messagesEl, '[data-ic-select], [data-ic-submit]', button => {
            if(button.disabled) return;
            const cardId = String(button.dataset.icCard || '');
            const card = button.closest('.canvas-agent-ic');
            const intent = String(card?.dataset.icIntent || 'choose');
            const fields = {};
            if(intent === 'collect'){
                card.querySelectorAll('[data-ic-field]').forEach(field => {
                    fields[field.dataset.icField] = field.value;
                });
            }
            if(intent === 'choose'){
                card.querySelectorAll('.canvas-agent-ic-opt').forEach(option => option.classList.remove('selected'));
                button.classList.add('selected');
                const messageEl = button.closest('.canvas-agent-message');
                if(messageEl){
                    const message = messageFor(messageEl.dataset.agentMessageId);
                    if(message) message.chosenId = button.dataset.icSelect || '';
                }
            }
            deps.submitInteractionReceipt({
                card_id:cardId,
                intent,
                selection:button.dataset.icSelect || null,
                fields,
                confirmed:intent === 'confirm'
                    ? !/修改|调整|改一|重做|返工/i.test(String(button.dataset.icAction || '') + String(button.querySelector('.canvas-agent-ic-opt-label')?.textContent || ''))
                    : false
            });
        });

        bindClick(messagesEl, '[data-agent-suggest]', button => {
            const key = String(button.dataset.agentSuggest || '');
            const action = String(button.dataset.agentAction || '');
            const nodeId = String(button.dataset.agentNode || '');
            const messageId = String(button.dataset.agentMessage || '');
            if(!key) return;
            if(action === 'locate_node' && nodeId){
                deps.locateSpecificNode(nodeId, messageId);
                return;
            }
            const input = deps.getInput();
            if(input){
                input.value = `选${key}`;
                deps.resizeInput();
            }
            deps.sendMessage();
        });

        bindClick(messagesEl, '[data-agent-quick]', async button => {
            const action = String(button.dataset.agentQuick || '');
            const messageId = String(button.dataset.agentMessage || '');
            if(action === 'locate') return deps.locateMessageNode(messageId);
            if(action === 'undo'){
                const message = messageFor(messageId);
                const batchEntry = (Array.isArray(message?.toolTrace?.items) ? message.toolTrace.items : [])
                    .filter(item => item?.ok !== false && item?.batchId).pop();
                const batchId = String(button.dataset.agentBatch || '') || String(batchEntry?.batchId || '');
                if(!batchId){ deps.toast('未找到可撤销的操作批次'); return; }
                button.disabled = true;
                try {
                    const response = await deps.fetcher('/api/canvas-agent-undo-batch', {
                        method:'POST',
                        headers:{'Content-Type':'application/json'},
                        body:JSON.stringify({batch_id:batchId})
                    });
                    const data = await response.json();
                    if(!response.ok || data?.ok === false) throw new Error(data?.error || '撤销失败');
                    if(message) message.undone = true;
                    deps.renderAgain();
                    await deps.refreshAfterUndo();
                    deps.toast(`已撤销 ${data?.undone_ops ?? ''} 项操作`);
                } catch(error){
                    button.disabled = false;
                    deps.toast(`撤销失败：${error?.message || error}`);
                }
                return;
            }
            if(action === 'run') return deps.executeRecentNodes(messageId);
            if(action === 'create' || action === 'save_text'){
                const message = messageFor(messageId);
                if(message?.brainstormCard && Array.isArray(message.brainstormCard.candidates) && message.brainstormCard.candidates.length){
                    const created = deps.createBrainstormNodes(message.brainstormCard.candidates, '');
                    if(created.length) deps.toast(`已按 ${created.length} 个候选分别创建节点`);
                    return;
                }
                return deps.saveReplyAsTextNode(message?.text || '');
            }
            if(action === 'quote') return deps.quoteMessageText(messageId);
        });

        messagesEl.scrollTop = messagesEl.scrollHeight;
        deps.refreshIcons();
    }

    global.CanvasAgentMessageViewController = {configure, render};
})(typeof window !== 'undefined' ? window : globalThis);

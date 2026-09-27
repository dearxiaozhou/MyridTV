/* Canvas Agent skill manager: panel, editor, and skill CRUD. */
(function (global) {
    'use strict';

    var deps = {
        proxyBase: function () { return global.location ? global.location.origin : ''; },
        escapeHtml: function (value) {
            return String(value == null ? '' : value).replace(/[&<>"']/g, function (char) {
                return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char];
            });
        },
        toast: function () {},
        refreshIcons: function () {},
        confirm: function (message) { return global.confirm(message); }
    };
    var state = {
        config: { skills: [] },
        listLoadedAt: 0,
        managerOpen: false,
        editingName: '',
        editorLoadToken: 0
    };

    function configure(patch) { Object.assign(deps, patch || {}); }
    function apiUrl(path) {
        var base = String(deps.proxyBase ? deps.proxyBase() : '').replace(/\/$/, '');
        return base + path;
    }
    function element(id) { return global.document.getElementById(id); }
    function setEditingName(name) {
        state.editorLoadToken += 1;
        state.editingName = String(name || '');
    }

    async function loadList(force) {
        if (!force && state.config.skills.length && Date.now() - state.listLoadedAt < 5000) {
            return state.config.skills;
        }
        var response = await global.fetch(apiUrl('/api/canvas-agent-config?v=' + Date.now()), { cache: 'no-store' });
        if (!response.ok) return [];
        var data = await response.json();
        state.config = { skills: Array.isArray(data.skills) ? data.skills : [] };
        state.listLoadedAt = Date.now();
        return state.config.skills;
    }

    function renderList(skills) {
        var list = element('canvasAgentSkillList');
        if (!list) return;
        skills = Array.isArray(skills) ? skills : [];
        if (!skills.length) {
            list.innerHTML = '<div class="canvas-agent-skill-empty">还没有技能。<br>点右上角「新建」手动创建，或让 Agent 在对话中帮你保存。</div>';
            return;
        }
        list.innerHTML = skills.map(function (skill) {
            var name = String(skill && skill.name || '');
            var meta = [
                String(skill && skill.file || ''),
                skill && skill.size ? skill.size + ' 字节' : '',
                skill && skill.updatedAt ? new Date(skill.updatedAt).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : ''
            ].filter(Boolean).join(' · ');
            return '<div class="canvas-agent-skill-item" data-skill-name="' + deps.escapeHtml(name) + '">' +
                '<div class="canvas-agent-skill-item-main"><div class="canvas-agent-skill-item-name">@' + deps.escapeHtml(name) + '</div>' +
                (meta ? '<div class="canvas-agent-skill-item-meta">' + deps.escapeHtml(meta) + '</div>' : '') + '</div>' +
                '<div class="canvas-agent-skill-item-actions">' +
                '<button class="canvas-agent-skill-btn" type="button" data-skill-edit="' + deps.escapeHtml(name) + '"><i data-lucide="pencil" class="w-3 h-3"></i><span>编辑</span></button>' +
                '<button class="canvas-agent-skill-btn danger" type="button" data-skill-delete="' + deps.escapeHtml(name) + '"><i data-lucide="trash-2" class="w-3 h-3"></i><span>删除</span></button>' +
                '</div></div>';
        }).join('');

        list.querySelectorAll('[data-skill-edit]').forEach(function (button) {
            button.onclick = function (event) {
                event.preventDefault();
                event.stopPropagation();
                openEditor(button.dataset.skillEdit || '');
            };
        });
        list.querySelectorAll('[data-skill-delete]').forEach(function (button) {
            button.onclick = async function (event) {
                event.preventDefault();
                event.stopPropagation();
                var name = String(button.dataset.skillDelete || '');
                if (!name) return;
                if (button.dataset.arm === '1') {
                    try { await deleteByName(name); }
                    catch (error) { deps.toast(String(error && error.message || error)); }
                    return;
                }
                button.dataset.arm = '1';
                var label = button.querySelector('span');
                if (label) label.textContent = '确认删除？';
                button.classList.add('danger');
                global.setTimeout(function () {
                    button.dataset.arm = '';
                    if (label) label.textContent = '删除';
                    button.classList.remove('danger');
                }, 4000);
            };
        });
        deps.refreshIcons();
    }

    async function refreshList() {
        state.listLoadedAt = 0;
        var skills = await loadList(true);
        renderList(skills);
        return skills;
    }

    async function deleteByName(name) {
        name = String(name || '').trim();
        if (!name) return;
        var response = await global.fetch(apiUrl('/api/canvas-agent-skill'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, delete: true })
        });
        var data = await response.json().catch(function () { return {}; });
        if (!response.ok || data.ok === false) throw new Error(data.detail || '删除技能失败');
        deps.toast('技能 @' + name + ' 已删除');
        await refreshList();
        if (state.editingName === name) {
            var editor = element('canvasAgentSkillEditor');
            if (editor) editor.hidden = true;
            setEditingName('');
        }
    }

    async function open() {
        var panel = element('canvasAgentSkillPanel');
        if (!panel) return;
        state.managerOpen = true;
        panel.classList.add('open');
        try { renderList(await loadList(true)); }
        catch (error) {
            renderList(state.config.skills);
            deps.toast(String(error && error.message || '技能列表加载失败'));
        }
        var editor = element('canvasAgentSkillEditor');
        if (editor) editor.hidden = true;
        setEditingName('');
    }

    function close() {
        state.managerOpen = false;
        var panel = element('canvasAgentSkillPanel');
        if (panel) panel.classList.remove('open');
    }

    function openEditor(name) {
        setEditingName(name);
        var requestToken = state.editorLoadToken;
        var editor = element('canvasAgentSkillEditor');
        if (!editor) return;
        var nameInput = element('canvasAgentSkillName');
        var contentInput = element('canvasAgentSkillContent');
        var deleteButton = element('canvasAgentSkillDelete');
        if (nameInput) nameInput.value = state.editingName;
        if (contentInput) contentInput.value = '';
        if (deleteButton) deleteButton.style.display = state.editingName ? 'inline-flex' : 'none';
        if (state.editingName) {
            var editingName = state.editingName;
            global.fetch(apiUrl('/api/canvas-agent-skill?name=' + encodeURIComponent(editingName)), { cache: 'no-store' })
                .then(function (response) {
                    if (!response.ok) throw new Error('技能内容读取失败');
                    return response.json();
                })
                .then(function (data) {
                    if (requestToken !== state.editorLoadToken || editingName !== state.editingName || editor.hidden) return;
                    var content = data && data.skill && data.skill.content;
                    if (typeof content === 'string' && contentInput) contentInput.value = content;
                })
                .catch(function (error) {
                    if (requestToken === state.editorLoadToken && editingName === state.editingName) {
                        deps.toast(String(error && error.message || '技能内容读取失败'));
                    }
                });
        }
        editor.hidden = false;
        if (nameInput) nameInput.focus();
    }

    function cancelEditor() {
        var editor = element('canvasAgentSkillEditor');
        if (editor) editor.hidden = true;
        setEditingName('');
    }

    async function saveFromEditor() {
        var nameInput = element('canvasAgentSkillName');
        var contentInput = element('canvasAgentSkillContent');
        var name = String(nameInput && nameInput.value || '').trim();
        var content = String(contentInput && contentInput.value || '').trim();
        if (!name) { deps.toast('请输入技能名'); return; }
        if (!content) { deps.toast('请输入技能内容'); return; }
        var response = await global.fetch(apiUrl('/api/canvas-agent-skill'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, content: content })
        });
        var data = await response.json().catch(function () { return {}; });
        if (!response.ok || data.ok === false) throw new Error(data.detail || '保存技能失败');
        deps.toast('技能 @' + name + ' 已保存，对话中可用 @' + name + ' 调用');
        await refreshList();
        var editor = element('canvasAgentSkillEditor');
        if (editor) editor.hidden = true;
        setEditingName('');
    }

    async function deleteFromEditor() {
        var name = state.editingName;
        if (!name || !deps.confirm('确认删除技能 @' + name + '？')) return;
        await deleteByName(name);
    }

    global.CanvasAgentSkillManager = {
        configure: configure,
        isOpen: function () { return state.managerOpen; },
        open: open,
        close: close,
        openEditor: openEditor,
        cancelEditor: cancelEditor,
        saveFromEditor: saveFromEditor,
        deleteFromEditor: deleteFromEditor
    };
})(typeof window !== 'undefined' ? window : globalThis);

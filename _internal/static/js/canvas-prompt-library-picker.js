/* MyridTV 画布提示词库快捷面板（~ 键调出）
 *
 * 交互定稿（用户 2026-09-23，参考图）：
 * - 光标在提示词框内按 ~ → 下方弹出「提示词库」面板
 * - 面板只显示条目标题（一行一个，带书签图标），不显示正文/描述
 * - ~后继续输入 → 按标题包含过滤
 * - ↑↓ 移动高亮，Enter/点击 → 插入所选条目的 positive 全文；Esc/失焦关闭
 * - 底部「管理提示词库」行 → postMessage open-page 跳素材库的提示词库标签
 * 数据源 = GET /api/prompt-libraries（与素材管理页同一份库文件）。
 * 纯增量模块：主文件只挂钩子（keydown 一处、初始化一行），零行为改动到 @ 引用面板。
 */
(function (global) {
    'use strict';

    var deps = {
        promptInput: null,
        escapeHtml: null,
        tr: null
    };
    function configure(opts) {
        Object.assign(deps, opts || {});
    }

    var panel = null;
    var items = [];           // 扁平化后的全部条目 [{id,name,positive,negative,libraryName}]
    var filtered = [];
    var activeIndex = 0;
    var queryStart = -1;      // promptInput textContent 中 '~' 的位置（打开瞬间记录）
    var loading = false;
    var loadedOnce = false;

    function ensurePanel() {
        if (panel) return panel;
        panel = document.createElement('div');
        panel.className = 'prompt-lib-picker';
        panel.style.display = 'none';
        var row = deps.promptInput && deps.promptInput.closest('.prompt-row');
        (row || document.body).appendChild(panel);
        panel.addEventListener('mousedown', function (event) { event.preventDefault(); event.stopPropagation(); });
        panel.addEventListener('click', function (event) {
            var opt = event.target.closest('[data-plib-index]');
            if (opt) {
                event.preventDefault(); event.stopPropagation();
                chooseItem(Number(opt.dataset.plibIndex));
                return;
            }
            if (event.target.closest('[data-plib-manage]')) {
                event.preventDefault(); event.stopPropagation();
                close();
                try {
                    global.parent.postMessage({ type: 'open-page', page: 'asset-manager', tab: 'prompts' }, '*');
                } catch (_) {}
            }
        });
        return panel;
    }

    function loadLibrary(done) {
        if (loadedOnce && !done) { render(); return; }
        if (loading) return;
        loading = true;
        fetch('/api/prompt-libraries', { cache: 'no-store' })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var libs = (data && data.library && data.library.libraries) || [];
                var flat = [];
                libs.forEach(function (lib) {
                    (lib.items || []).forEach(function (item) {
                        if (!item || !item.id) return;
                        var positive = String(item.positive || '').trim();
                        if (!positive) return;
                        flat.push({
                            id: item.id,
                            name: String(item.name || '未命名'),
                            positive: positive,
                            negative: String(item.negative || '').trim(),
                            libraryId: lib.id || '',
                            libraryName: lib.name || ''
                        });
                    });
                });
                items = applyLibraryOverrides(flat);
                loadedOnce = true;
                loading = false;
                render();
                if (typeof done === 'function') done();
            })
            .catch(function () {
                loading = false;
                items = [];
                render();
            });
    }

    // 与旧页面提示词库同源：合并 localStorage 覆盖层（隐藏/编辑过的内置模板）
    // key 与 canvas.js CANVAS_PROMPT_TEMPLATE_OVERRIDES_KEY 一致；同域 iframe 共享 localStorage。
    function applyLibraryOverrides(flat) {
        var ov = { hiddenBuiltinIds: [], editedBuiltins: {} };
        try {
            var data = JSON.parse(global.localStorage.getItem('canvas_prompt_template_overrides') || '{}');
            ov = {
                hiddenBuiltinIds: Array.isArray(data.hiddenBuiltinIds) ? data.hiddenBuiltinIds : [],
                editedBuiltins: (data.editedBuiltins && typeof data.editedBuiltins === 'object') ? data.editedBuiltins : {}
            };
        } catch (_) {}
        var hidden = {};
        ov.hiddenBuiltinIds.forEach(function (id) { hidden[String(id)] = true; });
        var out = [];
        flat.forEach(function (it) {
            if (it.libraryId === 'system') {
                if (hidden[it.id]) return;
                var ed = ov.editedBuiltins[it.id];
                if (ed) {
                    it = Object.assign({}, it);
                    if (ed.name) it.name = String(ed.name);
                    if (ed.positive != null) it.positive = String(ed.positive || '').trim();
                    if (ed.negative != null) it.negative = String(ed.negative || '').trim();
                    if (!it.positive) return;
                }
            }
            out.push(it);
        });
        return out;
    }

    function currentQuery() {
        if (queryStart < 0) return '';
        var text = (deps.promptInput.textContent || '');
        return text.slice(queryStart + 1);
    }

    function applyFilter() {
        var q = currentQuery().trim().toLowerCase();
        filtered = q ? items.filter(function (it) { return it.name.toLowerCase().includes(q); }) : items.slice();
        if (activeIndex >= filtered.length) activeIndex = Math.max(0, filtered.length - 1);
    }

    function render() {
        if (!panel || panel.style.display === 'none') return;
        applyFilter();
        if (!filtered.length) {
            panel.innerHTML = '<div class="prompt-lib-empty">没有匹配的提示词<br><span>按 Esc 关闭</span></div>';
            return;
        }
        panel.innerHTML =
            '<div class="prompt-lib-head">提示词库</div>' +
            '<div class="prompt-lib-list">' +
            filtered.map(function (it, i) {
                return '<button type="button" class="prompt-lib-item' + (i === activeIndex ? ' active' : '') + '" data-plib-index="' + i + '">' +
                    '<i data-lucide="bookmark"></i><span>' + deps.escapeHtml(it.name) + '</span></button>';
            }).join('') +
            '</div>' +
            '<button type="button" class="prompt-lib-manage" data-plib-manage="1"><i data-lucide="settings-2"></i><span>管理提示词库</span></button>';
        if (global.lucide) global.lucide.createIcons({ attrs: {}, nameAttr: 'data-lucide' });
        var active = panel.querySelector('.prompt-lib-item.active');
        if (active) active.scrollIntoView({ block: 'nearest' });
    }

    function positionPanel() {
        var inputRect = deps.promptInput.getBoundingClientRect();
        var row = deps.promptInput.closest('.prompt-row');
        var rowRect = (row || deps.promptInput).getBoundingClientRect();
        var scale = 1;
        try { scale = (global.viewport && Number(global.viewport.scale)) || 1; } catch (_) {}
        if (!(scale > 0)) scale = 1;
        panel.style.left = ((inputRect.left - rowRect.left) / scale) + 'px';
        panel.style.top = 'calc(100% + 4px)';
    }

    function open() {
        if (!deps.promptInput) return;
        ensurePanel();
        queryStart = (deps.promptInput.textContent || '').length; // ~ 已被输入，位置在 ~ 处
        // 记录 ~ 的位置：光标当前在 ~ 之后一位
        var text = deps.promptInput.textContent || '';
        queryStart = Math.max(0, text.length - 1);
        // 若 ~ 不在文本末尾（罕见：粘贴带~），不弹
        if (text.slice(queryStart, queryStart + 1) !== '~') { close(); return; }
        activeIndex = 0;
        panel.style.display = 'block';
        positionPanel();
        loadLibrary();
    }

    function close(opts) {
        if (!panel) return;
        // 把提示词框里 '~查询' 的临时文字保留或擦除：擦除策略=用户没选择就删掉 ~ 及输入的词
        var keepTyped = opts && opts.keepTyped;
        if (!keepTyped && queryStart >= 0) {
            var text = deps.promptInput.textContent || '';
            var removed = text.slice(0, queryStart);
            try {
                deps.promptInput.textContent = removed;
                // 触发 input 让既有链路（placeholder 状态、保存）刷新
                deps.promptInput.dispatchEvent(new Event('input', { bubbles: true }));
                placeCaretEnd(removed.length);
            } catch (_) {}
        }
        queryStart = -1;
        panel.style.display = 'none';
    }

    function placeCaretEnd(pos) {
        try {
            var range = document.createRange();
            range.selectNodeContents(deps.promptInput);
            var walker = document.createTreeWalker(deps.promptInput, NodeFilter.SHOW_TEXT, null);
            var n, acc = 0, target = Math.max(0, pos);
            while ((n = walker.nextNode())) {
                var len = (n.textContent || '').length;
                if (acc + len >= target) { range.setStart(n, target - acc); range.collapse(true); break; }
                acc += len;
            }
            var sel = global.getSelection();
            sel.removeAllRanges(); sel.addRange(range);
        } catch (_) {}
    }

    function chooseItem(index) {
        var item = filtered[index];
        if (!item) return;
        // 删除 '~查询' 后插入正文（与参考图"选模板填入提示词"一致）
        if (queryStart >= 0) {
            deps.promptInput.textContent = (deps.promptInput.textContent || '').slice(0, queryStart);
        }
        queryStart = -1;
        var posText = item.positive;
        var negText = item.negative ? ('\n\n' + item.negative) : '';
        var node = document.createTextNode(posText + negText);
        deps.promptInput.appendChild(node);
        deps.promptInput.focus();
        placeCaretEnd((deps.promptInput.textContent || '').length);
        deps.promptInput.dispatchEvent(new Event('input', { bubbles: true }));
        panel.style.display = 'none';
    }

    // ---- 主文件钩子 ----
    // keydown 返回 true = 本模块已消费该按键，主链不要继续处理
    function handleKeydown(event) {
        var input = deps.promptInput;
        if (!input) return false;
        var isOpen = panel && panel.style.display !== 'none';
        if (!isOpen) return false;
        var key = String(event.key || '');
        if (key === 'ArrowDown') { activeIndex = Math.min(filtered.length - 1, activeIndex + 1); render(); return true; }
        if (key === 'ArrowUp') { activeIndex = Math.max(0, activeIndex - 1); render(); return true; }
        if (key === 'Enter') { chooseItem(activeIndex); return true; }
        if (key === 'Escape') { close(); return true; }
        if (key === ' ') {
            if (!currentQuery().trim()) { close(); return true; }
            return false;
        }
        if (key === 'Backspace' && queryStart >= 0 && currentQuery().length === 0) {
            close(); return true;
        }
        return false;
    }
    // 面板打开时每次输入刷新过滤
    function handleInput() {
        if (panel && panel.style.display !== 'none' && queryStart >= 0) render();
    }
    function isOpen() { return Boolean(panel && panel.style.display !== 'none'); }

    global.CanvasPromptLibPicker = {
        configure: configure,
        open: open,
        close: close,
        isOpen: isOpen,
        handleKeydown: handleKeydown,
        handleInput: handleInput
    };
})(typeof window !== 'undefined' ? window : globalThis);

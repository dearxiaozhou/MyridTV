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
    var repositionHooked = false;
    var repositionHooks = null;

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
            positionPanel();
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
        // 边打字边跟着光标走：~多机位 每多一个字符光标右移，菜单跟着右移。
        positionPanel();
    }

    // 把 promptInput 的纯文本偏移映射成一个 Range（用来量光标/字符位置）。
    // promptInput 是 contenteditable，里面可能有多段文本节点，得靠 TreeWalker 累加。
    // offset 落在某个字符上 → 返回包住该字符的 Range；落在末尾 → 返回折叠在末尾的 Range。
    function rangeAtTextOffset(input, offset) {
        try {
            var walker = document.createTreeWalker(input, NodeFilter.SHOW_TEXT, null);
            var n, acc = 0, target = Math.max(0, offset | 0);
            var range = document.createRange();
            while ((n = walker.nextNode())) {
                var len = (n.textContent || '').length;
                if (acc + len > target) { range.setStart(n, target - acc); range.setEnd(n, target - acc + 1); return range; }
                if (acc + len === target) { range.setStart(n, len); range.collapse(true); return range; }
                acc += len;
            }
            range.selectNodeContents(input);
            range.collapse(false);
            return range;
        } catch (_) { return null; }
    }

    // 光标所在的纯文本偏移（把 selection 的 DOM 位置翻译成字符下标）。
    function caretTextOffset(input) {
        try {
            var sel = global.getSelection();
            if (!sel || !sel.rangeCount) return -1;
            var range = sel.getRangeAt(0);
            if (!input.contains(range.startContainer)) return -1;
            var pre = document.createRange();
            pre.selectNodeContents(input);
            pre.setEnd(range.startContainer, range.startOffset);
            return pre.toString().length;
        } catch (_) { return -1; }
    }

    // 取光标在视口坐标里的矩形。
    // ⚠️ 血泪：光标常常落在**元素层**（例如 selectNodeContents 后 collapse 到末尾，
    // startContainer 是 DIV 而不是文本节点），Chromium/WebView2 对这种折叠 range
    // **不返回任何 client rect**（getClientRects 为空、boundingRect 全 0）。
    // 所以主路量不到时必须退化到「量光标前一个字符」——它的右边缘就是光标 x。
    // 这里不能用 queryStart（~ 的位置）来量：那是个固定坐标，边打字边过滤时
    // 菜单会停在 ~ 那里不动（实测光标走了 105px 而菜单只跟了 5px）。
    function caretClientRect(input) {
        try {
            var sel = global.getSelection();
            if (sel && sel.rangeCount) {
                var range = sel.getRangeAt(0);
                if (input.contains(range.startContainer)) {
                    var collapsed = range.cloneRange();
                    collapsed.collapse(true);
                    var rects = collapsed.getClientRects();
                    for (var i = 0; i < rects.length; i++) {
                        if (rects[i] && rects[i].height) return rects[i];
                    }
                    var box = collapsed.getBoundingClientRect();
                    if (box && box.height) return box;
                }
            }
        } catch (_) {}

        // 退化一：量光标前一个字符（offset-1 .. offset），其右边缘 = 光标位置。
        var off = caretTextOffset(input);
        if (off > 0) {
            var probe = rangeAtTextOffset(input, off - 1);
            var r = probe && probe.getBoundingClientRect();
            if (r && r.height) {
                return { left: r.right, right: r.right, top: r.top, bottom: r.bottom, width: 0, height: r.height };
            }
        }
        // 退化二：光标在首字符之前（offset 0）→ 量第一个字符，取其左边缘。
        if (off === 0) {
            var first = rangeAtTextOffset(input, 0);
            var fr = first && first.getBoundingClientRect();
            if (fr && fr.height) {
                return { left: fr.left, right: fr.left, top: fr.top, bottom: fr.bottom, width: 0, height: fr.height };
            }
        }
        // 退化三：连 selection 都读不到（面板刚开、焦点还没落定）→ 退回 ~ 的位置。
        if (queryStart >= 0) {
            var q = rangeAtTextOffset(input, queryStart);
            var qr = q && q.getBoundingClientRect();
            if (qr && qr.height) {
                return { left: qr.right, right: qr.right, top: qr.top, bottom: qr.bottom, width: 0, height: qr.height };
            }
        }
        return null;
    }

    // 面板跟着光标走（2026-10-05：原来固定贴输入框左下角，改成从光标处弹出）。
    // 先在视口坐标里算好「贴光标、别越出输入框、别出视口」的位置，再换算成
    // .prompt-row 内的布局坐标（composer 上有 transform:scale，所以要除以 scale）。
    function positionPanel() {
        if (!panel || !deps.promptInput) return;
        var input = deps.promptInput;
        var row = input.closest('.prompt-row');
        var rowRect = (row || input).getBoundingClientRect();
        var scale = 1;
        try { scale = (global.viewport && Number(global.viewport.scale)) || 1; } catch (_) {}
        if (!(scale > 0)) scale = 1;

        var caret = caretClientRect(input);
        if (!caret) {   // 量不到光标 → 沿用旧的「贴左下角」
            panel.style.left = '8px';
            panel.style.top = 'calc(100% + 4px)';
            return;
        }

        var inputRect = input.getBoundingClientRect();
        var panelW = (panel.offsetWidth || 300) * scale;
        var panelH = (panel.offsetHeight || 240) * scale;
        var vw = global.innerWidth || document.documentElement.clientWidth;
        var vh = global.innerHeight || document.documentElement.clientHeight;
        var GAP = 2, PAD = 8;

        // 横向：默认光标 x；顶到输入框右边界就往左让（不越出输入框），最后兜一次视口。
        var left = caret.left;
        var maxLeft = Math.max(inputRect.left, inputRect.right - panelW);
        if (left > maxLeft) left = maxLeft;
        if (left < inputRect.left) left = inputRect.left;
        if (left + panelW > vw - PAD) left = Math.max(PAD, vw - PAD - panelW);

        // 纵向：默认光标下一行；下方塞不下就翻到光标上方。
        var top = caret.bottom + GAP;
        if (top + panelH > vh - PAD) {
            var above = caret.top - GAP - panelH;
            top = above >= PAD ? above : Math.max(PAD, vh - PAD - panelH);
        }
        if (top < PAD) top = PAD;

        panel.style.left = ((left - rowRect.left) / scale) + 'px';
        panel.style.top = ((top - rowRect.top) / scale) + 'px';
    }

    // 输入框滚动 / 窗口缩放时光标在视口里的位置会变，面板得跟上。
    // 只在面板打开期间挂监听，close 时摘掉，避免常驻开销。
    function bindRepositionHooks() {
        if (repositionHooked || !deps.promptInput) return;
        repositionHooked = true;
        var onScroll = function () { if (isOpen()) positionPanel(); };
        deps.promptInput.addEventListener('scroll', onScroll, { passive: true });
        global.addEventListener('resize', onScroll);
        repositionHooks = { input: deps.promptInput, fn: onScroll };
    }

    function unbindRepositionHooks() {
        if (!repositionHooks) return;
        try {
            repositionHooks.input.removeEventListener('scroll', repositionHooks.fn);
            global.removeEventListener('resize', repositionHooks.fn);
        } catch (_) {}
        repositionHooks = null;
        repositionHooked = false;
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
        bindRepositionHooks();
        loadLibrary();
        // loadLibrary 命中缓存时会同步 render（内部已定位）；首次拉库是异步的，
        // 这儿先按空内容定位一次，render() 拿到真实尺寸后会再校正。
        positionPanel();
    }

    function close(opts) {
        if (!panel) return;
        unbindRepositionHooks();
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
        unbindRepositionHooks();
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

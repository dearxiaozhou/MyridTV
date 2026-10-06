/* 提示词节点输入框快捷插入面板（~ 提示词库 / / 技能）
 *
 * 需求（2026-10-05 老王）：LLM 节点的输入区按 ~ 调提示词库、按 / 调技能，
 * 技能弹窗的样式和提示词库完全一致（复用 .prompt-lib-* 一套 class）。
 *
 * 与底部 composer 的 CanvasPromptLibPicker 的分工：
 * - 那个绑死在 contenteditable 的 #promptInput 上，只认 ~，面板是 absolute 贴 .prompt-row；
 * - 这个绑在节点里的 <textarea> 上（.prompt-node-text / .prompt-llm-instruction /
 *   .prompt-llm-system），面板挂 document.body + position:fixed，靠镜像 div 量光标，
 *   不受 #world 的 transform:scale 和节点裁剪影响。
 *
 * 数据源：提示词库 GET /api/prompt-libraries；技能列表 GET /api/canvas-agent-config，
 * 正文 GET /api/canvas-agent-skill?name=xxx（列表接口只给名字/大小/时间，正文要单独取）。
 *
 * 触发规则：
 * - ~ / ～：任何时候都触发（正文里不会出现 ~，不用怕误伤）
 * - / / ／：只在行首或前一个字符是空白时触发——"16/9" 这种词中间的斜杠不是要调技能
 */
(function (global) {
    'use strict';

    var deps = {
        escapeHtml: function (value) { return String(value == null ? '' : value); },
        toast: function () {},
        tr: function (key) { return key; }
    };
    function configure(patch) { Object.assign(deps, patch || {}); }
    function esc(value) {
        try { return deps.escapeHtml(value); }
        catch (_) { return String(value == null ? '' : value); }
    }

    var panel = null;
    var field = null;
    var mode = '';              // 'lib' | 'skill'
    var triggerChar = '';       // 实际落入文本的触发符（~ ～ / ／，handleInput 靠它判存亡）
    var triggerPos = -1;        // 触发符(~ 或 /)在 value 里的下标
    var items = [];
    var filtered = [];
    var activeIndex = 0;
    var libCache = null;        // {at, items}
    var skillCache = null;      // {at, items}
    var loadToken = 0;
    var repositionHooked = false;
    var repositionTarget = null;

    var LIB_TTL = 60000;
    var SKILL_TTL = 30000;

    // ---------- 面板骨架 ----------
    function ensurePanel() {
        // 面板可能被别的代码（节点重渲染、清理脚本）摘出 DOM：缓存的是游离节点就再挂回去，
        // 否则 panel.style/display 改了也看不见，且渲染全发生在文档外。
        if (panel) {
            if (!panel.isConnected) document.body.appendChild(panel);
            return panel;
        }
        panel = document.createElement('div');
        panel.className = 'prompt-lib-picker prompt-node-picker is-float';
        panel.style.display = 'none';
        document.body.appendChild(panel);
        // 别让画布抢走 mousedown（会触发 pan/清选中），也别让输入框失焦
        panel.addEventListener('mousedown', function (event) { event.preventDefault(); event.stopPropagation(); });
        panel.addEventListener('click', function (event) {
            var opt = event.target.closest('[data-npp-index]');
            if (opt) {
                event.preventDefault(); event.stopPropagation();
                choose(Number(opt.dataset.nppIndex));
                return;
            }
            if (event.target.closest('[data-npp-manage]')) {
                event.preventDefault(); event.stopPropagation();
                manage();
            }
        });
        // 画布 wheel 是缩放：面板自己滚，不能冒上去
        panel.addEventListener('wheel', function (event) { event.stopPropagation(); }, { passive: true });
        panel.addEventListener('contextmenu', function (event) { event.stopPropagation(); });
        return panel;
    }

    function isOpen() { return Boolean(panel && panel.style.display !== 'none'); }

    // ---------- 取值/光标 ----------
    function value() { return field ? String(field.value || '') : ''; }
    function caret() {
        if (!field) return 0;
        var pos = field.selectionStart;
        return pos == null ? value().length : pos;
    }
    function queryText() {
        if (triggerPos < 0) return '';
        var c = caret();
        if (c < triggerPos) return '';
        return value().slice(triggerPos + 1, c);
    }

    // ---------- 数据源 ----------
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
                    if (ed.positive != null) it.text = String(ed.positive || '').trim();
                    if (!it.text) return;
                }
            }
            out.push(it);
        });
        return out;
    }

    function loadPromptLib(done) {
        if (libCache && Date.now() - libCache.at < LIB_TTL) {
            items = applyLibraryOverrides(libCache.items);
            done();
            return;
        }
        global.fetch('/api/prompt-libraries', { cache: 'no-store' })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var libs = (data && data.library && data.library.libraries) || [];
                var flat = [];
                libs.forEach(function (lib) {
                    (lib.items || []).forEach(function (it) {
                        if (!it || !it.id) return;
                        var positive = String(it.positive || '').trim();
                        if (!positive) return;
                        flat.push({
                            id: String(it.id),
                            name: String(it.name || '未命名'),
                            text: positive,
                            libraryId: String(lib.id || '')
                        });
                    });
                });
                libCache = { at: Date.now(), items: flat };
                items = applyLibraryOverrides(flat);
                done();
            })
            .catch(function () { items = []; done(); });
    }

    function loadSkills(done) {
        if (skillCache && Date.now() - skillCache.at < SKILL_TTL) {
            items = skillCache.items.slice();
            done();
            return;
        }
        global.fetch('/api/canvas-agent-config?v=' + Date.now(), { cache: 'no-store' })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var list = Array.isArray(data && data.skills) ? data.skills : [];
                var flat = [];
                list.forEach(function (s) {
                    var name = String((s && s.name) || '').trim();
                    if (!name) return;
                    flat.push({ id: name, name: name, size: s.size || 0, updatedAt: s.updatedAt || 0 });
                });
                skillCache = { at: Date.now(), items: flat };
                items = flat.slice();
                done();
            })
            .catch(function () { items = []; done(); });
    }

    function fetchSkillContent(name) {
        return global.fetch('/api/canvas-agent-skill?name=' + encodeURIComponent(name), { cache: 'no-store' })
            .then(function (r) { return r.json(); })
            .then(function (data) { return String((data && data.skill && data.skill.content) || '').trim(); })
            .catch(function () { return ''; });
    }

    // ---------- @技能名 → 正文（运行期展开） ----------
    // 单独拉一次列表，不复用面板的 items：展开可能在面板没打开时发生，
    // 共用那个数组会把正在显示的列表冲掉。
    function fetchSkillNames() {
        return global.fetch('/api/canvas-agent-config?v=' + Date.now(), { cache: 'no-store' })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var list = Array.isArray(data && data.skills) ? data.skills : [];
                return list.map(function (s) { return String((s && s.name) || '').trim(); }).filter(Boolean);
            })
            .catch(function () { return []; });
    }

    function skillMentionsInText(text) {
        var found = String(text || '').match(/@([A-Za-z0-9_\-\u4e00-\u9fa5]+)/g) || [];
        var out = [];
        found.forEach(function (raw) {
            var name = raw.slice(1);
            if (out.indexOf(name) < 0) out.push(name);
        });
        return out;
    }

    // 输入框里躺的是 @名称，这里换成技能正文再送出去。
    // 只认技能库里真实存在的名字——普通文本里的 @某人 不会被误伤。
    function expandSkillMentions(text, opts) {
        var src = String(text || '');
        var names = skillMentionsInText(src);
        if (!names.length) return Promise.resolve(src);
        return fetchSkillNames()
            .then(function (known) {
                var valid = names.filter(function (n) { return known.indexOf(n) >= 0; });
                if (!valid.length) return src;
                return Promise.all(valid.map(function (name) {
                    return fetchSkillContent(name).then(function (body) { return { name: name, body: body }; });
                })).then(function (entries) {
                    var out = src;
                    var missing = [];
                    entries.forEach(function (entry) {
                        if (!entry.body) { missing.push(entry.name); return; }
                        // 同一个技能被引用多次时只展开一次，后面重复的 @名 直接丢掉
                        // ——否则同一份几千字的技能正文会被重复喂给模型。
                        var parts = out.split('@' + entry.name);
                        out = parts[0] + entry.body + parts.slice(1).join('');
                    });
                    if (missing.length && opts && typeof opts.onMissing === 'function') opts.onMissing(missing);
                    return out;
                });
            })
            .catch(function () { return src; });
    }

    // ---------- 渲染 ----------
    function applyFilter() {
        var q = queryText().trim().toLowerCase();
        filtered = q ? items.filter(function (it) { return String(it.name || '').toLowerCase().indexOf(q) >= 0; }) : items.slice();
        if (activeIndex >= filtered.length) activeIndex = Math.max(0, filtered.length - 1);
    }

    function render() {
        if (!panel || !isOpen()) return;
        applyFilter();
        var isSkill = mode === 'skill';
        if (!filtered.length) {
            panel.innerHTML = '<div class="prompt-lib-empty">' +
                (isSkill ? '没有匹配的技能' : '没有匹配的提示词') +
                '<br><span>按 Esc 关闭</span></div>';
            positionPanel();
            return;
        }
        var icon = isSkill ? 'sparkles' : 'bookmark';
        panel.innerHTML =
            '<div class="prompt-lib-head">' + (isSkill ? '技能' : '提示词库') + '</div>' +
            '<div class="prompt-lib-list">' +
            filtered.map(function (it, i) {
                return '<button type="button" class="prompt-lib-item' + (i === activeIndex ? ' active' : '') +
                    '" data-npp-index="' + i + '"><i data-lucide="' + icon + '"></i><span>' + esc(it.name) + '</span></button>';
            }).join('') +
            '</div>' +
            '<button type="button" class="prompt-lib-manage" data-npp-manage="1"><i data-lucide="settings-2"></i><span>' +
            (isSkill ? '管理技能' : '管理提示词库') + '</span></button>';
        if (global.lucide) global.lucide.createIcons({ attrs: {}, nameAttr: 'data-lucide' });
        var active = panel.querySelector('.prompt-lib-item.active');
        if (active) active.scrollIntoView({ block: 'nearest' });
        positionPanel();
    }

    // textarea 没有 contenteditable 那样的 Range，用镜像 div 量光标：
    // 复制排版样式 + 同宽，把光标前文本塞进去，末尾挂个 marker span 量它的位置。
    // 节点在 #world 里被 transform:scale，所以镜像整体 scale(rect.width/offsetWidth)，
    // 再用「marker 相对镜像左上角的偏移」换算，避免去猜 viewport.scale 是多少。
    function caretRect() {
        if (!field || !field.isConnected) return null;
        var rect = field.getBoundingClientRect();
        var layoutW = field.offsetWidth || 0;
        var scale = layoutW ? (rect.width / layoutW) : 1;
        if (!(scale > 0)) scale = 1;
        var cs = global.getComputedStyle(field);
        var mirror = document.createElement('div');
        var props = ['boxSizing', 'borderTopWidth', 'borderRightWidth', 'borderBottomWidth', 'borderLeftWidth',
            'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft', 'fontStyle', 'fontVariant', 'fontWeight',
            'fontStretch', 'fontSize', 'fontFamily', 'lineHeight', 'letterSpacing', 'wordSpacing', 'textTransform',
            'textIndent', 'tabSize', 'wordBreak', 'overflowWrap'];
        mirror.style.position = 'absolute';
        mirror.style.left = '0px';
        mirror.style.top = '0px';
        mirror.style.visibility = 'hidden';
        mirror.style.pointerEvents = 'none';
        mirror.style.whiteSpace = 'pre-wrap';
        mirror.style.wordWrap = 'break-word';
        mirror.style.overflowWrap = 'break-word';
        props.forEach(function (p) { try { mirror.style[p] = cs[p]; } catch (_) {} });
        mirror.style.boxSizing = 'border-box';
        mirror.style.width = layoutW + 'px';
        var text = value();
        var pos = caret();
        mirror.textContent = text.slice(0, pos);
        var marker = document.createElement('span');
        marker.textContent = text.slice(pos) || '.';
        mirror.appendChild(marker);
        document.body.appendChild(mirror);
        mirror.style.transformOrigin = '0 0';
        mirror.style.transform = 'scale(' + scale + ')';
        var mRect = mirror.getBoundingClientRect();
        var sRect = marker.getBoundingClientRect();
        var lineH = (parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) || 16) * scale;
        try { document.body.removeChild(mirror); } catch (_) {}
        if (!sRect || (!sRect.height && !sRect.width)) return null;
        var x = rect.left + (sRect.left - mRect.left) - (field.scrollLeft || 0) * scale;
        var y = rect.top + (sRect.top - mRect.top) - (field.scrollTop || 0) * scale;
        var h = sRect.height || lineH;
        return { left: x, right: x, top: y, bottom: y + h, height: h, width: 0 };
    }

    function positionPanel() {
        if (!panel || !field) return;
        var rect = field.getBoundingClientRect();
        var caretBox = caretRect();
        var vw = global.innerWidth || document.documentElement.clientWidth;
        var vh = global.innerHeight || document.documentElement.clientHeight;
        var w = panel.offsetWidth || 300;
        var h = panel.offsetHeight || 200;
        var PAD = 8, GAP = 3;

        var x = caretBox ? caretBox.left : rect.left;
        var y = caretBox ? caretBox.bottom + GAP : rect.bottom + GAP;
        if (x + w > vw - PAD) x = Math.max(PAD, vw - PAD - w);
        if (x < PAD) x = PAD;
        if (y + h > vh - PAD) {                     // 下方塞不下 → 翻到光标上方
            var above = (caretBox ? caretBox.top : rect.top) - GAP - h;
            y = above >= PAD ? above : Math.max(PAD, vh - PAD - h);
        }
        if (y < PAD) y = PAD;
        panel.style.left = x + 'px';
        panel.style.top = y + 'px';
    }

    function bindRepositionHooks() {
        if (repositionHooked || !field) return;
        repositionHooked = true;
        var fn = function () { if (isOpen()) positionPanel(); };
        field.addEventListener('scroll', fn, { passive: true });
        global.addEventListener('resize', fn);
        repositionTarget = { field: field, fn: fn };
    }
    function unbindRepositionHooks() {
        if (!repositionTarget) return;
        try {
            repositionTarget.field.removeEventListener('scroll', repositionTarget.fn);
            global.removeEventListener('resize', repositionTarget.fn);
        } catch (_) {}
        repositionTarget = null;
        repositionHooked = false;
    }

    // ---------- 文本写入（走 execCommand 保住原生撤销栈） ----------
    // ⚠️ execCommand 有个坑：文档没拿到焦点时它照样返回 true，但一个字都没插进去
    // （无头/后台窗口、程序化 focus 都可能踩到）。所以写完必须回读校验，没变就退回
    // setRangeText——宁可丢一步撤销栈，也不能让触发符消失导致面板定位到错误的下标。
    function selectionRange() {
        var s = field.selectionStart == null ? 0 : field.selectionStart;
        var e = field.selectionEnd == null ? s : field.selectionEnd;
        return { start: s, end: e };
    }
    function replaceSelection(text) {
        if (!field) return false;
        text = String(text == null ? '' : text);
        var before = value();
        var range = selectionRange();
        var ok = false;
        try { ok = global.document.execCommand('insertText', false, text); } catch (_) { ok = false; }
        // 插入成功 = 值变了（插入空串时看选区是否塌缩）
        var changed = text ? value() !== before : (selectionRange().start === selectionRange().end);
        if (!ok || !changed) {
            var r = selectionRange();
            try { field.setRangeText(text, r.start, r.end, 'end'); } catch (_) {}
            field.dispatchEvent(new global.Event('input', { bubbles: true }));
        }
        return true;
    }
    function deleteSelection() {
        if (!field) return false;
        var before = value();
        var ok = false;
        try { ok = global.document.execCommand('delete'); } catch (_) { ok = false; }
        var r0 = selectionRange();
        var changed = value() !== before || r0.start === r0.end;
        if (!ok || !changed) {
            var r = selectionRange();
            try { field.setRangeText('', r.start, r.end, 'end'); } catch (_) {}
            field.dispatchEvent(new global.Event('input', { bubbles: true }));
        }
        return true;
    }

    // ---------- 开/关/选 ----------
    function open() {
        if (!field) return;
        ensurePanel();
        panel.style.display = 'block';
        bindRepositionHooks();
        items = [];
        filtered = [];
        render();
        var token = ++loadToken;
        var done = function () {
            if (token !== loadToken || !isOpen() || !field || !field.isConnected) return;
            activeIndex = 0;
            render();
        };
        if (mode === 'lib') loadPromptLib(done);
        else loadSkills(done);
    }

    function hide() {
        unbindRepositionHooks();
        if (panel) panel.style.display = 'none';
        field = null;
        mode = '';
        triggerChar = '';
        triggerPos = -1;
    }

    function close(opts) {
        var strip = Boolean(opts && opts.strip);
        var target = field;
        if (strip && target && triggerPos >= 0) {
            var c = caret();
            if (c > triggerPos) {
                try { target.focus(); target.setSelectionRange(triggerPos, c); deleteSelection(); } catch (_) {}
            }
        }
        hide();
    }

    // 技能：输入框里**只写 @名称**（与提示词框调用风格 @名 同一套语义），
    // 正文不进输入框——技能文档动辄几千字，塞进来既没法读也没法编辑。
    // 真正送模型前由 expandSkillMentions 展开（见 runPromptLLMNode）。
    function choose(index) {
        var item = filtered[index];
        if (!item || !field) return;
        var apply = function (text) {
            var target = field;
            if (!target || !target.isConnected) { hide(); return; }
            var c = caret();
            if (triggerPos < 0 || c < triggerPos) { hide(); return; }
            try { target.focus(); target.setSelectionRange(triggerPos, c); } catch (_) {}
            replaceSelection(String(text || ''));
            hide();
        };
        if (mode === 'skill') {
            apply('@' + item.name);
            try { deps.toast('已引用技能 @' + item.name + '（运行时展开正文）'); } catch (_) {}
            return;
        }
        apply(item.text || '');
    }

    function manage() {
        var tab = mode === 'skill' ? 'skills' : 'prompts';
        close({ strip: false });
        try { global.parent.postMessage({ type: 'open-page', page: 'asset-manager', tab: tab }, '*'); } catch (_) {}
    }

    // ---------- 按键 ----------
    function handleInput() {
        if (!isOpen() || !field) return;
        var text = value();
        if (triggerPos < 0 || text.charAt(triggerPos) !== triggerChar) { hide(); return; }
        render();
    }

    function handleKeydown(event) {
        if (!event) return false;
        var el = event.currentTarget || event.target;
        if (!el || (el.tagName !== 'TEXTAREA' && el.tagName !== 'INPUT')) return false;

        if (isOpen() && field === el) {
            var key = String(event.key || '');
            if (key === 'ArrowDown') { activeIndex = Math.min(filtered.length - 1, activeIndex + 1); render(); return true; }
            if (key === 'ArrowUp') { activeIndex = Math.max(0, activeIndex - 1); render(); return true; }
            if (key === 'Enter' || key === 'Tab') { choose(activeIndex); return true; }
            if (key === 'Escape') { close({ strip: true }); return true; }
            if (key === 'Backspace' && queryText().length === 0) { close({ strip: false }); return false; } // 让默认删除吃掉触发符
            if (key === ' ' && !queryText().trim()) { close({ strip: true }); return true; }
            return false;
        }

        if (event.ctrlKey || event.metaKey || event.altKey) return false;
        if (el.readOnly || el.disabled) return false;
        var ch = String(event.key || '');
        var isTilde = (ch === '~' || ch === '～');
        var isSlash = (ch === '/' || ch === '／');
        if (!isTilde && !isSlash) return false;

        var pos = el.selectionStart == null ? String(el.value || '').length : el.selectionStart;
        if (isSlash) {   // 词中间的 / 不是要调技能（16/9、正/侧 之类）
            var prev = pos > 0 ? String(el.value || '').charAt(pos - 1) : '';
            if (pos > 0 && prev && !/\s/.test(prev)) return false;
        }

        event.preventDefault();
        event.stopPropagation();
        if (isOpen()) close({ strip: false });
        field = el;
        mode = isTilde ? 'lib' : 'skill';
        triggerChar = ch;
        try { el.focus(); } catch (_) {}
        replaceSelection(ch);                       // 让触发符真的进到文本里（并触发 input 保存）
        triggerPos = caret() - 1;
        if (value().charAt(triggerPos) !== ch) { hide(); return true; }
        activeIndex = 0;
        open();
        return true;
    }

    function attach(el) {
        if (!el || el.dataset.nppBound === '1') return;
        el.dataset.nppBound = '1';
        el.addEventListener('keydown', function (event) {
            if (handleKeydown(event)) {
                event.preventDefault();
                event.stopPropagation();
            }
        });
        el.addEventListener('input', function () { handleInput(); });
        el.addEventListener('blur', function () { if (isOpen() && field === el) close({ strip: false }); });
    }

    // 面板外点一下就收（capture 阶段：面板自己的 mousedown 已经 preventDefault+stop 过了，
    // 但 capture 先跑，所以这里按 target 判断，别把自己关掉）
    global.document.addEventListener('mousedown', function (event) {
        if (!isOpen()) return;
        var target = event.target;
        if (target && target.closest && target.closest('.prompt-node-picker')) return;
        if (target === field) { close({ strip: false }); return; }
        close({ strip: true });
    }, true);

    global.CanvasNodePromptPicker = {
        configure: configure,
        attach: attach,
        close: function () { close({ strip: false }); },
        isOpen: isOpen,
        expandSkillMentions: expandSkillMentions
    };
})(typeof window !== 'undefined' ? window : globalThis);

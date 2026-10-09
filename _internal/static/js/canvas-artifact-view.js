/* MyridTV 画布产物视图层（拆模块 ④-3：Artifact Sidebar / Viewer / Conversation chrome / 事件绑定）
 *
 * Phase 8/9 产物 UI：Sidebar 一级列表、Viewer 打开/正文渲染（markdown 安全子集/表格）、
 * Section·Item 导航 chrome、加入画布（scope 幂等复用）、引用回 Agent、重命名/删除/清空、
 * 会话种子标题、侧栏与 Viewer 全部事件绑定（configure 后显式 bindEvents()）。
 * 数据层在 canvas-artifact-model.js（Model 直连）；状态所有权在画布主文件，经 deps 注入读写。
 */
(function (global) {
    'use strict';

    var Model = global.CanvasArtifactModel;

    var deps = {
        getArtifacts: null, setArtifacts: null,
        getActiveArtifactId: null, setActiveArtifactId: null,
        getActiveSectionId: null, setActiveSectionId: null,
        getActiveItemId: null, setActiveItemId: null,
        getSelectedId: null, setSelectedId: null,
        getNodes: null, getRefs: null, getMessages: null,
        render: null, scheduleSave: null, escapeHtml: null,
        artifactTypeLabel: null, artifactTypeMeta: null,
        createTextNode: null, screenCenterForNewNode: null,
        newCanvasAgentSession: null, renderCanvasAgentRefs: null
    };
    function configure(opts) {
        Object.assign(deps, opts || {});
    }

function renderArtifactSidebar(){
    const list = document.getElementById('canvasAgentArtifactList');
    const empty = document.getElementById('canvasAgentArtifactEmpty');
    const bar = document.getElementById('canvasAgentArtifactSidebar');
    const clearBtn = document.getElementById('canvasAgentArtifactsClear');
    if(!list) return;

    // Phase 9：一级条目 = Conversation Artifact（一轮完整讨论） + 普通文档。
    // Section / Item 永远是某个 Conversation 的内部层级，绝不上升为一级条目。
    const all = (deps.getArtifacts() || []).filter(a => a && a.id);
    const convs = all.filter(a => a.kind === 'conversation' || (Array.isArray(a.sections) && a.sections.length));
    const docs  = all.filter(a => !(a.kind === 'conversation' || (Array.isArray(a.sections) && a.sections.length)));

    if(bar) bar.classList.toggle('has-content', all.length > 0);
    if(empty) empty.hidden = all.length > 0;
    if(clearBtn) clearBtn.hidden = all.length === 0;

    const itemHtml = (a) => {
        const meta = deps.artifactTypeMeta(a.artifactType);
        const active = a.id === deps.getActiveArtifactId() ? ' active' : '';
        const secs = Array.isArray(a.sections) ? a.sections : [];
        const count = secs.length
            ? '<span class="canvas-agent-artifact-item-count">' + secs.length + '</span>'
            : '';
        return '<button type="button" class="canvas-agent-artifact-item' + active + '" data-artifact-id="' + deps.escapeHtml(a.id) + '" title="' + deps.escapeHtml(a.title) + '">'
            + '<i data-lucide="' + deps.escapeHtml(meta.icon) + '"></i>'
            + '<span class="canvas-agent-artifact-item-name">' + deps.escapeHtml(a.title) + '</span>'
            + count
            + '<span class="canvas-agent-artifact-item-badge">' + deps.escapeHtml(meta.label) + '</span>'
            + '</button>';
    };
    const groupHtml = (label, arr) => {
        if(!arr.length) return '';
        return '<div class="canvas-agent-artifact-group"><span class="canvas-agent-artifact-group-label">' + deps.escapeHtml(label) + '</span></div>'
            + arr.map(itemHtml).join('');
    };

    const html = groupHtml('Brainstorm', convs) + groupHtml('Documents', docs);
    list.innerHTML = html || '';
    list.querySelectorAll('[data-artifact-id]').forEach(btn => {
        btn.onclick = () => openArtifact(btn.dataset.artifactId);
    });
    if(window.lucide) window.lucide.createIcons();
}
function toggleArtifactSidebar(force){
    const bar = document.getElementById('canvasAgentArtifactSidebar');
    if(!bar) return;
    const next = (typeof force === 'boolean') ? force : bar.hidden;
    bar.hidden = !next;
    // 头部开关图标随状态切换：打开→panel-left-close(点击收起)，关闭→panel-left-open
    const toggleBtn = document.getElementById('canvasAgentFilesToggle');
    if(toggleBtn){
        const icon = toggleBtn.querySelector('i[data-lucide]');
        if(icon) icon.setAttribute('data-lucide', next ? 'panel-left-close' : 'panel-left-open');
        if(window.lucide) window.lucide.createIcons();
    }
}
function openArtifact(id, opts){
    const a = Model.findArtifact(id);
    if(!a) return;
    const _o = opts || {};
    deps.setActiveArtifactId(id);
    // Phase 9：进入 Conversation 时定位到它的 Section / Item（不跳 Sidebar、不新建 Panel）
    deps.setActiveSectionId((_o.sectionId !== undefined) ? (_o.sectionId || '') : Model.defaultSectionId(a));
    deps.setActiveItemId((_o.itemId !== undefined) ? (_o.itemId || '') : Model.defaultItemId(a, deps.getActiveSectionId()));
    toggleArtifactSidebar(true);
    renderArtifactSidebar();
    const viewer = document.getElementById('canvasAgentArtifactViewer');
    if(!viewer) return;
    viewer.hidden = false;
    const badge = document.getElementById('canvasAgentAvTypeBadge');
    const titleInput = document.getElementById('canvasAgentAvTitle');
    const meta = document.getElementById('canvasAgentAvMeta');
    const body = document.getElementById('canvasAgentAvBody');
    if(badge) badge.textContent = deps.artifactTypeLabel(a.artifactType);
    if(titleInput){ titleInput.value = a.title || ''; titleInput.readOnly = true; }
    if(meta){
        const when = new Date(Number(a.updatedAt || Date.now())).toLocaleString();
        meta.textContent = (a.canvasNodeId ? '已在画布 · ' : '') + 'v' + (Number(a.version || 1)) + ' · 更新于 ' + when;
    }
    if(body) body.innerHTML = renderArtifactContent(a);
    renderConversationChrome(a);   // Phase 9：Section 下拉 + Item Tabs
    if(window.lucide) window.lucide.createIcons();
}
function closeArtifactViewer(){
    const viewer = document.getElementById('canvasAgentArtifactViewer');
    if(viewer) viewer.hidden = true;
    deps.setActiveArtifactId('');
    renderArtifactSidebar();
}
function renderArtifactContent(a){
    if(!a) return '<div class="canvas-agent-md"><p></p></div>';
    // Phase 9：Conversation Artifact 按当前 Section / Item 取内容；老扁平产物仍取 a.content
    const sec = Model.activeSectionOf(a);
    if(sec){
        const it = Model.activeItemOf(sec);
        const raw = (it && String(it.content || '').trim())
            ? String(it.content || '')
            : Model.flattenSectionContent(sec);
        return renderArtifactBodyByType(a.artifactType, raw);
    }
    return renderArtifactBodyByType(a.artifactType, String(a.content || ''));
}
function renderArtifactBodyByType(type, raw){
    const t = String(type || '').trim().toLowerCase();
    if(t === 'csv' || t === 'table') return renderArtifactTable(raw, t === 'csv');
    if(t === 'html' || t === 'interactive'){
        return '<div class="canvas-agent-md"><pre><code>' + deps.escapeHtml(raw) + '</code></pre></div>';
    }
    return renderMarkdownSafe(raw);
}
function renderMarkdownSafe(raw){
    const esc = deps.escapeHtml(String(raw || ''));
    const lines = esc.split('\n');
    const out = [];
    let inList = false;
    let inCode = false;
    let para = [];
    const flushPara = () => {
        if(para.length){ out.push('<p>' + inlineMd(para.join('<br>')) + '</p>'); para = []; }
    };
    const closeList = () => { if(inList){ out.push('</ul>'); inList = false; } };
    for(const line of lines){
        if(/^\s*```/.test(line)){ flushPara(); closeList(); inCode = !inCode; out.push(inCode ? '<pre><code>' : '</code></pre>'); continue; }
        if(inCode){ out.push(line + '\n'); continue; }
        const h = line.match(/^(#{1,4})\s+(.*)$/);
        if(h){ flushPara(); closeList(); const lv = h[1].length; out.push('<h' + lv + '>' + inlineMd(h[2]) + '</h' + lv + '>'); continue; }
        if(/^\s*([-*+])\s+(.*)$/.test(line)){
            flushPara();
            if(!inList){ out.push('<ul>'); inList = true; }
            out.push('<li>' + inlineMd(line.replace(/^\s*[-*+]\s+/, '')) + '</li>');
            continue;
        }
        if(/^\s*(\d+)\.\s+(.*)$/.test(line)){
            flushPara(); closeList();
            out.push('<p>' + inlineMd(line.replace(/^\s*\d+\.\s+/, '')) + '</p>');
            continue;
        }
        if(/^\s*(---|\*\*\*)\s*$/.test(line)){ flushPara(); closeList(); out.push('<hr>'); continue; }
        if(!line.trim()){ flushPara(); closeList(); continue; }
        closeList();
        para.push(line);
    }
    flushPara(); closeList();
    return '<div class="canvas-agent-md">' + (out.join('') || '<p></p>') + '</div>';
}
function inlineMd(s){
    return String(s || '')
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        .replace(/(^|\s)\*([^*]+)\*/g, '$1<em>$2</em>');
}
function canvasAgentArtifactTranscript(refs){
    const list = (refs || []).filter(r => r && r.artifactId);
    if(!list.length) return '';
    return list.map(r => {
        const a = Model.findArtifact(r.artifactId);
        if(!a) return '';
        const sid = String(r.artifactSectionId || '');
        const iid = String(r.artifactItemId || '');
        const sec = sid ? (a.sections || []).find(s => String(s.id || '') === sid) : null;
        const it  = (sec && iid) ? (sec.items || []).find(x => String(x.id || '') === iid) : null;

        // Phase 9：引用到 Item 就只发 Item，引用到 Section 就只发 Section。
        // Agent 因此只会改林澜，不会顺手重写整轮 Brainstorm（需求第十八/二十九条）。
        let scopeTag = 'conversation';
        let body = Model.flattenConversationContent(a) || String(a.content || '');
        let path = String(a.title || '');
        if(sec){
            scopeTag = 'section';
            path += ' / ' + String(sec.title || '');
            body = Model.flattenSectionContent(sec);
        }
        if(it){
            scopeTag = 'section_item';
            path += ' / ' + String(it.title || '(条目)');
            body = String(it.content || '');
        }
        return '\n\n=== \u5f15\u7528\u4ea7\u7269\uff1a' + path +
               ' (artifactId=' + String(a.id) +
               (sec ? ', sectionId=' + String(sec.id) : '') +
               (it ? ', itemId=' + String(it.id) : '') +
               ', scope=' + scopeTag +
               ', type=' + String(a.artifactType || 'text') + ') ===\n' +
               body +
               '\n\n[\u4fee\u6539\u7ea6\u675f] \u53ea\u5141\u8bb8\u4fee\u6539\u4e0a\u8ff0 scope \u8303\u56f4\u5185\u7684\u5185\u5bb9\uff1b'
               '\u4e0d\u8981\u6539\u5199\u5176\u4ed6\u5206\u7c7b\u3001\u5176\u4ed6\u6761\u76ee\u6216\u5176\u4ed6 Brainstorm\uff0c\u4e5f\u4e0d\u8981\u65b0\u5efa\u4ea7\u7269\u3002';
    }).join('');
}
function renderArtifactTable(raw, isCsv){
    const rows = String(raw || '').split('\n').filter(l => l.trim().length).map(l => isCsv ? l.split(',') : l.split('|').filter(c => c.trim() !== ''));
    if(!rows.length) return '<div class="canvas-agent-md"><p></p></div>';
    const head = rows[0];
    let html = '<div class="canvas-agent-md"><table><thead><tr>';
    head.forEach(c => { html += '<th>' + inlineMd(deps.escapeHtml(String(c).trim())) + '</th>'; });
    html += '</tr></thead><tbody>';
    rows.slice(1).forEach(r => {
        if(!isCsv && /^[\s:-]+$/.test(r.join(''))) return;
        html += '<tr>' + r.map(c => '<td>' + inlineMd(deps.escapeHtml(String(c).trim())) + '</td>').join('') + '</tr>';
    });
    html += '</tbody></table></div>';
    return html;
}
function artifactNodeDropSpot(){
    try{
        const list = (typeof deps.getNodes() !== 'undefined' && Array.isArray(deps.getNodes()) && deps.getNodes().length) ? deps.getNodes() : [];
        if(list.length){
            let maxX = -Infinity, minY = Infinity;
            list.forEach(function(n){
                maxX = Math.max(maxX, Number(n && n.x || 0) + Number(n && n.w || 316));
                minY = Math.min(minY, Number(n && n.y || 0));
            });
            if(isFinite(maxX) && isFinite(minY)) return {x: maxX + 40, y: minY};
        }
        const vp = (typeof viewport === 'object' && viewport) ? viewport : null;
        if(vp) return {x: Number(vp.x || 0) + 240, y: Number(vp.y || 0) + 160};
    }catch(e){}
    return {x:0, y:0};
}
function addArtifactToCanvas(id, opts){
    const a = Model.findArtifact(id);
    if(!a) return null;
    const o = opts || {};
    const scope = o.scope || Model.currentArtifactScope();
    const sec = (scope === 'conversation') ? null : Model.activeSectionOf(a);
    const it  = (scope === 'item') ? Model.activeItemOf(sec) : null;

    const key = artifactScopeKey(scope, sec, it);
    a.canvasNodeIds = (a.canvasNodeIds && typeof a.canvasNodeIds === 'object') ? a.canvasNodeIds : {};
    const prevId = (scope === 'conversation') ? (a.canvasNodeId || a.canvasNodeIds[key]) : a.canvasNodeIds[key];
    if(prevId && deps.getNodes().some(n => n.id === prevId)){
        deps.setSelectedId(prevId); deps.render(); return prevId;
    }

    const label = artifactScopeLabel(a, scope, sec, it);
    const text  = artifactScopeText(a, scope, sec, it);
    if(!String(text || '').trim()) return null;

    const center = deps.screenCenterForNewNode ? deps.screenCenterForNewNode() : artifactNodeDropSpot();
    const node = deps.createTextNode(center.x, center.y, {
        skipUndo:false, select:true,
        title: label,
        text: text
    });
    if(!node) return null;
    // 身份关系：Node 只是 Artifact 某个 scope 的 Canvas Representation（需求第十四条）
    node.artifactId = a.id;
    node.artifactScope = scope;
    node.artifactSectionId = sec ? String(sec.id || '') : '';
    node.artifactItemId = it ? String(it.id || '') : '';
    node.__origin = 'artifact_sidebar';
    node.role = 'text';
    node.status = 'ready';
    a.canvasNodeIds[key] = node.id;
    if(scope === 'conversation') a.canvasNodeId = node.id;
    a.updatedAt = Date.now();
    renderArtifactSidebar();
    deps.scheduleSave();
    deps.setSelectedId(node.id);
    deps.render();
    return node.id;
}
function artifactScopeKey(scope, sec, it){
    if(scope === 'conversation') return 'conversation';
    if(scope === 'item' && it) return 'item:' + String(it.id || '');
    if(sec) return 'section:' + String(sec.id || '');
    return 'conversation';
}
function artifactScopeLabel(a, scope, sec, it){
    const base = String(a.title || deps.artifactTypeLabel(a.artifactType) || '产物');
    if(scope === 'conversation') return base;
    if(scope === 'item' && it) return base + ' · ' + String(sec?.title || '') + ' · ' + String(it.title || '');
    if(sec) return base + ' · ' + String(sec.title || '');
    return base;
}
function artifactScopeText(a, scope, sec, it){
    if(scope === 'item' && it) return String(it.content || '');
    if(sec) return Model.flattenSectionContent(sec);
    return Model.flattenConversationContent(a) || String(a.content || '');
}
function referenceArtifactInAgent(id, opts){
    const a = Model.findArtifact(id);
    if(!a) return false;
    const o = opts || {};
    const scope = o.scope || Model.currentArtifactScope();
    const sec = (scope === 'conversation') ? null : Model.activeSectionOf(a);
    const it  = (scope === 'item') ? Model.activeItemOf(sec) : null;
    const sid = sec ? String(sec.id || '') : '';
    const iid = it ? String(it.id || '') : '';
    // Phase 9：引用必须带 scope，Agent 才知道讨论的是整轮对话 / 某个分类 / 某个人物
    const exists = (deps.getRefs() || []).some(r => r && r.artifactId === a.id
        && String(r.artifactSectionId || '') === sid && String(r.artifactItemId || '') === iid);
    if(!exists){
        deps.getRefs().push({
            url:'artifact:' + a.id + (sid ? ('/' + sid) : '') + (iid ? ('/' + iid) : ''),
            nodeId:a.canvasNodeId || '',
            name: artifactScopeLabel(a, scope, sec, it),
            kind:'artifact', artifactId:a.id, artifactType:a.artifactType,
            artifactScope: scope, artifactSectionId: sid, artifactItemId: iid
        });
        deps.renderCanvasAgentRefs();
    }
    const panel = document.getElementById('canvasAgentPanel');
    if(panel && !panel.classList.contains('open')) panel.classList.add('open');
    const input = document.getElementById('canvasAgentInput');
    if(input) input.focus();
    return true;
}
function renameArtifact(id, title){
    const a = Model.findArtifact(id);
    if(!a) return false;
    const t = String(title || '').trim();
    if(!t) return false;
    a.title = t;              // 只改 title，不动 artifactId（需求第二十五条）
    a.updatedAt = Date.now();
    renderArtifactSidebar();
    const titleInput = document.getElementById('canvasAgentAvTitle');
    if(titleInput) titleInput.value = t;
    const meta = document.getElementById('canvasAgentAvMeta');
    if(meta){
        const when = new Date(Number(a.updatedAt || Date.now())).toLocaleString();
        meta.textContent = (a.canvasNodeId ? '已在画布 · ' : '') + 'v' + (Number(a.version || 1)) + ' · 更新于 ' + when;
    }
    deps.scheduleSave();
    return true;
}
function deleteArtifact(id){
    const a = Model.findArtifact(id);
    if(!a) return false;
    // 需求第二十六条：若同时存在 Canvas Node，只取消 Sidebar 呈现，不删 Node
    if(a.canvasNodeId && deps.getNodes().some(n => n.id === a.canvasNodeId)){
        a.canvasNodeId = '';
        a.updatedAt = Date.now();
    } else {
        deps.setArtifacts(deps.getArtifacts().filter(x => x && x.id !== id));
    }
    if(deps.getActiveArtifactId() === id) closeArtifactViewer();
    renderArtifactSidebar();
    deps.scheduleSave();
    return true;
}
function clearCanvasAgentArtifacts(){
    if(!deps.getArtifacts().length) return;
    // 有已加入画布的节点则不动节点本身，只清空 Sidebar 呈现与引用关系
    for(const a of deps.getArtifacts()){
        if(a && a.canvasNodeId) a.canvasNodeId = '';
    }
    deps.setArtifacts([]);
    closeArtifactViewer();
    renderArtifactSidebar();
    deps.scheduleSave();
}
function newBrainstormConversation(){
    if(deps.newCanvasAgentSession) deps.newCanvasAgentSession(true);
    const bar = document.getElementById('canvasAgentArtifactSidebar');
    if(bar) bar.hidden = false;
    const input = document.getElementById('canvasAgentInput');
    if(input) input.focus();
}
function canvasAgentConversationSeedTitle(){
    try{
        const list = deps.getMessages() || [];
        for(let i = 0; i < list.length; i += 1){
            const m = list[i];
            if(m && m.role === 'user' && String(m.text || '').trim()){
                return String(m.text || '').trim().replace(/\s+/g, ' ').slice(0, 30);
            }
        }
    }catch(e){}
    return '';
}
function setArtifactScope(scope){
    localStorage.setItem('myridtv.artifact.scope', String(scope || 'section'));
    const label = document.getElementById('canvasAgentAvScopeLabel');
    if(label) label.textContent = '添加到画布';
}
function renderConversationChrome(a){
    const bar = document.getElementById('canvasAgentAvSectionBar');
    const tabs = document.getElementById('canvasAgentAvItemTabs');
    if(!bar || !tabs) return;
    const viewer = document.getElementById('canvasAgentArtifactViewer');
    const secs = Model.artifactSections(a);
    // conv-mode：Conversation 容器走图2/图3 的干净布局（← 标题 / Section 下拉 / Tabs），
    // 隐藏旧阅读器的徽章/重命名/加入画布/继续修改；旧扁平文档保持原样。
    if(viewer) viewer.classList.toggle('conv-mode', secs.length > 0);
    const titleText = document.getElementById('canvasAgentAvTitleText');
    if(titleText) titleText.textContent = String(a.title || '');
    if(!secs.length){ bar.hidden = true; tabs.hidden = true; tabs.innerHTML = ''; return; }

    bar.hidden = false;
    const sec = Model.activeSectionOf(a);
    const label = document.getElementById('canvasAgentAvSectionLabel');
    if(label) label.textContent = String(sec?.title || '全部分类');

    const menu = document.getElementById('canvasAgentAvSectionMenu');
    if(menu){
        menu.innerHTML = secs.map(s => {
            const meta = sectionTypeMeta(s.type);
            const on = sec && String(s.id || '') === String(sec.id || '') ? ' selected' : '';
            const n = Model.sectionItems(s).length;
            return '<button type="button" class="canvas-agent-av-option' + on + '" data-section-id="' + deps.escapeHtml(String(s.id || '')) + '" role="option">'
                + '<i data-lucide="' + deps.escapeHtml(meta.icon) + '"></i>'
                + '<span>' + deps.escapeHtml(String(s.title || '')) + '</span>'
                + (n > 1 ? '<em>' + n + ' 项</em>' : '')
                + '</button>';
        }).join('');
        menu.querySelectorAll('[data-section-id]').forEach(btn => {
            btn.onclick = e => {
                e.preventDefault(); e.stopPropagation();
                selectArtifactSection(btn.dataset.sectionId);
            };
        });
    }

    // Item Tabs：只在 Section 内存在具名条目时出现（核心人物 -> 林澜 | 司徒岳）
    const items = Model.sectionItems(sec);
    const showTabs = items.length > 1 || (items.length === 1 && String(items[0].title || '').trim());
    if(!showTabs){ tabs.hidden = true; tabs.innerHTML = ''; setArtifactScope(Model.currentArtifactScope()); return; }
    tabs.hidden = false;
    const cur = Model.activeItemOf(sec);
    tabs.innerHTML = items.map(it => {
        const on = cur && String(it.id || '') === String(cur.id || '') ? ' active' : '';
        return '<button type="button" class="canvas-agent-av-itemtab' + on + '" data-item-id="' + deps.escapeHtml(String(it.id || '')) + '">'
            + deps.escapeHtml(String(it.title || '(条目)')) + '</button>';
    }).join('');
    tabs.querySelectorAll('[data-item-id]').forEach(btn => {
        btn.onclick = e => {
            e.preventDefault(); e.stopPropagation();
            deps.setActiveItemId(btn.dataset.itemId || '');
            const art = Model.findArtifact(deps.getActiveArtifactId());
            if(art){ openArtifactBodyOnly(art); }
        };
    });
    setArtifactScope(Model.currentArtifactScope());
}
function selectArtifactSection(sid){
    const a = Model.findArtifact(deps.getActiveArtifactId());
    if(!a) return;
    deps.setActiveSectionId(String(sid || ''));
    deps.setActiveItemId(Model.defaultItemId(a, deps.getActiveSectionId()));
    closeArtifactSectionMenu();
    openArtifactBodyOnly(a);
}
function openArtifactBodyOnly(a){
    const body = document.getElementById('canvasAgentAvBody');
    if(body) body.innerHTML = renderArtifactContent(a);
    renderConversationChrome(a);
    if(window.lucide) window.lucide.createIcons();
}
function closeArtifactSectionMenu(){
    const menu = document.getElementById('canvasAgentAvSectionMenu');
    const btn = document.getElementById('canvasAgentAvSectionBtn');
    if(menu) menu.hidden = true;
    if(btn) btn.setAttribute('aria-expanded', 'false');
}
function closeArtifactScopeMenu(){
    const menu = document.getElementById('canvasAgentAvScopeMenu');
    const btn = document.getElementById('canvasAgentAvScopeBtn');
    if(menu) menu.hidden = true;
    if(btn) btn.setAttribute('aria-expanded', 'false');
}
function updateArtifactItemContent(artifactId, sectionId, itemId, content){
    const a = Model.findArtifact(artifactId);
    if(!a) return false;
    const sec = Model.findSectionOf(a, sectionId);
    if(!sec) return false;
    const item = Model.sectionItems(sec).find(x => String(x.id || '') === String(itemId || ''));
    if(!item) return false;
    item.content = String(content || '');
    item.updatedAt = Date.now();
    sec.updatedAt = Date.now();
    a.updatedAt = Date.now();
    a.content = Model.flattenConversationContent(a);
    if(document.getElementById('canvasAgentArtifactViewer') && !document.getElementById('canvasAgentArtifactViewer').hidden
        && deps.getActiveArtifactId() === artifactId){
        openArtifactBodyOnly(a);
    }
    renderArtifactSidebar();
    deps.scheduleSave();
    return true;
}

    /* 事件绑定：原主文件尾部两个 IIFE，configure 注入完成后由 bindEvents() 显式触发 */
    var eventsBound = false;
    function bindEvents(){
        if(eventsBound) return;
        eventsBound = true;
(function(){
    const filesToggle = document.getElementById('canvasAgentFilesToggle');
    if(filesToggle) filesToggle.addEventListener('click', e => {
        e.preventDefault(); e.stopPropagation();
        toggleArtifactSidebar();
    });
    const collapse = document.getElementById('canvasAgentArtifactsCollapse');
    if(collapse) collapse.addEventListener('click', e => {
        e.preventDefault(); e.stopPropagation();
        toggleArtifactSidebar(false);
    });
    const clearBtn = document.getElementById('canvasAgentArtifactsClear');
    if(clearBtn) clearBtn.addEventListener('click', e => {
        e.preventDefault(); e.stopPropagation();
        clearCanvasAgentArtifacts();
    });
    const closeBtn = document.getElementById('canvasAgentAvClose');
    if(closeBtn) closeBtn.addEventListener('click', e => {
        e.preventDefault(); e.stopPropagation();
        closeArtifactViewer();
    });
    const addBtn = document.getElementById('canvasAgentAvAddCanvas');
    if(addBtn) addBtn.addEventListener('click', e => {
        e.preventDefault(); e.stopPropagation();
        if(!deps.getActiveArtifactId()) return;
        addArtifactToCanvas(deps.getActiveArtifactId());
        closeArtifactViewer();
    });
    const contBtn = document.getElementById('canvasAgentAvContinue');
    if(contBtn) contBtn.addEventListener('click', e => {
        e.preventDefault(); e.stopPropagation();
        if(!deps.getActiveArtifactId()) return;
        referenceArtifactInAgent(deps.getActiveArtifactId());
        closeArtifactViewer();
    });
    const renameBtn = document.getElementById('canvasAgentAvRename');
    if(renameBtn) renameBtn.addEventListener('click', e => {
        e.preventDefault(); e.stopPropagation();
        const input = document.getElementById('canvasAgentAvTitle');
        if(!input) return;
        if(input.readOnly){
            input.readOnly = false;
            input.focus();
            input.select();
            return;
        }
        if(renameArtifact(deps.getActiveArtifactId(), input.value)){
            input.readOnly = true;
            input.blur();
        }
    });
    const titleInput = document.getElementById('canvasAgentAvTitle');
    if(titleInput) titleInput.addEventListener('keydown', e => {
        if(e.key === 'Enter'){
            e.preventDefault();
            if(renameArtifact(deps.getActiveArtifactId(), titleInput.value)){
                titleInput.readOnly = true;
                titleInput.blur();
            }
        } else if(e.key === 'Escape'){
            e.preventDefault();
            const a = Model.findArtifact(deps.getActiveArtifactId());
            titleInput.value = a ? (a.title || '') : '';
            titleInput.readOnly = true;
            titleInput.blur();
        }
    });
})();
(function(){
    // 返回：收起 Viewer，回到 Sidebar 一级列表（需求第五条：Section 是内部导航）
    const backBtn = document.getElementById('canvasAgentAvBack');
    if(backBtn) backBtn.addEventListener('click', e => {
        e.preventDefault(); e.stopPropagation();
        closeArtifactViewer();
    });
    // 讨论：把当前选中内容（scope 感知）作为上下文放进输入框，由用户补充指令后发送
    const discussBtn = document.getElementById('canvasAgentAvDiscuss');
    if(discussBtn) discussBtn.addEventListener('click', e => {
        e.preventDefault(); e.stopPropagation();
        const a = Model.findArtifact(deps.getActiveArtifactId());
        if(!a) return;
        const sec = Model.activeSectionOf(a);
        const it = Model.activeItemOf(sec);
        const scope = Model.currentArtifactScope();
        const summary = artifactScopeText(a, scope, sec, it);
        if(!summary) return;
        const input = document.getElementById('canvasAgentInput');
        if(!input) return;
        const head = '[讨论引用 · ' + a.title + (sec ? (' / ' + sec.title) : '') + (it && it.title ? (' / ' + it.title) : '') + ']\n'
            + summary.slice(0, 2000) + '\n[引用结束]\n';
        input.value = head + input.value;
        input.focus();
        try { input.setSelectionRange(input.value.length, input.value.length); } catch(_e){}
    });
    const secBtn = document.getElementById('canvasAgentAvSectionBtn');
    if(secBtn) secBtn.addEventListener('click', e => {
        e.preventDefault(); e.stopPropagation();
        const menu = document.getElementById('canvasAgentAvSectionMenu');
        if(!menu) return;
        const next = menu.hidden;
        closeArtifactScopeMenu();
        menu.hidden = !next;
        secBtn.setAttribute('aria-expanded', next ? 'true' : 'false');
    });
    const scopeBtn = document.getElementById('canvasAgentAvScopeBtn');
    if(scopeBtn) scopeBtn.addEventListener('click', e => {
        e.preventDefault(); e.stopPropagation();
        const menu = document.getElementById('canvasAgentAvScopeMenu');
        if(!menu) return;
        const next = menu.hidden;
        closeArtifactSectionMenu();
        menu.hidden = !next;
        scopeBtn.setAttribute('aria-expanded', next ? 'true' : 'false');
    });
    (document.getElementById('canvasAgentAvScopeMenu') || document.createElement('div'))
        .querySelectorAll('[data-scope]').forEach(btn => {
            btn.onclick = e => {
                e.preventDefault(); e.stopPropagation();
                setArtifactScope(btn.dataset.scope);
                closeArtifactScopeMenu();
                if(deps.getActiveArtifactId()) addArtifactToCanvas(deps.getActiveArtifactId(), {scope: btn.dataset.scope});
            };
        });
    document.addEventListener('click', e => {
        if(e.target.closest('#canvasAgentAvSectionBar')) return;
        closeArtifactSectionMenu();
        closeArtifactScopeMenu();
    }, true);
})();
    }

    global.CanvasArtifactView = {
        configure: configure,
        bindEvents: bindEvents,
        renderArtifactSidebar: renderArtifactSidebar,
        toggleArtifactSidebar: toggleArtifactSidebar,
        openArtifact: openArtifact,
        closeArtifactViewer: closeArtifactViewer,
        renderArtifactContent: renderArtifactContent,
        renderArtifactBodyByType: renderArtifactBodyByType,
        renderMarkdownSafe: renderMarkdownSafe,
        inlineMd: inlineMd,
        canvasAgentArtifactTranscript: canvasAgentArtifactTranscript,
        renderArtifactTable: renderArtifactTable,
        artifactNodeDropSpot: artifactNodeDropSpot,
        addArtifactToCanvas: addArtifactToCanvas,
        artifactScopeKey: artifactScopeKey,
        artifactScopeLabel: artifactScopeLabel,
        artifactScopeText: artifactScopeText,
        referenceArtifactInAgent: referenceArtifactInAgent,
        renameArtifact: renameArtifact,
        deleteArtifact: deleteArtifact,
        clearCanvasAgentArtifacts: clearCanvasAgentArtifacts,
        newBrainstormConversation: newBrainstormConversation,
        canvasAgentConversationSeedTitle: canvasAgentConversationSeedTitle,
        setArtifactScope: setArtifactScope,
        renderConversationChrome: renderConversationChrome,
        selectArtifactSection: selectArtifactSection,
        openArtifactBodyOnly: openArtifactBodyOnly,
        closeArtifactSectionMenu: closeArtifactSectionMenu,
        closeArtifactScopeMenu: closeArtifactScopeMenu,
        updateArtifactItemContent: updateArtifactItemContent
    };
})(typeof window !== 'undefined' ? window : globalThis);

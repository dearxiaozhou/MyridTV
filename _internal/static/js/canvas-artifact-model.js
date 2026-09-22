/* MyridTV 画布产物数据模型（拆模块 ④-2：Conversation/Section/Item 三层 + Sidebar 数据层）
 *
 * Phase 8/9 的产物（Artifact）数据模型：ID 计算（与后端 _artifact_hash 严格一致）、
 * 容器/文档类型表、Section/Item 推断与分层 upsert、扁平化镜像、legacy 归并、读取兼容。
 * 只含数据层——Sidebar/Viewer 渲染与事件绑定仍在主文件。
 * 状态所有权在画布主文件（canvasAgentArtifactsState 整数组在加载/草稿恢复时重赋值），
 * 本模块经 deps.getArtifacts()/setArtifacts() 读写，导航选中态经 nav 注入。
 */
(function (global) {
    'use strict';

    var deps = {
        canvasId: null,       // () => 当前画布 id
        getArtifacts: null,   // () => canvasAgentArtifactsState 数组
        setArtifacts: null,   // (list) => 主文件整体替换
        navSectionId: null,   // () => 当前选中 Section id
        navItemId: null,      // () => 当前选中 Item id
        renderSidebar: null,  // () => void
        scheduleSave: null,   // () => void
        artifactTypeLabel: null // (type) => string
    };
    function configure(opts) {
        Object.assign(deps, opts || {});
    }

const ARTIFACT_LIMIT = 300;  // 与后端 ARTIFACT_LIMIT 保持一致
function findArtifact(id){
    if(!id) return null;
    return deps.getArtifacts().find(a => a && a.id === id) || null;
}
function artifactUpsert(next){
    if(!next || !next.id) return null;
    const idx = deps.getArtifacts().findIndex(a => a && a.id === next.id);
    if(idx >= 0){
        const prev = deps.getArtifacts()[idx];
        deps.getArtifacts()[idx] = Object.assign({}, prev, next, {
            createdAt: prev.createdAt || next.createdAt || Date.now(),
            updatedAt: Date.now(),
            version: (Number(prev.version || 1) || 1) + 1
        });
        return deps.getArtifacts()[idx];
    }
    deps.getArtifacts().push(Object.assign({
        canvasId: deps.canvasId(),
        createdAt: Date.now(),
        updatedAt: Date.now(),
        version: 1
    }, next));
    // 与后端 _merge_artifacts 同构：超出上限截断（保留最新的）
    if(deps.getArtifacts().length > ARTIFACT_LIMIT){
        deps.setArtifacts(deps.getArtifacts().slice(-ARTIFACT_LIMIT));
    }
    return deps.getArtifacts()[deps.getArtifacts().length - 1];
}
function saveArtifactToSidebar(opts){
    const o = opts || {};
    const content = String(o.content || '').trim();
    const title = String(o.title || '').trim();
    // 需求第四十一条/四十二条：宁可不创建，也不创建空 Sidebar Item
    if(!content && !o.resourceId) return null;
    if(!title && !content) return null;
    const artifactType = String(o.artifactType || o.type || 'text').trim().toLowerCase();
    // Phase 9：容器型产物（一轮 Brainstorm / 一次完整创意讨论）走分层模型。
    // 同一 canvas + 同一 conversationId + 同一类型 -> 同一个 Conversation Artifact，
    // 内容写进它内部的 Section / Item，绝不在 Sidebar 新建平铺的一级条目。
    const _convId = String(o.conversationId || '').trim();
    // Phase 9 兜底：会话内的非文档产物（text/note/script/analysis...）一律归入
    // 会话容器，哪怕事件没带 sectionTitle —— 用产物 title 退化成板块名，
    // 绝不退回旧的"每次 uuid 新建平铺条目"。只有独立文档型保持一级条目。
    if(_convId && !INDEPENDENT_DOC_TYPES.has(artifactType)){
        const _saved = upsertConversationSection({
            conversationId: _convId,
            artifactType: CONVERSATION_CONTAINER_TYPES.has(artifactType) ? artifactType : 'brainstorm',
            conversationTitle: o.conversationTitle || '',
            sectionType: o.sectionType || '',
            sectionTitle: o.sectionTitle || '',
            fallbackTitle: title,
            itemTitle: o.itemTitle || '',
            content: content,
            metadata: o.metadata || null,
            sourceRunId: o.sourceRunId || ''
        });
        if(_saved){ deps.renderSidebar(); deps.scheduleSave(); }
        return _saved;
    }
    const id = String(o.id || ('artifact_' + artifactType + '_' + simpleHash(artifactType + '|' + title)));
    const saved = artifactUpsert({
        id: id,
        title: title || (deps.artifactTypeLabel(artifactType) || '未命名'),
        artifactType: artifactType,
        content: content,
        resourceId: o.resourceId || '',
        canvasId: deps.canvasId(),
        sourceRunId: o.sourceRunId || '',
        sourceEventId: o.sourceEventId || '',
        canvasNodeId: findArtifact(id)?.canvasNodeId || ''
    });
    deps.renderSidebar();
    deps.scheduleSave();
    return saved;
}
function simpleHash(str){
    let h = 0;
    const s = String(str || '');
    for(let i = 0; i < s.length; i += 1){ h = ((h << 5) - h + s.charCodeAt(i)) | 0; }
    return Math.abs(h).toString(36);
}
const CONVERSATION_CONTAINER_TYPES = new Set([
    'brainstorm', 'creative_session', 'document_session', 'research_session',
    'story_bible', 'character_bible', 'world_bible',
    'story_outline', 'outline', 'visual_direction', 'creative_brief', 'brief'
]);
const INDEPENDENT_DOC_TYPES = new Set([
    'document', 'markdown', 'file', 'table', 'csv',
    'html', 'interactive', 'deck', 'presentation'
]);
const ARTIFACT_AUTO_MIGRATE = false;
const SECTION_TYPE_META = {
    character:  {label:'核心人物', icon:'users'},
    story:      {label:'故事设定', icon:'book-open'},
    scene:      {label:'关键场面', icon:'clapperboard'},
    world:      {label:'世界观',   icon:'globe'},
    visual:     {label:'视觉方向', icon:'palette'},
    direction:  {label:'方案方向', icon:'compass'},
    custom:     {label:'其他',     icon:'shapes'}
};
const SECTION_TYPE_KEYWORDS = [
    ['character', ['人物','角色','人设','character','主角']],
    ['story',     ['故事','剧情','梗概','大纲','story','plot','主线']],
    ['scene',     ['场面','场景','分镜','镜头','scene','关键场','高潮']],
    ['world',     ['世界观','势力','world','地理','规则','设定集']],
    ['visual',    ['视觉','美术','色彩','摄影','灯光','材质','visual','画风']],
    ['direction', ['方向','结局','方案','候选','direction','版本']]
];
function artifactHash(){
    let h = 2166136261;
    for(let i = 0; i < arguments.length; i += 1){
        const s = String(arguments[i] == null ? '' : arguments[i]);
        for(let j = 0; j < s.length; j += 1){
            h = Math.imul(h ^ s.charCodeAt(j), 16777619) >>> 0;
        }
    }
    return ('0000000' + h.toString(16)).slice(-8);
}
function conversationArtifactId(canvasIdVal, conversationId, artifactType){
    return 'conv_' + artifactHash(
        String(canvasIdVal || ''),
        String(conversationId || ''),
        String(artifactType || 'brainstorm').trim().toLowerCase()
    );
}
function artifactSectionId(conversationId, sectionType, sectionTitle){
    const st = String(sectionType || '').trim().toLowerCase();
    if(st) return 'sec_' + artifactHash(String(conversationId || ''), 't:' + st);
    return 'sec_' + artifactHash(String(conversationId || ''), 'n:' + String(sectionTitle || '').trim().toLowerCase());
}
function artifactItemId(sectionId, itemTitle){
    const t = String(itemTitle || '').trim();
    if(!t) return String(sectionId || '') + '_main';
    return 'item_' + artifactHash(String(sectionId || ''), t.toLowerCase());
}
function inferSectionType(title, explicit){
    const e = String(explicit || '').trim().toLowerCase();
    if(SECTION_TYPE_META[e]) return e;
    const t = String(title || '').toLowerCase();
    for(const [stype, kws] of SECTION_TYPE_KEYWORDS){
        for(const kw of kws){ if(t.indexOf(kw.toLowerCase()) >= 0) return stype; }
    }
    return 'custom';
}
function sectionTypeMeta(type){ return SECTION_TYPE_META[String(type || 'custom')] || SECTION_TYPE_META.custom; }
function artifactSections(a){
    return (a && Array.isArray(a.sections)) ? a.sections : [];
}
function findSectionOf(a, sid){
    if(!sid) return null;
    return artifactSections(a).find(s => s && String(s.id || '') === String(sid)) || null;
}
function defaultSectionId(a){
    const secs = artifactSections(a);
    if(!secs.length) return '';
    if(deps.navSectionId() && findSectionOf(a, deps.navSectionId())) return deps.navSectionId();
    return String(secs[0].id || '');
}
function activeSectionOf(a){
    if(!a) return null;
    const secs = artifactSections(a);
    if(!secs.length) return null;
    return findSectionOf(a, deps.navSectionId()) || secs[0] || null;
}
function defaultItemId(a, sid){
    const sec = findSectionOf(a, sid);
    const items = (sec && Array.isArray(sec.items)) ? sec.items : [];
    if(!items.length) return '';
    const hit = items.find(x => x && String(x.id || '') === String(deps.navItemId() || ''));
    if(hit) return String(hit.id || '');
    return items[0].title ? String(items[0].id || '') : '';
}
function activeItemOf(sec){
    if(!sec) return null;
    const items = Array.isArray(sec.items) ? sec.items : [];
    if(!items.length) return null;
    const hit = items.find(x => x && String(x.id || '') === String(deps.navItemId() || ''));
    if(hit) return hit;
    // 单条目且无标题 -> 直接显示内容，不显示 Tab
    if(items.length === 1 && !String(items[0].title || '').trim()) return items[0];
    return items[0] || null;
}
function sectionItems(sec){ return (sec && Array.isArray(sec.items)) ? sec.items : []; }
function flattenSectionContent(sec){
    if(!sec) return '';
    const items = sectionItems(sec);
    if(!items.length) return '';
    if(items.length === 1 && !String(items[0].title || '').trim()) return String(items[0].content || '');
    return items.map(it => {
        const t = String(it.title || '').trim();
        const c = String(it.content || '').trim();
        return t ? ('### ' + t + (c ? ('\n' + c) : '')) : c;
    }).filter(Boolean).join('\n\n');
}
function flattenConversationContent(a){
    if(!a) return '';
    const secs = artifactSections(a);
    if(!secs.length) return '';
    return secs.map(sec => {
        const body = flattenSectionContent(sec);
        return '## ' + String(sec.title || '') + (body ? ('\n\n' + body) : '');
    }).join('\n\n');
}
function upsertConversationSection(opts){
    const o = opts || {};
    const convId = String(o.conversationId || '').trim();
    if(!convId) return null;
    const atype = String(o.artifactType || 'brainstorm').trim().toLowerCase();
    const aid = conversationArtifactId(deps.canvasId(), convId, atype);
    const now = Date.now();

    let art = findArtifact(aid);
    if(!art){
        art = {
            id: aid,
            canvasId: deps.canvasId(),
            conversationId: convId,
            artifactType: atype,
            kind: 'conversation',
            title: String(o.conversationTitle || '').trim().slice(0, 60) || 'Brainstorm',
            content: '',
            sections: [],
            resourceId: '',
            canvasNodeId: '',
            canvasNodeIds: {},
            sourceRunId: String(o.sourceRunId || ''),
            sourceEventId: '',
            version: 1,
            createdAt: now,
            updatedAt: now
        };
        deps.getArtifacts().push(art);
    }
    art.kind = 'conversation';
    art.conversationId = convId;
    if(!Array.isArray(art.sections)) art.sections = [];

    // 板块名取值链：显式 sectionTitle > 产物 title(fallbackTitle) > 退化成类型标签。
    // 与后端 sec_name 规则必须一致，否则前后端会算出不同 sectionId。
    const secName = String(o.sectionTitle || '').trim() || String(o.fallbackTitle || '').trim();
    const stype = inferSectionType(secName, o.sectionType);
    const stitle = secName || sectionTypeMeta(stype).label;
    // ID 去重键：有名字就按名字；连名字都没有才按类型。
    // 不能仅因为语义类型相同就合并 —— 「悲剧结局/开放结局/反转结局」都推断成 direction，
    // 但它们明明是三个不同板块（需求第二十八/二十条）。
    const sid = secName ? artifactSectionId(convId, '', secName) : artifactSectionId(convId, stype, '');

    let sec = art.sections.find(s => s && String(s.id || '') === sid);
    if(!sec){
        sec = {id: sid, type: stype, title: stitle, order: art.sections.length, items: [], createdAt: now, updatedAt: now};
        art.sections.push(sec);
    }
    sec.title = stitle;
    sec.type = stype;
    if(!Array.isArray(sec.items)) sec.items = [];

    const iTitle = String(o.itemTitle || '').trim();
    const iid = String(o.itemId || '').trim() || artifactItemId(sid, iTitle);
    // 板块从「一整块文本」升级成「具名条目」时，撤掉之前那个匿名占位条目。
    // 否则 核心人物 会同时挂着 "林澜/司徒岳" 旧块 + 林澜 + 司徒岳 三条。
    if(iTitle){
        const only = sec.items.length === 1 ? sec.items[0] : null;
        if(only && !String(only.title || '').trim() && String(only.id || '').endsWith('_main')){
            sec.items = [];
        }
    }
    let item = sec.items.find(x => x && String(x.id || '') === iid);
    if(!item){
        item = {id: iid, title: iTitle, content: '', order: sec.items.length, metadata: o.metadata || {}, createdAt: now, updatedAt: now};
        sec.items.push(item);
    }
    if(o.content !== undefined) item.content = String(o.content || '');
    if(o.metadata && typeof o.metadata === 'object') item.metadata = Object.assign({}, item.metadata || {}, o.metadata);
    item.updatedAt = now;
    sec.updatedAt = now;

    art.sections.sort((x, y) => (Number(x.order || 0) - Number(y.order || 0)));
    art.sections.forEach((s, i) => { s.order = i; });
    art.updatedAt = now;
    art.version = (Number(art.version || 1) || 1) + 1;
    // content 保留扁平镜像，供旧逻辑 / 全文检索兜底（不作为分层导航来源）
    art.content = flattenConversationContent(art);

    if(deps.getArtifacts().length > ARTIFACT_LIMIT){
        deps.setArtifacts(deps.getArtifacts().slice(-ARTIFACT_LIMIT));
    }
    return art;
}
function migrateLegacyArtifactsToConversations(apply){
    const groups = {};
    (deps.getArtifacts() || []).forEach(a => {
        if(!a || !a.id || a.kind === 'conversation') return;
        if(Array.isArray(a.sections) && a.sections.length) return;
        const run = String(a.sourceRunId || '').trim();
        if(!run || run === 'agent_action_plan') return;   // 通用常量不作归并依据
        const key = String(a.canvasId || deps.canvasId()) + '|' + run + '|' + String(a.artifactType || 'text');
        (groups[key] = groups[key] || []).push(a);
    });
    const plan = Object.keys(groups).filter(k => groups[k].length > 1);
    if(!apply){
        return {groups: plan.length, artifacts: plan.reduce((n, k) => n + groups[k].length, 0)};
    }
    let moved = 0;
    plan.forEach(key => {
        const list = groups[key].slice().sort((x, y) => Number(x.createdAt || 0) - Number(y.createdAt || 0));
        const convId = String(list[0].sourceRunId || '');
        list.forEach(a => {
            upsertConversationSection({
                conversationId: convId,
                artifactType: String(a.artifactType || 'brainstorm'),
                conversationTitle: String(list[0].title || ''),
                sectionTitle: String(a.title || ''),
                content: String(a.content || '')
            });
            deps.setArtifacts(deps.getArtifacts().filter(x => x && x.id !== a.id));
            moved += 1;
        });
    });
    deps.renderSidebar();
    deps.scheduleSave();
    return {moved: moved, conversations: plan.length};
}
function artifactPlainText(a){
    if(!a) return '';
    const sec = activeSectionOf(a);
    if(sec){
        const it = activeItemOf(sec);
        return (it && String(it.content || '').trim()) ? String(it.content || '') : flattenSectionContent(sec);
    }
    return String(a.content || '');
}
function currentArtifactScope(){
    return localStorage.getItem('myridtv.artifact.scope') || 'section';
}

    global.CanvasArtifactModel = {
        configure: configure,
        ARTIFACT_AUTO_MIGRATE: ARTIFACT_AUTO_MIGRATE,
        CONVERSATION_CONTAINER_TYPES: CONVERSATION_CONTAINER_TYPES,
        INDEPENDENT_DOC_TYPES: INDEPENDENT_DOC_TYPES,
        findArtifact: findArtifact,
        artifactUpsert: artifactUpsert,
        saveArtifactToSidebar: saveArtifactToSidebar,
        simpleHash: simpleHash,
        artifactHash: artifactHash,
        conversationArtifactId: conversationArtifactId,
        artifactSectionId: artifactSectionId,
        artifactItemId: artifactItemId,
        inferSectionType: inferSectionType,
        sectionTypeMeta: sectionTypeMeta,
        artifactSections: artifactSections,
        findSectionOf: findSectionOf,
        defaultSectionId: defaultSectionId,
        activeSectionOf: activeSectionOf,
        defaultItemId: defaultItemId,
        activeItemOf: activeItemOf,
        sectionItems: sectionItems,
        flattenSectionContent: flattenSectionContent,
        flattenConversationContent: flattenConversationContent,
        upsertConversationSection: upsertConversationSection,
        migrateLegacyArtifactsToConversations: migrateLegacyArtifactsToConversations,
        artifactPlainText: artifactPlainText,
        currentArtifactScope: currentArtifactScope
    };
})(typeof window !== 'undefined' ? window : globalThis);

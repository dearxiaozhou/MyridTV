/* Agent @reference picker, stable badge order and keyboard navigation. */
(function(global){
    'use strict';

    const deps = {};
    let inputBound = false;

    function configure(options){Object.assign(deps, options || {});}
    function input(){return deps.getInput ? deps.getInput() : null;}
    function panel(){return deps.getPanel ? deps.getPanel() : null;}
    function candidates(){
        return deps.uniqueRefs([
            ...(deps.getRefs() || []),
            ...(deps.collectSelectedResources() || [])
        ]).filter(ref => ['image','video'].includes(deps.mediaKindForItem(ref)));
    }
    function query(){
        const el = input();
        if(!el) return null;
        const pos = el.selectionStart ?? el.value.length;
        const before = el.value.slice(0, pos);
        const at = before.lastIndexOf('@');
        if(at < 0) return null;
        const value = before.slice(at + 1);
        if(/\s/.test(value)) return null;
        return {start:at, end:pos, query:value || ''};
    }
    function ensurePicker(){
        const host = panel();
        if(!host) return null;
        let picker = host.querySelector('.canvas-agent-mention');
        if(!picker){
            picker = global.document.createElement('div');
            picker.className = 'canvas-agent-mention';
            host.appendChild(picker);
        }
        return picker;
    }
    function setIndex(value){if(deps.setIndex) deps.setIndex(value);}
    function close(){
        const picker = panel()?.querySelector?.('.canvas-agent-mention');
        if(picker){
            picker.classList.remove('open');
            picker.innerHTML = '';
        }
        setIndex(-1);
    }
    function sortRefsByMentionPool(){
        const pool = deps.getMentionPool() || [];
        if(!pool.length) return;
        const orderMap = new Map();
        const counters = {};
        pool.forEach(ref => {
            const label = deps.refKindLabel(ref);
            counters[label] = (counters[label] || 0) + 1;
            orderMap.set(`${label}|${ref.url}`, counters[label] - 1);
        });
        const refs = deps.getRefs() || [];
        refs.sort((a, b) => {
            const labelA = deps.refKindLabel(a), labelB = deps.refKindLabel(b);
            if(labelA !== labelB) return 0;
            return (orderMap.get(`${labelA}|${a.url}`) ?? 1e9) - (orderMap.get(`${labelB}|${b.url}`) ?? 1e9);
        });
        deps.setRefs(refs);
    }
    function render(){
        const picker = ensurePicker();
        const info = query();
        if(!picker || !info){close();return;}
        const q = info.query.trim().toLowerCase();
        const matching = candidates().filter(ref => {
            const name = `${deps.mediaLabel(ref)} ${deps.refFileName(ref)}`.toLowerCase();
            const badge = deps.mentionBadge(ref).toLowerCase();
            return !q || name.includes(q) || badge.includes(q);
        });
        if(!matching.length){
            picker.innerHTML = '<div class="canvas-agent-mention-empty">没有可引用的图片，先点 + 加入画布资源</div>';
            picker.classList.add('open');
            setIndex(-1);
            return;
        }
        let selectedIndex = deps.getIndex();
        if(selectedIndex < 0 || selectedIndex >= matching.length) selectedIndex = 0;
        setIndex(selectedIndex);
        const pool = deps.getMentionPool() || [];
        matching.forEach(ref => {
            if(!pool.some(item => item.url === ref.url)) pool.push(ref);
        });
        deps.setMentionPool(pool);
        matching.sort((a, b) => pool.findIndex(ref => ref.url === a.url) - pool.findIndex(ref => ref.url === b.url));
        const visible = matching.slice(0, 8);
        picker.innerHTML = visible.map((ref, index) => {
            const kind = deps.mediaKindForItem(ref);
            const label = `@${deps.mentionBadge(ref)}`;
            const media = kind === 'video'
                ? `<video src="${deps.escapeHtml(ref.url)}" muted preload="metadata" playsinline></video>`
                : `<img src="${deps.escapeHtml(ref.url)}" alt="">`;
            return `<button type="button" class="${index === selectedIndex ? 'active' : ''}" data-agent-mention-index="${index}">
                ${media}
                <span>${deps.escapeHtml(label)}</span>
                <small>${deps.escapeHtml(deps.refFileName(ref) || deps.mediaLabel(ref, index))}</small>
            </button>`;
        }).join('');
        picker._items = visible;
        picker.classList.add('open');
        picker.querySelectorAll('[data-agent-mention-index]').forEach(button => {
            button.onclick = event => {
                event.preventDefault();
                event.stopPropagation();
                insert(picker._items[Number(button.dataset.agentMentionIndex)]);
            };
        });
        if(global.lucide) global.lucide.createIcons();
    }
    function insert(ref){
        const el = input();
        if(!ref || !el) return;
        const info = query();
        deps.addRefs([ref]);
        sortRefsByMentionPool();
        deps.renderRefs();
        const token = `@${deps.mentionBadge(ref)}`;
        const start = info ? info.start : (el.selectionStart ?? el.value.length);
        const end = info ? info.end : (el.selectionEnd ?? start);
        const before = el.value.slice(0, start);
        const after = el.value.slice(end);
        el.value = `${before}${token} ${after}`;
        const next = before.length + token.length + 1;
        el.setSelectionRange(next, next);
        deps.resizeInput();
        close();
        el.focus();
    }
    function bindInputEvents(){
        const el = input();
        if(!el || inputBound) return;
        inputBound = true;
        el.addEventListener('input', () => {
            deps.resizeInput();
            render();
        });
        el.addEventListener('keydown', event => {
            const picker = panel()?.querySelector?.('.canvas-agent-mention.open');
            const items = picker?._items || [];
            if(picker && event.key === 'Escape'){
                event.preventDefault();
                close();
                return;
            }
            if(picker && items.length && ['ArrowDown','ArrowUp','Enter','Tab'].includes(event.key)){
                if(event.key === 'ArrowDown' || event.key === 'ArrowUp'){
                    event.preventDefault();
                    const current = deps.getIndex();
                    setIndex(event.key === 'ArrowDown'
                        ? (current + 1) % items.length
                        : (current - 1 + items.length) % items.length);
                    render();
                    return;
                }
                if(event.key === 'Enter' || event.key === 'Tab'){
                    event.preventDefault();
                    const current = Math.max(0, deps.getIndex());
                    insert(items[current]);
                    return;
                }
            }
            if(event.key === 'Enter' && !event.shiftKey){
                event.preventDefault();
                deps.sendMessage();
            }
        });
        el.addEventListener('blur', () => global.setTimeout(close, 140));
    }

    global.CanvasAgentMentionController = {
        configure,
        candidates,
        query,
        ensurePicker,
        close,
        sortRefsByMentionPool,
        render,
        insert,
        bindInputEvents
    };
})(typeof window !== 'undefined' ? window : globalThis);

//** Move-lines-to-new-source: redirect pick mode UI, candidate highlight, connection migration. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    function D(name){return typeof deps[name] === 'function' ? deps[name]() : deps[name];}

(function injectNodeMoveLinesUi(){
    if(document.getElementById('node-move-lines-style')) return;
    const st = document.createElement('style');
    st.id = 'node-move-lines-style';
    st.textContent = [
        '.node-move-lines{position:absolute;top:7px;left:44px;z-index:10;width:28px;height:28px;border-radius:8px;border:1px solid rgba(200,200,200,.32);background:rgba(31,31,31,.9);color:#cfd3d8;display:flex;align-items:center;justify-content:center;cursor:pointer;opacity:0;padding:0;transition:opacity .15s,background .15s,border-color .15s;}',
        '.image-node:hover .node-move-lines,.image-node.selected .node-move-lines{opacity:1;}',
        '.node-move-lines:hover{background:rgba(40,44,52,.95);border-color:#6aa9ff;color:#fff;}',
        '.node-move-lines svg{width:15px;height:15px;}',
        '.image-node.node-move-candidate{outline:2px dashed #6aa9ff;outline-offset:2px;}',
        '.move-lines-banner{position:fixed;left:50%;top:14px;transform:translateX(-50%);z-index:3000;background:rgba(31,31,31,.96);color:#fff;padding:8px 14px;border-radius:8px;font-size:13px;font-weight:600;box-shadow:0 10px 30px rgba(0,0,0,.4);display:none;}'
    ].join('');
    document.head.appendChild(st);
})();

// ===== 把线移到新素材：原节点保留、图片不动，仅将旧素材所有 outgoing 连线整体平移到新素材 =====
let redirectPickMode = null;

function enterRedirectPickMode(sourceId){
    const src = D("nodes").find(n => n.id === sourceId);
    if(!src){ deps.toast('无法作为来源'); return; }
    exitRedirectPickMode();
    redirectPickMode = { sourceId };
    D("nodes").forEach(n => {
        if(n.id === sourceId) return;
        if(n.type !== 'smart-image' && n.type !== 'smart-video' && n.type !== 'smart-audio' && n.type) return;
        const el = D("world").querySelector('.image-node[data-id="'+CSS.escape(n.id)+'"]');
        if(el) el.classList.add('node-move-candidate');
    });
    let banner = document.getElementById('move-lines-banner');
    if(!banner){ banner = document.createElement('div'); banner.id='move-lines-banner'; banner.className='move-lines-banner'; document.body.appendChild(banner); }
    banner.textContent = '把线移到新素材：点另一个素材节点 → 旧素材所有连线整体平移（图片与节点均不动）。Esc / 点空白取消';
    banner.style.display = 'block';
    deps.toast('已进入「把线移到新素材」：点选目标素材节点');
}

function exitRedirectPickMode(){
    if(!redirectPickMode) return;
    redirectPickMode = null;
    D("world").querySelectorAll('.image-node.node-move-candidate').forEach(el => el.classList.remove('node-move-candidate'));
    const banner = document.getElementById('move-lines-banner');
    if(banner) banner.style.display = 'none';
}

function applyMoveLinesToNewSource(oldId, newId){
    const conns = D("canvas").connections || [];
    const oldNode = D("nodes").find(n => n.id === oldId);
    const newNode = D("nodes").find(n => n.id === newId);
    if(!oldNode || !newNode || oldId === newId) return false;
    let moved = 0;
    conns.forEach(c => {
        if(c.from !== oldId) return;
        const dup = conns.some(o => o !== c && o.from === newId && o.to === c.to && (o.kind || 'flow') === (c.kind || 'flow'));
        if(dup) return;
        c.from = newId;
        moved++;
    });
    const idsByTo = {};
    conns.forEach(c => { if(c.to){ (idsByTo[c.to] = idsByTo[c.to] || new Set()).add(c.from); } });
    D("nodes").forEach(n => { if(idsByTo[n.id]) n.inputNodeIds = Array.from(idsByTo[n.id]); });
    return moved > 0;
}

document.addEventListener('mousedown', function(e){
    const btn = e.target && e.target.closest ? e.target.closest('.node-move-lines') : null;
    if(btn){
        e.preventDefault();
        e.stopPropagation();
        const el = btn.closest('.image-node');
        const id = el && el.dataset.id;
        if(id && !redirectPickMode) enterRedirectPickMode(id);
    }
}, true);

document.addEventListener('click', function(e){
    const btn = e.target && e.target.closest ? e.target.closest('.node-move-lines') : null;
    if(btn){
        e.preventDefault();
        e.stopPropagation();
        const el = btn.closest('.image-node');
        const id = el && el.dataset.id;
        if(id && !redirectPickMode) enterRedirectPickMode(id);
        return;
    }
}, true);

document.addEventListener('click', function(e){
    if(!redirectPickMode) return;
    if(e.target && e.target.closest && e.target.closest('.node-move-lines')) return;
    const nodeEl = e.target && e.target.closest ? e.target.closest('.image-node') : null;
    if(nodeEl){
        const id = nodeEl.dataset.id;
        e.preventDefault();
        e.stopPropagation();
        if(id && id !== redirectPickMode.sourceId){
            deps.pushUndo();
            const ok = applyMoveLinesToNewSource(redirectPickMode.sourceId, id);
            if(ok){ deps.render(); deps.scheduleSave(); deps.toast('已把该素材所有连线移到新素材（图片与节点均不动）'); }
            else { deps.toast('该素材没有可移动的连线'); }
        }
        exitRedirectPickMode();
        return;
    }
    exitRedirectPickMode();
}, true);

document.addEventListener('keydown', function(e){
    if(redirectPickMode && e.key === 'Escape'){ e.preventDefault(); exitRedirectPickMode(); }
}, true);

    global.CanvasRedirectLines = {
        configure,
        enterRedirectPickMode,
        exitRedirectPickMode,
        applyMoveLinesToNewSource,
    };
})(typeof window !== 'undefined' ? window : this);

(function () {
  function qs(selector, root) {
    return (root || document).querySelector(selector);
  }

  function create(tag, className, html) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (html != null) el.innerHTML = html;
    return el;
  }

  function text(value, fallback = '') {
    return ((value || '').replace(/\s+/g, ' ').trim()) || fallback;
  }

  function gateCount() {
    return text(qs('#gateCountPill')?.textContent, '0');
  }

  function ensureGateEnhancements() {
    const gateHeadText = qs('.gate-head-text');
    const gateSubtitle = qs('#gateSubtitle');
    if (!gateHeadText || !gateSubtitle) return;

    if (!qs('.prism-canvas-brandline', gateHeadText)) {
      gateHeadText.insertBefore(create('div', 'prism-canvas-brandline', [
'<img src="/static/images/myrid-mark.svg" alt="MyridTV">',
        '<span class="prism-canvas-brand-copy"><strong>MyridTV</strong><em>本地无限画布 · 一站式智能创作中枢</em></span>'
      ].join('')), qs('.gate-title-row', gateHeadText) || gateHeadText.firstChild);
    }

    // 2026-10-16：老王要求删掉主页面的「后端：127.0.0.1:3113」标签，整块移除
  }

  function ensureTopbarEnhancements() {
    const navMeta = qs('.canvas-nav-meta');
    if (!navMeta) return;
    if (!qs('#prismCanvasModePill', navMeta)) {
      navMeta.appendChild(create('div', 'prism-canvas-nav-row', '<div id="prismCanvasModePill" class="prism-canvas-mode-pill">画布列表</div>'));
    }
  }

  function syncModePill() {
    const pill = qs('#prismCanvasModePill');
    const shell = qs('#shell');
    if (!pill || !shell) return;
    const isGate = shell.classList.contains('no-canvas');
    if (isGate) {
      pill.textContent = `画布列表 · ${gateCount()} 个`;
    } else {
      const title = text(qs('#currentCanvasTitle')?.textContent, '未命名画布');
      pill.textContent = `当前画布 · ${title}`;
    }
  }

  function observeState() {
    const shell = qs('#shell');
    const title = qs('#currentCanvasTitle');
    const count = qs('#gateCountPill');
    const targets = [shell, title, count].filter(Boolean);
    if (!targets.length) return;

    const observer = new MutationObserver(() => window.requestAnimationFrame(syncModePill));
    targets.forEach((node) => observer.observe(node, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ['class'],
    }));
  }

  function enhance() {
    document.body.classList.add('prism-canvas-page');
    ensureTopbarEnhancements();
    ensureGateEnhancements();
    syncModePill();
    observeState();
  }

  document.addEventListener('DOMContentLoaded', () => {
    enhance();
    window.setTimeout(syncModePill, 200);
    window.setTimeout(syncModePill, 900);
  }, { once: true });
})();

(function(){
  window.addEventListener('message', function(event){
    if(event.data && event.data.type === 'myrid-home-canvas-list'){
      try {
        if(typeof setTrashMode === 'function' && typeof trashMode !== 'undefined' && trashMode) setTrashMode(false);
        if(typeof setCreateMode === 'function') setCreateMode(false);
        if(typeof setCanvasMode === 'function') setCanvasMode(false);
        if(typeof loadCanvasList === 'function') loadCanvasList(false);
      } catch(e) {}
    }
  });
})();

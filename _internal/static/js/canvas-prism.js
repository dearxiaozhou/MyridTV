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

    const gateActions = qs('.gate-head-actions');
    let info = qs('#gateBackendInfo');
    if (!info) {
      qs('.prism-canvas-gate-pills')?.remove();
      const row = create('div', 'prism-canvas-gate-pills');
      info = create('button', 'prism-canvas-hero-pill');
      info.id = 'gateBackendInfo';
      info.type = 'button';
      info.textContent = '后端：检测中…';
      row.appendChild(info);
      if (gateActions) gateActions.insertAdjacentElement('afterend', row);
      else gateHeadText.appendChild(row);
      bindBackendInfo(info);
    }
  }

  function bindBackendInfo(button) {
    let address = '', normalText = '', copiedTimer = null, checkVersion = 0;
    function show(port, connected) {
      const endpoint = new URL(location.origin);
      endpoint.port = String(port);
      address = endpoint.origin;
      normalText = `后端：${endpoint.hostname}:${port}${connected ? '' : ' · 未连接'}`;
      button.textContent = normalText;
      button.title = `${address}（点击复制后端地址）`;
      button.setAttribute('aria-label', normalText + '，点击复制后端地址');
      button.dataset.address = address;
      button.dataset.connection = connected ? 'connected' : 'offline';
    }
    async function refreshBackend() {
      const version = ++checkVersion;
      try {
        const response = await fetch('/health', {cache:'no-store'});
        const health = response.ok ? await response.json() : null;
        if (version !== checkVersion) return;
        const port = Number(health?.port);
        if (!health?.ok || !Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Unavailable backend');
        show(port, true);
      } catch (_) {
        if (version !== checkVersion) return;
        show(Number(location.port) || (location.protocol === 'https:' ? 443 : 80), false);
      }
    }
    button.addEventListener('click', async () => {
      if (!address) return;
      const copied = await copyTextToClipboard(address);
      button.textContent = copied ? '后端地址已复制' : '复制失败，请从提示中选择地址';
      clearTimeout(copiedTimer);
      copiedTimer = setTimeout(() => {button.textContent = normalText;}, 1800);
    });
    window.addEventListener('focus', refreshBackend);
    refreshBackend();
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

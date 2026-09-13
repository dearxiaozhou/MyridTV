(function () {
  function qs(selector, root) {
    return (root || document).querySelector(selector);
  }

  function qsa(selector, root) {
    return Array.from((root || document).querySelectorAll(selector));
  }

  function cleanText(value) {
    return (value || '').replace(/\s+/g, ' ').trim();
  }

  function activeProviderName() {
    const active = qs('#providerList .provider-card.active') || qs('#agentList .provider-card.active');
    if (!active) return '未选择';
    const name = cleanText(qs('.provider-name', active)?.textContent);
    return name || cleanText(active.textContent) || '未选择';
  }

  function currentEditorTitle() {
    return cleanText(qs('#editorTitle')?.textContent) || activeProviderName();
  }

  function countCards(selector) {
    return qsa(selector).length;
  }

  function setText(selector, value) {
    const node = qs(selector);
    if (node) node.textContent = value;
  }

  function syncSummary() {
    const providerCount = countCards('#providerList .provider-card');
    const agentCount = countCards('#agentList .provider-card') || 1;
    const selected = currentEditorTitle();

    setText('#apiPlatformCount', String(providerCount));
    setText('#apiAgentCount', String(agentCount));
    setText('#prismEditorMirror', `当前：${selected}`);
  }

  function ensurePageHeadEnhancements() {
    // pills removed per user request
  }

  function ensureContentHeadEnhancements() {
    const actions = qs('.content-actions');
    if (!actions || qs('#prismEditorMirror', actions)) return;

    const mirror = document.createElement('div');
    mirror.id = 'prismEditorMirror';
    mirror.className = 'prism-api-meta-chip';
    mirror.textContent = '当前：平台';
    actions.prepend(mirror);
  }

  function observeTargets() {
    const targets = [
      qs('#providerList'),
      qs('#agentList'),
      qs('#editorTitle'),
    ].filter(Boolean);
    if (!targets.length) return;

    const observer = new MutationObserver(() => window.requestAnimationFrame(syncSummary));
    targets.forEach((target) => observer.observe(target, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
    }));
  }

  function enhance() {
    document.body.classList.add('prism-api-page');
    ensurePageHeadEnhancements();
    ensureContentHeadEnhancements();
    syncSummary();
    observeTargets();
  }

  document.addEventListener('DOMContentLoaded', () => {
    enhance();
    window.setTimeout(syncSummary, 200);
    window.setTimeout(syncSummary, 900);
  }, { once: true });
})();

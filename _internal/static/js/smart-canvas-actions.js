(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.WcsSmartCanvasActions = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  function shouldStartSmartCanvasMiddlePan(button, hitOverlay) {
    return Number(button) === 1 && !hitOverlay;
  }

  function smartImageContextActionIds() {
    return ['add-agent', 'duplicate-node', 'view-image', 'img2img', 'save-asset', 'copy-path', 'open-folder', 'set-cover', 'asset-follow-latest', 'asset-pin-version', 'asset-save-version'];
  }

  function duplicateNodeConnections(connections, sourceId, copyId) {
    const seen = new Set();
    const next = [];
    for (const conn of connections || []) {
      if (!conn || (!conn.from && !conn.to)) continue;
      let from = conn.from;
      let to = conn.to;
      let touched = false;
      if (from === sourceId) {
        from = copyId;
        touched = true;
      }
      if (to === sourceId) {
        to = copyId;
        touched = true;
      }
      if (!touched || !from || !to) continue;
      const kind = conn.kind || 'flow';
      const key = `${from}->${to}:${kind}`;
      if (seen.has(key)) continue;
      seen.add(key);
      next.push({...conn, from, to, kind});
    }
    return next;
  }

  return {
    duplicateNodeConnections,
    shouldStartSmartCanvasMiddlePan,
    smartImageContextActionIds,
  };
});

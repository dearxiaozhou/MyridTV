/* Generation attempt identity, terminal cleanup and persistent frame ownership. */
(function (global) {
    'use strict';
    let sequence = 0;
    function box(value) {
        const width = Number(value?.width ?? value?.w), height = Number(value?.height ?? value?.h);
        return Number.isFinite(width) && Number.isFinite(height) && width > 0 && height > 0 ? {width, height} : null;
    }
    function lockFrame(node, value) {
        const size = box(value);
        if (!node || !size) return false;
        node.cardSize = size;
        node.w = size.width; node.h = size.height;
        node.cardSizing = node.cardSizing || 'media';
        node.generationFrameLocked = true;
        return true;
    }
    function restoreFrame(node, fallback) {
        if (!node) return false;
        return lockFrame(node, box(node.cardSize) || box({w:node.w,h:node.h}) || box(fallback));
    }
    function begin(node, options={}) {
        const id = options.id || `generation-${Date.now()}-${++sequence}`;
        node.generationAttemptId = id;
        node.generationState = 'preparing';
        delete node.pendingTasks;
        delete node.jimengPending;
        delete node.runError;
        return id;
    }
    function owns(node, id) { return !!node && !!id && node.generationAttemptId === id; }
    function isCurrent(node, id) { return owns(node,id) && node.generationState !== 'cancelled'; }
    function transition(node, id, state) {
        if (!isCurrent(node,id) || !['queued','running','starting'].includes(state)) return false;
        if (['succeeded','failed'].includes(node.generationState)) return false;
        node.generationState = state;
        return true;
    }
    function finish(node, id, state, error='', now=Date.now()) {
        if (!owns(node,id) || !['succeeded','failed','cancelled'].includes(state)) return false;
        if (node.generationState === 'cancelled' && state !== 'cancelled') return false;
        node.generationState = state;
        node.pending = 0; node.running = false; node.apiRunning = false;
        delete node.pendingTasks;
        node.runFinishedAt = now;
        if (!node.runStartedAt) node.runStartedAt = now;
        node.runElapsedMs = Math.max(0, now - Number(node.runStartedAt));
        if (state === 'failed') node.runError = String(error || '生成失败');
        else delete node.runError;
        restoreFrame(node);
        return true;
    }
    global.CanvasGenerationLifecycle = {box, lockFrame, restoreFrame, begin, owns, isCurrent, transition, finish};
})(typeof window !== 'undefined' ? window : globalThis);

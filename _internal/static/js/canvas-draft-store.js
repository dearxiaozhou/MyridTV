/* MyridTV 画布本地草稿层（③ 持久化：前端本地库 + 防抖写）
 *
 * 背景：画布目前只有"页面把整张画布 PUT 给后端"这一条路 —— 页面崩了/断网/被强关，
 * 没同步出去的那部分改动就没了；页面开太久时手里还是老快照，保存会把新的盖掉。
 *
 * 做法（TDCanvas 同思路，但不动后端权威性，只做兜底）：
 *  - 每次改动先落一份本地草稿（IndexedDB，异步、容量大；不可用时退回 localStorage）
 *  - 草稿记录 baseUpdatedAt（基于服务端哪个版本改的）与 savedAt（本地写入时刻）
 *  - 页面加载时若草稿比服务端新、且基于当前服务端版本 → 自动恢复并立刻同步回后端
 *  - 同步成功后就清掉草稿，避免把旧草稿当"新改动"反复恢复
 *
 * 说明：后端仍是权威副本（Agent/MCP 通道直接读画布文件的能力不受影响）。
 */
(function (global) {
    'use strict';

    var DB_NAME = 'myridtv_canvas';
    var DB_VERSION = 1;
    var STORE = 'drafts';
    var LOCAL_PREFIX = 'myridtv:canvas-draft:';

    function openDb() {
        return new Promise(function (resolve, reject) {
            if (!global.indexedDB) return reject(new Error('no indexedDB'));
            var req = global.indexedDB.open(DB_NAME, DB_VERSION);
            req.onupgradeneeded = function () {
                var db = req.result;
                if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE, { keyPath: 'canvasId' });
            };
            req.onsuccess = function () { resolve(req.result); };
            req.onerror = function () { reject(req.error || new Error('indexedDB open failed')); };
        });
    }

    function withStore(mode, fn) {
        return openDb().then(function (db) {
            return new Promise(function (resolve, reject) {
                var tx = db.transaction(STORE, mode);
                var store = tx.objectStore(STORE);
                var out;
                try { out = fn(store); } catch (err) { reject(err); return; }
                tx.oncomplete = function () {
                    // 注意：IDBRequest 没有结果时 result 是 undefined，此时必须回 null，
                    // 否则会把 request 对象本身当记录返回（读出来是个空对象）
                    if (out && typeof out === 'object' && 'result' in out) { resolve(out.result === undefined ? null : out.result); return; }
                    resolve(out);
                };
                tx.onerror = function () { reject(tx.error || new Error('indexedDB tx failed')); };
            });
        });
    }

    function localKey(canvasId) { return LOCAL_PREFIX + String(canvasId || ''); }

    function saveLocal(canvasId, draft) {
        try {
            global.localStorage.setItem(localKey(canvasId), JSON.stringify(draft));
            return true;
        } catch (_) { return false; }
    }

    function readLocal(canvasId) {
        try {
            var raw = global.localStorage.getItem(localKey(canvasId));
            return raw ? JSON.parse(raw) : null;
        } catch (_) { return null; }
    }

    function removeLocal(canvasId) {
        try { global.localStorage.removeItem(localKey(canvasId)); } catch (_) {}
    }

    function save(canvasId, draft) {
        var id = String(canvasId || '').trim();
        if (!id || !draft) return Promise.resolve(false);
        var record = {
            canvasId: id,
            savedAt: Number(draft.savedAt || Date.now()),
            baseUpdatedAt: Number(draft.baseUpdatedAt || 0),
            title: draft.title || '',
            nodes: draft.nodes || [],
            connections: draft.connections || [],
            logs: draft.logs || [],
            settings: draft.settings || {},
            viewport: draft.viewport || { x: 0, y: 0, scale: 1 },
            artifacts: draft.artifacts || [],
            clientId: draft.clientId || ''
        };
        // 双写：IndexedDB 为主，localStorage 兜底（小画布场景下即使 IDB 不可用也不丢）
        saveLocal(id, record);
        return withStore('readwrite', function (store) { store.put(record); return true; })
            .then(function () { return true; })
            .catch(function () { return false; });
    }

    function read(canvasId) {
        var id = String(canvasId || '').trim();
        if (!id) return Promise.resolve(null);
        return withStore('readonly', function (store) { return store.get(id); })
            .then(function (row) { return row || readLocal(id); })
            .catch(function () { return readLocal(id); });
    }

    function clear(canvasId) {
        var id = String(canvasId || '').trim();
        if (!id) return Promise.resolve(false);
        removeLocal(id);
        return withStore('readwrite', function (store) { store.delete(id); return true; })
            .catch(function () { return false; });
    }

    function list() {
        return withStore('readonly', function (store) { return store.getAllKeys(); })
            .then(function (keys) { return keys || []; })
            .catch(function () { return []; });
    }

    global.CanvasDraftStore = {
        save: save,
        read: read,
        clear: clear,
        list: list,
        localKey: localKey
    };
})(typeof window !== 'undefined' ? window : globalThis);

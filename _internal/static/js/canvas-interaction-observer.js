/* MyridTV 画布交互观察者（状态机改造·第0步，零侵入）
 *
 * 只做一件事：在指针事件入口采样现有全局交互态，统计「多态并存」次数，
 * 暴露 window.__smDbg = {samples, multistateCount, peak, combos, lastCombos[]}。
 * 不读写任何交互状态、不 preventDefault、不影响行为——供 e2e 断言与迁移期对照。
 *
 * 并存白名单（设计内的合法瞬态）：
 *   thumbDetached 升级窗口：thumbDragState+dragState（L20016 先写 drag 后清 thumb，靠代码顺序）
 */
(function (global) {
    'use strict';

    // 交互态探针清单：名字 → 读取函数（主文件经 configure 注入）
    var probes = [];
    var whitelists = [
        // 两条以函数表达：返回 true 表示该组合是设计内瞬态
        function (names) {
            return names.indexOf('thumbDragState') >= 0 && names.indexOf('dragState') >= 0
                && names.length === 2;
        }
    ];

    var dbg = { samples: 0, multistateCount: 0, peak: 0, combos: {}, lastCombos: [], lastActive: [] };

    function configure(opts) {
        if (Array.isArray(opts.probes)) probes = probes.concat(opts.probes);
        if (Array.isArray(opts.whitelist)) whitelists = whitelists.concat(opts.whitelist);
    }

    function tick() {
        dbg.samples++;
        var active = [];
        for (var i = 0; i < probes.length; i++) {
            try {
                if (probes[i].get()) active.push(probes[i].name);
            } catch (_e) { /* 探针永不影响页面 */ }
        }
        dbg.lastActive = active;   // 供状态机 audit 比对当前 mode
        try {
            if (global.CanvasInteractionMachine && global.CanvasInteractionMachine.audit) {
                global.CanvasInteractionMachine.audit();
            }
        } catch (_e) { /* 审计永不影响页面 */ }
        if (active.length > dbg.peak) dbg.peak = active.length;
        if (active.length >= 2) {
            var whitelisted = false;
            for (var w = 0; w < whitelists.length; w++) {
                try { if (whitelists[w](active)) { whitelisted = true; break; } } catch (_e) {}
            }
            if (!whitelisted) {
                dbg.multistateCount++;
                var key = active.slice().sort().join('+');
                dbg.combos[key] = (dbg.combos[key] || 0) + 1;
                dbg.lastCombos.push(key);
                if (dbg.lastCombos.length > 20) dbg.lastCombos.shift();
                if (global.console && console.warn) console.warn('SM_MULTISTATE ' + key);
            }
        }
    }

    global.CanvasInteractionObserver = { configure: configure, tick: tick, dbg: dbg };
})(typeof window !== 'undefined' ? window : globalThis);

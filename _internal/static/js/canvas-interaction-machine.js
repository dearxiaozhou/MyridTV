/* MyridTV 画布交互状态机（拆模块⑩·第2步：影子模式骨架）
 *
 * 目标（八步计划的 2~5）：让「任一时刻只有一种画布指针交互」从约定变成可断言的事实。
 *
 * 本阶段是**影子机器**：begin/end 只记录 mode 与违规计数，权威状态仍在
 * smart-canvas.js 的 panState 等旧变量里（双写过渡，零行为变更）。
 * 每个交互态迁移进机器后，旧代码继续读旧变量直到全量迁完再删除。
 *
 * mode 集合（规划）：idle / panning / dragging-node / box-selecting / connecting /
 *                   resizing / cutting / minimap-panning
 * 违规定义：begin(X) 时 mode !== 'idle'（除白名单瞬态）。
 */
(function (global) {
    'use strict';

    var mode = 'idle';
    var began = {};           // 当前活跃态 -> payload（含起始时间戳）
    var dbg = {
        enabled: true,
        mode: 'idle',
        transitions: 0,
        violations: 0,
        divergences: 0,      // 巨链里「状态非空但 mode 不配」=记账漏网/行为债，第5步核心指标
        dispatchDiff: 0,     // 5步b：按链优先级模拟选出的态 ≠ machine.current() 的次数
        dispatchLog: [],     // 最近 20 条：{chain, mode, at}
        violationLog: [],     // 最近 20 条：{from,to,at}
        divergenceLog: [],    // 最近 20 条：{state,mode,at}
        stickyEndCount: 0     // end(未知态) 次数 = 复位路径遗漏的信号
    };

    // 白名单：允许并存的过渡瞬态组合（迁移期逐个消灭后清空的清单）
    var overlaps = [];

    // —— 第7步：粘滞标志收编 ——
    // 把散落在主文件的「指针手势后抑制后续点击」标志（didPan / suppressNodeClickUntil）
    // 归一为一张可查询、可断言的表。两种生命周期精确复刻原布尔/时间戳语义：
    //   setSticky(key, Infinity) = 旧 `flag = true`（不定长，直到 clearSticky）
    //   setSticky(key, ms)       = 旧 `flagUntil = Date.now()+ms`（限时）
    //   stickyActive(key)        = 旧 `if(flag)` / `if(Date.now()<until)`（过期自动清）
    var sticky = {};
    function setSticky(key, ms) { sticky[key] = (ms === Infinity) ? Infinity : Date.now() + (ms || 0); }
    function clearSticky(key) { delete sticky[key]; }
    function stickyActive(key) {
        var t = sticky[key];
        if (t === undefined) return false;
        if (t === Infinity) return true;
        if (Date.now() >= t) { delete sticky[key]; return false; }
        return true;
    }
    function stickySnapshot() {
        var out = {};
        for (var k in sticky) out[k] = (sticky[k] === Infinity) ? 'sticky' : 'timed';
        return out;
    }
    dbg.sticky = sticky;   // e2e 直接读这张表断言粘滞态

    // —— 第6步：Escape 一键取消 ——
    // 主文件按 mode 注册 cancel 钩子（清旧状态+视觉+必要还原）；
    // cancelActive() 在 Escape 时调用当前 mode 的钩子并强制回 idle。
    var cancels = {};
    function registerCancel(modeName, fn) { cancels[modeName] = fn; }
    function cancelActive() {
        var m = mode;
        if (m === 'idle') return false;
        var fn = cancels[m];
        try { if (fn) fn(); } catch (e) {
            if (global.console && console.warn) console.warn('SM_CANCEL error ' + m + ': ' + e);
        }
        // 与 end 栈语义一致：取消只弹掉当前态，并存时回到剩余态（如 box×pan
        // 取消平移后框选继续），否则才归 idle
        if (mode === m) {
            delete began[m];
            var oi = order.indexOf(m);
            if (oi >= 0) order.splice(oi, 1);
            mode = order.length ? order[order.length - 1] : 'idle';
            dbg.mode = mode;
        }
        return m;
    }

    // —— 5步b第二刀：路由权移交 ——
    // routeFn 由主文件 configure 注入（smChainModeProbe：逐字复刻旧链优先级的
    // 单一判定函数）。巨链的 7 个受管分支全部改读 route()，不再各自 if(旧变量)。
    // 「任一时刻只有一种交互」从此由一个函数说了算，且它可被 e2e 直接断言。
    var routeFn = null;
    function route() { return routeFn ? routeFn() : mode; }
    function configure(opts) {
        if (typeof opts.route === 'function') routeFn = opts.route;
    }

    function isOverlapped(next) {
        for (var i = 0; i < overlaps.length; i++) {
            if (overlaps[i](mode, next)) return true;
        }
        return false;
    }

    var order = [];   // begin 顺序栈：白名单并存时 end 回到剩余态而不是硬跳 idle

    function begin(next, payload) {
        dbg.transitions++;
        if (mode !== 'idle' && mode !== next && !isOverlapped(next)) {
            dbg.violations++;
            dbg.violationLog.push({ from: mode, to: next, at: Date.now() });
            if (dbg.violationLog.length > 20) dbg.violationLog.shift();
            if (global.console && console.warn) console.warn('SM_VIOLATION begin ' + next + ' while ' + mode);
        }
        mode = next;
        began[next] = payload || true;
        var oi = order.indexOf(next);
        if (oi >= 0) order.splice(oi, 1);
        order.push(next);
        dbg.mode = mode;
        return true;
    }

    function end(next) {
        dbg.transitions++;
        delete began[next];
        var oi = order.indexOf(next);
        if (oi >= 0) order.splice(oi, 1);
        if (mode !== next) {
            // 结束的不是当前态：可能是重复 end 或顺序错——记 sticky 信号，不强断言
            dbg.stickyEndCount++;
            if (global.console && console.warn) console.warn('SM_STICKY end ' + next + ' while ' + mode);
            return false;
        }
        // 并存白名单场景：还有别的活跃态则回到最近 begin 的那个（如 box×pan 中
        // 松中键后仍应处于 box-selecting），否则才归 idle
        mode = order.length ? order[order.length - 1] : 'idle';
        dbg.mode = mode;
        return true;
    }

    // 机器接管前的登记辅助（探针/调试用）
    function current() { return mode; }
    function reset() { mode = 'idle'; began = {}; order = []; dbg.mode = mode; }

    // —— 审计（第5步量化）：观察者探到的旧状态 vs 机器 mode 是否一致 ——
    // state→mode 权威映射：任何被探到的活跃态若不是当前 mode（且不在并存白名单），
    // 即 divergence=记账漏网或行为债。idle 时不允许任何受管态活跃。
    var STATE_TO_MODE = {
        panState: 'panning',
        selectionState: 'box-selecting',
        dragState: 'dragging-node',
        portDragState: 'connecting',
        resizeState: 'resizing',
        connectionCutState: 'cutting',
        minimapDrag: 'minimap-panning',
        promptResizeState: 'prompt-resize',
        thumbDragState: 'thumb-drag',
        inputThumbDragState: 'input-thumb-drag',
        previewCompareDrag: 'preview-compare',
        panoramaDrag: 'panorama-drag',
        previewPanDrag: 'preview-pan',
        imageEditPanDrag: 'image-edit-pan',
        cropDrag: 'crop-drag'
    };

    function audit() {
        var O = global.CanvasInteractionObserver;
        if (!O || !O.dbg || !Array.isArray(O.dbg.lastActive)) return;
        var active = O.dbg.lastActive;
        for (var i = 0; i < active.length; i++) {
            var st = active[i];
            var expect = STATE_TO_MODE[st];
            if (!expect) continue;                     // 模态内 5 态等未接管态不参与审计
            if (expect === mode) continue;             // 一致
            if (mode !== 'idle' && isOverlapped(expect)) continue;  // 白名单瞬态（如 box×pan）
            dbg.divergences++;
            dbg.divergenceLog.push({ state: st, expect: expect, mode: mode, at: Date.now() });
            if (dbg.divergenceLog.length > 20) dbg.divergenceLog.shift();
        }
        // 机器自认为在某态、对应状态却不在活跃集合 = end 漏记
        if (mode !== 'idle') {
            var found = false;
            for (var k in STATE_TO_MODE) {
                if (STATE_TO_MODE[k] === mode && active.indexOf(k) >= 0) { found = true; break; }
            }
            if (!found) {
                dbg.divergences++;
                dbg.divergenceLog.push({ state: '(none)', expect: mode, mode: mode, at: Date.now() });
                if (dbg.divergenceLog.length > 20) dbg.divergenceLog.shift();
            }
        }
    }

    // —— 5步b dispatch 影子：主文件链顶每帧把「按旧链优先级模拟出的态」送进来比对。
    // 不改路由、不改行为，只量化差异；差异清零（或只剩已知债）才允许第二刀换真路由。
    function dispatchShadow(chainMode) {
        if (chainMode === mode) return;
        dbg.dispatchDiff++;
        dbg.dispatchLog.push({ chain: chainMode, mode: mode, at: Date.now() });
        if (dbg.dispatchLog.length > 20) dbg.dispatchLog.shift();
    }

    global.CanvasInteractionMachine = {
        configure: configure,
        registerCancel: registerCancel,
        cancelActive: cancelActive,
        setSticky: setSticky,
        clearSticky: clearSticky,
        stickyActive: stickyActive,
        stickySnapshot: stickySnapshot,
        begin: begin,
        end: end,
        route: route,
        current: current,
        reset: reset,
        audit: audit,
        dispatchShadow: dispatchShadow,
        dbg: dbg,
        addOverlapWhitelist: function (fn) { if (typeof fn === 'function') overlaps.push(fn); }
    };
})(typeof window !== 'undefined' ? window : globalThis);

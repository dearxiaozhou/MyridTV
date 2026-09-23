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
        violationLog: [],     // 最近 20 条：{from,to,at}
        divergenceLog: [],    // 最近 20 条：{state,mode,at}
        stickyEndCount: 0     // end(未知态) 次数 = 复位路径遗漏的信号
    };

    // 白名单：允许并存的过渡瞬态组合（迁移期逐个消灭后清空的清单）
    var overlaps = [];

    function isOverlapped(next) {
        for (var i = 0; i < overlaps.length; i++) {
            if (overlaps[i](mode, next)) return true;
        }
        return false;
    }

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
        dbg.mode = mode;
        return true;
    }

    function end(next) {
        dbg.transitions++;
        if (mode !== next) {
            // 结束的不是当前态：可能是重复 end 或顺序错——记 sticky 信号，不强断言
            dbg.stickyEndCount++;
            if (global.console && console.warn) console.warn('SM_STICKY end ' + next + ' while ' + mode);
            return false;
        }
        mode = 'idle';
        delete began[next];
        dbg.mode = mode;
        return true;
    }

    // 机器接管前的登记辅助（探针/调试用）
    function current() { return mode; }
    function reset() { mode = 'idle'; began = {}; dbg.mode = mode; }

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
        minimapDrag: 'minimap-panning'
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

    global.CanvasInteractionMachine = {
        begin: begin,
        end: end,
        current: current,
        reset: reset,
        audit: audit,
        dbg: dbg,
        addOverlapWhitelist: function (fn) { if (typeof fn === 'function') overlaps.push(fn); }
    };
})(typeof window !== 'undefined' ? window : globalThis);

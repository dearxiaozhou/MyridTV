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
        violationLog: [],     // 最近 20 条：{from,to,at}
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

    global.CanvasInteractionMachine = {
        begin: begin,
        end: end,
        current: current,
        reset: reset,
        dbg: dbg,
        addOverlapWhitelist: function (fn) { if (typeof fn === 'function') overlaps.push(fn); }
    };
})(typeof window !== 'undefined' ? window : globalThis);

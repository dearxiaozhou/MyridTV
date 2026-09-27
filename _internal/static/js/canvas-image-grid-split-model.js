/* Calculates ordered image-grid crop rectangles for preset and custom cut lines. */
(function(global){
    'use strict';

    function clampGap(value){return Math.max(0, Math.min(240, Number(value || 0)));}

    function presetRects(width, height, rows, cols, gap){
        const rowCount = Number(rows), colCount = Number(cols), halfGap = clampGap(gap) / 2, rects = [];
        for(let row = 0; row < rowCount; row++){
            const top = row * height / rowCount, bottom = (row + 1) * height / rowCount;
            const y1 = Math.round(row === 0 ? 0 : top + halfGap);
            const y2 = Math.round(row === rowCount - 1 ? height : bottom - halfGap);
            for(let col = 0; col < colCount; col++){
                const left = col * width / colCount, right = (col + 1) * width / colCount;
                const x1 = Math.round(col === 0 ? 0 : left + halfGap);
                const x2 = Math.round(col === colCount - 1 ? width : right - halfGap);
                if(x2 > x1 && y2 > y1) rects.push({row, col, x:x1, y:y1, w:x2 - x1, h:y2 - y1});
            }
        }
        return rects;
    }

    function customRects(width, height, lines, gap){
        const halfGap = clampGap(gap) / 2;
        const horizontal = [...new Set((lines || []).filter(line => line.type === 'h').map(line => line.pos * height))].sort((a, b) => a - b);
        const vertical = [...new Set((lines || []).filter(line => line.type === 'v').map(line => line.pos * width))].sort((a, b) => a - b);
        const yCuts = [0, ...horizontal, height], xCuts = [0, ...vertical, width], rects = [];
        for(let row = 0; row < yCuts.length - 1; row++) for(let col = 0; col < xCuts.length - 1; col++){
            const y1 = Math.round(row === 0 ? yCuts[row] : yCuts[row] + halfGap);
            const y2 = Math.round(row === yCuts.length - 2 ? yCuts[row + 1] : yCuts[row + 1] - halfGap);
            const x1 = Math.round(col === 0 ? xCuts[col] : xCuts[col] + halfGap);
            const x2 = Math.round(col === xCuts.length - 2 ? xCuts[col + 1] : xCuts[col + 1] - halfGap);
            if(x2 > x1 && y2 > y1) rects.push({row, col, x:x1, y:y1, w:x2 - x1, h:y2 - y1});
        }
        return rects;
    }

    function rects(width, height, options={}){
        if(options.custom) return customRects(width, height, options.customLines, options.gap);
        return presetRects(width, height, options.rows, options.cols, options.gap);
    }

    function layoutFromRects(rectangles, groupId){
        const list = rectangles || [];
        return {
            type:'grid-split',
            groupId,
            rows:Math.max(1, ...list.map(rect => Number(rect.row || 0) + 1)),
            cols:Math.max(1, ...list.map(rect => Number(rect.col || 0) + 1))
        };
    }

    global.CanvasImageGridSplitModel = {clampGap, rects, presetRects, customRects, layoutFromRects};
})(typeof window !== 'undefined' ? window : globalThis);

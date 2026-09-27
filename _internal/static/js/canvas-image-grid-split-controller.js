/* Owns custom grid-cut interaction state and the image-grid preview drawing. */
(function(global){
    'use strict';

    const state = {custom:false, lines:[], orientation:'h', history:[], drag:null};
    const deps = {
        getDrawCanvas:() => null,
        getCropCanvas:() => null,
        getEditorMode:() => '',
        getGridSettings:() => ({rows:1, cols:1, gap:0}),
        getRawGap:() => 0,
        translate:key => key
    };

    function configure(options){Object.assign(deps, options || {});}
    function copyLines(lines){return (lines || []).map(line => ({...line}));}
    function isCustomMode(){return state.custom;}
    function isDragging(){return Boolean(state.drag);}
    function endLineEdit(){state.drag = null;}
    function snapshot(){
        return {
            custom:state.custom,
            lines:copyLines(state.lines),
            orientation:state.orientation,
            historyDepth:state.history.length,
            dragging:Boolean(state.drag)
        };
    }

    function reset(){
        state.custom = false;
        state.lines = [];
        state.orientation = 'h';
        state.history = [];
        state.drag = null;
    }

    function applyPreset(){
        state.custom = false;
        state.lines = [];
        state.history = [];
        state.drag = null;
    }

    function toggleCustomMode(){
        state.custom = !state.custom;
        if(state.custom){
            state.lines = [];
            state.history = [];
        }
        state.drag = null;
        return state.custom;
    }

    function setOrientation(orientation){state.orientation = orientation;}

    function clearLines(){
        state.history = [];
        state.lines = [];
        state.drag = null;
    }

    function undoLine(){
        if(!state.history.length) return false;
        state.lines = state.history.pop();
        state.drag = null;
        return true;
    }

    function canUndo(){return state.history.length > 0;}

    function setLinePosition(index, point, width, height){
        const line = state.lines[index];
        if(!line) return;
        line.pos = line.type === 'h'
            ? Math.max(0.001, Math.min(0.999, point.y / Math.max(1, height)))
            : Math.max(0.001, Math.min(0.999, point.x / Math.max(1, width)));
    }

    function lineAt(point, width, height){
        const threshold = Math.max(8, Math.min(width, height) / 80);
        let best = -1, bestDistance = Infinity;
        state.lines.forEach((line, index) => {
            const distance = line.type === 'h'
                ? Math.abs(point.y - line.pos * height)
                : Math.abs(point.x - line.pos * width);
            if(distance < bestDistance && distance <= threshold){best = index; bestDistance = distance;}
        });
        return best;
    }

    function beginLineEdit(point, width, height, pointerId){
        if(!state.custom) return false;
        const hit = lineAt(point, width, height);
        state.history.push(copyLines(state.lines));
        if(hit >= 0){
            state.drag = {index:hit, pointerId};
            setLinePosition(hit, point, width, height);
        } else {
            const line = {
                type:state.orientation,
                pos:state.orientation === 'h' ? point.y / height : point.x / width
            };
            state.lines.push(line);
            state.drag = {index:state.lines.length - 1, pointerId};
        }
        return true;
    }

    function moveLineEdit(point, width, height){
        if(!state.drag) return false;
        setLinePosition(state.drag.index, point, width, height);
        return true;
    }

    function rects(width, height, settings){
        return global.CanvasImageGridSplitModel.rects(width, height, {
            ...(settings || {}), custom:state.custom, customLines:state.lines
        });
    }

    function layoutFromRects(rectangles, groupId){
        return global.CanvasImageGridSplitModel.layoutFromRects(rectangles, groupId);
    }

    function syncCursor(){
        const element = deps.getCropCanvas();
        if(!element) return;
        const custom = deps.getEditorMode() === 'grid' && state.custom;
        element.classList.toggle('grid-custom-h', custom && state.orientation === 'h');
        element.classList.toggle('grid-custom-v', custom && state.orientation === 'v');
    }

    function refreshPreview(){
        const canvas = deps.getDrawCanvas();
        if(!canvas) return;
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        if(deps.getEditorMode() !== 'grid') return;
        const count = global.document.getElementById('gridSplitCount');
        const lineWidth = Math.max(2, Math.round(Math.min(canvas.width, canvas.height) / 320));
        const drawLine = (x1, y1, x2, y2) => {
            ctx.save();
            ctx.lineWidth = lineWidth + 2;
            ctx.strokeStyle = 'rgba(0,0,0,0.72)';
            ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
            ctx.lineWidth = lineWidth;
            ctx.strokeStyle = 'rgba(255,255,255,0.92)';
            ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
            ctx.restore();
        };
        if(state.custom){
            const gap = Math.max(0, Math.min(240, Number(deps.getRawGap() || 0)));
            const horizontal = state.lines.filter(line => line.type === 'h');
            const vertical = state.lines.filter(line => line.type === 'v');
            if(count) count.textContent = deps.translate('canvas.gridWillOutput').replace('{n}', (horizontal.length + 1) * (vertical.length + 1));
            horizontal.forEach(line => {
                const y = line.pos * canvas.height;
                if(gap > 0){drawLine(0, y - gap / 2, canvas.width, y - gap / 2); drawLine(0, y + gap / 2, canvas.width, y + gap / 2);}
                else drawLine(0, y, canvas.width, y);
            });
            vertical.forEach(line => {
                const x = line.pos * canvas.width;
                if(gap > 0){drawLine(x - gap / 2, 0, x - gap / 2, canvas.height); drawLine(x + gap / 2, 0, x + gap / 2, canvas.height);}
                else drawLine(x, 0, x, canvas.height);
            });
            return;
        }

        const settings = deps.getGridSettings();
        if(count) count.textContent = deps.translate('canvas.gridWillOutput').replace('{n}', settings.rows * settings.cols);
        for(let col = 1; col < settings.cols; col++){
            const x = col * canvas.width / settings.cols;
            if(settings.gap > 0){drawLine(x - settings.gap / 2, 0, x - settings.gap / 2, canvas.height); drawLine(x + settings.gap / 2, 0, x + settings.gap / 2, canvas.height);}
            else drawLine(x, 0, x, canvas.height);
        }
        for(let row = 1; row < settings.rows; row++){
            const y = row * canvas.height / settings.rows;
            if(settings.gap > 0){drawLine(0, y - settings.gap / 2, canvas.width, y - settings.gap / 2); drawLine(0, y + settings.gap / 2, canvas.width, y + settings.gap / 2);}
            else drawLine(0, y, canvas.width, y);
        }
    }

    global.CanvasImageGridSplitController = {
        configure, reset, applyPreset, toggleCustomMode, setOrientation, clearLines, undoLine, canUndo,
        isCustomMode, isDragging, endLineEdit, snapshot, beginLineEdit, moveLineEdit,
        rects, layoutFromRects, syncCursor, refreshPreview
    };
})(typeof window !== 'undefined' ? window : globalThis);

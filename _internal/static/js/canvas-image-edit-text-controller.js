/* Owns image-editor text annotations, selection, dragging, and inline editing. */
(function(global){
    'use strict';

    const state = {items:[], selectedId:'', drag:null, dirty:false, inlineEditor:null};
    const deps = {
        getCanvas:() => null,
        getCropCanvas:() => null,
        getMode:() => '',
        getBrushTool:() => '',
        getBrushSize:() => 20,
        getBrushColor:() => '#ff2d55',
        getDefaultText:() => '双击编辑',
        getPoint:event => ({x:Number(event?.clientX) || 0, y:Number(event?.clientY) || 0}),
        createId:() => `txt-${Date.now()}-${Math.random()}`,
        pushHistory:() => {}
    };

    function configure(options){Object.assign(deps, options || {});}
    function getItems(){return state.items;}
    function setItems(items){state.items = (items || []).map(item => ({...item}));}
    function getSelectedId(){return state.selectedId;}
    function setSelectedId(id){state.selectedId = id || '';}
    function selectedItem(){return state.items.find(item => item.id === state.selectedId) || null;}
    function markClean(){state.dirty = false;}
    function resetInteraction(){state.drag = null; state.dirty = false;}
    function resetState(){state.items = []; state.selectedId = ''; resetInteraction();}
    function snapshotState(){
        return {items:state.items.map(item => ({...item})), selectedId:state.selectedId,
            dragging:Boolean(state.drag), dirty:state.dirty, inlineEditing:Boolean(state.inlineEditor)};
    }

    function defaultText(){return deps.getDefaultText();}
    function sizeFromBrush(){return Math.max(14, Math.min(120, Math.round(deps.getBrushSize() * 2)));}
    function createItem(text, point, preset={}){
        const size = Math.max(10, Math.min(120, Number(preset.size) || sizeFromBrush()));
        return {id:deps.createId(), text:String(text || defaultText()).trim(), x:Number(point?.x || 0), y:Number(point?.y || 0), color:preset.color || deps.getBrushColor(), size};
    }
    function itemFont(item){
        const size = Math.max(10, Math.min(120, Number(item?.size) || 28));
        return `900 ${size}px Arial, sans-serif`;
    }
    function measure(item, context=null){
        const ctx = context || deps.getCanvas()?.getContext('2d');
        if(!item || !ctx) return {x:0, y:0, w:0, h:0};
        const size = Math.max(10, Math.min(120, Number(item.size) || 28));
        ctx.save();
        ctx.font = itemFont(item);
        const metrics = ctx.measureText(String(item.text || ''));
        ctx.restore();
        const width = Math.max(1, metrics.width || 1);
        const ascent = Number.isFinite(metrics.actualBoundingBoxAscent) ? metrics.actualBoundingBoxAscent : size * 0.8;
        const descent = Number.isFinite(metrics.actualBoundingBoxDescent) ? metrics.actualBoundingBoxDescent : size * 0.25;
        const pad = Math.max(4, Math.round(size * 0.18));
        return {x:item.x - width / 2 - pad, y:item.y - (ascent + descent) / 2 - pad,
            w:width + pad * 2, h:ascent + descent + pad * 2, textW:width, textH:ascent + descent, pad};
    }
    function hit(point){
        const canvas = deps.getCanvas();
        const ctx = canvas?.getContext('2d');
        if(!ctx) return null;
        for(let index = state.items.length - 1; index >= 0; index--){
            const item = state.items[index];
            const box = measure(item, ctx);
            if(point.x >= box.x && point.x <= box.x + box.w && point.y >= box.y && point.y <= box.y + box.h) return item;
        }
        return null;
    }
    function canvasScale(){
        const canvas = deps.getCanvas();
        const rect = canvas?.getBoundingClientRect?.();
        return {x:(rect?.width || canvas?.width || 1) / Math.max(1, canvas?.width || 1),
            y:(rect?.height || canvas?.height || 1) / Math.max(1, canvas?.height || 1), rect};
    }
    function inlineText(){
        const editor = state.inlineEditor;
        return String(editor?.el?.innerText || editor?.el?.textContent || '').replace(/\u00a0/g, ' ');
    }
    function autosizeInlineEditor(){
        const editor = state.inlineEditor;
        if(!editor?.el) return;
        const el = editor.el;
        el.style.width = 'auto'; el.style.height = 'auto';
        el.style.width = `${Math.max(Number(editor.minW || 48), el.scrollWidth + 10)}px`;
        el.style.height = `${Math.max(Number(editor.minH || 28), el.scrollHeight + 4)}px`;
    }
    function positionInlineEditor(){
        const editor = state.inlineEditor;
        if(!editor?.el) return;
        const item = state.items.find(entry => entry.id === editor.itemId);
        const canvas = deps.getCanvas();
        const cropCanvas = deps.getCropCanvas();
        if(!item || !canvas || !cropCanvas) return;
        const box = measure(item, canvas.getContext('2d'));
        const scale = canvasScale();
        const hostRect = cropCanvas.getBoundingClientRect();
        const canvasRect = scale.rect || canvas.getBoundingClientRect();
        const left = canvasRect.left - hostRect.left + box.x * scale.x;
        const top = canvasRect.top - hostRect.top + box.y * scale.y;
        const width = Math.max(48, box.w * scale.x);
        const height = Math.max(28, box.h * scale.y);
        editor.minW = width; editor.minH = height;
        editor.el.style.left = `${left}px`; editor.el.style.top = `${top}px`;
        editor.el.style.minWidth = `${width}px`; editor.el.style.minHeight = `${height}px`;
        editor.el.style.font = `900 ${Math.max(10, (Number(item.size) || 28) * scale.y)}px Arial, sans-serif`;
        editor.el.style.color = item.color || deps.getBrushColor();
        autosizeInlineEditor();
    }
    function render(){
        const canvas = deps.getCanvas();
        const ctx = canvas?.getContext('2d');
        if(!canvas || !ctx) return;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        state.items.forEach(item => {
            if(!item?.text) return;
            const selected = item.id === state.selectedId;
            const box = measure(item, ctx);
            ctx.save();
            ctx.font = itemFont(item); ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
            ctx.fillStyle = item.color || deps.getBrushColor();
            ctx.strokeStyle = 'rgba(255,255,255,.92)';
            ctx.lineWidth = Math.max(2, (Number(item.size) || 28) / 8);
            ctx.strokeText(String(item.text || ''), item.x, item.y);
            ctx.fillText(String(item.text || ''), item.x, item.y);
            if(selected){
                ctx.setLineDash([7, 5]); ctx.lineWidth = 1.5; ctx.strokeStyle = 'rgba(31,31,31,.72)';
                ctx.strokeRect(box.x, box.y, box.w, box.h);
                ctx.setLineDash([]); ctx.fillStyle = 'rgba(31,31,31,.92)';
                ctx.beginPath(); ctx.arc(item.x + box.w / 2 - box.pad, item.y - box.h / 2 + box.pad, 3.5, 0, Math.PI * 2); ctx.fill();
            }
            ctx.restore();
        });
        positionInlineEditor();
    }
    function syncToolState(){
        deps.getCropCanvas()?.classList.toggle('text-mode', deps.getMode() === 'brush' && deps.getBrushTool() === 'text');
    }
    function beginChange(){
        if(state.dirty) return;
        deps.pushHistory();
        state.dirty = true;
    }
    function syncSelectedStyleFromBrush(){
        if(deps.getMode() !== 'brush' || deps.getBrushTool() !== 'text' || state.inlineEditor) return;
        const item = selectedItem();
        if(!item) return;
        const size = sizeFromBrush();
        const color = deps.getBrushColor();
        if(item.size === size && item.color === color) return;
        beginChange(); item.size = size; item.color = color; render(); syncToolState();
    }
    function setSelected(id){state.selectedId = id || ''; render(); syncToolState();}
    function confirmSelected(){
        const item = selectedItem();
        if(!item) return false;
        if(!String(item.text || '').trim()) state.items = state.items.filter(entry => entry.id !== item.id);
        state.selectedId = ''; state.drag = null; state.dirty = false;
        render(); syncToolState();
        return true;
    }
    function selectInlineEditorText(element){
        const range = global.document.createRange();
        range.selectNodeContents(element);
        const selection = global.getSelection();
        selection.removeAllRanges(); selection.addRange(range);
    }
    function removeInlineEditor(commit=true){
        const editor = state.inlineEditor;
        if(!editor) return;
        const item = state.items.find(entry => entry.id === editor.itemId);
        const next = inlineText().trim();
        state.inlineEditor = null;
        editor.el.remove();
        if(!item) return;
        if(commit){
            if(next !== String(editor.before || '')){
                beginChange();
                if(next) item.text = next;
                else {state.items = state.items.filter(entry => entry.id !== item.id); state.selectedId = '';}
            }
        } else {
            item.text = editor.before || item.text || deps.getDefaultText();
        }
        state.dirty = false;
        render(); syncToolState();
    }
    function beginInline(item){
        if(!item) return;
        removeInlineEditor(true);
        state.selectedId = item.id;
        const host = deps.getCropCanvas();
        if(!host) return;
        const element = global.document.createElement('div');
        element.className = 'edit-text-inline'; element.contentEditable = 'true'; element.spellcheck = false;
        element.textContent = item.text || deps.getDefaultText();
        host.appendChild(element);
        state.inlineEditor = {el:element, itemId:item.id, before:item.text || ''};
        positionInlineEditor();
        element.addEventListener('input', autosizeInlineEditor);
        element.addEventListener('keydown', event => {
            if(event.key === 'Enter' && !event.shiftKey){event.preventDefault(); event.stopPropagation(); removeInlineEditor(true);}
            else if(event.key === 'Escape'){event.preventDefault(); event.stopPropagation(); removeInlineEditor(false);}
        });
        element.addEventListener('blur', () => removeInlineEditor(true));
        global.requestAnimationFrame(() => {element.focus(); selectInlineEditorText(element);});
        render(); syncToolState();
    }
    function begin(event){
        if(deps.getMode() !== 'brush' || deps.getBrushTool() !== 'text') return;
        event.preventDefault(); event.stopPropagation();
        removeInlineEditor(true);
        const canvas = deps.getCanvas();
        const point = deps.getPoint(event);
        const item = hit(point);
        if(item){
            state.selectedId = item.id;
            state.drag = {id:item.id, pointerId:event.pointerId, startX:item.x, startY:item.y, sx:event.clientX, sy:event.clientY, moved:false, hasHistory:false};
            canvas.setPointerCapture?.(event.pointerId); canvas.style.cursor = 'grabbing';
            syncToolState(); render();
            return;
        }
        if(selectedItem()){confirmSelected(); return;}
        beginChange();
        const created = createItem(deps.getDefaultText(), point, {color:deps.getBrushColor(), size:sizeFromBrush()});
        state.items.push(created); state.selectedId = created.id;
        canvas.style.cursor = 'text'; render(); syncToolState();
    }
    function updateCursor(event){
        const canvas = deps.getCanvas();
        if(!canvas || deps.getMode() !== 'brush' || deps.getBrushTool() !== 'text') return;
        canvas.style.cursor = hit(deps.getPoint(event)) ? 'move' : 'text';
    }
    function move(event){
        if(!state.drag){updateCursor(event); return;}
        event.preventDefault(); event.stopPropagation();
        const item = state.items.find(entry => entry.id === state.drag.id);
        if(!item) return;
        const dx = event.clientX - state.drag.sx, dy = event.clientY - state.drag.sy;
        if(!state.drag.moved && Math.abs(dx) + Math.abs(dy) < 2) return;
        state.drag.moved = true;
        if(!state.drag.hasHistory){beginChange(); state.drag.hasHistory = true;}
        const canvas = deps.getCanvas();
        const rect = canvas?.getBoundingClientRect?.();
        const scaleX = canvas ? canvas.width / Math.max(1, rect?.width || canvas.width) : 1;
        const scaleY = canvas ? canvas.height / Math.max(1, rect?.height || canvas.height) : 1;
        item.x = state.drag.startX + dx * scaleX;
        item.y = state.drag.startY + dy * scaleY;
        render();
    }
    function end(event){
        if(state.drag && event?.pointerId != null) deps.getCanvas()?.releasePointerCapture?.(event.pointerId);
        state.drag = null; state.dirty = false;
        render(); syncToolState();
        if(event) updateCursor(event);
    }
    function hasContent(){return state.items.some(item => String(item?.text || '').trim().length > 0);}

    global.CanvasImageEditTextController = {
        configure, getItems, setItems, getSelectedId, setSelectedId, selectedItem, snapshotState,
        resetState, resetInteraction, markClean, defaultText, sizeFromBrush, createItem, itemFont, measure, hit,
        render, syncToolState, syncSelectedStyleFromBrush, beginChange, setSelected, confirmSelected,
        canvasScale, removeInlineEditor, beginInline, positionInlineEditor, begin, move, end, hasContent
    };
})(typeof window !== 'undefined' ? window : globalThis);

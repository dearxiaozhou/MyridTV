/* Owns undo/redo snapshots for mask and brush editing on image nodes. */
(function(global){
    'use strict';

    const HISTORY_LIMIT = 40;
    const state = {undo:[], redo:[]};
    const deps = {
        getDrawCanvas:() => null,
        getTextCanvas:() => null,
        getTextItems:() => [],
        setTextItems:() => {},
        getSelectedTextId:() => '',
        setSelectedTextId:() => {},
        getLabelCounter:() => 1,
        setLabelCounter:() => {},
        removeInlineEditor:() => {},
        renderTextCanvas:() => {},
        syncTextToolState:() => {},
        resetTextInteraction:() => {},
        hasContent:() => false
    };

    function configure(options){Object.assign(deps, options || {});}
    function snapshot(){
        const canvas = deps.getDrawCanvas();
        return {
            imageData:canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height),
            labelCounter:deps.getLabelCounter(),
            textItems:(deps.getTextItems() || []).map(item => ({...item})),
            textSelectedId:deps.getSelectedTextId() || ''
        };
    }

    function syncButtons(){
        ['maskUndoBtn','brushUndoBtn'].forEach(id => {
            const button = global.document.getElementById(id);
            if(button){button.disabled = !state.undo.length; button.style.opacity = state.undo.length ? '1' : '.42';}
        });
        ['maskRedoBtn','brushRedoBtn'].forEach(id => {
            const button = global.document.getElementById(id);
            if(button){button.disabled = !state.redo.length; button.style.opacity = state.redo.length ? '1' : '.42';}
        });
    }

    function restore(value){
        if(!value) return;
        deps.removeInlineEditor(false);
        const canvas = deps.getDrawCanvas();
        canvas.getContext('2d').putImageData(value.imageData || value, 0, 0);
        if(value.labelCounter) deps.setLabelCounter(value.labelCounter);
        deps.setTextItems((value.textItems || []).map(item => ({...item})));
        deps.setSelectedTextId(value.textSelectedId || '');
        deps.renderTextCanvas();
        deps.syncTextToolState(true);
    }

    function push(){
        state.undo.push(snapshot());
        if(state.undo.length > HISTORY_LIMIT) state.undo.shift();
        state.redo = [];
        syncButtons();
    }

    function undo(){
        if(!state.undo.length) return false;
        state.redo.push(snapshot());
        restore(state.undo.pop());
        syncButtons();
        return true;
    }

    function redo(){
        if(!state.redo.length) return false;
        state.undo.push(snapshot());
        restore(state.redo.pop());
        syncButtons();
        return true;
    }

    function clear(silent=false){
        deps.removeInlineEditor(false);
        const canvas = deps.getDrawCanvas();
        if(!silent && deps.hasContent()) push();
        canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height);
        const textCanvas = deps.getTextCanvas();
        textCanvas?.getContext('2d')?.clearRect(0, 0, textCanvas.width, textCanvas.height);
        deps.setTextItems([]);
        deps.setSelectedTextId('');
        deps.resetTextInteraction();
        deps.setLabelCounter(1);
        deps.syncTextToolState(true);
        syncButtons();
    }

    function reset(){
        deps.removeInlineEditor(false);
        state.undo = [];
        state.redo = [];
        deps.setLabelCounter(1);
        deps.setTextItems([]);
        deps.setSelectedTextId('');
        deps.resetTextInteraction();
        deps.renderTextCanvas();
        deps.syncTextToolState(true);
        syncButtons();
    }

    function canUndo(){return state.undo.length > 0;}
    function canRedo(){return state.redo.length > 0;}

    global.CanvasImageEditDrawingHistoryController = {
        configure, snapshot, restore, push, undo, redo, clear, reset, syncButtons, canUndo, canRedo,
        historyState:() => ({undo:state.undo.length, redo:state.redo.length})
    };
})(typeof window !== 'undefined' ? window : globalThis);

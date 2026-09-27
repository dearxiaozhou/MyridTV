/* Loop-node controls: bind number, mode, prompt and run interactions. */
(function(global){
    'use strict';

    const deps = {getContext:null};
    function configure(options){Object.assign(deps, options || {});}
    function context(){return deps.getContext ? deps.getContext() : {};}

    function bind(el, node){
        const ctx = context();
        if(!el || !node) return;
        el.querySelectorAll('.loop-smart-control').forEach(control => {
            control.addEventListener('mousedown', event => event.stopPropagation());
            control.addEventListener('click', event => event.stopPropagation());
            control.addEventListener('dblclick', event => event.stopPropagation());
        });
        const numberBounds = key => key === 'loopStart'
            ? {min:1, max:9999}
            : {min:1, max:100};
        const normalizeNumber = (key, rawValue) => {
            const bounds = numberBounds(key);
            return Math.max(bounds.min, Math.min(bounds.max, Number(rawValue) || bounds.min));
        };
        const syncNumberUi = (source, value) => {
            const control = source?.closest?.('.loop-number-control');
            if(!control) return;
            const display = control.querySelector('.loop-number-trigger strong');
            if(display) display.textContent = value;
            control.querySelectorAll('[data-loop-value]').forEach(cell => {
                cell.classList.toggle('active', Number(cell.dataset.loopValue) === value);
            });
        };
        const setNumber = (key, rawValue, rerender=true, source=null) => {
            const value = normalizeNumber(key, rawValue);
            if(key === 'count') node.count = ctx.smartLoopCount({count:value});
            if(key === 'loopStart') node.loopStart = value;
            if(key === 'imageBatchSize') node.imageBatchSize = value;
            ctx.scheduleSave();
            if(rerender) ctx.render();
            else syncNumberUi(source, value);
        };

        el.querySelectorAll('.loop-number-trigger').forEach(btn => {
            btn.onclick = event => {
                event.preventDefault();
                event.stopPropagation();
                const control = btn.closest('.loop-number-control');
                const wasPinned = control.classList.contains('pinned');
                el.querySelectorAll('.loop-number-control.pinned').forEach(item => item.classList.remove('pinned'));
                if(wasPinned && control.contains(document.activeElement)) document.activeElement.blur();
                if(!wasPinned) control.classList.add('pinned');
            };
        });
        el.querySelectorAll('[data-loop-number]').forEach(btn => {
            btn.onclick = event => {
                event.preventDefault();
                event.stopPropagation();
                setNumber(btn.dataset.loopNumber, btn.dataset.loopValue, true);
            };
        });
        el.querySelectorAll('[data-loop-number-input]').forEach(input => {
            input.oninput = event => {
                event.stopPropagation();
                setNumber(input.dataset.loopNumberInput, input.value, false, input);
            };
            input.onchange = event => {
                event.stopPropagation();
                setNumber(input.dataset.loopNumberInput, input.value, true);
            };
        });
        el.querySelectorAll('[data-loop-mode]').forEach(btn => {
            btn.onclick = event => {
                event.preventDefault();
                event.stopPropagation();
                node.mode = btn.dataset.loopMode === 'parallel' ? 'parallel' : 'serial';
                ctx.render();
                ctx.scheduleSave();
            };
        });
        el.querySelectorAll('[data-loop-toggle]').forEach(btn => {
            btn.onclick = event => {
                event.preventDefault();
                event.stopPropagation();
                if(btn.dataset.loopToggle === 'image') node.imageInput = !node.imageInput;
                if(btn.dataset.loopToggle === 'prompt'){
                    node.showPrompt = !node.showPrompt;
                    if(node.showPrompt && !ctx.smartLoopActivePromptFieldValues(node).length){
                        ctx.setSmartLoopPromptFieldValues(node, [ctx.tr('smart.loopDefaultPrompt') || '现在生成第《计数》张卖点图片']);
                    }
                }
                ctx.fitSmartLoopNode(node);
                ctx.render();
                ctx.scheduleSave();
            };
        });
        const syncPromptFieldsFromDom = () => {
            const values = [...el.querySelectorAll('[data-loop-prompt-index]')]
                .sort((a, b) => Number(a.dataset.loopPromptIndex) - Number(b.dataset.loopPromptIndex))
                .map(input => ctx.smartLoopEditorText(input));
            ctx.setSmartLoopPromptFieldValues(node, values);
        };
        let activePromptEditor = null;
        el.querySelectorAll('.loop-smart-text').forEach(text => {
            ctx.bindScrollableText(text);
            text.onfocus = () => { activePromptEditor = text; };
            text.oninput = () => { syncPromptFieldsFromDom(); ctx.scheduleSave(); };
            text.addEventListener('click', event => {
                const remove = event.target.closest?.('.loop-smart-token-chip button');
                if(!remove) return;
                event.preventDefault();
                event.stopPropagation();
                remove.closest('.loop-smart-token-chip')?.remove();
                syncPromptFieldsFromDom();
                ctx.scheduleSave();
            });
        });
        el.querySelectorAll('[data-loop-prompt-add]').forEach(btn => {
            btn.onclick = event => {
                event.preventDefault();
                event.stopPropagation();
                syncPromptFieldsFromDom();
                const values = ctx.smartLoopPromptFieldValues(node);
                ctx.setSmartLoopPromptFieldValues(node, [...values, '']);
                ctx.fitSmartLoopNode(node);
                ctx.render();
                ctx.scheduleSave();
            };
        });
        el.querySelectorAll('[data-loop-prompt-delete]').forEach(btn => {
            btn.onclick = event => {
                event.preventDefault();
                event.stopPropagation();
                syncPromptFieldsFromDom();
                const removeIndex = Number(btn.dataset.loopPromptDelete);
                const values = ctx.smartLoopPromptFieldValues(node);
                if(values.length <= 1) return;
                values.splice(removeIndex, 1);
                ctx.setSmartLoopPromptFieldValues(node, values);
                ctx.fitSmartLoopNode(node);
                ctx.render();
                ctx.scheduleSave();
            };
        });
        const firstText = el.querySelector('.loop-smart-text');
        const targetPromptEditor = () => activePromptEditor && el.contains(activePromptEditor) ? activePromptEditor : firstText;
        el.querySelectorAll('[data-loop-token]').forEach(btn => {
            btn.onclick = event => {
                event.preventDefault();
                event.stopPropagation();
                const text = targetPromptEditor();
                if(!text) return;
                ctx.insertSmartLoopToken(text, btn.dataset.loopToken || '《计数》');
                syncPromptFieldsFromDom();
                ctx.scheduleSave();
            };
        });
        el.querySelectorAll('[data-loop-run]').forEach(btn => {
            btn.onclick = event => {
                event.preventDefault();
                event.stopPropagation();
                const loopId = btn.dataset.loopRun || node.id;
                if(ctx.smartCascadeIsLoopRunning(loopId)){
                    ctx.requestSmartCascadeStop(loopId);
                    return;
                }
                ctx.runSmartCascadeFromLoop(loopId);
            };
        });
    }

    global.CanvasLoopNodeController = {configure, bind};
})(typeof window !== 'undefined' ? window : globalThis);

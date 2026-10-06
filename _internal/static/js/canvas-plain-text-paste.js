/* Keep prompt text in the canvas theme while preserving internal reference chips. */
(function(global){
    'use strict';
    const editorSelector = '#promptInput, .loop-smart-text';
    const chipSelector = '.mention-image-token, .mention-style-token, .loop-smart-token-chip';
    const blocks = new Set(['P','DIV','LI','UL','OL','H1','H2','H3','H4','H5','H6','BLOCKQUOTE','PRE','SECTION','ARTICLE','TR']);

    function cleanFormatting(editor){
        let changed = false;
        for(const el of [...editor.querySelectorAll('*')]){
            if(el.closest(chipSelector)) continue;
            if(['SCRIPT','STYLE','IMG','SVG','IFRAME','OBJECT'].includes(el.tagName)){
                el.remove(); changed = true; continue;
            }
            for(const attr of [...el.attributes]){el.removeAttribute(attr.name); changed = true;}
            if(['BR','DIV','P','UL','OL','LI'].includes(el.tagName)) continue;
            if(blocks.has(el.tagName)){
                const div = editor.ownerDocument.createElement('div');
                div.append(...el.childNodes); el.replaceWith(div);
            } else el.replaceWith(...el.childNodes);
            changed = true;
        }
        return changed;
    }
    function htmlText(html){
        const body = new DOMParser().parseFromString(html,'text/html').body;
        let text = '';
        const line = () => {if(text && !text.endsWith('\n')) text += '\n';};
        function visit(node){
            if(node.nodeType === Node.TEXT_NODE){text += node.nodeValue; return;}
            if(node.nodeType !== Node.ELEMENT_NODE || ['SCRIPT','STYLE'].includes(node.tagName)) return;
            if(node.tagName === 'BR'){text += '\n'; return;}
            const block = blocks.has(node.tagName);
            if(block) line();
            if(node.tagName === 'LI') text += '• ';
            for(const child of node.childNodes) visit(child);
            if(block) line();
            if(['TD','TH'].includes(node.tagName)) text += '\t';
        }
        for(const child of body.childNodes) visit(child);
        return text.replace(/\n$/,'');
    }
    document.addEventListener('paste', event => {
        const editor = event.target.closest?.(editorSelector);
        const data = event.clipboardData;
        if(!editor?.isContentEditable || event.defaultPrevented || !data || data.files.length) return;
        const types = [...data.types];
        if(!types.includes('text/plain') && !types.includes('text/html')) return;
        event.preventDefault();
        event.stopPropagation();
        const text = (types.includes('text/plain') ? data.getData('text/plain') : htmlText(data.getData('text/html'))).replace(/\r\n?/g,'\n');
        if(!text) return;
        let inputFired = false;
        const onInput = () => {inputFired = true;};
        editor.addEventListener('input',onInput);
        try {
            // Only escaped text and line breaks enter the editor. A single editing command
            // preserves undo and avoids Chromium adding extra blank lines for insertText.
            const html = text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>');
            if(!document.execCommand('insertHTML',false,html)){
                const selection = global.getSelection();
                if(!selection?.rangeCount) return;
                const range = selection.getRangeAt(0);
                if(!editor.contains(range.commonAncestorContainer)) return;
                range.deleteContents();
                const node = document.createTextNode(text);
                range.insertNode(node); range.setStartAfter(node); range.collapse(true);
                selection.removeAllRanges(); selection.addRange(range);
            }
        } finally {editor.removeEventListener('input',onInput);}
        if(!inputFired) editor.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertFromPaste',data:text}));
    },true);
    global.CanvasPlainTextPaste = {cleanFormatting};
})(window);

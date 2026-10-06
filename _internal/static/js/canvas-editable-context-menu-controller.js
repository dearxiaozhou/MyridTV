/* Canvas editable context menu: right-click copy / paste / select-all for text fields.
 *
 * Why this exists: the real canvas runs inside a WebView2 host, which suppresses the
 * browser's native context menu. So simply "letting the native menu through" on a
 * textarea does nothing on the real machine — right-click yields no menu and the user
 * is forced back to Ctrl+C / Ctrl+V. This controller owns a canvas-native menu with
 * 复制 / 粘贴 / 全选 that drives the OS clipboard via the Clipboard API (with
 * document.execCommand fallbacks) so pasting text copied from outside the app, and
 * copying a selection inside a field, both work from a right-click.
 *
 * It only handles genuine editable widgets (textarea / input / select / contenteditable).
 * Everything else (node body, thumbnails, blank canvas) is left to the other menus.
 */
(function(global){
    'use strict';

    const deps = {toast:null};
    let currentField = null;

    function configure(options){ Object.assign(deps, options || {}); }

    function close(){
        document.getElementById('smartEditableContextMenu')?.classList.remove('open');
        currentField = null;
    }

    function isOpen(){
        return Boolean(document.getElementById('smartEditableContextMenu')?.classList.contains('open'));
    }

    // Returns the actual editable element, or null when the target is not editable.
    function isEditableTarget(target){
        if(!target || typeof target.closest !== 'function') return null;
        if(target.matches('textarea, input, select, [contenteditable="true"]')) return target;
        return null;
    }

    function hasSelection(field){
        if(typeof field.selectionStart === 'number' && typeof field.selectionEnd === 'number'){
            return field.selectionEnd > field.selectionStart;
        }
        if(field.isContentEditable) return window.getSelection().toString().length > 0;
        return false;
    }

    function getSelectedText(field){
        if(typeof field.selectionStart === 'number' && typeof field.selectionEnd === 'number'){
            return (field.value || '').substring(field.selectionStart, field.selectionEnd);
        }
        if(field.isContentEditable) return window.getSelection().toString();
        return '';
    }

    function ensure(){
        let menu = document.getElementById('smartEditableContextMenu');
        if(menu) return menu;
        menu = document.createElement('div');
        menu.id = 'smartEditableContextMenu';
        menu.className = 'smart-editable-context-menu';
        menu.innerHTML = [
            ['copy', '复制'],
            ['paste', '粘贴'],
            ['select-all', '全选']
        ].map(([action, label]) => `<button type="button" data-edit-action="${action}">${label}</button>`).join('');
        menu.addEventListener('mousedown', event => {
            event.preventDefault();
            event.stopPropagation();
        });
        menu.addEventListener('contextmenu', event => event.stopPropagation());
        menu.addEventListener('click', event => {
            event.preventDefault();
            event.stopPropagation();
            const button = event.target.closest('[data-edit-action]');
            if(!button || button.disabled) return;
            const action = button.dataset.editAction;
            const field = currentField;
            close();
            runAction(action, field);
        });
        document.body.appendChild(menu);
        return menu;
    }

    function copyText(field){
        const text = getSelectedText(field);
        if(!text) return;
        if(navigator.clipboard && navigator.clipboard.writeText){
            navigator.clipboard.writeText(text).catch(() => document.execCommand('copy'));
        } else {
            document.execCommand('copy');
        }
    }

    function applyText(field, text){
        if(text == null || text === '') return;
        field.focus();
        if(typeof field.setRangeText === 'function'){
            const s = field.selectionStart || 0;
            const e = field.selectionEnd || 0;
            field.setRangeText(text, s, e, 'end');
            field.dispatchEvent(new Event('input', {bubbles:true}));
        } else if(field.isContentEditable){
            document.execCommand('insertText', false, text);
        } else {
            document.execCommand('paste');
        }
    }

    function pasteText(field){
        field.focus();
        const viaApi = () => {
            if(navigator.clipboard && navigator.clipboard.readText){
                return navigator.clipboard.readText().then(text => {
                    if(text == null || text === '') throw new Error('empty');
                    applyText(field, text);
                }).catch(() => viaExec());
            }
            return viaExec();
        };
        const viaExec = () => {
            field.focus();
            const ok = document.execCommand('paste');
            if(!ok && deps.toast) deps.toast('粘贴未生效，请直接用 Ctrl+V');
        };
        viaApi();
    }

    function selectAll(field){
        field.focus();
        if(typeof field.select === 'function') field.select();
        else if(typeof field.setSelectionRange === 'function') field.setSelectionRange(0, (field.value || '').length);
        else document.execCommand('selectAll');
    }

    function runAction(action, field){
        if(!field) return;
        if(action === 'copy') return copyText(field);
        if(action === 'paste') return pasteText(field);
        if(action === 'select-all') return selectAll(field);
    }

    function open(field, event){
        if(!field) return false;
        const menu = ensure();
        currentField = field;
        // 没有选区时「复制」禁用，避免点了没反应
        const copyBtn = menu.querySelector('[data-edit-action="copy"]');
        if(copyBtn) copyBtn.disabled = !hasSelection(field);
        const width = 168;
        const height = 3 * 40 + 16;
        menu.style.left = `${Math.max(12, Math.min(global.innerWidth - width - 12, event.clientX + 4))}px`;
        menu.style.top = `${Math.max(12, Math.min(global.innerHeight - height - 12, event.clientY + 4))}px`;
        menu.classList.add('open');
        return true;
    }

    global.CanvasEditableContextMenuController = {configure, ensure, open, close, isOpen, isEditableTarget};

    // 浮层注册表一处声明：mousedown / 中键平移 / 空白点击清选中 都要排除本菜单，
    // 否则点菜单按钮会被画布当成"点了空白/开始平移"把菜单清掉。
    global.CanvasOverlayRegistry?.register('.smart-editable-context-menu,#smartEditableContextMenu', ['overlay', 'pan-exclude', 'click-empty', 'wheel-exclude']);
})(typeof window !== 'undefined' ? window : globalThis);

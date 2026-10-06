/* Canvas node context menu: right-click actions on a node (copy / delete).
 *
 * Why this exists: `shell.oncontextmenu` bails out for anything inside `.image-node`,
 * so empty nodes (no thumbnails) had no right-click menu at all — the image context
 * menu only covers thumbnail hits. This controller owns the node-level menu.
 *
 * Editable controls (textarea / input / contenteditable) are NOT handled here:
 * the shell lets the browser's native context menu through for them so that
 * cut/copy/paste/select-all keep working with the OS clipboard.
 */
(function(global){
    'use strict';

    const deps = {};
    const state = {nodeId:''};

    function configure(options){Object.assign(deps, options || {});}

    function close(){
        document.getElementById('smartNodeContextMenu')?.classList.remove('open');
        state.nodeId = '';
    }

    function isOpen(){
        return Boolean(document.getElementById('smartNodeContextMenu')?.classList.contains('open'));
    }

    // Editable widgets must keep the native menu (cut/copy/paste/select-all).
    function isEditableTarget(target){
        if(!target || typeof target.closest !== 'function') return false;
        return Boolean(target.closest('textarea, input, select, [contenteditable="true"]'));
    }

    function nodeFor(nodeId){
        return deps.getNodes().find(node => node.id === nodeId) || null;
    }

    function ensure(){
        let menu = document.getElementById('smartNodeContextMenu');
        if(menu) return menu;
        menu = document.createElement('div');
        menu.id = 'smartNodeContextMenu';
        menu.className = 'smart-node-context-menu';
        menu.innerHTML = [
            ['duplicate-node', '复制节点'],
            ['copy-node', '复制'],
            ['delete-node', '删除节点']
        ].map(([action, label]) => `<button type="button" data-smart-node-menu-action="${action}">${label}</button>`).join('');
        menu.addEventListener('mousedown', event => {
            event.preventDefault();
            event.stopPropagation();
        });
        menu.addEventListener('contextmenu', event => event.stopPropagation());
        menu.addEventListener('click', event => {
            event.preventDefault();
            event.stopPropagation();
            const button = event.target.closest('[data-smart-node-menu-action]');
            if(!button) return;
            const nodeId = state.nodeId;
            close();
            runAction(button.dataset.smartNodeMenuAction, nodeId);
        });
        document.body.appendChild(menu);
        return menu;
    }

    function runAction(action, nodeId){
        const node = nodeFor(nodeId);
        if(!node) return;
        if(action === 'duplicate-node') return deps.duplicateNodeWithConnections(nodeId);
        if(action === 'copy-node') return deps.copyNodesToClipboard(nodeId);
        if(action === 'delete-node') return deps.deleteNodes([nodeId]);
    }

    // 空节点：图片类节点且没有任何图、也没在生成中。这种节点只保留「复制节点 / 删除节点」，
    // 不提供「复制」（老王的明确要求：空节点右键只留这两个）。
    function isNodeEmpty(node){
        if(!node) return false;
        const t = node.type || 'smart-image';
        if(t !== 'smart-image') return false;
        if((node.images || []).length) return false;
        if(node.pending || node.queued) return false;
        if(node.jimengPending && node.jimengPending.submitId) return false;
        if(node.generatedResult) return false;
        return true;
    }

    function open(nodeId, event){
        const node = nodeFor(nodeId);
        if(!node) return false;
        // Multi-selection: act on the whole selection when this node is part of it.
        const selected = deps.getSelectedNodeIds() || [];
        const ids = (selected.length > 1 && selected.includes(nodeId)) ? selected : [nodeId];
        const menu = ensure();
        state.nodeId = nodeId;
        // Show how many nodes an action will touch.
        const labelSuffix = ids.length > 1 ? `（${ids.length}）` : '';
        const labels = {
            'duplicate-node': `复制节点${labelSuffix}`,
            'copy-node': '复制',
            'delete-node': `删除节点${labelSuffix}`
        };
        menu.querySelectorAll('[data-smart-node-menu-action]').forEach(button => {
            button.textContent = labels[button.dataset.smartNodeMenuAction] || button.textContent;
        });
        // 空节点：隐藏「复制」，只留 复制节点 + 删除节点
        const empty = isNodeEmpty(node);
        const copyBtn = menu.querySelector('[data-smart-node-menu-action="copy-node"]');
        if(copyBtn) copyBtn.style.display = empty ? 'none' : '';
        const visible = menu.querySelectorAll('[data-smart-node-menu-action]').length - (empty ? 1 : 0);
        const width = 168;
        const height = visible * 40 + 16;
        menu.style.left = `${Math.max(12, Math.min(global.innerWidth - width - 12, event.clientX + 4))}px`;
        menu.style.top = `${Math.max(12, Math.min(global.innerHeight - height - 12, event.clientY + 4))}px`;
        menu.classList.add('open');
        deps.bringNodesToFront(ids);
        return true;
    }

    global.CanvasNodeContextMenuController = {configure, ensure, open, close, isOpen, isEditableTarget};

    // 浮层注册表一处声明：mousedown / 中键平移 / 空白点击清选中 都要排除本菜单，
    // 否则点菜单按钮会被画布当成"点了空白/开始平移"把节点选中态和菜单一起清掉。
    // 不注册 wheel-exclude：菜单只有 3 个按钮，滚轮漏到画布缩放无害。
    global.CanvasOverlayRegistry?.register('.smart-node-context-menu,#smartNodeContextMenu', ['overlay', 'pan-exclude', 'click-empty']);
})(typeof window !== 'undefined' ? window : globalThis);

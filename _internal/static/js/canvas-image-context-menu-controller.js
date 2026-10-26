/* Owns the canvas image context menu lifecycle and its image actions. */
(function(global){
    'use strict';

    const deps = {};
    const state = {nodeId:'', imageIndex:-1};
    function configure(options){Object.assign(deps, options || {});}

    function close(){
        document.getElementById('smartImageContextMenu')?.classList.remove('open');
    }

    function nodeFor(nodeId){
        return deps.getNodes().find(node => node.id === nodeId) || null;
    }

    function imageFor(nodeId, imageIndex){
        const node = nodeFor(nodeId);
        return {node, image:(node?.images || [])[Number(imageIndex)] || null};
    }

    function actionIds(){
        return deps.getActionIds() || ['add-agent', 'duplicate-node'];
    }

    function ensure(){
        let style = document.getElementById('smartImageContextMenuStyle');
        if(!style){
            style = document.createElement('style');
            style.id = 'smartImageContextMenuStyle';
            style.textContent = `
            #smartImageContextMenu{position:fixed;display:none;flex-direction:column;min-width:168px;padding:8px;border-radius:8px;border:1px solid var(--line);background:var(--panel);box-shadow:0 18px 40px var(--shadow);backdrop-filter:blur(14px);z-index:2500}
            #smartImageContextMenu.open{display:flex}
            #smartImageContextMenu button{display:flex;align-items:center;justify-content:flex-start;gap:8px;width:100%;padding:10px 12px;border:0;border-radius:8px;background:transparent;color:var(--text);font-size:13px;font-weight:700;cursor:pointer;white-space:nowrap}
            #smartImageContextMenu button:hover{background:var(--x-hover-bg)}
            `;
            document.head.appendChild(style);
        }
        let menu = document.getElementById('smartImageContextMenu');
        if(menu) return menu;
        menu = document.createElement('div');
        menu.id = 'smartImageContextMenu';
        menu.className = 'smart-image-context-menu';
        const labels = {
            'add-agent':'加入Agent',
            'duplicate-node':'复制节点',
            'redirect-input-source':'把线移到新素材',
            'view-image':'查看图片',
            'img2img':'图生图',
            'save-asset':'加入素材库',
            'copy-path':'复制路径',
            'open-folder':'打开文件夹',
            'set-cover':'设置为封面',
            'asset-follow-latest':deps.translate('smart.assetFollowLatest'),
            'asset-pin-version':deps.translate('smart.assetPinVersion'),
            'asset-save-version':deps.translate('smart.assetSaveVersion')
        };
        menu.innerHTML = actionIds().map(action => `<button type="button" data-smart-image-menu-action="${deps.escapeAttr(action)}">${deps.escapeHtml(labels[action] || action)}</button>`).join('');
        menu.addEventListener('mousedown', event => {
            event.preventDefault();
            event.stopPropagation();
        });
        menu.addEventListener('click', async event => {
            event.preventDefault();
            event.stopPropagation();
            const button = event.target.closest('[data-smart-image-menu-action]');
            if(!button) return;
            const {nodeId, imageIndex} = state;
            close();
            await runAction(button.dataset.smartImageMenuAction, nodeId, imageIndex);
        });
        document.body.appendChild(menu);
        return menu;
    }

    async function runAction(action, nodeId, imageIndex){
        const {node, image} = imageFor(nodeId, imageIndex);
        if(action === 'set-cover'){
            if(!image?.url){deps.toast('该图片没有地址，无法设为封面');return;}
            deps.fetcher(`/api/canvases/${encodeURIComponent(deps.getCanvasId())}/meta`, {
                method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cover:image.url})
            }).then(response => {
                if(!response.ok) throw new Error('save failed');
                deps.toast('已设置为画布封面');
            }).catch(() => deps.toast('设置封面失败，请重试'));
            return;
        }
        if(action === 'asset-follow-latest') return deps.setAssetVersionMode(nodeId, imageIndex, 'latest');
        if(action === 'asset-pin-version') return deps.setAssetVersionMode(nodeId, imageIndex, 'pinned');
        if(action === 'asset-save-version') return deps.saveAssetVersion(nodeId, imageIndex);
        if(action === 'add-agent') return deps.addImageNodeRefToAgent(nodeId, imageIndex);
        if(action === 'duplicate-node') return deps.duplicateNodeWithConnections(nodeId);
        if(action === 'view-image'){
            if(node?.images?.[imageIndex]) global.open(node.images[imageIndex].url, '_blank');
            return;
        }
        if(action === 'img2img'){
            if(node && image?.url){
                const rect = deps.nodeRect(node);
                const point = {
                    x:Math.round((Number(node.x) || 0) + (Number(rect.width) || 260) + 260),
                    y:Math.round((Number(node.y) || 0) + (Number(rect.height) || 180) / 2)
                };
                const settings = deps.getSettings();
                const target = deps.createGeneratorNode(point, {engine:settings.engine || 'api', apiKind:'image', title:'图生图'});
                target.runSettings = deps.settingsForStorage({
                    ...deps.cloneSettings(settings),
                    engine:settings.engine || 'api',
                    apiKind:'image'
                });
                deps.connectInputNode(node.id, target.id);
                deps.setSelectedId(target.id);
                deps.setSelectedIds([]);
                deps.setSelectedImage({nodeId:'', index:-1});
                if(deps.isApiLikeEngine(settings.engine)) deps.setApiKind('image');
                deps.syncSelectionUi();
                deps.updateComposer();
                deps.insertImageReferenceIntoPrompt({
                    ...image,
                    url:image.url,
                    name:image.name || '参考图',
                    kind:deps.mediaKindForItem(image),
                    nodeId,
                    imageIndex:Number(imageIndex)
                });
                deps.persistActiveSettings();
                deps.renderDynamicParams();
                deps.render();
                deps.scheduleSave();
                deps.toast('已创建图生图节点并连线');
            }
            return;
        }
        if(action === 'save-asset'){
            if(image?.url){
                try {
                    if(!deps.getAssetLibrary()?.libraries?.length) await deps.loadAssetLibrary();
                    await deps.addUrlToAssetLibrary(image.url, image.name || node?.title || 'image');
                } catch(error){
                    deps.toast((error.message || deps.translate('smart.assetAddFail')).slice(0, 120));
                }
            }
            return;
        }
        if(action === 'copy-path'){
            if(node?.images?.[imageIndex]){
                let url = node.images[imageIndex].url || '';
                if(url.startsWith('/')) url = global.location.origin + url;
                try { global.navigator.clipboard.writeText(url); }
                catch(error) { global.prompt('复制路径', url); }
            }
            return;
        }
        if(action === 'open-folder'){
            const target = nodeId ? imageFor(nodeId, imageIndex).image : null;
            deps.fetcher('/api/open-folder', {
                method:'POST',headers:{'Content-Type':'application/json'},
                body:JSON.stringify({
                    url:target?.url || '',
                    name:target?.source_file_name || target?.file_name || target?.name || '',
                    kind:target?.kind || deps.mediaKindForItem(target) || '',
                    local_path:target?.local_path || target?.localPath || ''
                })
            }).catch(() => {});
        }
        // 已移除 replace-material / revert-media-version（2026-09-27 用户反馈太卡）
        if(action === 'redirect-input-source') return deps.enterRedirectPickMode(nodeId);
    }

    function open(nodeId, imageIndex, event){
        const menu = ensure();
        const node = nodeFor(nodeId);
        if(!menu || !node) return;
        state.nodeId = nodeId;
        state.imageIndex = imageIndex;
        const selectedIds = deps.getSelectedNodeIds();
        const keepMultiSelection = selectedIds.length > 1 && selectedIds.includes(nodeId);
        if(keepMultiSelection){
            deps.setSelectedImage({nodeId, index:imageIndex});
            deps.bringNodesToFront(selectedIds);
        } else {
            deps.setSelectedId(nodeId);
            deps.setSelectedIds([]);
            deps.setSelectedImage({nodeId, index:imageIndex});
            deps.bringNodesToFront(nodeId);
        }
        deps.syncSelectionUi();
        deps.updateComposer();
        const width = 188;
        const height = 108;
        menu.style.left = `${Math.max(12, Math.min(global.innerWidth - width - 12, event.clientX + 4))}px`;
        menu.style.top = `${Math.max(12, Math.min(global.innerHeight - height - 12, event.clientY + 4))}px`;
        const image = (node.images || [])[Number(imageIndex)] || {};
        const hasAssetRef = !!String(image.assetId || '').trim();
        const mode = String(image.assetVersionMode || 'latest').toLowerCase();
        const setItemVisible = (actionId, visible) => {
            const button = menu.querySelector(`[data-smart-image-menu-action="${actionId}"]`);
            if(button) button.style.display = visible ? '' : 'none';
        };
        setItemVisible('asset-follow-latest', hasAssetRef && mode !== 'latest');
        setItemVisible('asset-pin-version', hasAssetRef && mode === 'latest');
        setItemVisible('asset-save-version', hasAssetRef);
        // 已移除 replace-material / revert-media-version 可见性（2026-09-27）
        setItemVisible('redirect-input-source', Array.isArray(node?.images));
        menu.classList.add('open');
    }

    global.CanvasImageContextMenuController = {configure, ensure, open, close};
})(typeof window !== 'undefined' ? window : globalThis);

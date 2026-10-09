/* Applies imported media to image nodes and maintains their single/group shape. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    function uploadTitleForItems(items, fallback='Upload'){
        const list = [...(items || [])];
        if(!list.length) return fallback;
        const kinds = new Set(list.map(item => deps.isFile(item) ? deps.mediaKindForFile(item) : deps.mediaKindForItem(item)));
        // 单素材优先用文件名当标题（2026-10-09）：上传"主角设定.png"标题就叫"主角设定"
        if(list.length === 1){
            const stem = String(list[0]?.name || '').replace(/\.[^.]+$/, '').replace(/[\\/:*?"<>|]+/g, ' ').trim().slice(0, 30);
            if(stem && !['Image','Images','Video','Videos','Audio','Audios','Group','Media'].includes(stem)) return stem;
        }
        if(kinds.size > 1) return list.length > 1 ? 'Media' : fallback;
        if(kinds.has('video')) return list.length > 1 ? 'Videos' : 'Video';
        if(kinds.has('audio')) return 'Audio';
        return list.length > 1 ? 'Group' : 'Image';
    }

    function appendImages(uploaded, targetId='', options={}){
        const images = [...(uploaded || [])].filter(file => file?.url);
        if(!images.length) return null;
        if(options.forceNew && images.length > 1 && typeof deps.createGroupFromImages === 'function'){
            const group = deps.createGroupFromImages(images, options);
            if(group) return group;
        }
        let node = deps.getNodes().find(item => item.id === targetId) || deps.selectedNode();
        if(node && !deps.isImageNode(node)) node = null;
        if(options.forceNew) node = null;
        if(!node){
            const center = options.point || deps.viewportCenter();
            node = deps.createEmptyNodeAt(center);
        }
        if(!node) return null;
        const previousCount = (node.images || []).length;
        // Imported media uses its own aspect; generation frame sizes are only for runs.
        delete node.cardSize;
        delete node.cardSizing;
        // 覆盖模式（replaceIfExists）：节点已有素材时，新上传直接替换旧素材，
        // 不再打组保留多张（上传按钮场景下，用户期望「换一张」而非「再叠一张」）。
        if(options.replaceIfExists && previousCount > 0){
            node.images = images.map(file => ({...file, kind:file.kind || deps.mediaKindForItem(file)}));
        } else {
            node.images = [...(node.images || []), ...images.map(file => ({...file, kind:file.kind || deps.mediaKindForItem(file)}))];
        }
        if(node.images.length > 1){
            node.title = uploadTitleForItems(node.images, 'Group');
            const scale = Number(node.scale);
            if(previousCount <= 1 && (!Number.isFinite(scale) || scale === deps.defaultImageNodeScale || scale === deps.previousGroupNodeScale)){
                node.scale = deps.defaultGroupNodeScale;
            }
            delete node.w;
            delete node.h;
        }
        if(node.images.length === 1){
            node.title = uploadTitleForItems(node.images, node.title || 'Image');
            delete node.w;
            delete node.h;
        }
        deps.setSelectedId(node.id);
        deps.render();
        deps.scheduleSave();
        return node;
    }

    global.CanvasImageNodeMediaController = {configure, uploadTitleForItems, appendImages};
})(typeof window !== 'undefined' ? window : globalThis);

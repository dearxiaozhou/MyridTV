/* Applies imported media to image nodes. Canvas groups are created manually. */
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
        return list.length > 1 ? 'Images' : 'Image';
    }

    function appendImages(uploaded, targetId='', options={}){
        const images = [...(uploaded || [])].filter(file => file?.url).map(file => ({...file, kind:file.kind || deps.mediaKindForItem(file)}));
        if(!images.length) return null;
        let node = deps.getNodes().find(item => item.id === targetId) || deps.selectedNode();
        if(node && !deps.isImageNode(node)) node = null;
        if(options.forceNew) node = null;
        // 2026-10-19（老王：一个节点只装一张图）：目标节点已有素材就不再叠加，
        // 除显式 replaceIfExists（上传按钮「换一张」）外，多出来的图各建一个独立节点。
        if(node && (node.images || []).length && !options.replaceIfExists) node = null;
        const point = options.point || deps.viewportCenter();
        if(!node) node = deps.createEmptyNodeAt(point);
        if(!node) return null;
        // Imported media uses its own aspect; generation frame sizes are only for runs.
        delete node.cardSize;
        delete node.cardSizing;
        node.images = [images[0]];
        node.title = uploadTitleForItems(node.images, node.title || 'Image');
        delete node.w;
        delete node.h;
        let last = node;
        for(const image of images.slice(1)){
            const rect = deps.nodeRect ? deps.nodeRect(last) : null;
            const w = rect && rect.width > 0 ? Math.round(rect.width) : 240;
            const h = rect && rect.height > 0 ? Math.round(rect.height) : 200;
            const sx = Math.round((rect ? rect.x + rect.width : Number(point?.x) || 0) + 24);
            const sy = Math.round(rect ? rect.y : Number(point?.y) || 0);
            const spot = deps.findFreeSpot ? deps.findFreeSpot(sx, sy, w, h) : {x:sx, y:sy};
            const created = deps.createNodeWithImage ? deps.createNodeWithImage({x: spot.x + Math.round(w / 2), y: spot.y + Math.round(h / 2)}, image) : null;
            if(!created) continue;
            delete created.cardSize;
            delete created.cardSizing;
            created.images = [image];
            created.title = uploadTitleForItems([image], 'Image');
            delete created.w;
            delete created.h;
            last = created;
        }
        deps.setSelectedId(node.id);
        deps.render();
        deps.scheduleSave();
        return node;
    }

    global.CanvasImageNodeMediaController = {configure, uploadTitleForItems, appendImages};
})(typeof window !== 'undefined' ? window : globalThis);

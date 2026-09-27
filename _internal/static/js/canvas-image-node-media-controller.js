/* Applies imported media to image nodes and maintains their single/group shape. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    function uploadTitleForItems(items, fallback='Upload'){
        const list = [...(items || [])];
        if(!list.length) return fallback;
        const kinds = new Set(list.map(item => deps.isFile(item) ? deps.mediaKindForFile(item) : deps.mediaKindForItem(item)));
        if(kinds.size > 1) return list.length > 1 ? 'Media' : fallback;
        if(kinds.has('video')) return list.length > 1 ? 'Videos' : 'Video';
        if(kinds.has('audio')) return 'Audio';
        return list.length > 1 ? 'Group' : 'Image';
    }

    function appendImages(uploaded, targetId='', options={}){
        const images = [...(uploaded || [])].filter(file => file?.url);
        if(!images.length) return null;
        let node = deps.getNodes().find(item => item.id === targetId) || deps.selectedNode();
        if(node && !deps.isImageNode(node)) node = null;
        if(options.forceNew) node = null;
        if(!node){
            const center = options.point || deps.viewportCenter();
            node = deps.createEmptyNodeAt(center);
        }
        if(!node) return null;
        const previousCount = (node.images || []).length;
        node.images = [...(node.images || []), ...images.map(file => ({...file, kind:file.kind || deps.mediaKindForItem(file)}))];
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

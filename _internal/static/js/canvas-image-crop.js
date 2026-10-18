/* Canvas image free-crop interaction and upload lifecycle. */
(function (global) {
    'use strict';

    var deps = {
        getNodes: function () { return []; },
        getWorld: function () { return null; },
        getViewport: function () { return { scale: 1 }; },
        mediaKindForItem: function () { return 'image'; },
        setSelection: function () {},
        syncSelectionUi: function () {},
        fileNameFromUrl: function () { return ''; },
        uploadCroppedBlob: async function () { throw new Error('裁剪上传未配置'); },
        imageLayout: function () { return { width: 260 }; },
        nodeScale: function () { return 1; },
        createNode: function () {},
        toast: function () {}
    };
    var state = null;

    function configure(patch) { Object.assign(deps, patch || {}); }
    function isActive() { return Boolean(state); }

    function stop() {
        if (state && state.moveHandler) global.removeEventListener('mousemove', state.moveHandler, true);
        if (state && state.upHandler) global.removeEventListener('mouseup', state.upHandler, true);
        if (state && state.boxEl) state.boxEl.remove();
        if (state && state.itemEl) state.itemEl.classList.remove('free-crop-target');
        state = null;
        global.document.body.classList.remove('smart-free-cropping');
    }

    function contentRect(img) {
        var rect = img.getBoundingClientRect();
        var viewport = deps.getViewport ? deps.getViewport() : null;
        var scale = Math.max(0.001, Number(viewport && viewport.scale) || 1);
        var cssW = Math.max(1, rect.width / scale);
        var cssH = Math.max(1, rect.height / scale);
        var naturalW = img.naturalWidth || cssW;
        var naturalH = img.naturalHeight || cssH;
        var fit = Math.min(cssW / naturalW, cssH / naturalH);
        var width = Math.max(1, naturalW * fit);
        var height = Math.max(1, naturalH * fit);
        return {
            left: rect.left + (rect.width - width * scale) / 2,
            top: rect.top + (rect.height - height * scale) / 2,
            width: width,
            height: height,
            scale: scale
        };
    }

    function point(event, img) {
        var rect = contentRect(img);
        return {
            x: Math.max(0, Math.min(rect.width, (event.clientX - rect.left) / rect.scale)),
            y: Math.max(0, Math.min(rect.height, (event.clientY - rect.top) / rect.scale))
        };
    }

    function updateBox() {
        if (!state || !state.boxEl || !state.start || !state.current) return;
        var itemRect = state.itemEl.getBoundingClientRect();
        var imageRect = contentRect(state.imgEl);
        var offsetX = (imageRect.left - itemRect.left) / imageRect.scale;
        var offsetY = (imageRect.top - itemRect.top) / imageRect.scale;
        var a = state.start;
        var b = state.current;
        Object.assign(state.boxEl.style, {
            left: (offsetX + Math.min(a.x, b.x)) + 'px',
            top: (offsetY + Math.min(a.y, b.y)) + 'px',
            width: Math.abs(b.x - a.x) + 'px',
            height: Math.abs(b.y - a.y) + 'px'
        });
    }

    /* The node body re-renders (e.g. on selection change / click) and replaces the
       .image-wrap element, which detaches the crop box we appended. Re-attach the box
       to the live itemEl so the selection stays visible after a re-render.
       Coordinates live in image-content space, so re-parenting never invalidates them. */
    function relocate() {
        if (!state || !state.boxEl) return;
        var world = deps.getWorld && deps.getWorld();
        if (!world) return;
        var nodeEl = world.querySelector('.image-node[data-id="' + CSS.escape(state.nodeId) + '"]');
        var itemEl = nodeEl && nodeEl.querySelector('[data-image-index="' + state.imageIndex + '"]');
        if (!itemEl) return;
        var imgEl = itemEl.querySelector('img');
        if (!imgEl) return;
        if (state.itemEl && state.itemEl !== itemEl) {
            state.itemEl.classList.remove('free-crop-target');
        }
        if (itemEl !== state.itemEl) {
            state.itemEl = itemEl;
            state.imgEl = imgEl;
            itemEl.classList.add('free-crop-target');
        }
        if (state.boxEl.parentNode !== itemEl) {
            itemEl.appendChild(state.boxEl);
        }
        updateBox();
    }

    function begin(nodeId, imageIndex, event) {
        if (event) {
            event.preventDefault && event.preventDefault();
            event.stopPropagation && event.stopPropagation();
            event.stopImmediatePropagation && event.stopImmediatePropagation();
        }
        var nodes = deps.getNodes ? deps.getNodes() : [];
        var node = nodes.find(function (item) { return item.id === nodeId; });
        var image = node && node.images && node.images[imageIndex];
        if (!node || !image || !image.url || deps.mediaKindForItem(image) !== 'image') return;
        stop();
        deps.setSelection(nodeId, imageIndex);
        deps.syncSelectionUi();
        var world = deps.getWorld && deps.getWorld();
        var nodeEl = world && world.querySelector('.image-node[data-id="' + CSS.escape(nodeId) + '"]');
        var itemEl = nodeEl && nodeEl.querySelector('[data-image-index="' + imageIndex + '"]');
        var imgEl = itemEl && itemEl.querySelector('img');
        if (!itemEl || !imgEl) return;
        itemEl.classList.add('free-crop-target');
        var boxEl = global.document.createElement('div');
        boxEl.className = 'smart-free-crop-box';
        itemEl.appendChild(boxEl);
        state = { nodeId: nodeId, imageIndex: imageIndex, node: node, image: image, itemEl: itemEl, imgEl: imgEl, boxEl: boxEl, start: null, current: null };
        global.document.body.classList.add('smart-free-cropping');
        // Catch a re-render that may follow the selection change / opening click.
        requestAnimationFrame(relocate);
    }

    function startSelection(event, nodeId, itemEl) {
        if (!state || state.nodeId !== nodeId || state.itemEl !== itemEl || event.button !== 0) return false;
        if (event.target.closest('.smart-crop-action, .smart-node-action, .image-delete, .mini-x')) return false;
        event.preventDefault();
        event.stopPropagation();
        if (event.stopImmediatePropagation) event.stopImmediatePropagation();
        var img = state.imgEl;
        state.start = point(event, img);
        state.current = state.start;
        updateBox();
        state.moveHandler = function (moveEvent) {
            moveEvent.preventDefault();
            moveEvent.stopPropagation();
            state.current = point(moveEvent, img);
            updateBox();
        };
        state.upHandler = function (upEvent) {
            upEvent.preventDefault();
            upEvent.stopPropagation();
            global.removeEventListener('mousemove', state.moveHandler, true);
            global.removeEventListener('mouseup', state.upHandler, true);
            state.moveHandler = null;
            state.upHandler = null;
            // The release may trigger a node-body re-render that swaps the .image-wrap.
            // Re-attach the box to the fresh itemEl so the selection stays on screen.
            requestAnimationFrame(function () { relocate(); });
            setTimeout(relocate, 80);
        };
        global.addEventListener('mousemove', state.moveHandler, true);
        global.addEventListener('mouseup', state.upHandler, true);
        return true;
    }

    function loadSource(url) {
        return new Promise(function (resolve, reject) {
            var img = new global.Image();
            img.crossOrigin = 'anonymous';
            img.onload = function () { resolve(img); };
            img.onerror = function () { reject(new Error('源图片加载失败')); };
            img.src = url;
        });
    }

    async function confirm() {
        var crop = state;
        if (!crop || !crop.start || !crop.current) return;
        var width = Math.abs(crop.current.x - crop.start.x);
        var height = Math.abs(crop.current.y - crop.start.y);
        if (width < 3 || height < 3) { deps.toast('请框选更大的裁剪区域'); return; }
        try {
            var source = await loadSource(crop.image.url);
            var rect = contentRect(crop.imgEl);
            var scaleX = source.naturalWidth / Math.max(1, rect.width);
            var scaleY = source.naturalHeight / Math.max(1, rect.height);
            var sx = Math.max(0, Math.round(Math.min(crop.start.x, crop.current.x) * scaleX));
            var sy = Math.max(0, Math.round(Math.min(crop.start.y, crop.current.y) * scaleY));
            var sw = Math.max(1, Math.min(source.naturalWidth - sx, Math.round(width * scaleX)));
            var sh = Math.max(1, Math.min(source.naturalHeight - sy, Math.round(height * scaleY)));
            var canvas = global.document.createElement('canvas');
            canvas.width = sw;
            canvas.height = sh;
            canvas.getContext('2d').drawImage(source, sx, sy, sw, sh, 0, 0, sw, sh);
            var blob = await new Promise(function (resolve) { canvas.toBlob(resolve, 'image/png'); });
            if (!blob) throw new Error('裁剪图片生成失败');
            var rawName = crop.image.name || deps.fileNameFromUrl(crop.image.url || '') || 'image';
            var base = String(rawName).replace(/\.[a-z0-9]{2,8}$/i, '') || 'image';
            var file = await deps.uploadCroppedBlob(blob, base + '-crop.png');
            if (!file || !file.url) throw new Error('未返回裁剪图片地址');
            var cropped = Object.assign({}, file, { kind: 'image', natural_w: sw, natural_h: sh });
            var layout = deps.imageLayout(crop.node.images || [], deps.nodeScale(crop.node), crop.node);
            stop();
            deps.createNode(Number(crop.node.x || 0) + Number(layout.width || 260) + 36, Number(crop.node.y || 0), [cropped]);
        } catch (error) {
            deps.toast(error && error.message || '裁剪失败');
        }
    }

    global.CanvasImageCrop = {
        configure: configure,
        isActive: isActive,
        begin: begin,
        stop: stop,
        startSelection: startSelection,
        confirm: confirm
    };
})(typeof window !== 'undefined' ? window : globalThis);

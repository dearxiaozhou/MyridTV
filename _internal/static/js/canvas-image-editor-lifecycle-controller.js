/* Owns image editor open/close lifecycle, asynchronous media loading, and navigation. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}
    function element(id){return global.document.getElementById(id);}

    function updateNavigation(){
        const navigation = deps.getPreviewNavigation();
        const node = deps.getNodes().find(item => item.id === navigation.nodeId);
        const count = Math.max(0, (node?.images || []).filter(image => image?.url).length);
        deps.setPreviewNavigation({...navigation, count});
        const show = deps.isModalOpen() && count > 1;
        element('previewPrevBtn')?.classList.toggle('visible', show);
        element('previewNextBtn')?.classList.toggle('visible', show);
    }

    function navigate(delta){
        if(!deps.isModalOpen()) return;
        const navigation = deps.getPreviewNavigation();
        const node = deps.getNodes().find(item => item.id === navigation.nodeId);
        const images = (node?.images || []).filter(image => image?.url);
        if(!node || images.length <= 1) return;
        const count = images.length;
        const next = (Number(navigation.index || 0) + Number(delta || 0) + count) % count;
        open(node.id, next);
    }

    function open(nodeId, imageIndex=0){
        const node = deps.getNodes().find(item => item.id === nodeId);
        const image = deps.imageForDisplay(node?.images?.[imageIndex]);
        if(!image?.url) return false;
        const kind = deps.mediaKindForItem(image);
        if(kind !== 'image' && kind !== 'video'){
            deps.downloadPreviewFile(image);
            return false;
        }

        const loadToken = deps.nextLoadToken();
        deps.setSelectedId(nodeId);
        deps.setSelectedImage({nodeId, index:imageIndex});
        deps.setPreviewNavigation({nodeId, index:imageIndex, count:(node.images || []).filter(item => item?.url).length});
        deps.setCropState({nodeId, imageIndex, x:0, y:0, w:0, h:0});
        deps.resetGridState();
        deps.resetImageViewState();
        deps.resetTextEditState();
        const toggle = element('gridCustomToggle');
        if(toggle){ toggle.classList.add('secondary'); toggle.classList.remove('primary'); }
        deps.syncGridCustomControls();
        ['gridHorizontalLines','gridVerticalLines'].forEach(id => { const control = element(id); if(control) control.disabled = false; });
        const orientH = element('gridOrientH'), orientV = element('gridOrientV');
        if(orientH){ orientH.classList.add('primary'); orientH.classList.remove('secondary'); }
        if(orientV){ orientV.classList.add('secondary'); orientV.classList.remove('primary'); }
        deps.syncGridCustomUndoButton();
        deps.updateZoomLabel();
        const imageElement = element('cropImage');
        imageElement.style.width = ''; imageElement.style.height = ''; imageElement.style.maxWidth = ''; imageElement.style.maxHeight = '';
        deps.lockRootScroll();
        deps.getModal().classList.add('open');
        deps.lockRootScroll();
        deps.resetCompareState();
        deps.disposePanoramaPreview();
        deps.resetPreviewTransform();

        const currentPreview = element('previewCurrentImage');
        const currentVideo = element('previewCurrentVideo');
        const comparePreview = element('previewCompareImage');
        [currentPreview, comparePreview].forEach(media => {
            if(!media) return;
            media.onload = null;
            media.onerror = null;
            media.removeAttribute('src');
            media.style.display = 'none';
        });
        if(currentVideo){
            currentVideo.pause?.();
            currentVideo.onloadedmetadata = null;
            currentVideo.onloadeddata = null;
            currentVideo.removeAttribute('src');
            currentVideo.load?.();
            currentVideo.style.display = 'none';
        }
        const previewFrame = element('previewFrame');
        if(previewFrame){ previewFrame.style.width = ''; previewFrame.style.height = ''; }
        deps.updatePreviewMetaHint('');
        if(kind === 'video'){
            imageElement.onload = null;
            imageElement.onerror = null;
            imageElement.removeAttribute('src');
            delete imageElement.dataset.proxyFallbackTried;
            deps.setImageEditMode('preview');
            updateNavigation();
            deps.refreshIcons();
            return true;
        }

        imageElement.onload = () => {
            if(loadToken !== deps.getLoadToken()) return;
            const targetImage = node.images?.[imageIndex];
            if(targetImage && imageElement.naturalWidth && imageElement.naturalHeight && (!targetImage.natural_w || !targetImage.natural_h)){
                targetImage.natural_w = imageElement.naturalWidth;
                targetImage.natural_h = imageElement.naturalHeight;
                deps.scheduleSave();
            }
            deps.setImageBaseSize(imageElement.clientWidth, imageElement.clientHeight);
            deps.updateZoomLabel();
            deps.resizeEditDrawCanvas();
            deps.resetEditDrawingHistory();
            deps.clearEditDrawing(true);
            deps.resetCropBox();
            if(!deps.isImageEditModeTouched()) deps.setImageEditMode('preview');
            else deps.refreshComparePanel();
            if(!deps.isPanoramaEnabled()) deps.updatePreviewMetaHint();
            deps.syncImageEditOverflow();
            deps.refreshIcons();
        };
        imageElement.onerror = () => {
            if(loadToken !== deps.getLoadToken()) return;
            if(imageElement.dataset.proxyFallbackTried === '1') return;
            const fallback = deps.proxiedMediaUrl(image);
            if(!fallback || fallback === imageElement.getAttribute('src')) return;
            imageElement.dataset.proxyFallbackTried = '1';
            imageElement.src = fallback;
        };
        imageElement.dataset.proxyFallbackTried = '';
        imageElement.crossOrigin = 'anonymous';
        imageElement.src = deps.displayMediaUrl(image);
        deps.setImageEditMode('preview');
        updateNavigation();
        deps.refreshIcons();
        return true;
    }

    function close(){
        deps.nextLoadToken();
        deps.getModal().classList.remove('open');
        global.document.querySelector('.image-edit-panel')?.classList.remove('video-preview-mode');
        const imageElement = element('cropImage');
        const previewVideo = element('previewCurrentVideo');
        imageElement.onload = null;
        imageElement.onerror = null;
        imageElement.removeAttribute('src');
        delete imageElement.dataset.proxyFallbackTried;
        imageElement.style.width = ''; imageElement.style.height = ''; imageElement.style.maxWidth = ''; imageElement.style.maxHeight = '';
        imageElement.style.position = ''; imageElement.style.left = ''; imageElement.style.top = '';
        if(previewVideo){
            previewVideo.pause?.();
            previewVideo.onloadedmetadata = null;
            previewVideo.onloadeddata = null;
            previewVideo.removeAttribute('src');
            previewVideo.load?.();
            previewVideo.style.display = 'none';
        }
        deps.clearEditDrawing(true);
        deps.setCropState(null);
        deps.setCropDrag(null);
        deps.setEditDrawState(null);
        deps.resetEditDrawingHistory();
        deps.setGridCustomDrag(null);
        deps.setPreviewNavigation({nodeId:'', index:0, count:0});
        deps.resetImageViewState();
        deps.disposePanoramaPreview();
        deps.resetPreviewInteractionState();
        deps.resetPreviewTransform();
        element('imageEditStage')?.classList.remove('overflow-x', 'overflow-y', 'preview-mode');
        const cropCanvas = element('cropCanvas');
        cropCanvas?.classList.remove('grid-custom-h', 'grid-custom-v', 'outpaint-mode', 'outpaint-warning', 'dragging-image', 'text-mode');
        if(cropCanvas){ cropCanvas.style.width = ''; cropCanvas.style.height = ''; }
        const textCanvas = element('editTextCanvas');
        if(textCanvas){ textCanvas.style.left = ''; textCanvas.style.top = ''; }
        updateNavigation();
    }

    global.CanvasImageEditorLifecycleController = {configure, open, close, updateNavigation, navigate};
})(typeof window !== 'undefined' ? window : globalThis);

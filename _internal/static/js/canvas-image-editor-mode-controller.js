/* Keeps image editor modes, mode buttons, toolbar visibility, and mode labels in sync. */
(function(global){
    'use strict';

    const deps = {};
    const MODES = ['preview', 'crop', 'outpaint', 'mask', 'brush', 'grid'];
    function configure(options){Object.assign(deps, options || {});}

    function element(id){return global.document.getElementById(id);}

    function setMode(requestedMode, userTouched=false){
        const editKind = deps.getEditKind();
        const isVideoPreview = editKind === 'video';
        let mode = requestedMode;
        if(isVideoPreview && mode !== 'preview') mode = 'preview';
        if(userTouched) deps.markModeTouched();
        const previousMode = deps.getMode();
        if(mode !== 'brush') deps.removeEditTextInlineEditor(true);
        mode = MODES.includes(mode) ? mode : 'preview';
        deps.setMode(mode);

        const cropCanvas = element('cropCanvas');
        const previewStage = element('previewStage');
        const editStage = element('imageEditStage');
        const editPanel = global.document.querySelector('.image-edit-panel');
        const isPreview = mode === 'preview';
        if(isPreview) deps.bindPreviewWheelListeners();
        if(!isPreview && deps.isPanoramaEnabled()) deps.disposePanoramaPreview();
        cropCanvas.style.display = isPreview ? 'none' : '';
        previewStage.style.display = isPreview ? 'inline-flex' : 'none';
        editStage?.classList.toggle('preview-mode', isPreview);
        editPanel?.classList.toggle('video-preview-mode', isVideoPreview);
        const previewDownload = element('previewDownloadBtn');
        const previewDownloadAll = element('previewDownloadAllBtn');
        if(previewDownload) previewDownload.style.display = isPreview ? 'inline-flex' : 'none';
        if(previewDownloadAll) previewDownloadAll.style.display = isPreview && !isVideoPreview && deps.previewDownloadGroupCount() > 1 ? 'inline-flex' : 'none';
        const modeBar = global.document.querySelector('.image-edit-mode');
        if(modeBar) modeBar.style.display = isVideoPreview ? 'none' : '';
        const videoTools = element('videoFrameTools');
        if(videoTools) videoTools.style.display = isVideoPreview && isPreview ? 'flex' : 'none';
        const zoomLabel = element('imageEditZoomLabel');
        if(zoomLabel) zoomLabel.style.display = isVideoPreview ? 'none' : '';
        const cancel = element('imageEditCancelBtn');
        if(cancel){
            cancel.style.display = '';
            cancel.textContent = isVideoPreview ? '关闭' : deps.translate('common.cancel');
        }
        cropCanvas.classList.toggle('mask-mode', mode === 'mask');
        cropCanvas.classList.toggle('brush-mode', mode === 'brush');
        cropCanvas.classList.toggle('grid-mode', mode === 'grid');
        cropCanvas.classList.toggle('outpaint-mode', mode === 'outpaint');
        deps.syncGridCustomCursor();
        global.document.querySelectorAll('[data-image-edit-mode]').forEach(button => button.classList.toggle('active', button.dataset.imageEditMode === mode));
        element('imagePreviewTools').classList.toggle('active', isPreview && !isVideoPreview);
        element('imageMaskTools').classList.toggle('active', mode === 'mask');
        element('imageBrushTools').classList.toggle('active', mode === 'brush');
        element('imageGridTools').classList.toggle('active', mode === 'grid');
        deps.syncGridGapValue();
        const apply = element('imageEditApplyBtn');
        element('compareToggleBtn').style.display = isPreview && !isVideoPreview ? 'inline-flex' : 'none';
        element('panoramaToggleBtn').style.display = isPreview && !isVideoPreview ? 'inline-flex' : 'none';
        element('panoramaExportBtn').style.display = isPreview && !isVideoPreview && deps.isPanoramaEnabled() ? 'inline-flex' : 'none';
        element('compareThumbs').style.display = 'none';
        if(isPreview){
            element('imageEditTitle').textContent = isVideoPreview ? '预览视频' : deps.translate('smart.previewImage');
            element('imageEditSub').textContent = isVideoPreview ? '' : deps.translate('smart.previewHint');
            apply.style.display = 'none';
            deps.refreshComparePanel();
        } else {
            deps.ensureImageEditBaseSize(true);
            deps.applyImageEditZoom();
            apply.style.display = '';
            const icon = mode === 'crop' ? 'crop' : mode === 'outpaint' ? 'expand' : mode === 'mask' ? 'brush' : mode === 'brush' ? 'paintbrush' : 'grid-3x3';
            const labelKey = mode === 'crop' ? 'canvas.applyCrop' : mode === 'outpaint' ? 'canvas.applyOutpaint' : mode === 'mask' ? 'canvas.applyMask' : mode === 'brush' ? 'canvas.applyBrush' : 'canvas.applyGrid';
            const titleKey = mode === 'crop' ? 'canvas.cropImage' : mode === 'outpaint' ? 'canvas.outpaintImage' : mode === 'mask' ? 'canvas.maskEdit' : mode === 'brush' ? 'canvas.brushEdit' : 'canvas.modeGrid';
            const subKey = mode === 'crop' ? 'canvas.cropHint' : mode === 'outpaint' ? 'canvas.outpaintHint' : mode === 'mask' ? 'canvas.maskHint2' : mode === 'brush' ? 'canvas.brushHint' : 'canvas.gridHint';
            element('imageEditTitle').textContent = deps.translate(titleKey);
            element('imageEditSub').textContent = deps.translate(subKey);
            apply.innerHTML = `<i data-lucide="${icon}" class="w-4 h-4"></i><span>${deps.translate(labelKey)}</span>`;
            if(mode === 'crop'){
                global.requestAnimationFrame(() => { deps.resetCropBox(); deps.syncImageEditOverflow(); });
            } else if(mode === 'outpaint'){
                global.requestAnimationFrame(() => { deps.resetOutpaintBox(); deps.syncImageEditOverflow(); });
            }
        }
        deps.resizeEditDrawCanvas();
        if(mode === 'grid') deps.refreshGridSplitPreview();
        else if(mode === 'crop' || mode === 'outpaint' || previousMode === 'grid') deps.clearEditDrawing(true);
        deps.syncEditDrawingHistoryButtons();
        deps.syncBrushToolButtons();
        deps.syncTextToolState(true);
        deps.refreshIcons();
        return mode;
    }

    global.CanvasImageEditorModeController = {configure, setMode, modes:MODES.slice()};
})(typeof window !== 'undefined' ? window : globalThis);

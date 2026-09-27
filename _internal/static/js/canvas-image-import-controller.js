/* Owns image upload and routing imported media into nodes. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    async function uploadFiles(files){
        const supported = [...(files || [])].filter(deps.isSupportedUploadFile);
        if(!supported.length) return [];
        const form = new global.FormData();
        supported.forEach(file => form.append('files', file, file.name || 'media'));
        // 落盘位置由宿主决定（画布内上传 → 该画布输出目录；缺省 assets/input）
        const url = (typeof deps.uploadUrl === 'function' && deps.uploadUrl()) || '/api/ai/upload';
        const data = await deps.fetcher(url, {method:'POST', body:form}).then(async response => {
            if(!response.ok) throw new Error((await response.text()) || deps.uploadFailMessage());
            return response.json();
        });
        return (data.files || []).map((file, index) => ({
            ...file,
            kind:file.kind || deps.mediaKindForFile(supported[index])
        }));
    }

    async function handleFiles(files, targetId='', options={}){
        try {
            const fileList = [...(files || [])].filter(deps.isSupportedUploadFile);
            if(!fileList.length) return;
            const uploaded = await uploadFiles(fileList);
            if(!uploaded.length) return;
            if(!options.skipUndo) deps.pushUndo();
            deps.appendImagesToNode(uploaded.map((file, index) => ({
                ...file,
                kind:file.kind || deps.mediaKindForFile(fileList[index])
            })), targetId, options);
        } catch(error) {
            deps.toast(error.message || deps.uploadFailMessage());
        }
    }

    async function handleDropPayload(payload, targetId='', options={}){
        try {
            if(payload.type === 'files') await handleFiles(payload.files, targetId, options);
            else if(payload.type === 'asset'){
                if(!options.skipUndo) deps.pushUndo();
                const image = {url:payload.url, name:payload.name || deps.imageNameFromUrl(payload.url), kind:payload.kind || 'image'};
                if(payload.assetId){ image.assetId = payload.assetId; image.assetVersionMode = 'latest'; }
                deps.appendImagesToNode([image], targetId, options);
            } else if(payload.type === 'url'){
                if(!options.skipUndo) deps.pushUndo();
                deps.appendImagesToNode([{url:payload.url, name:deps.imageNameFromUrl(payload.url), kind:'image'}], targetId, options);
            }
        } catch(error) {
            deps.toast(error.message || deps.uploadFailMessage());
        }
    }

    global.CanvasImageImportController = {configure, uploadFiles, handleFiles, handleDropPayload};
})(typeof window !== 'undefined' ? window : globalThis);

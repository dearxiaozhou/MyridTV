/* Normalizes generated media and task ids for canvas generation flows. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    function resultMediaUrls(result){
        const urls = [];
        const add = value => {
            if(!value) return;
            if(typeof value === 'string'){
                urls.push(value);
                return;
            }
            if(Array.isArray(value)){
                value.forEach(add);
                return;
            }
            if(typeof value === 'object'){
                if(value.url || value.path || value.src || value.uri){
                    const url = value.url || value.path || value.src || value.uri;
                    if(url) urls.push({url, kind:value.kind || value.type || value.mediaKind || '', name:value.name || value.filename || ''});
                }
                ['outputs','videos','images','urls','data','result'].forEach(key => add(value[key]));
                ['url','path','src','uri','output','output_url','outputUrl','video','video_url','videoUrl','mp4_url','mp4Url','download_url','downloadUrl','preview_url','previewUrl'].forEach(key => add(value[key]));
            }
        };
        ['items','outputs','videos','audios','texts','files','images','urls','data','result','output','url'].forEach(key => add(result?.[key]));
        const seen = new Set();
        return urls.map(item => {
            const url = typeof item === 'string' ? item : item?.url || item?.path || '';
            if(!url) return null;
            return typeof item === 'object' ? {...item, url} : url;
        }).filter(item => {
            const url = typeof item === 'string' ? item : item?.url || '';
            return url && !seen.has(url) && seen.add(url);
        });
    }

    function taskIdsFromResult(result){
        const ids = [];
        const add = value => {
            if(!value) return;
            if(Array.isArray(value)){
                value.forEach(add);
                return;
            }
            const text = String(value || '').trim();
            if(text && !ids.includes(text)) ids.push(text);
        };
        add(result?.taskIds);
        add(result?.task_ids);
        add(result?.task_id);
        add(result?.taskId);
        return ids;
    }

    function mediaKindForUrls(urls, fallback='image'){
        const items = (urls || []).map(item => typeof item === 'string' ? {url:item} : (item || {}));
        if(fallback && fallback !== 'image') return fallback;
        if(items.some(deps.isVideoMediaItem)) return 'video';
        if(items.some(deps.isAudioMediaItem)) return 'audio';
        if(items.some(deps.isTextMediaItem)) return 'text';
        return fallback;
    }

    global.CanvasGenerationResultModel = {configure, resultMediaUrls, taskIdsFromResult, mediaKindForUrls};
})(typeof window !== 'undefined' ? window : globalThis);

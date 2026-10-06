/* Normalizes generated media and task ids for canvas generation flows. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    function mediaIdentityKeys(item){
        const values = typeof item === 'string' ? [item] : [item?.url, item?.path, item?.src, item?.uri, item?.source_url, item?.sourceUrl];
        const keys = [];
        for(const value of values){
            if(typeof value !== 'string' || !value.trim()) continue;
            const raw = value.trim();
            let key = raw;
            try {
                const url = new URL(raw, global.location?.origin || 'http://localhost');
                const local = raw.startsWith('/') || url.origin === global.location?.origin;
                if(local && url.pathname.startsWith('/assets/')){
                    const path = decodeURIComponent(url.pathname);
                    key = path;
                    // Normal and recovery results used to archive the same Comfy file
                    // in different folders. The prompt UUID identifies that output.
                    const filename = path.split('/').pop();
                    if(path.startsWith('/assets/output/') && /^comfy_[0-9a-f]{8}-[0-9a-f-]{27}_/i.test(filename)) key = 'comfy-output:' + filename;
                }
            } catch(_) {}
            keys.push(key);
        }
        return keys;
    }

    function uniqueMediaItems(items){
        const seen = new Set();
        return (items || []).filter(item => {
            const keys = mediaIdentityKeys(item);
            if(!keys.length) return false;
            const duplicate = keys.some(key => seen.has(key));
            keys.forEach(key => seen.add(key));
            return !duplicate;
        });
    }

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
        return uniqueMediaItems(urls.map(item => {
            const url = typeof item === 'string' ? item : item?.url || item?.path || '';
            if(!url) return null;
            return typeof item === 'object' ? {...item, url} : url;
        }).filter(Boolean));
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

    global.CanvasGenerationResultModel = {configure, mediaIdentityKeys, uniqueMediaItems, resultMediaUrls, taskIdsFromResult, mediaKindForUrls};
})(typeof window !== 'undefined' ? window : globalThis);

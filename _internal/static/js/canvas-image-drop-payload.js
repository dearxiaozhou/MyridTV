/* Normalizes files, asset references, and URLs from browser drops. */
(function(global){
    'use strict';

    const deps = {};
    const TEXT_TYPES = [
        'text/uri-list',
        'text/plain',
        'text/html',
        'DownloadURL',
        'text/x-moz-url',
        'text/x-file-url',
        'public.file-url',
        'public.url',
        'UniformResourceLocator',
        'FileName',
        'FileNameW'
    ];
    const TYPE_HINT_RE = /^(?:files?|image\/.+|text\/(?:uri-list|html|plain|x-moz-url|x-file-url)|downloadurl|public\.(?:file-url|url)|uniformresourcelocator|filenamew?)$|application\/x-smart-asset|application\/x-qt-(?:windows-mime|image)|application\/x-moz-file|com\.eagle/i;

    function configure(options){Object.assign(deps, options || {});}

    function dataTypes(dataTransfer){
        return [...(dataTransfer?.types || [])].map(type => String(type || ''));
    }

    function readData(dataTransfer, type){
        try { return dataTransfer?.getData?.(type) || ''; } catch(_) { return ''; }
    }

    function unique(values){
        const seen = new Set();
        return values.filter(value => {
            const key = String(value || '').trim();
            if(!key || seen.has(key)) return false;
            seen.add(key);
            return true;
        });
    }

    function textFragments(value){
        const text = String(value || '').trim();
        if(!text) return [];
        const fragments = [];
        if(/<img|<a\s/i.test(text)){
            const doc = new global.DOMParser().parseFromString(text, 'text/html');
            doc.querySelectorAll('img[src],a[href]').forEach(el => fragments.push(el.getAttribute('src') || el.getAttribute('href') || ''));
        }
        text.split(/\r?\n/).forEach(line => {
            const item = line.trim();
            if(item) fragments.push(item);
        });
        const downloadUrl = text.match(/^image\/[^\s:]+:(.+)$/i);
        if(downloadUrl) fragments.push(downloadUrl[1]);
        return fragments;
    }

    function decodeText(value){
        const text = String(value || '').trim();
        if(!text) return '';
        try { return decodeURIComponent(text); } catch(_) { return text; }
    }

    function textCandidates(dataTransfer){
        if(!dataTransfer) return [];
        const types = unique([...TEXT_TYPES, ...dataTypes(dataTransfer)]);
        const values = types.map(type => readData(dataTransfer, type)).filter(Boolean);
        return unique(values.flatMap(textFragments).map(decodeText)).filter(value => value && !value.startsWith('#'));
    }

    function isRemoteValue(value){
        const text = String(value || '').trim();
        return /^https?:\/\/.+/i.test(text) || /^data:image\//i.test(text) || /^blob:/i.test(text);
    }

    function imageFiles(dataTransfer){
        return [...(dataTransfer?.files || [])].filter(deps.isSupportedUploadFile || (() => false));
    }

    function imageNameFromUrl(url){
        try {
            const clean = String(url || '').split('?', 1)[0].split('#', 1)[0];
            return decodeURIComponent(clean.split('/').pop() || 'image');
        } catch(_) {
            return 'image';
        }
    }

    function payloadFromDataTransfer(dataTransfer){
        try {
            const rawAsset = readData(dataTransfer, 'application/x-smart-asset');
            if(rawAsset){
                const asset = JSON.parse(rawAsset);
                if(asset?.url) return {type:'asset', url:asset.url, name:asset.name || '', kind:asset.kind || 'image', assetId:asset.assetId || ''};
            }
        } catch(_) {}
        const files = imageFiles(dataTransfer);
        if(files.length) return {type:'files', files};
        const url = textCandidates(dataTransfer).find(isRemoteValue) || '';
        if(url) return {type:'url', url};
        return {type:'none'};
    }

    function itemEntry(item){
        try { return item?.webkitGetAsEntry?.() || null; } catch(_) { return null; }
    }

    async function filesFromEntry(entry){
        if(!entry) return [];
        if(entry.isFile){
            return new Promise(resolve => entry.file(file => resolve(file ? [file] : []), () => resolve([])));
        }
        if(!entry.isDirectory) return [];
        const reader = entry.createReader();
        const children = [];
        while(true){
            const batch = await new Promise(resolve => reader.readEntries(resolve, () => resolve([])));
            if(!batch.length) break;
            children.push(...batch);
        }
        return (await Promise.all(children.map(filesFromEntry))).flat();
    }

    async function filesFromDataTransfer(dataTransfer){
        const items = [...(dataTransfer?.items || [])];
        const entries = items.map(itemEntry).filter(Boolean);
        const raw = entries.length
            ? (await Promise.all(entries.map(filesFromEntry))).flat()
            : [...(dataTransfer?.files || [])];
        return raw.filter(deps.isSupportedUploadFile || (() => false));
    }

    async function resolve(dataTransfer){
        const payload = payloadFromDataTransfer(dataTransfer);
        if(payload.type !== 'none') return payload;
        const files = await filesFromDataTransfer(dataTransfer);
        return files.length ? {type:'files', files} : payload;
    }

    function hasImageData(dataTransfer){
        if(!dataTransfer) return false;
        if(imageFiles(dataTransfer).length) return true;
        if(dataTypes(dataTransfer).some(type => TYPE_HINT_RE.test(type.toLowerCase()))) return true;
        return payloadFromDataTransfer(dataTransfer).type !== 'none';
    }

    function hasAsset(dataTransfer){return dataTypes(dataTransfer).includes('application/x-smart-asset');}
    function hasInputThumb(dataTransfer){return dataTypes(dataTransfer).includes('application/x-smart-input-thumb');}

    global.CanvasImageDropPayload = {
        configure,
        dataTypes,
        filesFromDataTransfer,
        payloadFromDataTransfer,
        resolve,
        hasImageData,
        hasAsset,
        hasInputThumb,
        imageNameFromUrl
    };
})(typeof window !== 'undefined' ? window : globalThis);

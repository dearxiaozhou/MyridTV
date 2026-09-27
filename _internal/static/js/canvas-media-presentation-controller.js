/* Owns canvas-media URL presentation, download names, and image-load feedback. */
(function(global){
    'use strict';

    function create(options){
        const deps = {
            mediaKindForItem:item => item?.kind || 'image'
        };
        Object.assign(deps, options || {});

        function fileNameFromUrl(url=''){
            try{
                const parsed = new URL(String(url || ''), global.location.href);
                return decodeURIComponent(parsed.pathname.split('/').filter(Boolean).pop() || '');
            }catch(e){
                return decodeURIComponent(String(url || '').split('?')[0].split('#')[0].split('/').filter(Boolean).pop() || '');
            }
        }
        function proxiedMediaUrl(itemOrUrl, name=''){
            const url = typeof itemOrUrl === 'string' ? itemOrUrl : (itemOrUrl?.url || '');
            if(!url || String(url).startsWith('/assets/') || String(url).startsWith('/output/') || String(url).startsWith('data:') || String(url).startsWith('blob:')) return url;
            const filename = name || (typeof itemOrUrl === 'object' ? (itemOrUrl.name || '') : '') || fileNameFromUrl(url) || 'preview';
            return `/api/download-output?inline=1&url=${encodeURIComponent(url)}&name=${encodeURIComponent(filename)}`;
        }
        function prefersDirectRemoteMedia(itemOrUrl){
            return Boolean(itemOrUrl && typeof itemOrUrl === 'object' && (
                itemOrUrl.remoteFallback || itemOrUrl.remote_fallback || itemOrUrl.directRemote || itemOrUrl.skipProxy
            ));
        }
        function displayMediaUrl(itemOrUrl, name=''){
            const url = typeof itemOrUrl === 'string' ? itemOrUrl : (itemOrUrl?.url || '');
            if(/^https?:\/\//i.test(String(url || ''))){
                if(prefersDirectRemoteMedia(itemOrUrl)) return url;
                return proxiedMediaUrl(itemOrUrl, name);
            }
            return url;
        }
        function thumbnailUrl(itemOrUrl, maxEdge=640){
            const rawUrl = typeof itemOrUrl === 'string' ? itemOrUrl : (itemOrUrl?.url || '');
            if(!String(rawUrl || '').startsWith('/assets/')) return displayMediaUrl(itemOrUrl);
            const edge = Math.max(160, Math.min(2048, Math.round(Number(maxEdge) || 640)));
            return `/api/canvas-thumbnail?url=${encodeURIComponent(rawUrl)}&size=${edge}`;
        }
        function safeExportFileName(name, fallback='download.zip'){
            const cleaned = String(name || fallback).replace(/[\\/:*?"<>|]+/g, '_').trim();
            return cleaned || fallback;
        }
        function extensionForMediaItem(item, fallback='.png'){
            const source = [item?.name, item?.url].map(value => String(value || '').split('?')[0].split('#')[0]).find(value => /\.[a-z0-9]{2,8}$/i.test(value));
            if(source) return source.match(/(\.[a-z0-9]{2,8})$/i)?.[1] || fallback;
            const kind = deps.mediaKindForItem(item);
            if(kind === 'video') return '.mp4';
            if(kind === 'audio') return '.mp3';
            if(kind === 'text') return '.txt';
            return fallback;
        }
        function downloadNameForMediaItem(item, fallbackPrefix='canvas-output'){
            const localName = fileNameFromUrl(item?.url || '');
            const preferred = localName || item?.name || '';
            const ext = extensionForMediaItem(item);
            const randomName = `${fallbackPrefix}_${Date.now()}_${Math.random().toString(16).slice(2, 8)}${ext}`;
            let name = safeExportFileName(preferred || randomName, randomName);
            if(!/\.[a-z0-9]{2,8}$/i.test(name)) name += ext;
            return name;
        }
        function markImageLoadFailure(imgEl, itemOrUrl){
            if(!imgEl || imgEl.dataset.canvasImageLoadFailed === '1') return;
            imgEl.dataset.canvasImageLoadFailed = '1';
            imgEl.setAttribute('aria-hidden', 'true');
            imgEl.style.visibility = 'hidden';
            const rawUrl = typeof itemOrUrl === 'string' ? itemOrUrl : (itemOrUrl?.url || '');
            const name = (typeof itemOrUrl === 'object' ? itemOrUrl?.name : '') || fileNameFromUrl(rawUrl);
            const accessibleLabel = name ? `图片加载失败：${name}` : '图片加载失败';
            const host = imgEl.closest('.image-wrap,.thumb-item');
            if(!host){
                imgEl.setAttribute('aria-label', accessibleLabel);
                return;
            }
            host.classList.add('media-load-failed');
            if(host.querySelector(':scope > .media-load-error')) return;
            const status = global.document.createElement('div');
            status.className = 'media-load-error';
            status.setAttribute('role', 'img');
            status.setAttribute('aria-label', accessibleLabel);
            const icon = global.document.createElement('span');
            icon.className = 'media-load-error-icon';
            icon.setAttribute('aria-hidden', 'true');
            icon.textContent = '!';
            const title = global.document.createElement('strong');
            title.className = 'media-load-error-title';
            title.textContent = '图片无法加载';
            const detail = global.document.createElement('span');
            detail.className = 'media-load-error-detail';
            detail.textContent = '请检查网络或素材文件是否存在';
            status.append(icon, title, detail);
            host.appendChild(status);
        }
        function bindImageFallback(imgEl, itemOrUrl){
            if(!imgEl || imgEl.dataset.proxyFallbackBound === '1') return;
            imgEl.dataset.proxyFallbackBound = '1';
            imgEl.addEventListener('error', () => {
                if(imgEl.dataset.proxyFallbackTried === '1'){
                    markImageLoadFailure(imgEl, itemOrUrl);
                    return;
                }
                const rawUrl = typeof itemOrUrl === 'string' ? itemOrUrl : (itemOrUrl?.url || '');
                const current = imgEl.getAttribute('src') || '';
                const proxied = proxiedMediaUrl(itemOrUrl);
                const fallback = /^https?:\/\//i.test(String(rawUrl || '')) && current !== rawUrl
                    ? rawUrl
                    : (proxied && proxied !== current ? proxied : '');
                if(!fallback){
                    markImageLoadFailure(imgEl, itemOrUrl);
                    return;
                }
                imgEl.dataset.proxyFallbackTried = '1';
                imgEl.src = fallback;
            });
        }

        return {
            bindImageFallback:bindImageFallback,
            displayMediaUrl:displayMediaUrl,
            downloadNameForMediaItem:downloadNameForMediaItem,
            extensionForMediaItem:extensionForMediaItem,
            fileNameFromUrl:fileNameFromUrl,
            prefersDirectRemoteMedia:prefersDirectRemoteMedia,
            proxiedMediaUrl:proxiedMediaUrl,
            safeExportFileName:safeExportFileName,
            thumbnailUrl:thumbnailUrl
        };
    }

    global.CanvasMediaPresentationController = { create:create };
})(window);

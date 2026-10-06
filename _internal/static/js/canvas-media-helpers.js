//** Media-kind predicates, text/audio/thumb HTML helpers and node DOM sync utilities. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    function D(name){return typeof deps[name] === 'function' ? deps[name]() : deps[name];}

function updateComfyInputsRow(){
    if(!D("dynamicParams")) return;
    const el = D("dynamicParams").querySelector('.cfn-inputs-row');
    if(!el) return;
    const tpl = document.createElement('template');
    tpl.innerHTML = deps.renderComfyInputsRow().trim();
    const next = tpl.content.firstElementChild;
    if(!next) return;
    // 同 syncComfyInputsRow：连外层 .cfn-inputs-wrap 一起替换，避免层层嵌套
    const host = el.parentElement?.classList?.contains('cfn-inputs-wrap') ? el.parentElement : el;
    host.replaceWith(next);
}
function updateNodeElementDuringResize(node){
    if(!node) return;
    const el = D("world").querySelector(`.image-node[data-id="${CSS.escape(node.id)}"]`);
    if(!el){
        deps.render();
        return;
    }
    const imgs = node.images || [];
    const layout = deps.imageLayout(imgs, deps.nodeScale(node), node);
    el.style.width = `${layout.width}px`;
    el.style.height = `${layout.height}px`;
    const body = el.querySelector('.node-body');
    if(body){
        const loadingSingle = body.querySelector('.loading-cell.single');
        if(loadingSingle){
            loadingSingle.style.width = `${layout.width}px`;
            loadingSingle.style.height = `${layout.height}px`;
        }
        const loadingGrid = body.querySelector('.loading-skeleton');
        if(loadingGrid){
            const count = Math.max(1, Number(node.pending) || 1);
            const cols = Math.min(4, Math.max(2, Math.ceil(Math.sqrt(count))));
            const rows = Math.ceil(count / cols);
            loadingGrid.style.width = `${layout.width}px`;
            loadingGrid.style.height = `${layout.height}px`;
            loadingGrid.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
            loadingGrid.style.gridTemplateRows = `repeat(${rows}, 1fr)`;
        }
        const grid = body.querySelector('.thumb-grid');
        if(grid){
            grid.style.setProperty('--thumb-cols', layout.cols);
            grid.style.setProperty('--thumb-size', `${layout.thumb}px`);
        }
        const wrap = body.querySelector('.image-wrap');
        if(wrap){
            wrap.style.setProperty('--node-img-w', `${layout.width}px`);
            wrap.style.setProperty('--node-img-h', `${layout.height}px`);
        }
        const media = body.querySelector('.node-img');
        if(media){
            media.style.width = `${layout.width}px`;
            media.style.height = `${layout.height}px`;
        }
    }
    const active = deps.selectedNode();
    if(active?.id === node.id) deps.positionComposerForNode(active);
    deps.scheduleConnectionLayerRefresh();
    deps.scheduleMinimapRender();
}
function isVideoMediaItem(img){
    if(!img) return false;
    if(img.kind === 'video') return true;
    const url = String(img.url || '').toLowerCase();
    return /\.(mp4|webm|mov|m4v)(\?|$)/.test(url);
}
function isAudioMediaItem(img){
    if(!img) return false;
    if(img.kind === 'audio') return true;
    const url = String(img.url || '').toLowerCase();
    return /\.(mp3|wav|m4a|aac|ogg|flac)(\?|$)/.test(url);
}
function isTextMediaItem(img){
    if(!img) return false;
    if(img.kind === 'text') return true;
    const url = String(img.url || '').toLowerCase();
    return /\.(txt|json|csv|srt|vtt|md)(\?|$)/.test(url);
}
function isFileMediaItem(img){
    if(!img) return false;
    return img.kind === 'file';
}
function mediaKindForFile(file){
    const type = String(file?.type || '').toLowerCase();
    const name = String(file?.name || '').toLowerCase();
    if(type.startsWith('video/') || /\.(mp4|webm|mov|m4v|avi|mkv)(\?|$)/.test(name)) return 'video';
    if(type.startsWith('audio/') || /\.(mp3|wav|m4a|aac|ogg|flac)(\?|$)/.test(name)) return 'audio';
    if(type.startsWith('text/') || /\.(txt|json|csv|srt|vtt|md)(\?|$)/.test(name)) return 'text';
    return 'image';
}
function mediaKindForItem(img){
    if(isFileMediaItem(img)) return 'file';
    if(isTextMediaItem(img)) return 'text';
    if(isAudioMediaItem(img)) return 'audio';
    if(isVideoMediaItem(img)) return 'video';
    return 'image';
}
function textContentValue(item){
    return String(item?.textContent || item?.text || item?.content || '').trim();
}
function textPreviewSnippet(text, max=140){
    const clean = String(text || '').replace(/\r/g, '').replace(/\n{3,}/g, '\n\n').trim();
    if(!clean) return '';
    return clean.length > max ? `${clean.slice(0, max).trimEnd()}...` : clean;
}
async function fetchTextMediaContent(url){
    const key = String(url || '').trim();
    if(!key) return '';
    if(D("smartTextContentCache").has(key)) return D("smartTextContentCache").get(key);
    const pending = fetch(key).then(async response => {
        if(!response.ok) throw new Error(await response.text().catch(() => '读取文本失败'));
        return response.text();
    }).catch(() => '');
    D("smartTextContentCache").set(key, pending);
    return pending;
}
function ensureTextMediaContent(item, onReady=null){
    if(!item || mediaKindForItem(item) !== 'text' || !item.url) return Promise.resolve(textContentValue(item));
    const existing = textContentValue(item);
    if(existing){
        item.textPreview = item.textPreview || textPreviewSnippet(existing);
        return Promise.resolve(existing);
    }
    return fetchTextMediaContent(item.url).then(text => {
        const clean = String(text || '').trim();
        if(clean){
            item.textContent = clean;
            item.textPreview = textPreviewSnippet(clean);
            if(typeof onReady === 'function') onReady(clean);
        }
        return clean;
    });
}
function ensureNodeTextMedia(node, rerender=false){
    const items = (node?.images || []).filter(img => mediaKindForItem(img) === 'text');
    if(!items.length) return;
    items.forEach(item => {
        ensureTextMediaContent(item, () => {
            if(rerender) deps.render();
            deps.scheduleSave();
        });
    });
}
function nodeTextOutput(node){
    if(!node) return '';
    return (node.images || [])
        .filter(img => mediaKindForItem(img) === 'text')
        .map(textContentValue)
        .filter(Boolean)
        .join('\n\n')
        .trim();
}
function localDisplayUrlForMediaItem(img){
    if(!img) return '';
    const candidates = [
        img.url,
        img.originalLocalUrl,
        img.localUrl,
        img.sourceUrl,
        img.local_url,
        img.source_url
    ];
    const local = candidates.find(url => url && !/^https?:\/\//i.test(String(url)));
    return local || img.url || '';
}
function imageForDisplay(img){
    if(!img || typeof img !== 'object') return img;
    const localUrl = localDisplayUrlForMediaItem(img);
    if(!localUrl || localUrl === img.url) return img;
    return {
        ...img,
        url:localUrl,
        originalLocalUrl:img.originalLocalUrl || localUrl
    };
}
function resultMediaUrls(result){
    return CanvasGenerationResultModel.resultMediaUrls(result);
}
function taskIdsFromResult(result){
    return CanvasGenerationResultModel.taskIdsFromResult(result);
}
function mediaKindForUrls(urls, fallback='image'){
    return CanvasGenerationResultModel.mediaKindForUrls(urls, fallback);
}
function imageRefsOnly(refs){
    return (refs || []).filter(ref => ref?.url && mediaKindForItem(ref) === 'image');
}
function looksLikeImageMediaUrl(url){
    const text = String(url || '').trim().toLowerCase();
    if(!text) return false;
    if(text.startsWith('data:image/')) return true;
    if(text.startsWith('asset://')) return false;
    const path = text.split('?', 1)[0].split('#', 1)[0];
    return /\.(png|jpe?g|webp|gif|bmp|tiff)$/i.test(path);
}
function videoRefsOnly(refs){
    return (refs || []).filter(ref => ref?.url && mediaKindForItem(ref) === 'video' && !looksLikeImageMediaUrl(ref.url));
}
function isRemoteVideoReferenceUrl(url){
    return /^https?:\/\//i.test(String(url || '')) || /^asset:\/\//i.test(String(url || ''));
}
function audioRefsOnly(refs){
    return (refs || []).filter(ref => ref?.url && mediaKindForItem(ref) === 'audio');
}
function audioThumbLabel(img, audioIndex=0){
    if(Number.isFinite(audioIndex) && audioIndex > 0) return `音频${audioIndex}`;
    return String(img?.name || '').trim() || '音频';
}
function audioThumbHtml(label='音频', attrs='', extraClass=''){
    return `<div class="media-thumb audio-thumb${extraClass ? ` ${extraClass}` : ''}"${attrs}><div class="audio-thumb-art" aria-hidden="true"><span class="audio-thumb-bars"><span></span><span></span><span></span><span></span><span></span></span></div><span class="audio-thumb-footer">${deps.escapeHtml(label || '音频')}</span></div>`;
}
function formatAudioTime(seconds){
    const value = Math.max(0, Math.floor(Number(seconds) || 0));
    return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, '0')}`;
}
const audioPeakCache = new Map();
function audioWaveBuckets(w){
    return Math.max(32, Math.min(96, Math.round((Number(w) || 280) / 3.6)));
}
function audioWaveFallbackLevel(index, buckets){
    const count = Math.max(2, Number(buckets) || 64);
    const t = index / (count - 1);
    const env = .34 + .46 * Math.abs(Math.sin(t * 6.1) + .5 * Math.sin(t * 13.3 + .7) + .25 * Math.sin(t * 3.3)) / 1.75;
    return Math.max(8, Math.min(96, Math.round(env * 100)));
}
function audioPeaksFor(url, buckets){
    const key = `${String(url || '')}#${buckets}`;
    if(audioPeakCache.has(key)) return audioPeakCache.get(key);
    const job = (async () => {
        const Ctx = window.AudioContext || window.webkitAudioContext;
        if(!Ctx || !url) return null;
        const res = await fetch(url);
        const buf = await res.arrayBuffer();
        const ctx = new Ctx();
        try{
            const decoded = await ctx.decodeAudioData(buf);
            const data = decoded.getChannelData(0);
            const step = Math.max(1, Math.floor(data.length / buckets));
            const peaks = [];
            for(let i = 0; i < buckets; i++){
                let max = 0;
                const start = i * step;
                for(let j = 0; j < step; j++){
                    const value = Math.abs(data[start + j] || 0);
                    if(value > max) max = value;
                }
                peaks.push(max);
            }
            const top = peaks.reduce((acc, value) => Math.max(acc, value), 0);
            if(!top) return null;
            return peaks.map(value => Math.max(6, Math.min(100, Math.round(value / top * 100))));
        } finally {
            try{ ctx.close(); }catch(_){}
        }
    })().catch(() => null);
    audioPeakCache.set(key, job);
    return job;
}
function audioPlayerHtml(img, w, h){
    const url = deps.displayMediaUrl(img, img?.name || 'audio');
    const width = Number(w) || 280;
    const height = Number(h) || 150;
    const compact = height < 110 || width < 220;
    const buckets = audioWaveBuckets(width);
    const bars = Array.from({length: buckets}, (_, index) => `<span class="audio-bar" style="--audio-level:${audioWaveFallbackLevel(index, buckets)}%;--audio-bar-index:${index}" aria-hidden="true"></span>`).join('');
    const name = audioThumbLabel(img);
    return `<div class="node-img media-audio-card media-audio-player${compact ? ' is-compact' : ''}" data-audio-player data-audio-buckets="${buckets}" style="width:${width}px;height:${height}px">
        <div class="audio-player-name" title="${D("escapeAttr")(name)}">${deps.escapeHtml(name)}</div>
        <div class="audio-player-waveform" data-audio-waveform title="拖动时间线定位" role="slider" aria-label="音频进度" tabindex="0">${bars}<span class="audio-playhead" data-audio-playhead aria-hidden="true"></span><span class="audio-scrub-bubble" data-audio-bubble aria-hidden="true">0:00</span></div>
        <div class="audio-player-controls">
            <span class="audio-time" data-audio-time>0:00 / 0:00</span>
            <button class="audio-play-button" type="button" data-audio-toggle title="播放音频" aria-label="播放音频"><i data-lucide="play" class="audio-icon-play"></i><i data-lucide="pause" class="audio-icon-pause"></i></button>
        </div>
        <audio class="audio-player-media" src="${D("escapeAttr")(url)}" data-url="${D("escapeAttr")(img?.url || url)}" preload="metadata"></audio>
    </div>`;
}
function bindSmartAudioPlayers(root=D("world")){
    root?.querySelectorAll?.('[data-audio-player]').forEach(card => {
        if(card.dataset.audioBound === '1') return;
        const media = card.querySelector('.audio-player-media');
        const toggle = card.querySelector('[data-audio-toggle]');
        const waveform = card.querySelector('[data-audio-waveform]');
        const time = card.querySelector('[data-audio-time]');
        if(!media || !toggle || !waveform) return;
        card.dataset.audioBound = '1';
        const playhead = card.querySelector('[data-audio-playhead]');
        const bubble = card.querySelector('[data-audio-bubble]');
        const bars = () => Array.from(waveform.querySelectorAll('.audio-bar'));
        let scrubbing = false;
        let hovering = false;
        const setProgress = progress => {
            waveform.style.setProperty('--audio-progress', `${progress * 100}%`);
            if(playhead) playhead.style.left = `${progress * 100}%`;
            const list = bars();
            if(list.length) list.forEach((bar, index) => bar.classList.toggle('is-played', index / list.length < progress));
        };
        const update = () => {
            const duration = Number.isFinite(media.duration) ? media.duration : 0;
            const current = Number.isFinite(media.currentTime) ? media.currentTime : 0;
            const progress = duration > 0 ? Math.min(1, Math.max(0, current / duration)) : 0;
            setProgress(progress);
            if(time) time.textContent = `${formatAudioTime(current)} / ${formatAudioTime(duration)}`;
            const playing = !media.paused;
            toggle.title = playing ? '暂停音频' : '播放音频';
            toggle.setAttribute('aria-label', toggle.title);
            // 仅切换 class，图标显隐交给 CSS；不再每帧重建按钮子树 / 全文档 createIcons
            card.classList.toggle('is-playing', playing);
        };
        const timeAt = clientX => {
            const rect = waveform.getBoundingClientRect();
            if(!rect.width) return null;
            const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
            const duration = Number.isFinite(media.duration) ? media.duration : 0;
            return {ratio, seconds: ratio * duration};
        };
        const showBubble = (ratio, seconds) => {
            if(!bubble) return;
            bubble.style.left = `${ratio * 100}%`;
            bubble.textContent = formatAudioTime(seconds);
            bubble.style.display = 'block';
        };
        const hideBubble = () => { if(bubble) bubble.style.display = 'none'; };
        const seek = clientX => {
            const at = timeAt(clientX);
            if(!at || !Number.isFinite(media.duration)) return;
            media.currentTime = Math.min(media.duration, Math.max(0, at.seconds));
            update();
        };
        toggle.addEventListener('click', event => {
            event.preventDefault();
            event.stopPropagation();
            if(media.paused){
                document.querySelectorAll('[data-audio-player] .audio-player-media').forEach(other => {
                    if(other !== media && !other.paused) other.pause();
                });
                media.play().catch(() => {});
            }
            else media.pause();
        });
        waveform.addEventListener('pointerdown', event => {
            event.stopPropagation();
            if(Number(event.button || 0) !== 0) return;
            scrubbing = true;
            try{ waveform.setPointerCapture(event.pointerId); }catch(_){}
            const at = timeAt(event.clientX);
            if(at) showBubble(at.ratio, at.seconds);
            seek(event.clientX);
        });
        waveform.addEventListener('pointermove', event => {
            const at = timeAt(event.clientX);
            if(!at) return;
            if(scrubbing){ showBubble(at.ratio, at.seconds); seek(event.clientX); return; }
            if(!hovering) return;
            showBubble(at.ratio, at.seconds);
            if(playhead) playhead.style.left = `${at.ratio * 100}%`;
        });
        const endScrub = () => { scrubbing = false; };
        waveform.addEventListener('pointerup', endScrub);
        waveform.addEventListener('pointercancel', endScrub);
        waveform.addEventListener('pointerenter', () => { hovering = true; });
        waveform.addEventListener('pointerleave', () => {
            hovering = false;
            hideBubble();
            update();
        });
        waveform.addEventListener('keydown', event => {
            if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
            event.preventDefault();
            const duration = Number.isFinite(media.duration) ? media.duration : 0;
            const step = event.key === 'Home' ? 0 : event.key === 'End' ? duration : Math.max(1, duration * .05) * (event.key === 'ArrowLeft' ? -1 : 1);
            media.currentTime = event.key === 'Home' || event.key === 'End' ? step : Math.min(duration, Math.max(0, media.currentTime + step));
            update();
        });
        // Only player controls consume pointer events; the card surface must remain draggable as a node.
        [toggle, waveform].forEach(control => {
            ['mousedown','pointerdown','dblclick'].forEach(type => control.addEventListener(type, event => event.stopPropagation()));
        });
        ['loadedmetadata','durationchange','timeupdate','play','pause','ended'].forEach(type => media.addEventListener(type, update));
        update();
        // 仅在此处（绑定时）渲染一次本批次新增图标，播放期间的 update 不再扫描全文档
        if(window.lucide) lucide.createIcons();
        const src = media.dataset.url || media.getAttribute('src') || '';
        const buckets = Number(card.dataset.audioBuckets) || 64;
        if(src){
            audioPeaksFor(src, buckets).then(peaks => {
                if(!peaks || !card.isConnected) return;
                const list = bars();
                if(list.length !== peaks.length) return;
                list.forEach((bar, index) => bar.style.setProperty('--audio-level', `${peaks[index]}%`));
                card.dataset.audioPeaks = '1';
            });
        }
    });
}
function thumbMediaHtml(img, audioIndex=0){
    if(isFileMediaItem(img) || isTextMediaItem(img)){
        const preview = isTextMediaItem(img) ? textPreviewSnippet(img.textPreview || textContentValue(img), 96) : '';
        return `<div class="media-thumb file-thumb" data-media-url="${D("escapeAttr")(img.url || '')}" data-media-kind="${D("escapeAttr")(mediaKindForItem(img))}"><i data-lucide="${isTextMediaItem(img) ? 'file-text' : 'file'}"></i><span>${deps.escapeHtml(img.name || (isTextMediaItem(img) ? 'Text' : 'File'))}</span>${preview ? `<small>${deps.escapeHtml(preview)}</small>` : ''}</div>`;
    }
    if(isAudioMediaItem(img)){
        return audioThumbHtml(audioThumbLabel(img, audioIndex), ` data-media-url="${D("escapeAttr")(img.url || '')}" data-media-kind="audio"`);
    }
    if(isVideoMediaItem(img)) return `<div class="media-thumb video-thumb"><video src="${deps.escapeHtml(img.url)}" data-url="${deps.escapeHtml(img.url)}" muted preload="metadata" playsinline disablepictureinpicture controlslist="nodownload noplaybackrate noremoteplayback"></video></div>`;
    return `<img src="${deps.escapeHtml(deps.canvasThumbnailUrl(img, 384))}" data-original-src="${D("escapeAttr")(img.url || '')}" draggable="false" loading="eager" decoding="async">`;
}

    global.CanvasMediaHelpers = {
        configure,
        updateComfyInputsRow,
        updateNodeElementDuringResize,
        isVideoMediaItem,
        isAudioMediaItem,
        isTextMediaItem,
        isFileMediaItem,
        mediaKindForFile,
        mediaKindForItem,
        textContentValue,
        textPreviewSnippet,
        fetchTextMediaContent,
        ensureTextMediaContent,
        ensureNodeTextMedia,
        nodeTextOutput,
        localDisplayUrlForMediaItem,
        imageForDisplay,
        resultMediaUrls,
        taskIdsFromResult,
        mediaKindForUrls,
        imageRefsOnly,
        looksLikeImageMediaUrl,
        videoRefsOnly,
        isRemoteVideoReferenceUrl,
        audioRefsOnly,
        audioThumbLabel,
        audioThumbHtml,
        formatAudioTime,
        audioPlayerHtml,
        bindSmartAudioPlayers,
        thumbMediaHtml,
    };
})(typeof window !== 'undefined' ? window : this);

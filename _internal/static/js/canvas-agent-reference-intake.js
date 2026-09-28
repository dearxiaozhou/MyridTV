//** Agent reference intake: collect selected-node resources, add refs with dedupe, upload agent files. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    function D(name){return typeof deps[name] === 'function' ? deps[name]() : deps[name];}

function collectCanvasAgentSelectedResources(){
    const refs = [];
    const addNodeImages = node => {
        if(!node) return;
        const ownImages = (node.images || []).map((img, index) => deps.canvasAgentRefFromImage(img, node, index)).filter(Boolean);
        refs.push(...ownImages);
        if(!ownImages.length && ['smart-prompt','smart-loop'].includes(node.type)){
            refs.push(...visibleReferenceImagesFor(node).map((img, index) => deps.canvasAgentRefFromImage(img, node, index)).filter(Boolean));
        }
    };
    if(D("selectedImage").nodeId && Number.isFinite(Number(D("selectedImage").index))){
        const node = D("nodes").find(n => n.id === D("selectedImage").nodeId);
        const img = node?.images?.[Number(D("selectedImage").index)];
        const ref = deps.canvasAgentRefFromImage(img, node, Number(D("selectedImage").index));
        if(ref) refs.push(ref);
    }
    deps.selectedNodeIds().forEach(id => addNodeImages(D("nodes").find(n => n.id === id)));
    if(!refs.length) addNodeImages(deps.selectedNode());
    const seen = new Set();
    return refs.filter(ref => ref?.url && !seen.has(ref.url) && seen.add(ref.url));
}
function addCanvasAgentRefs(refs=[]){
    const seen = new Set(D("canvasAgentRefsState").map(ref => ref.url));
    (refs || []).forEach(ref => {
        if(!ref?.url || seen.has(ref.url)) return;
        seen.add(ref.url);
        D("canvasAgentRefsState").push(ref);
    });
    deps.renderCanvasAgentRefs();
}
const CANVAS_AGENT_FILE_TEXT_LIMIT = 24000;
const CANVAS_AGENT_TEXT_FILE_RE = /\.(txt|md|markdown|json|csv|tsv|srt|vtt|log|py|js|ts|jsx|tsx|html?|css|xml|yaml|yml|ini|cfg|conf|bat|cmd|ps1|sh|java|kt|c|h|cpp|cs|rs|go|rb|php|sql|gitignore)$/i;
const CANVAS_AGENT_BINARY_FILE_RE = /\.(png|jpe?g|webp|gif|bmp|mp4|webm|mov|m4v|avi|mkv|mp3|wav|m4a|aac|ogg|flac|pdf|docx?|xlsx?|pptx?|zip|rar|7z|exe|dll|apk|iso)$/i;
function isAgentTextFile(file){
    const type = String(file?.type || '').toLowerCase();
    const name = String(file?.name || '').toLowerCase();
    if(CANVAS_AGENT_BINARY_FILE_RE.test(name)) return false;
    return type.startsWith('text/') || type.includes('json') || type.includes('xml') || type.includes('javascript') || CANVAS_AGENT_TEXT_FILE_RE.test(name);
}
async function uploadCanvasAgentFiles(fileList){
    const files = Array.from(fileList || []);
    if(!files.length || !D("canvasAgentPanel")) return;
    deps.setCanvasAgentOpen(true);
    for(const file of files){
        try{
            deps.toast(`正在上传：${file.name}`);
            const form = new FormData();
            form.append('files', file, file.name);
            const response = await fetch(`${D("RH_OFFICIAL_PROXY_BASE")}${deps.canvasScopedUploadUrl()}`, {method:'POST', body:form});
            if(!response.ok) throw new Error(await deps.smartResponseErrorMessage(response, '文件上传失败'));
            const data = await response.json();
            const info = (data?.files || [])[0];
            if(!info?.url) throw new Error('上传结果缺少文件地址');
            const serverKind = String(info.kind || '');
            let kind = ['image', 'video', 'audio', 'text', 'file'].includes(serverKind) ? serverKind : deps.mediaKindForFile(file);
            const ref = {
                url:info.url,
                name:file.name,
                kind,
                content_type:info.content_type || file.type || ''
            };
            if(kind === 'file' && isAgentTextFile(file)) kind = ref.kind = 'text';
            if(ref.kind === 'text'){
                try{
                    const raw = await file.text();
                    const text = String(raw || '').replace(/\r\n/g, '\n').trim();
                    if(text){
                        ref.textContent = text.length > CANVAS_AGENT_FILE_TEXT_LIMIT
                            ? `${text.slice(0, CANVAS_AGENT_FILE_TEXT_LIMIT)}\n...(内容过长已截断)`
                            : text;
                        ref.textPreview = deps.textPreviewSnippet(ref.textContent);
                    }
                }catch(_) {}
            }
            addCanvasAgentRefs([ref]);
            deps.toast(ref.kind === 'text' ? `已加入文件：${file.name}（内容可被 Agent 学习）` : `已加入文件：${file.name}`);
        }catch(error){
            deps.toast(`上传失败：${file.name} — ${error?.message || error}`);
        }
    }
    if(D("canvasAgentFileInput")) D("canvasAgentFileInput").value = '';
}
function canvasAgentFileTranscript(refs){
    const sections = [];
    (refs || []).forEach(ref => {
        const kind = deps.mediaKindForItem(ref);
        if(kind !== 'text' && kind !== 'file') return;
        const name = deps.canvasAgentMediaLabel(ref);
        const content = deps.textContentValue(ref);
        if(content) sections.push(`【引用文件：${name}】\n${content}`);
        else sections.push(`【引用文件：${name}】（${kind === 'file' ? '二进制文件，只能参考文件名' : '空文件或内容未读取'}）`);
    });
    return sections.join('\n\n');
}

    global.CanvasAgentReferenceIntake = {
        configure,
        collectCanvasAgentSelectedResources,
        addCanvasAgentRefs,
        isAgentTextFile,
        uploadCanvasAgentFiles,
        canvasAgentFileTranscript,
    };
})(typeof window !== 'undefined' ? window : this);

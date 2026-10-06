//** Engine dispatch layer: prompt-LLM node runs + API / RunningHub / video generation paths. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    function D(name){return typeof deps[name] === 'function' ? deps[name]() : deps[name];}

// 输入框里写的是 @技能名（只显示名称，跟提示词框调用风格 @名 一个语义），
// 这里在真正送模型之前把技能正文展开回来。没命中技能库的名字原样保留。
function expandSkillMentions(text, opts){
    const fn = deps.expandSkillMentions;
    if(typeof fn !== 'function') return Promise.resolve(String(text || ''));
    return Promise.resolve(fn(text, opts)).catch(() => String(text || ''));
}

async function runPromptLLMNode(nodeId){
    const node = D("nodes").find(n => n.id === nodeId);
    if(!node || node.type !== 'smart-prompt') return;
    const rawMessage = (node.llmInstruction || node.text || '').trim();
    if(!rawMessage){ deps.toast(tr('smart.promptLlmNeedText')); return; }
    const rawSystemPrompt = (node.llmSystemPrompt || '').trim();
    const missingSkills = [];
    const noteMissing = names => names.forEach(name => { if(missingSkills.indexOf(name) < 0) missingSkills.push(name); });
    const [message, systemPrompt] = await Promise.all([
        expandSkillMentions(rawMessage, {onMissing: noteMissing}),
        expandSkillMentions(rawSystemPrompt, {onMissing: noteMissing})
    ]);
    if(missingSkills.length) deps.toast('技能未读到内容，已按原文发送：@' + missingSkills.join(' @'));
    node.llmEnabled = true;
    node.running = true;
    deps.render();
    try {
        const provider = deps.resolveChatProviderId(node.llmProvider || '');
        const model = deps.resolveChatModel(node.llmModel || '', provider);
        const mediaRefs = deps.promptNodeInputMediaForLLM(node);
        const images = deps.imageRefsOnly(mediaRefs).map(img => ({
            url:img.url,
            source_url:img.source_url || img.sourceUrl || '',
            name:img.name || '',
            nodeId:img.nodeId || '',
            imageIndex:img.imageIndex ?? ''
        })).filter(img => img.url);
        const videos = deps.videoRefsOnly(mediaRefs).map(video => video.url).filter(Boolean);
        const llmPayload = {
            message,
            messages:[],
            images,
            videos,
            model,
            provider,
            system_prompt:node.llmSystemEnabled ? (systemPrompt || 'You are a helpful prompt assistant.') : ''
        };
        const result = await fetch(deps.canvasLLMEndpointForPayload(llmPayload), {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify(llmPayload)
        }).then(async r => {
            if(!r.ok) throw new Error(await r.text());
            return r.json();
        });
        node.text = (result.text || '').trim();
        node.llmProvider = provider;
        node.llmModel = model;
        deps.scheduleSave();
    } catch(e) {
        deps.toast((e.message || tr('smart.promptLlmFailed')).slice(0, 160));
    } finally {
        node.running = false;
        deps.render();
    }
}
function comfyFieldKind(field, workflowData=deps.currentComfyWorkflowData()){
    if(['image','video','audio'].includes(field?.type)) return field.type;
    const meta = deps.comfyFieldMeta(field, workflowData);
    const excludedPromptNode = /previewany|preview|save\s*text|savetext|save_text/.test(meta.classType)
        || /预览|保存文本|保存文件|输出/.test(meta.nodeTitle)
        || /preview|markdown|output|save|file|path|name/.test(meta.inputKey);
    if(excludedPromptNode) return 'setting';
    const promptNode = /cliptextencode|primitivestringmultiline|prompt/.test(meta.classType)
        || /提示词|正向|负向|prompt/.test(meta.nodeTitle);
    const promptField = /(^|[\s_-])(prompt|positive|negative)([\s_-]|$)|提示词|正向|负向/.test(meta.fullText);
    if(promptNode && (meta.inputKey === 'text' || meta.inputKey === 'value' || field?.type === 'textarea' || promptField)) return 'prompt';
    if(promptField) return 'prompt';
    return 'setting';
}
async function runApiGeneration(prompt, refs, runSettings=D("settings"), sourceNode=null){
    if(!runSettings.provider_id || !runSettings.model) throw new Error(tr('smart.errNoApiModel'));
    const count = Math.max(1, Math.min(8, Number(runSettings.count || 1)));
    const referenceImages = deps.imageRefsOnly(refs);
    const payload = {
        prompt,
        provider_id:runSettings.provider_id,
        model:deps.rhOfficialModelForRun(runSettings.model, referenceImages),
        size:deps.sizeForRun(runSettings),
        quality:runSettings.quality || 'auto',
        n:1,
        reference_images:referenceImages,
        canvas_id:D("canvasId") || '',
        canvas_title:String(D("canvas")?.title || document.getElementById('smartTitle')?.textContent || '').trim(),
        node_id:String(sourceNode?.id || '')
    };
    // —— 3D预演：强制 blender 平台 + 单视频 ——
    if((runSettings.engine || D("settings").engine) === 'blender'){
        deps.normalizePrevizLlmSettings(runSettings);
        payload.provider_id = 'blender';
        payload.model = 'blender-previz';
        payload.n = 1;
        payload.count = 1;
        payload.aspectRatio = deps.rhOfficialAspectRatioForRun(runSettings);
        payload.previz_llm_enabled = runSettings.previzLlmEnabled === true;
        payload.previz_llm_provider = runSettings.previzLlmProvider || '';
        payload.previz_llm_model = runSettings.previzLlmModel || '';
        delete payload.size;
        delete payload.quality;
    }
    if(deps.shouldUseRhOfficialProxy(payload)){
        payload.resolution = deps.rhOfficialResolutionForRun(runSettings);
        payload.aspectRatio = deps.rhOfficialAspectRatioForRun(runSettings);
        if(!payload.quality || payload.quality === 'auto') payload.quality = 'medium';
    }
    const taskBase = deps.shouldUseRhOfficialProxy(payload) ? D("RH_OFFICIAL_PROXY_BASE") : '';
    const tasks = await Promise.all(Array.from({length:count}, () => fetch(`${taskBase}/api/canvas-image-tasks`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)}).then(async r => {
        if(!r.ok) throw new Error(await r.text());
        return r.json();
    })));
    return {taskIds:tasks.map(task => task.task_id).filter(Boolean), count};
}
async function runRunningHubGeneration(prompt, refs, runSettings=D("settings")){
    const ref = deps.selectedRunningHubRef(runSettings);
    if(!ref) throw new Error(tr('smart.rhNeedConfig'));
    const fields = deps.rhActiveFields(runSettings);
    if(!fields.length) throw new Error(tr('smart.rhNeedFields'));
    const randomValues = {};
    const mode = ref.kind;
    const media = deps.rhMediaForRun(prompt, refs);
    const nodeInfoList = await deps.rhBuildNodeInfoList(media, runSettings, randomValues);
    const workflowExtras = mode === 'workflow' ? await deps.rhBuildWorkflowRequestExtras(media, nodeInfoList, runSettings) : {};
    const endpoint = mode === 'workflow' ? '/api/runninghub/workflow-submit' : '/api/runninghub/submit';
    const body = mode === 'workflow'
        ? {workflowId:ref.id, nodeInfoList, useWallet:runSettings.rhPayment === 'wallet', ...workflowExtras}
        : {webappId:ref.id, nodeInfoList, instanceType:runSettings.rhInstanceType || '', useWallet:runSettings.rhPayment === 'wallet'};
    const submit = await fetch(endpoint, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify(body)
    }).then(async r => {
        const data = await r.json();
        if(!r.ok || data.success === false) throw new Error(data.detail || data.error || tr('smart.rhFailed'));
        return data.data || data;
    });
    const taskId = submit.taskId;
    if(!taskId) throw new Error(tr('smart.rhNoTaskId'));
    for(let i = 0; i < 720; i++){
        await sleep(2500);
        const data = await fetch(`/api/runninghub/query?taskId=${encodeURIComponent(taskId)}`).then(async r => {
            const json = await r.json();
            if(!r.ok || json.success === false) throw new Error(json.detail || json.error || tr('smart.rhFailed'));
            return json.data || json;
        });
        if(data.status === 'SUCCESS'){
            const urls = data.urls || [];
            if(!urls.length) throw new Error(tr('smart.rhOutputsEmpty'));
            return urls;
        }
        if(data.status === 'FAILED') throw new Error(data.failReason || tr('smart.rhFailed'));
    }
    throw new Error(tr('smart.rhTimeout'));
}
async function runApiVideoGeneration(prompt, refs, runSettings=D("settings")){
    if(!runSettings.videoModel) throw new Error(tr('smart.errNoVideoModel'));
    try {
        let uploadedRefs = deps.applyUploadedUrlsToSmartRefs(refs, runSettings);
        let referenceMode = deps.videoReferenceModeValue(runSettings);
        // 可信素材：来源=素材库时启用 asset:// 认证路由（与参考模式解耦，独立开关）
        const trustedSource = (runSettings.videoTrustedAsset === true && ['library','cloud','manual'].includes(runSettings.videoTrustedSource)) ? runSettings.videoTrustedSource : 'none';
        const useAssetUris = trustedSource === 'library';
        const targetPlatform = deps.videoProviderPlatform(runSettings.videoProvider || 'comfly');
        if(trustedSource === 'cloud'){
            await deps.uploadCurrentSmartVideosToCloud();
            uploadedRefs = deps.applyUploadedUrlsToSmartRefs(refs, runSettings);
        }
        let mismatchedAsset = false;
        const effUrl = ref => {
            const uris = (ref && ref.asset_uris && typeof ref.asset_uris === 'object') ? ref.asset_uris : null;
            if(useAssetUris && uris && Object.keys(uris).length){
                // asset:// 与平台绑定：取当前视频平台对应的认证地址；该素材没注册到这个平台就回退本地 url
                if(targetPlatform && uris[targetPlatform]) return uris[targetPlatform];
                mismatchedAsset = true;
            }
            return ref?.url;
        };
        const refImages = deps.imageRefsOnly(uploadedRefs).map((ref, i) => {
            const item = {url:effUrl(ref), name:ref.name || `图${i + 1}`};
            if(runSettings.videoUseFrameRoles){
                if(i === 0) item.role = 'first_frame';
                else if(i === 1) item.role = 'last_frame';
            }
            return item;
        });
        const manualVideo = deps.manualSmartVideoLink(runSettings)?.url || '';
        let refVideos = manualVideo ? deps.manualSmartMediaLinks(runSettings).map(item => item.url).filter(Boolean) : deps.videoRefsOnly(uploadedRefs).map(ref => effUrl(ref)).filter(Boolean);
        const refAudios = deps.audioRefsOnly(uploadedRefs).map(ref => effUrl(ref)).filter(Boolean).slice(0, 3);
        // 官方编辑/延长任务：提示词必须用「严格编辑视频N」「向前/向后延长视频N」句式指代源视频，
        // 不能写成「参考视频N」，否则被模型误判为参考任务（官方硬约束；Seedance 2.0/2.5 系列均支持编辑·延长）。
        if(referenceMode === 'video_edit' || referenceMode === 'video_extend'){
            const isSeedanceFamily = targetPlatform === 'volcengine' || /seedance/i.test(String(runSettings.videoModel || ''));
            if(!isSeedanceFamily){
                deps.toast('视频编辑/延长是 Seedance 系列能力，当前模型按全能参考提交');
                referenceMode = 'mixed';
            } else {
                if(!refVideos.length) throw new Error(referenceMode === 'video_edit' ? '视频编辑需要先连入 1 段源视频（把视频节点连到本节点输入）' : '视频延长需要先连入 1 段源视频（把视频节点连到本节点输入）');
                if(refVideos.length > 1) deps.toast('编辑/延长只使用最先连入的 1 段源视频');
                refVideos = refVideos.slice(0, 1);
                const directive = referenceMode === 'video_edit'
                    ? `严格编辑视频1：${prompt}`
                    : ((runSettings.videoExtendMode === 'before' ? '向前延长视频1：' : '向后延长视频1：') + prompt);
                prompt = `请勿复述视频1原内容。${directive}`;
            }
        }
        if(mismatchedAsset) deps.toast('部分认证素材属于其它平台，已回退为普通素材。切换到对应平台的视频接口才能用 asset:// 认证地址。');
        const payload = {
            prompt,
            provider_id: runSettings.videoProvider || 'comfly',
            model: runSettings.videoModel,
            duration: Math.max(1, Math.min(60, Number(runSettings.videoDuration) || 5)),
            aspect_ratio: runSettings.videoAspect || '16:9',
            canvas_id: D("canvasId"),
            resolution: runSettings.videoResolution || '',
            images: refImages,
            videos: refVideos,
            audios: refAudios,
            enhance_prompt: Boolean(runSettings.videoEnhancePrompt),
            enable_upsample: false,
            watermark: false,
            camerafixed: false,
            generate_audio: Boolean(runSettings.videoGenerateAudio),
            multimodal: false,
            trusted_asset: useAssetUris,
            reference_mode: referenceMode
        };
        const result = await fetch('/api/canvas-video', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify(payload)
        }).then(async r => { if(!r.ok) throw new Error(await deps.smartResponseErrorMessage(r, tr('smart.errRunFailed'))); return r.json(); });
        if(result && result.jimeng_pending) throw new CanvasSmartTaskSupervisor.JimengPendingSignal({submitId:result.submit_id, kind:result.kind || 'video', queueInfo:result.queue_info, message:result.message});
        return {
            urls: deps.resultMediaUrls(result),
            taskIds: deps.taskIdsFromResult(result),
            kind: 'video',
            raw: result
        };
    } finally {
        deps.setTransientSmartCloudLinks([]);
    }
}
async function urlToBase64(url){
    const res = await fetch(url);
    if(!res.ok) throw new Error(tr('smart.errImageRead'));
    const blob = await res.blob();
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(blob);
    });
}
function sleep(ms){ return new Promise(resolve => setTimeout(resolve, ms)); }

    global.CanvasEngineDispatch = {
        configure,
        runPromptLLMNode,
        comfyFieldKind,
        runApiGeneration,
        runRunningHubGeneration,
        runApiVideoGeneration,
        urlToBase64,
        sleep,
    };
})(typeof window !== 'undefined' ? window : this);

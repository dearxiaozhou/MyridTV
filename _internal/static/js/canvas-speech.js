/* Speech nodes use the canvas media player and server-side provider credentials. */
(function(global){
    'use strict';
    let deps = {};
    const active = new Set();
    const modes = {'mimo-v2.5-tts-voicedesign':'音色设计', 'mimo-v2.5-tts':'预置音色', 'mimo-v2.5-tts-voiceclone':'音色复刻'};
    const voices = ['mimo_default','冰糖','茉莉','苏打','白桦','Mia','Chloe','Milo','Dean'];
    const e = value => deps.escapeHtml(String(value ?? ''));
    function configure(options){deps = options;}
    function providers(){return deps.getProviders().filter(p => p.enabled !== false && (p.audio_models || []).length);}
    function modelFor(node, provider){return node.speechModel || provider?.audio_models?.[0] || '';}
    function sources(node){
        const ids = new Set(deps.getConnections().filter(c => c.to === node.id).map(c => c.from));
        return deps.getNodes().filter(n => ids.has(n.id) && (n.type === 'smart-prompt' || n.text || n.content || n.prompt));
    }
    function value(node, field){
        const id = node[field + 'Source'];
        if(!id) return String(node[field] || '').trim();
        const source = sources(node).find(n => n.id === id);
        if(!source) throw new Error('所选上游文本已断开，请重新连接或选择手写文本');
        return String(source.text || source.content || source.prompt || '').trim();
    }
    function sourceOptions(node, field){
        const id = node[field + 'Source'] || '';
        const inputs = sources(node);
        return `<option value="">手写文本</option>${id && !inputs.some(n => n.id === id) ? `<option value="${e(id)}" selected>上游已断开</option>` : ''}${inputs.map(n => `<option value="${e(n.id)}" ${id === n.id ? 'selected' : ''}>上游：${e(n.title || '文本节点')}</option>`).join('')}`;
    }
    function body(node){
        const list = providers();
        const pid = node.speechProvider || list[0]?.id || '';
        const provider = list.find(p => p.id === pid);
        const model = modelFor(node, provider);
        const modelOptions = provider?.audio_models || [];
        const design = model === 'mimo-v2.5-tts-voicedesign';
        const clone = model === 'mimo-v2.5-tts-voiceclone';
        const busy = active.has(node.id);
        const select = (field,label,options) => `<label>${label}<select data-speech="${field}" aria-label="${label}" ${busy ? 'disabled' : ''}>${options.map(([v,t])=>`<option value="${e(v)}" ${String(node[field] ?? '')===v ? 'selected' : ''}>${e(t)}</option>`).join('')}</select></label>`;
        const input = (field, label, placeholder) => {
            let text = node[field] || '';
            try {text = value(node, field);} catch(_) {text = '';}
            const hasSources = sources(node).length > 0 || node[field + 'Source'];
            return `<label class="speech-field"><span>${label}${hasSources ? `<select data-speech="${field}Source" aria-label="${label}来源" ${busy ? 'disabled' : ''}>${sourceOptions(node, field)}</select>` : ''}</span><textarea data-speech="${field}" aria-label="${label}" placeholder="${e(placeholder)}" ${node[field + 'Source'] ? 'readonly' : ''} ${busy ? 'disabled' : ''}>${e(text)}</textarea></label>`;
        };
        return `<div class="speech-card">
            <div class="speech-heading">语音生成</div>
            <div class="speech-workspace"><div class="speech-design"><div class="speech-controls"><label>平台<select data-speech="speechProvider" aria-label="语音平台" ${busy ? 'disabled' : ''}><option value="">请选择平台</option>${pid && !provider ? `<option value="${e(pid)}" selected>平台不可用</option>` : ''}${list.map(p => `<option value="${e(p.id)}" ${pid === p.id ? 'selected' : ''}>${e(p.name || p.id)}</option>`).join('')}</select></label><label>生成方式<select data-speech="speechModel" aria-label="语音生成方式" ${busy ? 'disabled' : ''}>${model && !modelOptions.includes(model) ? `<option value="${e(model)}" selected disabled>模型未配置：${e(model)}</option>` : ''}${modelOptions.map(id => `<option value="${e(id)}" ${model === id ? 'selected' : ''}>${e(provider?.model_display_names?.[id] || modes[id] || id)}</option>`).join('')}</select></label></div>
            ${!design && !clone ? `<label class="speech-field">预置音色<select data-speech="speechVoice" aria-label="预置音色" ${busy ? 'disabled' : ''}>${voices.map(v => `<option value="${e(v)}" ${(node.speechVoice || 'mimo_default') === v ? 'selected' : ''}>${v === 'mimo_default' ? 'MiMo 默认' : e(v)}</option>`).join('')}</select></label>` : ''}
            <div class="speech-controls">${select('speechFormat','输出格式',[['wav','WAV'],['mp3','MP3']])}${design ? select('speechOptimize','台词处理',[['','原文朗读'],['true','智能优化 / 自动写词']]) : !clone ? select('speechSinging','表演模式',[['','说话'],['true','唱歌']]) : ''}</div>

            <div class="speech-quick-controls">${select('speechSpeed','语速',[['','跟随描述'],['slow','慢速'],['normal','中速'],['fast','快速']])}${select('speechEmotion','情绪',[['','跟随描述'],['calm','平静'],['happy','开心'],['sad','悲伤'],['angry','愤怒'],['fear','恐惧'],['surprise','惊讶'],['tired','疲惫'],['tender','温柔']])}${select('speechDialect','语言 / 方言',[['','跟随描述'],['mandarin','普通话'],['cantonese','粤语'],['northeastern','东北话'],['sichuan','四川话'],['henan','河南话']])}</div>
            ${input('speechStyle', design ? '声音描述' : '表演指导（可选）', design ? '例如：三十岁左右的女性，声音清冷、略带沙哑，语速缓慢。' : '例如：轻声说话，带着疲惫，在句尾稍作停顿。')}
            </div><div class="speech-script">
            ${clone ? `<div class="speech-reference"><button type="button" data-speech-upload ${busy ? 'disabled' : ''}>${node.speechReference ? '更换音色样本' : '上传音色样本'}</button><input type="file" data-speech-file accept=".mp3,.wav,audio/mpeg,audio/wav" hidden>${node.speechReference ? `<span title="${e(node.speechReference.name)}">${e(node.speechReference.name)}</span>${deps.audioPlayerHtml(node.speechReference,300,64)}` : ''}</div>` : ''}
<div class="speech-tagbar"><div class="speech-tags">${['吸气','叹气','轻笑','哽咽','停顿'].map(tag=>`<button type="button" data-speech-tag="${tag}" ${busy || node.speechTextSource ? 'disabled' : ''}>${tag}</button>`).join('')}</div><div class="speech-actions"><button type="button" class="speech-generate" data-speech-run ${busy ? 'disabled' : ''}>${busy ? '正在生成…' : '生成语音'}</button></div></div>${input('speechText','朗读文本',design && String(node.speechOptimize)==='true' ? '可留空，由模型根据声音描述生成台词。' : '填写需要朗读的台词。')}
            </div></div>
            ${node.speechError ? `<div class="speech-footer"><div class="speech-status error" role="status">${e(node.speechError)}</div></div>` : ''}
        </div>`;
    }
    let picker = null;
    let pickerSequence = 0;
    function closePicker(restoreFocus = false){
        if(!picker) return;
        const old = picker; picker = null;
        cancelAnimationFrame(old.frame);
        old.menu.remove();
        old.button.setAttribute('aria-expanded','false');
        old.button.removeAttribute('aria-controls');
        if(restoreFocus && old.button.isConnected) old.button.focus({preventScroll:true});
    }
    function openPicker(button, select, nodeId){
        if(button.disabled) return;
        if(picker?.button === button) return closePicker(true);
        closePicker();
        const menu = document.createElement('div');
        menu.className = 'speech-picker-menu';
        menu.id = 'speech-picker-' + (++pickerSequence);
        menu.setAttribute('role','listbox');
        menu.setAttribute('aria-label', select.getAttribute('aria-label'));
        menu.innerHTML = Array.from(select.options, (option,index) => `<button type="button" role="option" class="unified-option${option.selected ? ' active' : ''}" data-speech-option="${index}" aria-selected="${option.selected}" ${option.disabled ? 'disabled' : ''}><span class="unified-option-name">${e(option.textContent)}</span><span class="unified-option-check">${option.selected ? '✓' : ''}</span></button>`).join('');
        document.body.append(menu);
        const state = picker = {button,select,menu,frame:0};
        button.setAttribute('aria-expanded','true');
        button.setAttribute('aria-controls',menu.id);
        ['pointerdown','mousedown','click','dblclick','wheel'].forEach(type => menu.addEventListener(type, event=>event.stopPropagation()));
        const options = Array.from(menu.querySelectorAll('[role=option]'));
        const enabled = options.filter(option=>!option.disabled);
        function position(){
            if(picker !== state) return;
            if(!button.isConnected || button.disabled) return closePicker();
            const rect = button.getBoundingClientRect();
            if(rect.bottom < 0 || rect.top > innerHeight || rect.right < 0 || rect.left > innerWidth) return closePicker();
            const width = Math.min(Math.max(rect.width,180),innerWidth-16);
            const above = rect.top-14, below = innerHeight-rect.bottom-14;
            const desired = Math.min(menu.scrollHeight,280);
            const up = below < desired && above > below;
            menu.style.width = width + 'px';
            menu.style.maxHeight = Math.max(40,Math.min(280,up ? above : below)) + 'px';
            menu.style.left = Math.max(8,Math.min(rect.left,innerWidth-width-8)) + 'px';
            menu.style.top = (up ? rect.top-6-menu.offsetHeight : rect.bottom+6) + 'px';
            state.frame = requestAnimationFrame(position);
        }
        position();
        function choose(option){
            if(option.disabled) return;
            const field = select.dataset.speech;
            select.selectedIndex = Number(option.dataset.speechOption);
            closePicker();
            select.dispatchEvent(new Event('change',{bubbles:true}));
            document.querySelector(`.speech-smart-node[data-id="${CSS.escape(nodeId)}"] [data-speech-picker="${field}"]`)?.focus({preventScroll:true});
        }
        options.forEach(option=>option.addEventListener('click',()=>choose(option)));
        menu.addEventListener('keydown',event=>{
            event.stopPropagation();
            const at = enabled.indexOf(document.activeElement);
            let next;
            if(event.key==='ArrowDown') next=(at+1)%enabled.length;
            if(event.key==='ArrowUp') next=(at-1+enabled.length)%enabled.length;
            if(event.key==='Home') next=0;
            if(event.key==='End') next=enabled.length-1;
            if(next!==undefined){event.preventDefault();enabled[next]?.focus({preventScroll:true});enabled[next]?.scrollIntoView({block:'nearest'});}
            if(event.key==='Escape'){event.preventDefault();closePicker(true);}
            if(event.key==='Tab') closePicker(true);
        });
        (options.find(option=>option.getAttribute('aria-selected')==='true' && !option.disabled) || enabled[0])?.focus({preventScroll:true});
    }
    function bindPickers(el,node){
        el.querySelectorAll('select[data-speech]').forEach(select=>{
            select.hidden = true;
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'smart-pill speech-picker';
            button.dataset.speechPicker = select.dataset.speech;
            button.disabled = select.disabled;
            button.setAttribute('role','combobox');
            button.setAttribute('aria-haspopup','listbox');
            button.setAttribute('aria-expanded','false');
            button.setAttribute('aria-label',select.getAttribute('aria-label'));
            const label = select.selectedOptions[0]?.textContent || '';
            button.title = label;
            button.innerHTML = `<span>${e(label)}</span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>`;
            select.after(button);
            ['pointerdown','mousedown','click','dblclick'].forEach(type=>button.addEventListener(type,event=>event.stopPropagation()));
            button.addEventListener('click',()=>openPicker(button,select,node.id));
            button.addEventListener('keydown',event=>{
                event.stopPropagation();
                if(event.key==='ArrowDown' || event.key==='ArrowUp'){event.preventDefault();openPicker(button,select,node.id);}
                if(event.key==='Escape') closePicker(true);
            });
        });
    }
    document.addEventListener('pointerdown',event=>{
        if(picker && !picker.menu.contains(event.target) && !picker.button.contains(event.target)) closePicker();
    },true);
    window.addEventListener('blur',()=>closePicker());
    function bind(el, node){
        const current = () => deps.getNodes().find(n=>n.id===node.id) || node;
        bindPickers(el,node);
        // Controls retain their browser focus instead of invoking node selection.
        el.querySelectorAll('[data-speech], [data-speech-run], [data-speech-tag], [data-speech-upload], [data-speech-file], .speech-output, .speech-reference, .speech-preview').forEach(control => {
            ['pointerdown','mousedown','click','dblclick'].forEach(type => control.addEventListener(type, event => event.stopPropagation()));
        });
        el.querySelectorAll('[data-speech]').forEach(input => {
            input.addEventListener('keydown', event => event.stopPropagation());
            input.addEventListener(input.tagName === 'TEXTAREA' ? 'input' : 'change', () => {
                node = current();
                node[input.dataset.speech] = input.value;
                if(input.dataset.speech === 'speechProvider'){
                    const selected = providers().find(p => p.id === input.value);
                    if(!(selected?.audio_models || []).includes(node.speechModel)) node.speechModel = selected?.audio_models?.[0] || '';
                }
                delete node.speechError;
                deps.scheduleSave();
                if(input.tagName !== 'TEXTAREA') deps.render();
            });
        });
        el.querySelectorAll('[data-speech-tag]').forEach(button => button.addEventListener('click', () => {
            const input = el.querySelector('[data-speech="speechText"]');
            if(!input || input.readOnly || input.disabled) return;
            input.setRangeText('[' + button.dataset.speechTag + ']', input.selectionStart, input.selectionEnd, 'end');
            input.dispatchEvent(new Event('input', {bubbles:true}));
            input.focus({preventScroll:true});
        }));
        const fileInput = el.querySelector('[data-speech-file]');
        el.querySelector('[data-speech-upload]')?.addEventListener('click', () => fileInput.click());
        fileInput?.addEventListener('change', async () => {
            node = current();
            const file = fileInput.files?.[0];
            if(!file || active.has(node.id)) return;
            if(!/\.(mp3|wav)$/i.test(file.name)) return deps.toast('音色样本仅支持 MP3 或 WAV');
            if(Math.ceil(file.size / 3) * 4 + 32 > 10000000) return deps.toast('音色样本编码后不能超过 10 MB，请上传更短的音频');
            active.add(node.id);
            delete node.speechError;
            deps.render();
            try {
                const form = new FormData(); form.append('file',file);
                const response = await fetch('/api/ai/upload?scope=canvas&canvas_id=' + encodeURIComponent(deps.getCanvasId()), {method:'POST',body:form});
                const result = await response.json();
                if(!response.ok || !result.files?.[0]?.url) throw new Error(result.detail || '音色样本上传失败');
                const target = deps.getNodes().find(n=>n.id===node.id);
                if(!target) return;
                node = target;
                node.speechReference = {...result.files[0],kind:'audio'};
            } catch(error){node=current();node.speechError=error.message; deps.toast(error.message);}
            finally{active.delete(node.id); deps.render(); deps.scheduleSave();}
        });
        el.querySelector('[data-speech-run]')?.addEventListener('click', event => {event.stopPropagation(); run(current());});
    }
    async function run(node){
        if(active.has(node.id)) return;
        active.add(node.id);
        delete node.speechError;
        const started = Date.now();
        const taskId = 'speech_' + crypto.randomUUID().replaceAll('-','');
        const runLog = {nodeId:node.id,nodeType:'smart-speech',kind:'audio',settings:{engine:'api',provider_id:node.speechProvider || providers()[0]?.id || '',model:node.speechModel || 'mimo-v2.5-tts-voicedesign'},prompt:node.speechText || '',refs:[],request:{}};
        const log = (status,outputs=[],error='') => deps.addSmartGenerationLog?.({run:runLog,taskId,update:true,status,outputs,error,runMs:Date.now()-started});
        log('running');
        try {
            const provider = providers().find(p => p.id === (node.speechProvider || providers()[0]?.id));
            if(!provider) throw new Error('请在 API 设置中配置并启用 MiMo 音频模型');
            node.speechProvider = provider.id;
            const model = modelFor(node, provider);
            if(!(provider.audio_models || []).includes(model)) throw new Error('此模型已从平台配置移除，请重新选择语音模型');
            node.speechModel = model;
            const text = value(node, 'speechText'), style = value(node, 'speechStyle');
            const optimize = model === 'mimo-v2.5-tts-voicedesign' && String(node.speechOptimize)==='true';
            if(!text && !optimize) throw new Error('请填写朗读文本，或连接并选择上游文本');
            if(model === 'mimo-v2.5-tts-voicedesign' && !style) throw new Error('音色设计需要填写声音描述');
            if(model === 'mimo-v2.5-tts-voiceclone' && !node.speechReference?.url) throw new Error('请上传 MP3 或 WAV 音色样本');
            if(!provider.has_key) throw new Error('尚未配置 MiMo API Key，请打开 API 设置，选择 MiMo 并保存密钥');
            deps.render();
            const request = {
                provider_id:provider.id, model, text, style, voice:node.speechVoice || 'mimo_default',
                format:node.speechFormat || 'wav', optimize_text_preview:optimize, reference_url:node.speechReference?.url || '',
                speed:node.speechSpeed || '', emotion:node.speechEmotion || '', dialect:node.speechDialect || '',
                singing:model === 'mimo-v2.5-tts' && String(node.speechSinging)==='true',
                canvas_id:deps.getCanvasId(), canvas_title:deps.getCanvasTitle(), node_id:node.id, node_title:node.title || '语音生成', client_task_id:taskId
            };
            runLog.prompt = text;
            runLog.request = {format:request.format,voice:request.voice,style,optimize_text_preview:optimize,speed:request.speed,emotion:request.emotion,dialect:request.dialect,singing:request.singing};
            runLog.refs = node.speechReference ? [{url:node.speechReference.url,name:node.speechReference.name,kind:'audio'}] : [];
            log('running');
            const response = await fetch('/api/canvas-audio', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(request)});
            const result = await response.json();
            if(!response.ok || result.ok === false) throw new Error(result.detail || result.error || '语音生成失败');
            if(!result.items?.[0]?.url) throw new Error('未收到有效音频结果');
            log('success',result.items.map(item=>item.url));
            const target = deps.getNodes().find(n=>n.id===node.id);
            if(!target) return;
            node = target;
            node.images = result.items.map(item => ({...item, generatedResult:true, kind:'audio'}));
            node.speechFinalText = result.final_text_preview || '';
            node.speechLastRun = {...request, at:Date.now()};
            node.status = 'ready';
            const output = deps.createSpeechOutputNode?.(node,node.images,taskId);
            if(output) node.speechOutputNodeId = output.id;
        } catch(error){
            node = deps.getNodes().find(n=>n.id===node.id) || node;
            node.speechError = error.message || '语音生成失败';
            log('failed',[],node.speechError);
            deps.toast(node.speechError);
        } finally {
            active.delete(node.id);
            deps.render();
            deps.scheduleSave();
        }
    }
    global.CanvasSpeech = {configure, body, bind, run, providers, value, isActive:id=>active.has(id)};
})(window);

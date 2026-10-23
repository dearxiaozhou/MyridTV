/* Independent offline previs UI. The host supplies node persistence and generation. */
(function(global){
    'use strict';
    let metadataPromise;
    const clone=value=>JSON.parse(JSON.stringify(value));
    const poses=[['STAND','站立'],['WALK','行走'],['RUN','跑步'],['SIT','坐姿']];
    const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    async function metadata(){
        if(!metadataPromise) metadataPromise=fetch('/api/plugins/offline-previs').then(r=>{if(!r.ok)throw Error('离线预演插件未加载');return r.json();}).catch(e=>{metadataPromise=null;throw e;});
        return metadataPromise;
    }
    function input(path,value,label,step='.1'){
        return `<label>${label}<input data-pv-path="${path}" type="number" step="${step}" value="${Number(value)}" required></label>`;
    }
    function vector(path,value,label){
        return `<fieldset class="pv-vector"><legend>${label}</legend>${['X','Y','Z'].map((axis,i)=>input(path+'.'+i,value[i],axis)).join('')}</fieldset>`;
    }
    function select(path,value,options,label){
        return `<label class="pv-select-label">${label}<select data-pv-path="${path}">${options.map(([key,text])=>`<option value="${escape(key)}" ${key===value?'selected':''}>${escape(text)}</option>`).join('')}</select></label>`;
    }
    function set(object,path,value){
        const keys=path.split('.');let target=object;
        keys.slice(0,-1).forEach(key=>{target=target[key];});target[keys[keys.length-1]]=value;
    }
    async function open(context){
        try{
            const originalNode=context.getNode();
            const meta=await metadata();
            if(!originalNode || context.getNode()?.id!==originalNode.id)throw Error('节点已切换，请重新打开起落幅设置');
            const spec=clone(context.settings.previzOfflineSpec || meta.default_spec);
            if(!context.getNode())throw Error('请先选择3D预演节点');
            const overlay=document.createElement('div');overlay.className='pv-plugin-overlay';
            const cameraOptions=meta.camera_presets.map(p=>[p,p==='01_慢镜头感'?'固定机位':p.replace(/^\d+_/, '')]);
            overlay.innerHTML=`<form class="pv-plugin-dialog" aria-label="离线起落幅设置"><header><div><h2>起落幅预演</h2><p>设置两个机位和人物状态，在本机生成两张图。</p></div><button type="button" data-pv-close aria-label="关闭起落幅设置">×</button></header>
            <section class="pv-camera"><h3>约束摄像机</h3><div class="pv-top-fields">${select('camera.preset',spec.camera.preset,cameraOptions,'运镜')}${input('camera.lens_mm',spec.camera.lens_mm,'焦距 / mm','1')}${input('duration',(spec.frame_end-spec.frame_start)/spec.fps,'时长 / 秒','1')}</div>
            <div class="pv-vector-grid">${vector('camera.start',spec.camera.start,'起机位')}${vector('camera.end',spec.camera.end,'落机位')}${vector('camera.aim_start',spec.camera.aim_start,'起始看向')}${vector('camera.aim_end',spec.camera.aim_end,'结束看向')}</div></section>
            <section><h3>人物资产 <span>位置单位为米，Z为高度</span></h3>${spec.actors.slice(0,2).map((actor,i)=>`<details class="pv-actor" ${i===0?'open':''}><summary>人物 ${i+1} · ${actor.asset==='y_bot'?'Y_Bot':'X_Bot'}</summary><div class="pv-top-fields">${select('actors.'+i+'.asset',actor.asset,[['x_bot','X_Bot'],['y_bot','Y_Bot']],'机器人')}${select('actors.'+i+'.start.pose',actor.start.pose,poses,'起始姿态')}${select('actors.'+i+'.end.pose',actor.end.pose,poses,'结束姿态')}</div><div class="pv-vector-grid">${vector('actors.'+i+'.start.position',actor.start.position,'起始位置')}${vector('actors.'+i+'.end.position',actor.end.position,'结束位置')}</div><div class="pv-top-fields">${input('actors.'+i+'.start.yaw_deg',actor.start.yaw_deg,'起始朝向 / 度','5')}${input('actors.'+i+'.end.yaw_deg',actor.end.yaw_deg,'结束朝向 / 度','5')}</div></details>`).join('')}</section>
            <p class="pv-note">相机通过路径和瞄准约束连接起落机位。这里只生成起落幅，不执行完整走跑动画。</p><p class="pv-error" role="alert"></p><footer><div class="pv-artifacts"></div><button type="button" data-pv-close>取消</button><button type="submit" class="primary">保存设置</button><button type="button" class="primary" data-pv-generate>生成起落幅</button></footer></form>`;
            const form=overlay.querySelector('form');
            function close(){overlay.remove();document.removeEventListener('keydown',keyDown);}
            function keyDown(event){if(event.key==='Escape')close();}
            document.addEventListener('keydown',keyDown);
            overlay.querySelectorAll('[data-pv-close]').forEach(b=>b.onclick=close);
            overlay.addEventListener('click',e=>{if(e.target===overlay)close();});
            const result=context.getNode()?.offlinePrevisArtifacts;
            if(result?.blend_url) form.querySelector('.pv-artifacts').innerHTML=`<a href="${escape(result.blend_url)}" download>下载可编辑工程</a>`;
            function apply(){
                if(!form.reportValidity())return false;
                const next=clone(spec);let duration=(next.frame_end-next.frame_start)/next.fps;
                for(const field of form.querySelectorAll('[data-pv-path]')){
                    const value=field.tagName==='SELECT'?field.value:Number(field.value);
                    if(typeof value==='number' && !Number.isFinite(value))throw Error('请输入有效数字');
                    if(field.dataset.pvPath==='duration')duration=value;else set(next,field.dataset.pvPath,value);
                }
                if(duration<1 || duration>600)throw Error('时长应在1至600秒之间');
                next.frame_end=next.frame_start+Math.round(duration*next.fps);
                if(next.camera.preset==='01_慢镜头感')next.camera.end=next.camera.start.slice();
                context.apply({previzOutput:'endpoints',previzOfflineSpec:next,previzLlmEnabled:false});
                return true;
            }
            form.onsubmit=e=>{e.preventDefault();try{if(apply())close();}catch(error){form.querySelector('.pv-error').textContent=error.message;}};
            form.querySelector('[data-pv-generate]').onclick=()=>{try{if(apply()){close();context.generate();}}catch(error){form.querySelector('.pv-error').textContent=error.message;}};
            document.body.appendChild(overlay);
            overlay.querySelector('select').focus();
        }catch(error){context.notify(error.message);}
    }
    function mount(context){
        const originalNode=context.getNode();
        const stillSelected=()=>originalNode && context.getNode()?.id===originalNode.id;
        document.querySelectorAll('.pv-plugin-entry').forEach(el=>el.remove());
        const head=document.querySelector('.composer-head-left');if(!head)return;
        const entry=document.createElement('div');entry.className='pv-plugin-entry';
        const endpoint=context.settings.previzOutput==='endpoints';
        entry.innerHTML=`<select aria-label="预演方式"><option value="endpoints" ${endpoint?'selected':''}>离线起落幅</option><option value="animation" ${!endpoint?'selected':''}>连续动画</option></select><button type="button" class="smart-pill" data-pv-config>起落幅设置</button>`;
        head.appendChild(entry);
        // 2026-10-23 老王：宿主 canvas-previz-controls 在调用 mount 之前，已经把 #runBtn
        // 挪进 .composer-actions。原来写死 `head.insertBefore(entry, runBtn)` 会因为
        // runBtn 不是 head 的子节点而抛 NotFoundError —— 预演入口直接出不来。
        // 只有运行键确实还在头部时才插到它前面，否则直接追加到头部末尾。
        const runBtn=document.getElementById('runBtn');
        if(runBtn && runBtn.parentElement===head) head.insertBefore(entry, runBtn);
        entry.querySelector('select').onchange=async e=>{
            try{
                const patch={previzOutput:e.target.value};
                if(patch.previzOutput==='endpoints' && !context.settings.previzOfflineSpec)patch.previzOfflineSpec=clone((await metadata()).default_spec);
                if(stillSelected()){context.apply(patch);update();}
            }catch(error){context.notify(error.message);}
        };
        entry.querySelector('[data-pv-config]').onclick=()=>open(context);
        function update(){
            const active=context.settings.previzOutput==='endpoints';
            entry.querySelector('[data-pv-config]').hidden=!active;
            const span=document.querySelector('#runBtn span');if(span)span.textContent=active?'生成起落幅':'生成预演';
        }
        update();
        if(endpoint && !context.settings.previzOfflineSpec)metadata().then(meta=>{if(stillSelected())context.apply({previzOfflineSpec:clone(meta.default_spec)});}).catch(error=>context.notify(error.message));
    }
    async function ensureSpec(settings){
        if(!settings.previzOfflineSpec)settings.previzOfflineSpec=clone((await metadata()).default_spec);
        return settings.previzOfflineSpec;
    }
    // 2026-10-23 老王：宿主（canvas-previz-controls）在切回普通引擎时会调
    // CanvasOfflinePrevis.unmount() 清理。此前本文件只导出 {mount,open,ensureSpec}，
    // unmount 缺失 → 宿主那行 `CanvasOfflinePrevis?.unmount()` 抛 TypeError，预演控件也留在页面上。
    function unmount(){
        document.querySelectorAll('.pv-plugin-entry').forEach(el=>el.remove());
        document.querySelectorAll('.pv-plugin-overlay').forEach(el=>el.remove());
        document.querySelectorAll('.pv-inline-composer').forEach(el=>el.classList.remove('pv-inline-composer'));
    }
    global.CanvasOfflinePrevis={mount,open,ensureSpec,unmount};
})(window);

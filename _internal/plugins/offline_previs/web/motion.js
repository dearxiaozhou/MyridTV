/* Named camera-animation presets. No camera coordinates in the product UI. */
(function(global){
 'use strict';
 let pendingMeta;
 const clone=v=>JSON.parse(JSON.stringify(v));
 const escape=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const framings=[['wide','大全景'],['full','全景'],['medium','中景'],['close','近景'],['detail','特写']];
 async function metadata(){
  if(!pendingMeta)pendingMeta=fetch('/api/plugins/offline-previs').then(r=>{if(!r.ok)throw Error('运镜插件未加载');return r.json();}).catch(e=>{pendingMeta=null;throw e;});
  return pendingMeta;
 }
 function options(items,value){return items.map(([id,label])=>`<option value="${escape(id)}" ${id===value?'selected':''}>${escape(label)}</option>`).join('');}
 function field(label,html){return `<label>${label}${html}</label>`;}
 async function ensureMotionSpec(settings){
  if(!settings.previzMotionSpec)settings.previzMotionSpec=clone((await metadata()).default_motion);
  return settings.previzMotionSpec;
 }
 async function open(context){
  try{
   const node=context.getNode();const meta=await metadata();
   if(!node || context.getNode()?.id!==node.id)throw Error('节点已切换，请重新打开运镜设置');
   const spec=clone(context.settings.previzMotionSpec || meta.default_motion);
   const overlay=document.createElement('div');overlay.className='pv-plugin-overlay';
   const grouped=primary=>meta.motion_presets.filter(p=>p.primary===primary).map(p=>[p.id,p.name]);
   const video=node.images?.find(item=>item.kind==='video')?.url || node.offlinePrevisArtifacts?.video_url;
   overlay.innerHTML=`<form class="pv-plugin-dialog pv-motion-dialog" aria-label="运镜动画设置">
    <header><div><h2>运镜动画</h2><p>选择预设，系统按景别和焦距自动取景。</p></div><button type="button" data-pv-close aria-label="关闭运镜设置">×</button></header>
    ${field('运镜预设',`<select name="preset"><optgroup label="常用运镜">${options(grouped(true),spec.preset)}</optgroup><optgroup label="更多动态预设">${options(grouped(false),spec.preset)}</optgroup></select>`)}
    <div class="pv-top-fields">${field('时长 / 秒',`<input name="duration" type="number" min="1" max="30" step=".5" value="${spec.duration}" required>`)}${field('起始景别',`<select name="framing">${options(framings,spec.framing)}</select>`)}${field('焦距 / mm',`<input name="lens_mm" type="number" min="18" max="135" step="1" value="${spec.lens_mm}" required>`)}</div>
    <div class="pv-top-fields"><label><span data-pv-amount-label>移动距离 / 米</span><input name="amount" type="number" min=".1" step=".1" placeholder="自动" value="${spec.amount??''}"></label>${field('主体',`<select name="subject">${options([['x_bot','X_Bot'],['y_bot','Y_Bot'],['both','双人']],spec.subject)}</select>`)}<label data-pv-direction>方向<select name="direction">${options([['left','向左'],['right','向右']],spec.direction)}</select></label></div>
    <p class="pv-note" data-pv-guidance>移动后结束景别由系统计算，不需要填写相机位置。</p>
    <details class="pv-actor pv-motion-more"><summary>更多：节奏与构图</summary><div class="pv-top-fields">${field('节奏',`<select name="pace">${options([['preset','预设默认'],['smooth','平稳起停'],['linear','匀速'],['accelerate','渐快'],['decelerate','渐慢']],spec.pace)}</select>`)}${field('构图',`<select name="composition">${options([['center','居中'],['left','左三分'],['right','右三分']],spec.composition)}</select>`)}</div><div data-pv-ending>${field('结束景别',`<select name="end_framing">${options([['auto','按移动距离自动变化'],...framings],spec.end_framing)}</select>`)}</div></details>
    ${video?`<details class="pv-motion-last"><summary>上一次预览</summary><video aria-label="上一次运镜动画" src="${escape(video)}" controls loop muted playsinline preload="metadata"></video></details>`:''}
    <p class="pv-error" role="alert"></p><footer><div class="pv-artifacts">${node.offlinePrevisArtifacts?.blend_url?`<a href="${escape(node.offlinePrevisArtifacts.blend_url)}" download>下载可编辑工程</a>`:''}</div><button type="button" data-pv-close>取消</button><button type="submit">保存设置</button><button type="button" class="primary" data-pv-generate>生成预览动画</button></footer></form>`;
   const form=overlay.querySelector('form');const input=name=>form.elements.namedItem(name);
   function describe(){
    const preset=meta.motion_presets.find(p=>p.id===input('preset').value);
    form.querySelector('[data-pv-amount-label]').textContent=preset.amount_type==='angle'?(preset.kind==='orbit'?'环绕角度 / 度':'转动角度 / 度'):(preset.kind==='follow'?'行进距离 / 米':preset.kind.startsWith('crane')?'升降距离 / 米':'移动距离 / 米');
    input('amount').step=preset.amount_type==='angle'?'5':'.1';
    form.querySelector('[data-pv-direction]').hidden=!preset.direction;
    const ending=['push','pull','dolly_zoom'].includes(preset.kind);
    form.querySelector('[data-pv-ending]').hidden=!ending;
    input('amount').disabled=ending && input('end_framing').value!=='auto';
    form.querySelector('[data-pv-guidance]').textContent=preset.kind==='follow'?'人物会使用现成行走动作实际前进，相机保持相对构图跟随。':preset.kind==='dolly_zoom'?'推进时自动反向变焦，保持主体大小并改变背景透视。':input('amount').disabled?'移动距离将按结束景别自动计算。':'幅度留空自动计算；修改景别或焦距，系统会重新匹配拍摄距离。';
   }
   input('preset').onchange=()=>{input('amount').value='';input('end_framing').value='auto';describe();};
   input('end_framing').onchange=describe;describe();
   function close(){overlay.remove();document.removeEventListener('keydown',keyDown);}
   function keyDown(e){if(e.key==='Escape')close();}
   overlay.querySelectorAll('[data-pv-close]').forEach(button=>button.onclick=close);
   overlay.addEventListener('click',e=>{if(e.target===overlay)close();});document.addEventListener('keydown',keyDown);
   function apply(){
    if(!form.reportValidity())return false;
    if(context.getNode()?.id!==node.id)throw Error('节点已切换，请重新打开设置');
    const result={...spec,schema_version:'motion/1.0'};
    for(const name of ['preset','framing','subject','direction','pace','composition','end_framing'])result[name]=input(name).value;
    for(const name of ['duration','lens_mm'])result[name]=Number(input(name).value);
    result.amount=input('amount').disabled || input('amount').value.trim()===''?null:Number(input('amount').value);
    const preset=meta.motion_presets.find(p=>p.id===result.preset);
    if(!['push','pull','dolly_zoom'].includes(preset.kind))result.end_framing='auto';
    context.apply({previzOutput:'motion',previzMotionSpec:result,previzLlmEnabled:false});return true;
   }
   form.onsubmit=e=>{e.preventDefault();try{if(apply())close();}catch(error){form.querySelector('.pv-error').textContent=error.message;}};
   form.querySelector('[data-pv-generate]').onclick=()=>{try{if(apply()){close();context.generate();}}catch(error){form.querySelector('.pv-error').textContent=error.message;}};
   document.body.appendChild(overlay);input('preset').focus();
  }catch(error){context.notify(error.message);}
 }
 function mount(context){
  document.querySelectorAll('.pv-plugin-entry').forEach(el=>el.remove());
  const head=document.querySelector('.composer-head-left');if(!head)return;
  const node=context.getNode();const stillSelected=()=>node && context.getNode()?.id===node.id;
  if(context.settings.previzOutput==='endpoints')context.apply({previzOutput:'motion'});
  const entry=document.createElement('div');entry.className='pv-plugin-entry';
  entry.innerHTML=`<select aria-label="预演方式"><option value="motion" ${context.settings.previzOutput==='motion'?'selected':''}>运镜动画</option><option value="animation" ${context.settings.previzOutput!=='motion'?'selected':''}>旧版预演</option></select><button type="button" class="smart-pill" data-pv-config>运镜设置</button>`;
  head.insertBefore(entry,document.getElementById('runBtn'));
  function update(){
   const active=context.settings.previzOutput==='motion';entry.querySelector('[data-pv-config]').hidden=!active;
   document.querySelectorAll('.blender-lens-item,.previz-llm-row').forEach(e=>e.style.display=active?'none':'');
   const span=document.querySelector('#runBtn span');if(span)span.textContent=active?'预览运镜':'生成预演';
  }
  entry.querySelector('select').onchange=async e=>{try{
   const patch={previzOutput:e.target.value};if(patch.previzOutput==='motion')patch.previzMotionSpec=await ensureMotionSpec(context.settings);
   if(stillSelected()){context.apply(patch);update();}
  }catch(error){context.notify(error.message);}};
  entry.querySelector('[data-pv-config]').onclick=()=>open(context);update();
  if(context.settings.previzOutput==='motion' && !context.settings.previzMotionSpec)metadata().then(meta=>{if(stillSelected())context.apply({previzMotionSpec:clone(meta.default_motion)});}).catch(e=>context.notify(e.message));
 }
 async function ensureSpec(settings){if(!settings.previzOfflineSpec)settings.previzOfflineSpec=clone((await metadata()).default_spec);return settings.previzOfflineSpec;}
 global.CanvasOfflinePrevis={mount,open,ensureMotionSpec,ensureSpec};
})(window);

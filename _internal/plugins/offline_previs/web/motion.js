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
   const spec={...clone(meta.default_motion),...clone(context.settings.previzMotionSpec||{})};
   let actions=clone(spec.actions||[]);
   if(!actions.length)actions=[{action:spec.preset.startsWith('08_')?'walk':'stand',duration:spec.duration,distance:spec.preset.startsWith('08_')?(spec.amount??spec.duration*1.35):0,direction:'forward'}];
   const overlay=document.createElement('div');overlay.className='pv-plugin-overlay';
   const grouped=primary=>meta.motion_presets.filter(p=>p.primary===primary).map(p=>[p.id,p.name]);
   const video=node.images?.find(item=>item.kind==='video')?.url || node.offlinePrevisArtifacts?.video_url;
   overlay.innerHTML=`<form class="pv-plugin-dialog pv-motion-dialog" aria-label="运镜动画设置">
    <header><div><h2>运镜动画</h2><p>选择预设，系统按景别和焦距自动取景。</p></div><button type="button" data-pv-close aria-label="关闭运镜设置">×</button></header>
    ${field('运镜预设',`<select name="preset"><optgroup label="常用运镜">${options(grouped(true),spec.preset)}</optgroup><optgroup label="更多动态预设">${options(grouped(false),spec.preset)}</optgroup></select>`)}
    <div class="pv-top-fields">${field('时长 / 秒',`<input name="duration" type="number" min="1" max="30" step=".5" value="${spec.duration}" required>`)}${field('起始景别',`<select name="framing">${options(framings,spec.framing)}</select>`)}${field('焦距 / mm',`<input name="lens_mm" type="number" min="18" max="135" step="1" value="${spec.lens_mm}" required>`)}</div>
    <div class="pv-top-fields"><label data-pv-amount><span data-pv-amount-label>移动距离 / 米</span><input name="amount" type="number" min=".1" step=".1" placeholder="自动" value="${spec.amount??''}"></label>${field('主体',`<select name="subject">${options([['x_bot','X_Bot'],['y_bot','Y_Bot'],['both','双人']],spec.subject)}</select>`)}<label data-pv-direction>方向<select name="direction">${options([['left','向左'],['right','向右']],spec.direction)}</select></label></div>
    <section><h3>拍哪里</h3><div class="pv-top-fields">${field('起镜拍摄部位',`<select name="target_start">${options([['auto','按景别自动'],['head','头部'],['chest','胸部'],['hips','腰胯'],['feet','脚部']],spec.target_start)}</select>`)}${field('结束拍摄部位',`<select name="target_end">${options([['same','保持起镜部位'],['auto','按景别自动'],['head','头部'],['chest','胸部'],['hips','腰胯'],['feet','脚部']],spec.target_end)}</select>`)}${field('拍摄方位',`<select name="view">${options([['front','正面'],['back','背面'],['left','左侧'],['right','右侧']],spec.view)}</select>`)}</div><div class="pv-top-fields">${field('瞄准方式',`<select name="target_motion">${options([['follow','跟随主体所选部位'],['fixed','固定在起止落点']],spec.target_motion)}</select>`)}${field('拍摄对象',`<select name="focus_subject">${options([['first','第一主体'],['second','第二主体（双人时）']],spec.focus_subject)}</select>`)}</div></section>
    <section><h3>主体动作 <span>与运镜自由组合</span></h3><div data-pv-actions></div><div class="pv-action-tools"><button type="button" data-pv-add>＋ 添加动作</button><button type="button" data-pv-combo>走 → 跑 → 停 → 坐下</button></div><p class="pv-note" data-pv-action-time></p><p class="pv-note">每段距离在该段时长内完成；前后左右以场景初始朝向为准。距离填 0 可原地走跑，剩余镜头时间保持最后状态。</p></section>
    <p class="pv-note" data-pv-guidance>移动后结束景别由系统计算，不需要填写相机位置。</p>
    <details class="pv-actor pv-motion-more"><summary>更多：节奏与构图</summary><div class="pv-top-fields">${field('机位移动参照',`<select name="travel_reference">${options([['subject','随主体一起移动'],['scene','在固定场景内运镜']],spec.travel_reference)}</select>`)}${field('节奏',`<select name="pace">${options([['preset','预设默认'],['smooth','平稳起停'],['linear','匀速'],['accelerate','渐快'],['decelerate','渐慢']],spec.pace)}</select>`)}${field('构图',`<select name="composition">${options([['center','居中'],['left','左三分'],['right','右三分']],spec.composition)}</select>`)}</div><div data-pv-ending>${field('结束景别',`<select name="end_framing">${options([['auto','按移动距离自动变化'],...framings],spec.end_framing)}</select>`)}</div></details>
    ${video?`<details class="pv-motion-last"><summary>上一次预览</summary><video aria-label="上一次运镜动画" src="${escape(video)}" controls loop muted playsinline preload="metadata"></video></details>`:''}
    <p class="pv-error" role="alert"></p><footer><div class="pv-artifacts">${node.offlinePrevisArtifacts?.blend_url?`<a href="${escape(node.offlinePrevisArtifacts.blend_url)}" download>下载可编辑工程</a>`:''}</div><button type="button" data-pv-close>取消</button><button type="submit">保存设置</button><button type="button" class="primary" data-pv-generate>生成预览动画</button></footer></form>`;
   const form=overlay.querySelector('form');const input=name=>form.elements.namedItem(name);
   const actionKinds=[['stand','站立'],['walk','走路'],['run','跑步'],['stop','停下'],['sit','坐下'],['stand_up','起身']];
   function actionTime(){const total=actions.reduce((sum,a)=>sum+Number(a.duration||0),0);form.querySelector('[data-pv-action-time]').textContent=`动作合计 ${+total.toFixed(2)} 秒 / 镜头 ${input('duration').value} 秒`;}
   function renderActions(){
    form.querySelector('[data-pv-actions]').innerHTML=actions.map((a,i)=>`<div class="pv-action-row" data-action-index="${i}"><label>动作 ${i+1}<select data-action-field="action">${options(actionKinds,a.action)}</select></label><label>时长 / 秒<input data-action-field="duration" type="number" min=".2" max="30" step=".1" value="${a.duration}" required></label><label>距离 / 米<input data-action-field="distance" type="number" min="0" max="50" step=".1" value="${a.distance}" ${['walk','run'].includes(a.action)?'':'disabled'} required></label><label>移动方向<select data-action-field="direction" ${['walk','run'].includes(a.action)?'':'disabled'}>${options([['forward','向前'],['backward','向后'],['left','向左'],['right','向右']],a.direction)}</select></label><button type="button" data-action-remove="${i}" aria-label="删除动作 ${i+1}">×</button></div>`).join('');
    form.querySelectorAll('[data-action-field]').forEach(el=>el.onchange=()=>{const a=actions[Number(el.closest('[data-action-index]').dataset.actionIndex)];const key=el.dataset.actionField;a[key]=['duration','distance'].includes(key)?Number(el.value):el.value;if(key==='action'){if(!['walk','run'].includes(a.action))a.distance=0;renderActions();}actionTime();});
    form.querySelectorAll('[data-action-remove]').forEach(el=>el.onclick=()=>{actions.splice(Number(el.dataset.actionRemove),1);renderActions();});actionTime();
   }
   form.querySelector('[data-pv-add]').onclick=()=>{if(actions.length<12){const left=Number(input('duration').value)-actions.reduce((sum,a)=>sum+a.duration,0);actions.push({action:'walk',duration:Math.max(.2,+left.toFixed(2)),distance:1,direction:'forward'});renderActions();}};
   form.querySelector('[data-pv-combo]').onclick=()=>{const duration=Math.max(4,Number(input('duration').value));input('duration').value=duration;actions=[{action:'walk',duration:+(duration*.25).toFixed(2),distance:1.5,direction:'forward'},{action:'run',duration:+(duration*.35).toFixed(2),distance:3,direction:'forward'},{action:'stop',duration:+(duration*.15).toFixed(2),distance:0,direction:'forward'},{action:'sit',duration:+(duration*.25).toFixed(2),distance:0,direction:'forward'}];renderActions();};
   input('duration').onchange=actionTime;renderActions();
   function describe(){
    const preset=meta.motion_presets.find(p=>p.id===input('preset').value);
    form.querySelector('[data-pv-amount-label]').textContent=preset.amount_type==='angle'?(preset.kind==='orbit'?'环绕角度 / 度':'转动角度 / 度'):(preset.kind==='follow'?'行进距离 / 米':preset.kind.startsWith('crane')?'升降距离 / 米':'移动距离 / 米');
    input('amount').step=preset.amount_type==='angle'?'5':'.1';input('amount').max=preset.kind==='orbit'?'360':preset.amount_type==='angle'?'180':'20';
    form.querySelector('[data-pv-amount]').hidden=preset.kind==='follow';
    form.querySelector('[data-pv-direction]').hidden=!preset.direction;
    const ending=['push','pull','dolly_zoom'].includes(preset.kind);
    form.querySelector('[data-pv-ending]').hidden=!ending;
    input('amount').disabled=preset.kind==='follow' || (ending && input('end_framing').value!=='auto');
    form.querySelector('[data-pv-guidance]').textContent=preset.kind==='follow'?'相机随主体位移；动作、距离和方向由下方动作组合控制。':preset.kind==='dolly_zoom'?'推进时自动反向变焦，保持主体大小并改变背景透视。':input('amount').disabled?'移动距离将按结束景别自动计算。':'幅度留空自动计算；修改景别或焦距，系统会重新匹配拍摄距离。';
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
    for(const name of ['preset','framing','subject','direction','pace','composition','end_framing','target_start','target_end','target_motion','view','focus_subject','travel_reference'])result[name]=input(name).value;
    for(const name of ['duration','lens_mm'])result[name]=Number(input(name).value);
    result.amount=input('amount').disabled || input('amount').value.trim()===''?null:Number(input('amount').value);
    const preset=meta.motion_presets.find(p=>p.id===result.preset);
    if(!['push','pull','dolly_zoom'].includes(preset.kind))result.end_framing='auto';
    if(actions.reduce((sum,a)=>sum+a.duration,0)>result.duration+.00001)throw Error('动作总时长超过镜头时长，请缩短动作或增加镜头时长');
    result.actions=clone(actions);
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

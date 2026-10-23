/* Named camera-animation presets. No camera coordinates in the product UI. */
(function(global){
 'use strict';
 let pendingMeta;
 let activeEditor=null,renderRevision=0;
 const clone=v=>JSON.parse(JSON.stringify(v));
 const escape=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const framings=[['wide','大全景'],['full','全景'],['medium','中景'],['close','近景'],['detail','特写']];
 async function metadata(){
  if(!pendingMeta)pendingMeta=fetch('/api/plugins/offline-previs').then(r=>{if(!r.ok)throw Error('运镜插件未加载');return r.json();}).catch(e=>{pendingMeta=null;throw e;});
  return pendingMeta;
 }
 function options(items,value){return items.map(([id,label])=>`<option value="${escape(id)}" ${id===value?'selected':''}>${escape(label)}</option>`).join('');}
 function field(label,html){return `<label>${label}${html}</label>`;}
 function parsePromptAssets(text,kinds){
  const source=String(text||'').trim(),catalog=new Map(kinds.map(k=>[k.id,k]));
  const project=source.match(/(?:场景工程|已有工程|工程)\s*[：:]\s*["“]?((?:[a-zA-Z]:[\\/]|\/assets\/)[^\r\n]*?\.blend)/i);
  if(project)return {scene_mode:'existing',scene_project:project[1].trim(),scene_assets:[]};
  const words=[['sofa',/长椅|沙发/],['table',/茶几|桌子|餐桌|办公桌|桌/],['chair',/椅子|椅/],['bed',/床/],['wall',/墙/],['door',/门洞|门框|门/],['tree',/树/],['car',/汽车|车辆|轿车|车/],['box',/箱子|盒子|立方体|箱|柜/]];
  const kindOf=value=>catalog.has(value)?value:(words.find(([,re])=>re.test(value))?.[0]||'box');
  const assets=[];let explicit=false,last=null;
  function locate(asset,text){
   if(/左/.test(text))asset.position[0]=-3;if(/右/.test(text))asset.position[0]=3;
   if(/后|背景/.test(text))asset.position[1]=-3;if(/前|前景/.test(text))asset.position[1]=3;
   if(/中间|中央|中心|正中/.test(text))asset.position=[0,0];
   const match=text.match(/([\d.]+)\s*[×xX*]\s*([\d.]+)\s*[×xX*]\s*([\d.]+)/);
   if(match){const values=match.slice(1).map(Number);if(values.some(v=>!Number.isFinite(v)||v<.05||v>50))throw Error('资产尺寸应在0.05至50米之间');asset.size=values;}
  }
  function add(name,kind,description=''){
   name=name.replace(/^[一二两三四五六七八九十\d]+\s*[个张把辆棵件]?/,'').trim();if(!name)return;
   if(assets.length>=32)throw Error('一镜最多提供32项场景资产');
   const def=catalog.get(kind)||catalog.get('box');const index=assets.length;
   const asset={name:name.slice(0,40),kind:def.id,size:clone(def.size),position:[Math.max(-6,Math.min(6,(index%5-2)*2)),-3],facing:'forward',model:''};
   locate(asset,description);assets.push(asset);last=asset;
  }
  for(const raw of source.split(/\r?\n/)){
   const line=raw.trim();
   const table=line.match(/^资产\s*\|\s*(.+)$/);
   if(table){
    explicit=true;const parts=table[1].split('|').map(v=>v.trim());if(parts.length<2)throw Error('资产行请写名称和类别');add(parts[0],kindOf(parts[1]),parts.slice(4).join(' '));
    const pos=(parts[2]||'').match(/-?\d+(?:\.\d+)?/g),size=(parts[3]||'').match(/\d+(?:\.\d+)?/g);
    if(pos?.length>=2)last.position=pos.slice(0,2).map(Number);if(size?.length>=3)last.size=size.slice(0,3).map(Number);continue;
   }
   const model=line.match(/^(?:模型|资产模型)\s*[：:]\s*["“]?((?:[a-zA-Z]:[\\/]|\/assets\/)[^\r\n]*?\.(?:blend|fbx|obj|glb|gltf))/i);
   if(model){explicit=true;if(!last)add('提供的模型','box');last.model=model[1].trim();continue;}
   const match=line.match(/^(?:场景资产|资产)\s*[：:]\s*(.*)$/);if(!match)continue;
   explicit=true;
   for(const clause of match[1].split(/[；;、，,]/).map(v=>v.trim()).filter(Boolean)){
    if(/^(?:不需要|不要|没有|无)/.test(clause))continue;
    if(last&&!words.some(([,re])=>re.test(clause))&&/^(?:在|放|摆|位于|左|右|前|后|中|\d)/.test(clause)){locate(last,clause);continue;}
    const kind=kindOf(clause),name=clause.split(/放在|位于|摆在|位置|放|在/)[0].trim()||clause;
    const countMatch=clause.match(/^([一二两三四五六七八]|[1-8])\s*[个张把辆棵件]/),counts={一:1,二:2,两:2,三:3,四:4,五:5,六:6,七:7,八:8};const count=countMatch?(counts[countMatch[1]]||Number(countMatch[1])):1;
    for(let i=0;i<count;i++)add(name+(count>1?' '+(i+1):''),kind,clause);
   }
  }
  if(!explicit){
   for(const [kind,re] of words){const match=source.match(re);if(match&&!/(?:不要|不需要|不需|没有|无需|别放)\s*$/.test(source.slice(Math.max(0,match.index-5),match.index)))add(match[0],kind);}
  }
  if(assets.some(a=>a.position.some(v=>!Number.isFinite(v)||Math.abs(v)>8)||a.size.some(v=>!Number.isFinite(v)||v<.05||v>50)))throw Error('资产位置或尺寸超出可用范围');
  return assets.length?{scene_mode:'new',scene_project:'',scene_assets:assets}:null;
 }
 async function ensureMotionSpec(settings){
  if(!settings.previzMotionSpec)settings.previzMotionSpec=clone((await metadata()).default_motion);
  return settings.previzMotionSpec;
 }
 async function buildInline(context){
  const revision=++renderRevision;
  try{
   const node=context.getNode();const meta=await metadata();
   if(!node||context.getNode()?.id!==node.id||revision!==renderRevision)return;
   const spec={...clone(meta.default_motion),...clone(context.settings.previzMotionDraft||context.settings.previzMotionSpec||{})};
   let actions=clone(spec.actions||[]);
   if(!actions.length)actions=[{action:spec.preset.startsWith('08_')?'walk':'stand',duration:spec.duration,distance:spec.preset.startsWith('08_')?(spec.amount??spec.duration*1.35):0,direction:'forward'}];
   let characters=clone(spec.characters|| (spec.subject==='both'?[{id:'subject_1',name:'人物1',asset:'x_bot',position:[-.75,0],facing:'forward',motion:'sequence'},{id:'subject_2',name:'人物2',asset:'y_bot',position:[.75,0],facing:'forward',motion:'sequence'}]:[{id:'subject_1',name:'主角',asset:spec.subject,position:[0,0],facing:'forward',motion:'sequence'}]));
   let assetsEnabled=spec.assets_enabled??spec.scene_mode!=='none';
   let sceneMemory=clone(spec.scene_memory||(spec.scene_mode!=='none'?{scene_mode:spec.scene_mode,scene_project:spec.scene_project,scene_assets:spec.scene_assets||[]}:null));
   let assetPromptKey=spec.asset_prompt??null,sceneParseError='';
   let sceneAssets=sceneMemory?.scene_assets||[];
   const host=document.createElement('div');
   const ratios=[['wide','16:9'],['story','9:16'],['square','1:1'],['portrait43','3:4'],['landscape43','4:3'],['ultrawide','21:9'],['ultratall','9:21']];
   const grouped=primary=>meta.motion_presets.filter(p=>p.primary===primary).map(p=>[p.id,p.name]);
   host.innerHTML=`<form class="pv-plugin-dialog pv-motion-dialog pv-inline-panel" aria-label="预演参数">
    <div class="pv-inline-top" aria-label="预演基础设置">
     <label class="pv-top-control" title="比例"><select name="ratio" aria-label="比例">${options(ratios,context.settings.ratio||'wide')}</select></label>
     <label class="pv-top-control" title="时长"><input name="duration" type="number" aria-label="时长" min="1" max="30" step=".1" value="${spec.duration}" required><small>秒</small></label>
     <label class="pv-top-control" title="运镜"><select name="preset" aria-label="运镜"><optgroup label="常用">${options(grouped(true),spec.preset)}</optgroup><optgroup label="更多">${options(grouped(false),spec.preset)}</optgroup></select></label>
     <label class="pv-top-control" title="焦距"><input name="lens_mm" type="number" aria-label="焦距" min="18" max="135" step="1" value="${spec.lens_mm}" required><small>mm</small></label>
    <label class="pv-top-control" title="相机高度 / 米"><input name="camera_height" aria-label="相机高度 / 米" type="number" min=".05" max="30" step=".05" placeholder="高度自动" value="${spec.camera_height??''}"><small>米</small></label><button type="button" class="pv-assets-toggle" data-pv-assets-toggle aria-pressed="${assetsEnabled}" title="开启后在提示词中描述资产或填写工程路径">资产${assetsEnabled?'开':'关'}</button></div><input type="hidden" name="subject" value="${spec.subject}">
    <p class="pv-note pv-legacy-note" ${context.settings.previzOutput==='motion'?'hidden':''}>此节点保留原文本镜头；调整参数后使用运镜预设。</p>
    <div class="pv-shoot-grid pv-inline-shot-grid">${field('景别',`<select name="framing">${options(framings,spec.framing)}</select>`)}<label data-pv-amount><span data-pv-amount-label>移动 / 米</span><input name="amount" type="number" min=".1" step=".1" placeholder="自动" value="${spec.amount??''}"></label><label data-pv-focus-label>拍谁<select name="focus_subject">${options([...characters.map(p=>[p.id,p.name]),['group','多人整体']],spec.focus_subject==='first'?characters[0].id:spec.focus_subject==='second'?characters[Math.min(1,characters.length-1)].id:spec.focus_subject)}</select></label>${field('拍哪里',`<select name="target_start">${options([['auto','自动取景'],['head','头部'],['chest','胸部'],['hips','腰胯'],['feet','脚部']],spec.target_start)}</select>`)}${field('方位',`<select name="view">${options([['front','正面'],['back','背面'],['left','左侧'],['right','右侧']],spec.view)}</select>`)}${field('角度',`<select name="camera_angle">${options([['auto','自动'],['eye','平视'],['low','仰拍'],['high','俯拍'],['overhead','鸟瞰']],spec.camera_angle)}</select>`)}${field('结束拍哪里',`<select name="target_end">${options([['same','同起镜'],['auto','自动取景'],['head','头部'],['chest','胸部'],['hips','腰胯'],['feet','脚部']],spec.target_end)}</select>`)}<label data-pv-direction>运镜方向<select name="direction">${options([['left','向左'],['right','向右']],spec.direction)}</select></label></div><p class="pv-note pv-assets-hint" ${assetsEnabled?'':'hidden'}>在提示词写“资产：长椅，左后方；茶几，右侧”，或“工程：本地 .blend 路径”。</p>
    <section class="pv-actions-section"><div data-pv-actions></div><div class="pv-action-tools"><button type="button" data-pv-add>＋ 接一段动作</button><button type="button" data-pv-combo>走 → 跑 → 停 → 坐下</button></div><p class="pv-note" data-pv-action-time></p></section>
    <details class="pv-actor pv-blocking"><summary>人物站位 <span data-pv-blocking-count></span></summary>
     <div class="pv-layout-tools"><button type="button" data-pv-layout="dialogue">双人对话</button><button type="button" data-pv-layout="confront">三人对峙</button><button type="button" data-pv-layout="bystanders">主角＋旁观者</button></div>
     <svg class="pv-floorplan" viewBox="-8 -8 16 16" role="group" aria-label="俯视站位图，拖动人物或资产调整位置"><rect x="-8" y="-8" width="16" height="16" fill="var(--x-soft)"/><g data-pv-map></g></svg><p class="pv-note">俯视图：上方为前，拖动色点摆人物，拖动方块摆资产。选中后也可用方向键微调。</p>
     <div data-pv-people></div><button type="button" data-pv-person-add>＋ 添加人物</button>
    </details>
    
    <p class="pv-error" role="status" aria-live="polite"></p><div class="pv-artifacts" data-pv-artifacts></div></form>`;
   const form=host.querySelector('form');form.id='pv-inline-'+node.id.replace(/[^a-z0-9_-]/gi,'');
   const top=form.querySelector('.pv-inline-top');
   const assetsToggle=top.querySelector('[data-pv-assets-toggle]');
   // Let the scrollable panel own wheel gestures instead of the canvas zoom handler.
   if(typeof CanvasOverlayRegistry!=='undefined')CanvasOverlayRegistry.register('.pv-inline-panel',['wheel-scrollable']);
   const input=name=>form.elements.namedItem(name);
   let initializing=true;
   const facingOptions=[['forward','朝前'],['backward','朝后'],['left','朝左'],['right','朝右']];
   const palette=['#296693','#b85c2e','#61924d','#8c59a6','#ad9238','#409996','#a64d6e','#787d8f'];
   function updateMap(){
    const assets=assetsEnabled?sceneAssets:[];
    const map=form.querySelector('[data-pv-map]');
    map.innerHTML=`<path d="M-8 0H8M0-8V8" stroke="var(--x-line)" stroke-width=".035"/><text x="0" y="-7.5" text-anchor="middle" fill="var(--x-text)" font-size=".55">前 ↑</text>`+assets.map((a,i)=>`<g data-map-asset="${i}" role="button" tabindex="0" aria-label="摆放资产 ${escape(a.name||'未命名')}"><rect x="${a.position[0]-a.size[0]/2}" y="${-a.position[1]-a.size[1]/2}" width="${a.size[0]}" height="${a.size[1]}" transform="rotate(${{forward:0,backward:180,left:-90,right:90}[a.facing||'forward']} ${a.position[0]} ${-a.position[1]})" fill="var(--x-line)" stroke="var(--x-muted)" stroke-width=".04"/><text x="${a.position[0]}" y="${-a.position[1]}" font-size=".55" text-anchor="middle" fill="var(--x-text)">${escape(a.name||'资产')}</text></g>`).join('')+characters.map((p,i)=>`<g data-map-person="${i}" transform="translate(${p.position[0]},${-p.position[1]})" role="button" tabindex="0" aria-label="摆放人物 ${escape(p.name)}"><circle r=".45" fill="${palette[i]}" stroke="var(--x-text)" stroke-width=".035"/><path d="M0-.65L-.16-.38H.16Z" fill="${palette[i]}" transform="rotate(${{forward:0,backward:180,left:-90,right:90}[p.facing]})"/><text y=".85" font-size=".55" text-anchor="middle" fill="var(--x-text)">${escape(p.name)}</text></g>`).join('');
    form.querySelector('[data-pv-blocking-count]').textContent=`${characters.length} 人`;form.querySelector('[data-pv-focus-label]').hidden=characters.length===1;
   }
   function focusOptions(){const value=input('focus_subject').value;input('focus_subject').innerHTML=options([...characters.map(p=>[p.id,p.name]),['group','多人整体']],characters.some(p=>p.id===value)||value==='group'?value:spec.focus_subject==='second'?characters[Math.min(1,characters.length-1)].id:characters[0].id);}
   function renderPeople(){
    form.querySelector('[data-pv-people]').innerHTML=characters.map((p,i)=>`<div class="pv-person-row" data-person-index="${i}"><label>人物<input data-person-field="name" maxlength="24" value="${escape(p.name)}" required></label><label>模型<select data-person-field="asset">${options([['x_bot','X_Bot'],['y_bot','Y_Bot']],p.asset)}</select></label><label>行为<select data-person-field="motion">${options([['sequence','执行下方动作'],['stand','静态站立'],['sit','静态坐姿']],p.motion)}</select></label><label>朝向<select data-person-field="facing">${options(facingOptions,p.facing)}</select></label><button type="button" data-person-remove="${i}" ${characters.length===1?'disabled':''} aria-label="删除人物 ${escape(p.name)}">×</button></div>`).join('');
    form.querySelectorAll('[data-person-field]').forEach(el=>el.onchange=()=>{characters[Number(el.closest('[data-person-index]').dataset.personIndex)][el.dataset.personField]=el.value;focusOptions();updateMap();});
    form.querySelectorAll('[data-person-field="name"]').forEach(el=>el.oninput=el.onchange);
    form.querySelectorAll('[data-person-remove]').forEach(el=>el.onclick=()=>{characters.splice(Number(el.dataset.personRemove),1);renderPeople();});
    focusOptions();updateMap();
   }
   form.querySelector('[data-pv-person-add]').onclick=()=>{if(characters.length>=8)return;let id=1;while(characters.some(p=>p.id==='person_'+id))id++;characters.push({id:'person_'+id,name:'人物'+(characters.length+1),asset:characters.length%2?'y_bot':'x_bot',position:[Math.min(6,characters.length*1.1),0],facing:'forward',motion:'stand'});renderPeople();};
   form.querySelectorAll('[data-pv-layout]').forEach(button=>button.onclick=()=>{const layout=button.dataset.pvLayout;const positions=layout==='dialogue'?[[-1,0],[1,0]]:layout==='confront'?[[0,1],[-1.5,-1],[1.5,-1]]:[[0,0],[-2,-1.5],[2,-1.5]];characters=positions.map((position,i)=>({id:'subject_'+(i+1),name:i===0?'主角':'配角'+i,asset:i%2?'y_bot':'x_bot',position,facing:layout==='dialogue'?(i===0?'right':'left'):i===0?'backward':'forward',motion:i===0?'sequence':'stand'}));renderPeople();});
   function resolveScene(){
    if(!assetsEnabled)return {scene_mode:'none',scene_project:'',scene_assets:[]};
    const prompt=String(context.prompt?.innerText||'').trim();
    if(prompt!==assetPromptKey){
     try{const parsed=parsePromptAssets(prompt,meta.asset_kinds);sceneParseError='';if(parsed)sceneMemory=parsed;else if(/(?:资产|场景资产)\s*[：:|]/.test(prompt))sceneMemory=null;}catch(error){sceneParseError=error.message;sceneMemory=null;}
     assetPromptKey=prompt;sceneAssets=sceneMemory?.scene_assets||[];updateMap();
    }
    return sceneMemory||{scene_mode:'new',scene_project:'',scene_assets:[]};
   }
   assetsToggle.onclick=()=>{
    assetsEnabled=!assetsEnabled;const button=assetsToggle;button.setAttribute('aria-pressed',String(assetsEnabled));button.textContent='资产'+(assetsEnabled?'开':'关');form.querySelector('.pv-assets-hint').hidden=!assetsEnabled;resolveScene();updateMap();commit();
   };
   const svg=form.querySelector('.pv-floorplan');let drag=null;
   function movePoint(event){const point=svg.createSVGPoint();point.x=event.clientX;point.y=event.clientY;const local=point.matrixTransform(svg.getScreenCTM().inverse());drag.position=[+Math.max(-7.5,Math.min(7.5,local.x)).toFixed(2),+Math.max(-7.5,Math.min(7.5,-local.y)).toFixed(2)];updateMap();}
   svg.onpointerdown=event=>{const person=event.target.closest('[data-map-person]');const asset=event.target.closest('[data-map-asset]');if(!person&&!asset)return;drag=person?characters[Number(person.dataset.mapPerson)]:sceneAssets[Number(asset.dataset.mapAsset)];svg.setPointerCapture(event.pointerId);event.preventDefault();movePoint(event);};svg.onpointermove=event=>{if(drag)movePoint(event);};svg.onpointerup=()=>{drag=null;commit();};svg.onpointercancel=()=>drag=null;
   svg.onkeydown=event=>{const p=event.target.closest('[data-map-person]'),a=event.target.closest('[data-map-asset]');const item=p?characters[Number(p.dataset.mapPerson)]:a?sceneAssets[Number(a.dataset.mapAsset)]:null;if(!item||!['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(event.key))return;event.preventDefault();item.position[0]=Math.max(-7.5,Math.min(7.5,item.position[0]+(event.key==='ArrowLeft'?-.1:event.key==='ArrowRight'?.1:0)));item.position[1]=Math.max(-7.5,Math.min(7.5,item.position[1]+(event.key==='ArrowDown'?-.1:event.key==='ArrowUp'?.1:0)));const selector=p?`[data-map-person="${p.dataset.mapPerson}"]`:`[data-map-asset="${a.dataset.mapAsset}"]`;updateMap();svg.querySelector(selector)?.focus();commit();};
   renderPeople();resolveScene();
   input('camera_angle').onchange=()=>input('camera_height').value='';
   const actionKinds=[['stand','站立'],['walk','走路'],['run','跑步'],['stop','停下'],['sit','坐下'],['stand_up','起身']];
   function actionTime(){if(actions.length===1){actions[0].duration=Number(input('duration').value);const single=form.querySelector('[data-action-field="duration"]');if(single)single.value=actions[0].duration;}const total=actions.reduce((sum,a)=>sum+Number(a.duration||0),0);form.querySelector('[data-pv-action-time]').textContent=actions.length>1?`共 ${+total.toFixed(2)} 秒 / 镜头 ${input('duration').value} 秒`:['walk','run'].includes(actions[0]?.action)?'在镜头时长内走完所填距离':'';}
   function renderActions(){
    form.querySelector('[data-pv-actions]').innerHTML=actions.map((a,i)=>`<div class="pv-action-row ${actions.length===1?'pv-action-single':''}" data-action-index="${i}"><label>${actions.length===1?'人物动作':'动作 '+(i+1)}<select data-action-field="action">${options(actionKinds,a.action)}</select></label><label ${actions.length===1?'hidden':''}>时长 / 秒<input data-action-field="duration" type="number" min=".2" max="30" step=".01" value="${a.duration}" required></label><label ${['walk','run'].includes(a.action)?'':'hidden'}>距离 / 米<input data-action-field="distance" type="number" min="0" max="50" step=".1" value="${a.distance}" ${['walk','run'].includes(a.action)?'':'disabled'} required></label><label ${['walk','run'].includes(a.action)?'':'hidden'}>方向<select data-action-field="direction" ${['walk','run'].includes(a.action)?'':'disabled'}>${options([['forward','向前'],['backward','向后'],['left','向左'],['right','向右']],a.direction)}</select></label><button type="button" ${actions.length===1?'hidden':''} data-action-remove="${i}" aria-label="删除动作 ${i+1}">×</button></div>`).join('');
    form.querySelectorAll('[data-action-field]').forEach(el=>el.onchange=()=>{const a=actions[Number(el.closest('[data-action-index]').dataset.actionIndex)];const key=el.dataset.actionField;a[key]=['duration','distance'].includes(key)?Number(el.value):el.value;if(key==='action'){if(!['walk','run'].includes(a.action))a.distance=0;renderActions();}actionTime();});
    form.querySelectorAll('input[data-action-field]').forEach(el=>el.oninput=el.onchange);
    form.querySelectorAll('[data-action-remove]').forEach(el=>el.onclick=()=>{actions.splice(Number(el.dataset.actionRemove),1);if(!actions.length)actions=[{action:'stand',duration:Number(input('duration').value),distance:0,direction:'forward'}];renderActions();});actionTime();
   }
   form.querySelector('[data-pv-add]').onclick=()=>{if(actions.length<12){let left=Number(input('duration').value)-actions.reduce((sum,a)=>sum+a.duration,0);if(left<.2&&actions.at(-1).duration>=.4){left=+(actions.at(-1).duration/2).toFixed(2);actions.at(-1).duration-=left;}actions.push({action:'walk',duration:Math.max(.2,+left.toFixed(2)),distance:1,direction:'forward'});renderActions();}};
   form.querySelector('[data-pv-combo]').onclick=()=>{const duration=Math.max(4,Number(input('duration').value));input('duration').value=duration;actions=[{action:'walk',duration:+(duration*.25).toFixed(2),distance:1.5,direction:'forward'},{action:'run',duration:+(duration*.35).toFixed(2),distance:3,direction:'forward'},{action:'stop',duration:+(duration*.15).toFixed(2),distance:0,direction:'forward'},{action:'sit',duration:+(duration*.25).toFixed(2),distance:0,direction:'forward'}];actions[3].duration=+(duration-actions.slice(0,3).reduce((sum,a)=>sum+a.duration,0)).toFixed(2);renderActions();};
   input('duration').oninput=input('duration').onchange=actionTime;renderActions();
   function describe(){
    const preset=meta.motion_presets.find(p=>p.id===input('preset').value);
    form.querySelector('[data-pv-amount-label]').textContent=preset.amount_type==='angle'?(preset.kind==='orbit'?'环绕角度 / 度':'转动角度 / 度'):(preset.kind==='follow'?'行进距离 / 米':preset.kind.startsWith('crane')?'升降距离 / 米':'移动距离 / 米');
    input('amount').min=preset.amount_type==='angle'?'0':'.1';input('amount').step=preset.amount_type==='angle'?'5':'.1';input('amount').max=preset.kind==='orbit'?'360':preset.amount_type==='angle'?'180':'20';
    form.querySelector('[data-pv-amount]').hidden=preset.kind==='follow';
    form.querySelector('[data-pv-direction]').hidden=!preset.direction;
    input('amount').disabled=preset.kind==='follow';
   }
   input('preset').onchange=()=>{input('amount').value='';describe();};describe();
   function snapshot(){
    if(context.getNode()?.id!==node.id)return null;
    const result={...spec,schema_version:'motion/1.0'};
    for(const name of ['preset','framing','subject','direction','target_start','target_end','view','focus_subject','camera_angle'])result[name]=input(name).value;
    for(const name of ['duration','lens_mm'])result[name]=Number(input(name).value);
    result.amount=input('amount').disabled || input('amount').value.trim()===''?null:Number(input('amount').value);
    const preset=meta.motion_presets.find(p=>p.id===result.preset);
    Object.assign(result,{end_framing:'auto',pace:'preset',composition:'center',target_motion:'follow',travel_reference:'subject'});
    Object.assign(result,resolveScene());result.assets_enabled=assetsEnabled;result.scene_memory=sceneMemory;result.asset_prompt=assetPromptKey;
    result.actions=clone(actions);result.characters=clone(characters);result.scene_assets=result.scene_mode==='new'?clone(sceneAssets):[];result.camera_height=input('camera_height').value.trim()===''?null:Number(input('camera_height').value);

    return result;
   }
   function validate(result){
    if(assetsEnabled&&sceneParseError)return sceneParseError;
    if(!form.checkValidity()){
     const bad=[...form.elements].find(el=>el.willValidate&&!el.validity.valid);
     return bad?.validationMessage||'请补全预演设置';
    }
    if(actions.reduce((sum,a)=>sum+a.duration,0)>result.duration+.00001)return '动作总时长超过镜头时长，请缩短动作或增加时长';
    if(result.scene_mode==='existing'&&!result.scene_project.trim())return '请提供已有Blender工程路径';
    if(result.scene_mode==='new'&&!sceneAssets.length)return '资产已开启，请在提示词中提供资产名称或已有工程路径';
    let previous='stand';
    for(const action of actions){
     if(action.action==='stand_up'&&previous!=='sit')return '起身前请先添加坐下动作';
     if(previous==='sit'&&!['sit','stop','stand_up'].includes(action.action))return '坐下后请先起身再走跑';
     if(action.action!=='stop')previous=action.action;
    }
    return '';
   }
   function commit(strict=false){
    if(initializing||context.getNode()?.id!==node.id)return false;
    const result=snapshot();if(!result)return false;
    const error=validate(result);form.querySelector('.pv-error').textContent=error;form.dataset.invalid=error?'true':'false';
    context.apply({ratio:input('ratio').value,previzOutput:'motion',previzMotionSpec:result,previzMotionDraft:result,previzMotionError:error,previzLlmEnabled:false});
    form.querySelector('.pv-legacy-note').hidden=true;
    if(error&&strict){context.notify(error);form.querySelector('.pv-error').scrollIntoView({block:'nearest'});}
    return !error;
   }
   function artifacts(){
    const blend=context.getNode()?.offlinePrevisArtifacts?.blend_url;
    form.querySelector('[data-pv-artifacts]').innerHTML=blend?`<a href="${escape(blend)}" download>可编辑工程 ↗</a>`:'';

   }
   for(const el of top.querySelectorAll('input,select'))el.setAttribute('form',form.id);
   context.container.appendChild(form);context.head.prepend(top);context.composer.classList.add('pv-inline-composer');
   form.onsubmit=event=>event.preventDefault();
   for(const target of [form,top]){
    target.addEventListener('input',()=>commit());target.addEventListener('change',()=>commit());
    target.addEventListener('click',event=>{if(event.target.closest('button[data-pv-add],button[data-pv-combo],button[data-pv-layout],button[data-pv-person-add],button[data-person-remove],button[data-asset-remove],button[data-pv-asset-add],button[data-pv-reuse-scene]'))commit();});
   }
   const promptListener=()=>{if(context.settings.previzOutput==='motion'||assetsEnabled)commit();};context.prompt?.addEventListener('input',promptListener);
   form.addEventListener('toggle',()=>context.layout?.(),true);
   const observer=typeof ResizeObserver!=='undefined'?new ResizeObserver(()=>context.layout?.()):null;observer?.observe(form);
   activeEditor={nodeId:node.id,root:form,top,commit,refresh(next){context=next;artifacts();},dispose(){observer?.disconnect();context.prompt?.removeEventListener('input',promptListener);form.remove();top.remove();}};
   initializing=false;artifacts();context.layout?.();
   if(context.settings.previzMotionError)form.querySelector('.pv-error').textContent=context.settings.previzMotionError;
  }catch(error){if(revision===renderRevision){context.notify(error.message);if(context.container)context.container.textContent='预演设置未能加载：'+error.message;}}
 }
 function unmount(){renderRevision++;activeEditor?.dispose();activeEditor=null;document.querySelectorAll('.pv-inline-composer').forEach(el=>el.classList.remove('pv-inline-composer'));}
 function mount(context){
  const node=context.getNode();if(!node)return unmount();
  if(activeEditor?.nodeId===node.id&&activeEditor.root.isConnected){activeEditor.refresh(context);return;}
  unmount();if(!context.container||!context.head)return;
  context.container.replaceChildren();buildInline(context);
 }
 async function prepare(node){
  if(activeEditor?.nodeId===node.id&&activeEditor.root.isConnected)return activeEditor.commit(true);
  const settings=node.runSettings||{};
  if(settings.previzMotionError)throw Error(settings.previzMotionError);
  await ensureMotionSpec(settings);return true;
 }

 async function ensureSpec(settings){if(!settings.previzOfflineSpec)settings.previzOfflineSpec=clone((await metadata()).default_spec);return settings.previzOfflineSpec;}
 global.CanvasOfflinePrevis={mount,open:mount,unmount,prepare,parsePromptAssets,ensureMotionSpec,ensureSpec};
})(window);

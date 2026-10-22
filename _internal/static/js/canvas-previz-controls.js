/* Canvas host seam for the independent, inline offline-previs editor. */
(function(global){
 'use strict';
 const deps={getContext:null};
 function configure(patch){Object.assign(deps,patch||{});}
 function renderBlenderControls(){
  const context=deps.getContext?deps.getContext():{};
  if(!context.settings||context.settings.engine!=='blender'){
   global.CanvasOfflinePrevis?.unmount();
   return false;
  }
  const document=global.document;
  document.querySelectorAll('.blender-ratio-item,.blender-asset-item,.blender-lens-item,.blender-engine-label,.previz-llm-row,.pv-plugin-entry').forEach(el=>el.remove());
  const toggle=document.getElementById('apiKindToggle');if(toggle)toggle.style.display='none';
  if(context.composerStyleModeSlot)context.composerStyleModeSlot.innerHTML='';
  const composer=document.getElementById('composer');composer?.classList.add('pv-inline-composer');
  const actions=document.querySelector('.composer-actions'),run=document.getElementById('runBtn');
  if(actions){actions.style.removeProperty('display');if(run&&run.parentElement!==actions)actions.appendChild(run);}
  if(run){for(const key of ['width','minWidth','height','marginLeft','fontSize','gap','borderRadius','justifyContent'])run.style[key]='';const span=run.querySelector('span');if(span)span.textContent='生成预演';}
  const cascade=document.getElementById('cascadeRunBtn');if(cascade)cascade.style.display='none';
  if(typeof context.syncEngineSelectOptions==='function')context.syncEngineSelectOptions();
  if(global.CanvasOfflinePrevis)global.CanvasOfflinePrevis.mount({settings:context.settings,getNode:context.getNode,apply:context.applyOfflinePatch,notify:context.notify,layout:context.layoutOffline,
    prompt:context.promptInput,container:context.dynamicParams,head:document.querySelector('.composer-head-left'),composer});
  return true;
 }
 global.CanvasPrevizControls={configure,renderBlenderControls};
})(typeof window!=='undefined'?window:globalThis);

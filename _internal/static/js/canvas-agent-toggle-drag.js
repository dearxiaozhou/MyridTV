//** Agent toggle pill: clamped positioning, localStorage edge-format persistence, pointer-drag install. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    function D(name){return typeof deps[name] === 'function' ? deps[name]() : deps[name];}

function clampCanvasAgentTogglePosition(pos={}){
 const rect = D("canvasAgentToggle")?.getBoundingClientRect?.();
 const w = rect?.width || 40;
 const h = rect?.height || 40;
 const pad = 16;
 const maxLeft = Math.max(pad, window.innerWidth - w - pad);
 const maxTop = Math.max(pad, window.innerHeight - h - pad);
 const fallbackLeft = maxLeft;
 const fallbackTop = Math.min(Math.max((window.innerHeight - h) / 2, pad), maxTop);
 return {
  left: Math.min(Math.max(Number(pos.left ?? fallbackLeft), pad), maxLeft),
  top: Math.min(Math.max(Number(pos.top ?? fallbackTop), pad), maxTop)
 };
}
function canvasAgentTogglePositionFromStored(pos={}){
 const rect = D("canvasAgentToggle")?.getBoundingClientRect?.();
 const w = rect?.width || 40;
 const h = rect?.height || 40;
 if(pos && (pos.edge === 'left' || pos.edge === 'right')){
  const offset = Math.max(0, Number(pos.edgeOffset ?? 16));
  const topSpan = Math.max(1, window.innerHeight - h);
  return clampCanvasAgentTogglePosition({
   left: pos.edge === 'left' ? offset : window.innerWidth - w - offset,
   top: Number(pos.topRatio ?? .5) * topSpan
  });
 }
 return clampCanvasAgentTogglePosition(pos);
}
function storedCanvasAgentTogglePosition(pos={}){
 const rect = D("canvasAgentToggle")?.getBoundingClientRect?.();
 const w = rect?.width || 40;
 const h = rect?.height || 40;
 const next = clampCanvasAgentTogglePosition(pos);
 const edge = next.left + w / 2 < window.innerWidth / 2 ? 'left' : 'right';
 const edgeOffset = edge === 'left' ? next.left : Math.max(0, window.innerWidth - next.left - w);
 const topRatio = Math.min(Math.max(next.top / Math.max(1, window.innerHeight - h), 0), 1);
 return {
  edge,
  edgeOffset: Math.round(edgeOffset),
  topRatio:Number(topRatio.toFixed(4)),
  left:Math.round(next.left),
  top:Math.round(next.top)
 };
}
function applyCanvasAgentTogglePosition(pos={}, persist=false){
 if(!D("canvasAgentToggle")) return;
 const next = canvasAgentTogglePositionFromStored(pos);
 D("canvasAgentToggle").style.left = `${Math.round(next.left)}px`;
 D("canvasAgentToggle").style.top = `${Math.round(next.top)}px`;
 D("canvasAgentToggle").style.right = 'auto';
 D("canvasAgentToggle").style.bottom = 'auto';
 D("canvasAgentToggle").style.transform = '';
 if(persist){
  try { localStorage.setItem(D("CANVAS_AGENT_TOGGLE_POS_KEY"), JSON.stringify(storedCanvasAgentTogglePosition(next))); } catch(_) {}
 }
}
function loadCanvasAgentTogglePosition(){
 try {
  const raw = localStorage.getItem(D("CANVAS_AGENT_TOGGLE_POS_KEY"));
  const parsed = raw ? JSON.parse(raw) : null;
  return parsed && (parsed.edge === 'left' || parsed.edge === 'right') ? parsed : null;
 } catch(_) {
  return null;
 }
}
function currentCanvasAgentTogglePosition(){
 const rect = D("canvasAgentToggle")?.getBoundingClientRect?.();
 return rect ? {left:rect.left, top:rect.top} : loadCanvasAgentTogglePosition();
}
function installCanvasAgentToggleDrag(){
 if(!D("canvasAgentToggle")) return;
 D("canvasAgentToggle").draggable = false;
 D("canvasAgentToggle").querySelectorAll?.('img').forEach(img => { img.draggable = false; });
 D("canvasAgentToggle").addEventListener('dragstart', e => {
  e.preventDefault();
  e.stopPropagation();
 });
 D("canvasAgentToggle").addEventListener('dragover', e => {
  e.preventDefault();
  e.stopPropagation();
 });
 D("canvasAgentToggle").addEventListener('drop', e => {
  e.preventDefault();
  e.stopPropagation();
 });
 D("canvasAgentToggle").addEventListener('pointerdown', e => {
  if(e.button !== 0) return;
  e.preventDefault();
  e.stopPropagation();
  const rect = D("canvasAgentToggle").getBoundingClientRect();
  deps.setCanvasAgentToggleDragState({
   pointerId:e.pointerId,
   startX:e.clientX,
   startY:e.clientY,
   left:rect.left,
   top:rect.top,
   moved:false
  });
  D("canvasAgentToggle").classList.add('is-dragging');
  try { D("canvasAgentToggle").setPointerCapture(e.pointerId); } catch(_) {}
 });
 D("canvasAgentToggle").addEventListener('pointermove', e => {
  const state = D("canvasAgentToggleDragState");
  if(!state || state.pointerId !== e.pointerId) return;
  e.preventDefault();
  e.stopPropagation();
  const dx = e.clientX - state.startX;
  const dy = e.clientY - state.startY;
  if(Math.abs(dx) > 3 || Math.abs(dy) > 3) state.moved = true;
  applyCanvasAgentTogglePosition({left:state.left + dx, top:state.top + dy}, false);
 });
 function finish(e){
  const state = D("canvasAgentToggleDragState");
 if(!state || state.pointerId !== e.pointerId) return;
 e.preventDefault();
 e.stopPropagation();
 deps.setCanvasAgentToggleDragState(null);
 D("canvasAgentToggle").classList.remove('is-dragging');
 try { D("canvasAgentToggle").releasePointerCapture(e.pointerId); } catch(_) {}
  applyCanvasAgentTogglePosition(currentCanvasAgentTogglePosition(), true);
  if(state.moved) deps.setCanvasAgentToggleSuppressClickUntil(Date.now() + 250);
  else if(e.type === 'pointerup'){ setCanvasAgentOpen(true); setTimeout(() => canvasAgentInput?.focus(), 80); }
 }
 D("canvasAgentToggle").addEventListener('pointerup', finish);
 D("canvasAgentToggle").addEventListener('pointercancel', finish);
 window.addEventListener('resize', () => applyCanvasAgentTogglePosition(loadCanvasAgentTogglePosition() || {}, false));
 applyCanvasAgentTogglePosition(loadCanvasAgentTogglePosition() || {}, false);
}

    global.CanvasAgentToggleDrag = {
        configure,
        clampCanvasAgentTogglePosition,
        canvasAgentTogglePositionFromStored,
        storedCanvasAgentTogglePosition,
        applyCanvasAgentTogglePosition,
        loadCanvasAgentTogglePosition,
        currentCanvasAgentTogglePosition,
        installCanvasAgentToggleDrag,
    };
})(typeof window !== 'undefined' ? window : this);

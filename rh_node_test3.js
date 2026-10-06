
const fs=require('fs');
let src=fs.readFileSync('D:/APP/MyridTV/_internal/static/js/canvas-rh-controls.js','utf8');
let CACHE={};
new Function(src)();
const api=globalThis.CanvasRhControls;
console.log('api?', typeof api, Object.keys(api||{}).length);
api.configure({
  escapeHtml:s=>String(s), tr:k=>k,
  rhIsWorkflowLinkValue:v=>Array.isArray(v)&&v.length===2&&typeof v[0]==='string',
  getRunningHubWorkflowCache:()=>CACHE, getSettings:()=>({rhNodeOff:{}}), rhNodeOffBucket:()=>({})
});
const providers=JSON.parse(fs.readFileSync('C:/Users/77972/AppData/Roaming/MyridTV/data/api_providers.json','utf8'));
const rh=providers.find(p=>p.id==='runninghub');
let ok=true;
for(const w of rh.rh_workflows){
  CACHE={}; CACHE[w.id]=w;
  const list=api.rhWorkflowNodeList({kind:'workflow', id:w.id, entry:w});
  const selected=new Set((w.fields||[]).filter(f=>f.enabled===true).map(f=>String(f.nodeId)));
  const wrong=list.filter(n=>!selected.has(String(n.id)));
  console.log(`${w.title}: 工作流共 ${Object.keys(w.workflowJson||{}).length} 节点 → 开关列出 ${list.length} 个 [期望 ${selected.size}]`);
  console.log('    ', list.map(n=>n.id+':'+n.label).join(' | '));
  if(list.length!==selected.size||wrong.length){ ok=false; console.log('    !! 多出:', wrong.map(n=>n.id)); }
}
CACHE={};
const w=rh.rh_workflows.find(x=>x.id==='2080925634650886146');
const fb=api.rhWorkflowNodeList({kind:'workflow',id:w.id,entry:w}).map(n=>n.id).sort((a,b)=>a-b);
console.log('缓存为空时回退 entry.fields →', fb.join(','), '(期望 95,96,115)');
console.log(ok ? '✅ 三个工作流的开关列表都等于已勾选节点' : '❌ 存在不一致');

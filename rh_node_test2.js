
const fs=require('fs');
let src=fs.readFileSync('D:/APP/MyridTV/_internal/static/js/canvas-rh-controls.js','utf8');
let CACHE={};
const mod={};
const fn=new Function('global', src + '\n; return global.CanvasRhControls;');
const api=fn(mod);
api.configure({
  escapeHtml:s=>String(s), tr:k=>k,
  rhIsWorkflowLinkValue:v=>Array.isArray(v)&&v.length===2&&typeof v[0]==='string',
  getRunningHubWorkflowCache:()=>CACHE,
  getSettings:()=>({rhNodeOff:{}}),
  rhNodeOffBucket:()=>({})
});
const providers=JSON.parse(fs.readFileSync('C:/Users/77972/AppData/Roaming/MyridTV/data/api_providers.json','utf8'));
const rh=providers.find(p=>p.id==='runninghub');
let ok=true;
for(const w of rh.rh_workflows){
  CACHE={}; CACHE[w.id]=w;
  const list=api.rhWorkflowNodeList({kind:'workflow', id:w.id, entry:w});
  const selected=new Set((w.fields||[]).filter(f=>f.enabled===true).map(f=>String(f.nodeId)));
  const wrongSel=list.filter(n=>!selected.has(String(n.id)));
  console.log(`${w.title}: 全部 ${Object.keys(w.workflowJson||{}).length} 节点 → 开关列出 ${list.length} [期望 ${selected.size}]`);
  console.log('    ', list.map(n=>n.id+':'+n.label).join(' | '));
  if(list.length!==selected.size || wrongSel.length){ ok=false; console.log('    !! 不一致:', wrongSel.map(n=>n.id)); }
}
CACHE={};
const w=rh.rh_workflows.find(x=>x.id==='2080925634650886146');
const fb=api.rhWorkflowNodeList({kind:'workflow',id:w.id,entry:w}).map(n=>n.id).sort();
console.log('缓存为空时回退 entry.fields →', fb.join(','), '(期望 95,96,115)');
console.log(ok ? '✅ 全部工作流：开关列表 = 已勾选节点' : '❌ 存在不一致');

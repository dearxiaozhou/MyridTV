
const fs=require('fs');
let src=fs.readFileSync('D:/APP/MyridTV/_internal/static/js/canvas-rh-controls.js','utf8');
const fakeWindow={};
// 提供最小 deps
const deps={
  escapeHtml:s=>String(s), tr:k=>k,
  runningHubEntries:()=>[], selectedRunningHubRef:()=>null,
  rhNodeOffBucket:()=>({}), renderRhInputsRow:()=>'', rhFieldRole:()=>'',
  renderRhSettingField:()=>'', getRunningHubWorkflowCache:()=>CACHE,
  rhIsWorkflowLinkValue:v=>Array.isArray(v)&&v.length===2&&typeof v[0]==='string',
  getSettings:()=>({rhNodeOff:{}}), getEngineSelect:()=>null
};
let CACHE={};
const mod={};
const fn=new Function('global','depsRef', src + '\n; return {rhWorkflowNodeList, configure};');
const api=fn(mod, deps);
Object.assign(deps,{}); // no-op
api.configure({getRunningHubWorkflowCache:()=>CACHE});
const providers=JSON.parse(fs.readFileSync('C:/Users/77972/AppData/Roaming/MyridTV/data/api_providers.json','utf8'));
const rh=providers.find(p=>p.id==='runninghub');
for(const w of rh.rh_workflows){
  CACHE={}; CACHE[w.id]=w;
  const ref={kind:'workflow', id:w.id, entry:w};
  const list=api.rhWorkflowNodeList(ref);
  console.log(w.title, '| 全部节点', Object.keys(w.workflowJson||{}).length, '| 开关列出', list.length);
  console.log('   ', list.map(n=>n.id+':'+n.label).join(' | '));
}
// 兜底路径：缓存为空时走 entry.fields
CACHE={};
const w=rh.rh_workflows.find(x=>x.id==='2080925634650886146');
console.log('兜底 entry.fields ->', api.rhWorkflowNodeList({kind:'workflow',id:w.id,entry:w}).map(n=>n.id).join(','));

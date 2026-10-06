const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const ctx = vm.createContext({URL, location:{origin:'http://127.0.0.1:3107'}});
for(const name of ['canvas-generation-result-model', 'canvas-generated-output-naming', 'canvas-merge-sync', 'canvas-comfy-job-engine']){
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../_internal/static/js', name+'.js'), 'utf8'), ctx);
}
const model = ctx.CanvasGenerationResultModel;
const merge = ctx.CanvasMergeSync;
merge.configure({smartPendingTasks:()=>[]});
ctx.CanvasComfyJobEngine.configure({nowMs:()=>50000});
const filename = 'comfy_82b4e140-7802-44bb-ab2d-65216619e389_ComfyUI_00001_.png';
const normal = '/assets/output/canvas/images/'+filename;
const recovered = '/assets/output/images/'+filename;
assert.equal(merge.mergeSmartImageLists([{url:normal}], [{url:recovered}]).length, 1);
assert.equal(model.uniqueMediaItems([{url:'/assets/output/%E6%B5%8B%E8%AF%95/images/a.png'}, {url:'http://127.0.0.1:3107/assets/output/测试/images/a.png'}]).length, 1);
assert.equal(model.uniqueMediaItems([{url:'http://127.0.0.1:3107/assets/output/a.png'}, {url:'http://127.0.0.1:8188/assets/output/a.png'}]).length, 2);
const source = 'https://provider.example/result.png';
assert.equal(model.uniqueMediaItems([{url:'/assets/output/a.png',source_url:source}, {url:source}]).length, 1);
assert.equal(model.resultMediaUrls({images:[normal],outputs:[recovered]}).length, 1);
assert.equal(ctx.CanvasGeneratedOutputNaming.uniqueGeneratedMediaItems([normal, recovered]).length, 1);
assert.equal(model.uniqueMediaItems([{url:normal},{url:normal.replace('00001','00002')}]).length, 2);
const old = {id:'n',runAt:100,images:[{url:'/assets/output/old.png'}]};
const latest = {id:'n',runAt:200,images:[{url:'/assets/output/new.png'}]};
for(const pair of [[old,latest],[latest,old]]){
    const merged=merge.mergeSmartNode(...pair);
    assert.equal(merged.images.length, 1);
    assert.equal(merged.images[0].url, latest.images[0].url);
}
const pending = {...latest,running:true,images:[]};
assert.equal(merge.mergeSmartNode(pending,old).images.length, 0);
assert.equal(merge.mergeSmartNode({...old,runAt:200},latest).images.length, 2);
assert.equal(ctx.CanvasComfyJobEngine.isRecoverableComfyNode({images:[],running:true,runStartedAt:1,runSettings:{engine:'comfy'}}), false);
assert.equal(ctx.CanvasComfyJobEngine.isRecoverableComfyNode({images:[],running:true,runStartedAt:1,runSettings:{engine:'comfy'},comfyPromptId:'own-prompt'}), true);
console.log('Canvas output identity, rerun synchronization, batch preservation and recovery ownership: passed');

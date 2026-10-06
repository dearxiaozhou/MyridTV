const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const assert = require('node:assert/strict');
const source = fs.readFileSync(path.join(__dirname,'../_internal/static/js/smart-canvas.js'),'utf8');
// Run the production resolution functions with controlled file-info responses.
const start=source.indexOf('const imageResolutionMetaCache = new Map();');
const end=source.indexOf('function imageResolutionLabel(',start);
const ctx=vm.createContext({URL,Map,location:{origin:'http://127.0.0.1:3107'},
    nodes:[],mediaKindForItem:()=> 'image',fitAutoGroupMemberToSlot:()=> false,
    render:()=>{},scheduleSave:()=>{},requestAnimationFrame:()=>{}});
vm.runInContext(source.slice(start,end),ctx);
const output={url:'/assets/output/result.png',natural_w:1152,natural_h:2048,generationTaskId:'new',source_url:'/assets/input/reference.png'};
const reference={url:'/assets/input/reference.png',natural_w:1152,natural_h:2048};
const owner={w:378,h:671,images:[output]};
ctx.nodes=[owner,{images:[reference]}];
assert.equal(ctx.localAssetUrlForImageInfo(output),output.url);
assert.equal(ctx.mediaItemUrlMatches(output,reference.url),false);
ctx.applyImageResolutionMetadata(output.url,2048,1152,output,ctx.imageResolutionCacheKey(output));
assert.equal(output.natural_w,2048);assert.equal(output.natural_h,1152);
assert.deepEqual([reference.natural_w,reference.natural_h],[1152,2048]);
assert(Math.abs(owner.w/owner.h-16/9)<0.01);
assert.equal(owner.w,671);
const previousKey=ctx.imageResolutionCacheKey(output);
output.generationTaskId='rerun';
assert.notEqual(ctx.imageResolutionCacheKey(output),previousKey);
ctx.applyImageResolutionMetadata(output.url,1152,2048,output,previousKey);
assert.equal(output.natural_w,2048,'late previous generation response must not overwrite current dimensions');
const preserved={w:400,h:400,groupLayout:{mode:'preserve'},images:[output]};
assert.equal(ctx.reconcileSingleImageAspect(preserved,output,2048,1152),false);
const helpers=vm.createContext({URL});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../_internal/static/js/canvas-media-helpers.js'),'utf8'),helpers);
assert.equal(helpers.CanvasMediaHelpers.localDisplayUrlForMediaItem({...output,originalLocalUrl:reference.url}),output.url);
console.log('Actual output dimensions, reference isolation, node aspect, cache generation and stale-response guards: passed');

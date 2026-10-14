"""Exercise production generation completion paths in the running app; no paid jobs/writes."""
import json
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe", headless=True)
    page = browser.new_page(viewport={"width":1440,"height":1000})
    page.route('**/api/canvas-audio*', lambda route: route.fulfill(status=200,content_type='application/json',
        body='{"ok":true,"items":[{"url":"/assets/verification.wav","kind":"audio"}]}'))
    page.route('**/api/canvases/**', lambda route: route.fulfill(status=200,content_type='application/json',body='{"ok":true}')
        if route.request.method in ('PUT','POST','PATCH','DELETE') else route.continue_())
    page.goto('http://127.0.0.1:3107/static/smart-canvas.html',wait_until='networkidle')
    page.wait_for_function("typeof CanvasSmartTaskSupervisor === 'object'")
    results = page.evaluate("""async () => {
        canvas={id:'generation-frame-verification',nodes:[],connections:[],logs:[],settings:{}};
        const picture='data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="%234980ab"/></svg>';
        smartGeneratedOutputItems=async urls=>urls.map((u,i)=>({url:typeof u==='string'?u:u.url,name:'test-'+i+'.png',kind:'image',generatedResult:true,natural_w:640,natural_h:360}));
        const results=[];
        const rect=n=>{const r=nodeRect(n);return [r.width,r.height]};
        for(const engine of ['comfy','api','runninghub','volcengine','blender']){
            for(const route of ['direct','async','cascade','append','loop','failure']){
                for(const kind of ['image','video','audio']){
                    const n={id:'frame',type:'smart-image',title:engine+' '+route+' '+kind,x:120,y:140,w:704,h:396,
                        images:[],scale:1,runSettings:{engine,apiKind:kind==='video'?'video':'image',ratio:'wide',videoAspect:'16:9'},
                        pendingTasks:[{taskId:'frame-task',kind}],pending:1};
                    nodes=[n];canvas.connections=[];canvas.logs=[];selectedId='';selectedIds=[];
                    const before=rect(n);
                    preserveNodeCardForRun(n,n.runSettings);
                    const item={url:picture,name:'result',kind,generatedResult:true,natural_w:640,natural_h:360};
                    if(route==='direct') await finalizePendingNode(n,[item],null,kind);
                    if(route==='async') await finalizeSmartPendingTask(n,'frame-task',[item],kind);
                    if(route==='cascade') replaceOutputsToNodeWithHistory(n,[item],kind,null,{skipShift:true});
                    if(route==='append') appendOutputsToNode(n,[item],kind,{skipShift:true});
                    if(route==='loop'){n.images=[item];finishLoopTargetPreviewState(n);}
                    if(route==='failure'){n.pending=0;restoreNodeBoxAfterFailure(n);}
                    const after=rect(n);
                    if(JSON.stringify(before)!==JSON.stringify(after)) throw new Error(JSON.stringify({engine,route,kind,before,after}));
                    if(n.images[0]) reconcileSingleImageAspect(n,n.images[0],1080,1920);
                    if(JSON.stringify(before)!==JSON.stringify(rect(n))) throw new Error('metadata changed '+engine+'/'+route+'/'+kind);
                    const restored=normalizeLegacySmartNode(JSON.parse(JSON.stringify(n)));
                    if(JSON.stringify(before)!==JSON.stringify(rect(restored))) throw new Error('reload changed '+engine+'/'+route+'/'+kind);
                    render();
                    const el=world.querySelector('[data-id="frame"]');
                    if(el.style.width!=='704px'||el.style.height!=='396px') throw new Error('DOM box changed '+engine+'/'+route+'/'+kind);
                    results.push({engine,route,kind,before,after});
                }
            }
        }
        // Comfy synchronous completion used to ignore a persisted cardSize after w/h were cleared.
        const legacy={id:'legacy',type:'smart-image',x:120,y:140,images:[{url:picture,kind:'video',generatedResult:true}],
            cardSize:{width:820,height:462},cardSizing:'media',runSettings:{engine:'comfy',apiKind:'video'}};
        if(JSON.stringify(rect(legacy))!=='[820,462]') throw new Error('legacy Comfy card size ignored');
        // A locked generation frame must survive MCP multi-image grouping as the first member.
        const mcp={id:'multi',type:'smart-image',x:120,y:140,w:704,h:396,scale:1,__origin:'mcp',
            images:[],runSettings:{engine:'comfy'}};
        preserveNodeCardForRun(mcp);mcp.images=[{url:picture,natural_w:640,natural_h:360},{url:picture+'#2',natural_w:640,natural_h:360}];
        nodes=materializeAgentImageGroups([mcp]);
        if(JSON.stringify(rect(mcp))!=='[704,396]') throw new Error('MCP grouping shrank source');
        const during=[];
        CanvasGenerationRunner.configure({
            ensureCustomComfyWorkflowReady:async()=>{},buildPromptRequest:()=>({prompt:'frame test',displayPrompt:'frame test',refs:[]}),
            addSmartGenerationLog:()=>{},saveCanvas:async()=>{},
            runComfyGeneration:async(n,p,r,target,meta)=>{during.push(rect(target));await finalizePendingNode(target,[picture],meta,'video');},
            runApiVideoGeneration:async()=>{during.push(rect(nodes[0]));return {urls:[picture]};},
            runApiGeneration:async()=>{during.push(rect(nodes[0]));return {taskIds:['mock-frame']};},
            runRunningHubGeneration:async()=>{during.push(rect(nodes[0]));return [picture];},
            resumeSmartPendingNode:async n=>{await finalizeSmartPendingTask(n,'mock-frame',[picture],'image');}
        });
        for(const engine of ['comfy','api','runninghub','volcengine','blender']){
            const n={id:'run-frame',type:'smart-image',title:'运行尺寸',x:120,y:140,w:704,h:396,images:[],scale:1,
                promptDraftText:'frame test',runSettings:{...settings,engine,apiKind:engine==='api'?'image':'video',comfyMode:'custom',ratio:'wide'}};
            nodes=[n];selectedId=n.id;selectedIds=[];canvas.connections=[];
            await runGeneration();
            if(JSON.stringify(rect(n))!=='[704,396]' || !n.images.length) throw new Error('full runner changed '+engine+JSON.stringify(n));
            results.push({engine,route:'full-runner',kind:n.outputKind,before:[704,396],after:rect(n)});
        }
        if(during.some(box=>JSON.stringify(box)!=='[704,396]')) throw new Error('pending box changed '+JSON.stringify(during));
        const speech={id:'speech-frame',type:'smart-speech',speechLayout:3,w:1080,h:620,speechText:'test',speechProvider:'test',speechModel:'mimo-v2.5-tts'};
        const originalFetch=window.fetch;
        window.fetch=async(url,init)=>String(url).endsWith('/api/canvas-audio')
            ? new Response(JSON.stringify({ok:true,items:[{url:picture,kind:'audio'}]}),{status:200,headers:{'Content-Type':'application/json'}})
            : originalFetch(url,init);
        CanvasSpeech.configure({getProviders:()=>[{id:'test',enabled:true,has_key:true,audio_models:['mimo-v2.5-tts']}],
            getNodes:()=>[speech],getConnections:()=>[],getCanvasId:()=>canvas.id,getCanvasTitle:()=>'',render:()=>{},scheduleSave:()=>{},toast:message=>{throw new Error(message)}});
        const speechBefore=rect(speech);await CanvasSpeech.run(speech);
        if(speech.speechError||!speech.images?.length||JSON.stringify(speechBefore)!==JSON.stringify(rect(speech))) throw new Error('speech changed frame');
        results.push({engine:'speech',route:'full-runner',kind:'audio',before:speechBefore,after:rect(speech)});
        window.fetch=originalFetch;
        nodes=[legacy];selectedId='';render();Object.assign(viewport,{x:0,y:0,scale:1});applyViewport();
        return results;
    }""")
    page.screenshot(path=str(ROOT/'_verification/generation-frame-v01019.png'))
    # Render copies of the user's completed Comfy videos with real media metadata.
    with urllib.request.urlopen('http://127.0.0.1:3107/api/canvases/7759942',timeout=10) as response:
        live=json.loads(response.read())['canvas']
    videos=[n for n in live.get('nodes',[]) if n.get('runSettings',{}).get('engine')=='comfy'
        and any(i.get('kind')=='video' for i in n.get('images',[])) and not n.get('pending')][:3]
    if videos:
        sizes=page.evaluate("""items=>{
            nodes=items;canvas.connections=[];selectedId='';selectedIds=[];
            nodes.forEach((n,i)=>{n.x=40+i*450;n.y=120;n.running=false;n.pending=0;delete n.pendingTasks;delete n.comfyStatus;});
            render();Object.assign(viewport,{x:0,y:0,scale:0.8});applyViewport();
            return nodes.map(n=>({id:n.id,card:n.cardSize,rect:nodeRect(n)}));
        }""",videos)
        for value in sizes:
            if value['card']:
                assert value['rect']['width']==value['card']['width'] and value['rect']['height']==value['card']['height'],value
        page.screenshot(path=str(ROOT/'_verification/generation-frame-v01019-existing-videos.png'))
        print('PASS existing Comfy videos:',json.dumps(sizes,ensure_ascii=False),flush=True)
    (ROOT/'_verification/generation-frame-v01019.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'PASS {len(results)} production completion-path cases; metadata, reload, DOM, legacy Comfy, MCP grouping')
    browser.close()

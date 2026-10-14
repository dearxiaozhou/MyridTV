"""Real runtime regression for generation ownership; providers are deferred stubs."""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = os.environ.get('MYRIDTV_TEST_BASE', 'http://127.0.0.1:3217')
OUT = Path('_verification/generation-lifecycle')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        executable = os.environ.get('MYRIDTV_TEST_BROWSER')
        if not executable and not Path(p.chromium.executable_path).exists():
            candidates = sorted((Path(os.environ.get('LOCALAPPDATA', '')) / 'ms-playwright').glob('chromium-*/chrome-win*/chrome.exe'))
            executable = str(candidates[-1]) if candidates else None
        browser = p.chromium.launch(headless=True, **({'executable_path': executable} if executable else {}))
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        def guard(route):
            r = route.request
            if not r.url.startswith(BASE + '/'):
                route.abort()
            elif '/static/app_config.json' in r.url:
                route.fulfill(json={'proxy': {'base_url': BASE}})
            elif r.method not in ('GET', 'HEAD'):
                route.fulfill(json={'ok': True})
            else:
                route.continue_()
        page.route('**/*', guard)
        page.goto(BASE + '/smart-canvas.html', wait_until='networkidle')
        result = page.evaluate("""async () => {
            const picture='data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="#6288c9"/></svg>');
            canvas={id:'generation-owner-fixture',title:'Generation ownership',nodes:[],connections:[],logs:[],settings:{}};
            const a={id:'a',type:'smart-image',x:100,y:100,w:704,h:396,images:[],scale:1,
                promptDraftHtml:'Draft A',runSettings:{...settings,engine:'api',apiKind:'video',count:2}};
            const b={id:'b',type:'smart-image',x:900,y:100,w:320,h:240,images:[],scale:1,
                promptDraftHtml:'Draft B',runSettings:{...settings,engine:'api',apiKind:'image',count:5}};
            nodes=[a,b]; selectedId=a.id;selectedIds=[];render();applyViewport();
            let resolveVideo;const response=new Promise(resolve=>resolveVideo=resolve);
            const logs=[];
            CanvasGenerationRunner.configure({
                ensureCustomComfyWorkflowReady:async()=>{},
                buildPromptRequest:()=>({prompt:'fixture prompt',displayPrompt:'fixture prompt',refs:[]}),
                addSmartGenerationLog:entry=>logs.push(entry),saveCanvas:async()=>{},
                runApiVideoGeneration:()=>response
            });
            const running=runGeneration();
            for(let i=0;i<20&&!a.pending;i++) await new Promise(r=>setTimeout(r,0));
            const before=nodeRect(a);
            selectNodeFromPointer(b.id);syncSelectionUi();updateComposer();
            promptInput.textContent='Editing B while A runs';
            resolveVideo({urls:[{url:picture,kind:'video'}]});await running;
            return {completed:a.images.length===1,selectionKept:selectedId===b.id,
                editorKept:CanvasStateHub.get('ui').editor.nodeId===b.id,
                settingsKept:settings.count===5,draftKept:promptInput.textContent==='Editing B while A runs',
                frameKept:nodeRect(a).width===before.width&&nodeRect(a).height===before.height,
                selectedId,count:settings.count,logs:logs.length};
        }""")
        page.screenshot(path=str(OUT / 'ownership.png'))
        races = page.evaluate("""async () => {
            const lifecycle=CanvasGenerationLifecycle;
            const base='data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="#6288c9"/></svg>');
            const n={id:'retry',type:'smart-image',x:100,y:100,w:704,h:396,images:[],scale:1,
                promptDraftHtml:'Retry draft',runSettings:{...settings,engine:'api',apiKind:'video',count:1}};
            nodes=[n];selectedId=n.id;selectedIds=[];render();
            const requests=[];
            CanvasGenerationRunner.configure({runApiVideoGeneration:()=>new Promise((resolve,reject)=>requests.push({resolve,reject}))});
            async function start(){
                const run=runGeneration();
                for(let i=0;i<200&&requests.length===start.count;i++) await new Promise(r=>setTimeout(r,10));
                if(requests.length===start.count) throw new Error('Provider boundary was not reached');
                start.count=requests.length;return {run};
            }
            start.count=0;
            const first=await start(), second=await start();
            const latest=n.generationAttemptId;
            requests[0].resolve({urls:[base+'#old']});await first.run;
            const staleSuccessIgnored=n.generationAttemptId===latest&&n.pending===1&&!n.images.length;
            requests[1].resolve({urls:[base+'#new']});await second.run;
            const latestCompleted=n.images[0]?.url===base+'#new'&&n.generationState==='succeeded'&&!n.pending;
            n.images=[];
            const third=await start(), fourth=await start();
            requests[2].reject(new Error('late old failure'));await third.run;
            const staleFailureIgnored=n.pending===1&&!n.runError&&n.generationState==='running';
            requests[3].resolve({urls:[base+'#newer']});await fourth.run;

            // Old cancellation must neither interrupt nor clear a freshly started Comfy job.
            const originalFetch=window.fetch, calls=[];let releaseCancel;
            window.fetch=(url,options)=>{
                if(String(url).includes('/api/comfyui/jobs/')){
                    calls.push(String(url));
                    if(String(url).endsWith('/cancel')) return new Promise(resolve=>releaseCancel=()=>resolve(new Response('{}',{status:200})));
                    return Promise.resolve(new Response('{}',{status:200}));
                }
                return originalFetch(url,options);
            };
            lifecycle.begin(n,{id:'cancel-old'});n.comfyJobId='old-job';n.comfyRunToken='old-token';
            const cancelling=cancelComfyJob(n);
            lifecycle.begin(n,{id:'cancel-new'});n.pending=2;n.running=true;n.comfyJobId='new-job';n.comfyRunToken='new-token';
            releaseCancel();await cancelling;window.fetch=originalFetch;
            const cancelRetryKept=n.generationAttemptId==='cancel-new'&&n.pending===2&&n.running&&n.comfyJobId==='new-job'&&calls.length===1;
            let releasePoll;
            n.comfyStatus='running';
            window.fetch=(url,options)=>String(url).includes('/api/comfyui/jobs/')
                ? new Promise(resolve=>releasePoll=()=>resolve(new Response(JSON.stringify({status:'done',images:[base+'#obsolete-poll']}),{status:200})))
                : originalFetch(url,options);
            const polling=CanvasComfyJobEngine.syncComfyJobStatusOnce(n);
            lifecycle.begin(n,{id:'poll-newer'});n.comfyJobId='newer-job';n.pending=3;n.running=true;
            releasePoll();await polling;window.fetch=originalFetch;
            const stalePollIgnored=n.comfyJobId==='newer-job'&&n.pending===3&&n.running;

            // One task can produce multiple outputs. Pending counts represent tasks, not output count.
            const batch={id:'batch',type:'smart-image',x:100,y:100,w:704,h:396,scale:1,images:[],pending:8,
                pendingTasks:[{taskId:'one',kind:'video'},{taskId:'two',kind:'video'}]};
            await finalizeSmartPendingTask(batch,'one',[base+'#1'],'video');
            const partialCountCorrect=batch.pending===1&&batch.pendingTasks.length===1;
            await finalizeSmartPendingTask(batch,'two',[base+'#2'],'video');
            const batchFinished=batch.pending===0&&!batch.pendingTasks&&batch.images.length===2;

            const frames=[];
            for(const engine of ['api','comfy','runninghub','volcengine','blender']){
                for(const outcome of ['succeeded','failed','cancelled']){
                    const card={id:engine+outcome,type:'smart-image',w:704,h:396,scale:1,images:[],runSettings:{engine}};
                    preserveNodeCardForRun(card);const attempt=lifecycle.begin(card);lifecycle.transition(card,attempt,'queued');lifecycle.transition(card,attempt,'running');
                    // User resize during generation is the new authoritative frame.
                    card.w=820;card.h=462;card.cardSize={width:820,height:462};
                    lifecycle.finish(card,attempt,outcome,'fixture error');
                    const rect=nodeRect(card), restored=normalizeLegacySmartNode(JSON.parse(JSON.stringify(card)));
                    frames.push(rect.width===820&&rect.height===462&&nodeRect(restored).width===820&&nodeRect(restored).height===462);
                }
            }
            const invalid={type:'smart-image',w:704,h:396,images:[],cardSize:{width:'invalid',height:0}};
            restoreNodeBoxAfterFailure(invalid);
            const invalidFrameRecovered=invalid.w===704&&invalid.h===396;
            // Exercise the full runner for each engine using provider-boundary stubs.
            smartGeneratedOutputItems=async(items,kind)=>items.map(item=>({url:typeof item==='string'?item:item.url,kind,natural_w:640,natural_h:360,generatedResult:true}));
            CanvasGenerationRunner.configure({
                runComfyGeneration:async(node,prompt,refs,target,meta)=>finalizePendingNode(target,[base],meta,'video'),
                runApiVideoGeneration:async()=>({urls:[base]}),
                runApiGeneration:async()=>({taskIds:['fixture-task']}),
                runRunningHubGeneration:async()=>[base],
                resumeSmartPendingNode:async target=>finalizeSmartPendingTask(target,'fixture-task',[base],'image')
            });
            const engines=[];
            for(const engine of ['api','comfy','runninghub','volcengine','blender']){
                const card={id:'engine-'+engine,type:'smart-image',x:100,y:100,w:704,h:396,cardSize:{width:704,height:396},scale:1,images:[],
                    promptDraftHtml:'Engine fixture',runSettings:{...settings,engine,apiKind:engine==='api'?'image':'video',count:1}};
                nodes=[card];selectedId=card.id;selectedIds=[];render();
                await runGeneration();
                engines.push({engine,ok:card.images.length>0&&card.pending===0&&nodeRect(card).width===704&&nodeRect(card).height===396&&card.generationState==='succeeded',
                    error:card.runError || '',state:card.generationState,pending:card.pending,outputs:card.images.length});
            }
            return {staleSuccessIgnored,latestCompleted,staleFailureIgnored,cancelRetryKept,stalePollIgnored,partialCountCorrect,batchFinished,
                framesPreserved:frames.every(Boolean),frameCases:frames.length,invalidFrameRecovered,allEnginesCompleted:engines.every(item=>item.ok),engines};
        }""")
        result.update(races)
        (OUT / 'results.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        checks = ['completed','selectionKept','editorKept','settingsKept','draftKept','frameKept',
                  'staleSuccessIgnored','latestCompleted','staleFailureIgnored','cancelRetryKept',
                  'partialCountCorrect','batchFinished','framesPreserved','invalidFrameRecovered','stalePollIgnored','allEnginesCompleted']
        for key in checks:
            print(('PASS' if result[key] else 'FAIL') + ' - ' + key)
        assert all(result[key] for key in checks) and not errors, (result, errors)
        browser.close()


if __name__ == '__main__':
    main()

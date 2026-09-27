/* Owns brush/mask pointer drawing and delegates custom grid gestures. */
(function(global){
    'use strict';

    const MASK_BRUSH_ALPHA=115;
    const MASK_BRUSH_COLOR=`rgba(255,255,255,${MASK_BRUSH_ALPHA/255})`;
    const state={draw:null,tool:'free',labelCounter:1};
    const deps={
        getCanvas:() => global.document.getElementById('editDrawCanvas'),
        getMode:() => 'brush',
        getGridController:() => global.CanvasImageGridSplitController,
        getElementById:id => global.document.getElementById(id),
        removeInlineEditor:() => {},
        syncTextToolState:() => {},
        pushHistory:() => {},
        snapshot:() => null,
        restoreSnapshot:() => {},
        syncGridUndoButton:() => {},
        refreshGridPreview:() => {},
        syncHistoryButtons:() => {}
    };

    function configure(options){Object.assign(deps,options || {});}
    function getState(){return state;}
    function getTool(){return state.tool;}
    function setDrawState(value){state.draw=value;}
    function getLabelCounter(){return state.labelCounter;}
    function setLabelCounter(value){state.labelCounter=Number(value) || 1;}
    function brushSize(){return Number(deps.getElementById(deps.getMode()==='mask'?'maskBrushSize':'paintBrushSize')?.value || 20);}
    function brushColor(){return deps.getElementById('paintBrushColor')?.value || '#ff2d55';}

    function setTool(tool){
        if(tool!=='text') deps.removeInlineEditor(true);
        state.tool=['free','rect','ellipse','label','text'].includes(tool) ? tool : 'free';
        syncToolButtons();
        deps.syncTextToolState(true);
        return state.tool;
    }

    function syncToolButtons(){
        global.document.querySelectorAll('[data-brush-tool]').forEach(button=>{
            const active=button.dataset.brushTool===state.tool;
            button.classList.toggle('primary',active);
            button.classList.toggle('secondary',!active);
        });
        deps.getElementById('cropCanvas')?.classList.toggle('text-mode',deps.getMode()==='brush' && state.tool==='text');
    }

    function point(event){
        const canvas=deps.getCanvas();
        const rect=canvas.getBoundingClientRect();
        return {x:(event.clientX-rect.left)*canvas.width/Math.max(1,rect.width),
            y:(event.clientY-rect.top)*canvas.height/Math.max(1,rect.height)};
    }

    function setupStyle(context){
        context.lineCap='round'; context.lineJoin='round'; context.lineWidth=brushSize();
        context.strokeStyle=deps.getMode()==='mask' ? MASK_BRUSH_COLOR : brushColor();
        context.fillStyle=deps.getMode()==='mask' ? MASK_BRUSH_COLOR : brushColor();
        context.globalCompositeOperation='source-over';
    }

    function normalizeMaskPreviewCanvas(canvas=deps.getCanvas()){
        if(deps.getMode()!=='mask' || !canvas?.width || !canvas?.height) return;
        const context=canvas.getContext('2d');
        const imageData=context.getImageData(0,0,canvas.width,canvas.height);
        const data=imageData.data;
        let changed=false;
        for(let i=0;i<data.length;i+=4){
            if(data[i+3]<=0) continue;
            data[i]=255; data[i+1]=255; data[i+2]=255;
            if(data[i+3]>MASK_BRUSH_ALPHA) data[i+3]=MASK_BRUSH_ALPHA;
            changed=true;
        }
        if(changed) context.putImageData(imageData,0,0);
    }

    function strokeFreeDrawPoint(next){
        if(!state.draw) return;
        const context=deps.getCanvas().getContext('2d');
        setupStyle(context);
        const dx=next.x-state.draw.x, dy=next.y-state.draw.y;
        const distance=Math.hypot(dx,dy);
        const radius=Math.max(1,brushSize()/2);
        if(distance>radius){
            const steps=Math.ceil(distance/Math.max(1,radius*0.35));
            for(let i=1;i<=steps;i++){
                const t=i/steps, x=state.draw.x+dx*t, y=state.draw.y+dy*t;
                context.beginPath(); context.arc(x,y,radius,0,Math.PI*2); context.fill();
            }
        }
        context.beginPath(); context.moveTo(state.draw.x,state.draw.y); context.lineTo(next.x,next.y); context.stroke();
        state.draw.x=next.x; state.draw.y=next.y;
    }

    function circledNumber(number){return number>=1 && number<=20 ? String.fromCharCode(0x2460+number-1) : String(number);}
    function drawBrushShape(context,start,end){
        setupStyle(context);
        const x=Math.min(start.x,end.x), y=Math.min(start.y,end.y);
        const width=Math.abs(end.x-start.x), height=Math.abs(end.y-start.y);
        if(state.tool==='rect') context.strokeRect(x,y,width,height);
        else if(state.tool==='ellipse'){
            context.beginPath(); context.ellipse(x+width/2,y+height/2,Math.max(1,width/2),Math.max(1,height/2),0,0,Math.PI*2); context.stroke();
        }
    }

    function drawNumberLabel(position){
        const context=deps.getCanvas().getContext('2d');
        const size=Math.max(18,brushSize()*2.2);
        const label=circledNumber(state.labelCounter++);
        setupStyle(context);
        context.save(); context.font=`900 ${size}px Arial, sans-serif`; context.textAlign='center'; context.textBaseline='middle'; context.lineWidth=Math.max(3,size/8);
        context.strokeStyle='rgba(255,255,255,0.92)'; context.strokeText(label,position.x,position.y); context.fillStyle=brushColor(); context.fillText(label,position.x,position.y); context.restore();
    }

    function begin(event){
        if(deps.getMode()==='crop') return;
        event.preventDefault(); event.stopPropagation();
        const canvas=deps.getCanvas();
        canvas.setPointerCapture?.(event.pointerId);
        const position=point(event);
        const mode=deps.getMode();
        const grid=deps.getGridController();
        if(mode==='grid'){
            if(!grid.isCustomMode()) return;
            grid.beginLineEdit(position,canvas.width,canvas.height,event.pointerId);
            deps.syncGridUndoButton(); deps.refreshGridPreview(); return;
        }
        const context=canvas.getContext('2d');
        deps.pushHistory();
        if(mode==='brush' && state.tool==='label'){
            drawNumberLabel(position); state.draw=null; canvas.releasePointerCapture?.(event.pointerId); return;
        }
        state.draw={x:position.x,y:position.y,sx:position.x,sy:position.y,pointerId:event.pointerId,
            snapshot:mode==='brush' && state.tool!=='free' ? deps.snapshot() : null};
        setupStyle(context);
        context.beginPath(); context.moveTo(position.x,position.y); context.lineTo(position.x+0.01,position.y+0.01);
        if(mode==='mask' || state.tool==='free') context.stroke();
        normalizeMaskPreviewCanvas(canvas);
    }

    function move(event){
        const canvas=deps.getCanvas();
        const grid=deps.getGridController();
        if(deps.getMode()==='grid' && grid.isCustomMode() && grid.isDragging()){
            event.preventDefault(); event.stopPropagation();
            grid.moveLineEdit(point(event),canvas.width,canvas.height); deps.refreshGridPreview(); return;
        }
        const mode=deps.getMode();
        if(!state.draw || mode==='crop' || mode==='grid') return;
        event.preventDefault(); event.stopPropagation();
        const context=canvas.getContext('2d'), position=point(event);
        if(mode==='brush' && state.tool!=='free'){
            deps.restoreSnapshot(state.draw.snapshot);
            drawBrushShape(context,{x:state.draw.sx,y:state.draw.sy},position); return;
        }
        const events=typeof event.getCoalescedEvents==='function' ? event.getCoalescedEvents() : [];
        if(events.length) events.forEach(item=>strokeFreeDrawPoint(point(item)));
        else strokeFreeDrawPoint(position);
        normalizeMaskPreviewCanvas();
    }

    function end(event){
        const canvas=deps.getCanvas();
        if(state.draw && event?.pointerId!=null) canvas.releasePointerCapture?.(event.pointerId);
        const grid=deps.getGridController();
        if(grid.isDragging() && event?.pointerId!=null) canvas.releasePointerCapture?.(event.pointerId);
        state.draw=null; grid.endLineEdit(); deps.syncHistoryButtons();
    }

    global.CanvasImageEditDrawingController={configure,getState,getTool,setTool,setDrawState,getLabelCounter,setLabelCounter,
        brushSize,brushColor,syncToolButtons,point,setupStyle,normalizeMaskPreviewCanvas,strokeFreeDrawPoint,
        drawBrushShape,drawNumberLabel,begin,move,end};
})(typeof window!=='undefined' ? window : globalThis);

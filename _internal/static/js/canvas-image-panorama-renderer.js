/* Owns the WebGL panorama renderer, image texture lifecycle, and animation loop. */
(function(global){
    'use strict';

    const state = {
        three:null, renderer:null, scene:null, camera:null, sphere:null, texture:null,
        threeLoadPromise:null, image:null, animationId:0, loadedSrc:'', loadToken:0
    };
    const deps = {
        getCanvas:() => global.document.getElementById('panoramaCanvas'),
        getStage:() => global.document.getElementById('panoramaStage'),
        getViewState:() => ({enabled:false,fov:75,yaw:0,pitch:0}),
        getFallbackSource:() => '',
        loadThree:() => import('/static/vendor/js/three-0.160.0.module.js?v=2026.05.30'),
        onReady:() => {},
        toast:() => {},
        translate:key => key
    };

    function configure(options){Object.assign(deps, options || {});}
    function getState(){return state;}

    async function ensure(){
        const canvas = deps.getCanvas();
        if(!canvas) return false;
        if(!state.three){
            state.threeLoadPromise = state.threeLoadPromise || deps.loadThree();
            state.three = await state.threeLoadPromise;
        }
        const THREE = state.three;
        if(!state.renderer){
            state.renderer = new THREE.WebGLRenderer({canvas,antialias:true,alpha:false,preserveDrawingBuffer:true});
            state.renderer.setPixelRatio(1);
            state.renderer.outputColorSpace = THREE.SRGBColorSpace;
        }
        if(!state.scene){
            state.scene = new THREE.Scene();
            state.camera = new THREE.PerspectiveCamera(Number(deps.getViewState().fov) || 75,16 / 9,1,1200);
            const geometry = new THREE.SphereGeometry(500,96,64);
            geometry.scale(-1,1,1);
            const material = new THREE.MeshBasicMaterial({color:0xffffff});
            state.sphere = new THREE.Mesh(geometry,material);
            state.scene.add(state.sphere);
        }
        return Boolean(state.renderer && state.scene && state.camera && state.sphere);
    }

    function disposeTexture(){
        if(state.texture){state.texture.dispose?.(); state.texture = null;}
        if(state.sphere?.material){state.sphere.material.map = null; state.sphere.material.needsUpdate = true;}
        state.image = null;
    }

    function applyTexture(image){
        const THREE = state.three;
        if(!THREE || !state.sphere || !image?.naturalWidth || !image?.naturalHeight) return false;
        disposeTexture();
        const texture = new THREE.Texture(image);
        texture.colorSpace = THREE.SRGBColorSpace;
        texture.needsUpdate = true;
        state.texture = texture;
        state.sphere.material.map = texture;
        state.sphere.material.needsUpdate = true;
        return true;
    }

    function drawFrame(){
        const canvas = deps.getCanvas();
        const image = state.image;
        const {renderer,scene,camera,sphere,three:THREE} = state;
        const view = deps.getViewState();
        if(!view.enabled || !canvas || !renderer || !scene || !camera || !sphere || !THREE || !image?.naturalWidth || !image?.naturalHeight) return false;
        const width = Math.max(1,canvas.width), height = Math.max(1,canvas.height);
        renderer.setSize(width,height,false);
        camera.fov = Math.max(35,Math.min(100,view.fov));
        camera.aspect = width / Math.max(1,height);
        camera.updateProjectionMatrix();
        const pitch = Math.max(-85,Math.min(85,view.pitch));
        const phi = THREE.MathUtils.degToRad(90 - pitch);
        const theta = THREE.MathUtils.degToRad(view.yaw);
        const target = new THREE.Vector3(
            500 * Math.sin(phi) * Math.cos(theta),
            500 * Math.cos(phi),
            500 * Math.sin(phi) * Math.sin(theta)
        );
        camera.position.set(0,0,0);
        camera.lookAt(target);
        renderer.render(scene,camera);
        return true;
    }

    function renderFrame(){
        if(!drawFrame()) return;
        state.animationId = global.requestAnimationFrame(renderFrame);
    }
    function start(){
        if(state.animationId) global.cancelAnimationFrame(state.animationId);
        state.animationId = global.requestAnimationFrame(renderFrame);
    }
    function stop(){
        if(state.animationId) global.cancelAnimationFrame(state.animationId);
        state.animationId = 0;
    }

    async function load(source, allowFallback=true){
        if(!source) return;
        const token = ++state.loadToken;
        const stage = deps.getStage();
        stage?.classList.remove('ready');
        let ready = false;
        try {ready = await ensure();}
        catch(error){global.console?.warn?.('panorama renderer init failed',error); ready = false;}
        if(!ready){
            stage?.classList.add('ready');
            deps.toast(deps.translate('smart.panoramaLoadFailed'));
            return;
        }
        if(token !== state.loadToken) return;
        const image = new global.Image();
        image.crossOrigin = 'anonymous';
        const fallback = allowFallback ? deps.getFallbackSource() : '';
        const done = () => {
            if(token !== state.loadToken) return;
            if(!applyTexture(image)){
                stage?.classList.add('ready');
                deps.toast(deps.translate('smart.panoramaLoadFailed'));
                return;
            }
            state.image = image;
            state.loadedSrc = source;
            stage?.classList.add('ready');
            deps.onReady();
        };
        const fail = () => {
            if(token !== state.loadToken) return;
            if(fallback && fallback !== source){load(fallback,false); return;}
            stage?.classList.add('ready');
            deps.toast(deps.translate('smart.panoramaLoadFailed'));
        };
        image.onload = done;
        image.onerror = fail;
        image.src = source;
        if(image.complete && image.naturalWidth) done();
    }

    function dispose(){
        stop();
        disposeTexture();
        state.loadedSrc = '';
        state.loadToken++;
    }

    global.CanvasImagePanoramaRenderer = {configure,getState,ensure,applyTexture,drawFrame,renderFrame,start,stop,load,disposeTexture,dispose};
})(typeof window !== 'undefined' ? window : globalThis);

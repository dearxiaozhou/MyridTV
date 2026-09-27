/* Owns preview file and grouped-image download requests. */
(function(global){
    'use strict';

    const deps={
        getNavigation:() => ({nodeId:'',index:0}),
        getNodes:() => [],
        safeExportFileName:(name,fallback='download.zip') => String(name||fallback).replace(/[\\/:*?"<>|]+/g,'_').trim()||fallback,
        downloadNameForMediaItem:(item,fallback='output') => item?.name || fallback,
        fetch:(...args) => global.fetch(...args),
        toast:() => {},
        createLink:() => global.document.createElement('a'),
        appendLink:link => global.document.body.appendChild(link),
        removeLink:link => link.remove(),
        createObjectURL:blob => global.URL.createObjectURL(blob),
        revokeObjectURL:url => global.URL.revokeObjectURL(url),
        schedule:callback => global.setTimeout(callback,1200)
    };

    function configure(options){Object.assign(deps,options || {});}
    function currentNode(){
        const navigation=deps.getNavigation();
        return deps.getNodes().find(node=>node.id===navigation.nodeId) || null;
    }
    function clickDownload(href,name){
        const link=deps.createLink();
        link.href=href; link.download=name;
        deps.appendLink(link); link.click(); deps.removeLink(link);
        return {href,name};
    }
    function downloadCurrent(){
        const navigation=deps.getNavigation();
        const image=currentNode()?.images?.[navigation.index];
        if(!image?.url) return false;
        const name=deps.downloadNameForMediaItem(image,'image');
        clickDownload(`/api/download-output?url=${encodeURIComponent(image.url)}&name=${encodeURIComponent(name)}`,name);
        return true;
    }
    function downloadFile(item){
        if(!item?.url) return false;
        const name=deps.downloadNameForMediaItem(item,'output');
        clickDownload(`/api/download-output?url=${encodeURIComponent(item.url)}&name=${encodeURIComponent(name)}`,name);
        return true;
    }
    function groupItems(){
        return (currentNode()?.images || [])
            .filter(item=>item?.url)
            .map((item,index)=>({...item,__index:index}))
            .sort((a,b)=>{
                const ga=a.grid || {}, gb=b.grid || {};
                const rowDiff=Number(ga.row ?? a.__index)-Number(gb.row ?? b.__index);
                if(rowDiff) return rowDiff;
                const colDiff=Number(ga.col ?? a.__index)-Number(gb.col ?? b.__index);
                return colDiff || a.__index-b.__index;
            });
    }
    async function downloadGroup(){
        const node=currentNode();
        const items=groupItems();
        if(!items.length) return false;
        try {
            const filename=deps.safeExportFileName(`${node?.title || 'image-group'}.zip`,'image-group.zip');
            const response=await deps.fetch('/api/canvas-assets/download',{
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({
                    filename,
                    urls:items.map(item=>item.url).filter(Boolean),
                    items:items.map((item,index)=>({url:item.url,name:deps.downloadNameForMediaItem(item,`image-${String(index+1).padStart(2,'0')}`)}))
                })
            });
            if(!response.ok) throw new Error((await response.text()) || '批量下载失败');
            const blob=await response.blob();
            const href=deps.createObjectURL(blob);
            clickDownload(href,filename);
            deps.schedule(()=>deps.revokeObjectURL(href));
            return true;
        } catch(error) {
            deps.toast((error.message || '批量下载失败').slice(0,160));
            return false;
        }
    }

    global.CanvasImagePreviewDownloadController={configure,currentNode,downloadCurrent,downloadFile,groupItems,downloadGroup};
})(typeof window !== 'undefined' ? window : globalThis);

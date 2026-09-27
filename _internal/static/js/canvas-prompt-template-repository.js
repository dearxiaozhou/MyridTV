/* Prompt-template repository: HTTP boundary for libraries, items and categories. */
(function(global){
    'use strict';

    async function getOr(url, fallback){
        const response=await fetch(url);
        return response.ok?response.json():fallback;
    }
    async function request(url,method,body,fallbackMessage){
        const options={method,headers:{'Content-Type':'application/json'}};
        if(body!==undefined) options.body=JSON.stringify(body);
        const response=await fetch(url,options);
        const data=await response.json().catch(()=>({}));
        if(!response.ok) throw new Error(data.detail||fallbackMessage);
        return data;
    }
    async function loadLibraries(){
        const data=await getOr('/api/prompt-libraries',{library:{libraries:[]}});
        const libraries=Array.isArray(data.library?.libraries)?data.library.libraries:[];
        if(!libraries.length){
            const fallback=await getOr('/api/smart-canvas/prompt-templates',{templates:[]});
            const builtinPromptTemplates=Array.isArray(fallback.templates)?fallback.templates.filter(item=>item?.id&&item?.positive):[];
            return {libraries:[{id:'system',name:'系统提示词库',readonly:true,items:builtinPromptTemplates}],builtinPromptTemplates};
        }
        const system=libraries.find(library=>library.id==='system')||libraries[0];
        const builtinPromptTemplates=Array.isArray(system?.items)?system.items.filter(item=>item?.id&&item?.positive):[];
        return {libraries,builtinPromptTemplates};
    }
    function createItem(body){return request('/api/prompt-libraries/items','POST',body,'保存失败');}
    function updateItem(id,body){return request(`/api/prompt-libraries/items/${encodeURIComponent(id)}`,'PATCH',body,'保存失败');}
    function deleteItem(id){return request(`/api/prompt-libraries/items/${encodeURIComponent(id)}`,'DELETE',undefined,'删除失败');}
    function createCategory(body){return request('/api/prompt-libraries/categories','POST',body,'新增分组失败');}
    function updateCategory(id,body){return request(`/api/prompt-libraries/categories/${encodeURIComponent(id)}`,'PATCH',body,'重命名失败');}
    function deleteCategory(id){return request(`/api/prompt-libraries/categories/${encodeURIComponent(id)}`,'DELETE',undefined,'删除失败');}

    global.CanvasPromptTemplateRepository={
        loadLibraries,
        createItem,
        updateItem,
        deleteItem,
        createCategory,
        updateCategory,
        deleteCategory
    };
})(typeof window!=='undefined'?window:globalThis);

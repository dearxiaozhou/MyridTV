/* Prompt-template model: local presets, library mapping and category semantics. */
(function(global){
    'use strict';

    const PRESETS_KEY='smart_canvas_prompt_presets_v1';
    const GROUPS_KEY='smart_canvas_prompt_template_groups_v1';
    const OVERRIDES_KEY='smart_canvas_prompt_template_overrides_v1';
    var deps={getContext:null};
    function configure(opts){Object.assign(deps,opts||{});}
    function context(){return deps.getContext?deps.getContext():{};}
    function defaultGroups(){
        const tr=context().tr||((key)=>key);
        return [
            {id:'view',name:tr('smart.tplCatView')},
            {id:'storyboard',name:tr('smart.tplCatStoryboard')},
            {id:'character',name:tr('smart.tplCatCharacter')},
            {id:'product',name:tr('smart.tplCatProduct')},
            {id:'lighting',name:tr('smart.tplCatLighting')},
            {id:'mine',name:tr('smart.tplCatMine')}
        ];
    }
    function loadPresets(){
        const state=context().state;
        try{
            const list=JSON.parse(localStorage.getItem(PRESETS_KEY)||'[]');
            state.promptPresets=Array.isArray(list)?list.filter(item=>item?.id&&typeof item.text==='string'):[];
        }catch(_){state.promptPresets=[];}
    }
    function savePresets(){localStorage.setItem(PRESETS_KEY,JSON.stringify(context().state.promptPresets));}
    function addPreset(preset){
        context().state.promptPresets.unshift(preset);
        savePresets();
        return preset;
    }
    function updatePreset(id,changes){
        const state=context().state;
        const index=state.promptPresets.findIndex(item=>item.id===id);
        if(index<0) return null;
        state.promptPresets[index]={...state.promptPresets[index],...(changes||{})};
        savePresets();
        return state.promptPresets[index];
    }
    function removePreset(id){
        const state=context().state;
        const removed=state.promptPresets.find(item=>item.id===id)||null;
        state.promptPresets=state.promptPresets.filter(item=>item.id!==id);
        savePresets();
        return removed;
    }
    function movePresetCategory(category,target){
        const state=context().state;
        let moved=0;
        state.promptPresets=state.promptPresets.map(item=>{
            if(item.category!==category) return item;
            moved++;
            return {...item,category:target};
        });
        savePresets();
        return moved;
    }
    function loadGroups(){
        const state=context().state;
        try{
            const list=JSON.parse(localStorage.getItem(GROUPS_KEY)||'[]');
            const valid=Array.isArray(list)?list.filter(group=>group?.id&&group?.name):[];
            const defaults=defaultGroups();
            state.promptTemplateGroups=defaults.map(group=>valid.find(item=>item.id===group.id)||group);
            valid.filter(group=>!state.promptTemplateGroups.some(item=>item.id===group.id)).forEach(group=>state.promptTemplateGroups.push(group));
        }catch(_){state.promptTemplateGroups=defaultGroups();}
    }
    function saveGroups(){localStorage.setItem(GROUPS_KEY,JSON.stringify(context().state.promptTemplateGroups));}
    function loadOverrides(){
        const state=context().state;
        try{
            const data=JSON.parse(localStorage.getItem(OVERRIDES_KEY)||'{}');
            state.promptTemplateOverrides={
                hiddenBuiltinIds:Array.isArray(data.hiddenBuiltinIds)?data.hiddenBuiltinIds:[],
                editedBuiltins:data.editedBuiltins&&typeof data.editedBuiltins==='object'?data.editedBuiltins:{}
            };
        }catch(_){state.promptTemplateOverrides={hiddenBuiltinIds:[],editedBuiltins:{}};}
    }
    function saveOverrides(){localStorage.setItem(OVERRIDES_KEY,JSON.stringify(context().state.promptTemplateOverrides));}
    function activeLibrary(){
        const state=context().state;
        return state.promptLibraries.find(library=>library.id===state.activePromptLibraryId)||state.promptLibraries[0]||
            {id:'system',name:'系统提示词库',readonly:true,items:state.builtinPromptTemplates};
    }
    function items(){
        const state=context().state;
        const library=activeLibrary();
        if(library.id!=='system') return (library.items||[]).filter(item=>item?.id&&item?.positive).map(item=>({
            ...item,sourceId:item.id,builtin:false,remote:true,libraryId:library.id
        }));
        const hidden=new Set(state.promptTemplateOverrides.hiddenBuiltinIds||[]);
        const builtins=state.builtinPromptTemplates.filter(item=>!hidden.has(item.id)).map(item=>({
            ...item,...(state.promptTemplateOverrides.editedBuiltins?.[item.id]||{}),builtin:true
        }));
        const tr=context().tr||((key)=>key);
        const mine=state.promptPresets.map(preset=>({
            id:`mine:${preset.id}`,sourceId:preset.id,name:preset.name||tr('smart.promptPresetUnnamed'),
            category:preset.category||'mine',scene:'我的提示词预设',positive:preset.text||'',negative:'',params:{},builtin:false
        }));
        return [...builtins,...mine];
    }
    function text(template,mode='positive'){
        const positive=String(template?.positive||'').trim();
        if(mode==='positive'||!template?.builtin) return positive;
        const negative=String(template?.negative||'').trim();
        const params=Object.entries(template?.params||{}).map(([key,value])=>`${key}: ${value}`).join('\n');
        return [positive,negative?`Negative prompt:\n${negative}`:'',params?`Params:\n${params}`:''].filter(Boolean).join('\n\n');
    }
    function localized(value,englishKey){
        const item=value||{};
        return global.StudioI18n?.lang?.()==='en'&&item[englishKey]?item[englishKey]:(item.name||'');
    }
    function name(template){return localized(template,'name_en');}
    function scene(template){
        const item=template||{};
        return global.StudioI18n?.lang?.()==='en'&&item.scene_en?item.scene_en:(item.scene||'');
    }
    function searchText(template){
        return [template?.name,template?.name_en,template?.scene,template?.scene_en,template?.positive,template?.negative].join(' ').toLowerCase();
    }
    function mergeGroups(...groupsList){
        const out=[];
        const seen=new Set();
        groupsList.flat().forEach(group=>{
            const id=String(group?.id||'').trim();
            const label=String(group?.name||id).trim();
            if(!id||!label||id==='all'||seen.has(id)) return;
            seen.add(id);
            out.push({...group,id,name:label});
        });
        return out;
    }
    function activeGroups(){
        const state=context().state;
        const library=activeLibrary();
        const backend=Array.isArray(library?.categories)?library.categories.filter(item=>item?.id&&item?.name):[];
        const fromItems=items().map(item=>String(item?.category||'').trim()).filter(id=>id&&id!=='all').map(id=>({id,name:id}));
        if(!library||library.id==='system'){
            const defaults=defaultGroups();
            const defaultIds=new Set(defaults.map(group=>group.id));
            const overrides=state.promptTemplateGroups.filter(group=>defaultIds.has(group.id)&&group.customized);
            const customGroups=state.promptTemplateGroups.filter(group=>!defaultIds.has(group.id));
            const displayedDefaults=defaults.map(group=>{
                const override=overrides.find(item=>item.id===group.id);
                return override?{...group,...override,name:String(override.name||group.name)}:group;
            });
            return mergeGroups(displayedDefaults,customGroups,backend,fromItems);
        }
        return mergeGroups(backend,fromItems);
    }
    function categoryLabel(category){
        const state=context().state;
        const tr=context().tr||((key)=>key);
        if(category==='all') return tr('smart.tplAll');
        const activeName=activeGroups().find(group=>group.id===category)?.name;
        if(activeName&&activeName!==category) return activeName;
        const library=activeLibrary();
        if(library&&library.id!=='system') return activeName||category;
        const builtin={
            view:tr('smart.tplCatView'),storyboard:tr('smart.tplCatStoryboard'),character:tr('smart.tplCatCharacter'),
            product:tr('smart.tplCatProduct'),lighting:tr('smart.tplCatLighting'),mine:tr('smart.tplCatMine')
        };
        return builtin[category]||state.promptTemplateGroups.find(group=>group.id===category)?.name||category;
    }
    function selectedItem(){
        const state=context().state;
        return items().find(item=>item.id===state.promptTemplateSelectedId)||items()[0]||null;
    }
    function currentPreset(id){return context().state.promptPresets.find(preset=>preset.id===id)||null;}
    function defaultPresetName(value){
        const tr=context().tr||((key)=>key);
        return (String(value||'').trim().split(/\r?\n/)[0]||tr('smart.promptPresetDefault')).slice(0,28);
    }

    global.CanvasPromptTemplateModel={
        configure,loadPresets,savePresets,addPreset,updatePreset,removePreset,movePresetCategory,defaultGroups,loadGroups,saveGroups,loadOverrides,saveOverrides,
        activeLibrary,items,text,name,scene,searchText,activeGroups,categoryLabel,selectedItem,currentPreset,defaultPresetName
    };
})(typeof window!=='undefined'?window:globalThis);

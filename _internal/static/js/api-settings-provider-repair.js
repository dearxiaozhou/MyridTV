(function(root, factory){
  if(typeof module !== 'undefined' && module.exports){
    module.exports = factory();
    return;
  }
  root.WcsApiSettingsProviderRepair = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function(){
  function unique(values){
    const seen = new Set();
    const result = [];
    for(const value of values || []){
      const text = String(value || '').trim();
      if(!text || seen.has(text)) continue;
      seen.add(text);
      result.push(text);
    }
    return result;
  }

  function repairProviderModelListsFromDisplayNames(provider){
    if(!provider || typeof provider !== 'object') return provider;
    const displayMap = provider.model_display_names && typeof provider.model_display_names === 'object'
      ? provider.model_display_names
      : {};
    const knownKeys = Object.keys(displayMap).map(key => String(key || '').trim()).filter(Boolean);
    if(!knownKeys.length) return provider;
    provider.image_models = Array.isArray(provider.image_models) ? provider.image_models : [];
    provider.chat_models = Array.isArray(provider.chat_models) ? provider.chat_models : [];
    provider.video_models = Array.isArray(provider.video_models) ? provider.video_models : [];
    if(!provider.image_models.length){
      // 修复显示名时只补「不属于视频/聊天桶」的模型名——纯视频平台（如豆包-SD-2.0）
      // 的别名不得回流进 image_models，否则删掉的视频模型会以"生图模型"身份复活
      const otherBuckets = new Set([...(provider.video_models || []), ...(provider.chat_models || [])]);
      const candidates = knownKeys.filter(key => !otherBuckets.has(key));
      if(candidates.length){
        provider.image_models = unique([...provider.image_models, ...candidates]);
      }
    }
    return provider;
  }

  return {
    repairProviderModelListsFromDisplayNames,
  };
});

(function(root, factory){
  if(typeof module !== 'undefined' && module.exports){
    module.exports = factory();
    return;
  }
  root.WcsApiSettingsPicker = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function(){
  function buildModelPickerState(fetchedIds, existingModels, fetchedSuggestion){
    const ids = Array.from(new Set(Array.isArray(fetchedIds) ? fetchedIds.filter(Boolean) : [])).sort();
    const existing = existingModels || {};
    const existingImage = new Set(Array.isArray(existing.image) ? existing.image : []);
    const existingChat = new Set(Array.isArray(existing.chat) ? existing.chat : []);
    const existingVideo = new Set(Array.isArray(existing.video) ? existing.video : []);
    const suggestion = fetchedSuggestion || {};
    const suggestionImage = suggestion.image instanceof Set ? suggestion.image : new Set(suggestion.image || []);
    const suggestionChat = suggestion.chat instanceof Set ? suggestion.chat : new Set(suggestion.chat || []);
    const suggestionVideo = suggestion.video instanceof Set ? suggestion.video : new Set(suggestion.video || []);
    const category = {};
    const selected = {};
    ids.forEach(id => {
      let cat = 'chat';
      if(suggestionImage.has(id)) cat = 'image';
      else if(suggestionVideo.has(id)) cat = 'video';
      else if(suggestionChat.has(id)) cat = 'chat';
      else if(existingImage.has(id)) cat = 'image';
      else if(existingVideo.has(id)) cat = 'video';
      else if(existingChat.has(id)) cat = 'chat';
      category[id] = cat;
      selected[id] = existingImage.has(id) || existingChat.has(id) || existingVideo.has(id);
    });
    return { ids, category, selected };
  }

  return {
    buildModelPickerState,
  };
});

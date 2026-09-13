(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.WcsRhModelAliases = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  const RH_DEFAULT_MODEL_DISPLAY_NAMES = {
    'rhart-image-g-2/image-to-image': 'RH-G-2-低价图生图',
    'rhart-image-g-2/text-to-image': 'RH-G-2-低价文生图',
    'rhart-image-g-2-official/text-to-image': 'RH-G-2-文生图官方稳定版',
    'rhart-image-g-2-official/image-to-image': 'RH-G-2-图生图官方稳定版',
  };

  const RH_MODEL_VALUE_BY_DISPLAY_NAME = Object.fromEntries(
    Object.entries(RH_DEFAULT_MODEL_DISPLAY_NAMES).map(([model, label]) => [label, model])
  );

  function uniqueStrings(values) {
    const seen = new Set();
    const result = [];
    for (const value of values || []) {
      const text = String(value || '').trim();
      if (!text || seen.has(text)) continue;
      seen.add(text);
      result.push(text);
    }
    return result;
  }

  function isRunningHubLikeProvider(provider) {
    if (!provider || typeof provider !== 'object') return false;
    const id = String(provider.id || '').trim();
    const protocol = String(provider.protocol || '').trim().toLowerCase();
    return id === 'runninghub' || protocol === 'runninghub';
  }

  function canonicalizeRhModelValue(value) {
    const text = String(value || '').trim();
    if (!text) return '';
    if (Object.prototype.hasOwnProperty.call(RH_DEFAULT_MODEL_DISPLAY_NAMES, text)) return text;
    return RH_MODEL_VALUE_BY_DISPLAY_NAME[text] || text;
  }

  function getRhModelValueOptions(values, currentValue) {
    const current = canonicalizeRhModelValue(currentValue);
    const available = uniqueStrings((values || []).map(canonicalizeRhModelValue).filter(Boolean));
    const defaults = Object.keys(RH_DEFAULT_MODEL_DISPLAY_NAMES).filter(
      (model) => model !== current && !available.includes(model)
    );
    return uniqueStrings([current, ...available, ...defaults]);
  }

  function repairProviderRhModelAliases(provider) {
    if (!isRunningHubLikeProvider(provider)) return provider;
    const keys = ['image_models', 'chat_models', 'video_models'];
    keys.forEach((key) => {
      provider[key] = uniqueStrings((provider[key] || []).map(canonicalizeRhModelValue));
    });
    const nextMap = {};
    const rawMap =
      provider.model_display_names && typeof provider.model_display_names === 'object'
        ? provider.model_display_names
        : {};
    Object.entries(rawMap).forEach(([model, label]) => {
      const canonicalModel = canonicalizeRhModelValue(model);
      if (!canonicalModel) return;
      const text =
        String(label || '').trim() || RH_DEFAULT_MODEL_DISPLAY_NAMES[canonicalModel] || '';
      if (text) nextMap[canonicalModel] = text;
    });
    keys.forEach((key) => {
      (provider[key] || []).forEach((model) => {
        if (
          Object.prototype.hasOwnProperty.call(RH_DEFAULT_MODEL_DISPLAY_NAMES, model) &&
          !nextMap[model]
        ) {
          nextMap[model] = RH_DEFAULT_MODEL_DISPLAY_NAMES[model];
        }
      });
    });
    provider.model_display_names = nextMap;
    return provider;
  }

  return {
    RH_DEFAULT_MODEL_DISPLAY_NAMES,
    canonicalizeRhModelValue,
    getRhModelValueOptions,
    isRunningHubLikeProvider,
    repairProviderRhModelAliases,
    uniqueStrings,
  };
});

(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.WcsProviderModelDisplay = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  const RH_DEFAULT_MODEL_DISPLAY_NAMES = {
    'rhart-image-g-2/image-to-image': 'RH-G-2-低价图生图',
    'rhart-image-g-2/text-to-image': 'RH-G-2-低价文生图',
    'rhart-image-g-2-official/text-to-image': 'RH-G-2-文生图官方稳定版',
    'rhart-image-g-2-official/image-to-image': 'RH-G-2-图生图官方稳定版',
  };

  function resolveProviderRecord(providers, providerId) {
    const id = String(providerId || '').trim();
    if (!Array.isArray(providers) || !id) return null;
    return providers.find((provider) => String(provider?.id || '').trim() === id) || null;
  }

  function resolveProviderModelDisplayName(providers, providerId, model) {
    const modelKey = String(model || '').trim();
    if (!modelKey) return '';
    const provider = resolveProviderRecord(providers, providerId);
    const map =
      provider?.model_display_names && typeof provider.model_display_names === 'object'
        ? provider.model_display_names
        : {};
    return String(map[modelKey] || RH_DEFAULT_MODEL_DISPLAY_NAMES[modelKey] || modelKey).trim();
  }

  return {
    resolveProviderModelDisplayName,
    resolveProviderRecord,
  };
});

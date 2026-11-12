(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.WcsProviderModelDisplay = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  // 出厂不含预置模型别名；实际显示名优先取 provider.model_display_names（用户数据）。
  const RH_DEFAULT_MODEL_DISPLAY_NAMES = {};

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

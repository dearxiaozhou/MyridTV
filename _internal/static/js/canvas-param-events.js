/* Canvas parameter controls: bind UI events and update host-owned settings. */
(function (global) {
    'use strict';

    var deps = {
        getContainer: function () { return null; },
        getEngineSelect: function () { return null; },
        getSettings: function () { return {}; },
        closeAllSmartPopovers: function () {},
        renderDynamicParams: function () {},
        setVideoSpecSetting: function () {},
        setImageSpecSetting: function () {},
        setDynamicSetting: function () {},
        syncImageSpecControl: function () {},
        persistActiveSmartSettings: function () {},
        scheduleSave: function () {},
        uploadCurrentSmartVideosToCloud: async function () {},
        setCurrentSmartManualVideoUrl: async function () {},
        currentComfyFields: function () { return []; },
        updateComfySliderValueLabel: function () {},
        toggleSmartComfyRandom: function () {},
        toggleSmartRhRandom: function () {},
        resolveComfyWorkflowName: function () { return ''; },
        tr: function (key) { return key; },
        syncComfyModesChrome: function () {},
        syncComfyDetailsAndParams: function () {},
        getComfyWorkflowCache: function () { return {}; },
        selectedRunningHubRef: function () { return null; },
        runningHubEntryKey: function () { return ''; },
        syncRhNodesChrome: function () {},
        syncRhDetailsAndParams: function () {},
        rhActiveFields: function () { return []; },
        rhParamKey: function () { return ''; },
        rhParamValue: function () { return ''; },
        toast: function () {},
        refreshIcons: function () {}
    };

    function configure(patch) { Object.assign(deps, patch || {}); }
    function settings() { return deps.getSettings ? deps.getSettings() : {}; }

    function handleComfyNodeModeToggle(button, event) {
        if (event) { event.preventDefault(); event.stopPropagation(); }
        var current = settings();
        var workflowName = deps.resolveComfyWorkflowName(current.comfyWorkflow || '');
        if (!workflowName) return;
        current.comfyModes = current.comfyModes || {};
        var nodeId = button.dataset.comfyNodeMode;
        current.comfyModes[workflowName] = current.comfyModes[workflowName] || {};
        var bucket = current.comfyModes[workflowName];
        var wasOff = bucket[nodeId] === 'bypass' || bucket[nodeId] === 'mute';
        if (wasOff) {
            delete bucket[nodeId];
            if (!Object.keys(bucket).length) delete current.comfyModes[workflowName];
        } else bucket[nodeId] = 'bypass';
        var nowOff = !wasOff;
        button.textContent = nowOff ? (deps.tr('smart.comfyOff') || '关') : (deps.tr('smart.comfyOn') || '开');
        button.classList.toggle('on', !nowOff);
        var row = button.closest('.cfm-row');
        if (row) row.classList.toggle('cfm-row-off', nowOff);
        deps.syncComfyModesChrome(workflowName);
        var cache = deps.getComfyWorkflowCache() || {};
        deps.syncComfyDetailsAndParams(cache[workflowName]);
        deps.persistActiveSmartSettings();
        deps.scheduleSave();
        bindDynamicParams();
        deps.refreshIcons();
    }

    function handleRhNodeModeToggle(button, event) {
        if (event) { event.preventDefault(); event.stopPropagation(); }
        var nodeId = String(button && button.dataset && button.dataset.rhNodeMode || '');
        if (!nodeId) return;
        var current = settings();
        var ref = deps.selectedRunningHubRef(current);
        if (!ref || ref.kind !== 'workflow') return;
        var key = deps.runningHubEntryKey(ref.kind, ref.id);
        current.rhNodeOff = current.rhNodeOff && typeof current.rhNodeOff === 'object' ? current.rhNodeOff : {};
        var bucket = current.rhNodeOff[key] && typeof current.rhNodeOff[key] === 'object' ? current.rhNodeOff[key] : {};
        var wasOff = bucket[nodeId] === true;
        if (wasOff) delete bucket[nodeId];
        else bucket[nodeId] = true;
        if (Object.keys(bucket).length) current.rhNodeOff[key] = bucket;
        else delete current.rhNodeOff[key];
        var nowOff = !wasOff;
        button.textContent = deps.tr(nowOff ? 'smart.comfyOff' : 'smart.comfyOn');
        button.title = deps.tr(nowOff ? 'smart.comfyNodeOff' : 'smart.comfyNodeOn');
        button.classList.toggle('on', !nowOff);
        var row = button.closest('.cfm-row');
        if (row) row.classList.toggle('cfm-row-off', nowOff);
        deps.syncRhNodesChrome(ref);
        deps.syncRhDetailsAndParams(ref);
        deps.persistActiveSmartSettings();
        deps.scheduleSave();
        bindDynamicParams();
        deps.refreshIcons();
    }

    function bindDynamicParams() {
        var container = deps.getContainer();
        if (!container) return;
        if (!container.__comfyNodeModeDelegated) {
            container.__comfyNodeModeDelegated = true;
            container.addEventListener('click', function (event) {
                if (event.defaultPrevented) return;
                var button = event.target && event.target.closest && event.target.closest('[data-comfy-node-mode]');
                if (!button || !container.contains(button)) return;
                handleComfyNodeModeToggle(button, event);
            });
        }
        container.querySelectorAll('.smart-control > .smart-pill').forEach(function (pill) {
            pill.onclick = function (event) {
                event.preventDefault(); event.stopPropagation();
                var control = pill.parentElement;
                var wasPinned = control.classList.contains('pinned');
                deps.closeAllSmartPopovers();
                if (wasPinned && control.contains(global.document.activeElement)) global.document.activeElement.blur();
                else pill.focus({ preventScroll: true });
                if (!wasPinned) control.classList.add('pinned');
            };
        });
        container.querySelectorAll('[data-combo-engine]').forEach(function (button) {
            button.onclick = function (event) {
                event.preventDefault(); event.stopPropagation();
                var engine = button.dataset.comboEngine;
                if (engine === settings().engine) return;
                var engineSelect = deps.getEngineSelect();
                if (engineSelect) {
                    engineSelect.value = engine;
                    engineSelect.dispatchEvent(new global.Event('change', { bubbles: true }));
                } else {
                    settings().engine = engine;
                    deps.renderDynamicParams();
                }
                deps.closeAllSmartPopovers();
            };
        });
        if (!global.document.__smartPillToggleDelegated) {
            global.document.__smartPillToggleDelegated = true;
            global.document.addEventListener('click', function (event) {
                var pill = event.target && event.target.closest && event.target.closest('.smart-control > .smart-pill');
                if (!pill || pill.onclick || pill.closest('#dynamicParams') || pill.closest('.composer-reference-mode-slot')) return;
                event.preventDefault();
                var control = pill.parentElement;
                var wasPinned = control.classList.contains('pinned');
                deps.closeAllSmartPopovers();
                if (wasPinned && control.contains(global.document.activeElement)) global.document.activeElement.blur();
                if (!wasPinned) control.classList.add('pinned');
            });
        }
        container.querySelectorAll('[data-smart-param]').forEach(function (button) {
            button.onclick = function (event) {
                event.preventDefault(); event.stopPropagation();
                if (button.closest('.video-spec-control')) { deps.setVideoSpecSetting(button.dataset.smartParam, button.dataset.smartValue); return; }
                if (button.closest('.image-spec-control')) { deps.setImageSpecSetting(button.dataset.smartParam, button.dataset.smartValue); return; }
                deps.setDynamicSetting(button.dataset.smartParam, button.dataset.smartValue);
                if (button.dataset.smartParam === 'videoDuration') deps.renderDynamicParams();
            };
        });
        container.querySelectorAll('[data-param]').forEach(function (input) {
            input.onclick = function (event) { event.stopPropagation(); };
            input.oninput = input.onchange = function (event) {
                if (event && event.stopPropagation) event.stopPropagation();
                if (input.closest('.video-spec-control')) { deps.setVideoSpecSetting(input.dataset.param, input.value); return; }
                deps.setDynamicSetting(input.dataset.param, input.value);
                if (input.closest('.image-spec-control')) deps.syncImageSpecControl();
                if (input.dataset.param === 'videoDuration' && event && event.type === 'change') deps.renderDynamicParams();
            };
        });
        container.querySelectorAll('[data-toggle-param]').forEach(function (button) {
            button.onclick = function (event) {
                event.preventDefault(); event.stopPropagation();
                if (button.closest('.video-spec-control')) { deps.setVideoSpecSetting(button.dataset.toggleParam, ''); return; }
                var current = settings();
                current[button.dataset.toggleParam] = !current[button.dataset.toggleParam];
                if (button.dataset.toggleParam === 'videoMultimodal' && current.videoMultimodal) current.videoUseFrameRoles = false;
                if (button.dataset.toggleParam === 'videoUseFrameRoles' && current.videoUseFrameRoles) current.videoMultimodal = false;
                deps.persistActiveSmartSettings();
                deps.renderDynamicParams();
                deps.scheduleSave();
            };
        });
        container.querySelectorAll('[data-trusted-source]').forEach(function (button) {
            button.onclick = async function (event) {
                event.preventDefault(); event.stopPropagation();
                var source = button.dataset.trustedSource;
                settings().videoTrustedSource = ['library', 'cloud', 'manual'].includes(source) ? source : 'library';
                deps.persistActiveSmartSettings();
                deps.renderDynamicParams();
                deps.scheduleSave();
                try {
                    if (source === 'cloud') await deps.uploadCurrentSmartVideosToCloud();
                    else if (source === 'manual') await deps.setCurrentSmartManualVideoUrl();
                } catch (error) { deps.toast(String(error && error.message || '操作失败').slice(0, 180)); }
            };
        });
        container.querySelectorAll('[data-comfy-bool]').forEach(function (button) {
            button.onclick = function (event) {
                event.preventDefault(); event.stopPropagation();
                var current = settings();
                current.comfyParams = current.comfyParams || {};
                var id = button.dataset.comfyBool;
                var field = deps.currentComfyFields().find(function (item) { return item.id === id; });
                current.comfyParams[id] = !Boolean(current.comfyParams[id] ?? (field && field.default) ?? false);
                deps.persistActiveSmartSettings(); deps.renderDynamicParams(); deps.scheduleSave();
            };
        });
        container.querySelectorAll('[data-comfy-param]').forEach(function (input) {
            input.onclick = function (event) { event.stopPropagation(); };
            input.oninput = input.onchange = function (event) {
                if (event && event.stopPropagation) event.stopPropagation();
                var current = settings();
                current.comfyParams = current.comfyParams || {};
                var field = deps.currentComfyFields().find(function (item) { return item.id === input.dataset.comfyParam; });
                if (field && (field.type === 'number' || field.type === 'slider')) current.comfyParams[input.dataset.comfyParam] = Number(input.value) || 0;
                else current.comfyParams[input.dataset.comfyParam] = input.value;
                if (field && field.type === 'slider') deps.updateComfySliderValueLabel(input, current.comfyParams[input.dataset.comfyParam]);
                deps.persistActiveSmartSettings(); deps.scheduleSave();
            };
        });
        container.querySelectorAll('[data-comfy-node-mode]').forEach(function (button) {
            button.onclick = function (event) { handleComfyNodeModeToggle(button, event); };
        });
        container.querySelectorAll('[data-comfy-pick]').forEach(function (button) {
            button.onclick = function (event) {
                event.preventDefault(); event.stopPropagation();
                var current = settings();
                current.comfyParams = current.comfyParams || {};
                var fieldId = button.dataset.comfyPick;
                var value = button.dataset.comfyValue;
                current.comfyParams[fieldId] = value;
                var popover = button.closest('.smart-popover');
                var control = button.closest('.smart-control');
                var pillSub = control && control.querySelector('.smart-pill .sub');
                if (pillSub) pillSub.textContent = value;
                if (popover) popover.querySelectorAll('[data-comfy-pick="' + fieldId.replace(/"/g, '\\"') + '"]').forEach(function (item) {
                    item.classList.toggle('active', item.dataset.comfyValue === value);
                });
                deps.closeAllSmartPopovers(); deps.persistActiveSmartSettings(); deps.scheduleSave();
            };
        });
        container.querySelectorAll('[data-comfy-random]').forEach(function (button) {
            button.onclick = function (event) { event.preventDefault(); event.stopPropagation(); deps.toggleSmartComfyRandom(button.dataset.comfyRandom); };
        });
        container.querySelectorAll('[data-rh-node-mode]').forEach(function (button) {
            button.onclick = function (event) { handleRhNodeModeToggle(button, event); };
        });
        container.querySelectorAll('[data-rh-bool]').forEach(function (button) {
            button.onclick = function (event) {
                event.preventDefault(); event.stopPropagation();
                var current = settings();
                current.rhParams = current.rhParams || {};
                var key = button.dataset.rhBool;
                var field = deps.rhActiveFields().find(function (item) { return deps.rhParamKey(item.nodeId, item.fieldName) === key; });
                var currentValue = current.rhParams[key] || {};
                var on = String(deps.rhParamValue(field, null)).toLowerCase() === 'true';
                current.rhParams[key] = Object.assign({}, currentValue, { value: String(!on) });
                deps.persistActiveSmartSettings(); deps.renderDynamicParams(); deps.scheduleSave();
            };
        });
        container.querySelectorAll('[data-rh-param]').forEach(function (input) {
            input.onclick = function (event) { event.stopPropagation(); };
            input.oninput = input.onchange = function (event) {
                if (event && event.stopPropagation) event.stopPropagation();
                var current = settings();
                var key = input.dataset.rhParam;
                current.rhParams = current.rhParams || {};
                var currentValue = current.rhParams[key] || {};
                current.rhParams[key] = Object.assign({}, currentValue, { value: input.value });
                var control = input.closest('.smart-control');
                var valueText = control && control.querySelector('.rh-slider-value');
                var pillValue = control && control.querySelector('.rh-slider-pill-value');
                if (valueText) valueText.textContent = input.value;
                if (pillValue) pillValue.textContent = input.value;
                deps.persistActiveSmartSettings(); deps.scheduleSave();
            };
            if (input.dataset.rhType === 'slider') {
                input.onpointerup = function () { input.blur(); };
                input.onmouseleave = function () { if (!input.closest('.smart-control')?.matches(':hover')) input.blur(); };
            }
        });
        container.querySelectorAll('[data-rh-pick]').forEach(function (button) {
            button.onclick = function (event) {
                event.preventDefault(); event.stopPropagation();
                var current = settings();
                var key = button.dataset.rhPick;
                var value = button.dataset.rhValue;
                current.rhParams = current.rhParams || {};
                var currentValue = current.rhParams[key] || {};
                current.rhParams[key] = Object.assign({}, currentValue, { value: value });
                var popover = button.closest('.smart-popover');
                var control = button.closest('.smart-control');
                var pillSub = control && control.querySelector('.smart-pill .sub');
                if (pillSub) pillSub.textContent = value;
                if (popover) popover.querySelectorAll('[data-rh-pick]').forEach(function (item) {
                    if (item.dataset.rhPick === key) item.classList.toggle('active', item.dataset.rhValue === value);
                });
                deps.closeAllSmartPopovers(); deps.persistActiveSmartSettings(); deps.scheduleSave();
            };
        });
        container.querySelectorAll('[data-rh-random]').forEach(function (button) {
            button.onclick = function (event) { event.preventDefault(); event.stopPropagation(); deps.toggleSmartRhRandom(button.dataset.rhRandom); };
        });
    }

    global.CanvasParamEvents = {
        configure: configure,
        bindDynamicParams: bindDynamicParams,
        handleComfyNodeModeToggle: handleComfyNodeModeToggle,
        handleRhNodeModeToggle: handleRhNodeModeToggle
    };
})(typeof window !== 'undefined' ? window : globalThis);

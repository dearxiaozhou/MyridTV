/* Draw the option popup in the app's shared interaction style while keeping
   the native select as the source of truth for existing page behavior. */
(function () {
    'use strict';

    if (window.StudioSelectMenu) return;
    // Agent settings and the engine switch already have their own visible menus.
    // All other single-value selects share this adapter, including dynamic fields.
    const targetSelector = 'select:not([multiple]):not([data-native-select]):not(#engineSelect):not(.agent-select-native):not(#canvasAgentSettingsPanel select)';
    const tracked = new Set();
    let activeState = null;
    let sequence = 0;

    function selectKind(select) {
        if (select.id === 'protocolInput') return 'protocol';
        if (select.matches('.model-value-input.mod-sel')) return 'model';
        if (select.matches('.prompt-llm-provider')) return 'llm-provider';
        if (select.matches('.prompt-llm-model')) return 'llm-model';
        return 'field';
    }

    function selectedOption(select) {
        return select.selectedOptions?.[0] || select.options[select.selectedIndex] || null;
    }

    function selectedLabel(select) {
        return String(selectedOption(select)?.textContent || select.getAttribute('aria-label') || '请选择').trim();
    }

    function syncState(state) {
        if (!state.select.isConnected || !state.button.isConnected) return;
        const label = selectedLabel(state.select);
        if (state.label.textContent !== label) state.label.textContent = label;
        if (state.button.title !== label) state.button.title = label;
        state.button.disabled = state.select.disabled;
        state.wrapper.hidden = state.select.hidden || state.select.style.display === 'none';
        state.button.setAttribute('aria-valuetext', label);
        if (state.select.disabled) state.button.setAttribute('aria-disabled', 'true');
        else state.button.removeAttribute('aria-disabled');
    }

    function closeMenu(restoreFocus = false) {
        if (!activeState) return;
        const state = activeState;
        activeState = null;
        cancelAnimationFrame(state.frame);
        state.menu?.remove();
        state.menu = null;
        state.activeIndex = -1;
        state.button.setAttribute('aria-expanded', 'false');
        state.button.removeAttribute('aria-controls');
        state.button.removeAttribute('aria-activedescendant');
        if (restoreFocus && state.button.isConnected && !state.button.disabled) {
            state.button.focus({ preventScroll: true });
        }
    }

    function enabledOptions(state) {
        return Array.from(state.menu?.querySelectorAll('[role="option"]') || []).filter(option => !option.disabled);
    }

    function setActiveOption(state, index) {
        const options = enabledOptions(state);
        if (!options.length) {
            state.activeIndex = -1;
            state.button.removeAttribute('aria-activedescendant');
            return;
        }
        const next = Math.max(0, Math.min(index, options.length - 1));
        options.forEach((option, i) => option.classList.toggle('keyboard-active', i === next));
        state.activeIndex = next;
        state.button.setAttribute('aria-activedescendant', options[next].id);
        options[next].scrollIntoView({ block: 'nearest' });
    }

    function chooseOption(state, option) {
        if (!option || option.disabled || !state.select.isConnected) return;
        const index = Number(option.dataset.optionIndex);
        if (!Number.isInteger(index) || index < 0 || index >= state.select.options.length) return;
        state.select.selectedIndex = index;
        closeMenu(false);
        syncState(state);
        state.select.dispatchEvent(new Event('change', { bubbles: true }));
        if (state.select.isConnected) syncState(state);
        if (state.button.isConnected && !state.button.disabled) state.button.focus({ preventScroll: true });
    }

    function optionWidth(menu, button, select) {
        const style = getComputedStyle(menu);
        const canvas = document.createElement('canvas');
        const context = canvas.getContext('2d');
        if (!context) return button.getBoundingClientRect().width;
        context.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
        const textWidth = Array.from(select.options).reduce((max, option) => {
            return Math.max(max, context.measureText(String(option.textContent || '').trim()).width);
        }, 0);
        return Math.ceil(textWidth + 64);
    }

    function positionMenu(state) {
        if (activeState !== state || !state.menu) return;
        if (!state.button.isConnected || !state.select.isConnected || state.button.disabled) {
            closeMenu(false);
            return;
        }
        const rect = state.button.getBoundingClientRect();
        if (rect.bottom < 0 || rect.top > innerHeight || rect.right < 0 || rect.left > innerWidth) {
            closeMenu(false);
            return;
        }
        const viewportWidth = document.documentElement.clientWidth || innerWidth;
        const width = Math.min(Math.max(rect.width, optionWidth(state.menu, state.button, state.select)), Math.max(120, viewportWidth - 16));
        const left = Math.max(8, Math.min(rect.left, viewportWidth - width - 8));
        const below = Math.max(0, innerHeight - rect.bottom - 8);
        const above = Math.max(0, rect.top - 8);
        const openAbove = below < Math.min(state.menu.scrollHeight, 280) && above > below;
        const available = openAbove ? above : below;
        state.menu.style.width = `${width}px`;
        state.menu.style.maxHeight = `${Math.max(64, Math.min(320, available || 64))}px`;
        state.menu.style.left = `${left}px`;
        const menuHeight = state.menu.offsetHeight;
        const top = openAbove ? Math.max(8, rect.top - menuHeight - 5) : Math.min(innerHeight - menuHeight - 8, rect.bottom + 5);
        state.menu.style.top = `${Math.max(8, top)}px`;
        state.frame = requestAnimationFrame(() => positionMenu(state));
    }

    function renderMenu(state) {
        const menu = document.createElement('div');
        menu.className = 'shared-native-select-menu';
        menu.id = `shared-native-select-menu-${++sequence}`;
        menu.setAttribute('role', 'listbox');
        menu.setAttribute('aria-label', state.button.getAttribute('aria-label') || '选项');
        Array.from(state.select.options).forEach((nativeOption, index) => {
            const option = document.createElement('button');
            option.type = 'button';
            option.className = 'shared-native-select-option';
            option.id = `${menu.id}-option-${index}`;
            option.setAttribute('role', 'option');
            option.setAttribute('aria-selected', nativeOption.selected ? 'true' : 'false');
            option.dataset.optionIndex = String(index);
            option.disabled = nativeOption.disabled || nativeOption.parentElement?.disabled || state.select.disabled;
            const label = document.createElement('span');
            label.className = 'shared-native-select-option-label';
            label.textContent = String(nativeOption.textContent || '').trim();
            const check = document.createElement('span');
            check.className = 'shared-native-select-option-check';
            check.setAttribute('aria-hidden', 'true');
            check.textContent = nativeOption.selected ? '✓' : '';
            option.append(label, check);
            option.addEventListener('pointerenter', () => {
                const enabled = enabledOptions(state);
                setActiveOption(state, enabled.indexOf(option));
            });
            option.addEventListener('click', event => {
                event.preventDefault();
                event.stopPropagation();
                chooseOption(state, option);
            });
            menu.append(option);
        });
        ['pointerdown', 'mousedown', 'click', 'dblclick', 'wheel'].forEach(type => {
            menu.addEventListener(type, event => event.stopPropagation());
        });
        state.menu = menu;
        state.button.setAttribute('aria-expanded', 'true');
        state.button.setAttribute('aria-controls', menu.id);
        document.body.append(menu);
        const all = Array.from(menu.querySelectorAll('[role="option"]'));
        const selected = all.findIndex(option => option.getAttribute('aria-selected') === 'true' && !option.disabled);
        const first = all.findIndex(option => !option.disabled);
        setActiveOption(state, selected >= 0 ? selected : first);
        positionMenu(state);
    }

    function openMenu(state) {
        if (state.button.disabled) return;
        if (activeState === state) {
            closeMenu(true);
            return;
        }
        closeMenu(false);
        syncState(state);
        activeState = state;
        renderMenu(state);
    }

    function handleKeydown(state, event) {
        if (!state.menu && (event.key === 'ArrowDown' || event.key === 'ArrowUp')) {
            event.preventDefault();
            openMenu(state);
            return;
        }
        if (activeState !== state || !state.menu) return;
        const options = enabledOptions(state);
        if (!options.length) {
            if (event.key === 'Escape') {
                event.preventDefault();
                closeMenu(true);
            }
            return;
        }
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            const step = event.key === 'ArrowDown' ? 1 : -1;
            setActiveOption(state, (state.activeIndex + step + options.length) % options.length);
        } else if (event.key === 'Home' || event.key === 'End') {
            event.preventDefault();
            setActiveOption(state, event.key === 'Home' ? 0 : options.length - 1);
        } else if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            chooseOption(state, options[state.activeIndex]);
        } else if (event.key === 'Escape') {
            event.preventDefault();
            closeMenu(true);
        } else if (event.key === 'Tab') {
            closeMenu(false);
        }
    }

    function enhance(select) {
        if (!(select instanceof HTMLSelectElement) || select.dataset.sharedSelectEnhanced === 'true') return;
        if (!select.matches(targetSelector)) return;
        const parent = select.parentElement;
        if (!parent) return;

        const kind = selectKind(select);
        const computed = getComputedStyle(select);
        const height = Math.max(24, parseFloat(computed.height) || select.offsetHeight || 32);
        const wrapper = document.createElement('div');
        wrapper.className = 'shared-native-select';
        wrapper.dataset.sharedSelectKind = kind;
        wrapper.style.height = `${height}px`;
        wrapper.style.fontFamily = computed.fontFamily;
        wrapper.style.fontSize = computed.fontSize;
        wrapper.style.fontWeight = computed.fontWeight;
        wrapper.style.lineHeight = computed.lineHeight;
        if (kind === 'field') {
            wrapper.style.flex = computed.flex;
            wrapper.style.margin = computed.margin;
            wrapper.style.maxWidth = computed.maxWidth;
        }

        const button = document.createElement('button');
        button.type = 'button';
        button.className = `shared-native-select-trigger shared-native-select-trigger--${kind}`;
        button.setAttribute('role', 'combobox');
        button.setAttribute('aria-haspopup', 'listbox');
        button.setAttribute('aria-expanded', 'false');
        const defaultLabels = { 'llm-provider': 'LLM 平台', 'llm-model': 'LLM 模型', model: '模型', protocol: '协议' };
        button.setAttribute('aria-label', select.getAttribute('aria-label') || select.title || defaultLabels[kind] || '选项');
        button.innerHTML = '<span class="shared-native-select-label"></span><svg class="shared-native-select-caret" viewBox="0 0 16 16" aria-hidden="true"><path d="m4 6 4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"></path></svg>';

        const label = button.querySelector('.shared-native-select-label');
        const state = { select, wrapper, button, label, menu: null, activeIndex: -1, frame: 0 };
        select.dataset.sharedSelectEnhanced = 'true';
        select.dataset.sharedSelectKind = kind;
        select.classList.add('shared-native-select-source');
        select.tabIndex = -1;
        select.setAttribute('aria-hidden', 'true');
        parent.insertBefore(wrapper, select);
        wrapper.append(select, button);
        button.addEventListener('click', event => {
            event.preventDefault();
            event.stopPropagation();
            openMenu(state);
        });
        button.addEventListener('keydown', event => handleKeydown(state, event));
        ['pointerdown', 'mousedown', 'dblclick'].forEach(type => button.addEventListener(type, event => event.stopPropagation()));
        select.addEventListener('change', () => {
            syncState(state);
            if (activeState === state) closeMenu(false);
        });
        tracked.add(state);
        syncState(state);
    }

    function scan(root) {
        if (!root || root.nodeType !== Node.ELEMENT_NODE) return;
        if (root.matches?.(targetSelector)) enhance(root);
        root.querySelectorAll?.(targetSelector).forEach(enhance);
    }

    document.addEventListener('pointerdown', event => {
        if (activeState && !activeState.menu?.contains(event.target) && !activeState.button.contains(event.target)) closeMenu(false);
    }, true);
    window.addEventListener('blur', () => closeMenu(false));
    window.addEventListener('resize', () => {
        if (activeState) positionMenu(activeState);
    });
    window.addEventListener('scroll', () => {
        if (activeState) positionMenu(activeState);
    }, true);

    window.StudioSelectMenu = { scan: () => scan(document.documentElement), close: closeMenu };
    scan(document.documentElement);
    const observer = new MutationObserver(records => {
        records.forEach(record => {
            if (record.type === 'childList') {
                const select = record.target instanceof HTMLSelectElement ? record.target : record.target.closest?.('select');
                const state = select && Array.from(tracked).find(item => item.select === select);
                if (state) {
                    syncState(state);
                    if (activeState === state) closeMenu(false);
                }
                record.addedNodes.forEach(scan);
            }
        });
        if (activeState && (!activeState.select.isConnected || !activeState.button.isConnected)) closeMenu(false);
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });

    const syncTimer = window.setInterval(() => {
        tracked.forEach(state => {
            if (!state.select.isConnected || !state.button.isConnected) {
                if (activeState === state) closeMenu(false);
                tracked.delete(state);
                return;
            }
            syncState(state);
        });
    }, 500);
    window.addEventListener('pagehide', () => {
        observer.disconnect();
        window.clearInterval(syncTimer);
        closeMenu(false);
    }, { once: true });
})();

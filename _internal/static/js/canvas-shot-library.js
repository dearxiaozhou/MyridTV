/* Shares the composer's persisted prompt tokens and overlay lifecycle. */
let shotLibraryCategory = 'light';
let shotLibraryQuery = '';
const SHOT_CATEGORIES = [{id:'light',name:'光影'},{id:'camera',name:'运镜'},{id:'composition',name:'构图'}];
function shotPresetTileHtml(p,activeIds){
    const on=activeIds.includes(p.id);
    const media=p.category==='camera'
        ? `<div class="shot-text-name">${escapeHtml(p.name)}</div><p class="shot-text-description">${escapeHtml(p.description)}</p>`
        : `<img class="style-tile-img" src="${escapeAttr(p.image)}" alt="" loading="lazy" draggable="false"><div class="style-tile-name">${escapeHtml(p.name)}</div>`;
    return `<div class="style-tile shot-preset-tile${p.category==='camera'?' shot-text-card':''}${on?' active':''}" data-shot-option="${p.id}" role="button" tabindex="0" aria-label="${escapeAttr(p.name)}" aria-pressed="${on}" title="${escapeAttr(p.text)}">${media}</div>`;
}
function shotPresetControlHtml(){
    const activeIds = promptInput ? [...promptInput.querySelectorAll('[data-preset-kind="preset"]')].map(t=>t.dataset.styleId) : [];
    const active = promptInput ? [...promptInput.querySelectorAll('[data-preset-kind="preset"]')].length : 0;
    return `<div class="smart-control filter-mode-control shot-mode-control">
        <button class="smart-pill${active ? ' has-value' : ''}" type="button" aria-label="预设" aria-expanded="false"><i data-lucide="clapperboard"></i><span>预设${active ? ' · '+active : ''}</span><i data-lucide="chevron-down" class="pill-caret"></i></button>
        <div class="smart-popover style-popover filter-popover shot-popover">
            <div class="style-popover-head">
                <div class="style-library-categories shot-categories" role="tablist" aria-label="预设分类">${SHOT_CATEGORIES.map(c=>`<button type="button" role="tab" data-shot-category="${c.id}" aria-selected="${c.id===shotLibraryCategory}">${c.name}</button>`).join('')}</div>
                <label class="style-library-search"><i data-lucide="search"></i><input type="search" data-shot-search aria-label="搜索预设" placeholder="搜索预设" value="${escapeAttr(shotLibraryQuery)}"></label>
                <button type="button" class="filter-preset-close" data-shot-close aria-label="关闭预设"><i data-lucide="x"></i></button>
            </div>
            <div class="style-library-results" data-preset-scroll><div class="style-tile-grid">${CanvasShotPresets.presets.map(p=>shotPresetTileHtml(p,activeIds)).join('')}</div><div class="style-library-empty" data-shot-empty hidden>没有匹配的预设</div></div>
        </div>
    </div>`;
}
function bindShotPresetControl(){
    const ctrl = composerStyleModeSlot?.querySelector('.shot-mode-control');
    if(!ctrl) return;
    const pill = ctrl.querySelector(':scope > .smart-pill');
    const pop = ctrl.querySelector('.shot-popover');
    const close = () => {ctrl.classList.remove('pinned'); pill.setAttribute('aria-expanded','false'); if(ctrl.contains(document.activeElement)) document.activeElement.blur();};
    pill.onclick = e => {e.preventDefault();e.stopPropagation();const was=ctrl.classList.contains('pinned');closeAllSmartPopovers();if(was){close();return;}ctrl.classList.add('pinned');pill.setAttribute('aria-expanded','true');positionPresetPopover(ctrl,pop);};
    const filter = () => {
        const q=shotLibraryQuery.trim().toLocaleLowerCase(); let count=0;
        ctrl.querySelector('.style-tile-grid').classList.toggle('shot-text-grid',shotLibraryCategory==='camera');
        ctrl.querySelectorAll('[data-shot-option]').forEach(tile=>{const p=CanvasShotPresets.presets.find(p=>p.id===tile.dataset.shotOption);tile.hidden=p.category!==shotLibraryCategory || (q&&!`${p.name} ${p.text} ${SHOT_CATEGORIES.find(c=>c.id===p.category).name}`.toLocaleLowerCase().includes(q));if(!tile.hidden)count++;});
        ctrl.querySelectorAll('[data-shot-category]').forEach(b=>{const on=b.dataset.shotCategory===shotLibraryCategory;b.classList.toggle('active',on);b.setAttribute('aria-selected',String(on));});
        ctrl.querySelector('[data-shot-empty]').hidden=count>0;ctrl.querySelector('[data-preset-scroll]').scrollTop=0;
    };
    ctrl.querySelector('[data-shot-search]').oninput=e=>{shotLibraryQuery=e.target.value;filter();};
    ctrl.querySelector('[data-shot-close]').onclick=e=>{e.preventDefault();e.stopPropagation();close();};
    ctrl.onkeydown=e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();close();}};
    ctrl.querySelectorAll('[data-shot-category]').forEach(b=>b.onclick=e=>{e.preventDefault();e.stopPropagation();shotLibraryCategory=b.dataset.shotCategory;filter();});
    ctrl.querySelectorAll('[data-shot-option]').forEach(tile=>{tile.onclick=e=>{e.preventDefault();e.stopPropagation();insertStyleToken(CanvasShotPresets.presets.find(p=>p.id===tile.dataset.shotOption));};tile.onkeydown=e=>{if(e.target===tile&&['Enter',' '].includes(e.key)){e.preventDefault();tile.click();}};});
    bindPresetPopoverScroll(pop);filter();
}

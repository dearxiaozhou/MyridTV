/* Blender previsualization controls: isolated composer layout and lens interactions. */
(function (global) {
    'use strict';

    var deps = { getContext: null };
    function configure(patch) { Object.assign(deps, patch || {}); }
    function renderBlenderControls() {
        var context = deps.getContext ? deps.getContext() : {};
        var settings = context.settings;
        if (!settings || settings.engine !== 'blender') return false;
        var dynamicParams = context.dynamicParams;
        var composerStyleModeSlot = context.composerStyleModeSlot;
        var promptInput = context.promptInput;
        var escapeAttr = context.escapeAttr;
        var escapeHtml = context.escapeHtml;
        var renderPrevizLlmControl = context.renderPrevizLlmControl;
        var closeAllSmartPopovers = context.closeAllSmartPopovers;
        var scheduleSave = context.scheduleSave;
        var bindPrevizLlmControl = context.bindPrevizLlmControl;
        var syncEngineSelectOptions = context.syncEngineSelectOptions;
        var document = global.document;
        var window = global;
        var localStorage = global.localStorage;
        var Event = global.Event;
        const ratios = [
            ['wide','16:9 横屏'], ['story','9:16 竖屏'], ['square','1:1 方形'],
            ['portrait43','3:4 竖版'], ['landscape43','4:3 横版'],
            ['ultrawide','21:9 超宽'], ['ultratall','9:21 超高']
        ];
        const cur = ratios.some(r => r[0] === settings.ratio) ? settings.ratio : 'wide';
        // 镜头语言 30 条（值=名称原文，与 assets/blender/previz/camera_language.py 词表一致）
        const lensOptions = [
            ['慢镜头感','拉长情绪与细节，适合回忆、压抑、浪漫。'],
            ['推进 / 慢推','靠近主体，强调“事件正在发生”、心理变化或重要细节。'],
            ['摇镜','固定机位左右转动，交代环境、跟随视线或揭示信息。'],
            ['背景虚化','把注意力锁定到人物，获得电影感与情绪隔离感。'],
            ['低机位','从下往上拍，人物更强势、宏大、有主角感。'],
            ['高机位','从上往下拍，人物更脆弱、孤立，或用于交代空间。'],
            ['浅景深','前后景虚实分明，适合情绪特写、产品与人物突出。'],
            ['中景跟拍','与人物同速移动，最自然地表现行走、生活流和行动。'],
            ['穿梭镜头','镜头穿过人群、物体或场景，增强沉浸和空间纵深。'],
            ['超现实镜头','用不符合现实物理的尺度或运动制造梦境、失序感。'],
            ['希区柯克变焦','推进与反向变焦同时发生，主体大小近似不变、背景变形；适合惊觉与恐惧。'],
            ['转移焦点 / 拉焦','视频标作“变焦点”；焦点从前景切到人物或背景，用于引导观看重点。'],
            ['蒙太奇','以多镜头并置压缩时间、传递情绪或展示变化。'],
            ['慢速拉出','从主体退出并露出环境，适合结尾、孤独感、世界观揭示。'],
            ['冲击变焦','突然快速变焦到主体，突出发现、危机、强烈反应。'],
            ['上摇镜头','固定机位由下向上转动，揭示人物、建筑高度或目标。'],
            ['下摇镜头','由上向下转动，揭示落点、细节或压迫性环境。'],
            ['水平摇镜','横向扫过场景；比横移更像“转头看”，适合信息揭示。'],
            ['横移','摄影机横向移动，产生明显前后景视差；适合展示空间层次。'],
            ['渐进变速横移','横移从慢到快或从快到慢，用于节奏升级和转场。'],
            ['吊臂上升','镜头升高，人物被置入更大的空间，适合开阔、释然、史诗感。'],
            ['吊臂下降','从高处落向人物，强化落点、压迫或情绪收束。'],
            ['正反打','对话双方交替拍摄，保证视线关系和戏剧节奏。'],
            ['鱼眼镜头','超广角畸变，画面夸张、陌生、带街头或梦幻感。'],
            ['第一人称行走','用主观视角前行，代入感最强，适合探索、惊悚与体验内容。'],
            ['遮挡物揭示','先被前景挡住，再移开露出主体；天然形成“发现感”。'],
            ['穿飞镜头','镜头从门、窗、缝隙或物体间飞入/穿出，适合空间转场。'],
            ['前景遮挡转场','让人物、柱子、车等遮满画面后切镜，衔接自然且不突兀。'],
            ['缝隙窥视推进','从栏杆、门缝、前景间慢推，制造观察、秘密或窥探感。'],
            ['180° 环绕','绕主体半圈，展示环境与人物关系，适合人物出场、情绪高点。']
        ];
        const beatOptions = [
            ['跟拍→横移→慢推', '镜头节拍：跟拍[0%-82%]；横移[30%-80%]；慢推[68%-100%]', '人物持续跟随，途中横移展示空间，结尾慢推收近。节拍按镜头时长自动换算。'],
            ['跟拍→慢推收镜', '镜头节拍：跟拍[0%-82%]；慢推[68%-100%]', '持续跟随人物，尾段推进到情绪近景。节拍按镜头时长自动换算。'],
            ['环绕亮相', '镜头节拍：环绕[0%-100%]', '镜头围绕主体运动一周，适合人物或场景亮相。节拍按镜头时长自动换算。'],
            ['横移揭示', '镜头节拍：横移[0%-100%]', '镜头平滑横移，逐步揭开主体与空间关系。节拍按镜头时长自动换算。'],
            ['固定→慢推', '镜头节拍：慢推[0%-100%]', '从稳定构图缓慢靠近主体，适合强调情绪或细节。节拍按镜头时长自动换算。']
        ];
        const compositionOptions = [
            ['环境建立→人物近景落幅', '镜头节拍：跟拍[0%-82%]；慢推[68%-100%] 构图起落幅：起幅[环境建立全景，主体左三分，右侧留白]；落幅[近景，主体右三分，视线左侧留白，头顶留白]', '起幅交代空间并给人物前进方向留白，结尾收近到右三分，保留视线空间与头顶余量。'],
            ['中轴悬念→右三分收束', '镜头节拍：慢推[62%-100%] 构图起落幅：起幅[全景，主体居中，头顶留白]；落幅[近景，主体右三分，视线左侧留白，头顶留白]', '开场稳定居中建立期待，结尾落在右三分并为视线留空间。'],
            ['左三分环境→居中定格', '镜头节拍：横移[0%-70%] 构图起落幅：起幅[全景，主体左三分，右侧留白]；落幅[中景，主体居中，头顶留白]', '开场保留右侧环境信息，横移后收在平衡的中轴构图。'],
            ['大全景→特写情绪落幅', '镜头节拍：慢推[58%-100%] 构图起落幅：起幅[环境建立大全景，主体居中]；落幅[特写，主体左三分，右侧留白，头顶留白]', '从环境建立逐渐推进到情绪特写，结尾留出人物视线方向。'],
            ['三分法跟拍起落幅', '镜头节拍：跟拍[0%-100%] 构图起落幅：起幅[中景，主体左三分，右侧留白，头顶留白]；落幅[中景，主体右三分，视线左侧留白，头顶留白]', '持续跟随动作，让主体从左三分过渡到右三分，开头与结尾都保留安全空间。']
        ];
        // 隐藏 图片/视频 切换按钮
        const toggle = document.getElementById('apiKindToggle');
        if(toggle) toggle.style.display = 'none';
        // Blender 模式：头部固定一行（引擎/视频比例不换行）
        const headEl = document.querySelector('.composer-head');
        if(headEl) headEl.style.flexWrap = 'nowrap';
        // 清理所有残留的比例/资产/镜头语言/LLM 控件（防累积）
        document.querySelectorAll('.blender-ratio-item, .blender-asset-item, .blender-lens-item, .blender-engine-label, .previz-llm-row').forEach(el => el.remove());
        // 3D预演不需要风格按钮：清空风格槽（非 blender 路径会在 renderDynamicParams 末尾重建）
        if(composerStyleModeSlot) composerStyleModeSlot.innerHTML = '';
        // 视频比例 + 镜头语言 + LLM 渲染到 composer 头部（与生成按钮同一排）
        const headLeft = document.querySelector('.composer-head-left');
        if(headLeft){
            headLeft.insertAdjacentHTML('beforeend', `
                <div class="param-item param-ratio blender-ratio-item">
                    <div class="smart-control blender-ratio-control" id="blenderRatioControl">
                        <button class="smart-pill blender-ratio-pill" type="button" title="视频比例：点击打开列表选择" id="blenderRatioPill"><span class="blender-ratio-label"></span><i data-lucide="chevron-down" class="pill-caret"></i></button>
                        <div class="smart-popover blender-ratio-popover">
                            <div class="blender-ratio-list">
                                ${ratios.map(r => `<button type="button" class="blender-ratio-opt ${r[0]===cur?'active':''}" data-ratio-value="${r[0]}" title="${r[1]}"><span class="blender-ratio-opt-name">${r[1]}</span>${r[0]===cur?'<span class="ratio-opt-check">✓</span>':''}</button>`).join('')}
                            </div>
                        </div>
                    </div>
                </div>
                <div class="param-item param-lens blender-lens-item">
                    <div class="smart-control previz-lens-control" id="previzLensControl">
                        <button class="smart-pill previz-lens-pill" type="button" title="${(() => { try { const last = localStorage.getItem('previz_last_lens'); if(last){ const hit = lensOptions.find(l => l[0] === last); return '镜头语言：' + last + (hit ? '（' + hit[1] + '）' : '') + '。点击打开列表重新选择'; } } catch(_){} return '镜头语言：点击打开列表，选中即插入提示词框光标处'; })()}""><i data-lucide="clapperboard"></i><span>镜头语言</span><i data-lucide="chevron-down" class="pill-caret"></i></button>
                        <div class="smart-popover previz-lens-popover">
                            <div class="previz-lens-list">
                                <div class="previz-lens-section">一键运镜节拍 · 自动适配镜头时长</div>
                                ${beatOptions.map(l => `<button type="button" class="previz-lens-opt previz-beat-opt" data-lens-template="true" data-lens-label="${escapeAttr(l[0])}" data-lens-text="${escapeAttr(l[1])}" title="${escapeAttr(l[2])}"><span class="previz-lens-opt-name">${escapeHtml(l[0])}</span></button>`).join('')}
                                <div class="previz-lens-section">电影构图起幅 → 落幅 · 主体位置与景别自动过渡</div>
                                ${compositionOptions.map(l => `<button type="button" class="previz-lens-opt previz-beat-opt" data-lens-template="true" data-lens-label="${escapeAttr(l[0])}" data-lens-text="${escapeAttr(l[1])}" title="${escapeAttr(l[2])}"><span class="previz-lens-opt-name">${escapeHtml(l[0])}</span></button>`).join('')}
                                <div class="previz-lens-section">单项镜头语言</div>
                                ${lensOptions.map(l => `<button type="button" class="previz-lens-opt" data-lens-text="${escapeAttr(l[0])}" title="${escapeAttr(l[1])}"><span class="previz-lens-opt-name">${escapeHtml(l[0])}</span></button>`).join('')}
                            </div>
                        </div>
                    </div>
                </div>
                ${renderPrevizLlmControl()}`);
        }
        dynamicParams.innerHTML = '';
        const ratioCtrl = document.getElementById('blenderRatioControl');
        if(ratioCtrl){
            const ratioPill = ratioCtrl.querySelector('.blender-ratio-pill');
            const ratioLabel = ratioCtrl.querySelector('.blender-ratio-label');
            const setRatioLabel = (val) => {
                const hit = ratios.find(r => r[0] === val);
                if(ratioLabel) ratioLabel.textContent = hit ? hit[1] : val;
            };
            setRatioLabel(cur);
            if(ratioPill) ratioPill.onclick = event => {
                event.preventDefault();
                event.stopPropagation();
                const wasPinned = ratioCtrl.classList.contains('pinned');
                closeAllSmartPopovers();
                if(wasPinned && ratioCtrl.contains(document.activeElement)) document.activeElement.blur();
                if(!wasPinned){
                    ratioCtrl.classList.add('pinned');
                    const pop = ratioCtrl.querySelector('.blender-ratio-popover');
                    if(pop){
                        const need = pop.scrollHeight + 24;
                        const rect = ratioCtrl.getBoundingClientRect();
                        ratioCtrl.classList.toggle('blender-ratio-pop-above', rect.bottom + need > window.innerHeight && rect.top > need);
                    }
                }
            };
            ratioCtrl.querySelectorAll('.blender-ratio-opt').forEach(opt => {
                opt.addEventListener('click', e => {
                    e.preventDefault(); e.stopPropagation();
                    const val = opt.dataset.ratioValue || '';
                    if(!val) return;
                    settings.ratio = val;
                    scheduleSave();
                    setRatioLabel(val);
                    ratioCtrl.querySelectorAll('.blender-ratio-opt').forEach(o => {
                        o.classList.toggle('active', o === opt);
                        const chk = o.querySelector('.ratio-opt-check');
                        if(o === opt && !chk) o.insertAdjacentHTML('beforeend', '<span class="ratio-opt-check">✓</span>');
                        if(o !== opt && chk) chk.remove();
                    });
                    closeAllSmartPopovers();
                });
            });
        }
        const lensCtrl = document.getElementById('previzLensControl');
        if(lensCtrl){
            const pill = lensCtrl.querySelector('.previz-lens-pill');
            if(pill) pill.onclick = event => {
                event.preventDefault();
                event.stopPropagation();
                const wasPinned = lensCtrl.classList.contains('pinned');
                closeAllSmartPopovers();
                if(wasPinned && lensCtrl.contains(document.activeElement)) document.activeElement.blur();
                if(!wasPinned){
                    lensCtrl.classList.add('pinned');
                    const pop = lensCtrl.querySelector('.previz-lens-popover');
                    if(pop){
                        const need = pop.scrollHeight + 24;
                        const rect = lensCtrl.getBoundingClientRect();
                        lensCtrl.classList.toggle('previz-lens-pop-above', rect.bottom + need > window.innerHeight && rect.top > need);
                    }
                }
            };
            lensCtrl.querySelectorAll('.previz-lens-opt').forEach(opt => {
                opt.addEventListener('click', e => {
                    e.preventDefault(); e.stopPropagation();
                    const text = opt.dataset.lensText || '';
                    const label = opt.dataset.lensLabel || text;
                    if(!text) return;
                    if(promptInput){
                        promptInput.focus();
                        if(opt.dataset.lensTemplate === 'true'){
                            const current = promptInput.innerText || promptInput.textContent || '';
                            const cleaned = current.replace(/(?:构图起落幅|起落幅构图)\s*[：:]\s*起幅\s*\[[^\]]+\]\s*[；;，,]\s*落幅\s*\[[^\]]+\]/g, '').replace(/(?:镜头节拍|运镜节拍)\s*[：:]\s*[^\n]*/g, '').trim();
                            promptInput.textContent = cleaned ? `${cleaned} ${text}` : text;
                            const range = document.createRange();
                            range.selectNodeContents(promptInput);
                            range.collapse(false);
                            const sel = window.getSelection();
                            if(sel){ sel.removeAllRanges(); sel.addRange(range); }
                        } else {
                            const sel = window.getSelection();
                            const range = sel && sel.rangeCount && promptInput.contains(sel.anchorNode) ? sel.getRangeAt(0) : null;
                            const node = document.createTextNode(text + ' ');
                            if(range){
                                range.deleteContents();
                                range.insertNode(node);
                                range.collapse(false);
                            } else {
                                promptInput.insertAdjacentHTML('beforeend', escapeHtml(text) + ' ');
                            }
                        }
                        promptInput.dispatchEvent(new Event('input', {bubbles:true}));
                    }
                    // 记录最近一次选中的镜头语言，用于按钮 hover 显示作用说明
                    try{ localStorage.setItem('previz_last_lens', label); }catch(_){}
                    if(pill) pill.title = `镜头语言：${label}（${opt.title || '已插入提示词框'}）。点击打开列表重新选择`;
                    closeAllSmartPopovers();
                });
            });
        }
        bindPrevizLlmControl();
        const rb = document.getElementById('runBtn');
        if(rb){
            rb.querySelector('span').textContent = '生成预演';
            // 按钮往左移：从 run 区（右侧 .composer-actions）挪到 head 区，与比例/资产/镜头语言/LLM 同一排
            const actionsRow = document.querySelector('.composer-actions');
            if(actionsRow) actionsRow.style.display = 'none';
            const headLeft2 = document.querySelector('.composer-head-left');
            // 无条件 appendChild：已存在的子节点会先被移除再追加到末尾，
            // 保证 runBtn 永远排在比例/资产/镜头/LLM 之后（最右），
            // 否则重渲染（点 LLM 等）时 runBtn 残留在前面、新控件追加到末尾导致按钮跑到最左
            if(headLeft2) headLeft2.appendChild(rb);
            rb.style.width = '100px';
            rb.style.minWidth = '0';
            rb.style.marginLeft = 'auto';
            rb.style.height = '26px';
            rb.style.fontSize = '12px';
            rb.style.justifyContent = 'center';
            rb.style.gap = '6px';
            rb.style.borderRadius = '8px';
            rb.style.marginLeft = 'auto';
        }
        // 3D预演 模式隐藏级联运行按钮（不适用）
        const cascadeBtn = document.getElementById('cascadeRunBtn');
        if(cascadeBtn) cascadeBtn.style.display = 'none';
        if(typeof syncEngineSelectOptions === 'function') syncEngineSelectOptions();
        return true;
    }

    global.CanvasPrevizControls = { configure: configure, renderBlenderControls: renderBlenderControls };
})(typeof window !== 'undefined' ? window : globalThis);

/* MyridTV 画布主页背景（2026-10-17 v2 磁盘目录版）
 * 素材来源：assets/home-bg/（用户自己放图片/视频），后端 GET /api/home-bg/list 列目录。
 * 配置极简：localStorage('myridtv_home_bg') = { mode:'fixed'|'carousel', selected:'<文件名>' }
 *  - fixed：显示 selected 指定的单个素材
 *  - carousel：全部素材按序轮播（视频每个最多 5 秒，图片 8 秒）
 * 无 IndexedDB、无保存按钮——点即生效。 */
(function (global) {
  'use strict';

  var CFG_KEY = 'myridtv_home_bg';
  var LIST_API = '/api/home-bg/list';
  var OPEN_FOLDER_API = '/api/open-folder';
  var VIDEO_SLOT_MS = 5000;   // 每个视频最多播 5 秒
  var IMAGE_SLOT_MS = 8000;   // 图片轮播每张 8 秒
  var CARD_ALPHA_DEFAULT = 100;  // 画布卡片默认不透明度（%）：100=不动卡片原样式

  function clampAlpha(v, dflt) {
    var n = parseFloat(v);
    if (!isFinite(n)) return dflt;
    return Math.max(0, Math.min(100, Math.round(n)));
  }

  /* 画布卡片（主页列表里的 .canvas-item）不透明度。100% = 不干预原样式；
   * 否则给每张卡 inline !important 上半透明底色（application-palette.css 等用 !important
   * 给卡片上了 var(--x-card) 底色，纯 CSS 覆盖打不赢，只能 inline 兜底）。
   * 只动 background-color，不动 background 简写——卡内封面图（canvas-card-bg）要保留。
   * ⚠ 2026-10-17 V0.13.22：卡片有「两层底」——.canvas-item 自身 + 主体区
   * .canvas-open（palette L127 `background:var(--x-card)!important` 盖满卡片）。
   * 只改一层另一层实底照样透不出背景（V0.13.15~21 七版无效即因此）。
   * 两层都透时 CSS 背景是**顺序混合**（dst'=src*a+dst*(1-a)），两层同 x 的复合
   * 不透明度 = x+(1-x)*x = 2x-x²（不是 1-(1-x)²！），故每层取 1-√(1-a)，
   * 复合恰为 a，滑块值=观感（实测 50% → 两层 0.293 → 灰底上 (77,78,80)）。
   * has-cover 卡的封面图盖满主体区（内容，不参与透明度），只透卡片自身那层。
   * ⚠ 2026-10-18 V0.13.20：卡片内部还有「第三层」——ID 行 / meta 行
   * （.canvas-card-id-row / .canvas-card-meta，application-palette.css L129
   * `background:var(--x-soft)!important` 实心底）。V0.13.22 只修了卡片两层，
   * 这两条透明卡里嵌死黑条。数学：卡片两层已把复合不透明度精确褪到 a，
   * 标签层再叠任何底都会超出 a（顺序混合单调递增），故此层只能清成全透
   * （inline rgba(0,0,0,0) !important 压过简写的 background-color 部分）。
   * has-cover 卡的这两条是封面图上的白字 scrim（palette L133/L139），
   * 属内容层不参与透明度，skip。
   * ⚠ 2026-10-18 V0.14.5 实测翻转：has-cover 卡的 ID/meta 行**不在封面图上**
   * （截图坐实：封面图只盖上部，两条在图下方无图区）——图片背景下半透明卡上
   * 挂两块 0.74 死黑（CDP 实测：卡片层已 0.294，这两条仍 0.74），即"一用图片
   * 背景就挂"。改为**跟着滑块联动**：scrim alpha = 0.74*a（a=1 时恢复原 0.74，
   * removeProperty），区域复合 = a+0.74a(1-a) ≤ 1，a=0.5 时 0.685——白字有
   * 依托且不再死黑。颜色 21,25,28 = --x-media-overlay-bg 实测 rgb。
   * ⚠ 2026-10-18 V0.14.8：封面卡还有「图片壳」两层——.canvas-card-bg
   * （不透明背景图 inset:0 盖满整卡）+ .canvas-card-bg-shade（渐变）。卡片两层
   * 底色透得再好也被实图压死（CDP：卡片层 0.224、封面图仍 1.0 满盖 337×337），
   * 即"一用图片做背景 transparency 就挂"。滑块 <100% 时图片壳整体 opacity=a
   * 随滑块褪，a=1 removeProperty 恢复；复合 = 页面背景 + a 份封面图。 */
  function applyCardAlpha(alpha) {
    var cards = document.querySelectorAll('#canvasGate .canvas-item, .gate-list .canvas-item');
    if (!cards.length) return;
    var a = clampAlpha(alpha, CARD_ALPHA_DEFAULT) / 100;
    var rgb = isDarkTheme() ? '26, 29, 33' : '255, 255, 255';
    var layer = a >= 1 ? 1 : 1 - Math.sqrt(1 - a);
    var val = 'rgba(' + rgb + ', ' + layer + ')';
    for (var i = 0; i < cards.length; i++) {
      var c = cards[i];
      var open = c.querySelector('.canvas-open');
      var hasCover = !!(open && open.classList.contains('has-cover'));
      var inner = c.querySelectorAll('.canvas-card-id-row, .canvas-card-meta');
      // 封面卡的「图片壳」（V0.14.8）：.canvas-card-bg 是不透明背景图、inset:0
      // 盖满整卡，.canvas-card-bg-shade 是渐变 scrim。卡片底色两层透得再好也被这层
      // 实图压死——"用图片做背景透明度就挂"的根因（CDP 实测：卡片层已 0.224，
      // 封面图仍 1.0 满盖）。滑块 <100% 时让图片壳整体 opacity=a 随滑块褪，
      // a=1 时 removeProperty 恢复原样；无封面图的卡（coverLayers 为空）天然跳过。
      var coverLayers = c.querySelectorAll('.canvas-card-bg, .canvas-card-bg-shade');
      if (a >= 1) {
        c.style.removeProperty('background-color');
        if (open) open.style.removeProperty('background-color');
        for (var j = 0; j < inner.length; j++) inner[j].style.removeProperty('background-color');
        for (var m = 0; m < coverLayers.length; m++) coverLayers[m].style.removeProperty('opacity');
      } else {
        c.style.setProperty('background-color', val, 'important');
        if (open && !hasCover) open.style.setProperty('background-color', val, 'important');
        else if (open) open.style.removeProperty('background-color');
        for (var k = 0; k < inner.length; k++) {
          if (hasCover) {
            // 封面卡：白字 scrim 跟滑块联动（0.74 → 0.74*a），别在半透明卡上死黑
            inner[k].style.setProperty('background-color', 'rgba(21, 25, 28, ' + (0.74 * a) + ')', 'important');
          } else {
            // 非封面卡：卡片两层已把复合不透明度精确褪到 a，此层只能全透
            inner[k].style.setProperty('background-color', 'rgba(0, 0, 0, 0)', 'important');
          }
        }
        // 封面图壳跟着滑块褪：复合 = 页面背景 + a 份封面图，与普通卡的 a 份卡片底色观感一致
        for (var n = 0; n < coverLayers.length; n++) {
          coverLayers[n].style.setProperty('opacity', String(a), 'important');
        }
      }
    }
  }

  function readConfig() {
    try {
      var raw = global.localStorage.getItem(CFG_KEY);
      var cfg = raw ? JSON.parse(raw) : {};
      return {
        mode: cfg.mode === 'carousel' ? 'carousel' : 'fixed',
        selected: typeof cfg.selected === 'string' ? cfg.selected : '',
        // 兼容迁移：V0.13.14 及更早存的字段叫 panelAlpha（当时调的是 gate 整卡），
        // 字段改名 cardAlpha 后读不到会回退默认 100%(不透)，这里把旧值继承过来
        cardAlpha: clampAlpha(cfg.cardAlpha != null ? cfg.cardAlpha : cfg.panelAlpha, CARD_ALPHA_DEFAULT)
      };
    } catch (e) {
      return { mode: 'fixed', selected: '', cardAlpha: CARD_ALPHA_DEFAULT };
    }
  }

  function writeConfig(cfg) {
    try { global.localStorage.setItem(CFG_KEY, JSON.stringify(cfg)); } catch (e) {}
  }

  function fetchList() {
    return fetch(LIST_API, { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : { ok: false, files: [] }; })
      .then(function (data) {
        if (data && data.ok && Array.isArray(data.files)) return data;
        return { ok: false, dir: (data && data.dir) || '', files: [] };
      })
      .catch(function () { return { ok: false, dir: '', files: [] }; });
  }

  function openFolder(dir) {
    try {
      return fetch(OPEN_FOLDER_API, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ local_path: dir })
      }).then(function (r) { return r.json(); }).catch(function () { return { ok: false }; });
    } catch (e) { return Promise.resolve({ ok: false }); }
  }

  /* 当前是否深色主题（供主页卡片底色、配置页预览卡片共用） */
  function isDarkTheme() {
    return document.documentElement.classList.contains('studio-theme-dark')
      || document.body.classList.contains('theme-dark')
      || document.documentElement.classList.contains('theme-dark');
  }

  
  /* 在 container 内渲染背景层（图片/视频 + 固定遮罩 + 轮播）。
   * items: [{name,url,type}]（来自 /api/home-bg/list）
   * opts.contained=true 时定位为 absolute（配置页预览框）；否则 fixed（主页全屏）。
   * 只清理自己创建的 .hb-layer，容器内其他子元素（预览卡片/滑块）不动。
   * 返回 controller.destroy()。 */
  function render(container, cfg, items, opts) {
    opts = opts || {};
    items = items || [];
    var oldLayers = container.querySelectorAll('.hb-layer');
    for (var i = 0; i < oldLayers.length; i++) { oldLayers[i].remove(); }
    if (!items.length) return { destroy: function () {} };

    var layer = document.createElement('div');
    layer.className = 'hb-layer';
    layer.style.position = opts.contained ? 'absolute' : 'fixed';
    if (!opts.contained) layer.style.zIndex = '0';

    var scrim = document.createElement('div');
    scrim.className = 'hb-scrim';
    scrim.style.opacity = '0.30';
    layer.appendChild(scrim);

    var mediaWrap = document.createElement('div');
    mediaWrap.className = 'hb-media';
    layer.appendChild(mediaWrap);

    container.appendChild(layer);

    var timer = null;
    var idx = 0;

    function hasMultipleVideos(list) {
      return list.filter(function (it) { return it.type === 'video'; }).length >= 2;
    }

    function pickStart() {
      if (cfg.selected) {
        var at = -1;
        for (var k = 0; k < items.length; k++) { if (items[k].name === cfg.selected) { at = k; break; } }
        if (at >= 0) return at;
        /* V0.14.7：选中的文件丢了/改名了（如用户改名加前缀）→ 容错匹配救回：
           忽略大小写；配置名是磁盘名的子串也认（f512b503... vs 512b503...）。
           命中就把配置纠正成真实名并写回，否则用户选的图永远不显示。 */
        var want = String(cfg.selected).toLowerCase();
        for (var m = 0; m < items.length; m++) {
          var nm = String(items[m].name).toLowerCase();
          if (nm === want || (want.length >= 8 && nm.indexOf(want) >= 0)) {
            try { cfg.selected = items[m].name; writeConfig(cfg); } catch (e) {}
            return m;
          }
        }
      }
      /* 彻底失联：回落后把生效名写回配置（弹窗高亮/下次启动才对得上） */
      if (items.length && cfg.selected !== items[0].name) {
        try { cfg.selected = items[0].name; writeConfig(cfg); } catch (e) {}
      }
      return 0;
    }

    function clearMedia() { mediaWrap.innerHTML = ''; }

    function showItem(i) {
      var item = items[i];
      if (!item) return;
      clearMedia();
      var el;
      if (item.type === 'video') {
        el = document.createElement('video');
        el.src = item.url; el.autoplay = true; el.muted = true; el.loop = false; el.playsInline = true;
        el.setAttribute('playsinline', ''); el.setAttribute('webkit-playsinline', ''); el.setAttribute('preload', 'auto');
        el.addEventListener('canplay', function () { try { el.play(); } catch (e) {} });
        el.addEventListener('error', function () { console.warn('[home-bg] 视频无法播放（可能缺少解码器）:', item.name); });
        // 5 秒上限：自然播完或到 5s 都切下一个（单视频时头 5 秒循环）
        var advance = function () {
          if (items.length > 1 && (cfg.mode === 'carousel' || hasMultipleVideos(items))) {
            idx = (idx + 1) % items.length; showItem(idx);
          } else {
            try { el.currentTime = 0; el.play(); } catch (e) {}
          }
        };
        el.addEventListener('ended', advance);
        el.addEventListener('timeupdate', function () {
          if (el.currentTime >= VIDEO_SLOT_MS / 1000) { try { el.pause(); } catch (e) {} advance(); }
        });
      } else {
        el = document.createElement('img');
        el.src = item.url; el.alt = '';
      }
      el.className = 'hb-el';
      mediaWrap.appendChild(el);
    }

    function start() {
      if (timer) { clearInterval(timer); timer = null; }
      idx = pickStart();
      showItem(idx);
      if (cfg.mode === 'carousel' && items.length > 1) {
        timer = setInterval(function () {
          idx = (idx + 1) % items.length; showItem(idx);
        }, IMAGE_SLOT_MS);
      }
    }
    start();

    return {
      destroy: function () {
        if (timer) clearInterval(timer);
        clearMedia();
        if (layer.parentNode) layer.parentNode.removeChild(layer);
      }
    };
  }

  /* 画布主页自动应用：检测 #canvasGate，读配置 + 拉目录清单 → 渲染。
   * storage 事件（配置页改了配置）会自动重渲染；同窗兜 1.5s 轮询。 */
  function applyToHomepage() {
    var gate = document.getElementById('canvasGate');
    if (!gate) return;
    var layerHost = document.getElementById('home-bg-layer') || (function () {
      var host = document.createElement('div');
      host.id = 'home-bg-layer';
      document.body.insertBefore(host, document.body.firstChild);
      return host;
    })();

    /* 主页的 gate / shell 被一堆高特异性 !important 规则上了不透明底色
     * （`html body :is(... .canvas-gate ...)`、`html.studio-theme-dark body.prism-canvas-page .canvas-gate`…），
     * 纯 CSS 覆盖打不完这场优先级战争，这里直接用 inline !important 兜底——实测可靠。 */
    var BLOCKERS = null;
    function blockers() {
      if (BLOCKERS) return BLOCKERS;
      var list = [gate];
      var shell = document.getElementById('shell') || document.querySelector('.shell');
      if (shell) list.push(shell);
      var extra = document.querySelectorAll('body.prism-canvas-page .canvas-gate');
      for (var i = 0; i < extra.length; i++) { if (list.indexOf(extra[i]) < 0) list.push(extra[i]); }
      BLOCKERS = list;
      return list;
    }
    function punchThrough(on) {
      blockers().forEach(function (el) {
        if (on) {
          el.style.setProperty('background-color', 'transparent', 'important');
          el.style.setProperty('background-image', 'none', 'important');
        } else {
          el.style.removeProperty('background-color');
          el.style.removeProperty('background-image');
        }
      });
    }

    function refresh() {
      var cfg = readConfig();
      fetchList().then(function (data) {
        var items = data.files || [];
        if (!items.length) {
          layerHost.innerHTML = '';
          gate.classList.remove('home-bg-on');
          document.body.classList.remove('has-home-bg');
          punchThrough(false);
          // 素材清空 → 卡片整体恢复默认。不能只清 .canvas-item 一层：
          // .canvas-open / 标签行 / 封面图壳的 inline 都要撤（V0.14.8）
          applyCardAlpha(100);
          return;
        }
        gate.classList.add('home-bg-on');
        // 主页自带的两团模糊光斑（body::before/::after, z-index:0）会盖在背景层上，先隐掉
        document.body.classList.add('has-home-bg');
        punchThrough(true);
        applyCardAlpha(cfg.cardAlpha);
        render(layerHost, cfg, items, { contained: false });
      });
    }
    refresh();
    // 画布列表由 canvas.js 渲染/重建（进回收站、刷新列表都会重建 DOM），
    // 新卡片插入后立刻补上透明度设置，不用等 1.5s 轮询
    var listEl = document.getElementById('gateCanvasList');
    if (listEl && global.MutationObserver && !global.__homeBgObs) {
      global.__homeBgObs = true;
      try {
        new MutationObserver(function () { applyCardAlpha(readConfig().cardAlpha); })
          .observe(listEl, { childList: true, subtree: true });
      } catch (e) {}
    }
    // 配置变化的三条到达路径（弹窗保存后）：
    // ① 弹窗同源直调（home-background.html notifyHomepage，最可靠）
    // ② 外壳 postMessage 中继（index.html → frame-canvas）
    // ③ storage 事件 / 1.5s 轮询兜底
    global.addEventListener('message', function (e) {
      if (e.data && e.data.type === 'home-bg-config-changed') refresh();
    });
    global.addEventListener('storage', function (e) {
      if (e.key === CFG_KEY) refresh();
    });
    // 关弹窗 / 切回主页标签时补一次（焦点回归双保险）
    global.addEventListener('focus', function () { refresh(); });
    if (!global.__homeBgPoll) {
      global.__homeBgPoll = setInterval(function () {
        try {
          var raw = global.localStorage.getItem(CFG_KEY);
          if (raw !== applyToHomepage.__lastRaw) {
            applyToHomepage.__lastRaw = raw;
            refresh();
          } else {
            // 主题深浅切换、canvas.js 重建列表都会让卡片底色过期：
            // 每轮幂等补设一次（100% 时 removeProperty 无副作用），新卡片立刻吃到透明度
            applyCardAlpha(readConfig().cardAlpha);
          }
        } catch (e) {}
      }, 1500);
    }
    try { applyToHomepage.__lastRaw = global.localStorage.getItem(CFG_KEY); } catch (e) {}
  }

  global.HomeBg = {
    readConfig: readConfig,
    writeConfig: writeConfig,
    fetchList: fetchList,
    openFolder: openFolder,
    render: render,
    applyToHomepage: applyToHomepage,
    isDarkTheme: isDarkTheme,
    applyCardAlpha: applyCardAlpha,
    clampAlpha: clampAlpha,
    CARD_ALPHA_DEFAULT: CARD_ALPHA_DEFAULT,
    VIDEO_SLOT_MS: VIDEO_SLOT_MS,
    IMAGE_SLOT_MS: IMAGE_SLOT_MS
  };

  // 画布主页自动挂载（canvas.html 只引本脚本，真正的入口在这里）
  function boot() {
    try { applyToHomepage(); } catch (e) { console.warn('[home-bg] apply failed', e); }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})(window);

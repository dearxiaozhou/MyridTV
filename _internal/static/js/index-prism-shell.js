(function () {
  const PAGE_META = {
    zimage: {
      label: '文生图',
      kicker: '本地创作',
      title: '文生图工作区',
      desc: '快速进入本地图像生成，适合草图、概念图和高频试错。',
    },
    enhance: {
      label: '细节增强',
      kicker: '本地创作',
      title: '细节增强工作区',
      desc: '用于放大、修复和质感提升，适合在生成结果后继续精修。',
    },
    klein: {
      label: '图片编辑',
      kicker: '本地创作',
      title: '图片编辑工作区',
      desc: '针对局部改图、替换、扩图等操作做集中处理。',
    },
    angle: {
      label: '角度控制',
      kicker: '本地创作',
      title: '角度控制工作区',
      desc: '用于姿态和镜头角度控制，适合前期机位和构图参考。',
    },
    online: {
      label: '在线生图',
      kicker: '云端创作',
      title: '在线生图工作区',
      desc: '接入云端模型和平台能力，适合调用在线生图与视频接口。',
    },
    canvas: {
      label: '无限画布',
      kicker: '主工作区',
      title: '无限画布一级菜单',
      desc: '以本地无限画布为主入口，一站式智能创作中枢。',
    },
    'asset-manager': {
      label: '素材库',
      kicker: '云端创作',
      title: '素材库工作区',
      desc: '集中整理图片、视频、音频和引用素材，服务整个项目流程。',
    },
    'api-settings': {
      label: 'API 设置',
      kicker: '系统配置',
      title: 'API 设置中心',
      desc: '统一管理平台、模型映射、密钥和 Agent 接入配置。',
    },
    'comfyui-settings': {
      label: '工作流设置',
      kicker: '系统配置',
      title: '工作流设置中心',
      desc: '维护 ComfyUI 工作流、节点映射和相关配置入口。',
    },
  };

  function qs(selector, root) {
    return (root || document).querySelector(selector);
  }

  function qsa(selector, root) {
    return Array.from((root || document).querySelectorAll(selector));
  }

  function create(tag, className, html) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (html != null) el.innerHTML = html;
    return el;
  }

  function getVersionText() {
    return qs('.app-version')?.textContent?.trim() || '桌面壳体';
  }

  function getThemeLabel() {
    return document.documentElement.classList.contains('studio-theme-dark') ? '深色模式' : '浅色模式';
  }

  function getLangLabel() {
    const lang = window.StudioI18n?.get?.() || localStorage.getItem('studio_lang') || 'zh-CN';
    return /en/i.test(lang) ? 'EN' : '中文';
  }

  function getDateLabel() {
    try {
      return new Intl.DateTimeFormat('zh-CN', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        weekday: 'long',
      }).format(new Date());
    } catch (error) {
      return '';
    }
  }

  function navIconFor(id) {
    const trigger = qs(`[onclick*="'${id}'"],[onclick*='"${id}"']`);
    return trigger?.querySelector('svg')?.outerHTML || '';
  }

  function goToPage(id) {
    const trigger = qs(`[onclick*="'${id}'"],[onclick*='"${id}"']`);
    if (typeof window.switchUI === 'function' && trigger) {
      window.switchUI(trigger, id);
    }
  }

  function enhanceBrand(sidebar) {
    const logoButton = qs('#sidebarLogoToggle', sidebar);
    const nav = qs('nav', sidebar);
    if (!logoButton || !nav || qs('.prism-brand-card', sidebar)) return;

    logoButton.classList.remove('mb-12');
    logoButton.innerHTML = '<img class="logo-mark" src="/static/images/myrid-icon.svg" alt="MyridTV">';

    const brandCard = create('section', 'prism-brand-card');
    const copy = create('div', 'prism-brand-copy');
    copy.innerHTML = [
      '<img class="prism-brand-wordmark" src="/static/images/wcstv-prism-wordmark.svg" alt="MyridTV">',
      '<div class="prism-brand-subtitle">把本地创作、在线调用、无限画布和工作流配置收拢到一个桌面壳体里。</div>',
      `<div class="prism-brand-status">${getVersionText()}</div>`,
    ].join('');
    brandCard.appendChild(logoButton);
    brandCard.appendChild(copy);
    sidebar.insertBefore(brandCard, nav);
  }

  function buildStageHeader() {
    const header = create('section', 'prism-stage-header');
    header.setAttribute('aria-hidden', 'true');
    header.style.display = 'none';
    return header;
  }

  function enhanceStage(stage) {
    if (qs('.prism-stage-frame', stage)) return;
    const frameWrap = create('div', 'prism-stage-frame');
    const frames = qsa('iframe', stage);
    const header = buildStageHeader();

    stage.insertBefore(header, stage.firstChild);
    stage.appendChild(frameWrap);
    frames.forEach((frame) => frameWrap.appendChild(frame));
  }

  function bindActions(root) {
    qsa('[data-prism-go]', root).forEach((button) => {
      button.addEventListener('click', () => goToPage(button.getAttribute('data-prism-go')));
    });
    qsa('[data-prism-action="theme"]', root).forEach((button) => {
      button.addEventListener('click', () => {
        if (typeof window.toggleTheme === 'function') {
          window.toggleTheme();
          window.setTimeout(syncHeaderState, 30);
        }
      });
    });
  }

  function syncHeaderState(activeId) {
    const resolvedId = activeId || qs('.nav-item.active,[data-prism-go].is-active')?.getAttribute('data-page-id') || localStorage.getItem('studio_active_page') || 'zimage';
    const meta = PAGE_META[resolvedId] || PAGE_META.zimage;
    const kicker = qs('#prismHeroKicker');
    const title = qs('#prismHeroTitle');
    const subtitle = qs('#prismHeroSubtitle');
    const heroMeta = qs('#prismHeroMeta');
    const activeValue = qs('#prismActiveValue');
    const themeValue = qs('#prismThemeValue');
    const langValue = qs('#prismLangValue');
    const dateValue = qs('#prismDateValue');

    if (kicker) kicker.textContent = meta.kicker;
    if (title) title.textContent = meta.title;
    if (subtitle) subtitle.textContent = meta.desc;
    if (heroMeta) {
      heroMeta.innerHTML = `<span class="prism-active-icon">${navIconFor(resolvedId)}</span><span>当前模块：${meta.label}</span>`;
    }
    if (activeValue) activeValue.textContent = meta.label;
    if (themeValue) themeValue.textContent = getThemeLabel();
    if (langValue) langValue.textContent = getLangLabel();
    if (dateValue) dateValue.textContent = getDateLabel();
  }

  function tagNavigation() {
    Object.keys(PAGE_META).forEach((id) => {
      qsa(`[onclick*="'${id}'"],[onclick*='"${id}"']`).forEach((node) => {
        node.setAttribute('data-page-id', id);
      });
    });
  }

  function installSwitchHook() {
    if (window.__prismSwitchHooked || typeof window.switchUI !== 'function') return;
    const original = window.switchUI;
    window.switchUI = function (el, id, options) {
      const result = original.apply(this, arguments);
      window.setTimeout(() => syncHeaderState(id), 0);
      return result;
    };
    window.__prismSwitchHooked = true;
  }

  function enhance() {
    const sidebar = qs('.sidebar');
    const stage = qs('.stage');
    if (!sidebar || !stage) return;
    document.body.classList.add('prism-shell');
    // Myrid HUD shell uses topbar + bottom dock; keep legacy sidebar hidden and avoid injecting old brand card.
    enhanceStage(stage);
    tagNavigation();
    bindActions(document);
    installSwitchHook();
    syncHeaderState(localStorage.getItem('studio_active_page') || 'canvas');
  }

  document.addEventListener('DOMContentLoaded', () => {
    enhance();
    window.setTimeout(syncHeaderState, 80);
  }, { once: true });

  window.addEventListener('studio-theme-change', () => window.setTimeout(syncHeaderState, 10));
})();

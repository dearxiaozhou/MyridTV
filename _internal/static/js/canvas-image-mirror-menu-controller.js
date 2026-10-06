/* Canvas image mirror direction menu.
 *
 * Why this exists: 镜像（flip）是「一次性动作」，不像裁剪/遮罩/画笔要先进图片编辑器
 * 选完再点应用。所以图片工具栏上的「镜像」按钮直接弹这个小菜单选方向，
 * 选完立刻执行，不进编辑器。
 *
 * 菜单是画布自建的 DOM 浮层（不是浏览器原生菜单）：真机跑在 WebView2 里宿主关掉了
 * 系统原生菜单，靠系统菜单的写法在真机上等于什么都不弹。
 */
(function(global){
    'use strict';

    const deps = {runMirror:null, toast:null};
    let state = {nodeId:'', imageIndex:0};

    function configure(options){ Object.assign(deps, options || {}); }

    function menuEl(){ return document.getElementById('smartImageMirrorMenu'); }

    function close(){
        menuEl()?.classList.remove('open');
        state = {nodeId:'', imageIndex:0};
    }

    function isOpen(){ return Boolean(menuEl()?.classList.contains('open')); }

    function ensure(){
        let menu = menuEl();
        if(menu) return menu;
        menu = document.createElement('div');
        menu.id = 'smartImageMirrorMenu';
        menu.className = 'smart-image-mirror-menu';
        // 方向定义：dir 决定水平/垂直翻转，suffix 决定产物文件名后缀
        menu.innerHTML = [
            ['flipX',   'flip-horizontal', '水平镜像', '_mirror_h.png'],
            ['flipY',   'flip-vertical',   '垂直镜像', '_mirror_v.png'],
            ['flipBoth','refresh-cw',       '180° 旋转', '_mirror_180.png']
        ].map(([dir, icon, label]) => `<button type="button" data-mirror-dir="${dir}"><i data-lucide="${icon}"></i><span>${label}</span></button>`).join('');
        // 按下即 preventDefault：避免画布把这次点击当成拖拽/平移起点
        menu.addEventListener('mousedown', event => {
            event.preventDefault();
            event.stopPropagation();
        });
        menu.addEventListener('contextmenu', event => event.stopPropagation());
        menu.addEventListener('click', event => {
            event.preventDefault();
            event.stopPropagation();
            const button = event.target.closest('[data-mirror-dir]');
            if(!button) return;
            const dir = button.dataset.mirrorDir;
            const {nodeId, imageIndex} = state;
            close();
            if(typeof deps.runMirror === 'function') deps.runMirror(nodeId, imageIndex, dir);
        });
        document.body.appendChild(menu);
        return menu;
    }

    // anchor：镜像按钮本身。菜单贴在按钮下方左对齐，并夹在视口内。
    function open(nodeId, imageIndex, anchor){
        if(!nodeId || !anchor) return false;
        const menu = ensure();
        state = {nodeId, imageIndex};
        menu.classList.add('open');
        const rect = anchor.getBoundingClientRect();
        const width = menu.offsetWidth || 148;
        const height = menu.offsetHeight || 126;
        const left = Math.max(12, Math.min(global.innerWidth - width - 12, rect.left));
        const top = Math.max(12, Math.min(global.innerHeight - height - 12, rect.bottom + 4));
        menu.style.left = `${left}px`;
        menu.style.top = `${top}px`;
        // 菜单是后插入 DOM 的，lucide 图标要补渲染一次
        try{ global.lucide?.createIcons?.({attrs:{width:15, height:15}}); }catch(_){}
        return true;
    }

    // 外部点击 / 缩放 / Esc 关闭（自包含，不依赖主文件）
    document.addEventListener('mousedown', event => {
        if(!isOpen()) return;
        if(event.target.closest?.('#smartImageMirrorMenu')) return;
        close();
    }, true);
    window.addEventListener('resize', close);
    document.addEventListener('keydown', event => {
        if(event.key === 'Escape' && isOpen()) close();
    }, true);

    global.CanvasImageMirrorMenuController = {configure, ensure, open, close, isOpen};

    // 浮层注册表一处声明：mousedown / 中键平移 / 空白点击清选中 / 滚轮 都要排除本菜单，
    // 否则点菜单项会被画布当成"点了空白/开始平移"，把节点选中态和菜单一起清掉。
    global.CanvasOverlayRegistry?.register('.smart-image-mirror-menu,#smartImageMirrorMenu', ['overlay', 'pan-exclude', 'click-empty', 'wheel-exclude']);
})(typeof window !== 'undefined' ? window : globalThis);

/* Prompt-based photographic looks. Selecting one replaces the previous filter chip. */
(function(global){
    'use strict';
    const presets=[
        ['ft-none','无','','brightness(.7)'],
        ['ft-kodak','柯达','柯达彩色胶片感调色，温暖自然的肤色，柔和琥珀色高光，丰富中间调，细微银盐颗粒，平滑高光过渡，保持主体和画面结构','sepia(.18) saturate(.9) contrast(1.05)'],
        ['ft-fuji','富士','富士彩色胶片感调色，通透的绿色与青蓝，清爽鲜明的色彩，自然肤色，细腻颗粒，保持主体与现有场景','saturate(1.25) hue-rotate(8deg)'],
        ['ft-ilford','伊尔福','伊尔福黑白胶片感，纯黑白灰阶，丰富中间调与深邃黑位，清晰而自然的明暗反差，细腻银盐颗粒，保留主体细节','grayscale(1) contrast(1.2)'],
        ['ft-cinematic','电影胶片','电影胶片感调色，克制的暖色高光与青色暗部，柔和高光滚降，细微胶片颗粒，统一的电影色彩与层次，保持原有主体和场景','sepia(.2) saturate(.8) contrast(1.1)'],
        ['ft-polaroid','宝丽来','宝丽来即时胶片感调色，柔和反差，奶油色高光，略褪色的暖色，细微颗粒与自然色偏，保持画面构图，不添加相纸边框或文字','sepia(.3) saturate(.65) contrast(.85) brightness(1.08)'],
        ['ft-film-light','电影光效','电影光效，局部柔和光晕，细腻边缘光与有方向的电影布光，层次丰富的明暗过渡，保持人物面部和主体清晰，不新增场景或对象','brightness(1.12) contrast(1.05)'],
        ['ft-hdr','HDR','HDR视觉效果，保留暗部和高光细节，清晰而自然的局部反差，细腻纹理与丰富明暗层次，控制过曝，避免过度锐化和生硬光晕','contrast(1.2) saturate(1.1)'],
        ['ft-soft-focus','柔焦效果','柔焦镜头效果，轻微高光晕染与柔和扩散，平滑而自然的细节过渡，温润肤色，保留主体轮廓和眼睛清晰，不改变构图','blur(.45px) brightness(1.08) contrast(.9)'],
        ['ft-grain','胶片颗粒','细腻均匀的胶片颗粒，轻微模拟胶片纹理，保留清晰的主体细节与原有色彩，不添加划痕、文字或边框','contrast(1.08) saturate(.9)'],
        ['ft-cyberpunk','赛博朋克','赛博朋克调色滤镜，青蓝与品红的冷暖反差，局部霓虹高光与柔和光晕，深色暗部，保持现有主体、服装和场景，不新增建筑或道具','hue-rotate(290deg) saturate(1.55) contrast(1.18)'],
        ['ft-retro','复古色调','复古色调滤镜，柔和暖褐色与略褪色的色彩，抬高暗部，低对比胶片感，细微颗粒，保持主体细节与原有画面结构','sepia(.5) saturate(.7) contrast(.9)']
    ].map(([id,name,text,previewFilter])=>Object.freeze({id,name,text,kind:'filter',image:'/static/images/styles/st-cinematic.webp',previewFilter}));
    global.CanvasFilterPresets=Object.freeze({presets:Object.freeze(presets)});
})(window);

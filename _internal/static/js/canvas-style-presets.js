/* Curated visual directions; prompts work with the selected image or video model. */
(function(global){
    'use strict';
    const categories = global.CanvasStyleCatalog.categories;
    // Keep the original IDs/text for saved references and custom styles.
    const catalog = [
        ['st-cg-realistic','写实CG国漫','material','写实人体皮肤质感，毛孔级次表面散射，CG电影感写实，超写实次世代3D，8K，极致细节，UE5渲染风格，国漫角色造型'],
        ['st-cel-anime','日系赛璐璐','anime','日系动画赛璐璐风格，干净利落的描边，平涂上色，明快色块阴影，动画质感'],
        ['st-ghibli','吉卜力手绘','anime','吉卜力工作室手绘动画风格，柔和水彩质感，温暖色调，细腻自然的背景描绘，治愈系氛围'],
        ['st-cinematic','电影感写实','film','电影感写实风格，柔和胶片调色，浅景深，电影布光，35mm胶片颗粒，高动态范围'],
        ['st-photo-film','胶片摄影','film','胶片摄影风格，Kodak Portra 400色调，自然光，细腻颗粒感，真实皮肤纹理，人像摄影构图'],
        ['st-impasto','厚涂油画','painting','厚涂油画风格，明显的笔触肌理，丰富的色彩层次，画布质感，古典油画光影'],
        ['st-ink-wash','水墨国风','chinese','中国水墨画风格，留白构图，墨色浓淡渐变，宣纸质感，写意笔法，东方意境'],
        ['st-pixel','像素复古','fantasy','像素艺术风格，16bit复古游戏画面，有限的调色板，清晰的像素网格，怀旧游戏氛围'],
        ['st-clay','黏土定格','material','黏土定格动画风格，手工黏土质感，柔和工作室布光，微缩场景，stop-motion质感'],
        ['st-cyber-neon','赛博霓虹','fantasy','赛博朋克风格，霓虹灯光，雨夜街景，蓝紫色调为主，全息投影元素，高对比光效'],
        ['st-flat-minimal','平面极简','painting','扁平极简插画风格，几何化造型，大面积纯色块，无描边，现代平面设计构图'],
        ['st-us-cartoon','美式卡通','anime','美式卡通风格，粗轮廓线，夸张的比例，鲜艳饱和的色彩，Nickelodeon式造型'],

        ['st-real-photo','自然写实','film','真人摄影质感，自然可信的肤色与皮肤细节，真实镜头光学与空间透视，柔和自然光，克制调色，不做插画或卡通化','st-cinematic'],
        ['st-documentary','纪实摄影','film','真人纪实摄影风格，现场环境光，真实生活纹理，朴素而克制的色彩，适度景深，保留自然瑕疵与细节，避免夸张美颜和过度磨皮','st-photo-film','saturate(.65) contrast(.95)'],
        ['st-bw-film','黑白电影','film','真人黑白电影风格，纯黑白灰阶，丰富中间调，方向性布光，细腻银盐胶片颗粒，立体明暗与层次，经典电影质感','st-cinematic','grayscale(1) contrast(1.2)'],
        ['st-hk-retro','港风复古','film','真人港风复古电影质感，暖色高光与青绿暗部，复古胶片颗粒，略带柔焦的高光，浓郁而克制的色彩，真实皮肤与镜头空间','st-photo-film','sepia(.3) saturate(1.2)'],
        ['st-noir','黑色电影','film','真人黑色电影风格，低调布光，深暗阴影与局部高光，高反差黑白灰阶，硬朗侧光，细腻胶片颗粒，悬疑电影质感','st-cinematic','grayscale(1) contrast(1.65) brightness(.8)'],
        ['st-japanese-film','日系清新','film','真人日系清新电影风格，柔和自然光，通透浅色调，轻微胶片颗粒，低对比度，真实且细腻的皮肤质感，安静的生活气息','st-photo-film','saturate(.65) brightness(1.15) contrast(.9)'],

        ['st-gongbi','工笔重彩','chinese','纯2D中国工笔重彩绘画，细致匀净的线描，矿物颜料层层晕染，精密形体与装饰细节，绢本质地，含蓄典雅的传统色彩','st-ink-wash','sepia(.25) saturate(1.4)'],
        ['st-dunhuang','敦煌壁画','chinese','纯2D敦煌壁画美学，赭石与石青石绿配色，流畅舒展的线条，矿物颜料与岁月斑驳壁面质感，装饰性平面构图，古朴庄严','st-impasto','sepia(.35) saturate(.85)'],
        ['st-paper-cut','民俗剪纸','chinese','纯2D民俗剪纸风格，清晰镂空轮廓，连续而简洁的剪刻线条，红纸与浅底的鲜明对比，纸纤维质感，平面装饰性，不使用立体摄影渲染','st-flat-minimal','sepia(.8) hue-rotate(320deg) saturate(2)'],
        ['st-blue-white','青花瓷绘','chinese','纯2D青花瓷绘画风格，钴蓝与瓷白为主，流畅勾线与水分晕染，疏密有致的装饰纹样，温润瓷面质感，典雅清晰','st-ink-wash','grayscale(1) sepia(1) hue-rotate(165deg) saturate(2)'],
        ['st-woodblock','传统版画','chinese','纯2D传统木刻版画风格，明确的黑白或有限套色，刀刻纹理与木版印痕，概括有力的形体，厚重轮廓，手工纸张质感','st-ink-wash','grayscale(1) contrast(1.8)'],
        ['st-ink-anime','水墨动画','chinese','纯2D中国水墨动画风格，写意轮廓，柔和墨色晕染，简洁而有生命力的造型，大面积留白，宣纸纤维，轻盈东方意境，避免写实3D材质','st-ink-wash'],
        ['st-xianxia-cg','仙侠国漫','chinese','纯3D仙侠国漫渲染风格，东方幻想审美，精致立体角色造型，柔和体积光，丝绸与金属的可信材质，细腻皮肤次表面散射，清雅飘逸的色彩','st-cg-realistic','saturate(.8) hue-rotate(10deg)'],

        ['st-guoman-flat','国风平涂','anime','纯2D国风平涂动画，清晰线条与概括造型，东方配色，大面积干净色块，少量明确的色块阴影，平面动画质感，不使用3D写实渲染','st-cel-anime','sepia(.12) saturate(.85)'],
        ['st-cel-painted','赛璐璐半厚涂','anime','纯2D赛璐璐半厚涂动画，明确轮廓与分区色块阴影，局部细腻的手绘笔触和柔和过渡，精致而富有层次的色彩，保持动画造型与平面绘画质感','st-cel-anime'],
        ['st-anime-90s','90年代动画','anime','纯2D九十年代手绘动画，赛璐璐上色，略带手绘起伏的描边，克制的复古配色，细微模拟胶片颗粒，柔和发光，传统动画摄影质感','st-cel-anime','saturate(.7) contrast(.9) sepia(.15)'],
        ['st-american-comic','美漫英雄','anime','纯2D美式英雄漫画，力量感造型，明确的黑色墨线，硬边光影，浓郁对比色与局部网点，富有张力的漫画画面，不使用真人摄影或3D渲染','st-us-cartoon','contrast(1.35) saturate(1.1)'],
        ['st-retro-comic','复古印刷漫画','anime','纯2D复古印刷漫画，有限套色，粗细变化的黑色轮廓线，明显的半色调网点与轻微套印偏移，旧纸质感，经典纸本漫画气息','st-us-cartoon','sepia(.4) saturate(.75)'],

        ['st-watercolor','通透水彩','painting','纯2D水彩绘画，透明颜料叠色，水迹与自然晕染边缘，轻盈笔触，纸张颗粒，明亮而通透的色彩，保留纸面留白','st-ghibli','saturate(.75) brightness(1.1)'],
        ['st-gouache','水粉插画','painting','纯2D水粉插画，不透明颜料色块，柔软而明确的笔触边缘，哑光纸张质感，鲜明而协调的配色，平面绘画层次','st-impasto','saturate(1.25) contrast(.9)'],
        ['st-pencil','铅笔素描','painting','纯2D铅笔素描，石墨灰阶，轻重变化的线条，交叉排线塑造体积，纸张颗粒，保留自然手绘笔触，不做彩色上色','st-ink-wash','grayscale(1) contrast(.8) brightness(1.1)'],
        ['st-line-art','简洁线描','painting','纯2D线描插画，清晰连续的轮廓线，有限的内部结构线，浅色或纯白底，保留充足负空间，几乎不做上色和体积阴影，轻巧干净','st-flat-minimal','grayscale(1) contrast(.8)'],
        ['st-pop-art','波普艺术','painting','纯2D波普艺术，强烈高饱和对比色，粗黑轮廓，半色调圆点，丝网印刷质感，清晰的大色块，醒目的平面视觉节奏','st-us-cartoon','saturate(1.8) contrast(1.25)'],
        ['st-picture-book','童话绘本','painting','纯2D童话绘本插画，圆润亲切的造型，温暖柔和的色彩，手绘彩铅与纸张纹理，柔软线条，细腻富有想象力的画面层次','st-ghibli','sepia(.12) saturate(.8)'],

        ['st-3d-toon','3D卡通动画','material','纯3D卡通动画渲染，圆润立体的角色造型，富有表情的比例，干净材质，柔和全局光照与清晰体积，明快配色，精致动画电影质感','st-clay'],
        ['st-q-figure','Q版手办','material','纯3D Q版手办风格，大头小身比例，简洁可爱的立体造型，精致树脂与哑光涂装材质，清晰柔和的体积光影，细腻微缩模型质感','st-clay','saturate(1.15)'],
        ['st-felt','羊毛毡','material','实体羊毛毡微缩造型风格，蓬松纤维与针毡纹理，柔软圆润的形体，手工制作感，温暖低饱和配色，柔和摄影布光，真实纤维材料而非塑料','st-clay','saturate(.7) contrast(.9)'],
        ['st-low-poly','低多边形','material','纯3D低多边形渲染，清晰可见的三角面与折面边缘，概括的几何形体，有限色板，简洁材质，干净方向光与明暗分面，不使用平滑写实细节','st-flat-minimal'],
        ['st-isometric','等距微缩','material','纯3D等距微缩模型风格，平行投影与清晰等距透视，精致的小型场景造型，柔和环境遮蔽，干净材质，协调低饱和配色，模型沙盘质感','st-clay','saturate(.85)'],
        ['st-paper-craft','立体纸雕','material','实体立体纸雕风格，层叠彩纸与清晰切割边缘，真实纸张纤维和折痕，纸层之间的柔和投影，手工微缩构造，有限而协调的色彩','st-flat-minimal','sepia(.15) saturate(.75)'],

        ['st-steampunk','蒸汽朋克','fantasy','蒸汽朋克幻想美术，黄铜与旧木材质，精密机械结构与手工装饰纹理，暖褐金属色调，方向性柔光，细致的工业复古视觉层次','st-cyber-neon','sepia(.75) saturate(.8) hue-rotate(330deg)'],
        ['st-retro-future','复古未来','fantasy','复古未来主义视觉，模拟时代的圆润工业造型，橙黄与青蓝配色，金属和塑料的复古材质，柔和胶片颗粒，简洁几何构成与怀旧科幻气息','st-cyber-neon','sepia(.25) saturate(.85)'],
        ['st-dark-fantasy','暗黑奇幻','fantasy','暗黑奇幻概念美术，复杂而可信的形体与材质，低饱和深色调，冷暖局部高光，层次分明的厚重暗部，古老神秘的视觉气氛，细腻绘画与电影光影','st-cg-realistic','saturate(.4) brightness(.65) contrast(1.25)'],
        ['st-fairy-fantasy','梦幻童话','fantasy','梦幻童话美术，柔软有机的造型，明亮柔和的粉彩色调，通透光晕与精致装饰纹理，层次轻盈的绘画空间，温暖奇妙的视觉氛围','st-ghibli','saturate(.8) brightness(1.1)'],
        ['st-eastern-fantasy','东方幻想','fantasy','东方幻想概念美术，传统东方线条与现代幻想造型结合，青绿与暖金配色，细腻手绘层次，流畅的装饰节奏与通透空间，庄严而空灵的视觉气息','st-impasto','hue-rotate(20deg) saturate(.85)'],
        ['st-game-concept','游戏概念美术','fantasy','游戏概念设计绘画，结构清晰的造型与材质表达，厚涂笔触结合精确局部细节，明确的光影分组，协调色彩层次，富有设计感的高质量概念美术','st-impasto','contrast(1.15)']
    ].map(([id,name,category,text,preview,previewFilter]) => Object.freeze({id,name,category,text,
        ...(preview ? {image:`/static/images/styles/${preview}.webp`,previewFilter:previewFilter || ''} : {})}));
    catalog.push(Object.freeze({id:'st-2-5d-painted',name:'2.5D厚涂',category:'anime',text:'2.5D厚涂插画，二维手绘造型结合有体积感的光影，细腻渐变与厚涂笔触，概括而清晰的结构，精致色彩层次，保留绘画质感，不做完整真人摄影或写实3D渲染',image:'/static/images/styles/st-impasto.webp'}));
    const presets = global.CanvasStyleCatalog.presets;
    // Hidden entries remain readable by saved canvases but are absent from the menu.
    const archived=catalog;
    global.CanvasStylePresets = Object.freeze({categories:Object.freeze(categories),presets:Object.freeze(presets),archived:Object.freeze(archived)});
})(window);

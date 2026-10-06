/* MyridTV 画布节点注册表（① 节点定义表 + 具名类型化端口）
 *
 * 目的：把"节点类型"从散落在 smart-canvas.js 里的 100+ 处 `node.type === 'xxx'` 收成一张表。
 *  - 一个类型一份定义：标签 / 分类 / 能力标志 / 具名类型化端口
 *  - 判定函数（是否有图片、是否容器…）统一走注册表，不再各写一份字符串比较
 *  - 端口带 dataType（image / video / text / any），为后续"类型化连线校验""无线引用 Set/Get"打底
 *
 * 兼容：历史节点可能没有 type 字段 —— 与既有 isSmartImageNode 行为保持一致，视作图片/生成节点。
 */
(function (global) {
    'use strict';

    var TYPES = Object.create(null);
    var ORDER = [];

    var DEFAULT_FLAGS = {
        hasImages: false,   // 节点带图片/媒体产物（可被引用为素材）
        hasPrompt: false,   // 节点带提示词
        isGenerator: false, // 生成类节点（会跑引擎出图/出视频）
        carriesImages: false, // 节点里能装图片（但不等于"老 isSmartImageNode 认定的图片节点"）
        dropByPointOverlap: false, // 拖拽落点按"指针矩形重叠"判定（提示词/循环节点用的老规则）
        isContainer: false  // 容器节点；是否可连线由该类型自己的端口定义决定
    };

    function normalizeFlags(flags) {
        var out = {};
        Object.keys(DEFAULT_FLAGS).forEach(function (key) {
            out[key] = Boolean(flags && flags[key]) || DEFAULT_FLAGS[key];
        });
        return out;
    }

    function normalizePort(port, direction, index) {
        if (!port || typeof port !== 'object') return null;
        var id = String(port.id || '').trim();
        var label = String(port.label || id).trim();
        var dataType = String(port.dataType || 'any').trim() || 'any';
        if (!id || !label) return null;
        return {
            id: id,
            label: label,
            direction: direction,
            dataType: dataType,
            multiple: port.multiple !== false,
            order: typeof port.order === 'number' ? port.order : index
        };
    }

    function normalizePorts(list, direction) {
        var out = [];
        (Array.isArray(list) ? list : []).forEach(function (port, index) {
            var normalized = normalizePort(port, direction, index);
            if (normalized) out.push(normalized);
        });
        return out;
    }

    function registerNodeType(def) {
        if (!def || !def.type) return null;
        var type = String(def.type).trim();
        if (!type) return null;
        var entry = {
            type: type,
            label: String(def.label || type),
            category: String(def.category || 'other'),
            flags: normalizeFlags(def.flags),
            inputs: normalizePorts(def.inputs, 'input'),
            outputs: normalizePorts(def.outputs, 'output'),
            // 端口的动态写法：def.ports(node) -> {inputs, outputs}，用于按节点状态变化（例如 Comfy 宏节点）
            dynamicPorts: typeof def.ports === 'function' ? def.ports : null,
            defaults: def.defaults && typeof def.defaults === 'object' ? def.defaults : {}
        };
        if (!(type in TYPES)) ORDER.push(type);
        TYPES[type] = entry;
        return entry;
    }

    var IMAGE_TYPE = 'smart-image'; // 历史节点无 type 时的默认归属

    function getNodeType(type) {
        var key = String(type == null ? '' : type).trim();
        if (!key) return TYPES[IMAGE_TYPE] || null;
        return TYPES[key] || null;
    }

    function listNodeTypes() {
        return ORDER.map(function (type) { return TYPES[type]; });
    }

    function nodeTypeHasImages(type) {
        var def = getNodeType(type);
        return Boolean(def && def.flags.hasImages);
    }

    function nodeTypeIsContainer(type) {
        var def = getNodeType(type);
        return Boolean(def && def.flags.isContainer);
    }

    function nodeTypeIsGenerator(type) {
        var def = getNodeType(type);
        return Boolean(def && def.flags.isGenerator);
    }

    function nodeTypeLabel(type) {
        var def = getNodeType(type);
        return def ? def.label : '';
    }

    function nodeTypePorts(type, node) {
        var def = getNodeType(type);
        if (!def) return { inputs: [], outputs: [] };
        if (def.dynamicPorts) {
            try {
                var dynamic = def.dynamicPorts(node || {}) || {};
                return {
                    inputs: normalizePorts(dynamic.inputs || dynamic.input, 'input'),
                    outputs: normalizePorts(dynamic.outputs || dynamic.output, 'output')
                };
            } catch (_) { /* 动态端口出错就退回静态定义 */ }
        }
        return { inputs: def.inputs.slice(), outputs: def.outputs.slice() };
    }

    function nodeTypeDropByPointOverlap(type) {
        var def = getNodeType(type);
        return Boolean(def && def.flags.dropByPointOverlap);
    }

    // 取某个方向上"主端口"的元信息（当前画布每节点单入单出，取顺序第一个）
    function nodePrimaryPort(type, direction) {
        var def = getNodeType(type);
        if (!def) return null;
        var list = direction === 'input' ? def.inputs : def.outputs;
        if (!list.length) return null;
        var port = list[0];
        return { id: port.id, label: port.label, dataType: port.dataType, multiple: port.multiple, count: list.length };
    }

    function labelForNodePort(type, direction) {
        var def = getNodeType(type);
        if (!def) return '';
        var list = direction === 'input' ? def.inputs : def.outputs;
        if (!list.length) return '';
        var head = direction === 'input' ? '输入：' : '输出：';
        return head + list.map(function (port) {
            return port.label + '(' + port.dataType + (port.multiple ? '，可多' : '') + ')';
        }).join('、');
    }

    function describeNode(node) {
        var type = node && node.type;
        var def = getNodeType(type);
        var ports = nodeTypePorts(type, node);
        return {
            type: String(type == null ? '' : type) || IMAGE_TYPE,
            known: Boolean(def),
            label: def ? def.label : '',
            category: def ? def.category : 'unknown',
            flags: def ? def.flags : normalizeFlags(null),
            inputs: ports.inputs,
            outputs: ports.outputs
        };
    }

    // ---------- 内置节点类型（与现有画布节点一一对应）----------
    registerNodeType({
        type: 'smart-image', label: '生成 / 图片节点', category: 'generate',
        flags: { hasImages: true, hasPrompt: true, isGenerator: true },
        inputs: [
            { id: 'in-image', label: '输入图', dataType: 'image', multiple: true },
            { id: 'in-text', label: '提示词', dataType: 'text', multiple: false },
            { id: 'in-audio', label: '音频', dataType: 'audio', multiple: true }
        ],
        outputs: [
            { id: 'out-image', label: '图片', dataType: 'image', multiple: true },
            { id: 'out-video', label: '视频', dataType: 'video', multiple: true },
            { id: 'out-audio', label: '音频', dataType: 'audio', multiple: true }
        ],
        defaults: { w: 320, h: 320 }
    });
    registerNodeType({
        type: 'smart-prompt', label: '提示词', category: 'text',
        flags: { hasPrompt: true, dropByPointOverlap: true },
        inputs: [],
        outputs: [{ id: 'out-text', label: '文本', dataType: 'text', multiple: false }],
        defaults: { w: 340, h: 168 }
    });
    registerNodeType({
        type: 'smart-loop', label: '循环', category: 'control',
        // 注意：hasImages 必须与老 isSmartImageNode 语义一致（loop 不算图片节点），
        // 它"能装图"这件事记在 carriesImages，避免悄悄改变引用/拖放判定
        flags: { hasImages: false, carriesImages: true, dropByPointOverlap: true },
        inputs: [{ id: 'in-image', label: '输入图', dataType: 'image', multiple: true }],
        outputs: [{ id: 'out-image', label: '图片', dataType: 'image', multiple: true }],
        defaults: { w: 340, h: 168 }
    });
    registerNodeType({
        type: 'smart-table', label: '表格', category: 'text',
        flags: {},
        inputs: [{ id: 'in-text', label: '文本', dataType: 'text', multiple: true }],
        outputs: [],
        defaults: {}
    });
    registerNodeType({
        type: 'smart-group', label: '组', category: 'container',
        flags: { isContainer: true, carriesImages: true },
        inputs: [{ id: 'in-image', label: '图片', dataType: 'image', multiple: true }],
        outputs: [{ id: 'out-image', label: '图片', dataType: 'image', multiple: true }],
        defaults: {}
    });

    registerNodeType({
        type:'smart-speech', label:'语音生成', category:'generate',
        flags:{hasImages:true, hasPrompt:false, isGenerator:true},
        inputs:[{id:'in-text', label:'声音描述 / 朗读文本', dataType:'text', multiple:true}],
        outputs:[{id:'out-audio', label:'音频', dataType:'audio', multiple:true}],
        defaults:{w:1000, h:540}
    });
    global.CanvasNodeRegistry = {
        registerNodeType: registerNodeType,
        getNodeType: getNodeType,
        listNodeTypes: listNodeTypes,
        nodeTypeHasImages: nodeTypeHasImages,
        nodeTypeIsContainer: nodeTypeIsContainer,
        nodeTypeIsGenerator: nodeTypeIsGenerator,
        nodeTypeLabel: nodeTypeLabel,
        nodeTypeDropByPointOverlap: nodeTypeDropByPointOverlap,
        nodePrimaryPort: nodePrimaryPort,
        labelForNodePort: labelForNodePort,
        nodeTypePorts: nodeTypePorts,
        describeNode: describeNode,
        IMAGE_TYPE: IMAGE_TYPE,
        DATA_TYPES: ['image', 'video', 'audio', 'text', 'any']
    };
})(typeof window !== 'undefined' ? window : globalThis);

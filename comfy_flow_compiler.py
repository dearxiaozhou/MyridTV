"""ComfyUI 工作流编译器：让画布能在提交前改写工作流图。

为什么需要这个模块
------------------
ComfyUI 后端的 ``POST /prompt`` 接口**不认识**节点上的 ``mode`` 字段。bypass（旁路）
和 mute（禁用）是 ComfyUI **前端 JS 在 graphToPrompt() 里**算出来的：前端把被旁路的
节点从图里摘掉，并把下游的输入重新接到该节点的上游。服务端 execution.py 里搜不到
任何 mode / bypass 逻辑。

所以要在画布上随手开关某个节点，必须在提交前自己把这张图编译一遍。本模块就是这个
编译器：纯函数、不碰网络、可单测。

图的表示
--------
ComfyUI API 格式的 prompt 是一个 dict::

    {"3": {"class_type": "KSampler",
           "inputs": {"model": ["1", 0], "seed": 123, "steps": 20}}}

``inputs`` 里的一条**连线**写作 ``[上游节点 id, 上游输出槽序号]``；其余都是字面量。
判断一条连线靠的是「长度为 2 的 list，第 0 项是字符串且能在图里找到，第 1 项是整数」。

三种节点状态
------------
run     原样保留。
bypass  从图里删掉，下游的连线接到它的上游（按输出类型匹配，递归跳过上游的旁路）。
mute    从图里删掉，并且**级联删掉它所有的下游**——否则下游会留一条指向已消失节点
        的悬空连线，ComfyUI 会直接报错。
"""

from __future__ import annotations

import copy
import json
import re

MODE_RUN = "run"
MODE_BYPASS = "bypass"
MODE_MUTE = "mute"

_VALID_MODES = (MODE_RUN, MODE_BYPASS, MODE_MUTE)


class CompileError(Exception):
    """工作流无法编译成合法 prompt（例如整条输出链被 mute 掉）。"""


def _is_link(value):
    """判断一个 input 值是不是连线 ``[node_id, slot]``。"""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return False
    node_id, slot = value
    return isinstance(node_id, str) and isinstance(slot, int) and not isinstance(slot, bool)


def _node_type(node):
    return str((node or {}).get("class_type") or "").strip()


def _node_inputs(node):
    raw = (node or {}).get("inputs")
    return raw if isinstance(raw, dict) else {}


def _output_types(class_type, object_info):
    """返回一个节点类型按顺序排列的输出类型列表，例如 ['MODEL', 'CLIP', 'VAE']。"""
    info = (object_info or {}).get(class_type)
    if not isinstance(info, dict):
        return []
    outputs = info.get("output")
    if not isinstance(outputs, list):
        return []
    return [str(x) for x in outputs]


def _input_spec(class_type, object_info):
    """合并 required / optional，返回 {输入名: 规格}。"""
    info = (object_info or {}).get(class_type)
    if not isinstance(info, dict):
        return {}
    block = info.get("input")
    if not isinstance(block, dict):
        return {}
    merged = {}
    for group in ("required", "optional"):
        entries = block.get(group)
        if isinstance(entries, dict):
            for key, spec in entries.items():
                merged[str(key)] = spec
    return merged


def _input_type(class_type, input_key, object_info):
    """输入声明的类型。可能是字符串（'INT'）、下拉列表，或类型联合列表。"""
    spec = _input_spec(class_type, object_info).get(input_key)
    if isinstance(spec, list) and len(spec) >= 1:
        head = spec[0]
        if isinstance(head, str):
            return head
        if isinstance(head, list):
            # 联合类型或下拉选项：只有元素是已知的大写类型名才算类型
            names = [str(x) for x in head if isinstance(x, str)]
            if names and all(n.isupper() for n in names):
                return names
            return None  # 下拉选项，不是连线类型
    return None


def _default_value(class_type, input_key, object_info):
    """从规格里猜一个默认值，兜底用。"""
    spec = _input_spec(class_type, object_info).get(input_key)
    if not isinstance(spec, list) or len(spec) < 2:
        return None
    options = spec[1]
    if not isinstance(options, dict):
        return None
    for key in ("default",):
        if key in options:
            return options[key]
    return None


def _required_input_keys(class_type, object_info):
    info = (object_info or {}).get(class_type)
    if not isinstance(info, dict):
        return []
    block = info.get("input")
    if not isinstance(block, dict):
        return []
    entries = block.get("required")
    if not isinstance(entries, dict):
        return []
    return [str(k) for k in entries.keys()]


def normalize_aspect_ratios(workflow, object_info):
    """原地将数字比例补全为该节点唯一匹配的枚举值。"""
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        inputs = _node_inputs(node)
        specs = _input_spec(_node_type(node), object_info)
        for key, value in inputs.items():
            if not isinstance(value, str) or not re.fullmatch(r"\s*\d+\s*:\s*\d+\s*", value):
                continue
            spec = specs.get(key)
            if not isinstance(spec, list) or not spec:
                continue
            choices = spec[0] if isinstance(spec[0], list) else (
                spec[1].get("options", [])
                if spec[0] == "COMBO" and len(spec) > 1 and isinstance(spec[1], dict) else [])
            if not isinstance(choices, list) or value in choices:
                continue
            ratio = re.sub(r"\s+", "", value)
            matches = [option for option in choices if isinstance(option, str)
                       and option.split(" ", 1)[0] == ratio]
            if len(matches) == 1:
                inputs[key] = matches[0]


def _build_reverse_index(workflow):
    """{被引用节点 id: [(下游节点 id, 输入名)]}"""
    index = {}
    for node_id, node in (workflow or {}).items():
        if not isinstance(node, dict):
            continue
        for key, value in _node_inputs(node).items():
            if _is_link(value) and value[0] in workflow:
                index.setdefault(value[0], []).append((str(node_id), str(key)))
    return index


def _downstream_closure(start_nodes, reverse_index):
    """从给定节点出发，沿着连线正向传播，取到所有可达的下游。"""
    seen = set()
    queue = [str(n) for n in start_nodes]
    while queue:
        current = queue.pop()
        if current in seen:
            continue
        seen.add(current)
        for child_id, _key in reverse_index.get(current, []):
            if child_id not in seen:
                queue.append(child_id)
    return seen


def compile_prompt(workflow, overrides=None, modes=None, object_info=None):
    """把「工作流 + 参数覆盖 + 节点开关」编译成最终提交给 ComfyUI 的 prompt。

    :param workflow: ComfyUI API 格式 prompt dict
    :param overrides: ``{node_id: {input_key: value}}``，直接覆盖输入值
    :param modes: ``{node_id: "run" | "bypass" | "mute"}``，缺省视为 run
    :param object_info: ComfyUI ``/object_info`` 的返回值，用于类型匹配
    :returns: ``(prompt, report)``
    """
    source = workflow if isinstance(workflow, dict) else {}
    safe_overrides = overrides if isinstance(overrides, dict) else {}
    safe_modes = modes if isinstance(modes, dict) else {}
    object_info = object_info if isinstance(object_info, dict) else {}

    graph = copy.deepcopy(source)
    report = {
        "bypassed": [],
        "muted": [],
        "overridden": [],
        "rewired": [],
        "warnings": [],
        "missing_types": [],
    }

    # ---- 1. 应用参数覆盖 ----
    for node_id, patch in safe_overrides.items():
        node = graph.get(str(node_id))
        if not isinstance(node, dict) or not isinstance(patch, dict):
            continue
        node.setdefault("inputs", {})
        for key, value in patch.items():
            node["inputs"][str(key)] = value
            report["overridden"].append({"node": str(node_id), "input": str(key)})

    normalize_aspect_ratios(graph, object_info)
    original_graph = copy.deepcopy(graph)

    # ---- 2. 归集节点状态 ----
    bypassed = set()
    muted = set()
    for node_id, mode in safe_modes.items():
        key = str(node_id)
        if key not in graph:
            continue
        normalized = str(mode or "").strip().lower()
        if normalized == MODE_BYPASS:
            bypassed.add(key)
        elif normalized == MODE_MUTE:
            muted.add(key)
        elif normalized and normalized != MODE_RUN:
            report["warnings"].append(f"节点 {key} 的开关值未知（{mode}），按执行处理")

    # ---- 3. mute 级联到所有下游 ----
    reverse_index = _build_reverse_index(graph)
    muted_full = _downstream_closure(muted, reverse_index)
    muted_full |= muted

    # ---- 4. 旁路解析 ----
    # 缓存 resolve 结果，避免多下游重复递归；用 visiting 集合防止图里出现环。
    resolved_cache = {}
    visiting = set()

    def resolve_passthrough(node_id, slot):
        """旁路节点 node_id 的第 slot 个输出，应改接到哪个 [上游, 槽位]。"""
        cache_key = (node_id, slot)
        if cache_key in resolved_cache:
            return resolved_cache[cache_key]
        if cache_key in visiting:
            report["warnings"].append(f"旁路链在节点 {node_id} 处出现环，已停止回溯")
            return None

        node = graph.get(node_id)
        if not isinstance(node, dict):
            return None
        target_types = _output_types(_node_type(node), object_info)
        if slot >= len(target_types):
            report["missing_types"].append(node_id)
            target_type = None
        else:
            target_type = target_types[slot]

        visiting.add(cache_key)
        try:
            fallback = None
            for _key, value in _node_inputs(node).items():
                if not _is_link(value):
                    continue
                upstream_id, upstream_slot = value[0], value[1]
                upstream = graph.get(upstream_id)
                if not isinstance(upstream, dict):
                    continue
                upstream_types = _output_types(_node_type(upstream), object_info)
                if upstream_slot >= len(upstream_types):
                    report["missing_types"].append(upstream_id)
                    upstream_type = None
                else:
                    upstream_type = upstream_types[upstream_slot]
                if target_type is not None and upstream_type == target_type:
                    candidate = (
                        resolve_passthrough(upstream_id, upstream_slot)
                        if upstream_id in bypassed
                        else [upstream_id, upstream_slot]
                    )
                    if candidate is not None:
                        resolved_cache[cache_key] = candidate
                        return candidate
                    fallback = fallback or None
                elif fallback is None and upstream_type is not None:
                    # 类型不完全一致时留个兜底：仍按槽位对槽位透传
                    if upstream_slot == slot:
                        fallback = [upstream_id, upstream_slot]
            if fallback is not None:
                report["warnings"].append(
                    f"节点 {node_id} 旁路时未找到类型完全匹配的上游，按槽位顺序透传"
                )
                resolved_cache[cache_key] = fallback
                return fallback
        finally:
            visiting.discard(cache_key)

        resolved_cache[cache_key] = None
        return None

    # ---- 5. 重写下游连线 ----
    dropped = bypassed | muted_full
    # 改写前的连线表（供 5.5 判断「彻底断粮」）与被切断输入的登记表
    original_links = {}
    for nid, orig_node in graph.items():
        if isinstance(orig_node, dict):
            original_links[str(nid)] = [
                key for key, value in _node_inputs(orig_node).items() if _is_link(value)]
    severed = {}  # node_id -> 被切断的输入名集合（含必填与可选）
    for node_id, node in graph.items():
        if str(node_id) in dropped or not isinstance(node, dict):
            continue
        inputs = _node_inputs(node)
        for key in list(inputs.keys()):
            value = inputs[key]
            if not _is_link(value):
                continue
            upstream_id, slot = value[0], value[1]
            if upstream_id in muted_full:
                replacement = None
            elif upstream_id in bypassed:
                replacement = resolve_passthrough(upstream_id, slot)
            else:
                continue
            if replacement is not None:
                inputs[key] = replacement
                report["rewired"].append({
                    "node": str(node_id),
                    "input": str(key),
                    "from": [upstream_id, slot],
                    "to": replacement,
                })
            else:
                # 没地方可接：尝试用声明的默认值顶上，否则删掉这个输入
                fallback = _default_value(_node_type(node), key, object_info)
                if fallback is not None and not isinstance(fallback, list):
                    inputs[key] = fallback
                    report["warnings"].append(
                        f"节点 {node_id} 的输入 {key} 上游被摘除，已回退到默认值"
                    )
                else:
                    del inputs[key]
                    severed.setdefault(str(node_id), set()).add(str(key))
                    if key in _required_input_keys(_node_type(node), object_info):
                        report["warnings"].append(
                            f"节点 {node_id} 的必填输入 {key} 上游被摘除且无默认值，可能导致执行失败"
                        )
                    else:
                        report["warnings"].append(
                            f"节点 {node_id} 的输入 {key} 上游被摘除，已从 prompt 中移除"
                        )

    # ---- 5.5 级联摘除断供节点 ----
    # bypass/mute 切断连线后，有的下游节点既接不回上游也没有默认值：
    # - 必填输入被切断 → 节点根本无法执行；
    # - 原有的连线输入全部断供（彻底断粮）→ 只会产出 None/垃圾，提交时
    #   ComfyUI 校验放行、执行到一半才炸（典型：吊在被旁路 LoadImage 下面的
    #   缩放/预览节点，在 save_images 的 images[0] 处报
    #   'NoneType' object is not subscriptable）。
    # 这类节点连同下游一起摘除，让主链继续跑；只断掉部分可选输入
    # （如 H3 的 ref_audios、部分 ref_images）的节点仍有存活连线，保持原样。
    dropped_extra = set()
    for nid, keys in severed.items():
        dead_node = graph.get(nid)
        if not isinstance(dead_node, dict):
            continue
        req = set(_required_input_keys(_node_type(dead_node), object_info))
        if keys & req:
            dropped_extra.add(str(nid))
    while True:
        grew = False
        bad = dropped | dropped_extra
        for node_id, node in graph.items():
            key_str = str(node_id)
            if key_str in bad or not isinstance(node, dict):
                continue
            inputs = _node_inputs(node)
            req = set(_required_input_keys(_node_type(node), object_info))
            # 必填连线指向已摘节点 → 活不成
            if any(k in req and _is_link(v) and str(v[0]) in bad
                   for k, v in inputs.items()):
                dropped_extra.add(key_str)
                grew = True
                continue
            # 原有连线全部断供（被切断或指向已摘节点）→ 彻底断粮
            orig = original_links.get(key_str) or []
            if orig:
                live = [
                    value for value in (inputs.get(k) for k in orig)
                    if _is_link(value) and str(value[0]) not in bad]
                if not live:
                    dropped_extra.add(key_str)
                    grew = True
        if not grew:
            break
    dropped |= dropped_extra
    if dropped_extra:
        report["cascaded_dropped"] = sorted(dropped_extra)
        report["warnings"].append(
            "有 {} 个节点的输入因上游被旁路/禁用而断供，已随本层级联摘除：{}".format(
                len(dropped_extra), ", ".join(sorted(dropped_extra))))
    # 级联后仍存活的节点若还挂着指向已摘节点的连线（只可能是可选输入），
    # 把悬空线摘掉，免得 ComfyUI 报「指向不存在的节点」。
    for node_id, node in graph.items():
        if str(node_id) in dropped or not isinstance(node, dict):
            continue
        inputs = _node_inputs(node)
        for key in list(inputs.keys()):
            value = inputs[key]
            if _is_link(value) and str(value[0]) in dropped:
                del inputs[key]
                report["warnings"].append(
                    f"节点 {node_id} 的输入 {key} 指向已被摘除的节点，连线已移除")

    # ---- 6. 摘掉被关闭的节点 ----
    compiled = {
        node_id: node
        for node_id, node in graph.items()
        if str(node_id) not in dropped and isinstance(node, dict)
    }
    report["bypassed"] = sorted(bypassed)
    report["muted"] = sorted(muted_full)

    _protect_media_output_chains(original_graph, compiled, safe_modes, object_info)
    if not compiled:
        raise CompileError("工作流里所有节点都被关闭了，没有可提交的内容")
    if not any(str(n) in compiled for n in _output_node_ids(compiled, object_info)):
        if _output_node_ids(source, object_info):
            raise CompileError("节点关闭后没有可执行的输出。请开启保存/预览节点及其必需的上游输入，再运行。")
        report["warnings"].append("工作流没有识别到输出节点，请检查保存/预览节点")

    return compiled, report


def _output_node_ids(workflow, object_info):
    """Use ComfyUI's output declaration, including custom and connected outputs."""
    output_ids = []
    for node_id, node in (workflow or {}).items():
        if not isinstance(node, dict):
            continue
        class_type = _node_type(node)
        info = (object_info or {}).get(class_type) or {}
        is_output = info.get("output_node") if "output_node" in info else class_type.startswith(("Save", "Preview"))
        if is_output:
            output_ids.append(str(node_id))
    return output_ids


def _protect_media_output_chains(source, compiled, modes, object_info):
    """Reject missing media that silently removes a final output, even if others survive.

    Never restore a missing media loader's bundled filename: it may be invalid or
    belong to another project. Optional reference/preview branches may disappear.
    """
    outputs = _output_node_ids(source, object_info)
    final_outputs = [nid for nid in outputs if not _node_type(source[nid]).startswith("Preview")]
    final_outputs = final_outputs or outputs
    lost = {nid for nid in final_outputs if nid not in compiled and
            str(modes.get(nid, "run")).lower() not in (MODE_BYPASS, MODE_MUTE)}
    if not lost:
        return
    reverse = _build_reverse_index(source)
    failures = []
    for nid, mode in modes.items():
        nid = str(nid)
        node = source.get(nid)
        if str(mode).lower() not in (MODE_BYPASS, MODE_MUTE) or not isinstance(node, dict):
            continue
        kind = _node_type(node)
        types = _output_types(kind, object_info)
        media_source = kind.startswith(("LoadImage", "LoadAudio", "LoadVideo", "VHS_LoadVideo")) or (
            any(t in ("IMAGE", "AUDIO", "VIDEO", "VHS_VIDEO") for t in types)
            and not any(_is_link(v) for v in _node_inputs(node).values())
            and any(k in _node_inputs(node) for k in ("image", "audio", "video", "file", "path")))
        if not media_source:
            continue
        # Breadth-first dependency path gives an actionable explanation.
        queue = [(nid, [nid])]
        visited = {nid}
        for current, path in queue:
            if current in lost:
                labels = []
                for key in path:
                    n = source[key]
                    title = (n.get("_meta") or {}).get("title") or _node_type(n)
                    labels.append(f"#{key} {title}")
                failures.append(" → ".join(labels))
                break
            for child, _input in sorted(reverse.get(current, ())):
                if child not in visited:
                    visited.add(child)
                    queue.append((child, path + [child]))
    if failures:
        raise CompileError(
            "无法安全裁剪缺少的媒体输入：它还被生成主链使用，关闭后会丢失输出。"
            "请补充以下输入，或调整工作流使生成尺寸和主链不依赖该空槽位；"
            "不会使用工作流自带的默认素材代替。依赖链：" + "；".join(failures))


def describe_workflow(workflow, object_info=None, prefs=None):
    """把工作流拆成卡片要展示的节点清单。

    :returns: 节点列表，每项含 id / class_type / title / category / 是否输出节点 /
              是否被引用。prefs 可传 ``{node_id: {name, hidden, collapsed}}`` 做轻量覆盖。
    """
    source = workflow if isinstance(workflow, dict) else {}
    object_info = object_info if isinstance(object_info, dict) else {}
    prefs = prefs if isinstance(prefs, dict) else {}
    referenced = set()
    for node in source.values():
        if not isinstance(node, dict):
            continue
        for value in _node_inputs(node).values():
            if _is_link(value):
                referenced.add(value[0])
    output_ids = set(_output_node_ids(source, object_info))

    items = []
    for node_id in sorted(source.keys(), key=lambda x: _safe_int(x)):
        node = source.get(node_id)
        if not isinstance(node, dict):
            continue
        class_type = _node_type(node)
        info = object_info.get(class_type) or {}
        meta_title = str(((node.get("_meta") or {}).get("title") or "")).strip()
        pref = prefs.get(str(node_id)) if isinstance(prefs.get(str(node_id)), dict) else {}
        items.append({
            "id": str(node_id),
            "class_type": class_type,
            "title": str(pref.get("name") or meta_title or info.get("display_name") or class_type),
            "category": str(info.get("category") or ""),
            "is_output": str(node_id) in output_ids,
            "is_referenced": str(node_id) in referenced,
            "hidden": bool(pref.get("hidden")),
            "collapsed": bool(pref.get("collapsed")),
        })
    return items


def _safe_int(value):
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 1 << 30


def load_json_file(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)

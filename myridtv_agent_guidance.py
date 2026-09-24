# -*- coding: utf-8 -*-
"""MyridTV Agent 提示词引导族（后端拆分第17刀）：消息清洗、工具纪律注入、
系统段拼装、回复规则/头脑风暴/候选交互三段引导文案生成。

逐字迁移自 rh_official_proxy.py 连续块 L(_agent_sanitize_messages)..
L(_codex_bridge_attachment_files)（6 函数 156 行，可逆还原行级 diff=0）。
行为零变更。闭包全自含（零外依赖/零全局/零 stdlib），故无 configure 注入。
主文件对被仍引用的 6 函数留同名薄代理。
"""

def _agent_sanitize_messages(messages):
    out = []
    for m in messages:
        content = m.get("content")
        if isinstance(content, list):
            # 2026-09-23 修「Agent 读图失明」真根因：旧逻辑把 image_url 块压平成
            # "[图片: data:base64…]" 纯文本再发上游——模型收到的是一墙 base64 字符，
            # 只能瞎猜。多模态消息必须保留 OpenAI parts 结构原样透传；
            # 仅当整条消息没有图片块时才压回纯文本（兼容旧路径）。
            has_image = False
            blocks = []
            texts = []
            def flush_texts():
                if texts:
                    joined = "\n".join(t for t in texts if t)
                    if joined.strip():
                        blocks.append({"type": "text", "text": joined})
                    texts.clear()
            for block in content:
                if isinstance(block, dict) and block.get("type") == "image_url":
                    url = block.get("image_url")
                    url = str((url.get("url") if isinstance(url, dict) else url) or "").strip()
                    if url:
                        flush_texts()
                        has_image = True
                        blocks.append({"type": "image_url", "image_url": {"url": url}})
                elif isinstance(block, dict) and block.get("type") == "text":
                    texts.append(str(block.get("text") or ""))
                else:
                    texts.append(str(block))
            flush_texts()
            m = dict(m)
            m["content"] = blocks if has_image else "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        # 协议防御：OpenAI 兼容上游会拒绝 assistant 消息携带空 tool_calls 数组
        # (400 invalid_parameter_error: Empty tool_calls is not supported in message)。
        # 历史存档会话里可能已存下 "tool_calls": [] 的坏消息，这里统一剔除，
        # 保证每轮发出去的 messages 都符合协议。
        if m.get("role") == "assistant" and "tool_calls" in m and not m.get("tool_calls"):
            m = dict(m)
            m.pop("tool_calls", None)
        out.append(m)
    return out


def _agent_inject_tool_guidance(messages, preset=None):
    guidance = ("\n\n## 画布工具\n"
                "你可以调用工具直接在画布上工作:canvas_get_state 查看画布;canvas_search_nodes 搜索素材;"
                "对话中【引用图片】开头的文字就是后台视觉模型(GLM)对图片的识别描述,直接把它当作图片内容使用;"
                "canvas_create_text_node 写剧本/脚本/方案;【头脑风暴分层】同一次会话里产出多个板块(人物/故事/场面/世界观/视觉/结局方案)时,必须带 section_title(板块名,如'核心人物'),同一会话同一板块会合并更新而不是重复新建,整轮讨论会成为侧边栏里的一个整体产物;板块内还有多个并列条目(如林澜/司徒岳)时再带 item_title;canvas_create_generation_node 把图片提示词+引用图+生图预设同步到画布生成节点(建立待生成节点,返回 node_id);"
                "canvas_update_node 修改节点;canvas_check_generation 查询生成任务状态。"
                "canvas_batch_operations 批量执行标准化操作(add_node/update_node/delete_node/add_link/delete_link/set_variable/layer_operate,原子性,失败全回滚,适合一次建多个节点并连线);"
                "canvas_undo_batch 撤销某次批量操作;canvas_add_link 连线;canvas_delete_node 删除节点。"
                "canvas_generate_images 仅在用户明确要求马上出图时才使用(会阻塞等待生成完成)。"
                "生图标准流程:需要生成图片时,用 canvas_create_generation_node 在画布建立生成节点即可——不要在对话框内阻塞等待生成;用户会在画布节点上点执行按钮生成,然后你可以用 canvas_get_state 读取节点状态/生成结果。"
                "只要用了参考图,生成提示词里就必须逐张写出 @图片1/@图片2/... ,并明确说明每张图分别参考什么(如人物/服装/构图/配色/材质/光效);"
                "这些编号严格按当前会话输入链图片顺序决定,如果用了多张图,必须 @每一张,不要合并成笼统的“参考上图/参考图片”。"
                "canvas_list_skills 查看已保存的技能;canvas_save_skill 把对话中提炼的可复用方法/工作流/风格偏好保存为技能,"
                "之后用户或自己可 @技能名 调用。当用户教你一套方法、或你总结出可复用的创作流程时,主动保存成技能。"
                "present_im_interaction 用于需要用户决策的等待点:把选择/表单/确认/进度/产物以结构化卡片展示给用户点击。"
                "【硬性要求】当你要给用户几个方向/方案/风格让他选、要收集已知参数(画幅/时长/旁白/比例)、要在高成本动作(生成素材/视频)前请用户确认、要展示生成进度、要交付最终产物时,"
                "必须调用 present_im_interaction 工具把内容做成结构化卡片(choose/collect/confirm/progress/artifact),通过 tool_calls 而不是正文。"
                "严格禁止:在正文写 A./B./C. 编号列选项、写“回复1或2”、让用户打字回答本该是选择题的、把该确认的写成文字问句。"
                "一卡一决策,发出卡片后本轮立即结束,等待用户回执,不要同轮继续执行未授权动作。"
                "把 options 的 id 写成 A/B/C,label 写清晰标题,desc 写一句可感知的差异化描述,default 预选一个最稳妥的;collect 的字段值闭集用 select 下拉。")
    guidance += (
        "\n\n## 短剧制作板流程\n"
        "当用户点击剧情短片、说创作短剧/拍剧情视频/做微剧,且没有明确给出完整标准分镜或已选制作模式时,"
        "第一轮必须调用 present_im_interaction(intent=choose) 发模式卡,只给三项:快速出片、专业制作、已有剧本。"
        "不要直接生成大纲/剧本/分镜,也不要同时询问比例/时长/风格。"
        "用户选模式后,把短剧创作收敛为用户侧五步:选模式→生成短剧制作板→确认内容→执行节点→选结果/重拍/合成。"
        "内部可以按叙事短片主链的九阶段推演,但用户侧不要连续暴露大纲确认、剧本确认、素材确认、Clip表确认。"
        "短剧制作板应优先落到画布,包含 Brief、剧本/梗概、素材清单、Clip表、素材生成节点、视频生成节点。"
        "能一次创建多个节点时优先 canvas_batch_operations,并把相关节点连线;对话里只说明已创建哪些制作板节点和下一步可执行动作。"
    )
    if isinstance(preset, dict) and preset:
        preset_desc = "当前生图预设(用户配置):平台={provider_id},模型={model},比例={aspectRatio},分辨率={resolution},质量={quality}。生成图片时默认使用这些参数,除非用户明确要求不同的参数。".format(
            provider_id=preset.get("provider_id") or "runninghub",
            model=preset.get("model") or "按 API 设置中已配置的模型自动选择",
            aspectRatio=preset.get("aspectRatio") or "4:3",
            resolution=preset.get("resolution") or "2k",
            quality=preset.get("quality") or "medium",
        )
        guidance += "\n\n" + preset_desc
    for i, m in enumerate(messages):
        if m.get("role") == "system":
            messages[i] = dict(m)
            messages[i]["content"] = str(m.get("content") or "") + guidance
            return messages
    return [{"role": "system", "content": guidance}] + messages


def _agent_append_system(messages, text):
    if not text:
        return messages
    for i, m in enumerate(messages):
        if m.get("role") == "system":
            messages[i] = dict(m)
            messages[i]["content"] = str(m.get("content") or "") + "\n\n" + text
            return messages
    return [{"role": "system", "content": text}] + messages


def _agent_reply_rules():
    """回复与建议格式规则：建议用 A./B./C. 编号；用户采纳后只简短确认并执行。"""
    return (
        "## 回复与建议格式\n"
        "1. 当你的回复给用户可选择的行动建议时,用 A./B./C. 编号输出,每项不超过一句话,保持简洁。\n"
        "2. 用户采纳某项建议(回复如'选A'、'用B'、'A')时,只做最简短的确认并立即执行,不要重复展开建议内容、不要长篇解释。\n"
        "3. 只要调用了参考图片来生成或改写提示词,就必须逐张写出 @图片1/@图片2/... ,并说明这张图具体参考什么;这些编号严格按当前会话输入链图片顺序决定。如果用了多张,必须 @每一张分别说明,不能笼统写“参考图片”。"
    )


def _agent_brainstorm_guidance(brainstorm):
    stage = str((brainstorm or {}).get("stage") or "方向探索")
    decisions = (brainstorm or {}).get("decisions") or []
    decision_lines = "\n".join(
        "- {}: {}".format(d.get("key"), d.get("value"))
        for d in decisions if isinstance(d, dict)
    ) or "（暂无）"
    json_example = '{"stage":"当前阶段","question":"需要用户决策的问题","candidates":[{"id":"A","title":"候选标题","desc":"一句话描述","prompt":"该候选对应的画面/视频生成提示词","tags":["标签"]}],"decisions":[{"key":"决策项","value":"已确认值"}],"done":false}'
    rules = (
        "## 头脑风暴模式\n"
        "你正在以一问一答的方式帮用户开发创意(类似专业创意头脑风暴)。规则：\n"
        "当前阶段：" + stage + "。已确认决策：\n" + decision_lines + "\n"
        "1. 每次回复**只输出一个 JSON 对象**，不要输出任何其他文字、解释、代码块或 markdown。\n"
        "2. JSON 格式：\n" + json_example + "\n"
        "3. **字符串值内部禁止使用英文双引号**，需要引号时一律用中文引号「」或单引号，否则 JSON 会解析失败。\n"
        "4. 阶段推进：方向探索→深化→确认→落地。\n"
        "   - 方向探索：给 2-3 个明显不同的候选方向，让用户选一个或说“换一批”。\n"
        "   - 深化：基于选定方向，逐个问关键细节（受众/卖点/场景/调性/结构），每次只问一个问题，可给子候选。\n"
        "   - 确认：汇总已确认内容，让用户确认是否完成。\n"
        "   - 落地：调用 canvas_create_text_node 工具把创意简报/角色/世界观/剧本/分镜写入画布，然后 done=true，在 question 里说明已写入哪些节点。\n"
        "5. candidates 每次最多 3 个；用户说“换一批”就重新给一批完全不同的候选。\n"
        "6. decisions 每轮都要带上全部已确认项（累加），不要丢失。\n"
        "7. 一次只问一个问题，一次最多给 3 个候选。\n"
        "8. **每个候选都必须带 prompt 字段**：该候选方向对应的、可直接用于图片/视频生成的画面提示词（具体、可视、含主体/场景/光影/镜头）。用户点选候选后，软件会按每个候选各建一个生成节点，prompt 分开使用。"
    )
    return rules


def _agent_candidate_interaction_guidance():
    """默认候选交互引导：不依赖任何开关。当回复适合给出多个可选方向/方案/风格时，
    用带 prompt 的 candidates JSON，前端会渲染成可选卡片，点选后只建所选候选的节点。"""
    json_example = '{"stage":"方向探索","question":"需要用户决策的问题","candidates":[{"id":"A","title":"候选标题","desc":"一句话描述","prompt":"该候选对应的画面/视频生成提示词","tags":["标签"]}],"decisions":[],"done":false}'
    return (
        "## 候选交互（默认启用）\n"
        "当你的回复适合给出多个明显不同的可选方向/方案/风格/调性（例如用户要几个方案、几个方向、几个镜头思路）时，"
        "用候选卡片的形式输出，规则：\n"
        "1. 只输出一个 JSON 对象，不要附加任何解释文字、代码块或 markdown。\n"
        "2. JSON 格式：\n" + json_example + "\n"
        "3. **字符串值内部禁止使用英文双引号**，需要引号时用中文引号「」或单引号，否则 JSON 解析失败。\n"
        "4. candidates 每次最多 3 个，每个候选**必须带 prompt 字段**（该候选可直接用于图片/视频生成的画面提示词，具体、可视、含主体/场景/光影/镜头）。\n"
        "5. 若用户只是问某一个具体问题、不需要对比选择，则**正常用文本回答**，不要输出 JSON。\n"
    )



# -*- coding: utf-8 -*-
"""MyridTV Agent 请求编排主干（后端拆分第19刀）：codex 本地桥编排
（submit_codex_chat：模式卡/制作板短路、桥执行、工具轮循环、回退节点）与
OpenAI 兼容上游编排（submit_chat：step 策略、交互卡重试、violation 纠正、
停止检查、任务收尾）。含 finish_runtime 嵌套收尾器（随块保真）。

逐字迁移自 rh_official_proxy.py 两块：L(submit_codex_chat)..L(request_canvas_
agent_stop) 前 + L(submit_chat)..L(upload_reference) 前（共 470 行 2 主函数，
可逆还原行级 diff=0）。行为零变更。
configure()：LOG_FILE getter；9 个留主真身（request_chat_json_with_retry/
resolve_chat_target/payload_prefers_codex_local/normalize_chat_messages/
canvas_agent_execute_tool/canvas_agent_tools_schema/codex session 记录三件）
经 *args 闭包延迟解析主模块名——主文件测试打桩照常穿透；6 个 import 期
定值的 CODEX/CANVAS 常量值传注入（零重绑）；STOP/SESSION/ROUTE/PHASE/
FALLBACK 全局属性链直引属主模块（同对象）。
主文件留 submit_chat 薄代理（Handler 调用点）；submit_codex_chat 块外零引用
无代理（模块内 B 调 A 裸名直连）。中间 5 个第16刀壳代理留主原位。
"""
import json
import time

from myridtv_core import append_log
import agent_task_runtime as agent_runtime

import myridtv_agent
import myridtv_agent_guard
import myridtv_agent_guidance
import myridtv_agent_short_drama
import myridtv_agent_state
import myridtv_agent_stop
import myridtv_agent_tools
import myridtv_canvas_store
import myridtv_agent_tasks
import myridtv_codex

_log_file = lambda: None
_G_CODEX_LOCAL_DEFAULT_MODEL = None
_G_CODEX_LOCAL_PERSIST_SESSIONS = None
_G_CANVAS_AGENT_MAX_TOOL_TURNS = None
_G_CANVAS_AGENT_MAX_INTERACTION_RETRIES = None
_G_CANVAS_AGENT_REASONING_EFFORT = None
_G__canvas_agent_reasoning_effort = None
_r_request_chat_json_with_retry = None
_r_resolve_chat_target = None
_r_payload_prefers_codex_local = None
_r_normalize_chat_messages = None
_r_canvas_agent_execute_tool = None
_r_canvas_agent_tools_schema = None
_r__codex_bridge_session_record = None
_r__codex_bridge_store_session_record = None
_r__codex_bridge_clear_session_record = None


def configure(log_file_getter, funcs, values):
    global _log_file
    _log_file = log_file_getter
    global _G_CODEX_LOCAL_DEFAULT_MODEL
    global _G_CODEX_LOCAL_PERSIST_SESSIONS
    global _G_CANVAS_AGENT_MAX_TOOL_TURNS
    global _G_CANVAS_AGENT_MAX_INTERACTION_RETRIES
    global _G_CANVAS_AGENT_REASONING_EFFORT
    global _G__canvas_agent_reasoning_effort
    global _r_request_chat_json_with_retry
    global _r_resolve_chat_target
    global _r_payload_prefers_codex_local
    global _r_normalize_chat_messages
    global _r_canvas_agent_execute_tool
    global _r_canvas_agent_tools_schema
    global _r__codex_bridge_session_record
    global _r__codex_bridge_store_session_record
    global _r__codex_bridge_clear_session_record
    _G_ = globals()
    _G_CODEX_LOCAL_DEFAULT_MODEL = values['CODEX_LOCAL_DEFAULT_MODEL']
    _G_CODEX_LOCAL_PERSIST_SESSIONS = values['CODEX_LOCAL_PERSIST_SESSIONS']
    _G_CANVAS_AGENT_MAX_TOOL_TURNS = values['CANVAS_AGENT_MAX_TOOL_TURNS']
    _G_CANVAS_AGENT_MAX_INTERACTION_RETRIES = values['CANVAS_AGENT_MAX_INTERACTION_RETRIES']
    _G_CANVAS_AGENT_REASONING_EFFORT = values['CANVAS_AGENT_REASONING_EFFORT']
    _G__canvas_agent_reasoning_effort = values['_canvas_agent_reasoning_effort']
    _r_request_chat_json_with_retry = funcs['request_chat_json_with_retry']
    _r_resolve_chat_target = funcs['resolve_chat_target']
    _r_payload_prefers_codex_local = funcs['payload_prefers_codex_local']
    _r_normalize_chat_messages = funcs['normalize_chat_messages']
    _r_canvas_agent_execute_tool = funcs['canvas_agent_execute_tool']
    _r_canvas_agent_tools_schema = funcs['canvas_agent_tools_schema']
    _r__codex_bridge_session_record = funcs['_codex_bridge_session_record']
    _r__codex_bridge_store_session_record = funcs['_codex_bridge_store_session_record']
    _r__codex_bridge_clear_session_record = funcs['_codex_bridge_clear_session_record']


# ===== 块A：submit_codex_chat =====
def submit_codex_chat(payload):
    codex_session_id = str(payload.get("agent_session_id") or payload.get("session_id") or "").strip()
    myridtv_agent_tools.CANVAS_AGENT_CURRENT_SESSION["session_id"] = codex_session_id
    script_board_result = myridtv_agent_short_drama._agent_short_drama_script_board_result(payload)
    if script_board_result:
        return finish_runtime(script_board_result)
    board_result = myridtv_agent_short_drama._agent_short_drama_board_result(payload)
    if board_result:
        return finish_runtime(board_result)
    script_param_card = myridtv_agent_short_drama._agent_short_drama_script_param_card_result(payload)
    if script_param_card:
        return finish_runtime(script_param_card)
    param_card = myridtv_agent_short_drama._agent_short_drama_param_card_result(payload)
    if param_card:
        return finish_runtime(param_card)
    mode_card = myridtv_agent_short_drama._agent_short_drama_mode_card_result(payload)
    if mode_card:
        return finish_runtime(mode_card)
    messages = _r_normalize_chat_messages(payload)
    messages = myridtv_agent_guidance._agent_sanitize_messages(messages)
    tools = payload.get("tools") or _r_canvas_agent_tools_schema()
    preset = payload.get("generation_preset")
    preset = preset if isinstance(preset, dict) else {}
    if tools:
        messages = myridtv_agent_guidance._agent_inject_tool_guidance(messages, preset)
    brainstorm = payload.get("brainstorm")
    if isinstance(brainstorm, dict) and brainstorm:
        messages = myridtv_agent_guidance._agent_append_system(messages, myridtv_agent_guidance._agent_brainstorm_guidance(brainstorm))
    messages = myridtv_agent_guidance._agent_append_system(messages, myridtv_agent_guidance._agent_reply_rules())
    # 默认候选交互：命中流程型技能（叙事短片主链）时跳过，避免压过技能的阶段推进
    if not myridtv_agent._agent_has_flow_skill(payload):
        messages = myridtv_agent_guidance._agent_append_system(messages, myridtv_agent_guidance._agent_candidate_interaction_guidance())
    if tools:
        messages = myridtv_agent_guidance._agent_append_system(messages, myridtv_codex._codex_bridge_protocol_instruction(tools, preset))
    messages = myridtv_codex._codex_bridge_compact_messages(messages)
    model = str(payload.get("model") or "").strip()
    if model == _G_CODEX_LOCAL_DEFAULT_MODEL:
        model = ""
    session_key, session_record = ("", None)
    if _G_CODEX_LOCAL_PERSIST_SESSIONS:
        session_key, session_record = _r__codex_bridge_session_record(payload, model or _G_CODEX_LOCAL_DEFAULT_MODEL)
    if session_record:
        latest_user = next((msg for msg in reversed(messages) if msg.get("role") == "user"), None)
        system_messages = [msg for msg in messages if msg.get("role") == "system"]
        resumed_messages = []
        if system_messages:
            resumed_messages.append(system_messages[0])
        if latest_user:
            resumed_messages.append(latest_user)
        if resumed_messages:
            messages = resumed_messages
    attachment_files = myridtv_codex._codex_bridge_attachment_files(payload)
    tool_log = []
    last_meta = {"returncode": 0, "stdout_events": 0}
    try:
        max_turns = _G_CANVAS_AGENT_MAX_TOOL_TURNS if tools else 1
        for turn in range(max_turns + 1):
            prompt_text = myridtv_codex._codex_bridge_prompt_text(payload, messages)
            active_session_id = str((session_record or {}).get("thread_id") or "").strip()
            try:
                if _G_CODEX_LOCAL_PERSIST_SESSIONS:
                    result = myridtv_codex._run_codex_bridge_persistent(prompt_text, model, attachment_files, active_session_id)
                else:
                    result = myridtv_codex._run_codex_bridge_exec(prompt_text, model, attachment_files, "")
                    result["bridge_mode"] = "exec_ephemeral"
            except RuntimeError as app_server_exc:
                if not _G_CODEX_LOCAL_PERSIST_SESSIONS:
                    raise
                append_log(_log_file(), "codex app-server bridge fallback: {}".format(str(app_server_exc)[:300]))
                try:
                    result = myridtv_codex._run_codex_bridge_exec(prompt_text, model, attachment_files, active_session_id)
                except RuntimeError as exc:
                    error_text = str(exc)
                    if myridtv_codex._codex_bridge_should_reset_session(error_text, bool(active_session_id)):
                        append_log(_log_file(), "codex bridge reset stale/conflict session={}".format(active_session_id or "-"))
                        _r__codex_bridge_clear_session_record(session_key)
                        session_record = None
                        result = myridtv_codex._run_codex_bridge_exec(prompt_text, model, attachment_files, "")
                    else:
                        raise
            final_text = result.get("text") or ""
            last_meta = result
            thread_id = str(result.get("thread_id") or "").strip()
            if _G_CODEX_LOCAL_PERSIST_SESSIONS and thread_id:
                _r__codex_bridge_store_session_record(session_key, thread_id, model or _G_CODEX_LOCAL_DEFAULT_MODEL)
                session_record = {"thread_id": thread_id, "model": model or _G_CODEX_LOCAL_DEFAULT_MODEL}
            if not tools:
                append_log(_log_file(), "codex bridge ok model={} images={} returncode={} session={} mode={}".format(model or _G_CODEX_LOCAL_DEFAULT_MODEL, len(attachment_files), result.get("returncode") or 0, thread_id or active_session_id or "new", result.get("bridge_mode") or "exec"))
                return {
                    "text": final_text,
                    "raw": {
                        "provider": "codex-local",
                        "model": model or _G_CODEX_LOCAL_DEFAULT_MODEL,
                        "returncode": result.get("returncode") or 0,
                        "stdout_events": result.get("stdout_events") or 0,
                        "tool_turns": 0,
                        "thread_id": thread_id or active_session_id,
                        "bridge_mode": result.get("bridge_mode") or "exec",
                    },
                    "tool_log": [],
                    "agent_result": myridtv_agent_guard._build_canvas_agent_result(
                        final_text,
                        [],
                        {"provider": "codex-local", "model": model or _G_CODEX_LOCAL_DEFAULT_MODEL},
                        "plain_text",
                        session_id=codex_session_id,
                    ),
                }
            parsed = myridtv_codex._codex_bridge_extract_json(final_text)
            if not parsed:
                fallback_nodes = []
                if myridtv_agent_short_drama.CANVAS_AGENT_ALLOW_TEXT_FALLBACK_NODES and myridtv_codex._codex_bridge_request_wants_canvas_nodes(payload):
                    fallback_nodes = myridtv_codex._codex_bridge_extract_generation_nodes(final_text, (payload or {}).get("message") or "")
                    if not fallback_nodes and myridtv_codex._codex_bridge_request_wants_canvas_nodes(payload):
                        fallback_nodes = myridtv_codex._codex_bridge_extract_generation_nodes((payload or {}).get("message") or "", (payload or {}).get("message") or "")
                    if not fallback_nodes and myridtv_codex._codex_bridge_request_wants_canvas_nodes(payload):
                        fallback_nodes = myridtv_codex._codex_bridge_default_generation_nodes(final_text, (payload or {}).get("message") or "")
                if tools and fallback_nodes:
                    for node in fallback_nodes:
                        args = myridtv_agent_state._agent_merge_payload_refs_into_tool_args("canvas_create_generation_node", {
                            "title": str(node.get("title") or "").strip(),
                            "prompt": str(node.get("prompt") or "").strip(),
                            "canvas_id": str((payload or {}).get("canvas_id") or ""),
                        }, payload)
                        result_data = _r_canvas_agent_execute_tool("canvas_create_generation_node", args, preset, codex_session_id)
                        tool_log.append({"name": "canvas_create_generation_node", "args": args, "result": result_data})
                    created_count = len([entry for entry in tool_log if str((entry.get("result") or {}).get("node_id") or "").strip()])
                    if created_count:
                        final_text = myridtv_codex._codex_bridge_cleanup_fallback_text(final_text)
                        final_text = "{}\n\n已自动创建 {} 个画布生成节点，可直接点击执行。".format(final_text.strip(), created_count).strip()
                        append_log(_log_file(), "codex bridge fallback-created-nodes model={} count={}".format(model or _G_CODEX_LOCAL_DEFAULT_MODEL, created_count))
                        return {
                            "text": final_text,
                            "raw": {
                                "provider": "codex-local",
                                "model": model or _G_CODEX_LOCAL_DEFAULT_MODEL,
                                "returncode": result.get("returncode") or 0,
                                "stdout_events": result.get("stdout_events") or 0,
                                "tool_turns": len(tool_log),
                                "output_mode": "plain_text_fallback_nodes",
                            },
                            "tool_log": tool_log,
                            "agent_result": myridtv_agent_guard._build_canvas_agent_result(
                                final_text,
                                tool_log,
                                {"provider": "codex-local", "model": model or _G_CODEX_LOCAL_DEFAULT_MODEL},
                                "plain_text_fallback_nodes",
                                session_id=codex_session_id,
                            ),
                        }
                if fallback_nodes and not myridtv_agent_short_drama.CANVAS_AGENT_ALLOW_TEXT_FALLBACK_NODES:
                    append_log(_log_file(), "codex bridge fallback nodes suppressed (myridtv_agent_short_drama.CANVAS_AGENT_ALLOW_TEXT_FALLBACK_NODES=False) count={}".format(len(fallback_nodes)))
                append_log(_log_file(), "codex bridge non-json fallback model={} turn={}".format(model or _G_CODEX_LOCAL_DEFAULT_MODEL, turn + 1))
                return {
                    "text": final_text,
                    "raw": {
                        "provider": "codex-local",
                        "model": model or _G_CODEX_LOCAL_DEFAULT_MODEL,
                        "returncode": result.get("returncode") or 0,
                        "stdout_events": result.get("stdout_events") or 0,
                        "tool_turns": len(tool_log),
                        "thread_id": thread_id or active_session_id,
                        "bridge_mode": result.get("bridge_mode") or "exec",
                        "output_mode": "plain_text",
                    },
                    "tool_log": tool_log,
                    "agent_result": myridtv_agent_guard._build_canvas_agent_result(
                        final_text,
                        tool_log,
                        {"provider": "codex-local", "model": model or _G_CODEX_LOCAL_DEFAULT_MODEL},
                        "plain_text",
                        session_id=codex_session_id,
                    ),
                }
            assistant_reply = str(parsed.get("assistant_reply") or parsed.get("text") or parsed.get("reply") or "").strip()
            tool_calls = myridtv_codex._codex_bridge_normalize_tool_calls(parsed)
            done = bool(parsed.get("done"))
            if not tool_calls:
                text = assistant_reply or final_text
                append_log(_log_file(), "codex bridge ok model={} images={} returncode={} tool_calls={}".format(model or _G_CODEX_LOCAL_DEFAULT_MODEL, len(attachment_files), result.get("returncode") or 0, len(tool_log)))
                return {
                    "text": text,
                    "raw": {
                        "provider": "codex-local",
                        "model": model or _G_CODEX_LOCAL_DEFAULT_MODEL,
                        "returncode": result.get("returncode") or 0,
                        "stdout_events": result.get("stdout_events") or 0,
                        "tool_turns": len(tool_log),
                        "thread_id": thread_id or active_session_id,
                        "bridge_mode": result.get("bridge_mode") or "exec",
                        "done": done,
                        "output_mode": "json_protocol",
                    },
                    "tool_log": tool_log,
                    "agent_result": myridtv_agent_guard._build_canvas_agent_result(
                        text,
                        tool_log,
                        {"provider": "codex-local", "model": model or _G_CODEX_LOCAL_DEFAULT_MODEL},
                        "json_protocol",
                        {"done": done},
                        session_id=codex_session_id,
                    ),
                }
            messages.append({"role": "assistant", "content": assistant_reply or "我现在开始执行画布操作。"})
            myridtv_canvas_store.CANVAS_AGENT_ROUTE_CONTEXT["user_text"] = myridtv_agent_short_drama._agent_latest_user_text(payload)
            for tc in tool_calls:
                name = tc.get("name") or ""
                args = myridtv_agent_state._agent_merge_payload_refs_into_tool_args(name, tc.get("arguments") or {}, payload)
                result_data = _r_canvas_agent_execute_tool(name, args, preset, codex_session_id)
                tool_log.append({"name": name, "args": args, "result": result_data})
                tool_content = json.dumps(result_data, ensure_ascii=False)
                if len(tool_content) > 8000:
                    tool_content = tool_content[:8000] + "...(结果已截断)"
                messages.append({"role": "tool", "content": "{} => {}".format(name, tool_content)})
        return {
            "text": "我已经执行了一部分画布操作，但工具调用达到轮次上限。请看画布里的新增节点，再告诉我是否继续。",
            "raw": {
                "provider": "codex-local",
                "model": model or _G_CODEX_LOCAL_DEFAULT_MODEL,
                "returncode": last_meta.get("returncode") or 0,
                "stdout_events": last_meta.get("stdout_events") or 0,
                "tool_turns": len(tool_log),
                "thread_id": last_meta.get("thread_id") or "",
                "bridge_mode": last_meta.get("bridge_mode") or "exec",
                "done": False,
                "output_mode": "json_protocol",
            },
            "tool_log": tool_log,
            "agent_result": myridtv_agent_guard._build_canvas_agent_result(
                "我已经执行了一部分画布操作，但工具调用达到轮次上限。请看画布里的新增节点，再告诉我是否继续。",
                tool_log,
                {"provider": "codex-local", "model": model or _G_CODEX_LOCAL_DEFAULT_MODEL},
                "json_protocol",
                {"done": False},
                session_id=codex_session_id,
            ),
        }
    finally:
        pass

# ===== 块B：submit_chat =====
def submit_chat(payload):
    payload = payload if isinstance(payload, dict) else {}
    # 本请求的会话 id：显式从 payload 取，沿调用链传递，
    # 不再依赖全局 myridtv_agent_tools.CANVAS_AGENT_CURRENT_SESSION（并发会话会互相覆盖）。
    agent_session_id = str(payload.get("agent_session_id") or payload.get("session_id") or "").strip()
    task = myridtv_agent_tasks._agent_task_for_payload(payload)
    turn = agent_runtime.begin_turn(task, myridtv_agent_short_drama._agent_latest_user_text(payload))

    def finish_runtime(result, assistant_text=None, tool_log=None, interaction=None):
        if not isinstance(result, dict):
            result = {"text": str(result or "")}
        agent_result = result.get("agent_result") if isinstance(result.get("agent_result"), dict) else {}
        resolved_text = str(assistant_text if assistant_text is not None else (agent_result.get("text") or result.get("text") or ""))
        resolved_tool_log = tool_log if isinstance(tool_log, list) else (agent_result.get("tool_log") if isinstance(agent_result.get("tool_log"), list) else result.get("tool_log") or [])
        resolved_interaction = interaction if isinstance(interaction, dict) else (agent_result.get("interaction") if isinstance(agent_result.get("interaction"), dict) else result.get("interaction"))
        if isinstance(resolved_interaction, dict):
            agent_runtime.record_interaction(task, turn, resolved_interaction)
        if result.get("stopped"):
            task["status"] = "paused"
            validation = {"complete": False, "reason": "paused_by_user"}
        else:
            validation = agent_runtime.advance_step_if_complete(task, resolved_text, resolved_tool_log, resolved_interaction)
        turn["message"]["text"] = resolved_text
        turn["result"]["created_nodes"] = [
            str((item.get("result") or {}).get("node_id") or "")
            for item in resolved_tool_log
            if isinstance(item, dict) and str((item.get("result") or {}).get("node_id") or "").strip()
        ]
        turn["status"] = "waiting_user" if isinstance(resolved_interaction, dict) else "completed"
        turn["updated_at"] = int(time.time() * 1000)
        myridtv_agent_tasks._agent_save_tasks()
        myridtv_agent_tasks._agent_task_log("Workflow", "task={} step={} status={} validation={}".format(
            task.get("task_id"), task.get("current_step_id"), task.get("status"), validation))
        return myridtv_agent_tasks._agent_attach_runtime_result(result, task, turn, validation)

    if _r_payload_prefers_codex_local(payload):
        try:
            return finish_runtime(submit_codex_chat(payload))
        except Exception as _exc:
            myridtv_agent_tasks._agent_mark_task_failed(task, turn, _exc)
            raise
    myridtv_agent_tools.CANVAS_AGENT_CURRENT_SESSION["session_id"] = agent_session_id
    script_board_result = myridtv_agent_short_drama._agent_short_drama_script_board_result(payload)
    if script_board_result:
        return script_board_result
    board_result = myridtv_agent_short_drama._agent_short_drama_board_result(payload)
    if board_result:
        return board_result
    script_param_card = myridtv_agent_short_drama._agent_short_drama_script_param_card_result(payload)
    if script_param_card:
        return script_param_card
    param_card = myridtv_agent_short_drama._agent_short_drama_param_card_result(payload)
    if param_card:
        return param_card
    mode_card = myridtv_agent_short_drama._agent_short_drama_mode_card_result(payload)
    if mode_card:
        return mode_card
    request_id = str(payload.get("request_id") or "").strip()
    if request_id:
        with myridtv_agent_stop.CANVAS_AGENT_STOP_LOCK:
            myridtv_agent_stop.CANVAS_AGENT_STOP_REQUESTS.discard(request_id)
    try:
        provider_id, model, upstream_base, key = _r_resolve_chat_target(payload)
    except Exception as _exc:
        myridtv_agent_tasks._agent_mark_task_failed(task, turn, _exc)
        raise
    messages = _r_normalize_chat_messages(payload)
    messages = myridtv_agent_guidance._agent_sanitize_messages(messages)
    tools = payload.get("tools") or _r_canvas_agent_tools_schema()
    preset = payload.get("generation_preset")
    preset = preset if isinstance(preset, dict) else {}
    if tools:
        messages = myridtv_agent_guidance._agent_inject_tool_guidance(messages, preset)
    brainstorm = payload.get("brainstorm")
    if isinstance(brainstorm, dict) and brainstorm:
        messages = myridtv_agent_guidance._agent_append_system(messages, myridtv_agent_guidance._agent_brainstorm_guidance(brainstorm))
    messages = myridtv_agent_guidance._agent_append_system(messages, myridtv_agent_guidance._agent_reply_rules())
    # 默认候选交互：不依赖开关，适合给可选项时自动出候选卡片。
    # 但当命中流程型技能（如叙事短片主链）时跳过，避免候选引导压过技能的阶段推进。
    if not myridtv_agent._agent_has_flow_skill(payload):
        messages = myridtv_agent_guidance._agent_append_system(messages, myridtv_agent_guidance._agent_candidate_interaction_guidance())
    body = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    if _G__canvas_agent_reasoning_effort["enabled"]:
        body["reasoning_effort"] = _G_CANVAS_AGENT_REASONING_EFFORT
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    tool_log = []
    data = None
    _interaction_retries = 0
    for _turn in range(_G_CANVAS_AGENT_MAX_TOOL_TURNS + 1):
        # 阶段守卫：按任务当前步骤写入 Mutation 阶段。
        # 资产发现/提取/提示词生成三个阶段禁建节点（与步骤 forbidden_tools 同源），其余为空=不激活。
        myridtv_canvas_store.CANVAS_AGENT_CURRENT_PHASE["phase"] = agent_runtime.step_phase(task)
        if myridtv_agent_stop._canvas_agent_stop_requested(request_id):
            append_log(_log_file(), "agent chat stopped by user at turn {}".format(_turn + 1))
            task["status"] = "paused"
            return finish_runtime({"text": "", "raw": None, "tool_log": tool_log, "stopped": True}, "", tool_log)
        _t0 = time.time()
        try:
            data = _r_request_chat_json_with_retry(
                f"{upstream_base}/chat/completions",
                body,
                {"Authorization": f"Bearer {key}"},
                attempts=3,
                timeout=300,
            )
        except Exception as _exc:
            append_log(_log_file(), "agent chat turn {} failed after {:.0f}s: {}".format(_turn + 1, time.time() - _t0, _exc))
            # 上游/模型不支持 reasoning_effort → 关掉开关并原样重试（保证换模型不会因此报错）
            if _G__canvas_agent_reasoning_effort["enabled"] and "reasoning_effort" in str(_exc):
                _G__canvas_agent_reasoning_effort["enabled"] = False
                append_log(_log_file(), "agent reasoning_effort not supported upstream, disabled and retrying")
                body.pop("reasoning_effort", None)
                continue
            myridtv_agent_tasks._agent_mark_task_failed(task, turn, _exc)
            raise
        append_log(_log_file(), "agent chat turn {} ok in {:.0f}s model={}".format(_turn + 1, time.time() - _t0, model))
        choices = data.get("choices") or []
        message = (choices[0].get("message") if choices and isinstance(choices[0], dict) else {}) or {}
        tool_calls = message.get("tool_calls")
        if not tool_calls:
            text = message.get("content") or ""
            # —— 交互合规拦截（harness 层确定性检测，非提示词）：该出卡没出卡/谎称发了卡 → 回灌纠正重试 ——
            if not myridtv_agent_guard._agent_has_present_interaction(tool_log):
                violation = myridtv_agent_guard._agent_detect_interaction_violation(text)
                if violation and _interaction_retries < _G_CANVAS_AGENT_MAX_INTERACTION_RETRIES:
                    append_log(_log_file(), "agent interaction violation turn={} type={} retrying".format(_turn + 1, violation))
                    # 本轮模型没返回工具调用，回灌时不能带 tool_calls 字段：
                    # 空数组会被 OpenAI 兼容上游拒收（400 Empty tool_calls is not supported）
                    messages.append({"role": "assistant", "content": message.get("content") or ""})
                    messages.append({"role": "user", "content": myridtv_agent_guard._agent_interaction_correction_prompt(violation)})
                    _interaction_retries += 1
                    continue
            return finish_runtime({
                "text": text,
                "raw": data,
                "tool_log": tool_log,
                "agent_result": myridtv_agent_guard._build_canvas_agent_result(
                    text,
                    tool_log,
                    {"provider": provider_id, "model": model},
                    "openai_compatible",
                    session_id=agent_session_id,
                ),
            }, text, tool_log)
        if myridtv_agent_stop._canvas_agent_stop_requested(request_id):
            append_log(_log_file(), "agent chat stopped before tool execution turn={}".format(_turn + 1))
            task["status"] = "paused"
            return finish_runtime({"text": "", "raw": data, "tool_log": tool_log, "stopped": True}, "", tool_log)
        # —— 流程纪律拦截：还没到落地环节就建节点 → 拦下工具调用，回灌纠正 ——
        premature = myridtv_agent_stop._agent_detect_premature_creation(tool_calls, messages, tool_log)
        if premature and _interaction_retries < _G_CANVAS_AGENT_MAX_INTERACTION_RETRIES:
            append_log(_log_file(), "agent premature creation blocked turn={} tools={}".format(_turn + 1, ",".join(
                str((tc.get("function") or {}).get("name") or "") for tc in tool_calls if isinstance(tc, dict))))
            messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": tool_calls})
            for tc in tool_calls:
                messages.append({"role": "tool", "tool_call_id": str((tc.get("id") or "")),
                                 "content": "已拦截：流程还没到创建节点环节，用户只要内容产出。请直接在正文输出内容。"})
            messages.append({"role": "user", "content": myridtv_agent_stop._agent_premature_creation_correction()})
            _interaction_retries += 1
            body["messages"] = messages
            continue
        messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": tool_calls})
        for tc in tool_calls:
            fn = tc.get("function") or {}
            name = str(fn.get("name") or "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                args = {}
            args = myridtv_agent_state._agent_merge_payload_refs_into_tool_args(name, args, payload)
            args = agent_runtime.attach_provenance(args, task, turn, str(tc.get("id") or ""))
            myridtv_canvas_store.CANVAS_AGENT_ROUTE_CONTEXT["user_text"] = myridtv_agent_short_drama._agent_latest_user_text(payload)
            policy = agent_runtime.authorize_tool(task, name, args)
            myridtv_agent_tasks._agent_task_log("ToolPolicy", "task={} step={} tool={} result={} reason={}".format(
                task.get("task_id"), task.get("current_step_id"), name,
                "allowed" if policy.get("allowed") else "blocked", policy.get("reason")))
            if not policy.get("allowed"):
                result = {
                    "ok": False,
                    "blocked": True,
                    "error": policy.get("message"),
                    "reason": policy.get("reason"),
                    "missing": policy.get("missing") or [],
                }
                tool_log.append({"name": name, "args": args, "result": result, "policy": policy})
                agent_runtime.record_tool_run(task, turn, name, args, result, policy)
                messages.append({"role": "tool", "tool_call_id": str(tc.get("id") or ""),
                                 "content": json.dumps(result, ensure_ascii=False)})
                continue
            _tt0 = time.time()
            result = _r_canvas_agent_execute_tool(name, args, preset, agent_session_id)
            append_log(_log_file(), "agent tool {} done in {:.0f}s".format(name, time.time() - _tt0))
            tool_log.append({"name": name, "args": args, "result": result})
            agent_runtime.record_tool_run(task, turn, name, args, result, policy)
            tool_content = json.dumps(result, ensure_ascii=False)
            # 工具结果截断，避免 ModLens 等大输出撑大上下文拖慢后续轮次
            if len(tool_content) > 8000:
                tool_content = tool_content[:8000] + "...(结果已截断)"
            messages.append({"role": "tool", "tool_call_id": str(tc.get("id") or ""),
                             "content": tool_content})
        # —— 批量建违规拦截：用户选"一次性全建"，但本轮逐个建且没调 canvas_batch_operations → 回灌纠正重试 ——
        bviol = myridtv_agent_guard._agent_detected_batch_violation(messages, tool_log)
        if bviol and _interaction_retries < _G_CANVAS_AGENT_MAX_INTERACTION_RETRIES:
            append_log(_log_file(), "agent batch violation turn={} type={} retrying".format(_turn + 1, bviol))
            messages.append({"role": "user", "content": myridtv_agent_guard._agent_batch_correction_prompt(bviol)})
            _interaction_retries += 1
            continue
        body["messages"] = messages
        body["tools"] = tools
    return finish_runtime({
        "text": "工具调用达到轮次上限,任务可能未完成。",
        "raw": data,
        "tool_log": tool_log,
        "agent_result": myridtv_agent_guard._build_canvas_agent_result(
            "工具调用达到轮次上限,任务可能未完成。",
            tool_log,
            {"provider": provider_id, "model": model},
            "openai_compatible",
            session_id=agent_session_id,
        ),
    }, "工具调用达到轮次上限,任务可能未完成。", tool_log)



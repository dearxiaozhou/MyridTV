# -*- coding: utf-8 -*-
"""Small task/workflow runtime for the canvas Agent.

This module is intentionally independent from the web server so it can be
unit-tested without starting the desktop app. It adds a Task/Step layer around
the existing chat and tool loop while keeping the old agent_result shape.
"""
import json
import re
import time
import uuid
from pathlib import Path


TASK_STATUSES = {"pending", "running", "waiting_user", "paused", "failed", "completed", "cancelled"}
PLACEHOLDER_PROMPT_MARKERS = (
    "todo", "tbd", "placeholder", "xxx",
    "待生成", "待定", "待写", "待补充", "待完善", "待产出", "占位", "占位符",
    "稍后", "暂无", "提示词占位", "生成提示词", "提示词待定", "待填",
)


WORKFLOWS = {
    "lightweight": [
        {
            "step_id": "respond",
            "label": "普通回复",
            "required_input": ["user_message"],
            "allowed_outputs": ["answer", "summary", "suggestion"],
            "allowed_tools": [
                "canvas_get_state", "canvas_search_nodes", "canvas_analyze_image",
                "canvas_create_text_node", "canvas_create_generation_node", "canvas_batch_operations",
                "canvas_generate_images", "canvas_update_node", "canvas_delete_node", "canvas_add_link",
                "canvas_list_skills", "canvas_save_skill", "present_im_interaction",
            ],
            "forbidden_tools": [],
            "completion_condition": ["assistant_text_present"],
            "next_step": None,
        }
    ],
    "video_creation": [
        {
            "step_id": "analyze_script",
            "label": "剧本分析",
            "required_input": ["script_or_brief"],
            "allowed_outputs": ["script_analysis"],
            "allowed_tools": ["canvas_get_state", "canvas_search_nodes", "present_im_interaction"],
            "forbidden_tools": ["canvas_create_text_node", "canvas_create_generation_node", "canvas_batch_operations", "canvas_generate_images"],
            "completion_condition": ["assistant_text_present"],
            "next_step": "determine_visual_direction",
        },
        {
            "step_id": "determine_visual_direction",
            "label": "视觉方向",
            "required_input": ["script_analysis"],
            "allowed_outputs": ["visual_direction", "choice"],
            "allowed_tools": ["present_im_interaction", "canvas_get_state", "canvas_search_nodes"],
            "forbidden_tools": ["canvas_create_generation_node", "canvas_batch_operations", "canvas_generate_images"],
            "completion_condition": ["assistant_text_present_or_interaction"],
            "next_step": "extract_assets",
        },
        {
            "step_id": "extract_assets",
            "label": "资产提取",
            "required_input": ["script", "visual_direction"],
            "allowed_outputs": ["character_asset_spec", "scene_asset_spec", "prop_asset_spec"],
            "allowed_tools": ["canvas_get_state", "canvas_search_nodes", "canvas_analyze_image", "present_im_interaction"],
            "forbidden_tools": ["canvas_create_text_node", "canvas_create_generation_node", "canvas_batch_operations", "canvas_generate_images"],
            "completion_condition": ["asset_specs_present"],
            "next_step": "generate_asset_prompts",
        },
        {
            "step_id": "generate_asset_prompts",
            "label": "资产 Prompt",
            "required_input": ["asset_specs"],
            "allowed_outputs": ["image_prompt"],
            "allowed_tools": ["canvas_get_state", "canvas_search_nodes", "canvas_analyze_image", "present_im_interaction"],
            "forbidden_tools": ["canvas_create_text_node", "canvas_create_generation_node", "canvas_batch_operations", "canvas_generate_images"],
            "completion_condition": ["required_asset_prompts_ready"],
            "next_step": "materialize_asset_nodes",
        },
        {
            "step_id": "materialize_asset_nodes",
            "label": "创建资产节点",
            "required_input": ["approved_asset_prompts"],
            "allowed_outputs": ["canvas_node"],
            "allowed_tools": ["canvas_create_text_node", "canvas_create_generation_node", "canvas_batch_operations", "present_im_interaction"],
            "forbidden_tools": ["canvas_generate_images"],
            "completion_condition": ["required_assets_have_nodes"],
            "next_step": "generate_assets",
        },
        {
            "step_id": "generate_assets",
            "label": "生成资产",
            "required_input": ["asset_nodes"],
            "allowed_outputs": ["generated_image"],
            "allowed_tools": ["canvas_generate_images", "canvas_check_generation", "present_im_interaction"],
            "forbidden_tools": [],
            "completion_condition": ["required_assets_generated"],
            "next_step": "review_assets",
        },
        {
            "step_id": "review_assets",
            "label": "资产确认",
            "required_input": ["generated_assets"],
            "allowed_outputs": ["asset_review"],
            "allowed_tools": ["present_im_interaction", "canvas_get_state", "canvas_search_nodes"],
            "forbidden_tools": ["canvas_create_generation_node", "canvas_batch_operations", "canvas_generate_images"],
            "completion_condition": ["required_assets_approved"],
            "next_step": "generate_storyboard",
        },
        {
            "step_id": "generate_storyboard",
            "label": "分镜",
            "required_input": ["approved_assets"],
            "allowed_outputs": ["storyboard"],
            "allowed_tools": ["canvas_get_state", "canvas_search_nodes", "present_im_interaction"],
            "forbidden_tools": ["canvas_generate_images"],
            "completion_condition": ["assistant_text_present"],
            "next_step": "generate_shot_prompts",
        },
        {
            "step_id": "generate_shot_prompts",
            "label": "镜头 Prompt",
            "required_input": ["storyboard"],
            "allowed_outputs": ["video_prompt"],
            "allowed_tools": ["canvas_get_state", "canvas_search_nodes", "present_im_interaction"],
            "forbidden_tools": ["canvas_batch_operations", "canvas_generate_images"],
            "completion_condition": ["assistant_text_present"],
            "next_step": "materialize_video_nodes",
        },
        {
            "step_id": "materialize_video_nodes",
            "label": "创建视频节点",
            "required_input": ["video_prompts"],
            "allowed_outputs": ["video_node"],
            "allowed_tools": ["canvas_batch_operations", "canvas_create_generation_node", "present_im_interaction"],
            "forbidden_tools": ["canvas_generate_images"],
            "completion_condition": ["created_nodes_present"],
            "next_step": "generate_video",
        },
        {
            "step_id": "generate_video",
            "label": "视频生成",
            "required_input": ["video_nodes"],
            "allowed_outputs": ["generated_video"],
            "allowed_tools": ["canvas_generate_images", "canvas_check_generation", "present_im_interaction"],
            "forbidden_tools": [],
            "completion_condition": ["assistant_text_present_or_tool_success"],
            "next_step": "qa",
        },
        {
            "step_id": "qa",
            "label": "QA",
            "required_input": ["generated_video"],
            "allowed_outputs": ["qa_report"],
            "allowed_tools": ["canvas_get_state", "canvas_search_nodes", "present_im_interaction"],
            "forbidden_tools": [],
            "completion_condition": ["assistant_text_present"],
            "next_step": None,
        },
    ],
}


TOOL_ALIASES = {
    "canvas_create_text_node": "canvas_create_text_node",
    "canvas_create_generation_node": "canvas_create_generation_node",
    "canvas_batch_operations": "canvas_batch_operations",
    "canvas_generate_images": "canvas_generate_images",
    "canvas_check_generation": "canvas_check_generation",
    "canvas_get_state": "canvas_get_state",
    "canvas_search_nodes": "canvas_search_nodes",
    "canvas_update_node": "canvas_update_node",
    "canvas_add_link": "canvas_add_link",
    "canvas_delete_node": "canvas_delete_node",
    "canvas_analyze_image": "canvas_analyze_image",
    "canvas_list_skills": "canvas_list_skills",
    "canvas_save_skill": "canvas_save_skill",
    "present_im_interaction": "present_im_interaction",
}


def now_ms():
    return int(time.time() * 1000)


def uid(prefix):
    return "{}_{}".format(prefix, uuid.uuid4().hex[:12])


def is_placeholder_prompt(prompt):
    raw = str(prompt or "").strip()
    if not raw:
        return True
    low = raw.lower()
    return any(marker in low for marker in PLACEHOLDER_PROMPT_MARKERS)


def workflow_steps(workflow_type):
    return list(WORKFLOWS.get(workflow_type) or WORKFLOWS["lightweight"])


def step_contract(workflow_type, step_id):
    for step in workflow_steps(workflow_type):
        if step["step_id"] == step_id:
            return dict(step)
    return dict(workflow_steps(workflow_type)[0])


# 步骤 → CanvasMutationManager 阶段（阶段守卫用）。
# 只有这三步属于「发现/提取/提示词生成」阶段，它们本就禁止建节点（见各步 forbidden_tools）；
# 映射后底层硬守卫 validate_asset_node 也能拦住绕过工具白名单的写入。
STEP_PHASE_MAP = {
    "analyze_script": "ASSET_DISCOVERY",
    "extract_assets": "ASSET_EXTRACTION",
    "generate_asset_prompts": "PROMPT_GENERATING",
}


def step_phase(task):
    """当前任务步骤对应的 Mutation 阶段；返回 "" 表示阶段守卫不激活。

    只对 video_creation 工作流生效（lightweight 普通回复永远返回 ""），
    因此普通对话/直接生成不会被阶段守卫拦。
    """
    if not isinstance(task, dict):
        return ""
    if str(task.get("workflow_type") or "") != "video_creation":
        return ""
    return STEP_PHASE_MAP.get(str(task.get("current_step_id") or ""), "")


def infer_workflow_type(text):
    raw = re.sub(r"\s+", "", str(text or ""))
    if any(token in raw for token in ("短片", "短剧", "视频", "分镜", "镜头", "成片", "AI短片", "制作板")):
        return "video_creation"
    if "剧本" in raw and any(token in raw for token in ("资产", "素材", "角色", "人物", "场景", "道具")):
        return "video_creation"
    if any(token in raw for token in ("资产", "素材")) and any(token in raw for token in ("提示词", "Prompt", "prompt", "文生图", "提取", "分析", "清单")):
        return "video_creation"
    return "lightweight"


def infer_initial_step(text, workflow_type):
    raw = str(text or "")
    if workflow_type != "video_creation":
        return "respond"
    if any(token in raw for token in ("Prompt", "prompt", "提示词", "文生图")) and any(token in raw for token in ("资产", "角色", "场景", "道具")):
        return "generate_asset_prompts"
    if any(token in raw for token in ("资产", "角色", "场景", "道具")) and any(token in raw for token in ("分析", "提取", "有哪些", "清单")):
        return "extract_assets"
    return "analyze_script"


def make_steps(workflow_type, current_step_id):
    steps = []
    current_seen = False
    for idx, step in enumerate(workflow_steps(workflow_type), 1):
        sid = step["step_id"]
        if sid == current_step_id:
            status = "running"
            current_seen = True
        elif not current_seen:
            status = "pending"
        else:
            status = "pending"
        steps.append({
            "step_id": sid,
            "label": step.get("label") or sid,
            "status": status,
            "index": idx,
            "contract": {
                "required_input": step.get("required_input", []),
                "allowed_outputs": step.get("allowed_outputs", []),
                "allowed_tools": step.get("allowed_tools", []),
                "forbidden_tools": step.get("forbidden_tools", []),
                "completion_condition": step.get("completion_condition", []),
                "next_step": step.get("next_step"),
            },
        })
    return steps


def task_title_from_text(text, workflow_type):
    raw = str(text or "").strip().replace("\n", " ")
    if workflow_type == "video_creation":
        m = re.search(r"《([^》]{1,40})》", raw)
        if m:
            return "制作《{}》短片".format(m.group(1))
        return "制作 AI 短片"
    return raw[:36] or "普通 Agent 对话"


def create_task(conversation_id="", canvas_id="", user_text=""):
    workflow_type = infer_workflow_type(user_text)
    current = infer_initial_step(user_text, workflow_type)
    total = len(workflow_steps(workflow_type))
    task = {
        "task_id": uid("task"),
        "conversation_id": str(conversation_id or ""),
        "canvas_id": str(canvas_id or ""),
        "title": task_title_from_text(user_text, workflow_type),
        "status": "running",
        "workflow_type": workflow_type,
        "current_step_id": current,
        "progress": {"current": step_index(workflow_type, current), "total": total},
        "created_at": now_ms(),
        "updated_at": now_ms(),
        "steps": make_steps(workflow_type, current),
        "turns": [],
        "artifacts": [],
        "assets": [],
        "canvas_nodes": [],
        "decisions": [],
        "tool_runs": [],
        "canvas_mutations": [],
        "interactions": [],
        "last_turn_id": None,
    }
    return task


def step_index(workflow_type, step_id):
    for idx, step in enumerate(workflow_steps(workflow_type), 1):
        if step["step_id"] == step_id:
            return idx
    return 1


def ensure_task(store, conversation_id="", canvas_id="", user_text="", task_id=""):
    if task_id and task_id in store:
        return store[task_id]
    for task in store.values():
        if (conversation_id and task.get("conversation_id") == conversation_id
                and task.get("status") in {"pending", "running", "waiting_user", "paused"}):
            task["status"] = "running" if task.get("status") == "paused" else task.get("status", "running")
            task["updated_at"] = now_ms()
            return task
    task = create_task(conversation_id, canvas_id, user_text)
    store[task["task_id"]] = task
    return task


def serialize_task(task):
    if not isinstance(task, dict):
        return None
    return {
        "task_id": task.get("task_id"),
        "conversation_id": task.get("conversation_id"),
        "canvas_id": task.get("canvas_id"),
        "title": task.get("title"),
        "status": task.get("status"),
        "workflow_type": task.get("workflow_type"),
        "current_step_id": task.get("current_step_id"),
        "progress": task.get("progress") or {},
        "error": task.get("error") or "",
        "failed_at": task.get("failed_at") or 0,
    }


def serialize_step(task):
    if not isinstance(task, dict):
        return None
    sid = task.get("current_step_id")
    contract = step_contract(task.get("workflow_type") or "lightweight", sid)
    return {
        "step_id": sid,
        "label": contract.get("label") or sid,
        "status": task.get("status") if task.get("status") in {"waiting_user", "failed", "completed"} else "running",
        "contract": {
            "required_input": contract.get("required_input", []),
            "allowed_outputs": contract.get("allowed_outputs", []),
            "allowed_tools": contract.get("allowed_tools", []),
            "forbidden_tools": contract.get("forbidden_tools", []),
            "completion_condition": contract.get("completion_condition", []),
            "next_step": contract.get("next_step"),
        },
    }


def authorize_tool(task, tool_name, args=None):
    if not isinstance(task, dict):
        return {"allowed": True, "reason": "no_task"}
    name = TOOL_ALIASES.get(str(tool_name or ""), str(tool_name or ""))
    contract = step_contract(task.get("workflow_type") or "lightweight", task.get("current_step_id"))
    allowed = set(contract.get("allowed_tools") or [])
    forbidden = set(contract.get("forbidden_tools") or [])
    if name in forbidden or (allowed and name not in allowed):
        return {
            "allowed": False,
            "reason": "tool_not_allowed_in_current_step",
            "task_id": task.get("task_id"),
            "step_id": task.get("current_step_id"),
            "tool": name,
            "message": "当前任务仍处于 {}，该阶段不允许调用 {}。请先完成当前 Step 的输出要求。".format(
                task.get("current_step_id"), name),
            "missing": expected_missing(task),
        }
    if name in {"canvas_create_generation_node", "canvas_generate_images"} and is_placeholder_prompt((args or {}).get("prompt")):
        return {
            "allowed": False,
            "reason": "invalid_or_placeholder_prompt",
            "task_id": task.get("task_id"),
            "step_id": task.get("current_step_id"),
            "tool": name,
            "message": "提示词为空或仍是占位内容，禁止进入画布节点创建或生成。",
            "missing": ["可执行的非占位 Prompt"],
        }
    return {"allowed": True, "reason": "allowed", "task_id": task.get("task_id"), "step_id": task.get("current_step_id"), "tool": name}


def expected_missing(task):
    sid = str((task or {}).get("current_step_id") or "")
    if sid == "extract_assets":
        return ["角色/场景/道具资产清单"]
    if sid == "generate_asset_prompts":
        return ["每个 required asset 的非空 Prompt", "无 TODO/待生成/placeholder 占位"]
    if sid == "review_assets":
        return ["所有 required asset 的用户确认"]
    return []


def begin_turn(task, user_message=""):
    turn = {
        "turn_id": uid("turn"),
        "task_id": task.get("task_id") if isinstance(task, dict) else "",
        "step_id": task.get("current_step_id") if isinstance(task, dict) else "",
        "message": {"text": str(user_message or "")},
        "execution": {"tool_runs": []},
        "result": {"created_nodes": [], "artifacts": []},
        "interaction": None,
        "status": "running",
        "created_at": now_ms(),
        "updated_at": now_ms(),
    }
    if isinstance(task, dict):
        task.setdefault("turns", []).append(turn)
        task["last_turn_id"] = turn["turn_id"]
        task["updated_at"] = now_ms()
    return turn


def record_tool_run(task, turn, tool_name, args, result, policy=None):
    run = {
        "tool_run_id": uid("toolrun"),
        "task_id": task.get("task_id") if isinstance(task, dict) else "",
        "step_id": task.get("current_step_id") if isinstance(task, dict) else "",
        "turn_id": turn.get("turn_id") if isinstance(turn, dict) else "",
        "tool_name": str(tool_name or ""),
        "args": args if isinstance(args, dict) else {},
        "result": result if isinstance(result, dict) else {},
        "policy": policy or {},
        "status": "completed" if isinstance(result, dict) and result.get("ok") is not False else "failed",
        "created_at": now_ms(),
    }
    if isinstance(task, dict):
        task.setdefault("tool_runs", []).append(run)
        if isinstance(turn, dict):
            turn.setdefault("execution", {}).setdefault("tool_runs", []).append(run)
        node_id = str((result or {}).get("node_id") or "").strip()
        if node_id:
            task.setdefault("canvas_nodes", []).append({
                "node_id": node_id,
                "step_id": run["step_id"],
                "turn_id": run["turn_id"],
                "tool_run_id": run["tool_run_id"],
                "created_at": run["created_at"],
            })
            if isinstance(turn, dict):
                turn.setdefault("result", {}).setdefault("created_nodes", []).append(node_id)
    return run


def record_interaction(task, turn, interaction):
    if not isinstance(task, dict) or not isinstance(interaction, dict):
        return None
    item = {
        "interaction_id": interaction.get("interaction_id") or interaction.get("card_id") or uid("interaction"),
        "task_id": task.get("task_id"),
        "step_id": task.get("current_step_id"),
        "turn_id": turn.get("turn_id") if isinstance(turn, dict) else "",
        "type": normalize_interaction_type(interaction.get("intent") or interaction.get("type")),
        "status": "waiting",
        "payload": dict(interaction),
        "created_at": now_ms(),
    }
    task.setdefault("interactions", []).append(item)
    if isinstance(turn, dict):
        turn["interaction"] = item
    task["status"] = "waiting_user"
    task["updated_at"] = now_ms()
    return item


def normalize_interaction_type(value):
    raw = str(value or "").strip()
    return {
        "choose": "choice",
        "confirm": "confirmation",
        "collect": "form",
        "artifact": "review",
        "progress": "progress",
    }.get(raw, raw or "choice")


def record_decision(task, receipt):
    if not isinstance(task, dict) or not isinstance(receipt, dict):
        return None
    decision = {
        "decision_id": uid("decision"),
        "task_id": task.get("task_id"),
        "step_id": task.get("current_step_id"),
        "type": "interaction_receipt",
        "target_id": receipt.get("card_id") or "",
        "value": receipt.get("selection") if receipt.get("selection") is not None else receipt.get("fields") or receipt.get("confirmed"),
        "created_at": now_ms(),
    }
    task.setdefault("decisions", []).append(decision)
    for item in task.get("interactions") or []:
        if str(item.get("interaction_id")) == str(receipt.get("card_id")):
            item["status"] = "resolved"
            item["resolved_at"] = decision["created_at"]
    task["status"] = "running"
    task["updated_at"] = now_ms()
    return decision


def upsert_asset(task, asset):
    if not isinstance(task, dict) or not isinstance(asset, dict):
        return None
    asset_id = str(asset.get("asset_id") or asset.get("id") or uid("asset"))
    assets = task.setdefault("assets", [])
    hit = next((item for item in assets if str(item.get("asset_id") or "") == asset_id), None)
    patch = {
        "asset_id": asset_id,
        "task_id": task.get("task_id"),
        "type": str(asset.get("type") or "asset"),
        "name": str(asset.get("name") or asset_id),
        "status": str(asset.get("status") or "identified"),
        "spec": asset.get("spec") if isinstance(asset.get("spec"), dict) else {},
        "prompt": str(asset.get("prompt") or ""),
        "approved_prompt": str(asset.get("approved_prompt") or ""),
        "canvas_node_id": asset.get("canvas_node_id"),
        "generated_node_ids": asset.get("generated_node_ids") if isinstance(asset.get("generated_node_ids"), list) else [],
        "review_status": str(asset.get("review_status") or "pending"),
        "required": asset.get("required", True) is not False,
        "updated_at": now_ms(),
    }
    if hit:
        hit.update(patch)
        return hit
    patch["created_at"] = now_ms()
    assets.append(patch)
    return patch


def record_asset_review_decision(task, asset_id, value):
    if not isinstance(task, dict):
        return None
    asset_id = str(asset_id or "")
    asset = next((item for item in task.get("assets") or [] if str(item.get("asset_id") or "") == asset_id), None)
    if not asset:
        return None
    value = str(value or "").strip().lower()
    if value in {"approved", "approve", "ok", "pass"}:
        asset["review_status"] = "approved"
        asset["status"] = "approved"
    elif value in {"regenerate", "rejected", "reject", "edit_prompt"}:
        asset["review_status"] = "rejected"
        asset["status"] = "generating" if value == "regenerate" else "prompt_ready"
    asset["updated_at"] = now_ms()
    return record_decision(task, {
        "card_id": asset_id,
        "selection": value,
        "confirmed": value == "approved",
        "fields": {},
    })


def validate_step_completion(task, assistant_text="", tool_log=None, interaction=None):
    if not isinstance(task, dict):
        return {"complete": False, "reason": "no_task"}
    sid = task.get("current_step_id")
    workflow_type = task.get("workflow_type") or "lightweight"
    conditions = step_contract(workflow_type, sid).get("completion_condition") or []
    text = str(assistant_text or "")
    tool_log = tool_log if isinstance(tool_log, list) else []
    created = [entry for entry in tool_log if str((entry.get("result") or {}).get("node_id") or "").strip()]
    successful = [entry for entry in tool_log if isinstance(entry.get("result"), dict) and entry["result"].get("ok") is not False]
    checks = {
        "assistant_text_present": bool(text.strip()),
        "assistant_text_present_or_interaction": bool(text.strip() or interaction),
        "assistant_text_present_or_tool_success": bool(text.strip() or successful),
        "created_nodes_present": bool(created),
        "asset_specs_present": bool(re.search(r"(角色|人物|场景|道具|资产|character|scene|prop)", text, re.I)),
        "required_asset_prompts_ready": required_asset_prompts_ready(task, text),
        "required_assets_have_nodes": required_assets_have_nodes(task, created),
        "required_assets_generated": bool(re.search(r"(生成完成|已生成|succeeded|generated)", text, re.I) or successful),
        "required_assets_approved": required_assets_approved(task),
    }
    missing = [cond for cond in conditions if not checks.get(cond, False)]
    return {"complete": not missing, "missing": missing, "conditions": conditions}


def advance_step_if_complete(task, assistant_text="", tool_log=None, interaction=None):
    validation = validate_step_completion(task, assistant_text, tool_log, interaction)
    if not isinstance(task, dict):
        return validation
    if interaction:
        task["status"] = "waiting_user"
        return validation
    if not validation.get("complete"):
        task["status"] = "running"
        task["updated_at"] = now_ms()
        return validation
    workflow_type = task.get("workflow_type") or "lightweight"
    current = task.get("current_step_id")
    next_step = step_contract(workflow_type, current).get("next_step")
    for step in task.get("steps") or []:
        if step.get("step_id") == current:
            step["status"] = "completed"
    if next_step:
        task["current_step_id"] = next_step
        for step in task.get("steps") or []:
            if step.get("step_id") == next_step:
                step["status"] = "running"
        task["status"] = "running"
        task["progress"] = {"current": step_index(workflow_type, next_step), "total": len(workflow_steps(workflow_type))}
    else:
        task["status"] = "completed"
        task["progress"] = {"current": len(workflow_steps(workflow_type)), "total": len(workflow_steps(workflow_type))}
    task["updated_at"] = now_ms()
    validation["advanced_to"] = task.get("current_step_id")
    validation["task_status"] = task.get("status")
    return validation


def required_assets(task):
    return [item for item in ((task or {}).get("assets") or []) if isinstance(item, dict) and item.get("required", True) is not False]


def required_asset_prompts_ready(task, text=""):
    assets = required_assets(task)
    if assets:
        return all(str(item.get("prompt") or item.get("approved_prompt") or "").strip()
                   and not is_placeholder_prompt(item.get("prompt") or item.get("approved_prompt"))
                   for item in assets)
    return bool(re.search(r"(提示词|prompt)", str(text or ""), re.I)) and not is_placeholder_prompt(text)


def required_assets_have_nodes(task, created=None):
    assets = required_assets(task)
    if assets:
        return all(str(item.get("canvas_node_id") or "").strip() for item in assets)
    return bool(created or (task or {}).get("canvas_nodes"))


def required_assets_approved(task):
    assets = required_assets(task)
    if assets:
        return all(str(item.get("review_status") or "") == "approved" for item in assets)
    return bool((task or {}).get("decisions")) and not any((i.get("status") == "waiting") for i in (task or {}).get("interactions") or [])


def provenance(task, turn, tool_call_id=""):
    return {
        "created_by": "agent",
        "conversation_id": (task or {}).get("conversation_id", "") if isinstance(task, dict) else "",
        "task_id": (task or {}).get("task_id", "") if isinstance(task, dict) else "",
        "step_id": (task or {}).get("current_step_id", "") if isinstance(task, dict) else "",
        "turn_id": (turn or {}).get("turn_id", "") if isinstance(turn, dict) else "",
        "tool_call_id": str(tool_call_id or ""),
        "source_asset_ids": [],
        "source_node_ids": [],
    }


def attach_provenance(args, task, turn, tool_call_id=""):
    safe = dict(args if isinstance(args, dict) else {})
    safe.setdefault("provenance", provenance(task, turn, tool_call_id))
    safe.setdefault("task_id", safe["provenance"].get("task_id"))
    safe.setdefault("step_id", safe["provenance"].get("step_id"))
    safe.setdefault("turn_id", safe["provenance"].get("turn_id"))
    return safe


def rollback_to_turn(task, turn_id):
    if not isinstance(task, dict) or not turn_id:
        return {"ok": False, "error": "missing task or turn_id"}
    turns = task.get("turns") or []
    idx = next((i for i, t in enumerate(turns) if t.get("turn_id") == turn_id), -1)
    if idx < 0:
        return {"ok": False, "error": "turn not found"}
    cutoff = set(t.get("turn_id") for t in turns[idx + 1:])
    for collection in ("tool_runs", "canvas_nodes", "canvas_mutations", "artifacts", "decisions", "interactions"):
        for item in task.get(collection) or []:
            if item.get("turn_id") in cutoff:
                item["status"] = "invalidated"
                item["invalidated_at"] = now_ms()
    task["turns"] = turns[:idx + 1]
    task["last_turn_id"] = turn_id
    task["status"] = "running"
    task["updated_at"] = now_ms()
    return {"ok": True, "invalidated_turns": len(cutoff)}


def load_tasks(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): v for k, v in data.items() if isinstance(v, dict)}
    except Exception:
        pass
    return {}


def save_tasks(path, store):
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(store if isinstance(store, dict) else {}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return True
    except Exception:
        return False

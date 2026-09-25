# -*- coding: utf-8 -*-
"""交互卡片回执域（后端拆分第33刀自 rh_official_proxy.py 逐字外移）：
回执登记（标记卡片已解决/会话级 receipt 记录/任务记账）与回执文本构造，
以及交互卡片读取接口。单例全部走属主模块属性链同对象直引（跨模块读写
互见，零注入——receipt 写 myridtv_agent_stop.RECEIPTS 与 stop/premature 检测同账本）。"""
import time
import agent_task_runtime as agent_runtime
import myridtv_agent_tools
import myridtv_agent_stop
import myridtv_agent_tasks
import myridtv_task_state


def submit_canvas_agent_interaction_receipt(payload):
    """接收用户对交互卡片的回执（点选/填写/确认）。
    只登记回执并标记卡片已解决；是否推进由前端用该回执重新发起一轮对话。"""
    payload = payload if isinstance(payload, dict) else {}
    session_id = str(payload.get("session_id") or payload.get("agent_session_id") or "").strip()
    card_id = str(payload.get("card_id") or "").strip()
    intent = str(payload.get("intent") or "").strip()
    if not session_id or not card_id:
        return {"ok": False, "error": "缺少 session_id 或 card_id"}
    receipt_selection = payload.get("selection")
    option_label = ""
    try:
        card = myridtv_agent_tools.CANVAS_AGENT_INTERACTIONS.get(str(session_id))
        if isinstance(card, dict) and receipt_selection is not None:
            for opt in card.get("options") or []:
                if isinstance(opt, dict) and str(opt.get("id") or "") == str(receipt_selection):
                    option_label = str(opt.get("label") or "").strip()
                    break
    except Exception:
        option_label = ""
    receipt = {
        "card_id": card_id,
        "selection": receipt_selection,
        "selection_label": option_label,
        "fields": payload.get("fields") if isinstance(payload.get("fields"), dict) else {},
        "confirmed": bool(payload.get("confirmed")),
        "submitted_at": int(time.time() * 1000),
        "resolved": True,
    }
    try:
        with myridtv_agent_stop.CANVAS_AGENT_RECEIPTS_LOCK:
            myridtv_agent_stop.CANVAS_AGENT_RECEIPTS[str(session_id)] = receipt
            # 同时把对应交互卡片标记为已解决
            card = myridtv_agent_tools.CANVAS_AGENT_INTERACTIONS.get(str(session_id))
            if card:
                card["resolved"] = True
    except Exception:
        pass
    try:
        with myridtv_task_state.TASKS_LOCK:
            task = next((t for t in myridtv_task_state.TASKS.values()
                         if isinstance(t, dict) and str(t.get("conversation_id") or "") == session_id
                         and t.get("status") in {"waiting_user", "running", "paused"}), None)
            if task:
                agent_runtime.record_decision(task, receipt)
                myridtv_task_state.persist_tasks_locked()
                myridtv_agent_tasks._agent_task_log("Decision", "task={} step={} card={} selection={} confirmed={}".format(
                    task.get("task_id"), task.get("current_step_id"), card_id, receipt_selection, receipt["confirmed"]))
    except Exception as exc:
        myridtv_agent_tasks._agent_task_log("Decision", "record failed card={} error={}".format(card_id, exc))
    # 构造回执文本，供前端作为新 user 消息发给 LLM 推进
    receipt_text = ""
    if intent == "confirm" and not receipt["confirmed"]:
        # 确认卡选了"需要修改"：明确让主链停下，收集用户具体修改意见，不要继续执行
        receipt_text = "需要修改，我还没满意。请先别继续往下走，听我要改哪里：{}(如需补充请直接告诉我)".format(receipt["selection"] or "")
    elif receipt["confirmed"]:
        receipt_text = "已确认，请继续执行。"
    elif receipt["selection"] is not None:
        suffix = "（{}）".format(option_label) if option_label else ""
        receipt_text = "我选择：{}{}".format(receipt["selection"], suffix)
    if receipt["fields"]:
        receipt_text = "我填写：{}".format("，".join("{}={}".format(k, v) for k, v in receipt["fields"].items()))
    return {
        "ok": True,
        "receipt": receipt,
        "receipt_text": receipt_text or "已收到。",
    }


def get_canvas_agent_interaction(session_id=""):
    """读取某会话当前待展示的交互卡片（供前端轮询/渲染）。"""
    try:
        with myridtv_agent_tools.CANVAS_AGENT_INTERACTIONS_LOCK:
            card = myridtv_agent_tools.CANVAS_AGENT_INTERACTIONS.get(str(session_id or ""))
        return {"ok": True, "interaction": card}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

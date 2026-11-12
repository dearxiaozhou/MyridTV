# -*- coding: utf-8 -*-
"""任务失败错误的中文解释器（2026-10-27 老王：「能不能把报错全部翻译或解释在日志里」）。

单一入口 explain_task_error(raw)：命中规则时返回一句"人话"（原因 + 建议动作），
未命中返回空串——调用方保留原文即可，绝不吞错、绝不瞎猜。
挂在 myridtv_task_state.update_task_state 的 failed 分支上，error_hint 随 state
进入任务 API / 画布日志面板 / 前端 toast，全渠道复用。

规则维护守则：
- 只写"有把握"的映射。语义拿不准的宁可留空（显示原文），不要编造原因。
- 新增错误码先在本机日志里 grep 真实文案（rh_official_proxy.log），按真实字符串写规则。
"""

import re

# (小写匹配词组/正则, 解释文案)。顺序即优先级，先命中先赢。
_RULES = [
    # --- 火山方舟 ---
    (("failed to parse request body",),
     "火山网关异步解析请求体失败（任务已受理但被拒）。多半是参考图走 base64 内嵌、把请求体顶到了 64MB 上限（火山官方原话：大文件请勿使用 Base64）。程序会先自动上传换公网直链，这条报错说明上传也没成（多为缺方舟 API Key 或图床不通）。改用素材库 asset://、或直接用公网图片链接；临时办法：降到 480p、或减少参考图数量。"),
    (("modelnotopen", "has not activated the model"),
     "该火山模型未开通。去火山方舟控制台→模型列表，找到这个模型点「开通」后重试（开通本身不扣费）。"),
    (("accountoverdue", "overdue balance", "欠费"),
     "火山引擎账户欠费或余额不足，请先到火山控制台结清账单。"),
    (("rate limit", "rpm", "tpm limit", "too many requests"),
     "火山接口限流（请求太密）。稍等一会儿再重试；批量任务建议减小并发。"),
    # --- RunningHub / 通用云端 ---
    (("content security audit", "内容安全审查", "sensitive content", "privacyinformation"),
     "内容安全审核未通过：提示词或参考图触发了平台风控（涉政/真人肖像/敏感元素常见）。改提示词、换掉疑似真人肖像的参考图再试。"),
    (("排队超时", "queued timeout", "queue timeout"),
     "云端排队超时未执行。当前并发任务太多，减少同时运行的任务数后重试。"),
    (("insufficient balance", "余额不足", "积分不足", "credit not enough", "insufficient credit"),
     "云平台余额/积分不足，请到对应平台控制台充值后再试。"),
    # --- 网络 ---
    (("ssleoferror", "unexpected_eof", "eof occurred", "bad record mac"),
     "TLS 握手被掐断——本机代理通道抽风的老症状（127.0.0.1:7897 间歇断 HTTPS）。直接重试往往就好；反复出现就检查/关闭系统代理。"),
    (("timed out", "timeout", "超时"),
     "请求超时。网络慢或云端排队，重试一次；反复超时可换个时段。"),
    (("connection reset", "connection aborted", "远程主机强迫关闭"),
     "连接被重置（网络抖动或云端主动断开）。直接重试一次。"),
    (("connection refused", "unable to connect", "getaddrhostfailed", "name resolution"),
     "连不上服务器：网络不通或域名解析失败，检查本机网络后重试。"),
    # --- 本地 ComfyUI ---
    (("cuda out of memory", "out of memory", "alloc memory"),
     "显卡显存不足。关掉其它占显存的程序（游戏/其它 ComfyUI 实例），或降低分辨率/批量数再试。"),
    (("no such node", "node not found", "missingnode", "prompt is invalid"),
     "工作流缺节点：本地 ComfyUI 没装该工作流需要的自定义节点，或节点版本不匹配。"),
]

# 正则型兜底：HTTP 状态码 → 一句话
_HTTP_RULES = [
    (re.compile(r"http 401|unauthorized|invalid api key|api key", re.I),
     "API Key 无效或过期，请到设置里检查对应平台的密钥。"),
    (re.compile(r"http 403|forbidden", re.I),
     "平台拒绝访问（Key 无该模型权限 / 账户状态异常），到对应控制台确认模型权限与账户。"),
    (re.compile(r"http 429", re.I),
     "请求太频繁被限流，稍等再试。"),
    (re.compile(r"http 5\d\d", re.I),
     "平台服务器错误（云端自己出问题），稍后重试；持续如此去看平台公告/工单。"),
]


def explain_task_error(raw):
    """返回中文解释（命中规则时），否则空串。"""
    text = str(raw or "").strip().lower()
    if not text:
        return ""
    for needles, hint in _RULES:
        for n in needles:
            if n in text:
                return hint
    for pat, hint in _HTTP_RULES:
        if pat.search(text):
            return hint
    return ""

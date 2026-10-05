# -*- coding: utf-8 -*-
"""MyridTV 静态交付域（后端拆分第41刀）：环境变量正整数 + 静态资源版本刷写。

逐字迁移自 rh_official_proxy.py 块 L(positive_env_int)..L(patch_static_versions_once 尾)。
STATIC_PATCHES 表在 configure(root) 内构造（ROOT 不重绑，值传安全；表体逐字，ROOT→root 参）；
STATIC_VERSION 走 getter 注入（版本串由兄弟会话频繁改版）。主文件留薄代理+loop+常量别名。
"""
import os
import re

_STATIC_PATCHES = {}
_static_version_getter = lambda: ""


def configure(root, static_version_getter):
    global _STATIC_PATCHES, _static_version_getter
    _static_version_getter = static_version_getter
    _STATIC_PATCHES = {
    root / "static" / "index.html": [
        "/static/canvas.html",
        "/static/smart-canvas.html",
        "/static/js/i18n.js",
        "/static/api-settings.html",
        "/static/comfyui-settings.html",
        "/static/asset-manager.html",
    ],
    root / "static" / "smart-canvas.html": ["/static/css/smart-canvas.css", "/static/js/smart-canvas.js", "/static/js/canvas-node-registry.js", "/static/js/canvas-draft-store.js", "/static/js/canvas-overlay-registry.js", "/static/js/canvas-viewport-engine.js", "/static/js/canvas-render-scheduler.js", "/static/js/canvas-comfy-job-engine.js", "/static/js/canvas-agent-history-store.js", "/static/js/canvas-artifact-model.js", "/static/js/canvas-artifact-view.js", "/static/js/canvas-agent-message-render.js", "/static/js/canvas-rh-controls.js", "/static/js/canvas-rh-workflow-builder.js", "/static/js/canvas-smart-task-supervisor.js", "/static/js/canvas-generated-output-naming.js", "/static/js/canvas-provider-catalog.js", "/static/js/canvas-dynamic-param-engine.js", "/static/js/canvas-agent-session-panel.js", "/static/js/canvas-history-archive-group.js", "/static/js/canvas-comfy-job-submitter.js", "/static/js/canvas-redirect-lines.js", "/static/js/canvas-agent-reference-intake.js", "/static/js/canvas-state-hub.js", "/static/js/canvas-agent-toggle-drag.js", "/static/js/canvas-agent-model-settings.js", "/static/js/canvas-agent-send-chain.js", "/static/js/canvas-smart-cascade-runner.js", "/static/js/canvas-generation-runner.js", "/static/js/canvas-media-helpers.js", "/static/js/canvas-video-comfy-params.js", "/static/js/canvas-node-body-html.js", "/static/js/canvas-engine-dispatch.js", "/static/js/canvas-object-ref-picker.js", "/static/js/canvas-merge-sync.js", "/static/js/canvas-smartloop-data.js", "/static/js/canvas-comfy-controls.js", "/static/js/canvas-param-controls.js", "/static/js/canvas-prompt-library-picker.js", "/static/js/canvas-unified-picker.js", "/static/js/canvas-spec-controls.js", "/static/js/canvas-interaction-observer.js", "/static/js/canvas-interaction-machine.js", "/static/js/i18n.js"],
    root / "static" / "canvas.html": [
        "/static/css/canvas.css",
        "/static/css/canvas-prism.css",
        "/static/js/canvas.js",
        "/static/js/canvas-prism.js",
        "/static/js/i18n.js",
    ],
root / "static" / "api-settings.html": ["/static/js/api-settings.js", "/static/css/api-settings.css", "/static/js/api-settings-provider-repair.js", "/static/js/i18n.js"],
root / "static" / "comfyui-settings.html": ["/static/js/comfyui-settings.js", "/static/css/comfyui-settings.css", "/static/js/i18n.js"],
root / "static" / "asset-manager.html": ["/static/js/asset-manager.js", "/static/css/asset-manager.css", "/static/js/i18n.js"],
    }


def positive_env_int(name, default, minimum=1, maximum=None):
    try:
        value = int(str(os.environ.get(name) or "").strip() or default)
    except Exception:
        value = default
    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


COMFY_WORKFLOW_POLL_TIMEOUT_SECONDS = positive_env_int("COMFY_WORKFLOW_POLL_TIMEOUT_SECONDS", 3600, 60, 21600)
RUNNINGHUB_DEFAULT_IMAGE_MODELS = [
    "seedream-v5-lite/text-to-image",
    "seedream-v5-lite/image-to-image",
    "rhart-image-g-2-official/text-to-image",
    "rhart-image-g-2-official/image-to-image",
    "rhart-image-g-2/text-to-image",
    "rhart-image-g-2/image-to-image",
    "rhart-image-n-g31-flash/image-to-image",
    "rhart-image-n-pro-official/edit",
]


def patch_static_versions_once():
    for path, urls in _STATIC_PATCHES.items():
        try:
            text = path.read_text(encoding="utf-8")
            updated = text
            for url in urls:
                # 兼容两种 URL 形态：/x.css?v= 与 /x.css?cb=xxx&v= （后者曾导致版本号永远刷不到）
                pattern = re.compile(rf"({re.escape(url)}\?(?:[^\"'<>\s]*&)?v=)[^\"'<>\s]+")
                updated = pattern.sub(lambda match: f"{match.group(1)}{_static_version_getter()}", updated)
                # 纯 /x.js?cb=xxx（整串查询里没有 v= 段）：补挂 &v=VERSION，纳入刷版。
                # 双形态 ?cb=a&v=b 上面 v 分支已刷，这里回调见 &v= 原样返回，不重复追加；
                # 二次运行本分支不再命中（已有 &v=）→ 幂等收敛。
                q_pat = re.compile("(" + re.escape(url) + r"\?[A-Za-z0-9._~%=?/&+-]+)")
                def _fix_cb(match):
                    q = match.group(1)
                    if '&v=' in q or '?v=' in q or '?cb=' not in q:
                        return q
                    return f"{q}&v={_static_version_getter()}"
                updated = q_pat.sub(_fix_cb, updated)
            if updated != text:
                path.write_text(updated, encoding="utf-8")
        except Exception:
            pass

# -*- coding: utf-8 -*-
"""
e2e_canvas_video_refmode.py
===========================
守护视频参考模式「官方极简收敛」（2026-09-23）：

官方事实（火山方舟 Seedance 2.0/2.5 创建视频任务 API）：
- 三种互斥场景：文生视频 / 图生视频(首帧、首尾帧) / 全模态参考生视频
- 编辑、延长不是新端点，仍走同一 content 结构，靠提示词句式区分：
  「严格编辑视频N」「向前/向后延长视频N」，且禁用「参考视频N」句式（会被误判为参考任务）

画布收敛后的 UI 枚举 = mixed(全能参考) / first_last(首尾帧) / video_edit(视频编辑) / video_extend(视频延长)
旧值 video_only / frame_extract 必须映射到 mixed（历史节点数据兼容）。

断言（全 mock fetch，不烧配额）：
1. videoReferenceModeValue 兼容映射正确
2. 参考模式弹层渲染 4 个选项、无 video_only/frame_extract
3. 全能参考提交：images role=reference_image + videos + reference_mode='mixed'
4. 首尾帧提交：role first_frame/last_frame、reference_mode='first_last'
5. 视频编辑提交：prompt 被包成「严格编辑视频1：…」且不含裸「参考视频1」句式冲突；videos 只留 1 段
6. 视频延长提交：默认「向后延长视频1：」；videoExtendMode=before → 「向前延长视频1：」
7. 编辑/延长无源视频 → 抛错提示先连入源视频
8. 非 Seedance 模型选编辑 → toast + 按 mixed 提交
"""
import json, sys
from playwright.sync_api import sync_playwright

import os

BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217")


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} - {label} | {str(detail)[:160]}")
    return 1 if ok else 0


def main():
    failures = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe",
            headless=True,
            args=["--no-sandbox"],
        )
        ctx = browser.new_context(viewport={"width": 1680, "height": 980})
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        def rc(route):
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"proxy": {"base_url": BASE}}))
        page.route("**/static/app_config.json*", rc)
        page.goto(f"{BASE}/smart-canvas.html", wait_until="networkidle")
        page.wait_for_timeout(1500)

        # mock 提交端点：记录 payload 并返回假任务
        page.evaluate("""() => {
            window.__vidPayloads = [];
            const realFetch = window.fetch.bind(window);
            window.fetch = async (input, init) => {
                const url = String(typeof input === 'string' ? input : (input && input.url) || '');
                if (url.includes('/api/canvas-video')) {
                    let body = {};
                    try { body = JSON.parse((init && init.body) || '{}'); } catch(e) {}
                    window.__vidPayloads.push(body);
                    return new Response(JSON.stringify({task_id: 'fakevid_1', status: 'queued'}), {status: 200, headers: {'Content-Type':'application/json'}});
                }
                return realFetch(input, init);
            };
            window.__toasts = [];
            const realToast = window.toast;
            window.toast = (msg) => { window.__toasts.push(String(msg||'')); if (realToast) {} };
        }""")

        # 1. 枚举兼容映射
        mapping = page.evaluate("""() => {
            return {
                v1: videoReferenceModeValue({videoReferenceMode:'video_only'}),
                v2: videoReferenceModeValue({videoReferenceMode:'frame_extract'}),
                v3: videoReferenceModeValue({videoReferenceMode:'mixed'}),
                v4: videoReferenceModeValue({videoReferenceMode:'video_edit'}),
                v5: videoReferenceModeValue({videoReferenceMode:'video_extend'}),
                v6: videoReferenceModeValue({videoReferenceMode:'first_last'}),
                v7: videoReferenceModeValue({videoReferenceMode:'', videoUseFrameRoles:true}),
                v8: videoReferenceModeValue({})
            };
        }""")
        want = ['mixed','mixed','mixed','video_edit','video_extend','first_last','first_last','mixed']
        got = [mapping[f'v{i}'] for i in range(1,9)]
        failures += not check("旧值映射/新枚举/兼容回退全对", got == want, str(got))

        # 2. 弹层选项
        opts = page.evaluate("""() => {
            const html = CanvasParamControls.renderVideoReferenceModeControl();
            const vals = [...html.matchAll(/data-smart-value="([^"]+)"/g)].map(m => m[1]);
            return {vals, hasOld: html.includes('frame_extract') || /data-smart-value="video_only"/.test(html),
                    hasDesc: html.includes('opt-desc'),
                    labels: [...html.matchAll(/data-smart-value="[^"]*"><span>([^<]+)<\/span>/g)].map(m => m[1])};
        }""")
        failures += not check("弹层 4 选项=官方枚举、无旧值、无描述行(用户定稿:只用官方文案)",
                      opts["vals"] == ["mixed","first_last","video_edit","video_extend"]
                      and not opts["hasOld"] and not opts["hasDesc"]
                      and opts["labels"] == ["全能参考","首尾帧","视频编辑","视频延长"], str(opts))

        # 通用提交驱动：构造 refs + settings，直调 runApiVideoGeneration
        submit_js = """(cfg) => {
            // 用实例磁盘上真实存在的素材（后端会校验文件存在性）
            const IMG = '/assets/input/ai_ref_b402b83fb32e.png';
            const VID = '/assets/output/3D预演测试/videos/previz_0920_220439.mp4';
            const imgRefs = cfg.imgCount ? Array.from({length: cfg.imgCount}, (_,i) => ({url:IMG, name:'图'+(i+1), kind:'image'})) : [];
            const vidRefs = cfg.vidCount ? Array.from({length: cfg.vidCount}, (_,i) => ({url:VID, name:'视频'+(i+1), kind:'video', videoUrl:VID})) : [];
            const refs = [...imgRefs, ...vidRefs];
            const rs = Object.assign({
                engine:'volcengine', apiKind:'video',
                videoProvider:'volcengine', videoModel:'doubao-seedance-2-0-260128',
                videoReferenceMode: cfg.mode, videoDuration: 5, videoAspect:'16:9',
                // 模拟 UI 链路 normalizeHiddenVideoToggles 的联动 flag
                videoUseFrameRoles: cfg.mode === 'first_last'
            }, cfg.extra || {});
            window.__vidPayloads = [];
            return runApiVideoGeneration(cfg.prompt || '角色在雨中回眸', refs, rs)
                .then(() => ({payload: window.__vidPayloads[0] || null}))
                .catch(e => ({err: String(e && e.message || e)}));
        }"""

        # 3. 全能参考
        r3 = page.evaluate(submit_js, {"mode": "mixed", "imgCount": 2, "vidCount": 1})
        pl = r3.get("payload") or {}
        roles = [i.get("role") for i in (pl.get("images") or [])]
        failures += not check("全能参考：images 保留+videos 提交+mode=mixed",
                      pl.get("reference_mode") == "mixed" and len(pl.get("images") or []) == 2 and len(pl.get("videos") or []) == 1
                      and "first_frame" not in roles, json.dumps(pl, ensure_ascii=False)[:200])

        # 4. 首尾帧
        r4 = page.evaluate(submit_js, {"mode": "first_last", "imgCount": 2, "vidCount": 0})
        pl = r4.get("payload") or {}
        roles = [i.get("role") for i in (pl.get("images") or [])]
        failures += not check("首尾帧：first_frame/last_frame + mode=first_last",
                      pl.get("reference_mode") == "first_last" and roles == ["first_frame","last_frame"], str(roles))

        # 5. 视频编辑（2 段源视频→留 1 段 + 句式）
        r5 = page.evaluate(submit_js, {"mode": "video_edit", "imgCount": 0, "vidCount": 2, "prompt": "把桌面的零件换成工具箱"})
        pl = r5.get("payload") or {}
        failures += not check("视频编辑：严格编辑句式+单源视频+不写「参考视频」",
                      pl.get("reference_mode") == "video_edit"
                      and str(pl.get("prompt","")).startswith("请勿复述视频1原内容。严格编辑视频1：")
                      and "参考视频" not in str(pl.get("prompt",""))
                      and len(pl.get("videos") or []) == 1, json.dumps(pl.get("prompt"), ensure_ascii=False)[:160])

        # 6. 视频延长（后延/前延）
        r6a = page.evaluate(submit_js, {"mode": "video_extend", "imgCount": 0, "vidCount": 1, "prompt": "五人终于见面友好聊天"})
        pl = r6a.get("payload") or {}
        r6b = page.evaluate(submit_js, {"mode": "video_extend", "imgCount": 0, "vidCount": 1, "prompt": "给白衣男子过肩镜头", "extra": {"videoExtendMode": "before"}})
        plb = r6b.get("payload") or {}
        failures += not check("视频延长：默认向后句式",
                      str(pl.get("prompt","")).startswith("请勿复述视频1原内容。向后延长视频1："),
                      json.dumps(pl.get("prompt"), ensure_ascii=False)[:140])
        failures += not check("向前延长句式", str(plb.get("prompt","")).find("向前延长视频1") >= 0,
                      json.dumps(plb.get("prompt"), ensure_ascii=False)[:140])

        # 7. 无源视频 → 抛错
        r7 = page.evaluate(submit_js, {"mode": "video_edit", "imgCount": 1, "vidCount": 0})
        failures += not check("编辑无源视频 → 明确报错提示连入",
                      "源视频" in str(r7.get("err","")) and not r7.get("payload"), str(r7))

        # 8. 非 Seedance 模型（comfly）→ toast 降级 mixed
        r8 = page.evaluate("""(cfg) => {
            const VID = '/assets/output/3D预演测试/videos/previz_0920_220439.mp4';
            const refs = [{url:VID, name:'视频1', kind:'video', videoUrl:VID}];
            window.__vidPayloads = []; window.__toasts = [];
            return runApiVideoGeneration('测试', refs, {
                engine:'api', apiKind:'video', videoProvider:'comfly', videoModel:'kling-v2',
                videoReferenceMode:'video_edit', videoDuration:5, videoAspect:'16:9'
            }).then(() => ({payload: window.__vidPayloads[0] || null, toasts: window.__toasts}))
              .catch(e => ({err: String(e && e.message || e)}));
        }""", {})
        pl8 = r8.get("payload") or {}
        failures += not check("非 Seedance 选编辑 → toast+按 mixed 提交",
                      pl8.get("reference_mode") == "mixed" and any("Seedance" in t for t in (r8.get("toasts") or [])), json.dumps(r8, ensure_ascii=False)[:220])

        real_errors = [e for e in errors if "WebSocket" not in e and "stats" not in e]
        failures += not check("无 JS 报错", len(real_errors) == 0, str(real_errors[:3]))

        browser.close()

    total = 10
    print(f"\nRESULT: {total - failures}/{total}")
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()

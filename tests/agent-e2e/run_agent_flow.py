# -*- coding: utf-8 -*-
"""一键 Agent→Canvas 验收命令（#38）。

覆盖完整链路：Asset 发现 → Prompt 生成 → Canvas 提交 → Video Prompt → Edge，
以及真实后端工具代码是否经 CanvasMutationManager 收口。

用法（项目根目录）：
  python tests/agent-e2e/run_agent_flow.py

注意：
- 确定性 E2E 任何 python3 可跑（驱动真实生产 gate 代码）。
- 后端接线测试需能 import rh_official_proxy（依赖 websockets 等）；
  若环境缺依赖，返回码 2，本命令将其标记为 ENV-LIMITED 而非 FAIL（诚实标注，
  不写"应该可以"）。
- 真实 LLM Agent Smoke Test：见 run_agent_e2e.py 头部，沙箱出站被拦截，NOT RUN。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _run(script):
    print("\n" + "#" * 64)
    print("# RUN: %s" % script)
    print("#" * 64)
    try:
        p = subprocess.run([sys.executable, os.path.join(HERE, script)],
                           capture_output=True, text=True, timeout=180)
    except Exception as e:  # pragma: no cover
        print("RUN ERROR: %s" % e)
        return 99
    sys.stdout.write(p.stdout)
    if p.stderr.strip():
        sys.stdout.write(p.stderr[-3000:])
    return p.returncode


def main():
    c1 = _run("run_agent_e2e.py")
    c2 = _run("test_backend_wiring.py")
    c3 = _run("test_short_drama_defer.py")

    print("\n" + "=" * 64)
    print("AGENT FLOW E2E — ONE-SHOT ACCEPTANCE")
    print("=" * 64)
    print("  Deterministic E2E (mock-replay, real gate code): %s"
          % ("PASS" if c1 == 0 else "FAIL"))
    if c2 == 0:
        bw = "PASS"
    elif c2 == 2:
        bw = "ENV-LIMITED (backend deps missing; gate logic proven by deterministic E2E)"
    else:
        bw = "FAIL"
    print("  Backend wiring (real tool -> manager)        : %s" % bw)
    print("  Short-drama board defer (confirm vs execute) : %s"
          % ("PASS" if c3 == 0 else "FAIL"))
    print("  Real LLM Agent Smoke Test                     : NOT RUN (sandbox outbound blocked)")
    overall = (c1 == 0 and c2 == 0 and c3 == 0)
    print("\n  FINAL RESULT: %s" % ("PASS" if overall else "FAIL"))
    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()

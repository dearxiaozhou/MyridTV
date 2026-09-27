# -*- coding: utf-8 -*-
"""Architecture fitness gate for the canvas frontend.

Baseline: Stage 2 acceptance threshold after the canvas responsibility extractions.
The legacy canvas entry script must stay at or below 17,570 lines. Extracted canvas
modules should stay small enough to review as a single responsibility.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
JS_DIR = ROOT / "_internal" / "static" / "js"
SMART_CANVAS = JS_DIR / "smart-canvas.js"
SMART_CANVAS_LINE_LIMIT = 17_570
CANVAS_MODULE_LINE_LIMIT = 1_200


def line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def main() -> int:
    if not SMART_CANVAS.is_file():
        print(f"FAIL - missing canvas entry script: {SMART_CANVAS}")
        return 1

    entry_lines = line_count(SMART_CANVAS)
    modules = sorted(JS_DIR.glob("canvas-*.js"), key=line_count, reverse=True)
    too_large = [(path, line_count(path)) for path in modules if line_count(path) > CANVAS_MODULE_LINE_LIMIT]

    print(f"Canvas architecture | smart-canvas.js: {entry_lines:,}/{SMART_CANVAS_LINE_LIMIT:,} lines")
    print(f"Extracted canvas modules: {len(modules)} | largest: {line_count(modules[0]) if modules else 0} lines")
    if entry_lines > SMART_CANVAS_LINE_LIMIT:
        print("FAIL - smart-canvas.js grew past its frozen baseline; extract or consolidate before adding more.")
        return 1
    if too_large:
        for path, lines in too_large:
            print(f"FAIL - {path.name} is {lines:,} lines (limit {CANVAS_MODULE_LINE_LIMIT:,})")
        return 1
    print("PASS - entry script did not grow; extracted modules remain reviewable")
    return 0


if __name__ == "__main__":
    sys.exit(main())

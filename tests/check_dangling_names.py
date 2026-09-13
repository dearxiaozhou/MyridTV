"""悬空名字检查：找出"用了但从没绑定过"的全局名字。

背景（真实事故）：把函数从一个巨型文件拆到新模块时，若原文件里"夹在两个函数之间"的
class / 常量被一起搬走、却没有 import 回来，`raise ApiError(...)` 这类代码不会在启动时报错，
只在**真正走到那条错误分支**时抛 NameError —— 语法检查、导入冒烟、正常路径全部照过，属于
最阴的一类回归。本脚本用 AST 静态扫一遍，把它挡在提交前。

用法：
    python tests/check_dangling_names.py                # 默认检查仓库根目录 *.py + tests/*.py
    python tests/check_dangling_names.py path1.py ...   # 指定文件
退出码：0 = 干净，1 = 发现悬空名字（打印 文件:行: 名字）。
"""

from __future__ import annotations

import ast
import builtins
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# 根级 `_xxx.py` 是本地开发残件（打包也会被排除），不纳入门禁
DEFAULT_TARGETS = sorted(
    [p for p in ROOT.glob("*.py") if not p.name.startswith("_")]
    + [p for p in (ROOT / "tests").glob("*.py") if not p.name.startswith("_")]
)
KNOWN = set(dir(builtins)) | {"__name__", "__file__", "__doc__", "__builtins__", "__package__", "__loader__", "__spec__"}


def bindings_of(tree: ast.AST) -> set:
    """收集本文件里出现过的所有"绑定名"（任何作用域、任何形式）。"""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if isinstance(node.ctx, (ast.Store, ast.Del)):
                names.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add((alias.asname or alias.name.split(".")[0]))
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    names.add("*")  # 星号导入：整文件豁免
                names.add(alias.asname or alias.name)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.Global) or isinstance(node, ast.Nonlocal):
            names.update(node.names)
        elif isinstance(node, ast.MatchAs) or isinstance(node, ast.MatchStar):
            if getattr(node, "name", None):
                names.add(node.name)
    return names


def check(path: Path):
    try:
        source = path.read_text(encoding="utf-8")
    except Exception as exc:
        return [(path.name, 0, "unreadable: %s" % exc)]
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [(path.name, exc.lineno or 0, "SyntaxError: %s" % exc.msg)]
    bound = bindings_of(tree)
    if "*" in bound:
        return []
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id not in bound and node.id not in KNOWN:
                problems.append((path.name, node.lineno, node.id))
    return problems


def main(argv):
    targets = [Path(a) for a in argv[1:]] or DEFAULT_TARGETS
    total = 0
    for path in targets:
        problems = check(Path(path))
        for name, line, detail in problems:
            print("  [悬空名字] %s:%s %s" % (name, line, detail))
            total += 1
    if total:
        print("check_dangling_names FAILED: %d 处" % total)
        return 1
    print("check_dangling_names ok: %d 个文件" % len(targets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

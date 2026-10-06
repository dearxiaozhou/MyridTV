# -*- coding: utf-8 -*-
"""前端接线检查（B 门禁）：configure 注入表的 deps↔键一致 + 值可解析性。

背景（真实事故两类，静态全漏、全靠 CDP 兜底）：
1) 第十九刀：configure 块写了 `JimengPendingSignal: JimengPendingSignal`——该标识符声明在
   另一模块 IIFE 内、主文件作用域不可见，configure 执行即 ReferenceError、deps 全空，
   症状却是下游各模块 "deps.xxx is not a function"，误导排查。
2) 切刀后模块用了 deps.foo 但注入表没给 foo（漏注入=运行时定时炸弹）。
本脚本对全量模块静态执行这两条断言（含 D("name") 串通道）：
  A. 每个模块用到的 deps.<name> / D("<name>") ⊆ 主文件里对该模块命名空间的注入键集合；
  B. 注入表每个值里引用到的裸标识符，必须能在主文件顶层声明 / 某模块导出的全局命名空间 /
     浏览器全局 / 同块注入键 中解析到（箭头惰性值同样查——调用时才炸也算雷）。

用法：python tests/check_frontend_wiring.py [入口html]   退出码 0=干净 1=有雷。
"""
from __future__ import annotations
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS_DIR = ROOT / '_internal' / 'static' / 'js'

BROWSER_GLOBALS = {
    'window','document','globalThis','console','fetch','location','navigator','history','localStorage',
    'sessionStorage','setTimeout','setInterval','clearTimeout','clearInterval','requestAnimationFrame',
    'cancelAnimationFrame','URL','Blob','FormData','FileReader','WebSocket','Image','Audio','Event',
    'CustomEvent','MutationObserver','IntersectionObserver','ResizeObserver','AbortController','TextEncoder',
    'PerformanceObserver','matchMedia','getComputedStyle','alert','confirm','prompt','btoa','atob','crypto',
    'structuredClone','performance','screen','devicePixelRatio','ResizeObserver','BroadcastChannel','Worker',
    'Math','JSON','Object','Array','String','Number','Boolean','Set','Map','WeakMap','WeakSet','Promise',
    'Error','TypeError','RangeError','RegExp','Date','Symbol','Proxy','Reflect','Intl','isNaN','isFinite',
    'parseInt','parseFloat','encodeURIComponent','decodeURIComponent','undefined','null','true','false','NaN',
    'Infinity','this','arguments','Function','File','DragEvent','KeyboardEvent','MouseEvent','PointerEvent',
    'WheelEvent','TouchEvent','ClipboardItem','DataTransfer','Node','Element','HTMLElement','SVGElement',
    'CSS','DOMParser','XMLSerializer','Text','Comment','DocumentFragment','HTMLInputElement','lucide','echarts','Chart',
}

def read(p): return p.read_text(encoding='utf-8', errors='ignore')

def strip_code(text):
    """去字符串/模板/注释，返回代码区拼接（字符串整体删掉，模板 ${...} 保留为代码）。"""
    spans = []
    out = []
    s = text
    i, n = 0, len(s)
    def skip_str(k):
        q = s[k]; j = k+1
        while j < n:
            if s[j] == '\\': j += 2; continue
            if s[j] == q: return j+1
            j += 1
        return n
    while i < n:
        c = s[i]
        if c == '/' and i+1 < n and s[i+1] == '/':
            while i < n and s[i] != '\n': i += 1
            continue
        if c == '/' and i+1 < n and s[i+1] == '*':
            k = s.find('*/', i+2); i = (k+2) if k >= 0 else n
            continue
        if c in '"\'':
            i = skip_str(i); continue
        if c == '`':
            # 模板：文本段丢弃，${...} 内当代码递归扫描
            j = i+1; seg_start = None
            while j < n:
                if s[j] == '\\': j += 2; continue
                if s[j] == '`': break
                if s[j] == '$' and j+1 < n and s[j+1] == '{':
                    depth = 1; k = j+2
                    inner_start = k
                    while k < n and depth:
                        cc = s[k]
                        if cc in '"\'':
                            k = skip_str(k); continue
                        if cc == '`':
                            # 嵌套模板：整体跳过到闭合（保守）
                            k2 = k+1
                            while k2 < n and s[k2] != '`':
                                if s[k2] == '\\': k2 += 1
                                k2 += 1
                            k = k2+1; continue
                        if cc == '{': depth += 1
                        elif cc == '}': depth -= 1
                        k += 1
                    out.append(s[inner_start:k-1])
                    j = k; continue
                j += 1
            i = j+1; continue
        out.append(c); i += 1
    return ''.join(out)

def main_decl_names(main_text):
    """主文件全部顶层可解析名。注意：本库代码存在一行内收尾+起新函数（}function x(){），
    不能限定行首——全文件 function/const/let/var/class 声明名一律收（顶层 IIFE 脚本里
    它们都在同一全局作用域，箭头体内再绑定的属于值内 bound 豁免范畴）。"""
    names = set()
    for m in re.finditer(r'(?<![\w$.])(?:async\s+)?function\s+([A-Za-z_$][\w$]*)', main_text):
        names.add(m.group(1))
    for m in re.finditer(r'(?<![\w$.])(?:const|let|var|class)\s+([A-Za-z_$][\w$]*)', main_text):
        names.add(m.group(1))
    return names

def extract_configure_blocks(main_text):
    """返回 {Namespace: {key: value_text}}，取 `if(globalThis.X){X.configure({...})}` 与裸 `X.configure({...})`。"""
    blocks = {}
    for m in re.finditer(r'\b([A-Z][A-Za-z0-9_$]*)\.configure\(\{', main_text):
        ns = m.group(1)
        i = m.end(); depth = 1; j = i
        s = main_text
        while j < len(s) and depth:
            c = s[j]
            if c == '{': depth += 1
            elif c == '}': depth -= 1
            elif c in '"\'':
                q = c; j += 1
                while j < len(s) and s[j] != q:
                    if s[j] == '\\': j += 1
                    j += 1
            elif c == '`':
                j += 1
                while j < len(s) and s[j] != '`':
                    if s[j] == '\\': j += 1
                    j += 1
            elif c == '/' and j+1 < len(s) and s[j+1] == '/':
                while j < len(s) and s[j] != '\n': j += 1
                continue
            j += 1
        body = s[i:j-1]
        kvs = {}
        body_nc = re.sub(r'//[^\n]*', '', body)
        body_nc = re.sub(r'/\*.*?\*/', '', body_nc, flags=re.S)
        # 只收深度0的键（嵌套对象里的 k: v 不是注入键，如 selectedImage={nodeId, index:imageIndex}）
        cand = []
        d0 = 0
        pos = 0
        while pos < len(body_nc):
            c = body_nc[pos]
            if c in '{[(': d0 += 1; pos += 1; continue
            if c in '}])': d0 -= 1; pos += 1; continue
            if c in '"\'':
                q = c; pos += 1
                while pos < len(body_nc) and body_nc[pos] != q:
                    if body_nc[pos] == '\\': pos += 1
                    pos += 1
                pos += 1; continue
            if d0 == 0:
                km = re.match(r'([A-Za-z_$][\w$]*)\s*:\s*', body_nc[pos:])
                if km and (pos == 0 or not re.search(r'[\w$.]$', body_nc[max(0,pos-1):pos])):
                    cand.append((km.group(1), pos + km.end()))
                    pos += km.end(); continue
            pos += 1
        for idx, (key, vstart) in enumerate(cand):
            # 值到同深度0的下一键起点前（再按深度0逗号截）
            lim = cand[idx+1][1] - len(key) - 1 if False else len(body_nc)
            d1 = 0; vend = vstart; s2 = body_nc
            while vend < len(s2):
                c = s2[vend]
                if c in '([{': d1 += 1
                elif c in ')]}':
                    if d1 == 0: break
                    d1 -= 1
                elif c == ',' and d1 == 0: break
                elif c in '"\'':
                    q = c; vend += 1
                    while vend < len(s2) and s2[vend] != q:
                        if s2[vend] == '\\': vend += 1
                        vend += 1
                elif c == '`':
                    vend += 1
                    while vend < len(s2) and s2[vend] != '`':
                        if s2[vend] == '\\': vend += 1
                        vend += 1
                vend += 1
            seg = body_nc[vstart:vend].strip().rstrip(',')
            kvs.setdefault(key, seg)
        blocks.setdefault(ns, {}).update(kvs)
    return blocks

def module_deps_usage(mod_text):
    """收集"无兜底"的 deps 用法=真雷候选：deps.X(...) 直接调用、或 D("X") 读取。
    带 `|| 默认值` 兜底、`Number(deps.X) || n` 的可选注入放行——同一名字只要有一次
    无兜底使用即计入。"""
    used = set()
    for m in re.finditer(r'(?<![\w$])deps\.([A-Za-z_$][\w$]*)', mod_text):
        x = m.group(1)
        tail = mod_text[m.end():m.end()+80].lstrip()
        # 有兜底形态：|| xxx / ) || / } 后接 || —— 逐出现点判：若该出现点同语句含 `||` 兜底则放行
        line = mod_text[:m.start()].split('\n')[-1] + tail.split('\n')[0]
        if '||' in line:
            continue
        used.add(x)
    used |= set(re.findall(r'\bD\("([A-Za-z_$][\w$]*)"\)', mod_text))
    return used

JS_RESERVED = {'function','return','const','let','var','if','else','for','while','do','async','await','new',
    'this','typeof','instanceof','in','of','true','false','null','undefined','try','catch','finally','throw',
    'switch','case','break','continue','default','delete','void','arguments','class','extends','super','yield',
    'get','set'}

def identifier_tokens(value_text):
    """值里引用到的裸标识符。先摘除该值内部绑定的名字（形参/局部 const/let/解构/ catch），
    否则 (n, urls) => f(urls) 会把形参当外部引用误报。"""
    code = strip_code(value_text)
    bound = set()
    # 箭头参数：匹配 `(...) =>` 与 `x =>` 两种头（值首与内层都算）
    for m in re.finditer(r'\(([^()]*)\)\s*=>', code):
        for p in m.group(1).split(','):
            p = p.strip().split('=')[0].strip().lstrip('{[ ').rstrip('} ]').strip()
            for pp in re.split(r'[,\s]+', p):
                if re.match(r'^[A-Za-z_$][\w$]*$', pp or ''): bound.add(pp)
    for m in re.finditer(r'(?<![\w$.])([A-Za-z_$][\w$]*)\s*=>', code):
        bound.add(m.group(1))
    for m in re.finditer(r'\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)', code):
        bound.add(m.group(1))
    # 解构 const {a, b} = / const [a,b] =
    for m in re.finditer(r'\b(?:const|let|var)\s+\{([^}]*)\}\s*=', code):
        for p in m.group(1).split(','):
            p = p.strip().split(':')[-1].split('=')[0].strip()
            if re.match(r'^[A-Za-z_$][\w$]*$', p or ''): bound.add(p)
    for m in re.finditer(r'\bcatch\s*\(\s*([A-Za-z_$][\w$]*)', code):
        bound.add(m.group(1))
    # getter/setter 属性名：get foo(){}/set foo(v){} 的 foo 是属性键非自由引用
    for m in re.finditer(r'\b(?:get|set)\s+([A-Za-z_$][\w$]*)\s*(?:\([^)]*\))?\s*\{', code):
        bound.add(m.group(1))
    toks = set()
    for m in re.finditer(r'(?<![\w$.])([A-Za-z_$][\w$]*)(?![\w$])', code):
        rest = code[m.end():m.end()+2]
        if rest.lstrip(' ').startswith(':'):   # 对象键/三元/标签：先取全名再判，防回溯截断
            continue
        toks.add(m.group(1))
    # typeof X 守卫的名字运行时未必存在（if(typeof f==='function') 就是防这个），豁免
    guarded = set(re.findall(r'\btypeof\s+([A-Za-z_$][\w$]*)', code))
    # 对象字面量键形态 name: 已在上面负向前瞻去掉；裸简写属性 { imageIndex } 无法静态分辨，
    # 由「值尾非:」规则保留为引用——保守可接受（注入表出现裸简写的场景极少）。
    return toks - bound - guarded - JS_RESERVED

def module_uses_configure_contract(mod_raw):
    """模块级 deps 单例契约：有 `const deps = {}` 且 configure 里 Object.assign(deps,...)。
    仅这类模块的 deps.X 来自主文件 `<NS>.configure({...})`；createWriter(deps) 这类
    形参式 DI（如 canvas-draft-store）的 deps 由调用点内联对象满足，不属本契约，跳过 A。"""
    return bool(re.search(r'\bconst\s+deps\s*=\s*\{\s*\}', mod_raw)) and \
           bool(re.search(r'Object\.assign\(\s*deps\s*,', mod_raw))

def main(argv):
    entry_html = Path(argv[1]) if len(argv) > 1 else ROOT / '_internal' / 'static' / 'smart-canvas.html'
    if not entry_html.exists():
        print('入口 html 不存在: %s' % entry_html); return 1
    html = read(entry_html)
    order = re.findall(r'<script src="/static/js/([\w.-]+\.js)', html)
    if 'smart-canvas.js' not in order:
        print('入口未引用 smart-canvas.js'); return 1
    main_idx = order.index('smart-canvas.js')
    mod_files = [f for f in order[:main_idx] if (JS_DIR / f).exists()]
    main_text = read(JS_DIR / 'smart-canvas.js')
    decls = main_decl_names(main_text)
    cfg = extract_configure_blocks(main_text)

    # 模块导出的全局命名空间：global.X = / globalThis.X =
    ns_exported = set()
    for f in mod_files + ['smart-canvas.js']:
        t = read(JS_DIR / f)
        ns_exported |= set(re.findall(r'\bglobal(?:This)?\.([A-Z][A-Za-z0-9_$]*)\s*=', t))
    resolvable = decls | ns_exported | BROWSER_GLOBALS

    problems = []
    # 断言 A：模块 deps 用法 ⊆ 注入键（仅 configure 单例契约模块）
    for f in mod_files:
        raw = read(JS_DIR / f)
        if not module_uses_configure_contract(raw):
            continue
        t = strip_code(raw)
        m = re.search(r'\bglobal(?:This)?\.([A-Z][A-Za-z0-9_$]*)\s*=\s*\{', raw)
        ns = m.group(1) if m else None
        if not ns: continue
        keys = set(cfg.get(ns, {}).keys())
        used = module_deps_usage(t)
        miss = sorted(used - keys)
        for x in miss:
            problems.append('A漏注入  %s(%s): deps.%s 未被主文件注入' % (f, ns, x))
    # 断言 B：注入值里的裸标识符可解析
    for ns, kvs in cfg.items():
        for key, v in kvs.items():
            for tok in identifier_tokens(v):
                if tok in resolvable or tok in kvs:  # 同块键互引也算
                    continue
                # 箭头参数形如 (...a)=>a / (x)=>x 的局部名：取常见单字母或 a/b/args——用启发式：
                # 若该 token 只出现在箭头参数位则放行成本过高，简化：忽略长度<=2 的短名与 'args'
                if len(tok) <= 2 or tok in ('args','arg','v','e2'):
                    continue
                problems.append('B不可解析 %s.%s: 值引用 `%s` 主文件不可见 (%s)' % (ns, key, tok, v[:70].strip()))
    if problems:
        for p in problems: print('WIRING-FAIL', p)
        print('共 %d 处接线雷' % len(problems))
        return 1
    print('wiring ok: %d 模块、%d 注入块、键一致+值可解析全过' % (len(mod_files), len(cfg)))
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv))

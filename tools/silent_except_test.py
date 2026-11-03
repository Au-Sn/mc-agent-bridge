#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""silent_except_test.py -- ★"静默吞异常"分级扫描（★离线 ✗ 进闸门✗★）（§79.402）

★★背景✗★★（★2026-10-26 §79.401✗★）✗★：
  ★`world3d._load_h3d()` 的 `except Exception: pass` 把 **`NameError: pathlib 未定义`** 吞了
  ⇒ ★**导出表从没加载** ✗ 而所有判据**都显示 100%**✗★ ✓ ★同一个坑踩过两次✗★ ✓
★★分级✗★★（★★只有 A 级算红✗★★）✗★：
  ★**A 危险**✗★：★try 里在**读数据／解析／解码／算模型／网络** ⇒ 吞了 ⇒ **静默用错的默认值**✗★
  ★**B 可容忍**✗★：★try 里是 `stdout.reconfigure`／`import 可选依赖`／`mkdir` 之类
    ⇒ 失败**不影响正确性**（★fail-safe✗★）✗★
  ★**C 未知**✗★：★认不出 ⇒ **列出来人工看** ✗ 不算红但**计数器必须报**✗★ ✓
"""
from __future__ import annotations

import pathlib
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCAN_DIRS = ("tools", "gateway", "mod/src")

SAFE_BODY = (
    "sys.stdout.reconfigure", "stdout.reconfigure", "stderr.reconfigure",
    "os.makedirs", "os.chdir", ".mkdir(", "makedirs", "import ", "from ",
    "signal.", "load_dotenv", "locale.",
)
# ★★§79.402 修✗★★：★原来用**子串**匹配 ✗ 两个假阳性✗★：
#   ★int( 会命中 **print(** ✗ send( 会命中 _send(**✗★（★gate-auditor 当场指出✓★）
#   ★现在一律用**词边界正则**：\b...\b ✗ 且带 ( 的按**调用**匹配✗★ ✓
DANGER_BODY = (
    "json.load", "json.loads", "read_text", "read_bytes", "open",
    "float", "int", "split", "dsh", "dshscan", "fetch_region",
    "re.search", "re.match", "re.findall", "urlopen", "socket", "recv",
    "send", "load", "collision_h", "stand_at", "decode", "getenv",
)
_DANGER_RE = tuple(re.compile(r"\b" + re.escape(w)) for w in DANGER_BODY)

# ★★§79.402✗★★：★A 级里**确认过安全**的（★每一条写理由 ✗ 不许空口✓★）✗★
#   ★格式✗★：★文件名 → (允许条数, 理由)✗★ ✓
SILENT_OK = {
    "mc_mcp.py": (1, "★坏 JSON 行现在会**回 -32700** ✗ 这条是备用兜底✗★"),
    "world3d.py": (1, "★stdout.reconfigure 在有些环境不支持 ✗ **纯装饰** ✗ 不影响数据✗★"),
    "mcp_core.py": (2, "★写日志／写 errlog 失败 ✗ **fail-safe** ✗ 故意吞 ✗ 不改任何数据✗★"),
}

BAD_ONE = [re.compile(r"^\s*except[^\n:]*:\s*pass\s*(#.*)?$"),
           re.compile(r"^\s*except[^\n:]*:\s*continue\s*(#.*)?$")]
MULTI_HEAD = re.compile(r"^\s*except[^\n:]*:\s*$")
PASSY = re.compile(r"^\s*(pass|continue)\s*(#.*)?$")
RETURNY = re.compile(r"^\s*return(\s+(None|\[\]|\{\})?)?\s*(#.*)?$")


# ★★§79.402✗★★：★Java 的 `catch` 也要看✗★（★队友指出判据原来对 `.java` **永远返回 []**✗★）
#   ★只抓最准的一种✗★：★**catch 体里只有注释／全空**✗ ⇒ 那就是**一声不响地吞掉**✗★ ✓
_JAVA_CATCH = re.compile(r"^\s*catch\s*\([^)]*\)\s*\{\s*$")
_JAVA_EMPTY = re.compile(r"^\s*\}\s*(//.*)?$")
_JAVA_COMMENT = re.compile(r"^\s*(//|/\*|\*).*$")


def scan_java(p):
    """★Java：catch 体**空／只有注释** ⇒ 记一行✗★"""
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as e:
        return [(0, "!! 读失败 %r" % (e,), "C")]
    out = []
    for i, ln in enumerate(lines):
        if not _JAVA_CATCH.match(ln):
            continue
        j = i + 1
        body = []
        while j < len(lines) and not _JAVA_EMPTY.match(lines[j]):
            body.append(lines[j])
            j += 1
            if j - i > 12:
                break
        real = [b for b in body if b.strip() and not _JAVA_COMMENT.match(b)]
        if not real:
            out.append((i + 1, "catch 体空／只有注释 ｜ %s" % ln.strip()[:60], "A"))
    return out


ALLOW_FILE = ROOT / "state" / "silent_allow.json"


def load_allow():
    """★读机器可读白名单✗★：★{文件: {"lines": [..], "why": [..]}}✗★

    ★由 `tools/silent_allow_build.py` 从两份审计报告生成 ✗ **每条都带理由**✗★ ✓
    """
    import json
    if not ALLOW_FILE.is_file():
        return {}
    try:
        return json.loads(ALLOW_FILE.read_text(encoding="utf-8"))
    except Exception as e:                 # ★★§79.402✗★ 读坏要吵 ✗ 不许静默当成"没白名单"✗★
        print("  ★白名单读坏：%r ✗ 按**没有白名单**处理（会多报 ✗ 安全方向✗★）" % (e,))
        return {}


def scan_file(p):
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as e:
        return [(0, "!! 读失败 %r" % (e,), "C")]
    out = []
    for i, ln in enumerate(lines):
        hit = any(r.match(ln) for r in BAD_ONE)
        if not hit and MULTI_HEAD.match(ln) and i + 1 < len(lines):
            hit = bool(PASSY.match(lines[i + 1]) or RETURNY.match(lines[i + 1]))
        if not hit:
            continue
        body = " ".join(lines[max(0, i - 8):i])
        if any(s in body for s in SAFE_BODY) and not any(r.search(body) for r in _DANGER_RE):
            lvl = "B"
        elif any(r.search(body) for r in _DANGER_RE):
            lvl = "A"
        else:
            lvl = "C"
        out.append((i + 1, body.strip()[-70:], lvl))
    return out


def main(argv=None) -> int:
    """★`argv` 只用来加打印参数（★`--list-c`✗★）✗ **A/B/C 分类口径一个字没动**✗★ ✓"""
    argv = list(sys.argv[1:] if argv is None else argv)
    files = 0
    per = {"A": [], "B": [], "C": []}
    for d in SCAN_DIRS:
        base = ROOT / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.py" if d != "mod/src" else "*.java")):
            if p.name == pathlib.Path(__file__).name:
                continue
            files += 1
            scan = scan_java(p) if p.suffix == ".java" else scan_file(p)
            for line, body, lvl in scan:
                per[lvl].append((str(p.relative_to(ROOT)), line, body))
    print("  扫了 **%d** 个源文件" % files)
    print("  ★A 危险（★会静默用错数据✗★）：**%d** 处" % len(per["A"]))
    print("  B 可容忍（★fail-safe✗★）：%d 处 ｜ C 未知（★要人看✗★）：%d 处"
          % (len(per["B"]), len(per["C"])))
    # ★★§79.403✗★★：★先按**机器白名单**放过（★精确到行号 ✗ 移位就失效✗★）✗★
    allow = load_allow()
    excused, kept = [], []
    for f, line, body in per["A"]:
        fb = f.replace("\\", "/")
        ent = allow.get(fb) or allow.get(fb.replace("/", "\\"))
        if ent and line in (ent.get("lines") or []):
            excused.append((f, line))
        else:
            kept.append((f, line, body))
    if excused:
        print("  ★机器白名单放过 %d 处（★每条在 state/silent_allow.json 里有理由✗★）✗★"
              % len(excused))
    per["A"] = kept
    # ★★§79.405（★task-7 ✗ 2026-10-27✗★）✗★★：★**C 级**也按机器白名单放过✗★ ——
    #   ★A/B/C 的**分类口径一个字没动** ✗ 这里只做"人工已分诊 ⇒ 不再计入待办"✗★ ✓
    #   ★C 的本义是"要人看" ✗ 看过的结论必须有去处 ✗ 否则每跑一次都重新报同样 30 条✗★ ✓
    #   ★行号移位 ⇒ 条目匹配不上 ⇒ **自动重新报出来**（安全方向 ✗ 白名单盖不住新问题）✗★ ✓
    raw_c = list(per["C"])
    excused_c, kept_c = [], []
    for f, line, body in per["C"]:
        fb = f.replace("\\", "/")
        ent = allow.get(fb) or allow.get(fb.replace("/", "\\"))
        if ent and line in (ent.get("lines") or []):
            excused_c.append((f, line))
        else:
            kept_c.append((f, line, body))
    if excused_c:
        print("  ★C 级分诊放过 %d 处（★人工判过假阳性 ✗ 理由在 state/silent_allow.json✗★）"
              % len(excused_c))
    per["C"] = kept_c
    if "--list-c" in argv:
        # ★审计用✗★：★把**全部** C（含已分诊的）打出来 ✗ 给下一个人看✗★ ✓
        print("  ★C 级全清单（★含已分诊✗★）：%d 处" % len(raw_c))
        for rel, line, body in raw_c:
            fb = rel.replace("\\", "/")
            ent = allow.get(fb) or allow.get(fb.replace("/", "\\"))
            mark = "已分诊" if (ent and line in (ent.get("lines") or [])) else "待分诊"
            print("     %-40s %4d ｜ %-6s ｜ %s" % (rel, line, mark, body[:50]))
    allowed = 0
    for k, (n, _r) in SILENT_OK.items():
        allowed += min(n, sum(1 for f, _l, _b in per["A"] if pathlib.Path(f).name == k))
    real = len(per["A"]) - allowed
    print("  A 级白名单放过 %d ✗ ★待修 %d★" % (allowed, real))
    # ★★§79.405✗★★：★C 级**待分诊**也要打出来 ✗ 不再只是"计数器里的 30"✗★ ✓
    #   （★以前 C 只报数 ✗ 谁都不知道是哪 30 条 ✗ 于是 30 条永远没人分诊✗★）✗★ ✓
    print("  ★C 级待分诊清单✗★（%d 条 ✗ ★`--list-c` 看全部✗★）：" % len(per["C"]))
    for rel, line, body in per["C"][:24]:
        print("     %-40s %4d ｜ %s" % (rel, line, body[:58]))
    print("  ★A 级清单✗★（★前 24 条✗★）：")
    for rel, line, body in per["A"][:24]:
        print("     %-40s %4d ｜ %s" % (rel, line, body[:58]))
    if real > 0:
        print("  => silent_except ★FAIL★（★A 级 %d 处 ✗ 每处都可能像 §79.401 那样静默出错✗★）"
              % real)
        # ★★§79.425✗★★：★C= 是**待分诊数** ✗ c_all= 是**总数**✗（★两个数都明摆着✗ ★）
        print("SILENTEXC ok=0 A=%d B=%d C=%d c_all=%d real=%d"
              % (len(per["A"]), len(per["B"]), len(per["C"]), len(raw_c), real))
        return 1
    print("  => silent_except PASS ✓（★A 级 0 ✗ 没有会静默用错数据的吞异常✗★）")
    print("SILENTEXC ok=1 A=0 B=%d C=%d c_all=%d" % (len(per["B"]), len(per["C"]), len(raw_c)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

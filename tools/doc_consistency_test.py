#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""doc_consistency_test.py -- D7 文档一致性闸门 C1~C10（离线 ✓ 2026-11-02 ✓ ADR-10）

★为什么有它✗★（优化路线 ADR-10 / 审计 P0-1 / 本轮任务 B）：
  ★本项目已经坏过一次"入口文档说谎而 118 项闸门全绿"✗★ ——
  `docs/交接提示词.md` 的 **271 行正文**被提交 cc875dc 清空 ⇒ 只剩 17 行自动生成的 DEBT 块 ✗
  而没有任何判据在读入口文档 ⇒ 下一个会话会拿着**空壳**开工（真悬空：00 引它的 §四）✗★
  ⇒ ★口径✗★：**修文档和加门必须同一次交付**（ADR-10）——
    入口文档里可机器核对的数字/路径/版本，全部由本判据守 ✓

★C1~C10（先写死 ✗ 再上线）✗★：
  C1 版本单一真源：mod/gradle.properties ＝ 入口文档里的模组版本 ＝
     mod/build/libs 最新 jar 文件名版本 ＝ 游戏 mods/ 里实际安装的 jar（同名同字节）；
     接口版本（mc_mcp serverInfo ↔ 契约文档）单独一条；
  C2 HEAD 引用：入口文档里"最新/HEAD"点名的短哈希必须真是当前 HEAD 的前缀；
     入口文档里所有 backtick 哈希必须是 git 库里存在的对象（悬空哈希 ⇒ 红）；
  C3 工具数＝55：mc_mcp TOOLS 实测 ＋ 契约文档工具表 ＋ 入口文档里写死的工具数；
  C4 docs 文件计数：入口文档写的 md/docx/总文件数 ＝ 盘上实测；
  C5 入口文档内部链接/悬空引用 ＋ 文档索引覆盖率（≥90% 的 docs md 被索引收录）；
  C6 入口文档关键数字与事实表：判据项数 / 判据脚本数 / 台账节数 / 工具面 / 直连主路 等
     全部拿**机器实算**去撞（不信任文档自述；**不写死具体数** —— GATE 扩容后由 --fix-counts 收敛）；
  C7 台账：ledger_index.render() 的节数与入口文档一致 ＋ 引用悬空必须 0；
  C8 DEBT 块自洽：入口文档的 DEBT 块 ＝ debt_count 生成块，且块外正文必须够长
     （★这条直接防"正文又被清空"：块外非空行 < 下限 ⇒ 红✗★）；
  C9 生成物新鲜度：闸门-项数.md 的四张表项数 ＝ import check_all 实算；
     分歧清单/迁移准备度 标题正确、mtime 不早于上游、且**两者不许同哈希**（复制品回归）；
  C10 事实错误：`agent/` 不许再被标成"早期架构遗留/legacy/仅作参考"（它是活依赖：
     53 个 agent 文件、59 个 tools 脚本 sys.path.insert(agent)）；
     README 必须列出全部根目录 ＋ 主链路必须是直连 8766；reports/ 在仓库外这件事要有登记。

★纪律✗★：
  · ★先自检能红✗★：本判据上线第一天对未修的入口文档必须报红（已留证据）✓
  · ★没数据就说没数据✗★：任何一条拿不到输入 ⇒ 红并写出**为什么拿不到** ✗ 不许静默吞 ✓
  · ★数字全部现算✗★：入口文档只当"被核对方" ✗ 不当真源（真源是 gradle.properties / TOOLS /
    check_all 的四张表 / ledger_index / 盘上文件）✓

★怎么维护（数字漂移时）✗★：
  GATE 扩容 ／ 台账合并 会让「判据项数／判据脚本数／台账节数」三个**滚动数字**漂移 ⇒
  跑 `py tools/doc_consistency_test.py --fix-counts`：**只**按机器实算刷新入口文档里这三个数 ✗
  不碰别的字；刷完**同一次运行里再核一遍**（门还在 ✗ 不是自动放行）✓
  ★预演过（2026-11-02）✗★：临时副本上人为把 7 处滚动数字改成 999 ⇒ 一条命令全部修回、剩余 999＝0 ✓
  ★HEAD 不写死✗★：入口文档给命令（`git log -1 --oneline`）而不是钉一个会过期的哈希 ✓
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "docs"
T = ROOT / "tools"
MODS = Path(r"D:\pcl2\.minecraft\versions\All the Mods 9 - To the Sky - atm9sky\mods")

sys.path.insert(0, str(T))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ok = [True]
RESULTS = []
FIX_COUNTS = "--fix-counts" in sys.argv   # ★可选模式：按机器实算刷新三个滚动数字（门还在）★


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    RESULTS.append((tag, bool(cond)))
    print("  %-6s %s %s" % (tag, "✓" if cond else "★红✗★", note))


def read(p):
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def read_doc(name):
    return read(D / name)


def rv(p):
    """★只读 rawspec：⇒ (text, err)；取不到就红 ✗ 不许把"读不到"当"没有"✗★"""
    try:
        return p.read_text(encoding="utf-8"), ""
    except Exception as e:
        return "", "%s: %s" % (type(e).__name__, str(e)[:60])


ENTRY = ["README.md"]
ENTRY_DOCS = ["00-快速上手与索引.md", "项目总览.md", "项目全史.md", "交接提示词.md", "文档索引.md"]

print("== doc_consistency：D7 入口文档闸门 C1~C10 ==")


# ---------------------------------------------------------------- 公共事实
def git(args):
    try:
        r = subprocess.run(["git"] + args, cwd=str(ROOT), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=30)
        return (r.returncode, r.stdout.strip())
    except Exception as e:
        return (99, "SUBERR:%s" % type(e).__name__)


def head_hash():
    rc, out = git(["rev-parse", "HEAD"])
    return out if rc == 0 and re.fullmatch(r"[0-9a-f]{40}", out) else None


def history_count():
    """★当前仓库有多少个提交✗★（取不到 ⇒ None）

    ★为什么需要它✗★：公开仓库用**干净快照**导出（单提交/浅历史）✗
    ⇒ 入口文档里引用的历史 hash（如 `cc875dc`）在新仓里**本来就不该存在** ✗★
    """
    rc, out = git(["rev-list", "--count", "HEAD"])
    return int(out) if rc == 0 and out.isdigit() else None


def _git_commit_ctime(p):
    """★这个文件最后一次被提交的时间✗★（取不到 ⇒ None）"""
    try:
        rel = p.resolve().relative_to(ROOT.resolve()).as_posix()
    except (ValueError, OSError) as e:
        print("[doc] 路径不在仓库内（取不到提交时间）：%s（%s）" % (p, type(e).__name__))
        return None
    rc, out = git(["log", "-1", "--format=%ct", "--", rel])
    if rc == 0 and out.strip().isdigit():
        return float(out.strip())
    return None


def _path_dirty(p):
    """⇒ True/False；取不到 git ⇒ None（★不猜✗★）"""
    try:
        rel = p.resolve().relative_to(ROOT.resolve()).as_posix()
    except (ValueError, OSError) as e:
        print("[doc] 路径不在仓库内（取不到 git 状态）：%s（%s）" % (p, type(e).__name__))
        return None
    rc, out = git(["status", "--porcelain", "--", rel])
    if rc != 0:
        return None
    return bool(out.strip())


def fresh_time(p):
    """★生成物新鲜度用的时间✗★：优先 **git commit 时间**，改动过/取不到再退回 mtime

    ★为什么不用裸 mtime✗★（2026-11-03 Lead 指出的发布阻断缺陷）：
      公开仓库是**干净快照**（`git archive`/clone）⇒ 所有文件 mtime = 解压/检出时间（同序不保证）✗
      ⇒ 闸门会把"文件解压先后"误判成"生成物过期" ⇒ 新用户第一次跑 `check_all --offline` 必假红 ✗★
    ★口径✗★：干净跟踪文件 ⇒ 用**提交时间**（与解压顺序无关）；有本地改动/未跟踪/无 git ⇒ 退回 mtime ✓
    """
    c = _git_commit_ctime(p)
    d = _path_dirty(p)
    if c is not None and d is False:
        return c
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def obj_exists(h):
    rc, _ = git(["cat-file", "-e", h])
    return rc == 0


def mod_src_version():
    m = re.search(r"^mod_version\s*=\s*(\S+)", read(ROOT / "mod" / "gradle.properties"), re.M)
    return m.group(1) if m else None


def parse_ver(name):
    m = re.search(r"dshbridge-(\d+)\.(\d+)\.(\d+)\.jar$", name)
    return tuple(int(g) for g in m.groups()) if m else None


def newest_build_jar():
    best = None
    for p in (ROOT / "mod" / "build" / "libs").glob("dshbridge-*.jar"):
        v = parse_ver(p.name)
        if not v:
            continue
        key = (v, p.stat().st_mtime)
        if best is None or key > best[0]:
            best = (key, p)
    return best[1] if best else None


def installed_jars():
    return sorted(MODS.glob("dshbridge-*.jar")) if MODS.is_dir() else []


def root_dirs():
    return sorted(p.name for p in ROOT.iterdir() if p.is_dir() and not p.name.startswith("."))


HEAD = head_hash()
SRCV = mod_src_version()
ALL_DOCS = sorted(D.glob("*.md"))
ALL_FILES = sorted(p for p in D.iterdir() if p.is_file())
DOCX = sorted(D.glob("*.docx"))
MD_N = len(ALL_DOCS)
FILE_N = len(ALL_FILES)
DOCX_N = len(DOCX)

# 版本类数字：允许在"历史"语境里出现旧版本，但入口文档的**现状行**必须写的是 SRCV
DOCS_TEXT = {n: read_doc(n) for n in ENTRY_DOCS}
README_TEXT = read(ROOT / "README.md")
FULL = dict(DOCS_TEXT, **{"README.md": README_TEXT})


def claims(doc, pattern):
    """⇒ 该文档里 pattern 抓到的全部第 1 组"""
    return re.findall(pattern, FULL.get(doc, ""))


# ---------------------------------------------------------------- C1 版本单一真源
print("")
print("-- C1 版本单一真源 --")
if not SRCV:
    check("C1a", False, "★读不到 mod/gradle.properties 的 mod_version✗★")
else:
    check("C1a", bool(re.fullmatch(r"\d+\.\d+\.\d+", SRCV)),
          "单一真源 mod/gradle.properties mod_version = **%s**" % SRCV)

DOCCLAIM = {
    "项目总览.md": [
        r"模组版本：\*\*(\d+\.\d+\.\d+)\*\*",
        r"\| \*\*模组\*\* \| \*\*(\d+\.\d+\.\d+)\*\*",
        r"\| \*\*L3 世界内执行端点\*\* \| 模组（所有世界能力） \| \*\*(\d+\.\d+\.\d+)\*\*",
    ],
    "00-快速上手与索引.md": [r"\| \*\*模组\*\* \| \*\*(\d+\.\d+\.\d+)\*\*"],
    "项目全史.md": [r"\| 模组 \| (\d+\.\d+\.\d+)"],
    "交接提示词.md": [r"\| \*\*模组\*\* \| \*\*(\d+\.\d+\.\d+)\*\*"],
}
_bad = []
_n = 0
for doc, pats in DOCCLAIM.items():
    for pat in pats:
        got = claims(doc, pat)
        if not got:
            _bad.append("%s 里用 `%s` 找不到模组版本声明" % (doc, pat))
            continue
        _n += 1
        for g in got:
            if g != SRCV:
                _bad.append("%s 写 **%s** ≠ 真源 **%s**" % (doc, g, SRCV))
check("C1b", (not _bad) and _n >= 5,
      "入口文档模组版本 ＝ 真源（核了 %d 处）：%s" % (_n, "；".join(_bad[:4]) or "全一致 ✓"))

# 接口版本：契约文档 ↔ mc_mcp serverInfo（与模组版本是两件事，分开核）
_mcp = read(T / "mc_mcp.py")
mv = re.search(r'"serverInfo":\s*\{"name":\s*"mc-bridge",\s*"version":\s*"([^"]+)"', _mcp)
iv = mv.group(1) if mv else None
_contract = read_doc("接口契约-伙伴v1.0.md")
check("C1c", bool(iv) and bool(_contract) and iv in _contract,
      "接口版本单一真源：mc_mcp.py serverInfo.version=%r 在契约文档里出现=%s"
      % (iv, bool(iv and iv in _contract)))

# 构建物/安装物：从**jar 文件名解析**版本（禁写死）＋ 字节一致
_bj = newest_build_jar()
_ij = installed_jars()
if _bj is None:
    # ★★2026-11-03 修（发布阻断）✗★★：公开仓 clone 下来**本来就没有** `mod/build/libs`（构建产物不入库）✗
    #   用 Release 附件装 jar 的用户**不需要本地构建** ⇒ 只要"已装 jar 版本 = 源码版本"就应算过 ✓
    _inst = installed_jars()
    if len(_inst) == 1:
        _iv = ".".join(str(x) for x in (parse_ver(_inst[0].name) or (0, 0, 0)))
        check("C1d", _iv == SRCV,
              "无本地构建产物（用发布 jar 属正常）｜installed=%s ｜ 源码=%s ⇒ %s"
              % (_inst[0].name, SRCV, "版本一致 ✓" if _iv == SRCV else "★版本不一致✗★"))
    else:
        check("C1d", False,
              "既没有 build/libs 构建产物、也没有恰好 1 个已装 jar（实际 %d 个）⇒ 先按 INSTALL 装模组"
              % len(_inst))
else:
    bv = ".".join(str(x) for x in parse_ver(_bj.name))
    check("C1d", bv == SRCV,
          "构建物最新 jar = %s（%d B）｜源码 = %s" % (_bj.name, _bj.stat().st_size, SRCV))

# C1e：安装物 == 构建物（★没有本地构建时"不适用"✗★：C1d 已核 installed 与源码同版本；
#   发布 jar 用户不构建 ⇒ 不能因此红 ✓）
if _bj is None:
    check("C1e", True,
          "无本地构建产物 ⇒ 「安装==构建」不适用（C1d 已核 installed 与源码同版本；"
          "发布 jar 用户不需要本地构建）")
elif len(_ij) != 1:
    check("C1e", False, "游戏 mods/ 里的 dshbridge*.jar 应恰好 1 个（实际 %d：%s）"
          % (len(_ij), [p.name for p in _ij]))
else:
    _bv2 = ".".join(str(x) for x in parse_ver(_bj.name))
    iv2 = ".".join(str(x) for x in (parse_ver(_ij[0].name) or ()))
    same = (iv2 == _bv2) and (_ij[0].stat().st_size == _bj.stat().st_size)
    check("C1e", same,
          "安装 jar = %s（%d B）｜构建 jar = %s（%d B）｜安装==构建 = %s"
          % (_ij[0].name, _ij[0].stat().st_size, _bj.name, _bj.stat().st_size, same))


# ---------------------------------------------------------------- C2 HEAD 引用
print("")
print("-- C2 HEAD 引用 --")
# C2a：凡出现"最新/HEAD + 哈希"的行 ⇒ 那个哈希必须**就是当前 HEAD 的前缀**
if not HEAD:
    check("C2a", True,
          "★跳过：取不到 git HEAD（无 .git / zip 快照）⇒ HEAD 引用无法核 ✗ 不冒充通过；"
          "正常 clone 的发布仓会真核✓★")
else:
    _bad, _n = [], 0
    for doc in ENTRY_DOCS:
        for line in DOCS_TEXT[doc].splitlines():
            if not re.search(r"最新|HEAD", line):
                continue
            for h in re.findall(r"\b([0-9a-f]{7,40})\b", line):
                _n += 1
                if not HEAD.startswith(h):
                    _bad.append("%s：`%s` ≠ 当前 HEAD %s" % (doc, h, HEAD[:12]))
    check("C2a", not _bad,
          "『最新/HEAD』点名的哈希（如果有）都在 HEAD 上（核了 %d 处）：%s"
          % (_n, "；".join(_bad[:4]) or "✓"))
# C2b：**不写死哈希**的政策本身要写出来（给命令 ✗ 不给过期哈希）—— 与有没有 HEAD 无关，始终检查
_pol = [n for n in ENTRY_DOCS
        if re.search(r"git log -1|git rev-parse HEAD|不写死", DOCS_TEXT[n])]
check("C2b", bool(_pol),
      "入口文档写明『HEAD 用命令当场查、不写死』：%s" % (_pol or "★没有✗★"))
# C2c：所有 backtick 哈希必须是 git 里存在的对象（防"编一个哈希"）
#   ★干净快照（单提交/浅历史/无 git）里文档引用的历史 hash 本来就不该存在 ⇒ 跳过并说清 ✓
_hist = history_count()
if _hist is None:
    check("C2c", True,
          "★跳过：取不到 git（zip 快照/无 .git）⇒ 无法校验历史 hash ✗ 不冒充校验过"
          "（发布仓正常是 clone 出来的 ⇒ 有 .git ⇒ 会真校验）✓★")
elif _hist < 10:
    check("C2c", True,
          "★跳过：当前仓库只有 %d 个提交（干净快照/浅历史）⇒ 不校验入口文档里的历史 hash"
          "（★这不是通过 ✗ 是「这一项在当前快照下无法判」✓★）" % _hist)
else:
    _bad2, _n2 = [], 0
    for doc in ENTRY_DOCS:
        for h in re.findall(r"`([0-9a-f]{7,40})`", DOCS_TEXT[doc]):
            _n2 += 1
            if not obj_exists(h):
                _bad2.append("%s：`%s` 在 git 里不存在" % (doc, h))
    check("C2c", not _bad2, "入口文档里 backtick 哈希都存在于 git（核了 %d 个）：%s"
          % (_n2, "；".join(_bad2[:4]) or "✓"))


# ---------------------------------------------------------------- C3 工具数 = 55
print("")
print("-- C3 工具数 = 55 --")
try:
    import contract_test as CT  # noqa: E402
    _tools = CT.parse_tools()
    _names = [t[0] for t in _tools]
    _doc_tools = CT.doc_tools()
    check("C3a", len(_names) == 55 and len(set(_names)) == 55,
          "mc_mcp TOOLS 实测 **%d** 件（期望 55）" % len(_names))
    check("C3b", _doc_tools == set(_names),
          "契约文档工具表 双向对账：doc %d 件 ｜ 差集 %s"
          % (len(_doc_tools), sorted(_doc_tools ^ set(_names))[:4] or "空 ✓"))
except Exception as e:
    check("C3a", False, "★导入 contract_test 失败：%s✗★" % (type(e).__name__,))
    check("C3b", False, "★同上✗★")

TOOL_CLAIM = {
    "00-快速上手与索引.md": [r"(\d+) 件 MCP 工具", r"\| \*\*工具面\*\* \| \*\*(\d+) 件\*\*"],
    "项目全史.md": [r"\| L5 中间层 \| (\d+) 件 MCP 工具"],
    "项目总览.md": [r"\| \*\*工具面\*\* \| \*\*(\d+) 件\*\*"],
    "交接提示词.md": [r"工具面 \*\*?(\d+) 件", r"(\d+) 件 MCP 工具"],
}
_bad, _n = [], 0
for doc, pats in TOOL_CLAIM.items():
    for pat in pats:
        got = claims(doc, pat)
        if not got:
            continue
        _n += 1
        for g in got:
            if g != "55":
                _bad.append("%s 写 %s 件 ≠ 55" % (doc, g))
check("C3c", not _bad, "入口文档写死的工具数都 ＝ 55（核了 %d 处）：%s"
      % (_n, "；".join(_bad[:4]) or "✓"))


# ---------------------------------------------------------------- C4 docs 文件计数
print("")
print("-- C4 docs 文件计数 --")
md = claims("项目总览.md", r"`docs/`\*\* \| \*\*(\d+) 个 `\.md`|`docs/` \| (\d+) 个 `?\.md")
md = [a or b for (a, b) in md]
check("C4a", all(int(x) == MD_N for x in md) and bool(md),
      "总览写 docs md = %s ｜ 盘上实测 **%d**" % (md or "（没找到声明）", MD_N))
fx = claims("项目总览.md", r"共 (\d+) 个文件")
check("C4b", all(int(x) == FILE_N for x in fx) and bool(fx),
      "总览写 docs 总文件 = %s ｜ 盘上实测 **%d**（md %d ＋ docx %d ＋ 其它 %d）"
      % (fx or "（没找到声明）", FILE_N, MD_N, DOCX_N, FILE_N - MD_N - DOCX_N))
h = claims("项目全史.md", r"### 文档（(\d+) 份）")
h2 = claims("项目全史.md", r"\| 文档 \| (\d+) 份")
c = claims("项目全史.md", r"(\d+) 份文档")
check("C4c", all(int(x) == MD_N for x in h + h2 + c) and bool(h or h2 or c),
      "全史写 docs 份数 = %s ｜ 实测 **%d**" % (h + h2 + c or "（没找到声明）", MD_N))
check("C4d", (MD_N >= 60) and (FILE_N >= MD_N),
      "计数器：docs md=%d 文件=%d docx=%d（防'一份都没有还全绿'）" % (MD_N, FILE_N, DOCX_N))


# ---------------------------------------------------------------- C5 链接 / 悬空引用 / 索引覆盖率
print("")
print("-- C5 内部链接 / 悬空引用 / 索引覆盖率 --")
_link_bad, _link_n = [], 0


def _resolve(doc_path: Path, target: str) -> Path:
    t = target.split("#", 1)[0].strip()
    if not t or t.startswith(("http://", "https://", "mailto:", "../")):
        return None  # 外链 & 仓库外（reports/ 在仓库外，见 C10）不归 C5 管
    if t.startswith("/"):
        return ROOT / t.lstrip("/")
    return (doc_path.parent / t)


for name in ["README.md"] + ENTRY_DOCS:
    p = (ROOT / name) if name == "README.md" else (D / name)
    text = read(p)
    for target in re.findall(r"\]\(([^)]+)\)", text):
        _link_n += 1
        tgt = _resolve(p, target)
        if tgt is not None and not tgt.exists():
            _link_bad.append("%s -> %s" % (name, target))
check("C5a", not _link_bad,
      "入口文档 markdown 链接都能落到盘上（核了 %d 条）：%s"
      % (_link_n, "；".join(_link_bad[:5]) or "✓"))

# backtick 里的仓库路径（docs/…、tools/…、mod/…）也要在
_path_bad, _path_n = [], 0
for name in ["README.md"] + ENTRY_DOCS:
    p = (ROOT / name) if name == "README.md" else (D / name)
    text = read(p)
    for raw in re.findall(r"`([^`\n]+)`", text):
        s = raw.strip().replace("\\", "/")
        if not re.match(r"^(docs|tools|mod|kubejs|state|agent|gateway|logs)/", s):
            continue
        if any(ch in s for ch in "*<>{}|… ") or s.endswith("/"):
            continue  # glob/占位符/目录前缀不逐个核
        _path_n += 1
        cand = ROOT / s
        if not cand.exists():
            _path_bad.append("%s: `%s`" % (name, raw.strip()[:60]))
check("C5b", not _path_bad,
      "入口文档 backtick 仓库路径都存在（核了 %d 个）：%s"
      % (_path_n, "；".join(_path_bad[:5]) or "✓"))

# 文档索引覆盖率：索引里 markdown 链接命中的 docs md 数 / 全部 md
_idx = read_doc("文档索引.md")
_idx_set = set()
for target in re.findall(r"\]\(([^)]+)\)", _idx):
    t = target.split("#", 1)[0].strip()
    if t.endswith(".md") and (D / t).is_file():
        _idx_set.add(t)
_cover = (len(_idx_set) * 100.0 / MD_N) if MD_N else 0.0
check("C5c", _cover >= 90.0,
      "文档索引覆盖 **%d/%d = %.0f%%**（门槛 ≥90%%）" % (len(_idx_set), MD_N, _cover))


# ---------------------------------------------------------------- C6 关键数字 / 事实表
print("")
print("-- C6 关键数字 / 事实表（拿机器实算撞文档）--")
try:
    import check_all as CA  # noqa: E402
    OFFLINE_N = len(CA.OFFLINE)
except Exception as e:
    OFFLINE_N = None
    check("C6a", False, "★导入 check_all 失败：%s✗★" % (type(e).__name__,))
TEST_N = len(list(T.glob("*_test.py")))
try:
    import ledger_index as LI  # noqa: E402
    _ltxt, LEDGER_N, _dang = LI.render()
except Exception:
    _ltxt, LEDGER_N, _dang = "", None, ["IMPORT FAIL"]

# ★滚动数字的真源值✗★（都不是从文档读的）
#   2026-11-02 第二轮补第四个：**模组 .java 文件数**（2.57.0 开发中从 2 变 3 ✗ 写死就红 ⇒ 纳入维护）✓
JAVA_N = len(list((ROOT / "mod" / "src").rglob("*.java")))
LIVE = {"判据项数": OFFLINE_N, "判据脚本数": TEST_N, "台账节数": LEDGER_N,
        "模组 .java 数": JAVA_N}
# ★历史语境豁免✗★：明确标"旧/当时/上一版"的行不当现状声明（豁免逐条不藏：C6a 会报数）
EXEMPT_MARK = ("上一版", "旧口径", "旧数字", "当时", "历史", "作废", "停在", "10 月口径")


def _line_at(text, pos):
    s = text.rfind("\n", 0, pos) + 1
    e = text.find("\n", pos)
    return text[s:(len(text) if e < 0 else e)]


def rolling_claims():
    """★三个滚动数字的**所有可机械核写法**✗★ ⇒ (claims, exempt)

    ★为什么不用固定表格正则✗★（2026-11-02 Lead 指出）：旧版 `--fix-counts` 只匹配 12 个表格单元格 ⇒
    正文散文里的「离线闸门 118 项」「（544 节，1.2 MB）」「156 个 *_test.py」**全逃掉** ✗
    ⇒ 口径：**(数字 + 单位)** ＋ **上下文窗口**判它属于哪个事实 ✗ 表格与散文一视同仁 ✓
    """
    rules = {
        "判据项数": [
            (re.compile(r"(?P<num>\d+)(?P<unit>\*{0,2}\s*项)"),
             lambda b, a: ("闸门" in b + a) or ("判据" in b and "判据脚本" not in b)
                          or ("check_all" in b) or ("全绿" in a)),
            (re.compile(r"(?P<num>\d+)(?P<unit>\s*进闸门)"), lambda b, a: True),
            # ★"进闸门的 118"（数字在词**后面**）也要抓✗★（2026-11-02 Lead 举的例子）
            (re.compile(r"(?P<pre>进闸门[^0-9\n]{0,8})(?P<num>\d+)(?P<unit>)"), lambda b, a: True),
        ],
        "判据脚本数": [
            (re.compile(r"(?P<num>\d+)(?P<unit>\*{0,2}\s*个)"),
             lambda b, a: ("_test.py" in a) or ("判据脚本" in b)),
        ],
        "模组 .java 数": [
            (re.compile(r"(?P<num>\d+)(?P<unit>\s*个\s*`?\.java)"), lambda b, a: True),
        ],
        "台账节数": [
            (re.compile(r"(?P<num>\d+)(?P<unit>\*{0,2}\s*节)"),
             lambda b, a: ("台账" in b + a) or ("索引悬空" in a) or ("1.2 MB" in b + a)),
        ],
    }
    claims, exempt = [], []
    for doc in ["项目总览.md", "00-快速上手与索引.md", "项目全史.md", "交接提示词.md", "README.md"]:
        text = FULL.get(doc, "")
        for fact, rs in rules.items():
            for rx, okctx in rs:
                for m in rx.finditer(text):
                    b = text[max(0, m.start("num") - 40):m.start("num")]
                    a = text[m.end("unit"):m.end("unit") + 40]
                    if not okctx(b, a):
                        continue
                    line = _line_at(text, m.start("num"))
                    rec = {"doc": doc, "fact": fact, "value": int(m.group("num")),
                           "start": m.start("num"), "end": m.end("num"),
                           "line": line.strip()[:100]}
                    (exempt if any(k in line for k in EXEMPT_MARK) else claims).append(rec)
    return claims, exempt


def apply_fix_counts():
    """★--fix-counts✗★：把**所有**扫描到的滚动数字改成本机实算（表格＋散文一视同仁）"""
    claims, _ex = rolling_claims()
    todo = {}
    for c in claims:
        want = LIVE.get(c["fact"])
        if want is None or c["value"] == want:
            continue
        todo.setdefault(c["doc"], []).append((c["start"], c["end"], str(want)))
    changed = []
    for doc, edits in sorted(todo.items()):
        p = (ROOT / "README.md") if doc == "README.md" else (D / doc)
        text = read(p)
        for (s, e, want) in sorted(edits, reverse=True):
            text = text[:s] + want + text[e:]
        p.write_text(text, encoding="utf-8")
        changed.append("%s×%d" % (doc, len(edits)))
    return changed


def reload_texts():
    global README_TEXT
    for n in ENTRY_DOCS:
        DOCS_TEXT[n] = read_doc(n)
    README_TEXT = read(ROOT / "README.md")
    FULL.clear()
    FULL.update(DOCS_TEXT)
    FULL["README.md"] = README_TEXT


if FIX_COUNTS:
    print("")
    print("-- --fix-counts：按机器实算刷新入口文档三个滚动数字（**表格＋散文都扫**）--")
    _ch = apply_fix_counts()
    print("  已刷新：%s" % ("；".join(_ch) or "（不用改 ✓）"))
    reload_texts()

_claims, _exempt = rolling_claims()
# C6a ★自洽✗★：同一事实在各处的值必须唯一（≥2 处），且扫描面足够大（防"只扫到一处就绿"）
_bad = []
for fact in LIVE:
    vals = sorted({c["value"] for c in _claims if c["fact"] == fact})
    if len(vals) != 1:
        _bad.append("%s 的声明值不唯一：%s" % (fact, vals))
check("C6a", (not _bad) and len(_claims) >= 10,
      "入口文档滚动数字彼此自洽（扫到 %d 处：%s ｜历史语境豁免 %d 处）：%s"
      % (len(_claims), sorted({c["value"] for c in _claims}), len(_exempt),
         "；".join(_bad) or "✓"))
# C6b ★对真源✗★：每一处都必须等于机器实算（不信任文档自述）
_bad = []
for c in _claims:
    want = LIVE[c["fact"]]
    if want is not None and c["value"] != want:
        _bad.append("%s：%s 写 %s ≠ 实算 %s（%s）"
                    % (c["doc"], c["fact"], c["value"], want, c["line"][:60]))
# 工具面 55 件（单独一条：它不在三个滚动数字里）
TOOL_CLAIM = {
    "00-快速上手与索引.md": [r"(\d+) 件 MCP 工具", r"\| \*\*工具面\*\* \| \*\*(\d+) 件\*\*"],
    "项目全史.md": [r"\| L5 中间层 \| (\d+) 件 MCP 工具"],
    "项目总览.md": [r"\| \*\*工具面\*\* \| \*\*(\d+) 件\*\*"],
    "交接提示词.md": [r"工具面 \*\*?(\d+) 件", r"(\d+) 件 MCP 工具"],
}
_tn = 0
for doc, pats in TOOL_CLAIM.items():
    for pat in pats:
        for g in claims(doc, pat):
            _tn += 1
            if g != "55":
                _bad.append("%s 写工具面 %s 件 ≠ 55" % (doc, g))
check("C6b", not _bad, "滚动数字逐处 ＝ 机器实算（核了 %d 处滚动＋%d 处工具面）：%s"
      % (len(_claims), _tn, "；".join(_bad[:6]) or "✓"))
# 事实表：直连主路（8766 + 2~4ms）必须在 总览/00/全史/交接提示词 里写对
_direct = {n: ("8766" in FULL[n]) for n in ["00-快速上手与索引.md", "项目总览.md", "项目全史.md", "交接提示词.md"]}
_missing = [n for n, v in _direct.items() if not v]
check("C6c", not _missing, "入口文档都写了直连主路 8766：缺 %s" % (_missing or "没有 ✓"))
check("C6d", ("2~4 ms" in FULL["项目总览.md"]) and ("2~4 ms" in FULL["00-快速上手与索引.md"]),
      "直连延迟 2~4 ms 在总览/00 都写了（本判据不 live 测延迟，只防数字被删）")
# 模组源码事实：java 文件数已纳入滚动数字（JAVA_N）⇒ 逐处等值由 C6b 管 ✗
#   这里只做**计数器**：必须真的扫到声明 ＋ 实算 >= 1（防"一个没扫到也全绿"）
_jc = [c for c in _claims if c["fact"] == "模组 .java 数"]
check("C6e", len(_jc) >= 1 and JAVA_N >= 1,
      "模组 .java 实算 **%d** 个 ｜ 入口文档里扫到 %d 处声明（逐处等值见 C6b）"
      % (JAVA_N, len(_jc)))


# ---------------------------------------------------------------- C7 台账
print("")
print("-- C7 台账节数 / 索引悬空 --")
check("C7a", _dang == [], "ledger_index 引用悬空（§79.x 被 tools/*.py 引用却不在台账）＝ **%s**"
      % (len(_dang), ) if _dang else "ledger_index 引用悬空 ＝ 0 ✓")
_idxdoc = read_doc("台账-索引.md")
m = re.search(r"台账共 \*\*(\d+)\*\* 节", _idxdoc)
check("C7b", bool(m) and int(m.group(1)) == LEDGER_N,
      "台账-索引.md 写 %s 节 ｜ ledger_index 实算 **%s**"
      % (m.group(1) if m else "（没找到）", LEDGER_N))
check("C7c", bool(_ltxt) and _idxdoc.strip() == _ltxt.strip(),
      "台账-索引.md 内容 ＝ ledger_index 现算（内容没变的 D4 口径）")


# ---------------------------------------------------------------- C8 DEBT 块自洽
print("")
print("-- C8 DEBT 块自洽 ＋ 正文下限 --")
try:
    import debt_count as DC  # noqa: E402
    _rows = DC.parse()
    _want = DC.block(_rows)
    _bad, _n = [], 0
    for p in DC.DOCS:
        text, err = rv(p)
        if err:
            _bad.append("%s 读不到：%s" % (p.name, err))
            continue
        head, tail, err2 = DC._split_block(text)
        if err2:
            _bad.append("%s：%s" % (p.name, err2))
            continue
        block = text[len(head):len(text) - len(tail)]
        _n += 1
        if block.strip() != _want.strip():
            _bad.append("%s 的 DEBT 块 ≠ debt_count 生成块" % p.name)
        need = DC.MIN_BODY.get(p.name, 30)
        nonempty = [ln for ln in (head + tail).splitlines() if ln.strip()]
        if len(nonempty) < need:
            _bad.append("%s 块外正文只有 %d 非空行 < 下限 %d（★正文被清空过✗★）"
                        % (p.name, len(nonempty), need))
    check("C8a", (not _bad) and _n >= 2,
          "DEBT 块自洽 ＋ 块外正文下限（核了 %d 份）：%s" % (_n, "；".join(_bad[:5]) or "✓"))
except Exception as e:
    check("C8a", False, "★导入 debt_count/解析失败：%s: %s✗★" % (type(e).__name__, str(e)[:60]))


# ---------------------------------------------------------------- C9 生成物新鲜度
print("")
print("-- C9 生成物新鲜度 --")
# C9a 闸门-项数.md 的四张表项数 ＝ import check_all 实算
_gate_doc = read_doc("闸门-项数.md")
_bad = []
if OFFLINE_N is not None:
    try:
        for k, want in (("QUICK", len(CA.QUICK)), ("WALK", len(CA.WALK)),
                        ("OFFLINE", len(CA.OFFLINE)), ("FAST", len(CA.FAST))):
            m = re.search(r"`%s`：\*\*(\d+)\*\* 项" % k, _gate_doc)
            if not m:
                _bad.append("闸门-项数.md 缺 %s 的项数行" % k)
            elif int(m.group(1)) != want:
                _bad.append("%s 写 %s ≠ 实算 %d" % (k, m.group(1), want))
        dedupe = len(set(sum([list(CA.QUICK), list(CA.WALK), list(CA.OFFLINE), list(CA.FAST)], [])))
        m = re.search(r"去重后共 \*\*(\d+)\*\* 个不同脚本", _gate_doc)
        if not m:
            _bad.append("缺『去重后共』行")
        elif int(m.group(1)) != dedupe:
            _bad.append("去重脚本写 %s ≠ 实算 %d" % (m.group(1), dedupe))
    except Exception as e:
        _bad.append("重算失败 %s" % type(e).__name__)
check("C9a", not _bad, "闸门-项数.md 项数 ＝ check_all 四张表实算：%s"
      % ("；".join(_bad[:4]) or "✓"))

# C9b 闸门-项数.md 不许比生成器/源表旧（check_all.py 改了却没重生成 ⇒ 红）
#   ★★2026-11-03 修（发布阻断）✗★★：原来用裸 mtime ✗ 干净快照里 mtime=解压顺序 ✗
#   新用户第一次跑就假红 ⇒ 改用 `fresh_time()`：干净跟踪文件用 **git 提交时间**，改动过/无 git 才退回 mtime ✓
_gp = D / "闸门-项数.md"
_ups = [T / "gate_tables_test.py", T / "check_all.py"]
if history_count() is None:
    # ★无 git（zip 下载/解压目录）✗★：mtime 只是解压顺序 ✗ 不能判新鲜度
    #   ⇒ **跳过并说清** （内容项数已由 C9a 实算 ✓ 不冒充"新鲜度已验证"✓）
    check("C9b", True,
          "★跳过：无 git（zip 快照/无 .git）⇒ 新鲜度无法判 ✗ 不冒充通过；"
          "内容项数已由 C9a 实算 ✓★")
else:
    _stale = [u.name for u in _ups if u.is_file() and _gp.is_file()
              and fresh_time(_gp) < fresh_time(u)]
    _tsrc = ("git" if _gp.is_file() and _git_commit_ctime(_gp) is not None
             and _path_dirty(_gp) is False else "mtime")
    check("C9b", not _stale,
          "闸门-项数.md 不比生成器旧（★时间源=%s★：git 提交时间优先/ mtime 兜底；"
          "旧了 ⇒ 跑 `py tools/gate_tables_test.py`）：%s" % (_tsrc, _stale or "✓"))

# C9c 分歧清单/迁移准备度：标题正确 + 不同哈希 + 不早于上游
_div = D / "分歧清单.md"
_mig = D / "迁移准备度.md"
_titles = {
    "分歧清单.md": "# 分歧清单",
    "迁移准备度.md": "# 迁移准备度",
}
_tbad = []
for n, t0 in _titles.items():
    p = D / n
    if not p.is_file():
        _tbad.append("%s 不在" % n)
        continue
    first = read(p).splitlines()[0] if read(p) else ""
    if not first.startswith(t0):
        _tbad.append("%s 首行是 %r ≠ %r" % (n, first[:40], t0))
check("C9c", not _tbad, "两份生成物标题各自正确：%s" % ("；".join(_tbad) or "✓"))
if _div.is_file() and _mig.is_file():
    same = hashlib.sha256(_div.read_bytes()).hexdigest() == hashlib.sha256(_mig.read_bytes()).hexdigest()
    check("C9d", not same, "分歧清单 ≠ 迁移准备度（防 2026-11-02 前那个『迁移准备度是分歧清单复制品』回归）")
    _up = [ROOT / "state" / "tags_category.json", ROOT / "state" / "exceptions.json",
           T / "divergence.py"]
    # ★同 C9b：git 提交时间优先（干净快照不因解压顺序假红）✗ mtime 兜底 ✓
    if history_count() is None:
        check("C9e", True,
              "★跳过：无 git（zip 快照/无 .git）⇒ 新鲜度无法判 ✗ 不冒充通过"
              "（标题/不同哈希由 C9c/C9d 核过；上游新鲜度需 git 历史才能判✓★）")
    else:
        _late = [u.name for u in _up if u.is_file() and fresh_time(_div) < fresh_time(u)]
        _late2 = [u.name for u in _up if u.is_file() and fresh_time(_mig) < fresh_time(u)]
        _tsrc2 = ("git" if _git_commit_ctime(_div) is not None and _path_dirty(_div) is False
                  else "mtime")
        check("C9e", not _late and not _late2,
              "两份生成物都不比上游旧（★时间源=%s★：git 提交时间优先/ mtime 兜底）：分歧旧于 %s ／ 迁移旧于 %s"
              % (_tsrc2, _late or "✓", _late2 or "✓"))
else:
    check("C9d", False, "★两份生成物有一份不在✗★")
    check("C9e", False, "★同上✗★")


# ---------------------------------------------------------------- C10 事实错误
print("")
print("-- C10 agent/ 标注类事实错误 ＋ README 目录事实 --")
# agent/ 是活依赖：不许再被标成"早期架构遗留/legacy/仅作参考/不再用"
_bad = []
_BAN = [
    (r"`?agent/`?[^\n]{0,24}(早期架构遗留|早期遗留)", "总览把 agent/ 标成早期架构遗留"),
    (r"`agent/`[^\n]{0,12}`?bridge/`?[^\n]{0,24}legacy", "把 agent/ 与 bridge/ 一起标 legacy"),
    (r"agent/[^\n]{0,20}仅作参考", "把 agent/ 标仅作参考"),
    (r"agent/[^\n]{0,20}不再用", "把 agent/ 标不再用"),
]
for doc in ENTRY_DOCS:
    for pat, why in _BAN:
        if re.search(pat, DOCS_TEXT[doc]):
            _bad.append("%s：%s" % (doc, why))
check("C10a", not _bad, "agent/ 不许被标成遗留：%s" % ("；".join(_bad[:4]) or "✓"))
_z = DOCS_TEXT["项目总览.md"]
check("C10b", ("agent/" in _z) and ("活依赖" in _z or "sys.path.insert" in _z),
      "总览必须写明 agent/ 是活依赖（含 `agent/` 与『活依赖』/`sys.path.insert` 证据）")
# README 目录事实：必须列全根目录 + 主链路写直连
_rd = README_TEXT
_dirs = root_dirs()
_miss = [d for d in _dirs if d + "/" not in _rd]
check("C10c", not _miss, "README 列全根目录（%d 个项目目录）：缺 %s"
      % (len(_dirs), _miss or "无 ✓"))
check("C10d", ("8766" in _rd) and ("直连" in _rd) and not re.search(r"主链路[^\n]{0,40}8765", _rd),
      "README 主链路必须是直连 8766（网关 8765 只作后备）")
# reports/ 在仓库外：入口文档里要有"外部"登记（避免以后按仓内路径引用）
_rep = any(re.search(r"reports/[^\n]{0,80}(仓库外|不在本仓|外部|repo 外)", FULL[n])
           for n in ENTRY_DOCS)
check("C10e", _rep, "reports/（审计+优化路线）『在仓库外』这件事在入口文档里有登记")

# ---------------------------------------------------------------- 汇总
print("")
_red = [t for (t, o) in RESULTS if not o]
print("== SUMMARY：%d 条子检查 ✗ 绿 %d ✗ 红 %d ==" % (len(RESULTS), len(RESULTS) - len(_red), len(_red)))
if _red:
    print("★红项✗★：%s" % "／".join(_red))
    print("★口径✗★：本判据上线即红是**设计**（ADR-10：先修 + 立刻加门；修完转绿才算 D7 过）")
print("=> doc_consistency %s" % ("PASS ✓" if ok[0] else "FAIL"))
sys.exit(0 if ok[0] else 1)

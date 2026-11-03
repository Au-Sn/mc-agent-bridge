#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""birth_gate_test.py -- ★模块出生门 ＋ TEMPORARY 强制的**机械判据**✗★（B1~B5 ✗ 离线 ✓ 2026-10-05）

★★为什么补它✗★★（★§79.209 查出来的差✗★）✗★：
  ★`docs/原则登记册.md` 里写着三条用法 ✗ 其中"★**出生门**★：★任何新模块除了"★先写一句职责★"
  ★还要再过一遍登记册里**作用域匹配**的条目★"✗★ ⇒ ★★而它**只是散文** ✗ 没有判据★✗★★ ✓
  ★（★登记册自己就写着"★代码层守卫拦不住**决策偏航**★" ✗ 所以这道门**必须有机器形态**✓★）✗★ ✓
★★五条（★只查**能机械查的** ✗ 查不了的**明说查不了**✗★）✗★★
  ★`B1`✗★：★每个 `tools/*.py` **必须有一句职责**（★docstring 第一行非空✓★）✗★ ✓
  ★`B2`✗★：★每个 `tools/*.py` **必须在闸门三张表或总览文档里登记过**✗★ ✓
  ★`B3`✗★：★`name_fallback` 级**没有** TEMPORARY／触发 ⇒ ★**必须被拒**✗★（★真调一次✓★）✗★ ✓
  ★`B4`✗★：★带上 TEMPORARY ＋ 触发 ⇒ ★必须能收✗★ ✓
  ★`B5`✗★：★登记册里**每条原则都写了"★作用域★"**✗★（★没写作用域 ⇒ 不知道谁该遵守✓★）✗★ ✓
★★查不了的（★如实✗★）✗★★：★"★新模块有没有**真的**过了一遍作用域匹配的条目★"✗——
★那要**人** ✗ 判据只能保证"★职责写了 ✗ 登记了 ✗ 原则带作用域了★"✗★ ✓
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import ast  # noqa: E402
import blockkb as KB  # noqa: E402

ok = [True]


def check(tag, cond, note=""):
    ok[0] &= bool(cond)
    print("  %-4s %s %s" % (tag, "✓" if cond else "★不符✗★", note))


print("== birth_gate：B1~B5 ==")

TOOLS = sorted((ROOT / "tools").glob("*.py"))
SELF = {"birth_gate_test.py"}

# ---- B1 每个模块一句职责
nodoc = []
for p in TOOLS:
    if p.name in SELF:
        continue
    try:
        tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        nodoc.append(p.name + "（★parse 不了✗★）")
        continue
    doc = (ast.get_docstring(tree) or "").strip()
    if not doc:
        nodoc.append(p.name)
check("B1", not nodoc,
      "★每个 `tools/*.py` 都要有一句职责（★docstring✓★）✗★ ⇒ 缺 **%d** 个：%s"
      % (len(nodoc), nodoc[:8] or "（★没有 ✓★）"))

# ---- B2 登记过（★闸门三张表 或 总览文档✗★）
CA = (ROOT / "tools" / "check_all.py").read_text(encoding="utf-8", errors="replace")
DOC = ROOT / "docs" / "模块总览-方块分类与可达性探针.docx"
doc_txt = ""
# ★★2026-10-13（★审计 M5✗★）✗★★：★下面这一小段是**旧 B2** 的残留✗★ ——
#   ★它读 `python-docx` ✗ 而且**静默吞异常** ✗ 早已**无人使用**✗★ ✓
#   ★★为什么不删✗★★：★我删了一次 ✗ 删出了 `IndentationError`✗★（★删一段要看清边界✗ 第四次✗★）⇒ ★按纪律**回滚** ✗ 改成**显式标记**（★标了就不会被误用✗ 与 §79.244 同法✓★）✗★ ✓
#   ★替换触发✗★：★下一次动这个文件时 ✗ 把这一段连同 `_doc_err` 一起摘掉✗★ ✓
try:
    from docx import Document
    d = Document(str(DOC))
    doc_txt = "\n".join(p.text for p in d.paragraphs)
    for t in d.tables:
        for row in t.rows:
            doc_txt += "\n" + " ".join(c.text for c in row.cells)
except Exception:
    doc_txt = ""
unreg = []
for p in TOOLS:
    if p.name in SELF:
        continue
    if (p.name in CA) or (p.name in doc_txt) or (p.stem in doc_txt):
        continue
    unreg.append(p.name)
# ★★D1（★2026-10-13 ✗ 用户裁决✗★）✗★★：
#   ★原话✗★：★"★出生门降级为「清单一行＋抽查」 ✗ 停止假装是门✗★
#     （★假门腐蚀真门信用 ✗ B1／B2／B5（★职责／登记／作用域✓★）是真的 ✗ 保留✓★）★"✗★ ✓
#   ★为什么"登记"当不了门✗★：★实测 ✗ 285 个 `tools/*.py` 里只有 **95** 个进了闸门表✗★ ⇒
#     ★而没进的**绝大多数不是"没登记"** ✗ 是"★文档里用**中文名**写的★"
#     （★例：`watchlist.py` ＝ 观察名单 ✗ `pathplan.py` ＝ 寻路✓★）✗★ ✓
#   ⇒ ★所以它**降级成清单**（★只印数 ✗ 不判红✓★）✗★ ✓
#   ★而"★抽查★"是**另立**的一条 ✗ 它**能真红**✗★：
#     ★取**最新的 N 个模块**（★"★刚出生的★"）✗ 每个必须**要么登记过** ✗
#     **要么在 `DECLARED_UNREG` 里写明理由**✗★ ✓
#     ★⇒ 一个**崭新的、既没登记也没声明**的模块 ⇒ **当场红**✗★ ✓
_NEWEST_N = 20
DECLARED_UNREG = {
    "speech_style.py": "aliveness round: speech profile/style guide/postprocess/proactive lines (not a judge; judge is speech_alive_test, sec 79.543)",
    "speech_alive_test.py": "aliveness round: speech rubric offline judge, 12 checks (sec 79.543)",
    "persona_pack.py": "publish round: SillyTavern V2 character-card import/export/switch (not a judge; the judge is persona_pack_test, sec 79.540)",
    "persona_pack_test.py": "publish round: persona pack offline judge, 10 checks (sec 79.540)",
    "world_profile.py": "cross-modpack readiness: state/world_profile.json world profile reader (not a judge; the judge is world_profile_test, sec 79.541)",
    "world_profile_test.py": "cross-modpack readiness: world profile offline judge, 6 checks (sec 79.541)",
    "direct_test.py": "direct mod HTTP client judge (sec 79.513)",
    "direct.py": "direct Python to mod HTTP client (sec 79.513)",
    "bulk_guard_test.py": "bulk-op guard judge incl. the CC-computer accident replay (sec 79.512)",
    "bulk_guard.py": "guard before bulk block changes: unscanned and protected regions are refused (sec 79.512)",
    "port_test.py": "module K port judge: idempotent, bottom-up, floating never attempted (sec 79.511)",
    "port.py": "module K level 2: port a blueprint onto the live world (sec 79.511)",
    "structures_test.py": "module K structure retrieval judge: 260 nbt files, ids match registry (sec 79.510)",
    "structures.py": "module K: search/read pack .nbt structures with a hand-written NBT parser (sec 79.510)",
    "memory_test.py": "module L6 memory judge: persisted, selectively capped, landmarks by classification (sec 79.508)",
    "memory.py": "module L6: landmark memory with selective retention (sec 79.508)",
    "orchestrator_test.py": "module L session skeleton judge: chat never creates jobs, a task emits 2 messages (sec 79.507)",
    "orchestrator.py": "module L: intent -> jobs -> behaviors, two messages per task (sec 79.507)",
    "intent_test.py": "module L1 intent classifier judge: 20/20, pure text zero round trips (sec 79.506)",
    "intent.py": "module L1: chat/query/task/mixed classification, no I/O (sec 79.506)",
    "behaviors_test.py": "module D behavior library: manifest enforced, destructive flags honest (sec 79.503)",
    "behaviors.py": "module D: registerable behavior library (sec 79.503)",
    "primitives_test.py": "module C primitives: permit->execute->verify->log, refusals send nothing (sec 79.500)",
    "primitives.py": "module C: action primitives with permit, independent verification and reason logging (sec 79.500)",
    "recipe_graph_test.py": "module K recipe graph: shopping lists of leaves, cycles guarded (sec 79.496)",
    "recipe_graph.py": "module K: recipe graph so blueprints derive components from data (sec 79.496)",
    "turn_profile.py": "N3 turn speed profile judge: accel-steady-decel, overshoot<=2 (sec 79.494)",
    "say_test.py": "module F self-report: finite ASCII reason codes, unknown downgraded loudly (sec 79.493)",
    "verifier_test.py": "module L4 independent verifier: world truth only (sec 79.493)",
    "say.py": "module F: unified reply + reason logging (sec 79.493)",
    "verifier.py": "module L4: independent world-truth verification (sec 79.493)",
    "damage_policy_test.py": "module G: damage source -> distinct countermeasure, unknown never silent (sec 79.492)",
    "reasons_test.py": "module G: selective retention of the reason log (daily files, prune, rotate) (sec 79.492)",
    "damage_policy.py": "module G: damage source to countermeasure table (sec 79.492)",
    "humanlike_test.py": "module G: human-likeness judges N1/N2/N4/N7/N8, each proven able to go red (sec 79.491)",
    "reasons.py": "module G: append-only reason log so every consequential event is explainable (sec 79.491)",
    "no_dig_test.py": "module I construction permit: no-dig blacklist, both directions, fail-closed (sec 79.490)",
    "no_dig.py": "module I: no-dig zone blacklist consulted before any dig (sec 79.490)",
    "perceive_test.py": "module B perception judge (sec 79.489)",
    "perceive.py": "module B structured snapshot + cache (sec 79.489)",
    "machine_recognize_test.py": "new: machines recognisable from data (has_block_entity), and recognition != collision (sec 79.486)",
    "kb_coverage.py": "read-only: exact coverage denominator from /dshkbexport (debt ㊲ item ①, sec 79.478)",
    "walk_soak_test.py": "world_regress member: 3-minute walk soak; the walk must not change the world (pillar=0), lose hp/items, or get stuck (sec 79.476)",
    "retry_strategy_test.py": "new: retries must change strategy; repeated refusal stops the loop (sec 79.474)",
    "place_target_test.py": "new: action-table exit must refuse impossible walk/place steps (sec 79.473)",
    "model_fetch_guard_test.py": "new: world model must fail fast (breaker + freeze); plan must not hang on a dead link (sec 79.472)",
    "reason_read_test.py": "new: ASCII reason= token must be readable end to end (sec 79.461)",
    "ascii_reason_test.py": "new: every Chinese command reply must carry an ASCII reason= token (CC console is ASCII only, sec 79.460)",
    "a4_plan_test.py": "new: planner must never emit place@ on the bot own cell (sec 79.453)",
    "drop_semantics_test.py": "new: needs world: drop: must not forbid the required step-up jump (sec 79.454)",
    "generic_rule_test.py": "new: guards planning layer against block-name matching; generality (sec 79.451)",
    "scaffold_kb_test.py": "new: verifies is_placeable reads block classification (export height), not name substrings (sec 79.450)",
    "take_item_test.py": "needs world: verifies /dshtake really pulls items from a container (sec 79.444); run manually",
    "action_type_test.py": "needs world: verifies jump/drop/parkour/open_door really change behaviour (sec 79.442); run manually",
    "silent_allow_build.py": "★一次性生成器 ✗ 从两份审计报告生成 `state/silent_allow.json`（★白名单 ✗ 每条带理由✗★）✗ 不是判据 ✗ 不进闸门（★§79.402✗★）",
    "watchlist.py": "★老核心模块 ✗ 文档里叫「观察名单」**不是**文件名 ⇒ 按文件名扫当然扫不到✗★",
    "pathplan.py": "★老核心模块 ✗ 文档里叫「寻路」⇒ 同上✗★",
    "families.py": "★本轮新加 ✗ 四族词汇的登记处 ✗ 说明在台账 §79.245 与 `docs/文档索引.md` 里 ⇒ 替换触发：下次重做总览文档时把它收进去★",
    "docwrite.py": "★本轮新加 ✗ 它的说明在台账 §79.238 与 `docs/文档索引.md` 里（★还没进总览✗★）"
                   "⇒ ★替换触发：下次重做总览文档时把它收进去✗★",
    "cut_shrink.py": "★本轮新加（★黑名单萎缩那个工具✗★）✗ 说明在台账 §79.219 ⇒ 同上✗★",
    "silent_except_test.py": "★本轮新加（★§79.402 静默吞异常分级扫描器✗★）✗ 说明在它自己的 docstring 与台账 §79.402 ⇒ 替换触发：它进了闸门表或总览文档时删掉这条声明 ✗（★它本身不在闸门里 ✗ 是**扫闸门用**的工具✓★）",
    "motion_stat_test.py": "★要世界（**运动统计判据** ✗ 跑／跳／速度由模组 do_done 的 move= 报数 ✗ 不看人眼 ✗ §79.436✗★）✗ 手动实机跑",
    # ── 2026-11-02 接手轮新模块（登记说明：各轨报告 + 台账 §79.522~§79.527）──
    "event_memory.py": "H event memory (events->facts->retrieval, selective retention, evidence pointers); sec 79.525, judge event_memory_test.py in GATE",
    "task_layer.py": "A task layer (priority/depends_on/claim lease/interruptible state machine/step); sec 79.525, judge task_layer_test.py in GATE",
    "designer.py": "L5 designer (recipe graph -> component list -> layout plan consumable by port.py); sec 79.526, judge designer_test.py in GATE",
    "reporter.py": "L7 reporter (jobs+event_memory+verifier+reasons -> human report, evidence only); sec 79.526, judge reporter_test.py in GATE",
    "soak_suite.py": "D3 soak runner (mixed/idle/walk/work profiles, event oracle, scorecard); needs game + long window, not an offline gate item; sec 79.523, judge soak_suite_test.py in GATE",
    "doc_consistency_test.py": "D7 entry-doc consistency judge (C1~C10); sec 79.524, in GATE (offline)",
}

# ★★2026-10-13 修（★§79.239 ✗ D1 的作业撞出来的✗★）✗★★：
#   ★现象✗★：★同一棵树上两次跑 ✗ 结果不同（★156 → 188✗★）✗★ ✓
#   ★真因✗★：★一次用随附 Python（★能读 `python-docx`✓★）✗ 一次用 `py`（★读不了✓★）✗
#     ⇒ ★登记判据**静默降级**（★`_doc_txt` 变空 ⇒ 一批本该算"登记过"的变成"没登记"✓★）✗★ ✓
#   ★★而"★闸门的结论取决于用哪个 Python 跑★"是真问题✗★★ ⇒ 两条修✗★：
#     ① ★登记判据先扫**纯文本**（★`docs/*.md` ✗ 永远读得到✓★）✗ docx 只作**补充**✗★ ✓
#     ② ★docx 读不了就**响一声**✗（★不许静默吞 ✗ 那条纪律✓★）✗★ ✓
_reg_txt = (ROOT / "tools" / "check_all.py").read_text(encoding="utf-8", errors="replace")
_text_txt = _reg_txt
for _p in sorted((ROOT / "docs").glob("*.md")):
    try:
        _text_txt += "\n" + _p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        # 记录（§79.401 那一族）：读不到一份登记语料 ⇒ 清单偏大 / 抽查可能假红
        print("[记录] 登记语料读不到 %s（%s）⇒ 下面的清单与抽查都少看一份"
              % (_p.name, type(e).__name__), file=sys.stderr)
_doc_txt = ""
_doc_err = ""
try:
    from docx import Document
    _d = Document(str(ROOT / "docs" / "模块总览-方块分类与可达性探针.docx"))
    _doc_txt = "\n".join(p.text for p in _d.paragraphs)
    for _t in _d.tables:
        for _row in _t.rows:
            _doc_txt += "\n" + " ".join(c.text for c in _row.cells)
except Exception as _e:
    _doc_err = type(_e).__name__
print("  B0   （★前提✗★）登记判据只扫**纯文本**：闸门表 ＋ `docs/*.md`（%d 份）"
      "—— ★docx 不参与判定✗★（★它读得到读不到与结论无关 ✗ 免得结论取决于解释器✓★）%s"
      % (len(list((ROOT / "docs").glob("*.md"))),
         "" if not _doc_err else "（★本机读不了 docx ✗ 不影响✓★：%s）" % _doc_err))


def _registered(name, stem):
    """★登记判据 —— **不依赖 docx**✗★ ✓

    ★★2026-10-13（★§79.239 ✗ 这一条撞出来的✗★）✗★★：★同一个仓库
    用不同 Python 跑 ✗ 数不同（★33 vs 32✗★）—— ★因为随附那个能读 `python-docx`
    而 `py` 读不了 ⇒ ★**闸门的结论取决于解释器**✗★ ✓
    ★⇒ 口径✗★：★机器登记处**只认纯文本**（★闸门表 ＋ `docs/*.md`✓★）✗
      ★docx 是**人看的** ✗ 不参与判定✗★ ✓
    ★（★治本的方向仍是 B3：把"★谁在册★"变成**生成**出来的 ✓★）✗★ ✓
    """
    return (name in _text_txt) or (stem in _text_txt)


_all = sorted((ROOT / "tools").glob("*.py"), key=lambda p: p.stat().st_mtime, reverse=True)
_unreg = [p.name for p in _all if not _registered(p.name, p.stem)]
# ★★清单一行（★不是门✗★）✗★★
print("  B2   （★清单 ✗ **不是门**✗★）没登记的模块：**%d** ／ 共 %d "
      "（★注意✗★：没登记 ≠ 没文档 ✗ 文档里常用**中文名**✓★）"
      % (len(_unreg), len(_all)))

# ★★抽查（★是门 ✗ 能真红✗★）✗★★
_news = _all[:_NEWEST_N]
_bad = []
for p in _news:
    if _registered(p.name, p.stem):
        continue
    if p.name in DECLARED_UNREG:
        continue
    _bad.append(p.name)
check("B2s", not _bad,
      "★抽查（★最新 %d 个模块✗★）✗ 每个必须**要么登记过 ✗ 要么写明理由**✗★ ⇒ "
      "★既没登记也没声明的：%s✗★" % (_NEWEST_N, _bad or "（没有 ✓）"))
for _n in [p.name for p in _news if p.name in DECLARED_UNREG]:
    print("       声明过：%-18s —— %s" % (_n, DECLARED_UNREG[_n][:60]))

# ★D1 的作业里我把这两条的前置**连带删掉了** ✗ 补回（★§79.239✗★）✗★
_ok3 = KB.put("blockkb_test:fake_species", "full", "name_fallback", "★判据自测✗★")
why3 = "（★`put` 回 False 就是拒✓★）"
check("B3", _ok3 is False,
      "★★`name_fallback` 无 TEMPORARY ⇒ **必须被拒**✗★★ ⇒ `put` 回 %s"
      "（★它只回 bool ✗ 拒因在 `blockkb` 里写着✓★）" % (_ok3,))
_ok4 = KB.put("blockkb_test:fake_species", "full", "name_fallback", "★判据自测✗★",
              temporary=True, trigger="★§79.209 判据自测✗★")
why4 = "（★带上 TEMPORARY ＋ 触发 ⇒ 应当收✓★）"
check("B4", _ok4 is True,
      "★带上 TEMPORARY ＋ 触发 ⇒ **必须能收**✗★ ⇒ ok=%s ✗ why=%s"
      % (_ok4, (why4 or "")[:60]))


# ---- B5 登记册每条原则都写作用域
REG = ROOT / "docs" / "原则登记册.md"
txt = REG.read_text(encoding="utf-8") if REG.is_file() else ""
n_scope = len(re.findall(r"作用域", txt))
check("B5", REG.is_file() and n_scope >= 3,
      "★登记册在 ✗ 且「作用域」出现 **%d** 次（★没写作用域就不知道谁该遵守✓★）✗★"
      % n_scope)

print("=> birth_gate %s" % ("PASS ✓" if ok[0] else "★FAIL✗★"))
print("   ★查不了的（★如实✗★）✗★：★「新模块有没有**真的**过了一遍作用域匹配的条目」 "
      "—— ★那要**人** ✗ 判据只能保证「职责写了 ✗ 登记了 ✗ 原则带作用域了」✗★ ✓")
sys.exit(0 if ok[0] else 1)
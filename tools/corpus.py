#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""corpus.py -- ★台词库（手写可改 ✓ 毫秒级 ✓ 零 token ✓）★（2026-09-30 ✓ 用户第 2／6 条 ✓）

## 为什么要有它 ✗（用户原话要点 ✓）
  「分层生成：**语料库扛 80%**，LLM 只接开放对话」✓
  ⇒ 播报／反应／闲聊／求助／邀功／承诺 **一律从库里抽** ✓ 填**真值槽位** ✓
  ⇒ ★只有 `接话`（开放对话）才走模型 ✗★
  ★好处★ ✗：① 毫秒级 ✓ ② 零 token ✓ ③ **人设不漂**✗（模型每句重写一遍人格 ⇒ 迟早走形 ✓）

## 库长什么样 ✗（★这是**给人改**的文件** ✗ 不是 json ✗★）
  `personas/<角色>.lines.txt` ✓ 一行一句 ✓ `##` 分节 ✓ `#` 注释 ✓：
  ```
  ## 播报/状态/tired/标准
  - 体力条没有显示，但我确实有点困了。
  - 再忙一会儿，我就找个角落趴下。
  ```
  ★键的写法＝查找顺序里的某一层**原样**✗★（`speech.pick_from_corpus` 一层层往下找 ✓）：
    `<类型>/<为什么>/<语气>/<关系>` → `<类型>/<为什么>/<语气>` → `<类型>/<为什么>`
    → `<类型>` → `*`（★`接话` 不吃 `*` ✗ P128 ✓）
  ⇒ 写不出 `/关系` 那一层**没关系** ✗（往下掉一层就行 ✓ 少写一层不该整类失声 ✓）

## 槽位 `{…}` ✗（★库里的句子要么**完整**✓ 要么**有真值**✓ 二者必居其一 ✗★）
  `{job}` `{n}` `{item}` `{reason}` … ✓ ⇒ 填不上真值的那条**整条不用** ✗（`speech.fill` ✓ P7 同族 ✓）
  ★`lint()` 会把"**永远填不上**的槽"（没有哪个意图会带这个字段 ✓）报出来 ✗★
  —— 那种句子是**死句子** ✗：写进去看着像有 ✓ 永远不会被选中 ✗

## 边界 ✓
  · 纯逻辑 ✓ 不读世界 ✗ 不调模型 ✗ 不发消息 ✗ ⇒ 离线单测 ✓（`corpus_test.py` ✓）
  · 它是**数据 + 解析** ✓；"什么时候说"是 `speech.py` ✗；"怎么发"是 `talk.py` ✗
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT = ROOT / "personas" / "dafeiyu.lines.txt"
# ★句子的"黑名单"✗★ ✓（`speech_audit.py --bad` 写它 ✓ 一行一句**整句**✓ 见 `is_banned` ✓）
DEFAULT_BAN = ROOT / "personas" / "dafeiyu.banned.txt"

# ★意图类型 ⇒ 是不是"开放对话"✗★（与 `speech.OPEN_KINDS` **同一口径** ✓ P106 ✓）
OPEN_KINDS = ("接话",)

# ★意图类型清单**从 speech 抄一份**✗★ —— 抄是因为本模块要能**单独离线**跑 ✓
#   （★两处口径不一致 ⇒ 由 `corpus_test.py` K5 直接对账 ✗ 不许靠人记 ✗★）
KINDS = ("播报", "反应", "闲聊", "接话", "求助", "邀功", "承诺")

# ★"真值槽位"的白名单✗★ ✓：只有这些字段**真的有意图会带** ✓（其余 = 死句子 ✗）
#   ★① 我们自己造的那些（任务账本／idle／库内部 ✓）★
KNOWN_SLOTS = {
    "job", "phase", "detail",          # job 迁移（speech.on_job_transition ✓）
    "idle_s", "reason",                # 没话找话（speech.on_idle ✓）
    "why_key", "event",                # 库分层键 / 事件名（speech.on_game_event ✓）
}
#   ★② 模组事件里带的那些 ⇒ **从模组源码里读**✗★（★不靠我记 ✗ —— 我记漏过一次 ✓ 见 P131 ✓★）
MOD_SRC = ROOT / "mod" / "src" / "main" / "java" / "com" / "dsh" / "bridge" / "DshBridgeMod.java"
EV_CALL = re.compile(r'ev\("([a-z_]+)",')
LIT = re.compile(r'"([^"]*)"')
KV = re.compile(r"([a-z_][a-z0-9_]*)=")


def mod_slots(path: Path | str = None) -> set:
    """★模组 `ev(...)` 里**真出现过的字段名**✗★ ✓ ⇒ 死槽位体检用它当白名单 ✓

    ★为什么从源码读✗★：`{left_s}` 这种槽位**只有模组真发**才算活的 ✓
      而我第一版是**手抄一份**✗ ⇒ 抄漏一个 ⇒ 库里的句子被误判成"死句子" ✗
      （实测 ✓：`{left_s}` 就被误报过 ✓ ⇒ 现在改成**读源码** ✓ 漏不了 ✓）
    ★为什么不能"整行抓字符串"✗★（实测 ✓ 第一版只抓到 14 个字段 ✗）：
      模组的 `ev("damage", "hp=" + hp + " delta=" + …)` 是**一串拼接**✗
      ⇒ 只抓第一个字符串字面量 ⇒ **后半段字段全丢** ✗
      ⇒ 口径 ✓：先圈出**这条语句**（到 `);` 为止 ✓）再把它里面**每个字符串字面量**都过一遍 ✓
    源码不在 ⇒ **退回空集** ✓（只留我们自己那几个 ✓ 宁可多报几个 ✗ 也别放过死句子 ✗）
    """
    p = Path(path) if path else MOD_SRC
    if not p.is_file():
        return set()
    txt = p.read_text(encoding="utf-8")
    out = set()
    for m in EV_CALL.finditer(txt):
        seg = txt[m.end():m.end() + 400]
        cut = seg.find(");")
        seg = seg[:cut if cut >= 0 else len(seg)]
        for lit in LIT.findall(seg):
            out |= set(KV.findall(lit))
    return out


def known_slots() -> set:
    """★能填的槽位全表★ ✓ ＝ 我们造的 ＋ 模组真发的 ✓"""
    return set(KNOWN_SLOTS) | mod_slots()


SLOT = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
SEC = re.compile(r"^##\s+(.+?)\s*$")
BULLET = re.compile(r"^\s*[-*]\s+(.*\S)\s*$")

# ★★不许进台词的字符✗★★（2026-09-30 **实机**发现 ✓ ⇒ P136 ✓）：
#   实测 ✓：`Talk.say()` 发出去的中文在游戏里是好的 ✓ **但 `✓`／`✗`／`★` 变成了 `?`** ✗
#     （游戏日志按**平台编码**写 ✓ 这几个符号**不在 GBK 里** ✗ ⇒ 落盘就成了 `?` ✓）
#   ★这三个符号是**我写文档的习惯**✗★（"✓ 做到了／✗ 没做到"）——
#     它属于**错题本／交接文档** ✓ **不属于台词** ✗（台词是**给玩家看的**✓ 不是给我标注的✗）
#   ⇒ 口径 ✓：出库（`load`）与写盘（`dump`）**两头都剥掉**✗ ＋ `lint()` 报出来 ✓
SPEECH_BAN_CHARS = "✓✗★"


def strip_marks(s: str) -> str:
    """★把"文档标记"从**台词**里剥掉✗★ ✓（顺带收掉多余空格 ✓）

    ⚠ 只剥**这三个**✗：`emoji`（🐟 之类）**不剥** ✗ ——
      那是用户在**渲染配置**里点名要的旋钮（用户第 6 条 ✓）✓ 它归 `persona_render` 管 ✓
    """
    t = str(s or "")
    for ch in SPEECH_BAN_CHARS:
        t = t.replace(ch, "")
    t = re.sub(r"\s{2,}", " ", t)
    # ★顺手收掉"标记留下的空格"✗★：`{hp} ✓）` 剥完会剩 `{hp} ）` ✗ ⇒ 中文标点前不留空格 ✓
    return re.sub(r"\s+([）)。，！？；：、」』])", r"\1", t).strip()


def parse_lines_text(txt: str) -> dict:
    """★手写台词库 ⇒ `{键: [句子]}` ✓★（`speech.render` 吃的就是这个形状 ✓）

    容错 ✓：`##` 之前的内容（说明文字 ✓）**全当注释** ✗；空句子 ✗ 丢掉；重复句子 ✗ 去重
    ★不许静默吞掉"看起来像句子但没挂在节里"的行 ✗★ ⇒ 交给 `lint()` 报 ✓
    """
    out: dict = {}
    key = None
    loose = []
    for ln in (txt or "").splitlines():
        m = SEC.match(ln)
        if m:
            key = m.group(1).strip()
            out.setdefault(key, [])
            continue
        if key is None:
            if ln.strip() and not ln.lstrip().startswith("#"):
                loose.append(ln.strip())
            continue
        b = BULLET.match(ln)
        if b:
            s = b.group(1).strip()
            if s and s not in out[key]:
                out[key].append(s)
        elif ln.strip() and not ln.lstrip().startswith("#"):
            loose.append(ln.strip())      # 节里没加 `-` ⇒ 也算"松散行" ✓ 报出来 ✓
    out["__loose__"] = loose
    return out


def dump_lines_text(corpus: dict, title: str = "台词库") -> str:
    """★反过来：`{键: [句子]}` ⇒ 手写格式 ✓★（导入后**给人接着改** ✓ 顺序稳定 ✓）

    ★写盘时**顺手剥掉文档标记**✗★ ✓（`strip_marks` ✓ 单一写入口 ⇒ 一处规则管到底 ✓ P106 ✓）
      ⇒ 于是"从上游导入／从我手写的 `MINE` 打底"都**不会再带 `✓✗★` 进台词**✗ ✓
    """
    L = ["# %s（一行一句 ✓ 改完直接生效 ✓ 不用动代码 ✓）" % title, ""]
    for k in sorted(corpus):
        if k in ("__loose__",) or not corpus[k]:
            continue
        L.append("## %s" % k)
        for s in corpus[k]:
            L.append("- %s" % strip_marks(s))
        L.append("")
    return "\n".join(L)


def kind_of(key: str) -> str:
    """键的第一段就是**意图类型** ✓（`播报/状态/tired/标准` ⇒ `播报` ✓）"""
    return (key.split("/")[0] if key else "").strip()


def lint(corpus: dict) -> list:
    """★结构体检 ✓ ⇒ 一串"问题"（空 = 干净 ✓）★ ✗

    查 ① 类型不认识 ✗ ② 松散行（没挂到任何节 ✗）③ **死槽位**（永远填不上 ✓）
       ④ 空节 ✗ ⑤ 键里段数太多（>4 层 ✗ 查找顺序根本到不了 ✓）
    """
    bad = []
    for s in corpus.get("__loose__") or []:
        bad.append("松散行（不在任何 `##` 节里 ✗ 永远不会被抽到）：%s" % s[:40])
    for k, lines in corpus.items():
        if k == "__loose__":
            continue
        parts = k.split("/")
        # ★`*` 是**合法的兜底层**✗★（`speech.pick_from_corpus` 的最后一级 ✓ P128 ✓）
        #   ✗ 实测 ✓：我加了 `## *` 之后体检报"类型不认识" ✗ ——
        #     是**体检这把尺子漏了这一层** ✓ 不是库错 ✓（同一格式两处认不同 ＝ P129 同族 ✓）
        if kind_of(k) not in KINDS and k != "*":
            bad.append("类型不认识 ✗：%s（只能是 %s ／ `*` ✓）" % (k, "／".join(KINDS)))
        if len(parts) > 4:
            bad.append("键层数 %d > 4 ✗：%s（查找顺序到不了 ✓）" % (len(parts), k))
        if not lines:
            bad.append("空节 ✗：%s" % k)
        for s in lines:
            dead = sorted(set(SLOT.findall(s)) - known_slots())
            if dead:
                bad.append("死槽位 %s ✗：%s" % (dead, s[:40]))
            marks = [ch for ch in SPEECH_BAN_CHARS if ch in s]
            if marks:
                bad.append("台词里有**文档标记** %s ✗：%s"
                           "（★游戏里会显示成 `?` ✗ 实测 ✓ ⇒ 见 P136 ✓★）" % (marks, s[:40]))
    return bad


def coverage(corpus: dict) -> dict:
    """★"库里扛得住吗"的账 ✓★（用户要的 80% 得**能算**✗ 不能靠感觉 ✓）

    返回 ✓：`{类型: 条数}` ✓ ＋ `covered`（≥1 条 ✓）／`open`（开放对话 ✓ 允许空 ✗）
    """
    n = {k: 0 for k in KINDS}
    for key, lines in corpus.items():
        if key == "__loose__":
            continue
        k = kind_of(key)
        if k in n:
            n[k] += len(lines)
    total = sum(n.values())
    return {"n": n, "total": total,
            "covered": [k for k in KINDS if n[k] > 0],
            "empty": [k for k in KINDS if n[k] == 0],
            "empty_closed": [k for k in KINDS if n[k] == 0 and k not in OPEN_KINDS]}


def banned(path: Path | str = None) -> set:
    """★禁用的句子★ ✓（★**整句精确匹配**✗★ —— 绝不子串 ✗ P105/P107 ✓）

    ★为什么要有它✗★（用户第 5 条"语言错题环"✓）：
      听到一句不对味的话 ⇒ 要么改库 ✓ 要么**禁掉它**✓
      ⇒ 而"禁"必须**留痕**（谁禁的、为什么 ✓ 见 `docs/语言错题本.md` ✓）
      ★不许悄悄删掉库里的句子✗★ —— 删了 ⇒ 下次导入又回来 ✗ 而且没人知道为什么少了一句 ✓
    """
    p = Path(path) if path else DEFAULT_BAN
    if not p.is_file():
        return set()
    out = set()
    for ln in p.read_text(encoding="utf-8").splitlines():
        s = ln.strip()
        if s and not s.startswith("#"):
            # ★★名单这头**也要归一化**✗★★（2026-09-30 ✓ 判据 Q6 当场抓到 ✓）：
            #   ✗ 库里的句子出库时被 `strip_marks` 剥过 ✓ 而名单里存的是**用户原样打的**那句 ✗
            #     ⇒ 用户复制的带 `✗` 的那一版 **永远匹配不上** ✗ ⇒ ★禁了却没生效、还不报错✗★
            #   ⇒ 口径 ✓：**两条路都剥** ✗（`load` 剥句子 ✓ `banned` 剥名单 ✓）
            out.add(strip_marks(s))
    return out


def load(path: Path | str = None, ban_path: Path | str = None) -> dict:
    """读库 ✓（文件不在 ⇒ 空库 ✓ **不报错** ✗ —— 空库就是"全走 LLM"✓ 也是一种合法状态 ✓）

    ★顺手**滤掉黑名单**✗★ ✓（用户第 5 条 ✓）：一处过滤 ⇒ 所有调用方都干净 ✓（P106 ✓）
    """
    p = Path(path) if path else DEFAULT
    if not p.is_file():
        return {"__loose__": []}
    c = parse_lines_text(p.read_text(encoding="utf-8"))
    # ★★出库也剥一遍✗★★（`dump` 那头剥了 ✓ 但**手写区是人手改的**✗ ⇒
    #   他可能又写进 `✓✗★` ✓ ⇒ 两头都剥 ✓ 一处不落 ✓ P106 ✓ 见 P136 ✓）
    for k in list(c):
        if k == "__loose__":
            continue
        c[k] = [strip_marks(s) for s in c[k]]
    b = banned(ban_path)
    if not b:
        return c
    out = {}
    for k, lines in c.items():
        if k == "__loose__":
            out[k] = lines
            continue
        keep = [s for s in lines if s not in b]
        if keep:
            out[k] = keep
    return out

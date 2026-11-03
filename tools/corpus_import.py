#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""corpus_import.py -- ★把上游桌宠语料**拉下来并转成我们的台词库**★ ✓（2026-09-30 ✓ 用户第 2 条 ✓）

## 干什么 ✗
  ① 把 `QCYTSN/ds-local-pet`（MIT ✓）的 `assets/dialogue/*.json` **拉一份存本地** ✓
     ⇒ 存进 `personas/dafeiyu-raw/` ✓（★这样"导入"这件事**离线可重放**✗ 不是一次性魔法 ✓）
  ② 转成 `personas/dafeiyu.lines.txt` ✓（**给人接着改**的格式 ✓ `tools/corpus.py` 吃它 ✓）
  ③ 把我自己挑的**Minecraft 化**句子（`docs/大肥鱼语料-来源与原文.md` §4 ✓）并进去 ✓
  ④ 打印**覆盖账**（每个意图类型几条 ✓）＋ **体检**（`corpus.lint` ✓）

## 口径（★这几条是取舍 ✗ 都得写出来 ✓★）
  · **只借"说法"，不搬美术** ✓（上游代码 MIT ✓ 视觉资产另有授权 ✗ 我们只取文字 ✓）
  · 语气四选 ✗：`standard` ⇒ `标准` ✓ ｜ `sharp` ⇒ `傲娇` ✓ ｜ `community` ⇒ `梗` ✓
    ｜ `gentle` ⇒ ★**不要**✗★（用户文档里写明："太软 ⇒ 会变成撒娇陪玩"✗）
  · 上游的"戳我"类句子 ⇒ 我们这儿最接近的是 **`反应/互动`** ✓（MC 里＝玩家右键/打我 ✓）
  · ★`接话`（开放对话）**故意留空**✗★ ⇒ 它按用户第 2 条**走 LLM** ✓
    （上游 `interaction` 那些句子本质是"被戳之后的反应"✓ 不是"接话"✗ 别混 ✓）

## 用法 ✓
  `py tools\\corpus_import.py`（已拉过就不重复拉 ✓）｜ `--refetch`（强制重拉 ✓）
  ★它**不碰世界**✗ 只写 `personas/` 下的两个文件 ✓
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import corpus as C      # noqa: E402

RAW = ROOT / "personas" / "dafeiyu-raw"
OUT = ROOT / "personas" / "dafeiyu.lines.txt"
BASE = "https://raw.githubusercontent.com/QCYTSN/ds-local-pet/main/assets/dialogue/%s.json"

# ★上游文件 ⇒ 我们的 (意图类型, 为什么键)★ ✓（这一张表就是"两套分类怎么对上"的全部 ✓）
MAP = {
    "state":        ("播报", "状态"),     # 累了/烦了/坐不住/高兴/亲近 ✓ 都是**自述状态** ✓
    "routine":      ("播报", "日常"),     # 日常在干什么 ✓
    "inner_voice":  ("闲聊", "心声"),     # 自言自语 ✓（没话找话那一类 ✓）
    "idle":         ("闲聊", "闲话"),     # 发呆 ✓
    "relationship": ("闲聊", "关系"),     # 对玩家的态度 ✓（★不是"接话"✗ 它不依赖玩家先开口 ✓）
    "interaction":  ("反应", "互动"),     # 被戳之后的反应 ✓
    "daily":        ("闲聊", "白天"),
    "late_night":   ("闲聊", "深夜"),
}
TONE = {"standard": "标准", "sharp": "傲娇", "community": "梗"}
TONE_SKIP = {"gentle": "太软 ⇒ 会变成撒娇陪玩 ✗（用户文档 §3 ✓）"}

# ★我们自己挑的 Minecraft 化句子★ ✓（来源：`docs/大肥鱼语料-来源与原文.md` §4 ✓ 逐字抄 ✓）
#   ★它**只用来给"手写区"打底**✗★ —— 文件已经有了就**一个字都不覆盖** ✗（用户改过的必须留住 ✓）
MINE = {
    "播报/干活": [
        "先把活做完，再谈小鱼干。",
        "没有 token 吃要饿死了……骗你的，先把活做完。",
        "我不是吃白饭的大肥鱼，今天也在努力消化上下文。",
        "当前状态：低功耗肥鱼。",
        "警告：大肥鱼 token 储备不足。",
        "上下文还在，体力快没了。",
        "一直站着会变成静态资源，我拒绝。",
        "大肥鱼开始执行桌面巡游。",
    ],
    "播报/干活/傲娇": [
        "看吧，顺起来以后也没那么难。",
        "这波表现，我允许你夸一下。",
        "只是刚好习惯你了，别想太多。",
        "我留下来可不是因为舍不得。",
    ],
    "反应/被戳/傲娇": [
        "再戳我就要收互动税了。",
        "专注不是把自己编译成石头。",
        "这次算你有礼貌。",
        "手法还行，批准继续三秒。",
    ],
    "闲聊/关心": [
        "专注不是把自己编译成石头。",
        "长上下文运行稳定，但用户需要散热。",
        "大肥鱼提醒：人类也有上下文窗口。",
        "熬夜不是高性能模式，只是降频运行。",
        "检测到人类能量低于安全阈值，建议结束会话。",
    ],
    # ★下面三节是**语料库里最容易被漏掉**的 ✗★（上游桌宠没有"干活儿的伙伴"这个身份 ✓）：
    #   上游是**桌宠**：它只管卖萌／被戳／发呆 ✗ 不"干活"、不"求救"、不"交差" ✓
    #   而我们是**一起玩 MC 的第二个玩家** ✓ ⇒ 这三类**必须自己写** ✗
    #   （★这正是用户第 2 条"语料扛 80%"真正的工作量所在 ✗★）
    "邀功": [
        "干完了。别夸，我本来就行。",
        "{job}这点事，我随手就做完了。",
        "收工。我不是吃白饭的大肥鱼。",
        "看吧，顺起来以后也没那么难。",
        "这波表现，我允许你夸一下。",
    ],
    "邀功/干活": [
        "干完了。别夸，我本来就行。",
        "{job}这点事，我随手就做完了。",
        "收工。我不是吃白饭的大肥鱼。",
    ],
    "求助": [
        "报告：{job}卡住了，我需要人搭把手。",
        "这条路我过不去，谁来把我捞出去。",
        "大肥鱼请求支援：我被关在一个小格子里了。",
        "我不装了：这活我做不到——做不到就说做不到。",
        "谁能给我挪一格地方？我想搭个坡。",
    ],
    "求助/干活": [
        "报告：{job}卡住了，我需要人搭把手。",
        "大肥鱼请求支援：我被关在一个小格子里了。",
    ],
    "承诺": [
        "我先去把这趟活做完，回来再跟你说话。",
        "给我一会儿，我把手头这个收尾。",
        "接下来我去{job}，不是拖延。",
        "「马上就好」之后我会真动手——这是我的铁律。",
    ],
}
HAND_MARK = ("# ==== 手写区（★corpus_import **永不覆盖** ✓ 想加句子／改口气就写这里 ✓★）====")
HEADER = """# ★台词库：大肥鱼（鲸鱼娘 ✓ 社区二创 ✓ 非官方 ✗）★
#
# 改这个文件**不用动代码** ✓ 一行一句 ✓ `##` 分节 ✓ `#` 注释 ✓
# ★文件分两区 ✗★：上面是**自动区**（脚本每次覆盖 ✓ 别手改 ✗）；
#   底下的**手写区**（@@AUTO@@ 的那个线以下 ✓）**永远不会被脚本动** ✗ ⇒ 想加句子写那里 ✓
# 键的写法（＝查找顺序里的某一层 ✓ 越具体越先命中 ✓）：
#     <类型>/<为什么>/<语气>/<关系>  →  <类型>/<为什么>/<语气>  →  <类型>/<为什么>
#     →  <类型>  →  *（★但 `接话` 不吃 `*` ✗ —— 开放对话要留给模型 ✓ P128 ✓）
# 类型只能是：@@KINDS@@
# 语气：标准／傲娇／梗 ✓（上游 `gentle` **故意不要** ✗：太软 ⇒ 会变撒娇陪玩 ✓）
# 句子里的 `{槽位}` 会被填**真值** ✓ 填不上 ⇒ 整条不用 ✗（★绝不编数字 ✗★）
#
# 来源 ✓：QCYTSN/ds-local-pet（MIT ✓ 桌宠 ✓ 470 条本地语料 ✓ 四种语气 ✓）
#         https://raw.githubusercontent.com/QCYTSN/ds-local-pet/main/assets/dialogue/*.json
#         原文与授权说明见 `docs/大肥鱼语料-来源与原文.md` ✓
# 生成 ✓：`py tools\\corpus_import.py`（可重放 ✓ 手改的部分请写在本文件**末尾追加节**里 ✓）
#
# ★`接话` 这一节**故意是空的**✗★ ⇒ 开放对话按用户第 2 条**走 LLM** ✓（80／20 的那个 20 ✓）
#
"""


def fetch(name: str, refetch: bool = False) -> dict | None:
    """拉一个上游文件 ✓（已经拉过 ⇒ 直接用本地的 ✓ 导入这件事要**可重放** ✗）"""
    RAW.mkdir(parents=True, exist_ok=True)
    p = RAW / ("%s.json" % name)
    if refetch or not p.is_file():
        url = BASE % name
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                body = r.read().decode("utf-8")
        except Exception as e:
            print("  ✗ 拉不到 %s：%s" % (name, e))
            return None
        p.write_text(body, encoding="utf-8")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print("  ✗ %s 解析不了：%s" % (name, e))
        return None


def walk(node, depth: int = 0) -> list:
    """★把上游 JSON 拆成 `[(情形名, 语气, [句子])]`✗★ ✓

    ★为什么要"走"而不是写死结构✗★：8 个文件**结构不一定一样** ✗
      （实测 `state.json` 是 `{情形: {语气: [句]}}` ✓ 别的可能是 `{语气: [句]}` 或直接一个数组 ✓）
    ⇒ 口径 ✓：**是"语气名"的那一层剥掉** ✗ 其余都当"情形名" ✓ 认不出的层 ⇒ 情形名留空 ✓
    """
    out = []
    if isinstance(node, list):
        out.append(("", "", [str(x) for x in node if isinstance(x, str)]))
    elif isinstance(node, dict):
        for k, v in node.items():
            if k in TONE or k in TONE_SKIP:
                if isinstance(v, list):
                    out.append(("", k, [str(x) for x in v if isinstance(x, str)]))
                else:
                    out += walk(v, depth + 1)
                continue
            if isinstance(v, list):
                out.append((str(k), "", [str(x) for x in v if isinstance(x, str)]))
            elif isinstance(v, dict):
                for sub in walk(v, depth + 1):
                    sit, tone, lines = sub
                    out.append(("%s-%s" % (k, sit) if sit else str(k), tone, lines))
    return out


def hand_zone(text: str) -> str | None:
    """★取出手写区（那条线**以下**的全部内容 ✓）★ ✗（没有 ⇒ `None` ✓）"""
    return text.split(HAND_MARK, 1)[1] if HAND_MARK in (text or "") else None


def compose(head: str, corpus: dict, hand_tail: str, kept: str = "") -> str:
    """★拼出整份文件 ✓★：头 ＋ **自动区**（每次覆盖 ✓）＋ **手写区**（**永不覆盖** ✗）

    ★抽成函数是为了**能离线判据**✗★ ✓（`corpus_test.py` K6 ✓）——
      "手改会不会被冲掉"这件事**必须能被跑出来** ✗ 不能靠"我觉得它保留了" ✗
    ★★`kept` 那句说明**必须写在线的上面**✗★★（实测 ✓ 第一版写在线下面 ⇒
      它**进了手写区** ✗ ⇒ 每跑一次**多一句** ✗ ⇒ 用户的那一区慢慢被脚本的废话占满 ✗
      —— ★K6 就是把这个抓出来的 ✓★）
    """
    note = kept if (kept or "").lstrip().startswith("#") else ("# " + (kept or ""))
    return (head
            + "# ==== 自动区（★本文件由 `py tools\\corpus_import.py` 生成 ✓ "
              "手改请写在下面的手写区 ✗★）====\n\n"
            + C.dump_lines_text(corpus)
            + "\n\n" + note + "\n" + HAND_MARK + hand_tail)


def main(argv) -> int:
    refetch = "--refetch" in argv
    corpus: dict = {}
    print("== 拉上游语料（MIT ✓ 只取文字 ✓）==")
    for name in MAP:
        data = fetch(name, refetch)
        if data is None:
            continue
        kind, why = MAP[name]
        n0 = 0
        for (sit, tone, lines) in walk(data):
            if tone in TONE_SKIP:
                n0 += len(lines)
                continue
            mood = TONE.get(tone, "")
            parts = [kind, why] + ([sit] if sit else []) + ([mood] if mood else [])
            key = "/".join(p for p in parts if p)
            corpus.setdefault(key, [])
            for s in lines:
                if s.strip() and s.strip() not in corpus[key]:
                    corpus[key].append(s.strip())
        print("  %-12s ⇒ %-12s %s（跳过 gentle %d 条 ✓）"
              % (name, "%s/%s" % (kind, why), "OK ✓", n0))
    print("== 并进我们自己的 Minecraft 化句子 ==")
    for k, lines in MINE.items():
        corpus.setdefault(k, [])
        for s in lines:
            if s not in corpus[k]:
                corpus[k].append(s)
    # ★★两条区：自动区（每次覆盖 ✓）／手写区（**永不覆盖** ✓）★★ ✗
    #   为什么 ✗：用户说这一层要"**可编辑的台词库**"✗ ⇒ 脚本一跑就把人的手改冲掉 ✗
    #     ＝ 这份库**根本不能被编辑** ✗（P129 同族：工具把"只增不减"的东西覆盖了 ✓）
    #   口径 ✓：**手写区原样搬过来**（文件存在就搬 ✗ 不存在就用 `MINE` 打底 ✓）
    want = "自动区（`py tools\\corpus_import.py` 每次覆盖 ✓ 别手改 ✗）"
    head = HEADER.replace("@@KINDS@@", "／".join(C.KINDS)) \
                 .replace("@@AUTO@@", want) + "\n"
    if OUT.is_file() and hand_zone(OUT.read_text(encoding="utf-8")) is not None:
        tail = hand_zone(OUT.read_text(encoding="utf-8"))
        kept = "（原有手写区**原样保留** ✓）"
    else:
        tail = "\n\n" + C.dump_lines_text(MINE, "手写区（我们自己写的句子 ✓ 想改就改 ✓）")
        kept = "（第一次生成 ⇒ 用 `MINE` 打底 ✓）"
    body = compose(head, corpus, tail, kept)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(body, encoding="utf-8")
    # ★报账要按**盘上那份文件**算✗★（不是按我内存里那个 dict ✓ —— 手写区也得算进去 ✓）
    on_disk = C.parse_lines_text(OUT.read_text(encoding="utf-8"))
    cov = C.coverage(on_disk)
    bad = C.lint(on_disk)
    print("== 写盘 ✓ %s ==" % OUT.name)
    print("  共 %d 条 ｜ 按类型：%s" % (cov["total"],
                                      "  ".join("%s=%d" % (k, v) for k, v in cov["n"].items())))
    print("  ★敞开说的那些类型**都有**✓★ ｜ 空的（允许 ✗）：%s" % (cov["empty"] or "无 ✓"))
    print("  体检：%s" % ("干净 ✓" if not bad else "%d 条问题 ✗" % len(bad)))
    for b in bad[:12]:
        print("    - %s" % b[:100])
    secs = [k for k in on_disk if k != "__loose__"]
    print("  节数 %d ｜ 类型数 %d" % (len(secs), len(set(C.kind_of(k) for k in secs))))
    print("  手写区 %s" % kept)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""debt_count.py -- ★欠账计数显式化 ＋ 入口文档自动再生成✗★（P3 第一件 ✓ 2026-10-02 ✓）

WHY ✓（用户 2026-10-02 的 P3 原话要点 ✓）：
  ★"欠账计数"应该有地方**挂着数字** ✗ 直到清零 ✗★ ——
  ★否则"还欠什么"永远只能凭记忆 ✗ 而这正是本项目最贵的一种浪费✗★
做法 ✓：
  ① ★从 `docs/当前阶段-状态与交接.md` 里**解析** §79.14 的欠账表✗★（★唯一真源 ✓ 不许另抄一份✗★）
  ② ★在入口文档里**自动重写**两块被标记夹住的内容✗★（`<!-- DEBT:BEGIN -->` … `<!-- DEBT:END -->` ✓）
  ③ ★`--check` ⇒ 只比对 ✗ 不一致就**红**✗★（★这也让"文档过期"变成闸门里的一项 ✓★）
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STA = ROOT / "docs" / "当前阶段-状态与交接.md"
DOCS = [ROOT / "docs" / "00-快速上手与索引.md", ROOT / "docs" / "交接提示词.md"]
BEGIN = "<!-- DEBT:BEGIN -->"
END = "<!-- DEBT:END -->"
# ★★2026-11-02 守卫（审计 P0-1 ✗ D7 闸门 C8 用的就是它）✗★★
#   ★事故✗★：`docs/交接提示词.md` 的 **271 行正文**在提交 cc875dc 里被清空 ✗
#     只剩这个自动生成的 DEBT 块（17 行）✗ 而 118 项离线闸门照样全绿 ✗★
#   ★口径✗★：DEBT 块是入口文档里**唯一**允许脚本自动改的部分 ⇒
#     ① 只替换 `<!-- DEBT:BEGIN -->` 与 `<!-- DEBT:END -->` **之间** ✗
#        标记缺失／重复 ⇒ **拒写并说清**（旧版会往文件尾追加 ✗ 那正是把空壳洗成"看起来正常"的路）✗★
#     ② 块外**正文非空行数**必须有下限 ✗ 低于下限 ⇒ 拒写（防止把块写进被清空的正文）✓
#     ③ 替换前后块外正文必须**逐字节相同**（只许块变 ✗ 别的一概不许动）✓
MIN_BODY = {"00-快速上手与索引.md": 60, "交接提示词.md": 40}

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ★★圈号表**只留一份**✗★★（2026-10-03 检修 ✓）：
#   先前 `MARK` 的字符类与 `debt_fresh_test` 里的 `_CIRC` **各存一份** ⇒
#   我补了这边忘了那边 ⇒ 加 `㉛` 时那边 `.index()` 直接 `ValueError`
#   （★与 §79.71「账本与账本对不齐」同族 ✗ 所以只留一份✓★）
MARKS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚㉛㉜㉝㉞㉟㊱㊲㊳㊴㊵㊶㊷㊸㊹㊺㊻㊼㊽㊾㊿"   # ★★2026-10-03 检修：㉟ 已经用到底 ✗ 扩到 ㊿★★
#   （★扩表只改**这一处** ✗ 因为 MARK 与测试都由它生成 ✓ 见 §79.81✓★）
MARK = re.compile(r"^\| ([" + MARKS + r"]) \| (.*) \|\s*$")
# ★★2026-10-03 修✗★★：★这个字符类原来**只写到 ⑮**✗★ ⇒ ★`⑯⑰⑱⑲` 那四行**根本不被看见**✗★
#   （★现象✗★：文档里明明有 ⑯~⑲ ✗ 而"总条数"永远停在 15 ✓✓ —— ★**又是我的装置**✗ ✓★）
# ★形状坏的行（内格数不对）—— 见下面 parse() 里的形状守卫
SHAPE_BAD = []

CLOSED = ("已销", "已关闭", "已结",
          # ★2026-10-03 补✗★：★"已定性 ✗ 不做" **也是收口**✗★（★一个决定就是一次关闭 ✓★）
          #   ★例子✗★：★⑤ `jump_run` 判定"不做" ✗ 它不该永远挂在"还欠"里✗★ ✓
          "已定性", "不做")
WAIT_USER = ("等用户",)
WAIT_RESTART = ("等重启",)
DOING = ("进行中", "已开", "并入")


def parse():
    """⇒ [(编号, 最后一列的字, 是否已销)] ✓

    ★★只解析 §79.14 那张表✗★★（2026-10-02 当场吃到 ✓）：
      ★第一版按整份文档找 `| ① |`… ⇒ 命中 **53** 行✗★ —— ★因为这份文档里**很多张表**
      都用同样的圈号 ✗★（★与 **P175** 同一个坑 ✗ 只是这次是**解析**而不是**替换**✗ ✓）
      ⇒ ★口径✗★：★先定位 `### 79.14` ✗ 再读它下面那张表 ✗ 遇到第一个非 `|` 行就停✗★ ✓
    """
    lines = STA.read_text(encoding="utf-8").split("\n")
    # ★★2026-10-03 再换口径✗★★：★按小节标题找会在"标题出现两次"时数错✗★
    #   （★实测：只数到 15 行 ✗ 而 `⑨`~`⑲` 明明都在文档里✓★）
    #   ⇒ ★改成**内容锚✗**：★`| ⑨ | ★key` 这一行是**欠账表独有**的✗★
    #     ⇒ ★从它往上、往下各扫**连续的行**✗ ✗ 直到断掉为止 ✓★
    anchor = None
    for i, ln in enumerate(lines):
        if ln.startswith("| ⑨ |") and "★key" in ln:
            anchor = i
            break
    if anchor is None:
        return []
    top = anchor
    while top - 1 >= 0 and MARK.match(lines[top - 1]):
        top -= 1
    bot = anchor
    while bot + 1 < len(lines) and MARK.match(lines[bot + 1]):
        bot += 1
    rows = []
    for ln in lines[top:bot + 1]:
        m = MARK.match(ln)
        if not m:
            continue
        cols = [c.strip() for c in m.group(2).split("|")]
        # ★★形状守卫✗★★（2026-10-03 检修 ✓）：★内格应当正好 3 个（文本／类别／状态）✗
        #   而 `safe_edit.replace_unique` **只换前缀** ⇒ 会留下旧尾巴 ⇒ 内格变 4 个 ✗
        #   ⇒ 那时读到的「状态」是**旧尾巴** ⇒ 正文写着已销、账面却算未销（我踩过三次）✗
        #   ⇒ 口径：★形状坏了就**大声**记下来 ✗ 并且**强制算未销**✗★
        #     （★宁可多算欠 ✗ 不许把坏行当成收口✓★）
        if len(cols) != 3:
            SHAPE_BAD.append((m.group(1), len(cols)))
            rows.append((m.group(1),
                         '★形状坏（内格 %d 个 ✗ 应当 3）✗★' % len(cols),
                         '★未销✗★'))
            continue
        last = cols[-1] if cols else ""
        rows.append((m.group(1), last, any(k in last for k in CLOSED)))
    return rows


def summary(rows):
    total = len(rows)
    closed = [r for r in rows if r[2]]
    wait_u = [r for r in rows if any(k in r[1] for k in WAIT_USER)]
    wait_r = [r for r in rows if any(k in r[1] for k in WAIT_RESTART)]
    doing = [r for r in rows if any(k in r[1] for k in DOING) and not r[2]]
    return {"total": total, "closed": len(closed), "wait_user": len(wait_u),
            "wait_restart": len(wait_r), "doing": len(doing),
            "open": total - len(closed)}


def block(rows):
    s = summary(rows)
    open_ids = "".join(r[0] for r in rows if not r[2])
    return (BEGIN + "\n"
            + "★欠账总账（★由 `py tools/debt_count.py --write` 自动生成 ✗ 别手改✗★）★\n\n"
            + "| 项 | 数 |\n|---|---|\n"
            + "| 欠账表总条数 | **%d** |\n" % s["total"]
            + "| ★已销✗★ | **%d** |\n" % s["closed"]
            + "| ★还欠（未销）✗★ | ★**%d**✗★ |\n" % s["open"]
            + "| 其中：★等用户✗★（console/拍板 ✓） | %d |\n" % s["wait_user"]
            + "| 其中：★等一次重启✗★ | %d |\n" % s["wait_restart"]
            + "| 其中：进行中 | %d |\n" % s["doing"]
            + "\n★未销的编号✗★：`%s`\n" % (open_ids or "（空 ✓ 全部销完 ✓）")
            + "★唯一真源✗★：`docs/当前阶段-状态与交接.md` 的 §79.14 ✓（本节由脚本生成 ✓）\n"
            + END)


def _split_block(text):
    """★把 DEBT 块切成 (块外前半, 块外后半)；只认**唯一**标记对✗★

    ⇒ (head, tail, err)：err 非空 ⇒ 这份文档**不许自动改**（标记缺失/重复/顺序反了）
    """
    nb, ne = text.count(BEGIN), text.count(END)
    if nb != 1 or ne != 1:
        return None, None, "DEBT 标记对不唯一（BEGIN=%d ✗ END=%d ✗ 必须各 1 个）" % (nb, ne)
    i, j = text.index(BEGIN), text.index(END)
    if j < i:
        return None, None, "DEBT:END 出现在 BEGIN 之前"
    return text[:i], text[j + len(END):], None


def inspect(path):
    """★守卫：这份入口文档能不能被自动刷新✗★ ⇒ (text, outside, errs)

    errs 非空 ⇒ 拒写。三道：标记唯一／块外正文行数下限／块外必须有一级标题。
    """
    if not path.is_file():
        return None, None, ["文件不在"]
    text = path.read_text(encoding="utf-8")
    head, tail, err = _split_block(text)
    errs = []
    if err:
        errs.append(err)
        outside = text
    else:
        outside = head + tail
    nonempty = [ln for ln in outside.splitlines() if ln.strip()]
    need = MIN_BODY.get(path.name, 30)
    if len(nonempty) < need:
        errs.append("块外正文只有 %d 个非空行 < 下限 %d ⇒ ★拒绝把 DEBT 块写进空壳/残缺的入口文档✗★"
                    % (len(nonempty), need))
    if not any(ln.startswith("# ") for ln in outside.splitlines()):
        errs.append("块外正文没有一级标题（`# `）⇒ 看起来正文已被删空")
    return text, outside, errs


def rewrite(rows, check=False):
    """⇒ (changed, errors)

    ★守卫口径✗★：errors 非空 ⇒ **一个文件都不写**（先修正文/标记，再谈刷新）✓
    """
    body = block(rows)
    changed, errors = [], []
    for p in DOCS:
        text, outside, errs = inspect(p)
        if errs:
            errors.extend("%s: %s" % (p.name, e) for e in errs)
            continue
        new = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END),
                     body.replace("\\", "\\\\"), text, flags=re.S)
        head2, tail2, err2 = _split_block(new)
        if err2 or (head2 + tail2) != outside:
            errors.append("%s: 替换后块外正文变了（只许改块）⇒ ★拒绝写✗★" % p.name)
            continue
        if new != text:
            changed.append(p.name)
            if not check:
                p.write_bytes(new.encode("utf-8"))
    return changed, errors


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "--report"
    rows = parse()
    s = summary(rows)
    print("★欠账表✗★（§79.14 ✓ 共 %d 条）：★已销 %d ✗ 还欠 %d✗★"
          % (s["total"], s["closed"], s["open"]))
    for (i, last, closed) in rows:
        print("  %s %s %s" % (i, "✓" if closed else "★", last[:56]))
    if mode == "--write":
        # ★★2026-10-03 检修加的源头闸✗★★：★形状坏了 ⇒ **拒绝刷新入口文档**✗★ ✓
        #   为什么：`safe_edit.replace_unique` **只换前缀** ⇒ 改"状态列"时会留下旧尾巴 ⇒
        #   内格变 4 个 ⇒ 状态读到旧尾巴（正文写着已销 ✗ 账面还算未销）✓
        #   我在一天里踩了**四次**（㉖ ㉔ ㉚ ㉜）⇒ 与其每次手修行 ✗ 不如**在这里拒收**✓★
        #   （★口径✗★：★坏行不许被"刷新"掩盖掉 ✗ 先把行修好 ✓★）
        if SHAPE_BAD:
            print("★★拒绝刷新✗★★：欠账表里有 **%d** 行**形状坏了**（内格不是 3 个）✗"
                  % len(SHAPE_BAD))
            for (i, n) in SHAPE_BAD:
                print("   %s ⇒ 内格 %d 个（应当 3）" % (i, n))
            print("★先把那些行**整行重写**（★别再在状态列上做前缀替换✗★）✗ 再来 --write ✓★")
            sys.exit(2)
        # ★★2026-11-02 守卫（P0-1）✗★★：块外正文不合格 ⇒ 拒写（见 inspect()）
        changed, errors = rewrite(rows)
        if errors:
            print("★★拒绝刷新✗★★：DEBT 块守卫拦下 **%d** 条 ⇒ 先修正文/标记，再 --write：" % len(errors))
            for e in errors:
                print("   " + e)
            sys.exit(2)
        print("★重写入口文档✗★：%s" % ("／".join(changed) or "（无变化 ✓）"))
    elif mode == "--check":
        changed, errors = rewrite(rows, check=True)
        if errors:
            print("★★守卫不过✗★★（★这不是「欠账块过期」 ✗ 是入口文档**正文**不合格/标记坏了✗★）：")
            for e in errors:
                print("   " + e)
            sys.exit(1)
        if changed:
            print("★过期✗★（需要 `--write`）：%s" % ", ".join(changed))
            sys.exit(1)
        print("★入口文档的欠账块是新的 ✓★")
    else:
        print()
        print(block(rows))

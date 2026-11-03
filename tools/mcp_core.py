#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mcp_core.py —— ★中间层的**原语**★（MCP 工具层人人都在用的那一小撮 ✓）

★来历✗★：v2.19 从 `tools/mc_mcp.py` **抽出来**的 ✓（那一份约 2800 行 ✗ 而且
**2026-09-23 被手工文本替换毁过一次** ✗ 见 `docs/错题本.md` **P91** ✓）。

★为什么第一刀是它✗★：用 `ast` 把 `mc_mcp.py` 的耦合量了一遍 ✓ —— 枢纽是
`cut`（**39** 个函数用 ✓）／`dsh`（26）／`errlog`（11）／`_pos_now`（11）／`ok_of`（8）✓
⇒ 先把它们抽出来，后面三块（感知／走路／动作）各自 `import` 就**不会循环依赖** ✓

★★纪律：这一刀**一个字都没改**✗★★
  · 函数体／常量／注释**逐字照搬** ✓ —— 只有"搬家" ✓ 没有"顺手改" ✓
  · 工具名与说明是**大脑直接读的那些字** ✗ ⇒ **一个字都不许动** ✓（P91 ✓）
  · 判据 ✓：`py tools/mcp_surface.py --diff tmp/surface_before.json`
    ⇒ 工具面必须**逐字节相同** ✓（少一件／丢一个参数／改一个字**都会报红** ✗）
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(r"C:\Users\Administrator\Documents\deepseek harness\mc-agent-bridge")
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "tools"))

BOT = "Bot"
PLAYER = "Au_Sn"
LOG = ROOT / "logs" / "mc_mcp.jsonl"
_CH = None


def ch():
    global _CH
    if _CH is None:
        from channel import Channel
        _CH = Channel("cmd0", verbose=False)
    return _CH


def log(rec: dict) -> None:
    try:
        rec = dict(rec)
        rec.setdefault("at", time.strftime("%Y-%m-%d %H:%M:%S"))
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        # ★★§79.402 fail-safe✗★★：★**记日志失败**不能把主流程弄死 ✗ 这一处**故意**吞✗★ ✓
        pass


def errlog(*a) -> None:
    try:
        with (ROOT / "logs" / "mc_mcp.err").open("a", encoding="utf-8", newline="\n") as f:
            f.write(" ".join(str(x) for x in a) + "\n")
    except Exception:
        # ★★§79.402 fail-safe✗★★：★**连记录都失败**时无处可记 ✗ 只能吞（★但它本身不改数据✗★）✗★
        pass


# ★★2026-10-18（★§79.289 ✗ 世界侧那条通道✗★）✗★★：★主路（★`ch().cmd(…)`✗★）在这台机器上
#   **不通** ✗ 而且**异常被吞成空串**✗★ ⇒ ★世界侧的一切读都拿到 `""`✗★ ✓
# ★而**网关 ＋ `cmd0`** 是通的✗★（★实测 `dshver version=2.19.0 … success:true` ✗ **0.5 秒**✗★）✗★ ✓
# ★⇒ 加一条**后备**✗★：★主路**拿到非空**就照旧 ✗ 拿到**空**才走网关✗★ ✓
#   ★（★主路不改 ✗ 签名不改 ✗ 那些把 `M.dsh` 换成桩的判据**照样能用**✓★）✗★ ✓
# ★协议（★从 `cc-tweaked/agent_bridge.lua` 读出来的✗★）✗★：★`cmd` 是**动词** ✗ 命令放 `args.text`✗★ ✓
GW_BASE = "http://127.0.0.1:8765"
GW_WHO = "cmd0"


def _gw_state():
    import json as _j
    import urllib.request as _u
    with _u.urlopen(GW_BASE + "/api/state", timeout=8) as r:
        return ((_j.loads(r.read().decode("utf-8", "replace")).get("states") or {})
                .get(GW_WHO) or {})


def _gw_dsh(text: str, t: float = 60.0) -> str:
    """★走网关发一条 ✗ 返回模组的回执文本（★多行就用换行接✗★）"""
    import json as _j
    import time as _t
    import urllib.request as _u
    try:
        # ★★§79.289 续✗★★：★主路一直带 `execute as Bot at Bot run` 包装✗ 而我第一版后备**漏了**✗★
        #   ⇒ ★模组那些命令（★dshpos ✗ dshmap✗★）在没包装时**失败**✗★ ⇒ ★补上同一个包装✗★ ✓
        # ★★§79.289 续✗★★：★实测 **raw** 才成（★A.cmd 自己会包`execute as … run`✗★）✗★ ⇒ 原样发✗★ ✓
        body = _j.dumps({"who": GW_WHO, "cmd": "cmd", "args": {"text": text}}).encode("utf-8")
        req = _u.Request(GW_BASE + "/api/command", data=body,
                         headers={"Content-Type": "application/json"})
        with _u.urlopen(req, timeout=8) as r:
            qid = (_j.loads(r.read().decode("utf-8", "replace")).get("queued") or {}).get("id")
        t0 = _t.time()
        while _t.time() - t0 < t:
            st = _gw_state()
            if st.get("id") == qid and st.get("result") is not None:
                res = st.get("result")
                if isinstance(res, dict) and isinstance(res.get("lines"), list):
                    return "\n".join(str(x) for x in res["lines"]).strip()
                return str(res).strip()
            _t.sleep(0.4)
        return ""
    except Exception:
        return ""



# ══ ★★§79.431✗★★：★"★脚格★"换算 ✗ 全仓只此一份✗★★
#   ★为什么✗★：★站在**不满一格高**的方块上时（★`dirt_path` 0.9375 ✗ 半砖 0.5 ✗ 灵魂沙✗★）
#     ★`dshdigest` 的 `pos.y` 是**小数**（★如 70.94✗★）✗★
#     ★⇒ ★`int(y)`（★＝floor✗★）读到的是**那个方块自己** ✗ **不是人站的那一格**✗★
#     ★⇒ ★C1「脚格是空气」那种判据 4 条全红 ✗ 而且**规划起点也是错的**✗★ ✓
#   ★正确✗★：★`cell_y = ceil(feet_y − 1e-9)`**✗★
#     ★71.0 ⇒ 71 ✓ ／ 70.9375 ⇒ 71 ✓ ／ 70.5 ⇒ 71 ✓（★都落到"人站着的那一格"✗★）✗★ ✓
def cell_of(fx, fy, fz):
    """★世界坐标 ⇒ 格子（★脚格规则**唯一实现**✗★）✗★"""
    import math as _m
    return (int(_m.floor(float(fx))), int(_m.ceil(float(fy) - 1e-9)), int(_m.floor(float(fz))))


def cell_from_pos(o):
    """★从 `dshdigest` 回包取脚格 ✗ 取不到 ⇒ None（★不静默给个 0,0,0✗★）✗★"""
    import re as _r
    m = _r.search(r"pos=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)", o or "")
    if not m:
        return None
    return cell_of(m.group(1), m.group(2), m.group(3))


# ══ ★★§79.438（★task-8 ✗ 2026-10-27✗★）✗★★：★"★到没到★"判定 ✗ 全仓只此一份✗★★
#   ★合并前是**两套**✗★：
#     · `exec3d`：★`bool(end) and tuple(end) == goal`（★`end` 来自模组 `do_done at=` 的**整数格**
#       或 `cell_of` 的整数格✗★）
#     · `mcp_walk`：★x／z **落格**（floor）＋ y **取整**（round）✗ 两个分量都成立才算到✗★
#   ★正确口径（★§79.421✗★）✗★：★模组 `do_done at=` 是**权威** ✗ 距离只是**辅助**✗★
#     ⇒ ★`arrived_at` 只判"★格对不对★" ✗ **绝不看距离**✗★ ✓（★P32／P104 那条错题✗★）
#   ★为什么一套能吃两种输入✗★：★传**整数格子**时 `floor(int)`／`round(int)` 恒等于原值
#     ⇒ ★退化成**逐元相等**（★`exec3d` 的语义**一字不变**✗★）✗
#     传**浮点世界坐标**时就是 `mcp_walk` 的旧规则（★逐字不变✗★）★ ✓
def arrive_flags(pos, target) -> tuple:
    """★到没到的**两个分量**（★唯一分解✗★）⇒ `(in_cell, same_lv)`（★都是 bool✗★）

    ★`pos` 空／None ⇒ `(False, False)`（★判不了就说判不了 ✗ 不猜"到了"✗★）✗★
    """
    import math as _m
    if not pos or len(pos) < 3 or len(target) < 3:
        return (False, False)
    in_cell = (int(_m.floor(float(pos[0]))) == int(target[0])) and \
              (int(_m.floor(float(pos[2]))) == int(target[2]))
    same_lv = abs(int(round(float(pos[1]))) - int(target[1])) <= 0
    return (in_cell, same_lv)


def arrived_at(pos, target) -> bool:
    """★"★到没到★"的**唯一判定**✗★ ＝ `in_cell and same_lv`

    ★★不许**只看距离**✗★★（★P32／P104：距离 ≤1.6 但站到旁边那一格／低一层 ⇒ **不算到**✗★）✓
    """
    in_cell, same_lv = arrive_flags(pos, target)
    return bool(in_cell and same_lv)

def dsh(text: str, t: float = 60.0) -> str:
    """发一条模组指令 ✓（一律 `execute as Bot at Bot` ✓ 模组里动作都作用在执行者身上 ✓ 见 P14 ✓）
    ★★主路拿不到 ⇒ **走网关**（★§79.289✗★）✗ 返回的是模组的**回执文本**✗★★ ✓
    """
    # ★★2.53.0（§79.513）✗★★ **直连优先**：模组自己开 8766 口 ⇒ 不经过 CC 计算机 ✓
    #   ★为什么✗★：★CC 计算机是又一个会坏的中间件 —— 一次 fill 填掉它 ⇒ 整套系统断线 ✓
    try:
        import direct as _D
        r0 = _D.post(text, timeout=min(t, 45.0))
        if r0 and r0 not in ("0", "1", "-1") and not r0.startswith("ERR:"):
            return r0
    except Exception as e0:            # ★不许静默✗★
        errlog("dsh 直连(8766)失败，回退：%r ／ cmd=%r" % (e0, text[:60]))
    try:
        r = ch().cmd("execute as %s at %s run %s" % (BOT, BOT, text), timeout=t, allow_str=True)
        out = (r.text() or "").strip()
        # ★★§79.289 续✗★★：★主路有时"成功"但只回一个**返回码行**（`0`／`1`）✗★
        #   ⇒ ★那**不是正文**（★ok_of 要 dsh… 前缀 ✓ 光 "1" 本来就判不过✓★）✗★ ⇒
        #   ★★退化结果也算"没拿到" ✗ 走网关后备✗★★ ✓
        if out and out not in ("0", "1", "-1"):
            return out
    except Exception as e:          # ★★§79.403✗★ 走网关后备 ✗ 但**为什么失败要留痕**✗★
        errlog("dsh 直连失败，走网关后备：%r ／ cmd=%r" % (e, text[:60]))
    return _gw_dsh(text, t)


def ok_of(txt: str, cmd: str) -> bool:
    """回执算不算成功 ✓（不同指令的回执形状不一样 ✓ 所以按指令名分别判 ✓）"""
    if not txt:
        return False
    t = txt.strip()
    if t.startswith("ERR:"):
        return False
    if cmd == "dshbox":
        return ("not a block entity" not in t) and ("too far" not in t)
    return t.startswith("dsh") or t.startswith("收成作业")


def kv(txt: str) -> dict:
    return dict(re.findall(r"(\w+)=(\S+)", txt or ""))


def esc(s: str) -> str:
    """非 ASCII 一律转义成 `\\uXXXX` ✓（CC 通道只吃 ASCII ✓ 模组那头自己解回来 ✓ 见 P13 ✓）"""
    return "".join(c if 32 <= ord(c) < 127 else "\\u%04x" % ord(c) for c in (s or "")).replace('"', "'")


def looks_mangled(txt: str) -> bool:
    return "\ufffd" in (txt or "")


def cut(s: str, n: int = 1600) -> str:
    s = s or ""
    return s if len(s) <= n else s[:n] + "…（截断 ✓ 原文 %d 字 ✓）" % len(s)


def ascii_or_note(txt: str, how_to_check: str = "") -> str:
    if txt and any(ord(c) > 127 for c in txt):
        return txt + "  ｜（含非 ASCII ✓ 若显示成 ? 请%s ✓）" % (how_to_check or "用 dshver 核对版本")
    return txt


def _inv_items():
    st = dsh("dshdigest 1", 40.0) or ""
    m = re.search(r"items=(\d+)", st)
    return int(m.group(1)) if m else None


def _pos_now():
    txt = dsh("dshdigest 1", 40.0) or ""
    m = re.search(r"pos=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)", txt)
    return (float(m.group(1)), float(m.group(2)), float(m.group(3))) if m else None


# ─────────────────────────────────────────────────────────────────────────────
# ★★v2.19 第三/四刀：共享的**可变状态**与**运行时代理**★★ ✗
# ★为什么它们必须在 core（而不是 geo/walk）✗★：`ast` 量出来**两边都要** ✗
#   · `_MISSION`   ：感知要（看图 ✓）走路要（规划 ✓）—— **同一张图**不许各存一份 ✗
#   · `BLOCKED*`   ：障碍记忆 —— 感知的 `t_check_path` 记 ✓ 走路的 `t_walk_route` 绕 ✓
#   · `MOD_CLIMB_UP`：执行者**能跳一级整方块**（墙 1.5 跳不上 ✓ 第 34 轮用户纠正过我 ✓）
#   ★同名对象**只能有一份**✗★：测试是就地改（`.clear()/.update()/.add()` ✓）
#     ⇒ 放 core ＝ 谁 import 都是**那一个对象** ✓ 搬走之后桩照样打得中 ✓
_MISSION: dict = {"box": None, "map": None, "at": 0.0, "builds": 0}

# ★★"道中障碍物"：本会话里**实地探到**的挡路格★ ✗（2026-09-23 ✓ 用户点的方向 ✓）
#   来源 ✓：`scan_route` 独立探出来的 ✓（**不是**按方块名猜的 ✗）
#   用途 ✓：之后所有规划都**绕开**它们 ✓（`Planner(blocked=…)` ✓）
# ★★第 31 轮补上**层**这一维★★ ✗（实测抓到的漏子 ✓）：
#   现象 ✗：探路时在**假人那一层**（`LEVEL` ✓）探到一堵墙 ✓ 记进 `BLOCKED` ✓
#     ⇒ 而"**站到那堵墙头上去**"（`y+1` 那一层 ✓）**也被这条记忆挡住** ✗
#       （`BLOCKED` 只按 `(x,z)` 记 ✗ 不看层 ✗）
#     ⇒ 实测 ✓：`verdict_levels` 的 V5 明明几何上站得住 ✓ 却报"不在连通区域"✗
#   ⇒ 口径 ✓：记忆要**带层** ✗ —— "**我在 `L` 这一层走不过去**"✓ 不等于
#     "**那一柱任何一层都过不去**"✗（与本轮主发现同一族：**少了一维** ✗ P106／P113 同族 ✓）
BLOCKED: set = set()
BLOCKED_WHY: dict = {}
BLOCKED_LV: dict = {}          # (x,z) -> 探到它的**那一层**（假人当时的脚层 ✓）

# ★★执行者的真实能力：**能跳一级（整方块 ✓）—— 墙（1.5）跳不上（真人也不行 ✓）**★★ ✗
#   （第 33 轮我写成"**模组不会跳**"✗ —— 第 34 轮**用户指出 ✗ 源码确认我错了** ✗
#    真因 ✓：我**只拿 `mcwfences:*_wall` 当试验对象** ✗ 而它高 **1.5** ✗
#      ⇒ 跳跃上限 ≈1.25 ⇒ **谁跳都上不去** ✓ ⇒ 我把"墙跳不上去"错推成"模组不会跳" ✗）
#   源码证据 ✓：`DshBridgeMod.java` 3687 行 `wantJump = blocked && headroom && onGround`
#     ＋ 3725 行 `setDeltaMovement(..., 0.42, ...)` ⇒ 起跳 0.42 ⇒ **约 1.25 格** ✓
#     ★同一处的 v2.7 注释就写着★："墙高 1.5 格 ⇒ 跳不过去（真人也不行）⇒ 真人会**绕**" ✓
#     ⇒ 模组照做 ✓（跳不上去时走 `detour` 绕障 ✓）
#   ⇒ 口径 ✓：`1`（一级整方块能跳 ✓）＋ ★由 `pathplan.is_climbable` 把**墙/树冠**那一格排除★ ✗
#   ⚠ 待办 ✓：游戏开起来之后**实测复验一次**（找一格**整方块**的 +1 台阶，真走上去 ✓）
#     验过了 ⇒ 把 `step_route_test`／`verdict_levels` 里"必须被拒"那半边**翻过来** ✓
MOD_CLIMB_UP = 1


class _LiveDelegates:
    """★★`_LIVE.<名>`：把"打进 `mc_mcp` 的桩"接到搬走的函数上✗★★

    为什么要有它 ✗（这是本轮**最容易假红**的地方 ✓）：
      测试/冒烟桩打的是 **`mc_mcp` 这个模块的属性** ✗（`M.dsh = 假` ✓ `M._walk = 假` ✓
      `M._pos_now` ✓ `M._near` ✓）—— 函数一搬到别的模块 ✓ 它的 `__globals__` 就换了 ✗
      ⇒ 桩打不着它 ⇒ 冒烟会**真去连桥**（假红 ✓）／`chest_many_test` 会**数不到 `_near`**
        ⇒ 那条"走一趟办多件"的判据会**假绿** ✗（**假绿比假红坏** ✗）
    口径 ✓：搬走的函数里那几个共享名字**只经这一个入口** ✓
      `_LIVE.dsh(...)` ⇒ `sys.modules["mc_mcp"].dsh(...)` ✓
      ⇒ 与"原来直接读本模块全局"**逐字等价** ✓（同一个 `__getattribute__` 路径 ✓）
    ⚠ 只代理**被桩打的那几个** ✗（`dsh`/`_walk`/`_pos_now`/`_near`/`ch` ✓）——
      纯函数（`cut`/`ok_of`/`errlog`/`kv`/`esc`…）**照旧直接 import** ✓ 少一层间接 ✓
    """

    _NAMES = ("dsh", "_walk", "_pos_now", "_near", "ch")

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        m = sys.modules.get("mc_mcp")
        if m is not None and hasattr(m, name):
            return getattr(m, name)
        return globals()[name]          # 没有 mc_mcp（单文件自测 ✓）⇒ 用 core 自己的 ✓


_LIVE = _LiveDelegates()

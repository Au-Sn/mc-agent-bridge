#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mcp_gesture.py -- ★★动作即语言（P2）✗★★：点头／摇头／指路（2026-10-02 ✓ 中间层 ✓ 零模组改动 ✓）

WHY ✓（★这是"伙伴"那半 ✗ 不是"控制"那半✗★）：
  ★控制类工具回答"把东西搬到哪"✗ ★动作语言回答"**我在跟你说话**"✗★
  ⇒ ★三件事✗★：① ★点头／摇头✗★（＝是／不是 ✓）② ★指路✗★（＝看过去 ＋ 一句话 ✓）
  ③ ★带路回头✗★（＝走 ＋ 回头看 ♥ 待做 ✓）

★纪律✗★（★按 P172 ✗ 每个动作**第一版**就带世界断言✓★）：
  ★姿态类动作的"世界真值"就是 **`dshdigest` 里的 yaw/pitch**✗★
  ⇒ ★做完**回读** ✗ 对不上就报红✗★（★不是"我发过 tp 了"✓★）

★纯函数在这里✗★（★`bearing_to` ✓ `nod_seq` ✓ `shake_seq` ✓）⇒ ★它们**离线可测**✗ ✓
  —— ★而 `t_look_at` 也改成用它✗ ⇒ **一处定义**✗（P106 ✓★）
"""
from __future__ import annotations

import math
import re
import sys
import time

# ★★2026-10-03 补✗★★（★P180 今天**第三次** ✗ 同一个形状✓★）：
#   ★`cut`（★截断长文本✓★）住在 **`mcp_core`**✗ ⇒ ★本模块原来只 import 了标准库✗★
#   ⇒ ★我写 `t_follow_gaze` 时直接用了它 ⇒ **运行必炸**（★编译能过 ✗ 正是 P180✓★）
#   ⇒ ★口径✗★：★写完新函数 ✗ 先问"**我用到的每个名字**从哪来"✗★ ✓
from mcp_core import cut, dsh  # noqa: E402
# ★★2026-10-03✗★★：★`dsh` 也是**我写 `_player_rot` 时才发现没导入**的✗★
#   ⇒ ★而我的 `except Exception: return None` 把 `NameError` **静默吞了**✗★
#   ⇒ ★于是我拿到的是"读不到玩家的朝向" ✗ 差一点读成"**玩家不在线**"✗★ ✓
#   ★口径✗★：★兜底**绝不许**吞掉"我自己代码写错"那一类 ✗ 要**打出来**✗★ ✓

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

EYE = 1.62          # ★眼睛高度（与玩家同 ✓）★
NOD_DEG = 18.0      # ★点头幅度✗★
SHAKE_DEG = 22.0    # ★摇头幅度✗★


def bearing_to(px, py, pz, tx, ty, tz, eye=EYE):
    """★从 (px,py,pz) 看向格中心 (tx,ty,tz) 的 (yaw, pitch)✗★ —— ★**唯一**定义（P106 ✓）★

    ★约定✗★：MC 里 `yaw=0` 朝 **+Z** ✗ yaw 增大＝从上往下看**顺时针** ✓ ⇒
      ★yaw = `-atan2(dx, dz)`✗ ✗ pitch = `-atan2(dy, 水平距)`✗★
    """
    dx = (tx + 0.5) - px
    dy = (ty + 0.5) - (py + eye)
    dz = (tz + 0.5) - pz
    yaw = math.degrees(math.atan2(-dx, dz))
    pitch = math.degrees(math.atan2(-dy, math.hypot(dx, dz)))
    return yaw, pitch


def wrap180(a):
    return ((a + 180.0) % 360.0) - 180.0


def nod_seq(base_pitch=0.0, times=1):
    """★点头＝"是"✗★：★低头 → 抬头 → 回中✗★（★幅度写死在上面 ✗ 不随手改✓★）"""
    out = []
    for _ in range(max(1, int(times))):
        out += [base_pitch + NOD_DEG, base_pitch - NOD_DEG, base_pitch]
    return out


def shake_seq(base_yaw=0.0, times=1):
    """★摇头＝"不是"✗★：★左 → 右 → 回中✗★"""
    out = []
    for _ in range(max(1, int(times))):
        out += [base_yaw - SHAKE_DEG, base_yaw + SHAKE_DEG, base_yaw]
    return out


# ── 与世界的接口（★可注入 ✗ 便于离线判据✓★）───────────────────────────────
def _send(cmd_text):
    from mcp_core import ch
    return ch().cmd(cmd_text, timeout=30.0, allow_str=True)


def pose_now():
    """★回读姿态✗★：`(yaw, pitch)` ✓ 读不到回 `(None, None)`"""
    from mcp_core import dsh
    t = dsh("dshdigest 1", 40.0) or ""
    m = re.search(r"yaw=(-?[\d.]+) pitch=(-?[\d.]+)", t)
    return (float(m.group(1)), float(m.group(2))) if m else (None, None)


def set_pose(yaw, pitch):
    return _send("tp %s ~ ~ ~ %.1f %.1f" % (BOT(), float(yaw), float(pitch)))


def BOT():
    from mcp_core import BOT as _B
    return _B


def say(text):
    from mcp_core import dsh
    return dsh("say %s" % str(text).replace("\n", " ")[:200], 40.0)


def _run_poses(seq, base, axis, label):
    """★按一串姿态值走一遍 ✗ 每步**回读**✗★ ⇒ ★返回 `(说明, 该不该报红)`✗★

    ★口径✗★：★与中间层其它工具**同一个约定**✗ —— `(text, bad)` ✓
      （★第一版我写成 `(ok, 说明)` ✗ ⇒ 判据那边 unpack 反了 ✗ 当场 TypeError ✓★）
    """
    got, bad = [], 0
    for v in seq:
        if axis == "pitch":
            set_pose(base[0], v)
        else:
            set_pose(v, base[1])
        time.sleep(0.22)
        g = pose_now()
        got.append(g)
        want = wrap180(v) if axis == "yaw" else v
        have = wrap180(g[0]) if axis == "yaw" else g[1]
        if have is None or abs(wrap180(have - want)) > 12.0:
            bad += 1
    ok = bad == 0
    return (("★%s✗★ 步数=%d ⇒ ★verified=%s✗★（★回读每步都对上才 true ✗ 对不上 %d 步✗★）"
             % (label, len(seq), "true" if ok else "false", bad)), (not ok))


def aim_and_verify(yaw, pitch, tries=2, tol=12.0, wait=0.25):
    """★★发姿态 ＋ **回读** ＋ 必要时**重发**✗★★（2026-10-03 ✓ 欠账 ⑲ 的正事 ✓）

    ★为什么不能"发一次就完"✗★（⑲ ✓ 实测 ✓）：★假人是**共享**的✗ —— ★常驻脑也在发动作✗★
      ⇒ ★单发那次可能被**别人的动作覆盖**✗（★实测差 123.7 度 ✗ 而如实报了 false ✓★）
      ★旁证✗★：★`gesture` 每步只等 0.22 秒、而且**逐步回读** ⇒ **全过**✗★ ✓
    ★⇒ 口径✗★：★"设姿态"必须带**回读**✗ ✗ 对不上就**再发一次**✗（★默认最多 2 次 ✓★）
    ★返回✗★：`(对上没有, 最后回读到的 (yaw,pitch), 用了几次)` ✓
    """
    got = (None, None)
    for i in range(1, max(1, int(tries)) + 1):
        set_pose(yaw, pitch)
        time.sleep(wait)
        got = pose_now()
        if got[0] is None:
            continue
        dy = abs(wrap180(wrap180(got[0]) - wrap180(yaw)))
        dp = abs(got[1] - pitch)
        if dy <= tol and dp <= tol:
            return True, got, i
    return False, got, max(1, int(tries))


# ★★注入缝✗★★（2026-10-03 ✓ P180 的**第二次**正面用法 ✓）：
#   ★为什么又踩一次✗★：★`t_lead_to` 里写的是 `from mcp_core import _pos_now`（★函数内局部导入✗★）
#     ⇒ ★判据那边 `G._pos_now = 假的` **注入不进去**✗★ ⇒
#     ★那个"离线判据"其实**偷偷依赖了活世界**✗（★世界活着 ⇒ 碰巧过 ✗ 桥一断 ⇒ 立刻露馅✓★）★
#   ⇒ ★口径✗★：★凡是"判据要替换掉的东西" ✗ 都必须有一个**模块级变量**做缝✗★ ✓
POS = None


def _default_pos():
    """★真依赖✗★（★判据里有一条"**不注入时**它点得着吗"✗ ✓ P180 ✓★）"""
    from mcp_core import _pos_now
    return _pos_now()


def _pos():
    return POS() if POS else _default_pos()


def parse_pos_line(txt):
    """★从 `data get entity <玩家> Pos` 的回执里抠出坐标✗★（★回执是**英文** ✗ 过 CC 不会被吃✓★）

    ★形状✗★：`Au_Sn has the following entity data: [123.4d, 71.0d, 5.6d]`
      ⇒ ★三个数字 ✗ 带 `d` 后缀✓★（★第一版要是按中文回执去抠 ✗ 必踩 P13/P38 那个坑✓★）
    """
    if not txt:
        return None
    m = re.search(r"\[\s*(-?[\d.]+)d?\s*,\s*(-?[\d.]+)d?\s*,\s*(-?[\d.]+)d?\s*\]", txt)
    if not m:
        return None
    return (float(m.group(1)), float(m.group(2)), float(m.group(3)))


def player_pos():
    """★问服务器要**玩家**的真实坐标✗★（★读不到就回 None ✗ 不许猜✓★）"""
    from mcp_core import PLAYER, dsh
    t = dsh("data get entity %s Pos" % PLAYER, 30.0) or ""
    return parse_pos_line(t)


# ★★注入缝✗★★（2026-10-03 ✓ P180 的正面用法 ✓）：
#   ★为什么需要一个**变量**而不是直接注入函数名✗★：★`t_walk_route` 是**懒导入**进来的✗★
#     ⇒ ★测试替换模块属性**替换不到**它 ✗★（★函数体里那次 import 会把假货盖掉✓★）
#   ⇒ ★口径✗★：★"要注入的东西"必须留一个**模块级变量**做缝 ✗
#     ✗ 且 ★判据里还要有一条"**不注入时**真依赖点得着吗"✗★（★这条就是 P180 的补丁✓★）
WALK = None


def _default_walk():
    """★真依赖✗★：★`t_walk_route` 住在 `mcp_walk` ✓ 懒导入免得循环✓★"""
    from mcp_walk import t_walk_route
    return t_walk_route


def _walk():
    return WALK or _default_walk()


def t_lead_to(x=None, y=None, z=None, look_back=True, timeout_ms=60000):
    """★`lead_to`✗★：★带路——走到目标 ✗ 然后**回头看玩家**✗★（P2 的第三件 ✓ 2026-10-03 ✓）

    ★判据（★两条都要世界真值✗★）★
      L1 ★到位✗★：★`walk_route` 自己的复核 ✗ ＋ 回读位置（★差得远就报红✓★）
      L2 ★回头✗★：★`yaw/pitch` 与"看向玩家坐标"算出来的角**对上**✗ ⇒ `verified=true` ✓
    ★读不到玩家坐标 ✗ 不算失败 ✗ 但要**明写** `look_back=unavailable`✗★（★不静默 ✓★）
    """
    if x is None or y is None or z is None:
        return ("★要么给 x/y/z（要到哪去 ✓）✗ ✗ 没目标带什么路✗★"), True
    from mcp_walk import t_walk_route  # noqa: F401  ★真依赖在这里被**真**点一次（见 P180 ✓）★
    out, bad = _walk()(int(x), int(y), int(z), timeout_ms=timeout_ms)
    parts = ["★带路✗★ 目标 (%s,%s,%s) ⇒ %s" % (x, y, z, str(out).replace("\n", " | ")[:150])]
    if not look_back:
        return (" ｜ ".join(parts)), bad
    pp = player_pos()
    if pp is None:
        parts.append("★回头看 ✗ look_back=unavailable✗★（★读不到玩家坐标 ✗ 没瞎转✓★）")
        return (" ｜ ".join(parts)), bad
    me = None
    me = _pos()
    if me is None:
        parts.append("★回头看 ✗ verified=false✗★（★读不到自己的坐标✓★）")
        return (" ｜ ".join(parts)), True
    want_yaw, want_pitch = bearing_to(me[0], me[1], me[2], pp[0], pp[1], pp[2])
    okv, g, used = aim_and_verify(want_yaw, want_pitch)
    dy = abs(wrap180(wrap180(g[0]) - wrap180(want_yaw))) if g[0] is not None else 999
    dp = abs(g[1] - want_pitch) if g[1] is not None else 999
    parts.append("★回头看玩家 (%.1f,%.1f,%.1f)✗★ ⇒ 回读 yaw=%.1f pitch=%.1f（★差 %.1f/%.1f ✗ 发了几次 %d✗★）"
                 "｜ ★verified=%s✗★" % (pp[0], pp[1], pp[2], g[0] or 0.0, g[1] or 0.0, dy, dp, used,
                                       "true" if okv else "false"))
    return (" ｜ ".join(parts)), (bad or (not okv))


# ── ★★`follow_gaze`✗★★（2026-10-03 ✓ 观感那一轴里最可验的一件 ✓）
#   ★它做什么✗★：★读**玩家自己**的视线（★yaw/pitch ✗ 世界真值✓★）⇒ ★让假人**朝同一个方向看**✗★ ✓
#   ★为什么值得有✗★：★现在假人只会"指**我算出来的**那个点"✗
#     ⇒ ★而"看你在看什么"是**伙伴**才有的动作 ✗ 也是 `point_at` 的天然上游✗★ ✓
#   ★判据（★先写死 ✗ 四条✗★）★
#     G1 ★读**玩家**的视线 ✗ 读不到 ⇒ **明写 unavailable**✗（★不猜 0,0✓★）
#     G2 ★对准要走 `aim_and_verify`✗（★回读 ＋ 一次重试 ✗ 回执报发了几次✓★）
#     G3 ★对准之后 ⇒ 回读的 yaw **等于玩家那个 yaw**（±容差✗★）
#     G4 ★玩家不在 ⇒ **拒**✗（★不许静默 no-op✓★）
def _player_rot(name):
    """★问世界 ✗ 玩家的朝向是多少✓★（★读不到 ⇒ None ✗ 不猜✓★）

    ★★2026-10-03 当场修✗★★：★我第一版写的是
      `dsh("execute as Bot at Bot run data get entity %s Rotation")`✗★
      ⇒ ★而 **`mcp_core.dsh` 自己就会加** `execute as Bot at Bot run` 前缀✗★
        （★`mcp_core.py:64` 的 docstring 明写着 ✓★）
      ⇒ ★**前缀加了两层** ⇒ 命令废 ⇒ 回 `None` ⇒ 我还差点把它读成"玩家不在线"✗★ ✓
    ★口径✗★：★用 `dsh` 时只写**动作本身**✗ ✗ 前缀归它✗★ ✓
    （★这是今天第四次"没问清哪一层" ✗ 前三次见 §79.46／§79.47／§79.50✓★）
    """
    try:
        t = dsh("data get entity %s Rotation" % name, 40.0) or ""
    except Exception as e:
        # ★★兜底**不许**吞掉"我自己写错"✗★★（2026-10-03 ✓ 就是这里把 NameError 吞成了"不在线"✓★）
        print("★[_player_rot] 读失败 ✗ 而且这是**代码/通道**问题不是「玩家不在」✗★：%s: %s"
              % (type(e).__name__, e))
        return None
    m = re.search(r"\[\s*(-?[\d.]+)f?d?\s*,\s*(-?[\d.]+)f?d?\s*\]", t)
    if not m:
        return None
    return float(m.group(1)), float(m.group(2))


def t_follow_gaze(player="Au_Sn", tol=6.0):
    """★★跟着你的视线看✗★★（★读**玩家**的 yaw/pitch ⇒ 假人朝同一方向看 ⇒ 回读自证✓★）

    ★★2026-10-03 世界验收抓出来的一件事✗★★：★它**间歇**失败✗★ ✓
      · ★站着时 ✗ 发完立刻读＝目标 ✗ 2 秒后**仍是**目标✗★（★实测 47.5/17.8 ✓★）
      · ★而走路时 ✗ **走路任务每 tick 都在设 yaw**✗ ⇒ ★姿态被盖掉 ⇒ `verified=false`✗★
        （★回读是 `-155.9` 那种"别人的姿态" ✓ 事件流里 `idle_stroll`／`walk_done` 一直在刷✓★）
      ⇒ ★这是 **⑲**"共享控制"那一族的**间歇版** ✗ 而它只在**动的时候**出现✗★ ✓
    ★处置（★也是"像个人"的做法✗★）★：★先**停下**（★Carpet 的 `stop` ✓ §79.43 学的✓★）
      再转头 ✗ 然后回读✗★ —— ★伙伴要看你指的东西 ✗ 本来就会先站住✗★ ✓
    """
    try:
        _send("player %s stop" % BOT())        # ★先站住 ✗ 不许边走边转✓★
        time.sleep(0.25)
    except Exception as e:
        print("★[follow_gaze] 停那一步失败 ✗ 据实继续（%s: %s）★" % (type(e).__name__, e))
    rot = _player_rot(player)
    if rot is None:
        return cut("★跟视线✗★ 读不到 **%s** 的朝向 ⇒ ★unavailable✗★"
                   "（★可能它不在线 ✗ 或这条命令没权限 ✓ 不猜 0,0✓★）" % player), True
    yaw, pitch = rot
    okv, msg, sends = aim_and_verify(yaw, pitch, tol=tol)
    note = ("★跟视线✗★ %s yaw=%.1f pitch=%.1f ✗ 发了几次 %d ✗ ★verified=%s✗★ ｜ %s"
            % (player, yaw, pitch, sends, "true" if okv else "false", msg))
    return cut(note), (not okv)


# ── ★★挂机小动作✗★★（2026-10-03 ✓ 观感那一轴的"① 闲着时像不像人" ✓）
#   ★它做什么✗★：★闲下来时 ✗ 轻轻看一眼别处（★小幅度转头✓★）✗ 再**转回原处**✗★ ✓
#     ★不是"随机抽搐" ✗ 而是**一次有始有终的小动作**✗（★幅度有上限 ✗ 而且必须回到原位✓★）★
#   ★三条硬约束（★都是被世界教出来的✗★）★
#     · ★★走路时不抢 yaw✗★★（★§79.55：★移动中身体朝向**归移动**所有✓★）
#     · ★★有**冷却**✗★★（★人不会每 5 秒甩一次头 ✓★）
#     · ★★时长为上✗★★（★不许卡住 ✗ 到点必须回来 ✓★）
#   ★判据✗★（★I1~I4 ✗ 离线可判✓★）：★I1 busy ⇒ 不做 ✗ I2 幅度 ≤ 上限✗ ✗
#     ★I3 必须**转回原位**（回读 ±2°✗★）✗ ★I4 冷却内再来 ⇒ 拒 ✗ 且**说明还要等几秒**✗★ ✓
IDLE_COOLDOWN = 45.0        # ★秒✗★（★够长 ✗ 才像"偶尔看一眼"✓★）
_last_idle = [0.0]


def t_idle_beat(amplitude=20.0, hold=1.2, busy=None, now=None, cooldown=None):
    """★★挂机小动作✗★★：★闲时轻看一眼再转回原处✗★（★busy 由调用方给 ✗ 免得**反向依赖**✓★）

    ★为什么 `busy` 要**外面传**✗★：★`mcp_gesture` 在**下层** ✗ 让它反过来 import `mc_mcp`
      会成环✗★ ✓ ⇒ ★口径✗★：★"我现在忙不忙"这种事 ✗ 归**上层**判 ✗ 下层只收结论✗★ ✓
    """
    import time as _t
    now = now or (lambda: _t.time())
    cd = IDLE_COOLDOWN if cooldown is None else float(cooldown)
    # ★I1：忙 ⇒ 什么都不做（★而且要说清"因为忙" ✗ 不许默默不动✓★）
    if callable(busy):
        try:
            b, why = busy()
        except Exception as e:
            return cut("★挂机小动作✗★ ✗ 忙不忙**问不出来**✗ ⇒ ★不做✗★（★不静默 ✗ %s✓★）"
                       % type(e).__name__), True
        if b:
            return cut("★挂机小动作✗★ ✗ **不做**✗ ⇒ 现在忙：%s（★走路时身体朝向归移动 ✗ "
                       "§79.55✓★）" % why), True
    # ★I4：冷却
    left = cd - (now() - _last_idle[0])
    if left > 0:
        return cut("★挂机小动作✗★ ✗ **不做**✗ ⇒ 刚做过 ✗ 还要等 **%.0f** 秒（★人不会一直甩头✓★）"
                   % left), True
    before = pose_now()
    if not before or before[0] is None:
        return cut("★挂机小动作✗★ ✗ 读不到自己朝向 ⇒ **不做**✗（★不猜✓★）"), True
    y0, p0 = float(before[0]), float(before[1])
    # ★I2：幅度**有上限** ✗ 而且是**先往一侧看一眼**✗★
    amp = max(3.0, min(45.0, float(amplitude)))
    side = 1.0 if (int(now()) % 2 == 0) else -1.0
    okv, msg, sends = aim_and_verify(y0 + side * amp, p0 - 6.0, tol=8.0, tries=1)
    _t.sleep(max(0.2, min(3.0, float(hold))))          # ★I3：时长有上✗★
    back_ok, back_msg, back_sends = aim_and_verify(y0, p0, tol=2.0, tries=2)
    _last_idle[0] = now()
    note = ("★挂机小动作✗★ 幅度 %.0f° ✗ 发了几次 %d ✗ ★转回来了=%s✗★ ｜ 回看 %s"
            % (amp, sends + back_sends, "true" if back_ok else "false", back_msg))
    return cut(note), (not back_ok)


# ★★2026-10-03 手滑记录✗★★：★我上面那处替换**吃掉了 `def t_gesture(...)` 这一行**✗★
#   ⇒ ★`t_gesture` 的函数体就挂到了 `t_idle_beat` 后面 ✗（★编译期才发现✓★）
#   ★口径✗★：★用 `edit` 替换时 ✗ **锚点里包含的那一行**要原样写回 ✗ 否则就是**删了一行**✗★ ✓
def t_gesture(kind="nod", times=1):
    """★`gesture`✗★：★点头（是 ✓）／摇头（不是 ✓）✗★ —— ★做完**回读姿态**✗ ✗ 不乱报成功✓★"""
    k = (kind or "nod").strip().lower()
    base = pose_now()
    if base[0] is None:
        return ("★读不到姿态 ✗ verified=false✗★（★这次没做 ✓ 先确认 Bot 在不在✓★）"), True
    if k in ("nod", "点头", "yes", "是"):
        return _run_poses(nod_seq(base[1], times), base, "pitch", "点头")
    if k in ("shake", "摇头", "no", "不是"):
        return _run_poses(shake_seq(base[0], times), base, "yaw", "摇头")
    return ("★只认得 `nod`（点头）／`shake`（摇头）✗ ✗ 收到的是 %r✗★" % kind), True


def t_point_at(x=None, y=None, z=None, yaw=None, pitch=None, text=None):
    """★`point_at`✗★：★看过去 ＋（可选）说一句✗★ —— ★回读 yaw/pitch 报 verified✗★"""
    base = pose_now()
    if base[0] is None:
        return ("★读不到姿态 ✗ verified=false✗★"), True
    if x is None or y is None or z is None:
        if yaw is None:
            return ("★要么给 x/y/z（看向某点 ✓）✗ 要么给 yaw（看向某方向 ✓）✗★"), True
        want_yaw = float(yaw)
        want_pitch = float(pitch) if pitch is not None else base[1]
        label = "方向 yaw=%.0f" % want_yaw
    else:
        p = _pos()
        if not p:
            return ("★读不到自己的坐标 ✗ verified=false✗★"), True
        want_yaw, want_pitch = bearing_to(p[0], p[1], p[2], x, y, z)
        label = "点 (%s,%s,%s)" % (x, y, z)
    okv, g, used = aim_and_verify(want_yaw, want_pitch)
    dy = abs(wrap180(wrap180(g[0]) - wrap180(want_yaw))) if g[0] is not None else 999
    dp = abs(g[1] - want_pitch) if g[1] is not None else 999
    said = ""
    if text:
        try:
            say(text)
            said = " ｜ 说了：%s" % str(text)[:60]
        except Exception as e:
            said = " ｜ ★说那句失败了✗★（%s）" % type(e).__name__
    return ("★指路✗★ %s ⇒ 回读 yaw=%.1f pitch=%.1f（★差 %.1f/%.1f ✗ 发了几次 %d✗★）"
            "｜ ★verified=%s✗★%s"
            % (label, g[0] or 0.0, g[1] or 0.0, dy, dp, used,
               "true" if okv else "false", said)), (not okv)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run.py — 智能体总入口（体检 / 感知 / 技能 / 大脑 / 反射）

用法：
    py agent/run.py doctor                      # 体检：通道、schema、假人、部署是否最新、API
    py agent/run.py perceive                    # 打印假人现在"看到"的世界（只读）
    py agent/run.py tools                       # 列出技能表
    py agent/run.py do scan radius=5            # 手动跑一个技能
    py agent/run.py reflex --dry-run            # 只观察反射层行为，不动手
    py agent/run.py journal -n 30               # 看行动流水（出问题先看这个）
    py agent/run.py ask "砍一棵树并回到房子"     # 让模型自己决定（需要 AGENT_API_KEY）
    py agent/run.py plan "造一个 5x5 平台"       # 只出计划不执行（安全预览）
    py agent/run.py script agent/plans/smoke.json
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from channel import (Channel, COMPUTERS, SAVE_DIR, BridgeError,   # noqa: E402
                     schema_freshness, load_schema)
from memory import Journal                                        # noqa: E402
from skills import Skills                                         # noqa: E402
from world import World                                           # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

LUA_LOCAL = HERE.parent / "cc-tweaked" / "agent_bridge.lua"

# ★ 可选/遗留的机器（用户定的方向 ✓ 见 docs/模组-容器存取与假人手.md §8 ✓）★
#   为什么要有这张表 ✗：cc0 每经历一次世界重启就会把自己搞成 0 字节 ✗（错题本 P18 ✓）
#   ⇒ 体检时它**必然**报红 ✓ 而它现在**一点也挡不着主线** ✗（模组已把它那几件活儿全接走 ✓）
#   ⇒ 报红的意义是"提醒有人要修它"✓；把它算成"故障"✗ 就会训练人**忽略红色**✗✗
#     —— 那比不报还危险 ✓ 所以：可选机器报 **提示** ✓ 必需机器才报 **故障** ✗
OPTIONAL_COMPUTERS = {
    "cc0":    "cc0(/海龟转发那条路) 已降级为可选 ✓（模组 /dshuse /dshcraft /dshbox /dshinv 已替代它 ✓）",
    "turtle": "海龟已降级为可选 ✓（它的活儿模组都能干 ✓）",
}


def _coerce(v, typ: str | None = None):
    """把命令行字符串转成合适类型。

    注意：只有当参数声明了数字类型（或没类型信息）时才尝试转数字 ——
    否则 `do say 404` 会变成整数 404 而不是字符串 "404"。
    """
    if not isinstance(v, str):
        return v
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    if typ in (None, "number", "integer"):
        try:
            return int(v)
        except ValueError:
            try:
                return float(v)
            except ValueError:
                pass
    return v


def _kv_args(argv: list[str]) -> dict:
    return {a.split("=", 1)[0]: _coerce(a.split("=", 1)[1])
            for a in argv if not a.startswith("--") and "=" in a}


def _split_args(argv: list[str], spec: dict | None = None) -> dict:
    """k=v 形式 + 位置参数一起支持。

    为什么支持位置参数：`do say "hello"` 比 `do say text=hello` 自然得多，
    而且第一次用的人一定会这么写 —— 那就别让它报"缺少参数"。
    位置参数按声明顺序填（必填优先）。
    """
    kv: dict = {}
    positional: list[str] = []
    for a in argv:
        if a.startswith("--"):
            continue
        if "=" in a:
            k, v = a.split("=", 1)
            kv[k] = _coerce(v)
        else:
            positional.append(a)
    params = (spec or {}).get("params") or {}
    if positional and params:
        required = [p for p, v in params.items() if len(v) > 2 and v[2]]
        order = required + [p for p in params if p not in required]
        for val, pname in zip(positional, order):
            if pname in kv:
                continue
            kv[pname] = _coerce(val, params[pname][0])
    return kv


# --------------------------------------------------------------------------- #

def cmd_doctor(argv: list[str]) -> int:
    problems, notes = [], []

    ok, msg = schema_freshness()
    (notes if ok else problems).append("schema：" + msg)

    # 部署是否最新：机器内存里跑的是哪一版，只能靠"磁盘上的文件大小"间接判断。
    # 注意真实路径：CC 把程序存成**没有扩展名的文件** `bridge_local` / `worker_local`，
    # 不是一个目录。之前这里查的是 bridge_local/agent_bridge.lua ✗ → 检查一直在空跑 ✓
    # 现在找不到文件会**明确报错**，因为静默跳过的检查等于没有检查 ✓。
    targets = [(LUA_LOCAL, "bridge_local", "agent_bridge.lua", ("cmd0", "cc0"))]
    optional_dead: set[str] = set()      # 磁盘上就是 0 字节的可选机器 ✓（已知它在跑空程序 ✗）
    turtle_local = HERE.parent / "cc-tweaked" / "turtle_worker.lua"
    if turtle_local.is_file():
        targets.append((turtle_local, "worker_local", "turtle_worker.lua", ("turtle",)))
    for repo_file, disk_name, label, who_list in targets:
        if not repo_file.is_file():
            problems.append("仓库里找不到 %s（%s）" % (label, repo_file))
            continue
        local = repo_file.stat().st_size
        repo_mtime = repo_file.stat().st_mtime
        for who in who_list:
            cid = COMPUTERS[who]["id"]
            p = SAVE_DIR / "computercraft" / "computer" / str(cid) / disk_name

            def put(msg: str) -> None:
                """可选机器 → 提示 ✓；必需机器 → 故障 ✗（理由见 OPTIONAL_COMPUTERS 注释 ✓）"""
                if who in OPTIONAL_COMPUTERS:
                    notes.append("[可选] " + msg)
                else:
                    problems.append(msg)

            if not p.is_file():
                put("计算机 %s 的磁盘文件不存在：%s（程序没部署？）" % (who, p))
                continue
            st = p.stat()
            d = st.st_size
            if d == 0 and who in OPTIONAL_COMPUTERS:
                optional_dead.add(who)      # ⇒ 等一下连探测都不发 ✗（见状态检查那段注释 ✓）
            # 关键判据（这一晚被咬过两次 ✗）：磁盘副本是**上次开机时**从网关拉下来的 ✓
            #   → "磁盘副本比仓库旧" == **这台机器内存里跑的还是旧程序** ✗
            #   真实事故：cmd0 从 09-12 起没重启过 ✓ → go_relative / run_job 全报「未知指令」✗
            #   而**按文件大小比对完全看不出来** ✗（大小恰好一样 ✓）→ 必须比 mtime ✓
            stale = (repo_mtime - st.st_mtime) > 5
            if d != local:
                put("计算机 %s 的 %s 是 %d 字节，仓库里是 %d 字节 → "
                    "重启该计算机即可从网关拉取新版%s"
                    % (who, disk_name, d, local,
                       "（可选机器 ✗ 想修就照 docs/模组-容器存取与假人手.md §8.3 三步 ✓）"
                       if who in OPTIONAL_COMPUTERS else ""))
            elif stale:
                put("计算机 %s 内存里很可能还是【旧程序】✗：它的 %s 是 %s 拉取的，"
                    "而仓库在 %s 之后改过 → 重启这台计算机即可加载新版"
                    "（⚠ 别把 shutdown/turn-on 发给它自己 ✗ 会把自己锁在门外 ✓）"
                    % (who, disk_name,
                       time.strftime("%m-%d %H:%M", time.localtime(st.st_mtime)),
                       time.strftime("%m-%d %H:%M", time.localtime(repo_mtime))))
            else:
                notes.append("计算机 %s 的 %s 与仓库一致（%d 字节，%s 拉取）"
                             % (who, disk_name, d,
                                time.strftime("%m-%d %H:%M", time.localtime(st.st_mtime))))
    ch = Channel("cmd0", verbose=False)
    q = ch.queued()
    if not q:
        problems.append("读不到 state.json 的队列 → 网关可能没在跑（要带 --bridge-dir bridge）")
    else:
        notes.append("网关队列：%s" % q)

    st = ch.bridge / "state.json"
    if st.is_file():
        try:
            age = time.time() - json.loads(st.read_text(encoding="utf-8")).get("ts", 0)
            (notes if age < 15 else problems).append("心跳年龄 %.1f 秒" % age)
        except Exception:
            pass

    try:
        alive = ch.alive()
        (notes if alive else problems).append("假人 Bot：%s" % ("在线" if alive else "查不到（不在线或没召唤）"))
    except BridgeError as e:
        problems.append("查假人在线状态失败：%s" % e)

    # 逐机存活检查 ✓ —— 为什么需要它：
    #   "某台计算机被关机"过去只能靠 45 秒超时**猜**出来 ✗
    #   （真实事故：我 shutdown 了 cmd0 ✓ 而 turn-on 被排进它自己的队列 ✗ → 把自己锁在门外 ✗）
    #   现在对每台机器发一条最短的 status ✓ 用很短的超时 ✓ 一眼看清谁活着 ✓
    cc0_alive = False
    for who in ("cc0", "cmd0"):
        if who in optional_dead:
            # ★ 已知它是坏的（磁盘上就是 0 字节 ✗）⇒ **一次探测都别发** ✗
            #   理由 ✓："问也白问"是小事 ✗ —— 真正的代价是**往它的死队列里堆垃圾** ✗
            #   （实测：队列从 0 涨到 7 ✗ 而"队列>0"本来是**判据**✗ ⇒ 判据被自己污染 ✗）
            notes.append("计算机 %s（**可选/遗留** ✓）：磁盘副本 0 字节 ⇒ 它在跑空程序 ✗ "
                         "⇒ 不发探测（问了也白问 ✓ 还会污染队列 ✗）"
                         " 修法：docs/模组-容器存取与假人手.md §8.3 三步 ✓" % who)
            continue
        try:
            Channel(who, verbose=False).call("status", timeout=12.0, allow_str=True)
            notes.append("计算机 %s：在应答 ✓" % who)
            if who == "cc0":
                cc0_alive = True
        except BridgeError as e:
            if who in OPTIONAL_COMPUTERS:
                # ★ 可选机器**不许把体检染红** ✗（理由见 OPTIONAL_COMPUTERS 注释 ✓）
                #   它每经历一次世界重启就会把自己搞成 0 字节 ✗ ⇒ 报红是**必然事件** ✗
                notes.append("计算机 %s（**可选/遗留** ✓）：没有应答 —— **不影响主线** ✓（%s）"
                             " 修法：docs/模组-容器存取与假人手.md §8.3 三步 ✓"
                             % (who, str(e)[:110]))
            else:
                problems.append("计算机 %s：**没有应答** ✗（关机？程序卡住？）%s" % (who, str(e)[:150]))
    # 海龟只能经 cc0 转发 ✓ 而且它**在跑长作业时本来就不会应答** ✓ 所以只作提示 ✓ 不算故障 ✓
    # ⚠ 而 cc0 已经不应答时**根本不要发** ✗ —— 发了只会往它的死队列里堆垃圾 ✓（队列深度会一直涨 ✗
    #   曾涨到 5~6 条 ✓ 让"队列>0"这个判据彻底失去意义 ✗ ⇒ 这里跳过并说清为什么 ✓）
    if not cc0_alive:
        notes.append("海龟：跳过探测 ✓ —— 海龟只能经 cc0 转发 ✗ 而 cc0 没应答 ✓"
                     "（主线不需要海龟 ✓ 见 docs/模组-容器存取与假人手.md §8 ✓）")
    else:
        try:
            router = Channel("cc0", verbose=False)
            cid = router.send("status", {"target": 1})
            router.wait(cid, timeout=15.0, cmd="status->turtle")
            notes.append("海龟：在应答 ✓")
        except BridgeError:
            notes.append("海龟：未应答 —— 可能是**正在跑长作业**（正常 ✓）"
                         "；用 py tools/cc_logs.py 1 看它的磁盘日志最可靠 ✓")

    if os.environ.get("AGENT_API_KEY"):
        notes.append("模型接口：%s / %s（已配置 key）"
                     % (os.environ.get("AGENT_API_BASE", "https://api.openai.com/v1"),
                        os.environ.get("AGENT_MODEL", "gpt-4o-mini")))
    else:
        notes.append("模型接口：未配置 AGENT_API_KEY → 只能用 plan/script 模式")

    print("=" * 74)
    print("体检")
    print("-" * 74)
    for n in notes:
        print("  [OK] " + n)
    for p in problems:
        print("  [!!] " + p)
    print("-" * 74)
    print("结论：%s" % ("一切正常，可以开跑" if not problems else
                        "有 %d 项需要注意（见上）" % len(problems)))
    print("=" * 74)
    return 0 if not problems else 1


def cmd_perceive(argv: list[str]) -> int:
    ch = Channel("cmd0", verbose=False)
    w = World(ch)
    print("=" * 74)
    print("假人感知（全部来自权威来源）")
    print("-" * 74)
    print(w.text(survey_radius=int(_kv_args(argv).get("radius", 6))))
    print("=" * 74)
    return 0


def cmd_tools(argv: list[str]) -> int:
    ch = Channel("cmd0", verbose=False)
    sk = Skills(ch, World(ch), allow_scaffold="--allow-scaffold" in argv)
    print(sk.help_text())
    return 0


def cmd_do(argv: list[str]) -> int:
    if not argv:
        print("用法：py agent/run.py do <技能> k=v ...")
        return 2
    ch = Channel("cmd0")
    sk = Skills(ch, World(ch), allow_scaffold="--allow-scaffold" in argv)
    from skills import SPEC
    r = sk.run(argv[0], _split_args(argv[1:], SPEC.get(argv[0])))
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return 0 if r.get("ok") else 1


def cmd_reflex(argv: list[str]) -> int:
    from reflex import Reflex
    ch = Channel("cmd0", verbose=False)
    w = World(ch)
    sk = Skills(ch, w, allow_scaffold=False, verbose=False)
    rx = Reflex(w, ch, skills=sk, dry_run=("--live" not in argv),
                verbose=True)
    secs = 30.0
    for a in argv:
        if a.startswith("--seconds="):
            secs = float(a.split("=", 1)[1])
    print("反射层观察 %ss（dry_run=%s：只报告不还手）" % (secs, rx.dry_run))
    rx.start()
    t0 = time.time()
    try:
        while time.time() - t0 < secs:
            time.sleep(2)
            for ev in rx.drain():
                print("  [事件] %s: %s" % (ev["kind"], ev["text"]))
    except KeyboardInterrupt:
        pass
    finally:
        rx.stop()
    print("统计：%s" % json.dumps(rx.stats, ensure_ascii=False))
    return 0


def cmd_look(argv: list[str]) -> int:
    """看游戏窗口的真实画面（B 线：绕不过界面时，我自己看、自己点）。

    为什么要有这条：科技包里大量机器自带 UI ✓ 假人开不了 ✗
    所以保留一条"人眼通道"：截图 → 我看图 → 需要时点击 ✓
    顺带它还给了我们一个**独立于 CC 的验证通道** ✓（能亲眼确认世界到底长什么样 ✓）
    """
    from screen import Screen
    sc = Screen()
    ok, msg = sc.healthy()
    print(("窗口正常：" if ok else "窗口有问题：") + msg)
    if not ok and "--fix" not in argv:
        # 关键：不健康时**不要**照样抓一张垃圾图 ✗
        # 那会产出一张"看起来像截图"的误导证据 ✓ 比报错危险得多 ✓
        print("（没有加 --fix，所以不抓图：避免产出一张会误导人的坏截图）")
        return 1
    try:
        p = sc.look(rescue=("--fix" in argv))
    except Exception as e:
        print("[X] 抓图失败：%s: %s" % (type(e).__name__, e))
        return 1
    print("已抓图：%s  → 用 read_image 看它" % p)
    return 0 if ok else 1


def cmd_journal(argv: list[str]) -> int:
    n = 20
    for a in argv:
        if a.startswith("-n"):
            n = int(a.split("=", 1)[1]) if "=" in a else n
    j = Journal("actions")
    rows = j.tail(n)
    if not rows:
        print("（还没有行动记录）")
        return 0
    for r in rows:
        print("%s  %-8s %-12s %s" % (r.get("at"), r.get("kind"), r.get("skill", ""),
                                     (r.get("summary") or "")[:150]))
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    mode, rest = argv[0], argv[1:]
    table = {
        "doctor": cmd_doctor,
        "perceive": cmd_perceive,
        "tools": cmd_tools,
        "do": cmd_do,
        "reflex": cmd_reflex,
        "journal": cmd_journal,
        "look": cmd_look,
    }
    if mode in table:
        return table[mode](rest)
    if mode in ("ask", "plan", "script"):
        import brain
        return brain.main(argv)
    print("未知子命令：%s" % mode)
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

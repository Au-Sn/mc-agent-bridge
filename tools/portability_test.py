#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""portability_test.py -- ★解绑判据✗★：工具/agent/legacy 里不许再有环境绑定字面量

规格（docs/评估四-解绑与优先级.md 的 P0 第三条；发版准备 task-14 扩面）：
  ★"这条门是'再也不长回来'的保证"✗★ —— 没有它，解绑会被下一次新增工具冲掉。

判法（★除 `paths.py` 与显式例外/误报表外✗★）：
  扫描范围：`tools/*.py` ＋ `agent/*.py` ＋ `tools/legacy/*.py`（★没配 dsh.env 的机器也要能过✗★）
  P1 绝对路径  ：`D:\\…`／`C:\\Users…`／`/home/…`／`/Users/…`（Windows/Unix 硬编码）
  P2 实例名    ：`All the Mods 9`／`atm9sky` 等（从 `paths.INSTANCE_NAME` 与已知别名派生）
  P3 存档名    ：`新的世界` 等（从 `paths.SAVE_NAME` 派生）
  P4 端口字面量：`8766`／`8765`（必须走 `paths.PORT`／`paths.GATEWAY_PORT`）
  P5 例外表    ：每条必须**带理由**（★写域表 ＝ 本轮改不了；误报表 ＝ 判据自带模式串★）
  P6 配置优先级：环境变量 > `dsh.env` > 默认（纯函数注入验证，不碰真环境）
  P7 `paths.py` 必须导出关键常量（MC_HOME／MODS_DIR／SAVE_DIR／BOT／PORT／GATEWAY_PORT…）
  P8 迁移覆盖  ：tools ≥20 个已 import paths ＋ agent/channel／world 两个都迁了
  P9 ★自检能红✗★：合成源文本四类违规**每个都能抓到**；干净不误报；例外能吃掉
  P10 ★未配置 ⇒ 明确报错**而不是静默用本机路径**★（paths.require／agent import／大脑层提示）
  P11 `dsh.env.example` 必须存在、占位符化、含全部配置项、**没有真路径**
  P12 计数器：扫过的三个目录文件数对得上（★不许空转冒充全扫✗★）
  W1 BOT 字面量：**只告警不判红**（默认参数/对外协议名，冻结面不许改行为）——报告里给计数

机器行：`PORTABILITY ok=1 scanned=N violations=0 exceptions=K warnings=W`
"""
from __future__ import annotations

import io
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import paths as PA            # noqa: E402  ★被扫对象之一 ✗ 也是扫描配置的来源✗★

TOOLS = ROOT / "tools"
AGENT = ROOT / "agent"
LEGACY = TOOLS / "legacy"

# ★写域豁免（整文件 ✗ 有理由）★：这些文件**这一轮不归我改**（Lead 指定的写域）。
#   ★不是"允许写死" ✗ 是"这一轮改不了" ✗ 每条都有替换触发；收口后它们也该 import paths✗★
DOMAIN_FILES = {
    # mod-arch 写域（A3 HTTP 加固／事件 trace／结构第二刀／装 jar）
    "direct.py": "mod-arch 写域（2.56.0 直连通道）：替换触发=收口后 import paths（DSH_GAME_DIR 已同口径）",
    "mcp_core.py": "mod-arch 写域（直连/网关通道）：替换触发=收口后 import paths",
    "install_mod.py": "mod-arch 写域（装 jar 工具）：替换触发=收口后 import paths",
    "mod_http_test.py": "mod-arch 写域（2.56.0 HTTP 判据）：替换触发=收口后 import paths",
    "mod_events_test.py": "mod-arch 写域（事件 trace 判据）：替换触发=收口后 import paths",
    "mod_contract.py": "mod-arch 写域（行为锚）：替换触发=收口后 import paths",
    "mod_arch_test.py": "mod-arch 写域（结构判据）：替换触发=收口后 import paths",
    "human_action_test.py": "mod-arch 写域（手部动画/工具判据）：替换触发=收口后 import paths",
    # docs-gate 写域（D7 文档闸门／发版链／恢复链）
    "doc_consistency_test.py": "docs-gate 写域（D7 文档闸门）：替换触发=收口后 import paths",
    "world_alive.py": "docs-gate 写域（旧 CC 车道→直连改造）：替换触发=收口后 import paths",
    "release.py": "docs-gate 写域（发版链 --check）：替换触发=收口后 import paths",
    "recover.py": "docs-gate 写域（D4 恢复链）：替换触发=收口后 import paths",
    "release_check_test.py": "docs-gate 写域（发版判据）：替换触发=收口后 import paths",
    "recover_test.py": "docs-gate 写域（恢复判据）：替换触发=收口后 import paths",
    "divergence.py": "docs-gate 写域（分歧清单生成器）：替换触发=收口后 import paths",
    "debt_count.py": "docs-gate 写域（欠账计数）：替换触发=收口后 import paths",
    # soak-verify 写域（D3 浸泡套件）
    "d3_soak.py": "soak-verify 写域（D3 浸泡）：替换触发=收口后 import paths",
    "d3_walk_soak.py": "soak-verify 写域（D3 浸泡）：替换触发=收口后 import paths",
    "d3_work_soak.py": "soak-verify 写域（D3 浸泡）：替换触发=收口后 import paths",
    "soak_suite.py": "soak-verify 写域（D3 套件）：替换触发=收口后 import paths",
    "soak_suite_test.py": "soak-verify 写域（D3 判据）：替换触发=收口后 import paths",
    # Lead 写域（闸门本体）
    "check_all.py": "Lead 写域（闸门本体）：替换触发=Lead 合并时 import paths",
}

# ★误报例外（整文件 ✗ 有理由）★：这些文件是**检测器** —— 它们必须写出"禁止出现的模式串"
#   才能扫描别人 ✗ 所以那些字面量是**判据的输入** ✗ 不是"它自己违规"✗★
#   （与 `offline_purity_test.py`／`world_touch_test.py` 的机器白名单同一口径）
FALSE_POSITIVE = {
    "cold_start_test.py": "冷启动判据：模式字符串本身用于**检测**本机绑定（`C:/Users`、`D:/pcl2`、"
                          "实例名、端口等），是扫描器输入 ✗ 不是调用／写死（同 offline_purity 口径）",
    "portability_test.py": "本判据本体：必须写出**禁止出现的模式串**才能判红（同 offline_purity 口径）",
    "export_public.py": "公开快照导出器：要把本机绑定/本机环境文件**列进排除清单** ✗ 清单里的名字是"
                        "检测对象（如 `dsh.env`）✗ 不是它自己用本机路径",
}

CATS = ("abs_path", "instance_name", "save_name", "port")

# ★显式例外表（单独条目）✗★：整文件写域豁免已由 `DOMAIN_FILES` 覆盖；
#   这里只放"单文件里某一类确实该留、但整文件不算写域"的特例（目前没有）。
EXCEPTIONS = {}

# ★实例名/存档名的"已知别名"✗★：除了当前配置值，还抓历史写死过的拼法
_KNOWN_INSTANCE = ("All the Mods 9", "atm9sky", "To the Sky")
_KNOWN_SAVE = ("新的世界",)


def _forbidden(cfg=None) -> dict:
    cfg = cfg or {}
    inst = set(_KNOWN_INSTANCE) | {str(cfg.get("INSTANCE_NAME") or ""),
                                   str(cfg.get("PACK_NAME") or "")}
    save = set(_KNOWN_SAVE) | {str(cfg.get("SAVE_NAME") or "")}
    return {"abs_path": None,
            "instance_name": tuple(sorted(s for s in inst if s)),
            "save_name": tuple(sorted(s for s in save if s)),
            "port": None}


RE_ABS_WIN = re.compile(r"(?<![\w])[A-Za-z]:[\\/](?![\\/])")
RE_ABS_UNIX = re.compile(r"(?<![\w.])/(?:home|Users|root)/")
RE_PORT = re.compile(r"(?<![\w.])(?:8765|8766)(?![\w])")
RE_BOT = re.compile(r"""["']Bot["']""")
# ★存档名的"别名"要防汉语误报✗★（`最新的世界信息` 里也含"新的世界" ✗ 但不是路径）
RE_SAVE_ALIAS = re.compile(r"(?<!最)新的世界(?!信息)")


def classify_line(line: str, cfg=None) -> list:
    """一行文本 ⇒ 命中的类别列表（`abs_path`／`instance_name`／`save_name`／`port`）"""
    forb = _forbidden(cfg)
    hits = []
    if RE_ABS_WIN.search(line) or RE_ABS_UNIX.search(line):
        hits.append("abs_path")
    if any(s in line for s in forb["instance_name"]):
        hits.append("instance_name")
    save_cfg = str((cfg or {}).get("SAVE_NAME") or "")
    if (save_cfg and save_cfg in line) or RE_SAVE_ALIAS.search(line):
        hits.append("save_name")
    if RE_PORT.search(line):
        hits.append("port")
    return hits


def _base(name: str) -> str:
    """展示名（`tools/x.py`／`agent/x.py`／`tools/legacy/x.py`）⇒ 表里用的键"""
    if name in DOMAIN_FILES or name in FALSE_POSITIVE:
        return name
    base = name.rsplit("/", 1)[-1]
    if name.startswith("tools/") and name.count("/") == 1:
        return base
    return name


def scan_sources(sources: dict, cfg=None, exceptions=None,
                 domain: dict | None = None,
                 false_positive: dict | None = None) -> dict:
    """★扫一组源文本✗★（`{展示名: 文本}` ⇒ 违规／例外命中／写域豁免／误报豁免／告警）

    纯函数形态：判据自检能红就靠它（★不碰真文件系统✗★）。
    """
    exceptions = dict(EXCEPTIONS if exceptions is None else exceptions)
    domain = DOMAIN_FILES if domain is None else domain
    fp = FALSE_POSITIVE if false_positive is None else false_positive
    violations, used, warnings = [], set(), {"bot_lines": 0}
    domains = {"hit": {}, "used": set()}
    fps = set()
    for name in sorted(sources):
        if name in ("paths.py", "tools/paths.py"):
            continue                        # ★唯一允许写死环境事实的模块✗★
        key = _base(name)
        for lno, line in enumerate(str(sources[name]).splitlines(), 1):
            cats = classify_line(line, cfg)
            if cats and key in fp:
                fps.add(key)
                continue
            for cat in cats:
                if key in domain:
                    domains["used"].add(key)
                    domains["hit"][key] = domains["hit"].get(key, 0) + 1
                    continue
                if (key, cat) in exceptions:
                    used.add((key, cat))
                    continue
                violations.append({"file": name, "line": lno, "cat": cat,
                                   "snippet": line.strip()[:140]})
            if RE_BOT.search(line):
                warnings["bot_lines"] += 1
    unknown = [k for k in exceptions if k[1] not in CATS]
    stale = sorted(k for k in exceptions if k not in used)
    return {"violations": violations, "violations_n": len(violations),
            "used": sorted(used), "stale": stale, "unknown_cats": unknown,
            "warnings": warnings, "domains": domains, "false_positive_used": sorted(fps)}


def _read_dir(d: pathlib.Path, prefix: str, sources: dict) -> int:
    n = 0
    for p in sorted(d.glob("*.py")):
        try:
            sources[prefix + p.name] = p.read_text(encoding="utf-8", errors="replace")
            n += 1
        except Exception as exc:            # ★不许静默✗★
            print("portability: 读不到 %s（%r）" % (p, exc), file=sys.stderr)
    return n


def collect_sources() -> dict:
    """三个目录的源码（展示名带目录前缀，便于报"文件:行"）"""
    sources = {}
    _read_dir(TOOLS, "tools/", sources)
    _read_dir(AGENT, "agent/", sources)
    _read_dir(LEGACY, "tools/legacy/", sources)
    return sources


def scan_repo(cfg=None) -> dict:
    """扫真实仓库（tools/ ＋ agent/ ＋ tools/legacy/，除 paths.py）"""
    sources = collect_sources()
    out = scan_sources(sources, cfg=cfg)
    out["scanned"] = len(sources)
    out["files"] = sorted(sources)
    out["counts"] = {"tools": len(list(TOOLS.glob("*.py"))),
                     "agent": len(list(AGENT.glob("*.py"))),
                     "legacy": len(list(LEGACY.glob("*.py")))}
    return out


def _sub_env(**over) -> dict:
    """子进程环境：清掉所有环境事实（★验"未配置 ⇒ 明确报错"✗★）"""
    env = dict(os.environ)
    for k in ("MC_HOME", "DSH_GAME_DIR", "DSH_MC_HOME", "SAVE_NAME", "DSH_SAVE_NAME",
              "INSTANCE_NAME", "DSH_INSTANCE_NAME", "PACK_NAME", "DSH_ENV_FILE",
              "DSH_NODE", "DSH_BIN_JS", "DSH_CMD", "DSH_BIN", "DSH_EXE", "DSH_HOME"):
        env.pop(k, None)
    env.update(over)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run(args, env) -> tuple:
    try:
        r = subprocess.run([sys.executable] + args, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", cwd=str(ROOT),
                           env=env, timeout=120)
        return r.returncode, (r.stdout or ""), (r.stderr or "")
    except Exception as exc:                  # ★不许静默✗★
        return 127, "", "%s: %s" % (type(exc).__name__, exc)


# ── 判据 ──────────────────────────────────────────────────────────────────
def main() -> int:
    checks = []
    cfg = {"INSTANCE_NAME": PA.INSTANCE_NAME, "PACK_NAME": PA.PACK_NAME,
           "SAVE_NAME": PA.SAVE_NAME}
    res = scan_repo(cfg=cfg)
    vis = res["violations"]
    scanned = res["scanned"]

    checks.append(("P1~P4 ★绝对路径／实例名／存档名／端口字面量 ⇒ 0 违规（tools＋agent＋legacy）★",
                   res["violations_n"] == 0,
                   "违规 %d 处：%s" % (res["violations_n"],
                                      [(v["file"], v["line"], v["cat"])
                                       for v in vis[:6]])))

    # P5 显式例外表（单条）
    bad5 = []
    for (fname, cat), why in EXCEPTIONS.items():
        if not str(why or "").strip():
            bad5.append((fname, cat, "没理由"))
        if cat not in CATS:
            bad5.append((fname, cat, "类别不在册"))
        if not (TOOLS / fname).is_file():
            bad5.append((fname, cat, "文件不存在"))
    checks.append(("P5 显式例外表：每条有理由＋文件在＋类别在册＋没有过期例外",
                   not bad5 and not res["stale"] and not res["unknown_cats"],
                   "坏条目=%s ｜ 过期=%s ｜ 用到 %d 条"
                   % (bad5[:3] or "无", res["stale"][:4] or "无", len(res["used"]))))

    # P5b 写域豁免表
    bad5b = [(f, why[:20]) for f, why in DOMAIN_FILES.items()
             if not str(why or "").strip()]
    miss5b = [f for f in DOMAIN_FILES if not (TOOLS / f).is_file()]
    checks.append(("P5b 写域豁免表：%d 条每条有理由＋文件都在" % len(DOMAIN_FILES),
                   not bad5b and not miss5b,
                   "无理由=%s ｜ 缺文件=%s ｜ 命中 %d 个文件"
                   % (bad5b[:3] or "无", miss5b[:3] or "无",
                      len(res.get("domains", {}).get("used") or []))))

    # P5c 误报例外表（检测器自带模式串）
    bad5c = [(f, why[:20]) for f, why in FALSE_POSITIVE.items()
             if not str(why or "").strip()]
    # ★必须被用到的只能是"真的含模式串的检测器"✗★（`export_public.py` 只是**可能**含，
    #   当前没扫到 ⇒ 允许未命中 ✗ 但仍在表里给未来兜底✗★）
    must_used = {"cold_start_test.py", "portability_test.py"}
    used_fp = set(res["false_positive_used"])
    checks.append(("P5c 误报例外表：%d 条每条有理由＋文件都在＋真检测器都被用到"
                   % len(FALSE_POSITIVE),
                   not bad5c
                   and all((TOOLS / f).is_file() for f in FALSE_POSITIVE)
                   and must_used <= used_fp
                   and used_fp <= set(FALSE_POSITIVE),
                   "无理由=%s ｜ 命中=%s ｜ 未命中=%s"
                   % (bad5c[:2] or "无", sorted(used_fp),
                      sorted(set(FALSE_POSITIVE) - used_fp) or "无")))

    # P6 配置优先级（纯函数注入）
    prio = []
    tab = {"MC_HOME": r"X:\from-env-file", "BOT_NAME": "FromFile"}
    env = {"MC_HOME": r"Y:\from-env"}
    if PA.resolve("MC_HOME", environ=env, table=tab) != r"Y:\from-env":
        prio.append("env 没赢")
    if PA.resolve("BOT_NAME", environ={}, table=tab) != "FromFile":
        prio.append("dsh.env 没生效")
    if PA.resolve("DSH_PORT", environ={}, table={}) != "8766":
        prio.append("默认没兜住")
    if PA.source_of("MC_HOME", environ=env, table=tab) != "env:MC_HOME":
        prio.append("source_of 不对")
    parsed = PA.parse_env_text("# c\nA=1\nB = two words \nC='quoted'\nexport D=4\nbadline")
    if parsed.get("A") != "1" or parsed.get("B") != "two words" \
            or parsed.get("C") != "quoted" or parsed.get("D") != "4":
        prio.append("env 文本解析不对：%s" % (parsed,))
    checks.append(("P6 ★读取优先级：环境变量 > dsh.env > 默认★（纯函数注入）",
                   not prio, str(prio[:3]) if prio else "3/3 对 ＋ 文本解析对"))

    # P7 paths.py 导出（★含"必须配置"的严格接口✗★）
    need7 = ("MC_HOME", "MODS_DIR", "SAVE_DIR", "SAVES_DIR", "MC_LOG_DIR", "BOT",
             "PORT", "GATEWAY_PORT", "ROOT", "RECIPES_FILE", "TAGS_FILE")
    miss7 = [a for a in need7 if not hasattr(PA, a)]
    strict7 = [n for n in ("require", "require_home", "require_save_dir",
                           "require_node", "require_dsh_bin_js") if not callable(getattr(PA, n, None))]
    checks.append(("P7 paths.py 导出关键常量 ＋ 严格接口（%d 个）" % len(need7),
                   not miss7 and not strict7 and callable(getattr(PA, "health_url", None)),
                   "缺=%s ｜ 缺严格接口=%s" % (miss7 or "无", strict7 or "无")))

    # P8 迁移覆盖（tools ≥20 ＋ agent 两个都迁）
    srcs = collect_sources()
    migrated = sorted(n for n, t in srcs.items()
                      if re.search(r"^\s*(?:import|from)\s+[^\n]*\bpaths\b", t, re.M)
                      or " paths as PA" in t)
    migrated_tools = [n for n in migrated if n.startswith("tools/")
                      and n.count("/") == 1]
    agent_migrated = [n for n in migrated if n.startswith("agent/")]
    checks.append(("P8 迁移覆盖：tools ≥20 个 import paths ＋ agent 2/2",
                   len(migrated_tools) >= 20
                   and "agent/channel.py" in agent_migrated
                   and "agent/world.py" in agent_migrated,
                   "tools 已迁 %d ｜ agent=%s" % (len(migrated_tools), agent_migrated)))

    # P9 ★自检能红★：合成源文本
    clean = {"tools/a.py": "import paths as PA\nx = PA.MC_HOME\n"}
    dirty = {"tools/b.py": 'P = r"D:\\games\\x"\nQ = "All the Mods 9"\n'
                            'S = "新的世界"\nPORT = 8766\nexc_ok = 1\n',
             "agent/c.py": "C:\\Users\\x\\y\n"}
    exc = {("b.py", "abs_path"): "测试例外（有理由）",
           ("b.py", "instance_name"): "测试例外",
           ("b.py", "save_name"): "测试例外",
           ("b.py", "port"): "测试例外"}
    test_cfg = {"INSTANCE_NAME": "All the Mods 9", "SAVE_NAME": "新的世界"}
    r_clean = scan_sources(clean, cfg=test_cfg, exceptions={})
    r_dirty = scan_sources(dirty, cfg=test_cfg, exceptions={})
    r_exc = scan_sources({"tools/b.py": dirty["tools/b.py"]}, cfg=test_cfg, exceptions=exc)
    r_paths = scan_sources({"tools/paths.py": 'P = r"D:\\games\\x"\nPORT = 8766\n'},
                           cfg={}, exceptions={})
    r_fp = scan_sources({"tools/detector_test.py": 'P = r"D:\\games\\x"\n'},
                        cfg={}, domain={}, false_positive={"detector_test.py": "检测器"})
    cats_dirty = {v["cat"] for v in r_dirty["violations"]}
    selfred = (r_clean["violations_n"] == 0
               and r_dirty["violations_n"] >= 4
               and {"abs_path", "instance_name", "save_name", "port"} <= cats_dirty
               and r_dirty["violations"][0]["file"] in ("agent/c.py", "tools/b.py")
               and r_exc["violations_n"] == 0 and len(r_exc["used"]) == 4
               and r_paths["violations_n"] == 0
               and r_fp["violations_n"] == 0
               and r_fp["false_positive_used"] == ["detector_test.py"])
    checks.append(("P9 ★自检能红★：合成违规四类全抓到／干净不误报／例外＋误报表能吃掉／paths.py 豁免",
                   selfred,
                   "dirty=%d 类=%s 例外后=%d 误报表=%d"
                   % (r_dirty["violations_n"], sorted(cats_dirty),
                      r_exc["violations_n"], r_fp["violations_n"])))

    # P10 ★未配置 ⇒ 明确报错（不静默用本机路径）★
    bad10 = []
    with tempfile.TemporaryDirectory() as td:
        noenv = str(pathlib.Path(td) / "no_such_dsh.env")
        e10 = _sub_env(DSH_ENV_FILE=noenv)
        rc, out, err = _run(["-c", "import sys; sys.path.insert(0, r'%s'); "
                                   "import paths as PA; print(PA.require('MC_HOME'))"
                             % str(TOOLS)], e10)
        if rc == 0 or "未配置" not in (out + err) or "D:\\pcl2" in (out + err):
            bad10.append(("paths.require", rc, (out + err)[:120]))
        rc2, out2, err2 = _run(["-c", "import sys; sys.path.insert(0, r'%s'); "
                                      "import channel" % str(AGENT)], e10)
        if rc2 == 0 or "NotConfigured" not in (out2 + err2) \
                or "D:\\pcl2" in (out2 + err2):
            bad10.append(("agent.channel", rc2, (out2 + err2)[:120]))
        # ★配了但**路径不存在**也必须明确报错✗★（不是"配了就算通"）
        e10b = _sub_env(DSH_ENV_FILE=noenv, MC_HOME=r"Q:\no_such_mc_home",
                        SAVE_NAME="saves")
        rc2b, out2b, err2b = _run(["-c", "import sys; sys.path.insert(0, r'%s'); "
                                         "import channel" % str(AGENT)], e10b)
        if rc2b == 0 or "不存在" not in (out2b + err2b) \
                or "D:\\pcl2" in (out2b + err2b):
            bad10.append(("agent.channel_bad_path", rc2b, (out2b + err2b)[:120]))
        # 已配置时（本机 dsh.env 在）require 必须给出真实值而不是占位
        if PA.configured():
            rc3, out3, err3 = _run(["-c", "import sys; sys.path.insert(0, r'%s'); "
                                          "import paths as PA; print(PA.require('MC_HOME'))"
                                    % str(TOOLS)], _sub_env())
            if rc3 != 0 or "未配置" in out3 or not out3.strip():
                bad10.append(("configured", rc3, out3[:120]))
        # 大脑层：dsh_cli 找不到时**明确报**（不静默）
        try:
            import dsh_cli
            real = dsh_cli.find_dsh
            dsh_cli.find_dsh = lambda: None
            buf = io.StringIO()
            got = dsh_cli.find_dsh_or_report(stream=buf)
            dsh_cli.find_dsh = real
            if got is not None or "需要配置 DSH_CMD" not in buf.getvalue():
                bad10.append(("dsh_cli.report", got, buf.getvalue()[:120]))
        except Exception as exc:              # ★不许静默✗★
            bad10.append(("dsh_cli.import", "exc", "%r" % (exc,)))
    checks.append(("P10 ★未配置 ⇒ 明确报错（不静默用本机路径）★：paths.require／agent／大脑层",
                   not bad10, str(bad10[:3]) or "没配：require 抛／agent 抛／dsh_cli 提示｜已配置：给出真值"))

    # P11 dsh.env.example（公开模板）
    #   ★端口默认值允许出现✗★（8766/8765 是协议默认 ✗ 不是某台机器的环境事实）
    ex = ROOT / "dsh.env.example"
    bad11 = []
    text11 = ""
    if not ex.is_file():
        bad11.append("example 不在：%s" % ex)
    else:
        text11 = ex.read_text(encoding="utf-8", errors="replace")
        for cat in classify_line(text11, cfg):
            if cat == "port":
                continue
            bad11.append("example 里有 %s 字面量" % cat)
        for key in ("MC_HOME", "INSTANCE_NAME", "PACK_NAME", "SAVE_NAME",
                    "BOT_NAME", "DSH_PORT", "GATEWAY_PORT", "DSH_EXE",
                    "DSH_NODE", "DSH_BIN_JS"):
            if key not in text11:
                bad11.append("缺配置项 %s" % key)
        if "<" not in text11:
            bad11.append("没有占位符（值应写 <...>）")
        if "D:\\pcl2" in text11 or "C:\\Users" in text11:
            bad11.append("含真路径")
    checks.append(("P11 dsh.env.example：占位符化＋全部配置项＋不含真路径",
                   not bad11, str(bad11[:4]) or "example 合规"))

    # P12 计数器
    cnt = res["counts"]
    checks.append(("P12 ★计数器：三个目录都真的扫了✗★",
                   scanned == cnt["tools"] + cnt["agent"] + cnt["legacy"]
                   and cnt["agent"] >= 2 and cnt["legacy"] >= 15,
                   "扫过 %d（tools=%d agent=%d legacy=%d）"
                   % (scanned, cnt["tools"], cnt["agent"], cnt["legacy"])))

    # W1 BOT 字面量
    bot_total = res["warnings"]["bot_lines"]
    bot_files = len([n for n, t in srcs.items() if RE_BOT.search(t)])
    checks.append(("W1 BOT 字面量（告警级，不算红；未迁移项见报告）",
                   True, "%d 处／%d 个文件（冻结面默认参数，保留字面量）"
                   % (bot_total, bot_files)))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s ｜ %s" % (name, "✓" if ok else "✗", str(detail)[:150]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => portability 有红（%d 项不对）" % bad)
        print("PORTABILITY ok=0 scanned=%d violations=%d exceptions=%d warnings=%d"
              % (scanned, res["violations_n"], len(res["used"]), bot_total))
        return 1
    print("  => portability 全绿（★环境事实只在 paths.py ✗ 例外表每条有理由 ✗ 未配置明确报错✗★）")
    print("PORTABILITY ok=1 scanned=%d violations=0 exceptions=%d warnings=%d"
          % (scanned, len(res["used"]), bot_total))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

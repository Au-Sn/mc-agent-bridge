#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""world_profile.py -- ★世界档案（跨整合包）单一入口✗★：换包/换存档只改这一个文件（2026-11-03 ✓）

WHY（用户口径 2026-11-03）：
  「哪怕是一个勉强能用的，也不能只在一个 1.20.1 的 ATM9 整合包里运行。」
  查过：模组源码 0 处整合包引用；`tools/*.py` 里也没有具体 mod 关键词 ⇒ **代码不绑定 ATM9**。
  真正绑死的是两类东西：
    ① **世界常量**（重生锚点／浸泡锚点／测试平台／不可挖区域／契约夹具路径）
       —— 以前散落在 `recover.py`、`soak_suite.py`、`human_action_test.py`… 各写各的；
    ② **离线数据**（配方/标签/例外/导出快照）—— 从当前整合包导出生成（见 `tools/bootstrap.py`）。
  这份模块把 ① 收成**一个可读文件** `state/world_profile.json`；没有它就**明确说'没有'**，
  ★绝不在读取路径里静默用本机 ATM9 默认✗★（"看不见的默认值"是换包第一杀手）。

读取优先级（`resolve_anchor`）：显式 CLI ＞ 环境变量 ＞ `state/world_profile.json` ＞ 报错/返回 None。
（最后一档**不给**本机默认；调用方想保留旧默认，必须自己打印"用默认锚点（本机世界）"。）

文件形状（schema `dshbridge/world_profile@1`）：
  {
    "schema": "dshbridge/world_profile@1",
    "pack_name": "本机整合包名（人读）",
    "anchor": [x, y, z],                 # 重生/回锚点（recover 用）
    "soak_anchor": [x, y, z],            # 浸泡/长跑锚点（soak_suite 默认 --anchor 用）
    "test_platform": {                   # 测试平台（虚空平台/专用平台）
        "center": [x, y, z], "radius": 3, "box": [x0, y0, z0, x1, y1, z1]
    },
    "no_dig_zones": [                    # 不可挖区域（家/屋/机器…）
        {"name": "...", "box": [x0, y0, z0, x1, y1, z1], "why": "..."}
    ],
    "contract_fixture": "state/contracts",   # 契约夹具目录（相对仓库根，禁止绝对路径）
    "notes": "人读备注（换包要改哪些）"
  }

用法：
  py tools/world_profile.py --show          # 读当前档案（缺失 exit 2，不算坏）
  py tools/world_profile.py --init          # 把**本机当前世界**的值写成示例（已存在且不同 ⇒ 拒绝覆盖）
  py tools/world_profile.py --init --force  # 明确要求覆盖
  py tools/world_profile.py --file tmp/x.json --show
本模块**只读文件/只写 --init 指定的档案**；不连游戏、不写世界、不改其它状态。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SCHEMA = "dshbridge/world_profile@1"
FILENAME = "state/world_profile.json"
DEFAULT_PATH = ROOT / "state" / "world_profile.json"

KIND_ENV = {"anchor": "DSH_WORLD_ANCHOR", "soak_anchor": "DSH_SOAK_ANCHOR"}
KIND_LABEL = {"anchor": "重生锚点 anchor", "soak_anchor": "浸泡锚点 soak_anchor"}

# 本机绝对路径/用户目录：档案里一律不许出现（换台电脑必错）
RE_ABS_WIN = re.compile(r"(?<![\w])[A-Za-z]:[\\/](?![\\/])")
RE_ABS_UNIX = re.compile(r"(?<![\w.])/(?:home|Users|root)/")

# 【示例值】= 本机当前（ATM9）世界的实测值，只在 --init 写示例时用；
# ★读取路径不会用它们✗★（没有档案就返回 None + 原因）
EXAMPLE_ANCHOR = (4121, 71, 16)          # 家/屋外侧安全落脚（recover 旧默认）
EXAMPLE_SOAK_ANCHOR = (4152, 71, 13)     # 虚空平台中心（soak_suite 平台档）
EXAMPLE_PLATFORM = {"center": [4152, 71, 13], "radius": 3,
                    "box": [4145, 70, 2, 4160, 72, 17]}
EXAMPLE_NO_DIG = [
    {"name": "家", "box": [4115, 71, 19, 4129, 79, 32], "why": "这是家，挖了就没地方住"},
    {"name": "CC计算机", "box": [4119, 71, 10, 4119, 71, 10], "why": "桥接计算机，挖了整条链路就断"},
]
EXAMPLE_CONTRACT = "state/contracts"


def _rel(p) -> str:
    try:
        return str(Path(p).resolve().relative_to(ROOT)).replace("\\", "/")
    except Exception:
        return str(p).replace("\\", "/")


def has_abs_path(text: str) -> bool:
    """★档案不许带本机绝对路径✗★（本机盘符／用户主目录）；命中 ⇒ 换机必坏"""
    return bool(RE_ABS_WIN.search(str(text)) or RE_ABS_UNIX.search(str(text)))


def _example_pack_name() -> str:
    """当前整合包名（从 paths/dsh.env 读，不在本模块写死）"""
    try:
        import paths as PA
        name = str(PA.PACK_NAME or "").strip()
        if name:
            return name
    except Exception as exc:                      # ★不许静默✗★
        print("world_profile: 读 paths.PACK_NAME 失败 %r ⇒ 用占位名" % (exc,),
              file=sys.stderr)
    return "本机整合包（换包请改）"


def example_document() -> dict:
    """★示例档案✗★：本机当前世界的值 ＋ 明确标注'示例，换包请改'"""
    return {
        "schema": SCHEMA,
        "pack_name": _example_pack_name(),
        "anchor": list(EXAMPLE_ANCHOR),
        "soak_anchor": list(EXAMPLE_SOAK_ANCHOR),
        "test_platform": {
            "center": list(EXAMPLE_PLATFORM["center"]),
            "radius": int(EXAMPLE_PLATFORM["radius"]),
            "box": list(EXAMPLE_PLATFORM["box"]),
        },
        "no_dig_zones": [
            {"name": z["name"], "box": list(z["box"]), "why": z["why"]}
            for z in EXAMPLE_NO_DIG
        ],
        "contract_fixture": EXAMPLE_CONTRACT,
        "notes": ("示例（由本机当前世界实测值生成）：换整合包/换存档后必须改 "
                  "anchor/soak_anchor/test_platform/no_dig_zones；"
                  "本文件禁止写本机绝对路径；换机先跑一次本工具 --init 再按新世界改。"),
    }


def _as_point(value, name):
    """解析 x,y,z：接受 [x,y,z] / (x,y,z) / 'x y z' / 'x,y,z'"""
    if isinstance(value, (list, tuple)):
        parts = list(value)
    elif isinstance(value, str):
        parts = [v for v in re.split(r"[,\s]+", value.strip()) if v]
    else:
        raise ValueError("%s 必须是 [x,y,z] 或 'x y z'（实际 %r）" % (name, value))
    if len(parts) != 3:
        raise ValueError("%s 必须是三个整数（实际 %r）" % (name, value))
    out = []
    for v in parts:
        if isinstance(v, bool):
            raise ValueError("%s 不许用布尔值" % name)
        out.append(int(v))
    return tuple(out)


def _as_int(value, name):
    if isinstance(value, bool):
        raise ValueError("%s 不许用布尔值" % name)
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError("%s 必须是整数（实际 %r）" % (name, value)) from None


def _as_box(value, name):
    if isinstance(value, str):
        parts = [v for v in re.split(r"[,\s]+", value.strip()) if v]
    elif isinstance(value, (list, tuple)):
        parts = list(value)
    else:
        raise ValueError("%s 必须是 [x0,y0,z0,x1,y1,z1]（实际 %r）" % (name, value))
    if len(parts) != 6:
        raise ValueError("%s 必须是六个整数（实际 %r）" % (name, value))
    box = [_as_int(v, name) for v in parts]
    if box[0] > box[3] or box[1] > box[4] or box[2] > box[5]:
        raise ValueError("%s 的 min 大于 max：%r" % (name, box))
    return box


def _walk_strings(value):
    """递归取出所有字符串值（判"档案里有没有本机绝对路径"用；json.dumps 会把 \\ 转义，
    直接扫序列化文本会漏掉 `盘符:\\...`，所以必须在**原始值**上扫）"""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            if isinstance(k, str):
                yield k
            yield from _walk_strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _walk_strings(v)


def validate(doc) -> list:
    """字段校验 ⇒ 错误列表（空 = 合法）。★不读盘、不猜默认✗★"""
    errors = []
    if not isinstance(doc, dict):
        return ["档案必须是 JSON 对象（实际 %r）" % type(doc).__name__]
    if doc.get("schema") != SCHEMA:
        errors.append("schema 必须是 %r（实际 %r）" % (SCHEMA, doc.get("schema")))
    pack = doc.get("pack_name")
    if not isinstance(pack, str) or not pack.strip():
        errors.append("pack_name 必须是非空字符串")
    if "notes" in doc and not isinstance(doc["notes"], str):
        errors.append("notes 必须是字符串")
    # 两个锚点
    for kind in ("anchor", "soak_anchor"):
        try:
            box = _as_point(doc.get(kind), kind)
            if not all(-30000000 <= v <= 30000000 for v in box):
                errors.append("%s 数值超出世界范围：%r" % (kind, box))
        except ValueError as exc:                   # ★明确报错✗ 不静默✗★
            errors.append(str(exc))
    # 测试平台
    tp = doc.get("test_platform")
    if not isinstance(tp, dict):
        errors.append("test_platform 必须是对象 {center,radius,box}")
    else:
        try:
            _as_point(tp.get("center"), "test_platform.center")
        except ValueError as exc:
            errors.append(str(exc))
        try:
            r = _as_int(tp.get("radius"), "test_platform.radius")
            if not 1 <= r <= 64:
                errors.append("test_platform.radius 必须在 1..64（实际 %r）" % r)
        except ValueError as exc:
            errors.append(str(exc))
        if "box" in tp:
            try:
                _as_box(tp.get("box"), "test_platform.box")
            except ValueError as exc:
                errors.append(str(exc))
    # 不可挖区域
    zones = doc.get("no_dig_zones")
    if not isinstance(zones, list):
        errors.append("no_dig_zones 必须是列表")
    else:
        for i, z in enumerate(zones):
            if not isinstance(z, dict):
                errors.append("no_dig_zones[%d] 必须是对象" % i)
                continue
            if not isinstance(z.get("name"), str) or not z.get("name", "").strip():
                errors.append("no_dig_zones[%d].name 必须是非空字符串" % i)
            try:
                _as_box(z.get("box"), "no_dig_zones[%d].box" % i)
            except ValueError as exc:
                errors.append(str(exc))
    # 契约夹具：相对路径
    cf = doc.get("contract_fixture")
    if not isinstance(cf, str) or not cf.strip():
        errors.append("contract_fixture 必须是相对路径字符串")
    else:
        cf = cf.strip()
        if has_abs_path(cf) or cf.startswith("/") or cf.startswith("\\"):
            errors.append("contract_fixture 必须是**相对**仓库根的路径（实际 %r）" % cf)
        if ".." in cf.replace("\\", "/").split("/"):
            errors.append("contract_fixture 不许用 .. 跳出仓库（实际 %r）" % cf)
    # 全局：任何字段都不许带本机绝对路径（★在原始值上扫✗★：json.dumps 会把 \ 转义，
    # 直接扫序列化文本会漏掉 "盘符:\..." 这种 2026-11-03 实测踩到的假绿）
    absolute_hit = [s for s in _walk_strings(doc) if has_abs_path(s)]
    if absolute_hit:
        errors.append("档案里出现本机绝对路径（盘符/用户主目录）⇒ 换台电脑必坏：%r"
                      % absolute_hit[0][:120])
    try:
        text = json.dumps(doc, ensure_ascii=False)
    except (TypeError, ValueError) as exc:          # ★明确报错✗★
        errors.append("档案无法序列化（%r）" % (exc,))
    else:
        if has_abs_path(text):
            errors.append("档案里出现本机绝对路径（盘符/用户主目录）⇒ 换台电脑必坏")
    return errors


def load(path=None) -> tuple:
    """读档案 ⇒ (doc|None, 原因/ok)。★文件不存在不创建、不兜底本机默认✗★"""
    p = Path(path) if path else DEFAULT_PATH
    if not p.is_file():
        return None, ("无世界档案：%s 不存在 —— ★不静默用本机默认✗★；"
                      "换包/新机器先跑 `py tools/world_profile.py --init` 再按新世界改值"
                      % _rel(p))
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:                          # ★不许静默✗★
        return None, "世界档案读不出来（%s）：%r ⇒ 不兜底" % (_rel(p), exc)
    try:
        doc = json.loads(text)
    except ValueError as exc:                       # ★明确失败✗ 不静默✗★
        return None, "世界档案不是合法 JSON（%s）：%s ⇒ 不兜底" % (_rel(p), str(exc)[:200])
    errors = validate(doc)
    if errors:
        return None, "世界档案字段有问题（%s）：%s ⇒ 不兜底" % (_rel(p), "；".join(errors[:6]))
    return doc, "ok"


def _env_value(kind: str, env) -> str:
    names = [KIND_ENV[kind]]
    if kind == "soak_anchor":
        names.append("DSH_WORLD_ANCHOR")   # 未单配浸泡锚点 ⇒ 可复用世界锚点
    src = os.environ if env is None else env
    for n in names:
        v = str((src or {}).get(n) or "").strip()
        if v:
            return v
    return ""


def resolve_anchor(kind: str = "anchor", cli=None, path=None, env=None) -> tuple:
    """★锚点解析（唯一口径）✗★ ⇒ (tuple|None, 来源, 说明)

    优先级：显式 CLI ＞ 环境变量 ＞ world_profile ＞ None（★不给本机默认✗★）。
    来源 ∈ {"cli", "env", "profile", "none"}；CLI/环境变量解析失败 ⇒ 抛 ValueError。
    """
    if kind not in KIND_ENV:
        raise ValueError("kind 必须是 %s（实际 %r）" % (sorted(KIND_ENV), kind))
    if cli is not None and str(cli).strip():
        return (_as_point(cli, "--%s（CLI）" % kind), "cli", "来自显式 CLI")
    envv = _env_value(kind, env)
    if envv:
        return (_as_point(envv, KIND_ENV[kind]), "env", "来自环境变量 %s" % KIND_ENV[kind])
    doc, reason = load(path)
    if doc is None:
        return (None, "none", reason)
    want = doc.get(kind)
    if want is None and kind == "soak_anchor":
        want = doc.get("anchor")
    if want is None:
        return (None, "none", "世界档案里没有 %s" % kind)
    return (tuple(_as_point(want, kind)), "profile",
            "来自世界档案 %s" % _rel(path or DEFAULT_PATH))


def write_example(path=None, force: bool = False) -> tuple:
    """★--init✗★：把本机当前世界的值写成示例文件 ⇒ (exit, 动作, 路径/说明)

    幂等：已存在且内容一字不差 ⇒ 动作 "unchanged"（exit 0，不重写）；
    已存在但内容不同 ⇒ 拒绝覆盖（exit 1），除非 force=True。
    """
    p = Path(path) if path else DEFAULT_PATH
    doc = example_document()
    text = json.dumps(doc, ensure_ascii=False, indent=1) + "\n"
    if p.is_file():
        try:
            old = p.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:                      # ★不许静默✗★
            return 1, "read_failed", "读不了已存在的 %s：%r" % (_rel(p), exc)
        if old == text:
            return 0, "unchanged", "已初始化，内容一致（未重写）"
        if not force:
            return 1, "exists", ("%s 已存在且内容不同 ⇒ 拒绝覆盖（加 --force 才覆盖；"
                                 "这防把改好的世界值冲掉）" % _rel(p))
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    except OSError as exc:                          # ★不许静默✗★
        return 1, "write_failed", "写不了 %s：%r" % (_rel(p), exc)
    return 0, "written", _rel(p)


def _fmt_pt(v) -> str:
    try:
        return "%d,%d,%d" % _as_point(v, "point")
    except ValueError:
        return str(v)


def describe(doc) -> str:
    tp = doc.get("test_platform") or {}
    zones = doc.get("no_dig_zones") or []
    lines = [
        "== world_profile: %s ==" % _rel(DEFAULT_PATH),
        "  schema      : %s" % doc.get("schema"),
        "  pack_name   : %s" % doc.get("pack_name"),
        "  anchor      : %s" % _fmt_pt(doc.get("anchor")),
        "  soak_anchor : %s" % _fmt_pt(doc.get("soak_anchor")),
        "  test_platform: center=%s radius=%s box=%s"
        % (_fmt_pt(tp.get("center")), tp.get("radius"), tp.get("box")),
        "  no_dig_zones: %d 个（%s）"
        % (len(zones), "、".join(str(z.get("name")) for z in zones[:4])),
        "  contract    : %s" % doc.get("contract_fixture"),
        "  notes       : %s" % str(doc.get("notes") or "")[:160],
    ]
    return "\n".join(lines)


def machine_line(doc, path=None) -> str:
    tp = doc.get("test_platform") or {}
    return ("WORLDPROFILE ok=1 schema=%s file=%s pack=%s anchor=%s soak=%s "
            "platform_radius=%s zones=%d contract=%s"
            % (doc.get("schema"), _rel(path or DEFAULT_PATH), doc.get("pack_name"),
               _fmt_pt(doc.get("anchor")), _fmt_pt(doc.get("soak_anchor")),
               tp.get("radius"), len(doc.get("no_dig_zones") or []),
               doc.get("contract_fixture")))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="世界档案（跨整合包）：读/写 state/world_profile.json；无档案不静默兜底")
    ap.add_argument("--file", default=str(DEFAULT_PATH),
                    help="档案路径（默认 state/world_profile.json）")
    ap.add_argument("--show", action="store_true", help="显示当前档案（默认动作）")
    ap.add_argument("--check", action="store_true", help="只校验（同 --show 的退出码）")
    ap.add_argument("--init", action="store_true",
                    help="把本机当前世界的值写成示例文件（示例，换包请改）")
    ap.add_argument("--force", action="store_true", help="--init 时允许覆盖已存在的档案")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    ns = ap.parse_args(argv)
    path = Path(ns.file)

    if ns.init:
        code, action, detail = write_example(path, force=ns.force)
        if ns.json:
            print(json.dumps({"ok": code == 0, "action": action, "file": _rel(path),
                              "detail": detail}, ensure_ascii=False, indent=1))
        else:
            print("WORLDPROFILE ok=%d action=%s file=%s detail=%s"
                  % (1 if code == 0 else 0, action, _rel(path), detail))
        if code == 0 and action == "written":
            print("  ★这是**示例**✗★：换整合包/换存档后必须改 anchor/soak_anchor/"
                  "test_platform/no_dig_zones ⇒ 再跑 --show 自检")
        return code

    doc, reason = load(path)
    if doc is None:
        exists = path.is_file()
        if ns.json:
            print(json.dumps({"ok": False, "file": _rel(path), "exists": exists,
                              "reason": reason}, ensure_ascii=False, indent=1))
        else:
            print("WORLDPROFILE ok=0 file=%s reason=%s"
                  % (_rel(path), "invalid" if exists else "no_file"))
            print("  " + reason)
            if not exists:
                print("  ⇒ 这不是失败，是'还没配'（INCONCLUSIVE）；新机器/换包："
                      "`py tools/world_profile.py --init` 然后按新世界改值")
        return 1 if exists else 2

    if ns.json:
        print(json.dumps({"ok": True, "file": _rel(path), "profile": doc},
                         ensure_ascii=False, indent=1))
    else:
        if not ns.check:
            print(describe(doc))
        print(machine_line(doc, path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

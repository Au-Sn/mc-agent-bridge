#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""paths.py -- ★解绑的唯一入口✗★：环境事实（路径／实例名／存档名／bot 名／端口）只在这里出现

规格（docs/评估四-解绑与优先级.md 的 P0；发版准备 task-14 收尾）：
  * 环境事实 = `dsh.env` ＋ 本模块；仓库只跟踪 **`dsh.env.example`**（模板），
    `dsh.env` 是本机配置（不进库）；
  * 读取优先级：★环境变量 > `dsh.env` > 内置默认★；
    ★机器相关项**没有本机默认**✗★ —— 未配置时**明确报错/告警**（`NotConfigured` ＋ hint），
    **绝不静默回退到某台电脑的绝对路径**；
  * ★除本模块（与 `portability_test.py` 的显式例外表）外，`tools/*.py`／`agent/*.py`／
    `tools/legacy/*.py` 不许再出现绝对路径／实例名／存档名／端口字面量★。

三层接缝：
  * **游戏工具**（tools/*.py）：`PA.MC_HOME／PA.MODS_DIR／PA.SAVE_DIR…`（未配置 ⇒ 告警＋占位路径）
  * **agent/**（agent/channel.py／world.py）：`PA.require(...)` ⇒ 未配置**直接抛** `NotConfigured`
  * **大脑层**（acp_serve／dsh_acp／dsh_live／dsh_cli…）：`PA.require_node()`／
    `PA.require_dsh_bin_js()`／`PA.find_dsh()` ⇒ 未配置时打印"需要配置 …"并非零退出

命名约定（★别混✗★）：
  * `LOG_DIR`  ＝ **仓库自己的** `logs/`；`MC_LOG_DIR`／`LATEST_LOG` ＝ **游戏实例的** `logs/`

用法：
    import paths as PA
    PA.MC_HOME / PA.MODS_DIR / PA.SAVE_DIR / PA.BOT / PA.PORT / PA.GATEWAY_PORT
    PA.require("MC_HOME") / PA.configured() / PA.describe()（诊断，不抛）
"""
from __future__ import annotations

import os
import pathlib
import shutil
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOOLS_DIR = ROOT / "tools"
AGENT_DIR = ROOT / "agent"
STATE_DIR = ROOT / "state"
JOBS_DIR = ROOT / "jobs"
BUILD_DIR = ROOT / "build"
LOG_DIR = ROOT / "logs"                 # ★仓库自己的日志目录（不是游戏实例的 logs）
DOCS_DIR = ROOT / "docs"
CONTRACTS_DIR = STATE_DIR / "contracts"
EXPORT_SNAPSHOTS_DIR = STATE_DIR / "export_snapshots"
BRIDGE_DIR = ROOT / "bridge"
MOD_DIR = ROOT / "mod"

ENV_FILE_ENV = "DSH_ENV_FILE"           # 可指向别的 dsh.env（判据/多实例用）
DSH_ENV_FILE = pathlib.Path(os.environ.get(ENV_FILE_ENV) or (ROOT / "dsh.env"))
DSH_ENV_EXAMPLE = ROOT / "dsh.env.example"

UNCONFIGURED_HINT = (
    "未配置环境事实：请 `cp dsh.env.example dsh.env` 后按本机情况填写"
    "（或设环境变量 MC_HOME／SAVE_NAME 等）"
)

# ── 可读环境事实的默认值（★只在本文件出现 ✗ 别处一律 import✗★）─────────────
#   ★机器相关项**故意留空**✗★：没有"某台电脑的默认路径"，未配置就报错/告警。
_DEFAULTS = {
    "MC_HOME": "",                      # 必须配置（实例目录）
    "INSTANCE_NAME": "",                # 建议配置（人读；doctor 核对）
    "PACK_NAME": "",                    # 可选（人读）
    "SAVE_NAME": "",                    # 必须配置（存档目录名；agent 的磁盘后备通道要它）
    "BOT_NAME": "Bot",                  # 协议默认名
    "DSH_PORT": "8766",                 # 模组直连 HTTP（/cmd /health）
    "GATEWAY_PORT": "8765",             # 旧网关／CC 车道
    "MOD_VERSION_FILE": "mod/gradle.properties",
    "HTTP_TOKEN_FILE": "",              # 可空 ⇒ 走默认候选
    "DSH_EXE": "",                      # 可空 ⇒ 走 PATH／常见位置
    "NODE_EXE": "",                     # 可空 ⇒ 走 PATH／常见位置（大脑层）
    "DSH_BIN_JS": "",                   # 可空 ⇒ 走 npm 缓存（大脑层）
}

# ★同一个事实允许多个环境变量名（★兼容既有代码：direct.py 用 DSH_GAME_DIR✗★）
_ALIASES = {
    "MC_HOME": ("MC_HOME", "DSH_GAME_DIR", "DSH_MC_HOME"),
    "BOT_NAME": ("BOT_NAME", "DSH_BOT_NAME", "DSH_BOT"),
    "DSH_PORT": ("DSH_PORT", "DSH_CMD_PORT"),
    "GATEWAY_PORT": ("GATEWAY_PORT", "DSH_GATEWAY_PORT"),
    "SAVE_NAME": ("SAVE_NAME", "DSH_SAVE_NAME"),
    "INSTANCE_NAME": ("INSTANCE_NAME", "DSH_INSTANCE_NAME"),
    "HTTP_TOKEN_FILE": ("HTTP_TOKEN_FILE", "DSH_HTTP_TOKEN_FILE"),
    "DSH_EXE": ("DSH_EXE", "DSH_DSH_EXE", "DSH_CMD"),
    "NODE_EXE": ("NODE_EXE", "DSH_NODE"),
    "DSH_BIN_JS": ("DSH_BIN_JS", "DSH_ACP_BIN"),
    "MOD_VERSION_FILE": ("MOD_VERSION_FILE", "DSH_MOD_VERSION_FILE"),
}

REQUIRED_KEYS = ("MC_HOME", "SAVE_NAME")


class NotConfigured(RuntimeError):
    """★环境事实没配✗★（不是"文件读坏了" ✗ 是"这台机器还没告诉我们在哪"✗★）"""


_warned = set()


def _warn_unconfigured(what: str) -> None:
    """未配置时的**明确**告警（★一次一条 ✗ 不刷屏✗★）"""
    if what in _warned:
        return
    _warned.add(what)
    print("paths: ★未配置 %s✗★ — %s（本次返回占位路径，**不是**本机路径）"
          % (what, UNCONFIGURED_HINT), file=sys.stderr)


def parse_env_text(text: str) -> dict:
    """★解析 `dsh.env`（KEY=VALUE ✗ 行首 # 注释 ✗ 值可带空格✗★）

    ★不吞坏行✗★：不像 KEY=VALUE 的行记进 `_bad_lines`（由 describe/doctor 看见）。
    """
    out = {}
    for raw in str(text or "").splitlines():
        ln = raw.strip()
        if not ln or ln.startswith("#"):
            continue
        if ln.lower().startswith("export "):
            ln = ln[7:].strip()
        if "=" not in ln:
            out.setdefault("_bad_lines", []).append(raw[:120])
            continue
        key, _, val = ln.partition("=")
        key = key.strip()
        if not key:
            out.setdefault("_bad_lines", []).append(raw[:120])
            continue
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        out[key] = val
    return out


def load_env_file(path=None) -> dict:
    """读 `dsh.env`（或 `DSH_ENV_FILE` 指向的文件）；不存在/读不动 ⇒ 空表 ＋ stderr 告警"""
    p = pathlib.Path(path) if path else DSH_ENV_FILE
    if not p.is_file():
        return {}
    try:
        return parse_env_text(p.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:                  # ★不许静默✗★
        print("paths: 读 %s 失败 %r（按空处理）" % (p, exc), file=sys.stderr)
        return {}


_ENV_TABLE = None


def env_table() -> dict:
    """当前生效的 `dsh.env` 表（首次读盘后缓存）"""
    global _ENV_TABLE
    if _ENV_TABLE is None:
        _ENV_TABLE = load_env_file()
    return _ENV_TABLE


def reload_env(path=None) -> dict:
    """重读 `dsh.env`（换配置/判据用；返回新表）"""
    global _ENV_TABLE
    _ENV_TABLE = load_env_file(path)
    return _ENV_TABLE


def resolve(key: str, default=None, environ=None, table=None) -> str:
    """★读取优先级✗★：环境变量（含别名） > `dsh.env`（含别名） > 默认

    ★纯函数形态✗★（可注入 environ/table ⇒ 判据能离线验优先级，不碰真环境/真文件）。
    """
    names = _ALIASES.get(key, (key,))
    env = os.environ if environ is None else environ
    tab = env_table() if table is None else table
    for name in names:
        v = env.get(name)
        if v not in (None, ""):
            return str(v)
    for name in names:
        v = tab.get(name)
        if v not in (None, ""):
            return str(v)
    if default is not None:
        return str(default)
    return _DEFAULTS.get(key, "")


def source_of(key: str, environ=None, table=None) -> str:
    """这个值从哪来：`env:<NAME>` ／ `dsh.env:<NAME>` ／ `default`／`未配置`"""
    names = _ALIASES.get(key, (key,))
    env = os.environ if environ is None else environ
    tab = env_table() if table is None else table
    for name in names:
        if env.get(name) not in (None, ""):
            return "env:%s" % name
    for name in names:
        if tab.get(name) not in (None, ""):
            return "dsh.env:%s" % name
    if _DEFAULTS.get(key):
        return "default"
    return "未配置"


def configured() -> bool:
    """★环境事实配齐了吗✗★（MC_HOME ＋ SAVE_NAME 是硬要求）"""
    return all(bool(resolve(k, "")) for k in REQUIRED_KEYS)


def require(key: str) -> str:
    """★严格取一个环境事实✗★：没配 ⇒ 抛 `NotConfigured`（★绝不回退本机路径✗★）"""
    v = resolve(key, "")
    if not v:
        raise NotConfigured("★未配置 %s✗★ — %s" % (key, UNCONFIGURED_HINT))
    return v


def require_path(key: str) -> pathlib.Path:
    return pathlib.Path(require(key))


def require_home() -> pathlib.Path:
    """★严格取实例目录✗★：没配就抛（agent 层用）"""
    return require_path("MC_HOME")


def require_save_dir() -> pathlib.Path:
    """★严格取存档目录✗★ = MC_HOME/saves/SAVE_NAME（两个键都必须配）"""
    return require_home() / "saves" / require("SAVE_NAME")


def _maybe(key: str):
    v = resolve(key, "")
    return pathlib.Path(v) if v else None


def _int(key: str, default: int) -> int:
    raw = resolve(key, str(default))
    try:
        return int(raw)
    except (TypeError, ValueError):
        print("paths: %s=%r 不是整数 ⇒ 用默认 %d" % (key, raw, default), file=sys.stderr)
        return int(default)


# ── 占位路径（★未配置时给"明显不是本机路径"的占位 ✗ 并已告警✗★）──────────
_PLACEHOLDER_HOME = ROOT / "__未配置_MC_HOME__"
_PLACEHOLDER_SAVE = ROOT / "__未配置_SAVE_NAME__"


def _home() -> pathlib.Path:
    h = _maybe("MC_HOME")
    if h is None:
        _warn_unconfigured("MC_HOME")
        return _PLACEHOLDER_HOME
    return h


def _mc_log_dir() -> pathlib.Path:
    return _home() / "logs"


def _save_dir() -> pathlib.Path:
    """存档目录：★没配 SAVE_NAME 时给占位（告警）✗ 不拿本机存档名猜✗★"""
    save = resolve("SAVE_NAME")
    if not save:
        _warn_unconfigured("SAVE_NAME")
        return _home() / "saves" / _PLACEHOLDER_SAVE.name
    return _home() / "saves" / save


# ── bot / 端口（有安全默认，不算机器绑定）─────────────────────────────────
BOT = resolve("BOT_NAME")
PORT = _int("DSH_PORT", 8766)
GATEWAY_PORT = _int("GATEWAY_PORT", 8765)


def cmd_url() -> str:
    return "http://127.0.0.1:%d" % PORT


def health_url() -> str:
    return cmd_url() + "/health"


def gateway_url() -> str:
    return "http://127.0.0.1:%d" % GATEWAY_PORT


# ── 版本 / jar / token（doctor＋bootstrap 用；不依赖 MC_HOME）─────────────
GRADLE_PROPERTIES = (ROOT / resolve("MOD_VERSION_FILE", "mod/gradle.properties")).resolve()


def read_gradle_version(path=None) -> str:
    """从 `gradle.properties` 读 `mod_version`（★单一真源 ✗ 不写死版本号✗★）"""
    p = pathlib.Path(path) if path else GRADLE_PROPERTIES
    try:
        for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
            s = ln.strip()
            if s.startswith("#") or "=" not in s:
                continue
            k, _, v = s.partition("=")
            if k.strip() in ("mod_version", "version"):
                return v.strip()
    except Exception as exc:                  # ★不许静默✗★
        print("paths: 读 %s 失败 %r" % (p, exc), file=sys.stderr)
    return ""


MOD_VERSION = os.environ.get("DSH_MOD_VERSION", "").strip() or read_gradle_version()

MOD_JAR_GLOB = "dshbridge*.jar"


def mod_jar_dirs() -> list:
    """找 jar 的目录（实例 mods ＋ 仓库构建产物）"""
    out = []
    home = _maybe("MC_HOME")
    if home is not None:
        out.append(home / "mods")
    out.append(MOD_DIR / "build" / "libs")
    return out


def token_file_candidates() -> list:
    """HTTP token 候选路径（★有顺序✗★）：env → 实例 config（若已配置）→ 仓库 state → 仓库 config"""
    out = []
    envf = resolve("HTTP_TOKEN_FILE", "")
    if envf:
        out.append(pathlib.Path(envf))
    home = _maybe("MC_HOME")
    if home is not None:
        out.append(home / "config" / "dshbridge" / "http_token.txt")
    out.append(STATE_DIR / "http_token.txt")
    out.append(ROOT / "config" / "dshbridge" / "http_token.txt")
    return out


def find_token_file():
    """第一个存在的 token 文件；都没有 ⇒ None（★不猜✗★）"""
    for p in token_file_candidates():
        try:
            if p.is_file():
                return p
        except OSError:                       # ★不许静默✗★
            print("paths: 检查 token 路径失败 %r" % (p,), file=sys.stderr)
    return None


# ── 大脑层接缝：node / dsh（★不写死本机安装路径 ✗ 未配置就明确报错✗★）──────
NODE_EXE_GLOBS = (r"C:\Program Files\nodejs\node.exe",)
DSH_EXE_GLOBS = (r"C:\Users\*\AppData\Local\Programs\*\dsh.exe",)


def find_node():
    """找 node：env(NODE_EXE/DSH_NODE) > PATH > 常见安装位置；找不到 ⇒ None"""
    v = resolve("NODE_EXE", "")
    if v:
        p = pathlib.Path(v)
        return p if p.is_file() else None
    w = shutil.which("node") or shutil.which("node.exe")
    if w:
        return pathlib.Path(w)
    import glob as _glob
    for pat in NODE_EXE_GLOBS:
        hits = _glob.glob(pat)
        if hits:
            return pathlib.Path(hits[0])
    return None


def require_node() -> pathlib.Path:
    """★大脑层要 node✗★：找不到 ⇒ 明确报错（调用方打印并非零退出）"""
    n = find_node()
    if n is None:
        raise NotConfigured(
            "★需要配置 node✗★：设环境变量 DSH_NODE（node 可执行文件路径）或把 node 加进 PATH")
    return n


def find_dsh_bin_js():
    """找 dsh 的 `lib/bin.js`：env(DSH_BIN_JS/DSH_ACP_BIN) > npm 缓存（LOCALAPPDATA）；无 ⇒ None"""
    v = resolve("DSH_BIN_JS", "")
    if v:
        p = pathlib.Path(v)
        return p if p.is_file() else None
    cache = pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "npm-cache" / "_npx"
    try:
        hits = sorted(cache.glob("*/node_modules/@deepseek-ai/dsh/lib/bin.js"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError as exc:                    # ★不许静默✗★
        print("paths: 查 npm 缓存失败 %r" % (exc,), file=sys.stderr)
        return None
    return hits[0] if hits else None


def require_dsh_bin_js() -> pathlib.Path:
    """★大脑层要 dsh 的 bin.js✗★：找不到 ⇒ 明确报错"""
    p = find_dsh_bin_js()
    if p is None:
        raise NotConfigured(
            "★需要配置 DSH_BIN_JS✗★（dsh 的 lib/bin.js 路径）或先安装 dsh")
    return p


# ── 离线数据（生成物的统一位置 ✗ bootstrap/doctor 用✗★；不依赖 MC_HOME）───
RECIPES_FILE = BUILD_DIR / "recipes.json"
TAGS_FILE = STATE_DIR / "tags_category.json"
EXCEPTIONS_FILE = STATE_DIR / "exceptions.json"
NO_DIG_FILE = STATE_DIR / "no_dig.json"
LANDMARKS_FILE = STATE_DIR / "landmarks.json"
EVENT_MEMORY_FILE = STATE_DIR / "event_memory.json"
TASKS_FILE = STATE_DIR / "tasks.json"
REASONS_INDEX = LOG_DIR / "reasons_index.json"
DIVERGENCE_DOC = DOCS_DIR / "分歧清单.md"
MIGRATION_DOC = DOCS_DIR / "迁移准备度.md"
MANIFEST_FILE = EXPORT_SNAPSHOTS_DIR / "manifest.json"

# 数据生成链（★顺序即依赖顺序✗★；bootstrap 按它跑）
GENERATORS = [
    ("tag_census", [sys.executable, str(TOOLS_DIR / "tag_census.py")]),
    ("recipe_index", [sys.executable, str(TOOLS_DIR / "recipe_index.py"), "--build"]),
    ("divergence", [sys.executable, str(TOOLS_DIR / "divergence.py"), "--by-namespace"]),
    ("kb_export", [sys.executable, str(TOOLS_DIR / "kb_export.py")]),   # ★验收器 ✗ 不是生成器✗★
]


def newest_export_snapshot():
    """最新的导出快照（`<版本>__<schema>__<日期>.json`，★排除 manifest✗★）"""
    if not EXPORT_SNAPSHOTS_DIR.is_dir():
        return None
    snaps = sorted(EXPORT_SNAPSHOTS_DIR.glob("*__*__*.json"))
    return snaps[-1] if snaps else None


# ── 机器相关常量：★惰性（用的时候才解析/才报错）✗★ ───────────────────────
_LAZY = {
    "MC_HOME": _home,
    "INSTANCE_NAME": lambda: resolve("INSTANCE_NAME"),
    "PACK_NAME": lambda: resolve("PACK_NAME"),
    "SAVE_NAME": lambda: resolve("SAVE_NAME"),
    "SAVES_DIR": lambda: _home() / "saves",
    "SAVE_DIR": _save_dir,
    "MODS_DIR": lambda: _home() / "mods",
    "CONFIG_DIR": lambda: _home() / "config",
    "MC_LOG_DIR": _mc_log_dir,
    "LATEST_LOG": lambda: _mc_log_dir() / "latest.log",
    "BLOCKKB_EXPORT": lambda: _mc_log_dir() / "blockkb.json",
    "RESOURCEPACKS_DIR": lambda: _home() / "resourcepacks",
    "MOD_JAR_DIRS": mod_jar_dirs,
}

__all__ = [n for n in _LAZY] + [
    "ROOT", "TOOLS_DIR", "AGENT_DIR", "STATE_DIR", "JOBS_DIR", "BUILD_DIR",
    "LOG_DIR", "DOCS_DIR", "CONTRACTS_DIR", "EXPORT_SNAPSHOTS_DIR", "BRIDGE_DIR",
    "MOD_DIR", "DSH_ENV_FILE", "DSH_ENV_EXAMPLE", "ENV_FILE_ENV", "BOT", "PORT",
    "GATEWAY_PORT", "cmd_url", "health_url", "gateway_url", "configured", "require",
    "require_path", "require_home", "require_save_dir", "require_node",
    "require_dsh_bin_js", "find_node", "find_dsh_bin_js", "resolve", "source_of",
    "describe", "parse_env_text", "load_env_file", "reload_env", "env_table",
    "GRADLE_PROPERTIES", "MOD_VERSION", "read_gradle_version",
    "token_file_candidates", "find_token_file", "newest_export_snapshot",
    "RECIPES_FILE", "TAGS_FILE", "EXCEPTIONS_FILE", "DSH_EXE_GLOBS",
    "NODE_EXE_GLOBS", "NotConfigured", "UNCONFIGURED_HINT",
]


def __getattr__(name):
    """★惰性机器相关常量✗★：访问时才解析；未配置 ⇒ 告警＋占位路径（`require()` 才抛）"""
    fn = _LAZY.get(name)
    if fn is not None:
        return fn()
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


def describe() -> dict:
    """诊断：每个环境事实的当前值与来源（doctor --json 用；★永不抛✗★）"""
    keys = ("MC_HOME", "INSTANCE_NAME", "PACK_NAME", "SAVE_NAME", "BOT_NAME",
            "DSH_PORT", "GATEWAY_PORT", "MOD_VERSION_FILE", "HTTP_TOKEN_FILE",
            "NODE_EXE", "DSH_BIN_JS")
    out = {"dsh_env_file": str(DSH_ENV_FILE),
           "dsh_env_exists": DSH_ENV_FILE.is_file(),
           "dsh_env_example": str(DSH_ENV_EXAMPLE),
           "dsh_env_example_exists": DSH_ENV_EXAMPLE.is_file(),
           "configured": configured(), "hint": UNCONFIGURED_HINT,
           "root": str(ROOT), "values": {}}
    for k in keys:
        out["values"][k] = {"value": resolve(k), "source": source_of(k)}
    out["derived"] = {}
    for k in ("MC_HOME", "MODS_DIR", "SAVES_DIR", "SAVE_DIR", "MC_LOG_DIR",
              "LATEST_LOG", "MOD_JAR_DIRS"):
        try:
            out["derived"][k] = str(_LAZY[k]())
        except NotConfigured as exc:          # ★不许静默✗★
            out["derived"][k] = {"error": str(exc)[:200]}
    out["derived"].update({"MOD_VERSION": MOD_VERSION, "BOT": BOT, "PORT": PORT,
                           "GATEWAY_PORT": GATEWAY_PORT,
                           "RECIPES_FILE": str(RECIPES_FILE),
                           "TAGS_FILE": str(TAGS_FILE),
                           "EXPORT_SNAPSHOTS_DIR": str(EXPORT_SNAPSHOTS_DIR),
                           "NODE": (str(find_node()) if find_node() else None),
                           "DSH_BIN_JS": (str(find_dsh_bin_js())
                                          if find_dsh_bin_js() else None)})
    return out


def main(argv) -> int:
    import json
    if argv and argv[0] == "--json":
        print(json.dumps(describe(), ensure_ascii=False, indent=1, default=str))
        return 0
    d = describe()
    print("dsh.env：%s（%s）" % (d["dsh_env_file"],
                                "在" if d["dsh_env_exists"] else "★不在✗★"))
    print("dsh.env.example：%s（%s）" % (d["dsh_env_example"],
                                        "在" if d["dsh_env_example_exists"] else "★不在✗★"))
    if not d["configured"]:
        print("★未配置✗★：%s" % d["hint"])
    for k, v in d["values"].items():
        print("  %-16s = %-60s ← %s" % (k, str(v["value"])[:60], v["source"]))
    print("派生：BOT=%s PORT=%d GATEWAY_PORT=%d MOD_VERSION=%s"
          % (BOT, PORT, GATEWAY_PORT, MOD_VERSION or "?"))
    for k, v in d["derived"].items():
        print("  %-16s = %s" % (k, (v.get("error") if isinstance(v, dict) else v)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
channel.py — 与游戏内计算机（cc0 / cmd0 / turtle）通信的唯一下层

这是"假人的手脚接口"：上层技能、反射、大脑都只能通过这里发指令、收结果。

设计原则（每一条都是踩坑换来的，别改）：
 1. **指令走网关文件收件箱**：往 bridge/inbox/ 写一个 JSON 就算下发，
    游戏内的计算机通过 HTTP 轮询网关把指令取走。
    好处：不需要写存档目录 ⇒ 不需要放宽沙箱权限。
    存档直写（send_disk）只作为"网关挂了"时的备用通道。
 2. **原子发布**：先写 .tmp 再改名。网关是边写边读的，
    如果直接写目标文件，它可能读到半个 JSON —— 然后报一个看不懂的解析错。
 3. **结果必须连轮转日志一起读**：cc0 心跳每秒约 4 条，
    刚执行完的结果经常已经被滚进 log.jsonl.1。只看 log.jsonl 会误判成"没回传"。
    （这个坑已经踩过两次，见 docs/错题本.md）
 4. **参数不许猜**：每个动作接受哪些参数，用 tools/gen_action_schema.py
    从 agent_bridge.lua 里提取成 action_schema.json。
    这里按 schema 过滤参数：多给的会被丢掉并告警，少给的交给 Lua 的默认值。
    schema 过期（lua 变了但没重新生成）会直接报错，避免"改了 lua 却按旧参数调"。
 5. **返回值形状不固定**：Lua 可能返回表、字符串、数字。
    字符串往往就是错误信息（例如"未知指令：xxx"），所以这里要把它当失败暴露出来，
    而不是当成"执行成功但没有内容"。

自测：
    py agent/channel.py            # 检查 schema 新鲜度 + 网关存活 + 一次安全的 status
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

AGENT_DIR = Path(__file__).resolve().parent
ROOT = AGENT_DIR.parent                      # mc-agent-bridge/
sys.path.insert(0, str(ROOT / "tools"))      # ★解绑：环境事实只在 tools/paths.py✗★
import paths as PA                           # noqa: E402
BRIDGE_DIR = ROOT / "bridge"
SCHEMA_PATH = AGENT_DIR / "action_schema.json"
LUA_PATH = ROOT / "cc-tweaked" / "agent_bridge.lua"
# ★这里**不写死本机路径**✗★：没配 dsh.env/环境变量 ⇒ `NotConfigured` 直接抛
#   （★明确报错 ✗ 绝不静默回退到某台电脑的存档路径✗★）
SAVE_DIR = PA.require_save_dir()
if not SAVE_DIR.is_dir():
    # ★配了但配错（路径不存在）也**明确报错**✗ 不许悄悄退回本机或空跑✗★
    raise PA.NotConfigured(
        "配置的存档目录不存在：%s（检查 dsh.env 的 MC_HOME／SAVE_NAME；"
        "★不会回退到本机路径✗★）" % SAVE_DIR)
GATEWAY = PA.gateway_url()

# 计算机 id → 角色。turtle 只能通过 cc0 的 rednet 转发，不能直连。
COMPUTERS = {
    "cc0": {"id": 0, "role": "main", "note": "Advanced Peripherals 全外设，可以转发指令给海龟"},
    "turtle": {"id": 1, "role": "miner", "note": "海龟，能合成能挖，只能经 cc0 转发"},
    "cmd0": {"id": 2, "role": "command", "note": "命令计算机，执行游戏指令的地方"},
    "gps0": {"id": 3, "role": "gps", "note": "GPS 基站"},
}


class BridgeError(RuntimeError):
    """通道层错误（会话级，应该让上层看见，不要吞）。"""


class BridgeTimeout(BridgeError):
    pass


# --------------------------------------------------------------------------- #
# schema：参数名不许猜
# --------------------------------------------------------------------------- #

def load_schema(path: Path = SCHEMA_PATH) -> dict:
    if not Path(path).is_file():
        return {"actions": {}}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as e:  # schema 坏了要立刻知道，不能静默当成"没有 schema"
        raise BridgeError("action_schema.json 解析失败：%r" % (e,))


def schema_freshness(path: Path = SCHEMA_PATH, lua: Path = LUA_PATH) -> tuple[bool, str]:
    """schema 是否仍然对应当前的 lua 源文件。"""
    path, lua = Path(path), Path(lua)
    if not path.is_file():
        return False, "schema 文件不存在：%s（先跑 py tools/gen_action_schema.py）" % path
    if not lua.is_file():
        return False, "lua 源文件不存在：%s" % lua
    rec = load_schema(path).get("sha1")
    now = hashlib.sha1(lua.read_bytes()).hexdigest()
    if rec == now:
        return True, "schema 与 agent_bridge.lua 一致（%s）" % now[:12]
    return False, ("schema 已过期：lua 现在是 %s，schema 记录的是 %s —— "
                   "请重跑 py tools/gen_action_schema.py" % (now[:12], str(rec)[:12]))


# --------------------------------------------------------------------------- #
# 回传
# --------------------------------------------------------------------------- #

@dataclass
class Result:
    id: str
    who: str
    cmd: str
    ok: bool
    data: dict = field(default_factory=dict)
    ts: float = 0.0

    @property
    def result(self):
        return self.data.get("result")

    def lines(self) -> list[str]:
        """把 Lua 的返回值尽力拆成文本行（形状不固定，所以要兼容）。"""
        r = self.result
        if isinstance(r, dict):
            v = r.get("lines", r.get("output"))
            if isinstance(v, list):
                return [str(x) for x in v]
            if isinstance(v, str):
                return [v]
            return []
        if isinstance(r, str):
            return [r]
        return []

    def as_dict(self) -> dict:
        r = self.result
        if isinstance(r, dict):
            return r
        raise BridgeError("[%s] %s 的返回值不是表，而是 %s：%r"
                          % (self.id, self.cmd, type(r).__name__, r))

    def text(self) -> str:
        return "\n".join(self.lines()) or repr(self.result)

    def summary(self, limit: int = 500) -> str:
        s = json.dumps(self.data, ensure_ascii=False)
        return s if len(s) <= limit else s[:limit] + "…"

    def __bool__(self) -> bool:
        return bool(self.ok)


def _extract_items(obj, out=None) -> list[dict]:
    """从任意嵌套结构里挖出形似物品的字典（name/id + count）。

    为什么要这样：bot_inv 的返回结构随 Lua 版本变过，
    写死路径会在某次改动后静默返回空列表 —— 那比报错更危险。
    """
    if out is None:
        out = []
    if isinstance(obj, dict):
        keys = set(obj.keys())
        if ("name" in keys or "id" in keys) and ("count" in keys or "Count" in keys):
            out.append(obj)
        else:
            for v in obj.values():
                _extract_items(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _extract_items(v, out)
    return out


# --------------------------------------------------------------------------- #
# 通道
# --------------------------------------------------------------------------- #

class Channel:
    """一台游戏内计算机的会话。线程安全（内部串行化：一台机器同时只吃一条指令）。"""

    def __init__(self, who: str = "cmd0", bridge: Path = BRIDGE_DIR,
                 schema: dict | None = None, strict_args: bool = True,
                 verbose: bool = True, gateway: str = GATEWAY, use_http: bool = True):
        self.who = who
        self.bridge = Path(bridge)
        self.schema = schema if schema is not None else load_schema()
        self.strict_args = strict_args
        self.verbose = verbose
        self.gateway = gateway
        self.use_http = use_http
        self.transport = "?"                  # 实际用了哪条通道：http / file
        self._lock = threading.Lock()
        self._cache: dict[str, dict] = {}     # id -> 结果记录（只放 state）
        self._pushes: list[dict] = []         # push/next 记录（文件通道认领 id 用）
        self._claimed: set[str] = set()
        self._offsets: dict[str, int] = {}
        self._warned: set[str] = set()
        self.sent: list[dict] = []       # 本会话下发过什么（给评审/复盘用）
        self.received: list[dict] = []   # 本会话收到什么

    # -- 收件箱 -------------------------------------------------------------- #

    @property
    def inbox(self) -> Path:
        d = self.bridge / "inbox"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _post_command(self, cmd: str, args: dict, timeout: float = 10.0) -> dict | None:
        """首选通道：POST /api/command。

        两个理由：
          1. 网关**自己生成 id**（agent_gateway.py 的 Hub.push 里是 uuid4().hex[:8]），
             它会把分配的 id 连同 queued 一起回给我们 —— 这样等待回传才能按 id 精确认领。
             （写文件通道是拿不到这个 id 的，只能事后从日志里认领，见 _claim_id。）
          2. 用 JSON body 而不是 GET /api/push 的 query string：
             query 里数字和布尔都会变成字符串，而 Lua 里 "false" 是**真值** —— 这种坑不值得踩。
        """
        body = json.dumps({"who": self.who, "cmd": cmd, "args": args},
                          ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.gateway.rstrip("/") + "/api/command", data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                d = json.loads(resp.read().decode("utf-8", "replace"))
        except Exception:
            return None                       # 网关没起/不可达 → 交给文件通道
        item = d.get("queued")
        return item if isinstance(item, dict) else None

    def _claim_id(self, cmd: str, args: dict, since: float, timeout: float = 15.0) -> str | None:
        """文件通道专用：从日志的 push 记录里认领"哪一条才是我们刚发的"。

        认领依据：cmd 相同 + args 完全相同 + 时间不早于下发时刻 + 没被别人认领过。
        一台计算机上的指令是串行的，所以这个指纹足够唯一。
        """
        t0 = time.time()
        while time.time() - t0 < timeout:
            self._pump()
            for rec in self._pushes:
                data = rec.get("data") or {}
                cid = str(data.get("id") or "")
                if not cid or cid in self._claimed or data.get("cmd") != cmd:
                    continue
                if (data.get("args") or {}) != (args or {}):
                    continue
                if float(rec.get("ts") or 0) < since - 0.5:
                    continue
                self._claimed.add(cid)
                return cid
            time.sleep(0.2)
        return None

    def send(self, cmd: str, args: dict | None = None, note: str = "") -> str:
        args = dict(args or {})
        t0 = time.time()
        item = self._post_command(cmd, args) if self.use_http else None
        if item and item.get("id"):
            cid = str(item["id"])
            self.transport = "http"
        else:
            # 备用通道：写收件箱。注意这里**不带 id 字段** —— 网关不看它，会自己分配，
            # 带上反而会让人误以为 id 是我们说了算。
            payload = {"who": self.who, "cmd": cmd, "args": args}
            if note:
                payload["note"] = note
            local = uuid.uuid4().hex[:8]
            safe = re.sub(r"[^A-Za-z0-9_.-]", "_", cmd)
            name = "%s-%s-%s.json" % (time.strftime("%H%M%S"), local, safe)
            tmp = self.inbox / (name + ".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
            os.replace(tmp, self.inbox / name)     # 原子发布，避免网关读到半个文件
            self.transport = "file"
            cid = self._claim_id(cmd, args, t0) or ""
            if not cid:
                raise BridgeError("已把 %s 写进收件箱，但 15s 内没能从日志里认领到它："
                                  "网关可能没在跑（启动时要带 --bridge-dir bridge），"
                                  "或者日志里没有对应的 push 记录。" % cmd)
        self.sent.append({"ts": t0, "id": cid, "cmd": cmd, "args": args,
                          "transport": self.transport})
        if self.verbose:
            print("[→ %s/%s] %s %s" % (self.transport, self.who, cmd,
                                       json.dumps(args, ensure_ascii=False)))
        return cid

    def send_disk(self, cmd: str, args: dict | None = None, computer: str = "cmd0") -> str:
        """备用通道：直接写进存档目录里计算机的本地收件箱（网关挂了时用）。

        需要进程对 D: 有写权限；在受限沙箱里会失败，这是预期行为，不要绕。
        """
        cid = uuid.uuid4().hex[:8]
        cidir = COMPUTERS.get(computer, {}).get("id")
        if cidir is None:
            raise BridgeError("未知计算机：%s（可选 %s）" % (computer, list(COMPUTERS)))
        d = SAVE_DIR / "computercraft" / "computer" / str(cidir) / "bridge_local" / "inbox"
        d.mkdir(parents=True, exist_ok=True)
        payload = {"id": cid, "who": computer, "cmd": cmd, "args": args or {}}
        (d / ("%s-%s.json" % (time.strftime("%H%M%S"), cid))).write_text(
            json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
        if self.verbose:
            print("[→ disk:%s] %s %s" % (computer, cmd, json.dumps(args or {}, ensure_ascii=False)))
        return cid

    # -- 日志（含轮转） ------------------------------------------------------ #

    def _log_files(self) -> list[Path]:
        cur = self.bridge / "log.jsonl"
        rots = []
        for p in glob.glob(str(cur) + ".*"):
            m = re.search(r"\.(\d+)$", p)
            if m:
                rots.append((int(m.group(1)), Path(p)))
        rots.sort(key=lambda t: -t[0])          # 数字大 = 旧
        return [p for _, p in rots] + ([cur] if cur.is_file() else [])

    def _ingest_line(self, line: str) -> None:
        line = line.strip()
        if not line or not line.startswith("{"):
            return
        try:
            rec = json.loads(line)
        except Exception:
            return
        data = rec.get("data")
        if not isinstance(data, dict):
            data = rec if ("id" in rec or "result" in rec) else None
        if not isinstance(data, dict):
            return
        kind = rec.get("kind")
        cid = data.get("id")
        # 只有 state（游戏侧回传的结果）才是"结果"。
        # 如果连 push 记录也当结果，wait() 会在指令刚下发时就误判成"已完成"。
        if kind == "state" or (kind is None and ("result" in data or "ok" in data)):
            if cid:
                self._cache[str(cid)] = rec
        elif kind in ("push", "next"):
            self._pushes.append(rec)
            if len(self._pushes) > 4000:
                del self._pushes[:2000]

    def _pump(self) -> None:
        for f in self._log_files():
            key = str(f)
            off = self._offsets.get(key, 0)
            try:
                size = f.stat().st_size
            except OSError:
                continue
            if size < off:                       # 被轮转/截断过 → 重读
                off = 0
            if size == off:
                continue
            with open(f, "rb") as fh:
                fh.seek(off)
                blob = fh.read()
            nl = blob.rfind(b"\n")
            if nl < 0:
                continue                        # 只处理完整行，半行等下次
            self._offsets[key] = off + nl + 1
            for ln in blob[:nl + 1].decode("utf-8", "replace").splitlines():
                self._ingest_line(ln)

    # -- 参数过滤 ------------------------------------------------------------ #

    def action_args(self, cmd: str) -> dict | None:
        a = (self.schema.get("actions") or {}).get(cmd)
        if not isinstance(a, dict):
            return None
        return a.get("args") or {}

    def filter_args(self, cmd: str, args: dict | None) -> dict:
        args = dict(args or {})
        known = self.action_args(cmd)
        if known is None:
            if cmd not in self._warned:
                self._warned.add(cmd)
                print("[!] schema 里没有动作 %r —— 参数不做过滤（跑 py tools/gen_action_schema.py 补上）" % cmd)
            return args
        if not known:
            return args
        keep = {k: v for k, v in args.items() if k in known}
        dropped = sorted(set(args) - set(known))
        if dropped and self.strict_args:
            raise BridgeError("动作 %s 不接受参数 %s（它接受：%s）"
                              % (cmd, dropped, sorted(known)))
        if dropped:
            print("[!] %s 忽略未知参数 %s" % (cmd, dropped))
        return keep

    # -- 调用 ---------------------------------------------------------------- #

    def wait(self, cid: str, timeout: float = 60.0, poll: float = 0.2,
             cmd: str | None = None) -> Result:
        t0 = time.time()
        last_note = 0.0
        while True:
            self._pump()
            rec = self._cache.get(cid)
            if rec is not None:
                data = rec.get("data") or {}
                r = Result(id=cid, who=rec.get("who", self.who), cmd=data.get("cmd", "?"),
                           ok=bool(data.get("ok")), data=data, ts=float(rec.get("ts", 0.0)))
                self.received.append({"ts": time.time(), "id": cid, "ok": r.ok})
                return r
            now = time.time()
            if now - t0 > timeout:
                q = self.queued().get(self.who, "?")
                raise BridgeTimeout(
                    "等 %s 的 %s(%s) 回传超时（%.0fs）。队列深度=%s。"
                    "队列>0 表示网关还没被取走；队列=0 却仍无回传，表示计算机正忙在跑上一条长指令"
                    "（同一台计算机一次只吃一条指令，长任务会把通道占住）。"
                    % (self.who, cmd or "?", cid, now - t0, q))
            if self.verbose and now - last_note > 10:
                last_note = now
                print("[…] 仍在等 %s 的 %s（已 %.0fs，队列=%s）"
                      % (self.who, cmd or cid, now - t0, self.queued().get(self.who, "?")))
            time.sleep(poll)

    def call(self, cmd: str, args: dict | None = None, timeout: float = 60.0,
             allow_str: bool = False, note: str = "") -> Result:
        args = self.filter_args(cmd, args)
        with self._lock:
            cid = self.send(cmd, args, note=note)
            r = self.wait(cid, timeout=timeout, cmd=cmd)
        # 字符串返回值通常就是错误信息，当成功会掩盖问题
        if not allow_str and isinstance(r.result, str) and not r.ok:
            raise BridgeError("[%s] %s 返回字符串（多半是错误）：%s" % (cid, cmd, r.result[:300]))
        if self.verbose and not r.ok:
            print("[! %s] %s 报告失败：%s" % (self.who, cmd, r.summary(300)))
        return r

    def cmd(self, text: str, timeout: float = 45.0, **kw) -> Result:
        """执行一条游戏指令（服务端视角，权威）。"""
        return self.call("cmd", {"text": text}, timeout=timeout, **kw)

    def cmd_async(self, text: str, timeout: float = 20.0) -> Result:
        return self.call("cmd_async", {"text": text}, timeout=timeout)

    # -- 世界状态才是证据 ---------------------------------------------------- #

    def verify_block(self, x: int, y: int, z: int, timeout: float = 20.0) -> dict:
        """查一个方块的权威状态。任何"我放下了/我挖掉了"的说法都要用它复核。"""
        r = self.call("block_state", {"x": x, "y": y, "z": z}, timeout=timeout)
        d = r.as_dict()
        return d

    def verify_command_ok(self, text: str, timeout: float = 45.0) -> bool:
        """执行指令并检查服务端是否真的成功（success 字段）。"""
        r = self.cmd(text, timeout=timeout, allow_str=True)
        res = r.result
        if isinstance(res, dict):
            return bool(res.get("success"))
        return bool(r.ok)

    def inventory(self, bot: str = "Bot", timeout: float = 30.0) -> list[dict]:
        r = self.call("bot_inv", {"bot": bot}, timeout=timeout, allow_str=True)
        return _extract_items(r.result)

    def alive(self, bot: str = "Bot", timeout: float = 45.0) -> bool:
        """假人是否在线。

        一律以"指令是否执行成功"为准。**不要**去回传文本里找 "has the following entity data"：
          1. 服务端可能是中文，那句话会被本地化；
          2. CC 终端渲染不了 CJK，中文会变成一串 '?'；
          3. 命令文本本身会被回显在 result.text 里，傻找关键词会把"指令里含 Pos"当成"实体存在"，
             于是永远返回 True —— 这就是个静默的假阳性。
        """
        return self.verify_command_ok("data get entity %s Health" % bot, timeout=timeout)

    def queued(self) -> dict:
        st = self.bridge / "state.json"
        if not st.is_file():
            return {}
        try:
            return json.loads(st.read_text(encoding="utf-8")).get("queues", {})
        except Exception:
            return {}


# --------------------------------------------------------------------------- #
# 自测
# --------------------------------------------------------------------------- #

def selftest() -> int:
    ok, msg = schema_freshness()
    print("schema：%s %s" % ("OK " if ok else "!! ", msg))
    ch = Channel("cmd0")
    print("收件箱：%s" % ch.inbox)
    print("排队的计算机：%s" % (ch.queued() or "（state.json 还没生成）"))
    try:
        r = ch.call("status", timeout=25.0, allow_str=True)
        print("status → ok=%s\n%s" % (r.ok, r.summary()))
    except BridgeError as e:
        print("[X] 通道不通：%s" % e)
        return 1
    return 0 if ok else 0


if __name__ == "__main__":
    raise SystemExit(selftest())

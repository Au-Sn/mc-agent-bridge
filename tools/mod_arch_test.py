#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mod_arch_test.py -- S1 结构判据（X1~X7，★离线源码断言 ✗ 不碰游戏✗★）

WHY（ADR-5「先切边界，再拆类；只搬不改」）
  2.56.0 把协议/安全/事件边界做出来了，但代码都还在 7500 行主类里。
  S1 的目标只有一件事：把 HTTP 服务（accept 池／世界车道／token／Origin／raw 白名单／
  请求账本／dshhttp／dshreqs）**原样搬进** `com.dsh.bridge.HttpBridge`，
  业务逻辑/回执文本/tick 顺序一律不动。

CHECKS
  X1 主类**变小**：DshBridgeMod.java 行数 ≤ 7050（S1 前实测 7498）；新类 HttpBridge.java ≥ 400 行
  X2 新边界存在：HttpBridge 里能看到 start/stop/accept/handle/token/白名单/世界车道/请求账本
  X3 协议方法**不再定义在主类**，且主类确实**调用** HttpBridge（生命周期 + 两条只读命令）
  X4 tick 顺序没动：turn→walk→do→auto 四段顺序不变；holdYaw 仍在 onServerTick 里、且
     `server_end_after_hold` 打戳在 holdYaw **之后**
  X5 主类 static 可变字段只减不增（S1 前实测 31 ⇒ 要求 ≤ 24，因为 HTTP 那 8 个搬走了）
  X6 E11 兼容：`ev("http_server")`/`ev("http_error")` 两个字面量**留在主类**
     （errata_guard E11 只扫 DshBridgeMod.java 对账事件名 ⇒ 搬走会让 E11 报"漏掉 2 个"）
  X7 只搬不改（协议文本原样在 HttpBridge 里）：/health 回执、401/403 的 reason=、X-DSH-Req 头、
     dshhttp/dshreqs 回执前缀、世界车道线程名、token 文件名 —— 逐字节保留
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JAVA_DIR = ROOT / "mod" / "src" / "main" / "java" / "com" / "dsh" / "bridge"
MAIN = JAVA_DIR / "DshBridgeMod.java"
BRIDGE = JAVA_DIR / "HttpBridge.java"

sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception as _exc:               # stdout may be a pipe without reconfigure
    print("note: stdout reconfigure skipped: %r" % (_exc,))


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""


def _lines(s: str) -> int:
    return len(s.splitlines())


def main(argv) -> int:
    checks = []
    main_src = _read(MAIN)
    bridge_src = _read(BRIDGE)

    # X1 主类变小 + 新类够大
    ml, bl = _lines(main_src), _lines(bridge_src)
    checks.append(("X1 主类变小（%d ⇒ %d 行，目标 ≤7050）＋ HttpBridge %d 行（≥400）"
                   % (7498, ml, bl),
                   bool(ml <= 7050 and bl >= 400), "main=%d bridge=%d" % (ml, bl)))

    # X2 新边界内容
    need = ["class HttpBridge", "httpStart", "httpStop", "httpAcceptLoop", "httpHandle",
            "httpTokenLoadOrCreate", "RAW_ALLOW_PLAYER", "RAW_ALLOW_SETBLOCK", "RAW_ALLOW_TP",
            "RAW_ALLOW_ITEM", "httpWorldLane", "httpLogReq", "httpDiag", "httpReqs",
            "dsh-world-lane", "x-dsh-token:"]
    miss = [k for k in need if k not in bridge_src]
    checks.append(("X2 HttpBridge 含协议/安全/并发全套边界方法", not miss,
                   "missing=%s" % miss))

    # X3 协议方法不再定义在主类 + 主类确实调用新类
    defs = [pat for pat in (r"static\s+void\s+httpHandle\s*\(",
                            r"static\s+void\s+httpAcceptLoop\s*\(",
                            r"static\s+String\s+httpWorldLane\s*\(",
                            r"httpTokenLoadOrCreate\s*\(",
                            r"rawDenyReason\s*\(")
            if re.search(pat, main_src)]
    calls = [k for k in ("HttpBridge.httpStart(", "HttpBridge.httpStop(",
                         "HttpBridge.httpDiag(", "HttpBridge.httpReqs(") if k in main_src]
    checks.append(("X3 协议方法已搬出主类 ＋ 主类调用 HttpBridge（生命周期/两条命令）",
                   bool(not defs and len(calls) == 4),
                   "still_defined=%s calls=%s" % (defs, calls)))

    # X4 tick 顺序没动
    m = main_src.find("public static void onPlayerTick(")
    region = main_src[m:m + 3200] if m >= 0 else ""
    order = [region.find(k) for k in ("tickTurn(p)", "tickWalk(p)", "tickDo(p)", "tickAuto(p)")]
    order_ok = all(v >= 0 for v in order) and order == sorted(order)
    st = main_src.find("public static void onServerTick(")
    sregion = main_src[st:st + 3000] if st >= 0 else ""
    hold = sregion.find("holdYaw(pl)")
    tag = sregion.find('bracket(pl, "server_end_after_hold")')
    hold_ok = hold >= 0 and tag > hold
    checks.append(("X4 tick 顺序不变：turn→walk→do→auto ＋ holdYaw 之后才打 server_end_after_hold",
                   bool(order_ok and hold_ok),
                   "order=%s hold_idx=%d tag_idx=%d" % (order, hold, tag)))

    # X5 主类 static 可变字段只减不增
    mut = [l for l in main_src.splitlines()
           if re.match(r"^    static\s+(?!final\b)(?!void\b)(?!class\b)(?!.*\()[\w<>\[\].]+\s+\w+\s*[=;]", l)]
    checks.append(("X5 主类 static 可变字段只减不增（S1 前 31 ⇒ 现 ≤24）",
                   len(mut) <= 24, "main_static_mutable=%d" % len(mut)))

    # X6 E11 兼容：http 事件字面量留在主类
    e11_ok = ('ev("http_server"' in main_src) and ('ev("http_error"' in main_src)
    checks.append(("X6 E11 兼容：http_server/http_error 的 ev 字面量留在主类（E11 只扫主类）",
                   e11_ok, "http_server_literal=%s http_error_literal=%s"
                   % ('ev("http_server"' in main_src, 'ev("http_error"' in main_src)))

    # X7 只搬不改：协议文本原样在新类里
    kept = ['"ok dshbridge-http"', "ERR:auth reason=missing_token", "reason=bad_token",
            "reason=origin_header", "ERR:raw_denied ", "X-DSH-Req: ",
            '"dshhttp port="', '"dshreqs total="', "dsh-world-lane", "http_token.txt",
            "HTTP/1.1 "]
    lost = [k for k in kept if k not in bridge_src]
    checks.append(("X7 只搬不改：协议回执文本/头/线程名逐字节保留在 HttpBridge", not lost,
                   "lost=%s" % lost))

    bad = 0
    for name, ok, detail in checks:
        print("  %s %s | %s" % (name, "PASS" if ok else "FAIL", str(detail)[:120]))
        if not ok:
            bad += 1
    print("  ---- %d/%d ----" % (len(checks) - bad, len(checks)))
    if bad:
        print("  => mod_arch FAIL (%d)" % bad)
        print("MODARCH ok=0 bad=%d checks=%d main_lines=%d bridge_lines=%d"
              % (bad, len(checks), ml, bl))
        return 1
    print("  => mod_arch PASS (S1: HTTP boundary moved to HttpBridge; main shrunk; tick order intact)")
    print("MODARCH ok=1 checks=%d main_lines=%d bridge_lines=%d" % (len(checks), ml, bl))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

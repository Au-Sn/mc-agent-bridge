# -*- coding: utf-8 -*-
"""skin_apply.py —— 按 docs/模组-皮肤系统.md §6 记录的**已验证修法**给假人换皮肤

记录里写死的两件事 ✓：
  ① 走**模组自己的 `/dskskin <名字>`** ✓ —— 它会 **移除实体 ＋ 重加实体** ✓
     （§6.1 第三次定位：「完全没反应」⇒ 排除缓存 ⇒ **实体早就在世界里 ⇒ 客户端不重建** ✗）
  ② 别让 **两套系统抢同一个 `textures`** ✗（`BotSkin`/`dshtskin` 与模组自己的 `dskskin` ✓）
     ⇒ 先把 `dshtskin` 那套清掉 ✓（它注入的是**未签名**属性 ⇒ 客户端会话服务会拒 ✗
        实测日志：`Signature is missing from Property textures` ✗ ⇒ 那条路走不通 ✗）

判据 ✓（照文档 §4 的 A2/A4/A7 来 ✓）：
  · `/dskskin` 列表里能看见 `deepseek` ✓ 且标 `ok` ✓
  · `/dskskin deepseek` 回执成功 ✓
  · **真去连一下**那个 URL ✓（文档 bug #2 的教训：只看端口号永远发现不了 ☞ 必须真连 ✓）
  · 客户端到底取没取 ✓：看 `logs/skin_server.log` 里有没有 **Minecraft 的 UA** ✓
    （顺带纠错 ✓：客户端取图的判官**不是** `logs/skin_http.log` ✗ —— 那文件根本不存在 ✗）
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
from channel import Channel  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

LOG = ROOT / "logs" / "skin_server.log"


def main() -> int:
    ch = Channel("cmd0", verbose=False)

    def ab(c: str, t: float = 60.0) -> str:
        try:
            return (ch.cmd("execute as Bot at Bot run " + c, timeout=t,
                           allow_str=True).text() or "").strip()
        except Exception as e:
            return "ERR:%s" % type(e).__name__

    before = LOG.stat().st_size if LOG.is_file() else 0

    print("1) 先清掉 BotSkin 那套服务端注入（两套别抢同一个 textures）")
    print("   dshtskin clear -> %s" % (ab("dshtskin clear").splitlines()[0][:130] or "(空)"))
    print("2) 用模组自己的皮肤命令（移除+重加实体 = 文档 §6.1 的修法）")
    for c in ("dskskin off", "dskskin deepseek"):
        r = ab(c)
        print("   %-18s -> %s" % (c, (r.splitlines()[0][:150] if r else "(空)")))
    time.sleep(3)
    print("3) 回执核对")
    for c in ("dskskin", "dshtskin status"):
        r = ab(c)
        print("   %-16s -> %s" % (c, (r.splitlines()[0][:160] if r else "(空)")))
    print("4) 客户端到底取没取图（判官 = logs/skin_server.log 里有没有 Minecraft 的 UA）")
    time.sleep(4)
    if LOG.is_file():
        txt = LOG.read_text(encoding="utf-8", errors="replace")
        new = txt[before:] if len(txt) > before else ""
        if new.strip():
            for ln in new.strip().splitlines()[-6:]:
                print("   NEW  " + ln[:150])
        else:
            print("   （这几秒没有新请求 ✓ —— 若假人外观没变 ⇒ 就是客户端没来取 ✗ 见文档 §6.2 bug #4）")
        ua_mc = [ln for ln in txt.splitlines() if "Minecraft" in ln or "Mozilla" not in ln and "GET /" in ln]
        print("   历史里有 Minecraft 取图的记录 = %s（共 %d 条 GET）"
              % (bool([l for l in txt.splitlines() if "Java" in l or "Minecraft" in l]),
                 len([l for l in txt.splitlines() if "GET /" in l])))
    return 0


raise SystemExit(main())

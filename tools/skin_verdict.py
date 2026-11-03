# -*- coding: utf-8 -*-
"""skin_verdict.py —— 重启之后**一条命令给结论**（皮肤到底成没成 ✓ 三个判官一起看 ✓）

为什么要它 ✗：这几轮我为了查皮肤，**一个一个文件去翻**（还翻错过目录 ✗ ——
  模组的访问日志在**游戏目录** ✓ 我却去仓库里找 ✗）⇒ 每次都要来回好几轮 ✗
  ⇒ 做成一条命令 ✓：**一次读齐三个判官** ✓ 并直接给"成/没成/还没重启"的三选一 ✗

三个判官 ✓（都是文件 ✓ 不猜 ✓）：
  ① `logs/latest.log` —— `Signature is missing from Property textures` 出现几次 ✗
     （≥1 ⇒ 客户端在**拒收未签名属性** ✓ ⇒ 服务端注入那条路不通 ✗）
  ② `CustomSkinLoader/CustomSkinLoader.log` —— **LocalSkin 有没有命中 Bot.png** ✓
     （这条是"客户端侧加载"成不成的**直接证据** ✓）
  ③ `logs/skin_http.log`（模组自己的小 HTTP ✓）—— 有没有**客户端**来取过 ✓
     （注意 ✓：这条是"服务端注入路"的判官 ✓ 与 ② 是**两条路** ✓ 要分开看 ✗）
判定 ✓：
  · ②里命中 ⇒ **成了** ✓（客户端自己加载的 ✓ 不依赖属性签名 ✓）
  · ②不存在 ⇒ **还没重启过** ✗（装完 CSL 之后没开过游戏 ✓）
  · ②存在但没命中 ⇒ CSL 没认出 Bot ⇒ 看它日志里报的目录/文件名 ✓（脚本会把最后几行打出来 ✓）
"""
from __future__ import annotations

import sys, paths as PA
import time
from pathlib import Path

ROOT = PA.ROOT
GAME = PA.MC_HOME
LATEST = GAME / "logs" / "latest.log"
CSL = GAME / "CustomSkinLoader" / "CustomSkinLoader.log"
MODSKIN = GAME / "logs" / "skin_http.log"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def tail(p: Path, n: int = 6) -> list:
    if not p.is_file():
        return []
    return p.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]


def main() -> int:
    out = []
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    out.append("== 皮肤判官（%s）==" % now)

    # ① 未签名属性被拒的次数
    sig = 0
    if LATEST.is_file():
        sig = sum(1 for l in LATEST.read_text(encoding="utf-8", errors="replace").splitlines()
                  if "Signature is missing" in l)
    out.append("① latest.log : 'Signature is missing from Property textures' = %d 次%s"
               % (sig, "  ⇒ 客户端在拒收未签名属性（服务端注入那条路不通 ✗）" if sig else ""))

    # ② CustomSkinLoader 有没有命中 LocalSkin
    hit = False
    if CSL.is_file():
        txt = CSL.read_text(encoding="utf-8", errors="replace")
        low = txt.lower()
        hit = ("localskin" in low) or ("bot.png" in low)
        out.append("② CustomSkinLoader.log : 存在 ✓（%d 行）命中 LocalSkin/Bot.png = %s"
                   % (len(txt.splitlines()), hit))
        for l in tail(CSL, 6):
            out.append("     | " + l[:150])
    else:
        out.append("② CustomSkinLoader.log : ★不存在★ ⇒ **装完 CSL 之后还没启动过游戏** ✗")

    # ③ 模组自己的小 HTTP 有没有被取过（另一条路 ✓ 分开看）
    if MODSKIN.is_file():
        lines = MODSKIN.read_text(encoding="utf-8", errors="replace").splitlines()
        out.append("③ 模组 skin_http.log : %d 次请求（其中可能有我自己 curl 的 ✗ 见时间戳 ✓）"
                   % len(lines))
        for l in lines[-3:]:
            out.append("     | " + l[:140])
    else:
        out.append("③ 模组 skin_http.log : ★不存在★")

    # 结论
    if hit:
        out.append("=> ★结论：成了★ ✓ 皮肤由客户端（CustomSkinLoader/LocalSkin）加载 ✓"
                   " —— 请顺便用眼睛确认一下假人是不是那条蓝鱼 ✓")
    elif not CSL.is_file():
        out.append("=> ★结论：还没重启过★ ✗ —— 起一次 Minecraft，我立刻重跑这条命令给结论 ✓")
    else:
        out.append("=> ★结论：CSL 加载了但没命中★ ✗ —— 请把它日志最后几行给我（上面已列 ✓）；"
                   "要查两件事：① 玩家名是不是 `Bot` ✓ ② 文件是不是 "
                   "`CustomSkinLoader/LocalSkin/skins/Bot.png` ✓")

    txt = "\n".join(out)
    (ROOT / "logs" / "skin_verdict.txt").write_text(txt, encoding="utf-8")
    print(txt)
    return 0


raise SystemExit(main())

# -*- coding: utf-8 -*-
"""skin_fix.py —— 用 CustomSkinLoader 的 **LocalSkin** 修"皮肤掉了"（离线可用 ✓ 不需要签名 ✓）

## 为什么原来那套不行 ✗（2026-09-26 实测 ✓ 证据都在）
  · 服务器侧其实**成功了** ✓：`/dshtskin status` 报 `textures_injected=true` ✓
    图也能取到（`http://127.0.0.1:8791/deepseek.png` ⇒ 200 / 2254 B ✓）
  · 但**客户端一次都没来取** ✗：`logs/skin_server.log` 里只有**我自己**用 PowerShell 请求的那一条 ✓
    （没有 Minecraft 的 UA ✗）—— 顺带纠正 ✓：客户端取图的判官**不是** `logs/skin_http.log` ✗
    （那文件根本不存在 ✗）；真判官是 `logs/skin_server.log`（服务 stdout ✓）
  · 真因 ✓：客户端走 **Yggdrasil 会话服务**校验皮肤属性 ⇒ 游戏日志反复报
    `Signature is missing from Property textures` ✗ ⇒ **未签名的 properties 被客户端拒收** ✗
    （离线/假人环境**签不了名** ✗ 这条路走不通 ✗）

## 这一版怎么修 ✓
  换一条**客户端侧**的路 ✓：`CustomSkinLoader` 的 `LocalSkin` 加载器 ✓
    · 它按**玩家名**去本地读皮肤文件 ✓ ⇒ 不需要 HTTP ✓ 不需要签名 ✓ 不依赖会话服务 ✓
    · 配置 ✓ `CustomSkinLoader/CustomSkinLoader.json` ⇒ `loadlist: ["LocalSkin"]` ✓
    · 皮肤文件 ✓ `CustomSkinLoader/LocalSkin/skins/Bot.png` ✓
  并把**服务器侧的注入清掉** ✗（两套别打架 ✓ 老账：BotSkin 与 dskskin 抢同一个 textures ✓）

判据 ✓：① jar 进 mods ✓ ② 配置与皮肤文件就位 ✓ ③ 服务器侧注入已清 ✓
  ④ 重启后看 `CustomSkinLoader/CustomSkinLoader.log` 里有没有 **LocalSkin 命中** ✓（那才是判官 ✓）
"""
from __future__ import annotations

import shutil
import sys, paths as PA
import urllib.request
from pathlib import Path

ROOT = PA.ROOT
GAME = PA.MC_HOME
URL = "https://cdn.modrinth.com/data/idMHQ4n2/versions/OLaesh5y/CustomSkinLoader_Universal-15.0.1.jar"
JAR = GAME / "mods" / "CustomSkinLoader_Universal-15.0.1.jar"
CFG_DIR = GAME / "CustomSkinLoader"
SKIN_SRC = ROOT / "skins" / "deepseek.png"
BOT_NAME = PA.BOT


def main() -> int:
    out = []
    # ① 下载（走 CDN ✓ 实测 api.modrinth.com 通 ✓）
    if JAR.is_file():
        out.append("① jar 已在: %s (%d B)" % (JAR.name, JAR.stat().st_size))
    else:
        try:
            with urllib.request.urlopen(URL, timeout=60) as r, JAR.open("wb") as f:
                shutil.copyfileobj(r, f)
            out.append("① 下载 ok: %s (%d B)" % (JAR.name, JAR.stat().st_size))
        except Exception as e:
            out.append("① ★下载失败★ %s: %s" % (type(e).__name__, e))
            print("\n".join(out).encode("ascii", "replace").decode("ascii"))
            return 1
    # ② 配置 + 皮肤文件
    sk_dir = CFG_DIR / "LocalSkin" / "skins"
    sk_dir.mkdir(parents=True, exist_ok=True)
    dst = sk_dir / ("%s.png" % BOT_NAME)
    if SKIN_SRC.is_file():
        shutil.copy2(SKIN_SRC, dst)
        out.append("② 皮肤文件: %s (%d B)  ← 来自 %s" % (dst.name, dst.stat().st_size, SKIN_SRC.name))
    else:
        out.append("② ★找不到源皮肤★ %s" % SKIN_SRC)
        return 1
    cfg = CFG_DIR / "CustomSkinLoader.json"
    cfg.write_text(
        '{\n'
        '  "enable": true,\n'
        '  "enableSkull": false,\n'
        '  "enableDynamicSkull": false,\n'
        '  "enableTransparentSkin": false,\n'
        '  "enableCape": false,\n'
        '  "cacheExpiry": 0,\n'
        '  "forceIgnoreHttpsCertificate": false,\n'
        '  "forceLoadAllTextures": true,\n'
        '  "threadPoolSize": 2,\n'
        '  "loadlist": [\n'
        '    { "name": "LocalSkin", "type": "LocalSkin", "skin": "LocalSkin/skins/{USERNAME}.png",\n'
        '      "model": "auto", "cape": "LocalSkin/capes/{USERNAME}.png",\n'
        '      "elytra": "LocalSkin/elytras/{USERNAME}.png" }\n'
        '  ]\n'
        '}\n', encoding="utf-8", newline="\n")
    out.append("② 配置: %s（loadlist 只有 LocalSkin ⇒ 不走网络 ✓ 不验签 ✓）" % cfg.name)
    print("\n".join(out).encode("ascii", "replace").decode("ascii"))
    print("=> next: 重启 Minecraft；判官 = %s 里的 LocalSkin 命中" % (CFG_DIR / "CustomSkinLoader.log"))
    return 0


raise SystemExit(main())

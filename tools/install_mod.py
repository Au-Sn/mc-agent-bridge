# -*- coding: utf-8 -*-
"""install_mod.py —— 验新 jar 里真有新东西 ✓ 然后装进游戏 mods/（旧的留备份 ✓）

纪律 ✓：
  · **先验、后装** ✗：`dshmap` ✓ `dshpath` ✓ `features=…,map,path` ✓ 三个字符串必须在 class 里找到 ✓
    （不然就是"装了个寂寞"✗ —— 而且重启一次游戏很贵 ✗ 不能靠猜 ✓）
  · **旧的绝不静默丢** ✗：先改名成 `.bak-<时间戳>` ✓ 再复制新的 ✓（P1/P5 那条老规矩 ✓）
  · 输出全 ASCII ✓（控制台是 GBK ✓ 见 P66 ✓）
"""
from __future__ import annotations

import re
import shutil
import sys
import time
import zipfile
from pathlib import Path

# ★出口编码★ ✗（2026-09-28 ✓）：本机控制台是 **GBK** ✗ ⇒ 一句带 `✓`/`✗` 的 print 就能
#   `UnicodeEncodeError` 崩掉整个脚本 ✗ —— 而且往往崩在**最后一行**✗
#   ⇒ 活儿已经干完了 ✗ 退出码却是 **1** ✗ ⇒ 骗人 ✓（P-family：错误路径没被走过就永不暴露 ✓）
#   口径二选一 ✓：**要么只打 ASCII** ✓（本脚本现在就是 ✓）
#                 **要么开头就 reconfigure** ✓（像 `mc_mcp_smoke.py` 那样 ✓）—— 这里两条都做 ✓
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ★★79.534（发布准备）✗★★：本机路径写死清掉 —— 换机器/上 GitHub 后按环境事实解析
#   ROOT：从本文件位置推（tools/ 的父目录）✓ 不再写死 C:\Users\...
#   MODS：一律走 tools/paths.py（env > dsh.env > 空/占位）✓ 不再写死 D:\pcl2\...
ROOT = Path(__file__).resolve().parent.parent
LIBS = ROOT / "mod" / "build" / "libs"
sys.path.insert(0, str(ROOT / "tools"))
import paths as PA          # noqa: E402  ★环境事实唯一入口（dsh.env / env / 默认）★

MODS = PA.MODS_DIR
NO_MODS_HINT = PA.UNCONFIGURED_HINT


def newest_jar():
    """★别再写死版本号★ ✗（2026-09-28 ✓）：每升一版都要来改一行 ✗ ⇒ 迟早忘 ✗
    口径 ✓：**先比版本号** ✓ 版本相同才比时间 ✓（同一版本重编过 ⇒ 取新的 ✓）
    """
    best = None
    for p in LIBS.glob("dshbridge-*.jar"):
        mm = re.search(r"dshbridge-(\d+)\.(\d+)\.(\d+)\.jar$", p.name)
        ver = tuple(int(g) for g in mm.groups()) if mm else (0, 0, 0)
        key = (ver, p.stat().st_mtime)
        if best is None or key > best[0]:
            best = (key, p)
    return best[1] if best else None


NEW = newest_jar()

NEED = ["dshmap", "dshpath", "features=scan,digest,look,walk,events,auto,map,path",
        "ASTAR_MAX_NODES", "ASTAR_EDGE_PENALTY", "standable",
        # ★v2.16：高度偏移 ＋ "你这一层被占"★ ✓（少了这两样 ⇒ 图又会被推平 ✗）
        #   ⚠ 别写 `ylegend=0:same` ✗（2026-09-28 栽过 ✓）：javac 里
        #     `.append(" ylegend=")` 与 YLEGEND 的**值是两个独立常量** ✗
        #     ⇒ 跨常量的子串**永远匹配不上** ✗ ⇒ 我把自己卡在"装不上"✗
        #     ⇒ 只写**单个常量内部**的子串 ✓
        "ylegend=", "0:same,A:+1,B:+2", "blevel=", "blocked=",
        # ★v2.17：落差口径统一 ＋ 到达判据"按格按层" ＋ 地板认碰撞箱顶高 ＋ 同层也印地板名★ ✓
        #   （★这是"装了个寂寞"的防线✗★：少了这几样 ⇒ **重启一次游戏就白费** ✗）
        "walk_refuse", "walk_relaxed", "max_drop=", "step_down=",
        # ★v2.18：只对 Bot 生效的死亡保险（保住背包 ＋ 送回安全落脚点 ★不会掉进虚空就捡不回★）★
        #   （少了这两样 ⇒ 装的是 v2.17 的 jar ⇒ **拒绝安装** ✓ 不浪费一次重启 ✓）
        "bot_died", "bot_revived",
        # ★★2.56.0（A3 HTTP 加固 ＋ A7 req trace ＋ N3 yaw 探针）★★
        #   ★为什么每一条都要✗★：装 jar 后只重启一次 ✗ 少了任意一样就是"装了个旧 jar" ✗✗
        "http_token.txt", "X-DSH-Token", "X-DSH-Req",
        "reason=missing_token", "reason=bad_token", "reason=origin_header",
        "reason=not_whitelisted", "httpWorldLane", "dsh-world-lane",
        "http2,token,origin,rawmap,reqid",
        "dshhttp", "dshreqs", "dshyawprobe",
        # ★★2.57.0（A2/S1 结构第二刀：HTTP 边界搬进 HttpBridge）★★
        #   ★这是"装的是新结构 jar"的锚✗★：主类里必须**调用**新类 ⇒ 两个字符串都要在 class 池里 ✓
        "com/dsh/bridge/HttpBridge", "HttpBridge",
        "httpEventServer", "httpEventError", "httpTokenLoadOrCreate",
        # ★★2.58.0（79.534 发布准备：环境事实收口）★★
        #   ★少了任意一样 = 装的是旧 jar（bot 名/端口还写死）✗★
        "ModConfig", "dshbridge.bot", "dshbridge.port", "dshbridge.tokenFile", " bot="]


def main() -> int:
    if not NEW.is_file():
        print("NO JAR:", NEW)
        return 2
    if not MODS.is_dir():
        # ★79.534✗★：不再写死本机路径 —— 按 paths.py 解析；没配就**明确报错 + 指向文档** ✓
        print("NO MODS DIR:", MODS)
        print("hint:", NO_MODS_HINT)
        print("      configure MC_HOME in dsh.env (or set env MC_HOME), see INSTALL.md (repo root)")
        return 2
    blob = b""
    with zipfile.ZipFile(NEW) as z:
        names = z.namelist()
        for n in names:
            if n.endswith(".class"):
                blob += z.read(n)
    txt = blob.decode("utf-8", "ignore")
    missing = [k for k in NEED if k not in txt]
    # ★print 一律 ASCII★ ✗（2026-09-28 栽过 ✓）：这份脚本**文件头**就写着"输出全 ASCII"
    #   却一直在 print 中文 ＋ `✓`/`✗` ✗ ⇒ 在 GBK 控制台上**直接崩 UnicodeEncodeError** ✗
    #   而且崩的是**最后一行** ⇒ **jar 已经装好了**✗ 退出码却是 **1** ✗ ⇒ 骗人 ✗
    #   （P-family："错误路径从没被走到"⇒ 就一直没暴露 ✓）
    print("jar=%s (%d B) | classes=%d | key strings %d/%d %s"
          % (NEW.name, NEW.stat().st_size,
             len([n for n in names if n.endswith('.class')]),
             len(NEED) - len(missing), len(NEED),
             "all present OK" if not missing else ("MISSING: %s" % missing)))
    if missing:
        print("=> NOT installed (the new bits are not in this jar; "
              "installing would waste a restart)")
        return 1
    old = sorted(MODS.glob("dshbridge*.jar"))
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for o in old:
        if o.name == NEW.name:
            continue
        bak = o.with_suffix(o.suffix + ".bak-" + stamp)
        o.rename(bak)
        print("backed up: %s -> %s" % (o.name, bak.name))
    dst = MODS / NEW.name
    shutil.copy2(NEW, dst)
    print("installed: %s (%d B)" % (dst.name, dst.stat().st_size))
    print("dshbridge jars now in mods/:")
    for p in sorted(MODS.glob("dshbridge*")):
        print("   %s  %d B" % (p.name, p.stat().st_size))
    print("=> restart Minecraft to load %s (I will verify with /dshver afterwards)"
          % NEW.name.replace("dshbridge-", "").replace(".jar", ""))
    return 0


raise SystemExit(main())

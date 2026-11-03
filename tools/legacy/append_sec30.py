# -*- coding: utf-8 -*-
"""append_sec30.py —— 交接 §30：本次目标（地图/寻路/中间层）的收官账

纪律 ✓：数字都来自本轮的实测回执 ✓ 不写"应该/大概"✗；没做完的**明确列出来** ✗ 不含糊 ✓
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]    # tools/legacy/ -> 仓库根（不写死本机路径）
DOC = ROOT / "docs" / "当前阶段-状态与交接.md"

ADD = """
---

## 30. 目标收官账（2026-09-28 ✓ 第 14 轮 ✓）：★地图读取 / 寻路 / 中间层★

**一句话** ✓：三条主线都落地并被**世界真值**验收过 ✓ 合并验收 **`py tools\\check_all.py` ⇒ 8/8 ALL PASS** ✓

### 30.1 合并验收（一次跑完 8 项 ✓ 这就是"当前能不能用"的唯一入口 ✓）

| 脚本 | 验什么 | 结果 |
|---|---|---|
| `floor_test.py` | 形状家族：能踩/挡人（确定性 10+12 例 ✓） | **PASS** ✓ |
| `ob_unit_test.py` | 道中障碍：探得出/绕得开/预算诚实/读失败即收手（**离线** ✓） | **PASS** ✓ |
| `r2_guard_test.py` | 虚空守卫（手工造图 ✓ 不靠现实碰巧 ✓） | **PASS** ✓ |
| `r8_guard_test.py` | 长走拦截（>8 格拒发 ✓ 真走对照 ✓） | **PASS** ✓ |
| `r9_target_guard_test.py` | 目标站不住拦截（手工造洞 ＋ 真 2 格对照 ✓） | **PASS** ✓ |
| `m1_verify.py` | 地图 M1~M4（抽查 14/14 ✓ 冷建 42 次/27 秒 ✓ 热 0.00 秒 ✓） | **PASS** ✓ |
| `r2_verify.py` | 寻路 P0~P5：3/3 到位 ✓ 每步验真值 ✓ 假人平安 ✓ | **PASS** ✓ |
| `r3_verify.py` | 提速 A/B T1~T3 ＋ **对比有效性闸** ✓ | **PASS** ✓ |

（`check_all` 现在会**自己挂/撤 `logs/relay_hold`** ✓ 免得中继的自动续跑把假人挪走搅黄判据 ✓）

### 30.2 ① 地图读取 ✓

- **`/dshmap`（v2.15 ✓ 一次调用一张图）** ✓：实测 **2 次调用 / 0.8 秒 / 988 个可站格 /
  图例 32 种方块** ✓ —— 对比老的"按方块种类扫描"**43 次 / 37.6 秒**且**只有 top-40** ✗
  ⇒ 稀有方块（`computercraft:computer_command` 那类）**不再丢** ✓ 这就是"地图完整性"的正解 ✓
- **形状家族分类** ✓（用户点的方向「除栅栏一类非完整方块和正常方块」✓）：
  `shape()` 归成 air/liquid/pass/canopy/fence/slab/machine/full ✓ 一份实现推出
  `is_floor` / `blocks_space` ✓ 取代原来两张名字表 ✗（还被 `mcwfences:…_wall` 冤枉过 ✓）
  ＋ `EXACT_PASS` 处理"同名不同命"（`grass` vs `grass_block`）✓
- **ASCII 视图/缓存** ✓：`map_area` 走快图（半径 24 ✓ 1.7 秒 ✓ 图例 47 种 ✓）；
  磁盘 + 进程内双层缓存 ✓；**任务图**跨段复用 ✓（曾因一个 4 元组/6 元组下标写错 ⇒
  每段重建 30 秒 ✗ 修好后 8 段 8 建 → **0 建** ✓）

### 30.3 ② 寻路优化 ✓

- **假 unreachable 修掉了** ✓（v2.15：搜索框改成罩住**起点＋终点** ✓）——
  实测 `/dshpath 4132 71 18` ⇒ `legs=10 ms=0 reachable=true` ✓（老代码在起点离目标 >30 格时
  会连起点邻居都判出界 ✗）
- **单发长走的两道闸** ✓（空岛实测掉过**两次虚空** ✗ 丢掉钻石一批 ＋ 麦子/种子 ✗）：
  · `walk_to` **>8 格一律拒** ✓ 并指路 `walk_route` ✓
  · `walk_to` 到**站不住**的格也拒 ✓（拒之前用一次 1x1 独立读取**复核** ✓ 不许靠近似拒 ✗）
- **`walk_route`** ✓：全局规划 ⇒ 拆跳(≤8) ⇒ **每跳验真实位置** ⇒ 偏了重规划 ✓
  A/B（同一条 5~7 格路 ✓ 两边都 3/3 成功 ✓）：老 `walk_to` 4 秒/段 ✓ 新路 7~22 秒/段 ✗
  ★价格拆开量过★ ✗：**验真值 ≈ +3 秒/段** ✓ **探路 ≈ +5 秒/段**（可用 `sweep=0` 关 ✓）
  —— 用户原话「重点是识别道中的障碍物，不一定说一定要快」✓ ⇒ 这是**点名的取舍** ✓
- **障碍识别 ＋ 记忆** ✓：走之前逐格独立探（脚层＋头层 ✓）⇒ 撞见挡人的 ⇒
  记进 `logs/obstacles.json` ✓（跨进程有效 ✓ **24 小时过期** ✓ 免得永久封锁一块地 ✗）
  ⇒ 同一个障碍**不重探** ✓（实测探路次数 16 → 10 ✓）

### 30.4 ③ 中间层拓展 ✓

- **MCP 工具 17 → 32 件** ✓：`map_area` `find_block`(带中文别名：桶/箱子/田/水/电脑…) `plan_route`
  `walk_route` `safe_spots` `survey` `remember` `check_path` `job_open/list/step/close`
  `chest_peek/put/take` ✓
- **长任务账本** ✓（`jobs/*.json`）：目标/状态/下一步/每步证据 ✓；中继**没人催也自己推** ✓
  （`logs/relay_hold` 可暂停 ✓）；`wait_s` 到点再动 ✓；同一件事**开重复账会先警告** ✓
- **中继** ✓：人设/实况/上下文任务书 ✓「说了就得做」强制重做 ✓「催它干活」单独一组 ✓（不许反问"要不要我做"）
  ；`saved`：记忆去重 ✓、重启不重放（`logs/acp_seen.txt` ✓ 修前重启会把旧指令**再执行一遍** ✗）

### 30.5 ★还没做完的（明确留账 ✗ 下一轮继续 ✓）★

1. **两模式测试跑完整** ＋ 把 `M2'`（探路 ≤5 秒/段）改成**多段中位数**（单次采样噪声大 ✗
   实测同一条路 5.2 / 7.7 秒都出现过 ✓）—— 这是**判据形状**问题 ✓ 不是放宽 ✓
2. **`survey` 勘察半径提到 24~32** ✓（快图一次调用就够 ✓ 现在仍卡在 14~20 的实现路径上 ✓）
3. **`walk_to` 的 8 格闸要不要重估** ✓：脚本 `tools/w1_gate_test.py` 已就绪（判据 W1a~W1d ✓）
   —— ★要用户拍板★ ✗：它会放开闸让假人走**贴边路线**（v2.15 的贴边惩罚正是冲它加的 ✓），
   有掉虚空风险（身上只有麦子/种子 ✓ 能再收 ✓）
4. **长任务还缺一只手**：往容器里**成批**存取（现在 `chest_put/take` 一次一种 ✓）⇒ 产线/整理类
   长任务会卡在这一步 ✓

### 30.6 现场怎么起（一条口令 ✓）

```powershell
py tools\\start_all.ps1                 # 网关端口见 dsh.env（默认见 paths.GATEWAY_PORT）＋ 皮肤:8791 ＋ 镜像:8789 ＋ 常驻会话 ＋ 中继
py tools\\start_all.ps1 -ReloadMcp      # ★改过 tools/mc_mcp.py 之后必须带这个★ ✗（MCP 是常驻进程 ✓）
py tools\\check_all.py                  # 8 项合并验收（会自己暂停/恢复中继 ✓）
py tools\\respawn_bot.py                # 假人不在就拉回来
py tools\\skin_verdict.py               # 皮肤到底成没成（三个判官一起看 ✓）
```

**皮肤现状** ✓：走**客户端侧** `CustomSkinLoader` 的 `LocalSkin` ✓（按玩家名读本地 PNG ✓
不发 HTTP ✗ 不验签 ✗）—— 实测 CSL 日志 `1/1 Try to load profile from 'LocalSkin'` ＋
`Bot's profile loaded` ✓ 且未签名属性那条路已**清零**（`Signature is missing` 3 → 0 ✓）
　加皮肤 ✓：覆盖 `CustomSkinLoader\\LocalSkin\\skins\\Bot.png`（64×64 RGBA）⇒ 重启 ✓
"""

txt = DOC.read_text(encoding="utf-8")
DOC.write_text(txt.rstrip() + "\n" + ADD, encoding="utf-8", newline="\n")
print("sec30 written, lines =", len(DOC.read_text(encoding="utf-8").splitlines()))

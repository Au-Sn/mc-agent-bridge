# -*- coding: utf-8 -*-
"""append_sec29.py —— 把交接 §29 追加到 docs/当前阶段-状态与交接.md

为什么不直接在命令行里写 ✗：中文 + 多行 + 引号 经 PowerShell 5.1 必坏 ✗（P83/P91 家族 ✓）
  ⇒ 老老实实**写成文件**再跑 ✓（这就是本轮 git 提交信息那次教训的正解 ✓）
"""
from pathlib import Path

import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


ROOT = Path(__file__).resolve().parents[2]    # tools/legacy/ -> 仓库根（不写死本机路径）
DOC = ROOT / "docs" / "当前阶段-状态与交接.md"

ADD = """
---

## 29. 自主迭代第五轮（2026-09-23 深夜 ✓ 目标第 10 轮 ✓）：★git 上了 ＋ 道中障碍识别★

### 29.1 git（用户提醒后立刻补的 ✓）

- `git init` ＋ `.gitignore`（忽略 build/jdk/mirrorcache/日志/依赖 ✓ 保留 docs/tools/jobs/memory/personas/skins/mod-src ✓）
- 两次提交 ✓：`59cbbd7` 初始入库（1414 个文件 ✓）、`f52e613` 本轮改动 ✓ 工作区干净 ✓
- 提交信息一律**写进文件再 `git commit -F`** ✗ —— 中文带引号直接塞命令行会被 PowerShell 撕碎 ✓
  （实测栽了一次 ✓ 见 P97 家族 ✓）

### 29.2 道中障碍识别（用户点的方向 ✓ 比"快"更重要 ✓）

**为什么这是必须的** ✗：地图是**按方块种类**建的 ✓ 而模组回执的 `counts[...]` **只列 top-40** ✗
  ⇒ **稀有方块根本不在图里** ✗（实测：假人重生点那格有 `computercraft:computer_command` ✓
    地图完全不知道它 ✓ 还因此判「那格上面是空的」✗）
  ⇒ **「图上没障碍」≠「道上没障碍」** ✗ ⇒ 必须**走之前实地探一遍** ✓

| 新东西 | 作用 |
|---|---|
| `mapread.scan_route(m, pts, level, budget, pace)` ✓ | 把这条路每格**独立读**脚层＋头层 ⇒ 报出**真障碍** ✓ 并写进图 ✓ |
| `pathplan.Planner(blocked=…)` ✓ | 把探到的挡路格记进来 ✓ **规划时绕开** ✓ |
| `t_check_path(x,y,z)` ✓（第 **32** 件工具） | 规划 ＋ 探路 ＋ 报障碍 ＋ **绕开后再规划** ✓（**不动手** ✓） |
| `walk_route` 每跳先探 6 格 ✓ | 撞到障碍 ⇒ 记下来 ⇒ **立刻重规划绕开** ✓ |
| `tools/ob_unit_test.py` ✓（**离线** ✓） | O1~O5 确定性验收 ✓ 不需要游戏 ✓ 桥断了也能跑 ✓ |

**实测（离线 ✓）**：O1 探出 `computercraft:computer_command` 并写进图 ✓
｜ O2 绕得开（6 航点 ✓ 路线不含障碍格 ✓）｜ O3 预算诚实（探 6/30 ✓ 报「还有 24 格没探」✓）
｜ O4 **读失败即收手**（第 3 次失败 ⇒ 只发 3 次 ⇒ `aborted=True` ✓）｜ O5 有节流 ✓ ⇒ **PASS** ✓

### 29.3 这一轮的阻塞（需要用户 ✓）

**Minecraft 在 10:37 被关掉了** ✗（游戏日志：`All dimensions are saved` ✓ `Stopping worker threads` ✓
  `FTB Chunks … Shutting down map thread` ✓ 之后 `cmd0` 就不再取指令 ⇒ 队列堆到 16 ✗）
⇒ 依赖世界的判据暂时**跑不了** ✓（`check_all --no-walk` 现在 **3/6** ✓ ——
  过的正好是**不依赖世界**的那三个：地板 ✓ 虚空守卫 ✓ 道中障碍（离线）✓）

**要做的事** ✓：
1. **把 Minecraft 起回来**（进世界 ✓ 起来后我会：`start_all.ps1 -ReloadMcp` ⇒ 拉假人 ⇒
   `check_all` 跑全套 ⇒ 用真世界里 `computercraft:computer_command` 那格**再验一次探路** ✓）
2. v2.15 仍要 **gradle 发行版或网络**（源码已 javac 验过 ✓ 见 §26.1 ✓）
"""

txt = DOC.read_text(encoding="utf-8")
DOC.write_text(txt.rstrip() + "\n" + ADD, encoding="utf-8", newline="\n")
print("交接 §29 已写入 ✓ 现在总行数 =", len(DOC.read_text(encoding="utf-8").splitlines()))

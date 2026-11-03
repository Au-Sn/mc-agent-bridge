# 盘点 · `cc-tweaked/agent_bridge.lua` 的职责（欠账 ②）

> 生成：**2026-10-02** ✓ 由 `tmp/lua_inventory.py` 机器生成 ✗ 裁定留人手填 ✓
> 口径 ✓：**外部**＝`tools/`·`agent/` 的 `.py` 里按名字调它 ✓；**内部**＝`.lua` 里别处提到它 ✓；
> ★两处都是 0 ⇒ **零引用**✗★ —— ★但「零引用」只是**冻结候选** ✗ 因为 Lua 可能有动态调用 ✓★
> ★当前总账✗★：**71 个导出函数** ⇒ ★在役 35 ✗ 仅内部 23 ✗ 零引用 13✗★

## 一、★在役✗★（外部有活调用 ⇒ ★不许动 ✗ 要么留着 ✓ 要么按拍板**移植进模组**✓★）

| 函数 | 行 | 外部 | 内部 | 现状 | 裁定（待填 ✓） |
|---|---|---|---|---|---|
| `cmd` | 435 | 41 | 35 | 在役（★外部有活调用✗★ ✓ channel.py,entity_nbt_diff.py,extend_outward.py） | ★待定✗★ |
| `cmd_async` | 468 | 1 | 0 | 在役（★外部有活调用✗★ ✓ channel.py） | ★待定✗★ |
| `survey` | 509 | 13 | 5 | 在役（★外部有活调用✗★ ✓ extend_outward.py,mc_mcp.py,mc_mcp_smoke.py） | ★待定✗★ |
| `bot_inv` | 719 | 6 | 9 | 在役（★外部有活调用✗★ ✓ blueprint.py,channel.py,hotbar.py） | ★待定✗★ |
| `hold_item` | 786 | 8 | 10 | 在役（★外部有活调用✗★ ✓ jobs.py,replant.py,sift_loop.py） | ★待定✗★ |
| `use_once` | 826 | 2 | 7 | 在役（★外部有活调用✗★ ✓ sift_loop.py） | ★待定✗★ |
| `walk_to` | 940 | 24 | 15 | 在役（★外部有活调用✗★ ✓ extend_outward.py,mc_mcp.py,mc_mcp_smoke.py） | ★待定✗★ |
| `block_state` | 1084 | 1 | 1 | 在役（★外部有活调用✗★ ✓ channel.py） | ★待定✗★ |
| `crosshair` | 1276 | 4 | 5 | 在役（★外部有活调用✗★ ✓ bench_v26.py,deploy.py,skills.py） | ★待定✗★ |
| `jade` | 1477 | 3 | 10 | 在役（★外部有活调用✗★ ✓ deploy.py） | ★待定✗★ |
| `give_slot` | 1631 | 5 | 0 | 在役（★外部有活调用✗★ ✓ extend_outward.py,plan_platform.py,skills.py） | ★待定✗★ |
| `install_mesh` | 1665 | 3 | 0 | 在役（★外部有活调用✗★ ✓ plan_platform.py,skills.py） | ★待定✗★ |
| `place_at` | 1709 | 2 | 2 | 在役（★外部有活调用✗★ ✓ plan_platform.py,skills.py） | ★待定✗★ |
| `sift` | 1743 | 15 | 2 | 在役（★外部有活调用✗★ ✓ jobs.py,mc_mcp.py,mc_mcp_smoke.py） | ★待定✗★ |
| `dig_at` | 1907 | 4 | 5 | 在役（★外部有活调用✗★ ✓ bench_v27.py,jobs.py,skills.py） | ★待定✗★ |
| `place_adjacent` | 1944 | 2 | 4 | 在役（★外部有活调用✗★ ✓ skills.py） | ★待定✗★ |
| `build_platform` | 2023 | 1 | 2 | 在役（★外部有活调用✗★ ✓ plan_platform.py） | ★待定✗★ |
| `extend_platform` | 2092 | 2 | 5 | 在役（★外部有活调用✗★ ✓ extend_outward.py） | ★待定✗★ |
| `sneak_place` | 2234 | 3 | 3 | 在役（★外部有活调用✗★ ✓ skills.py） | ★待定✗★ |
| `chop_tree` | 2322 | 2 | 1 | 在役（★外部有活调用✗★ ✓ skills.py） | ★待定✗★ |
| `dig` | 2481 | 3 | 15 | 在役（★外部有活调用✗★ ✓ skills.py） | ★待定✗★ |
| `place` | 2487 | 5 | 6 | 在役（★外部有活调用✗★ ✓ memory3.py,plan_platform.py,skills.py） | ★待定✗★ |
| `attack` | 2493 | 2 | 9 | 在役（★外部有活调用✗★ ✓ reflex.py,skills.py） | ★待定✗★ |
| `drop` | 2495 | 2 | 1 | 在役（★外部有活调用✗★ ✓ skills.py） | ★待定✗★ |
| `status` | 2518 | 48 | 11 | 在役（★外部有活调用✗★ ✓ bench_v26.py,bench_v27.py,bench_v28.py） | ★待定✗★ |
| `scan` | 2575 | 33 | 10 | 在役（★外部有活调用✗★ ✓ brain.py,jobs.py,mc_mcp.py） | ★待定✗★ |
| `inv_list` | 2616 | 2 | 3 | 在役（★外部有活调用✗★ ✓ recover.py） | ★待定✗★ |
| `locate` | 2672 | 3 | 3 | 在役（★外部有活调用✗★ ✓ skills.py） | ★待定✗★ |
| `say` | 2704 | 10 | 5 | 在役（★外部有活调用✗★ ✓ mc_mcp.py,mc_mcp_smoke.py,plan_platform.py） | ★待定✗★ |
| `shutdown` | 2731 | 3 | 4 | 在役（★外部有活调用✗★ ✓ dsh_live.py,dsh_live2.py,dsh_live3.py） | ★待定✗★ |
| `snapshot` | 2929 | 7 | 3 | 在役（★外部有活调用✗★ ✓ bench_v26.py,blueprint.py,jobs.py） | ★待定✗★ |
| `blueprint_build` | 3018 | 1 | 1 | 在役（★外部有活调用✗★ ✓ blueprint.py） | ★待定✗★ |
| `path_plan` | 3378 | 1 | 13 | 在役（★外部有活调用✗★ ✓ speech.py） | ★待定✗★ |
| `path_follow` | 3572 | 1 | 12 | 在役（★外部有活调用✗★ ✓ skills.py） | ★待定✗★ |
| `self_update` | 3932 | 1 | 2 | 在役（★外部有活调用✗★ ✓ deploy.py） | ★待定✗★ |

## 二、仅 Lua 内部用（★外部 0✗★ ⇒ ★上层不再依赖它 ✗ 可随上层一起冻结✓★）

| 函数 | 行 | 内部 | 裁定（待填 ✓） |
|---|---|---|---|
| `calibrate` | 326 | 2 | ★待定✗★ |
| `probe_order` | 663 | 1 | ★待定✗★ |
| `plant_sapling` | 837 | 1 | ★待定✗★ |
| `blocks_around` | 1520 | 2 | ★待定✗★ |
| `suck` | 2497 | 1 | ★待定✗★ |
| `select` | 2504 | 4 | ★待定✗★ |
| `refuel` | 2511 | 1 | ★待定✗★ |
| `players` | 2550 | 3 | ★待定✗★ |
| `block_info` | 2600 | 2 | ★待定✗★ |
| `inv_man` | 2628 | 1 | ★待定✗★ |
| `player_pos` | 2651 | 1 | ★待定✗★ |
| `geo_status` | 2665 | 1 | ★待定✗★ |
| `discover_turtles` | 2684 | 3 | ★待定✗★ |
| `chat_read` | 2712 | 1 | ★待定✗★ |
| `quit` | 2725 | 2 | ★待定✗★ |
| `pebble_farm` | 2831 | 1 | ★待定✗★ |
| `step_to` | 3812 | 3 | ★待定✗★ |
| `nest_probe` | 3878 | 2 | ★待定✗★ |
| `reboot` | 3951 | 3 | ★待定✗★ |
| `rediscover` | 3962 | 1 | ★待定✗★ |
| `broadcast_cmd` | 3974 | 1 | ★待定✗★ |
| `peripheral_api` | 4002 | 5 | ★待定✗★ |
| `sleep` | 4015 | 52 | ★待定✗★ |

## 三、★零引用 ⇒ 冻结候选✗★（★先确认没有动态调用✗★）

| 函数 | 行 |
|---|---|
| `turn_left` | 312 |
| `turn_right` | 319 |
| `probe_bulk` | 620 |
| `dig_up` | 2483 |
| `dig_down` | 2485 |
| `place_up` | 2489 |
| `place_down` | 2491 |
| `suck_up` | 2499 |
| `suck_down` | 2501 |
| `place_face` | 2753 |
| `go_relative` | 4022 |
| `tunnel` | 4059 |
| `mine_column` | 4086 |

## 四、★与本项目已拍板的关系✗★

- ★`dig_at`（行 1907）**正式冻结**✗★（用户 2026-10-02 拍板 ✓）：
  ★模组侧 `/dshdig` 已按「玩家语义」修好（掉战利品 ✓ 回读世界真值 ✓）✗
  余下 ★把「按方块名挑工具」移植进模组✗★ ⇒ ★这条做完 ⇒ `dig_at` 的外部调用可以删✓★
- ★`walk_to` / `path_plan` / `path_follow` / `step_to`✗★：★模组侧 `/dshwalk` 已经接管**走路**✓★
  ⇒ ★逐条核对「还有谁在调」✗ ✗ 没有就一起冻结 ✓★
- ★盘点口径的局限（据实✗）★：★「零引用」≠「没人用」✗★ —— ★本文件内部有 `A.x(...)` 形式的调用 ✓
  ★`pcall`／字符串拼名的动态调用**看不见** ✗ ⇒ ★冻结前必须**按名字全文搜一遍**✗（含 `_G` ✓）★

## 五、★「零引用 13 条」的全文复核结果✗★（2026-10-02 ✓ 由 `tmp/lua_zero_check.py` 生成 ✓）

> 口径 ✓：★在**全仓**（含 `logs/` ✓ `cc-tweaked/` ✓ `kubejs/` ✓ `docs/` ✓）按名字搜 ✗
> ★只有「确实零引用」才保留**冻结候选**✗ ✗ 否则撤出候选并**写出在哪被用**✓★

| 函数 | 行 | 复核结论 |
|---|---|---|
| `turn_left` | 312 | ★**有人用**✗★：`agent\action_schema.json`×1, `agent\skills.py`×1, `cc-tweaked\agent_bridge.lua`×1, `cc-tweaked\install.md`×1 |
| `turn_right` | 319 | ★**有人用**✗★：`agent\action_schema.json`×1, `agent\skills.py`×1, `cc-tweaked\agent_bridge.lua`×1, `cc-tweaked\install.md`×1 |
| `probe_bulk` | 620 | ★**有人用**✗★：`agent\action_schema.json`×1, `cc-tweaked\agent_bridge.lua`×1, `docs\盘点-Lua桥职责.md`×1, `bridge\processed\W1-probe-bulk.json`×1 |
| `dig_up` | 2483 | ★**有人用**✗★：`agent\action_schema.json`×1, `agent\skills.py`×1, `cc-tweaked\agent_bridge.lua`×1, `cc-tweaked\install.md`×1 |
| `dig_down` | 2485 | ★**有人用**✗★：`agent\action_schema.json`×1, `agent\skills.py`×1, `cc-tweaked\agent_bridge.lua`×1, `cc-tweaked\install.md`×1 |
| `place_up` | 2489 | ★**有人用**✗★：`agent\action_schema.json`×1, `agent\skills.py`×1, `cc-tweaked\agent_bridge.lua`×1, `cc-tweaked\install.md`×1 |
| `place_down` | 2491 | ★**有人用**✗★：`agent\action_schema.json`×1, `agent\skills.py`×1, `cc-tweaked\agent_bridge.lua`×1, `cc-tweaked\install.md`×1 |
| `suck_up` | 2499 | ★**有人用**✗★：`agent\action_schema.json`×1, `cc-tweaked\agent_bridge.lua`×1, `cc-tweaked\install.md`×1, `cc-tweaked\turtle_worker.lua`×1 |
| `suck_down` | 2501 | ★**有人用**✗★：`agent\action_schema.json`×1, `cc-tweaked\agent_bridge.lua`×1, `cc-tweaked\install.md`×1, `cc-tweaked\turtle_worker.lua`×1 |
| `place_face` | 2753 | ★**有人用**✗★：`agent\action_schema.json`×1, `cc-tweaked\agent_bridge.lua`×1, `docs\盘点-Lua桥职责.md`×1, `docs\蓝图大炮-仿制与站位几何.md`×1 |
| `go_relative` | 4022 | ★**有人用**✗★：`agent\action_schema.json`×1, `agent\run.py`×1, `cc-tweaked\agent_bridge.lua`×1, `cc-tweaked\install.md`×1 |
| `tunnel` | 4059 | ★**有人用**✗★：`agent\action_schema.json`×1, `agent\skills.py`×3, `cc-tweaked\agent_bridge.lua`×1, `cc-tweaked\install.md`×4 |
| `mine_column` | 4086 | ★**有人用**✗★：`agent\action_schema.json`×1, `agent\skills.py`×2, `cc-tweaked\agent_bridge.lua`×1, `cc-tweaked\install.md`×1 |

★总账✗★：★确实零引用 **0** 条 ✓ ／ 其实有人用 **13** 条 ✗★

## 六、★换口径重判：可达性（★因为「按名字派发」✗ ⇒ 引用数法作废✓）✗★

## 七、★逐条裁定（★证据三列✗★ 2026-10-02 ✓）

> 口径 ✓：★「谁还在调」数的是**带引号的名字**✗（真调用 ✓ 不是 schema 登记 ✓）；
> 「模组有没有对应」是在 `DshBridgeMod.java` 里找那条 `dsh<别名>` ✗★
> ★结论✗★：★有对应 ＋ 还有调用 ⇒ 可移植待改上层 ✗ 有对应 ＋ 没调用 ⇒ **已可冻结**✗★

| Lua 动作 | 模组对应 | 层内直调处 | 谁在调 | 裁定 |
|---|---|---|---|---|
| `dig_at` | `dshdig` | 3 | bench_v27.py, jobs.py, skills.py | ★**可移植 ✗ 待改上层**✗★（★模组已有 `dshdig` ✗ 但还有 3 处在直调✗★） |
| `place_adjacent` | `dshplace` | 1 | skills.py | ★**可移植 ✗ 待改上层**✗★（★模组已有 `dshplace` ✗ 但还有 1 处在直调✗★） |
| `hold_item` | `dshequip` | 4 | jobs.py, replant.py, sift_loop.py | ★**可移植 ✗ 待改上层**✗★（★模组已有 `dshequip` ✗ 但还有 4 处在直调✗★） |
| `walk_to` | `dshwalk` | 12 | extend_outward.py, mc_mcp.py, mc_mcp_smoke.py | ★**可移植 ✗ 待改上层**✗★（★模组已有 `dshwalk` ✗ 但还有 12 处在直调✗★） |
| `path_plan` | `dshpath` | 1 | speech.py | ★**可移植 ✗ 待改上层**✗★（★模组已有 `dshpath` ✗ 但还有 1 处在直调✗★） |
| `path_follow` | `dshwalk` | 1 | skills.py | ★**可移植 ✗ 待改上层**✗★（★模组已有 `dshwalk` ✗ 但还有 1 处在直调✗★） |
| `step_to` | `dshwalk` | 0 | （无 ✓） | ★**已可冻结**✗★（★模组有 `dshwalk` ✗ 上层不再直调✓★） |
| `crosshair` | `dshlook` | 3 | bench_v26.py, deploy.py, skills.py | ★**可移植 ✗ 待改上层**✗★（★模组已有 `dshlook` ✗ 但还有 3 处在直调✗★） |
| `status` | `dshdigest` | 21 | bench_v26.py, bench_v27.py, bench_v28.py | ★**可移植 ✗ 待改上层**✗★（★模组已有 `dshdigest` ✗ 但还有 21 处在直调✗★） |
| `survey` | `dshdigest` | 8 | extend_outward.py, mc_mcp.py, mc_mcp_smoke.py | ★**可移植 ✗ 待改上层**✗★（★模组已有 `dshdigest` ✗ 但还有 8 处在直调✗★） |
| `probe_bulk` | `dshscan` | 0 | （无 ✓） | ★**已可冻结**✗★（★模组有 `dshscan` ✗ 上层不再直调✓★） |
| `block_state` | `dshscan` | 1 | channel.py | ★**可移植 ✗ 待改上层**✗★（★模组已有 `dshscan` ✗ 但还有 1 处在直调✗★） |
| `sift` | `—` | 11 | jobs.py, mc_mcp.py, mc_mcp_smoke.py | ★留在 Lua ✗ 或缺模组命令✗★（★还有 11 处在调 ✗ 我没有对应命令 ✓） |
| `chop_tree` | `—` | 1 | skills.py | ★留在 Lua ✗ 或缺模组命令✗★（★还有 1 处在调 ✗ 我没有对应命令 ✓） |
| `sneak_place` | `—` | 1 | skills.py | ★留在 Lua ✗ 或缺模组命令✗★（★还有 1 处在调 ✗ 我没有对应命令 ✓） |
| `install_mesh` | `—` | 2 | plan_platform.py, skills.py | ★留在 Lua ✗ 或缺模组命令✗★（★还有 2 处在调 ✗ 我没有对应命令 ✓） |
| `give_slot` | `—` | 3 | extend_outward.py, plan_platform.py, skills.py | ★留在 Lua ✗ 或缺模组命令✗★（★还有 3 处在调 ✗ 我没有对应命令 ✓） |
| `place_at` | `—` | 2 | plan_platform.py, skills.py | ★留在 Lua ✗ 或缺模组命令✗★（★还有 2 处在调 ✗ 我没有对应命令 ✓） |

★怎么用这张表✗★：
- ★「已可冻结」✗★ 的那几条 ⇒ ★上层已经不再直调 ✗ 可以正式冻结（★保留代码 ✗ 不许再新增职责✓★）
- ★「可移植待改上层」✗★ 的那几条 ⇒ ★它们是 **⑫** 的输入 ✗ 改完上层就变成「已可冻结」✗★
- ★「留在 Lua」✗★ 的（★`sift`／`chop_tree`／`sneak_place`／`install_mesh`／`give_slot`／`place_at`✗★）
  ⇒ ★要么**留在 Lua**（★它做得挺好 ✓ 别为了统一而重写✗★）✗ 要么**另立模组命令**✗ ——
  ★判据是「模组能不能做得**更好**」✗ ✗ 不是「能不能做得**一样**」✓★


> ★方法结论✗★：`agent/channel.py` 的派发是**运行期按名字**的 ✗（`action_args(cmd)` ✓
> 而 `agent/skills.py:942` 是 `ch.call(**cand**, args)` ✗）⇒ ★「有没有人调用」grep 不出来✗★
> ⇒ 改用★**可达性**✗★：在 `agent/action_schema.json` 里 ⇒ 脑叫得到 ⇒ **在役** ✓；
> 不在 schema 但有**代码硬调用** ⇒ 在役 ✓；★两者都没有 ⇒ **不可达** ✗ 才是冻结候选✓★

| 档 | 数量 | 含义 |
|---|---|---|
| ★在役 · schema✗★ | **71** | ★脑能叫到 ✗ 不许动✓★ |
| ★在役 · 代码硬调用✗★ | **0** | ★上层直调 ✗ 不许动✓★ |
| ★**不可达✗**★ | **0** | ★真正的冻结候选 ✗ —— ★但动手前仍须按名字全文搜一遍✗（含 `_G` ✓）★ |

★不可达清单✗★：**空** ✓ ⇒ ★71 个导出函数**全都可达**✗★ ✓

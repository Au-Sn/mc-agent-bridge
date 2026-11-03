# PACK-PORTING — 换整合包 / 换存档上手指南（跨包就绪层，2026-11-03）

> 目标（用户口径）：**"哪怕是一个勉强能用的，也不能只在一个 1.20.1 的 ATM9 整合包里运行。"**
>
> 结论先说：**代码本身不绑定整合包**（模组源码 0 处整合包引用；`tools/*.py` 也没有具体 mod
> 关键词）。真正要换的是两类东西：
> ① **离线数据**（方块/标签/配方/例外/导出快照）—— 用 bootstrap 从当前整合包重新生成；
> ② **世界常量**（重生锚点/浸泡锚点/测试平台/不可挖区域/契约夹具路径）—— 现在收进
>    `state/world_profile.json`，换包只改这一个文件。
>
> ⚠ **未验证**：本轮**没有第二个整合包/第二台实例**可跑 ⇒ 下面流程里"真实第二个包"整条链
> 属于**未验证（TODO）**；文末列明。别把这份指南当成"已支持多整合包"的证明。

---

## 0. 前提（与 INSTALL.md 一致）

| 组件 | 要求 |
|---|---|
| 操作系统 | Windows 10/11（开发实测）；Linux/macOS 未验证 |
| Minecraft | **1.20.1** |
| Forge | **47.x**（开发用 47.2.20） |
| 假人 | **Carpet**或兼容 forge-carpet（要能 `/player Bot spawn`） |
| 模组 | `dshbridge-<version>.jar`（发布附件；或按 INSTALL §5 路径 B 自己构建） |
| Python | **3.10+，纯标准库**（开发机 3.14.2；不需要 pip install） |
| 磁盘 | 仓库本身很小；游戏/整合包另计 |

先按 `INSTALL.md` §2~§6 把"一个包能跑起来"跑通（`direct.py --health` 返回 `ok dshbridge-http`，
`doctor.py` 不红）。**换包 = 在已跑通的基础上只换下面 4 组东西。**

---

## 1. 换环境事实：`dsh.env`（本机，不进版本库）

```powershell
Copy-Item dsh.env.example dsh.env
notepad dsh.env
```

至少改（完整键见 `dsh.env.example` 注释）：

| 键 | 新包要填什么 |
|---|---|
| `MC_HOME` | 新实例目录（PCL2 的 versions/<实例名>） |
| `INSTANCE_NAME` | 实例目录名（人读/doctor 核对） |
| `PACK_NAME` | 新整合包简称（人读） |
| `SAVE_NAME` | 新存档目录名（`MC_HOME/saves/` 下） |
| `BOT_NAME` | 假人名（默认 `Bot`） |
| `DSH_PORT` / `GATEWAY_PORT` | 端口（默认 8766 / 8765；冲突再改） |
| `MOD_VERSION_FILE` | 版本单一真源（默认 `mod/gradle.properties`） |

> `tools/paths.py` 是**唯一**允许写"本机默认值"的模块；其他 `tools/*.py` 写死本机路径会被
> `tools/portability_test.py` 判红（换台电脑必坏）。所以**永远改 dsh.env，不改代码**。

---

## 2. 换世界常量：`state/world_profile.json`（跨包档案，唯一入口）

```powershell
py tools/world_profile.py --init      # 生成示例（本机当前世界的值；已存在且不同会拒绝覆盖，--force 才覆盖）
py tools/world_profile.py --show      # 看/校验（缺档案 exit 2 = "还没配"，不是坏）
```

然后按新世界改这些字段：

| 字段 | 含义 | 谁用 |
|---|---|---|
| `pack_name` | 新整合包名（人读） | 诊断/审计 |
| `anchor` `[x,y,z]` | 重生/回锚点（安全落脚） | `tools/recover.py`（D4 恢复） |
| `soak_anchor` `[x,y,z]` | 浸泡/长跑锚点（起点必须在半径 16 内） | `tools/soak_suite.py` 默认 `--anchor` |
| `test_platform` | `{center,radius,box}` 测试平台（虚空平台等） | 平台档 `--allow-void-platform` 的安全盒/回锚点 |
| `no_dig_zones` | `[{name,box,why}]` 不可挖区域（家/屋/机器） | 施工许可（no_dig）；换包必须重划 |
| `contract_fixture` | 契约夹具目录（**相对**仓库根，默认 `state/contracts`） | 模组契约（`mod_contract.py`） |
| `notes` | 人读备注（换包要改哪些） | 人 |

规则：
- **档案里禁止本机绝对路径**（盘符/用户主目录）——`world_profile_test.py` W6 守；换台电脑必坏。
- **没有档案时**：`recover`/`soak_suite` 会**打印**"用默认锚点（本机世界）"再用旧默认；
  `doctor` 的 `world_profile` 项 = unknown（**不判死**）。★不会静默假装配好了✗★。
- 读取优先级：显式 CLI（`--anchor`）＞ 环境变量（`DSH_WORLD_ANCHOR` / `DSH_SOAK_ANCHOR`）＞ 档案。

---

## 3. 换离线数据（当前整合包的知识）：bootstrap 重新生成

>> 详细起因/口径见 `INSTALL.md` §8；这里给换包执行清单。

1. **游戏内导出**：在当前世界里让模组导出方块注册表/标签/碰撞数据（模组命令
   `/dshkb` / `/dshkbexport`，以 `mod/README.md` 为准）。产物在**实例目录**的
   `logs\blockkb.json`（不是仓库里）。
2. **验收导出文件**：`py tools/kb_export.py`（V1~V6 校验 schema/count/族名闭集/max_height…）。
3. **生成四件套**：`py tools/bootstrap.py export`
   - `build/recipes.json`（配方图）
   - `state/tags_category.json` + `state/tags_family.json`（标签/分类）
   - `docs/分歧清单.md`、`docs/迁移准备度.md`（生成物，别手改）
   - 收尾自检：四份产物在不在
4. **重新跑闸门**：`py tools/check_all.py --offline`（期望 `SUMMARY ... fail=0`；干净包没有
   本机残留 ⇒ 这是换包后最硬的验收）。
5. 若数据条数/内容变化大：同步更新 `state/exceptions.json`（例外表是**人判**，不能自动生成）。

> 注意：`build/recipes.json` 在开发机约 12MB；新包的条数会不同（别写死 20764 之类数字）。
> 发布用的干净快照由 `py tools/export_public.py` 生成，**不含**本机日志/工具链/第三方 jar。

---

## 4. 重抓世界验收件（契约夹具 / 测试件 / 禁区）

| 件 | 命令 / 位置 | 说明 |
|---|---|---|
| 契约夹具 | `py tools/mod_contract.py --id calib_v1 --capture`（会覆盖旧件） | 存 `state/contracts/<id>.json`；换世界后必须重抓 |
| 测试件清单 | `state/test_fixtures.json`（`fixtures.py add/list`） | 记录测试用方块/箱子的 box 与用途 |
| 不可挖区域 | `py tools/no_dig.py`（list / add；state/no_dig.json） | 换包后**先重划**家/机器/箱子，再跑任何动手判据 |
| 测试平台/建造件 | `state/platform_build.json`、`state/blueprint_build.json` | 旧世界建造记录；新世界按需重建 |

> 本轮的 `world_profile.no_dig_zones` 是"人类可读的禁区声明"；`no_dig.json` 仍是运行时真值源。
> 两者一致由人在换包时保证（**已知缺口**：`no_dig.py` 的默认区仍是本机 ATM9 坐标，见 §6）。

---

## 5. 换包后的验收（按顺序，全离线）

```powershell
py tools/world_profile.py --show          # 期望 WORLDPROFILE ok=1；看 anchor/soak/zones 对不对
py tools/doctor.py --no-net               # exit 0 全好；exit 2 = 部分未知（无游戏/没配 token，不是坏）
py tools/check_all.py --offline           # 期望 SUMMARY ... fail=0
py tools/portability_test.py              # 期望 PORTABILITY ok=1（代码里没有本机绑定）
py tools/world_profile_test.py            # 期望 WORLDPROFILE ok=1 checks=6（W1~W6）
py tools/cold_start_test.py --dir tmp/cleanroom   # 发布前：干净副本还缺什么
```

进游戏后：
```powershell
py tools/direct.py --health               # ok dshbridge-http
py tools/recover.py --dry-run             # 期望 RESPAWN/回锚点可行（不发真指令）
py tools/soak_suite.py --profile mixed --minutes 2 --radius 3   # 小烟测；看 scorecard hard=0
```
**判定规则**：`doctor` 的 unknown、`cold_start/soak` 的 INCONCLUSIVE **都不算通过**（"测不了≠好"）；
换包完成的最低证据是 `check_all --offline` 全绿 + 小烟测 `hard=0` + `oracle gaps=0`。

---

## 6. 已知缺口（本轮审计，换包前必须知道）

1. **只有 3 处已接线 world_profile**：`recover`（anchor）、`soak_suite`（soak_anchor）、
   `doctor`（检查项）。其余世界常量仍是本机 ATM9 硬编码 —— 换包后要么别用那些工具，要么先改：
   - `tools/no_dig.py:35 DEFAULT_ZONES`（家/屋/CC 机坐标）
   - `tools/sandbox.py:37 SANDBOX_BOUNDS`、`tools/mcp_policy.py:18` 默认 bounds
   - `tools/human_action_test.py:143` 探针候选坐标
   - `tools/free_inv.py:22` / `tools/free_slots.py:31` / `tools/inv_guard.py:52` 容器坐标
   - `tools/e1_window.py:26 E1_SPOT`；`tools/ring_path.py:43/50/51` 环半径默认
   - `tools/soak_night.ps1` 的 `-Anchor` 默认（脚本层没法 import Python 档案；需显式传参）
   - 诊断/遗留工具（`_diag_walk.py`、`bench_v27.py`、`cut34_seam_check.py`、`tools/legacy/*`）里的
     坐标只用于本机排障，换包后不保证可用。
   完整清单（文件:行:常量:建议）见 `tmp/ledger/soak-541.md` 审计表。
2. **离线数据是"当前包生成的"**：换包后不重新 bootstrap，配方/标签/例外就是错的（工具会读出
   旧包知识，可能静默用错 ⇒ 所以 §3 是必须项，不是可选）。
3. **契约夹具/测试件是旧世界快照**：换世界后旧 `state/contracts/*`、`state/fixtures/*` 只对旧世界
   成立；不重抓就跑契约判据 = 测旧世界（结果无意义）。
4. **真实第二个整合包未验证**：没有第二实例/第二台机 ⇒ 本指南的步骤是"按代码/数据依赖推导"，
   未经端到端实测。首次真换包时请把每一步结果补进 `tmp/ledger/` 并更新本节。
5. 平台档的 `VOID_PLATFORM_BOX`（`soak_suite.py:84`）仍是本机平台坐标；新包没有那座平台时
   **不要加 `--allow-void-platform`**（否则安全盒/回锚点对不上）。

---

## 7. 回滚

- 换包只动 `dsh.env`（本机文件，随时改回）和 `state/world_profile.json`（示例文件，可删）。
- 离线数据（`build/recipes.json`、`state/tags_*`、`state/export_snapshots/`）建议换包前先备份，
  失败就拷回；契约夹具同理。
- 代码不需要回滚（不绑定整合包）。

---

## 8. 实测状态（2026-11-03 发布准备轮）

| 项 | 状态 |
|---|---|
| `world_profile.py --init/--show` | ✅ 本机实测（生成/校验/幂等） |
| `world_profile_test.py` W1~W6 | ✅ 离线 6/6 绿（无档案不兜底/接线/坏档案红/init 幂等/优先级/无绝对路径） |
| `recover`/`soak_suite`/`doctor` 读档案 | ✅ 纯函数注入实测（W2；未进游戏实测） |
| `bootstrap.py export` 真跑 | ❌ **未实测**（需游戏侧导出配合；本轮只 `--dry` 验证过计划） |
| `mod_contract capture` / `no_dig` 重划 | ❌ 本机本轮未跑（需游戏） |
| **真实第二个整合包端到端** | ❌ **未验证（本轮做不到）** |

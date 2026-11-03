# MC Agent Bridge

**让外部 Agent（LLM / 任意模型 / 你自己的程序）在 Minecraft 里像一个玩家一样在场** ——
服务端 Carpet 假人身体 ＋ Forge 模组能力面 ＋ 纯 Python 工具层，全部通过本机直连 HTTP 驱动。

> An experimental bridge that lets an external agent inhabit a Minecraft server as a
> **Carpet fake player**. A small Forge mod exposes world actions over a localhost HTTP
> endpoint; a dependency-free Python layer turns them into verifiable tools. The "brain"
> (LLM, harness, or your own program) is replaceable — the game side stays unchanged.

> **状态：实验性 / 研究项目，不是成熟产品。** 目前以 **Windows + Minecraft 1.20.1 Forge** 为主，
> 在 ATM9（All the Mods 9 - To the Sky）整合包上开发与验证。请先看下面的「现状与限制」。

---

## 它解决什么问题

把"Agent 进游戏"做成三层，各层只做自己的事：

```
          可换的「脑」                       项目的「身体」
  ┌──────────────────────┐        ┌──────────────────────────────────────┐
  │ LLM / harness / 你的程序 │        │  Python 工具层（tools/，55 个 MCP 工具）│
  │  （纯外部，可插拔）       │◄──────►│  感知 / 移动 / 容器 / 合成 / 对话 / 记账  │
  └──────────────────────┘        └───────────────┬──────────────────────┘
                                                  │ POST http://127.0.0.1:8766/cmd
                                                  │ （本机直连，毫秒级）
                                  ┌───────────────▼──────────────────────┐
                                  │ Forge 模组 dshbridge（服务端权威）      │
                                  │ /cmd /raw /health；读方块/背包 NBT，   │
                                  │ 驱动假人走挖放用、开容器、事件流         │
                                  └───────────────┬──────────────────────┘
                                                  │
                                  ┌───────────────▼──────────────────────┐
                                  │ Minecraft 世界 + Carpet 假人（Bot）     │
                                  │ 服务器线程执行，世界是唯一真值           │
                                  └──────────────────────────────────────┘

  后备链路（模组 HTTP 未起时）：Python → 本地网关 :8765 → CC:Tweaked 计算机 → 模组
```

**为什么不是"让 LLM 直接连游戏"**：游戏侧只暴露**原语**，判断与规划放在 Python/脑侧；
所有指令与回执都走同一条本机 HTTP，可日志、可回放、可审计；换脑只改配置，不改游戏侧代码。

## 核心特点

- **服务端假人，不是客户端外挂**：Carpet 假人在服务器线程执行动作，读的是方块与背包 **NBT 真值**，
  不受渲染/客户端差异影响。
- **本机直连，低延迟**：模组自己开 `127.0.0.1:8766`；旧网关＋CC 计算机链路只作后备。
- **判据驱动（可验证）**：项目自带数百条**离线判据**（不需要游戏即可跑），覆盖工具契约、环境解绑、
  文档一致性、发版链、恢复链等；行为改动要求"先能红的判据"。
- **安全护栏**：禁区黑名单、批量改方块前强制扫描、写通道 token、拒绝浏览器 Origin、`/raw` 白名单。
- **脑可插拔**：MCP 工具面（固定 55 件）＋ ACP/harness 两种接入方式；换模型/换 Agent 不动游戏侧。
- **纯标准库 Python**：`tools/` 无第三方依赖（3.10+；开发机实测 3.14）。
- **离线优先**：构建、判据、文档闸门都可在断网/无游戏时跑。

## 现状与限制（请先读）

- **实验性**：接口与内部结构仍可能变动；没有发布保证，也没有 CI 与正式版本号策略（模组有版本号）。
- **长期稳定性未收口**：连续 3 小时 × 3 夜的"身体不出事"长测还没有跑满；已跑过若干短档与混合档。
- **移动能力不如 Baritone**：寻路是"够用"级别（拆跳 + 每跳验真 + 防坠），复杂地形与长途移动不保证。
- **ATM9 特化**：方块分类/配方等数据是为当前整合包生成的知识资产；换整合包需要重新生成
  （`py tools/bootstrap.py export`，通常需要游戏侧导出配合）。
- **Windows 优先**：构建/服务脚本是 PowerShell；Python 部分理论上跨平台，但 Linux/macOS 未验证。
- **单假人、单世界**：为"一个在场身体"设计，不是多 Bot 集群。
- **需要真实游戏进程**：检查是否能跑、恢复假人、live 判据，都需要开着的 Minecraft 世界。

## 快速开始（5 步，约 15–30 分钟）

> 完整细节、每一步的实测状态、常见问题见 **[INSTALL.md](INSTALL.md)**。

1. **前置**：Windows 10/11、Minecraft **1.20.1 + Forge 47.x**、**Carpet**（或 forge-carpet 包）、
   Python **3.10+**；要改模组时另需 **JDK 17 + Gradle 8.1.1**（或让 `tools/bootstrap_toolchain.ps1` 下载）。
2. **取代码**：`git clone <本仓库地址>`（仓库不含游戏、整合包、第三方 mod jar、构建工具链）。
3. **配置环境**：把 `dsh.env.example` 复制成 `dsh.env`，填你的**实例路径 / 存档名 / 假人名 / 端口**；
   `dsh.env` 只在本机，不入库。检查：`py tools\paths.py`。
4. **启动游戏世界**：Forge 客户端（或服务端）进入世界，确认 Carpet 假人可用；
   构建并安装模组：`tools\build_jar.ps1` → `py tools\install_mod.py` → **重启游戏进程**（或用发布附件的 jar）。
5. **验证**：`py tools\direct.py --health`（应回 `ok dshbridge-http`）→ `py tools\doctor.py` →
   `py tools\recover.py`（世界重启后一条命令恢复假人）→ `py tools\check_all.py --offline`（离线判据全绿）。

跑通后，用一条只读指令看现场：

```powershell
py tools\act.py cmd text="execute as Bot at Bot run dshdigest"
py tools\block_at.py --nbt <x> <y> <z>   # 方块权威状态 + 方块实体 NBT
```

## 目录结构（简）

```
mc-agent-bridge/
├── README.md / INSTALL.md / CONTRIBUTING.md / LICENSE   ← 新读者从这里开始
├── mod/         Forge 模组源码（dshbridge）：/dsh* 指令、读世界、驱动假人（构建细节见 [mod/README.md](mod/README.md)）
├── tools/       Python 层：MCP 工具面（55 件）、判据、部署/恢复/发版脚本（纯标准库）
├── agent/       Python 侧活依赖：旧通道/世界/作业模块（被若干工具引用，不是遗留）
├── gateway/     本地指令队列网关 :8765（仅后备链路用）
├── bridge/      网关运行轨迹（运行时痕迹，不入库）
├── cc-tweaked/  游戏内 CC:Tweaked 程序（仅后备链路用）
├── kubejs/      KubeJS 服务端脚本（补模组未覆盖的少量行为）
├── docs/        文档：项目总览 / 接口契约 / 交接 / 错题本 / 索引（入口见下）
├── state/       离线知识资产与运行时状态（分类标签、例外表、导出快照等）
├── build/       离线数据（配方图等）
├── logs/        运行日志（不入库）
├── jobs/        任务账本（运行时数据）
├── memory/      长期记忆落盘（运行时数据）
├── personas/    人设/语料
├── skins/       皮肤 PNG
├── backups/     手动备份（不入库）
├── downloads/   本地下载缓存（不入库）
├── secrets/     本机密钥（不入库；公开仓库不应包含）
└── tmp/         一次性脚本/草稿（不入库）
```

## 判据与验证概览

项目把"能不能被信任"做成可执行的判据，而不是文档承诺：

| 命令 | 量什么 | 需要游戏？ |
|---|---|---|
| `py tools\check_all.py --offline` | 离线闸门：全部静态判据一次跑完（维护者要求连跑两遍同数） | 否 |
| `py tools\contract_test.py` | MCP 工具面与接入契约的双向守恒 | 否 |
| `py tools\portability_test.py` | 换机器可跑：`tools/*.py` 里不许再写死本机路径/实例名/端口 | 否 |
| `py tools\doc_consistency_test.py` | 入口文档里的版本/数字/链接与机器实况一致 | 否 |
| `py tools\doctor.py` | 一条命令回答"为什么跑不起来"（配置/实例/数据/版本/token/健康/进程/判据） | 否（健康检查会 unknown） |
| `py tools\recover.py` | 重启后一条命令恢复假人（幂等） | 是 |
| `py tools\check_all.py` | 全量电池（含需要世界的项） | 是 |

当前的具体数字（判据条数、长测进度等）由机器实算并写进 **`docs/项目总览.md`**，
本 README 不写死，避免过期。

## 文档地图

- **新读者**：本 README → [INSTALL.md](INSTALL.md) → [docs/项目总览.md](docs/项目总览.md)
- **想接自己的 Agent**：[docs/接口契约-伙伴v1.0.md](docs/接口契约-伙伴v1.0.md)
  （55 件 MCP 工具表、失败语义、三条硬边界、D1~D7 验收判据）
- **想一起改**：[CONTRIBUTING.md](CONTRIBUTING.md)
- **想发布/分发**：[docs/开源发布-清单.md](docs/开源发布-清单.md)（上传前检查清单）
  ＋ [GITHUB-UPLOAD.md](GITHUB-UPLOAD.md)（如何把这个项目传到 GitHub，含干净快照/Release/更新流程）
- **接手维护**：[docs/交接提示词.md](docs/交接提示词.md)（新会话直接粘贴的交接段）
- **全部文档**：[docs/文档索引.md](docs/文档索引.md)

## 许可证与致谢

- 本仓库默认 **MIT** 许可，见 [LICENSE](LICENSE)。仓库**不包含** Minecraft、Forge、Carpet、
  CC:Tweaked、ATM9 整合包或其它第三方 mod 的二进制；使用前请自行安装并遵守其许可证。
- 致谢：[Carpet](https://github.com/gnembon/fabric-carpet)（假人概念与服务端权威行为）、
  [Forge](https://forums.minecraftforge.net/)（模组框架）、
  [CC:Tweaked](https://tweaked.cc/)（后备链路与早期探索）、
  All the Mods 9 整合包（开发/验证环境）以及所有开源判据工具的启发。
- 项目内的审计/优化报告属于开发过程资料，不随公开仓库分发。

# INSTALL — 从零到跑起来

本文件面向**第一次接触本项目的人**：目标是在一台自己的 Windows 机器上，让外部 Agent 能驱动
Minecraft 里的一个 Carpet 假人。全程约 **15–30 分钟**（不含下载游戏/整合包的时间）。

> 实测状态标记（重要）：本项目目前的"已实测"是在**开发机**（Windows 11）上验证过的路径；
> 换机器/换整合包后，标「未实测」的步骤请按实际情况排查，用 `py tools\doctor.py` 定位。
> 本文件末尾有一张「各步骤实测状态」总表。

---

## 0. 三条最快路径，先选一条

| 路径 | 适合谁 | 额外时间 |
|---|---|---|
| **A. 用别人构建好的模组 jar**（推荐先跑通） | 只想把 Agent 接进游戏 | 最少 |
| **B. 从源码构建模组** | 要改模组/跟进最新代码 | +10–20 分钟（首次需下载 Gradle 依赖） |
| **C. 用不同整合包/自建世界** | 想换环境 | 还要重新生成离线数据（见 §8） |

无论哪条路径，**Python 侧和游戏侧是本仓库自带的；Minecraft/Forge/Carpet/整合包要你自己装**。

---

## 1. 前置要求

| 组件 | 要求 | 说明 / 本机实测 |
|---|---|---|
| Windows | **10 / 11** | 开发机 Windows 11 ✓（Linux/macOS 未验证，见 §10） |
| Minecraft | **1.20.1** | 开发环境（可选 ATM9 - To the Sky 空岛整合包）✓ |
| Forge | **47.x**（本项目在 47.2.20 上开发） | 用 Forge Installer 安装到对应版本实例 ✓ |
| Carpet 假人 | **Carpet**（或兼容的 forge-carpet 1.20.1 包） | 需要能 `/player Bot spawn` ✓（开发机用 `forge-carpet`） |
| Python | **3.10+，纯标准库** | 开发机 3.14.2 ✓；不需要 pip 装任何包 ✓ |
| 服务端/客户端 | 单机客户端开世界（局域网）或 Forge 服务端均可 | 开发机是客户端单机开世界 ✓ |
| 构建（可选） | **JDK 17** ＋ **Gradle 8.1.1** | 仅路径 B 需要；本机系统 PATH 无 java，构建使用仓库内/指定 JDK ✓（构建过程由模组维护者验证） |
| 磁盘/内存 | 建议 ≥8 GB 空闲（游戏+整合包另计） | 仓库本身很小（工具链/日志/第三方 jar 都已移出库） |
| 网络 | 路径 A 只需下载本仓库与游戏组件；路径 B 首次构建需要能访问 Maven 仓库 | 开发机为"离线/内网镜像构建"，见 §5 的镜像说明 |

> 端口占用：模组默认用 **127.0.0.1:8766**（直连 HTTP），旧网关用 8765，皮肤服务 8791，
> 可选 Maven 镜像 8789。端口冲突时见 §9。

---

## 2. 获取代码

```powershell
git clone <本仓库地址> mc-agent-bridge
cd mc-agent-bridge
```

- 仓库**不含**：游戏、整合包、第三方 mod jar、JDK/Gradle 工具链、日志和本地配置。
- 如果用的是打包快照（zip）：解压到任意目录即可，不要放在游戏实例目录里面。

---

## 3. 配置你的环境（`dsh.env`）

所有"本机环境事实"（实例路径、存档名、假人名、端口）都集中在**一个文件**里：

```powershell
Copy-Item dsh.env.example dsh.env
notepad dsh.env
```

至少要改：

`dsh.env.example` 里每一项都有注释与占位符，必填的是 `MC_HOME` / `INSTANCE_NAME` / `SAVE_NAME`，
其余一般保持默认即可。**机器相关项没有内置默认值：没配置会明确报错/告警，不会偷偷用别人的本机路径。**

```ini
MC_HOME=<你的 PCL2 实例目录，例如 C:\<启动器目录>\.minecraft\versions\<实例名>>
INSTANCE_NAME=<实例目录名>
PACK_NAME=<整合包简称>
SAVE_NAME=<世界存档目录名，在 MC_HOME\saves\ 下>
BOT_NAME=Bot
DSH_PORT=8766
GATEWAY_PORT=8765
# 可选：HTTP_TOKEN_FILE / DSH_EXE / DSH_BIN_JS / DSH_NODE（见 dsh.env.example 注释）
```

**实测状态**：`dsh.env.example` 已随本轮发布准备提供，`py tools\paths.py` 能识别模板/配置文件 ✓
（"复制并填写你自己的值"这一步是用户操作，本轮未在干净机器上实测）。配置好后用下面命令核对"每个值从哪来"：

```powershell
py tools\paths.py
```

它会打印 `dsh.env在不在`、每个键的值与来源（`env:` / `dsh.env:` / `default`）。

> 环境变量优先于 `dsh.env`；换机器/换整合包只改这个文件或设同名环境变量，不要改代码。
> **不要把 `dsh.env` 提交到仓库**（`.gitignore` 已忽略）。

---

## 4. 启动游戏世界

1. 用 Forge 1.20.1 启动器/服务端进入（或创建）你的世界。
2. 确认 Carpet 假人可用：在游戏聊天里执行

   ```
   /player Bot spawn
   ```

   能出现名为 `Bot` 的假人（或你在 `dsh.env` 里配置的名字）即可。
3. 保持世界运行——模组的 HTTP 服务随游戏进程启动。

> 模组安装好之前，`/player` 由 Carpet 提供；模组装好并重启后，Agent 才能驱动它。
> 单机客户端"对局域网开放"与 Forge 服务端都可以；本项目开发机是客户端单机开世界。

**实测状态：已实测（开发机）**。

---

## 5. 安装模组（`dshbridge`）

### 路径 A：用发布附件里的 jar（推荐先跑通）

1. 从 GitHub Releases 下载 `dshbridge-<version>.jar`（发布附件，不放在仓库里）。
2. 把它放进实例的 `mods\`（或让工具代装：把 jar 放到 `mod\build\libs\` 后跑 `py tools\install_mod.py`）。
3. **完全退出并重启游戏进程**（退到主菜单不算，模组只在进程启动时加载）。
4. 进世界后验证：`py tools\direct.py --health` 应返回 `ok dshbridge-http`。

**实测状态：部分实测（`install_mod.py` 在开发机上多次使用 ✓；"下载发布 jar"这一步本轮未实测）**。

### 路径 B：从源码构建

需要 **JDK 17 + Gradle 8.1.1**，任选一种来源：

- 用你自己的：设置 `DSH_JDK_HOME` / `DSH_GRADLE_HOME`（或 PATH 里有 `java`/`gradle`）；
- 或让脚本下载：`powershell -ExecutionPolicy Bypass -File tools\bootstrap_toolchain.ps1`
  （**未实测**：本机网络受限，脚本由模组维护者提供，会下载到 `mod\jdk`、`mod\gdist`）；
- 开发机惯例：工具链在 `mod\jdk\`、`mod\gdist\`（**不入库**）。

构建 → 安装：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_jar.ps1
py tools\install_mod.py        # 先验 jar 里真有新特征，再装进 mods/，旧 jar 自动备份
# 然后完全退出并重启游戏进程
```

- **离线/内网构建**：`build_jar.ps1` 会提示需要 Maven 镜像（`:8789`）；如果本机连不上公网，
  启动 `py tools\maven_mirror.py`（本机镜像）或设置 `DSH_MAVEN_MIRROR`。公开环境一般不需要镜像。
- **实测状态**：`build_jar.ps1` 在本机开发环境**历史已实测**（本轮构建由模组维护者复验）；
  `install_mod.py` 已实测 ✓；`bootstrap_toolchain.ps1` **未实测**。
- 构建细节/配置项（bot 名、端口、token 文件）见 `mod/README.md`。

结果：`mods\` 里出现 `dshbridge-<version>.jar`，`py tools\doctor.py` 的 `version` 一项会显示
"gradle 版本 = 已装 jar 版本"。

---

## 6. 启动后验证（按顺序）

先启动游戏并进入世界，再开一个 PowerShell 在仓库根目录执行：

| # | 命令 | 期望 | 实测状态 |
|---|---|---|---|
| 1 | `py tools\paths.py` | 打印你配置的实例/存档/假人/端口 | 已实测（开发机） |
| 2 | `py tools\direct.py --health` | `ok dshbridge-http`（连不上见 §9） | 已实测（游戏开启时；游戏未开时失败是正常的） |
| 3 | `py tools\doctor.py` | 10 项检查里"硬问题 0"；游戏没开时退出码 **2（部分未知）是正常的** | 本轮已实测（游戏未开 ⇒ 2） |
| 4 | `py tools\recover.py` | 世界重启后一条命令拉起假人并切生存；已就绪时幂等 | 已实测（2026-11-02 live） |
| 5 | `py tools\act.py cmd text="execute as Bot at Bot run dshver"` | 回执含 `version=<模组版本>` | 已实测（开发机） |
| 6 | `py tools\act.py cmd text="execute as Bot at Bot run dshdigest"` | 回执含 `name=Bot pos=... mode=survival` | 已实测（开发机） |
| 7 | `py tools\check_all.py --offline` | 离线判据全部通过（fail=0；允许带理由的 inconclusive） | 已实测（维护者例行运行；见 §11） |
| 8 | `py tools\contract_test.py` | MCP 接口契约 C1~C5 全绿 | 已实测 |
| 9 | `py tools\portability_test.py` | 无本机环境绑定违规 | 已实测 |
| 10 | `py tools\doc_consistency_test.py` | 入口文档自洽（全部绿） | 已实测 |

> 第 5/6 条里的 `execute as Bot at Bot run ...` 前缀不能省：模组用玩家上下文执行指令。

---

## 7.（可选）常驻服务与「脑」接入

直连模式下**不需要**网关/CC 计算机；但"能听会说/常驻会话"等功能需要额外常驻进程：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\start_all.ps1        # 幂等，可重复跑
powershell -NoProfile -ExecutionPolicy Bypass -File tools\start_all.ps1 -ReloadMcp  # 改过 mc_mcp.py 之后
```

它尝试启动：网关 `:8765`、皮肤服务 `:8791`、Maven 镜像 `:8789`、常驻会话、聊天中继（需要本机
已安装 `dsh` 可执行文件）。**实测状态：本轮未实测**（会启动常驻进程；开发机历史上用过）。

接自己的 Agent/模型：见 **`docs/接口契约-伙伴v1.0.md`**（55 件 MCP 工具、传输格式、失败语义、D1~D7）。

---

## 8. 换整合包 / 换世界（重新生成离线数据）

仓库自带一份与开发整合包匹配的离线知识数据（方块分类、例外表、配方图、导出快照）。
换整合包后需要重新生成：

1. 在游戏内导出方块注册表/标签数据（模组命令 `/dshkb` 或对应导出流程，详见 `docs/方案-注册表只读导出.md`）；
2. `py tools\bootstrap.py export`（按 `dsh.env` 生成 `build/recipes.json`、`state/tags_category.json`、
   `docs/分歧清单.md`、`docs/迁移准备度.md`）；
3. 重新跑 `py tools\check_all.py --offline`，按输出修数据/判据。

**实测状态**：`py tools\bootstrap.py export --dry` 已实测（只打印计划）；真正 `export` 本轮未实测
（需要游戏侧导出配合）。

---

## 9. 常见问题（FAQ）

**Q1. `direct.py --health` 连不上 / 超时**
- 游戏进程没开、世界没进？先确认游戏在跑且已进世界。
- 模组没加载：`mods\` 里有没有 `dshbridge-*.jar`？改过 jar 后是否**完全重启**了进程？
- 版本不匹配：`doctor.py` 的 version 一项会对比 `gradle.properties` 与已装 jar。
- 端口被占/改了：`dsh.env` 的 `DSH_PORT` 与模组启动参数要一致（默认 8766）。
- 防火墙/杀毒：只监听 `127.0.0.1`，正常不需要放行公网；如果本机安全软件拦截本地回环 HTTP，请放行
  Python/java 进程。
- 用 `py tools\doctor.py` 一次看全：config / home / mods / save / data / version / token / health / process / judges。

**Q2. `doctor.py` 退出码是 2，是不是坏了？**
不是。2 = **部分未知**（典型：游戏没开 ⇒ health/process 两项 unknown）。"不知道"不是"通过"，
但也不是失败；进游戏后再跑一次。

**Q3. 写指令返回 token 相关错误**
2.56 起模组的**写通道**需要请求头 token（`/health` 除外）。token 文件由模组在实例的
`config\dshbridge\http_token.txt` 生成；`tools/direct.py` 会自动找它。若你手动 curl，请带上
`X-DSH-Token: <文件内容>`。找不到文件通常因为模组版本旧或游戏未重启。

**Q4. 假人不在 / 重启后不见了**
世界重启后假人必然掉线，这是 Carpet 行为。跑 `py tools\recover.py`（幂等）即可：它会
health → 不在就 `/raw` 拉起 → 切生存 → 回读确认。**注意**：spawn 出来默认可能是创造模式，
不切生存会让"挖掘掉落"的验证全部失真。

**Q5. 构建失败：找不到 JDK / Gradle / Could not initialize native services**
- 用 `bootstrap_toolchain.ps1` 或设置 `DSH_JDK_HOME`/`DSH_GRADLE_HOME`；
- 需要 JDK **17**（不是 8/11/21）与 Gradle **8.1.1**；
- `Could not initialize native services` 常见于把 Gradle 用户目录放到不可写位置：保证 `GRADLE_USER_HOME`
  指向一个**真实可写目录**（构建脚本默认用工作区内的一个目录）；
- 首次构建要下载依赖，需能访问 Maven 仓库（离线环境见 §5 的镜像说明）。

**Q6. 端口冲突（8766/8765/8791/8789）**
改 `dsh.env` 的 `DSH_PORT`/`GATEWAY_PORT`，并让模组按同一端口启动（模组支持
`-Ddshbridge.port=`）；皮肤/镜像端口在对应脚本里。先确认没有旧进程占着端口
（`Get-NetTCPConnection -LocalPort 8766 -State Listen`）。

**Q7. 中文乱码 / 脚本报 SyntaxError**
Windows PowerShell 5.1 会把无 BOM 的脚本当 ANSI；本项目脚本要么纯 ASCII，要么 UTF-8 BOM。
自己写 PowerShell 时同理；Python 输出请确保控制台是 UTF-8（或 `PYTHONIOENCODING=utf-8`）。

**Q8. 我想跑完整长测（D3 soak）**
`py tools\soak_suite.py --profile mixed --minutes 20`（先短跑）；完整口径与门槛见
`docs/项目总览.md` 与 `docs/接口契约-伙伴v1.0.md`。需要游戏保持运行且不要在真实资产区改世界。

---

## 10. Linux / macOS（未实测，TODO）

- **Python 部分**理论上跨平台（纯标准库），`py tools\xxx.py` 换成 `python3 tools/xxx.py`。
- **PowerShell 脚本**（`build_jar.ps1`、`start_all.ps1`、`install_mod` 相关）尚未移植；
  Linux/macOS 需要自行改写或使用 `pwsh`（未验证）。
- 游戏侧同理：Forge 1.20.1 服务端 + Carpet 在 Linux 上可运行，但本项目的脚本与路径默认按 Windows 写。
- 欢迎 PR（请在描述里标注"未实测/已实测"）。

---

## 11. 各步骤实测状态总表（发布准备轮，2026-11-03）

| 步骤 | 状态 | 证据/备注 |
|---|---|---|
| 仓库不含工具链/日志/下载物 | ✓ 已核实 | `git ls-files` 无 `mod/jdk17.zip`、`mod/gdist`、`logs`、`downloads` 等 |
| `dsh.env.example` 存在且被 `paths.py` 识别 | ✓ 已实测 | 模板含占位符与注释；开发机用本机 `dsh.env` |
| 干净机器上复制 example → 填写 → 跑通 | 未实测 | 需要另一台机器；用 `py tools\doctor.py` 定位 |
| `py tools\paths.py` | ✓ 已实测 | 打印配置值与来源 |
| `direct.py --health` | ✓（游戏开时）/ 本轮未复测（游戏未开） | 历史与 2026-11-02 live 实测 |
| `doctor.py` | ✓ 已实测 | 本轮游戏未开 ⇒ 退出码 2 部分未知，符合预期 |
| `recover.py` | ✓ 已实测（live） | 2026-11-02 重启窗口：spawn→切生存→确认，exit 0 |
| `check_all.py --offline` | ✓ 已实测 | 维护者例行运行；本轮见交付报告机器行 |
| `contract_test.py` / `portability_test.py` / `doc_consistency_test.py` | ✓ 已实测 | 见交付报告 |
| `build_jar.ps1`（源码构建） | 历史已实测 / 本轮由模组维护者复验 | 需要 JDK17+Gradle；本机系统 PATH 无 java |
| `bootstrap_toolchain.ps1` | 未实测 | 下载工具链脚本（本机网络受限未真跑） |
| `install_mod.py` | ✓ 已实测 | 装前先验 jar 内特征 |
| `start_all.ps1` 常驻服务 | 未实测（本轮） | 会起常驻进程，涉及 `dsh` 安装 |
| `bootstrap.py export`（重新生成数据） | `--dry` 已实测；真跑未实测 | 需要游戏侧导出配合 |
| 干净快照首跑（doc gate） | ✓ 已实测（2026-11-03） | 模拟 zip 快照与单提交 clone 两种，`doc_consistency_test` 均 37/37（无 mtime 假红） |
| 干净快照首跑（generated_freshness） | ✓ 已实测（2026-11-03） | 单提交 clone 下 PASS（git 提交时间优先，不再因解压顺序假红） |
| Linux/macOS 全流程 | 未实测 | 见 §10 |

---

## 12. 卸载 / 回滚

1. 退出游戏，删除实例 `mods\` 里的 `dshbridge-*.jar`（保留 `.bak-*` 备份即可回滚）。
2. 删除仓库根目录的 `dsh.env`（本机配置，不应提交）。
3. 不需要本项目时直接删除仓库目录；游戏/整合包不受影响（模组不改存档格式）。
4. 如果起过常驻服务，停掉对应进程（网关/皮肤/MCP）；`start_all.ps1` 起的进程名见脚本注释。

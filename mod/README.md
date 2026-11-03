# dshbridge —— 模组构建与运行说明（发布/换机版）

> **第一次上手请看仓库根的 [`INSTALL.md`](../INSTALL.md)**（从零到跑起来的完整流程）。
> 这份 README 只讲**模组本身**：怎么在另一台机器上构建、配置、安装。
（仓库根还有 `docs/`（项目总览/架构）、`tools/`（Python 能力层）、`dsh.env`（整套工具的环境事实）。）

---

## 1. 适用环境

| 项 | 值 | 说明 |
|---|---|---|
| Minecraft | **1.20.1** | `minecraft_version=1.20.1` |
| Forge | **47.2.20**（任意 47.x 可加载） | `forge_version=47.2.20` |
| Java | **17**（编译与运行） | `java.toolchain.languageVersion = 17` |
| 假人（可选） | **Carpet: NeoForged 1.0.8+v251027**（Forge 1.20.1） | 用 `/player <名字> spawn` 造 `ServerPlayer` 假人；没有 Carpet 时模组的容器/动作命令仍可用，只是没假人可驱动 |
| 服务端 | 任意 Forge 1.20.1 服务端 | 单机内置服务端同样可用（本项目就是在 ATM9 空岛单机内置服务端上跑的） |

> 模组自己不依赖 ATM9：ATM9 只是本项目的"真实世界"测试环境。

## 2. 构建前置（工具链不随 git 仓库分发）

仓库里**不入库**这 ~300 MB 工具链（`.gitignore` 已排除）：
`mod/jdk/`、`mod/jdk17.zip`、`mod/gdist/`、`mod/gradle-8.1.1-bin.zip`、`mod/build/` 等。

构建脚本按下面的顺序找工具链（`tools/build_jar.ps1`）：

| 工具 | 1) 环境变量 | 2) 本地目录兜底 | 3) 都没有 |
|---|---|---|---|
| JDK 17 | `DSH_JDK_HOME`（须有 `bin\javac.exe`） | `mod\jdk\jdk-17.0.20.1+1` | 明确报错 → 提示 `tools\bootstrap_toolchain.ps1` |
| Gradle 8.1.1 | `DSH_GRADLE_HOME`（须有 `bin\gradle.bat`） | `mod\gdist\gradle-8.1.1` | 同上 |
| Gradle 缓存 | `DSH_GRADLE_USER_HOME` | 仓库父目录 `.gradle-home/` | 自动创建 |

一键取工具链（**当前环境没跑过**：本机网络对上游按 UA 有限制，脚本已写但未实测下载）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\bootstrap_toolchain.ps1
# 校验和：上游有 .sha256 就自动校验；没有就要求 -ExpectedJdkSha256/-ExpectedGradleSha256，
#         或显式 -AllowUnverified（会大声 WARN，绝不静默跳过）
```

**Maven 镜像可选**（79.534 起不再硬绑 `127.0.0.1:8789`）：

- 设了 `DSH_MAVEN_MIRROR`（或 `-PdshMirror=<url>`）⇒ 先走镜像，后面再跟公开仓；
- 没设 ⇒ 只走公开仓：`maven.minecraftforge.net` / Maven Central / `bmclapi2.bangbang93.com/maven` / Gradle Plugin Portal；
- 本机之所以需要镜像：上游按 **User-Agent** 拒绝 Gradle（Java/17 的 UA 实测 200，工具型 UA 403）✗
  ⇒ 本机 `tools/build_jar.ps1` 会**自动探测** `:8789`，在监听就自动设置 `DSH_MAVEN_MIRROR=http://127.0.0.1:8789`；
- `mod/mirror.init.gradle` **只在用镜像时**才传给 Gradle（`--init-script`）。

## 3. 构建

```powershell
# 版本单一真源：mod/gradle.properties 的 mod_version
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_jar.ps1
# 首次/缓存丢失：加 -SeedCache（从 %USERPROFILE%\.gradle\caches 播种到 .gradle-home）
```

产物：`mod/build/libs/dshbridge-<version>.jar`；日志：`logs/build_jar.log`。
构建脚本**不会**改世界、不会启动游戏。

## 4. 模组运行配置（全部可选，默认值与历史行为逐字节一致）

配置有两种来源：**JVM 系统属性**（优先）> **环境变量** > 默认值。游戏启动参数里加 `-D…` 即可（PCL2：实例设置 → 游戏 → JVM 参数）。

| 系统属性 | 环境变量 | 默认 | 作用 |
|---|---|---|---|
| `-Ddshbridge.bot=<name>` | `BOT_NAME` | `Bot` | 假人名（/dshver 会自报 `bot=`） |
| `-Ddshbridge.port=<port>` | `DSH_PORT` | `8766` | 直连 HTTP 端口（只绑 `127.0.0.1`） |
| `-Ddshbridge.tokenFile=<path>` | `HTTP_TOKEN_FILE` | 相对 `config/dshbridge/http_token.txt` | 请求 token 文件（首启自动生成 32 hex） |
| `-Ddshbridge.http.pool=false` | — | `true` | 回滚开关：HTTP 回到旧的单 accept 线程（不再用 worker 池） |

> 注意：token 文件默认是**相对路径** ⇒ 相对于游戏进程的工作目录（PCL2 启动时=实例目录）。
> 用绝对路径最稳：`-Ddshbridge.tokenFile=D:/pcl2/.../config/dshbridge/http_token.txt`。

`/dshver` 可自检：真实加载版本 + `bot=`；`/dshhttp` 自报端口/token 文件/线程池状态。

## 5. 安装到游戏

1. 把 `mod/build/libs/dshbridge-<version>.jar` 复制到 `<实例>/mods/`；
2. **完整重启游戏进程**（模组只在进程启动时加载；只退世界不生效）；
3. 游戏内或直连验证：`/dshver`（应报新版本）、`/dshhttp`；
4. 本仓库工具：`py tools/install_mod.py`（会先验 jar 里真的含预期特征串，再备份旧 jar、复制新的）。

直连（Python 侧）：`py tools/direct.py --health` → `ok dshbridge-http`；`/cmd` 与 `/raw` 需要
`X-DSH-Token` 头，token 从 `config/dshbridge/http_token.txt` 读（`tools/direct.py` 自动找）。

## 6. 排障

| 现象 | 原因/处理 |
|---|---|
| `Could not initialize native services` | `GRADLE_USER_HOME` 跑到了工作区外（沙箱拒绝写）⇒ 本脚本默认 `<仓库父目录>\.gradle-home`；可用 `DSH_GRADLE_USER_HOME` 指定 |
| 依赖下载 403 / `Skipped due to earlier error` | 上游按 UA 拒 Gradle ⇒ 本机需启动 `py tools/maven_mirror.py 8789`，或用 `DSH_MAVEN_MIRROR` 指向可用镜像 |
| 找不到 JDK/Gradle | 见 §2：设 `DSH_JDK_HOME`/`DSH_GRADLE_HOME`，或跑 `tools/bootstrap_toolchain.ps1` |
| 建好的 jar 装上没生效 | 必须**重启游戏进程**；用 `/dshver` 确认真实版本 |
| 直连 401 | 请求没带 `X-DSH-Token` 或 token 文件不匹配 ⇒ 看 `/dshhttp` 的 `token_file=`/`token_len=` |

## 7. 不随 git 分发的内容

`mod/jdk*`、`mod/gdist/`、`mod/build/`、`.gradle-home/`（仓库父目录）、`downloads/`、`logs/`、`backups/`、
`state/` 中的运行痕迹。它们由 `tools/bootstrap_toolchain.ps1` + 首次构建 + 运行时自动生成。

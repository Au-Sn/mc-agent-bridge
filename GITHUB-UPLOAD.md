# 把这个项目上传到 GitHub —— 详细操作说明

> 适用状态：2026-11-03，发布准备轮已完成（干净快照已生成、门禁已绿）。
> 本文只讲"如何把**已经准备好的公开快照**推上 GitHub"，不涉及改代码。
> 配套文件：`INSTALL.md`（别人如何安装）、`docs/开源发布-清单.md`（上传前检查清单）、`tools/export_public.py`（生成快照）。

---

## 0. 先认清两样东西（很重要，别推错）

| 目录 | 是什么 | 要不要推 GitHub |
|---|---|---|
| **私有开发仓**（本仓库，HEAD 已到 2.58.0） | 含完整历史（441MB 旧 `.git`，里面有工具链旧 blob、曾经泄露过的旧 key、本机日志/私人运行数据） | **不要推**。留在这台机器上自己用 |
| **公开快照**（`..\mc-agent-bridge-public`，由 `tools/export_public.py` 生成） | 只含当前版本的源码/文档/离线数据，**无**工具链、无第三方 jar、无日志、无本机 `dsh.env`、无旧历史；单提交、干净 | **推这个** |

公开快照的现状（可以直接推）：
- 678 个文件 / 约 31 MB / 单提交（branch `main`）/ 工作区干净
- 首次运行应看到：`COLDSTART ok=1`（冷启动判据）、`doc_consistency 37/37 PASS`
- 不含任何密钥；不含第三方 mod 二进制（Carpet/AP/CC 等请用户按 `INSTALL.md` 去官方源下载）

> 为什么不用 `git push` 推原仓库？<br>
> 原仓库 `.git` 有 441MB 历史，其中初始提交里有 `secrets/deepseek.key` 的旧 blob；GitHub 单文件 100MB 硬限也会被旧工具链文件（178MB 的 jdk17.zip）直接拒收。<br>
> 如果一定要"保留历史"，见文末「附录 B：想保留历史怎么办」，但**不推荐**。

---

## 1. 你需要准备什么

1. **GitHub 账号**（建议开两步验证 2FA）。
2. **Git for Windows**（PowerShell 里 `git --version` 能出版本即可）。
3. **认证方式二选一**（推荐 A）：
   - **A. HTTPS + Personal Access Token（PAT）**：GitHub 网页右上角头像 → Settings → Developer settings →
     Personal access tokens → **Fine-grained tokens** → Generate new token：
     - Repository access：选 `Only select repositories` → 建仓后再选它（或先选 `All repositories` 临时用）
     - Permissions：`Contents` = Read and write；`Metadata` = Read（自动）；以后要传 Release 附件再加 `Releases` = Read and write
     - 生成后**只显示一次**，复制保存好
     - Windows 的 Git Credential Manager 第一次 push 时会弹窗要 token，粘贴即可（会记住）
   - **B. SSH key**：`ssh-keygen -t ed25519 -C "你的邮箱"` → 把 `~/.ssh/id_ed25519.pub` 内容贴到
     GitHub → Settings → SSH and GPG keys → New SSH key → 然后 remote 用 `git@github.com:用户名/仓库.git`。
     适合长期用；公司/校园网封 22 端口时改用 HTTPS。
4. （可选）**GitHub CLI `gh`**：装好后 `gh auth login` 一条命令完成认证和建仓，最省事。
5. **Git 身份**（只影响提交作者显示，不影响认证）：
   ```powershell
   git config --global user.name  "<你的 GitHub 用户名>"
   git config --global user.email "<你的 GitHub 邮箱>"
   ```
6. 顺手关掉 Windows 换行转换（避免文档被自动改 CRLF 产生噪音提交）：
   ```powershell
   git config --global core.autocrlf false
   git config --global core.quotepath false   # 让中文文件名在 git status 里正常显示
   ```

---

## 2. 在 GitHub 上创建仓库

### 方式 A：网页创建（推荐，最直观）

1. 打开 <https://github.com/new>。
2. **Repository name**：例如 `mc-agent-bridge`（只能用字母/数字/`-`/`_`/`.`）。
3. **Description**（可选）：
   `Minecraft AI 在场层：服务端假人（Carpet）+ Forge 模组 + Python 工具层，可换脑、可验证、带安全护栏。`
4. **Public / Private**：想开源就选 **Public**；只想先给自己看就选 Private（**不影响本机使用**，以后可随时改）。
5. **⚠ 不要勾选** "Add a README file"、"Add .gitignore"、"Choose a license" ——
   我们本地快照里已经有这些文件；勾了会让远端先有一个提交，push 时会冲突。
6. 点 **Create repository**。创建完的页面会显示：
   `https://github.com/<用户名>/<仓库名>.git`
   —— 复制这行，下一步用。

### 方式 B：GitHub CLI 创建（一条命令）

```powershell
# 先认证（浏览器登录一次即可）
gh auth login

# 进入公开快照目录后建仓并推送（--public 可换 --private）
cd "..\mc-agent-bridge-public"
gh repo create <用户名>/mc-agent-bridge --public --source . --remote origin --push
```

> 如果 `gh repo create --source .` 报 "repository already exists"，说明名字被占，换个名字即可。

---

## 3. 把公开快照推上去（核心步骤）

### 3.1 进入公开快照目录

```powershell
cd "..\mc-agent-bridge-public"
# 确认它是干净的、单提交、分支 main：
git status          # 应为 nothing to commit, working tree clean
git log --oneline   # 应只有 1 行：public snapshot of mc-agent-bridge (from private HEAD ...)
git branch --show-current   # 应为 main
```

### 3.2 设置远端

```powershell
git remote add origin https://github.com/<用户名>/<仓库名>.git
git remote -v      # 检查 origin 的 fetch/push 两行都对
```

如果之前加过错地址：`git remote set-url origin https://github.com/<用户名>/<仓库名>.git`。

### 3.3 推送

```powershell
git push -u origin main
```

预期输出：`branch 'main' -> 'main'`、`new branch`，最后提示 `Branch 'main' set up to track remote branch 'main' from 'origin'`。

- 第一次 push 会弹 **Git Credential Manager** 窗口：选 `Token`（或 `Personal access token`），贴第 1 步的 PAT。
- 如果弹的是浏览器登录（OAuth），也可以直接登录授权。
- 看到 `remote: Resolving deltas: 100% ... done` 就是成功了。

### 3.4 验证

```powershell
git ls-remote origin      # 应看到 main 的 commit id，与本地 git log -1 一致
git status                # 应显示 up to date
```

打开 `https://github.com/<用户名>/<仓库名>`：
- 首页应渲染出 `README.md`（架构图/快速开始）；
- 文件树应有 `INSTALL.md`、`LICENSE`、`CONTRIBUTING.md`、`dsh.env.example`、`docs/`、`tools/`、`mod/`；
- 右侧应显示 **MIT license**；
- 仓库大小在 **Settings → General → 底部** 或 `https://github.com/<用户名>/<仓库名>/settings` 查看，应该 ~31MB 左右。

---

## 4. 发布第一个版本（Release）＋ 上传 jar 附件

jar **不要放进 git 仓库**（每次构建都变，且二进制不该进版本库）；正确做法是放到 **Release 附件**里。

### 4.1 先准备 jar

在私有开发仓（本仓库）里构建并确认版本：

```powershell
cd "<私有开发仓目录>"          # 例如 ...\deepseek harness\mc-agent-bridge
py tools/doctor.py --no-net     # 确认版本/数据；或看 mod/gradle.properties
# 构建（需要 JDK17 + Gradle；没装见 INSTALL.md 或 tools/bootstrap_toolchain.ps1）
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_jar.ps1
# 产物：mod\build\libs\dshbridge-2.58.0.jar
Get-FileHash mod\build\libs\dshbridge-2.58.0.jar -Algorithm SHA256
```

> 本轮已构建好：`mod\build\libs\dshbridge-2.58.0.jar`（143,967 B，sha256 前 8 位 6171f023）。
> 发版清单已记录：`py tools/release.py --check` → `RELEASE: PASS`。

### 4.2 网页上传 Release（推荐）

1. 打开 `https://github.com/<用户名>/<仓库名>/releases/new`。
2. **Choose a tag**：输入 `v2.58.0` → 点 "Create new tag: v2.58.0 on publish"。
3. **Release title**：`v2.58.0 — 发布准备版（干净快照）`
4. **Describe this release**：可从 `docs/开源发布-清单.md` 或台账 §79.538 摘几行（建议写清楚：需要 MC 1.20.1 + Forge + Carpet；ATM9 兼容；limitations）。
5. **Attach binaries**：把 `mod\build\libs\dshbridge-2.58.0.jar` 拖进 "Attach binaries by dropping them here" 框。
6. 勾不勾 "Set as the latest release" 都可以（第一个版本建议勾）。
7. 点 **Publish release**。

### 4.3 或者用 `gh` 一条命令

```powershell
gh release create v2.58.0 `
  "mod\build\libs\dshbridge-2.58.0.jar" `
  --title "v2.58.0 — 发布准备版（干净快照）" `
  --notes "首个公开版本：ModConfig 配置化 / 构建去镜像化 / 跨机冷启动判据 / GitHub 文档。需要 MC 1.20.1 + Forge 47.x + Carpet 假人；详见 INSTALL.md。"
```

> GitHub 对**单个 Release 附件**上限是 2GB，jar 才 140KB，随便传。<br>
> Release 里建议附上 sha256（上面 `Get-FileHash` 的结果），方便别人校验。

---

## 5. 仓库设置建议（上传完花 2 分钟做）

在 `https://github.com/<用户名>/<仓库名>/settings`：

1. **General → Description / Website / Topics**：
   填一句话简介＋主题词（建议 `minecraft`、`forge`、`carpet`、`ai-agent`、`llm`、`mcp`、`automation`）。
   首页右上角会显示 topics，方便别人搜到。
2. **General → Default branch**：确认为 `main`（我们快照就是 main，一般不用改）。
3. **Settings → Actions → General**：本项目**没有** CI workflow，保持默认即可；如果不熟悉别开 "Allow all actions"，用 "Allow select actions" 更安全。
4. **Settings → Secrets and variables → Actions**：**不要**存任何游戏账号/API key（这个仓库用不到）。
5. **Settings → Code security and analysis**：开启 **Secret scanning** 和 **Push protection**（公开仓免费，防止以后误传 key）。
6. **Settings → Branches → Add branch protection rule**（可选）：只允许 PR 合并、禁止 force push——多人协作时再开。
7. 账号层面（Settings → Password and authentication）：**开 2FA**；PAT 设置过期时间（例如 90 天）。

---

## 6. 以后如何更新（私有仓 → 公开仓的日常流程）

公开快照是"每次从私有仓重新导出"的，所以更新流程是：

```powershell
# ① 在私有仓完成开发、跑门禁、提交（私有仓 HEAD 前进）
cd "<私有开发仓目录>"
py tools\check_all.py --offline       # 至少确认离线闸门不退化
py tools\export_public.py --check     # 检查"可公开性"：EXPORTPUBLIC ok=1

# ② 导出新快照到临时目录（不要覆盖公开仓，公开仓里有 .git/remote）
py tools\export_public.py --out tmp\public-update

# ③ 把新快照同步进公开仓目录（保留 .git！用 robocopy 镜像，排除 .git）
robocopy "tmp\public-update" "<公开仓目录>" /MIR /XD ".git" /NFL /NDL /NJH /NJS
#    <公开仓目录> 例如 "..\mc-agent-bridge-public"

# ④ 提交并推送
cd "<公开仓目录>"
git status            # 看这次同步了哪些文件
git add -A
git commit -m "sync public snapshot to <私有仓 HEAD 短哈希>"
git push
```

发新版本时再重复第 4 节（新 tag + 新 jar）。

> 小技巧：`robocopy /MIR /XD ".git"` 会删除公开仓里不再存在的文件，但**保留 `.git` 目录**（remote/历史都在），这是关键。

---

## 7. 常见问题（照着排查）

| 现象 | 原因 / 解决 |
|---|---|
| `remote: error: GH001: Large files detected` / `File ... is 178.00 MB; this exceeds GitHub's file size limit of 100.00 MB` | 你把私有仓或工具链推上去了。停！删远端仓库重建空仓，按本文用**公开快照**重推；本地私有仓不要动 |
| `! [rejected] main -> main (fetch first)` 或 `(non-fast-forward)` | 远端有初始提交（建仓时勾了 README/LICENSE）。要么 `git pull --rebase origin main` 再 push；要么删掉远端仓库重建**空仓**（推荐，避免两套 README 混在一起） |
| `fatal: remote origin already exists` | `git remote set-url origin <url>` |
| push 时一直提示输入密码 / 401 / 403 | 不要用 GitHub 账号密码（已不支持）；用 PAT（见第 1 步）。检查 PAT 的 Contents 权限和是否过期；组织仓库还要 SSO 授权 |
| `Permission denied (publickey)` | SSH key 没加到 GitHub 或没加载；改回 HTTPS，或 `ssh -T git@github.com` 排查 |
| 中文文件名显示成 `\346\226\207...` | 只是显示问题：`git config --global core.quotepath false` |
| `warning: LF will be replaced by CRLF` | `git config --global core.autocrlf false` |
| 推送很慢 / 卡在 `Writing objects` | 仓库约 31MB 属正常；网络问题可重试，或 `git config --global http.postBuffer 524288000` |
| 页面 README 没渲染 / 全是纯文本 | 确认文件在根目录且文件名 `README.md`；GitHub 默认渲染 main 分支根目录 README |
| 首页没显示 License | 确认根目录 `LICENSE` 文件存在；GitHub 偶尔延迟识别，重新打开页面 |
| 传上去后想删仓库 | Settings → 最底部 Danger Zone → Delete this repository（需输仓库名确认） |
| 仓库不小心建成了 Private，想改 Public | Settings → General → 最底部 Danger Zone → Change repository visibility |

---

## 8. 上传后第一件事：验证"别人能跑"（重要）

找一台**没装过本项目**的机器（或本机另开一个目录模拟），只按 GitHub 上的 `README.md` + `INSTALL.md` 操作：

```powershell
git clone https://github.com/<用户名>/<仓库名>.git mc-agent-bridge
cd mc-agent-bridge
Copy-Item dsh.env.example dsh.env     # 编辑 dsh.env：MC_HOME / SAVE_NAME / BOT_NAME ...
py tools\cold_start_test.py           # 期望 COLDSTART ok=1
py tools\doctor.py                    # 配好 dsh.env 后应全绿（没开游戏时部分 unknown 属正常）
py tools\check_all.py --offline       # 期望 pass 为主；详见下一段的已知限制
```

**已知限制（如实说明）**：干净副本直接跑 `check_all --offline` 会有约 10 项红，原因不是代码坏了，而是缺运行环境：没有 `dsh.env`、没有 `jobs/`、`logs/` 运行目录、没有本机游戏历史。按 `INSTALL.md` 配好 `dsh.env` 后大部分会转绿。这一条已写进台账 §79.538 的"未验证/风险"，后续版本计划把"缺运行目录"的判据改成 INCONCLUSIVE 而不是 FAIL。

---

## 9. 安全与合规提醒（别跳过）

1. **轮换旧 key**：本机历史里曾有 `secrets/deepseek.key`（值已泄露过）。到 DeepSeek 控制台**作废并重新生成**，新 key 只放环境变量或本机 `secrets/`（已被 .gitignore）。
2. **公开快照里没有** `dsh.env`、`secrets/`、`logs/`、`downloads/`、工具链；以后也**不要**手工把它们加回去。
3. **第三方资产**：仓库不含 Minecraft/Forge/Carpet/CC/ATM9/其它 mod 的二进制；`state/` 与 `build/` 里的数据是从整合包生成的（MIT 声明只覆盖本项目自有内容，是否可再分发请自行确认）。
4. **隐私**：快照里保留了 `personas/`（人设文本）和 `skins/`（皮肤图）；`docs/` 历史里会出现玩家名 `Au_Sn`。如果你不想公开这些，先在私有仓删除/替换，再重新导出（`tools/export_public.py` 会自动排除已删文件）。
5. **别把 GitHub 当成备份**：私有仓 + 本机磁盘才是你的完整历史；公开仓只是"发布出口"。

---

## 10. 命令速查（照着粘）

```powershell
# —— 首次上传（前提：第 1-2 节已完成，远端空仓已建好）——
cd "..\mc-agent-bridge-public"
git remote add origin https://github.com/<用户名>/<仓库名>.git
git push -u origin main

# —— 发布 v2.58.0（jar 在私有仓构建好后）——
cd "<私有开发仓目录>"
gh release create v2.58.0 "mod\build\libs\dshbridge-2.58.0.jar" --title "v2.58.0" --notes "首个公开版本"

# —— 以后更新 ——
cd "<私有开发仓目录>"
py tools\check_all.py --offline
py tools\export_public.py --out tmp\public-update
robocopy "tmp\public-update" "..\mc-agent-bridge-public" /MIR /XD ".git" /NFL /NDL /NJH /NJS
cd "..\mc-agent-bridge-public"
git add -A
git commit -m "sync public snapshot"
git push
```

---

## 附录 A：公开快照是怎么生成的（可复现）

```powershell
cd "<私有开发仓目录>"
py tools\export_public.py --check          # 只检查：EXPORTPUBLIC ok=1 problems=0
py tools\export_public.py --out "..\mc-agent-bridge-public" --init-git
```

`export_public.py` 做的事：
1. `git archive HEAD` 导出**当前跟踪树**（被 .gitignore 忽略的工具链/日志/下载物/本机 env 天然不在里面）；
2. 检查必需文件（README/INSTALL/LICENSE/CONTRIBUTING/dsh.env.example/核心 tools/mod 构建入口/离线数据）与禁止项；
3. 大文件检查（>50MB 警告，100MB GitHub 硬限）；
4. 可选 `--init-git`：在导出目录 `git init -b main` + 单提交，直接可 push；
5. 支持重复导出到已有目录（会先处理 Windows 只读 `.git` 文件）。

## 附录 B：想保留完整 git 历史怎么办（不推荐）

如果你一定要把**私有仓的历史**推上去（而不是干净快照），需要先清理历史：

```powershell
# 强烈建议先做全量备份（bundle 可以完整还原）
git bundle create ..\mc-agent-bridge-history.bundle --all

# 用 git-filter-repo（需单独安装）删除大文件和密钥
git filter-repo --strip-blobs-bigger-than 50M
git filter-repo --path secrets/deepseek.key --invert-paths
```

代价：所有 commit hash 会变（台账/文档里的旧 hash 引用全部对不上）、需要强推 `git push --force`、历史里可能还有其它本机痕迹没清干净。**除非你明确需要保留逐日提交历史，否则不要走这条路**——公开仓用干净快照 + Release 版本化更合适。

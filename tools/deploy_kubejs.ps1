# deploy_kubejs.ps1 —— 把仓库里的 KubeJS 脚本推回游戏实例（改完在游戏里跑 /kubejs reload server_scripts 即可生效）
# 2026-11-02 修（审计 §2.3 第 3 条）：$src 原来 = Join-Path $PSScriptRoot 'kubejs'
#   ⇒ 指向不存在的 tools\kubejs ⇒ Get-ChildItem 空 ⇒ **静默复制 0 个、退出码 0**（假成功）。
#   现在：$src = 仓库根\kubejs（$PSScriptRoot 是 tools\，上一层才是仓库根）；
#   并且**先核算源文件数**：源目录不在 / 0 个 .js ⇒ 明确失败（exit 1），不再静默成功。
#   -WhatIf 只核算并打印"会复制哪几个"，不碰游戏实例（可在游戏关着时安全自检）。
param([switch]$WhatIf)

$root = Split-Path -Parent $PSScriptRoot
$src = Join-Path $root 'kubejs'
# 目标实例：优先 $env:MC_HOME；否则读仓库 dsh.env 的 MC_HOME（2026-11 开源轮去本机化）
#   —— 不再写死本机 D:\pcl2\...；没配置就明确失败（exit 2），不静默指向别人的机器。
$mcHome = $env:MC_HOME
$dshEnv = Join-Path $root 'dsh.env'
if (-not $mcHome -and (Test-Path $dshEnv)) {
  $line = Select-String -Path $dshEnv -Pattern '^\s*MC_HOME\s*=' | Select-Object -First 1
  if ($line) { $mcHome = ($line.Line -split '=', 2)[1].Trim() }
}
if (-not $mcHome) {
  Write-Host "[X] 没配置 MC_HOME（环境变量或仓库 dsh.env）⇒ 不知道游戏实例在哪；见 INSTALL.md 的 dsh.env 配置"
  exit 2
}
$dst = Join-Path (Join-Path $mcHome 'kubejs') 'server_scripts'

if (-not (Test-Path $src)) { Write-Host "[X] 找不到仓库 kubejs 源目录: $src"; exit 1 }
$files = @(Get-ChildItem $src -Filter *.js -File)
Write-Host ("[src] {0} ⇒ 源文件 {1} 个" -f $src, $files.Count)
if ($files.Count -eq 0) { Write-Host "[X] 源目录里 0 个 .js ⇒ 拒绝静默成功（这就是 2026-11-02 修掉的那个 bug）"; exit 1 }

if ($WhatIf) {
  Write-Host ("[WhatIf] 目标 {0}" -f $dst)
  foreach ($f in $files) { Write-Host ("[WhatIf] 会复制 {0} ({1} B)" -f $f.Name, $f.Length) }
  Write-Host ("[WhatIf] 共 {0} 个 .js —— 源文件数核算通过（不碰实例）" -f $files.Count)
  exit 0
}

if (-not (Test-Path $dst)) { Write-Host "[X] 找不到实例目录: $dst"; exit 1 }
$n = 0
foreach ($f in $files) {
  Copy-Item $f.FullName (Join-Path $dst $f.Name) -Force
  $n++
  Write-Host ("[OK] {0} -> {1}" -f $f.Name, $dst)
}
if ($n -ne $files.Count) { Write-Host ("[X] 只复制了 {0}/{1} 个 ⇒ 失败" -f $n, $files.Count); exit 1 }
Write-Host ("[done] 已复制 {0} 个 .js -> {1}" -f $n, $dst)
Write-Host "下一步：py tools/raw.py `"kubejs reload server_scripts`""

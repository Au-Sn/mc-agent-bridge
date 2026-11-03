# tools/legacy/ —— ★历史脚本（保留作证据 ✗ 不保证可移植✗★）

这些脚本是**上一阶段**的施工/取证工具，现在**不在主链路上**（主链路见 `tools/` 顶层与
`agent/`）。保留它们只有一个目的：**历史证据可查**（当时的判据、当时的输出、当时的形状）。

## 怎么对待它们

1. **不要 import 它们**：主链路不许依赖 `legacy/`。
2. **不保证可移植**：它们是历史现场的一次性脚本，质量/依赖都不如顶层工具。
3. **本机绑定已清理（2026-11-03，task-14）**：
   - `ROOT = Path(r"C:\Users\...")` → `Path(__file__).resolve().parents[2]`（仓库根，不写死机器）；
   - 存档/实例路径 → `import paths`（**没配 `dsh.env` 时明确报错**，不会静默用本机路径）；
   - node 路径 → 环境变量 `DSH_NODE`（或 PATH），dsh 的 `lib/bin.js` → `DSH_BIN_JS`；
     未配置时脚本会打印"需要配置 …"并非零退出。
4. **新增历史脚本请照此办理**：要么不写死本机路径，要么在入口加同样的 guard。
   `tools/portability_test.py` 会把 `tools/legacy/*.py` 一起扫描（有理由的例外表除外）。

## 清单（按用途）

| 文件 | 当时的用途 |
|---|---|
| `dsh_live2.py` / `dsh_live3.py` | 早期 SDK/ACP 协议**形状试探**（后续被 `tools/dsh_acp.py` 取代） |
| `read_joblog.py` | 从 CC 计算机磁盘直接读 job.log（不依赖网络回传） |
| `chest_probe.py` / `find_machines.py` / `floor_scan.py` | 早期世界/容器探针 |
| `m1_debug_cols.py` / `m1_measure2.py` / `self_cell_test.py` / `cell_truth_test.py` | 地图/高度模型调试 |
| `recover_mc_mcp.py` / `test_persona_reload.py` / `v210_check.py` / `v29_verify.py` | 恢复/人设/版本一次性验收 |
| `append_sec29.py` / `append_sec30.py` | 台账历史章节的写入脚本 |
| `bench_v26.py` / `bench_v28.py` | 早期基准 |

> 主链路的口径在 `tools/` 顶层；这里只作考古，**以当前代码与判据为准**。

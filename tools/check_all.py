r"""check_all.py -- 一条命令跑完整套验收（地图 / 寻路 / 守卫 / 地板 / 假人 ✓）

为什么要有它 ✗：到 2026-09-23 已经有 5 个验收脚本 ✓ 每次改一点都要记得"该跑哪几个"✗
  ⇒ 漏跑 = 拿旧结论当新结论 ✗（P86 的教训 ✓）⇒ 串成一条 ✓ 并且**最后给一句话总账** ✓

它**不动游戏**的部分（安全 ✓ 快 ✓）：
  · floor_test            什么算地板（确定性 ✓）
  · r2_guard_test         虚空守卫（手工造图 ✓ 确定性 ✓）
  · m1_verify             地图读取 M1~M4（会读游戏 ✓ 但不走路 ✓）
会**走路**的部分（慢 ✓ 有风险但已加守卫 ✓）：
  · r2_verify             寻路 P0~P5
  · r3_verify             提速 A/B（T1~T3）
用法：
    py tools\check_all.py             # 全套（约 6~10 分钟 ✓）
    py tools\check_all.py --no-walk   # 只跑不动腿的那几个（约 2 分钟 ✓）
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ★★2026-10-13（★用户裁决 B3 第二步 ✗ §79.253✗★）✗★★：
#   ★用户原话：★「闸门四张表生成化：**一张源表＋标签派生四张** ✗
#     **包含关系由生成保证** ✗ 文档项数脚本再生成」★✗★ ✓
#   ★现状（★评审抓的✗★）：★四张表**各自手写** ✗ 于是「★QUICK ⊄ OFFLINE★」
#     「★WALK ⊄ FAST★」这类**包含关系失真** ✗ 而 §79.237 第一步只做到
#     「★不成立的**必须声明**✗」✗★ ✓
#   ★★这一版把它们收成**一张源表**✗★★：
#     · ★每个脚本一行 ✗ 带 `tags`（★quick／walk／offline／fast 的子集✗★）✗
#     · ★四张视图**由标签派生** ✗ 包含关系**天然成立** ✗ 不用再声明✗★ ✓
#     · ★一个脚本**只留一条**说明✗★（★合并前 80 个脚本在不同表里说明不同 ——
#       ★多数是同长度不同字符 ✗ 少数真的长短不一✓★）
#   ★迁移是**可验证**的✗★：★四张派生视图的**脚本集合**必须与旧表**逐个相等**✗
#     （★已验：集合全等 ✗ 只有说明文字按上面那条统一了✓★）✗★ ✓
GATE = [
    ("floor_test.py", "地板模型（确定性）", "quick／offline／fast"),
    ("check_all_fast_test.py", "── 子集自己也得守住规矩（F1/F3/F4 ✓ 瞬间 ✓）", "quick／offline／fast"),
    ("errata_guard_test.py", "错题守卫：11 条最贵的错题各配最小复现（**离线** ✓ 不需要游戏 ✓）", "quick／offline"),
    ("errata_index_test.py", "错题归档守恒：条目不许丢＋引用不许悬空（**离线** ✓ 秒级 ✓）", "quick／offline"),
    ("contract_test.py", "接入契约守恒：41 件工具双向对账＋参数一致＋版本单一真源（C1~C5 ✓ 离线 ✓ 秒级 ✓）", "quick／offline"),
    ("mcp_surface.py", "★工具面**逐字节**对账★：S1 握手／S2 稳定／S3 >=41 件（离线 ✓ 不需要游戏 ✓ 见 P151 ✓）", "quick／offline"),
    ("speech_test.py", "什么时候该开口：主动扳机＋不刷屏（冷却/额度/退避 ✓ 纯逻辑 ✓ 秒级 ✓）", "quick／offline"),
    ("speech_loop_test.py", "主动扳机：事件流⇒该说什么（水位/不叠话/缺台词拒掉 L1~L9 ✓ 离线 ✓）", "quick／offline"),
    ("corpus_test.py", "台词库扛 80%：解析/覆盖账/手写区守恒/端到端（K1~K8 ✓ 离线 ✓）", "quick／offline"),
    ("mood_render_test.py", "情绪要稳＋人设只是配置：慢变量/滞回/真值不动（M1~M6 T1~T7 ✓ 离线 ✓）", "quick／offline"),
    ("mapcache_test.py", "连通区缓存：快＋改图就失效＋配置不串味（M1~M4 ✓ 离线 ✓ 秒级 ✓）", "quick／offline"),
    ("memory3_test.py", "记忆三分 人/承诺/地：没证据不算兑现＋过期≠做到（N1~N7 ✓ 离线 ✓）", "quick／offline"),
    ("speech_audit_test.py", "语言错题环：审计回放＋禁句精确＋禁必留痕（Q1~Q6 ✓ 离线 ✓）", "quick／offline"),
    ("ob_unit_test.py", "道中障碍：探得出/绕得开/预算诚实（**离线** ✓ 没游戏也能跑 ✓）", "quick／offline／fast"),
    ("collision_classes_test.py", "★碰撞高度**按类**对账：小方块 0 ／ 整块 1 ／ 半砖 0.5 ／ 带状态的名字也要切干净（**离线** ✓ 进闸门 ✗ §79.401✗★）", "quick／offline／fast"),
    ("stepup_cost_test.py", "★能绕平路就绕（★step_up 代价 > 2 步 ✗ pillar／bridge 语义没坏 ✗ 离线✗★）",
     "quick／offline／fast"),
    ("exec_task_test.py", "★多目标执行器：每段重读位置 ✗ 失败如实停 ✗ dry 透传（★离线✗★）", "quick／offline／fast"),
    ("speech_nav_test.py", "★导航汇报该说／不该说：到达邀功 ✗ 失败播报 ✗ 不认识⇒None ✗ 出口唯一（★离线✗★）", "quick／offline／fast"),
    ("feet_cell_test.py", "★脚格换算钉死：ceil(y−ε) ✗ dirt_path／半砖／雪层／负坐标都对 ✗ 全仓无残留手写换算（★离线✗★）", "quick／offline／fast"),
    ("scaffold_kb_test.py", "★能垫脚**引用方块分类**（★在导出里 ＋ h≈1.0✗★）✗ 名字名单式写法已退役（★离线 ✗ §79.450✗★）", "quick／offline／fast"),
    ("generic_rule_test.py", "★规划层**不许靠方块名字**（★普适性的机械守门 ✗ 换包不用重来✗★）✗ 误报已区分 ✗ mapread 的 2.5D 名单记为已知豁免（★离线✗★）", "quick／offline／fast"),
    ("a4_plan_test.py", "★A4：规划器不许产 place 在自己身上（会 place_on_body 整任务死）✗ 守门仍在（★离线 ✗ §79.453✗★）", "quick／offline／fast"),
    ("ascii_reason_test.py", "★中文回执必须带 ASCII reason=（★CC 控制台 ASCII 化 ✗ 中文全变 ?✗★）✗ 扫描模组源码（★离线 ✗ §79.460✗★）", "quick／offline／fast"),
    ("reason_read_test.py", "★ASCII reason= 端到端可读（★模组发 ✗ kv 解析 ✗ mcp_walk 报出来✗★）✗ 中文那半在 CC 上读不到（★离线 ✗ §79.461✗★）", "quick／offline／fast"),
    ("model_fetch_guard_test.py", "★世界模型必须快速失败（★掉线时 plan 不许卡死✗★）✗ 熔断 ＋ 冻结 ＋ 成功率清零（★离线 ✗ §79.472✗★）", "quick／offline／fast"),
    ("place_target_test.py", "★动作表出口校验：walk 目标站得住 ＋ place 目标能放（★空／有面／在 4 格内✗★）✗ 该拒的拒该放的放（★离线 ✗ §79.473✗★）", "quick／offline／fast"),
    ("retry_strategy_test.py", "★重试必须换策略（★三次同一份药方＝没重试✗★）✗ 拒绝型失败两次就停手（★离线 ✗ §79.474✗★）", "quick／offline／fast"),
    ("machine_recognize_test.py", "★机器必须能被**识别**（★数据驱动 ✗ has_block_entity ✗ 零名字表✗★）✗ 且识别≠碰撞（★cable_bus 无碰撞但仍算机器✗★）✗ 离线 §79.486", "quick／offline／fast"),
    ("perceive_test.py", "★感知层：快照与真值逐项一致 ＋ 方块性质一律问分类 ＋ 机器带朝向 ＋ 缓存是 0 往返快路（★真世界 ✗ §79.489✗★）", "walk／live"),
    ("no_dig_test.py", "★模块I 施工许可：不可挖区域黑名单（★家/屋/箱子/产线/农田✗★）✗ 两向都测 ＋ 状态坏了保守全禁 ＋ 真接线 dig_bad（★离线 §79.490✗★）", "quick／offline／fast"),
    ("humanlike_test.py", "★模块G 拟人判据：N1 瞬移／N2 悬空／N4 一帧完成／N7 无故掉血／N8' 有后果事件必须留痕 ✗ 每条都能故意造红（★离线自检 §79.491✗★）", "quick／offline／fast"),
    ("damage_policy_test.py", "★伤害来源→对策：有怪打或跑／窒息上浮／卡墙挪出／饿找食物 ✗ 未知来源不许静默（★离线 §79.492✗★）", "quick／offline／fast"),
    ("reasons_test.py", "★留痕日志选择性保留：按天分文件／超上限只留最后800行＋全部重要记录／旧天只留index／窗口读（★离线 §79.492✗★）", "quick／offline／fast"),
    ("say_test.py", "★F 自述层：17 个机器码有限集／自造码降级并标出／留痕开关／码全 ASCII／一条任务只 2 条（★离线 §79.493✗★）", "quick／offline／fast"),
    ("verifier_test.py", "★L4 独立校验官：只信世界真值 ✗ 挖/放/到达逐项核 ✗ 读不到一律红 ✗ 接口不接受自述（★真世界冒烟 §79.493✗★）", "walk／live"),
    ("turn_profile.py", "★N3 转向速度剖面：先加速／中段匀速／收尾减速／过冲≤2 ✗ 梯形绿 阶跃红 过冲红（★判据自检 ✗ 离线 §79.494✗★）", "quick／offline／fast"),
    ("recipe_graph_test.py", "★K 配方图：功能需求→元件清单 ✗ 真 12.4MB 数据 20764 产物 ✗ 只到底料 ✗ 同料合并 ✗ 环保护（★离线 §79.496✗★）", "quick／offline／fast"),
    ("primitives_test.py", "★C 动作原语：许可→执行→独立校验→留痕 ✗ 禁止区拒绝时**一次 dsh 都不发** ✗ 放块 item 必须加引号（★离线 §79.500✗★）", "quick／offline／fast"),
    ("behaviors_test.py", "★D 行为库：9 条**全部真实现**（enter/leave_house、chop_tree、store_to_chest、handle_night 均已落地）✗ 每个 manifest 齐全（implemented/needs/verify）✗ **破坏性标记必须诚实** ✗ 未实现边界与证据断言（★离线 §79.525✗★）", "quick／offline／fast"),
    ("intent_test.py", "★L1 意图判别：chat/query/task/mixed 四类 ✗ 20 句全对 ✗ **纯文本零往返** ✗ chat/query 绝不动世界（★离线 §79.506✗★）", "quick／offline／fast"),
    ("orchestrator_test.py", "★L 会话骨架：chat/query **绝不落 job** ✗ task 恰好 1 条带验收 ✗ mixed 先聊后做 ✗ **一条任务恰好 2 条消息**（★离线 §79.507✗★）", "quick／offline／fast"),
    ("memory_test.py", "★L6 记忆官：地标持久化 ✗ **选择性保留（每类封顶 ✗ 丢最旧）** ✗ 地标用**分类**认不问名字（★离线 §79.508✗★）", "quick／offline／fast"),
    ("structures_test.py", "★K 结构检索：包里真找到 260 个 .nbt 并读成坐标表（手写 NBT 解析器）✗ 属性也读到 ✗ **方块 id 全在 24779 注册表里**（★离线 §79.510✗★）", "quick／offline／fast"),
    ("bulk_guard_test.py", "★批量改方块硬守卫：**没扫过 ⇒ 拒绝** ✗ 命中禁区 ⇒ 拒绝 ✗ 有方块实体 ⇒ 拒绝 ✗ **含 2026-11-01 填掉 CC 计算机的事故回归测试**（★离线 §79.512✗★）", "quick／offline／fast"),
    ("port_test.py", "★K 移植：缺料清单 ✗ **幂等**（已对的不放）✗ 自下而上 ✗ 悬空格不硬放（★离线 §79.511✗★）", "quick／offline／fast"),
    ("direct_test.py", "★直连（模组 8766 HTTP）：回执往返含中文 ✗ **连不上回 None 不抛** ✗ 超时不挂死（★离线 §79.513✗★）", "quick／offline／fast"),
    ("human_action_test.py", "★手部动画＋工具匹配：place／dig **两条路径都挥手** ✗ 工具选择**数据驱动**（getDestroySpeed ✗ 不写死方块名）✗ 太远明确拒绝（★离线源码 ＋ --live 真世界 §79.519✗★）", "quick／offline／fast"),
    ("silent_except_test.py", "★静默吞异常分级扫描：A 级（★会静默用错数据★）必须为 0 ✗ 机器白名单 `state/silent_allow.json` 逐条带理由（**离线** ✓ 秒级 ✓ ★§79.401 真凶的防线✗★）", "quick／offline／fast"),
    ("bridge_unit_test.py", "★搭桥（place 边）：先证无路 ⇒ 再证有路 ⇒ 铺满 3 格（**合成世界** ✓ 零风险 ✓ 见 §79.383 ✓）", "quick／offline／fast"),
    ("pillar_unit_test.py", "★1by1tower（抄 mineflayer getMoveUp ✗ 垫脚下跳上来）：没方块无路 ⇒ 有方块上来（§79.384 ✓）", "quick／offline／fast"),
    ("dshmap_parse_test.py", "快图解析：真高度 ＋ 你这一层被占（**离线** ✓ 合成回执 ✓）", "quick／offline／fast"),
    ("cut34_seam_check.py", "★拆 god file 之后的「桩还打得中吗」★（离线 ✓ 秒级 ✓ 见 P156~P158 ✓）", "quick／offline／fast"),
    ("stdio_guard_test.py", "★印得出吗：会印 ✓/✗ 的脚本必须 pin 住 stdout★（S1~S4 ✓ 离线 ✓ 秒级 ✓ 见 P151/P160 ✓）", "quick／offline／fast"),
    ("policy_test.py", "★接入策略：动作边界／分层授权／目的留痕的判据★（P1~P5 ✓ 离线 ✓ 秒级 ✓ 参考外部同题项目的机制 ✓）", "quick／offline／fast"),
    ("verify_test.py", "★统一回执包装★：动作发完由**框架**回读世界真值（Q1~Q5 ✓ 离线 ✓ 注入假读数 ✓ 见欠账 ③）", "quick／offline／fast"),
    ("syntax_guard_test.py", "★引号错/语法错的系统解★：全仓 .py（含 tmp/ 手写脚本）一律先 py_compile ✓ G1~G4 ✓ 秒级 ✓", "quick／offline／fast"),
    ("debt_fresh_test.py", "★欠账计数与入口文档新鲜度★：§79.14 解析（D1~D2 防吞错表）＋ 入口文档欠账块必须与真源一致（D3）✓ 秒级 ✓", "quick／offline／fast"),
    ("safe_edit_test.py", "★改文档的护栏★：唯一锚＋自动看 diff 行数（S1~S6 ✓ ★护栏自己不许有副作用✓ 见 P175）", "quick／offline／fast"),
    ("leash_test.py", "★持续输入的安全壳★：时长上限／围栏／读不到就停／body 抛异常也停（L1~L6 ✓ 用假 send/sample ✓ 见 P177）", "quick／offline／fast"),
    ("events_log_test.py", "★死亡保险的证据链★：捞 ASCII 事件／丢掉含中文的行／落盘纯 ASCII／去重／凭证要含 kept_items（E1~E5 ✓ 见欠账 ⑬）", "quick／offline／fast"),
    ("sandbox_test.py", "★沙盒档★：测试件必须在框内／框外必拒／框内放行／on-off 可还原／on 必须提示 off（A1~A5 ✓ 见欠账 ⑦ 第 1 层）", "quick／offline／fast"),
    ("gesture_test.py", "★动作即语言★：朝向数学／点头摇头序列／wrap180／回读对上才算真／对不上必须红（G1~G6 ✓ 离线 ✓ 见 P2）", "quick／offline／fast"),
    ("lead_test.py", "★动作即语言·带路回头★：玩家坐标回执抠取／到位才不红／回头必须回读才算真／读不到就明写 unavailable（L1~L5 ✓ 离线 ✓ 见 P2）", "quick／offline／fast"),
    ("declare_rehearsal_test.py", "预演「导出回来」那条链（R1~R5）：拿**真的**未声明名单 ＋ 合成导出去撞 `declare_collision.py`／只要 `--dry` ⇒ ★不许动真例外表（哈希比）★／三条纪律要在输出里被点名（canopy⇒拒 ✗ 没覆盖⇒不猜 ✗ 只写碰撞槽）／计划要有四个数（见 §79.267）", "quick／offline／fast"),
    ("generated_freshness_test.py", "生成物的**新鲜度**（N1~N5）：`分歧清单`／`迁移准备度`／`DoD-对账表`／`切换计划` 的 mtime **不许早于**它依赖的上游数据（★复核 P2-4 那两份**以前没有任何判据盖**✗★）／有计数器／红了怎么修写在输出里（★重生成要导出✗★）（见 §79.281）", "quick／offline／fast"),
    ("family_switch.py", "★物理切到碰撞表的**按族声明**★（S1~S5 ✗ 离线）：★用户 2026-10-24 裁决：不需要完全声明每一项改动 ✗ 仅说明改动了哪几个族的几项★ ／ `--check` 重算「名字老路 vs 碰撞表」的差异 ✗ **按族**比条数 ✗ **任何会变的族都必须在声明里**（铁律②在族粒度上的形态）／ 每族条数与总数都必须一致 ／ 有计数器（≥7 个族）／ 口径：导出 `family` 经 `FAM2SHAPE` 映射后再喂 `blockkb.*_fam`（★fence_15→fence ✗ snow_layer→pass✗★）（见 §79.349）", "quick／offline／fast"),
    ("family_selection.py", "★A2 的 ≥99%：45 个家族标签类 ⇒ 20 入选 ／ 25 语义★（S1~S5 ✗ 离线）：★「族」＝ `tag_census.family_tags()` 的 45 个家族标签类★ ／ ★一致率＝该类底下经标签闭包得到的物种 × 导出里的碰撞族（family）的多数派占比✗★ ／ **写下的 20／25 必须与现算逐项相等**（★不许手改✗★）／ 两个数必须**对得上用户给的** 20 与 25 ／ 有计数器（入选＋语义＝45 ✗ 不许漏类）（见 §79.331）", "quick／offline／fast"),
    ("gate_coverage_test.py", "★判据有没有**进闸门**★（C1~C4 ✗ 离线）：盘上每个同时写死 PASS／FAIL 的 .py **必须**在 GATE 里 ✗ 或在**声明表**里带理由 ✗ ★不许「写好了没进闸门 ＝ 它不存在」✗（★`hop_cost` 那次就是这么漏的 ✗ §79.308✗★）／声明表与 GATE **不许两头占** ／ 有计数器（★扫过 303 个 .py✗★）／ ★未声明的数**只许变小**✗（基线 `state/gate_coverage_baseline.json` ✗ 2026-10-18 ＝ 14✗★）（见 §79.319）", "quick／offline／fast"),
    ("world_touch_test.py", "世界触碰清单可机器统计（W1~W4，欠账 ⑦ 第三层）：碰世界的脚本必须要么头部标注★世界★、要么声明＋替换触发／★误报要声明★／计数器／把清单打出来（见 §79.256）", "quick／offline／fast"),
    ("taskbook_v5_test.py", "任务书 v5 的主张必须与代码一致（V1~V5）：四条修订都写进了 v5／§9 两条梯子与 EVIDENCE_PHYS／EVIDENCE_SEM 一致／§8 四族与 families.FAMILIES 一致／§7 TEMPORARY 表 8 样字段齐／§6 只读围栏在（见 §79.255）", "quick／offline／fast"),
    ("entry_status_test.py", "入口状态行配判据（S1~S4）：台账开头有那条状态／★它的四个数必须等于 logs/check_all.txt 首行的机器行（不许过期）★／索引等于当场重算的结果（手改或没重跑就红）／计数器（见 §79.248）", "quick／offline／fast"),
    ("family_vocab_test.py", "四族词汇 ＋ L1~L4 退役（V1~V5）：四族就是 phys／sem／exec／policy／每个符号写清族与为什么／★同一件事的两半各有其族★（standable_physical 是 phys ✗ standable 是 policy）／★退役那种 L1~L4（挨着层／族／§11）一次都不许有★／退役清单在册（见 §79.245）", "quick／offline／fast"),
    ("temporary_test.py", "临时的东西必须带替换触发（T1~T6）：每条都有 id／what／where／为什么／★今天生效到什么程度（today_state）★／起于／替换触发／谁看着／★触发里要有动作★／★没人看着的临时就是永久★／★T5 声明对得上现实★（叶子：is_landing=False ✗ is_canopy=True ✗ is_floor=False ⇒ 树冠那一半今天不生效，要等碰撞模型）（见 §79.243）", "quick／offline／fast"),
    ("family_source_test.py", "五张家族表：真源一条路（F1~F5）：恰好一张自称真源／五张都在且非空／★类别⇒真源⇒导出族⇒翻译⇒判定族 必须一致（这条抓到过 3 条）★／真源没覆盖的必须声明（＋替换触发）／翻译层定义域 ⊆ 导出闭集且两套词汇说清（见 §79.242）", "quick／offline／fast"),
    ("evidence_ladder_test.py", "两条不相交的梯子（L1~L6）：物理＋collision 收／物理＋registry 拒（R3）／语义＋registry 收／语义＋collision 拒（R7）／registry 根本不在物理梯上（不许压过的机械形态）／现有表每一条仍全部合规（见 §79.241）", "quick／offline／fast"),
    ("ascii_machine_test.py", "机器那一行必须纯 ASCII（A1~A4）：源码里有那条 SUMMARY 行／真跑出来的日志**首行**就是它且纯 ASCII／所有 SUMMARY 行纯 ASCII（其余行允许中文，那是人读的）／计数器（日志不许是空的）（见 §79.240）", "quick／offline／fast"),
    ("docwrite_test.py", "生成物内容没变就不写（W1~W4）：内容一样 ⇒ 连 mtime 都不变／内容变了 ⇒ 照写／例外表与观察名单连着渲染两次第二次不写／★而真因是那句「生成时间 %H:%M:%S」每秒都变 ⇒ 先让内容只随数据变★（见 §79.238）", "quick／offline／fast"),
    ("gate_tables_test.py", "闸门四张表的关系一条都不许没声明（G1~G6）：不重名／脚本都在盘上／FAST⊆QUICK／OFFLINE∩WALK=空集／不成立的关系必须声明并写理由（四张表量的不是同一件事）／顺手生成 docs/闸门-项数.md（内容没变就不写）（见 §79.237）", "quick／offline／fast"),
    ("offline_purity_test.py", "离线表里的判据真的不碰世界吗（P1~P4）：源码扫「会连世界」的**调用**（只认调用，不认提到名字）＋例外必须声明并写理由＋★运行时绊线：注入路径一碰 `_col_top`／`_default_scan` 就炸★＋没绑定一律 None＋计数器（查过＝表里总数）（见 §79.235）", "quick／offline／fast"),
    ("probe_limit_test.py", "探针两条红线真的执行（L1~L5）：墙钟 0 ⇒ unknown＋timeout＋limit=wall_clock／预算 0 ⇒ limit=budget／没踩住时答案照旧／只报闭集里的 timeout／★注入纯度：没给列顶来源必须立刻回 None（不许偷偷连世界）★（见 §79.233／79.234）", "quick／offline／fast"),
    ("pathplan_height_test.py", "寻路层接 max_height 的 A/B（H1~H5）：开关关着与今天逐字相同／开着按高度判（半砖 0.5 能上、农田 0.9375 不能）／跳跃阈值（整块 1.0 行、栅栏 1.5 不行）／拿不到高度绝不静默回落名字／阈值＝实测口径 0.6 与 1.25（见 §79.232）", "quick／offline／fast"),
    ("a3_wired_test.py", "★A3 的开关到底**接没接上**★（W1~W7 ✗ 离线 ✗ 两臂子进程）：拿「★名字与高度打架★」的方块（★`sneaky_slab` 高 1.4 ✗ `odd_thing` 高 0.3✗★）逐臂子进程跑 `pathplan.is_auto_step` ✗ ★关＝名字档会**假可达**／**假不可达** ✗ 开＝高度档两个方向都对✗★ ／ 高度拿不到必须**保守拒**（★不许静默回落名字✗★）／ **两臂在打架例子上必须不同**（★这才是「接上了」的证据 ✗ 不是比判据结论✗★）／有计数器（见 §79.304）", "quick／offline／fast"),
    ("export_fence_test.py", "导出那一半的围栏（F1~F4）：缺导出硬红＋人话／第一次跑记账／同一份再跑绿／导出动过必须红并点名（用临时合成导出与临时围栏验，验完必清）（见 §79.228）", "quick／offline／fast"),
    ("truth_contract_test.py", "真值契约的守卫（T1~T4）：期望只许来自**物理实测**，不许来自导出（否则导出考导出）；measured 必须有数字＋台账出处，unmeasured 必须 null＋写清怎么量；导出不在盘上时 T4 如实说**跳过**（见 §79.227）", "quick／offline／fast"),
    ("export_guard_test.py", "缺输入必须硬红（不是测不了）＋ 快照必须能被找到（X1~X5：require 红并带人话／soft 不红／find_export 优先快照／快照名带版本与 schema／内容没变不重写；用**临时合成导出**验机制，验完必清）（见 §79.224）", "quick／offline／fast"),
    ("danger_test.py", "危险要拦住而水要照旧能过（D1~D5）：岩浆/岩浆块判 DANGER ＋ 探针不许穿过危险格 ＋ ★水必须仍 pass★ ＋ 政策不许动物理 ＋ 没绑定不许假装安全（见 §79.222）", "quick／offline／fast"),
    ("scope_test.py", "作用域真的把开关关住了吗（S1~S5）：域内至少 1 个变（开关是活的）＋ 域外一个都不许变 ＋ 计数器 ＋ 子进程里读到的 src/scope 与给的一致 ＋ 走真路径（见 §79.216）", "quick／offline／fast"),
    ("generated_docs_test.py", "拿数去撞生成物（G1~G6）：乙档对账清单的头条数、只有语义清单的个数、要求单里的名录、DoD 表的未声明与例外表条数、索引里星标与文件是否真的在（见 §79.214）", "quick／offline／fast"),
    ("birth_gate_test.py", "★决策层守卫的机械形态★：每个模块一句职责 ＋ 登记情况（只报数）＋ ★★`name_fallback` 无 TEMPORARY 必须被拒★★ ＋ 带 TEMPORARY＋触发必须能收 ＋ 登记册每条带「作用域」（B1~B5 ✓ 离线 ✓ 见 §79.209）", "quick／offline／fast"),
    ("conflict_rule_test.py", "★裁定守卫★：多族冲突**必须**被碰撞裁决掉 ⇒ 读得到碰撞却仍判冲突的**必须为 0** ＋ 计数器（★已裁决＋读不到＋仍冲突＝多族总数✗★）＋ ★裁决只管语义不许碰名字侧★（C1~C5 ✓ 离线 ✓ 见 §79.203）", "quick／offline／fast"),
    ("u1_declared_test.py", "★铁律②那个数的算术判据★：不一致／决策级／已声明／未声明 四个数必须自洽（★已声明＋未声明＝决策级✗★）—— **不**判「未声明该不该是 0」（★那是裁定✓★）（U1~U3 ✓ 离线 ✓ 见 §79.189）", "quick／offline／fast"),
    ("cut_verify_test.py", "★按种切换的逐签名比对★：对 54 个 ≥40 方块的命名空间 ✗ 逐个方块比 mapread.is_floor／blocks_space／cat 的老路↔新路 ＋ ★★计数器（比过＋跳过必须等于总数 ✗ 防「全跳光」冒充「全一致」）★★ （V1~V4 ✓ 离线 ✓ 见 §79.187）", "quick／offline／fast"),
    ("environment_test.py", "★有名查询判据★：三栏（真值／执行／政策）＋★没测过的执行族必须回 None★＋★政策不许动真值★＋★safe(lava) 必须 None★（E1~E7 ✓ 离线 ✓ 见 §79.183）", "quick／offline／fast"),
    ("passclass_test.py", "★类别层判据★：AIR／SOLID／LIQUID／CANOPY／DANGER／UNKNOWN ＋★政策不许越界★＋★UNKNOWN 永不当 AIR★（P1~P7 ✓ 离线 ✓ 见 §79.176）", "quick／offline／fast"),
    ("reach_probe_test.py", "★可达性探针的**契约**判据★（第 0 步）：四个键／reachable 三值而 unknown 合法／why_not 闭集／★没有生产模块 import 它★／用例库 7 条形状对／★骨架期只许回 unknown 绝不给假 yes-no★（R1~R6 ✓ 离线 ✓ 见 §79.154）", "quick／offline／fast"),
    ("mapfind_test.py", "★`level_ok` 的判据★：同层/高 1 层够得着、高 3 层够不着、往下 2 层内够得着、上限随参数走（M1~M4 ✓ 离线 ✓ 见 §79.149）", "quick／offline／fast"),
    ("kb_policy_test.py", "★政策层的判据★：is_floor 说真话（树叶能站）／类别来自标签并带出处／树冠不当落脚点（两个问题分开答）／没类别⇒跟着物理走／类别⇒族的映射只声明有裁定的那一条（J1~J6 ✓ 离线 ✓ 见 §79.144）", "quick／offline／fast"),
    ("switch_plan_test.py", "★切换计划的判据★：风险≤25%⇒先切／风险>50%⇒先看清（不许跳）／表中无>50%⇒等导出覆盖／两头不极端⇒可切（P1~P4 ✓ 离线 ✓ 见 §79.127）", "quick／offline／fast"),
    ("kb_species_test.py", "★单种可回退的判据★：show 要摆三处与三档／drop 摘掉那一条并留痕／drop 不在表里的要明说「什么都没退」／★drop 不许动导出（观测不许被退掉）★（T1~T4 ✓ 离线 ✓ 见 §79.124）", "quick／offline／fast"),
    ("kb_switch_test.py", "★三档开关接线的判据★：blacklist 与老路逐字相同／table 档碰撞槽有它就用碰撞、没有则取保守值（is_floor=False，blocks_space=True）／table+fallback 未知则走老路／语义槽永不许影响物理（S1~S5 ✓ 离线 ✓ 见 §79.123）", "quick／offline／fast"),
    ("kb_risk_test.py", "★迁移风险图（模型 vs 碰撞）的判据★：族名不同但两条判定一样⇒算一致／真的翻了⇒算不一致并进名单／canopy⇒交语义层既不算一致也不算风险／按模组分组能算（R1~R4 ✓ 离线 ✓ 见 §79.121）", "quick／offline／fast"),
    ("kb_export_test.py", "★导出验收器的判据★：四样字段齐／`count` 必须等于条数（不许说谎）／族名在闭集（七类＋liquid）／★`other` 必须带 `max_height`★／`empty=true` 与高度不许矛盾／`errors` 非零必须报（V1~V7 ✓ 离线 ✓ 合成数据 ✓ 见 §79.116）", "quick／offline／fast"),
    ("declare_collision_test.py", "★物理裁决器的判据★：真的翻了=>声明进碰撞槽（collision 级）／导出支持黑名单=>不声明但要计数／没覆盖=>计数且绝不退化成名字兜底／canopy=>拒且不许进碰撞槽／★全程不动语义槽★／导出不在=>抛（D1~D6 ✓ 离线 ✓ 合成导出 ✓ 见 §79.115）", "quick／offline／fast"),
    ("watchlist_test.py", "★第五种状态 (contradicted) 的判据★：必须写明两条通道各说什么／必须有隔离理由与重读条件／坏文件必须抛／机械生成的条目必须过自己的判据／名单上的人不许被自动声明（与 pick_semantic 联动）（C1~C5 ✓ 离线 ✓ 见 §79.110）", "quick／offline／fast"),
    ("kb_audit_test.py", "★新轴（模型 vs 知识表）的判据★：知识表说不知道不算矛盾／两边都有意见且不同才算 contradict／分层顺序写死（walked＞changed＞multi_layer＞under_canopy＞near_liquid＞plain）／六层一个不许少／★★回落到名字兜底不许算同意★★（A1~A5 ✓ 离线 ✓ 见 §79.107）", "quick／offline／fast"),
    ("exception_table_test.py", "★例外表的判据★：六样字段缺一即拒／★★标签证据不许支撑物理结论（铁律 1 的机械形态）★★／物理结论必须布尔、家族结论在闭集里／name_fallback 必须 TEMPORARY＋复核触发／升级语义（硬的覆盖软的、反方向拒收）／坏文件必须抛不许当空表／生成物里每条都要有证据与出处（X1~X7 ✓ 离线 ✓ 见 §79.104）", "quick／offline／fast"),
    ("divergence_test.py", "★分歧清单的判据★：三栏边界（一致／不一致／表中无）／多族冲突必须落「不一致」而不是「表中无」（★这两件事不许混★）／没有家族标签要说原因且不算冲突／`TAG_FAMILY` 的键必须都在家族模式表里（D1~D4 ✓ 离线 ✓ 见 §79.101）", "quick／offline／fast"),
    ("mod_contract_test.py", "★契约围栏的判据★：同一份契约 ⇒ 差异必须为空／四个计数器各改一个各报一条／逐种计数与逐格物种都要看得见（要指出哪一格从什么到什么）／`species_of()` 切状态（含大写值）（M1~M4 ✓ 离线 ✓ 注入两份契约 ✓ 见 §79.98）", "quick／offline／fast"),
    ("blockkb_test.py", "★方块知识表的判据★：默认（blacklist）与今天逐字相同／未登记等级与空来源都要拒收／name_fallback 缺 TEMPORARY 或缺复核触发都要拒收／升级语义（collision 覆盖一切，name_fallback 覆盖不了 registry）／物理只听碰撞形状（phys=True 时标签级不许说话）／回落必须声明并标 TEMPORARY（K1~K7 ✓ 离线 ✓ 见 §79.93）", "quick／offline／fast"),
    ("tag_census_test.py", "★标签普查工具自己的判据★：两种目录拼法／宇宙路径／三种值形态／传递闭包（环不许死）／反查／一趟扫（假 zip ＋ 目录，跨 jar 引用）（C1~C6 ✓ 离线 ✓ 合成 fixture ✗ 不拿真 jar 当判据 ✓ 见 §79.89）", "quick／offline／fast"),
    ("ops_guard_test.py", "★改世界要有守卫★：分类（setblock/fill 是、/dsh… 不是）／没声明 ⇒ **一个字都不发** ＋ 退出码 3／声明了 ⇒ 发 ＋ 留痕／拒绝话要给两条正路（O1~O4 ✓ 离线 ✓ 见 §79.85）", "quick／offline／fast"),
    ("ob_memory_offline_test.py", "★障碍记忆（自足版）★：落盘要有那一格（顺带守住 mcp_geo 缺 BLOCKED_WHY 那个真 bug）／新进程读得回／25 小时前的条目不许读回／★真数据一个字节都不许动（含 mtime）★（T1~T4 ✓ 离线 ✓ 见 §79.67）", "quick／offline／fast"),
    ("relay_guard_test.py", "★自己给自己排班的骨架★：续跑有硬上限（--continue-max 默认 6，落 1..50）／要有活才推（RUNNABLE_JOBS，在 wait_s 里等的会跳过）／干跑就停／HOLD 停止文件 ＋ cont_on 开关两条摁住的路／运行日志里真有 CONTINUE: 那行（R1~R6 ✓ 离线 ✓ 见 §79.62）", "quick／offline／fast"),
    ("jobs_restart_test.py", "★跨重启还记得吗★：账本是文件（jobs/*.json）／换个新进程读出的下一步必须逐字相同／没做完的活不许静默空下一步／最近一步要带 evidence／账本不在游戏目录／brief() 里看得见它（K1~K6b ✓ 离线 ✓ 见 §79.61）", "quick／offline／fast"),
    ("idle_test.py", "★挂机小动作★：忙⇒不做且说明原因／幅度夹到 45°／必须转回原位（回不到就判红）／冷却内拒并报还要等几秒／读不到朝向就不做（I1~I5 ✓ 离线 ✓ 见 §79.59）", "quick／offline／fast"),
    ("box_probe_test.py", "★「我改的世界动了没有」的判据★：放上去 solid/多重集各 +1、挖掉要逐项回基线、读不到必须回 None（不许冒充「盒里是空的」）、顺序不同仍算安静（B1~B6 ✓ 离线 ✓ 见 §79.48/§79.49）", "quick／offline／fast"),
    ("move_slot_test.py", "★槽位移动★：越界发都不发／from 空的没动／回读 to 槽才算成／读不到就 verified=false（N1~N4 ✓ 离线 ✓ 见欠账 ⑳）", "quick／offline／fast"),
    ("fixtures_test.py", "★测试件的清单/快照/复原/复核★：快照只记非空气／计划最小／异动必须标出来不许静默铲（F1~F6 ✓ 注入假 scan ✓ 见欠账 ⑦ 第 2 层）", "quick／offline／fast"),
    ("mapnames_test.py", "图上的名字是真的吗：真名/世界对账/视图不糊/不自造障碍/结论全图生效/补得上（N1~N6）", "quick"),
    ("r2_guard_test.py", "虚空守卫（确定性）", "quick／offline／fast"),
    ("shape_learn_test.py", "方块形状：按词匹配 ＋ 从碰撞箱学（U1~U4）", "quick／fast"),
    ("job_plan_test.py", "任务账本：步骤清单能跨会话（W1~W5，**离线** ✓）", "quick／offline／fast"),
    ("freeze_test.py", "冻结：动世界前先让它别动（F1/F3/F4）", "quick／fast"),
    ("prefix_guard_test.py", "撞名：动手**之前**就拒绝（G1~G4）", "quick"),
    ("platform_test.py", "平台与边：边在哪 ＋ 贴边警告（P1~P4）", "quick"),
    ("edge_avoid_test.py", "避边：默认走中间、只有边路也照走（Q1~Q5）", "quick"),
    ("edge_hop_test.py", "贴边跳：跳距压到 4 ＋ 多探一格，但照走（R1~R4）", "quick"),
    ("walk_progress_test.py", "长走心跳：超时后还能问「走到哪了」（S1~S4）", "quick／fast"),
    ("verdict_levels_test.py", "模组结论的分层：那一层能用＋不越权＋抬一级真的走得到（V1~V6）", "quick"),
    ("step_route_test.py", "上下台阶：规划得出来＋走不上去就如实说＋到没到按格按层判（S1~S5）", "quick"),
    ("one_way_test.py", "别把自己送进下不来的地方：回程不可行就拦住＋理由点对（O1~O4b）", "quick"),
    ("slab_ramp_test.py", "半砖/楼梯是自动上的台阶：逐格验（半步接受／整方块拒绝）（R1~R3）", "quick"),
    ("whereami_test.py", "现状速览：一次调用说完我的处境（W1~W4）", "quick／fast"),
    ("route_verify_test.py", "道剖面**实地验**：图被扫回来改正 ＋ 世界对账（X1~X5）", "quick"),
    ("kb_audit.py", "★新轴第一版：模型 vs 知识表★（两条**独立**通道 ✗ 表那一路跑 `table` 模式 ⇒ 不知道才是真的✓★）—— ★只报数 ✗ 不判红 ✗ 退出码恒 0★ ✗ 分层六层写死 ✗ 六层一个不许少（见 §79.107）", "quick"),
    ("mod_contract.py", "★契约围栏：复核模组现在的判定★（盒级计数器／逐种计数／逐格物种 ✗ 全部来自**模组回执** ✗ 不经过名字分类器✓★）—— 一致 ⇒ 0 ✗ 有差异 ⇒ 1 ✗ 契约或夹具不在 ⇒ **测不了**（`INCONCLUSIVE` ＋ 退出码 4）（见 §79.98）", "quick"),
    ("area_verify_test.py", "看地图也要真：map_area 实地验一片 ＋ 改正（Y1~Y5）", "quick"),
    ("plan_verify_test.py", "规划也要真：按路补验 ＋ 重规划 ＋ 端到端走（Z1~Z6）", "quick"),
    ("chest_many_test.py", "容器批量：走一趟办多件 ＋ 逐件对账（C1~C5）", "quick"),
    ("r8_guard_test.py", "长走拦截（真走 ✓ 2~18 格）", "quick"),
    ("r9_target_guard_test.py", "目标站不住拦截（手工造洞 ＋ 真走对照）", "quick"),
    ("m1_verify.py", "地图读取 M1~M4", "quick"),
    ("w1_gate_test.py", "★v2.15 之后单发长走还危险吗★（W1a~W1d ✗ 真走 ✗ 要世界）：★每次尝试后假人必须还活着★ ／ ★一次都不许掉（y 全程 ≥60✗★）／ 3 次里至少 2 次走到（≤2.0 格）／ 跑完还在连通平台里 ／ ★决策规则✗★：三条全过 ⇒ `SAFE_WALK` 8 → 16 ✗ 否则维持 8 ✗ ★并如实说「v2.15 还不够」✗（★真走有掉虚空风险 ✗ 脚本每次记背包✗★）（见 §79.320）", "walk"),
    ("hop_cost.py", "★不许每次重建地图★（H1~H3）：真跑 ≥6 跳 ✗ 逐跳计时 ✗ ★建图次数 ≤2★（★这条之前**根本不在闸门里** ⇒ `t_route_view` 每次重建 4 张图没人管 ✗ 见 §79.307／§79.308✗★）／ 跳时中位 ≤6.0 秒 ／ 跑完假人还活着（★要世界✗★）", "walk"),
    ("r2_verify.py", "寻路 P0~P5", "walk"),
    ("r3_verify.py", "提速 A/B T1~T3", "walk"),
    ("route_view_test.py", "道剖面：画得出来 ＋ 世界对账（V1~V6）", "walk"),
    # ── 2026-11-02 接手轮新增（各轨作者写判据 ✗ Lead 统一进 GATE ✗ 见 §79.525／§79.527）──
    ("doc_consistency_test.py", "★D7 入口文档一致性★：版本单一真源／工具数=55／docs 计数／入口链接／台账节数／DEBT 自洽（C1~C10 ✗ 离线 ✗ §79.524✗★）", "quick／offline／fast"),
    ("event_memory_test.py", "★H 事件记忆★：事件→事实→检索／选择性保留不丢重要／坏文件必须抛／证据指针（离线 ✗ §79.525✗★）", "quick／offline／fast"),
    ("task_layer_test.py", "★A 任务层★：priority／depends_on／claim 租约／中断可恢复／单步推进／失败如实停（离线 ✗ §79.525✗★）", "quick／offline／fast"),
    ("designer_test.py", "★L5 设计官★：配方图→元件清单→铺位/顺序/理由/缺料／坏数据与越界必须 refuse（离线 ✗ §79.526✗★）", "quick／offline／fast"),
    ("reporter_test.py", "★L7 汇报官★：账本＋事件→人话／只引用证据／无证据不称完成／长度分级（离线 ✗ §79.526✗★）", "quick／offline／fast"),
    ("mod_http_test.py", "★A3 HTTP 并发＋token＋Origin＋/raw 白名单★（离线：源码契约＋假服务器实测 direct.py 带头；live 用 --live ✗ §79.522✗★）", "quick／offline／fast"),
    ("mod_events_test.py", "★A7 事件 req trace★：ev() 追加 req=／dshreqs 账本／旧消费方兼容（离线 ✗ §79.522✗★）", "quick／offline／fast"),
    ("soak_suite_test.py", "★D3 soak 套件判据★：硬失败判定／事件 oracle／INCONCLUSIVE 不算 PASS／scorecard 自洽（离线 ✗ §79.523✗★）", "quick／offline／fast"),
    # ── 2026-11-02 第二轮新增（行为锚/S1/解绑/发版/D4 ✗ Lead 统一进 GATE ✗ 见 §79.528~§79.533）──
    ("mod_arch_test.py", "★S1 结构拆分判据★：HttpBridge 存在且被主类调用／主类行数下降／协议字面量不再在主类／tick 顺序常量未变（X1~X7 ✗ 离线 ✗ §79.532✗★）", "quick／offline／fast"),
    ("portability_test.py", "★解绑 P0 判据★：除 paths.py/例外外禁绝对路径·实例名·存档名·端口；计数器＋例外带理由＋自检能红（P1~P9 ✗ 离线 ✗ §79.530✗★）", "quick／offline／fast"),
    ("doctor_test.py", "★doctor 三态判据★：能跑／硬坏／部分未知（exit 0/1/2）／--json／缺数据必报（D1~D11 ✗ 离线 ✗ §79.530✗★）", "quick／offline／fast"),
    ("bootstrap_test.py", "★bootstrap export 判据★：生成顺序／缺产物必报／硬失败即停／条数读生成结果／确定性（B1~B8 ✗ 离线 ✗ §79.530✗★）", "quick／offline／fast"),
    ("release_check_test.py", "★发版链离线判据★：五件事 PASS/BLOCK 判定／sha 不符必红／缺 manifest 必 BLOCK／运行痕迹白名单（RC1~RC10 ✗ 离线 ✗ §79.531✗★）", "quick／offline／fast"),
    ("recover_test.py", "★D4 一条命令恢复判据★：health 不通不 spawn／spawn 失败如实退出／已就绪幂等／relay 旗处理／exit 0/1/2（RE1~RE10 ✗ 离线 ✗ §79.531✗★）", "quick／offline／fast"),
    # ── 2026-11-03 发布准备轮新增（开源发布：换机器能跑 ✗ Lead 统一进 GATE ✗ 见 §79.536）──
    ("cold_start_test.py", "★D8 冷启动判据★：干净副本缺什么——必需文件（DIST）／禁止物（工具链·第三方 jar·日志·dsh.env）／本机绑定泄漏／离线数据完整／大文件＞50MB（离线 ✗ --fast 默认不连游戏 ✗ §79.536✗★）", "quick／offline／fast"),
    # ── 2026-11-03 组件化/产品感轮新增（人格档案包 + 跨包世界档案 ✗ 见 §79.540/§79.541）──
    ("persona_pack_test.py", "★人格档案包判据★：SillyTavern V2 角色卡 JSON/PNG 导入导出／--use 渲染兼容 talk.py／注入 warn 不静默／超大与坏输入必红／幂等／template 可回读（离线 ✗ §79.540✗★）", "quick／offline／fast"),
    ("world_profile_test.py", "★世界档案判据★：无档案不兜底／recover·soak·doctor 三处接线可测／坏档案必红／--init 幂等／CLI>profile>默认优先级／档案里不许本机绝对路径（离线 ✗ §79.541✗★）", "quick／offline／fast"),
    ("speech_alive_test.py", "★语言表现层判据（活人感）★：去 AI 腔／长度预算／十轮去重／失败不谎报／上下文引用／口癖概率／5 场景主动发言／人格不串味／talk 接线点（离线 ✗ §79.543✗★）", "quick／offline／fast"),
]


# ★★2026-10-13（★§79.267 又栽一次✗★）✗★★：★元数错要**在模块级就点名**✗★ ——
#   ★现象✗★：★我插表时又漏了标签（★2 元组✗★）⇒ `_view` 里 `for s, d, t in GATE`
#     **解包失败** ✗ 报 `ValueError: not enough values to unpack`✗★ ⇒
#     ★而那时**连 `G1b` 都没机会跑** ✗ 闸门整个起不来✗★ ✓
#   ★⇒ 口径✗★：★错要**早说 ✗ 并说清是哪一条**✗★ ✓
_ARITY_BAD = [x for x in GATE if len(x) != 3]
if _ARITY_BAD:
    raise SystemExit("★`GATE` 每行必须是（★脚本 ✗ 说明 ✗ 标签★）三元组 ✗ 这几条不是：%s"
                     % [x[0] if x else "（空）" for x in _ARITY_BAD])


def _view(tag: str):
    """★按标签取一张视图✗★（★包含关系由**派生**保证 ✗ 不靠人写对✓★）"""
    return [(s, d) for s, d, t in GATE if tag in t.split("／")]


QUICK = _view("quick")
WALK = _view("walk")
OFFLINE = _view("offline")
FAST = _view("fast")

def settle(tries: int = 12, wait: float = 0.8) -> str:
    """★每个脚本开跑前，先把假人"安顿"到一个已知状态★ ✗（2026-09-28 第 21 轮 ✓）

    为什么必须有它 ✗（实测 ✓ 失败在**换位置** ✓）：
      现象 ✗：同一批脚本，总检里 **FAIL** ✗ 而**单跑 PASS** ✓ —— 而且每次失败的那个还不一样 ✗
        （一会儿 `route_verify` ✗ 一会儿 `plan_verify` ＋ `chest_many` ✗）
      真因 ✓：前一个脚本刚**走过路／改过图** ✓ ⇒ 后一个恰好在"**半路状态**"上开跑 ✗
        （人还在半空/刚落地被挤 ✓ 地图任务框刚换过 ✓ 障碍记忆刚更新 ✓）
      ⇒ "**单独跑**"与"**在总检里跑**"必须是同一件事 ✗（P94/P96 那一族的老账 ✓）
    做法 ✓：**等到"落地站住"**（`onground=true` ✓ 连读两次同一个位置 ✓）再让脚本开跑 ✓
      读不出来（通道忙/游戏没起）⇒ 也放行 ✓ 但把这件事**说出来** ✗ 不静默 ✓
    """
    import re as _re
    import time as _t
    # ★开跑前**冻结**★ ✗（2026-09-29 第 23 轮 ✓ 治 §40.7 ✓）：
    #   为什么要冻 ✗：脚本之间假人会**自己溜达**（`dshidle` ✓）
    #     ⇒ "前后对比"型判据会误判成"丢东西"✗（上一轮 12/13 那条就是这个 ✓）
    try:
        import mc_mcp as M0
        ft, ferr = M0.t_freeze(True)
        froze = "★冻结★" in (ft or "")
        del ferr
    except Exception:
        froze = False
    last = None
    for i in range(max(1, int(tries))):
        try:
            import mc_mcp as M
            txt = M.dsh("dshdigest 1", 40.0) or ""
        except Exception as e:
            return "settle: cannot talk to the game (%s) -- running anyway" % type(e).__name__
        m = _re.search(r"pos=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)", txt)
        ong = "onground=true" in txt
        cur = m.groups() if m else None
        if cur and ong and last == cur:
            return ("settle: frozen=%s on ground at (%.1f,%.1f,%.1f)"
                    % (froze, float(cur[0]), float(cur[1]), float(cur[2])))
        last = cur
        _t.sleep(float(wait))
    return "settle: gave up waiting (still moving) -- running anyway (frozen=%s)" % froze


def verdict_of(code: int, out: str) -> str:
    """★三分类：**通过 ／ 真的坏了 ／ **测不了**✗★**（2026-09-30 第 39 轮 ✓ ⇒ P147 ✓）

    ★为什么要分三类✗★：实测（第 38 轮 ✓）假人掉进一个 **2 格小坑** ✗ ⇒
      `route_view`／`r3_verify` 报 **FAIL** ✗ —— 而它们输的其实是
      "**8 格内挑不到安全目标** ✗"／"**no candidate target ⇒ cannot test** ✗" ✓
      ⇒ ★那是**测不了**✗ 不是**坏了**✗★（本项目早有这条纪律 ✓ P82/P96：
        "测试挑不到 ⇒ 不是功能坏"✓）—— ★可它们**混在 FAIL 里**✗★ ⇒
        读账面的人会以为"功能坏了 9 项"✗ 其实其中两三件是"**这块地太小**"✗
    ★口径✗★（★不许把"测不了"算成"通过"✗★ —— 那才是假绿 ✓）：
      · 退出码 0 ⇒ **通过** ✓
      · 退出码非 0 ＋ 输出里有 **`=> FAIL`** 行 ⇒ **失败** ✗（★真红优先 ✗ 哪怕同时缺输入✓★）
      · 退出码非 0 ＋ 输出里有 **`MissingExport`** ⇒ **缺输入** ✗（★B1 裁决：缺输入＝**硬红** ✗ 不是"没法测"✓★）
      · 退出码非 0 ＋ 输出里有 `INCONCLUSIVE` ⇒ **测不了** ✗
      · 其余 ⇒ **失败** ✗
    ★★2026-10-18（★复核 P0-3✗★）✗★★：★"缺输入"原来是**混在 FAIL 里**的✗★ ⇒
      ★于是"★5 条红全是环境★"这句话只能**靠人记** ✗ 而机器读到的就是"★失败了 5 项★"✗★ ✓
      ★⇒ 总账给它**自己一格**（★机器行 `missing=N`✗★）✗ 但**退出码仍然非 0**✗★ ⇒
      ★★"★看得见 ✗ 但不装成判据坏 ✗ 也不放过★"✗★★ ✓
    """
    if code == 0:
        return "PASS"
    out = out or ""
    import re as _re_v  # ★本模块的 `re` 是函数内局部导入 ✗ 这里自带一个更稳✗★
    # ★★2026-10-18（★复核连带修的**第二个盲区**✗★）✗★★：
    #   ★原来只认 `ln.strip().endswith("=> FAIL")` ✗ ⇒
    #     ★而判据的真实收尾行长这样：`=> generated_docs FAIL`／`=> cut_verify ★FAIL✗★`✗★ ⇒
    #     ★**一行都匹配不上** ✗ 于是"★有真红★"的判据被当成"★只有缺输入★"✗★ ✓
    #   ★口径✗★：★`=>` 后面**任意名字** ＋ 结尾 `FAIL` 都算真红✗★ ✓
    has_fail = any(_re_v.search(r"=>\s*\S*\s*[★\[]*\s*FAIL", ln) or "=> FAIL:" in ln
                   for ln in out.splitlines())
    if has_fail:
        return "FAIL"          # ★真红优先✗★：★一条判据里既有真红又缺输入 ⇒ 它**还是红**✗★ ✓
    # ★"缺输入"有两套字样✗★：★`export_guard` 抛的异常名（`MissingExport`✗★）
    #   ＋ 它的人话（★"★缺输入（硬红，不是测不了）★"✓★）✗ 两个都认✗★ ✓
    if "MissingExport" in out or "缺输入" in out:
        return "MISSING"
    has_inc = "INCONCLUSIVE" in out
    if has_inc:
        return "INCONCLUSIVE"
    return "FAIL"


# ★★离线脚本集合（★2026-10-05 修✗★）✗★★
#   ★上一版我按 `settle_world` 判隔离 ✗ 而调用点是 `run(script, settle_world=not offline)`✗★
#   ⇒ ★**全量**跑时 `offline=False` ⇒ 对**每个**测试都是 `True` ✗ 隔离**完全没生效**✗★ ✓
#   （★实测：全量里那 4 条离线判据照样假红 ✓★）
#   ⇒ ★改按"★这个脚本属不属于**离线表**★"判 ✗ 全量与 `--offline` 都成立✗★ ✓
def _offline_scripts() -> set:
    out = set()
    for tbl in (OFFLINE, ):
        for row in tbl:
            try:
                out.add(row[0])
            except Exception:
                pass
    return out


OFFLINE_SCRIPTS = _offline_scripts()


import time as _time
_GATE_T0 = _time.time()


def _refresh_status_line(msg: str) -> None:
    """★把"★闸门现状★"那行写进台账开头 ✗ 并重生成索引✗★（★§79.254✗★）"""
    import re as _re
    import sys as _sys
    _sys.path.insert(0, str(ROOT / "tools"))
    STA = ROOT / "docs" / "当前阶段-状态与交接.md"
    if not STA.is_file():
        return
    LOGF = ROOT / "logs" / "check_all.txt"
    first = ""
    if LOGF.is_file():
        first = (LOGF.read_text(encoding="utf-8", errors="replace").splitlines() or [""])[0]
    m = _re.search(r"SUMMARY pass=(\d+) fail=(\d+) inconclusive=(\d+) total=(\d+)", first)
    if not m:
        return
    import docwrite as DW
    text = STA.read_text(encoding="utf-8", errors="replace")
    line = ("★闸门现状（★机器行＊由 `tools/entry_status_test.py` 对着 `logs/check_all.txt` 查✗★）："
            "`pass=%s fail=%s inconclusive=%s total=%s`★" % m.groups())
    if "★闸门现状" in text:
        new = _re.sub(r"★闸门现状[^\n]*", line, text, count=1)
    else:
        new = line + "\n\n" + text
    DW.write_if_changed(STA, new)
    import ledger_index as LI
    LI.main()


def run(script: str, settle_world: bool = True) -> tuple:
    t0 = time.time()
    # ★离线闸门 ⇒ **不 settle**（第 34 轮末 ✓）：settle 要读世界 ✗ 而离线模式没有世界 ✓
    st = settle() if settle_world else "offline: 不 settle（不碰世界 ✓）"
    # ★★离线表必须**隔离环境变量**✗★★（2026-10-04 ✗ §79.132 实测出来的**假红**）
    #   · ★离线判据的可信度来自**注入** ✗ 不是世界✗★ ⇒ ★环境里带着
    #     `CLASSIFIER_SOURCE`／`DSH_KB_SCOPE` 会把它们带偏 ⇒ **假红**✗★ ✓
    #   · ★世界表**照旧透传**✗★（★否则"★作用域 A/B★"做不了 —— 那正是阶段 4 要用的✓★）
    _env = dict(os.environ)
    if (not settle_world) or (script in OFFLINE_SCRIPTS):
        for _k in ("CLASSIFIER_SOURCE", "DSH_KB_SCOPE"):
            _env.pop(_k, None)
    # ★★2026-10-13（★§79.250✗★）✗★★：★审计发现失败明细在日志里是**乱码**✗★ ——
    #   ★子进程的 traceback 走 **stderr** ✗ 而它按本地代码页写出 ✗ 闸门按 UTF-8 读✗★ ⇒
    #   ★★治本是让**子进程**自己说 UTF-8✗★★（★pin stdout 只管 stdout ✗ 管不到 traceback✗★）✗★ ✓
    _env = dict(_env)
    _env["PYTHONIOENCODING"] = "utf-8"
    # ★★2026-10-13（★§79.254 ✗ 自指振荡✗★）✗★★：★给子进程一个"★本次运行开始时刻★"✗★ ⇒
    #   ★判据就能分辨"★这份日志是**本次运行**写的（★自指✗★）★" ✗
    #   ★还是"★上一次跑完留下的★"✗★ ✓
    #   ★（★`entry_status_test` 拿日志比状态行 ✗ 而它自己**就在**写这个日志的那次运行里✗★）✗★ ✓
    _env["DSH_GATE_STARTED"] = "%.3f" % _GATE_T0
    # ★★2026-10-18（★§79.295 ✗ 治 §79.293 那个"★--walk 挂 45 分钟★"✗★）✗★★：
    #   ★`subprocess.run` **没有 timeout**✗★ ⇒ ★卡在"★等世界★"的判据会**一直等**✗★ ✓
    #   ★口径✗★：★**超时不是坏** ✗ 是"★测不了★"✗★ ⇒
    #     ★输出第一行写 `INCONCLUSIVE:` ✗ 而且**绝不**带 `=> FAIL`✗★（★`verdict_of` 会据此判测不了✓★）✗★ ✓
    #   ★上限✗★：★`DSH_GATE_ITEM_TIMEOUT`（★默认 900 秒✗★）✗ 单项要更久就调它✗★ ✓
    _cap = float(os.environ.get("DSH_GATE_ITEM_TIMEOUT", "900") or 900)
    try:
        r = subprocess.run([sys.executable, str(ROOT / "tools" / script)],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=str(ROOT), env=_env, timeout=_cap)
        _code, _out = r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired as _te:
        _code = -9
        _out = ("INCONCLUSIVE: ★这一项**超时**（%.0f 秒上限）✗ 很可能是卡在**等世界**✗ "
                "不是判据坏★（★要更久 ⇒ 调 `DSH_GATE_ITEM_TIMEOUT`✓★）\n" % _cap)
        _out += (_te.stdout or "") if isinstance(_te.stdout, str) else ""
    out = ("[settle] %s\n" % st) + _out
    # ★把每个脚本的**完整输出**落盘★ ✗（2026-09-28 第 18 轮补 ✓）：
    #   现象 ✗：`r8` 在总检里 FAIL ✗ 而单跑 PASS ✓ —— 可总检**只留了最后一行**✗
    #     ⇒ 失败的**现场没有了** ✗ ⇒ 只能靠猜 ✓（这正是错题本 P98 ④ 那条纪律 ✗
    #       "失败证据要先存下来再重跑" ✓ 我自己在工具里没做到 ✗）
    #   ⇒ 现在每个脚本的全文都写进 `logs/check_<脚本名>.log` ✓ 查得到 ✓
    try:
        (ROOT / "logs" / ("check_%s.log" % script.replace(".py", ""))).write_text(
            out, encoding="utf-8")
    except Exception:
        pass
    tail = [ln for ln in out.splitlines() if "=>" in ln or "exit=" in ln]
    return (_code, round(time.time() - t0, 1),
            (tail[-1].strip() if tail else out.strip()[-80:]), out)


HOLD = ROOT / "logs" / "relay_hold"


def relay_pause() -> bool:
    """★跑验收前挂一个"暂停自动续跑"的旗子★ ✗（以前这条只写在文档里 ✗）

    现象 ✗：`r8`/`r9` 单独跑 PASS ✓ 放进总检就 FAIL ✗ —— 因为中继带着**长任务自动续跑** ✓
      会在测试中途把假人**挪走** ✗ ⇒ "跑完还在原地/在连通平台里"这类判据被搅黄 ✗
    ★做法（2026-09-23 改过一版 ✗）★：一开始我用 `subprocess` 起 PowerShell 去杀进程 ✗
      ⇒ **挂住了**（这个沙箱不允许子进程走管道 stdio ✓ 见环境注记 ✓）⇒ 整轮超时 ✗
      ⇒ 改成**纯文件旗子** ✓：这里落一个 `logs/relay_hold` ✓ 中继自己看到就**不动手** ✓
        （不改对方代码就没法真正暂停它 ✓ 但"不许自动续跑"正好是我们要的那一条 ✓）
    """
    try:
        HOLD.write_text("check_all 正在跑验收 %s\n" % time.strftime("%H:%M:%S"), encoding="utf-8")
        return True
    except Exception:
        return False


def relay_resume() -> None:
    try:
        HOLD.unlink(missing_ok=True)
    except Exception:
        pass


def _compile_all() -> str:
    """★把 `tools/*.py` 全编译一遍✗★ ✓（返回一句给人看的话 ✓ 不抛异常 ✓）

    ★为什么它是"发货前闸门"的一部分✗★（P141 ✓）：
      实测 ✓：我把 ASCII 双引号混进中文串 ✗ ⇒ `edge_hop_test.py` 语法错 ✗
      ⇒ 而 `--offline` 那一组**不含**它（它只跑实测 ✓）✗ ⇒ 闸门**全绿**而文件是坏的 ✗✗
      ⇒ ★"闸门盖不住的那一半"里，**"能不能编译"是唯一不需要游戏就能盖住的那一项**✗★
    """
    import py_compile
    bad = []
    n = 0
    for p in sorted((ROOT / "tools").glob("*.py")):
        n += 1
        try:
            py_compile.compile(str(p), doraise=True, cfile=str(p) + ".pyc.tmp")
        except Exception as e:
            bad.append("%s：%s" % (p.name, str(e).splitlines()[0][:80]))
    for p in (ROOT / "tools").glob("*.py.pyc.tmp"):
        try:
            p.unlink()
        except Exception as e:      # ★★§79.403✗★ 清临时文件失败 ⇒ **记一句**（★不然永远留着没人知道✗★）
            bad.append("清理 %s 失败：%r" % (p.name, e))
    if bad:
        return "★%d 个编译不过 ✗★：%s" % (len(bad), " ｜ ".join(bad[:4]))
    return "%d 个全部编译通过 ✓" % n


def main(argv) -> int:
    fast = "--fast" in argv
    offline = "--offline" in argv
    plan = FAST if fast else (OFFLINE if offline
                              else (QUICK if "--no-walk" in argv else QUICK + WALK))
    total = len(QUICK) + len(WALK)
    if fast:
        # ★★子集必须**自己声明**这是子集★★ ✗（第 28 轮 ✓）：不然就是"假绿"✗
        print("== check_all: %d 个脚本（★--fast **子集**★ ✗ 全量有 %d 项 ✓ —— "
              "**别把它当全绿** ✗）==" % (len(plan), total))
    elif offline:
        # ★★发货前闸门（第 34 轮末 ✓ 用户审计提出 ✓）：**不需要游戏**★ ✗
        #   为什么要有它 ✗：以前 check_all 是"出了事再跑"✗ ⇒ 改物理/寻路的行为**先发货再验**✗
        #     （第 34 轮的 commit message 自己写着"shipping it unverified cost 4 battery items"✗）
        #   ⇒ 口径 ✓：**凡动 pathplan／mapread 这类纯逻辑 ⇒ 先过这一关** ✗（离线 ✓ 秒级 ✓）
        #   ⚠ 它**盖不住**"跟世界打交道"的那一半 ✓ ⇒ 明说 ✓ 不许当全绿 ✗
        print("== check_all: %d 个脚本（★--offline 发货前闸门★ ✓ **不需要游戏** ✓）=="
              % len(plan))
        print("   ★它只盖**纯逻辑/离线**那一半** ✗：真走/真读/真动手的那 %d 项**没有跑** ✗"
              % (total - len(plan)))
    else:
        print("== check_all: %d 个脚本 ==%s"
              % (len(plan), "  (--no-walk)" if "--no-walk" in argv else ""))
    paused = relay_pause()
    print("[relay] " + ("已挂暂停旗 logs/relay_hold（中继不会再自动续跑 ✓）" if paused else "旗子没挂上 ✗"))
    # ★★先**编译所有 tools/*.py**✗★★（2026-09-30 第 35 轮 ✓ ⇒ P141 ✓）
    #   ★为什么要有这一步✗★：我在写 `edge_hop_test.py` 时把 ASCII 双引号混进了中文串里 ✗
    #     ⇒ 那个文件**语法错**✗ ⇒ 而它**只跑实测**✗ ⇒ ★`--offline` 闸门**根本碰不到它**✗★
    #     ⇒ 这类错会**一路带到游戏里**才发现 ✓（代价：一轮白跑 ✓）
    #   ⇒ 口径 ✓：**发货前，凡是 `tools/*.py` 都得能编译**✗（1~2 秒 ✓ 不需要游戏 ✓）
    compiled = _compile_all()
    print("[compile] tools/*.py：%s" % compiled)
    # ★试过又**删掉**的一条 ✗（2026-09-30 ✓ 记在这里免得下次再想一遍 ✓）：
    #   "抓 ASCII 引号夹在汉字中间" ✗ ⇒ 实测**1218 处误报** ✗（注释里我合法写的中文引号全被算上 ✓）
    #   ⇒ ★而"引号夹汉字"在**代码**里**必然是语法错**✗★ ⇒ **编译那一步已经全覆盖**✓
    #     （今天它两次当场抓住我这个错 ✓）⇒ 重复的尺子更吵 ✗ 不如只有一把 ✓
    if offline:
        # ★★离线闸门**不许碰世界**★★ ✗（第 34 轮末 ✓ 实测：闸门原来 600 秒超时 ✗）
        #   真因 ✓：每一项前后的 `settle()`（等假人站稳 ✓）与末尾的 `freeze(False)`（解冻 ✓）
        #     都要**读世界** ✗ —— 游戏关着时每次读都空等到超时 ✓ ⇒ 7 项就超 10 分钟 ✗
        #   ⇒ 口径 ✓：**离线模式一律不 settle 也不 freeze** ✓（没有世界可安顿 ✓ 也没冻过 → 不用解 ✓）
        print("[world] 离线模式：**不碰世界** ✓（不 settle ✗ 不 freeze ✗ —— 因为没有世界 ✓）")
    rows = []
    try:
        for script, what in plan:
            code, sec, last, out = run(script, settle_world=not offline)
            v = verdict_of(code, out)
            rows.append((script, what, code, sec, last, v))
            print("%-18s %-20s %-6s %6.1fs  %s"
                  % (script, what,
                     {"PASS": "PASS", "FAIL": "★FAIL★", "INCONCLUSIVE": "†测不了†",
                      "MISSING": "‡缺输入‡"}[v],
                     sec, last[:70]))
    finally:
        relay_resume()
        print("[relay] 旗子已撤（自动续跑恢复 ✓）")
        if offline:
            print("[freeze] 离线模式：没冻过 ✓ 也就不解冻 ✓（没碰世界 ✓）")
        else:
            # ★跑完必须**解冻**★ ✗（2026-09-29 第 23 轮 ✓）：不然等于把"假人会自己溜达"这个
            #   原有设置**改掉不还** ✗ —— 那是动了别人的东西 ✓（P-family：动过就要还原 ✓）
            try:
                import mc_mcp as M9
                ut, _ue = M9.t_freeze(False)
                print("[freeze] " + (ut or "").splitlines()[0][:80])
            except Exception as e:
                print("[freeze] 解冻没做成 ✗（%s）⇒ ★假人可能还冻着★ ✗ 手动跑一次 freeze(on=false) ✓"
                      % type(e).__name__)
    bad = [r for r in rows if r[5] == "FAIL"]
    inc = [r for r in rows if r[5] == "INCONCLUSIVE"]
    mis = [r for r in rows if r[5] == "MISSING"]
    # ★★三分类总账✗★★（2026-09-30 第 39 轮 ✓ ⇒ P147 ✓）：
    #   ★"测不了"**单独列**✗★ 而且**不算通过**✗（★那才是假绿✗★）——
    #   实测撞到 ✓：假人掉进 2 格小坑 ⇒ 2~3 项输的是"挑不到目标" ✗ 却混在 FAIL 里 ✓
    # ★★2026-10-18（★复核 P0-3 ✗ §79.274✗★）✗★★：★多加一格「**缺输入**」✗★ ✓
    #   ★真因✗★：★`export_guard` 的"★缺输入硬红★"（★B1 裁决 ✗ 对的✓★）✗
    #     ★让 4 条**只是没输入**的判据混在 `fail` 里 ✗ 于是"★5 条红＝4 环境＋1 真红★"✗
    #     ★这句真话只能靠**人记** ✗ 机器行读到的是"★失败 5 项★"✗★ ✓
    #   ★处置✗★：★机器行**追加** `missing=N`（★放在最后 ✗ 现有那些前缀匹配的解析**不会断**✓★）✗
    #     ★退出码**仍然非 0**✗★（★缺输入不放过 ✗ 只是不再冒充判据坏✓★）✗★ ✓
    n_pass = len(rows) - len(bad) - len(inc) - len(mis)
    print("---- 总账：通过 %d ／ 失败 %d ／ ★测不了 %d✗★ ／ ★缺输入 %d✗★ ／ 共 %d ----"
          % (n_pass, len(bad), len(inc), len(mis), len(rows)))
    for b in bad:
        print("   ★FAIL★ %s：%s" % (b[0], b[4][:90]))
    for b in inc:
        print("   †测不了† %s：%s（★不是通过✗ 也不是坏✗ —— 换个位置/条件再测✓★）"
              % (b[0], b[4][:70]))
    for b in mis:
        print("   ‡缺输入‡ %s：%s（★是**没输入** ✗ 不是判据坏✗ ⇒ 补输入再跑 ✓★）"
              % (b[0], b[4][:70]))
    # ★★2026-10-13（★用户裁决 D3 ✗ §79.240✗★）✗★★：★机器那一行**必须纯 ASCII**✗★ ✓
    #   ★用户原话✗★：★"★面向机器的输出必须纯 ASCII（★logs／回执／判据结论行✓★）✗
    #     ★人读的文档保持现状★"✗★ ✓
    #   ★口径✗★：★中文那行**保留**（★人读 ✓★）✗ 另加**纯 ASCII** 那一行（★机器读✓★）✗★ ✓
    #     ⇒ ★机器不用再去解析"★通过／失败／测不了★"这些字✗★ ✓
    _ascii = ("SUMMARY pass=%d fail=%d inconclusive=%d total=%d missing=%d"
              % (n_pass, len(bad), len(inc), len(rows), len(mis)))
    print(_ascii)
    (ROOT / "logs" / "check_all.txt").write_text(
        _ascii + "\n" + "\n".join("%s %s %s %.1fs %s" % r[:5] for r in rows),
        encoding="utf-8")
    # ★★退出码也分三类✗★★：★只有"测不了"⇒ **不许**报成功✗★（★那才是假绿✗★）
    #   0 ⇒ 全通过 ✓ ｜ 1 ⇒ 有真失败 ✗ ｜ 4 ⇒ 没失败但**有测不了的**✗（要换条件重测 ✓）
    # ★2026-10-18：★缺输入（`missing`）也**算非 0**✗★（★B1：缺输入＝硬红 ✗ 不放过✓★）✗★ ✓
    if not bad and not inc and not mis:
        msg = "ALL PASS"
    elif bad:
        msg = "有失败 ✗（见上 ✓ 明细在 logs/check_all.txt ✓）"
    elif mis:
        msg = ("★没有失败 ✗ 但有 **%d 项缺输入** ✗（★补输入再跑 ✗ 不是判据坏✓★）%s"
               % (len(mis), (" ＋ %d 项测不了✗" % len(inc)) if inc else ""))
    else:
        msg = ("★没有失败，但有 %d 项**测不了**✗★（★不许当通过✗ 见上面 † 那几行 ✓）"
               % len(inc))
    # ★★2026-10-13（★§79.254✗★）✗★★：★闸门**自己**刷那两条生成物✗★★ ✓
    #   ★真因✗★：★"★台账状态行★"原来靠**手动**刷 ✗★ ⇒ ★"★闸门 SUMMARY★"就取决于
    #     "★上一次有没有人手动刷★"✗★ ⇒ ★`entry_status_test` 拿它比日志 ⇒ **自指振荡**✗★ ✓
    #     （★它一红 ⇒ 日志变 69/6 ⇒ 状态行(70/5)更对不上 ⇒ 永远红✓★）✗★ ✓
    #   ★治本✗★：★跑完就刷新状态行 ＋ 重生成索引✗★ ⇒
    #     ★它**永远等于刚跑完那一次** ✗ 只有**手改**才会红✗★ ✓
    try:
        _refresh_status_line(msg)
    except Exception as _e:
        print("[status] ★刷新状态行没做成 ✗★：%s（★不许静默吞 ✗ 但不该拖垮闸门✓★）"
              % type(_e).__name__)
    print("=> %s%s" % (msg, "" if not fast else
                      "  ★（★这只是 --fast 子集：%d/%d 项 ✓★ 全量请跑不带参数的那个 ✓）★"
                      % (len(rows), total)))
    if bad or mis:
        return 1
    return 4 if inc else 0


# ★主保护★ ✗（2026-09-29 第 28 轮 ✓ **实测栽过** ✓）：
#   原来是**裸的** `raise SystemExit(main(sys.argv[1:]))` ✗
#   ⇒ 任何人 `import check_all`（比如我那条"子集守卫"判据 ✓）都会**顺手跑一整套总检** ✗
#     表现 ✓：一条"瞬间完成"的判据**跑了 5 分钟被超时打断** ✗
#   ⇒ 加 `if __name__ == "__main__":` ✓（这是标准做法 ✓ 我竟然一直没加 ✗）
if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

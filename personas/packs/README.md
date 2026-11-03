# personas/packs/ —— 人格档案包（角色卡）目录

- `examples/`：**随仓库分发的示例卡**（可直接试）：
  - `dafeiyu.json` / `laokuang.json` / `guanjia.json`：SillyTavern **V2 角色卡** JSON；
  - `dafeiyu.png`：同内容的 **PNG 角色卡**（图片里嵌 `chara` 文本块 = base64 JSON）。
- 本目录根：**你导入的卡**（`py tools/persona_pack.py --import …` 生成）。
  - `<id>.json`：规范化后的 V2 卡（本项目读写用；`--list/--show/--use/--export` 认它）；
  - `<id>.raw.json`：导入时的**原文保留**（排错/对照用）。
- 切人设：`py tools/persona_pack.py --use <id>` ⇒ 渲染成 `personas/current.md`
  （`talk.py` 每轮重读 ⇒ **下一轮就生效**，不用重启）。
- 说明文档：仓库根 `PERSONA-CARDS.md`。

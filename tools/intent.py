#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""intent.py -- 模块 L1 对话官的**意图判别**：这句话要不要动手？

用户原话（规格 §10.3）：
  「**dsh 需要至少两个智能体**，一个负责对话、另一个负责执行；
   **对话的需要判断哪些需要去执行 ✗ 哪些是聊天**」
  「发言可以仅开始和结束」＋「chat 不能让延迟太高」⇒ ★判别必须**纯本地** ✗ 0 次往返✗★

四类（★判据 L-a/L-b/L-e 用的就是这四类✗★）：
  chat  纯聊天            ⇒ 直接回 ⇒ **绝不触发任何世界动作**
  query 问状态/问世界     ⇒ 读感知层缓存作答 ⇒ **也不动世界**
  task  要执行            ⇒ 落 `jobs/` 交执行侧
  mixed 先聊后做          ⇒ 拆成 "chat 回一句 ＋ 一条 task"

★本模块只做判别 ✗ 不执行任何命令** ⇒ 天然满足"chat 零往返"**✗★
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ── 词表（★宁可宽 ✗ 不可漏：漏掉"要执行"的话最危险✗★）─────────────────────
TASK_VERBS = (
    # 移动
    "去", "过来", "回去", "回来", "回到", "走", "跑到", "走到", "前往", "带我去", "跟上",
    # 破坏/建造
    "挖", "采", "砍", "拆", "放置", "放一个", "放个", "搭", "建", "盖", "铺", "填",
    # 交互
    "取", "拿", "存", "放进", "装进", "打开", "关上", "关掉", "开一下", "按", "踩",
    "用一下", "右键", "交易", "给", "递给", "扔", "丢",
    # 生产
    "种", "收", "浇", "合成", "做一", "制作", "烤", "烧", "炼", "修",
    # 战斗
    "杀", "打它", "打那个", "攻击", "赶走",
    # 通用祈使
    "帮我", "替我", "麻烦你", "去把", "去给", "帮我看看", "帮我找",
)

QUERY_PATTERNS = (
    "你在哪", "你在干什么", "你在做什么", "你现在", "背包", "手里拿", "血", "饿",
    "几点", "什么时间", "附近有", "周围有", "这里有什么", "有几个", "多少",
    "是什么", "这是哪", "能不能看到", "看到什么",
)

CHAT_PATTERNS = (
    "你好", "您好", "hi", "hello", "嗨", "哈喽", "在吗", "早上好", "晚上好", "晚安",
    "谢谢", "多谢", "辛苦", "厉害", "哈哈", "笑死", "真棒", "不错", "好久不见",
    "你累不累", "你累吗", "你喜欢", "你觉得", "你是谁", "你叫什么", "你多大了",
    "无聊", "聊聊", "说说", "讲个", "好吧", "行吧", "嗯", "明白了",
)

# ★"先聊后做"的连接词✗★：出现它 ＋ 两侧都有内容 ⇒ mixed
MIX_CONNECTORS = ("顺便", "然后", "再", "接着", "之后", "另外", "并且", "同时")


def _hits(text: str, words) -> list:
    t = (text or "").lower()
    return [w for w in words if w.lower() in t]


def classify(text: str) -> dict:
    """★一句话 ⇒ `{"intent","need_exec","chat_part","task_part","why"}`✗★

    ★判别顺序（★很要紧✗★）✗★：
      ① 有**执行动词** ⇒ 至少是 task（★哪怕同时有寒暄✗★）
      ② 同时有**寒暄/问句** ⇒ **mixed**（★拆两段✗★）
      ③ 没有执行动词但有**问状态** ⇒ query
      ④ 都没有 ⇒ chat（★默认是聊天 ✗ 宁可不动手✗★）
    """
    t = (text or "").strip()
    if not t:
        return {"intent": "chat", "need_exec": False, "chat_part": "", "task_part": "",
                "why": "空话 ✗ 当聊天"}
    task_hits = _hits(t, TASK_VERBS)
    query_hits = _hits(t, QUERY_PATTERNS)
    chat_hits = _hits(t, CHAT_PATTERNS)
    conn_hits = _hits(t, MIX_CONNECTORS)

    # ★问句里的"在哪/有什么"是 query ✗ 不是 task（★但"去把X关掉"是 task✗★）
    is_question = t.endswith("?") or t.endswith("？") or any(
        k in t for k in ("吗", "呢", "哪", "什么", "多少", "几"))

    if task_hits:
        # 寒暄 ＋ 执行 ⇒ mixed（★仅当寒暄出现在执行动词之前 ✗ 那是"先聊后做"✗★）
        if chat_hits or (query_hits and is_question):
            first_task = min(t.find(h) for h in task_hits)
            first_chat = min((t.find(h) for h in chat_hits), default=len(t) + 1)
            first_query = min((t.find(h) for h in query_hits), default=len(t) + 1)
            if min(first_chat, first_query) < first_task or conn_hits:
                return {"intent": "mixed", "need_exec": True,
                        "chat_part": t[:first_task].strip(" ，,。、"),
                        "task_part": t[first_task:].strip(" ，,。、"),
                        "why": "寒暄在前 ＋ 执行动词：%s" % ",".join(task_hits[:3])}
        return {"intent": "task", "need_exec": True, "chat_part": "",
                "task_part": t,
                "why": "执行动词：%s" % ",".join(task_hits[:3])}

    # ★显式寒暄**优先于**"是疑问句"✗★（★"在吗"/"你叫什么"/"你觉得…吗"都是聊天✗★）
    if chat_hits and not query_hits:
        return {"intent": "chat", "need_exec": False, "chat_part": t, "task_part": "",
                "why": "寒暄（带问号但没问状态）：%s" % ",".join(chat_hits[:3])}
    if query_hits or is_question:
        return {"intent": "query", "need_exec": False, "chat_part": t, "task_part": "",
                "why": "问状态：%s" % (",".join(query_hits[:3]) or "疑问句")}

    return {"intent": "chat", "need_exec": False, "chat_part": t, "task_part": "",
            "why": "寒暄／闲聊：%s" % (",".join(chat_hits[:3]) or "无执行动词")}


def main(argv) -> int:
    if argv:
        r = classify(" ".join(argv))
        print("INTENT intent=%s need_exec=%s why=%s"
              % (r["intent"], r["need_exec"], r["why"]))
        if r["intent"] == "mixed":
            print("  chat_part: %s" % r["chat_part"])
            print("  task_part: %s" % r["task_part"])
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

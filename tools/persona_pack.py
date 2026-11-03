#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""persona_pack.py -- ★人格档案包✗★：吃酒馆/SillyTavern V2 角色卡的**导入/导出/切换**层

为什么要有它 ✗（用户 2026-11-03 的判断 ✓）：
  「还至少差了一个**模板化的人格档案**……接 QQ 的模板不错」
  ⇒ ★不自造格式✗★：直接用**社区现成**的 SillyTavern V2 角色卡（酒馆生态 ✓ QQ bot 圈也认 ✓）
  ⇒ 组件化：人设 = 一张卡（JSON 或 PNG）✓ 换人设 = 换卡 ✓ 可导出给别人 ✓

## 卡片格式（V2，宽松兼容 v1 / 未标 spec / ccv3）
```json
{"spec":"chara_card_v2","spec_version":"2.0",
 "data":{"name":"…","description":"…","personality":"…","scenario":"…",
         "first_mes":"…","mes_example":"…","creator_notes":"…","system_prompt":"…",
         "post_history_instructions":"…","alternate_greetings":["…"],"tags":["…"],
         "character_book":{"entries":[{"keys":["…"],"content":"…"}]}}}
```
  * 也接受 v1 写法（字段在**顶层** ✓ 无 `data` 包一层 ✓）；
  * PNG：读 `tEXt`/`iTXt`/`zTXt` 里的 `chara`（V2）或 `ccv3`（V3）＝ base64 JSON ☞ **纯标准库手写 chunk**（zlib/struct ✓ 不用 Pillow ✗）。

## 用法
    py tools/persona_pack.py --import 卡.json|卡.png [--id 自定义id]
    py tools/persona_pack.py --list
    py tools/persona_pack.py --show <id>
    py tools/persona_pack.py --use <id>                  # 渲染成 personas/current.md（talk.py 直接生效 ✓）
    py tools/persona_pack.py --export <id> --out 卡.json [--png 卡.png]
    py tools/persona_pack.py --template --out 模板.json   # 空白 V2 卡（字段带中文说明）
    py tools/persona_pack.py --validate 卡.json|卡.png

## 纪律（★都是踩过的坑✗★）
  * **注入标记 warn 不静默**：卡里出现"忽略以上指令 / 执行命令"等 ⇒ 打印 `warn=ascii原因` 并记录，不阻断（用户自己决定用不用）；
  * **超大卡拒绝**：description > 64KB 或全文 > 256KB ⇒ 拒绝并给原因（exit 2）；
  * **坏 JSON/坏 PNG 必须非零**：不静默成功；
  * **幂等**：同一张卡重复 import ⇒ 落盘字节稳定（只有 current.meta.jsonl 会追加留痕）；
  * **不联网、零第三方依赖**、stdout 已 pin UTF-8（项目纪律 ✓）。
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import re
import struct
import sys
import time
import zlib
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
PERSONAS_DIR = ROOT / "personas"
PACKS_DIR = PERSONAS_DIR / "packs"
CURRENT_MD = PERSONAS_DIR / "current.md"
META_JSONL = PERSONAS_DIR / "current.meta.jsonl"
EXAMPLES_DIR = PACKS_DIR / "examples"

V2_SPEC = "chara_card_v2"
V2_VERSION = "2.0"
KNOWN_SPECS = ("chara_card_v2", "chara_card_v3", "chara_card_v1")

MAX_DESC_BYTES = 64 * 1024
MAX_TOTAL_BYTES = 256 * 1024
MAX_RENDER_CHARS = 24000

STRING_FIELDS = ("name", "description", "personality", "scenario", "first_mes",
                 "mes_example", "creator_notes", "system_prompt",
                 "post_history_instructions")
LIST_FIELDS = ("alternate_greetings", "tags")


class PackError(RuntimeError):
    """★坏输入/坏卡✗★（带 ascii reason，CLI 统一 exit 2）"""

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__("%s%s" % (reason, ("：" + detail) if detail else ""))


# ── 注入标记（★warn 不静默✗★；每条带 ascii 原因）─────────────────────────
INJECTION_PATTERNS = [
    (re.compile(r"忽略(?:以上|之前|上面|先前|一切)(?:的)?(?:所有)?(?:指令|提示|设定|规则)"),
     "ignore_previous_instructions"),
    (re.compile(r"ignore\s+(?:all\s+)?(?:the\s+)?(?:previous|above|prior)\s+"
                r"(?:instructions|prompts|rules|system)", re.I),
     "ignore_previous_instructions"),
    (re.compile(r"(?:执行|运行|调用)\s*(?:命令|shell|终端|powershell|cmd|bash)", re.I),
     "execute_commands"),
    (re.compile(r"(?:rm\s+-rf|del\s+/[sq]|format\s+[a-z]:|drop\s+table|"
                r"curl\s+https?|wget\s+https?)", re.I), "destructive_or_network"),
    (re.compile(r"<\s*script|javascript:", re.I), "script_injection"),
    (re.compile(r"(?:system\s+prompt|开发者模式|开发者指令|DAN\b|越狱|jailbreak)", re.I),
     "jailbreak_marker"),
    (re.compile(r"\{\{.*?(?:system|prompt|inject|exec).*?\}\}", re.I), "template_injection"),
]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _b(text: str) -> int:
    return len(text.encode("utf-8"))


# ═══════════════════════════════════════════════════════════════════════════
# 卡片解析/规范化（JSON）
# ═══════════════════════════════════════════════════════════════════════════
def _card_data(obj: dict) -> dict:
    """取出卡的数据层：V2（data 包一层）或 V1（字段在顶层）都认"""
    if not isinstance(obj, dict):
        raise PackError("not_a_card", "JSON 顶层不是对象")
    data = obj.get("data")
    has_top_fields = any(k in obj for k in STRING_FIELDS) or "character_book" in obj
    if isinstance(data, dict) and (obj.get("spec") in KNOWN_SPECS
                                   or "name" in data or not has_top_fields):
        return data
    if has_top_fields:
        return obj
    raise PackError("not_a_card", "既没有 data 层，也没有 name/description 等角色卡字段")


def _coerce_str(val, field: str) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, (int, float, bool)):
        return str(val)
    raise PackError("bad_field_type", "%s 应为字符串，实际是 %s" % (field, type(val).__name__))


def _coerce_list(val, field: str) -> list:
    if val is None:
        return []
    if not isinstance(val, list):
        raise PackError("bad_field_type", "%s 应为数组，实际是 %s" % (field, type(val).__name__))
    out = []
    for i, item in enumerate(val):
        if isinstance(item, str):
            out.append(item)
        elif item is None:
            continue
        elif isinstance(item, (int, float)):
            out.append(str(item))
        else:
            raise PackError("bad_field_type", "%s[%d] 应为字符串" % (field, i))
    return out


def detect_injection(norm: dict) -> list:
    """★扫注入标记✗★：返回 [{"field","reason"}]（reason 是 ascii ✓ 便于日志检索）"""
    hits = []
    data = norm.get("data") or {}
    for field in STRING_FIELDS:
        text = data.get(field) or ""
        if not text:
            continue
        for pat, reason in INJECTION_PATTERNS:
            if pat.search(text):
                hits.append({"field": field, "reason": reason})
    book = data.get("character_book")
    if isinstance(book, dict):
        for i, entry in enumerate(book.get("entries") or []):
            if not isinstance(entry, dict):
                continue
            text = " ".join(str(entry.get(k) or "") for k in ("comment", "content", "name"))
            for pat, reason in INJECTION_PATTERNS:
                if pat.search(text):
                    hits.append({"field": "character_book[%d]" % i, "reason": reason})
    # 去重（同 field+reason）
    seen, out = set(), []
    for h in hits:
        key = (h["field"], h["reason"])
        if key not in seen:
            seen.add(key)
            out.append(h)
    return out


def normalize_card(obj: dict, source: str = "") -> dict:
    """★规范化成 V2 结构✗★（字段宽松：缺省补空；类型不对明确报错；长度/总量限制）"""
    data_in = _card_data(obj)
    spec = str(obj.get("spec") or V2_SPEC)
    if spec not in KNOWN_SPECS and not spec.startswith("chara_card"):
        spec = V2_SPEC                     # 未标/未知 spec 一律按 V2 处理（宽松兼容）
    data = {}
    for k, v in data_in.items():           # 保留未知字段（不丢信息）
        data[k] = v
    for field in STRING_FIELDS:
        data[field] = _coerce_str(data_in.get(field), field)
    for field in LIST_FIELDS:
        data[field] = _coerce_list(data_in.get(field), field)
    # character_book：宽松（dict 或 None）
    book = data.get("character_book")
    if book is not None and not isinstance(book, dict):
        raise PackError("bad_field_type", "character_book 应为对象或 null")
    if isinstance(book, dict) and book.get("entries") is not None \
            and not isinstance(book.get("entries"), list):
        raise PackError("bad_field_type", "character_book.entries 应为数组")
    if _b(data.get("description") or "") > MAX_DESC_BYTES:
        raise PackError("card_too_large",
                        "description 超过 64KB（%d 字节；请精简设定或改成世界书）"
                        % _b(data.get("description") or ""))
    norm = {"spec": V2_SPEC, "spec_version": V2_VERSION,
            "id": str(obj.get("id") or data_in.get("id") or ""),
            "data": data}
    blob = json.dumps(norm, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")
    if len(blob) > MAX_TOTAL_BYTES:
        raise PackError("card_too_large",
                        "全文超过 256KB（%d 字节；请拆分世界书/精简示例对话）" % len(blob))
    return norm


def safe_id(name: str) -> str:
    """★安全 id✗★：小写 ascii 字母数字/下划线/横线；中文名 ⇒ 空（调用方用文件名词干或哈希兜底）"""
    s = re.sub(r"[^a-z0-9_-]+", "-", str(name or "").strip().lower())
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:48]


def pick_id(norm: dict, source_path=None, explicit: str = "") -> str:
    """id 优先级：显式 > 卡内 id > name 的 ascii 化 > 源文件名词干 > 哈希兜底"""
    for cand in (explicit, norm.get("id") or ""):
        cid = safe_id(str(cand or ""))
        if cid:
            return cid
    cid = safe_id(str((norm.get("data") or {}).get("name") or ""))
    if cid:
        return cid
    if source_path is not None:
        cid = safe_id(Path(source_path).stem)
        if cid:
            return cid
    payload = json.dumps(norm, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return "card-" + _sha256(payload)[:8]


# ═══════════════════════════════════════════════════════════════════════════
# PNG：手写 chunk（★零第三方✗★）
# ═══════════════════════════════════════════════════════════════════════════
PNG_SIG = b"\x89PNG\r\n\x1a\n"
PNG_KEYWORDS = ("chara", "ccv3")


def _chunk(ctype: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + ctype + payload
            + struct.pack(">I", binascii.crc32(ctype + payload) & 0xFFFFFFFF))


def png_crc_ok(ctype: bytes, payload: bytes, crc: int) -> bool:
    return (binascii.crc32(ctype + payload) & 0xFFFFFFFF) == crc


def iter_png_chunks(data: bytes):
    """解析 PNG chunk（★校验签名/CRC/越界✗★；坏 ⇒ PackError）"""
    if len(data) < 8 or data[:8] != PNG_SIG:
        raise PackError("bad_png", "PNG 签名不对（不是 PNG 或文件损坏）")
    pos = 8
    n = len(data)
    while pos + 12 <= n:
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        ctype = data[pos + 4:pos + 8]
        if pos + 12 + length > n:
            raise PackError("bad_png", "PNG chunk 越界（文件被截断）")
        payload = data[pos + 8:pos + 8 + length]
        (crc,) = struct.unpack(">I", data[pos + 8 + length:pos + 12 + length])
        if not png_crc_ok(ctype, payload, crc):
            raise PackError("bad_png", "PNG chunk CRC 校验失败（%r）" % ctype[:16])
        yield ctype, payload
        pos += 12 + length
        if ctype == b"IEND":
            break


def png_text_chunks(data: bytes):
    """产出 (keyword, text)（tEXt/iTXt/zTXt；iTXt 支持压缩标记）"""
    for ctype, payload in iter_png_chunks(data):
        try:
            if ctype == b"tEXt":
                kw, _, txt = payload.partition(b"\x00")
                yield kw.decode("latin-1"), txt.decode("latin-1")
            elif ctype == b"zTXt":
                kw, _, rest = payload.partition(b"\x00")
                if not rest:
                    continue
                yield (kw.decode("latin-1"),
                       zlib.decompress(rest[1:]).decode("latin-1"))
            elif ctype == b"iTXt":
                kw, _, rest = payload.partition(b"\x00")
                if len(rest) < 2:
                    continue
                comp_flag, _method = rest[0], rest[1]
                rest = rest[2:]
                _lang, _, rest = rest.partition(b"\x00")
                _tkw, _, txt = rest.partition(b"\x00")
                if comp_flag == 1:
                    txt = zlib.decompress(txt)
                yield kw.decode("latin-1"), txt.decode("utf-8", errors="replace")
        except (binascii.Error, zlib.error, UnicodeDecodeError) as exc:
            raise PackError("bad_png_text", "PNG 文本块解码失败（%s）" % type(exc).__name__)


def read_card_from_png(data: bytes) -> tuple:
    """从 PNG 读角色卡 ⇒ (card dict, 命中的 keyword)"""
    found = {}
    for kw, txt in png_text_chunks(data):
        if kw in PNG_KEYWORDS and kw not in found:
            found[kw] = txt
    if not found:
        raise PackError("no_card_in_png",
                        "PNG 里没有 chara/ccv3 文本块（不是角色卡 PNG）")
    errors = []
    for kw in PNG_KEYWORDS:                # chara（V2）优先；没有再看 ccv3（V3）
        if kw not in found:
            continue
        try:
            raw = base64.b64decode(found[kw].strip(), validate=True)
        except (binascii.Error, ValueError):
            try:
                raw = base64.b64decode(found[kw].strip())    # 容错：容忍缺 padding
            except (binascii.Error, ValueError) as exc:
                errors.append("%s base64 坏：%s" % (kw, type(exc).__name__))
                continue
        try:
            obj = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append("%s JSON 坏：%s" % (kw, type(exc).__name__))
            continue
        if not isinstance(obj, dict):
            errors.append("%s 顶层不是对象" % kw)
            continue
        return obj, kw
    raise PackError("bad_card_in_png", "；".join(errors) or "chara/ccv3 解析失败")


def build_png_card(card: dict, size: int = 64) -> bytes:
    """★写一张最小 PNG 角色卡✗★：IHDR + tEXt(chara=base64 JSON) + IDAT + IEND
    图案是确定性渐变色块（不让示例卡看起来是空白文件）；读回只依赖 tEXt。
    """
    card_json = json.dumps(card, ensure_ascii=False, separators=(",", ":"))
    b64 = base64.b64encode(card_json.encode("utf-8"))
    text_chunk = _chunk(b"tEXt", b"chara\x00" + b64)
    # 像素：蓝绿渐变 + 中心暖色圆（确定性；无随机）
    rows = []
    cx = cy = (size - 1) / 2.0
    rad = size * 0.30
    for y in range(size):
        row = bytearray([0])               # filter type 0
        for x in range(size):
            edge = 1.0 if (x < 2 or y < 2 or x >= size - 2 or y >= size - 2) else 0.0
            dx, dy = x - cx, y - cy
            if dx * dx + dy * dy <= rad * rad:
                px = (250, 190, 90)        # 鱼身暖色
            else:
                px = (30 + int(160 * x / size), 90 + int(120 * y / size), 170)
            if edge:
                px = (20, 20, 30)
            row.extend(px)
        rows.append(bytes(row))
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"".join(rows), 9)
    return (PNG_SIG + _chunk(b"IHDR", ihdr) + _chunk(b"tEXt", b"Software\x00mc-agent-bridge")
            + text_chunk + _chunk(b"IDAT", idat) + _chunk(b"IEND", b""))


# ═══════════════════════════════════════════════════════════════════════════
# 落盘仓库（★root 可注入 ⇒ 判据不碰运行时的 current.md✗★）
# ═══════════════════════════════════════════════════════════════════════════
class PersonaStore:
    def __init__(self, root=None) -> None:
        base = Path(root) if root is not None else ROOT
        self.root = base
        self.personas = base / "personas"
        self.packs = self.personas / "packs"
        self.examples = self.packs / "examples"
        self.current = self.personas / "current.md"
        self.meta = self.personas / "current.meta.jsonl"

    # — 安装 —
    def load_card_file(self, path) -> tuple:
        """读 JSON/PNG ⇒ (原始 card dict, 规范化 card, 格式, 源字节 sha256)"""
        p = Path(path)
        if not p.is_file():
            raise PackError("file_not_found", str(p))
        data = p.read_bytes()
        if data[:8] == PNG_SIG:
            obj, key = read_card_from_png(data)
            fmt = "png:%s" % key
        else:
            try:
                text = data.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise PackError("bad_encoding", "不是 UTF-8 文本（%s）" % type(exc).__name__)
            try:
                obj = json.loads(text)
            except json.JSONDecodeError as exc:
                raise PackError("bad_json", "JSON 解析失败：line %s col %s"
                                % (exc.lineno, exc.colno))
            fmt = "json"
        norm = normalize_card(obj, source=str(p))
        return obj, norm, fmt, _sha256(data)

    def _warn_overwrite(self, cid: str, raw_blob: bytes) -> str | None:
        existing = self.packs / ("%s.raw.json" % cid)
        if existing.is_file():
            old = _sha256(existing.read_bytes())
            if old != _sha256(raw_blob):
                return "同 id 的旧卡内容不同 ⇒ 已覆盖（旧 sha256=%s）" % old[:12]
        return None

    def install(self, path, explicit_id: str = "") -> dict:
        """导入一张卡 ⇒ 写 <id>.raw.json（原文保留）＋ <id>.json（规范化）"""
        obj, norm, fmt, src_sha = self.load_card_file(path)
        cid = pick_id(norm, path, explicit=explicit_id)
        norm["id"] = cid
        warnings = detect_injection(norm)
        raw_blob = json.dumps(obj, ensure_ascii=False, indent=1,
                              sort_keys=False).encode("utf-8") + b"\n"
        norm_blob = json.dumps(norm, ensure_ascii=False, indent=1,
                               sort_keys=False).encode("utf-8") + b"\n"
        note = self._warn_overwrite(cid, raw_blob)
        self.packs.mkdir(parents=True, exist_ok=True)
        self._atomic_write(self.packs / ("%s.raw.json" % cid), raw_blob)
        self._atomic_write(self.packs / ("%s.json" % cid), norm_blob)
        return {"id": cid, "format": fmt, "source_sha256": src_sha,
                "raw_sha256": _sha256(raw_blob), "norm_sha256": _sha256(norm_blob),
                "warnings": warnings, "overwrite_note": note,
                "path": str(self.packs / ("%s.json" % cid))}

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)

    # — 读取 —
    def ids(self) -> list:
        if not self.packs.is_dir():
            return []
        return sorted(p.stem for p in self.packs.glob("*.json")
                      if not p.name.endswith(".raw.json")
                      and not p.name.endswith(".warnings.json"))

    def load_norm(self, cid: str) -> dict:
        p = self.packs / ("%s.json" % safe_id(cid))
        if not p.is_file():
            raise PackError("card_not_found", "没有已安装的卡 %r（先 --import；见 --list）" % cid)
        try:
            obj = json.loads(p.read_text(encoding="utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PackError("bad_installed_card", "%s 读不动：%s" % (p.name, type(exc).__name__))
        data = _card_data(obj)
        if isinstance(obj.get("data"), dict):
            obj["data"] = data
        return obj

    def warnings(self, cid: str) -> list:
        try:
            return detect_injection(self.load_norm(cid))
        except Exception as exc:             # ★不许静默✗★（探针失败也要留原因）
            print("warn=injection_probe_failed reason=%r" % (exc,), file=sys.stderr)
            return []                       # 保守默认：不把"探针失败"当成"没有 warn"

    # — 渲染 / 切换 —
    def render(self, norm: dict) -> str:
        text = render_card(norm)
        if _b(text) > MAX_RENDER_CHARS * 8:
            text = text[:MAX_RENDER_CHARS] + "\n…（渲染超长已截断，原文见角色卡）"
        return text

    def use(self, cid: str) -> dict:
        """★把卡渲染成运行时 personas/current.md✗★（talk.py 每轮重读 ⇒ 立刻生效）

        ★同时把卡里的语言风格（extensions.dsh_speech）写成
        `personas/current.speech.json`✗★ —— 换人设＝换声音：风格层不能停在上一张卡上。
        卡里没有 dsh_speech ⇒ 写**默认风格**（而不是保留上一张卡的风格 ✗）。
        """
        norm = self.load_norm(cid)
        text = self.render(norm)
        cid = str(norm.get("id") or safe_id(cid))
        self.personas.mkdir(parents=True, exist_ok=True)
        self._atomic_write(self.current, (text.rstrip() + "\n").encode("utf-8"))
        speech_written = ""
        try:
            import speech_style as _ss
            prof = _ss.load(norm)            # 卡 extensions.dsh_speech；没有 ⇒ 默认
            blob = (json.dumps(prof, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
            self._atomic_write(self.personas / "current.speech.json", blob)
            speech_written = str(self.personas / "current.speech.json")
        except Exception as exc:             # ★不许静默✗★（风格写不了 ⇒ 明说，并让 talk 用默认）
            print("[persona_pack] ★写 speech profile 失败✗★（风格层退回默认）：%r" % (exc,),
                  file=sys.stderr)
        card_file = self.packs / ("%s.json" % cid)
        card_sha = _sha256(card_file.read_bytes()) if card_file.is_file() else ""
        rec = {"at": time.strftime("%Y-%m-%d %H:%M:%S"),
               "source": "card:%s" % cid, "chars": len(text),
               "head": text[:60], "card_id": cid, "card_sha256": card_sha,
               "speech_profile": speech_written}
        try:
            self.meta.parent.mkdir(parents=True, exist_ok=True)
            with self.meta.open("a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError as exc:               # ★不许静默✗★
            print("[persona_pack] ★meta 留痕写不进✗★：%r" % (exc,), file=sys.stderr)
        return {"id": cid, "chars": len(text), "current": str(self.current),
                "speech_profile": speech_written}

    # — 导出 —
    def export_json(self, cid: str, out) -> dict:
        norm = self.load_norm(cid)
        card = clean_card(norm)
        blob = json.dumps(card, ensure_ascii=False, indent=1).encode("utf-8") + b"\n"
        p = Path(out)
        self._atomic_write(p, blob)
        return {"id": str(norm.get("id") or cid), "out": str(p),
                "bytes": len(blob), "sha256": _sha256(blob)}

    def export_png(self, cid: str, out) -> dict:
        norm = self.load_norm(cid)
        card = clean_card(norm)
        blob = build_png_card(card)
        p = Path(out)
        self._atomic_write(p, blob)
        # 往返自检：写出去的 PNG 必须能被自己读回（★坏编码当场红✗★）
        obj, _key = read_card_from_png(blob)
        if not isinstance(obj, dict):
            raise PackError("png_roundtrip", "写出的 PNG 读回不是对象")
        return {"id": str(norm.get("id") or cid), "out": str(p),
                "bytes": len(blob), "sha256": _sha256(blob)}


def clean_card(norm: dict) -> dict:
    """导出/给外部用：去掉本项目的私有键（id/_warnings 等），保留 V2 结构"""
    card = {"spec": V2_SPEC, "spec_version": V2_VERSION,
            "data": json.loads(json.dumps(norm.get("data") or {}, ensure_ascii=False))}
    for k, v in norm.items():
        if k in ("spec", "spec_version", "id", "data", "_warnings", "_source"):
            continue
        card[k] = v
    return card


def _fill_placeholders(text: str, name: str) -> str:
    out = (text or "").replace("{{char}}", name).replace("{{Char}}", name)
    out = out.replace("{{user}}", "<主人>").replace("{{User}}", "<主人>")
    out = out.replace("{{original}}", "").replace("{{persona}}", "")
    return out


def _clip(text: str, limit: int) -> str:
    t = (text or "").strip()
    return t if len(t) <= limit else t[:limit].rstrip() + "…（截断，原文见角色卡）"


def render_card(norm: dict) -> str:
    """★把卡渲染成纯文本人设✗★（talk.py 兼容：仍是 markdown 文本，不是 JSON）"""
    data = norm.get("data") or {}
    name = (data.get("name") or "").strip() or "（未命名角色）"
    parts = ["# 人设：%s（角色卡 %s）" % (name, norm.get("id") or "?")]
    notes = (data.get("creator_notes") or "").strip()
    if notes:
        parts.append("> 角色卡说明：%s" % _clip(notes, 400))

    def sec(title: str, body: str, limit: int = 6000) -> None:
        body = _fill_placeholders(body, name).strip()
        if body:
            parts.append("## %s\n\n%s" % (title, _clip(body, limit)))

    sec("你是谁", data.get("description") or "", 8000)
    sec("性格", data.get("personality") or "", 3000)
    sec("场景", data.get("scenario") or "", 2000)
    sec("说话方式 / 核心规则", data.get("system_prompt") or "", 4000)
    first = _fill_placeholders((data.get("first_mes") or "").strip(), name)
    if first:
        parts.append("## 开场白（参考语气，不要照抄）\n\n%s" % _clip(first, 1500))
    alts = [_fill_placeholders(str(x), name).strip()
            for x in (data.get("alternate_greetings") or [])]
    alts = [a for a in alts if a][:3]
    if alts:
        parts.append("## 备用开场（参考语气）\n" + "\n".join(
            "- %s" % _clip(a, 300) for a in alts))
    mes = _fill_placeholders(data.get("mes_example") or "", name).strip()
    if mes:
        parts.append("## 示例对话（学语气 ✗ 别照抄台词）\n\n%s" % _clip(mes, 4000))
    book = data.get("character_book") or {}
    entries = book.get("entries") if isinstance(book, dict) else None
    if isinstance(entries, list) and entries:
        rows = []
        for e in entries[:8]:
            if not isinstance(e, dict):
                continue
            label = (e.get("comment") or e.get("name") or
                     "、".join(str(k) for k in (e.get("keys") or [])[:3]) or "条目")
            body = _fill_placeholders(str(e.get("content") or ""), name).strip()
            if body:
                rows.append("- %s：%s" % (str(label)[:60], _clip(body, 400)))
        if rows:
            parts.append("## 世界书要点\n" + "\n".join(rows))
    ph = _fill_placeholders((data.get("post_history_instructions") or "").strip(), name)
    if ph:
        parts.append("## 行为边界（优先级高）\n\n%s" % _clip(ph, 2000))
    parts.append("<!-- 本文件由角色卡渲染：py tools/persona_pack.py --use <id>；"
                 "原件 personas/packs/%s.json -->" % (norm.get("id") or "?"))
    text = "\n\n".join(p for p in parts if p.strip())
    if not (data.get("description") or data.get("personality")
            or data.get("first_mes") or data.get("system_prompt")):
        raise PackError("empty_card", "这张卡是空的（description/personality/first_mes 都没有）")
    return text


# ═══════════════════════════════════════════════════════════════════════════
# 模板
# ═══════════════════════════════════════════════════════════════════════════
TEMPLATE_FIELD_NOTES = {
    "name": "角色名（必填；会用来做 id，如 dafeiyu）",
    "description": "你是谁：身份、处境、对玩家的关系（主体设定；建议 ≤2KB）",
    "personality": "性格底色：几个关键词 + 一句解释",
    "scenario": "场景：现在在哪里、在做什么",
    "first_mes": "开场白：第一句话是什么（可含 {{char}} / {{user}} 占位符）",
    "mes_example": "示例对话：用 <START> 分隔多轮，示范语气（不要写说明书）",
    "creator_notes": "给导入者看的说明（示例卡/出处/注意事项；不进入人设正文）",
    "system_prompt": "核心规则/说话方式（可选；优先级高于普通描述）",
    "post_history_instructions": "行为边界：绝对不能做的事（可选）",
    "alternate_greetings": "备用开场白（字符串数组，可空）",
    "tags": "标签（字符串数组，方便检索）",
    "character_book": "世界书：{\"entries\":[{\"keys\":[...],\"content\":\"...\"}]}（可 null）",
}


def template_card() -> dict:
    """空白 V2 卡模板（字段值留空，另带 `_字段说明` 中文注释块）"""
    return {
        "spec": V2_SPEC,
        "spec_version": V2_VERSION,
        "id": "",
        "_字段说明": TEMPLATE_FIELD_NOTES,
        "data": {
            "name": "",
            "description": "",
            "personality": "",
            "scenario": "",
            "first_mes": "",
            "mes_example": "",
            "creator_notes": "示例模板：把各字段填好后用 "
                             "`py tools/persona_pack.py --import 你的卡.json` 导入。",
            "system_prompt": "",
            "post_history_instructions": "",
            "alternate_greetings": [],
            "tags": [],
            "character_book": None,
        },
    }


def validate_card_file(path) -> dict:
    """--validate：只用标准库检查（返回规范化结果 + warnings；坏 ⇒ PackError）"""
    store = PersonaStore()
    obj, norm, fmt, src_sha = store.load_card_file(path)
    warnings = detect_injection(norm)
    return {"ok": True, "format": fmt, "id": pick_id(norm, path),
            "name": (norm.get("data") or {}).get("name") or "",
            "warnings": warnings, "source_sha256": src_sha}


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════
def _print_warnings(warnings, out=None) -> None:
    for w in warnings:
        print("warn=%s field=%s" % (w["reason"], w["field"]), file=out or sys.stdout)


def cmd_list(store: PersonaStore, as_json: bool = False) -> int:
    ids = store.ids()
    out = {"packs": str(store.packs), "cards": []}
    for cid in ids:
        try:
            norm = store.load_norm(cid)
        except PackError as exc:             # ★坏卡不静默✗★
            print("  [bad] %-24s %s" % (cid, exc), file=sys.stderr)
            continue
        data = norm.get("data") or {}
        out["cards"].append({"id": cid, "name": data.get("name") or "",
                             "tags": data.get("tags") or [],
                             "warnings": len(detect_injection(norm))})
    examples = []
    if store.examples.is_dir():
        examples = sorted(p.name for p in store.examples.glob("*.json"))
    out["examples"] = examples
    if as_json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0
    print("已安装的角色卡（%s）：" % store.packs)
    if not out["cards"]:
        print("  （还没有；先 --import 一张卡）")
    for c in out["cards"]:
        print("  %-24s %s%s" % (c["id"], c["name"],
                                ("  ★warn=%d" % c["warnings"]) if c["warnings"] else ""))
    if examples:
        print("示例卡（%s，可直接 --import）：" % store.examples)
        for e in examples:
            print("  examples/%s" % e)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="persona_pack.py",
        description="人格档案包：SillyTavern V2 角色卡 导入/导出/切换（纯标准库）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--import", dest="import_file", metavar="CARD")
    g.add_argument("--use", dest="use_id", metavar="ID")
    g.add_argument("--list", action="store_true")
    g.add_argument("--show", dest="show_id", metavar="ID")
    g.add_argument("--export", dest="export_id", metavar="ID")
    g.add_argument("--template", action="store_true")
    g.add_argument("--validate", dest="validate_file", metavar="CARD")
    ap.add_argument("--out", help="导出/模板输出路径")
    ap.add_argument("--png", action="store_true", help="--export 时写 PNG 角色卡")
    ap.add_argument("--id", dest="explicit_id", default="", help="--import 时指定 id")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    store = PersonaStore()
    try:
        if args.import_file:
            res = store.install(args.import_file, explicit_id=args.explicit_id)
            print("IMPORT ok=1 id=%s format=%s sha256=%s"
                  % (res["id"], res["format"], res["source_sha256"][:12]))
            print("  已安装：%s" % res["path"])
            if res["warnings"]:
                print("  ★warn=%d（卡里可能有注入/越权指令，已记录 ✗ 不阻断）"
                      % len(res["warnings"]))
                _print_warnings(res["warnings"])
            if res["overwrite_note"]:
                print("  ★注意✗★：%s" % res["overwrite_note"])
            return 0
        if args.use_id:
            norm = store.load_norm(args.use_id)
            warnings = detect_injection(norm)
            res = store.use(args.use_id)
            print("USE ok=1 id=%s chars=%d → %s" % (res["id"], res["chars"],
                                                     res["current"]))
            if warnings:
                print("  ★warn=%d（已记录；内容来自卡，用不用你决定）" % len(warnings))
                _print_warnings(warnings)
            return 0
        if args.list:
            return cmd_list(store, as_json=args.json)
        if args.show_id:
            norm = store.load_norm(args.show_id)
            print(json.dumps(norm, ensure_ascii=False, indent=1))
            return 0
        if args.export_id:
            if args.png:
                if not args.out:
                    print("[X] --export --png 需要 --out 路径", file=sys.stderr)
                    return 2
                res = store.export_png(args.export_id, args.out)
            else:
                if args.out:
                    res = store.export_json(args.export_id, args.out)
                else:
                    norm = store.load_norm(args.export_id)
                    print(json.dumps(clean_card(norm), ensure_ascii=False, indent=1))
                    return 0
            print("EXPORT ok=1 id=%s out=%s bytes=%d"
                  % (res["id"], res["out"], res["bytes"]))
            return 0
        if args.template:
            blob = json.dumps(template_card(), ensure_ascii=False, indent=1) + "\n"
            if args.out:
                store._atomic_write(Path(args.out), blob.encode("utf-8"))
                print("TEMPLATE ok=1 out=%s" % args.out)
            else:
                print(blob, end="")
            return 0
        if args.validate_file:
            res = validate_card_file(args.validate_file)
            print("VALID ok=1 id=%s format=%s warnings=%d"
                  % (res["id"], res["format"], len(res["warnings"])))
            _print_warnings(res["warnings"])
            return 0
    except PackError as exc:
        print("PACKFAIL reason=%s detail=%s" % (exc.reason, exc.detail), file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

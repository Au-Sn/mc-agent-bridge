#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_action_schema.py -- build ``agent/action_schema.json`` from ``cc-tweaked/agent_bridge.lua``.

The Lua program is NEVER executed and never imported: this is a pure lexer + block
scanner over the source text.  It answers "what does the fake-player bridge accept?"
so the agent layer can validate/complete commands instead of guessing.

What it extracts
----------------
For every action registered in the dispatcher:

* the ``args.<name>`` parameter names the action body actually reads,
* the default value when one is written in the source (``or <literal>`` / ``~= false``),
* a best-effort scalar type (number | boolean | string | unknown),
* the long-running / cancellable markers found in the body (raw names),
* the source line of the definition,
* the doc/section comment sitting directly above the definition.

Dispatcher shape in this file (important)
-----------------------------------------
``agent_bridge.lua`` does NOT use an ``if action == "..."`` chain.  It builds a table::

    local A = {}
    A.status  = function()   ... end
    A.sleep   = function(args) local ms = tonumber(args and args.ms) or 500 ... end
    ...
    local fn = A[cmd]                     -- execute()

So an "action" is any ``A.<name> = function(...)`` assignment, plus the actions
generated dynamically by ``makeMove("forward", ...)`` (which all share the single
template body ``A[name] = function(args)``).  Both forms are handled below.

Argument aliasing (why a naive ``args\\.`` regex is not enough)
--------------------------------------------------------------
Only ~1/4 of the actions touch ``args`` directly.  Most alias it first::

    A.chop_tree = function(args)
      local a = args or {}          -- <- alias
      ...
      local r = math.floor(tonumber(a.radius) or 6)

The scanner therefore tracks scope: it knows ``a`` is bound to the ``args`` table
and that a later ``for _, p in ipairs(...)`` or ``function(a, b)`` parameter
*shadows* the name (so ``p.x`` / the inner ``a.id`` are correctly NOT args).

Usage
-----
    py tools/gen_action_schema.py            # write the JSON + print the summary
    py tools/gen_action_schema.py --json     # print the JSON to stdout
    py tools/gen_action_schema.py --check    # regenerate in memory, exit != 0 if stale
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BRIDGE_ROOT = os.path.dirname(HERE)                       # .../mc-agent-bridge
DEFAULT_LUA = os.path.join(BRIDGE_ROOT, "cc-tweaked", "agent_bridge.lua")
DEFAULT_OUT = os.path.join(BRIDGE_ROOT, "agent", "action_schema.json")
LUA_REL = "cc-tweaked/agent_bridge.lua"

# Markers that flag an action as long-running / cancellable.  These are recorded
# verbatim in the output so a human can judge; `task`/`cancel`/`interrupt`/
# `os.sleep` happen not to occur in the current revision of the file.
MARKERS = ("task", "budget", "jobNote", "cancel", "os.sleep", "EXIT_NOW", "interrupt")

# Subset that actually means "this action blocks for a while / is cancellable".
# EXIT_NOW is deliberately excluded: it marks a deliberate process *termination*
# (quit / shutdown / reboot), not a long-running job.
LONG_RUNNING_MARKERS = frozenset({"task", "budget", "jobNote", "cancel", "interrupt", "os.sleep"})

KEYWORDS = frozenset(
    """and break do else elseif end false for function goto if in local nil
       not or repeat return then true until while""".split()
)

LONG_OPEN = re.compile(r"\[(=*)\[")
NUMBER_RE = re.compile(r"0[xX][0-9a-fA-F]+|\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?")
OPS = ("...", "..", "==", "~=", "<=", ">=", "::", "//",
       "+", "-", "*", "/", "%", "^", "#", "<", ">", "=", "(", ")", "{", "}",
       "[", "]", ";", ":", ",", ".")

# statement-ish tokens that end a forward scan for a default value
FWD_STOP = frozenset({",", "then", "do", "end", "else", "elseif", ";;", ";", "=",
                      "if", "while", "for", "return", "local", "function", "until"})
# tokens that end a backward scan looking for `tonumber(`
BWD_STOP = frozenset({",", "=", ";", "do", "return", "{", "}", "or"})

MISSING = object()


class Tok:
    __slots__ = ("kind", "value", "line", "start", "end")

    def __init__(self, kind, value, line, start, end):
        self.kind = kind        # name | number | string | op | kw
        self.value = value
        self.line = line
        self.start = start
        self.end = end

    def __repr__(self):  # pragma: no cover - debug helper
        return "Tok(%s,%r,L%d)" % (self.kind, self.value, self.line)


# ---------------------------------------------------------------------------
# lexer
# ---------------------------------------------------------------------------
def tokenize(src):
    """Return (tokens, comments, masked_src).

    ``comments`` is a list of (start, end) character spans; ``masked_src`` is the
    source with every comment blanked out, so marker searches only ever hit code.
    """
    toks = []
    comments = []
    n = len(src)
    i = 0
    line = 1

    while i < n:
        c = src[i]

        if c == "\n":
            line += 1
            i += 1
            continue
        if c in " \t\r\f\v":
            i += 1
            continue

        # ---- comment ------------------------------------------------------
        if c == "-" and src.startswith("--", i):
            m = LONG_OPEN.match(src, i + 2)
            if m:
                close = "]" + m.group(1) + "]"
                k = src.find(close, m.end())
                k = n if k == -1 else k + len(close)
            else:
                k = src.find("\n", i)
                k = n if k == -1 else k
            comments.append((i, k))
            line += src.count("\n", i, k)
            i = k
            continue

        # ---- long string --------------------------------------------------
        if c == "[":
            m = LONG_OPEN.match(src, i)
            if m:
                close = "]" + m.group(1) + "]"
                k = src.find(close, m.end())
                if k != -1:
                    end = k + len(close)
                    toks.append(Tok("string", src[m.end():k], line, i, end))
                    line += src.count("\n", i, end)
                    i = end
                    continue

        # ---- short string -------------------------------------------------
        if c in "\"'":
            j = i + 1
            buf = []
            while j < n:
                ch = src[j]
                if ch == "\\":
                    buf.append(src[j:j + 2])
                    j += 2
                    continue
                if ch == c:
                    j += 1
                    break
                if ch == "\n":
                    break
                buf.append(ch)
                j += 1
            toks.append(Tok("string", "".join(buf), line, i, j))
            line += src.count("\n", i, j)
            i = j
            continue

        # ---- number -------------------------------------------------------
        if c.isdigit() or (c == "." and i + 1 < n and src[i + 1].isdigit()):
            m = NUMBER_RE.match(src, i)
            if m:
                toks.append(Tok("number", m.group(0), line, i, m.end()))
                i = m.end()
                continue

        # ---- name / keyword -----------------------------------------------
        if c.isalpha() or c == "_":
            m = re.match(r"[A-Za-z_][A-Za-z0-9_]*", src[i:])
            word = m.group(0)
            kind = "kw" if word in KEYWORDS else "name"
            toks.append(Tok(kind, word, line, i, i + len(word)))
            i += len(word)
            continue

        # ---- operator -----------------------------------------------------
        for op in OPS:
            if src.startswith(op, i):
                toks.append(Tok("op", op, line, i, i + len(op)))
                i += len(op)
                break
        else:
            toks.append(Tok("op", c, line, i, i + 1))
            i += 1

    chars = list(src)
    for (a, b) in comments:
        for k in range(a, b):
            if chars[k] != "\n":
                chars[k] = " "
    return toks, comments, "".join(chars)


# ---------------------------------------------------------------------------
# block scanner
# ---------------------------------------------------------------------------
def match_end(toks, open_idx):
    """Index of the ``end``/``until`` closing the block opened at ``open_idx``."""
    depth = 0
    expect_do = False
    for j in range(open_idx, len(toks)):
        t = toks[j]
        if t.kind != "kw":
            continue
        v = t.value
        if v in ("function", "if", "repeat"):
            depth += 1
        elif v in ("for", "while"):
            depth += 1
            expect_do = True
        elif v == "do":
            if not expect_do:
                depth += 1
            expect_do = False
        elif v in ("end", "until"):
            depth -= 1
            if depth == 0:
                return j
    return None


def find_actions(toks):
    """Locate every dispatcher registration.

    Returns (actions, templates, named_funcs) where ``actions`` maps
    name -> dict(def_line, params, body_start, body_end, via) and ``templates``
    holds dynamic ``A[var] = function`` definitions keyed by the variable name.
    """
    actions = {}
    templates = {}
    named_funcs = {}

    for i, t in enumerate(toks):
        # record "local function NAME(" / "function NAME(" bodies (for makeMove)
        if t.kind == "kw" and t.value == "function":
            if (i + 2 < len(toks) and toks[i + 1].kind == "name"
                    and toks[i + 2].value == "("):
                close = matching_paren(toks, i + 2)
                end = match_end(toks, i)
                if close is not None and end is not None:
                    named_funcs[toks[i + 1].value] = dict(
                        def_line=toks[i + 1].line,
                        params=param_names(toks, i + 2, close),
                        body_start=close + 1,
                        body_end=end,
                    )

        if t.kind != "name" or t.value != "A":
            continue
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        if nxt is None:
            continue

        key = None
        key_var = None
        j = i + 1
        if nxt.value == "." and i + 2 < len(toks) and toks[i + 2].kind == "name":
            key = toks[i + 2].value
            j = i + 3
        elif (nxt.value == "[" and i + 2 < len(toks) and toks[i + 2].kind == "string"
              and i + 3 < len(toks) and toks[i + 3].value == "]"):
            key = toks[i + 2].value
            j = i + 4
        elif nxt.value == "[" and i + 2 < len(toks) and toks[i + 2].kind == "name" \
                and i + 3 < len(toks) and toks[i + 3].value == "]":
            key_var = toks[i + 2].value
            j = i + 4
        else:
            continue

        if j >= len(toks) or toks[j].value != "=":
            continue
        if j + 1 >= len(toks) or toks[j + 1].kind != "kw" or toks[j + 1].value != "function":
            # `A.x = <something else>` -- recorded as an anomaly by the caller
            actions.setdefault("__anomalies__", []).append(
                dict(name=key or key_var, line=t.line,
                     rhs=toks[j + 1].value if j + 1 < len(toks) else "?")
            )
            continue

        close = matching_paren(toks, j + 2)
        end = match_end(toks, j + 1)
        if close is None or end is None:
            continue

        info = dict(def_line=t.line, params=param_names(toks, j + 2, close),
                    body_start=close + 1, body_end=end, via="A")

        if key is not None:
            actions[key] = info
        else:
            info["def_line"] = t.line
            templates[key_var] = info

    return actions, templates, named_funcs


def matching_paren(toks, open_idx):
    if open_idx >= len(toks) or toks[open_idx].value != "(":
        return None
    depth = 0
    for j in range(open_idx, len(toks)):
        v = toks[j].value
        if v == "(":
            depth += 1
        elif v == ")":
            depth -= 1
            if depth == 0:
                return j
    return None


def param_names(toks, open_idx, close_idx):
    names = []
    depth = 0
    for j in range(open_idx + 1, close_idx):
        v = toks[j].value
        if v in ("(", "{", "["):
            depth += 1
        elif v in (")", "}", "]"):
            depth -= 1
        elif toks[j].kind == "name" and depth == 0:
            names.append(v)
    return names


# ---------------------------------------------------------------------------
# argument extraction inside one action body
# ---------------------------------------------------------------------------
class ScopeTracker:
    """Tracks which names are currently bound to the ``args`` table."""

    def __init__(self, param):
        self.param = param
        self.scopes = [{param: True}]
        self.blocks = []

    def push(self, names=None):
        self.scopes.append({n: False for n in (names or [])})
        self.blocks.append(True)

    def pop(self):
        if self.blocks:
            self.blocks.pop()
            self.scopes.pop()

    def lookup(self, name):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return False

    def bind_alias(self, name):
        self.scopes[-1][name] = True


def walk_body(toks, start, end, param, on_ref, on_local_pairs=None, on_call=None):
    """Single pass over the body, keeping Lua block scope in sync.

    ``on_ref(field_name, field_token_index, form)`` fires for every read of a field
    of the args table (or of an alias of it).  ``on_call(callee, call_index,
    first_arg_is_args)`` fires for every function call, so helper delegation
    (``cmdText(args)``) can be followed.
    """
    st = ScopeTracker(param)
    expect_do = False
    j = start
    while j < end:
        t = toks[j]
        v = t.value

        if t.kind == "kw":
            if v == "function":
                names = []
                if j + 1 < end and toks[j + 1].value == "(":
                    close = matching_paren(toks, j + 1)
                    if close is not None and close < end:
                        names = param_names(toks, j + 1, close)
                st.push(names)
            elif v == "for":
                names = []
                k = j + 1
                while k < end and toks[k].value not in ("do", "="):
                    if toks[k].kind == "name":
                        names.append(toks[k].value)
                    k += 1
                st.push(names)
                expect_do = True
                if on_local_pairs is not None:
                    on_local_pairs(names, j, end)
            elif v == "while":
                st.push()
                expect_do = True
            elif v in ("if", "repeat"):
                st.push()
            elif v == "do":
                if expect_do:
                    expect_do = False
                else:
                    st.push()
            elif v in ("end", "until"):
                st.pop()
            elif v == "local":
                k = j + 1
                lhs = []
                while k < end:
                    if toks[k].kind == "name":
                        lhs.append(toks[k].value)
                        k += 1
                    else:
                        break
                    if k < end and toks[k].value == ",":
                        k += 1
                        continue
                    break
                if lhs and k < end and toks[k].value == "=":
                    rhs = k + 1
                    if rhs < end and toks[rhs].value == param:
                        after = toks[rhs + 1].value if rhs + 1 < end else None
                        # `local x = args and args.y` binds a *field*, not the table
                        if after != "and":
                            st.bind_alias(lhs[0])
            j += 1
            continue

        if t.kind == "name" and st.lookup(t.value) and j + 2 < end:
            nxt = toks[j + 1]
            if nxt.value == "." and toks[j + 2].kind == "name":
                on_ref(toks[j + 2].value, j + 2, "dot")
            elif nxt.value == "[" and toks[j + 2].kind == "string" and toks[j + 3].value == "]":
                on_ref(toks[j + 2].value, j + 2, "bracket")
                j += 2
        elif t.kind == "name" and on_call is not None and j + 1 < end and toks[j + 1].value == "(":
            first = toks[j + 2] if j + 2 < end else None
            on_call(t.value, j, bool(first is not None and first.kind == "name" and st.lookup(first.value)))
        j += 1

    return st


def parse_literal(tok):
    if tok is None:
        return MISSING
    if tok.kind == "string":
        return tok.value
    if tok.kind == "number":
        return float(tok.value) if re.search(r"[.eE]", tok.value) else int(tok.value)
    if tok.value == "true":
        return True
    if tok.value == "false":
        return False
    return MISSING


def literal_type(value):
    if value is MISSING:
        return "unknown"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    return "unknown"


def describe_ref(toks, idx, end, param):
    """Inspect one ``args.x`` reference: -> (default, default_kind, type_hint)."""
    default = MISSING
    default_kind = None
    number_call = False

    # -- backwards: is it wrapped in tonumber(...) ? ------------------------
    k = idx - 1
    steps = 0
    while k >= 0 and steps < 10:
        v = toks[k].value
        if v == "tonumber":
            number_call = True
            break
        if v in BWD_STOP:
            break
        k -= 1
        steps += 1

    # -- forwards: `or <literal>` / `~= false` -----------------------------
    j = idx + 1
    while j < end and toks[j].value == ")":       # close tonumber( / math.floor(
        j += 1
    if j < end:
        v = toks[j].value
        if v == "or" and j + 1 < end and toks[j + 1].value not in FWD_STOP:
            lit = parse_literal(toks[j + 1])
            if lit is not MISSING:
                default = lit
                default_kind = "or-literal"
        elif v in ("~=", "==") and j + 1 < end and toks[j + 1].value == "false":
            default = (v == "~=")
            default_kind = "compare-false" if v == "~=" else "compare-false-neg"

    if number_call:
        ttype = "number"
    elif default is not MISSING:
        ttype = literal_type(default)
    else:
        ttype = "unknown"
    return default, default_kind, ttype


def body_type_evidence(masked_body, argname):
    """Fallback scalar-type evidence for args with no literal default."""
    pat = re.escape(argname)
    if re.search(r"tonumber\s*\([^()]{0,40}?\b" + pat + r"\b", masked_body):
        return "number"
    if re.search(r'type\s*\([^()]{0,40}?\b' + pat + r'\b[^()]{0,20}?\)\s*[~=]=\s*"string"', masked_body):
        return "string"
    if re.search(r'\b' + pat + r'\b\s*[~=]=\s*"[^"]*"', masked_body):
        return "string"
    if re.search(r'\b' + pat + r'\b\s*[~=]=\s*(?:true|false)\b', masked_body):
        return "boolean"
    return "unknown"


TYPE_RANK = {"number": 3, "boolean": 2, "string": 1, "unknown": 0}


def collect_refs(toks, start, end, param):
    """One body -> (entries, order, helper_calls, pairs_loops).

    ``entries`` maps arg name -> {default, kind, type}; ``helper_calls`` lists the
    in-file functions the body calls passing the args table as the first argument.
    """
    entries = {}
    order = []
    helper_calls = []
    pairs_loops = []

    def on_ref(name, idx, form):
        if name not in entries:
            entries[name] = dict(default=MISSING, kind=None, type="unknown", refs=0)
            order.append(name)
        entry = entries[name]
        entry["refs"] += 1
        d, kind, ttype = describe_ref(toks, idx, end, param)
        if d is not MISSING and entry["default"] is MISSING:
            entry["default"] = d
            entry["kind"] = kind
        if TYPE_RANK[ttype] > TYPE_RANK[entry["type"]]:
            entry["type"] = ttype

    def on_local_pairs(names, idx, _end):
        # `for k, v in pairs(<param> or {}) do` -- remember the loop vars so a
        # `k ~= "wait_ms"` filter can be surfaced as a pass-through hint.
        k = idx + 1
        limit = 0
        while k < _end and limit < 24:
            if toks[k].value == "pairs" and k + 1 < _end and toks[k + 1].value == "(":
                if k + 2 < _end and toks[k + 2].value == param:
                    pairs_loops.append(names)
                    return
            if toks[k].value == "do":
                return
            k += 1
            limit += 1

    def on_call(callee, idx, first_is_args):
        if first_is_args:
            helper_calls.append(callee)

    walk_body(toks, start, end, param, on_ref, on_local_pairs, on_call)
    return entries, order, helper_calls, pairs_loops


def gather_refs(toks, start, end, param, helpers, depth=0, seen=None, via=None):
    """collect_refs + sound one-hop dataflow through helpers called as f(args).

    ``via`` maps each inherited arg name to the helper it came from.
    """
    seen = set() if seen is None else seen
    via = {} if via is None else via
    entries, order, helper_calls, pairs_loops = collect_refs(toks, start, end, param)

    if depth < 3:
        for callee in helper_calls:
            if callee in seen or callee not in helpers:
                continue
            finfo = helpers[callee]
            if len(finfo["params"]) != 1:
                continue          # cannot map the args table onto this signature
            seen.add(callee)
            sub_via = {}
            sub, sub_order, _hc, _pl, _sv = gather_refs(
                toks, finfo["body_start"], finfo["body_end"], finfo["params"][0],
                helpers, depth + 1, seen, sub_via)
            for n in sub_order:
                if n not in entries:
                    entries[n] = sub[n]
                    order.append(n)
                    via[n] = sub_via.get(n, callee)
    return entries, order, helper_calls, pairs_loops, via


def extract_action(masked, toks, info, helpers):
    """-> (args dict, markers list, notes list) for one action."""
    param = info["params"][0] if info["params"] else None
    start, end = info["body_start"], info["body_end"]
    notes = []
    body_masked = masked[toks[start].start:toks[end].end] if start < end else ""

    entries, order, pairs_loops, via = {}, [], [], {}

    if param is not None:
        entries, order, _helper_calls, pairs_loops, via = gather_refs(
            toks, start, end, param, helpers)

        for helper in sorted(set(via.values())):
            inherited = [n for n in order if via.get(n) == helper]
            notes.append("args %s inherited from %s() (called as %s(<args>))"
                         % ("/".join(inherited), helper, helper))

        # string-literal passthrough hints (NOT added to args -- see report rules)
        for names in pairs_loops:
            if not names:
                continue
            for lit in re.findall(
                    r'\b' + re.escape(names[0]) + r'\b\s*[~=]=\s*"([A-Za-z_][A-Za-z0-9_]*)"',
                    body_masked):
                if lit not in entries and lit not in order:
                    notes.append("passthrough-hint:" + lit)

    args = {}
    for name in order:
        entry = entries[name]
        ttype = entry["type"]
        if ttype == "unknown":
            ttype = body_type_evidence(body_masked, name)
        default = None if entry["default"] is MISSING else entry["default"]
        args[name] = {"default": default, "type": ttype}

    markers = [m for m in MARKERS if m in body_masked]
    return args, markers, notes


def comment_above(src, line_no):
    lines = src.split("\n")
    out = []
    i = line_no - 2
    while i >= 0:
        s = lines[i].strip()
        if s.startswith("--"):
            out.append(s)
            i -= 1
            continue
        break
    if out:
        out.reverse()
        return "\n".join(out)
    # fall back to a trailing comment on the definition line itself
    if 0 <= line_no - 1 < len(lines):
        s = lines[line_no - 1]
        idx = s.find("--")
        if idx != -1:
            return s[idx:].strip()
    return None


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------
def build_schema(lua_path):
    # hash RAW BYTES: the agent layer compares the file's sha1 later, so the value
    # recorded here must be the true digest of the bytes on disk, independent of
    # any BOM / CRLF / encoding quirk the decoder papers over.
    with open(lua_path, "rb") as fh:
        raw = fh.read()
    sha1 = hashlib.sha1(raw).hexdigest()
    src = raw.decode("utf-8", "replace")

    toks, _comments, masked = tokenize(src)
    actions, templates, named_funcs = find_actions(toks)
    anomalies = actions.pop("__anomalies__", [])

    notes = []

    # -- expand dynamic registrations (makeMove) ---------------------------
    for fname, finfo in named_funcs.items():
        tmpl = None
        for var, tinfo in templates.items():
            if tinfo["body_start"] > finfo["body_start"] and tinfo["body_end"] <= finfo["body_end"]:
                tmpl = (var, tinfo)
                break
        if tmpl is None:
            continue
        var, tinfo = tmpl
        # find calls:  fname("action", ...)
        for i, t in enumerate(toks):
            if t.kind != "name" or t.value != fname:
                continue
            if i + 2 >= len(toks) or toks[i + 1].value != "(" or toks[i + 2].kind != "string":
                continue
            name = toks[i + 2].value
            if name in actions:
                continue
            actions[name] = dict(def_line=t.line, params=tinfo["params"],
                                 body_start=tinfo["body_start"], body_end=tinfo["body_end"],
                                 via="%s()" % fname)
            notes.append("%s: args come from the shared %s() template body (line %d)"
                         % (name, fname, tinfo["def_line"]))

    out_actions = {}
    for name in sorted(actions, key=lambda k: (actions[k]["def_line"], k)):
        info = actions[name]
        args, markers, anotes = extract_action(masked, toks, info, named_funcs)
        out_actions[name] = {
            "args": args,
            "markers": markers,
            "line": info["def_line"],
            # NOTE: `long_running` and `comment` are extras beyond the required
            # args/markers/line triple; they carry the classification asked for
            # and the doc comment sitting above the definition.
            "long_running": any(m in LONG_RUNNING_MARKERS for m in markers),
            "comment": comment_above(src, info["def_line"]),
        }
        for n in anotes:
            notes.append("%s: %s" % (name, n))

    schema = {
        "generated_from": LUA_REL,
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
                                .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "sha1": sha1,
        "actions": out_actions,
    }

    for a in anomalies:
        notes.append("ANOMALY: A.%s = %s (line %d) is not a function registration"
                     % (a["name"], a["rhs"], a["line"]))

    return schema, notes


def print_summary(schema, notes, out_path):
    actions = schema["actions"]
    print("generated_from : %s" % schema["generated_from"])
    print("sha1           : %s" % schema["sha1"])
    print("generated_at   : %s" % schema["generated_at"])
    print("actions        : %d" % len(actions))
    print()

    name_w = max([len(n) for n in actions] + [6])
    print("%-*s  %5s  %-13s  %s" % (name_w, "ACTION", "LINE", "KIND", "ARGS"))
    print("%s  %5s  %-13s  %s" % ("-" * name_w, "-" * 5, "-" * 13, "-" * 40))
    for name, info in actions.items():
        kind = "long-running" if info["long_running"] else "quick"
        if info["markers"]:
            kind = "markers:" + ",".join(info["markers"])
        argstr = ", ".join(
            "%s(%s%s)" % (a,
                          v["type"],
                          "" if v["default"] is None else "=" + json.dumps(v["default"], ensure_ascii=False))
            for a, v in info["args"].items()
        ) or "-"
        print("%-*s  %5d  %-13s  %s" % (name_w, name, info["line"], kind, argstr))

    untyped = [(n, a) for n, i in actions.items() for a, v in i["args"].items() if v["type"] == "unknown"]
    marked = [n for n, i in actions.items() if i["markers"]]
    longrun = [n for n, i in actions.items() if i["long_running"]]
    noargs = [n for n, i in actions.items() if not i["args"]]

    print()
    print("long-running (marker-derived): %s" % (", ".join(longrun) or "-"))
    print("actions carrying markers     : %s"
          % (", ".join("%s[%s]" % (n, ",".join(actions[n]["markers"])) for n in marked) or "-"))
    print("actions with no args         : %s" % (", ".join(noargs) or "-"))
    print("args typed 'unknown'         : %s"
          % (", ".join("%s.%s" % (n, a) for n, a in untyped) or "-"))
    if notes:
        print()
        print("NOTES")
        for n in notes:
            print("  - %s" % n)
    print()
    print("written: %s" % out_path)


def write_schema(schema, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    text = json.dumps(schema, ensure_ascii=False, indent=2) + "\n"
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _force_utf8_stdout():
    """The schema carries CJK comments (and the odd emoji), while a Windows
    console defaults to a legacy code page (e.g. GBK) that cannot encode them.
    Reconfigure the streams so printing never raises UnicodeEncodeError."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    _force_utf8_stdout()
    ap = argparse.ArgumentParser(description="Generate the agent action schema from agent_bridge.lua")
    ap.add_argument("--lua", default=DEFAULT_LUA, help="path to agent_bridge.lua")
    ap.add_argument("--out", default=DEFAULT_OUT, help="path to action_schema.json")
    ap.add_argument("--json", action="store_true", help="print the JSON instead of the summary")
    ap.add_argument("--check", action="store_true",
                    help="regenerate in memory and compare sha1 with the existing schema; exit != 0 if stale")
    opt = ap.parse_args(argv)

    if not os.path.exists(opt.lua):
        print("error: lua file not found: %s" % opt.lua, file=sys.stderr)
        return 1

    schema, notes = build_schema(opt.lua)

    if opt.check:
        if not os.path.exists(opt.out):
            print("STALE: %s does not exist" % opt.out)
            return 2
        with open(opt.out, "r", encoding="utf-8-sig", errors="replace") as fh:
            try:
                old = json.load(fh)
            except ValueError as exc:
                print("STALE: %s is not valid JSON (%s)" % (opt.out, exc))
                return 2
        if old.get("sha1") != schema["sha1"]:
            print("STALE: sha1 mismatch\n  schema: %s\n  lua   : %s"
                  % (old.get("sha1"), schema["sha1"]))
            return 2
        if old.get("actions") != schema["actions"]:
            print("STALE: sha1 matches but the extracted actions differ "
                  "(schema was produced by a different extractor version)")
            return 3
        print("OK: schema is current (sha1 %s, %d actions)"
              % (schema["sha1"], len(schema["actions"])))
        return 0

    write_schema(schema, opt.out)

    if opt.json:
        print(json.dumps(schema, ensure_ascii=False, indent=2))
    else:
        print_summary(schema, notes, opt.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

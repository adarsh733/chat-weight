#!/usr/bin/env python3
"""Shared code for the status line, the prompt hook and the audit.

The one number everything shows is the chat's WEIGHT: how much it has grown
since its first reply, against the point where a fresh chat becomes cheaper
(see "the chat's budget" below). Every chat starts out holding instructions,
tool lists and startup files; that fixed start is not counted, so a brand-new
chat weighs 0%. Never raises: anything unmeasurable comes back measured=False.
"""
import io
import json
import os
import re
import time
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

BAR_WIDTH = 10
GREEN, YELLOW, RED, EMPTY = "🟩", "🟨", "🟥", "⬜"
DOT = {GREEN: "🟢", YELLOW: "🟡", RED: "🔴"}
TAIL_BYTES = 3_000_000      # the last reply is almost always near the end of the log
TAIL_RETRY_BYTES = 40_000_000   # ...unless one huge tool result pushed it further back
HEAD_BYTES = 4_000_000      # the first reply is always near the start
STALE_DAYS = 90             # model names older than this get "(or newer)"
KEEP_STATE_DAYS = 30        # per-chat notes older than this are deleted, once a day
SHARED_STATE = ("restart-costs.json", "pruned.json")


# ------------------------------------------------------------------ storage

def home_dir():
    """~/.claude/chat-weight: the user's settings and notes."""
    return os.path.join(os.path.expanduser("~"), ".claude", "chat-weight")


def state_dir():
    d = os.environ.get("CHAT_WEIGHT_STATE") or os.path.join(home_dir(), "state")
    os.makedirs(d, exist_ok=True)
    return d


def prune_state(now=None):
    """Each chat leaves a few tiny notes behind. Once a day, delete the ones from
    chats older than KEEP_STATE_DAYS so the folder never grows without end."""
    try:
        d = state_dir()
        now = now or time.time()
        marker = os.path.join(d, "pruned.json")
        if now - float((read_json(marker) or {}).get("at") or 0) < 86400:
            return
        write_json(marker, {"at": now})
        cutoff = now - KEEP_STATE_DAYS * 86400
        for name in os.listdir(d):
            p = os.path.join(d, name)
            if name not in SHARED_STATE and os.path.isfile(p) and os.path.getmtime(p) < cutoff:
                try:
                    os.remove(p)
                except Exception:
                    pass
    except Exception:
        pass


def read_json(path):
    try:
        with io.open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def write_json(path, obj):
    try:
        tmp = path + ".tmp"
        with io.open(tmp, "w", encoding="utf-8") as fh:
            json.dump(obj, fh)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def state_file(kind, session_id):
    safe = "".join(ch for ch in str(session_id or "default") if ch.isalnum() or ch in "-_")
    return os.path.join(state_dir(), "%s-%s.json" % (kind, safe or "default"))


# ------------------------------------------------------------------- config

def _merge(base, extra):
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def project_root(cwd):
    """The nearest folder above cwd holding .git or .claude; else cwd itself."""
    start = os.path.abspath(cwd or os.getcwd())
    d = start
    for _ in range(30):
        if os.path.isdir(os.path.join(d, ".git")) or os.path.isdir(os.path.join(d, ".claude")):
            if os.path.abspath(d) != os.path.abspath(os.path.expanduser("~")):
                return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return start


def in_project(root, rel):
    """A setting's path, relative to the project root; "../" may step out of it."""
    return os.path.normpath(os.path.join(root, *str(rel).replace("\\", "/").split("/")))


def load_config(cwd=None):
    """Defaults from config.json, then the user's file, then the project's."""
    cfg = read_json(os.path.join(ROOT, "config.json")) or {}
    _merge(cfg, read_json(os.path.join(home_dir(), "config.json")))
    if cwd:
        proj = os.path.join(project_root(cwd), ".claude")
        _merge(cfg, read_json(os.path.join(proj, "chat-weight.json")))
    for key, val in (("wrap_up_pct", 40), ("fresh_chat_pct", 60), ("restart_multiple", 4),
                     ("restart_tokens_default", 30000), ("memory_cap_pct", 70)):
        cfg.setdefault(key, val)
    cfg.setdefault("handoff_folder", ".claude/handoffs")
    cfg.setdefault("handoff_extra", ".claude/handoff-extra.md")
    cfg.setdefault("context_windows", {"default": 200000})
    return cfg


# ---------------------------------------------------------------- measuring

def _reply_tokens(obj):
    """Everything the model was holding for one reply, or 0 if not a main-chat reply."""
    if obj.get("type") != "assistant" or obj.get("isSidechain"):
        return 0
    u = (obj.get("message") or {}).get("usage") or {}
    return (int(u.get("input_tokens") or 0)
            + int(u.get("cache_creation_input_tokens") or 0)
            + int(u.get("cache_read_input_tokens") or 0))


def _read_part(path, head=None, tail=None):
    size = os.path.getsize(path)
    with open(path, "rb") as fh:
        if tail and size > tail:
            fh.seek(size - tail)
            fh.readline()                      # drop the partial first line
            return fh.read()
        return fh.read(head) if head else fh.read()


def _lines(path, head=None, tail=None, data=None):
    if data is None:
        data = _read_part(path, head, tail)
    for raw in data.splitlines():
        if b'"usage"' in raw:
            try:
                yield json.loads(raw.decode("utf-8", "replace"))
            except Exception:
                continue


def model_id(raw):
    """'claude-opus-5-5' from any spelling a provider uses ('us.anthropic.claude-…',
    'claude-…[1m]'); None for placeholders such as '<synthetic>'."""
    raw = str(raw or "")
    i = raw.find("claude-")
    return raw[i:] if i >= 0 else None


def last_reply(transcript_path):
    """(tokens, model, readable) of the newest main-chat reply.

    tokens is 0 when there is no reply yet. readable is False when the log has
    replies but none carries a size chat-weight understands -- that means Claude
    Code changed its log format, and the honest answer is "can't measure", not 0%.
    Interrupted replies are saved with a placeholder model; only a real model id counts.
    """
    tokens, model = 0, None
    try:
        size = os.path.getsize(transcript_path)
        data = _read_part(transcript_path, tail=TAIL_BYTES)
        if size > TAIL_BYTES and b'"usage"' not in data:
            data = _read_part(transcript_path, tail=TAIL_RETRY_BYTES)
        for obj in _lines(transcript_path, data=data):
            t = _reply_tokens(obj)
            if t:
                tokens = t
                model = model_id((obj.get("message") or {}).get("model")) or model
        readable = (bool(tokens) or b'"input_tokens"' in data
                    or b'"type":"assistant"' not in data.replace(b'": "', b'":"'))
    except Exception:
        return 0, None, False
    return tokens, model, readable


def first_reply_tokens(transcript_path, session_id):
    """What the chat held at its very first reply. Cached per chat."""
    cache = state_file("start", session_id)
    saved = read_json(cache) or {}
    if saved.get("path") == transcript_path and int(saved.get("tokens") or 0) > 0:
        return int(saved["tokens"])
    try:
        for obj in _lines(transcript_path, head=HEAD_BYTES):
            t = _reply_tokens(obj)
            if t:
                write_json(cache, {"path": transcript_path, "tokens": t})
                return t
    except Exception:
        pass
    return 0


def remember_window(session_id, size):
    """The status line hears the real window size from Claude Code; keep it for the hook."""
    try:
        size = int(size or 0)
    except Exception:
        size = 0
    if size > 0:
        write_json(state_file("window", session_id), {"window": size})


def window_for(cfg, session_id, model, tokens=0):
    """Real size from Claude Code if we have it, else the table, else the default.

    A chat already holding more than the table says it can hold is on a bigger
    window than the table knows about; assume the 1M size rather than show >100%.
    """
    told = int((read_json(state_file("window", session_id)) or {}).get("window") or 0)
    if told > 0:
        return told
    table = cfg.get("context_windows") or {}
    best, size = "", int(table.get("default") or 200000)
    for prefix, val in table.items():
        if prefix != "default" and model and model.startswith(prefix) and len(prefix) > len(best):
            best, size = prefix, int(val)
    if model and "[1m]" in model:
        size = max(size, 1000000)
    if tokens > size:
        size = 1000000 if tokens <= 1000000 else tokens
    return size


# ------------------------------------------------------- the chat's budget
#
# The bar does not measure memory. It measures how heavy the chat has become
# compared with starting over, because every reply re-reads everything:
#
#   restart cost      what a fresh chat must re-load to carry on (note + files).
#                     Learned from this user's own fresh chats; a default until then.
#   fresh-chat point  growth = restart_multiple x restart cost, but never past
#                     memory_cap_pct of the model's memory.
#   weight %          growth scaled so the fresh-chat point reads fresh_chat_pct (60).
#
# Measured on 698 real chats: 4x restart cost was the middle ground -- nearly the
# savings of 2-3x with half as many fresh chats. The numbers are locked when a
# chat starts, so the bar never jumps because something was learned mid-chat.

EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
SAMPLES_KEPT = 20


def _first_prompt(transcript_path):
    try:
        with io.open(transcript_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if obj.get("type") == "user" and not obj.get("isMeta"):
                    c = (obj.get("message") or {}).get("content")
                    if isinstance(c, list):
                        c = " ".join(b.get("text", "") for b in c if isinstance(b, dict))
                    return str(c or "")
    except Exception:
        pass
    return ""


def learn_restart_cost(transcript_path, session_id, start, cfg):
    """If this chat began from a handoff note, record what it loaded before its
    first edit: that is one real restart cost. Once per chat; never raises."""
    done = state_file("learned", session_id)
    if read_json(done) is not None:
        return
    folder = str(cfg.get("handoff_folder") or ".claude/handoffs").replace("\\", "/").rstrip("/").split("/")[-1]
    prompt = _first_prompt(transcript_path).replace("\\", "/")
    if not ("/%s/" % folder in prompt and ".md" in prompt):
        write_json(done, {"sample": None})
        return
    try:
        data = _read_part(transcript_path, head=HEAD_BYTES)
        for raw in data.splitlines():
            if b'"tool_use"' not in raw:
                continue
            obj = json.loads(raw.decode("utf-8", "replace"))
            blocks = (obj.get("message") or {}).get("content") or []
            if any(isinstance(b, dict) and b.get("type") == "tool_use"
                   and b.get("name") in EDIT_TOOLS for b in blocks):
                sample = _reply_tokens(obj) - start
                # The status line and the hook can both get here at once: whoever
                # creates the marker first records the sample, so it is never counted twice.
                fd = os.open(done, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump({"sample": sample if sample > 0 else None}, fh)
                if sample > 0:
                    path = os.path.join(state_dir(), "restart-costs.json")
                    kept = (read_json(path) or {}).get("samples") or []
                    write_json(path, {"samples": (kept + [sample])[-SAMPLES_KEPT:]})
                return
        if len(data) >= HEAD_BYTES:      # no edit early on: this chat cannot teach us
            write_json(done, {"sample": None})
    except Exception:
        return


def restart_cost(cfg):
    """The middle of this user's measured restart costs, or the default."""
    samples = sorted((read_json(os.path.join(state_dir(), "restart-costs.json")) or {}).get("samples") or [])
    default = int(cfg.get("restart_tokens_default") or 30000)
    if len(samples) < 3:
        return default
    mid = samples[len(samples) // 2]
    return int(max(default / 3.0, min(default * 3.0, mid)))


def chat_plan(transcript_path, session_id, cfg, start, model, tokens):
    """The numbers this chat is measured against, locked at its first reply."""
    path = state_file("plan", session_id)
    plan = read_json(path) or {}
    window = window_for(cfg, session_id, model, tokens)
    if plan.get("path") != transcript_path or not plan.get("restart"):
        plan = {"path": transcript_path, "restart": restart_cost(cfg)}
    plan["window"] = max(window, int(plan.get("window") or 0))
    cap = plan["window"] * int(cfg.get("memory_cap_pct") or 70) / 100.0 - start
    plan["fresh_at"] = int(max(plan["restart"],
                               min(plan["restart"] * float(cfg.get("restart_multiple") or 4), cap)))
    write_json(path, plan)
    return plan


def measure(transcript_path, session_id, cfg):
    """{'measured', 'pct', 'tokens', 'growth', 'fresh_at', 'model', 'unreadable'} for one chat."""
    out = {"measured": False, "pct": 0, "tokens": 0, "growth": 0, "fresh_at": 0, "model": None,
           "unreadable": False}
    if not transcript_path or not os.path.isfile(transcript_path):
        return out
    prune_state()
    tokens, model, readable = last_reply(transcript_path)
    if not readable:                     # replies exist, but no size we understand
        out["unreadable"] = True
        return out
    if not tokens:                       # no reply yet: a fresh chat weighs nothing
        out["measured"] = True
        return out
    start = first_reply_tokens(transcript_path, session_id)
    learn_restart_cost(transcript_path, session_id, start, cfg)
    plan = chat_plan(transcript_path, session_id, cfg, start, model, tokens)
    growth = max(0, tokens - start)
    pct = growth / float(plan["fresh_at"]) * int(cfg.get("fresh_chat_pct") or 60)
    out.update(measured=True, pct=int(max(0, min(100, round(pct)))), tokens=tokens,
               growth=growth, fresh_at=plan["fresh_at"], model=model)
    return out


# --------------------------------------------------------------------- bar

def bar_line(pct, cfg):
    """One line: ten coloured squares and a plain sentence."""
    fresh = int(cfg.get("fresh_chat_pct") or 60)
    warn = min(int(cfg.get("wrap_up_pct") or 40), fresh - 1)
    pct = int(max(0, min(100, pct)))
    if pct >= fresh:
        seg, where, note = RED, "past %d%%" % fresh, "start a fresh chat"
    elif pct >= warn:
        seg, where, note = YELLOW, "fresh chat at %d%%" % fresh, "wrap up soon"
    else:
        seg, where, note = GREEN, "fresh chat at %d%%" % fresh, "all good"
    filled = int(round(pct / 100.0 * BAR_WIDTH))
    filled = BAR_WIDTH if pct >= 100 else min(BAR_WIDTH - 1, max(1 if pct > 0 else 0, filled))
    return "%s%s  ***%s chat weight %d%% — %s — %s***" % (
        seg * filled, EMPTY * (BAR_WIDTH - filled), DOT[seg], pct, where, note)


# ------------------------------------------------------------------- models

def _days_since(day):
    try:
        return (date.today() - datetime.strptime(str(day), "%Y-%m-%d").date()).days
    except Exception:
        return 0


def model_lines(cfg):
    """The model table the handoff names, in plain lines. New models need no code change:
    Claude Code's short names always point at the newest model, and every other tool's
    names come from config, marked '(or newer)' once the list is old."""
    m = cfg.get("models") or {}
    levels = m.get("levels") or {}
    stale = _days_since(m.get("checked")) > STALE_DAYS
    rows = []
    for tool, names in (m.get("tools") or {}).items():
        if not isinstance(names, dict):
            continue
        cells = []
        for lvl in ("top", "middle", "small"):
            name = names.get(lvl)
            if not name:
                continue
            if stale and not names.get("names_stay_current"):
                name += " (or newer)"
            cells.append("%s = %s" % (lvl, name))
        rows.append("  %s: %s" % (tool, ", ".join(cells)))
    for lvl in ("top", "middle", "small"):
        info = levels.get(lvl) or {}
        rows.append("  %s level is for %s · effort %s" % (lvl, info.get("for", "?"), info.get("effort", "?")))
    rows.append("  A tool not listed: name the level in words, e.g. \"your tool's strongest model\".")
    rows.append("  Never write a version number (\"Opus 5\"): it goes stale the day a newer model ships.")
    return rows


# A family name followed by a version: "Opus 5", "sonnet-4.5", "claude-haiku-4-5".
PINNED = re.compile(r"\b(?:opus|sonnet|haiku|fable)[ -]?\d+(?:[.-]\d+)*\b", re.I)
LINKED = re.compile(r"[`(]([^`()\s]+\.md)[`)]")


def pinned_model_names(extra_path, root, limit=5):
    """[(file, 'Opus 5'), …] — version-pinned model names in the project's handoff additions
    and in up to `limit` .md files linked from their lines about models. Pinned names go stale with every release,
    and project additions win over the skill's rules, so they would quietly bring it back."""
    try:
        with io.open(extra_path, encoding="utf-8") as fh:
            text = fh.read(200000)
    except Exception:
        return []
    found, files = [], [(extra_path, text)]
    # Follow only links on lines about models: other links (a work log, a claims file)
    # record who did what, and "done by Opus 5" there is history, not an instruction.
    about_models = [line for line in text.splitlines() if "model" in line.lower()]
    for rel in LINKED.findall("\n".join(about_models))[:limit]:
        for base in (root, os.path.dirname(extra_path)):
            p = os.path.normpath(os.path.join(base, rel))
            if os.path.isfile(p):
                try:
                    with io.open(p, encoding="utf-8") as fh:
                        files.append((p, fh.read(200000)))
                except Exception:
                    pass
                break
    for path, body in files:
        names = sorted({m.group(0) for m in PINNED.finditer(body)})
        found += [(path, n) for n in names]
    return found

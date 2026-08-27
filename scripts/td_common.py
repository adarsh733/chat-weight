#!/usr/bin/env python3
"""Shared plumbing for the status line and the hooks.

One home for the three things both need: where per-session state lives, how a
project's limits are found, and how many messages the user has actually sent.
"""
import json
import os
from datetime import datetime

DEFAULTS = {
    "max_turns": 50,
    "warn_turns": 35,
    "max_hours": 2,
    "max_context_pct": 60,
    "context_window_tokens": 200000,
}


def state_dir():
    d = os.environ.get("TOKEN_DIET_STATE")
    if not d:
        d = os.path.join(os.path.expanduser("~"), ".claude", "token-diet", "state")
    os.makedirs(d, exist_ok=True)
    return d


def load_config(start_dir):
    """Walk up from start_dir looking for .claude/efficiency.json."""
    cfg = dict(DEFAULTS)
    try:
        d = os.path.abspath(start_dir or ".")
        for _ in range(12):
            p = os.path.join(d, ".claude", "efficiency.json")
            if os.path.isfile(p):
                with open(p, encoding="utf-8") as fh:
                    session = (json.load(fh) or {}).get("session") or {}
                for k in DEFAULTS:
                    if isinstance(session.get(k), (int, float)) and session[k] > 0:
                        cfg[k] = session[k]
                break
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
    except Exception:
        pass
    return cfg


def is_user_turn(obj):
    """True for a real message the human typed.

    Excludes tool results (also type 'user'), meta entries injected by the CLI,
    and subagent side-chains.
    """
    if obj.get("type") != "user" or obj.get("isMeta") or obj.get("isSidechain"):
        return False
    content = (obj.get("message") or {}).get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        return not any(
            isinstance(b, dict) and b.get("type") == "tool_result" for b in content
        )
    return False


CACHE_VERSION = 2


def scan_transcript(transcript_path, session_id):
    """Return {turns, prompts, hours} for one chat.

    `turns` counts the assistant's replies, NOT the messages the user typed.
    That is deliberate and it is what the limits are calibrated against.
    Measured over 93 real chats: the median chat holds 3 typed messages and 171
    assistant replies -- 58 replies per typed message. A limit expressed in
    typed messages would never fire (the largest chat on record had 15), while
    the same chats crossed 60% loaded at assistant reply ~55. Counting replies
    makes the two limits agree; counting typed messages makes one of them dead.

    Re-reads only the bytes appended since the last call: transcripts run to
    megabytes and this is called on every status-line refresh, so the byte
    offset and running counts are cached per chat.
    """
    if not transcript_path or not os.path.isfile(transcript_path):
        return {"turns": 0, "prompts": 0, "hours": 0.0}
    cache_file = os.path.join(state_dir(), "turns-%s.json" % (session_id or "default"))
    offset, turns, prompts, first_ts = 0, 0, 0, None
    try:
        with open(cache_file, encoding="utf-8") as fh:
            cached = json.load(fh)
        if (cached.get("path") == transcript_path
                and cached.get("v") == CACHE_VERSION):
            offset = int(cached.get("offset", 0))
            turns = int(cached.get("turns", 0))
            prompts = int(cached.get("prompts", 0))
            first_ts = cached.get("first_ts")
    except Exception:
        offset, turns, prompts, first_ts = 0, 0, 0, None

    if os.path.getsize(transcript_path) < offset:  # replaced or truncated
        offset, turns, prompts, first_ts = 0, 0, 0, None

    with open(transcript_path, "rb") as fh:
        fh.seek(offset)
        data = fh.read()
    cut = data.rfind(b"\n") + 1          # leave any partial trailing line
    consumed, data = cut, data[:cut]

    last_ts = None
    for raw in data.splitlines():
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw.decode("utf-8", "replace"))
        except Exception:
            continue
        ts = obj.get("timestamp")
        if ts:
            first_ts = first_ts or ts
            last_ts = ts
        if obj.get("type") == "assistant" and not obj.get("isSidechain"):
            turns += 1
        elif is_user_turn(obj):
            prompts += 1

    try:
        tmp = cache_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"v": CACHE_VERSION, "path": transcript_path,
                       "offset": offset + consumed, "turns": turns,
                       "prompts": prompts, "first_ts": first_ts,
                       "last_ts": last_ts}, fh)
        os.replace(tmp, cache_file)
    except Exception:
        pass

    return {"turns": turns, "prompts": prompts, "hours": hours_since(first_ts)}


def last_turn_context_tokens(transcript_path):
    """How full the context was at the end of the most recent reply.

    Returns input + cache-creation + cache-read tokens on the last assistant
    message that carries a usage record -- i.e. the size of everything the model
    was holding at the fullest point of the reply that just finished. This
    already includes every file loaded at startup, so it is never a misleading
    zero on the first message.

    Reads only the tail of the transcript. Transcripts run to many megabytes and
    this fires after every reply, but the only line we need is near the end, so
    we seek instead of scanning the whole file. Never raises; returns 0 on any
    failure so a broken read can never break the meter.
    """
    if not transcript_path or not os.path.isfile(transcript_path):
        return 0
    try:
        size = os.path.getsize(transcript_path)
        tail = 3_000_000                      # 3 MB tail covers the last few turns
        with open(transcript_path, "rb") as fh:
            if size > tail:
                fh.seek(size - tail)
                fh.readline()                 # drop the partial first line
            data = fh.read()
    except Exception:
        return 0

    best = 0
    for raw in data.splitlines():
        if b'"usage"' not in raw:             # cheap skip before the JSON parse
            continue
        try:
            obj = json.loads(raw.decode("utf-8", "replace"))
        except Exception:
            continue
        if obj.get("type") != "assistant" or obj.get("isSidechain"):
            continue
        u = (obj.get("message") or {}).get("usage") or {}
        tot = (int(u.get("input_tokens") or 0)
               + int(u.get("cache_creation_input_tokens") or 0)
               + int(u.get("cache_read_input_tokens") or 0))
        if tot:
            best = tot                        # keep the last one -> the latest turn
    return best


def context_percent(transcript_path, cfg):
    """The fuel gauge number: how full the context is, 0-100."""
    win = int(cfg.get("context_window_tokens") or 200000) or 200000
    tokens = last_turn_context_tokens(transcript_path)
    return int(min(100, max(0, round(tokens / float(win) * 100.0))))


def hours_since(first_ts):
    if not first_ts:
        return 0.0
    try:
        start = datetime.fromisoformat(str(first_ts).replace("Z", "+00:00"))
        now = datetime.now(start.tzinfo)
        return max(0.0, (now - start).total_seconds() / 3600.0)
    except Exception:
        return 0.0


def touch_marker(session_id, who):
    """Leave a per-chat trace of which piece ran.

    The bar and the checker share scan_transcript(), so the shared cache file
    proves only that *something* ran. Separate markers make "is the bar actually
    live in this chat?" an answerable question instead of an inference.
    """
    try:
        p = os.path.join(state_dir(), "ran-%s-%s" % (who, session_id or "default"))
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(datetime.now().isoformat(timespec="seconds"))
    except Exception:
        pass


def session_flag(session_id, name):
    """One-shot marker, so a warning fires once per chat instead of every message."""
    p = os.path.join(state_dir(), "flag-%s-%s" % (session_id or "default", name))
    if os.path.exists(p):
        return True
    try:
        open(p, "w").close()
    except Exception:
        pass
    return False


def once_since(name, since_date):
    """Cross-chat one-shot: has `name` already fired on or after `since_date`?

    session_flag() is per-chat, and every other state file here is too. This is
    the only marker that outlives a chat, which is what "say it at most once a
    week" needs. The caller supplies the window start, so this stays ignorant of
    quota cycles and reset days -- it answers one question and stores one date.

    Returns True if it already fired inside the window (say nothing). Returns
    False and records today if it did not (go ahead and say it).
    """
    p = os.path.join(state_dir(), "every-%s.json" % name)
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(p, encoding="utf-8") as fh:
            last = str((json.load(fh) or {}).get("last") or "")
        if last and last >= str(since_date):
            return True
    except Exception:
        pass
    try:
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"last": today}, fh)
        os.replace(tmp, p)
    except Exception:
        return True          # cannot record it -- stay quiet rather than repeat
    return False


def read_json(path):
    """Best-effort JSON read. Returns None rather than raising."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def write_json(path, obj):
    """Atomic best-effort JSON write. Never raises."""
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(obj, fh)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def savings_cache_path(root):
    """Where the frozen savings sentence for one project lives.

    Both writer (diet.py, after a scan it already paid for) and reader
    (hooks/savings_note.py, on the startup path) need this name. Defining it
    twice is exactly the bug the skill is supposed to find in other people's
    projects, so it is defined here once.
    """
    key = "".join(ch if ch.isalnum() else "-" for ch in os.path.abspath(root or ".").lower())
    return os.path.join(state_dir(), "savings-%s.json" % key.strip("-")[-60:])

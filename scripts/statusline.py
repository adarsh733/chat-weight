#!/usr/bin/env python3
"""token-diet status line.

Renders one line at the bottom of Claude Code showing how used-up this chat is.

Costs zero tokens: Claude Code runs this locally and never sends the output to
the model. It is the only permanent display in the product that adds nothing to
the bill.

Payload fields used (verified against Claude Code 2.1.220, docs 2026-08-21):
  session_id                      per-session cache key
  transcript_path                 counted incrementally for messages sent
  cost.total_duration_ms          wall-clock hours
  context_window.used_percentage  may be null early and after /compact

Never raises. On any failure it prints nothing and exits 0, so a broken status
line can never break a session.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import td_common  # noqa: E402

GREEN = "\033[32m"
AMBER = "\033[33m"
RED = "\033[31m"
DIM = "\033[2m"
RESET = "\033[0m"

BAR_WIDTH = 10
FULL = "▓"   # dark shade
EMPTY = "░"  # light shade


def emit(line):
    """Write UTF-8 bytes straight to stdout.

    Windows stdout is usually cp1252, which cannot encode the bar glyphs; a
    plain print() would raise and silently blank the line. Claude Code captures
    stdout and decodes it as UTF-8, so bytes are the correct thing to send.
    """
    data = (line + chr(10)).encode("utf-8")
    try:
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
    except Exception:
        sys.stdout.write(data.decode("utf-8", "replace"))


def render(pct, width):
    filled = min(BAR_WIDTH, max(0, int(round(pct / 100.0 * BAR_WIDTH))))
    if pct >= 100:
        filled = BAR_WIDTH
    elif pct > 0:
        filled = max(1, filled)
    bar = FULL * filled + EMPTY * (BAR_WIDTH - filled)

    if pct >= 100:
        colour = RED
        label, note = "chat full", "start a fresh one, your work carries over"
    elif pct >= 70:
        colour = AMBER
        label, note = "chat %d%% used" % pct, "wrap up soon"
    else:
        colour = GREEN
        label, note = "chat %d%% used" % pct, "all good"

    # Narrow terminals: drop the advice rather than wrap onto a second row.
    if width and width < BAR_WIDTH + len(label) + len(note) + 6:
        return "%s%s%s  %s%s" % (colour, bar, RESET, label, RESET)
    return "%s%s%s  %s %s· %s%s" % (colour, bar, RESET, label, DIM, note, RESET)


def used_percent(payload, cfg):
    """How close this chat is to the nearest of its three limits.

    A chat is not long because the user typed a lot -- the median chat on record
    holds 3 typed messages and 171 assistant replies. Taking the worst of the
    three is what catches that shape.
    """
    scan = td_common.scan_transcript(
        payload.get("transcript_path"), payload.get("session_id"))
    turns, hours = scan["turns"], scan["hours"]

    duration = (payload.get("cost") or {}).get("total_duration_ms")
    if isinstance(duration, (int, float)) and duration > 0:
        hours = max(hours, float(duration) / 3600000.0)

    ctx = (payload.get("context_window") or {}).get("used_percentage")
    ctx = float(ctx) if isinstance(ctx, (int, float)) else 0.0

    pct = max(
        turns / float(cfg["max_turns"]),
        hours / float(cfg["max_hours"]),
        ctx / float(cfg["max_context_pct"]),
    ) * 100.0
    return int(min(100, max(0, round(pct))))


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0
    try:
        cfg = td_common.load_config(
            (payload.get("workspace") or {}).get("project_dir") or payload.get("cwd"))
        try:
            width = int(os.environ.get("COLUMNS") or 0)
        except Exception:
            width = 0
        emit(render(used_percent(payload, cfg), width))
        td_common.touch_marker(payload.get("session_id"), "bar")
    except Exception:
        if os.environ.get("TOKEN_DIET_DEBUG"):
            import traceback
            traceback.print_exc(file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

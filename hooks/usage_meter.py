#!/usr/bin/env python3
"""Stop hook: the fuel gauge, drawn AFTER the reply, counting the reply just finished.

Fires the instant a reply finishes. By then Claude has written that reply's real
token usage to the transcript, so this is the one place the bar can include the
message the person is actually looking at -- a status line drawn *before* the
reply (the old UserPromptSubmit bar) never can, which is why the first message
always read a misleading 0%.

Costs zero model tokens: it reads a number Claude already wrote to disk and does
arithmetic locally. The bar rides in `systemMessage`, shown to the person and
never fed back to the model, so it adds nothing to the bill either.

Contract (Claude Code hooks, verified 2026-08-23):
  stdin  : {session_id, transcript_path, cwd, stop_hook_active, ...}
  stdout : JSON {"systemMessage": "..."} -> shown to the person, never to model
  exit 0 : always. Never raises, never blocks a reply.

The bar is coloured segments (green -> yellow -> red as the chat fills), matching
the segmented loading-bar look, drawn with the only colour a chat line can carry:
emoji squares.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SKILL, "scripts"))

try:
    import td_common
except Exception:
    td_common = None

BAR_WIDTH = 10
EMPTY = "⬜"          # white square (empty segment)
GREEN = "\U0001F7E9"      # green square
YELLOW = "\U0001F7E8"     # yellow square
RED = "\U0001F7E5"        # red square

RED_AT = 85               # over this, the chat is genuinely pricey


def render(pct, cfg):
    """Build the coloured segmented bar for a 0-100 fullness.

    Green while there is comfortable room, yellow from the handoff line
    (max_context_pct, default 60) so the colour and the wrap-up rule agree, red
    once it is clearly cheaper to start fresh.
    """
    yellow_at = int(cfg.get("max_context_pct") or 60) if cfg else 60
    if pct >= RED_AT:
        seg, note = RED, "a fresh chat is cheaper"
    elif pct >= yellow_at:
        seg, note = YELLOW, "wrap up soon"
    else:
        seg, note = GREEN, ""

    filled = int(round(pct / 100.0 * BAR_WIDTH))
    filled = max(0, min(BAR_WIDTH, filled))
    if pct >= 100:
        filled = BAR_WIDTH
    elif pct > 0:
        filled = max(1, filled)             # any usage shows at least one segment
    bar = seg * filled + EMPTY * (BAR_WIDTH - filled)

    label = "chat %d%% full" % pct
    return "%s  %s%s" % (bar, label, (" · " + note) if note else "")


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0
    if td_common is None:
        return 0
    try:
        cfg = td_common.load_config(payload.get("cwd"))
        pct = td_common.context_percent(payload.get("transcript_path"), cfg)
        td_common.touch_marker(payload.get("session_id"), "meter")
        out = {"systemMessage": render(pct, cfg)}
        sys.stdout.buffer.write((json.dumps(out) + "\n").encode("utf-8"))
    except Exception:
        if os.environ.get("TOKEN_DIET_DEBUG"):
            import traceback
            traceback.print_exc(file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

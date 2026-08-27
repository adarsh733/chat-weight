#!/usr/bin/env python3
"""Gate for the usage meter: the coloured fuel bar drawn AFTER each reply.

Pins the bar shape (coloured segments + "chat NN%"), the green -> yellow -> red
colour bands, and the token maths that feeds it.
Run:  python tests/test_bar_display.py   -> must print PASS (0 fail).
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SKILL, "hooks"))
sys.path.insert(0, os.path.join(SKILL, "scripts"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import usage_meter as m      # noqa: E402
import td_common             # noqa: E402

CFG = {"max_context_pct": 60, "context_window_tokens": 200000}
fails = 0


def check(label, cond):
    global fails
    if cond:
        print("ok   %s" % label)
    else:
        print("FAIL %s" % label)
        fails += 1


# --- colour bands: green under the handoff line, yellow from it, red near full
check("0%% all empty",      m.render(0, CFG) == m.EMPTY * 10 + "  chat 0% full")
check("35%% is green",      m.GREEN in m.render(35, CFG) and m.YELLOW not in m.render(35, CFG))
check("60%% turns yellow",  m.YELLOW in m.render(60, CFG) and "wrap up soon" in m.render(60, CFG))
check("90%% turns red",     m.RED in m.render(90, CFG) and "fresh chat is cheaper" in m.render(90, CFG))

# --- shape: ten segments, filled count tracks the percentage
r46 = m.render(46, CFG)
check("46%% -> 5 filled",   r46.count(m.GREEN) == 5 and r46.count(m.EMPTY) == 5)
check("100%% -> 10 filled", m.render(100, CFG).count(m.RED) == 10)
check("any usage shows >=1 segment", m.render(3, CFG).count(m.GREEN) == 1)
check("label present",      "chat 46%" in r46)

# --- token maths: reads the LAST assistant turn's input+cache from a transcript
with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False,
                                 encoding="utf-8") as fh:
    fh.write(json.dumps({"type": "assistant", "message": {"usage": {
        "input_tokens": 2, "cache_creation_input_tokens": 1000,
        "cache_read_input_tokens": 1000}}}) + "\n")
    # a later, fuller turn -> 100k tokens = 50% of a 200k window
    fh.write(json.dumps({"type": "assistant", "message": {"usage": {
        "input_tokens": 0, "cache_creation_input_tokens": 20000,
        "cache_read_input_tokens": 80000}}}) + "\n")
    path = fh.name

check("last turn tokens = 100k", td_common.last_turn_context_tokens(path) == 100000)
check("context_percent = 50",   td_common.context_percent(path, CFG) == 50)
os.unlink(path)

print("\n%s (%d fail)" % ("PASS" if fails == 0 else "RED", fails))
def test_bar_display():
    """Pytest entry point; the checks above run at import."""
    assert fails == 0


if __name__ == "__main__":
    sys.exit(1 if fails else 0)

#!/usr/bin/env python3
"""token-diet status line: the progress bar at the bottom of the Claude Code terminal.

Free: Claude Code runs this on your machine and never sends it to the model.
It also passes the model's real window size, which is saved so the prompt
hook measures against the true number instead of a guess.

Never raises. On any problem it prints nothing and exits 0.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import td_common  # noqa: E402


def render(pct, cfg):
    """The same bar as in the replies, without the bold markers a terminal can't show."""
    return td_common.bar_line(pct, cfg).replace("***", "")


def main():
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace") or "{}")
        sid = payload.get("session_id")
        td_common.remember_window(sid, (payload.get("context_window") or {}).get("context_window_size"))
        cfg = td_common.load_config((payload.get("workspace") or {}).get("project_dir") or payload.get("cwd"))
        r = td_common.measure(payload.get("transcript_path"), sid, cfg)
        if r["unreadable"]:
            line = "token-diet paused: can't read this Claude Code version's chat log — update token-diet"
        elif r["measured"]:
            line = render(r["pct"], cfg)
        else:
            return 0
        sys.stdout.buffer.write((line + "\n").encode("utf-8"))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""SessionStart hook: the one line that says the week is going further.

The product promise is "we keep saving for you, you keep working". This is the
only moment the promise is ever spoken out loud, so it has to be rare enough to
stay believable: at most once a week, once more when a real milestone is first
crossed, and never twice in the same chat.

Contract (Claude Code hooks, read off the installed binary 2026-08-21):
  stdin  : {session_id, transcript_path, cwd, source, agent_type, model, ...}
           `source` is one of startup | resume | clear | compact | fork, and is
           also what the `matcher` in settings.json filters on. Note the name:
           it is `source`, not `session_start_reason`.
  stdout : JSON {"systemMessage": "..."} shows the line to the person directly,
           and never enters the model's input. Plain stdout would instead be
           handed to the model, which would cost something every chat and put a
           user-facing sentence in the hands of a paraphraser. Use the JSON.
  exit 0 : always.

Never raises, never blocks, never scans anything. It reads one small file that
a previous audit left behind; if that file is missing or old it starts a refresh
in the background, says nothing this time, and is ready by the next chat.
"""
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
SCRIPTS = os.path.join(SKILL, "scripts")
sys.path.insert(0, SCRIPTS)

try:
    import td_common
except Exception:
    td_common = None

DAYS = ["monday", "tuesday", "wednesday", "thursday",
        "friday", "saturday", "sunday"]

STALE_DAYS = 14          # older than this and the sentence is not trustworthy
GRADES = ["F", "D", "C", "B", "A"]


def week_start(reset_day):
    """The date of the most recent reset. The window the weekly rule counts in.

    Said on the first chat after the reset, not on a rolling seven days, so the
    message lands when a fresh allowance starts rather than at a random moment.
    """
    try:
        want = DAYS.index(str(reset_day or "friday").strip().lower())
    except ValueError:
        want = 4
    today = date.today()
    back = (today.weekday() - want) % 7
    return (today - timedelta(days=back)).isoformat()


def is_stale(generated):
    try:
        d = datetime.strptime(str(generated), "%Y-%m-%d").date()
    except Exception:
        return True
    return (date.today() - d).days > STALE_DAYS


def refresh_in_background(cwd):
    """Recompute the sentence without anyone waiting for it.

    The scan behind this sentence reads every session log on disk. That is fine
    once a week in the background and completely unacceptable on the path
    between pressing enter and seeing a cursor, so it is detached and forgotten
    -- this process does not wait, read its output, or care if it fails.
    """
    if td_common is None:
        return
    if td_common.once_since("savings-refresh", date.today().isoformat()):
        return                                   # already kicked one off today
    try:
        kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                  "stdin": subprocess.DEVNULL, "cwd": cwd or None}
        if os.name == "nt":
            kwargs["creationflags"] = 0x00000008 | 0x08000000   # detached, no window
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen(
            [sys.executable, os.path.join(SCRIPTS, "diet.py"), "savings",
             "--all", "--quiet"], **kwargs)
    except Exception:
        pass


def milestone_line(cache):
    """Fires once, the first time the grade actually improves.

    Improvement is the only thing worth interrupting for. A grade that has not
    moved, or has slipped, is not news the person asked to hear.
    """
    now = str(cache.get("grade") or "")
    if now not in GRADES:
        return None
    p = os.path.join(td_common.state_dir(), "milestone.json")
    seen = (td_common.read_json(p) or {}).get("grade")
    td_common.write_json(p, {"grade": now, "on": date.today().isoformat()})
    if seen not in GRADES or GRADES.index(now) <= GRADES.index(seen):
        return None
    return ("Your chats are running leaner than they were. %s"
            % (cache.get("sentence") or ""))


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0
    if td_common is None:
        return 0
    try:
        # The matcher should already have filtered this, but a hook that is
        # wired up by hand should not misbehave when the matcher is missing.
        if str(payload.get("source") or "startup") != "startup":
            return 0

        # Left whether or not anything is said, so "did this fire?" stays an
        # answerable question. A silent hook and an uninstalled hook look
        # identical from the outside, and that cost the status line two weeks.
        td_common.touch_marker(payload.get("session_id"), "savings")

        cwd = payload.get("cwd") or os.getcwd()
        cache = td_common.read_json(td_common.savings_cache_path(cwd))
        if not cache or is_stale(cache.get("generated")):
            refresh_in_background(cwd)
            return 0

        sentence = str(cache.get("sentence") or "").strip()
        if not sentence:
            return 0
        if td_common.session_flag(payload.get("session_id"), "savings"):
            return 0                              # never twice in the same chat

        line = milestone_line(cache)
        if line is None:
            if td_common.once_since("savings", week_start(cache.get("reset_day"))):
                return 0                          # already said this week
            line = sentence

        sys.stdout.buffer.write(
            (json.dumps({"systemMessage": line}) + "\n").encode("utf-8"))
    except Exception:
        if os.environ.get("TOKEN_DIET_DEBUG"):
            import traceback
            traceback.print_exc(file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

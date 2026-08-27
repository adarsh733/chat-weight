#!/usr/bin/env python3
"""UserPromptSubmit hook: warn at the thresholds.

At the two thresholds it hands the model a nudge to wrap up or write the
carry-over note -- a rule in a markdown file only works if the model chooses to
follow it, and this fires on the event itself so it does not depend on that
choice. Silent otherwise. (The fuel-gauge bar moved to hooks/usage_meter.py, a
Stop hook, so it can be drawn after the reply and count the reply just finished
instead of always reading one turn stale.)

Contract (Claude Code hooks, verified 2026-08-21):
  stdin  : {session_id, transcript_path, cwd, user_input, ...}
  stdout : one JSON object.
             systemMessage                     -> shown to the person, never
                                                  enters the model's input
             hookSpecificOutput.additionalContext -> added to the model's input
  exit 2 : would erase the user's prompt -- never used here

Never raises. On any failure it prints nothing and exits 0, so a broken hook can
never block a prompt.
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


def posix(path):
    return path.replace("\\", "/")


def ceiling_message(turns, hours, cfg):
    reason = []
    if turns >= cfg["max_turns"]:
        reason.append("%d steps of work" % turns)
    if hours >= cfg["max_hours"]:
        reason.append("%.1f hours" % hours)
    return "\n".join([
        "[token-diet] This chat is full (%s). Every further message here costs"
        % " and ".join(reason or ["at its limit"]),
        "several times what the same message costs in a fresh chat.",
        "",
        "Before doing anything this message asked for, do this instead:",
        "",
        "  1. Run:  python %s --slug <short-topic>" % posix(
            os.path.join(SKILL, "scripts", "handoff.py")),
        "  2. Read: %s" % posix(os.path.join(SKILL, "reference", "handoff.md")),
        "     and write the carry-over note exactly as it specifies -- all seven",
        "     sections, in order, plain language, no jargon.",
        "  3. Release any file locks you hold in .claude/ACTIVE-WORK.md.",
        "  4. Print the note as one copy-pasteable block AND save it to the path",
        "     the script prints.",
        "",
        "Do not start new work. If this message was 'continue' or similar, the note",
        "is the answer to it. Tell the user in one plain line that this chat is full,",
        "that the note carries everything over, and that they should paste it into a",
        "fresh chat. Do not use the words handoff, context, tokens or turns.",
    ])


def warn_message(turns, cfg):
    return (
        "[token-diet] This chat is about two-thirds used (%d of %d steps of work). "
        "Finish what is in flight and avoid starting anything new that cannot land "
        "in a few messages. Say this to the user in one short plain line -- do not "
        "use the words handoff, context, tokens or turns." % (turns, cfg["max_turns"])
    )


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0
    if td_common is None:
        return 0
    try:
        cfg = td_common.load_config(payload.get("cwd"))
        session_id = payload.get("session_id")
        scan = td_common.scan_transcript(
            payload.get("transcript_path"), session_id)
        turns, hours = scan["turns"], scan["hours"]
        td_common.touch_marker(session_id, "guard")

        # The fuel-gauge bar now lives in hooks/usage_meter.py (a Stop hook), so
        # it draws AFTER the reply and can count the reply just finished. This
        # hook keeps only the two nudges, which must reach the model, so they
        # still ride in additionalContext. Silent unless one of them fires.
        parts = []
        if turns >= cfg["max_turns"] or hours >= cfg["max_hours"]:
            parts.append(ceiling_message(turns, hours, cfg))
        elif turns >= cfg["warn_turns"] and not td_common.session_flag(
                session_id, "warned"):
            parts.append(warn_message(turns, cfg))   # once only; nagging is not a feature

        if not parts:
            return 0

        out = {"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "\n\n".join(parts),
        }}

        sys.stdout.buffer.write((json.dumps(out) + "\n").encode("utf-8"))
    except Exception:
        if os.environ.get("TOKEN_DIET_DEBUG"):
            import traceback
            traceback.print_exc(file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

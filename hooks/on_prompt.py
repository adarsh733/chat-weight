#!/usr/bin/env python3
"""Runs each time the user sends a message (Claude Code UserPromptSubmit hook).

1. Asks Claude to end its reply with the progress bar, so the bar shows in every
   Claude Code window, including ones that draw no status line.
2. Once chat weight passes 60%, asks Claude, once, to finish the step it is
   on and, at that safe break, write the handoff (reference/handoff.md).
3. After that, one short line per message: a nudge until the note exists, then
   a reminder that it does. Nothing is ever blocked.

Prints nothing and exits 0 on any problem, so it can never break a chat.
"""
import io
import json
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SKILL, "scripts"))

import td_common  # noqa: E402

RULES = os.path.join(SKILL, "reference", "handoff.md")
EXTRA_MAX = 4000

BAR = ("[chat-weight] End your reply with this exact line, on its own line, after all "
       "other text. Do not comment on it:\n\n%s")
BAR_ABOVE_PASTE = ("[chat-weight] Put this exact line on its own line just above the paste "
                   "block, which stays the very last thing. Do not comment on it:\n\n%s")
NUDGE = ("[chat-weight] Still no handoff note, and chat weight is %d%%. At the next safe "
         "break, write it as %s says.")
PINNED = ("[chat-weight] Model names: this project's handoff rules name fixed versions (%s). "
          "Those go stale when a newer model ships. In this handoff name the level and the "
          "model name from the list above instead, and tell the user in one line which file "
          "pins versions so they can change it.")
UNREADABLE = ("[chat-weight] chat-weight could not measure this chat: this version of Claude "
              "Code writes its chat log in a way chat-weight does not recognise. At the end of "
              "your reply, tell the user in one line that the chat-weight bar is paused and "
              "that updating chat-weight (git pull in its folder) should bring it back. Say it "
              "once; do not repeat it in later replies.")


def _read(path, limit=None):
    try:
        with io.open(path, encoding="utf-8") as fh:
            return fh.read(limit) if limit else fh.read()
    except Exception:
        return ""


def newest_note_since(folder, since):
    best, best_t = None, since
    try:
        for name in os.listdir(folder):
            p = os.path.join(folder, name)
            if name.endswith(".md") and os.path.isfile(p) and os.path.getmtime(p) > best_t:
                best, best_t = p, os.path.getmtime(p)
    except Exception:
        return None
    return best


def handoff_request(r, cfg, root):
    folder = td_common.in_project(root, cfg["handoff_folder"])
    note = os.path.join(folder, "%s-<short-topic>.md" % datetime.now().strftime("%Y-%m-%d"))
    parts = [
        "[chat-weight] HANDOFF — chat weight is %d%%, past the %d%% line: this chat has grown "
        "about %dk tokens since it started, and every reply re-reads all of it. A fresh chat "
        "is now cheaper." % (r["pct"], cfg["fresh_chat_pct"], r["growth"] // 1000),
        "Never interrupt unfinished work: an edit and the check that proves it are one step. "
        "Finish the step you are on, start nothing new, and at that safe break write the "
        "handoff exactly as these rules say. Save the note as:\n  %s" % note,
        "Model names to use:\n" + "\n".join(td_common.model_lines(cfg)),
        "--- rules ---\n" + _read(RULES).strip(),
    ]
    extra_path = td_common.in_project(root, cfg["handoff_extra"])
    extra = _read(extra_path, EXTRA_MAX).strip()
    if extra:
        parts.append("--- this project's additions ---\n" + extra)
        pinned = td_common.pinned_model_names(extra_path, root)
        if pinned:
            parts.append(PINNED % "; ".join("%s in %s" % (n, p) for p, n in pinned[:6]))
    return "\n\n".join(parts)


def build(data):
    sid = data.get("session_id") or "default"
    cwd = data.get("cwd") or os.getcwd()
    cfg = td_common.load_config(cwd)
    r = td_common.measure(data.get("transcript_path"), sid, cfg)
    if r["unreadable"]:
        flag = td_common.state_file("unreadable", sid)
        if td_common.read_json(flag) is None:
            td_common.write_json(flag, {"told": True})
            return UNREADABLE
        return ""
    if not r["measured"]:
        return ""
    bar = td_common.bar_line(r["pct"], cfg)
    out = [BAR % bar]
    if r["pct"] >= int(cfg["fresh_chat_pct"]):
        root = td_common.project_root(cwd)
        flag = td_common.state_file("handoff", sid)
        asked = td_common.read_json(flag) or {}
        folder = td_common.in_project(root, cfg["handoff_folder"])
        note = asked.get("at") and newest_note_since(folder, asked["at"])
        if note:
            out.append("[chat-weight] The handoff note is written: %s. If the user carries on "
                       "here, help them, but remind them in one line that a fresh chat "
                       "with the paste block is cheaper." % note)
        elif asked.get("at"):
            out.append(NUDGE % (r["pct"], RULES))
        else:
            td_common.write_json(flag, {"at": datetime.now().timestamp() - 1})
            out = [BAR_ABOVE_PASTE % bar, handoff_request(r, cfg, root)]
    return "\n\n".join(out)


def main():
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", "replace")
        text = build(json.loads(raw or "{}"))
    except Exception:
        return 0
    if text:
        payload = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                          "additionalContext": text}}
        sys.stdout.buffer.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

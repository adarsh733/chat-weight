#!/usr/bin/env python3
"""chat-weight's one hook script. Claude Code runs it at three moments:

- UserPromptSubmit (the user sends a message): measures the chat and asks Claude to end
  its reply with the bar, so the bar sits inside the reply in every Claude Code window.
  A newer chat-weight is mentioned here too, once per chat, just above the bar.
- Past 60%, asks Claude, once, for the handoff: with the message that crosses the line,
  during a long run (PostToolUse, after each of Claude's steps) as soon as the line is
  crossed, or right after a reply that crossed it (Stop). Claude finishes the step it
  is on first. After that, one short line per message: a nudge until the note exists,
  then a reminder that it does.
- Otherwise steps and the end of a reply are silent.

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
import updates  # noqa: E402

RULES = os.path.join(SKILL, "reference", "handoff.md")
EXTRA_MAX = 4000

BAR = ("[chat-weight] End your reply with this exact line, on its own line, after all "
       "other text. Do not comment on it:\n\n%s")
BAR_ABOVE_PASTE = ("[chat-weight] Put this exact line on its own line just above the paste "
                   "block, which stays the very last thing. Do not comment on it:\n\n%s")
NUDGE = ("[chat-weight] Still no handoff note, and chat weight is %d%%. At the next safe "
         "break, write it as %s says.")
WRITTEN = ("[chat-weight] The handoff note is written: %s. If the user carries on here, help "
           "them, but remind them in one line that a fresh chat with the paste block is cheaper.")
PINNED = ("[chat-weight] Model names: this project's handoff rules name fixed versions (%s). "
          "Those go stale when a newer model ships. In this handoff name the level and the "
          "model name from the list above instead, and tell the user in one line which file "
          "pins versions so they can change it.")
UPDATE = ("[chat-weight] Just above the bar line, add this exact line once: A chat-weight "
          "update is available (%s) — say \"update chat-weight\". Do not mention it again "
          "in later replies.")
PAUSED = ("[chat-weight] chat-weight could not measure this chat: this version of Claude "
          "Code writes its chat log in a way chat-weight does not recognise. At the end of "
          "your reply, tell the user in one line that the chat-weight bar is paused and that "
          "saying \"update chat-weight\" should bring it back. Say it once; do not repeat it "
          "in later replies.")


def _read(path, limit=None):
    try:
        with io.open(path, encoding="utf-8") as fh:
            return fh.read(limit) if limit else fh.read()
    except Exception:
        return ""


def note_from_this_chat(folder, since, transcript_path):
    """The newest note written after the handoff was asked for AND named in this chat's
    own log. Another chat in the same project can write its own note at the same time;
    a note this chat never wrote or named is not this chat's handoff."""
    try:
        notes = [os.path.join(folder, n) for n in os.listdir(folder) if n.endswith(".md")]
        notes = sorted((p for p in notes if os.path.isfile(p) and os.path.getmtime(p) > since),
                       key=os.path.getmtime, reverse=True)
        if not notes:
            return None
        log = td_common._read_part(transcript_path, tail=td_common.TAIL_BYTES)
    except Exception:
        return None
    for p in notes:
        name = os.path.basename(p)
        if any(form.encode("utf-8") in log for form in (name, json.dumps(name)[1:-1])):
            return p
    return None


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
        "If you were asked to end the reply with the chat-weight bar, put that line just "
        "above the paste block instead: the paste block stays the very last thing.",
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
    """What to send back to Claude Code, as a dict, or None to stay silent."""
    event = data.get("hook_event_name") or "UserPromptSubmit"
    if data.get("agent_id"):
        return None                      # a helper agent's own events: the bar is the main chat's
    sid = data.get("session_id") or "default"
    cwd = data.get("cwd") or os.getcwd()
    cfg = td_common.load_config(cwd)
    r = td_common.measure(data.get("transcript_path"), sid, cfg)
    if r["unreadable"]:
        flag = td_common.state_file("unreadable", sid)
        if event != "UserPromptSubmit" or td_common.read_json(flag) is not None:
            return None
        td_common.write_json(flag, {"told": True})
        return context(event, PAUSED)
    if not r["measured"]:
        r = dict(r, pct=0)               # no chat log yet: a brand-new chat weighs 0%
    root = td_common.project_root(cwd)
    flag = td_common.state_file("handoff", sid)
    asked = td_common.read_json(flag) or {}
    past_line = r["pct"] >= int(cfg["fresh_chat_pct"])
    bar = td_common.bar_line(r["pct"], cfg)
    if past_line and not asked.get("at") and not data.get("stop_hook_active"):
        td_common.write_json(flag, {"at": datetime.now().timestamp() - 1})
        text = handoff_request(r, cfg, root)
        if event == "Stop":              # the reply is finished: write the handoff now
            return {"decision": "block", "reason": text}
        if event == "UserPromptSubmit":
            text = BAR_ABOVE_PASTE % bar + "\n\n" + text
        return context(event, text)
    if event != "UserPromptSubmit":
        return None                      # steps and the end of a reply: silent
    out = [BAR % bar]
    if asked.get("at") and past_line:
        folder = td_common.in_project(root, cfg["handoff_folder"])
        note = note_from_this_chat(folder, asked["at"], data.get("transcript_path"))
        out.append(WRITTEN % note if note else NUDGE % (r["pct"], RULES))
    else:
        out += update_line(cfg, sid)
    return context(event, "\n\n".join(out))


def context(event, text):
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}


def update_line(cfg, sid):
    """The update notice, once per chat, just above the bar. Never alongside a handoff."""
    try:
        found = updates.notice(cfg)
        flag = td_common.state_file("update", sid)
        if not found or td_common.read_json(flag) is not None:
            return []
        td_common.write_json(flag, {"told": found[1]})
        return [UPDATE % found[1]]
    except Exception:
        return []


def main():
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", "replace")
        payload = build(json.loads(raw or "{}"))
    except Exception:
        return 0
    if payload:
        sys.stdout.buffer.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

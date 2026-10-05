---
name: token-diet
description: Keeps Claude Code chats short and cheap. Shows the chat's weight after every reply, and at 60% writes a handoff note so the work continues in a fresh chat. Use when the user asks for a handoff, a fresh or new chat, chat weight, how heavy or long the chat is, where their tokens or usage went, or why they hit their limit.
---

# token-diet

Long chats are expensive because every reply re-reads the whole chat. token-diet keeps
them short:

- **Chat weight.** Every reply ends with a line like
  `🟩🟩⬜⬜⬜⬜⬜⬜⬜⬜  🟢 chat weight 24% — fresh chat at 60% — all good`.
  Weight is growth since the chat began, against the point where a fresh chat becomes
  cheaper (4× what a fresh chat must re-load). It is not memory. A hook adds the line;
  print it exactly as given and do not comment on it.
- **The handoff.** Past 60% the hook asks for a handoff once. Never interrupt unfinished
  work: finish the step you are on (an edit and its check are one step), then follow
  `reference/handoff.md`: a short note saved on disk, then a 3-line paste block as the
  last thing in the reply.

## When the user asks

| They say | Do |
|---|---|
| "write a handoff", "new chat", "continue in a fresh chat" | Follow `reference/handoff.md` now, at any fullness |
| "where did my tokens go", "why did I hit my limit", "audit my usage" | Run `python <this folder>/scripts/audit.py` (add `--all` for every project) and explain the result in plain words |
| "how heavy is this chat" | Read the last bar line; no need to run anything |
| "hand off later / sooner" or other settings | Put the key in `~/.claude/token-diet/config.json` (all projects) or `<project>/.claude/token-diet.json` (one project). Never edit this folder's `config.json` |

## Model names in a handoff

Name the **level** the next chat's work needs (top for thinking, middle for building an
agreed plan, small for routine work), plus the model name for that level. In Claude Code
use `opus`, `sonnet` and `haiku`: Claude Code points these at the newest model of each
kind, so they never go out of date. Other tools' names come from `config.json` → `models`.

## Install

`python install.py` from this folder. Never hand-edit `~/.claude/settings.json` for it.

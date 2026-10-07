---
name: chat-weight
description: Keeps Claude chats short and cheap, in Claude Code and in normal chats. Shows how heavy the chat is, and near the fresh-chat point writes a handoff note so the work continues in a fresh chat. Use when the user asks for a handoff, a fresh or new chat, chat weight, how heavy or long the chat is, where their tokens or usage went, or why they hit their limit.
---

# chat-weight

Long chats are expensive because every reply re-reads the whole chat. chat-weight keeps
them short. It works in two places, and you decide which one you are in:

- **Claude Code** — a `[chat-weight]` line arrives with the user's messages, or you have
  tools that run commands on the user's own computer. Follow this file.
- **A normal chat** (claude.ai on the web, the desktop app's chat, the phone apps) — neither
  of those. There are no hooks and no logs to read, so follow `reference/chat-mode.md`
  instead: same idea, your own estimate, the handoff written into the reply.

In Claude Code with no `[chat-weight]` line at all, chat-weight is not switched on yet: say
in one line that `python install.py` in this folder turns it on.

## Claude Code

- **Chat weight.** Every reply ends with a line like
  `🟩🟩⬜⬜⬜⬜⬜⬜⬜⬜  🟢 chat weight 24% — fresh chat at 60% — all good`.
  Weight is growth since the chat began, against the point where a fresh chat becomes
  cheaper (4× what a fresh chat must re-load). It is not memory. A hook adds the line;
  print it exactly as given and do not comment on it.
- **Updates.** Once a day a background check looks for a newer chat-weight. If there is
  one, the hook asks you to say so in one line, once per chat. Nothing updates until the
  user says "update chat-weight".
- **The handoff.** Past 60% the hook asks for a handoff once. Never interrupt unfinished
  work: finish the step you are on (an edit and its check are one step), then follow
  `reference/handoff.md`: a short note saved on disk, then a 3-line paste block as the
  last thing in the reply.

## When the user asks (Claude Code)

| They say | Do |
|---|---|
| "write a handoff", "new chat", "continue in a fresh chat" | Follow `reference/handoff.md` now, at any fullness |
| "where did my tokens go", "why did I hit my limit", "audit my usage" | Run `python <this folder>/scripts/audit.py` (add `--all` for every project) and explain the result in plain words |
| "update chat-weight" | Run `python <this folder>/scripts/updates.py --apply` and tell the user in plain words what it printed. Only when the user asks: never update on your own |
| "how heavy is this chat" | Read the last bar line; no need to run anything |
| "hand off later / sooner" or other settings | Put the key in `~/.claude/chat-weight/config.json` (all projects) or `<project>/.claude/chat-weight.json` (one project). Never edit this folder's `config.json` |

## Model names in a handoff

Name the **level** the next chat's work needs first, in words (top for thinking,
middle for building an agreed plan, small for routine work), then the model name for that
level. In Claude Code use `opus`, `sonnet` and `haiku`: Claude Code points these at the
newest model of each kind, so they never go out of date. In a normal chat use the family
name from the model menu ("the newest Opus"). Other tools' names come from
`config.json` → `models`. **Never write a version number** ("Opus 5"), even when the
project's own rules do — the hook flags those files so the user can fix them.

## Install

- **Claude Code:** `python install.py` from this folder. Never hand-edit
  `~/.claude/settings.json` for it.
- **Normal chats:** `python scripts/package.py` makes `chat-weight.zip`; upload it where
  skills are added in the app's settings. Nothing else to set up.

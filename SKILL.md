---
name: chat-weight
description: Keeps Claude chats short and cheap. Shows a bar with how heavy the chat is, and near the fresh-chat point writes a handoff so the work continues in a fresh chat. In a normal chat (claude.ai, the Claude apps) ALWAYS load this skill at the start of every chat, before your first reply, even for a greeting or a one-line question, and end every reply with its bar. In Claude Code the bar is drawn for you, so load it only when the user asks for a handoff, a fresh or new chat, chat weight, how heavy or long the chat is, where their tokens or usage went, why they hit their limit, or says "update chat-weight".
---

# chat-weight

Long chats are expensive because every reply re-reads the whole chat. chat-weight keeps
them short.

## Which kind of chat is this? Decide first

You are in **Claude Code** only if your own instructions say you are Claude Code
(Anthropic's coding tool: the `claude` terminal app, the Code tab of the desktop app, or an
editor extension), or a `[chat-weight]` line arrived in this chat. Then follow this file.

Anything else is a **normal chat** (claude.ai on the web, the desktop app's chat, the phone
apps): follow `reference/chat-mode.md` instead of this file.

**Tools prove nothing.** A normal chat can have tools too: a sandbox that runs code,
connectors, desktop extensions that read the user's files. Never decide from tools. If you
are unsure, it is a normal chat.

## Claude Code

- **The bar is not yours to print.** When you finish a reply, Claude Code measures the chat
  (after all the reply's work) and shows the bar under it, once:
  `🟩🟩⬜⬜⬜⬜⬜⬜⬜⬜  🟢 chat weight 24% — fresh chat at 60% — all good`.
  It goes straight to the user, so it costs no tokens and you never see it. Never draw a
  bar yourself in Claude Code. Weight is growth since the chat began, against the point
  where a fresh chat becomes cheaper (4× what a fresh chat must re-load). It is not memory.
- **"I don't see the bar."** Look at `~/.claude/settings.json`. If it mentions
  `chat-weight` and `on_prompt.py`, it is installed: tell them "Open a new chat to see the
  bar." If not, it is not installed: run `python install.py` in this folder (`python3` on
  Mac and Linux), then tell them "Open a new chat to see the bar."
- **Updates.** Once a day a background check looks for a newer chat-weight. If there is
  one, a line under the bar says so, once per chat. Nothing updates until the user says
  "update chat-weight".
- **The handoff.** Past 60%, a `[chat-weight] HANDOFF` message asks for it, once: right
  after a reply that crossed the line, or mid-run if a long task crosses it. Never interrupt
  unfinished work: finish the step you are on (an edit and its check are one step), then
  follow `reference/handoff.md`: a short note saved on disk, then a 3-line paste block as
  the last thing in the reply.

## When the user asks (Claude Code)

Commands below say `python`; on Mac and Linux use `python3`.

| They say | Do |
|---|---|
| "install chat-weight" | Follow the README's "For AI assistants" steps. Then tell the user clearly, on its own line: "Open a new chat to see the bar." |
| "write a handoff", "new chat", "continue in a fresh chat" | Follow `reference/handoff.md` now, at any fullness |
| "where did my tokens go", "why did I hit my limit", "audit my usage" | Run `python <this folder>/scripts/audit.py` (add `--all` for every project) and explain the result in plain words |
| "update chat-weight" | Run `python <this folder>/scripts/updates.py --apply` and tell the user in plain words what it printed, including "open a new chat to use the new version". Only when the user asks: never update on your own |
| "how heavy is this chat" | Point them at the bar under your last reply; no need to run anything |
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

- **Claude Code:** `python install.py` from this folder (`python3` on Mac and Linux). Never
  hand-edit `~/.claude/settings.json` for it. Then: "Open a new chat to see the bar."
- **Normal chats:** `python scripts/package.py` makes `dist/chat-weight.zip`; the README's
  "Normal chats" steps say where to upload it. Then: "Open a new chat to see the bar."

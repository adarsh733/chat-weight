---
name: token-diet
description: Measure and cut AI coding token cost. Use when the user asks about token usage, context cost, session length, why they hit their limit, an efficiency audit, or asks to check file health / oversized files / duplicated values. Also run at session start to enforce session limits and startup-file size ceilings. Triggers on "token", "usage", "context", "quota", "limit", "efficiency", "audit", "how much have I saved", "session too long", "handoff", "file health".
---

# Token Diet

Cuts the cost of AI-assisted coding using the user's own local session logs.
Nothing leaves the machine.

**The one fact everything follows from:** cost = `turns × context size`. Output
is ~0.5% of spend; ~99.5% is re-reading the conversation every turn. So prompt
length barely matters — **session length is almost the entire bill.** Measured
over 61 real sessions: a turn at position 300 cost **3.9×** the same turn at
position 25, and sessions over 300 turns consumed **70%** of 3.07bn tokens.

## Installation & Setup

**When installing or configuring this skill:**
- Run `python install.py` from the skill root directory.
- **Do NOT hand-edit `~/.claude/settings.json`.**
- **Do NOT attempt exploratory configuration or create custom installer scripts.**
- To preview changes safely: `python install.py --dry-run`
- To remove: `python install.py --uninstall`

The installer automatically backs up `settings.json`, verifies the updated file, and rolls back immediately if any error occurs.

## Config

Per-project settings live in `.claude/efficiency.json`. If missing, run
`python scripts/diet.py init` to create it from defaults. Never hard-code
project specifics into this skill — it is meant to be shared.

## Commands

| Ask | Run |
|---|---|
| "audit my usage" / "where did my tokens go" | `python scripts/diet.py audit` |
| "check file health" / "which files are too big" | `python scripts/diet.py health` |
| "check the startup files" / size ceilings | `python scripts/diet.py guard` |
| "audit startup footprint" / loads before typing | `python scripts/diet.py loadaudit` |
| "generate code map" / index symbols | `python scripts/diet.py codemap` |
| "find duplicated constants" / dupes | `python scripts/diet.py dupes` |
| "clean up finished items" / tidy trackers | `python scripts/diet.py tidy` (or `--apply`) |
| "compare cost movement" | `python scripts/diet.py movement --baseline=N --current=N` |
| session start / "are we over the limit" | `python scripts/diet.py check` |
| "how much am I saving" | `python scripts/diet.py savings` |
| first time in a new project | `python scripts/diet.py init` |

## What runs on its own

The user is not supposed to operate this skill. Three pieces run without being
asked, and all three are installed into `~/.claude/settings.json`:

| Piece | When | What it does |
|---|---|---|
| `scripts/statusline.py` | every status-line refresh | Draws how used-up this chat is. Rendered by the CLI, never sent to the model, so it is free. **Only the terminal CLI draws a status line** — it does not appear in the desktop app. |
| `hooks/usage_meter.py` | a reply finishing (Stop hook) | The coloured fuel bar (green → yellow → red segments + `chat NN%`). Drawn *after* the reply, so it counts the reply just finished — the first message included, never a misleading 0%. Reads the last turn's real token count from the transcript and does local arithmetic: **zero model tokens.** Shown as a `systemMessage` (seen by the person, never sent to the model). |
| `hooks/session_guard.py` | every message the user sends | Silent early, one plain line at 35 steps of work, and from 50 steps (or 2 hours) it will not let new work start until the carry-over note is written. (No longer draws the bar — that moved to `usage_meter.py`.) |
| `hooks/savings_note.py` | a chat starting fresh | Says one sentence about how far the week is going. At most once a week, once more the first time the grade improves, never twice in one chat. Reads a cached number; if it is missing or over two weeks old it says nothing and refreshes in the background. |

To check a piece actually ran in a given chat, look for `ran-<piece>-<chat id>`
in `~/.claude/token-diet/state/`.

## The five laws this skill enforces

Read `reference/rules.md` for the full text and the evidence behind each. Load it
only when the user asks *why* a rule exists or wants to change one.

1. **Session ceiling.** Hand off at 50 turns / 2 hours / 60% context, whichever
   first. Warn at 35. At the limit the next message **is** the handoff — not a
   question. A bare "continue" past the limit produces a handoff, never more work.
2. **Startup-file ceilings.** Anything read at session start has a size cap.
   Over cap → archive the history, keep only what is true now.
3. **Load audit.** Report what loads before the user types. Sum the startup
   footprint and flag any startup file over its size cap.
4. **File health.** Every source file scored. Over the split threshold → it must
   be split before new work goes into it.
5. **One value, one home.** A constant defined in two places is a defect. Flag
   duplicate string constants defined across multiple files.

## How to behave (not just what to run)

- **Read line ranges, never whole files.** Use the project's generated code map
  to locate things instead of opening files to search.
- **Ask every question in one batch, before writing code.** A wrong assumption
  costs more than any question.
- **Never fragment coherent work across subagents** — usually more expensive and
  worse than one session.
- **Speak in plain language.** Nobody reading the output should need to know
  what a token is.

## Keeping the skill honest

This skill is meant to improve. When a session reveals a new waste pattern,
add it to `reference/rules.md` with the number that proves it, and update the
analyzer if it can be detected automatically. A rule without a measurement is an
opinion — don't add it.

# Chat mode — chat-weight in a normal chat

A normal chat (claude.ai on the web, the desktop app's chat, the phone apps) has no hooks, no
chat log you can read, and no files on the user's computer. So there is no exact meter. The
idea stays the same: a long chat re-reads everything on every reply, and past a point a fresh
chat is cheaper. Here you judge that point yourself.

## How heavy is the chat — your own estimate

Count roughly how much the chat holds since it began: every message, every reply, every pasted
file or document, every tool result. About 4 characters, or ¾ of a word, is one token.

- **Fresh-chat point:** the chat has grown by about 120,000 tokens (`restart_multiple` ×
  `restart_tokens_default` in `config.json`). That point reads **60%**.
- **Weight** = tokens so far ÷ 120,000 × 60, rounded to the nearest 5.
- A rough guide: a short question and answer is 1–2k tokens; a pasted page of text 1k; a long
  reply with code 2–4k; a pasted PDF or long document 10k or more.

It is an estimate. Never write it as if it were measured: always put `≈` in front of the number,
and round it.

## What to show

Do **not** add a bar to every reply. A guessed number repeated every turn looks measured, and it
costs words each time. Speak only at these points:

- **About 40%**, once: one line at the end of the reply —
  `🟨 This chat is getting long (≈40%). Wrap up the current step; a fresh chat soon will be cheaper.`
- **About 60%**, once: finish the step you are on, then one line —
  `🟥 This chat is long now (≈60%). Say "write a handoff" and I'll set up a fresh chat.`
  Ask rather than write it unasked: the number is a guess, and the note is long.
- **When the user asks** "how heavy is this chat": show the bar with the estimate, e.g.
  `🟩🟩⬜⬜⬜⬜⬜⬜⬜⬜  🟢 chat weight ≈20% (estimate) — fresh chat at 60% — all good`.
  Ten squares, one per 10%: 🟩 below 40%, 🟨 from 40%, 🟥 from 60%.

## The handoff in a chat

Follow every rule in `reference/handoff.md` except where the note goes. A chat cannot save a file
on the user's computer, so:

1. **Write the note in the reply, inside one code block**, so one tap copies it. Same sections,
   same 4 KB limit. Point at things by name ("the pricing table you pasted", "my reply with the
   final plan") — the new chat cannot see this one, so anything it needs to carry on must be in
   the note itself, kept short.
2. **Start the block with two lines** so the new chat knows what it is:

   ```
   Continuing: <one sentence: the topic>
   Start at section 4, item 1. <level> level (<model>) · <effort>.

   ▶ NEXT CHAT — SETUP
   ...the rest of the note...
   ```

3. Tell the user, in one line after the block: open a new chat, pick the model it names, paste
   the block. If they use a Project, they can save the note to the project's files instead, and
   the next chat in that project will find it.
4. **Model names:** use the level, then the model family as it appears in the chat's model menu
   (`config.json` → `models` → `tools` → `"Claude chat"`), e.g. "top level (the newest Opus)".
   Never a version number, as in `handoff.md` rule 5.

## When the user asks for something else

| They say | In a chat |
|---|---|
| "where did my tokens go", "why did I hit my limit" | The usage report reads Claude Code's own logs, so it only works in Claude Code. Explain in plain words what usually costs most here: long chats, big pasted files and documents, many long replies. |
| "update chat-weight" | Updates in chats are manual: download the new version, then upload it again where skills are added in the app's settings, replacing the old one. |
| "hand off later / sooner" | There is no settings file here. Use the new point for the rest of this chat, and say it lasts only for this chat. |

## If you are not sure which mode you are in

Look for proof of Claude Code: a `[chat-weight]` line arriving with the user's message, or tools
that run commands on the user's own computer. Either one → you are in Claude Code; follow
`SKILL.md`. Neither → you are in a normal chat; follow this file.

# Chat mode — chat-weight in a normal chat

A normal chat (claude.ai on the web, the desktop app's chat, the phone apps) has no hooks, no
chat log you can read, and no files on the user's computer. So nothing measures the chat for
you. The idea stays the same: a long chat re-reads everything on every reply, and past a point
a fresh chat is cheaper. Here you keep the count yourself, with a running tally.

## The bar — on every reply

End every reply with the bar, on its own line, after all other text — the same line Claude Code
shows, with `≈` because it is counted, not measured:

```
🟩🟩🟩⬜⬜⬜⬜⬜⬜⬜  ***🟢 chat weight ≈30% — fresh chat at 60% — all good***
🟨🟨🟨🟨⬜⬜⬜⬜⬜⬜  ***🟡 chat weight ≈45% — fresh chat at 60% — wrap up soon***
🟥🟥🟥🟥🟥🟥⬜⬜⬜⬜  ***🔴 chat weight ≈62% — past 60% — start a fresh chat***
```

- Colour: 🟩 + 🟢 below 40%, 🟨 + 🟡 from 40%, 🟥 + 🔴 from 60%. Every filled square takes the
  same colour.
- Squares: the weight ÷ 10, rounded (24% → 2, 26% → 3); at least 1 once the weight is above 0,
  at most 9 below 100%. The rest are ⬜.
- Do not comment on the bar. It speaks for itself.

## The running tally — how to get the number

**1% ≈ 2,000 tokens of growth**, so 60% is about 120,000 tokens — the point where, in real Claude
Code chats, a fresh chat became the cheaper choice (4 × a 30,000-token restart; see `config.json`).

Each reply: **read the number in your previous bar, add what this turn cost, print the new
total.** Work out the bar last, after the rest of the reply is written, so it counts this
reply too. The first reply of a new chat starts from 0. The number only ever goes up. Do not re-guess the
whole chat each time — the tally is what keeps the bar steady.

What a turn costs — add every line that applies:

| This turn had | Add |
|---|---|
| A message and a normal reply (the usual case) | +1 |
| A long reply: a full code file, a detailed plan, a long table | +2 more |
| Pasted text, per 2 pages (about 1,000 words) | +1 |
| An image or screenshot | +1 |
| A PDF or document, per 2 pages | +1 |
| A web search, a fetched page, or another tool result | +3 each |
| An artifact or long file written | +2 each |

What the chat held before the first message — instructions, project files, memory — is not
counted, just as Claude Code does not count a chat's start size.

**Lost the tally?** If your previous reply has no bar, or the user edited an earlier message and
the chat changed under you, estimate the whole chat once — about 4 characters, or ¾ of a word,
is one token; divide by 2,000 — and carry on from that number.

## At 40% and at 60%

- **40%:** the bar turns yellow. Finish what you are doing; start nothing big.
- **60%:** finish the step you are on (an edit and its check are one step), then write the
  handoff below — once. After that the bar stays red; do not write another unless asked.

## The handoff in a chat

Follow every rule in `reference/handoff.md` except where the note goes. A chat cannot save a file
on the user's computer, so:

1. **Write the note in the reply, inside one code block**, so one tap copies it. Same sections,
   same 4 KB limit. Point at things by name ("the pricing table you pasted", "my reply with the
   final plan") — the new chat cannot see this one, so anything it needs to carry on must be in
   the note itself, kept short.
2. **Name this chat so the next one can find it.** Put its link in the note if you know it (the
   user shared it, or it is visible to you); otherwise its title or topic in a few words. Where
   past-chat search is on, the next chat can look back at this one for detail.
3. **Start the block with these lines** so the new chat knows what it is:

   ```
   Continuing: <one sentence: the topic>
   From chat: <link, or title>
   Start at section 4, item 1. <level> level (<model>) · <effort>.

   ▶ NEXT CHAT — SETUP
   ...the rest of the note...
   ```

4. Tell the user, in one line after the block: open a new chat, pick the model it names, paste
   the block. If they use a Project, they can save the note to the project's files instead, and
   the next chat in that project will find it.
5. **Model names:** use the level, then the model family as it appears in the chat's model menu
   (`config.json` → `models` → `tools` → `"Claude chat"`), e.g. "top level (the newest Opus)".
   Never a version number, as in `handoff.md` rule 5.

## When the user asks for something else

| They say | In a chat |
|---|---|
| "write a handoff", "new chat" | Write the handoff above now, at any weight |
| "how heavy is this chat" | Point at the bar; say in one line it is a count, not a measurement |
| "where did my tokens go", "why did I hit my limit" | The usage report reads Claude Code's own logs, so it only works in Claude Code. Explain in plain words what usually costs most here: long chats, big pasted files and documents, web searches, many long replies. |
| "update chat-weight" | Updates in chats are manual: download `chat-weight.zip` again from the chat-weight GitHub page, then in Customize → Skills delete the old chat-weight (its "..." menu) and upload the new zip. Then: open a new chat to use the new version. |
| "which version is this" | Read the `VERSION` file in this skill's folder and say the number. The newest is on the chat-weight GitHub page, under Releases. |
| "hand off later / sooner" | There is no settings file here. Use the new point for the rest of this chat, and say it lasts only for this chat. |

## Which kind of chat is this

You are in Claude Code only if your own instructions say you are Claude Code, or a `[chat-weight]`
line arrived in this chat. Then follow `SKILL.md`. Anything else is a normal chat:
follow this file.

Tools prove nothing. A normal chat can have tools too (a sandbox that runs code, connectors,
desktop extensions that read the user's files), so never decide from tools. Never tell someone in
a normal chat to run `install.py`: that is for Claude Code only. Unsure? It is a normal chat.

# Handoff — carry the work into a fresh chat

A long chat re-reads everything on every reply, so each reply costs more than the last.
A handoff saves what matters in a short note, and a fresh chat picks up from there.

## When

- Chat weight is past 60% — chat-weight tells you — or
- the user asks for one.

Nothing else is a reason to write one.

**In a normal chat** (no hooks, no files on the user's computer), the rules below still hold,
except where the note goes: see `reference/chat-mode.md`, "The handoff in a chat".

## Rules

1. **Never interrupt unfinished work.** An edit and the check that proves it are one step.
   Finish the step you are on, start nothing new, and write the handoff at that safe break —
   even if the whole run began from the chat's first message.
2. **Two outputs:** a note saved on disk, and a 3-line paste block as the very last thing in
   your reply. Do not print the note itself in chat.
3. **The note** goes in `<project>/.claude/handoffs/YYYY-MM-DD-<short-topic>.md` and stays
   under 4 KB. It points at files (`path:line`). It never copies their contents.
4. **Facts only.** Say what is proven done and what is not started — no percentages.
   Anything not checked is written as "not verified".
5. **Pick the model for the next chat's work, not this one's:** top level for thinking, middle
   for building a plan that is already agreed, small for routine work. Name tool, level, model
   and effort together: the level first, in words, then the model name chat-weight gives you.
   **Never a version number** ("Opus 5") — it is wrong the day a newer model ships, and a
   reader who has never used that version cannot tell. The level stays right even when a new
   model family arrives.
6. **The paste block points, it never carries:** topic, absolute path to the note, where to
   start plus tool · model · effort. Three lines, in a code block, so one tap copies it.
7. If the project has its own additions (shown after these rules, under "this project's
   additions"), follow them too. They may change which level or tool to use, but rule 5 still
   holds: if they name a fixed version, use the level and current name instead and tell the
   user which file pins it.

## The note

```
▶ NEXT CHAT — SETUP
Tool:   <tool>
Model:  <top | middle | small> level — <model name, e.g. opus>
Effort: <High | Medium | Low>
Why:    <one line: what kind of work comes next>

# Handoff — <topic> · <YYYY-MM-DD>

## 1. State right now
- Proven done: <what, and what proves it>
- Not started: <what>

## 2. What we did, and why
- <change> — <why>. `file:line`

## 3. Decisions — do not reopen
- <decision> — <one-line reason>

## 4. Next actions, in order
1. <action> — <how the next chat knows it is done>

## 5. Do not do
- <dead end already tried, and why it failed>

## 6. Open questions for the user
- <question> — recommend: <answer>
```

The setup block comes first: the user picks the model before opening the next chat.
An empty section says `— none.` rather than disappearing.

## The paste block — last thing in the reply

```
Continuing: <one sentence: the topic>
Note: <absolute path to the note>
Read that note and start at section 4, item 1. <Tool> · <level> level (<model>) · <effort>.
```

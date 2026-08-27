# Writing the carry-over note

When a chat runs out of room, the next chat starts from nothing. This note is the
only thing that crosses the gap. Everything the next chat has to re-derive costs
the user money and time, so a bad note is worse than no split at all.

**Assume the person reading it reads none of it.** They will paste it and type
"go". It has to work anyway.

Run `python scripts/handoff.py` first. It gathers the facts — files touched, what
failed, what other windows have locked, how long this chat ran. You write the
judgement; never guess a fact the script already knows.

---

## Plain language is a hard rule

The user is not a programmer, and this ships to strangers who are not either.

**Never write these words:** handoff, context, tokens, turns, compaction,
threshold, ceiling.

Say *this chat is getting full*, *a fresh chat*, *your work carries over*.
Write the way you would explain it to a friend who is good at their job and has
never used a terminal.

---

## The seven sections — in this order, all of them, every time

Use these exact headings. A section with nothing in it gets `— none.`, never
deletion: an empty section is information.

```markdown
# Where we got to — <topic> · <YYYY-MM-DD>

## 1. What this chat was doing
<One sentence. Not two.>

## 2. What is finished
<Bulleted. Each line names the thing and the file it lives in. The next chat must
never redo any of this, so anything half-true belongs in section 3, not here.>

## 3. What is half-done, and exactly where it stopped
<For each: the file, the line, what the last attempt was, and what it did. If
nothing is half-done, say so — that is a good outcome, not a gap.>

## 4. Open these files, and nothing else
<Scoped to the NEXT job, not the last one. See the rule below — this is the
section that decides whether the note works. Each file gets one clause saying
why. Never "read the docs". Never a folder. If a file only matters for one
function, give the line range.>

## 5. Do NOT do these
<Traps. Approaches already tried that failed, and what happened. Standing
constraints that are easy to break by accident. Do not paste the lock list here
— see the rule below.>

## 6. What is proven, and what is only assumed
**Proven:** <what was actually run or seen, and how>
**Assumed:** <what looks right but nobody checked>
<Never let an assumption sit in section 2 dressed as a fact.>

## 7. Do this first
<One instruction, written as an instruction. This is the line the next chat acts
on before anything else.>
```

---

## The rule section 4 lives or dies by

**Section 4 lists what the NEXT job needs. Not what the last job touched.**

This is the single thing that decides whether a note is worth writing. It was
tested: a note whose section 4 listed the six files the previous chat had built
scored **4 out of 10**, because the reader had to open nine files it never named
— and one of them held most of the feature they had just been told to build from
scratch.

The two lists barely overlap. Files you finished are finished; naming them
invites someone to re-read work that is already done. So before you write
section 4:

1. **Read the next task.** Whatever names it — a brief, a ticket, a list — open
   that first, and quote the item.
2. **Go looking for what already exists.** Search the codebase for the thing the
   next task describes. Half-built helpers are the expensive thing to miss.
   Name them with line numbers: *"`scripts/diet.py:166` already writes this
   sentence; the job is only the trigger."*
3. **Name what does NOT exist yet**, if the next task assumes it does. *"There is
   no SessionStart hook; that script has to be created."* One line here saves an
   hour of confused searching.
4. **Then** add the few finished files worth keeping open, and say plainly that
   they are finished: *"working, do not open unless something breaks."*

**Never write "items 3 to 9 are untouched" unless you checked.** Saying a thing
is unbuilt when it is half-built is the most expensive sentence a note can hold.

## Locks are a snapshot — never copy them in

Do not paste the current lock list into the note. It goes stale in minutes: in
testing, two of the locked files had been released before the note was even read,
and a new lock had appeared on the very folder the note told the reader to write
into.

Write this instead, and nothing more:

> Before writing any file, read `.claude/ACTIVE-WORK.md` and check your list
> against it. It changes while you work. <If a lock is yours and still open, say
> so and say whether the next chat inherits it or files a fresh one.>

## What makes one good

- **Facts, not mood.** "We made great progress" tells the next chat nothing.
  "The bar renders; the installer is untested" tells it everything.
- **Name files, not areas.** `js/week.js:120-180`, not "the calendar code".
- **Every failure earns its place in section 5.** A failed attempt that is not
  written down will be repeated, at full price.
- **Section 6 is the honesty section.** If you did not see it work, it is
  assumed. Saying "unverified" costs one line; a wrong claim costs a whole chat.
- **One page.** If it is longer, sections 2 and 4 are padded — cut them.

## What makes one bad

- Pointing at documentation instead of naming the file and the reason.
- Listing every file touched instead of the few that matter next.
- Burying the actual next action at the bottom of a wall of prose.
- Claiming something works because it was written, not because it was run.

---

## Where it goes

1. Print it in the chat as one copy-pasteable block.
2. Save it to `.claude/handoffs/YYYY-MM-DD-<slug>.md`.
3. **Release any file locks first.** A note that leaves a lock open deadlocks the
   next window. `handoff.py` prints the open locks — clear your own before you
   finish.

## The test it has to pass

Paste it into a genuinely fresh chat, with nothing else. The chat must continue
correctly **without opening a single file the note does not name.**

If it cannot, the note failed. That is the whole bar.

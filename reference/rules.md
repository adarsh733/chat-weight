# The rules, and the evidence behind each

Loaded only when someone asks *why* a rule exists or wants to change one.
Every rule here was derived from 61 real coding sessions (13,851 AI turns,
3.07 billion tokens). **A rule without a measurement is an opinion — don't add one.**

## The mechanic everything follows from

`cost = turns x context size`

Output is **0.5%** of spend. **99.5%** is re-reading the conversation before every
reply. Two consequences most people get backwards:

- **Prompt length barely matters.** Typing "continue" costs the same as a
  3,000-word brief, because the whole window reloads either way.
- **Session length is almost the entire bill.**

## Rule 1 — Session ceiling (worth ~59% on its own)

**Hand off at 50 turns / 2 hours / 60% context, whichever comes first. Warn at 35.**

Measured cost per turn, by position in the chat:

| Turn position | Cost | vs. start |
|---|---|---|
| 1–50 | 90,008 | 1.0x |
| 100–150 | 204,493 | 2.3x |
| 200–250 | 295,601 | 3.3x |
| 300–350 | 351,124 | **3.9x** |
| 400+ | ~359,000 | **4.0x** |

By session length: short (<=100 turns) **105,235** per turn; long (>300 turns)
**256,766** per turn. **20 long sessions consumed 70% of all spend.**

Capping every session at 50 turns would have done identical work for **59% less**.

**At the limit, the next message IS the handoff** — not a question, not "shall I
continue". Release claims, write the log, emit the handoff, start fresh.

**Corollary — never resume a big chat after a break.** Returning to a long
conversation is the single most expensive moment to continue: the window is
already at its most bloated. A bare "continue" past the limit produces a handoff.

## Rule 2 — Startup-file ceilings

Anything read at the start of every session has a size cap. Over cap → archive
the history, keep only what is true right now.

Observed failure: a coordination file whose only job was *"who is editing what
right now"* reached **141 KB** and was read **65 times** — roughly **2.3 million
tokens** to answer a one-line question. Its own header contained a "keep last 10"
rule that was never enforced. Eleven such files totalled **~146,000 tokens**,
about three-quarters of a window, before any code was opened.

**Rules of thumb:** contract file <= 200 lines; coordination file <= 8 KB; any
always-read doc <= 15 KB. Work logs are **append-only and never read at session
start** — they are a record for the human, not context for the agent.

## Rule 3 — Load audit

Report what loads before the user types a word. Sum the startup footprint
(`startup_files`) and flag any file over its configured ceiling.

Observed failure: one bundled documentation skill loaded **799,000 characters
(~200,000 tokens)** in a single message, on three separate occasions, in a
project that never needed it. Those three sessions have the worst per-turn cost
in the entire dataset — **435k–498k**, roughly double an already-bad average.

Connected tool servers are the same class of problem: a typical five-server setup
costs **~55,000 tokens before the conversation starts**. Skills are the cheap
alternative — about **100 tokens while dormant**, because they load
progressively: name and description first, body only when triggered, reference
files only if actually needed. `diet.py loadaudit` measures and caps the files
read before every turn.

## Rule 4 — File health

`warn at 500 lines, must-split at 800`.

Every edit to a large file reloads the whole file, and oversized files are also
the most re-read. In the source dataset the six largest files were also the six
most frequently reopened.

**Over the split threshold → the file must be split before new work goes into it.**
Not "eventually" — before.

## Rule 5 — One value, one home

A constant defined in two places is a **defect**, not a style preference. It is
what breaks the promise that changing one module changes the whole app.

Observed failure: one calorie target existing as both `GOALS.cal` and
`FOOD_TARGETS.kcal`; and a type-size scale living privately inside one feature
while a shared design system defined another — which is why two parts of the same
app visibly drifted apart for weeks.

`diet.py dupes` scans source files to detect identical string constants
(length >= 8) defined across two or more distinct files.

## Rule 6 — Sketches, not second builds

Deciding on screen before building is correct and saves real rework. Building the
app twice is not.

Observed failure: a single "wireframe" file of **227 KB**, and **1.34 MB** of
design directions — fully interactive, verified at phone size, overflow-checked.
That is a second implementation, thrown away.

**Caps:** one file per round, **40 KB max**, static only, no working logic and no
verification passes. Round 1: up to 4 directions at thumbnail fidelity. Round 2:
one direction refined. Round 3: build for real. Narrow every round, never widen.

## Rule 7 — Behaviour, not just limits

- **Read line ranges, never whole files.** In the source dataset **45%** of reads
  pulled an entire file when one function was needed, plus **199** redundant
  re-reads of a file already read in the same session.
- **Ask every question in one batch, before writing code.** A wrong assumption
  costs more than any question. Observed rework rate: **16.7%** — one prompt in
  six was a correction.
- **Don't fragment coherent work across subagents.** Usually more expensive and
  worse than keeping it in one session.
- **Plain language.** Nobody reading the output should need to know what a
  token is.

## What did NOT make the cut, and why

**A "prompt coach" that flags vague instructions.** Tempting, but the data
undercut it: of 34 short "continue"-type prompts, **11 were auto-generated by the
tool itself** on resume, not typed by the user. The genuinely useful 10% is
already covered by one line in Rule 1 — *a bare "continue" past the limit
produces a handoff.* A whole subsystem for that would be weight without payoff.

**Keep this skill small enough that people actually use it.**

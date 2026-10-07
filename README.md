# chat-weight

**Long AI chats get expensive. chat-weight tells you when a fresh chat would be cheaper,
and writes the handoff so nothing is lost.**

With every reply, Claude re-reads the whole chat: your messages, the files, its own earlier
answers. In my own Claude Code logs, 99.4% of 11.6 billion tokens went on that re-reading,
and only 0.6% on the code and answers Claude actually wrote. A reply deep into a long chat
cost about 4× one near the start. Run against those same logs, chat-weight's rule would have
done the same work for about 15% fewer tokens. That figure is an estimate, and it already
counts the cost of every fresh chat re-loading what it needs.

## What you get

**1. Chat weight, at the end of every reply**

```
🟩🟩⬜⬜⬜⬜⬜⬜⬜⬜  🟢 chat weight 24% — fresh chat at 60% — all good
🟨🟨🟨🟨⬜⬜⬜⬜⬜⬜  🟡 chat weight 45% — fresh chat at 60% — wrap up soon
🟥🟥🟥🟥🟥🟥⬜⬜⬜⬜  🔴 chat weight 62% — past 60% — start a fresh chat
```

Weight is how much the chat has grown since it started, compared with the point where
starting fresh becomes cheaper. It is not how full the model's memory is: today's big
models can hold a million tokens, and a chat gets expensive long before it fills that.
The terminal also shows the bar at the bottom of the screen, which is free because it
never reaches the AI.

**2. An automatic handoff at 60%**

Claude never stops halfway: an edit and the test that proves it count as one step. Once
that step is done, it saves a short note in your project (`.claude/handoffs/`) and ends its
reply with three lines to paste into a new chat:

```
Continuing: add search to the recipes page
Note: /home/you/project/.claude/handoffs/2026-10-01-recipe-search.md
Read that note and start at section 4, item 1. Claude Code · middle level (sonnet) · Medium.
```

The note covers what is done, what's next, what was decided, and which model fits the next
step. The rules it follows are in [`reference/handoff.md`](reference/handoff.md). You can
also ask for a handoff at any time: "write a handoff".

**3. A usage report, when you want one**

Ask Claude "where did my tokens go?", or run `python scripts/audit.py` (add `--all` for
every project). It reads Claude Code's own logs on your machine, and nothing is uploaded.

## How the 60% point is worked out

Each chat gets its own numbers, worked out when the chat starts and then kept fixed for
that chat:

- **Start size:** what the chat holds before you've done anything (instructions, tools,
  project files). This isn't counted.
- **Restart cost:** what a fresh chat must re-load to carry on (the note plus the files it
  needs). On day one this is a sensible 30k tokens. Each time you start a chat from a
  handoff's paste block, chat-weight measures what that chat loaded before its first edit
  and keeps the last 20 such numbers. From the third one on, it uses their middle value,
  kept between 10k and 90k so one odd chat can't throw it off. It keeps learning for as long
  as you use it.
- **The fresh-chat point:** when the chat has grown by 4× the restart cost. Across 698 real
  chats, 4× was the middle ground: nearly the savings of handing off sooner, with half as
  many new chats. A model with a small memory hands off earlier, never past 70% of that
  memory.

The bar reads 60% at that point. The last 40% is room to finish what you're doing.

## Where it works

One skill, and Claude works out on its own where it is running.

**Claude Code** — terminal and desktop app, using the same install:

- **Terminal (`claude`):** the bar shows at the end of every reply and in the status line at
  the bottom of the screen.
- **Claude desktop app (Code tab), and any other window with no status line:** the bar shows
  at the end of every reply. The handoff works the same way.

Each message costs about 0.2 seconds of local work, even on a 65 MB chat log.

**Normal chats** — claude.ai on the web, the desktop app's chat, the phone apps. A chat has no
hooks and no log to read, so nothing measures it. Claude keeps the count itself:

- The same bar ends every reply, marked `≈` because it is counted, not measured:
  `🟩🟩🟩⬜⬜⬜⬜⬜⬜⬜  🟢 chat weight ≈30% — fresh chat at 60% — all good`
- It is a running tally. Each reply reads the last bar's number and adds what that turn cost
  (1% ≈ 2,000 tokens): +1 for a normal message and reply, more for long replies, pasted text,
  files, images and web searches. So the bar moves steadily and never jumps back.
- 60% is the same point as in Claude Code: about 120,000 tokens of growth.
- At 60% Claude finishes its step and writes the handoff once. The note comes in the reply, in
  one block you copy into a new chat (a chat can't save files on your computer), and it names
  the old chat so the new one can look back at it.
- The usage report needs Claude Code's logs, so it is Claude Code only.

The rules Claude follows in a chat are in [`reference/chat-mode.md`](reference/chat-mode.md).

## Install

You need Claude Code, git and Python 3.8 or newer.

**Mac / Linux**

```bash
git clone https://github.com/adarsh733/chat-weight ~/.claude/skills/chat-weight
python3 ~/.claude/skills/chat-weight/install.py
```

**Windows (PowerShell)**

```powershell
git clone https://github.com/adarsh733/chat-weight "$HOME\.claude\skills\chat-weight"
python "$HOME\.claude\skills\chat-weight\install.py"
```

Then open a new chat. That's it.

**Normal chats (claude.ai and the Claude apps)**

```bash
python scripts/package.py
```

This makes `dist/chat-weight.zip`. Upload it where skills are added in the Claude app's
settings. Nothing else to set up. To update, make a new zip and upload it again in place of the
old one.

**Or ask Claude to do it.** Paste this into Claude Code:

> Install chat-weight from https://github.com/adarsh733/chat-weight — follow the "For AI
> assistants" steps in its README.

### For AI assistants installing this

1. Find a working Python 3.8+ (`python3 --version`, else `python --version`, else `py -3 --version`).
2. Clone into the user's home folder, exactly here: `<home>/.claude/skills/chat-weight`. If
   that folder already exists, run `git pull` inside it instead.
3. Run `install.py` from that folder with that same Python. Do not edit
   `~/.claude/settings.json` by hand; the installer backs it up, changes only its own two
   entries, and undoes itself if anything goes wrong. Show the user what it printed.
4. Tell the user to open a new chat. The bar appears at the end of the next reply.

The installer adds two entries to `~/.claude/settings.json`: the status bar, and one hook
that runs when you send a message. It touches nothing else. It saves a backup first,
checks the result, and puts the backup back if anything looks wrong.

If you already have a status line, it stays: the bar still shows at the end of every reply.
To show chat-weight's bar there instead, run `python install.py --statusline`, and
`--uninstall` will give yours back.

In the terminal's bar the empty squares are 🔳, because many terminal fonts draw ⬜ small and
hollow. If yours draws ⬜ well, set `"statusline_empty": "⬜"` in your config.

- Preview without changing anything: `python install.py --dry-run`
- Remove it: `python install.py --uninstall` (your old status bar comes back if you had one)
- Upgrading: say "update chat-weight" to Claude, or run `git pull` in this folder and then
  `install.py` again. Old entries are cleaned up.
- Moved or upgraded Python? Run `install.py` again so the hook points at the new one.
- To remove every trace: uninstall, then delete this folder and chat-weight's small notes
  folder, `~/.claude/chat-weight/`. Notes from chats older than 30 days are cleared
  automatically while it is installed.

## Change the settings

Create `~/.claude/chat-weight/config.json` containing only what you want to change, for
example to hand off later:

```json
{ "restart_multiple": 6 }
```

For a single project, put it in `<project>/.claude/chat-weight.json` instead. Every setting
is explained in [`config.json`](config.json).

To give a project its own handoff rules (for example "also update the changelog"), write
them in `<project>/.claude/handoff-extra.md`.

If a project sits inside a bigger folder that should own the notes and rules, point it
there from `<project>/.claude/chat-weight.json`:

```json
{ "handoff_folder": "../.claude/handoffs", "handoff_extra": "../.claude/handoff-extra.md" }
```

## How new models are handled

A handoff names a **level**, not just a model:

- **top:** thinking, planning, reviewing
- **middle:** building something already agreed
- **small:** routine work

In Claude Code it uses the short names `opus`, `sonnet` and `haiku`. Claude Code always
points these at the newest model of each kind, so nothing needs updating. For other tools,
add their model names to the `models` section of your config. If that list is more than
3 months old, the handoff adds "(or newer)".

A handoff never names a version number like "Opus 5": that is out of date the day a newer
model ships. The level comes first, in words, so the note still reads right when a whole
new model family appears. If your project's own handoff rules (`handoff_extra`, or a file it
links to) pin a version, the handoff uses the level instead and tells you which file to fix.

## Updates

Once a day, in the background, chat-weight downloads one small public file (`VERSION`) from
this GitHub page to see if a newer version is out. Nothing about you is sent, and your chat
never waits for it. If there is a newer version, Claude adds one line to a reply, once per
chat:

```
A chat-weight update is available — say "update chat-weight".
```

Say it, and Claude runs `python scripts/updates.py --apply`: `git pull` in this folder, then
`install.py` again. It never updates by itself. That is on purpose: if this GitHub account
were ever taken over, silent updates would put bad code on every machine without anyone
noticing. To see where you stand, run `python scripts/updates.py --status`. To stop the
check, set `"check_for_updates": false` in your config.

## Honest limits

- chat-weight acts when you send a message. One message that starts a very long run can
  grow past 60% before it gets a chance to speak.
- The 15% is counted in tokens. Claude caches re-read text and charges less for it, so the
  effect on your plan's limit may be smaller.
- The bar at the end of each reply is itself a few dozen tokens per reply. That is small
  next to what it saves, but it is not zero.
- Only Claude Code is measured. In a normal chat the weight is Claude's own count, so it can be
  off by about a quarter either way, more in chats full of big files.
- chat-weight reads Claude Code's own chat log. If a future Claude Code changes that log's
  format, the bar does not show a wrong number: it says it is paused, once, and asks you to
  update chat-weight.

## License

MIT. See [LICENSE](LICENSE).

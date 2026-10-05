# token-diet

**Long AI chats get expensive. token-diet tells you when a fresh chat would be cheaper,
and writes the handoff so nothing is lost.**

With every reply, Claude re-reads the whole chat: your messages, the files, its own earlier
answers. In my own Claude Code logs, 99.4% of 11.6 billion tokens went on that re-reading,
and only 0.6% on the code and answers Claude actually wrote. A reply deep into a long chat
cost about 4× one near the start. Run against those same logs, token-diet's rule would have
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
Read that note and start at section 4, item 1. Claude Code · sonnet · Medium.
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
  handoff's paste block, token-diet measures what that chat loaded before its first edit
  and keeps the last 20 such numbers. From the third one on, it uses their middle value,
  kept between 10k and 90k so one odd chat can't throw it off. It keeps learning for as long
  as you use it.
- **The fresh-chat point:** when the chat has grown by 4× the restart cost. Across 698 real
  chats, 4× was the middle ground: nearly the savings of handing off sooner, with half as
  many new chats. A model with a small memory hands off earlier, never past 70% of that
  memory.

The bar reads 60% at that point. The last 40% is room to finish what you're doing.

## Terminal and desktop app

Both work, using the same install.

- **Terminal (`claude`):** the bar shows at the end of every reply and in the status line at
  the bottom of the screen.
- **Claude desktop app (Code tab), and any other window with no status line:** the bar shows
  at the end of every reply. The handoff works the same way.

Each message costs about 0.2 seconds of local work, even on a 65 MB chat log.

## Install

You need Claude Code, git and Python 3.8 or newer.

**Mac / Linux**

```bash
git clone https://github.com/adarsh733/token-diet ~/.claude/skills/token-diet
python3 ~/.claude/skills/token-diet/install.py
```

**Windows (PowerShell)**

```powershell
git clone https://github.com/adarsh733/token-diet "$HOME\.claude\skills\token-diet"
python "$HOME\.claude\skills\token-diet\install.py"
```

Then open a new chat. That's it.

**Or ask Claude to do it.** Paste this into Claude Code:

> Install token-diet from https://github.com/adarsh733/token-diet — follow the "For AI
> assistants" steps in its README.

### For AI assistants installing this

1. Find a working Python 3.8+ (`python3 --version`, else `python --version`, else `py -3 --version`).
2. Clone into the user's home folder, exactly here: `<home>/.claude/skills/token-diet`. If
   that folder already exists, run `git pull` inside it instead.
3. Run `install.py` from that folder with that same Python. Do not edit
   `~/.claude/settings.json` by hand; the installer backs it up, changes only its own two
   entries, and undoes itself if anything goes wrong. Show the user what it printed.
4. Tell the user to open a new chat. The bar appears at the end of the next reply.

The installer adds two entries to `~/.claude/settings.json`: the status bar, and one hook
that runs when you send a message. It touches nothing else. It saves a backup first,
checks the result, and puts the backup back if anything looks wrong.

If you already have a status line, it stays: the bar still shows at the end of every reply.
To show token-diet's bar there instead, run `python install.py --statusline`, and
`--uninstall` will give yours back.

- Preview without changing anything: `python install.py --dry-run`
- Remove it: `python install.py --uninstall` (your old status bar comes back if you had one)
- Upgrading: `git pull` in this folder, then run `install.py` again. Old entries are cleaned up.
- Moved or upgraded Python? Run `install.py` again so the hook points at the new one.
- To remove every trace: uninstall, then delete this folder and token-diet's small notes
  folder, `~/.claude/token-diet/`. Notes from chats older than 30 days are cleared
  automatically while it is installed.

## Change the settings

Create `~/.claude/token-diet/config.json` containing only what you want to change, for
example to hand off later:

```json
{ "restart_multiple": 6 }
```

For a single project, put it in `<project>/.claude/token-diet.json` instead. Every setting
is explained in [`config.json`](config.json).

To give a project its own handoff rules (for example "also update the changelog"), write
them in `<project>/.claude/handoff-extra.md`.

If a project sits inside a bigger folder that should own the notes and rules, point it
there from `<project>/.claude/token-diet.json`:

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

## Honest limits

- token-diet acts when you send a message. One message that starts a very long run can
  grow past 60% before it gets a chance to speak.
- The 15% is counted in tokens. Claude caches re-read text and charges less for it, so the
  effect on your plan's limit may be smaller.
- The bar at the end of each reply is itself a few dozen tokens per reply. That is small
  next to what it saves, but it is not zero.
- Only Claude Code is measured today.
- token-diet reads Claude Code's own chat log. If a future Claude Code changes that log's
  format, the bar does not show a wrong number: it says it is paused, once, and asks you to
  update token-diet.

## License

MIT. See [LICENSE](LICENSE).

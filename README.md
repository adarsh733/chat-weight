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

**1. Chat weight, once, under every reply**

```
🟩🟩⬜⬜⬜⬜⬜⬜⬜⬜  🟢 chat weight 24% — fresh chat at 60% — all good
🟨🟨🟨🟨⬜⬜⬜⬜⬜⬜  🟡 chat weight 45% — fresh chat at 60% — wrap up soon
🟥🟥🟥🟥🟥🟥⬜⬜⬜⬜  🔴 chat weight 62% — past 60% — start a fresh chat
```

Weight is how much the chat has grown since it started, compared with the point where
starting fresh becomes cheaper. It is measured once, after Claude has finished the reply,
so it includes everything that reply did, however many steps it took. In Claude Code the
bar is shown by Claude Code itself, not written by the AI, so it costs no tokens at all. It is not how full the model's memory is: today's big
models can hold a million tokens, and a chat gets expensive long before it fills that.
The terminal also shows the bar at the bottom of the screen, which is free because it
never reaches the AI.

**2. An automatic handoff at 60%**

This works mid-task too: if one long task crosses 60%, the request arrives while Claude is
working. Claude never stops halfway: an edit and the test that proves it count as one step. Once
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

- **Terminal (`claude`):** the bar shows once under every reply, and in the status line at
  the bottom of the screen.
- **Claude desktop app (Code tab), and any other window with no status line:** the bar shows
  once under every reply. The handoff works the same way.

Each check costs about 0.1–0.2 seconds of local work, even on a 65 MB chat log. During a long
task it also checks quietly after each step, only so a handoff can start the moment the 60%
line is crossed; it shows nothing until the reply is done.

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
- It needs **Code execution and file creation** switched on (Settings → Capabilities):
  Claude uses uploaded skills only with it.

The rules Claude follows in a chat are in [`reference/chat-mode.md`](reference/chat-mode.md).

## Install

For Claude Code you need git and Python 3.8 or newer.

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

Then **open a new chat to see the bar**. Chats that were already open, including the one
you installed from, may not show it.

On Mac and Linux, wherever this page says `python`, type `python3`.

**Normal chats (claude.ai and the Claude apps)**

No Python or git needed. Do this once, on a computer (claude.ai in a browser, or the Claude
desktop app); it then works in the new chats you open on that account.

1. **Download** [chat-weight.zip](https://github.com/adarsh733/chat-weight/releases/latest/download/chat-weight.zip).
   Keep it zipped: Claude wants the `.zip` itself. (On a Mac, if Safari unzips it for you,
   right-click the `chat-weight` folder → Compress to get the zip back.)
2. **Turn on code execution.** Go to **Settings → Capabilities** and switch on
   **Code execution and file creation**. Skills don't work without it. On a Team or
   Enterprise plan, your organisation's owner must allow skills first.
3. **Upload it.** Go to **Customize → Skills** (or open
   [claude.ai/customize/skills](https://claude.ai/customize/skills)). Click **+**, then
   **Create skill**, then **Upload a skill**, and pick `chat-weight.zip`.
4. **Check it is on.** chat-weight now shows in your skills list. Make sure its switch is on.
5. **Make it load in every chat.** Claude only opens a skill when it thinks the chat needs it,
   so a plain "hi" may not wake it up. Go to **Settings → Profile** and paste this line into
   **"What personal preferences should Claude consider in responses?"**:

   > At the start of every chat, load my chat-weight skill and end every reply with its bar.

   This is the step that makes it automatic. It applies to every new chat on your account.
6. **Open a new chat.** Chats that were already open don't pick it up. Send any message:
   the reply ends with the bar, starting near 0%:
   `🟩⬜⬜⬜⬜⬜⬜⬜⬜⬜  🟢 chat weight ≈1% — fresh chat at 60% — all good`

No bar? Check that the switch from step 4 is on, the line from step 5 is saved, and code
execution is on, then try a new chat. You can also ask "how heavy is this chat?" to wake it
up.

**To update:** download the zip again, then in Customize → Skills open chat-weight, use its
**...** menu to delete it, and upload the new zip. The new version starts in your next new
chat. To build the zip yourself from this folder, run `python scripts/package.py` (it makes
`dist/chat-weight.zip`).

**Hear about new versions:** zip uploads can't check for updates themselves. On this GitHub
page, click **Watch → Custom → Releases** and GitHub emails you when a new version is out.
Ask Claude "which version of chat-weight is this?" to compare.

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
4. Tell the user plainly, on its own line: "Open a new chat to see the bar." Chats that were
   already open, including this one, may not show it.

The installer adds its own entries to `~/.claude/settings.json`: the status bar, and one
small script that runs when Claude finishes a reply, after each step it takes, and when you
send a message. It touches nothing else. It saves a backup first,
checks the result, and puts the backup back if anything looks wrong.

If you already have a status line, it stays: the bar still shows once under every reply.
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
this GitHub page to see if a newer version is out. Nothing about you is sent: it is a plain
download, like opening a web page. Your chat never waits for it. If there is a newer version, Claude adds one line to a reply, once per
chat:

```
A chat-weight update is available — say "update chat-weight".
```

Say it, and Claude runs `python scripts/updates.py --apply`: `git pull` in this folder, then
`install.py` again. Open a new chat to use the new version. Updating takes one word from
you, and you always get the newest version. It never updates by itself. That is on purpose:
if this GitHub account were ever taken over, silent updates would put bad code on every
machine without anyone noticing. To see where you stand, run `python scripts/updates.py --status`. To stop the
check, set `"check_for_updates": false` in your config.

## Honest limits

- The 15% is counted in tokens. Claude caches re-read text and charges less for it, so the
  effect on your plan's limit may be smaller.
- In a normal chat the bar is written by Claude, so it is a few dozen tokens per reply. In
  Claude Code it costs nothing.
- In a normal chat, Claude itself decides when to open a skill. Without the line in step 5
  of the normal-chat install, it may wait until you mention chat weight. Even with it,
  Claude can occasionally miss a bar; ask "how heavy is this chat?" and it comes back.
- Only Claude Code is measured. In a normal chat the weight is Claude's own count, so it can be
  off by about a quarter either way, more in chats full of big files.
- chat-weight reads Claude Code's own chat log. If a future Claude Code changes that log's
  format, the bar does not show a wrong number: it says it is paused, once, and asks you to
  update chat-weight.

## License

MIT. See [LICENSE](LICENSE).

# Token Diet

Keep your chats fast and save money without changing how you work.

Claude chats get slower and more expensive the longer they run. Token Diet works quietly in the background so you can focus on building. It monitors session size, warns you before chats become heavy, and keeps your project clean.

## How to install

**Run this single command from the token-diet folder:**

```bash
python install.py
```

**Do NOT hand-edit `~/.claude/settings.json`.**
**Do not let an AI assistant "figure out" the install — run the single command above with no exploration.**

To preview changes before applying them, run:
```bash
python install.py --dry-run
```

To remove Token Diet at any time, run:
```bash
python install.py --uninstall
```

## What this changes on your machine

Token Diet safely updates only four specific entries in `~/.claude/settings.json`:
1. `statusLine` — points to the lightweight local status display (`scripts/statusline.py`). If you already had a custom status line, it is preserved under `_tokenDietPreviousStatusLine`.
2. `hooks.UserPromptSubmit` — adds the session guard reminder (`hooks/session_guard.py`).
3. `hooks.SessionStart` — adds the weekly startup summary (`hooks/savings_note.py`).
4. `hooks.Stop` — adds the fuel-gauge bar drawn after each reply (`hooks/usage_meter.py`).

**All other settings (`env`, `permissions`, `model`, `apiKeyHelper`, company auth, and unrelated custom hooks) are left untouched and preserved byte-identical.**

## If Claude Code shows a Settings Error after install

Before making any changes, the installer creates an automatic timestamped backup: `~/.claude/settings.json.token-diet-backup-<YYYYMMDD-HHMMSS>`.

If you ever need to restore your settings:

1. **PowerShell:**
   ```powershell
   Copy-Item ~/.claude/settings.json.token-diet-backup-<TIMESTAMP> ~/.claude/settings.json -Force
   ```

2. **Bash / macOS / Linux:**
   ```bash
   cp ~/.claude/settings.json.token-diet-backup-<TIMESTAMP> ~/.claude/settings.json
   ```

3. **Or run the uninstaller:**
   ```bash
   python install.py --uninstall
   ```

## What it does

- **Live fuel bar:** A coloured bar (green → yellow → red) appears after each reply showing how full the chat is — updated the moment a message finishes, so it always reflects what you have actually used.
- **Smart reminders:** Gently lets you know when it is a great time to start a fresh chat to keep speeds high and costs low.
- **Automatic tidy-up:** Trims finished checklist items and archives old working notes safely.
- **Code indexing:** Generates a lightweight map of your project files so searches stay fast and lean.

## License

MIT License. See [LICENSE](LICENSE) for details.

---

<sub>Made after hours. Built by the **After Hours** team.</sub>

#!/usr/bin/env python3
"""Installer for chat-weight.

Adds two things to ~/.claude/settings.json: the status line, and one small script that
runs when Claude finishes a reply, after each step it takes, and when you send a message.
Backs the file up first, touches nothing else, checks the result and puts the backup back
if anything is wrong.

    python install.py             install (or upgrade)
    python install.py --dry-run   show the change, write nothing
    python install.py --uninstall remove chat-weight, restore your old status line
    python install.py --statusline  use chat-weight's status line even if you have one
"""
import argparse
import copy
from datetime import datetime
import difflib
import json
import os
import shutil
import sys

ROOT = os.path.normpath(os.path.dirname(os.path.abspath(__file__)))
PY = "python" if os.name == "nt" else "python3"     # what to tell the user to type


def get_settings_path():
    return os.path.normpath(os.path.expanduser("~/.claude/settings.json"))


def load_settings(path):
    if not os.path.exists(path):
        return {}
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception as err:
            print(f"Error: Could not read your settings file at {path}")
            print(f"Details: {err}")
            print("Nothing was changed.")
            sys.exit(1)
    return {}


def create_backup(path):
    if not os.path.isfile(path):
        return None
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = f"{path}.chat-weight-backup-{timestamp}"
    try:
        shutil.copy2(path, backup_path)
    except Exception as err:
        print(f"Error: Could not create backup file at {backup_path}")
        print(f"Details: {err}")
        print("Nothing was changed.")
        sys.exit(1)

    print(f"Backup created: {backup_path}")
    print("To restore your previous settings if needed:")
    print(f'  PowerShell: Copy-Item "{backup_path}" "{path}" -Force')
    print(f'  Bash:       cp "{backup_path}" "{path}"')
    return backup_path


def restore_backup(backup_path, target_path):
    if backup_path and os.path.isfile(backup_path):
        try:
            shutil.copy2(backup_path, target_path)
        except Exception as err:
            print(f"Warning: Failed to restore backup from {backup_path}: {err}")


def save_settings(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


OURS = ("on_prompt.py",)
KEY = "_chatWeightPreviousStatusLine"


def _from_us(command):
    """True when a command runs a script from a chat-weight folder. A script name alone is
    not proof: other tools ship their own on_prompt.py and statusline.py."""
    command = str(command or "").replace("\\", "/").lower()
    return ("chat-weight" in command
            or ROOT.replace("\\", "/").lower() in command)


def hook_text(h):
    """Everything a hook entry runs, whether written as one command line or as
    command + args (exec form)."""
    if not isinstance(h, dict):
        return ""
    args = h.get("args") if isinstance(h.get("args"), list) else []
    return " ".join(str(x) for x in [h.get("command") or ""] + args)


def is_ours(h):
    """A hook entry that belongs to chat-weight: this install, or one from a moved folder."""
    text = hook_text(h)
    return _from_us(text) and any(s in text for s in OURS)


# ------------------------------------------------------------ running Python

ARGS_SINCE = (2, 1, 139)    # first Claude Code that runs hooks in exec form (no shell)


def pick_python():
    """The Python running this installer, as a path Claude Code can start.

    The Microsoft Store Python reports a path inside "C:/Program Files/WindowsApps",
    which other programs may not be allowed to start; its user-level shortcut in
    AppData works everywhere, so that is used when it exists."""
    exe = sys.executable
    if os.name == "nt" and "\\program files\\windowsapps\\" in exe.lower():
        apps = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WindowsApps")
        for name in ("python%d.%d.exe" % sys.version_info[:2], "python3.exe", "python.exe"):
            if os.path.isfile(os.path.join(apps, name)):
                exe = os.path.join(apps, name)
                break
    return exe.replace("\\", "/")      # forward slashes: Git Bash eats backslashes


def no_spaces(path):
    """On Windows, the space-free short form of a path when one exists, so one command
    line works the same in Git Bash, PowerShell and cmd. Elsewhere, unchanged."""
    if os.name != "nt" or " " not in path:
        return path
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetShortPathNameW(path, buf, 1024):
            return buf.value.replace("\\", "/")
    except Exception:
        pass
    return path


def command_line(python_bin, script):
    """One line any shell can run: bare paths when they have no spaces, quoted otherwise."""
    parts = [no_spaces(python_bin), no_spaces(script)]
    return " ".join(('"%s"' % x) if " " in x else x for x in parts)


def claude_runs_exec_form():
    """True unless the installed Claude Code is older than ARGS_SINCE. If Claude Code
    can't be found from here, assume a current one."""
    try:
        import re
        import subprocess
        out = subprocess.run("claude --version", shell=True, capture_output=True,
                             text=True, timeout=20).stdout
        m = re.search(r"(\d+)\.(\d+)\.(\d+)", out or "")
        return not m or tuple(int(x) for x in m.groups()) >= ARGS_SINCE
    except Exception:
        return True


def hook_entry(python_bin, prompt_script, exec_form):
    if exec_form:   # no shell at all: spaces, quotes and PowerShell can't break it
        return {"type": "command", "command": python_bin, "args": [prompt_script], "timeout": 10}
    return {"type": "command", "command": command_line(python_bin, prompt_script), "timeout": 10}


def self_test(python_bin, prompt_script, statusline_script):
    """Start both scripts the way Claude Code will, before anything is written."""
    import subprocess
    for script in (prompt_script, statusline_script):
        try:
            r = subprocess.run([python_bin, script], input=b"{}", capture_output=True, timeout=30)
            if r.returncode != 0:
                return "%s exited with %d: %s" % (os.path.basename(script), r.returncode,
                                                  r.stderr.decode("utf-8", "replace")[:300])
        except Exception as err:
            return "could not start %s with %s: %s" % (os.path.basename(script), python_bin, err)
    return ""


def is_our_statusline(value):
    return isinstance(value, dict) and "statusline.py" in str(value.get("command") or "") \
        and _from_us(value.get("command"))


def extract_unrelated_state(data):
    """Capture all keys and hooks not owned by chat-weight."""
    unrelated_top = {
        k: copy.deepcopy(v) for k, v in data.items()
        if k not in ("statusLine", "hooks", KEY)
    }
    unrelated_hooks = {}
    if "hooks" in data and isinstance(data["hooks"], dict):
        for event, hook_items in data["hooks"].items():
            if not isinstance(hook_items, list):
                unrelated_hooks[event] = copy.deepcopy(hook_items)
                continue
            filtered = []
            for item in hook_items:
                item_copy = copy.deepcopy(item)
                if isinstance(item_copy, dict) and isinstance(item_copy.get("hooks"), list):
                    item_copy["hooks"] = [h for h in item_copy["hooks"]
                                          if not is_ours(h)]
                    if item_copy["hooks"]:
                        filtered.append(item_copy)
                elif not is_ours(item_copy):
                    filtered.append(item_copy)
            if filtered:
                unrelated_hooks[event] = filtered
    return unrelated_top, unrelated_hooks


def assert_unrelated_intact(data, unrelated_top, unrelated_hooks):
    for k, v in unrelated_top.items():
        assert k in data, f"Unrelated setting key '{k}' was lost."
        assert data[k] == v, f"Unrelated setting key '{k}' was modified."

    if unrelated_hooks:
        assert "hooks" in data and isinstance(data["hooks"], dict), "Hooks dictionary was lost."
        for event, items in unrelated_hooks.items():
            assert event in data["hooks"], f"Hook event '{event}' was lost."
            for item in items:
                assert item in data["hooks"][event] or any(
                    isinstance(x, dict) and x.get("matcher") == item.get("matcher")
                    for x in data["hooks"][event]
                ), f"Unrelated hook in '{event}' was lost or changed."


def verify_written_file(path, unrelated_top, unrelated_hooks, is_uninstall=False):
    with open(path, "r", encoding="utf-8") as fh:
        reloaded = json.load(fh)

    if not is_uninstall:
        assert isinstance(reloaded.get("statusLine"), dict), "statusLine must be a dictionary object."
        assert "type" in reloaded["statusLine"], "statusLine must have a 'type' field."
        assert "command" in reloaded["statusLine"], "statusLine must have a 'command' field."

    assert_unrelated_intact(reloaded, unrelated_top, unrelated_hooks)
    return True


def strip_ours(data):
    """Remove every chat-weight hook entry (this version and older ones); drop empty events."""
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return
    for event in list(hooks):
        items = hooks[event]
        if not isinstance(items, list):
            continue
        kept = []
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("hooks"), list):
                item["hooks"] = [h for h in item["hooks"] if not is_ours(h)]
                if item["hooks"]:
                    kept.append(item)
            elif not is_ours(item):
                kept.append(item)
        hooks[event] = kept
        if not kept:
            del hooks[event]
    if not hooks:
        del data["hooks"]


def apply_install(data, python_bin, statusline_script, prompt_script, take_statusline=False,
                  exec_form=True):
    # 1. statusLine. A working one that belongs to someone else stays, unless the user
    #    asks for ours (--statusline); the bar still shows under every reply.
    statusline_cmd = command_line(python_bin, statusline_script)
    existing = data.get("statusLine")
    theirs_works = isinstance(existing, dict) and bool(existing.get("command")) \
        and not is_our_statusline(existing)
    if is_our_statusline(existing):
        existing["type"] = "command"
        existing["command"] = statusline_cmd
    elif theirs_works and not take_statusline:
        print("You already have a status line, so it stays as it is. The chat-weight bar")
        print("still shows under every reply. To show it in the status line instead,")
        print("run: %s install.py --statusline" % PY)
    else:
        if existing is not None:
            print("Saved your old status line under '_chatWeightPreviousStatusLine'; "
                  "--uninstall puts it back.")
            data[KEY] = existing
        data["statusLine"] = {"type": "command", "command": statusline_cmd}

    # 2. one script, at three moments: when Claude finishes a reply (the bar, measured after
    #    the work), after each step during a long run (the handoff, if the line is crossed),
    #    and when the user sends a message (handoff reminders)
    strip_ours(data)
    if not isinstance(data.get("hooks"), dict):
        data["hooks"] = {}
    for event, matcher in (("Stop", None), ("PostToolUse", "*"), ("UserPromptSubmit", None)):
        item = {"hooks": [hook_entry(python_bin, prompt_script, exec_form)]}
        if matcher:
            item = dict({"matcher": matcher}, **item)
        data["hooks"].setdefault(event, []).append(item)


def apply_uninstall(data):
    if KEY in data:
        data["statusLine"] = data.pop(KEY)
        print("Restored previous statusLine configuration.")
    elif is_our_statusline(data.get("statusLine")):
        del data["statusLine"]
        print("Removed chat-weight statusLine.")
    strip_ours(data)


def main():
    parser = argparse.ArgumentParser(description="Installer and manager for chat-weight.")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without modifying settings.json")
    parser.add_argument("--uninstall", action="store_true", help="Remove chat-weight from settings.json")
    parser.add_argument("--statusline", action="store_true",
                        help="Show the bar in the status line even if you already have one (yours is kept for --uninstall)")
    args = parser.parse_args()

    settings_path = get_settings_path()
    python_bin = pick_python()
    statusline_script = os.path.normpath(os.path.join(ROOT, "scripts", "statusline.py")).replace("\\", "/")
    prompt_script = os.path.normpath(os.path.join(ROOT, "hooks", "on_prompt.py")).replace("\\", "/")

    if args.uninstall and not os.path.exists(settings_path):
        print(f"No settings file found at {settings_path}. Nothing to uninstall.")
        return

    original_data = load_settings(settings_path)
    working_data = copy.deepcopy(original_data)
    unrelated_top, unrelated_hooks = extract_unrelated_state(working_data)

    if args.uninstall:
        apply_uninstall(working_data)
    else:
        problem = self_test(python_bin, prompt_script, statusline_script)
        if problem:
            print("Stopped before changing anything: chat-weight's scripts did not run.")
            print("Details: " + problem)
            print("Nothing was changed. Try running install.py with another Python 3.8 or newer.")
            sys.exit(1)
        apply_install(working_data, python_bin, statusline_script, prompt_script,
                      args.statusline, claude_runs_exec_form())

    assert_unrelated_intact(working_data, unrelated_top, unrelated_hooks)

    if args.dry_run:
        orig_str = json.dumps(original_data, indent=2, ensure_ascii=False) + "\n"
        new_str = json.dumps(working_data, indent=2, ensure_ascii=False) + "\n"
        diff = list(difflib.unified_diff(
            orig_str.splitlines(keepends=True),
            new_str.splitlines(keepends=True),
            fromfile=f"{settings_path} (current)",
            tofile=f"{settings_path} (proposed)"
        ))
        if diff:
            print("".join(diff))
        else:
            print("No changes required.")
        print("[Dry Run] No files were modified.")
        return

    backup_path = create_backup(settings_path)

    try:
        save_settings(settings_path, working_data)
        verify_written_file(settings_path, unrelated_top, unrelated_hooks, is_uninstall=args.uninstall)
    except Exception as err:
        print(f"Error during verification: {err}")
        if backup_path:
            restore_backup(backup_path, settings_path)
        elif not original_data and os.path.isfile(settings_path):
            os.remove(settings_path)        # there was no settings file before us
        print("Install rolled back — your settings are unchanged.")
        sys.exit(1)

    if args.uninstall:
        print("Uninstall complete. chat-weight has been removed from your settings.")
        print("Chats that are already open may keep showing the bar until you start a new one.")
        print(f"Updated configuration in: {settings_path}")
    else:
        print("Setup complete.")
        print("")
        print("  >>> OPEN A NEW CHAT TO SEE THE BAR. <<<")
        print("")
        print("Chats that are already open, including the one you ran this from, may not show")
        print("it. In the new chat the bar appears under each reply, and at 60% weight")
        print("Claude writes a handoff note and gives you three lines to paste into a fresh chat.")
        print(f"Updated configuration in: {settings_path}")


if __name__ == "__main__":
    main()


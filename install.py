#!/usr/bin/env python3
"""Installer for token-diet.

Configures Claude settings to wire up status line and hooks safely.
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
    backup_path = f"{path}.token-diet-backup-{timestamp}"
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


def update_hook_list(hook_list, script_name, hook_entry_builder):
    """Ensure a hook referencing script_name exists in hook_list exactly once, updating if present."""
    found = False
    for item in hook_list:
        if isinstance(item, dict):
            inner_hooks = item.get("hooks", [])
            for h in inner_hooks:
                if isinstance(h, dict) and script_name in h.get("command", ""):
                    found = True
                    h["command"] = hook_entry_builder()["hooks"][0]["command"]
                    break
            if not found and script_name in item.get("command", ""):
                found = True
                item["command"] = hook_entry_builder()["hooks"][0]["command"]
                break
        if found:
            break

    if not found:
        hook_list.append(hook_entry_builder())


def remove_hook_from_list(hook_list, script_name):
    """Remove any hook entries that reference script_name."""
    indices_to_remove = []
    for idx, item in enumerate(hook_list):
        if isinstance(item, dict):
            if "hooks" in item and isinstance(item["hooks"], list):
                item["hooks"] = [
                    h for h in item["hooks"]
                    if not (isinstance(h, dict) and script_name in h.get("command", ""))
                ]
                if len(item["hooks"]) == 0:
                    indices_to_remove.append(idx)
            elif script_name in item.get("command", ""):
                indices_to_remove.append(idx)

    for idx in reversed(indices_to_remove):
        hook_list.pop(idx)


def extract_unrelated_state(data):
    """Capture all keys and hooks not owned by token-diet."""
    unrelated_top = {
        k: copy.deepcopy(v) for k, v in data.items()
        if k not in ("statusLine", "hooks", "_tokenDietPreviousStatusLine")
    }
    unrelated_hooks = {}
    if "hooks" in data and isinstance(data["hooks"], dict):
        for event, hook_items in data["hooks"].items():
            if event not in ("UserPromptSubmit", "SessionStart", "Stop"):
                unrelated_hooks[event] = copy.deepcopy(hook_items)
            elif isinstance(hook_items, list):
                filtered = []
                for item in hook_items:
                    item_copy = copy.deepcopy(item)
                    if isinstance(item_copy, dict):
                        if "hooks" in item_copy and isinstance(item_copy["hooks"], list):
                            item_copy["hooks"] = [
                                h for h in item_copy["hooks"]
                                if not (isinstance(h, dict) and any(
                                    s in h.get("command", "") for s in ("session_guard.py", "savings_note.py", "usage_meter.py")
                                ))
                            ]
                            if len(item_copy["hooks"]) > 0:
                                filtered.append(item_copy)
                        elif not any(s in item_copy.get("command", "") for s in ("session_guard.py", "savings_note.py", "usage_meter.py")):
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


def apply_install(data, python_bin, statusline_script, session_guard_script, savings_note_script, usage_meter_script):
    # 1. statusLine
    statusline_cmd = f'"{python_bin}" "{statusline_script}"'
    existing_status = data.get("statusLine")
    if existing_status is not None:
        is_our_dict = (
            isinstance(existing_status, dict)
            and "statusline.py" in existing_status.get("command", "")
        )
        if not is_our_dict:
            print("Found existing statusLine configuration. Preserved it under '_tokenDietPreviousStatusLine'.")
            data["_tokenDietPreviousStatusLine"] = existing_status

    data["statusLine"] = {
        "type": "command",
        "command": statusline_cmd
    }

    # 2. hooks
    if "hooks" not in data or not isinstance(data["hooks"], dict):
        data["hooks"] = {}

    # UserPromptSubmit -> session_guard.py
    ups_list = data["hooks"].setdefault("UserPromptSubmit", [])
    if not isinstance(ups_list, list):
        ups_list = []
        data["hooks"]["UserPromptSubmit"] = ups_list

    guard_cmd = f'"{python_bin}" "{session_guard_script}"'
    update_hook_list(
        ups_list,
        "session_guard.py",
        lambda: {
            "hooks": [
                {
                    "type": "command",
                    "command": guard_cmd,
                    "timeout": 10
                }
            ]
        }
    )

    # SessionStart -> savings_note.py
    ss_list = data["hooks"].setdefault("SessionStart", [])
    if not isinstance(ss_list, list):
        ss_list = []
        data["hooks"]["SessionStart"] = ss_list

    savings_cmd = f'"{python_bin}" "{savings_note_script}"'
    update_hook_list(
        ss_list,
        "savings_note.py",
        lambda: {
            "matcher": "startup",
            "hooks": [
                {
                    "type": "command",
                    "command": savings_cmd,
                    "timeout": 10
                }
            ]
        }
    )

    # Stop -> usage_meter.py
    stop_list = data["hooks"].setdefault("Stop", [])
    if not isinstance(stop_list, list):
        stop_list = []
        data["hooks"]["Stop"] = stop_list

    meter_cmd = f'"{python_bin}" "{usage_meter_script}"'
    update_hook_list(
        stop_list,
        "usage_meter.py",
        lambda: {
            "hooks": [
                {
                    "type": "command",
                    "command": meter_cmd,
                    "timeout": 10
                }
            ]
        }
    )


def apply_uninstall(data):
    # 1. statusLine
    if "_tokenDietPreviousStatusLine" in data:
        data["statusLine"] = data.pop("_tokenDietPreviousStatusLine")
        print("Restored previous statusLine configuration.")
    elif isinstance(data.get("statusLine"), dict) and "statusline.py" in data["statusLine"].get("command", ""):
        del data["statusLine"]
        print("Removed token-diet statusLine.")

    # 2. hooks
    if "hooks" in data and isinstance(data["hooks"], dict):
        if "UserPromptSubmit" in data["hooks"] and isinstance(data["hooks"]["UserPromptSubmit"], list):
            remove_hook_from_list(data["hooks"]["UserPromptSubmit"], "session_guard.py")
            if len(data["hooks"]["UserPromptSubmit"]) == 0:
                del data["hooks"]["UserPromptSubmit"]

        if "SessionStart" in data["hooks"] and isinstance(data["hooks"]["SessionStart"], list):
            remove_hook_from_list(data["hooks"]["SessionStart"], "savings_note.py")
            if len(data["hooks"]["SessionStart"]) == 0:
                del data["hooks"]["SessionStart"]

        if "Stop" in data["hooks"] and isinstance(data["hooks"]["Stop"], list):
            remove_hook_from_list(data["hooks"]["Stop"], "usage_meter.py")
            if len(data["hooks"]["Stop"]) == 0:
                del data["hooks"]["Stop"]

        if len(data["hooks"]) == 0:
            del data["hooks"]


def main():
    parser = argparse.ArgumentParser(description="Installer and manager for token-diet.")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without modifying settings.json")
    parser.add_argument("--uninstall", action="store_true", help="Remove token-diet from settings.json")
    args = parser.parse_args()

    settings_path = get_settings_path()
    python_bin = sys.executable
    statusline_script = os.path.normpath(os.path.join(ROOT, "scripts", "statusline.py")).replace("\\", "/")
    session_guard_script = os.path.normpath(os.path.join(ROOT, "hooks", "session_guard.py")).replace("\\", "/")
    savings_note_script = os.path.normpath(os.path.join(ROOT, "hooks", "savings_note.py")).replace("\\", "/")
    usage_meter_script = os.path.normpath(os.path.join(ROOT, "hooks", "usage_meter.py")).replace("\\", "/")

    if args.uninstall and not os.path.exists(settings_path):
        print(f"No settings file found at {settings_path}. Nothing to uninstall.")
        return

    original_data = load_settings(settings_path)
    working_data = copy.deepcopy(original_data)
    unrelated_top, unrelated_hooks = extract_unrelated_state(working_data)

    if args.uninstall:
        apply_uninstall(working_data)
    else:
        apply_install(working_data, python_bin, statusline_script, session_guard_script, savings_note_script, usage_meter_script)

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
        restore_backup(backup_path, settings_path)
        print("Install rolled back — your settings are unchanged.")
        sys.exit(1)

    if args.uninstall:
        print("Uninstall complete. Token Diet has been removed from your settings.")
        print(f"Updated configuration in: {settings_path}")
    else:
        print("Setup complete.")
        print(f"Configured status line -> {statusline_script}")
        print(f"Configured prompt reminder -> {session_guard_script}")
        print(f"Configured startup summary -> {savings_note_script}")
        print(f"Configured usage meter -> {usage_meter_script}")
        print(f"Updated configuration in: {settings_path}")


if __name__ == "__main__":
    main()


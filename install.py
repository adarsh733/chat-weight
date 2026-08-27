#!/usr/bin/env python3
"""Installer for token-diet.

Configures Claude settings to wire up status line and hooks.
"""
import json
import os
import sys

ROOT = os.path.normpath(os.path.dirname(os.path.abspath(__file__)))


def get_settings_path():
    return os.path.normpath(os.path.expanduser("~/.claude/settings.json"))


def load_settings(path):
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}
    return {}


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


def main():
    settings_path = get_settings_path()
    data = load_settings(settings_path)

    statusline_script = os.path.normpath(os.path.join(ROOT, "scripts", "statusline.py")).replace("\\", "/")
    session_guard_script = os.path.normpath(os.path.join(ROOT, "hooks", "session_guard.py")).replace("\\", "/")
    savings_note_script = os.path.normpath(os.path.join(ROOT, "hooks", "savings_note.py")).replace("\\", "/")
    usage_meter_script = os.path.normpath(os.path.join(ROOT, "hooks", "usage_meter.py")).replace("\\", "/")

    # 1. statusLine
    statusline_cmd = f'python "{statusline_script}"'
    if "statusLine" not in data or not isinstance(data["statusLine"], dict):
        data["statusLine"] = {
            "type": "command",
            "command": statusline_cmd
        }
    else:
        data["statusLine"]["command"] = statusline_cmd
        if "type" not in data["statusLine"]:
            data["statusLine"]["type"] = "command"

    # 2. hooks
    if "hooks" not in data or not isinstance(data["hooks"], dict):
        data["hooks"] = {}

    # UserPromptSubmit -> session_guard.py
    ups_list = data["hooks"].setdefault("UserPromptSubmit", [])
    if not isinstance(ups_list, list):
        ups_list = []
        data["hooks"]["UserPromptSubmit"] = ups_list

    guard_cmd = f'python "{session_guard_script}"'
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

    savings_cmd = f'python "{savings_note_script}"'
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

    # Stop -> usage_meter.py (the fuel-gauge bar, drawn after each reply)
    stop_list = data["hooks"].setdefault("Stop", [])
    if not isinstance(stop_list, list):
        stop_list = []
        data["hooks"]["Stop"] = stop_list

    meter_cmd = f'python "{usage_meter_script}"'
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

    save_settings(settings_path, data)

    print("Setup complete.")
    print(f"Configured status line -> {statusline_script}")
    print(f"Configured prompt reminder -> {session_guard_script}")
    print(f"Configured startup summary -> {savings_note_script}")
    print(f"Configured usage meter -> {usage_meter_script}")
    print(f"Updated configuration in: {settings_path}")


if __name__ == "__main__":
    main()

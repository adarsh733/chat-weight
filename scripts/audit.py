#!/usr/bin/env python3
"""Where did my tokens go? Reads Claude Code's own chat logs on this machine.

    python audit.py          this project's chats
    python audit.py --all    every project on this machine

Nothing is uploaded. Prints a short report in plain words.
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import td_common  # noqa: E402

PROJECTS = os.path.join(os.path.expanduser("~"), ".claude", "projects")


def human(n):
    for unit, s in ((1e9, "bn"), (1e6, "M"), (1e3, "k")):
        if abs(n) >= unit:
            return "%.1f%s" % (n / unit, s)
    return "%.0f" % n


def _is_prompt(obj):
    """A message the person typed (not a tool result, not a helper agent's)."""
    if obj.get("type") != "user" or obj.get("isMeta") or obj.get("isSidechain"):
        return False
    c = (obj.get("message") or {}).get("content")
    return isinstance(c, str) or (isinstance(c, list) and not any(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in c))


def read_chat(path):
    """Every reply's size, where the person's messages fell, output written, model."""
    steps, sizes, out, model, day = [], [], 0, None, ""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"usage"' not in line and '"user"' not in line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if _is_prompt(obj):
                    steps.append(0)
                    continue
                t = td_common._reply_tokens(obj)
                if not t:
                    continue
                steps.append(t)
                sizes.append(t)
                msg = obj.get("message") or {}
                out += int((msg.get("usage") or {}).get("output_tokens") or 0)
                m = str(msg.get("model") or "")
                if m.startswith("claude-"):
                    model = m
                day = day or str(obj.get("timestamp") or "")[:10]
    except Exception:
        return None
    if not sizes:
        return None
    return {"steps": steps, "sizes": sizes, "out": out, "model": model, "day": day,
            "total": sum(sizes) + out}


def with_fresh_chats(chat, cfg):
    """Same chat, re-priced under token-diet's own rule. An estimate, not a bill.

    A fresh chat is only started where token-diet can act: when the person sends
    a message, once growth has passed the fresh-chat point. The fresh chat starts
    at the old start plus the restart cost, and re-loading that is counted twice
    because it is not yet cached. Returns (tokens, fresh chats started).
    """
    start = chat["sizes"][0]
    win = td_common.window_for(cfg, "audit-none", chat["model"], max(chat["sizes"]))
    restart = td_common.restart_cost(cfg)
    cap = win * int(cfg["memory_cap_pct"]) / 100.0 - start
    line = max(restart, min(restart * float(cfg["restart_multiple"]), cap))
    drop, now, total, fresh = 0, start, 0, 0
    for s in chat["steps"]:
        if s == 0:
            if now - drop - start > line:
                drop = now - start - restart
                total += 2 * restart
                fresh += 1
            continue
        now = s
        total += s - drop
    return total + chat["out"], fresh


def chat_logs(scope_all, root):
    if not os.path.isdir(PROJECTS):
        return []
    folders = [d for d in glob.glob(os.path.join(PROJECTS, "*")) if os.path.isdir(d)]
    if not scope_all:
        key = "".join(ch if ch.isalnum() else "-" for ch in os.path.abspath(root)).lower().strip("-")
        folders = [d for d in folders if os.path.basename(d).lower().strip("-") == key]
    return [f for d in folders for f in glob.glob(os.path.join(d, "*.jsonl"))]


def main(argv):
    scope_all = "--all" in argv
    root = td_common.project_root(os.getcwd())
    cfg = td_common.load_config(root)
    chats = [c for c in (read_chat(p) for p in chat_logs(scope_all, root)) if c]
    if not chats:
        print("No chat logs found for %s yet. Do some work in Claude Code first, or try --all."
              % ("this machine" if scope_all else "this project"))
        return 0

    total = sum(c["total"] for c in chats)
    out = sum(c["out"] for c in chats)
    replies = sum(len(c["sizes"]) for c in chats)
    biggest = sorted(chats, key=lambda c: -c["total"])
    top_n = max(1, len(chats) // 10)
    top_share = sum(c["total"] for c in biggest[:top_n]) / float(total)
    priced = [with_fresh_chats(c, cfg) for c in chats]
    lean = sum(t for t, _ in priced)
    fresh = sum(n for _, n in priced)

    by_depth = {}
    for c in chats:
        for i, s in enumerate(c["sizes"]):
            by_depth.setdefault(min(i // 50, 6), []).append(s)
    first = sum(by_depth[0]) / len(by_depth[0])

    print("")
    print("  TOKEN DIET — where your tokens went (%s)" % ("all projects" if scope_all else "this project"))
    print("  " + "-" * 58)
    print("  Chats %d · replies %s · tokens %s" % (len(chats), format(replies, ","), human(total)))
    print("  Written by the AI      %5.1f%%" % (100.0 * out / total))
    print("  Re-reading the chat    %5.1f%%   <- the real bill" % (100.0 - 100.0 * out / total))
    print("")
    print("  What one reply costs, by how deep into a chat it was:")
    for b in sorted(by_depth):
        avg = sum(by_depth[b]) / len(by_depth[b])
        label = "replies %d+" % (b * 50) if b == 6 else "replies %d-%d" % (b * 50 + 1, b * 50 + 50)
        print("    %-15s %4.1fx  %s" % (label, avg / first, "#" * max(1, int(round(avg / first * 4)))))
    print("")
    print("  Your biggest %d chat%s used %.0f%% of everything." % (top_n, "" if top_n == 1 else "s", 100 * top_share))
    if lean < total:
        print("  With token-diet's fresh chats (%d extra), the same work would have cost about"
              % fresh)
        print("  %.0f%% less (%s). An estimate: it counts re-loading each fresh chat twice."
              % (100.0 * (total - lean) / total, human(total - lean)))
    print("")
    print("  Most expensive chats:")
    for c in biggest[:5]:
        print("    %s  %5d replies  %8s" % (c["day"] or "?", len(c["sizes"]), human(c["total"])))
    print("")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main(sys.argv[1:]))

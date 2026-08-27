#!/usr/bin/env python3
"""Gather the mechanical facts a handoff needs.

This script does NOT write the handoff. It writes the FACTS the handoff is made
of -- files touched, things that failed, what other windows have locked, how far
along this chat is -- so the model never has to re-derive them and never has to
guess. The model turns these facts into the seven sections described in
reference/handoff.md.

Usage:
    python handoff.py                     facts for the current chat
    python handoff.py --transcript PATH   facts for a specific transcript
    python handoff.py --slug NAME         also print the save path to use
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

WRITE_TOOLS = {"Write", "Edit", "NotebookEdit", "MultiEdit"}
SKIP_DIRS = {
    ".git", "node_modules", "dist", "build", "vendor", "__pycache__",
    ".venv", "venv", "archive", "graveyard", "scratchpad", ".next",
    "coverage", "tool-results",
}
MAX_LISTED = 25


# --------------------------------------------------------------------------
# transcript
# --------------------------------------------------------------------------

def newest_transcript(cwd):
    """Find the transcript for the current project, newest first."""
    root = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    if not os.path.isdir(root):
        return None
    best, best_m = None, -1
    for entry in os.listdir(root):
        d = os.path.join(root, entry)
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            if not name.endswith(".jsonl"):
                continue
            p = os.path.join(d, name)
            try:
                m = os.path.getmtime(p)
            except OSError:
                continue
            if m > best_m:
                best, best_m = p, m
    return best


def read_transcript(path):
    """Return (turns, first_ts, last_ts, written_files, failures, tool_counts)."""
    turns = 0
    first_ts = last_ts = None
    written = []
    failures = []
    tool_counts = {}
    pending = {}

    if not path or not os.path.isfile(path):
        return turns, first_ts, last_ts, written, failures, tool_counts

    with open(path, "rb") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw.decode("utf-8", "replace"))
            except Exception:
                continue

            ts = obj.get("timestamp")
            if ts:
                first_ts = first_ts or ts
                last_ts = ts

            kind = obj.get("type")
            message = obj.get("message") or {}
            content = message.get("content")

            if kind == "user" and not obj.get("isMeta") and not obj.get("isSidechain"):
                if isinstance(content, str):
                    turns += 1
                elif isinstance(content, list) and not any(
                    isinstance(b, dict) and b.get("type") == "tool_result"
                    for b in content
                ):
                    turns += 1

            if kind == "assistant" and isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    name = block.get("name") or "?"
                    tool_counts[name] = tool_counts.get(name, 0) + 1
                    args = block.get("input") or {}
                    if name in WRITE_TOOLS:
                        target = args.get("file_path") or args.get("notebook_path")
                        if target and target not in written:
                            written.append(target)
                    # remember what a call was, so a later error can name it
                    label = args.get("command") or args.get("file_path") or ""
                    pending[block.get("id")] = (name, str(label)[:120])

            if kind == "user" and isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_result":
                        continue
                    if not block.get("is_error"):
                        continue
                    name, label = pending.get(block.get("tool_use_id"), ("?", ""))
                    body = block.get("content")
                    if isinstance(body, list):
                        body = " ".join(
                            b.get("text", "") for b in body if isinstance(b, dict)
                        )
                    body = re.sub(r"\s+", " ", str(body or "")).strip()
                    failures.append({"tool": name, "call": label, "error": body[:200]})

    return turns, first_ts, last_ts, written, failures, tool_counts


# --------------------------------------------------------------------------
# repo / filesystem
# --------------------------------------------------------------------------

def git_facts(cwd):
    def run(*args):
        try:
            out = subprocess.run(
                ["git"] + list(args), cwd=cwd, capture_output=True,
                text=True, timeout=10,
            )
            return out.stdout.strip() if out.returncode == 0 else None
        except Exception:
            return None

    if run("rev-parse", "--is-inside-work-tree") != "true":
        return None
    facts = {
        "branch": run("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": [],
        "unpushed": [],
    }
    status = run("status", "--porcelain") or ""
    facts["dirty"] = [ln.strip() for ln in status.splitlines() if ln.strip()]
    ahead = run("log", "--oneline", "@{u}..HEAD")
    if ahead:
        facts["unpushed"] = ahead.splitlines()
    elif ahead == "":
        facts["unpushed"] = []
    else:
        facts["unpushed"] = ["(no upstream branch set)"]
    return facts


def recently_modified(root, since_epoch, limit=MAX_LISTED):
    """Files changed since the chat started -- catches shell writes that no
    Write/Edit tool call would show."""
    hits = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            p = os.path.join(base, name)
            try:
                if os.path.getmtime(p) >= since_epoch:
                    hits.append((os.path.getmtime(p), os.path.relpath(p, root)))
            except OSError:
                continue
        if len(hits) > 400:
            break
    hits.sort(reverse=True)
    return [h[1] for h in hits[:limit]]


def active_claims(cwd):
    """Rows from .claude/ACTIVE-WORK.md, so the handoff can say what is locked."""
    d = os.path.abspath(cwd)
    for _ in range(12):
        p = os.path.join(d, ".claude", "ACTIVE-WORK.md")
        if os.path.isfile(p):
            try:
                text = open(p, encoding="utf-8").read()
            except Exception:
                return []
            block = text.split("## Active claims", 1)
            if len(block) < 2:
                return []
            body = block[1]
            end = re.search(r"^-{3,}\s*$", body, re.M)
            block = body[:end.start()] if end else body
            rows = []
            for line in block.splitlines():
                line = line.strip()
                if not line.startswith("|") or line.startswith("|---"):
                    continue
                cells = [c.strip() for c in line.strip("|").split("|")]
                if len(cells) >= 5 and cells[0] not in ("Claim ID", ""):
                    rows.append({"id": cells[0], "files": cells[3], "task": cells[4]})
            return rows
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return []


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------

def parse_ts(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def bullet(items, empty="none"):
    if not items:
        return "  - %s" % empty
    return "\n".join("  - %s" % i for i in items)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript")
    ap.add_argument("--cwd", default=os.getcwd())
    ap.add_argument("--slug", default="")
    args = ap.parse_args()

    cwd = os.path.abspath(args.cwd)
    transcript = args.transcript or newest_transcript(cwd)
    turns, first_ts, last_ts, written, failures, tools = read_transcript(transcript)

    start = parse_ts(first_ts)
    end = parse_ts(last_ts) or datetime.now(timezone.utc)
    elapsed = (end - start).total_seconds() / 3600.0 if start else 0.0
    since_epoch = start.timestamp() if start else 0

    git = git_facts(cwd)
    claims = active_claims(cwd)
    changed = recently_modified(cwd, since_epoch) if since_epoch else []

    out = []
    out.append("FACTS FOR THE HANDOFF  (generated, not prose -- you write the prose)")
    out.append("=" * 70)
    out.append("")
    out.append("Chat so far: %d messages from the user, %.1f hours." % (turns, elapsed))
    out.append("Working folder: %s" % cwd)
    if transcript:
        out.append("Transcript: %s" % transcript)
    out.append("")

    out.append("FILES THIS CHAT WROTE (from Write/Edit calls)")
    out.append(bullet(written))
    out.append("")

    out.append("FILES CHANGED ON DISK SINCE THIS CHAT STARTED")
    out.append("  (catches shell writes -- but another open window may own some of")
    out.append("   these; check the locks below before claiming them as your work)")
    out.append(bullet(changed))
    out.append("")

    if git:
        out.append("GIT")
        out.append("  - branch: %s" % (git["branch"] or "?"))
        out.append("  - uncommitted: %s" % (len(git["dirty"]) or "clean"))
        for line in git["dirty"][:MAX_LISTED]:
            out.append("      %s" % line)
        out.append("  - not pushed: %s" % (len(git["unpushed"]) or "nothing"))
        for line in git["unpushed"][:10]:
            out.append("      %s" % line)
    else:
        out.append("GIT")
        out.append("  - not a git repository")
    out.append("")

    out.append("THINGS THAT FAILED THIS CHAT (candidates for 'what NOT to do')")
    if failures:
        for f in failures[-10:]:
            out.append("  - %s: %s" % (f["tool"], f["call"]))
            out.append("      -> %s" % f["error"])
    else:
        out.append("  - none")
    out.append("")

    out.append("LOCKS AS OF THIS SECOND -- A SNAPSHOT, NOT SOMETHING TO COPY DOWN")
    out.append("  (they change while you work: when this was tested, two of the locks")
    out.append("   had been released and a new one had appeared before the note was")
    out.append("   even read. Tell the next chat to read .claude/ACTIVE-WORK.md")
    out.append("   itself. If a lock below is yours, say whether the next chat")
    out.append("   inherits it or files a fresh one.)")
    if claims:
        for c in claims:
            out.append("  - %s holds %s  (%s)" % (c["id"], c["files"], c["task"]))
    else:
        out.append("  - none")
    out.append("")

    if tools:
        top = sorted(tools.items(), key=lambda kv: -kv[1])[:6]
        out.append("TOOLS USED: %s" % ", ".join("%s x%d" % t for t in top))
        out.append("")

    slug = args.slug or "handoff"
    date = datetime.now().strftime("%Y-%m-%d")
    out.append("SAVE THE FINISHED NOTE TO")
    out.append("  %s" % os.path.join(cwd, ".claude", "handoffs",
                                     "%s-%s.md" % (date, slug)))
    out.append("")
    out.append("BEFORE YOU WRITE SECTION 4 -- THE ONE THING THAT MAKES OR BREAKS IT")
    out.append("  Everything above is what this chat TOUCHED. Section 4 is about what")
    out.append("  the next job NEEDS. They barely overlap, and getting this wrong is")
    out.append("  the difference between a note that scores 4 and one that works. So:")
    out.append("    1. Open whatever names the next task and quote the item.")
    out.append("    2. Search the code for anything that already does part of it, and")
    out.append("       name it with line numbers. Half-built helpers are the expensive")
    out.append("       thing to miss -- never write 'not started' without looking.")
    out.append("    3. Say what does NOT exist yet if the next task assumes it does.")
    out.append("    4. Only then add finished files, marked 'working, do not open'.")
    out.append("")
    out.append("NOW WRITE IT: follow reference/handoff.md exactly -- seven sections,")
    out.append("in order, plain language, no jargon. Anything you cannot back with a")
    out.append("fact above goes under 'what we are assuming', never under 'done'.")

    sys.stdout.buffer.write(("\n".join(out) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

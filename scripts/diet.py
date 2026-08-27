#!/usr/bin/env python3
"""token-diet - measure and cut AI coding token cost. All local, nothing uploaded."""
import collections, datetime, fnmatch, glob, json, os, re, statistics, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import td_common

# Two settings readers exist and that is deliberate, not an oversight.
# cfg() below reads the whole of efficiency.json -- quota cycle, file ceilings,
# startup files -- because this script is the only thing that needs all of it.
# td_common.load_config() reads the `session` block alone, because the bar and
# the hooks run on the startup path and must stay tiny. Merging them would drag
# quota and file-health handling into every status-line refresh for nothing.
# What td_common gained instead is storage with no opinions: once_since(),
# read_json(), write_json().

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HOME = os.path.expanduser("~")
PROJECTS = os.path.join(HOME, ".claude", "projects")

DEFAULTS = {
    "session": {"max_turns": 50, "warn_turns": 35, "max_hours": 2, "max_context_pct": 60},
    "quota": {"cycle": "weekly", "reset_day": "friday"},
    "startup_files": [],
    "trackers": [],
    "file_health": {
        "warn_lines": 500,
        "split_lines": 800,
        "source_exts": [".js", ".ts", ".jsx", ".tsx", ".py", ".css", ".go", ".rb", ".java"],
        "ignore": ["node_modules", "graveyard", "archive", "dist", "build", "vendor", "_vault"],
    },
    "doc_ceilings_kb": {"default": 15},
}


def cfg(root="."):
    p = os.path.join(root, ".claude", "efficiency.json")
    d = json.loads(json.dumps(DEFAULTS))
    if os.path.exists(p):
        try:
            u = json.load(open(p, encoding="utf-8"))
            for k, v in u.items():
                if isinstance(v, dict) and isinstance(d.get(k), dict):
                    d[k].update(v)
                else:
                    d[k] = v
        except Exception as e:
            print("  ! could not read %s: %s" % (p, e))
    return d


def human(n):
    n = float(n)
    for u, s in ((1e9, "bn"), (1e6, "M"), (1e3, "k")):
        if abs(n) >= u:
            return "%.1f%s" % (n / u, s)
    return "%.0f" % n


def read_session(path):
    ctx, out, turns, prompts = [], 0, 0, 0
    t0 = t1 = None
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except Exception:
        return None
    for line in fh:
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        ts = r.get("timestamp")
        if ts:
            if t0 is None:
                t0 = ts
            t1 = ts
        m = r.get("message") or {}
        if r.get("type") == "assistant":
            turns += 1
            u = m.get("usage") or {}
            c = ((u.get("input_tokens") or 0)
                 + (u.get("cache_read_input_tokens") or 0)
                 + (u.get("cache_creation_input_tokens") or 0))
            ctx.append(c)
            out += (u.get("output_tokens") or 0)
        elif r.get("type") == "user":
            c = m.get("content")
            if isinstance(c, str) and c.strip():
                prompts += 1
            elif isinstance(c, list) and not any(
                isinstance(b, dict) and b.get("type") == "tool_result" for b in c
            ):
                prompts += 1
    fh.close()
    if not turns:
        return None
    hrs = None
    try:
        a = datetime.datetime.fromisoformat(t0.replace("Z", "+00:00"))
        b = datetime.datetime.fromisoformat(t1.replace("Z", "+00:00"))
        hrs = (b - a).total_seconds() / 3600
    except Exception:
        pass
    return {
        "id": os.path.basename(path)[:8], "turns": turns, "prompts": prompts,
        "ctx": ctx, "total": sum(ctx) + out, "out": out,
        "start": t0, "hours": hrs, "date": (t0 or "")[:10],
    }


def load_sessions(scope="project", root="."):
    """Read local session logs. scope 'project' = this folder only, 'all' = every project."""
    if not os.path.isdir(PROJECTS):
        return []
    dirs = sorted(d for d in glob.glob(os.path.join(PROJECTS, "*")) if os.path.isdir(d))
    if scope == "project":
        tail = os.path.basename(os.path.abspath(root)).lower()
        norm = "".join(ch if ch.isalnum() else "-" for ch in os.path.abspath(root).lower())
        m = [d for d in dirs if os.path.basename(d).lower().strip("-") == norm.strip("-")]
        if not m and tail:
            m = [d for d in dirs if tail[:12] in os.path.basename(d).lower()]
        dirs = m or dirs
    out = []
    for d in dirs:
        for f in glob.glob(os.path.join(d, "*.jsonl")):
            s = read_session(f)
            if s:
                out.append(s)
    return sorted(out, key=lambda x: x["start"] or "")


def metrics(S, c):
    if not S:
        return None
    tot = sum(s["total"] for s in S)
    turns = sum(s["turns"] for s in S)
    allctx = sorted(x for s in S for x in s["ctx"])
    bypos = collections.defaultdict(list)
    for s in S:
        for i, x in enumerate(s["ctx"]):
            bypos[min(i // 50, 9)].append(x)
    curve = [(b * 50, statistics.mean(v), len(v)) for b, v in sorted(bypos.items())]
    cap = c["session"]["max_turns"]
    early = [x for s in S for x in s["ctx"][:cap]]
    capped_rate = statistics.mean(early) if early else 90000.0
    would_be = capped_rate * turns
    saved = max(tot - would_be, 0)
    grp = {"short": [], "medium": [], "long": []}
    for s in S:
        k = "short" if s["turns"] <= 100 else ("medium" if s["turns"] <= 300 else "long")
        grp[k].append(s)

    def rate(g):
        t = sum(x["turns"] for x in g)
        return (sum(x["total"] for x in g) / t) if t else 0

    return {
        "sessions": len(S), "turns": turns, "prompts": sum(s["prompts"] for s in S),
        "total": tot, "out": sum(s["out"] for s in S),
        "per_turn": tot / turns if turns else 0,
        "median_ctx": statistics.median(allctx) if allctx else 0,
        "over150": (sum(1 for x in allctx if x > 150000) / len(allctx)) if allctx else 0,
        "curve": curve, "capped_rate": capped_rate, "would_be": would_be,
        "saved": saved, "saved_pct": (saved / tot) if tot else 0,
        "rates": {k: rate(v) for k, v in grp.items()},
        "counts": {k: len(v) for k, v in grp.items()},
        "long_share": (sum(x["total"] for x in grp["long"]) / tot) if tot else 0,
        "top": sorted(S, key=lambda x: -x["total"])[:10],
    }


DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday",
             "Friday", "Saturday", "Sunday"]


def reset_weekday(c):
    """Index of the configured reset day, Monday=0. Defaults to Friday."""
    want = str(c["quota"].get("reset_day") or "friday").strip().lower()
    for i, n in enumerate(DAY_NAMES):
        if n.lower() == want:
            return i
    return 4


def analogy(m, c):
    """The one sentence a person actually reads.

    Rules it has to obey, all from the brief:
      - never a number in tokens; a count of anything measures nothing to the
        reader. The only unit that lands is *the day you would have been cut off*
      - none of the banned words, and "turns" is one of them
      - two sentences: what the old way cost you, then the reassurance

    The arithmetic: a week's allowance drained `mult` times faster lasts 7/mult
    days, so the old way ran out that many days after the reset. Naming the
    weekday is the whole point -- "Wednesday" is a feeling, "38% saved" is not.
    """
    day = DAY_NAMES[reset_weekday(c)]
    if m["capped_rate"] <= 0:
        return ""
    mult = m["per_turn"] / m["capped_rate"]
    if mult <= 1.05:
        return ("You are already working lean. A week's allowance lasts the full "
                "week, and you reach %s's reset with room to spare." % day)
    lasted = 7.0 / mult
    if lasted < 1:
        hit = "within a day of the reset"
    else:
        hit = "around %s" % DAY_NAMES[(reset_weekday(c) + int(lasted)) % 7]
    return ("Working the old way, you would have hit your limit %s. You are on "
            "track to reach %s's reset with room to spare." % (hit, day))


def grade(m):
    p = m["per_turn"]
    if p < 90000:
        return ("A", "Lean. Sessions are short and context stays small.")
    if p < 140000:
        return ("B", "Good. A few sessions run longer than they should.")
    if p < 190000:
        return ("C", "Heavy. Long sessions are costing you real time.")
    if p < 250000:
        return ("D", "Expensive. Most work happens in an overloaded window.")
    return ("F", "Severe. You are paying several times over for the same work.")


def cmd_audit(root, scope):
    c = cfg(root)
    m = metrics(load_sessions(scope, root), c)
    if not m:
        print("No session logs found yet. Do some work first, then run this again.")
        return
    g, gt = grade(m)
    print("")
    print("  TOKEN DIET - audit (%s)" % scope)
    print("  " + "=" * 60)
    print("  Sessions            %s" % format(m["sessions"], ","))
    print("  AI turns            %s" % format(m["turns"], ","))
    print("  Your prompts        %s" % format(m["prompts"], ","))
    print("  Total tokens        %s" % human(m["total"]))
    print("  Written by the AI   %s  (%.1f%% of the bill)" % (human(m["out"]), 100 * m["out"] / m["total"]))
    print("  Re-reading context  %s  (%.1f%%)" % (human(m["total"] - m["out"]), 100 - 100 * m["out"] / m["total"]))
    print("")
    print("  Cost per turn       %s      GRADE %s - %s" % (format(int(m["per_turn"]), ","), g, gt))
    print("  Turns over 150k     %.0f%%" % (100 * m["over150"]))
    print("")
    print("  Cost per turn, by how deep into a chat it happened:")
    base = m["curve"][0][1] if m["curve"] else 1
    for lo, avg, n in m["curve"]:
        print("    turns %3d-%3d  %9s  %4.1fx  %s"
              % (lo, lo + 49, format(int(avg), ","), avg / base, "#" * max(1, int(avg / 12000))))
    print("")
    print("  By session length:")
    labels = {"short": "under 100 turns", "medium": "100-300 turns", "long": "over 300 turns"}
    for k in ("short", "medium", "long"):
        print("    %-16s %3d sessions   %9s per turn"
              % (labels[k], m["counts"][k], format(int(m["rates"][k]), ",")))
    print("    -> long sessions are %.0f%% of everything you have spent" % (100 * m["long_share"]))
    print("")
    print("  If every session had stopped at %d turns:" % c["session"]["max_turns"])
    print("    same work would have cost   %s" % human(m["would_be"]))
    print("    you would have saved        %s  (%.0f%%)" % (human(m["saved"]), 100 * m["saved_pct"]))
    print("")
    print("  " + (analogy(m, c) or "Not enough history yet."))
    print("")
    print("  Most expensive sessions:")
    for s in m["top"][:5]:
        h = ("%.1fh" % s["hours"]) if s["hours"] else "?"
        print("    %s  %4d turns  %7s  %7s" % (s["date"], s["turns"], h, human(s["total"])))
    print("")
    write_savings_cache(m, c, root)   # the audit already paid for the scan


def cmd_check(root, scope):
    c = cfg(root)
    S = load_sessions(scope, root)
    if not S:
        print("  No history yet - nothing to enforce.")
        return
    cur = S[-1]
    s = c["session"]
    print("")
    print("  SESSION CHECK  -  %d turns%s"
          % (cur["turns"], (", %.1fh" % cur["hours"]) if cur["hours"] else ""))
    over = []
    if cur["turns"] >= s["max_turns"]:
        over.append("turns %d >= %d" % (cur["turns"], s["max_turns"]))
    if cur["hours"] and cur["hours"] >= s["max_hours"]:
        over.append("%.1fh >= %dh" % (cur["hours"], s["max_hours"]))
    if cur["ctx"] and cur["ctx"][-1] >= 200000 * s["max_context_pct"] / 100.0:
        over.append("context %s over %d%%" % (format(cur["ctx"][-1], ","), s["max_context_pct"]))
    if over:
        print("  >> LIMIT REACHED: " + "; ".join(over))
        print("  >> The next message must be a HANDOFF. Release claims, write the log,")
        print("     emit the handoff, start a fresh chat. Do not continue here.")
    elif cur["turns"] >= s["warn_turns"]:
        print("  >> WARNING: %d turns left. Find a stopping point." % (s["max_turns"] - cur["turns"]))
    else:
        print("  OK - %d turns of headroom." % (s["max_turns"] - cur["turns"]))
    print("")


def _walk(root, c):
    ig = set(c["file_health"]["ignore"])
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in ig and not d.startswith(".")]
        for f in fn:
            yield os.path.join(dp, f)


def cmd_health(root, scope):
    c = cfg(root)
    fh = c["file_health"]
    exts = set(fh["source_exts"])
    rows = []
    for p in _walk(root, c):
        if os.path.splitext(p)[1] not in exts:
            continue
        try:
            n = sum(1 for _ in open(p, encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if n >= fh["warn_lines"]:
            rows.append((n, os.path.relpath(p, root)))
    rows.sort(reverse=True)
    print("")
    print("  FILE HEALTH  (warn %d lines, must-split %d lines)" % (fh["warn_lines"], fh["split_lines"]))
    print("  " + "=" * 60)
    if not rows:
        print("  All source files are within limits.")
        print("")
        return
    for n, p in rows:
        tag = "MUST SPLIT" if n >= fh["split_lines"] else "watch     "
        print("  %s  %5d lines   %s" % (tag, n, p))
    split = [r for r in rows if r[0] >= fh["split_lines"]]
    if split:
        print("")
        print("  >> %d file(s) must be split BEFORE new work goes into them." % len(split))
        print("     Every edit to these reloads the whole file. That is the cost.")
    print("")


def cmd_guard(root, scope):
    c = cfg(root)
    files = c.get("startup_files") or []
    if not files:
        print("")
        print("  No startup_files configured. List the files read at the start of every")
        print("  session in .claude/efficiency.json so they can be capped.")
        print("")
        return
    dflt = c["doc_ceilings_kb"]["default"]
    print("")
    print("  STARTUP FILE GUARD")
    print("  " + "=" * 60)
    tot = 0.0
    bad = 0
    for entry in files:
        if isinstance(entry, str):
            path, cap = entry, dflt
        else:
            path, cap = entry["path"], entry.get("kb", dflt)
        fp = os.path.join(root, path)
        if not os.path.exists(fp):
            print("  missing   %s" % path)
            continue
        kb = os.path.getsize(fp) / 1024.0
        tot += kb
        if kb > cap:
            bad += 1
            print("  OVER      %7.1f KB / %s KB   %s   -> archive the history" % (kb, cap, path))
        else:
            print("  ok        %7.1f KB / %s KB   %s" % (kb, cap, path))
    print("")
    print("  Read every session: %.1f KB  (~%s tokens)" % (tot, format(int(tot * 1024 / 4), ",")))
    if bad:
        print("  >> %d file(s) over ceiling. Archive to .claude/archive/, keep only what is true now." % bad)
    print("")


def cmd_init(root, scope):
    d = os.path.join(root, ".claude")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "efficiency.json")
    if os.path.exists(p):
        print("  Already exists: %s" % p)
        return
    v = json.loads(json.dumps(DEFAULTS))
    v["startup_files"] = [{"path": "AGENTS.md", "kb": 10}, {"path": "CLAUDE.md", "kb": 5}]
    json.dump(v, open(p, "w", encoding="utf-8"), indent=2)
    print("  Created %s - edit startup_files and thresholds to suit this project." % p)


def write_savings_cache(m, c, root):
    """Freeze the finished sentence on disk so nothing has to think at chat start.

    analogy() cannot run without reading every session log on disk -- megabytes
    across a hundred chats. Anything on the startup path has a fraction of a
    second, so the startup path never computes this: it reads the answer that
    the last audit left behind, or it says nothing at all.

    Reset day and grade travel with the sentence deliberately. The reader of
    this file is a hook that must not know what a quota cycle is.
    """
    if not m:
        return None
    g, gt = grade(m)
    p = td_common.savings_cache_path(root)
    ok = td_common.write_json(p, {
        "v": 1,
        "generated": datetime.date.today().isoformat(),
        "sentence": analogy(m, c),
        "grade": g,
        "grade_text": gt,
        "reset_day": DAY_NAMES[reset_weekday(c)].lower(),
        "sessions": m["sessions"],
        "per_turn": int(m.get("per_turn", 0)),
        "capped_rate": int(m.get("capped_rate", 0)),
    })
    return p if ok else None


def cmd_savings(root, scope):
    """Recompute the sentence and store it. Slow on purpose; never on startup."""
    c = cfg(root)
    m = metrics(load_sessions(scope, root), c)
    if not m:
        print("  Not enough history yet.")
        return
    p = write_savings_cache(m, c, root)
    if "--quiet" in sys.argv:
        return
    print("")
    print("  " + (analogy(m, c) or "Not enough history yet."))
    print("")
    print("  stored: %s" % p)
    print("")


from codemap import cmd_codemap, cmd_dupes
from tidy import cmd_tidy


def cmd_loadaudit(root, scope):
    """Audit the startup footprint: sum bytes of startup_files and flag any over cap."""
    c = cfg(root)
    files = c.get("startup_files") or []
    dflt = c.get("doc_ceilings_kb", {}).get("default", 15)
    print("")
    print("  LOAD AUDIT - startup footprint")
    print("  " + "=" * 60)
    if not files:
        print("  No startup_files configured in .claude/efficiency.json")
        print("  Total startup footprint: 0.0 KB (loads before you type)")
        print("")
        return
    tot = 0.0
    bad = 0
    for entry in files:
        if isinstance(entry, str):
            path, cap = entry, dflt
        else:
            path, cap = entry.get("path", ""), entry.get("kb", dflt)
        fp = os.path.join(root, path)
        if not os.path.exists(fp):
            print("  missing   %s" % path)
            continue
        kb = os.path.getsize(fp) / 1024.0
        tot += kb
        if kb > cap:
            bad += 1
            print("  OVER      %7.1f KB / %s KB   %s   -> over cap" % (kb, cap, path))
        else:
            print("  ok        %7.1f KB / %s KB   %s" % (kb, cap, path))
    print("")
    print("  Total startup footprint: %.1f KB (loads before you type, ~%s tokens)"
          % (tot, format(int(tot * 1024 / 4), ",")))
    if bad:
        print("  >> %d file(s) over ceiling. Archive to .claude/archive/, keep only what is true now." % bad)
    print("")


def cmd_movement(root, scope):
    """Compare baseline vs current cost per turn. Output: better / worse / same."""
    baseline = None
    current = None
    for a in sys.argv[1:]:
        if a.startswith("--baseline="):
            try:
                baseline = float(a.split("=", 1)[1])
            except ValueError:
                pass
        elif a.startswith("--current="):
            try:
                current = float(a.split("=", 1)[1])
            except ValueError:
                pass
    if baseline is None or current is None:
        print("Usage: diet.py movement --baseline=N --current=N")
        return
    if current < baseline:
        diff_pct = (baseline - current) / baseline * 100.0 if baseline > 0 else 0
        print("better (%.1f%% lower cost per turn)" % diff_pct)
    elif current > baseline:
        diff_pct = (current - baseline) / baseline * 100.0 if baseline > 0 else 0
        print("worse (%.1f%% higher cost per turn)" % diff_pct)
    else:
        print("same")



CMDS = {
    "audit": cmd_audit,
    "check": cmd_check,
    "health": cmd_health,
    "guard": cmd_guard,
    "init": cmd_init,
    "savings": cmd_savings,
    "codemap": cmd_codemap,
    "dupes": cmd_dupes,
    "loadaudit": cmd_loadaudit,
    "movement": cmd_movement,
    "tidy": cmd_tidy,
}

if __name__ == "__main__":
    cmd = "audit"
    for a in sys.argv[1:]:
        if not a.startswith("--"):
            cmd = a
            break
    scope = "all" if "--all" in sys.argv else "project"
    root = "."
    for a in sys.argv[1:]:
        if a.startswith("--root="):
            root = a.split("=", 1)[1]
    if cmd not in CMDS:
        print("Unknown command '%s'. Try: %s" % (cmd, ", ".join(CMDS)))
        sys.exit(1)
    CMDS[cmd](root, scope)
    if cmd in ("audit", "health", "savings", "loadaudit", "movement"):
        print("\n  ── token-diet · built by After Hours · github.com/adarsh733/token-diet")

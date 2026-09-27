"""Helpers the bash lane runners call: config lookup, working-tree snapshots, effort checks, and the
per-run ledger record (tokens and how much of the ChatGPT window the run ate).

    python3 lib/af.py lane-config LANE [--root DIR] [--config PATH]
    python3 lib/af.py verify-command [--root DIR] [--config PATH]
    python3 lib/af.py root [DIR]
    python3 lib/af.py snapshot ROOT
    python3 lib/af.py changed BEFORE_FILE AFTER_FILE
    python3 lib/af.py check-effort MODEL EFFORT [--root DIR]
    python3 lib/af.py codex-now
    python3 lib/af.py record --kind K --lane L --model M ... (see record())
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys

from . import core, pantry

SKIP_DIRS = {".git", "node_modules", ".build", "build", "DerivedData", ".venv", "venv", "__pycache__",
             "target", "dist", ".next", ".gradle", ".idea", ".swiftpm"}


# ---------------------------------------------------------------- config

def cmd_lane_config(args):
    try:
        lanes, layers = core.load_lanes(args.root, args.config)
    except ValueError as exc:
        print("ERR\t%s" % exc)
        return 0
    lane = lanes.get(args.lane)
    if not isinstance(lane, dict) or "model" not in lane:
        known = ", ".join(k for k, v in lanes.items() if isinstance(v, dict) and "model" in v)
        print("ERR\tunknown lane '%s' (known: %s) in %s" % (args.lane, known, core.describe_layers(layers)))
        return 0
    fields = ["OK", lane.get("provider", "codex"), lane["model"], lane.get("effort", "high"),
              str(lane.get("timeout_seconds", 1500)), "true" if lane.get("enabled", True) else "false",
              lane.get("base_url") or "-", core.describe_layers(layers)]
    print("\t".join(str(f) for f in fields))
    return 0


def cmd_verify_command(args):
    lanes, _ = core.load_lanes(args.root, args.config)
    print((lanes.get("verify") or {}).get("command", ""))
    return 0


def cmd_root(args):
    print(core.project_root(args.dir))
    return 0


# ---------------------------------------------------------------- snapshots

def _hash_file(path):
    try:
        if os.path.islink(path):
            return "link:" + os.readlink(path)
        if not os.path.isfile(path):
            return "-"
        h = hashlib.sha1()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
    except OSError:
        return "?"


def snapshot(root):
    """Map path -> (status, content hash) for every dirty or untracked file. Comparing two of these
    catches changes git status alone misses: a file that was already modified, or already
    untracked, and got edited again."""
    try:
        out = subprocess.run(["git", "-C", root, "status", "--porcelain=v1", "-z", "--untracked-files=all"],
                             capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        out = None
    entries = {}
    if out is not None and out.returncode == 0:
        items = out.stdout.decode("utf-8", "surrogateescape").split("\0")
        i = 0
        while i < len(items):
            item = items[i]
            i += 1
            if len(item) < 4:
                continue
            xy, path = item[:2], item[3:]
            if xy[0] in "RC":
                i += 1  # the rename source follows; the destination is what changed
            entries[path] = (xy, _hash_file(os.path.join(root, path)))
        return entries, "git"
    # not a git repository: size and mtime of every file, skipping build and dependency directories
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            full = os.path.join(dirpath, name)
            try:
                st = os.stat(full)
            except OSError:
                continue
            entries[os.path.relpath(full, root)] = ("??", "%d:%d" % (int(st.st_mtime), st.st_size))
    return entries, "files"


def cmd_snapshot(args):
    entries, kind = snapshot(args.root)
    sys.stdout.write("#kind\t%s\n" % kind)
    for path in sorted(entries):
        xy, h = entries[path]
        sys.stdout.write("%s\t%s\t%s\n" % (xy, h, path))
    return 0


def _read_snapshot(path):
    entries = {}
    with open(path) as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t", 2)
            if len(parts) == 3:
                entries[parts[2]] = (parts[0], parts[1])
    return entries


def changed(before, after):
    out = []
    for path in sorted(set(before) | set(after)):
        b, a = before.get(path), after.get(path)
        if b == a:
            continue
        if a is None:
            out.append(("clean", path))  # was dirty, now matches HEAD again (reverted or committed)
        else:
            out.append((a[0].strip() or "M", path))
    return out


def cmd_changed(args):
    for status, path in changed(_read_snapshot(args.before), _read_snapshot(args.after)):
        print("%-5s %s" % (status, path))
    return 0


# ---------------------------------------------------------------- efforts

def find_model(models_cfg, key):
    models = (models_cfg or {}).get("models", {})
    if key in models:
        return key, models[key]
    for mid, m in models.items():
        if not isinstance(m, dict):
            continue
        if key == m.get("slug") or key in (m.get("aliases") or []):
            return mid, m
    return None, None


def cmd_check_effort(args):
    effort = args.effort
    if effort not in core.CODEX_EFFORTS:
        print("error\t'%s' is not a reasoning effort Codex knows (%s)" % (effort, ", ".join(core.CODEX_EFFORTS)))
        return 2
    try:
        models, _ = core.load_models(args.root)
    except ValueError:
        models = {}
    mid, m = find_model(models, args.model)
    if not m:
        print("warn\t%s is not in the Potato Council's roster; effort '%s' unchecked (af-council add %s --like ...)"
              % (args.model, effort, args.model))
        return 0
    known = m.get("efforts") or []
    if known and effort not in known:
        print("warn\t%s is not known to accept '%s' (known: %s); Codex will say if it minds"
              % (m.get("name", mid), effort, ", ".join(known)))
        return 0
    print("ok\t%s accepts %s" % (m.get("name", mid), effort))
    return 0


# ---------------------------------------------------------------- run records

def cmd_codex_now(args):
    snap = pantry.codex_snapshot(use_cache=False)
    print(json.dumps(snap))
    return 0


def _window_delta(before, after):
    """Per-window before/after/delta, only where both readings describe the same window
    (same reset time). Anything else is 'unknown', because unknown is not zero."""
    if not after:
        return None
    b_windows = {w["name"]: w for w in (before or {}).get("windows", [])}
    rows = []
    for w in after.get("windows", []):
        row = {"window": w["name"], "after": w["used"]}
        bw = b_windows.get(w["name"])
        same = (bw is not None and bw.get("resets_at") and w.get("resets_at")
                and abs(float(bw["resets_at"]) - float(w["resets_at"])) < 120)
        if same:
            row["before"] = bw["used"]
            row["delta"] = round(w["used"] - bw["used"], 2)
        rows.append(row)
    return {"budget": after.get("budget", "chatgpt"), "plan": after.get("plan"), "windows": rows}


def fmt_tokens(tokens):
    if not tokens:
        return "unknown (no rollout found for this session)"
    def n(k):
        v = tokens.get(k)
        return "?" if v is None else "{:,}".format(int(v))
    parts = ["in %s" % n("input_tokens")]
    if tokens.get("cached_input_tokens"):
        parts[-1] += " (cached %s)" % n("cached_input_tokens")
    parts.append("out %s" % n("output_tokens"))
    if tokens.get("reasoning_output_tokens"):
        parts[-1] += " (reasoning %s)" % n("reasoning_output_tokens")
    return " · ".join(parts)


def fmt_budget(delta):
    if not delta or not delta.get("windows"):
        return "unknown (no rate-limit reading)"
    segs = []
    for row in delta["windows"]:
        if "delta" in row:
            segs.append("%s %.1f%% → %.1f%% (%+.1f)" % (row["window"], row["before"], row["after"], row["delta"]))
        else:
            segs.append("%s now %.1f%% (no same-window reading before)" % (row["window"], row["after"]))
    return "%s · %s" % (delta.get("budget"), " · ".join(segs))


def cmd_record(args):
    before = None
    if args.before and os.path.isfile(args.before):
        try:
            with open(args.before) as fh:
                before = json.load(fh)
        except ValueError:
            before = None
    usage = pantry.session_usage(args.session) if args.session and args.provider != "local" else None
    tokens = (usage or {}).get("tokens")
    after = (usage or {}).get("snapshot")
    delta = _window_delta(before, after) if after else None
    run_id = core.new_run_id(args.lane)
    entry = {
        "id": run_id, "ts": core.iso(), "kind": args.kind, "lane": args.lane, "provider": args.provider,
        "model": args.model, "effort": args.effort, "effort_source": args.effort_source,
        "status": args.status, "exit": args.exit, "duration_s": args.duration,
        "changed_files": args.changed_count, "session": args.session or None,
        "project": os.path.basename(args.root.rstrip("/")) if args.root else None,
        "tokens": tokens, "budget_delta": delta, "verdict": None,
    }
    if args.note:
        entry["note"] = args.note
    try:
        core.ledger_append(entry)
    except OSError as exc:
        print("RUN: (ledger not writable: %s)" % exc)
        return 0
    print("RUN: %s   (grade it: af-council grade %s pass|fail)" % (run_id, run_id))
    if args.provider != "local":
        print("TOKENS: %s" % fmt_tokens(tokens))
        print("BUDGET: %s" % fmt_budget(delta))
    return 0


# ---------------------------------------------------------------- dispatch

def main(argv=None):
    p = argparse.ArgumentParser(prog="af.py")
    sub = p.add_subparsers(dest="cmd")
    a = sub.add_parser("lane-config"); a.add_argument("lane"); a.add_argument("--root"); a.add_argument("--config")
    a = sub.add_parser("verify-command"); a.add_argument("--root"); a.add_argument("--config")
    a = sub.add_parser("root"); a.add_argument("dir", nargs="?")
    a = sub.add_parser("snapshot"); a.add_argument("root")
    a = sub.add_parser("changed"); a.add_argument("before"); a.add_argument("after")
    a = sub.add_parser("check-effort"); a.add_argument("model"); a.add_argument("effort"); a.add_argument("--root")
    sub.add_parser("codex-now")
    a = sub.add_parser("record")
    for flag in ("--kind", "--lane", "--provider", "--model", "--effort", "--effort-source", "--status",
                 "--session", "--before", "--root", "--note"):
        a.add_argument(flag, default="")
    a.add_argument("--exit", type=int, default=0)
    a.add_argument("--duration", type=int, default=0)
    a.add_argument("--changed-count", type=int, default=0)
    args = p.parse_args(argv)
    handlers = {"lane-config": cmd_lane_config, "verify-command": cmd_verify_command, "root": cmd_root,
                "snapshot": cmd_snapshot, "changed": cmd_changed, "check-effort": cmd_check_effort,
                "codex-now": cmd_codex_now, "record": cmd_record}
    if args.cmd not in handlers:
        p.print_help()
        return 2
    return handlers[args.cmd](args)

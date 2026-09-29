"""af-doctor: is everything plugged in? One screen that answers the questions setup and debugging
both start with. Read-only; never spends a token."""
import argparse
import json
import os
import shutil
import subprocess
import sys

from . import __version__, core, council, jev, pantry, spud
from .lanes import find_model

OK, WARN, BAD = "ok", "warn", "bad"


def _run(cmd, timeout=15):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return out.returncode, (out.stdout + out.stderr).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, str(exc)


def checks(root):
    rows = []
    def add(level, what, detail=""):
        rows.append({"level": level, "what": what, "detail": detail})

    add(OK, "astrafabulopus %s" % __version__, core.PLUGIN_ROOT)
    v = sys.version_info
    add(OK if v >= (3, 9) else WARN, "python %d.%d.%d" % v[:3], "" if v >= (3, 9) else "3.9+ recommended")
    add(OK if shutil.which("git") else BAD, "git", shutil.which("git") or "not on PATH")
    on_path = shutil.which("af-lane")
    add(OK if on_path else WARN, "af-* commands on PATH",
        on_path or "not on PATH here; the plugin adds bin/ to Claude Code's Bash tool, lite installs use .claude/orchestra/bin/")

    codex = shutil.which("codex")
    if not codex:
        add(BAD, "codex CLI", "not found: npm i -g @openai/codex && codex login")
    else:
        _, ver = _run(["codex", "--version"])
        add(OK, "codex CLI", ver.splitlines()[-1] if ver else codex)
        rc, status = _run(["codex", "login", "status"])
        add(OK if rc == 0 else BAD, "codex login", (status.splitlines() or ["?"])[-1])

    try:
        lanes, lane_layers = core.load_lanes(root)
        add(OK, "lanes config", core.describe_layers(lane_layers))
    except ValueError as exc:
        lanes, lane_layers = {}, []
        add(BAD, "lanes config", str(exc))
    try:
        mcfg, models, model_layers = council.load(root)
        add(OK, "council roster", "%d models · %s" % (len(council.active(models)), core.describe_layers(model_layers)))
    except ValueError as exc:
        mcfg, models = {}, {}
        add(BAD, "council roster", str(exc))

    try:
        jev_settings = jev.config(root)
        state, source = jev.key_status(jev_settings)
        if state == "disabled":
            add(OK, "Jev", "disabled (advisory quick decisions)")
        elif state == "found":
            add(OK, "Jev", "enabled · key found via %s" % source)
        else:
            add(WARN, "Jev", "enabled · key missing (TYPESAFE_API_KEY, 1Password, or Keychain)")
    except (ValueError, jev.Unavailable):
        add(WARN, "Jev", "configuration unavailable")

    for name, lane in lanes.items():
        if name == "jev":
            continue
        if not isinstance(lane, dict) or "model" not in lane or lane.get("provider") == "anthropic":
            continue
        mid, m = find_model(mcfg, lane["model"])
        detail = "%s · %s · effort %s" % (lane.get("provider", "codex"), lane["model"], lane.get("effort", "high"))
        level = OK
        if not lane.get("enabled", True):
            detail += " · disabled"
        if not m:
            level, detail = WARN, detail + " · not on the Council (af-council add %s --like ...)" % lane["model"]
        elif m.get("efforts") and lane.get("effort", "high") not in m["efforts"]:
            level, detail = WARN, detail + " · effort not in %s's known rungs" % m.get("name", mid)
        elif m.get("retires"):
            detail += " · retires %s" % m["retires"]
        add(level, "lane %s" % name, detail)

    budgets = pantry.gather(refresh_codex=True)
    for b in ("claude", "chatgpt"):
        lv = budgets[b]["level"]
        add(OK if lv in ("plenty", "watch") else WARN, "pantry %s" % b,
            "%s · %s" % (lv, budgets[b].get("reason", "")))

    settings = core.read_json(os.path.join(core.claude_config_dir(), "settings.json"), {}) or {}
    sl = (settings.get("statusLine") or {}).get("command", "")
    add(OK if "af-statusline" in sl else WARN, "status-line tap",
        sl if "af-statusline" in sl else "not installed: Claude windows stay unknown (run /astrafabulopus:setup)")

    runs = core.ledger_read()
    graded = sum(1 for r in runs if r.get("verdict") in ("pass", "fail"))
    add(OK, "ledger", "%d runs, %d graded · %s" % (len(runs), graded, core.ledger_path()))
    return rows


def main(argv=None):
    p = argparse.ArgumentParser(prog="af-doctor", description="Is everything plugged in?")
    p.add_argument("--root")
    p.add_argument("--json", action="store_true")
    p.add_argument("--strict", action="store_true", help="exit 1 if anything is bad")
    p.add_argument("--candidates", action="store_true", help="print the Codex slugs setup should probe")
    args = p.parse_args(argv)
    root = args.root or core.project_root()
    if args.candidates:
        lanes, _ = core.load_lanes(root)
        print("\n".join(lanes.get("_candidates") or []))
        return 0
    rows = checks(root)
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        marks = {OK: "✓", WARN: "!", BAD: "✗"} if not core.plain_mode() else {OK: "ok", WARN: "!!", BAD: "XX"}
        print(spud.banner("SPUD CHECK"))
        for r in rows:
            print(" %s %-24s %s" % (marks[r["level"]], r["what"], r["detail"]))
        bad = sum(1 for r in rows if r["level"] == BAD)
        warn = sum(1 for r in rows if r["level"] == WARN)
        print("\n %s" % ("All tubers accounted for." if not bad and not warn else
                         "%d problem%s, %d warning%s." % (bad, "" if bad == 1 else "s", warn, "" if warn == 1 else "s")))
    return 1 if args.strict and any(r["level"] == BAD for r in rows) else 0

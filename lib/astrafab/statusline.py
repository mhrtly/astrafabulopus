"""af-statusline: a Claude Code status line that also feeds the pantry.

Claude Code pipes a JSON payload to the status-line command. Since 2.1.80 that payload carries
`rate_limits.five_hour` / `rate_limits.seven_day` (`used_percentage`, `resets_at`) for Pro and Max
plans. We save it, print one short line, and never fail loudly: a status line that crashes is worse
than one that says nothing.

    af-statusline [--chain "your-existing-statusline-command"]
"""
import json
import subprocess
import sys

from . import core, pantry, spud


def segment(payload, claude_snap):
    parts = []
    model = (payload.get("model") or {}).get("display_name") if isinstance(payload, dict) else None
    head = ("%s %s" % (spud.emoji("plenty"), model)).strip() if model else spud.emoji("plenty")
    if head:
        parts.append(head)
    if claude_snap:
        pantry.evaluate(claude_snap)
        ws = " ".join("%s %.0f%%" % (w["name"], w["effective_used"]) for w in claude_snap["windows"]
                      if w["name"] in ("5h", "7d"))
        lv = claude_snap["level"]
        parts.append("Claude %s%s" % (ws, "" if lv == "plenty" else " " + spud.emoji(lv)))
    codex = pantry.codex_snapshot(use_cache=True)
    if codex:
        pantry.evaluate(codex)
        ws = " ".join("%s %.0f%%" % (w["name"], w["effective_used"]) for w in codex["windows"])
        lv = codex["level"]
        parts.append("GPT %s%s" % (ws, "" if lv == "plenty" else " " + spud.emoji(lv)))
    return " │ ".join(p for p in parts if p)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    chain = None
    if len(argv) >= 2 and argv[0] == "--chain":
        chain = argv[1]
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {}
    chained = ""
    if chain:
        try:
            out = subprocess.run(chain, shell=True, input=raw, capture_output=True, text=True, timeout=10)
            chained = out.stdout.rstrip("\n")
        except (OSError, subprocess.SubprocessError):
            chained = ""
    try:
        snap = pantry.tap_statusline(payload) or pantry.claude_snapshot()
        mine = segment(payload, snap)
    except Exception:  # a status line must never take the session down with it
        mine = spud.emoji("unknown") + " pantry unavailable"
    if chained:
        lines = chained.split("\n")
        lines[-1] = lines[-1] + " │ " + mine
        print("\n".join(lines))
    else:
        print(mine)
    return 0

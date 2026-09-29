"""`af-decide`: ask Jev for a typed, advisory read of an implementation spec."""
import argparse
import json
import os
from . import core, council, jev

_SAFE_REASONS = {
    "disabled", "no key found", "invalid key format", "invalid endpoint",
    "invalid Jev configuration", "no enabled lanes", "http error", "network error",
    "timeout", "invalid response", "internal error",
}


def _read_spec(path):
    if not os.path.isfile(path):
        raise ValueError("spec file not found")
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeError):
        raise ValueError("spec file cannot be read as text")


def _run(path, root=None):
    try:
        spec_text = _read_spec(path)
        settings = jev.config(root)
        if not settings.get("enabled"):
            raise jev.Unavailable("disabled")
        lanes, _ = core.load_lanes(root)
        models_cfg, _, _ = council.load(root)
        result = jev.request(spec_text, lanes, models_cfg, settings)
        decision_id = jev.log_suggestion(result)
        return result, decision_id, settings, None
    except jev.Unavailable as exc:
        reason = exc.args[0] if exc.args and isinstance(exc.args[0], str) else "internal error"
        return None, None, None, reason if reason in _SAFE_REASONS else "internal error"
    except Exception:
        return None, None, None, "internal error"


def main(argv=None):
    p = argparse.ArgumentParser(prog="af-decide", description="Ask Jev for advisory quick decisions.")
    p.add_argument("command", choices=("lane",), help="decision set to ask")
    p.add_argument("spec_file", help="plain text spec to send as Jev state")
    p.add_argument("--root", help=argparse.SUPPRESS)
    p.add_argument("--json", action="store_true", help="print structured output")
    args = p.parse_args(argv)
    root = args.root or core.project_root()
    result, decision_id, settings, error = _run(args.spec_file, root)
    if error:
        print("DECISION: unavailable (%s)" % error)
        return 3
    lines = jev.render_lines(result, settings["min_probability"])
    if args.json:
        print(json.dumps({"available": True, "decision_id": decision_id, "model": result["model"],
                          "request_id": result.get("request_id"), "latency_ms": result["latency_ms"],
                          "decisions": result["answers"], "confident_at": settings["min_probability"]},
                         indent=2))
    else:
        print("\n".join(lines))
        print("DECISION_ID: %s" % decision_id)
    return 0

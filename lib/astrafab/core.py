"""Shared plumbing for astrafabulopus: paths, layered config, the run ledger, small helpers.

Python 3.9+ and the standard library only, because macOS ships 3.9 with the Xcode tools and
nobody should have to pip-install anything to route a spec.
"""
import datetime as _dt
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time

PLUGIN_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", ".."))

# Codex's full reasoning-effort vocabulary (codex-rs/protocol/src/openai_models.rs, 2026-09).
CODEX_EFFORTS = ["none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"]


# ---------------------------------------------------------------- paths

def af_home():
    return os.path.expanduser(os.environ.get("ASTRAFABULOPUS_HOME") or "~/.claude/astrafabulopus")


def codex_home():
    return os.path.expanduser(os.environ.get("CODEX_HOME") or "~/.codex")


def claude_config_dir():
    return os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude")


def project_root(start=None):
    """The git top level containing `start` (default: cwd), else `start` itself."""
    start = os.path.abspath(start or os.getcwd())
    try:
        out = subprocess.run(["git", "-C", start, "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return start


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


# ---------------------------------------------------------------- json io

def read_json(path, default=None):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def write_json_atomic(path, data):
    ensure_dir(os.path.dirname(path) or ".")
    fd, tmp = tempfile.mkstemp(prefix=".af-", dir=os.path.dirname(path) or ".")
    with os.fdopen(fd, "w") as fh:
        json.dump(data, fh, indent=2, sort_keys=False)
        fh.write("\n")
    os.replace(tmp, path)


# ---------------------------------------------------------------- layered config

def config_layers(name, root=None, explicit=None):
    """Files that make up a config, lowest precedence first.

    lanes.json and models.json both resolve plugin default -> user (~/.claude/astrafabulopus) ->
    project (.claude/orchestra). An explicit --config PATH replaces the whole stack.
    """
    if explicit:
        return [os.path.abspath(explicit)]
    root = root or project_root()
    candidates = [
        os.path.join(PLUGIN_ROOT, "config", name),
        os.path.join(af_home(), name),
        os.path.join(root, ".claude", "orchestra", name),
    ]
    return [p for p in candidates if os.path.isfile(p)]


def merge_layers(paths, depth=2):
    """Merge JSON objects: top-level keys, then one level inside each (so a project can override
    one lane's effort without restating the lane, or one talent without restating the model)."""
    merged = {}
    for path in paths:
        data = read_json(path)
        if not isinstance(data, dict):
            raise ValueError("cannot read %s as a JSON object" % path)
        for key, val in data.items():
            if depth > 1 and isinstance(val, dict) and isinstance(merged.get(key), dict):
                merged[key] = merge_layers_obj(merged[key], val, depth - 1)
            else:
                merged[key] = val
    return merged


def merge_layers_obj(base, over, depth):
    out = dict(base)
    for key, val in over.items():
        if depth > 1 and isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = merge_layers_obj(out[key], val, depth - 1)
        else:
            out[key] = val
    return out


def describe_layers(paths):
    home = os.path.expanduser("~")
    return " + ".join(p.replace(home, "~") for p in reversed(paths)) or "(none)"


def load_lanes(root=None, explicit=None):
    layers = config_layers("lanes.json", root, explicit)
    return merge_layers(layers), layers


def load_models(root=None, explicit=None):
    layers = config_layers("models.json", root, explicit)
    # models -> model -> talent: an overlay can change one talent without restating the model
    return merge_layers(layers, depth=4), layers


def overlay_path(name, scope, root=None):
    if scope == "project":
        return os.path.join(root or project_root(), ".claude", "orchestra", name)
    return os.path.join(af_home(), name)


# ---------------------------------------------------------------- the ledger

def ledger_path():
    return os.path.join(af_home(), "ledger.jsonl")


def ledger_append(entry):
    ensure_dir(af_home())
    line = json.dumps(entry, sort_keys=False)
    with open(ledger_path(), "a") as fh:
        fh.write(line + "\n")


def ledger_read():
    """Runs with their grades folded in, oldest first. Grades are separate append-only lines."""
    runs, order = {}, []
    try:
        fh = open(ledger_path())
    except OSError:
        return []
    with fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except ValueError:
                continue
            if rec.get("type") == "grade":
                run = runs.get(rec.get("run"))
                if run is not None:
                    run["verdict"] = rec.get("verdict")
                    run["verdict_note"] = rec.get("note")
                continue
            rid = rec.get("id")
            if rid:
                runs[rid] = rec
                order.append(rid)
    return [runs[r] for r in order]


def new_run_id(lane):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    salt = hashlib.sha1(("%s%s%s" % (time.time(), os.getpid(), lane)).encode()).hexdigest()[:4]
    return "%s-%s-%s" % (stamp, lane, salt)


# ---------------------------------------------------------------- time helpers

def now():
    return time.time()


def parse_ts(value):
    """Unix seconds (int/float/str) or ISO 8601 -> float seconds, else None."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        return v / 1000.0 if v > 1e12 else v
    s = str(value).strip()
    try:
        v = float(s)
        return v / 1000.0 if v > 1e12 else v
    except ValueError:
        pass
    s = s.replace("Z", "+00:00")
    try:
        d = _dt.datetime.fromisoformat(s)
    except ValueError:
        # Python 3.9's fromisoformat wants exactly 3 or 6 fractional digits; Codex writes 3, Claude
        # Code sometimes 9. Normalise to 6.
        if "." in s:
            head, tail = s.split(".", 1)
            digits = ""
            for ch in tail:
                if not ch.isdigit():
                    break
                digits += ch
            zone = tail[len(digits):]
            try:
                d = _dt.datetime.fromisoformat("%s.%s%s" % (head, digits[:6].ljust(6, "0"), zone))
            except ValueError:
                return None
        else:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=_dt.timezone.utc)
    return d.timestamp()


def iso(ts=None):
    ts = now() if ts is None else ts
    return _dt.datetime.fromtimestamp(ts, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def local_clock(ts):
    """'Thu 14:20' in local time, or 'Oct 03 14:20' if more than six days away."""
    d = _dt.datetime.fromtimestamp(ts)
    if abs(ts - now()) > 6 * 86400:
        return d.strftime("%b %d %H:%M")
    return d.strftime("%a %H:%M")


def human_delta(seconds):
    seconds = int(max(0, seconds))
    if seconds < 90:
        return "%ds" % seconds
    minutes = seconds // 60
    if minutes < 90:
        return "%dm" % minutes
    hours, minutes = divmod(minutes, 60)
    if hours < 48:
        return "%dh %02dm" % (hours, minutes)
    days, hours = divmod(hours, 24)
    return "%dd %dh" % (days, hours)


def window_label(minutes):
    if not minutes:
        return "window"
    minutes = int(minutes)
    if minutes % 1440 == 0:
        return "%dd" % (minutes // 1440)
    if minutes % 60 == 0:
        return "%dh" % (minutes // 60)
    return "%dm" % minutes


# ---------------------------------------------------------------- output helpers

def use_color(stream=None):
    stream = stream or sys.stdout
    if os.environ.get("NO_COLOR") or os.environ.get("AF_PLAIN"):
        return False
    return hasattr(stream, "isatty") and stream.isatty()


def plain_mode():
    return bool(os.environ.get("AF_PLAIN"))


def paint(text, code, enabled):
    return "\033[%sm%s\033[0m" % (code, text) if enabled else text


def die(msg, code=2):
    sys.stderr.write(msg.rstrip() + "\n")
    sys.exit(code)

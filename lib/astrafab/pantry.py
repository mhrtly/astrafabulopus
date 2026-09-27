"""The Pantry: how much potato is left in each sack.

Reads real usage limits, never guesses them:
  * ChatGPT / Codex: the `rate_limits` snapshot Codex writes into every rollout file
    (~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl, `event_msg` / `token_count`). Every lane run
    refreshes it for free.
  * Claude: the `rate_limits` object Claude Code hands to status-line commands (5-hour and 7-day
    windows, Pro/Max plans). `af-statusline` taps it into ~/.claude/astrafabulopus/pantry/claude.json.
    Optional and experimental: `af-pantry refresh --claude-oauth` polls the undocumented endpoint
    Claude Code's own /usage screen uses.
  * Anything else (API credit balances, a team plan you watch by hand): `af-pantry set`.

Each budget gets a pressure level (plenty / watch / tight / empty / unknown). The lanes gate on it,
the Council subtracts it from its scores, and the doctrine tells the architect how to reroute.
"""
import argparse
import json
import os
import subprocess
import sys

from . import core, spud

BUDGETS = {
    "claude":  "Claude subscription · architect, opus-implementer, fable-advisor, verifier",
    "chatgpt": "ChatGPT subscription · Luna, Sol, Astra, codex review, astra-advisor",
}
STALE_AFTER = {"statusline": 6 * 3600, "oauth": 6 * 3600, "codex rollout": 12 * 3600, "manual": 24 * 3600}
CODEX_CACHE_TTL = 30
OAUTH_MIN_INTERVAL = 120


def pantry_dir():
    return os.path.join(core.af_home(), "pantry")


# ================================================================ Codex / ChatGPT

def rollout_files(max_days=6, max_files=40):
    """Newest uncompressed rollout files first. Codex compresses files older than ~7 days to .zst;
    those are history, not the present, so they are skipped."""
    base = os.path.join(core.codex_home(), "sessions")
    found, days = [], []
    try:
        for y in sorted(os.listdir(base), reverse=True):
            ypath = os.path.join(base, y)
            if not (y.isdigit() and os.path.isdir(ypath)):
                continue
            for m in sorted(os.listdir(ypath), reverse=True):
                mpath = os.path.join(ypath, m)
                if not (m.isdigit() and os.path.isdir(mpath)):
                    continue
                for d in sorted(os.listdir(mpath), reverse=True):
                    dpath = os.path.join(mpath, d)
                    if d.isdigit() and os.path.isdir(dpath):
                        days.append(dpath)
                    if len(days) >= max_days:
                        break
                if len(days) >= max_days:
                    break
            if len(days) >= max_days:
                break
    except OSError:
        return []
    for dpath in days:
        try:
            for name in os.listdir(dpath):
                if name.startswith("rollout-") and name.endswith(".jsonl"):
                    full = os.path.join(dpath, name)
                    try:
                        found.append((os.path.getmtime(full), full))
                    except OSError:
                        pass
        except OSError:
            pass
    found.sort(reverse=True)
    return [p for _, p in found[:max_files]]


def rollout_for_session(session_id):
    if not session_id:
        return None
    for path in rollout_files(max_days=4, max_files=400):
        if path.endswith(session_id + ".jsonl"):
            return path
    return None


def _tail_lines(path, max_bytes=768 * 1024):
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            if size > max_bytes:
                fh.seek(size - max_bytes)
                fh.readline()  # drop the partial line
            data = fh.read()
    except OSError:
        return []
    return data.decode("utf-8", "replace").splitlines()


def scan_rollout(path):
    """(last rate-limit event, last token-usage info) from a rollout file, newest wins.

    Returns dicts {"observed_at", "rate_limits"} and {"observed_at", "info"} or None.
    Prefers the snapshot whose limit_id is "codex" (or unset), which is the account's main limit."""
    lines = _tail_lines(path)
    rate, info, fallback_rate = None, None, None
    for raw in reversed(lines):
        if '"token_count"' not in raw:
            continue
        try:
            rec = json.loads(raw)
        except ValueError:
            continue
        payload = rec.get("payload") or {}
        if payload.get("type") != "token_count":
            continue
        ts = core.parse_ts(rec.get("timestamp")) or os.path.getmtime(path)
        if info is None and isinstance(payload.get("info"), dict):
            info = {"observed_at": ts, "info": payload["info"]}
        rl = payload.get("rate_limits")
        if isinstance(rl, dict):
            if rl.get("limit_id") in (None, "codex"):
                if rate is None:
                    rate = {"observed_at": ts, "rate_limits": rl}
            elif fallback_rate is None:
                fallback_rate = {"observed_at": ts, "rate_limits": rl}
        if rate is not None and info is not None:
            break
    return rate or fallback_rate, info


def normalize_codex(rl, observed_at, source="codex rollout"):
    windows = []
    for key in ("primary", "secondary"):
        w = rl.get(key)
        if not isinstance(w, dict) or w.get("used_percent") is None:
            continue
        minutes = w.get("window_minutes")
        resets = core.parse_ts(w.get("resets_at"))
        if resets is None and w.get("resets_in_seconds") is not None:  # older Codex builds
            resets = observed_at + float(w["resets_in_seconds"])
        windows.append({"name": core.window_label(minutes) if minutes else key,
                        "used": float(w["used_percent"]), "window_minutes": minutes,
                        "resets_at": resets})
    credits = rl.get("credits") if isinstance(rl.get("credits"), dict) else None
    return {"budget": "chatgpt", "source": source, "observed_at": observed_at,
            "plan": rl.get("plan_type"), "windows": windows, "credits": credits,
            "limit_reached": rl.get("rate_limit_reached_type") or (
                "spend_control" if rl.get("spend_control_reached") else None)}


def codex_snapshot(use_cache=True):
    cache = os.path.join(pantry_dir(), "codex-cache.json")
    files = rollout_files(max_files=12)
    newest_mtime = None
    if files:
        try:
            newest_mtime = os.path.getmtime(files[0])
        except OSError:
            pass
    if use_cache:
        cached = core.read_json(cache)
        if (isinstance(cached, dict) and cached.get("newest_mtime") == newest_mtime
                and core.now() - cached.get("cached_at", 0) < CODEX_CACHE_TTL):
            return cached.get("snapshot")
    snap = None
    for path in files:
        rate, _ = scan_rollout(path)
        if rate:
            snap = normalize_codex(rate["rate_limits"], rate["observed_at"])
            snap["file"] = path
            break
    try:
        core.write_json_atomic(cache, {"cached_at": core.now(), "newest_mtime": newest_mtime,
                                       "snapshot": snap})
    except OSError:
        pass
    return snap


def session_usage(session_id):
    """Tokens and the closing rate-limit snapshot for one Codex session (a lane run)."""
    path = rollout_for_session(session_id)
    if not path:
        return None
    rate, info = scan_rollout(path)
    out = {"file": path}
    if info:
        total = (info["info"] or {}).get("total_token_usage") or {}
        out["tokens"] = {k: total.get(k) for k in ("input_tokens", "cached_input_tokens",
                                                     "output_tokens", "reasoning_output_tokens",
                                                     "total_tokens") if total.get(k) is not None}
    if rate:
        out["snapshot"] = normalize_codex(rate["rate_limits"], rate["observed_at"])
    return out


# ================================================================ Claude

CLAUDE_WINDOWS = [("five_hour", "5h", 300), ("seven_day", "7d", 10080),
                  ("seven_day_opus", "7d opus", 10080), ("seven_day_sonnet", "7d sonnet", 10080)]


def normalize_claude_statusline(rate_limits, observed_at, extra=None):
    windows = []
    for key, label, minutes in CLAUDE_WINDOWS:
        w = rate_limits.get(key)
        if isinstance(w, dict) and w.get("used_percentage") is not None:
            windows.append({"name": label, "used": float(w["used_percentage"]),
                            "window_minutes": minutes, "resets_at": core.parse_ts(w.get("resets_at"))})
    snap = {"budget": "claude", "source": "statusline", "observed_at": observed_at,
            "windows": windows, "limit_reached": None}
    spend = rate_limits.get("spend_limit")
    if isinstance(spend, dict) and spend.get("used_percentage") is not None:
        windows.append({"name": "spend", "used": float(spend["used_percentage"]),
                        "window_minutes": None, "resets_at": core.parse_ts(spend.get("resets_at"))})
    if extra:
        snap.update(extra)
    return snap


def normalize_claude_oauth(resp, observed_at):
    windows = []
    for key, label, minutes in CLAUDE_WINDOWS:
        w = resp.get(key)
        if isinstance(w, dict) and w.get("utilization") is not None:
            windows.append({"name": label, "used": float(w["utilization"]),
                            "window_minutes": minutes, "resets_at": core.parse_ts(w.get("resets_at"))})
    snap = {"budget": "claude", "source": "oauth", "observed_at": observed_at,
            "windows": windows, "limit_reached": None}
    extra = resp.get("extra_usage")
    if isinstance(extra, dict) and extra.get("is_enabled"):
        snap["credits"] = {"extra_usage_used_cents": extra.get("used_credits"),
                           "extra_usage_limit_cents": extra.get("monthly_limit"),
                           "currency": extra.get("currency")}
    return snap


def claude_snapshot():
    data = core.read_json(os.path.join(pantry_dir(), "claude.json"))
    if not isinstance(data, dict) or not data.get("windows"):
        return None
    return data


def tap_statusline(payload):
    """Save the rate_limits from one status-line payload. Returns the snapshot or None."""
    rl = payload.get("rate_limits") if isinstance(payload, dict) else None
    if not isinstance(rl, dict) or not rl:
        return None
    model = payload.get("model") or {}
    extra = {"model": model.get("display_name") or model.get("id"),
             "model_id": model.get("id"),
             "session_id": payload.get("session_id")}
    snap = normalize_claude_statusline(rl, core.now(), extra)
    if not snap["windows"]:
        return None
    try:
        core.write_json_atomic(os.path.join(pantry_dir(), "claude.json"), snap)
    except OSError:
        pass
    return snap


def _claude_oauth_token():
    """The Claude Code OAuth access token: ~/.claude/.credentials.json, else the macOS Keychain."""
    blob = core.read_json(os.path.join(core.claude_config_dir(), ".credentials.json"))
    if not isinstance(blob, dict) and sys.platform == "darwin":
        try:
            out = subprocess.run(["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
                                 capture_output=True, text=True, timeout=10)
            if out.returncode == 0:
                blob = json.loads(out.stdout)
        except (OSError, subprocess.SubprocessError, ValueError):
            blob = None
    oauth = (blob or {}).get("claudeAiOauth") if isinstance(blob, dict) else None
    if not isinstance(oauth, dict) or not oauth.get("accessToken"):
        return None, "no Claude Code OAuth credentials found (API-key logins have no subscription windows)"
    expires = core.parse_ts(oauth.get("expiresAt"))
    if expires and expires < core.now():
        return None, "the stored OAuth token has expired; open Claude Code once to refresh it"
    return oauth["accessToken"], None


def refresh_claude_oauth(force=False):
    """Experimental: poll the endpoint Claude Code's /usage uses. Undocumented, so opt-in only."""
    current = claude_snapshot()
    if (not force and current and current.get("source") == "oauth"
            and core.now() - current.get("observed_at", 0) < OAUTH_MIN_INTERVAL):
        return current, "fresh enough (polled %s ago)" % core.human_delta(core.now() - current["observed_at"])
    token, err = _claude_oauth_token()
    if not token:
        return None, err
    import urllib.request
    import urllib.error
    req = urllib.request.Request("https://api.anthropic.com/api/oauth/usage", headers={
        "Authorization": "Bearer " + token, "anthropic-beta": "oauth-2025-04-20",
        "User-Agent": "astrafabulopus-pantry", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return None, "oauth usage request failed: %s" % exc
    snap = normalize_claude_oauth(body, core.now())
    if not snap["windows"]:
        return None, "oauth usage response had no windows"
    core.write_json_atomic(os.path.join(pantry_dir(), "claude.json"), snap)
    return snap, "ok"


# ================================================================ manual entries

def manual_path():
    return os.path.join(pantry_dir(), "manual.json")


def manual_entries():
    data = core.read_json(manual_path(), {}) or {}
    return data.get("entries", {}) if isinstance(data, dict) else {}


def manual_snapshot(name, e):
    used = e.get("used")
    if used is None and e.get("balance") is not None and e.get("of"):
        used = 100.0 * (1.0 - float(e["balance"]) / float(e["of"]))
    windows = []
    if used is not None:
        windows.append({"name": e.get("window") or "manual", "used": float(used),
                        "window_minutes": e.get("window_minutes"), "resets_at": e.get("resets_at")})
    snap = {"budget": e.get("budget") or name, "account": name, "source": "manual",
            "observed_at": e.get("set_at"), "windows": windows, "limit_reached": None, "note": e.get("note")}
    if e.get("balance") is not None:
        snap["credits"] = {"balance": e.get("balance"), "of": e.get("of"), "currency": e.get("currency") or "$"}
    return snap


# ================================================================ evaluation

def evaluate(snap, at=None):
    """Adds effective usage, pace projection and a pressure level to a snapshot (in place)."""
    at = core.now() if at is None else at
    if not snap:
        return {"level": "unknown", "windows": [], "stale": False, "reason": "no reading"}
    levels, reasons = [], []
    age = at - (snap.get("observed_at") or at)
    snap["age_seconds"] = age
    snap["stale"] = age > STALE_AFTER.get(snap.get("source"), 12 * 3600)
    for w in snap.get("windows", []):
        used, resets, minutes = w.get("used"), w.get("resets_at"), w.get("window_minutes")
        w["reset_since_reading"] = bool(resets and resets <= at)
        eff = 0.0 if w["reset_since_reading"] else used
        w["effective_used"] = eff
        w["projected"] = None
        w["dry_in_seconds"] = None
        if resets and minutes and not w["reset_since_reading"] and eff is not None:
            span = float(minutes) * 60.0
            left = resets - at
            elapsed = max(0.0, min(1.0, 1.0 - left / span))
            if elapsed >= 0.15 and eff > 0:
                w["projected"] = eff / elapsed
                rate = eff / (elapsed * span)  # percent per second
                if rate > 0:
                    dry = (100.0 - eff) / rate
                    if dry < left:
                        w["dry_in_seconds"] = dry
        lv = window_level(eff, w["projected"])
        w["level"] = lv
        levels.append(lv)
        if lv != "plenty":
            reasons.append("%s %.0f%% used%s" % (w["name"], eff, (
                ", resets %s" % core.local_clock(resets)) if resets and not w["reset_since_reading"] else ""))
    flag_is_current = False
    if snap.get("limit_reached"):
        # Only a current reading can empty a sack. After a reset (or once the reading is stale) the
        # flag is history: say so, but let the next lane run find out, since that run is also what
        # records a fresh reading. Blocking here would block the only thing that can unblock it.
        if snap["stale"] or any(w.get("reset_since_reading") for w in snap.get("windows", [])):
            levels.append("tight")
            reasons.insert(0, "limit was reached (%s) at the last reading; unconfirmed since" % snap["limit_reached"])
        else:
            levels.append("empty")
            flag_is_current = True
            reasons.insert(0, "limit reached (%s)" % snap["limit_reached"])
    credits = snap.get("credits") if isinstance(snap.get("credits"), dict) else {}
    if not flag_is_current and "empty" in levels and (credits.get("unlimited") or credits.get("has_credits")):
        # a full window with credits on the account keeps running, on credits (unless Codex itself
        # says the stop is real right now, which it would not if the credits were carrying it)
        levels = ["tight" if lv == "empty" else lv for lv in levels]
        for w in snap.get("windows", []):
            if w.get("level") == "empty":
                w["level"] = "tight"
        reasons.insert(0, "window full, running on credits%s" % (
            " (balance %s)" % credits["balance"] if credits.get("balance") is not None else ""))
    level = spud.worst(levels) if levels else "unknown"
    snap["level"] = level
    snap["reason"] = "; ".join(reasons) or ("no windows in reading" if not levels else "headroom everywhere")
    return snap


def window_level(used, projected):
    if used is None:
        return "unknown"
    if used >= 99.5:
        return "empty"
    if used >= 85 or (projected is not None and projected >= 125 and used >= 50):
        return "tight"
    if used >= 60 or (projected is not None and projected >= 100 and used >= 25):
        return "watch"
    return "plenty"


def gather(refresh_codex=True):
    """Every budget we know about, evaluated. Automatic readings win over manual ones."""
    budgets = {}
    codex = codex_snapshot(use_cache=not refresh_codex)
    claude = claude_snapshot()
    manual = manual_entries()
    for name, entry in manual.items():
        snap = manual_snapshot(name, entry)
        target = snap["budget"]
        if target in ("claude", "chatgpt"):
            if target == "claude" and not claude:
                claude = snap
            elif target == "chatgpt" and not codex:
                codex = snap
            else:
                budgets["%s (manual)" % name] = evaluate(snap)
        else:
            budgets[name] = evaluate(snap)
    budgets["claude"] = evaluate(claude) if claude else {"budget": "claude", "level": "unknown", "windows": [],
                                                           "reason": "no reading yet: install the af-statusline tap"}
    budgets["chatgpt"] = evaluate(codex) if codex else {"budget": "chatgpt", "level": "unknown", "windows": [],
                                                          "reason": "no reading yet: no Codex rollout with rate limits"}
    return budgets


def level_of(budgets, name):
    b = budgets.get(name) or {}
    return b.get("level", "unknown")


# ================================================================ advice

def advise(budgets):
    c, g = level_of(budgets, "claude"), level_of(budgets, "chatgpt")
    tips = []
    if g == "empty":
        tips.append("ChatGPT is empty: luna/sol/astra lanes, af-review and astra-advisor are unavailable until the reset. "
                    "Tell the user. Hard work -> opus-implementer; routine work -> opus-implementer at effort medium "
                    "or queue it; mechanical work -> the local lane if enabled. Never substitute silently.")
    elif g == "tight":
        tips.append("ChatGPT is tight: keep it for Luna only (cheapest per token). Send Sol-class work to "
                    "opus-implementer, skip astra-advisor and af-review unless this is a release.")
    elif g == "watch":
        tips.append("ChatGPT is frying: normal routing, Luna at effort medium for docs, renames and config; hold Astra.")
    if c == "empty":
        tips.append("Claude is empty: the architect runs on it. Finish the current step, write the state down for the "
                    "user (what is done, what is next, which lanes are queued), and stop. The user decides.")
    elif c == "tight":
        tips.append("Claude is tight: architect turns short and effort medium; delegate exploration and every build "
                    "to the codex lanes (Sol instead of opus-implementer); use astra-advisor for commitment-boundary "
                    "checks and keep fable-advisor for the one final review.")
    elif c == "watch":
        tips.append("Claude is frying: prefer codex lanes over opus-implementer and keep fable-advisor to the final review.")
    if c in ("tight", "empty") and g in ("tight", "empty"):
        tips.append("Both sacks are low: do only what the user is waiting on, push mechanical work to the local lane, "
                    "and give the user the reset times.")
    for name, lv in (("Claude", c), ("ChatGPT", g)):
        if lv == "unknown":
            tips.append("%s has no reading. Unknown is not zero: do not assume headroom. %s" % (name, (
                "Install the af-statusline tap (/astrafabulopus:setup) or run `af-pantry refresh --claude-oauth`."
                if name == "Claude" else "Any lane run records one; so does using Codex interactively.")))
    if not tips:
        tips.append("Plenty in both sacks. Route by talent (`af-council recommend <task>`), not by thrift.")
    return tips


PRESSURE_PENALTY = {"plenty": 0.0, "unknown": 0.25, "watch": 0.6, "tight": 1.6, "empty": None}


def budget_for_run_kind(kind):
    return {"codex": "chatgpt", "claude": "claude", "local": "local"}.get(kind, kind)


# ================================================================ rendering

def fmt_window(w, color):
    eff = w.get("effective_used")
    left = None if eff is None else 100.0 - eff
    parts = ["  %-9s %s %5s left" % (w["name"], spud.gauge(eff), "?" if left is None else "%.0f%%" % left)]
    resets = w.get("resets_at")
    if w.get("reset_since_reading"):
        parts.append("reset since this reading")
    elif resets:
        parts.append("resets %s (in %s)" % (core.local_clock(resets), core.human_delta(resets - core.now())))
    if w.get("dry_in_seconds"):
        parts.append(core.paint("at this pace: dry in %s" % core.human_delta(w["dry_in_seconds"]), "33", color))
    return "   ".join(parts)


def render(budgets, color=False):
    out = [spud.banner("THE PANTRY"), "how much potato is left in each sack", ""]
    names = ["claude", "chatgpt"] + sorted(k for k in budgets if k not in ("claude", "chatgpt"))
    for name in names:
        b = budgets[name]
        lv = b.get("level", "unknown")
        title = name.upper()
        desc = BUDGETS.get(name, b.get("note") or "")
        head = "%s  %s %s" % (core.paint(title, "1", color), spud.emoji(lv), spud.state(lv))
        out.append(head + ("   · " + desc if desc else ""))
        for w in b.get("windows", []):
            out.append(fmt_window(w, color))
        src = []
        if b.get("source"):
            age = b.get("age_seconds")
            src.append("source: %s%s" % (b["source"], ", %s ago" % core.human_delta(age) if age is not None else ""))
        if b.get("stale"):
            src.append(core.paint("STALE", "33", color))
        if b.get("plan"):
            src.append("plan %s" % b["plan"])
        if b.get("model"):
            src.append("architect seen: %s" % b["model"])
        cr = b.get("credits")
        if isinstance(cr, dict):
            if cr.get("unlimited"):
                src.append("credits: unlimited")
            elif cr.get("balance") is not None:
                src.append("credits: %s%s%s" % (cr.get("currency", ""), cr["balance"],
                                                 " of %s%s" % (cr.get("currency", ""), cr["of"]) if cr.get("of") else ""))
            elif cr.get("has_credits") is False:
                src.append("credits: none")
            elif cr.get("extra_usage_used_cents") is not None:
                src.append("extra usage: %.2f of %.2f %s" % (cr["extra_usage_used_cents"] / 100.0,
                                                            (cr.get("extra_usage_limit_cents") or 0) / 100.0,
                                                            cr.get("currency") or ""))
        if not b.get("windows"):
            src.append(b.get("reason", ""))
        out.append("  " + " · ".join(s for s in src if s))
        out.append("")
    out.append(core.paint("ROUTING ADVICE", "1", color))
    for tip in advise(budgets):
        out.append("  • " + tip)
    q = spud.quip()
    if q:
        out += ["", "  " + q]
    return "\n".join(out)


def brief(budgets):
    segs = []
    for name in ("claude", "chatgpt"):
        b = budgets[name]
        lv = b.get("level", "unknown")
        ws = " · ".join("%s %.0f%%" % (w["name"], w.get("effective_used") or 0) for w in b.get("windows", [])
                        if w["name"] in ("5h", "7d"))
        stale = " STALE" if b.get("stale") else ""
        segs.append("%s %s%s (%s)%s" % (name, spud.emoji(lv) + " " if spud.emoji(lv) else "", lv, ws or "no reading", stale))
    return "BUDGET " + " | ".join(segs)


def to_json(budgets):
    return {"generated_at": core.iso(), "budgets": budgets, "advice": advise(budgets)}


# ================================================================ statusline launcher

LAUNCHER = """#!/bin/bash
# Installed by `af-pantry install-statusline` (astrafabulopus). Finds the plugin and runs its status line.
# Plugin updates move the plugin directory, so this looks it up instead of hard-coding one version.
TARGET="%(target)s"
if [ ! -x "$TARGET" ]; then
  TARGET="$(find "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugins" -path '*astrafabulopus*' -name af-statusline -type f 2>/dev/null | while read -r f; do printf '%%s\\t%%s\\n' "$(stat -c %%Y "$f" 2>/dev/null || stat -f %%m "$f" 2>/dev/null)" "$f"; done | sort -rn | head -1 | cut -f2-)"
fi
if [ -z "$TARGET" ] || [ ! -x "$TARGET" ]; then echo "🥔 astrafabulopus not found"; exit 0; fi
exec "$TARGET" %(chain)s"$@"
"""


def install_statusline(chain=None):
    target = os.path.join(core.PLUGIN_ROOT, "bin", "af-statusline")
    dest_dir = core.ensure_dir(os.path.join(core.af_home(), "bin"))
    dest = os.path.join(dest_dir, "af-statusline")
    chain_arg = ""
    if chain:
        chain_arg = "--chain %s " % _shell_quote(chain)
    with open(dest, "w") as fh:
        fh.write(LAUNCHER % {"target": target, "chain": chain_arg})
    os.chmod(dest, 0o755)
    return dest


def _shell_quote(s):
    return "'" + s.replace("'", "'\"'\"'") + "'"


# ================================================================ CLI

def _parse_resets(value):
    if not value:
        return None
    v = value.strip()
    if v.startswith("+") and v[-1] in "mhd":
        mult = {"m": 60, "h": 3600, "d": 86400}[v[-1]]
        return core.now() + float(v[1:-1]) * mult
    ts = core.parse_ts(v)
    if ts is None:
        core.die("pantry: cannot read reset time %r (use ISO 8601 or +3h / +2d)" % value)
    return ts


def main(argv=None):
    p = argparse.ArgumentParser(prog="af-pantry", description="How much potato is left in each sack.")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--brief", action="store_true", help="one line, for the ROUTE block")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("show", help="the full pantry (default)")
    sub.add_parser("advise", help="routing advice only")
    g = sub.add_parser("gate", help="exit 3 if BUDGET is empty (used by the lanes)")
    g.add_argument("budget")
    s = sub.add_parser("set", help="record a reading by hand (API credits, a plan you watch yourself)")
    s.add_argument("name")
    s.add_argument("--budget", help="claude, chatgpt, or any account name (default: NAME)")
    s.add_argument("--used", type=float, help="percent used, 0-100")
    s.add_argument("--balance", type=float)
    s.add_argument("--of", type=float, help="the full amount, with --balance")
    s.add_argument("--currency", default="$")
    s.add_argument("--window", help="label, e.g. 7d or month")
    s.add_argument("--resets", help="ISO time, or +3h / +2d")
    s.add_argument("--note")
    f = sub.add_parser("forget", help="drop a manual reading")
    f.add_argument("name")
    r = sub.add_parser("refresh", help="re-read Codex rollouts; optionally poll Claude's usage endpoint")
    r.add_argument("--claude-oauth", action="store_true",
                   help="EXPERIMENTAL: poll the undocumented endpoint behind Claude Code's /usage")
    r.add_argument("--force", action="store_true")
    i = sub.add_parser("install-statusline", help="write the status-line launcher and print the settings snippet")
    i.add_argument("--chain", help="an existing status-line command to keep running in front of ours")
    args = p.parse_args(argv)
    cmd = args.cmd or "show"

    if cmd == "set":
        data = core.read_json(manual_path(), {}) or {}
        entries = data.setdefault("entries", {})
        if args.used is None and args.balance is None:
            core.die("pantry set: give --used PCT or --balance X --of Y")
        if args.balance is not None and not args.of:
            core.die("pantry set: --balance needs --of (the full amount)")
        entries[args.name] = {k: v for k, v in {
            "budget": args.budget or args.name, "used": args.used, "balance": args.balance, "of": args.of,
            "currency": args.currency if args.balance is not None else None, "window": args.window,
            "resets_at": _parse_resets(args.resets), "note": args.note, "set_at": core.now()}.items() if v is not None}
        core.write_json_atomic(manual_path(), data)
        print("pantry: recorded %s" % args.name)
        return 0
    if cmd == "forget":
        data = core.read_json(manual_path(), {}) or {}
        if data.get("entries", {}).pop(args.name, None) is None:
            core.die("pantry: no manual reading named %s" % args.name, 1)
        core.write_json_atomic(manual_path(), data)
        print("pantry: forgot %s" % args.name)
        return 0
    if cmd == "install-statusline":
        dest = install_statusline(args.chain)
        print(dest)
        print(json.dumps({"statusLine": {"type": "command", "command": dest, "refreshInterval": 60}}, indent=2))
        return 0
    if cmd == "refresh" and args.claude_oauth:
        snap, msg = refresh_claude_oauth(force=args.force)
        print("claude oauth: %s" % msg)
        if snap is None:
            return 1

    budgets = gather(refresh_codex=(cmd == "refresh"))
    if cmd == "gate":
        name = args.budget
        if name in ("local", "free", "none"):
            print("GATE %s plenty free" % name)
            return 0
        b = budgets.get(name) or {"level": "unknown", "reason": "no such budget"}
        print("GATE %s %s %s" % (name, b.get("level", "unknown"), b.get("reason", "")))
        return 3 if b.get("level") == "empty" else 0
    if args.json:
        print(json.dumps(to_json(budgets), indent=2, default=str))
    elif args.brief:
        print(brief(budgets))
    elif cmd == "advise":
        print("\n".join("• " + t for t in advise(budgets)))
    else:
        print(render(budgets, color=core.use_color()))
    return 0

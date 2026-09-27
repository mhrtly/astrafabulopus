"""The Potato Council: who is good at what, what it costs, and what actually happened.

Two kinds of knowledge, kept apart on purpose:
  * priors: config/models.json, talent scores 0-10 per dimension, with the evidence they came from.
    When a new model ships you add it relative to one you know (`af-council add NEW --like OLD
    --bump debugging=+1`) instead of re-deriving the whole ecosystem.
  * observations: ~/.claude/astrafabulopus/ledger.jsonl, one line per lane run (status, duration,
    tokens, share of the ChatGPT window) plus your pass/fail grades. `af-tryout` fills it fast.

`af-council recommend <task>` blends the two, subtracts budget pressure from the pantry, and names
the lane to use. It informs the architect; it does not overrule the doctrine.
"""
import argparse
import datetime as _dt
import json
import os
import statistics
import sys

from . import core, pantry, spud
from .lanes import find_model

DIMS = ["architecture", "implementation", "debugging", "review", "speed", "efficiency"]
DIM_SHORT = {"architecture": "ARCH", "implementation": "IMPL", "debugging": "DEBUG", "review": "REVIEW",
             "speed": "SPEED", "efficiency": "EFFIC"}
RUN_BUDGET = {"codex": "chatgpt", "claude": "claude", "local": "local"}


# ================================================================ loading

def load(root=None, explicit=None):
    cfg, layers = core.load_models(root, explicit)
    models = {k: v for k, v in (cfg.get("models") or {}).items() if isinstance(v, dict)}
    return cfg, models, layers


def active(models, include_retired=False):
    """Everyone not explicitly retired. An announced retirement date only warns: vendors say 'not
    sooner than', so the Council keeps the seat warm until you `af-council retire` it."""
    return {mid: m for mid, m in models.items() if include_retired or not m.get("retired")}


def budget_of(m):
    return m.get("budget") or RUN_BUDGET.get(m.get("run"), "chatgpt")


# ================================================================ observations

def observed(runs, mid, m):
    keys = {mid, m.get("slug")} | set(m.get("aliases") or [])
    mine = [r for r in runs if r.get("model") in keys and r.get("kind") in ("lane", "tryout", "manual", None)]
    graded = [r for r in mine if r.get("verdict") in ("pass", "fail")]
    passes = sum(1 for r in graded if r["verdict"] == "pass")
    durations = [r["duration_s"] for r in mine if isinstance(r.get("duration_s"), (int, float)) and r["duration_s"] > 0]
    outs = [r["tokens"]["output_tokens"] for r in mine
            if isinstance(r.get("tokens"), dict) and r["tokens"].get("output_tokens") is not None]
    deltas = []
    for r in mine:
        bd = r.get("budget_delta") or {}
        for w in bd.get("windows", []):
            if w.get("window") == "5h" and "delta" in w:
                deltas.append(w["delta"])
    statuses = {}
    for r in mine:
        statuses[r.get("status")] = statuses.get(r.get("status"), 0) + 1
    return {
        "runs": len(mine), "graded": len(graded), "passes": passes,
        "pass_rate": (passes / float(len(graded))) if graded else None,
        "median_duration_s": statistics.median(durations) if durations else None,
        "median_output_tokens": statistics.median(outs) if outs else None,
        "median_5h_delta": statistics.median(deltas) if deltas else None,
        "statuses": statuses,
    }


def expected_pass_rate(m):
    impl = (m.get("talent") or {}).get("implementation", 7)
    return min(0.97, 0.4 + 0.06 * float(impl))


def observed_adjustment(m, obs):
    """Nudge a prior by graded evidence. Weight grows with the number of graded runs (n / (n + 8)),
    so three lucky runs cannot crown a model and thirty unlucky ones cannot be ignored."""
    if not obs or not obs.get("graded"):
        return 0.0, None
    n = obs["graded"]
    w = n / (n + 8.0)
    exp = expected_pass_rate(m)
    adj = w * (obs["pass_rate"] - exp) * 5.0
    return adj, "observed %d/%d passed vs ~%.0f%% expected (%+.2f)" % (obs["passes"], n, exp * 100, adj)


# ================================================================ scoring

def talent_score(m, weights):
    t = m.get("talent") or {}
    total, wsum = 0.0, 0.0
    for dim, w in weights.items():
        if dim in t and t[dim] is not None:
            total += float(t[dim]) * float(w)
            wsum += float(w)
    return total / wsum * sum(float(w) for w in weights.values()) if wsum else 0.0


def lane_hint(mid, m, task, lanes):
    run = m.get("run")
    slug = m.get("slug") or mid
    if run == "codex":
        if task in ("review",):
            return "af-review --model %s" % slug
        if task in ("consult",):
            return "astra-advisor (af-consult --model %s)" % slug
        for lane_name, agent in (("routine", "luna-implementer"), ("complex", "sol-implementer"),
                                 ("frontier", "astra-implementer")):
            lane = lanes.get(lane_name) or {}
            if lane.get("model") == slug:
                return "%s (af-lane %s)" % (agent, lane_name)
        lane_for_task = {"routine": "routine", "mechanical": "routine", "complex": "complex",
                         "frontier": "frontier"}.get(task, "complex")
        return "af-lane %s SPEC --model %s" % (lane_for_task, slug)
    if run == "claude":
        alias = slug
        if task == "architect":
            return "/model %s" % alias
        if task in ("review", "consult"):
            return "fable-advisor" + ("" if alias == "fable" else " (Agent model: %s)" % alias)
        return "opus-implementer" + ("" if alias == "opus" else " (Agent model: %s)" % alias)
    if run == "local":
        return "local-implementer (af-lane local)"
    return "?"


def recommend(task, cfg, models, lanes, budgets, runs, architect=None, today=None):
    tasks = cfg.get("tasks") or {}
    if task not in tasks:
        raise KeyError(task)
    spec = tasks[task]
    weights = spec.get("weights") or {}
    runs_on = spec.get("runs_on") or ["codex", "claude", "local"]
    reserve = (cfg.get("scoring") or {}).get("budget_reserve") or {}
    diversity = float((cfg.get("scoring") or {}).get("diversity_bonus", 0.5))
    today = today or _dt.date.today()
    arch_vendor = None
    if architect:
        _, am = find_model({"models": models}, architect)
        arch_vendor = (am or {}).get("vendor")
    rows, excluded = [], []
    for mid, m in active(models).items():
        run = m.get("run")
        if run not in runs_on:
            continue
        name = m.get("name", mid)
        if run == "local" and not (lanes.get("local") or {}).get("enabled", False):
            excluded.append((name, "local lane disabled in lanes.json"))
            continue
        budget = budget_of(m)
        level = pantry.level_of(budgets, budget) if budget in ("claude", "chatgpt") else "plenty"
        penalty = pantry.PRESSURE_PENALTY.get(level, 0.25)
        if penalty is None:
            excluded.append((name, "%s budget is empty" % budget))
            continue
        base = talent_score(m, weights)
        notes = []
        score = base
        if penalty:
            score -= penalty * float(spec.get("pressure_sensitivity", 1.0))
            notes.append("%s %s (-%.2f)" % (budget, level, penalty * float(spec.get("pressure_sensitivity", 1.0))))
        r = float(reserve.get(budget, 0.0))
        if r and task != "architect":
            score -= r
            notes.append("%s reserve (-%.2f)" % (budget, r))
        if arch_vendor and task in ("complex", "review", "consult", "frontier") and m.get("vendor") != arch_vendor:
            score += diversity
            notes.append("cross-vendor vs architect (+%.2f)" % diversity)
        if m.get("retires"):
            try:
                days = (_dt.date.fromisoformat(m["retires"]) - today).days
            except ValueError:
                days = None
            if days is not None and days < 0:
                score -= 0.6
                notes.append("past its announced retirement %s; check it still runs (-0.60)" % m["retires"])
            elif days is not None and days <= 45:
                score -= 0.3
                notes.append("retires %s (-0.30)" % m["retires"])
        adj, why = observed_adjustment(m, observed(runs, mid, m))
        if why:
            score += adj
            notes.append(why)
        rows.append({"id": mid, "name": name, "score": round(score, 3), "base": round(base, 3),
                     "budget": budget, "level": level, "notes": notes,
                     "how": lane_hint(mid, m, task, lanes),
                     "effort": (spec.get("effort") or {}).get(run) or m.get("default_effort")})
    rows.sort(key=lambda r: -r["score"])
    return rows, excluded


# ================================================================ rendering

def fmt_price(m):
    p = m.get("price") or {}
    if m.get("run") == "local":
        return "free"
    if p.get("input") is None or p.get("output") is None:
        return "?"
    def f(x):
        return ("%g" % x)
    return "%s/%s" % (f(p["input"]), f(p["output"]))


def fmt_obs(obs):
    if not obs["runs"]:
        return "no runs yet"
    parts = ["%d run%s" % (obs["runs"], "" if obs["runs"] == 1 else "s")]
    if obs["graded"]:
        parts.append("%d/%d pass" % (obs["passes"], obs["graded"]))
    if obs["median_duration_s"] is not None:
        parts.append("~%s" % core.human_delta(obs["median_duration_s"]))
    if obs["median_5h_delta"] is not None:
        parts.append("%.1f%% of 5h/run" % obs["median_5h_delta"])
    return " · ".join(parts)


def render_roster(models, runs, color=False):
    out = [spud.banner("THE POTATO COUNCIL"), "who is good at what (0-10), what it costs ($/1M in/out, API list), what happened", ""]
    head = "%-17s %-7s" % ("MODEL", "RUNS ON") + "".join("%7s" % DIM_SHORT[d] for d in DIMS) + "  %-10s %s" % ("$ IN/OUT", "OBSERVED")
    out.append(core.paint(head, "1", color))
    order = sorted(models.items(), key=lambda kv: (kv[1].get("run") != "claude", kv[1].get("run") != "codex",
                                                   -float((kv[1].get("talent") or {}).get("implementation", 0))))
    for mid, m in order:
        t = m.get("talent") or {}
        row = "%-17s %-7s" % (m.get("name", mid)[:17], m.get("run", "?"))
        row += "".join("%7s" % ("%.1f" % t[d] if t.get(d) is not None else "?") for d in DIMS)
        row += "  %-10s %s" % (fmt_price(m), fmt_obs(observed(runs, mid, m)))
        if m.get("retires"):
            row += core.paint("  (retires %s)" % m["retires"], "33", color)
        out.append(row)
    out += ["", core.paint("POTATO OR NOT-ATO", "1", color)]
    for mid, m in order:
        if m.get("spud"):
            out.append("  %-17s %s" % (m.get("name", mid)[:17], m["spud"]))
    q = spud.quip(len(runs))
    if q:
        out += ["", "  " + q]
    return "\n".join(out)


def render_card(mid, m, runs, lanes):
    t = m.get("talent") or {}
    obs = observed(runs, mid, m)
    out = [spud.banner(m.get("name", mid)), ""]
    out.append("  id %s · slug %s · vendor %s · runs on %s · budget %s" % (
        mid, m.get("slug", mid), m.get("vendor", "?"), m.get("run", "?"), budget_of(m)))
    if m.get("released") or m.get("retires"):
        out.append("  released %s%s" % (m.get("released", "?"), " · retires %s" % m["retires"] if m.get("retires") else ""))
    out.append("  price %s per 1M tokens (API list; subscriptions absorb it, but it predicts how fast a window drains)"
               % fmt_price(m))
    if m.get("efforts"):
        out.append("  efforts %s (default %s)" % (", ".join(m["efforts"]), m.get("default_effort", "?")))
    out.append("")
    for d in DIMS:
        out.append("  %-15s %s %s" % (d, spud.talent_bar(t.get(d)), "?" if t.get(d) is None else "%.1f" % t[d]))
    adj, why = observed_adjustment(m, obs)
    out += ["", "  observed: %s" % fmt_obs(obs)]
    if why:
        out.append("  " + why)
    if obs["median_output_tokens"] is not None:
        out.append("  median output tokens per run: {:,}".format(int(obs["median_output_tokens"])))
    if m.get("spud"):
        out += ["", "  🥔 " + m["spud"] if not core.plain_mode() else "  " + m["spud"]]
    if m.get("notes"):
        out += ["", "  notes: " + m["notes"]]
    for ev in m.get("evidence") or []:
        out.append("  evidence: " + ev)
    if m.get("rated"):
        out.append("  priors last rated %s" % m["rated"])
    return "\n".join(out)


# ================================================================ writing overlays

def _load_overlay(name, scope, root):
    path = core.overlay_path(name, scope, root)
    return path, (core.read_json(path, {}) or {})


def _parse_assignments(items, base):
    out = {}
    for item in items or []:
        if "=" not in item:
            core.die("council: expected dim=value, got %r" % item)
        dim, val = item.split("=", 1)
        dim = dim.strip()
        if dim not in DIMS:
            core.die("council: unknown talent %r (one of %s)" % (dim, ", ".join(DIMS)))
        val = val.strip()
        try:
            if val[:1] in "+-":
                new = float(base.get(dim, 5)) + float(val)
            else:
                new = float(val)
        except ValueError:
            core.die("council: %r is not a number" % val)
        out[dim] = round(max(0.0, min(10.0, new)), 2)
    return out


def cmd_add(args, cfg, models):
    if args.id in models and not args.force:
        core.die("council: %s already sits on the Council (use rate, or --force to replace)" % args.id)
    anchor_id, anchor = (None, {})
    if args.like:
        anchor_id, anchor = find_model(cfg, args.like)
        if not anchor:
            core.die("council: no model %r to compare against" % args.like)
    entry = {}
    for key in ("vendor", "run", "budget", "efforts", "default_effort", "talent"):
        if key in anchor:
            entry[key] = json.loads(json.dumps(anchor[key]))
    entry["name"] = args.name or args.id
    entry["slug"] = args.slug or args.id
    for key in ("vendor", "run", "budget", "released", "retires", "notes", "spud"):
        val = getattr(args, key)
        if val:
            entry[key] = val
    if args.efforts:
        entry["efforts"] = [e.strip() for e in args.efforts.split(",") if e.strip()]
    if args.price:
        try:
            parts = [float(x) for x in args.price.split("/")]
        except ValueError:
            core.die("council: --price is IN/OUT or IN/CACHED/OUT dollars per 1M tokens")
        entry["price"] = ({"input": parts[0], "output": parts[1]} if len(parts) == 2
                          else {"input": parts[0], "cached": parts[1], "output": parts[2]})
    talent = entry.get("talent") or {}
    talent.update(_parse_assignments(args.set, talent))
    talent.update(_parse_assignments(args.bump, talent))
    entry["talent"] = talent
    missing = [d for d in DIMS if d not in talent]
    if missing:
        core.die("council: %s needs talents for %s (use --like MODEL, or --set dim=N)" % (args.id, ", ".join(missing)))
    if not entry.get("run"):
        core.die("council: say how it runs: --run codex|claude|local (or --like a model that runs the same way)")
    entry["rated"] = _dt.date.today().isoformat()
    entry["evidence"] = ["added %s%s" % (entry["rated"], " relative to %s" % anchor_id if anchor_id else "")]
    path, overlay = _load_overlay("models.json", args.scope, args.root)
    overlay.setdefault("models", {})[args.id] = entry
    core.write_json_atomic(path, overlay)
    print("council: %s now sits on the Council (%s)" % (entry["name"], path))
    print("next: `af-tryout %s` for real numbers, then `af-council promote %s --lane routine` if it earns it."
          % (args.id, args.id))
    return 0


def cmd_rate(args, cfg, models):
    mid, m = find_model(cfg, args.id)
    if not m:
        core.die("council: no model %r" % args.id)
    changes = _parse_assignments(args.assignments, m.get("talent") or {})
    path, overlay = _load_overlay("models.json", args.scope, args.root)
    entry = overlay.setdefault("models", {}).setdefault(mid, {})
    entry.setdefault("talent", {}).update(changes)
    entry["rated"] = _dt.date.today().isoformat()
    if args.why:
        entry.setdefault("evidence", list(m.get("evidence") or [])).append("%s: %s" % (entry["rated"], args.why))
    core.write_json_atomic(path, overlay)
    print("council: re-rated %s: %s (%s)" % (m.get("name", mid), ", ".join("%s=%s" % kv for kv in changes.items()), path))
    return 0


def cmd_retire(args, cfg, models):
    mid, m = find_model(cfg, args.id)
    if not m:
        core.die("council: no model %r" % args.id)
    path, overlay = _load_overlay("models.json", args.scope, args.root)
    overlay.setdefault("models", {}).setdefault(mid, {})["retired"] = True
    core.write_json_atomic(path, overlay)
    print("council: %s has been thanked for its service and returned to the soil. 🥔" % m.get("name", mid))
    return 0


def cmd_promote(args, cfg, models):
    mid, m = find_model(cfg, args.id)
    if not m:
        core.die("council: no model %r" % args.id)
    lanes, _ = core.load_lanes(args.root)
    lane = lanes.get(args.lane)
    if not isinstance(lane, dict) or "model" not in lane:
        core.die("council: no lane %r in lanes.json" % args.lane)
    provider = lane.get("provider", "codex")
    run = m.get("run")
    if provider == "anthropic" or run == "claude":
        core.die("council: Claude models are pinned in agent frontmatter (model: opus / fable), not in lanes.json; "
                 "edit the agent or pass the Agent tool's model override")
    if (provider == "codex") != (run == "codex"):
        core.die("council: lane %s runs %s; %s runs on %s" % (args.lane, provider, m.get("name", mid), run))
    if args.effort and m.get("efforts") and args.effort not in m["efforts"]:
        core.die("council: %s does not list effort %s (known: %s)" % (m.get("name", mid), args.effort, ", ".join(m["efforts"])))
    path, overlay = _load_overlay("lanes.json", args.scope, args.root)
    entry = overlay.setdefault(args.lane, {})
    entry["model"] = m.get("slug", mid)
    if args.effort:
        entry["effort"] = args.effort
    core.write_json_atomic(path, overlay)
    print("council: %s now runs the %s lane%s (%s)" % (m.get("name", mid), args.lane,
                                                        " at effort %s" % args.effort if args.effort else "", path))
    return 0


def cmd_grade(args):
    runs = core.ledger_read()
    target = None
    if args.run == "last":
        for r in reversed(runs):
            if args.lane and r.get("lane") != args.lane:
                continue
            target = r
            break
    else:
        target = next((r for r in runs if r.get("id") == args.run), None)
    if not target:
        core.die("council: no run %r in the ledger" % args.run, 1)
    core.ledger_append({"type": "grade", "run": target["id"], "verdict": args.verdict,
                        "note": args.note, "ts": core.iso()})
    print("council: %s graded %s%s" % (target["id"], args.verdict, " — " + args.note if args.note else ""))
    return 0


def cmd_log(args, cfg):
    mid, m = find_model(cfg, args.model)
    run_id = core.new_run_id(args.lane)
    entry = {"id": run_id, "ts": core.iso(), "kind": "manual", "lane": args.lane,
             "provider": (m or {}).get("run", "?"), "model": (m or {}).get("slug", args.model),
             "effort": args.effort, "status": args.status, "duration_s": args.duration,
             "tokens": None, "budget_delta": None, "verdict": args.verified, "note": args.note}
    core.ledger_append(entry)
    print("RUN: %s logged%s" % (run_id, "" if m else " (model not on the Council yet)"))
    return 0


def cmd_ledger(args, cfg):
    runs = core.ledger_read()
    if args.model:
        mid, m = find_model(cfg, args.model)
        keys = {args.model} | ({mid, m.get("slug")} | set(m.get("aliases") or []) if m else set())
        runs = [r for r in runs if r.get("model") in keys]
    runs = runs[-args.limit:]
    if args.json:
        print(json.dumps(runs, indent=2))
        return 0
    if not runs:
        print("the ledger is empty. every lane run writes one line; af-tryout writes three.")
        return 0
    for r in runs:
        tok = (r.get("tokens") or {}).get("output_tokens")
        d5 = next((w.get("delta") for w in (r.get("budget_delta") or {}).get("windows", [])
                   if w.get("window") == "5h" and "delta" in w), None)
        print("%-34s %-8s %-14s %-7s %-9s %6s %9s %8s  %s" % (
            r.get("id", "?"), r.get("kind", "?"), r.get("model", "?")[:14], r.get("effort") or "-",
            r.get("status", "?"), "%ss" % r.get("duration_s", "?"),
            "{:,}".format(tok) if isinstance(tok, int) else "-",
            "%+.1f%%" % d5 if d5 is not None else "-", r.get("verdict") or "ungraded"))
    return 0


def cmd_resolve(args, cfg):
    mid, m = find_model(cfg, args.model)
    if not m:
        print("unknown\t%s\t%s" % (args.model, args.model))
        return 1
    print("%s\t%s\t%s" % (m.get("run", "?"), m.get("slug", mid), mid))
    return 0


# ================================================================ CLI

def main(argv=None):
    p = argparse.ArgumentParser(prog="af-council", description="The Potato Council: model talent and token thrift.")
    p.add_argument("--root", help="project root (default: the git top level)")
    p.add_argument("--config", help="use only this models.json")
    p.add_argument("--json", action="store_true")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("roster", help="everyone on the Council (default)")
    a = sub.add_parser("show", help="one model's card"); a.add_argument("id")
    a = sub.add_parser("recommend", help="best model for a task, budget-aware")
    a.add_argument("task"); a.add_argument("--architect", help="the architect's model, for cross-vendor credit")
    a.add_argument("--top", type=int, default=3)
    sub.add_parser("tasks", help="task classes and their weights")
    a = sub.add_parser("add", help="seat a new model, relative to one you know")
    a.add_argument("id"); a.add_argument("--like"); a.add_argument("--name"); a.add_argument("--slug")
    a.add_argument("--vendor"); a.add_argument("--run", choices=["codex", "claude", "local"]); a.add_argument("--budget")
    a.add_argument("--released"); a.add_argument("--retires"); a.add_argument("--efforts"); a.add_argument("--price")
    a.add_argument("--notes"); a.add_argument("--spud"); a.add_argument("--set", action="append")
    a.add_argument("--bump", action="append"); a.add_argument("--force", action="store_true")
    a.add_argument("--scope", choices=["user", "project"], default="user")
    a = sub.add_parser("rate", help="adjust talents: dim=8 or dim=+0.5")
    a.add_argument("id"); a.add_argument("assignments", nargs="+"); a.add_argument("--why")
    a.add_argument("--scope", choices=["user", "project"], default="user")
    a = sub.add_parser("retire", help="take a model off the Council"); a.add_argument("id")
    a.add_argument("--scope", choices=["user", "project"], default="user")
    a = sub.add_parser("promote", help="make a model the default for a codex lane")
    a.add_argument("id"); a.add_argument("--lane", required=True); a.add_argument("--effort")
    a.add_argument("--scope", choices=["user", "project"], default="user")
    a = sub.add_parser("grade", help="record whether a run's work passed your verification")
    a.add_argument("run", help="run id from the LANE REPORT, or 'last'")
    a.add_argument("verdict", choices=["pass", "fail"]); a.add_argument("--lane"); a.add_argument("--note")
    a = sub.add_parser("log", help="record a run that did not go through af-lane (e.g. opus-implementer)")
    a.add_argument("--model", required=True); a.add_argument("--lane", default="claude_builder")
    a.add_argument("--status", default="complete"); a.add_argument("--effort")
    a.add_argument("--verified", choices=["pass", "fail"]); a.add_argument("--duration", type=int)
    a.add_argument("--note")
    a = sub.add_parser("ledger", help="recent runs"); a.add_argument("--model"); a.add_argument("--limit", type=int, default=20)
    a = sub.add_parser("resolve", help="(for scripts) MODEL -> run, slug, id"); a.add_argument("model")
    args = p.parse_args(argv)
    cmd = args.cmd or "roster"

    try:
        cfg, models, layers = load(args.root, args.config)
    except ValueError as exc:
        core.die("council: %s" % exc)
    if cmd == "add":
        return cmd_add(args, cfg, models)
    if cmd == "rate":
        return cmd_rate(args, cfg, models)
    if cmd == "retire":
        return cmd_retire(args, cfg, models)
    if cmd == "promote":
        return cmd_promote(args, cfg, models)
    if cmd == "grade":
        return cmd_grade(args)
    if cmd == "log":
        return cmd_log(args, cfg)
    if cmd == "ledger":
        return cmd_ledger(args, cfg)
    if cmd == "resolve":
        return cmd_resolve(args, cfg)

    runs = core.ledger_read()
    color = core.use_color()
    if cmd == "tasks":
        tasks = cfg.get("tasks") or {}
        if args.json:
            print(json.dumps(tasks, indent=2))
            return 0
        for name, t in tasks.items():
            w = ", ".join("%s %.2f" % kv for kv in sorted((t.get("weights") or {}).items(), key=lambda kv: -kv[1]))
            print("%-11s %s\n            weights: %s · runs on: %s" % (name, t.get("about", ""), w, ", ".join(t.get("runs_on", []))))
        return 0
    if cmd == "show":
        mid, m = find_model(cfg, args.id)
        if not m:
            core.die("council: no model %r (af-council roster lists them)" % args.id, 1)
        lanes, _ = core.load_lanes(args.root)
        if args.json:
            print(json.dumps({"id": mid, "model": m, "observed": observed(runs, mid, m)}, indent=2))
        else:
            print(render_card(mid, m, runs, lanes))
        return 0
    if cmd == "recommend":
        lanes, _ = core.load_lanes(args.root)
        budgets = pantry.gather(refresh_codex=False)
        architect = args.architect or (budgets.get("claude") or {}).get("model_id")
        try:
            rows, excluded = recommend(args.task, cfg, active(models), lanes, budgets, runs, architect)
        except KeyError:
            core.die("council: unknown task %r (one of %s)" % (args.task, ", ".join(cfg.get("tasks") or {})))
        if args.json:
            print(json.dumps({"task": args.task, "architect": architect, "ranking": rows,
                              "excluded": excluded, "budget": pantry.brief(budgets)}, indent=2))
            return 0
        if not rows:
            print("NO PICK for %s: every candidate is excluded." % args.task)
            for name, why in excluded:
                print("  excluded: %s — %s" % (name, why))
            return 1
        top = rows[0]
        print("PICK for %s: %s (score %.2f) → %s%s" % (args.task, top["name"], top["score"], top["how"],
                                                       " · effort %s" % top["effort"] if top.get("effort") else ""))
        if top["notes"]:
            print("  why: base %.2f; %s" % (top["base"], "; ".join(top["notes"])))
        if len(rows) > 1 and top["score"] - rows[1]["score"] < 0.25:
            print("  close call: %s is within %.2f. Priors are not that precise; the doctrine's lane table breaks the tie."
                  % (rows[1]["name"], top["score"] - rows[1]["score"]))
        for r in rows[1:args.top]:
            print("  runner-up: %s %.2f → %s%s" % (r["name"], r["score"], r["how"],
                                                  " (%s)" % "; ".join(r["notes"]) if r["notes"] else ""))
        for name, why in excluded:
            print("  excluded: %s — %s" % (name, why))
        print("  " + pantry.brief(budgets))
        if architect:
            print("  architect: %s" % architect)
        return 0
    if args.json:
        print(json.dumps({mid: dict(m, observed=observed(runs, mid, m)) for mid, m in active(models).items()}, indent=2))
        return 0
    print(render_roster(active(models), runs, color))
    print("\n  layers: %s" % core.describe_layers(layers))
    return 0

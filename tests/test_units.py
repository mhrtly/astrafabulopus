"""Unit tests for the Python core. Run by tests/run.sh with PYTHONPATH=lib."""
import json
import os
import tempfile
import time
import unittest

from astrafab import core, council, lanes, pantry


class TimeParsing(unittest.TestCase):
    def test_iso_forms(self):
        self.assertAlmostEqual(core.parse_ts("2026-09-27T22:51:58Z"), 1790549518.0, places=0)
        self.assertAlmostEqual(core.parse_ts("2026-09-27T22:51:58.763123456Z"), 1790549518.763, places=2)
        self.assertAlmostEqual(core.parse_ts("2026-09-27T22:51:58+00:00"), 1790549518.0, places=0)

    def test_epochs(self):
        self.assertEqual(core.parse_ts(1790549518), 1790549518.0)
        self.assertEqual(core.parse_ts(1790549518000), 1790549518.0)  # milliseconds
        self.assertEqual(core.parse_ts("1790549518"), 1790549518.0)
        self.assertIsNone(core.parse_ts("potato"))
        self.assertIsNone(core.parse_ts(None))

    def test_labels(self):
        self.assertEqual(core.window_label(300), "5h")
        self.assertEqual(core.window_label(10080), "7d")
        self.assertEqual(core.window_label(45), "45m")


class Evaluation(unittest.TestCase):
    def snap(self, used, minutes=300, resets_in=3600, observed_ago=60):
        now = time.time()
        return {"budget": "chatgpt", "source": "codex rollout", "observed_at": now - observed_ago,
                "windows": [{"name": core.window_label(minutes), "used": used, "window_minutes": minutes,
                             "resets_at": now + resets_in}], "limit_reached": None}

    def test_levels(self):
        self.assertEqual(pantry.evaluate(self.snap(10, resets_in=17000))["level"], "plenty")
        self.assertEqual(pantry.evaluate(self.snap(65, resets_in=600))["level"], "watch")
        self.assertEqual(pantry.evaluate(self.snap(90, resets_in=600))["level"], "tight")
        self.assertEqual(pantry.evaluate(self.snap(100))["level"], "empty")

    def test_reset_since_reading_is_fresh(self):
        s = pantry.evaluate(self.snap(100, resets_in=-5))
        self.assertEqual(s["level"], "plenty")
        self.assertTrue(s["windows"][0]["reset_since_reading"])
        self.assertEqual(s["windows"][0]["effective_used"], 0.0)

    def test_pace_projection(self):
        # 50% used a quarter of the way through a 5h window: on pace for 200%, dry well before reset
        s = pantry.evaluate(self.snap(50, resets_in=int(0.75 * 300 * 60)))
        w = s["windows"][0]
        self.assertAlmostEqual(w["projected"], 200, delta=2)
        self.assertEqual(s["level"], "tight")
        self.assertIsNotNone(w["dry_in_seconds"])
        self.assertAlmostEqual(w["dry_in_seconds"], 0.25 * 300 * 60, delta=60)

    def test_early_window_does_not_project(self):
        s = pantry.evaluate(self.snap(20, resets_in=int(0.95 * 300 * 60)))
        self.assertIsNone(s["windows"][0]["projected"])
        self.assertEqual(s["level"], "plenty")

    def test_limit_reached_flag_empties(self):
        s = self.snap(40)
        s["limit_reached"] = "workspace_member_credits_depleted"
        self.assertEqual(pantry.evaluate(s)["level"], "empty")

    def test_limit_flag_after_reset_is_not_empty(self):
        s = self.snap(100, resets_in=-30)
        s["limit_reached"] = "rate_limit_reached"
        ev = pantry.evaluate(s)
        self.assertEqual(ev["level"], "tight")
        self.assertIn("unconfirmed", ev["reason"])

    def test_limit_flag_on_stale_reading_is_not_empty(self):
        s = self.snap(40, observed_ago=13 * 3600, resets_in=90000)
        s["limit_reached"] = "rate_limit_reached"
        self.assertEqual(pantry.evaluate(s)["level"], "tight")

    def test_credits_keep_a_full_window_running(self):
        s = self.snap(100)
        s["credits"] = {"has_credits": True, "balance": "12"}
        ev = pantry.evaluate(s)
        self.assertEqual(ev["level"], "tight")
        self.assertIn("credits", ev["reason"])

    def test_current_limit_flag_is_not_softened_by_credits(self):
        s = self.snap(100)
        s["limit_reached"] = "rate_limit_reached"
        s["credits"] = {"has_credits": True, "balance": "12"}
        self.assertEqual(pantry.evaluate(s)["level"], "empty")

    def test_staleness(self):
        self.assertTrue(pantry.evaluate(self.snap(10, observed_ago=13 * 3600, resets_in=90000))["stale"])


class Normalizing(unittest.TestCase):
    def test_codex_resets_in_seconds_fallback(self):
        s = pantry.normalize_codex({"primary": {"used_percent": 42, "window_minutes": 300, "resets_in_seconds": 600}}, 1000.0)
        self.assertEqual(s["windows"][0]["resets_at"], 1600.0)
        self.assertEqual(s["windows"][0]["name"], "5h")

    def test_claude_statusline_and_oauth(self):
        a = pantry.normalize_claude_statusline({"five_hour": {"used_percentage": 23.5, "resets_at": 2000},
                                                "seven_day": {"used_percentage": 41.2, "resets_at": 3000}}, 1000)
        self.assertEqual([w["name"] for w in a["windows"]], ["5h", "7d"])
        b = pantry.normalize_claude_oauth({"five_hour": {"utilization": 12, "resets_at": "2026-09-28T01:00:00Z"},
                                           "seven_day_opus": {"utilization": 30, "resets_at": None},
                                           "extra_usage": {"is_enabled": True, "used_credits": 250, "monthly_limit": 1000}}, 1000)
        self.assertEqual([w["name"] for w in b["windows"]], ["5h", "7d opus"])
        self.assertEqual(b["credits"]["extra_usage_used_cents"], 250)

    def test_tap_ignores_payloads_without_limits(self):
        self.assertIsNone(pantry.tap_statusline({"model": {"id": "x"}}))
        self.assertIsNone(pantry.tap_statusline("garbage"))

    def test_scan_prefers_the_codex_limit(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "rollout-x.jsonl")
            with open(p, "w") as fh:
                for lid, used in (("codex", 10), ("gpt-6-astra", 99)):
                    fh.write(json.dumps({"timestamp": "2026-09-27T10:00:00Z", "type": "event_msg", "payload": {
                        "type": "token_count", "info": None,
                        "rate_limits": {"limit_id": lid, "primary": {"used_percent": used, "window_minutes": 300}}}}) + "\n")
            rate, _ = pantry.scan_rollout(p)
            self.assertEqual(rate["rate_limits"]["limit_id"], "codex")


class Deltas(unittest.TestCase):
    def test_same_window_only(self):
        before = {"windows": [{"name": "5h", "used": 10.0, "resets_at": 5000}, {"name": "7d", "used": 3, "resets_at": 90000}]}
        after = {"budget": "chatgpt", "windows": [{"name": "5h", "used": 11.5, "resets_at": 5030},
                                                  {"name": "7d", "used": 4, "resets_at": 99999}]}
        rows = {r["window"]: r for r in lanes._window_delta(before, after)["windows"]}
        self.assertEqual(rows["5h"]["delta"], 1.5)
        self.assertNotIn("delta", rows["7d"])  # different window: unknown, not zero

    def test_no_before(self):
        rows = lanes._window_delta(None, {"windows": [{"name": "5h", "used": 3, "resets_at": 1}]})["windows"]
        self.assertNotIn("delta", rows[0])


class Layers(unittest.TestCase):
    def test_merge_depths(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = os.path.join(d, "a.json"), os.path.join(d, "b.json")
            with open(a, "w") as fh:
                json.dump({"routine": {"model": "x", "effort": "high", "timeout_seconds": 5},
                           "models": {"m": {"name": "M", "talent": {"speed": 1, "review": 2}}}}, fh)
            with open(b, "w") as fh:
                json.dump({"routine": {"effort": "low"}, "models": {"m": {"talent": {"speed": 9}}}}, fh)
            lanes_merged = core.merge_layers([a, b])
            self.assertEqual(lanes_merged["routine"], {"model": "x", "effort": "low", "timeout_seconds": 5})
            models_merged = core.merge_layers([a, b], depth=4)
            self.assertEqual(models_merged["models"]["m"], {"name": "M", "talent": {"speed": 9, "review": 2}})


class Snapshots(unittest.TestCase):
    def test_changed(self):
        before = {"a": ("??", "1"), "b": (" M", "2"), "c": (" M", "3")}
        after = {"a": ("??", "9"), "b": (" M", "2"), "d": ("??", "4")}
        self.assertEqual(lanes.changed(before, after), [("??", "a"), ("clean", "c"), ("??", "d")])


class Council(unittest.TestCase):
    def setUp(self):
        self.cfg, self.models, _ = council.load(explicit=os.path.join(core.PLUGIN_ROOT, "config", "models.json"))
        self.lanes = {"routine": {"model": "gpt-6-luna"}, "complex": {"model": "gpt-6-sol"},
                      "frontier": {"model": "gpt-6-astra"}, "local": {"enabled": False}}

    def budgets(self, claude="plenty", chatgpt="plenty"):
        return {"claude": {"level": claude}, "chatgpt": {"level": chatgpt}}

    def pick(self, task, **kw):
        rows, excluded = council.recommend(task, self.cfg, council.active(self.models), self.lanes,
                                           kw.pop("budgets", self.budgets()), kw.pop("runs", []), **kw)
        return rows, excluded

    def test_doctrine_defaults(self):
        self.assertEqual(self.pick("routine")[0][0]["id"], "gpt-6-luna")
        self.assertEqual(self.pick("architect")[0][0]["id"], "claude-opus-5-5")
        self.assertEqual(self.pick("review")[0][0]["id"], "claude-fable-5-1")
        self.assertEqual(self.pick("complex", architect="claude-opus-5-5")[0][0]["id"], "gpt-6-sol")

    def test_empty_budget_excludes_and_tight_penalizes(self):
        rows, excluded = self.pick("routine", budgets=self.budgets(chatgpt="empty"))
        self.assertTrue(all(r["budget"] != "chatgpt" for r in rows))
        self.assertTrue(any("chatgpt budget is empty" in why for _, why in excluded))
        tight = {r["id"]: r["score"] for r in self.pick("routine", budgets=self.budgets(chatgpt="tight"))[0]}
        easy = {r["id"]: r["score"] for r in self.pick("routine")[0]}
        self.assertLess(tight["gpt-6-luna"], easy["gpt-6-luna"])

    def test_observed_evidence_moves_scores(self):
        m = self.models["gpt-6-luna"]
        runs = [{"model": "gpt-6-luna", "kind": "lane", "verdict": "fail"} for _ in range(20)]
        adj, why = council.observed_adjustment(m, council.observed(runs, "gpt-6-luna", m))
        self.assertLess(adj, -2)
        self.assertIn("0/20", why)
        runs = [{"model": "gpt-6-luna", "kind": "lane", "verdict": "pass"} for _ in range(2)]
        adj, _ = council.observed_adjustment(m, council.observed(runs, "gpt-6-luna", m))
        self.assertLess(adj, 0.2)  # two lucky runs do not crown anybody

    def test_model_names_claude_code_reports(self):
        for key, want in (("claude-opus-5-5[1m]", "claude-opus-5-5"), ("claude-haiku-4-5-20251001", "claude-haiku-4-5"),
                          ("Claude-Sonnet-5", "claude-sonnet-5"), ("opus", "claude-opus-5-5"), ("gpt-6-luna-pro", None)):
            self.assertEqual(lanes.find_model(self.cfg, key)[0], want, key)
        rows, _ = self.pick("complex", architect="claude-opus-5-5[1m]")
        self.assertEqual(rows[0]["id"], "gpt-6-sol")

    def test_priors_are_sane(self):
        for mid, m in self.models.items():
            self.assertTrue(m.get("name") and m.get("run") in ("codex", "claude", "local"), mid)
            self.assertEqual(set(m["talent"]), set(council.DIMS), mid)


if __name__ == "__main__":
    unittest.main()

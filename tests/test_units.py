"""Unit tests for the Python core. Run by tests/run.sh with PYTHONPATH=lib."""
import json
import os
import contextlib
import io
import tempfile
import time
import unittest
from unittest.mock import patch

from astrafab import core, council, jev, lanes, pantry


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


class Jev(unittest.TestCase):
    def setUp(self):
        self.lanes = {
            "routine": {"model": "gpt-6-luna", "description": "Clear, routine work."},
            "complex": {"model": "gpt-6-sol", "description": "Hard debugging."},
            "frontier": {"model": "gpt-6-astra"},
            "local": {"model": "qwen", "enabled": False},
        }
        self.cfg, _, _ = council.load(explicit=os.path.join(core.PLUGIN_ROOT, "config", "models.json"))

    def test_question_shapes_and_disabled_lanes(self):
        questions, available = jev.make_questions(self.lanes, self.cfg)
        self.assertEqual(set(questions), {"lane", "effort", "spec_complete"})
        self.assertEqual(set(questions["lane"]["criteria"]), {"routine", "complex", "frontier"})
        self.assertEqual(set(questions["effort"]["criteria"]), {"medium", "high", "xhigh"})
        self.assertEqual(questions["spec_complete"]["type"], "noul")
        self.assertIn("implementation", questions["lane"]["criteria"]["routine"])
        self.assertNotIn("local", available)

    def test_parses_choice_and_noul_probabilities(self):
        questions, _ = jev.make_questions(self.lanes, self.cfg)
        response = {"answers": {
            "lane": {"type": "choice", "choice": "complex", "probabilities": {"complex": 0.77}},
            "effort": {"type": "choice", "choice": "high", "probabilities": {"high": 0.91}},
            "spec_complete": {"type": "noul", "noul": 0.84},
        }}
        parsed = jev.parse_answers(response, questions)
        self.assertEqual(parsed["lane"]["answer"], "complex")
        self.assertEqual(parsed["lane"]["probability"], 0.77)
        self.assertEqual(parsed["spec_complete"]["answer"], 0.84)

    def test_rejects_invalid_probability(self):
        questions, _ = jev.make_questions(self.lanes, self.cfg)
        response = {"answers": {
            "lane": {"type": "choice", "choice": "complex", "probabilities": {"complex": 2}},
            "effort": {"type": "choice", "choice": "high", "probabilities": {"high": 0.9}},
            "spec_complete": {"type": "noul", "noul": 0.8},
        }}
        with self.assertRaises(jev.Unavailable):
            jev.parse_answers(response, questions)

    def test_request_sends_fixed_criteria_and_refuses_redirect(self):
        secret = "unit-key-sentinel"
        self.lanes["routine"]["description"] = "PRIVATE LANE DESCRIPTION"
        self.lanes["routine"]["_note"] = "PRIVATE NOTE"
        self.cfg["models"]["gpt-6-luna"]["talent"] = {"architecture": 9}
        seen, opens = [], []

        class FakeOpener:
            def __init__(self, handler):
                self.handler = handler

            def open(self, request, timeout=None):
                opens.append(request)
                seen.append(request.data.decode("utf-8"))
                self.handler.redirect_request(request, None, 302, "Found", {}, "https://other.invalid")

        with patch.dict(os.environ, {"TYPESAFE_API_KEY": secret}):
            with patch("astrafab.jev.build_opener", side_effect=lambda handler: FakeOpener(handler)):
                with self.assertRaises(jev.Unavailable) as raised:
                    jev.request("SPEC BODY", self.lanes, self.cfg, {"enabled": True, "timeout_s": 1})
        self.assertEqual(str(raised.exception), "http error")
        self.assertEqual(len(opens), 1)
        self.assertEqual(opens[0].get_header("Authorization"), "Bearer " + secret)
        self.assertNotIn(secret, str(raised.exception) + " ".join(seen))
        payload = json.loads(seen[0])
        self.assertEqual(payload["state"], "SPEC BODY")
        serialized = json.dumps(payload)
        for private in ("PRIVATE LANE DESCRIPTION", "PRIVATE NOTE", "architecture"):
            self.assertNotIn(private, serialized)

    def test_rejects_plain_http_endpoint(self):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "http-key-sentinel"}):
            with patch("astrafab.jev.build_opener") as opener:
                with self.assertRaises(jev.Unavailable):
                    jev.request("spec", self.lanes, self.cfg,
                                {"enabled": True, "endpoint": "http://127.0.0.1/test"})
        opener.assert_not_called()

    def test_resolved_key_is_trimmed_and_visible_ascii_only(self):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "  visible-key-sentinel\n"}):
            self.assertEqual(jev.resolve_key({}), ("visible-key-sentinel", "env"))
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "bad-key-sentinel\r\n-tail"}):
            with self.assertRaises(jev.Unavailable) as raised:
                jev.resolve_key({})
        self.assertEqual(str(raised.exception), "invalid key format")
        self.assertNotIn("bad-key-sentinel", str(raised.exception))

    def test_worker_value_error_is_sanitized(self):
        secret = "worker-key-sentinel"

        class BrokenOpener:
            def open(self, _request, timeout=None):
                raise ValueError("Invalid header value: Bearer " + secret)

        with patch.dict(os.environ, {"TYPESAFE_API_KEY": secret}):
            with patch("astrafab.jev.build_opener", return_value=BrokenOpener()):
                with self.assertRaises(jev.Unavailable) as raised:
                    jev.request("spec", self.lanes, self.cfg, {"enabled": True, "timeout_s": 1})
        self.assertEqual(str(raised.exception), "http error")
        self.assertNotIn(secret, str(raised.exception))

    def test_response_read_obeys_overall_deadline(self):
        class SlowResponse:
            headers = {}
            fp = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def getcode(self):
                return 200

            def read1(self, _size):
                time.sleep(0.05)
                return b"x"

        class SlowOpener:
            def open(self, _request, timeout=None):
                return SlowResponse()

        started = time.monotonic()
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "slow-key-sentinel"}):
            with patch("astrafab.jev.build_opener", return_value=SlowOpener()):
                with self.assertRaises(jev.Unavailable) as raised:
                    jev.request("spec", self.lanes, self.cfg, {"enabled": True, "timeout_s": 0.1})
        self.assertEqual(str(raised.exception), "timeout")
        self.assertLess(time.monotonic() - started, 0.6)

    def test_ledger_merges_calibration_outcome(self):
        with tempfile.TemporaryDirectory() as d:
            previous = os.environ.get("ASTRAFABULOPUS_HOME")
            os.environ["ASTRAFABULOPUS_HOME"] = d
            try:
                core.ledger_append({"id": "jev-1", "kind": "jev", "actual_choice": None, "run_grade": None})
                core.ledger_append({"id": "lane-1", "kind": "lane", "lane": "routine", "effort": "high"})
                core.ledger_append({"type": "jev_outcome", "decision": "jev-1", "run": "lane-1",
                                    "actual_choice": {"lane": "routine", "effort": "high"}, "run_grade": "pass",
                                    "match": "spec", "spec_complete": "no"})
                rows = core.ledger_read()
                decision = next(row for row in rows if row["id"] == "jev-1")
                self.assertEqual(decision["actual_choice"]["lane"], "routine")
                self.assertEqual(decision["run_grade"], "pass")
                self.assertEqual(decision["match"], "spec")
                self.assertEqual(decision["spec_complete"], "no")
            finally:
                if previous is None:
                    os.environ.pop("ASTRAFABULOPUS_HOME", None)
                else:
                    os.environ["ASTRAFABULOPUS_HOME"] = previous

    def test_grading_links_pending_jev_once_per_run(self):
        with tempfile.TemporaryDirectory() as d:
            previous = os.environ.get("ASTRAFABULOPUS_HOME")
            os.environ["ASTRAFABULOPUS_HOME"] = d
            try:
                for decision_id, spec_hash in (("jev-a", "aaaa"), ("jev-b", "bbbb")):
                    core.ledger_append({"id": decision_id, "kind": "jev", "actual_choice": None,
                                        "spec_sha256": spec_hash})
                core.ledger_append({"id": "lane-a", "kind": "lane", "lane": "routine", "effort": "high",
                                    "spec_sha256": "aaaa"})
                core.ledger_append({"id": "lane-b", "kind": "lane", "lane": "routine", "effort": "high",
                                    "spec_sha256": "cccc"})

                def grade(run_id):
                    args = type("Args", (), {"run": run_id, "lane": None, "decision": None,
                                              "verdict": "pass", "note": None, "spec_complete": None})()
                    with contextlib.redirect_stdout(io.StringIO()):
                        council.cmd_grade(args)

                grade("lane-a")
                args = type("Args", (), {"run": "lane-a", "lane": None, "decision": None,
                                          "verdict": "fail", "note": None, "spec_complete": "no"})()
                with contextlib.redirect_stdout(io.StringIO()):
                    council.cmd_grade(args)
                grade("lane-b")
                rows = core.ledger_read()
                decisions = [row for row in rows if row.get("kind") == "jev"]
                self.assertEqual(len([row for row in decisions if row.get("graded_run")]), 2)
                self.assertEqual(next(row for row in decisions if row["id"] == "jev-a")["run_grade"], "fail")
                with open(core.ledger_path()) as ledger:
                    outcomes = [json.loads(line) for line in ledger
                                if '"type": "jev_outcome"' in line]
                self.assertEqual(outcomes[0]["decision"], "jev-a")
                self.assertEqual(outcomes[0]["match"], "spec")
                self.assertEqual(outcomes[1]["match"], "spec")
                self.assertEqual(outcomes[1]["spec_complete"], "no")
                self.assertEqual(outcomes[2]["match"], "fallback")
            finally:
                if previous is None:
                    os.environ.pop("ASTRAFABULOPUS_HOME", None)
                else:
                    os.environ["ASTRAFABULOPUS_HOME"] = previous


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

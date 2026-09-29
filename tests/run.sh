#!/bin/bash
# The astrafabulopus test suite. Runs every lane against a fake Codex (tests/fakes/codex) in throwaway
# homes and repos, then the Python unit tests. No network, no login, no real subscription touched.
#
#   tests/run.sh            # everything
#   tests/run.sh lane       # only tests whose name contains "lane"
#
# Bash 3.2 compatible, like everything else here.
# shellcheck disable=SC2015,SC2209  # `check && check || fail` is the assertion idiom here; VAR=x func is deliberate
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
ORIG_PATH="$PATH"
FILTER="${1:-}"
PASSED=0; FAILED=0; FAILED_NAMES=""
export AF_PLAIN=1 NO_COLOR=1

setup() {
  T="$(mktemp -d "${TMPDIR:-/tmp}/af-test.XXXXXX")"
  export ASTRAFABULOPUS_HOME="$T/afhome" CODEX_HOME="$T/codexhome" CLAUDE_CONFIG_DIR="$T/claude"
  export PATH="$REPO/tests/fakes:$REPO/bin:$ORIG_PATH"
  unset FAKE_CODEX_MODE FAKE_CODEX_FILE FAKE_CODEX_LOGGED_IN FAKE_CODEX_USED5H FAKE_CODEX_USED7D \
        FAKE_CODEX_RESET5H FAKE_CODEX_RESET7D FAKE_CODEX_NO_RATES FAKE_CODEX_REJECT_EFFORT FAKE_CODEX_SLEEP \
        FAKE_CODEX_REACHED FAKE_CODEX_CREDITS \
        AF_IGNORE_PANTRY TYPESAFE_API_KEY AF_JEV_ENDPOINT FAKE_OP_KEY FAKE_KEYCHAIN_KEY
  export FAKE_CODEX_ARGS_LOG="$T/codex-args.log"
  PROJ="$T/proj"; mkdir -p "$PROJ"
  ( cd "$PROJ" && git init -q && echo "# spud project" > README.md && git add -A \
      && git -c user.name=t -c user.email=t@t commit -qm init ) >/dev/null
  SPEC="$T/spec.md"
  printf 'Objective: create a file.\nFiles: created-by-fake.txt\nInterfaces: none\nConstraints: minimal\nVerification: test -f created-by-fake.txt\n' > "$SPEC"
}
teardown() { rm -rf "$T"; }

fail() { echo "    ✗ $*"; return 1; }
has() { printf '%s' "$OUT" | grep -qF -- "$1" || fail "expected output to contain: $1"; }
hasnt() { if printf '%s' "$OUT" | grep -qF -- "$1"; then fail "expected output NOT to contain: $1"; fi; }
code() { [ "$RC" -eq "$1" ] || fail "expected exit $1, got $RC"; }
run() { OUT="$("$@" 2>&1)"; RC=$?; }
in_proj() { OUT="$(cd "$PROJ" && "$@" 2>&1)"; RC=$?; }
ledger_count() { if [ -f "$ASTRAFABULOPUS_HOME/ledger.jsonl" ]; then grep -c '"id"' "$ASTRAFABULOPUS_HOME/ledger.jsonl"; else echo 0; fi; }

# ------------------------------------------------------------------------------- lanes

t_lane_complete() {
  in_proj af-lane routine "$SPEC"
  code 0 && has "STATUS: complete" && has "created-by-fake.txt" && has "LANE: routine · gpt-6-luna · effort high (default)" \
    && has "RUN: " && has "TOKENS: in 12,000 (cached 8,000) · out 900 (reasoning 400)" && has "BUDGET: chatgpt" \
    && [ "$(ledger_count)" -eq 1 ] || fail "ledger should have one run"
}
t_lane_budget_delta_same_window() {
  export FAKE_CODEX_RESET5H=$(( $(date +%s) + 3600 )) FAKE_CODEX_RESET7D=$(( $(date +%s) + 300000 ))
  FAKE_CODEX_USED5H=10 in_proj af-lane routine "$SPEC"
  FAKE_CODEX_USED5H=11.5 FAKE_CODEX_USED7D=3.25 in_proj af-lane routine "$SPEC"
  code 0 && has "5h 10.0% → 11.5% (+1.5)" && has "7d 3.0% → 3.2% (+0.2)"
}
t_lane_budget_delta_window_rolled() {
  FAKE_CODEX_USED5H=90 FAKE_CODEX_RESET5H=$(( $(date +%s) + 60 )) in_proj af-lane routine "$SPEC"
  FAKE_CODEX_USED5H=2 FAKE_CODEX_RESET5H=$(( $(date +%s) + 18000 )) in_proj af-lane routine "$SPEC"
  code 0 && has "5h now 2.0% (no same-window reading before)"
}
t_lane_refused() {
  FAKE_CODEX_MODE=noop in_proj af-lane routine "$SPEC"
  code 4 && has "STATUS: refused" && has "a clean exit with no file changes is a refusal"
}
t_lane_failed() { FAKE_CODEX_MODE=fail in_proj af-lane routine "$SPEC"; code 1 && has "STATUS: failed"; }
t_lane_timeout() {
  mkdir -p "$PROJ/.claude/orchestra"
  echo '{"routine": {"timeout_seconds": 2}}' > "$PROJ/.claude/orchestra/lanes.json"
  FAKE_CODEX_MODE=sleep FAKE_CODEX_SLEEP=30 in_proj af-lane routine "$SPEC"
  code 5 && has "STATUS: timeout"
}
t_lane_detects_edit_to_untracked_file() {
  echo "already here" > "$PROJ/notes.txt"   # untracked before the run: git status alone cannot see the edit
  FAKE_CODEX_MODE=edit-untracked FAKE_CODEX_FILE=notes.txt in_proj af-lane routine "$SPEC"
  code 0 && has "STATUS: complete" && has "notes.txt"
}
t_lane_detects_edit_to_modified_file() {
  echo "local edit" >> "$PROJ/README.md"
  FAKE_CODEX_MODE=edit-modified FAKE_CODEX_FILE=README.md in_proj af-lane routine "$SPEC"
  code 0 && has "README.md"
}
t_lane_project_overlay_from_subdir() {
  mkdir -p "$PROJ/.claude/orchestra" "$PROJ/deep/er"
  echo '{"routine": {"model": "gpt-5.6-luna"}}' > "$PROJ/.claude/orchestra/lanes.json"
  OUT="$(cd "$PROJ/deep/er" && af-lane routine "$SPEC" 2>&1)"; RC=$?
  code 0 && has "gpt-5.6-luna · effort high (default)" && has ".claude/orchestra/lanes.json" \
    && [ -f "$PROJ/created-by-fake.txt" ] || fail "codex should run at the repo root"
}
t_lane_invalid_effort() { in_proj af-lane routine "$SPEC" --effort turbo; code 2 && has "STATUS: invalid"; }
t_lane_unlisted_effort_warns() {
  in_proj af-lane routine "$SPEC" --effort ultra
  code 0 && has "WARN: GPT-6 Luna is not known to accept 'ultra'" && has "effort ultra (flag)"
}
t_lane_spec_reasoning_line() {
  printf 'REASONING: xhigh\n' >> "$SPEC"
  in_proj af-lane routine "$SPEC"
  code 0 && has "effort xhigh (spec)" && grep -q 'model_reasoning_effort=xhigh' "$FAKE_CODEX_ARGS_LOG" || fail "effort not passed"
}
t_lane_logged_out() { FAKE_CODEX_LOGGED_IN=0 in_proj af-lane routine "$SPEC"; code 3 && has "STATUS: unavailable" && has "not logged in"; }
t_lane_local_disabled() { in_proj af-lane local "$SPEC"; code 3 && has "disabled"; }
t_lane_unknown_lane() { in_proj af-lane potato "$SPEC"; code 3 && has "unknown lane 'potato'"; }
t_lane_flag_without_value() { in_proj af-lane routine "$SPEC" --effort; code 2 && has "needs a value"; }
t_lane_usage() { run af-lane; code 2 && has "af-lane <routine"; }
t_lane_empty_budget_blocks() {
  FAKE_CODEX_USED5H=100 in_proj af-lane routine "$SPEC"   # this run records a 100% reading
  in_proj af-lane routine "$SPEC"
  code 3 && has "ChatGPT sack is empty"
  in_proj af-lane routine "$SPEC" --ignore-pantry
  code 0 && has "PANTRY: chatgpt empty"
}
t_lane_limit_flag_does_not_block_after_reset() {
  # Codex said "limit reached", then the window reset. The gate must not block the only run that can
  # record a fresh reading, or the sack stays "empty" forever.
  FAKE_CODEX_USED5H=100 FAKE_CODEX_REACHED=rate_limit_reached FAKE_CODEX_RESET5H=$(( $(date +%s) - 30 )) \
    in_proj af-lane routine "$SPEC" --ignore-pantry
  in_proj af-lane routine "$SPEC"
  code 0 && has "STATUS: complete" && has "unconfirmed since"
}
t_lane_limit_flag_blocks_while_current() {
  FAKE_CODEX_USED5H=100 FAKE_CODEX_REACHED=rate_limit_reached in_proj af-lane routine "$SPEC" --ignore-pantry
  in_proj af-lane routine "$SPEC"
  code 3 && has "ChatGPT sack is empty"
}
t_lane_full_window_with_credits_runs() {
  FAKE_CODEX_USED5H=100 FAKE_CODEX_CREDITS=40 in_proj af-lane routine "$SPEC"
  in_proj af-lane routine "$SPEC"
  code 0 && has "running on credits (balance 40)"
}
t_lane_that_commits_is_not_a_refusal() {
  FAKE_CODEX_MODE=commit in_proj af-lane routine "$SPEC"
  code 0 && has "STATUS: complete" && has "the lane committed" && has "created-by-fake.txt" || return 1
  printf '%s' "$OUT" | grep -qE '^  commit [0-9a-f]{12}\.\.[0-9a-f]{12} ' || fail "commit line should show the full short range"
}
t_lane_tight_budget_warns() {
  FAKE_CODEX_USED5H=90 in_proj af-lane routine "$SPEC"
  in_proj af-lane routine "$SPEC"
  code 0 && has "PANTRY: chatgpt tight"
}
t_lane_compat_shim() { in_proj "$REPO/scripts/lane.sh" routine "$SPEC"; code 0 && has "STATUS: complete"; }
t_lane_through_symlink() {
  mkdir -p "$T/elsewhere" && ln -s "$REPO/bin/af-lane" "$T/elsewhere/af-lane"
  in_proj "$T/elsewhere/af-lane" routine "$SPEC"
  code 0 && has "STATUS: complete"
}
t_lane_non_git_root() {
  mkdir -p "$T/plain" && echo hi > "$T/plain/a.txt"
  OUT="$(cd "$T/plain" && af-lane routine "$SPEC" 2>&1)"; RC=$?
  code 0 && has "created-by-fake.txt" && hasnt "DIFFSTAT"
}

# ------------------------------------------------------------------------------- consult / review / verify

t_consult_read_only() {
  echo "Should we mash or roast?" > "$T/q.md"
  in_proj af-consult "$T/q.md"
  code 0 && has "CONSULT: gpt-6-astra" && has "VERDICT: ship" && grep -q '"read-only"' "$FAKE_CODEX_ARGS_LOG" \
    || fail "consult must run read-only"
}
t_consult_failure() { echo "q" > "$T/q.md"; FAKE_CODEX_MODE=fail in_proj af-consult "$T/q.md"; code 1 && has "STATUS: failed"; }
t_review_custom_prompt_is_valid_codex() {
  in_proj af-review
  code 0 && has "VERDICT: ship" && has "scope uncommitted" \
    && grep '"review"' "$FAKE_CODEX_ARGS_LOG" | grep -q '"-"' && ! grep -q -- '--uncommitted' "$FAKE_CODEX_ARGS_LOG" \
    || fail "custom review must pass the prompt on stdin without --uncommitted"
}
t_review_base_prompt_includes_uncommitted_work() {
  mkdir -p "$T/capture-bin"
  cat > "$T/capture-bin/codex" <<'SH'
#!/bin/bash
if [ "${1:-}" = exec ]; then
  tee "$FAKE_CODEX_PROMPT_LOG" | "$FAKE_CODEX_BIN" "$@"
else
  exec "$FAKE_CODEX_BIN" "$@"
fi
SH
  chmod +x "$T/capture-bin/codex"
  export FAKE_CODEX_BIN="$REPO/tests/fakes/codex" FAKE_CODEX_PROMPT_LOG="$T/review-prompt.md"
  export PATH="$T/capture-bin:$PATH"
  in_proj af-review --base HEAD
  code 0 && grep -qF 'git diff --cached' "$FAKE_CODEX_PROMPT_LOG" \
    && grep -qF 'git diff,' "$FAKE_CODEX_PROMPT_LOG" \
    && grep -qF 'git ls-files --others --exclude-standard' "$FAKE_CODEX_PROMPT_LOG" \
    && grep -qF 'read untracked files as text when they are small text files' "$FAKE_CODEX_PROMPT_LOG" \
    || fail "base review prompt must include staged, unstaged, and untracked work"
}
t_review_native_scope() {
  in_proj af-review --native --base main
  code 0 && grep -q '"review", "--base", "main"' "$FAKE_CODEX_ARGS_LOG" || fail "native review should pass --base main"
}
t_review_failure_propagates() { FAKE_CODEX_MODE=fail in_proj af-review; code 1 && has "STATUS: failed"; }
t_verify_pass_fail() {
  in_proj af-verify -- sh -c 'echo "Ran 3 tests"; echo OK'
  code 0 && has "VERDICT: PASS" && has "Ran 3 tests" || return 1
  in_proj af-verify -- sh -c 'echo "AssertionError: spud"; exit 1'
  code 1 && has "VERDICT: FAIL (1)" && has "AssertionError: spud"
}
t_verify_detail_preserves_project_report() {
  in_proj af-verify -- sh -c 'printf "VERIFY REPORT\\nPACKAGE: built\\nCODESIGN: strict verification passed\\nVERDICT: PASS\\n"'
  code 0 || return 1
  DETAIL="$(printf '%s\n' "$OUT" | awk '/^DETAIL:/{show=1; next} show{print}')"
  printf '%s\n' "$DETAIL" | grep -qFx 'VERIFY REPORT' \
    && printf '%s\n' "$DETAIL" | grep -qFx 'PACKAGE: built' \
    && printf '%s\n' "$DETAIL" | grep -qFx 'CODESIGN: strict verification passed' \
    && printf '%s\n' "$DETAIL" | grep -qFx 'VERDICT: PASS' \
    || fail "DETAIL must preserve the project's verification report"
}
t_verify_timeout() { in_proj af-verify --timeout 1 -- sleep 20; code 124 && has "VERDICT: FAIL (124)"; }
t_verify_config_command() {
  mkdir -p "$PROJ/.claude/orchestra"
  echo '{"verify": {"command": "echo 7 passed"}}' > "$PROJ/.claude/orchestra/lanes.json"
  in_proj af-verify
  code 0 && has "7 passed"
}
t_verify_stale_lock() {
  mkdir -p "$ASTRAFABULOPUS_HOME/locks"
  ROOTP="$(python3 "$REPO/lib/af.py" root "$PROJ")"
  if command -v shasum >/dev/null 2>&1; then H="$(printf '%s' "$ROOTP" | shasum | cut -c1-12)"; else H="$(printf '%s' "$ROOTP" | sha1sum | cut -c1-12)"; fi
  L="$ASTRAFABULOPUS_HOME/locks/$H.lock"
  mkdir -p "$L" && echo 999999 > "$L/pid"
  in_proj af-verify -- true
  code 0 && has "VERDICT: PASS"
}

# ------------------------------------------------------------------------------- pantry / statusline

t_pantry_reads_rollouts() {
  FAKE_CODEX_USED5H=90 FAKE_CODEX_USED7D=40 in_proj af-lane routine "$SPEC"
  run af-pantry --brief
  has "chatgpt tight (5h 90% · 7d 40%)" && has "claude unknown" || return 1
  run af-pantry advise
  has "ChatGPT is tight" || return 1
  run af-pantry --json
  printf '%s' "$OUT" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["budgets"]["chatgpt"]["level"]=="tight"' \
    || fail "json should say tight"
}
t_pantry_reset_window_counts_as_fresh() {
  FAKE_CODEX_USED5H=99.9 FAKE_CODEX_RESET5H=$(( $(date +%s) - 10 )) in_proj af-lane routine "$SPEC" --ignore-pantry
  run af-pantry --brief
  has "chatgpt plenty (5h 0%"
}
t_statusline_tap() {
  run sh -c 'echo "{\"model\":{\"id\":\"claude-opus-5-5\",\"display_name\":\"Opus 5.5\"},\"rate_limits\":{\"five_hour\":{\"used_percentage\":23.5,\"resets_at\":'$(( $(date +%s) + 3600 ))'},\"seven_day\":{\"used_percentage\":41.2,\"resets_at\":'$(( $(date +%s) + 90000 ))'}}}" | af-statusline'
  code 0 && has "Opus 5.5" && has "Claude 5h 24% 7d 41%" || return 1
  run af-pantry --json
  printf '%s' "$OUT" | python3 -c 'import json,sys; d=json.load(sys.stdin)["budgets"]["claude"]; assert d["source"]=="statusline" and d["model_id"]=="claude-opus-5-5", d' \
    || fail "claude reading should come from the status line"
}
t_statusline_chain_and_garbage() {
  run sh -c 'echo "{}" | af-statusline --chain "echo hello-from-your-old-statusline"'
  code 0 && has "hello-from-your-old-statusline │" || return 1
  run sh -c 'echo "not json at all" | af-statusline'
  code 0
}
t_statusline_launcher() {
  run af-pantry install-statusline --chain "echo mine"
  code 0 && has '"refreshInterval": 60' || return 1
  run sh -c "echo '{}' | '$ASTRAFABULOPUS_HOME/bin/af-statusline'"
  code 0 && has "mine │"
}
t_pantry_manual_accounts() {
  run af-pantry set openai-api --balance 12.5 --of 50 --note "API key credits"
  code 0 || return 1
  run af-pantry --json
  printf '%s' "$OUT" | python3 -c 'import json,sys; d=json.load(sys.stdin)["budgets"]["openai-api"]; assert d["level"]=="watch" and abs(d["windows"][0]["used"]-75)<0.01, d' \
    || fail "12.5 of 50 left should read 75% used, watch"
  run af-pantry forget openai-api
  code 0
}
t_pantry_gate_exit_codes() {
  run af-pantry gate chatgpt; code 0 || return 1
  run af-pantry gate local; code 0 && has "plenty"
}

# ------------------------------------------------------------------------------- council / tryout

t_council_roster_and_card() {
  run af-council
  code 0 && has "THE POTATO COUNCIL" && has "GPT-6 Luna" && has "Tater Tot" || return 1
  run af-council show opus
  code 0 && has "Yukon Gold" && has "Terminal-Bench 4.0 66.4%"
}
t_council_recommend_matches_doctrine() {
  run af-council recommend routine; has "PICK for routine: GPT-6 Luna" || return 1
  run af-council recommend complex --architect claude-opus-5-5; has "PICK for complex: GPT-6 Sol" || return 1
  run af-council recommend review; has "PICK for review: Fable 5.1" || return 1
  run af-council recommend architect; has "PICK for architect: Opus 5.5"
}
t_council_budget_pressure_reroutes() {
  FAKE_CODEX_USED5H=100 in_proj af-lane routine "$SPEC"
  run af-council recommend routine
  has "excluded: GPT-6 Luna — chatgpt budget is empty" && has "PICK for routine: Sonnet 5"
}
t_council_new_model_workflow() {
  run af-council add gpt-7-luna --like gpt-6-luna --name "GPT-7 Luna" --bump implementation=+1.5 --price 0.1/0.5
  code 0 || return 1
  run af-council show gpt-7-luna; has "implementation" && has "9.5" || return 1
  run af-council recommend routine; has "PICK for routine: GPT-7 Luna" || return 1
  run af-council rate gpt-7-luna speed=6 --why "slower than advertised"; code 0 || return 1
  run af-council promote gpt-7-luna --lane routine --effort medium; code 0 || return 1
  in_proj af-lane routine "$SPEC"; has "gpt-7-luna · effort medium (default)" || return 1
  run af-council retire gpt-7-luna; code 0 || return 1
  run af-council; hasnt "GPT-7 Luna"
}
t_council_rejects_bad_input() {
  run af-council add mystery; code 2 || return 1
  run af-council rate gpt-6-luna charisma=10; code 2 || return 1
  run af-council promote opus --lane routine; code 2 && has "agent frontmatter"
}
t_council_grades_move_the_needle() {
  in_proj af-lane routine "$SPEC"; run af-council grade last pass; code 0 || return 1
  in_proj af-lane routine "$SPEC"; run af-council grade last fail --note "missed an edge"; code 0 || return 1
  run af-council show gpt-6-luna; has "2 runs · 1/2 pass" && has "observed 1/2 passed" || return 1
  run af-council ledger; hasnt "ungraded" && has "pass" && has "fail"
}
t_council_log_manual_run() {
  run af-council log --model opus --status complete --verified pass --duration 120; code 0 || return 1
  run af-council show opus; has "1 run · 1/1 pass"
}

# ------------------------------------------------------------------------------- Jev advisory

jev_tools() {
  mkdir -p "$T/key-bin"
  cat > "$T/key-bin/op" <<'SH'
#!/bin/sh
if [ -n "${FAKE_OP_KEY:-}" ]; then printf '%s' "$FAKE_OP_KEY"; else exit 1; fi
SH
  cat > "$T/key-bin/security" <<'SH'
#!/bin/sh
if [ -n "${FAKE_KEYCHAIN_KEY:-}" ]; then printf '%s' "$FAKE_KEYCHAIN_KEY"; else exit 1; fi
SH
  chmod +x "$T/key-bin/op" "$T/key-bin/security"
  export PATH="$T/key-bin:$PATH"
  export AF_JEV_ENDPOINT="https://stub.invalid/v1/systemone"
  mkdir -p "$PROJ/.claude/orchestra"
  cat > "$PROJ/.claude/orchestra/lanes.json" <<'JSON'
{"jev":{"enabled":true,"key_ref":"op://vault/item/password","timeout_s":2}}
JSON
}
jev_stub() {
  JEV_MODE="$1"; JEV_COMMAND="$2"; shift 2
  in_proj python3 "$REPO/tests/jev_stub.py" "$JEV_MODE" "$T/jev-body.json" "$T/jev-auth" \
    "$JEV_COMMAND" "$SPEC" "$@"
}
jev_stop() { unset AF_JEV_ENDPOINT; }

t_jev_request_shape_and_response() {
  jev_tools || return 1
  export TYPESAFE_API_KEY=env-key-sentinel
  jev_stub ok decide --json
  unset TYPESAFE_API_KEY
  code 0 && has '"available": true' && has '"request_id": "header-request-id"' || { jev_stop; return 1; }
  python3 - "$T/jev-body.json" "$T/jev-auth" "$SPEC" <<'PY' || { jev_stop; return 1; }
import json, sys
body = json.load(open(sys.argv[1]))
assert body["model"] == "jev-latest"
assert body["state"] == open(sys.argv[3]).read()
assert set(body["questions"]) == {"lane", "effort", "spec_complete"}
assert body["questions"]["lane"]["type"] == "choice"
assert set(body["questions"]["effort"]["criteria"]) == {"medium", "high", "xhigh"}
assert body["questions"]["spec_complete"]["type"] == "noul"
assert "local" not in body["questions"]["lane"]["criteria"]
assert open(sys.argv[2]).read() == "env"
PY
  hasnt "env-key-sentinel" && hasnt "PRIVATE LANE DESCRIPTION" || { jev_stop; return 1; }
  if grep -qF 'env-key-sentinel' "$ASTRAFABULOPUS_HOME/ledger.jsonl"; then jev_stop; fail "Jev key leaked to ledger"; return 1; fi
  python3 - "$ASTRAFABULOPUS_HOME/ledger.jsonl" <<'PY' || { jev_stop; return 1; }
import json, sys
entry = json.loads(open(sys.argv[1]).readline())
assert entry["kind"] == "jev" and entry["model"] == "jev-test-1"
assert entry["latency_ms"] >= 0 and entry["request_id"] == "header-request-id"
assert entry["answers"]["lane"]["answer"] == "routine"
assert entry["answers"]["lane"]["probability"] == 0.82
assert entry["actual_choice"] is None and entry["run_grade"] is None
PY
  in_proj af-lane routine "$SPEC" >/dev/null 2>&1
  in_proj af-council grade last pass --spec-complete no >/dev/null 2>&1
  python3 - "$ASTRAFABULOPUS_HOME/ledger.jsonl" <<'PY' || { jev_stop; return 1; }
import json, sys
entries = [json.loads(line) for line in open(sys.argv[1]) if line.strip()]
decision = next(row for row in entries if row.get("kind") == "jev")
lane = next(row for row in entries if row.get("kind") == "lane")
outcome = next(row for row in entries if row.get("type") == "jev_outcome")
assert lane["lane"] == "routine"
assert outcome["decision"] == decision["id"]
assert outcome["actual_choice"]["lane"] == "routine"
assert outcome["actual_choice"]["effort"] == lane["effort"]
assert outcome["run_grade"] == "pass"
assert outcome["spec_complete"] == "no"
PY
  in_proj af-council --json ledger
  code 0 && has '"match": "spec"' && has '"spec_complete": "no"' || { jev_stop; return 1; }
  jev_stop
}
t_jev_metadata_key_echo_is_suppressed() {
  jev_tools || return 1
  export TYPESAFE_API_KEY=metadata-key-sentinel
  jev_stub metadata-echo decide
  unset TYPESAFE_API_KEY
  code 0 && hasnt "metadata-key-sentinel" || { jev_stop; return 1; }
  export TYPESAFE_API_KEY=metadata-key-sentinel
  jev_stub metadata-echo decide --json
  unset TYPESAFE_API_KEY
  code 0 && hasnt "metadata-key-sentinel" || { jev_stop; return 1; }
  if grep -qF 'metadata-key-sentinel' "$ASTRAFABULOPUS_HOME/ledger.jsonl"; then jev_stop; fail "Jev metadata key leaked to ledger"; return 1; fi
  jev_stop
}
t_jev_matches_calibration_by_spec() {
  jev_tools || return 1
  SPEC_B="$T/spec-b.md"
  printf 'Different spec B\n' > "$SPEC_B"
  export TYPESAFE_API_KEY=calibration-key-sentinel
  in_proj python3 "$REPO/tests/jev_stub.py" ok "$T/body-a" "$T/auth-a" decide "$SPEC" >/dev/null 2>&1
  in_proj python3 "$REPO/tests/jev_stub.py" ok "$T/body-b" "$T/auth-b" decide "$SPEC_B" >/dev/null 2>&1
  unset TYPESAFE_API_KEY
  in_proj af-lane routine "$SPEC" >/dev/null 2>&1
  in_proj af-council grade last pass >/dev/null 2>&1
  python3 - "$ASTRAFABULOPUS_HOME/ledger.jsonl" <<'PY' || { jev_stop; return 1; }
import json, sys
rows = [json.loads(line) for line in open(sys.argv[1]) if line.strip()]
decision_a, decision_b = [row for row in rows if row.get("kind") == "jev"]
lane = next(row for row in rows if row.get("kind") == "lane")
outcome = next(row for row in rows if row.get("type") == "jev_outcome")
assert decision_a["spec_sha256"] == lane["spec_sha256"]
assert outcome["decision"] == decision_a["id"] and outcome["decision"] != decision_b["id"]
assert outcome["match"] == "spec"
PY
  jev_stop
}
t_jev_key_precedence() {
  jev_tools || return 1
  export TYPESAFE_API_KEY=env-key-sentinel FAKE_OP_KEY=op-key-sentinel FAKE_KEYCHAIN_KEY=keychain-key-sentinel
  jev_stub ok decide >/dev/null 2>&1
  RC=$?; [ "$RC" -eq 0 ] && [ "$(cat "$T/jev-auth")" = "env" ] || { jev_stop; fail "env key must win"; return 1; }
  unset TYPESAFE_API_KEY
  jev_stub ok decide >/dev/null 2>&1
  RC=$?; [ "$RC" -eq 0 ] && [ "$(cat "$T/jev-auth")" = "op" ] || { jev_stop; fail "op key must precede Keychain"; return 1; }
  unset FAKE_OP_KEY
  jev_stub ok decide >/dev/null 2>&1
  RC=$?; [ "$RC" -eq 0 ] && [ "$(cat "$T/jev-auth")" = "keychain" ] || { jev_stop; fail "Keychain key should be used last"; return 1; }
  unset FAKE_KEYCHAIN_KEY
  jev_stop
}
t_jev_unavailable_and_secret_safety() {
  jev_tools
  in_proj af-decide lane "$SPEC"; code 3 && has "no key found" || return 1
  export TYPESAFE_API_KEY=$'trailing-key-sentinel\n'
  jev_stub ok decide
  unset TYPESAFE_API_KEY
  code 0 && [ "$(cat "$T/jev-auth")" = "env" ] || { jev_stop; fail "trailing newline key should be trimmed"; return 1; }
  export TYPESAFE_API_KEY=$'embedded-key-sentinel\r\n-tail'
  jev_stub ok decide
  unset TYPESAFE_API_KEY
  code 3 && has "invalid key format" && hasnt "embedded-key-sentinel" || { jev_stop; return 1; }
  if [ -f "$ASTRAFABULOPUS_HOME/ledger.jsonl" ] && grep -qF 'embedded-key-sentinel' "$ASTRAFABULOPUS_HOME/ledger.jsonl"; then jev_stop; fail "invalid env key leaked to ledger"; return 1; fi
  export FAKE_OP_KEY=$'op-embedded-key-sentinel\r\n-tail'
  jev_stub ok decide
  unset FAKE_OP_KEY
  code 3 && has "invalid key format" && hasnt "op-embedded-key-sentinel" || { jev_stop; return 1; }
  if [ -f "$ASTRAFABULOPUS_HOME/ledger.jsonl" ] && grep -qF 'op-embedded-key-sentinel' "$ASTRAFABULOPUS_HOME/ledger.jsonl"; then jev_stop; fail "invalid op key leaked to ledger"; return 1; fi
  export TYPESAFE_API_KEY=worker-key-sentinel
  jev_stub value-error decide
  unset TYPESAFE_API_KEY
  code 3 && has "http error" && hasnt "worker-key-sentinel" || { jev_stop; return 1; }
  export TYPESAFE_API_KEY=error-key-sentinel
  jev_stub 500 decide
  unset TYPESAFE_API_KEY
  code 3 && has "http error" && hasnt "error-key-sentinel" || { jev_stop; return 1; }
  hasnt "secret-looking server error" || { jev_stop; return 1; }
  export TYPESAFE_API_KEY=redirect-key-sentinel
  jev_stub 302 decide
  unset TYPESAFE_API_KEY
  code 3 && has "http error" && hasnt "redirect-key-sentinel" || { jev_stop; return 1; }
  cat > "$PROJ/.claude/orchestra/lanes.json" <<'JSON'
{"jev":{"enabled":true,"key_ref":"op://vault/item/password","timeout_s":0.1}}
JSON
  export TYPESAFE_API_KEY=timeout-key-sentinel
  jev_stub timeout decide
  unset TYPESAFE_API_KEY
  code 3 && has "timeout" && hasnt "timeout-key-sentinel" || { jev_stop; return 1; }
  if [ -f "$ASTRAFABULOPUS_HOME/ledger.jsonl" ] && grep -qE 'embedded-key-sentinel|op-embedded-key-sentinel|worker-key-sentinel|error-key-sentinel|timeout-key-sentinel|redirect-key-sentinel' "$ASTRAFABULOPUS_HOME/ledger.jsonl"; then jev_stop; fail "Jev key leaked to ledger"; return 1; fi
  jev_stop
}
t_jev_council_recommend_is_advisory_and_opt_in() {
  in_proj af-council recommend --spec "$SPEC"
  code 0 && has "PICK for complex: Opus 5.5" && hasnt "Jev suggests" || { jev_stop; return 1; }
  jev_tools || return 1
  export TYPESAFE_API_KEY=council-key-sentinel
  jev_stub ok council
  unset TYPESAFE_API_KEY
  code 0 && has "PICK for complex: Opus 5.5" && has "Jev suggests: routine/high (p=0.820)" || { jev_stop; return 1; }
  jev_stop
}
t_tryout_happy_path() {
  FAKE_CODEX_MODE=solve run af-tryout gpt-6-luna
  code 0 && has "SCORE: 3/3" || return 1
  run af-council show gpt-6-luna; has "3/3 pass"
}
t_tryout_failing_model() {
  FAKE_CODEX_MODE=write run af-tryout gpt-6-sol --lane complex --tasks 1,2
  code 1 && has "SCORE: 0/2"
}
t_tryout_rejects_claude_models() { run af-tryout opus; code 2 && has "run as agents"; }

t_doctor() {
  run af-doctor
  code 0 && has "SPUD CHECK" && has "lane routine" && has "codex login" && has "Jev" && has "disabled" || return 1
  run af-doctor --candidates; has "gpt-6-luna" || return 1
  jev_tools
  in_proj af-doctor --json
  code 0 && has "key missing" || return 1
  has '"what": "Jev"' && hasnt '"what": "lane jev"' || return 1
  export TYPESAFE_API_KEY=doctor-env-sentinel
  in_proj af-doctor --json
  unset TYPESAFE_API_KEY
  code 0 && has "key found via env" && hasnt "doctor-env-sentinel" || return 1
  export FAKE_OP_KEY=doctor-key-sentinel
  in_proj af-doctor --json
  unset FAKE_OP_KEY
  code 0 && has "key found via op" && hasnt "doctor-key-sentinel" || return 1
  FAKE_CODEX_LOGGED_IN=0 run af-doctor --strict; code 1
}

# ------------------------------------------------------------------------------- packaging

t_packaging() {
  python3 - "$REPO" <<'PY' || fail "packaging checks failed"
import json, os, re, sys
repo = sys.argv[1]
for rel in ("config/lanes.json", "config/models.json", ".claude-plugin/plugin.json", ".claude-plugin/marketplace.json"):
    json.load(open(os.path.join(repo, rel)))
plugin = json.load(open(os.path.join(repo, ".claude-plugin/plugin.json")))
init = open(os.path.join(repo, "lib/astrafab/__init__.py")).read()
marketplace = json.load(open(os.path.join(repo, ".claude-plugin/marketplace.json")))
assert plugin["version"] == "0.3.0", "plugin version must be 0.3.0"
assert marketplace["plugins"][0]["version"] == "0.3.0", "marketplace version must be 0.3.0"
assert '__version__ = "0.3.0"' in init, "package version must be 0.3.0"
assert '__version__ = "%s"' % plugin["version"] in init, "plugin.json and __init__ disagree on version"
for d in ("agents", "commands", "skills/orchestration"):
    for name in os.listdir(os.path.join(repo, d)):
        if not name.endswith(".md"):
            continue
        text = open(os.path.join(repo, d, name)).read()
        assert text.startswith("---\n"), name
        front = text.split("---\n")[1]
        assert "description:" in front, name
        if d == "agents":
            assert re.search(r"^name: ", front, re.M) and re.search(r"^model: ", front, re.M), name
for name in os.listdir(os.path.join(repo, "bin")):
    assert os.access(os.path.join(repo, "bin", name), os.X_OK), name + " is not executable"
models = json.load(open(os.path.join(repo, "config/models.json")))["models"]
for mid, m in models.items():
    for dim in ("architecture", "implementation", "debugging", "review", "speed", "efficiency"):
        assert 0 <= m["talent"][dim] <= 10, (mid, dim)
PY
}

# ------------------------------------------------------------------------------- runner

TESTS="$(grep -E '^t_[a-z0-9_]+\(\)' "$0" | sed 's/().*//')"
for t in $TESTS; do
  if [ -n "$FILTER" ] && ! printf '%s' "$t" | grep -q -- "$FILTER"; then continue; fi
  setup
  if ( set +e; OUT=""; $t; r=$?; printf '%s\n' "$OUT" > "$T/.last-output"; exit $r ) ; then PASSED=$((PASSED+1)); echo "  ✓ ${t#t_}"
  else FAILED=$((FAILED+1)); FAILED_NAMES="$FAILED_NAMES ${t#t_}"; echo "  ✗ ${t#t_}"; tail -25 "$T/.last-output" 2>/dev/null | sed 's/^/      | /'; fi
  teardown
done

if [ -z "$FILTER" ] || printf '%s' "units" | grep -q -- "$FILTER"; then
  if ( cd "$REPO" && PYTHONPATH="$REPO/lib" python3 -m unittest discover -s tests -p 'test_*.py' -q ) ; then
    PASSED=$((PASSED+1)); echo "  ✓ python units"
  else FAILED=$((FAILED+1)); FAILED_NAMES="$FAILED_NAMES python-units"; echo "  ✗ python units"; fi
fi

echo
echo "$PASSED passed, $FAILED failed${FAILED_NAMES:+ ($FAILED_NAMES )}"
[ "$FAILED" -eq 0 ]

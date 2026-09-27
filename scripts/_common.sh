#!/bin/bash
# Shared helpers for astrafabulopus scripts. Sourced, not executed.
# Config resolution: --config PATH > ./.claude/orchestra/lanes.json (project) > ~/.claude/astrafabulopus/lanes.json (user) > <plugin>/config/lanes.json
af_script_dir() { cd "$(dirname "${BASH_SOURCE[1]}")" && pwd; }
af_home() { echo "${ASTRAFABULOPUS_HOME:-$HOME/.claude/astrafabulopus}"; }
af_resolve_config() { # $1 explicit path or empty, $2 project root
  if [ -n "$1" ]; then echo "$1"; return; fi
  if [ -f "$2/.claude/orchestra/lanes.json" ]; then echo "$2/.claude/orchestra/lanes.json"; return; fi
  if [ -f "$(af_home)/lanes.json" ]; then echo "$(af_home)/lanes.json"; return; fi
  echo "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/config/lanes.json"
}
af_lane_cfg() { # $1 config, $2 lane -> "OK provider model effort timeout enabled base_url" or "ERR ..."
  python3 - "$1" "$2" <<'PY'
import json, sys
try:
    cfg = json.load(open(sys.argv[1]))
except Exception as e:
    print("ERR cannot read %s: %s" % (sys.argv[1], e)); sys.exit(0)
lane = cfg.get(sys.argv[2])
if not isinstance(lane, dict) or "model" not in lane:
    print("ERR unknown lane '%s' in %s" % (sys.argv[2], sys.argv[1])); sys.exit(0)
print("OK", lane.get("provider", "codex"), lane["model"], lane.get("effort", "high"),
      lane.get("timeout_seconds", 1500), "true" if lane.get("enabled", True) else "false",
      lane.get("base_url", "-"))
PY
}
af_preflight() { # $1 provider, $2 base_url or '-'
  command -v codex >/dev/null 2>&1 || { echo "codex CLI not found on PATH (npm i -g @openai/codex && codex login)"; return 3; }
  case "$1" in
    codex) codex login status >/dev/null 2>&1 || { echo "codex not logged in: $(codex login status 2>&1 | head -1)"; return 3; } ;;
    lmstudio|ollama)
      local url="$2"; [ "$url" = "-" ] && { [ "$1" = "lmstudio" ] && url="http://localhost:1234/v1/models" || url="http://localhost:11434/api/tags"; }
      curl -s --max-time 3 "$url" >/dev/null 2>&1 || { echo "local server not reachable at $url ($1)"; return 3; } ;;
    *) echo "unknown provider '$1'"; return 3 ;;
  esac
  return 0
}
af_run_with_watchdog() { # $1 timeout, $2 log, $3 prompt file, $4 marker, rest: command
  local timeout="$1" log="$2" prompt="$3" marker="$4"; shift 4
  "$@" < "$prompt" >> "$log" 2>&1 &
  local pid=$!
  ( sleep "$timeout"; if kill -0 "$pid" 2>/dev/null; then echo "# $marker: timeout after ${timeout}s" >> "$log"; kill -TERM "$pid" 2>/dev/null; sleep 15; kill -KILL "$pid" 2>/dev/null; fi ) >/dev/null 2>&1 &
  local wd=$!
  wait "$pid"; local rc=$?
  pkill -P "$wd" 2>/dev/null; kill "$wd" 2>/dev/null; wait "$wd" 2>/dev/null
  return $rc
}

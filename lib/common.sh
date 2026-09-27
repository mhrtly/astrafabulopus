#!/bin/bash
# Shared helpers for the astrafabulopus lanes. Sourced, not executed. Bash 3.2 compatible, because
# that is what /bin/bash still is on a Mac, and a potato does not judge a shell by its age.

# Resolve the plugin root from the calling script, following symlinks without GNU readlink -f.
af_self_root() {
  local src="$1" dir
  while [ -L "$src" ]; do
    dir="$(cd -P "$(dirname "$src")" && pwd)"
    src="$(readlink "$src")"
    case "$src" in /*) ;; *) src="$dir/$src" ;; esac
  done
  dir="$(cd -P "$(dirname "$src")" && pwd)"
  (cd "$dir/.." && pwd)
}

AF_ROOT="${AF_ROOT:-$(af_self_root "${BASH_SOURCE[1]:-$0}")}"
AF_BIN="$AF_ROOT/bin"
AF_PY="$AF_ROOT/lib/af.py"

af_home() { echo "${ASTRAFABULOPUS_HOME:-$HOME/.claude/astrafabulopus}"; }
af_py() { python3 "$AF_PY" "$@"; }
af_logdir() { local d; d="$(af_home)/logs"; mkdir -p "$d"; echo "$d"; }
af_stamp() { date +%Y%m%d-%H%M%S; }

# Portable short hash of stdin (shasum on macOS, sha1sum on Linux, cksum anywhere).
af_hash() {
  if command -v shasum >/dev/null 2>&1; then shasum | cut -c1-12
  elif command -v sha1sum >/dev/null 2>&1; then sha1sum | cut -c1-12
  else cksum | tr ' ' '-' | cut -c1-12; fi
}

# Requires a value after a flag; with `set -u` a missing value would otherwise crash unhelpfully.
af_need() { # $1 flag, $2 argc remaining
  if [ "$2" -lt 2 ]; then echo "$(basename "$0"): $1 needs a value" >&2; exit 2; fi
}

af_preflight() { # $1 provider, $2 base_url or '-'
  command -v codex >/dev/null 2>&1 || { echo "codex CLI not found on PATH (npm i -g @openai/codex && codex login)"; return 3; }
  command -v python3 >/dev/null 2>&1 || { echo "python3 not found on PATH (xcode-select --install on a Mac)"; return 3; }
  case "$1" in
    codex) codex login status >/dev/null 2>&1 || { echo "codex not logged in: $(codex login status 2>&1 | tail -1)"; return 3; } ;;
    lmstudio|ollama)
      local url="$2"
      if [ "$url" = "-" ]; then
        if [ "$1" = "lmstudio" ]; then url="http://localhost:1234/v1/models"; else url="http://localhost:11434/api/tags"; fi
      fi
      curl -s --max-time 3 "$url" >/dev/null 2>&1 || { echo "local server not reachable at $url ($1)"; return 3; } ;;
    *) echo "unknown provider '$1'"; return 3 ;;
  esac
  return 0
}

# Budget gate: prints nothing when there is headroom, a PANTRY line when there is not, and returns 3
# when the budget is empty. Unknown readings never block: unknown is not zero, but it is not empty.
af_pantry_gate() { # $1 budget
  local out rc
  out="$(python3 "$AF_BIN/af-pantry" gate "$1" 2>/dev/null)"; rc=$?
  case "$out" in
    "GATE $1 plenty"*|"GATE $1 unknown"*|"") ;;
    *) echo "PANTRY: ${out#GATE }" ;;
  esac
  return $rc
}

# Run a command with stdin from a file, output appended to a log, under a watchdog. No coreutils
# `timeout` needed. On timeout the command and its direct children get TERM, then KILL.
af_run_with_watchdog() { # $1 timeout, $2 log, $3 stdin file, $4 marker, rest: command
  local timeout="$1" log="$2" stdin_file="$3" marker="$4"; shift 4
  "$@" < "$stdin_file" >> "$log" 2>&1 &
  local pid=$!
  (
    sleep "$timeout"
    if kill -0 "$pid" 2>/dev/null; then
      echo "# $marker: timeout after ${timeout}s" >> "$log"
      pkill -TERM -P "$pid" 2>/dev/null; kill -TERM "$pid" 2>/dev/null
      sleep 15
      pkill -KILL -P "$pid" 2>/dev/null; kill -KILL "$pid" 2>/dev/null
    fi
  ) >/dev/null 2>&1 &
  local wd=$!
  wait "$pid"; local rc=$?
  pkill -P "$wd" 2>/dev/null; kill "$wd" 2>/dev/null; wait "$wd" 2>/dev/null
  return $rc
}

af_session_id() { # $1 log
  grep -m1 -E '^session id:' "$1" 2>/dev/null | sed 's/^session id:[[:space:]]*//'
}

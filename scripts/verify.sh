#!/bin/bash
# Compatibility shim: astrafabulopus 0.1 lived in scripts/verify.sh; it is bin/af-verify now.
exec "$(cd "$(dirname "$0")/.." && pwd)/bin/af-verify" "$@"

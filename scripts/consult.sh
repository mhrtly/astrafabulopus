#!/bin/bash
# Compatibility shim: astrafabulopus 0.1 lived in scripts/consult.sh; it is bin/af-consult now.
exec "$(cd "$(dirname "$0")/.." && pwd)/bin/af-consult" "$@"

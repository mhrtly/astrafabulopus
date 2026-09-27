#!/bin/bash
# Compatibility shim: astrafabulopus 0.1 lived in scripts/lane.sh; it is bin/af-lane now.
exec "$(cd "$(dirname "$0")/.." && pwd)/bin/af-lane" "$@"

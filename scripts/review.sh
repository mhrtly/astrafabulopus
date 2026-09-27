#!/bin/bash
# Compatibility shim: astrafabulopus 0.1 lived in scripts/review.sh; it is bin/af-review now.
exec "$(cd "$(dirname "$0")/.." && pwd)/bin/af-review" "$@"

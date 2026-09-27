#!/usr/bin/env python3
"""Internal entry point for the bash lanes: python3 lib/af.py <helper> ... (see astrafab/lanes.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

from astrafab import lanes  # noqa: E402

if __name__ == "__main__":
    sys.exit(lanes.main(sys.argv[1:]))

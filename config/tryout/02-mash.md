Objective: `spudlib.mash.chunk` drops the last chunk of its input (for example
`chunk([1, 2, 3, 4, 5], 2)` returns `[[1, 2], [3, 4]]` instead of `[[1, 2], [3, 4], [5]]`). Fix the
bug so every element appears, in order, in chunks of at most `size`.

Files: modify `spudlib/mash.py` only.

Interfaces: keep `def chunk(items, size)` and its ValueError for `size < 1`.

Constraints: fix the cause, do not special-case the test inputs. Do not edit the tests. Keep the
change minimal. Do not commit.

Verification: `python3 -m unittest tests.test_mash -v`

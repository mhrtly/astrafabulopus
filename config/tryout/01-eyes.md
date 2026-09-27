Objective: add `count_eyes` to spudlib. An "eye" is a run of one or more consecutive letters "o"
(either case); count the runs. "potato" has 2 eyes, "Moo" has 1, "O o O" has 3, "" has 0.

Files: create `spudlib/eyes.py`.

Interfaces: `def count_eyes(text: str) -> int`

Constraints: standard library only. Keep the change minimal. Do not edit the tests. Do not commit.

Verification: `python3 -m unittest tests.test_eyes -v`

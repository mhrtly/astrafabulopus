Objective: add `fair_split`, which divides a whole number of cents among weighted shares so the
parts always add up to exactly the total. Use the largest-remainder method: give each share the
floor of its exact portion, then hand the leftover cents one at a time to the shares with the
largest fractional remainders, breaking ties by the lower index.

Files: create `spudlib/pantry.py`.

Interfaces: `def fair_split(total_cents: int, weights: list) -> list` returning a list of ints, one
per weight, in the same order.

Constraints: raise ValueError when total_cents is negative, when weights is empty, when any weight
is negative, or when all weights are zero. A zero weight always gets 0. Use exact integer arithmetic
(no floating-point rounding). Standard library only. Do not edit the tests. Do not commit.

Verification: `python3 -m unittest tests.test_pantry -v`

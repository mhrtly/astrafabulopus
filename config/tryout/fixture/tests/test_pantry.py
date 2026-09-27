import random
import unittest


class FairSplitTest(unittest.TestCase):
    def setUp(self):
        from spudlib.pantry import fair_split
        self.split = fair_split

    def test_even_three_way(self):
        self.assertEqual(self.split(100, [1, 1, 1]), [34, 33, 33])

    def test_largest_remainder_wins(self):
        self.assertEqual(self.split(7, [2, 1]), [5, 2])
        self.assertEqual(self.split(10, [1, 2, 2]), [2, 4, 4])

    def test_zero_weight_gets_nothing(self):
        self.assertEqual(self.split(10, [0, 1]), [0, 10])

    def test_zero_total(self):
        self.assertEqual(self.split(0, [1, 2]), [0, 0])

    def test_always_sums_exactly(self):
        rng = random.Random(1729)
        for _ in range(300):
            total = rng.randint(0, 10000)
            weights = [rng.randint(0, 9) for _ in range(rng.randint(1, 7))]
            if not any(weights):
                weights[0] = 1
            parts = self.split(total, weights)
            self.assertEqual(sum(parts), total)
            self.assertEqual(len(parts), len(weights))
            self.assertTrue(all(isinstance(p, int) and p >= 0 for p in parts))
            for p, w in zip(parts, weights):
                if w == 0:
                    self.assertEqual(p, 0)

    def test_bad_inputs(self):
        with self.assertRaises(ValueError):
            self.split(10, [])
        with self.assertRaises(ValueError):
            self.split(10, [0, 0])
        with self.assertRaises(ValueError):
            self.split(-1, [1])
        with self.assertRaises(ValueError):
            self.split(10, [1, -1])


if __name__ == "__main__":
    unittest.main()

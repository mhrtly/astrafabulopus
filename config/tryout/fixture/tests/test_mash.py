import unittest

from spudlib.mash import chunk


class ChunkTest(unittest.TestCase):
    def test_uneven_tail_is_kept(self):
        self.assertEqual(chunk([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]])

    def test_exact_fit(self):
        self.assertEqual(chunk([1, 2, 3], 3), [[1, 2, 3]])
        self.assertEqual(chunk([1, 2, 3, 4], 2), [[1, 2], [3, 4]])

    def test_small_inputs(self):
        self.assertEqual(chunk([], 3), [])
        self.assertEqual(chunk([1], 5), [[1]])

    def test_accepts_any_sequence(self):
        self.assertEqual(chunk("spuds", 2), [["s", "p"], ["u", "d"], ["s"]])

    def test_rejects_nonpositive_size(self):
        with self.assertRaises(ValueError):
            chunk([1, 2], 0)


if __name__ == "__main__":
    unittest.main()

import unittest


class CountEyesTest(unittest.TestCase):
    def setUp(self):
        from spudlib.eyes import count_eyes
        self.count = count_eyes

    def test_potato_has_two_eyes(self):
        self.assertEqual(self.count("potato"), 2)

    def test_empty_and_eyeless(self):
        self.assertEqual(self.count(""), 0)
        self.assertEqual(self.count("spud"), 0)

    def test_runs_of_o_are_one_eye(self):
        self.assertEqual(self.count("Moo"), 1)
        self.assertEqual(self.count("OoOo"), 1)
        self.assertEqual(self.count("boo hoo"), 2)

    def test_case_insensitive_and_spaces_split_runs(self):
        self.assertEqual(self.count("O o O"), 3)


if __name__ == "__main__":
    unittest.main()

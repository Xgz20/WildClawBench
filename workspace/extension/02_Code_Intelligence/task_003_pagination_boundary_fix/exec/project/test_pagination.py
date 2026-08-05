import unittest

from pagination import paginate


class Fetcher:
    def __init__(self, rows):
        self.rows = list(rows)
        self.calls = []

    def __call__(self, *, limit, offset):
        self.calls.append((limit, offset))
        return self.rows[offset : offset + limit]


class PaginationTest(unittest.TestCase):
    def test_partial_first_page(self):
        fetch = Fetcher(["a", "b", "c"])
        self.assertEqual(
            paginate(fetch, 1, 2),
            {"items": ["a", "b"], "has_next": True},
        )

    def test_partial_last_page(self):
        fetch = Fetcher(["a", "b", "c"])
        self.assertEqual(
            paginate(fetch, 2, 2),
            {"items": ["c"], "has_next": False},
        )

    def test_out_of_range_page(self):
        fetch = Fetcher(["a"])
        self.assertEqual(paginate(fetch, 4, 2), {"items": [], "has_next": False})

    def test_invalid_page_size(self):
        with self.assertRaises(ValueError):
            paginate(Fetcher([]), 1, 0)


if __name__ == "__main__":
    unittest.main()

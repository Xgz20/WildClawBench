import unittest

from inventory import aggregate_inventory


class InventoryTests(unittest.TestCase):
    def test_aggregates_and_sorts(self):
        rows = [
            {"sku": "B200", "quantity": "1"},
            {"sku": "A100", "quantity": "2"},
            {"sku": "B200", "quantity": "4"},
        ]
        self.assertEqual(
            aggregate_inventory(rows),
            [
                {"sku": "A100", "quantity": 2},
                {"sku": "B200", "quantity": 5},
            ],
        )

    def test_empty(self):
        self.assertEqual(aggregate_inventory([]), [])


if __name__ == "__main__":
    unittest.main()

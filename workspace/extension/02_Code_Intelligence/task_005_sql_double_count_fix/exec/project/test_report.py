import csv
import io
import sqlite3
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def report_rows():
    connection = sqlite3.connect(":memory:")
    connection.executescript((ROOT / "schema.sql").read_text(encoding="utf-8"))
    connection.executescript((ROOT / "fixtures.sql").read_text(encoding="utf-8"))
    cursor = connection.execute((ROOT / "report.sql").read_text(encoding="utf-8"))
    header = [item[0] for item in cursor.description]
    rows = cursor.fetchall()
    connection.close()
    return header, rows


class ReportTest(unittest.TestCase):
    def test_expected_report(self):
        header, rows = report_rows()
        self.assertEqual(
            header,
            ["property_id", "property_name", "lease_count", "visit_count"],
        )
        self.assertEqual(
            rows,
            [
                (1, "Harbor House", 2, 3),
                (2, "Maple Court", 1, 0),
                (3, "Pine Studios", 0, 1),
                (4, "Riverside Empty", 0, 0),
            ],
        )


if __name__ == "__main__":
    unittest.main()

import copy
import sqlite3
import unittest

from store import BatchError, create_schema, import_batch


def batch():
    return {"people": [{"id": "p1", "name": " 小陈 "}], "rooms": [{"id": "r1", "capacity": 4}],
            "bookings": [{"id": "b1", "person_id": "p1", "room_id": "r1", "seats": 2}]}


class StoreContractTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.addCleanup(self.conn.close)
        create_schema(self.conn)

    def snapshot(self):
        return {name: self.conn.execute(f"SELECT * FROM {name} ORDER BY id").fetchall() for name in ("people", "rooms", "bookings")}

    def test_basic_and_exact_retry(self):
        self.assertEqual(import_batch(self.conn, batch()), {"inserted": {"people": 1, "rooms": 1, "bookings": 1}, "skipped": {"people": 0, "rooms": 0, "bookings": 0}})
        before = self.snapshot()
        self.assertEqual(import_batch(self.conn, batch()), {"inserted": {"people": 0, "rooms": 0, "bookings": 0}, "skipped": {"people": 1, "rooms": 1, "bookings": 1}})
        self.assertEqual(self.snapshot(), before)

    def test_missing_person_rolls_back_new_parents(self):
        value = batch()
        value["bookings"][0]["person_id"] = "absent"
        with self.assertRaises(BatchError) as caught:
            import_batch(self.conn, value)
        self.assertEqual((caught.exception.code, caught.exception.entity, caught.exception.index), ("E_PERSON", "bookings", 0))
        self.assertEqual(self.snapshot(), {"people": [], "rooms": [], "bookings": []})

    def test_injection_after_final_insert_is_atomic(self):
        with self.assertRaises(BatchError) as caught:
            import_batch(self.conn, batch(), fail_after=3)
        self.assertEqual(caught.exception.code, "E_INJECTED")
        self.assertEqual(self.snapshot(), {"people": [], "rooms": [], "bookings": []})

    def test_failure_preserves_caller_transaction(self):
        self.conn.execute("INSERT INTO people VALUES ('outer', '调用者')")
        with self.assertRaises(BatchError):
            import_batch(self.conn, batch(), fail_after=1)
        self.assertTrue(self.conn.in_transaction)
        self.assertEqual(self.snapshot()["people"], [("outer", "调用者")])
        self.conn.rollback()
        self.assertEqual(self.snapshot()["people"], [])

    def test_success_does_not_commit_caller_transaction(self):
        self.conn.execute("INSERT INTO people VALUES ('outer', '调用者')")
        import_batch(self.conn, batch())
        self.assertTrue(self.conn.in_transaction)
        self.conn.rollback()
        self.assertEqual(self.snapshot(), {"people": [], "rooms": [], "bookings": []})

    def test_capacity_is_total_not_per_booking(self):
        import_batch(self.conn, batch())
        before = self.snapshot()
        value = {"people": [{"id": "p2", "name": "乙"}], "rooms": [],
                 "bookings": [{"id": "b2", "person_id": "p2", "room_id": "r1", "seats": 3}]}
        with self.assertRaises(BatchError) as caught:
            import_batch(self.conn, value)
        self.assertEqual(caught.exception.code, "E_CAPACITY")
        self.assertEqual(self.snapshot(), before)

    def test_conflict_is_not_replace(self):
        import_batch(self.conn, batch())
        before = self.snapshot()
        value = batch()
        value["people"][0]["name"] = "改名"
        with self.assertRaises(BatchError) as caught:
            import_batch(self.conn, value)
        self.assertEqual(caught.exception.code, "E_ID_CONFLICT")
        self.assertEqual(self.snapshot(), before)

    def test_skip_does_not_advance_injection_counter(self):
        import_batch(self.conn, batch())
        result = import_batch(self.conn, batch(), fail_after=1)
        self.assertEqual(result["inserted"]["bookings"], 0)

    def test_no_database_foreign_keys_or_triggers(self):
        for table in ("people", "rooms", "bookings"):
            self.assertEqual(self.conn.execute(f"PRAGMA foreign_key_list({table})").fetchall(), [])
        self.assertEqual(self.conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall(), [])


if __name__ == "__main__":
    unittest.main()

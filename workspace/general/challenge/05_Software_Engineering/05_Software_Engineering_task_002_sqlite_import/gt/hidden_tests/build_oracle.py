"""Explicitly labelled SQLite action/state vectors; no implementation is imported."""
from copy import deepcopy
import json
from pathlib import Path


P = {"id": "p1", "name": " 小陈 "}
R = {"id": "r1", "capacity": 4}
B = {"id": "b1", "person_id": "p1", "room_id": "r1", "seats": 2}
BASE = {"people": [P], "rooms": [R], "bookings": [B]}
INJECTED = {"people": [{"id": "p2", "name": "乙"}], "rooms": [{"id": "r2", "capacity": 3}],
            "bookings": [{"id": "b2", "person_id": "p2", "room_id": "r2", "seats": 3}]}


def state(people=(), rooms=(), bookings=()):
    return {"people": sorted([list(row) for row in people]), "rooms": sorted([list(row) for row in rooms]),
            "bookings": sorted([list(row) for row in bookings])}


EMPTY = state()
S1 = state([("p1", " 小陈 ")], [("r1", 4)], [("b1", "p1", "r1", 2)])
S2 = state([("p1", " 小陈 ")], [("r1", 4)], [("b1", "p1", "r1", 2), ("b2", "p1", "r1", 2)])
OUTER = state([("outer", "调用者")])
S1_OUTER = state([("outer", "调用者"), ("p1", " 小陈 ")], [("r1", 4)], [("b1", "p1", "r1", 2)])


def counts(inserted=(0, 0, 0), skipped=(0, 0, 0)):
    return {"inserted": dict(zip(("people", "rooms", "bookings"), inserted)),
            "skipped": dict(zip(("people", "rooms", "bookings"), skipped))}


def error(code, entity="batch", index=None):
    return {"error": {"code": code, "entity": entity, "index": index}}


def event(before, after, result, label="import", tx=False):
    return {"label": label, "before": before, "after": after, "result": result, "in_transaction": tx}


def action(batch, **extra):
    return {"kind": "import", "batch": batch, **extra}


def build():
    cases = []
    def case(name, actions, expected, *, seed=EMPTY, group="business", requirement="atomic_rollback"):
        cases.append(deepcopy({"id": name, "group": group, "requirement": requirement,
            "scenario": {"seed": seed, "actions": actions}, "expected_events": expected}))
    def rejected(name, value, code, entity="batch", index=None, *, seed=EMPTY, **extra):
        case(name, [action(value)], [event(seed, seed, error(code, entity, index))], seed=seed, **extra)

    case("basic-committed", [action(BASE), {"kind": "external", "label": "committed"}],
         [event(EMPTY, S1, counts((1, 1, 1))), {"label": "committed", "state": S1}], group="boundary", requirement="compatibility")
    case("retry-once", [action(BASE)], [event(S1, S1, counts(skipped=(1, 1, 1)))], seed=S1, requirement="idempotency")
    case("retry-twice", [action(BASE), action(BASE)], [event(S1, S1, counts(skipped=(1, 1, 1)))] * 2, seed=S1, requirement="idempotency")
    doubled = {key: rows * 2 for key, rows in BASE.items()}
    case("identical-in-batch", [action(doubled)], [event(EMPTY, S1, counts((1, 1, 1), (1, 1, 1)))], requirement="idempotency")
    value = {"people": [{"id": "p2", "name": "乙"}, {"id": "p1", "name": "改名"}], "rooms": [], "bookings": []}
    rejected("person-conflict-rolls-back-earlier", value, "E_ID_CONFLICT", "people", 1, seed=S1)
    value = {"people": [{"id": "p2", "name": "乙"}], "rooms": [{"id": "r2", "capacity": 3}, {"id": "r1", "capacity": 8}], "bookings": []}
    rejected("room-conflict-rolls-back-parent", value, "E_ID_CONFLICT", "rooms", 1, seed=S1)
    value = {"people": [], "rooms": [], "bookings": [{**B, "person_id": "absent"}]}
    rejected("booking-conflict-before-reference", value, "E_ID_CONFLICT", "bookings", 0, seed=S1, requirement="idempotency")
    value = deepcopy(BASE); value["bookings"][0]["person_id"] = "absent"
    rejected("missing-person", value, "E_PERSON", "bookings", 0, requirement="associations")
    value = deepcopy(BASE); value["bookings"][0]["room_id"] = "absent"
    rejected("missing-room", value, "E_ROOM", "bookings", 0, requirement="associations")
    value = deepcopy(BASE); value["bookings"] += [{"id": "b2", "person_id": "p1", "room_id": "r1", "seats": 3}]
    rejected("same-batch-capacity-aggregate", value, "E_CAPACITY", "bookings", 1, requirement="associations")
    value = {"people": [], "rooms": [], "bookings": [{"id": "b2", "person_id": "p1", "room_id": "r1", "seats": 3}]}
    rejected("prior-capacity-aggregate", value, "E_CAPACITY", "bookings", 0, seed=S1, requirement="associations")
    value = {"people": [], "rooms": [], "bookings": [{"id": "b2", "person_id": "p1", "room_id": "r1", "seats": 2}]}
    case("exact-capacity", [action(value)], [event(S1, S2, counts((0, 0, 1)))], seed=S1, group="boundary", requirement="compatibility")
    value = {"people": [], "rooms": [], "bookings": [B]}
    case("retry-when-full", [action(value)], [event(S2, S2, counts(skipped=(0, 0, 1)))], seed=S2, requirement="idempotency")
    for number, entity in ((1, "people"), (2, "rooms"), (3, "bookings")):
        case(f"inject-after-{number}", [action(BASE, fail_after=number)], [event(EMPTY, EMPTY, error("E_INJECTED", entity, 0))])
    case("inject-zero", [action({"people": [], "rooms": [], "bookings": []}, fail_after=0)],
         [event(EMPTY, EMPTY, error("E_INJECTED"))])
    case("inject-beyond-inserts", [action(BASE, fail_after=10)], [event(EMPTY, S1, counts((1, 1, 1)))], group="boundary", requirement="compatibility")
    case("skipped-does-not-inject", [action(BASE, fail_after=1)], [event(S1, S1, counts(skipped=(1, 1, 1)))], seed=S1, requirement="idempotency")
    for name, value in (("negative", -1), ("boolean", True), ("float", 1.0)):
        case("invalid-injection-" + name, [action(None, fail_after=value)], [event(S1, S1, error("E_CONFIG"))], seed=S1, group="boundary", requirement="error_priority")
    for name, value in (("null", None), ("missing-key", {"people": [], "rooms": []}),
                        ("extra-key", {"people": [], "rooms": [], "bookings": [], "extra": []}),
                        ("non-list", {"people": {}, "rooms": [], "bookings": []})):
        rejected("bad-root-" + name, value, "E_SCHEMA", group="boundary", requirement="field_types")
    rejected("bad-record-type", {"people": [4], "rooms": [], "bookings": []}, "E_ROW", "people", 0, group="boundary", requirement="field_types")
    value = deepcopy(BASE); value["rooms"][0]["capacity"] = True
    rejected("boolean-capacity", value, "E_FIELD", "rooms", 0, group="boundary", requirement="field_types")
    value = deepcopy(BASE); value["bookings"][0]["seats"] = 2.0
    rejected("float-seats", value, "E_FIELD", "bookings", 0, group="boundary", requirement="field_types")
    value = deepcopy(BASE); value["people"][0]["name"] = "　 "
    rejected("blank-name", value, "E_FIELD", "people", 0, group="boundary", requirement="field_types")
    value = deepcopy(BASE); value["people"][0]["id"] = "P1"
    rejected("invalid-identifier", value, "E_FIELD", "people", 0, group="boundary", requirement="field_types")
    value = {"people": [], "rooms": [], "bookings": [{"id": "b2", "person_id": "p1", "room_id": "r1", "seats": 3},
              {"id": "b3", "person_id": "absent", "room_id": "r1", "seats": 1}]}
    rejected("first-record-before-error-kind", value, "E_CAPACITY", "bookings", 0, seed=S1, group="boundary", requirement="error_priority")
    value = deepcopy(BASE); value["rooms"][0]["capacity"] = 0; value["bookings"][0]["person_id"] = "absent"
    rejected("parent-group-before-child", value, "E_FIELD", "rooms", 0, group="boundary", requirement="error_priority")
    case("caller-failure-isolated", [{"kind": "caller_person", "row": ["outer", "调用者"]}, action(INJECTED, fail_after=2),
         {"kind": "external", "label": "outside-before-rollback"}, {"kind": "rollback"}, {"kind": "snapshot", "label": "after-rollback"}],
         [event(S1_OUTER, S1_OUTER, error("E_INJECTED", "rooms", 0), tx=True),
          {"label": "outside-before-rollback", "state": S1}, {"label": "after-rollback", "state": S1, "in_transaction": False}],
         seed=S1, requirement="caller_transactions")
    case("caller-success-not-committed", [{"kind": "caller_person", "row": ["outer", "调用者"]}, action(BASE),
         {"kind": "external", "label": "uncommitted"}, {"kind": "rollback"}, {"kind": "snapshot", "label": "after-rollback"}],
         [event(OUTER, S1_OUTER, counts((1, 1, 1)), tx=True), {"label": "uncommitted", "state": EMPTY},
          {"label": "after-rollback", "state": EMPTY, "in_transaction": False}], requirement="caller_transactions")
    case("caller-can-commit", [{"kind": "caller_person", "row": ["outer", "调用者"]}, action(BASE), {"kind": "commit"},
         {"kind": "external", "label": "committed"}], [event(OUTER, S1_OUTER, counts((1, 1, 1)), tx=True),
         {"label": "committed", "state": S1_OUTER}], requirement="caller_transactions")
    case("schema-does-not-commit-caller", [{"kind": "caller_person", "row": ["outer", "调用者"]}, {"kind": "schema_again"},
         {"kind": "external", "label": "still-uncommitted"}, {"kind": "snapshot", "label": "local"}, {"kind": "rollback"}],
         [{"label": "still-uncommitted", "state": EMPTY}, {"label": "local", "state": OUTER, "in_transaction": True}], requirement="caller_transactions")
    value = {"people": [P, {"id": "p1", "name": "different"}], "rooms": [], "bookings": []}
    rejected("conflicting-duplicate-in-batch", value, "E_ID_CONFLICT", "people", 1, requirement="idempotency")
    value = {"people": [], "rooms": [R, R], "bookings": []}
    case("parent-repeat-in-batch", [action(value)], [event(EMPTY, state(rooms=[("r1", 4)]), counts((0, 1, 0), (0, 1, 0)))], requirement="idempotency")
    value = {"people": [{"id": "person-a", "name": " Éva\n用户 "}], "rooms": [], "bookings": []}
    case("raw-name-preserved", [action(value)], [event(EMPTY, state(people=[("person-a", " Éva\n用户 ")]), counts((1, 0, 0)))],
         group="boundary", requirement="compatibility")
    return cases


if __name__ == "__main__":
    Path(__file__).with_name("cases.json").write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n")

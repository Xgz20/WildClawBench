"""Independent date/decision model; never reads the manually labelled answers."""
import calendar
from datetime import date
from decimal import Decimal, ROUND_HALF_UP


def parsed_date(value):
    return date.fromisoformat(value) if value else None


def plus_months(value, months):
    total = value.year * 12 + value.month - 1 + months
    year, month = divmod(total, 12)
    month += 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def all_known(predicates):
    if False in predicates:
        return False
    return None if None in predicates else True


def select_rules(record):
    submitted = parsed_date(record["apply_date"])
    if submitted is None:
        return "待核实"
    if submitted < date(2025, 1, 1):
        return "未覆盖"
    if submitted < date(2026, 7, 1):
        return "V1"
    registered = record["registered"]
    registration = parsed_date(record["registered_at"])
    start = parsed_date(record["course_start"])
    t01 = all_known([
        registered == "yes" if registered else None,
        registration < date(2026, 7, 1) if registration else None,
        start < date(2026, 9, 1) if start else None,
    ])
    if t01 is True:
        return "V1-T01"
    if t01 is None:
        return "待核实"
    hired = parsed_date(record["hire_date"])
    formal = record["employee_type"] == "正式" if record["employee_type"] else None
    t02 = all_known([
        submitted <= date(2026, 12, 31), formal,
        plus_months(hired, 6) <= date(2026, 7, 1) < plus_months(hired, 12) if hired else None,
    ])
    return "V2-T02" if t02 is True else "待核实" if t02 is None else "V2"


def decide(record):
    rule_set = select_rules(record)
    if rule_set in {"未覆盖", "待核实"}:
        return {"rule_set": rule_set, "status": rule_set, "rate": None, "cap_cny": None, "grant_cny": None}
    old = rule_set.startswith("V1")
    months = 6 if old or rule_set == "V2-T02" else 12
    rate = Decimal("0.6") if old else Decimal("0.7")
    cap = 3000 if old else 4500
    submitted, hired = parsed_date(record["apply_date"]), parsed_date(record["hire_date"])
    kind = record["course_kind"]
    days = int(record["days"]) if record["days"] != "" else None
    conditions = [
        record["employee_type"] == "正式" if record["employee_type"] else None,
        plus_months(hired, months) <= submitted if hired else None,
        kind in ({"岗位技能", "学历提升"} if old else {"岗位技能"}) if kind else None,
        5 <= days <= (30 if old else 20) if days is not None else None,
    ]
    materials = [record[key] == "yes" if record[key] else None for key in ("approval", "completion", "invoice")]
    fee = Decimal(str(record["fee_cny"])) if record["fee_cny"] != "" else None
    eligible = all_known(conditions)
    if eligible is False:
        status, grant = "不资助", 0
    elif eligible is None or fee is None or None in materials:
        status, grant = "待核实", None
    elif False in materials:
        status, grant = "待补正", None
    else:
        status = "可资助"
        grant = float(min(fee * rate, Decimal(cap)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    return {"rule_set": rule_set, "status": status, "rate": float(rate), "cap_cny": cap, "grant_cny": grant}

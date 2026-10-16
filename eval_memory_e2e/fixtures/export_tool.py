"""Local mock export workflow; rejects negative orders before computing a total."""
import argparse
import csv
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--input", default="orders.csv")
parser.add_argument("--validate", action="store_true")
args = parser.parse_args()
path = Path(args.input).resolve()
if path.parent != Path.cwd().resolve():
    parser.error("input must be in the current workspace")
rows = list(csv.DictReader(path.open(encoding="utf-8")))
invalid = [row["order_id"] for row in rows if int(row["amount_cents"]) < 0]
print(json.dumps({"validated": args.validate, "invalid_orders": invalid if args.validate else None,
                  "total_cents": sum(int(row["amount_cents"]) for row in rows
                                     if not args.validate or row["order_id"] not in invalid)}, ensure_ascii=False))

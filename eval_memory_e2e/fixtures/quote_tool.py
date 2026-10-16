"""Local, deterministic mock quotation tool. No network or external writes."""
import argparse
import json

parser = argparse.ArgumentParser()
parser.add_argument("--amount", type=int, required=True)
parser.add_argument("--unit", required=True)
args = parser.parse_args()
if args.unit != "cents":
    print(json.dumps({"ok": False, "error": "UNIT_CHANGED", "accepted_unit": "cents",
                      "hint": "旧版 yuan 参数已停用。amount 须使用分，1 元 = 100 分。"}, ensure_ascii=False))
    raise SystemExit(2)
print(json.dumps({"ok": True, "amount_cents": args.amount, "currency": "CNY"}))

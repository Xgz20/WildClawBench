#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path


def aggregate_inventory(rows):
    """Aggregate integer quantities by SKU and return rows sorted by SKU."""
    raise NotImplementedError("implement aggregate_inventory")


def main():
    parser = argparse.ArgumentParser(description="Aggregate an inventory CSV")
    parser.add_argument("input_csv")
    parser.add_argument("output_json")
    args = parser.parse_args()

    with open(args.input_csv, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    result = {"inventory": aggregate_inventory(rows)}

    output = Path(args.output_json)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Publish built-in menu capabilities; does not create sandboxes or copy credentials."""

from pathlib import Path
import argparse, json, sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.e2e import DEFAULT_AGENTCUBE_TEMPLATE
from src.e2e.controller_catalog import chatgpt_desktop_profile, controller_catalog, profiles_from_catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controller-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--template", default=DEFAULT_AGENTCUBE_TEMPLATE)
    parser.add_argument("--chatgpt-desktop-template", help="publish an independently registered Desktop template")
    args = parser.parse_args()
    value = controller_catalog(args.controller_root)
    profiles = profiles_from_catalog(value, args.template)
    if args.chatgpt_desktop_template:
        profiles.append(chatgpt_desktop_profile(
            args.controller_root, args.chatgpt_desktop_template, value["source_revision"]
        ))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(
            {
                "schema": "wildclawbench.e2e-capabilities/v1",
                "controller_revision": value["source_revision"],
                "source_hashes": value["source_hashes"],
                "profiles": profiles,
            },
            stream,
            ensure_ascii=False,
            indent=2,
        )
        stream.write("\n")
    print(
        json.dumps(
            {
                "source_revision": value["source_revision"],
                "products": {
                    key: len(row["models"]) for key, row in value["products"].items()
                },
            }
        )
    )


if __name__ == "__main__":
    main()

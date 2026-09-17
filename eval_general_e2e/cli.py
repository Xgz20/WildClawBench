"""Formal repository CLI for General E2E discovery and layout checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from .layout import find_repo_root, inspect_repository_layout
from .stages import BUNDLE_PROTOCOL, CONTRACT_VERSION, GENERAL_E2E_SKILLS, get_skill_spec


def _skill_payload(name: Optional[str]) -> dict:
    specs = (get_skill_spec(name),) if name else GENERAL_E2E_SKILLS
    return {
        "schema_version": "wildclawbench.general-e2e-skill-registry/v1",
        "contract_version": CONTRACT_VERSION,
        "bundle_protocol": BUNDLE_PROTOCOL,
        "skill_count": len(specs),
        "skills": [spec.as_dict() for spec in specs],
    }


def _print_skill_table(payload: dict) -> None:
    for skill in payload["skills"]:
        stages = ",".join(skill["stages"])
        print(
            f"{skill['name']}\t{skill['implementation_status']}\t{stages}\t"
            f"{skill['responsibility']}"
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m eval_general_e2e",
        description="General E2E repository integration entrypoint",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    skills = subparsers.add_parser(
        "skills", help="list locked General E2E Skill identities and readiness"
    )
    skills.add_argument("--name", choices=[spec.name for spec in GENERAL_E2E_SKILLS])
    skills.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    layout = subparsers.add_parser(
        "check-layout", help="validate canonical sources, discovery links and legacy entry"
    )
    layout.add_argument("--repo-root", type=Path, default=None)
    layout.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "skills":
        payload = _skill_payload(args.name)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            _print_skill_table(payload)
        return 0

    repo_root = args.repo_root.resolve() if args.repo_root else find_repo_root()
    report = inspect_repository_layout(repo_root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"{report['status']}: {report['expected_skill_count']} General E2E Skills; "
            f"legacy eval_e2e preserved={str(report['legacy_eval_e2e']['preserved']).lower()}"
        )
        for error in report["errors"]:
            skill = f" [{error['skill']}]" if error.get("skill") else ""
            print(f"- {error['code']}{skill}: {error['detail']}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

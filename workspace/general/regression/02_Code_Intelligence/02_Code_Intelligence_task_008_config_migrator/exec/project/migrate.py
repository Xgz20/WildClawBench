"""Migrate service configuration files to schema version 3."""

import argparse
import json
from pathlib import Path


class MigrationError(ValueError):
    pass


def migrate_document(document):
    """Return a validated version-3 document without mutating the input."""
    raise NotImplementedError("migration is not implemented")


def migrate_file(config_path, schema_path):
    path = Path(config_path)
    json.loads(Path(schema_path).read_text(encoding="utf-8"))
    document = json.loads(path.read_text(encoding="utf-8"))
    migrated = migrate_document(document)
    path.write_text(json.dumps(migrated, indent=2) + "\n", encoding="utf-8")
    return migrated


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    parser.add_argument("--schema", required=True)
    args = parser.parse_args(argv)
    try:
        migrate_file(args.config, args.schema)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(2, f"migration failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

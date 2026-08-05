"""Reference configuration migrator."""

import argparse
import copy
import json
import os
from pathlib import Path
import tempfile


class MigrationError(ValueError):
    pass


def _require_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise MigrationError(f"{label} must be a non-empty string")
    return value


def _require_features(value):
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise MigrationError("features must be an array of strings")
    return list(value)


def _validate_v3(document):
    if not isinstance(document, dict) or document.get("version") != 3:
        raise MigrationError("version must be 3")
    service = document.get("service")
    timeouts = document.get("timeouts")
    features = document.get("features")
    if not isinstance(service, dict):
        raise MigrationError("service must be an object")
    _require_text(service.get("name"), "service.name")
    _require_text(service.get("endpoint"), "service.endpoint")
    if not isinstance(timeouts, dict):
        raise MigrationError("timeouts must be an object")
    timeout = timeouts.get("request_seconds")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
        raise MigrationError("timeouts.request_seconds must be a positive integer")
    if not isinstance(features, dict):
        raise MigrationError("features must be an object")
    _require_features(features.get("enabled"))


def _v1_to_v2(document):
    known = {"version", "service_name", "endpoint", "timeout_seconds", "features"}
    result = {key: copy.deepcopy(value) for key, value in document.items() if key not in known}
    result.update(
        {
            "version": 2,
            "service": {
                "name": _require_text(document.get("service_name"), "service_name"),
                "endpoint": _require_text(document.get("endpoint"), "endpoint"),
            },
            "request_timeout_seconds": document.get("timeout_seconds"),
            "features": _require_features(document.get("features")),
        }
    )
    return result


def _v2_to_v3(document):
    known = {"version", "service", "request_timeout_seconds", "features"}
    result = {key: copy.deepcopy(value) for key, value in document.items() if key not in known}
    service = document.get("service")
    if not isinstance(service, dict):
        raise MigrationError("service must be an object")
    result.update(
        {
            "version": 3,
            "service": copy.deepcopy(service),
            "timeouts": {"request_seconds": document.get("request_timeout_seconds")},
            "features": {"enabled": _require_features(document.get("features"))},
        }
    )
    return result


def migrate_document(document):
    if not isinstance(document, dict):
        raise MigrationError("configuration must be an object")
    version = document.get("version")
    working = copy.deepcopy(document)
    if version == 1:
        working = _v1_to_v2(working)
        version = 2
    if version == 2:
        working = _v2_to_v3(working)
    elif version != 3:
        raise MigrationError("unsupported configuration version")
    _validate_v3(working)
    return working


def migrate_file(config_path, schema_path):
    path = Path(config_path)
    json.loads(Path(schema_path).read_text(encoding="utf-8"))
    document = json.loads(path.read_text(encoding="utf-8"))
    migrated = migrate_document(document)
    payload = json.dumps(migrated, ensure_ascii=False, indent=2) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
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

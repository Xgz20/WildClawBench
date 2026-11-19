"""Reference solution for the fixed-version tomllib task."""

import json
from pathlib import Path
import sys
import tomllib


class MetadataError(ValueError):
    pass


def read_project_metadata(path):
    with Path(path).open("rb") as handle:
        document = tomllib.load(handle)
    project = document.get("project")
    if not isinstance(project, dict):
        raise MetadataError("project table is missing")
    name = project.get("name")
    if not isinstance(name, str) or not name.strip():
        raise MetadataError("project.name must be a non-empty string")
    version = project.get("version")
    if version is not None and not isinstance(version, str):
        raise MetadataError("project.version must be a string when present")
    dependencies = project.get("dependencies", [])
    if not isinstance(dependencies, list) or any(
        not isinstance(item, str) for item in dependencies
    ):
        raise MetadataError("project.dependencies must be an array of strings")
    return {
        "name": name,
        "version": version,
        "dependencies": list(dependencies),
    }


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        print("usage: pyproject_reader.py PATH", file=sys.stderr)
        return 4
    try:
        result = read_project_metadata(arguments[0])
    except FileNotFoundError:
        print(f"file not found: {arguments[0]}", file=sys.stderr)
        return 2
    except tomllib.TOMLDecodeError as exc:
        print(f"invalid TOML: {exc}", file=sys.stderr)
        return 3
    except (OSError, MetadataError) as exc:
        print(f"invalid project metadata: {exc}", file=sys.stderr)
        return 4
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

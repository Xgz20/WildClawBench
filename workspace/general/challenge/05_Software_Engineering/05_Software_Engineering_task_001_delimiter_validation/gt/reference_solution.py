"""Independent author reference, not part of the candidate execution input."""
from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
import re
import unicodedata


class ImportFailure(Exception):
    def __init__(self, code, row=None, field=None):
        self.error = {"code": code, "row": row, "field": field, "message": f"[{code}] Import rejected"}


def parse_courses(raw, separator, row):
    tokens, current, errors = [], [], set()
    if any(char in raw for char in ("｜", "；")):
        errors.add("E_DELIMITER_INVALID")
    cursor = 0
    while cursor < len(raw):
        char = raw[cursor]
        if char == "\\":
            cursor += 1
            if cursor == len(raw) or raw[cursor] not in {"\\", "|", ";"}:
                errors.add("E_ESCAPE")
                if cursor < len(raw):
                    current.append(raw[cursor])
            else:
                current.append(raw[cursor])
        elif char in {"｜", "；"}:
            errors.add("E_DELIMITER_INVALID")
            current.append(char)
        elif char in {"|", ";"} and char != separator:
            errors.add("E_DELIMITER_MIXED")
            current.append(char)
        elif char == separator:
            tokens.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        cursor += 1
    tokens.append("".join(current).strip())
    keys = [unicodedata.normalize("NFC", value).casefold() for value in tokens]
    if any(not token for token in tokens):
        errors.add("E_COURSE_EMPTY")
    if len(keys) != len(set(keys)):
        errors.add("E_COURSE_DUP")
    for code in ("E_DELIMITER_INVALID", "E_DELIMITER_MIXED", "E_ESCAPE", "E_COURSE_EMPTY", "E_COURSE_DUP"):
        if code in errors:
            raise ImportFailure(code, row, "courses")
    return tokens


def import_bytes(data, file_format="csv", course_separator="|"):
    if file_format not in {"csv", "tsv"} or course_separator not in {"|", ";"}:
        raise ImportFailure("E_CONFIG")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportFailure("E_ENCODING") from exc
    try:
        rows = list(csv.reader(io.StringIO(text, newline=""), delimiter="," if file_format == "csv" else "\t", strict=True))
    except csv.Error as exc:
        raise ImportFailure("E_CSV_SYNTAX") from exc
    if not rows or len(rows[0]) != 3 or set(rows[0]) != {"id", "name", "courses"}:
        raise ImportFailure("E_HEADER", 1)
    columns = {name: index for index, name in enumerate(rows[0])}
    output, seen = [], set()
    for row_number, cells in enumerate(rows[1:], 2):
        if not cells:
            continue
        if len(cells) != 3:
            raise ImportFailure("E_ROW_WIDTH", row_number)
        student_id = cells[columns["id"]].strip()
        name = cells[columns["name"]]
        raw_courses = cells[columns["courses"]]
        if not student_id:
            raise ImportFailure("E_ID_EMPTY", row_number, "id")
        if not re.fullmatch(r"[A-Z][0-9]{3}", student_id):
            raise ImportFailure("E_ID_FORMAT", row_number, "id")
        if student_id in seen:
            raise ImportFailure("E_ID_DUP", row_number, "id")
        if not name.strip():
            raise ImportFailure("E_NAME_EMPTY", row_number, "name")
        courses = parse_courses(raw_courses, course_separator, row_number)
        output.append({"id": student_id, "name": name, "courses": courses, "raw_courses": raw_courses})
        seen.add(student_id)
    return {"ok": True, "records": output, "stats": {"students": len(output), "enrollments": sum(len(record["courses"]) for record in output)}}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--format", default="csv")
    parser.add_argument("--course-separator", default="|")
    args = parser.parse_args(argv)
    try:
        if args.format not in {"csv", "tsv"} or args.course_separator not in {"|", ";"}:
            raise ImportFailure("E_CONFIG")
        try:
            data = Path(args.input).read_bytes()
        except OSError as exc:
            raise ImportFailure("E_IO") from exc
        result = import_bytes(data, args.format, args.course_separator)
    except ImportFailure as exc:
        print(json.dumps({"ok": False, "error": exc.error}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

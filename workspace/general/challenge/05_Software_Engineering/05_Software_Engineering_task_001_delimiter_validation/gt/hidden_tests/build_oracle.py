"""Declarative independently labelled examples; never imports an implementation."""
import base64
import csv
import io
import json
from pathlib import Path


def build():
    cases = []

    def success(key, records, *, fmt="csv", sep="|", header=None, bom=False, newline="\n", group="business"):
        header = header or ["id", "name", "courses"]
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, delimiter="," if fmt == "csv" else "\t", lineterminator=newline)
        writer.writerow(header)
        expected = []
        for student_id, name, raw_courses, expected_courses in records:
            row = {"id": student_id, "name": name, "courses": raw_courses}
            writer.writerow([row[column] for column in header])
            expected.append({"id": student_id.strip(), "name": name, "raw_courses": raw_courses, "courses": expected_courses})
        raw = (("\ufeff" if bom else "") + stream.getvalue()).encode()
        result = {"ok": True, "records": expected, "stats": {"students": len(records), "enrollments": sum(len(row[3]) for row in records)}}
        add(key, raw, result, fmt, sep, group)

    def add(key, raw, expected, fmt="csv", sep="|", group="boundary"):
        cases.append({"id": key, "group": group, "input_base64": base64.b64encode(raw).decode(),
                      "format": fmt, "separator": sep, "expected": expected})

    def error(key, raw, code, row=None, field=None, *, fmt="csv", sep="|", group="boundary"):
        add(key, raw.encode() if isinstance(raw, str) else raw, {"ok": False, "error": {"code": code, "row": row, "field": field}}, fmt, sep, group)

    success("legacy-comma", [("A001", "Alice", "Math|Physics", ["Math", "Physics"]), ("A002", "Bob, Jr.", "Music", ["Music"])])
    success("tsv-semicolon", [("B003", "李四", "数学;物理", ["数学", "物理"])], fmt="tsv", sep=";", bom=True, newline="\r\n")
    success("column-permutation", [(" A005 ", " 张三 ", " 数学 | 物理 ", ["数学", "物理"])], header=["courses", "id", "name"])
    success("quoted-newline", [("C002", "甲\r\n乙", "Math|Music", ["Math", "Music"])], newline="\r\n")
    success("quote-preserved", [("D009", 'A "quoted" name', '音"乐|文学', ['音"乐', "文学"])])
    success("escaped-active-separator", [("E010", "甲", "几何\\|进阶|物理", ["几何|进阶", "物理"])])
    success("escaped-other-separator", [("F011", "甲", "Logic\\;Proof|Math", ["Logic;Proof", "Math"])])
    success("literal-backslash", [("G012", "甲", "A\\\\B|C", ["A\\B", "C"])])
    success("raw-nfd-preserved", [("H013", " Cafe\u0301 ", " Cafe\u0301 | 物理 ", ["Cafe\u0301", "物理"])])
    success("same-course-across-students", [("I014", "甲", "Math", ["Math"]), ("I015", "乙", "Math", ["Math"])])
    success("header-only", [])
    success("tsv-quoted-tab", [("J016", "甲\t乙", "A\\;B;C", ["A;B", "C"])], fmt="tsv", sep=";")
    add("blank-logical-record", b"id,name,courses\n\nK017,Kai,Math\n", {"ok": True, "records": [{"id": "K017", "name": "Kai", "raw_courses": "Math", "courses": ["Math"]}], "stats": {"students": 1, "enrollments": 1}}, group="business")
    error("invalid-config-precedes-decode", b"\xff", "E_CONFIG", sep="||", group="business")
    error("encoding", b"id,name,courses\nA001,\xff,Math\n", "E_ENCODING", group="business")
    error("header-missing", "id,name\nA001,Alice\n", "E_HEADER", 1, group="business")
    error("header-duplicate", "id,id,courses\nA001,A001,Math\n", "E_HEADER", 1, group="business")
    error("row-width", "id,name,courses\nA001,Alice,Math,extra\n", "E_ROW_WIDTH", 2, group="business")
    error("id-empty", "id,name,courses\n,Alice,Math\n", "E_ID_EMPTY", 2, "id", group="business")
    error("id-invalid-ascii", "id,name,courses\nA１２３,Alice,Math\n", "E_ID_FORMAT", 2, "id", group="business")
    error("id-duplicate", "id,name,courses\nA001,Alice,Math\n A001 ,Bob,Music\n", "E_ID_DUP", 3, "id", group="business")
    error("name-empty", "id,name,courses\nA001,　 ,Math\n", "E_NAME_EMPTY", 2, "name", group="business")
    error("fullwidth-pipe", "id,name,courses\nA001,Alice,Math｜Physics\n", "E_DELIMITER_INVALID", 2, "courses")
    error("fullwidth-semicolon", "id,name,courses\nA001,Alice,Math；Physics\n", "E_DELIMITER_INVALID", 2, "courses", sep=";")
    error("mixed-pipe", "id,name,courses\nA001,Alice,Math;Physics\n", "E_DELIMITER_MIXED", 2, "courses")
    error("mixed-semicolon", "id\tname\tcourses\r\nA001\tAlice\tMath|Physics\r\n", "E_DELIMITER_MIXED", 2, "courses", fmt="tsv", sep=";")
    error("unknown-escape", "id,name,courses\nA001,Alice,Math\\qPhysics\n", "E_ESCAPE", 2, "courses")
    error("trailing-escape", "id,name,courses\nA001,Alice,Math\\\n", "E_ESCAPE", 2, "courses")
    for key, value in (("empty-field", ""), ("leading-empty", "|Math"), ("trailing-empty", "Math|"), ("middle-empty", "Math|  |Physics")):
        error(key, f"id,name,courses\nA001,Alice,{value}\n", "E_COURSE_EMPTY", 2, "courses")
    error("duplicate-casefold", "id,name,courses\nA001,Alice, Math | MATH\n", "E_COURSE_DUP", 2, "courses")
    error("duplicate-nfc", "id,name,courses\nA001,Alice,Café|Cafe\u0301\n", "E_COURSE_DUP", 2, "courses")
    error("duplicate-casefold-expansion", "id,name,courses\nA001,Alice,Straße|STRASSE\n", "E_COURSE_DUP", 2, "courses")
    error("priority-id-before-courses", "id,name,courses\n,Alice,Math||Physics\n", "E_ID_EMPTY", 2, "id")
    error("priority-name-before-courses", "id,name,courses\nA001, ,Math;Physics|\n", "E_NAME_EMPTY", 2, "name")
    error("priority-first-record", "id,name,courses\nA001,Alice,Math|\n,Bob,Math\n", "E_COURSE_EMPTY", 2, "courses")
    error("priority-invalid-before-escape", "id,name,courses\nA001,Alice,Math\\｜Physics\n", "E_DELIMITER_INVALID", 2, "courses")
    error("priority-mixed-before-empty", "id,name,courses\nA001,Alice,Math;|\n", "E_DELIMITER_MIXED", 2, "courses")
    error("priority-escape-before-empty", "id,name,courses\nA001,Alice,Math\\q|\n", "E_ESCAPE", 2, "courses")
    error("quoted-logical-row", 'id,name,courses\nA001,"Alice\nSmith",Math\nA002,Bob,Math||Physics\n', "E_COURSE_EMPTY", 3, "courses")
    error("blank-record-still-counted", "id,name,courses\n\nA001,Alice,Math||Physics\n", "E_COURSE_EMPTY", 3, "courses")
    error("strict-csv-before-business", 'id,name,courses\n,Alice,Math\nA002,Bob,"unclosed\n', "E_CSV_SYNTAX")
    error("empty-file", b"", "E_HEADER", 1)
    error("header-literal", " id,name,courses\nA001,Alice,Math\n", "E_HEADER", 1)
    error("interior-bom-is-not-stripped", "id,name,courses\n\ufeffA001,Alice,Math\n", "E_ID_FORMAT", 2, "id")
    error("wrong-file-format-not-guessed", "id\tname\tcourses\nA001\tAlice\tMath\n", "E_HEADER", 1)
    error("only-empty-fields-not-a-blank-line", "id,name,courses\n,,\n", "E_ID_EMPTY", 2, "id")
    for case in cases:
        key = case["id"]
        delimiter_fixes = {"mixed-pipe", "empty-field", "leading-empty", "trailing-empty", "middle-empty", "priority-mixed-before-empty"}
        phase_fixes = {"priority-first-record", "priority-invalid-before-escape", "strict-csv-before-business", "encoding",
                       "priority-id-before-courses", "priority-name-before-courses", "priority-escape-before-empty"}
        if key in delimiter_fixes:
            case.update(group="business", requirement="delimiter_fix")
        elif key == "mixed-semicolon":
            case.update(group="business", requirement="cross_format_fix")
        elif key in phase_fixes:
            case.update(group="business", requirement="phase_and_record_routing")
        elif case["expected"]["ok"]:
            case.update(group="boundary", requirement="valid_tsv" if key.startswith("tsv-") else "valid_csv")
        elif key.startswith("duplicate-"):
            case.update(group="boundary", requirement="unicode_duplicates")
        else:
            case.update(group="boundary", requirement="other_errors")
    return cases


if __name__ == "__main__":
    path = Path(__file__).with_name("cases.json")
    path.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

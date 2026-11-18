"""Export only Loomy's bound OpenCode session subtree from a read-only backup.

No authentication/configuration tables are queried. The source connection is
read-only, including when a WAL writer is active; the temporary backup is private.
"""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone


def capture(request):
    path = Path(request["database"]).absolute()
    if path.is_symlink() or path.resolve(strict=True) != path or not path.is_file():
        raise ValueError("LOOMY_DATABASE_PATH_UNSAFE")
    source = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
    try:
        with tempfile.TemporaryDirectory(prefix="loomy-native-") as directory:
            backup_path = Path(directory) / "snapshot.sqlite"
            backup = sqlite3.connect(backup_path)
            try:
                source.backup(backup)
                backup.row_factory = sqlite3.Row
                if backup.execute("PRAGMA quick_check").fetchall()[0][0] != "ok":
                    raise ValueError("LOOMY_DATABASE_INTEGRITY_FAILED")
                required = {"session": {"id", "parent_id", "directory", "version", "time_created", "time_updated"},
                            "message": {"id", "session_id", "data", "time_created", "time_updated"},
                            "part": {"id", "session_id", "message_id", "data", "time_created", "time_updated"}}
                for table, columns in required.items():
                    actual = {row[1] for row in backup.execute("PRAGMA table_info(" + table + ")")}
                    if not columns.issubset(actual):
                        raise ValueError("LOOMY_DATABASE_SCHEMA_UNSUPPORTED:" + table)
                query = "SELECT id,parent_id,directory,version,time_created,time_updated FROM session ORDER BY time_created,id"
                sessions = [dict(row) for row in backup.execute(query)]
                if len(sessions) > 100000:
                    raise ValueError("LOOMY_NATIVE_ROW_BUDGET_EXCEEDED")
                roots = {row["id"] for row in sessions if row["parent_id"] is None
                         and (row["id"] == request.get("session_id") if request.get("session_id")
                              else row["directory"] == request.get("workspace"))}
                scope = set(roots)
                while True:
                    expanded = scope | {row["id"] for row in sessions if row["parent_id"] in scope}
                    if expanded == scope:
                        break
                    scope = expanded
                selected = [row for row in sessions if row["id"] in scope]
                activity = []
                tail_query = "SELECT id,data FROM message WHERE session_id=? ORDER BY time_created DESC,id DESC LIMIT 1"
                pending_query = "SELECT count(*) FROM part WHERE session_id=? AND json_extract(data,'$.type')='tool' AND coalesce(json_extract(data,'$.state.status'),'') NOT IN ('completed','error')"
                activity_ids = [row["id"] for row in sessions if not request.get("workspace") and not request.get("session_id") or row["id"] in scope]
                query += "\n" + tail_query + "\n" + pending_query + json.dumps(activity_ids)
                for row in sessions:
                    if (request.get("workspace") or request.get("session_id")) and row["id"] not in scope:
                        continue
                    tail = backup.execute(tail_query, (row["id"],)).fetchone()
                    info = json.loads(tail["data"]) if tail else {}
                    pending = backup.execute(pending_query, (row["id"],)).fetchone()[0]
                    completed = info.get("time", {}).get("completed")
                    settled = (info.get("role") == "assistant" and (info.get("finish") in {"stop", "length", "other"} or bool(info.get("error")))
                               and type(completed) is int and completed >= 0 and pending == 0)
                    activity.append({"session_id": row["id"], "parent_id": row["parent_id"], "directory": row["directory"],
                                     "status": "settled" if settled else "active_or_unknown", "last_message_id": tail["id"] if tail else None,
                                     "last_message_sha256": hashlib.sha256(tail["data"].encode("utf-8")).hexdigest() if tail else None,
                                     "last_role": info.get("role"), "finish": info.get("finish"), "completed_at": completed,
                                     "has_error": bool(info.get("error")), "pending_tool_count": pending})
                messages, parts = [], []
                if scope:
                    placeholders = ",".join("?" for _ in scope)
                    for table, target in [("message", messages), ("part", parts)]:
                        statement = "SELECT * FROM " + table + " WHERE session_id IN (" + placeholders + ") ORDER BY time_created,id"
                        query += "\n" + statement + json.dumps(sorted(scope))
                        target.extend(dict(row) for row in backup.execute(statement, sorted(scope)))
                        if len(target) > 100000:
                            raise ValueError("LOOMY_NATIVE_ROW_BUDGET_EXCEEDED")
                # Preserve each original JSON column byte-for-byte as a string.
                result = {"profile": "loomy-opencode-sqlite/v1", "observed_at": datetime.now(timezone.utc).isoformat(),
                          "session_index": selected if request.get("workspace") or request.get("session_id") else sessions,
                          "sessions": selected, "messages": messages, "parts": parts,
                          "session_activity": activity,
                          "snapshot": {"database_path": str(path), "method": "readonly-source-sqlite-online-backup",
                                       "quick_check": "ok", "query_sha256": hashlib.sha256(query.encode()).hexdigest()}}
            finally:
                backup.close()
            result["snapshot"]["snapshot_sha256"] = hashlib.sha256(backup_path.read_bytes()).hexdigest()
            return result
    finally:
        source.close()


if __name__ == "__main__":
    try:
        result = capture(json.load(sys.stdin))
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    except (ValueError, OSError, sqlite3.Error, KeyError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}))
        sys.exit(1)

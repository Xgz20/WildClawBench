export const QWENWORK_METADATA_GATE_SCHEMA =
  "wildclawbench.general-e2e-qwenwork-metadata-gate/v1";

function expectedString(value, label) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`QWENWORK_METADATA_GATE_EXPECTED_VALUE_MISSING: ${label}`);
  }
  return value;
}

function expectedWorkspace(value) {
  const workspace = expectedString(value, "workspace");
  if (!workspace.startsWith("/")) {
    throw new Error("QWENWORK_METADATA_GATE_WORKSPACE_NOT_ABSOLUTE");
  }
  return workspace.replace(/\/{2,}/gu, "/").replace(/\/$/u, "") || "/";
}

function sameWorkspace(value, workspace) {
  return typeof value === "string"
    && value.startsWith("/")
    && (value.replace(/\/{2,}/gu, "/").replace(/\/$/u, "") || "/") === workspace;
}

function coverage(rows, read, expected, { workspace = false } = {}) {
  let known = 0;
  let missing = 0;
  let mismatched = 0;
  for (const row of rows) {
    const value = read(row);
    if (value == null || value === "") {
      missing += 1;
    } else if ((workspace ? sameWorkspace(value, expected) : value === expected)) {
      known += 1;
    } else {
      mismatched += 1;
    }
  }
  return {
    known,
    total: rows.length,
    missing,
    mismatched,
  };
}

function firstPresent(row, fields) {
  for (const read of fields) {
    const value = read(row);
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return null;
}

function segmentSessionId(row) {
  return firstPresent(row, [
    (value) => value?.session_id,
    (value) => value?.sessionId,
    (value) => value?.data?.session_id,
    (value) => value?.data?.sessionId,
  ]);
}

function segmentWorkspace(row) {
  const values = [
    row?.cwd,
    row?.data?.cwd,
    row?.data?.project_root,
    row?.data?.target_dir,
    row?.data?.workspace,
  ].filter((value) => value !== undefined && value !== null && value !== "");
  if (!values.length) return null;
  // A row with multiple workspace claims is bound only when every claim agrees.
  return values.every((value) => typeof value === "string") ? values : values;
}

function segmentWorkspaceCoverage(rows, workspace) {
  let known = 0;
  let missing = 0;
  let mismatched = 0;
  for (const row of rows) {
    const values = segmentWorkspace(row);
    if (values == null) {
      missing += 1;
    } else if (values.every((value) => sameWorkspace(value, workspace))) {
      known += 1;
    } else {
      mismatched += 1;
    }
  }
  return { known, total: rows.length, missing, mismatched };
}

function binding(known, total, unit, source) {
  return { known, total, unit, source };
}

/**
 * Assess raw metadata before a QwenWork collection is archived.
 *
 * Transcript identity and cwd are required on every row. Segment files are
 * structurally bound by the discovered `<session_id>/segments` directory;
 * per-row session/cwd fields are reported with coverage and are never filled
 * in from that directory. At least one explicit segment workspace claim is
 * required, and any conflicting claim blocks collection.
 */
export function assessQwenMetadataCoverage({
  state,
  transcriptRows = [],
  segmentRows = [],
  segmentDirectoryBound = false,
}) {
  const sessionId = expectedString(state?.session?.session_id, "session_id");
  const workspace = expectedWorkspace(state?.session?.cwd);
  if (!Array.isArray(transcriptRows) || !Array.isArray(segmentRows)) {
    throw new Error("QWENWORK_METADATA_GATE_ROWS_INVALID");
  }

  const transcript = {
    rows: transcriptRows.length,
    session_id: coverage(transcriptRows, (row) => row?.sessionId, sessionId),
    cwd: coverage(transcriptRows, (row) => row?.cwd, workspace, { workspace: true }),
  };
  transcript.binding = binding(
    transcriptRows.filter((row) => row?.sessionId === sessionId && sameWorkspace(row?.cwd, workspace)).length,
    transcriptRows.length,
    "transcript_row",
    "explicit_session_id_and_cwd",
  );

  const segments = {
    rows: segmentRows.length,
    session_id: coverage(segmentRows, segmentSessionId, sessionId),
    cwd: segmentWorkspaceCoverage(segmentRows, workspace),
    directory_binding: binding(
      segmentDirectoryBound && segmentRows.length ? segmentRows.length : 0,
      segmentRows.length,
      "segment_row",
      "session_directory",
    ),
  };
  segments.binding = binding(
    segments.cwd.known,
    segmentRows.length,
    "segment_row",
    "explicit_workspace_claim",
  );

  const blockers = [];
  if (transcriptRows.length === 0) blockers.push("transcript_empty");
  if (transcript.session_id.missing > 0) blockers.push("transcript_session_id_missing");
  if (transcript.session_id.mismatched > 0) blockers.push("transcript_session_id_mismatch");
  if (transcript.cwd.missing > 0) blockers.push("transcript_cwd_missing");
  if (transcript.cwd.mismatched > 0) blockers.push("transcript_cwd_mismatch");
  if (segmentRows.length === 0) blockers.push("segments_empty");
  if (!segmentDirectoryBound) blockers.push("segment_directory_unbound");
  if (segments.session_id.mismatched > 0) blockers.push("segment_session_id_mismatch");
  if (segments.cwd.mismatched > 0) blockers.push("segment_cwd_mismatch");
  if (segments.cwd.known === 0) blockers.push("segment_cwd_unverified");

  const complete = [
    transcript.session_id,
    transcript.cwd,
    segments.session_id,
    segments.cwd,
  ].every((item) => item.known === item.total && item.missing === 0 && item.mismatched === 0);
  return {
    schema_version: QWENWORK_METADATA_GATE_SCHEMA,
    readiness: {
      ready_for_collect: blockers.length === 0,
      status: blockers.length ? "blocked" : complete ? "complete" : "partial",
      blockers,
    },
    transcript,
    segments,
    claims_withheld: [
      "per-row-segment-session_id_when_missing",
      "per-row-segment-cwd_when_missing",
      "terminal_state_from_metadata_only",
      "usage_from_metadata_only",
    ],
  };
}

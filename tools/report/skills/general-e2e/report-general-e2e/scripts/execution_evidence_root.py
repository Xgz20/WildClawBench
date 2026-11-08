"""Resolve an exact copied execution record back to its bound evidence directory."""
from pathlib import Path


def frozen_execution_evidence_root(unit_root, selected_record, record):
    unit=Path(unit_root).resolve(strict=True)
    selected=Path(selected_record)
    if selected.is_symlink() or not selected.is_file():
        raise ValueError('EXECUTION_EVIDENCE_SELECTED_RECORD_UNSAFE')
    direct=selected.parent
    state=direct/'execution/automation-state.json'
    if direct.resolve().is_relative_to(unit) and state.is_file() and not state.is_symlink():
        return direct
    identity=record.get('identity',{})
    values=[identity.get('task_id'),identity.get('attempt_id')]
    if any(not isinstance(v,str) or len(Path(v).parts)!=1 or v in {'.','..'} for v in values):
        raise ValueError('EXECUTION_EVIDENCE_IDENTITY_UNSAFE')
    root=unit/'evidence/tasks'/values[0]/values[1]
    original=root/'execution-record.json'
    if (not root.resolve().is_relative_to(unit) or original.is_symlink() or not original.is_file()
        or original.read_bytes()!=selected.read_bytes()):
        raise ValueError('EXECUTION_EVIDENCE_ORIGINAL_RECORD_MISMATCH')
    state=root/'execution/automation-state.json'
    if state.is_symlink() or not state.is_file():
        raise ValueError('EXECUTION_EVIDENCE_STATE_MISSING')
    return root

"""Freeze explicitly authorized reference research for a new rescore attempt."""
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import hashlib, json, os, re, shutil, stat, sys, uuid
from urllib.parse import urlsplit

SCHEMA = 'wildclawbench.general-e2e-reference-supplement/v1'
INPUT_SCHEMA = 'wildclawbench.general-e2e-reference-supplement-input/v1'
DIRECTORY = 'reference-supplement'
KINDS = {'publisher_full_text', 'publisher_public_appendices', 'publisher_metadata',
         'author_manuscript', 'citation_context_excerpt', 'secondary_citation',
         'research_note', 'original_source_binary'}
SHA = re.compile(r'[0-9a-f]{64}')
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,119}')
OFFICE_SUFFIXES = {'.docx','.docm','.xlsx','.xlsm','.xltx','.xltm','.pptx','.pptm','.potx','.potm','.ppsx','.ppsm'}


def guard_office_copy(path, expected_sha256):
    """Guard only a newly copied, exact reference; never repair historical bytes."""
    if path.suffix.lower() not in OFFICE_SUFFIXES:
        return False
    if sys.platform == 'darwin':
        os.chflags(path, path.stat().st_flags | stat.UF_IMMUTABLE, follow_symlinks=False)
    require(digest(path) == expected_sha256, 'REFERENCE_SUPPLEMENT_COPY_DRIFT')
    return True

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def load(path):
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('REFERENCE_SUPPLEMENT_OBJECT_REQUIRED')
    return value

def require(value, code):
    if not value:
        raise ValueError(code)

def safe_file(root, relative):
    require(isinstance(relative, str) and '\\' not in relative, 'REFERENCE_SUPPLEMENT_PATH_INVALID')
    parts = PurePosixPath(relative)
    require(not parts.is_absolute() and parts.parts and all(p not in {'.', '..'} for p in relative.split('/')), 'REFERENCE_SUPPLEMENT_PATH_INVALID')
    path = root
    for part in parts.parts:
        path = path / part
        require(not path.is_symlink(), 'REFERENCE_SUPPLEMENT_SYMLINK')
    require(path.is_file(), 'REFERENCE_SUPPLEMENT_FILE_MISSING')
    return path

def validate(root, attempt):
    folder = root / DIRECTORY
    if not os.path.lexists(folder):
        return []
    require(folder.is_dir() and not folder.is_symlink(), 'REFERENCE_SUPPLEMENT_DIRECTORY_INVALID')
    document = load(safe_file(folder, 'manifest.json'))
    lineage = attempt.get('lineage') or {}
    require(lineage.get('kind') == 'rescore' and document.get('schema_version') == SCHEMA,
            'REFERENCE_SUPPLEMENT_RESCORE_REQUIRED')
    require(attempt.get('judge', {}).get('protocol') == 'codex-agent-judge-v1',
            'REFERENCE_SUPPLEMENT_CODEX_JUDGE_REQUIRED')
    require(document.get('identity') == attempt.get('identity')
            and document.get('source_score_sha256') == lineage.get('source_score_sha256'),
            'REFERENCE_SUPPLEMENT_IDENTITY_MISMATCH')
    require(document.get('candidate_output') is False and document.get('candidate_behavior_evidence') is False
            and document.get('rubric_changed') is False, 'REFERENCE_SUPPLEMENT_ROLE_INVALID')
    entries = document.get('files')
    require(isinstance(entries, list) and 1 <= len(entries) <= 16, 'REFERENCE_SUPPLEMENT_SCOPE_INVALID')
    paths = ['manifest.json']
    for entry in entries:
        relative = entry.get('path')
        path = safe_file(folder, relative)
        require(relative not in paths and entry.get('size') == path.stat().st_size
                and entry.get('sha256') == digest(path), 'REFERENCE_SUPPLEMENT_FILE_DRIFT')
        paths.append(relative)
    actual = set()
    for path in folder.rglob('*'):
        require(not path.is_symlink(), 'REFERENCE_SUPPLEMENT_SYMLINK')
        if path.is_file():
            actual.add(path.relative_to(folder).as_posix())
        else:
            require(path.is_dir(), 'REFERENCE_SUPPLEMENT_TYPE_INVALID')
    require(actual == set(paths), 'REFERENCE_SUPPLEMENT_MEMBER_SET_DRIFT')
    files = [folder / relative for relative in paths]
    semantic = root / 'semantic'
    if semantic.exists():
        catalog = load(safe_file(semantic, 'evidence-catalog.json'))
        indexed = {entry['reference'].get('path'): entry['reference'].get('sha256')
                   for entry in catalog['evidence_index']['entries']}
        require(all(indexed.get(path.relative_to(root).as_posix()) == digest(path) for path in files),
                'REFERENCE_SUPPLEMENT_NOT_IN_FROZEN_CATALOG')
    return files

def register(rt, *, attempt_root, source_manifest, authorization_reference):
    root = Path(attempt_root).resolve(strict=True)
    rt.verify_attempt(root)
    attempt = load(root / 'attempt-manifest.json')
    lineage = attempt.get('lineage') or {}
    require(lineage.get('kind') == 'rescore', 'REFERENCE_SUPPLEMENT_RESCORE_REQUIRED')
    require(attempt.get('judge', {}).get('protocol') == 'codex-agent-judge-v1',
            'REFERENCE_SUPPLEMENT_CODEX_JUDGE_REQUIRED')
    require(isinstance(authorization_reference, str) and len(authorization_reference.strip()) >= 8,
            'REFERENCE_SUPPLEMENT_AUTHORIZATION_REQUIRED')
    source_manifest = Path(source_manifest).absolute()
    require(source_manifest.is_file() and not source_manifest.is_symlink()
            and source_manifest.stat().st_size <= 1024 * 1024, 'REFERENCE_SUPPLEMENT_INPUT_INVALID')
    incoming = load(source_manifest)
    require(set(incoming) == {'schema_version', 'task_id', 'source_score_sha256', 'documents'}
            and incoming['schema_version'] == INPUT_SCHEMA, 'REFERENCE_SUPPLEMENT_INPUT_SCHEMA_INVALID')
    require(incoming['task_id'] == attempt['identity']['task_id']
            and incoming['source_score_sha256'] == lineage['source_score_sha256'],
            'REFERENCE_SUPPLEMENT_SOURCE_SCORE_MISMATCH')
    source_hash = digest(source_manifest)
    target = root / DIRECTORY
    if os.path.lexists(target):
        files = validate(root, attempt)
        frozen = load(target / 'manifest.json')
        require(frozen['input_manifest_sha256'] == source_hash
                and frozen['authorization_reference'] == authorization_reference,
                'REFERENCE_SUPPLEMENT_OUTPUT_CONFLICT')
        return {'status': 'PASS', 'idempotent': True, 'manifest': str(files[0]), 'file_count': len(files) - 1}
    require(not any(os.path.lexists(root / name) for name in ['semantic', 'semantic-component.json', 'score.json']),
            'REFERENCE_SUPPLEMENT_TOO_LATE')
    rows = incoming['documents']
    require(isinstance(rows, list) and 1 <= len(rows) <= 16, 'REFERENCE_SUPPLEMENT_SCOPE_INVALID')
    documents = []
    names = set()
    total = 0
    for row in rows:
        require(isinstance(row, dict) and set(row) == {'name', 'path', 'sha256', 'size', 'url', 'retrieved_at', 'kind', 'description'},
                'REFERENCE_SUPPLEMENT_DOCUMENT_INVALID')
        require(isinstance(row['name'], str) and NAME.fullmatch(row['name']) and row['name'] not in names,
                'REFERENCE_SUPPLEMENT_NAME_INVALID')
        require(row['kind'] in KINDS and isinstance(row['description'], str)
                and 0 < len(row['description']) <= 4000, 'REFERENCE_SUPPLEMENT_PROVENANCE_REQUIRED')
        url = urlsplit(row['url'])
        require(url.scheme == 'https' and url.hostname and not url.username and not url.password,
                'REFERENCE_SUPPLEMENT_SOURCE_URL_INVALID')
        try:
            stamp = datetime.fromisoformat(row['retrieved_at'].replace('Z', '+00:00'))
            require(stamp.tzinfo is not None, 'REFERENCE_SUPPLEMENT_TIMESTAMP_INVALID')
        except (TypeError, AttributeError, ValueError) as error:
            raise ValueError('REFERENCE_SUPPLEMENT_TIMESTAMP_INVALID') from error
        path = safe_file(source_manifest.parent, row['path'])
        require(isinstance(row['size'], int) and not isinstance(row['size'], bool)
                and 0 < row['size'] <= 64 * 1024 * 1024 and row['size'] == path.stat().st_size
                and isinstance(row['sha256'], str) and SHA.fullmatch(row['sha256'])
                and digest(path) == row['sha256'], 'REFERENCE_SUPPLEMENT_SOURCE_FILE_DRIFT')
        names.add(row['name']); total += row['size']
        item = {key: value for key, value in row.items() if key != 'path'}
        item['path'] = 'files/' + row['name']
        documents.append((path, item))
    require(total <= 128 * 1024 * 1024, 'REFERENCE_SUPPLEMENT_TOTAL_LIMIT')
    document = {'schema_version': SCHEMA, 'identity': attempt['identity'],
                'source_score_sha256': lineage['source_score_sha256'], 'input_manifest_sha256': source_hash,
                'authorization_reference': authorization_reference,
                'created_at': datetime.now(timezone.utc).isoformat(), 'candidate_output': False,
                'candidate_behavior_evidence': False, 'rubric_changed': False,
                'files': [item for path, item in documents]}
    stage = root / ('.reference-supplement.staging-' + uuid.uuid4().hex)
    stage.mkdir()
    try:
        (stage / 'files').mkdir()
        guarded = []
        for path, item in documents:
            destination = stage / item['path']
            shutil.copyfile(path, destination, follow_symlinks=False)
            require(digest(destination) == item['sha256'] and digest(path) == item['sha256'],
                    'REFERENCE_SUPPLEMENT_COPY_DRIFT')
            if destination.suffix.lower() in OFFICE_SUFFIXES:
                guarded.append({'path':item['path'],'sha256':item['sha256']})
        if guarded:
            document['office_byte_guard']={'profile':'reference-supplement-office-byte-guard/v1',
                'platform':sys.platform,'user_immutable':sys.platform=='darwin','files':guarded,
                'original_bytes_changed':False}
        (stage / 'manifest.json').write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        rt._make_read_only(stage)
        for item in guarded:
            guard_office_copy(stage/item['path'],item['sha256'])
        stage.rename(target)
    except BaseException:
        rt._remove_tree(stage)
        raise
    files = validate(root, attempt)
    return {'status': 'PASS', 'idempotent': False, 'manifest': str(files[0]),
            'manifest_sha256': digest(files[0]), 'file_count': len(documents),
            'candidate_output': False, 'candidate_behavior_evidence': False, 'rubric_changed': False}

"""Seal verified report bytes before host metadata can alter separate copies."""
from pathlib import Path, PurePosixPath
import argparse, hashlib, json, os, stat, uuid, zipfile

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''): h.update(block)
    return h.hexdigest()

def require(ok, code):
    if not ok: raise ValueError(code)

def child(root, relative):
    p = PurePosixPath(relative)
    require(relative and not p.is_absolute() and '\\' not in relative and not any(v in ('.', '..') for v in p.parts), 'REPORT_SEAL_PATH')
    path = root.joinpath(*p.parts)
    require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root.resolve()), 'REPORT_SEAL_FILE')
    return path

def seal_report(report_dir, output_dir, *, batch_root=None):
    report_dir, output_dir = Path(report_dir).resolve(), Path(output_dir).resolve()
    require(report_dir.is_dir() and not output_dir.is_relative_to(report_dir), 'REPORT_SEAL_OUTPUT_LOCATION')
    formal = report_dir / 'receipts/report-receipt.json'
    composite = report_dir / 'composite-report-receipt.json'
    if formal.is_file():
        require(batch_root is not None, 'REPORT_SEAL_BATCH_ROOT_REQUIRED')
        receipt = json.loads(formal.read_text(encoding='utf-8'))
        for ref in receipt['artifacts']:
            path = child(Path(batch_root).resolve(), ref['path'])
            require(path.resolve().is_relative_to(report_dir) and sha(path) == ref['sha256'] and path.stat().st_size == ref['size'], 'REPORT_SEAL_ARTIFACT_DRIFT')
    else:
        require(composite.is_file(), 'REPORT_SEAL_RECEIPT_REQUIRED')
        receipt = json.loads(composite.read_text(encoding='utf-8'))
        data = json.loads(child(report_dir, 'general_e2e_report_data.json').read_text(encoding='utf-8'))
        for name, expected in [('general_e2e_report_data.json', receipt['source_json_sha256']),
                               (data['artifact_filenames']['excel'], receipt['excel_sha256'])]:
            require(sha(child(report_dir, name)) == expected, 'REPORT_SEAL_ARTIFACT_DRIFT')
    files = []
    for p in sorted(report_dir.rglob('*')):
        require(not p.is_symlink(), 'REPORT_SEAL_SYMLINK')
        if p.is_file() and p.name != '.DS_Store' and not p.name.startswith('._'):
            files.append({'path': p.relative_to(report_dir).as_posix(), 'sha256': sha(p), 'size': p.stat().st_size})
    document = {'schema': 'general-e2e-canonical-report-seal/v1', 'source_report_dir': str(report_dir),
                'source_report_data_sha256': sha(report_dir / 'general_e2e_report_data.json'), 'files': files}
    output_dir.mkdir(parents=True, exist_ok=True)
    name = report_dir.name + '__standard-report'
    archive, sidecar = output_dir / (name + '.zip'), output_dir / (name + '__seal.json')
    require(not archive.exists() and not sidecar.exists(), 'REPORT_SEAL_EXISTS')
    temporary = output_dir / ('.' + name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with zipfile.ZipFile(temporary, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            def put(relative, data):
                info = zipfile.ZipInfo(name + '/' + relative, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, data)
            for ref in files:
                data = child(report_dir, ref['path']).read_bytes()
                require(len(data) == ref['size'] and hashlib.sha256(data).hexdigest() == ref['sha256'], 'REPORT_SEAL_SOURCE_CHANGED')
                put(ref['path'], data)
            put('REPORT_SEAL.json', json.dumps(document, ensure_ascii=False, indent=2) + '\n')
        os.rename(temporary, archive)
    finally:
        temporary.unlink(missing_ok=True)
    result = {**document, 'status': 'PASS', 'archive': str(archive), 'archive_sha256': sha(archive)}
    with sidecar.open('x', encoding='utf-8') as f: json.dump(result, f, ensure_ascii=False, indent=2); f.write('\n')
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--batch-root', type=Path)
    args = parser.parse_args()
    print(json.dumps(seal_report(args.report_dir, args.output_dir, batch_root=args.batch_root), ensure_ascii=False))

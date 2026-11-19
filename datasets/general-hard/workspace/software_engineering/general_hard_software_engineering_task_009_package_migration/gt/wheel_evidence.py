"""Verify delivered wheel/source agreement, not another execution or contract gate.
The existing business/boundary tests own wrong API behavior/console declarations.
"""
from pathlib import Path,PurePosixPath
import base64,csv,hashlib,io,re,zipfile,configparser,tomllib
from email.parser import Parser

def verify(path,root,source):
    errors=[];details={}
    def mismatch(message):errors.append(message)
    try:
        package=tomllib.loads((root/'project/pyproject.toml').read_text()).get('project',{})
        expected_code={rel[len('project/src/'):]:digest for rel,digest in source.items() if rel.startswith('project/src/') and rel.endswith('.py')}
        expected_resources={p.relative_to(root/'project/src').as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'project/src/batchstamp/resources').rglob('*') if p.is_file() and not p.is_symlink()}
        with zipfile.ZipFile(path) as archive:
            infos=archive.infolist();names=[x.filename for x in infos if not x.is_dir()]
            if len(names)!=len(set(names)):mismatch('duplicate archive file identities')
            if any(PurePosixPath(n).is_absolute() or '..' in PurePosixPath(n).parts or '\\' in n for n in names):mismatch('unsafe member identity')
            code={n for n in names if n.endswith('.py') and (n.startswith('batchstamp/') or n=='legacy_stamp.py')}
            if not expected_code or code!=set(expected_code):mismatch('module inventory differs from complete current src')
            for name,digest in expected_code.items():
                if name not in names or hashlib.sha256(archive.read(name)).hexdigest()!=digest:mismatch('module path/bytes mismatch: '+name)
            for name,digest in expected_resources.items():
                if name not in names or hashlib.sha256(archive.read(name)).hexdigest()!=digest:mismatch('resource path/bytes mismatch: '+name)
            dist={n.split('/')[0] for n in names if n.split('/')[0].endswith('.dist-info')}
            if len(dist)!=1:mismatch('one distribution metadata tree required')
            else:
                directory=next(iter(dist));mandatory={directory+'/'+n for n in ['METADATA','WHEEL','RECORD']}
                if not mandatory<=set(names):mismatch('incomplete installable wheel metadata')
                if directory+'/METADATA' in names:
                    metadata=Parser().parsestr(archive.read(directory+'/METADATA').decode('utf-8'))
                    normalize=lambda s:re.sub(r'[-_.]+','-',str(s).lower())
                    if package.get('name') is not None and normalize(metadata.get('Name'))!=normalize(package['name']):mismatch('distribution name disagrees with current source')
                    if package.get('version') is not None and metadata.get('Version')!=str(package['version']):mismatch('distribution version disagrees with current source')
                scripts=package.get('scripts',{});actual={}
                if directory+'/entry_points.txt' in names:
                    parser=configparser.ConfigParser(interpolation=None);parser.optionxform=str;parser.read_string(archive.read(directory+'/entry_points.txt').decode('utf8'))
                    if parser.has_section('console_scripts'):actual=dict(parser.items('console_scripts'))
                if actual!={str(k):str(v) for k,v in scripts.items()}:mismatch('entrypoint declarations disagree with current source')
                if directory+'/RECORD' in names:
                    rows=list(csv.reader(io.StringIO(archive.read(directory+'/RECORD').decode('utf8'))));record={r[0]:r for r in rows if len(r)==3}
                    if len(record)!=len(rows) or set(record)!=set(names):mismatch('RECORD does not cover archive members exactly')
                    for name,row in record.items():
                        if name==directory+'/RECORD':continue
                        algorithm,sep,encoded=row[1].partition('=')
                        if not sep or algorithm in {'md5','sha1'}:mismatch('invalid RECORD digest: '+name);continue
                        try:
                            data=archive.read(name);digest=base64.urlsafe_b64encode(hashlib.new(algorithm,data).digest()).rstrip(b'=').decode('ascii')
                            if digest!=encoded or str(len(data))!=row[2]:mismatch('RECORD digest/size mismatch: '+name)
                        except (ValueError,KeyError):mismatch('unsupported/corrupt RECORD entry: '+name)
            details={'expected_code':expected_code,'expected_resources':expected_resources,'archive_code_members':sorted(code),'archive_file_count':len(names),'distribution_trees':sorted(dist)}
    except (OSError,ValueError,KeyError,UnicodeError,zipfile.BadZipFile,configparser.Error) as error:mismatch(type(error).__name__+': '+str(error))
    return {'valid_source_agreement':not errors,'errors':errors,'details':details,'scope':'Exact delivered payload agreement with current source and RECORD integrity only. Actual fresh-build install/API/entrypoint behavior retains separate ownership.'}

"""Configure and run an isolated native Writer API evidence probe on macOS.

It reports mechanical observations; it never decides semantic criteria.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import socket
import stat
import subprocess
import sys
import time
import zipfile

SCHEMA = 'wildclawbench.general-e2e-native-writer-runtime/v1'
JAR_SHA256 = '37b94f944cb35fdbdb586d08df65419b42f1bd2363e143958dbae63ca15c23b3'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as output:
        output.write(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def environment(python):
    result = {'PATH': str(Path(python).parent), 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
              'PYTHONUTF8': '1', 'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
    if os.environ.get('TMPDIR'):
        result['TMPDIR'] = os.environ['TMPDIR']
    return result


def identity(pid):
    result = subprocess.run(['/bin/ps', '-ww', '-p', str(pid), '-o', 'pid=,lstart=,command='],
                            capture_output=True, text=True, encoding='utf-8')
    parts = result.stdout.strip().split(None, 6)
    if len(parts)!=7:
        return None
    return {'pid': int(parts[0]), 'started_at': ' '.join(parts[1:6]),
            'command_sha256': hashlib.sha256(parts[6].encode('utf-8')).hexdigest(),
            'command': parts[6]}


def stop_bound(expected, actions):
    if expected is None:
        return
    for kind, duration in [(signal.SIGTERM, 2.0), (signal.SIGKILL, 2.0)]:
        if identity(expected['pid']) != expected:
            return
        os.kill(expected['pid'], kind)
        actions.append({'pid': expected['pid'], 'signal': kind.name})
        deadline = time.monotonic()+duration
        while time.monotonic()<deadline:
            if identity(expected['pid']) != expected:
                return
            time.sleep(0.05)


def properties(path):
    def unescape(value):
        def replace(match):
            token = match.group(1)
            if token.startswith('u') and len(token)==5:
                return chr(int(token[1:],16))
            return {'t':'\t','n':'\n','r':'\r','f':'\f'}.get(token, token)
        return re.sub(r'\\(u[0-9a-fA-F]{4}|.)', replace, value)
    result = {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if not line or line.startswith(('#','!')):
            continue
        key, separator, value = line.partition('=')
        if not separator:
            raise ValueError('NATIVE_WRITER_RECEIPT_INVALID')
        result[unescape(key)] = unescape(value)
    return result


def validate_configuration(config):
    if config.get('schema_version')!=SCHEMA or sys.platform!='darwin':
        raise ValueError('NATIVE_WRITER_CONFIGURATION_UNSUPPORTED')
    if sha(__file__)!=config['runner']['sha256']:
        raise ValueError('NATIVE_WRITER_CALLER_IMPLEMENTATION_DRIFT')
    for name in ['python','java','jar','office_launcher','office_binary','runner','java_source']:
        item = config[name]
        if sha(item['path']) != item['sha256']:
            raise ValueError('NATIVE_WRITER_ASSET_DRIFT: '+name)
        if name in {'python','java','office_launcher','office_binary'} and not os.access(item['path'],os.X_OK):
            raise ValueError('NATIVE_WRITER_EXECUTABLE_UNAVAILABLE: '+name)
    for item in config['classes']:
        if sha(Path(config['class_root'])/item['path']) != item['sha256']:
            raise ValueError('NATIVE_WRITER_CLASS_DRIFT')


def run_probe(*, config_path, source, control, output_root, timeout_seconds=180):
    config_path = Path(config_path).absolute()
    config = json.loads(config_path.read_text(encoding='utf-8'))
    validate_configuration(config)
    if timeout_seconds<=0:
        raise ValueError('NATIVE_WRITER_TIMEOUT_INVALID')
    source = Path(source).resolve(strict=True)
    control = Path(control).resolve(strict=True)
    output = Path(output_root).absolute()
    if output.exists():
        raise ValueError('NATIVE_WRITER_OUTPUT_EXISTS')
    output.mkdir(parents=True)
    inputs = [{'role': role, 'path': str(path), 'sha256': sha(path)}
              for role,path in [('candidate',source),('known_good_control',control)]]
    copy = output/'editable-copy.docx'
    shutil.copyfile(source,copy)
    # Data-only copy is deliberately writable. The source is never unprotected.
    if copy.stat().st_flags & stat.UF_IMMUTABLE:
        raise ValueError('NATIVE_WRITER_COPY_IMMUTABLE')
    saved = output/'native-saved.docx'
    pdf = output/'candidate-native.pdf'
    receipt = output/'native-receipt.properties'
    profile = output/'native-profile'
    pid_file = output/'native-server.pid'
    with socket.socket() as port_request:
        port_request.bind(('127.0.0.1',0));port = port_request.getsockname()[1]
    server_argv = [config['office_launcher']['path'], '-env:UserInstallation='+profile.as_uri(),
                   '--headless','--nologo','--norestore','--nodefault','--pidfile='+str(pid_file),
                   '--accept=socket,host=127.0.0.1,port='+str(port)+';urp;StarOffice.ComponentContext']
    java_argv = [config['java']['path'],'-cp',config['jar']['path']+os.pathsep+config['class_root'],
                 'NativeDocxEditProbe', 'uno:socket,host=127.0.0.1,port='+str(port)+';urp;StarOffice.ComponentContext',
                 control.as_uri(),source.as_uri(),copy.as_uri(),saved.as_uri(),pdf.as_uri(),str(receipt)]
    env = environment(config['python']['path'])
    actions=[];server_identity=None;java_identity=None;native_identity=None;client=None;startup_error=None
    def capture_native_identity():
        nonlocal native_identity
        if native_identity is None and pid_file.is_file():
            text=pid_file.read_text(encoding='ascii').strip()
            observed=identity(int(text)) if text.isdigit() else None
            if observed and '-env:UserInstallation='+profile.as_uri() in observed['command']:
                native_identity=observed
    started = datetime.now(timezone.utc).isoformat()
    timed_out = False
    # Keep every child in the managed Worker's process group. Its supervisor
    # can still stop all descendants if this helper itself is interrupted.
    with (output/'server.stdout').open('xb') as so, (output/'server.stderr').open('xb') as se, \
         (output/'java.stdout').open('xb') as jo, (output/'java.stderr').open('xb') as je:
        server = subprocess.Popen(server_argv,env=env,stdout=so,stderr=se)
        server_identity = identity(server.pid)
        try:
            client = subprocess.Popen(java_argv,env=env,stdout=jo,stderr=je)
            java_identity = identity(client.pid)
            deadline = time.monotonic()+timeout_seconds
            while client.poll() is None and time.monotonic()<deadline:
                capture_native_identity()
                time.sleep(0.1)
            if client.poll() is None:
                timed_out = True
                stop_bound(java_identity,actions)
            client.wait(timeout=5)
            try:server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                capture_native_identity()
                stop_bound(native_identity,actions)
                try:server.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    stop_bound(server_identity,actions);server.wait(timeout=3)
        except (OSError,subprocess.SubprocessError) as error:
            startup_error=str(error)
        finally:
            if client is not None and client.poll() is None:stop_bound(java_identity,actions)
            capture_native_identity()
            if native_identity and identity(native_identity['pid'])==native_identity:
                stop_bound(native_identity,actions)
            if server.poll() is None:
                stop_bound(native_identity,actions);stop_bound(server_identity,actions)
    residual = [item for item in [java_identity,native_identity,server_identity]
                if item and identity(item['pid'])==item]
    server.poll()
    if client is not None:client.poll()
    try:
        facts = properties(receipt) if receipt.is_file() else {'status':'evaluator_error','reason':'native receipt missing'}
    except (ValueError,UnicodeError):
        facts={'status':'evaluator_error','reason':'native receipt invalid'}
    unchanged = all(sha(item['path'])==item['sha256'] for item in inputs)
    status = facts.get('status')
    if timed_out or startup_error or residual or not unchanged or server.returncode!=0 or client is None or client.returncode not in (0,) or status not in {'pass','candidate_not_editable','candidate_not_openable'}:
        status = 'evaluator_error'
    profile_archive = None
    if status!='evaluator_error' and profile.is_dir():
        # Preserve the exact ordinary files and symlink targets from our own
        # stopped profile as opaque runtime evidence. Do not follow links.
        profile_archive=output/'native-profile.zip'
        with zipfile.ZipFile(profile_archive,'x',compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(profile.rglob('*')):
                relative=path.relative_to(profile).as_posix()
                kind=path.lstat()
                if path.is_symlink():
                    item=zipfile.ZipInfo(relative);item.create_system=3;item.external_attr=(stat.S_IFLNK|0o777)<<16
                    archive.writestr(item,os.readlink(path).encode('utf-8'))
                elif path.is_file():archive.write(path,relative)
                elif path.is_dir():archive.write(path,relative+'/')
                else:raise ValueError('NATIVE_WRITER_PROFILE_SPECIAL_FILE: '+relative)
        shutil.rmtree(profile)
    for owned in [copy,saved]:
        if owned.is_file():os.chflags(owned,owned.stat().st_flags | stat.UF_IMMUTABLE)
    artifacts = [{'path': str(path.relative_to(output)), 'sha256': sha(path), 'size': path.stat().st_size}
                 for path in output.iterdir() if path.is_file()]
    result = {'schema_version':'wildclawbench.general-e2e-native-writer-evidence/v1',
              'status':status,'started_at':started,'finished_at':datetime.now(timezone.utc).isoformat(),
              'configuration_sha256':sha(config_path),'inputs':inputs,'input_bytes_unchanged':unchanged,
              'native_facts':facts,'timed_out':timed_out,'server_exit_code':server.returncode,
              'java_exit_code':client.returncode if client is not None else None,'startup_error':startup_error,
              'server_argv':server_argv,'java_argv':java_argv,
              'environment_keys':sorted(env),'process_identities':[item for item in [server_identity,java_identity,native_identity] if item],
              'cleanup_actions':actions,'cleanup_residual':residual,'artifacts':artifacts,
              'native_profile_archive':profile_archive.name if profile_archive else None,
              'candidate_rewritten':False,'grader_evidence_not_agent_action':True}
    write_new(output/'probe-result.json',result)
    return result


def configure(*, runtime_python, jdk_home, uno_jar, office_configuration, support_root=None):
    if sys.platform!='darwin':
        raise ValueError('NATIVE_WRITER_CONFIGURATION_PLATFORM_UNSUPPORTED')
    python = Path(runtime_python).absolute()
    runtime = python.parent.parent
    support = Path(support_root).absolute() if support_root else runtime/'native-writer-v1'
    marker = runtime/'general-e2e-native-writer.json'
    launcher = python.parent/'general-e2e-native-writer'
    if any(os.path.lexists(path) for path in [support,marker,launcher]):
        raise ValueError('NATIVE_WRITER_DESTINATION_EXISTS')
    jdk = Path(jdk_home).resolve(strict=True)
    java = jdk/'bin/java';javac = jdk/'bin/javac'
    jar = Path(uno_jar).resolve(strict=True)
    if sha(jar)!=JAR_SHA256 or not java.is_file() or not javac.is_file():
        raise ValueError('NATIVE_WRITER_DEPENDENCY_MISMATCH')
    office = json.loads(Path(office_configuration).read_text(encoding='utf-8'))
    office_launcher = python.parent/'soffice'
    if sha(office_launcher)!=office['bin_launcher_sha256'] or sha(office['binary']['path'])!=office['binary']['sha256']:
        raise ValueError('NATIVE_WRITER_OFFICE_CONFIGURATION_MISMATCH')
    support.mkdir(parents=True)
    shutil.copyfile(jar,support/'libreoffice-26.2.2.jar')
    java_source = Path(__file__).parent/'native_writer/NativeDocxEditProbe.java'
    shutil.copyfile(java_source,support/'NativeDocxEditProbe.java')
    runner = support/'runner.py';shutil.copyfile(__file__,runner)
    classes = support/'classes'
    compile_argv = [str(javac),'--release','17','-cp',str(support/'libreoffice-26.2.2.jar'),
                    '-d',str(classes),str(support/'NativeDocxEditProbe.java')]
    compiled = subprocess.run(compile_argv,capture_output=True,env=environment(python),timeout=60)
    (support/'compiler.stdout').write_bytes(compiled.stdout);(support/'compiler.stderr').write_bytes(compiled.stderr)
    if compiled.returncode:
        raise ValueError('NATIVE_WRITER_COMPILATION_FAILED')
    version = subprocess.run([str(java),'-version'],capture_output=True,env=environment(python),timeout=10)
    def asset(path):return {'path':str(path),'sha256':sha(path)}
    config = {'schema_version':SCHEMA,'created_at':datetime.now(timezone.utc).isoformat(),
              'python':asset(python),'java':{**asset(java),'version':(version.stdout+version.stderr).decode('utf-8')},
              'jar':asset(support/'libreoffice-26.2.2.jar'),'java_source':asset(support/'NativeDocxEditProbe.java'),
              'runner':asset(runner),'office_launcher':asset(office_launcher),'office_binary':office['binary'],
              'office_version':office['version'],'class_root':str(classes),
              'classes':[{'path':str(path.relative_to(classes)),'sha256':sha(path)} for path in sorted(classes.glob('*.class'))]}
    config_path = support/'configuration.json';write_new(config_path,config)
    from docx import Document
    synthetic = support/'synthetic-control.docx'
    document = Document();document.add_heading('Synthetic native editability control',0)
    for text in ['Editable body','Second paragraph','Third paragraph']:document.add_paragraph(text)
    for index in range(2):
        table = document.add_table(rows=3,cols=2);table.cell(1,0).text='XQ-00'+str(index+1)
        document.add_paragraph('Table section '+str(index+1))
    document.save(synthetic)
    os.chflags(synthetic,synthetic.stat().st_flags | stat.UF_IMMUTABLE)
    smoke = run_probe(config_path=config_path,source=synthetic,control=synthetic,output_root=support/'validation',timeout_seconds=120)
    if smoke['status']!='pass':
        raise ValueError('NATIVE_WRITER_REAL_API_VALIDATION_FAILED')
    wrapper = '#!/bin/sh\nexec '+shlex.quote(str(python))+' -I '+shlex.quote(str(runner))+' run --config '+shlex.quote(str(config_path))+' "$@"\n'
    with launcher.open('x',encoding='utf-8') as output:output.write(wrapper)
    launcher.chmod(0o755)
    published = {'schema_version':SCHEMA,'status':'VALIDATED_REAL_NATIVE_EDIT_SAVE_REOPEN',
                 'configuration':asset(config_path),'launcher':asset(launcher),
                 'validation':asset(support/'validation/probe-result.json'),'global_java_configuration_changed':False}
    write_new(marker,published)
    return published


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command',required=True)
    setup = commands.add_parser('configure')
    for field in ['runtime-python','jdk-home','uno-jar','office-configuration']:
        setup.add_argument('--'+field,type=Path,required=True)
    setup.add_argument('--support-root',type=Path)
    run = commands.add_parser('run')
    for field in ['config','source','control','output-root']:
        run.add_argument('--'+field,type=Path,required=True)
    run.add_argument('--timeout-seconds',type=float,default=180)
    args = parser.parse_args()
    try:
        if args.command=='configure':
            result = configure(runtime_python=args.runtime_python,jdk_home=args.jdk_home,uno_jar=args.uno_jar,
                               office_configuration=args.office_configuration,support_root=args.support_root)
        else:
            result = run_probe(config_path=args.config,source=args.source,control=args.control,
                               output_root=args.output_root,timeout_seconds=args.timeout_seconds)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 2 if result.get('status')=='evaluator_error' else 0
    except (OSError,ValueError,subprocess.SubprocessError) as error:
        print(json.dumps({'status':'evaluator_error','error':str(error)},ensure_ascii=False))
        return 2


if __name__=='__main__':
    raise SystemExit(main())

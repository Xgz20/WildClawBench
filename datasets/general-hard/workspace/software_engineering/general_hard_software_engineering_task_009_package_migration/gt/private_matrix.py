from pathlib import Path
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
class TrustedRuntimeError(RuntimeError):pass
def find_interpreters():
    found=[]
    for version in ['3.11','3.12']:
        choice=shutil.which('python'+version)
        if not choice:
            choice=next((str(p) for p in [Path('/usr/local/bin')/('python'+version),Path('/opt/homebrew/bin')/('python'+version)] if p.is_file()),None)
        if not choice:raise TrustedRuntimeError('H049_RUNTIME_REQUIRED: Python '+version)
        found.append({'version':version,'path':choice})
    return found
def collect(root,cases,data,interpreters,output):
    root=Path(root);output=Path(output);output.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((root/'offline_wheels/manifest.json').read_text())
    for item in manifest['files']:
        path=root/'offline_wheels'/item['name']
        if not path.is_file() or sha(path)!=item['sha256']:raise TrustedRuntimeError('H049_OFFLINE_WHEEL_REQUIRED: '+item['name'])
    library=output/'bootstraplib';library.mkdir()
    with zipfile.ZipFile(root/'offline_wheels/setuptools-79.0.1-py3-none-any.whl') as z:z.extractall(library)
    pip_wheel=root/'offline_wheels/pip-24.0-py3-none-any.whl';driver=root/'tools/offline_driver.py';probe=root/'tools/installed_probe.py';api_probe=Path(__file__).with_name('private_probe.py')
    env={**os.environ,'PIP_CONFIG_FILE':os.devnull,'PIP_NO_INDEX':'1','PIP_DISABLE_PIP_VERSION_CHECK':'1','PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1'}
    commands=[]
    def command(argv,cwd,extra_env=None):
        try:p=subprocess.run([str(x) for x in argv],cwd=cwd,text=True,capture_output=True,check=False,timeout=35,env={**env,**(extra_env or {})})
        except subprocess.TimeoutExpired as error:return {'argv':[str(x) for x in argv],'cwd':str(cwd),'returncode':None,'candidate_timeout':True,'stdout':error.stdout.decode() if isinstance(error.stdout,bytes) else error.stdout or '', 'stderr':error.stderr.decode() if isinstance(error.stderr,bytes) else error.stderr or ''}
        result={'argv':[str(x) for x in argv],'cwd':str(cwd),'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr};commands.append(result);return result
    def parsed(result):
        try:return json.loads(result['stdout']) if result['returncode']==0 else None
        except ValueError:return None
    versions=[]
    for runtime in interpreters:
        python=Path(runtime['path'])
        if not python.is_file() or not os.access(python,os.X_OK):raise TrustedRuntimeError('H049_RUNTIME_REQUIRED: '+str(python))
        info=command([python,'-I','-B','-c','import sys,json;print(json.dumps({"version":sys.version,"major":sys.version_info.major,"minor":sys.version_info.minor,"executable":sys.executable}))'],output)
        observed=parsed(info)
        if not observed or f"{observed['major']}.{observed['minor']}"!=runtime['version']:raise TrustedRuntimeError('H049_RUNTIME_VERSION_MISMATCH')
        if runtime.get('executable_sha256') and sha(python)!=runtime['executable_sha256']:raise TrustedRuntimeError('H049_RUNTIME_SHA_MISMATCH')
        work=output/('构建 '+runtime['version']);work.mkdir();project=work/'project';shutil.copytree(root/'project',project,ignore=shutil.ignore_patterns('build','*.egg-info','__pycache__','*.pyc'))
        foreign=work/'非ASCII cwd';foreign.mkdir();target=work/'安装 target';wheel_dir=work/'wheel';wheel_dir.mkdir()
        data_path=foreign/'输入 数据.json';data_path.write_text(json.dumps(data,ensure_ascii=False))
        configs={};datasets={}
        for item in cases:
            p=foreign/(item['id']+'.json');p.write_text(json.dumps(item['config'],ensure_ascii=False));configs[item['id']]=p
            d=foreign/(item['id']+'-records.json');d.write_text(json.dumps(item.get('records',data),ensure_ascii=False));datasets[item['id']]=d
        tests=command([python,'-B','-m','unittest','discover','-s',str(root/'tests_public'),'-v'],project)
        checkout=command([python,'-I','-B',project/'legacy_cli.py','--source',data_path,'--settings',configs[cases[0]['id']]],foreign)
        built=command([python,'-I','-B',driver,'build',library,project,wheel_dir],foreign)
        wheels=list(wheel_dir.glob('*.whl'));wheel=wheels[0] if built['returncode']==0 and len(wheels)==1 else None
        retired=work/'source-retired';project.rename(retired)
        installed=command([python,'-I','-B',driver,'install',pip_wheel,target,wheel],foreign) if wheel else None
        ok=installed is not None and installed['returncode']==0
        origin=command([python,'-I','-B',probe,target,'origin'],foreign) if ok else None
        resources=command([python,'-I','-B',probe,target,'resources'],foreign) if ok else None
        zipped=command([python,'-I','-B',probe,wheel,'resources'],foreign) if wheel else None
        source_match=False;resources_match=False
        if wheel:
            with zipfile.ZipFile(wheel) as z:
                names=set(z.namelist())
                pyfiles={'batchstamp/'+n:retired/'src/batchstamp'/n for n in ['__init__.py','__main__.py','cli.py','core.py']};pyfiles['legacy_stamp.py']=retired/'src/legacy_stamp.py'
                source_match=all(member in names and source.is_file() and hashlib.sha256(z.read(member)).hexdigest()==sha(source) for member,source in pyfiles.items())
                resources_match=all('batchstamp/resources/'+n in names and hashlib.sha256(z.read('batchstamp/resources/'+n)).hexdigest()==sha(retired/'src/batchstamp/resources'/n) for n in ['defaults.json','banner.txt'])
        api=[]
        for item in cases:
            for module in ['batchstamp.core','legacy_stamp']:
                call=command([python,'-I','-B',api_probe,target,module,datasets[item['id']],configs[item['id']]],foreign) if ok else None
                observed_api=parsed(call) if call else None
                api.append({'id':item['id'],'module':module,'command':call,
                            'result':observed_api.get('result') if isinstance(observed_api,dict) else None,
                            'input_observation':observed_api.get('input_observation') if isinstance(observed_api,dict) else None})
        entries=[]
        for item in cases[:2]+[c for c in cases if c.get('entry')]:
            for kind,name in [('console-new','batchstamp'),('console-old','stamp-old'),('module-new','batchstamp'),('module-old','legacy_stamp')]:
                flags=['--source',str(datasets[item['id']]),'--settings',str(configs[item['id']])] if kind.endswith('old') else ['--input',str(datasets[item['id']]),'--config',str(configs[item['id']])]
                if ok and kind.startswith('console'):
                    script=target/('Scripts' if os.name=='nt' else 'bin')/(name+'.exe' if os.name=='nt' else name)
                    call=command([script,*flags],foreign,{'PYTHONPATH':str(target)}) if script.is_file() else {'argv':[str(script),*flags],'cwd':str(foreign),'returncode':None,'stdout':'','stderr':'candidate console missing'}
                elif ok:call=command([python,'-I','-B',probe,target,'module',name,*flags],foreign)
                else:call=None
                entries.append({'id':item['id'],'kind':kind,'command':call,'result':parsed(call) if call else None})
        invalid=[]
        for index,config in enumerate([{'scale':True},{'include_null_region':0},{'min_amount':'bad'}]):
            bad_config=foreign/f'invalid-config-{index}.json';bad_config.write_text(json.dumps(config))
            call=command([python,'-I','-B',probe,target,'module','batchstamp','--input',data_path,'--config',bad_config],foreign) if ok else None
            invalid.append({'kind':'config','index':index,'command':call})
        bad_records=foreign/'invalid-records.json';bad_records.write_text('[{"id":"x","amount":true,"region":"cn"}]\n')
        call=command([python,'-I','-B',probe,target,'module','batchstamp','--input',bad_records,'--config',configs[cases[0]['id']]],foreign) if ok else None
        invalid.append({'kind':'records','index':0,'command':call})
        versions.append({'version':runtime['version'],'observed':observed,'python_sha256':sha(python),'work':str(work),'source_retired':str(retired),'foreign_cwd':str(foreign),'target':str(target),
                         'public_tests':tests,'checkout_legacy':checkout,'build':built,'wheel':str(wheel) if wheel else None,'wheel_sha256':sha(wheel) if wheel else None,
                         'install':installed,'origin':origin,'origin_result':parsed(origin) if origin else None,'resources':resources,'resources_result':parsed(resources) if resources else None,
                         'zip_resources':zipped,'zip_resources_result':parsed(zipped) if zipped else None,'src_members_match':source_match,'resource_members_match':resources_match,
                         'api':api,'entries':entries,'invalid_inputs':invalid})
    return {'schema':'h049-actual-install-matrix/v1','versions':versions,'commands':commands,'network_or_external_install':False,'only_candidate_wheel_installed_into_owned_target':True}

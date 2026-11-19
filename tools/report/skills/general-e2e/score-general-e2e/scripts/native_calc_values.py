"""Observe bulk native Calc scalar results in an isolated read-only disposable copy."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib,json,os,math
from pathlib import Path
import re,shutil,socket,stat,subprocess,sys,time
import zipfile
import xml.etree.ElementTree as ET
import native_writer_runtime as native

PROFILE='readonly-native-calc-bulk-values/v2'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write_new(p,value):
    with Path(p).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')
def assets(configuration):
    c=json.loads(Path(configuration).read_text(encoding='utf-8'));native.validate_configuration(c)
    javac=Path(c['java']['path']).with_name('javac')
    if not javac.is_file() or not os.access(javac,os.X_OK):raise ValueError('NATIVE_CALC_JAVAC_UNAVAILABLE')
    source=Path(__file__).with_name('native_calc')/'NativeCalcValues.java'
    return c,{'helper_sha256':sha(__file__),'java_source_sha256':sha(source),
              'writer_configuration_sha256':sha(configuration),'javac_sha256':sha(javac)}

def check_local_workbook(source):
    with zipfile.ZipFile(source) as archive:
        infos=archive.infolist()
        if (len(infos)>10000 or len(infos)!=len(set(i.filename for i in infos))
                or sum(i.file_size for i in infos)>128*1024*1024 or any(i.file_size>96*1024*1024 for i in infos)):raise ValueError('NATIVE_CALC_INPUT_LIMIT')
        for item in infos:
            name=item.filename.lower()
            if any(token in name for token in ['vbaproject','externallinks/','connections.xml','oleobjects/']):
                raise ValueError('NATIVE_CALC_EXTERNAL_CONTENT_UNSUPPORTED')
            if name.endswith('.rels'):
                tree=ET.fromstring(archive.read(item))
                if any(node.attrib.get('TargetMode')=='External' for node in tree):
                    raise ValueError('NATIVE_CALC_EXTERNAL_RELATIONSHIP_UNSUPPORTED')
            if name.startswith('xl/worksheets/') and name.endswith('.xml'):
                for node in ET.fromstring(archive.read(item)).iter():
                    if node.tag.rsplit('}',1)[-1]=='f' and re.search(
                            r'WEBSERVICE|DDE|RTD\s*\(|IMAGE\s*\(|STOCKHISTORY|https?:|file:|\[',node.text or '',re.I):
                        raise ValueError('NATIVE_CALC_EXTERNAL_FORMULA_UNSUPPORTED')

def run_probe(configuration,source,locations,output_root,timeout=900):
    c,locked=assets(configuration);source=Path(source).resolve(strict=True);out=Path(output_root).absolute()
    if out.exists() or not 0<len(locations)<=100000 or len(set(locations))!=len(locations):raise ValueError('NATIVE_CALC_REQUEST_INVALID')
    if any(not re.fullmatch(r'[^\r\n\t]{1,31}![A-Z]{1,3}[1-9]\d{0,6}',p) for p in locations):raise ValueError('NATIVE_CALC_CELL_INVALID')
    locations_set=set(locations)
    check_local_workbook(source)
    out.mkdir(parents=True);before=sha(source);copy=out/'readonly-copy.xlsx';shutil.copyfile(source,copy)
    if sys.platform=='darwin':os.chflags(copy,copy.stat().st_flags|stat.UF_IMMUTABLE)
    classes=out/'classes';classes.mkdir();java_source=Path(__file__).with_name('native_calc')/'NativeCalcValues.java'
    javac=Path(c['java']['path']).with_name('javac');env=native.environment(c['python']['path'])
    compile_argv=[str(javac),'-encoding','UTF-8','-cp',c['jar']['path'],'-d',str(classes),str(java_source)]
    compiled=subprocess.run(compile_argv,env=env,capture_output=True,timeout=30)
    (out/'compile.stdout').write_bytes(compiled.stdout);(out/'compile.stderr').write_bytes(compiled.stderr)
    if compiled.returncode or sha(javac)!=locked['javac_sha256']:
        if sys.platform=='darwin':os.chflags(copy,copy.stat().st_flags & ~stat.UF_IMMUTABLE)
        raise ValueError('NATIVE_CALC_COMPILE_FAILED')
    with socket.socket() as request:request.bind(('127.0.0.1',0));port=request.getsockname()[1]
    profile=out/'native-profile';pid_file=out/'native.pid';receipt=out/'native.properties'
    server_argv=[c['office_launcher']['path'],'-env:UserInstallation='+profile.as_uri(),'--headless','--nologo',
                 '--norestore','--nodefault','--pidfile='+str(pid_file),
                 '--accept=socket,host=127.0.0.1,port='+str(port)+';urp;StarOffice.ComponentContext']
    request_file=out/'requested-locations.txt';request_file.write_text('\n'.join(locations)+'\n',encoding='utf-8')
    value_file=out/'native-values.jsonl'
    java_argv=[c['java']['path'],'-cp',c['jar']['path']+os.pathsep+str(classes),'NativeCalcValues',
               'uno:socket,host=127.0.0.1,port='+str(port)+';urp;StarOffice.ComponentContext',
               copy.as_uri(),str(receipt),str(request_file),str(value_file)]
    actions=[];owned=None;client=None;java_identity=None;timed_out=False
    def capture():
        nonlocal owned
        if owned is None and pid_file.is_file():
            value=pid_file.read_text().strip();observed=native.identity(int(value)) if value.isdigit() else None
            if observed and '-env:UserInstallation='+profile.as_uri() in observed['command']:owned=observed
    started=datetime.now(timezone.utc).isoformat()
    with (out/'server.stdout').open('xb') as so,(out/'server.stderr').open('xb') as se, \
         (out/'java.stdout').open('xb') as jo,(out/'java.stderr').open('xb') as je:
        server=subprocess.Popen(server_argv,env=env,stdout=so,stderr=se);server_identity=native.identity(server.pid)
        try:
            client=subprocess.Popen(java_argv,env=env,stdout=jo,stderr=je);java_identity=native.identity(client.pid)
            deadline=time.monotonic()+timeout
            while client.poll() is None and time.monotonic()<deadline:capture();time.sleep(.1)
            if client.poll() is None:timed_out=True;native.stop_bound(java_identity,actions)
            client.wait(timeout=5)
            try:server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                capture();native.stop_bound(owned,actions)
                try:server.wait(timeout=3)
                except subprocess.TimeoutExpired:native.stop_bound(server_identity,actions);server.wait(timeout=3)
        finally:
            capture()
            if client is not None and client.poll() is None:native.stop_bound(java_identity,actions)
            if owned and native.identity(owned['pid'])==owned:native.stop_bound(owned,actions)
            if server.poll() is None:native.stop_bound(server_identity,actions)
    residual=[p for p in [owned,server_identity,java_identity] if p and native.identity(p['pid'])==p]
    if not residual and sys.platform=='darwin':os.chflags(copy,copy.stat().st_flags & ~stat.UF_IMMUTABLE)
    facts=native.properties(receipt) if receipt.is_file() else {}
    if (timed_out or residual or client is None or client.returncode!=0 or facts.get('status')!='pass'
            or facts.get('read_only')!='true' or facts.get('saved')!='false'
            or facts.get('macro_execution')!='NEVER_EXECUTE' or facts.get('external_link_updates')!='NO_UPDATE'
            or facts.get('calculated_all')!='true' or facts.get('cell_count')!=str(len(locations)) or sha(source)!=before or sha(copy)!=before):
        raise ValueError('NATIVE_CALC_OBSERVATION_FAILED')
    if assets(configuration)[1]!=locked:raise ValueError('NATIVE_CALC_ASSET_DRIFT_DURING_OBSERVATION')
    if not value_file.is_file() or value_file.stat().st_size>64*1024*1024:
        raise ValueError('NATIVE_CALC_VALUE_OUTPUT_INVALID')
    seen=set();counts={'number':0,'string':0,'error':0};pages=[];batch=[];batch_bytes=2
    def publish():
        nonlocal batch,batch_bytes
        if not batch:return
        name=f'values-{len(pages)+1:04d}.json';path=out/name
        write_new(path,{'profile':PROFILE,'columns':['location','kind','value','error_code'],'rows':batch})
        pages.append({'path':name,'sha256':sha(path),'size':path.stat().st_size,'cell_count':len(batch)})
        batch=[];batch_bytes=2
    with value_file.open(encoding='utf-8') as stream:
        for line in stream:
            row=json.loads(line)
            if (not isinstance(row,list) or len(row)!=4 or row[0] not in locations_set
                    or row[0] in seen or row[1] not in counts or type(row[3]) is not int):
                raise ValueError('NATIVE_CALC_VALUE_SCOPE_INVALID')
            location,kind,value,error=row
            if (kind=='number' and (type(value) not in (int,float) or not math.isfinite(value) or error!=0)
                    or kind=='string' and (not isinstance(value,str) or error!=0)
                    or kind=='error' and (not isinstance(value,str) or error<=0)):
                raise ValueError('NATIVE_CALC_VALUE_TYPE_INVALID')
            seen.add(location);counts[kind]+=1
            length=len(json.dumps(row,ensure_ascii=False).encode('utf-8'))+2
            if batch and (len(batch)>=10000 or batch_bytes+length>2*1024*1024):publish()
            batch.append(row);batch_bytes+=length
    publish()
    if seen!=locations_set or sum(counts.values())!=len(locations):raise ValueError('NATIVE_CALC_VALUE_SCOPE_INCOMPLETE')
    if any(p.stat().st_size>1024*1024 for p in out.iterdir() if p.is_file() and p.suffix in {'.stdout','.stderr','.properties'}):
        raise ValueError('NATIVE_CALC_LOG_LIMIT')
    logs={p.name:{'text':p.read_text(encoding='utf-8',errors='replace'),'sha256':sha(p)}
          for p in out.iterdir() if p.is_file() and p.suffix in {'.stdout','.stderr','.properties'}}
    result={'status':'PASS','profile':PROFILE,'started_at':started,'finished_at':datetime.now(timezone.utc).isoformat(),
            'source_sha256':before,'source_unchanged':True,'disposable_copy_unchanged':True,'assets':locked,
            'engine':'LibreOffice Calc UNO','cell_count':len(locations),'cell_type_counts':counts,'pages':pages,
            'native_values_sha256':sha(value_file),'request_sha256':sha(request_file),'calculated_all':facts.get('calculated_all')=='true',
            'read_only':True,'saved':False,
            'macro_execution':'NEVER_EXECUTE','external_link_updates':'NO_UPDATE',
            'server_argv':server_argv,'java_argv':java_argv,'owned_processes':[p for p in [owned,server_identity,java_identity] if p],
            'cleanup_actions':actions,'residual_processes':False,'native_logs':logs,'numeric_score_assigned':False}
    write_new(out/'observation.json',result);return result

def self_test(configuration,output_root):
    import openpyxl
    out=Path(output_root).absolute();out.mkdir(parents=True,exist_ok=False)
    source=out/'synthetic.xlsx';w=openpyxl.Workbook();s=w.active;s.title='合成'
    for i in range(1,131):s.cell(i,1,'=1+1')
    s['B1']='=0';s['B2']='=IF(1=1,"",7)';s['B3']='=1/0';s['B4']='="中文"'
    w.save(source);w.close()
    if sys.platform=='darwin':os.chflags(source,source.stat().st_flags|stat.UF_IMMUTABLE)
    locations=['合成!A'+str(i) for i in range(1,131)]+['合成!B'+str(i) for i in range(1,5)]
    result=run_probe(configuration,source,locations,out/'probe')
    observed={row[0]:row for page in result['pages'] for row in json.loads((out/'probe'/page['path']).read_text(encoding='utf-8'))['rows']}
    if (len(observed)!=134 or observed['合成!A130'][1:]!=['number',2.0,0]
            or observed['合成!B1'][1:]!=['number',0.0,0]
            or observed['合成!B2'][1:]!=['string','',0]
            or observed['合成!B3'][1]!='error' or observed['合成!B3'][3]<=0
            or observed['合成!B4'][1:]!=['string','中文',0]):
        raise ValueError('NATIVE_CALC_BULK_SYNTHETIC_DISCRIMINATION_FAILED')
    marker={'status':'PASS','profile':PROFILE,'synthetic_only':True,'assets':result['assets'],
            'writer_configuration':str(Path(configuration).absolute()),'observation_sha256':sha(out/'probe/observation.json'),
            'more_than_64_cells_validated':True,'numeric_zero_text_empty_and_error_distinguished':True,
            'numeric_score_assigned':False}
    write_new(out/'validation.json',marker);return marker

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['observe','self-test'])
    p.add_argument('--writer-configuration',type=Path,required=True);p.add_argument('--source',type=Path)
    p.add_argument('--cell',action='append',default=[]);p.add_argument('--output-root',type=Path,required=True)
    a=p.parse_args()
    if a.command=='self-test':result=self_test(a.writer_configuration,a.output_root)
    else:
        if a.source is None:p.error('observe requires --source')
        result=run_probe(a.writer_configuration,a.source,a.cell,a.output_root)
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()

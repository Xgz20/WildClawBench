from __future__ import annotations
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import copy, hashlib, json, os, select, shutil, socket, socketserver, ssl, subprocess, sys, tempfile, threading, unittest, zipfile
from unittest.mock import patch
from urllib.parse import urlsplit
from tests.general_e2e.test_research_sources import ResearchSourceTests, SOURCES, RUNTIME, REPO_ROOT, POLICY
from tests.general_e2e.test_local_scoring_runtime import load_module
import research_sources_proxy as P
import research_source_dispatch as D

OBSERVATIONS=[]
CURL=Path('/usr/bin/curl')
REAL_RUN=subprocess.run
REAL_DNS=socket.getaddrinfo

class Origin(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        self.server.observed.append({'host':self.headers['Host'],'path':self.path})
        if self.path.startswith('/redirect-private'):
            self.send_response(302);self.send_header('Location','http://127.0.0.1/private');self.end_headers();return
        if self.path.startswith('/redirect'):
            self.send_response(302);self.send_header('Location','/publication?edition=kept');self.end_headers();return
        if self.path.startswith('/loop'):
            self.send_response(302);self.send_header('Location','/loop');self.end_headers();return
        data=b'<html><p>independent publication</p></html>'
        self.send_response(200);self.send_header('Content-Type','text/html');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)

class Tunnel(socketserver.BaseRequestHandler):
    def handle(self):
        raw=b''
        while b'\r\n\r\n' not in raw and len(raw)<16384:
            chunk=self.request.recv(4096)
            if not chunk:return
            raw+=chunk
        line=raw.split(b'\r\n',1)[0].decode('ascii');self.server.authorities.append(line)
        if self.server.mode=='407':self.request.sendall(b'HTTP/1.1 407 Proxy Authentication Required\r\nContent-Length: 0\r\n\r\n');return
        if self.server.mode=='403':self.request.sendall(b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n');return
        self.request.sendall(b'HTTP/1.1 200 Connection established\r\n\r\n')
        if self.server.mode=='close':return
        target=line.split()[1];port=int(target.rsplit(':',1)[1])
        upstream=socket.create_connection(('127.0.0.1',port),timeout=5)
        with upstream:
            for conn in (upstream,self.request):conn.settimeout(8)
            while True:
                ready,_,_=select.select([upstream,self.request],[],[],8)
                if not ready:return
                for conn in ready:
                    try:data=conn.recv(65536)
                    except OSError:return
                    if not data:return
                    try:(upstream if conn is self.request else self.request).sendall(data)
                    except OSError:return

class ProxyServer(socketserver.ThreadingTCPServer):
    allow_reuse_address=True;daemon_threads=True

class ProxyTransportTests(unittest.TestCase):
    fixture=ResearchSourceTests.fixture
    public_ledger=ResearchSourceTests.public_ledger
    public_fetch=ResearchSourceTests.public_fetch
    public_attempt=ResearchSourceTests.public_attempt
    @classmethod
    def setUpClass(cls):
        cls.cert_dir=Path(tempfile.mkdtemp(prefix='proxy-fixture-cert-'))
        def openssl(args):REAL_RUN(['openssl',*args],cwd=cls.cert_dir,capture_output=True,check=True)
        openssl(['req','-x509','-newkey','rsa:2048','-nodes','-keyout','ca.key','-out','ca.pem','-days','2','-subj','/CN=ProxyFixtureOnlyCA'])
        for name,host in [('good','publication.example'),('wrong','other.example')]:
            openssl(['req','-newkey','rsa:2048','-nodes','-keyout',name+'.key','-out',name+'.csr','-subj','/CN='+host])
            (cls.cert_dir/(name+'.ext')).write_text('subjectAltName=DNS:'+host+'\n')
            openssl(['x509','-req','-in',name+'.csr','-CA','ca.pem','-CAkey','ca.key','-CAcreateserial','-out',name+'.pem','-days','2','-extfile',name+'.ext'])
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.cert_dir)
    def setUp(self):
        self.root=Path(tempfile.mkdtemp(prefix='proxy-case-'));self.runtime_python=Path(sys.executable)
        self.servers=[];self.threads=[];self.argv=[];self.sni=[]
        self.http=self.server(ThreadingHTTPServer(('127.0.0.1',0),Origin));self.http.observed=[]
        self.https=self.tls_server('good');self.wrong=self.tls_server('wrong')
        self.proxy=self.server(ProxyServer(('127.0.0.1',0),Tunnel));self.proxy.authorities=[];self.proxy.mode='tunnel'
        self.endpoint=f'http://127.0.0.1:{self.proxy.server_address[1]}'
    def server(self,server):
        self.servers.append(server);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();self.threads.append(thread);return server
    def tls_server(self,name):
        srv=ThreadingHTTPServer(('127.0.0.1',0),Origin);srv.observed=[]
        ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(self.cert_dir/(name+'.pem'),self.cert_dir/(name+'.key'))
        ctx.set_servername_callback(lambda sock,name,context:self.sni.append(name));srv.socket=ctx.wrap_socket(srv.socket,server_side=True)
        return self.server(srv)
    def tearDown(self):
        OBSERVATIONS.append({'test':self.id(),'CONNECT_requests':self.proxy.authorities,'SNI':self.sni,'HTTPS_origin':self.https.observed,'HTTP_origin':self.http.observed,'argv':self.argv})
        for server in self.servers:server.shutdown();server.server_close()
        for thread in self.threads:thread.join(timeout=5)
        for p in self.root.rglob('*'):
            if not p.is_symlink():p.chmod(0o755 if p.is_dir() else 0o644)
        shutil.rmtree(self.root)
    def dns(self,host,port,*args,**kwargs):
        if host=='publication.example':return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',port))]
        return REAL_DNS(host,port,*args,**kwargs)
    @contextmanager
    def transport(self,*,ca=True):
        def run(argv,**kwargs):
            self.argv.append({'argv':list(argv),'proxy_env_present':any(k.lower().endswith('_proxy') for k in kwargs.get('env',{})),'ca_env_present':any(k in kwargs.get('env',{}) for k in ['CURL_CA_BUNDLE','SSL_CERT_FILE','SSL_CERT_DIR'])})
            actual=list(argv)
            if ca and '--url' in actual:actual[2:2]=['--cacert',str(self.cert_dir/'ca.pem')]
            return REAL_RUN(actual,**kwargs)
        with patch.object(socket,'getaddrinfo',side_effect=self.dns),patch.object(P.subprocess,'run',side_effect=run):yield
    def url(self,path='/publication?edition=kept',*,server=None,scheme='https'):
        server=server or self.https
        return f'{scheme}://publication.example:{server.server_port}{path}'
    def fetch(self,url=None,*,ca=True):
        with self.transport(ca=ca):return P.fetch(url or self.url(),self.root/'body.bin',{'timeout_seconds':8,'max_bytes_per_source':4096},CURL,trusted_http_connect_proxy=self.endpoint)
    def proxy_attempt(self,name='proxy',url=None):
        ledger={'sources':[{'source_id':'S1','url':url or self.url(),'access_status':'read_full','citations':[]}]}
        attempt=self.fixture(name,ledger=ledger).prepare()
        with self.transport():RUNTIME.collect_research_sources_attempt(attempt_root=attempt,curl=CURL,trusted_http_connect_proxy=self.endpoint)
        return attempt
    def test_actual_connect_ip_sni_host_and_proxy_peer_are_distinct(self):
        with patch.dict(os.environ,{'HTTPS_PROXY':'http://192.0.2.1:1','NO_PROXY':'*','CURL_CA_BUNDLE':'/wrong-ca'}):receipt=self.fetch()
        self.assertEqual(self.proxy.authorities,[f'CONNECT 8.8.8.8:{self.https.server_port} HTTP/1.1'])
        self.assertEqual(self.sni,['publication.example']);self.assertEqual(self.https.observed[0]['host'],f'publication.example:{self.https.server_port}')
        hop=receipt['responses'][0];self.assertEqual(hop['proxy_peer']['address'],'127.0.0.1');self.assertNotIn('connected_address',hop);self.assertFalse(receipt['origin_socket_observed'])
        self.assertEqual(len(receipt['responses']),1);self.assertEqual(receipt['http_status'],200)
        argv=self.argv[0]['argv'];self.assertEqual(argv[1],'-q');self.assertIn('--suppress-connect-headers',argv);self.assertEqual(argv[argv.index('--noproxy')+1],'');self.assertNotIn('-k',argv);self.assertNotIn('-L',argv)
        self.assertFalse(self.argv[0]['proxy_env_present']);self.assertFalse(self.argv[0]['ca_env_present'])
    def test_wrong_hostname_and_untrusted_ca_fail(self):
        for url,ca in [(self.url(server=self.wrong),True),(self.url(),False)]:
            with self.subTest(url=url,ca=ca),self.assertRaisesRegex(P.ResearchSourceError,'RESEARCH_SOURCE_ACQUISITION_FAILED'):self.fetch(url,ca=ca)
    def test_http_connect_is_honestly_without_origin_tls(self):
        r=self.fetch(self.url(server=self.http,scheme='http'));self.assertEqual(r['tls_verification'],'none-http');self.assertFalse(r['responses'][0]['origin_tls']['required'])
    def test_redirect_revalidates_and_preserves_query(self):
        r=self.fetch(self.url('/redirect?edition=kept'));self.assertEqual(r['redirect_count'],1);self.assertEqual(len(self.proxy.authorities),2);self.assertEqual(r['final_url'],self.url());P._validate_receipt(r,'test')
    def test_private_redirect_rejected_before_second_connect(self):
        with self.assertRaisesRegex(P.ResearchSourceError,'RESEARCH_SOURCE_URL_NOT_PUBLIC'):self.fetch(self.url('/redirect-private'))
        self.assertEqual(len(self.proxy.authorities),1)
    def test_redirect_cap_and_proxy_failure_are_not_origin_success(self):
        with self.assertRaisesRegex(P.ResearchSourceError,'redirect limit'):self.fetch(self.url('/loop'))
        self.assertEqual(len(self.proxy.authorities),11)
        for mode in ['403','407','close']:
            self.proxy.mode=mode
            with self.subTest(mode=mode),self.assertRaisesRegex(P.ResearchSourceError,'RESEARCH_SOURCE_ACQUISITION_FAILED'):self.fetch()
    def test_proxy_endpoint_and_nonpublic_dns_reject_before_curl(self):
        for value in ['http://localhost:7897','http://user@127.0.0.1:7897','http://127.0.0.1:7897/','https://127.0.0.1:7897','http://8.8.8.8:7897','http://127.0.0.1:0','http://127.0.0.1:7897?x=1','http://127.0.0.1:7897#x','http://127.0.0.1:7897\n']:
            with self.subTest(value=value),self.assertRaises(P.ResearchSourceError):P.proxy_endpoint(value)
        self.assertEqual(P.proxy_endpoint('http://[::1]:7897')['address'],'::1')
        for ip in ['127.0.0.1','10.0.0.1','169.254.1.1','224.0.0.1','0.0.0.0','192.0.2.1']:
            answers=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443)),(socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,443))]
            with self.subTest(ip=ip),patch.object(socket,'getaddrinfo',return_value=answers),patch.object(P.subprocess,'run',side_effect=AssertionError('no curl')),self.assertRaisesRegex(P.ResearchSourceError,'URL_NOT_PUBLIC'):P.fetch(self.url(),self.root/'x',{'timeout_seconds':8,'max_bytes_per_source':4096},CURL,trusted_http_connect_proxy=self.endpoint)
        for url in ['file:///tmp/a','https://u:p@publication.example/a','https://localhost/a','https://publication.example:0/a','https://publication.example/a\n']:
            with self.subTest(url=url),patch.object(P.subprocess,'run',side_effect=AssertionError('no curl')),self.assertRaises(P.ResearchSourceError):P.fetch(url,self.root/'x',{'timeout_seconds':8,'max_bytes_per_source':4096},CURL,trusted_http_connect_proxy=self.endpoint)
    def test_receipt_tampering_rejected_offline(self):
        receipt=self.fetch()
        mutations=[lambda r:r.update(public_address_policy='unknown'),lambda r:r.update(schema_version='unknown'),lambda r:r.update(origin_socket_observed=True),lambda r:r.update(connected_address='8.8.8.8'),lambda r:r['responses'][0].update(connected_address='127.0.0.1'),lambda r:r['responses'][0]['proxy_peer'].update(address='8.8.8.8'),lambda r:r['responses'][0]['proxy_peer'].update(port=1),lambda r:r['responses'][0]['connect_target'].update(address='1.1.1.1'),lambda r:r['responses'][0].update(validated_addresses=['127.0.0.1']),lambda r:r['responses'][0].update(connect_status=407),lambda r:r['responses'][0]['origin_tls'].update(verify_result=1),lambda r:r['responses'][0]['origin_tls'].update(verification_name='other.example'),lambda r:r['responses'][0].update(url='https://other.example/'),lambda r:r.update(redirect_count=1)]
        with patch.object(socket,'getaddrinfo',side_effect=AssertionError('offline validator')):
            for i,mutate in enumerate(mutations):
                r=copy.deepcopy(receipt);mutate(r)
                with self.subTest(mutation=i),self.assertRaises(P.ResearchSourceError):P._validate_receipt(r,'tampered')
    def test_fresh_seal_normal_archive_rescore_and_source_lock_tamper(self):
        attempt=self.proxy_attempt();self.assertIs(D.backend(attempt),P)
        with patch.object(socket,'getaddrinfo',side_effect=AssertionError('offline verify')),patch.object(P,'fetch',side_effect=AssertionError('offline verify must not GET')):
            RUNTIME.verify_attempt(attempt);P.verify(attempt,required=True,archived=True,attempt_verifier=RUNTIME.verify_attempt)
            RUNTIME.run_rules_attempt(attempt_root=attempt,runtime_python=self.runtime_python,timeout_seconds=15)
            RUNTIME.prepare_semantics_attempt(attempt_root=attempt);RUNTIME.finalize_score_attempt(attempt_root=attempt)
            clone=RUNTIME.prepare_rescore_attempt(source_attempt_root=attempt,output_root=self.root/'rescore',scoring_attempt_id='proxy-rescore')['attempt_root']
            self.assertIs(D.backend(Path(clone)),P)
        document=SOURCES.read(attempt/P.BUNDLE_PATH/'manifest.json');row=document['sources'][0];receipt_path=attempt/P.BUNDLE_PATH/row['receipt_path']
        receipt=SOURCES.read(receipt_path);receipt['responses'][0]['proxy_peer']['address']='8.8.8.8';receipt_path.chmod(0o644);receipt_path.write_bytes(SOURCES.encoded(receipt))
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'RESEARCH_SOURCE_BUNDLE_DRIFT'):RUNTIME.verify_attempt(attempt)
    def test_real_legacy_v1_verifier_reuse_retains_response_and_get_time(self):
        old=self.public_attempt('old',ledger=self.public_ledger(citations=[]));old_doc=SOURCES.read(old/P.BUNDLE_PATH/'manifest.json');row=old_doc['sources'][0];original=(old/P.BUNDLE_PATH/row['receipt_path']).read_bytes()
        new=self.fixture('new',ledger=self.public_ledger(citations=[])).prepare()
        with patch.object(socket,'getaddrinfo',side_effect=AssertionError('reuse no DNS')),patch.object(P.subprocess,'run',side_effect=AssertionError('reuse no curl')):
            result=RUNTIME.collect_research_sources_attempt(attempt_root=new,trusted_http_connect_proxy=self.endpoint,reuse_sources_from=(old,));RUNTIME.verify_attempt(new)
        self.assertEqual(result['fresh_get_count'],0);self.assertEqual(result['reused_snapshot_count'],1)
        document=SOURCES.read(new/P.BUNDLE_PATH/'manifest.json');r=document['sources'][0];self.assertEqual((new/P.BUNDLE_PATH/r['original_receipt_path']).read_bytes(),original)
        self.assertNotIn('started_at',SOURCES.read(new/P.BUNDLE_PATH/r['receipt_path']));self.assertEqual(SOURCES.read(new/P.BUNDLE_PATH/r['original_receipt_path'])['finished_at'],'2026-10-28T01:00:01Z')
        P.verify(new,required=True,archived=True,attempt_verifier=RUNTIME.verify_attempt)
    def test_proxy_reuse_and_mixed_direct_fresh_are_not_relabelled(self):
        old=self.public_attempt('old',ledger=self.public_ledger(citations=[]));ledger=self.public_ledger(citations=[]);ledger['sources'].append({'source_id':'fresh','url':self.url(),'access_status':'read_full','citations':[]})
        new=self.fixture('mixed',ledger=ledger).prepare()
        with self.transport():RUNTIME.collect_research_sources_attempt(attempt_root=new,curl=CURL,trusted_http_connect_proxy=self.endpoint,reuse_sources_from=(old,))
        doc=SOURCES.read(new/P.BUNDLE_PATH/'manifest.json');a,b=doc['sources'];self.assertEqual(SOURCES.read(new/P.BUNDLE_PATH/a['original_receipt_path'])['public_address_policy'],'global-unicast-dns-pinned-no-proxy/v1');self.assertEqual(SOURCES.read(new/P.BUNDLE_PATH/b['receipt_path'])['public_address_policy'],P.ADDRESS_POLICY)
        child=self.fixture('child',ledger=ledger).prepare()
        with patch.object(socket,'getaddrinfo',side_effect=AssertionError('reuse no DNS')),patch.object(P.subprocess,'run',side_effect=AssertionError('reuse no GET')):
            result=RUNTIME.collect_research_sources_attempt(attempt_root=child,trusted_http_connect_proxy=self.endpoint,reuse_sources_from=(new,));RUNTIME.verify_attempt(child)
        self.assertEqual(result['reused_snapshot_count'],2)
    def test_resealed_transport_tamper_fails_normal_archive_and_reuse(self):
        original=self.proxy_attempt('transport-base')
        for field,value in [('connect_status',407),('selected_address','1.1.1.1'),('proxy_peer',{'address':'8.8.8.8','port':7897}),('origin_tls',{'required':True,'verification_name':'other.example','verify_result':0}),('headers',[])]:
            bad=self.root/('bad-'+field);shutil.copytree(original,bad)
            for path in [bad,*bad.rglob('*')]:path.chmod(0o755 if path.is_dir() else 0o644)
            bundle=bad/P.BUNDLE_PATH;doc=SOURCES.read(bundle/'manifest.json');row=doc['sources'][0];rp=bundle/row['receipt_path'];r=SOURCES.read(rp);r['responses'][0][field]=value;rp.write_bytes(SOURCES.encoded(r));row['receipt_sha256']=SOURCES.sha(rp);(bundle/'manifest.json').write_bytes(SOURCES.encoded(doc))
            lock=SOURCES.read(bad/P.LOCK_PATH);lock.update(entries=SOURCES.inventory(bundle),bundle_manifest_sha256=SOURCES.sha(bundle/'manifest.json'));(bad/P.LOCK_PATH).write_bytes(SOURCES.encoded(lock))
            for archived in [False,True]:
                with self.subTest(field=field,archived=archived),self.assertRaises(P.ResearchSourceError):P.verify(bad,required=True,archived=archived,attempt_verifier=RUNTIME.verify_attempt)
            target=self.fixture('consume-'+field,ledger={'sources':[{'source_id':'S1','url':self.url(),'access_status':'read_full','citations':[]}]}).prepare()
            with patch.object(P,'fetch',side_effect=AssertionError('invalid origin no GET')),self.assertRaises(RUNTIME.ScoringRuntimeError):RUNTIME.collect_research_sources_attempt(attempt_root=target,trusted_http_connect_proxy=self.endpoint,reuse_sources_from=(bad,))
    def test_historical_receipt_unknown_collector_sha_is_rejected(self):
        receipt=self.fetch();receipt['collector_sha256']='0'*64
        with self.assertRaisesRegex(P.ResearchSourceError,'unknown proxy collector'):P._public_receipt(receipt,'unknown')
        direct_path=self.root/'direct.html';direct=self.public_fetch('https://publication.example/read',direct_path,{})
        direct['collector_sha256']='0'*64
        with self.assertRaisesRegex(P.ResearchSourceError,'unknown direct collector'):P._public_receipt(direct,'unknown')

    def test_fresh_direct_receipt_cannot_be_sealed_as_proxy(self):
        attempt=self.fixture('bad-fresh',ledger=self.public_ledger(citations=[])).prepare()
        def wrong(url,destination,specification,curl=None,**kwargs):return self.public_fetch(url,destination,specification,curl)
        with patch.object(P,'fetch',side_effect=wrong),self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'RESEARCH_SOURCE_RECEIPT_INVALID'):RUNTIME.collect_research_sources_attempt(attempt_root=attempt,trusted_http_connect_proxy=self.endpoint)
        self.assertFalse((attempt/P.LOCK_PATH).exists());self.assertFalse((attempt/P.BUNDLE_PATH).exists())
    def test_independent_package_and_moved_archive_without_runtime_or_curl(self):
        attempt=self.proxy_attempt('packaged')
        RUNTIME.run_rules_attempt(attempt_root=attempt,runtime_python=self.runtime_python,timeout_seconds=15);RUNTIME.prepare_semantics_attempt(attempt_root=attempt);RUNTIME.finalize_score_attempt(attempt_root=attempt)
        builder=load_module('proxy_package_builder',REPO_ROOT/'tools/e2e-build/build_skill_packages.py');distribution=self.root/'distribution';result=builder.build_skill_package(REPO_ROOT,distribution,'score-general-e2e',source_revision='proxy-test')
        with zipfile.ZipFile(distribution/result['archive']) as archive:archive.extractall(distribution/'installed')
        script=distribution/'installed/score-general-e2e/scripts/score_general_e2e.py';self.assertTrue(script.with_name('research_sources_proxy.py').is_file());self.assertEqual(SOURCES.sha(script.with_name('research_sources.py')),SOURCES.sha(Path(SOURCES.__file__)))
        moved=self.root/'archive-moved';shutil.copytree(attempt,moved,ignore=shutil.ignore_patterns('runtime'))
        env={k:v for k,v in os.environ.items() if k not in {'PYTHONPATH','PYTHONHOME'}};env['PATH']='/missing-collector-tools'
        checked=REAL_RUN([sys.executable,str(script),'verify-score','--attempt-root',str(moved),'--archived'],cwd=self.root,env=env,capture_output=True,text=True,timeout=30)
        self.assertEqual(checked.returncode,0,checked.stdout+checked.stderr);self.assertTrue(json.loads(checked.stdout)['score_valid'])

    def test_cli_flag_default_direct_pin_and_v2_proxy_rejection(self):
        self.assertEqual(SOURCES.sha(Path(SOURCES.__file__)),'4fcb5239474bf5d3749f817abdccd02054ba86e2d766458f78f70d2da8c8968a')
        p=REAL_RUN([sys.executable,str(Path(RUNTIME.__file__)),'collect-research-sources','--help'],capture_output=True,text=True);self.assertEqual(p.returncode,0);self.assertIn('--trusted-http-connect-proxy',p.stdout)
        # Schema/profile v2 is deliberately unsupported only for this explicit mode.
        from tests.general_e2e.test_research_sources_native import NativeSourceTests
        native=NativeSourceTests(methodName='runTest');native.root=self.root
        attempt=native.fixture('v2')
        with patch.object(P.subprocess,'run',side_effect=AssertionError('unsupported mode no curl')),self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'RESEARCH_SOURCE_TRANSPORT_UNSUPPORTED'):RUNTIME.collect_research_sources_attempt(attempt_root=attempt,trusted_http_connect_proxy=self.endpoint)

if __name__=='__main__':unittest.main()

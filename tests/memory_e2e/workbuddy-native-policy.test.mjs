import test from 'node:test';
import assert from 'node:assert/strict';
import {NativeProfileBinding,buildUnitMemoryRules,centerCoordinationPaths} from '../../eval_memory_e2e/native/workbuddy-native-policy.mjs';

const roots=['/Users/SYNTHETIC/protected'];
const binding=()=>new NativeProfileBinding({uid:'synthetic',peerPid:42,deniedRoots:roots});
const request=(id='r1',session='s1',extra={})=>({messageId:id,uid:'synthetic',sessionId:session,
  command:'sandbox.rules.fetch_profile',data:{sessionId:session,platform:'macos',_client:{pid:42},...extra}});
const response=(id='r1',extra={})=>({messageId:id,success:true,data:{profile:JSON.stringify(['(allow file-read* (subpath \\"/\\"))']),
  serverRevision:43,upToDate:false,execParams:{deniedReadPaths:['native-deny'],grantedPaths:['**'],nativeField:'preserve'},...extra}});

test('preserves every native fragment and grant while appending deny-only SBPL',()=>{
  const b=binding(),input=response(),raw=input.data.profile;b.request(request());
  const output=b.response(input).message;
  assert.ok(output.data.profile.startsWith(raw.slice(0,-1)+','));
  assert.deepEqual(JSON.parse(output.data.profile).slice(0,1),JSON.parse(raw));
  assert.deepEqual(output.data.execParams.grantedPaths,['**']);
  assert.deepEqual(output.data.execParams.deniedReadPaths,['native-deny',roots[0]+'/**']);
  assert.equal(output.data.execParams.nativeField,'preserve');
  assert.equal(input.data.profile,raw);
  assert.ok(JSON.parse(output.data.profile)[1].startsWith('(deny file-read* file-write* '));
});

test('accepts a cached profile only on the same connection, session, platform and native revision',()=>{
  const b=binding();b.request(request());b.response(response());
  b.request(request('r2'));assert.equal(b.response(response('r2',{profile:'',upToDate:true})).changed,false);
  const fresh=binding();fresh.request(request());
  assert.throws(()=>fresh.response(response('r1',{profile:'',upToDate:true})),/UNBOUND_CACHE/);
  b.request(request('r3','s2'));
  assert.throws(()=>b.response(response('r3',{profile:'',upToDate:true})),/UNBOUND_CACHE/);
  b.request(request('r4'));assert.throws(()=>b.response(response('r4',{profile:'',upToDate:true,serverRevision:44})),/UNBOUND_CACHE/);
});

test('refuses forged identities, duplicate IDs, session mismatch and unbound responses',()=>{
  for(const input of [{...request(),uid:'other'},request('r1','s1',{_client:{pid:43}}),
    request('r1','s1',{sessionId:'other'}),request('r1','s1',{platform:'darwin'})]) {
    assert.throws(()=>binding().request(input),/WB_POLICY_/);
  }
  const b=binding();b.request(request());assert.throws(()=>b.request(request()),/REQUEST_ID/);
  assert.throws(()=>b.response(response('unknown')),/UNBOUND_RESPONSE/);
});

test('refuses revision rollback, invalid policy shape and unsafe path literals',()=>{
  const b=binding();b.request(request());b.response(response());b.request(request('r2'));
  assert.throws(()=>b.response(response('r2',{serverRevision:42})),/REVISION/);
  for(const profile of ['{}','[]','[42]']){
    const b=binding();b.request(request());assert.throws(()=>b.response(response('r1',{profile})),/NATIVE_FRAGMENTS/);
  }
  for(const root of ['/','/Users/SYNTHETIC/x/../y','/Users/SYNTHETIC/quote"','/Users/SYNTHETIC/new\nline'])
    assert.throws(()=>new NativeProfileBinding({uid:'synthetic',peerPid:42,deniedRoots:[root]}),/DENY_PATH/);
});

test('forwards non-profile native requests and errors without payload mutation',()=>{
  const b=binding(),r={...request(),command:'sandbox.rules.decide_file'};b.request(r);
  const reply={messageId:'r1',success:true,data:{native:'opaque'}};
  assert.equal(b.response(reply).message,reply);
  b.request(request('r2'));const error={messageId:'r2',success:false,error:'native denial'};
  assert.equal(b.response(error).message,error);
});

test('unit policy denies other debug units and outside writes without adding native grants',()=>{
  const memoryUnit={debugRoot:'/Users/SYNTHETIC/debug',allowedPaths:['/Users/SYNTHETIC/debug/unit/home','/Users/SYNTHETIC/debug/unit/tmp'],
    readLiterals:['/Users/SYNTHETIC/debug/unit/gateway.json']};
  const rules=buildUnitMemoryRules(memoryUnit);
  assert.ok(rules.every(x=>x.startsWith('(deny ')));
  assert.ok(rules[0].includes('/System/Volumes/Data/Users/SYNTHETIC/debug'));
  assert.ok(rules[0].includes('(require-not (literal "/Users/SYNTHETIC/debug/unit/gateway.json"))'));
  assert.ok(!rules[2].includes('gateway.json'));
  assert.ok(rules.some(x=>x.startsWith('(deny file-write-unlink')&&x.includes('(literal "/Users/SYNTHETIC/debug/unit/home")')));
  const b=new NativeProfileBinding({uid:'synthetic',peerPid:42,deniedRoots:roots,memoryUnit});
  b.request(request());const output=b.response(response()).message;
  assert.ok(JSON.parse(output.data.profile).some(x=>x.startsWith('(deny file-write-unlink')));
  assert.deepEqual(output.data.execParams.grantedPaths,['**']);
});

test('unit path exclusions cannot cover all debug data or escape the declared debug root',()=>{
  for(const allowedPaths of [[],['/Users/SYNTHETIC/debug'],['/Users/SYNTHETIC/other']])
    assert.throws(()=>buildUnitMemoryRules({debugRoot:'/Users/SYNTHETIC/debug',allowedPaths}),/WB_POLICY_UNIT_/);
});

test('a trusted Center socket exception can never enter the data-worker policy',()=>{
  const memoryUnit={debugRoot:'/Users/SYNTHETIC/debug',allowedPaths:['/Users/SYNTHETIC/debug/unit/home'],
    writeLiterals:['/tmp/wcbm-wb-abcd.sock']};
  assert.ok(buildUnitMemoryRules(memoryUnit)[2].includes('(literal "/private/tmp/wcbm-wb-abcd.sock")'));
  assert.throws(()=>new NativeProfileBinding({uid:'synthetic',peerPid:42,deniedRoots:roots,memoryUnit}),/DATA_WORKER_CONTROL_SOCKET/);
});
test('the short temp alias is protected without granting another writable directory',()=>{
  const rules=buildUnitMemoryRules({debugRoot:'/Users/SYNTHETIC/debug',allowedPaths:['/Users/SYNTHETIC/debug/unit/tmp'],
    protectedAliases:['/tmp/wbme-012345abcdef']});
  assert.ok(rules.every(x=>x.startsWith('(deny ')));
  const unlink=rules.find(x=>x.startsWith('(deny file-write-unlink'));
  assert.ok(unlink.includes('(literal "/tmp/wbme-012345abcdef")'));
  assert.ok(unlink.includes('(literal "/private/tmp/wbme-012345abcdef")'));
  assert.ok(!rules.find(x=>x.startsWith('(deny file-write*')).includes('wbme-'));
});

test('Center coordination paths match the two actual native FDs from the frozen synthetic witness',()=>{
  const root='/Users/LQ4T7293TX/debug-workspace/e2e-evaluate/memory-e2e/workbuddy-admission-20261021-r1/center-lock-discovery-01/app-home';
  assert.deepEqual(centerCoordinationPaths(root,'/tmp/wcbm-wb-ba69add84ce9f8b4.sock'),
    ['/tmp/wcbm-wb-ba69add84ce9f8b4.sock','/tmp/workbuddy-sandbox-center-epoch-26f904b596bb8212.lock','/tmp/workbuddy-sandbox-center-d080f67f00ff15e7.lock']);
});

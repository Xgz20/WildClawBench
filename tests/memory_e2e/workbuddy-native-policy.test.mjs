import test from 'node:test';
import assert from 'node:assert/strict';
import {NativeProfileBinding} from '../../eval_memory_e2e/native/workbuddy-native-policy.mjs';

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

import assert from 'node:assert/strict';
import test from 'node:test';
import vm from 'node:vm';
import { createHash, webcrypto } from 'node:crypto';
import { readNativeProjectWorkspace, PROJECT_SOURCE_SHA256 } from '../../tools/report/e2e-shared/doubaowork/runtime-project.mjs';
const sha=s=>createHash('sha256').update(s).digest('hex');
const state=()=>({client:{project_name:'exact',project_id_sha256:sha('123')},workspace:'/unit/workspace',history:[]});
function page({workspace='/unit/workspace',device='this-device',sourceSha=PROJECT_SOURCE_SHA256}={}) {
 const project={projectId:'123',name:'exact',folders:[{projectId:'123',projectFolderId:'456',folderDeviceId:device,isPrimary:true,workspace}]};
 const require=id=>({'tb':{S:()=>({listStatus:{initiated:true},projectMap:{'123':project}})},PBe:{u:async()=>'this-device'},ZBb:{W:()=>workspace}}[id]);
 require.m=Object.fromEntries(['tb','gt','tr','ZBb','PBe','kuf','RJ'].map(id=>[id,()=>{}]));
 let first=true;const chunks=[];chunks.push=args=>args[2](require);
 const context=vm.createContext({window:{'chunk_@flow-web/desktop':chunks},TextEncoder,Uint8Array,
  document:{querySelectorAll:()=>[{getAttribute:()=> '123',querySelectorAll:()=>[{getAttribute:()=> 'exact'}]}]},
  crypto:{randomUUID:()=> 'fixture',subtle:{digest:async(...args)=>{if(first){first=false;return Uint8Array.from(Buffer.from(sourceSha,'hex')).buffer;}return webcrypto.subtle.digest(...args);}}}});
 return{evaluate:(fn,cfg)=>{context.cfg=cfg;return vm.runInContext(`(${fn.toString()})(cfg)`,context);}};
}
test('native project readback binds the exact UI ID, initialized store, current device and primary folder',async()=>{
 const s=state();assert.equal(await readNativeProjectWorkspace(page(),s),s.workspace);assert.equal(s.history.length,1);
 await assert.rejects(readNativeProjectWorkspace(page({workspace:'/other'}),state()),/FOLDER_CHANGED/);
 await assert.rejects(readNativeProjectWorkspace(page({device:'other-device'}),state()),/FOLDER_CHANGED/);
 await assert.rejects(readNativeProjectWorkspace(page({sourceSha:'0'.repeat(64)}),state()),/MODULE_SOURCE_CHANGED/);
});

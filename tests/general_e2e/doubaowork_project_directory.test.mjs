import test from 'node:test';import assert from 'node:assert/strict';
import {verifyProjectDirectory,PROJECT_DIRECTORY_SOURCE_SHA256} from '../../tools/report/e2e-shared/doubaowork/project-directory.mjs';
const fixture=()=>({source_sha256:PROJECT_DIRECTORY_SOURCE_SHA256,loading:false,failed:false,deviceId:'local',project:{projectId:'123',version:2,folders:[{projectId:'123',folderDeviceId:'local',isPrimary:true,workspace:'/tmp/exact-workspace',version:3}]}});
test('native directory proof binds the exact project, current device and complete path',()=>{
  assert.equal(verifyProjectDirectory(fixture(),'123','/tmp/exact-workspace').path,'/tmp/exact-workspace');
});
test('unknown profile, foreign device, same basename elsewhere, loading and duplicate roots fail closed',()=>{
  for(const mutate of [x=>x.source_sha256='unknown',x=>x.deviceId='foreign',x=>x.project.projectId='456',
    x=>x.loading=true,x=>x.project.folders[0].workspace='/different/exact-workspace',x=>x.project.folders.push({...x.project.folders[0]})]){
    const f=fixture();mutate(f);assert.throws(()=>verifyProjectDirectory(f,'123','/tmp/exact-workspace'));
  }
});

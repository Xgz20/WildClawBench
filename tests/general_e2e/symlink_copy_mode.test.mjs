import assert from 'node:assert/strict';
import test from 'node:test';
import {mkdtemp,mkdir,writeFile,symlink,lchmod,lstat,readFile,readlink,rm,chmod} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {copyCandidateTree} from '../../tools/report/skills/general-e2e/collect-general-e2e/scripts/lib/general-finalizer.mjs';

test('candidate copier preserves a0777 contained link without following or changing its target',async()=>{
  const root=await mkdtemp(join(tmpdir(),'general-e2e-link-mode-'));
  try{
    const src=join(root,'source'),dst=join(root,'copy');await mkdir(join(src,'nested'),{recursive:true});
    const target=join(src,'sentinel.txt');await writeFile(target,'synthetic-sentinel');await chmod(target,0o640);
    const link=join(src,'nested/link');await symlink('../sentinel.txt',link);
    if(process.platform==='darwin')await lchmod(link,0o777);
    const entries=await copyCandidateTree(src,dst,{ignored_directories:[],forbidden_directories:[]});
    const expected=entries.find(e=>e.path==='nested/link');assert.equal(expected.mode,'0777');
    assert.equal((await lstat(join(dst,'nested/link'))).mode&0o777,0o777);
    assert.equal(await readlink(join(dst,'nested/link')),'../sentinel.txt');
    assert.equal((await lstat(target)).mode&0o777,0o640);assert.equal(await readFile(target,'utf8'),'synthetic-sentinel');
    assert.equal((await lstat(link)).mode&0o777,0o777);
  }finally{await rm(root,{recursive:true,force:true});}
});

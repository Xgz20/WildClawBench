import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtemp, mkdir, symlink, writeFile, rm, realpath } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { listSessionDirectoryIds } from '../../tools/report/e2e-shared/doubaowork/platform.mjs';

test('a lazy native inventory stays empty without creating it, while bad ancestors remain errors', async () => {
  const dir=await realpath(await mkdtemp(join(tmpdir(),'dw-inventory-')));
  const root=join(dir,'.sessions');
  try {
    assert.deepEqual(await listSessionDirectoryIds({roots:{sessions_root:root}}),[]);
    await mkdir(root);await mkdir(join(root,'123'));await mkdir(join(root,'not-session'));
    assert.deepEqual(await listSessionDirectoryIds({roots:{sessions_root:root}}),['123']);
    await symlink(join(dir,'absent'),join(dir,'linked'));
    await assert.rejects(listSessionDirectoryIds({roots:{sessions_root:join(dir,'linked','.sessions')}}),/符号链接/);
    await writeFile(join(dir,'file'),'not a directory');
    await assert.rejects(listSessionDirectoryIds({roots:{sessions_root:join(dir,'file','.sessions')}}),/不是普通目录/);
  } finally { await rm(dir,{recursive:true,force:true}); }
});

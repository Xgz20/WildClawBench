// Prevent host Office metadata writers from changing an already frozen copy.
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { lstat, readdir } from 'node:fs/promises';
import { extname, join } from 'node:path';

const run = promisify(execFile);
const OFFICE = new Set(['.docx', '.xlsx', '.pptx', '.docm', '.xlsm', '.pptm']);
export async function sealFrozenOfficeFile(path) {
  if (process.platform !== 'darwin' || !OFFICE.has(extname(path).toLowerCase())) return;
  const info = await lstat(path);
  if (!info.isFile() || info.isSymbolicLink()) throw Error('FROZEN_OFFICE_NOT_REGULAR');
  await run('/usr/bin/chflags', ['uchg', path], { timeout: 10_000 });
  const { stdout } = await run('/usr/bin/stat', ['-f', '%f', path], { encoding: 'utf8', timeout: 10_000 });
  const flags = Number(stdout.trim());
  if (!Number.isSafeInteger(flags) || !(flags & 2)) throw Error('FROZEN_OFFICE_IMMUTABLE_NOT_SET');
}

// Called only for a staging tree created by this finalizer before publication.
// It never clears protection from a published candidate or a source workspace.
export async function clearOwnedStagingOffice(root) {
  if (process.platform !== 'darwin') return;
  for (const child of await readdir(root, { withFileTypes: true })) {
    const path = join(root, child.name);
    if (child.isDirectory()) await clearOwnedStagingOffice(path);
    else if (child.isFile() && OFFICE.has(extname(path).toLowerCase()))
      await run('/usr/bin/chflags', ['nouchg', path], { timeout: 10_000 });
  }
}

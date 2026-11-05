// The 2.35.15 menu only renames a project; it no longer edits its folder.
// Read the same initialized native project store and device-specific primary
// folder resolver used by the visible Open Project Folder action.
export async function readNativeProjectWorkspace(page, state) {
  const result = await page.evaluate(async cfg => {
    const chunks = window['chunk_@flow-web/desktop'];
    if (!Array.isArray(chunks) || Array.isArray(window['@flow-web/desktop:stable'])) throw Error('DOUBAOWORK_PROJECT_RUNTIME_UNKNOWN');
    let req; chunks.push([['wcb-project-read-' + crypto.randomUUID()], {}, r => { req = r; }]);
    const ids = ['tb','gt','tr','ZBb','PBe','kuf','RJ'];
    if (ids.some(id => typeof req?.m?.[id] !== 'function')) throw Error('DOUBAOWORK_PROJECT_MODULE_UNAVAILABLE');
    const source = ids.map(id => String(req.m[id])).join('\n');
    const hash = value => crypto.subtle.digest('SHA-256', new TextEncoder().encode(value)).then(b => [...new Uint8Array(b)].map(x=>x.toString(16).padStart(2,'0')).join(''));
    const sourceSha = await hash(source);
    if (!cfg.sourceHashes.includes(sourceSha)) throw Error('DOUBAOWORK_PROJECT_MODULE_SOURCE_CHANGED');
    const rows = [...document.querySelectorAll('section[data-project-id]')].filter(e =>
      [...e.querySelectorAll('[title]')].some(n => n.getAttribute('title') === cfg.name));
    if (rows.length !== 1) throw Error('DOUBAOWORK_PROJECT_ROW_AMBIGUOUS');
    const id = rows[0].getAttribute('data-project-id');
    if (!/^[0-9]{1,64}$/.test(id || '') || await hash(id) !== cfg.projectSha) throw Error('DOUBAOWORK_PROJECT_ID_CHANGED');
    const store = req('tb').S(), project = store.projectMap?.[id], device = await req('PBe').u();
    if (store.listStatus?.initiated !== true || !project || project.projectId !== id || project.name !== cfg.name
        || typeof device !== 'string' || !device || !Array.isArray(project.folders)) throw Error('DOUBAOWORK_PROJECT_STORE_UNBOUND');
    const folders = project.folders.filter(f => f.folderDeviceId === device && f.isPrimary === true);
    if (folders.length !== 1 || folders[0].projectId !== id || typeof folders[0].projectFolderId !== 'string'
        || req('ZBb').W(project, device) !== cfg.workspace || folders[0].workspace.trim() !== cfg.workspace) throw Error('DOUBAOWORK_PROJECT_FOLDER_CHANGED');
    return { workspace: cfg.workspace, profile: 'doubaowork-native-primary-folder-2.35.15/v1', module_source_sha256: sourceSha,
      project_id_sha256: await hash(id), device_id_sha256: await hash(device), folder_id_sha256: await hash(folders[0].projectFolderId) };
  }, { name: state.client.project_name, workspace: state.workspace, projectSha: state.client.project_id_sha256,
    sourceHashes: [PROJECT_SOURCE_SHA256, PROJECT_LAZY_SOURCE_SHA256] });
  if (result.workspace !== state.workspace || result.project_id_sha256 !== state.client.project_id_sha256) throw Error('DOUBAOWORK_PROJECT_READBACK_INVALID');
  state.history.push({ event: 'NATIVE_PRIMARY_PROJECT_FOLDER_RECONFIRMED', at: new Date().toISOString(), ...result });
  return result.workspace;
}

export const PROJECT_SOURCE_SHA256 = '38bd5081f9639f936627caa002ef69604360fb07e5efcca044c74a0ac68a317c';
// Same getters after the native lazy chunk replaces two factories. The only
// differences in PBe/kuf are verified minifier-local variable renames.
export const PROJECT_LAZY_SOURCE_SHA256 = '60ecaf7aaee2d6d9bd97635355bbb7d8cf349d1a8feb9156918330dd21978702';

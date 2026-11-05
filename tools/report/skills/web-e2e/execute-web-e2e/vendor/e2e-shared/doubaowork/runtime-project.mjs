// The 2.35.15 menu only renames a project; it no longer edits its folder.
// Read the same initialized native project store and device-specific primary
// folder resolver used by the visible Open Project Folder action.
export async function readNativeProjectWorkspace(page, state) {
  const version = state.client.version || '2.35.15';
  const getterSourceSha = version === '2.35.15' ? PROJECT_GETTER_SOURCE_SHA256
    : version === '2.35.19' ? PROJECT_23519_GETTER_SOURCE_SHA256 : null;
  if (!getterSourceSha) throw Error('DOUBAOWORK_PROJECT_VERSION_UNVERIFIED');
  const result = await page.evaluate(async cfg => {
    const chunks = window['chunk_@flow-web/desktop'];
    if (!Array.isArray(chunks) || Array.isArray(window['@flow-web/desktop:stable'])) throw Error('DOUBAOWORK_PROJECT_RUNTIME_UNKNOWN');
    let req; chunks.push([['wcb-project-read-' + crypto.randomUUID()], {}, r => { req = r; }]);
    const ids = ['tb','gt','tr','ZBb','PBe','kuf','RJ'];
    if (ids.some(id => typeof req?.m?.[id] !== 'function')) throw Error('DOUBAOWORK_PROJECT_MODULE_UNAVAILABLE');
    // Lazy chunks can replace a factory with an alpha-renamed equivalent
    // after its exports have already been cached. Pin the actual functions
    // being invoked, rather than the subsequently replaced factory table.
    const getters = [req('tb').S, req('gt').L, req('tr').KD, req('ZBb').W,
      req('PBe').u, req('kuf').N, req('RJ').z?.getDeviceInfo];
    if (getters.some(fn => typeof fn !== 'function')) throw Error('DOUBAOWORK_PROJECT_GETTER_UNAVAILABLE');
    const source = getters.map(fn => String(fn)).join('\n');
    const hash = value => crypto.subtle.digest('SHA-256', new TextEncoder().encode(value)).then(b => [...new Uint8Array(b)].map(x=>x.toString(16).padStart(2,'0')).join(''));
    const sourceSha = await hash(source);
    if (sourceSha !== cfg.getterSourceSha) throw Error('DOUBAOWORK_PROJECT_GETTER_SOURCE_CHANGED');
    const factorySha = await hash(ids.map(id => String(req.m[id])).join('\n'));
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
    return { workspace: cfg.workspace, profile: cfg.profile, getter_source_sha256: sourceSha,
      factory_source_sha256: factorySha,
      project_id_sha256: await hash(id), device_id_sha256: await hash(device), folder_id_sha256: await hash(folders[0].projectFolderId) };
  }, { name: state.client.project_name, workspace: state.workspace, projectSha: state.client.project_id_sha256,
    getterSourceSha, profile: `doubaowork-native-primary-folder-${version}/v2` });
  if (result.workspace !== state.workspace || result.project_id_sha256 !== state.client.project_id_sha256) throw Error('DOUBAOWORK_PROJECT_READBACK_INVALID');
  state.history.push({ event: 'NATIVE_PRIMARY_PROJECT_FOLDER_RECONFIRMED', at: new Date().toISOString(), ...result });
  return result.workspace;
}

export const PROJECT_SOURCE_SHA256 = '38bd5081f9639f936627caa002ef69604360fb07e5efcca044c74a0ac68a317c';
// Same getters after the native lazy chunk replaces two factories. The only
// differences in PBe/kuf are verified minifier-local variable renames.
export const PROJECT_LAZY_SOURCE_SHA256 = '60ecaf7aaee2d6d9bd97635355bbb7d8cf349d1a8feb9156918330dd21978702';
export const PROJECT_GETTER_SOURCE_SHA256 = 'c0c507e18c4a2d313560673263f7e52934262583b22bd5885b2f842da3453afa';
// Captured actual seven getters on 2.35.19; the required store/device/folder
// relationship and native resolver are checked independently after the pin.
export const PROJECT_23519_GETTER_SOURCE_SHA256 = '05110aa14aa5efe0d6f6c166ff58f5b11f86ef624e63aab81c4f330815ce6cbc';

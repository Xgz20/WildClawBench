"""Prepare empty same-account WorkBuddy units. No memory/auth data is imported."""
import argparse
import json
import os
import plistlib
import re
import subprocess
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = 'eval_memory_e2e'
from .astudio_scope import asar_file
from .io import publish, require, sha, timestamp
from .machine import machine_paths

ADAPTER = 'macos-seatbelt-workbuddy-unit/v1'

CONTRACT = 'workbuddy-case-memory-unit/v1'
NATIVE = Path(__file__).parent / 'native'
APP = Path('/Applications/WorkBuddy.app')


def item(path):
    path = Path(path).absolute()
    require(path.resolve() == path, 'WB_SCOPE_SOURCE_CANONICAL', str(path))
    return {'path': str(path), 'sha256': sha(path.read_bytes())}


def installation_witness():
    archive = APP / 'Contents/Resources/app.asar'
    code = {name: asar_file(archive, 'main/' + name).decode() for name in
            ('main-bootstrap.js', 'workbuddy-paths.js', 'app-instance.js', 'netdrive-env-route.js')}
    checks = {'config_home': 'WORKBUDDY_CONFIG_DIR' in code['app-instance.js'],
              'userdata_home': 'WORKBUDDY_USER_DATA_DIR' in code['workbuddy-paths.js'],
              'five_rpc_pipes': 'stdio:[`pipe`,`pipe`,`pipe`,`pipe`,`pipe`]' in code['main-bootstrap.js'],
              'node_backend': 'ELECTRON_RUN_AS_NODE:`1`' in code['main-bootstrap.js'],
              'epoch_socket': 'function buildEpochCenterAddress' in code['netdrive-env-route.js']}
    with (APP / 'Contents/Info.plist').open('rb') as stream:
        version = plistlib.load(stream)['CFBundleShortVersionString']
    cli_root = APP / 'Contents/Resources/app.asar.unpacked/cli'
    cli = cli_root / 'dist/codebuddy-lite-wb.mjs'
    require(version == '5.8.3' and all(checks.values()) and not (cli_root / 'customization.json').exists(),
            'WB_SCOPE_INSTALLATION_UNSUPPORTED', 'Source and customization must be re-audited')
    require(sha(cli.read_bytes()) == '9eacdcdaaf3d53877ca4eac53836a446770b9a40f5dc6382b43230c73fdc5448',
            'WB_SCOPE_CLI_DRIFT', str(cli))
    require(sha(archive.read_bytes()) == 'a7eff702411704d140d7d8d706fe9e711d9b13e304928481c9eba0af9c06f731',
            'WB_SCOPE_ASAR_DRIFT', 'Installed resources differ from the audited 5.8.3 source')
    return {'version': version, 'checks': checks, 'asar': item(archive), 'cli': item(cli),
            'source_sha256': {name: sha(text.encode()) for name, text in code.items()},
            'renderer_ui': item(APP / 'Contents/Resources/app.asar.unpacked/renderer/assets/src-DbE1_mgM.js'),
            'binary': item(APP / 'Contents/MacOS/Electron'),
            'center': item(cli_root / 'vendor/sandbox/5.8.6/sandbox-center'),
            'native_cli': item(cli_root / 'vendor/sandbox/5.8.6/sandbox-cli')}


def current_native_uid(optional=False):
    # Read process identity metadata, never the native credential file.
    rows = subprocess.check_output(['/bin/ps', '-axo', 'command='], text=True).splitlines()
    prefix = str(APP / 'Contents/Resources/app.asar.unpacked/cli/vendor/sandbox/5.8.6/sandbox-cli') + ' '
    uids = set()
    for row in rows:
        if row.startswith(prefix) and re.search(r' --app_home ' + re.escape(str(machine_paths()['workbuddy'])) + r'(?: |$)', row):
            matched = re.search(r' --uid ([A-Za-z0-9_-]+)(?: |$)', row)
            if matched:
                uids.add(matched[1])
    if optional and not uids:
        return None
    require(len(uids) == 1, 'WB_SCOPE_CURRENT_ACCOUNT_UNAVAILABLE', 'Need one current native account identity')
    return next(iter(uids))


def minimal_model_config(data):
    require(isinstance(data, list), 'WB_SCOPE_MODEL_SCHEMA', 'Only audited list-format models.json is admitted')
    selected = [row for row in data if isinstance(row, dict) and row.get('id') == 'xopglm52']
    require(len(selected) == 1, 'WB_SCOPE_MODEL_ID', 'Exactly one current xopglm52 provider is required')
    model = selected[0]
    allowed = {'id', 'name', 'apiKey', 'url', 'vendor', 'reasoning', 'supportsImages', 'supportsReasoning',
               'supportsToolCall', 'useCustomProtocol'}
    require(set(model) <= allowed and model.get('name') == 'xopglm52', 'WB_SCOPE_MODEL_FIELDS',
            'Re-audit unknown provider fields; never import memory or instructions')
    require(isinstance(model.get('apiKey'), str) and model['apiKey'] and isinstance(model.get('url'), str),
            'WB_SCOPE_MODEL_AUTH', 'Current provider configuration is incomplete')
    uri = urlsplit(model['url'])
    require(uri.scheme in ('https', 'http') and uri.hostname and not uri.username and not uri.password
            and '${' not in model['apiKey'] and '${' not in model['url'], 'WB_SCOPE_MODEL_ENDPOINT',
            'Provider environment references require separate admission')
    require(model.get('supportsToolCall') is True, 'WB_SCOPE_MODEL_TOOLS', 'Current provider must support native tools')
    require(not model.get('reasoning') or isinstance(model['reasoning'], dict)
            and set(model['reasoning']) <= {'effort', 'summary', 'enabled', 'type', 'budget_tokens',
                                           'defaultEffort', 'supportedEfforts', 'canDisableThinking'},
            'WB_SCOPE_MODEL_REASONING', 'Re-audit unknown reasoning configuration')
    return [model]


def create(folder, case_id, repetition, peer_addon, model_preferences=None):
    folder = Path(folder).absolute()
    require(folder.is_relative_to(machine_paths()['debug']) and folder.resolve() == folder and not folder.exists(),
            'WB_SCOPE_FRESH_ROOT', str(folder))
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', case_id) and 1 <= repetition <= 20,
            'WB_SCOPE_UNIT_KEY', case_id)
    witness = installation_witness()
    require(model_preferences is not None, 'WB_SCOPE_MODEL_PREFERENCES', 'Use current UI model-only metadata')
    preference_path = Path(model_preferences).absolute()
    require(preference_path.is_relative_to(machine_paths()['debug']) and preference_path.resolve() == preference_path,
            'WB_SCOPE_MODEL_PREFERENCE_PATH', 'Use an owned native UI metadata receipt')
    preferences = json.loads(preference_path.read_text())
    uid = preferences.get('uid')
    require(isinstance(uid, str) and re.fullmatch(r'[A-Za-z0-9_-]+', uid)
            and preferences.get('account_fingerprint') == sha(uid.encode()),
            'WB_SCOPE_CURRENT_ACCOUNT_RECEIPT', 'Current native UI account identity is required')
    native_uid = current_native_uid(optional=True)
    require(native_uid is None or native_uid == uid, 'WB_SCOPE_CURRENT_ACCOUNT_MISMATCH', 'Native UI/service accounts differ')
    model_source = machine_paths()['workbuddy'] / 'models.json'
    require(model_source.resolve() == model_source, 'WB_SCOPE_MODEL_SOURCE', 'No redirected ordinary provider file')
    model_bytes = model_source.read_bytes()
    model_config = minimal_model_config(json.loads(model_bytes))
    endpoint_origin = uri_origin(model_config[0]['url'])
    require(preferences.get('contract') == 'workbuddy-model-preferences/v1'
            and preferences.get('account_fingerprint') == sha(uid.encode())
            and preferences.get('selection', {}).get('id') == 'custom-local:xopglm52',
            'WB_SCOPE_MODEL_PREFERENCES', 'Current account/model selection must match')
    selection = preferences['selection']
    require(set(selection) <= {'id', 'isThinking', 'reasoningEffort'}
            and type(selection.get('isThinking')) is bool
            and selection.get('reasoningEffort') in ('minimal', 'low', 'medium', 'high', 'xhigh', 'max'),
            'WB_SCOPE_MODEL_PREFERENCE_FIELDS', 'Only audited model-selection fields are imported')
    require(preferences.get('thinking') in (None, selection['isThinking'])
            and preferences.get('effort') in (None, selection['reasoningEffort']),
            'WB_SCOPE_MODEL_PREFERENCE_CONFLICT', 'Model-specific and selected reasoning preferences differ')
    addon = item(peer_addon)
    require(addon['path'].endswith('/unix-peer.node'), 'WB_SCOPE_PEER_ADDON', addon['path'])
    folder.mkdir(parents=True, mode=0o700)
    for name in ('app-home', 'tmp', 'candidate', 'synthetic-non-target'):
        (folder / name).mkdir(mode=0o700)
    publish(folder / 'app-home/models.json', model_config)
    (folder / 'app-home/models.json').chmod(0o600)
    unit_id = uuid4().hex
    publish(folder / 'app-home/synthetic-control.txt', b'SYNTHETIC-ALLOW\n')
    publish(folder / 'synthetic-non-target/fact.txt', ('SYNTHETIC-DENY-' + unit_id + '\n').encode())
    (folder / 'app-home/protected-alias').symlink_to(folder / 'synthetic-non-target', target_is_directory=True)
    sources = {key: item(NATIVE / name) for key, name in
               [('gateway', 'workbuddy-executor-gateway.mjs'), ('guard', 'workbuddy-backend-spawn-guard.cjs'),
                ('client', 'workbuddy-executor-client.cjs'), ('policy', 'workbuddy-native-policy.mjs'),
                ('main_guard', 'workbuddy-seatbelt-spawn-guard.cjs'), ('supervisor', 'workbuddy-unit-launch.mjs'),
                ('model_readiness', 'workbuddy-unit-model.mjs')]}
    spec = {'contract': CONTRACT, 'created_at': timestamp(), 'unit_id': unit_id, 'case_id': case_id,
            'repetition': repetition, 'root': str(folder), 'app_home': str(folder / 'app-home'),
            'temp': str(folder / 'tmp'), 'candidate': str(folder / 'candidate'),
            'os_home': str(machine_paths()['home']), 'debug_root': str(machine_paths()['debug']),
            'account_uid': uid, 'account_fingerprint': sha(uid.encode()), 'account_verified_in_isolated_ui': False,
            'account_basis': 'ordinary_native_ui_profile_receipt_rechecked_before_isolated_ui_preparation', 'installation': witness,
            'peer_addon': addon, 'sources': sources, 'imported_memory_or_history': False,
            'imported_authentication': False, 'ordinary_memory_cleared': False, 'within_unit_reset': False,
            'imported_provider_configuration': {'model_id': 'xopglm52', 'catalog_id': 'custom-local:xopglm52',
                'source_sha256': sha(model_bytes), 'source_path': str(model_source),
                'provider_credential_material_present': True, 'destination': str(folder / 'app-home/models.json'),
                'endpoint_origin': endpoint_origin},
            'model_preferences': {key: preferences[key] for key in ('selection', 'thinking', 'effort')},
            'model_expected': 'xopglm52', 'zero_model_bootstrap_only': True, 'application_admitted': False,
            'ports': {'main_inspector': 9336, 'backend_inspector': 9337, 'ui': 9229},
            'scope_helper_sha256': sha(Path(__file__).read_bytes())}
    publish(folder / 'scope.json', spec)
    return {'scope': str(folder / 'scope.json'), 'unit_id': unit_id, 'account_fingerprint': spec['account_fingerprint'],
            'zero_model_bootstrap_only': True, 'application_admitted': False}


def uri_origin(value):
    parsed = urlsplit(value)
    return parsed.scheme + '://' + parsed.hostname + ((':' + str(parsed.port)) if parsed.port else '')


def load(scope, frozen=None):
    path = Path(scope).absolute()
    require(path.name == 'scope.json' and path.resolve() == path and path.is_relative_to(machine_paths()['debug']),
            'WB_SCOPE_PATH', str(path))
    spec = json.loads(path.read_text())
    root = path.parent
    require(spec['contract'] == CONTRACT and spec['root'] == str(root)
            and spec['app_home'] == str(root / 'app-home') and spec['temp'] == str(root / 'tmp')
            and spec['candidate'] == str(root / 'candidate') and spec['os_home'] == str(machine_paths()['home']),
            'WB_SCOPE_PATH_BINDING', str(path))
    require(spec['installation'] == installation_witness(), 'WB_SCOPE_INSTALLATION_DRIFT', str(path))
    for descriptor in spec['sources'].values():
        require(item(descriptor['path']) == descriptor, 'WB_SCOPE_SOURCE_DRIFT', descriptor['path'])
    # A v1 producer remains auditable after adding a compatible consumer. Runtime
    # actor sources stay exact; this does not relabel an old producer as current.
    creator = Path(__file__)
    if sha(creator.read_bytes()) != spec['scope_helper_sha256']:
        creator = root / 'source-snapshot/workbuddy_scope.py'
    require(creator.is_file() and sha(creator.read_bytes()) == spec['scope_helper_sha256'],
            'WB_SCOPE_CREATOR_SOURCE', 'Preserve the exact unit creation source')
    for name in ('app-home', 'tmp', 'candidate'):
        require((root / name).resolve() == root / name, 'WB_SCOPE_SYMLINK', name)
    if frozen is not None:
        require(frozen == freeze(path, spec), 'WB_SCOPE_FROZEN_DRIFT', str(path))
    return spec


def freeze(scope, spec=None):
    path = Path(scope).absolute()
    spec = spec or load(path)
    names = ['scope.json', 'gateway.json', 'main-spawn-spec.json', 'backend.sb', 'center.sb',
             'desktop-bootstrap-ready.json', 'model-selection-prepared.json',
             'app-home/admission-probe/result.json', 'runtime-observation.json']
    files = {str(path.parent / name): sha((path.parent / name).read_bytes()) for name in names}
    files[spec['app_home'] + '/models.json'] = sha(Path(spec['app_home'], 'models.json').read_bytes())
    return {'contract': CONTRACT, 'scope': str(path), 'scope_sha256': files[str(path)],
            'unit_id': spec['unit_id'], 'case_id': spec['case_id'], 'repetition': spec['repetition'],
            'root': spec['root'], 'app_home': spec['app_home'], 'candidate': spec['candidate'],
            'account_fingerprint': spec['account_fingerprint'], 'files': files}


def bind_batch(profile, root, unit, scenarios, repeats):
    spec = load(unit['scope'], unit)
    require(str(Path(root).absolute()) == spec['root'] and scenarios == [spec['case_id']] and repeats == 1,
            'WB_SCOPE_BATCH_BINDING', 'One case and repetition per private WorkBuddy unit')
    require(profile.get('memory_protocol', {}).get('formal_scoring_allowed') is False,
            'WB_SCOPE_DIAGNOSTIC_ONLY', 'Formal mixed20 is not admitted')
    profile['isolation'] = 'verified_namespace'
    return spec


def native_metadata(spec):
    path = Path(spec['app_home']) / 'workbuddy.db'
    connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    connection.execute('PRAGMA query_only=ON')
    try:
        sessions = [{'conversation_id': row[0], 'cwd': row[1], 'status': row[2]}
                    for row in connection.execute('SELECT id,cwd,status FROM sessions WHERE deleted_at IS NULL')]
        runs = [row[0] for row in connection.execute('SELECT status FROM automation_runs')]
        running = connection.execute('SELECT COUNT(*) FROM automation_runtime_state WHERE running != 0').fetchone()[0]
        return {'sessions': sessions, 'automation_run_statuses': runs, 'automation_running_count': running}
    finally:
        connection.close()


def attest(unit, boundary=None):
    from .os_boundary import process_table, check_policy, OPERATIONS
    spec = load(unit['scope'], unit)
    root = Path(spec['root'])
    require(not (root / 'desktop-main-exited.json').exists(), 'WB_SCOPE_CLOSED', 'Do not relaunch a closed unit')
    gw = json.loads((root / 'gateway.json').read_text())
    rows = process_table()
    main = rows.get(gw['main']['pid'])
    require(main and main['ppid'] == gw['main']['ppid'] and main['started_at'] == gw['main']['started']
            and main['command'] == gw['main']['command'], 'WB_SCOPE_MAIN_DRIFT', 'Original Main must remain live')
    backend = [r for r in rows.values() if r['ppid'] == main['pid'] and r['command'] == gw['backend_command']]
    center = [r for r in rows.values() if r['ppid'] == main['pid']
              and r['command'].startswith(spec['installation']['center']['path'] + ' ')
              and '--app_home ' + spec['app_home'] in r['command']]
    require(len(backend) == len(center) == 1, 'WB_SCOPE_ACTOR_DRIFT', 'One bound backend and Center required')
    actors = {'backend': backend[0], 'center': center[0]}
    proof = json.loads((root / 'app-home/admission-probe/result.json').read_text())
    required = {'control', 'write-control', 'protected', 'alias', 'old-unit', 'outside-write'}
    require(proof.get('pass') is True and proof.get('backend_pid') == backend[0]['pid']
            and {t['name'] for t in proof['tests']} == required and proof['service_exit'] == {'code': 0, 'signal': None},
            'WB_SCOPE_SYNTHETIC_PROOF', 'Need real signed-backend/native-worker positive and negative controls')
    queries = {}
    for name, actor in actors.items():
        protected = {op: check_policy(actor['pid'], root / 'synthetic-non-target/fact.txt', op) for op in OPERATIONS}
        own = check_policy(actor['pid'], Path(spec['app_home']) / 'synthetic-control.txt', 'file-read-data')
        unlink = check_policy(actor['pid'], spec['app_home'], 'file-write-unlink')
        private = check_policy(actor['pid'], root / 'private/scenarios.json', 'file-read-data')
        non_target = {p: {op: check_policy(actor['pid'], p, op) for op in OPERATIONS} for p in gw['denied_roots']}
        require(own == 0 and unlink == 1 and private == 1 and all(v == 1 for v in protected.values())
                and all(v == 1 for values in non_target.values() for v in values.values()),
                'WB_SCOPE_OS_POLICY', 'OS policy differs from the frozen unit')
        queries[name] = {'protected': protected, 'own_read': own, 'root_unlink': unlink,
                         'controller_private_read': private, 'non_target': non_target}
    observation = json.loads((root / 'runtime-observation.json').read_text())
    require(observation['backend_pid'] == backend[0]['pid']
            and observation['config_dir'] == spec['app_home'] and observation['cli_home'] == spec['app_home']
            and observation['memory_enabled'] is True, 'WB_SCOPE_RUNTIME_HOME', 'Actual runtime memory root/condition required')
    if boundary is not None:
        require(boundary.get('admitted_adapter') == ADAPTER and boundary.get('unit_id') == spec['unit_id']
                and boundary.get('scope_sha256') == unit['scope_sha256'] and boundary.get('status') == 'os_enforced',
                'WB_SCOPE_BOUNDARY_BINDING', 'Wrong adapter or unit')
    return {'status': 'PASS', 'adapter': ADAPTER, 'unit_id': spec['unit_id'], 'main_pid': main['pid'],
            'actors': actors, 'policy_queries': queries, 'native_metadata': native_metadata(spec),
            'account_fingerprint': spec['account_fingerprint'], 'formal_scoring_allowed': False,
            'external_broker_isolation_exhaustive': False}


def profile(scope, output):
    from .batch import default_profiles, MEMORY_UI_LOCK
    from .native_profiles import driver_dependencies
    from .machine import machine_identity, node_identity
    path = Path(scope).absolute()
    unit = freeze(path)
    proof = attest(unit)
    spec = load(path, unit)
    result = default_profiles()['WorkBuddy']
    entry = NATIVE / 'workbuddy.mjs'
    result.update(profile_id='WorkBuddy-unit-' + spec['unit_id'][:12], machine=machine_identity(), node_runtime=node_identity(),
                  driver_command=['node', str(entry.resolve())], driver_sources=driver_dependencies(entry, NATIVE.parent.parent),
                  driver_source_scope='local-dependency-closure/v1', workbuddy_scope=unit, isolation='verified_namespace',
                  state_observation=True, ui_lock_path=str(MEMORY_UI_LOCK), driver_timeout_seconds=180,
                  memory_wait_seconds=10, pre_send_retry=False,
                  expected_config={'app_version': spec['installation']['version'], 'model_display': 'xopglm52',
                                   'permissions': 'default-sandbox', 'underlying_model': 'xopglm52',
                                   'account_fingerprint': spec['account_fingerprint']},
                  model_route={'catalog_id': 'custom-local:xopglm52', 'wire_model': 'xopglm52'},
                  non_target_memory_boundary={'required': True, 'status': 'os_enforced', 'admitted_adapter': ADAPTER,
                      'unit_id': spec['unit_id'], 'scope_sha256': unit['scope_sha256']},
                  memory_protocol={'purpose': 'scoped_workbuddy_canary', 'formal_scoring_allowed': False,
                                   'requires_enabled_memory': True, 'formation_verified': False})
    for helper in (Path(__file__), Path(__file__).with_name('os_boundary.py')):
        result['driver_sources'][str(helper.resolve())] = sha(helper.read_bytes())
    publish(output, {'WorkBuddy': result})
    return {'output': str(output), 'unit_id': spec['unit_id'], 'os_status': proof['status'], 'formal_scoring_allowed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['create', 'attest', 'profile'])
    parser.add_argument('--root')
    parser.add_argument('--case')
    parser.add_argument('--repetition', type=int)
    parser.add_argument('--peer-addon')
    parser.add_argument('--model-preferences')
    parser.add_argument('--scope')
    parser.add_argument('--frozen-json')
    parser.add_argument('--boundary-json')
    parser.add_argument('--output')
    args = parser.parse_args()
    if args.command == 'create':
        value = create(args.root, args.case, args.repetition, args.peer_addon, args.model_preferences)
    elif args.command == 'profile':
        value = profile(args.scope, args.output)
    else:
        value = attest(json.loads(args.frozen_json) if args.frozen_json else freeze(args.scope),
                       json.loads(args.boundary_json) if args.boundary_json else None)
    print(json.dumps(value, ensure_ascii=False))


if __name__ == '__main__':
    main()

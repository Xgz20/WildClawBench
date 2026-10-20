"""Prepare empty same-account WorkBuddy units. No memory/auth data is imported."""
import argparse
import json
import os
import plistlib
import re
import subprocess
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit

from .astudio_scope import asar_file
from .io import publish, require, sha, timestamp
from .machine import machine_paths

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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['create'])
    parser.add_argument('--root', required=True)
    parser.add_argument('--case', required=True)
    parser.add_argument('--repetition', required=True, type=int)
    parser.add_argument('--peer-addon', required=True)
    parser.add_argument('--model-preferences', required=True)
    args = parser.parse_args()
    print(json.dumps(create(args.root, args.case, args.repetition, args.peer_addon, args.model_preferences), ensure_ascii=False))


if __name__ == '__main__':
    main()

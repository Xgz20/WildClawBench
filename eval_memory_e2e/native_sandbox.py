"""Synthetic-only prefix-policy research for ACode's execution protocol.

The native compiler canonicalizes grants, so lexical intersection is NOT an OS
security boundary. A real synthetic symlink counterexample is retained. This
module cannot be used by an application execution profile. All paths in the
prefix calculation are lexical; real non-target data is never a test fixture.
"""
from copy import deepcopy
import argparse
import json
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from .io import require

ACCESS = {'none': 0, 'read': 1, 'write': 2}


def native_path(value):
    require(isinstance(value, str) and '\x00' not in value,
            'NATIVE_POLICY_PATH', 'Expected an absolute file URI')
    parsed = urlsplit(value)
    require(parsed.scheme == 'file' and not parsed.netloc and not parsed.query and not parsed.fragment,
            'NATIVE_POLICY_PATH', 'Only local absolute file URIs are supported')
    path = unquote(parsed.path)
    require(path.startswith('/') and '..' not in PurePosixPath(path).parts and '\x00' not in path,
            'NATIVE_POLICY_PATH', 'Path traversal is not supported')
    return str(PurePosixPath(path))


def _under(path, root):
    return path == root or path.startswith(root.rstrip('/') + '/')


def effective(entries, path):
    selected = [(root, access) for root, access in entries if _under(path, root)]
    if not selected:
        return 0
    depth = max(len(PurePosixPath(root).parts) for root, _ in selected)
    return min(access for root, access in selected if len(PurePosixPath(root).parts) == depth)


def intersect_permissions(original, mandatory):
    """Intersect two explicit prefix trees without adding any native grant.

    `mandatory` is controller-owned [(absolute path, none/read/write), ...].
    The native request's networking and all non-filesystem fields are retained.
    This deliberately rejects dynamic roots, globs and unknown fields until
    their exact semantics have independent native tests.
    """
    require(isinstance(original, dict) and original.get('type') == 'managed'
            and set(original) == {'type', 'file_system', 'network'}
            and original['network'] in ('enabled', 'restricted'),
            'NATIVE_POLICY_UNSUPPORTED', 'Only explicit managed native policies are supported')
    fs = original['file_system']
    require(isinstance(fs, dict) and fs.get('type') == 'restricted'
            and set(fs) <= {'type', 'entries', 'glob_scan_max_depth'} and isinstance(fs.get('entries'), list),
            'NATIVE_POLICY_UNSUPPORTED', 'Expected a restricted prefix policy')
    native = []
    for entry in fs['entries']:
        require(isinstance(entry, dict) and set(entry) == {'path', 'access'}
                and entry.get('access') in ACCESS and isinstance(entry.get('path'), dict)
                and set(entry['path']) == {'type', 'path'} and entry['path']['type'] == 'path',
                'NATIVE_POLICY_UNSUPPORTED', 'Dynamic roots, globs and optional path behavior need native admission')
        native.append((native_path(entry['path']['path']), ACCESS[entry['access']]))
    outer = []
    for root, access in mandatory:
        require(isinstance(root, str) and root.startswith('/') and '\x00' not in root
                and '..' not in PurePosixPath(root).parts and access in ACCESS,
                'NATIVE_MANDATORY_POLICY', 'Invalid controller prefix')
        outer.append((str(PurePosixPath(root)), ACCESS[access]))
    require(any(root == '/' for root, _ in outer), 'NATIVE_MANDATORY_POLICY', 'Explicit root restriction required')
    points = sorted({root for root, _ in native + outer}, key=lambda root: (len(PurePosixPath(root).parts), root))
    result = deepcopy(original)
    names = {value: key for key, value in ACCESS.items()}
    result['file_system']['entries'] = [
        {'path': {'type': 'path', 'path': PurePosixPath(root).as_uri()},
         'access': names[min(effective(native, root), effective(outer, root))]}
        for root in points
    ]
    return result


def transform_request(message, spec):
    """Exercise native policy transport only in an owned synthetic diagnostic.

    Native canonicalization prevents admitting this bridge as an OS boundary.
    Shell snapshot capture is also unsupported because it can execute shell
    initialization in the controller before the command sandbox.
    """
    require(spec.get('synthetic_only') is True and isinstance(spec.get('diagnostic_peer'), dict)
            and spec.get('application_integration_allowed') is False,
            'NATIVE_PREFIX_NOT_ADMITTED', 'Prefix intersection has a synthetic symlink escape; app integration is prohibited')
    require(isinstance(message, dict) and not isinstance(message, list),
            'NATIVE_RPC_UNSUPPORTED', 'JSON-RPC batches are unsupported')
    method = message.get('method')
    if method is None:
        require(set(message) <= {'jsonrpc', 'id', 'result', 'error'},
                'NATIVE_RPC_UNSUPPORTED', 'Unexpected server-request response')
        return message
    data_methods = {'process/start', 'fs/readFile', 'fs/writeFile', 'fs/createDirectory',
                    'fs/getMetadata', 'fs/canonicalize', 'fs/readDirectory', 'fs/walk', 'fs/remove', 'fs/copy'}
    metadata_methods = {'initialize', 'initialized', 'environment/info', 'environment/status',
                        'process/read', 'process/write', 'process/signal', 'process/terminate'}
    require(method in data_methods | metadata_methods, 'NATIVE_RPC_UNSUPPORTED', method)
    if method in metadata_methods:
        return message
    result = deepcopy(message)
    params = result.get('params')
    require(isinstance(params, dict), 'NATIVE_RPC_UNSUPPORTED', 'Missing native parameters')
    require(not params.get('shellSnapshot') and not params.get('networkProxy')
            and not params.get('managedNetwork') and not params.get('enforceManagedNetwork'),
            'NATIVE_RPC_UNSUPPORTED', 'Controller-side snapshot/proxy needs separate isolation admission')
    context = params.get('sandbox')
    if context is None:
        # No native sandbox was requested. Impose the controller boundary via
        # the installed native sandbox, preserving the original full-access
        # request's network setting. Never pass it through unrestricted.
        context = {'permissions': {'type': 'managed', 'file_system': {'type': 'restricted', 'entries': [
            {'path': {'type': 'path', 'path': 'file:///'}, 'access': 'write'}]}, 'network': 'enabled'},
            'cwd': params.get('cwd', PurePosixPath(spec['runtime']).as_uri()),
            'windowsSandboxLevel': 'disabled'}
    require(isinstance(context, dict) and set(context) <= {
        'permissions', 'cwd', 'windowsSandboxLevel', 'workspaceRoots', 'useLegacyLandlock'},
        'NATIVE_POLICY_UNSUPPORTED', 'Unknown native sandbox context field')
    require(context.get('windowsSandboxLevel') == 'disabled' and context.get('useLegacyLandlock') in (None, False),
            'NATIVE_POLICY_UNSUPPORTED', 'Only the macOS native backend is supported')
    native_path(context['cwd'])
    context['permissions'] = intersect_permissions(context['permissions'], spec['mandatory'])
    params['sandbox'] = context
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--transform-spec', type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads(args.transform_spec.read_text())
    try:
        result = transform_request(json.load(sys.stdin), spec)
        print(json.dumps({'ok': True, 'message': result}, separators=(',', ':')))
    except Exception as exc:
        from .io import MemoryEvaluationError
        if isinstance(exc, MemoryEvaluationError):
            print(json.dumps({'ok': False, 'reason': exc.code}))
        elif isinstance(exc, (ValueError, KeyError, TypeError)):
            print(json.dumps({'ok': False, 'reason': type(exc).__name__}))
        else:
            raise


if __name__ == '__main__':
    main()

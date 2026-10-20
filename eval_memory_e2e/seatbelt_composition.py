"""Preserve a frozen native SBPL and append controller-owned explicit denies.

This is a composition primitive, not an ACode integration or admission. The
installed kernel must supply its generated native SBPL before sandbox_apply;
its current JSON prefix-policy API is insufficient for this operation.
"""
import json

from .io import require, sha

HEADER = '(version 1)\n(allow default)\n'
OPERATIONS = {'file-read*', 'file-write*', 'file-read-data', 'appleevent-send'}


def _forms(source):
    """Parse only the small literal deny grammar our boundary generator emits."""
    index = 0
    decoder = json.JSONDecoder()

    def item():
        nonlocal index
        while index < len(source) and source[index].isspace():
            index += 1
        require(index < len(source), 'COMPOSITE_DENY_GRAMMAR', 'Unexpected end of policy')
        if source[index] == '(':
            index += 1; values = []
            while True:
                while index < len(source) and source[index].isspace():
                    index += 1
                require(index < len(source), 'COMPOSITE_DENY_GRAMMAR', 'Unclosed form')
                if source[index] == ')':
                    index += 1
                    return values
                values.append(item())
        if source[index] == '"':
            value, length = decoder.raw_decode(source[index:])
            index += length
            return ('string', value)
        start = index
        while index < len(source) and not source[index].isspace() and source[index] not in '()':
            index += 1
        require(index > start, 'COMPOSITE_DENY_GRAMMAR', 'Invalid token')
        return source[start:index]

    result = []
    while index < len(source):
        if source[index:].isspace():
            break
        result.append(item())
    return result


def _filter(value):
    require(isinstance(value, list) and value, 'COMPOSITE_DENY_GRAMMAR', 'Expected a literal filter')
    if value[0] in ('subpath', 'literal'):
        require(len(value) == 2 and isinstance(value[1], tuple) and value[1][0] == 'string'
                and value[1][1].startswith('/') and '\x00' not in value[1][1],
                'COMPOSITE_DENY_GRAMMAR', 'Expected an absolute literal path')
    else:
        require(value[0] in ('require-all', 'require-any', 'require-not') and len(value) >= 2
                and (value[0] != 'require-not' or len(value) == 2),
                'COMPOSITE_DENY_GRAMMAR', 'No code, includes, macros or grants in the deny fragment')
        for child in value[1:]:
            _filter(child)


def compose(native_profile, native_sha256, outer_profile, outer_sha256):
    require(isinstance(native_profile, str) and isinstance(outer_profile, str)
            and sha(native_profile.encode()) == native_sha256 and sha(outer_profile.encode()) == outer_sha256,
            'COMPOSITE_PROFILE_DRIFT', 'Both policy byte strings must match frozen witnesses')
    require(native_profile.startswith('(version 1)') and outer_profile.startswith(HEADER),
            'COMPOSITE_PROFILE_VERSION', 'Expected frozen v1 native and controller profiles')
    denies = outer_profile[len(HEADER):]
    forms = _forms(denies)
    require(forms, 'COMPOSITE_DENY_GRAMMAR', 'An empty controller boundary is not admitted')
    for form in forms:
        require(isinstance(form, list) and len(form) >= 2 and form[0] == 'deny',
                'COMPOSITE_DENY_GRAMMAR', 'Only explicit denies may be appended to the native policy')
        pos = 1
        while pos < len(form) and isinstance(form[pos], str):
            require(form[pos] in OPERATIONS, 'COMPOSITE_DENY_GRAMMAR', 'Unsupported operation')
            pos += 1
        require(pos > 1, 'COMPOSITE_DENY_GRAMMAR', 'Missing denied operation')
        for value in form[pos:]:
            _filter(value)
    # In particular, never append the controller's allow-default header: that
    # would reopen operations denied by the original native default policy.
    result = native_profile + '\n; memory-e2e explicit deny boundary\n' + denies
    return {'profile': result, 'profile_sha256': sha(result.encode()),
            'native_sha256': native_sha256, 'outer_sha256': outer_sha256,
            'native_bytes_preserved': True, 'controller_grants_appended': False,
            'automatic_consolidation_admitted': False}

"""Freeze available real Drivers without silently selecting a model or account."""
import re
from pathlib import Path

from .batch import default_profiles, MEMORY_UI_LOCK
from .machine import machine_identity, kernel_identity, node_identity
from .io import publish, sha


def driver_dependencies(entry, repository):
    """Freeze the local import closure and sibling launchers, excluding installed dependencies.

    Native launchers reference Swift helpers and scripts with literal filenames.
    Their package/lock manifests are included; node_modules are not source inputs.
    """
    repository = Path(repository).resolve()
    pending, found = [Path(entry).resolve()], set()
    while pending:
        path = pending.pop()
        if path in found:
            continue
        if not path.is_relative_to(repository) or 'node_modules' in path.parts:
            continue
        if not path.is_file() or path.is_symlink():
            raise ValueError(f'Invalid Driver dependency: {path}')
        found.add(path)
        for parent in path.parents:
            if not parent.is_relative_to(repository):
                break
            for name in ('package.json', 'package-lock.json'):
                manifest = parent / name
                if manifest.is_file():
                    found.add(manifest)
        if path.suffix not in {'.mjs', '.js', '.cjs'}:
            continue
        source = path.read_text()
        # Literal imports and relative/sibling filenames passed to native launchers.
        literals = re.findall(r'''["']([^"'\n]+\.(?:mjs|js|cjs|swift|py|json))["']''', source)
        for literal in literals:
            if literal.startswith(('node:', 'http:', 'https:')):
                continue
            dependency = (path.parent / literal).resolve()
            if 'node_modules' in dependency.parts:
                owner = Path(*dependency.parts[:dependency.parts.index('node_modules')])
                for name in ('package.json', 'package-lock.json'):
                    manifest = owner / name
                    if manifest.is_file():
                        found.add(manifest)
                continue
            if dependency.is_file():
                pending.append(dependency)
            elif literal.startswith(('./', '../')):
                raise ValueError(f'Missing literal Driver dependency: {literal} in {path}')
    return {str(path): sha(path.read_bytes()) for path in sorted(found)}


def native_profiles(output, astudio_boundary_lease=None):
    root = Path(__file__).resolve().parents[1]
    profiles = default_profiles()
    gates = {"AstronStudio": "eligible_idle_history_and_two_phase_completion",
             "WorkBuddy": "nightly_summary_or_verified_explicit_update",
             "QwenWork": "verified_native_write_or_declared_behavior_window",
             "DoubaoWork": "active_native_profile_and_explicit_or_periodic_update"}
    machine = machine_identity()
    node = node_identity()
    if int(node['version'].split('.')[0].lstrip('v')) < 22:
        raise ValueError('Native memory Drivers require Node >=22')
    for harness in profiles:
        profiles[harness]['machine'] = machine
        profiles[harness]['node_runtime'] = node
        # A real canary attempted to search another client's memory despite the
        # frozen Prompt. A Prompt is not a filesystem access control boundary.
        # Default profiles fail closed. AStudio may bind a separately verified
        # live backend Seatbelt lease below; other clients remain blocked.
        profiles[harness]['non_target_memory_boundary'] = {
            'required': True, 'status': 'not_enforced',
            'admitted_adapter': None, 'policy': 'deny_non_target_memory_access'}
        profiles[harness]['ui_lock_path'] = str(MEMORY_UI_LOCK)
        profiles[harness]["driver_timeout_seconds"] = 180
        profiles[harness]["state_observation"] = True
        profiles[harness]["targeted_cleanup_verified"] = False
        profiles[harness]["pre_send_retry"] = harness in {'QwenWork', 'DoubaoWork'}
        profiles[harness]["memory_protocol"] = {
            "purpose": "immediate_automation_smoke", "formal_scoring_allowed": False,
            "requires_enabled_memory": harness == 'AstronStudio',
            "formation_gate": gates[harness], "formation_verified": False,
            "interpretation": "A short behavior window validates automation, not completed automatic memory formation"}
    for harness, filename in (("WorkBuddy", "workbuddy.mjs"), ("QwenWork", "qwenwork.mjs"),
                              ("DoubaoWork", "doubaowork.mjs"), ("AstronStudio", "astronstudio.mjs")):
        driver = root / "eval_memory_e2e/native" / filename
        if driver.is_file():
            profiles[harness]["driver_command"] = ["node", str(driver)]
            profiles[harness]["driver_sources"] = driver_dependencies(driver, root)
            profiles[harness]["driver_source_scope"] = "local-dependency-closure/v1"
            profiles[harness]["isolation"] = "shared_account_cold_first"
    profiles['AstronStudio']['pre_click_rpc_wait_seconds'] = 30
    profiles['AstronStudio']['pre_click_focus_wait_seconds'] = 60
    profiles['AstronStudio']['driver_timeout_seconds'] = 300
    profiles['AstronStudio']['cdp_timeout_ms'] = 30000
    profiles['AstronStudio']['native_acceptance_wait_seconds'] = 120
    if Path('/Applications/AStudio.app').is_dir():
        profiles['AstronStudio']['kernel'] = kernel_identity()
    if astudio_boundary_lease is not None:
        from .os_boundary import frozen_boundary, load_lease, BRIDGE, GUARD, LAUNCHER
        profiles['AstronStudio']['non_target_memory_boundary'] = frozen_boundary(astudio_boundary_lease)
        profiles['AstronStudio']['memory_protocol']['automatic_generation_compatible'] = False
        profiles['AstronStudio']['driver_sources'].update({str(p):sha(p.read_bytes()) for p in (BRIDGE,GUARD,LAUNCHER)})
        unit = load_lease(astudio_boundary_lease).get('astudio_scope')
        if unit is not None:
            from .astudio_scope import SELF, attest, load
            from .io import require
            condition = load(unit['scope'], unit)['memory_condition']
            require(condition['generate_memories'] is False, 'SCOPE_AUTOMATIC_NOT_ADMITTED',
                    'Native automatic consolidation cannot nest Seatbelt; explicit-memory isolation only')
            attest(unit, profiles['AstronStudio']['non_target_memory_boundary'])
            profiles['AstronStudio']['astudio_scope'] = unit
            profiles['AstronStudio']['isolation'] = 'verified_namespace'
            profiles['AstronStudio']['driver_sources'][str(SELF)] = sha(SELF.read_bytes())
            idle = SELF.parent / 'native/astudio-unit-idle.mjs'
            profiles['AstronStudio']['driver_sources'][str(idle)] = sha(idle.read_bytes())
            profiles['AstronStudio']['memory_protocol']['purpose'] = 'explicit_memory_case_repeat_isolation'
    publish(output, profiles)
    return {"output": str(output), "configured_harnesses": [name for name, value in profiles.items() if value["driver_command"]],
            "memory_admission": "requires_live_scoped_preflight",
            "os_boundary_admitted_harnesses": ['AstronStudio'] if astudio_boundary_lease is not None else []}

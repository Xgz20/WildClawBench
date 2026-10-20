"""Public/private preparation and immutable, scoped experiment plans."""

from __future__ import annotations

import sys
from uuid import uuid4
from pathlib import Path

from . import CONTRACT, HARNESS_PORTS, EXECUTION_GUARD, execution_guard
from .dataset import load_dataset, materialize
from .io import digest, encoded, identifier, publish, read_json, require, safe_file, sha, timestamp

from .machine import machine_paths, machine_identity, kernel_identity, node_identity

MEMORY_UI_LOCK = machine_paths()['ui_lock']


def memory_ui_lock_path(root, profiles):
    paths = set()
    for profile in profiles.values():
        value = profile.get('ui_lock_path')
        require(value is None or value == str(MEMORY_UI_LOCK), 'UI_LOCK_POLICY', 'Only the shared memory UI lock is admitted')
        paths.add(Path(value) if value is not None else Path(root).absolute().parent / '.memory-native-ui.lock')
    require(len(paths) == 1, 'UI_LOCK_POLICY', 'All Harnesses must use the same frozen UI lock')
    return next(iter(paths))


def default_profiles():
    return {name: {"profile_id": name + "-current-account", "account_policy": "current_signed_in_account",
                   "reset_policy": "synthetic_test_facts_only", "driver_command": None,
                   "expected_config": None, "isolation": "unverified", "memory_wait_seconds": 10,
                   "execution_guard_policy": "controller_per_scenario"}
            for name in HARNESS_PORTS}


def prepare(root, *, batch_id, seed, repeats=1, harnesses=None, scenario_ids=None,
            mode="native", profiles=None, judge=None, dataset_path=None):
    root = Path(root).absolute()
    identifier(batch_id)
    require(type(repeats) is int and 1 <= repeats <= 20, "INVALID_REPEATS", "Expected 1..20")
    require(mode in {"native", "fixture"}, "INVALID_MODE", mode)
    require(isinstance(seed, str) and seed.strip(), "INVALID_SEED", "Explicit seed required")
    require(not root.exists(), "OUTPUT_EXISTS", str(root))
    for ancestor in root.parents:
        require(not ancestor.is_symlink(), "SYMLINK_REJECTED", str(ancestor))
    dataset = load_dataset() if dataset_path is None else load_dataset(dataset_path)
    harnesses = list(HARNESS_PORTS) if harnesses is None else harnesses
    scope = [case["id"] for case in dataset["scenarios"]] if scenario_ids is None else scenario_ids
    require(harnesses and len(set(harnesses)) == len(harnesses) and set(harnesses) <= set(HARNESS_PORTS),
            "HARNESS_SCOPE", "Unknown or duplicate Harness")
    require(scope and len(set(scope)) == len(scope)
            and set(scope) <= {case["id"] for case in dataset["scenarios"]},
            "SCENARIO_SCOPE", "Unknown, empty or duplicate scenario scope")
    profiles = default_profiles() if profiles is None else profiles
    require(set(harnesses) <= set(profiles), "PROFILE_SCOPE", "Each selected Harness requires a profile")
    for harness in harnesses:
        profile = profiles[harness]
        if profile.get('astudio_scope') is not None:
            require(harnesses == ['AstronStudio'] and mode == 'native', 'SCOPE_HARNESS', 'AStudio native units only')
            from .astudio_scope import bind_batch
            bind_batch(profile, root, profile['astudio_scope']['scope'], scope, repeats)
        if profile.get('machine') is not None:
            require(profile['machine'] == machine_identity(), 'MACHINE_DRIFT', 'Create a new local native Profile')
        if profile.get('kernel') is not None:
            require(harness == 'AstronStudio' and profile['kernel'] == kernel_identity(), 'KERNEL_DRIFT', 'Create a new local native Profile')
        if profile.get('node_runtime') is not None:
            require(profile['node_runtime'] == node_identity(), 'NODE_DRIFT', 'Create a new local native Profile')
        identifier(profile["profile_id"])
        require(profile.get("account_policy") == "current_signed_in_account"
                and profile.get("reset_policy") == "synthetic_test_facts_only",
                "PROFILE_POLICY", "Only this run's synthetic facts may be cleaned up")
        command = profile.get("driver_command")
        wait = profile.get("memory_wait_seconds", 10)
        require(type(wait) in {int, float} and 0 <= wait <= 300, "MEMORY_WAIT", "Observation window must be 0..300 seconds")
        require(command is None or (isinstance(command, list) and command
                and all(isinstance(part, str) and part for part in command)),
                "DRIVER_COMMAND", "driver_command must be an argv array, never a shell string")
        if mode == "native" and command is not None:
            sources = profile.get("driver_sources")
            require(isinstance(sources, dict) and sources, "DRIVER_SOURCE_REQUIRED", "Freeze native Driver source hashes")
            for source, checksum in sources.items():
                require(sha(safe_file(source).read_bytes()) == checksum, "DRIVER_SOURCE_DRIFT", source)
    for case in dataset['scenarios']:
        if case['id'] not in scope:
            continue
        formation = case.get('learning', {}).get('formation', {})
        if mode == 'native' and formation.get('kind') == 'native_event':
            require(False, 'FORMATION_ADAPTER_NOT_ADMITTED',
                    'Native-event gates can be declared in v2 but have no admitted execution adapter yet')
    memory_ui_lock_path(root, {h: profiles[h] for h in harnesses})
    judge = judge or {"protocol": "memory-checkpoint-review/v1", "model": None, "reasoning": None}
    require(judge.get("protocol") == "memory-checkpoint-review/v1", "JUDGE_PROTOCOL", "Unsupported judge")
    root.mkdir(parents=True)
    experiment_id = uuid4().hex
    private, inputs, episodes, guard_hashes = {}, {}, [], {}
    first_repetition = profiles.get('AstronStudio', {}).get('astudio_scope', {}).get('repetition', 1)
    for run in range(first_repetition, first_repetition + repeats):
        for case in dataset["scenarios"]:
            if case["id"] not in scope:
                continue
            variant = materialize(case, f"{seed}:{experiment_id}", run)
            guard = execution_guard(case.get('learning', {}).get('mode', 'explicit'))
            if mode == 'native':
                guard_hashes[case['id']] = sha(guard.encode())
            private_key = f"{case['id']}/r{run:02d}"
            private[private_key] = variant
            for harness in harnesses:
                # Fixed cold-first scheduling is explicit when sharing a logged-in account.
                for arm in ("C0", "M+"):
                    arm_id = "cold" if arm == "C0" else "experienced"
                    episode_id = f"{harness}__{case['id']}__r{run:02d}__{arm_id}"
                    relative = f"public/{episode_id}/steps.json"
                    cold_ids = case.get('conditions', {}).get('C0', {}).get('probe_steps')
                    chosen = [step for step in variant["steps"] if arm == "M+" or
                              (step['id'] in cold_ids if cold_ids is not None else step["phase"] == "probe")]
                    chosen = [{**step, "session": "new" if index == 0 and arm == "C0"
                               and step["session"] != "restart_new" else step["session"]}
                              for index, step in enumerate(chosen)]
                    if mode == "native":
                        chosen = [{**step, "prompt": guard + "\n\n" + step["prompt"]} for step in chosen]
                    plan = {"episode_id": episode_id, "steps": chosen}
                    if 'learning' in variant:
                        plan['learning'] = variant['learning']
                    publish(root / relative, plan)
                    inputs[relative] = digest(plan)
                    for fixture in variant["fixtures"]:
                        identifier(fixture)
                        asset = dataset.get('fixture_assets', {}).get(fixture)
                        data = safe_file(Path(dataset_path).parent / asset['path'], Path(dataset_path).parent).read_bytes() if asset else safe_file(Path(__file__).with_name("fixtures") / fixture).read_bytes()
                        source = f"public/{episode_id}/materials/{fixture}"
                        publish(root / source, data)
                        inputs[source] = sha(data)
                    episodes.append({"id": episode_id, "harness": harness, "scenario_id": case["id"],
                                     "dimension": case["dimension"], "run": run, "arm": arm,
                                     "private_key": private_key, "plan_path": relative,
                                     "namespace": "memory-" + digest({"experiment_id": experiment_id, "episode_id": episode_id})[:24],
                                     "workspaces": {scope_id: str(root / "candidate" / episode_id / scope_id)
                                                    for scope_id in variant.get('scopes', ("A", "B"))}})
    private_path = "private/scenarios.json"
    publish(root / private_path, private)
    inputs[private_path] = digest(private)
    for relative, checksum in dataset.get("source_assets", {}).items():
        source = Path(dataset_path).parent / relative
        private_relative = "private/source/" + relative
        publish(root / private_relative, safe_file(source, Path(dataset_path).parent).read_bytes())
        inputs[private_relative] = checksum
    runtime_sources = {str(path): sha(path.read_bytes()) for path in Path(__file__).parent.rglob("*.py")}
    for profile in profiles.values():
        runtime_sources.update(profile.get("driver_sources", {}))
    for source, checksum in runtime_sources.items():
        target = root / "runtime-source" / checksum
        if not target.exists():
            publish(target, safe_file(source).read_bytes())
    manifest = {"contract": CONTRACT, "batch_id": batch_id, "experiment_id": experiment_id,
                "created_at": timestamp(), "mode": mode, "failure_policy": "stop_batch",
                "scheduling_policy": "strict_harness_serial",
                "dataset_id": dataset["dataset_id"], "dataset_sha256": digest(dataset), "seed": seed,
                "source_composition": dataset.get("composition", {"self_constructed": len(dataset['scenarios'])}),
                "repeats": repeats, "harnesses": harnesses, "scenario_ids": scope, "arms": ["C0", "M+"],
                "profiles": {key: profiles[key] for key in harnesses}, "judge": judge,
                "baseline": "cold_first_shared_account", "causal_claim": "historical_experience_only",
                "memory_channel_policy": "product_default_with_observed_workspace",
                "execution_guard_sha256": next(iter(guard_hashes.values())) if len(set(guard_hashes.values())) == 1 else None,
                "execution_guards": guard_hashes,
                "implementation": {str(path.relative_to(Path(__file__).parent)): sha(path.read_bytes())
                                   for path in sorted(Path(__file__).parent.rglob("*.py"))},
                "inputs": inputs, "episodes": episodes}
    if profiles.get('AstronStudio', {}).get('astudio_scope'):
        manifest['first_repetition'] = first_repetition
    if mode == "fixture":
        manifest["profiles"] = {key: {**manifest["profiles"][key], "driver_command":
                                     [sys.executable, "-m", "eval_memory_e2e.fixture_driver"],
                                     "isolation": "fixture_only"} for key in harnesses}
        manifest["judge"] = {"protocol": "memory-checkpoint-review/v1", "model": "fixture-judge", "reasoning": "none"}
    publish(root / "manifest.json", manifest)
    publish(root / "manifest.sha256", (digest(manifest) + "\n").encode())
    return {"root": str(root), "mode": mode, "episode_count": len(episodes), "manifest_sha256": digest(manifest)}


def load_batch(root, *, harness=None, episode_id=None):
    root = Path(root).absolute()
    manifest = read_json(safe_file(root / "manifest.json", root))
    expected = safe_file(root / "manifest.sha256", root).read_text().strip()
    require(manifest.get("contract") == CONTRACT and digest(manifest) == expected,
            "MANIFEST_DRIFT", str(root))
    from .runtime_repair import effective_sources
    implementation, drivers, _, _ = effective_sources(root, manifest)
    for name, profile in manifest['profiles'].items():
        if profile.get('astudio_scope') is not None:
            from .astudio_scope import load
            unit = load(profile['astudio_scope']['scope'], profile['astudio_scope'])
            require(str(Path(root).absolute()) == unit['batch_root']
                    and manifest['scenario_ids'] == [unit['case_id']] and manifest['repeats'] == 1
                    and manifest.get('first_repetition') == unit['repetition']
                    and all(item['run'] == unit['repetition'] for item in manifest['episodes']),
                    'SCOPE_BATCH_BINDING', 'Frozen unit does not belong to this batch')
        if profile.get('machine') is not None:
            require(profile['machine'] == machine_identity(), 'MACHINE_DRIFT', 'Frozen Profile belongs to another host or runtime')
        if profile.get('kernel') is not None:
            require(name == 'AstronStudio' and profile['kernel'] == kernel_identity(), 'KERNEL_DRIFT', 'Installed kernel changed')
        if profile.get('node_runtime') is not None:
            require(profile['node_runtime'] == node_identity(), 'NODE_DRIFT', 'Frozen Node runtime changed')
    for relative, checksum in implementation.items():
        source = safe_file(Path(__file__).parent / relative, Path(__file__).parent)
        require(sha(source.read_bytes()) == checksum, "IMPLEMENTATION_DRIFT", relative)
    if episode_id is not None:
        selected = episode(manifest, episode_id)["harness"]
        require(harness is None or harness == selected, "HARNESS_SCOPE", "Conflicting source scope")
        harness = selected
    require(harness is None or harness in manifest["harnesses"], "HARNESS_SCOPE", str(harness))
    for name, sources in drivers.items():
        if harness is not None and name != harness:
            continue
        for source, checksum in sources.items():
            require(sha(safe_file(source).read_bytes()) == checksum, "DRIVER_SOURCE_DRIFT", source)
    for relative, checksum in manifest["inputs"].items():
        path = Path(relative)
        require(not path.is_absolute() and ".." not in path.parts, "PATH_ESCAPE", relative)
        require(sha(safe_file(root / relative, root).read_bytes()) == checksum,
                "INPUT_DRIFT", relative)
    return manifest


def episode(manifest, episode_id):
    found = [item for item in manifest["episodes"] if item["id"] == episode_id]
    require(len(found) == 1, "EPISODE_SCOPE", episode_id)
    return found[0]


def operation_id(manifest, episode_id, step_id):
    return "op-" + digest({"experiment_id": manifest["experiment_id"], "episode_id": episode_id,
                           "step_id": step_id, "execution_attempt_id": "a01"})

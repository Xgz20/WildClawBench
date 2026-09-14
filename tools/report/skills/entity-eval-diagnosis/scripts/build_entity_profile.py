"""Legacy import/CLI entrypoint. New discovery name: harness-model-diagnosis.

No second SKILL.md is kept here. Historical analysis scripts can still import
build_profile, summarize, token_components, contract_state and fingerprint.
Schema v2 returns null for incomplete totals instead of misleading zeros.
"""
import importlib.util
from pathlib import Path

_path = Path(__file__).resolve().parents[2] / "harness-model-diagnosis/scripts/build_diagnosis_profile.py"
_spec = importlib.util.spec_from_file_location("harness_model_profile_compat", _path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
globals().update({key: value for key, value in vars(_module).items() if not key.startswith("_")})

if __name__ == "__main__":
    _module.main()

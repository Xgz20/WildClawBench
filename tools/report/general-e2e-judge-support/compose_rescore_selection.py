"""Compatibility import/launcher for the distributed orchestration entrypoint."""
from pathlib import Path
import runpy
_path=Path(__file__).resolve().parents[1]/'skills/general-e2e/orchestrate-general-e2e/scripts/compose_rescore_selection.py'
if __name__=='__main__':runpy.run_path(str(_path),run_name='__main__')
else:
    _api=runpy.run_path(str(_path))
    plan_selection=_api['plan_selection']
    compose=_api['compose']

"""Compatibility launcher; canonical implementation ships with score-general-e2e."""
from pathlib import Path
import runpy
if __name__ == '__main__':
    runpy.run_path(str(Path(__file__).resolve().parents[1]/'skills/general-e2e/score-general-e2e/scripts/offline_browser_validate.py'),run_name='__main__')

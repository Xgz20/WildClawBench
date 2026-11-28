#!/usr/bin/env python3
"""Offline synthetic checks for the scorer image; never invokes a model."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
import subprocess
import sys
import tempfile

RUNTIME = Path('/opt/scoring-runtime')
SKILL = Path('/opt/runtime-score-skill')


def browser_directory() -> str:
    path = Path(os.environ.get('PLAYWRIGHT_BROWSERS_PATH', ''))
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        raise RuntimeError('SCORER_BROWSER_DIRECTORY_INVALID: ' + str(path))
    return str(path.resolve(strict=True))


def run(argv: list[str], *, env: dict | None = None) -> str:
    return subprocess.run(argv, env=env, check=True, capture_output=True,
                          text=True, timeout=120).stdout.strip()


def office_smoke(root: Path) -> dict:
    from docx import Document
    import openpyxl
    import fitz

    # Match the minimal environment used by rule workers (no inherited keys).
    env = {'PATH': str(RUNTIME / 'bin'), 'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1',
           'PYTHONUTF8': '1', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'}
    office = str(RUNTIME / 'bin/soffice')
    document = Document()
    document.add_paragraph('SCORER_WORD_SMOKE 中文办公验证')
    document.save(root / 'word.docx')
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(['SCORER_CALC_SMOKE 中文表格', 'Value'])
    sheet.append(['A', 19])
    sheet.append(['B', 23])
    sheet.append(['Total', '=SUM(B2:B3)'])
    sheet.column_dimensions['A'].width = 42
    workbook.save(root / 'calc.xlsx')
    # Flat ODF is only a fixture generator. The actual tested input is PPTX.
    presentation = root / 'slides.fodp'
    presentation.write_text('''<?xml version="1.0" encoding="UTF-8"?>
<office:document xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
 xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0"
 office:version="1.2" office:mimetype="application/vnd.oasis.opendocument.presentation">
 <office:body><office:presentation><draw:page draw:name="Smoke">
 <draw:frame svg:x="1cm" svg:y="1cm" svg:width="22cm" svg:height="5cm">
 <draw:text-box><text:p>SCORER_SLIDES_SMOKE 中文演示验证</text:p></draw:text-box>
 </draw:frame></draw:page></office:presentation></office:body></office:document>''', encoding='utf-8')
    run([office, '--headless', '--convert-to', 'pptx', '--outdir', str(root), str(presentation)], env=env)
    rows = {}
    for name, marker in [('word.docx', 'SCORER_WORD_SMOKE'), ('calc.xlsx', 'SCORER_CALC_SMOKE'),
                         ('slides.pptx', 'SCORER_SLIDES_SMOKE')]:
        source = root / name
        if not source.is_file():
            raise RuntimeError(f'OFFICE_FIXTURE_NOT_CREATED: {name}')
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        run([office, '--headless', '--convert-to', 'pdf', '--outdir', str(root), str(source)], env=env)
        pdf = source.with_suffix('.pdf')
        with fitz.open(pdf) as rendered:
            text = ''.join(page.get_text() for page in rendered)
            if rendered.page_count < 1 or marker not in text or '中文' not in text:
                raise RuntimeError(f'OFFICE_RENDER_INVALID: {name}')
            if name == 'calc.xlsx' and '42' not in text:
                raise RuntimeError('OFFICE_CALC_FORMULA_NOT_RECALCULATED')
            for index, page in enumerate(rendered):
                page.get_pixmap().save(root / f'{source.stem}-{index + 1}.png')
            rows[name] = {'pages': rendered.page_count, 'marker_found': True, 'chinese_text_found': True,
                          'source_sha256': before, 'pdf_sha256': hashlib.sha256(pdf.read_bytes()).hexdigest()}
        if hashlib.sha256(source.read_bytes()).hexdigest() != before:
            raise RuntimeError(f'OFFICE_SOURCE_CHANGED: {name}')
    font = run(['/usr/bin/fc-match', '-f', '%{family}', 'Noto Sans CJK SC'])
    if 'Noto Sans CJK' not in font:
        raise RuntimeError('CJK_FONT_UNAVAILABLE')
    return {'status': 'PASS', 'version': run([office, '--version'], env=env), 'cjk_font': font,
            'formats': rows, 'calc_formula_result': 42}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--office', action='store_true')
    parser.add_argument('--codex-version')
    parser.add_argument('--dsh-version')
    parser.add_argument('--claude-code-version')
    parser.add_argument('--platform', choices=['linux/amd64', 'linux/arm64'])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--evidence-dir', type=Path)
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 11) or sys.prefix != str(RUNTIME):
        raise RuntimeError('MANAGED_PYTHON_MISMATCH')
    browsers = browser_directory()
    manifest = json.loads(Path('/opt/scorer-build-manifest.json').read_text())
    inputs = manifest['inputs']
    machine = {'x86_64': 'amd64', 'aarch64': 'arm64'}.get(platform.machine(), platform.machine())
    observed_platform = sys.platform + '/' + machine
    expected_platform = args.platform or inputs.get('PLATFORM')
    if expected_platform and observed_platform != expected_platform:
        raise RuntimeError(f'SCORER_PLATFORM_MISMATCH: expected {expected_platform}, got {observed_platform}')
    codex = run(['codex', '--version'])
    dsh = run(['dsh', '--version'])
    if codex.split()[-1] != (args.codex_version or inputs['CODEX_VERSION']):
        raise RuntimeError('CODEX_VERSION_MISMATCH: ' + codex)
    if (args.dsh_version or inputs['DSH_VERSION']) not in dsh.split():
        raise RuntimeError('DSH_VERSION_MISMATCH: ' + dsh)
    claude = run(['claude', '--version'])
    if claude.split()[0] != (args.claude_code_version or inputs['CLAUDE_CODE_VERSION']):
        raise RuntimeError('CLAUDE_CODE_VERSION_MISMATCH: ' + claude)
    with tempfile.TemporaryDirectory(prefix='scorer-runtime-smoke-') as temporary:
        root = args.evidence_dir or Path(temporary)
        root.mkdir(parents=True, exist_ok=True)
        browser = root / 'browser'
        run([sys.executable, str(SKILL / 'scripts/offline_browser_validate.py'),
             '--probe', '--output-dir', str(browser)])
        result = {'schema_version': 'wildclawbench.scorer-runtime-validation/v1', 'status': 'PASS',
                  'platform': observed_platform,
                  'python': sys.version.split()[0], 'codex': codex, 'dsh': dsh, 'claudecode': claude,
                  'source_revision': manifest['source_revision'], 'skill': manifest['skill'],
                  'browser_directory': browsers,
                  'browser': json.loads((browser / 'observations.json').read_text()),
                  'office': office_smoke(root) if args.office else None}
    data = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(data, encoding='utf-8')
    print(data)


if __name__ == '__main__':
    main()

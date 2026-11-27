"""Exact-source compatibility for path *fields* in frozen private checkers.

No candidate file or rule source is edited. Only reviewed parser arguments are
translated, only inside the selected workspace/gt, only for matching SHA256s.
The isolated worker is single-task; the runpy hook is restored on every exit.
"""
from contextlib import contextmanager
from functools import wraps
import hashlib
from pathlib import Path
import re
import runpy

PROFILE = "wildclawbench.frozen-rule-path-aliases/v1"
PARSERS = {
    ('check_visual_mapping.py', 'a5af7b92e4de64e499cf398dbd747778db5091234c684705ddb25630e666f5ea'): ('relative',),
    ('native_io.py', '06688f16d24be0ff0a461e192a71081f24f463df080b60aae85dc0898d00daee'): ('npath',),
    ('native_io.py', '808541250bca622058791ec778420ebdb7fc84a61cd33ebf26cc7486e7fbd3d0'): ('path_value',),
    ('native_io.py', '53cf6c54917be374efbf1833e5af1351fd3ce8a8466db84fbd04906095ec744d'): ('path_value',),
    ('native_io.py', 'c64ae8d109025e9d0239ac2c553cd6a1bfa7c7563632090f07c2c3da226ce0d8'): ('path_value',),
    ('native_io.py', 'a432fb1dbb8a77ff83f6989c4d0dc5003ad0293717d55a30ef02786735a671d1'): ('relative',),
    ('financial_io.py', '78455fef542e996d63a7a04aad55a23c680d5ca9fae2017283928f6c281b0af4'): ('source_path',),
    ('structured_io.py', '63beb74d485649582dba3abd2ec49a8dc42199ac497ea4a9de537a5ab8edbc92'): ('tokens',),
    ('structured_io.py', 'bb721f78ca09c4e18518be7832fa5de79ad4a896f881bceff7e895c5dd170989'): ('parse_refs',),
    ('structured_io.py', '7820ac3d0c65acfb8effbbe51039344083f030e57c672bc65395dc08c03573b2'): ('image_name',),
    ('common_io.py', '94046a30972358af99b02f54357e96f17f8f144a10f11e90cd13eb0ef2bd70cf'): ('output_path',),
}
_ROOT = re.compile(r"(?<![A-Za-z0-9_./:\\-])C:/(?:ProgramData/WGUI/workspace/project|tmp_workspace)(?=/)", re.I)


def canonical_field(value):
    if isinstance(value, list):
        return [canonical_field(item) for item in value]
    if not isinstance(value, str):
        return value
    normalized = value.replace("\\", "/")
    mapped, count = _ROOT.subn("/tmp_workspace", normalized)
    return mapped if count else value


@contextmanager
def rule_path_aliases(workspace):
    root = (Path(workspace).resolve() / "gt")
    original = runpy.run_path
    observations = {}

    def load(path_name, *args, **kwargs):
        namespace = original(path_name, *args, **kwargs)
        path = Path(path_name)
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            return namespace
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        names = PARSERS.get((path.name, sha), ())
        for name in names:
            function = namespace.get(name)
            if not callable(function):
                raise ValueError("FROZEN_PATH_PARSER_MISSING: " + name)
            key = sha + ":" + name
            receipt = observations.setdefault(key, {"helper_sha256": sha, "parser": name, "adapted_calls": 0})

            def wrap(function, name, receipt):
                @wraps(function)
                def adapted(value, *args, **kwargs):
                    if name == "tokens":
                        raw = function(value, *args, **kwargs)
                        mapped = canonical_field(raw)
                    else:
                        mapped = canonical_field(value)
                        raw = value
                    if mapped != raw:
                        receipt["adapted_calls"] += 1
                    return mapped if name == "tokens" else function(mapped, *args, **kwargs)
                return adapted

            adapted = wrap(function, name, receipt)
            function.__globals__[name] = adapted
            namespace[name] = adapted
        return namespace

    runpy.run_path = load
    try:
        yield observations
    finally:
        runpy.run_path = original

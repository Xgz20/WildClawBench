"""Declared pure-function replay profile; this is not an OS security sandbox."""
import ast
import builtins
import importlib
import __future__

PROFILE = 'h050-pure-api/v1'
ALLOWED_IMPORTS = {'collections', 'itertools', 'functools'}
FORBIDDEN_NAMES = {'open', 'exec', 'eval', 'compile', '__import__', 'globals', 'locals', 'vars', 'getattr', 'setattr',
                   'delattr', 'dir', 'breakpoint', 'help', 'input', 'type', 'object', 'super', 'property', 'classmethod', 'staticmethod'}
SAFE_BUILTINS = ('hash', 'map', 'filter', 'slice', 'len', 'range', 'enumerate', 'zip', 'min', 'max', 'sum', 'all', 'any', 'sorted', 'reversed', 'iter', 'next',
                 'list', 'tuple', 'dict', 'set', 'frozenset', 'bool', 'int', 'float', 'str', 'isinstance', 'abs', 'round',
                 'ValueError', 'TypeError', 'KeyError', 'IndexError', 'Exception', 'StopIteration')

class ProfileUnsupported(RuntimeError):
    pass

def _immutable(value):
    return value is None or isinstance(value, (str, int, float, bool, bytes)) or isinstance(value, tuple) and all(_immutable(x) for x in value)

def _literal(node):
    try:
        return _immutable(ast.literal_eval(node))
    except (ValueError, TypeError, SyntaxError):
        return False

def validate_source(raw):
    if len(raw) > 65536:
        raise ProfileUnsupported('source exceeds declared 64 KiB profile')
    tree = ast.parse(raw.decode('utf-8-sig'), filename='<h050-candidate>')
    for top in tree.body:
        if isinstance(top, (ast.FunctionDef, ast.Import, ast.ImportFrom)):
            continue
        if isinstance(top, ast.Expr) and isinstance(top.value, ast.Constant) and isinstance(top.value.value, str):
            continue
        if isinstance(top, (ast.Assign, ast.AnnAssign)) and top.value is not None and _literal(top.value):
            continue
        raise ProfileUnsupported('module scope must contain functions, imports and immutable literal constants')
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.AsyncFunctionDef, ast.AsyncFor, ast.AsyncWith, ast.Await, ast.Global, ast.Nonlocal)):
            raise ProfileUnsupported('unsupported pure profile form: ' + type(node).__name__)
        if isinstance(node, ast.Name) and (node.id.startswith('__') or node.id in FORBIDDEN_NAMES):
            raise ProfileUnsupported('reflection/IO/interpreter name outside declared profile: ' + node.id)
        if isinstance(node, ast.Attribute) and (node.attr.startswith('_') or node.attr in {'format', 'format_map'} or isinstance(node.ctx, (ast.Store, ast.Del))):
            raise ProfileUnsupported('private attribute or attribute mutation outside declared profile')
        if isinstance(node, ast.FunctionDef):
            if node.name.startswith('__') or node.decorator_list or not all(_literal(value) for value in (*node.args.defaults, *(x for x in node.args.kw_defaults if x is not None))):
                raise ProfileUnsupported('decorators or mutable/dynamic defaults outside declared profile')
        if isinstance(node, ast.Import):
            if any(alias.name not in ALLOWED_IMPORTS or alias.asname and alias.asname.startswith('_') for alias in node.names):
                raise ProfileUnsupported('import outside declared profile')
        if isinstance(node, ast.ImportFrom):
            if node.module == '__future__' and node.level == 0 and all(alias.name == 'annotations' for alias in node.names):
                continue
            if node.level or node.module not in ALLOWED_IMPORTS or any(alias.name.startswith('_') or alias.name == '*' for alias in node.names):
                raise ProfileUnsupported('from-import outside declared profile')
    return tree

def load_source(raw):
    tree = validate_source(raw)
    def restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == '__future__' and not level and tuple(fromlist) == ('annotations',):
            return importlib.import_module(name)
        if level or name not in ALLOWED_IMPORTS or any(item.startswith('_') for item in fromlist):
            raise ProfileUnsupported('runtime import outside declared profile')
        return importlib.import_module(name)
    available = {name: getattr(builtins, name) for name in SAFE_BUILTINS}
    available['__import__'] = restricted_import
    namespace = {'__builtins__': available}
    exec(compile(tree, '<h050-candidate>', 'exec', flags=__future__.annotations.compiler_flag), namespace, namespace)
    function = namespace.get('query_records')
    if not callable(function):
        raise ValueError('query_records callable missing')
    return function

"""Use only task-owned tool libraries and install only the candidate wheel target."""
from pathlib import Path
import json
import os
import sys

mode=sys.argv[1]
if mode=='build':
    library,project,output=map(Path,sys.argv[2:5]);sys.path[:0]=[str(library),str(library/'setuptools/_vendor')];os.chdir(project)
    import setuptools
    from setuptools.build_meta import build_wheel
    if setuptools.__version__!='79.0.1':raise RuntimeError('locked backend not loaded')
    name=build_wheel(str(output));print(json.dumps({'backend_version':setuptools.__version__,'wheel':name}))
elif mode=='install':
    pip_wheel,target,wheel=map(Path,sys.argv[2:5]);sys.path.insert(0,str(pip_wheel))
    import pip
    if pip.__version__!='24.0':raise RuntimeError('locked installer not loaded')
    from pip._internal.cli.main import main
    raise SystemExit(main(['install','--no-index','--no-deps','--no-compile','--disable-pip-version-check','--no-warn-script-location','--target',str(target),str(wheel)]))
else:raise ValueError('driver mode')

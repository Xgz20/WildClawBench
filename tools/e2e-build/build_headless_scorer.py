#!/usr/bin/env python3
"""Build a reusable headless scorer from a standalone, hash-locked score Skill."""
from pathlib import Path
import argparse,json,shutil,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from src.e2e.common import load_script
from src.e2e.artifacts import extract_zip

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--context',type=Path,required=True)
 p.add_argument('--tag',required=True)
 p.add_argument('--docker-context',default='default')
 p.add_argument('--eval-base-image',default='python:3.11-bookworm')
 p.add_argument('--node-runtime-image',default='node:24-bookworm-slim')
 p.add_argument('--http-proxy')
 args=p.parse_args();target=args.context.resolve();target.mkdir(parents=True,exist_ok=True)
 builder=load_script(ROOT/'tools/e2e-build/build_skill_packages.py','headless_skill_builder')
 package_root=Path(tempfile.mkdtemp(prefix='.skill-packages-',dir=target))
 result=builder.build_skill_packages(ROOT,package_root,skill_names=['score-general-e2e'])
 skill=target/'runtime-skill'
 if skill.exists():shutil.rmtree(skill)
 extract_zip(package_root/result['skills'][0]['archive'],skill,strip_root=True)
 shutil.rmtree(package_root)
 (target/'.dockerignore').write_text('packages\n.skill-packages-*\n.env\n')
 shutil.copyfile(ROOT/'docker/e2e-scorer/Dockerfile',target/'Dockerfile')
 shutil.copyfile(ROOT/'docker/deepseek-harness/v3/wcb-dsh',target/'wcb-dsh')
 command=['docker','--context',args.docker_context,'build','--progress=plain','--tag',args.tag,
          '--build-arg','EVAL_BASE_IMAGE='+args.eval_base_image,'--build-arg','NODE_RUNTIME_IMAGE='+args.node_runtime_image]
 if args.http_proxy:
  for key in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy']:command+=['--build-arg',key+'='+args.http_proxy]
 command+=[str(target)];subprocess.run(command,check=True)
 print(json.dumps({'image':args.tag,'context':str(target),'skill':result['skills'][0]}))
if __name__=='__main__':main()

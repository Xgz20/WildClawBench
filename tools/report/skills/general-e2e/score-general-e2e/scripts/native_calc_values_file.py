"""File-based request transport for the unchanged bulk Calc observation engine."""
import argparse,json
from pathlib import Path
import native_calc_values

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['observe'])
    p.add_argument('--writer-configuration',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--locations-json',type=Path,required=True)
    p.add_argument('--output-root',type=Path,required=True)
    a=p.parse_args();locations=json.loads(a.locations_json.read_text(encoding='utf-8'))
    if not isinstance(locations,list) or any(not isinstance(x,str) for x in locations):raise ValueError('NATIVE_CALC_REQUEST_NOT_STRING_LIST')
    result=native_calc_values.run_probe(a.writer_configuration,a.source,locations,a.output_root)
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()

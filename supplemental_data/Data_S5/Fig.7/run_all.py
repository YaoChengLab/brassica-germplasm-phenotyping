#!/usr/bin/env python3
"""Rebuild Figure 7, simplified Table S7, and model checks from local inputs."""
from pathlib import Path
import argparse, hashlib, importlib.metadata, json, os, shutil, subprocess, sys

ROOT = Path(__file__).resolve().parent

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'outputs',help='Output directory (default: package/outputs)')
    args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    for name in ['data','scripts','reference']:
        if out == ROOT/name or ROOT/name in out.parents:
            raise ValueError('Output must not be inside an input, script, or reference directory')
    provenance=json.loads((ROOT/'data/provenance.json').read_text(encoding='utf-8'))
    for item in provenance['files']:
        if hashlib.sha256((ROOT/item['path']).read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError('Input/reference checksum mismatch: '+item['path'])
    env=os.environ.copy();env['MPLCONFIGDIR']=str(out/'.matplotlib')
    env['PYTHONHASHSEED']='0';env['XDG_CACHE_HOME']=str(out/'.cache');env['PYTHONIOENCODING']='utf-8'
    for case,exclude in [('all_batches',''),('without_B12_B13','2025B12,2025B13')]:
        caseout=out/case;caseout.mkdir(exist_ok=True)
        print('Running '+case,flush=True)
        with (caseout/'execution.log').open('w',encoding='utf-8') as log:
            subprocess.run([sys.executable,str(ROOT/'scripts/analyze.py'),str(ROOT/'data/Table_units_269.csv'),str(ROOT/'data/fig6_plant_traits.csv'),str(caseout),exclude],check=True,env=env,stdout=log,stderr=subprocess.STDOUT)
    subprocess.run([sys.executable,str(ROOT/'scripts/make_tables.py'),str(out)],check=True,env=env)
    for ext in ['png','pdf','svg']:
        shutil.copyfile(out/'all_batches'/f'Fig7.{ext}',out/f'Fig7.{ext}')
    versions={p:importlib.metadata.version(p) for p in ['numpy','pandas','scipy','statsmodels','matplotlib','openpyxl','patsy']}
    (out/'environment.json').write_text(json.dumps({'python':sys.version,'packages':versions,'seeds':list(range(50))},indent=2)+'\n',encoding='utf-8')
    subprocess.run([sys.executable,str(ROOT/'scripts/verify.py'),str(out)],check=True,env=env)
    print('Complete. See '+str(out/'Table_S7.xlsx')+' and '+str(out/'verification.json'),flush=True)

if __name__=='__main__': main()

#!/usr/bin/env python3
"""Reproduce available manuscript analyses from bundled prepared inputs."""
from pathlib import Path
import argparse, hashlib, json, os, subprocess, sys

ROOT = Path(__file__).resolve().parent
JOBS = {
    'Fig.5': [('figures/plot_processing_time.py', []), ('figures/plot_s0232_trajectories.py', ['--only', 'fig5'])],
    'Fig.6': [('figures/plot_trait_splom.py', []), ('tables/stats_fig6.py', [])],
    'Fig.7': [('run_all.py', [])],
    'Supp.Fig.S2': [('figures/plot_ownership_twobatch.py', [])],
    'Supp.Fig.S3': [('figures/plot_s0232_trajectories.py', ['--only', 's3'])],
    'Supp.Fig.S4': [('figures/plot_dead_plant.py', [])],
    'Table.1': [('tables/make_table1_s6.py', [])],
    'Supp.Table.S5': [('tables/make_table_s5.py', [])],
}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('items', nargs='*', help='Optional current item names, e.g. Fig.5 Fig.6')
    parser.add_argument('--output', type=Path, default=ROOT/'results')
    args = parser.parse_args()
    unknown = set(args.items) - set(JOBS)
    if unknown:
        parser.error('Unknown items: ' + ', '.join(sorted(unknown)) + '. Choices: ' + ', '.join(JOBS))
    out = args.output.resolve()
    # Only the generated results tree is writable inside the supplied package.
    package = ROOT.parent.resolve()
    if out == package or package in out.parents:
        if out != ROOT/'results' and ROOT/'results' not in out.parents:
            parser.error('Inside the package, output must be results/ or a child of it.')
    for item in json.loads((ROOT/'input_checksums.json').read_text(encoding='utf-8')):
        path = ROOT/item['path']
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise SystemExit('Input checksum mismatch: ' + item['path'])
    out.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(PYTHONDONTWRITEBYTECODE='1', MPLBACKEND='Agg', PYTHONHASHSEED='0', PYTHONIOENCODING='utf-8',
               MPLCONFIGDIR=str(out/'.matplotlib'), XDG_CACHE_HOME=str(out/'.cache'))
    completed = []
    for name in args.items or JOBS:
        folder = ROOT/name
        target = out/name
        target.mkdir(exist_ok=True)
        for script, extra in JOBS[name]:
            cmd = [sys.executable, '-B', str(folder/script)]
            if name == 'Fig.7':
                cmd += ['--output', str(target)]
            else:
                cmd += ['--data', str(folder/'data'), '--out', str(target)] + extra
            print('Running ' + name + ': ' + script, flush=True)
            subprocess.run(cmd, cwd=folder, env=env, check=True)
        completed.append(name)
    (out/'run_summary.json').write_text(json.dumps({'completed': completed, 'python': sys.version,
        'scope': 'Prepared-data analysis only; no raw processing or manual figure assembly.'}, indent=2)+'\n')
    print('Complete: ' + str(out))

if __name__ == '__main__':
    main()

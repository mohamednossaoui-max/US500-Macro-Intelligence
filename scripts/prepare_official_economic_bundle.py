"""Export validated Economic/dependent changes without copying unrelated old data."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
REQUIRED={'economic_ingestion_status_v1.json',
          'economic_historical_events_v1.csv','economic_historical_quality_v1.csv',
          'economic_surprise_engine_v1.csv','economic_surprise_summary_v1.csv',
          'economic_regime_events_v1.csv','economic_regime_summary_v1.csv','research_context_summary_v1.csv'}

def prepare(baseline,validated,output):
    baseline,validated,output=map(Path,(baseline,validated,output))
    subprocess.run([sys.executable,str(Path(__file__).with_name('verify_publication_integrity.py')),'--public-data',str(validated)],check=True)
    missing=REQUIRED-{p.name for p in validated.iterdir() if p.is_file()}
    if missing:raise RuntimeError('Validated bundle missing: '+','.join(sorted(missing)))
    if output.exists():shutil.rmtree(output)
    output.mkdir(parents=True)
    names=[]
    for path in sorted(validated.iterdir()):
        if path.suffix not in {'.csv','.json'} or path.name=='manifest.json':continue
        prior=baseline/path.name
        if path.name in REQUIRED or not prior.exists() or prior.read_bytes()!=path.read_bytes():
            (output/path.name).write_bytes(path.read_bytes());names.append(path.name)
    return names

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--baseline',required=True);ap.add_argument('--validated',required=True);ap.add_argument('--output',required=True)
    args=ap.parse_args();print('\n'.join(prepare(args.baseline,args.validated,args.output)))

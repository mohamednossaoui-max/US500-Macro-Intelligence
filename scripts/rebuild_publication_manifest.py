from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

def rebuild(root:Path, source='autonomous-intelligence-pipeline-v1'):
    manifest={'publisher':'US500 Macro Intelligence','publisher_version':'V3','research_only':True,'source_workflow':source,'files':{}}
    for p in sorted(root.iterdir()):
        if not p.is_file() or p.name=='README.md' or p.name=='manifest.json' or (p.suffix=='.json' and 'manifest' in p.stem.lower()): continue
        data=p.read_bytes(); manifest['files'][p.name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    return manifest

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--public-data',default='public_data'); ap.add_argument('--source',default='autonomous-intelligence-pipeline-v1'); a=ap.parse_args()
    m=rebuild(Path(a.public_data),a.source); print(f"manifest files: {len(m['files'])}")
if __name__=='__main__': main()

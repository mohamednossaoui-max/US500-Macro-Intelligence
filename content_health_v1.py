"""Content freshness and hash-verified published-output checks, never filesystem age."""
from pathlib import Path
import hashlib,json
import pandas as pd

DATE_COLUMNS = ['available_at_utc','availability_date','available_at','available_as_of',
                'asof_date','context_date','as_of_date','release_date','research_date',
                'published_at','date','observation_date']
JSON_DATES = ['latest_asof_date','analysis_date_end','date_end','context_date','as_of_date',
              'asof_date','retrieved_at','generated_at','generated_at_utc','as_of']

def content_timestamp(path):
    path=Path(path)
    try:
        if path.suffix.lower()=='.csv':
            d=pd.read_csv(path,low_memory=False)
            names={str(c).lower():c for c in d.columns}
            for key in DATE_COLUMNS:
                if key in names:
                    v=pd.to_datetime(d[names[key]],errors='coerce',utc=True,format='mixed').dropna()
                    if not v.empty:return v.max().to_pydatetime()
        elif path.suffix.lower()=='.json':
            obj=json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(obj,dict):return None
            for key in JSON_DATES:
                if obj.get(key):
                    v=pd.to_datetime(obj[key],errors='coerce',utc=True)
                    if pd.notna(v):return v.to_pydatetime()
    except (OSError,ValueError,TypeError):pass
    return None

def output_facts(node,public):
    paths=[Path(public)/n for n in node.get('outputs',[])]
    existing=[f for f in paths if f.is_file()]
    freshness=[Path(public)/n for n in node.get("freshness_outputs",node.get("outputs",[]))]
    stamps=[content_timestamp(f) for f in freshness if f.is_file()]
    stamps=[v for v in stamps if v is not None]
    # Latest per file; oldest supported output bounds multi-file node freshness.
    stamp=min(stamps) if stamps else None
    try: manifest=json.loads((Path(public)/'manifest.json').read_text(encoding='utf-8')).get('files',{})
    except (OSError,ValueError):manifest={}
    verified=bool(paths) and len(existing)==len(paths)
    for f in existing:
        meta=manifest.get(f.name,{})
        verified=verified and meta.get('sha256')==hashlib.sha256(f.read_bytes()).hexdigest() and meta.get('bytes')==f.stat().st_size
    return stamp,bool(verified),len(existing)==len(paths)

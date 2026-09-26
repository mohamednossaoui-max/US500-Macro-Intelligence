from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
from typing import Any
MANIFEST_NAMES=("public_data_manifest.json","manifest.json")
def sha256_file(path: Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()
def load_json(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise ValueError(f"{path} must contain a JSON object")
    return x
def extract_entries(m):
    if isinstance(m.get("files"),dict): return {k:{"bytes":v.get("bytes"),"sha256":v.get("sha256")} for k,v in m["files"].items() if isinstance(v,dict)}
    if isinstance(m.get("datasets"),list): return {x["file"]:{"bytes":x.get("bytes"),"sha256":x.get("sha256")} for x in m["datasets"] if isinstance(x,dict) and isinstance(x.get("file"),str)}
    raise ValueError("Unsupported manifest format")
def verify_manifest(mp:Path,root:Path):
    rows=[]
    for fn,md in sorted(extract_entries(load_json(mp)).items()):
        p=root/fn; r={"file":fn,"expected_sha256":md.get("sha256"),"actual_sha256":None,"expected_bytes":md.get("bytes"),"actual_bytes":None,"status":"MISSING"}
        if p.is_file():
            r["actual_sha256"]=sha256_file(p); r["actual_bytes"]=p.stat().st_size
            r["status"]="MATCH" if r["actual_sha256"]==r["expected_sha256"] and r["actual_bytes"]==r["expected_bytes"] else "MISMATCH"
        rows.append(r)
    return {"summary":{"manifest":mp.name,"total":len(rows),"match":sum(r["status"]=="MATCH" for r in rows),"mismatch":sum(r["status"]=="MISMATCH" for r in rows),"missing":sum(r["status"]=="MISSING" for r in rows),"error":0},"results":rows}
def run(root:Path):
    reps=[verify_manifest(root/n,root) for n in MANIFEST_NAMES if (root/n).is_file()]; by={}
    for rep in reps:
        for r in rep["results"]: by.setdefault(r["file"],{})[rep["summary"]["manifest"]]=r["expected_sha256"]
    conflicts=[{"file":f,"manifest_hashes":v} for f,v in sorted(by.items()) if len({x for x in v.values() if isinstance(x,str)})>1]
    return {"manifests":reps,"manifest_conflicts":conflicts}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--public-data",type=Path,default=Path("public_data")); a=ap.parse_args(); rep=run(a.public_data)
    print("\n============================================\nUS500 PUBLICATION INTEGRITY\n============================================")
    for x in rep["manifests"]:
        s=x["summary"]; print(f"\nManifest: {s['manifest']}\nTotal:     {s['total']}\nMatch:     {s['match']}\nMismatch:  {s['mismatch']}\nMissing:   {s['missing']}\nError:     {s['error']}")
        for r in x["results"]:
            if r["status"]!="MATCH": print(f"  [{r['status']}] {r['file']}\n    expected sha256: {r['expected_sha256']}\n    actual sha256:   {r['actual_sha256']}\n    expected bytes:  {r['expected_bytes']}\n    actual bytes:    {r['actual_bytes']}")
    print(f"\nManifest conflicts: {len(rep['manifest_conflicts'])}")
    for c in rep["manifest_conflicts"]: print("\n  "+c["file"]+"\n"+"\n".join(f"    {k}: {v}" for k,v in c["manifest_hashes"].items()))
    return 0
if __name__=="__main__": raise SystemExit(main())

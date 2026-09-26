import hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"scripts"))
from verify_publication_integrity import sha256_file, verify_manifest, run, extract_entries
def wm(p,fn,data): p.write_text(json.dumps({"files":{fn:{"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}}}))
def test_sha(tmp_path):
 p=tmp_path/"x";p.write_bytes(b"abc");assert sha256_file(p)==hashlib.sha256(b"abc").hexdigest()
def test_match(tmp_path):
 d=tmp_path/"p";d.mkdir();(d/"x").write_bytes(b"a");wm(d/"manifest.json","x",b"a");assert verify_manifest(d/"manifest.json",d)["summary"]["match"]==1
def test_mismatch(tmp_path):
 d=tmp_path/"p";d.mkdir();(d/"x").write_bytes(b"b");wm(d/"manifest.json","x",b"a");assert verify_manifest(d/"manifest.json",d)["summary"]["mismatch"]==1
def test_missing(tmp_path):
 d=tmp_path/"p";d.mkdir();wm(d/"manifest.json","x",b"a");assert verify_manifest(d/"manifest.json",d)["summary"]["missing"]==1
def test_readonly(tmp_path):
 d=tmp_path/"p";d.mkdir();f=d/"x";f.write_bytes(b"a");m=d/"manifest.json";wm(m,"x",b"a");before=(m.read_bytes(),f.read_bytes());verify_manifest(m,d);assert before==(m.read_bytes(),f.read_bytes())
def test_conflict(tmp_path):
 d=tmp_path/"p";d.mkdir();(d/"x").write_bytes(b"b");wm(d/"manifest.json","x",b"b");(d/"public_data_manifest.json").write_text(json.dumps({"datasets":[{"file":"x","bytes":1,"sha256":hashlib.sha256(b"a").hexdigest()}]}));assert len(run(d)["manifest_conflicts"])==1

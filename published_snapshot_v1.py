"""One manifest per frontend run; missing or mismatched bytes never fall back across generations."""
from pathlib import Path,PurePosixPath
import hashlib,json

class PublishedSnapshot:
    def __init__(self,public,fetch):
        self.public=Path(public);self.fetch=fetch;self.cache={};self.local=(self.public/'manifest.json').is_file()
        try:
            raw=(self.public/'manifest.json').read_bytes() if self.local else fetch('manifest.json')
            self.manifest=json.loads(raw) if raw else {}
        except (OSError,ValueError,TypeError):self.manifest={}
        self.generation=hashlib.sha256(json.dumps(self.manifest,sort_keys=True).encode()).hexdigest()[:16]

    def read(self,name):
        name=str(name).replace('\\','/').removeprefix('public_data/')
        if name.startswith('/') or '..' in PurePosixPath(name).parts:return None,'INVALID ARTIFACT PATH'
        if name in self.cache:return self.cache[name]
        meta=self.manifest.get('files',{}).get(name)
        if not isinstance(meta,dict):return None,'NOT IN VERIFIED PUBLICATION'
        try:raw=(self.public/name).read_bytes() if self.local else self.fetch(name)
        except OSError:raw=None
        if raw is None:return None,'MISSING FROM PUBLICATION '+self.generation
        if len(raw)!=meta.get('bytes') or hashlib.sha256(raw).hexdigest()!=meta.get('sha256'):
            return None,'PUBLICATION HASH MISMATCH '+self.generation
        result=(raw,('LOCAL' if self.local else 'GITHUB RAW')+': public_data/'+name+' · generation '+self.generation)
        self.cache[name]=result
        return result

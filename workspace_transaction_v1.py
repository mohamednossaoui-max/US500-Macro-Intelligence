"""Recoverable multi-file installation into the private build workspace.
Publication still requires a verified manifest and one Git commit.
"""
from pathlib import Path
import json,os,shutil,tempfile

def recover(root):
    root=Path(root); journal=root/'.economic-install-journal.json'
    if not journal.exists():return
    info=json.loads(journal.read_text());backup=Path(info['backup'])
    for name,existed in info['files'].items():
        dest=root/name
        if existed:shutil.copyfile(backup/name,dest)
        elif dest.exists():dest.unlink()
    journal.unlink();shutil.rmtree(backup)

def install_bundle(root,payloads):
    root=Path(root);recover(root)
    backup=Path(tempfile.mkdtemp(prefix='.economic-install-',dir=root))
    existed={n:(root/n).exists() for n in payloads}
    for n,exists in existed.items():
        if exists:shutil.copyfile(root/n,backup/n)
        (backup/(n+'.new')).write_bytes(payloads[n])
    journal=root/'.economic-install-journal.json'
    journal.write_text(json.dumps({'backup':str(backup.resolve()),'files':existed}))
    try:
        for n in payloads:os.replace(backup/(n+'.new'),root/n)
    except BaseException:
        recover(root);raise
    journal.unlink();shutil.rmtree(backup)

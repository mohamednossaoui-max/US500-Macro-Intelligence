from pathlib import Path
import shutil, sys, py_compile
base=Path(__file__).resolve().parent
app=base/'app.py'; backup=base/'app.py.pre_patch4'
if not backup.exists():
    print('RESTORE ABORTED: app.py.pre_patch4 not found.'); sys.exit(1)
try: py_compile.compile(str(backup), doraise=True)
except Exception as e: print(f'RESTORE ABORTED: backup syntax check failed: {e}'); sys.exit(1)
shutil.copy2(backup, app)
print('PATCH 4 RESTORED: app.py was restored from app.py.pre_patch4')

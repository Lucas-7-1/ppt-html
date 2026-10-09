#!/usr/bin/env python3
"""Report dependencies without installing or modifying anything."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
HERE = Path(__file__).resolve().parent

def main():
    checks = [{'component':'Python >= 3.10','ok':sys.version_info >= (3,10)}]
    for name in ('lxml','PIL','fontTools','yaml'):
        checks.append({'component':name,'ok':importlib.util.find_spec(name) is not None})
    root = os.environ.get('CODEX_PRIMARY_RUNTIME_ROOT')
    for name in ('soffice','pdftoppm','fc-match','fc-cache'):
        provided = Path(root)/'dependencies/bin/override'/name if root else None
        found = str(provided) if provided and provided.is_file() else shutil.which(name)
        checks.append({'component':name,'ok':bool(found)})
    node = os.environ.get('CODEX_PRIMARY_RUNTIME_NODE') or os.environ.get('RUNTIME_NODE') or shutil.which('node')
    try:
        if not node: raise RuntimeError('Node.js was not found')
        result = subprocess.run([node,str(HERE/'container.mjs'),'--probe'],capture_output=True,text=True,timeout=30)
        if result.returncode: raise RuntimeError(result.stderr[-1200:])
        runtime = json.loads(result.stdout)
        checks.append({'component':'Node >= 22 and presentation/preview runtime','ok':int(runtime['node'].split('.')[0]) >= 22,'runtime':runtime})
    except Exception as error:
        checks.append({'component':'Node presentation/preview runtime','ok':False,'error':str(error)})
    try:
        from fonts import resolve, metrics
        coverage, _, _ = metrics(str(resolve('Noto Sans SC')))
        if not set(map(ord,'中文Aa0123%')).issubset(coverage): raise ValueError('required glyphs missing')
        checks.append({'component':'Noto Sans SC','ok':True})
    except Exception as error:
        checks.append({'component':'Noto Sans SC','ok':False,'error':str(error),'fix':'python3 scripts/fonts.py --ensure'})
    ok = all(item['ok'] for item in checks)
    print(json.dumps({'ok':ok,'checks':checks},ensure_ascii=False,indent=2))
    return 0 if ok else 1
if __name__ == '__main__': sys.exit(main())

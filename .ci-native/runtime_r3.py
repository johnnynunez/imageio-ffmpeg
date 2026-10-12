"""Resolve OS import/API-set hosts in a native clean-path process."""
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path

reports=Path(os.environ['REPORTS'])
imports=json.loads((reports/'runtime-imports.json').read_text())['imports']
os.environ['PATH']=str(Path(os.environ['SystemRoot'])/'System32')
kernel=ctypes.WinDLL('kernel32',use_last_error=True)
kernel.GetModuleFileNameW.argtypes=[wintypes.HMODULE,wintypes.LPWSTR,wintypes.DWORD]
kernel.GetModuleFileNameW.restype=wintypes.DWORD
rows=[]; modules=[]
for name in imports:
    module=ctypes.WinDLL(name); modules.append(module)
    buffer=ctypes.create_unicode_buffer(32768)
    assert kernel.GetModuleFileNameW(module._handle,buffer,len(buffer))
    path=Path(buffer.value)
    assert path.parent.resolve()==(Path(os.environ['SystemRoot'])/'System32').resolve(),(name,str(path))
    rows.append({'import':name,'loaded_host_path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
(reports/'system-runtime-witness.json').write_text(json.dumps(rows,indent=2),encoding='utf8')
print(json.dumps(rows,indent=2))

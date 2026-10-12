"""Pinned LLVM-MinGW installation and source provenance; not legal clearance."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile

ROOT = Path.cwd()
REPORTS = Path(os.environ['REPORTS'])
SOURCES = Path(os.environ['SOURCES'])
PIN = '28748c4b2dbc7396f095bafd92321958c5a2db1c'
LLVM = '6146a88f60492b520a36f8f8f3231e15f3cc6082'
MINGW = 'e06d7853b292f6f81f200169092dd41ff92bca7e'
ASSET = 'https://github.com/mstorsjo/llvm-mingw/releases/download/20250613/llvm-mingw-20250613-ucrt-aarch64.zip'
DIGEST = 'b1dcfe18854bdf5e719064df35417bf4e485e1973996c0acc4e1ec193d09de53'

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def download(url,p):
    with urllib.request.urlopen(url,timeout=180) as r, p.open('wb') as f:
        shutil.copyfileobj(r,f)

archive = Path(os.environ['RUNNER_TEMP'])/'llvm-mingw.zip'
download(ASSET, archive)
assert sha(archive) == DIGEST
with zipfile.ZipFile(archive) as z:
    z.extractall(ROOT/'toolchain')
tool = next((ROOT/'toolchain').glob('llvm-mingw-*'))
with open(os.environ['GITHUB_ENV'],'a') as f:
    f.write('TOOLCHAIN='+tool.as_posix()+'\n')
with open(os.environ['GITHUB_PATH'],'a') as f:
    f.write(str(tool/'bin')+'\n')
version = subprocess.check_output([str(tool/'bin/aarch64-w64-mingw32-clang.exe'),'--version'],text=True)
(REPORTS/'clang-version.txt').write_text(version,encoding='utf8')
assert '20.1.7' in version
inputs = []
for label,repo,commit in [('llvm-mingw','mstorsjo/llvm-mingw',PIN),('mingw-w64','mingw-w64/mingw-w64',MINGW),('llvm-project','llvm/llvm-project',LLVM)]:
    url=f'https://codeload.github.com/{repo}/tar.gz/{commit}'
    p=SOURCES/(label+'.tar.gz')
    download(url,p)
    inputs.append({'component':label,'commit':commit,'url':url,'sha256':sha(p),'size':p.stat().st_size})
    with tarfile.open(p) as t:
        names=t.getnames()
        if label=='llvm-mingw':
            wanted={'README.md':'toolchain-README.md','LICENSE.txt':'toolchain-LICENSE.txt'}
        elif label=='mingw-w64':
            wanted={'COPYING':'mingw-COPYING.txt'}
        else:
            wanted={'LICENSE.TXT':'llvm-LICENSE.txt'}
        for rel,out in wanted.items():
            member=next(n for n in names if n.split('/',1)[-1]==rel)
            (REPORTS/out).write_bytes(t.extractfile(member).read())
provenance={'profile':'NEW LLVM-MinGW 20250613 native aarch64, UCRT OS import','toolchain_commit':PIN,'toolchain_asset':ASSET,'toolchain_sha256':DIGEST,'sources':inputs,'runtime_policy':'MinGW-w64 startup/support and LLVM compiler-rt static objects; system UCRT dynamically imported, never copied. No MSVC compiler/runtime input intended. Actual link-map and PE audit must confirm.','rights_verified':False,'bit_reproducibility_claim':False}
(REPORTS/'toolchain-provenance.json').write_text(json.dumps(provenance,indent=2),encoding='utf8')
libs=[]
for p in sorted(tool.rglob('*')):
    if p.is_file() and (p.suffix in ('.a','.o') or p.name.lower().startswith(('license','copying'))):
        libs.append({'path':p.relative_to(tool).as_posix(),'sha256':sha(p),'size':p.stat().st_size})
(REPORTS/'toolchain-inputs.json').write_text(json.dumps(libs,indent=2),encoding='utf8')
print(json.dumps(provenance,indent=2))

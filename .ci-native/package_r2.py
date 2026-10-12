"""Experimental package/source assembly and fail-closed publication gates."""
import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path.cwd()
REPORTS = Path(os.environ['REPORTS'])
PAYLOAD = Path(os.environ['PAYLOAD'])
SOURCES = Path(os.environ['SOURCES'])
VERSION = '0.6.0+arm64.gpl.r2'
PINS = {'imageio': '852dff761c65517e7cb24c380391ea39cf2d27bf', 'ffmpeg': 'b08d7969c550a804a59511c7b83f2dd8cc0499b8', 'x264': 'b35605ace3ddf7c1a5d67a2eb553f034aef41d55'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    (REPORTS/name).write_text(json.dumps(value, indent=2), encoding='utf8')


def command(args, **kwargs):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, **kwargs)


def surface(text, kind):
    result = set()
    active = False
    for line in text.splitlines():
        s = line.strip()
        if kind == 'protocols':
            if s in ('Input:', 'Output:'):
                active = True
            elif active and re.fullmatch(r'[a-z0-9_]+', s):
                result.add(s)
        elif kind == 'filters':
            m = re.match(r'^\s*[TSC.]{3}\s+(\S+)\s', line)
            if m and m.group(1) != '=':
                result.add(m.group(1))
        else:
            m = re.match(r'^\s*[VAS.][A-Z.]{5}\s+(\S+)\s', line)
            if m and m.group(1) != '=':
                result.add(m.group(1))
    assert result, kind
    return result


def prepare():
    import pefile
    exe = ROOT/'ffmpeg/ffmpeg.exe'
    assert not command(['git','-C','ffmpeg','diff','--name-only']).strip()
    assert not command(['git','-C','source','diff','--name-only']).strip()
    pe = pefile.PE(str(exe))
    assert pe.FILE_HEADER.Machine == 0xAA64
    imports = sorted({x.dll.decode().lower() for attr in ('DIRECTORY_ENTRY_IMPORT','DIRECTORY_ENTRY_DELAY_IMPORT') for x in getattr(pe, attr, [])})
    # No CRT/vendor DLL copying. Every import must be a named OS component.
    allowed = {'kernel32.dll','user32.dll','advapi32.dll','bcrypt.dll','shell32.dll','ole32.dll','gdi32.dll','secur32.dll','ws2_32.dll','psapi.dll','ntdll.dll','vfw32.dll','winmm.dll'}
    save('runtime-imports.json', {'imports': imports, 'unclassified': sorted(set(imports)-allowed), 'exe_sha256': sha(exe), 'machine': hex(pe.FILE_HEADER.Machine), 'runtime_policy': 'Explicit -MT for x264 and FFmpeg: static MSVC CRT; no runtime DLL copied; separate rights review required.'})
    assert set(imports) <= allowed, imports
    bins = ROOT/'source/imageio_ffmpeg/binaries'
    shutil.copy2(exe, bins/'ffmpeg-win-aarch64-v7.1.exe')
    definitions = ROOT/'source/imageio_ffmpeg/_definitions.py'
    original = definitions.read_text()
    assert original.count('__version__ = "0.6.0"') == 1
    definitions.write_text(original.replace('__version__ = "0.6.0"', f'__version__ = "{VERSION}"'), encoding='utf8')
    notices = command(['git','-C','source','show','HEAD:LICENSE'])
    (bins/'LICENSE-wrapper-BSD-2-Clause.txt').write_text(notices, encoding='utf8')
    for path in (ROOT/'ffmpeg').glob('COPYING*'):
        shutil.copy2(path, bins/f'FFmpeg-{path.name}.txt')
    shutil.copy2(ROOT/'ffmpeg/LICENSE.md', bins/'FFmpeg-LICENSE.md')
    shutil.copy2(ROOT/'x264/COPYING', bins/'x264-COPYING-GPL-2.0.txt')
    # Preserve all separately named legal material in the payload and full source.
    legal = []
    for component in ('source','ffmpeg','x264'):
        for p in sorted((ROOT/component).rglob('*')):
            if not p.is_file() or '.git' in p.parts or 'binaries' in p.parts:
                continue
            if re.search(r'(?i)^(copying|copyright|license|notice|patents)([._-]|$)', p.name):
                rel = p.relative_to(ROOT/component).as_posix()
                legal.append({'component': component, 'path': rel, 'sha256': sha(p)})
                name = 'LEGAL-'+component+'-'+rel.replace('/','__')+'.txt'
                shutil.copy2(p, bins/name)
    save('legal-file-inventory.json', legal)
    (bins/'THIRD-PARTY-NOTICES.txt').write_text((ROOT/'harness/.ci-native/NOTICES-r2.txt').read_text(), encoding='utf8')
    for option in ('version','buildconf','encoders','decoders','protocols','filters','L'):
        (REPORTS/f'{option}.txt').write_text(command([str(exe), '-'+option]), encoding='utf8')
    assert 'GNU General Public License' in (REPORTS/'L.txt').read_text()
    conf = (REPORTS/'buildconf.txt').read_text()
    assert '--enable-gpl' in conf and '--enable-libx264' in conf and '--enable-nonfree' not in conf
    reference = json.loads((ROOT/'harness/.ci-native/official-reference.json').read_text())
    parity = {'reference': reference['reference'], 'native_exe_sha256': sha(exe), 'full_parity': False, 'features': {}}
    for kind in ('encoders','decoders','protocols','filters'):
        actual = surface((REPORTS/f'{kind}.txt').read_text(), kind)
        official = set(reference['features'][kind]['official'])
        parity['features'][kind] = {'native_count':len(actual), 'reference_count':len(official), 'native':sorted(actual), 'missing_from_native':sorted(official-actual), 'native_only':sorted(actual-official)}
    save('feature-differences.json', parity)
    shutil.copy2(REPORTS/'feature-differences.json', bins/'feature-differences.json')
    pins = {**PINS, 'harness':command(['git','-C','harness','rev-parse','HEAD']).strip(), 'version':VERSION, 'exe_sha256':sha(exe), 'source_archive_hashes':{p.name:sha(p) for p in SOURCES.iterdir() if p.is_file()}, 'runtime':'static MSVC -MT; OS DLLs not bundled', 'publication_rights_verified':False}
    save('provenance.json', pins)
    shutil.copy2(REPORTS/'provenance.json', bins/'provenance.json')
    diff = command(['git','-C','source','diff','--','imageio_ffmpeg/_definitions.py'])
    (SOURCES/'wrapper-local-version.patch').write_text(diff, encoding='utf8')
    (REPORTS/'wrapper-local-version.patch').write_text(diff, encoding='utf8')
    for component, paths in {'ffmpeg':['ffbuild/config.mak','ffbuild/config.log','config.h','config_components.h','libavutil/ffversion.h'], 'x264':['config.mak','config.log','config.h','x264_config.h']}.items():
        for relative in paths:
            p = ROOT/component/relative
            if p.exists():
                shutil.copy2(p, SOURCES/(component+'-'+relative.replace('/','__')))
                shutil.copy2(p, REPORTS/(component+'-'+relative.replace('/','__')))


def negative():
    wheel = next(PAYLOAD.glob('*.whl'))
    assert wheel.name == f'imageio_ffmpeg-{VERSION}-py3-none-win_arm64.whl', wheel.name
    bad = Path(os.environ['RUNNER_TEMP'])/'poisoned-wheel.whl'
    with zipfile.ZipFile(wheel) as z, zipfile.ZipFile(bad,'w') as out:
        for name in z.namelist():
            raw = z.read(name)
            if name.endswith('_definitions.py'):
                raw += b'\n# deliberately invalid RECORD\n'
            out.writestr(name, raw)
    run = subprocess.run([sys.executable, str(ROOT/'harness/.ci-native/audit_wheel.py'),str(bad),str(REPORTS/'negative-record-audit.json')],text=True,capture_output=True)
    assert run.returncode != 0 and 'RECORD mismatch' in run.stdout, run.stdout+run.stderr
    save('negative-control.json', {'corrupt_RECORD_rejected':True, 'returncode':run.returncode})
    bad.unlink()


def finalize():
    xml = ET.parse(REPORTS/'bundled.xml')
    cases = xml.findall('.//testcase')
    assert len(cases) == 5 and not xml.findall('.//failure') and not xml.findall('.//error') and not xml.findall('.//skipped')
    suites = xml.findall('.//testsuite')
    assert sum(int(s.get('tests',0)) for s in suites) == len(cases)
    audit = json.loads((REPORTS/'wheel-audit.json').read_text())
    assert not audit['errors'] and len(audit['PE']) == 1
    assert f'Version: {VERSION}' in audit['metadata']
    assert 'Tag: py3-none-win_arm64' in audit['wheel_metadata']
    assert any('wrapper-BSD' in x for x in audit['licenses'])
    # Evidence is separate from publication authorization. Never infer permission
    # from native execution or absence of imported CRT DLLs.
    gates = {'technical':True, 'native_tests':len(cases), 'source_pins_verified':True, 'gpl_enabled':True, 'source_assembly':True, 'notices_staged':True, 'rights_verified':False, 'publish':False, 'blockers':['Static Microsoft CRT object redistribution and GPL/system-library treatment have not been cleared for this exact compiler/runtime. Public documentation is not a grant for this artifact.', 'Final applicable inline-license/NOTICE/PATENTS attribution review remains open; source recovery and named notice copying are not legal clearance.'], 'limitations':['No PNG/zlib or network support; no requirement demonstrated for the accepted rawvideo API; no new dependency substituted.', 'No codec parity, GPU acceleration, assembly optimization or upstream readiness claim.']}
    save('publication-gates.json', gates)
    for name in ('provenance.json','legal-file-inventory.json','feature-differences.json','runtime-imports.json','publication-gates.json'):
        shutil.copy2(REPORTS/name, SOURCES/name)
    shutil.copy2(ROOT/'harness/.ci-native/NOTICES-r2.txt', SOURCES/'NOTICES.txt')
    archive = PAYLOAD/f'imageio_ffmpeg-{VERSION}-corresponding-source.tar.gz'
    with tarfile.open(archive,'w:gz') as tar:
        for p in sorted(SOURCES.iterdir()):
            tar.add(p, arcname='corresponding-source/'+p.name)
    with tarfile.open(archive) as tar:
        names = tar.getnames()
        for required in ('ffmpeg.tar.gz','x264.tar.bz2','wrapper.tar.gz','recipe.tar.gz','wrapper-local-version.patch','NOTICES.txt'):
            assert 'corresponding-source/'+required in names
    save('payload-manifest.json', {'retained_on_runner_only':True,'artifacts':[{'name':p.name,'sha256':sha(p),'size':p.stat().st_size} for p in sorted(PAYLOAD.iterdir())], 'source_bundle_members':names})
    with open(os.environ['GITHUB_OUTPUT'],'a') as f:
        f.write('publish=false\n')
    print(json.dumps(gates,indent=2))


if __name__ == '__main__':
    {'prepare':prepare,'negative':negative,'finalize':finalize}[sys.argv[1]]()

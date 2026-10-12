"""Conservative compiled-source attribution from compiler dependency files."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile


def comments(text):
    # Retain every block comment, not just SPDX or keyword-selected fragments.
    return '\n\n'.join(re.findall(r'/\*.*?\*/|(?m:^\s*//[^\r\n]*$)', text, re.S))


def compiled_sources(root):
    root=Path(root).resolve()
    paths=set()
    for dep in root.rglob('*.d'):
        text=dep.read_text(encoding='utf8').replace('\\\n',' ')
        for token in re.split(r'\s+',text):
            token=token.strip().rstrip(':')
            if not token or token.endswith(('.o','.obj')):
                continue
            p=(root/token).resolve()
            if p.is_file() and p.suffix.lower() in ('.c','.h','.s','.asm','.inc','.cpp'):
                try: paths.add(p.relative_to(root).as_posix())
                except ValueError: pass  # External compiler headers have a separate provenance gate.
    if not paths:
        raise ValueError('no compiled dependencies found: '+str(root))
    return sorted(paths)


def main():
    root=Path.cwd(); reports=Path(os.environ['REPORTS']); sources=Path(os.environ['SOURCES'])
    assert not subprocess.check_output(['git','-C','ffmpeg','diff','--name-only'],text=True).strip()
    assert not subprocess.check_output(['git','-C','source','diff','--name-only'],text=True).strip()
    x264_changed=[]
    with tarfile.open(sources/'x264.tar.bz2') as tar:
        for member in tar.getmembers():
            if not member.isfile(): continue
            rel=member.name.split('/',1)[-1]; p=root/'x264'/rel
            if not p.is_file() or p.read_bytes()!=tar.extractfile(member).read(): x264_changed.append(rel)
    assert not x264_changed,x264_changed
    inventory=[]; text=[(root/'harness/.ci-native/NOTICES-r3.txt').read_text(encoding='utf8')]
    for component in ('ffmpeg','x264'):
        paths=compiled_sources(root/component)
        for rel in paths:
            p=root/component/rel; raw=p.read_bytes()
            inventory.append({'component':component,'path':rel,'sha256':hashlib.sha256(raw).hexdigest(),'evidence':'compiler .d dependency; compiled-input superset of retained linked sections'})
            notice=comments(raw.decode('utf8',errors='strict'))
            if notice: text.extend(['\n===== '+component+'/'+rel+' =====\n',notice])
    # Explicit pinned upstream terms and wrapper terms remain verbatim.
    for component,rel in [('source','LICENSE'),('ffmpeg','LICENSE.md'),('ffmpeg','COPYING.GPLv2'),('ffmpeg','COPYING.GPLv3'),('ffmpeg','COPYING.LGPLv2.1'),('ffmpeg','COPYING.LGPLv3'),('x264','COPYING')]:
        text.extend(['\n===== '+component+'/'+rel+' =====\n',(root/component/rel).read_text(encoding='utf8')])
    for required in ['libavcodec/jfdctfst.c','libavcodec/jfdctint_template.c','libavcodec/jrevdct.c']:
        assert any(x['component']=='ffmpeg' and x['path']==required for x in inventory),required
    linkmap=(root/'ffmpeg/ffmpeg.map').read_text(encoding='utf8')
    for obj in ('jfdctfst.o','jfdctint.o','jrevdct.o'):
        assert obj in linkmap,obj
    forbidden=('libcmt.lib','libvcruntime.lib','libucrt.lib','vcruntime140','msvcp140')
    assert not any(x in linkmap.lower() for x in forbidden)
    (reports/'link-map.txt').write_text(linkmap,encoding='utf8')
    (reports/'THIRD-PARTY-NOTICES.txt').write_text('\n'.join(text),encoding='utf8')
    data={'scope':'FFmpeg/x264 compiler dependency inventory plus unchanged pinned wrapper license. Includes compiled but dead-stripped inputs conservatively. Actual selected sections in link-map.txt. External toolchain headers/startup/compiler-rt remain a separate review.','compiled_source_count':len(inventory),'sources':inventory,'IJG_link_selected':True,'MSVC_static_library_names_found':False}
    (reports/'source-attribution.json').write_text(json.dumps(data,indent=2),encoding='utf8')
    unchanged={'ffmpeg_pin':'b08d7969c550a804a59511c7b83f2dd8cc0499b8','ffmpeg_tracked_diff_empty':True,'x264_pin':'b35605ace3ddf7c1a5d67a2eb553f034aef41d55','x264_original_archive_members_unchanged':True,'wrapper_pin':'852dff761c65517e7cb24c380391ea39cf2d27bf','wrapper_before_version_patch_unchanged':True,'statement':'No additions, deletions, or modifications to jfdctfst.c, jfdctint_template.c or jrevdct.c relative to this exact pinned FFmpeg revision. This does not assert that upstream FFmpeg never modified original IJG sources. Generated configuration/version headers are build outputs; wrapper local version and added binary/notice packaging are recorded separately.'}
    (reports/'source-unchanged.json').write_text(json.dumps(unchanged,indent=2),encoding='utf8')

if __name__=='__main__': main()

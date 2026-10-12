"""Fail-closed exact-name text policy; originals are never edited/deleted."""
import hashlib
import json
from pathlib import Path
import stat
import sys
import zipfile

ALLOW = frozenset(json.loads(Path(__file__).with_name('reports-allowlist.json').read_text()))

def validate(name, raw):
    if name not in ALLOW:
        raise ValueError('unlisted report member: '+name)
    if raw.startswith((b'MZ', b'PK\x03\x04', b'\x7fELF', b'\x1f\x8b')):
        raise ValueError('binary signature: '+name)
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeError as exc:
        raise ValueError('not UTF-8 text: '+name) from exc
    if any(ord(c) < 32 and c not in '\n\r\t' for c in text) or '\x7f' in text:
        raise ValueError('binary/control byte: '+name)

def audit_zip(path):
    result = []
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if len(names) != len(set(names)):
            raise ValueError('duplicate ZIP members')
        for info in z.infolist():
            if info.is_dir() or stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError('non-regular ZIP entry: '+info.filename)
            raw = z.read(info)
            validate(info.filename, raw)
            result.append({'name': info.filename, 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    if not result:
        raise ValueError('empty report archive')
    return {'strict_reports_only': True, 'sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest(), 'count': len(result), 'files': result}

def filter_zip(path, dest):
    dest = Path(dest)
    dest.mkdir(exist_ok=False, parents=True)
    accepted, rejected = [], []
    with zipfile.ZipFile(path) as z:
        if len(z.namelist()) != len(set(z.namelist())):
            raise ValueError('duplicate ZIP members')
        for info in z.infolist():
            raw = z.read(info)
            try:
                if info.is_dir() or stat.S_ISLNK(info.external_attr >> 16):
                    raise ValueError('nonregular')
                validate(info.filename, raw)
            except ValueError:
                rejected.append(info.filename)
                continue
            (dest/info.filename).write_bytes(raw)
            accepted.append(info.filename)
    return {'source_sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest(), 'accepted_count': len(accepted), 'accepted': accepted, 'rejected': rejected, 'original_modified': False}

def stage(source, dest):
    source, dest = Path(source), Path(dest)
    # Unlike historical salvage, new CI output is rejected as a whole on extras.
    files = sorted(p for p in source.rglob('*') if p.is_file() or p.is_symlink())
    for p in files:
        if p.is_symlink():
            raise ValueError('symlink: '+str(p))
        validate(p.relative_to(source).as_posix(), p.read_bytes())
    if not files:
        raise ValueError('empty report directory')
    dest.mkdir(exist_ok=False, parents=True)
    for p in files:
        (dest/p.name).write_bytes(p.read_bytes())
    return {'accepted_count':len(files), 'rejected':[], 'strict_reports_only':True}

if __name__ == '__main__':
    mode, *args = sys.argv[1:]
    result = {'audit':audit_zip, 'filter':filter_zip, 'stage':stage}[mode](*args)
    print(json.dumps(result, indent=2))

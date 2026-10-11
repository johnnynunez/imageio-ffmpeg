"""Strict wheel RECORD and native-PE inventory, writes evidence before failing."""
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import zipfile

wheel = Path(sys.argv[1])
result = {'wheel': wheel.name, 'sha256': hashlib.sha256(wheel.read_bytes()).hexdigest(), 'PE': [], 'errors': []}
with zipfile.ZipFile(wheel) as z:
    names = z.namelist()
    record = next(n for n in names if n.endswith('.dist-info/RECORD'))
    rows = list(csv.reader(io.StringIO(z.read(record).decode())))
    assert len(names) == len(set(names)), 'duplicate zip member'
    recorded = set()
    for name, digest, size in rows:
        recorded.add(name)
        raw = z.read(name)
        if digest:
            alg, expected = digest.split('=', 1)
            actual = base64.urlsafe_b64encode(hashlib.new(alg, raw).digest()).rstrip(b'=').decode()
            if actual != expected or len(raw) != int(size):
                result['errors'].append('RECORD mismatch: ' + name)
        elif name != record:
            result['errors'].append('unhashed payload: ' + name)
    result['record_rows'] = len(rows)
    result['errors'].extend('unrecorded member: '+n for n in names if n not in recorded and not n.endswith('/'))
    for name in names:
        if name.endswith(('.dll', '.pyd', '.exe')):
            raw = z.read(name)
            off = struct.unpack_from('<I', raw, 0x3C)[0]
            assert raw[:2] == b'MZ' and raw[off:off+4] == b'PE\0\0', name
            machine = struct.unpack_from('<H', raw, off+4)[0]
            result['PE'].append({'path': name, 'machine': hex(machine), 'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)})
            if machine != 0xAA64:
                result['errors'].append('non-native PE requires separate hybrid/import analysis: ' + name)
    result['metadata'] = z.read(next(n for n in names if n.endswith('.dist-info/METADATA'))).decode()
    result['wheel_metadata'] = z.read(next(n for n in names if n.endswith('.dist-info/WHEEL'))).decode()
    result['licenses'] = [n for n in names if 'license' in n.lower() or 'copying' in n.lower()]
    if not result['PE']:
        result['errors'].append('no native payload')
Path(sys.argv[2]).write_text(json.dumps(result, indent=2), encoding='utf8')
print(json.dumps(result, indent=2))
assert not result['errors'], result['errors']

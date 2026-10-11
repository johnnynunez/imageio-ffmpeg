"""Real API default-codec acceptance, no forced FFV1 fallback."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import sysconfig

import imageio_ffmpeg as ff
import numpy as np


def test_default_h264(tmp_path):
    assert sys.version_info[:2] == (3, 12)
    assert sysconfig.get_platform() == 'win-arm64'
    exe = Path(ff.get_ffmpeg_exe())
    b = exe.read_bytes()
    assert struct.unpack_from('<H', b, struct.unpack_from('<I', b, 0x3C)[0] + 4)[0] == 0xAA64
    print('EXECUTABLE', exe, hashlib.sha256(b).hexdigest(), flush=True)
    print(subprocess.check_output([str(exe), '-version'], text=True), flush=True)
    colors = [(20, 40, 180), (80, 140, 20), (180, 40, 50), (220, 180, 30)]
    frames = [np.full((48, 64, 3), c, dtype=np.uint8) for c in colors]
    output = tmp_path / 'default.mp4'
    writer = ff.write_frames(str(output), (64, 48), codec=None, fps=5)
    writer.send(None)
    try:
        for frame in frames:
            writer.send(frame)
    finally:
        writer.close()
    assert output.is_file() and output.stat().st_size > 0
    reader = ff.read_frames(str(output), pix_fmt='rgb24')
    meta = next(reader)
    decoded = [np.frombuffer(x, dtype=np.uint8).reshape(48, 64, 3) for x in reader]
    assert meta['codec'] == 'h264', meta
    assert meta['size'] == (64, 48)
    assert abs(meta['fps'] - 5) < 0.01
    assert abs(meta['duration'] - 0.8) < 0.05
    assert len(decoded) == len(frames)
    errors = [int(np.abs(a.astype(int) - b.astype(int)).max()) for a, b in zip(decoded, frames)]
    assert max(errors) <= 12, errors
    # Separate poisoned oracle: valid frames must reject reversed color order.
    assert max(int(np.abs(a.astype(int)-b.astype(int)).max()) for a,b in zip(decoded,frames[::-1])) > 12
    print('DEFAULT_H264_PASS', json.dumps({'meta': meta, 'frame_count': len(decoded), 'max_errors': errors}), flush=True)

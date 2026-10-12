"""Fresh installed bundle acceptance; never permit an exe override."""
import hashlib
import importlib.metadata as md
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import sysconfig

import imageio_ffmpeg as ff
import numpy as np
import pytest

VERSION = '0.6.0+arm64.gpl.r2'


def bundled():
    assert 'IMAGEIO_FFMPEG_EXE' not in os.environ
    assert sys.version_info[:2] == (3, 12)
    assert sysconfig.get_platform() == 'win-arm64'
    assert md.version('imageio-ffmpeg') == VERSION
    assert ff.__version__ == VERSION
    path = Path(ff.get_ffmpeg_exe()).resolve()
    assert path.parent == Path(ff.__file__).resolve().parent / 'binaries'
    assert 'site-packages' in str(path)
    raw = path.read_bytes()
    assert struct.unpack_from('<H', raw, struct.unpack_from('<I', raw, 0x3c)[0]+4)[0] == 0xAA64
    assert ff.get_ffmpeg_version() == 'n7.1'
    print('BUNDLED', path, hashlib.sha256(raw).hexdigest())
    return path


def test_bundled_native_identity():
    exe = bundled()
    info = subprocess.check_output([str(exe), '-version'], text=True)
    assert '--enable-gpl' in info and '--enable-libx264' in info
    assert '--enable-nonfree' not in info
    license_text = subprocess.check_output([str(exe), '-L'], stderr=subprocess.STDOUT, text=True)
    assert 'GNU General Public License' in license_text


def test_default_h264(tmp_path):
    bundled()
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
    assert meta['codec'] == 'h264' and meta['size'] == (64, 48)
    assert abs(meta['fps'] - 5) < .01 and abs(meta['duration'] - .8) < .05
    assert len(decoded) == len(frames)
    errors = [int(np.abs(a.astype(int)-b.astype(int)).max()) for a,b in zip(decoded,frames)]
    assert max(errors) <= 12, errors
    assert max(int(np.abs(a.astype(int)-b.astype(int)).max()) for a,b in zip(decoded,frames[::-1])) > 12
    print('DEFAULT_H264_PASS', json.dumps({'meta': meta, 'frame_count': len(decoded), 'max_errors': errors}))


def test_ffv1_old_oracle(tmp_path):
    bundled()
    oracle = np.stack([np.full((48, 64, 3), i*16, dtype=np.uint8) for i in range(12)])
    output = tmp_path / 'lossless.mkv'
    writer = ff.write_frames(str(output), (64,48), fps=12, codec='ffv1', pix_fmt_in='rgb24', pix_fmt_out='bgr0', macro_block_size=1)
    writer.send(None)
    for frame in oracle:
        writer.send(frame.tobytes())
    writer.close()
    reader = ff.read_frames(str(output), pix_fmt='rgb24')
    meta = next(reader)
    decoded = np.stack([np.frombuffer(frame,np.uint8).reshape(48,64,3) for frame in reader])
    np.testing.assert_array_equal(decoded, oracle)
    assert meta['size'] == (64,48) and abs(meta['fps']-12) < 1e-6
    count, seconds = ff.count_frames_and_secs(str(output))
    assert count == 12 and abs(seconds-1) < .1
    with pytest.raises(AssertionError):
        np.testing.assert_array_equal(decoded, np.zeros_like(decoded))
    print('FFV1_PASS', count, seconds, meta)


def test_malformed_video(tmp_path):
    bundled()
    path = tmp_path / 'malformed.mp4'
    path.write_bytes(b'not a video\x00'*17)
    with pytest.raises(IOError, match='Could not load meta information'):
        next(ff.read_frames(str(path)))


def test_clean_path_no_ffmpeg_override(tmp_path, monkeypatch):
    exe = bundled()
    monkeypatch.setenv('PATH', str(Path(os.environ['SystemRoot'])/'System32'))
    assert Path(ff.get_ffmpeg_exe()).resolve() == exe
    # Fresh process defeats both wrapper LRU cache and developer PATH fallback.
    code = "import imageio_ffmpeg as f, pathlib; p=pathlib.Path(f.get_ffmpeg_exe()); assert p.parent==pathlib.Path(f.__file__).parent/'binaries'; print(p, f.get_ffmpeg_version())"
    run = subprocess.run([sys.executable, '-I', '-c', code], cwd=tmp_path, text=True, capture_output=True, timeout=30)
    assert run.returncode == 0, run.stderr
    print(run.stdout)

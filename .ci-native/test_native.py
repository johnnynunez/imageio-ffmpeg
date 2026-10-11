"""Installed-wheel CPU tests. No CUDA/NVDEC/NVENC claim."""
import importlib.metadata as md
import io
import os
from pathlib import Path
import platform
import struct
import sys
import sysconfig
import zlib

import numpy as np
import pytest

PACKAGE = os.environ['TEST_PACKAGE']
VERSION = os.environ['TEST_VERSION']


def test_native_interpreter_and_installed_version():
    assert sys.platform == 'win32'
    assert sys.version_info[:2] == (3, 12)
    assert sysconfig.get_platform() == 'win-arm64'
    assert platform.machine().lower() in ('arm64', 'aarch64')
    assert md.version(PACKAGE) == VERSION
    dist = md.distribution(PACKAGE)
    assert 'site-packages' in str(dist.locate_file(''))


def known_rgb():
    return np.array([[[255, 0, 0], [0, 255, 0], [0, 0, 255]],
                     [[12, 34, 56], [255, 255, 255], [0, 0, 0]]], dtype=np.uint8)


def png_fixture(rgb):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    h, w, _ = rgb.shape
    raw = b''.join(b'\0' + row.tobytes() for row in rgb)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')


@pytest.mark.skipif(PACKAGE != 'opencv-python-headless', reason='other package lane')
def test_opencv_resize_colors_known_png(tmp_path):
    import cv2
    rgb = known_rgb()
    bgr = rgb[:, :, ::-1].copy()
    np.testing.assert_array_equal(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), rgb)
    expected = np.repeat(np.repeat(bgr, 2, axis=0), 2, axis=1)
    np.testing.assert_array_equal(cv2.resize(bgr, (6, 4), interpolation=cv2.INTER_NEAREST), expected)
    fixture = np.frombuffer(png_fixture(rgb), dtype=np.uint8)
    np.testing.assert_array_equal(cv2.imdecode(fixture, cv2.IMREAD_COLOR), bgr)
    for ext in ('.png', '.bmp', '.tiff'):
        ok, encoded = cv2.imencode(ext, bgr)
        assert ok
        np.testing.assert_array_equal(cv2.imdecode(encoded, cv2.IMREAD_COLOR), bgr)
    assert cv2.imdecode(np.frombuffer(b'not a picture', np.uint8), cv2.IMREAD_COLOR) is None
    with pytest.raises(AssertionError):
        np.testing.assert_array_equal(cv2.imdecode(fixture, cv2.IMREAD_COLOR), np.zeros_like(bgr))
    (tmp_path / 'build-information.txt').write_text(cv2.getBuildInformation())
    print(cv2.getBuildInformation())


def frames():
    return np.stack([np.full((48, 64, 3), i * 16, dtype=np.uint8) for i in range(12)])


def avi_fixture(images, fps=12):
    """Independent uncompressed AVI oracle, no codec library generates it."""
    n, h, w, _ = images.shape
    framebytes = h * w * 3
    def chunk(tag, data):
        return tag + struct.pack('<I', len(data)) + data + (b'\0' if len(data) % 2 else b'')
    def lst(tag, data):
        return chunk(b'LIST', tag + data)
    avih = struct.pack('<14I', 1000000 // fps, framebytes * fps, 0, 16, n, 0, 1, framebytes, w, h, 0, 0, 0, 0)
    strh = struct.pack('<4s4sIHH8I4h', b'vids', b'DIB ', 0, 0, 0, 0, 1, fps, 0, n, framebytes, 0xFFFFFFFF, 0, 0, 0, w, h)
    strf = struct.pack('<IiiHH4sIiiII', 40, w, h, 1, 24, b'\0' * 4, framebytes, 0, 0, 0, 0)
    header = lst(b'hdrl', chunk(b'avih', avih) + lst(b'strl', chunk(b'strh', strh) + chunk(b'strf', strf)))
    movie, index, offset = b'', b'', 4
    for image in images:
        payload = image[::-1, :, ::-1].tobytes()
        packet = chunk(b'00db', payload)
        movie += packet
        index += struct.pack('<4sIII', b'00db', 16, offset, len(payload))
        offset += len(packet)
    body = b'AVI ' + header + lst(b'movi', movie) + chunk(b'idx1', index)
    return b'RIFF' + struct.pack('<I', len(body)) + body


@pytest.mark.skipif(PACKAGE != 'imageio-ffmpeg', reason='other package lane')
def test_imageio_bundled_native_encode_decode_metadata(tmp_path):
    import imageio_ffmpeg as ff
    exe = Path(ff.get_ffmpeg_exe())
    assert 'site-packages' in str(exe) and 'imageio_ffmpeg' in str(exe)
    raw = exe.read_bytes()
    peoff = struct.unpack_from('<I', raw, 0x3C)[0]
    assert raw[peoff:peoff+4] == b'PE\0\0'
    assert struct.unpack_from('<H', raw, peoff+4)[0] == 0xAA64
    assert ff.get_ffmpeg_version().startswith('7.1')
    oracle = frames()
    output = tmp_path / 'lossless.mkv'
    writer = ff.write_frames(str(output), (64, 48), fps=12, codec='ffv1', pix_fmt_in='rgb24', pix_fmt_out='bgr0', macro_block_size=1)
    writer.send(None)
    for frame in oracle:
        writer.send(frame.tobytes())
    writer.close()
    reader = ff.read_frames(str(output), pix_fmt='rgb24')
    metadata = next(reader)
    decoded = np.stack([np.frombuffer(frame, np.uint8).reshape(48, 64, 3) for frame in reader])
    np.testing.assert_array_equal(decoded, oracle)
    assert metadata['size'] == (64, 48)
    assert abs(metadata['fps'] - 12) < 1e-6
    count, seconds = ff.count_frames_and_secs(str(output))
    assert count == 12 and abs(seconds - 1) < 0.1
    with pytest.raises(AssertionError):
        np.testing.assert_array_equal(decoded, np.zeros_like(decoded))
    print({'exe': str(exe), 'version': ff.get_ffmpeg_version(), 'metadata': metadata, 'frames': count, 'seconds': seconds})


@pytest.mark.skipif(PACKAGE != 'decord2', reason='other package lane')
def test_decord_video_frame_cadence_seek_and_memory(tmp_path):
    import decord
    oracle = frames()
    data = avi_fixture(oracle)
    path = tmp_path / 'oracle.avi'
    path.write_bytes(data)
    for source in (str(path), io.BytesIO(data)):
        reader = decord.VideoReader(source, ctx=decord.cpu(0), num_threads=1)
        assert len(reader) == 12
        assert abs(reader.get_avg_fps() - 12) < 1e-6
        decoded = reader.get_batch(list(range(12))).asnumpy()
        np.testing.assert_array_equal(decoded, oracle)
        np.testing.assert_array_equal(reader.get_batch([11, 0, 6, 6, 2]).asnumpy(), oracle[[11, 0, 6, 6, 2]])
        stamps = reader.get_frame_timestamp(list(range(12)))
        np.testing.assert_allclose(stamps[:, 0], np.arange(12) / 12, atol=1e-6)
        reader.seek_accurate(3)
        np.testing.assert_array_equal(reader.next().asnumpy(), oracle[3])
        held = reader[5]
        del reader
        np.testing.assert_array_equal(held.asnumpy(), oracle[5])
        with pytest.raises(AssertionError):
            np.testing.assert_array_equal(decoded, np.zeros_like(decoded))
    with pytest.raises(Exception):
        decord.VideoReader(io.BytesIO(b'not a video'), ctx=decord.cpu(0))

"""Architecture regression: the interpreter ABI wins over host ISA."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('defs', Path(__file__).parents[1] / 'imageio_ffmpeg/_definitions.py')
defs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(defs)

class WindowsArchitecture(unittest.TestCase):
    def test_arm64_native(self):
        with patch.object(defs.sys, 'platform', 'win32'), patch.object(defs.platform, 'machine', return_value='ARM64'), patch('sysconfig.get_platform', return_value='win-arm64'):
            self.assertEqual(defs.get_platform(), 'windows-aarch64')
    def test_amd64_interpreter_on_arm_host(self):
        with patch.object(defs.sys, 'platform', 'win32'), patch.object(defs.platform, 'machine', return_value='ARM64'), patch('sysconfig.get_platform', return_value='win-amd64'):
            self.assertEqual(defs.get_platform(), 'windows-x86_64')

if __name__ == '__main__':
    unittest.main()

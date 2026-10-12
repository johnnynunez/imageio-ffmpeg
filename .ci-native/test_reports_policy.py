"""Artifact policy regression, including the retained historical ZIP."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

HERE = Path(__file__).parent

class ReportsPolicy(unittest.TestCase):
    def test_binary_and_unlisted_names_rejected(self):
        spec = importlib.util.spec_from_file_location('reports_policy', HERE/'reports_policy.py')
        self.assertTrue(Path(spec.origin).exists(), 'strict reports filter not implemented')
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for name, data in [('bad.pyc', b'abc'), ('unexpected.txt', b'text'), ('version.txt', b'MZ\0binary'), ('version.txt', b'\xff\xfe'), ('../version.txt', b'text')]:
            with self.subTest(name=name, data=data):
                with self.assertRaises(ValueError):
                    mod.validate(name, data)
        mod.validate('version.txt', b'ffmpeg n7.1\n')

    def test_actual_retained_zip_is_rejected_without_changes(self):
        original = os.environ.get('RETAINED_R2_ZIP')
        if not original:
            self.skipTest('historical archive supplied by local or CI caller')
        import reports_policy as mod
        import hashlib
        p = Path(original)
        before = hashlib.sha256(p.read_bytes()).hexdigest()
        self.assertEqual(before, 'd0200691d7ddadd0798a55634ee674ceca7156dcd58e35ef056586ceb3750c2c')
        with self.assertRaisesRegex(ValueError, 'pyc'):
            mod.audit_zip(p)
        with tempfile.TemporaryDirectory() as d:
            report = mod.filter_zip(p, Path(d)/'filtered')
            self.assertEqual(report['rejected'], ['__pycache__/test_bundled_r2.cpython-312-pytest-9.1.1.pyc'])
            self.assertEqual(report['accepted_count'], 38)
            out = Path(d)/'clean.zip'
            with zipfile.ZipFile(out, 'w') as z:
                for f in sorted((Path(d)/'filtered').iterdir()):
                    z.write(f, f.name)
            self.assertEqual(mod.audit_zip(out)['count'], 38)
        self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), before)

if __name__ == '__main__':
    unittest.main()

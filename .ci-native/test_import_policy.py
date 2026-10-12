"""Regression for observed FFmpeg imports; preserve unknown-DLL rejection."""
import ast
from pathlib import Path
import unittest

TREE=ast.parse(Path(__file__).with_name('package_r2.py').read_text())
ALLOWED=next(ast.literal_eval(node.value) for node in ast.walk(TREE) if isinstance(node, ast.Assign) and any(isinstance(t,ast.Name) and t.id=='allowed' for t in node.targets))

class ImportPolicy(unittest.TestCase):
    def test_observed_documented_os_imports(self):
        observed={'avicap32.dll','bcrypt.dll','gdi32.dll','kernel32.dll','ole32.dll','oleaut32.dll','psapi.dll','shell32.dll','shlwapi.dll','user32.dll'}
        self.assertEqual(observed-ALLOWED, set())

    def test_vendor_runtimes_not_treated_as_os(self):
        self.assertTrue({'msvcp140.dll','vcruntime140.dll','avcodec-62.dll','libc++.dll'}.isdisjoint(ALLOWED))

if __name__=='__main__':
    unittest.main()

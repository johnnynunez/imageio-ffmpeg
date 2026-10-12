import importlib.util
from pathlib import Path
import tempfile
import unittest

class Attribution(unittest.TestCase):
    def test_dependency_notice_includes_template(self):
        path=Path(__file__).with_name('attribution_r3.py')
        self.assertTrue(path.exists(), 'compiled-source attribution missing')
        spec=importlib.util.spec_from_file_location('attribution_r3',path)
        mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'unit.c').write_text('/* BSD-like unit notice */\n#include "template.h"\n')
            (root/'template.h').write_text('/* IJG notice in a compiled template */\n')
            (root/'unit.d').write_text('unit.o: unit.c \\\n template.h\n')
            inventory=mod.compiled_sources(root)
            self.assertEqual(set(inventory), {'unit.c','template.h'})
            self.assertIn('IJG notice',mod.comments((root/'template.h').read_text()))

if __name__=='__main__': unittest.main()

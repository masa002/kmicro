"""toolchain/kn.py def_headers(): the files whose change re-runs cinterop for kbuild --def (no compiler needed).

python -m unittest discover -s tests/unit
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'toolchain'))
import kn  # noqa: E402


class DefHeaders(unittest.TestCase):
    def test_named_and_neighbouring_headers(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / 'inc').mkdir()
            for f in ('api.h', 'util.h', 'inc/board.h', 'inc/regs.h'):
                (d / f).write_text('\n')
            (d / 'api.def').write_text('headers = api.h \\\n    board.h\npackage = c\n---\nstatic int x;\n')
            got = kn.def_headers(d / 'api.def', [d / 'inc'])
        self.assertEqual([p.relative_to(d).as_posix() for p in got],
                         ['api.h', 'inc/board.h', 'util.h', 'inc/regs.h'])

    def test_repo_cinterop_test(self):
        root = Path(__file__).resolve().parents[2] / 'tests/cinterop'
        self.assertEqual([p.name for p in kn.def_headers(root / 'kernel.def')], ['kernel.h'])


if __name__ == '__main__':
    unittest.main()

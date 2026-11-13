"""toolchain/kn.py c_prototypes(): the --c-api prototypes of a header, read by clang (skipped without the LLVM that
Kotlin/Native downloads).

python -m unittest discover -s tests/unit
"""
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'toolchain'))
import kn  # noqa: E402
import paths  # noqa: E402

HAVE_CLANG = (lambda p: p is not None and (p / f'clang{paths.EXE}').exists())(
    paths._find(paths.llvm.env, paths.llvm.patterns, paths.llvm.what, paths.llvm.tool))


@unittest.skipUnless(HAVE_CLANG, "no clang (Kotlin/Native's LLVM)")
class Prototypes(unittest.TestCase):
    def test_fixture(self):
        self.assertEqual(kn.c_prototypes(HERE / 'fixtures/cproto.h'),
                         ['system_init', 'gpio_set', 'EXTI0_IRQHandler', 'set_cb2', 'gc_chains', 'die',
                          'kt_init_all', 'ready'])

    def test_examples(self):
        root = HERE.parents[1]
        self.assertEqual(kn.c_prototypes(root / 'examples/hello/hello.h'), ['hello'])

    def test_include_dirs_and_defines(self):
        with tempfile.TemporaryDirectory() as d:
            inc, h = Path(d) / 'inc', Path(d) / 'api.h'
            inc.mkdir()
            (inc / 'board.h').write_text('#define HAVE_LED 1\n')
            h.write_text('#include "board.h"\n#if HAVE_LED\nvoid led(int on);\n#endif\n'
                         '#ifdef EXTRA\nvoid extra(void);\n#endif\n')
            with self.assertRaises(SystemExit) as e:
                kn.c_prototypes(h)
            self.assertIn('board.h', str(e.exception))
            self.assertEqual(kn.c_prototypes(h, include_dirs=[inc]), ['led'])
            self.assertEqual(kn.c_prototypes(h, include_dirs=[inc], defines=['EXTRA']), ['led', 'extra'])


if __name__ == '__main__':
    unittest.main()

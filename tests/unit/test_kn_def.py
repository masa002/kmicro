"""toolchain/kn.py def_headers(): the files whose change re-runs cinterop for kbuild --def, listed by clang (skipped
without the LLVM that Kotlin/Native downloads).

python -m unittest discover -s tests/unit
"""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'toolchain'))
import kn  # noqa: E402
import paths  # noqa: E402

HAVE_CLANG = (lambda p: p is not None and (p / f'clang{paths.EXE}').exists())(
    paths._find(paths.llvm.env, paths.llvm.patterns, paths.llvm.what, paths.llvm.tool))

FILES = {'api.h': '#include <stdint.h>\n#include "regs/version.h"\n#include "gone.h"\n'
                  '#ifdef WITH_TRACE\n#include "trace.h"\n#endif\n',
         'regs/version.h': '#define VERSION 1\n', 'trace.h': '\n', 'util.h': '\n',
         'inc/board.h': '#include "pins/map.h"\n', 'inc/pins/map.h': '\n', 'inc/regs.h': '\n',
         'linux.h': '\n', 'arm32.h': '\n', 'target.h': '\n', 'osx.h': '\n', 'tail.h': '\n',
         'api.def': 'headers = api.h \\\n    board.h\nheaders.linux = linux.h\nheaders.arm32 = arm32.h\n'
                    'headers.linux_arm32_hfp = target.h\nheaders.osx = osx.h\ncompilerOpts = -DWITH_TRACE\n'
                    'package = c\n---\n#include "tail.h"\nstatic int x;\n'}


@unittest.skipUnless(HAVE_CLANG, 'no clang (the LLVM of Kotlin/Native)')
class DefHeaders(unittest.TestCase):
    def test_every_header_clang_reads(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for name, text in FILES.items():
                (d / name).parent.mkdir(parents=True, exist_ok=True)
                (d / name).write_text(text)
            got = kn.def_headers(d / 'api.def', [d / 'inc'])
            mine = sorted(p.relative_to(d).as_posix() for p in got if d in p.parents)
        # not util.h and inc/regs.h (nothing includes them), osx.h (another target), gone.h (it does not exist)
        self.assertEqual(mine, ['api.h', 'arm32.h', 'inc/board.h', 'inc/pins/map.h', 'linux.h', 'regs/version.h',
                                'tail.h', 'target.h', 'trace.h'])
        self.assertIn('stdint.h', [p.name for p in got])

    def test_option_clang_refuses(self):
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stderr(io.StringIO()) as err:
            (Path(d) / 'api.def').write_text('headers = api.h\ncompilerOpts = --no-such-option\n')
            self.assertEqual(kn.def_headers(Path(d) / 'api.def'), [])
        self.assertIn('warning: clang cannot list the headers of', err.getvalue())
        self.assertIn('--no-such-option', err.getvalue())

    def test_repo_cinterop_test(self):
        root = Path(__file__).resolve().parents[2] / 'tests/cinterop'
        self.assertEqual([p.name for p in kn.def_headers(root / 'kernel.def') if root in p.parents], ['kernel.h'])


if __name__ == '__main__':
    unittest.main()

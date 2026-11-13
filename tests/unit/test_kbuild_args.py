"""tools/kbuild.py command line (no compiler needed).

python -m unittest discover -s tests/unit
"""
import contextlib
import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import kbuild  # noqa: E402

HELLO = str(ROOT / 'examples/hello/hello.kt')
HEADER = str(ROOT / 'examples/hello/hello.h')


def parse(*argv):
    return kbuild.parse(['build/x', HELLO, *argv])


def error(*argv):
    err = io.StringIO()
    with contextlib.redirect_stderr(err), unittest.TestCase().assertRaises(SystemExit) as e:
        parse(*argv)
    msg = err.getvalue().strip()
    assert e.exception.code == 2 and len(msg.splitlines()) == 1, msg
    return msg


class Args(unittest.TestCase):
    def test_kotlinc_options_with_a_dash(self):
        a = parse('--kotlinc', '-Xbinary=latin1Strings=true', '--kotlinc', '-ea', '--kotlinc=-opt-in=x.Y')
        self.assertEqual(a.kotlinc_args, ['-Xbinary=latin1Strings=true', '-ea', '-opt-in=x.Y'])

    def test_options_between_sources(self):
        a = kbuild.parse(['build/x', HELLO, '--package', 'hello', '--c-api', HEADER, HELLO])
        self.assertEqual(len(a.sources), 2)
        self.assertEqual(a.package, 'hello')

    def test_root_package(self):
        self.assertEqual(parse('--c-api', HEADER, '--package', '').package, '')

    def test_bad_invocations_are_one_line(self):
        self.assertIn('unknown option -ea', error('-ea'))
        self.assertIn('--kotlinc -ea', error('-ea'))
        self.assertIn('expected one argument', error('--package'))
        self.assertIn('--hot needs --size', error('--hot', 'foo'))
        self.assertIn('need --package', error('--c-api', HEADER))
        self.assertIn('nope.klib: not found', error('-l', 'nope.klib'))
        self.assertIn('ad.kt: not found', error(str(ROOT / 'tests/add/ad.kt')))
        self.assertIn('unknown option --kotlin-args', error('--kotlin-args', 'x'))


if __name__ == '__main__':
    unittest.main()

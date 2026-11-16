# Copyright 2026 the kmicro authors (NOTICE).
# SPDX-License-Identifier: Apache-2.0
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

    def test_kotlinc_option_with_a_separate_value(self):
        a = parse('--kotlinc', '-language-version', '--kotlinc', '2.3', '--kotlinc=-module-name', '--kotlinc=app')
        self.assertEqual(a.kotlinc_args, ['-language-version', '2.3', '-module-name', 'app'])
        a = parse('--kotlinc', '-linker-option', '--kotlinc', '-o', HELLO)      # a value that is an option's name
        self.assertEqual((a.kotlinc_args, len(a.sources)), (['-linker-option', '-o'], 2))
        self.assertEqual(parse('--kotlinc', '-module-name').kotlinc_args, ['-module-name'])

    def test_kotlinc_option_typed_as_for_kotlinc(self):
        right = '--kotlinc -language-version --kotlinc 2.3'
        self.assertIn('unknown option -language-version (a kotlinc-native option goes through --kotlinc, each word '
                      f'through its own: {right})', error('-language-version', '2.3'))
        self.assertIn('--kotlinc -language-version 2.3: each word of a kotlinc-native option goes through its own '
                      f'--kotlinc: {right}', error('--kotlinc', '-language-version', '2.3'))
        # the value is no Kotlin source, although a folder of that name exists
        tests = str(ROOT / 'tests')
        self.assertIn(f'--kotlinc -module-name --kotlinc {tests}', error('--kotlinc', '-module-name', tests))
        self.assertIn(f'--kotlinc -module-name --kotlinc {tests}', error('--kotlinc=-module-name', tests))
        self.assertIn('unknown option -module-name (a kotlinc-native option goes through --kotlinc: --kotlinc '
                      '-module-name)', error('-module-name', '--size'))
        self.assertIn('unknown option -linker-options', error('-linker-options', 'x'))
        self.assertIn('unknown option -library: kbuild takes a klib with its own -l: -l x.klib',
                      error('-library', 'x.klib'))
        self.assertIn('--kotlinc -l: kbuild takes a klib with its own -l: -l x.klib',
                      error('--kotlinc', '-l', 'x.klib'))

    def test_kotlinc_option_read_as_a_klib(self):
        self.assertIn('-l ist-targets: not found (-list-targets is read as -l ist-targets; a kotlinc-native option '
                      'goes through --kotlinc: --kotlinc -list-targets)', error('-list-targets'))
        self.assertTrue(error('-lnope.klib').endswith('-l nope.klib: not found'))
        self.assertTrue(error('-l', 'ist-targets').endswith('-l ist-targets: not found'))
        self.assertEqual(parse('--kotlinc', '-list-targets').kotlinc_args, ['-list-targets'])

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


class Output(unittest.TestCase):
    """main() with a stdout and a stderr that cannot encode every character, as a pipe on Windows, where Python
    writes the ANSI code page. kn.build is replaced: no compiler runs."""

    def run_main(self, *argv, objs=()):
        saved = sys.argv, sys.stdout, sys.stderr, kbuild.kn.build
        out = io.TextIOWrapper(io.BytesIO(), encoding='ascii', errors='strict')
        err = io.TextIOWrapper(io.BytesIO(), encoding='ascii', errors='backslashreplace')
        sys.argv, sys.stdout, sys.stderr, kbuild.kn.build = ['kbuild.py', *argv], out, err, lambda *a, **k: objs
        try:
            kbuild.main()
            code = 0
        except SystemExit as e:
            code = e.code
        finally:
            sys.argv, sys.stdout, sys.stderr, kbuild.kn.build = saved
        out.flush()
        err.flush()
        return code, *(s.buffer.getvalue().decode('utf-8').splitlines() for s in (out, err))

    def test_objects_in_a_folder_with_any_name(self):
        objs = [Path('build') / 'café テスト' / name for name in ('k.o', 'bridges.o')]
        self.assertEqual(self.run_main('build/x', HELLO, objs=objs), (0, [str(o) for o in objs], []))

    def test_error_names_the_file(self):
        self.assertEqual(self.run_main('build/x', 'café.kt'), (2, [], ['kbuild.py: error: café.kt: not found']))


if __name__ == '__main__':
    unittest.main()

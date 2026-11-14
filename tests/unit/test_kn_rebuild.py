"""toolchain/kn.py compile_ir(): when the saved IR is reused and when kotlinc-native runs again, and the klibs of
kbuild --def (no compiler needed: the compiler call is replaced by a fake that writes the IR files or the klib).

python -m unittest discover -s tests/unit
"""
import contextlib
import io
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'toolchain'))
import kn  # noqa: E402
import paths  # noqa: E402


def fake_dist(where, version='2.4.21'):
    (where / 'konan/lib').mkdir(parents=True)
    (where / 'konan/konan.properties').write_text(f'compilerVersion={version}\n')
    (where / 'konan/lib/kotlin-native-compiler-embeddable.jar').write_bytes(b'jar')
    return where


class Rebuild(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.dist = fake_dist(self.d / 'kn1')
        self.saved = paths.run_kn, paths.kotlin_native
        self.calls = 0
        self.fail = False

        def run_kn(tool, args):
            self.calls += 1
            if self.fail:
                return SimpleNamespace(returncode=1, stdout='', stderr='e.kt:1:1: error: boom\n')
            if tool == 'cinterop':
                Path(args[args.index('-o') + 1] + '.klib').write_text('klib\n')
                return SimpleNamespace(returncode=0, stdout='', stderr='')
            for name in ('out.Codegen.ll', 'out.LinkBitcodeDependencies.ll'):
                (self.d / 'out/ir' / name).write_text('; ir\n')
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        paths.run_kn = run_kn
        paths.kotlin_native = lambda: self.dist
        self.src = self.d / 'src'
        self.src.mkdir()
        self.a, self.b = self.src / 'a.kt', self.src / 'b.kt'
        self.a.write_text('fun a() = 1\n')
        self.b.write_text('fun b() = 2\n')

    def tearDown(self):
        paths.run_kn, paths.kotlin_native = self.saved
        self.tmp.cleanup()

    def compile(self, srcs=None, extra=()):
        before = self.calls
        with contextlib.redirect_stderr(io.StringIO()):     # 'kotlinc-native: compiling ...'
            kn.compile_ir(srcs if srcs is not None else [self.a, self.b], self.d / 'out', extra)
        return self.calls - before

    def touch_later(self, f, text):
        f.write_text(text)
        t = time.time() + 5
        os.utime(f, (t, t))

    def test_unchanged_is_reused(self):
        self.assertEqual(self.compile(), 1)
        self.assertEqual(self.compile(), 0)

    def test_removed_source(self):
        self.compile()
        self.assertEqual(self.compile([self.a]), 1)

    def test_added_option(self):
        self.compile()
        self.assertEqual(self.compile(extra=['-Xbinary=latin1Strings=true']), 1)
        self.assertEqual(self.compile(extra=['-Xbinary=latin1Strings=true']), 0)

    def test_file_inside_source_folder(self):
        self.assertEqual(self.compile([self.src]), 1)
        self.assertEqual(self.compile([self.src]), 0)
        self.touch_later(self.b, 'fun b() = 3\n')
        self.assertEqual(self.compile([self.src]), 1)
        (self.src / 'c.kt').write_text('fun c() = 4\n')
        self.assertEqual(self.compile([self.src]), 1)

    def test_file_with_an_older_time(self):
        self.compile()
        t = self.a.stat().st_mtime - 3600
        self.a.write_text('fun a() = 10\n')
        os.utime(self.a, (t, t))
        self.assertEqual(self.compile(), 1)

    def test_other_compiler(self):
        self.compile()
        self.dist = fake_dist(self.d / 'kn2')
        self.assertEqual(self.compile(), 1)

    def test_missing_source_is_one_line(self):
        with self.assertRaises(SystemExit) as e:
            self.compile([self.a, self.src / 'ad.kt'])
        self.assertIn('Kotlin source not found', str(e.exception))
        self.assertIn('ad.kt', str(e.exception))

    def test_failed_compile_is_not_current(self):
        self.compile()
        self.touch_later(self.a, 'fun a() = 11\n')
        self.fail = True
        with self.assertRaises(SystemExit):
            self.compile()
        self.fail = False
        self.assertEqual(self.compile(), 1)

    def test_two_defs_with_one_file_name(self):
        defs = [self.d / 'uart/driver.def', self.d / 'spi/driver.def']
        for f in defs:
            f.parent.mkdir()
            f.write_text('headers = driver.h\n')

        def klibs():
            before = self.calls
            with contextlib.redirect_stderr(io.StringIO()):     # 'cinterop: ...'
                made = [kn.cinterop(f, kn.klib_base(f, self.d / 'out', defs)) for f in defs]
            return made, self.calls - before
        (uart, spi), runs = klibs()
        self.assertEqual((runs, uart.exists(), spi.exists()), (2, True, True))
        self.assertNotEqual(uart, spi)
        self.assertRegex(uart.name, r'^driver-[0-9a-f]{8}\.klib$')
        self.assertEqual(klibs(), ([uart, spi], 0))
        self.assertEqual(kn.klib_base(defs[0], self.d / 'out', defs[:1]), self.d / 'out/driver')


if __name__ == '__main__':
    unittest.main()

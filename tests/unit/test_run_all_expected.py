# Copyright 2026 the kmicro authors (NOTICE).
# SPDX-License-Identifier: Apache-2.0
"""tests/run_all.py expected_file(): which file a test's output is compared with, by architecture and by the
feature release of the Kotlin/Native in use (no toolchain needed).

python -m unittest discover -s tests/unit
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests'))
import run_all  # noqa: E402


class ExpectedFile(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        for rel in ('a.txt', 'b.txt', 'c.txt', 'd.txt', 'thumbv6m/b.txt', 'thumbv6m/d.txt', 'kotlin-2.5/c.txt',
                    'kotlin-2.5/d.txt', 'kotlin-2.5/thumbv6m/d.txt'):
            (self.dir / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.dir / rel).write_text('', encoding='utf-8')

    def files(self, version, arch, kotlin=True):
        with mock.patch.object(run_all, 'EXPECTED', self.dir), \
                mock.patch.object(run_all.paths, 'kotlin_native_version', lambda: version), \
                mock.patch.object(run_all.paths, 'arch', lambda: arch):
            return [run_all.expected_file(n, kotlin).relative_to(self.dir).as_posix() for n in 'abcd']

    def test_tested_release(self):
        self.assertEqual(self.files('2.4.21', 'thumbv7em'), ['a.txt', 'b.txt', 'c.txt', 'd.txt'])
        self.assertEqual(self.files('2.4.21', 'thumbv6m'), ['a.txt', 'thumbv6m/b.txt', 'c.txt', 'thumbv6m/d.txt'])

    def test_another_release(self):
        for version in ('2.5.0-RC', '2.5.0', '2.5.20'):
            self.assertEqual(self.files(version, 'thumbv7em'),
                             ['a.txt', 'b.txt', 'kotlin-2.5/c.txt', 'kotlin-2.5/d.txt'])
            self.assertEqual(self.files(version, 'thumbv6m'),
                             ['a.txt', 'thumbv6m/b.txt', 'kotlin-2.5/c.txt', 'kotlin-2.5/thumbv6m/d.txt'])

    def test_a_test_without_kotlin_code_does_not_ask_for_the_compiler(self):
        def no_compiler():
            raise AssertionError('asked for the version of Kotlin/Native')
        with mock.patch.object(run_all, 'EXPECTED', self.dir), \
                mock.patch.object(run_all.paths, 'kotlin_native_version', no_compiler), \
                mock.patch.object(run_all.paths, 'arch', lambda: 'thumbv6m'):
            self.assertEqual(run_all.expected_file('d').relative_to(self.dir).as_posix(), 'thumbv6m/d.txt')

    def test_missing_file_is_named_in_the_main_folder(self):
        with mock.patch.object(run_all, 'EXPECTED', self.dir), \
                mock.patch.object(run_all.paths, 'kotlin_native_version', lambda: '2.5.0-RC'), \
                mock.patch.object(run_all.paths, 'arch', lambda: 'thumbv7em'):
            self.assertEqual(run_all.expected_file('none', True), self.dir / 'none.txt')


if __name__ == '__main__':
    unittest.main()

# Copyright 2026 the kmicro authors (NOTICE).
# SPDX-License-Identifier: Apache-2.0
"""tools/difftest.py: the `// difftest: ...` lines of a program (no compiler needed).

python -m unittest discover -s tests/unit
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
import difftest  # noqa: E402


def directives(text):
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / 'd_program.kt'
        src.write_text(text, encoding='utf-8')
        return difftest.directives(src)


class Directives(unittest.TestCase):
    def test_numbers_and_flags(self):
        self.assertEqual(directives('// difftest: heap 32768 -- why\n// difftest: ulp 2 -- why\n'
                                    '// difftest: large -- why\n// difftest: frame -- why\nfun main() {}\n'),
                         {'heap': 32768, 'ulp': 2, 'large': True, 'frame': True})

    def test_a_program_without_directives(self):
        self.assertEqual(directives('fun main() {}\n'), {})

    def test_bad_directives(self):
        for line in ('// difftest: frame 8192 -- a flag with a number', '// difftest: large 1 -- a flag with a number',
                     '// difftest: heap -- no number', '// difftest: stack 4096 -- no such directive'):
            with self.assertRaises(difftest.Failure, msg=line):
                directives(line + '\n')


class UlpTolerance(unittest.TestCase):
    def close(self, golden, got, ulps=1):
        return difftest.close(golden.encode(), got.encode(), ulps)

    def test_a_double_is_compared_as_a_double_however_short_it_prints(self):
        self.assertFalse(self.close('x = 2.5\n', 'x = 2.5000002\n'))
        self.assertFalse(self.close('1.0E10\n', '1.0000001E10\n'))
        self.assertTrue(self.close('x = 2.5\n', 'x = 2.5000000000000004\n'))
        self.assertFalse(self.close('x = 2.5\n', 'x = 2.500000000000001\n'))
        self.assertTrue(self.close('x = 2.5\n', 'x = 2.500000000000001\n', 2))
        self.assertTrue(self.close('0.0 -0.0\n', '-0.0 0.0\n'))

    def test_a_number_marked_f_is_compared_as_a_float(self):
        self.assertTrue(self.close('sin=0.84147096f\n', 'sin=0.841471f\n'))
        self.assertFalse(self.close('sin=0.84147096f\n', 'sin=0.84147105f\n'))
        self.assertTrue(self.close('sin=0.84147096f\n', 'sin=0.84147105f\n', 2))
        self.assertFalse(self.close('2.5f 2.5\n', '2.5f 2.5000002\n'))
        self.assertFalse(self.close('2.5foo\n', '2.5000002foo\n'))        # no mark: a word that begins with f
        self.assertFalse(self.close('1.0E300f\n', '1.0000000000000002E300f\n'))    # no Float is that large

    def test_integers_and_text_must_be_equal(self):
        self.assertFalse(self.close('sum 16777216\n', 'sum 16777217\n'))
        self.assertFalse(self.close('hash 123456789\n', 'hash 123456792\n'))
        self.assertFalse(self.close('n 3\n', 'n 3.0000000000000004\n'))
        self.assertFalse(self.close('x = 2.5\n', 'y = 2.5\n'))
        self.assertFalse(self.close('NaN\n', '1.0\n'))
        self.assertFalse(self.close('Infinity\n', '1.7976931348623157E308\n'))
        self.assertTrue(self.close('NaNf Infinity -Infinity 7\n', 'NaNf Infinity -Infinity 7\n'))


if __name__ == '__main__':
    unittest.main()

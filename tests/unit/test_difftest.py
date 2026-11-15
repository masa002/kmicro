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
        self.assertEqual(directives('// difftest: uncaught -- why\nfun main() {}\n'), {'uncaught': True})

    def test_a_program_without_directives(self):
        self.assertEqual(directives('fun main() {}\n'), {})

    def test_bad_directives(self):
        for line in ('// difftest: frame 8192 -- a flag with a number', '// difftest: large 1 -- a flag with a number',
                     '// difftest: heap -- no number', '// difftest: stack 4096 -- no such directive'):
            with self.assertRaises(difftest.Failure, msg=line):
                directives(line + '\n')


class Frameless(unittest.TestCase):
    def test_frame_lines_go_and_the_rest_stays(self):
        host = (b'before\nUncaught Kotlin exception: kotlin.Error: top\n'
                b'    at 0   d_x.kexe    0x41a3f1    kfun:kotlin.Throwable#<init>(kotlin.String?){} + 97 \n'
                b'    Suppressed: kotlin.Error: at sea\n        at 1   d_x.kexe    0x41a400    kfun:#main(){} + 5 \n'
                b'        ... and 3 more common stack frames skipped\nCaused by: kotlin.Error: ... and more\n')
        kmicro = (b'before\nUncaught Kotlin exception: kotlin.Error: top\n    at 0x08001234\n'
                  b'    Suppressed: kotlin.Error: at sea\n        at 0x08001240\n'
                  b'        ... and 3 more common stack frames skipped\nCaused by: kotlin.Error: ... and more\n')
        text = (b'before\nUncaught Kotlin exception: kotlin.Error: top\n    Suppressed: kotlin.Error: at sea\n'
                b'Caused by: kotlin.Error: ... and more\n')
        self.assertEqual(difftest.frameless(host), text)
        self.assertEqual(difftest.frameless(kmicro), text)
        self.assertEqual(difftest.frameless(host.replace(b'\n', b'\r\n')), text.replace(b'\n', b'\r\n'))


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

    def test_the_numbers_are_counted_not_their_digits_subtracted(self):
        # The digits of a Float are up to half a unit away from it: the neighbours 0.1f and 0.10000001f are 1.3 units
        # apart as decimals.
        self.assertTrue(self.close('0.1f\n', '0.10000001f\n'))
        self.assertFalse(self.close('0.1f\n', '0.10000002f\n'))
        self.assertTrue(self.close('0.1f\n', '0.10000002f\n', 2))
        self.assertFalse(self.close('0.1f\n', '0.100000024f\n', 2))
        self.assertTrue(self.close('3.4028235E38f\n', '3.4028233E38f\n'))         # Float.MAX_VALUE and the one below
        self.assertFalse(self.close('3.4028235E38f\n', '3.5E38f\n', 100))         # no Float
        self.assertTrue(self.close('1.4E-45f -1.4E-45f\n', '0.0f -0.0f\n'))        # Float.MIN_VALUE next to zero
        self.assertFalse(self.close('1.4E-45f\n', '-1.4E-45f\n'))

    def test_the_unit_is_the_same_from_both_sides_of_a_power_of_two(self):
        for one, below in (('1.0f', '0.99999994f'), ('1.0', '0.9999999999999999')):
            self.assertTrue(self.close(one + '\n', below + '\n'))
            self.assertTrue(self.close(below + '\n', one + '\n'))
        for one, below in (('1.0f', '0.9999999f'), ('1.0', '0.9999999999999998')):  # two numbers below 1
            self.assertFalse(self.close(one + '\n', below + '\n'))
            self.assertFalse(self.close(below + '\n', one + '\n'))
            self.assertTrue(self.close(one + '\n', below + '\n', 2))

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

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


if __name__ == '__main__':
    unittest.main()

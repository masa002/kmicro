# Copyright 2026 the kmicro authors (NOTICE).
# SPDX-License-Identifier: Apache-2.0
"""Numbers the documents give for tests/run_all.py, compared with its list of tests (no toolchain needed).

python -m unittest discover -s tests/unit
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests'))
import run_all  # noqa: E402

WORDS = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten']


def text(path):
    """The document as one line, so that a sentence is found wherever its lines break."""
    return ' '.join((ROOT / path).read_text(encoding='utf-8').split())


class Counts(unittest.TestCase):
    def test_tests_on_the_large_memory_machine(self):
        n = WORDS[sum(t.target == 'an386' for t in run_all.TESTS)]
        self.assertIn(f'{n} tests on `mps2-an386`', text('docs/how-it-works.md'))
        self.assertIn(f'The {n} tests of the large-memory machine, `mps2-an386`', text('docs/roadmap.md'))


if __name__ == '__main__':
    unittest.main()

# Copyright 2026 the kmicro authors (NOTICE).
# SPDX-License-Identifier: Apache-2.0
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class KbuildOptions(unittest.TestCase):
    def test_inline_kotlinc_options_get_hint(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'app.kt').write_text('fun main() {}\n', encoding='utf-8')
            for option in ('-language-version=2.3', '-library=x.klib', '-linker-option=-lfoo'):
                with self.subTest(option=option):
                    result = subprocess.run(
                        [sys.executable, str(ROOT / 'tools/kbuild.py'), 'build/app', 'app.kt', option],
                        cwd=directory, capture_output=True, text=True,
                    )
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn(f'a kotlinc-native option goes through --kotlinc: --kotlinc {option}', result.stderr)


if __name__ == '__main__':
    unittest.main()

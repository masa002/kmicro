# Copyright 2026 the kmicro authors (NOTICE).
# SPDX-License-Identifier: Apache-2.0
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from isr_check import analyse  # noqa: E402


class ThreadLocalFirstUseTests(unittest.TestCase):
    def test_handler_reports_thread_local_first_use(self):
        for initializer in ('CallInitThreadLocal', 'kmicro_init_thread_local'):
            with self.subTest(initializer=initializer):
                disassembly = (
                    '08000100 <SysTick_Handler>:\n'
                    f' 8000100:\tbl 8000110 <{initializer}>\n'
                    f'08000110 <{initializer}>:\n'
                    ' 8000110:\tblx r3\n'
                )
                lines, _, _ = analyse(disassembly, '')
                self.assertIn(f'LAZY   SysTick_Handler: SysTick_Handler -> {initializer}', lines)


if __name__ == '__main__':
    unittest.main()

# Copyright 2026 the kmicro authors (NOTICE).
# SPDX-License-Identifier: Apache-2.0
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import insn_check  # noqa: E402


class InstructionAvailability(unittest.TestCase):
    def test_cpu_requirements(self):
        cases = (
            ('vmov.8 d0[1], r0', 'cortex-m55-nomve', 'cortex-m55'),
            ('vmov.u8 r0, d0[1]', 'cortex-m4f', 'cortex-m55'),
            ('vmov.s16 r0, d0[1]', 'cortex-m4f', 'cortex-m55'),
            ('vmov.32 d0[1], r0', 'cortex-m4', 'cortex-m4f'),
            ('msr MSPLIM, r0', 'cortex-m0plus', 'cortex-m23'),
            ('mrs r0, PSPLIM', 'cortex-m0plus', 'cortex-m23'),
            ('msr MSP_NS, r0', 'cortex-m3', 'cortex-m33'),
            ('msr APSR_g, r0', 'cortex-m23', 'cortex-m4'),
            ('vstr FPSCR_nzcvqc, [r0]', 'cortex-m4f', 'cortex-m55-nomve'),
            ('vldr FPCXTNS, [sp]', 'cortex-m7', 'cortex-m55'),
            ('vmsr FPSCR_nzcvqc, r0', 'cortex-m33f', 'cortex-m55'),
            ('vmrs r0, FPCXTNS', 'cortex-m33f', 'cortex-m55'),
            ('vlstm r0', 'cortex-m4f', 'cortex-m33'),
            ('vlldm r0', 'cortex-m23', 'cortex-m55-nofp'),
        )
        for instruction, unsupported, supported in cases:
            with self.subTest(instruction=instruction):
                mnemonic, operands = instruction.split(' ', 1)
                need = insn_check.needs(True, mnemonic, operands)
                self.assertTrue(need - insn_check.features(unsupported), unsupported)
                self.assertEqual(need - insn_check.features(supported), set(), supported)


if __name__ == '__main__':
    unittest.main()

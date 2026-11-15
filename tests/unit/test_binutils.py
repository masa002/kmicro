# Copyright 2026 the kmicro authors (NOTICE).
# SPDX-License-Identifier: Apache-2.0
"""toolchain/binutils.py: the architecture objdump is told for an ARMv8.1-M core. The last test assembles an MVE
instruction and reads it back (skipped when the LLVM of Kotlin/Native or arm-none-eabi-gcc is not installed).

python -m unittest discover -s tests/unit
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'toolchain'))
import binutils  # noqa: E402
import paths  # noqa: E402

HAVE_TOOLS = all(paths._find(t.env, t.patterns, t.what) for t in (paths.llvm, paths.arm_gcc))


def core(cpu):
    return mock.patch.dict(os.environ, {'KMICRO_CPU': cpu})


class Machine(unittest.TestCase):
    def test_objdump_is_told_the_architecture_of_an_armv81m_core_only(self):
        for cpu in paths.CORES:
            with core(cpu):
                want = ['-m', 'armv8.1-m.main'] if cpu.startswith(('cortex-m55', 'cortex-m85')) else []
                self.assertEqual(binutils.machine('objdump', ('-d',)), want, cpu)

    def test_other_tools_and_a_caller_who_names_the_architecture_are_left_alone(self):
        with core('cortex-m55'):
            self.assertEqual(binutils.machine('nm', ()), [])
            self.assertEqual(binutils.machine('size', ()), [])
            self.assertEqual(binutils.machine('objdump', ('-d', '-m', 'armv8-m.main')), [])

    def test_run_puts_it_before_the_callers_options(self):
        done = subprocess.CompletedProcess([], 0, '', '')
        with core('cortex-m55-nofp'), mock.patch.object(binutils.paths, 'gcc_bin', return_value=Path('objdump')), \
                mock.patch.object(binutils.subprocess, 'run', return_value=done) as run:
            binutils.run('objdump', Path('some/folder/app.elf'), '-d', '--no-show-raw-insn')
        self.assertEqual(run.call_args.args[0][1:], ['-m', 'armv8.1-m.main', '-d', '--no-show-raw-insn', 'app.elf'])


@unittest.skipUnless(HAVE_TOOLS, 'needs LLVM and arm-none-eabi-gcc (python toolchain/paths.py)')
class Disassembly(unittest.TestCase):
    def test_an_mve_instruction_shows_under_its_name(self):
        # an object with the build attributes of ARMv8-M Mainline, as newlib gives a linked image
        with tempfile.TemporaryDirectory() as d:
            src, obj = Path(d) / 'f.s', Path(d) / 'f.o'
            src.write_text('\t.syntax unified\n\t.thumb\n\t.cpu cortex-m33\nf:\n\t.inst.w 0xfcb40e88\n\tbx lr\n',
                           encoding='utf-8')
            subprocess.run([str(paths.clang()), '--target=thumbv8m.main-none-eabi', '-c', str(src), '-o', str(obj)],
                           check=True)
            with core('cortex-m33'):
                self.assertNotIn('vldrb.u16', binutils.output('objdump', obj, '-d'))
            with core('cortex-m55'):
                self.assertIn('vldrb.u16\tq0, [r4], #8', binutils.output('objdump', obj, '-d'))


if __name__ == '__main__':
    unittest.main()

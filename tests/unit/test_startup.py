# Copyright 2026 the kmicro authors (NOTICE).
# SPDX-License-Identifier: Apache-2.0
"""The QEMU l475 start code: fault report, stack guard, null guard and clocks, on the default core, on an ARMv8-M
one and on an ARMv8.1-M one, and the same probes on the start code of QEMU virt for the Cortex-A7 and of QEMU
mps3-an536 for the Cortex-R52. C programs only (startup_probe.c), no Kotlin compile.

usage: python -m unittest discover tests/unit       (skipped when LLVM, arm-none-eabi-gcc or QEMU is not installed)
"""
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'toolchain'))
import paths  # noqa: E402

HAVE_TOOLS = all(paths._find(t.env, t.patterns, t.what) for t in (paths.llvm, paths.arm_gcc, paths.qemu))


@unittest.skipUnless(HAVE_TOOLS, 'needs LLVM, arm-none-eabi-gcc and QEMU (python toolchain/paths.py)')
class StartupTest(unittest.TestCase):
    CPU = None                                  # qbuild --cpu; None: the default core (or KMICRO_CPU)

    def run_probe(self, probe):
        elf = ROOT / 'build/unit' / '-'.join(filter(None, ['startup', self.CPU])) / f'probe{probe}.elf'
        r = subprocess.run([sys.executable, ROOT / 'tools/qbuild.py', elf, Path(__file__).parent / 'startup_probe.c',
                            '-D', f'PROBE={probe}', '--run', *(['--cpu', self.CPU] if self.CPU else [])],
                           capture_output=True, text=True, errors='replace', timeout=300)
        return elf, r.returncode, r.stdout + r.stderr

    def symbolized(self, elf, log):
        """The fault line of the log as tools/symbolize.py rewrites it: the stacked PC is looked up as it is."""
        r = subprocess.run([sys.executable, ROOT / 'tools/symbolize.py', elf], input=log, capture_output=True,
                           text=True, encoding='utf-8', errors='replace')
        return next((line for line in r.stdout.splitlines() if 'kmicro fault:' in line), r.stdout + r.stderr)

    def test_fault_report_names_the_faulting_function(self):
        elf, rc, out = self.run_probe(1)
        self.assertEqual(rc, 99, out)
        m = re.search(r'kmicro fault: BusFault at (0x[0-9a-f]{8})\n    sp 0x[0-9a-f]{8}  lr 0x.*bfar 0xf0000000', out)
        self.assertTrue(m, out)
        self.assertIn('probe_bad_read+', self.symbolized(elf, out))

    def test_usage_fault(self):
        elf, rc, out = self.run_probe(2)
        self.assertEqual(rc, 99, out)
        m = re.search(r'kmicro fault: UsageFault at (0x[0-9a-f]{8})', out)
        self.assertTrue(m, out)
        self.assertIn('probe_undefined+', self.symbolized(elf, out))

    def test_stack_overflow_stops_before_bss(self):
        _, rc, out = self.run_probe(3)
        self.assertEqual(rc, 99, out)
        self.assertIn('kmicro fault: stack overflow (MemManage)', out)     # with or without a stacked frame
        self.assertNotIn('bss changed', out)

    def test_null_read_faults(self):
        elf, rc, out = self.run_probe(4)
        self.assertEqual(rc, 99, out)
        m = re.search(r'kmicro fault: null pointer access \(MemManage\) at (0x[0-9a-f]{8})\n.* mmfar 0x0000000c', out)
        self.assertTrue(m, out)
        self.assertIn('probe_null_read+', self.symbolized(elf, out))

    def test_clocks(self):
        _, rc, out = self.run_probe(5)
        self.assertEqual(rc, 0, out)
        self.assertIn('monotonic: ok', out)
        self.assertIn('wall clock: ok', out)


class StartupArmv8MTest(StartupTest):
    """The same start code on the Cortex-M33 of QEMU mps2-an505: the MPU of ARMv8-M, in the Secure state."""
    CPU = 'cortex-m33'


class StartupArmv81MTest(StartupTest):
    """The same code, built with MVE, on the Cortex-M55 of QEMU mps3-an547, which reads its reset words at address
    0: the linker script of that machine, and the guards on this core."""
    CPU = 'cortex-m55'


class StartupCortexATest(StartupTest):
    """The start code of QEMU virt (targets/qemu-virt) on its Cortex-A7. The guards are memory the MMU does not map,
    and the report names the exceptions of the A profile: a data abort, an undefined instruction."""
    CPU = 'cortex-a7'
    NOTHING = '0xf0000000'                      # startup_probe.c: the address of the bad read

    def test_fault_report_names_the_faulting_function(self):
        elf, rc, out = self.run_probe(1)
        self.assertEqual(rc, 99, out)
        m = re.search(r'kmicro fault: data abort at (0x[0-9a-f]{8})\n    sp 0x[0-9a-f]{8}  lr 0x.*dfar ' + self.NOTHING,
                      out)
        self.assertTrue(m, out)
        self.assertIn('probe_bad_read+', self.symbolized(elf, out))

    def test_usage_fault(self):
        elf, rc, out = self.run_probe(2)
        self.assertEqual(rc, 99, out)
        m = re.search(r'kmicro fault: undefined instruction at (0x[0-9a-f]{8})', out)
        self.assertTrue(m, out)
        self.assertIn('probe_undefined+', self.symbolized(elf, out))

    def test_stack_overflow_stops_before_bss(self):
        _, rc, out = self.run_probe(3)
        self.assertEqual(rc, 99, out)
        self.assertIn('kmicro fault: stack overflow (data abort)', out)
        self.assertNotIn('bss changed', out)

    def test_null_read_faults(self):
        elf, rc, out = self.run_probe(4)
        self.assertEqual(rc, 99, out)
        m = re.search(r'kmicro fault: null pointer access \(data abort\) at (0x[0-9a-f]{8})\n.* dfar 0x0000000c', out)
        self.assertTrue(m, out)
        self.assertIn('probe_null_read+', self.symbolized(elf, out))


class StartupCortexRTest(StartupCortexATest):
    """The start code of QEMU mps3-an536 (targets/qemu-an536) on its Cortex-R52: the same report as on the
    Cortex-A7, with guards that are addresses outside every region of the MPU."""
    CPU = 'cortex-r52'
    NOTHING = '0x70000000'


if __name__ == '__main__':
    unittest.main()

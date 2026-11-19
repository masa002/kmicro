# Copyright 2026 the kmicro authors (NOTICE).
# SPDX-License-Identifier: Apache-2.0
"""The runtime's interrupt mask and its atomics, compiled for the ARM cores before the profiles: an ARMv6K core
(ARM1176JZF-S), an ARMv5TE core (ARM926EJ-S) and an ARMv4T core (ARM7TDMI), as ARM code. Nothing runs here: the
test reads the machine code and the symbols (skipped when LLVM or arm-none-eabi-gcc is not installed).

python -m unittest discover -s tests/unit
"""
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'toolchain'))
import binutils  # noqa: E402
import paths  # noqa: E402

HAVE_TOOLS = all(paths._find(t.env, t.patterns, t.what) for t in (paths.llvm, paths.arm_gcc))
FLAGS = {'armv6k': ['--target=armv6kz-none-eabihf', '-mcpu=arm1176jzf-s', '-mfpu=vfpv2', '-mfloat-abi=hard'],
         'armv5te': ['--target=armv5e-none-eabi', '-mcpu=arm926ej-s', '-mfpu=none', '-mfloat-abi=soft'],
         'armv4t': ['--target=armv4t-none-eabi', '-mcpu=arm7tdmi', '-mfpu=none', '-mfloat-abi=soft']}
PROBE = '''#include "km_cpu.h"
#include "hw.h"
uint32_t probe_save(void) { return km_irq_save(); }
void probe_restore(uint32_t saved) { km_irq_restore(saved); }
uint32_t probe_handler(void) { return km_handler(); }
int probe_return(uintptr_t ra) { return km_handler_return(ra); }
'''


@unittest.skipUnless(HAVE_TOOLS, 'needs LLVM and arm-none-eabi-gcc (python toolchain/paths.py)')
class ClassicCores(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        (cls.dir / 'probe.c').write_text(PROBE, encoding='utf-8')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def compiled(self, arch, source):
        """The object of `source` for the core of `arch`, compiled as qbuild compiles the runtime, without LTO."""
        obj = self.dir / f'{arch}-{Path(source).stem}.o'
        if not obj.exists():
            r = subprocess.run([str(paths.clang()), *FLAGS[arch], '-isystem', str(paths.newlib_include()), '-O2',
                                '-Wall', '-Wextra', '-Werror', '-Wno-atomic-alignment', '-I', str(ROOT / 'runtime'),
                                '-I', str(ROOT / 'support'), '-c', str(source), '-o', str(obj)],
                               capture_output=True, text=True, errors='replace')
            self.assertEqual(r.returncode, 0, f'{arch} {source}\n{r.stderr}')
        return obj

    def function(self, arch, source, name):
        """The instructions of one function, as objdump prints them."""
        text = binutils.output('objdump', self.compiled(arch, source), '-d', '--no-show-raw-insn')
        m = re.search(rf'^[0-9a-f]+ <{name}>:\n((?:[ \t].*\n)+)', text, re.M)
        self.assertTrue(m, f'{arch} {name}\n{text}')
        return m.group(1)

    def defined(self, arch, source):
        """The functions an object defines."""
        return set(re.findall(r'^[0-9a-f]+ T (\w+)$', binutils.output('nm', self.compiled(arch, source)), re.M))

    def test_interrupts_are_masked_through_the_cpsr(self):
        # ARMv6 has cpsid; before it the I and F bits are set in a copy of the CPSR, which is written back
        code = self.function('armv6k', self.dir / 'probe.c', 'probe_save')
        self.assertRegex(code, r'mrs\tr\d, CPSR\n.*cpsid\tif\n')
        for arch in ('armv5te', 'armv4t'):
            code = self.function(arch, self.dir / 'probe.c', 'probe_save')
            self.assertRegex(code, r'mrs\tr0, CPSR\n.*orr\tr\d, r0, #192.*\n.*msr\tCPSR_c, r\d\n', arch)
            self.assertNotIn('cpsid', code, arch)
        for arch in FLAGS:
            self.assertRegex(self.function(arch, self.dir / 'probe.c', 'probe_restore'), r'msr\tCPSR_c, r0\n', arch)

    def test_a_handler_is_known_by_its_mode(self):
        for arch in FLAGS:
            code = self.function(arch, self.dir / 'probe.c', 'probe_handler')
            self.assertRegex(code, r'mrs\tr\d, CPSR\n', arch)
            self.assertRegex(code, r'and\tr\d, r\d, #31\n', arch)          # the mode bits

    def test_the_return_address_of_a_handler_lies_in_the_interrupt_entry(self):
        # as on the A and R profiles: between the two symbols a linker script puts around the entry's code
        for arch in FLAGS:
            symbols = binutils.output('nm', self.compiled(arch, self.dir / 'probe.c'))
            self.assertRegex(symbols, r' w _sirq_entry\b', arch)
            self.assertRegex(symbols, r' w _eirq_entry\b', arch)

    def test_the_atomics_mask_interrupts_where_the_core_has_no_exclusive_access(self):
        small = {f'__atomic_{op}_{n}' for n in (1, 2, 4)
                 for op in ('load', 'store', 'exchange', 'compare_exchange', 'fetch_add')}
        large = {f'__atomic_{op}_8' for op in ('load', 'store', 'exchange', 'compare_exchange', 'fetch_add')}
        for arch in ('armv5te', 'armv4t'):
            self.assertLessEqual(small, self.defined(arch, ROOT / 'runtime/atomic32.c'), arch)
            self.assertLessEqual(large, self.defined(arch, ROOT / 'runtime/atomic64.c'), arch)
            self.assertIn('msr\tCPSR_c', self.function(arch, ROOT / 'runtime/atomic32.c', '__atomic_fetch_add_4'))
        # ARMv6K has the exclusive loads and stores of every size, and the compiler uses them: no function of
        # these files may stand beside them
        self.assertEqual(self.defined('armv6k', ROOT / 'runtime/atomic32.c'), set())
        self.assertEqual(self.defined('armv6k', ROOT / 'runtime/atomic64.c'), set())

    def test_the_hardware_helpers_compile(self):
        # support/hw.c: the barriers and the wait for an interrupt are writes to CP15 before ARMv7, where a core has
        # them at all
        self.assertIn('mcr\t15, 0, r0, cr7, cr0, {4}', self.function('armv6k', ROOT / 'support/hw.c', 'hw_wfi'))
        self.assertIn('mcr\t15, 0, r0, cr7, cr10, {4}', self.function('armv6k', ROOT / 'support/hw.c', 'hw_dsb'))
        self.assertIn('mcr\t15, 0, r0, cr7, cr0, {4}', self.function('armv5te', ROOT / 'support/hw.c', 'hw_wfi'))
        self.assertNotIn('mcr', self.function('armv4t', ROOT / 'support/hw.c', 'hw_wfi'))
        for arch in FLAGS:
            self.assertLessEqual({'hw_irq_save', 'hw_irq_restore', 'hw_dsb', 'hw_isb', 'hw_dmb', 'hw_wfi'},
                                 self.defined(arch, ROOT / 'support/hw.c'), arch)


if __name__ == '__main__':
    unittest.main()

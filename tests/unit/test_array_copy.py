# Copyright 2026 the kmicro authors (NOTICE).
# SPDX-License-Identifier: Apache-2.0
"""runtime/types.c: an array copy stays a loop of whole elements, also when the compiler knows that source and
destination are one array. That is when it turns a plain loop into memmove, which newlib-nano does byte by byte: an
interrupt handler could then read half of an element (tests/interrupts/copy.kt runs the copies under a handler; in
that image the compiler does not know the two arrays are one, so only this test sees the difference).

The runtime file is compiled to IR with two callers added that copy inside one array (skipped when the LLVM of
Kotlin/Native is not installed).

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
sys.path.insert(0, str(ROOT / 'tools'))
import paths  # noqa: E402
import qbuild  # noqa: E402

CALLERS = '''
void rotate_references(ObjHeader *ring, int32_t n) { Kotlin_Array_copyImpl(ring, 1, ring, 0, n - 1); }
void rotate_ints(ObjHeader *ring, int32_t n) { Kotlin_IntArray_copyImpl(ring, 1, ring, 0, n - 1); }
void clear_references(ObjHeader *ring, int32_t n) { Kotlin_Array_fillImpl(ring, 0, n, 0); }
void clear_ints(ObjHeader *ring, int32_t n) { Kotlin_IntArray_fillImpl(ring, 0, n, 0); }
'''


@unittest.skipUnless(paths._find(paths.llvm.env, paths.llvm.patterns, paths.llvm.what)
                     and paths._find(paths.arm_gcc.env, paths.arm_gcc.patterns, paths.arm_gcc.what),
                     'needs LLVM and arm-none-eabi-gcc (newlib headers)')
class ArrayCopy(unittest.TestCase):
    def test_copies_and_fills_of_one_array_stay_element_loops(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 'types_and_callers.c'
            src.write_text((ROOT / 'runtime/types.c').read_text(encoding='utf-8') + CALLERS, encoding='utf-8')
            flags = [f for f in qbuild.cflags() if f not in ('-flto', '-g')]
            r = subprocess.run([str(paths.clang()), *flags, '-S', '-emit-llvm', str(src), '-o', str(Path(d) / 'o.ll')],
                               capture_output=True, text=True, errors='replace')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertNotIn('discards qualifiers', r.stderr)
            ir = (Path(d) / 'o.ll').read_text(encoding='utf-8')
        for name, kind in (('rotate_references', 'ptr'), ('rotate_ints', 'i32'), ('clear_references', 'ptr'),
                           ('clear_ints', 'i32')):
            body = re.search(rf'^define [^\n]*@{name}\(.*?^\}}', ir, re.M | re.S)
            self.assertTrue(body, name)
            body = body.group(0)
            self.assertNotRegex(body, r'@llvm\.mem(move|cpy|set)|@mem(move|cpy|set)\b', name)
            self.assertRegex(body, rf'store volatile {kind} ', name)
            if name.startswith('rotate'):
                self.assertRegex(body, rf'load volatile {kind}, ', name)


if __name__ == '__main__':
    unittest.main()

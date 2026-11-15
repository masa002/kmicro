# Copyright 2026 the kmicro authors (NOTICE).
# SPDX-License-Identifier: Apache-2.0
"""toolchain/aapcs.py on a module shaped like cinterop's bridges: struct results of C functions and of callbacks
are passed in memory, calls between the bridges stay as they are, and what it cannot handle is an error. The output
must compile for a core without an FPU (skipped when the LLVM of Kotlin/Native is not installed).

python -m unittest discover -s tests/unit
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'toolchain'))
import aapcs  # noqa: E402
import paths  # noqa: E402

MODULE = """target datalayout = "e-m:e-p:32:32-Fi8-i64:64-v128:64:128-a:0:32-n32-S64"
target triple = "armv6kz-unknown-linux-gnueabihf"

%struct.vec2 = type { float, float }
%struct.cplx = type { double, double }
%struct.quat = type { [4 x float] }

@knifunptr_drv_vec_scale_0 = local_unnamed_addr global ptr @drv_vec_scale_wrapper0, align 4

define void @_drv_knbridge0(ptr noundef %0, float noundef %1, ptr noundef %2) {
  %4 = load ptr, ptr @knifunptr_drv_vec_scale_0, align 4
  %5 = load %struct.vec2, ptr %0, align 4
  %6 = tail call %struct.vec2 %4(%struct.vec2 %5, float noundef %1)
  store %struct.vec2 %6, ptr %2, align 4
  ret void
}

define %struct.vec2 @drv_vec_scale_wrapper0(%struct.vec2 %0, float noundef %1) {
  %3 = tail call %struct.vec2 @vec_scale(%struct.vec2 %0, float noundef %1)
  ret %struct.vec2 %3
}

declare %struct.vec2 @vec_scale(%struct.vec2, float noundef) local_unnamed_addr

define void @drv_named_wrapper9(ptr %0) {
  %"the result" = call noundef %struct.cplx @cplx_conj(%struct.cplx zeroinitializer)
  store %struct.cplx %"the result", ptr %0, align 8
  ret void
}

define %struct.cplx @drv_cplx_conj_wrapper1(%struct.cplx %0) {
  %2 = tail call %struct.cplx @cplx_conj(%struct.cplx %0)
  ret %struct.cplx %2
}

declare %struct.cplx @cplx_conj(%struct.cplx) local_unnamed_addr

define i32 @drv_quat_touch_wrapper2() {
  tail call %struct.quat @quat_zero()
  %2 = call i32 @plain(i32 noundef 1)
  ret i32 %2
}

declare %struct.quat @quat_zero() local_unnamed_addr

define %struct.vec2 @_drv_kncfun3(%struct.vec2 %0, float noundef %1) {
  %3 = alloca %struct.vec2, align 4
  call void @_drv_knbridge4(ptr noundef nonnull %3, float noundef %1)
  %4 = load %struct.vec2, ptr %3, align 4
  ret %struct.vec2 %4
}

declare void @_drv_knbridge4(ptr noundef, float noundef) local_unnamed_addr

declare i32 @plain(i32 noundef) local_unnamed_addr
"""


def run(text):
    return aapcs.in_memory(text).split('\n')


class StructResults(unittest.TestCase):
    def test_a_c_function_gets_the_result_pointer_and_each_call_a_slot(self):
        out = run(MODULE)
        self.assertIn('declare void @vec_scale(ptr sret(%struct.vec2) align 4, %struct.vec2, float noundef) '
                      'local_unnamed_addr', out)
        i = out.index('define %struct.vec2 @drv_vec_scale_wrapper0(%struct.vec2 %0, float noundef %1) {')
        self.assertEqual(out[i + 1:i + 5], [
            '  %kmicro.result.1 = alloca %struct.vec2, align 4',
            '  call void @vec_scale(ptr sret(%struct.vec2) align 4 %kmicro.result.1, %struct.vec2 %0, '
            'float noundef %1)',
            '  %3 = load %struct.vec2, ptr %kmicro.result.1, align 4',
            '  ret %struct.vec2 %3'])                           # the wrapper itself is code of this module
        self.assertIn('declare void @cplx_conj(ptr sret(%struct.cplx) align 8, %struct.cplx) local_unnamed_addr', out)
        self.assertIn('  %kmicro.result.3 = alloca %struct.cplx, align 8', out)
        self.assertIn('declare void @quat_zero(ptr sret(%struct.quat) align 4) local_unnamed_addr', out)
        i = out.index('define i32 @drv_quat_touch_wrapper2() {')      # a result without a name keeps its number
        self.assertEqual(out[i + 1:i + 5], ['  %kmicro.result.4 = alloca %struct.quat, align 4',
                                            '  call void @quat_zero(ptr sret(%struct.quat) align 4 %kmicro.result.4)',
                                            '  load %struct.quat, ptr %kmicro.result.4, align 4',
                                            '  %2 = call i32 @plain(i32 noundef 1)'])

    def test_the_slot_of_a_call_in_a_loop_is_in_the_entry_block(self):
        loop = ('%struct.vec2 = type { float, float }\n'
                'define float @sum_all(i32 noundef %0) {\n'
                '  %2 = icmp sgt i32 %0, 0\n'
                '  br i1 %2, label %3, label %9\n'
                '\n'
                '3:\n'
                '  %4 = phi i32 [ %7, %3 ], [ 0, %1 ]\n'
                '  %5 = tail call %struct.vec2 @vec_get(i32 noundef %4)\n'
                '  %6 = extractvalue %struct.vec2 %5, 0\n'
                '  %7 = add nuw nsw i32 %4, 1\n'
                '  %8 = icmp eq i32 %7, %0\n'
                '  br i1 %8, label %9, label %3\n'
                '\n'
                '9:\n'
                '  ret float 0.0\n'
                '}\n'
                'declare %struct.vec2 @vec_get(i32 noundef)\n')
        out = run(loop)
        self.assertEqual(out[1:3], ['define float @sum_all(i32 noundef %0) {',
                                    '  %kmicro.result.1 = alloca %struct.vec2, align 4'])
        i = out.index('3:')
        self.assertEqual(out[i + 2:i + 4], ['  call void @vec_get(ptr sret(%struct.vec2) align 4 %kmicro.result.1, '
                                            'i32 noundef %4)',
                                            '  %5 = load %struct.vec2, ptr %kmicro.result.1, align 4'])
        named = loop.replace('define float @sum_all(i32 noundef %0) {\n', 'define float @sum_all(i32 noundef %0) {\n'
                             'entry:\n')
        out = run(named)
        self.assertEqual(out[2:4], ['entry:', '  %kmicro.result.1 = alloca %struct.vec2, align 4'])

    def test_a_result_of_four_bytes_stays_as_it_is(self):
        one = ('%struct.one = type { float }\n%union.un = type { float }\n'
               'define float @caller() {\n  %1 = tail call %struct.one @f_one(i32 noundef 7)\n'
               '  %2 = extractvalue %struct.one %1, 0\n  ret float %2\n}\n'
               'declare %struct.one @f_one(i32 noundef) local_unnamed_addr\n'
               'define %union.un @_x_kncfun0() {\n  ret %union.un zeroinitializer\n}\n'
               'define void @_x_knbridge1(ptr %0, ptr %1) {\n  %3 = tail call %struct.one %0()\n'
               '  store %struct.one %3, ptr %1, align 4\n  ret void\n}\n')
        self.assertEqual(aapcs.in_memory(one), one)             # r0 on both sides: the base ABI and the backend

    def test_a_named_result_and_a_result_attribute(self):
        out = run(MODULE)
        i = out.index('define void @drv_named_wrapper9(ptr %0) {')
        self.assertEqual(out[i + 1:i + 4], [
            '  %kmicro.result.2 = alloca %struct.cplx, align 8',
            '  call void @cplx_conj(ptr sret(%struct.cplx) align 8 %kmicro.result.2, %struct.cplx zeroinitializer)',
            '  %"the result" = load %struct.cplx, ptr %kmicro.result.2, align 8'])

    def test_a_callback_stores_its_result_through_the_pointer(self):
        out = run(MODULE)
        i = out.index('define void @_drv_kncfun3(ptr sret(%struct.vec2) align 4 %kmicro.result, %struct.vec2 %0, '
                      'float noundef %1) {')
        self.assertEqual(out[i + 4:i + 7], ['  store %struct.vec2 %4, ptr %kmicro.result, align 4', '  ret void', '}'])

    def test_calls_between_the_bridges_and_other_functions_stay(self):
        out = run(MODULE)
        for line in ('  %6 = tail call %struct.vec2 %4(%struct.vec2 %5, float noundef %1)',
                     'define %struct.vec2 @drv_vec_scale_wrapper0(%struct.vec2 %0, float noundef %1) {',
                     'declare i32 @plain(i32 noundef) local_unnamed_addr',
                     'declare void @_drv_knbridge4(ptr noundef, float noundef) local_unnamed_addr'):
            self.assertIn(line, out)
        plain = 'define i32 @f(i32 %0) {\n  %2 = call i32 @plain(i32 %0)\n  ret i32 %2\n}\ndeclare i32 @plain(i32)\n'
        self.assertEqual(aapcs.in_memory(plain), plain)
        intrinsic = 'declare { i32, i1 } @llvm.sadd.with.overflow.i32(i32, i32)\n'
        self.assertEqual(aapcs.in_memory(intrinsic), intrinsic)

    def test_what_is_not_handled_is_an_error_that_says_what_to_do(self):
        for use in ('  %3 = invoke %struct.vec2 @vec_get(i32 noundef %0)\n          to label %4 unwind label %5\n',
                    '  %3 = call %struct.vec2 (i32, ...) @vec_get(i32 noundef %0)\n'):
            module = ('%struct.vec2 = type { float, float }\ndefine void @f(i32 %0) {\n' + use + '  ret void\n}\n'
                      'declare %struct.vec2 @vec_get(i32 noundef, ...)\n')
            with self.assertRaisesRegex(ValueError, 'the C function vec_get .* is not a plain call', msg=use):
                aapcs.in_memory(module)
        pointer = ('%struct.vec2 = type { float, float }\ndefine void @_x_knbridge0(ptr %0, ptr %1) {\n'
                   '  %3 = tail call %struct.vec2 %0()\n  store %struct.vec2 %3, ptr %1, align 4\n  ret void\n}\n')
        with self.assertRaisesRegex(ValueError, 'through a C function pointer'):
            aapcs.in_memory(pointer)
        with self.assertRaisesRegex(ValueError, 'layout is not known'):
            aapcs.in_memory('%struct.o = type opaque\ndeclare %struct.o @opaque()\n')

    def test_layout(self):
        types = {'%struct.m': '{ i8, double, i16, i64, float }', '%struct.q': '{ [4 x float] }'}
        self.assertEqual(aapcs.layout('%struct.m', types), (40, 8))
        self.assertEqual(aapcs.layout('%struct.q', types), (16, 4))
        self.assertEqual(aapcs.layout('{ float, { double, i8 } }', types), (24, 8))

    @unittest.skipUnless(paths._find(paths.llvm.env, paths.llvm.patterns, paths.llvm.what), 'needs LLVM')
    def test_the_output_compiles_for_a_core_without_an_fpu(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'in.ll').write_text(MODULE, encoding='utf-8')
            env = {**os.environ, 'KMICRO_CPU': 'cortex-m3'}
            r = subprocess.run([sys.executable, ROOT / 'toolchain/retarget.py', Path(d) / 'in.ll', Path(d) / 'out.ll'],
                               capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            text = (Path(d) / 'out.ll').read_text(encoding='utf-8')
            self.assertIn('declare void @vec_scale(ptr sret(%struct.vec2) align 4', text)
            code = ('import sys; sys.path.insert(0, sys.argv[1]); import paths, subprocess\n'
                    'sys.exit(subprocess.run([str(paths.clang()), *paths.target_flags(), "-O2", "-c", "-x", "ir", '
                    'sys.argv[2], "-o", sys.argv[2] + ".o"]).returncode)\n')
            c = subprocess.run([sys.executable, '-c', code, str(ROOT / 'toolchain'), str(Path(d) / 'out.ll')],
                               capture_output=True, text=True, env=env)
            self.assertEqual(c.returncode, 0, c.stderr)
            r = subprocess.run([sys.executable, ROOT / 'toolchain/retarget.py', Path(d) / 'in.ll', Path(d) / 'hf.ll'],
                               capture_output=True, text=True, env={**os.environ, 'KMICRO_CPU': 'cortex-m4f'})
            self.assertEqual(r.returncode, 0, r.stderr)             # with an FPU the calls stay as they are
            self.assertIn('declare %struct.vec2 @vec_scale(%struct.vec2, float noundef)',
                          (Path(d) / 'hf.ll').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()

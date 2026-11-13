"""toolchain/bridges.py extract() on a small module in the shape kotlinc-native saves (no Kotlin compiler needed;
the last test assembles the result with clang when it is installed).

python -m unittest discover -s tests/unit
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'toolchain'))
import bridges  # noqa: E402

HEADER = '''target datalayout = "e-m:e-p:32:32-Fi8-i64:64-v128:64:128-a:0:32-n32-S64"
target triple = "armv6kz-unknown-linux-gnueabihf"
'''
# Codegen: the Kotlin program. It defines the Kotlin side of a callback (_h_3_knbridge1) and declares the rest.
CODEGEN = HEADER + '''
@"kclass:kotlin.Any" = constant { ptr, i32 } { ptr null, i32 1 }

define internal i32 @"kfun:#lambda(kotlin.Int){}kotlin.Int"(i32 %0) #4 {
  ret i32 %0
}

define i32 @_h_3_knbridge1(i32 %0) #4 personality ptr @__gxx_personality_v0 {
  call void @Kotlin_initRuntimeIfNeeded()
  %2 = call i32 @"kfun:#lambda(kotlin.Int){}kotlin.Int"(i32 %0)
  ret i32 %2
}

declare void @_h_1_knbridge1(ptr)
declare i32 @_h_2_knbridge1(i32)
declare i32 @_h_4_kncfun2(i32)
declare void @Kotlin_initRuntimeIfNeeded()
'''
# LinkBitcodeDependencies: the same plus the stock runtime and the compiler's C stubs.
LBD = HEADER + '''
%struct.TypeInfo = type { ptr, i32 }
%struct._h_1_struct3 = type { i32, %struct.inner }
%struct.inner = type { [2 x i16] }
%struct.unused = type { i64 }

@"kclass:kotlin.Any" = constant %struct.TypeInfo { ptr @"kclass:kotlin.Any", i32 1 }
@knifunptr_p_make_0 = local_unnamed_addr global ptr @p_make_wrapper0, align 4
@knifunptr_p_sum_to_0 = local_unnamed_addr global ptr @p_sum_to_wrapper1, align 4
@p_count = external local_unnamed_addr global i32, align 4

define void @Kotlin_initRuntimeIfNeeded() #4 {
  %1 = load ptr, ptr @"kclass:kotlin.Any", align 4
  ret void
}

define internal i32 @"kfun:#lambda(kotlin.Int){}kotlin.Int"(i32 %0) #4 {
  ret i32 %0
}

define i32 @_h_3_knbridge1(i32 %0) #4 personality ptr @__gxx_personality_v0 {
  call void @Kotlin_initRuntimeIfNeeded()
  %2 = call i32 @"kfun:#lambda(kotlin.Int){}kotlin.Int"(i32 %0)
  ret i32 %2
}

define void @_h_1_knbridge1(ptr noundef %0) #6 {
  %2 = load ptr, ptr @knifunptr_p_make_0, align 4, !tbaa !15
  call void %2(ptr dead_on_unwind writable sret(%struct._h_1_struct3) align 4 %0) #102
  ret void
}

define i32 @_h_2_knbridge1(i32 noundef %0) #6 {
  %2 = load ptr, ptr @knifunptr_p_sum_to_0, align 4, !tbaa !15
  %3 = tail call i32 %2(i32 noundef %0)
  ret i32 %3
}

define i32 @_h_4_kncfun2(i32 noundef %0) #6 {
  %2 = tail call i32 @_h_3_knbridge1(i32 noundef %0)
  ret i32 %2
}

define void @p_make_wrapper0(ptr dead_on_unwind noalias writable sret(%struct._h_1_struct3) align 4 %0) #6 {
  tail call void @p_make(ptr dead_on_unwind writable sret(%struct._h_1_struct3) align 4 %0) #102
  ret void
}

declare void @p_make(ptr dead_on_unwind writable sret(%struct._h_1_struct3) align 4) local_unnamed_addr #7

define i32 @p_sum_to_wrapper1(i32 noundef %0) #6 {
  %2 = load i32, ptr @p_count, align 4, !tbaa !15
  %3 = add i32 %2, %0
  ret i32 %3
}

attributes #4 = { nounwind }
attributes #6 = { nounwind "target-cpu"="generic" }
attributes #7 = { nounwind }
attributes #102 = { nounwind }

!15 = !{!"tbaa"}
'''


class Extract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text, cls.summary = bridges.extract(LBD, CODEGEN)

    def test_roots_are_the_bridges_codegen_does_not_define(self):
        self.assertIn('define void @_h_1_knbridge1(ptr noundef %0) {', self.text)
        self.assertIn('define i32 @_h_2_knbridge1(i32 noundef %0) {', self.text)
        self.assertIn('define i32 @_h_4_kncfun2(i32 noundef %0) {', self.text)    # the C-callable stub
        self.assertTrue(self.summary.startswith('bridges: 2 Kotlin->C bridges, 1 C->Kotlin stubs;'), self.summary)

    def test_kotlin_and_runtime_code_is_declared_not_copied(self):
        self.assertIn('declare i32 @_h_3_knbridge1(i32 %0)', self.text)
        for name in ('kclass:kotlin.Any', 'kfun:#lambda', 'Kotlin_initRuntimeIfNeeded', '__gxx_personality_v0'):
            self.assertNotIn(name, self.text)

    def test_struct_types_are_copied_with_the_types_inside_them(self):
        self.assertIn('%struct._h_1_struct3 = type { i32, %struct.inner }', self.text)
        self.assertIn('%struct.inner = type { [2 x i16] }', self.text)
        self.assertNotIn('%struct.unused', self.text)
        self.assertNotIn('%struct.TypeInfo', self.text)

    def test_summary_names_the_c_functions(self):
        self.assertTrue(self.summary.endswith('C functions: p_make'), self.summary)
        self.assertIn('copied 5 functions, 3 pointers, 2 types', self.summary)

    def test_clang_accepts_the_module(self):
        try:
            import paths
            clang = paths.clang()
        except (ImportError, SystemExit):
            self.skipTest('clang is not installed')
        with tempfile.TemporaryDirectory() as d:
            ll = Path(d) / 'bridges.ll'
            ll.write_text(self.text, encoding='utf-8')
            r = subprocess.run([str(clang), *paths.TARGET_M4F, '-Wno-override-module', '-c', '-x', 'ir', str(ll),
                                '-o', str(Path(d) / 'bridges.o')], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == '__main__':
    unittest.main()

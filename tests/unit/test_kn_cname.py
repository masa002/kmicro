"""toolchain/kn.py add_cname_aliases(): @CName names from kotlinc-native's C adapter (IR excerpts, no compiler needed;
tests/programs/cname.kt runs the real thing).

python -m unittest discover -s tests/unit
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'toolchain'))
import kn  # noqa: E402

ADAPTER = '''
define i32 @_konan_function_0(i32 %0, i32 %1) #4 {
}
define i32 @k_add(i32 noundef %0, i32 noundef %1) #64 personality ptr @__gxx_personality_v0 {
  %14 = invoke i32 @_konan_function_0(i32 noundef %12, i32 noundef %13)
          to label %15 unwind label %18
}
define internal noundef i32 @_ZL22_konan_function_1_impli(i32 noundef %0) #65 {
  %11 = invoke i32 @_konan_function_1(i32 noundef %10)
}
'''
GREET = '''
define ptr @k_greet(ptr noundef %0) #64 {
  %5 = call ptr @_konan_function_2(ptr %3, ptr %4)
}
'''


def codegen(n, sym, ret, params):
    return (f'define {ret} @_konan_function_{n}({params}) #9 {{\nentry:\n  %3 = call {ret} @"{sym}"({params})\n}}\n'
            f'define {ret} @"{sym}"({params}) {{\n}}\n')


CODEGEN = (codegen(0, 'kfun:#add(kotlin.Int;kotlin.Int){}kotlin.Int', 'i32', 'i32 %0, i32 %1')
           + codegen(1, 'kfun:app#hello(kotlin.Int){}kotlin.Int', 'i32', 'i32 %0')
           + codegen(2, 'kfun:#greet(kotlin.String){}kotlin.String', 'ptr', 'ptr %0, ptr %1'))


class CName(unittest.TestCase):
    def test_primitive_export_becomes_an_alias(self):
        lines, errors = kn.add_cname_aliases(ADAPTER, CODEGEN)
        self.assertEqual(errors, [])
        self.assertEqual(lines, ['@k_add = alias i32 (i32, i32), ptr @"kfun:#add(kotlin.Int;kotlin.Int){}kotlin.Int"'])

    def test_object_types_are_an_error(self):
        lines, errors = kn.add_cname_aliases(ADAPTER + GREET, CODEGEN)
        self.assertEqual(len(errors), 1)
        self.assertIn('@CName("k_greet")', errors[0])
        self.assertIn('takes kotlin.String', errors[0])

    def test_no_export(self):
        self.assertEqual(kn.add_cname_aliases('define i32 @main() {\n}\n', CODEGEN), ([], []))


if __name__ == '__main__':
    unittest.main()

"""Arrays on the stack: kn.check_stack_arrays() before linking (IR) and tools/frames.py after (machine code); canned
inputs, no compiler needed.

python -m unittest discover -s tests/unit
"""
import contextlib
import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'toolchain'))
sys.path.insert(0, str(ROOT / 'tools'))
import frames  # noqa: E402
import kn  # noqa: E402

IR = '''%"local#IntArray14000#internal" = type <{ %struct.ArrayHeader, [14000 x i32] }>
%"local#ByteArray600#internal" = type <{ %struct.ArrayHeader, [600 x i8] }>
%"local#CharArray25#internal" = type <{ %struct.ArrayHeader, [25 x i16] }>
define void @"kfun:#main(){}"() {
  %11 = alloca %"local#IntArray14000#internal", align 4
}
define i32 @"kfun:app.Codec#encode(kotlin.Int){}kotlin.Int"(ptr %0, i32 %1) {
  %3 = alloca %"local#ByteArray600#internal", align 4
}
define internal void @"kfun:kotlin.native.internal.NumberConverter.freeFormat#internal"(ptr %0) {
  %3 = alloca %"local#CharArray25#internal", align 4
}
'''

DISASM = '''
08001520 <Reset_Handler>:
 8001520:	stmdb	sp!, {r4, r5, r6, r7, r8, r9, sl, fp, lr}
 8001524:	sub.w	sp, sp, #56064	@ 0xdb00
 8001528:	sub	sp, #52	@ 0x34
 800152a:	bl	8000200 <kmicro_init>
08001600 <small>:
 8001600:	push	{r4, lr}
 8001602:	vpush	{d8-d9}
 8001606:	movw	ip, #5000	@ 0x1388
 800160a:	sub.w	sp, sp, ip
 800160e:	bl	8000300 <work>
 8001612:	sub	sp, #400
08001700 <leaf>:
 8001700:	bx	lr
'''


class Before(unittest.TestCase):
    def test_arrays_by_function(self):
        got = {kn.kotlin_name(s): a for s, a in kn.stack_arrays(IR)}
        self.assertEqual(got['main()'], [('IntArray', 14000, 56000)])
        self.assertEqual(got['app.Codec.encode(Int)'], [('ByteArray', 600, 600)])

    def test_warning_names_function_and_bytes(self):
        with contextlib.redirect_stderr(io.StringIO()) as err:
            kn.check_stack_arrays(IR)
        text = err.getvalue()
        self.assertIn('main() puts arrays on the stack: IntArray(14000) 56000 B', text)
        self.assertIn('app.Codec.encode(Int)', text)
        self.assertNotIn('NumberConverter', text)

    def test_error_and_limit(self):
        with self.assertRaises(SystemExit):
            kn.check_stack_arrays(IR, error=True)
        with contextlib.redirect_stderr(io.StringIO()) as err:
            kn.check_stack_arrays(IR, limit=60000)
        self.assertEqual(err.getvalue(), '')


class After(unittest.TestCase):
    def test_frames(self):
        f = frames.frames(DISASM)
        self.assertEqual(f['Reset_Handler'], 9 * 4 + 56064 + 52)
        self.assertEqual(f['small'], 2 * 4 + 2 * 8 + 5000)     # stops at the call: the later sub is not counted
        self.assertEqual(f['leaf'], 0)


if __name__ == '__main__':
    unittest.main()

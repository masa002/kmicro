"""tools/frames.py: the stack a function's prologue takes, read from objdump -d text."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import frames  # noqa: E402

THUMB2 = """
08000100 <small>:
 8000100:	push	{r4, r5, r7, lr}
 8000102:	sub	sp, #24
 8000104:	bl	8000200 <other>

08000200 <big>:
 8000200:	stmdb	sp!, {r4, r5, r6, r7, r8, r9, sl, lr}
 8000204:	vpush	{d8-d9}
 8000208:	movw	r12, #56000
 800020c:	sub.w	sp, sp, r12
 8000210:	bl	8000100 <small>
"""

# ARMv6-M has no instruction that holds a large constant: the size comes from a literal pool, as a negative number
# that is added to sp.
THUMB1 = """
08001b5c <run_main>:
 8001b5c:	push	{r4, r5, r6, r7, lr}
 8001b5e:	ldr	r7, [pc, #744]	@ (8001e48 <run_main+0x2ec>)
 8001b60:	add	sp, r7
 8001b62:	ldr	r0, [pc, #696]	@ (8001e1c <run_main+0x2c0>)
 8001b64:	bl	8005800 <other>
 8001e1c:	.word	0x20000010
 8001e48:	.word	0xffff2504

08002000 <leaf>:
 8002000:	push	{r7, lr}
 8002002:	sub	sp, #8
 8002004:	add	r0, sp, #4
 8002006:	bl	8005800 <other>
"""


class Frames(unittest.TestCase):
    def test_thumb2_prologues(self):
        f = frames.frames(THUMB2)
        self.assertEqual(f['small'], 16 + 24)
        self.assertEqual(f['big'], 32 + 16 + 56000)

    def test_thumb1_size_from_a_literal_pool(self):
        f = frames.frames(THUMB1)
        self.assertEqual(f['run_main'], 20 + (0x100000000 - 0xffff2504))
        self.assertEqual(f['leaf'], 8 + 8)                # `add r0, sp, #4` is not a frame


if __name__ == '__main__':
    unittest.main()

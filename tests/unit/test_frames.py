# Copyright 2026 the kmicro authors (NOTICE).
# SPDX-License-Identifier: Apache-2.0
"""tools/frames.py: the stack a function's prologue takes, read from objdump -d text."""
import contextlib
import io
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

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

# A variable-length array or alloca(): clang for ARMv7-M, clang for ARMv6-M, GCC after a call, and clang's alloca of
# 8 bytes inside a loop. Then what is none: a frame pointer that gives the stack back, a constant in a register, a
# stack that is aligned for a local.
DYNAMIC = """
08000004 <vla_thumb2>:
 8000004:	push	{r4, r6, r7, lr}
 8000006:	add	r7, sp, #8
 8000008:	adds	r1, r0, #7
 800000a:	bic.w	r1, r1, #7
 800000e:	sub.w	r1, sp, r1
 8000012:	mov	sp, r1
 8000014:	sub.w	r4, r7, #8
 8000018:	mov	sp, r4
 800001a:	pop	{r4, r6, r7, pc}

08000020 <vla_thumb1>:
 8000020:	push	{r4, r6, r7, lr}
 8000022:	add	r7, sp, #8
 8000024:	mov	r6, sp
 8000026:	adds	r0, r0, #7
 8000028:	movs	r2, #7
 800002a:	bics	r0, r2
 800002c:	mov	r2, sp
 800002e:	subs	r4, r2, r0
 8000030:	mov	sp, r4
 8000032:	subs	r6, r7, #7
 8000034:	subs	r6, #1
 8000036:	mov	sp, r6
 8000038:	pop	{r4, r6, r7, pc}

08000040 <vla_after_a_call>:
 8000040:	push	{r7, lr}
 8000042:	add	r7, sp, #0
 8000044:	bl	8000200 <get>
 8000048:	adds	r3, r0, #7
 800004a:	bic.w	r3, r3, #7
 800004e:	sub.w	sp, sp, r3
 8000052:	mov	sp, r7
 8000054:	pop	{r7, pc}

08000060 <alloca_in_a_loop>:
 8000060:	push	{r4, r5, r6, r7, lr}
 8000062:	add	r7, sp, #12
 8000064:	mov	r4, sp
 8000066:	subs	r4, #8
 8000068:	mov	sp, r4
 800006a:	bl	8000200 <get>
 800006e:	bne.n	8000064 <alloca_in_a_loop+0x4>
 8000070:	sub.w	r4, r7, #12
 8000074:	mov	sp, r4
 8000076:	pop	{r4, r5, r6, r7, pc}

08000080 <frame_pointer>:
 8000080:	push	{r7, lr}
 8000082:	sub	sp, #24
 8000084:	add	r7, sp, #0
 8000086:	mov	r3, sp
 8000088:	str	r3, [r7, #4]
 800008a:	bl	8000200 <get>
 800008e:	mov	sp, r7
 8000090:	add	sp, #24
 8000092:	pop	{r7, pc}

080000a0 <aligned_local>:
 80000a0:	push	{r4, r6, r7, lr}
 80000a2:	add	r7, sp, #8
 80000a4:	sub	sp, #96
 80000a6:	mov	r4, sp
 80000a8:	bfc	r4, #0, #5
 80000ac:	mov	sp, r4
 80000ae:	sub.w	r4, r7, #8
 80000b2:	mov	sp, r4
 80000b4:	pop	{r4, r6, r7, pc}
"""

# An alloca() of constant size that is not taken in the prologue (in an `if`, in a loop). clang sets sp from a
# register: a size that no subtract instruction holds is loaded as a negative number and added (every size above 255
# for ARMv6-M, one above 65535 for ARMv8-M Baseline).
ADDED = """
08000000 <clang_armv6m>:
 8000000:	push	{r4, r6, r7, lr}
 8000002:	add	r7, sp, #8
 8000004:	mov	r6, sp
 8000006:	cmp	r0, #0
 8000008:	beq.n	8000014 <clang_armv6m+0x14>
 800000a:	ldr	r0, [pc, #24]	@ (8000024 <clang_armv6m+0x24>)
 800000c:	mov	r2, sp
 800000e:	adds	r0, r2, r0
 8000010:	mov	sp, r0
 8000014:	bl	8000200 <use>
 8000018:	subs	r6, r7, #7
 800001a:	subs	r6, #1
 800001c:	mov	sp, r6
 800001e:	pop	{r4, r6, r7, pc}
 8000024:	.word	0xffffe000

08000030 <clang_armv6m_in_a_loop>:
 8000030:	push	{r1, r2, r3, r4, r5, r6, r7, lr}
 8000032:	add	r7, sp, #24
 8000034:	mov	r6, sp
 8000036:	mov	r4, sp
 8000038:	ldr	r0, [pc, #32]	@ (800005c <clang_armv6m_in_a_loop+0x2c>)
 800003a:	adds	r0, r4, r0
 800003c:	mov	sp, r0
 800003e:	bl	8000200 <use>
 8000042:	b.n	8000036 <clang_armv6m_in_a_loop+0x6>
 800005c:	.word	0xfffffda8

08000060 <clang_added_to_sp>:
 8000060:	push	{r4, r6, r7, lr}
 8000062:	add	r7, sp, #8
 8000064:	cbz	r0, 800006c <clang_added_to_sp+0xc>
 8000066:	ldr	r0, [pc, #16]	@ (8000078 <clang_added_to_sp+0x18>)
 8000068:	add	r0, sp
 800006a:	mov	sp, r0
 800006c:	bl	8000200 <use>
 8000070:	sub.w	r4, r7, #8
 8000074:	mov	sp, r4
 8000076:	pop	{r4, r6, r7, pc}
 8000078:	.word	0xfffe7958

08000080 <clang_for_size>:
 8000080:	push	{r4, r6, r7, lr}
 8000082:	add	r7, sp, #8
 8000084:	cbz	r0, 800008e <clang_for_size+0xe>
 8000086:	sub.w	r0, sp, #8192	@ 0x2000
 800008a:	mov	sp, r0
 800008e:	bl	8000200 <use>
 8000092:	sub.w	r4, r7, #8
 8000096:	mov	sp, r4
 8000098:	pop	{r4, r6, r7, pc}

080000a0 <an_address_in_the_frame>:
 80000a0:	push	{r4, r6, r7, lr}
 80000a2:	add	r7, sp, #8
 80000a4:	sub	sp, #64
 80000a6:	mov	r4, sp
 80000a8:	adds	r0, r4, r1
 80000aa:	add	r2, sp, #4
 80000ac:	bl	8000200 <use>
 80000b0:	sub.w	r4, r7, #8
 80000b4:	mov	sp, r4
 80000b6:	pop	{r4, r6, r7, pc}
"""

# GCC takes it from sp where the call stands, here after the first call: with an immediate, with a negative number
# from the literal pool on ARMv6-M, and at -O0 through a second register. The bytes are added to the frame. A frame
# from the literal pool that is given back the same way is counted once.
LATE = """
08000100 <gcc_thumb2>:
 8000100:	push	{r7, lr}
 8000102:	add	r7, sp, #0
 8000104:	bl	8000200 <get>
 8000108:	cbz	r0, 8000110 <gcc_thumb2+0x10>
 800010a:	sub.w	sp, sp, #8192	@ 0x2000
 800010e:	mov	r0, sp
 8000110:	bl	8000200 <use>
 8000114:	mov	sp, r7
 8000116:	pop	{r7, pc}

08000120 <gcc_armv6m>:
 8000120:	push	{r7, lr}
 8000122:	add	r7, sp, #0
 8000124:	bl	8000200 <get>
 8000128:	cmp	r1, #0
 800012a:	beq.n	8000132 <gcc_armv6m+0x12>
 800012c:	ldr	r3, [pc, #12]	@ (800013c <gcc_armv6m+0x1c>)
 800012e:	add	sp, r3
 8000130:	mov	r0, sp
 8000132:	bl	8000200 <use>
 8000136:	mov	sp, r7
 8000138:	pop	{r7, pc}
 800013c:	.word	0xffffe000

08000140 <gcc_armv6m_O0>:
 8000140:	push	{r7, lr}
 8000142:	sub	sp, #16
 8000144:	add	r7, sp, #0
 8000146:	bl	8000200 <get>
 800014a:	ldr	r3, [pc, #36]	@ (8000170 <gcc_armv6m_O0+0x30>)
 800014c:	mov	ip, r3
 800014e:	add	sp, ip
 8000150:	bl	8000200 <use>
 8000154:	mov	sp, r7
 8000156:	add	sp, #16
 8000158:	pop	{r7, pc}
 8000170:	.word	0xffffe000

08000180 <given_back_from_the_pool>:
 8000180:	push	{r4, r5, r6, lr}
 8000182:	ldr	r6, [pc, #20]	@ (8000198 <given_back_from_the_pool+0x18>)
 8000184:	add	sp, r6
 8000186:	bl	8000200 <use>
 800018a:	ldr	r6, [pc, #16]	@ (800019c <given_back_from_the_pool+0x1c>)
 800018c:	add	sp, r6
 800018e:	pop	{r4, r5, r6, pc}
 8000198:	.word	0xffffe890
 800019c:	.word	0x00001770
"""

# ARM code (clang for an ARM1176JZF-S and for an ARM7TDMI). An instruction holds a constant of eight bits, shifted by
# an even number of places, so a large frame is taken in two steps; a variable-length array; a register of the FPU.
ARM = """
00100000 <arm_small>:
  100000:	push	{r4, lr}
  100004:	sub	sp, sp, #16
  100008:	mov	r4, r0
  10000c:	mov	r0, sp
  100010:	bl	100200 <use>
  100014:	ldr	r0, [sp]
  100018:	add	sp, sp, #16
  10001c:	pop	{r4, pc}

00100024 <arm_big>:
  100024:	push	{r4, r5, fp, lr}
  100028:	sub	sp, sp, #6848	@ 0x1ac0
  10002c:	sub	sp, sp, #49152	@ 0xc000
  100030:	mov	r5, sp
  100034:	mov	r0, r5
  100038:	bl	100200 <use>
  10003c:	add	sp, sp, #6848	@ 0x1ac0
  100040:	add	sp, sp, #49152	@ 0xc000
  100044:	pop	{r4, r5, fp, lr}
  100048:	bx	lr

0010007c <arm_vla>:
  10007c:	push	{r4, r5, r6, r7, fp, lr}
  100080:	add	fp, sp, #16
  100084:	mov	r1, #7
  100088:	add	r0, r1, r0, lsl #2
  10008c:	bic	r4, r0, #7
  100090:	mov	r5, sp
  100094:	sub	r0, r5, r4
  100098:	mov	sp, r0
  10009c:	bl	100200 <use>
  1000a0:	ldr	r0, [r5, -r4]
  1000a4:	sub	sp, fp, #16
  1000a8:	pop	{r4, r5, r6, r7, fp, pc}

001000ac <arm_alloca>:
  1000ac:	push	{r4, r5, fp, lr}
  1000b0:	sub	sp, sp, #8192	@ 0x2000
  1000b4:	mov	r5, sp
  1000b8:	mov	r0, r5
  1000bc:	bl	100200 <use>
  1000c0:	add	sp, sp, #8192	@ 0x2000
  1000c4:	pop	{r4, r5, fp, pc}

001000d0 <arm_fp>:
  1000d0:	push	{fp, lr}
  1000d4:	vpush	{d8}
  1000d8:	sub	sp, sp, #16
  1000dc:	mov	r0, sp
  1000e0:	vstr	d0, [sp]
  1000e4:	bl	100200 <use>
  1000e8:	add	sp, sp, #16
  1000ec:	vpop	{d8}
  1000f0:	pop	{fp, pc}
"""

# `ld.lld --strip-all`, `arm-none-eabi-strip`: one label per section
STRIPPED = """
Disassembly of section .text:

08000000 <.text>:
 8000000:	push	{r4, lr}
 8000002:	sub	sp, #600
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

    def test_a_size_the_function_computes(self):
        dynamic = set()
        f = frames.frames(DYNAMIC + THUMB2 + THUMB1, dynamic)
        self.assertEqual(dynamic, {'vla_thumb2', 'vla_thumb1', 'vla_after_a_call', 'alloca_in_a_loop'})
        self.assertEqual((f['vla_thumb2'], f['frame_pointer'], f['big']), (16, 8 + 24, 32 + 16 + 56000))

    def test_a_constant_added_as_a_negative_number(self):
        dynamic = set()
        f = frames.frames(ADDED + THUMB1, dynamic)
        self.assertEqual(dynamic, {'clang_armv6m', 'clang_armv6m_in_a_loop', 'clang_added_to_sp', 'clang_for_size'})
        self.assertEqual(f['an_address_in_the_frame'], 16 + 64)

    def test_a_constant_taken_after_the_prologue_is_counted(self):
        dynamic = set()
        f = frames.frames(LATE, dynamic)
        self.assertEqual(f, {'gcc_thumb2': 8 + 8192, 'gcc_armv6m': 8 + 8192, 'gcc_armv6m_O0': 8 + 16 + 8192,
                             'given_back_from_the_pool': 16 + 6000})
        self.assertEqual(dynamic, set())

    def test_arm_code(self):
        dynamic = set()
        f = frames.frames(ARM, dynamic)
        self.assertEqual(f, {'arm_small': 8 + 16, 'arm_big': 16 + 6848 + 49152, 'arm_vla': 24,
                             'arm_alloca': 16 + 8192, 'arm_fp': 8 + 8 + 16})
        self.assertEqual(dynamic, {'arm_vla'})

    def image(self, disasm):
        """frames.of_image() for an image with this disassembly."""
        done = subprocess.CompletedProcess([], 0, disasm, '')
        with mock.patch.object(frames.binutils, 'run', return_value=done):
            return frames.of_image('app.elf')

    def test_of_image_lists_a_computed_size_first(self):
        f, dynamic = self.image(THUMB2 + DYNAMIC)
        self.assertEqual(dynamic, {'vla_thumb2', 'vla_thumb1', 'vla_after_a_call', 'alloca_in_a_loop'})
        self.assertEqual([name for name, _ in f[:6]],
                         ['alloca_in_a_loop', 'vla_thumb2', 'vla_thumb1', 'vla_after_a_call', 'big', 'aligned_local'])

    def test_a_stripped_image_is_an_error(self):
        with self.assertRaises(SystemExit) as e:
            self.image(STRIPPED)
        self.assertEqual(e.exception.code, 'frames.py: app.elf has no function symbols: its functions cannot be told '
                         'apart')

    def test_over_guard_reports_a_frame_larger_than_the_stack_guard(self):
        with mock.patch.object(frames, 'of_image', return_value=([('big', frames.STACK_GUARD + 4), ('s', 40)], set())):
            self.assertEqual(frames.over_guard('app.elf'), 'big has a stack frame of 4100 bytes, larger than the '
                             '4096-byte stack guard of qemu-l475, which it could step over without a fault')
        with mock.patch.object(frames, 'of_image', return_value=([('main', frames.STACK_GUARD), ('s', 40)], set())):
            self.assertIsNone(frames.over_guard('app.elf'))
        with mock.patch.object(frames, 'of_image', return_value=([('fill', 16), ('main', 40)], {'fill'})):
            self.assertEqual(frames.over_guard('app.elf'), 'fill has a stack frame of a size it computes (a '
                             'variable-length array or alloca), which could step over the 4096-byte stack guard of '
                             'qemu-l475 without a fault')

    def run_main(self, *options):
        """(exit code or message, output) of frames.py on an image with a 40-byte frame and a computed one."""
        out = io.StringIO()
        with mock.patch.object(frames, 'of_image', return_value=([('fill', 16), ('main', 40)], {'fill'})), \
                mock.patch.object(sys, 'argv', ['frames.py', __file__, *options]), contextlib.redirect_stdout(out):
            try:
                frames.main()
            except SystemExit as e:
                return e.code, out.getvalue()
        return 0, out.getvalue()

    def test_limit_and_a_size_the_function_computes(self):
        code, out = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[1:], [
            '      16+ fill', '      40  main',
            '       +: and what the function computes when it runs (a variable-length array or alloca)'])
        self.assertEqual(self.run_main('--limit', '32')[0], 'frames.py: main takes 40 bytes of stack, more than '
                         '--limit 32')
        self.assertEqual(self.run_main('--limit', '64')[0], 'frames.py: fill takes stack of a size it computes (a '
                         'variable-length array or alloca), which --limit cannot check; --allow fill accepts it')
        self.assertEqual(self.run_main('--limit', '64', '--allow', 'fill')[0], 0)
        self.assertEqual(self.run_main('--limit', '32', '--allow', 'fill')[0], 'frames.py: main takes 40 bytes of '
                         'stack, more than --limit 32')


if __name__ == '__main__':
    unittest.main()

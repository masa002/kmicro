# Copyright 2026 the kmicro authors (NOTICE).
# SPDX-License-Identifier: Apache-2.0
"""tools/insn_check.py: which instructions a core has. The first tests read disassembly written by hand; the last
ones assemble an instruction of every kind for every core and compare what the assembler takes with what the tool
allows (skipped when the LLVM of Kotlin/Native or arm-none-eabi-gcc is not installed).

python -m unittest discover -s tests/unit
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'toolchain'))
sys.path.insert(0, str(ROOT / 'tools'))
import insn_check  # noqa: E402
import paths  # noqa: E402

HAVE_TOOLS = all(paths._find(t.env, t.patterns, t.what) for t in (paths.llvm, paths.arm_gcc))

DISASM = '''
app.elf:     file format elf32-littlearm


Disassembly of section .text:

08000100 <main>:
 8000100:\tb510      \tpush\t{r4, lr}
 8000102:\tf000 f805 \tbl\t8000110 <helper>
 8000106:\tf240 1034 \tmovw\tr0, #308\t@ 0x134
 800010a:\tb108      \tcbz\tr0, 8000110 <helper>
 800010c:\tbd10      \tpop\t{r4, pc}
 800010e:\t46c0      \tnop\t\t\t@ (mov r8, r8)

08000110 <helper>:
 8000110:\tfb90 f0f1 \tsdiv\tr0, r0, r1
 8000114:\teb00 0001 \tadd.w\tr0, r0, r1
 8000118:\tfb10 2001 \tsmlabb\tr0, r0, r1, r2
 800011c:\tee30 0a20 \tvadd.f32\ts0, s0, s1
 8000120:\tee30 0b01 \tvadd.f64\td0, d0, d1
 8000124:\tfe00 0a20 \tvseleq.f32\ts0, s0, s1
 8000128:\tfcb4 0e88 \tvldrb.u16\tq0, [r4], #8
 800012c:\tf04e e001 \tdls\tlr, lr
 8000130:\t4770      \tbx\tlr
 8000132:\tbf00      \tnop
 8000134:\t08000100 \t.word\t0x08000100
\t...
 8000140:\t0801558c 080158de 080157c4 08015590     .U...X...W...U..

08000150 <__gnu_Unwind_Restore_VFP_D>:
 8000150:\tec90 0b20 \tvldmia\tr0, {d0-d15}
 8000154:\t4770      \tbx\tlr
'''


def out_of_place(cpu, disasm=DISASM):
    return [text.split()[0] for _, _, _, text, _ in insn_check.check(disasm, cpu)[2]]


class Disassembly(unittest.TestCase):
    def test_instructions_and_data(self):
        got = list(insn_check.instructions(DISASM))
        self.assertEqual(len(got), 18)                          # the .word, the dump and the '...' are no instructions
        self.assertEqual(got[1], (0x8000102, 'main', 2, True, 'bl', '8000110 <helper>'))
        self.assertEqual(got[3], (0x800010a, 'main', 10, False, 'cbz', 'r0, 8000110 <helper>'))
        self.assertEqual(got[6][1:3], ('helper', 0))

    def test_what_each_core_lacks(self):
        self.assertEqual(out_of_place('cortex-m0plus'), ['movw', 'cbz', 'sdiv', 'add.w', 'smlabb', 'vadd.f32',
                                                         'vadd.f64', 'vseleq.f32', 'vldrb.u16', 'dls'])
        self.assertEqual(out_of_place('cortex-m23'), ['add.w', 'smlabb', 'vadd.f32', 'vadd.f64', 'vseleq.f32',
                                                      'vldrb.u16', 'dls'])
        self.assertEqual(out_of_place('cortex-m3'), ['smlabb', 'vadd.f32', 'vadd.f64', 'vseleq.f32', 'vldrb.u16',
                                                     'dls'])
        self.assertEqual(out_of_place('cortex-m4'), ['vadd.f32', 'vadd.f64', 'vseleq.f32', 'vldrb.u16', 'dls'])
        self.assertEqual(out_of_place('cortex-m4f'), ['vadd.f64', 'vseleq.f32', 'vldrb.u16', 'dls'])
        self.assertEqual(out_of_place('cortex-m7'), ['vldrb.u16', 'dls'])
        self.assertEqual(out_of_place('cortex-m7-sp'), ['vadd.f64', 'vldrb.u16', 'dls'])
        self.assertEqual(out_of_place('cortex-m33f'), ['vadd.f64', 'vldrb.u16', 'dls'])
        self.assertEqual(out_of_place('cortex-m55-nofp'), ['vadd.f32', 'vadd.f64', 'vseleq.f32', 'vldrb.u16'])
        self.assertEqual(out_of_place('cortex-m55-nomve'), ['vldrb.u16'])
        self.assertEqual(out_of_place('cortex-m55'), [])
        self.assertEqual(out_of_place('cortex-m85'), [])

    def test_the_report_names_the_place_and_the_reason(self):
        checked, skipped, bad = insn_check.check(DISASM, 'cortex-m23')
        self.assertEqual((checked, skipped), (16, 2))           # the unwinder's helper is not checked
        self.assertEqual(bad[0], (0x8000114, 'helper', 4, 'add.w r0, r0, r1', ['thumb2']))
        self.assertEqual(bad[1][3:], ('smlabb r0, r0, r1, r2', ['dsp', 'thumb2']))

    def test_an_undefined_encoding_is_out_of_place_on_every_core(self):
        line = '08000100 <f>:\n 8000100:\te800 0000 \t\t\t@ <UNDEFINED> instruction: 0xe8000000\n'
        for cpu in ('cortex-m0', 'cortex-m4f', 'cortex-m85'):
            self.assertEqual(insn_check.check(line, cpu),
                             (1, 0, [(0x8000100, 'f', 0, '<UNDEFINED> instruction: 0xe8000000', ['undefined'])]))

    def test_conditions_and_widths(self):
        needs = insn_check.needs
        self.assertEqual(needs(False, 'bne.n'), set())
        self.assertEqual(needs(True, 'b.w'), {'base'})
        self.assertEqual(needs(True, 'bls.w'), {'base'})        # b with a condition, not bl
        self.assertEqual(needs(True, 'blt.w'), {'base'})
        self.assertEqual(needs(True, 'blx'), {'thumb2'})
        self.assertEqual(needs(True, 'bl'), set())
        self.assertEqual(needs(False, 'ite'), {'thumb2'})
        self.assertEqual(needs(False, 'movne'), set())          # its it is what the core lacks
        self.assertEqual(needs(True, 'smlabbne'), {'thumb2', 'dsp'})
        self.assertEqual(needs(True, 'bfc'), {'thumb2'})        # a bit field, not the branch future bf
        self.assertEqual(needs(True, 'msr', 'BASEPRI, r0'), {'thumb2'})
        self.assertEqual(needs(True, 'msr', 'PRIMASK, r0'), set())
        self.assertEqual(needs(True, 'vcvtpl.s32.f64', 's0, d0'), {'fp', 'fp64'})     # vcvt with a condition
        self.assertEqual(needs(True, 'vcvtp.s32.f64', 's0, d0'), {'fp', 'fp64', 'fpv5'})
        self.assertEqual(needs(True, 'vldmia', 'r0, {d16-d31}'), {'fp', 'd32'})
        self.assertEqual(needs(True, 'vmov', 'd0, r0, r1'), {'fp'})
        self.assertEqual(needs(True, 'vmrs', 'r0, VPR'), {'mve'})
        self.assertEqual(needs(True, 'letp', 'lr, 8000100 <f>'), {'mve'})
        self.assertEqual(needs(True, 'le', 'lr, 8000100 <f>'), {'v8.1m'})
        self.assertEqual(needs(True, 'mrc', '7, 0, r0, cr1, cr2, {0}'), {'coprocessor'})
        self.assertEqual(needs(True, 'ldc2', '14, cr0, [r4], #544'), {'coprocessor'})
        self.assertEqual(needs(True, '', '@ <UNDEFINED> instruction: 0xeca21e88'), {'undefined'})


# One instruction of every kind, or a few lines where one cannot stand alone (';' separates them). ARMv6-M first.
SAMPLES = '''
adds r0, r1, #1
movs r0, #5
ldr r0, [r1, #4]
push {r4, lr}
pop {r4, pc}
bx lr
blx r3
beq 1f; nop; 1:
b 1f; nop; 1:
svc 0
bkpt 0xab
cpsid i
wfi
nop
rev r0, r1
uxtb r0, r1
sxth r0, r1
mov r8, r0
muls r0, r1, r0
stmia r0!, {r1, r2}
udf #1
bl s0
msr primask, r0
mrs r0, ipsr
dsb sy
dmb sy
isb sy
udf.w #1
movw r0, #0x1234
movt r0, #0x1234
cbz r0, 1f; nop; 1:
cbnz r0, 1f; nop; 1:
b.w s0
sdiv r0, r1, r2
udiv r0, r1, r2
ldrex r0, [r1]
ldrexb r0, [r1]
ldrexh r0, [r1]
strex r0, r1, [r2]
strexb r0, r1, [r2]
strexh r0, r1, [r2]
clrex
lda r0, [r1]
ldab r0, [r1]
ldah r0, [r1]
stl r0, [r1]
stlb r0, [r1]
stlh r0, [r1]
ldaex r0, [r1]
ldaexb r0, [r1]
ldaexh r0, [r1]
stlex r0, r1, [r2]
stlexb r0, r1, [r2]
stlexh r0, r1, [r2]
sg
bxns r0
blxns r0
tt r0, r1
ttt r0, r1
tta r0, r1
ttat r0, r1
it ne; movne r0, r1
ite eq; moveq r0, r1; movne r0, r2
add.w r0, r1, r2
ldr.w r0, [r1, #4]
beq.w s0
tbb [r0, r1]
ubfx r0, r1, #2, #3
bfi r0, r1, #2, #3
bfc r0, #2, #3
clz r0, r1
rbit r0, r1
mls r0, r1, r2, r3
umull r0, r1, r2, r3
ldrd r0, r1, [r2]
strd r0, r1, [r2]
orn r0, r1, r2
push {r4-r11, lr}
addw r0, r1, #4095
mov.w r0, #0xff00
teq r0, r1
ssat r0, #8, r1
msr basepri, r0
mrs r0, basepri
msr faultmask, r0
vldr s0, [r0]
vstr s0, [r0]
vadd.f32 s0, s1, s2
vcvt.f32.s32 s0, s0
vcvt.s32.f32 s0, s0
vmov s0, r0
vmov r0, s0
vmov.f32 s0, s1
vmov.f32 s0, #1.0
vpush {d8-d15}
vpop {d8-d15}
vpush {s16-s31}
vldr d0, [r0]
vstr d0, [r0]
vmov d0, r0, r1
vmov r0, r1, d0
vldmia r0, {d0-d15}
vstmia r0, {d0-d15}
vmrs r0, fpscr
vmsr fpscr, r0
vmrs APSR_nzcv, fpscr
vcmp.f32 s0, s1
vsqrt.f32 s0, s1
vfma.f32 s0, s1, s2
vneg.f32 s0, s1
vcvtb.f32.f16 s0, s1
vcvtt.f16.f32 s0, s1
vadd.f64 d0, d1, d2
vmul.f64 d0, d1, d2
vdiv.f64 d0, d1, d2
vcvt.f64.s32 d0, s0
vcvt.s32.f64 s0, d0
vcvt.f64.f32 d0, s0
vcvt.f32.f64 s0, d0
vcmp.f64 d0, d1
vsqrt.f64 d0, d1
vfma.f64 d0, d1, d2
vmov.f64 d0, d1
vmov.f64 d0, #1.0
vneg.f64 d0, d1
vcvtb.f64.f16 d0, s0
vcvtb.f16.f64 s0, d0
vseleq.f32 s0, s1, s2
vselge.f32 s0, s1, s2
vmaxnm.f32 s0, s1, s2
vminnm.f32 s0, s1, s2
vrinta.f32 s0, s1
vrintn.f32 s0, s1
vrintp.f32 s0, s1
vrintm.f32 s0, s1
vrintz.f32 s0, s1
vrintx.f32 s0, s1
vrintr.f32 s0, s1
vcvta.s32.f32 s0, s1
vcvtn.s32.f32 s0, s1
vcvtp.u32.f32 s0, s1
vcvtm.s32.f32 s0, s1
vseleq.f64 d0, d1, d2
vmaxnm.f64 d0, d1, d2
vrintz.f64 d0, d1
vcvta.s32.f64 s0, d0
vadd.f16 s0, s1, s2
vcvt.f16.s32 s0, s0
vmov.f16 s0, #1.0
vldr.16 s0, [r0]
vldrb.u16 q0, [r4], #8
vstrh.16 q0, [r2], #16
vadd.i32 q0, q1, q2
vadd.f32 q0, q1, q2
vmov.i16 q0, #0x1
vdup.32 q0, r0
vpst; vaddt.i32 q0, q1, q2
vcmp.i16 eq, q0, q1
vctp.8 r0
vpnot
vpsel q0, q1, q2
vaddv.s8 r0, q0
vmrs r0, vpr
dlstp.16 lr, r3
wlstp.8 lr, r0, 1f; nop; 1:
1: nop; letp lr, 1b
lctp
asrl r0, r1, #3
lsll r0, r1, #3
lsrl r0, r1, #3
sqrshr r0, r1
uqshl r0, #3
dls lr, r0
wls lr, r0, 1f; nop; 1:
1: nop; le lr, 1b
csel r0, r1, r2, eq
csinc r0, r1, r2, eq
csinv r0, r1, r2, eq
csneg r0, r1, r2, eq
cinc r0, r1, ne
cinv r0, r1, ne
cneg r0, r1, ne
cset r0, ne
csetm r0, ne
clrm {r0-r3}
pac r12, lr, sp
aut r12, lr, sp
pacbti r12, lr, sp
bti
pacg r0, r1, r2
autg r0, r1, r2
bxaut r0, r1, r2
'''.strip().splitlines()
FOUR = re.compile(r'smla|(umaal|smlsd|smlsdx|smlsld|smlsldx|smmla|smmlar|smmls|smmlsr|usada8)$')
for name in sorted(insn_check.DSP):                             # every DSP instruction, with the operands it takes
    SAMPLES.append(f'{name} r0, #8, r1' if name in ('ssat16', 'usat16') else
                   f'{name} r0, r1' if name in ('sxtb16', 'uxtb16') else
                   f'{name} r0, r1, r2' + (', r3' if FOUR.match(name) else ''))


# Where the tool is stricter than clang's assembler. A single-precision FPU has no vmov.f64 between D registers: the
# assembler refuses it for the Cortex-M4F and the Cortex-M33, but takes it for a Cortex-M7 whose double precision
# -mfpu took away. The compiler does not emit it there: it copies a double as two vmov.f32.
STRICTER = {'cortex-m7-sp': {SAMPLES.index('vmov.f64 d0, d1')}}


@unittest.skipUnless(HAVE_TOOLS, 'needs LLVM and arm-none-eabi-gcc (python toolchain/paths.py)')
class Assembler(unittest.TestCase):
    """The assembler is the reference for what a core has: clang, with the flags of the core's entry."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.src = Path(cls.tmp.name) / 'samples.s'
        lines, cls.line_of = ['\t.syntax unified', '\t.thumb', '\t.text'], {}
        for i, sample in enumerate(SAMPLES):
            lines.append(f's{i}:')
            for part in filter(None, map(str.strip, sample.replace(':', ':;').split(';'))):
                lines.append(part if part.endswith(':') else '\t' + part)
                cls.line_of[len(lines)] = i
        cls.src.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        # the samples as objdump shows them, from an object assembled for the core that has them all
        obj = Path(cls.tmp.name) / 'samples.o'
        r = cls.assemble('cortex-m85', obj)
        assert r.returncode == 0, r.stderr
        dump = subprocess.run([str(paths.gcc_bin('objdump')), '-d', '-m', 'armv8.1-m.main', obj.name],
                              cwd=obj.parent, capture_output=True, text=True, errors='replace').stdout
        cls.needs = {}
        for _, name, _, wide, mnemonic, operands in insn_check.instructions(dump):
            cls.needs.setdefault(int(name[1:]), set()).update(insn_check.needs(wide, mnemonic, operands))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def assemble(cls, cpu, obj):
        code = ('import subprocess, sys; sys.path.insert(0, sys.argv[1]); import paths\n'
                'sys.exit(subprocess.run([str(paths.clang()), *paths.target_flags(), "-c", sys.argv[2], "-o", '
                'sys.argv[3]]).returncode)\n')
        return subprocess.run([sys.executable, '-c', code, str(ROOT / 'toolchain'), str(cls.src), str(obj)],
                              capture_output=True, text=True, errors='replace', env={**os.environ, 'KMICRO_CPU': cpu})

    def test_every_sample_was_read(self):
        self.assertEqual(sorted(self.needs), list(range(len(SAMPLES))))

    def test_the_tool_and_the_assembler_agree_for_every_core(self):
        for cpu in paths.CORES:
            with self.subTest(cpu=cpu):
                r = self.assemble(cpu, Path(self.tmp.name) / f'{cpu}.o')
                refused = set()
                for line in re.findall(r'samples\.s:(\d+):\d+: error', r.stderr):
                    refused.add(self.line_of.get(int(line), -1))
                self.assertNotIn(-1, refused, r.stderr[:600])
                has = insn_check.features(cpu)
                lacks = {i for i, need in self.needs.items() if need - has} - STRICTER.get(cpu, set())
                self.assertEqual([SAMPLES[i] for i in sorted(lacks - refused)], [],
                                 'the tool refuses these, the assembler takes them')
                self.assertEqual([SAMPLES[i] for i in sorted(refused - lacks)], [],
                                 'the assembler refuses these, the tool takes them')


@unittest.skipUnless(HAVE_TOOLS, 'needs LLVM and arm-none-eabi-gcc (python toolchain/paths.py)')
class CommandLine(unittest.TestCase):
    def test_exit_status_and_report(self):
        with tempfile.TemporaryDirectory() as d:
            src, obj = Path(d) / 'f.s', Path(d) / 'f.o'
            src.write_text('\t.syntax unified\n\t.thumb\nf:\n\tadds r0, r1, #1\n\tmovw r0, #4660\n\tbx lr\n',
                           encoding='utf-8')
            subprocess.run([str(paths.clang()), '--target=thumbv7m-none-eabi', '-c', str(src), '-o', str(obj)],
                           check=True)
            tool = [sys.executable, str(ROOT / 'tools/insn_check.py'), str(obj)]
            r = subprocess.run([*tool, '--cpu', 'cortex-m23'], capture_output=True, text=True)
            self.assertEqual((r.returncode, r.stdout), (0, 'insn_check: f.o: 3 instructions, each of them one that '
                                                           'cortex-m23 has\n'), r.stderr)
            r = subprocess.run([*tool, '--cpu', 'cortex-m0plus'], capture_output=True, text=True)
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertEqual(r.stdout.splitlines(),
                             ['insn_check: f.o: 1 of 3 instructions are not ones that cortex-m0plus has',
                              '  0x00000002  f+0x2  movw r0, #4660  (needs ARMv7-M or ARMv8-M)'])
            r = subprocess.run([*tool[:2], str(Path(d) / 'none.elf')], capture_output=True, text=True)
            self.assertEqual(r.returncode, 2)
            self.assertIn('not found', r.stderr)


if __name__ == '__main__':
    unittest.main()

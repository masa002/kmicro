#!/usr/bin/env python3
# Copyright 2026 the kmicro authors (NOTICE).
# SPDX-License-Identifier: Apache-2.0
"""Static check of a firmware image: every instruction is one that the core has.

    python tools/insn_check.py firmware.elf [--cpu CORE] [--all]

    --cpu  the core the image is for (toolchain/paths.py CORES; default cortex-m4f, or KMICRO_CPU)
    --all  list every instruction that is out of place (default: the first 20)

An image is built for one core and often tested on another: QEMU has no Cortex-M0+ and no Cortex-M23, so their code
runs on a larger core, which also runs an instruction the smaller one does not have. A board with the smaller core
stops there with a fault. This check reads the machine code (arm-none-eabi-objdump -d) and fails for an instruction
outside the instruction set of the core, as the compiler's flags for --cpu define it:

- ARMv6-M (Cortex-M0, M0+, M1): the 16-bit Thumb instructions without cbz, cbnz and it, and of the 32-bit ones only
  bl, msr, mrs, dsb, dmb and isb;
- ARMv8-M Baseline (Cortex-M23) adds movw, movt, cbz, cbnz, the 32-bit b without a condition, sdiv, udiv, the
  exclusive loads and stores, and what ARMv8-M adds to every core (lda, stl and their kin, sg, bxns, blxns, tt);
- the other cores have the rest of Thumb-2, the 32-bit b<condition> (beq.w) among it; the DSP instructions
  (smlabb, qadd, uxtab ...) from ARMv7E-M on;
- an FPU instruction needs an FPU, one on double-precision values (vadd.f64) a double-precision FPU, vsel, vrint,
  vmaxnm, vminnm and vcvta/n/p/m an FPv5, one on half-precision values the FPU of ARMv8.1-M;
- MVE instructions, the low-overhead loops, csel and clrm need ARMv8.1-M, the first of them MVE;
- pacg, autg and bxaut need PACBTI, which a Cortex-M85 can have. (pac, aut, pacbti and bti are hints: a core
  without PACBTI runs them as nop.) A coprocessor instruction or an undefined one is out of place everywhere.

tests/unit/test_insn_check.py assembles one instruction of every kind for every core and checks that this file and
the assembler agree on which cores have it.

Not checked: the functions of libgcc's unwinder that save and restore FPU and iWMMXt registers
(__gnu_Unwind_Save_VFP_D and the like). Every libgcc has them, also the one for a core without those registers, and
they run only when an unwind table names such a register, which no code built for that core does. The data that
the disassembly marks as data (literal pools, tables) is skipped.

The instruction sets are those of the Cortex-M cores. An image for a core of another profile (cortex-a7) is not
checked: the tool says so and exits 2.

Exit status: 0 when every instruction is one of the core's, 1 when one is not, 2 when the image cannot be read.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'toolchain'))
import binutils  # noqa: E402
import paths  # noqa: E402

# What a core has beyond ARMv6-M, by the architecture of its triple and by its FPU (paths.CORES).
ARCH = {'thumbv6m': set(),
        'thumbv8m.base': {'base', 'v8m'},
        'thumbv7m': {'base', 'thumb2'},
        'thumbv7em': {'base', 'thumb2', 'dsp'},
        'thumbv8m.main': {'base', 'v8m', 'thumb2', 'dsp'},
        'thumbv8.1m.main': {'base', 'v8m', 'thumb2', 'dsp', 'v8.1m'}}
FPU = {'none': set(), 'fpv4-sp-d16': {'fp'}, 'fpv5-sp-d16': {'fp', 'fpv5'}, 'fpv5-d16': {'fp', 'fpv5', 'fp64'},
       'fp-armv8-fullfp16-d16': {'fp', 'fpv5', 'fp64', 'fp16'}}
NEEDS = {'base': 'ARMv7-M or ARMv8-M', 'v8m': 'ARMv8-M', 'thumb2': 'Thumb-2 (ARMv7-M, ARMv8-M Mainline)',
         'dsp': 'the DSP extension', 'fp': 'an FPU', 'fp64': 'a double-precision FPU', 'fpv5': 'an FPv5 FPU',
         'fp16': 'the half-precision FPU of ARMv8.1-M', 'd32': 'the registers d16 to d31', 'mve': 'MVE',
         'v8.1m': 'ARMv8.1-M', 'pacbti': 'PACBTI', 'coprocessor': 'a coprocessor'}

CONDS = ('eq', 'ne', 'cs', 'hs', 'cc', 'lo', 'mi', 'pl', 'vs', 'vc', 'hi', 'ls', 'ge', 'lt', 'gt', 'le')
V6M_WIDE = {'bl', 'msr', 'mrs', 'dsb', 'dmb', 'isb'}               # the 32-bit instructions of ARMv6-M
BASE = {'movw', 'movt', 'sdiv', 'udiv', 'ldrex', 'ldrexb', 'ldrexh', 'strex', 'strexb', 'strexh', 'clrex'}
V8M = {'lda', 'ldab', 'ldah', 'stl', 'stlb', 'stlh', 'ldaex', 'ldaexb', 'ldaexh', 'stlex', 'stlexb', 'stlexh', 'sg',
       'tt', 'ttt', 'tta', 'ttat', 'bxns', 'blxns'}
DSP = set('''qadd qdadd qsub qdsub sadd16 sadd8 ssub16 ssub8 sasx ssax qadd16 qadd8 qsub16 qsub8 qasx qsax shadd16
    shadd8 shsub16 shsub8 shasx shsax uadd16 uadd8 usub16 usub8 uasx usax uqadd16 uqadd8 uqsub16 uqsub8 uqasx uqsax
    uhadd16 uhadd8 uhsub16 uhsub8 uhasx uhsax smlabb smlabt smlatb smlatt smlad smladx smlalbb smlalbt smlaltb
    smlaltt smlald smlaldx smlawb smlawt smlsd smlsdx smlsld smlsldx smmla smmlar smmls smmlsr smmul smmulr smuad
    smuadx smulbb smulbt smultb smultt smulwb smulwt smusd smusdx umaal pkhbt pkhtb sel ssat16 usat16 sxtab
    sxtab16 sxtah sxtb16 uxtab uxtab16 uxtah uxtb16 usad8 usada8'''.split())
V81M = {'dls', 'wls', 'le', 'csel', 'csinc', 'csinv', 'csneg', 'cinc', 'cinv', 'cneg', 'cset', 'csetm', 'clrm',
        'vscclrm', 'bf', 'bfl', 'bfx', 'bflx', 'bfcsel'}
MVE = {'dlstp', 'wlstp', 'letp', 'lctp', 'vctp', 'vpnot', 'vpsel', 'asrl', 'lsll', 'lsrl', 'sqrshr', 'sqrshrl',
       'sqshl', 'sqshll', 'srshr', 'srshrl', 'uqrshl', 'uqrshll', 'uqshl', 'uqshll', 'urshr', 'urshrl'}
PACBTI = {'pacg', 'autg', 'bxaut'}                 # pac, aut, pacbti and bti are hints: a nop without PACBTI
COPROCESSOR = re.compile(r'(cdp|ldc|stc|mcr|mrc|mcrr|mrrc)2?l?$')
FPV5 = re.compile(r'vsel(eq|ge|gt|vs)$|v(max|min)nm$|vrint[anpmxzr]|vcvt[anpm]$')
FP_OLD = {'fldmiax', 'fstmiax', 'fldmdbx', 'fstmdbx'}             # as objdump names vldmia and vstmia of an odd length
UNWIND_HELPERS = re.compile(r'__gnu_Unwind_(Save|Restore)_(VFP|VFP_D|VFP_D_16_to_31|WMMXD|WMMXC)$')
INSN = re.compile(r'^\s*([0-9a-f]+):\t([0-9a-f]{4})( [0-9a-f]{4})? *\t(\S*)(?:\t(.*))?$')
LABEL = re.compile(r'^([0-9a-f]+) <(.+)>:$')


def features(cpu):
    """What the core has beyond ARMv6-M: read from its entry in paths.CORES, the flags everything is built with."""
    target, flags, _ = paths.CORES[cpu]
    mcpu = next(f for f in flags if f.startswith('-mcpu='))
    fpu = next(f for f in flags if f.startswith('-mfpu='))[len('-mfpu='):]
    has = ARCH[target.split('-')[0]] | FPU[fpu]
    if 'v8.1m' in has and 'fp' in has and '+nomve' not in mcpu:
        has = has | {'mve'}
    if mcpu.startswith('-mcpu=cortex-m85'):
        has = has | {'pacbti'}
    return has


def root(m, names):
    """The mnemonic without a condition (smlabbne -> smlabb), when that is one of the names."""
    if m in names:
        return m
    return m[:-2] if m[-2:] in CONDS and m[:-2] in names else None


def fp_needs(m, operands):
    """An instruction on the registers of the FPU: m is the mnemonic without .w."""
    name, _, kind = m.partition('.')
    if re.search(r'\bq[0-7]\b|\bvpr\b|\bp0\b', operands, re.I) or re.match(r'vp(st|t)', name) or root(name, MVE):
        return {'mve'}
    need = {'fp'}
    if 'f64' in kind:
        need.add('fp64')
    if kind == '16' or 'f16' in kind and not re.match(r'vcvt[bt]', name):   # vcvtb, vcvtt: every FPU has them
        need.add('fp16')
    if FPV5.match(name) or (re.match(r'vcvt[bt]', name) and 'f64' in kind):
        need.add('fpv5')
    if re.search(r'\bd(1[6-9]|2[0-9]|3[01])\b', operands):
        need.add('d32')
    return need


def needs(wide, mnemonic, operands=''):
    """What a core must have for the instruction, as a set of the names in NEEDS (or 'undefined', which no core
    has): empty for an instruction of ARMv6-M. wide: the encoding has 32 bits."""
    m = re.sub(r'\.[nw]$', '', mnemonic.lower())
    if not m or '<UNDEFINED>' in operands:        # objdump gives an undefined encoding no mnemonic
        return {'undefined'}
    if root(m, V81M):
        return {'v8.1m'}
    if m.partition('.')[0] in MVE or root(m, MVE):
        return {'mve'}
    if m[0] == 'v' or m in FP_OLD:
        return fp_needs(m, operands)
    if root(m, PACBTI):
        return {'pacbti'}
    if COPROCESSOR.match(m):
        return {'coprocessor'}
    if root(m, V8M):
        return {'v8m'}
    if root(m, {'msr', 'mrs'}):                 # the registers ARMv6-M and ARMv8-M Baseline do not have
        return {'thumb2'} if re.search(r'basepri|faultmask', operands, re.I) else set()
    if not wide:
        return {'base'} if m in ('cbz', 'cbnz') else {'thumb2'} if re.match(r'it[te]{0,3}$', m) else set()
    if m in V6M_WIDE:
        return set()
    if m[0] == 'b' and m[1:] in CONDS:          # bls is b with a condition, not bl; Baseline has only the plain b
        return {'thumb2'}
    if m == 'b' or root(m, BASE):
        return {'base'}
    return {'thumb2', 'dsp'} if root(m, DSP) else {'thumb2'}


def instructions(disasm):
    """objdump -d text -> (address, function, offset, 32 bits?, mnemonic, operands) of every instruction. Data is
    not an instruction: .word lines, and the dumps of longer data, which have no mnemonic."""
    name, start = '?', 0
    for line in disasm.splitlines():
        m = LABEL.match(line)
        if m:
            start, name = int(m.group(1), 16), m.group(2)
            continue
        m = INSN.match(line)
        if m and not m.group(4).startswith('.'):
            addr = int(m.group(1), 16)
            yield addr, name, addr - start, bool(m.group(3)), m.group(4), (m.group(5) or '').strip()


def check(disasm, cpu):
    """(instructions checked, instructions in the unwinder's helpers, [(address, function, offset, text, what the
    core lacks)])."""
    has, checked, skipped, bad = features(cpu), 0, 0, []
    for addr, name, offset, wide, mnemonic, operands in instructions(disasm):
        if UNWIND_HELPERS.match(name):
            skipped += 1
            continue
        checked += 1
        lacks = needs(wide, mnemonic, operands) - has
        if lacks:
            text = f'{mnemonic} {operands.split("@")[0].strip()}'.strip() or operands.strip('@ \t')
            bad.append((addr, name, offset, text, sorted(lacks)))
    return checked, skipped, bad


def main():
    p = argparse.ArgumentParser(prog='insn_check.py', description=__doc__.split('\n\n')[0])
    p.add_argument('elf', type=Path, help='the linked image (qbuild output or your board build)')
    paths.add_cpu_option(p, 'the core the image is for (default cortex-m4f, or KMICRO_CPU)')
    p.add_argument('--all', action='store_true', help='list every instruction that is out of place')
    a = p.parse_args()
    cpu = paths.select_cpu(a.cpu)
    if paths.profile() != 'M':
        print(f'insn_check.py: {cpu} is not a Cortex-M core, and this check knows the instruction sets of those only',
              file=sys.stderr)
        sys.exit(2)
    if not a.elf.is_file():
        print(f'insn_check.py: {a.elf}: not found', file=sys.stderr)
        sys.exit(2)
    # as ARMv8.1-M code, whatever the image's build attributes say: every instruction then has its own name
    r = binutils.run('objdump', a.elf, '-d', '-m', 'armv8.1-m.main')
    if r.returncode != 0:
        print(f'insn_check.py: objdump failed: {r.stderr.strip()[:500]}', file=sys.stderr)
        sys.exit(2)
    checked, skipped, bad = check(r.stdout, cpu)
    if not checked:
        print(f'insn_check.py: {a.elf.name}: no instructions found', file=sys.stderr)
        sys.exit(2)
    helpers = f' ({skipped} more in the register helpers of libgcc\'s unwinder, not checked)' if skipped else ''
    if not bad:
        print(f'insn_check: {a.elf.name}: {checked} instructions, each of them one that {cpu} has{helpers}')
        return
    print(f'insn_check: {a.elf.name}: {len(bad)} of {checked} instructions are not ones that {cpu} has{helpers}')
    for addr, name, offset, text, lacks in bad if a.all else bad[:20]:
        why = 'no instruction' if 'undefined' in lacks else 'needs ' + ', '.join(NEEDS[n] for n in lacks)
        print(f'  0x{addr:08x}  {name}+0x{offset:x}  {text}  ({why})')
    if len(bad) > 20 and not a.all:
        print(f'  ... and {len(bad) - 20} more (--all lists them)')
    sys.exit(1)


if __name__ == '__main__':
    main()

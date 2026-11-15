# Copyright 2026 the kmicro authors (NOTICE).
# SPDX-License-Identifier: Apache-2.0
"""The largest stack frames of a linked image, read from its machine code.

    python tools/frames.py app.elf [--top N] [--limit BYTES] [--allow FUNCTION]

    --top    how many functions to list (default 10)
    --limit  exit 1 when a frame is larger than BYTES, or of a size the function computes (for a build script)
    --allow  a function whose computed size --limit accepts

A frame is what a function's prologue takes from the stack: the registers it pushes (push/stmdb, vpush) and the
space it reserves (sub sp). This is counted after linking because LTO inlines functions into their callers and
merges their frames: a Kotlin `fun main()` with a local `IntArray(14000)` shows up as a 56 KB frame of whatever it
was inlined into, often the start code's run_main. kbuild warns about such arrays by function name before linking
(--stack-array-limit); a frame is the stack a call needs, on top of its callers' frames.

A function with a variable-length array or alloca() takes more than its prologue does, by an amount it computes when
it runs. It is listed first, with a `+` after the bytes of its prologue.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'toolchain'))
import binutils  # noqa: E402

PROLOGUE = 24                                  # instructions looked at per function
STACK_GUARD = 4096                             # bytes below the stack of the QEMU targets (targets/qemu-l475/*.ld)
READS = ('str', 'cmp', 'cmn', 'tst', 'teq', 'cb')      # instructions that only read their first operand


def reg_count(regs):
    """'{r4, r5, r6, r7, r8, r9, sl, lr}' or '{r4-r11, lr}' or '{d8-d15}' -> number of registers."""
    n = 0
    for r in regs.strip('{} ').split(','):
        a, _, b = r.strip().partition('-')
        n += int(b[1:]) - int(a[1:]) + 1 if b else 1
    return n


def frames(disasm, dynamic=None):
    """objdump -d text -> {function: bytes its prologue takes from the stack}. dynamic: a set that gets the functions
    that take more by an amount they compute (a variable-length array, alloca)."""
    out, name, seen, imm, held = {}, None, 0, {}, {}
    # literal pools: ARMv6-M code loads a frame size that no instruction can hold from one (ldr r7, [pc, #N])
    words = {int(a, 16): int(v, 16)
             for a, v in re.findall(r'^\s*([0-9a-f]+):\s+\.word\s+0x([0-9a-f]+)', disasm, re.M)}
    for line in disasm.splitlines():
        m = re.match(r'^[0-9a-f]+ <(.+)>:$', line)
        if m:
            name, seen, imm, held = m.group(1), 0, {}, {}
            out[name] = 0
            continue
        m = re.match(r'^\s*[0-9a-f]+:\s+(\S+)\s*(.*)$', line)
        if not name or not m:
            continue
        op, args = m.group(1), m.group(2).split('@')[0].split(';')[0].strip()
        # Stack taken by an amount the function computes, anywhere in it: sp is set from a register that holds sp
        # less something (`sub.w r4, sp, r0; mov sp, r4`, on ARMv6-M `mov r2, sp; subs r4, r2, r0; mov sp, r4`), or a
        # register is taken from sp. held: a register -> 'sp' when it is a copy of sp, 'below' when it is sp less
        # something. The frame pointer is neither: `mov sp, r7` gives the stack back.
        a = [x.strip() for x in args.split(',')]
        if dynamic is not None and len(a) >= 2 and not op.startswith(READS):
            if op.startswith('sub') and a[0] == 'sp':
                if seen >= PROLOGUE and not a[-1].startswith('#'):             # in the prologue: counted below
                    dynamic.add(name)
            elif op.startswith('mov') and a[0] == 'sp':
                if held.get(a[1]) == 'below':
                    dynamic.add(name)
            elif op.startswith('mov') and (a[1] == 'sp' or a[1] in held):
                held[a[0]] = held.get(a[1], 'sp')
            elif op.startswith('sub') and (a[len(a) > 2] == 'sp' or a[len(a) > 2] in held):
                held[a[0]] = 'below'                   # `sub.w r4, sp, r0`, `subs r4, r2, r0`, `subs r4, #8`
            else:
                held.pop(a[0], None)
        if seen >= PROLOGUE:
            continue
        seen += 1
        if op in ('push', 'push.w') or (op in ('stmdb', 'stmdb.w', 'stmfd') and args.startswith('sp!')):
            out[name] += 4 * reg_count(args[args.index('{'):])
        elif op in ('vpush', 'vpush.64', 'vpush.32', 'vstmdb'):
            regs = args[args.index('{'):]
            out[name] += (8 if 'd' in regs else 4) * reg_count(regs)
        elif op in ('movw', 'mov.w', 'mov', 'movs') and re.match(r'^(\w+), #(\d+)$', args):
            r, v = re.match(r'^(\w+), #(\d+)$', args).groups()
            imm[r] = int(v)
        elif op == 'ldr' and re.match(r'^(\w+), \[pc, ', args) and '@ (' in m.group(2):
            literal = int(m.group(2).split('@ (')[1].split()[0].rstrip(')'), 16)
            if literal in words:
                imm[args.split(',')[0]] = words[literal]
        elif op == 'add' and re.match(r'^sp,\s*(?:sp,\s*)?(\w+)$', args):
            v = imm.get(re.match(r'^sp,\s*(?:sp,\s*)?(\w+)$', args).group(1), 0)
            if v >= 1 << 31:                   # add sp, rN with a negative size from a literal pool
                out[name] += (1 << 32) - v
        elif op in ('sub', 'sub.w', 'subw') and args.startswith('sp,'):
            m2 = re.match(r'^sp,\s*(?:sp,\s*)?(#(\d+)|(\w+))$', args)
            if m2:
                out[name] += int(m2.group(2)) if m2.group(2) else imm.get(m2.group(3), 0)
                if dynamic is not None and m2.group(3) and m2.group(3) not in imm:
                    dynamic.add(name)              # a register with no constant in it
        elif op in ('bl', 'blx'):
            seen = PROLOGUE                    # the prologue ends at the first call; an early return may come
                                               # before it (bxeq lr, cbz), the frame only on the longer path
    return out


def of_image(elf):
    """([(function, bytes)], the functions that take more by an amount they compute) for a linked image; those
    functions first, then the largest frame first."""
    r = binutils.run('objdump', elf, '-d', '--no-show-raw-insn')
    if r.returncode != 0:
        sys.exit(f'frames.py: objdump failed: {r.stderr.strip()[:500]}')
    dynamic = set()
    f = frames(r.stdout, dynamic)
    if all(name.startswith('.') for name in f):   # a stripped image: the code of a section under its name, `<.text>:`
        sys.exit(f'frames.py: {Path(elf).name} has no function symbols: its functions cannot be told apart')
    return sorted(f.items(), key=lambda kv: (kv[0] not in dynamic, -kv[1])), dynamic


def over_guard(elf):
    """What run_all and difftest report for an image with a frame larger than the stack guard, or of a size the
    function computes; None without one."""
    f, dynamic = of_image(elf)
    name, size = max(f, key=lambda kv: kv[1])
    if size > STACK_GUARD:
        return (f'{name} has a stack frame of {size} bytes, larger than the {STACK_GUARD}-byte stack guard of '
                f'qemu-l475, which it could step over without a fault')
    if dynamic:
        return (f'{f[0][0]} has a stack frame of a size it computes (a variable-length array or alloca), which could '
                f'step over the {STACK_GUARD}-byte stack guard of qemu-l475 without a fault')
    return None


def main():
    p = argparse.ArgumentParser(prog='frames.py', description=__doc__.split('\n\n')[0])
    p.add_argument('elf', type=Path, help='the linked image (qbuild output or your board build)')
    p.add_argument('--top', type=int, default=10, metavar='N', help='how many functions to list (default 10)')
    p.add_argument('--limit', type=int, metavar='BYTES',
                   help='exit 1 when a frame is larger than BYTES, or of a size the function computes')
    p.add_argument('--allow', action='append', default=[], metavar='FUNCTION',
                   help='a function with a variable-length array or alloca that --limit accepts (may be repeated)')
    a = p.parse_args()
    if not a.elf.exists():
        p.error(f'{a.elf}: not found')
    f, dynamic = of_image(a.elf)
    print(f'largest stack frames of {a.elf.name} (bytes a call takes, LTO-merged):')
    for name, size in f[:a.top]:
        print(f'{size:8d}{"+" if name in dynamic else " "} {name}')
    if dynamic & {name for name, _ in f[:a.top]}:
        print('       +: and what the function computes when it runs (a variable-length array or alloca)')
    if a.limit is None:
        return
    name, size = max(f, key=lambda kv: kv[1])
    if size > a.limit:
        sys.exit(f'frames.py: {name} takes {size} bytes of stack, more than --limit {a.limit}')
    for name in sorted(dynamic - set(a.allow)):
        sys.exit(f'frames.py: {name} takes stack of a size it computes (a variable-length array or alloca), which '
                 f'--limit cannot check; --allow {name} accepts it')


if __name__ == '__main__':
    main()

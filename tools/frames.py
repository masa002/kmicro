"""The largest stack frames of a linked image, read from its machine code.

    python tools/frames.py app.elf [--top N] [--limit BYTES]

    --top    how many functions to list (default 10)
    --limit  exit 1 when a frame is larger than BYTES (for a build script)

A frame is what a function's prologue takes from the stack: the registers it pushes (push/stmdb, vpush) and the
space it reserves (sub sp). This is counted after linking because LTO inlines functions into their callers and
merges their frames: a Kotlin `fun main()` with a local `IntArray(14000)` shows up as a 56 KB frame of whatever it
was inlined into, often the start code's run_main. kbuild warns about such arrays by function name before linking
(--stack-array-limit); a frame is the stack a call needs, on top of its callers' frames.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'toolchain'))
import binutils  # noqa: E402

PROLOGUE = 24                                  # instructions looked at per function
STACK_GUARD = 4096                             # bytes below the stack of the QEMU targets (targets/qemu-l475/*.ld)


def reg_count(regs):
    """'{r4, r5, r6, r7, r8, r9, sl, lr}' or '{r4-r11, lr}' or '{d8-d15}' -> number of registers."""
    n = 0
    for r in regs.strip('{} ').split(','):
        a, _, b = r.strip().partition('-')
        n += int(b[1:]) - int(a[1:]) + 1 if b else 1
    return n


def frames(disasm):
    """objdump -d text -> {function: bytes its prologue takes from the stack}."""
    out, name, seen, imm = {}, None, 0, {}
    # literal pools: ARMv6-M code loads a frame size that no instruction can hold from one (ldr r7, [pc, #N])
    words = {int(a, 16): int(v, 16)
             for a, v in re.findall(r'^\s*([0-9a-f]+):\s+\.word\s+0x([0-9a-f]+)', disasm, re.M)}
    for line in disasm.splitlines():
        m = re.match(r'^[0-9a-f]+ <(.+)>:$', line)
        if m:
            name, seen, imm = m.group(1), 0, {}
            out[name] = 0
            continue
        m = re.match(r'^\s*[0-9a-f]+:\s+(\S+)\s*(.*)$', line)
        if not name or not m or seen >= PROLOGUE:
            continue
        seen += 1
        op, args = m.group(1), m.group(2).split('@')[0].split(';')[0].strip()
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
        elif op in ('bl', 'blx'):
            seen = PROLOGUE                    # the prologue ends at the first call; an early return may come
                                               # before it (bxeq lr, cbz), the frame only on the longer path
    return out


def of_image(elf):
    """[(function, bytes)] for a linked image, the largest frame first."""
    r = binutils.run('objdump', elf, '-d', '--no-show-raw-insn')
    if r.returncode != 0:
        sys.exit(f'frames.py: objdump failed: {r.stderr.strip()[:500]}')
    return sorted(frames(r.stdout).items(), key=lambda kv: -kv[1])


def over_guard(elf):
    """What run_all and difftest report for an image with a frame larger than the stack guard; None without one."""
    name, size = of_image(elf)[0]
    if size > STACK_GUARD:
        return (f'{name} has a stack frame of {size} bytes, larger than the {STACK_GUARD}-byte stack guard of '
                f'qemu-l475, which it could step over without a fault')
    return None


def main():
    p = argparse.ArgumentParser(prog='frames.py', description=__doc__.split('\n\n')[0])
    p.add_argument('elf', type=Path, help='the linked image (qbuild output or your board build)')
    p.add_argument('--top', type=int, default=10, metavar='N', help='how many functions to list (default 10)')
    p.add_argument('--limit', type=int, metavar='BYTES', help='exit 1 when a frame is larger than BYTES')
    a = p.parse_args()
    if not a.elf.exists():
        p.error(f'{a.elf}: not found')
    f = of_image(a.elf)
    print(f'largest stack frames of {a.elf.name} (bytes a call takes, LTO-merged):')
    for name, size in f[:a.top]:
        print(f'{size:8d}  {name}')
    if a.limit is not None and f and f[0][1] > a.limit:
        sys.exit(f'frames.py: {f[0][0]} takes {f[0][1]} bytes of stack, more than --limit {a.limit}')


if __name__ == '__main__':
    main()

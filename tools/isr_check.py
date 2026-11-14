#!/usr/bin/env python3
"""Static check of a firmware image: no interrupt handler can reach a Kotlin allocation.

    python tools/isr_check.py firmware.elf [--callback NAME ...] [--boxing]

    --callback  a function handlers reach only through a pointer (a callback registered with a driver): C functions
                by name, Kotlin ones by their mangled name, e.g. 'kfun:app#onTimer(){}' (an alias is no label)
    --boxing    also list every call outside the standard library that boxes an Int, Long, Short or Byte, in any
                code (an unsigned == / != or a generic container of a primitive), and fail on them

The handlers are the entries of the vector table (.isr_vector, without the initial stack pointer and the reset
handler), whatever their names: under LTO the C name kbuild --c-api gives a Kotlin handler (SysTick_Handler) is
folded into the Kotlin function, so only the table still shows it. Functions named like handlers (C names ending in
_Handler or _IRQHandler, Kotlin functions ending in Handler) are checked too, for handlers installed at run time.

Walks the machine code (arm-none-eabi-objdump -d) from every handler along direct calls and tail branches, and
reports each path that ends in the Kotlin allocator (AllocInstance, AllocArrayInstance and kmicro's allocation
functions) or in a boxing function. The heap is not reentrant, so a handler that allocates can corrupt it (kmicro
also stops at run time with "allocation inside an interrupt handler"). Paths through the throw helpers of the
runtime and the standard library (ThrowException, kfun:kotlin.native.internal#Throw...) are not followed: those only
run on a bug (an index out of bounds, a null), and the run-time guard covers them.
Indirect calls (function pointers, virtual calls) cannot be followed here and are counted per handler: a handler
that has one is not proven clean. --callback names the functions such a call reaches.

Exit status: 0 when no handler reaches an allocation, 1 when one does (or --boxing finds a box), 2 when the image
cannot be read or has no handler.
"""
import argparse
import re
import subprocess
import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'toolchain'))
import paths  # noqa: E402

ALLOC = {'AllocInstance', 'AllocArrayInstance', 'kmicro_alloc_object', 'kmicro_alloc_array', 'alloc_block'}
BOX = re.compile(r'<U?(Int|Byte|Short|Long)-box>')
HANDLER_NAME = re.compile(r'\w+_(IRQ)?Handler|kfun:[^#]*#\w*Handler\(\)\{\}')
# A transfer through a register or a loaded address: a call (blx r3), a tail call (bx r3, mov pc, r3) or a load into
# pc. A function's own return is not one: bx lr, mov pc, lr, pop {.., pc}, ldr pc, [sp], #4.
INDIRECT = re.compile(r'\t(?:blx\w*\s|bx\w*\s+(?!lr\b)|mov\w*\s+pc, (?!lr\b)|ldr\S*\s+pc, \[(?!sp\b))')


def lazy(name):
    """Kotlin create-on-first-use points: a file's globals, an object or a companion. Safe in a handler only if
    the thread code used them first; kmicro stops at run time otherwise. Listed so each one can be checked."""
    return name == 'CallInitGlobalPossiblyLock' or '<get-$companion>' in name or '<get-$instance>' in name


def throw_helper(name):
    """The functions that exist only to throw: the runtime's C functions (ThrowException, ThrowNullPointerException)
    and the standard library's own helpers (kfun:kotlin.native.internal#ThrowNoWhenBranchMatchedException). A user
    function such as sendOrThrow is followed like any other."""
    return name.startswith('Throw') or (name.startswith(('kfun:kotlin.', 'kfun:kotlin#')) and
                                        name.split('#')[-1].startswith('Throw'))


def parse_disassembly(text):
    """objdump -d output -> (calls: function -> the functions it calls or tail-branches to, indirect: function ->
    number of indirect calls, start: address -> function)."""
    calls, indirect, start, cur = {}, {}, {}, None
    for line in text.splitlines():
        m = re.match(r'^([0-9a-f]+) <(.+)>:$', line)
        if m:
            cur = m.group(2)
            start.setdefault(int(m.group(1), 16), cur)
            calls.setdefault(cur, set())
            indirect.setdefault(cur, 0)
            continue
        if cur is None:
            continue
        # Kotlin names contain '<' and '>' (kotlin#<UInt-box>, <get-$companion>): take everything up to the last
        # '>' of the line, minus a +0x offset.
        # A call or tail call lands on a function's first instruction; a target inside another function (+0x..)
        # comes from padding or a literal pool decoded as an instruction, and is no edge.
        m = re.search(r'\t(b[a-z]*(?:\.[nw])?)\s+[0-9a-f]+ <(.+?)(\+0x[0-9a-f]+)?>\s*$', line)
        if m and m.group(3):
            m = None
        if m and m.group(2) != cur:
            calls[cur].add(m.group(2))
        elif INDIRECT.search(line):
            indirect[cur] += 1
    return calls, indirect, start


def vector_words(text):
    """objdump -s -j .isr_vector output -> the table's 32-bit words, in order."""
    data = bytearray()
    for line in text.splitlines():
        if not re.match(r'^ [0-9a-f]+ [0-9a-f]', line):
            continue
        hexpart = line[1:].split('  ')[0].split()[1:]      # address, up to 4 groups of bytes, then the ASCII
        data += bytes.fromhex(''.join(hexpart))
    return [int.from_bytes(data[i:i + 4], 'little') for i in range(0, len(data) - 3, 4)]


def handler_roots(words, calls, start, callbacks=()):
    """The functions to check: every vector table entry (without the stack pointer and the reset handler), the
    functions named like handlers, the callbacks. Returns (roots, notes)."""
    roots, notes = [], []
    for i, w in enumerate(words[2:], 2):
        f = start.get(w & ~1)
        if w and f is None:
            notes.append(f'note   vector {i} (0x{w:08x}) is not the start of a function')
        elif f and f not in roots:
            roots.append(f)
    reset = start.get(words[1] & ~1) if len(words) > 1 else None
    for f in sorted(calls):
        if HANDLER_NAME.fullmatch(f) and f not in roots and f not in ('Reset_Handler', reset):
            roots.append(f)
    roots += [f for f in callbacks if f not in roots]
    return roots, notes


def walk(root, calls, indirect):
    """Breadth-first from root: (hits, lazies, indirect call count). Each hit or lazy is the path that reaches it."""
    prev, q, hits, lazies, ind = {root: None}, deque([root]), [], [], 0

    def path(n):
        p = []
        while n:
            p.append(n)
            n = prev[n]
        return ' -> '.join(reversed(p))
    while q:
        f = q.popleft()
        ind += indirect.get(f, 0)
        for g in sorted(calls.get(f, ())):
            if g in prev or throw_helper(g):
                continue
            prev[g] = f
            if g in ALLOC:
                hits.append(('ALLOC', path(g)))
            elif BOX.search(g):
                hits.append(('BOX', path(g)))
            elif lazy(g):
                lazies.append(path(g))
            else:
                q.append(g)
    return hits, lazies, ind


def analyse(disasm, vectors, callbacks=(), boxing=False):
    """The report: (lines, number of failures, number of handlers). Raises ValueError when there is nothing to
    check."""
    calls, indirect, start = parse_disassembly(disasm)
    if not calls:
        raise ValueError('no functions in the disassembly')
    unknown = [c for c in callbacks if c not in calls]
    if unknown:
        raise ValueError('no such function: ' + ', '.join(unknown))
    roots, lines = handler_roots(vector_words(vectors), calls, start, callbacks)
    if not roots:
        raise ValueError('no interrupt handler found (no vector table, no function named like a handler)')
    bad = 0
    for root in roots:
        hits, lazies, ind = walk(root, calls, indirect)
        for kind, p in hits:
            lines.append(f'{kind:6s} {root}: {p}')
        lines += [f'LAZY   {root}: {p}' for p in lazies]
        if ind:
            lines.append(f'note   {root}: {ind} indirect call site(s) not followed: not proven clean')
        bad += len(hits)
    lines.append(f'{len(roots)} interrupt handler(s) checked: '
                 + ('no path to an allocation' if not bad else f'{bad} path(s) to an allocation'))
    if boxing:          # boxing anywhere in the program's own code, handler or not
        boxes = sorted((f, g) for f, gs in calls.items() for g in gs if BOX.search(g)
                       and not f.startswith('kfun:kotlin'))
        lines += [f'BOX    {f[:90]} -> {g}' for f, g in boxes]
        lines.append(f'--boxing: {len(boxes)} boxing call(s) outside the standard library')
        bad += len(boxes)
    return lines, bad, len(roots)


def objdump(elf, *args):
    """objdump ARGS ELF, run in the ELF's folder: on Windows binutils open files through the ANSI code page, so they
    cannot reach a folder named in Japanese."""
    r = subprocess.run([str(paths.gcc_bin('objdump').resolve()), *args, elf.name], cwd=elf.parent,
                       capture_output=True, text=True, errors='replace')
    if r.returncode != 0:
        print(f'isr_check: objdump {" ".join(args)} {elf} failed: {r.stderr.strip()[-500:]}', file=sys.stderr)
        sys.exit(2)
    return r.stdout


def main():
    ap = argparse.ArgumentParser(usage='python tools/isr_check.py firmware.elf [--callback NAME ...] [--boxing]',
                                 description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('elf', type=Path, help=argparse.SUPPRESS)
    ap.add_argument('--callback', action='append', default=[], help=argparse.SUPPRESS)
    ap.add_argument('--boxing', action='store_true', help=argparse.SUPPRESS)
    args = ap.parse_args()
    if not args.elf.is_file():
        print(f'isr_check: no such file: {args.elf}', file=sys.stderr)
        sys.exit(2)
    disasm = objdump(args.elf, '-d', '--no-show-raw-insn')
    sections = objdump(args.elf, '-h')
    vectors = objdump(args.elf, '-s', '-j', '.isr_vector') if re.search(r'\s\.isr_vector\s', sections) else ''
    try:
        lines, bad, _ = analyse(disasm, vectors, args.callback, args.boxing)
    except ValueError as e:
        print(f'isr_check: {args.elf}: {e}', file=sys.stderr)
        sys.exit(2)
    print('\n'.join(lines))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()

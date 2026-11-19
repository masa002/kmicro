#!/usr/bin/env python3
# Copyright 2026 the kmicro authors (NOTICE).
# SPDX-License-Identifier: Apache-2.0
"""Static check of a firmware image: no interrupt handler can reach a Kotlin allocation.

    python tools/isr_check.py firmware.elf [--vectors SECTION] [--handlers SECTION] [--callback NAME ...] [--boxing]

    --vectors   the section that holds the vector table of a Cortex-M, when the linker script does not call it
                .isr_vector (.vectors, .intvec, .vector_table ...). A section that goes on with code (.text, with
                the table at its start) is read up to its first function
    --handlers  the section that holds a table of handler addresses and nothing else, when it is not called
                .irq_handlers
    --callback  a function handlers reach only through a pointer (a callback registered with a driver): C functions
                by name, Kotlin ones by their mangled name, e.g. 'kfun:app#onTimer(){}' (an alias is no label)
    --boxing    also list every call outside the standard library that boxes an Int, Long, Short or Byte, in any
                code (an unsigned == / != or a generic container of a primitive), and fail on them. kbuild keeps the
                box functions out of line, so the call is there to find

The handlers are the entries of the vector table (.isr_vector, without the initial stack pointer and the reset
handler), whatever their names: under LTO the C name kbuild --c-api gives a Kotlin handler (SysTick_Handler) is
folded into the Kotlin function, so only the table still shows it. A Cortex-A or Cortex-R core has no such table:
its IRQ vector is one instruction, and the board's interrupt entry finds the handler. Where that entry calls the
handlers through a table of their addresses in a section of its own (.irq_handlers), every entry of that table is a
handler too. Functions named like handlers (C names ending in _Handler or _IRQHandler, Kotlin functions ending in
Handler) are checked as well, for handlers installed at run time. An image with neither section is checked by those
names alone, and the report says so: a handler that only a table shows was not looked at then.

Walks the machine code (arm-none-eabi-objdump -d) from every handler along direct calls and tail branches, and
reports each path that ends in the Kotlin allocator (AllocInstance, AllocArrayInstance and kmicro's allocation
functions) or in a boxing function. The heap is not reentrant, so a handler that allocates can corrupt it (kmicro
also stops at run time with "allocation inside an interrupt handler"). Paths through the throw helpers of the
runtime and the standard library (ThrowException, kfun:kotlin.native.internal#Throw...) are not followed: those only
run on a bug (an index out of bounds, a null), and the run-time guard covers them. The same holds for the exception
that a function of the standard library creates in its own body (digitToInt() of a character that is no digit,
nativeHeap's allocation when the native-memory arena is full): what a function does when it can do nothing more
than throw as the standard library does is left out. That is read from the branches of the machine code, so it holds
for a library function the link has inlined, and the standard library throws through a function of its own
(kmicro_library_throw, toolchain/retarget.py): a `throw` in the program's own code allocates and is reported.
Indirect calls (function pointers, virtual calls) cannot be followed here and are counted per handler: a handler
that has one is not proven clean. --callback names the functions such a call reaches.

Exit status: 0 when no handler reaches an allocation, 1 when one does (or --boxing finds a box), 2 when the image
cannot be read or has no handler.
"""
import argparse
import re
import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'toolchain'))
import binutils  # noqa: E402

ALLOC = {'AllocInstance', 'AllocArrayInstance', 'kmicro_alloc_object', 'kmicro_alloc_array', 'alloc_block'}
BOX = re.compile(r'<U?(Int|Byte|Short|Long)-box>')
HANDLER_NAME = re.compile(r'\w+_(IRQ)?Handler|kfun:[^#]*#\w*Handler\(\)\{\}')
# A transfer through a register or a loaded address: a call (blx r3), a tail call (bx r3, mov pc, r3) or a load into
# pc. A function's own return is not one: bx lr, mov pc, lr, pop {.., pc}, ldr pc, [sp], #4. Nor is the jump of a
# switch in ARM code, which loads pc from the table of addresses behind it, the entry chosen by a register:
# ldr pc, [r2, r1, lsl #2] (clang), ldrls pc, [pc, r3, lsl #2] (GCC). Thumb-2 code has tbb and tbh for that.
INDIRECT = re.compile(r'\t(?:blx\w*\s|bx\w*\s+(?!lr\b)|mov\w*\s+pc, (?!lr\b)'
                      r'|ldr\S*\s+pc, \[(?!sp\b)(?!\w+, \w+, lsl #2\]))')


def lazy(name):
    """Kotlin create-on-first-use points: a file's globals, an object or a companion. Safe in a handler only if
    the thread code used them first; kmicro stops at run time otherwise. Listed so each one can be checked."""
    return (name in ('CallInitGlobalPossiblyLock', 'kmicro_init_global')      # the second with Kotlin/Native 2.5
            or '<get-$companion>' in name or '<get-$instance>' in name)


def throw_helper(name):
    """The functions that exist only to throw: the runtime's C functions (ThrowException, ThrowNullPointerException)
    and the standard library's own helpers (kfun:kotlin.native.internal#ThrowNoWhenBranchMatchedException). A user
    function such as sendOrThrow is followed like any other."""
    return name.startswith('Throw') or (name.startswith(('kfun:kotlin.', 'kfun:kotlin#')) and
                                        name.split('#')[-1].startswith('Throw'))


# The standard library's own `throw`: toolchain/retarget.py makes every function of the standard library throw through
# this function, which is never inlined, so that the call is still there to find where the link inlined the library
# function into the program's code.
LIBRARY_THROW = 'kmicro_library_throw'
INSTRUCTION = re.compile(r'^\s*([0-9a-f]+):\t(\S+)[ \t]*([^\t]*)')      # address, mnemonic, operands (no comment)
TARGET = re.compile(r'(?:^|, )([0-9a-f]+) <(.+?)(\+0x[0-9a-f]+)?>\s*$')
CONDITION = '(eq|ne|cs|hs|cc|lo|mi|pl|vs|vc|hi|ls|ge|lt|gt|le|al)?(?:\\.[nw])?'
BRANCH = re.compile('(blx|bl|bx|b)' + CONDITION)                        # bls is b + ls, blls is bl + ls
NO_BRANCH = re.compile('(?:bics?|bfc|bfi|bkpt)' + CONDITION)            # the other mnemonics that start with b
# An instruction after which the function is left, or goes on where this tool cannot follow: a return (bx lr,
# pop {.., pc}, ldm with pc, mov pc, lr), a jump through a register or a table (bx r3, tbb, ldr pc), an exception
# return, a branch that names no target, and what is no instruction (.word, udf, the dump of data in the code).
WAY_OUT = re.compile(r'(?:b|tb[bh]|eret|rfe|udf|[^a-z])|\S+\tpc\b|(?:pop|ldm)\S*\t.*\bpc\}')


def library_throw_only(code):
    """The instructions of one function, [(address, mnemonic, operands)], after which the function can do nothing
    more than throw as the standard library does, as a set of indices: a call of LIBRARY_THROW can be reached from
    them, and no way out of the function can, nor a `throw` of the program's own code (ThrowException). A throw
    helper ends a path as LIBRARY_THROW does. An instruction that is not known here counts as a way out, so that a
    mistake reports a path too many."""
    at = {address: i for i, (address, _, _) in enumerate(code)}
    before = [[] for _ in code]                 # the instructions that can run directly before each one
    throws, out = set(), set()
    for i, (_, mnemonic, operands) in enumerate(code):
        b, t = BRANCH.fullmatch(mnemonic), TARGET.search(operands)
        callee = t.group(2) if t and not t.group(3) else None       # the start of a function
        thrower = callee == LIBRARY_THROW or bool(callee) and callee != 'ThrowException' and throw_helper(callee)
        jump, goes_on = None, True              # where a branch goes; whether the next instruction can follow
        if b and b.group(1) in ('bl', 'blx'):                       # a call; one through a register returns too
            goes_on = bool(b.group(2)) or not thrower
            way_out = callee == 'ThrowException'                    # the program's own throw
        elif t and (b and b.group(1) == 'b' or not mnemonic.startswith('b')):   # b, beq, cbz, le; or a tail call
            jump, goes_on = at.get(int(t.group(1), 16)), not b or bool(b.group(2))
            way_out = jump is None and not thrower
        else:
            way_out = not NO_BRANCH.fullmatch(mnemonic) and bool(WAY_OUT.match(mnemonic + '\t' + operands))
        if callee == LIBRARY_THROW:
            throws.add(i)
        if way_out or goes_on and i + 1 == len(code):               # what follows the function is not its code
            out.add(i)
        elif goes_on:
            before[i + 1].append(i)
        if jump is not None:
            before[jump].append(i)

    def reach(found):
        """The instructions from which one of `found` can be reached."""
        todo, found = list(found), set(found)
        while todo:
            for i in before[todo.pop()]:
                if i not in found:
                    found.add(i)
                    todo.append(i)
        return found
    return reach(throws) - reach(out) if throws else set()


def parse_disassembly(text):
    """objdump -d output -> (calls: function -> the functions it calls or tail-branches to, indirect: function ->
    number of indirect calls, start: address -> function). What a function does when it can only throw as the
    standard library does (library_throw_only) is in neither."""
    calls, indirect, start, cur, code = {}, {}, {}, None, []

    def edges():
        skip = library_throw_only([c[:3] for c in code])
        for line in (c[3] for i, c in enumerate(code) if i not in skip):
            # Kotlin names contain '<' and '>' (kotlin#<UInt-box>, <get-$companion>): take everything up to the
            # last '>' of the line, minus a +0x offset.
            # A call or tail call lands on a function's first instruction; a target inside another function
            # (+0x..) comes from padding or a literal pool decoded as an instruction, and is no edge.
            m = re.search(r'\t(b[a-z]*(?:\.[nw])?)\s+[0-9a-f]+ <(.+?)(\+0x[0-9a-f]+)?>\s*$', line)
            if m and m.group(3):
                m = None
            if m and m.group(2) != cur:
                calls[cur].add(m.group(2))
            elif INDIRECT.search(line):
                indirect[cur] += 1
        code.clear()
    for line in text.splitlines():
        m = re.match(r'^([0-9a-f]+) <(.+)>:$', line)
        if m:
            edges()
            cur = m.group(2)
            start.setdefault(int(m.group(1), 16), cur)
            calls.setdefault(cur, set())
            indirect.setdefault(cur, 0)
            continue
        m = INSTRUCTION.match(line) if cur is not None else None
        if m:
            code.append((int(m.group(1), 16), m.group(2), m.group(3), line))
    edges()
    return calls, indirect, start


def vector_words(text, start=()):
    """objdump -s -j SECTION output -> (the section's 32-bit words in order, None). start (address -> function): when
    a function starts inside the section, the table ends there: (the words before it, that function)."""
    data, base = bytearray(), None
    for line in text.splitlines():
        if not re.match(r'^ [0-9a-f]+ [0-9a-f]', line):
            continue
        hexpart = line[1:].split('  ')[0].split()      # address, up to 4 groups of bytes, then the ASCII
        base = int(hexpart[0], 16) if base is None else base
        data += bytes.fromhex(''.join(hexpart[1:]))
    words = [int.from_bytes(data[i:i + 4], 'little') for i in range(0, len(data) - 3, 4)]
    end = min((a for a in start if data and base < a < base + len(data)), default=None)
    return (words, None) if end is None else (words[:(end - base) // 4], start[end])


def handler_roots(words, calls, start, callbacks=(), table=()):
    """The functions to check: every vector table entry (without the stack pointer and the reset handler), every
    entry of a table of handlers, the functions named like handlers, the callbacks. Returns (roots, notes)."""
    roots, notes = [], []
    entries = [(f'vector {i}', w) for i, w in enumerate(words[2:], 2)]
    entries += [(f'handler table entry {i}', w) for i, w in enumerate(table)]
    for what, w in entries:
        f = start.get(w & ~1)
        if w and f is None:
            notes.append(f'note   {what} (0x{w:08x}) is not the start of a function')
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


def analyse(disasm, vectors, callbacks=(), boxing=False, section='.isr_vector', handlers=''):
    """The report: (lines, number of failures, number of handlers). vectors: the dump of the vector table's section,
    empty when the image has no section of that name; handlers: the same for a table of handler addresses. Raises
    ValueError when there is nothing to check."""
    calls, indirect, start = parse_disassembly(disasm)
    if not calls:
        raise ValueError('no functions in the disassembly')
    unknown = [c for c in callbacks if c not in calls]
    if unknown:
        raise ValueError('no such function: ' + ', '.join(unknown))
    (words, code), table = vector_words(vectors, start), vector_words(handlers)[0]
    roots, lines = handler_roots(words, calls, start, callbacks, table)
    if code:            # `.text : { KEEP(*(.isr_vector)) *(.text*) }`: the words after the table are no vectors
        lines.insert(0, f'note   the section {section} goes on with code: its first {len(words)} words, up to the '
                     f'function {code}, were read as the vector table')
    if not roots:
        raise ValueError('no interrupt handler found (no vector table, no function named like a handler)')
    if not words and not table:
        lines.append(f'note   no vector table: the image has no section {section}. Only the functions named like '
                     'handlers were checked; --vectors SECTION names the section that holds the table')
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
    """The output of objdump ARGS ELF."""
    r = binutils.run('objdump', elf, *args)
    if r.returncode != 0:
        print(f'isr_check: objdump {" ".join(args)} {elf} failed: {r.stderr.strip()[-500:]}', file=sys.stderr)
        sys.exit(2)
    return r.stdout


def main():
    ap = argparse.ArgumentParser(usage='python tools/isr_check.py firmware.elf [--vectors SECTION] '
                                 '[--handlers SECTION] [--callback NAME ...] [--boxing]',
                                 description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('elf', type=Path, help=argparse.SUPPRESS)
    ap.add_argument('--vectors', metavar='SECTION', help=argparse.SUPPRESS)
    ap.add_argument('--handlers', metavar='SECTION', help=argparse.SUPPRESS)
    ap.add_argument('--callback', action='append', default=[], help=argparse.SUPPRESS)
    ap.add_argument('--boxing', action='store_true', help=argparse.SUPPRESS)
    args = ap.parse_args()
    if not args.elf.is_file():
        print(f'isr_check: no such file: {args.elf}', file=sys.stderr)
        sys.exit(2)
    disasm = objdump(args.elf, '-d', '--no-show-raw-insn')
    sections = objdump(args.elf, '-h')
    section = args.vectors or '.isr_vector'
    found = re.search(rf'\s{re.escape(section)}\s', sections)
    if args.vectors and not found:                      # the default name may be absent, a name that was given may not
        print(f'isr_check: {args.elf}: no section {section} (--vectors); arm-none-eabi-objdump -h lists the sections',
              file=sys.stderr)
        sys.exit(2)
    vectors = objdump(args.elf, '-s', '-j', section) if found else ''
    table = args.handlers or '.irq_handlers'
    has_table = re.search(rf'\s{re.escape(table)}\s', sections)
    if args.handlers and not has_table:
        print(f'isr_check: {args.elf}: no section {table} (--handlers); arm-none-eabi-objdump -h lists the sections',
              file=sys.stderr)
        sys.exit(2)
    handlers = objdump(args.elf, '-s', '-j', table) if has_table else ''
    try:
        lines, bad, _ = analyse(disasm, vectors, args.callback, args.boxing, section, handlers)
    except ValueError as e:
        print(f'isr_check: {args.elf}: {e}', file=sys.stderr)
        sys.exit(2)
    print('\n'.join(lines))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()

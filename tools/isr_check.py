#!/usr/bin/env python3
"""Static check of a firmware image: no interrupt handler can reach a Kotlin allocation.

    python tools/isr_check.py firmware.elf [--callback NAME ...] [--boxing]

    --callback  a function handlers reach only through a pointer (a callback registered with a driver): C functions
                by name, Kotlin ones by their mangled name, e.g. 'kfun:app#onTimer(){}' (an alias is no label)
    --boxing    also list every call outside the standard library that boxes an Int, Long, Short or Byte, in any
                code (an unsigned == / != or a generic container of a primitive), and fail on them

Walks the machine code (arm-none-eabi-objdump -d) from every interrupt handler of the vector table along direct
calls and tail branches, and reports each path that ends in the Kotlin allocator (AllocInstance, AllocArrayInstance
and kmicro's allocation functions) or in a boxing function. The heap is not reentrant, so a handler that allocates
can corrupt it (kmicro also stops at run time with "allocation inside an interrupt handler"). Paths through Throw*
functions are not followed: those only run on a bug (an index out of bounds, a null), and the run-time guard covers
them.
Indirect calls (function pointers, virtual calls) cannot be followed here and are listed per handler.

Exit status: 0 when no handler reaches an allocation, 1 when one does (or --boxing finds a box).
"""
import re
import subprocess
import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'toolchain'))
import paths  # noqa: E402

ALLOC = {'AllocInstance', 'AllocArrayInstance', 'kmicro_alloc_object', 'kmicro_alloc_array', 'alloc_block'}
BOX = re.compile(r'<U?(Int|Byte|Short|Long)-box>')


def lazy(name):
    """Kotlin create-on-first-use points: a file's globals, an object or a companion. Safe in a handler only if
    the thread code used them first; kmicro stops at run time otherwise. Listed so each one can be checked."""
    return name == 'CallInitGlobalPossiblyLock' or '<get-$companion>' in name or '<get-$instance>' in name


def main():
    args = sys.argv[1:]
    boxing = '--boxing' in args
    args = [a for a in args if a != '--boxing']
    callbacks = set()
    while '--callback' in args:
        i = args.index('--callback')
        callbacks.add(args[i + 1])
        del args[i:i + 2]
    if not args:
        sys.exit(__doc__)
    elf = Path(args[0])
    text = subprocess.run([str(paths.gcc_bin('objdump')), '-d', '--no-show-raw-insn', str(elf)], capture_output=True, text=True,
                          errors='replace').stdout
    calls, indirect, cur = {}, {}, None
    for line in text.splitlines():
        m = re.match(r'^[0-9a-f]+ <(.+)>:$', line)
        if m:
            cur = m.group(1)
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
        elif re.search(r'\tblx\s+r\d+', line):
            indirect[cur] += 1
    # plus the functions handlers reach only through a pointer (--callback): a callback a driver calls from its
    # interrupt, for example
    roots = sorted(f for f in calls if (re.fullmatch(r'\w+_(IRQ)?Handler', f) and f != 'Reset_Handler') or
                   f in callbacks)
    bad = 0
    for root in roots:
        prev, seen, q, hits, ind, lazies = {root: None}, {root}, deque([root]), [], 0, []
        while q:
            f = q.popleft()
            ind += indirect.get(f, 0)
            for g in calls.get(f, ()):
                if g in seen or g.startswith('Throw') or 'Throw' in g.split('#')[-1][:12]:
                    continue
                seen.add(g)
                prev[g] = f
                if g in ALLOC or BOX.search(g):
                    hits.append(g)
                elif lazy(g):
                    lazies.append(g)
                else:
                    q.append(g)
        for h in hits:
            path, n = [], h
            while n:
                path.append(n)
                n = prev[n]
            print(f'{"BOX" if BOX.search(h) else "ALLOC":6s} {root}: ' + ' -> '.join(reversed(path)))
            bad += 1
        for h in lazies:
            path, n = [], h
            while n:
                path.append(n)
                n = prev[n]
            print(f'LAZY   {root}: ' + ' -> '.join(reversed(path)))
        if ind:
            print(f'note   {root}: {ind} indirect call site(s) not followed')
    print(f'{len(roots)} interrupt handler(s) checked: '
          + ('no path to an allocation' if not bad else f'{bad} path(s) to an allocation'))
    if boxing:          # boxing anywhere in the program's own code, handler or not
        boxes = sorted((f, g) for f, gs in calls.items() for g in gs if BOX.search(g)
                       and not f.startswith('kfun:kotlin'))
        for f, g in boxes:
            print(f'BOX    {f[:90]} -> {g}')
        print(f'--boxing: {len(boxes)} boxing call(s) outside the standard library')
        bad += len(boxes)
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()

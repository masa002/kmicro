"""Turn the addresses of a kmicro stack trace into Kotlin function names, using the firmware's ELF symbols.

usage: python tools/symbolize.py firmware.elf [log.txt]      (rewrites every "at 0x........" line; stdin without a file)
       python tools/symbolize.py firmware.elf 0x08007ac0 ...
Every trace address is a return address, so the name is looked up for the call instruction just before it: a throw
often ends a function with a call that never returns, and its return address is already the next function's first
instruction. The offset printed is the return address's. A "kmicro fault:" line is different: its address is the
faulting instruction itself (the stacked PC), so it is looked up as it is. Kotlin/Native symbol names are readable as
they are: kfun:<package>.<Class>#<name>(<params>){}<return type>.
When the ELF has debug line information, each frame is followed by the functions LTO inlined at that call, innermost
first, and the function that contains them, each with its file:line (arm-none-eabi-addr2line -i).
"""
import argparse
import bisect
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'toolchain'))
import binutils  # noqa: E402

HEX = re.compile(r'(0x)?[0-9a-fA-F]+')
AT = re.compile(r'at (0x[0-9a-fA-F]{8})')


def load(elf):
    r = binutils.run('nm', elf, '-n', '-S')
    if r.returncode != 0:
        sys.exit(f'symbolize: nm failed on {elf}: {r.stderr.strip()}')
    addrs, names = [], []
    for line in r.stdout.splitlines():
        p = line.split(maxsplit=3)
        if len(p) == 4 and p[2] in 'tTwW':
            addrs.append(int(p[0], 16) & ~1)
            names.append((p[3], int(p[1], 16)))
    if not addrs:
        sys.exit(f'symbolize: {elf} has no function symbols')
    return addrs, names


def name_of(addrs, names, a, exact=False):
    ret = a & ~1
    call = ret if exact else ret - 1                 # the faulting instruction, or inside the call instruction
    i = bisect.bisect_right(addrs, call) - 1
    if i < 0:
        return '?'
    n, size = names[i]
    pretty = n[5:] if n.startswith('kfun:') else n
    return f'{pretty}+0x{ret - addrs[i]:x}' if call - addrs[i] < max(size, 1) or size == 0 else f'? (after {pretty})'


def has_lines(elf):
    return '.debug_line' in binutils.run('readelf', elf, '-S', '-W').stdout


def source_lines(elf, trace, exact=False):
    """{return address: [(function, file:line), ...]} for the call before each address (with exact, for the
    instruction at it), innermost inlined function first. Only code built with -g has lines; other frames get none."""
    if not trace:
        return {}
    back = 0 if exact else 1
    calls = list(dict.fromkeys(f'0x{(a & ~1) - back:x}' for a in trace))
    r = binutils.run('addr2line', elf, '-a', '-f', '-i', '-s', '-e', after=calls)
    out, cur = {}, None
    lines = iter(r.stdout.splitlines())
    for line in lines:
        if line.startswith('0x'):
            cur = out.setdefault(int(line, 16) + back, [])
            continue
        loc = re.sub(r' \(discriminator \d+\)$', '', next(lines, '??:0'))
        if cur is not None and re.search(r':[1-9]\d*$', loc):   # code built without -g: no line, nothing to add
            cur.append((line[5:] if line.startswith('kfun:') else line, loc))
    return out


def detail(levels):
    last = len(levels) - 1
    return [f'        {fn} ({loc}){" [inlined]" if i < last else ""}\n' for i, (fn, loc) in enumerate(levels)]


def rewrite(lines, elf, addrs, names, out):
    dwarf = has_lines(elf)
    for line in lines:                               # line by line: a live log keeps flowing
        m = AT.search(line)
        if not m:
            out.write(line)
            continue
        a = int(m.group(1), 16)
        exact = 'kmicro fault:' in line              # the stacked PC, not a return address
        out.write(line.rstrip('\n') + f'  {name_of(addrs, names, a, exact)}\n')
        if dwarf:
            out.writelines(detail(source_lines(elf, [a], exact).get(a & ~1, [])))
        out.flush()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0],
                                 epilog='Without a log file or addresses, the log is read from stdin.')
    ap.add_argument('elf', help='the firmware ELF the log came from')
    ap.add_argument('inputs', nargs='*', default=[], metavar='log.txt | 0xADDRESS',
                    help='a log file to rewrite, or trace addresses to name')
    a = ap.parse_args()
    for s in (sys.stdin, sys.stdout):                # the log is UTF-8; Windows would use the ANSI code page
        s.reconfigure(encoding='utf-8', errors='replace')
    if not Path(a.elf).is_file():
        sys.exit(f'symbolize: no such ELF file: {a.elf}')
    files = [x for x in a.inputs if Path(x).is_file()]
    if files:
        if len(a.inputs) > 1:
            ap.error('give one log file, or addresses only')
        addrs, names = load(a.elf)
        with open(files[0], encoding='utf-8', errors='replace') as f:
            rewrite(f, a.elf, addrs, names, sys.stdout)
        return
    bad = [x for x in a.inputs if not HEX.fullmatch(x)]
    if bad:
        ap.error(f'not a hex address and no such file: {bad[0]}')
    addrs, names = load(a.elf)
    if a.inputs:
        trace = [int(x, 16) for x in a.inputs]
        src = source_lines(a.elf, trace) if has_lines(a.elf) else {}
        for x, t in zip(a.inputs, trace):
            print(f'{x}  {name_of(addrs, names, t)}')
            sys.stdout.writelines(detail(src.get(t & ~1, [])))
        return
    rewrite(sys.stdin, a.elf, addrs, names, sys.stdout)


if __name__ == '__main__':
    main()

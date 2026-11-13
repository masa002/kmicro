"""Turn the addresses of a kmicro stack trace into Kotlin function names, using the firmware's ELF symbols.

usage: python tools/symbolize.py firmware.elf [log.txt]      (rewrites every "at 0x........" line; stdin without a file)
       python tools/symbolize.py firmware.elf 0x08007ac0 ...
Every trace address is a return address, so the name is looked up for the call instruction just before it: a throw
often ends a function with a call that never returns, and its return address is already the next function's first
instruction. The offset printed is the return address's. Kotlin/Native symbol names are readable as they are:
kfun:<package>.<Class>#<name>(<params>){}<return type>.
"""
import argparse
import bisect
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'toolchain'))
import paths  # noqa: E402

NM = str(paths.gcc_bin('nm'))
HEX = re.compile(r'(0x)?[0-9a-fA-F]+')


def load(elf):
    r = subprocess.run([NM, '-n', '-S', elf], capture_output=True, text=True, errors='replace')
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


def name_of(addrs, names, a):
    ret = a & ~1
    call = ret - 1                                   # inside the call instruction
    i = bisect.bisect_right(addrs, call) - 1
    if i < 0:
        return '?'
    n, size = names[i]
    pretty = n[5:] if n.startswith('kfun:') else n
    return f'{pretty}+0x{ret - addrs[i]:x}' if call - addrs[i] < max(size, 1) or size == 0 else f'? (after {pretty})'


def rewrite(lines, addrs, names, out):
    for line in lines:
        m = re.search(r'at (0x[0-9a-fA-F]{8})', line)
        if m:
            line = line.rstrip('\n') + f'  {name_of(addrs, names, int(m.group(1), 16))}\n'
        out.write(line)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0],
                                 epilog='Without a log file or addresses, the log is read from stdin.')
    ap.add_argument('elf', help='the firmware ELF the log came from')
    ap.add_argument('inputs', nargs='*', default=[], metavar='log.txt | 0xADDRESS',
                    help='a log file to rewrite, or trace addresses to name')
    a = ap.parse_args()
    if not Path(a.elf).is_file():
        sys.exit(f'symbolize: no such ELF file: {a.elf}')
    files = [x for x in a.inputs if Path(x).is_file()]
    if files:
        if len(a.inputs) > 1:
            ap.error('give one log file, or addresses only')
        addrs, names = load(a.elf)
        with open(files[0], encoding='utf-8', errors='replace') as f:
            rewrite(f, addrs, names, sys.stdout)
        return
    bad = [x for x in a.inputs if not HEX.fullmatch(x)]
    if bad:
        ap.error(f'not a hex address and no such file: {bad[0]}')
    addrs, names = load(a.elf)
    if a.inputs:
        for x in a.inputs:
            print(f'{x}  {name_of(addrs, names, int(x, 16))}')
        return
    rewrite(sys.stdin, addrs, names, sys.stdout)


if __name__ == '__main__':
    main()

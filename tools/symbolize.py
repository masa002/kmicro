"""Turn the addresses of a kmicro stack trace into Kotlin function names, using the firmware's ELF symbols.

usage: python symbolize.py firmware.elf < log.txt      (rewrites every "at 0x........" line)
       python symbolize.py firmware.elf 0x08007ac0 ...
Kotlin/Native symbol names are readable as they are: kfun:<package>.<Class>#<name>(<params>){}<return type>.
"""
import bisect
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'toolchain'))
import paths  # noqa: E402

NM = str(paths.gcc_bin('nm'))


def load(elf):
    out = subprocess.run([NM, '-n', '-S', elf], capture_output=True, text=True, errors='replace').stdout
    addrs, names = [], []
    for line in out.splitlines():
        p = line.split(maxsplit=3)
        if len(p) == 4 and p[2] in 'tTwW':
            addrs.append(int(p[0], 16) & ~1)
            names.append((p[3], int(p[1], 16)))
    return addrs, names


def name_of(addrs, names, a):
    i = bisect.bisect_right(addrs, a & ~1) - 1
    if i < 0:
        return '?'
    n, size = names[i]
    off = (a & ~1) - addrs[i]
    pretty = n[5:] if n.startswith('kfun:') else n
    return f'{pretty}+0x{off:x}' if off < max(size, 1) or size == 0 else f'? (after {pretty})'


def main():
    addrs, names = load(sys.argv[1])
    if len(sys.argv) > 2:
        for a in sys.argv[2:]:
            print(f'{a}  {name_of(addrs, names, int(a, 16))}')
        return
    for line in sys.stdin:
        m = re.search(r'at (0x[0-9a-fA-F]{8})', line)
        if m:
            line = line.rstrip('\n') + f'  {name_of(addrs, names, int(m.group(1), 16))}\n'
        sys.stdout.write(line)


if __name__ == '__main__':
    main()

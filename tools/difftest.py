"""Differential test: the same Kotlin program on the official runtime (built for this computer) and on kmicro
(Cortex-M4, QEMU). The outputs must be byte-identical.

usage: python tools/difftest.py [NAME ...] [--cpu CORE] [--stress] [--size]

    NAME      a program in tests/diff (d_strings, d_collections ...). Default: every tests/diff/d_*.kt except the
              d_known_* ones, which show what kmicro does not support yet and run only when named
    --cpu     the core of the kmicro side (toolchain/paths.py CORES; default cortex-m4f); each core has its own
              build folder, build/diff-<core>
    --stress  the kmicro side collects garbage at every allocation (KM_GC_STRESS)
    --size    the kmicro side is built for size, as tools/kbuild.py --size does

The kmicro side is built the way tools/kbuild.py builds a program (toolchain/kn.py build(), with --single-core) and
linked by tools/qbuild.py with the runtime's default 16 KB heap. The host side is built by kotlinc-native for this
computer (mingw_x64, linux_x64, linux_arm64, macos_x64 or macos_arm64).

A program can declare, each on a comment line of its own:

    // difftest: heap BYTES -- reason     a bigger kmicro heap
    // difftest: large -- reason          allowed to exceed the STM32L431 (256 KB of flash, 64 KB of RAM): linked
                                          with qbuild --large
    // difftest: ulp N -- reason          numbers in the output may differ by N units in the last place

Each line of the report shows SAME, DIFF, OVER (same output, but the image does not fit the STM32L431) or ERROR (the
program could not be built or run), with the image size and the heap's peak and live bytes at the end of the run.
"""
import argparse
import difflib
import math
import platform
import re
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'toolchain'))
import kn  # noqa: E402
import paths  # noqa: E402
sys.path.insert(0, str(ROOT / 'tools'))
import qbuild  # noqa: E402

OUT = ROOT / 'build/diff'
DIFF = ROOT / 'tests/diff'
FLASH, RAM = 256 * 1024, 64 * 1024              # the STM32L431
STATS = re.compile(rb'kmicro-difftest: heap (\d+) peak (\d+) live (\d+)\n\Z')   # driver.c's last line
NUMBER = re.compile(r'-?(?:\d+(?:\.\d+)?(?:E-?\d+)?|Infinity)|NaN')
FLOAT_MAX = 3.4028234663852886e38               # Float.MAX_VALUE: a bigger number is a Double


class Failure(Exception):
    pass


def host_target():
    system, arm = platform.system(), platform.machine().lower() in ('arm64', 'aarch64')
    target = {'Windows': 'mingw_x64', 'Linux': 'linux_arm64' if arm else 'linux_x64',
              'Darwin': 'macos_arm64' if arm else 'macos_x64'}.get(system)
    if not target:
        sys.exit(f'difftest: no Kotlin/Native host target for {system} {platform.machine()}')
    return target


def directives(src):
    """The `// difftest: ...` lines of a program: {'heap': 32768, 'large': True, 'ulp': 2}."""
    d = {}
    for line in src.read_text(encoding='utf-8').splitlines():
        m = re.match(r'\s*//\s*difftest:\s*(\w+)\s*(\d*)', line)
        if m:
            if m.group(1) not in ('heap', 'large', 'ulp') or (m.group(1) == 'large') != (m.group(2) == ''):
                raise Failure(f'bad directive: {line.strip()}')
            d[m.group(1)] = int(m.group(2)) if m.group(2) else True
    return d


def kotlinc(args, where):
    """kotlinc-native with an argument file: UTF-8, every argument quoted (paths with spaces or non-ASCII letters)."""
    where.mkdir(parents=True, exist_ok=True)
    quoted = ['"' + str(a).replace('\\', '\\\\').replace('"', '\\"') + '"' for a in args]
    (where / 'args.txt').write_text('\n'.join(quoted) + '\n', encoding='utf-8')
    r = paths.run_kn('kotlinc-native', ['@' + (where / 'args.txt').as_posix()])
    if r.returncode != 0:
        raise Failure('kotlinc-native failed (host)\n' + (r.stdout + r.stderr)[-2000:])


def exit_code(rc):
    return f'0x{rc & 0xffffffff:08X}' if rc < 0 or rc > 255 else str(rc)


def host(name, src):
    d = OUT / 'host' / name
    exe = d / (name + ('.exe' if paths.WINDOWS else '.kexe'))   # what kotlinc-native -p program writes
    if not exe.exists() or exe.stat().st_mtime < src.stat().st_mtime:
        kotlinc([src.as_posix(), '-target', host_target(), '-p', 'program', '-opt', '-o', (d / name).as_posix()], d)
    r = subprocess.run([str(exe)], capture_output=True, timeout=300)  # the runtime writes UTF-8 bytes (::write)
    if r.returncode != 0:
        raise Failure(f'host program exited with {exit_code(r.returncode)} (the reference output would be cut '
                      f'short); its output ends with: {r.stdout[-200:].decode("utf-8", "replace")!r}')
    return r.stdout.replace(b'\r\n', b'\n')


def kmicro(name, src, opts, stress, size):
    d = OUT / 'kmicro' / (name + ('-size' if size else ''))
    objs = kn.build([src], d, size=size)
    if re.search(r'load atomic i32, ptr @"state_global', (d / 'm4.ll').read_text(encoding='utf-8')):
        raise Failure('m4.ll still checks file initialisation with atomic loads: not built with --single-core')
    elf = d / (name + ('-stress' if stress else '') + '.elf')
    defs = [*(['-D', f'KM_HEAP_BYTES={opts["heap"]}'] if 'heap' in opts else []),
            *(['-D', 'KM_GC_STRESS=1'] if stress else []), *(['--large'] if opts.get('large') else [])]
    r = subprocess.run([sys.executable, ROOT / 'tools/qbuild.py', elf, DIFF / 'driver.c', *objs, *defs],
                       capture_output=True, encoding='utf-8', errors='replace')
    if r.returncode != 0:
        raise Failure('qbuild failed\n' + (r.stdout + r.stderr)[-2000:])
    notes = [l for l in r.stdout.splitlines() if l.startswith('qbuild: warning')]
    m = re.search(r' text (\d+)\s+data (\d+)\s+bss (\d+)', r.stdout)
    text, data, bss = map(int, m.groups())
    timeout = 3000 if stress else 300                # stress collects before every allocation: legitimately slow
    try:
        # in the image's folder, with its bare name: on Windows QEMU opens files through the ANSI code page
        machine = qbuild.TARGETS[qbuild.DEFAULT_TARGET.get(paths.cpu(), 'l475')][2]
        q = subprocess.run([str(paths.qemu_system_arm().resolve()), '-machine', machine, '-nographic',
                            '-semihosting-config', 'enable=on,target=native', '-kernel', elf.name, '-serial', 'none',
                            '-monitor', 'none'], capture_output=True, timeout=timeout, cwd=elf.parent)
    except subprocess.TimeoutExpired:
        raise Failure(f'QEMU timed out after {timeout} s') from None
    out = q.stderr.replace(b'\r\n', b'\n')           # QEMU writes semihosting output to stderr
    stats = STATS.search(out)
    if stats:
        out = out[:stats.start()]
    return out, q.returncode, notes, (text + data, data + bss), stats and tuple(map(int, stats.groups()))


def significant_digits(token):
    mantissa = re.sub(r'E.*|[-.]', '', token).strip('0')
    return len(mantissa)


def float_ulp(x):
    bits = struct.unpack('<I', struct.pack('<f', abs(x)))[0]
    lo, hi = (struct.unpack('<f', struct.pack('<I', b))[0] for b in (bits, bits + 1))
    return hi - lo


def close(golden, got, ulps):
    """Equal text, and numbers at most `ulps` units in the last place apart: of a Float when both are printed with at
    most 9 significant digits, of a Double otherwise."""
    a, b = golden.decode('utf-8', 'replace'), got.decode('utf-8', 'replace')
    if NUMBER.split(a) != NUMBER.split(b):
        return False
    for x, y in zip(NUMBER.findall(a), NUMBER.findall(b)):
        if x == y:
            continue
        fx, fy = float(x), float(y)
        if not (math.isfinite(fx) and math.isfinite(fy)):
            return False
        short = significant_digits(x) <= 9 and significant_digits(y) <= 9 and abs(fx) <= FLOAT_MAX
        if abs(fx - fy) > ulps * (float_ulp(fx) if short else math.ulp(fx)):
            return False
    return True


def kb(n):
    return f'{n / 1024:.1f} KB'


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    ap = argparse.ArgumentParser(usage='python tools/difftest.py [NAME ...] [--cpu CORE] [--stress] [--size]', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('names', nargs='*', help=argparse.SUPPRESS)
    ap.add_argument('--cpu', choices=sorted(paths.CORES), help=argparse.SUPPRESS)
    ap.add_argument('--stress', action='store_true', help=argparse.SUPPRESS)
    ap.add_argument('--size', action='store_true', help=argparse.SUPPRESS)
    args = ap.parse_args()
    global OUT
    if paths.select_cpu(args.cpu) != paths.DEFAULT_CPU:
        OUT = ROOT / f'build/diff-{paths.cpu()}'
    available = sorted(p.stem for p in DIFF.glob('d_*.kt'))
    unknown = [n for n in args.names if n not in available]
    if unknown:
        ap.error(f'no such program: {", ".join(unknown)} (tests/diff has: {" ".join(available)})')
    names = args.names or [n for n in available if not n.startswith('d_known_')]
    bad = 0
    for name in names:
        src = DIFF / (name + '.kt')
        try:
            opts = directives(src)
            golden = host(name, src)
            got, rc, notes, (flash, ram), stats = kmicro(name, src, opts, args.stress, args.size)
        except (Exception, SystemExit) as e:          # noqa: BLE001 - kn.py stops with SystemExit; report, go on
            first, *rest = str(e).strip().splitlines() or ['']
            print(f'ERROR {name}: {first}')
            for line in rest[-12:]:
                print('      ' + line)
            bad += 1
            continue
        same = rc == 0 and (got == golden or 'ulp' in opts and close(golden, got, opts['ulp']))
        fits = flash <= FLASH and ram <= RAM
        status = 'DIFF' if not same else 'SAME' if fits or opts.get('large') else 'OVER'
        heap = f'  heap {stats[0]}: peak {stats[1]} live {stats[2]}' if stats else ''
        exact = '' if got == golden or not same else f'  (within {opts["ulp"]} ulp)'
        lines = golden.count(b'\n')
        print(f'{status:5s} {name}  ({len(golden)} bytes, {lines} lines, qemu exit {rc})'
              f'  flash {kb(flash)}  RAM {kb(ram)}{heap}{exact}')
        for n in notes:
            print('      ' + n)
        if status == 'OVER':
            print('      the image does not fit the STM32L431 (256 KB flash, 64 KB RAM): shrink it, or say '
                  '`// difftest: large -- reason` in the program')
        if status != 'SAME':
            bad += 1
        if not same:
            for line in list(difflib.unified_diff(golden.decode('utf-8', 'replace').splitlines(),
                                                  got.decode('utf-8', 'replace').splitlines(),
                                                  'official runtime (host)', 'kmicro (Cortex-M4)', lineterm='',
                                                  n=0))[:30]:
                print('      ' + line)
        (OUT / f'{name}.golden.txt').write_bytes(golden)
        (OUT / f'{name}.kmicro.txt').write_bytes(got)
    print(f'{len(names) - bad} same, {bad} different')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()

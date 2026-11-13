"""Differential test: the same Kotlin program on the official runtime (built for this computer) and on kmicro
(Cortex-M4, QEMU). The outputs must be byte-identical.

usage: python tools/difftest.py [NAME ...] [--stress]

    NAME      a program in tests/diff (d_strings, d_collections ...). Default: every tests/diff/d_*.kt
    --stress  the kmicro side collects garbage at every allocation (KM_GC_STRESS)

The host side is built by kotlinc-native for this computer (mingw_x64, linux_x64, linux_arm64, macos_x64 or
macos_arm64). Each line of the report shows SAME, DIFF or ERROR (the program could not be built or run).
"""
import argparse
import difflib
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'toolchain'))
import kn  # noqa: E402
import paths  # noqa: E402

OUT = ROOT / 'build/diff'
DIFF = ROOT / 'tests/diff'


class Failure(Exception):
    pass


def host_target():
    system, arm = platform.system(), platform.machine().lower() in ('arm64', 'aarch64')
    target = {'Windows': 'mingw_x64', 'Linux': 'linux_arm64' if arm else 'linux_x64',
              'Darwin': 'macos_arm64' if arm else 'macos_x64'}.get(system)
    if not target:
        sys.exit(f'difftest: no Kotlin/Native host target for {system} {platform.machine()}')
    return target


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
    exe = d / (name + paths.EXE)
    if not exe.exists() or exe.stat().st_mtime < src.stat().st_mtime:
        kotlinc([src.as_posix(), '-target', host_target(), '-p', 'program', '-opt', '-o', (d / name).as_posix()], d)
    r = subprocess.run([str(exe)], capture_output=True, timeout=300)  # the runtime writes UTF-8 bytes (::write)
    if r.returncode != 0:
        raise Failure(f'host program exited with {exit_code(r.returncode)} (the reference output would be cut '
                      f'short); its output ends with: {r.stdout[-200:].decode("utf-8", "replace")!r}')
    return r.stdout.replace(b'\r\n', b'\n')


def kmicro(name, src, stress):
    d = OUT / 'kmicro' / name
    kn.compile_ir([src], d)
    kn.lto_object(kn.retarget(d / 'ir/out.Codegen.ll', d / 'm4.ll', '--no-tls'), d / 'k.o')
    elf = d / (name + '.elf')
    r = subprocess.run([sys.executable, ROOT / 'tools/qbuild.py', elf, DIFF / 'driver.c', d / 'k.o', '-D',
                        'KM_HEAP_BYTES=65536', *(['-D', 'KM_GC_STRESS=1'] if stress else [])],
                       capture_output=True, text=True, errors='replace')
    if r.returncode != 0:
        raise Failure('qbuild failed\n' + (r.stdout + r.stderr)[-2000:])
    notes = [l for l in r.stdout.splitlines() if l.startswith('qbuild: warning')]
    timeout = 3000 if stress else 300                # stress collects before every allocation: legitimately slow
    try:
        q = subprocess.run([str(paths.qemu_system_arm()), '-machine', 'b-l475e-iot01a', '-nographic',
                            '-semihosting-config', 'enable=on,target=native', '-kernel', str(elf), '-serial', 'none',
                            '-monitor', 'none'], capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise Failure(f'QEMU timed out after {timeout} s') from None
    return q.stderr.replace(b'\r\n', b'\n'), q.returncode, notes   # QEMU writes semihosting output to stderr


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    ap = argparse.ArgumentParser(usage='python tools/difftest.py [NAME ...] [--stress]', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('names', nargs='*', help=argparse.SUPPRESS)
    ap.add_argument('--stress', action='store_true', help=argparse.SUPPRESS)
    args = ap.parse_args()
    available = sorted(p.stem for p in DIFF.glob('d_*.kt'))
    unknown = [n for n in args.names if n not in available]
    if unknown:
        ap.error(f'no such program: {", ".join(unknown)} (tests/diff has: {" ".join(available)})')
    names = args.names or available
    bad = 0
    for name in names:
        src = DIFF / (name + '.kt')
        try:
            golden = host(name, src)
            got, rc, notes = kmicro(name, src, args.stress)
        except (Exception, SystemExit) as e:          # noqa: BLE001 - kn.py stops with SystemExit; report, go on
            first, *rest = str(e).strip().splitlines() or ['']
            print(f'ERROR {name}: {first}')
            for line in rest[-12:]:
                print('      ' + line)
            bad += 1
            continue
        same = got == golden and rc == 0
        lines = golden.count(b'\n')
        print(f'{"SAME" if same else "DIFF"}  {name}  ({len(golden)} bytes, {lines} lines, qemu exit {rc})')
        for n in notes:
            print('      ' + n)
        if not same:
            bad += 1
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

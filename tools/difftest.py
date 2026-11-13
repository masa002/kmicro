"""Differential test: the same Kotlin program on the official runtime (host, mingw_x64) and on kmicro (Cortex-M4,
QEMU). The outputs must be byte-identical.

usage: python tools/difftest.py [name ...]       (names: d_strings d_collections ...; default: all tests/diff/*.kt)
"""
import difflib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'toolchain'))
import kn  # noqa: E402
import paths  # noqa: E402

OUT = ROOT / 'build/diff'
STRESS = '--stress' in sys.argv


def kotlinc(args, where):
    where.mkdir(parents=True, exist_ok=True)
    (where / 'args.txt').write_text('\n'.join(args) + '\n')
    r = paths.run_kn('kotlinc-native', ['@' + (where / 'args.txt').as_posix()])
    if r.returncode != 0:
        raise RuntimeError('kotlinc failed: ' + (r.stdout + r.stderr)[-2000:])


def host(name, src):
    d = OUT / 'host' / name
    exe = d / (name + paths.EXE)
    if not exe.exists() or exe.stat().st_mtime < src.stat().st_mtime:
        kotlinc([src.as_posix(), '-target', 'mingw_x64' if paths.WINDOWS else 'linux_x64', '-p', 'program', '-opt', '-o', (d / name).as_posix()], d)
    r = subprocess.run([str(exe)], capture_output=True, timeout=120)   # the runtime writes UTF-8 bytes (::write)
    return r.stdout.replace(b'\r\n', b'\n')


def kmicro(name, src):
    d = OUT / 'kmicro' / name
    kn.compile_ir([src], d)
    kn.lto_object(kn.retarget(d / 'ir/out.Codegen.ll', d / 'm4.ll', '--no-tls'), d / 'k.o')
    elf = d / (name + '.elf')
    stress = ['-D', 'KM_GC_STRESS=1'] if STRESS else []
    r = subprocess.run([sys.executable, ROOT / 'tools/qbuild.py', elf, ROOT / 'tests/diff/driver.c', d / 'k.o', '-D',
                        'KM_HEAP_BYTES=65536', *stress], capture_output=True, text=True, errors='replace')
    if r.returncode != 0:
        raise RuntimeError('qbuild failed: ' + (r.stdout + r.stderr)[-2000:])
    stubbed = [l for l in r.stdout.splitlines() if 'stubbed' in l]
    q = subprocess.run([str(paths.qemu_system_arm()), '-machine', 'b-l475e-iot01a', '-nographic', '-semihosting-config',
                        'enable=on,target=native', '-kernel', str(elf), '-serial', 'none', '-monitor', 'none'],
                       capture_output=True, timeout=3000)
    return q.stderr.replace(b'\r\n', b'\n'), q.returncode, stubbed   # QEMU writes semihosting output to stderr


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    names = [a for a in sys.argv[1:] if not a.startswith('--')] or sorted(p.stem for p in (ROOT / 'tests/diff').glob('d_*.kt'))
    bad = 0
    for name in names:
        src = ROOT / 'tests/diff' / (name + '.kt')
        try:
            golden = host(name, src)
            got, rc, stubbed = kmicro(name, src)
        except Exception as e:                       # noqa: BLE001
            print(f'ERROR {name}: {e}')
            bad += 1
            continue
        same = got == golden and rc == 0
        nlines = golden.count(b'\n')
        print(f'{"SAME" if same else "DIFF"}  {name}  ({len(golden)} bytes, {nlines} lines, qemu exit {rc})')
        for s in stubbed:
            print('      ' + s)
        if not same:
            bad += 1
            for l in list(difflib.unified_diff(golden.decode('utf-8', 'replace').splitlines(),
                                               got.decode('utf-8', 'replace').splitlines(), 'official runtime (host)',
                                               'kmicro (Cortex-M4)', lineterm='', n=0))[:30]:
                print('      ' + l)
        (OUT / f'{name}.golden.txt').write_bytes(golden)
        (OUT / f'{name}.kmicro.txt').write_bytes(got)
    print(f'{len(names) - bad} same, {bad} different')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()

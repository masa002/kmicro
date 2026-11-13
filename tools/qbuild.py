"""Build a QEMU test image: Kotlin LTO object(s) + the kmicro runtime + a C main, for the emulated STM32L475
(QEMU machine b-l475e-iot01a, targets/qemu-l475).

usage: python tools/qbuild.py <out.elf> <main.c> <k.o>... [-D NAME=VALUE ...] [--run]

Runtime symbols the program needs but kmicro does not implement yet become stubs that print their name and stop
(autostubs.c), so a test run tells exactly which piece is missing.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'toolchain'))
import paths  # noqa: E402

TARGET = ROOT / 'targets/qemu-l475'
# -g costs no flash. It lets Kotlin code built with debug information keep its line info when LTO inlines it into C.
CFLAGS = [*paths.TARGET_M4F, '-isystem', str(paths.newlib_include()), '-O2', '-g', '-flto', '-ffunction-sections',
          '-fdata-sections', '-fexceptions', '-funwind-tables', '-Wall', '-Wextra', '-Wno-unused-parameter',
          '-I', str(ROOT / 'runtime')]


def run(args, check=True):
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.exit(f'FAILED: {" ".join(map(str, args))[:400]}\n{r.stdout[-2000:]}{r.stderr[-4000:]}')
    return r


def runtime_sources():
    rt = ROOT / 'runtime'
    return [*sorted(rt.glob('*.c')), *sorted(rt.glob('*.cpp')), *sorted((rt / 'dtoa').glob('*.cpp'))]


def main():
    argv = sys.argv[1:]
    do_run = '--run' in argv
    argv = [a for a in argv if a != '--run']
    defs = []
    while '-D' in argv:
        i = argv.index('-D')
        defs.append('-D' + argv[i + 1])
        del argv[i:i + 2]
    out, main_c, kobjs = Path(argv[0]), Path(argv[1]), [Path(p) for p in argv[2:]]
    bdir = out.parent / (out.stem + '.obj')
    bdir.mkdir(parents=True, exist_ok=True)
    objs = []
    for s in [TARGET / 'start.c', main_c, *runtime_sources()]:
        o = bdir / (s.stem + '.o')
        lang = ['-std=c++17', '-fno-rtti', '-Wno-unused-variable', '-Wno-unused-but-set-variable'] if s.suffix == '.cpp' else []
        run([paths.clang(), *CFLAGS, *lang, *defs, '-c', s, '-o', o])
        objs.append(o)
    stubs = bdir / 'autostubs.c'
    stubs.write_text('')
    link = [paths.ld_lld(), '-T', TARGET / 'l475.ld', '--gc-sections', '--lto-O2', '-o', out, *objs, *kobjs,
            bdir / 'autostubs.o', f'-L{paths.newlib_lib()}', '-lc_nano', '-lm', '-lnosys', paths.libgcc()]
    for attempt in range(3):
        run([paths.clang(), *CFLAGS, '-w', '-c', stubs, '-o', bdir / 'autostubs.o'])
        r = run(link, check=False)
        if r.returncode == 0:
            break
        missing = sorted(set(re.findall(r'undefined symbol: (\S+)', r.stderr)))
        if not missing or attempt == 2:
            sys.exit(f'link failed:\n{r.stderr[-4000:]}')
        body = ['#include "kmicro.h"']
        for m in missing:
            body.append(f'void {m}(void) {{ kmicro_panic("unimplemented runtime symbol: {m}"); }}')
        stubs.write_text('\n'.join(body) + '\n')
        print(f'qbuild: {len(missing)} runtime symbols stubbed: {" ".join(missing)}')
    size = run([paths.gcc_bin('size'), out]).stdout.strip().splitlines()[-1].split()
    print(f'qbuild: {out.name}  text {size[0]}  data {size[1]}  bss {size[2]}')
    if do_run:
        r = subprocess.run([str(paths.qemu_system_arm()), '-machine', 'b-l475e-iot01a', '-nographic',
                            '-semihosting-config', 'enable=on,target=native', '-kernel',
                            paths.arg_path(out, ascii=True), '-serial', 'none', '-monitor', 'none'],
                           capture_output=True, timeout=120)
        sys.stdout.buffer.write(r.stdout)
        sys.stdout.buffer.write(r.stderr)
        sys.stdout.flush()
        print(f'qemu: exit {r.returncode}')
        sys.exit(r.returncode)


if __name__ == '__main__':
    main()

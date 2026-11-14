"""Build the selftest for an STM32L431 board: build/stm32l431/selftest.elf, .hex and .bin.

usage: python examples/selftest/stm32l431/build.py [--kotlin]

The Kotlin side is built as for the emulator (tools/kbuild.py with ../selftest.h). board.c takes the place of
../main.c and of the QEMU start code, stm32l431.ld the place of the QEMU linker script. --kotlin recompiles the
Kotlin code even when the saved IR is current.

Write the .hex or .bin to the board at 0x08000000 with the tool you use for it, open a terminal on USART1 (PA9 is
TX) at 115200 8N1 and reset the board: it prints one line per check with its time, then the heap statistics.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXAMPLE = HERE.parent
ROOT = EXAMPLE.parent.parent
sys.path.insert(0, str(ROOT / 'toolchain'))
import binutils  # noqa: E402
import paths  # noqa: E402

OUT = ROOT / 'build/stm32l431'
paths.select_cpu('cortex-m4f')                   # this board's core
CFLAGS = [*paths.target_flags(), '-isystem', str(paths.newlib_include()), '-O2', '-flto', '-ffunction-sections',
          '-fdata-sections', '-fexceptions', '-funwind-tables', '-Wall', '-Wextra', '-Wno-unused-parameter',
          '-I', str(ROOT / 'runtime'), '-I', str(EXAMPLE)]
CXXFLAGS = ['-std=c++17', '-fno-rtti', '-Wno-unused-variable', '-Wno-unused-but-set-variable']


def run(args):
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True, errors='replace')
    if r.returncode != 0:
        sys.exit(f'FAILED: {" ".join(map(str, args))[:400]}\n{r.stdout[-3000:]}{r.stderr[-4000:]}')
    return r


def kotlin(force):
    """selftest.kt -> the objects tools/kbuild.py prints (k.o, and bridges.o if the code called C)."""
    r = run([sys.executable, ROOT / 'tools/kbuild.py', OUT / 'kotlin', EXAMPLE / 'selftest.kt',
             '--c-api', EXAMPLE / 'selftest.h', '--package', 'selftest', *(['--kotlin'] if force else [])])
    return [Path(line.strip()) for line in r.stdout.splitlines() if line.strip().endswith('.o')]


def c_objects():
    rt = ROOT / 'runtime'
    sources = [HERE / 'board.c', *sorted(rt.glob('*.c')), *sorted(rt.glob('*.cpp')), *sorted((rt / 'dtoa').glob('*.cpp'))]
    (OUT / 'obj').mkdir(parents=True, exist_ok=True)
    objs = []
    for s in sources:
        o = OUT / 'obj' / (s.stem + '.o')
        run([paths.clang(), *CFLAGS, *(CXXFLAGS if s.suffix == '.cpp' else []), '-c', s, '-o', o])
        objs.append(o)
    return objs


def main():
    if set(sys.argv[1:]) - {'--kotlin'}:
        sys.exit(__doc__)
    objs = kotlin('--kotlin' in sys.argv) + c_objects()
    elf = OUT / 'selftest.elf'
    run([paths.ld_lld(), '-T', HERE / 'stm32l431.ld', '--gc-sections', '--lto-O2', '-Map', OUT / 'selftest.map',
         '-o', elf, *objs, f'-L{paths.newlib_lib()}', '-lc_nano', '-lm', '-lnosys', paths.libgcc()])
    binutils.output('objcopy', elf, '-O', 'ihex', after=['selftest.hex'])
    binutils.output('objcopy', elf, '-O', 'binary', after=['selftest.bin'])
    text, data, bss = binutils.output('size', elf).strip().splitlines()[-1].split()[:3]
    print(f'selftest.elf: flash {int(text) + int(data)} B of 256 KB, RAM {int(data) + int(bss)} B of 64 KB '
          f'(the rest is stack)')
    print(OUT / 'selftest.hex')


if __name__ == '__main__':
    main()

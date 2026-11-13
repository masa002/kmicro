"""Kotlin sources -> Cortex-M4 objects to link with the kmicro runtime (toolchain/kn.py build()).

usage: python tools/kbuild.py <outdir> <file.kt>... [-l lib.klib]... [--c-api header.h]... [--package NAME]
                              [--init-all NAME] [--size [--hot REGEX]] [--kotlin]

    -l          a klib the sources use (cinterop output)
    --c-api     a C header whose prototypes the Kotlin code implements: `int32_t gc_chains(int32_t)` becomes a C name
                for the Kotlin function <package>.gcChains (needs --package)
    --init-all  generate `void NAME(void)`, which initialises every file-level global of <package>: call it at boot,
                before interrupts are enabled, and no interrupt handler ever runs a first-use initialisation
    --size      minsize for all Kotlin code; --hot keeps full speed for the functions whose symbol matches REGEX
    --kotlin    recompile even when the saved IR is newer than every source

Prints the objects: <outdir>/k.o, plus <outdir>/bridges.o when the program calls C through cinterop. Link them with
runtime/*.c, runtime/*.cpp, runtime/dtoa/*.cpp and your C code; tools/qbuild.py does that for the QEMU target.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'toolchain'))
import kn  # noqa: E402


def main():
    argv, opts, lists = sys.argv[1:], {}, {'-l': [], '--c-api': []}
    for flag in ('--package', '--hot', '--init-all'):
        if flag in argv:
            i = argv.index(flag)
            opts[flag] = argv[i + 1]
            del argv[i:i + 2]
    for flag in lists:
        while flag in argv:
            i = argv.index(flag)
            lists[flag].append(Path(argv[i + 1]))
            del argv[i:i + 2]
    flags = {a for a in argv if a.startswith('--')}
    argv = [a for a in argv if not a.startswith('--')]
    if len(argv) < 2 or flags - {'--size', '--kotlin'}:
        sys.exit(__doc__)
    objs = kn.build([Path(s) for s in argv[1:]], Path(argv[0]), libs=lists['-l'], c_api=lists['--c-api'],
                    package=opts.get('--package'), init_all=opts.get('--init-all'), size='--size' in flags,
                    hot=opts.get('--hot'), force='--kotlin' in flags)
    print('\n'.join(str(o) for o in objs))


if __name__ == '__main__':
    main()

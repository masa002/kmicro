"""Kotlin sources -> Cortex-M4 objects to link with the kmicro runtime (toolchain/kn.py build()).

usage: python tools/kbuild.py <outdir> <file.kt or folder>... [options]      (--help lists the options)

Prints the objects: <outdir>/k.o, plus <outdir>/bridges.o when the program calls C through cinterop. Link them with
runtime/*.c, runtime/*.cpp, runtime/dtoa/*.cpp and your C code; tools/qbuild.py does that for the QEMU target.
Compiler warnings and progress go to stderr.

A program with a `fun main()` needs no C code of its own: link targets/common/kotlin_main.c, which calls it.
    python tools/kbuild.py build/app app.kt
    python tools/qbuild.py build/app/app.elf targets/common/kotlin_main.c build/app/k.o --run
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'toolchain'))
import kn  # noqa: E402

VALUE_OPTIONS = ('--kotlinc',)            # their value starts with '-': `--kotlinc -ea` is read as `--kotlinc=-ea`


class Parser(argparse.ArgumentParser):
    def error(self, message):                  # one line, without the usage block (--help shows it)
        self.exit(2, f'{self.prog}: error: {message}\n')


def parser():
    p = Parser(prog='kbuild.py', description=__doc__.split('\n\n')[0], allow_abbrev=False,
               formatter_class=argparse.RawDescriptionHelpFormatter,
               epilog='Examples:\n'
                      '  python tools/kbuild.py build/app app.kt           (fun main(): run it with '
                      'targets/common/kotlin_main.c)\n'
                      '  python tools/kbuild.py build/app app.kt --c-api app.h --package app')
    p.add_argument('outdir', type=Path, help='build folder (k.o, the saved IR, ...)')
    p.add_argument('sources', nargs='+', type=Path, metavar='source', help='Kotlin file, or a folder of .kt files')
    p.add_argument('-l', dest='libs', action='append', default=[], type=Path, metavar='LIB.klib',
                   help='a klib the sources use (cinterop output); repeatable')
    p.add_argument('--c-api', action='append', default=[], type=Path, metavar='HEADER.h',
                   help='a C header whose prototypes the Kotlin code implements: `int32_t gc_chains(int32_t)` becomes '
                        'a C name for the Kotlin function <package>.gcChains (needs --package); repeatable')
    p.add_argument('-I', dest='include_dirs', action='append', default=[], type=Path, metavar='DIR',
                   help='a folder the C headers include from (for --c-api); repeatable')
    p.add_argument('--package', metavar='NAME', help='the Kotlin package of the --c-api and --init-all functions')
    p.add_argument('--init-all', metavar='NAME',
                   help='generate `void NAME(void)`, which initialises the globals of --package and its sub-packages '
                        '(file-level ones and those of objects); call it at boot, before interrupts are enabled, and '
                        'no interrupt handler runs a first-use initialisation of that code (the standard library '
                        'still initialises its own objects on first use)')
    p.add_argument('--size', action='store_true', help='optimise all Kotlin code for size (minsize)')
    p.add_argument('--hot', metavar='REGEX', help='with --size: keep full speed for the functions whose symbol '
                                                  'matches REGEX')
    p.add_argument('--kotlinc', dest='kotlinc_args', action='append', default=[], metavar='ARG',
                   help='pass ARG to kotlinc-native, e.g. --kotlinc -Xbinary=latin1Strings=true or --kotlinc '
                        '-opt-in=kotlin.ExperimentalUnsignedTypes; repeatable')
    p.add_argument('--main', action='store_true',
                   help='require a `fun main()` (an error when there is none); one is found without this flag too '
                        'and gets the C name kmicro_kotlin_main, which targets/common/kotlin_main.c calls')
    p.add_argument('--kotlin', dest='force', action='store_true',
                   help='recompile even when the saved IR is current')
    return p


def parse(argv):
    joined, i = [], 0
    while i < len(argv):
        if argv[i] in VALUE_OPTIONS and i + 1 < len(argv):
            joined.append(f'{argv[i]}={argv[i + 1]}')
            i += 2
        else:
            joined.append(argv[i])
            i += 1
    p = parser()
    args, rest = p.parse_known_intermixed_args(joined)
    for r in rest:
        if r.startswith('--'):
            p.error(f'unknown option {r}')
        if r.startswith('-'):
            p.error(f'unknown option {r} (a kotlinc-native option goes through --kotlinc: --kotlinc {r})')
        p.error(f'unexpected argument {r}')
    if args.hot and not args.size:
        p.error('--hot needs --size (it chooses the functions that --size leaves at full speed)')
    if (args.c_api or args.init_all) and args.package is None:
        p.error('--c-api and --init-all need --package (the Kotlin package that implements them)')
    for flag, files in (('-l', args.libs), ('--c-api', args.c_api), ('-I', args.include_dirs)):
        for f in files:
            if not f.exists():
                p.error(f'{flag} {f}: not found')
    for s in args.sources:
        if not s.exists():
            p.error(f'{s}: not found')
    return args


def main():
    a = parse(sys.argv[1:])
    objs = kn.build(a.sources, a.outdir, libs=a.libs, c_api=a.c_api, package=a.package, init_all=a.init_all,
                    size=a.size, hot=a.hot, force=a.force, kotlinc_args=a.kotlinc_args, include_dirs=a.include_dirs,
                    main=True if a.main else None)
    print('\n'.join(str(o) for o in objs))


if __name__ == '__main__':
    main()

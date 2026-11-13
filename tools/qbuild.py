"""Build a QEMU test image: Kotlin LTO object(s) + the kmicro runtime + a C main, for the emulated STM32L475
(QEMU machine b-l475e-iot01a, targets/qemu-l475).

usage: python tools/qbuild.py <out.elf> <main.c> <k.o>... [-D NAME=VALUE ...] [--run]

A symbol nothing defines fails the link with the file that needs it. The one exception is a Kotlin runtime native
(Kotlin_*, Konan_*, Throw*, ...) that a Kotlin object calls and kmicro does not implement yet: it becomes a stub that
stops the program with 'kmicro panic: unimplemented runtime symbol: NAME' (autostubs.s), and qbuild prints a warning
naming it, because a board link without qbuild fails on it.
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
# The names Kotlin code calls the runtime by: the natives of the standard library and the compiler's entry points.
# Only these are stubbed when missing, and only when a Kotlin object calls them.
RUNTIME_NAME = re.compile(r'(Kotlin_|Konan_|Throw[A-Z]|_ZN6kotlin|__cxa_)\w*$|(getCached|in)[A-Za-z]+Box(Cache)?$')


def run(args, check=True):
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.exit(f'FAILED: {" ".join(map(str, args))[:400]}\n{r.stdout[-2000:]}{r.stderr[-4000:]}')
    return r


def runtime_sources():
    rt = ROOT / 'runtime'
    return [*sorted(rt.glob('*.c')), *sorted(rt.glob('*.cpp')), *sorted((rt / 'dtoa').glob('*.cpp'))]


def bridge_source(name):
    """The Kotlin file a cinterop bridge belongs to: its name is the hex of '<uuid><path of the .kt file>'."""
    m = re.match(r'_([0-9a-f]+)_\d+_kn', name)
    try:
        return re.sub(r'^[0-9a-f-]{36}', '', bytes.fromhex(m.group(1)).decode('utf-8'))
    except (AttributeError, ValueError):
        return '?'


def missing_symbols(link, stderr, labels, kotlin):
    """Sort the undefined symbols of a failed link: (runtime natives to stub, error lines). ld.lld's own report
    names only the LTO output, so the link runs again with --trace-symbol to find the input that needs each one."""
    missing = sorted(set(re.findall(r'undefined symbol: (.+?)\s*$', stderr, re.M)))
    traced = run([*link, *[f'--trace-symbol={m}' for m in missing]], check=False).stdout
    refs = {m: [] for m in missing}
    for line in traced.splitlines():                # '<input file>: reference to <symbol>'
        f, sep, sym = line.partition(': reference to ')
        if sep and sym in refs and f in labels and labels[f] not in refs[sym]:
            refs[sym].append(labels[f])
    stubs, errors, bridges = [], [], set()
    for m in missing:
        by = f' (referenced by {", ".join(refs[m])})' if refs[m] else ''
        if '_knbridge' in m or '_kncfun' in m:
            bridges.add(bridge_source(m))
        elif m.startswith('kfun:'):
            errors.append(f'Kotlin function not found: {m}{by}')
        elif RUNTIME_NAME.match(m) and any(r in kotlin for r in refs[m]):
            stubs.append(m)
        else:
            errors.append(f'undefined symbol: {m}{by}')
    for b in sorted(bridges):
        errors.append(f'the cinterop bridges of {b} are missing: link the bridges.o that kbuild printed next to k.o')
    return stubs, errors


def write_stubs(path, names):
    """Each name: a function that panics with its name. Assembly, so no optimiser sees a signature it could
    disagree with (LTO deletes the paths that call a C stub with another prototype), and any spelling assembles."""
    text = ['\t.syntax unified', '\t.thumb', '\t.section .text.kmicro_autostubs,"ax",%progbits']
    for i, n in enumerate(names):
        q = '"' + n + '"'
        text += ['\t.p2align 1', f'\t.globl {q}', f'\t.type {q}, %function', '\t.thumb_func', f'{q}:',
                 f'\tldr r0, =.Lkm_autostub{i}', '\tb.w kmicro_panic', '\t.ltorg']
    text.append('\t.section .rodata.kmicro_autostubs,"a",%progbits')
    for i, n in enumerate(names):
        text += [f'.Lkm_autostub{i}:', f'\t.asciz "unimplemented runtime symbol: {n}"']
    path.write_text('\n'.join(text) + '\n', encoding='utf-8')


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
    objs, labels = [], {}                         # labels: link input -> the name used in messages
    for s in [TARGET / 'start.c', main_c, *runtime_sources()]:
        o = bdir / (s.stem + '.o')
        lang = ['-std=c++17', '-fno-rtti', '-Wno-unused-variable', '-Wno-unused-but-set-variable'] if s.suffix == '.cpp' else []
        run([paths.clang(), *CFLAGS, *lang, *defs, '-c', s, '-o', o])
        objs.append(o)
        labels[str(o)] = str(s)
    kotlin = {str(k) for k in kobjs}
    labels.update((k, k) for k in kotlin)
    stubs_s, stubs_o = bdir / 'autostubs.s', bdir / 'autostubs.o'
    link = [paths.ld_lld(), '-T', TARGET / 'l475.ld', '--gc-sections', '--lto-O2', '--no-demangle', '--error-limit=0',
            '-o', out, *objs, *kobjs, f'-L{paths.newlib_lib()}', '-lc_nano', '-lm', '-lnosys', paths.libgcc()]
    stubbed = []
    for _ in range(3):
        r = run([*link, *([stubs_o] if stubbed else [])], check=False)
        if r.returncode == 0:
            break
        new, errors = missing_symbols([*link, *([stubs_o] if stubbed else [])], r.stderr, labels, kotlin)
        if errors:
            sys.exit('qbuild: link failed\n' + '\n'.join('  ' + e for e in errors))
        if not new:
            sys.exit(f'link failed:\n{r.stderr[-4000:]}')
        stubbed = sorted({*stubbed, *new})
        write_stubs(stubs_s, stubbed)
        run([paths.clang(), *paths.TARGET_M4F, '-c', stubs_s, '-o', stubs_o])
    else:
        sys.exit(f'link failed:\n{r.stderr[-4000:]}')
    if stubbed:
        print(f'qbuild: warning: {len(stubbed)} runtime symbols stubbed (kmicro does not implement them: a call stops '
              f'the program with "unimplemented runtime symbol", and a board link fails): {" ".join(stubbed)}')
    size = run([paths.gcc_bin('size'), out]).stdout.strip().splitlines()[-1].split()
    print(f'qbuild: {out.name}  text {size[0]}  data {size[1]}  bss {size[2]}')
    if do_run:
        r = subprocess.run([str(paths.qemu_system_arm()), '-machine', 'b-l475e-iot01a', '-nographic',
                            '-semihosting-config', 'enable=on,target=native', '-kernel', out.name, '-serial', 'none',
                            '-monitor', 'none'], capture_output=True, timeout=120,
                           cwd=out.parent)             # QEMU opens a non-ASCII path wrongly on Windows
        sys.stdout.buffer.write(r.stdout)
        sys.stdout.buffer.write(r.stderr)
        sys.stdout.flush()
        print(f'qemu: exit {r.returncode}')
        sys.exit(r.returncode)


if __name__ == '__main__':
    main()

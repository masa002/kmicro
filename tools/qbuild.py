# Copyright 2026 the kmicro authors (NOTICE).
# SPDX-License-Identifier: Apache-2.0
"""Build a QEMU test image: Kotlin LTO object(s) + the kmicro runtime + C code, for an emulated Cortex-M or
Cortex-A.

usage: python tools/qbuild.py OUT.elf FILE... [-D NAME=VALUE]... [-I DIR]... [--cpu CORE] [--target NAME] [--large]
                              [--run] [--icount] [--timeout SECONDS]

    FILE       C (.c), C++ (.cpp) and assembly (.s, .S) files, compiled with the runtime's flags, and objects (.o, .a)
               linked as they are: the k.o (and bridges.o) that tools/kbuild.py prints. Several C files are fine, e.g.
               main.c support/hw.c
    -D, -I     a definition or include folder for every C file, e.g. -D KM_HEAP_BYTES=32768 (runtime/, support/
               and the target's folder, for its tick.h, are always on the include path)
    --cpu      the core to compile for (toolchain/paths.py CORES; default cortex-m4f, or KMICRO_CPU). The objects
               from kbuild must be built for the same core, and the target must be one that runs its code:
               qbuild stops when it is not
    --target   l475: QEMU b-l475e-iot01a, an STM32L475 (targets/qemu-l475), the layout programs run on; its
               Cortex-M4F also runs the code of the cores below it (cortex-m0 to cortex-m4). The default for those
               an386: QEMU mps2-an386 (targets/qemu-an386: 4 MB of code, 16 MB of RAM, newlib stdio over
               semihosting), for tests that need more memory than a microcontroller has
               an385, an500: the start code and the layout of l475 on QEMU mps2-an385 (a Cortex-M3; the default for
               cortex-m3) and mps2-an500 (a Cortex-M7 with a double-precision FPU; the default for cortex-m7 and
               cortex-m7-sp)
               an505: the same on QEMU mps2-an505, a Cortex-M33 with an FPU (the default for cortex-m33, cortex-m33f
               and cortex-m23, whose ARMv8-M Baseline code it runs too). The program runs in the Secure state, in
               which that core starts
               an547: the same on QEMU mps3-an547, a Cortex-M55 with an FPU and MVE, in the Secure state too (the
               default for the cortex-m55 and cortex-m85 cores: QEMU has no Cortex-M85). It runs the code of the
               three ARMv8-M cores as well. QEMU gives this machine 2 GB of memory, which a Windows host commits when
               the machine starts
               virt: QEMU virt with a Cortex-A7 (targets/qemu-virt), the default for cortex-a7 and the only
               machine for it. The image is loaded into the machine's RAM and gets the same amounts of it
               an536: QEMU mps3-an536, a Cortex-R52 (targets/qemu-an536), the default for cortex-r52 and the
               only machine for it, with the image in its RAM in the same way
    --large    l475, an385, an500, an505, an547, virt and an536 give a program the memory of the STM32L431 kmicro
               aims at, 256 KB of flash and 64 KB of RAM: one that does not fit fails to link, and the stack ends
               where it would end on that chip. With --large the program gets the memory of the STM32L475: 1 MB of
               flash and 96 KB of RAM
    --run      run the image on QEMU and exit with the program's exit code (124 when it runs out of time)
    --icount   with --run: QEMU's clock is the number of instructions the program has run, one nanosecond each
               (-icount shift=0,sleep=off), not the host's clock. A timer interrupt then lands on the same
               instruction in every run and on every host, and a wait for one (WFI) takes no time
    --timeout  seconds a --run may take (default 120)

The runtime is compiled once per set of -D values (build/qbuild/) and recompiled when one of its files changes.

A symbol nothing defines fails the link with the file that needs it. The one exception is a Kotlin runtime native
(Kotlin_*, Konan_*, Throw*, ...) that a Kotlin object calls and kmicro does not implement yet: it becomes a stub that
stops the program with 'kmicro panic: unimplemented runtime symbol: NAME' (autostubs.s), and qbuild prints a warning
naming it, because a board link without qbuild fails on it.
"""
import argparse
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'toolchain'))
import paths  # noqa: E402

TARGETS = {   # start code and linker script, QEMU machine (and its -cpu, where it has several), the newlib
              # system-call library
    'l475': (ROOT / 'targets/qemu-l475', 'l475.ld', 'b-l475e-iot01a', ['-lnosys']),
    'an386': (ROOT / 'targets/qemu-an386', 'an386.ld', 'mps2-an386', ['-lrdimon_nano', '--wrap=_exit']),
    'an385': (ROOT / 'targets/qemu-l475', 'mps2.ld', 'mps2-an385', ['-lnosys']),
    'an500': (ROOT / 'targets/qemu-l475', 'mps2.ld', 'mps2-an500', ['-lnosys']),
    'an505': (ROOT / 'targets/qemu-l475', 'an505.ld', 'mps2-an505', ['-lnosys']),
    'an547': (ROOT / 'targets/qemu-l475', 'an547.ld', 'mps3-an547', ['-lnosys']),
    'virt': (ROOT / 'targets/qemu-virt', 'virt.ld', 'virt -cpu cortex-a7', ['-lnosys']),
    'an536': (ROOT / 'targets/qemu-an536', 'an536.ld', 'mps3-an536', ['-lnosys']),
}
# The machine a core's programs run on when --target is not given: its own where QEMU has one with this start code,
# else the STM32L475, whose Cortex-M4F runs the code of every core below it. QEMU has no Cortex-M23: its code, ARMv8-M
# Baseline, runs on the Cortex-M33. It has no Cortex-M85 either: its code runs on the Cortex-M55, which has every
# instruction of that core but those of PACBTI, and kmicro builds none of them (paths.py).
_A7 = ('cortex-a5', 'cortex-a7', 'cortex-a7-nofp', 'cortex-a8', 'cortex-a9', 'cortex-a15')
_M55 = ('cortex-m55', 'cortex-m55-nomve', 'cortex-m55-nofp', 'cortex-m85', 'cortex-m85-nomve', 'cortex-m85-nofp')
DEFAULT_TARGET = {'cortex-m3': 'an385', 'cortex-m7': 'an500', 'cortex-m7-sp': 'an500', 'cortex-m23': 'an505',
                  'cortex-m33': 'an505', 'cortex-m33f': 'an505', **dict.fromkeys(_M55, 'an547'),
                  **dict.fromkeys(_A7, 'virt'), 'cortex-r52': 'an536',
                  'cortex-r5': 'an536', 'cortex-r5f': 'an536'}
# The cores whose code each machine runs. A machine does not run code for an FPU or for instructions its core lacks.
# And the start code is compiled for the core: its stack and null guards are written for the MPU of ARMv8-M or for the
# one of the older cores, and on a machine with the other MPU the program runs with no guard at all.
_M3 = ('cortex-m0', 'cortex-m0plus', 'cortex-m1', 'cortex-m3')
_M4F = (*_M3, 'cortex-m4', 'cortex-m4f')
_M33F = ('cortex-m23', 'cortex-m33', 'cortex-m33f')
RUNS = {'l475': _M4F, 'an386': _M4F, 'an385': _M3, 'an500': (*_M4F, 'cortex-m7', 'cortex-m7-sp'), 'an505': _M33F,
        'an547': (*_M33F, *_M55), 'virt': _A7,
        'an536': ('cortex-r52', 'cortex-r5', 'cortex-r5f')}


def qemu_machine(target):
    """QEMU's options that choose the target's machine."""
    return ['-machine', *TARGETS[target][2].split()]


def cflags():
    """The flags of every C file. -g costs no flash: it lets Kotlin code built with debug information keep its line
    info when LTO inlines it into C."""
    return [*paths.target_flags(), '-isystem', str(paths.newlib_include()), '-O2', '-g', '-flto',
            '-ffunction-sections', '-fdata-sections', '-fexceptions', '-funwind-tables', '-Wall', '-Wextra',
            '-Wno-unused-parameter', '-Wno-atomic-alignment', '-I', str(ROOT / 'runtime'), '-I', str(ROOT / 'support')]


CXXFLAGS = ['-std=c++17', '-fno-rtti', '-Wno-unused-variable', '-Wno-unused-but-set-variable']
C_SOURCES = ('.c', '.cpp', '.s', '.S')
NO_ROOM = ('qbuild: the program does not fit the STM32L431 (256 KB of flash, 64 KB of RAM); --large links it for the '
           'memory of the STM32L475 (1 MB, 96 KB)')
# The names Kotlin code calls the runtime by: the natives of the standard library and the compiler's entry points.
# Only these are stubbed when missing, and only when a Kotlin object calls them.
RUNTIME_NAME = re.compile(r'(Kotlin_|Konan_|Throw[A-Z]|_ZN6kotlin|__cxa_)\w*$|(getCached|in)[A-Za-z]+Box(Cache)?$')


def fail(msg):
    sys.stdout.flush()
    sys.exit(msg)


def run(args, check=True, cwd=None):
    try:
        r = subprocess.run([str(a) for a in args], capture_output=True, encoding='utf-8', errors='replace', cwd=cwd)
    except FileNotFoundError:
        fail(f'qbuild: cannot run {args[0]} (see python toolchain/paths.py)')
    if check and r.returncode != 0:
        fail(f'FAILED: {" ".join(map(str, args))[:400]}\n{r.stdout[-2000:]}{r.stderr[-4000:]}')
    return r


def compile_one(src, obj, flags):
    """src -> obj, shown warnings and all. Written under a temporary name first: an interrupted or concurrent build
    never leaves a half-written object behind."""
    if src.suffix in ('.s', '.S'):
        cmd = [paths.clang(), *paths.target_flags(), *(flags if src.suffix == '.S' else []), '-c', src]
    else:
        cmd = [paths.clang(), *cflags(), *(CXXFLAGS if src.suffix == '.cpp' else []), *flags, '-c', src]
    obj.parent.mkdir(parents=True, exist_ok=True)
    tmp = obj.with_name(f'{obj.name}.{os.getpid()}.tmp')
    r = run([*cmd, '-o', tmp])
    if r.stderr.strip():
        print(r.stderr.rstrip(), flush=True)
    try:
        os.replace(tmp, obj)
    except PermissionError:                       # another qbuild just wrote the same cached object
        tmp.unlink()


def runtime_objects(defs):
    """runtime/ compiled with these -D values, cached in build/qbuild/runtime-<hash of the flags>/."""
    rt = ROOT / 'runtime'
    sources = [*sorted(rt.glob('*.c')), *sorted(rt.glob('*.cpp')), *sorted((rt / 'dtoa').glob('*.cpp'))]
    headers = max(p.stat().st_mtime for p in [*rt.rglob('*.h'), *rt.rglob('*.hpp'), Path(__file__)])
    key = hashlib.sha1('\n'.join([str(paths.clang()), *cflags(), *defs]).encode()).hexdigest()[:12]
    cache = ROOT / 'build/qbuild' / f'runtime-{key}'
    objs = []
    for s in sources:
        o = cache / (s.relative_to(rt).as_posix().replace('/', '_') + '.o')
        if not o.exists() or o.stat().st_mtime < max(s.stat().st_mtime, headers):
            compile_one(s, o, defs)
        objs.append(o)
    return objs


def built_for(obj):
    """The core kbuild built the object for (it leaves core.txt next to k.o and bridges.o); None when nothing says."""
    try:
        core = (obj.parent / 'core.txt').read_text(encoding='utf-8').strip()
    except OSError:
        return None
    return core if core in paths.CORES else None


def object_name(bdir, src):
    """One object per source path: main.c and a runtime file of the same name never overwrite each other."""
    return bdir / f'{src.stem}-{hashlib.sha1(str(src.resolve()).encode()).hexdigest()[:8]}.o'


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
    if not missing:
        return [], []
    traced = run([*link, *[f'--trace-symbol={m}' for m in missing]], check=False).stdout
    refs = {m: [] for m in missing}
    for line in traced.splitlines():                # '<input file>: reference to <symbol>'
        f, sep, sym = line.partition(': reference to ')
        if f not in labels:                         # 'lib.a(member.o)': the archive given on the command line
            f = re.sub(r'\([^()]*\)$', '', f)
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
    disagree with (LTO deletes the paths that call a C stub with another prototype), and any spelling assembles.
    The branch is a `bl`, which every core has (ARMv6-M has no `b.w`); kmicro_panic does not return."""
    text = ['\t.syntax unified', '\t.thumb', '\t.section .text.kmicro_autostubs,"ax",%progbits']
    for i, n in enumerate(names):
        q = '"' + n + '"'
        text += ['\t.p2align 1', f'\t.globl {q}', f'\t.type {q}, %function', '\t.thumb_func', f'{q}:',
                 f'\tldr r0, =.Lkm_autostub{i}', '\tbl kmicro_panic', '\t.ltorg']
    text.append('\t.section .rodata.kmicro_autostubs,"a",%progbits')
    for i, n in enumerate(names):
        text += [f'.Lkm_autostub{i}:', f'\t.asciz "unimplemented runtime symbol: {n}"']
    path.write_text('\n'.join(text) + '\n', encoding='utf-8')


def size_line(out):
    """The size line, with the stack: the RAM between the end of .bss and the top of the stack. A target with a
    stack guard (qemu-l475: _eguard) has the guard and the unused bytes around it in between; they are counted
    neither as bss nor as stack, so bss is what the program takes and the stack what it can use. On Windows binutils
    and QEMU open files through the ANSI code page, so a folder named in Japanese is out of their reach: they run in
    the image's folder and get its bare name."""
    here = dict(cwd=out.parent)
    t, d, b = run([paths.gcc_bin('size').resolve(), out.name], **here).stdout.strip().splitlines()[-1].split()[:3]
    syms = {}
    for line in run([paths.gcc_bin('nm').resolve(), out.name], **here).stdout.splitlines():
        p = line.split()
        if len(p) == 3 and p[2] in ('_estack', '_ebss', '_eguard'):
            syms[p[2]] = int(p[0], 16)
    if '_estack' not in syms or '_ebss' not in syms:
        return f'qbuild: {out.name}  text {t}  data {d}  bss {b}'
    guard = syms.get('_eguard', syms['_ebss']) - syms['_ebss']
    stack = syms['_estack'] - syms['_ebss'] - guard
    return f'qbuild: {out.name}  text {t}  data {d}  bss {int(b) - guard}  stack {stack}'


def parse_args():
    head, usage, *rest = __doc__.split('\n\n')
    ap = argparse.ArgumentParser(usage=usage.split('usage: ', 1)[1], description='\n\n'.join([head, *rest]),
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    hide = argparse.SUPPRESS                      # the description explains every option
    ap.add_argument('out', type=Path, help=hide)
    ap.add_argument('files', type=Path, nargs='+', help=hide)
    ap.add_argument('-D', dest='defs', action='append', default=[], help=hide)
    ap.add_argument('-I', dest='incs', action='append', default=[], help=hide)
    ap.add_argument('--cpu', choices=sorted(paths.CORES), help=hide)
    ap.add_argument('--target', choices=sorted(TARGETS), help=hide)
    ap.add_argument('--large', action='store_true', help=hide)
    ap.add_argument('--run', action='store_true', help=hide)
    ap.add_argument('--icount', action='store_true', help=hide)
    ap.add_argument('--timeout', type=float, default=120, help=hide)
    return ap.parse_intermixed_args()


def main():
    for stream in (sys.stdout, sys.stderr):      # UTF-8, as the program's own output: any file name prints
        stream.reconfigure(encoding='utf-8', errors='replace')
    args = parse_args()
    for f in args.files:
        if not f.is_file():
            fail(f'qbuild: no such file: {f}')
        if f.suffix not in (*C_SOURCES, '.o', '.a'):
            fail(f'qbuild: {f}: expected .c, .cpp, .s, .S, .o or .a')
    cpu = paths.select_cpu(args.cpu)
    for f in args.files:                          # before anything is compiled: the mistake costs no build
        if f.suffix in ('.o', '.a') and built_for(f) not in (None, cpu):
            fail(f'qbuild: {f} was built for {built_for(f)}, and this link is for {cpu}. Give kbuild and qbuild the '
                 'same core (--cpu or KMICRO_CPU)')
    target = args.target or DEFAULT_TARGET.get(cpu, 'l475')
    tdir, script, machine, syslibs = TARGETS[target]
    if cpu not in RUNS[target]:
        fail(f'qbuild: --target {target} (QEMU {machine}) does not run {cpu} code: it runs ' + ', '.join(RUNS[target])
             + f'. Without --target, {cpu} runs on {DEFAULT_TARGET.get(cpu, "l475")}')
    defs = [f'-D{d}' for d in args.defs]
    incs = [*[f'-I{i}' for i in args.incs], f'-I{tdir}']
    out = args.out
    bdir = out.parent / (out.stem + '.obj')
    bdir.mkdir(parents=True, exist_ok=True)

    labels, objs, kotlin = {}, [], set()          # labels: link input -> the name used in messages
    for src in [tdir / 'start.c', *[f for f in args.files if f.suffix in C_SOURCES]]:
        o = object_name(bdir, src)
        compile_one(src, o, [*defs, *incs])
        objs.append(o)
        labels[str(o)] = str(src)
    rt = runtime_objects(defs)
    labels.update((str(o), 'runtime/' + o.stem.replace('dtoa_', 'dtoa/')) for o in rt)
    given = [f for f in args.files if f.suffix in ('.o', '.a')]
    for f in given:
        labels[str(f)] = str(f)
        kotlin.add(str(f))
    stubs_s, stubs_o = bdir / 'autostubs.s', bdir / 'autostubs.o'
    link = [paths.ld_lld(), '-T', tdir / script, '--gc-sections', '--lto-O2', '--target2=abs', '--no-demangle',
            '--error-limit=0', '-o', out, *objs, *rt, *given, f'-L{paths.newlib_lib()}', '-lc_nano', '-lm',
            *syslibs, paths.libgcc(), *(['--defsym=kmicro_large=1'] if args.large else [])]
    stubbed = []
    for _ in range(3):
        r = run([*link, *([stubs_o] if stubbed else [])], check=False)
        if r.returncode == 0:
            break
        new, errors = missing_symbols([*link, *([stubs_o] if stubbed else [])], r.stderr, labels, kotlin)
        if errors:
            fail('qbuild: link failed\n' + '\n'.join('  ' + e for e in errors))
        if not new:
            no_room = 'will not fit in region' in r.stderr and script != 'an386.ld' and not args.large
            fail(f'qbuild: link failed\n{r.stderr[-4000:]}' + (NO_ROOM if no_room else ''))
        stubbed = sorted({*stubbed, *new})
        write_stubs(stubs_s, stubbed)
        compile_one(stubs_s, stubs_o, [])
    else:
        fail(f'qbuild: link failed\n{r.stderr[-4000:]}')
    # The warnings of a link that succeeded. One comes with every Kotlin object and means nothing here: its IR says
    # DWARF 2 and clang's C objects say DWARF 5.
    warnings = '\n'.join(line for line in r.stderr.splitlines()
                         if line.strip() and "linking module flags 'Dwarf Version'" not in line)
    if 'different target triples' in warnings:       # ld.lld only warns, and the image mixes two calling conventions
        fail(f'qbuild: link failed: an object is built for another core than this link ({cpu})\n{warnings[-4000:]}')
    if warnings:
        print(warnings, flush=True)
    if stubbed:
        print(f'qbuild: warning: {len(stubbed)} runtime symbols stubbed (kmicro does not implement them: a call stops '
              f'the program with "unimplemented runtime symbol", and a board link fails): {" ".join(stubbed)}',
              flush=True)
    print(size_line(out), flush=True)
    if args.run:
        # in the image's folder, as size_line runs binutils
        qemu = [paths.qemu_system_arm().resolve(), *qemu_machine(target), '-nographic', '-semihosting-config',
                'enable=on,target=native', '-kernel', out.name, '-serial', 'none', '-monitor', 'none',
                *(['-icount', 'shift=0,sleep=off'] if args.icount else [])]
        try:
            r = subprocess.run([str(a) for a in qemu], capture_output=True, timeout=args.timeout, cwd=out.parent)
        except subprocess.TimeoutExpired as e:
            sys.stdout.buffer.write((e.stdout or b'') + (e.stderr or b''))
            sys.stdout.flush()
            print(f'qemu: timed out after {args.timeout:g} s', flush=True)
            sys.exit(124)
        sys.stdout.buffer.write(r.stdout)
        sys.stdout.buffer.write(r.stderr)
        sys.stdout.flush()
        print(f'qemu: exit {r.returncode}', flush=True)
        sys.exit(r.returncode)


if __name__ == '__main__':
    main()

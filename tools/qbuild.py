"""Build a QEMU test image: Kotlin LTO object(s) + the kmicro runtime + C code, for an emulated Cortex-M4.

usage: python tools/qbuild.py OUT.elf FILE... [-D NAME=VALUE]... [-I DIR]... [--target l475|an386] [--run]
                              [--timeout SECONDS]

    FILE       C (.c), C++ (.cpp) and assembly (.s, .S) files, compiled with the runtime's flags, and objects (.o, .a)
               linked as they are: the k.o (and bridges.o) that tools/kbuild.py prints. Several C files are fine, e.g.
               main.c support/hw.c
    -D, -I     a definition or include folder for every C file, e.g. -D KM_HEAP_BYTES=32768 (runtime/ and support/
               are always on the include path)
    --target   l475 (default): QEMU b-l475e-iot01a, an STM32L475 (targets/qemu-l475), the layout programs run on.
               an386: QEMU mps2-an386 (targets/qemu-an386: 4 MB of code, 16 MB of RAM, newlib stdio over
               semihosting), for tests that need more memory than a microcontroller has
    --run      run the image on QEMU and exit with the program's exit code (124 when it runs out of time)
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

TARGETS = {   # start code and linker script, QEMU machine, the newlib system-call library
    'l475': (ROOT / 'targets/qemu-l475', 'l475.ld', 'b-l475e-iot01a', ['-lnosys']),
    'an386': (ROOT / 'targets/qemu-an386', 'an386.ld', 'mps2-an386', ['-lrdimon_nano', '--wrap=_exit']),
}
# -g costs no flash. It lets Kotlin code built with debug information keep its line info when LTO inlines it into C.
CFLAGS = [*paths.TARGET_M4F, '-isystem', str(paths.newlib_include()), '-O2', '-g', '-flto', '-ffunction-sections',
          '-fdata-sections', '-fexceptions', '-funwind-tables', '-Wall', '-Wextra', '-Wno-unused-parameter',
          '-I', str(ROOT / 'runtime'), '-I', str(ROOT / 'support')]
CXXFLAGS = ['-std=c++17', '-fno-rtti', '-Wno-unused-variable', '-Wno-unused-but-set-variable']
C_SOURCES = ('.c', '.cpp', '.s', '.S')
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
        cmd = [paths.clang(), *paths.TARGET_M4F, *(flags if src.suffix == '.S' else []), '-c', src]
    else:
        cmd = [paths.clang(), *CFLAGS, *(CXXFLAGS if src.suffix == '.cpp' else []), *flags, '-c', src]
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
    key = hashlib.sha1('\n'.join([str(paths.clang()), *CFLAGS, *defs]).encode()).hexdigest()[:12]
    cache = ROOT / 'build/qbuild' / f'runtime-{key}'
    objs = []
    for s in sources:
        o = cache / (s.relative_to(rt).as_posix().replace('/', '_') + '.o')
        if not o.exists() or o.stat().st_mtime < max(s.stat().st_mtime, headers):
            compile_one(s, o, defs)
        objs.append(o)
    return objs


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
    ap.add_argument('--target', choices=sorted(TARGETS), default='l475', help=hide)
    ap.add_argument('--run', action='store_true', help=hide)
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
    tdir, script, machine, syslibs = TARGETS[args.target]
    defs = [f'-D{d}' for d in args.defs]
    incs = [f'-I{i}' for i in args.incs]
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
            *syslibs, paths.libgcc()]
    stubbed = []
    for _ in range(3):
        r = run([*link, *([stubs_o] if stubbed else [])], check=False)
        if r.returncode == 0:
            break
        new, errors = missing_symbols([*link, *([stubs_o] if stubbed else [])], r.stderr, labels, kotlin)
        if errors:
            fail('qbuild: link failed\n' + '\n'.join('  ' + e for e in errors))
        if not new:
            fail(f'qbuild: link failed\n{r.stderr[-4000:]}')
        stubbed = sorted({*stubbed, *new})
        write_stubs(stubs_s, stubbed)
        compile_one(stubs_s, stubs_o, [])
    else:
        fail(f'qbuild: link failed\n{r.stderr[-4000:]}')
    if stubbed:
        print(f'qbuild: warning: {len(stubbed)} runtime symbols stubbed (kmicro does not implement them: a call stops '
              f'the program with "unimplemented runtime symbol", and a board link fails): {" ".join(stubbed)}',
              flush=True)
    print(size_line(out), flush=True)
    if args.run:
        # in the image's folder, as size_line runs binutils
        qemu = [paths.qemu_system_arm().resolve(), '-machine', machine, '-nographic', '-semihosting-config',
                'enable=on,target=native', '-kernel', out.name, '-serial', 'none', '-monitor', 'none']
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

"""kmicro regression suite: the test programs and the examples, built the way a user builds them and run on QEMU.

usage: python tests/run_all.py [NAME ...] [--kotlin] [--stress] [-v]

    NAME      a test (an unknown name lists them); default: every test
    --kotlin  recompile the Kotlin sources even when their saved IR is current
    --stress  the runtime collects garbage at every allocation (KM_GC_STRESS)
    -v        print what each test builds and runs: the build messages and the program's output

Each test builds its Kotlin sources with toolchain/kn.py build(), as tools/kbuild.py does (kotlinc-native runs only
when a source or an option changed), links them with its C files and the runtime with tools/qbuild.py, runs the image
on QEMU's STM32L475 and checks:

- the exit code;
- the output, line by line against tests/expected/<name>.txt. There {N} stands for a number, {X} for hex digits and
  {*} for any text within a line, and a line {...} for any number of lines: they mark what differs between runs or
  under --stress, such as heap statistics, addresses and times;
- that qbuild stubbed no runtime native (a board link would fail on it);
- that the image fits the STM32L431 kmicro aims at: flash (text + data) at most 256 KB, RAM (data + bss: the heap,
  the runtime's tables, the globals) at most 64 KB, unless the test is marked large with the reason.

A test can instead expect its link to fail, with qbuild's message in its expected file. What a test is compared on
is written to build/t/<name>/run.log, with the checkout's folder written as $ROOT. To add a test: add it to TESTS,
run it, read its run.log, and copy that to tests/expected/<name>.txt with {N} where a number may vary.
"""
import argparse
import contextlib
import difflib
import io
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'toolchain'))
import kn  # noqa: E402

BUILD = ROOT / 'build/t'
EXPECTED = ROOT / 'tests/expected'
FLASH, RAM = 256 * 1024, 64 * 1024          # the STM32L431


@dataclass
class Kotlin:
    """Kotlin sources and kn.build() options (paths relative to the checkout), built in build/t/<folder>."""
    folder: str
    srcs: list
    opts: dict = field(default_factory=dict)


@dataclass
class Test:
    name: str
    kotlin: Kotlin = None               # None: a program of C files only
    c: list = field(default_factory=list)   # C files, the driver first
    heap: int = 16384                   # KM_HEAP_BYTES
    exit: int = 0                       # the program's exit code (QEMU's), or qbuild's when the link must fail
    fails: bool = False                 # the link must fail
    large: str = None                   # why the image may exceed the STM32L431


HELLO = Kotlin('hello', ['examples/hello/hello.kt'], dict(c_api=['examples/hello/hello.h'], package='hello'))
SELFTEST = Kotlin('selftest', ['examples/selftest/selftest.kt'],
                  dict(c_api=['examples/selftest/selftest.h'], package='selftest'))
GC = Kotlin('gc', ['tests/gc/gc.kt'])

TESTS = [
    Test('add', Kotlin('add', ['tests/add/add.kt']), ['tests/add/main.c']),
    Test('cname', Kotlin('cname', ['tests/cname/cname.kt']), ['tests/cname/main.c']),
    Test('objects', Kotlin('objects', ['tests/objects/objects.kt']), ['tests/objects/main.c']),
    Test('gc16k', GC, ['tests/gc/main.c']),
    Test('gc5k', GC, ['tests/gc/main.c'], heap=5120),
    Test('strings', Kotlin('strings', ['tests/strings/strings.kt']), ['tests/strings/main.c']),
    Test('exceptions', Kotlin('exceptions', ['tests/exceptions/exceptions.kt']), ['tests/exceptions/main.c'],
         heap=8192, exit=98),
    Test('coroutines', Kotlin('coroutines', ['tests/coroutines/coroutines.kt']), ['tests/coroutines/main.c'],
         heap=4096),
    Test('app', Kotlin('app', ['tests/app/app.kt']), ['tests/app/main.c'], heap=32768),
    Test('cinterop', Kotlin('cinterop', ['tests/cinterop/cinterop.kt'], dict(defs=['tests/cinterop/kernel.def'])),
         ['tests/cinterop/main.c']),
    Test('cinterop_shapes', Kotlin('cinterop_shapes', ['tests/cinterop_shapes/shapes.kt'],
                                   dict(defs=['tests/cinterop_shapes/drv.def'])), ['tests/cinterop_shapes/drv.c']),
    Test('event_loop', Kotlin('event_loop', ['tests/event_loop/event_loop.kt']), ['tests/event_loop/main.c'],
         heap=8192),
    Test('hello', HELLO, ['examples/hello/main.c']),
    Test('selftest', SELFTEST, ['examples/selftest/main.c']),
]
PATH_OPTIONS = ('c_api', 'defs', 'libs', 'deps', 'include_dirs')
QBUILD_SIZE = re.compile(r'^qbuild: .*  text (\d+)  data (\d+)  bss (\d+).*\n', re.M)
QBUILD_STUBS = re.compile(r'^qbuild: warning: \d+ runtime symbols stubbed .*$', re.M)
QEMU_END = re.compile(r'qemu: (?:exit -?\d+|timed out after .*)\n?\Z')


class Failed(Exception):
    """A test failed: the first line says why, the others show the evidence."""


def normalized(text):
    """Text as it is compared: LF line ends, and each path in the checkout as $ROOT/... with forward slashes."""
    text = text.replace('\r\n', '\n')
    for root in sorted({str(ROOT), ROOT.as_posix()}, key=len, reverse=True):
        text = re.sub(re.escape(root) + r'([^\s\'"():,]*)', lambda m: '$ROOT' + m.group(1).replace('\\', '/'), text)
    return text


def pattern(expected):
    """The expected text as one regular expression (see the module docstring for {N}, {X}, {*} and {...})."""
    parts = []
    for line in expected.splitlines():
        if line == '{...}':
            parts.append(r'(?:[^\n]*\n)*?')
            continue
        p = re.escape(line)
        for mark, rx in ((re.escape('{N}'), r'-?\d+(?:\.\d+)?'), (re.escape('{X}'), r'[0-9a-fA-F]+'),
                         (re.escape('{*}'), r'[^\n]*')):
            p = p.replace(mark, rx)
        parts.append(p + r'\n')
    return re.compile(''.join(parts))


def compare(name, got):
    """got against tests/expected/<name>.txt; raises Failed with a diff when they differ."""
    path = EXPECTED / f'{name}.txt'
    shown = path.relative_to(ROOT).as_posix()
    if not path.exists():
        raise Failed(f'{shown} is missing (the output is in build/t/{name}/run.log)')
    expected = path.read_text(encoding='utf-8')
    if pattern(expected).fullmatch(got if got.endswith('\n') or not got else got + '\n'):
        return
    diff = difflib.unified_diff(expected.splitlines(), got.splitlines(), shown, 'output', lineterm='', n=1)
    raise Failed(f'the output differs from {shown}\n' + '\n'.join(list(diff)[:40]))


_built = {}                             # build folder -> (the options of the last build there, its objects)
_forced = set()


def build_kotlin(k, force, log):
    """kn.build() for k, once per run and set of options. Its messages (compiler warnings, retarget's notes) go to
    log, shown with -v or when the build fails."""
    out = BUILD / k.folder
    key = repr((k.srcs, sorted(k.opts.items())))
    if out in _built and _built[out][0] == key:
        return _built[out][1]
    opts = {o: [ROOT / p for p in v] if o in PATH_OPTIONS else v for o, v in k.opts.items()}
    messages = io.StringIO()
    try:
        with contextlib.redirect_stderr(messages):
            objs = kn.build([ROOT / s for s in k.srcs], out, force=force and out not in _forced, **opts)
    finally:
        log.append(normalized(messages.getvalue()))
    _forced.add(out)
    _built[out] = (key, objs)
    return objs


def qbuild(t, d, objs, args):
    """tools/qbuild.py for test t, into folder d: (exit code, its output)."""
    defs = ['-D', f'KM_HEAP_BYTES={t.heap}', *(['-D', 'KM_GC_STRESS=1'] if args.stress else [])]
    cmd = [sys.executable, ROOT / 'tools/qbuild.py', d / f'{t.name}.elf', *(ROOT / c for c in t.c), *objs, *defs,
           *([] if t.fails else ['--run'])]
    r = subprocess.run([str(a) for a in cmd], capture_output=True, timeout=3600)
    return r.returncode, normalized((r.stdout + r.stderr).decode('utf-8', 'replace'))


def indented(text):
    return ''.join('      ' + line + '\n' for line in text.rstrip('\n').splitlines())


def run_test(t, args):
    """One test: returns the note for its PASS line, or raises Failed."""
    d = BUILD / t.name
    d.mkdir(parents=True, exist_ok=True)
    log = []
    try:
        objs = build_kotlin(t.kotlin, args.kotlin, log) if t.kotlin else []
    except SystemExit as e:
        raise Failed('the Kotlin build failed\n' + ''.join(log) + normalized(str(e))) from None
    rc, out = qbuild(t, d, objs, args)
    if args.verbose:
        print(indented(''.join(log) + out), end='')
    if t.fails:
        got, note = out, 'the link fails as expected'
        (d / 'run.log').write_text(got, encoding='utf-8', newline='\n')
    else:
        size, end = QBUILD_SIZE.search(out), QEMU_END.search(out)
        if not size or not end:
            raise Failed(f'qbuild failed (exit {rc})\n' + out[-3000:])
        got = out[size.end():end.start()]
        (d / 'run.log').write_text(got, encoding='utf-8', newline='\n')
        stubs = QBUILD_STUBS.search(out)
        if stubs:
            raise Failed('qbuild stubbed runtime natives that kmicro does not implement\n' + stubs.group(0))
        text, data, bss = map(int, size.groups())
        note = f'flash {(text + data) / 1024:5.1f} KB  RAM {(data + bss) / 1024:4.1f} KB'
        if (text + data > FLASH or data + bss > RAM) and not t.large:
            raise Failed(f'does not fit the STM32L431 (256 KB flash, 64 KB RAM): {note} (text {text}, data {data}, '
                         f'bss {bss}); shrink it, or mark the test large with the reason')
        if t.large:
            note += f'  (large: {t.large})'
    if rc != t.exit:
        raise Failed(f'exit {rc}, expected {t.exit}\n' + '\n'.join(got.splitlines()[-15:]))
    compare(t.name, got)
    return note


def parse_args():
    names = [t.name for t in TESTS]
    head, usage, *rest = __doc__.split('\n\n')
    ap = argparse.ArgumentParser(usage=usage.split('usage: ', 1)[1], description='\n\n'.join([head, *rest]),
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog='tests: ' + ' '.join(names))
    ap.add_argument('names', nargs='*', help=argparse.SUPPRESS)
    ap.add_argument('--kotlin', action='store_true', help=argparse.SUPPRESS)
    ap.add_argument('--stress', action='store_true', help=argparse.SUPPRESS)
    ap.add_argument('-v', '--verbose', action='store_true', help=argparse.SUPPRESS)
    args = ap.parse_args()
    unknown = [n for n in args.names if n not in names]
    if unknown:
        ap.error(f'no such test: {", ".join(unknown)} (tests: {" ".join(names)})')
    return args


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    args = parse_args()
    selected = [t for t in TESTS if not args.names or t.name in args.names]
    failed = 0
    for t in selected:
        try:
            print(f'PASS  {t.name:22s} {run_test(t, args)}')
        except Failed as e:
            failed += 1
            first, *rest = str(e).splitlines() or ['']
            print(f'FAIL  {t.name:22s} {first}')
            print(indented('\n'.join(rest)), end='')
        except Exception as e:                    # noqa: BLE001 - report it and go on with the next test
            failed += 1
            print(f'FAIL  {t.name:22s} {type(e).__name__}: {e}')
    print(f'{len(selected) - failed} passed, {failed} failed')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()

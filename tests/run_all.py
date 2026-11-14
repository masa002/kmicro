"""kmicro regression suite: the test programs and the examples, built the way a user builds them and run on QEMU.

usage: python tests/run_all.py [NAME ...] [--kotlin] [--stress] [-v]

    NAME      a test (an unknown name lists them); default: every test
    --kotlin  recompile the Kotlin sources even when their saved IR is current
    --stress  the runtime collects garbage at every allocation (KM_GC_STRESS)
    -v        print what each test builds and runs: the build messages and the program's output

Each test builds its Kotlin sources with toolchain/kn.py build(), as tools/kbuild.py does (kotlinc-native runs only
when a source or an option changed), links them with its C files and the runtime with tools/qbuild.py, runs the image
on QEMU's STM32L475 (or mps2-an386, for a test that says so) and checks:

- the exit code;
- the output, line by line against tests/expected/<name>.txt. There {N} stands for a number, {X} for hex digits and
  {*} for any text within a line, and a line {...} for any number of lines: they mark what differs between runs or
  under --stress, such as heap statistics, addresses and times;
- that qbuild stubbed no runtime native (a board link would fail on it);
- that the image fits the STM32L431 kmicro aims at: flash (text + data) at most 256 KB, RAM (data + bss: the heap,
  the runtime's tables, the globals) at most 64 KB, unless the test is marked large with the reason;
- that no function of the image has a stack frame larger than the 4 KB stack guard of the qemu-l475 target, which
  such a frame could step over without a fault (tools/frames.py), unless the test says why it has one;
- the checks the test adds: a tool run on the image or on the output (isr_check, symbolize, frames, gen_regs,
  missing_natives), its exit code and its output against tests/expected/<name>.<check>.txt (not with --stress,
  which builds another runtime than users get).

Several tests can share one Kotlin build and one C driver: the driver then tells the cases apart by a TEST_* macro,
which run_all defines in a small file that includes the driver (build/t/<name>/case_<driver>), so that the runtime,
compiled once per set of -D values, is shared. A test can instead expect its Kotlin build, its link or a command to
fail, with the message in its expected file.

What a test is compared on is written to build/t/<name>/run.log, with the checkout's folder written as $ROOT. To add a
test: add it to TESTS, run it, read its run.log, and copy that to tests/expected/<name>.txt with {N} where a number may
vary.
"""
import argparse
import contextlib
import difflib
import io
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'toolchain'))
sys.path.insert(0, str(ROOT / 'tools'))
import frames  # noqa: E402
import kn  # noqa: E402
import paths  # noqa: E402

BUILD = ROOT / 'build/t'
EXPECTED = ROOT / 'tests/expected'
FLASH, RAM = 256 * 1024, 64 * 1024          # the STM32L431


@dataclass
class Kotlin:
    """Kotlin sources (files or folders) and kn.build() options, paths relative to the checkout, built in
    build/t/<folder>. Builds that differ only in options after the compile (size, hot, init_all, c_api,
    stack_array_error) can share a folder, and with it the compile."""
    folder: str
    srcs: list
    opts: dict = field(default_factory=dict)


@dataclass
class Check:
    """A tool run after the test: tools/<script> with args, in the checkout's folder; {elf}, {log}, {dir} and {kotlin}
    stand for the image, run.log, the test's build folder and its Kotlin build folder. The output is compared with
    tests/expected/<test>.<name>.txt; `same` names two files that must then be identical."""
    name: str
    args: list
    exit: int = 0
    same: tuple = None


@dataclass
class Test:
    name: str
    kotlin: Kotlin = None               # None: a program of C files only
    c: list = field(default_factory=list)   # C files, the driver first
    heap: int = 16384                   # KM_HEAP_BYTES
    exit: int = 0                       # the program's exit code (QEMU's), or that of the step that must fail
    case: dict = field(default_factory=dict)    # macros for the driver only, e.g. {'TEST_ALLOC': 1}
    defs: list = field(default_factory=list)    # more -D values for qbuild: the runtime and every C file
    target: str = 'l475'                # qbuild --target
    large: str = None                   # why the image may exceed the STM32L431
    big_frame: str = None               # why a function of the image may have a frame larger than the stack guard
    checks: list = field(default_factory=list)
    fails: str = None                   # the step that must fail: 'kotlin' (kn.build) or 'link' (qbuild)
    command: object = None              # instead of a build: a function (build folder) -> the command line to run
    archive: bool = False               # link the Kotlin objects from an archive (llvm-ar) instead
    bridges: bool = True                # link the cinterop bridges (bridges.o) that kn.build made
    folder: str = None                  # the build folder's name, if not the test's
    copy: bool = False                  # compile copies of the C files, made in the build folder


def eh_without_exceptions(d):
    """runtime/eh.c with qbuild's flags but no -fexceptions: the build must stop with eh.c's #error."""
    import qbuild
    return [paths.clang(), *[f for f in qbuild.CFLAGS if f != '-fexceptions'], '-c', ROOT / 'runtime/eh.c', '-o',
            d / 'eh.o']


ADD = Kotlin('add', ['tests/add/add.kt'])
GC = Kotlin('gc', ['tests/gc/gc.kt'])
STRINGS = Kotlin('strings', ['tests/strings/strings.kt'])
EXCEPTIONS = Kotlin('exceptions', ['tests/exceptions'])
CINTEROP = Kotlin('cinterop', ['tests/cinterop/cinterop.kt'], dict(defs=['tests/cinterop/kernel.def']))
SHAPES = Kotlin('cinterop_shapes', ['tests/cinterop_shapes/shapes.kt'], dict(defs=['tests/cinterop_shapes/drv.def']))
HELLO = Kotlin('hello', ['examples/hello/hello.kt'], dict(c_api=['examples/hello/hello.h'], package='hello'))
SELFTEST_API = dict(c_api=['examples/selftest/selftest.h'], package='selftest')
SELFTEST = Kotlin('selftest', ['examples/selftest/selftest.kt'], SELFTEST_API)
IRQ = Kotlin('irq', ['examples/irq'], dict(defs=['support/hw.def'], c_api=['examples/irq/irq.h'], package='irq',
                                           init_all='kt_init_all'))
INTERRUPTS = Kotlin('interrupts', ['tests/interrupts'], dict(c_api=['tests/interrupts/isr.h'], package='isr',
                                                             init_all='kt_init_all'))
WINDOW = Kotlin('interrupt_window', ['tests/interrupt_window/window.kt'], dict(defs=['support/hw.def']))
NATIVES = Kotlin('natives', ['tests/natives/natives.kt'])
MEMORY = Kotlin('memory', ['tests/memory/memory.kt', 'tests/memory/globals.kt'])
FAULTS = Kotlin('faults', ['tests/faults/faults.kt'])

SYMBOLIZE = Check('symbolize', ['tools/symbolize.py', '{elf}', '{log}'])
REGEX = 'the Regex engine, which CANON_EQ needs, is most of its flash'


def uncaught(name, macro, exit=98, **kw):
    return Test(name, EXCEPTIONS, ['tests/exceptions/uncaught.c'], exit=exit, case={macro: 1}, **kw)


def isr(name, macro, exit=98, **kw):
    return Test(name, INTERRUPTS, ['tests/interrupts/main.c'], exit=exit, case={macro: 1, **kw.pop('case', {})}, **kw)


def native(name, macro, exit=98, **kw):
    return Test(name, NATIVES, ['tests/natives/main.c'], exit=exit, case={macro: 1}, **kw)


def memory(name, macro, exit=0, **kw):
    return Test(name, MEMORY, ['tests/memory/main.c'], exit=exit, case={macro: 1}, **kw)


def fault(name, macro, exit=99, **kw):
    return Test(name, FAULTS, ['tests/faults/main.c'], exit=exit, case={macro: 1}, **kw)


TESTS = [
    # the language and the runtime, each from C
    Test('add', ADD, ['tests/add/main.c']),
    Test('cname', Kotlin('cname', ['tests/cname/cname.kt']), ['tests/cname/main.c']),
    Test('objects', Kotlin('objects', ['tests/objects/objects.kt']), ['tests/objects/main.c']),
    Test('gc16k', GC, ['tests/gc/main.c']),
    Test('gc5k', GC, ['tests/gc/main.c'], heap=5120),
    Test('strings', STRINGS, ['tests/strings/main.c']),
    Test('strings_latin1', Kotlin('strings_latin1', STRINGS.srcs, dict(kotlinc_args=['-Xbinary=latin1Strings=true'])),
         ['tests/strings/main.c']),
    Test('coroutines', Kotlin('coroutines', ['tests/coroutines/coroutines.kt']), ['tests/coroutines/main.c'],
         heap=4096),
    Test('app', Kotlin('app', ['tests/app/app.kt']), ['tests/app/main.c'], heap=32768),
    Test('event_loop', Kotlin('event_loop', ['tests/event_loop/event_loop.kt']), ['tests/event_loop/main.c'],
         heap=8192),
    Test('kotlin_main', Kotlin('kotlin_main', ['tests/kotlin_main/main.kt'], dict(main=True)),
         ['targets/common/kotlin_main.c']),
    # exceptions: caught, then uncaught; the report, the hook, processUnhandledException
    Test('exceptions', EXCEPTIONS, ['tests/exceptions/main.c'], heap=8192, exit=98, checks=[SYMBOLIZE]),
    uncaught('uncaught_cause_chain', 'TEST_CAUSE_CHAIN', checks=[SYMBOLIZE]),
    uncaught('uncaught_long_message', 'TEST_LONG_MESSAGE'),
    uncaught('uncaught_failed_initializer', 'TEST_FAILED_INITIALIZER'),
    uncaught('uncaught_hook', 'TEST_HOOK'),
    uncaught('uncaught_hook_terminates', 'TEST_HOOK_TERMINATES'),
    uncaught('uncaught_hook_throws', 'TEST_HOOK_THROWS'),
    uncaught('uncaught_circular_cause', 'TEST_CIRCULAR_CAUSE'),
    uncaught('uncaught_message_throws', 'TEST_MESSAGE_THROWS'),
    uncaught('unhandled_without_hook', 'TEST_PROCESS_WITHOUT_HOOK'),
    uncaught('unhandled_with_hook', 'TEST_PROCESS_WITH_HOOK', exit=0),
    Test('eh_needs_fexceptions', command=eh_without_exceptions, exit=1),
    # calling C: cinterop, C calling Kotlin, and qbuild's link errors
    Test('cinterop', CINTEROP, ['tests/cinterop/main.c']),
    Test('cinterop_no_bridges', CINTEROP, ['tests/cinterop/main.c'], bridges=False, fails='link', exit=1),
    Test('cinterop_archive', CINTEROP, ['tests/qbuild/poke.c'], archive=True, fails='link', exit=1),
    Test('cinterop_shapes', SHAPES, ['tests/cinterop_shapes/drv.c']),
    Test('cinterop_callback_throws', SHAPES, ['tests/cinterop_shapes/drv.c'], exit=98,
         case={'TEST_CALLBACK_THROWS': 1}),
    Test('qbuild_c_files', None, ['tests/qbuild/init.c', 'support/hw.c']),
    Test('qbuild_undefined', None, ['tests/qbuild/undefined.c'], fails='link', exit=1),
    Test('qbuild_folder_name', ADD, ['tests/add/main.c'], folder='テスト フォルダ', copy=True),
    # interrupt handlers: the run-time guards, isr_check, --init-all, reference stores while the collector marks
    isr('isr_alloc', 'TEST_ALLOC', checks=[Check('isr_check', ['tools/isr_check.py', '{elf}'], exit=1), SYMBOLIZE]),
    isr('isr_to_string', 'TEST_TO_STRING'),
    isr('isr_gc', 'TEST_GC'),
    isr('isr_collect', 'TEST_COLLECT'),
    isr('isr_schedule', 'TEST_SCHEDULE', exit=0),
    isr('isr_lazy_globals', 'TEST_LAZY'),
    isr('isr_init_all', 'TEST_INIT_ALL', exit=0),
    isr('isr_throw', 'TEST_THROW', exit=0),
    Test('isr_init_window', WINDOW, ['tests/interrupt_window/main.c', 'support/hw.c'], exit=98),
    isr('isr_swap_fields', 'TEST_SWAP_FIELDS', exit=0, heap=32768, defs=['KM_GC_STRESS=1'],
        case={'RVR': '200u', 'ROUNDS': 40000}),
    isr('isr_swap_slots', 'TEST_SWAP_SLOTS', exit=0, heap=32768, defs=['KM_GC_STRESS=1'],
        case={'RVR': '200u', 'ROUNDS': 40000}),
    # runtime natives: platform values, console input, entropy, and the APIs kmicro does not support
    native('natives_platform', 'TEST_PLATFORM', exit=3,
           checks=[Check('missing_natives', ['tools/missing_natives.py', '--check', '--ir', '{kotlin}/m4.ll'])]),
    native('natives_input', 'TEST_INPUT', exit=0),
    native('natives_canon_eq', 'TEST_CANON_EQ', exit=0, heap=32768, large=REGEX),
    native('natives_weak_reference', 'TEST_WEAK_REFERENCE'),
    native('natives_worker', 'TEST_WORKER'),
    native('natives_gc_tuning', 'TEST_GC_TUNING'),
    native('natives_uuid', 'TEST_UUID'),
    native('natives_uuid_entropy', 'TEST_UUID_ENTROPY', exit=0),
    # memory: the heap and the native arena running out, the runtime's tables, the Unicode tables
    memory('oom_catch', 'TEST_TOO_BIG'),
    memory('oom_panic', 'TEST_HEAP_FULL', exit=98),
    memory('native_oom', 'TEST_NATIVE_OOM'),
    memory('stable_refs_full', 'TEST_STABLE_REFS', exit=98),
    memory('globals_limit', 'TEST_GLOBALS', exit=98),
    memory('globals_raised', 'TEST_GLOBALS', defs=['KM_GLOBALS=300']),
    memory('unicode_tables', 'TEST_UNICODE_TABLES'),
    Test('native_double_free', None, ['tests/memory/double_free.c'], exit=98),
    Test('native_arena_fuzz', None, ['tests/memory/arena_fuzz.c']),
    # faults the start code reports, and frames on the stack
    fault('stack_overflow', 'TEST_STACK_OVERFLOW'),
    fault('null_field', 'TEST_NULL_FIELD'),
    fault('stack_guard', 'TEST_GUARD_SCAN', exit=0,
          checks=[Check('scan', ['tests/faults/guard_scan.py', '{elf}'])]),
    fault('stack_array', 'TEST_BIG_ARRAY', exit=0, big_frame='a 56 KB array on the stack, which frames.py must report',
          checks=[Check('frames', ['tools/frames.py', '{elf}', '--top', '1', '--limit', '8192'], exit=1)]),
    Test('stack_array_error', Kotlin('faults', FAULTS.srcs, dict(stack_array_error=True)), fails='kotlin', exit=1),
    # the examples
    Test('hello', HELLO, ['examples/hello/main.c']),
    Test('selftest', SELFTEST, ['examples/selftest/main.c'],
         checks=[Check('isr_check', ['tools/isr_check.py', '{elf}']),
                 Check('isr_check_boxing', ['tools/isr_check.py', '{elf}', '--boxing'], exit=1)]),
    Test('selftest_an386', SELFTEST, ['examples/selftest/main.c'], heap=1024 * 1024, target='an386',
         large='mps2-an386, with a 1 MB heap'),
    Test('selftest_size', Kotlin('selftest', SELFTEST.srcs, dict(SELFTEST_API, size=True, init_all='kt_init_all',
                                                                    hot=r'^kfun:selftest#(gcChains|coroEvent)\(')),
         ['examples/selftest/main.c']),
    Test('irq', IRQ, ['examples/irq/main.c', 'support/hw.c'],
         checks=[Check('isr_check', ['tools/isr_check.py', '{elf}']),
                 Check('gen_regs', ['tools/gen_regs.py', '--header', 'examples/irq/systick.h', '--sources',
                                    'examples/irq', '--out', '{dir}/gen/Regs.kt', '--package', 'irq'],
                       same=('{dir}/gen/Regs.kt', 'examples/irq/Regs.kt'))]),
]
STACK_GUARD = 4096                      # targets/qemu-l475/l475.ld
PATH_OPTIONS = ('c_api', 'defs', 'libs', 'deps', 'include_dirs')
QBUILD_SIZE = re.compile(r'^qbuild: .*  text (\d+)  data (\d+)  bss (\d+).*\n', re.M)
QBUILD_STUBS = re.compile(r'^qbuild: warning: \d+ runtime symbols stubbed .*$', re.M)
# the last such line: a tool warning on stderr (an untested LLVM, say) comes after it
QEMU_END = re.compile(r'^qemu: (?:exit -?\d+|timed out after .*)$\n?', re.M)


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


def compare(name, got, log_name):
    """got against tests/expected/<name>.txt; raises Failed with a diff when they differ."""
    path = EXPECTED / f'{name}.txt'
    shown = path.relative_to(ROOT).as_posix()
    if not path.exists():
        raise Failed(f'{shown} is missing (the output is in {log_name})')
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
        if isinstance(_built[out][1], SystemExit):        # failed before in this run: not again
            raise _built[out][1]
        return _built[out][1]
    opts = {o: [ROOT / p for p in v] if o in PATH_OPTIONS else v for o, v in k.opts.items()}
    messages = io.StringIO()
    try:
        with contextlib.redirect_stderr(messages):
            objs = kn.build([ROOT / s for s in k.srcs], out, force=force and out not in _forced, **opts)
    except SystemExit as e:
        _built[out] = (key, e)
        raise
    finally:
        log.append(normalized(messages.getvalue()))
        _forced.add(out)
    _built[out] = (key, objs)
    return objs


def c_files(t, d):
    """The test's C files: copies in d (t.copy), and the driver wrapped in a file that defines t.case first."""
    files = [ROOT / c for c in t.c]
    if t.copy:
        files = [Path(shutil.copy2(f, d / f.name)) for f in files]
    if t.case:
        wrapper = d / ('case_' + files[0].name)
        text = ''.join(f'#define {k} {v}\n' for k, v in t.case.items()) + f'#include "{files[0].as_posix()}"\n'
        if not wrapper.exists() or wrapper.read_text(encoding='utf-8') != text:
            wrapper.write_text(text, encoding='utf-8', newline='\n')
        files[0] = wrapper
    return files


def archived(objs, d):
    """The objects in one archive, d/kotlin.a, made with the llvm-ar next to the compiler's clang."""
    ar = paths.clang().parent / ('llvm-ar' + paths.EXE)
    a = d / 'kotlin.a'
    a.unlink(missing_ok=True)
    subprocess.run([str(ar), 'rcs', str(a), *map(str, objs)], check=True)
    return [a]


def qbuild(t, d, objs, args):
    """tools/qbuild.py for test t, into folder d: (exit code, its output)."""
    defs = dict.fromkeys([f'KM_HEAP_BYTES={t.heap}', *t.defs, *(['KM_GC_STRESS=1'] if args.stress else [])])
    timeout = 120 * (10 if args.stress else 1)
    cmd = [sys.executable, ROOT / 'tools/qbuild.py', d / f'{t.name}.elf', *c_files(t, d), *objs,
           *(x for v in defs for x in ('-D', v)), '--target', t.target,
           *([] if t.fails else ['--run', '--timeout', str(timeout)])]
    r = subprocess.run([str(a) for a in cmd], capture_output=True, timeout=timeout + 1800)
    return r.returncode, normalized((r.stdout + r.stderr).decode('utf-8', 'replace'))


def indented(text):
    return ''.join('      ' + line + '\n' for line in text.rstrip('\n').splitlines())


def run_check(t, c, d, args):
    """One check of test t: raises Failed when it does not pass."""
    k = BUILD / (t.kotlin.folder if t.kotlin else '')
    subst = dict(elf=(d / f'{t.name}.elf').as_posix(), log=(d / 'run.log').as_posix(), dir=d.as_posix(),
                 kotlin=k.as_posix())
    argv = [a.format(**subst) for a in c.args]
    if c.same:
        shutil.rmtree(Path(c.same[0].format(**subst)).parent, ignore_errors=True)
    r = subprocess.run([sys.executable, ROOT / argv[0], *argv[1:]], capture_output=True, cwd=ROOT, timeout=600)
    out = normalized((r.stdout + r.stderr).decode('utf-8', 'replace'))
    (d / f'{c.name}.log').write_text(out, encoding='utf-8', newline='\n')
    if args.verbose:
        print(indented(f'$ python {" ".join(argv)}\n' + out), end='')
    if r.returncode != c.exit:
        raise Failed(f'{c.name}: exit {r.returncode}, expected {c.exit}\n' + out[-3000:])
    try:
        compare(f'{t.name}.{c.name}', out, f'build/t/{d.name}/{c.name}.log')
    except Failed as e:
        raise Failed(f'{c.name}: {e}') from None
    if c.same:
        a, b = (ROOT / p.format(**subst) for p in c.same)
        if a.read_bytes() != b.read_bytes():
            raise Failed(f'{c.name}: {normalized(str(a))} differs from {normalized(str(b))}')


def program_output(t, d, rc, out):
    """What the program printed, taken from qbuild's output after the checks on the image (stubs, size): (the output,
    the note for the PASS line)."""
    size, end = QBUILD_SIZE.search(out), ([None] + list(QEMU_END.finditer(out)))[-1]
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
    if t.target == 'l475' and not t.big_frame:
        name, size = frames.of_image(d / f'{t.name}.elf')[0]
        if size > STACK_GUARD:
            raise Failed(f'{name} has a stack frame of {size} bytes, larger than the {STACK_GUARD}-byte stack guard '
                         f'of qemu-l475, which it could step over without a fault; shrink it, or give the test '
                         f'big_frame with the reason')
    return got, note + (f'  (large: {t.large})' if t.large else '')


def run_test(t, args):
    """One test: returns the note for its PASS line, or raises Failed."""
    d = BUILD / (t.folder or t.name)
    d.mkdir(parents=True, exist_ok=True)
    log_name = f'build/t/{d.name}/run.log'
    log = []
    if t.command:
        r = subprocess.run([str(a) for a in t.command(d)], capture_output=True, timeout=600)
        objs, rc, got = None, r.returncode, normalized((r.stdout + r.stderr).decode('utf-8', 'replace'))
        note = 'fails as expected'
    else:
        try:
            objs = build_kotlin(t.kotlin, args.kotlin, log) if t.kotlin else []
        except SystemExit as e:
            if t.fails != 'kotlin':
                raise Failed('the Kotlin build failed\n' + ''.join(log) + normalized(str(e))) from None
            objs, rc, got, note = None, 1, normalized(str(e)) + '\n', 'the Kotlin build fails as expected'
        else:
            if t.fails == 'kotlin':
                raise Failed('the Kotlin build did not fail\n' + ''.join(log))
        if objs is not None:
            objs = [o for o in objs if t.bridges or o.name != 'bridges.o']
            rc, out = qbuild(t, d, archived(objs, d) if t.archive else objs, args)
            if args.verbose:
                print(indented(''.join(log) + out), end='')
            got, note = out, 'the link fails as expected'
        if objs is not None and not t.fails:
            got, note = program_output(t, d, rc, out)
    (d / 'run.log').write_text(got, encoding='utf-8', newline='\n')
    if args.verbose and objs is None:
        print(indented(''.join(log) + got), end='')
    if rc != t.exit:
        raise Failed(f'exit {rc}, expected {t.exit}\n' + '\n'.join(got.splitlines()[-15:]))
    compare(t.name, got, log_name)
    checks = [] if args.stress else t.checks       # they look at the image users get, not the stress build
    for c in checks:
        run_check(t, c, d, args)
    return note + ''.join(f', {c.name}' for c in checks)


def parse_args():
    names = [t.name for t in TESTS]
    head, usage, *rest = __doc__.split('\n\n')
    ap = argparse.ArgumentParser(usage=usage.split('usage: ', 1)[1], description='\n\n'.join([head, *rest]),
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog='tests: ' + ' '.join(names))
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
            print(f'PASS  {t.name:28s} {run_test(t, args)}')
        except Failed as e:
            failed += 1
            first, *rest = str(e).splitlines() or ['']
            print(f'FAIL  {t.name:28s} {first}')
            print(indented('\n'.join(rest)), end='')
        except Exception as e:                    # noqa: BLE001 - report it and go on with the next test
            failed += 1
            print(f'FAIL  {t.name:28s} {type(e).__name__}: {e}')
    print(f'{len(selected) - failed} passed, {failed} failed')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()

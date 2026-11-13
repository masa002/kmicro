"""kmicro regression suite: every Kotlin test program, on the emulated STM32L475 (QEMU), with the kmicro runtime.

usage: python tests/run_all.py [name ...] [--kotlin] [--stress]
       --kotlin: recompile the Kotlin sources even if their IR is current; --stress: collect at every allocation

Per test: toolchain/kn.py build() (kotlinc-native 2.4.21 only when a source is newer than its saved IR, retarget,
clang -flto) -> tools/qbuild.py (runtime + C driver) -> QEMU. A test passes when the program exits as expected (the
uncaught-exception test expects 98) and its output holds the expected text. The examples/ programs run here too.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'toolchain'))
import kn  # noqa: E402

HELLO = dict(c_api=['examples/hello/hello.h'], package='hello')
SELFTEST = dict(c_api=['examples/selftest/selftest.h'], package='selftest')
KERNEL = dict(defs=['tests/cinterop/kernel.def'])
SHAPES = dict(defs=['tests/cinterop_shapes/drv.def'])
# name, kotlin sources, C driver, kn.build() options, heap bytes, expected exit, text that must appear
TESTS = [
    ('add', ['tests/add/add.kt'], 'tests/add/main.c', {}, 16384, 0, 'add(40, 2) = 42'),
    ('cname', ['tests/cname/cname.kt'], 'tests/cname/main.c', {}, 16384, 0, 'cname: OK'),
    ('objects', ['tests/objects/objects.kt'], 'tests/objects/main.c', {}, 16384, 0, 'OK'),
    ('gc16k', ['tests/gc/gc.kt'], 'tests/gc/main.c', {}, 16384, 0, 'OK'),
    ('gc5k', ['tests/gc/gc.kt'], 'tests/gc/main.c', {}, 5120, 0, 'OK'),
    ('strings', ['tests/strings/strings.kt'], 'tests/strings/main.c', {}, 16384, 0, 'mask = 0  OK'),
    ('exceptions', ['tests/exceptions/exceptions.kt'], 'tests/exceptions/main.c', {}, 8192, 98,
     'Uncaught Kotlin exception: PanelError: panel error -5'),
    ('coroutines', ['tests/coroutines/coroutines.kt'], 'tests/coroutines/main.c', {}, 4096, 0, 'OK'),
    ('app', ['tests/app/app.kt'], 'tests/app/main.c', {}, 32768, 0, 'OK'),
    ('cinterop', ['tests/cinterop/cinterop.kt'], 'tests/cinterop/main.c', KERNEL, 16384, 0, 'poke(7) = 1003  OK'),
    ('cinterop_shapes', ['tests/cinterop_shapes/shapes.kt'], 'tests/cinterop_shapes/drv.c', SHAPES, 16384, 0,
     'cinterop_shapes: all OK'),
    ('event_loop', ['tests/event_loop/event_loop.kt'], 'tests/event_loop/main.c', {}, 8192, 0,
     'ticks*100+presses = 502'),
    ('hello', ['examples/hello/hello.kt'], 'examples/hello/main.c', HELLO, 16384, 0,
     'Hello from Kotlin #1, Kotlin #2, Kotlin #3 on a bare Cortex-M4'),
    ('selftest', ['examples/selftest/selftest.kt'], 'examples/selftest/main.c', SELFTEST, 16384, 0, 'result: ALL PASS'),
]


def kotlin(name, srcs, opts, force):
    c_api = [ROOT / h for h in opts.get('c_api', [])]
    defs = [ROOT / d for d in opts.get('defs', [])]
    return kn.build([ROOT / s for s in srcs], ROOT / 'build/t' / name, c_api=c_api, package=opts.get('package'),
                    defs=defs, force=force)


def main():
    force = '--kotlin' in sys.argv
    only = [a for a in sys.argv[1:] if not a.startswith('--')]
    failed = 0
    for name, srcs, driver, opts, heap, want_exit, want_text in TESTS:
        if only and name not in only:
            continue
        try:
            objs = kotlin(name, srcs, opts, force)
            elf = ROOT / 'build/t' / name / f'{name}.elf'
            stress = ['-D', 'KM_GC_STRESS=1'] if '--stress' in sys.argv else []
            r = subprocess.run([sys.executable, ROOT / 'tools/qbuild.py', elf, ROOT / driver, *objs, '-D',
                                f'KM_HEAP_BYTES={heap}', *stress, '--run'], capture_output=True, timeout=1800)
            out = r.stdout.decode('utf-8', 'replace') + r.stderr.decode('utf-8', 'replace')
            ok = r.returncode == want_exit and want_text in out
            size = next((l.split('  ', 1)[1] for l in out.splitlines() if l.startswith('qbuild: ') and ' text ' in l), '')
            print(f'{"PASS" if ok else "FAIL"}  {name:9s} {size}', flush=True)
            if not ok:
                failed += 1
                print('      ' + '\n      '.join(out.strip().splitlines()[-12:]))
        except (Exception, SystemExit) as e:          # noqa: BLE001 - report and go on
            failed += 1
            print(f'FAIL  {name:9s} {e}')
    print(f'{len([t for t in TESTS if not only or t[0] in only]) - failed} passed, {failed} failed')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()

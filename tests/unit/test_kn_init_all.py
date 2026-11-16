# Copyright 2026 the kmicro authors (NOTICE).
# SPDX-License-Identifier: Apache-2.0
"""toolchain/kn.py add_init_all(): which globals --init-all initialises (an IR excerpt, no compiler needed).

python -m unittest discover -s tests/unit
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'toolchain'))
import kn  # noqa: E402


def init(state, fn):
    return f'  call void @CallInitGlobalPossiblyLock(ptr noundef @"state_global${state}", ptr noundef @"kfun:{fn}")\n'


def init_local(state, fn, with_global=True):
    """The call for @ThreadLocal globals: the state of the file's other globals comes first, null without any."""
    first = f'@"state_global${state}"' if with_global else 'null'
    return (f'  call void @CallInitThreadLocal(ptr noundef {first}, ptr noundef @"state_thread_local${state}", '
            f'ptr noundef @"kfun:{fn}")\n')


# the root package: a lower-case name, Écran as the IR writes it, a private object. The package cfg has no function.
ROOT_OBJECTS = ['Registry', 'Registry.Companion', r'\C3\89cran', 'calibration', 'hidden']
STRING = ('@%d = internal unnamed_addr constant { ptr, i32, i32, i16, [%d x i8] } { ptr getelementptr (i8, ptr '
          '@"kclass:kotlin.String", i32 1), i32 3, i32 %d, i16 %d, [%d x i8] %s }\n')


def kclass(name, package_name, private=False):
    """A class record as kotlinc-native writes it: the 12th field of the TypeInfo is the string of its package."""
    sym = f'kclass:{name}#internal' if private else f'kclass:{name}'
    return (f'@"{sym}" = {"internal " if private else ""}constant {{ %struct.TypeInfo, [3 x ptr] }} '
            f'{{ %struct.TypeInfo {{ ptr @"{sym}", ptr null, i32 0, i32 8, ptr @"kclass:kotlin.Any", '
            f'ptr @"krefs:{name}", i32 1, ptr null, i32 0, i32 0, ptr @"kifacetable:{name}", ptr {package_name}, '
            'ptr @9, i32 770, i32 436, ptr null, ptr @Kotlin_processObjectInMark, i32 8 }, [3 x ptr] '
            'zeroinitializer }\n')


IR = ('define void @"kfun:loop#step(){}"() {\n'
      + init('loop$C:/src/loop.kt', 'loop.$init_global$loop.kt#internal')
      + init('loop.Loop', 'loop.Loop.$init_global#internal')
      + init('loop.Loop.Companion', 'loop.Loop.Companion.$init_global#internal')
      + init('loop.io$C:/src/io.kt', 'loop.io.$init_global$io.kt#internal')
      + init('loop.io.Uart', 'loop.io.Uart.$init_global#internal')
      + init('loopy.Other', 'loopy.Other.$init_global#internal')
      + init_local('loop$C:/src/loop.kt', 'loop.$init_thread_local$loop.kt#internal')
      + init_local('loop.io.Cache', 'loop.io.Cache.$init_thread_local#internal', with_global=False)
      + init_local('loopy.Scratch', 'loopy.Scratch.$init_thread_local#internal', with_global=False)
      + init_local('tls$C:/src/tls.kt', 'tls.$init_thread_local$tls.kt#internal', with_global=False)
      + init_local('kotlin.native.concurrent.CurrentThread',
                   'kotlin.native.concurrent.CurrentThread.$init_thread_local#internal', with_global=False)
      + init('kotlin.collections.ArrayList', 'kotlin.collections.ArrayList.$init_global#internal')
      + init('cfg.Settings', 'cfg.Settings.$init_global#internal')
      + 'define void @"kfun:#main(){}"() {\n'
      + init('<root>$C:/src/main.kt', '$init_global$main.kt#internal')
      + init_local('<root>$C:/src/main.kt', '$init_thread_local$main.kt#internal')
      + ''.join(init(n, n + '.$init_global#internal') for n in ROOT_OBJECTS)
      + STRING % (1, 0, 0, 1, 0, 'zeroinitializer') + STRING % (2, 6, 98404, 0, 6, r'c"c\00f\00g\00"')
      + ''.join(kclass(n, '@1', private=n == 'hidden') for n in ROOT_OBJECTS) + kclass('cfg.Settings', '@2'))


def function(name, *lines):
    return f'define void @"kfun:{name}"() {{\n' + ''.join(lines) + '  ret void\n}\n'


# A package that reaches objects of the standard library and of a cinterop package: by a call, and through a class
# it names, whose record lists the member functions. Nothing of the package drv refers to kotlin.random.Random.
LIBRARY_IR = (
    function('drv#poll(){}', init('drv$C:/src/drv.kt', 'drv.$init_global$drv.kt#internal'),
             '  call void @"kfun:kotlinx.cinterop.IntVarOf#<get-$companion>#static(){}"()\n',
             '  %1 = call ptr @AllocInstance(ptr @"kclass:kotlin.ranges.UIntRange", ptr null)\n')
    + function('kotlinx.cinterop.IntVarOf#<get-$companion>#static(){}',
               init('kotlinx.cinterop.IntVarOf', 'kotlinx.cinterop.IntVarOf.$init_global#internal'))
    + '@"kclass:kotlin.ranges.UIntRange" = constant { ptr, [1 x ptr] } { ptr null, [1 x ptr] '
      '[ptr @"kfun:kotlin.ranges.UIntRange#contains(){}"] }\n'
    + function('kotlin.ranges.UIntRange#contains(){}',
               init('kotlin.ranges.UIntRange', 'kotlin.ranges.UIntRange.$init_global#internal'),
               init('kotlin.collections.ArrayList', 'kotlin.collections.ArrayList.$init_global#internal'),
               init('kotlin.native.internal.NativePtr', 'kotlin.native.internal.NativePtr.$init_global#internal'),
               '  call void @"kfun:dev.point#<get-$companion>#static(){}"()\n')
    + function('dev.point#<get-$companion>#static(){}', init('dev.point', 'dev.point.$init_global#internal'))
    + function('other#unused(){}', init('kotlin.random.Random', 'kotlin.random.Random.$init_global#internal')))


def states(lines):
    return [l.split('"state_global$')[1].split('"')[0] for l in lines
            if '@CallInitGlobalPossiblyLock(' in l and '"state_global$' in l]


def local_states(lines):
    return [l.split('"state_thread_local$')[1].split('"')[0] for l in lines if '@CallInitThreadLocal(' in l]


class InitAll(unittest.TestCase):
    def test_files_objects_and_sub_packages(self):
        self.assertEqual(states(kn.add_init_all(IR, 'loop')),
                         ['loop$C:/src/loop.kt', 'loop.Loop', 'loop.Loop.Companion', 'loop.io$C:/src/io.kt',
                          'loop.io.Uart'])

    def test_sub_package_alone(self):
        self.assertEqual(states(kn.add_init_all(IR, 'loop.io')), ['loop.io$C:/src/io.kt', 'loop.io.Uart'])

    def test_root_package(self):
        self.assertEqual(states(kn.add_init_all(IR, '')), ['<root>$C:/src/main.kt', *sorted(ROOT_OBJECTS)])

    def test_thread_local_globals(self):
        lines = kn.add_init_all(IR, 'loop')
        self.assertEqual(local_states(lines), ['loop$C:/src/loop.kt', 'loop.io.Cache'])
        self.assertIn('  call void @CallInitThreadLocal(ptr @"state_global$loop$C:/src/loop.kt", '
                      'ptr @"state_thread_local$loop$C:/src/loop.kt", '
                      'ptr @"kfun:loop.$init_thread_local$loop.kt#internal")', lines)
        self.assertIn('  call void @CallInitThreadLocal(ptr null, ptr @"state_thread_local$loop.io.Cache", '
                      'ptr @"kfun:loop.io.Cache.$init_thread_local#internal")', lines)
        self.assertLess(max(i for i, l in enumerate(lines) if '@CallInitGlobalPossiblyLock(' in l),
                        min(i for i, l in enumerate(lines) if '@CallInitThreadLocal(' in l))
        self.assertEqual(local_states(kn.add_init_all(IR, '')), ['<root>$C:/src/main.kt'])

    def test_calls_with_the_class(self):
        # Kotlin/Native 2.5 as retarget.py leaves it: the runtime's functions that take the class (null for a file)
        ir = ('  call void @kmicro_init_global(ptr noundef @"state_global$loop$C:/src/loop.kt", '
              'ptr noundef @"kfun:loop.$init_global$loop.kt#internal", ptr noundef null)\n'
              '  call void @kmicro_init_global(ptr noundef @"state_global$loop.Loop", '
              'ptr noundef @"kfun:loop.Loop.$init_global#internal", ptr noundef @"kclass:loop.Loop")\n'
              '  call void @kmicro_init_thread_local(ptr noundef @"state_global$loop.Loop", '
              'ptr noundef @"state_thread_local$loop.Loop", '
              'ptr noundef @"kfun:loop.Loop.$init_thread_local#internal", ptr noundef @"kclass:loop.Loop")\n'
              '  call void @kmicro_init_global(ptr noundef @"state_global$loopy.Other", '
              'ptr noundef @"kfun:loopy.Other.$init_global#internal", ptr noundef @"kclass:loopy.Other")\n')
        self.assertEqual(kn.add_init_all(ir, 'loop')[1:-2], [
            '  call void @kmicro_init_global(ptr @"state_global$loop$C:/src/loop.kt", '
            'ptr @"kfun:loop.$init_global$loop.kt#internal", ptr null)',
            '  call void @kmicro_init_global(ptr @"state_global$loop.Loop", '
            'ptr @"kfun:loop.Loop.$init_global#internal", ptr @"kclass:loop.Loop")',
            '  call void @kmicro_init_thread_local(ptr @"state_global$loop.Loop", ptr @"state_thread_local$loop.Loop", '
            'ptr @"kfun:loop.Loop.$init_thread_local#internal", ptr @"kclass:loop.Loop")'])

    def test_package_with_thread_local_globals_only(self):
        self.assertEqual(local_states(kn.add_init_all(IR, 'tls')), ['tls$C:/src/tls.kt'])

    def test_library_objects_come_from_a_table(self):
        # one entry per global of LIBRARY_GLOBALS that the module uses, tied to its state: the link drops the entry
        # with the state. Not the ArrayList companion, which is not in the list. The package's own calls follow.
        lines = kn.add_init_all(LIBRARY_IR, 'drv')
        entries = [l for l in lines if l.startswith('@"km_init$')]
        self.assertEqual([l.split('"')[1] for l in entries],
                         ['km_init$kotlin.native.internal.NativePtr', 'km_init$kotlin.random.Random',
                          'km_init$kotlin.ranges.UIntRange', 'km_init$kotlinx.cinterop.IntVarOf'])
        self.assertEqual(entries[2], '@"km_init$kotlin.ranges.UIntRange" = internal constant { ptr, ptr, ptr } '
                         '{ ptr @"state_global$kotlin.ranges.UIntRange", '
                         'ptr @"kfun:kotlin.ranges.UIntRange.$init_global#internal", ptr null }, section "km_init", '
                         'align 4, !associated !{ptr @"state_global$kotlin.ranges.UIntRange"}')
        # the compiler keeps each entry, and each state as a global of its own (--size would merge the states)
        used = [l for l in lines if l.startswith('@llvm.compiler.used = ')][0]
        self.assertIn('appending global [8 x ptr] [ptr @"km_init$kotlin.native.internal.NativePtr", '
                      'ptr @"state_global$kotlin.native.internal.NativePtr", ', used)
        self.assertTrue(used.endswith('ptr @"state_global$kotlinx.cinterop.IntVarOf"], section "llvm.metadata"'))
        body = lines[lines.index('define void @kt_init_all() {'):]
        self.assertIn('  %entry = phi ptr [ @__start_km_init, %0 ], [ %next, %create ]', body)
        self.assertIn('  call void @CallInitGlobalPossiblyLock(ptr %state, ptr %init)', body)
        self.assertEqual(states(body), ['drv$C:/src/drv.kt'])
        self.assertLess(body.index('own:'), body.index('  call void @CallInitGlobalPossiblyLock('
                                                       'ptr @"state_global$drv$C:/src/drv.kt", '
                                                       'ptr @"kfun:drv.$init_global$drv.kt#internal")'))

    def test_objects_of_the_cinterop_packages(self):
        # the companion of a C struct, when the .def file's package is given
        lines = kn.add_init_all(LIBRARY_IR, 'drv', packages=['dev'])
        self.assertIn('km_init$dev.point', [l.split('"')[1] for l in lines if l.startswith('@"km_init$')])

    def test_no_table_without_library_objects(self):
        lines = kn.add_init_all(IR, 'loop')
        self.assertEqual(lines[0], 'define void @kt_init_all() {')
        self.assertNotIn('km_init', ''.join(lines))

    def test_calls_with_the_class_in_the_table(self):
        # Kotlin/Native 2.5: the class is the third field of an entry and the third argument of the call
        ir = LIBRARY_IR.replace('@CallInitGlobalPossiblyLock(', '@kmicro_init_global(').replace(
            '.$init_global#internal")\n', '.$init_global#internal", ptr noundef @"kclass:any")\n')
        lines = kn.add_init_all(ir, 'drv')
        self.assertIn('ptr @"kfun:kotlin.ranges.UIntRange.$init_global#internal", ptr @"kclass:any" }, ',
                      ''.join(lines))
        self.assertIn('  call void @kmicro_init_global(ptr %state, ptr %init, ptr %class)', lines)

    def test_def_package(self):
        d = Path(__file__).resolve().parents[2] / 'build/unit/init_all'
        d.mkdir(parents=True, exist_ok=True)
        (d / 'board.def').write_text('headers = board.h\npackage = hw.board\n', encoding='utf-8')
        (d / 'plain.def').write_text('headers = plain.h\n', encoding='utf-8')
        self.assertEqual(kn.def_package(d / 'board.def'), 'hw.board')
        self.assertEqual(kn.def_package(d / 'plain.def'), 'plain')

    def test_function_shape(self):
        lines = kn.add_init_all(IR, 'loop', 'boot_init')
        self.assertEqual(lines[0], 'define void @boot_init() {')
        self.assertEqual(lines[-2:], ['  ret void', '}'])

    def test_unknown_package(self):
        with self.assertRaises(SystemExit) as e:
            kn.add_init_all(IR, 'lop')
        self.assertIn('no Kotlin code in package lop', str(e.exception))


if __name__ == '__main__':
    unittest.main()

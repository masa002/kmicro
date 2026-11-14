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
      + init('kotlin.collections.ArrayList', 'kotlin.collections.ArrayList.$init_global#internal')
      + init('cfg.Settings', 'cfg.Settings.$init_global#internal')
      + 'define void @"kfun:#main(){}"() {\n'
      + init('<root>$C:/src/main.kt', '$init_global$main.kt#internal')
      + ''.join(init(n, n + '.$init_global#internal') for n in ROOT_OBJECTS)
      + STRING % (1, 0, 0, 1, 0, 'zeroinitializer') + STRING % (2, 6, 98404, 0, 6, r'c"c\00f\00g\00"')
      + ''.join(kclass(n, '@1', private=n == 'hidden') for n in ROOT_OBJECTS) + kclass('cfg.Settings', '@2'))


def states(lines):
    return [l.split('"state_global$')[1].split('"')[0] for l in lines if 'state_global' in l]


class InitAll(unittest.TestCase):
    def test_files_objects_and_sub_packages(self):
        self.assertEqual(states(kn.add_init_all(IR, 'loop')),
                         ['loop$C:/src/loop.kt', 'loop.Loop', 'loop.Loop.Companion', 'loop.io$C:/src/io.kt',
                          'loop.io.Uart'])

    def test_sub_package_alone(self):
        self.assertEqual(states(kn.add_init_all(IR, 'loop.io')), ['loop.io$C:/src/io.kt', 'loop.io.Uart'])

    def test_root_package(self):
        self.assertEqual(states(kn.add_init_all(IR, '')), ['<root>$C:/src/main.kt', *sorted(ROOT_OBJECTS)])

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

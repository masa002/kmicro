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


IR = ('define void @"kfun:loop#step(){}"() {\n'
      + init('loop$C:/src/loop.kt', 'loop.$init_global$loop.kt#internal')
      + init('loop.Loop', 'loop.Loop.$init_global#internal')
      + init('loop.Loop.Companion', 'loop.Loop.Companion.$init_global#internal')
      + init('loop.io$C:/src/io.kt', 'loop.io.$init_global$io.kt#internal')
      + init('loop.io.Uart', 'loop.io.Uart.$init_global#internal')
      + init('loopy.Other', 'loopy.Other.$init_global#internal')
      + init('kotlin.collections.ArrayList', 'kotlin.collections.ArrayList.$init_global#internal')
      + 'define void @"kfun:#main(){}"() {\n'
      + init('<root>$C:/src/main.kt', '$init_global$main.kt#internal')
      + init('Registry', 'Registry.$init_global#internal'))


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
        self.assertEqual(states(kn.add_init_all(IR, '')), ['<root>$C:/src/main.kt', 'Registry'])

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

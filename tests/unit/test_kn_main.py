"""toolchain/kn.py add_kotlin_main(): the C name kmicro_kotlin_main for the program's `fun main()` (IR excerpts, no
compiler needed).

python -m unittest discover -s tests/unit
"""
import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'toolchain'))
import kn  # noqa: E402

STDLIB = 'define void @"kfun:kotlin.io#println(kotlin.Any?){}"(ptr %0) {\n'


def main_ir(package='', args=False):
    a = 'kotlin.Array<kotlin.String>' if args else ''
    return STDLIB + f'define void @"kfun:{package}#main({a}){{}}"({"ptr %0" if args else ""}) {{\n'


def suspend_main_ir(package='', params=''):
    return (f'define ptr @"kfun:{package}#main#suspend({params}kotlin.coroutines.Continuation<kotlin.Unit>){{}}'
            'kotlin.Any"(ptr %0, ptr %1) #9 {\n')


class KotlinMain(unittest.TestCase):
    def test_root_package(self):
        self.assertEqual(kn.add_kotlin_main(main_ir()), ['@kmicro_kotlin_main = alias void (), ptr @"kfun:#main(){}"'])

    def test_package(self):
        self.assertEqual(kn.add_kotlin_main(main_ir('app.demo')),
                         ['@kmicro_kotlin_main = alias void (), ptr @"kfun:app.demo#main(){}"'])

    def test_args_get_an_empty_array(self):
        lines = kn.add_kotlin_main(main_ir('app', args=True))
        self.assertEqual(lines[0], 'define void @kmicro_kotlin_main() uwtable {')
        self.assertIn('call void @"kfun:app#main(kotlin.Array<kotlin.String>){}"(ptr @theEmptyArray)', lines[1])

    def test_no_main(self):
        self.assertEqual(kn.add_kotlin_main(STDLIB), [])
        with self.assertRaises(SystemExit) as e:
            kn.add_kotlin_main(STDLIB, required=True)
        self.assertIn('no `fun main()`', str(e.exception))

    def test_several_mains(self):
        ir = main_ir('a') + main_ir('b')
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(kn.add_kotlin_main(ir), [])
        self.assertIn('several places (a, b)', err.getvalue())
        with self.assertRaises(SystemExit):
            kn.add_kotlin_main(ir, required=True)

    def test_suspend_main_is_refused(self):
        ir = STDLIB + suspend_main_ir()
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(kn.add_kotlin_main(ir), [])
        self.assertIn('warning: `suspend fun main()` in package <root>: entry point can not be a suspend function',
                      err.getvalue())
        with self.assertRaises(SystemExit) as e:
            kn.add_kotlin_main(ir, required=True)
        self.assertIn('--main: `suspend fun main()` in package <root>', str(e.exception))

    def test_suspend_main_beside_a_plain_main(self):
        ir = main_ir('app') + suspend_main_ir('jobs', 'kotlin.Array<kotlin.String>;')
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(kn.add_kotlin_main(ir, required=True),
                             ['@kmicro_kotlin_main = alias void (), ptr @"kfun:app#main(){}"'])
        self.assertIn('warning: `suspend fun main()` in package jobs', err.getvalue())

    def test_suspend_function_that_is_no_entry_point(self):
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(kn.add_kotlin_main(STDLIB + suspend_main_ir(params='kotlin.Int;')), [])
        self.assertEqual(err.getvalue(), '')


if __name__ == '__main__':
    unittest.main()

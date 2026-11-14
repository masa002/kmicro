"""tools/missing_natives.py --ir: the functions an IR file declares, and a file that declares none. No compiler
needed.

usage: python -m unittest discover -s tests/unit
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
import missing_natives  # noqa: E402

MODULE = '''target datalayout = "e-m:e-p:32:32-Fi8-i64:64-v128:64:128-a:0:32-n32-S64"

define void @"kfun:#main(){}"() {
  ret void
}

declare void @llvm.memset.p0.i32(ptr, i8, i32, i1)
declare ptr @__cxa_begin_catch(ptr)
declare ptr @AllocInstance(ptr, ptr)
declare zeroext i1 @"Kotlin_Char_isISOControl"(i16 zeroext)
'''


class DeclaredFunctions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def ir(self, name, text):
        path = Path(self.tmp.name) / name
        path.write_text(text, encoding='utf-8')
        return path

    def test_declared_functions(self):
        m4 = self.ir('m4.ll', MODULE)
        self.assertEqual(missing_natives.declared_functions([m4]), {
            'AllocInstance': (('', 'ptr', (('', 'ptr'), ('', 'ptr'))), m4),
            'Kotlin_Char_isISOControl': (('zeroext', 'i1', (('zeroext', 'i16'),)), m4)})

    def test_a_file_that_declares_no_function_is_an_error(self):
        m4 = self.ir('m4.ll', MODULE)
        for name, text in (('empty.ll', ''), ('notes.ll', 'this is not LLVM IR\n'),
                           ('cut.ll', MODULE[:MODULE.index('declare ptr @AllocInstance')])):
            bad = self.ir(name, text)
            with self.assertRaises(SystemExit) as e:
                missing_natives.declared_functions([m4, bad])
            self.assertEqual(e.exception.code, f'missing_natives: {bad} declares no function: it is not the IR of a '
                                               'compiled Kotlin program')

    def test_check_stops_before_the_report(self):
        empty = self.ir('empty.ll', '')
        with mock.patch.object(sys, 'argv', ['missing_natives.py', '--check', '--ir', str(empty)]), \
                mock.patch.object(missing_natives, 'stdlib_natives', side_effect=AssertionError('not reached')), \
                self.assertRaises(SystemExit) as e:
            missing_natives.main()
        self.assertIn('declares no function', e.exception.code)


if __name__ == '__main__':
    unittest.main()

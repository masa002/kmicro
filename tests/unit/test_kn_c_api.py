"""toolchain/kn.py --c-api type checks: a C prototype must match the Kotlin function it becomes an alias of, and only
types with a plain C equivalent may cross (the clang part is skipped without the LLVM of Kotlin/Native).

python -m unittest discover -s tests/unit
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'toolchain'))
import kn  # noqa: E402
import paths  # noqa: E402

HAVE_CLANG = (lambda p: p is not None and (p / f'clang{paths.EXE}').exists())(
    paths._find(paths.llvm.env, paths.llvm.patterns, paths.llvm.what, paths.llvm.tool))

IR = '''
define i32 @"kfun:app#hello(kotlin.Int){}kotlin.Int"(i32 %0) {
define ptr @"kfun:app#version(){}kotlin.String"(ptr %0) {
define void @"kfun:app#log(kotlin.String){}"(ptr %0) {
define void @"kfun:app#maybe(kotlin.Int?){}"(ptr %0) {
define signext i8 @"kfun:app#small(kotlin.Byte){}kotlin.Byte"(i8 signext %0) {
define void @"kfun:app#fill(kotlinx.cinterop.CPointer<kotlinx.cinterop.ByteVar>?;kotlin.UInt){}"(ptr %0, i32 %1) {
define zeroext i1 @"kfun:app#ready(){}kotlin.Boolean"() {
'''


def sig(text):
    """'i32 (i32, ptr)' -> ir_signature()"""
    ret, params = text.rsplit(' (', 1)
    return kn.ir_signature(ret, params.rstrip(')'))


class Check(unittest.TestCase):
    def errors(self, cname, c=None):
        k = kn.kotlin_functions(IR, 'app')[kn.camel(cname)][0]
        return kn.check_c_signature(cname, k[0], k[3], sig(c) if c else None)

    def test_matching(self):
        self.assertEqual(self.errors('hello', 'i32 (i32 noundef)'), [])
        self.assertEqual(self.errors('fill', 'void (ptr noundef, i32 noundef)'), [])
        self.assertEqual(self.errors('ready', 'zeroext i1 ()'), [])
        self.assertEqual(self.errors('small', 'signext i8 (i8 noundef signext)'), [])
        self.assertEqual(self.errors('ready', 'zeroext i1 (...)'), [])          # `bool ready();`

    def test_wrong_prototype(self):
        e = self.errors('hello', 'double (ptr noundef, i64 noundef)')
        self.assertEqual(len(e), 1)
        self.assertIn('does not match Kotlin hello(kotlin.Int): kotlin.Int', e[0])
        self.assertIn('C: double (ptr, i64); Kotlin: i32 (i32)', e[0])

    def test_signedness(self):
        e = self.errors('small', 'zeroext i8 (i8 noundef zeroext)')       # `char small(char)`: unsigned on Arm
        self.assertIn('signed/unsigned differs', e[0])

    def test_object_types_rejected(self):
        self.assertIn('version returns kotlin.String', self.errors('version')[0])
        self.assertIn('log takes kotlin.String', self.errors('log')[0])
        self.assertIn('maybe takes kotlin.Int?', self.errors('maybe')[0])

    def test_add_c_aliases_stops(self):
        with self.assertRaises(SystemExit) as e:
            kn.add_c_aliases(IR, ['hello', 'version'], 'app')
        self.assertIn('version returns kotlin.String', str(e.exception))

    def test_kotlin_signature(self):
        self.assertEqual(kn.kotlin_signature('kfun:a.b#f(kotlin.collections.Map<kotlin.String,kotlin.Int>;'
                                             'kotlin.Int){}kotlin.Unit'),
                         (['kotlin.collections.Map<kotlin.String,kotlin.Int>', 'kotlin.Int'], 'kotlin.Unit'))
        self.assertEqual(kn.kotlin_signature('kfun:#main(){}'), ([], ''))


@unittest.skipUnless(HAVE_CLANG, 'no clang (the LLVM of Kotlin/Native)')
class ClangLowering(unittest.TestCase):
    def test_c_signatures(self):
        with tempfile.TemporaryDirectory() as d:
            h = Path(d) / 'api.h'
            h.write_text('#include <stdint.h>\n#include <stdbool.h>\ndouble hello(const char *who, int64_t n);\n'
                         'bool ready(void);\nchar small(char c);\nvoid old();\n')
            s = kn.c_signatures([h], ['hello', 'ready', 'small', 'old'], work=d)
        self.assertEqual(s['hello'], (('double', ''), [('ptr', ''), ('i64', '')]))
        self.assertEqual(s['ready'], (('i1', 'zeroext'), []))
        self.assertEqual(s['small'], (('i8', 'zeroext'), [('i8', 'zeroext')]))
        self.assertEqual(s['old'], (('void', ''), [('...', '')]))


if __name__ == '__main__':
    unittest.main()

"""toolchain/kn.py check_regex(): kbuild's warning for a program that uses Regex (canned IR, no compiler needed).

python -m unittest discover -s tests/unit
"""
import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'toolchain'))
import kn  # noqa: E402

# What every program with String.toDouble() has: the Regex engine, and the hexadecimal parser of the stdlib that
# uses it. retarget.py replaces that parser, so nothing here links the engine.
ENGINE = '''define internal void @"kfun:kotlin.native.internal.HexStringParser.parseMantissa#internal"(ptr %0) {
  %2 = call ptr @"kfun:kotlin.text#toRegex__at__kotlin.String(){}kotlin.text.Regex"(ptr @7)
}
define ptr @"kfun:kotlin.text#toRegex__at__kotlin.String(){}kotlin.text.Regex"(ptr %0) {
  %2 = call ptr @"kfun:kotlin.text.Regex#<init>(kotlin.String){}"(ptr %1, ptr %0)
}
define ptr @"kfun:kotlin.text.Regex#<init>(kotlin.String){}"(ptr %0, ptr %1) {
  %3 = call ptr @"kfun:kotlin.text.regex.Pattern.Companion#compile(kotlin.String){}kotlin.text.regex.Pattern"(ptr %1)
}
define ptr @"kfun:kotlin.text.Regex#find(kotlin.CharSequence;kotlin.Int){}kotlin.text.MatchResult?"(ptr %0) {
  %2 = call ptr @"kfun:kotlin.text.regex.MatchResultImpl#<init>(kotlin.text.Regex){}"(ptr %0)
}
define double @"kfun:app#parse(kotlin.String){}kotlin.Double"(ptr %0) {
  %2 = call double @"kfun:kotlin.text#toDouble__at__kotlin.String(){}kotlin.Double"(ptr %0)
}
'''

PROGRAM = ENGINE + '''define ptr @"kfun:app#firstNumber(kotlin.String){}kotlin.String?"(ptr %0) {
  %2 = call ptr @"kfun:kotlin.text.Regex#<init>(kotlin.String){}"(ptr %1, ptr @8)
}
define ptr @"kfun:app.Csv#clean(kotlin.String){}kotlin.String"(ptr %0, ptr %1) {
  %3 = call ptr @"kfun:kotlin.text#replace__at__kotlin.CharSequence(kotlin.text.Regex;kotlin.String){}kotlin.String"(ptr %1)
}
define ptr @"kfun:kotlin.text#replace__at__kotlin.CharSequence(kotlin.text.Regex;kotlin.String){}kotlin.String"(ptr %0) {
  %4 = call ptr @"kfun:kotlin.text.Regex#replace(kotlin.CharSequence;kotlin.String){}kotlin.String"(ptr %1, ptr %0)
}
define void @"kfun:app#options(){}"() {
  %1 = load ptr, ptr @"kvar:kotlin.text.RegexOption#IGNORE_CASE", align 4
}
'''


def warning(ir):
    with contextlib.redirect_stderr(io.StringIO()) as err:
        kn.check_regex(ir)
    return err.getvalue()


class Regex(unittest.TestCase):
    def test_names_the_program_functions_that_use_regex(self):
        self.assertEqual([kn.kotlin_name(s) for s in kn.regex_users(PROGRAM)],
                         ['app.firstNumber(String)', 'app.Csv.clean(String)'])
        text = warning(PROGRAM)
        self.assertTrue(text.startswith('kmicro: warning: app.firstNumber(String), app.Csv.clean(String) use Regex'))
        self.assertIn('--size', text)

    def test_number_parsing_alone_does_not_warn(self):
        self.assertEqual(kn.regex_users(ENGINE), [])
        self.assertEqual(warning(ENGINE), '')


if __name__ == '__main__':
    unittest.main()

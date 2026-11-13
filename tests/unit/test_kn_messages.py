"""toolchain/kn.py compiler_messages(): which kotlinc-native messages kbuild shows (canned compiler output).

python -m unittest discover -s tests/unit
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'toolchain'))
import kn  # noqa: E402

NOTICE = ('warning: target linux_arm32_hfp is deprecated and will be removed soon. '
          'See: https://kotl.in/native-targets-tiers')

WARNING = f'''{NOTICE}
app.kt:3:24: warning: unchecked cast of 'List<Any>' to 'List<String>'.
    val strings = list as List<String>
                       ^^^^^^^^^^^^^^^
'''

TWO_ERRORS = f'''{NOTICE}
dep.kt:2:16: error: initializer type mismatch: expected 'Int', actual 'String'.
    val n: Int = "1"
               ^
dep.kt:3:19: error: 'fun String.toUpperCase(): String' is deprecated. Use uppercase() instead.
    println("abc".toUpperCase() + n)
                  ^^^^^^^^^^^
'''

API_CPP = f'''{NOTICE}
error: compilation failed: The C:\\llvm/bin/clang++ command returned non-zero exit code: 1.
output:
C:\\b\\tmp\\api.cpp:103:26: error: expected ')'
  103 |       const char* (*name with spaces)();
                          ^
C:\\b\\tmp\\api.cpp:103:19: note: to match this '('
  103 |       const char* (*name with spaces)();
                   ^
1 error generated.

 * Compiler version: 2.4.21
 * Output kind: STATIC

exception: org.jetbrains.kotlin.konan.KonanExternalToolFailure: The C:\\llvm/bin/clang++ command failed.
output:
C:\\b\\tmp\\api.cpp:103:26: error: expected ')'
  103 |       const char* (*name with spaces)();
      |                          ^
1 error generated.
\tat org.jetbrains.kotlin.konan.exec.Command.handleExitCode(ExecuteCommand.kt:133)
\tat org.jetbrains.kotlin.konan.exec.Command.execute(ExecuteCommand.kt:89)
'''


class Messages(unittest.TestCase):
    def test_warning_with_source_and_caret(self):
        errors, warnings = kn.compiler_messages(WARNING)
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn('unchecked cast', warnings[0])
        self.assertIn('val strings = list as List<String>', warnings[0])
        self.assertIn('^^^', warnings[0])

    def test_target_notice_hidden(self):
        self.assertEqual(kn.compiler_messages(NOTICE + '\n'), ([], []))

    def test_every_error_and_deprecation_kept(self):
        errors, _ = kn.compiler_messages(TWO_ERRORS)
        self.assertEqual(len(errors), 2)
        self.assertIn('is deprecated. Use uppercase()', errors[1])
        self.assertIn('println("abc".toUpperCase() + n)', errors[1])

    def test_c_adapter_error_shown_once_with_hint(self):
        errors, _ = kn.compiler_messages(API_CPP)
        text = '\n'.join(errors)
        self.assertEqual(text.count("api.cpp:103:26: error: expected ')'"), 1)
        self.assertIn('(*name with spaces)', text)
        self.assertNotIn('\tat ', text)
        self.assertEqual(errors[-1], kn.API_CPP_HINT)

    def test_c_adapter_warnings_hidden(self):
        out = 'C:\\b\\tmp\\api.cpp:12:3: warning: unused variable\n  12 | int x;\n'
        self.assertEqual(kn.compiler_messages(out), ([], []))


if __name__ == '__main__':
    unittest.main()

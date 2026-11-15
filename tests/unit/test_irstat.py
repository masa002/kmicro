# Copyright 2026 the kmicro authors (NOTICE).
# SPDX-License-Identifier: Apache-2.0
"""tools/irstat.py on a small module written here: Kotlin names with their parameter lists, overloads counted apart,
debug records not counted. No compiler needed.

python -m unittest discover -s tests/unit
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

MODULE = '''@"kvar:app#limit" = global i32 3
@plain = external global i32
@"kvar:app#state" = internal thread_local global i32 0

define i32 @"kfun:app#area(kotlin.Int){}kotlin.Int"(i32 %0) !dbg !7 {
    #dbg_declare(ptr %0, !9, !DIExpression(), !10)
  %2 = add i32 %0, 1
  ret i32 %2
}

define double @"kfun:app#area(kotlin.Double){}kotlin.Double"(double %0) {
entry:
  %2 = fadd double %0, 1.0
  %3 = fadd double %2, 1.0
  ret double %3
}

define void @plain_c() {
  ret void
}

declare void @"kfun:app#log(kotlin.String){}"(ptr)
declare ptr @AllocInstance(ptr, ptr)
declare void @llvm.memset.p0.i32(ptr, i8, i32, i1)
'''


class Irstat(unittest.TestCase):
    def run_tool(self, *options):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'm.ll').write_text(MODULE, encoding='utf-8')
            r = subprocess.run([sys.executable, str(ROOT / 'tools/irstat.py'), str(Path(d) / 'm.ll'), *options],
                               capture_output=True, encoding='utf-8')
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.splitlines()

    def section(self, lines, title):
        """The lines under a title, up to the next empty line."""
        rest = lines[lines.index(title) + 1:]
        return [line.strip() for line in rest[:rest.index('') if '' in rest else None]]

    def test_kotlin_names_keep_their_parameters_and_overloads_stay_apart(self):
        lines = self.run_tool('--list-defs', '--list-decls')
        self.assertIn('defined functions: 3   instructions: 6', lines)      # the debug record is no instruction
        self.assertIn('declared functions: 3 (llvm intrinsics 1, external 2)', lines)
        self.assertIn('external globals: 1   defined globals: 2   thread_local: 1', lines)
        self.assertIn('thread_local globals: kvar:app#state', lines)
        self.assertEqual(self.section(lines, 'external functions (the runtime contract):'),
                         ['AllocInstance', 'kfun:app#log(kotlin.String){}'])
        self.assertEqual(self.section(lines, 'largest defined functions:'),
                         ['3  kfun:app#area(kotlin.Double){}kotlin.Double', '2  kfun:app#area(kotlin.Int){}kotlin.Int',
                          '1  plain_c'])
        self.assertEqual(self.section(lines, 'all defined functions:'),
                         ['kfun:app#area(kotlin.Int){}kotlin.Int', 'kfun:app#area(kotlin.Double){}kotlin.Double',
                          'plain_c'])
        self.assertEqual(self.section(lines, 'all declared functions:'),
                         ['kfun:app#log(kotlin.String){}', 'AllocInstance', 'llvm.memset.p0.i32'])


if __name__ == '__main__':
    unittest.main()

# Copyright 2026 the kmicro authors (NOTICE).
# SPDX-License-Identifier: Apache-2.0
"""tools/symbolize.py: names for trace addresses from a synthetic nm listing (no tools needed), then, with the xPack
GCC, on an image built here from symbolize_probe.c: the call before a return address, the inlined levels, a log file,
UTF-8 text, a function without a size, the exit codes, and the image in a folder that the host's ANSI code page
cannot name (tools/frames.py too).

python -m unittest discover -s tests/unit
"""
import io
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'toolchain'))
sys.path.insert(0, str(ROOT / 'tools'))
import binutils  # noqa: E402
import paths  # noqa: E402
import symbolize  # noqa: E402

HAVE_GCC = paths._find(paths.arm_gcc.env, paths.arm_gcc.patterns, paths.arm_gcc.what) is not None

NM = '\n'.join([        # nm -n -S --format=sysv
    '', '', 'Symbols from image.elf:', '',
    'Name                  Value   Class        Type         Size     Line  Section', '',
    '__sf                |        |   w  |            NOTYPE|        |     |*UND*',
    'Reset_Handler       |08000000|   T  |              FUNC|00000010|     |.text',
    'kfun:app#top(kotlin.Int){}kotlin.Int|08000010|   T  |              FUNC|00000020|     |.text',
    'kfun:app#next(){}   |08000030|   T  |              FUNC|00000004|     |.text',
    'weak_one            |08000034|   W  |              FUNC|00000008|     |.text',
    'some_data           |08000040|   D  |            OBJECT|00000004|     |.data',
    'kfun:app#of(kotlin.Array<out|0:0>){}|08000080|   t  |              FUNC|00000010|     |.text',
    'kclass:app.Box      |08000090|   t  |            OBJECT|00000048|     |.text',
    'no_size             |08000100|   t  |              FUNC|        |     |.text',
    '_etext              |08000200|   T  |            NOTYPE|        |     |.text',
]) + '\n'


class Lookup(unittest.TestCase):
    def setUp(self):
        with mock.patch.object(symbolize.binutils, 'run', return_value=subprocess.CompletedProcess([], 0, NM, '')):
            self.addrs, self.names = symbolize.load('image.elf')

    def name(self, a, exact=False):
        return symbolize.name_of(self.addrs, self.names, a, exact)

    def test_functions_only(self):
        self.assertEqual([n for n, _ in self.names],
                         ['Reset_Handler', 'kfun:app#top(kotlin.Int){}kotlin.Int', 'kfun:app#next(){}', 'weak_one',
                          'kfun:app#of(kotlin.Array<out|0:0>){}', 'kclass:app.Box', 'no_size'])

    def test_return_address_names_the_caller(self):
        # a call that never returns ends top: its return address is next's first instruction
        self.assertEqual(self.name(0x08000030), 'app#top(kotlin.Int){}kotlin.Int+0x20')
        self.assertEqual(self.name(0x08000031), 'app#top(kotlin.Int){}kotlin.Int+0x20')      # the Thumb bit

    def test_fault_address_is_exact(self):
        self.assertEqual(self.name(0x08000030, exact=True), 'app#next(){}+0x0')

    def test_past_the_end_of_a_function(self):
        self.assertEqual(self.name(0x0800003e), '? (after weak_one)')

    def test_before_the_first_function(self):
        self.assertEqual(self.name(0x07ffff00), '?')

    def test_a_function_without_a_size_goes_on_to_the_next_symbol(self):
        self.assertEqual(self.name(0x080001f0), 'no_size+0xf0')
        self.assertEqual(self.name(0x08000300), 'no_size+0x200')         # _etext is no function

    def test_a_log_with_cr_lf_line_ends_keeps_them(self):
        # stdin passes the CR on where the system's line end is LF
        for end in ('\r\n', '\n', ''):
            out = io.StringIO()
            with mock.patch.object(symbolize, 'has_lines', return_value=False):
                symbolize.rewrite(['boot' + end, '    at 0x08000030' + end], 'image.elf', self.addrs, self.names, out)
            self.assertEqual(out.getvalue(), 'boot' + end + '    at 0x08000030  app#top(kotlin.Int){}kotlin.Int+0x20'
                             + (end or '\n'))


@unittest.skipUnless(HAVE_GCC, 'needs the xPack arm-none-eabi-gcc (python toolchain/paths.py)')
class Image(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = ROOT / 'build/unit/symbolize'
        cls.dir.mkdir(parents=True, exist_ok=True)
        cls.elf, cls.stripped = cls.dir / 'probe.elf', cls.dir / 'probe-nodebug.elf'
        subprocess.run([str(paths.gcc_bin('gcc')), '-mcpu=cortex-m4', '-mthumb', '-O2', '-g', '-nostdlib',
                        str(Path(__file__).parent / 'symbolize_probe.c'), '-o', str(cls.elf)], check=True)
        subprocess.run([str(paths.gcc_bin('objcopy')), '--strip-debug', str(cls.elf), str(cls.stripped)], check=True)
        dis = subprocess.run([str(paths.gcc_bin('objdump')), '-d', '--no-show-raw-insn', str(cls.elf)],
                             capture_output=True, text=True, check=True).stdout
        call = next(line for line in dis.splitlines() if 'bl' in line.split() and '<sink>' in line)
        cls.ret = int(call.split(':')[0], 16) + 4               # the return address of the call to sink in top
        nm = subprocess.run([str(paths.gcc_bin('nm')), str(cls.elf)], capture_output=True, text=True).stdout
        cls.after_top = {p[2]: int(p[0], 16) for p in (line.split() for line in nm.splitlines()) if len(p) == 3}

    def run_tool(self, *args, stdin=None):
        r = subprocess.run([sys.executable, str(ROOT / 'tools/symbolize.py'), *map(str, args)], input=stdin,
                           capture_output=True, encoding='utf-8', errors='replace')
        return r.returncode, r.stdout, r.stderr

    def test_call_before_a_noreturn_end(self):
        rc, out, _ = self.run_tool(self.elf, hex(self.ret))
        self.assertEqual(rc, 0)
        self.assertTrue(out.startswith(f'{hex(self.ret)}  top+0x'), out)

    def test_inlined_levels_innermost_first(self):
        _, out, _ = self.run_tool(self.elf, hex(self.ret))
        levels = [line.split()[0] for line in out.splitlines()[1:]]
        self.assertEqual(levels, ['level3', 'level2', 'top'], out)
        self.assertIn('[inlined]', out.splitlines()[1])

    def test_no_lines_without_debug_information(self):
        _, out, _ = self.run_tool(self.stripped, hex(self.ret))
        self.assertEqual(len(out.splitlines()), 1, out)
        self.assertIn('top+0x', out)

    def test_log_file_and_stdin(self):
        log = f'Uncaught Kotlin exception: café 😀\n    at 0x{self.ret:08x}\nafter\n'
        (self.dir / 'log.txt').write_text(log, encoding='utf-8')
        for args, stdin in (((self.elf, self.dir / 'log.txt'), None), ((self.elf,), log)):
            rc, out, err = self.run_tool(*args, stdin=stdin)
            self.assertEqual(rc, 0, err)
            lines = out.splitlines()
            self.assertEqual(lines[0], 'Uncaught Kotlin exception: café 😀')
            self.assertTrue(lines[1].startswith(f'    at 0x{self.ret:08x}  top+0x'), out)
            self.assertEqual(lines[-1], 'after')

    def test_an_assembly_function_without_a_size(self):
        rc, out, err = self.run_tool(self.elf, hex(self.after_top['bare'] + 4), hex(self.after_top['bare'] + 8))
        self.assertEqual(rc, 0, err)
        self.assertEqual([line.split()[1] for line in out.splitlines()], ['bare+0x4', 'bare+0x8'])

    def test_fault_line_names_the_faulting_function(self):
        rc, out, _ = self.run_tool(self.elf, stdin=f'kmicro fault: UsageFault at 0x{self.after_top["_start"]:08x}\n')
        self.assertIn('_start+0x0', out)

    def test_folder_outside_the_ansi_code_page(self):
        # binutils open files through the ANSI code page on Windows; no code page but UTF-8 has these three letters
        there = self.dir / '\u00e9\u8a9e\u0e01'
        there.mkdir(exist_ok=True)
        shutil.copy(self.elf, there / 'probe.elf')
        rc, out, err = self.run_tool(there / 'probe.elf', hex(self.ret))
        self.assertEqual(rc, 0, err)
        self.assertEqual([line.split()[0] for line in out.splitlines()], [hex(self.ret), 'level3', 'level2', 'top'])
        r = subprocess.run([sys.executable, str(ROOT / 'tools/frames.py'), str(there / 'probe.elf'), '--top', '1'],
                           capture_output=True, encoding='utf-8', errors='replace')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stdout, r'largest stack frames of probe\.elf [^\n]*\n +\d+  \w+\n')
        binutils.output('objcopy', there / 'probe.elf', '-O', 'binary', after=['probe.bin'])   # an output file too
        self.assertTrue((there / 'probe.bin').is_file())

    def test_exit_codes(self):
        self.assertEqual(self.run_tool(self.dir / 'missing.elf', '0x1')[0], 1)
        rc, _, err = self.run_tool(Path(__file__).parent / 'symbolize_probe.c', '0x1')      # not an ELF: nm fails
        self.assertEqual(rc, 1, err)
        self.assertIn('nm failed', err)
        self.assertEqual(self.run_tool(self.elf, 'zz')[0], 2)
        self.assertEqual(self.run_tool()[0], 2)


if __name__ == '__main__':
    unittest.main()

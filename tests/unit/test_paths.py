# Copyright 2026 the kmicro authors (NOTICE).
# SPDX-License-Identifier: Apache-2.0
"""toolchain/paths.py: which installed tool version is picked, the `python toolchain/paths.py` check, and the table of
cores (its two tests are skipped when arm-none-eabi-gcc or the LLVM of Kotlin/Native is not installed).

python -m unittest discover -s tests/unit
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'toolchain'))
import paths  # noqa: E402

ENV_VARS = ('KMICRO_KOTLIN_NATIVE', 'KMICRO_LLVM', 'KMICRO_ARM_GCC', 'KMICRO_QEMU', 'KONAN_DATA_DIR')


class VersionChoice(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.saved = paths.HOME, {k: os.environ.pop(k, None) for k in ENV_VARS}
        paths.HOME = self.home

    def tearDown(self):
        paths.HOME = self.saved[0]
        for k, v in self.saved[1].items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v
        self.tmp.cleanup()

    def install(self, *names):
        for n in names:
            (self.home / 'toolchains' / n).mkdir(parents=True)

    def pick(self):
        return paths._find(paths.qemu.env, paths.qemu.patterns, paths.qemu.what, paths.qemu.tool).name

    def test_tested_version_wins(self):
        self.install('xpack-qemu-arm-10.1.0-1', 'xpack-qemu-arm-9.2.4-1', 'xpack-qemu-arm-8.2.6-1')
        self.assertEqual(self.pick(), 'xpack-qemu-arm-9.2.4-1')

    def test_newest_by_number_without_the_tested_one(self):
        self.install('xpack-qemu-arm-9.9.0-1', 'xpack-qemu-arm-10.1.0-1')
        self.assertEqual(self.pick(), 'xpack-qemu-arm-10.1.0-1')

    def test_archive_beside_the_unpacked_folder(self):
        self.install('xpack-qemu-arm-9.2.4-1')
        for archive in ('xpack-qemu-arm-9.2.4-1-win32-x64.zip', 'xpack-qemu-arm-9.2.4-1-linux-x64.tar.gz',
                        'xpack-qemu-arm-10.1.0-1-darwin-arm64.tar.gz'):
            (self.home / 'toolchains' / archive).write_bytes(b'')
        self.assertEqual(self.pick(), 'xpack-qemu-arm-9.2.4-1')

    def test_archive_alone_is_no_install(self):
        (self.home / 'toolchains').mkdir()
        (self.home / 'toolchains/xpack-qemu-arm-9.2.4-1-win32-x64.zip').write_bytes(b'')
        self.assertIsNone(paths._find(paths.qemu.env, paths.qemu.patterns, paths.qemu.what, paths.qemu.tool))

    def test_version_key(self):
        names = ['llvm-21-x86_64-windows-essentials-99', 'llvm-21-x86_64-windows-essentials-150',
                 'llvm-19-x86_64-windows-essentials-200']
        self.assertEqual(max(names, key=paths.version_key), 'llvm-21-x86_64-windows-essentials-150')

    def test_versions_file(self):
        t = paths.tested_versions()
        self.assertEqual(t['kotlin-native'][0], paths.KOTLIN_NATIVE_VERSION)
        for tool in ('llvm', 'arm-gcc', 'qemu', 'java'):
            self.assertIn(tool, t)

    def test_llvm_kotlin_native_downloads(self):
        # the essentials build on Windows and Linux, the dev build on macOS
        for name in ('llvm-21-x86_64-windows-essentials-150', 'llvm-21-x86_64-linux-essentials-116',
                     'llvm-21-aarch64-macos-dev-97', 'llvm-21-x86_64-macos-dev-83'):
            self.assertTrue(paths._tested('llvm', self.home / '.konan/dependencies' / name / 'bin'), name)

    def pick_llvm(self):
        return paths._find(paths.llvm.env, paths.llvm.patterns, paths.llvm.what, paths.llvm.tool)

    def test_llvm_under_konan_data_dir(self):
        # KONAN_DATA_DIR moves the downloads of Kotlin/Native away from ~/.konan
        data = self.home / 'data'
        in_data = data / 'dependencies/llvm-21-x86_64-windows-essentials-150/bin'
        in_home = self.home / '.konan/dependencies/llvm-21-x86_64-windows-essentials-150/bin'
        in_data.mkdir(parents=True)
        self.assertIsNone(self.pick_llvm())
        os.environ['KONAN_DATA_DIR'] = str(data)
        self.assertEqual(self.pick_llvm(), in_data)
        in_home.mkdir(parents=True)
        self.assertEqual(self.pick_llvm(), in_data)            # before the home folder
        os.environ['KONAN_DATA_DIR'] = str(self.home / 'empty')
        self.assertEqual(self.pick_llvm(), in_home)


class Check(unittest.TestCase):
    def run_check(self, **env):
        e = {k: v for k, v in os.environ.items() if k not in ENV_VARS}
        e.update(env)
        return subprocess.run([sys.executable, str(ROOT / 'toolchain/paths.py')], capture_output=True, text=True,
                              errors='replace', env=e)

    def test_missing_tool_exits_1_and_names_it(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'llvm-root').mkdir()
            r = self.run_check(KMICRO_LLVM=str(Path(d) / 'llvm-root'))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('MISSING', r.stdout)
        self.assertIn('clang', r.stdout)

    def test_unset_tool_not_found(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.run_check(KMICRO_QEMU=str(Path(d) / 'nothing-here'))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('KMICRO_QEMU', r.stdout + r.stderr)

    def test_not_found_names_konan_data_dir(self):
        with tempfile.TemporaryDirectory() as d:
            home = {'USERPROFILE' if paths.WINDOWS else 'HOME': str(Path(d) / 'home')}
            r = self.run_check(KONAN_DATA_DIR=str(Path(d) / 'data'), **home)
        llvm = [line for line in r.stdout.splitlines() if line.startswith('LLVM')]
        self.assertEqual(len(llvm), 1, r.stdout + r.stderr)
        self.assertIn('NOT FOUND', llvm[0])
        self.assertIn(str(Path(d) / 'data' / 'dependencies'), llvm[0])
        self.assertIn('(KONAN_DATA_DIR)', llvm[0])


class Cores(unittest.TestCase):
    def each_core(self):
        """Every core of the table, as the core of this process while the caller looks at it."""
        saved = os.environ.get('KMICRO_CPU')
        try:
            for cpu in paths.CORES:
                os.environ['KMICRO_CPU'] = cpu
                yield cpu
        finally:
            os.environ.pop('KMICRO_CPU', None)
            if saved is not None:
                os.environ['KMICRO_CPU'] = saved

    @unittest.skipUnless(paths._find(paths.arm_gcc.env, paths.arm_gcc.patterns, paths.arm_gcc.what), 'needs GCC')
    def test_every_core_has_its_newlib_and_libgcc(self):
        for cpu in self.each_core():
            self.assertTrue((paths.newlib_lib() / 'libc_nano.a').is_file(), f'{cpu}: {paths.newlib_lib()}')
            self.assertTrue(paths.libgcc_ok(), f'{cpu}: libgcc in {paths.multilib()}')

    @unittest.skipUnless(paths._find(paths.llvm.env, paths.llvm.patterns, paths.llvm.what), 'needs LLVM')
    def test_the_flags_give_the_fpu_and_mve_the_entry_stands_for(self):
        # -mcpu alone turns on what the full core has: an entry without the FPU or without MVE has to take it away
        for cpu in self.each_core():
            r = subprocess.run([str(paths.clang()), *paths.target_flags(), '-dM', '-E', '-x', 'c', '-'], input='',
                               capture_output=True, text=True, errors='replace')
            self.assertEqual(r.returncode, 0, f'{cpu}: {r.stderr}')
            macros = set(re.findall(r'^#define (\w+)', r.stdout, re.M))
            fpu = '-mfloat-abi=hard' in paths.target_flags()
            self.assertEqual('__ARM_FP' in macros, fpu, cpu)
            self.assertEqual('__ARM_PCS_VFP' in macros, fpu, cpu)           # the hard-float calling convention
            self.assertEqual('__ARM_FEATURE_MVE' in macros, cpu in ('cortex-m55', 'cortex-m85'), cpu)


class ArgPathError(unittest.TestCase):
    """arg_path() as on Windows with the code page 1252, on a volume without 8.3 short names: what the error advises
    for a path that Java cannot take."""
    NAME, FOLDER = 'give it, or the file it is named after, a name', 'move it to a folder'
    RELATIVE = 'run the build from inside the folder'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = paths.WINDOWS, paths._ansi_codepage, paths._short_path, os.getcwd()
        paths.WINDOWS, paths._ansi_codepage, paths._short_path = True, lambda: 'cp1252', lambda p: None
        self.dir = Path(self.tmp.name).resolve() / 'テスト'
        self.dir.mkdir()

    def tearDown(self):
        paths.WINDOWS, paths._ansi_codepage, paths._short_path, cwd = self.saved
        os.chdir(cwd)
        self.tmp.cleanup()

    def error(self, path, **kw):
        with self.assertRaises(SystemExit) as e:
            paths.arg_path(path, **kw)
        self.assertIn('cannot be passed to the tool (cp1252 only)', str(e.exception))
        return str(e.exception)

    def test_folder_name(self):
        msg = self.error(self.dir / 'x.def')
        self.assertIn(self.FOLDER, msg)
        self.assertIn(self.RELATIVE, msg)
        self.assertNotIn(self.NAME, msg)
        os.chdir(self.dir)
        self.assertEqual(paths.arg_path(self.dir / 'x.def'), 'x.def')

    def test_no_relative_path_is_tried(self):
        os.chdir(self.dir)
        msg = self.error(self.dir / 'x.def', relative=False)
        self.assertIn(self.FOLDER, msg)
        self.assertNotIn(self.RELATIVE, msg)

    def test_file_name(self):
        os.chdir(self.dir.parent)
        for path in (self.dir.parent / 'build' / 'カフェ', Path('カフェ.def')):
            msg = self.error(path)
            self.assertIn(self.NAME, msg)
            self.assertNotIn(self.FOLDER, msg)
        both = self.error(self.dir / 'カフェ.def')
        self.assertIn(self.NAME, both)
        self.assertIn(self.FOLDER, both)
        os.chdir(self.dir)
        self.assertNotIn(self.FOLDER, self.error(self.dir / 'カフェ.def'))


class BugReportForm(unittest.TestCase):
    def test_the_form_offers_every_core(self):
        form = (ROOT / '.github/ISSUE_TEMPLATE/bug_report.yml').read_text(encoding='utf-8')
        self.assertEqual(sorted(re.findall('^ +- (cortex-[a-z0-9-]+)', form, re.M)), sorted(paths.CORES))


if __name__ == '__main__':
    unittest.main()

"""toolchain/paths.py: which installed tool version is picked, and the `python toolchain/paths.py` check.

python -m unittest discover -s tests/unit
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'toolchain'))
import paths  # noqa: E402

ENV_VARS = ('KMICRO_KOTLIN_NATIVE', 'KMICRO_LLVM', 'KMICRO_ARM_GCC', 'KMICRO_QEMU')


class VersionChoice(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.saved = paths.HOME, {k: os.environ.pop(k, None) for k in ENV_VARS}
        paths.HOME = self.home

    def tearDown(self):
        paths.HOME = self.saved[0]
        for k, v in self.saved[1].items():
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
        # konan.properties llvmHome.<host>: the essentials build on Windows, the dev build on Linux and macOS
        for name in ('llvm-21-x86_64-windows-essentials-150', 'llvm-21-x86_64-linux-dev-116',
                     'llvm-21-aarch64-macos-dev-97', 'llvm-21-x86_64-macos-dev-83'):
            self.assertTrue(paths._tested('llvm', self.home / '.konan/dependencies' / name / 'bin'), name)


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


if __name__ == '__main__':
    unittest.main()

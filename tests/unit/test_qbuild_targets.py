# Copyright 2026 the kmicro authors (NOTICE).
# SPDX-License-Identifier: Apache-2.0
"""tools/qbuild.py: which core runs on which QEMU target (no compiler needed), and the stubs of missing runtime
natives, assembled for every core (skipped when LLVM is not installed).

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
sys.path.insert(0, str(ROOT / 'tools'))
import paths  # noqa: E402
import qbuild  # noqa: E402


def run(*options):
    with tempfile.TemporaryDirectory() as d:
        return subprocess.run([sys.executable, ROOT / 'tools/qbuild.py', Path(d) / 'probe.elf',
                               Path(__file__).parent / 'startup_probe.c', *options], capture_output=True, text=True,
                              encoding='utf-8')


@unittest.skipUnless(paths._find(paths.llvm.env, paths.llvm.patterns, paths.llvm.what), 'needs LLVM')
class Stubs(unittest.TestCase):
    def test_the_stubs_assemble_for_every_core(self):
        code = ('import sys, pathlib; sys.path[:0] = [sys.argv[1] + "/toolchain", sys.argv[1] + "/tools"]\n'
                'import qbuild\n'
                's = pathlib.Path(sys.argv[2], "autostubs.s")\n'
                'qbuild.write_stubs(s, ["Kotlin_Example_missing", "Kotlin_Example_other"])\n'
                'qbuild.compile_one(s, s.with_suffix(".o"), [])\n')
        for cpu in paths.CORES:                 # a process each: the tools read the core from KMICRO_CPU
            with tempfile.TemporaryDirectory() as d:
                r = subprocess.run([sys.executable, '-c', code, str(ROOT), d], capture_output=True, text=True,
                                   encoding='utf-8', errors='replace', env={**os.environ, 'KMICRO_CPU': cpu})
                self.assertEqual(r.returncode, 0, f'{cpu}\n{r.stdout}{r.stderr}')
                self.assertTrue((Path(d) / 'autostubs.o').is_file(), cpu)


class OtherCore(unittest.TestCase):
    def link(self, core_txt, *options):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'k.o').write_bytes(b'')
            if core_txt is not None:
                (Path(d) / 'core.txt').write_text(core_txt, encoding='utf-8')
            return subprocess.run([sys.executable, ROOT / 'tools/qbuild.py', Path(d) / 'app.elf', Path(d) / 'k.o',
                                   '--target', 'an505', *options], capture_output=True, text=True,
                                  encoding='utf-8')

    def test_an_object_kbuild_built_for_another_core_is_refused(self):
        r = self.link('cortex-m4\n')
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn('k.o was built for cortex-m4, and this link is for cortex-m4f', r.stderr)
        r = self.link('cortex-m4f\n', '--cpu', 'cortex-m7')
        self.assertIn('k.o was built for cortex-m4f, and this link is for cortex-m7', r.stderr)

    def test_the_same_core_and_an_object_from_elsewhere_pass_the_check(self):
        # the run then stops at the target (an505 runs none of these cores), which is checked after the objects
        for core_txt, options in (('cortex-m4f\n', ()), ('cortex-m3\n', ('--cpu', 'cortex-m3')), (None, ()),
                                  ('not a core\n', ())):
            r = self.link(core_txt, *options)
            self.assertNotIn('was built for', r.stderr, core_txt)
            self.assertIn('--target an505 (QEMU mps2-an505) does not run', r.stderr, core_txt)


class Targets(unittest.TestCase):
    def test_every_target_lists_cores_that_exist(self):
        self.assertEqual(set(qbuild.RUNS), set(qbuild.TARGETS))
        for target, cores in qbuild.RUNS.items():
            self.assertLessEqual(set(cores), set(paths.CORES), target)

    def test_every_core_runs_on_its_default_target(self):
        for cpu in paths.CORES:
            self.assertIn(cpu, qbuild.RUNS[qbuild.DEFAULT_TARGET.get(cpu, 'l475')], cpu)

    def test_a_core_the_target_does_not_run_is_refused(self):
        for cpu, target, default in (('cortex-m4f', 'an505', 'l475'), ('cortex-m33', 'l475', 'an505'),
                                     ('cortex-m4f', 'an385', 'l475'), ('cortex-m7', 'an386', 'an500'),
                                     ('cortex-m4f', 'an547', 'l475'), ('cortex-m55', 'an505', 'an547'),
                                     ('cortex-m85-nofp', 'an505', 'an547'), ('arm1176jzf-s', 'virt', 'raspi0'),
                                     ('cortex-a7', 'raspi0', 'virt')):
            r = run('--cpu', cpu, '--target', target)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn(f'qbuild: --target {target} ', r.stderr)
            self.assertIn(f'does not run {cpu} code: it runs ', r.stderr)
            self.assertTrue(r.stderr.rstrip().endswith(f'Without --target, {cpu} runs on {default}'), r.stderr)


if __name__ == '__main__':
    unittest.main()

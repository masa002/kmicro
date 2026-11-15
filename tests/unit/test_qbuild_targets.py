# Copyright 2026 the kmicro authors (NOTICE).
# SPDX-License-Identifier: Apache-2.0
"""tools/qbuild.py: which core runs on which QEMU target (no compiler needed).

python -m unittest discover -s tests/unit
"""
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
                                     ('cortex-m4f', 'an385', 'l475'), ('cortex-m7', 'an386', 'an500')):
            r = run('--cpu', cpu, '--target', target)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn(f'qbuild: --target {target} ', r.stderr)
            self.assertIn(f'does not run {cpu} code: it runs ', r.stderr)
            self.assertTrue(r.stderr.rstrip().endswith(f'Without --target, {cpu} runs on {default}'), r.stderr)


if __name__ == '__main__':
    unittest.main()

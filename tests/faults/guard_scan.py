"""Runs the stack_guard test image once per stack position: String.toDouble() called with the stack 0, 8, 16 ...
4096 bytes above the stack guard of qemu-l475 (main.c reads the distance from QEMU's command line).

    python tests/faults/guard_scan.py build/t/stack_guard/stack_guard.elf

Each run must end in one of two ways: the call returns and the unused bytes below the guard are untouched (exit 0), or
the stack reaches the guard and the start code reports a stack overflow (exit 99). A run in which the bytes below the
guard changed and the program went on is the failure this looks for: a frame stepped over the guard. Exit status 1
when any run ended another way.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'toolchain'))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
import paths  # noqa: E402
import qbuild  # noqa: E402


def run(elf, pad):
    """(exit code, output) of the image with the stack `pad` bytes above the guard."""
    # in the image's folder, with its bare name: on Windows QEMU opens files through the ANSI code page
    machine = qbuild.TARGETS[qbuild.DEFAULT_TARGET.get(paths.cpu(), 'l475')][2]
    r = subprocess.run([str(paths.qemu_system_arm().resolve()), '-machine', machine, '-nographic',
                        '-semihosting-config', f'enable=on,target=native,arg=pad,arg={pad}', '-kernel', elf.name,
                        '-serial', 'none', '-monitor', 'none'], capture_output=True, timeout=120, cwd=elf.parent)
    return r.returncode, (r.stdout + r.stderr).decode('utf-8', 'replace').replace('\r\n', '\n')


def main():
    elf = Path(sys.argv[1])
    returned = faulted = 0
    bad = []
    for pad in range(0, 4097, 8):
        rc, out = run(elf, pad)
        if rc == 0 and f'stack {pad} bytes above the guard: toDouble 3141, words changed below the guard 0\n' == out:
            returned += 1
        elif rc == 99 and out.startswith('kmicro fault: stack overflow'):
            faulted += 1
        else:
            bad.append(f'  {pad}: exit {rc}: {out.strip().splitlines()[0] if out.strip() else "(no output)"}')
    print(f'{returned + faulted + len(bad)} stack positions: {returned} returned with the bytes below the guard '
          f'untouched, {faulted} stopped with a stack overflow report, {len(bad)} ended another way')
    for line in bad[:20]:
        print(line)
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()

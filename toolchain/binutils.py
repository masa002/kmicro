"""Run a program of the xPack arm-none-eabi binutils (nm, size, objdump, readelf, addr2line, objcopy) on a file.

On Windows these programs open files through the ANSI code page, so they cannot reach a folder whose name has a
character outside it (an accented letter on Japanese Windows). run() starts the program in the file's folder and
gives it the bare file name: such a folder then works. A file name outside the code page still does not.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402


def run(tool, file, *options, after=()):
    """arm-none-eabi-TOOL OPTIONS FILE AFTER, run in FILE's folder: the finished process, its output as text. A file
    named in AFTER (objcopy's output) is given by its name in that folder."""
    file = Path(file)
    return subprocess.run([str(paths.gcc_bin(tool).resolve()), *options, file.name, *after], cwd=file.parent,
                          capture_output=True, text=True, errors='replace')


def output(tool, file, *options, after=()):
    """What run() prints, for a script that cannot go on without it: a failure ends the script with the message."""
    r = run(tool, file, *options, after=after)
    if r.returncode != 0:
        sys.exit(f'FAILED: arm-none-eabi-{tool} {" ".join(options)} {file}\n{r.stderr[-3000:]}')
    return r.stdout

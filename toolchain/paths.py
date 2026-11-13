"""Where the external tools are. Every kmicro script imports this instead of naming a path.

Each tool is looked up in this order: its environment variable, then the usual install place under the home folder.

    KMICRO_KOTLIN_NATIVE  Kotlin/Native 2.4.21 prebuilt distribution (contains bin/kotlinc-native, bin/cinterop)
                          default: ~/toolchains/kotlin-native-prebuilt-*-2.4.21
    KMICRO_LLVM           the LLVM bin folder Kotlin/Native downloads on its first run (clang, ld.lld)
                          default: ~/.konan/dependencies/llvm-*-essentials-*/bin
    KMICRO_ARM_GCC        xPack arm-none-eabi-gcc (newlib, libgcc, objcopy, size, objdump)
                          default: ~/toolchains/xpack-arm-none-eabi-gcc-*
    KMICRO_QEMU           xPack QEMU Arm (only for the emulator targets and tests)
                          default: ~/toolchains/xpack-qemu-arm-*

BUILDING.md lists the versions kmicro is tested with.
"""
import os
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
WINDOWS = os.name == 'nt'
EXE = '.exe' if WINDOWS else ''
KOTLIN_NATIVE_VERSION = '2.4.21'          # retarget.py reads this compiler's IR; other versions are untested

ML = 'thumb/v7e-m+fp/hard'                 # newlib / libgcc multilib for Cortex-M4F, hard float
TARGET_M4F = ['--target=thumbv7em-none-eabihf', '-mcpu=cortex-m4', '-mfpu=fpv4-sp-d16', '-mfloat-abi=hard']


def _find(env, patterns, what):
    v = os.environ.get(env)
    if v:
        p = Path(v)
        if not p.exists():
            sys.exit(f'kmicro: {env}={v} does not exist ({what})')
        return p
    for pat in patterns:
        hits = sorted(HOME.glob(pat), reverse=True)
        if hits:
            return hits[0]
    return None


class _Lazy:
    """Tools resolved on first use, so a script that never needs QEMU never asks for it."""

    def __init__(self, env, patterns, what):
        self.env, self.patterns, self.what, self._p = env, patterns, what, None

    def __call__(self):
        if self._p is None:
            self._p = _find(self.env, self.patterns, self.what)
            if self._p is None:
                sys.exit(f'kmicro: {self.what} not found. Set {self.env} or install it under '
                         f'{HOME / self.patterns[0]} (see BUILDING.md).')
        return self._p


kotlin_native = _Lazy('KMICRO_KOTLIN_NATIVE', [f'toolchains/kotlin-native-prebuilt-*-{KOTLIN_NATIVE_VERSION}'],
                      f'Kotlin/Native {KOTLIN_NATIVE_VERSION}')
llvm = _Lazy('KMICRO_LLVM', ['.konan/dependencies/llvm-*-essentials-*/bin', '.konan/dependencies/llvm-*/bin'],
             'the LLVM of Kotlin/Native (run kotlinc-native once to download it)')
arm_gcc = _Lazy('KMICRO_ARM_GCC', ['toolchains/xpack-arm-none-eabi-gcc-*'], 'xPack arm-none-eabi-gcc')
qemu = _Lazy('KMICRO_QEMU', ['toolchains/xpack-qemu-arm-*'], 'xPack QEMU Arm')


def clang():
    return llvm() / f'clang{EXE}'


def ld_lld():
    return llvm() / f'ld.lld{EXE}'


def gcc_bin(name):
    """arm-none-eabi-<name> of the xPack toolchain (gcc, objcopy, size, objdump, nm)."""
    return arm_gcc() / 'bin' / f'arm-none-eabi-{name}{EXE}'


def newlib_include():
    return arm_gcc() / 'arm-none-eabi/include'


def newlib_lib():
    return arm_gcc() / 'arm-none-eabi/lib' / ML


def libgcc():
    return next((arm_gcc() / 'lib/gcc/arm-none-eabi').glob('*')) / ML / 'libgcc.a'


def qemu_system_arm():
    return qemu() / 'bin' / f'qemu-system-arm{EXE}'


def kn_command(tool, args):
    """Command line for kotlinc-native / cinterop (Windows ships .bat wrappers that need cmd.exe)."""
    b = kotlin_native() / 'bin'
    if WINDOWS:
        return ['cmd.exe', '/c', str(b / f'{tool}.bat'), *map(str, args)]
    return [str(b / tool), *map(str, args)]


def run_kn(tool, args, **kw):
    return subprocess.run(kn_command(tool, args), capture_output=True, text=True, errors='replace', **kw)


if __name__ == '__main__':                 # python toolchain/paths.py: show what was found
    for name, lazy in (('Kotlin/Native', kotlin_native), ('LLVM', llvm), ('arm-none-eabi-gcc', arm_gcc),
                       ('QEMU', qemu)):
        p = _find(lazy.env, lazy.patterns, lazy.what)
        print(f'{name:18s} {p if p else "NOT FOUND (" + lazy.env + ")"}')

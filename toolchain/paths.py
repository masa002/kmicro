"""Where the external tools are. Every kmicro script imports this instead of naming a path.

Each tool is looked up in this order: its environment variable, then the usual install place under the home folder.

    KMICRO_KOTLIN_NATIVE  Kotlin/Native 2.4.21 prebuilt distribution (contains bin/kotlinc-native, bin/cinterop)
                          default: ~/toolchains/kotlin-native-prebuilt-*-2.4.21
    KMICRO_LLVM           the LLVM bin folder Kotlin/Native downloads on its first run (clang, ld.lld)
                          default: ~/.konan/dependencies/llvm-*-essentials-*/bin (Windows, Linux), llvm-*-dev-*/bin
                          (macOS)
    KMICRO_ARM_GCC        xPack arm-none-eabi-gcc (newlib, libgcc, objcopy, size, objdump)
                          default: ~/toolchains/xpack-arm-none-eabi-gcc-*
    KMICRO_QEMU           xPack QEMU Arm (only for the emulator targets and tests)
                          default: ~/toolchains/xpack-qemu-arm-*
    JAVA_HOME             the Java that runs kotlinc-native and cinterop; default: `java` on PATH

toolchain/versions.txt lists the versions kmicro is tested with, with their downloads and SHA-256: when several
versions of a tool are installed, the tested one is used, else the newest, with a warning.
`python toolchain/paths.py` shows what is found and exits 1 when a tool is missing or incomplete.
"""
import functools
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
WINDOWS = os.name == 'nt'
EXE = '.exe' if WINDOWS else ''
KOTLIN_NATIVE_VERSION = '2.4.21'          # retarget.py reads this compiler's IR; other versions are untested

# The cores kmicro builds for: the clang target, the flags that choose the core and its floating-point unit, and the
# newlib / libgcc multilib of the xPack GCC that matches them. A core without an FPU uses the soft-float calling
# convention. Every 32-bit little-endian Thumb target has the data layout that retarget.py expects.
_SOFT = ['-mfpu=none', '-mfloat-abi=soft']
CORES = {
    'cortex-m0': ('thumbv6m-none-eabi', ['-mcpu=cortex-m0', *_SOFT], 'thumb/v6-m/nofp'),
    'cortex-m0plus': ('thumbv6m-none-eabi', ['-mcpu=cortex-m0plus', *_SOFT], 'thumb/v6-m/nofp'),
    'cortex-m1': ('thumbv6m-none-eabi', ['-mcpu=cortex-m1', *_SOFT], 'thumb/v6-m/nofp'),
    'cortex-m3': ('thumbv7m-none-eabi', ['-mcpu=cortex-m3', *_SOFT], 'thumb/v7-m/nofp'),
    'cortex-m4': ('thumbv7em-none-eabi', ['-mcpu=cortex-m4', *_SOFT], 'thumb/v7e-m/nofp'),
    'cortex-m4f': ('thumbv7em-none-eabihf', ['-mcpu=cortex-m4', '-mfpu=fpv4-sp-d16', '-mfloat-abi=hard'],
                   'thumb/v7e-m+fp/hard'),
    'cortex-m7': ('thumbv7em-none-eabihf', ['-mcpu=cortex-m7', '-mfpu=fpv5-d16', '-mfloat-abi=hard'],
                  'thumb/v7e-m+dp/hard'),
    'cortex-m7-sp': ('thumbv7em-none-eabihf', ['-mcpu=cortex-m7', '-mfpu=fpv5-sp-d16', '-mfloat-abi=hard'],
                     'thumb/v7e-m+fp/hard'),
    'cortex-m23': ('thumbv8m.base-none-eabi', ['-mcpu=cortex-m23', *_SOFT], 'thumb/v8-m.base/nofp'),
    'cortex-m33': ('thumbv8m.main-none-eabi', ['-mcpu=cortex-m33', *_SOFT], 'thumb/v8-m.main/nofp'),
    'cortex-m33f': ('thumbv8m.main-none-eabihf', ['-mcpu=cortex-m33', '-mfpu=fpv5-sp-d16', '-mfloat-abi=hard'],
                    'thumb/v8-m.main+fp/hard'),
}
DEFAULT_CPU = 'cortex-m4f'


def cpu():
    """The core this process builds for: KMICRO_CPU (which --cpu sets, for the tools a tool starts too), else the
    Cortex-M4F."""
    name = os.environ.get('KMICRO_CPU') or DEFAULT_CPU
    if name not in CORES:
        sys.exit(f'kmicro: unknown core {name} (KMICRO_CPU or --cpu); kmicro knows: {" ".join(CORES)}')
    return name


def select_cpu(name):
    """--cpu NAME of a tool: checks the name and makes it the core of this process and of the tools it starts."""
    if name:
        os.environ['KMICRO_CPU'] = name
    return cpu()


def add_cpu_option(parser, help_text=None):
    parser.add_argument('--cpu', metavar='CORE', choices=sorted(CORES),
                        help=help_text or f'the core to build for (default {DEFAULT_CPU}, or KMICRO_CPU): '
                                          + ', '.join(sorted(CORES)))


def triple():
    """The LLVM target triple of the core, as retarget.py writes it into the IR."""
    return CORES[cpu()][0].replace('-none-', '-unknown-none-')


def target_flags():
    """The clang flags that choose the core: target, CPU, FPU and calling convention."""
    t, flags, _ = CORES[cpu()]
    return [f'--target={t}', *flags]


def multilib():
    """The newlib / libgcc multilib folder of the xPack GCC for the core."""
    return CORES[cpu()][2]


@functools.lru_cache(maxsize=None)
def tested_versions():
    """toolchain/versions.txt: tool -> the versions kmicro is tested with (every host)."""
    t = {}
    for line in (Path(__file__).resolve().parent / 'versions.txt').read_text(encoding='utf-8').splitlines():
        f = line.split()
        if f and not line[0].isspace() and not f[0].startswith('#') and len(f) >= 2 and f[1] not in t.get(f[0], []):
            t.setdefault(f[0], []).append(f[1])
    return t


def version_key(p):
    """Sort key that orders version numbers as numbers: xpack-qemu-arm-10.1.0-1 after xpack-qemu-arm-9.2.4-1."""
    return [int(x) if x.isdigit() else x for x in re.split(r'(\d+)', Path(p).as_posix())]


def _tested(tool, p):
    return any(v in Path(p).as_posix() for v in tested_versions().get(tool, []))


def _find(env, patterns, what, tool=None):
    v = os.environ.get(env)
    if v:
        p = Path(v)
        if not p.exists():
            sys.exit(f'kmicro: {env}={v} does not exist ({what})')
        return p
    for pat in patterns:
        hits = sorted(HOME.glob(pat), key=version_key)
        if hits:
            tested = [h for h in hits if tool and _tested(tool, h)]
            return (tested or hits)[-1]
    return None


_warned = set()


def warn_once(msg):
    if msg not in _warned:
        _warned.add(msg)
        print(f'kmicro: warning: {msg}', file=sys.stderr)


class _Lazy:
    """Tools resolved on first use, so a script that never needs QEMU never asks for it."""

    def __init__(self, env, patterns, what, tool):
        self.env, self.patterns, self.what, self.tool, self._p = env, patterns, what, tool, None

    def __call__(self):
        if self._p is None:
            self._p = _find(self.env, self.patterns, self.what, self.tool)
            if self._p is None:
                sys.exit(f'kmicro: {self.what} not found. Set {self.env} or install it under '
                         f'{HOME / self.patterns[0]} (see BUILDING.md).')
            if not os.environ.get(self.env) and not _tested(self.tool, self._p):
                warn_once(f'{self._p} is not the tested version of {self.what} '
                          f'({", ".join(tested_versions().get(self.tool, []))}; toolchain/versions.txt)')
        return self._p


kotlin_native = _Lazy('KMICRO_KOTLIN_NATIVE', [f'toolchains/kotlin-native-prebuilt-*-{KOTLIN_NATIVE_VERSION}'],
                      f'Kotlin/Native {KOTLIN_NATIVE_VERSION}', 'kotlin-native')
llvm = _Lazy('KMICRO_LLVM', ['.konan/dependencies/llvm-*-essentials-*/bin', '.konan/dependencies/llvm-*/bin'],
             'the LLVM of Kotlin/Native (run kotlinc-native once to download it)', 'llvm')
arm_gcc = _Lazy('KMICRO_ARM_GCC', ['toolchains/xpack-arm-none-eabi-gcc-*'], 'xPack arm-none-eabi-gcc', 'arm-gcc')
qemu = _Lazy('KMICRO_QEMU', ['toolchains/xpack-qemu-arm-*'], 'xPack QEMU Arm', 'qemu')


def kotlin_native_version():
    """compilerVersion of the Kotlin/Native distribution in use (konan/konan.properties), or None."""
    props = kotlin_native() / 'konan/konan.properties'
    m = re.search(r'^compilerVersion\s*=\s*(\S+)', props.read_text(encoding='utf-8', errors='replace'), re.M) \
        if props.exists() else None
    v = m.group(1) if m else None
    if v != KOTLIN_NATIVE_VERSION:
        warn_once(f'{kotlin_native()} is Kotlin/Native {v or "(unknown version)"}; kmicro needs '
                  f'{KOTLIN_NATIVE_VERSION} (retarget.py reads its IR)')
    return v


def _exe(lazy, rel):
    """A tool's executable, or a one-line error that names it (e.g. KMICRO_LLVM set to the LLVM root, not bin)."""
    p = lazy() / rel
    if not p.exists():
        env = os.environ.get(lazy.env)
        what = lazy.what.split(' (')[0]
        sys.exit(f'kmicro: {p} not found: ' + (f'{lazy.env}={env} must be the {"bin" if lazy is llvm else "top"} '
                                                f'folder of {what}' if env else f'the install of {what} is incomplete'))
    return p


def clang():
    return _exe(llvm, f'clang{EXE}')


def ld_lld():
    return _exe(llvm, f'ld.lld{EXE}')


def gcc_bin(name):
    """arm-none-eabi-<name> of the xPack toolchain (gcc, objcopy, size, objdump, nm)."""
    return _exe(arm_gcc, f'bin/arm-none-eabi-{name}{EXE}')


def newlib_include():
    return arm_gcc() / 'arm-none-eabi/include'


def newlib_lib():
    return arm_gcc() / 'arm-none-eabi/lib' / multilib()


def libgcc():
    dirs = sorted((arm_gcc() / 'lib/gcc/arm-none-eabi').glob('*'), key=version_key)
    version = dirs[-1].name if dirs else '<version>'
    return _exe(arm_gcc, Path('lib/gcc/arm-none-eabi') / version / multilib() / 'libgcc.a')


def qemu_system_arm():
    return _exe(qemu, f'bin/qemu-system-arm{EXE}')


_java = None


def java():
    """(java executable, major version): JAVA_HOME's java, else the one on PATH (what the launchers use)."""
    global _java
    if _java is None:
        home = os.environ.get('JAVA_HOME')
        exe = Path(home) / 'bin' / f'java{EXE}' if home else shutil.which('java')
        if not exe or not Path(exe).exists():
            where = f'JAVA_HOME={home} has no bin/java{EXE}' if home else 'no java on PATH'
            sys.exit(f'kmicro: Java not found ({where}). Kotlin/Native runs on Java (JDK or JRE, 21 tested): set '
                     'JAVA_HOME or put java on PATH.')
        r = subprocess.run([str(exe), '-version'], capture_output=True, text=True, errors='replace')
        m = re.search(r'version "(\d+)(?:\.(\d+))?', r.stderr + r.stdout)
        major = int(m.group(1)) if m else 0
        if major == 1 and m.group(2):          # "1.8.0_275" is Java 8
            major = int(m.group(2))
        _java = (Path(exe), major)
    return _java


def _ansi_codepage():
    import ctypes
    acp = ctypes.windll.kernel32.GetACP()
    return 'utf-8' if acp == 65001 else f'cp{acp}'


def _short_path(p):
    import ctypes
    buf = ctypes.create_unicode_buffer(32768)
    n = ctypes.windll.kernel32.GetShortPathNameW(str(p), buf, len(buf))
    return buf.value if 0 < n < len(buf) else None


def arg_path(p, relative=True, fail=True):
    """A path as a command-line argument of Java (kotlinc-native, cinterop). Java's launcher on Windows reads its
    command line in the ANSI code page, so a character outside it (an accented letter on Japanese Windows, Japanese on
    English Windows) is lost. Such a path is given relative to the current folder, or by its 8.3 short name, when that
    avoids the character; else an error (None with fail=False)."""
    s = Path(p).as_posix()
    if not WINDOWS:
        return s
    cp = _ansi_codepage()

    def ok(t):
        try:
            t.encode(cp)
            return True
        except UnicodeEncodeError:
            return False
    if ok(s):
        return s
    tries = []
    if relative:
        try:
            tries.append(Path(os.path.relpath(p)).as_posix())
        except ValueError:                     # another drive
            pass
    short = _short_path(p) if Path(p).exists() else _short_path(Path(p).parent)
    if short:
        tries.append(Path(short).as_posix() if Path(p).exists() else (Path(short) / Path(p).name).as_posix())
    for t in tries:
        if ok(t):
            return t
    if fail:
        sys.exit(f'kmicro: {s}: this path cannot be passed to the tool ({cp} only) and has no short name: move it to '
                 'a folder whose name has no such characters, or run the build from inside the folder that has them '
                 '(a relative path avoids them).')
    return None


KN_TOOLS = {'kotlinc-native': 'konanc', 'konanc': 'konanc', 'cinterop': 'cinterop', 'klib': 'klib'}


def kn_command(tool, args):
    """Command line for kotlinc-native / cinterop. On Windows, Java runs the compiler directly, as run_konan.bat does:
    the .bat launchers go through cmd.exe, which splits arguments at '=' and ',', and breaks on a space in the
    Kotlin/Native path or on &, ^, %, ! in any path. An argument `@file` (an argument file) gets arg_path()."""
    return _kn_command(tool, args)[0]


def _kn_command(tool, args):
    """(command, working folder or None): an argument file whose path Java cannot take is named from its own folder."""
    kotlin_native_version()
    if not WINDOWS:
        return [str(_exe(kotlin_native, f'bin/{tool}')), *map(str, args)], None
    home = Path(os.path.abspath(kotlin_native()))
    exe, major = java()
    jar = Path(os.path.abspath(_exe(kotlin_native, 'konan/lib/kotlin-native-compiler-embeddable.jar')))
    opts = ['-ea', '-Xmx3G', '-XX:TieredStopAtLevel=1', '-Dfile.encoding=UTF-8',
            f'-Dkonan.home={arg_path(home, relative=False)}']
    if major >= 19:                            # messages as UTF-8 (run_kn decodes them so)
        opts += ['-Dstdout.encoding=UTF-8', '-Dstderr.encoding=UTF-8']
    if major >= 24:
        opts.append('--enable-native-access=ALL-UNNAMED')
    if major == 24:
        opts.append('--sun-misc-unsafe-memory-access=allow')
    opts += os.environ.get('JAVA_OPTS', '').split()
    cwd, tool_args = None, []
    for a in map(str, args):
        if a.startswith('@'):
            s = arg_path(a[1:], fail=False)
            if s is None:
                cwd, s = os.path.abspath(Path(a[1:]).parent), Path(a[1:]).name
            a = '@' + s
        tool_args.append(a)
    return [str(exe), *opts, '-cp', arg_path(jar, relative=False), 'org.jetbrains.kotlin.cli.utilities.MainKt',
            KN_TOOLS.get(tool, tool), *tool_args], cwd


def run_kn(tool, args, **kw):
    cmd, cwd = _kn_command(tool, args)
    utf8 = WINDOWS and java()[1] >= 19
    env = {**os.environ, 'LIBCLANG_DISABLE_CRASH_RECOVERY': '1', **kw.pop('env', {})}
    return subprocess.run(cmd, capture_output=True, text=True, errors='replace', env=env,
                          **({'encoding': 'utf-8'} if utf8 else {}), **({'cwd': cwd} if cwd else {}), **kw)


def _first_line(cmd):
    try:
        r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, errors='replace', timeout=60)
    except OSError as e:
        return f'cannot run ({e.strerror})'
    return ((r.stdout + r.stderr).strip().splitlines() or ['?'])[0]


def report():
    """python toolchain/paths.py: each tool, its version and whether it is the tested one. Exit 1 when one is
    missing or incomplete."""
    bad = 0
    tested = tested_versions()
    rows = [('Kotlin/Native', kotlin_native, [f'bin/kotlinc-native{".bat" if WINDOWS else ""}',
                                              f'bin/cinterop{".bat" if WINDOWS else ""}',
                                              'konan/lib/kotlin-native-compiler-embeddable.jar']),
            ('LLVM', llvm, [f'clang{EXE}', f'ld.lld{EXE}']),
            ('arm-none-eabi-gcc', arm_gcc, [f'bin/arm-none-eabi-{n}{EXE}' for n in ('gcc', 'objcopy', 'size', 'objdump',
                                                                                   'nm')] + ['arm-none-eabi/include']),
            ('QEMU', qemu, [f'bin/qemu-system-arm{EXE}'])]
    for name, lazy, files in rows:
        p = _find(lazy.env, lazy.patterns, lazy.what, lazy.tool)
        if p is None:
            print(f'{name:18s} NOT FOUND: set {lazy.env} or install it under {HOME / lazy.patterns[0]}')
            bad += 1
            continue
        lazy._p = p
        missing = [f for f in files if not (p / f).exists()]
        if lazy is arm_gcc and not missing:
            missing = [] if libgcc_ok() else [f'lib/gcc/arm-none-eabi/*/{multilib()}/libgcc.a']
        version = (kotlin_native_version() if lazy is kotlin_native else
                   _first_line([p / f'clang{EXE}', '--version']) if lazy is llvm else
                   _first_line([p / f'bin/arm-none-eabi-gcc{EXE}', '-dumpversion']) if lazy is arm_gcc else
                   _first_line([p / f'bin/qemu-system-arm{EXE}', '--version'])) if not missing else ''
        ok = (version == KOTLIN_NATIVE_VERSION if lazy is kotlin_native else
              _tested(lazy.tool, p) or any(v in (version or '') for v in tested.get(lazy.tool, [])))
        print(f'{name:18s} {p}')
        if not missing:
            print(f'{"":18s} {version}' + ('' if ok else
                                           f'   (untested: kmicro is tested with {", ".join(tested[lazy.tool])})'))
        for f in missing:
            print(f'{"":18s} MISSING: {p / f}')
        bad += bool(missing)
    home = os.environ.get('JAVA_HOME')
    exe = Path(home) / 'bin' / f'java{EXE}' if home else shutil.which('java')
    if not exe or not Path(exe).exists():
        print(f'{"Java":18s} NOT FOUND: set JAVA_HOME or put java on PATH (Kotlin/Native runs on Java)')
        bad += 1
    else:
        v = re.search(r'version "([^"]+)"', _first_line([exe, '-version']))
        major = java()[1]
        print(f'{"Java":18s} {exe}' + (' (JAVA_HOME)' if home else ' (PATH)'))
        print(f'{"":18s} {v.group(1) if v else "?"}' + ('' if str(major) in tested.get('java', []) else
                                                        f'   (untested: kmicro is tested with Java '
                                                        f'{", ".join(tested.get("java", []))})'))
    if bad:
        print(f'{bad} tool(s) missing or incomplete: see BUILDING.md')
    return 1 if bad else 0


def libgcc_ok():
    dirs = sorted((arm_gcc() / 'lib/gcc/arm-none-eabi').glob('*'), key=version_key)
    return bool(dirs) and (dirs[-1] / multilib() / 'libgcc.a').exists()


if __name__ == '__main__':                 # python toolchain/paths.py: show what was found
    sys.exit(report())

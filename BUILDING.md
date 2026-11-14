# Building kmicro

## Tools

| Tool | Tested version | What kmicro uses it for | Where kmicro looks |
|---|---|---|---|
| Kotlin/Native, prebuilt | 2.4.21 | `kotlinc-native`, `cinterop` | `KMICRO_KOTLIN_NATIVE`, else `~/toolchains/kotlin-native-prebuilt-*-2.4.21` |
| LLVM (`clang`, `ld.lld`) | 21, as downloaded by Kotlin/Native | IR to objects, the LTO link | `KMICRO_LLVM`, else `~/.konan/dependencies/llvm-*-essentials-*/bin` on Windows and Linux, `~/.konan/dependencies/llvm-*-dev-*/bin` on macOS |
| xPack GNU Arm Embedded GCC | 15.2.1-1.1 | newlib-nano, libm, libgcc, `objcopy`, `size`, `nm`, `objdump`, `readelf`, `addr2line` | `KMICRO_ARM_GCC`, else `~/toolchains/xpack-arm-none-eabi-gcc-*` |
| xPack QEMU Arm | 9.2.4-1 | running the tests and examples | `KMICRO_QEMU`, else `~/toolchains/xpack-qemu-arm-*` |
| Java (JDK or JRE) | 21 | runs `kotlinc-native` and `cinterop` | `JAVA_HOME`, else `java` on `PATH` |
| Python | 3.10 or later (3.11 tested) | the build scripts | `PATH` |

Each variable names the tool's top folder (for LLVM, its `bin` folder). When `KONAN_DATA_DIR` is set, Kotlin/Native
keeps its downloads in the folder it names instead of `~/.konan`, and kmicro looks for the LLVM in its
`dependencies` folder first.
[toolchain/paths.py](toolchain/paths.py) is the only place that knows these paths.
[toolchain/versions.txt](toolchain/versions.txt) lists the tested version of each tool for each host, with its
download and the download's SHA-256. When several versions of a tool are installed, kmicro uses the tested one,
else the newest, with a warning.

## Steps

1. **Kotlin/Native 2.4.21.** Download `kotlin-native-prebuilt-<host>-2.4.21` from the assets of the Kotlin 2.4.21
   release (<https://github.com/JetBrains/kotlin/releases/tag/v2.4.21>) and unpack it into `~/toolchains`.
   [toolchain/versions.txt](toolchain/versions.txt) has the SHA-256 of each host's archive.
2. **The compiler's LLVM.** The first compile for `linux_arm32_hfp` downloads the compiler's dependencies into
   `~/.konan/dependencies` (`$KONAN_DATA_DIR/dependencies` when that variable is set): LLVM 21 and a Linux ARM
   sysroot, a few hundred MB. It is the essentials build of LLVM on Windows and Linux; on macOS, the dev build that
   konan.properties names (versions.txt names each). `python tests/run_all.py add` does that compile.
3. **xPack GCC** from <https://github.com/xpack-dev-tools/arm-none-eabi-gcc-xpack/releases>, unpacked into
   `~/toolchains`. kmicro compiles with clang, but links newlib-nano and libgcc from this toolchain and uses its
   binutils.
4. **xPack QEMU** from <https://github.com/xpack-dev-tools/qemu-arm-xpack/releases>, unpacked into `~/toolchains`.
5. **Java**, a JDK or a JRE, which runs Kotlin/Native: set `JAVA_HOME`, or put `java` on `PATH`.
6. Check. `python toolchain/paths.py` prints each tool's folder and, on a second line, its version; `~` stands for
   the home folder here:

   ```
   $ python toolchain/paths.py
   Kotlin/Native      ~\toolchains\kotlin-native-prebuilt-windows-x86_64-2.4.21
                      2.4.21
   LLVM               ~\.konan\dependencies\llvm-21-x86_64-windows-essentials-150\bin
                      clang version 21.1.6 (https://github.com/Kotlin/llvm-project c2e420df942a21f93c15248b4fb9259737fa58c1)
   arm-none-eabi-gcc  ~\toolchains\xpack-arm-none-eabi-gcc-15.2.1-1.1
                      15.2.1
   QEMU               ~\toolchains\xpack-qemu-arm-9.2.4-1
                      xPack QEMU emulator version 9.2.4
   Java               C:\Program Files\Java\jdk-21\bin\java.exe (JAVA_HOME)
                      21.0.8
   ```

   A version other than the tested one is marked `(untested: kmicro is tested with ...)`. A missing tool or file is
   named (`NOT FOUND`, `MISSING`), and paths.py then exits 1.
7. `python tests/run_all.py` builds and runs every test program and example on QEMU, one PASS or FAIL line each, and
   ends with the count, `N passed, 0 failed`. `python -m unittest discover -s tests/unit` tests the tools.

## Hosts

- **Windows 10/11 x64:** tested, also in CI (windows-latest). kmicro starts Kotlin/Native with Java directly, with the
  options of its `run_konan.bat`, and hands `kotlinc-native` its arguments in a file; no `.bat` launcher and no
  `cmd.exe` is involved. Paths with spaces, `&`, `%` and Japanese folder names work. Java reads its command line in
  the ANSI code page, so kmicro passes a path with a character outside it (an accented letter on Japanese Windows)
  relative to the current folder or by its 8.3 short name. A cinterop `.def` file or `-I` folder that has neither is
  refused: run kbuild from inside that folder, or move it. The xPack tools (QEMU, `size`, `nm`, `objdump`) open files
  through the ANSI code page too: kmicro runs them in the file's folder with its bare name, so a folder name outside
  the code page works, but such a file name does not.
- **Linux x64:** tested in CI (ubuntu-latest), with the toolchains of versions.txt. `paths.py` runs the shell
  launchers of Kotlin/Native.
- **macOS:** untested. `paths.py` runs the shell launchers and looks for the dev build of the LLVM.

## Build output

Everything goes under `build/` (ignored by git). kbuild runs `kotlinc-native` again only when its arguments, the
compiler (its folder, version and jar) or one of the input files (size and time) changed since its last successful
run; `--kotlin` forces it. The same holds for the klibs that cinterop makes, include folders and headers included.
qbuild compiles the runtime once per set of `-D` values, into `build/qbuild/`, and again when a runtime file
changes.

A board build does not use qbuild: [docs/porting.md](docs/porting.md) lists what it compiles and links.

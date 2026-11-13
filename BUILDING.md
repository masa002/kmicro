# Building kmicro

## Tools

| Tool | Tested version | What kmicro uses it for | Where kmicro looks |
|---|---|---|---|
| Kotlin/Native, prebuilt | 2.4.21 | `kotlinc-native`, `cinterop` | `KMICRO_KOTLIN_NATIVE`, else `~/toolchains/kotlin-native-prebuilt-*-2.4.21` |
| LLVM (`clang`, `ld.lld`) | 21, as downloaded by Kotlin/Native | IR to objects, the LTO link | `KMICRO_LLVM`, else `~/.konan/dependencies/llvm-*-essentials-*/bin` |
| xPack GNU Arm Embedded GCC | 15.2.1-1.1 | newlib-nano, libm, libgcc, `objcopy`, `size`, `objdump` | `KMICRO_ARM_GCC`, else `~/toolchains/xpack-arm-none-eabi-gcc-*` |
| xPack QEMU Arm | 9.2.4-1 | running the tests and examples | `KMICRO_QEMU`, else `~/toolchains/xpack-qemu-arm-*` |
| Java (JDK or JRE) | 21 tested | runs `kotlinc-native` and `cinterop` | `JAVA_HOME`, else `PATH` (read by the Kotlin/Native launchers) |
| Python | 3.10 or later (3.11 tested) | the build scripts | `PATH` |

Each variable names the tool's top folder (for LLVM, its `bin` folder).
[toolchain/paths.py](toolchain/paths.py) is the only place that knows these paths.

## Steps

1. **Kotlin/Native 2.4.21.** Download `kotlin-native-prebuilt-<host>-2.4.21` from the assets of the Kotlin 2.4.21
   release (<https://github.com/JetBrains/kotlin/releases/tag/v2.4.21>) and unpack it into `~/toolchains`.
   [docs/research/PROVENANCE.txt](docs/research/PROVENANCE.txt) holds the SHA-256 of the Windows archive kmicro was
   developed with.
2. **The compiler's LLVM.** The first compile for `linux_arm32_hfp` downloads the compiler's dependencies into
   `~/.konan/dependencies`: LLVM 21 and a Linux ARM sysroot, a few hundred MB. `python tests/run_all.py add` does
   that compile.
3. **xPack GCC** from <https://github.com/xpack-dev-tools/arm-none-eabi-gcc-xpack/releases>, unpacked into
   `~/toolchains`. kmicro compiles with clang, but links newlib-nano and libgcc from this toolchain.
4. **xPack QEMU** from <https://github.com/xpack-dev-tools/qemu-arm-xpack/releases>, unpacked into `~/toolchains`.
5. Check (`paths.py` prints full paths; `~` stands for the home folder here):

   ```
   $ python toolchain/paths.py
   Kotlin/Native      ~/toolchains/kotlin-native-prebuilt-windows-x86_64-2.4.21
   LLVM               ~/.konan/dependencies/llvm-21-x86_64-windows-essentials-150/bin
   arm-none-eabi-gcc  ~/toolchains/xpack-arm-none-eabi-gcc-15.2.1-1.1
   QEMU               ~/toolchains/xpack-qemu-arm-9.2.4-1
   ```

6. `python tests/run_all.py` builds and runs everything: 66 tests, `66 passed, 0 failed`.

## Hosts

- **Windows 10/11 x64:** tested. kmicro runs the `.bat` launchers of Kotlin/Native through `cmd.exe` and hands
  `kotlinc-native` its arguments in a file, because the launcher splits arguments at `=` and `,`.
- **Linux, macOS:** `paths.py` runs the shell launchers instead. Untested so far.

## Build output

Everything goes under `build/` (ignored by git). `kotlinc-native` runs only when a Kotlin source is newer than the
IR saved from its last run; `--kotlin` forces it.

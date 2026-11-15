# Changelog

What changed in each release of kmicro. [docs/roadmap.md](docs/roadmap.md#releases-and-versions) says how versions
are numbered. The open problems are the [issues](https://github.com/masa002/kmicro/issues).

## 0.2.0 (2026-11-15)

kmicro builds for every Cortex-M core from the Cortex-M0 to the Cortex-M33, and the problems listed with 0.1.0 are
fixed.

### What a build script or a board has to change

- **qbuild gives a program the memory of the STM32L431:** 256 KB of flash and 64 KB of RAM on `l475` (and on the new
  targets `an385`, `an500` and `an505`), where it gave 1 MB and 96 KB. A program that does not fit fails to link, and
  with the default heap the stack is 40,960 bytes instead of 73,728. `qbuild --large` gives the old memory.
- **stdio:** the runtime has a weak `_write` that sends `printf` output where `println` goes. A board's own `_write`
  still replaces it. A `kmicro_puts` or `kmicro_write` that itself prints through stdio would now call itself: write
  to the device directly.
- **The uncaught-exception report** names a local class by its simple name and the class of an anonymous object
  `Throwable`, as `Throwable.toString()` does; it printed the compiler's internal names.
- Nothing changes in `runtime/kmicro.h`, and a build for the Cortex-M4F needs no new option.

### Cores

- `--cpu CORE` on kbuild, qbuild, run_all and difftest (or `KMICRO_CPU`) chooses the core: `cortex-m0`,
  `cortex-m0plus`, `cortex-m1`, `cortex-m3`, `cortex-m4`, `cortex-m4f` (the default), `cortex-m7`, `cortex-m7-sp`,
  `cortex-m23`, `cortex-m33`, `cortex-m33f`. A core without an FPU uses the soft-float calling convention.
  [docs/roadmap.md](docs/roadmap.md#targets) lists them with what was checked on each and the size of the selftest;
  [docs/porting.md](docs/porting.md#another-core) says what a board with another core changes.
- The runtime and the start code build for ARMv6-M (atomics without LDREX/STREX, Thumb-1 assembly) and for ARMv8-M
  (the MPU guards of the start code, IPSR on ARMv8-M Baseline).
- QEMU targets for the tests: `an385` (Cortex-M3), `an500` (Cortex-M7), `an505` (Cortex-M33, which also runs the
  code built for the Cortex-M23). Code for the Cortex-M0, M0+, M1 and M4 runs on the Cortex-M4F of the STM32L475.
- Not supported: Cortex-M55 and M85, Cortex-R, 32-bit Cortex-A, 64-bit ARM.

### Fixed

- **Runtime:** `printf` printed nothing on `qemu-l475` and on a board (#102); `String.toDouble()` failed on text with
  400 or more significant digits (#93); the uncaught-exception report showed internal class names (#94); an uncaught
  exception hung when the reset entry called the start function with `bl` (#143); the start code relied on the reset
  value of lr, which a Cortex-M0 does not define.
- **Build:** a header included from a subfolder did not trigger a rebuild of its cinterop library (#98); two `.def`
  files with the same name collided (#92); `--init-all` skipped root-package objects whose name does not start with
  A-Z (#113); `-Xbinary=latin1Strings=true` failed on a string that contains `thread_local ` (#105);
  `suspend fun main()` is refused with a message (#107); the LLVM is found under `KONAN_DATA_DIR` (#109).
- **Tools:** `--target an386` has a SysTick vector (#104); `gen_regs.py` reads more of C and names what it leaves out
  (#103); `symbolize.py` and `frames.py` work in a folder outside the ANSI code page on Windows (#90);
  `isr_check.py` counts indirect tail calls (#106); `retarget.py` and `missing_natives.py` stop with a message on a
  file that is not LLVM IR (#108).

### New in the tools

- `qbuild --icount` runs QEMU on its instruction count instead of the host's clock, so a timer interrupt lands on the
  same instruction in every run (#114). run_all uses it.
- kbuild warns about a program that uses Regex, which does not fit 256 KB of flash without `--size`; the Regex rows
  of [docs/kotlin-support.md](docs/kotlin-support.md) say "partly" (#99).
- `retarget.py` warns when one of its rewrites of the standard library matches nothing in a module that contains its
  target, the first sign that a compiler version writes that code in another way (#115).

### Tests and CI

- CI runs run_all for eight cores and on Windows on every pull request, and a weekly job builds and tests with the
  newest Kotlin release without failing the others (#95, #115, #119).
- The size budget counts the stack (#97); run_all builds the STM32L431 example (#110); difftest checks the stack
  frames of its programs (#142).
- Every source file carries its copyright and license header (#91).

### Tested with

- Kotlin/Native 2.4.21 with the LLVM 21 it downloads, xPack GNU Arm Embedded GCC 15.2.1-1.1, xPack QEMU Arm 9.2.4-1,
  Python 3.10 to 3.12 ([toolchain/versions.txt](toolchain/versions.txt)).
- Hosts: Windows and Linux x64, both in CI. macOS is untested.
- Cores: run_all passes for cortex-m0plus, cortex-m3, cortex-m4, cortex-m4f, cortex-m7, cortex-m23, cortex-m33 and
  cortex-m33f on QEMU; an STM32L431 board in [a run recorded before 0.1.0](examples/selftest/stm32l431-report.txt).
- Suites: 79 run_all tests, on the default core also with a collection at every allocation; 45 difftest programs,
  the same way; 143 tool tests.

### Known issues

- The board times in the README are from a runtime older than 0.1.0; the run has not been repeated (#111).
- Kotlin 2.5.0-RC: programs do not link, because its standard library no longer has a function that the runtime
  calls (#149). The supported version is 2.4.21.

## 0.1.0 (2026-11-14)

The first release.

### What it is

kmicro runs the output of the unmodified Kotlin/Native 2.4.21 compiler on a Cortex-M4F with no operating system:
`tools/kbuild.py` compiles Kotlin sources for the microcontroller, and the runtime in `runtime/` replaces the stock
Kotlin/Native runtime.

- **Language and standard library.** Classes, generics, lambdas, coroutines, exceptions with stack traces,
  collections, strings, numbers, `kotlin.time`, `kotlin.random`, atomics.
  [docs/kotlin-support.md](docs/kotlin-support.md) lists every feature with its status; most behave as on stock
  Kotlin/Native, checked by comparing program output byte for byte (`tools/difftest.py`).
- **Runtime.** A precise, non-moving mark-sweep garbage collector on a heap of 16 KB by default, ARM EHABI
  exceptions, `fun main()` or a C `main` that calls Kotlin.
- **C interop.** cinterop through `kbuild.py --def`, C calling Kotlin by plain names (`--c-api`, `@CName`),
  register access from Kotlin (`support/hw.h`, `tools/gen_regs.py`).
- **Interrupt handlers in Kotlin**, with run-time guards and a static check (`tools/isr_check.py`).
- **Tools.** `qbuild.py` (link and run on QEMU), `symbolize.py`, `frames.py`, `missing_natives.py`.
- **Documentation.** How it works, writing Kotlin for a microcontroller, porting to a board.

### Tested with

- Kotlin/Native 2.4.21 with the LLVM 21 it downloads, xPack GNU Arm Embedded GCC 15.2.1-1.1, xPack QEMU Arm 9.2.4-1,
  Python 3.10 to 3.12 ([toolchain/versions.txt](toolchain/versions.txt)).
- Hosts: Windows 10 and Linux x64 (CI). macOS is untested.
- Targets: QEMU's STM32L475 (`qemu-l475`), every test; QEMU's MPS2-AN386 for programs that need more memory; an
  STM32L431 board in [a run recorded earlier](examples/selftest/stm32l431-report.txt).
- Suites: 70 run_all tests and 44 difftest programs, each also with a collection at every allocation, and 107 tool
  tests.

### Known issues

The limits by design and the known gaps are in [README.md](README.md#known-gaps). Open problems found so far:

- **Runtime:** `printf` prints nothing on `qemu-l475` and on a board (#102); `String.toDouble()` fails on text with
  400 or more significant digits (#93); the uncaught-exception report shows internal names for local and anonymous
  classes (#94).
- **Build:** a header included from a subfolder does not trigger a rebuild of its cinterop library (#98); two `.def`
  files with the same name collide (#92); `--init-all` skips root-package objects whose name does not start with
  A-Z (#113); `-Xbinary=latin1Strings=true` fails on a string that contains `thread_local ` (#105); a
  `suspend fun main()` is not refused (#107); `KONAN_DATA_DIR` is ignored (#109).
- **Tools:** `--target an386` has no SysTick vector (#104); `gen_regs.py` fails on some ordinary C headers (#103);
  `symbolize.py` and `frames.py` fail in a folder outside the ANSI code page on Windows (#90); `isr_check.py` does
  not report an indirect tail call (#106); two tools print a traceback for a file that is not LLVM IR (#108).
- **Tests and CI:** the size budget does not count the stack (#97); no Windows job (#95); no test builds the
  STM32L431 example (#110); interrupt tests follow the host clock (#114); no early warning for the next compiler
  release (#115).
- **Documentation and repository:** files derived from Kotlin/Native do not carry its copyright line (#91); the
  Regex rows say "works" although a Regex program does not fit 256 KB of flash without `--size` (#99); the board
  times in the README are from an earlier runtime (#111).

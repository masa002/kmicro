# Changelog

What changed in each release of kmicro. [docs/roadmap.md](docs/roadmap.md#releases-and-versions) says how versions
are numbered. The open problems are the [issues](https://github.com/masa002/kmicro/issues).

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

# Changelog

What changed in each release of kmicro. [docs/roadmap.md](docs/roadmap.md#releases-and-versions) says how versions
are numbered. The open problems are the [issues](https://github.com/masa002/kmicro/issues).

## 0.2.1 (2026-11-16)

The fixes of a check of the whole repository after 0.2.0. Three of the problems gave a wrong program without a
message: an exception lost with `kbuild --size`, array copies under an interrupt handler, and C functions that
return a struct of floats on a core without an FPU.

### What a build script or a board has to change

- **Rebuild a firmware that was built with `kbuild --size`** (#197, below). Its image is now 1 to 3 % larger: a
  program close to the flash limit may no longer fit.
- **qbuild refuses a `k.o` that kbuild built for another core,** and a `--target` whose machine does not run the
  code of the core: give kbuild and qbuild the same `--cpu` (or `KMICRO_CPU`). kbuild leaves the core's name in
  `core.txt` next to `k.o` and `bridges.o`. A link that succeeds now prints the linker's warnings.
- **`hw_cycles_enable()` returns a `bool`** ([support/hw.h](support/hw.h)): false where there is no cycle counter,
  and `hw_cycles()` then stays 0. Code that ignores the result needs no change.
- **The QEMU start code has vectors for the external interrupts:** `IRQ0_Handler` to `IRQ99_Handler`, numbered as
  the NVIC numbers them. A program for a QEMU target gives its handler that name; an interrupt that is enabled
  without one ends in the fault report. The table takes 0.5 KB of flash in a QEMU image.
- **isr_check** has `--vectors SECTION` for a linker script that does not call the vector table `.isr_vector`; without
  that section it now prints a note that only the functions named like handlers were checked.
- **difftest:** under `// difftest: ulp N` a number is compared as a Float only when the program prints an `f`
  after it.
- The hello example and the selftest say `Cortex-M` where they said `Cortex-M4` (#167): a script that compares
  their output follows.
- Nothing changes in `runtime/kmicro.h` except that a C++ file can include it.

### Fixed

- **`kbuild --size` could lose an exception (#197).** An exception thrown below a call that LLVM's machine outliner
  had moved out of a Kotlin function passed the `try` that should have caught it, and the program ended with
  `Uncaught Kotlin exception`. Seen on the Cortex-M4F, M7 and M33; code for the Cortex-M0+ was not affected. `--size`
  now keeps the outliner away from Kotlin code (#199), and the sizes the documents give for `--size` are measured
  again (#206).
- **An interrupt handler could read a half-copied array element (#178).** `copyInto`, and with it
  `ArrayList.removeAt` and `add(0, x)`, copied byte by byte: a handler that read an element in the middle of a copy
  got bytes of two values, for a reference a pointer to nowhere, and one that stored into the array could leave
  such a pointer in it. Copies and fills now go element by element, each element with one load and one store; an
  element of a `LongArray` or `DoubleArray` is two words, as any `Long` (#205, #211).
- **cinterop on a core without an FPU: a C function that returns a struct of floats or doubles by value (#171)**
  wrote its result through its first argument: wrong values, or a fault far from the cause. A `staticCFunction`
  that returns such a struct to C failed the same way. The bridges now pass the result as C compiled for the core
  does (#210, #219). One shape is not handled there and stops the build with a message that says what to do: a
  struct of floats returned through a C function pointer that Kotlin calls. The cores with an FPU were not affected.
- **Runtime:** `-D KM_GC_STRESS=0` turned GC stress on (#189); `kmicro.h` and `support/hw.h` could not be included
  from C++ (#181); `hw_cycles()` stayed 0 without a word on ARMv6-M, on ARMv8-M Baseline and on Cortex-M7 chips that
  lock the DWT: `hw_cycles_enable()` opens the lock and says whether a counter counts (#183; not run on a chip,
  QEMU models no DWT); `toDouble()` and `toFloat()` could free native memory twice when the arena ran out in a later
  round of the parser (#188); a C `main` without `kmicro_init()` stopped with `unknown TLS key`, and the panic now
  names the missing call (#190); the compare-and-set functions for ARMv6-M had a parameter that the compiler's call
  does not pass (#191).
- **Tools:** qbuild linked a `k.o` built for another core without a word and hid the linker's warnings (#172), built
  for a `--target` on which the stack and null guards do nothing (#164), and wrote stubs for missing runtime
  functions that did not assemble on ARMv6-M (#173); the QEMU start code had no vectors for the external interrupts:
  a handler was dropped and the interrupt jumped into code (#180); `gen_regs.py` gave every register after a nested
  struct of 8- or 16-bit registers a wrong address (#174), read interrupt numbers in hexadecimal or octal wrong and
  computed some constants as C does not (#175); `isr_check.py` did not say when it found no vector table (#176);
  difftest `ulp N` compared short Doubles and integers with the tolerance of a Float (#177) and headed the kmicro
  side `Cortex-M4` for every core (#166).
- **Documentation:** `printf` of `platform.posix` prints nothing for `%f` and reads the wrong arguments after `%lld`,
  where the documents said it works: they now say which conversions work and how to get the others (#198);
  [docs/porting.md](docs/porting.md) says what the null guard needs on a chip whose flash begins at address 0 (#179),
  that a board hook in a static library is not linked (#182), and that ARMv6-M and ARMv8-M Baseline fault on an
  unaligned access (#170); the instruction counts of a throw say what they depend on (#169); the sample outputs
  and sizes in the documents, and the sizes in kbuild's warning about Regex, are measured again (#236).

### Tests and CI

- The QEMU start code turns on the fault for an unaligned access (CCR.UNALIGN_TRP) for the cores that have it on
  the chip, so the tests that run ARMv6-M and ARMv8-M Baseline code on a larger core find such an access (#168).
- New tests for the fixes above: `size_throw`, `isr_copy`, `no_init`, `app_gc_stress_0`, `qbuild_cxx`, `qbuild_irq`,
  `qbuild_irq_an386`, `qbuild_unaligned`, `stdio_float`, and struct results of floats in `cinterop_shapes`.
- The bug report form asks for the core (#165).

### Tested with

- Kotlin/Native 2.4.21 with the LLVM 21 it downloads, xPack GNU Arm Embedded GCC 15.2.1-1.1, xPack QEMU Arm 9.2.4-1,
  Python 3.10 to 3.12 ([toolchain/versions.txt](toolchain/versions.txt)).
- Hosts: Windows and Linux x64, both in CI. macOS is untested.
- Cores: run_all passes for cortex-m0plus, cortex-m3, cortex-m4, cortex-m4f, cortex-m7, cortex-m23, cortex-m33 and
  cortex-m33f on QEMU; an STM32L431 board in [a run recorded before 0.1.0](examples/selftest/stm32l431-report.txt).
- Suites: 88 run_all tests, on the default core also with a collection at every allocation; 45 difftest programs,
  the same way; 169 tool tests.

### Known issues

- The board times in the README are from a runtime older than 0.1.0; the run has not been repeated (#111).
- Kotlin 2.5.0-RC: programs do not link, because its standard library no longer has a function that the runtime
  calls (#149). The supported version is 2.4.21.
- A second check, made after these fixes, found more problems; they are open at this release as #213 to #238. Two
  of them can stop a correct program: `--init-all` leaves out `@ThreadLocal` globals and objects, so an interrupt
  handler's first use of one still stops the program (#216), and a member function named `main()` is taken for the
  program's `fun main()` (#220). The others are in the tools and their messages: gen_regs, frames, symbolize,
  isr_check, difftest, missing_natives, irstat, kbuild's option parsing and the search for the installed tools.

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

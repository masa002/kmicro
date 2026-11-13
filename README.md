# kmicro

[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![Kotlin/Native 2.4.21](https://img.shields.io/badge/Kotlin%2FNative-2.4.21-informational)](https://github.com/JetBrains/kotlin/releases/tag/v2.4.21)
[![Target: Cortex-M4F](https://img.shields.io/badge/target-Cortex--M4F%2C%20bare%20metal-informational)](docs/how-it-works.md)
[![RAM: 64 KB](https://img.shields.io/badge/RAM-64%20KB-informational)](#numbers)
[![Status: experimental](https://img.shields.io/badge/status-experimental-orange)](#status)

**Running Kotlin® on bare-metal microcontrollers, built by the official compiler.**

kmicro runs the output of the unmodified Kotlin/Native 2.4.21 compiler on a Cortex-M4 with no operating system and
64 KB of RAM. It replaces the Kotlin/Native runtime with one written for a single thread and a heap of a few
kilobytes: a precise garbage collector, exceptions, coroutines, strings, and cinterop to call C.

```kotlin
// examples/hello/hello.kt
package hello

fun hello(times: Int): Int {
    val names = List(times) { "Kotlin #${it + 1}" }
    println("Hello from ${names.joinToString()} on a bare Cortex-M4")
    return names.size
}
```

```c
// examples/hello/main.c
#include "kmicro.h"
#include "hello.h"

int main(void)
{
    kmicro_init();                      /* heap, garbage collector, exceptions */
    return hello(3) == 3 ? 0 : 1;       /* the exit code QEMU reports */
}
```

```
$ python tests/run_all.py hello
PASS  hello     text 66892  data 80  bss 18004
```

## Status

kmicro is experimental. It grew out of a real device firmware: 24 modules written in Kotlin on an STM32L431 with
64 KB of RAM and 256 KB of flash. That firmware is not part of this repository; the examples, tests and the
[board run of the self-test](examples/selftest/stm32l431-report.txt) are.

Most of the language and the standard library behave exactly as on stock Kotlin/Native: `tools/difftest.py` builds
the same program for the host and for kmicro and compares the output byte for byte. The full list, feature by
feature, is in [docs/kotlin-support.md](docs/kotlin-support.md).

| Works | Notes |
|---|---|
| classes, interfaces, generics, lambdas, objects, data/sealed/enum/value classes, delegation | |
| garbage collection | precise mark-sweep in a fixed arena (`KM_HEAP_BYTES`), non-moving |
| strings, `StringBuilder`, `println` | UTF-16, output through your `kmicro_puts` |
| exceptions, `try`/`catch`/`finally`, cause chains, `runCatching` | ARM EHABI unwinding |
| coroutines (`kotlin.coroutines`) | suspend, resume, sequence builders, your own event loop |
| collections, sequences, `Regex`, number formatting and parsing | output byte-identical to stock Kotlin/Native; `Regex` and `toDouble()` need a large heap (below) |
| cinterop with scalars, pointers, strings, globals, enums | Kotlin calls C; C calls Kotlin by plain names |
| interrupt handlers in Kotlin | they must not allocate or store object references: [docs/writing-kotlin.md](docs/writing-kotlin.md) |

### Known gaps

These do not work yet; fixes for most of them are in progress. This is the short list:
[docs/kotlin-support.md](docs/kotlin-support.md) has every case.

- **No clock or entropy source:** `kotlin.random` (even `Random(42)`), `measureTime`, `TimeSource.Monotonic`,
  `Clock.System` and `Uuid.random()` stop the program.
- **Missing runtime functions:** `kotlin.native.Platform`, `exitProcess`, `readln`, `GC.schedule`, `WeakReference`,
  `StableRef`, `Duration.toString(unit, decimals)`, `AtomicIntArray`, `ByteArray.getIntAt` and a few others stop the
  program, most of them with a message naming the missing function; a few end in a misleading exception or a fault
  instead.
- **Silently ignored:** `@CName` exports nothing (use `--c-api`), and `setUnhandledExceptionHook` never calls its
  hook.
- **Stack traces:** addresses only; a frame can repeat or be missing, and `printStackTrace()` of an exception with a
  cause stops the program.
- **Memory:** a stack overflow is not detected, and Kotlin/Native puts large local arrays on the stack;
  `String.toDouble()` needs more than the default 16 KB heap, and the first `Regex` keeps 12-14 KB of it.
- **cinterop:** structs by value, `staticCFunction` callbacks and header `static inline` functions with loops do not
  build yet; `nativeHeap` has a 1 KB arena that is reused only in last-in, first-out order.
- **Tools:** a program needs a small C `main` (no Kotlin-only `fun main` yet); build paths with spaces or non-ASCII
  characters fail on Windows.

Limits by design:

- **One compiler version.** kmicro reads the IR of Kotlin/Native 2.4.21. It builds on the `linux_arm32_hfp` target,
  which JetBrains has deprecated, so a later compiler may not offer it.
- **One CPU, tested: Cortex-M4F.** The compiler target is hard-float, so the core needs an FPU. A Cortex-M7 should
  need only other CPU flags in `toolchain/` (untested); a core without an FPU would need the soft-float calling convention.
- **One thread.** Interrupts are fine, with the rules in [docs/writing-kotlin.md](docs/writing-kotlin.md). There are
  no threads and no `Worker`.
- **The standard library only.** kotlinx libraries are untested.

## Getting started

1. Install the tools listed in [BUILDING.md](BUILDING.md): Kotlin/Native 2.4.21 and a Java runtime to run it (its
   first compile downloads LLVM), the xPack Arm GCC (for newlib and libgcc), QEMU for Arm, Python 3.10 or later.
2. `python toolchain/paths.py` shows what it found.
3. `python tests/run_all.py` builds every test and example and runs them on an emulated STM32L475.
   The first run compiles each program with kotlinc-native, about a minute each.

Your own program, on the emulator, takes three files like [examples/hello](examples/hello): the Kotlin code with a
`package` line, a C header whose prototypes name the Kotlin functions C may call, and a C `main` that calls
`kmicro_init()` first.

```
python tools/kbuild.py build/app app.kt --c-api app.h --package app
python tools/qbuild.py build/app/app.elf main.c build/app/k.o --run
```

When the Kotlin code calls C, `cinterop` makes a klib from a `.def` file, `kbuild.py -l` takes it, and kbuild also
prints a `bridges.o` to link: [docs/how-it-works.md](docs/how-it-works.md#calling-between-c-and-kotlin).

On a real board, link `k.o` with `runtime/`, your startup code and a linker script:
[examples/selftest/stm32l431](examples/selftest/stm32l431) does this for an STM32L431, and
[docs/how-it-works.md](docs/how-it-works.md) explains the pieces. Copy the compiler flags and linker-script
sections of that example: without `-fexceptions -funwind-tables` on the runtime, no Kotlin exception is caught.

## Numbers

[examples/selftest](examples/selftest) on an STM32L431 at 16 MHz, 16 KB Kotlin heap
([full report](examples/selftest/stm32l431-report.txt)):

| Check | Time |
|---|---|
| runtime start (module initializers) | 111 µs |
| classes, interface, virtual calls | 53 µs |
| garbage collection: 6000+ objects through the 16 KB heap | 161 ms |
| strings: 10 checks, UTF-16, JVM `hashCode` | 1.5 ms |
| one `throw` + `catch` | 1.6 ms\* |
| coroutine: 300 suspend/resume cycles | 49 ms |
| one full collection | 1.8 ms |

\* Recorded with a stack-trace walk that visits the same frame several times; a fix is in progress, after which the
time will be measured again.

## Repository layout

| Folder | Contents |
|---|---|
| [runtime/](runtime) | the Kotlin runtime, in C and C++ |
| [toolchain/](toolchain) | the build steps: `paths.py` finds the tools, `kn.py` runs the pipeline, `retarget.py` and `bridges.py` adapt the compiler's IR |
| [support/](support) | `hw.h`: volatile register access, barriers, interrupt masks for Kotlin |
| [targets/](targets) | startup code and linker scripts for QEMU (`qemu-l475` for programs, `qemu-an386` for large unit tests) |
| [tools/](tools) | `kbuild.py`, `qbuild.py`, `gen_regs.py` (CMSIS to Kotlin), `isr_check.py`, `symbolize.py`, `difftest.py`, `measure.py`, `irstat.py`, `port_dtoa.py` |
| [examples/](examples) | `hello`, `selftest` (with its STM32L431 board files) |
| [tests/](tests) | `run_all.py`, the test programs, the differential tests |
| [docs/](docs) | [Kotlin support](docs/kotlin-support.md), [how it works](docs/how-it-works.md), [writing Kotlin for a microcontroller](docs/writing-kotlin.md), [design notes](docs/research) |

## License

Apache License 2.0: [LICENSE](LICENSE). Parts follow Kotlin/Native and Apache Harmony sources: [NOTICE](NOTICE).

kmicro is an independent project, not affiliated with or endorsed by JetBrains or the Kotlin Foundation. "Kotlin"
refers to the Kotlin® programming language.

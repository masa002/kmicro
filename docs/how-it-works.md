# How kmicro works

Kotlin/Native has no target for a microcontroller without an operating system. It does have `linux_arm32_hfp`:
32-bit ARM, hard-float, EABI. The LLVM data layout of that target is identical, character for character, to the
one for Cortex-M (`thumbv7em-none-eabihf`):

    e-m:e-p:32:32-Fi8-i64:64-v128:64:128-a:0:32-n32-S64

So the IR that the official compiler produces for `linux_arm32_hfp` is already laid out the way a Cortex-M4
program must be: the same sizes, alignments and calling convention. kmicro takes that IR before the compiler links
its own runtime, which needs Linux, threads and about 184 KB of code, and links it with a small runtime written for
one thread and no OS. The compiler itself is not modified.

## The build

```
app.kt
  │  kotlinc-native 2.4.21 -target linux_arm32_hfp -p static -nomain -opt
  │                        -Xsave-llvm-ir-after=Codegen,LinkBitcodeDependencies
  ▼
out.Codegen.ll                 your code + the parts of the standard library it uses, as LLVM IR
  │  toolchain/retarget.py     triple -> thumbv7em, Cortex-M4 attributes, thread-locals -> plain globals
  ▼
m4.ll ──(C names for Kotlin functions, --c-api)──▶ clang -flto ──▶ k.o (LLVM bitcode)
                                                                     │
runtime/*.c *.cpp  ── clang -flto -fexceptions -funwind-tables ──────┤
your C code        ── clang -flto (or gcc without -flto) ────────────┤
                                                                     ▼
                                                    ld.lld --lto-O2 ──▶ firmware.elf
```

[toolchain/kn.py](../toolchain/kn.py) holds these steps as functions. [tools/kbuild.py](../tools/kbuild.py) runs
them from the command line, and [tools/qbuild.py](../tools/qbuild.py) links the result for the QEMU target.
[porting.md](porting.md) is the same link for a board: the runtime's flags, the linker script and the libraries.

```
python tools/qbuild.py OUT.elf FILE... [-D NAME=VALUE]... [-I DIR]... [--target l475|an386] [--large] [--run]
                       [--icount] [--timeout S]
```

The files are any number of C, C++ and assembly files and the objects kbuild printed (`k.o`, and `bridges.o` when
the Kotlin code calls C). `-D` applies to every C file and to the runtime, which is compiled once per set of `-D`
values, and `-I` to every C file; `runtime/` and `support/` are always on the include path. `--target an386` links
for QEMU's `mps2-an386` (4 MB of code, 16 MB of RAM) instead of the STM32L475, for a program that needs more memory
than a microcontroller has. `--run` runs the image and exits with its exit code, 124 after `--timeout` seconds (120
by default). With `--icount` the emulator's clock is the number of instructions the program has run, one nanosecond
each, instead of the host's clock: a timer interrupt then lands on the same instruction in every run. qbuild prints
a size line, `qbuild: app.elf  text N  data N  bss N  stack N`, where the stack is the RAM above `.bss`, without the
stack guard on a target that has one (`qemu-l475`); `bss` leaves the guard out too.

The STM32L475 has 1 MB of flash and 96 KB of RAM, but qbuild links a program into the memory of the STM32L431,
256 KB of flash and 64 KB of RAM: a program that does not fit fails to link, and one that needs more stack than
those 64 KB leave stops with `kmicro fault: stack overflow`. `--large` links it for the whole STM32L475 instead.

Link-time optimisation treats the runtime and the Kotlin code as one program. The runtime's hooks, such as the
frame push of the garbage collector or an array access, are inlined into the Kotlin functions that call them. For
that to work, retarget.py stamps the Kotlin functions with exactly the `target-cpu` / `target-features` attributes
clang gives the runtime. LLVM does not inline across functions with different attributes.

What retarget.py changes:

| Change | Why |
|---|---|
| target triple `thumbv7em-unknown-none-eabihf` | the code generator then emits Thumb-2 for Cortex-M |
| `target-cpu` / `target-features` = clang's values for the core (`CORES` in [toolchain/paths.py](../toolchain/paths.py)) | LTO inlines runtime hooks into Kotlin code; the values are read from clang once and kept in `target_attributes.txt` next to the output |
| `thread_local` removed (`--no-tls`) | one thread; no `__aeabi_read_tp` on bare metal |
| init-state loads made plain (`--single-core`) | each access to a file's globals checks its init state with an acquire load (a `DMB`); with one core and one thread a plain load is exact and can leave the loop |
| `minsize` everywhere except `--hot` functions (`--size`) | a firmware keeps real-time code fast and the rest small |
| `Random.Default` seeded from `kmicro_random_seed()` | `kotlin.random` needs no clock |
| the hexadecimal branch of `toDouble()` / `toFloat()` calls `runtime/hexfloat.c` | number parsing does not link the Regex engine |
| the Unicode tables stay in flash | the standard library would copy them to the heap on first use |

kbuild compiles with kotlinc-native again only when its arguments, the compiler or one of the inputs changed;
`--kotlin` forces it. `python tools/kbuild.py build/app app.kt --kotlinc -g` adds debug information, which
[tools/symbolize.py](../tools/symbolize.py) uses (below).

## The runtime

[runtime/](../runtime) replaces the stock Kotlin/Native runtime. A file that follows a stock source names it in its
first comment.

| File | What it does |
|---|---|
| `kmicro.h` | The contract between the compiled code, the runtime and the board: object layouts, the board's functions and hooks, the runtime's C API. |
| `mm.c` | Memory: a static arena (`KM_HEAP_BYTES`, default 16 KB), objects 8-byte aligned, no per-object header beyond the type pointer. Precise mark-sweep, stop-the-world, non-moving. Roots are the shadow-stack frames the compiled code pushes, the registered globals, the thread-local slots, `kmicro_root` slots, StableRefs and an exception in flight. The collector runs only inside an allocation or an explicit `kmicro_gc()`; an interrupt handler that stores a reference while it marks makes it mark again. |
| `eh.c` | Exceptions: libgcc's ARM EHABI unwinder with kmicro's own personality routine. `try`/`catch`/`finally` work as on the JVM. An uncaught exception prints its type, its whole message, its stack trace and every cause, as `printStackTrace()` does ([below](#reading-a-stack-trace)). |
| `init.c`, `init_cxx.cpp` | Startup: the module initializers, the initialisation of file-level globals on first use (a failing initializer behaves as in the stock runtime), `kmicro_panic`. |
| `strings.c` | `String` (UTF-16, and the compiler's Latin-1 option: `kbuild.py --kotlinc -Xbinary=latin1Strings=true`), `toString`, `println`. |
| `types.c` | Type checks, identity hash codes, boxing caches, arrays, interface dispatch. |
| `numbers.c`, `kmath.c` | Numeric helpers and `kotlin.math` on newlib's libm. |
| `dtoa/`, `hexfloat.c` | `Double`/`Float` to and from `String` (Apache Harmony code, as in Kotlin/Native); `hexfloat.c` parses hexadecimal text without the Regex engine. |
| `time.c` | `kotlin.time` and the seed of `Random.Default`, on the board's clock hooks. |
| `system.c` | `Platform`, `exitProcess`, `readln`, `GC.schedule`, `Uuid.random`, on the board's input and entropy hooks. |
| `regex.c` | The natives of `RegexOption.CANON_EQ`, which throw `IllegalArgumentException`. |
| `unsupported.c` | The standard-library functions that need threads or an OS (`Worker`, `WeakReference`, heap tuning, ...): each stops the program with `... is not supported on kmicro`. `python tools/missing_natives.py` lists them. |
| `interop.c` | What cinterop needs: thread-state switches (nothing to do) and a small arena for `memScoped`, `cstr`, `nativeHeap` (`KM_INTEROP_BYTES`). |
| `atomic64.c` | 64-bit atomics (`AtomicLong`, `@Volatile` `Long` fields) on a CPU without 64-bit exclusive loads. |

## The board

The runtime asks the board for two functions, declared in [runtime/kmicro.h](../runtime/kmicro.h):

```c
void kmicro_puts(const char *s);                        /* println and error reports: a UART, semihosting, a log */
__attribute__((noreturn)) void kmicro_exit(int code);   /* the program stopped: reset, halt, or report */
```

Optional hooks give the program clocks, a random seed, entropy, console input and output with a length; without
them the runtime uses a weak default. [porting.md](porting.md#the-board-contract) lists them with their defaults.

Exit codes: `kmicro_panic` stops with 98, for an uncaught exception, an out-of-memory report, an unsupported API or
an allocation inside an interrupt handler. The QEMU start code stops with 99 for a CPU fault. `exitProcess(n)` and a
C `main` that returns `n` stop with `n`.

The start code enables the FPU in a naked `Reset_Handler` before any compiled C runs (LTO can inline floating-point
code into the C start function), copies `.data`, clears `.bss` and runs the constructors in `.init_array` (the
compiler registers the module initializers there); `kmicro_init()` then comes before the first Kotlin call.
[porting.md](porting.md#start-up) has the details. [targets/qemu-l475/start.c](../targets/qemu-l475/start.c), the
start code for QEMU, adds three optional parts: a fault report, MPU guards against stack overflow and null reads, and
clocks through semihosting. [examples/selftest/stm32l431/board.c](../examples/selftest/stm32l431/board.c) is the
start code of a real STM32L431. The `main()` of every C example begins with `kmicro_init()`;
[targets/common/kotlin_main.c](../targets/common/kotlin_main.c) is the C `main` of a Kotlin-only program.

## Sizes

The runtime's memory is static: the heap, the native-memory arena and the root tables are arrays in `.bss`. Each
size is a macro, set with `-D` when the runtime is compiled: `python tools/qbuild.py ... -D KM_HEAP_BYTES=32768`, or
the runtime's flags in a board build. When a table is full the program stops with a panic that names its macro,
such as `kmicro panic: too many globals (raise KM_GLOBALS, now 160)`.

| Macro | Default | RAM | What it sizes |
|---|---|---|---|
| `KM_HEAP_BYTES` | 16384 | the value | the Kotlin heap; when it runs out the program stops ([writing-kotlin.md](writing-kotlin.md#memory)) |
| `KM_INTEROP_BYTES` | 1024 | the value, when the program uses native memory or parses numbers | native memory: `nativeHeap`, `memScoped`, `cstr`, and the scratch memory of `toDouble()`; a request that does not fit throws `OutOfMemoryError` |
| `KM_GLOBALS` | 160 | 4 B each | reference globals, the standard library's included |
| `KM_C_ROOTS` | 16 | 4 B each | `kmicro_root()` slots: objects that C code holds |
| `KM_STABLE_REFS` | 16 | 8 B each | StableRefs alive at once |
| `KM_EH_DEPTH` | 4 | 104 B each | exceptions between their throw and the end of their catch at once: one for the thread code, one for each interrupt handler that throws while it has interrupted another throw |
| `KM_TLS_KEYS` | 8 | 12 B each | modules with thread-local globals |
| `KM_TLS_SLOTS` | 64 | 4 B each | thread-local reference slots, all modules together |
| `KM_MARK_STACK` | 96 | 4 B each | the collector's mark stack; not a limit: an overflow costs a rescan of the heap |
| `KM_GC_REMARKS` | 3 | none | how often an interrupt handler that stores references can make the collector mark again; the pass after that runs with interrupts masked |
| `KM_GC_STRESS` | off | none | `-D KM_GC_STRESS=1`: a full collection before every allocation, and freed memory overwritten; for tests |

Two limits are fixed in `runtime/eh.c`: a stack trace keeps at most 12 frames (`KM_TRACE_MAX`), and the
uncaught-exception report prints at most 8 exceptions of a cause chain (`KM_CAUSES_MAX`).

## Calling between C and Kotlin

**Kotlin calls C** through cinterop, as on any Kotlin/Native target: a `.def` file lists the headers, and Kotlin
calls `c.uart_send(...)`. `kbuild.py --def` runs cinterop and uses its klib (`-l` takes a klib made separately). The
compiler routes each call through a small bridge function. [toolchain/bridges.py](../toolchain/bridges.py) copies
those bridges out of the saved IR (`out.Codegen.ll` and the `LinkBitcodeDependencies` module), together with the
C-callable stubs of `staticCFunction` callbacks, the types they use and the metadata they need, so they are compiled
for Cortex-M as well. For a callback, C calls the stub, which calls the Kotlin side of the bridge in `k.o`.

```
python tools/kbuild.py build/app app.kt --def board.def -I include --c-api app.h --package app
```

kbuild then prints `bridges.o` next to `k.o`, and both are linked. [tests/cinterop](../tests/cinterop)
and [tests/cinterop_shapes](../tests/cinterop_shapes) are complete examples. An exception thrown inside a
`staticCFunction` does not reach a Kotlin `try` around the C call: the program stops with
`Uncaught Kotlin exception: ...` (exit 98), as on stock Kotlin/Native, so catch it inside the callback.

**C calls Kotlin** by symbol. A top-level function `fun gcChains(rounds: Int): Int` in package `selftest` is the
symbol `kfun:selftest#gcChains(kotlin.Int){}kotlin.Int`. C can declare it with that name as an assembler label, or
let the build give it a plain C name: `kbuild.py --c-api selftest.h --package selftest` reads the prototypes in the
header and adds `gc_chains` as an alias of `selftest.gcChains`. A firmware can keep its C API this way while its
implementation moves to Kotlin one module at a time.

- C names become lowerCamelCase Kotlin names: `gc_chains` is `gcChains`; `_IRQHandler` becomes `IrqHandler` and
  `_Handler` becomes `Handler` (`SysTick_Handler` is `sysTickHandler`, `USART1_IRQHandler` is `usart1IrqHandler`);
  an all-caps word keeps only its first capital (`TIM1_UP_TIM16_IRQHandler` is `tim1UpTim16IrqHandler`); an
  underscore stays between two numbers (`EXTI15_10_IRQHandler` is `exti15_10IrqHandler`). The spellings of earlier
  kmicro versions (`SysTickHandler`) still work, with a note. Two C names that give one Kotlin name are an error.
- clang reads the header with qbuild's flags and the `-I` folders: extern prototypes count, macros expand, `#if` is
  honoured, and the headers it includes do not count. A prototype without a Kotlin function stops the build.
- The prototype must match the Kotlin function as C calls it. Only primitives, unsigned numbers, `CPointer` and
  `NativePtr` can cross, with `Unit` or `Nothing` as the result type where there is none.
- `@CName("name")` on a Kotlin function gives it a C name the same way, with the same rule; a string or an object
  parameter is an error.
- `--init-all NAME` generates `void NAME(void)`, which initialises the globals of the package and its sub-packages:
  file-level ones, objects and companions. The header may declare it.
- **C holding a Kotlin object:** `StableRef.create(obj).asCPointer()` gives C a `void *` (callback user data, for
  example), `asStableRef<T>().get()` turns it back, and `dispose()` releases it. At most `KM_STABLE_REFS` (16) are
  alive at once. Using a reference after `dispose()` stops the program, as long as no later `StableRef.create` has
  taken its slot. C code can keep an object alive with `kmicro_root(&slot)` and `kmicro_unroot(&slot)`.

## Hardware access

Kotlin has no volatile memory access (`@Volatile` applies to properties only) and no inline assembly.
[support/hw.h](../support/hw.h) provides what is missing, one instruction each after LTO: `hw_rd32` / `hw_wr32`
(volatile register access), `mem_*` (plain memory shared with C), barriers, `WFI`, `PRIMASK` / `BASEPRI`, and the DWT
cycle counter (`hw_cycles_enable()`, `hw_cycles()`; QEMU does not model the DWT, so `hw_cycles()` stays 0 there).
Kotlin reaches them through cinterop: `kbuild.py --def support/hw.def` makes them the package `c` (`import c.*`).
`support/hw.c` is linked with the program: on QEMU it is one of qbuild's C files, on a board it is compiled with the
runtime's flags ([porting.md](porting.md#compiling-the-runtime)). A call such as `hw_wr32(RCC.CR, v)` becomes a single
`STR` in the Kotlin function that made it.

[tools/gen_regs.py](../tools/gen_regs.py) turns CMSIS device headers into Kotlin constants: register addresses
(`RCC.CR`), bit fields (`RCC_CR_HSION`) and IRQ numbers, only those the sources use. The addresses are computed from
the CMSIS struct layouts, so nothing is typed by hand. `--package` names the Kotlin package, `--sources` includes
the subfolders of the folder it names, and the folder of `--out` is created when it does not exist.

hw.h and gen_regs.py are part of kmicro. They were first written for the device firmware kmicro grew out of
([Origin](../README.md#origin)), which uses them too. [examples/irq](../examples/irq) uses both: registers
generated by gen_regs.py and a SysTick handler written in Kotlin.

## Interrupts

A Kotlin function can be an interrupt handler: name it after the vector (`fun usart1IrqHandler()`) and alias it with
`--c-api`. An interrupt can arrive while the collector is running, so a handler must not allocate. The runtime
stops with a panic when a handler allocates or collects, the runtime's own allocations included. A handler may read
and store references and use the atomics. [tools/isr_check.py](../tools/isr_check.py) finds allocation, boxing and
lazy initialisation on the paths from the handlers before the code runs. It takes the handlers from the vector
table; `--callback` adds functions reached through a pointer, and `--boxing` also fails on every call outside the
standard library that boxes an `Int`, `Long`, `Short` or `Byte`, in any code. It exits 0 when no handler reaches an
allocation, 1 when one does (or `--boxing` finds a box), and 2 when the image cannot be read or has no handler.
[examples/irq](../examples/irq) is a worked example, and [writing-kotlin.md](writing-kotlin.md#interrupt-handlers)
has the rules and the Kotlin constructs that allocate where it is not obvious.

## Reading a stack trace

An uncaught exception prints its type, its whole message and its stack trace, then each cause as
`Caused by: ...` with its own frames. The type is named as `Throwable.toString()` names it: the qualified name, the
simple name for a local class, `Throwable` for an anonymous object. Frames that a cause shares with the exception
above it become `... and N more common stack frames skipped`, as in `printStackTrace()`. The report allocates nothing.
It leaves out suppressed exceptions (`e.printStackTrace()` in a catch block shows them) and does not call a custom
`toString()`. A stack trace is a list of return addresses; [tools/symbolize.py](../tools/symbolize.py) names them from
the ELF.

Before the report, the hook set with `setUnhandledExceptionHook` runs, as on stock Kotlin/Native; if it throws, its
exception is reported instead. It may end the program itself with `terminateWithUnhandledException(it)`.
`processUnhandledException(e)` returns after a hook that returns, and otherwise reports and stops. Inside an
interrupt handler the Kotlin hook is skipped, because it may allocate; the C hook `kmicro_on_uncaught` runs after
the report in every case ([porting.md](porting.md#the-board-contract)). When no hook was ever set, the first
uncaught exception makes the standard library create its hook holder, two small objects; if the heap is full at
that moment, the program stops with the out-of-memory report instead.

The exceptions test ([tests/exceptions/exceptions.kt](../tests/exceptions/exceptions.kt)) ends with an uncaught
exception thrown three calls deep. Its output saved to a log file, then symbolized:

```
python tools/kbuild.py build/exc tests/exceptions/exceptions.kt
python tools/qbuild.py build/exc/exc.elf tests/exceptions/main.c build/exc/k.o -D KM_HEAP_BYTES=8192 --run > exc.log
python tools/symbolize.py build/exc/exc.elf exc.log
```

symbolize.py prints the log with the names added:

```
qbuild: exc.elf  text 54332  data 80  bss 10532  stack 81920
exception checks failed mask = 0  OK   (gcs=6)
now an uncaught one (expected to stop with a report):
Uncaught Kotlin exception: PanelError: panel error -5
    at 0x08009dfc  PanelError#<init>(kotlin.Int){}+0x1e4
    at 0x08002978  run_main+0x8b4
        run_main (main.c:21)
    at 0x08001942  start_c+0xaa
        start_c (start.c:71)
kmicro panic: uncaught Kotlin exception
qemu: exit 98
```

symbolize.py adds the function and the offset after each `at 0x...`. A trace address is a return address, so it
names the function that made the call; the offset is the return address's. The trace starts where the exception
was created, here in the constructor of `PanelError`. LTO inlined `uncaught`, `deep` and `check` into `main` of
`main.c`, and `main` into `run_main` of the start code, so the Kotlin functions fold into `run_main`. The C files are
compiled with `-g` by qbuild, hence `main.c:21`.

Compiled with debug information, the Kotlin frames come back:

```
python tools/kbuild.py build/exc tests/exceptions/exceptions.kt --kotlinc -g
python tools/qbuild.py build/exc/exc.elf tests/exceptions/main.c build/exc/k.o -D KM_HEAP_BYTES=8192 --run > exc.log
python tools/symbolize.py build/exc/exc.elf exc.log
```

symbolize.py prints the log with the names added:

```
qbuild: exc.elf  text 56444  data 80  bss 10532  stack 81920
exception checks failed mask = 0  OK   (gcs=6)
now an uncaught one (expected to stop with a report):
Uncaught Kotlin exception: PanelError: panel error -5
    at 0x0800a4cc  PanelError#<init>(kotlin.Int){}+0x1c0
    at 0x08002a48  run_main+0x984
        #check(kotlin.Int){} (exceptions.kt:6) [inlined]
        #deep(kotlin.Int;kotlin.Int){}kotlin.Int (exceptions.kt:7) [inlined]
        #uncaught(kotlin.Int){}kotlin.Int (exceptions.kt:40) [inlined]
        main (main.c:21) [inlined]
        run_main (start.c:61)
    at 0x08001942  start_c+0xaa
        start_c (start.c:71)
kmicro panic: uncaught Kotlin exception
qemu: exit 98
```

Under each frame, the functions inlined at that call are listed innermost first, each with its file and line,
then the function that holds them (`arm-none-eabi-addr2line -i`). kotlinc-native warns
`unsupported combination of flags: -opt and -g` and builds the program, here 2,112 bytes larger. The C files need
`-g` too, which qbuild gives them and which takes no flash: without it, the Kotlin functions that LTO inlined into a
C function (here into `run_main`) are not listed. On a board, compile the C files with `-g`
([porting.md](porting.md#compiling-the-runtime)), save what the UART printed and pass that file the same way; the
ELF must be the one the board runs.

symbolize.py also reads the log on stdin (`python tools/symbolize.py build/exc/exc.elf < exc.log`), or names
addresses given as arguments:

```
python tools/symbolize.py build/exc/exc.elf 0x08002a48
```

```
0x08002a48  run_main+0x984
        #check(kotlin.Int){} (exceptions.kt:6) [inlined]
        #deep(kotlin.Int;kotlin.Int){}kotlin.Int (exceptions.kt:7) [inlined]
        #uncaught(kotlin.Int){}kotlin.Int (exceptions.kt:40) [inlined]
        main (main.c:21) [inlined]
        run_main (start.c:61)
```

It reads the log as UTF-8: in Windows PowerShell, save the log with `| Out-File -Encoding utf8 exc.log` rather than
`>`, whose encoding depends on the PowerShell version and its settings. symbolize.py exits 1 when the ELF is missing
or unreadable and 2 for a bad argument.

A cause chain, from a Kotlin-only program:

```kotlin
// trace.kt
class SensorMissing(id: Int) : Exception("sensor $id not answering")

fun probe(id: Int, left: Int): Int {
    if (left == 0) throw IllegalStateException("boot failed at sensor $id", SensorMissing(id))
    return probe(id, left - 1) + id
}

fun main() {
    println(probe(3, 2))
}
```

```
python tools/kbuild.py build/trace trace.kt --kotlinc -g
python tools/qbuild.py build/trace/trace.elf targets/common/kotlin_main.c build/trace/k.o --run > trace.log
python tools/symbolize.py build/trace/trace.elf trace.log
```

symbolize.py prints the log with the names added:

```
qbuild: trace.elf  text 52692  data 80  bss 18724  stack 73728
Uncaught Kotlin exception: kotlin.IllegalStateException: boot failed at sensor 3
    at 0x08009a2c  #probe(kotlin.Int;kotlin.Int){}kotlin.Int+0x90
    at 0x080099cc  #probe(kotlin.Int;kotlin.Int){}kotlin.Int+0x30
    at 0x080099cc  #probe(kotlin.Int;kotlin.Int){}kotlin.Int+0x30
    at 0x08002128  run_main+0x64
        run_main (trace.kt:10)
    at 0x08001942  start_c+0xaa
        start_c (start.c:71)
Caused by: SensorMissing: sensor 3 not answering
    at 0x08009986  SensorMissing#<init>(kotlin.Int){}+0x1ea
    at 0x08009a22  #probe(kotlin.Int;kotlin.Int){}kotlin.Int+0x86
    at 0x080099cc  #probe(kotlin.Int;kotlin.Int){}kotlin.Int+0x30
    ... and 3 more common stack frames skipped
kmicro panic: uncaught Kotlin exception
qemu: exit 98
```

A trace keeps at most 12 frames, with no marker when it is cut.

**A CPU fault** is not an exception. On `qemu-l475` the start code prints a fault report and stops with exit 99
([porting.md](porting.md#optional-a-fault-report-and-mpu-guards) has the format). Here a constructor of `Base` calls
`describe()` before `Sub` has set `name`, so `name.length` reads through null:

```kotlin
// fault.kt
abstract class Base {
    init { println("Base sees " + describe()) }
    abstract fun describe(): String
}

class Sub(val name: String) : Base() {
    override fun describe() = "name of ${name.length} characters"
}

fun main() {
    println(Sub("x").describe())
}
```

```
python tools/kbuild.py build/fault fault.kt --kotlinc -g
python tools/qbuild.py build/fault/fault.elf targets/common/kotlin_main.c build/fault/k.o --run > fault.log
python tools/symbolize.py build/fault/fault.elf fault.log
```

symbolize.py prints the log with the names added:

```
qbuild: fault.elf  text 48316  data 80  bss 18724  stack 73728
kmicro fault: null pointer access (MemManage) at 0x080091b2  Sub#describe(){}kotlin.String+0xfe
    sp 0x20017ec8  lr 0x20000960  cfsr 0x00000082  hfsr 0x00000000  mmfar 0x0000000c  bfar 0x00000000
qemu: exit 99
```

The address of a fault report is the faulting instruction itself, not a return address, so symbolize.py looks it up
as it is. `mmfar` is the address that was read, 12 bytes past null. A stack overflow reports
`kmicro fault: stack overflow (MemManage), no stacked frame`: there is no PC to name.

A panic that knows where it happened ends with the address too, for example
`kmicro panic: allocation inside an interrupt handler at 0x0800...`; symbolize.py names the function that made the
call.

## Testing

- [tests/run_all.py](../tests/run_all.py) builds every test program and the examples, runs them on QEMU
  (`b-l475e-iot01a`, an emulated STM32L475; one test on `mps2-an386`) and compares each program's whole output with
  its file in `tests/expected/`. It also fails a program that does not fit the STM32L431 unless the test is marked
  large, and runs the tools (isr_check, symbolize, frames, gen_regs, missing_natives) on some of them. The programs
  run with `qbuild --icount`, so an interrupt test takes its ticks at the same instructions in every run; the `irq`
  example runs on the host's clock, as a user runs it.
- [tools/difftest.py](../tools/difftest.py) runs the programs in `tests/diff/` on the stock Kotlin/Native runtime
  of the host and on kmicro in QEMU, and requires byte-identical output: strings including emoji, collections,
  exceptions, initialisers, number formatting and parsing, sequences. The kmicro side is built as kbuild builds it,
  at the default 16 KB heap; a program that needs more says `// difftest: heap BYTES -- reason`, and
  `// difftest: large -- reason` allows an image above the STM32L431's 256 KB of flash and 64 KB of RAM (the report
  marks one without it `OVER`); `// difftest: ulp N -- reason` lets numbers differ by N units in the last place
  (`d_math`: kotlin.math is newlib's libm on kmicro). As run_all does, it fails an image with a stack frame larger
  than the 4 KB stack guard (`FRAME` in the report), unless the program says `// difftest: frame -- reason`.
  `--stress` collects at every allocation; the heap peak in the report is then the most the program had live at
  once, while without it the peak is often the heap size. The `d_known_*.kt` programs show what does not work and
  run only when named.
- `python -m unittest discover -s tests/unit` tests the tools.
- CI ([.github/workflows/ci.yml](../.github/workflows/ci.yml)) runs the unit tests and run_all, also with `--stress`,
  on every pull request, on Linux and (without `--stress`) on Windows, and difftest on main and once a week. Once a week it also runs the unit tests and run_all
  with the newest Kotlin release, in a job that may fail without failing the others.
- `python tools/missing_natives.py` lists the standard library's runtime functions that kmicro implements, does not
  support, or lacks.

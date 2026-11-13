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
runtime/*.c *.cpp  ── clang -flto ───────────────────────────────────┤
your C code        ── clang -flto (or gcc) ──────────────────────────┤
                                                                     ▼
                                                    ld.lld --lto-O2 ──▶ firmware.elf
```

[toolchain/kn.py](../toolchain/kn.py) holds these steps as functions. [tools/kbuild.py](../tools/kbuild.py) runs
them from the command line, and [tools/qbuild.py](../tools/qbuild.py) links the result for the QEMU target.

Link-time optimisation treats the runtime and the Kotlin code as one program. The runtime's hooks, such as the
frame push of the garbage collector or an array access, are inlined into the Kotlin functions that call them. For
that to work, retarget.py stamps the Kotlin functions with exactly the `target-cpu` / `target-features` attributes
clang gives the runtime. LLVM does not inline across functions with different attributes.

What retarget.py changes:

| Change | Why |
|---|---|
| target triple `thumbv7em-unknown-none-eabihf` | the code generator then emits Thumb-2 for Cortex-M |
| `target-cpu` / `target-features` = clang's Cortex-M4F values | LTO inlines runtime hooks into Kotlin code |
| `thread_local` removed (`--no-tls`) | one thread; no `__aeabi_read_tp` on bare metal |
| init-state loads made plain (`--single-core`) | each access to a file's globals checks its init state with an acquire load (a `DMB`); with one core and one thread a plain load is exact and can leave the loop |
| `minsize` everywhere except `--hot` functions (`--size`) | a firmware keeps real-time code fast and the rest small |

## The runtime

[runtime/](../runtime) replaces the stock Kotlin/Native runtime. A file that follows a stock source names it in its
first comment.

| File | What it does |
|---|---|
| `mm.c` | Memory: a static arena (`KM_HEAP_BYTES`, default 16 KB), objects 8-byte aligned, no per-object header beyond the type pointer. Precise mark-sweep, stop-the-world, non-moving. Roots are the shadow-stack frames the compiled code pushes, the registered globals, the thread-local slots and an exception in flight. The collector runs only inside an allocation or an explicit `kmicro_gc()`. |
| `eh.c` | Exceptions: libgcc's ARM EHABI unwinder with kmicro's own personality routine. `try`/`catch`/`finally` work as on the JVM. An uncaught exception prints its type, its whole message, its stack trace and every cause, as `printStackTrace()` does (addresses; [tools/symbolize.py](../tools/symbolize.py) turns them into function names, and LTO folds inlined functions into their callers). |
| `init.c`, `init_cxx.cpp` | Startup: the module initializers, the initialisation of file-level globals on first use (a failing initializer behaves as in the stock runtime), `kmicro_panic`. |
| `strings.c` | `String` (UTF-16; the compiler's Latin-1 string option is implemented too, but no kmicro tool sets it and it is untested), `toString`, `println`. |
| `types.c` | Type checks, identity hash codes, boxing caches, arrays. |
| `numbers.c`, `kmath.c` | Numeric helpers and `kotlin.math` on newlib's libm. |
| `dtoa/` | `Double`/`Float` to and from `String` (Apache Harmony code, as in Kotlin/Native). |
| `interop.c` | What cinterop needs: thread-state switches (nothing to do) and a small arena for `memScoped`, `cstr`, `nativeHeap`. |
| `atomic64.c` | 64-bit atomics (`AtomicLong`, `@Volatile` `Long` fields) on a CPU without 64-bit exclusive loads. |

The runtime asks the board for two functions:

```c
void kmicro_puts(const char *s);   /* println and error reports: a UART, semihosting, a log buffer */
void kmicro_exit(int code);        /* the program stopped (98 = kmicro_panic): reset, halt, or report */
```

An uncaught exception also stops with 98. The QEMU start code adds 99 for a CPU fault.

Your startup code enables the FPU before any compiled C runs (LTO can inline floating-point code into the startup
function), copies `.data`, clears `.bss` and runs the constructors in `.init_array` (the compiler registers the
module initializers there); `kmicro_init()` then comes before the first Kotlin call.
[examples/selftest/stm32l431/board.c](../examples/selftest/stm32l431/board.c) does this for an STM32L431.
[targets/qemu-l475/start.c](../targets/qemu-l475/start.c) is the startup for QEMU: a naked `Reset_Handler` enables
the FPU before any C runs, and it adds a fault report, MPU guards against stack overflow and null reads, and clocks
through semihosting. The `main()` of every C example begins with `kmicro_init()`;
[targets/common/kotlin_main.c](../targets/common/kotlin_main.c) is the C `main` of a Kotlin-only program.

## Calling between C and Kotlin

**Kotlin calls C** through cinterop, as on any Kotlin/Native target: a `.def` file lists the headers, and Kotlin
calls `c.uart_send(...)`. `kbuild.py --def` runs cinterop and uses its klib (`-l` takes a klib made separately). The
compiler routes each call through a small bridge function; [toolchain/bridges.py](../toolchain/bridges.py) extracts
those bridges, and the C-callable stubs of `staticCFunction` callbacks, from the saved IR, so they are compiled for
Cortex-M as well.

```
python tools/kbuild.py build/app app.kt --def board.def -I include --c-api app.h --package app
```

kbuild then prints `bridges.o` next to `k.o`, and both are linked. [tests/cinterop](../tests/cinterop)
and [tests/cinterop_shapes](../tests/cinterop_shapes) are complete examples.

**C calls Kotlin** by symbol. A top-level function `fun gcChains(rounds: Int): Int` in package `selftest` is the
symbol `kfun:selftest#gcChains(kotlin.Int){}kotlin.Int`. C can declare it with that name as an assembler label, or
let the build give it a plain C name: `kbuild.py --c-api selftest.h --package selftest` reads the prototypes in the
header and adds `gc_chains` as an alias of `selftest.gcChains` (snake_case to camelCase;
`USART1_IRQHandler` becomes `usart1IrqHandler`). A prototype without a Kotlin function stops the build. A firmware can
keep its C API this way while its implementation moves to Kotlin one module at a time.

## Hardware access

Kotlin has no volatile memory access (`@Volatile` applies to properties only) and no inline assembly.
[support/hw.h](../support/hw.h) provides what is missing, one instruction each after LTO: `hw_rd32` / `hw_wr32`
(volatile register access), `mem_*` (plain memory shared with C), barriers, `WFI`, `PRIMASK` / `BASEPRI`. Kotlin
reaches them through cinterop with [support/hw.def](../support/hw.def), and `hw.c` is linked with the program. A call
such as `hw_wr32(RCC.CR, v)` becomes a single `STR` in the Kotlin function that made it.

[tools/gen_regs.py](../tools/gen_regs.py) turns CMSIS device headers into Kotlin constants: register addresses
(`RCC.CR`), bit fields (`RCC_CR_HSION`) and IRQ numbers, only those the sources use. The addresses are computed from
the CMSIS struct layouts, so nothing is typed by hand.

hw.h and gen_regs.py are part of kmicro. They were first written for the device firmware kmicro grew out of
([Origin](../README.md#origin)), which uses them too. [examples/irq](../examples/irq) uses both: registers
generated by gen_regs.py and a SysTick handler written in Kotlin.

## Interrupts

A Kotlin function can be an interrupt handler: name it after the vector (`fun usart1IrqHandler()`) and alias it with
`--c-api`. An interrupt can arrive while the collector is running, so a handler must not allocate. The runtime
stops with a panic when a handler allocates or collects, the runtime's own allocations included.
[tools/isr_check.py](../tools/isr_check.py) finds allocation, boxing and lazy initialisation on the paths from the
handlers before the code runs. It takes the handlers from the vector table; `--callback` adds functions reached
through a pointer. [examples/irq](../examples/irq) is a worked example, and [writing-kotlin.md](writing-kotlin.md)
lists the Kotlin constructs that allocate where it is not obvious.

## Testing

- [tests/run_all.py](../tests/run_all.py) builds every test program and the examples and runs them on QEMU
  (`b-l475e-iot01a`, an emulated STM32L475).
- [tools/difftest.py](../tools/difftest.py) runs the programs in `tests/diff/` on the stock Kotlin/Native runtime
  of the host and on kmicro in QEMU (at the default 16 KB heap unless a program asks for more), and requires
  byte-identical output: strings including emoji, collections, exceptions, initialisers, number formatting and
  parsing, sequences.
- `python -m unittest discover -s tests/unit` tests the tools.

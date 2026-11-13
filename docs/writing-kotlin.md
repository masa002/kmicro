# Writing Kotlin® for a microcontroller

Most Kotlin runs on kmicro unchanged: classes, interfaces, generics, lambdas, collections, strings, exceptions,
coroutines (see [examples/selftest](../examples/selftest), `tests/diff` and the feature list in
[kotlin-support.md](kotlin-support.md)). What changes is the cost of things:
64 KB of RAM, a heap that never moves objects, interrupt handlers that must not allocate, and a CPU at 16-80 MHz.

The rules below come from a device firmware with 24 Kotlin modules on an STM32L431 (64 KB RAM, 256 KB flash) and
from kmicro's own tests. That firmware is not part of this repository, so the numbers taken from it are reported,
not reproducible here. Times are at 16 MHz on the STM32L431. Sizes and instruction counts were measured on QEMU's
emulated STM32L475 (`qemu-l475`, the target qbuild links for) with the current runtime.

## Memory

The RAM holds `.data`, `.bss` and the stack. `.bss` holds the Kotlin heap, a fixed arena of `KM_HEAP_BYTES` (16 KB
by default), and the runtime's tables; the stack is the RAM that is left above it. Objects live on the heap; local
arrays of constant size can live on the stack (below).

What common standard-library features cost: a program that prints one line and then uses the feature once,
compared with the same program without it.

| Feature | Flash (`--size`) | Heap kept | Heap peak | Stack |
|---|---|---|---|---|
| one `Regex`: `Regex("[a-z]+[0-9]").containsMatchIn("abc1")` | 315.4 KB (191.6 KB) | 11,768 B | 13,360 B | 4,684 B |
| three small `Regex` patterns | 316.6 KB (192.1 KB) | 12,080 B | 16,344 B: out of memory on the default 16 KB heap, runs at 20 KB | 4,748 B |
| `"3.14".toDouble()` | 48.6 KB (42.5 KB), and 1 KB of RAM for the native-memory arena | 48 B | 136 B | 1,380 B |
| `"Grüße".uppercase()`, `"ÉCOLE".lowercase()`; ASCII text takes the same flash | 43.4 KB (33.9 KB) | 0 B | 56 B: the result strings | 444 B |
| `Char.isLetter()` on `'é'` and `'ж'` | 3.6 KB (3.4 KB) | 0 B | 0 B | 172 B |
| `Char.category` | 31.0 KB (23.5 KB) | 984 B: the 30 `CharCategory` entries | 984 B | 860 B |
| `val buf = ByteArray(4096)` in a function | 0.4 KB (0.1 KB) | 0 B | 0 B | 4,148 B |
| one `throw`, caught in the same function | 0.5 KB (0.3 KB) | 0 B | 112 B: the exception and its stack trace | 1,056 B |

- **Flash** is the growth of the image, without and with `kbuild.py --size`. Parts are shared: the features do not
  add up. A program that uses one `Regex` is 365 KB of flash (234 KB with `--size`), against the STM32L431's 256 KB.
- **Heap kept** is still live after the call and a full collection: tables the standard library keeps for good.
- **Heap peak** is the most live data during the call, measured with `-D KM_GC_STRESS=1` (a collection before every
  allocation). A heap needs more than that, because free memory comes in pieces: three `Regex` patterns peak at
  16,344 B and stop on the 16 KB heap with
  `kmicro: out of memory: wanted 72 B, live after GC 16160 of 16384 B, largest free 32 B in 14 free blocks`.
- **Stack** is the deepest the stack went below the caller, a collection inside the call included.
- Number parsing (`toDouble`, `toFloat`, `toDoubleOrNull`) does not use `Regex`. Its scratch memory comes from the
  1 KB native-memory arena (`KM_INTEROP_BYTES`), not from the heap.
- Case mapping and character classes read their tables from flash; only `Char.category` puts something on the heap.

1. **Allocate up front.** The collector does not move objects, so a list that keeps growing fragments the heap. Keep
   buffers in arrays sized at start, and use ring buffers for queues.
2. **An allocation may run a full collection** (1.8 ms for a 16 KB heap). Keep allocation out of timing-critical
   code.
3. **Size the heap from `live_peak_bytes`, with a margin.** `kmicro_stats()` reports it: the most live data a
   collection found. It is a lower bound (live data between two collections can be higher) and 0 before the first
   collection. `peak_bytes` counts garbage too, so it reaches the heap size at the first collection. The selftest
   prints both: `heap 16384 B, peak 16384 B, live peak 3584 B`. Run the program once with `-D KM_GC_STRESS=1`
   (`python tests/run_all.py --stress` does this for the tests): a collection before every allocation makes
   `live_peak_bytes` the true peak. Set the heap with `-D KM_HEAP_BYTES=N` when the runtime is compiled.
4. **Keep big buffers off the stack.** Kotlin/Native puts a local array of constant size that never leaves its
   function on the stack, up to 64 KB per function. kbuild warns above 512 bytes (`--stack-array-limit BYTES` sets
   the limit, `--stack-array-error` makes it an error), and `tools/frames.py` lists the largest frames of the linked
   image, after LTO has merged functions. Keep big buffers in a top-level `val` or a class field.

   ```kotlin
   // buf.kt
   fun checksum(): Int {
       val buf = ByteArray(4096)
       for (i in buf.indices) buf[i] = (i * 7).toByte()
       return buf.sum()
   }

   fun main() {
       println(checksum())
   }
   ```

   ```
   $ python tools/kbuild.py build/buf buf.kt
   kotlinc-native: compiling 1 file...
   single-core: 113 init-state loads made plain
   kmicro: warning: checksum() puts arrays on the stack: ByteArray(4096) 4096 B (limit 512 B)
   A local array of constant size that never leaves its function lives on the stack (Kotlin/Native, up to 64 KB per function). Keep a big buffer in a top-level val or a class field; --stack-array-limit sets the limit. tools/frames.py shows the frames after linking.
   build\buf\k.o
   $ python tools/qbuild.py build/buf/buf.elf targets/common/kotlin_main.c build/buf/k.o
   qbuild: buf.elf  text 49100  data 80  bss 18864  stack 79820
   $ python tools/frames.py build/buf/buf.elf --top 3
   largest stack frames of buf.elf (bytes a call takes, LTO-merged):
       4160  run_main
       1024  unwind_phase2_forced
        600  __gnu_Unwind_Backtrace
   ```

   `checksum()` was inlined into `run_main`, the start code's call of `main`. frames.py reads each function's
   prologue up to its first call, so it also sees a prologue placed after an early return. `--limit BYTES` makes it
   exit 1 when a frame is larger.
5. **Use loops, or `tailrec`, instead of deep recursion.** There is no `StackOverflowError`. On `qemu-l475` an MPU
   guard below the stack stops the program with `kmicro fault: stack overflow` (exit 99) before the stack reaches
   `.bss`; a board without such a guard ([porting.md](porting.md#optional-a-fault-report-and-mpu-guards)) lets the
   stack run into the heap. A frame larger than the 256-byte guard can jump it. qbuild's size line shows the RAM above
   `.bss` (`stack 79820` above); on `qemu-l475` the guard and its alignment take up to 511 bytes of it (460 here).
   Reading through null is not an exception either: a property read before its initializer ran (a constructor
   that calls an overridden function) or a null C pointer stops the program on `qemu-l475` with
   `kmicro fault: null pointer access`, exit 99, not with a `NullPointerException`.
6. **Put large temporaries in a helper function.** A local stays reachable until its function returns, even after
   its last use, so a long function keeps every object it made. Moved into a function of its own, the temporary is
   garbage once that function returns.

When the heap runs out, the program stops; it cannot catch this:

```
kmicro: out of memory: wanted 72 B, live after GC 16160 of 16384 B, largest free 32 B in 14 free blocks
kmicro panic: out of memory
```

Read it this way: when "live after GC" is close to the heap size, the heap is too small for what the program keeps.
When it is well below the heap size but "largest free" is smaller than "wanted", the heap is fragmented: the free
memory is there, in pieces too small for the request. A single request larger than the whole heap throws
`OutOfMemoryError` instead, and that one can be caught: `IntArray(5000)` kept in a top-level `var` asks for 20,008
bytes, more than the 16 KB heap.

Native memory (`nativeHeap`, `memScoped`, `cstr`) comes from its own arena of `KM_INTEROP_BYTES` (1 KB), which
`toDouble` also uses for scratch. Freed blocks are reused in any order and merged with free neighbours. A request that
does not fit throws `OutOfMemoryError("unable to allocate native memory")`; an alignment above 8 bytes is not
supported and stops the program, and so does freeing a block twice, unless the block was handed out again in
between.

The runtime's other tables have fixed sizes too, each settable with `-D`; a full one stops the program with a panic
that names its macro, such as `too many globals (raise KM_GLOBALS, now 160)`.
[how-it-works.md](how-it-works.md#sizes) lists them all.

## Interrupt handlers

A handler can run while the collector is working, and the heap is not reentrant, so **a handler must not allocate**.
The runtime checks every allocation, its own included, and every collection, and stops the program when one comes
from a handler:

```
kmicro panic: allocation inside an interrupt handler at 0x0800....
kmicro panic: garbage collection inside an interrupt handler at 0x0800....
```

`python tools/symbolize.py app.elf log.txt` names the function at that address. Before the program runs,
[tools/isr_check.py](../tools/isr_check.py) finds such paths in the machine code: `python tools/isr_check.py app.elf`
follows every entry of the vector table, so handlers aliased with `--c-api` are found too; `--callback NAME` adds a
function that handlers reach only through a pointer ([how-it-works.md](how-it-works.md#interrupts)).

What a handler may do:

- **Read and store object references**: fields, array elements, globals. When a handler stores a reference while the
  collector is marking, the collector marks again; after `KM_GC_REMARKS` passes (3) it marks the last time with
  interrupts masked. This costs one byte store per reference store. C code that stores a Kotlin reference from a
  handler calls `km_ref_stored()` ([runtime/kmicro.h](../runtime/kmicro.h)).
- **Use the atomics**: `AtomicInt`, `AtomicLong`, `AtomicReference`, the atomic arrays, and `@Volatile` fields of any
  type. They are atomic against handlers: 32-bit values and references with LDREX/STREX (an interrupt in between
  makes the update retry), 64-bit values with interrupts masked.
- **Use native memory** with `nativeHeap.alloc` and `nativeHeap.free`: the arena masks interrupts. Not `memScoped` or
  `cstr`, which may create Kotlin objects.
- **Print a string that already exists**: `println` of it does not allocate.

What a handler must not do:

- **Create an object**, including the runtime's own allocations: `Int.toString()`, string templates and
  concatenation, decoding UTF-8, the stack trace of a new exception.
- **Run a collection**: `GC.collect()` and `kmicro_gc()` stop the program. `GC.schedule()` does nothing inside a
  handler.
- **Use a file's globals for the first time** (rule 11): that initialises them, which allocates, and stops the
  program with `Kotlin globals first used inside an interrupt handler`.

An exception that escapes a handler is reported and stops the program (exit 98). The Kotlin hook set with
`setUnhandledExceptionHook` does not run for it, because it may allocate; the C hook `kmicro_on_uncaught`
([porting.md](porting.md#the-board-contract)) does. [examples/irq](../examples/irq) is a worked example: a SysTick
handler written in Kotlin that touches registers and keeps its state in `@Volatile` fields.

Allocations hide in these places:

7. **`==` and `!=` on `UInt`, `UByte`, `UShort` box their operands.** Compare `a.toInt() == b.toInt()`.
8. **Nullable unsigned types (`UInt?`) are boxed.** Use a sentinel value instead.
9. **`throw` allocates the exception, and `IntArray.fill()` can allocate too.** Return an error code, and write a loop.
10. **`toLong()` on a nullable `CPointer`** initialises the `NativePtr` companion object. Keep pointers non-null.
11. **The first use of a file's globals initialises the whole file.** Generate a boot-time initialiser
    (`kbuild.py --init-all kt_init_all`; the `--c-api` header may declare it) and call it before enabling
    interrupts.

## Speed

12. **Exceptions are for errors.** One throw and catch took about 1.6 ms in the recorded run, which still walked some
    stack frames more than once. On QEMU the same check now executes 9,853 instructions: 7,131 to create the
    exception with its message and stack trace, 2,722 from the throw to the catch. The unwinder reads its tables
    from flash.
13. **Hoist globals and arrays into locals before a loop,** and check the size once before it. LLVM then drops the
    bounds check of every element.
14. **Mark small per-element helpers `inline`.**
15. **`@Volatile` costs a `DMB` barrier on every access.** Use it for fields that an interrupt handler writes, and
    nowhere else.
16. **A function that holds object references sets up a garbage-collector frame on entry.** On a path with a
    budget of a few microseconds, use primitives and `hw_*` calls only. One such path in the firmware took 475
    cycles in C and 714 in Kotlin written this way (990 before).
17. **Build with `--size --hot REGEX`:** minimum size everywhere, full speed for the functions the regex matches
    (interrupt handlers and the code they call). The regex matches the symbol as Kotlin/Native writes it
    (`kfun:app#sysTickHandler(){}`), so `^` and `$` work; kbuild stops when it matches nothing.

## Size

18. **`data class` and `enum class` generate many members** (`toString`, `equals`, `hashCode`, `copy`,
    `componentN`, `values`, `valueOf`, `entries`). The firmware saved 9.5 KB by using plain classes and `Int`
    constants instead.
19. **`const val MASK = 1u shl 3` is not a constant expression.** Write the literal: `const val MASK = 0x8u`.
20. **Mind the big features**: `Regex`, case mapping and `Char.category` cost tens to hundreds of KB of flash (the
    table under [Memory](#memory)).

## Hardware

21. **Reach registers through `hw_rd32` / `hw_wr32`** ([support/hw.h](../support/hw.h)), never through a plain
    `CPointer` read. Kotlin has no volatile memory access: the optimiser may merge or drop an ordinary one.
    `kbuild.py --def support/hw.def` makes them the Kotlin package `c`, and `support/hw.c` is linked with the program
    ([examples/irq](../examples/irq)).
22. **Generate register names from the vendor's CMSIS headers** with [tools/gen_regs.py](../tools/gen_regs.py)
    instead of typing addresses.

## Build

- kbuild shows the compiler's warnings and errors on stderr.
- A public top-level function whose backtick name contains a space breaks the C export of Kotlin/Native
  (`-p static`); kbuild shows the error with a hint. Make such a function `internal` or `private`.
- `kbuild.py --kotlinc ARG` passes an option to kotlinc-native, for example `--kotlinc -opt-in=...`.
- An API that needs threads or an operating system stops the program with
  `kmicro panic: <API> is not supported on kmicro` (exit 98). `RegexOption.CANON_EQ` is the exception: it throws an
  `IllegalArgumentException` that can be caught.

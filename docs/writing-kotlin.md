# Writing Kotlin® for a microcontroller

Most Kotlin runs on kmicro unchanged: classes, interfaces, generics, lambdas, collections, strings, exceptions,
coroutines (see [examples/selftest](../examples/selftest), `tests/diff` and the feature list in
[kotlin-support.md](kotlin-support.md)). What changes is the cost of things:
64 KB of RAM, a heap that never moves objects, interrupt handlers that must not allocate, and a CPU at 16-80 MHz.

Each rule below was found on real hardware, in a device firmware with 24 Kotlin modules on an STM32L431 (64 KB RAM,
256 KB flash). That firmware is not part of this repository, so its numbers below are reported, not reproducible
here. The times are at 16 MHz.

## Memory

1. **Allocate up front.** The heap is a fixed arena (`KM_HEAP_BYTES`) and the collector does not move objects, so a
   list that keeps growing fragments it. Keep buffers in arrays sized at start, and use ring buffers for queues.
2. **An allocation may run a full collection** (1.8 ms for a 16 KB heap). Keep allocation out of timing-critical
   code; `kmicro_stats()` reports the heap's use and peak.

## Interrupt handlers

A handler can run while the collector is working, so it must not allocate. The runtime stops with a panic when
Kotlin code in a handler allocates (allocations inside runtime functions are not caught yet), and
[tools/isr_check.py](../tools/isr_check.py) finds such paths in the machine code before the program runs: name each
Kotlin handler with `--callback` and its compiler symbol ([how-it-works.md](how-it-works.md#interrupts)).
A handler may read object references, but storing one into a field or an array can let a collection it interrupted
free a live object, so keep handler state in primitives and primitive arrays. Allocations hide in these places:

3. **`==` and `!=` on `UInt`, `UByte`, `UShort` box their operands.** Compare `a.toInt() == b.toInt()`.
4. **Nullable unsigned types (`UInt?`) are boxed.** Use a sentinel value instead.
5. **`throw` allocates the exception, and `IntArray.fill()` can allocate too.** Return an error code, and write a loop.
6. **`toLong()` on a nullable `CPointer`** initialises the `NativePtr` companion object. Keep pointers non-null.
7. **The first use of a file's globals initialises the whole file.** Generate a boot-time initialiser
   (`kbuild.py --init-all kt_init_all`) and call it before enabling interrupts.

## Speed

8. **Exceptions are for errors.** One throw and catch took about 1.6 ms in the recorded run, which still walked some
   stack frames more than once; even without that, the unwinder reads its tables from flash.
9. **Hoist globals and arrays into locals before a loop,** and check the size once before it. LLVM then drops the
   bounds check of every element.
10. **Mark small per-element helpers `inline`.**
11. **`@Volatile` costs a `DMB` barrier on every access.** Use it for fields that an interrupt handler writes, and
    nowhere else.
12. **A function that holds object references sets up a garbage-collector frame on entry.** On a path with a
    budget of a few microseconds, use primitives and `hw_*` calls only. One such path in the firmware took 475
    cycles in C and 714 in Kotlin written this way (990 before).
13. **Build with `--size --hot REGEX`:** minimum size everywhere, full speed for the functions the regex matches
    (interrupt handlers and the code they call).

## Size

14. **`data class` and `enum class` generate many members** (`toString`, `equals`, `hashCode`, `copy`,
    `componentN`, `values`, `valueOf`, `entries`). The firmware saved 9.5 KB by using plain classes and `Int`
    constants instead.
15. **`const val MASK = 1u shl 3` is not a constant expression.** Write the literal: `const val MASK = 0x8u`.

## Hardware

16. **Reach registers through `hw_rd32` / `hw_wr32`** ([support/hw.h](../support/hw.h)), never through a plain
    `CPointer` read. Kotlin has no volatile memory access: the optimiser may merge or drop an ordinary one.
17. **Generate register names from the vendor's CMSIS headers** with [tools/gen_regs.py](../tools/gen_regs.py)
    instead of typing addresses.

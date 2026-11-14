# selftest

The Kotlin features a firmware leans on, one function each, checked from C: virtual calls, garbage collection
through a small heap, strings, exceptions, a coroutine resumed by events, a full collection.

On the emulator (QEMU's STM32L475 board):

```
python tools/kbuild.py build/selftest examples/selftest/selftest.kt --c-api examples/selftest/selftest.h --package selftest
python tools/qbuild.py build/selftest/selftest.elf examples/selftest/main.c build/selftest/k.o --run
```

After the lines of the build, ending with `qbuild: selftest.elf  text 132956  data 88  bss 18800  stack 73728`, the
program prints this, and qbuild ends with `qemu: exit 0`:

```
=== kmicro self-test: official Kotlin/Native 2.4.21 output on a Cortex-M4 ===
  PASS  runtime init (module initializers)
Hello from Kotlin/Native 2.4.21 on a bare Cortex-M4 (no OS, kmicro runtime)
  PASS  println from Kotlin
  PASS  classes, interface, virtual calls (= 45)
  PASS  garbage collection, 6000+ objects
  PASS  strings (10 checks, UTF-16, JVM hashCode)
  PASS  exceptions (10 checks, 200+ throws)
  PASS  one throw + catch
  PASS  coroutine: 300 suspend/resume cycles
  PASS  one full GC

heap 16384 B, peak 16384 B, live peak 3584 B, objects 9599, collections 12, freed 9574
result: ALL PASS
```

Each line is a check that can fail; the exit code is the number of failed checks.

| Line | Passes when |
|---|---|
| runtime init | `kmicro_init()` ran the module initializers: the standard library registered its thread-local slots |
| println from Kotlin | `hello()` returns |
| classes, interface, virtual calls | three shapes behind an interface add up to 45 |
| garbage collection | `gc_chains(60)` sums every node it built (6000+ objects, most of them garbage at once) while the heap is collected again and again |
| strings | each of the 10 checks in `strings()` holds (it returns a bit mask of the failed ones) |
| exceptions | each of the 10 numbered checks in `exceptions()` holds; check k sets bit k - 1 of the result when it fails |
| one throw + catch | `throw_once(-1)` catches its exception |
| coroutine | 300 events resume the coroutine, and it adds up each one |
| one full GC | `kmicro_gc()` adds one collection and frees the garbage the checks left: `used_bytes` falls |

The last line is `kmicro_stats()`. `peak` counts garbage too: the collector runs only when the heap is full, so it
reaches the heap size. `live peak` is the most live data a collection found, the figure to size the heap from
([docs/writing-kotlin.md](../../docs/writing-kotlin.md#memory)).

`python tests/run_all.py selftest` builds and runs the same program as part of the test suite.

## On an STM32L431

[stm32l431/](stm32l431) runs the same checks on a real STM32L431 at 16 MHz and times each one with the CPU's cycle
counter. `board.c` takes the place of `main.c` and of the QEMU start code: start-up, the clock, output on USART1,
and the timing. `stm32l431.ld` is its linker script.

```
python examples/selftest/stm32l431/build.py
```

It prints what the image takes, `selftest.elf: flash 134660 B of 256 KB, RAM 18628 B of 64 KB (the rest is stack)`,
and the path of the .hex file. Write `build/stm32l431/selftest.hex` to the board, open a terminal on USART1 (TX on
PA9) at 115200 8N1 and reset the board. Each check line then ends with its time in microseconds. The heap statistics
are the same as on the emulator: the collector does the same work on both. [docs/porting.md](../../docs/porting.md)
explains each part of such a board build.

[stm32l431-report.txt](stm32l431-report.txt) is a recorded run; its header says how and when it was recorded. It
predates the checks above: there, the runtime-init and full-GC lines always passed, the exceptions line said 9
checks, and the heap line had no live peak.

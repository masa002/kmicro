# Porting kmicro to a board

On QEMU, `tools/qbuild.py` compiles the runtime, adds the start code and links everything. On a board, your build
does the same with four parts:

- the Kotlin code: the `k.o` (and, when the Kotlin code calls C, the `bridges.o`) that `tools/kbuild.py` prints;
- the runtime: [runtime/](../runtime), compiled with clang;
- the board's C code: start-up, the two functions the runtime calls, and any drivers;
- a linker script.

Two references in the repository do all of this. [targets/qemu-l475](../targets/qemu-l475) (`start.c`, `l475.ld`)
is what qbuild links for the emulated STM32L475. [examples/selftest/stm32l431](../examples/selftest/stm32l431)
(`board.c`, `stm32l431.ld`, `build.py`) is a complete build for a real STM32L431.

## The board contract

[runtime/kmicro.h](../runtime/kmicro.h) declares it. A board file that includes `kmicro.h` needs no other
declaration. Two functions are required; without them the link fails:

```c
void kmicro_puts(const char *s);                        /* a NUL-terminated UTF-8 string: println, reports, panics */
__attribute__((noreturn)) void kmicro_exit(int code);   /* the program stopped: reset, halt or report; never returns */
```

`kmicro_exit` gets 98 from `kmicro_panic`: an uncaught exception, an out-of-memory report, an API that kmicro does
not support, an allocation inside an interrupt handler. `exitProcess(n)` passes `n`, and the start code passes the
return value of `main`. The QEMU start code also uses 99, for a CPU fault (below).

The other hooks are optional. The runtime has a weak default for each, so a board defines only the ones it has:

| Hook | Used by | Without it |
|---|---|---|
| `int64_t kmicro_time_ns(void)` | `measureTime`, `TimeSource.Monotonic`: a monotonic clock, any origin | the program stops with `kmicro panic: measureTime and TimeSource.Monotonic need the board clock: int64_t kmicro_time_ns(void)` |
| `int64_t kmicro_wall_time_ns(void)` | `Clock.System`: nanoseconds since 1970-01-01 UTC | the program stops with a panic that names the hook |
| `uint64_t kmicro_random_seed(void)` | the seed of `Random.Default` | 0: `Random.Default` repeats its sequence after every reset (`Random(seed)` needs no hook) |
| `void kmicro_random_bytes(void *buf, size_t n)` | `Uuid.random()`: a true entropy source, such as a hardware random number generator | the program stops with a panic that names the hook |
| `int kmicro_getc(void)` | `readln`, `readlnOrNull`, `readLine`: the next input byte, waiting if needed; -1 at the end of the input | -1: `readlnOrNull()` returns null, `readln()` throws `ReadAfterEOFException` |
| `void kmicro_write(const char *buf, size_t n)` | `println`: UTF-8 text with a length, which may hold U+0000 | `kmicro_puts` once per chunk of up to 64 bytes, with U+0000 dropped |
| `void kmicro_on_uncaught(ObjHeader *e)` | an uncaught exception, after its report and before the panic, also inside an interrupt handler | nothing |

The runtime provides `kmicro_init()`, `kmicro_gc()`, `kmicro_stats()`, `kmicro_put_int()`, `kmicro_panic()`,
`kmicro_root()` / `kmicro_unroot()` and `km_ref_stored()` to the board and to any C code.

The QEMU start code writes through semihosting (`SYS_WRITE0`), exits with `SYS_EXIT_EXTENDED`, and reads the
host's clocks through semihosting for the two clocks and the seed, so SysTick stays free for the program. The
STM32L431 `board.c` writes to USART1, and its `kmicro_exit` prints the code and waits.

## Start-up

The start code runs these steps, in this order:

1. **`Reset_Handler` turns the FPU on before any compiled C code runs.** The compiler target is hard-float. With
   LTO, code that uses floating-point registers can be inlined into the C start function, whose prologue then saves
   them (`vpush`), and with the FPU still off that is a fault. So `Reset_Handler` is naked: it sets CP10/CP11 to full
   access in CPACR and branches to the C start function.

   ```c
   __attribute__((naked)) void Reset_Handler(void)
   {
       __asm volatile("movw r0, #0xED88\n"
                      "movt r0, #0xE000\n"                         /* CPACR */
                      "ldr r1, [r0]\n"
                      "orr r1, r1, #(0xF << 20)\n"                  /* CP10/CP11 full access (FPU) */
                      "str r1, [r0]\n"
                      "dsb\n"
                      "isb\n"
                      "b start_c\n");
   }
   ```

2. **Copy `.data` and clear `.bss`.** `.bss` holds the Kotlin heap and the runtime's tables.
3. **Optionally**, point VTOR at the vector table, turn on the fault handlers and set up the MPU guards (below).
4. **Run the constructors in `.init_array`.** The compiler registers each Kotlin module's initializer there. Under
   LTO the linker usually resolves those registrations itself and leaves `.init_array` empty, as in every image
   built for this page; keep the loop anyway, for whatever is left there.
5. **Call `main` through a `noinline` function**, so that what LTO inlines into `main` stays out of the start
   function's frame.
6. **`main` calls `kmicro_init()` before the first Kotlin call.** It runs the module initializers.
   [targets/common/kotlin_main.c](../targets/common/kotlin_main.c) is the C `main` of a Kotlin-only program and does
   this.

`start_c` in [targets/qemu-l475/start.c](../targets/qemu-l475/start.c) and `board_start` in
[board.c](../examples/selftest/stm32l431/board.c) are a dozen lines each.

## Compiling the runtime

The runtime is compiled with clang: the LLVM that Kotlin/Native downloads, as `python toolchain/paths.py` shows.
The files are `runtime/*.c`, `runtime/*.cpp` and `runtime/dtoa/*.cpp`.

| Flags | Why |
|---|---|
| `--target=thumbv7em-none-eabihf -mcpu=cortex-m4 -mfpu=fpv4-sp-d16 -mfloat-abi=hard` | the Cortex-M4F, with the values retarget.py gives the Kotlin code (`cortex-m4f` in `CORES`, [toolchain/paths.py](../toolchain/paths.py)) |
| `-isystem <arm-none-eabi-gcc>/arm-none-eabi/include` | newlib's headers |
| `-O2 -flto` | the runtime is LLVM bitcode like `k.o`, so ld.lld optimises both as one program and inlines the runtime's hooks (the garbage collector's frame push, an array access, a reference store) into the Kotlin functions |
| `-ffunction-sections -fdata-sections` | `--gc-sections` drops what the program does not use |
| `-fexceptions -funwind-tables` | a Kotlin exception unwinds through runtime functions (`ThrowException`, the array functions). Without unwind tables they get `[cantunwind]` entries, the unwinder stops there, and every exception is reported as uncaught, exit 98. `runtime/eh.c` stops the build without `-fexceptions` |
| `-std=c++17 -fno-rtti` | the `.cpp` files only |
| `-g` (optional) | debug information, which takes no flash: with `kbuild.py --kotlinc -g`, `tools/symbolize.py` then names the Kotlin functions that LTO inlined into C functions, with file and line ([how-it-works.md](how-it-works.md#reading-a-stack-trace)). The exceptions test below, its Kotlin built with `--kotlinc -g`, is 56,444 bytes of text with or without `-g` on the C side |
| `-I runtime` | `kmicro.h` |
| `-D KM_HEAP_BYTES=32768`, ... | the sizes ([how-it-works.md](how-it-works.md#sizes)) |

Compiled without `-fexceptions`, clang stops at `eh.c`:

```
runtime/eh.c:23:2: error: "compile the kmicro runtime with -fexceptions -funwind-tables (docs/porting.md)"
```

arm-none-eabi-gcc cannot build the runtime: `eh.c` names two Kotlin functions by their symbols
(`kfun:kotlin.Throwable#<init>(kotlin.String?;kotlin.Throwable?){}`), and GNU as rejects those names
(`Error: junk at end of line, first unrecognized character is ':'`).

**Your own C code** goes through the same compiler and flags. A C function that a Kotlin exception can pass through
needs `-fexceptions -funwind-tables` too: one that throws, as the runtime's array functions do, or C called from
Kotlin that calls Kotlin again. When `runtime/types.c` alone is compiled without them, the out-of-bounds array
store that the exceptions test catches ends the program with
`Uncaught Kotlin exception: kotlin.ArrayIndexOutOfBoundsException`. [support/hw.c](../support/hw.c), when the
program uses [support/hw.h](../support/hw.h), is compiled the same way.

C compiled with arm-none-eabi-gcc links as ordinary objects (without `-flto`), if it does not name Kotlin symbols.
Watch two differences where its types meet Kotlin's:

- **Enums.** arm-none-eabi-gcc makes an enum as small as its values: `enum mode { MODE_A, MODE_B }` takes 1 byte
  and a struct of two of them 2 bytes. clang for the Cortex-M and cinterop take 4 and 8 bytes. Compile C that
  shares such types with Kotlin with `-fno-short-enums`.
- **`time_t`.** cinterop reads headers as for 32-bit Linux (glibc): `time_t` is 4 bytes and `timespec` 8 bytes in
  Kotlin, but newlib's are 8 and 16 bytes. Keep `time_t` and `timespec` out of the structs Kotlin and C share.

## The linker script

The sections, from [targets/qemu-l475/l475.ld](../targets/qemu-l475/l475.ld):

```
.isr_vector : { KEEP(*(.isr_vector)) } > FLASH
.text : { *(.text .text.*) *(.rodata .rodata.*) } > FLASH
.ARM.extab : { *(.ARM.extab* .gnu.linkonce.armextab.*) } > FLASH
.ARM.exidx : { __exidx_start = .; *(.ARM.exidx* .gnu.linkonce.armexidx.*) __exidx_end = .; } > FLASH
.init_array : { __init_array_start = .; KEEP(*(SORT(.init_array.*))) KEEP(*(.init_array)) __init_array_end = .; } > FLASH
_sidata = LOADADDR(.data);
.data : { _sdata = .; *(.data .data.*) . = ALIGN(4); _edata = .; } > RAM AT > FLASH
.bss (NOLOAD) : { _sbss = .; *(.bss .bss.* COMMON) . = ALIGN(4); _ebss = .; } > RAM
```

- `.ARM.extab` and `.ARM.exidx` are the unwind tables. libgcc's unwinder finds them through `__exidx_start` and
  `__exidx_end`.
- `.init_array` holds the module initializers. `KEEP` stops `--gc-sections` from dropping them, and the start code
  runs them from `__init_array_start` to `__init_array_end`.
- The start code copies `.data` from `_sidata` to `_sdata` .. `_edata` and clears `_sbss` .. `_ebss`.
- The Kotlin heap is a static array in `.bss` (`KM_HEAP_BYTES`), so there is no heap section. The stack is the RAM
  above `.bss`, up to `_estack`. qbuild prints that size (`stack N` in its size line; on `qemu-l475`, without the
  stack guard and the unused bytes around it), and [stm32l431.ld](../examples/selftest/stm32l431/stm32l431.ld) stops
  the link when less than 8 KB is left.

## The link

ld.lld, from the same LLVM:

```
ld.lld -T board.ld --gc-sections --lto-O2 --target2=abs -o app.elf <C objects> <runtime objects> k.o [bridges.o]
       -L<arm-none-eabi-gcc>/arm-none-eabi/lib/thumb/v7e-m+fp/hard -lc_nano -lm -lnosys
       <arm-none-eabi-gcc>/lib/gcc/arm-none-eabi/<version>/thumb/v7e-m+fp/hard/libgcc.a
```

- `--lto-O2` optimises the bitcode objects as one program; `--gc-sections` drops unused sections.
- `--target2=abs` is what qbuild passes. It sets how ld.lld fills the type-table entries of the unwind tables;
  kmicro's personality routine never reads them, and the STM32L431 example links without it.
- `-lc_nano -lm`: newlib-nano and its libm (`memcpy`, string functions, `kotlin.math`). `-lnosys`: empty system
  calls, as there is no operating system.
- `libgcc.a`: the ARM EHABI unwinder and the compiler helpers. Newlib and libgcc come from the
  `thumb/v7e-m+fp/hard` multilib, the one for a Cortex-M4F with the hard-float calling convention.

qbuild links a Kotlin runtime function that kmicro does not define to a stub that stops the program with
`kmicro panic: unimplemented runtime symbol: NAME`, and warns `qbuild: warning: N runtime symbols stubbed`. A board
link reports `undefined symbol: NAME` instead. `python tools/missing_natives.py` lists the standard library's
runtime functions and how kmicro handles each. On the current runtime its first line reads `353 natives in the
Kotlin/Native stdlib: 261 implemented, 52 unsupported, 40 Objective-C, 0 missing`.

## A check on QEMU

The steps above, written out as a shell script (bash) for the exceptions test `tests/exceptions/exceptions.kt`, with
the QEMU target's `start.c` and `l475.ld` standing in for a board's. The tool folders are the ones
`python toolchain/paths.py` prints; these are a Windows host's, run from the repository root in Git Bash:

```
python tools/kbuild.py build/board tests/exceptions/exceptions.kt

LLVM=~/.konan/dependencies/llvm-21-x86_64-windows-essentials-150/bin
GCC=~/toolchains/xpack-arm-none-eabi-gcc-15.2.1-1.1
QEMU=~/toolchains/xpack-qemu-arm-9.2.4-1
ML=thumb/v7e-m+fp/hard

CFLAGS="--target=thumbv7em-none-eabihf -mcpu=cortex-m4 -mfpu=fpv4-sp-d16 -mfloat-abi=hard
        -isystem $GCC/arm-none-eabi/include -O2 -flto -ffunction-sections -fdata-sections
        -fexceptions -funwind-tables -I runtime -D KM_HEAP_BYTES=8192"
mkdir -p build/board/obj
for f in runtime/*.c runtime/*.cpp runtime/dtoa/*.cpp targets/qemu-l475/start.c tests/exceptions/main.c; do
    case $f in *.cpp) more="-std=c++17 -fno-rtti" ;; *) more="" ;; esac
    $LLVM/clang $CFLAGS $more -c $f -o build/board/obj/$(basename $f).o || break
done

$LLVM/ld.lld -T targets/qemu-l475/l475.ld --gc-sections --lto-O2 --target2=abs -o build/board/exc.elf \
    build/board/obj/*.o build/board/k.o -L$GCC/arm-none-eabi/lib/$ML -lc_nano -lm -lnosys \
    $GCC/lib/gcc/arm-none-eabi/*/$ML/libgcc.a

$QEMU/bin/qemu-system-arm -machine b-l475e-iot01a -nographic -semihosting-config enable=on,target=native \
    -serial none -monitor none -kernel build/board/exc.elf
echo "exit $?"
```

```
kotlinc-native: compiling 1 file...
single-core: 113 init-state loads made plain
build\board\k.o
exception checks failed mask = 0  OK   (gcs=6)
now an uncaught one (expected to stop with a report):
Uncaught Kotlin exception: PanelError: panel error -5
    at 0x08009df8
    at 0x08005254
    at 0x0800421e
kmicro panic: uncaught Kotlin exception
exit 98
```

`mask = 0` means that each of the test's exceptions was caught where it should be; the last one is uncaught on
purpose. For a board, replace `start.c` and `l475.ld` with its own and write the ELF to its flash.

## Optional: a fault report and MPU guards

[targets/qemu-l475/start.c](../targets/qemu-l475/start.c) adds both; copy what fits the board.

- **The fault report.** The fault handler is naked: it takes the stacked frame from MSP or PSP (as EXC_RETURN says)
  and moves SP to a 256-byte stack of its own before any C runs, because the faulting stack may be the problem. It
  prints two lines and calls `kmicro_exit(99)`:

  ```
  kmicro fault: [stack overflow (|null pointer access (]<NMI|HardFault|MemManage|BusFault|UsageFault>[)] at 0x<PC>
      sp 0x...  lr 0x...  cfsr 0x...  hfsr 0x...  mmfar 0x...  bfar 0x...
  ```

  The other exceptions that the vector table sends there (SVCall, DebugMonitor, PendSV) are named `exception N`.
  When the stacked frame cannot be read, `, no stacked frame` replaces ` at 0x<PC>` and the `lr` field is left out.
  [how-it-works.md](how-it-works.md#reading-a-stack-trace) shows a report and how `tools/symbolize.py` names its
  address.
- **The MPU guards.** VTOR points at the vector table in flash. Region 0 covers the first 64 KB of the address space
  with no access and execute-never: on the Cortex-M4 address 0 is an alias of flash, so a read through a null object
  or a null C pointer would otherwise return the vector table. Region 1 is a 4 KB, 4 KB-aligned no-access guard
  between `.bss` and the stack (`_sguard` .. `_eguard` in `l475.ld`): an overflowing stack faults there before it
  writes the heap. Make the guard larger than the largest frame of the image (`python tools/frames.py app.elf`):
  a function with a larger frame can move the stack pointer past a smaller guard without writing into it, and the
  calls below it then write the heap with no fault. The runtime's C code has frames of up to 1024 bytes (the
  unwinder) and the standard library of up to 2984 bytes (the character-class tables of `Regex`); a program without
  `Regex` can do with a 2 KB guard if frames.py shows nothing larger. PRIVDEFENA keeps the default memory map everywhere else, and SHCSR turns on the MemManage,
  BusFault and UsageFault handlers.
- **Limits.** The stack-overflow report has no PC. A frame larger than the guard can step over it:
  `python tools/frames.py app.elf` lists the largest frames, and `--limit 4096` makes it fail for a larger one.

The STM32L431 example prints a shorter fault report (exception number, PC, LR, CFSR) and has no MPU guards.

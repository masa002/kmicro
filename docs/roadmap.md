# Roadmap

kmicro has no release schedule. This page says what kmicro supports, where its known gaps are, and where the open
work is tracked. It names no dates.

## Releases and versions

Releases are tagged `vMAJOR.MINOR.PATCH` and listed in [CHANGELOG.md](../CHANGELOG.md) with what they contain and
their known issues. A release is cut when a set of fixes or a feature is ready and every suite passes on `main`.

- While the major version is 0, a minor release (0.2.0) may change the board contract in
  [runtime/kmicro.h](../runtime/kmicro.h), the command line of a tool, or the supported Kotlin/Native version. The
  changelog says what a board or a build script has to change.
- A patch release (0.2.1) fixes problems and changes none of those.
- Version 1.0 is the point from which the board contract and the command lines stay compatible within a major
  version.

## Compiler versions

kmicro reads the IR of one compiler, Kotlin/Native 2.4.21, and is tested only with it; `python toolchain/paths.py`
warns when another version is installed. kmicro builds on the compiler's `linux_arm32_hfp` target, which JetBrains
has deprecated, so a later compiler may not offer it. In Kotlin 2.5.0-RC the deprecation is still a warning, and no
release is named for the removal; [research/R_arm32_target.md](research/R_arm32_target.md) has the sources, and what
kmicro can build on when the target goes.

Another compiler version becomes supported when the runtime contract ([runtime/kmicro.h](../runtime/kmicro.h), the
notes in [research/](research)) and [toolchain/retarget.py](../toolchain/retarget.py) have been checked against its
IR, and `tests/run_all.py`, `tools/difftest.py` (also with `--stress`) and the unit tests pass with it. Until then,
the version in [BUILDING.md](../BUILDING.md) is the only supported one. Once a week a CI job (`next-kotlin`) builds
and runs the unit tests and run_all with the newest Kotlin release, pre-releases included, and may fail: it shows
what the next compiler changes before anyone depends on it.

### Kotlin 2.5

Kotlin 2.5.0 is not released, and kmicro does not support it. What its release candidate changes for kmicro was
checked with Kotlin/Native 2.5.0-RC: the IR of the test programs was compared with that of 2.4.21, and the suites
were run with `KMICRO_KOTLIN_NATIVE` set to it, on Windows and for the default core.

**The same as in 2.4.21:** the target `linux_arm32_hfp` and its triple, the data layout, the LLVM the compiler
downloads, and the layouts the runtime shares with the compiled code (the `TypeInfo`, the object and array headers).
The standard library declares 353 runtime functions, as before: six for parsing and printing floating-point numbers
are gone, because it does that in Kotlin now, and six array accessors that the runtime already has are new.
`python tools/missing_natives.py` finds none missing.

**Different, and handled for both versions:**

- The two functions that initialise globals on first use take the class as one more argument, and a failed
  initializer is reported through another function of the standard library. The runtime has both forms
  ([runtime/init_cxx.cpp](../runtime/init_cxx.cpp)), and retarget.py, `--init-all` and isr_check know both.
- The standard library's `HexStringParser` moved from `kotlin.native.internal` to `kotlin.text`; retarget.py finds
  it under both names.
- The constructor of `Throwable` stays a function of its own in more programs. That showed a defect in how a
  stack trace leaves the constructor's frame out, which a 2.4.21 program could meet too; it is fixed.
- A failed initializer throws `kotlin.ExceptionInInitializerError` (2.4.21:
  `kotlin.native.internal.FileFailedToInitializeException`), and `"abc".uppercase()` keeps 16 bytes of heap for
  good, the companion object of the new `kotlin.text.unicode.CodePoint` (2.4.21: none). Two tests of run_all print
  these; their expected outputs for 2.5 are in `tests/expected/kotlin-2.5`.

With that, `python tests/run_all.py` passes with 2.5.0-RC, and so do the unit tests, on Windows and, in the CI
job `next-kotlin`, on Linux. `python tools/difftest.py` gives the output of the stock runtime of 2.5.0-RC for 45 of
its 47 programs (Windows); items 1 and 4 below are the other two. Not run with it: `--stress`, the other cores, a
board.

**Open: what the change to 2.5 needs.** None of it is done, because each item would change what 2.4.21 programs
do or measure. [Issue #149](https://github.com/masa002/kmicro/issues/149) has the list as a checklist for the day
2.5.0 is released:

1. `1.0.pow(Double.NaN)` and `1.0f.pow(Float.NaN)` are `NaN` in 2.5, as the documentation of `pow` says, and `1.0`
   in 2.4.21. `Kotlin_math_Double_pow` and `Kotlin_math_Float_pow` in [runtime/kmath.c](../runtime/kmath.c) follow
   2.4.21; they need the stock runtime's new line (`if (isnan(x)) return NAN;`). `d_math` of difftest prints it.
2. The version itself: `KOTLIN_NATIVE_VERSION` in [toolchain/paths.py](../toolchain/paths.py), the rows of
   [toolchain/versions.txt](../toolchain/versions.txt) (2.5 has no prebuilt compiler for Intel Macs, so the
   `macos-x64` rows go), [BUILDING.md](../BUILDING.md), the README and the other texts that name the version (the
   selftest prints it), and the files of `tests/expected/kotlin-2.5` in the place of the two they stand for.
3. What only 2.4.21 needs can go: the two-argument forms of the initialisation functions and the rename in
   retarget.py (the runtime's functions can then have the compiler's names), the old name of `HexStringParser`, and
   the six runtime functions the standard library no longer calls. Those six are all of `runtime/dtoa/`, which
   goes with what serves only it: its scratch memory in `runtime/interop.c`, `km_dtoa_utf8` in `runtime/strings.c`,
   `tools/port_dtoa.py`, and its lines in qbuild, [porting.md](porting.md) and NOTICE.
4. Every size in the documents is measured again. Programs are larger with 2.5: the selftest is 137.7 KB of flash
   and 18.7 KB of RAM (2.4.21: 121.1 KB and 18.5 KB), `hello` 82.2 KB (72.0 KB). The standard library of 2.5
   initialises a class's static state as the JVM does, the superclasses first, so more of its functions check an
   initialisation state (in `tests/diff/d_init.kt`, 463 checks where 2.4.21 has 122). One program of difftest,
   `d_lang_2`, no longer fits the 256 KB of the STM32L431 (265.0 KB; 2.4.21: 230.1 KB) and needs its
   `// difftest: large` line; linked so, it gives the stock runtime's output.
5. In 2.5 a function that uses such a class reads the state of its globals twice, the second time with a volatile
   load, which `retarget.py --single-core` leaves as it is. A trial that made it a plain load too passed the three
   tests it was run on (`selftest`, `hello`, `isr_init_window_tls`) and made their images larger, not smaller (the
   selftest 139.0 KB instead of 137.7 KB), so it was not kept. What it does to speed was not measured.

**One supported version at a time (a proposal).** When 2.5.0 is released, kmicro changes from 2.4.21 to 2.5.0 in
one minor release, and that release supports 2.5.0 only; the last release before it remains the one for 2.4.21. The
reasons:

- kmicro is tied to things a compiler release is free to change and that no option selects: the signatures of
  runtime functions, names inside the standard library, what a standard-library call allocates, what an exception is
  called. 2.5 changed one of each. Supporting two versions means two forms of each in the runtime and the tools for
  as long as both are supported, and item 1 above cannot have two forms at all: one runtime function has to give
  two results.
- Every number in the documents and every expected output holds for one compiler. Two versions double the tables,
  the expected files that differ, and the CI time of every pull request.
- What does cost little is being ready: the tools and the runtime accept the next version's IR beside the
  supported one where that takes a second name or a second form, as above, so that the weekly `next-kotlin` job
  stays green and shows the next difference when it appears, and the change of version is the short list above.
  After the change, the forms of the old version are removed (item 3).

## Targets

kmicro builds for the Cortex-M cores from the Cortex-M0 to the Cortex-M85, and for cores of the A and the R profile
in their 32-bit state: the Cortex-A7 and the Cortex-R52, and others whose code those two run. It also builds for
one ARM core from before the Cortex names, the ARM1176JZF-S. `--cpu CORE` on kbuild, qbuild, run_all and difftest,
or the environment variable `KMICRO_CPU`, chooses the core; the default is `cortex-m4f`. `CORES` in
[toolchain/paths.py](../toolchain/paths.py) holds the clang target, the flags and the newlib and libgcc multilib of
each. A core without an FPU uses the soft-float calling convention.

| `--cpu` | Architecture | FPU | Tested on QEMU's | Checked | selftest: flash | RAM |
|---|---|---|---|---|---|---|
| `cortex-m0` | ARMv6-M | none | `b-l475e-iot01a` (an STM32L475), a Cortex-M4F | the selftest | 121.9 KB | 18.5 KB |
| `cortex-m0plus` | ARMv6-M | none | `b-l475e-iot01a`, a Cortex-M4F | run_all; difftest | 121.9 KB | 18.5 KB |
| `cortex-m1` | ARMv6-M | none | `b-l475e-iot01a`, a Cortex-M4F | the selftest | 121.9 KB | 18.5 KB |
| `cortex-m3` | ARMv7-M | none | `mps2-an385`, a Cortex-M3 | run_all | 131.6 KB | 18.5 KB |
| `cortex-m4` | ARMv7E-M | none | `b-l475e-iot01a`, a Cortex-M4F | run_all | 131.5 KB | 18.5 KB |
| `cortex-m4f`, the default | ARMv7E-M | FPv4, single precision | `b-l475e-iot01a`, a Cortex-M4F | run_all, also under GC stress; difftest; an STM32L431 board | 131.2 KB | 18.5 KB |
| `cortex-m7` | ARMv7E-M | FPv5, double precision | `mps2-an500`, a Cortex-M7 | run_all | 130.1 KB | 18.5 KB |
| `cortex-m7-sp` | ARMv7E-M | FPv5, single precision | `mps2-an500`, a Cortex-M7 | the selftest | 131.0 KB | 18.5 KB |
| `cortex-m23` | ARMv8-M Baseline | none | `mps2-an505`, a Cortex-M33 | run_all | 121.1 KB | 18.5 KB |
| `cortex-m33` | ARMv8-M Mainline | none | `mps2-an505`, a Cortex-M33 | run_all; difftest | 131.5 KB | 18.5 KB |
| `cortex-m33f` | ARMv8-M Mainline | FPv5, single precision | `mps2-an505`, a Cortex-M33 | run_all | 131.1 KB | 18.5 KB |
| `cortex-m55` | ARMv8.1-M Mainline | FPv5, double precision; MVE | `mps3-an547`, a Cortex-M55 | run_all; difftest | 126.1 KB | 18.5 KB |
| `cortex-m55-nomve` | ARMv8.1-M Mainline | FPv5, double precision | `mps3-an547`, a Cortex-M55 | the selftest | 130.3 KB | 18.5 KB |
| `cortex-m55-nofp` | ARMv8.1-M Mainline | none | `mps3-an547`, a Cortex-M55 | the selftest | 131.5 KB | 18.5 KB |
| `cortex-m85` | ARMv8.1-M Mainline | FPv5, double precision; MVE | `mps3-an547`, a Cortex-M55 | the selftest | 127.7 KB | 18.5 KB |
| `cortex-m85-nomve` | ARMv8.1-M Mainline | FPv5, double precision | `mps3-an547`, a Cortex-M55 | the selftest | 129.8 KB | 18.5 KB |
| `cortex-m85-nofp` | ARMv8.1-M Mainline | none | `mps3-an547`, a Cortex-M55 | the selftest | 131.0 KB | 18.5 KB |
| `cortex-a5` | ARMv7-A, built as Thumb-2 code | VFPv4 and NEON | `virt`, a Cortex-A7 | the selftest | 117.0 KB | 18.2 KB |
| `cortex-a7` | ARMv7-A, built as Thumb-2 code | VFPv4 and NEON | `virt`, a Cortex-A7 | run_all, also under GC stress; difftest | 116.2 KB | 18.2 KB |
| `cortex-a7-nofp` | ARMv7-A, built as Thumb-2 code | none | `virt`, a Cortex-A7 | run_all | 115.2 KB | 18.2 KB |
| `cortex-a8` | ARMv7-A, built as Thumb-2 code | VFPv3 and NEON | `virt`, a Cortex-A7 | the selftest | 116.9 KB | 18.2 KB |
| `cortex-a9` | ARMv7-A, built as Thumb-2 code | VFPv3-D16 | `virt`, a Cortex-A7 | the selftest | 115.6 KB | 18.2 KB |
| `cortex-a15` | ARMv7-A, built as Thumb-2 code | VFPv4 and NEON | `virt`, a Cortex-A7 | the selftest | 114.7 KB | 18.2 KB |
| `cortex-r5` | ARMv7-R, built as Thumb-2 code | none | `mps3-an536`, a Cortex-R52 | run_all | 116.1 KB | 18.2 KB |
| `cortex-r5f` | ARMv7-R, built as Thumb-2 code | VFPv3-D16 | `mps3-an536`, a Cortex-R52 | the selftest | 115.2 KB | 18.2 KB |
| `cortex-r52` | ARMv8-R, built as Thumb-2 code | FP-ARMv8 and NEON | `mps3-an536`, a Cortex-R52 | run_all, also under GC stress; difftest for 16 of its programs | 117.1 KB | 18.2 KB |
| `arm1176jzf-s` | ARMv6KZ, built as ARM code | VFPv2 | `raspi0` (a Raspberry Pi Zero), an ARM1176JZF-S | run_all; difftest for 6 of its programs | 147.6 KB | 18.2 KB |

- **run_all** means that `python tests/run_all.py --cpu CORE` passes: every test program and example, with the
  checks the tools make on the images. The three tests of the large-memory machine, `mps2-an386`, are skipped for a
  core whose code its Cortex-M4F does not run: the Cortex-M7, the cores of ARMv8-M and ARMv8.1-M, and those of
  the A and R profiles, and the ARM1176JZF-S. For those last three kinds three more are skipped, whose Kotlin code
  programs the System Control Block or the SysTick of a Cortex-M: `isr_init_window`, `isr_init_window_tls` and the
  example `irq`.
- **The selftest** means that `python tests/run_all.py --cpu CORE selftest` passes and nothing else was run. The
  Cortex-A and Cortex-R cores with this word differ from the core of their machine in the `-mcpu` value, the FPU
  and its multilib.
  `cortex-m0` and `cortex-m1` differ from `cortex-m0plus` only in the `-mcpu` value, and `cortex-m7-sp` from
  `cortex-m7` in the FPU and its multilib. Of the six entries of ARMv8.1-M (below), run_all ran for `cortex-m55`.
- **The sizes** are those of [examples/selftest](../examples/selftest) as that test builds it, with the default
  16 KB heap and the QEMU start code: flash is text and data, RAM is data and `.bss` (the heap, the runtime's tables,
  the globals), without the stack.
- **ARMv6-M and ARMv8-M Baseline code is tested on a larger core,** not on a model of the core itself. The
  Cortex-M4F of QEMU's STM32L475 runs the code built for the Cortex-M0, M0+ and M1, and QEMU has no Cortex-M23, so
  its code runs on the Cortex-M33. The compiler's flags keep such an image to the instructions of its core, and
  [tools/insn_check.py](../tools/insn_check.py) checks that they did: it reads the disassembly of an image and
  fails for an instruction that the core does not have (on ARMv6-M, any 32-bit instruction but `bl`, `msr`, `mrs`,
  `dsb`, `dmb` and `isb`). run_all runs it on the images of three tests (selftest, irq, stdio_float) for the core
  it builds for, so CI runs it for `cortex-m0plus`, `cortex-m23` and every other core of its matrix. (The build
  attributes of an image, `arm-none-eabi-readelf -A`, do not show this: ld.lld keeps those of the first object
  that has any, which is a member of newlib.) Those cores fault on an unaligned LDR or STR and the larger ones do
  not, so the QEMU start code asks the larger core to fault too (CCR.UNALIGN_TRP); run_all passes with it for
  `cortex-m0plus` and `cortex-m23`, and difftest for `cortex-m0plus`. What else belongs to the core and not to the
  code was not tested there: its reset state, its MPU and its fault registers are those of the larger core.
- **The ARMv8-M and ARMv8.1-M cores run in the Secure state,** in which the Cortex-M33 and the Cortex-M55 of
  these machines start. The program never leaves it and does not use the Security Extension.
- **The Cortex-M55 and the Cortex-M85 have three entries each.** A chip maker builds these cores with or without
  the FPU (half, single and double precision) and with or without MVE (Helium). `cortex-m55` is the core with both,
  which is what `-mcpu=cortex-m55` means to clang and to GCC; `cortex-m55-nomve` has the FPU only, and
  `cortex-m55-nofp` neither. The first two link the newlib and libgcc of ARMv8-M Mainline with a double-precision
  FPU (`thumb/v8-m.main+dp/hard`) and the third the ones without an FPU: the xPack GCC has no others for these
  cores and chooses the same. A core with MVE and no FPU has no entry; `-nofp` code runs on it and leaves MVE
  unused. With MVE the compiler puts vector instructions into ordinary code: the `cortex-m55` selftest has them in
  the string functions of the runtime and of the standard library, and run_all runs every test program built that
  way. [porting.md](porting.md#another-core) says what that means for a board. Four programs of difftest with
  floating point and 64-bit integers (d_math, d_numbers, d_to_double, d_long_digits) were run by hand for
  `cortex-m55-nomve`, `cortex-m55-nofp` and `cortex-m85` and gave the output of the stock runtime.
- **Cortex-M85 code is tested on the Cortex-M55,** because QEMU 9.2.4 has no model of the Cortex-M85. For the
  compiler the Cortex-M85 is the Cortex-M55 with PACBTI (pointer authentication and branch target identification)
  and another tuning. kmicro builds nothing with `-mbranch-protection`, and
  `python tools/insn_check.py --cpu cortex-m55` passes on the three `cortex-m85` selftest images: they hold only
  instructions that the Cortex-M55 has too, and its model runs them. Nothing that belongs to the Cortex-M85 itself
  was tested: its reset state, its MPU and its fault registers.
- **The Cortex-A7 is a core of another profile.** It has no vector table of handler addresses, no NVIC and no
  SysTick, and an MMU where a Cortex-M has an MPU, so it has start code of its own
  ([targets/qemu-virt](../targets/qemu-virt)): the program runs in Supervisor mode with the MMU on and a flat map,
  and its interrupt handlers in IRQ mode, called through the machine's interrupt controller (a GIC, version 2).
  The Kotlin code and the runtime are built as for a Cortex-M, as Thumb-2 code with the hard-float calling
  convention. run_all also passes under GC stress, and difftest gave the output of the stock runtime for all 47 of
  its programs (both once, on Windows; CI runs neither for this core). In three of those programs (`d_arrays`,
  `d_lang_6`, `d_stdlib_misc`) `main` has a stack frame of 4176 to 4280 bytes on this core, more than the 4 KB of
  the stack guard, which such a frame could step over without a fault; difftest marks them FRAME for it. What was
  not checked: nothing ran on a board or on another QEMU machine; QEMU does not model
  the caches, which the start code leaves off; there is no build as ARM code; and one
  core runs, the machine's default. [porting.md](porting.md#a-cortex-a-core) says what a board with such a core
  does.
- **The Cortex-R52 is a core of the R profile,** with the exceptions, the modes and the interrupt controller of the
  A profile and an MPU in place of the MMU. Its start code ([targets/qemu-an536](../targets/qemu-an536)) leaves Hyp
  mode, in which this core starts, for Supervisor mode, and runs the program there, its handlers in IRQ mode, called
  through the machine's GIC (version 3, reached through system registers). The MPU has a region for each piece of
  memory the program has and no default map behind them, so every other address faults: address 0 and the 4 KB below
  each stack among them. run_all also passes under GC stress (once, on Windows), and 16 differential tests, chosen
  across the language, the strings, the numbers, the atomics and the stack traces, gave the output of the stock
  runtime. What was not checked: nothing ran on a board; the program never uses Hyp mode again; the xPack GCC has no
  newlib and libgcc for ARMv8-R, so the libraries are those of ARMv7 with VFPv3-D16, which this core runs, next to
  Kotlin and runtime code built for its own FPU; there is no build without the FPU; difftest was not run in full or
  under GC stress. [porting.md](porting.md#a-cortex-r-core) says what differs from a Cortex-A core.
- **Cortex-A and Cortex-R code that is tested on a larger core.** QEMU's `virt` runs the code of five more entries
  on its Cortex-A7, which has every instruction they use: `cortex-a5`, `cortex-a8`, `cortex-a9` and `cortex-a15`,
  each built with its own `-mcpu`, its FPU and the libraries of its multilib, and `cortex-a7-nofp`, the Cortex-A7
  without its FPU, in the soft-float calling convention. `cortex-r5` (no FPU) and `cortex-r5f` are code of ARMv7-R,
  which the Cortex-R52 of `mps3-an536` runs. The start code is that of the machine in both cases. So what was
  tested is the compiler's code for the core, its libraries and the runtime, and nothing that belongs to the core:
  its reset state, its vectors, its MPU or MMU, its interrupt controller. For the Cortex-R5 that is much: it has
  the MPU of ARMv7-R, no VBAR (its vectors are at address 0 or 0xFFFF0000) and no Hyp mode, so a board needs start
  code that this repository does not have. QEMU 9.2.4 has models of the Cortex-A8, A9 and A15 on other machines,
  for which there is no start code here, and of the Cortex-R5F on `xlnx-zcu102` (in `qemu-system-aarch64`, next to four
  64-bit Cortex-A53), where a trial did not get an image to run: the two Cortex-R5F cores stayed off.
- **The ARM1176JZF-S is a core from before the Cortex names:** ARMv6KZ with VFPv2, the core of the first
  Raspberry Pi and of the Pi Zero, and the one the compiler's own target, `linux_arm32_hfp`, compiles for. It has
  the exceptions and the modes of the A profile, so its start code ([targets/qemu-raspi0](../targets/qemu-raspi0))
  is laid out as that of the Cortex-A7: the program in Supervisor mode with the MMU on, a flat map and the same
  guards (the first megabyte, and a 4 KB page below the stack and below each exception stack, are not mapped), its
  handlers in IRQ mode, called through the interrupt controller of the board's chip, a BCM2835. What differs is the
  code. This core has no Thumb-2, so everything is built as ARM code, the only core here for which it is, and an
  image is larger: the selftest by a quarter. The libraries are those of ARMv5TE with VFPv2 (`arm/v5te/hard`), the
  nearest the xPack GCC has. An unaligned load or store of a word faults there: the start code asks for that
  (SCTLR.A), because this core would otherwise read the aligned word and rotate it, and run_all passes with it.
  Six differential tests (`d_strings`, `d_atomic_arrays`, `d_exceptions`, `d_math`, `d_numbers`, `d_to_double`)
  gave the output of the stock runtime.
  What was not checked: nothing ran on a board, whose firmware loads an image at another address than the second
  megabyte this one is linked for, and which has no semihosting to print through; QEMU does not model the caches,
  which the start code leaves off; there is no build without the FPU (the ARM1176JZ-S); run_all was not run under
  GC stress, and difftest not in full. The other ARM11 cores (the ARM1136, the ARM11 MPCore) are ARMv6 too, but
  have no Security Extensions and with them no VBAR: their vectors are at address 0 or 0xFFFF0000, which this start
  code does not do, and nothing was built or run for them.
  [porting.md](porting.md#an-arm-core-from-before-the-cortex-names) says what a board with this core does.
- **On a board,** only the Cortex-M4F has run: an STM32L431, in
  [the recorded run](../examples/selftest/stm32l431-report.txt), which predates release 0.1.0.
  [porting.md](porting.md#another-core) says what a board with another core changes.
- **difftest** means that `python tools/difftest.py --cpu CORE` passes: every program of
  [tests/diff](../tests/diff) prints on kmicro what it prints on the stock runtime. CI runs that for the default
  core after every merge, also under GC stress, and once a week for `cortex-m0plus`, `cortex-m33` and
  `cortex-m55`, without GC stress. Before CI did, the whole suite was run by hand for these three: for
  `cortex-m0plus` when its unaligned-access trap went in, for the other two after the ARMv8.1-M cores were added.
  Nothing differed. For `cortex-m55` one program, `d_lang_6`, had a frame of its `main` above the stack guard, and
  now says so in its source, as two others did.
- CI runs run_all under GC stress for the default core only.

Not supported:

- **PACBTI on the Cortex-M85:** the code is built without pointer authentication and branch target
  identification, and the libraries GCC has for them are not linked.
- **The other Cortex-R cores and 32-bit Cortex-A cores:** there is no entry in `CORES` for them, and nothing ran.
- **The other ARM cores from before the Cortex names:** the rest of ARM11 (ARM1136, ARM1156, ARM11 MPCore), and all
  of ARM9 and ARM7 (ARMv5TE, ARMv4T). There is no entry in `CORES` for them, and nothing ran.
- **Start code for a Cortex-R5 or for a Cortex-A core other than the Cortex-A7:** the entries of those cores build
  code, and only the machines of the Cortex-A7 and the Cortex-R52 have start code.
- **64-bit ARM:** out of reach of this approach, which reads the IR of the compiler's 32-bit ARM target.
- **Threads:** the runtime is single-threaded, and interrupt handlers follow
  [the rules](writing-kotlin.md#interrupt-handlers).

## Known gaps

Each gap is described where it matters; this list only points there.

| Theme | Where |
|---|---|
| The standard library: what works partly, does not work, or is not supported | [kotlin-support.md](kotlin-support.md) |
| Memory: a heap that does not move objects and fragments, heap exhaustion that cannot be caught, the size of `Regex` | [README: Known gaps](../README.md#known-gaps), [writing-kotlin.md](writing-kotlin.md#memory) |
| Diagnostics: stack traces of at most 12 frames, cut without a marker; stack overflow and null reads caught only by the start code of `qemu-l475` (by MPU guards), of `qemu-virt` and `qemu-raspi0` (by pages the MMU does not map) and of `qemu-an536` (by addresses outside the MPU's regions), not by `qemu-an386` or the STM32L431 example | [how-it-works.md](how-it-works.md#reading-a-stack-trace), [porting.md](porting.md#optional-a-fault-report-and-mpu-guards) |
| Boards: the hooks a board must provide for clocks, entropy and input | [porting.md](porting.md#the-board-contract) |
| Hosts: Windows is tested, and Linux x64 in CI; macOS is not; on Windows, file names outside the ANSI code page fail in the xPack tools | [BUILDING.md](../BUILDING.md#hosts) |

## Open work

The open issues, by theme:

- [runtime](https://github.com/masa002/kmicro/issues?q=is%3Aissue%20is%3Aopen%20label%3A%22area%3A%20runtime%22):
  the C and C++ runtime
- [toolchain](https://github.com/masa002/kmicro/issues?q=is%3Aissue%20is%3Aopen%20label%3A%22area%3A%20toolchain%22)
  and [tools](https://github.com/masa002/kmicro/issues?q=is%3Aissue%20is%3Aopen%20label%3A%22area%3A%20tools%22):
  the build pipeline and the command-line tools
- [Kotlin features](https://github.com/masa002/kmicro/issues?q=is%3Aissue%20is%3Aopen%20label%3Akotlin-support):
  language and standard-library features that do not work
- [tests](https://github.com/masa002/kmicro/issues?q=is%3Aissue%20is%3Aopen%20label%3A%22area%3A%20tests%22):
  the test suites and their coverage
- [docs](https://github.com/masa002/kmicro/issues?q=is%3Aissue%20is%3Aopen%20label%3A%22area%3A%20docs%22),
  [examples](https://github.com/masa002/kmicro/issues?q=is%3Aissue%20is%3Aopen%20label%3A%22area%3A%20examples%22)
  and [the repository](https://github.com/masa002/kmicro/issues?q=is%3Aissue%20is%3Aopen%20label%3A%22area%3A%20repo%22)

A gap that has no issue yet can get one: [CONTRIBUTING.md](../CONTRIBUTING.md#reporting-a-bug) says what to put in
it.

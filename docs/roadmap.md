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
has deprecated, so a later compiler may not offer it.

Another compiler version becomes supported when the runtime contract ([runtime/kmicro.h](../runtime/kmicro.h), the
notes in [research/](research)) and [toolchain/retarget.py](../toolchain/retarget.py) have been checked against its
IR, and `tests/run_all.py`, `tools/difftest.py` (also with `--stress`) and the unit tests pass with it. Until then,
the version in [BUILDING.md](../BUILDING.md) is the only supported one. Once a week a CI job (`next-kotlin`) builds
and runs the unit tests and run_all with the newest Kotlin release, pre-releases included, and may fail: it shows
what the next compiler changes before anyone depends on it.

## Targets

kmicro builds for the Cortex-M cores from the Cortex-M0 to the Cortex-M85. `--cpu CORE` on kbuild, qbuild, run_all
and difftest, or the environment variable `KMICRO_CPU`, chooses the core; the default is `cortex-m4f`. `CORES` in
[toolchain/paths.py](../toolchain/paths.py) holds the clang target, the flags and the newlib and libgcc multilib of
each. A core without an FPU uses the soft-float calling convention.

| `--cpu` | Architecture | FPU | Tested on QEMU's | Checked | selftest: flash | RAM |
|---|---|---|---|---|---|---|
| `cortex-m0` | ARMv6-M | none | `b-l475e-iot01a` (an STM32L475), a Cortex-M4F | the selftest | 121.9 KB | 18.5 KB |
| `cortex-m0plus` | ARMv6-M | none | `b-l475e-iot01a`, a Cortex-M4F | run_all | 121.9 KB | 18.5 KB |
| `cortex-m1` | ARMv6-M | none | `b-l475e-iot01a`, a Cortex-M4F | the selftest | 121.9 KB | 18.5 KB |
| `cortex-m3` | ARMv7-M | none | `mps2-an385`, a Cortex-M3 | run_all | 131.6 KB | 18.5 KB |
| `cortex-m4` | ARMv7E-M | none | `b-l475e-iot01a`, a Cortex-M4F | run_all | 131.5 KB | 18.5 KB |
| `cortex-m4f`, the default | ARMv7E-M | FPv4, single precision | `b-l475e-iot01a`, a Cortex-M4F | run_all, also under GC stress; difftest; an STM32L431 board | 131.2 KB | 18.5 KB |
| `cortex-m7` | ARMv7E-M | FPv5, double precision | `mps2-an500`, a Cortex-M7 | run_all | 130.1 KB | 18.5 KB |
| `cortex-m7-sp` | ARMv7E-M | FPv5, single precision | `mps2-an500`, a Cortex-M7 | the selftest | 131.0 KB | 18.5 KB |
| `cortex-m23` | ARMv8-M Baseline | none | `mps2-an505`, a Cortex-M33 | run_all | 121.1 KB | 18.5 KB |
| `cortex-m33` | ARMv8-M Mainline | none | `mps2-an505`, a Cortex-M33 | run_all | 131.5 KB | 18.5 KB |
| `cortex-m33f` | ARMv8-M Mainline | FPv5, single precision | `mps2-an505`, a Cortex-M33 | run_all | 131.1 KB | 18.5 KB |
| `cortex-m55` | ARMv8.1-M Mainline | FPv5, double precision; MVE | `mps3-an547`, a Cortex-M55 | run_all | 126.1 KB | 18.5 KB |
| `cortex-m55-nomve` | ARMv8.1-M Mainline | FPv5, double precision | `mps3-an547`, a Cortex-M55 | the selftest | 130.3 KB | 18.5 KB |
| `cortex-m55-nofp` | ARMv8.1-M Mainline | none | `mps3-an547`, a Cortex-M55 | the selftest | 131.5 KB | 18.5 KB |
| `cortex-m85` | ARMv8.1-M Mainline | FPv5, double precision; MVE | `mps3-an547`, a Cortex-M55 | the selftest | 127.7 KB | 18.5 KB |
| `cortex-m85-nomve` | ARMv8.1-M Mainline | FPv5, double precision | `mps3-an547`, a Cortex-M55 | the selftest | 129.8 KB | 18.5 KB |
| `cortex-m85-nofp` | ARMv8.1-M Mainline | none | `mps3-an547`, a Cortex-M55 | the selftest | 131.0 KB | 18.5 KB |

- **run_all** means that `python tests/run_all.py --cpu CORE` passes: every test program and example, with the
  checks the tools make on the images. The three tests of the large-memory machine, `mps2-an386`, are skipped for a
  core whose code its Cortex-M4F does not run: the Cortex-M7 and the cores of ARMv8-M and ARMv8.1-M.
- **The selftest** means that `python tests/run_all.py --cpu CORE selftest` passes and nothing else was run.
  `cortex-m0` and `cortex-m1` differ from `cortex-m0plus` only in the `-mcpu` value, and `cortex-m7-sp` from
  `cortex-m7` in the FPU and its multilib. Of the six entries of ARMv8.1-M (below), run_all ran for `cortex-m55`.
- **The sizes** are those of [examples/selftest](../examples/selftest) as that test builds it, with the default
  16 KB heap and the QEMU start code: flash is text and data, RAM is data and `.bss` (the heap, the runtime's tables,
  the globals), without the stack.
- **ARMv6-M and ARMv8-M Baseline code is tested on a larger core,** not on a model of the core itself. The
  Cortex-M4F of QEMU's STM32L475 runs the code built for the Cortex-M0, M0+ and M1, and QEMU has no Cortex-M23, so
  its code runs on the Cortex-M33. The compiler's flags keep such an image to the instructions of its core: the
  build attributes of the `cortex-m0plus` selftest say ARMv6S-M and Thumb-1, those of `cortex-m23` ARMv8-M Baseline
  (`arm-none-eabi-readelf -A`). Those cores fault on an unaligned LDR or STR and the larger ones do not, so the
  QEMU start code asks the larger core to fault too (CCR.UNALIGN_TRP); run_all passes with it for `cortex-m0plus`
  and `cortex-m23`, and difftest for `cortex-m0plus`. What else belongs to the core and not to the code was not
  tested there: its reset state, its MPU and its fault registers are those of the larger core.
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
  way. [porting.md](porting.md#another-core) says what that means for a board. CI does not run difftest for
  these cores. Run by hand, it gave the output of the stock runtime for 14 of its programs for `cortex-m55` (among
  them those with floating point and 64-bit integers) and for 4 of those for `cortex-m55-nomve`, `cortex-m55-nofp`
  and `cortex-m85`.
- **Cortex-M85 code is tested on the Cortex-M55,** because QEMU 9.2.4 has no model of the Cortex-M85. For the
  compiler the Cortex-M85 is the Cortex-M55 with PACBTI (pointer authentication and branch target identification)
  and another tuning. kmicro builds nothing with `-mbranch-protection`, and the disassembly of the three
  `cortex-m85` selftest images shows none of the PACBTI instructions: these images hold only instructions that the
  Cortex-M55 has too, and its model runs them. (The build attributes of an image do not show this: ld.lld keeps
  those of the first object that has any, which is a member of newlib.) Nothing that belongs to the Cortex-M85
  itself was tested: its reset state, its MPU and its fault registers.
- **On a board,** only the Cortex-M4F has run: an STM32L431, in
  [the recorded run](../examples/selftest/stm32l431-report.txt), which predates release 0.1.0.
  [porting.md](porting.md#another-core) says what a board with another core changes.
- CI runs run_all under GC stress, and difftest, for the default core only.

Not supported:

- **PACBTI on the Cortex-M85:** the code is built without pointer authentication and branch target
  identification, and the libraries GCC has for them are not linked.
- **Cortex-R and 32-bit Cortex-A cores:** they have the same instruction sets but another start-up and interrupt
  model. They are a separate step after the Cortex-M cores.
- **64-bit ARM:** out of reach of this approach, which reads the IR of the compiler's 32-bit ARM target.
- **Threads:** the runtime is single-threaded, and interrupt handlers follow
  [the rules](writing-kotlin.md#interrupt-handlers).

## Known gaps

Each gap is described where it matters; this list only points there.

| Theme | Where |
|---|---|
| The standard library: what works partly, does not work, or is not supported | [kotlin-support.md](kotlin-support.md) |
| Memory: a heap that does not move objects and fragments, heap exhaustion that cannot be caught, the size of `Regex` | [README: Known gaps](../README.md#known-gaps), [writing-kotlin.md](writing-kotlin.md#memory) |
| Diagnostics: stack traces of at most 12 frames, cut without a marker; stack overflow and null reads caught (by MPU guards) only by the start code of `qemu-l475`, not by `qemu-an386` or the STM32L431 example | [how-it-works.md](how-it-works.md#reading-a-stack-trace), [porting.md](porting.md#optional-a-fault-report-and-mpu-guards) |
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

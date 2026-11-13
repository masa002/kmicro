# Roadmap

kmicro has no release schedule. This page says what kmicro supports, where its known gaps are, and where the open
work is tracked. It names no dates.

## Compiler versions

kmicro reads the IR of one compiler, Kotlin/Native 2.4.21, and is tested only with it; `python toolchain/paths.py`
warns when another version is installed. kmicro builds on the compiler's `linux_arm32_hfp` target, which JetBrains
has deprecated, so a later compiler may not offer it.

Another compiler version becomes supported when the runtime contract ([runtime/kmicro.h](../runtime/kmicro.h), the
notes in [research/](research)) and [toolchain/retarget.py](../toolchain/retarget.py) have been checked against its
IR, and `tests/run_all.py`, `tools/difftest.py` (also with `--stress`) and the unit tests pass with it. Until then,
the version in [BUILDING.md](../BUILDING.md) is the only supported one.

## Targets

- **Tested:** Cortex-M4F, on QEMU's emulated STM32L475 (`qemu-l475`, the test target) and on an STM32L431 board
  ([the recorded run](../examples/selftest/stm32l431-report.txt)).
- **Untested:** a Cortex-M7 should need only another CPU in `TARGET_M4F` ([toolchain/paths.py](../toolchain/paths.py)).
- **Not supported:** a core without an FPU, which would need the soft-float calling convention, and threads: the
  runtime is single-threaded, and interrupt handlers follow
  [the rules](writing-kotlin.md#interrupt-handlers).

## Known gaps

Each gap is described where it matters; this list only points there.

| Theme | Where |
|---|---|
| The standard library: what works partly, does not work yet, or is not supported | [kotlin-support.md](kotlin-support.md) |
| Memory: a heap that does not move objects and fragments, heap exhaustion that cannot be caught, the size of `Regex` | [README: Known gaps](../README.md#known-gaps), [writing-kotlin.md](writing-kotlin.md#memory) |
| Diagnostics: stack traces of at most 12 frames, cut without a marker; a fault report and MPU guards only in the QEMU start code | [how-it-works.md](how-it-works.md#reading-a-stack-trace), [porting.md](porting.md#optional-a-fault-report-and-mpu-guards) |
| Boards: the hooks a board must provide for clocks, entropy and input | [porting.md](porting.md#the-board-contract) |
| Hosts: Windows is tested, Linux and macOS are not; file names outside the ANSI code page fail in the xPack tools | [BUILDING.md](../BUILDING.md#hosts) |

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

# Research notes

Design notes from the first weeks of kmicro (October 2026). They answer what the official Kotlin/Native 2.4.21
compiler expects from a runtime, what each piece of a bare-metal runtime would cost on a Cortex-M4, and how the
first plan was checked, with the evidence behind each answer: source lines, sizes, commands. They were written for
a Kotlin layer inside an existing C firmware on an STM32L431 (Cortex-M4F at 16 MHz, 256 KB flash, 64 KB SRAM).

Some decisions changed once code ran. The decision table in [design-plan.md](design-plan.md) gives each decision's
status, and each note starts with a short status. [how-it-works.md](../how-it-works.md) describes kmicro as it is
now.

| Note | Question |
|---|---|
| [R_abi.md](R_abi.md) | What does the compiled code expect from the runtime: symbols, object layout, calling convention? |
| [R_mm.md](R_mm.md) | Which memory-manager contract must a collector honour (frames, globals, write barriers)? |
| [R_eh.md](R_eh.md) | How does the compiler lower `throw` / `try`, and what must the personality routine do on ARM EHABI? |
| [R_zephyr.md](R_zephyr.md) | What did the Kotlin/Native Zephyr / STM32 target (2017-2020) do, and where did it stop? |
| [design-plan.md](design-plan.md) | The plan built from those answers, the experiments meant to prove it, and the status of each decision |
| [design-check.md](design-check.md) | Each claim of the plan checked against the compiler and runtime sources |
| [MEASUREMENTS.md](MEASUREMENTS.md) | What the first measurements found: getting the IR out, the size of the stock runtime, feature costs |
| [PROVENANCE.txt](PROVENANCE.txt) | The Kotlin/Native 2.4.21 release archive the work used, and its SHA-256 |

## Conventions

- **VERIFIED** (**[V]** in design-plan.md): read at the cited source line, or measured with the cited command.
  **INFERRED** (**[I]**): reasoned from what was read, not checked.
- `File.kt:12-34` means lines 12 to 34 of that file. Each note defines its path prefixes at the top. They point
  into the Kotlin repository at tag v2.4.21 (github.com/JetBrains/kotlin, commit 9180ce6a), the archived
  github.com/JetBrains/kotlin-native repository at tag v1.3.70, or the Kotlin/Native 2.4.21 prebuilt distribution.
  `git:` marks a file read with `git show` from the v2.4.21 tag.
- Sizes are in bytes; 1 KB = 1024 bytes.

## Abbreviations

| Term | Meaning |
|---|---|
| IR | LLVM intermediate representation: the compiler's output before machine code |
| SSA | static single assignment: an IR value that lives in a register, not in memory |
| DFG | the compiler's data-flow graph, used for devirtualisation and dead-code elimination |
| LTO | link-time optimisation: the whole program optimised as one module at link time |
| DCE | dead-code elimination |
| CI | `compiler_interface.bc`, the runtime module from which the compiler takes types and declarations |
| F, DL | the target-feature string clang uses for Cortex-M4F, and the LLVM data layout (design-plan.md) |
| EABI, PIC, GOT | the Arm embedded ABI; position-independent code; the global offset table PIC goes through |
| GC, MM | garbage collector, memory manager |
| STW | stop-the-world: the program waits while the collector runs |
| stms, pmcs, cms | the stock collectors: single-thread mark-sweep, parallel mark concurrent sweep, concurrent mark-sweep |
| GHA | global hierarchy analysis, the compiler's class-hierarchy optimisation (enabled by `-opt`) |
| EH | exception handling |
| EHABI | the Exception Handling ABI for the Arm architecture: unwind tables in `.ARM.exidx` / `.ARM.extab` |
| LSDA | language-specific data area: the per-function table of call sites and landing pads that the personality routine reads |
| UCB | `_Unwind_Control_Block`, the exception object of the ARM EHABI unwinder |
| SjLj | the setjmp/longjmp exception model |
| RTTI | run-time type information |
| TLS | thread-local storage |
| CAS | compare-and-swap, an atomic operation |
| ISR | interrupt service routine, an interrupt handler |
| PRIMASK | the Cortex-M register that masks interrupts |
| DWT, CYCCNT | the Cortex-M data watchpoint and trace unit and its cycle counter |
| VFP | the Arm floating-point unit and its instructions |
| AAPCS | the Arm procedure call standard |
| Stop 1 | an STM32L4 low-power mode that keeps SRAM and stops most clocks |
| RTC, LPTIM, EXTI, LSE, SysTick | STM32 parts: the real-time clock, the low-power timer, the external interrupt lines, the 32.768 kHz crystal oscillator, the Cortex-M system timer |
| RM0394 | ST's reference manual for the STM32L4 microcontrollers |
| WFI | wait for interrupt: the Cortex-M instruction that sleeps until an interrupt |
| M1-M4 | the bring-up milestones of design-plan.md §3: no allocation; objects and GC; strings, arrays and exceptions; coroutines |
| E0-E6 | the experiments of design-plan.md §6 |
| D1-D11, R1-R16 | the decisions and risks of design-plan.md |
| KN#n, KT-n | a github.com/JetBrains/kotlin-native issue or pull request; an issue in JetBrains' YouTrack |
| kotlin@sha | a commit of github.com/JetBrains/kotlin |

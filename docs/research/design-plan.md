# kmicro: technical design and experiment plan

Written in October 2026, before most of kmicro existed, for a Kotlin layer inside an existing C firmware on an
STM32L431. The decision table below gives the status of each decision: what the code does now. The rest of the
note is the plan as it was, the record of why; sections that describe something kmicro did not build start with a
status line. [design-check.md](design-check.md) checks each claim of this plan against the compiler and runtime
sources, and [how-it-works.md](../how-it-works.md) describes kmicro as it is.

Markers: **[V: ref]** means verified, with the source line, command or commit given; **[V abi]**, **[V mm]** and
**[V eh]** mean verified in [R_abi.md](R_abi.md), [R_mm.md](R_mm.md) and [R_eh.md](R_eh.md); **[I]** means inferred.
Paths:
- `KN` = the Kotlin/Native 2.4.21 prebuilt distribution for Windows (`kotlin-native-prebuilt-windows-x86_64-2.4.21`)
- `SRC` = the github.com/JetBrains/kotlin repository at tag v2.4.21
- `BK` = `SRC/kotlin-native/backend.native/compiler/ir/backend.native/src/org/jetbrains/kotlin/backend/konan`
- `RT` = `SRC/kotlin-native/runtime/src`

The C firmware is called the kernel below: it owns reset, the interrupt vectors, the watchdog and sleep, and the
Kotlin code runs as an application layer above it.

---

## 0. Decisions at a glance

| # | Decision (October 2026) | Key evidence | Status now |
|---|---|---|---|
| D1 | Compile with `-target linux_arm32_hfp` (hard-float, toolchain dependencies already downloaded). Do not use `android_arm32`. | `ls` of the Kotlin/Native dependency folder: arm gnueabihf gcc, msys2, llvm-21 [V]; `KN/konan/konan.properties:511-526` [V] | **Kept.** kmicro compiles for `linux_arm32_hfp`. The target is deprecated, so kmicro is pinned to 2.4.21. |
| D2 | No retargeting after the fact. The compiler takes the triple and data layout from `compiler_interface.bc`, which we build with clang for `thumbv7em-unknown-none-eabihf`. CPU and features come from `-Xoverride-konan-properties`. Kotlin IR then comes out of the compiler already Thumb-2/M4. | `BK/llvm/ContextUtils.kt:409-412`, `BK/llvm/Runtime.kt:23-62`, `ContextUtils.kt:301-303` (LTO triple = module triple), `OptimizationPipeline.kt:241` [V] | **Reversed.** kmicro saves the IR after the `Codegen` phase and rewrites it as text: [toolchain/retarget.py](../../toolchain/retarget.py) sets the thumbv7em triple and clang's Cortex-M4 attributes. The reason given in the appendix (no `opt`/`llc` to rewrite with) does not hold: clang compiles textual IR directly (design-check.md #16). |
| D3 | Replace every runtime module by running the unmodified compiler jar against a junction-built copy of the distribution (`-Dkonan.home`). `-Xruntime` alone replaces only `compiler_interface.bc`. | `BK/llvm/runtime/RuntimeModulesConfig.kt:18-30`; `CompilerOutput.kt:112-198` [V] | **Dropped.** kmicro uses the distribution as it is. The IR is saved before the compiler links its own runtime, so no runtime module has to be replaced. |
| D4 | Bitcode route: `-produce program -nomain -entry <fq main> -Xtemporary-files-dir -Xdisable-phases=ObjectFiles,Linker` → keep `out.bc`. Then the bundled clang 21 does codegen and arm-none-eabi-gcc links. The LLVM bundle has no `opt`/`llc`/`llvm-link`/`llvm-dis`, and the plan needs none. | `ls .../llvm-21-...-150/bin`: clang, clang++, clang-cache, ld.lld, lld, llvm-ar, llvm-cov, llvm-profdata [V]; `TopLevelPhases.kt:88,196`, `ObjectFiles.kt:19`, `Linker.kt:27` [V] | **Replaced.** `-p static -nomain -opt` with `-Xsave-llvm-ir-after=Codegen,LinkBitcodeDependencies` ([toolchain/kn.py](../../toolchain/kn.py)). clang and ld.lld then link the Kotlin code, the runtime and the C code with LTO; neither `opt` nor `llc` is needed. |
| D5 | Kotlin→C uses `@SymbolName("k_x") external fun` with primitive arguments: a plain direct call, no thread-state switch, no C stub. There is no cinterop and no `staticCFunction`. Those always generate C stubs, which the backend compiles with `-target arm-unknown-linux-gnueabihf -mfpu=vfp -fPIC` (ARM state, double-precision VFP; the M4 runs only Thumb code and has a single-precision FPU). | `IrUtils.kt:255-268`, `IrToBitcode.kt:2536-2613`, `CBridgeGen.kt:180-231,698-708`, `CStubsManager.kt:36-44`, `SRC/native/utils/.../ClangArgs.kt` (git HEAD, `specificClangArgs`) [V]; ARM-state default for an `arm-` triple [I] | **Reversed.** Kotlin calls C through cinterop: [toolchain/bridges.py](../../toolchain/bridges.py) takes the compiler's call bridges from the IR saved after `LinkBitcodeDependencies`, so they are compiled for Cortex-M4 with the rest of the program. kmicro's build uses no `@SymbolName`. |
| D6 | C→Kotlin has exactly one entry. The C loop calls `kmicro_step()`, which calls the compiler-generated `Konan_start(NULL)`, which calls Kotlin `main()`. One call is one application step. `@CName` is not usable: it is only emitted by the C-adapter for static/dynamic libraries. | `EntryPoint.kt:27-93`; `Ir.kt:241-253` (entry point independent of `-nomain`); `CompilerOutput.kt:229-239` (no `main` alias with `-nomain`); grep: `CName` only in `cexport/`, `objc*` [V] | **Reversed.** There is no step function. C calls any top-level Kotlin function directly, by its compiler symbol or by a plain C name that `tools/kbuild.py --c-api` adds; `kmicro_init()` runs the module initializers first ([how-it-works.md](../how-it-works.md), "Calling between C and Kotlin"). |
| D7 | Exceptions: our own `__gxx_personality_v0` on libgcc's ARM EHABI unwinder (eh option b), from M3. In M1-M2 a throw is fatal. | §4 | **Kept** ([runtime/eh.c](../../runtime/eh.c)). Cleanup pads end in `__cxa_end_cleanup`, not `_Unwind_Resume` (design-check.md #26). |
| D8 | GC: precise, non-moving, stop-the-world mark-sweep on a 12 KB static heap. No per-object header; collection only on allocation failure, at idle, or on explicit request; never in an ISR. | §5 | **Kept, with changes** ([runtime/mm.c](../../runtime/mm.c)). The heap is `KM_HEAP_BYTES`, 16 KB by default. There is no idle-time collection: the collector runs when an allocation fails or on request (`kmicro_gc()`, `GC.collect()`). Interrupt handlers must not allocate. |
| D9 | TLS: emulated TLS at codegen (`clang -femulated-tls`) with our own static-pool `__emutls_get_address`. libgcc's version needs malloc (checked in E0.3). | `LlvmUtils.kt:217-230` [V]; libgcc has `__emutls_get_address` [V nm]; malloc use [I] | **Replaced.** `retarget.py --no-tls` turns every `thread_local` global into an ordinary global (one thread), so no TLS support is linked. |
| D10 | 64-bit atomics: our own `__atomic_*_8` under PRIMASK in `km_sys.c`. libgcc v7e-m+fp/hard has no `__atomic_*`. | nm of libgcc.a [V] | **Kept**, in [runtime/atomic64.c](../../runtime/atomic64.c). |
| D11 | No Kotlin code in external flash: the board's external flash chip is on an SPI bus and not memory-mapped. | the board's design (not part of this repository) | **A board matter.** kmicro's code goes wherever the board's linker script puts `.text`; memory outside the address space can hold data only. |

---

## 1. Thesis

kmicro runs, on a bare-metal STM32L431 (Cortex-M4F, 16 MHz, 64 KB SRAM, no OS), the machine code that the official, unmodified Kotlin/Native 2.4.21 compiler produces for a normal Kotlin program. The compiler jar is the release file (SHA-256 `7ded8eaa3bf8b716539321b1f1fc198486295da503a560541f64bb18ee81928e` [V sha256sum], [PROVENANCE.txt](PROVENANCE.txt)). The plan used standard command-line options plus one internal opt-in (`-opt-in=kotlin.native.SymbolNameIsInternal`, the gate on `@SymbolName`, `RT/main/kotlin/kotlin/native/Annotations.kt:17-37` [V]; fallbacks in §7); since cinterop replaced `@SymbolName` (D5), the build needs no opt-in. The program runs as the application layer above the C kernel, on a small C runtime of our own instead of the stock one. For this target the stock runtime is 25 bitcode modules, 1,618,416 bytes [V ls -la], built for pthreads, C++ exceptions, TLS and mimalloc-class allocators.

Why it is hard:
- The 2.4.21 compiler hard-codes threads, C++ zero-cost exceptions (`__gxx_personality_v0`, `ContextUtils.kt:596-625` [V]) and general-dynamic TLS (`LlvmUtils.kt:225` [V]).
- Its runtime contract has about 50 compiler hooks (`RT/compiler_interface/cpp/CompilerCInterface.cpp`) plus whichever of the 322 `@GCUnsafeCall` stdlib natives survive dead-code elimination [V grep].
- The earlier Kotlin/Native MCU target (zephyr_stm32f4_disco, 2017-2020; begun by a community contributor, made to run on STM32F4 and maintained by JetBrains) needed an OS, aborted on every throw, published no size figures, and ran on a part with about 4× the flash and 3× the RAM [I from part number]. It was cut when the new memory manager required threads (kotlin@aea8bac7d29, 1.9.20) and deleted in 2.0.0 [V R_zephyr.md].
- The Kotlin code, the runtime and the heap must fit beside the kernel in the flash and SRAM it leaves free.
- The Kotlin layer must never disturb the kernel's real-time paths: its watchdog window and its interrupt-driven I/O bound how long a Kotlin step may run.

Claims will be limited to what we measure: flash and RAM bytes, GC pause and throw latency (DWT cycle counter on the device), bytes per suspended coroutine, Stop-1 residency (RTC), and output identical to the stock runtime on host differential tests.

---

## 2. Architecture

### 2.1 Pipeline

**Status:** not built in this form (D2-D4, D9). The pipeline kmicro uses is in [how-it-works.md](../how-it-works.md), "The build".

```
Kotlin sources ──► java … MainKt konanc  (konan.home = kmicro-dist, a junction copy of KN
                    -target linux_arm32_hfp   whose targets/linux_arm32_hfp/native/*.bc are OURS)
                    -produce program -nomain -entry kmicro.app.main -opt
                    -Xbinary=smallBinary=true
                    -Xoverride-konan-properties=targetCpu.linux_arm32_hfp=cortex-m4;targetCpuFeatures.linux_arm32_hfp=<F>
                    -Xdisable-phases=ObjectFiles,Linker  -Xtemporary-files-dir=<o>
                       │  (in the compiler: codegen with triple/DL from our compiler_interface.bc
                       │   → links our runtime.bc + launcher.bc + empty modules
                       │   → internalize + globaldce + lto<Oz>, RemoveRedundantSafepoints)
                       ▼
                    <o>/out.bc   (thumbv7em, cortex-m4 attributes; Kotlin + stdlib + kmicro runtime)
                       │
       clang 21 (Kotlin/Native bundle): --target=thumbv7em-unknown-none-eabihf -mcpu=cortex-m4 -mfpu=fpv4-sp-d16
                                        -mfloat-abi=hard -Os -Xclang -disable-llvm-optzns -femulated-tls -fno-pic
                                        -ffunction-sections -fdata-sections -fstack-usage -c -x ir out.bc
                       ▼
                    kotlin.o  +  km_sys.o (gcc: emutls, __atomic_*_8, M1-M2 EH stubs)
                       │      +  the kernel's objects (gcc, unchanged flags)
                       ▼
       arm-none-eabi-gcc (xPack 15.2.1) -T <board>.ld --specs=nano.specs -Wl,--gc-sections
                         -Wl,--target2=rel  … -lm  (libgcc unwinder from M3)
                       ▼
                    firmware.elf / .bin  (one image; the kernel owns reset, vectors, sleep)
```

Facts behind the pipeline:
- Konan_start/LTO pipeline: `-opt` is required for DCE, devirtualization and escape analysis. `smallBinary` selects Oz (`NativeSecondStageCompilationConfig.kt:104-114` [V]).
- The LTO TargetMachine uses the module triple plus `targetCpu`/`targetCpuFeatures` (`OptimizationPipeline.kt:157-216, 241` [V]). The override string `<F>` must equal clang's own feature string for cortex-m4, so that runtime functions inline into Kotlin functions and per-function attributes match [I] (taken in E0.1).
- `out.bc` is written before `ObjectFiles` (`TopLevelPhases.kt:196`, `Bitcode.kt:44-51`) and kept when `-Xtemporary-files-dir` is given (`SRC/native/utils/.../TempFiles.kt:23-36`) [V].
- The compiler is run with `java` directly, not `run_konan.bat`. The batch file splits `-Dkonan.home=<path>` at `=` [I, cmd parsing]. The java line copies the bat's own (`KN/bin/run_konan.bat`: `-ea -Xmx3G -XX:TieredStopAtLevel=1 -Dfile.encoding=UTF-8 -Dkonan.home=… -cp …/kotlin-native-compiler-embeddable.jar org.jetbrains.kotlin.cli.utilities.MainKt konanc`) [V].
- `kmicro-dist` layout (a folder next to KN):
  - `klib`, `konan/lib`, `konan/nativelib`, `konan/platformDef`, `konan/swift_export` are junctions to KN.
  - `konan/konan.properties` and `konan/compiler.fingerprint` are copied unmodified.
  - `konan/targets/linux_arm32_hfp/native/` holds our files.
  - This uses `Distribution.defaultNatives = $konanHome/konan/targets/<t>/native` (`SRC/native/utils/.../Distribution.kt`, git HEAD) [V]. Junctions avoid a 650 MB copy.

### 2.2 Memory budget

**Status:** the heap default became 16 KB (`KM_HEAP_BYTES`). [examples/selftest/stm32l431](../../examples/selftest/stm32l431) prints the flash and RAM a complete program uses.

The STM32L431 has 256 KB of flash and 64 KB of SRAM (one region at 0x20000000). The kernel keeps the rest of both; kmicro's share was budgeted as follows.

Flash:

| Item | Bytes | Status |
|---|---|---|
| kmicro C runtime, M3 complete | ≤ 16,384 budget | [I] |
| libgcc EHABI unwinder (`unwind-arm.o` 2,676 + `pr-support.o` 952 + `libunwind.o` 408 text, plus exidx) | ≈ 4,300 | [V eh report sizes] |
| Kotlin code + stdlib + RTTI + literals + EH tables | ≤ 112,640 budget (decided by E1/E4) | [I] |
| Soft-double, libm, `__aeabi_*` pieces pulled in | ≤ 6,144 budget | [I] |

SRAM:

| Item | Bytes | Notes |
|---|---|---|
| Stack | 8,192 | Kotlin frames and their shadow-stack slots live here, plus about 1 KB during a throw [V eh frames; I total]. Stack painting logs the high-water mark. |
| Kotlin heap `km_heap[12288]` (in .bss, 8-aligned) | 12,288 | Tunable 12-16 KB from the logged peak live bytes |
| kmicro runtime state: globals table 96×4, mark stack 64×4, free lists ~80, TLS slots 8×4, stable refs 8×8, exception slots 2×(UCB 88 + 4), emutls pool 64 | ≈ 1,100 | [I sizes] |
| Kotlin module .data/.bss (init-state words, primitive globals) | ≤ 1,024 budget | measured in E2-E5 |

Notes:
- There is no separate shadow-stack area. Each Kotlin frame allocas `FrameOverlay` + slots on the C stack (`CodeGenerator.kt:1351-1356`, `EnterFrame` at `:1411-1413` [V]). The runtime keeps only the pointer `km_top`.
- External flash that is not memory-mapped holds data only, if any. It is never used for code (D11).

### 2.3 Runtime modules

**Status:** not built under these names. The runtime became `runtime/*.c` and `runtime/*.cpp` ([how-it-works.md](../how-it-works.md), "The runtime"). `km_ci.c` and `km_empty.c` were not needed (D3), and the 64-bit atomics of `km_sys.c` are in `runtime/atomic64.c`.

All of these are C11 compiled to bitcode with clang 21, except km_sys.c.

| File | Becomes | Responsibility |
|---|---|---|
| `km_types.h` | — | Exact mirrors of `ObjHeader`, `ArrayHeader`, `StringHeader`, `TypeInfo` (18 fields, no `WritableTypeInfo`), `InterfaceTableRecord`, `AssociatedObjectTableRecord`, `ExtendedTypeInfo`, `FrameOverlay`, `InitNode`, tag constants. Every declaration carries `__attribute__((nothrow))` except `ThrowException`, `AllocArrayInstance`, `CallInitGlobalPossiblyLock` and `CallInitThreadLocal` (the same split as stock: `RT/main/cpp/Memory.h:180-266`, `Exceptions.h:17-23`, `Runtime.h:24-37` [V]). |
| `km_ci.c` | `compiler_interface.bc` | `touch<Type>` globals and `touch<Fn>()` address-takers, as in `RT/compiler_interface/cpp/CompilerCInterface.cpp` [V]. Supplies the triple, data layout, struct types and the nounwind flags the compiler copies (`ContextUtils.kt:330-345` [V]). |
| `km_runtime.c` (unity: `km_core.c`, `km_heap.c`, `km_array.c`, `km_string.c`, `km_number.c`, `km_box.c`, `km_misc.c`) | `runtime.bc` (`-fno-exceptions`) | Frames, init, globals, TLS slots, type checks, reference stores, allocator and GC, natives. Hot hooks are `always_inline`. |
| `km_launcher.c` (+ `km_eh.c`) | `launcher.bc` (`-fexceptions`) | `kmicro_init()`, `kmicro_step()` (both `used`), `ThrowException`, personality, `__cxa_*`, `Kotlin_getExceptionObject`, unhandled-exception path. `launcher.bc` is always linked for PROGRAM (`CompilerOutput.kt:118` [V]). |
| `km_empty.c` | 22 empty modules (`mm`, `common_alloc`, `common_gc`, `common_gcScheduler`, `noop_crashHandler`, `{manual,adaptive,aggressive}_gcScheduler`, `{noop,same_thread_ms,concurrent_ms,pmcs}_gc`, `source_info_libbacktrace`, `libbacktrace`, `{custom,legacy,std}_alloc`, `{noop,impl}_externalCallsChecker`, `debug`, `objc`, `exceptionsSupport`) | Satisfy every file name the compiler may open for any binary option (`CompilerOutput.kt:131-187` [V]). |
| `km_sys.c` | gcc object (not bitcode) | Symbols introduced only at codegen, after LTO: `__emutls_get_address`, `__atomic_{load,store,exchange,compare_exchange,fetch_add,fetch_sub,fetch_and,fetch_or,fetch_xor}_8` (PRIMASK), and in M1-M2 fatal stubs `__aeabi_unwind_cpp_pr0/1/2` and `_Unwind_Resume` so that the libgcc unwinder is not pulled in. |

On the kernel side the plan needed little: the C API of §2.4, a call to `kmicro_init()` once the kernel's own
initialisation is done, calls to `kmicro_step()` from the main loop only while no time-critical work runs, a fault
code and a log tag for Kotlin, a stack raised to 8 KB, and `kotlin.o km_sys.o -lm` in its link.

The kernel's start-up code did not run `.init_array`, so `kmicro_init` was to run it itself. **Status:** in kmicro the
board's start-up code runs `.init_array` before `main` ([how-it-works.md](../how-it-works.md)).

### 2.4 C kernel API boundary

**Status:** replaced by cinterop (D5) and direct calls into Kotlin (D6). The rule that interrupt handlers do not
allocate still holds ([how-it-works.md](../how-it-works.md), "Interrupts").

- **Kotlin → C:** `@SymbolName` externals in package `kmicro.kernel`. They compile to a plain `call` with no thread-state switch and no filtering landing pad [V `IrToBitcode.kt:2536-2613`]. Inside a `try` they become `invoke`, which is harmless because C has no unwind entries.
- **Types:** Int, UInt and Float only, matching `int32_t`/`uint32_t`/`float`. No Long, Double, Boolean or struct.
  - Hard-float AAPCS on both sides: the kernel is built with `-mfloat-abi=hard`, so its objects say `Tag_ABI_VFP_args: VFP registers` [V readelf -A].
  - Buffers (M3) are passed as an address Int, obtained through `usePinned { it.addressOf(0).toLong().toInt() }` (public `kotlinx.cinterop`, `@OptIn(ExperimentalForeignApi::class)`, no C stub) [I].
- **Initial API:**

  ```c
  void     k_log(int32_t code, int32_t value);          /* into the kernel's event log */
  uint32_t k_now_ms(void);                               /* M4: keeps counting through Stop 1 */
  uint32_t k_take_events(void);                          /* ISR-set bits, taken under PRIMASK */
  int32_t  k_payload(int32_t src);
  void     k_set_wake_ms(int32_t ms);                    /* -1 none, 0 run again, >0 deadline */
  void     k_console_write(uint32_t addr, int32_t len);  /* UTF-8 (M3, debug only) */
  void     k_fatal(int32_t code, int32_t arg) __attribute__((noreturn)); /* the kernel's fault reset */
  ```

- **C → Kotlin:** `void kmicro_step(void) { Konan_start(NULL); if (km_gc_wanted()) km_gc_collect(); }`.
  - `Konan_start` is generated by the compiler with `try { main() } catch (Throwable) { Kotlin_processUnhandledException; Kotlin_terminateWithUnhandledException }` [V `EntryPoint.kt:56-90`].
  - After `Konan_start` returns, no Kotlin frame is live, so an idle GC has minimal roots.
- **Rules:**
  - ISRs never touch Kotlin.
  - `k_*` functions never block and never call Kotlin.
  - The kernel calls `kmicro_step` only while no time-critical work runs.
  - The kernel logs step duration (DWT); a hung step ends in a watchdog reset.

---

## 3. Minimal runtime spec

**Status:** the milestones were followed in this order, on QEMU. The symbols below became
[runtime/kmicro.h](../../runtime/kmicro.h) and the runtime files next to it. kmicro has no `k_fatal`: a fatal error
goes to `kmicro_panic()`, which prints the reason and calls the board's `kmicro_exit()`. Exceptions carry real
stack traces, and console output goes to the board's `kmicro_puts()`.

The authoritative list for each milestone is the `nm -u` / undefined-symbol output of the experiments (E1, E2-E5). Any native not implemented stays undefined and fails the link. That failure is the detector; there are no catch-all stubs.

Signatures are ARM32 C, with `KRef = ObjHeader*`. `OBJ_GETTER(f, a…)` means `ObjHeader* f(a…, ObjHeader** result)`: write `*result`, then return it [V `RT/main/cpp/Memory.h:147-160`].

All 24 eagerly imported functions must be **declared** in `compiler_interface.bc` from M1 on (`ContextUtils.kt:416-439` [V]): AllocInstance, AllocArrayInstance, RegisterGlobal, UpdateHeapRef, UpdateStackRef, UpdateReturnRef, ZeroHeapRef, ZeroArrayRefs, EnterFrame, LeaveFrame, SetCurrentFrame, CheckCurrentFrame, LookupInterfaceTableRecord, IsSubtype, IsSubclassFast, Kotlin_Any_getTypeInfo, ThrowException, AppendToInitializersTail, CallInitGlobalPossiblyLock, CallInitThreadLocal, AddTLSRecord, LookupTLS, Kotlin_initRuntimeIfNeeded, Kotlin_getExceptionObject. The lazily imported rest of `CompilerCInterface.cpp` is declared too.

### M1: no allocation (top-level functions, Int/Float, file-level `val`/`var`, calls into C)

| Symbol | Signature | kmicro semantics | Source |
|---|---|---|---|
| EnterFrame | `void(KRef* start, int32_t params, int32_t count)` | `f=(FrameOverlay*)start; f->previous=km_top; f->parameters=params; f->count=count; km_top=f;` (always_inline) | `RT/mm/cpp/ShadowStack.cpp`; `CodeGenerator.kt:1411-1413` [V] |
| LeaveFrame | same | `km_top = ((FrameOverlay*)start)->previous` | `Memory.h:231`; `CodeGenerator.kt:1590-1596` [V] |
| SetCurrentFrame | `void(KRef* start)` | `km_top = start`. Called first in every landing pad. | `CodeGenerator.kt:1023-1037` [V] |
| CheckCurrentFrame | `void(KRef*)` | `km_assert(km_top==start)` (emitted only without `-opt`) | `CodeGenerator.kt:1182-1185` [V] |
| Kotlin_mm_safePointFunctionPrologue / …WhileLoopBody | `void(void)` | Empty in release. With `KM_STACK_CHECK` (tests): `if (sp < __km_stack_floor+256) k_fatal(KM_E_STACK)`. | `Memory.h:263-264`; `IrToBitcode.kt:1209,1229` [V] |
| Kotlin_mm_switchThreadState{Native,Runnable}{,_debug} | `void(void)` | Empty | `Memory.h:254-260` [V] |
| AppendToInitializersTail | `void(InitNode*)` | Append to a singly linked list; called from `.init_array` constructors | `RT/main/cpp/Runtime.cpp:168-176`; `IrToBitcode.kt:456-475` [V] |
| Kotlin_initRuntimeIfNeeded | `void(void)` | Once: `km_heap_init()`; walk InitNodes with `init(0,NULL)` (ALLOC_TLS), commit TLS, `init(1,NULL)` (INIT_GLOBALS), `init(2,NULL)` (INIT_THREAD_LOCAL) | `Runtime.cpp:48-61,83-116` [V] |
| CallInitGlobalPossiblyLock | `void(uintptr_t* st, void(*init)(void))` | `2` → return; `1` (ours, recursive) → return; `0` → `*st=1; saved=km_top; init(); km_top=saved; *st=2`. In M1-M2 an exception is fatal; M3 adds state 3 and the wrap. | `Runtime.cpp:328-355`; `IrToBitcode.kt:2348-2364` [V] |
| CallInitThreadLocal | `void(uintptr_t volatile* g, uintptr_t* l, void(*init)(void))` | `*l=2; init();` | `Runtime.cpp:357-370` [V] |
| RegisterGlobal | `void(KRef*)` | Append to `km_globals[96]`; overflow → `k_fatal(KM_E_GLOBALS, n)` | `IrToBitcode.kt:1717-1719` [V] |
| AddTLSRecord / LookupTLS | `void(void* mem, void** key, int32_t n)` / `KRef*(void** key, int32_t i)` | One module means one key: reserve n of `km_tls[8]` and return `&km_tls[i]`. These are GC roots. | `Memory.h:238,244`; `LlvmUtils.kt:210-221` [V] |
| UpdateHeapRef, UpdateStackRef, UpdateReturnRef, ZeroHeapRef, ZeroArrayRefs, UpdateVolatileHeapRef | `void(KRef* loc, KRef v)` / `void(ArrayHeader*)` | Plain stores (always_inline). No barrier, because the collector is stop-the-world. | `Memory.h:210-227`; stock `RT/mm/cpp/Memory.cpp:124-167` [V mm] |
| CompareAndSetVolatileHeapRef / CompareAndSwap… / GetAndSet… | `bool(KRef*,KRef,KRef)` / `OBJ_GETTER(…)` | Plain compare and store (single core; ISRs never touch the heap) | `Memory.h:221-223` [V] |
| Kotlin_Any_getTypeInfo | `const TypeInfo*(KRef)` | `((TypeInfo*)(o->hdr & ~3))->typeInfo_` | `RT/main/cpp/Natives.cpp:110-112`; `Memory.h:73-78` [V abi] |
| IsSubtype / IsSubclassFast / LookupInterfaceTableRecord | see `Types.h:76`, `TypeInfo.h:170` | Ports of the stock C++ | `Types.cpp:23-42`; `TypeInfo.cpp:30-47` [V abi] |
| Kotlin_process{Object,Array,EmptyObject}InMark | `void(void*, KRef)` | Empty. Their addresses are stored in every TypeInfo. | `RTTIGenerator.kt:259-262` [V abi] |
| AllocInstance / AllocArrayInstance | see M2 | `k_fatal(KM_E_NOHEAP)` in M1 | — |
| ThrowException | `noreturn void(KRef)` (not nothrow) | M1-M2: `k_fatal(KM_E_THROW, classId)` | stock `Exceptions.cpp:39-43` [V abi] |
| Kotlin_getExceptionObject, `__gxx_personality_v0`, `__cxa_begin_catch`, `__cxa_end_catch`, `_ZSt9terminatev`, `_ZTI18ExceptionObjHolder` | per `ContextUtils.kt:596-625` | M1-M2 stubs: fatal, or a dummy for the typeinfo | [V] |
| Kotlin_processUnhandledException / Kotlin_terminateWithUnhandledException | `void(KRef)` | `k_fatal(KM_E_UNHANDLED, classId)` | `RT/main/kotlin/kotlin/native/Runtime.kt:77-91` [V] |
| `__aeabi_unwind_cpp_pr0/1/2`, `_Unwind_Resume` (km_sys.c) | — | M1-M2 fatal stubs, so libgcc's 4 KB unwinder is not linked | [I] |
| kmicro_init / kmicro_step (ours) | `void(void)` | init: run `__init_array_start..end`, then `Kotlin_initRuntimeIfNeeded()`. step: see §2.4. | — |
| memset / memcpy / memmove | newlib-nano | Slot zeroing (`llvm.memset`, `CodeGenerator.kt:1354-1356` [V]) | — |

### M2: objects and GC (classes, interfaces, `object`, lambdas, linked structures; no arrays yet)

| Symbol | Signature | Semantics | Source |
|---|---|---|---|
| AllocInstance | `OBJ_GETTER(AllocInstance, const TypeInfo*)` nothrow | `g=(ti->instanceSize_+7)>>3`; allocate (§5); zero; `hdr=ti`; `*result=o`. If `ti->flags_ & TF_HAS_FINALIZER`, fatal (v1). | `Memory.h:180`; `RT/mm/cpp/Memory.cpp:105-108` [V mm] |
| AllocArrayInstance | `OBJ_GETTER(…, const TypeInfo*, int32_t n)` may throw | `elem=-instanceSize_`; size = `align8(8 + n*elem)`; `count_=n`; n<0 → M2 fatal, M3 `ThrowIllegalArgumentException`. Strings: `count_` includes the 3 header units on ARM32. | `KObject.hpp:61-76`; `KString.h:28-67`; `Memory.cpp:110-116` [V abi/mm] |
| km_gc_collect (internal), Kotlin_native_internal_GC_collect | `void(KRef)` | §5 | `RT/mm/cpp/Memory.cpp:223-225` [V] |
| Kotlin_mm_createRetainedExternalRCRef / releaseExternalRCRef / disposeExternalRCRef | `void*(KRef)` / `void(void*)` | `km_stable[8] {obj, rc}`; rc>0 is a root | `RT/main/cpp/ExternalRCRef.hpp:296-298` [V] |
| Kotlin_Any_hashCode | `int32_t(KRef)` | `(int32_t)(uintptr_t)o` (non-moving) | `Natives.cpp:40-48` [V mm] |
| in{Boolean,Byte,Char,Short,Int,Long}BoxCache / getCached…Box | `bool(x)` / `OBJ_GETTER` | `in*` returns false, so the fast paths fold away; `getCached*` is fatal (unreachable) | `RT/main/kotlin/kotlin/native/internal/Boxing.kt:11-75` [V] |
| Konan_getWeakReferenceImpl | — | fatal (v1: weak refs and Cleaner rejected) | `RT/main/cpp/FinalizerHooks.cpp:20-28` [V mm] |
| `__emutls_get_address` (km_sys.c) | `void*(struct {uint32 size, align; void* ptr; const void* templ;}*)` | Bump from a 64-byte static pool, copy or zero the template, cache in `ptr`; overflow fatal. Only if E1 shows TLS. | layout libgcc-compatible [I] |
| `__atomic_*_8` (km_sys.c) | standard libatomic ABI | PRIMASK save/disable/restore. Only if E1 shows i64 atomics. | [I] |

### M3: strings, arrays and real exceptions

| Group | Symbols (exact set taken from E1/E4 undefined lists) | Semantics | Port from |
|---|---|---|---|
| Arrays | `Kotlin_{Boolean,Byte,Char,Short,Int,Long,Float,Double}Array_{get,set,getArrayLength}` and `_without_BoundCheck`; `Kotlin_Array_{get,set,getArrayLength}` (+ without); `Kotlin_NativePtrArray_*`; `Kotlin_*Array_{fillImpl,copyImpl}`; `Kotlin_emptyArray`; `Kotlin_ByteArray_{get,set}*At` if reachable | Element at offset 8. An out-of-bounds index calls Kotlin `ThrowArrayIndexOutOfBoundsException` (`@ExportForCppRuntime`; our runtime's reference keeps it alive through internalize). `Kotlin_Array_set` = UpdateHeapRef semantics. All always_inline. | `RT/main/cpp/Arrays.cpp`; naming `BK/ir/FunctionsWithoutBoundCheckGenerator.kt:52-58` [V] |
| Strings (UTF-16 only; `latin1Strings` stays false, the default) | `Kotlin_String_{hashCode,get,subSequence,compareTo,getStringLength,plusImpl,equals,indexOfChar,indexOfString,lastIndexOfChar,replace,unsafeRangeEquals,toCharArray,unsafeStringFromCharArray,unsafeStringToUtf8[OrThrow]}`, `Kotlin_ByteArray_unsafeStringFromUtf8[OrThrow]`, `Kotlin_StringBuilder_{insertString,insertInt}`, `Kotlin_Char_{isHighSurrogate,isLowSurrogate,isISOControl,toString}`, `Kotlin_{Byte,Short,Int,Long}_toString`, `Kotlin_{Int,Long}_toStringRadix` | Length = `count_ − 3`. The hash is cached with `HASHCODE_IS_ZERO`. Literals are flash constants (tag 01) and are never written. | `RT/main/cpp/KString.cpp`, `KString.h:28-67`; `NativeSecondStageCompilationConfig.kt:361-363` [V] |
| Type names / console | `Kotlin_TypeInfo_{getPackageName,getRelativeName,isInstance}`, `Kotlin_io_Console_{print,println,println0,printlnToStdErr}` | Console: UTF-16 → UTF-8 → `k_console_write` (semihosting in QEMU) | `RT/main/cpp/Console.cpp:63` [V] |
| Exceptions (option b, §4) | `ThrowException`, `Kotlin_getExceptionObject`, `__gxx_personality_v0`, `__cxa_begin_catch`, `__cxa_end_catch`, `_ZSt9terminatev`, `_ZTI18ExceptionObjHolder`, `Kotlin_getCurrentStackTrace` (empty `NativePtrArray`), `Kotlin_getStackTraceStrings` (empty `Array<String>`), `Kotlin_processUnhandledException`, `Kotlin_terminateWithUnhandledException`, the `CallInitGlobalPossiblyLock` failure path (state 3 → `ThrowFileFailedToInitializeException`). libgcc: `_Unwind_RaiseException`, `_Unwind_Resume`, `__gnu_unwind_frame`, `_Unwind_VRS_*`, `__aeabi_unwind_cpp_pr0/1`. | §4 | `CodeGenerator.kt:1023-1180`, `Exceptions.cpp:39-43,110-112`, `Throwable.kt:36-41,153-159` [V] |
| Number formatting / parsing (only if reachable) | `Kotlin_native_NumberConverter_*`, `Kotlin_native_FloatingPointParser_*`, `Kotlin_{Float,Double}_*` | Port if E4 shows them reachable from the app; otherwise they stay undefined (app avoids them) | `RT/main/cpp/` [V abi] |
| C runtime | `__aeabi_d*`, `__aeabi_ldivmod`, `fmodf`/`fmod` | libgcc / newlib libm (`-lm`) | [V nm libgcc] |

### M4: coroutines and sleep

The runtime needs nothing new beyond M2+M3: coroutine frames are ordinary objects, `label` is a `blockaddress` dispatched with `indirectbr` [V mm: `IrToBitcode.kt:2277-2324`], and `BaseContinuationImpl.resumeWith` catches through real EH [V `RT/main/kotlin/kotlin/coroutines/ContinuationImpl.kt:21-50`]. Additions:

| Item | Where | Semantics |
|---|---|---|
| `kmicro.Loop` dispatcher | Kotlin library | Fixed arrays, `createCoroutineUnintercepted(Done)`, waits written with `suspendCoroutineUninterceptedOrReturn`. No interceptor, no `SafeContinuation`, zero allocation per wait. |
| Idle GC policy | `kmicro_step` | Collect after `Konan_start` returns when `allocated_since_gc ≥ heap/4` and no time-critical work runs |
| `k_now_ms` that keeps counting through Stop 1, RTC wake-up timer, `k_set_wake_ms` → Stop 1 when the kernel allows it | kernel | SysTick stops in Stop 1 (RM0394, the STM32L4 reference manual) |
| Avoid `kotlin.time` / `Kotlin_system_getSteadyTime*` and `suspendCoroutine` | app rule | Removes 64-bit time and per-suspend `SafeContinuation` allocation [V mm] |

---

## 4. Exceptions decision

**Status:** implemented as decided, in [runtime/eh.c](../../runtime/eh.c) (D7).

**Decision.** Use the libgcc ARM EHABI unwinder (`unwind-arm.o`, `pr-support.o`, `libunwind.o` from `thumb/v7e-m+fp/hard`, already in the toolchain's libgcc [V nm]) with our own personality and `__cxa_*` helpers in `launcher.bc`. Ship it at M3. In M1-M2 `ThrowException` is fatal and the EH entry points are stubs.

How it works:
- **`ThrowException`** lives in a `-fexceptions` translation unit and is deliberately not nothrow.
  - It fills one of two static, 8-aligned `{_Unwind_Control_Block, KRef}` slots and roots the KRef for the GC.
  - Then it calls `_Unwind_RaiseException`. If that returns, there is no handler, or the throw reached a C frame (C has no unwind entries [I]); the result is `k_fatal(KM_E_UNCAUGHT, classId)` with the object still intact.
- **Personality:**
  - Handles phase 1, phase 2 and `UNWIND_FRAME_RESUME`.
  - Parses LLVM's LSDA call-site table (uleb128 and udata4), installs cleanup pads (action 0) and catch pads (action > 0) with r0 = ucbp and r1 = selector, and calls `__gnu_unwind_frame` to continue.
  - It never reads the type table. Kotlin catch pads are `catch ptr null` and type matching runs in Kotlin code (`CodeGenerator.kt:1139-1165`, `IrToBitcode.kt:1044-1077` [V eh]).
  - Filtering pads exist only on cinterop bridges, which we do not generate (D5). (Once cinterop came in, they do occur: runtime/eh.c gives them the selector of their first action record.)
- **Catch helpers:** `__cxa_begin_catch` returns the UCB; `Kotlin_getExceptionObject` stores the KRef into the result slot; `__cxa_end_catch` frees the slot. Kotlin calls end_catch immediately, so 2 slots suffice [V `CodeGenerator.kt:1150-1165`].

Reasons:
1. Real semantics are needed: `Konan_start`'s catch, `finally` (lowered to catch+rethrow, `NativeLoweringPhases.kt:274` [V eh]), `runCatching`, and `resumeWith` turning failures into `Result.failure` [V].
2. Smallest fixed cost of any real-EH option: about 4.7 KB flash and 0.1 KB static RAM. libsupc++ (a) costs about 7.2 KB and drags in malloc and `.init_array` [V eh sizes].
3. Zero cost when nothing is thrown, unlike SjLj (d).
4. No compiler or LLVM switch can remove C++ EH in 2.4.21 [V `BinaryOptions.kt` has none; eh §1.6]. The lower-invoke route (c2) needs `opt`, which the bundle lacks [V ls]. (Corrected by design-check.md #29: `-Xllvm-lto-passes` can run `lower-invoke` inside the unmodified compiler. Option (b) was kept for reasons 1-3; (c2) remains a possible size lever that would change semantics.)
5. A throw uses about 1 KB of stack; the 8 KB stack absorbs it.

The kernel's hard real-time paths stay in C and never throw.

**Fallback:** if (b) fails the E4 matrix, link (a) (libsupc++ personality with our own `__cxa_allocate_exception` pool) as a reference, diff the behaviour, fix (b) [I 0.5-1 day].

---

## 5. GC decision

**Status:** implemented in [runtime/mm.c](../../runtime/mm.c) (D8), with these differences: a 16 KB default heap;
8 exact-size free lists plus one list for larger blocks, and no bump region (blocks of 256 bytes or more are taken
from the top of the heap, smaller ones from the bottom); no idle-time collection; and a panic, after a report of the
heap state, when an allocation fails even after a collection.

**Decision.** Precise, non-moving, stop-the-world mark-sweep, run on the caller's thread. Interrupts are never masked; ISRs never touch the heap.

**Heap.** 12,288 B static, 8-byte granules, no per-object header.
- The mark bit is bit 1 of the heap object's header word, which is always clear for heap objects (tag 00).
- Free blocks: `w0 = (granules<<2)|1`, `w1 = next`. Bit 0 never appears in a heap object header; tag 01 objects live in flash.

**Allocation.**
- Free lists: `km_free[12]`, exact lists for 1-8 granules, then ranges 9-16, 17-32, 33-128 and >128, plus a bump region at the top.
- Order: exact list → bump → first fit with split → collect and retry → `k_fatal(KM_E_OOM, size)`. The OOM log carries live bytes and the largest free run.

**Roots, in order:**
1. Frame chain from `km_top`, slots `[3+parameters, count)` (`RT/mm/cpp/ShadowStack.hpp:49-53` [V mm]).
2. `km_globals`.
3. `km_tls`.
4. Stable refs.
5. In-flight exception slots.

**Marking rules.**
- Skip a value ≤ 1 (null or `kInitializingSingleton`).
- Mark only addresses inside `km_heap`.
- A root that is a stack object (tag 11) has its fields scanned in place. Fields pointing outside the heap are skipped: every stack object has its own root slot (`CodeGenerator.kt:412-438,472-500` [V mm]), so it is reached exactly once through that slot and cycles among stack objects cannot loop.
- Push only objects that have reference fields (`objOffsetsCount_>0`, or `theArrayTypeInfo` with count>0).
- The mark stack holds 64 entries. On overflow, set a flag and rescan the heap linearly until clean.

**Sweep.** A linear walk that coalesces free blocks and lowers the bump pointer. Object size comes from TypeInfo, or from the count for arrays.

**Triggers.** Allocation failure; idle (after `Konan_start` returns, with `allocated_since_gc ≥ heap/4`, never while time-critical work runs); explicit `GC.collect()`.

Reasons:
- **Correctness of a precise, non-moving collector.** Every object value is reachable from a frame slot, a caller's slot, or a reachable object's final field, and collection happens only inside allocation calls. This is the same invariant stms relies on [V mm §1.2-1.4].
- **Moving is impossible.** References live only in SSA values across allocations, `addressOf` hands raw interior pointers to C, and the identity hash is the address [V mm §1.5].
- **No barrier needed.** Every reference store already goes through `UpdateHeapRef`, so a STW collector needs none, and an incremental collector stays possible later [V `CodeGenerator.kt:742-774`].
- **Cheap metadata.** No headers and no bitmap: about 0.4 KB of metadata and about 2.5-3 KB of code [I].
- **Pause.** Estimated about 4 ms for 500 live objects at 16 MHz [I], well inside the kernel's watchdog window. It is measured with DWT on the device. (Measured later: a full collection of the selftest's heap takes 1.8 ms, [stm32l431-report.txt](../../examples/selftest/stm32l431-report.txt).)
- **Weak refs and Cleaners rejected in v1.** Only `CleanerImpl` and `RegularWeakReferenceImpl` have finalizers [V mm].
- **Fragmentation** is handled by size classes, long-lived objects created at start-up, and big buffers kept in C.

---

## 6. Experiments, in order

**Status:** E0 and the measuring half of E1 were done ([MEASUREMENTS.md](MEASUREMENTS.md)). E2 was not run in this
form, because its pipeline (D2-D4) was replaced by the one the first measurements used. The goals of E3-E6 were
met by other means:

| Experiment | Goal | Status now |
|---|---|---|
| E0. Toolchain facts | E0.1: the feature string F and the data layout of clang for Cortex-M4. E0.2: the SHA-256 of the compiler. E0.3: whether libgcc's emutls needs malloc. | Done. F and the data layout are in `toolchain/retarget.py`, the hashes in [PROVENANCE.txt](PROVENANCE.txt). Emulated TLS became unnecessary (D9). |
| E1. Biggest unknowns, stock distribution | Per probe program: compile time, the undefined runtime symbols, section sizes, TLS, 64-bit atomics, `RegisterGlobal` count, stack arrays. E1.6: the size of the smallest program with the stock runtime. | Done with the `-p static` pipeline: MEASUREMENTS.md §1-3. |
| E2. M1 end to end through a replaced `compiler_interface.bc` (QEMU) | Data layout, float ABI and Thumb-only code of the copied-distribution build | Not run: D2-D4 were replaced. The retargeted build runs every test on QEMU (`tests/run_all.py`). |
| E3. M2 objects and GC | GC correctness under stress, `max_live`, the GC count | `tests/run_all.py --stress` runs the programs with a collection before every allocation (`KM_GC_STRESS`). |
| E4. M3 against the stock runtime | Byte-identical output of strings, arrays and the exception matrix on the host's stock runtime and on kmicro | [tools/difftest.py](../../tools/difftest.py) and `tests/diff/`. |
| E5. M4 coroutines | Suspend/resume without allocation per wait; bytes per suspended coroutine | Coroutines run in the tests and in examples/selftest; bytes per suspended coroutine were not measured. |
| E6. Device check | Size on the device; GC pause, throw latency and step time from DWT | [examples/selftest/stm32l431](../../examples/selftest/stm32l431) and its recorded report. |

Gate G1, which decided the project:
- `@SymbolName` is accepted. Otherwise switch to F1 (§7).
- p1 (the M1 probe): Kotlin .text+.rodata+.ARM.ex* ≤ 4 KB, and the undefined set contains no `AllocInstance`.
- The data layout is identical to E0.1.
- p5 (an app-shaped probe) Kotlin footprint:
  - ≤ 110 KB: **GO**.
  - 110-160 KB: GO with size work (latin1Strings, no box-cache references, avoid `HashMap`/`Any.toString` in the app).
  - over 160 KB: **NO-GO** for full-stdlib apps; the Kotlin layer stays at the M3 feature level (strings, arrays,
    exceptions).
- Each compile ≤ 5 min (otherwise note it and accept; there is no cache for this target [V `konan.properties:70-84`]).

Outcome: the app-shaped probe needed about 64 KB of flash in total (MEASUREMENTS.md §3), and a compile took about
21 s (design-check.md #48).

Checks planned for the first Kotlin object, as corrected by design-check.md #49-#55:
- `readelf -A`: v7E-M, Thumb-2, VFPv4-D16, single-precision hard float, VFP arguments, small enums, 4-byte wchar.
- `nm --special-syms`: no `$a` (ARM-state) mapping symbols.
- `objdump -dr`: no remaining calls to `EnterFrame`, `LeaveFrame` or the safepoint functions (they inline).
- `readelf -S`: no `.tdata` / `.tbss`; `nm -u`: no `__emutls_*`.
- `-fstack-usage`: no frame above 1 KB.

---

## 7. Risks and fallbacks

| # | Risk | Detection | Fallback |
|---|---|---|---|
| R1 | `-opt-in=kotlin.native.SymbolNameIsInternal` rejected (internal marker) | E1 compile | F1: `@file:Suppress("INVISIBLE_REFERENCE")` + `@file:OptIn(SymbolNameIsInternal::class)` [I K2 permits with a warning]. F2: `@GCUnsafeCall` with the same trick. F3 (public API only): a memory mailbox at a linker-script address, accessed with `interpretCPointer`/`pointed.value` (no C stub); kernel requests become suspend calls answered in the next step. F4: cinterop with stub compilation redirected (last resort: ARM-state/`-fPIC` stubs need `targetTriple` override and GOT handling). |
| R2 | Compiler rejects the C-built CI or the thumb triple | E2 | Fix the struct mirrors. Or keep the stock CI (armv6kz, identical DL by E0/E1) and force `-triple thumbv7em-unknown-none-eabihf` at codegen (clang overrides the module triple with a warning [I]). |
| R3 | Feature-string mismatch blocks inlining of hooks | E2 `bl EnterFrame` count | Copy F exactly from E0.1; `always_inline` on hooks |
| R4 | Code size (G1 NO-GO band) | E1/E4 | latin1Strings plus Latin-1 support in the string runtime; no constant boxes (they pin `*_CACHE` arrays, `BK/Boxing.kt:192-215` [V]); avoid `HashMap`/`toString`/`kotlin.text.Regex`; keep the app at the M3 feature level |
| R5 | Emulated TLS mismatch | E2 `.tdata` / nm | Local-exec TLS + `__aeabi_read_tp` + `.tdata/.tbss` sections in the linker script |
| R6 | Personality bugs | E4 matrix | Reference (a) libsupc++ for diffing; until fixed, the app does not rely on catch |
| R7 | Runtime C code holding refs across an allocation | GC stress + verify | `ObjHolder`-style frame macro in C (`Memory.h:279-311` pattern [V mm]) |
| R8 | Escape analysis puts up to 64 KB of arrays on the stack | `-fstack-usage` > 1 KB fails the build | `-Xdisable-phases=EscapeAnalysis` (`BK/driver/phases/LTO.kt:132` [V]) |
| R9 | Stack overflow at 8 KB | Painted high-water, `KM_STACK_CHECK` safepoint in tests | Raise to 10 KB from margin; keep loop bodies in helpers (slots are never reused [V mm]) |
| R10 | Real-time interference with the kernel (its watchdog window, its interrupt-driven I/O) | Step-time log | No `kmicro_step` and no GC while time-critical work runs; step budget 10 ms |
| R11 | `-g` needs `Konan_debugOperationsList` (otherwise a compiler NPE) and disables smallBinary | — | Never use `-g`; debug with map files, `-fstack-usage` and QEMU+gdb on the ELF symbols |
| R12 | `-Xdisable-phases` not honoured | E1: a `.o` appears or a linker runs | Harmless: `out.bc` is written before both phases [V] |
| R13 | Heap fragmentation | OOM log (largest free run) | Size classes, init-time allocation of long-lived objects, heap 12 → 16 KB |
| R14 | Version drift (the contract lives in bitcode) | — | Pin 2.4.21; on upgrade diff `ContextUtils.kt:414-502` and `TypeInfo.h` |
| R15 | QEMU fidelity (no cycle timing, larger RAM) | — | Linker script enforces the STM32L431 flash and RAM sizes; timing claims only from the device |
| R16 | Licences | — | Ported runtime code is Apache-2.0 (keep NOTICE); libgcc under the GCC Runtime Library Exception [I] |

---

## 8. What the plan set out to measure, and where it stands

1. **Provenance:** unmodified kotlinc-native 2.4.21 output runs bare-metal on a 256 KB / 64 KB Cortex-M4 at 16 MHz.
   Now: [PROVENANCE.txt](PROVENANCE.txt), the QEMU tests and the board report. kmicro's own runtime replaces the
   stock one; the build needs no copied distribution and no internal opt-in.
2. **Size:** the stock runtime for this target is 1.62 MB of bitcode in 25 modules [V], and the smallest program
   with it is 184 KB of `.text` (MEASUREMENTS.md §2). `tests/run_all.py` prints the size of every kmicro program.
3. **Memory and GC pause:** a 16 KB heap by default; a full collection of the selftest's heap takes 1.8 ms at 16 MHz
   (the board report).
4. **Exceptions:** real `try`/`catch`/`finally` on the MCU; the board report has the time of one throw and catch.
   The Zephyr target of 2017-2020 aborted on every throw (archive `Exceptions.cpp:201-210`).
5. **Coroutines:** bytes per suspended coroutine and Stop-1 residency: not measured.
6. **Correctness method:** output byte-identical to the stock runtime on the host ([tools/difftest.py](../../tools/difftest.py)).

---

## Appendix: disagreements between the notes, resolved

"abi", "mm", "eh" and "zephyr" are the notes R_abi.md, R_mm.md, R_eh.md and R_zephyr.md.

| Topic | Notes | Resolution |
|---|---|---|
| What `-Xruntime` replaces | mm: runtime.bc. abi: compiler_interface.bc. | abi is right [V `RuntimeModulesConfig.kt:22-29`]. We use a distribution copy instead (later dropped, D3). |
| Target to borrow | zephyr: android_arm32 + emulated TLS. abi/eh: linux_arm32_hfp. | linux_arm32_hfp (D1). Emulated TLS is applied at our own codegen step (later replaced, D9). |
| Retargeting | zephyr: save IR and rewrite it. abi: let the CI define the triple. | CI defines it (D2). There is no opt/llc to rewrite with [V]. Later reversed: kmicro rewrites the saved IR as text, as the Zephyr note proposed (D2). |
| C entry point | mm: `@CName("kmicro_step")` | Not emitted for PROGRAM [V grep]. Use `Konan_start` as the step (D6). Later reversed: C calls Kotlin functions directly (D6). |
| Exceptions | mm: fatal, then 10-20 KB later. eh: option (b), about 4.7 KB. | (b) from M3, fatal stubs in M1-M2 (D7). |
| C interop | zephyr: cinterop as in the old sample | Rejected: the stubs are built ARM-state, VFP and `-fPIC` (D5). |

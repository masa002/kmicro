# kmicro design: each claim of the plan checked against the source trees

Every claim of [design-plan.md](design-plan.md) checked against the Kotlin/Native compiler and runtime sources,
October 2026, before the plan was carried out. The "Fix" column is what the plan had to change; the last section
says what became of each change. Rows #49-#55 check the shell scripts and expected outputs of experiments E0-E6 as
the plan first spelled them out; design-plan.md §6 now summarises those experiments and lists the corrected checks.

Abbreviations: `BK`, `RT` and `KN` are as defined in design-plan.md. `git:` means read with `git show` at tag v2.4.21
(commit 9180ce6a). "Local" marks evidence from the first prototype pipeline (`-p static`, the IR rewritten as text,
clang LTO), which already ran when the plan was written but which the plan did not cite. That pipeline became
[toolchain/kn.py](../../toolchain/kn.py); the logs it produced then are not kept in this repository.

| # | Claim | Verdict | Evidence | Fix |
|---|---|---|---|---|
| 1 | `linux_arm32_hfp` works in 2.4.21; hard-float; dependencies present | confirmed (target is deprecated) | `KN/konan/konan.properties:511-531`; `ls` of the Kotlin/Native dependency folder; the compiler's warning on a local build ("target linux_arm32_hfp is deprecated and will be removed soon") | Pin 2.4.21, as planned |
| 2 | Triple and data layout of the generated module come from `compiler_interface.bc` | confirmed | `BK/llvm/Runtime.kt:23-62`; `BK/llvm/ContextUtils.kt:409-412`; constants module copies the layout only (`IrToBitcode.kt:2891-2893`) | — |
| 3 | The LTO TargetMachine uses the module triple plus `targetCpu`/`targetCpuFeatures` | confirmed | `BK/OptimizationPipeline.kt:89-99,151-219,237-249`; `BK/driver/phases/Bitcode.kt:162-168`; `ContextUtils.kt:301-303` | — |
| 4 | Per-function `target-cpu`/`target-features` come from overridable konan properties; `;` separates pairs, so commas inside F are safe | confirmed | `BK/llvm/LlvmAttributes.kt:28-35`; `BK/NativeSecondStageCompilationConfig.kt:55-87`; `BK/SetupConfiguration.kt:503-519`; git:`compiler/cli/cli-base/gen/.../K2NativeCompilerArguments.kt:458-464` (`delimiter = semicolon`) | — |
| 5 | Nothing in the backend checks the module triple against the KonanTarget | confirmed | grep `.targetTriple`/`runtime.target` in BK: only `BitcodeCompiler.kt:50-52` (disabled phase), `Bitcode.kt:165`, `OptimizationPipeline.kt:123,239-243` | — |
| 6 | armv6kz and thumbv7em data layouts are identical; the feature string F is known | confirmed; already measured locally | clang 21.1.6 output for a cortex-m4 C file; [MEASUREMENTS.md](MEASUREMENTS.md) §1; the local retarget script (now `toolchain/retarget.py`, `EXPECT_DL` and the Cortex-M4 attributes) | E0.1 is already done; take F from that clang output |
| 7 | `-Xruntime` replaces only `compiler_interface.bc`; every other module comes from `konan.home/konan/targets/<t>/native` | confirmed | `BK/llvm/runtime/RuntimeModulesConfig.kt:19-30`; `BK/CompilerOutput.kt:115-187`; `RuntimeModule.kt:9-39`; git:`native/utils/.../Distribution.kt:84` | — |
| 8 | The fingerprint files and the missing `runtime.fingerprint` do not matter | confirmed | Read only for caches: `BK/util/DistributionUtils.kt:15-18`, `BK/CacheStorage.kt:25-35`. No cacheable targets on a Windows host: `konan.properties:70-86` (`cacheableTargets.mingw_x64 =`) | — |
| 9 | The stdlib adds no per-target bitcode to the runtime set | confirmed | `KN/klib/common/stdlib/default` has no `targets/`; `CompilerOutput.kt:105-111,186` | — |
| 10 | The runtime can freely define globals | refuted (unstated trap) | For final binaries the compiler defines `Kotlin_gcMutatorsCooperate`, `Kotlin_latin1Strings`, `Kotlin_runtimeLogs`… itself, as strong exported definitions (`IrToBitcode.kt:2636-2684`, `LlvmUtils.kt:161-189`). The constants module defines `Kotlin_needDebugInfo` etc. (`IrToBitcode.kt:2891-2908`) | The runtime must only declare these `extern` |
| 11 | `run_konan.bat` splits arguments at `=`, so call java directly; the java line matches | confirmed | `KN/bin/run_konan.bat` (final `java` line; `--enable-native-access` only for JDK ≥24); local MEASUREMENTS.md §1 (splits at `=` and `,`) | — |
| 12 | `-produce program … -Xtemporary-files-dir` keeps `out.bc`, written before ObjectFiles | confirmed | `BK/driver/phases/TopLevelPhases.kt:88,196,393,403-432`; `Bitcode.kt:44-51`; git:`native/utils/.../TempFiles.kt:23-36` | — |
| 13 | `-Xdisable-phases=ObjectFiles,Linker` is honoured | confirmed | `ObjectFiles.kt:18-19`, `Linker.kt:26-27`; git:`compiler/config/.../PhaseSet.kt` (case-insensitive name match), `CompilerPhase.kt` (`invoke` checks `isEnabled`), `PhaseBuilders.kt` (Unit phase returns `{}` when disabled) | — |
| 14 | `-Xsave-llvm-ir-after=CStubs` writes `out.CStubs.ll`: Kotlin and stdlib, runtime only declared | confirmed | `LlvmPassesUtilities.kt:33-56` (`$moduleName.$phase.ll`, the directory must already exist); `TopLevelPhases.kt:480-491` | — |
| 15 | The LLVM bundle has no `opt`/`llc`/`llvm-link`/`llvm-dis` | confirmed | `ls llvm-21-…-150/bin` | — |
| 16 | "So IR cannot be rewritten after the fact" (appendix) | refuted | Local pipeline does text-IR rewrite with clang only (`-Xsave-llvm-ir-after=Codegen` → `retarget.py` → `clang -x ir`); its first differential tests printed the same as the stock runtime (5 of 5) | Drop this as a reason for D2. D2 is still valid on its own merits |
| 17 | `smallBinary` gives Oz and turns off performance inlining | confirmed | `NativeSecondStageCompilationConfig.kt:104-114`; `OptimizationPipeline.kt:167-171,230-234` | — |
| 18 | `-entry`, `-nomain` and `-opt` exist; the entry point does not depend on `-nomain`; no `main` alias with `-nomain`; `launcher.bc` is always linked for PROGRAM | confirmed | git:`K2NativeCompilerArguments.kt:689-695,877-881,907-911`; git:`.../konan/ir/Ir.kt:242-253`; `CompilerOutput.kt:117-119,229-239` | — |
| 19 | A `@SymbolName` external is a plain call: no thread-state switch, no stub | confirmed | `BK/ir/IrUtils.kt:255-268`; `IrToBitcode.kt:2536-2613`; external functions are legal (git:`FirNativeExternalDeclarationChecker.kt`) | — |
| 20 | `-opt-in=kotlin.native.SymbolNameIsInternal` is accepted | unverifiable | The marker is `internal` with level ERROR (`RT/main/kotlin/kotlin/native/Annotations.kt:19-37`). The local pipeline never used it; it uses `-p static` + `@CName` (the probes of MEASUREMENTS.md §3) | Keep the E1 gate. Add `-p static` + `@CName` as a known-working fallback |
| 21 | cinterop stubs are compiled ARM-state, double-precision VFP, `-fPIC` | confirmed | git:`native/utils/.../ClangArgs.kt:101,123-133`; `BK/CStubsManager.kt:40-44` | — |
| 22 | `Konan_start(args)` wraps `main` in try/catch(Throwable); passing NULL is fine for a parameterless `main` | confirmed | `BK/EntryPoint.kt:39-93` | — |
| 23 | `Konan_start` is `@ExportForCppRuntime`, so it gets a cleanup pad ending in `resume`, and EH symbols are referenced from M1 on | confirmed (design misses the M1 effect) | `EntryPoint.kt:55-57`; `CodeGenerator.kt:621-626,1382-1391` | See #26 |
| 24 | `@CName` is emitted only by the C adapter for libraries | confirmed | `CompilerOutput.kt:50-51`; `TopLevelPhases.kt:197,466` | — |
| 25 | `__attribute__((used))` keeps `kmicro_init`/`kmicro_step` callable from firmware C after internalize | refuted (strong inference) | Stock uses `RUNTIME_EXPORT = used,retain` with a KT-68640 note (`RT/main/cpp/Common.h:25-30`) for `Konan_main` (`RT/launcher/cpp/launcher.cpp:73-80`). On ELF, `used` alone goes to `llvm.compiler.used`, which the `internalize` pass (`OptimizationPipeline.kt:357-362`) still internalizes [I] | Use `__attribute__((used, retain))`. E2 check: `nm kotlin.o` shows `T kmicro_step` |
| 26 | Cleanup-pad `resume` needs `_Unwind_Resume`, so km_sys.c stubs that | refuted | Local: the retarget script ("ARM backend emits `__cxa_end_cleanup` itself", now `toolchain/retarget.py --eh-stubs`); the MEASUREMENTS.md §3 probes (`__cxa_end_cleanup` survives `--gc-sections` in all 6); a working implementation in the local runtime (now `runtime/eh.c`, `__cxa_end_cleanup`) | Define `__cxa_end_cleanup` outside the LTO bitcode (km_sys.c, or `used,retain`). M1-M2: fatal stub. M3: naked `ldr r0,=saved_ucb; ldr r0,[r0]; b _Unwind_Resume`, with the personality saving the UCB before it installs a cleanup pad |
| 27 | Landing pads use `catch ptr null`; type matching happens in Kotlin; `__cxa_end_catch` follows immediately | confirmed | `CodeGenerator.kt:1023-1037,1139-1165`; `ContextUtils.kt:596-625` | — |
| 28 | Filtering pads exist only on bridges | confirmed | `IrToBitcode.kt:2556-2595`; only `ObjCExportCoroutines.kt:69,74` use `@FilterExceptions` | — |
| 29 | "No compiler or LLVM switch can remove C++ EH; lower-invoke needs `opt`" | refuted | `-Xllvm-lto-passes` (git:`K2NativeCompilerArguments.kt:376-384`) replaces the LTO pipeline (`OptimizationPipeline.kt:345-360`), so `internalize,globaldce,function(lower-invoke,simplifycfg),lto<Oz>` runs inside the unmodified compiler. `ld.lld --lto-newpm-passes` can too | Keep (b), but list this as a fallback and size lever (panic=abort semantics) |
| 30 | `nothrow` split of declarations matches stock | confirmed | `RT/main/cpp/Memory.h:180-264`; `Exceptions.h:17,23`; `Runtime.h:24-32`; `TypeInfo.h:170`; `Types.h:75-79` | — |
| 31 | `runtime.bc` built with `-fno-exceptions` | refuted | Natives that throw: `Arrays.cpp:74-86` (bounds checks), `mm/cpp/Memory.cpp:110-116`, `Runtime.cpp:328-370`. Stdlib externals are not declared nounwind (only `ContextUtils.kt:604-624` and ObjC code set it). Clang marks every definition nounwind under `-fno-exceptions` [I]. Then a catch of an array index error, a negative-size array or a failed initialiser never runs. Local runtime uses `-fexceptions -funwind-tables` (now `tools/qbuild.py`, `CFLAGS`) and its exceptions differential test (now `tests/diff/d_exceptions.kt`) matches | Build the runtime with `-fexceptions`; put explicit `nothrow` on non-throwing functions (stock pattern) |
| 32 | M3 `CallInitGlobalPossiblyLock` "state 3 + wrap" in C | unverifiable; plain C cannot catch | Stock uses C++ try/catch (`Runtime.cpp:342-350,361-369`) | Small C++ file (`-fexceptions -fno-rtti`, `catch(...)`). The own personality treats any catch action as catch-all |
| 33 | `__emutls_get_address` in libgcc needs malloc | confirmed | `arm-none-eabi-nm libgcc.a`: emutls.o `U malloc` | — |
| 34 | General-dynamic TLS for non-object thread-locals, and it appears in practice | confirmed | `LlvmUtils.kt:217-230`; `IrToBitcode.kt:686-692`; `Throwable.kt:36-41` → `Lock.kt:16-27` (also needs `Kotlin_Any_hashCode`) | — |
| 35 | `clang -femulated-tls` takes effect on `-x ir` input | unverifiable | Local pipeline strips `thread_local` in text instead (now `toolchain/retarget.py --no-tls`) | Add `nm -u kotlin.o \| grep __emutls` to the E2 checks |
| 36 | libgcc v7e-m+fp/hard has no `__atomic_*` | confirmed | nm: 0 matches; only `__sync_synchronize*` | — |
| 37 | The C firmware's flash and SRAM budget; its linker script keeps `.init_array`, but its start-up code never runs it | confirmed | its size report, linker script and start-up code (not part of this repository) | — |
| 38 | The C firmware's timing limits; SysTick stops in Stop 1; hard-float VFP arguments and small enums in its objects | confirmed | its design notes and sources (not part of this repository); `readelf -A` on its objects | — |
| 39 | TypeInfo has 18 fields; `TF_HAS_FINALIZER = 1<<6`; tag bits; `kInitializingSingleton = 1`; `getTypeInfo` masks `~3` | confirmed | `RT/main/cpp/TypeInfo.h:45-56,92-140`; `Memory.h:30-139`; `Natives.cpp:110-112` | — |
| 40 | String `count_` includes 3 header units on ARM32; array size formula | confirmed | `KString.h:28-67`; `Runtime.kt:114-116`; `KObject.hpp:61-76` | — |
| 41 | FrameOverlay is 3 slots; GC scans `[3+parameters, count)`; slots zeroed; EnterFrame placement | confirmed | `Memory.h:272-277`; `RT/mm/cpp/ShadowStack.hpp:49-53`; `CodeGenerator.kt:609-611,1351-1359,1411-1418` | — |
| 42 | Signatures of `AddTLSRecord`/`LookupTLS`/`CallInit*`/InitNode; init order 0/1/2 | confirmed | `Memory.h:238-244`; `Runtime.h:17-32`; `IrToBitcode.kt:379-425,2348-2409`; `Runtime.cpp:55-61,102-108` | — |
| 43 | 24 eagerly imported functions; the processInMark pointers are mandatory | confirmed | `ContextUtils.kt:414-439`; `RTTIGenerator.kt:259-262,484-496` | — |
| 44 | Stock runtime is 25 modules, 1,618,416 B; 322 `@GCUnsafeCall`; every M3 symbol name exists | confirmed | `ls`; grep (322); each name found in `RT/main/kotlin` | — |
| 45 | Box caches are defined by the compiler; runtime `in*BoxCache` gates them | confirmed | `BK/Boxing.kt:150-185`; `RT/main/kotlin/kotlin/native/internal/Boxing.kt:11-40` | — |
| 46 | Escape analysis allows 64 KB of stack arrays; `-Xdisable-phases=EscapeAnalysis` works | confirmed | `EscapeAnalysis.kt:1650`; `LTO.kt:131-133` (returns an empty map when disabled) | — |
| 47 | `finally` lowering; `resumeWith` catches; `indirectbr` dispatch | confirmed | `NativeLoweringPhases.kt:273-277`; `ContinuationImpl.kt:21-50`; `IrToBitcode.kt` near 2290 | — |
| 48 | Each compile takes up to 5 min | refuted (much faster) | Local: a `-p static -opt` probe took about 21 s (from the time stamps of its argument file and its output) | — |
| 49 | E2 check `nm kotlin.o \| grep '$a'` finds ARM-state code | refuted (always 0) | `nm --help` ("--special-syms: include special symbols"); a GCC-built Cortex-M object: 0 mapping symbols by default, 26 with `--special-syms` | Use `nm --special-syms` or `readelf -s` |
| 50 | E2 check `objdump -d \| grep 'bl.*<EnterFrame>'` | unverifiable as written | Without `-r`, relocations in a `.o` do not show their target name | Use `objdump -dr` (`R_ARM_THM_CALL`) or `nm kotlin.o \| grep EnterFrame` |
| 51 | E2 expected output is `1 6820 / 2 1077936128 / 1 6875` | refuted | The M1 probe p1 prints 2 lines per step, and the planned QEMU start-up code steps twice | Expect 4 lines: `1 6820, 2 1077936128, 1 6875, 2 1077936128` |
| 52 | E2 `clang -S -emit-llvm -x ir compiler_interface.bc` (no `--target`) | minor flaw | Clang replaces the module triple with the host default and warns [I] | Pass the Cortex-M4 target (`--target=thumbv7em-none-eabihf`) |
| 53 | E4 differential runs as written | refuted | The device harness steps `main` twice, the mingw golden runs once. `@SymbolName` k_* would be unresolved on mingw | Step once for E4. Keep k_* calls out of the differential test sources |
| 54 | `clang -Os -x ir` gives size-optimised codegen | at risk [I] | No `optsize`/`minsize` attributes are added to IR input; the local `retarget.py` `--size` adds them | Measure, or accept the larger size |
| 55 | Matching F is enough for runtime functions to inline into Kotlin code | at risk [I] | `-ffreestanding` in the planned runtime CFLAGS adds `"no-builtins"`. LLVM's default target-library-info inline check needs equal no-builtin sets, which blocks non-`always_inline` inlining | Drop `-ffreestanding` from those CFLAGS, then confirm with the #50 check |
| 56 | Zephyr: throw aborted; cut in 1.9.20; removed in 2.0.0; STM32F407 | confirmed | archive `runtime/src/main/cpp/Exceptions.cpp:201-210`, `shared/.../ClangArgs.kt:333-337`. `gh api` compare (the commits are not in a shallow clone): aea8bac7d29 (2023-05-12) is in v1.9.20, not in v1.9.0; 0f05ffe111f is in v2.0.0, not in v1.9.23. `samples/zephyr/c_interop/platforms/stm32f4_disco.sh:20` (`-DSTM32F407xx`) | — |
| 57 | "JetBrains' own MCU target" | partly refuted (wording) | `d968fafec` "zephyr: first attempt" by a community contributor; `0de9b3a9b` LED blink by a JetBrains engineer | Say "begun by a community contributor, made to run on STM32F4 and maintained by JetBrains". "No size figures" stays unverifiable |
| 58 | Jar SHA-256 `7ded8eaa…928e` | confirmed | `sha256sum`; [PROVENANCE.txt](PROVENANCE.txt) | — |
| 59 | Stdlib eager initialisers do not allocate (M1 AllocInstance can be fatal) | unverifiable | Local E2 shows stdlib module initialisers exist (`MEASUREMENTS.md`: 878 B) | Keep the E1 gate |

## Changes the design must make

1. **Exports.** Mark `kmicro_init` and `kmicro_step` (and any global shared between the bitcode and km_sys.c, such as the saved UCB) `__attribute__((used, retain))`, not `used` alone. Add an `nm` check that they are global `T` symbols.
2. **`__cxa_end_cleanup`, not `_Unwind_Resume`.** ARM EHABI lowers `resume` to `__cxa_end_cleanup`, and `Konan_start` already needs it in M1. Define it outside the LTO bitcode: a fatal stub in M1-M2, then the naked tail-call version with personality-side UCB saving in M3 (as the local runtime already did). Keep every other symbol that only appears at codegen (`__emutls_get_address`, `__atomic_*_8`, `__aeabi_unwind_cpp_pr*`) out of the bitcode as well.
3. **Build the runtime with `-fexceptions`** and put `nothrow` explicitly on non-throwing functions. A `-fno-exceptions` `runtime.bc` makes array-bounds, negative-size and failed-initialiser exceptions uncatchable. Write the M3 `CallInit*` failure wrapping as a small C++ `catch(...)` file, or in Kotlin.
4. **Correct the EH rationale.** `-Xllvm-lto-passes` can run `lower-invoke` inside the unmodified compiler. Keep option (b), but record this as a fallback and size lever.
5. **Fix the E2 and E4 checks:**
   - mapping symbols via `nm --special-syms`;
   - call checks via `objdump -dr` or `nm`;
   - p1 expects 4 lines;
   - one step per run for E4, and no k_* calls in host-diffed tests;
   - the Cortex-M4 target on the `compiler_interface.bc` dump;
   - add `nm -u | grep __emutls` and `readelf -S | grep init_array`.
6. **Drop `-ffreestanding`** from the runtime CFLAGS (inlining blocked by `"no-builtins"`), or verify inlining explicitly.
7. **Runtime globals.** Declare the compiler-defined overridable and constant globals `extern` only.
8. **Build on the local work instead of redoing it:**
   - the measurements (MEASUREMENTS.md): data layout, F, stock size 184,226 B, symbol lists;
   - the local runtime (eh.c, mm.c, strings.c, atomic64.c…);
   - the local build scripts and the passing differential tests;
   - QEMU `b-l475e-iot01a`, which is the same STM32L4 family.

   E0.1, most of E1 and the E1.6 baseline already exist. The design should say whether D2-D4 (the program build against a copied distribution) replaces the working pipeline (`-p static` + `@CName` + text retarget).
9. **Wording:** the Zephyr origin is community-started (#57), and add a note that `linux_arm32_hfp` is deprecated.

## What became of these changes

| Change | Outcome |
|---|---|
| 1. Exports | Moot: there is no `kmicro_step`. C calls Kotlin functions directly, and they are part of the same LTO link, so the linker keeps every one that C calls (design-plan.md, D6). |
| 2. `__cxa_end_cleanup` | Done: [runtime/eh.c](../../runtime/eh.c) defines it as a naked tail call into `_Unwind_Resume`. |
| 3. `-fexceptions` | Done: the runtime is compiled with `-fexceptions -funwind-tables`, and failed initialisers are caught in C++ ([runtime/init_cxx.cpp](../../runtime/init_cxx.cpp)). |
| 4. EH rationale | Recorded here and in design-plan.md §4. kmicro keeps real exceptions (option b). |
| 5. E2 and E4 checks | Moot for E2: its pipeline was not built. E4 became [tools/difftest.py](../../tools/difftest.py). |
| 6. `-ffreestanding` | Done: the runtime is compiled without it. |
| 7. Runtime globals | Done: the runtime declares the compiler's globals `extern` (for example `Kotlin_latin1Strings` in runtime/strings.c). |
| 8. Local work | Done: D2-D4 were dropped in favour of the working pipeline, which became toolchain/kn.py. |
| 9. Wording | Done in design-plan.md and R_zephyr.md. |

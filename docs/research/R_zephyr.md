# Kotlin/Native on Zephyr and STM32F4 (2017-2020): how the target worked, and what carries over to a bare-metal port

> **Status.** kmicro took the reusable ideas of §5: the Kotlin program as one object that is linked into the
> firmware, a small porting layer (the board provides functions such as `kmicro_puts` and `kmicro_exit`), and the
> toolchain lessons. Three of §5's conclusions came out differently: the start-up code runs `.init_array` instead of
> calling `_Konan_constructors` ([how-it-works.md](../how-it-works.md)); thread-locals become ordinary globals
> (`toolchain/retarget.py --no-tls`), so neither `__emutls_get_address` nor `__aeabi_read_tp` is needed; and
> exceptions run on kmicro's own personality routine over libgcc's unwinder (R_eh.md, option (b)).

Path prefixes:
- `A/` = the archived github.com/JetBrains/kotlin-native repository at tag v1.3.70 (commit 9e63309cd; full history)
- `M/` = the github.com/JetBrains/kotlin repository at tag v2.4.21 (a shallow clone with one commit, so its history
  comes from GitHub)
- `D/` = the Kotlin/Native 2.4.21 prebuilt distribution for Windows (`kotlin-native-prebuilt-windows-x86_64-2.4.21`)
- `kotlin@sha` = a JetBrains/kotlin commit read with `gh api`. `KN#n` = a JetBrains/kotlin-native issue or PR. `KT-n` = a YouTrack issue read through its REST API.

## 0. Key findings
- **Who did it.** A community contributor started it (PR KN#1062, commit d968fafec) and later wrote: "I'm not JetBrains, but it was me that proposed Zephyr/STM32" (KN#2483, 2018-12-20). JetBrains engineers made the boards configurable, got the LED blink working on STM32F4 (0de9b3a9b) and maintained the target afterwards. VERIFIED.
- **It was not bare metal.** The `zephyr_<board>` target produced one relocatable ELF object, `program.o`. That object held the Kotlin code, the stdlib, the C++ runtime, the launcher and the cinterop C stubs, all merged into one LLVM module and joined with `ld -r`. Zephyr's CMake then linked it as an ordinary object, on top of newlib and libsupc++. VERIFIED.
- **Runtime.** It was the normal C++ runtime, switched by about 10 `KONAN_*` macros:
  - no threads;
  - no C++ exceptions: any Kotlin `throw` printed the exception and aborted;
  - no math library: every `kotlin.math` call aborted;
  - time was always 0;
  - memory came from newlib's `calloc`. VERIFIED.
- **It stayed experimental.**
  - Its author called it "possible in theory, but almost unusable in practice" and said a compile took almost 5 minutes (KN#2447).
  - On STM32F4 it crashed with a "USAGE FAULT: No coprocessor instructions" (KN#2447).
  - On a QEMU Cortex-M3 it printed "Hello Kotlin!" and then hit a cycle-collector assert (KN#2485).
  - No flash or RAM figure was ever published (section 4.4). VERIFIED quotes; "no figures" is INFERRED from the places searched (section 4).
- **Why it ended.**
  - From Kotlin/Native 1.2.0 it was "experimental": you had to rebuild the whole distribution to get it.
  - JetBrains (2020-12-18, KN#2483): "requires to recompile the distribution, is not supported in other parts of Kotlin (e.g. Gradle plugin) and is not really flexible. So this is not what we are working on right now."
  - In 1.9.20 compiling for it became an error. That release removed the old memory manager, and the new one needs threads (kotlin@aea8bac7d29).
  - The target code was removed in 2.0.0 and the last leftovers in 2.2.20. VERIFIED.
- **What carries over.**
  - The idea of a small porting layer.
  - The link model: one optimized object, no OS loader.
  - Calling `_Konan_constructors` explicitly.
  - Toolchain lessons: short enums, float ABI and FPU enable, TLS producing `__aeabi_read_tp`, and the C++ exception helpers from libsupc++.
- **What does not.** The old memory manager and every `KONAN_NO_*` switch are gone. The 2.4.21 runtime assumes pthreads, C++ exceptions and thread-local storage.

## 1. Timeline

| Date | Ref (first release) | Event |
|---|---|---|
| 2017-11-22 | KN#1062 (closed) | Work-in-progress PR "Zephyr target" for Cortex-M |
| 2017-12-17 | d968fafec (v0.6) | "zephyr: first attempt". Target `zephyr`, board qemu_cortex_m3, Zephyr v1.10.0, gcc-arm 6-2017q2, LLVM 5. `entrySelector = --defsym main=Konan_main`. ZephyrLinker runs `ld -r --gc-sections --entry main`. Output suffix is "o". Sample is `println("Hello World!")`. The first link failed on `__aeabi_memclr4` and `__aeabi_read_tp` (thread-local storage; KN#1062, 2017-12-17) |
| 2018-01-16 | 9789420ed | Boards become configurable: one `zephyr_<board>` target per file in `konan/platforms/zephyr/` (KN#1298) |
| 2018-02-16 | 0de9b3a9b (v0.6.1) | LED blink on stm32f4_disco through cinterop. Link step: `llvm-link` → `opt -O3 -internalize -globaldce` → `llc -function-sections -data-sections`. Links libsupc++.a. Removes hand-written `__aeabi_memset`/`__aeabi_memclr` |
| 2018-02-22 / 02-26 | feaf220f5 / ac6c3443e / d285a4515 | cinterop string `#define`s; `-fshort-enums`; empty.c removed |
| 2018-02-28 | 510ee3550, 8d7d0907f | Builds on a Windows host |
| 2018-03-28 | cca928009 | Fix WASM32/Zephyr build (Memory.cpp) |
| 2018-12-21 / 12-24 | 8d00a1ebc (KN#2481), 7de47bb1d (KN#2490) | Sample updated for Zephyr 1.13.99; `update_zephyr.sh` |
| 2019-02-19 | bf7040a11 (KN#2681, v1.2.0) | "Support experimental targets": Zephyr is only built with `-Porg.jetbrains.kotlin.native.experimentalTargets` (A/README.md:29, A/RELEASE_NOTES.md:44-47) |
| 2019-10-01 | eb0e6a8f1 (v1.3.70, not in 1.3.60) | `targetCpu`/`targetAbi` properties; LLVM 8; Zephyr now goes through the full LLVM pipeline at size level 2 (before, only internalize + GlobalDCE); `clangFlags = -Os`; `entrySelector` dropped in favour of a `main` alias |
| 2019-10-08 | 767515cdc | Sysroot `target-sysroot-4-embedded` (size_t fix) |
| 2020-10-12 | b7470495f | Macros moved from ClangArgs.kt to `runtimeDefinitions.zephyr_stm32f4_disco` |
| 2020-10-27 | f624800b8 | Repository moved into JetBrains/kotlin/kotlin-native |
| 2020-12-18 | KN#2483 comment | Stated reason (quoted in section 0); use cases redirected to KT-43974 (open in October 2026) |
| 2021-07-01 | kotlin@c286a9d8c6f | Adds `KONAN_NO_BACKTRACE` |
| 2022-08-09 | kotlin@de1dd47ab10 | `runtimeDefinitions` removed; macros now derived from target traits (for example `NO_THREADS` when the target lacks threads) |
| 2022-08-26 | kotlin@71b8089f337 | Zephyr sample deleted ("remove samples that are not used in tests") |
| until 2023-05 | lines removed by kotlin@aea8bac7d29 | On a target without threads the new memory manager fell back to the old one with the warning "New MM requires threads, which are not supported on a deprecated target" |
| 2023-05-12 | kotlin@aea8bac7d29 (in v1.9.20) | "Do not compile for deprecated targets and legacy MM". `target is KonanTarget.ZEPHYR` now reports the error "target … is no longer available"; the old memory manager is an error; the compiler requires threads |
| 2024-01-16 | kotlin@0f05ffe111f, 85bcc8443d8, 29e90d70c6a, 4957d99fd6f, b19ad2505cf (in v2.0.0; KT-64517) | ZEPHYR removed from KonanTarget and Family (only error stubs left). `threadsAreAllowed`, `tlsMode` and the box-cache range made constant. Commit text: "ZEPHYR was the first and the last experimental KonanTarget" |
| 2025-05-01 | kotlin@b2b147267f7, e77d9c9f17f, f5d4d10fdb1, 7dc64f62cf2 (in v2.2.20; KT-59008) | Platform file, ZephyrConfigurables, update_zephyr.sh and the error stubs removed |

Stated reasons, all VERIFIED:
- KN#2483: the 2020 quote above. Also JetBrains (2018-12-21): "Kotlin/Native for embedded targets is generally an area where we expect community will provide us with feedback and contributions."
- KT-64517: "Targets like `ZEPHYR` or `wasm32` are not supported on the backend for a while… compiler error since 1.9.20."
- Technical root cause: aea8bac7d29 removed the old memory manager, and the new one needs threads.

## 2. The target definition (v1.3.70)

### 2.1 Properties
- **Board file** `A/konan/platforms/zephyr/stm32f4_disco`. VERIFIED.
  - :20 `quadruple = armv7m-none-eabi`
  - :21 `targetSysRoot = target-sysroot-4-embedded`
  - :23 `boardSpecificClangFlags = -mthumb`
  - :24 `targetCpu = cortex-m4`
  - :25 `targetAbi = aapcs`
  - :26 `clangFlags = -Os` (no target suffix)
  - :28-47 toolchain gcc-arm-none-eabi-7-2017-q4-major for linux/mac/win32, plus clang-llvm-8.0.0 and libffi.
  - There is no float ABI or FPU key anywhere.
- **Main properties file.** `A/konan/konan.properties` has no Zephyr keys (grep). The board file was merged in from `konan/platforms/<genericName>/` (Distribution.kt diff in bf7040a11). VERIFIED.
- **How the target appeared.** HostManager created one target per board file: `zephyrSubtargets = distribution.availableSubTarget("zephyr").map { ZEPHYR(it) }`, enabled only when experimental targets were on (kotlin@7a19558d541, HostManager.kt). VERIFIED.
  - Definition: `class ZEPHYR(val subName: String, val genericName: String = "zephyr") : KonanTarget("${genericName}_$subName", Family.ZEPHYR, Architecture.ARM32)`.
  - `Family.ZEPHYR("o","lib","a","lib","a")`, so a PROGRAM build produces `program.o` (lines removed in kotlin@0f05ffe111f). VERIFIED.
- **Key lookup.** A target key falls back to the key without a suffix (`M@HEAD:compiler/util-io/src/org/jetbrains/kotlin/io/PropertyFileUtils.kt:46-47,143`). That makes the unsuffixed `clangFlags = -Os` apply to Zephyr. VERIFIED for 2.4.21; INFERRED to be the same in 2019.
- **WASM32 for comparison:** `A/konan/konan.properties:681-688`.

### 2.2 Clang flags for the runtime and C stubs (`A/shared/src/main/kotlin/org/jetbrains/kotlin/konan/target/`)
All VERIFIED.
- `ClangArgs.kt:138-154` (Zephyr): `-target armv7m-none-eabi -fno-rtti -fno-exceptions -fno-asynchronous-unwind-tables -fno-pie -fno-pic -fshort-enums -nostdinc`, then `-isystem` for gcc 7.2.1 `include` and `include-fixed`, then the sysroot's `include/libcxx` and `include/libc`.
- `ConfigurablesExtensions.kt:3-11` appends `-mcpu=cortex-m4 -mabi=aapcs -mthumb`.
- `ClangArgs.kt:333-343` sets the Zephyr macros (section 3); `ClangArgs.kt:322-331` does the same for WASM32.
- `Configurables.kt:89-93` defines `ZephyrConfigurables` (boardSpecificClangFlags, targetCpu, targetAbi).
- The runtime was built per target into LLVM bitcode modules: runtime, launcher, debug, release, strict, relaxed, profileRuntime, objc, exceptionsSupport (`A/runtime/build.gradle:14-86`).

### 2.3 Compiler special cases (`A/backend.native/compiler/ir/backend.native/src/org/jetbrains/kotlin/backend/konan/`)
- **Threads off.** `KonanConfig.kt:69-70` sets `threadsAreAllowed = false` for WASM32 and ZEPHYR (`indirectBranchesAreAllowed` is false only for WASM32). Where it matters (VERIFIED):
  - `llvm/IrToBitcode.kt:62-67`: `@ThreadLocal` objects are not put in thread-local storage.
  - `IrToBitcode.kt:1562,1603`: no main-thread checks.
  - `llvm/CodeGenerator.kt:946`: `initInstance` is used instead of `initSharedInstance`.
- **No thread-local storage.** `llvm/ContextUtils.kt:492-498` sets `tlsMode = LLVMNotThreadLocal` for WASM32 and ZEPHYR. VERIFIED. This is what removes the `__aeabi_read_tp` link errors (INFERRED).
- **Box caches off.** `Boxing.kt:196-210` disables them for ZEPHYR; the comment at :198 says "Memory usage is around 20kb". VERIFIED.
- **Optimization** (`OptimizationPipeline.kt`):
  - :76-79 the CPU comes from `targetCpu`;
  - :82-86 the CPU feature string is empty for Zephyr;
  - :104-111 size level is AGGRESSIVE (= 2, defined at :138-142) for ZEPHYR and WASM32;
  - :156-186 pass-manager builder, then internalize, GlobalDCE and the LTO pass manager. VERIFIED.
- **Frame pointer.** `llvm/LlvmAttributes.kt:51`: not forced. VERIFIED.
- **Exceptions are not special-cased.** VERIFIED.
  - The personality is `__gxx_personality_v0` (`ContextUtils.kt:509-513`).
  - `_ZSt9terminatev`, `__cxa_begin_catch` and `__cxa_end_catch` are imported (:515-535).
  - Calls to functions not marked nounwind are emitted as `invoke` (`CodeGenerator.kt:380-406`), with landing pads that use the personality (:613-618).
- **Object emission.** `BitcodeCompiler.kt:64-86` runs the host `clang++` with `clangFlags` + `-triple <quadruple>` + `constructClangCC1Args()`. That function (`ConfigurablesExtensions.kt:14-23`) adds `-cc1 -emit-obj -disable-llvm-optzns -x ir -fdata-sections -ffunction-sections`, the ABI/CPU pair and `-mthumb`.
  - As written at v1.3.70 (VERIFIED):
    - Lines :16-21 swap the values, producing `-target-abi cortex-m4 -target-cpu aapcs`.
    - The unsuffixed `-Os` ends up ahead of `-cc1`.
    - `-mthumb` is a driver flag, not a `-cc1` flag.
  - Effect (INFERRED, not run): stock clang should reject this command line. The v1.3.70 snapshot is a design reference, not a recipe known to build.
- **Linking the module.** `CompilerOutput.kt:67-79` links the runtime bitcode, launcher, stdlib and cinterop stubs into one module, and :82-90 adds the LLVM alias `main` → `Konan_main`. `CStubsManager.kt:20-46` compiles cinterop C stubs to target bitcode (`-O2 -emit-llvm`). VERIFIED.
- **Linker** (`A/shared/.../Linker.kt:465-488`, ZephyrLinker): `$targetToolchain/bin/ld -r --gc-sections --entry main -o <out> objects libraries linkerArgs` (:481). It accepts only EXECUTABLE output (:479) and drops static libraries (:472). VERIFIED.

### 2.4 What came out and how Zephyr linked it
- **Output:** one relocatable `program.o`. VERIFIED. It left these symbols for the app to provide: newlib, the libsupc++ exception helpers, the Zephyr API and `Konan_exit` (INFERRED). That the sample links libsupc++ is VERIFIED below.
- **Zephyr side** (`A/samples/zephyr/`):
  - `CMakeLists.txt:6-10` imports and links `$GNUARMEMB_TOOLCHAIN_PATH/arm-none-eabi/lib/thumb/libsupc++.a`;
  - :12 sets `LINKER_LANGUAGE C`;
  - :14-23 copies `build/kotlin/program.o` and adds it as an external object;
  - `prj.conf:1-5`: `CONFIG_CPLUSPLUS=n`, `CONFIG_PRINTK=y`, `CONFIG_BOOT_BANNER=y`, `CONFIG_BUILD_OUTPUT_BIN=y`, `CONFIG_NEWLIB_LIBC=y`. VERIFIED.
- **Boot path** (`A/runtime/src/launcher/cpp/launcher.cpp`). VERIFIED:
  1. Zephyr calls `main` (an alias of `Konan_main(argc, argv)`, :63-65).
  2. `Init_and_run_start` (:48-61) calls `_Konan_constructors()` because of `KONAN_NO_CTORS_SECTION` (:49-52). The compiler makes `_Konan_constructors` external for programs (`IrToBitcode.kt:2489-2511`).
  3. Then `Kotlin_initRuntimeIfNeeded`, then `Konan_run_start` → `setupArgs(argc, argv)` (:27-37), then `Konan_start`, then the user's `main`.
- **Hazard.** Zephyr 1.x declares `void main(void)`, so `argc`/`argv` are whatever is left in r0/r1. `setupArgs` then allocates `argc-1` slots and reads `argv`. INFERRED: undefined behaviour that happened to work.

## 3. Runtime configuration

### 3.1 Macro by macro (`A/runtime/src/main/cpp/` unless noted). Effects are VERIFIED at the cited lines.

| Macro | ZEPHYR | WASM32 | Effect |
|---|---|---|---|
| KONAN_ZEPHYR | yes | – | Porting.cpp:38-45 declares `Konan_abort`, `Konan_exit` and newlib's `strnlen`; :78-79 `consoleReadUtf8` returns 0; :163 `onThreadExit` does nothing; :185-188 `exit` calls `Konan_exit`; :245-249 `Konan_date_now` = 0; :358-417 libc++ helper stubs (`__throw_length_error` → `Konan_abort`, a `__next_prime` table, `__assert_fail`, `__errno_location`, `pow` via `__builtin_pow`); :468-472 `Konan_abort` is `while(1){}`. Types.h:22-25 maps `assert` to `abort()`. Runtime.cpp:214-256 has no Zephyr case, so OS family = 0 and CPU arch = 0 (`KONAN_ARM32` is not set either) |
| KONAN_WASM | – | yes | JS launcher and interop, ReturnSlot, math through JS; dlmalloc `moreCore` through wasm `memory.grow` (Porting.cpp:291-341); its own `memcpy` etc. (:419-466) |
| KONAN_NO_THREADS | yes | yes | Common.h:29-33 `THREAD_LOCAL_VARIABLE` is empty; Atomic.h:6-78 atomics become plain operations and `synchronize()` does nothing; Memory.h:128-185 non-atomic reference counts; Memory.cpp:1889-1907, 1992-2019, 2622-2640 no compare-and-swap or spin locks; Runtime.cpp:57-67; Porting.cpp:25-27 (no pthread.h) and :118-178; Weak.cpp:32,76,87; Worker.cpp:17-19 and 583-641 (Worker calls throw WorkerUnsupported, which aborts) |
| KONAN_NO_EXCEPTIONS | yes | yes | Exceptions.cpp:23-25 no backtrace; `ThrowException` (Exceptions.cpp:201-210) prints the exception, then `RuntimeCheck(false,"Exceptions unsupported")`, then `konan::abort()` (KAssert.cpp:28), then `::abort()`; Memory.cpp:1977-1979, 2003-2006, 2033-2039 object init without try/catch; Porting.h:85-93 `TRY_CATCH` without `try`; utf8.h:34-36 no checked UTF-8; A/runtime/src/exceptions_support/cpp/ExceptionsSupport.cpp:5-13 no RTTI reference |
| KONAN_NO_FFI | yes | yes | Not referenced anywhere in A/runtime/src (grep), so it did nothing at 1.3.70. VERIFIED absence |
| KONAN_NO_MATH | yes | – | KotlinMath.cpp:452-564: every `Kotlin_math_*` throws NotImplementedError, which aborts |
| KONAN_INTERNAL_DLMALLOC | – | yes | Porting.cpp:225-241 `dlcalloc`/`dlfree`; dlmalloc/malloc.cpp:524-528. On Zephyr, newlib's `::calloc`/`::free` are used |
| KONAN_INTERNAL_SNPRINTF | yes | yes | Porting.cpp:102-107 `rpl_vsnprintf` (snprintf/snprintf.cpp:166-2115), used by `consolePrintf` (1 KB stack buffer, :109-116) and `konan::snprintf` (:212-218) |
| KONAN_INTERNAL_NOW | yes | yes | Porting.cpp:243-266 time through `Konan_date_now`: always 0 on Zephyr, JS `Date` on WASM |
| KONAN_NO_MEMMEM | yes | yes | Porting.cpp:198-209 simple loop |
| KONAN_NO_CTORS_SECTION | yes | yes | launcher.cpp:49-52 calls `_Konan_constructors` explicitly |
| KONAN_NO_UNALIGNED_ACCESS | yes | – | Arrays.cpp:180-441 `ByteArray` get/set byte by byte; Runtime.cpp:198-204 reports no unaligned access |
| KONAN_NO_64BIT_ATOMIC | – | – | Not set. Atomic.cpp:98-150 has a spin-lock fallback; not needed because `NO_THREADS` already makes `compareAndSwap` plain (Atomic.h:15-26) |
| KONAN_CORE_SYMBOLICATION | – | – | Apple only (debug/cpp/SourceInfo.cpp:19-126; ClangArgs.kt:217,246,261,281) |
| KONAN_NO_DEBUG_API | – | – | No target sets it in ClangArgs.kt (KDebug.cpp:27) |
| KONAN_NO_BACKTRACE | added 2021 | added 2021 | kotlin@c286a9d8c6f |

### 3.2 Exceptions when disabled
- **On throw:** print, then abort. `catch` and `finally` blocks never run. Every implicit throw (null pointer, bounds, arithmetic, cast, `require`/`check`, math NotImplementedError, WorkerUnsupported) ends in abort. VERIFIED code path.
- **What abort did:** `konan::abort` calls newlib `::abort` (Porting.cpp:181-183), which goes to Zephyr's exit hook (INFERRED). Only the libc++ stubs and asserts use the `Konan_abort` spin loop. VERIFIED.
- **Did codegen still emit invoke/landingpad?** Yes, unchanged, with `__gxx_personality_v0` (section 2.3). VERIFIED.
  - The runtime was compiled with `-fno-exceptions`, so runtime functions count as nounwind and are called with a plain `call` (CodeGenerator.kt:380-382, plus clang behaviour). INFERRED.
  - LLVM's link-time passes can delete landing pads once `ThrowException` cannot unwind. Whatever is left needs `__gxx_personality_v0` and the `__cxa_*` helpers, which is why libsupc++.a was linked. The reason is INFERRED; the link itself is VERIFIED.

### 3.3 Memory
- **Model.** The old "strict" memory manager: a reference count in each container header (Memory.h:128-185), stack-reference decrements deferred into a `toRelease` list, and Bacon's trial-deletion cycle collector (Memory.cpp:33-36, `USE_GC 1`). VERIFIED.
- **Thresholds** (Memory.cpp:72-88): `kGcThreshold` 8×1024 entries, `kMaxToFreeSize` 8×1024, `kMaxGcAllocThreshold` 8 MB. VERIFIED.
- **Triggers.** VERIFIED:
  - the `toRelease` list reaches the threshold (Memory.cpp:1115-1118, 1156-1159);
  - or enough bytes were allocated and at least 10 ms passed since the last collection, measured with `getTimeMicros` (Memory.cpp:1909-1916).
- **On Zephyr** (INFERRED): time is stuck at 0, so the time-based trigger never fires and only the count trigger works. 8192 pointers is 32 KB of RAM before the first collection, half the SRAM of a 64 KB part.
- **Allocation:** `konanAllocMemory` → `konan::calloc` → newlib `calloc` (Alloc.h:28-34, Porting.cpp:224-241). VERIFIED.
- **Other:**
  - No thread-local storage: `memoryState` is a plain global (VERIFIED).
  - Box caches are off (VERIFIED).
  - Object freezing still ran (Memory.cpp:1995-2006, VERIFIED).
  - The runtime still used libc++ containers (`deque`, `map`, `set`, `string`: Types.h:27-30), header-only from the sysroot (VERIFIED).
- **Observed failure** (KN#2485, 2018-12-21, QEMU Cortex-M3): "Hello Kotlin!" then "Memory.cpp:615: runtime assert: cycle collector shall only work with single object containers". VERIFIED.

### 3.4 Porting layer (Porting.h:25-95, Porting.cpp)
All VERIFIED unless marked.
- **Console.**
  - `consoleInit` does nothing.
  - `consoleWriteUtf8` and `consoleErrorUtf8` call `::write(STDOUT/STDERR)` (:59-75). That goes to newlib and then Zephyr's console hook (INFERRED).
  - `consoleReadUtf8` returns 0 (:77-79).
  - `consolePrintf` formats into a 1 KB buffer.
- **Process.**
  - `abort` → `::abort` (:181-183).
  - `exit` → `Konan_exit` (:185-188). Nothing in the Zephyr runtime defines `Konan_exit`, so the app must provide it if `exitProcess` is reachable (INFERRED).
  - `onThreadExit` does nothing.
- **Memory:** `calloc`/`free` from newlib.
- **Time:** `getTimeMillis`, `getTimeMicros`, `getTimeNanos` all return 0.
- **Strings:** `memmem` (simple loop), `snprintf`, and `strnlen` from newlib.
- **Also needed from newlib/libgcc:** `memcpy`, `memset` and the `__aeabi_mem*` helpers. The hand-written versions were removed in 0de9b3a9b.

## 4. The sample
1. **Kotlin code** (`A/samples/zephyr/src/main.kt:6-28`), VERIFIED:
   ```kotlin
   val dev = device_get_binding(LED0_GPIO_CONTROLLER)
   gpio_pin_configure(dev, LED0_GPIO_PIN.convert(), GPIO_DIR_OUT)
   while (true) { gpio_pin_write(dev, led.convert(), if (toggler) 1U else 0U); toggler = !toggler; k_sleep(1000 * value) }
   ```
2. **C interop.**
   - `.def` (`c_interop/platforms/stm32f4_disco.def:8-9`): headers `autoconf.h zephyr.h generated_dts_board.h device.h gpio.h`; options `-DKERNEL -DUSE_FULL_LL_DRIVER -DUSE_HAL_DRIVER -D_FORTIFY_SOURCE=2 -D__ZEPHYR__=1 -ffreestanding -std=c99 -nostdinc`.
   - `stm32f4_disco.sh:18-36` passes `-Xclang -DSTM32F407xx` and the Zephyr include paths, including headers generated by a first `make zephyr` (build.sh:42-44). Package `platform.zephyr.stm32f4_disco`. VERIFIED.
   - Static-inline and syscall wrappers were callable because the C stubs are compiled into target bitcode (CStubsManager.kt:20-46). Mechanism VERIFIED; that these particular functions went through stubs is INFERRED.
3. **Build** (build.sh:52-56): `konanc main.kt -target zephyr_stm32f4_disco -r … -l stm32f4_disco -opt -g -o build/kotlin/program`, then the CMake link above. Flashing: `st-flash --reset write build/zephyr/zephyr.bin 0x08000000` (:60-70). The Gradle plugin never supported this target (its author, KN#2447). VERIFIED.
4. **Resources and limitations.**
   - **No flash or RAM numbers anywhere.** Searched: the sample, RELEASE_NOTES, the archived README and KN#1062/1324/1385/1418/2447/2449/2481/2483/2485/2490. INFERRED: none were published.
   - The chip was STM32F407 (`-DSTM32F407xx`, VERIFIED). That part has 1 MB flash and 192 KB RAM, about 4× the flash and 3× the RAM of the STM32L431 (INFERRED from the part number).
   - **Usability:** about 5-minute compiles and "almost unusable" (its author, KN#2447). VERIFIED.
   - **FPU crash.** STM32F4 hit "USAGE FAULT: No coprocessor instructions" (a user, KN#2447). VERIFIED.
     - Cause (INFERRED): the code was built for cortex-m4 with an empty feature string on a soft-float "eabi" triple. That emits FPU instructions while Zephyr never enabled the FPU (CPACR).
   - **Cycle-collector assert** on Cortex-M3 (KN#2485). VERIFIED.
   - **Only one board ever merged.** nucleo_f412zg (KN#1418) and the QEMU M3 sample (KN#2485) were closed.
   - **Missing pieces:** no math, exceptions, time, threads or stdin; garbage `argc`; `Konan_exit` undefined.

## 5. Reusable today vs obsolete (2.4.21 paths under `M/kotlin-native/` unless noted)

### Reusable (ideas and mechanisms)
1. **One optimized object, linked by us.**
   - Then: `ld -r` produced `program.o`.
   - Now: `-produce bitcode` is gone ("Bitcode output kind is obsolete.", `backend.native/compiler/ir/backend.native/src/org/jetbrains/kotlin/backend/konan/driver/NativeCompilerDriver.kt:45`). VERIFIED.
   - The unmodified compiler can still write out the Kotlin module: `-Xsave-llvm-ir-after=Codegen -Xsave-llvm-ir-directory=<dir>` (HACKING.md:344; `driver/utilities/LlvmPassesUtilities.kt:33-56`; Codegen phase at `driver/phases/BitcodeGeneration.kt:62-65`, before `LinkBitcodeDependencies` at `driver/phases/Bitcode.kt:147`). VERIFIED that the hook exists.
   - Plan: take that `.ll`, retarget it with our own LLVM, and link it next to the C firmware. INFERRED. This is what
     kmicro does now ([toolchain/kn.py](../../toolchain/kn.py)), with clang and ld.lld.
2. **Porting layer.**
   - Now: `runtime/src/main/cpp/Porting.h:27-53`: console (`consoleInit`, `consolePrintf`, `consoleErrorf`, `consoleWriteUtf8`, `consoleErrorUtf8`, `consoleReadUtf8`, `consoleFlush`), `onThreadExit`, `isOnThreadExitNotSetOrAlreadyStarted`, `currentThreadId`, `getTime*`, `getSystemTimeNanos`, `isLittleEndian`. VERIFIED.
   - `calloc`, `free`, `abort`, `exit`, `memmem`, `snprintf` and `strnlen` were removed from that API. VERIFIED.
   - Porting.cpp:26 includes pthread.h unconditionally, :255-256 has `#error` for an unknown OS, and :261-280 uses `std::chrono`. VERIFIED.
   - Plan: rewrite this API over the board's C functions (console, clock). INFERRED.
3. **Explicit constructor call.**
   - The compiler still emits `_Konan_constructors` (external for programs) plus `llvm.global_ctors` (`backend.native/.../llvm/IrToBitcode.kt:2817-2837`). VERIFIED.
   - The current launcher no longer calls it (`runtime/src/launcher/cpp/launcher.cpp:57-77`). VERIFIED.
   - Bare-metal start-up code often keeps `.init_array` in the linker script but never runs it; the firmware this was planned for was such a case.
   - So the Kotlin entry point must call `_Konan_constructors`, as the Zephyr port did. INFERRED.
4. **Toolchain lessons** (VERIFIED facts, INFERRED application):
   - **Enum size.** Use `-fshort-enums` to match arm-none-eabi gcc (ac6c3443e; ld warning in KN#1062).
   - **Thread-local storage.** It produces `__aeabi_read_tp` (KN#1062). Today the compiler emits general-dynamic TLS (`backend.native/.../llvm/LlvmUtils.kt:225`), and android_arm32 compiles with `-femulated-tls` (`konan/konan.properties:626`). We must provide `__emutls_get_address` or `__aeabi_read_tp`.
   - **Float ABI.** C firmware for a Cortex-M4F is built with `-mfpu=fpv4-sp-d16 -mfloat-abi=hard` and enables the FPU at start-up. Kotlin objects must therefore use hard-float EABI. Zephyr never set a float ABI and hit the coprocessor fault.
   - **CPU attributes in the bitcode.** Every function carries the source target's `target-cpu`/`target-features` attributes (`backend.native/.../llvm/LlvmAttributes.kt:30-33`). android_arm32 is `arm7tdmi`, `+armv4t`, `-thumb-mode`, no FPU registers (`konan/konan.properties:623-627`). These must be rewritten when retargeting.
   - **Personality** is still `__gxx_personality_v0` (`backend.native/.../llvm/ContextUtils.kt:596-598`). Either make `ThrowException` cannot-unwind plus abort, or link libsupc++ and libgcc ARM unwinding.
5. **Size.** Zephyr used size level 2. Today `-Xbinary=smallBinary=true` gives `Oz` (`backend.native/.../NativeSecondStageCompilationConfig.kt:104-113`; `OptimizationPipeline.kt:167-170,230-233`). VERIFIED. Box caches are now always the default range (`Boxing.kt:173,211`; kotlin@29e90d70c6a). VERIFIED.
6. **Platform macros that still exist** (VERIFIED):
   - `KONAN_NO_UNALIGNED_ACCESS`: `runtime/src/main/cpp/Arrays.cpp:205-460`, `Runtime.cpp:204`
   - `KONAN_NO_64BIT_ATOMIC`: `runtime/src/main/cpp/std_support/Atomic.hpp:21`
   - `KONAN_FORBID_BUILTIN_MUL_OVERFLOW`: `runtime/src/main/cpp/Saturating.hpp:162`
   - `KONAN_NO_DEBUG_API`: `runtime/src/main/cpp/KDebug.h:25,98`, `runtime/src/debug/cpp/KDebug.cpp:28,329`
   - `KONAN_ARM32`: `runtime/src/main/cpp/Runtime.cpp:241`, `StackTrace.cpp:248`
   - `KONAN_NEED_ASINH_ACOSH`: `runtime/src/main/cpp/KotlinMath.cpp:26-197`
   - They are derived from target traits in `M@HEAD:native/utils/src/org/jetbrains/kotlin/konan/target/ClangArgs.kt:38-70`.
7. **Runtime surface we must supply** (VERIFIED):
   - The runtime is now split into modules chosen by binary options (`backend.native/.../CompilerOutput.kt:131-187`; `llvm/runtime/RuntimeModule.kt`): no-op GC, single-thread mark-and-sweep, manual GC scheduler, std allocator, and others.
   - Prebuilt android_arm32 copies of these modules are in `D/konan/targets/android_arm32/native/` (ls).
   - `-Xruntime=` replaces only `compiler_interface.bc` (`llvm/runtime/RuntimeModulesConfig.kt:22-29`). Every other module is read from the distribution directory.
   - The compiler reads runtime function signatures from that bitcode (`llvm/ContextUtils.kt:414-502`, `importRtFunction`).
   - The full compiler-to-runtime contract is listed in `runtime/src/compiler_interface/cpp/CompilerCInterface.cpp:24-88`: 52 entries, including safepoint and thread-state switch functions, which can be no-ops on one thread (INFERRED).
   - The Kotlin side declares 322 unique native functions (`@GCUnsafeCall`/`@SymbolName`) under `runtime/src`.
8. **Changing target settings without touching the compiler:** `-Xoverride-konan-properties` (HACKING.md:326,336; `SetupConfiguration.kt:216`). VERIFIED. KT-43974 ("More flexible cross-compilation in Kotlin/Native") was open in October 2026 (VERIFIED). Using it for this retarget is INFERRED.

### Obsolete
- **Old memory manager.** Reference counting, the cycle collector and freezing are gone (kotlin@aea8bac7d29). The current runtime has `runtime/src/mm` and `gc/{noop,stms,pmcs,cms}` instead. VERIFIED.
- **All the "no OS" switches.** `KONAN_ZEPHYR`, `KONAN_WASM`, `NO_THREADS`, `NO_EXCEPTIONS`, `NO_FFI`, `NO_MATH`, `INTERNAL_DLMALLOC`, `INTERNAL_SNPRINTF`, `INTERNAL_NOW`, `NO_MEMMEM`, `NO_CTORS_SECTION` and `NO_BACKTRACE` appear zero times in `M/kotlin-native/runtime/src` (grep). VERIFIED.
- **Compiler toggles** `threadsAreAllowed`, `indirectBranchesAreAllowed`, `tlsMode` and the box-cache range were made constant (kotlin@29e90d70c6a). The compiler now assumes threads; there is no `supportsThreads` check left in the backend (grep). VERIFIED.
- **Zephyr plumbing.** ZephyrConfigurables, ZephyrLinker, the platform files and the experimental-target mechanism are removed (kotlin@b19ad2505cf, e77d9c9f17f, b2b147267f7). VERIFIED.
- **Exception throwing.** `ThrowException` now does a real C++ throw via `ExceptionObjHolder::Throw` (`runtime/src/main/cpp/Exceptions.cpp:39-43`). A no-exceptions version has to be written. VERIFIED.
- **Math.** The `NO_MATH` stubs are gone; `KotlinMath.cpp` uses libm. Newlib's libm could serve that (INFERRED).
- **Launcher.** `Konan_main` and `Init_and_run_start` still exist (`runtime/src/launcher/cpp/launcher.cpp:51-77`) and their shape can be reused, but `argc`/`argv` must be built by us (INFERRED).

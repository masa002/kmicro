# kmicro measurements

The first measurements, October 2026, on a Windows x64 host: Kotlin/Native **2.4.21** (released 2026-10-08), target
`linux_arm32_hfp`, retargeted to Cortex-M4 (`thumbv7em-none-eabihf`, `-mcpu=cortex-m4 -mfpu=fpv4-sp-d16
-mfloat-abi=hard`) with the LLVM 21 `clang` / `ld.lld` that Kotlin/Native downloads on its first run
(`llvm-21-x86_64-windows-essentials-150`).

Status: section 1 is how kmicro builds today ([how-it-works.md](../how-it-works.md)). Sections 2 and 3 are why it
has its own runtime, and the list of runtime functions it started from.

## 1. Getting the IR out of the official compiler (2026-10-10)

- `-p bitcode` is gone: `error: Bitcode output kind is obsolete` (`NativeCompilerDriver.kt:45`).
- Instead: `-p static` plus `-Xsave-llvm-ir-after=Codegen` and `-Xsave-llvm-ir-directory=<dir>` writes
  `out.Codegen.ll`. That module is the Kotlin program plus the stdlib, before the stock runtime is linked in.
  `LinkBitcodeDependencies` (runtime linked) and `LTOBitcodeOptimization` (after the compiler's own LTO) can be
  saved the same way.
- `linux_arm32_hfp` still exists in 2.4.21 but warns "deprecated and will be removed soon". kmicro pins 2.4.21.
- `kotlinc-native.bat` splits arguments at `=` and `,` when called from PowerShell. Pass every option through an
  argument file (`kotlinc-native @args.txt`).
- The IR header is `target datalayout = "e-m:e-p:32:32-Fi8-i64:64-v128:64:128-a:0:32-n32-S64"`, triple
  `armv6kz-unknown-linux-gnueabihf`. The data layout is the one `thumbv7em-none-eabihf` uses, so retargeting is a
  triple change plus Cortex-M4 values for the per-function `target-cpu` / `target-features` attributes
  ([toolchain/retarget.py](../../toolchain/retarget.py)).

## 2. The smallest program (`@CName("k_add") fun add(a: Int, b: Int) = a + b`)

| build | .text | other |
|---|---|---|
| the function alone (module initializers dropped) | **14 B** (`adds r4, r1, r0` + a safepoint call) | — |
| with the stdlib module initializers (`@llvm.global_ctors`) | 878 B | .data 8, .bss 7 |
| the stock runtime + stdlib after the compiler's own LTO, retargeted (libc left out) | **184,226 B** | .rodata 38,182, .ARM.extab 4,372, .ARM.exidx 3,296, .bss 1,564 |

With the stock runtime, the smallest program takes 184 KB of the STM32L431's 256 KB of flash, far more than a
firmware that already holds C code can spare. That is why kmicro writes its own runtime.

## 3. What each language feature costs and which runtime symbols survive dead-code elimination

Each probe is a short Kotlin program that uses the features named in its row. Method
([tools/measure.py](../../tools/measure.py)):
- Retarget the Codegen IR.
- Make every runtime symbol a trapping stub.
- Full LTO with `ld.lld --gc-sections`, keeping only the probe's entry functions.
- Sizes exclude the stubs.
- Thread-local storage is turned into ordinary storage (single thread), which removes `__aeabi_read_tp`.

| probe | .text | .rodata | .ARM.exidx/extab | runtime symbols needed |
|---|---|---|---|---|
| classes, interface, virtual calls | 14,394 | 7,672 | 552 / 100 | 58 |
| string template, hashCode | 14,506 | 7,040 | 544 / 100 | 54 |
| mutableListOf, filter, map, sum | 28,810 | 12,824 | 1,256 / 100 | 62 |
| custom exception, try/catch/finally | 14,256 | 7,160 | 552 / 128 | 54 |
| suspendCoroutine + startCoroutine + resume | 33,666 | 21,168 | 1,288 / 136 | 68 |
| app-shaped: sealed events, state machine, ArrayList<String> log, coroutine loop | 42,070 | 22,012 | 1,752 / 136 | 66 |

measure.py lists the runtime symbols a probe needs; the lists of this run were not kept.

Where the ~14 KB baseline comes from, as soon as an object is allocated:
- **Exception text for runtime errors.** `ThrowClassCastException` and the null-pointer paths build their messages
  through `Any.toString`, `TypeInfoNames.qualifiedName`, `StringBuilder` and `Throwable.toString`.
- **Lazy and thread plumbing.** `SynchronizedLazyImpl` and `Lock` come in with it.
- **Exception unwinding.** libgcc's ARM EHABI unwinder adds about 2.5 KB.

Not a blocker: the app-shaped probe is about 64 KB of flash in total.

The union of the runtime symbols over all probes is the runtime contract for the bring-up milestones M1–M4 of
[design-plan.md](design-plan.md) §3 (about 70 functions). By group:

| group | functions |
|---|---|
| allocation | AllocInstance, AllocArrayInstance |
| reference stores / GC hooks | UpdateHeapRef, UpdateStackRef, UpdateReturnRef, UpdateVolatileHeapRef, CompareAndSetVolatileHeapRef, Kotlin_processObjectInMark, Kotlin_processArrayInMark, Kotlin_processEmptyObjectInMark |
| frames and safepoints | EnterFrame, LeaveFrame, SetCurrentFrame, Kotlin_mm_safePointFunctionPrologue, Kotlin_mm_safePointWhileLoopBody |
| globals and initialization | RegisterGlobal, CallInitGlobalPossiblyLock, CallInitThreadLocal, AppendToInitializersTail, AddTLSRecord, LookupTLS |
| types | IsSubclassFast, Kotlin_TypeInfo_isInstance, Kotlin_Any_getTypeInfo, Kotlin_Any_hashCode, Kotlin_TypeInfo_getPackageName, Kotlin_TypeInfo_getRelativeName |
| arrays | Kotlin_{Array,CharArray,IntArray}_* |
| strings | Kotlin_String_*, Kotlin_StringBuilder_insert*, Kotlin_Int_toString, Kotlin_Long_toStringRadix |
| boxing caches | getCached*Box, in*BoxCache |
| exceptions | ThrowException, Kotlin_getExceptionObject, Kotlin_getCurrentStackTrace, Kotlin_getStackTraceStrings, __gxx_personality_v0, __cxa_begin_catch, __cxa_end_catch, __cxa_end_cleanup |

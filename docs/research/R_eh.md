# Kotlin/Native 2.4.21 exceptions on a bare-metal Cortex-M4 (STM32L431): lowering, options, cost

> **Status.** Option (b) is what [runtime/eh.c](../../runtime/eh.c) implements: kmicro's own personality routine on
> libgcc's ARM EHABI unwinder. Cleanup pads end in `__cxa_end_cleanup`, which the ARM backend emits itself, not in
> `_Unwind_Resume` (design-check.md #26). An uncaught exception is reported with its type, message and stack trace,
> then the program stops ([how-it-works.md](../how-it-works.md)). §1.6 is too strong: `-Xllvm-lto-passes` can run
> `lower-invoke` inside the unmodified compiler, so option (c2) needs no separate `opt` (design-check.md #29).

Sizes come from `arm-none-eabi-size -A`, `nm -S` and `objdump -r/-d` on the multilib archives of xPack GCC 15.2.1.

## 0. Bottom line

- **Recommendation: option (b).** Use libgcc's ARM EHABI unwinder (`unwind-arm.o`, `pr-support.o`, `libunwind.o` from `thumb/v7e-m+fp/hard`). Write our own small `__gxx_personality_v0`, `__cxa_begin_catch`, `__cxa_end_catch`, `ThrowException`, `Kotlin_getExceptionObject`, `_ZSt9terminatev` and a dummy `_ZTI18ExceptionObjHolder` in the new C runtime. Do not link libsupc++, and do not use malloc.
- **Fixed cost:** about 4.7 KB flash and about 0.1 KB static RAM, plus about 1.0 KB of stack used only while a throw is in progress.
- **Variable cost:** the Kotlin unwind tables (`.ARM.exidx` and `.ARM.extab`, which also hold the LSDA). Every table-based option pays this. It has to be measured on the first real build.

## 1. How 2.4.21 lowers throw / try / catch / finally

All paths below are under `kotlin-native/backend.native/compiler/ir/backend.native/src/org/jetbrains/kotlin/backend/konan/` unless stated otherwise.

### 1.1 throw
- `evaluateThrow` calls `currentCodeContext.exceptionHandler.genThrow` (`llvm/IrToBitcode.kt:953-957`). VERIFIED
- **Throw inside a try in the same function:** `CatchingScope.genThrow` is a direct branch to the handler. No runtime call is made (`IrToBitcode.kt:1024-1034`). This includes throws that come from Kotlin `inline` functions such as `require` and `check`. VERIFIED
- **Any other throw:** the default `genThrow` emits `call ThrowException(KRef)` followed by `unreachable` (`llvm/CodeGenerator.kt:75-94`). VERIFIED

### 1.2 Calls: call vs invoke
`callRaw` (`CodeGenerator.kt:830-866`) decides as follows. VERIFIED
- If the callee is `nounwind`, it emits a plain `call`.
- If the handler is `Caller`, it emits a plain `call`, unless the function has a cleanup landing pad.
- If the handler is `Local`, it emits `invoke … unwind label %landingpad`.
- If the handler is `None`, the **compiler itself throws** "no exception handler specified when calling function … without nounwind attr" (`:846-853`).

Other facts that follow from this:
- The function-level default handler is `Caller` (`IrToBitcode.kt:634-635`). So **a function with no try/finally contains no invoke at all.** VERIFIED
- Cleanup landing pads exist only when `forceCleanupLandingpad`, `@ExportForCppRuntime` or `switchToRunnable` applies, i.e. in C→Kotlin bridges and `Konan_start`. The pad is `landingpad cleanup` → releaseVars → thread-state switch → `resume` (`CodeGenerator.kt:621-626, 1382-1394`). VERIFIED
- Runtime functions are imported with their attributes copied from runtime.bc (`ContextUtils.kt:330-344`). So the nounwind-ness of our runtime functions decides call vs invoke. Every runtime function the compiler calls with handler `None` (AllocInstance, EnterFrame, SetCurrentFrame, …) **must** be nounwind in our runtime.bc. VERIFIED

### 1.3 try / catch / finally
- **finally** is removed before codegen by the common `FinallyBlocksLowering` (`driver/phases/NativeLoweringPhases.kt:274`). It becomes `try {…} catch (t: Throwable) { finally; throw t }`, and the finally block is inlined on the normal and return paths (`compiler/ir/backend.common/.../FinallyBlocksLowering.kt:207-262` at HEAD). `evaluateTry` asserts that no finally is left (`IrToBitcode.kt:1083`). VERIFIED
- **Each catching scope gets one landing pad.** VERIFIED
  - It is `landingpad {ptr,i32} catch ptr null`, which is catch-all at the LLVM level (`CodeGenerator.kt:1139-1148`).
  - It then calls `__cxa_begin_catch(exn)` → `Kotlin_getExceptionObject(raw, slot)` → `__cxa_end_catch()` (`:1150-1165`), and branches to the Kotlin handler.
- **Matching the Kotlin type happens in Kotlin code.** VERIFIED
  - Each catch clause is a `genInstanceOfImpl` check; `catch (Throwable)` short-circuits.
  - If no clause matches, the exception is rethrown through the outer handler. If there is no enclosing try, that is a fresh `ThrowException` (`IrToBitcode.kt:1044-1077`).
  - So **the personality routine never has to match Kotlin types.**
  - Each catch that does not match, and each finally, restarts a full two-phase unwind.
- **Every landing pad calls `SetCurrentFrame(slots)`** (`CodeGenerator.kt:1023-1037`). This repairs the GC shadow stack, which is why skipping LeaveFrame on frames that were unwound is safe. VERIFIED

### 1.4 Interop "filtering" handler (Kotlin→C bridges)
- It applies to `KOTLIN_TO_C_BRIDGE` / `@FilterExceptions` functions. For imported bridges the mode is TERMINATE (`IrToBitcode.kt:2536-2595`, `cgen/CBridgeGenUtils.kt:139-143`). VERIFIED
- The landing pad is `landingpad catch @_ZTI18ExceptionObjHolder, catch null`. It compares the selector with `llvm.eh.typeid.for.p0(@_ZTI18ExceptionObjHolder)` (`CodeGenerator.kt:1043-1106`; intrinsic at `ContextUtils.kt:579-585`). VERIFIED
  - Kotlin exception: forwarded to the outer handler.
  - Anything else: `__cxa_begin_catch` + `_ZSt9terminatev` + an infinite loop (`:1108-1124`).
- C stubs are compiled with `-O2 -fexceptions` (`CStubsManager.kt:40-43`). VERIFIED
  - So each call site from Kotlin into C keeps an invoke and a filtering pad, unless the C function is declared `__attribute__((nothrow))` and LLVM infers nounwind after linking. INFERRED
- `kotlinExceptionHandler` (`CodeGenerator.kt:1126-1137`) is used only by ObjC export (`objcexport/ObjCExportCodeGenerator.kt:901-936`). It is not relevant here. VERIFIED

### 1.5 Symbols involved

| Symbol | Declared at | Must exist in runtime.bc? | Role |
|---|---|---|---|
| `ThrowException(KRef)` | `ContextUtils.kt:432` (importRtFunction; fails with "function not found" otherwise, `:334`) | yes | raise |
| `Kotlin_getExceptionObject(void*, KRef*)`, OBJ_GETTER, NOTHROW | `ContextUtils.kt:439`; `runtime/src/main/cpp/Exceptions.h` | yes | extract KRef |
| `SetCurrentFrame` | `CodeGenerator.kt:1033` | yes | repair shadow stack |
| `__gxx_personality_v0` (`i32(...)` nounwind; `__gxx_personality_seh0` only on MINGW_X64) | `ContextUtils.kt:596-612` | no, resolved at link | personality |
| `__cxa_begin_catch(ptr)`, `__cxa_end_catch()` | `:614-625` | no | catch |
| `_ZSt9terminatev` | `:601-605` | no | filtering pad, foreign exception |
| `_ZTI18ExceptionObjHolder` (global) | `CodeGenerator.kt:1464-1468` | only if a filtering pad is emitted | type-table entry |
| `_Unwind_Resume` | emitted by LLVM for `resume` | no | cleanup pads (INFERRED; confirm with `nm -u`) |
| `Kotlin_processUnhandledException`, `Kotlin_terminateWithUnhandledException` | `Konan_start` wraps main in try/catch(Throwable) (`EntryPoint.kt:61-90`), calling them via `@GCUnsafeCall` (`runtime/src/main/kotlin/kotlin/native/Runtime.kt:77-91`) | yes, as C | unhandled-exception path |
| `HandleCurrentExceptionWhenLeavingKotlinCode` | used only by the C++ C-adapter for `-produce static/dynamic` (`cexport/CAdapterGenerator.kt:355-358`) | not if we link bitcode ourselves | |

Notes on the table: VERIFIED
- The Kotlin-side throw helpers (`ThrowNullPointerException`, `ThrowArrayIndexOutOfBoundsException`, …) are Kotlin code that simply `throw` (`runtime/src/main/kotlin/kotlin/native/internal/RuntimeUtils.kt:26-47`).
- In the stock runtime, `ThrowException` does a C++ `throw ExceptionObjHolderImpl`. That object holds the exception through an `OwningExternalRCRef`, which acts as a GC root (`runtime/src/main/cpp/Exceptions.cpp:39-43`; `runtime/src/mm/cpp/ExceptionObjHolder.cpp:15-38`). Our runtime must keep the in-flight KRef alive in the same way.

### 1.6 Can a compiler or binary option avoid C++ EH?
**No.** VERIFIED
- `native/binary-options/.../BinaryOptions.kt` has no exception-related option.
- The personality name is hard-coded per target.
- The backend never emits `uwtable` (grep finds nothing).

The only lever is nounwind on runtime declarations, together with LLVM's own nounwind inference.

### 1.7 How the old wasm32 and zephyr targets handled it (archive v1.3.70, commit 9e63309)
- **Runtime build flags:** both were built with `-fno-exceptions` and `-DKONAN_NO_EXCEPTIONS=1` (`shared/.../ClangArgs.kt:122-155, 322-344`). VERIFIED
- **ThrowException** printed the throwable, then `RuntimeCheck(false, "Exceptions unsupported")` (`runtime/src/main/cpp/Exceptions.cpp:204-206`). `TRY_CATCH` and the init paths dropped their try blocks (`Porting.h:85-92`, `Memory.cpp:1977-2055`). VERIFIED
- **Codegen was the same for every target.** The only difference was the personality name: `IOS_ARM32` used `__gxx_personality_sj0` (SjLj), `MINGW_X64` used seh0, and everything else used `__gxx_personality_v0` (`ContextUtils.kt:509-513`). VERIFIED
- **Zephyr link:** the sample linked `arm-none-eabi/lib/thumb/libsupc++.a` to resolve the personality and `__cxa_*` (`samples/zephyr/CMakeLists.txt:6-10`). The platform was armv7m-none-eabi, cortex-m4, -mthumb (`konan/platforms/zephyr/stm32f4_disco`). VERIFIED
  - So the binary carried tables and a personality, but any throw aborted. **The Zephyr target never ran a `catch` block.**
- **wasm32:** `lld --allow-undefined` (`konan.properties:688`) left the EH references unresolved. LLVM's wasm backend at the time had no EH model, so it lowered invokes to calls itself. INFERRED

## 2. Options for bare-metal ARMv7E-M

### 2.0 Measured pieces (xPack 15.2.1, `thumb/v7e-m+fp/hard`) — VERIFIED

**libgcc.a**

| Object | Text | Other |
|---|---|---|
| `unwind-arm.o` | 2676 | exidx 208 |
| `pr-support.o` | 952 | exidx 72, extab 24 |
| `libunwind.o` (assembly, single section) | 408 | |
| `unwind-c.o` (`__gcc_personality_v0`, C cleanup-only; not needed) | 764 | |

- The `v7e-m/nofp` multilib has the same sizes.
- libgcc contains **no `_Unwind_SjLj_*`** and **no DWARF unwinder** (no `unwind-dw2.o`).
- The unwinder needs `abort`, `memcpy`, `__exidx_start` and `__exidx_end`. Its references to `__cxa_begin_cleanup`, `__cxa_type_match` and `__cxa_call_unexpected` are weak.

**libsupc++_nano.a** (text + rodata/data/bss)

| Object | Size |
|---|---|
| `eh_personality.o` | 1270 |
| `eh_arm.o` | 342 |
| `eh_catch.o` | 224 |
| `eh_throw.o` | 320 |
| `eh_call.o` | 128 |
| `eh_terminate.o` | 156 |
| `eh_globals.o` | 16 + 12 bss |
| `eh_exception.o` | 84 + 249 ro |
| `class_type_info.o` | 226 + 90 ro |
| `tinfo.o` | 72 + 53 ro |
| `eh_alloc.o` | 670 + 127 ro + 16 bss + an `.init_array` constructor |
| `eh_term_handler.o`, `eh_unex_handler.o` | 4 + 4 data |

**`eh_alloc` and the emergency pool (RAM):**
- The 16 B in bss is only the pool descriptor.
- The arena is **malloc'd by a static constructor**, which calls `getenv`, `malloc` and `strtoul` to read `GLIBCXX_TUNABLES`.
- `__cxa_allocate_exception` calls `malloc` first.
- A weak `string_view::compare` refers to libstdc++'s `__throw_out_of_range_fmt` (202 B in nano).
- The default terminate handler is `abort`, so `cp-demangle` (about 15 KB) is not pulled in.

**Stack frames (from objdump prologues):**

| Function | Frame |
|---|---|
| asm `_Unwind_RaiseException` | about 72 B pushed |
| `__gnu_Unwind_RaiseException` | 20 + 492 |
| `__gxx_personality_v0` | 36 + 84 |
| `_Unwind_VRS_Pop` | 24 + 272 |
| `__gnu_unwind_execute` | 24 + 24 |

**The C firmware this was planned for** (typical of bare-metal firmware):
- The linker script already has `.ARM.extab`, `.ARM.exidx` and `__exidx_start/__exidx_end`.
- Its only exidx entry is 8 B from libgcc's `__udivmoddi4`. No unwinder is linked.
- CFLAGS have no `-funwind-tables` or `-fexceptions`.
- There is no malloc or heap, and the start-up code never runs `.init_array`.

### (a) libgcc unwinder + libsupc++ `__gxx_personality_v0`
- **How it would work:**
  - `ThrowException` calls `__cxa_allocate_exception(4)`, stores the KRef, roots it, then calls `__cxa_throw(p, &_ZTI18ExceptionObjHolder, NULL)`.
  - `_ZTI18ExceptionObjHolder` is written in C as `{&_ZTVN10__cxxabiv117__class_type_infoE[2], "18ExceptionObjHolder"}`.
  - `Kotlin_getExceptionObject` reads `*(KRef*)holder`.
  - **Override `__cxa_allocate_exception` and `__cxa_free_exception` with a static pool of 1–2 slots.** Otherwise `eh_alloc.o` pulls in malloc, getenv, strtoul and `.init_array`, and that constructor never runs in a firmware whose start-up skips `.init_array`.
  - `abort` goes to the firmware's fatal-error handler.
- **Flash:** about 4.0 KB unwinder + about 2.8 KB libsupc++ text + 0.4 KB rodata ≈ **7.2 KB**. If eh_alloc and malloc get pulled in, about 9–10 KB. (Per-object sizes VERIFIED; the sum is INFERRED.)
- **RAM:** 12 B globals + 8 B handlers + about 136 B per in-flight exception. A `__cxa_refcounted_exception` is about 128 B, including the 88 B UCB. Kotlin calls `__cxa_end_catch` immediately, so one or two slots are enough: about 0.15–0.3 KB. The throw itself uses about 1.1–1.2 KB of stack.
- **Correctness:** full.
  - Small caveat: LLVM ends cleanup pads with `_Unwind_Resume`, not `__cxa_end_cleanup`. So libsupc++'s ARM propagating-exception list is pushed but never popped. This only affects bridge cleanup pads and is harmless. INFERRED
- **Effort:** 0.5–1 day, low risk. Its best use is as a **bring-up reference** that (b) can be checked against.

### (b) Custom minimal personality on the libgcc unwinder — RECOMMENDED

**The personality routine.** About 150–250 lines of C, about 0.6–0.8 KB. Signature: `_Unwind_Reason_Code __gxx_personality_v0(_Unwind_State, _Unwind_Control_Block*, _Unwind_Context*)`.

- **States:** handle VIRTUAL_UNWIND_FRAME (phase 1), UNWIND_FRAME_STARTING (phase 2), and UNWIND_FRAME_RESUME (after a cleanup pad's `_Unwind_Resume`; this one only unwinds).
- **Finding the call site:**
  - Get the LSDA with `_Unwind_GetLanguageSpecificData` and the function start with `_Unwind_GetRegionStart`.
  - Take IP = (r15 & ~1) − 1.
  - Parse the header: LPStart encoding (omit means function start), TType encoding and offset (only skipped), then call-site encoding and length.
  - Walk the call-site table. It must handle both uleb128 and udata4, because LLVM picks one per object file. INFERRED
- **Cleanup (action = 0):**
  - Phase 1: continue unwinding.
  - Phase 2: install the pad with r0 = ucbp and r1 = 0.
- **Catch (action > 0):**
  - Take the first action record's filter.
  - Phase 1: save `barrier_cache.sp` and return `_URC_HANDLER_FOUND`.
  - Phase 2: set r0 = ucbp, r1 = filter, pc = lp | 1, and return `_URC_INSTALL_CONTEXT`.
- **Continue path:** `__gnu_unwind_frame(ucbp, ctx)`, then return `_URC_CONTINUE_UNWIND`. An EHABI personality must unwind its own frame; libsupc++'s personality imports `__gnu_unwind_frame` for exactly this (VERIFIED).
- **Why the selector comes out right without reading the type table:**
  - The filtering pad's first action is `typeid(ExceptionObjHolder)`, which is exactly what `llvm.eh.typeid.for` returns, so the Kotlin branch is taken.
  - For catch-all pads the selector is not used.
  - So there is no type-table and no TARGET2 decoding at all.

**The rest of the runtime:**
- **`ThrowException`:**
  - Its translation unit must be built with `-fexceptions` (clang) or `-funwind-tables` (gcc), and it must **not** be nounwind.
  - It fills a static, 8-byte-aligned `{UCB, KRef}`, sets the exception class and cleanup function, roots the KRef, and calls `_Unwind_RaiseException`.
  - If that call returns, it calls the firmware's fatal-error handler. This happens when there is no handler, or when unwinding reaches a C frame. C code has no exidx, and GNU ld fills such gaps with CANTUNWIND entries (INFERRED). Phase 1 runs before any cleanup, so the exception object is still intact for the log.
- **Catch helpers:**
  - `__cxa_begin_catch` returns the ucb.
  - `Kotlin_getExceptionObject` stores and returns the KRef.
  - `__cxa_end_catch` frees the slot and drops the GC root.
- **Fatal paths and dummies:** `_ZSt9terminatev` and `abort` go to the fatal-error handler. `_ZTI18ExceptionObjHolder` is a dummy constant.
- **Link:** libgcc.a only, which the firmware already links. Do not link libsupc++; it would clash on these symbols.

**Cost and risk:**
- **Flash:** about 4.0 + 0.7 ≈ **4.7 KB**.
- **RAM:** about 100 B static. The throw itself uses about 1.0 KB of stack: 72 + 512 + ~60 + 48 + 296 (frames VERIFIED, sum INFERRED).
- **Correctness:** full Kotlin semantics. No foreign exceptions exist on this system.
- **Effort:** 2–4 days, low-to-medium risk.
- **Throw latency:** roughly 0.5–2 k cycles per frame per phase, about 0.06–0.25 ms per frame at 16 MHz (INFERRED). Measure it with `DWT->CYCCNT` and log the result. Hard real-time paths stay in C and never throw.

### (c) invoke→call plus a fatal throw
- **(c1) runtime-only variant:**
  - Make `ThrowException` `nounwind noreturn` in runtime.bc. The compiler then emits a plain `call` for it (`CodeGenerator.kt:832-834`; VERIFIED).
  - LLVM's function-attrs pass and SimplifyCFG then drop invokes whose callees are provably nounwind.
  - But indirect calls (virtual, interface, lambda) cannot be proven nounwind, so their invokes and pads stay as dead code. Builds without optimisation keep all of them. INFERRED
  - Still needs stub definitions for the personality, `__cxa_*`, `_Unwind_Resume` and `_ZSt9terminatev`.
- **(c2) full variant:**
  - Add `opt -passes=lower-invoke,simplifycfg` on the linked bitcode, then `/DISCARD/` the `.ARM.exidx*` and `.ARM.extab*` sections.
  - The installed LLVM 21 bundle contains only clang, clang++, clang-cache, ld.lld, lld, llvm-ar, llvm-cov and llvm-profdata. **There is no opt or llc** (VERIFIED). So this needs an upstream LLVM 21.x `opt`, or a text rewrite via `clang -S -emit-llvm -x ir`.
- **Size:** about 0.1–0.2 KB of stubs. It also removes the 4 KB unwinder, about 8 B of exidx per function, all landing pads and the duplicated finally code. This is the largest saving.
- **Correctness: partial.**
  - Only throws written lexically inside the try (including inline `require`/`check`) are caught.
  - Any throw that comes from a called function is fatal.
  - finally does not run on the exceptional path.
  - The coroutine machinery's `catch (exception: Throwable) { Result.failure(exception) }` (`runtime/src/main/kotlin/kotlin/coroutines/ContinuationImpl.kt:35`, VERIFIED) never runs, so failure and cancellation by exception are impossible.
  - In effect this is Rust's `panic=abort`, the same behaviour the Zephyr port had.
- **Effort:** 1–2 days. Technical risk is low; semantic risk is high.

### (d) setjmp/longjmp
- **Without changing the compiler or LLVM's EH model: not feasible.** VERIFIED from the codegen structure.
  - Nothing runs at the entry of a try.
  - The only runtime calls on EH paths sit inside landing pads, which run after the unwind.
  - EnterFrame/LeaveFrame are per-function GC frames, emitted only for functions that have slots, and LeaveFrame is skipped during unwinding.
- **With LLVM's own SjLj model** (`-exception-model=sjlj`): feasible without touching the Kotlin/Native compiler. This is how Kotlin/Native 1.3 supported ios_arm32. Requirements:
  - Our own `_Unwind_SjLj_Register/Unregister/RaiseException/Resume` (libgcc has none).
  - A personality that reads the SjLj-style LSDA, still named `__gxx_personality_v0`. LLVM selects SjLj from the exception model, not from the personality name. INFERRED
- **Cost:** about 0.6–1 KB of runtime and no exidx.
  - On every execution, each function with a pad registers and unregisters a function context of about 50–60 B.
  - Every invoke stores a call-site index.
  - setjmp clobbers all callee-saved registers, including d8–d15.
- **Risks:**
  - ARM SjLj in LLVM is a legacy Darwin path, untested on M-profile ELF.
  - It is unverified whether clang passes `-exception-model` through for `-x ir` input. The fallback is `ld.lld -mllvm -exception-model=sjlj` during LTO.
  - Effort 4–8 days. Not recommended.

### Comparison

| | (a) libsupc++ | (b) own personality | (c2) lower-invoke | (d) SjLj |
|---|---|---|---|---|
| Fixed flash | ≈7.2 KB (9–10 KB with malloc) | ≈4.7 KB | ≈0.2 KB | ≈0.6–1 KB |
| Kotlin tables | exidx + extab + LSDA | same as (a) | none | LSDA only, plus per-pad code |
| Static RAM | ≈0.15–0.3 KB | ≈0.1 KB | 0 | ~8 B |
| Stack during a throw | ≈1.1–1.2 KB | ≈1.0 KB | — | small |
| Overhead when nothing is thrown | 0 | 0 | 0 | every try-function |
| catch by type / finally | yes | yes | only local throws | yes |
| Effort | 0.5–1 d | 2–4 d | 1–2 d | 4–8 d |

## 3. What LLVM needs to emit ARM EHABI tables for thumbv7em-none-eabi

- **The model comes from the triple.** ARM ELF uses the EHABI exception model for every OS except NetBSD, so no flag is needed. INFERRED (the LLVM source was not read)
- **`-exception-model=` cannot help here.** It can switch to sjlj or dwarf, but not to "none" on ARM. dwarf would need an `.eh_frame` unwinder, which this libgcc does not have. `-arm-enable-ehabi` and `-arm-enable-ehabi-descriptors` no longer exist (removed around LLVM 3.5); do not pass them. INFERRED
- **Function attributes:** Kotlin/Native emits no `uwtable` and no `nounwind` on Kotlin functions (VERIFIED). As a result: INFERRED
  - Every function that is not nounwind gets `.fnstart/.fnend` and an 8 B EXIDX entry. Short prologues use the compact `__aeabi_unwind_cpp_pr0` form inline; longer ones, and functions with landing pads, get an extab entry.
  - nounwind functions get `.cantunwind`, which is still an 8 B entry.
  - `uwtable` is not needed for EH.
- **Personality:**
  - `LLVMBuildLandingPad` sets `personality @__gxx_personality_v0` on the function (`llvm/LlvmCallable.kt:49-50`).
  - In the object file this becomes `.personality __gxx_personality_v0`, an R_ARM_PREL31 in `.ARM.extab`. Compact entries carry R_ARM_NONE references to `__aeabi_unwind_cpp_pr0/1` (VERIFIED on the GCC objects in libsupc++.a; INFERRED for LLVM's output).
  - The LSDA follows the opcodes in `.ARM.extab`.
  - Type-table entries are `sym(target2)`, i.e. R_ARM_TARGET2. Pass `--target2=rel` explicitly; the option exists in this ld (VERIFIED). (b) never reads the type table.
- **Retargeting edits that are not EH-specific but are mandatory:**
  - Set the triple and data layout. The compiler copies both from runtime.bc into the generated module (`llvm/Runtime.kt:58-60`, `ContextUtils.kt:410-411`; VERIFIED), so our runtime.bc can supply them.
  - Rewrite the per-function `"target-cpu"="arm1176jzf-s"` and `"target-features"="+armv6kz,…,-thumb-mode,…"` (`konan.properties:521,524`; `llvm/LlvmAttributes.kt:28-35`; VERIFIED). Otherwise LLVM generates ARM-state code, which the M4 cannot run.
  - Start from linux_arm32_hfp (`-mfloat-abi hard`, `:525`). Its hard-float ABI matches the `v7e-m+fp/hard` multilib that Cortex-M4F firmware links. android_arm32 is PIC, uses emulated TLS and soft-float.
- **Runtime build:** the translation unit containing `ThrowException` needs unwind info. Everything else must be nounwind (C built with `-fno-exceptions` gives this).
- **Linker:**
  - Keep `.ARM.exidx` between `__exidx_start` and `__exidx_end`; the script already does this.
  - `--gc-sections` keeps each exidx entry together with its function.
  - GNU ld merges identical adjacent entries unless `--no-merge-exidx-entries` is given (the option is VERIFIED; the merging behaviour is INFERRED).
- **Checks on the first object:**
  - `nm -u` should list only `__gxx_personality_v0`, `__cxa_begin_catch`, `__cxa_end_catch`, `_ZSt9terminatev`, `_Unwind_Resume` (possibly also `__cxa_end_cleanup`), `__aeabi_unwind_cpp_pr0/1`, and runtime symbols.
  - The size of `.ARM.exidx` + `.ARM.extab` is the whole table cost. Estimate: 7–12% of Kotlin `.text` (INFERRED).

## 4. Recommendation: (b)

1. **It keeps the compiler's output semantically intact:** catch by type, finally, rethrow, `Result.failure` in coroutines, `runCatching`. The Zephyr port never had more than "throw = abort".
2. **It has the smallest fixed cost of any option with real exceptions:** about 4.7 KB flash and 0.1 KB RAM, against at least 7.2 KB for (a). It needs no libsupc++, no malloc, no C++ globals and no `.init_array`, which this startup code never runs.
3. **It costs nothing when no exception is thrown,** unlike SjLj. An exception that reaches C code ends in the fatal-error handler every time, with the exception object still available for the log.
4. **It uses the unwinder already in the toolchain we link,** from the same multilib.
5. **It does not rule out (c2).** That stays available as a later size lever on the same bitcode, if the measured tables turn out too big. It would change semantics, so it would have to be a deliberate choice.

**Plan:**
1. Bring up with (a) as the reference (about 1 day).
2. Swap in (b) and run a test matrix in QEMU (mps2-an386 is a Cortex-M4 board model) and from board logs. The matrix should cover:
   - nested try
   - catch by type, and rethrow when no clause matches
   - finally on both the throw and the return path
   - a throw 10 frames deep
   - a bridge cleanup pad and `_Unwind_Resume`
   - the filtering-pad selector
   - an exception reaching C (must go to fatal)
   - an exception inside a coroutine becoming `Result.failure`
3. Then measure the table bytes.

**Licence note:** libgcc is GPLv3 with the GCC Runtime Library Exception, and the C firmware already links it. INFERRED
# kmicro: the contract between Kotlin/Native 2.4.21 generated code and its runtime, for a bare-metal Cortex-M4 replacement

> **Status.** This is the contract kmicro's runtime implements ([runtime/kmicro.h](../../runtime/kmicro.h) and the
> files next to it). The route of §0 items 1-2 and §5.3 (a), a `compiler_interface.bc` of our own in a copied
> distribution, was not taken: kmicro saves the compiler's IR and retargets it as text (design-plan.md, D2-D4). On
> that route, C entry points would have needed `__attribute__((used, retain))`, not the `used` alone that §1 says
> (design-check.md #25). kmicro has no such entry points: C calls the Kotlin functions directly, in one LTO link.

Path abbreviations used below (all are 2.4.21 unless marked):
- **BK** = `kotlin-native/backend.native/compiler/ir/backend.native/src/org/jetbrains/kotlin/backend/konan/`
- **RT** = `kotlin-native/runtime/src/`
- **KT** = `RT/main/kotlin/`
- **DIST** = the Kotlin/Native 2.4.21 prebuilt distribution for Windows (`kotlin-native-prebuilt-windows-x86_64-2.4.21/`)
- **ARCH** = the archived github.com/JetBrains/kotlin-native repository at tag v1.3.70
- **git:** = read with `git show` at tag v2.4.21 (files outside the checked-out folders)

---

## 0. Findings that decide the design

1. **The compiler gets its runtime ABI from a bitcode file, not from code inside the compiler.**
   - The compiler parses `compiler_interface.bc` and takes these from it: the struct types, the target triple, the data layout, and the declarations (including attributes such as `nounwind`) of every runtime function it calls. VERIFIED: BK/llvm/Runtime.kt:23-62, BK/llvm/ContextUtils.kt:330-345 and :409-412.
   - The generated module's triple and data layout are copied from that file (`LLVMSetTarget(module, runtime.target)`).
   - **So if we supply a `compiler_interface.bc` built for `thumbv7em-none-eabihf`, the compiler emits Thumb-2 bitcode directly. Nothing has to be retargeted afterwards.**
2. **`-Xruntime=<file>` replaces only `compiler_interface.bc`.** VERIFIED: BK/llvm/runtime/RuntimeModulesConfig.kt:22-29.
   - All other runtime modules (`runtime.bc`, `mm.bc`, and so on) always come from `<konan.home>/konan/targets/<target>/native/`. VERIFIED: :19-20 and CompilerOutput.kt:131-187.
   - They are linked into the program whenever the stdlib is compiled into it and is not cached. VERIFIED: CompilerOutput.kt:69-70 and :197-199.
   - **To drop the stock runtime, run the unmodified compiler against a copied distribution** (`-Dkonan.home=<copy>`) whose `.bc` files are ours.
3. **`-produce bitcode` is a hard error in 2.4.21** ("Bitcode output kind is obsolete"). VERIFIED: BK/driver/NativeCompilerDriver.kt:45.
   - The usable route is `-produce program -Xtemporary-files-dir=D -Xdisable-phases=ObjectFiles,Linker`.
   - That leaves `D/out.bc`: the final module after LTO, with the runtime merged in. VERIFIED: TopLevelPhases.kt:196 and :393, Bitcode.kt:44-51, git:compiler/ir/backend.common/.../PhaseBuilders.kt:84-98 (a disabled phase with Unit output does nothing), git:compiler/config/.../CompilerPhase.kt:86-88.
4. **Use `-target linux_arm32_hfp`, not `android_arm32`.**
   - Its toolchain dependencies are the ones Kotlin/Native downloads on first use: the arm gnueabihf gcc, msys2, and llvm-21 essentials. VERIFIED by ls of the dependency folder, and DIST/konan/konan.properties:65, :68, :502-505.
   - It is hard-float. `android_arm32` is armv4t with `-fpregs`, and its NDK is not downloaded. VERIFIED: konan.properties:623-631.
   - **You must override `targetCpu.linux_arm32_hfp` and `targetCpuFeatures.linux_arm32_hfp`.** The stock values are `arm1176jzf-s` and `+armv6kz,...,-thumb-mode` (konan.properties:521-523), and these are written as `target-cpu` / `target-features` attributes on every Kotlin function (VERIFIED: BK/llvm/LlvmAttributes.kt:24-35, LlvmFunctionPrototype.kt:200-207). Left alone, the compiler would emit ARM-mode code, which a Cortex-M cannot run.
5. **Build the runtime as LLVM bitcode with the bundled clang 21.1.6.**
   - Array get/set, `getTypeInfo`, `UpdateHeapRef`, safepoints and the rest are real calls to runtime symbols. They only become cheap after LTO inlines them, so the runtime must be bitcode.
   - Use the clang of the LLVM 21 bundle that Kotlin/Native downloads (`llvm-21-x86_64-windows-essentials-150`). The stock `compiler_interface.bc` was produced by "clang version 21.1.6 (Kotlin/llvm-project c2e420df…)" with triple `armv6kz-unknown-linux-gnueabihf`. VERIFIED: strings dump of DIST/konan/targets/linux_arm32_hfp/native/compiler_interface.bc.
6. **There is no "no exceptions" or "no threads" switch in 2.4.21.**
   - Codegen always uses C++ zero-cost EH: `invoke`, `landingpad`, `__gxx_personality_v0`, `__cxa_*`, `std::terminate`, `_ZTI18ExceptionObjHolder`. VERIFIED: ContextUtils.kt:596-625, CodeGenerator.kt:1023-1180.
   - `@ThreadLocal` primitive globals become LLVM `thread_local` with the general-dynamic model. VERIFIED: LlvmUtils.kt:217-230.
   - In 1.3.70, Zephyr forced `NotThreadLocal` and turned throw into abort. VERIFIED: ARCH ContextUtils.kt:492-496, ARCH runtime Exceptions.cpp:201-210. **2.4.21 removed both, so a bare-metal runtime and its build steps have to do the same things themselves.**
7. **Stack roots use a precise shadow stack** (`FrameOverlay` plus a slot array in each frame, linked by `EnterFrame`/`LeaveFrame`). Codegen guarantees that every object reference that is still needed across a call sits in a slot. A non-moving precise mark-sweep only has to walk:
   - the frame chain
   - registered globals
   - TLS slots
   - objects allocated on the stack, which are reachable through their root slots

---

## 1. How the compiler binds to the runtime

| Mechanism | Detail | Evidence |
|---|---|---|
| Type lookup | For each of `TypeInfo`, `ExtendedTypeInfo`, `InterfaceTableRecord`, `AssociatedObjectTableRecord`, `ObjHeader`, `ArrayHeader`, `StringHeader`, `FrameOverlay`, `InitNode`, the compiler wants `struct.<Name>` or a global `touch<Name>` (it takes that global's value type). `WritableTypeInfo` is optional (ObjC only). Missing type → compile error. | VERIFIED Runtime.kt:27-56; RT/compiler_interface/cpp/CompilerCInterface.cpp:16-34 |
| Function import | `importFunction`: `LLVMGetNamedFunction(compiler_interface, name) ?: throw Error("function $name not found")`, then the function type and all attributes are copied. Each call site uses `call` if the declaration is `nounwind`, otherwise `invoke`. | VERIFIED ContextUtils.kt:330-345; CodeGenerator.kt:830-865 |
| Triple / data layout | Taken from `compiler_interface.bc`. The LTO TargetMachine uses the module triple plus `targetCpu` / `targetCpuFeatures` from konan.properties. | VERIFIED ContextUtils.kt:409-412; OptimizationPipeline.kt:88-99, :151-216; Bitcode.kt:162-168 |
| Runtime modules (PROGRAM) | Additional: `launcher.bc`. Runtime: `debug.bc` (only with `-g`), `runtime.bc`, `mm.bc`, `common_alloc.bc`, `common_gc.bc`, `common_gcScheduler.bc`, `noop_crashHandler.bc`, `<sched>_gcScheduler.bc`, `<gc>.bc`, `source_info_libbacktrace.bc` + `libbacktrace.bc` (always on LINUX/ANDROID), `custom_alloc.bc` (or `legacy_alloc.bc` + `std_alloc.bc`), `noop_externalCallsChecker.bc`, plus a compiler-generated "constants" module. | VERIFIED CompilerOutput.kt:115-204; KonanTargetExtenstions.kt (git:native/utils) `supportsLibBacktrace` |
| Linking order | Codegen → link C stubs → link runtime and additional modules (`LinkBitcodeDependencies`) → stack protector, mandatory, module, LTO (`internalize` + `globaldce` + `lto<O3/Oz>`) → `RemoveRedundantSafepoints` → `WriteBitcodeFile` (writes `out.bc` and inserts the `main` alias) → ObjectFiles (`clang++ -cc1`) → Linker. | VERIFIED TopLevelPhases.kt:375-438, :460-499; Bitcode.kt:44-51, :146-186; OptimizationPipeline.kt:353-367 |
| Internalize | In a final binary everything is internalized except `llvm.used`. The stock `Konan_main` survives only because of `RUNTIME_EXPORT = used,retain`. **Our C-callable entry points need `__attribute__((used))`.** | VERIFIED OptimizationPipeline.kt:182, :357-362; RT/main/cpp/Common.h:25-30; launcher.cpp:73-80. INFERRED: LLVM internalize preserves only `llvm.used`/`compiler.used` |
| `performance_inline` | Runtime functions annotated `annotate("performance_inline")` become `alwaysinline` unless `-g` or `smallBinary`. | VERIFIED BK/optimizations/PerformanceInline.kt; NativeSecondStageCompilationConfig.kt:114 |

---

## 2. Runtime symbols that generated code references (item 1)

**Legend.** **T** = trivial for a single-thread, no-OS runtime. **W** = real work. **U** = never referenced if the feature is avoided. Signatures are ARM32 C, with `KRef = ObjHeader*`. `OBJ_GETTER(f, args)` means `ObjHeader* f(args..., ObjHeader** __result__)`: the callee must store its result into `*__result__`, a slot in the caller's frame. VERIFIED: RT/main/cpp/Memory.h:147-160, CodeGenerator.kt:795-828.

### 2.1 Allocation

| Symbol | Signature | Must do | Eff. | Evidence |
|---|---|---|---|---|
| `AllocInstance` | `OBJ_GETTER(AllocInstance, const TypeInfo*)`, nounwind in stock | Allocate `ti->instanceSize_` bytes, zeroed and 8-aligned. Store `ti` into the header with tag 00. Write the result slot. Trigger GC when needed. | W | ContextUtils.kt:416; CodeGenerator.kt:888-895; mm/cpp/Memory.cpp:105-108 |
| `AllocArrayInstance` | `OBJ_GETTER(AllocArrayInstance, const TypeInfo*, int32_t n)`, may throw | size = `align8(alignUp(8, elemSz) + n*elemSz)` with `elemSz = -instanceSize_`; set `count_ = n`; negative n → IllegalArgumentException. For String, n counts UTF-16 units **including** the hash/flags header units (3 on ARM32, see §3). | W | ContextUtils.kt:417; CodeGenerator.kt:897-918; RT/main/cpp/KObject.hpp:61-74; mm/cpp/Memory.cpp:110-116 |
| (stack allocation) | no call | Escape analysis (only with `-opt`) allocas objects and arrays and tags the header with `\|3`. The GC must trace through them but never mark or free them. | — | CodeGenerator.kt:415-551 |

### 2.2 Reference writes and barriers

| Symbol | Signature | Must do | Eff. | Evidence |
|---|---|---|---|---|
| `UpdateHeapRef` | `void(ObjHeader** loc, const ObjHeader* v)` | Store into a field or global (add a barrier only for an incremental GC) | T | ContextUtils.kt:419; CodeGenerator.kt:761-774 |
| `UpdateStackRef` | same | Store into a frame slot | T | :420 |
| `UpdateReturnRef` | `void(ObjHeader** retSlot, const ObjHeader* v)` | Store into the caller's result slot | T | :421; CodeGenerator.kt:757-759, :1432-1438 |
| `ZeroHeapRef` / `ZeroArrayRefs` | `void(ObjHeader**)` / `void(ArrayHeader*)` | Clear a reference field, or all elements of an `Array<T>`, of a stack-local object | T | :422-423; CodeGenerator.kt:505-542 |
| `UpdateVolatileHeapRef` | `void(ObjHeader**, const ObjHeader*)` | seq_cst store (`@Volatile` reference fields) | T | :494; CodeGenerator.kt:768-769 |
| `CompareAndSetVolatileHeapRef` | `bool(ObjHeader** loc, ObjHeader* exp, ObjHeader* nw)` | CAS (AtomicReference, atomic arrays) | T | :495; IntrinsicGenerator.kt:226-243 |
| `CompareAndSwapVolatileHeapRef` | `OBJ_GETTER(…, ObjHeader** loc, ObjHeader* exp, ObjHeader* nw)` | CAS that returns the old value | T | :496 |
| `GetAndSetVolatileHeapRef` | `OBJ_GETTER(…, ObjHeader** loc, ObjHeader* nw)` | Exchange | T | :497; IntrinsicGenerator.kt:245-257 |
| `RegisterGlobal` | `void(ObjHeader** loc)` | Add a reference-typed global to the root set. Called once, when the field is first initialized. | T | :418; IrToBitcode.kt:1717-1719 |

Primitive `@Volatile` and atomic operations become LLVM `load atomic`, `cmpxchg` and `atomicrmw` with seq_cst (VERIFIED IrToBitcode.kt:1636-1640, IntrinsicGenerator.kt:226-257). On ARMv7-M, 32-bit atomics compile to LDREX/STREX. **64-bit atomics (AtomicLong, volatile Long) become `__atomic_*_8` libcalls, which we must provide** (INFERRED: LLVM ARM M-profile maximum atomic width is 32).

### 2.3 Stack roots and frames

| Symbol | Signature | Must do | Eff. | Evidence |
|---|---|---|---|---|
| `EnterFrame` | `void(ObjHeader** start, int params, int count)` | `((FrameOverlay*)start)->previous = cur; cur = start; store params and count` | T | ContextUtils.kt:424; CodeGenerator.kt:1411-1413; mm/cpp/ShadowStack.cpp |
| `LeaveFrame` | same | `cur = frame->previous` | T | CodeGenerator.kt:1590-1596 |
| `SetCurrentFrame` | `void(ObjHeader** start)` | Restore `cur` in a landing pad. Intermediate frames are skipped when an exception unwinds through them. | T | CodeGenerator.kt:1023-1036 |
| `CheckCurrentFrame` | `void(ObjHeader** start)` | Debug assert, emitted only without `-opt` | T | CodeGenerator.kt:1182-1185 |

### 2.4 Safepoints and thread state

| Symbol | When emitted | Eff. | Evidence |
|---|---|---|---|
| `Kotlin_mm_safePointFunctionPrologue()` | Prologue of every generated function except trampolines and no-runtime functions; the redundant-safepoint pass deduplicates and inlines it | T (empty or GC poll) | CodeGenerator.kt:1416-1418; Bitcode.kt:129-138 |
| `Kotlin_mm_safePointWhileLoopBody()` | Every while/do-while (and lowered for) iteration | T | IrToBitcode.kt:1209, :1229 |
| `Kotlin_mm_switchThreadStateNative()` / `…Runnable()` (`…_debug` variants without `-opt`) | Around Kotlin→C bridges, at C→Kotlin bridge entry/exit, and for forceNativeThreadState functions | T (no-op) | ContextUtils.kt:451-462; IrToBitcode.kt:2536-2606; CodeGenerator.kt:1404-1410, :1457-1462 |
| `Kotlin_mm_checkStateAtExternalFunctionCall` | Only with `checkStateAtExternalCalls=true` | U | CheckExternalCalls.kt:54-55 |

### 2.5 Globals, thread-locals, initialization

| Symbol | Signature | Must do | Eff. | Evidence |
|---|---|---|---|---|
| `AppendToInitializersTail` | `void(InitNode*)` | Append to a linked list. Called from `.init_array` constructors that never touch the runtime. | T | IrToBitcode.kt:456-475; Runtime.cpp:168-176 |
| `Kotlin_initRuntimeIfNeeded` | `void()` | Once: heap init; walk the InitNode list with `init(0 /*ALLOC_TLS*/, mem)`, commit TLS, then `init(1 /*INIT_GLOBALS*/)`, then `init(2 /*INIT_TL*/)` | T to W | IrToBitcode.kt:379-425; Runtime.cpp:48-61, :83-116, :178-182 |
| `CallInitGlobalPossiblyLock` | `void(uintptr_t* state, void(*init)())` | States: 0 = not initialized, `1\|(tid<<2)` = initializing, 2 = done, 3 = failed. A recursive call from the same thread returns immediately. A throw from `init` sets 3 and wraps the exception. | T | IrToBitcode.kt:2348-2364; Runtime.cpp:328-355; RuntimePrivate.hpp:11-14 |
| `CallInitThreadLocal` | `void(uintptr_t volatile* g /*nullable*/, uintptr_t* l, void(*init)())` | Set `*l = 2`, then run `init` | T | IrToBitcode.kt:2366-2409; Runtime.cpp:357-370 |
| `AddTLSRecord` | `void(MemoryState*, void** key, int n)` | Reserve n reference slots for `key` (`&__KonanTlsKey`, internal to the module) | T | IrToBitcode.kt:416-421; ContextUtils.kt:589-594 |
| `LookupTLS` | `ObjHeader**(void** key, int idx)` | Return `&slots[idx]`. These slots are GC roots. | T | LlvmUtils.kt:210-215 |
| LLVM `thread_local` primitive globals | — | Created for `@ThreadLocal` primitive fields and for `state_thread_local$<file>`. Needs emulated TLS (`__emutls_get_address`), `__aeabi_read_tp` plus a TLS block, or stripping `thread_local` from the IR. | W-lite | LlvmUtils.kt:217-230; IrToBitcode.kt:686-692 |

### 2.6 Exceptions

| Symbol | Signature | Must do | Eff. | Evidence |
|---|---|---|---|---|
| `ThrowException` | `void(KRef) noreturn` | Either panic (the 1.3.70 Zephyr behaviour) or a real C++ throw of an `ExceptionObjHolder` | T (panic) / W (real) | CodeGenerator.kt:82-93; Exceptions.cpp:39-43; ARCH Exceptions.cpp:201-210 |
| `Kotlin_getExceptionObject` | `OBJ_GETTER(…, void* cxxObj)` | Unwrap the result of `__cxa_begin_catch` | U in panic mode | CodeGenerator.kt:1150-1165; Exceptions.cpp:110-112 |
| `__gxx_personality_v0` (varargs, nounwind) | — | Personality for every landing pad | stub / libsupc++ | ContextUtils.kt:596-612 |
| `__cxa_begin_catch`, `__cxa_end_catch`, `_ZSt9terminatev` | `void*(void*)`, `void()`, `void()` | Catch and terminate paths | stub / libsupc++ | ContextUtils.kt:601-625 |
| `_ZTI18ExceptionObjHolder` (global) | — | typeid compared in filtering landing pads (Kotlin→C bridges) | dummy / real RTTI | CodeGenerator.kt:1043-1106, :1464-1468 |
| Implicit: `_Unwind_Resume`, `__aeabi_unwind_cpp_pr0/1`, `.ARM.exidx` | — | From `resume` and EHABI tables | — | INFERRED (LLVM ARM EHABI) |

A `throw` inside a `try` in the same function becomes a direct jump, with no C++ EH (VERIFIED IrToBitcode.kt:1024-1033). Every call that may unwind inside a `try` is an `invoke` (CodeGenerator.kt:830-865).

**Panic-mode trick.** Declare `ThrowException` (and every runtime function) `nounwind` in our `compiler_interface.bc`. The compiler then emits `call` instead of `invoke` for it, because attributes are copied from the declaration (VERIFIED). After that, LTO function-attrs and simplifycfg can remove most landing pads (INFERRED). Indirect calls through vtables stay "may unwind", so some EH tables will remain (INFERRED).

### 2.7 Type checks and dispatch

| Symbol | Signature | Must do | Eff. | Evidence |
|---|---|---|---|---|
| `Kotlin_Any_getTypeInfo` | `const TypeInfo*(KConstRef)` | `((TypeInfo*)(hdr & ~3))->typeInfo_`. Indirect because the header may point to a meta-object whose first word is the TypeInfo. Used by every virtual call and type check. | T | CodeGenerator.kt:1257; Natives.cpp:110-112; Memory.h:73-78 |
| `IsSubtype` | `bool(const TypeInfo* obj, const TypeInfo* dst)` | Interface: scan `implementedInterfaces_`. Class: walk `superType_`. Used when GHA is off (no `-opt`). | T | CodeGenerator.kt:248-249; Types.cpp:23-37 |
| `IsSubclassFast` | `bool(const TypeInfo*, int32 lo, int32 hi)` | `lo <= classId_ <= hi` (with GHA) | T | CodeGenerator.kt:252-254; Types.cpp:39-42 |
| `LookupInterfaceTableRecord` | `const InterfaceTableRecord*(const InterfaceTableRecord* t, int size, int32 id)` | Search a sorted table; never returns null; the caller checks `.id`. This slow path runs only when `interfaceTableSize_ < 0`, or for every call when GHA is off. | T | CodeGenerator.kt:206-246; TypeInfo.cpp:30-47 |
| `Kotlin_processObjectInMark`, `Kotlin_processArrayInMark`, `Kotlin_processEmptyObjectInMark` | `void(void* state, ObjHeader*)` | Their addresses are stored in **every** TypeInfo, so all three must exist. Whether our GC uses them is up to us. | T | RTTIGenerator.kt:259-262, :484-496 |

Virtual calls go through compiler-generated trampolines named `<symbol>` that load `vtable = (void**)(typeInfo + 1)` or an itable record's `.vtable` (field 2), then call `<symbol>-impl`. The runtime is not involved. VERIFIED: CodeGenerator.kt:263-370.

### 2.8 Arrays, strings, boxing (codegen side)

| Symbol | Signature | Eff. | Evidence |
|---|---|---|---|
| `Kotlin_arrayGetElementAddress` / `Kotlin_intArrayGetElementAddress` / `Kotlin_longArrayGetElementAddress` | `KRef*/KInt*/KLong*(KRef arr, KInt i)` — atomic array intrinsics only | U unless atomic arrays are used | ContextUtils.kt:500-502; IntrinsicGenerator.kt:283-291 |
| `BOOLEAN/BYTE/SHORT/CHAR/INT/LONG_CACHE`, `*_RANGE_FROM/TO` | **Defined by the compiler** (constant permanent boxes). The runtime functions `in*BoxCache` / `getCached*Box` read them. | T | BK/Boxing.kt `initCache`; git:compiler/ir/backend.native/.../BoxCache.kt ("~20kb") |
| `theUnitInstance`, `theEmptyArray` | Defined by the compiler (permanent) | — | LlvmDeclarations.kt:37-40, :349-362 |
| `theAnyTypeInfo`, `theArrayTypeInfo`, `theStringTypeInfo`, `theThrowableTypeInfo`, `theUnitTypeInfo`, `the{Byte,Char,Short,Int,Long,Float,Double,Boolean}ArrayTypeInfo`, `theNativePtrArrayTypeInfo`, `theCleanerImplTypeInfo`, `theRegularWeakReferenceImplTypeInfo` | Compiler-defined `const TypeInfo*` variables (`@ExportTypeInfo`). The runtime may read them. | — | RTTIGenerator.kt:148-156; grep KT for `@ExportTypeInfo` |

### 2.9 Startup and entry point

| Symbol | Defined by | Contract | Evidence |
|---|---|---|---|
| `Konan_start` | Compiler (PROGRAM) | `int32_t Konan_start(KRef args /*Array<String>*/)`: `try { main(args?) ; return 0 } catch (e) { Kotlin_processUnhandledException(e); Kotlin_terminateWithUnhandledException(e) }` | BK/EntryPoint.kt:27-93 |
| `Konan_main` (`entryPointName`) | **Runtime `launcher.bc`** | Must exist for PROGRAM unless `-nomain`. The compiler adds `main` as an alias of it. | CompilerOutput.kt:229-239; NativeSecondStageCompilationConfig.kt:502-512 |
| `_Konan_constructors`, `_Konan_init_<module>` | Compiler | Put into `llvm.global_ctors` (priority 1). They only call `AppendToInitializersTail`. **The C startup must run `.init_array`.** | IrToBitcode.kt:2714-2838 |
| Stock launcher sequence | runtime | `Kotlin_initRuntimeIfNeeded(); Kotlin_mm_switchThreadStateRunnable(); Konan_start(args)` | RT/launcher/cpp/launcher.cpp:51-80 |

### 2.10 Globals the compiler defines (the runtime must not define them strongly)

- **Constants module:** `Kotlin_needDebugInfo`, `Kotlin_runtimeAssertsMode`, `Kotlin_disableMmap`, `Kotlin_runtimeLogsEnabled`, `Kotlin_concurrentWeakSweep`, `Kotlin_gcMarkSingleThreaded`, `Kotlin_fixedBlockPageSize`, `Kotlin_pagedAllocator`. VERIFIED IrToBitcode.kt:2891-2908, CompilerOutput.kt:202.
- **Overridable globals (final binary only):** `Kotlin_gcMutatorsCooperate`, `Kotlin_auxGCThreads`, `Kotlin_concurrentMarkMaxIterations`, `Kotlin_suspendFunctionsFromAnyThreadFromObjC`, `Kotlin_getSourceInfo_Function` (only if sourceInfoType≠noop), `Kotlin_CoreSymbolication_useOnlyKotlinImage`, `Kotlin_appStateTracking`, `Kotlin_objcDisposeOnMain`, `Kotlin_objcDisposeWithRunLoop`, `Kotlin_enableSafepointSignposts`, `Kotlin_globalDataLazyInit`, `Kotlin_swiftExport`, `Kotlin_latin1Strings`, `Kotlin_mmapTag`, `Kotlin_minidumpLocation`, `Kotlin_minidumpOnSIGTERM`, `Kotlin_runtimeLogs`. VERIFIED IrToBitcode.kt:2636-2684, NativeRuntimeOverridableConstants.kt:19-46.
- **Debug:** `Konan_debugOperationsList` must exist in `debug.bc` when building with `-g` and without `-opt`. Otherwise the compiler hits a NPE (`!!`). VERIFIED RTTIGenerator.kt:391-416.

### 2.11 Non-runtime symbols the generated code needs (from libc / compiler-rt / libgcc)

`memset` (from `llvm.memset`), `memcpy`; `__aeabi_ldivmod` / `__aeabi_uldivmod` (Long `/` `%`); soft-double `__aeabi_d*` (the FPU is single-precision only); `fmodf` / `fmod` (`frem`); 64-bit `__atomic_*`; `__stack_chk_*` only when `stackProtector≠no` (default no, NativeSecondStageCompilationConfig.kt:524-530). INFERRED (standard LLVM ARM lowering), except where a line is cited.

### 2.12 Runtime functions the stdlib calls (`@GCUnsafeCall` externals; needed once the calling stdlib function is reachable)

All 322 externals in KT use `@GCUnsafeCall`. There is no `@SymbolName` in the native stdlib (VERIFIED grep). Symbol = callee name. ABI: receiver first, then the Kotlin-mapped parameters; Boolean/Char are zeroext, Byte/Short signext (VERIFIED TargetAbiInfo.kt:29-101); object returns get the trailing `__result__` slot (LlvmFunctionPrototype.kt:121-136).

| Group | Symbols | Needed when | Eff. |
|---|---|---|---|
| Arrays (KT/kotlin/Arrays.kt, Array.kt, NativePtr.kt) | `Kotlin_{Byte,Char,Short,Int,Long,Float,Double,Boolean}Array_{get,set,getArrayLength}`, `Kotlin_Array_{get,set,getArrayLength}`, `Kotlin_NativePtrArray_{get,set,getArrayLength}`, and the compiler-generated `…_get_without_BoundCheck` / `…_set_without_BoundCheck` for every array class | Any array access (they must inline: provide them as bitcode). The bounds-checking versions call `ThrowArrayIndexOutOfBoundsException`. `Kotlin_Array_set` must apply `UpdateHeapRef` semantics. | T |
| Array utilities (collections/ArrayUtil.kt, ArrayIntrinsics.kt, TypedArrays.kt) | `Kotlin_*Array_fillImpl`, `Kotlin_*Array_copyImpl`, `Kotlin_emptyArray`, `Kotlin_ByteArray_{get,set}{Char,Short,Int,Long,Float,Double}At` | copyOf / fill / ByteArray views | T |
| String (String.kt, text/Strings.kt, StringBuilderNative.kt, CharNative.kt, Char.kt, StringNumberConversions.kt) | `Kotlin_String_{hashCode,get,subSequence,compareTo,getStringLength,plusImpl,equals,indexOfChar,indexOfString,lastIndexOfChar,replace,unsafeRangeEquals,toCharArray,unsafeStringFromCharArray,unsafeStringToUtf8,unsafeStringToUtf8OrThrow}`, `Kotlin_ByteArray_unsafeStringFromUtf8[OrThrow]`, `Kotlin_StringBuilder_{insertString,insertInt}`, `Kotlin_Char_{isHighSurrogate,isLowSurrogate,isISOControl,toString}`, `Kotlin_{Int,Long}_toStringRadix` | Any string operation, template or StringBuilder. Must handle the UTF-16 encoding, and Latin-1 too if `latin1Strings=true`. | W (moderate) |
| Number formatting / parsing (Primitives.kt, Numbers.kt, internal/NumberConverter.kt, FloatingPointParser.kt, HexStringParser.kt, time/DurationNative.kt) | `Kotlin_{Byte,Short,Int,Long}_toString`, `Kotlin_{Float,Double}_{toInt,toLong,isNaN,isInfinite}`, `Kotlin_{Int,Long}_count{OneBits,LeadingZeroBits,TrailingZeroBits}`, `Kotlin_native_NumberConverter_{bigIntDigitGeneratorInstImpl,ceil}`, `Kotlin_native_FloatingPointParser_parse{Double,Float}Impl`, `Kotlin_native_{int_bits_to_float,long_bits_to_double}`, `Kotlin_DurationValue_formatToExactDecimals` | `toString` / parsing of numbers | T (int), W (float/double) |
| Math (math/math.kt) | 68 `Kotlin_math_*` wrappers over libm | kotlin.math use | T (newlib libm) |
| Boxing (internal/Boxing.kt) | `getCached{Boolean,Byte,Char,Short,Int,Long}Box`, `in{…}BoxCache` | Any boxing. Returning `false` from all `in*BoxCache` drops the ~20 KB caches. | T |
| Type info / reflection (KClassImpl.kt, TypeInfoNames.kt, Utils.kt, reflect/KClassEx.kt) | `Kotlin_TypeInfo_{findAssociatedObject,isInstance,getPackageName,getRelativeName}`, `Kotlin_Any_getTypeInfo`, `Kotlin_internal_reflect_getObjectReferenceFields{Count,ByIndex}`, `Kotlin_native_internal_reflect_objCNameOrNull` | `::class`, names, `Any.toString` | T |
| Identity / runtime (native/Runtime.kt, internal/Undefined.kt, Debugging.kt) | `Kotlin_Any_hashCode` (address; non-moving GC), `Kotlin_processUnhandledException`, `Kotlin_terminateWithUnhandledException`, `Kotlin_native_internal_undefined`, `Kotlin_Debugging_{isPermanent,isStack}` | Always (`Konan_start` references the two exception ones) | T |
| Throwable (Throwable.kt) | `Kotlin_getCurrentStackTrace` (returns a `NativePtrArray`; an empty one is fine), `Kotlin_getStackTraceStrings` | Any exception construction / printing | T |
| Console (io/Console.kt) | `Kotlin_io_Console_{print,println,println0,printlnToStdErr,readLine,readlnOrNull}` | print/println | T (route to the board's console) |
| Time / process (system/Timing.kt, Process.kt, time/InstantNative.kt, uuid/UuidNative.kt) | `Kotlin_system_getSteadyTime{Millis,Micros,Nanos}`, `Kotlin_system_exitProcess`, `Kotlin_system_getSystemTimeNanos`, `Kotlin_Uuid_getRandomBytes` | Timing / Instant / Uuid | T |
| Platform (native/Platform.kt) | `Konan_Platform_{canAccessUnaligned,isLittleEndian,getOsFamily,getCpuArchitecture,isDebugBinary,getProgramName,getAvailableProcessors,getAvailableProcessorsEnv,getAllocator}` | Platform API | T |
| GC API (runtime/GC.kt, GCInfo.kt, Debugging.kt) | 25 `Kotlin_native_internal_GC_*` / `Kotlin_native_runtime_GC_MainThreadFinalizerProcessor_*`, `Kotlin_Internal_GC_GCInfoBuilder_Fill`, `Kotlin_native_runtime_Debugging_dumpMemory`, `Kotlin_Debugging_isThreadStateRunnable` | `GC.collect()` and similar | U / T |
| References / weak / cleaner (internal/ref/ExternalRCRef.kt, ref/WeakPrivate.kt) | `Kotlin_native_internal_ref_{create(Un)RetainedExternalRCRef,dispose,dereference[OrNull],retain,release}ExternalRCRef`, `Konan_getWeakReferenceImpl` | StableRef / WeakReference / Workers | U (W if used) |
| Threads / workers (concurrent/Internal.kt, internal/concurrent/Thread.kt, Monitor.kt, concurrent/MutableData.kt) | 16 `Kotlin_Worker_*`, `Kotlin_native_concurrent_{currentThreadId,startThreadImpl}`, `Kotlin_Monitor_*`, `Kotlin_CPointer_CopyMemory` | Worker / thread API | U |
| Regex (text/regex/DecompositionHelpers.kt) | `Kotlin_text_regex_*` (5) | Regex | U |
| Blob / SIMD (native/Blob.kt, simd.kt) | `Kotlin_ImmutableBlob_{toByteArray,asCPointerImpl}`, `Kotlin_Interop_Vector4{f,i32}_of` | Rare | U |
| Interop runtime (Interop/Runtime) | `Kotlin_interop_{malloc,free}`, `Kotlin_Arrays_get*AddressOfElement`, `Kotlin_CString_toKStringFromUtf8Impl`, `Kotlin_Interop_*`, and ObjC symbols (Apple only) | nativeHeap, pinning, CString | T |

### 2.13 Kotlin functions the C++ runtime calls (`@ExportForCppRuntime`)

These are roots for Kotlin-level DCE. They are always code-generated, but LLVM `internalize` + `globaldce` removes them unless our runtime references them. VERIFIED: DataFlowIR.kt:644-650, DevirtualizationAnalysis.kt:89 and :121. The LLVM removal is INFERRED.

- **Throwers (KT/kotlin/native/internal/RuntimeUtils.kt):** `ThrowNullPointerException`, `ThrowIndexOutOfBoundsException`, `ThrowArrayIndexOutOfBoundsException`, `ThrowClassCastException(Any, NativePtr)`, `ThrowTypeCastException`, `ThrowKotlinNothingValueException`, `ThrowInvalidReceiverTypeException`, `ThrowArithmeticException`, `ThrowNumberFormatException`, `ThrowOutOfMemoryError`, `ThrowIllegalArgumentException[WithMessage]`, `ThrowIllegalStateException[WithMessage]`, `ThrowNotImplementedError`, `ThrowCharacterCodingException`, `ThrowFileFailedToInitializeException`, `ThrowRuntimeException`.
- **Other RuntimeUtils.kt exports:** `PrintThrowable`, `ReportUnhandledException`, `Kotlin_runUnhandledExceptionHook`, `TheEmptyString`, `KonanObjectToUtf8Array`, `Kotlin_internal_executeAndRelease`.
- **Boxing.kt:** `Kotlin_box*` / `Kotlin_unbox*`.
- **Elsewhere:** Worker launchpads; `checkRangeIndexes`; `Kotlin_Throwable_getStackTrace`.
- **Codegen calls some throwers directly, not through the runtime:** `throwNullPointerException` / `throwClassCastException` / `throwTypeCastException` for casts (IrToBitcode.kt:1399-1426); `throwArithmeticException` for a non-constant integer `/` or `%` (IntrinsicGenerator.kt:644-650); `throwIndexOutOfBoundsException` (:652-657); `throwIllegalArgumentExceptionWithMessage` (IrToBitcode.kt:2505-2511).

---

## 3. Object layout and static data (item 2), ARM32

The ARM data layout `e-m:e-p:32:32-Fi8-i64:64-v128:64:128-a:0:32-n32-S64` is the same for `armv6kz-linux-gnueabihf` and `thumbv7em-none-eabihf` (INFERRED). The compiler computes every offset from the runtime's data layout (Runtime.kt:107-109).

| Struct | Fields (must match exactly) | Notes / evidence |
|---|---|---|
| `ObjHeader` | `TypeInfo* typeInfoOrMeta_` (4 B) | Low 2 bits: 00 heap, 01 permanent, 11 stack; mask `~3`. If the pointer differs from `ptr->typeInfo_`, the header points to a meta-object (ExtraObjectData; first word is `typeInfo_`). Only weak refs and ObjC create meta-objects. VERIFIED Memory.h:30-118; CodeGenerator.kt:46, :544-550; KotlinStaticData.kt:23-26; mm/cpp/ExtraObjectData.hpp:83-98 |
| `ArrayHeader` | `{ptr typeInfoOrMeta_, uint32 count_}` = 8 B | Data at `alignUp(8, elemSize)` = offset 8 for every element type. VERIFIED Memory.h:123-134; KObject.hpp:61-74 |
| `StringHeader` | `{ptr, uint32 count_, int32 hashCode_, uint16 flags_, char data_[]}` | Data at offset 14. `stringHeaderExtraSize` = 14 − 8 = 6 bytes, so `count_` = chars + 3. Flags: bit0 HASHCODE_IS_ZERO, bit1 IGNORE_LAST_BYTE, bits 12-15 encoding (0 UTF-16, 1 Latin-1). VERIFIED KString.h:28-67; Runtime.kt:114-116; KotlinStaticData.kt:46-70. The ARM32 numbers are INFERRED from the layout. |
| `TypeInfo` (no ObjC) | 0 `typeInfo_` (self), 1 `extendedInfo_`, 2 `unused_` (0), 3 `instanceSize_` (negative = array element size), 4 `superType_`, 5 `objOffsets_`, 6 `objOffsetsCount_` (Array: 1), 7 `implementedInterfaces_`, 8 `…Count_`, 9 `interfaceTableSize_` (≥0 = mask for fast path, <0 = −size sorted, −1 = none), 10 `interfaceTable_`, 11 `packageName_` (String), 12 `relativeName_` (String), 13 `flags_`, 14 `classId_`, 15 `associatedObjects`, 16 `processObjectInMark`, 17 `instanceAlignment_`. 72 B on ARM32 (INFERRED), followed by the vtable `void*[]`. | Fields 9 and 10 are read inline by codegen. Do **not** define `WritableTypeInfo`, or an extra field is emitted. VERIFIED TypeInfo.h:92-165; RTTIGenerator.kt:83-140, :199-277; CodeGenerator.kt:208-209, :281 |
| `InterfaceTableRecord` | `{int32 id, uint32 vtableSize, void* const* vtable}` | VERIFIED TypeInfo.h:80-84 |
| `AssociatedObjectTableRecord` | `{const TypeInfo* key, ObjHeader*(*fn)(ObjHeader**)}`, null-terminated | VERIFIED TypeInfo.h:22-25; RTTIGenerator.kt:465-482 |
| `ExtendedTypeInfo` | `{int32, int32*, uint8*, char**, int32, void**}` | Emitted only without `-opt`. VERIFIED RTTIGenerator.kt:418-463 |
| `FrameOverlay` | `{FrameOverlay* previous; int32 parameters; int32 count}` = 3 slots | The compiler uses `storeSize(FrameOverlay)/ptrSize`, so our runtime may shrink it (pointer-size multiple). VERIFIED Memory.h:272-277; CodeGenerator.kt:609-611 |
| `InitNode` | `{void(*init)(int32, MemoryState*), InitNode* next}` | VERIFIED IrToBitcode.kt:456-464 |

**Object bodies.** An object is `ObjHeader` followed by its fields, packed by size class (`packFields` defaults to true). Required alignment is always 8: `kObjectAlignment`, and over-alignment is rejected. VERIFIED: LlvmDeclarations.kt:95-136, :200-252, :272-274; Runtime.kt:119; NativeSecondStageCompilationConfig.kt:160-162.

**Static and permanent data** (KotlinStaticData.kt):
- **String literals:** constant, `unnamed_addr` globals laid out as `StringHeader + data`, with tag 01 added to the String TypeInfo pointer through a GEP of +1. `hashCode_` and `HASHCODE_IS_ZERO` are precomputed (:46-70), so a correct runtime never writes to a literal and **literals can live in flash**.
- **Constant arrays and objects:** `createConstKotlinArray` / `createConstKotlinObject` produce `{header|1, fields}` (:74-91).
- **Stateless `object` declarations:** become constant permanent objects (ObjectClassLowering.kt:126).
- **Units:** `theUnitInstance` / `theEmptyArray` (:93-103).
- **Per-class name strings:** every TypeInfo also carries `packageName` / `relativeName` strings (RTTIGenerator.kt:127-128, :583-613).

**Global and companion initialization (2.4.21 has no InitAndRegisterGlobal):**
1. A static field with a constant initializer (primitive, or a `final` reference to a constant) gets a static LLVM initializer and no code. VERIFIED StaticInitializersLowering.kt:120-124; IrToBitcode.kt:807-821.
2. Every other static field in a file or class is set in a synthetic `$init_global`. With lazy init (the default), a call to it is inserted at the start of every function without a dispatch receiver and every constructor in that container. VERIFIED StaticInitializersLowering.kt:186-206; NativeSecondStageCompilationConfig.kt:494-500.
3. Codegen turns that call into `if (state_global$file != 2) CallInitGlobalPossiblyLock(&state, init)` with an acquire load. VERIFIED IrToBitcode.kt:2348-2364, :678-684.
4. A reference field is passed to `RegisterGlobal(&field)` when it is first initialized. VERIFIED IrToBitcode.kt:1717-1719.
5. `object` and `companion`: a static field `<instance>` in the class or file. Initialization does `createUninitializedInstance` → store → `initInstance(ctor)`, which allows recursive reads; access goes through the getter. VERIFIED ObjectClassLowering.kt:107-150.
6. `@ThreadLocal` fields go through the `$init_thread_local` path (TLS slots or LLVM `thread_local`). `@EagerInitialization` fields, or `-Xir-property-lazy-initialization=disable`, run from `InitNode(INIT_GLOBALS)` at runtime init. VERIFIED StaticInitializersLowering.kt:55-61; IrToBitcode.kt:703-726, :387-425.

---

## 4. Roots, safepoints and thread-state switches (item 3)

**Frame layout.** In the prologue the function does `slots = alloca ptr[slotCount]` and zeroes it with memset when it has slots. `slots[0..2]` holds the `FrameOverlay`. Next come object-typed parameter mirrors (`skipSlots`, only with debug info). Then come object locals, anonymous result slots, and stack-object root slots. `EnterFrame(slots, skipSlots, slotCount)` runs in the prologue; `LeaveFrame` runs on every return and in cleanup landing pads. VERIFIED CodeGenerator.kt:671-697, :1347-1421, :1580-1596; VariableManager.kt:60-122.

**GC scanning range.** A precise GC scans `[slots + 3 + params, slots + count)` of every frame in the chain, then the TLS slots, `RegisterGlobal` locations, and stable refs. VERIFIED mm/cpp/ShadowStack.hpp:49-53, RootSet.cpp.

**Why rooting through slots is complete:**
- Object-returning calls always write a caller slot (`__result__`).
- Reads of `var` fields are copied into a slot.
- Parameters are rooted by the caller.
- Values read from `val` fields are reachable through their rooted holder.

VERIFIED for the code paths: CodeGenerator.kt:716-734, :795-828. INFERRED that this is complete for a GC that runs only at calls.

**Stack objects.** These are `alloca` objects tagged `|3`, each with a root slot in the frame. The GC must trace their fields. VERIFIED CodeGenerator.kt:415-501.

**Safepoints:**
- Every function prologue, except trampolines and functions generated without runtime support (constructors/`.init_array` code). VERIFIED CodeGenerator.kt:174-193, :360, :1416-1418.
- Every loop iteration (IrToBitcode.kt:1209, :1229).
- The redundant-safepoint pass removes duplicates and inlines the remaining ones when `inlineForPerformance` is on. VERIFIED Bitcode.kt:129-138; ConfigChecks.kt:38.

**Kotlin→C** (cinterop `KOTLIN_TO_C_BRIDGE`, `@ImportedBridge`, forceNativeThreadState):
1. `switchThreadStateNative()`
2. `invoke` the C function with a filtering landing pad. Mode TERMINATE: a Kotlin exception is rethrown via `ThrowException`; anything else calls `__cxa_begin_catch` and then `std::terminate`.
3. `switchThreadStateRunnable()`

VERIFIED IrToBitcode.kt:2536-2613; CodeGenerator.kt:1043-1124.

**C→Kotlin** (`staticCFunction` bridges, `@ExportedBridge`):
- Entry: `Kotlin_initRuntimeIfNeeded()`, then `switchThreadStateRunnable()`, then a forced `EnterFrame` plus a cleanup landing pad.
- Exit, and inside the landing pad: `LeaveFrame`, then `switchThreadStateNative()`.

VERIFIED CodeGenerator.kt:107-135, :621-626, :1404-1410, :1457-1462.

**Calling C without bridges.** `@GCUnsafeCall` externals are plain direct calls with no state switch. They are the cheapest way to reach C code, but the opt-in marker `InternalForKotlinNative` is `internal` (KT/kotlin/native/internal/Annotations.kt:132-147). Whether `-opt-in=kotlin.native.internal.InternalForKotlinNative` is accepted from user code is INFERRED / not tested.

---

## 5. Options that change what the runtime must provide (item 4)

### 5.1 Command-line arguments (git:compiler/cli/cli-base/gen/.../K2NativeCompilerArguments.kt)

| Option | Effect on the runtime contract | Evidence |
|---|---|---|
| `-target linux_arm32_hfp` | Selects the module list (adds libbacktrace modules), hard-float, `__gxx_personality_v0`, `supports64BitMulOverflow=false` | CompilerOutput.kt:165-171; KonanTargetExtenstions.kt |
| `-produce program\|static\|dynamic\|framework\|library\|bitcode` | program: launcher + `Konan_start` + `main` alias. static/dynamic: C API adapter compiled by clang (`cInterfaceMode` V1 by default) plus llvm-ar. **bitcode: error.** | CompilerOutput.kt:117-119; NativeSecondStageCompilationConfig.kt:703-710; NativeCompilerDriver.kt:45; Linker.kt (git:native/utils) :34-37 |
| `-opt` | Enables DFG, devirtualization, DCE (vtable entries of unreferenced methods are nulled), GHA (`IsSubclassFast`, fast itables), escape analysis (stack objects), no ExtendedTypeInfo, non-`_debug` switch functions | TopLevelPhases.kt:522-543; RTTIGenerator.kt:284-295, :420-421; ContextUtils.kt:451-462 |
| `-g` | Adds `debug.bc` (`Konan_debugOperationsList`), DWARF, `linkRuntime=Optimize` by default, `frame-pointer=all` without `-opt` | CompilerOutput.kt:132; RTTIGenerator.kt:391-416; NativeSecondStageCompilationConfig.kt:484-488; LlvmAttributes.kt:37-48 |
| `-Xruntime=<file>` | Replaces **only** `compiler_interface.bc` (types, triple, data layout, imported declarations and their attributes) | RuntimeModulesConfig.kt:22-29; SetupConfiguration.kt:74 |
| `-Xallocator=std\|custom` | Chooses `legacy_alloc` + `std_alloc` vs `custom_alloc` (mimalloc is an error) | SetupConfiguration.kt:276-292; CompilerOutput.kt:172-180 |
| `-Xgc=` (deprecated) | noop / stms / cms (cms maps to PMCS) | SetupConfiguration.kt:229-252 |
| `-Xtemporary-files-dir=D` | Keeps `D/out.bc` (after LTO, runtime merged) and `D/<name>.o` | TopLevelPhases.kt:196, :403; git:native/utils/.../TempFiles.kt |
| `-Xdisable-phases=ObjectFiles,Linker` (common argument) | Stops after `out.bc`; no target clang or linker runs | git:compiler/cli/.../createPhaseConfig.kt; PhaseBuilders.kt:84-98 |
| `-Xsave-llvm-ir-after=<Phase>` + `-Xsave-llvm-ir-directory` | Writes `out.<Phase>.ll`. **`CStubs` = Kotlin code only, runtime as `declare`s** (step 2 of the plan). Also useful: `LinkBitcodeDependencies` (runtime merged, before LTO) and `LTOBitcodeOptimization`. | Bitcode.kt:140-150; LlvmPassesUtilities.kt:35-50; TopLevelPhases.kt:88 |
| `-Xoverride-konan-properties=k=v;…` | `targetCpu.<t>`, `targetCpuFeatures.<t>`, `llvmInlineThreshold`, `clangFlags.<t>`, linker entries | SetupConfiguration.kt:503-519; NativeSecondStageCompilationConfig.kt:55-87 |
| `-Xoverride-clang-options=a,b,…` | Replaces the whole ObjectFiles clang command line (no `-triple` is added for you) | BitcodeCompiler.kt:48-72 |
| `-Xllvm-module-passes` / `-Xllvm-lto-passes` | Replace the LLVM pipelines | OptimizationPipeline.kt:345-367 |
| `-nomain` | No `main` alias, so `Konan_main` is not required. `Konan_start` is still generated. | CompilerOutput.kt:229-239 |
| `-native-library x.bc` | Links extra bitcode into the module before LTO. Clashes with the stock runtime, so it cannot replace it. | CompilerOutput.kt:116 |
| `-Xcompile-from-bitcode` + `-Xread-dependencies-from` | Re-runs post-processing (LTO) and link on a given `.bc` | NativeCompilerDriver.kt:118-135 |
| `-Xir-property-lazy-initialization=disable` | Eager globals through INIT_GLOBALS (deprecated) | NativeSecondStageCompilationConfig.kt:494-500 |
| `-Xbackend-threads`, `-Xverify-bitcode`, `-Xprint-bitcode` | Tooling only | — |

### 5.2 `-Xbinary=` keys (git:native/binary-options/.../BinaryOptions.kt:15-137)

| Key | Effect |
|---|---|
| `gc=noop\|stwms\|pmcs\|cms` (default cms), `gcSchedulerType=manual\|adaptive\|aggressive` | **Only pick the runtime file names.** Codegen never inlines barriers; every reference store calls `UpdateHeapRef`. VERIFIED CompilerOutput.kt:145-164; grep shows no other `config.gc` use. |
| `allocator` / `pagedAllocator`, `checkStateAtExternalCalls`, `linkRuntime=Raw\|Optimize`, `minidumpLocation` | Module selection (plus extra calls for checkStateAtExternalCalls) |
| `smallBinary` | Oz, and `inlineForPerformance=false` (no `performance_inline`, no safepoint inlining) |
| `latin1Strings` | Literals encoded as Latin-1 where possible; **the runtime must then support both encodings** |
| `packFields` (default true) | Field layout |
| `genericSafeCasts` (default `!opt`) | Extra casts and bridges |
| `sourceInfoType` (default noop on Linux) | `Kotlin_getSourceInfo_*` |
| `stackProtector` | `ssp` attributes, needs `__stack_chk_*` |
| `escapeAnalysisPropagateExiledToHeapObjects` (default true) | Avoids heap→stack references |
| `preCodegenInlineThreshold` | Pre-codegen inliner |
| `cCallMode` (default IndirectOrDirect) | Direct avoids the C stubs that clang compiles with the Linux sysroot |
| `cInterfaceMode=none` | Needed for static/dynamic without the C++ adapter |
| `forceNativeThreadStateForFunctions` | Thread-state switches around listed functions |
| `runtimeAssertionsMode`, `gcMarkSingleThreaded`, `fixedBlockPageSize`, `concurrentWeakSweep`, `concurrentMarkMaxIterations`, `gcMutatorsCooperate`, `auxGCThreads`, `disableMmap`, `mmapTag`, `globalDataLazyInit`, `appStateTracking`, `enableSafepointSignposts`, `swiftExport`, `minidumpOnSIGTERM` | Only set constant or overridable globals; our runtime can ignore them |
| `memoryModel` (only experimental), `freezing` (only Disabled) | Deprecated |
| `objcExport*`, `bundle*`, `macabi`, `compileBitcodeWithXcodeLlvm`, `objcDispose*`, `unitSuspendFunctionObjCExport`, `dumpObjcSelectorToSignatureMapping`, `coreSymbolicationImageListType`, `androidProgramType`, `enableDebugTransparentStepping`, `debugCompilationDir`, `sanitizer`, `perFileCacheForStdlib`, `enableReleaseBinaryCache`, `runLLVMPassesInCompiler`, `stripDebugInfoFromNativeLibs` | Not relevant here |

### 5.3 Answers

**(a) Bitcode without the stock runtime.**
1. Copy DIST to `D2`. In `D2/konan/targets/linux_arm32_hfp/native/`, replace every file the compiler opens with ours. Our real code lives in `runtime.bc` and `launcher.bc`; the rest are empty modules with the same triple: `compiler_interface.bc`, `runtime.bc`, `mm.bc`, `common_alloc.bc`, `common_gc.bc`, `common_gcScheduler.bc`, `noop_crashHandler.bc`, `manual_gcScheduler.bc`, `noop_gc.bc`, `source_info_libbacktrace.bc`, `libbacktrace.bc`, `custom_alloc.bc`, `noop_externalCallsChecker.bc`, `launcher.bc`, plus `debug.bc` if `-g`.
2. Run `D2/bin/kotlinc-native.bat -Dkonan.home=D2 -target linux_arm32_hfp -opt -nomain -Xbinary=gc=noop -Xoverride-konan-properties="targetCpu.linux_arm32_hfp=cortex-m4;targetCpuFeatures.linux_arm32_hfp=<exact string our clang puts on runtime functions>" -Xtemporary-files-dir=D -Xdisable-phases=ObjectFiles,Linker`.
3. Compile `D/out.bc` ourselves with `clang -cc1 -triple thumbv7em-none-eabihf … -mrelocation-model static -ffunction-sections`, then link with arm-none-eabi-ld.
- VERIFIED: the script passes `-D` through and puts it after its own `-Dkonan.home` (bin/run_konan.bat:31-34, :65-73); the property is read by git:compiler/util/.../KotlinNativePaths.kt.
- INFERRED: the JVM takes the last `-D` value; the feature string must match exactly for runtime functions to inline into Kotlin code.
- For measurement only, the stock distribution plus `-Xsave-llvm-ir-after=CStubs,LTOBitcodeOptimization` is enough.

**(b) Keep the stdlib, drop threads and workers.** There is no flag for this.
- Threads, workers, GC threads and the TLS registry live entirely in the C++ runtime that we replace.
- The Kotlin Worker and Thread APIs pull `Kotlin_Worker_*` only when reachable (with `-opt` DCE).
- What remains thread-shaped in generated code: the thread-state switches and safepoints (no-ops for us), TLS (`AddTLSRecord` / `LookupTLS` / LLVM `thread_local`), and atomics (single core, fine).
- `Lock` (used by `lazy`) spins with CAS, which is correct single-threaded (KT/kotlin/native/concurrent/Lock.kt).

**(c) Shrink the output.**
- `-opt` (essential).
- `-Xbinary=smallBinary=true`, `latin1Strings=true` (needs Latin-1 support in the runtime string code), `gc=noop` for the module choice; leave `packFields` at its default true and `sourceInfoType` at noop; no `-g`.
- Optionally `-Xllvm-lto-passes`.
- Runtime-side choices:
  - return false from `in*BoxCache`, which removes about 20 KB of box caches (BoxCache.kt)
  - exception panic mode with nounwind declarations
  - don't call the Kotlin `Report*` / `PrintThrowable` functions from the runtime
  - avoid `Any.toString`, KClass names and `printStackTrace`
- TypeInfo name strings cannot be turned off; only a post-LTO bitcode pass could remove them (INFERRED).

---

## 6. Stdlib code a tiny program always pulls in (item 5)

| Item | Why | Evidence |
|---|---|---|
| `Konan_start` + try/catch landing pad + `Kotlin_processUnhandledException` / `Kotlin_terminateWithUnhandledException` | Generated for every PROGRAM | EntryPoint.kt:27-93 |
| The `launcher.bc` entry (`Konan_main` unless `-nomain`) | Alias check | CompilerOutput.kt:229-239 |
| TypeInfo + vtable + 2 name strings for every class instantiated or type-checked; Unit / Any / String / Array TypeInfos; `theUnitInstance` | RTTI | RTTIGenerator.kt:199-277; LlvmDeclarations.kt:327-362 |
| About 80 `@ExportForCppRuntime` functions (throwers, Report/Print, box/unbox, worker launchpads, ObjC helpers) | DCE roots: compiled, then removed by LLVM DCE unless our runtime references them (INFERRED) | DataFlowIR.kt:644-650; DevirtualizationAnalysis.kt:89, :121 |
| `$init_global` of every reachable file with non-constant globals, plus a `CallInitGlobalPossiblyLock` guard per function | Lazy init | §3 |
| Throw paths inserted by codegen: NPE (`!!`, casts), ClassCastException (message built from `KClass` names and a string template, so StringBuilder), ArithmeticException (every non-constant integer `/` or `%`), IndexOutOfBounds | Codegen | IrToBitcode.kt:1399-1426; IntrinsicGenerator.kt:644-657; RuntimeUtils.kt |
| Any exception object: `Throwable.<init>` calls `Kotlin_getCurrentStackTrace` and `by lazy` (SynchronizedLazyImpl: 2 AtomicReference + `Lock`; `Lock.lock()` reads the `@ThreadLocal object CurrentThread`, so TLS) | Throwable fields | KT/kotlin/Throwable.kt (`stackTrace`, `stackTraceStrings by lazy`); KT/kotlin/Lazy.kt:22; KT/kotlin/native/concurrent/Lazy.kt:62-90; Lock.kt |
| `println` → `Kotlin_io_Console_println`; string templates → StringBuilder (`insertString`, `insertInt`, `unsafeStringFromCharArray`); Double → NumberConverter (Kotlin) + `bigIntDigitGeneratorInstImpl` | Only when used | §2.12 |
| Workers, GC API, regex, weak refs | Not pulled unless used | §2.12 |

---

## 7. What the Zephyr target did (ARCH v1.3.70), as a baseline

| Aspect | 1.3.70 `zephyr_stm32f4_disco` | Evidence |
|---|---|---|
| Target | `armv7m-none-eabi`, `-mthumb`, cpu cortex-m4, abi aapcs, gcc-arm-none-eabi 7 toolchain | ARCH konan/platforms/zephyr/stm32f4_disco |
| Runtime build | Defines `KONAN_ZEPHYR`, `NO_FFI`, `NO_THREADS`, `NO_EXCEPTIONS`, `NO_MATH`, `INTERNAL_SNPRINTF`, `INTERNAL_NOW`, `NO_MEMMEM`, `NO_CTORS_SECTION`, `NO_UNALIGNED_ACCESS`; flags `-fno-rtti -fno-exceptions -fno-asynchronous-unwind-tables -fno-pie -fno-pic -fshort-enums` | ARCH shared/.../ClangArgs.kt (zephyr branches) |
| Exceptions | `ThrowException` = `PrintThrowable` + abort; libsupc++ linked only for the personality | ARCH runtime Exceptions.cpp:201-210; samples/zephyr/CMakeLists.txt |
| TLS | `LLVMNotThreadLocal` for Zephyr | ARCH llvm/ContextUtils.kt:492-496 |
| Constructors | `_Konan_constructors` external and in `llvm.used` "if .ctors is not available (WASM, embedded)" | ARCH llvm/IrToBitcode.kt:2489-2511 |
| Build | `konanc -target zephyr_stm32f4_disco -opt -g`; Zephyr CMake linked `program.o` | ARCH samples/zephyr/build.sh; commits eb0e6a8f11, 767515cdcc |

---

## 8. Not verified when this was written

The first two items belong to the copied-distribution route, which kmicro did not take. The feature string is now
the one clang gives Cortex-M4 code ([toolchain/retarget.py](../../toolchain/retarget.py)), and kmicro keeps the
exception tables (real exceptions, R_eh.md option (b)).

- That `-Xdisable-phases` matches phase names exactly (only the `PhaseSet.Enum(names)` construction was read).
- That a later `-Dkonan.home` overrides the script's own value; it depends on JVM last-wins behaviour.
- The exact `targetCpuFeatures` string and float-ABI behaviour for `thumbv7em-none-eabihf` in the Kotlin LLVM 21 fork.
- How far LTO removes EH tables in panic mode.
- Whether `@ThreadLocal` is used in the common stdlib sources; `libraries/stdlib` is not checked out, and only KT was grepped.
- Observed but not explained: the prebuilt stdlib manifest says `compiler_version=2.4.20-dev-7885` inside the 2.4.21 distribution.
# kmicro: memory management and coroutines for Kotlin/Native 2.4.21 on a bare-metal STM32L431

> **Status.** The collector of §3 became [runtime/mm.c](../../runtime/mm.c), whose header comment describes it as
> it is. The main differences: the heap is `KM_HEAP_BYTES`, 16 KB by default; free blocks go to 8 exact-size lists
> and one list for larger blocks, with no bump region (blocks of 256 bytes or more come from the top of the heap,
> smaller ones from the bottom); the mark stack and the globals table are larger; there is no idle-time collection;
> when an allocation fails even after a collection, the runtime reports the heap state and stops with a panic; and
> `KM_GC_STRESS` collects before every allocation and fills freed blocks with a pattern instead of running a heap
> walk. Coroutines work as §4.1-4.2 describe. The dispatcher of §4.3 and the sleep loop of §4.5 were not built: C
> calls Kotlin functions directly (design-plan.md, D6), and examples/selftest resumes a coroutine from C.

Abbreviations: `K/` = `kotlin-native/` in the github.com/JetBrains/kotlin repository at tag v2.4.21, `BE/` = `K/backend.native/compiler/ir/backend.native/src/org/jetbrains/kotlin/backend/konan/`, `RT/` = `K/runtime/src/`, `ARC/` = the archived github.com/JetBrains/kotlin-native repository (tag v1.3.70), `DIST/` = the Kotlin/Native 2.4.21 prebuilt distribution for Windows. Files outside the checked-out folders were read with `git show` at v2.4.21.

## 0. Decisions in one screen

1. **Collector.** A precise, non-moving, stop-the-world mark-sweep that runs on the caller's own thread and never inside an interrupt.
   - Roots: shadow-stack frames, registered globals, the thread-local object slots, a small stable-reference table, exceptions in flight, and the root slots of stack-allocated objects.
   - The compiler's code does not depend on which GC is chosen. Every barrier is a call into the runtime, so a single-threaded collector makes every barrier a plain store.
2. **No moving or compacting collector.** Objects are held only in compiler SSA values (registers) across allocation points, raw interior pointers are passed to C, and the identity hash is the object's address. Section 1.5 has the evidence.
3. **Heap.** 12–16 KB, in 8-byte granules, with no per-object header.
   - The mark bit is bit 1 of the object's existing type-info word, which is free in heap objects.
   - Free blocks carry a tag in bit 0.
   - Allocation uses segregated free lists plus a bump region at the top of the heap; the sweep walks the heap linearly and coalesces.
   - Metadata is about 0.8 KB of RAM; the code is about 2.5–3 KB of flash.
4. **Finalizers, Cleaners and WeakReference are rejected in v1**, with checks at allocation time and at link time. Only two classes in the whole standard library have finalizers.
5. **Coroutines need no special runtime support** beyond allocation, roots and C++ exception tables. A minimal dispatcher (fixed arrays, no `ContinuationInterceptor`, `suspendCoroutineUninterceptedOrReturn`) allocates nothing per wait.
   - The C main loop stays in charge: it calls the exported `kmicro_step()`.
   - When every coroutine is suspended, `kmicro_step()` returns the next deadline and the C firmware chooses Sleep or Stop 1.
6. **Hard risks:**
   - `thread_local` appears in generated code in practice: `Throwable` → `lazy` → `Lock` → a `@ThreadLocal` object.
   - The 64-bit atomics helper functions (`__atomic_*_8`) are missing from libgcc and must be provided.
   - The distribution's 32-bit ARM target enables double-precision VFP, which the Cortex-M4 does not have; the per-function CPU and feature attributes must be rewritten before code generation.
   - Escape analysis may put up to 64 KB of arrays on the C stack per function, against a stack of a few KB.
   - A typical bare-metal start-up never runs `.init_array`.

---

## 1. How the stock memory manager finds roots, and what the compiler guarantees

### 1.1 Object layout and tags (32-bit)
- **Object header.** One word, `TypeInfo* typeInfoOrMeta_`, with tag bits in the low two bits: HEAP=0, PERMANENT=1, STACK=3, mask=3. Tag value 2 is unused. VERIFIED `RT/main/cpp/Memory.h:30-46`. `type_info()` clears the tag bits (`Memory.h:73-78`).
- **Arrays.** Header word plus `uint32 count_` (`Memory.h:121-133`).
- **Object size.** For a plain object, size = `instanceSize_`, header included. For an array, size = `AlignUp(AlignUp(8, elemAlign) + (-instanceSize_)*count, 8)`. VERIFIED `RT/main/cpp/KObject.hpp:29,76`.
- **Alignment.** `kObjectAlignment = 8` (`RT/main/cpp/Alignment.hpp:15`) must match the compiler's `objectAlignment = 8` (`BE/llvm/Runtime.kt:118-119`).
- **Reference fields.** Found through `TypeInfo.objOffsets_/objOffsetsCount_`. `kotlin.Array` has count 1 only as a marker and must be detected by `typeInfo == theArrayTypeInfo`. VERIFIED `RT/main/cpp/TypeInfo.h:103-107`, `RT/mm/cpp/ObjectTraversal.hpp:39-54`.
- **Type info is read through the runtime.** Generated code reads type info by calling `Kotlin_Any_getTypeInfo` (`BE/llvm/CodeGenerator.kt:1257`, `BE/llvm/ContextUtils.kt:431`). Our runtime therefore controls header decoding: it must mask `&~3`. VERIFIED.
- **TypeInfo and permanent objects are constants in flash:**
  - TypeInfo: `setConstant(true)`, `BE/llvm/RTTIGenerator.kt:274,570`.
  - String literals, constant arrays, constant objects, `Unit` and the empty array are LLVM `constant` globals with tag 1: `BE/llvm/KotlinStaticData.kt:24-44,93-103`.
  - Their fields can only point to other constants. VERIFIED that they are constant; that the fields cannot reach the heap is INFERRED, but LLVM does not allow a constant initializer to point at runtime data.
  - The box caches are also constant arrays: `BE/Boxing.kt:164-188`.

### 1.2 Shadow-stack frames: what the compiler puts in slots
- **Frame format.** `FrameOverlay {previous; int32 parameters; int32 count}` is 12 bytes, i.e. 3 slots on 32-bit (`Memory.h:272-277`). The compiler takes this layout from the runtime bitcode's type (`BE/llvm/CodeGenerator.kt:609-611`). A slot array is allocated with `alloca ptr, slotCount`; the overlay sits at slots 0–2. VERIFIED `CodeGenerator.kt:1351-1352`.
- **Prologue.** The slots are zeroed with `memset`, then `EnterFrame(slots, skipSlots, slotCount)` is called, then `Kotlin_mm_safePointFunctionPrologue`. VERIFIED `CodeGenerator.kt:1355-1359,1411-1418`. The GC therefore never sees uninitialized slots.
- **When a frame is entered.** Only if the function has at least one object slot beyond its parameters (`needSlots`), or needs a cleanup landing pad (exported or bridge functions, or `switchToRunnable`). VERIFIED `CodeGenerator.kt:621-626,1580-1588`.
- **What lives in a slot (object-typed only, `alloca(isObjectType=true)`):**
  - Every `var` local. In debug (`-g`) builds, every local (`BE/llvm/VariableManager.kt:60-71`).
  - The **result slot of every call that returns an object**. Each call site gets its own anonymous slot, so the callee writes its result into the caller's frame through the trailing `ObjHeader**` argument (`OBJ_GETTER`). VERIFIED `CodeGenerator.kt:795-828`, `Memory.h:147-160`.
  - Every load of a **non-final** field, copied into a fresh slot. VERIFIED `CodeGenerator.kt:716-734` (`isVar`), `BE/llvm/IrToBitcode.kt:1657-1665` (`!isFinal`).
  - One root slot per stack-allocated object (escape analysis). VERIFIED `CodeGenerator.kt:412-438,472-500`.
  - Parameters are copied to slots only in debug builds. They are counted in `skipSlots` and **skipped** by the GC iterator, because the caller already roots them. VERIFIED `VariableManager.kt:89-103`, `IrToBitcode.kt:579-585`, `RT/mm/cpp/ShadowStack.hpp:49-53`.
- **What is held only in SSA values (registers / C stack), with no slot of its own:**
  - Release-build `val` locals: `ValueRecord` (`VariableManager.kt:43-48,63-64`).
  - Release-build parameters: `createParameter` → immutable.
  - Loads of final fields.
  - The SSA copy of every call or allocation result; the slot holds a second copy, but the code keeps using the SSA value.
- **Return.** `UpdateReturnRef(returnSlot, value)` is called **before** `LeaveFrame`. VERIFIED `CodeGenerator.kt:1432-1455,1590-1596`.
- **Exceptions.** Ordinary functions have no cleanup landing pad and do *not* call `LeaveFrame` while unwinding. Every catch or finally landing pad first calls `SetCurrentFrame(own slots)`, which pops all the dead frames at once. VERIFIED `CodeGenerator.kt:1023-1037`. `CheckCurrentFrame` is emitted only in non-optimized builds (`CodeGenerator.kt:1182-1185`).
- **Slots are never reused within a function.** Each call site and each load site gets a new slot, so dead temporaries stay rooted until the function returns. VERIFIED `CodeGenerator.kt:671-681` (slotCount only grows). Consequence: a never-returning Kotlin function, such as a run loop, keeps its last temporaries alive. Keep loop bodies in helper functions.

### 1.3 Other root sources (stock)
| Source | Stock implementation | Evidence (VERIFIED) |
|---|---|---|
| Stack frames + thread-local object slots | `ThreadRootSet` = shadow stack, then TLS | `RT/mm/cpp/RootSet.hpp` (ThreadRootSet), `RootSet.cpp` |
| Globals | `RegisterGlobal(ObjHeader**)` → `GlobalsRegistry` queue | `RT/mm/cpp/Memory.cpp:118-122`, `GlobalsRegistry.cpp` |
| Stable/"special" refs | `ExternalRCRef` registry; rc>0 = root, rc=0 = weak | `RT/mm/cpp/ExternalRCRefRegistry.hpp` header comment, `MarkAndSweepUtils.hpp:132-147` |
| Exception in flight | `ExceptionObjHolderImpl` owns an `OwningExternalRCRef` | `RT/mm/cpp/ExceptionObjHolder.cpp:19-34` |
| Stack/permanent objects | `collectRoot`: heap → enqueue; otherwise `processInMark` on the spot | `RT/gc/common/cpp/MarkAndSweepUtils.hpp:59-72` |
| Field scan | enqueue only if `field->heap()` | `MarkAndSweepUtils.hpp:28-39` |

**Which globals get registered.** Every non-constant reference static field gets an `INITIALIZE_GLOBAL_FIELD` store, even when it is initialized to null, and that store calls `RegisterGlobal`. This happens lazily, when the file's initializer runs. Final fields initialized to a constant are skipped because they point to flash constants. VERIFIED `BE/lower/StaticInitializersLowering.kt:104-143`, `IrToBitcode.kt:1717-1719`.

**Thread-local object fields** live in runtime TLS storage reached through `LookupTLS(key, idx)`; the size is reserved via `AddTLSRecord` in the init node's `ALLOC_THREAD_LOCAL_GLOBALS` pass. VERIFIED `IrToBitcode.kt:416-421`, `BE/llvm/LlvmUtils.kt:210-221`, `RT/mm/cpp/ThreadLocalStorage.cpp:11-55`.

The `initializingSingletons_` vector in `ThreadData` is declared but never read anywhere. VERIFIED by grep (only `ThreadData.hpp:56,87`).

### 1.4 Why a precise non-moving collector is sound here
Every object value in SSA traces back to one of three things:
- a slot in the current frame (call result, allocation result, or a var-field copy);
- a caller's slot (parameters);
- an object that is itself reachable and whose *final* field cannot change after construction.

This is the same invariant the stock collectors rely on. They stop other threads at any safepoint, including every function prologue, so roots must be complete at every call boundary (stms marks only shadow stack, TLS, globals and stable refs: `MarkAndSweepUtils.hpp:113-160`, `RT/gc/stms/cpp/SingleThreadMark.hpp:18-22`). kmicro collects only inside `AllocInstance`, `AllocArrayInstance` and `GC.collect()`, which is a subset of call boundaries. VERIFIED that the pieces exist; the conclusion is INFERRED.

**Obligation on our own C runtime code:** any runtime function that allocates while holding Kotlin references must root them in a frame (the `ObjHolder` pattern, `Memory.h:279-311`), and must return objects through the result slot (`RETURN_OBJ`).

### 1.5 Is a moving compactor possible? No.
- **Values held only in registers across allocations.** In release builds, vals and parameters are SSA (`VariableManager.kt:63-64`, `IrToBitcode.kt:584`). `evaluateSetField` evaluates the receiver, then the value (which may allocate), and only then computes the field address from the receiver's SSA pointer. VERIFIED `IrToBitcode.kt:1701-1711`. A move would leave stale pointers.
- **Interior pointers passed to C.** `Pinned` is only a field that keeps the object alive (`K/Interop/Runtime/src/native/kotlin/kotlinx/cinterop/Pinning.kt:12-17`); `addressOf` and `refTo` pass raw element addresses into C (`Pinning.kt:43,115-122`). The atomic-array intrinsics use `Kotlin_arrayGetElementAddress` (`BE/llvm/IntrinsicGenerator.kt:283-292`). VERIFIED.
- **Identity hash is the address.** `Kotlin_Any_hashCode` returns `(uintptr_t)thiz` (`RT/main/cpp/Natives.cpp:40-48`). Moving would break HashMap keys that rely on identity. VERIFIED.
- **Allocator page sizes.** The stock "custom" allocator uses 256 KB NextFit pages (`RT/alloc/custom/cpp/NextFitPage.hpp:26`), larger than all of SRAM. VERIFIED.
- **The only escape route** would be a mostly-copying (Bartlett-style) collector: scan the main stack conservatively and pin whatever it references, plus add per-object hash storage. That costs RAM and complexity for little gain. Rejected. INFERRED.
- **Mitigating fragmentation instead:** size-segregated lists, allocating long-lived Kotlin structures at start-up, and keeping large buffers in C static memory.

---

## 2. Barriers and hooks the compiler emits, and what kmicro does for each

The compiler-facing list is `RT/compiler_interface/cpp/CompilerCInterface.cpp:36-88`, imported in `BE/llvm/ContextUtils.kt:414-502`. Code generation selects nothing by GC type: `config.gc` only chooses which runtime modules get linked (`BE/CompilerOutput.kt:159-177`). VERIFIED.

| Hook | When emitted | kmicro single-thread behaviour |
|---|---|---|
| `AllocInstance(ti, slot)` / `AllocArrayInstance(ti, n, slot)` | every heap allocation that escape analysis does not put on the stack (`CodeGenerator.kt:888-918`) | Allocate zeroed memory, which the compiler requires: it omits zero initializations (`IrToBitcode.kt:1689-1698`). Write the header; for arrays also `count_`. Then `*slot = obj` and return. Negative `n` throws IllegalArgumentException (`RT/mm/cpp/Memory.cpp:110-116`). May run the GC. Abort fatally if `ti->flags_ & TF_HAS_FINALIZER` (v1). |
| `UpdateHeapRef`, `UpdateStackRef`, `UpdateReturnRef`, `ZeroHeapRef`, `ZeroArrayRefs` | every reference store (`CodeGenerator.kt:742-774`) | Plain store (`Memory.cpp:124-167` shows stock already does this when barriers are no-ops). No write barrier is needed for a non-incremental STW collector. Because every heap reference store goes through these hooks, an incremental or generational collector could add a barrier later. |
| `UpdateVolatileHeapRef`, `CompareAndSet/SwapVolatileHeapRef`, `GetAndSetVolatileHeapRef` | `@Volatile` and atomic reference ops (`IntrinsicGenerator.kt:226-257`) | Plain load / compare / store. Interrupt handlers never touch the Kotlin heap, so no masking or LDREX is needed. Used by `AtomicReference` in `SafeContinuation` and `lazy`. |
| `EnterFrame(start, params, count)` | prologue, after the slot memset | `f->previous = top; f->parameters = params; f->count = count; top = f` (as in `RT/mm/cpp/ShadowStack.cpp` EnterFrame). |
| `LeaveFrame` | every return, and in cleanup landing pads | `top = f->previous` |
| `SetCurrentFrame(start)` | first instruction of every catch/finally landing pad | `top = start` |
| `CheckCurrentFrame` | debug builds only | Assert, or nothing. |
| `Kotlin_mm_safePointFunctionPrologue`, `…WhileLoopBody` | every function prologue (after `RemoveRedundantSafepointsPass`, one per function) and every loop back-edge (`IrToBitcode.kt:1198-1235`) | No GC work. Suggested use: a **stack-overflow guard** (`sp < __stack_limit + margin` → fatal), since the M4 has no stack-limit register. INFERRED. |
| `Kotlin_mm_switchThreadStateNative/Runnable` (and `_debug`) | around calls into C, and in exported bridges | Empty. |
| `RegisterGlobal(loc)` | first initialization of each reference global | Append to a static `ObjHeader** globals[KM_MAX_GLOBALS]`. Size it from a build-time count of `call @RegisterGlobal` in the final IR; overflow is fatal and is logged with the needed count. |
| `AddTLSRecord`, `CommitTLSStorage`, `ClearTLS`, `LookupTLS(key, i)` | thread-local object fields | One module, so one key: a static `ObjHeader* tls[]`, and `LookupTLS` returns `&tls[i]`. These slots are roots. |
| `CallInitGlobalPossiblyLock`, `CallInitThreadLocal`, `AppendToInitializersTail`, `Kotlin_initRuntimeIfNeeded` | file and object initializers (`IrToBitcode.kt:2350-2409`, `468-475`) | Single-threaded state machine without locks, as in `RT/main/cpp/Runtime.cpp:328-370` minus the waiting. Save and restore `top` around `init()`. Runtime init runs `ALLOC_TLS` → commit → `INIT_GLOBALS` → `INIT_THREAD_LOCAL` over the InitNode list (`Runtime.cpp:55-61,102-108`). |
| `Kotlin_mm_createRetainedExternalRCRef` / `release` / `dispose` | `StableRef`, `createRetainedExternalRCRef` (Cleaner) | Fixed table of `{obj, rc}`, about 8 entries; rc>0 is a root. |
| `ThrowException`, `Kotlin_getExceptionObject` | throw and catch | Exception-in-flight roots: holder objects linked into a list, or "fatal" in phase 1 (section 5). |
| `Kotlin_process{Object,Array,EmptyObject}InMark` | referenced as function pointers in every TypeInfo (`RTTIGenerator.kt:259-262,484-496`) | Must be defined. The kmicro GC can ignore them and use `objOffsets_` directly. |
| `Kotlin_{,int,long}ArrayGetElementAddress` | atomic array intrinsics | Return the element address. No allocation happens before it is used. |

**Inlining.** The stock runtime is linked as bitcode and LTO-inlined (`BE/llvm/runtime/RuntimeLinkage.kt:21-51`). To get the hooks as plain stores rather than `bl` calls, build kmicro's hot hooks with clang into bitcode and link them at the IR level. `-Xruntime=<path>` overrides `runtime.bc` (`compiler/cli/cli-base/gen/.../K2NativeCompilerArguments.kt:547-550`), but the compiler reads its struct types and target triple from that module (`BE/llvm/Runtime.kt:43-62`), so a replacement must keep the `touch*` types with identical layouts. INFERRED that this route works; the pipeline work must confirm it.

---

## 3. Allocator and GC design (12–16 KB heap)

### 3.1 Layout
- `uint8_t km_heap[KM_HEAP]`, aligned to 8, divided into 8-byte granules. No per-object header.
- **Allocated block:** an ordinary Kotlin object. Word 0 is the TypeInfo pointer; heap tag is 00, and **bit 1 is the mark bit**, used only during a collection.
- **Free block:** word 0 = `(granules << 2) | 1`; word 1 = `next`. Bit 0 can never be set in a heap object, because tag 1 means permanent and permanent objects live in flash.
- **Why this is safe:** the collector is stop-the-world, all marks are cleared in the sweep, and the runtime masks the tag bits wherever it reads the header (`Memory.h:35,73-78`). VERIFIED basis.
- **Free lists:** `km_free[12]`. Exact lists for 1–8 granules (8–64 B), then range lists for 9–16, 17–32, 33–128 and >128 granules.
- **Bump region:** `km_bump`..`km_end`, the trailing free run after each sweep.

### 3.2 Allocation
1. `g = (size + 7) >> 3`.
2. Try the exact list.
3. Otherwise bump from the top region.
4. Otherwise first fit in a larger list, splitting the block and pushing the remainder onto its list.
5. If that fails: collect, retry; if it still fails, `km_oom(size)`.
6. On success: `memset` the block to zero and write the header (and `count_` for arrays).

`km_oom` reports `{size, live, largest free run}` and stops the program; the firmware decides what happens next (a reset, for example).

### 3.3 Mark
- **Roots, in order:**
  1. Walk the frame chain from `top`. For each frame, read slots `[3 + params, count)` (as `ShadowStack.hpp:49-53` does).
  2. The globals table.
  3. The TLS slots.
  4. The stable-reference table.
  5. Exception holders.
- **For each root `o`:**
  - `o <= 1` (null or `kInitializingSingleton`, `Memory.h:136-139`): skip.
  - `o` in the heap address range: mark and push.
  - Header tag 3 (stack object): scan its fields now; it has no mark bit.
  - Header tag 1 (permanent, in flash): skip.

  This mirrors `collectRoot` and `processFieldInMark` (`MarkAndSweepUtils.hpp:28-39,59-72`); stms also allows heap-to-stack references (`RT/gc/stms/cpp/MarkTraits.hpp:19`).
- **`mark(o)`:** if bit 1 is already set, return. Otherwise set it. Push `o` only if it has reference fields: `theArrayTypeInfo` with `count_ > 0`, or `objOffsetsCount_ > 0`. Leaf objects (Strings, ByteArrays, boxed numbers) are never pushed.
- **Work list:** a static mark stack of 64 entries (256 B), not on the C stack.
  - On overflow, set a flag instead of pushing.
  - After the stack drains, if the flag is set: walk the heap linearly, rescan every marked object (rescanning is idempotent), and repeat until there is no overflow.
  - stms instead links gray objects through a per-object word (`RT/gc/stms/cpp/ObjectData.hpp:17-47`), which costs 4 B per object. Rejected for RAM.

### 3.4 Sweep (linear, coalescing)
Walk from the heap start to `km_bump`:
- Free block: size = `w0 >> 2`; it is free.
- Object: size from TypeInfo (or array count). If marked, clear bit 1 and keep it. If not, it is free.
- Adjacent free blocks merge into runs. Each run goes to its list; a run that reaches `km_bump` lowers `km_bump`.

Cost is proportional to the number of blocks. There is no bitmap.

### 3.5 When to collect
1. **Always** when an allocation fails.
2. **At idle**, before `kmicro_step` returns a "sleep" result, if `allocated_since_gc >= heap/4`. At that point the shadow stack holds only `step`'s frame, so roots are minimal.
3. On explicit `kotlin.native.runtime.GC.collect()` (`Kotlin_native_internal_GC_collect`, `Memory.cpp:223-225`).
4. **Never** in an interrupt handler. The GC never masks interrupts, so interrupt handlers preempt it.

**Pause estimate at 16 MHz:** 500 live objects × ~70 cycles for marking, plus ~1,500 blocks × ~15 cycles for sweeping, comes to about 60k cycles, roughly 4 ms. INFERRED; measure with DWT CYCCNT and log it. (Measured later: a full collection of the selftest's heap takes 1.8 ms at 16 MHz, [stm32l431-report.txt](../../examples/selftest/stm32l431-report.txt).)

### 3.6 Finalizers, Cleaners, weak references
- Only `CleanerImpl` (`RT/main/kotlin/kotlin/native/ref/Cleaner.kt:112`) and `RegularWeakReferenceImpl` (`ref/WeakPrivate.kt:40`) carry `@HasFinalizer`. The finalizer dispatch is hard-coded to those two (`RT/main/cpp/FinalizerHooks.cpp:20-28`). VERIFIED.
- Elsewhere in the standard library, weak references, Cleaners and stable refs are used only in Worker, concurrency and GCInfo code. VERIFIED by grep.
- **v1: reject.**
  - Fatal error on allocation of a type with `TF_HAS_FINALIZER`.
  - `Konan_getWeakReferenceImpl` aborts fatally.
  - A post-link `nm` check fails the build if `Konan_getWeakReferenceImpl` or `DisposeCleaner` is reachable.
- **v2 (optional):**
  - Weak refs: a table of `(weakImpl, referent)` pairs, with referents nulled after marking. Same idea as `processWeaks`, `MarkAndSweepUtils.hpp:162-182`.
  - Cleaners: actions queued and run from the event loop, never inside the GC, because a cleaner runs Kotlin code that allocates.

### 3.7 Permanent and static objects
- Flash constants (tag 1) are never marked, swept or written.
- Kotlin `object` singletons and file-level globals are ordinary heap objects, rooted through `RegisterGlobal`. Initialize them early (eager init, or touch them at start) so they settle at the bottom of the heap and do not fragment it.

### 3.8 Budget
| Item | RAM | Flash |
|---|---|---|
| Heap | 12–16 KB (start at 14 KB, tune from logged peak live bytes) | – |
| Free-list heads, bump pointers, counters | ~80 B | – |
| Mark stack | 256 B | – |
| Globals table (assumed 96 entries) | 384 B | – |
| TLS slots (8) + stable refs (8) + exception roots (4) | ~110 B | – |
| MM code: alloc, mark, sweep, roots, hooks, init, stable refs, 64-bit atomics | – | ~2.5–3 KB (INFERRED, -Os Thumb-2) |
| Extra C stack for Kotlin frames | +3 KB (INFERRED) | – |

Total: about 18–20 KB of SRAM.

### 3.9 Verification without lab tools
- **Host:** unit-test the C core with synthetic TypeInfos (the stock runtime tests do this with `TypeInfoHolder`), compiled for the host.
- **Device test build:** `KM_GC_STRESS=1` collects on every allocation and runs a heap-verify walk after each GC. Report through the console: GC count, max pause, peak live bytes, OOM events, globals high-water mark.

---

## 4. Coroutines

### 4.1 How Kotlin/Native 2.4.21 lowers `suspend` (VERIFIED)
- **No state machine** if a function has no non-tail suspend calls; tail calls become plain returns. `BE/lower/NativeSuspendFunctionLowering.kt:56-93`.
- **Otherwise a coroutine class is generated:**
  - It extends `ContinuationImpl`, or `RestrictedContinuationImpl` for restricted suspension (`:95-101`).
  - It has one field per parameter, receiver included (`compiler/ir/backend.common/.../AbstractSuspendFunctionsLowering.kt:122-123`).
  - It has a `label` field of type `NativePtr` (`:126`).
  - `invokeSuspend` holds the state machine.
- **Every call allocates a new instance.** The original function body becomes "create a coroutine object from the arguments plus `getContinuation()`, then call `invokeSuspend(Result.success(Unit))`" (`AbstractSuspendFunctionsLowering.kt:66-90`, `NativeSuspendFunctionLowering.kt:106-113`). This happens even when the call does not suspend. Resuming does not allocate again.
- **Suspension points.** Each one runs `saveCoroutineState`, sets `label = blockaddress(resume BB)`, makes the call, and returns if the result `=== COROUTINE_SUSPENDED`. The resume path runs `restoreCoroutineState` and then `result.getOrThrow()` (`:256-334`). Code generation dispatches with `indirectbr` on `label`, where null means the start (`IrToBitcode.kt:2277-2324`). `label` holds a code address, not a GC reference.
- **Spilling.** Each live local gets its own private field; fields are not shared between suspension points (`BE/lower/CoroutinesVarSpillingLowering.kt:57-72,86-108`). Liveness analysis is used when it runs; otherwise every visible variable is spilled (`:116-168`).
- **Runtime classes:**
  - `BaseContinuationImpl.resumeWith` unrolls the completion chain in a loop, with **try/catch around `invokeSuspend`** (`RT/main/kotlin/kotlin/coroutines/ContinuationImpl.kt:21-50`).
  - `ContinuationImpl.intercepted()` caches the interceptor result; it returns `this` when there is no interceptor (`:104-107`).
  - The debug probes are no-ops (`coroutines/DebugProbes.kt`).
  - `SafeContinuation` uses `AtomicReference` (`SafeContinuationNative.kt:28`).

### 4.2 Runtime support coroutines need
- Allocation and the roots described above.
- The reference CAS hooks (for `SafeContinuation`, if it is used).
- C++ exception tables, because `resumeWith` contains a catch.
- `indirectbr` and `blockaddress`, which LLVM handles on Thumb-2. INFERRED.

No threads, no TLS of their own, no 64-bit atomics, and no kotlinx.coroutines.

**Garbage rule.** While suspended, a coroutine has **no shadow-stack frame**, because `invokeSuspend` has returned. It survives only if something rooted holds its continuation. The dispatcher must keep every waiting continuation in its global arrays; otherwise the coroutine is collected and silently disappears.

### 4.3 Minimal single-thread dispatcher (no interceptor, no allocation per wait)
```kotlin
import kotlin.coroutines.*
import kotlin.coroutines.intrinsics.*

object Done : Continuation<Unit> {                       // shared completion: 0 B per coroutine
    override val context: CoroutineContext get() = EmptyCoroutineContext
    override fun resumeWith(result: Result<Unit>) { result.getOrThrow() }   // uncaught -> fatal
}

object Loop {
    private const val QN = 16; private val q = arrayOfNulls<Continuation<Unit>>(QN); private var qh = 0; private var qn = 0
    private const val TN = 16; private val tAt = IntArray(TN); private val tC = arrayOfNulls<Continuation<Unit>>(TN); private var tn = 0
    private const val EN = 8;  private val eC = arrayOfNulls<Continuation<Unit>>(EN); val payload = IntArray(EN)

    fun launch(block: suspend () -> Unit) = post(block.createCoroutineUnintercepted(Done))  // no SafeContinuation
    private fun post(c: Continuation<Unit>) { check(qn < QN); q[(qh + qn++) and (QN - 1)] = c }

    // Tail-call form: no state machine, no allocation. c is the caller's own frame object.
    suspend fun sleep(ms: Int): Unit = suspendCoroutineUninterceptedOrReturn { c ->
        check(tn < TN); tAt[tn] = k_now_ms() + ms; tC[tn++] = c; COROUTINE_SUSPENDED }
    suspend fun awaitEvent(src: Int): Unit = suspendCoroutineUninterceptedOrReturn { c ->
        eC[src] = c; COROUTINE_SUSPENDED }               // caller then reads Loop.payload[src] (avoids boxing)

    @CName("kmicro_step")                                  // called by the C main loop
    fun step(events: Int): Int {
        var ev = events
        while (ev != 0) { val s = ev.countTrailingZeroBits(); ev = ev and (ev - 1)
            val c = eC[s]; if (c != null) { eC[s] = null; payload[s] = k_payload(s); post(c) } }
        val now = k_now_ms(); var i = 0
        while (i < tn) { if (tAt[i] - now <= 0) { post(tC[i]!!); tn--; tAt[i] = tAt[tn]; tC[i] = tC[tn]; tC[tn] = null } else i++ }
        var budget = 8                                     // bounded work per step
        while (qn > 0 && budget-- > 0) { val c = q[qh]!!; q[qh] = null; qh = (qh + 1) and (QN - 1); qn--; c.resume(Unit) }
        if (qn > 0) return 0                               // more ready work: call again
        if (km_gc_wanted()) kotlin.native.runtime.GC.collect()   // idle-time GC, minimal roots
        if (tn == 0) return -1                             // no deadline
        var next = Int.MAX_VALUE; for (j in 0 until tn) next = minOf(next, tAt[j] - now); return maxOf(next, 0)
    }
}
```
- Time is an `Int` in milliseconds with wrap-safe subtraction, so no `Long` and no 64-bit atomics are involved.
- `resume(Unit)` uses the permanent `Unit` object and the inline `Result`, so it allocates nothing. VERIFIED that `Unit` is a constant (`KotlinStaticData.kt:93-103`).
- Avoid `suspendCoroutine`: it adds a `SafeContinuation` plus an `AtomicReference`, about 24 B per suspension (`libraries/stdlib/src/kotlin/coroutines/Continuation.kt:142-145`).
- Avoid `startCoroutine` and `createCoroutine`: the latter wraps in `SafeContinuation` (`Continuation.kt:84-87`).

### 4.4 Heap cost per suspended coroutine (32-bit, no allocator header)
| Object | Size |
|---|---|
| One frame of a stateful suspend function | 20 B base (header, completion, `_context`, `intercepted`, `label`), + 4 B per reference/Int/Float parameter or spilled local, + 8 B per Long/Double; rounded up to 8 → typically **24–40 B** |
| Launched lambda | Its coroutine instance: same formula, captured variables as fields. The `create()` copy is allocated at launch. |
| Completion / interceptor / wait registration | 0 B (shared singleton, none, fixed arrays) |
| Per resume | 0 B, or an Int box when the value is outside the box cache |
| Example | 3-deep chain with 1–2 locals per frame + lambda ≈ 3×32 + 32 = **~128 B**; 10 such coroutines ≈ 1.3 KB |

Every call to a stateful suspend function allocates its frame object at least once, which becomes garbage when the call completes. Keep leaf waits in tail-call or inline form (as above), so that hot loops allocate nothing per iteration.

### 4.5 "All coroutines suspended" → Sleep or Stop 1
The C main loop stays in charge:
```c
for (;;) {
    /* the firmware's own duties, such as feeding the watchdog */
    int32_t next = kmicro_step(take_events());         // events: bits set by interrupt handlers, taken under PRIMASK
    if (next == 0) continue;                           // ready work left
    idle(next);      // the firmware's low-power policy: Sleep (WFI) or Stop 1, with events checked under PRIMASK
}
```
- **Race-free sleep entry:** set PRIMASK, check for events once more, then WFI. A pending interrupt wakes the core even while it is masked (Cortex-M behaviour).
- **Wake sources from Stop 1** on the STM32L431 (RM0394): the RTC wake-up timer for millisecond deadlines, an RTC alarm, LPTIM1 clocked from LSE as an alternative timebase, EXTI lines, and a USART with wake-up from Stop enabled.
- **Timebase.** SysTick stops in Stop 1, so `k_now_ms()` must count the time spent in Stop, using RTC subseconds or LPTIM1. INFERRED.
- **Sleep, not Stop, while DMA or peripheral work is running:** the firmware's low-power policy decides this.
- **Standby** loses SRAM and CPU state. Kotlin coroutines cannot survive it, so the Kotlin layer must restart from persisted state. INFERRED.

---

## 5. Risks

| # | Risk | Evidence | Mitigation |
|---|---|---|---|
| 1 | `thread_local` in generated code | Non-object `@ThreadLocal` fields and the per-file `state_thread_local$` use LLVM `thread_local` with the GeneralDynamic model (`BE/llvm/LlvmUtils.kt:217-226`, `IrToBitcode.kt:686-692`). The chain `Throwable` (`by lazy`, `RT/main/kotlin/kotlin/Throwable.kt:39`) → `lazy` = `SynchronizedLazyImpl` (`kotlin/Lazy.kt:22`) → `Lock()` (`native/concurrent/Lazy.kt:62-65`) → `@ThreadLocal object CurrentThread` (`native/concurrent/Lock.kt:16-19`) makes this appear in practice. VERIFIED. | Single thread: strip `thread_local` in the IR before `llc`, or use `llc -emulated-tls` with libgcc's `__emutls_get_address` (present, VERIFIED by nm). Object thread-locals go through `LookupTLS` and are fine. |
| 2 | 64-bit atomics | `AtomicLong` is a `@Volatile Long` with LLVM `cmpxchg`/`atomicrmw` (`IntrinsicGenerator.kt:234-256`); `kotlin.random.Random` uses it (`random/Random.kt:20`). ARMv7-M has no LDREXD/STREXD, so LLVM emits `__atomic_*_8` calls (INFERRED). The xPack libgcc for v7e-m+fp/hard has **no** `__atomic_*` symbols, only `__sync_synchronize*` (VERIFIED by nm). | Provide `__atomic_{load,store,exchange,compare_exchange,fetch_add,fetch_sub}_8` with PRIMASK save/restore, about 0.2 KB. 32-bit atomics become LDREX/STREX plus DMB, which works (INFERRED). |
| 3 | Float ABI and CPU features | `linux_arm32_hfp`: triple `arm-unknown-linux-gnueabihf`, CPU `arm1176jzf-s`, features `+fp64,+vfp2,+strict-align,-thumb-mode`, `-mfloat-abi hard` (`DIST/konan/konan.properties:511,521,524-525`). VERIFIED. | Rewrite every function's `"target-cpu"`/`"target-features"` to cortex-m4 with fpv4-sp-d16 (no fp64) and Thumb mode before `llc`. Hard-float AAPCS-VFP matches C code built with `-mfpu=fpv4-sp-d16 -mfloat-abi=hard`, INFERRED. Double arithmetic becomes libgcc soft-float. |
| 4 | Stack arrays from escape analysis | Up to 65,536 B of stack arrays allowed per function (`BE/optimizations/EscapeAnalysis.kt:1650,1663-1715`) against a stack of a few KB. VERIFIED. | Post-link frame-size check that fails the build above, say, 512 B; fallback `-Xdisable-phases=EscapeAnalysis` (INFERRED that the phase name works with this flag: `BE/driver/phases/LTO.kt:131-132`). Escape analysis is otherwise valuable: it takes temporaries off the heap. |
| 5 | Global constructors never run | Initializers register through constructor functions that call `AppendToInitializersTail` (`IrToBitcode.kt:468-475`, `RT/main/cpp/Runtime.cpp:168-176`). A start-up that copies .data/.bss and calls `main()` without running `.init_array` never registers them. | Iterate `__init_array_start..end` before Kotlin init. |
| 6 | Exceptions | Personality `__gxx_personality_v0` plus `__cxa_*` (`ContextUtils.kt:596-599`, `CodeGenerator.kt:1023-1037,1170-1178`); stdlib catch blocks, e.g. in `resumeWith`. libsupc++_nano and the libgcc EHABI unwinder exist (VERIFIED by nm). `__cxa_allocate_exception` needs malloc or the emergency pool. | Phase 1: `ThrowException` is fatal (the old Zephyr approach) plus a stub personality. Phase 2: real exception handling, roughly 10–20 KB flash (INFERRED; measure with `size`) and exception-holder roots. |
| 7 | Allocations per `Throwable` and `lazy` | Each Throwable captures a stack trace (`Throwable.kt:37`) and builds a `SynchronizedLazyImpl` with Lock and atomics; roughly 100 B or more each (INFERRED). | `Kotlin_getCurrentStackTrace` returns an empty array; app code uses `lazy(LazyThreadSafetyMode.NONE)`. |
| 8 | Alignment | Objects 8-aligned; LDRD/STRD/VLDR on M4 need word alignment. Stack objects get explicit alignment (`CodeGenerator.kt:419-420`). | The heap base is 8-aligned and granules are 8 B. Compatible. |
| 9 | Workers and threads pulled in | `Worker.kt`, `Thread.kt`, `getAvailableProcessors` (`Runtime.cpp:277-290`) | kmicro does not define the Worker and thread natives, so any reference becomes a link error. Good as a detector. |
| 10 | C runtime code missing a root | The obligation in section 1.4 | GC-stress build plus heap verification; ObjHolder-style frame helper in C. |
| 11 | Fragmentation (non-moving heap) | Section 1.5 | Segregated lists, early long-lived allocations, big buffers in C, OOM log with largest free run. |
| 12 | Interrupt code touching Kotlin | – | Rule: interrupt handlers only set C event bits and ring buffers. The GC never masks interrupts. |
| 13 | Box-cache flash cost | Constant box caches for each primitive type (`BE/Boxing.kt:164-188`) | Flash only, no RAM. Measure; where the range is defined was not checked. |
| 14 | Flash cost of safepoint calls | One `bl` per function prologue unless inlined (`BE/optimizations/RemoveRedundantSafepointsPass.kt:11-17`) | LTO-link kmicro's empty or stack-check hook as bitcode. `-Xbinary=smallBinary=true` turns on size-level optimization (`BE/NativeSecondStageCompilationConfig.kt:104-114`, `OptimizationPipeline.kt:127,169`). |

---

## 6. What the 2017–2020 Zephyr target contributes
- **Platform settings:** `armv7m-none-eabi`, `-mthumb`, cortex-m4, aapcs (`ARC/konan/platforms/zephyr/stm32f4_disco:20-25`). VERIFIED.
- **Runtime defines:** `KONAN_NO_THREADS`, `NO_EXCEPTIONS`, `NO_MATH`, `NO_FFI`, `INTERNAL_SNPRINTF/NOW`, `NO_CTORS_SECTION`, `NO_UNALIGNED_ACCESS` (`ARC/shared/src/main/kotlin/org/jetbrains/kotlin/konan/target/ClangArgs.kt:333-343`, via `git show`).
- **Exceptions:** throw printed the exception and failed fatally (`ARC/runtime/src/main/cpp/Exceptions.cpp:204-209`). There was no C++ runtime (`ARC/samples/zephyr/prj.conf`: `CONFIG_CPLUSPLUS=n`). VERIFIED.
- **Memory manager:** reference counting with container headers and a cycle collector (`ARC/runtime/src/main/cpp/Memory.h:120-190`). That code generation emitted reference-count updates. **Nothing of that memory manager carries over**; the 2.4.21 shadow-stack and tracing interface is what kmicro builds on. VERIFIED (old) / INFERRED (conclusion).

## 7. Next measurements, small and in this order
1. Compile a small Kotlin file for `linux_arm32_hfp` to bitcode with `-Xtemporary-files-dir`. In the IR, count:
   - `call @RegisterGlobal`, which sizes the globals table;
   - `thread_local` globals;
   - `cmpxchg i64` / `atomicrmw i64`;
   - stack frames larger than 512 B;
   - references to `Konan_getWeakReferenceImpl`, `DisposeCleaner`, `Worker`.
2. Confirm the `-Xruntime` / IR-link route: does the compiler accept a kmicro `runtime.bc` that keeps the `touch*` types?
3. Build the C core (allocator and GC) for the host, with synthetic TypeInfos and GC stress.
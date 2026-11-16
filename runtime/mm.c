/* Copyright 2010-2024 JetBrains s.r.o. and Kotlin Programming Language contributors.
 * Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
/* kmicro memory manager: one thread, stop-the-world precise mark-sweep, non-moving, no per-object header.
 *
 * Heap: a static arena of 8-byte granules. An allocated block IS the Kotlin object: its first word is the TypeInfo
 * pointer (heap tag 00). A free block starts with (bytes | 1) and keeps the next-free pointer in its second word;
 * bit 0 never appears in a heap object's first word (tag 01 is "permanent", and permanent objects live in flash).
 * The mark bit is bit 1 of the object's first word, set only during a collection; everything that reads the
 * header masks the two tag bits (km_type_info). Object sizes come from the TypeInfo (and count_ for arrays), so the
 * sweep walks the arena linearly. Objects are 8-byte aligned (kObjectAlignment).
 *
 * Roots, as in the stock MM (mm/cpp RootSet, ShadowStack): the shadow-stack frames the compiled code pushes with
 * EnterFrame (slots after the FrameOverlay and the parameters), the globals registered with RegisterGlobal, the
 * thread-local slots, kmicro's C-side roots and an exception in flight. Stack objects (tag 3) and permanent objects
 * (tag 1) are never marked or freed; their fields are traced when they appear as roots ("each permanent and stack
 * object has own entry in the root set", MarkAndSweepUtils.hpp). Field tracing goes through
 * TypeInfo::processObjectInMark, which the compiler points at the Kotlin_process*InMark functions defined here.
 *
 * The collector runs only inside an allocation call (or an explicit GC.collect / kmicro_gc). The compiled code
 * keeps every live reference in a frame slot across calls, so nothing live hides in registers (docs/research/R_mm.md).
 * Interrupt handlers may run while it marks and store references; mark() handles that.
 */
#include <string.h>
#include "kmicro.h"

/* Sizes; each can be set from the build (-D NAME=VALUE). A full table stops with a panic naming its macro. */
#ifndef KM_HEAP_BYTES
#define KM_HEAP_BYTES (16u * 1024u)
#endif
#ifndef KM_MARK_STACK
#define KM_MARK_STACK 96                             /* not a limit: an overflow costs a rescan of the heap */
#endif
#ifndef KM_GLOBALS
#define KM_GLOBALS    160                            /* reference globals (RegisterGlobal), the stdlib's included */
#endif
#ifndef KM_C_ROOTS
#define KM_C_ROOTS    16                             /* kmicro_root slots */
#endif
#ifndef KM_STABLE_REFS
#define KM_STABLE_REFS 16                            /* StableRefs, and Cleaners whose actions have not run */
#endif
#ifndef KM_GC_REMARKS
#define KM_GC_REMARKS 3                              /* marking passes an interrupt handler may restart (mark()) */
#endif
#ifndef KM_GC_STRESS
#define KM_GC_STRESS  0                              /* 1: collect before every allocation, overwrite freed memory */
#endif

#define FREE_BIT 1u
#define MARK_BIT 2u

static uint64_t s_arena[KM_HEAP_BYTES / 8u];         /* 8-byte aligned by type */
static uint32_t *s_lo, *s_hi;                        /* arena start / end */
#define KM_SMALL_BINS 8                              /* exact sizes 8, 16, ..., 64 bytes */
static uint32_t *s_bin[KM_SMALL_BINS];               /* free blocks of exactly (i + 1) * 8 bytes, LIFO */
static uint32_t *s_large;                            /* free blocks above 64 bytes, unordered */
static kmicro_stats_t s_st;

static FrameOverlay *s_frame;                        /* the shadow stack */
static ObjHeader **s_globals[KM_GLOBALS];
static int s_nglobals;
static ObjHeader **s_croots[KM_C_ROOTS];

static ObjHeader *s_mark_stack[KM_MARK_STACK];
static int s_msp;
static bool s_mark_overflow;

/* ---------------------------------------------------------------------------------------------------------- */
/* heap                                                                                                       */
/* ---------------------------------------------------------------------------------------------------------- */

static inline uint32_t free_size(const uint32_t *b) { return b[0] & ~7u; }
static inline uint32_t *next_free(uint32_t *b) { return (uint32_t *)b[1]; }
static inline void set_free(uint32_t *b, uint32_t bytes, uint32_t *next)
{
    b[0] = bytes | FREE_BIT;
    b[1] = (uint32_t)next;
}

static inline uint32_t round8(uint32_t n) { return (n + 7u) & ~7u; }

/* Block size of the object at b (header word possibly carrying the mark bit). */
static inline uint32_t object_size(const uint32_t *b)
{
    const TypeInfo *t = ((const TypeInfo *)(b[0] & ~(uint32_t)KM_TAG_MASK))->typeInfo_;
    if (t->instanceSize_ >= 0)
        return round8((uint32_t)t->instanceSize_);
    return round8((uint32_t)sizeof(ArrayHeader) + (uint32_t)-t->instanceSize_ * ((const ArrayHeader *)b)->count_);
}

static void push_free(uint32_t *b, uint32_t bytes)
{
    if (bytes <= KM_SMALL_BINS * 8u) {
        uint32_t i = bytes / 8u - 1u;
        set_free(b, bytes, s_bin[i]);
        s_bin[i] = b;
    } else {
        set_free(b, bytes, s_large);
        s_large = b;
    }
}

static void heap_init(void)
{
    s_lo = (uint32_t *)s_arena;
    s_hi = (uint32_t *)((uint8_t *)s_arena + sizeof s_arena);
    push_free(s_lo, sizeof s_arena);
    s_st.heap_bytes = sizeof s_arena;
}

static inline bool in_heap(const void *p) { return (const uint32_t *)p >= s_lo && (const uint32_t *)p < s_hi; }

static uint32_t *claim(uint32_t *b, uint32_t size)  /* a block leaves the free lists: zero it, count it */
{
    memset(b, 0, size);
    s_st.used_bytes += size;
    if (s_st.used_bytes > s_st.peak_bytes)
        s_st.peak_bytes = s_st.used_bytes;
    s_st.alloc_count++;
    return b;
}

/* Hand out `bytes` from free block b (already unlinked): the low part, the rest goes back to the lists. */
static uint32_t *split_low(uint32_t *b, uint32_t bytes)
{
    uint32_t size = free_size(b);
    if (size - bytes >= 8u) {
        push_free((uint32_t *)((uint8_t *)b + bytes), size - bytes);
        return claim(b, bytes);
    }
    return claim(b, size);
}

/* Policy (segregated fits, two-ended):
 *  - 8..64 bytes: the exact-size bin first, so holes left by objects of the same size are reused; then a larger
 *    bin, then the lowest large block;
 *  - 72..255 bytes: the lowest large block that fits;
 *  - 256 bytes and more: the highest large block that fits, carved from its end.
 * Small and short-lived objects stay low, big arrays high: a non-moving heap cannot compact, so this is what keeps
 * room for large blocks. */
#define KM_LARGE_BLOCK 256u

static uint32_t *take_large(uint32_t bytes, bool high)
{
    uint32_t **best = NULL;
    for (uint32_t **link = &s_large; *link != NULL; link = (uint32_t **)&(*link)[1]) {
        uint32_t *b = *link;
        if (free_size(b) >= bytes && (best == NULL || (high ? b > *best : b < *best)))
            best = link;
    }
    if (best == NULL)
        return NULL;
    uint32_t *b = *best;
    *best = next_free(b);
    if (!high)
        return split_low(b, bytes);
    uint32_t size = free_size(b);
    if (size - bytes >= 8u) {                        /* the head stays free, the tail is handed out */
        push_free(b, size - bytes);
        return claim((uint32_t *)((uint8_t *)b + size - bytes), bytes);
    }
    return claim(b, size);
}

static uint32_t *take(uint32_t bytes)              /* bytes: a multiple of 8, at least 8 */
{
    if (bytes <= KM_SMALL_BINS * 8u) {
        for (uint32_t i = bytes / 8u - 1u; i < KM_SMALL_BINS; i++) {
            uint32_t *b = s_bin[i];
            if (b != NULL) {
                s_bin[i] = next_free(b);
                return split_low(b, bytes);
            }
        }
    }
    return take_large(bytes, bytes >= KM_LARGE_BLOCK);
}

static void count_free(uint32_t *largest, uint32_t *nfree)
{
    *largest = *nfree = 0;
    for (uint32_t i = 0; i < KM_SMALL_BINS; i++)
        for (uint32_t *f = s_bin[i]; f != NULL; f = next_free(f), (*nfree)++)
            if (free_size(f) > *largest)
                *largest = free_size(f);
    for (uint32_t *f = s_large; f != NULL; f = next_free(f), (*nfree)++)
        if (free_size(f) > *largest)
            *largest = free_size(f);
}

static void report_oom(uint32_t bytes)
{
    uint32_t largest, nfree;
    count_free(&largest, &nfree);
    kmicro_puts("kmicro: out of memory: wanted ");
    kmicro_put_int((int32_t)bytes);
    kmicro_puts(" B, live after GC ");
    kmicro_put_int((int32_t)s_st.used_bytes);
    kmicro_puts(" of ");
    kmicro_put_int((int32_t)s_st.heap_bytes);
    kmicro_puts(" B, largest free ");
    kmicro_put_int((int32_t)largest);
    kmicro_puts(" B in ");
    kmicro_put_int((int32_t)nfree);
    kmicro_puts(" free blocks\n");
}

static void collect(void);

/* Interrupt handlers written in Kotlin must not allocate or collect: the handler may have interrupted another
 * allocation or the collector (the heap is not reentrant), and a collection started there would miss references
 * the interrupted code holds only in registers. Stop loudly instead of corrupting the heap. Every heap allocation
 * (the compiled code's and the runtime's own, e.g. Int.toString) and every collection passes one of these checks;
 * km_fault_pc is the return address into the code that asked, and kmicro_panic prints it. */
void *km_fault_pc;

__attribute__((noinline, cold, noreturn)) static void isr_fail(void *caller, const char *what)
{
    if ((uintptr_t)caller >= 0xF0000000u)            /* EXC_RETURN: the check was inlined into the handler itself, */
        caller = (char *)__builtin_return_address(0) - 2;   /* so name the call to here (it may end the handler) */
    km_fault_pc = caller;
    kmicro_panic(what);
}

static inline void isr_check(void *caller, const char *what)
{
    if (km_in_interrupt())
        isr_fail(caller, what);
}
#define KM_ISR_ALLOC "allocation inside an interrupt handler"

static bool s_cleaners;                              /* a collection found Cleaners dead: their actions are to run */
static bool s_cleaning;                              /* run_cleaners is running them */
static void run_cleaners(void);

static uint32_t *alloc_block(uint32_t object_bytes)
{
    if (s_lo == NULL)
        heap_init();
    if (__builtin_expect(s_cleaners, 0))             /* before anything is taken from the heap */
        run_cleaners();
    if (object_bytes > KM_HEAP_BYTES)
        ThrowOutOfMemoryError();
    uint32_t bytes = round8(object_bytes);
#if KM_GC_STRESS
    collect();                                       /* stress: a full collection before every allocation */
#endif
    uint32_t *b = take(bytes);
    if (b == NULL) {
        collect();
        b = take(bytes);
        /* No room, and the collection found Cleaners dead. What their actions hold (a buffer given to createCleaner)
         * is still live: it is free once the actions have run and another collection has looked. A resource may have
         * a Cleaner of its own, so this repeats while collections find dead ones; each such Cleaner held a slot, which
         * bounds the rounds. Not when an action itself is what allocates: its own round is still running. */
        for (int round = 0; b == NULL && s_cleaners && !s_cleaning && round < KM_STABLE_REFS; round++) {
            run_cleaners();
            collect();
            b = take(bytes);
        }
        if (b == NULL) {
            report_oom(bytes);
            kmicro_panic("out of memory");          /* ThrowOutOfMemoryError would itself allocate */
        }
    }
    return b;
}

static ObjHeader *alloc_object(const TypeInfo *type, ObjHeader **result)
{
    ObjHeader *o = (ObjHeader *)alloc_block((uint32_t)type->instanceSize_);
    o->typeInfoOrMeta_ = type;
    return km_return(result, o);
}

static ObjHeader *alloc_array(const TypeInfo *type, int32_t count, ObjHeader **result)
{
    if (count < 0)
        ThrowIllegalArgumentException();
    uint32_t elem = (uint32_t)-type->instanceSize_;
    uint64_t bytes = sizeof(ArrayHeader) + (uint64_t)elem * (uint32_t)count;
    if (bytes > KM_HEAP_BYTES)
        ThrowOutOfMemoryError();
    ArrayHeader *a = (ArrayHeader *)alloc_block((uint32_t)bytes);
    a->typeInfoOrMeta_ = type;
    a->count_ = (uint32_t)count;
    return km_return(result, (ObjHeader *)a);
}

/* The runtime's own allocations (strings, stack traces) */
ObjHeader *kmicro_alloc_object(const TypeInfo *type, ObjHeader **result)
{
    isr_check(__builtin_return_address(0), KM_ISR_ALLOC);
    return alloc_object(type, result);
}
ObjHeader *kmicro_alloc_array(const TypeInfo *type, int32_t count, ObjHeader **result)
{
    isr_check(__builtin_return_address(0), KM_ISR_ALLOC);
    return alloc_array(type, count, result);
}

/* Memory.h: the compiled code's allocations */
KM_NOTHROW ObjHeader *AllocInstance(const TypeInfo *type, ObjHeader **result)
{
    isr_check(__builtin_return_address(0), KM_ISR_ALLOC);
    return alloc_object(type, result);
}
ObjHeader *AllocArrayInstance(const TypeInfo *type, int32_t elements, ObjHeader **result)
{
    isr_check(__builtin_return_address(0), KM_ISR_ALLOC);
    return alloc_array(type, elements, result);
}

/* ---------------------------------------------------------------------------------------------------------- */
/* reference stores (the one barrier: km_ref_stored, for interrupt handlers storing while the collector marks)  */
/* ---------------------------------------------------------------------------------------------------------- */

volatile uint8_t km_refs_stored;

/* Stores into objects and globals (heap stores) go through the barrier. Frame slots (UpdateStackRef, UpdateReturnRef)
 * do not: a handler only writes its own frames, and storing null (ZeroHeapRef) cannot hide an object. */
KM_NOTHROW void UpdateHeapRef(ObjHeader **location, const ObjHeader *object)
{
    km_ref_stored();
    *location = (ObjHeader *)object;
}
KM_NOTHROW void UpdateStackRef(ObjHeader **location, const ObjHeader *object) { *location = (ObjHeader *)object; }
KM_NOTHROW void UpdateReturnRef(ObjHeader **slot, const ObjHeader *object) { *slot = (ObjHeader *)object; }
KM_NOTHROW void UpdateVolatileHeapRef(ObjHeader **location, const ObjHeader *object)
{
    km_ref_stored();
    *location = (ObjHeader *)object;
}
KM_NOTHROW void ZeroHeapRef(ObjHeader **location) { *location = NULL; }
KM_NOTHROW void ZeroArrayRefs(ArrayHeader *array) { memset(km_array_refs(array), 0, array->count_ * sizeof(ObjHeader *)); }
/* AtomicReference and @Volatile read-modify-writes: atomic against interrupt handlers too (LDREX/STREX; exception
 * entry clears the exclusive monitor, so an interrupted update retries), like the Int and Long atomics. */
KM_NOTHROW bool CompareAndSetVolatileHeapRef(ObjHeader **location, ObjHeader *expected, ObjHeader *value)
{
    km_ref_stored();
    return __atomic_compare_exchange_n(location, &expected, value, false, __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST);
}
KM_NOTHROW ObjHeader *CompareAndSwapVolatileHeapRef(ObjHeader **location, ObjHeader *expected, ObjHeader *value,
                                                    ObjHeader **result)
{
    km_ref_stored();
    __atomic_compare_exchange_n(location, &expected, value, false, __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST);
    return km_return(result, expected);              /* the old value, whether or not it was replaced */
}
KM_NOTHROW ObjHeader *GetAndSetVolatileHeapRef(ObjHeader **location, ObjHeader *value, ObjHeader **result)
{
    km_ref_stored();
    return km_return(result, __atomic_exchange_n(location, value, __ATOMIC_SEQ_CST));
}

/* ---------------------------------------------------------------------------------------------------------- */
/* shadow stack (ShadowStack.cpp)                                                                             */
/* ---------------------------------------------------------------------------------------------------------- */

KM_NOTHROW void EnterFrame(ObjHeader **start, int parameters, int count)
{
    FrameOverlay *f = (FrameOverlay *)start;
    f->previous = s_frame;
    s_frame = f;
    f->parameters = parameters;
    f->count = count;
}
KM_NOTHROW void LeaveFrame(ObjHeader **start, int parameters, int count)
{
    (void)parameters;
    (void)count;
    s_frame = ((FrameOverlay *)start)->previous;
}
KM_NOTHROW void SetCurrentFrame(ObjHeader **start) { s_frame = (FrameOverlay *)start; }
KM_NOTHROW FrameOverlay *getCurrentFrame(void) { return s_frame; }
KM_NOTHROW void CheckCurrentFrame(ObjHeader **frame)
{
    if ((FrameOverlay *)frame != s_frame)
        kmicro_panic("shadow stack mismatch");
}

/* ---------------------------------------------------------------------------------------------------------- */
/* globals and file initialization (Runtime.cpp)                                                              */
/* ---------------------------------------------------------------------------------------------------------- */

KM_NOTHROW void RegisterGlobal(ObjHeader **location)
{
    if (s_nglobals == KM_GLOBALS)
        kmicro_panic("too many globals (raise KM_GLOBALS, now " KM_STR(KM_GLOBALS) ")");
    s_globals[s_nglobals++] = location;
}

/* CallInitGlobalPossiblyLock / CallInitThreadLocal: runtime/init_cxx.cpp (a failing initializer must be caught). */

/* C-side roots: the kernel keeps Kotlin objects (e.g. a pending continuation) alive through these. */
void kmicro_root(ObjHeader **slot)
{
    for (int i = 0; i < KM_C_ROOTS; i++)
        if (s_croots[i] == NULL) {
            s_croots[i] = slot;
            return;
        }
    kmicro_panic("too many C roots (raise KM_C_ROOTS, now " KM_STR(KM_C_ROOTS) ")");
}
void kmicro_unroot(ObjHeader **slot)
{
    for (int i = 0; i < KM_C_ROOTS; i++)
        if (s_croots[i] == slot)
            s_croots[i] = NULL;
}

/* ---------------------------------------------------------------------------------------------------------- */
/* StableRef: externally reference-counted references (ExternalRCRef.kt; stock mm/cpp ExternalRCRef)           */
/* ---------------------------------------------------------------------------------------------------------- */

/* StableRef.create(obj).asCPointer() is the address of a slot in this table; C keeps it as a void * (callback user
 * data) and Kotlin turns it back with asStableRef. While the count is above zero the object is a root (create sets
 * 1, dispose releases and frees the slot); at zero the slot is weak and the collector clears it once nothing else
 * keeps the object. A null object has no slot: its reference is NULL. Interrupt handlers may use these too.
 * A Cleaner keeps its action in a slot as well (createCleaner, below). */
typedef struct { ObjHeader *obj; uint16_t rc; bool used, clean; } km_stable_ref_t;   /* clean: see run_cleaners */
static km_stable_ref_t s_stable[KM_STABLE_REFS];

static km_stable_ref_t *stable_slot(void *ref)
{
    km_stable_ref_t *s = ref;
    if (s < s_stable || s >= s_stable + KM_STABLE_REFS || !s->used)
        kmicro_panic("not a live StableRef (used after dispose?)");
    return s;
}

static void *stable_create(ObjHeader *obj, uint16_t rc)
{
    if (obj == NULL)
        return NULL;
    for (int attempt = 0;; attempt++) {
        uint32_t pm = km_irq_save();
        for (int i = 0; i < KM_STABLE_REFS; i++)
            if (!s_stable[i].used) {
                s_stable[i] = (km_stable_ref_t){ obj, rc, true, false };
                km_ref_stored();                     /* a new root: a collection that is marking looks again */
                km_irq_restore(pm);
                return &s_stable[i];
            }
        km_irq_restore(pm);
        if (attempt > 0 || km_in_interrupt())
            break;
        /* Full. A Cleaner keeps a slot until its action has run: collect, and run the actions of the dead ones. */
        struct { FrameOverlay f; ObjHeader *obj; } fr = { { 0, 0, 0 }, obj };
        EnterFrame((ObjHeader **)&fr, 0, sizeof fr / sizeof(ObjHeader *));
        collect();
        run_cleaners();
        LeaveFrame((ObjHeader **)&fr, 0, sizeof fr / sizeof(ObjHeader *));
    }
    kmicro_panic("too many StableRefs (raise KM_STABLE_REFS, now " KM_STR(KM_STABLE_REFS) ")");
}

KM_NOTHROW void *Kotlin_native_internal_ref_createRetainedExternalRCRef(ObjHeader *obj) { return stable_create(obj, 1); }
KM_NOTHROW void *Kotlin_native_internal_ref_createUnretainedExternalRCRef(ObjHeader *obj) { return stable_create(obj, 0); }

KM_NOTHROW void Kotlin_native_internal_ref_retainExternalRCRef(void *ref)
{
    if (ref == NULL)
        return;
    uint32_t pm = km_irq_save();
    stable_slot(ref)->rc++;
    km_ref_stored();                                 /* a weak slot may have become a root */
    km_irq_restore(pm);
}
KM_NOTHROW void Kotlin_native_internal_ref_releaseExternalRCRef(void *ref)
{
    if (ref == NULL)
        return;
    uint32_t pm = km_irq_save();
    km_stable_ref_t *s = stable_slot(ref);
    if (s->rc == 0)
        kmicro_panic("StableRef released more often than retained");
    s->rc--;
    km_irq_restore(pm);
}
KM_NOTHROW void Kotlin_native_internal_ref_disposeExternalRCRef(void *ref)
{
    if (ref == NULL)
        return;
    uint32_t pm = km_irq_save();
    *stable_slot(ref) = (km_stable_ref_t){ NULL, 0, false, false };
    km_irq_restore(pm);
}
KM_NOTHROW ObjHeader *Kotlin_native_internal_ref_dereferenceExternalRCRef(void *ref, ObjHeader **result)
{
    return km_return(result, ref == NULL ? NULL : stable_slot(ref)->obj);
}
KM_NOTHROW ObjHeader *Kotlin_native_internal_ref_dereferenceExternalRCRefOrNull(void *ref, ObjHeader **result)
{
    km_stable_ref_t *s = ref;
    if (s < s_stable || s >= s_stable + KM_STABLE_REFS)   /* WeakReference.get(): the object itself, or NULL (below) */
        return km_return(result, ref);
    return km_return(result, stable_slot(ref)->obj);     /* NULL once a weak slot was cleared */
}

/* ---------------------------------------------------------------------------------------------------------- */
/* WeakReference (ref/Weak.kt, ref/WeakPrivate.kt; stock mm/cpp WeakRef.cpp)                                  */
/* ---------------------------------------------------------------------------------------------------------- */

/* WeakReference(obj) keeps what Konan_getWeakReferenceImpl returns, a RegularWeakReferenceImpl, and get() is
 * dereferenceExternalRCRefOrNull(impl.weakRef). In the stock runtime weakRef is an entry of its reference registry,
 * and the object's extra data remembers the impl. kmicro's objects have no extra data and its StableRef table is
 * small, so here weakRef is the object itself: the field is a native pointer, which the collector does not trace.
 * The other field, `referred`, which the Kotlin code never reads, chains the impls: after marking the collector
 * walks the chain, drops the impls that are garbage themselves and clears weakRef where the object is (mark()).
 * An object that is not on the heap (a constant, an `object`) is never cleared, so it needs no
 * PermanentWeakReferenceImpl. Each WeakReference gets an impl of its own, 16 bytes of heap. */
typedef struct km_weak { ObjHeader header; ObjHeader *object; struct km_weak *next; } km_weak_t;
static km_weak_t *s_weak;
extern const TypeInfo *theRegularWeakReferenceImplTypeInfo;

ObjHeader *Konan_getWeakReferenceImpl(ObjHeader *referent, ObjHeader **result)
{
    km_weak_t *w = (km_weak_t *)kmicro_alloc_object(theRegularWeakReferenceImplTypeInfo, result);
    w->object = referent;
    w->next = s_weak;
    s_weak = w;
    return &w->header;
}

/* ---------------------------------------------------------------------------------------------------------- */
/* createCleaner (ref/Cleaner.kt; stock main/cpp Cleaner.cpp)                                                 */
/* ---------------------------------------------------------------------------------------------------------- */

/* createCleaner(resource, action) returns a CleanerImpl whose only field is a retained StableRef of a lambda that
 * runs the action. When the sweep frees the CleanerImpl it marks that slot (finalize), and the lambda, still a
 * root, runs later. The stock runtime runs it on its finalizer thread. kmicro has one thread and runs it where
 * Kotlin code can run and nothing is half done: at the start of the next allocation (and inside the one that
 * collected, when it still finds no room: alloc_block), at the end of GC.collect() and
 * kmicro_gc(), and when the StableRef table is full. Never inside the collector, and never in an interrupt handler,
 * which reaches none of these places. The action may allocate, collect and make Cleaners; an exception it throws
 * ends inside the lambda, as in the stock runtime. */
__attribute__((weak)) ObjHeader *km_function0_invoke(ObjHeader *function, ObjHeader **result)
    __asm__("kfun:kotlin.Function0#invoke(){}1:0");  /* the interface call */

__attribute__((noinline, cold)) static void run_cleaners(void)
{
    if (s_cleaning)                                  /* an action that allocates or collects: the loop below goes on */
        return;
    if (km_function0_invoke == NULL)
        kmicro_panic("Cleaner: no Function0.invoke");
    s_cleaning = true;
    struct { FrameOverlay f; ObjHeader *action, *unit; } fr = { { 0, 0, 0 }, 0, 0 };
    EnterFrame((ObjHeader **)&fr, 0, sizeof fr / sizeof(ObjHeader *));
    while (s_cleaners) {
        s_cleaners = false;
        for (int i = 0; i < KM_STABLE_REFS; i++)
            if (s_stable[i].clean) {                 /* as the stdlib's executeAndRelease: free the slot, then run */
                fr.action = s_stable[i].obj;
                uint32_t pm = km_irq_save();
                s_stable[i] = (km_stable_ref_t){ NULL, 0, false, false };
                km_irq_restore(pm);
                km_function0_invoke(fr.action, &fr.unit);
            }
    }
    LeaveFrame((ObjHeader **)&fr, 0, sizeof fr / sizeof(ObjHeader *));
    s_cleaning = false;
}

/* The sweep frees an object whose class has a finalizer. For a CleanerImpl the first field is the slot of its
 * action; for a RegularWeakReferenceImpl it is an object or NULL, and there is nothing to do. */
static void finalize(const uint32_t *b)
{
    km_stable_ref_t *s = (km_stable_ref_t *)b[1];
    if (s >= s_stable && s < s_stable + KM_STABLE_REFS && s->used && s->rc > 0) {
        s->clean = true;
        s_cleaners = true;
    }
}

/* ---------------------------------------------------------------------------------------------------------- */
/* mark                                                                                                       */
/* ---------------------------------------------------------------------------------------------------------- */

static inline void push_child(ObjHeader *o)       /* a reference found in a field or a root */
{
    if ((uintptr_t)o <= 1u || !in_heap(o))            /* null, kInitializingSingleton (Memory.h), or not heap */
        return;
    uint32_t *w = (uint32_t *)o;
    if (*w & MARK_BIT)
        return;
    *w |= MARK_BIT;
    if (s_msp < KM_MARK_STACK)
        s_mark_stack[s_msp++] = o;
    else
        s_mark_overflow = true;                      /* marked but not scanned: found again by the rescan */
}

static inline void scan(ObjHeader *o) { km_type_info(o)->processObjectInMark(NULL, o); }

/* TypeInfo::processObjectInMark targets (gc/common MarkAndSweepUtils.hpp, traverseClassObjectFields) */
KM_NOTHROW void Kotlin_processObjectInMark(void *state, ObjHeader *object)
{
    (void)state;
    const TypeInfo *t = km_type_info(object);
    for (int32_t i = 0; i < t->objOffsetsCount_; i++)
        push_child(*(ObjHeader **)((uint8_t *)object + t->objOffsets_[i]));
}
KM_NOTHROW void Kotlin_processArrayInMark(void *state, ObjHeader *object)
{
    (void)state;
    ArrayHeader *a = (ArrayHeader *)object;
    ObjHeader **e = km_array_refs(a);
    for (uint32_t i = 0; i < a->count_; i++)
        push_child(e[i]);
}
KM_NOTHROW void Kotlin_processEmptyObjectInMark(void *state, ObjHeader *object) { (void)state; (void)object; }

static unsigned root(ObjHeader *o)                   /* 1 when the slot held a reference, for the statistics */
{
    if ((uintptr_t)o <= 1u)                          /* null, or kInitializingSingleton */
        return 0;
    if (km_tag(o) == KM_TAG_HEAP)
        push_child(o);
    else
        scan(o);                                     /* stack / permanent object: trace its fields */
    return 1;
}

static void drain(void)
{
    for (;;) {
        while (s_msp > 0)
            scan(s_mark_stack[--s_msp]);
        if (!s_mark_overflow)
            return;
        s_mark_overflow = false;                     /* rescan: every marked object's fields again */
        for (uint32_t *b = s_lo; b < s_hi;) {
            uint32_t size;
            if (b[0] & FREE_BIT) {
                size = free_size(b);
            } else {
                size = object_size(b);
                if (b[0] & MARK_BIT) {
                    scan((ObjHeader *)b);
                    while (s_msp > 0)
                        scan(s_mark_stack[--s_msp]);
                }
            }
            b = (uint32_t *)((uint8_t *)b + size);
        }
    }
}

km_gc_info_t km_gc_info;                             /* the collection that ran last (kmicro.h) */
int64_t (*km_gc_clock)(void);

static void eh_root(ObjHeader *o) { root(o); }

static void mark_roots(void)
{
    unsigned stack = 0, global = 0, tls = 0, stable = 0;
    for (FrameOverlay *f = s_frame; f != NULL; f = f->previous) {
        ObjHeader **slot = (ObjHeader **)(f + 1) + f->parameters;
        int n = f->count - KM_FRAME_OVERLAY_SLOTS - f->parameters;
        for (int i = 0; i < n; i++)
            stack += root(slot[i]);
    }
    for (int i = 0; i < s_nglobals; i++)
        global += root(*s_globals[i]);
    for (int i = 0; i < kmicro_tls_slot_count; i++)
        tls += root(kmicro_tls_slots[i]);
    for (int i = 0; i < KM_C_ROOTS; i++)
        if (s_croots[i] != NULL)
            stable += root(*s_croots[i]);
    for (int i = 0; i < KM_STABLE_REFS; i++)
        if (s_stable[i].rc > 0)
            stable += root(s_stable[i].obj);
    extern void kmicro_eh_roots(void (*visit)(ObjHeader *));
    kmicro_eh_roots(eh_root);                        /* an exception in flight */
    km_gc_info.stack_roots = stack;
    km_gc_info.global_roots = global;
    km_gc_info.tls_roots = tls;
    km_gc_info.stable_roots = stable;
}

/* ---------------------------------------------------------------------------------------------------------- */
/* sweep                                                                                                      */
/* ---------------------------------------------------------------------------------------------------------- */

static void sweep(void)
{
    for (uint32_t i = 0; i < KM_SMALL_BINS; i++)
        s_bin[i] = NULL;
    s_large = NULL;
    uint32_t *run = NULL, run_size = 0;               /* the free run being built (coalescing) */
    uint32_t used = 0, kept = 0, freed = s_st.objects_freed;
    for (uint32_t *b = s_lo; b < s_hi;) {
        uint32_t size;
        bool live = false;
        if (b[0] & FREE_BIT) {
            size = free_size(b);
        } else {
            size = object_size(b);
            if (b[0] & MARK_BIT) {
                b[0] &= ~MARK_BIT;
                used += size;
                kept++;
                live = true;
            } else {
                s_st.objects_freed++;
                if (((const TypeInfo *)b[0])->typeInfo_->flags_ & KM_TF_HAS_FINALIZER)
                    finalize(b);
#if KM_GC_STRESS
                memset(b, 0xA5, size);               /* stress: a dangling reference reads garbage, not old data */
#endif
            }
        }
        if (live) {
            if (run != NULL)
                push_free(run, run_size);
            run = NULL;
        } else if (run != NULL) {
            run_size += size;                        /* merge into the run */
        } else {
            run = b;
            run_size = size;
        }
        b = (uint32_t *)((uint8_t *)b + size);
    }
    if (run != NULL)
        push_free(run, run_size);
    km_gc_info.bytes_before = s_st.used_bytes;
    km_gc_info.bytes_after = used;
    km_gc_info.kept = kept;
    km_gc_info.swept = s_st.objects_freed - freed;
    s_st.used_bytes = used;
    if (used > s_st.live_peak_bytes)
        s_st.live_peak_bytes = used;
}

static void remark(void)                            /* the roots and every marked object's fields again */
{
    mark_roots();
    s_mark_overflow = true;
    drain();
}

/* After marking: a heap object that nothing reached, which the sweep frees. */
static inline bool dying(const ObjHeader *o) { return o != NULL && in_heap(o) && !(*(const uint32_t *)o & MARK_BIT); }

/* Marking runs with interrupts enabled. A handler that moves a reference meanwhile, from a slot not scanned yet to
 * one already scanned (a buffer swap), would hide a live object, so km_ref_stored() records every reference store
 * made during marking, and marking repeats until a pass ends without one: then the reference graph did not change
 * during a complete pass. A pass from the roots alone would not do, since it stops at marked objects whose fields
 * may have changed. If handlers keep storing, the last pass (after KM_GC_REMARKS) runs with interrupts masked. */
static void mark(void)
{
    s_msp = 0;
    s_mark_overflow = false;
    km_refs_stored = 0;                              /* only interrupt handlers store from here on */
    mark_roots();
    drain();
    uint32_t pm = km_irq_save();
    for (int pass = 0; km_refs_stored && pass < KM_GC_REMARKS; pass++) {
        km_refs_stored = 0;
        km_irq_restore(pm);
        remark();
        pm = km_irq_save();
    }
    if (km_refs_stored)
        remark();
    for (int i = 0; i < KM_STABLE_REFS; i++)        /* weak StableRef slots: forget objects about to be freed */
        if (s_stable[i].rc == 0 && dying(s_stable[i].obj))
            s_stable[i].obj = NULL;
    for (km_weak_t **link = &s_weak, *w; (w = *link) != NULL;) {   /* and so do the WeakReferences */
        if (dying(&w->header)) {
            *link = w->next;                         /* nothing holds this WeakReference any more */
            continue;
        }
        if (dying(w->object))
            w->object = NULL;
        link = &w->next;
    }
    km_irq_restore(pm);
}

static void collect(void)
{
    if (s_lo == NULL)
        heap_init();
    int64_t (*clock)(void) = km_gc_clock;            /* set once the program has asked for GC.lastGCInfo */
    if (clock != NULL)
        km_gc_info.start_ns = clock();
    mark();
    sweep();
    km_gc_info.epoch = ++s_st.gc_count;
    km_gc_info.timed = clock != NULL;
    if (clock != NULL)
        km_gc_info.end_ns = clock();
}

void kmicro_gc(void)
{
    isr_check(__builtin_return_address(0), "garbage collection inside an interrupt handler");
    collect();
    if (s_cleaners)
        run_cleaners();
}

void kmicro_stats(kmicro_stats_t *out)
{
    if (s_lo == NULL)
        heap_init();
    *out = s_st;
}

/* The Kotlin GC API (kotlin.native.runtime.GC) maps onto the same collector. */
void Kotlin_native_internal_GC_collect(ObjHeader *thiz) { (void)thiz; kmicro_gc(); }

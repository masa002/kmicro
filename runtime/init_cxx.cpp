/* Copyright 2010-2024 JetBrains s.r.o. and Kotlin Programming Language contributors.
 * Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
/* File / object initializers (Runtime.cpp CallInitGlobalPossiblyLock / CallInitThreadLocal), in C++ because a
 * failing initializer must be caught: the state becomes FILE_FAILED_TO_INITIALIZE and the Kotlin exception is
 * rethrown wrapped (ThrowFileFailedToInitializeException), exactly as the stock runtime does. The catch(...) runs
 * on kmicro's own personality (runtime/eh.c), which treats every catch clause as catch-all. One thread: a re-entry
 * during initialization ("being initialized") simply returns, as the stock code does for the initializing thread.
 * kmicro_call_catching does the same catch for eh.c, which runs the unhandled-exception hook and goes on when the
 * hook throws.
 *
 * Kotlin/Native 2.5 gives the two functions one more argument, the class whose initializer runs (null for a file's),
 * and its standard library has StaticInitializationFailure(reason, class) in the place of
 * ThrowFileFailedToInitializeException(reason). C cannot define one name with two signatures, and the LTO link
 * treats a call through another signature as undefined behaviour, so the functions of 2.5 are kmicro_init_global and
 * kmicro_init_thread_local here: toolchain/retarget.py gives the calls of a 2.5 program these names. A program calls
 * one pair, and the link drops the other with the function of the standard library it names.
 *
 * GC rules followed here: Kotlin frames left by the unwinding are dropped (SetCurrentFrame to our own frame) before
 * anything can allocate, and the caught exception is kept in a slot of our shadow-stack frame, never only in a C++
 * variable, while ThrowFileFailedToInitializeException allocates the wrapper. */
#include <stdint.h>
#include "km_cpu.h"

extern "C" {
struct ObjHeader;
struct TypeInfo;
void EnterFrame(ObjHeader **start, int parameters, int count);
void LeaveFrame(ObjHeader **start, int parameters, int count);
void SetCurrentFrame(ObjHeader **start);
ObjHeader *kmicro_caught_exception(void);       /* runtime/eh.c: the exception between begin_catch and end_catch */
void ThrowFileFailedToInitializeException(ObjHeader *reason) __attribute__((noreturn));
void StaticInitializationFailure(ObjHeader *reason, const TypeInfo *type) __attribute__((noreturn));
void CallInitGlobalPossiblyLock(uintptr_t *state, void (*init)(void));
void CallInitThreadLocal(volatile uintptr_t *global_state, uintptr_t *local_state, void (*init)(void));
void kmicro_init_global(uintptr_t *state, void (*init)(void), const TypeInfo *type);
void kmicro_init_thread_local(volatile uintptr_t *global_state, uintptr_t *local_state, void (*init)(void),
                              const TypeInfo *type);
ObjHeader *kmicro_call_catching(void (*fn)(ObjHeader *), ObjHeader *arg, ObjHeader **frame, ObjHeader **slot);
void kmicro_panic(const char *what) __attribute__((noreturn));
extern void *km_fault_pc;                           /* runtime/mm.c: the address kmicro_panic prints */
}

/* kmicro.h's km_in_interrupt (that header is C) */
static inline bool km_in_interrupt() { return km_handler() != 0u; }

namespace {
enum : uintptr_t { NOT_INITIALIZED = 0, BEING_INITIALIZED = 1, INITIALIZED = 2, FAILED_TO_INITIALIZE = 3 };

struct Frame {                                       /* FrameOverlay (3 words) + one object slot */
    void *previous = nullptr;
    int32_t parameters = 0;
    int32_t count = 0;
    ObjHeader *reason = nullptr;
    ObjHeader **start() { return reinterpret_cast<ObjHeader **>(this); }
    static constexpr int kSlots = 4;
};

/* Runs init(); on an exception returns it (rooted in fr), else nullptr. */
bool run_init(Frame &fr, void (*init)(void))
{
    try {
        init();
        return false;
    } catch (...) {
        SetCurrentFrame(fr.start());                 /* the initializer's frames are gone */
        fr.reason = kmicro_caught_exception();
        return true;
    }
}
} // namespace

/* A file's globals are created on first use, which allocates: never in an interrupt handler. A handler that finds
 * them being created has interrupted that first use and would read them unset; it cannot wait for the thread code.
 * The panic names the code that made the first use, as the allocation check of mm.c does: `caller` is the return
 * address of the function the compiled code called. */
__attribute__((noinline, cold, noreturn)) static void refused(void *caller, uintptr_t st)
{
    if (km_handler_return((uintptr_t)caller))        /* the call was inlined into the handler itself, */
        caller = (char *)__builtin_return_address(0) - 2;   /* so name the call to here */
    km_fault_pc = caller;
    if (st == BEING_INITIALIZED)
        kmicro_panic("Kotlin globals used inside an interrupt handler while the thread code creates them");
    kmicro_panic("Kotlin globals first used inside an interrupt handler");
}

static inline void refuse_in_handler(uintptr_t st, void *caller)
{
    if (km_in_interrupt())
        refused(caller, st);
}

/* The two functions, with `failed` for what throws: failed(exception) when the initializer threw it, and
 * failed(nullptr) for a later use of what it left uninitialised. failed() does not return. `caller` is the return
 * address of the function the compiled code called, for the panic of a first use inside a handler. */
template <typename Failed>
static inline void init_global(uintptr_t *state, void (*init)(void), void *caller, Failed failed)
{
    uintptr_t st = *state;
    if (st == INITIALIZED)
        return;
    refuse_in_handler(st, caller);
    if (st == BEING_INITIALIZED)                     /* the initializer itself uses its file's globals */
        return;
    if (st == FAILED_TO_INITIALIZE)
        failed(nullptr);
    *state = BEING_INITIALIZED;
    Frame fr;
    EnterFrame(fr.start(), 0, Frame::kSlots);
    if (run_init(fr, init)) {
        *state = FAILED_TO_INITIALIZE;
        failed(fr.reason);                           /* our frame is popped by the catcher's SetCurrentFrame */
    }
    LeaveFrame(fr.start(), 0, Frame::kSlots);
    *state = INITIALIZED;
}

template <typename Failed>
static inline void init_thread_local(volatile uintptr_t *global_state, uintptr_t *local_state, void (*init)(void),
                                     void *caller, Failed failed)
{
    /* The @ThreadLocal globals of a file. The stock runtime marks them initialised before it runs the initializer;
     * kmicro keeps "being initialised" until it is done, so that a handler that interrupts it is stopped as for
     * ordinary globals. The compiled code calls this function whenever the state is not INITIALIZED. */
    uintptr_t st = *local_state;
    if (st == INITIALIZED)
        return;
    refuse_in_handler(st, caller);
    if (st == BEING_INITIALIZED)                     /* the initializer itself uses its file's thread-locals */
        return;
    if (st == FAILED_TO_INITIALIZE || (global_state != nullptr && *global_state == FAILED_TO_INITIALIZE))
        failed(nullptr);
    *local_state = BEING_INITIALIZED;
    Frame fr;
    EnterFrame(fr.start(), 0, Frame::kSlots);
    if (run_init(fr, init)) {
        *local_state = FAILED_TO_INITIALIZE;
        failed(fr.reason);
    }
    LeaveFrame(fr.start(), 0, Frame::kSlots);
    *local_state = INITIALIZED;
}

void CallInitGlobalPossiblyLock(uintptr_t *state, void (*init)(void))
{
    init_global(state, init, __builtin_return_address(0),
                [](ObjHeader *reason) { ThrowFileFailedToInitializeException(reason); });
}

void CallInitThreadLocal(volatile uintptr_t *global_state, uintptr_t *local_state, void (*init)(void))
{
    init_thread_local(global_state, local_state, init, __builtin_return_address(0),
                      [](ObjHeader *reason) { ThrowFileFailedToInitializeException(reason); });
}

void kmicro_init_global(uintptr_t *state, void (*init)(void), const TypeInfo *type)
{
    init_global(state, init, __builtin_return_address(0),
                [type](ObjHeader *reason) { StaticInitializationFailure(reason, type); });
}

void kmicro_init_thread_local(volatile uintptr_t *global_state, uintptr_t *local_state, void (*init)(void),
                              const TypeInfo *type)
{
    init_thread_local(global_state, local_state, init, __builtin_return_address(0),
                      [type](ObjHeader *reason) { StaticInitializationFailure(reason, type); });
}

/* Calls fn(arg). Returns nullptr when it returns, else the Kotlin exception it threw, kept in *slot, a slot of the
 * caller's shadow-stack frame `frame` (the frames the unwinding removed are dropped first, as in run_init). */
ObjHeader *kmicro_call_catching(void (*fn)(ObjHeader *), ObjHeader *arg, ObjHeader **frame, ObjHeader **slot)
{
    try {
        fn(arg);
        return nullptr;
    } catch (...) {
        SetCurrentFrame(frame);
        *slot = kmicro_caught_exception();
        return *slot;
    }
}

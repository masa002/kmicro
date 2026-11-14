/* File / object initializers (Runtime.cpp CallInitGlobalPossiblyLock / CallInitThreadLocal), in C++ because a
 * failing initializer must be caught: the state becomes FILE_FAILED_TO_INITIALIZE and the Kotlin exception is
 * rethrown wrapped (ThrowFileFailedToInitializeException), exactly as the stock runtime does. The catch(...) runs
 * on kmicro's own personality (runtime/eh.c), which treats every catch clause as catch-all. One thread: a re-entry
 * during initialization ("being initialized") simply returns, as the stock code does for the initializing thread.
 * kmicro_call_catching does the same catch for eh.c, which runs the unhandled-exception hook and goes on when the
 * hook throws.
 *
 * GC rules followed here: Kotlin frames left by the unwinding are dropped (SetCurrentFrame to our own frame) before
 * anything can allocate, and the caught exception is kept in a slot of our shadow-stack frame, never only in a C++
 * variable, while ThrowFileFailedToInitializeException allocates the wrapper. */
#include <stdint.h>

extern "C" {
struct ObjHeader;
void EnterFrame(ObjHeader **start, int parameters, int count);
void LeaveFrame(ObjHeader **start, int parameters, int count);
void SetCurrentFrame(ObjHeader **start);
ObjHeader *kmicro_caught_exception(void);       /* runtime/eh.c: the exception between begin_catch and end_catch */
void ThrowFileFailedToInitializeException(ObjHeader *reason) __attribute__((noreturn));
void CallInitGlobalPossiblyLock(uintptr_t *state, void (*init)(void));
void CallInitThreadLocal(volatile uintptr_t *global_state, uintptr_t *local_state, void (*init)(void));
ObjHeader *kmicro_call_catching(void (*fn)(ObjHeader *), ObjHeader *arg, ObjHeader **frame, ObjHeader **slot);
void kmicro_panic(const char *what) __attribute__((noreturn));
}

/* kmicro.h's km_in_interrupt (that header is C) */
static inline bool km_in_interrupt()
{
#if defined(__ARM_ARCH_PROFILE) && __ARM_ARCH_PROFILE == 'M'
    unsigned ipsr;
    __asm volatile("mrs %0, ipsr" : "=r"(ipsr));
    return (ipsr & 0x1FFu) != 0u;
#else
    return false;
#endif
}

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
 * them being created has interrupted that first use and would read them unset; it cannot wait for the thread code. */
static void refuse_in_handler(uintptr_t st)
{
    if (!km_in_interrupt())
        return;
    if (st == BEING_INITIALIZED)
        kmicro_panic("Kotlin globals used inside an interrupt handler while the thread code creates them");
    kmicro_panic("Kotlin globals first used inside an interrupt handler");
}

void CallInitGlobalPossiblyLock(uintptr_t *state, void (*init)(void))
{
    uintptr_t st = *state;
    if (st == INITIALIZED)
        return;
    refuse_in_handler(st);
    if (st == BEING_INITIALIZED)                     /* the initializer itself uses its file's globals */
        return;
    if (st == FAILED_TO_INITIALIZE)
        ThrowFileFailedToInitializeException(nullptr);
    *state = BEING_INITIALIZED;
    Frame fr;
    EnterFrame(fr.start(), 0, Frame::kSlots);
    if (run_init(fr, init)) {
        *state = FAILED_TO_INITIALIZE;
        ThrowFileFailedToInitializeException(fr.reason);   /* our frame is popped by the catcher's SetCurrentFrame */
    }
    LeaveFrame(fr.start(), 0, Frame::kSlots);
    *state = INITIALIZED;
}

void CallInitThreadLocal(volatile uintptr_t *global_state, uintptr_t *local_state, void (*init)(void))
{
    /* The @ThreadLocal globals of a file. The stock runtime marks them initialised before it runs the initializer;
     * kmicro keeps "being initialised" until it is done, so that a handler that interrupts it is stopped as for
     * ordinary globals. The compiled code calls this function whenever the state is not INITIALIZED. */
    uintptr_t st = *local_state;
    if (st == INITIALIZED)
        return;
    refuse_in_handler(st);
    if (st == BEING_INITIALIZED)                     /* the initializer itself uses its file's thread-locals */
        return;
    if (st == FAILED_TO_INITIALIZE || (global_state != nullptr && *global_state == FAILED_TO_INITIALIZE))
        ThrowFileFailedToInitializeException(nullptr);
    *local_state = BEING_INITIALIZED;
    Frame fr;
    EnterFrame(fr.start(), 0, Frame::kSlots);
    if (run_init(fr, init)) {
        *local_state = FAILED_TO_INITIALIZE;
        ThrowFileFailedToInitializeException(fr.reason);
    }
    LeaveFrame(fr.start(), 0, Frame::kSlots);
    *local_state = INITIALIZED;
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

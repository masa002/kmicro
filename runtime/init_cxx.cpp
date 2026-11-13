/* File / object initializers (Runtime.cpp CallInitGlobalPossiblyLock / CallInitThreadLocal), in C++ because a
 * failing initializer must be caught: the state becomes FILE_FAILED_TO_INITIALIZE and the Kotlin exception is
 * rethrown wrapped (ThrowFileFailedToInitializeException), exactly as the stock runtime does. The catch(...) runs
 * on kmicro's own personality (runtime/eh.c), which treats every catch clause as catch-all. One thread: a re-entry
 * during initialization ("being initialized") simply returns, as the stock code does for the initializing thread.
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
void kmicro_panic(const char *what) __attribute__((noreturn));
}

/* kmicro.h's km_in_interrupt (that header is C) */
static inline bool km_in_interrupt()
{
#if defined(__ARM_ARCH_7EM__) || defined(__ARM_ARCH_7M__) || defined(__ARM_ARCH_6M__) || defined(__ARM_ARCH_8M_MAIN__)
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

void CallInitGlobalPossiblyLock(uintptr_t *state, void (*init)(void))
{
    uintptr_t st = *state;
    if (st == INITIALIZED || st == BEING_INITIALIZED)
        return;
    if (km_in_interrupt())                           /* a file's globals are created on first use: never in a handler */
        kmicro_panic("Kotlin globals first used inside an interrupt handler");
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
    if (*local_state == FAILED_TO_INITIALIZE || (global_state != nullptr && *global_state == FAILED_TO_INITIALIZE))
        ThrowFileFailedToInitializeException(nullptr);
    *local_state = INITIALIZED;
    Frame fr;
    EnterFrame(fr.start(), 0, Frame::kSlots);
    if (run_init(fr, init)) {
        *local_state = FAILED_TO_INITIALIZE;
        ThrowFileFailedToInitializeException(fr.reason);
    }
    LeaveFrame(fr.start(), 0, Frame::kSlots);
}

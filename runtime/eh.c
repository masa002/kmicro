/* Kotlin exceptions on ARM EHABI, bare metal: libgcc's unwinder plus kmicro's own personality routine.
 *
 * How the compiler lowers exceptions (docs/research/R_eh.md, CodeGenerator.kt / IrToBitcode.kt at v2.4.21):
 *   - throw out of a function: call ThrowException(exception);
 *   - every try gets one landing pad `landingpad catch null` (catch-all at the LLVM level); it calls
 *     SetCurrentFrame, __cxa_begin_catch(r0), Kotlin_getExceptionObject, __cxa_end_catch and then matches the
 *     Kotlin catch clauses in Kotlin code, rethrowing when none matches; finally is lowered to catch + rethrow;
 *   - Kotlin -> C bridges get "filtering" pads `catch @_ZTI18ExceptionObjHolder, catch null` that compare the
 *     selector with the type index of _ZTI18ExceptionObjHolder; cleanup pads end in __cxa_end_cleanup.
 * So the personality never matches Kotlin types: a frame with a catch action handles the exception, the selector
 * handed to the pad is the filter of its first action record, and a cleanup-only pad runs and unwinding resumes.
 * Phase 1 finds the handler frame and remembers its SP; phase 2 runs cleanups on the way and installs the handler.
 * If nothing handles the exception (or unwinding reaches code without unwind tables), ThrowException runs the hook
 * set by setUnhandledExceptionHook, reports the exception with its Kotlin type, message, the stack trace captured
 * at construction and its causes, then stops.
 */
#include <string.h>
#include "kmicro.h"

/* Without -fexceptions this file's functions get [cantunwind] entries: phase 1 stops at ThrowException and every Kotlin
 * exception is reported as uncaught. Clang and GCC define __EXCEPTIONS for C exactly when -fexceptions is given. */
#ifndef __EXCEPTIONS
#error "compile the kmicro runtime with -fexceptions -funwind-tables (docs/porting.md)"
#endif

/* ARM EHABI interface of libgcc (unwind-arm-common.h, GCC 15.2), declared here because clang's own <unwind.h>
 * describes a different (LLVM libunwind) layout. */
typedef enum {
    _URC_OK = 0, _URC_NO_REASON = 0, _URC_FOREIGN_EXCEPTION_CAUGHT = 1, _URC_END_OF_STACK = 5,
    _URC_HANDLER_FOUND = 6, _URC_INSTALL_CONTEXT = 7, _URC_CONTINUE_UNWIND = 8, _URC_FAILURE = 9
} _Unwind_Reason_Code;
typedef int _Unwind_State;
enum { _US_VIRTUAL_UNWIND_FRAME = 0, _US_UNWIND_FRAME_STARTING = 1, _US_UNWIND_FRAME_RESUME = 2,
       _US_ACTION_MASK = 3, _US_FORCE_UNWIND = 8 };
typedef struct _Unwind_Context _Unwind_Context;
typedef struct _Unwind_Control_Block {
    char exception_class[8];
    void (*exception_cleanup)(_Unwind_Reason_Code, struct _Unwind_Control_Block *);
    struct { uint32_t reserved1, reserved2, reserved3, reserved4, reserved5; } unwinder_cache;
    struct { uint32_t sp; uint32_t bitpattern[5]; } barrier_cache;
    struct { uint32_t bitpattern[4]; } cleanup_cache;
    struct { uint32_t fnstart; uint32_t *ehtp; uint32_t additional; uint32_t reserved1; } pr_cache;
    long long : 0;
} _Unwind_Control_Block;
typedef _Unwind_Reason_Code (*_Unwind_Trace_Fn)(_Unwind_Context *, void *);
enum { _UVRSC_CORE = 0, _UVRSD_UINT32 = 0 };
int _Unwind_VRS_Get(_Unwind_Context *, int regclass, uint32_t regno, int repr, void *value);
int _Unwind_VRS_Set(_Unwind_Context *, int regclass, uint32_t regno, int repr, void *value);
void *_Unwind_GetLanguageSpecificData(_Unwind_Context *);
uintptr_t _Unwind_GetRegionStart(_Unwind_Context *);
_Unwind_Reason_Code _Unwind_RaiseException(_Unwind_Control_Block *);
__attribute__((noreturn)) void _Unwind_Resume(_Unwind_Control_Block *);
_Unwind_Reason_Code _Unwind_Backtrace(_Unwind_Trace_Fn, void *);
_Unwind_Reason_Code __gnu_unwind_frame(_Unwind_Control_Block *, _Unwind_Context *);
static inline uint32_t _Unwind_GetGR(_Unwind_Context *c, int r)
{
    uint32_t v;
    _Unwind_VRS_Get(c, _UVRSC_CORE, (uint32_t)r, _UVRSD_UINT32, &v);
    return v;
}
static inline void _Unwind_SetGR(_Unwind_Context *c, int r, uint32_t v)
{
    _Unwind_VRS_Set(c, _UVRSC_CORE, (uint32_t)r, _UVRSD_UINT32, &v);
}
typedef uint32_t _Unwind_Word;

void EnterFrame(ObjHeader **start, int parameters, int count);
void LeaveFrame(ObjHeader **start, int parameters, int count);

/* ---- the exceptions being thrown or caught: one record per running context ----
 *
 * Kotlin catches an exception at once and `finally` rethrows a fresh one, so the thread code has at most one exception
 * between its throw and the end of its catch. An interrupt handler can throw and catch one of its own in the middle of
 * that (an exception that already exists: creating one allocates), and a handler of higher priority inside that one.
 * Each takes the next record and gives it back before the code it interrupted goes on, so the records are a stack:
 * the top one always belongs to the code that is running. KM_EH_DEPTH is the thread code plus the handlers that can be
 * nested inside each other while they throw. */

#ifndef KM_EH_DEPTH
#define KM_EH_DEPTH 4
#endif

typedef struct {
    _Unwind_Control_Block ucb;                       /* first: r0 at the landing pad points here */
    ObjHeader *exception;                            /* from ThrowException to __cxa_begin_catch: a GC root */
    ObjHeader *caught;                               /* from __cxa_begin_catch to __cxa_end_catch: a GC root */
    uint32_t context;                                /* who threw it: 0 the thread code, else the handler's number */
} km_exception_t;

static km_exception_t s_recs[KM_EH_DEPTH] __attribute__((aligned(8)));
static int s_depth;                                  /* records in use: s_recs[0 .. s_depth) */
/* &s_recs[s_depth - 1], or NULL. Not static: __cxa_end_cleanup reads it by name in assembly. */
__attribute__((used)) km_exception_t *km_eh_current;
const void *const _ZTI18ExceptionObjHolder[2] = { 0, "18ExceptionObjHolder" };   /* identity only */

/* A handler that interrupts push or pop takes and returns records above the ones in use and leaves s_depth and
 * km_eh_current as it found them, so neither needs interrupts masked: push raises s_depth before it writes the
 * record. */
static km_exception_t *push_record(void)
{
    int n = s_depth;
    s_depth = n + 1;
    km_eh_current = &s_recs[n];
    return &s_recs[n];
}

static void pop_record(void)
{
    int n = s_depth - 1;
    s_recs[n].exception = s_recs[n].caught = NULL;
    s_depth = n;
    km_eh_current = n > 0 ? &s_recs[n - 1] : NULL;
}

/* The Cortex-M exception number of the running code (IPSR): 0 in thread code. */
static uint32_t running_context(void)
{
#if defined(__ARM_ARCH_7EM__) || defined(__ARM_ARCH_7M__) || defined(__ARM_ARCH_6M__) || defined(__ARM_ARCH_8M_MAIN__)
    uint32_t ipsr;
    __asm volatile("mrs %0, ipsr" : "=r"(ipsr));
    return ipsr & 0x1FFu;
#else
    return 0;
#endif
}

void kmicro_eh_roots(void (*visit)(ObjHeader *))
{
    for (int i = 0; i < s_depth; i++) {
        visit(s_recs[i].exception);
        visit(s_recs[i].caught);
    }
}

/* ---- LSDA reading (GCC exception table format, as LLVM emits it after the EHABI opcodes) ---- */

enum { DW_EH_PE_omit = 0xff, DW_EH_PE_uleb128 = 0x01, DW_EH_PE_udata2 = 0x02, DW_EH_PE_udata4 = 0x03,
       DW_EH_PE_sleb128 = 0x09, DW_EH_PE_sdata2 = 0x0a, DW_EH_PE_sdata4 = 0x0b, DW_EH_PE_pcrel = 0x10 };

static uint32_t uleb(const uint8_t **p)
{
    uint32_t r = 0;
    unsigned shift = 0;
    uint8_t b;
    do {
        b = *(*p)++;
        r |= (uint32_t)(b & 0x7f) << shift;
        shift += 7;
    } while (b & 0x80);
    return r;
}

static int32_t sleb(const uint8_t **p)
{
    int32_t r = 0;
    unsigned shift = 0;
    uint8_t b;
    do {
        b = *(*p)++;
        r |= (int32_t)(b & 0x7f) << shift;
        shift += 7;
    } while (b & 0x80);
    if (shift < 32 && (b & 0x40))
        r |= -(1 << shift);
    return r;
}

static uint32_t read_enc(const uint8_t **p, uint8_t enc)
{
    const uint8_t *start = *p;
    uint32_t v;
    switch (enc & 0x0f) {
    case DW_EH_PE_uleb128: v = uleb(p); break;
    case DW_EH_PE_sleb128: v = (uint32_t)sleb(p); break;
    case DW_EH_PE_udata2: case DW_EH_PE_sdata2: {
        uint16_t x;
        memcpy(&x, *p, 2);
        *p += 2;
        v = (enc & 0x0f) == DW_EH_PE_sdata2 ? (uint32_t)(int32_t)(int16_t)x : x;
        break;
    }
    default:                                         /* absptr / udata4 / sdata4 */
        memcpy(&v, *p, 4);
        *p += 4;
        break;
    }
    if (v != 0 && (enc & 0x70) == DW_EH_PE_pcrel)
        v += (uint32_t)(uintptr_t)start;
    return v;
}

typedef struct { uint32_t lp; int32_t filter; bool found; } km_site_t;

/* The call-site entry covering ip: its landing pad (0 = none) and the first action's filter (0 = cleanup). */
static km_site_t find_site(_Unwind_Context *ctx)
{
    km_site_t s = { 0, 0, false };
    const uint8_t *p = _Unwind_GetLanguageSpecificData(ctx);
    if (p == NULL)
        return s;
    uint32_t fstart = (uint32_t)_Unwind_GetRegionStart(ctx);
    uint32_t ip = (uint32_t)(_Unwind_GetGR(ctx, 15) & ~1u) - 1u;   /* inside the call instruction */
    uint8_t lp_enc = *p++;
    uint32_t lpstart = lp_enc == DW_EH_PE_omit ? fstart : read_enc(&p, lp_enc);
    uint8_t tt_enc = *p++;
    if (tt_enc != DW_EH_PE_omit)
        (void)uleb(&p);                              /* type table offset: never read */
    uint8_t cs_enc = *p++;
    uint32_t cs_len = uleb(&p);
    const uint8_t *cs_end = p + cs_len, *actions = cs_end;
    while (p < cs_end) {
        uint32_t start = read_enc(&p, cs_enc), len = read_enc(&p, cs_enc), lp = read_enc(&p, cs_enc);
        uint32_t action = uleb(&p);
        if (ip < lpstart + start)
            break;                                   /* sorted table */
        if (ip < lpstart + start + len) {
            s.found = true;
            if (lp != 0) {
                s.lp = lpstart + lp;
                if (action != 0) {
                    const uint8_t *a = actions + action - 1;
                    s.filter = sleb(&a);
                }
            }
            return s;
        }
    }
    return s;
}

static _Unwind_Reason_Code continue_unwinding(_Unwind_Control_Block *ucbp, _Unwind_Context *ctx)
{
    return __gnu_unwind_frame(ucbp, ctx) == _URC_OK ? _URC_CONTINUE_UNWIND : _URC_FAILURE;
}

static _Unwind_Reason_Code install(_Unwind_Control_Block *ucbp, _Unwind_Context *ctx, uint32_t lp, int32_t sel)
{
    _Unwind_SetGR(ctx, 0, (_Unwind_Word)(uintptr_t)ucbp);
    _Unwind_SetGR(ctx, 1, (_Unwind_Word)sel);
    _Unwind_SetGR(ctx, 15, lp | 1u);                 /* Thumb */
    return _URC_INSTALL_CONTEXT;
}

_Unwind_Reason_Code __gxx_personality_v0(_Unwind_State state, _Unwind_Control_Block *ucbp, _Unwind_Context *ctx)
{
    _Unwind_SetGR(ctx, 12, (_Unwind_Word)(uintptr_t)ucbp);   /* the unwinder reads the LSDA through r12 */
    switch (state & _US_ACTION_MASK) {
    case _US_VIRTUAL_UNWIND_FRAME: {                 /* phase 1: is there a catch here? */
        if (state & _US_FORCE_UNWIND)                /* _Unwind_Backtrace walking the stack: just step past the frame */
            return continue_unwinding(ucbp, ctx);
        km_site_t s = find_site(ctx);
        if (s.lp != 0 && s.filter > 0) {
            ucbp->barrier_cache.sp = _Unwind_GetGR(ctx, 13);
            return _URC_HANDLER_FOUND;
        }
        return continue_unwinding(ucbp, ctx);
    }
    case _US_UNWIND_FRAME_STARTING: {                /* phase 2 */
        km_site_t s = find_site(ctx);
        if (s.lp != 0) {
            if (s.filter > 0) {
                if (ucbp->barrier_cache.sp == _Unwind_GetGR(ctx, 13))
                    return install(ucbp, ctx, s.lp, s.filter);
            } else {                                 /* a cleanup pad: __cxa_end_cleanup resumes with ucbp, */
                return install(ucbp, ctx, s.lp, 0);  /* the top record while the pad runs */
            }
        }
        return continue_unwinding(ucbp, ctx);
    }
    case _US_UNWIND_FRAME_RESUME:                    /* this frame's cleanup ran: go on */
        return continue_unwinding(ucbp, ctx);
    default:
        return _URC_FAILURE;
    }
}

/* End of a cleanup pad: resume the exception whose pad ran, the top record (its control block is its first member).
 * Tail-call with the pad's own registers: _Unwind_Resume snapshots them, and the PC comes from the control block
 * (UCB_SAVED_CALLSITE_ADDR). */
__attribute__((naked)) void __cxa_end_cleanup(void)
{
    __asm volatile("ldr r0, =km_eh_current\n"
                   "ldr r0, [r0]\n"
                   "b _Unwind_Resume\n"
                   ".ltorg\n");
}

/* The record stays in use until __cxa_end_catch: a handler that interrupts the catch takes the one above it. */
void *__cxa_begin_catch(void *exn)
{
    km_exception_t *e = exn;
    e->caught = e->exception;
    e->exception = NULL;
    return e;
}
KM_NOTHROW void __cxa_end_catch(void) { pop_record(); }
/* for C++ catch(...) in the runtime */
KM_NOTHROW ObjHeader *kmicro_caught_exception(void) { return km_eh_current != NULL ? km_eh_current->caught : NULL; }

KM_NOTHROW ObjHeader *Kotlin_getExceptionObject(void *holder, ObjHeader **result)
{
    (void)holder;                                    /* what __cxa_begin_catch returned: the top record */
    return km_return(result, kmicro_caught_exception());
}

/* ---- throwing ---- */

ObjHeader *Kotlin_Throwable_getMessage(ObjHeader *throwable, ObjHeader **result);
ObjHeader *Kotlin_Throwable_getStackTrace(ObjHeader *throwable, ObjHeader **result);
void Kotlin_io_Console_print(const ObjHeader *message);   /* strings.c: any length, in chunks, no allocation */
__attribute__((weak)) ObjHeader *km_throwable_cause(ObjHeader *throwable, ObjHeader **result)
    __asm__("kfun:kotlin.Throwable#<get-cause>(){}kotlin.Throwable?");   /* the virtual getter */
void Kotlin_runUnhandledExceptionHook(ObjHeader *throwable);   /* stdlib: the hook, or rethrows when none is set */
ObjHeader *kmicro_call_catching(void (*fn)(ObjHeader *), ObjHeader *arg, ObjHeader **frame, ObjHeader **slot);
__attribute__((weak)) void kmicro_on_uncaught(ObjHeader *exception) { (void)exception; }

static bool s_hook_ran;                              /* the Kotlin hook runs once, for the first uncaught exception */
static int s_reports;                                /* reports started: one that throws starts another */

static void put_hex(uint32_t v)
{
    char b[11] = "0x00000000";
    for (int i = 0; i < 8; i++)
        b[9 - i] = "0123456789abcdef"[(v >> (4 * i)) & 15u];
    kmicro_puts(b);
}

static void put_kstr(const ObjHeader *s)
{
    if (s != NULL)
        Kotlin_io_Console_print(s);
}

/* "<package>.<Class>: <message>", as Throwable.toString() prints it */
static void put_throwable(ObjHeader *e, ObjHeader **msg)
{
    const TypeInfo *t = km_type_info(e);
    if (t->packageName_ && ((const ArrayHeader *)t->packageName_)->count_ > 3) {
        put_kstr(t->packageName_);
        kmicro_puts(".");
    }
    put_kstr(t->relativeName_);
    Kotlin_Throwable_getMessage(e, msg);
    if (*msg != NULL) {
        kmicro_puts(": ");
        put_kstr(*msg);
    }
}

/* The frames of a trace. A cause's frames end with the ones it shares with the top exception: all but one of those
 * are left out, as printStackTrace() does. */
static void put_frames(const ObjHeader *trace, const ObjHeader *top)
{
    uint32_t n = trace != NULL ? ((const ArrayHeader *)trace)->count_ : 0, common = 0;
    const uint32_t *pc = trace != NULL ? km_array_data((ArrayHeader *)trace) : NULL;
    if (top != NULL) {
        uint32_t m = ((const ArrayHeader *)top)->count_;
        const uint32_t *tpc = km_array_data((ArrayHeader *)top);
        while (common < n && common < m && pc[n - 1 - common] == tpc[m - 1 - common])
            common++;
        if (common > 0)
            common--;
    }
    for (uint32_t i = 0; i < n - common; i++) {
        kmicro_puts("    at ");
        put_hex(pc[i]);
        kmicro_puts("\n");
    }
    if (common > 0) {
        kmicro_puts("    ... and ");
        kmicro_put_int((int32_t)common);
        kmicro_puts(" more common stack frames skipped\n");
    }
}

#define KM_CAUSES_MAX 8

/* The report of the stock runtime (ReportUnhandledException, printStackTrace()): the exception and every cause, each
 * with its frames. Written in C, it needs no heap and links none of the stdlib's printing code (about 30 KB), so it
 * also works inside an interrupt handler and on a full heap. Suppressed exceptions are not listed: printStackTrace()
 * in a catch block shows them. */
void kmicro_report_exception(ObjHeader *e)
{
    struct { FrameOverlay f; ObjHeader *cur, *msg, *trace, *top; } fr = { { 0, 0, 0 }, e, 0, 0, 0 };
    EnterFrame((ObjHeader **)&fr, 0, sizeof fr / sizeof(ObjHeader *));
    const ObjHeader *seen[KM_CAUSES_MAX];
    int n = 0;
    kmicro_puts("Uncaught Kotlin exception: ");
    for (;;) {
        put_throwable(fr.cur, &fr.msg);
        kmicro_puts("\n");
        Kotlin_Throwable_getStackTrace(fr.cur, &fr.trace);
        put_frames(fr.trace, n == 0 ? NULL : fr.top);
        if (n == 0)
            fr.top = fr.trace;
        seen[n++] = fr.cur;
        if (km_throwable_cause == NULL || km_throwable_cause(fr.cur, &fr.cur) == NULL)
            break;
        kmicro_puts("Caused by: ");
        bool again = false;
        for (int i = 0; i < n; i++)
            again |= seen[i] == fr.cur;
        if (again) {
            kmicro_puts("[CIRCULAR REFERENCE, SEE ABOVE: ");
            put_throwable(fr.cur, &fr.msg);
            kmicro_puts("]\n");
            break;
        }
        if (n == KM_CAUSES_MAX) {
            kmicro_puts("...\n");
            break;
        }
    }
    LeaveFrame((ObjHeader **)&fr, 0, sizeof fr / sizeof(ObjHeader *));
}

/* The hook set by setUnhandledExceptionHook (Exceptions.cpp processUnhandledException). Returns NULL when it ran and
 * returned, else the exception to terminate with: the hook's own when it threw, e itself when no hook is set. Inside an
 * interrupt handler the hook is skipped (it may allocate); kmicro_on_uncaught is the C hook that runs there too.
 * The stdlib creates the object that holds the hook on first use: with no hook ever set, that takes two small
 * allocations, and on a heap that is full at that moment the program stops with "out of memory" before the report. */
static ObjHeader *run_hook(ObjHeader *e, ObjHeader **frame, ObjHeader **slot)
{
    if (km_in_interrupt())
        return e;
    return kmicro_call_catching(Kotlin_runUnhandledExceptionHook, e, frame, slot);
}

/* Report e and stop; with hook, as for an exception nothing caught: the Kotlin hook runs first, then the exception it
 * leaves is reported. A hook may itself call terminateWithUnhandledException. An exception that escapes from the
 * report (a message getter that throws) is reported in turn. */
__attribute__((noreturn)) static void terminate(ObjHeader *e, bool hook)
{
    struct { FrameOverlay f; ObjHeader *e, *thrown; } fr = { { 0, 0, 0 }, e, 0 };
    EnterFrame((ObjHeader **)&fr, 0, sizeof fr / sizeof(ObjHeader *));
    if (hook && !s_hook_ran && s_reports == 0) {
        s_hook_ran = true;
        ObjHeader *t = run_hook(fr.e, (ObjHeader **)&fr, &fr.thrown);
        if (t != NULL)
            fr.e = t;
    }
    if (s_reports == 2)
        kmicro_panic("uncaught Kotlin exception while reporting an uncaught exception");
    if (s_reports++ > 0)
        kmicro_puts("\n");                           /* the report before stopped mid-line */
    kmicro_report_exception(fr.e);
    kmicro_on_uncaught(fr.e);
    kmicro_panic("uncaught Kotlin exception");
}

__attribute__((noreturn)) void ThrowException(ObjHeader *exception)
{
    uint32_t context = running_context();
    /* The same code throwing again before its own exception reached a catch: a cleanup pad that throws. */
    if (s_depth > 0 && s_recs[s_depth - 1].exception != NULL && s_recs[s_depth - 1].context == context)
        kmicro_panic("exception thrown while another one is being unwound");
    if (s_depth == KM_EH_DEPTH)
        kmicro_panic("interrupt handlers that throw are nested deeper than KM_EH_DEPTH");
    km_exception_t *r = push_record();
    memset(&r->ucb, 0, sizeof r->ucb);
    memcpy(r->ucb.exception_class, "KMICROKT", 8);
    r->caught = NULL;
    r->context = context;
    r->exception = exception;
    _Unwind_Reason_Code rc = _Unwind_RaiseException(&r->ucb);
    /* Only returns when no handler was found (end of stack, or a frame without unwind tables). The hook and the
     * report run Kotlin code that may throw and catch exceptions of its own, so this one is no longer in flight. */
    (void)rc;
    ObjHeader *e = r->exception;
    pop_record();
    terminate(e, true);
}

/* kotlin.native.processUnhandledException: the hook, and termination when there is none or it throws. */
void Kotlin_processUnhandledException(ObjHeader *e)
{
    struct { FrameOverlay f; ObjHeader *thrown; } fr = { { 0, 0, 0 }, 0 };
    EnterFrame((ObjHeader **)&fr, 0, sizeof fr / sizeof(ObjHeader *));
    ObjHeader *t = run_hook(e, (ObjHeader **)&fr, &fr.thrown);
    if (t != NULL)
        terminate(t, false);
    LeaveFrame((ObjHeader **)&fr, 0, sizeof fr / sizeof(ObjHeader *));
}
__attribute__((noreturn)) void Kotlin_terminateWithUnhandledException(ObjHeader *e) { terminate(e, false); }
__attribute__((noreturn)) void _ZSt9terminatev(void) { kmicro_panic("std::terminate"); }

/* ---- stack traces: return addresses through the same unwind tables ---- */

/* The trace leaves out the frames that only build the exception, as the stock runtime does: Kotlin_getCurrentStackTrace
 * itself and the Throwable primary constructor that calls it. They are recognised by their function's address, not
 * counted: LTO often inlines the constructor into a subclass constructor or into the function that throws, and a fixed
 * count then drops that function instead. A constructor that was inlined somewhere stays as the frame it became. */
__attribute__((noinline)) ObjHeader *Kotlin_getCurrentStackTrace(ObjHeader **result);
__attribute__((weak)) void km_throwable_init(void)
    __asm__("kfun:kotlin.Throwable#<init>(kotlin.String?;kotlin.Throwable?){}");

#define KM_TRACE_MAX 12
typedef struct { uint32_t pc[KM_TRACE_MAX], last_pc, last_sp; int n; } km_trace_t;

static _Unwind_Reason_Code trace_fn(_Unwind_Context *ctx, void *arg)
{
    km_trace_t *t = arg;
    uint32_t pc = (uint32_t)(_Unwind_GetGR(ctx, 15) & ~1u), sp = _Unwind_GetGR(ctx, 13);
    if (pc == t->last_pc && sp == t->last_sp)
        return _URC_END_OF_STACK;                    /* the walk did not move: never one frame twice */
    t->last_pc = pc;
    t->last_sp = sp;
    if (t->n == 0) {
        uint32_t fn = (uint32_t)_Unwind_GetRegionStart(ctx) & ~1u;
        uint32_t ctor = (uint32_t)(uintptr_t)km_throwable_init & ~1u;
        if (fn == ((uint32_t)(uintptr_t)Kotlin_getCurrentStackTrace & ~1u) || (ctor != 0 && fn == ctor))
            return _URC_NO_REASON;
    }
    if (t->n >= KM_TRACE_MAX)
        return _URC_END_OF_STACK;
    t->pc[t->n++] = pc;
    return _URC_NO_REASON;
}

extern const TypeInfo *theNativePtrArrayTypeInfo;
ObjHeader *Kotlin_getCurrentStackTrace(ObjHeader **result)
{
    km_trace_t t;
    t.n = 0;
    t.last_pc = t.last_sp = 0;
    _Unwind_Backtrace(trace_fn, &t);
    ObjHeader *a = kmicro_alloc_array(theNativePtrArrayTypeInfo, t.n, result);
    memcpy(km_array_data((ArrayHeader *)a), t.pc, (size_t)t.n * 4u);
    return a;
}

/* NativePtrArray (Arrays.cpp), the type of a stack trace: printStackTrace() of an exception with a cause or a
 * suppressed exception compares its frames with the top exception's. Elements are 4-byte addresses. */
KM_NOTHROW int32_t Kotlin_NativePtrArray_getArrayLength(const ObjHeader *a)
{
    return (int32_t)((const ArrayHeader *)a)->count_;
}
void *Kotlin_NativePtrArray_get(const ObjHeader *a, int32_t i)
{
    if ((uint32_t)i >= ((const ArrayHeader *)a)->count_)
        ThrowArrayIndexOutOfBoundsException();
    return ((void **)km_array_data((ArrayHeader *)a))[i];
}
void Kotlin_NativePtrArray_set(ObjHeader *a, int32_t i, void *v)
{
    if ((uint32_t)i >= ((const ArrayHeader *)a)->count_)
        ThrowArrayIndexOutOfBoundsException();
    ((void **)km_array_data((ArrayHeader *)a))[i] = v;
}

/* Addresses as text: the host tool turns them into Kotlin function names from the ELF symbols. */
ObjHeader *CreateStringFromCString(const char *c, ObjHeader **result);
ObjHeader *Kotlin_getStackTraceStrings(const ObjHeader *trace, ObjHeader **result)
{
    const ArrayHeader *t = (const ArrayHeader *)trace;
    uint32_t n = t->count_;
    struct { FrameOverlay f; ObjHeader *arr, *s; } fr = { { 0, 0, 0 }, 0, 0 };
    EnterFrame((ObjHeader **)&fr, 0, sizeof fr / sizeof(ObjHeader *));
    kmicro_alloc_array(theArrayTypeInfo, (int32_t)n, &fr.arr);
    for (uint32_t i = 0; i < n; i++) {
        char b[11] = "0x00000000";
        uint32_t v = ((const uint32_t *)km_array_data((ArrayHeader *)t))[i];
        for (int k = 0; k < 8; k++)
            b[9 - k] = "0123456789abcdef"[(v >> (4 * k)) & 15u];
        CreateStringFromCString(b, &fr.s);
        km_array_refs((ArrayHeader *)fr.arr)[i] = fr.s;
    }
    ObjHeader *r = km_return(result, fr.arr);
    LeaveFrame((ObjHeader **)&fr, 0, sizeof fr / sizeof(ObjHeader *));
    return r;
}

/* Copyright 2010-2024 JetBrains s.r.o. and Kotlin Programming Language contributors.
 * Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
/* kotlin.native.Platform, exitProcess, readln, GC.schedule/lastGCInfo, Uuid.random and the Debugging queries
 * (Runtime.cpp, Natives.cpp, Console.cpp, Random.cpp, Memory.cpp of the stock runtime). Board input and entropy come
 * through weak hooks; without them readln sees the end of input and Uuid.random stops with the hook's name. */
#include <string.h>
#include "kmicro.h"

void kmicro_exit(int code);
ObjHeader *CreateStringFromUtf8(const char *utf8, uint32_t n, ObjHeader **result);
extern const TypeInfo *theByteArrayTypeInfo;

/* ---- Platform (values as the stock runtime gives them for ARM32; enum ordinals of Platform.kt) ---- */

KM_NOTHROW int32_t Konan_Platform_getOsFamily(void) { return 0; }          /* OsFamily.UNKNOWN: no OS */
KM_NOTHROW int32_t Konan_Platform_getCpuArchitecture(void) { return 1; }   /* CpuArchitecture.ARM32 */
KM_NOTHROW int32_t Konan_Platform_isLittleEndian(void) { return 1; }
KM_NOTHROW int32_t Konan_Platform_canAccessUnaligned(void) { return 0; }   /* LDRD/LDM/VLDR trap when unaligned */
KM_NOTHROW bool Konan_Platform_isDebugBinary(void) { return false; }
KM_NOTHROW int32_t Konan_Platform_getAvailableProcessors(void) { return 1; }
KM_NOTHROW int32_t Konan_Platform_getAllocator(void) { return 1; }         /* Allocator.PER_OBJECT */
/* No program name and no environment (KOTLIN_NATIVE_AVAILABLE_PROCESSORS): both null. */
KM_NOTHROW ObjHeader *Konan_Platform_getProgramName(ObjHeader **result) { return km_return(result, NULL); }
KM_NOTHROW ObjHeader *Konan_Platform_getAvailableProcessorsEnv(ObjHeader **result) { return km_return(result, NULL); }

/* ---- kotlin.system.exitProcess: the board's exit ---- */

__attribute__((noreturn)) void Kotlin_system_exitProcess(int32_t status)
{
    kmicro_exit(status);
    for (;;) {
    }
}

/* ---- GC (Memory.cpp, GCStatistics.cpp) ---- */

/* One thread: collect now. Inside an interrupt handler the request is dropped: a collection there would miss the
 * references the interrupted code holds only in registers (the heap collects anyway when it runs out). */
void Kotlin_native_internal_GC_schedule(ObjHeader *thiz)
{
    (void)thiz;
    if (!km_in_interrupt())
        kmicro_gc();
}
/* GC.lastGCInfo: the standard library's builder calls this, and it calls the builder's setters (GCInfo.kt) with what
 * mm.c recorded about the last collection. A GCInfo needs the start and end times, so collections are timed from the
 * first call on, with the board's kmicro_time_ns; one that ran before, or on a board without that clock, sets
 * nothing, and GC.lastGCInfo is null. The collection is one pause, and it is over when collect() returns: there is
 * no second pause and no cleanup after it. The setters allocate, which may collect: the record is copied first. */
void Kotlin_Internal_GC_GCInfoBuilder_setEpoch(ObjHeader *builder, int64_t value);
void Kotlin_Internal_GC_GCInfoBuilder_setStartTime(ObjHeader *builder, int64_t value);
void Kotlin_Internal_GC_GCInfoBuilder_setEndTime(ObjHeader *builder, int64_t value);
void Kotlin_Internal_GC_GCInfoBuilder_setFirstPauseRequestTime(ObjHeader *builder, int64_t value);
void Kotlin_Internal_GC_GCInfoBuilder_setFirstPauseStartTime(ObjHeader *builder, int64_t value);
void Kotlin_Internal_GC_GCInfoBuilder_setFirstPauseEndTime(ObjHeader *builder, int64_t value);
void Kotlin_Internal_GC_GCInfoBuilder_setRootSet(ObjHeader *builder, int64_t thread_local, int64_t stack,
                                                 int64_t global, int64_t stable);
void Kotlin_Internal_GC_GCInfoBuilder_setMarkStats(ObjHeader *builder, int64_t marked);
void Kotlin_Internal_GC_GCInfoBuilder_setSweepStats(ObjHeader *builder, const char *name, int64_t kept,
                                                    int64_t swept);
void Kotlin_Internal_GC_GCInfoBuilder_setMemoryUsageBefore(ObjHeader *builder, const char *name, int64_t bytes);
void Kotlin_Internal_GC_GCInfoBuilder_setMemoryUsageAfter(ObjHeader *builder, const char *name, int64_t bytes);

/* Weak in this file: the compiler then cannot take the hook for a function other than km_no_clock, which it is on a
 * board without a clock (time.c). */
int64_t kmicro_time_ns(void) __attribute__((weak));

void Kotlin_Internal_GC_GCInfoBuilder_Fill(ObjHeader *builder, int32_t id)
{
    if (kmicro_time_ns != km_no_clock)
        km_gc_clock = kmicro_time_ns;
    const km_gc_info_t g = km_gc_info;
    if (id != 0 || !g.timed)                         /* 0 is the last collection, the only one the stdlib asks for */
        return;
    Kotlin_Internal_GC_GCInfoBuilder_setEpoch(builder, g.epoch);
    Kotlin_Internal_GC_GCInfoBuilder_setStartTime(builder, g.start_ns);
    Kotlin_Internal_GC_GCInfoBuilder_setEndTime(builder, g.end_ns);
    Kotlin_Internal_GC_GCInfoBuilder_setFirstPauseRequestTime(builder, g.start_ns);
    Kotlin_Internal_GC_GCInfoBuilder_setFirstPauseStartTime(builder, g.start_ns);
    Kotlin_Internal_GC_GCInfoBuilder_setFirstPauseEndTime(builder, g.end_ns);
    Kotlin_Internal_GC_GCInfoBuilder_setRootSet(builder, g.tls_roots, g.stack_roots, g.global_roots, g.stable_roots);
    Kotlin_Internal_GC_GCInfoBuilder_setMarkStats(builder, g.kept);
    Kotlin_Internal_GC_GCInfoBuilder_setSweepStats(builder, "heap", g.kept, g.swept);
    Kotlin_Internal_GC_GCInfoBuilder_setMemoryUsageBefore(builder, "heap", g.bytes_before);
    Kotlin_Internal_GC_GCInfoBuilder_setMemoryUsageAfter(builder, "heap", g.bytes_after);
}
/* There is no main-thread run loop to process finalizers on (as on every non-Apple target). */
KM_NOTHROW bool Kotlin_native_runtime_GC_MainThreadFinalizerProcessor_isAvailable(ObjHeader *thiz)
{
    (void)thiz;
    return false;
}

/* ---- Debugging (Runtime.cpp): Kotlin code always runs in the runnable state here ---- */

KM_NOTHROW bool Kotlin_Debugging_isThreadStateRunnable(void) { return true; }
KM_NOTHROW bool Kotlin_Debugging_isPermanent(const ObjHeader *obj) { return km_tag(obj) == KM_TAG_PERMANENT; }
KM_NOTHROW bool Kotlin_Debugging_isStack(const ObjHeader *obj) { return km_tag(obj) == KM_TAG_STACK; }

/* ---- readln / readlnOrNull / readLine (Console.cpp) ---- */

/* The next input byte, waiting for it if needed; -1 at the end of input. The default has no input. */
__attribute__((weak)) int kmicro_getc(void) { return -1; }

/* One line without its "\n" (and a "\r" before it), decoded as UTF-8; null at the end of input with nothing read.
 * The bytes collect in a ByteArray in the result slot (a GC root), which doubles when full. */
static ObjHeader *read_line(ObjHeader **result)
{
    uint32_t n = 0, cap = 0;
    int c;
    *result = NULL;
    while ((c = kmicro_getc()) >= 0 && c != '\n') {
        if (n == cap) {
            ObjHeader *old = *result;
            cap = cap ? cap * 2u : 32u;
            ObjHeader *a = kmicro_alloc_array(theByteArrayTypeInfo, (int32_t)cap, result);   /* old stays rooted */
            if (old != NULL)
                memcpy(km_array_data((ArrayHeader *)a), km_array_data((ArrayHeader *)old), n);
        }
        ((uint8_t *)km_array_data((ArrayHeader *)*result))[n++] = (uint8_t)c;
    }
    if (n == 0 && c < 0)
        return km_return(result, NULL);
    const uint8_t *bytes = n ? km_array_data((ArrayHeader *)*result) : (const uint8_t *)"";
    if (c == '\n' && n > 0 && bytes[n - 1] == '\r')
        n--;
    return CreateStringFromUtf8((const char *)bytes, n, result);    /* the bytes stay rooted until it allocates */
}
ObjHeader *Kotlin_io_Console_readlnOrNull(ObjHeader **result) { return read_line(result); }
ObjHeader *Kotlin_io_Console_readLine(ObjHeader **result) { return read_line(result); }

/* ---- newlib's stdio (printf, puts; from C, or from Kotlin through platform.posix) ---- */

/* The system call newlib's streams write through, which fails in libnosys: stdout and stderr go where println goes.
 * Weak: a board's own _write takes its place. Without one, kmicro_puts and kmicro_write must not print with stdio
 * themselves: they would be called again from inside it. */
__attribute__((weak)) int _write(int fd, const char *buf, int len)
{
    if (fd != 1 && fd != 2)
        return -1;
    kmicro_write(buf, (size_t)len);
    return len;
}

/* ---- Uuid.random(): random bytes from the board ---- */

/* Fills buf with n bytes from a true entropy source (a hardware RNG). There is no safe default, so without the hook
 * Uuid.random() stops instead of returning a predictable UUID. */
__attribute__((weak)) void kmicro_random_bytes(void *buf, size_t n)
{
    (void)buf;
    (void)n;
    kmicro_panic("Uuid.random() needs an entropy source: define void kmicro_random_bytes(void *buf, size_t n)");
}
void Kotlin_Uuid_getRandomBytes(ObjHeader *bytes, int32_t size)
{
    kmicro_random_bytes(km_array_data((ArrayHeader *)bytes), (size_t)size);
}

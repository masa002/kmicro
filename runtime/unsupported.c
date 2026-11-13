/* Stdlib natives kmicro does not support. Each is defined with the stock signature, so a board build links and
 * link-time optimisation sees a well-typed call, and calling one stops the program with a message that names the
 * Kotlin API. tools/missing_natives.py lists them with the rest of the stdlib's natives. */
#include "kmicro.h"

#pragma GCC diagnostic ignored "-Wunused-parameter"

#define UNSUPPORTED(api) kmicro_panic(api " is not supported on kmicro")

/* ---- kotlin.native.ref.WeakReference: weak references need the collector to clear them (Memory.cpp) ---- */

ObjHeader *Konan_getWeakReferenceImpl(ObjHeader *referent, ObjHeader **result)
{
    UNSUPPORTED("kotlin.native.ref.WeakReference");
}

/* ---- kotlin.native.concurrent.Worker and Future: one thread, no scheduler (Worker.cpp) ---- */

#define WORKER UNSUPPORTED("kotlin.native.concurrent.Worker")
int32_t Kotlin_Worker_startInternal(bool error_reporting, void *name) { WORKER; }
int32_t Kotlin_Worker_currentInternal(void) { WORKER; }
int32_t Kotlin_Worker_requestTerminationWorkerInternal(int32_t id, bool process) { WORKER; }
int32_t Kotlin_Worker_executeInternal(int32_t id, void *argument, void *job) { WORKER; }
void Kotlin_Worker_executeAfterInternal(int32_t id, void *job, int64_t after_us) { WORKER; }
bool Kotlin_Worker_processQueueInternal(int32_t id) { WORKER; }
bool Kotlin_Worker_parkInternal(int32_t id, int64_t timeout_us, bool process) { WORKER; }
void *Kotlin_Worker_getNameInternal(int32_t id) { WORKER; }
int32_t Kotlin_Worker_stateOfFuture(int32_t id) { WORKER; }
void *Kotlin_Worker_consumeFuture(int32_t id) { WORKER; }
bool Kotlin_Worker_waitForAnyFuture(int32_t version, int32_t millis) { WORKER; }
int32_t Kotlin_Worker_versionToken(void) { WORKER; }
void Kotlin_Worker_waitTermination(int32_t id) { WORKER; }
uint64_t Kotlin_Worker_getPlatformThreadIdInternal(int32_t id) { WORKER; }
ObjHeader *Kotlin_Worker_getActiveWorkersInternal(ObjHeader **result) { WORKER; }
ObjHeader *Kotlin_Worker_invokeCFunction(void *job, ObjHeader *argument, ObjHeader **result) { WORKER; }

/* ---- threads and monitors of kotlin.native.internal.concurrent (Thread.cpp, Monitor.cpp) ---- */

#define THREADS UNSUPPORTED("kotlin.native.internal.concurrent threads and monitors")
void Kotlin_native_concurrent_startThreadImpl(void *routine) { THREADS; }
uint64_t Kotlin_native_concurrent_currentThreadId(void) { THREADS; }
void *Kotlin_Monitor_allocate(ObjHeader *companion) { THREADS; }
void Kotlin_Monitor_destroy(void *monitor) { THREADS; }
void Kotlin_Monitor_enter(void *monitor) { THREADS; }
void Kotlin_Monitor_leave(void *monitor) { THREADS; }
void Kotlin_Monitor_wait(void *monitor, int64_t timeout_ms) { THREADS; }
void Kotlin_Monitor_notify(void *monitor) { THREADS; }
void Kotlin_Monitor_notifyAll(void *monitor) { THREADS; }

/* ---- kotlin.native.runtime.GC tuning: the heap is one KM_HEAP_BYTES arena, collected when it is full ---- */

#define GC_TUNING(prop) UNSUPPORTED("GC." prop " (heap tuning)")
bool Kotlin_native_internal_GC_getTuneThreshold(ObjHeader *gc) { GC_TUNING("autotune"); }
void Kotlin_native_internal_GC_setTuneThreshold(ObjHeader *gc, bool v) { GC_TUNING("autotune"); }
int64_t Kotlin_native_internal_GC_getRegularGCIntervalMicroseconds(ObjHeader *gc) { GC_TUNING("regularGCInterval"); }
void Kotlin_native_internal_GC_setRegularGCIntervalMicroseconds(ObjHeader *gc, int64_t v)
{
    GC_TUNING("regularGCInterval");
}
int64_t Kotlin_native_internal_GC_getTargetHeapBytes(ObjHeader *gc) { GC_TUNING("targetHeapBytes"); }
void Kotlin_native_internal_GC_setTargetHeapBytes(ObjHeader *gc, int64_t v) { GC_TUNING("targetHeapBytes"); }
double Kotlin_native_internal_GC_getTargetHeapUtilization(ObjHeader *gc) { GC_TUNING("targetHeapUtilization"); }
void Kotlin_native_internal_GC_setTargetHeapUtilization(ObjHeader *gc, double v) { GC_TUNING("targetHeapUtilization"); }
int64_t Kotlin_native_internal_GC_getMinHeapBytes(ObjHeader *gc) { GC_TUNING("minHeapBytes"); }
void Kotlin_native_internal_GC_setMinHeapBytes(ObjHeader *gc, int64_t v) { GC_TUNING("minHeapBytes"); }
int64_t Kotlin_native_internal_GC_getMaxHeapBytes(ObjHeader *gc) { GC_TUNING("maxHeapBytes"); }
void Kotlin_native_internal_GC_setMaxHeapBytes(ObjHeader *gc, int64_t v) { GC_TUNING("maxHeapBytes"); }
double Kotlin_native_internal_GC_getHeapTriggerCoefficient(ObjHeader *gc) { GC_TUNING("heapTriggerCoefficient"); }
void Kotlin_native_internal_GC_setHeapTriggerCoefficient(ObjHeader *gc, double v)
{
    GC_TUNING("heapTriggerCoefficient");
}
bool Kotlin_native_internal_GC_getPauseOnTargetHeapOverflow(ObjHeader *gc) { GC_TUNING("pauseOnTargetHeapOverflow"); }
void Kotlin_native_internal_GC_setPauseOnTargetHeapOverflow(ObjHeader *gc, bool v)
{
    GC_TUNING("pauseOnTargetHeapOverflow");
}

/* GC.MainThreadFinalizerProcessor needs an Apple main run loop; its `available` is false (system.c). */
#define FINALIZERS UNSUPPORTED("GC.MainThreadFinalizerProcessor")
int64_t Kotlin_native_runtime_GC_MainThreadFinalizerProcessor_getMaxTimeInTask(ObjHeader *p) { FINALIZERS; }
void Kotlin_native_runtime_GC_MainThreadFinalizerProcessor_setMaxTimeInTask(ObjHeader *p, int64_t v) { FINALIZERS; }
int64_t Kotlin_native_runtime_GC_MainThreadFinalizerProcessor_getMinTimeBetweenTasks(ObjHeader *p) { FINALIZERS; }
void Kotlin_native_runtime_GC_MainThreadFinalizerProcessor_setMinTimeBetweenTasks(ObjHeader *p, int64_t v)
{
    FINALIZERS;
}
uint64_t Kotlin_native_runtime_GC_MainThreadFinalizerProcessor_getBatchSize(ObjHeader *p) { FINALIZERS; }
void Kotlin_native_runtime_GC_MainThreadFinalizerProcessor_setBatchSize(ObjHeader *p, uint64_t v) { FINALIZERS; }

/* ---- memory diagnostics ---- */

bool Kotlin_native_runtime_Debugging_dumpMemory(ObjHeader *debugging, int64_t fd)    /* dumpMemory(fd: Long) */
{
    UNSUPPORTED("kotlin.native.runtime.Debugging.dumpMemory");
}
int64_t Kotlin_MemoryUsageInfo_getPeakResidentSetSizeBytes(void)
{
    UNSUPPORTED("MemoryUsageInfo.peakResidentSetSizeBytes (kmicro_stats has the heap use)");
}

/* ---- kotlin.native.ImmutableBlob (immutableBlobOf has been an error since Kotlin 2.1) ---- */

ObjHeader *Kotlin_ImmutableBlob_toByteArray(const ObjHeader *blob, int32_t start, int32_t end, ObjHeader **result)
{
    UNSUPPORTED("kotlin.native.ImmutableBlob");
}
void *Kotlin_ImmutableBlob_asCPointerImpl(ObjHeader *blob, int32_t offset)
{
    UNSUPPORTED("kotlin.native.ImmutableBlob");
}

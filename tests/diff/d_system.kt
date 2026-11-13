@file:OptIn(kotlin.experimental.ExperimentalNativeApi::class, kotlin.native.runtime.NativeRuntimeApi::class)

// Platform, GC.schedule and exitProcess. Only what is the same on the host and on the board is printed: osFamily,
// cpuArchitecture, canAccessUnaligned, the processor count, programName and GC.lastGCInfo differ (kmicro: UNKNOWN,
// ARM32, false, 1, null, null).

import kotlin.native.CpuArchitecture
import kotlin.native.Platform
import kotlin.native.runtime.GC

fun main() {
    println("little endian: ${Platform.isLittleEndian}, debug: ${Platform.isDebugBinary}")
    println("cpu known: ${Platform.cpuArchitecture != CpuArchitecture.UNKNOWN}, bitness: ${Platform.cpuArchitecture.bitness > 0}")
    println("processors: ${Platform.getAvailableProcessors() >= 1}, finalizer processor: ${GC.MainThreadFinalizerProcessor.available}")
    GC.schedule()
    println("schedule ok")
    val list = MutableList(100) { "item $it" }
    GC.schedule()
    println("after schedule: ${list.size} ${list[99]}")
    kotlin.system.exitProcess(0)
    @Suppress("UNREACHABLE_CODE")
    println("not reached")
}

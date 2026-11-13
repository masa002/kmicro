@file:OptIn(kotlin.native.runtime.NativeRuntimeApi::class)

package isr

import kotlin.native.runtime.GC

// What main.c's SysTick_Handler calls, one function per test case. A handler must not allocate or collect: the first
// two allocate (the runtime stops with "allocation inside an interrupt handler"), the third collects ("garbage
// collection inside an interrupt handler"). GC.schedule() is allowed and does nothing there.

fun allocInHandler(n: Int): Int = "tick $n".length

fun toStringInHandler(n: Int): Int = n.toString().length

fun collectInHandler(): Int {
    GC.collect()
    return 1
}

fun scheduleGc() {
    GC.schedule()
}

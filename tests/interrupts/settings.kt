package isr

import isr.sub.Registry

// Globals that allocate when they are created, the first time code uses this file, an object or the sub-package's
// object. Inside an interrupt handler that creation is refused ("Kotlin globals first used inside an interrupt
// handler"), unless kt_init_all() (kbuild --init-all) created them at boot. Reading them allocates nothing.

val limits = intArrayOf(5, 10, 20)
val names = listOf("low", "mid", "high")

object Calibration {
    val offsets = IntArray(3) { it * 2 }
}

fun readSettings(): Int = limits.sum() + names.size + Calibration.offsets.sum() + Registry.slots.size

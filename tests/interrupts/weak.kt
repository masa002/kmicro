// Copyright 2026 the kmicro authors (NOTICE).
// SPDX-License-Identifier: Apache-2.0
@file:OptIn(kotlin.experimental.ExperimentalNativeApi::class)

package isr

import kotlin.native.ref.WeakReference

// A handler may read a WeakReference while the collector works: SysTick takes the objects out of the references
// below and keeps the last one in a global, while the main code makes objects that only a WeakReference knows and
// allocates, which under KM_GC_STRESS collects before every allocation. What get() gives the handler must be a whole
// object, and the one it kept must stay: an object the collector freed is overwritten (0xA5 under stress, or reused
// by a junk Box), which the checks see as a wrong value.

class Probe(val value: Int)

val probes = arrayOfNulls<WeakReference<Probe>>(8)
var rescued: Probe? = null
var taken = 0
var badInHandler = 0

// in the handler
fun weakRead(): Int {
    for (w in probes) {
        val p = w?.get() ?: continue
        if (p.value != 3000001) badInHandler++
        taken++
        rescued = p
    }
    return taken
}

// its own function, so that no frame slot of the caller keeps the Probe alive
fun plant(i: Int) {
    probes[i % probes.size] = WeakReference(Probe(3000001))
}

// in main; returns the bad reads
fun weakRounds(rounds: Int): Int {
    var bad = 0
    repeat(rounds) { i ->
        plant(i)
        val junk = Array(4) { Box(it) }
        val r = rescued
        if (r != null && r.value != 3000001 || junk.size != 4) bad++
        if (i % 5 == 0) rescued = null
    }
    return bad + badInHandler
}

fun weakTaken(): Int = taken

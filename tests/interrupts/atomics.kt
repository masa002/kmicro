// Copyright 2026 the kmicro authors (NOTICE).
// SPDX-License-Identifier: Apache-2.0
@file:OptIn(kotlin.concurrent.atomics.ExperimentalAtomicApi::class)
package isr

import kotlin.concurrent.Volatile
import kotlin.concurrent.atomics.AtomicArray
import kotlin.concurrent.atomics.AtomicInt
import kotlin.concurrent.atomics.AtomicIntArray
import kotlin.concurrent.atomics.AtomicLong
import kotlin.concurrent.atomics.AtomicLongArray
import kotlin.concurrent.atomics.AtomicReference
import kotlin.concurrent.atomics.incrementAndFetch
import kotlin.concurrent.atomics.incrementAndFetchAt

// What a handler may use and no other file of this folder does: the atomics, the atomic arrays, a @Volatile field
// and println of a string that exists. kt_init_all() creates the objects; the handler then allocates nothing, and
// tools/isr_check.py finds no path to an allocation. Returns the checks that held: 5.

val events = AtomicInt(0)
val micros = AtomicLong(0L)
val latest = AtomicReference<Box?>(null)
val perLine = AtomicIntArray(4)
val totals = AtomicLongArray(4)
val owners = AtomicArray<Box?>(4) { null }
val even = Box(2)
val odd = Box(1)
@Volatile var level = 0L

const val PRINTED = "a handler printed this line"

fun atomicsInHandler(n: Int): Int {
    var ok = 0
    val line = n and 3
    if (events.incrementAndFetch() == n && events.compareAndSet(n, n) && events.fetchAndAdd(0) == n) ok += 1
    if (micros.addAndFetch(1L shl 33) == n.toLong() shl 33 && micros.exchange(micros.load()) != 0L) ok += 1
    val box = if (n % 2 == 0) even else odd
    val before = latest.exchange(box)
    if (before !== box && latest.compareAndSet(box, box) && latest.load() === box) ok += 1
    owners.storeAt(line, box)
    if (perLine.incrementAndFetchAt(line) > 0 && totals.addAndFetchAt(line, 1L shl 40) >= 1L shl 40 &&
        owners.exchangeAt(line, box) === box) ok += 1
    level += n
    if (level > 0L) ok += 1
    if (n == 1) println(PRINTED)
    return ok
}

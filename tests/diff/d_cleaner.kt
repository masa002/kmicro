// Copyright 2026 the kmicro authors (NOTICE).
// SPDX-License-Identifier: Apache-2.0
// createCleaner: the cleanup action runs once, after a collection found the object that holds the Cleaner dead, and
// GC.collect() returns after the actions of the objects it found. An object is made in a function of its own, so
// that no frame slot of main keeps it alive. The actions only count and record, and main prints: the stock runtime
// runs them on another thread.
@file:OptIn(kotlin.experimental.ExperimentalNativeApi::class, kotlin.native.runtime.NativeRuntimeApi::class)

import kotlin.concurrent.AtomicInt
import kotlin.native.ref.Cleaner
import kotlin.native.ref.createCleaner
import kotlin.native.runtime.GC

val closed = AtomicInt(0)
val sum = AtomicInt(0)
val built = AtomicInt(0)

// A resource that must be given back: the Cleaner holds its handle, not the Port itself.
class Port(val id: Int) {
    private val handle = id * 10
    val cleaner: Cleaner = createCleaner(handle) { h ->
        closed.incrementAndGet()
        sum.addAndGet(h)
    }
}

class Buffer(n: Int) {
    val cleaner = createCleaner(n) { size ->
        // a cleanup action may allocate
        val text = buildString { repeat(size) { append("x$it") } }
        built.addAndGet(text.length + listOf(size, size * 2).sum())
    }
}

class Failing {
    val cleaner = createCleaner(Unit) {
        closed.incrementAndGet()
        throw IllegalStateException("thrown by a cleanup action")
    }
}

// Each of these dies before its cleaner runs, and its own Cleaner (made by the action of another) runs later.
class Chain(val left: Int) {
    val cleaner = createCleaner(left) { n ->
        closed.incrementAndGet()
        if (n > 0) Chain(n - 1)
    }
}

class Holder(var cleaner: Cleaner?)

fun open(n: Int) {
    repeat(n) { Port(it + 1) }
}

fun buffer(n: Int) {
    Buffer(n)
}

fun failing() {
    Failing()
}

fun chain(n: Int) {
    Chain(n)
}

fun hold(h: Holder) {
    h.cleaner = createCleaner(7) { sum.addAndGet(it * 1000) }
}

fun openKept(n: Int): List<Port> = List(n) { Port(100 + it) }

fun churn(): Int {
    var total = 0
    repeat(2000) { total += "junk $it".length }
    return total
}

fun main() {
    open(3)
    GC.collect()
    println("3 ports dropped: closed ${closed.value}, handles ${sum.value}")

    val kept = openKept(4)
    open(30)                                // more of them at once than the StableRef table has slots
    GC.collect()
    println("30 dropped, 4 kept: closed ${closed.value}, handles ${sum.value}")
    println("churn ${churn()}, kept ${kept.sumOf { it.id }}")
    GC.collect()
    println("the kept ones are still open: closed ${closed.value}")

    buffer(40)
    GC.collect()
    println("an action that allocates: built ${built.value}")

    val before = closed.value
    failing()
    GC.collect()
    println("an action that throws: ran ${closed.value - before}, and the program goes on")

    val start = closed.value
    chain(3)
    repeat(5) { GC.collect() }
    println("actions that make objects with cleaners: ${closed.value - start}")

    // a Cleaner of its own, kept in a field: it runs when the field lets it go
    val holder = Holder(null)
    hold(holder)
    GC.collect()
    println("held cleaner: handles ${sum.value}")
    holder.cleaner = null
    GC.collect()
    println("dropped: handles ${sum.value}")
}

// Copyright 2026 the kmicro authors (NOTICE).
// SPDX-License-Identifier: Apache-2.0
// A cleanup action and globals that are still being created: the object dies while the initializer of this file,
// or of an object, is running, and its action uses a property that the initializer has not reached yet. The stock
// runtime runs the action on another thread, which waits for the initializer; kmicro runs it after the initializer
// has ended. The initializers only allocate, so that the small heap of kmicro collects while they run; they do not
// call GC.collect(), which waits for the actions on the stock runtime.
@file:OptIn(kotlin.experimental.ExperimentalNativeApi::class, kotlin.native.runtime.NativeRuntimeApi::class)

import kotlin.concurrent.AtomicInt
import kotlin.native.ref.createCleaner
import kotlin.native.runtime.GC

val early = AtomicInt(0)
val warm = run { drop(); churn() }      // a collection finds the Port dead while this runs
val closed = AtomicInt(0)               // not created yet at that moment

class Port {
    val cleaner = createCleaner(Unit) { closed.incrementAndGet() }
}

fun drop() {
    Port()
}

fun churn(): Int {
    var n = 0
    repeat(3000) { n += "junk $it".length }
    return n
}

// The same for the initializer of an object.
object Registry {
    val warm = run { dropEntry(); churn() }
    val removed = AtomicInt(0)
}

class Entry {
    val cleaner = createCleaner(Unit) { Registry.removed.incrementAndGet() }
}

fun dropEntry() {
    Entry()
}

// An initializer that throws has ended as well: the actions run after it.
object Broken {
    val warm: Int = run { dropEntry(); churn(); error("broken") }
}

fun main() {
    println("file: warm $warm, early ${early.value}")
    GC.collect()
    println("closed ${closed.value}")
    println("object: warm ${Registry.warm}")
    GC.collect()
    println("removed ${Registry.removed.value}")
    try {
        println("not reached: ${Broken.warm}")
    } catch (e: Throwable) {
        println("an initializer that throws: caught")
    }
    GC.collect()
    println("removed ${Registry.removed.value}")
}

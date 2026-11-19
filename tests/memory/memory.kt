// Copyright 2026 the kmicro authors (NOTICE).
// SPDX-License-Identifier: Apache-2.0
@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class, kotlin.experimental.ExperimentalNativeApi::class,
    kotlin.native.runtime.NativeRuntimeApi::class)

import kotlin.concurrent.AtomicInt
import kotlin.native.CName
import kotlin.native.ref.createCleaner
import kotlin.native.runtime.GC
import kotlinx.cinterop.ByteVar
import kotlinx.cinterop.StableRef
import kotlinx.cinterop.allocArray
import kotlinx.cinterop.memScoped
import kotlinx.cinterop.nativeHeap
import kotlinx.cinterop.set
import kotlinx.cinterop.toLong

// What a program gets when memory runs out, one function per case of main.c: the Kotlin heap, the native-memory
// arena (KM_INTEROP_BYTES), the StableRef table (KM_STABLE_REFS) and the reference globals (KM_GLOBALS, globals.kt).

class Box(val v: Int)

// One request larger than the whole heap: a catchable OutOfMemoryError.
@CName("k_too_big")
fun tooBig(): Int = try {
    IntArray(100_000).size
} catch (e: OutOfMemoryError) {
    println("IntArray(100000): OutOfMemoryError")
    -1
}

// The heap filled with live objects: the runtime stops with "out of memory" and a report.
@CName("k_heap_full")
fun heapFull(): Int {
    val keep = ArrayList<IntArray>()
    while (true) keep.add(IntArray(64))
}

@CName("k_native_oom")
fun nativeOom() {
    try {
        val p = nativeHeap.allocArray<ByteVar>(0xFFFF_FFF9L)
        val q = nativeHeap.allocArray<ByteVar>(8)
        println("4 GB: allocated, next block ${q.toLong() - p.toLong()} bytes later")
    } catch (e: OutOfMemoryError) {
        println("4 GB: OutOfMemoryError: ${e.message}")
    }
    try {
        memScoped { allocArray<ByteVar>(4096)[0] = 1 }
        println("4 KB memScoped: allocated")
    } catch (e: OutOfMemoryError) {
        println("4 KB memScoped: OutOfMemoryError")
    } finally {
        println("finally ran")
    }
}

@CName("k_stable_refs")
fun stableRefs() {
    val r = StableRef.create(Box(1))
    val p = r.asCPointer()
    r.dispose()
    val refs = List(16) { StableRef.create(Box(it)) }
    println("16 live refs, the first reused the disposed slot: ${refs[0].asCPointer() == p}")
    try {
        StableRef.create(Box(17))
    } finally {
        println("not reached")
    }
}

// Cleaners without GC.collect(): the actions run at an allocation after the collection that found the objects dead,
// which comes when the heap is full. The one whose object is held does not run. Then 17 Cleaners alive at once: each
// holds a slot of the StableRef table until its action has run.
val returned = AtomicInt(0)
var sink: Box? = null                   // what is stored here is a heap object: a Box nobody keeps would not be one

class Lease(id: Int) {
    val cleaner = createCleaner(id) { returned.addAndGet(1 + it * 100) }
}

// its own function, so that no frame slot of the caller keeps a Lease alive
fun lease(n: Int) {
    repeat(n) { Lease(it) }
}

@CName("k_cleaners")
fun cleaners() {
    val held = Lease(1000)
    lease(5)
    var rounds = 0
    while (returned.value % 100 < 5 && rounds < 100_000) {
        sink = Box(rounds)
        rounds++
    }
    val ran = returned.value
    println("5 dropped, 1 held: actions ${ran % 100}, ids ${ran / 100}, held ${held.cleaner != null}")
    val all = List(16) { Lease(it) }
    println("not reached: ${all.size}")
}

// A Cleaner whose resource is memory: the cleaner of a Buffered holds its 4 KB until the action has run, so three
// dead ones fill the 16 KB heap, and the allocation that finds it full must run their actions and collect again.
// A Wrapped holds a Buffered through a cleaner of its own: that takes two such rounds, and comes first, on a heap that
// no collection has touched, so that the fourth one needs both rounds in one allocation.
class Buffered {
    val buf = ByteArray(4096)
    val cleaner = createCleaner(buf) { returned.addAndGet(1) }
}

class Wrapped {
    val inner = Buffered()
    val cleaner = createCleaner(inner) { returned.addAndGet(1) }
}

fun buffered() {
    Buffered()
}

fun wrapped() {
    Wrapped()
}

@CName("k_cleaner_memory")
fun cleanerMemory() {
    repeat(60) { wrapped() }
    println("60 buffers of 4 KB, each held by a cleaner behind a second one: most actions ran ${returned.value >= 100}")
    repeat(100) { buffered() }
    println("100 more, each held by one cleaner: most actions ran ${returned.value >= 100 + 90}")
}

// Actions that need slots of the StableRef table themselves, with the table full of dead Cleaners and no collection
// since (the heap has room): the 17th createCleaner collects, and the 16 actions it runs make two StableRefs each.
// Then one action that makes 17 Cleaners and drops them: the 17th finds the table full inside the action, where the
// actions of the other 16 must run, as nothing else will free a slot.
class Pinning(id: Int) {
    val cleaner = createCleaner(id) {
        val a = StableRef.create(Box(it))
        val b = StableRef.create(Box(it + 1))
        returned.addAndGet(b.get().v - a.get().v)
        a.dispose()
        b.dispose()
    }
}

val inside = AtomicInt(0)

class Leasing {
    val cleaner = createCleaner(Unit) {
        lease(17)
        inside.value = returned.value % 100
    }
}

fun pinning(n: Int) {
    repeat(n) { Pinning(it) }
}

fun leasing() {
    Leasing()
}

@CName("k_cleaner_slots")
fun cleanerSlots() {
    pinning(17)
    val first = returned.value
    GC.collect()
    println("17 dropped, each makes two StableRefs: $first ran before the last was made, ${returned.value} in all")
    returned.value = 0
    leasing()
    GC.collect()
    GC.collect()
    println("an action that makes 17 Cleaners: ${inside.value} of them ran inside it, ${returned.value % 100} in all")
}

// Case mapping and Char properties read the Unicode tables in flash: no heap kept. Char.category creates the 30
// CharCategory entries once.
@CName("k_uppercase")
fun uppercase(): Int = "abc".uppercase().length

@CName("k_is_letter")
fun isLetter(): Int = if ('\u00e9'.isLetter()) 1 else 0

@CName("k_category")
fun category(): Int = '\u00e9'.category.ordinal

@CName("k_println")
fun printLine() {
    println("warm-up")
}

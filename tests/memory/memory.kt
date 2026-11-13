@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class, kotlin.experimental.ExperimentalNativeApi::class)

import kotlin.native.CName
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

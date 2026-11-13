// Known not to work on kmicro yet: AtomicIntArray, AtomicLongArray and AtomicArray need the element-address natives
// (Kotlin_intArrayGetElementAddress ...), which kmicro does not have.
// Not run by default: python tools/difftest.py d_known_atomic_arrays
@file:OptIn(kotlin.concurrent.atomics.ExperimentalAtomicApi::class)

import kotlin.concurrent.atomics.*

fun main() {
    val a = AtomicIntArray(3)
    println("int: ${a.incrementAndFetchAt(1)} ${a.addAndFetchAt(2, 5)} $a")
    val l = AtomicLongArray(2)
    println("long: ${l.addAndFetchAt(1, 1L shl 40)} $l")
    val r = AtomicArray(arrayOf("a", "b"))
    println("ref: ${r.compareAndSetAt(0, "a", "z")} $r")
    println("done")
}

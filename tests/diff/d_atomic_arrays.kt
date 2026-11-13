@file:OptIn(kotlin.concurrent.atomics.ExperimentalAtomicApi::class, ExperimentalStdlibApi::class)
@file:Suppress("DEPRECATION")

// AtomicIntArray, AtomicLongArray and AtomicArray (kotlin.concurrent.atomics, and the older kotlin.concurrent
// classes): the compiler does the atomic operation on the element's address.

import kotlin.concurrent.atomics.*

fun index(label: String, block: () -> Any) =
    println("$label: " + try { block().toString() } catch (e: IndexOutOfBoundsException) { "IOOBE ${e.message}" })

fun main() {
    val ia = AtomicIntArray(3)
    println("int: ${ia.incrementAndFetchAt(1)} ${ia.addAndFetchAt(2, 5)} ${ia.fetchAndAddAt(2, 1)} ${ia.decrementAndFetchAt(0)}")
    println("int cas: ${ia.compareAndSetAt(0, -1, 7)} ${ia.compareAndSetAt(0, -1, 8)} ${ia.compareAndExchangeAt(1, 1, 4)} " +
        "${ia.exchangeAt(2, 9)} ${ia.loadAt(2)} $ia")
    ia.storeAt(1, Int.MAX_VALUE)
    println("int wrap: ${ia.incrementAndFetchAt(1)} ${ia.size} ${ia.updateAndFetchAt(0) { it * 3 }} ${ia.fetchAndUpdateAt(0) { it - 1 }} $ia")
    val la = AtomicLongArray(longArrayOf(1L, 1L shl 40, -1L))
    println("long: ${la.addAndFetchAt(1, 1L shl 40)} ${la.incrementAndFetchAt(2)} ${la.fetchAndAddAt(0, Long.MAX_VALUE)} " +
        "${la.loadAt(0)} ${la.compareAndSetAt(1, 1L shl 41, 5L)} ${la.exchangeAt(2, Long.MIN_VALUE)} $la")
    val ra = AtomicArray(arrayOf("a", "b", "c"))
    println("ref: ${ra.compareAndSetAt(0, "a", "z")} ${ra.compareAndSetAt(0, "a", "y")} ${ra.exchangeAt(1, "q")} " +
        "${ra.compareAndExchangeAt(2, "c", "w")} ${ra.loadAt(2)} $ra")
    val nulls = AtomicArray<String?>(2) { null }
    println("ref null: ${nulls.compareAndSetAt(1, null, "x")} ${nulls.loadAt(1)} $nulls")
    index("int loadAt 3", { ia.loadAt(3) })
    index("int addAndFetchAt -1", { ia.addAndFetchAt(-1, 1) })
    index("long exchangeAt 3", { la.exchangeAt(3, 0L) })
    index("ref storeAt 3", { ra.storeAt(3, "x") })

    val old = kotlin.concurrent.AtomicIntArray(4)
    old.addAndGet(1, 3); old.incrementAndGet(2); old.compareAndSet(2, 1, 5)
    println("old int: [${(0 until old.length).joinToString { old[it].toString() }}] ${old.getAndSet(1, 7)} ${old[1]}")
    val oldLong = kotlin.concurrent.AtomicLongArray(2)
    println("old long: ${oldLong.addAndGet(0, 1L shl 60)} ${oldLong.getAndIncrement(1)} ${oldLong[1]}")
    val oldRef = kotlin.concurrent.AtomicArray(2) { "e$it" }
    println("old ref: ${oldRef.compareAndSet(1, "e1", "f")} ${oldRef[1]} ${oldRef.getAndSet(0, "g")} ${oldRef[0]}")
}

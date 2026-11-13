// StableRef: a Kotlin object that only C holds (its void * kept as a number) survives full collections, and
// dispose frees the slot, so many more create/dispose rounds than the table has slots work.
@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class, kotlin.native.runtime.NativeRuntimeApi::class)

import kotlinx.cinterop.*
import kotlin.native.runtime.GC

class Box(val value: Int, val tag: String)

// Only the raw pointer leaves this function: no Kotlin reference to the Box survives the call.
fun stash(v: Int): Long = StableRef.create(Box(v, "box #$v")).asCPointer().toLong()

// Garbage of the same shape: a Box freed by mistake would be reused and overwritten.
fun churn(): Int {
    var sum = 0
    repeat(3000) { sum += Box(-it, "junk $it").value }
    return sum
}

fun main() {
    val held = LongArray(5) { stash(it * 11) }
    GC.collect()
    println("churn: ${churn()}")
    GC.collect()
    for (p in held) {
        val ref = p.toCPointer<CPointed>()!!.asStableRef<Box>()
        val box = ref.get()
        println("after GC: ${box.value} ${box.tag}")
        ref.dispose()
    }

    var sum = 0
    repeat(500) {
        val ref = StableRef.create(Box(it, "round"))
        sum += ref.get().value
        ref.dispose()
    }
    println("500 create/dispose rounds: $sum")

    val list = mutableListOf("a", "b")
    val ref = StableRef.create(list)
    ref.asCPointer().asStableRef<MutableList<String>>().get().add("c")
    GC.collect()
    println("shared object: $list, same: ${ref.get() === list}")
    ref.dispose()
}

// Copyright 2026 the kmicro authors (NOTICE).
// SPDX-License-Identifier: Apache-2.0
// WeakReference: get() gives the object while something else holds it and null after a collection found it dead.
// An object is made and looked at in a function of its own, so that no frame slot of main keeps it alive, and what
// is printed about an object that nothing holds comes after a GC.collect(): until then it may or may not be there.
@file:OptIn(kotlin.experimental.ExperimentalNativeApi::class, kotlin.native.runtime.NativeRuntimeApi::class)

import kotlin.native.ref.WeakReference
import kotlin.native.runtime.GC

class Box(val value: Int, val tag: String)

object Registry {
    val name = "registry"
}

class Parent(val id: Int) {
    var child: Child? = null
}

class Child(parent: Parent) {
    val parent = WeakReference(parent)      // a back reference that does not keep the parent
}

fun weakBox(v: Int): WeakReference<Box> = WeakReference(Box(v, "box #$v"))

fun show(w: WeakReference<Box>): String = w.get()?.let { "${it.value} ${it.tag}" } ?: "null"

// Garbage of the same shape as a Box and as what a WeakReference is made of: a freed object would be overwritten.
fun churn(): Int {
    var sum = 0
    repeat(400) { sum += Box(-it, "junk $it").value + 2 * (WeakReference(Box(it, "weak junk")).get()?.value ?: 0) }
    return sum
}

fun family(id: Int): Child {
    val p = Parent(id)
    val c = Child(p)
    p.child = c
    println("parent seen from the child: ${c.parent.get()?.id}")
    return c
}

// More of them than the StableRef table has slots; every third object goes to `held`.
fun fill(held: MutableList<Box>): List<WeakReference<Box>> =
    List(60) { i ->
        val b = Box(i, "box #$i")
        if (i % 3 == 0) held.add(b)
        WeakReference(b)
    }

fun live(refs: List<WeakReference<Box>>): Int = refs.count { it.get() != null }

fun sum(refs: List<WeakReference<Box>>): Int = refs.sumOf { it.get()?.value ?: 0 }

fun main() {
    val dead = weakBox(7)
    GC.collect()
    println("after a collection: ${show(dead)}, value ${dead.value}")
    println("churn: ${churn()}")
    println("after reuse of the memory: ${show(dead)}")

    val kept = Box(11, "kept")
    val alive = WeakReference(kept)
    val second = WeakReference(kept)
    GC.collect()
    println("held object: ${show(alive)}, same object: ${alive.get() === kept}, twice: ${second.value === alive.value}")
    alive.clear()
    println("cleared: ${show(alive)}, the other one: ${show(second)}")

    val text = WeakReference("a constant")
    val single = WeakReference(Registry)
    GC.collect()
    println("constant: ${text.get()}, object: ${single.get()?.name}")

    val held = ArrayList<Box>()
    val refs = fill(held)
    GC.collect()
    println("60 references: ${live(refs)} alive, sum ${sum(refs)}, held ${held.size}")
    held.clear()
    GC.collect()
    println("after dropping the objects: ${live(refs)} alive")

    val child = family(5)
    GC.collect()
    println("parent after a collection: ${child.parent.get()?.id}")

    // references dropped before their objects: the collector forgets them
    var sum = 0
    repeat(300) { i ->
        val b = Box(i, "round")
        sum += WeakReference(b).get()!!.value
        if (i % 50 == 0) GC.collect()
    }
    println("300 short-lived references: $sum")
    println("the first one again: ${show(dead)} ${show(second)}")
}

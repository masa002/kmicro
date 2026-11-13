@file:OptIn(kotlin.experimental.ExperimentalNativeApi::class)

import kotlin.native.CName

// What stops a program with a fault report from the start code ("kmicro fault: ...", exit 99), and a stack-hungry
// function kbuild warns about. One function per case of main.c.

class Cell(val v: Int, val next: Cell?)

// Each level allocates on the way back up (Cell(n, build(n - 1)) would allocate first): at the deepest point the heap
// is still empty, and only the stack runs out.
fun build(n: Int): Cell? {
    if (n == 0) return null
    val next = build(n - 1)
    return Cell(n, next)
}

fun sum(c: Cell?): Int {
    var s = 0
    var p = c
    while (p != null) { s += p.v; p = p.next }
    return s
}

// Deep recursion: the MPU guard below the stack stops it before it writes .bss (the heap).
@CName("k_deep")
fun deep() {
    for (depth in intArrayOf(100, 300, 100_000)) println("depth $depth: sum ${sum(build(depth))}")
}

abstract class Base {
    init { println("Base sees " + describe()) }
    abstract fun describe(): String
}

class Sub(val name: String) : Base() {
    override fun describe() = "name=$name"         // called by Base's init, before name is set: a null read
}

@CName("k_null_field")
fun nullField() {
    println("start")
    println(Sub("x").describe())
}

// A local array of constant size that never leaves the function lives on the stack: 56000 bytes here, over kbuild's
// 512-byte warning limit (an error with stack_array_error).
@CName("k_big_array")
fun bigArray(): Int {
    val big = IntArray(14000)
    for (i in big.indices) big[i] = i
    return big.sum()
}

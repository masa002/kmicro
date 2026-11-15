// Copyright 2026 the kmicro authors (NOTICE).
// SPDX-License-Identifier: Apache-2.0
// Built with --size: an exception thrown below a call sequence that repeats in many functions. Each `for (x in it)`
// loop calls Iterator.hasNext() and tests the result; with `minsize` LLVM's machine outliner would move that
// sequence into one function, whose unwind entry is wrong on a Thumb-2 core, and the catch in main would be
// skipped. retarget.py keeps the outliner away ("nooutline").
class Reader(private val n: Int) : Iterator<Int> {
    private var i = 0
    override fun hasNext(): Boolean {
        if (i == n) throw IllegalStateException("input ended after $i values")
        return true
    }
    override fun next() = i++
}

fun fold0(it: Iterator<Int>): Int { var s = 0; for (x in it) { s += x }; return s }
fun fold1(it: Iterator<Int>): Int { var s = 1; for (x in it) { s -= x }; return s }
fun fold2(it: Iterator<Int>): Int { var s = 2; for (x in it) { s += x * 3 }; return s }
fun fold3(it: Iterator<Int>): Int { var s = 3; for (x in it) { s = s * 2 + x }; return s }
fun fold4(it: Iterator<Int>): Int { var s = 4; for (x in it) { s = s xor x }; return s }
fun fold5(it: Iterator<Int>): Int { var s = 5; for (x in it) { s += x * x }; return s }
fun fold6(it: Iterator<Int>): Int { var s = 6; for (x in it) { s = (s shl 1) - x }; return s }
fun fold7(it: Iterator<Int>): Int { var s = 7; for (x in it) { s += x + 7 }; return s }
fun fold8(it: Iterator<Int>): Int { var s = 8; for (x in it) { s = s or (x shl 4) }; return s }
fun fold9(it: Iterator<Int>): Int { var s = 9; for (x in it) { s += x % 5 }; return s }
fun fold10(it: Iterator<Int>): Int { var s = 10; for (x in it) { s = s * 31 + x }; return s }
fun fold11(it: Iterator<Int>): Int { var s = 11; for (x in it) { s -= x * 9 }; return s }
fun fold12(it: Iterator<Int>): Int { var s = 12; for (x in it) { s += x shr 1 }; return s }
fun fold13(it: Iterator<Int>): Int { var s = 13; for (x in it) { s = s * 7 - x }; return s }

fun main() {
    val folds = listOf<(Iterator<Int>) -> Int>(::fold0, ::fold1, ::fold2, ::fold3, ::fold4, ::fold5, ::fold6,
                                              ::fold7, ::fold8, ::fold9, ::fold10, ::fold11, ::fold12, ::fold13)
    for ((k, f) in folds.withIndex()) {
        val r = try { f(Reader(3 + k)).toString() } catch (e: IllegalStateException) { "caught: ${e.message}" }
        println("fold$k: $r")
    }
    println("done")
}

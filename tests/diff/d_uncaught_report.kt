// Copyright 2026 the kmicro authors (NOTICE).
// SPDX-License-Identifier: Apache-2.0
// The report of an uncaught exception: what toString() of each exception gives, its suppressed exceptions with
// their own causes and suppressed exceptions, every cause, and an exception that comes up twice.
// difftest: uncaught -- the program ends with the report, which is what it tests

class Fault(val code: Int) : Exception("fault") {
    override fun toString() = "Fault #$code (${message})"
}

class Res(private val name: String) : AutoCloseable {
    override fun close() = throw IllegalStateException("closing $name failed")
}

fun work(): Nothing {
    try {
        Res("flash").use { throw Fault(7) }
    } catch (e: Fault) {
        val top = RuntimeException("boot failed", e)
        val first = IllegalArgumentException("first suppressed", ArithmeticException("its cause"))
        first.addSuppressed(Fault(8))
        first.cause!!.addSuppressed(UnsupportedOperationException("suppressed by the cause"))
        top.addSuppressed(first)
        top.addSuppressed(e)
        throw top
    }
}

fun main() {
    println("before the exception")
    work()
}

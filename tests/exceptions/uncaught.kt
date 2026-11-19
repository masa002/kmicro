// Copyright 2026 the kmicro authors (NOTICE).
// SPDX-License-Identifier: Apache-2.0
@file:OptIn(kotlin.experimental.ExperimentalNativeApi::class)

import kotlin.native.CName

// Uncaught exceptions and the unhandled-exception hook, one function per case of uncaught.c. Each case but the hook
// that returns ends the program with the uncaught-exception report and exit 98.

class SensorMissing(id: Int) : Exception("sensor $id not answering")

class Loop : Exception("loop") {
    override val cause: Throwable? get() = this
}

class Broken : Exception() {
    override val message: String get() = throw IllegalStateException("message failed")
}

fun probe(id: Int, left: Int): Int {
    if (left == 0) throw IllegalStateException("boot failed at sensor $id", SensorMissing(id))
    return probe(id, left - 1) + id
}

@CName("k_cause_chain")
fun causeChain() {
    println(probe(3, 2))
}

@CName("k_long_message")
fun longMessage() {
    throw RuntimeException("x".repeat(150) + " END")
}

@CName("k_failed_initializer")
fun failedInitializer() {
    println("config = $config")                     // config.kt: its initializer throws
}

@CName("k_hook")
fun hook() {
    setUnhandledExceptionHook { println("HOOK RAN for $it") }
    throw IllegalStateException("for the hook")
}

@CName("k_hook_terminates")
fun hookTerminates() {
    setUnhandledExceptionHook { println("HOOK: $it"); terminateWithUnhandledException(it) }
    throw IllegalStateException("for the hook")
}

@CName("k_hook_throws")
fun hookThrows() {
    setUnhandledExceptionHook { throw IllegalArgumentException("the hook failed", it) }
    throw IllegalStateException("original")
}

@CName("k_process_without_hook")
fun processWithoutHook() {
    processUnhandledException(IllegalStateException("processed"))
    println("after processUnhandledException: still running")
}

@CName("k_process_with_hook")
fun processWithHook() {
    setUnhandledExceptionHook { println("HOOK RAN for $it") }
    processUnhandledException(IllegalStateException("processed with a hook"))
    println("after processUnhandledException with a hook: still running")
}

@CName("k_circular_cause")
fun circularCause() {
    throw Loop()
}

@CName("k_message_throws")
fun messageThrows() {
    throw Broken()
}

// The report prints what toString() of a class that has its own gives, and under each exception the ones it
// suppressed, with their causes. The Fault comes up twice: as a suppressed exception and as the cause.
class Fault(val code: Int) : Exception("fault") {
    override fun toString() = "Fault #$code ($message)"
}

class Flash : AutoCloseable {
    override fun close() = throw IllegalStateException("closing failed")
}

@CName("k_suppressed")
fun suppressed() {
    try {
        Flash().use { throw Fault(7) }
    } catch (e: Fault) {
        val top = RuntimeException("boot failed", e)
        top.addSuppressed(IllegalArgumentException("first suppressed", ArithmeticException("its cause")))
        top.addSuppressed(e)
        throw top
    }
}

// The report names a class as toString() does: a local class by its simple name, an anonymous object as Throwable.
@CName("k_local_class")
fun localClass() {
    class LocalError : Exception("local")
    throw LocalError()
}

@CName("k_anonymous_object")
fun anonymousObject() {
    throw object : IllegalStateException("anonymous") {}
}

// A trace keeps the frames nearest to where the exception was made (KM_TRACE_MAX of them, 12), and the report says
// so when it left some out. The exceptions are made at every depth of a recursion, through one call, so that the
// first whose trace is full is found whatever the frames below the recursion are: it has exactly as many frames as
// a trace keeps, which is not a cut, and the ones made one and three calls deeper have one and three more. Kotlin
// code sees the frames that were kept and nothing else.
class Made : Exception() {
    var label = ""
    var why: Throwable? = null
    override val message: String get() = label
    override val cause: Throwable? get() = why
}

var visits = 0                          // work on both sides of the call, so that the recursion stays one

fun madeAt(depth: Int): Made {
    visits += depth
    val e = if (depth == 0) Made() else madeAt(depth - 1)
    visits -= depth
    return e
}

@CName("k_cut_trace")
fun cutTrace() {
    val made = List(24) { madeAt(it) }
    val sizes = made.map { it.getStackTraceAddresses().size }
    val full = sizes.indexOf(sizes.last())
    println("frames of the deepest: ${sizes.last()}; of the first that has as many, and of the one before: " +
            "${sizes[full]}, ${sizes[full - 1]}")
    val top = made[full + 3]
    println("getStackTrace() of the one made three calls deeper: ${top.getStackTrace().size} frames, and " +
            "${top.stackTraceToString().trim().lines().size} lines in stackTraceToString()")
    top.label = "three frames more than a trace keeps"
    made[full + 1].label = "one frame more"
    made[full].label = "as many frames as a trace keeps"
    top.addSuppressed(made[full + 1])
    top.why = made[full]
    throw top
}

// More exceptions than the report prints (KM_REPORT_MAX, 16): it says that it left some out.
fun wrapped(n: Int): Exception = if (n == 0) Exception("root") else Exception("level $n", wrapped(n - 1))

@CName("k_long_chain")
fun longChain() {
    throw wrapped(20)
}

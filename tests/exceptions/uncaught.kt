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

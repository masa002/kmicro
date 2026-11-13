// Known not to work on kmicro yet: stackTraceToString() and printStackTrace() of an exception with a cause or a
// suppressed exception stop with "unimplemented runtime symbol: Kotlin_NativePtrArray_getArrayLength".
// Not run by default: python tools/difftest.py d_known_stack_trace
fun main() {
    val e = IllegalStateException("outer", IllegalArgumentException("inner"))
    e.addSuppressed(RuntimeException("sup"))
    val trace = e.stackTraceToString()
    println("throwable: ${trace.lines().first()} hasCause=${trace.contains("Caused by: kotlin.IllegalArgumentException: inner")} frames=${trace.lines().size > 2} suppressed=${e.suppressedExceptions.map { it.message }} ${e.cause?.message} ${e}")
    println("done")
}

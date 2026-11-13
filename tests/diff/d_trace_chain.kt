// printStackTrace()/stackTraceToString() of exceptions with causes and suppressed exceptions. Frame lines ("at ...",
// "... and N more common stack frames skipped") differ between the targets and are left out; the rest must match.

class SensorMissing(id: Int) : Exception("sensor $id not answering")

class Res(private val name: String) : AutoCloseable {
    override fun close() = throw IllegalStateException("closing $name failed")
}

fun text(e: Throwable): String =
    e.stackTraceToString().lines().filter { l -> l.trim().let { !it.startsWith("at ") && !it.startsWith("... and ") } }
        .joinToString("\n")

fun boot(id: Int): Int {
    try {
        if (id > 2) throw SensorMissing(id)
        return id
    } catch (e: SensorMissing) {
        throw IllegalStateException("boot failed", e)
    }
}

fun main() {
    try {
        throw RuntimeException("outer", IllegalStateException("inner"))
    } catch (e: Exception) {
        println("cause:\n${text(e)}")
    }
    try {
        boot(3)
    } catch (e: Exception) {
        println("wrapped in a function:\n${text(e)}")
        println("cause is SensorMissing: ${e.cause is SensorMissing}")
    }
    try {
        throw Error("level 1", RuntimeException("level 2", IllegalArgumentException("level 3")))
    } catch (e: Error) {
        println("three levels:\n${text(e)}")
    }
    try {
        Res("disk").use { throw RuntimeException("work failed") }
    } catch (e: Exception) {
        println("use + failing close:\n${text(e)}")
        println("suppressed: ${e.suppressedExceptions.map { it.message }}")
    }
    val top = IllegalStateException("top", ArithmeticException("cause with suppressed"))
    top.cause!!.addSuppressed(UnsupportedOperationException("sup 1"))
    top.addSuppressed(RuntimeException("sup 2", NoSuchElementException("sup 2 cause")))
    println("suppressed and causes:\n${text(top)}")
    val e = IllegalStateException("printed")
    println("trace has frames: ${e.stackTraceToString().lines().any { it.trim().startsWith("at ") }}")
}

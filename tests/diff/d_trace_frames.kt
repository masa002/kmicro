// Stack traces: an exception created inside a try block lists every frame once. Frame lines differ between the
// targets (symbols on the host, addresses on kmicro), so only facts about them are printed.

fun frameLines(e: Throwable): List<String> =
    e.stackTraceToString().lines().map { it.trim() }.filter { it.startsWith("at ") }

fun main() {
    try {
        throw IllegalStateException("made inside try")
    } catch (e: IllegalStateException) {
        val at = frameLines(e)
        println("header: ${e.stackTraceToString().lines().first()}")
        println("try: no frame twice in a row ${at.zipWithNext().none { (a, b) -> a == b }}")
    }
}

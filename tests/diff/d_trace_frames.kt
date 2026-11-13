// Stack traces: an exception created inside a try block lists every frame once, and a trace starts in the function
// that created the exception. Frame lines differ between the targets (symbols on the host, addresses on kmicro), so
// only facts about them are printed.

fun frameLines(e: Throwable): List<String> =
    e.stackTraceToString().lines().map { it.trim() }.filter { it.startsWith("at ") }

fun make(tag: String): IllegalArgumentException = IllegalArgumentException("made by $tag, ${tag.length} chars")

fun main() {
    try {
        throw IllegalStateException("made inside try")
    } catch (e: IllegalStateException) {
        val at = frameLines(e)
        println("header: ${e.stackTraceToString().lines().first()}")
        println("try: has frames ${at.isNotEmpty()}")
        println("try: no frame twice in a row ${at.zipWithNext().none { (a, b) -> a == b }}")
    }
    val a = frameLines(make("first"))
    val b = frameLines(make("second call"))
    println("creator: has a caller ${a.size >= 2 && b.size >= 2}")
    println("creator: same first frame from two call sites ${a.isNotEmpty() && a.firstOrNull() == b.firstOrNull()}")
    println("creator: callers differ ${a.size >= 2 && a.getOrNull(1) != b.getOrNull(1)}")
}

// Known not to work on kmicro yet: RegexOption.CANON_EQ stops with "unimplemented runtime symbol:
// Kotlin_text_regex_decomposeString" (it cannot be caught).
// Not run by default: python tools/difftest.py d_known_regex_canon_eq
// difftest: heap 32768 -- the Regex engine builds its tables on the heap: the default 16 KB runs out
// difftest: large -- the Regex engine is about 240 KB of flash
fun err(label: String, block: () -> Any?) {
    val r = runCatching(block)
    val e = r.exceptionOrNull()
    println("$label: " + if (e == null) "ok ${r.getOrNull()}" else "${e::class.simpleName}: ${e.message}")
}

fun main() {
    err("CANON_EQ") { Regex("e\u0301", RegexOption.CANON_EQ).matches("\u00e9") }
    println("done")
}

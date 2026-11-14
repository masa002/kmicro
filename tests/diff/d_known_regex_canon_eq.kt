// Known to differ on kmicro: RegexOption.CANON_EQ is not supported. kmicro throws an IllegalArgumentException with
// the message "RegexOption.CANON_EQ is not supported on kmicro", which the program can catch; stock Kotlin/Native
// matches the canonically equivalent text.
// Not run by default: python tools/difftest.py d_known_regex_canon_eq
// difftest: heap 32768 -- the Regex engine builds its tables on the heap: the default 16 KB runs out
// difftest: large -- a program that uses Regex is about 366 KB of flash
fun err(label: String, block: () -> Any?) {
    val r = runCatching(block)
    val e = r.exceptionOrNull()
    println("$label: " + if (e == null) "ok ${r.getOrNull()}" else "${e::class.simpleName}: ${e.message}")
}

fun main() {
    err("CANON_EQ") { Regex("e\u0301", RegexOption.CANON_EQ).matches("\u00e9") }
    println("done")
}

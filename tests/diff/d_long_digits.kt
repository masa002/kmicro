// String.toDouble() and toFloat() on decimal text with 399 to 800 significant digits: more than the runtime's parser
// reads, and from 400 on more than its buffer holds. (Shorter text: d_to_double.kt.)
// difftest: heap 32768 -- a text of 800 digits takes 1.6 KB and the stdlib copies it to parse it: the free memory of
// the default 16 KB ends up in smaller blocks
fun show(label: String, s: String) {
    val d = s.toDoubleOrNull()
    println("$label: ${d?.toRawBits()?.toString(16)} ($d) ${s.toFloatOrNull()}")
}

fun main() {
    val digits = (0 until 800).joinToString("") { ((it % 9) + 1).toString() }
    for (n in listOf(399, 400, 450, 800))
        for (e in listOf(-700, -491, -400, -300, 0, 100))
            show("$n digits e$e", digits.substring(0, n) + "e$e")
    println(runCatching { (digits.substring(0, 450) + "e-300").toDouble() })
}

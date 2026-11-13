// Known to differ on kmicro: decoding invalid UTF-8 without throwOnInvalidSequence. Stock Kotlin/Native writes one
// U+FFFD for each incomplete sequence, kmicro one for each of its bytes. (Strict decoding matches: d_unicode.kt.)
// Not run by default: python tools/difftest.py d_known_utf8_decode
fun hex(s: String) = s.map { it.code.toString(16).padStart(4, '0') }.joinToString(" ")

fun main() {
    val bad = listOf(
        "e6bc41", "e6bc", "f09f98", "f09f9841", "c080", "c0", "80", "bf41", "ed a080", "f4908080", "f8", "ff41", "e080af", "e0a041",
        "c3a9", "f09f9880", "41c2", "e2828", "fe", "efbfbd", "c2c3a9", "e6bcbce6"
    )
    for (h in bad) {
        val clean = h.replace(" ", "")
        val b = ByteArray(clean.length / 2) { clean.substring(it * 2, it * 2 + 2).toInt(16).toByte() }
        println("decode $h -> ${hex(b.decodeToString())}")
    }
    println("done")
}

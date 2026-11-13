// Unicode: case mapping, Char properties, UTF-8 encoding and strict decoding. (Lenient decoding of
// invalid UTF-8: d_utf8_decode.kt)
fun err(label: String, block: () -> Any?) {
    val r = runCatching(block)
    val e = r.exceptionOrNull()
    println("$label: " + if (e == null) "ok ${r.getOrNull()}" else "${e::class.simpleName}: ${e.message}")
}

fun hex(s: String) = s.map { it.code.toString(16).padStart(4, '0') }.joinToString(" ")
fun bytes(b: ByteArray) = b.joinToString(" ") { (it.toInt() and 0xff).toString(16).padStart(2, '0') }

fun main() {
    val samples = listOf("ÀÉÎõüÿ", "ΑΒΓ σς ΣΑΣ ὈΔΥΣΣΕΎΣ", "straße ß", "İstanbul ı i I", "ǆ ǅ Ǆ", "日本語 カタカナ ｶﾀｶﾅ ＡＢＣ", "Ωmega µ ﬁ ŉ", "😀 𝐀𝐁 𐐀")
    for (t in samples) {
        val u = t.uppercase(); val l = t.lowercase()
        println("case [$t] -> U[$u] L[$l] len=${t.length}/${u.length}/${l.length}")
    }
    println("hex İ lower: ${hex("İ".lowercase())} ß upper: ${hex("ß".uppercase())} ΣΑΣ lower: ${hex("ΣΑΣ".lowercase())} ﬁ upper: ${hex("ﬁ".uppercase())} 𐐀 lower: ${hex("𐐀".lowercase())}")
    val chars = listOf('a', 'Z', '5', ' ', '\t', 'é', 'ß', 'Ж', 'ж', 'あ', 'ア', '漢', '٣', ' ', ' ', '​', '_', '$', '€', 'ǅ', 'Ⅻ', '²', '\uD83D', '\uDE00', '́', '\u0000', '­', 'ı', 'İ')
    for (c in chars) {
        println("char U+${c.code.toString(16).padStart(4, '0')} letter=${c.isLetter()} digit=${c.isDigit()} letterOrDigit=${c.isLetterOrDigit()} ws=${c.isWhitespace()} upper=${c.isUpperCase()} lower=${c.isLowerCase()} title=${c.isTitleCase()} cat=${c.category} ${c.category.code} upperChar=${c.uppercaseChar().code} lowerChar=${c.lowercaseChar().code} titleChar=${c.titlecaseChar().code} title=${hex(c.titlecase())} upperStr=${hex(c.uppercase())} iso=${c.isISOControl()} surrogate=${c.isSurrogate()} defined=${c.isDefined()} ident=${c.isJavaIdentifierStartLike()}")
    }
    println("digitToInt: ${'7'.digitToInt()} ${'f'.digitToInt(16)} ${'٣'.digitToIntOrNull()} ${'z'.digitToIntOrNull()} ${'Z'.digitToInt(36)} ${7.digitToChar()} ${11.digitToChar(16)} ${'A'.code} ${Char(0x263A)} ${'a' + 2} ${'z' - 'a'} ${'a'.inc()}")
    err("digitToInt bad") { 'x'.digitToInt() }
    err("Char(-1)") { Char(-1) }
    // UTF-8
    val texts = listOf("plain", "é", "日本", "😀", "a\uD800b", "\uDC00x", "end\uD83D", "😀\uD83D", "")
    for (t in texts) {
        println("utf8 [${hex(t)}] -> ${bytes(t.encodeToByteArray())} back=${hex(t.encodeToByteArray().decodeToString())}")
        err("  encode strict ${hex(t)}") { bytes(t.encodeToByteArray(0, t.length, throwOnInvalidSequence = true)) }
    }
    println("encode range: ${bytes("héllo😀".encodeToByteArray(1, 3))} ${bytes("a😀".encodeToByteArray(1, 2))}")
    val bad = listOf(
        "e6bc41", "e6bc", "f09f98", "f09f9841", "c080", "c0", "80", "bf41", "ed a080", "f4908080", "f8", "ff41", "e080af", "e0a041",
        "c3a9", "f09f9880", "41c2", "e2828", "fe", "efbfbd", "c2c3a9", "e6bcbce6"
    )
    for (h in bad) {
        val clean = h.replace(" ", "")
        val b = ByteArray(clean.length / 2) { clean.substring(it * 2, it * 2 + 2).toInt(16).toByte() }
        err("  strict $h") { hex(b.decodeToString(throwOnInvalidSequence = true)) }
    }
    val blob = "αβγ😀δ".encodeToByteArray()
    println("decode range: ${blob.decodeToString(2, 6)} ${hex(blob.decodeToString(1, 5))} ${blob.decodeToString(0, 0).length}")
    err("decode range bad") { blob.decodeToString(3, 100) }
    println("String(bytes)-like: ${"x".encodeToByteArray().size}")
    println("done")
}

fun Char.isJavaIdentifierStartLike() = isLetter() || this == '_' || this == '$'

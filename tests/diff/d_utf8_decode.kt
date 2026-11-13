// UTF-8 decoding with replacement (decodeToString) and the throwing variant. A sequence cut short gives one U+FFFD;
// an invalid lead byte, an overlong form, an encoded surrogate or a value above U+10FFFF gives one per byte.

fun bytes(hex: String) = ByteArray(hex.length / 2) { hex.substring(2 * it, 2 * it + 2).toInt(16).toByte() }

fun codes(s: String) = s.map { it.code.toString(16).padStart(4, '0') }.joinToString(" ")

fun main() {
    val cases = listOf(
        // cut short: one replacement for the lead and its continuation bytes
        "e6bc41", "e6bc", "f09f98", "f09f9841", "e0a041", "e282", "e28241", "41e282", "c2", "c241", "e2", "f0", "f09f",
        "f09f41", "e6bce6bca2", "f09f98e6bca2", "41f09f9841f09f98",
        // invalid after the second byte or as a lead: one replacement per byte
        "eda0", "e080", "e08041", "f490", "f49041", "f580", "f08f", "eda080", "edbfbf", "e08080", "f0808080",
        "f4908080", "c080", "c1bf", "80", "bf", "8080", "f8", "ff", "fe41", "f8808080", "c0", "f5", "f7bfbfbf",
        // valid
        "", "41", "c3a9", "e6bca2", "f09f9880", "f48fbfbf", "efbfbd", "ed9fbf", "ee8080", "7f", "c280", "dfbf", "e0a080",
        "f0908080", "41c3a9e6bca2f09f9880")
    for (hex in cases) {
        val b = bytes(hex)
        val checked = try { codes(b.decodeToString(throwOnInvalidSequence = true)) } catch (e: CharacterCodingException) { "throws" }
        println("decode [$hex] -> [${codes(b.decodeToString())}] checked [$checked]")
    }
    val mixed = bytes("41e6bc42f09f43c08044e6bca245")
    println("range: [${codes(mixed.decodeToString(1, 6))}] [${codes(mixed.decodeToString(3, 7))}] [${codes(mixed.decodeToString(4, 14))}]")
    println("roundtrip: ${"aé漢😀".encodeToByteArray().decodeToString() == "aé漢😀"}")
}

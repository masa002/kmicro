// The stdlib's Unicode tables: categories, letter/digit tests and case mappings over every UTF-16 code unit, compared
// through hashes, plus samples. kmicro reads these tables in place in flash.

fun main() {
    println("uppercase: ${"abc".uppercase()} ${"été".uppercase()} ${"straße".uppercase()} ${"ŉ".uppercase()}")
    println("lowercase: ${"ABC".lowercase()} ${"ÉTÉ".lowercase()} ${"İ".lowercase().length} ${"ΣΑΣ".lowercase()}")
    println("category: ${'a'.category} ${'é'.category} ${'1'.category} ${' '.category} ${'٣'.category} ${'€'.category}")
    println("is: ${'é'.isLetter()} ${'٣'.isDigit()} ${' '.isWhitespace()} ${'ǅ'.isTitleCase()} ${'ʰ'.isLowerCase()}")
    var cat = 0L
    var bits = 0L
    var upper = 0L
    var lower = 0L
    var title = 0L
    for (i in 0..0xFFFF) {
        val c = i.toChar()
        cat = cat * 31 + c.category.ordinal
        var b = 0
        if (c.isLetter()) b = b or 1
        if (c.isDigit()) b = b or 2
        if (c.isLetterOrDigit()) b = b or 4
        if (c.isWhitespace()) b = b or 8
        if (c.isUpperCase()) b = b or 16
        if (c.isLowerCase()) b = b or 32
        if (c.isTitleCase()) b = b or 64
        if (c.isDefined()) b = b or 128
        bits = bits * 31 + b
        upper = upper * 31 + c.uppercaseChar().code
        lower = lower * 31 + c.lowercaseChar().code
        title = title * 31 + c.titlecaseChar().code
    }
    println("all chars: category $cat, tests $bits, upper $upper, lower $lower, title $title")
    var strings = 0L
    for (i in 0 until 0x3000 step 7) {
        val s = charArrayOf(i.toChar(), (i + 1).toChar(), (i + 3).toChar()).concatToString()
        strings = strings * 31 + s.uppercase().hashCode()
        strings = strings * 31 + s.lowercase().hashCode()
    }
    println("strings: $strings")
}

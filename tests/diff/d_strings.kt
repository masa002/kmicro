fun main() {
    val words = listOf("kotlin", "Native", "", "マイコン", "émoji😀", "a,b,,c", "  pad  ")
    for (w in words) {
        println("[$w] len=${w.length} hash=${w.hashCode()} upper=${w.uppercase()} lower=${w.lowercase()} rev=${w.reversed()}")
        println("  trim=[${w.trim()}] split=${w.split(",")} startsK=${w.startsWith("k")} idx_a=${w.indexOf('a')} last_a=${w.lastIndexOf('a')}")
        println("  pad=[${w.padStart(10, '.')}] [${w.padEnd(10, '_')}] sub=${if (w.length > 2) w.substring(1, 3) else "-"} chars=${w.toList().take(4)}")
    }
    val sb = StringBuilder()
    for (i in -3..3) sb.append(i).append(':').append(i * 1_000_003L).append(';')
    println(sb)
    println(listOf("b", "a", "C", "ä", "B").sorted())
    println("abc".compareTo("abd").toString() + " " + "b".compareTo("a") + " " + "x".repeat(5) + " " + "a-b-c".replace("-", "+"))
    println(1234567.toString(2) + " " + (-255).toString(16) + " " + Long.MAX_VALUE.toString(36) + " " + Int.MIN_VALUE)
    println("%".plus("ok") + " " + "Hello, %s".length + " " + "x=" + 3 + 'c' + true + null)
    println(buildString { for (c in 'a'..'e') append(c.code).append(' ') })
    println("tab\tquote\"backslash\\ unicodeé end")
    println("ab".encodeToByteArray().toList() + "é".encodeToByteArray().toList() + "😀".encodeToByteArray().toList())
    println(byteArrayOf(0xe6.toByte(), 0xbc.toByte(), 0xa2.toByte(), 0x41).decodeToString())
}

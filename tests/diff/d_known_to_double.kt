// Known not to work on kmicro yet with the default 16 KB heap: String.toDouble() and toFloat() go through the Regex
// engine, which needs about 27 KB of heap and about 240 KB of flash. With a bigger heap the results are the same as
// on stock Kotlin/Native (d_numbers.kt).
// Not run by default: python tools/difftest.py d_known_to_double
fun err(label: String, block: () -> Any?) {
    val r = runCatching(block)
    val e = r.exceptionOrNull()
    println("$label: " + if (e == null) "ok ${r.getOrNull()}" else "${e::class.simpleName}: ${e.message}")
}

fun main() {
    // parsing
    val parse = listOf("1", "-1.5", "1e10", "1E-10", "  7.25  ", "0x1.8p1", "0X10P0", "-0x1p-2", "1.7976931348623159e308", "4.9e-325", "2.4703282292062328e-324", "NaN", "+NaN", "-Infinity", "Infinity", "inf", "1_0", "", " ", ".", "e5", "1e+", "0.000001", "123456789012345678901234567890", "0.1e-400", "1.0d", "1.0F", "1.", ".1", "+1", "--1", "0x", "0x1p", "1e2147483648", "9".repeat(400), "0." + "0".repeat(350) + "1")
    for (p in parse) print("[${p.take(12)}]=${p.toDoubleOrNull()}/${p.toFloatOrNull()} ")
    println()
    println("toDouble: ${"3.5".toDouble()} ${"1e3".toDouble()} ${" 2.5 ".toDoubleOrNull()} ${"0x1p4".toDoubleOrNull()} ${"NaN".toDouble()} ${"-Infinity".toDouble()} ${"1_000".toDoubleOrNull()} ${".5".toDouble()} ${"5.".toDouble()} ${"1e".toDoubleOrNull()} ${"1d".toDoubleOrNull()} ${"1f".toDoubleOrNull()} ${"0x10".toDoubleOrNull()} ${"+.5e-2".toDouble()}")
    println("toFloat: ${"3.4028235e38".toFloat()} ${"1e39".toFloat()} ${"1.4e-45".toFloat()} ${"0.1".toFloat()} ${"abc".toFloatOrNull()} ${"16777217".toFloat()}")
    err("toDouble bad") { "1.2.3".toDouble() }
    println("done")
}

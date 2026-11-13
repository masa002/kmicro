// String.toDouble()/toFloat() and their OrNull forms on decimal, named and hexadecimal text, valid and invalid. The
// hexadecimal cases cover the grammar, rounding (ties, digits beyond the 15 that fit the mantissa), subnormals,
// overflow and huge exponents; a batch of generated strings is compared through a hash of the bits.

fun showD(s: String): String = s.toDoubleOrNull()?.let { "$it ${it.toRawBits().toULong().toString(16)}" } ?: "null"
fun showF(s: String): String = s.toFloatOrNull()?.let { "$it ${it.toRawBits().toUInt().toString(16)}" } ?: "null"

val cases = listOf(
    "3.14", "-0.0", "1e10", "1.5f", "2.5d", " 42 ", "NaN", "-Infinity", "+Infinity", "abc", "", "1e", ".5", "5.",
    "0x1p0", "0x1.8p1", "-0x1.8p1", "+0x1P-1d", " 0x1p1F ", "\t0x1p1\n", "0x.8p1", "0x1.p1", "0X10p-4", "0xABCdefp0",
    "0x", "0xp1", "0x.p1", "0x1.8", "0x1.8p", "0x1.8pf", "0x1p+-1", "0x1.2.3p1", "0x1p1x", "0xgp1", "0x1p1ff",
    "0x1p١", "0x１p1", "0x1 p1", "0x1p 1", "--0x1p1", "0x1p+1", "0x1p-0", "0x0p0", "-0x0p0", "0x000.000p7",
    "0x1.fffffffffffffp1023", "0x1.fffffffffffff7p1023", "0x1.fffffffffffff8p1023", "0x1p1024", "0x1p1023",
    "0x1p-1022", "0x1p-1074", "0x1p-1075", "0x1.8p-1075", "0x1.0000000000001p-1075", "0x1p-1076", "0x1.fffffffffffffp-1023",
    "0x0.0000000000001p-1022", "0x0.00000000000008p-1022", "0x1.00000000000008p0", "0x1.00000000000018p0",
    "0x1.000000000000081p0", "0x1.0000000000000800000000000001p0", "0x1.00000000000007ffffffffffffp0",
    "0x123456789abcdef0123p0", "0x000000000000000000001p0", "0x0.000000000000000000001p0",
    "0x0p99999999999999999999", "0x1p99999999999999999999", "0x1p-99999999999999999999", "0x1p9223372036854775807",
    "0x1p-9223372036854775808", "0x1p2147483648", "0x1p-2147483649", "0xffffffffffffffffffffp-80",
)

val floatCases = listOf(
    "1.5", "0x1p0", "0x1.fffffep127", "0x1.ffffffp127", "0x1p128", "0x1p-126", "0x1p-149", "0x1p-150", "0x1.8p-150",
    "0x1.000001p0", "0x1.0000018p0", "0x1.00000100000000001p0", "0x1.7fffffp-149", "-0x1.8p1f", "0x1p1d", "0x1.8",
)

var seed = 12345L
fun next(n: Int): Int {
    seed = (seed * 6364136223846793005L + 1442695040888963407L)
    return ((seed ushr 33) % n).toInt()
}

fun generated(): String {
    val digits = "0123456789abcdefABCDEF"
    val sb = StringBuilder()
    if (next(4) == 0) sb.append(if (next(2) == 0) '-' else '+')
    sb.append(if (next(2) == 0) "0x" else "0X")
    val n = 1 + next(22)
    val point = next(n + 2) - 1
    for (i in 0 until n) {
        if (i == point) sb.append('.')
        sb.append(if (next(3) == 0) '0' else digits[next(digits.length)])
    }
    sb.append(if (next(2) == 0) 'p' else 'P')
    val e = next(2300) - 1150
    sb.append(if (e >= 0 && next(2) == 0) "+$e" else "$e")
    when (next(6)) { 0 -> sb.append('f'); 1 -> sb.append('D') }
    if (next(6) == 0) sb.insert(next(sb.length + 1), ".pPx+-g 9\u0000"[next(10)])   // often no longer valid
    return sb.toString()
}

fun main() {
    for (s in cases) println("toDouble(\"$s\") = ${showD(s)}")
    for (s in floatCases) println("toFloat(\"$s\") = ${showF(s)}")
    var hd = 0L
    var hf = 0L
    var valid = 0
    for (i in 0 until 3000) {
        val s = generated()
        val d = s.toDoubleOrNull()
        val f = s.toFloatOrNull()
        if (d != null) valid++
        hd = hd * 31 + (d?.toRawBits() ?: 7L)
        hf = hf * 31 + (f?.toRawBits() ?: 7).toLong()
        if (i % 500 == 0) println("generated $i: \"$s\" = ${showD(s)} / ${showF(s)}")
    }
    println("generated: $valid valid, double hash ${hd.toULong().toString(16)}, float hash ${hf.toULong().toString(16)}")
    println("exception: " + runCatching { "0x1.8".toDouble() }.exceptionOrNull()?.let { "${it::class.simpleName} ${it.message}" })
    println("float sum: " + ("1.5".toFloat() + "0x1p-2".toFloat()))
}

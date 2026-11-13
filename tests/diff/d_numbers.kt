// difftest: heap 32768 -- String.toDouble() goes through the Regex engine, which needs about 27 KB of heap
// difftest: large -- and links the Regex engine, about 240 KB of flash
fun Double.pow10(): Double { var r = 1.0; repeat(10) { r *= this }; return r }

fun main() {
    val ints = listOf(0, 1, -1, 7, -7, Int.MAX_VALUE, Int.MIN_VALUE, 123456789)
    for (a in ints) for (b in listOf(1, -1, 3, -3, 7)) print("${a / b},${a % b},${a.mod(b)};")
    println()
    println("${Int.MAX_VALUE + 1} ${Int.MIN_VALUE - 1} ${(-17) shr 2} ${(-17) ushr 28} ${1 shl 31} ${0x7f and 0x0f xor 0x55 or 0x100}")
    val longs = listOf(0L, 1L, -1L, Long.MAX_VALUE, Long.MIN_VALUE, 1_000_000_007L * 3, -98765432123L)
    for (a in longs) print("${a / 7} ${a % 7} ${a * 31} ${a.countOneBits()} ${a.countTrailingZeroBits()} ${a.toInt()}|")
    println()
    val doubles = listOf(0.0, -0.0, 1.0, 0.1, 1.0 / 3, 2.0 / 3, 1e21, 1e-7, 123456.789, Double.MAX_VALUE, Double.MIN_VALUE,
        Double.NaN, Double.POSITIVE_INFINITY, -2.5, 100.0, 1e15, 12345678901234567.0)
    for (d in doubles) print("$d ${d.toInt()} ${d.toLong()} ${d.isNaN()};")
    println()
    val floats = listOf(0f, 1f, 0.1f, 1f / 3, 3.4e38f, 1.17549435e-38f, -7.25f, 16777217f, 1e-3f)
    for (f in floats) print("$f ${f.toInt()} ${f.toDouble()};")
    println()
    println("${7.0 / 2} ${7 / 2.0f} ${(0.1 + 0.2)} ${(0.1f + 0.2f)} ${2.0.pow10()} ${kotlin.math.sqrt(2.0)} ${kotlin.math.abs(-3.5)}")
    println("${"3.14".toDouble()} ${"-1e10".toDouble()} ${"2.5".toFloat()} ${"1e400".toDouble()}")
    println("${3.7.toInt()} ${(-3.7).toInt()} ${kotlin.math.round(2.5)} ${kotlin.math.floor(-2.5)} ${kotlin.math.ceil(-2.5)}")
    var acc = 1.0
    for (i in 1..20) acc = acc * 1.5 - i
    println(acc)
    println(UInt.MAX_VALUE.toString() + " " + (0u - 1u) + " " + 200.toUByte() + " " + ULong.MAX_VALUE)
}

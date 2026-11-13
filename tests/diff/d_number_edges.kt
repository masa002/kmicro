// Numbers: overflow, division, bit operations, Double/Float toString, rounding, conversions. (String.toDouble:
// d_to_double.kt, d_parse_small.kt)
import kotlin.math.*

fun err(label: String, block: () -> Any?) {
    val r = runCatching(block)
    val e = r.exceptionOrNull()
    println("$label: " + if (e == null) "ok ${r.getOrNull()}" else "${e::class.simpleName}: ${e.message}")
}

// values the optimiser cannot fold
fun <T> opaque(v: T): T = listOf(v).first()

fun main() {
    val a = opaque(Int.MAX_VALUE); val b = opaque(Int.MIN_VALUE); val m1 = opaque(-1); val z = opaque(0)
    println("int overflow: ${a + 1} ${b - 1} ${a * 2} ${b * m1} ${b / m1} ${b % m1} ${-b} ${b.absoluteValue} ${abs(b)}")
    println("neg div/mod: ${opaque(-7) / 2} ${opaque(-7) % 2} ${opaque(7) / -2} ${opaque(7) % -2} floorDiv=${opaque(-7).floorDiv(2)} ${opaque(7).floorDiv(-2)} mod=${opaque(-7).mod(2)} ${opaque(7).mod(-2)} ${opaque(-7L).floorDiv(2L)} ${opaque(-7L).mod(3)} ${opaque(-7).mod(3L)}")
    err("int / 0") { opaque(5) / z }
    err("int % 0") { opaque(5) % z }
    err("long / 0") { opaque(5L) / z.toLong() }
    err("long % 0") { opaque(5L) % 0L }
    err("floorDiv 0") { opaque(5).floorDiv(z) }
    err("mod 0") { opaque(5).mod(z) }
    println("double / 0: ${opaque(1.0) / 0} ${opaque(-1.0) / 0} ${opaque(0.0) / 0} ${opaque(1.0) % 0} ${opaque(5.5) % 2} ${opaque(-5.5) % 2} ${opaque(-5.5).mod(2.0)} ${opaque(5.5).IEEErem(2.0)}")
    val L = opaque(Long.MAX_VALUE); val LM = opaque(Long.MIN_VALUE)
    println("long: ${L + 1} ${LM - 1} ${L * 3} ${LM / -1L} ${LM % -1L} ${opaque(123456789012345L) * 1000003L} ${opaque(-98765432109876L) / 12345L} ${opaque(-98765432109876L) % 12345L} ${opaque(0x123456789ABCDEFL) * opaque(0x7FEDCBAL)}")
    println("long more: ${opaque(1L) shl 63} ${LM shr 3} ${LM ushr 3} ${opaque(-1L) ushr 1} ${opaque(1L shl 40) / opaque(3L)} ${opaque(-1L shl 40) % opaque(7L)} ${opaque(Long.MAX_VALUE) / opaque(Long.MIN_VALUE)} ${opaque(4000000000L).toInt()} ${opaque(-1L).toUInt()}")
    println("short/byte: ${(opaque(32767.toShort()) + 1).toShort()} ${(opaque(127.toByte()) + 1).toByte()} ${opaque((-128).toByte()) / -1} ${opaque(200).toByte()} ${opaque(70000).toShort()} ${opaque(-1).toChar().code} ${opaque(300).toByte().toInt() and 0xff} ${opaque(5.toByte()) * opaque(30.toByte())}")
    println("int bits: ${opaque(0x0F0F).countOneBits()} ${opaque(1).countLeadingZeroBits()} ${opaque(0).countLeadingZeroBits()} ${opaque(256).countTrailingZeroBits()} ${opaque(0).countTrailingZeroBits()} ${opaque(0x80000001.toInt()).rotateLeft(1)} ${opaque(1).rotateRight(1)} ${opaque(100).takeHighestOneBit()} ${opaque(100).takeLowestOneBit()} ${opaque(0).takeHighestOneBit()} ${opaque(-1L).rotateLeft(5)} ${opaque(Long.MIN_VALUE).takeHighestOneBit()}")
    println("byte/short bits: ${opaque(0x81.toByte()).countOneBits()} ${opaque(1.toByte()).countLeadingZeroBits()} ${opaque(0x80.toByte()).rotateLeft(1)} ${opaque(0x0100.toShort()).countTrailingZeroBits()} ${opaque(0x8000.toShort()).takeHighestOneBit()}")
    // doubles to string
    val ds = listOf(0.1 + 0.2, 1e21, 1e20, 1e-7, 1e-6, 0.001, 1234567.0, 12345678.9, 1e7, 9999999.0, 100.0, -0.0, Double.NaN, Double.POSITIVE_INFINITY, Double.NEGATIVE_INFINITY,
        Double.MIN_VALUE, Double.MAX_VALUE, 2.2250738585072014E-308, 4.9e-324 * 3, 1.0 / 3, 2.0 / 3, 0.5, 123e-20, 5e-324, 1.7976931348623157e308, 9007199254740993.0, 0.30000000000000004, 1.1, 100.5, 1e16, 1.0E-5, 3.14159e100)
    println("double toString: " + ds.joinToString(" "))
    val fs = listOf(0.1f + 0.2f, 1e10f, 1e-7f, Float.MIN_VALUE, Float.MAX_VALUE, -0.0f, Float.NaN, Float.NEGATIVE_INFINITY, 1.0f / 3, 16777216f, 1.17549435E-38f, 3.4e38f, 0.001f, 1e7f, 100f, 33.333f)
    println("float toString: " + fs.joinToString(" "))
    println("double props: ${(-0.0).sign} ${(0.0).equals(-0.0)} ${0.0 == -0.0} ${Double.NaN == Double.NaN} ${Double.NaN.equals(Double.NaN)} ${(-0.0).compareTo(0.0)} ${listOf(0.0, -0.0, Double.NaN, -1.0, 1.0).sorted()} ${maxOf(0.0, -0.0)} ${minOf(Double.NaN, 1.0)} ${max(-0.0, 0.0)} ${min(Float.NaN, 1f)}")
    // rounding
    val rv = listOf(2.5, 3.5, -2.5, -0.5, 0.49999999999999994, 1e10 + 0.5, Double.NaN, 1e300, -1e300, 2147483647.5, -2147483648.6, 4.5e18, 9.3e18)
    for (v in rv) print("${v}: ${runCatching { v.roundToInt() }.getOrElse { it::class.simpleName }} ${runCatching { v.roundToLong() }.getOrElse { it::class.simpleName }} ${round(v)} ${floor(v)} ${ceil(v)} ${truncate(v)} ${v.toInt()} ${v.toLong()} | ")
    println()
    println("float round: ${2.5f.roundToInt()} ${(-2.5f).roundToInt()} ${round(2.5f)} ${Float.NaN.toInt()} ${3e9f.toInt()} ${(-3e9f).toLong()} ${1e20f.toLong()}")
    println("abs/sign: ${(-3).absoluteValue} ${(-3L).sign} ${(-2.5).absoluteValue} ${(-2.5).sign} ${0.0.sign} ${Double.NaN.sign} ${(-7).sign} ${(-1.5f).absoluteValue}")
    println("coerce: ${15.coerceIn(1, 10)} ${(-5).coerceIn(1..10)} ${2.5.coerceIn(0.0, 1.0)} ${5.coerceAtLeast(7)} ${5.coerceAtMost(3)} ${5L.coerceIn(1L, 3L)}")
    err("coerceIn bad") { 5.coerceIn(10, 1) }
    println("toBits: ${1.0.toBits()} ${(-0.0).toBits()} ${Double.NaN.toBits()} ${Double.fromBits(0x400921FB54442D18L)} ${1.5f.toBits()} ${Float.fromBits(0x7f800000)} ${Float.NaN.toRawBits()} ${Double.fromBits(0x7ff8000000000001L).toRawBits()} ${Double.fromBits(0x7ff8000000000001L).toBits()}")
    println("conversions: ${300.5.toInt().toByte()} ${(-1).toLong()} ${Long.MAX_VALUE.toDouble()} ${Long.MAX_VALUE.toFloat()} ${(1L shl 53).plus(1).toDouble()} ${Int.MAX_VALUE.toFloat()} ${'A'.code.toDouble()} ${0.1f.toDouble()} ${0.1.toFloat()} ${1e40.toFloat()} ${Double.MAX_VALUE.toLong()} ${(-1e30).toInt()}")
    println("numeric toString: ${Byte.MIN_VALUE} ${Short.MAX_VALUE} ${Int.MIN_VALUE} ${Long.MIN_VALUE} ${(-5).toByte().toString(2)} ${(-1).toUInt().toString(16)} ${Char.MAX_VALUE.code} ${Long.MAX_VALUE.toString(2).length} ${255.toUByte().toString(2)}")
    println("done")
}

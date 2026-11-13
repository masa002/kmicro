// Language probe 6: Nothing/TODO/error/require/check/assert, numeric semantics, annotations, newer Kotlin 2.x features.
// difftest: heap 32768 -- one long main: its frame keeps the objects of every check alive until it returns

annotation class Marker(val why: String = "", val level: Int = 0)
@Target(AnnotationTarget.FUNCTION, AnnotationTarget.CLASS) @Retention(AnnotationRetention.SOURCE) annotation class Src

@RequiresOptIn(level = RequiresOptIn.Level.ERROR) @Retention(AnnotationRetention.BINARY) annotation class Unstable
@Unstable fun unstableApi() = "unstable called"
@OptIn(Unstable::class) fun useUnstable() = unstableApi()

@Deprecated("use newFn", ReplaceWith("newFn()")) fun oldFn() = "old"
fun newFn() = "new"

@Marker("demo", 2) @Src class Annotated(@Marker val x: Int)

fun fail(msg: String): Nothing = throw IllegalArgumentException(msg)

fun describe(e: Throwable?) = "${e?.let { it::class.simpleName }}: ${e?.message}"

inline fun <T> probe(label: String, f: () -> T) {
    val r = runCatching(f)
    println("$label -> " + (r.exceptionOrNull()?.let { "threw " + describe(it) } ?: r.getOrNull().toString()))
}

@OptIn(kotlin.experimental.ExperimentalNativeApi::class)
fun main() {
    println("== Nothing / TODO / error / require / check / assert")
    probe("fail") { fail("bad input") }
    probe("TODO") { TODO() }
    probe("TODO msg") { TODO("later") }
    probe("error") { error("boom") }
    probe("require") { require(1 > 2) }
    probe("require msg") { require(false) { "need it" } }
    probe("check") { check(false) }
    probe("check msg") { check(false) { "state bad" } }
    probe("requireNotNull") { requireNotNull(null as String?) }
    probe("requireNotNull msg") { requireNotNull(null as String?) { "need value" } }
    probe("checkNotNull") { checkNotNull(null as Int?) }
    probe("checkNotNull ok") { checkNotNull(5) + 1 }
    var assertRan = false
    probe("assert") { assert(run { assertRan = true; false }) { "assert msg" }; "no throw" }
    println("assert evaluated: $assertRan")
    probe("div0") { val z = 0; 10 / z }
    probe("rem0") { val z = 0L; 10L % z }
    probe("double div0") { 1.0 / 0 }
    probe("index") { intArrayOf(1)[3] }
    probe("list index") { listOf(1)[3] }
    probe("negative size") { IntArray(-1) }
    probe("arithmetic msg") { Math2.divide(1, 0) }
    val u: Unit = Unit
    println("unit: $u ${println("inner")}")
    val x: Nothing? = null
    println("nothing? $x")

    println("== chars / bits / overflow")
    val c = 'a'
    println("${c + 1} ${c - 'A'} ${(c + 25).code} ${c.code.toString(2)} ${Char(0x41)} ${'\u0000'.code} ${Char.MAX_VALUE.code}")
    var cc = 'x'; cc++; println(cc)
    val a = 0b1011_0000
    println("${a shl 2} ${a shr 2} ${-a shr 2} ${-a ushr 28} ${a and 0xF0} ${a or 1} ${a xor 0xFF} ${a.inv()}")
    val l = 0x0123_4567_89AB_CDEFL
    println("${l shl 4} ${l shr 8} ${-l ushr 60} ${l and 0xFFFFL} ${l or 1L} ${l xor -1L} ${l.inv()}")
    println("${1 shl 31} ${1 shl 32} ${1L shl 63} ${1L shl 64} ${-1 ushr 1} ${-1L ushr 1}")
    println("${Int.MAX_VALUE + 1} ${Int.MIN_VALUE - 1} ${Int.MAX_VALUE * 2} ${Long.MAX_VALUE + 1} ${Int.MIN_VALUE / -1} ${Long.MIN_VALUE / -1L}")
    println("${Int.MIN_VALUE % -1} ${-7 / 2} ${-7 % 2} ${-7.mod(2)} ${-7.floorDiv(2)} ${7.rem(-2)}")
    println("${(-5).absoluteValue2()} ${Int.MIN_VALUE.absoluteValue2()}")
    println("${Byte.MAX_VALUE.inc()} ${(Byte.MAX_VALUE + 1).toByte()} ${(200).toByte()} ${(70000).toShort()} ${(-1).toUByte()}")
    println("${0xFFFF_FFFF} ${0xFFFF_FFFFL.toInt()} ${123_456_789_012L} ${1_000_000} ${0x7FFF_FFFF_FFFF_FFFF} ${Long.MIN_VALUE}")
    println("${1e3.toInt()} ${(-1.9).toInt()} ${2.9.toLong()} ${1e20.toInt()} ${(-1e20).toLong()} ${Double.NaN.toInt()} ${Double.POSITIVE_INFINITY.toLong()}")
    println("${300.7.toInt().toByte()} ${(-129.5).toInt().toShort()} ${3.99f.toInt()} ${Float.NaN.toLong()} ${1e10f.toInt()}")
    println("${5000000000L.toInt()} ${(-1L).toInt()} ${Long.MAX_VALUE.toShort()} ${Long.MIN_VALUE.toByte()} ${65.toChar()} ${'A'.code.toLong()}")
    println("${Long.MAX_VALUE.toDouble()} ${Long.MAX_VALUE.toFloat()} ${(1L shl 53) + 1} ${((1L shl 53) + 1).toDouble().toLong()}")
    val nan = Double.NaN
    println("${nan == nan} ${nan != nan} ${nan < 1.0} ${nan > 1.0} ${nan.equals(nan)} ${(nan as Any) == (nan as Any)} ${nan.compareTo(nan)} ${0.0 == -0.0} ${0.0.equals(-0.0)}")
    println("${listOf(nan, 1.0, -0.0, 0.0).sorted()} ${maxOf(nan, 1.0)} ${minOf(-0.0, 0.0)} ${nan.isNaN()}")
    println("${0.1 + 0.2} ${1.0 / 3} ${2.0f / 3} ${100.0} ${1e-7} ${1e21} ${-0.0} ${Float.MIN_VALUE} ${Double.MAX_VALUE}")
    println("${7 / 2} ${7.0 / 2} ${7 / 2.0} ${7 % 2.5} ${2.5 % -1} ${(-7) % 3}")
    println("${Int.MAX_VALUE.toLong() + 1} ${Int.MAX_VALUE.toUInt() + 1u} ${UInt.MAX_VALUE} ${ULong.MAX_VALUE} ${(-1).toUInt()} ${255u.toUByte()}")
    println("${3u - 5u} ${10u / 3u} ${UInt.MAX_VALUE.toInt()} ${200.toUByte().toInt()} ${0xFFu.toByte()} ${1uL shl 63}")
    val big: Long = 1 shl 40
    println("int shift into long: $big")
    println("${5.coerceIn(1, 3)} ${(-2).sign2()} ${10.toString(16)} ${"ff".toInt(16)} ${Int.MAX_VALUE.countOneBits()} ${8.takeHighestOneBit()} ${0x10.countTrailingZeroBits()}")
    println("${1.compareTo(2)} ${2L.compareTo(1)} ${'a'.compareTo('b')} ${true.compareTo(false)} ${true and false} ${true xor true} ${!true}")

    println("== annotations")
    @Suppress("UNUSED_VARIABLE") val unused = 1
    println(useUnstable())
    @Suppress("DEPRECATION") println(oldFn() + " " + newFn())
    println(Annotated(3).x)

    println("== newer features")
    for (i in 0..<3) print(i); println()
    val names = listOf("a", "b", "stop", "c")
    for (n in names) {
        names.forEach { if (it == "b") return@forEach }
        n.let { if (it == "stop") break }
        n.also { if (it == "b") continue }
        print("$n ")
    }
    println()
    println(DObj)
    println("${DObj == DObj} ${DObj.hashCode() == "DObj".hashCode()}")
    println(Level.entries.joinToString())
    println(with(Ctx("ctx")) { greet("p") })
    println(sumAll())
    println("done")
}

object Math2 { fun divide(a: Int, b: Int) = a / b }

fun Int.absoluteValue2() = if (this < 0) -this else this
fun Int.sign2() = when { this < 0 -> -1; this > 0 -> 1; else -> 0 }

data object DObj
enum class Level { LOW, HIGH }

class Ctx(val name: String)
context(c: Ctx) fun greet(who: String) = "${c.name} greets $who"

fun sumAll(vararg xs: Int = intArrayOf(1, 2, 3)) = xs.sum()

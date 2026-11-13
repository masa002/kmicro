// Duration, Uuid, HexFormat, Base64, atomics, print. (Duration.toString(unit, decimals): d_known_duration_format.kt;
// the clock: d_known_random_time.kt)
// difftest: heap 32768 -- one long main keeps the objects of its checks alive: the default 16 KB runs out at Uuid
// difftest: large -- Duration, Uuid, HexFormat and Base64 in one program: about 290 KB of flash
@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class, ExperimentalStdlibApi::class, kotlin.io.encoding.ExperimentalEncodingApi::class,
    kotlin.concurrent.atomics.ExperimentalAtomicApi::class, kotlin.time.ExperimentalTime::class)

import kotlin.time.*
import kotlin.time.Duration.Companion.days
import kotlin.time.Duration.Companion.hours
import kotlin.time.Duration.Companion.minutes
import kotlin.time.Duration.Companion.seconds
import kotlin.time.Duration.Companion.milliseconds
import kotlin.time.Duration.Companion.microseconds
import kotlin.time.Duration.Companion.nanoseconds
import kotlin.uuid.Uuid
import kotlin.io.encoding.Base64
import kotlin.concurrent.atomics.*

fun err(label: String, block: () -> Any?) {
    val r = runCatching(block)
    val e = r.exceptionOrNull()
    println("$label: " + if (e == null) "ok ${r.getOrNull()}" else "${e::class.simpleName}: ${e.message}")
}

fun <T> opaque(v: T): T = listOf(v).first()

fun main() {
    // Duration
    val d1 = 90.minutes; val d2 = 1.5.seconds; val d3 = 1234.microseconds; val d4 = 2.days + 3.hours + 4.minutes + 5.seconds + 6.milliseconds
    println("duration toString: $d1 $d2 $d3 $d4 ${-d2} ${Duration.ZERO} ${Duration.INFINITE} ${-Duration.INFINITE} ${1.nanoseconds} ${999.nanoseconds} ${1001.nanoseconds} ${0.5.milliseconds} ${Long.MAX_VALUE.nanoseconds} ${(Long.MAX_VALUE / 2).milliseconds} ${0.000001.seconds} ${123.456789.seconds} ${36500.days}")
    println("duration arith: ${d1 + d2} ${d1 - d2} ${d1 * 3} ${d1 * 1.5} ${d1 / 4} ${d1 / d2} ${(-d1).absoluteValue} ${d2.isPositive()} ${(-d2).isNegative()} ${d1 > d2} ${d1.compareTo(d1)} ${Duration.INFINITE + 1.seconds} ${d2.isFinite()}")
    println("duration inWhole: ${d4.inWholeMilliseconds} ${d4.inWholeSeconds} ${d4.inWholeMinutes} ${d4.inWholeHours} ${d4.inWholeDays} ${d3.inWholeNanoseconds} ${d3.inWholeMicroseconds} ${d2.toDouble(DurationUnit.MINUTES)} ${d4.toLong(DurationUnit.HOURS)} ${d4.toInt(DurationUnit.SECONDS)} ${Duration.INFINITE.inWholeMilliseconds}")
    println("duration components: ${d4.toComponents { days, h, m, s, ns -> "$days d $h h $m m $s s $ns ns" }} ${d1.toComponents { h, m, s, ns -> "$h:$m:$s.$ns" }} iso=${d1.toIsoString()} ${d4.toIsoString()} ${(-d2).toIsoString()} ${Duration.INFINITE.toIsoString()}")
    println("duration parse: ${Duration.parse("1h 30m")} ${Duration.parse("PT1.5S")} ${Duration.parse("-(1h 2m)")} ${Duration.parseOrNull("bogus")} ${Duration.parseIsoString("P1DT2H")} ${Duration.parse("1.5s")} ${Duration.parse("Infinity")} ${Duration.parse("2d 3h 4m 5.006s")} ${Duration.parseIsoStringOrNull("PT")}")
    println("duration factories: ${2.toDuration(DurationUnit.HOURS)} ${1.25.toDuration(DurationUnit.DAYS)} ${Duration.convert(1.0, DurationUnit.HOURS, DurationUnit.SECONDS)} ${d1.inWholeSeconds.seconds == d1} ${(1..4).map { it.seconds }.fold(Duration.ZERO) { a, b -> a + b }}")
    err("duration parse bad") { Duration.parse("1x") }
    err("duration iso bad") { Duration.parseIsoString("1h") }
    // Uuid
    val u = Uuid.parse("550e8400-e29b-41d4-a716-446655440000")
    println("uuid: $u ${u.toHexString()} ${u.toByteArray().size} ${Uuid.fromLongs(1L, 2L)} ${u.toLongs { a, b -> "$a/$b" }} ${Uuid.NIL} ${u == Uuid.parse(u.toString().uppercase())} ${u.hashCode()} ${Uuid.parseHex("550e8400e29b41d4a716446655440000") == u} ${Uuid.fromByteArray(ByteArray(16) { it.toByte() })}")
    err("uuid parse bad") { Uuid.parse("zzz") }
    // hex and Base64
    val bs = byteArrayOf(1, -1, 0x7f, -128, 0x10)
    println("hex: ${bs.toHexString()} ${bs.toHexString(HexFormat { upperCase = true; bytes.byteSeparator = ":" })} ${255.toHexString()} ${(-1L).toHexString()} ${"0aff".hexToByteArray().contentToString()} ${"ff".hexToInt()} ${"7fffffff".hexToInt()} ${0x1234.toShort().toHexString()} ${200.toUByte().toHexString()}")
    err("hex bad") { "xyz".hexToByteArray() }
    println("base64: ${Base64.encode("hello, kmicro!".encodeToByteArray())} ${Base64.decode("aGVsbG8=").decodeToString()} ${Base64.UrlSafe.encode(byteArrayOf(-5, -1, -2))} ${Base64.Default.encode(ByteArray(0))} ${Base64.Mime.encode(ByteArray(60) { it.toByte() }).length}")
    err("base64 bad") { Base64.decode("!!!") }
    // atomics
    val ai = AtomicInt(5); val al = AtomicLong(1L shl 40); val ar = AtomicReference("a")
    println("atomics: ${ai.fetchAndAdd(2)} ${ai.incrementAndFetch()} ${ai.compareAndSet(8, 10)} ${ai.load()} ${ai.exchange(1)} ${al.addAndFetch(5)} ${al.compareAndSet(1L shl 40, 0)} ${al.load()} ${ar.compareAndSet("a", "b")} ${ar.load()} ${AtomicBoolean(true).exchange(false)}")
    // print variants
    print("print:"); print(1); print('c'); print(null); print(2.5); print(listOf(1)); println()
    println(null); println(charArrayOf('o', 'k').concatToString()); println(); println("after blank")
    println("done")
}

// Known not to work on kmicro yet: kotlin.random and the clock. Creating any Random, even a seeded one, first
// initialises Random.Default, whose seed comes from the clock native Kotlin_system_getSteadyTimeNanos, which kmicro does
// not have; measureTime and TimeSource.Monotonic need the same native.
// Not run by default: python tools/difftest.py d_known_random_time
import kotlin.random.Random
import kotlin.random.nextInt
import kotlin.random.nextUInt
import kotlin.time.TimeSource
import kotlin.time.measureTime

fun err(label: String, block: () -> Any?) {
    val r = runCatching(block)
    val e = r.exceptionOrNull()
    println("$label: " + if (e == null) "ok ${r.getOrNull()}" else "${e::class.simpleName}: ${e.message}")
}

fun main() {
    println("before Random(42)")
    val r = Random(42)
    println("Random(42): ${r.nextInt()} ${r.nextInt(100)} ${r.nextInt(-5, 5)} ${r.nextInt(1..6)} ${r.nextLong()} ${r.nextLong(1000L)} ${r.nextLong(-10L, 10L)} ${r.nextDouble()} ${r.nextDouble(5.0)} ${r.nextDouble(1.0, 2.0)} ${r.nextFloat()} ${r.nextBoolean()} ${r.nextBits(7)} ${r.nextUInt()}")
    println("nextBytes: ${r.nextBytes(8).contentToString()} ${r.nextBytes(ByteArray(10), 2, 6).contentToString()}")
    val r2 = Random(42L); val r3 = Random(42)
    println("same seed: ${r2.nextInt() == r3.nextInt()} ${Random(0).nextInt()} ${Random(-1L).nextLong()} ${Random(Long.MAX_VALUE).nextDouble()}")
    println("shuffled/random: ${(1..12).shuffled(Random(3))} ${listOf("a", "b", "c", "d").random(Random(9))} ${(1..100).random(Random(10))} ${arrayOf(1, 2, 3).apply { shuffle(Random(4)) }.contentToString()} ${IntArray(5) { it }.apply { shuffle(Random(5)) }.contentToString()}")
    err("nextInt bad range") { Random(1).nextInt(5, 5) }
    err("random empty") { emptyList<Int>().random(Random(1)) }
    val sh = (1..10).toMutableList(); sh.shuffle(Random(42)); println("shuffle(Random(42)): $sh")
    println("xyz".random(Random(1)))
    println(Random(7).nextLong() == Random(7).nextLong())
    val n = Random.nextInt(10)
    println("default random in range: ${n in 0..9}")
    val d = measureTime { var s = 0; for (i in 0..1000) s += i }
    println("measureTime ok: ${d.inWholeDays == 0L}")
    val mark = TimeSource.Monotonic.markNow()
    println("elapsed not negative: ${!mark.elapsedNow().isNegative()}")
    println("done")
}
